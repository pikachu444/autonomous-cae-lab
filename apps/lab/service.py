"""Process-local coordination for the public Lab API; no engineering rules."""

from copy import deepcopy
from dataclasses import dataclass
import hashlib
import inspect
import json
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import secrets
import threading
from typing import Callable, Mapping
import uuid

from caelab import Lab
from caelab.storage import check_id, load_json, utc_now


OPERATIONS = {
    "study_create": "create_study", "parameter_discover": "discover_parameters",
    "parameter_register": "register_parameter", "registry_refresh": "refresh_registry",
    "cad_run": "run_experiment", "native_create": "create_native_model",
    "native_inspect": "inspect_native_model", "native_final": "select_native_final",
    "analysis_run": "run_analysis", "pde_run": "run_pde",
    "model_analysis_run": "run_model_analysis", "doe_plan": "plan_doe",
    "doe_run": "run_doe", "optimization_plan": "plan_optimization",
    "optimization_run": "run_optimization",
}
READ_OPERATIONS = frozenset({"parameter_discover", "native_inspect"})
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
                 lab_factory: Callable[[Path], Lab] = Lab):
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
            "parameter_discover": ("설계 변수 찾기", "fixture.cadquery / fixture.freecad", "IMPLEMENTED", "기존 CAD adapter의 native 변수"),
            "parameter_register": ("설계 변수 등록", "fixture.cadquery / fixture.freecad", "IMPLEMENTED", "기존 Core의 범위·형상 효과 검증"),
            "registry_refresh": ("변수 매핑 갱신", None, "IMPLEMENTED", "기존 Core의 native 개정 확인"),
            "cad_run": ("CAD 실험", "fixture.cadquery / fixture.freecad", "IMPLEMENTED", "형상 검증과 편집 가능한 원본·증거; 강도 승인 아님"),
            "native_create": ("FreeCAD 원본 만들기", "fixture.freecad", "EXPERIMENTAL", "설정된 FreeCAD 실행 환경 필요"),
            "native_inspect": ("FreeCAD 원본 살펴보기", "fixture.freecad", "EXPERIMENTAL", "기존 native model ID로 조회"),
            "native_final": ("최종 형상 선택", "fixture.freecad", "EXPERIMENTAL", "원본의 기존 final-solid 선택"),
            "analysis_run": ("선형 구조 해석", "fixture.calculix", "EXPERIMENTAL", "검증된 CAD parent, 가정된 재료·하중; NOT_RELEASED"),
            "pde_run": ("약형 PDE 실험", "pde.fenicsx", "EXPERIMENTAL", "제한된 scalar weak form와 해석해 비교; 물리 검증 UNKNOWN"),
            "model_analysis_run": ("선언 모델 구조 해석", "structural.code_aster", "EXPERIMENTAL", "독립적인 선형 block benchmark; 비선형·접촉 미구현"),
            "doe_plan": ("DOE 계획", "scipy.latin_hypercube", "IMPLEMENTED", "수치 엔진이 후보를 생성"),
            "doe_run": ("DOE 실행", "scipy.latin_hypercube", "IMPLEMENTED", "기존 Core의 개별 실험과 증거 재사용"),
            "optimization_plan": ("최적화 계획", "scipy.differential_evolution", "IMPLEMENTED", "수치 엔진의 목적 함수·제약·seed"),
            "optimization_run": ("수치 최적화 실행", "scipy.differential_evolution", "IMPLEMENTED", "SciPy 후보와 기존 validation 판정; 자동 release 아님"),
        }
        lab = self._selected().lab
        rows = [{"operation": operation, "label": label, "backend": backend,
                 "status": status, "scope": scope,
                 "callable": callable(getattr(lab, OPERATIONS[operation], None))}
                for operation, (label, backend, status, scope) in descriptions.items()]
        for operation, label, backend, scope in (
            ("nonlinear_contact", "비선형·접촉", "Code_Aster / CalculiX", "다음 독립 reference benchmark 필요"),
            ("explicit_dynamics", "충격·낙하 동해석", "OpenRadioss", "Starter/Engine adapter와 접촉·에너지 benchmark 미구현"),
            ("material_point", "재료 모델·접선 검증", "MFront / MTest", "라이브러리 설치와 별개로 material-point adapter 및 독립 benchmark 필요"),
            ("physical_validation", "실물·내구 시험", None, "측정·시험 근거가 필요하며 UNKNOWN 유지"),
            ("uncertainty_inverse", "역문제·불확실성", None, "추가 numerical engine 및 관측 자료 연결 필요"),
            ("hpc", "원격·병렬 계산", "MPI / SSH / Slurm / PBS", "실제 환경과 작업·증거 추적 검증 필요"),
            ("field_postprocessing", "해석 필드·애니메이션 화면", None, "원본 field 파일은 보존; 통합 field viewer는 미구현"),
            ("native_upload", "기존 CAD 업로드", "FreeCAD", "경로 입력 대신 제한된 업로드 API가 필요"),
        ):
            rows.append({"operation": operation, "label": label, "backend": backend,
                         "status": "PLANNED", "scope": scope, "callable": False})
        return rows

    def overview(self) -> dict:
        with self._lock:
            selected = self._selected()
            jobs = deepcopy(list(self._jobs.values()))
            active = self._active_store
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
        return {"token": self.token, "active_store": active,
                "stores": [{"id": item.id, "label": item.id, "writable": item.writable}
                           for item in self._stores.values()],
                "studies": studies, "experiments": experiments, "campaigns": campaigns,
                "capabilities": self.capabilities(), "jobs": jobs}

    def _folders(self, store: Store, namespace: str) -> list[Path]:
        root = contained(store.path, namespace)
        return sorted((p for p in root.iterdir() if p.is_dir()), key=lambda p: p.name) if root.exists() else []

    @staticmethod
    def _error(exc: Exception) -> str:
        return f"{type(exc).__name__}: {exc}"

    def study(self, identifier: str) -> dict:
        selected = self._selected()
        contained(selected.path, f"studies/{check_id(identifier)}/study.json")
        contained(selected.path, f"studies/{identifier}/parameters.json")
        return {"study": selected.lab.inspect_study(identifier), "registry": selected.lab.registry(identifier)}

    def experiment(self, identifier: str) -> dict:
        from .reporting import verified_record
        return verified_record(self._selected().lab, check_id(identifier))

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
        method = selected.lab.inspect_doe if kind == "doe" else selected.lab.inspect_optimization
        record = method(identifier)
        recheck_records(selected.lab, records)
        return {"type": kind, "record": record}

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
        from scripts.verify_codeaster import specification as codeaster_specification
        material_path = (Path(__file__).resolve().parents[2] /
                         "plugins/fixture_design/upstream/examples/printed_material_ASSUMED.json")
        # Exact existing acceptance inputs; material remains explicitly assumed.
        return {
            "structural_linear": {"backend": "fixture.calculix", "label": "가정된 재료·하중의 선형 구조 screen",
                "status": "EXPERIMENTAL", "scope": "100 N/support 및 미측정 orthotropic 재료; peak stress와 강도·물리 검증 UNKNOWN, NOT_RELEASED",
                "settings": {"load": {"force_per_support_N": 100.0,
                    "source": "Illustrative 100 N screen per support; unqualified, not measured"},
                    "material": load_json(material_path), "mesh": {"max_sizes_mm": [4.0, 3.0, 2.0]}}},
            "pde_canonical": {"backend": "pde.fenicsx", "label": "Canonical Poisson 약형 benchmark",
                "status": "EXPERIMENTAL", "scope": "dimensionless unit square의 해석해·오차·수렴 검증; 물리 검증 UNKNOWN",
                "settings": pde_specification()},
            "codeaster_linear": {"backend": "structural.code_aster", "label": "독립적인 선형 elasticity benchmark",
                "status": "EXPERIMENTAL", "scope": "가정된 solid block의 affine analytical reference; 비선형·접촉 및 물리·강도 검증 UNKNOWN",
                "settings": codeaster_specification()},
        }

    def submit(self, operation: str, arguments: dict) -> dict:
        with self._lock:
            if not isinstance(operation, str) or operation not in OPERATIONS:
                raise ServiceError(400, "Operation is not in the Lab allowlist")
            if not isinstance(arguments, dict):
                raise ServiceError(400, "Operation arguments must be a JSON object")
            if self._active_job is not None:
                raise ServiceError(409, "A job is already running")
            selected = self._selected()
            if not selected.writable and operation not in READ_OPERATIONS:
                raise ServiceError(403, "Selected library is read only")
            method = getattr(selected.lab, OPERATIONS[operation])
            try:
                inspect.signature(method).bind(**arguments)
                self._argument_paths(selected, operation, arguments)
            except (TypeError, ValueError) as exc:
                raise ServiceError(400, str(exc)) from exc
            identifier = "J" + uuid.uuid4().hex
            job = {"id": identifier, "operation": operation, "status": "RUNNING",
                   "created_utc": utc_now(), "store_id": selected.id}
            self._jobs[identifier] = job
            self._active_job = identifier
            snapshot = deepcopy(job)
            threading.Thread(target=self._execute, args=(selected, identifier, method, deepcopy(arguments)),
                             name=f"caelab-{identifier}", daemon=True).start()
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
        for key in ("study_id", "experiment_id", "parent_experiment_id", "campaign_id", "parameter_id", "hypothesis_id"):
            if arguments.get(key) is not None:
                check_id(arguments[key])
        for namespace in ("studies", "experiments", "ledger", "campaigns", "optimizations", "native_designs"):
            contained(selected.path, namespace)
        for key, namespace in (("study_id", "studies"), ("experiment_id", "experiments"),
                               ("parent_experiment_id", "experiments")):
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
        try:
            operation = self._jobs[identifier]["operation"]
            if operation == "analysis_run":
                from .reporting import verified_record
                verified_record(selected.lab, arguments["parent_experiment_id"])
            elif operation in {"doe_run", "optimization_run"}:
                self._campaign_preflight(selected, arguments["campaign_id"])
            result = method(**arguments)
            update = {"status": "COMPLETED", "result": result}
        except Exception as exc:
            update = {"status": "FAILED", "error": self._error(exc)}
        finally:
            with self._lock:
                self._jobs[identifier].update(**update, completed_utc=utc_now())
                self._active_job = None

    def job(self, identifier: str) -> dict:
        with self._lock:
            if identifier not in self._jobs:
                raise ServiceError(404, "Job not found")
            return deepcopy(self._jobs[identifier])
