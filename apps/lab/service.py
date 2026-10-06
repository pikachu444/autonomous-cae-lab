"""Process-local coordination for the public Lab API; no engineering rules."""

from copy import deepcopy
from dataclasses import dataclass
import hashlib
import inspect
import json
import math
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import secrets
import threading
import time
from typing import Callable, Mapping
import uuid

from caelab import Lab
from caelab.execution_control import CancellationToken, cancellation_scope, check_cancelled
from caelab.storage import check_id, load_json, utc_now

from .job_journal import HTTPJobJournal, JournalError


OPERATIONS = {
    "study_create": "create_study", "parameter_discover": "discover_parameters",
    "parameter_register": "register_parameter", "registry_refresh": "refresh_registry",
    "cad_run": "run_experiment", "native_create": "create_native_model",
    "native_import": "import_native_model",
    "native_inspect": "inspect_native_model", "native_final": "select_native_final",
    "analysis_run": "run_analysis", "pde_run": "run_pde",
    "model_analysis_run": "run_model_analysis", "doe_plan": "plan_doe",
    "doe_run": "run_doe", "optimization_plan": "plan_optimization",
    "optimization_run": "run_optimization",
    "model_parameters_discover": "discover_model_parameters",
    "model_parameters_register": "register_model_parameter",
    "model_optimization_plan": "plan_model_optimization",
    "condition_parameters_discover": "discover_condition_parameters",
    "condition_parameters_register": "register_condition_parameter",
    "condition_optimization_plan": "plan_condition_optimization",
    "response_comparison_save": "save_response_comparison",
    "analysis_conditions_save": "save_analysis_conditions",
}
READ_OPERATIONS = frozenset({"parameter_discover", "native_inspect", "model_parameters_discover", "condition_parameters_discover"})
REFERENCE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


class ServiceError(ValueError):
    def __init__(self, status: int, message: str):
        self.status = status
        super().__init__(message)


@dataclass(frozen=True)
class Store:
    id: str
    path: Path
    writable: bool
    lab: Lab


def contained(root: Path, relative: str) -> Path:
    """Resolve a server-owned relative reference without following an escape."""
    if (not isinstance(relative, str) or not relative or "\\" in relative
            or "\x00" in relative or ":" in relative):
        raise ServiceError(400, "A relative manifest path is required")
    parts = relative.split("/")
    if (PurePosixPath(relative).is_absolute() or PureWindowsPath(relative).is_absolute()
            or any(part in {"", ".", ".."} for part in parts)):
        raise ServiceError(400, "Absolute paths and traversal are not allowed")
    target = root.joinpath(*parts).resolve()
    if not target.is_relative_to(root.resolve()):
        raise ServiceError(400, "Path escapes its configured root")
    return target


class LabService:
    def __init__(self, store: str | Path, *, libraries: Mapping[str, str | Path] | None = None,
                 lab_factory: Callable[[Path], Lab] = Lab, research=None,
                 http_journal: HTTPJobJournal | None = None):
        local = Path(store).resolve()
        local.mkdir(parents=True, exist_ok=True)
        self._stores = {"local": Store("local", local, True, lab_factory(local))}
        for identifier, value in (libraries or {}).items():
            check_id(identifier)
            if identifier == "local":
                raise ValueError("The local store ID is reserved")
            path = Path(value).resolve()
            if not path.is_dir():
                raise ValueError(f"Configured library does not exist: {identifier}")
            if path.is_relative_to(local) or local.is_relative_to(path):
                raise ValueError("Writable store and read-only libraries must not overlap")
            self._stores[identifier] = Store(identifier, path, False, lab_factory(path))
        self.token = secrets.token_urlsafe(32)
        self._active_store = "local"
        self._lock = threading.RLock()
        self._active_job = None
        self._jobs: dict[str, dict] = {}
        self._job_tokens: dict[str, CancellationToken] = {}
        self._job_threads: dict[str, threading.Thread] = {}
        self._accepting_jobs = True
        self._research = research
        self._http_journal = http_journal
        self._recovery_reasons = []
        if http_journal is not None:
            if http_journal.store != local:
                raise ValueError("HTTP journal must belong to the configured local store")
            self._jobs = deepcopy(http_journal.jobs)
            self._recovery_reasons = list(http_journal.errors)
            if self._recovery_reasons:
                self._accepting_jobs = False

    def _http_failure(self, identifier: str | None, error: BaseException):
        reason = self._error(error)
        self._recovery_reasons.append(reason)
        self._accepting_jobs = False
        if identifier is not None:
            job = self._jobs[identifier]
            if job.get("status") != "RECOVERY_REQUIRED":
                job["retained_status"] = job["status"]
            job.update(status="RECOVERY_REQUIRED", outcome="UNKNOWN", recovery_required=True,
                       recovery_reason="실행 기록의 종료 상태를 확인해야 합니다. 새 작업은 차단됩니다.",
                       persistence_error=reason)

    def _http_event(self, identifier: str, event: str, *, details: dict | None = None) -> bool:
        if self._http_journal is None:
            return True
        if self._jobs[identifier].get("recovery_required"):
            self._jobs[identifier]["status"] = "RECOVERY_REQUIRED"
            return False
        try:
            self._http_journal.append(identifier, event, self._jobs[identifier], details=details)
            return True
        except (OSError, ValueError, TypeError) as error:
            self._http_failure(identifier, error)
            return False

    def _research_prepared(self, identifier: str, details: dict):
        with self._lock:
            self._jobs[identifier]["research_evidence"] = deepcopy(details)
            if not self._http_event(identifier, "PREPARED", details=details):
                raise JournalError("HTTP Research request binding could not be retained")

    def research_status(self) -> dict:
        """Describe the configured official control plane, never choose a model."""
        with self._lock:
            if self._recovery_reasons:
                return {"configured": self._research is not None, "available": False,
                        "state": "RECOVERY_REQUIRED", "outcome": "UNKNOWN",
                        "reason": "이전 실행의 종료 상태를 확인해야 합니다. 새 작업은 차단됩니다."}
        if self._research is None:
            return {"configured": False, "available": False, "state": "NOT_CONFIGURED",
                    "reason": "AI 연구 연결이 준비되지 않았습니다."}
        status = self._research.status()
        with self._lock:
            if not self._selected().writable:
                return {**status, "available": False, "reason": "읽기 전용 기록입니다. 작업 저장소를 선택하세요."}
            if self._active_job is not None or not self._accepting_jobs:
                return {**status, "available": False, "reason": "진행 중인 작업의 종료 상태를 먼저 확인하세요."}
        return status

    def execution_status(self) -> dict:
        """Small resident observation; no store scan or native execution."""
        with self._lock:
            if self._recovery_reasons:
                return {"state": "RECOVERY_REQUIRED", "outcome": "UNKNOWN",
                        "scope": "HTTP_JOB_CONTROL",
                        "idle_confirmed": False, "accepting_jobs": False,
                        "reason": "실행 상태 확인 필요 · 새 작업 차단. 보존 기록을 조회할 수 있습니다.",
                        "recovered_job_ids": [identifier for identifier, job in self._jobs.items()
                                              if job.get("recovery_required")]}
            pending = (self._active_job is not None or
                       any(token.cleanup_pending for token in self._job_tokens.values()))
            return {"state": "BUSY" if pending else "IDLE", "idle_confirmed": not pending,
                    "accepting_jobs": self._accepting_jobs,
                    **({"scope": "HTTP_JOB_CONTROL"} if self._http_journal is not None else {})}

    def _selected(self) -> Store:
        with self._lock:
            return self._stores[self._active_store]

    def select_store(self, identifier: str) -> dict:
        with self._lock:
            if self._active_job is not None:
                raise ServiceError(409, "A job is running; store switching is blocked")
            if not isinstance(identifier, str) or identifier not in self._stores:
                raise ServiceError(400, "Select a configured store ID")
            self._active_store = identifier
            return self.overview()

    def capabilities(self) -> list[dict]:
        descriptions = {
            "study_create": ("연구 만들기", None, "IMPLEMENTED", "Core 연구 질문·가설·목표 기록"),
            "response_comparison_save": ("관측·시험 기준과 비교 기록", None, "IMPLEMENTED", "사용자가 선언한 관측값과 보존된 수치 응답의 차이; 원인·물리 검증 또는 사용 승인 아님"),
            "analysis_conditions_save": ("CAD 개정에 해석 조건 저장", None, "EXPERIMENTAL", "영역·재료·하중·구속의 명시적 선언과 solver 지원 여부; 입력 지원은 실행·물성 검증 아님"),
            "parameter_discover": ("설계 변수 찾기", "fixture.cadquery / fixture.freecad / fixture.assembly", "IMPLEMENTED", "기존 CAD adapter의 native 변수"),
            "parameter_register": ("설계 변수 등록", "fixture.cadquery / fixture.freecad / fixture.assembly", "IMPLEMENTED", "기존 Core의 범위·형상 효과 검증"),
            "registry_refresh": ("변수 매핑 갱신", None, "IMPLEMENTED", "기존 Core의 native 개정 확인"),
            "cad_run": ("CAD 실험", "fixture.cadquery / fixture.freecad / fixture.assembly", "IMPLEMENTED", "원본 조립체·단일 부품의 형상 검증과 재생성 입력·증거; 조립체 해석·강도 검증은 별도"),
            "native_create": ("FreeCAD 원본 만들기", "fixture.freecad", "EXPERIMENTAL", "설정된 FreeCAD 실행 환경 필요"),
            "native_import": ("내 FreeCAD 모델 가져오기", "fixture.freecad", "EXPERIMENTAL", "100바이트~25MiB FCStd 원본 보존·실제 native 가져오기; 임의 CAD의 구조해석 지원은 별도"),
            "native_inspect": ("FreeCAD 원본 살펴보기", "fixture.freecad", "EXPERIMENTAL", "기존 native model ID로 조회"),
            "native_final": ("최종 형상 선택", "fixture.freecad", "EXPERIMENTAL", "원본의 기존 final-solid 선택"),
            "analysis_run": ("선형 구조 해석", "fixture.calculix", "EXPERIMENTAL", "검증된 CAD parent, 가정된 재료·하중; NOT_RELEASED"),
            "pde_run": ("약형 PDE 실험", ", ".join(sorted(self._selected().lab.pde_adapters)), "EXPERIMENTAL", "제한된 선형·비선형 scalar weak form와 해석해 비교; 물리 검증 UNKNOWN"),
            "model_analysis_run": ("모델·재료·동해석 실행", "CalculiX / Code_Aster / MFront / OpenRadioss", "EXPERIMENTAL", "제한된 선형 모델·큰 회전 보·재료·동해석; 실행 기록별 수치 검증 확인, 물리·강도 UNKNOWN"),
            "doe_plan": ("DOE 계획", "scipy.latin_hypercube", "IMPLEMENTED", "수치 엔진이 후보를 생성"),
            "doe_run": ("DOE 실행", "scipy.latin_hypercube", "IMPLEMENTED", "기존 Core의 개별 실험과 증거 재사용"),
            "optimization_plan": ("최적화 계획", "scipy.differential_evolution", "IMPLEMENTED", "수치 엔진의 목적 함수·제약·seed"),
            "optimization_run": ("수치 최적화 실행", "scipy.differential_evolution", "IMPLEMENTED", "SciPy 후보와 기존 validation 판정; 자동 release 아님"),
            "model_parameters_discover": ("해석 모델 변수 찾기", None, "IMPLEMENTED", "adapter가 선언한 수치 입력과 단위·범위"),
            "model_parameters_register": ("해석 모델 변수 등록", None, "IMPLEMENTED", "선택한 입력만 변경하고 나머지 모델 선언 보존"),
            "model_optimization_plan": ("해석 모델 최적화 계획", "scipy.differential_evolution", "IMPLEMENTED", "공통 수치 엔진과 model 기준 목적 함수·제약·재개 기록"),
            "condition_parameters_discover": ("고정 CAD의 조건 입력 찾기", "structure.calculix.native", "EXPERIMENTAL", "같은 CAD 개정의 재료 E·ν와 명시한 힘 성분; engineering UNKNOWN"),
            "condition_parameters_register": ("조건 연구 변수 등록", "structure.calculix.native", "EXPERIMENTAL", "원 CAD·면·조건 출처를 보존하는 선언 수치 입력"),
            "condition_optimization_plan": ("고정 CAD 조건 탐색 계획", "scipy.differential_evolution", "EXPERIMENTAL", "CAD를 재생성하지 않고 조건 후보·실제 native 자식·결과 비교; AI 실행 admission은 별도"),
        }
        lab = self._selected().lab
        rows = [{"operation": operation, "label": label, "backend": backend,
                 "status": status, "scope": scope,
                 "callable": callable(getattr(lab, OPERATIONS[operation], None))}
                for operation, (label, backend, status, scope) in descriptions.items()]
        rows.append({"operation": "research_run", "label": "AI에게 연구 질문하기",
                     "backend": "OpenScience", "status": "EXPERIMENTAL",
                     "scope": "연결한 공식 모델이 허용된 도구로 연구하고 같은 기록을 해석합니다.",
                     "callable": self._research is not None})
        for operation, label, backend, scope in (
            ("nonlinear_contact", "비선형·접촉", "Code_Aster / CalculiX", "다음 독립 reference benchmark 필요"),
            ("physical_validation", "실물·내구 시험", None, "측정·시험 근거가 필요하며 UNKNOWN 유지"),
            ("uncertainty_inverse", "역문제·불확실성", None, "추가 numerical engine 및 관측 자료 연결 필요"),
            ("hpc", "원격·병렬 계산", "MPI / SSH / Slurm / PBS", "실제 환경과 작업·증거 추적 검증 필요"),
            ("field_postprocessing", "해석 필드·애니메이션 화면", None, "원본 field 파일은 보존; 통합 field viewer는 미구현"),
        ):
            rows.append({"operation": operation, "label": label, "backend": backend,
                         "status": "PLANNED", "scope": scope, "callable": False})
        return rows

    def overview(self) -> dict:
        with self._lock:
            selected = self._selected()
            jobs = deepcopy(list(self._jobs.values()))
            active = self._active_store
            accepting = self._accepting_jobs
        studies, experiments, campaigns = [], [], []
        for folder in self._folders(selected, "studies"):
            try:
                contained(selected.path, f"studies/{check_id(folder.name)}/study.json")
                study = selected.lab.inspect_study(check_id(folder.name))
                studies.append(study)
            except Exception as exc:
                studies.append({"id": folder.name, "error": self._error(exc)})
        for folder in self._folders(selected, "experiments"):
            row = {"id": folder.name, "study_id": None, "status": None, "decision": None,
                   "solver_status": None, "backend": None, "created_utc": None,
                   "cad_revision": None, "model_revision": None, "integrity": "NOT_CHECKED"}
            try:
                check_id(folder.name)
                result = load_json(contained(selected.path, f"experiments/{folder.name}/result.json"))
                row.update(study_id=result["study"]["id"], status=result["status"],
                           decision=result["decision"], solver_status=result["solver_status"],
                           backend=result["provenance"]["adapter"],
                           created_utc=result["provenance"]["created_utc"],
                           cad_revision=result["cad_revision"], model_revision=result.get("model_revision"))
            except Exception as exc:
                row["error"] = self._error(exc)
            experiments.append(row)
        for namespace, kind in (("campaigns", "doe"), ("optimizations", "optimization")):
            for folder in self._folders(selected, namespace):
                row = {"id": folder.name, "type": kind, "study_id": None}
                try:
                    check_id(folder.name)
                    plan = load_json(contained(selected.path, f"{namespace}/{folder.name}/plan.json"))
                    row["study_id"] = plan["study_id"]
                except Exception as exc:
                    row["error"] = self._error(exc)
                campaigns.append(row)
        return {"token": self.token, "active_store": active, "accepting_jobs": accepting,
                "recovery_required": bool(self._recovery_reasons),
                "execution": self.execution_status(),
                "stores": [{"id": item.id, "label": item.id, "writable": item.writable}
                           for item in self._stores.values()],
                "studies": studies, "experiments": experiments, "campaigns": campaigns,
                "capabilities": self.capabilities(), "jobs": jobs}

    def _folders(self, store: Store, namespace: str) -> list[Path]:
        root = contained(store.path, namespace)
        return sorted((p for p in root.iterdir() if p.is_dir()), key=lambda p: p.name) if root.exists() else []

    @staticmethod
    def _error(exc: BaseException) -> str:
        return f"{type(exc).__name__}: {exc}"

    def study(self, identifier: str) -> dict:
        selected = self._selected()
        contained(selected.path, f"studies/{check_id(identifier)}/study.json")
        contained(selected.path, f"studies/{identifier}/parameters.json")
        return {"study": selected.lab.inspect_study(identifier), "registry": selected.lab.registry(identifier)}

    def experiment(self, identifier: str) -> dict:
        from .reporting import verified_record
        return verified_record(self._selected().lab, check_id(identifier))

    def response_histories(self, identifier: str) -> dict:
        from .reporting import preflight_records, recheck_records
        selected = self._selected()
        expected = preflight_records(selected.lab, [check_id(identifier)])
        value = selected.lab.response_histories(identifier)
        recheck_records(selected.lab, expected)
        return value

    @staticmethod
    def _comparison_source(selected: Store, identifier: str) -> str:
        path = contained(selected.path, f"response_comparisons/{check_id(identifier)}/record.json")
        contained(selected.path, f"response_comparisons/{identifier}/receipt.json")
        value = load_json(path)
        return check_id(value["request"]["experiment_id"])

    def _response_comparison(self, selected: Store, identifier: str) -> dict:
        from .reporting import preflight_records, recheck_records
        from jsonschema.exceptions import ValidationError
        source = self._comparison_source(selected, identifier)
        expected = preflight_records(selected.lab, [source])
        try:
            record = selected.lab.inspect_response_comparison(identifier)
        except ValidationError as error:
            raise ValueError("Comparison record schema is invalid") from error
        recheck_records(selected.lab, expected)
        return {"record": record, "integrity": "VERIFIED"}

    def response_comparison(self, identifier: str) -> dict:
        return self._response_comparison(self._selected(), check_id(identifier))

    def analysis_conditions_catalog(self, experiment_id: str) -> dict:
        return self._selected().lab.describe_analysis_conditions(check_id(experiment_id))

    def analysis_conditions(self, identifier: str) -> dict:
        return {"record": self._selected().lab.inspect_analysis_conditions(check_id(identifier)),
                "integrity": "VERIFIED"}

    def analysis_conditions_list(self, experiment_id: str) -> dict:
        return {"records": self._selected().lab.list_analysis_conditions(check_id(experiment_id))}

    def response_comparisons(self, study_id: str) -> list[dict]:
        selected = self._selected()
        study_id = check_id(study_id)
        contained(selected.path, f"studies/{study_id}/study.json")
        selected.lab.inspect_study(study_id)
        root = contained(selected.path, "response_comparisons")
        if not root.is_dir():
            return []
        rows = []
        for folder in sorted(root.iterdir()):
            try:
                value = self._response_comparison(selected, check_id(folder.name))
                if value["record"]["source"]["study_id"] == study_id:
                    rows.append(value)
            except (OSError, ValueError, KeyError, TypeError) as error:
                rows.append({"id": folder.name, "integrity": "UNKNOWN", "error": str(error)})
        return rows

    def _campaign(self, selected: Store, identifier: str) -> tuple[str, Path]:
        check_id(identifier)
        matches = [(kind, contained(selected.path, f"{namespace}/{identifier}"))
                   for namespace, kind in (("campaigns", "doe"), ("optimizations", "optimization"))]
        matches = [(kind, path) for kind, path in matches if path.is_dir()]
        if len(matches) != 1:
            raise ServiceError(404 if not matches else 409, "Campaign is missing or its ID is ambiguous")
        return matches[0]

    def _campaign_preflight(self, selected: Store, identifier: str, *, with_records=False):
        from .reporting import preflight_records
        kind, folder = self._campaign(selected, identifier)
        references = set()

        def collect(value):
            if isinstance(value, dict):
                for key, item in value.items():
                    if key in {"experiment_id", "cad_experiment_id", "analysis_experiment_id", "model_experiment_id"} and item:
                        references.add(check_id(item))
                    collect(item)
            elif isinstance(value, list):
                for item in value:
                    collect(item)

        paths = [contained(folder, "plan.json")]
        if contained(folder, "result.json").exists():
            paths.append(contained(folder, "result.json"))
        for namespace in ("journal", "candidates", "checkpoints"):
            directory = contained(folder, namespace)
            if directory.exists():
                paths.extend(contained(folder, f"{namespace}/{p.name}") for p in directory.glob("*.json"))
        for path in paths:
            collect(load_json(path))
        existing = [experiment_id for experiment_id in sorted(references)
                    if contained(selected.path, f"experiments/{experiment_id}").exists()]
        records = preflight_records(selected.lab, existing)
        return (kind, records) if with_records else kind

    def campaign(self, identifier: str) -> dict:
        selected = self._selected()
        from .reporting import recheck_records
        kind, records = self._campaign_preflight(selected, identifier, with_records=True)
        _kind, folder = self._campaign(selected, identifier)
        plan_path = contained(folder, 'plan.json')
        plan_raw = plan_path.read_bytes()
        plan = json.loads(plan_raw)
        method = selected.lab.inspect_doe if kind == "doe" else selected.lab.inspect_optimization
        record = method(identifier)
        recheck_records(selected.lab, records)
        if (contained(folder, 'plan.json').read_bytes() != plan_raw
                or ('plan' in record and record['plan'] != plan)
                or ('plan_sha256' in record and record['plan_sha256'] != hashlib.sha256(plan_raw).hexdigest())):
            raise ValueError('Campaign plan changed while reopening the verified results')
        return {"type": kind, "record": record, 'plan': plan}

    def compare(self, identifiers: list[str]) -> list[dict]:
        from .reporting import verified_record
        if not identifiers or len(identifiers) > 12 or len(set(identifiers)) != len(identifiers):
            raise ServiceError(400, "Compare requires 1–12 distinct experiment IDs")
        lab = self._selected().lab
        for identifier in identifiers:
            verified_record(lab, check_id(identifier))
        return lab.compare(identifiers)

    def artifact(self, identifier: str, relative: str) -> tuple[bytes, str, str]:
        from .reporting import verified_record
        selected = self._selected()
        root = contained(selected.path, f"experiments/{check_id(identifier)}")
        path = contained(root, relative)
        record = verified_record(selected.lab, identifier)
        entries = [a for a in record["result"]["artifacts"] if a["path"] == relative]
        if len(entries) != 1:
            raise ServiceError(404, "File is not listed in the verified artifact manifest")
        entry = entries[0]
        payload = path.read_bytes()
        if len(payload) != entry["size_bytes"] or hashlib.sha256(payload).hexdigest() != entry["sha256"]:
            raise ServiceError(409, "Artifact changed during retrieval")
        mime = entry.get("mime_type", "application/octet-stream")
        image_extensions = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                            ".webp": "image/webp", ".gif": "image/gif"}
        safe_image = image_extensions.get(path.suffix.lower())
        # Active content is always a download, even when a manifest declares HTML/JS/SVG.
        disposition = "inline" if safe_image and mime == safe_image else "attachment"
        return payload, safe_image if disposition == "inline" else "application/octet-stream", disposition

    def report(self, identifier: str, format: str) -> bytes:
        from .reporting import bundle_bytes, render_html, verified_record
        lab = self._selected().lab
        check_id(identifier)
        if format == "zip":
            return bundle_bytes(lab, identifier)
        record = verified_record(lab, identifier)
        if format == "html":
            return render_html(record).encode("utf-8")
        if format == "json":
            return json.dumps(record, ensure_ascii=False, allow_nan=False).encode("utf-8")
        raise ServiceError(404, "Unknown report format")

    def presets(self) -> dict:
        from scripts.verify_pde import specification as pde_specification
        from plugins.pde_nonlinear.reference import manufactured_settings as nonlinear_pde_specification
        from plugins.pde_elliptic.reference import manufactured_settings as rectangle_pde_specification
        from plugins.pde_transient.reference import manufactured_settings as transient_pde_specification
        from plugins.pde_vector.reference import manufactured_settings as vector_pde_specification
        from plugins.pde_coupled.reference import manufactured_settings as coupled_pde_specification
        from caelab.adapters.fenicsx_imported import manufactured_settings as imported_pde_specification
        from scripts.verify_codeaster import specification as codeaster_specification
        from scripts.verify_plasticity import specification as plasticity_specification
        from plugins.geometric_nonlinearity.reference import default_settings as geometric_specification
        from scripts.verify_openradioss import specification as explicit_specification
        from scripts.verify_compliant_drop import specification as compliant_specification
        from plugins.material_point.reference import canonical_settings as material_specification
        from plugins.material_point.inverse_reference import canonical_settings as inverse_specification
        from plugins.hyperelastic.reference import canonical_settings as hyperelastic_specification
        from plugins.material_point.viscoelastic_reference import canonical_settings as viscoelastic_specification
        from plugins.structural_families.reference import specification as family_specification
        material_path = (Path(__file__).resolve().parents[2] /
                         "plugins/fixture_design/upstream/examples/printed_material_ASSUMED.json")
        # Exact existing acceptance inputs; material remains explicitly assumed.
        presets = {
            "structural_linear": {"operation": "analysis_run", "backend": "fixture.calculix", "parent_backends": ["fixture.cadquery"], "label": "가정된 재료·하중의 선형 구조 screen",
                "status": "EXPERIMENTAL", "scope": "roller_support 단일 부품의 100 N/support 및 미측정 orthotropic 재료; peak stress와 강도·물리 검증 UNKNOWN, NOT_RELEASED",
                "settings": {"load": {"force_per_support_N": 100.0,
                    "source": "Illustrative 100 N screen per support; unqualified, not measured"},
                    "material": load_json(material_path), "mesh": {"max_sizes_mm": [4.0, 3.0, 2.0]}}},
            "pde_canonical": {"operation": "pde_run", "backend": "pde.fenicsx", "label": "Canonical Poisson 약형 benchmark",
                "status": "EXPERIMENTAL", "scope": "dimensionless unit square의 해석해·오차·수렴 검증; 물리 검증 UNKNOWN",
                "settings": pde_specification()},
            "pde_nonlinear": {"operation": "pde_run", "backend": "pde.fenicsx.nonlinear", "label": "비선형 확산 약형 benchmark",
                "status": "EXPERIMENTAL", "scope": "단위 정사각형의 해석해·Newton 잔차·오차 수렴 비교; 일반 비선형·MPI·물리 자격 UNKNOWN",
                "settings": nonlinear_pde_specification()},
            "pde_rectangle": {"operation": "pde_run", "backend": "pde.fenicsx.rectangle", "label": "직사각형·혼합 경계 약형 benchmark",
                "status": "EXPERIMENTAL", "scope": "영역 크기와 변별 고정값·바깥 유량을 지정하는 scalar PDE; 해석해·수렴·경계 필드 확인, 물리 자격 UNKNOWN",
                "settings": rectangle_pde_specification()},
            "pde_transient_mesh": {"operation": "pde_run", "backend": "pde.fenicsx.transient", "label": "시간에 따른 확산·반응 — 메시 비교",
                "status": "EXPERIMENTAL", "scope": "초기·중간·최종 필드와 시간별 조건을 보존하고 메시 정확도를 비교; 실제 연구 연결과 물리 자격 UNKNOWN",
                "settings": transient_pde_specification()},
            "pde_transient_time": {"operation": "pde_run", "backend": "pde.fenicsx.transient", "label": "시간에 따른 확산·반응 — 시간 간격 비교",
                "status": "EXPERIMENTAL", "scope": "고정된 메시에서 시간 간격에 따른 오차·잔차·전체 이력을 비교; 실제 연구 연결과 물리 자격 UNKNOWN",
                "settings": transient_pde_specification(axis="time", case="temporal")},
            "pde_vector_lame": {"operation": "pde_run", "backend": "pde.fenicsx.vector", "label": "두 성분 벡터 약형 — 결합·경계하중",
                "status": "EXPERIMENTAL", "scope": "두 성분의 결합과 방향별 경계하중·오차를 보존하는 Lamé형 PDE; 실제 연구 연결과 물리 자격 UNKNOWN",
                "settings": vector_pde_specification()},
            "pde_vector_harmonic": {"operation": "pde_run", "backend": "pde.fenicsx.vector", "label": "두 성분 벡터 약형 — 원항 없는 기준식",
                "status": "EXPERIMENTAL", "scope": "원항이 없는 기준식으로 벡터 방향·전체 필드·수렴을 확인; 실제 연구 연결과 물리 자격 UNKNOWN",
                "settings": vector_pde_specification(case="harmonic")},
            "pde_coupled_interface": {"operation": "pde_run", "backend": "pde.fenicsx.coupled", "label": "두 영역의 결합 방정식 — 재료 경계",
                "status": "EXPERIMENTAL", "scope": "두 변수의 결합과 재료 경계 양쪽의 필드·하중을 보존; 실제 연구 연결과 물리 자격 UNKNOWN",
                "settings": coupled_pde_specification()},
            "pde_coupled_harmonic": {"operation": "pde_run", "backend": "pde.fenicsx.coupled", "label": "두 영역의 결합 방정식 — 원항 없는 기준식",
                "status": "EXPERIMENTAL", "scope": "원항 없는 기준식으로 재료 경계와 전체 필드·수렴을 확인; 실제 연구 연결과 물리 자격 UNKNOWN",
                "settings": coupled_pde_specification(case="harmonic")},
            "pde_imported_l_shape": {"operation": "pde_run", "backend": "pde.fenicsx.imported", "label": "가져온 메시 — L자 영역과 물리 경계",
                "status": "EXPERIMENTAL", "scope": "작은 Gmsh ASCII 메시의 원본·경계 이름을 보존하는 scalar PDE; 실제 연구 연결과 물리 자격 UNKNOWN",
                "settings": imported_pde_specification()},
            "pde_imported_harmonic": {"operation": "pde_run", "backend": "pde.fenicsx.imported", "label": "가져온 메시 — 원항 없는 기준식",
                "status": "EXPERIMENTAL", "scope": "L자 영역의 원항 없는 기준식과 전체 필드·수렴을 확인; 실제 연구 연결과 물리 자격 UNKNOWN",
                "settings": imported_pde_specification(case="harmonic")},
            "codeaster_linear": {"operation": "model_analysis_run", "backend": "structural.code_aster", "label": "독립적인 선형 elasticity benchmark",
                "status": "EXPERIMENTAL", "scope": "가정된 solid block의 affine analytical reference; 비선형·접촉 및 물리·강도 검증 UNKNOWN",
                "settings": codeaster_specification()},
            "codeaster_plasticity": {"operation": "model_analysis_run", "backend": "structural.code_aster.plasticity", "label": "소성 재료의 하중·제하 benchmark",
                "status": "EXPERIMENTAL", "scope": "J2 small-strain 전체 이력·해석해 검증; 접촉·기하 비선형·재료 자격 UNKNOWN",
                "settings": plasticity_specification()},
            "codeaster_geometric": {"operation": "model_analysis_run", "backend": "structural.code_aster.geometric_nonlinearity", "label": "보의 큰 회전 — 끝 모멘트 기준 해석",
                "status": "EXPERIMENTAL", "scope": "끝 모멘트를 받는 보의 1 rad 이내 회전·변형·반력·곡률 비교; 실제 솔버 기준 검증 대기, 물리·강도 UNKNOWN",
                "settings": geometric_specification()},
            "material_point": {"operation": "model_analysis_run", "backend": "material.mfront", "label": "재료점의 응력·접선 benchmark",
                "status": "EXPERIMENTAL", "scope": "실제 MGIS·MTest 응력 및 유한차분 접선 검증; 솔버 결합·물리적 재료 자격 UNKNOWN",
                "settings": material_specification()},
            "material_inverse": {"operation": "model_analysis_run", "backend": "material.mfront.inverse", "label": "합성 기준값의 재료 역추정 평가",
                "status": "EXPERIMENTAL", "scope": "합성 응력 기준값과 실제 MGIS 응력을 비교하는 평가; 수치 탐색은 공통 engine, 측정 재료·역추정 자격 UNKNOWN",
                "settings": inverse_specification()},
            "material_hyperelastic": {"operation": "model_analysis_run", "backend": "material.mfront.hyperelastic", "label": "큰 회전 재료점의 응력·에너지 기준 해석",
                "status": "EXPERIMENTAL", "scope": "작은 Green 변형과 큰 회전의 SVK 재료점 응력·접선·저장 에너지 비교; 실제 솔버 수치 검증 대기, 물성·강도·솔버 결합 UNKNOWN",
                "settings": hyperelastic_specification()},
            "material_viscoelastic": {"operation": "model_analysis_run", "backend": "material.mfront.viscoelastic", "label": "점탄성 재료의 하중·유지·제하",
                "status": "EXPERIMENTAL", "scope": "합성 단일 Maxwell 가지의 응력·이력·에너지 비교; 실제 수치 검증 대기, 물성·강도·솔버 결합 UNKNOWN",
                "settings": viscoelastic_specification()},
            "explicit_freefall": {"operation": "model_analysis_run", "backend": "explicit.openradioss", "label": "강체 자유낙하 benchmark",
                "status": "EXPERIMENTAL", "scope": "질량·중력·초기 속도·시간 간격에 대한 실제 자유낙하 검증; 충격·파손 자격 UNKNOWN",
                "settings": explicit_specification(case="rigid_cube_freefall")},
            "explicit_ground_stop": {"operation": "model_analysis_run", "backend": "explicit.openradioss", "label": "벽 접촉 실패 재현",
                "status": "REJECTED", "scope": "기존 벽 접촉은 충돌 후 속도·충격량 이력 기준 실패; 접촉 단계 미완료, NOT_RELEASED",
                "settings": explicit_specification(case="rigid_cube_ground_stop")},
            "explicit_compliant_stop": {"operation": "model_analysis_run", "backend": "explicit.openradioss", "label": "탄성 정지 장치의 낙하·반발 평가",
                "status": "EXPERIMENTAL", "scope": "알려진 힘 법칙의 축약 장치에서 전체 이력·에너지·반발 검증; 실제 표면 접촉·재료·파손 자격 UNKNOWN",
                "settings": compliant_specification()},
        }
        for solver, backend in (("CalculiX", "structural.families.calculix"), ("Code_Aster", "structural.families.code_aster")):
            for case, load_case, label in (
                ("ansys_vmd1_regular", "Fx", "보의 인장"),
                ("ansys_vmd1_regular", "Fy", "보의 Y 방향 굽힘"),
                ("ansys_vmd1_regular", "Fz", "보의 Z 방향 굽힘"),
                ("lame_cylinder_plane_strain", "pressure", "두꺼운 원통의 내압"),
                ("scordelis_lo_solid", "gravity", "곡면 지붕의 자중"),
            ):
                presets[f"family_{case}_{load_case}_{solver.lower()}"] = {
                    "operation": "model_analysis_run", "backend": backend,
                    "label": f"{label} · {solver}", "status": "EXPERIMENTAL",
                    "scope": "고정된 공개 입력·참조의 제한된 solid 모델; 원 NFX 재현·강도·물리 검증 UNKNOWN. 실제 결과 기록에서 수치 판정 확인.",
                    "settings": family_specification(case, load_case),
                }
        # Advertise the existing binding interface without calling descriptors,
        # runtime admission or a solver. Availability/qualification is separate.
        adapters = self._selected().lab.model_analysis_adapters
        for preset in presets.values():
            adapter = adapters.get(preset["backend"])
            preset["declared_inputs"] = (preset["operation"] == "model_analysis_run" and
                adapter is not None and all(callable(getattr(adapter, name, None)) for name in
                    ("describe_model", "describe_inputs", "bind_inputs", "input_runtime_identity")) and
                isinstance(getattr(adapter, "input_source_files", None), (list, tuple)) and
                bool(adapter.input_source_files))
        return presets

    def native_imports(self) -> dict:
        from .native_input import list_imports
        return list_imports(self._selected().path)

    def native_import(self, identifier: str) -> dict:
        from .native_input import inspect_import
        return inspect_import(self._selected().path, identifier)

    def submit_native_import(self, payload: bytes) -> dict:
        from .native_input import retain_input, verified_input, producer_identity, retain_result
        with self._lock:
            if self._recovery_reasons or not self._accepting_jobs:
                raise ServiceError(503, "Lab execution is closed or recovery is required")
            if self._active_job is not None:
                raise ServiceError(409, "A job is already running")
            selected = self._selected()
            if not selected.writable:
                raise ServiceError(403, "Selected library is read only")
            self._argument_paths(selected, "native_import", {})
            capture = retain_input(selected.path, payload)

            def import_owned(upload_id, input_sha256, input_bytes):
                if (upload_id != capture["id"] or input_sha256 != capture["input"]["sha256"]
                        or input_bytes != capture["input"]["size_bytes"]):
                    raise ValueError("Native import job differs from its retained input")
                self._argument_paths(selected, "native_import", {})
                producer = producer_identity(selected.path, capture)
                check_cancelled()
                original, _receipt = verified_input(selected.path, capture)
                info = selected.lab.import_native_model(original)
                return retain_result(selected.path, capture, info, producer)

            return self._submit("native_import", {"upload_id": capture["id"],
                                "input_sha256": capture["input"]["sha256"],
                                "input_bytes": capture["input"]["size_bytes"]},
                                native_method=import_owned)

    def submit(self, operation: str, arguments: dict) -> dict:
        if operation == "native_import":
            raise ServiceError(400, "Native import requires the binary file-selection route")
        return self._submit(operation, arguments)

    def _submit(self, operation: str, arguments: dict, *, native_method=None) -> dict:
        with self._lock:
            if self._recovery_reasons:
                raise ServiceError(503, "HTTP recovery is required; new execution is blocked")
            if not self._accepting_jobs:
                raise ServiceError(503, "Lab service is shutting down; new jobs are closed")
            if not isinstance(operation, str) or (operation not in OPERATIONS and operation != "research_run"):
                raise ServiceError(400, "Operation is not in the Lab allowlist")
            if not isinstance(arguments, dict):
                raise ServiceError(400, "Operation arguments must be a JSON object")
            if self._active_job is not None:
                raise ServiceError(409, "A job is already running")
            selected = self._selected()
            if not selected.writable and operation not in READ_OPERATIONS:
                raise ServiceError(403, "Selected library is read only")
            if operation == "native_import":
                if native_method is None:
                    raise ServiceError(400, "Retained native input is required")
                method = native_method
            elif operation == "research_run":
                if self._research is None:
                    raise ServiceError(503, "AI 연구 연결이 준비되지 않았습니다.")
                method = self._research.run
            else:
                method = getattr(selected.lab, OPERATIONS[operation])
            try:
                inspect.signature(method).bind(**arguments)
                if operation == "research_run":
                    question = arguments.get("question")
                    if (set(arguments) - {"question", "session_id"} or not isinstance(question, str)
                            or not question.strip() or "\x00" in question
                            or len(question.encode("utf-8")) > 16384):
                        raise ValueError("연구 질문은 빈 내용 없이 16 KiB 이내의 텍스트로 입력하세요.")
                    session = arguments.get("session_id")
                    if session is not None and (not isinstance(session, str)
                                               or not re.fullmatch(r"ses_[A-Za-z0-9]+", session)):
                        raise ValueError("확인된 대화 ID가 필요합니다.")
                self._argument_paths(selected, operation, arguments)
            except (TypeError, ValueError) as exc:
                raise ServiceError(400, str(exc)) from exc
            identifier = "J" + uuid.uuid4().hex
            job = {"id": identifier, "operation": operation, "status": "RUNNING",
                   "created_utc": utc_now(), "store_id": selected.id,
                   "cancel_requested": False, "cancel_observed": False,
                   "cleanup_pending": False, "cleanup_owners": []}
            if self._http_journal is not None:
                try:
                    self._http_journal.reserve(job, arguments)
                except (OSError, ValueError, TypeError) as error:
                    # A claim or partial admission can survive a failed write.
                    # Never start this worker or reuse another controller's claim.
                    self._http_journal.recover()
                    self._jobs.update(deepcopy(self._http_journal.jobs))
                    self._http_failure(None, error)
                    raise ServiceError(503, "HTTP admission could not be retained; recovery is required") from error
            self._jobs[identifier] = job
            self._job_tokens[identifier] = CancellationToken()
            self._active_job = identifier
            snapshot = deepcopy(job)
            worker = threading.Thread(target=self._execute,
                                      args=(selected, identifier, method, deepcopy(arguments)),
                                      name=f"caelab-{identifier}", daemon=True)
            self._job_threads[identifier] = worker
            try:
                worker.start()
            except Exception as exc:
                job.update(status="FAILED", error=self._error(exc), completed_utc=utc_now())
                self._http_event(identifier, "TERMINAL", details={"worker_started": False})
                self._active_job = None
                self._job_threads.pop(identifier)
                raise
            return snapshot

    def _argument_paths(self, selected: Store, operation: str, arguments: dict):
        # Native object paths are adapter-owned names, never client filesystem references.
        for key in ("model", "template", "backend", "analysis_backend", "engine"):
            value = arguments.get(key)
            if value is not None and (not isinstance(value, str) or not REFERENCE.fullmatch(value)):
                raise ValueError(f"{key} must be a registered name or model ID, not a filesystem path")
        for key in ("native_path", "final"):
            value = arguments.get(key)
            if value is not None and (not isinstance(value, str) or not value or len(value) > 512
                                      or any(char in value for char in ("/", "\\", "\x00", ":"))):
                raise ValueError(f"{key} must be an existing native object/dimension name")
        for key in ("study_id", "experiment_id", "parent_experiment_id", "campaign_id", "parameter_id", "hypothesis_id", "comparison_id", "conditions_id"):
            if arguments.get(key) is not None:
                check_id(arguments[key])
        for namespace in ("studies", "experiments", "ledger", "campaigns", "optimizations", "native_designs", "response_comparisons", "native_imports", "analysis_conditions"):
            contained(selected.path, namespace)
        for key, namespace in (("study_id", "studies"), ("experiment_id", "experiments"),
                               ("parent_experiment_id", "experiments"), ("comparison_id", "response_comparisons"),
                               ("conditions_id", "analysis_conditions")):
            if arguments.get(key):
                contained(selected.path, f"{namespace}/{arguments[key]}")
        if arguments.get("campaign_id"):
            for namespace in ("campaigns", "optimizations"):
                contained(selected.path, f"{namespace}/{arguments['campaign_id']}")
        native_operation = operation in {"native_inspect", "native_final"}
        if (native_operation or arguments.get("backend") == "fixture.freecad") and arguments.get("model"):
            contained(selected.path, f"native_designs/{arguments['model']}")
            contained(selected.path, f"native_designs/{arguments['model']}/editable.FCStd")

    def _execute(self, selected: Store, identifier: str, method: Callable, arguments: dict):
        update = {}
        token = self._job_tokens[identifier]
        result = None
        operation = self._jobs[identifier]["operation"]
        try:
            with self._lock:
                if not self._http_event(identifier, "WORKER_STARTED"):
                    raise JournalError("HTTP worker start could not be retained")
            with cancellation_scope(token):
                check_cancelled()
                if operation == "response_comparison_save":
                    from .reporting import preflight_records, recheck_records
                    comparison_sources = preflight_records(selected.lab, [arguments["experiment_id"]])
                if operation == "analysis_run":
                    from .reporting import verified_record
                    verified_record(selected.lab, arguments["parent_experiment_id"])
                elif operation in {"doe_run", "optimization_run"}:
                    self._campaign_preflight(selected, arguments["campaign_id"])
                check_cancelled()
                if operation == "research_run":
                    options = {"cancellation_requested": lambda: token.requested}
                    if self._http_journal is not None and "evidence_prepared" in inspect.signature(method).parameters:
                        options["evidence_prepared"] = lambda details: self._research_prepared(identifier, details)
                    result = method(**arguments, **options)
                    if result.get("status") == "CANCELLED" and token.requested:
                        # The bridge has confirmed its exact session idle and
                        # native command cleanup before acknowledging this.
                        token.check()
                else:
                    result = method(**arguments)
                    if operation == "response_comparison_save":
                        recheck_records(selected.lab, comparison_sources)
            # A request after the operation's last checkpoint is not an observed
            # interruption. Preserve that completed/failed Core result verbatim.
            update = {"status": "CANCELLED" if token.observed else "COMPLETED", "result": result}
            if operation == "research_run" and result.get("status") in {"FAILED", "CANCELLED"}:
                update["status"] = result["status"]
                if result.get("error"):
                    update["error"] = result["error"]
        except BaseException as exc:
            update = {"status": "CANCELLED" if token.observed else "FAILED", "error": self._error(exc)}
            if operation == "research_run" and result is not None:
                update["result"] = result
        finally:
            with self._lock:
                job = self._jobs[identifier]
                job.update(**update, cancel_requested=token.requested,
                           cancel_observed=token.observed,
                           cleanup_pending=token.cleanup_pending,
                           cleanup_owners=token.cleanup_owners)
                if token.cleanup_pending:
                    job.update(status="CLEANUP_PENDING", operation_finished_utc=utc_now(),
                               deferred_terminal_status="CANCELLED" if token.observed else "FAILED")
                    self._http_event(identifier, "CLEANUP_PENDING")
                else:
                    job["completed_utc"] = utc_now()
                    self._http_event(identifier, "TERMINAL")
                    self._active_job = None

    def job(self, identifier: str) -> dict:
        try:
            check_id(identifier)
        except (TypeError, ValueError) as exc:
            raise ServiceError(400, "A valid job ID string is required") from exc
        with self._lock:
            if identifier not in self._jobs:
                raise ServiceError(404, "Job not found")
            snapshot = deepcopy(self._jobs[identifier])
            research = (self._research if identifier == self._active_job and
                        snapshot["operation"] == "research_run" else None)
        if research is not None and callable(getattr(research, "progress", None)):
            # Read already retained events, never start another health/inference
            # request during the regular job poll.
            try:
                snapshot["progress"] = deepcopy(research.progress())
            except (OSError, ValueError):
                snapshot["progress"] = {"state": "UNAVAILABLE"}
        return snapshot

    def cancel(self, identifier: str) -> dict:
        """Request cooperative cancellation; a terminal job is unchanged."""
        try:
            check_id(identifier)
        except (TypeError, ValueError) as exc:
            raise ServiceError(400, "A valid job ID string is required") from exc
        with self._lock:
            if identifier not in self._jobs:
                raise ServiceError(404, "Job not found")
            if identifier == self._active_job:
                token = self._job_tokens[identifier]
                if self._http_journal is not None:
                    snapshot = self._jobs[identifier]
                    previous = deepcopy(snapshot)
                    snapshot.update(cancel_requested=True)
                    if snapshot["status"] != "CLEANUP_PENDING":
                        snapshot["status"] = "CANCEL_REQUESTED"
                    if not self._http_event(identifier, "CANCEL_REQUESTED"):
                        # Original token ownership still exists; cancellation is
                        # requested even when persistence is uncertain.
                        token.request()
                        return deepcopy(snapshot)
                    snapshot.update(previous)
                token.request()
                if (token.cleanup_pending or self._jobs[identifier]["status"] == "CLEANUP_PENDING"
                        or self._jobs[identifier].get("retained_status") == "CLEANUP_PENDING"):
                    error = self._retry_cleanup(token, timeout=1.0)
                    if error is not None:
                        self._jobs[identifier]["cleanup_error"] = error
                    self._resolve_cleanup(identifier)
                else:
                    self._jobs[identifier].update(status="CANCEL_REQUESTED", cancel_requested=True,
                                                 cancel_observed=token.observed)
            elif self._jobs[identifier].get("recovery_required"):
                job = self._jobs[identifier]
                try:
                    if self._http_journal is not None:
                        self._http_journal.cancellation_intent(identifier)
                except (OSError, ValueError, TypeError) as error:
                    self._http_failure(identifier, error)
                job.update(cancel_requested=True, cancel_observed=False,
                           cancel_limitation="기록만 보존했습니다. 재연결 소유권이 없어 종료를 확인할 수 없습니다.")
            return deepcopy(self._jobs[identifier])

    def _resolve_cleanup(self, identifier: str):
        """Publish a deferred terminal snapshot only under the service lock."""
        job, token = self._jobs[identifier], self._job_tokens[identifier]
        job.update(cancel_requested=token.requested, cancel_observed=token.observed,
                   cleanup_pending=token.cleanup_pending, cleanup_owners=token.cleanup_owners)
        worker = self._job_threads[identifier]
        if ((job["status"] == "CLEANUP_PENDING" or job.get("retained_status") == "CLEANUP_PENDING")
                and not token.cleanup_pending and not worker.is_alive()):
            job.update(status=job["deferred_terminal_status"], completed_utc=utc_now())
            self._http_event(identifier, "TERMINAL")
            self._active_job = None

    @staticmethod
    def _retry_cleanup(token: CancellationToken, *, timeout: float) -> str | None:
        try:
            token.retry_cleanup(timeout=timeout)
        except BaseException as exc:
            # Retained ownership still blocks admission; preserve the retry
            # error instead of pretending that cancellation finished.
            return LabService._error(exc)
        return None

    def shutdown(self, timeout: float = 5.0) -> dict:
        """Close admission and boundedly join owned workers without forcing threads."""
        if (type(timeout) not in (int, float) or not 0 <= timeout <= threading.TIMEOUT_MAX
                or not math.isfinite(timeout)):
            raise ServiceError(400, "Shutdown timeout must be finite, nonnegative and within the thread limit")
        deadline = time.monotonic() + timeout
        with self._lock:
            self._accepting_jobs = False
            if self._active_job is not None:
                token = self._job_tokens[self._active_job]
                job = self._jobs[self._active_job]
                job.update(cancel_requested=True, cancel_observed=token.observed)
                if job["status"] != "CLEANUP_PENDING":
                    job["status"] = "CANCEL_REQUESTED"
                self._http_event(self._active_job, "CANCEL_REQUESTED")
                token.request()
            workers = list(self._job_threads.values())
        # Workers publish their final snapshot under _lock, so never hold it
        # while joining. An uncooperative operation stays pending truthfully.
        for worker in workers:
            if worker is not threading.current_thread() and worker.is_alive():
                worker.join(max(0.0, deadline - time.monotonic()))
        with self._lock:
            cleanup_id = (self._active_job if self._active_job is not None and
                          self._job_tokens[self._active_job].cleanup_pending else None)
        if cleanup_id is not None:
            error = self._retry_cleanup(self._job_tokens[cleanup_id],
                                        timeout=max(0.0, deadline - time.monotonic()))
            with self._lock:
                if error is not None:
                    self._jobs[cleanup_id]["cleanup_error"] = error
                if self._active_job == cleanup_id:
                    self._resolve_cleanup(cleanup_id)
        # A dead Python worker can leave unresolved owned native resources.
        # Do not busy-spin the normal server shutdown loop on a failed retry.
        if any(token.cleanup_pending for token in self._job_tokens.values()):
            threading.Event().wait(max(0.0, deadline - time.monotonic()))
        with self._lock:
            if self._active_job is not None:
                self._resolve_cleanup(self._active_job)
            pending = ([deepcopy(self._jobs[self._active_job])]
                       if self._active_job is not None else [])
            pending.extend(deepcopy(job) for identifier, job in self._jobs.items()
                           if job.get("recovery_required") and identifier != self._active_job)
            return {"accepting_jobs": False, "pending": pending,
                    **({"recovery_required": bool(self._recovery_reasons)} if self._http_journal is not None else {}),
                    "joined": (not any(worker.is_alive() for worker in workers) and
                               not any(token.cleanup_pending for token in self._job_tokens.values()))}
