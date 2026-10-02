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


OPERATIONS = {
    "study_create": "create_study", "parameter_discover": "discover_parameters",
    "parameter_register": "register_parameter", "registry_refresh": "refresh_registry",
    "cad_run": "run_experiment", "native_create": "create_native_model",
    "native_inspect": "inspect_native_model", "native_final": "select_native_final",
    "analysis_run": "run_analysis", "pde_run": "run_pde",
    "model_analysis_run": "run_model_analysis", "doe_plan": "plan_doe",
    "doe_run": "run_doe", "optimization_plan": "plan_optimization",
    "optimization_run": "run_optimization",
    "model_parameters_discover": "discover_model_parameters",
    "model_parameters_register": "register_model_parameter",
    "model_optimization_plan": "plan_model_optimization",
}
READ_OPERATIONS = frozenset({"parameter_discover", "native_inspect", "model_parameters_discover"})
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
        self._job_tokens: dict[str, CancellationToken] = {}
        self._job_threads: dict[str, threading.Thread] = {}
        self._accepting_jobs = True

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
            "pde_run": ("약형 PDE 실험", ", ".join(sorted(self._selected().lab.pde_adapters)), "EXPERIMENTAL", "제한된 선형·비선형 scalar weak form와 해석해 비교; 물리 검증 UNKNOWN"),
            "model_analysis_run": ("모델·재료·동해석 실행", "CalculiX / Code_Aster / MFront / OpenRadioss", "EXPERIMENTAL", "보·압력용기·곡면 지붕의 제한된 선형 모델과 기존 재료·동해석; 실행 기록별 검증 확인, 물리·강도 UNKNOWN"),
            "doe_plan": ("DOE 계획", "scipy.latin_hypercube", "IMPLEMENTED", "수치 엔진이 후보를 생성"),
            "doe_run": ("DOE 실행", "scipy.latin_hypercube", "IMPLEMENTED", "기존 Core의 개별 실험과 증거 재사용"),
            "optimization_plan": ("최적화 계획", "scipy.differential_evolution", "IMPLEMENTED", "수치 엔진의 목적 함수·제약·seed"),
            "optimization_run": ("수치 최적화 실행", "scipy.differential_evolution", "IMPLEMENTED", "SciPy 후보와 기존 validation 판정; 자동 release 아님"),
            "model_parameters_discover": ("해석 모델 변수 찾기", None, "IMPLEMENTED", "adapter가 선언한 수치 입력과 단위·범위"),
            "model_parameters_register": ("해석 모델 변수 등록", None, "IMPLEMENTED", "선택한 입력만 변경하고 나머지 모델 선언 보존"),
            "model_optimization_plan": ("해석 모델 최적화 계획", "scipy.differential_evolution", "IMPLEMENTED", "공통 수치 엔진과 model 기준 목적 함수·제약·재개 기록"),
        }
        lab = self._selected().lab
        rows = [{"operation": operation, "label": label, "backend": backend,
                 "status": status, "scope": scope,
                 "callable": callable(getattr(lab, OPERATIONS[operation], None))}
                for operation, (label, backend, status, scope) in descriptions.items()]
        for operation, label, backend, scope in (
            ("nonlinear_contact", "비선형·접촉", "Code_Aster / CalculiX", "다음 독립 reference benchmark 필요"),
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
        from plugins.pde_nonlinear.reference import manufactured_settings as nonlinear_pde_specification
        from plugins.pde_elliptic.reference import manufactured_settings as rectangle_pde_specification
        from plugins.pde_transient.reference import manufactured_settings as transient_pde_specification
        from plugins.pde_vector.reference import manufactured_settings as vector_pde_specification
        from plugins.pde_coupled.reference import manufactured_settings as coupled_pde_specification
        from scripts.verify_codeaster import specification as codeaster_specification
        from scripts.verify_plasticity import specification as plasticity_specification
        from scripts.verify_openradioss import specification as explicit_specification
        from scripts.verify_compliant_drop import specification as compliant_specification
        from plugins.material_point.reference import canonical_settings as material_specification
        from plugins.material_point.inverse_reference import canonical_settings as inverse_specification
        from plugins.structural_families.reference import specification as family_specification
        material_path = (Path(__file__).resolve().parents[2] /
                         "plugins/fixture_design/upstream/examples/printed_material_ASSUMED.json")
        # Exact existing acceptance inputs; material remains explicitly assumed.
        presets = {
            "structural_linear": {"operation": "analysis_run", "backend": "fixture.calculix", "label": "가정된 재료·하중의 선형 구조 screen",
                "status": "EXPERIMENTAL", "scope": "100 N/support 및 미측정 orthotropic 재료; peak stress와 강도·물리 검증 UNKNOWN, NOT_RELEASED",
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
            "codeaster_linear": {"operation": "model_analysis_run", "backend": "structural.code_aster", "label": "독립적인 선형 elasticity benchmark",
                "status": "EXPERIMENTAL", "scope": "가정된 solid block의 affine analytical reference; 비선형·접촉 및 물리·강도 검증 UNKNOWN",
                "settings": codeaster_specification()},
            "codeaster_plasticity": {"operation": "model_analysis_run", "backend": "structural.code_aster.plasticity", "label": "소성 재료의 하중·제하 benchmark",
                "status": "EXPERIMENTAL", "scope": "J2 small-strain 전체 이력·해석해 검증; 접촉·기하 비선형·재료 자격 UNKNOWN",
                "settings": plasticity_specification()},
            "material_point": {"operation": "model_analysis_run", "backend": "material.mfront", "label": "재료점의 응력·접선 benchmark",
                "status": "EXPERIMENTAL", "scope": "실제 MGIS·MTest 응력 및 유한차분 접선 검증; 솔버 결합·물리적 재료 자격 UNKNOWN",
                "settings": material_specification()},
            "material_inverse": {"operation": "model_analysis_run", "backend": "material.mfront.inverse", "label": "합성 기준값의 재료 역추정 평가",
                "status": "EXPERIMENTAL", "scope": "합성 응력 기준값과 실제 MGIS 응력을 비교하는 평가; 수치 탐색은 공통 engine, 측정 재료·역추정 자격 UNKNOWN",
                "settings": inverse_specification()},
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

    def submit(self, operation: str, arguments: dict) -> dict:
        with self._lock:
            if not self._accepting_jobs:
                raise ServiceError(503, "Lab service is shutting down; new jobs are closed")
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
                   "created_utc": utc_now(), "store_id": selected.id,
                   "cancel_requested": False, "cancel_observed": False,
                   "cleanup_pending": False, "cleanup_owners": []}
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
        token = self._job_tokens[identifier]
        try:
            with cancellation_scope(token):
                check_cancelled()
                operation = self._jobs[identifier]["operation"]
                if operation == "analysis_run":
                    from .reporting import verified_record
                    verified_record(selected.lab, arguments["parent_experiment_id"])
                elif operation in {"doe_run", "optimization_run"}:
                    self._campaign_preflight(selected, arguments["campaign_id"])
                check_cancelled()
                result = method(**arguments)
            # A request after the operation's last checkpoint is not an observed
            # interruption. Preserve that completed/failed Core result verbatim.
            update = {"status": "CANCELLED" if token.observed else "COMPLETED", "result": result}
        except BaseException as exc:
            update = {"status": "CANCELLED" if token.observed else "FAILED", "error": self._error(exc)}
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
                else:
                    job["completed_utc"] = utc_now()
                    self._active_job = None

    def job(self, identifier: str) -> dict:
        try:
            check_id(identifier)
        except (TypeError, ValueError) as exc:
            raise ServiceError(400, "A valid job ID string is required") from exc
        with self._lock:
            if identifier not in self._jobs:
                raise ServiceError(404, "Job not found")
            return deepcopy(self._jobs[identifier])

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
                token.request()
                if self._jobs[identifier]["status"] == "CLEANUP_PENDING":
                    error = self._retry_cleanup(token, timeout=1.0)
                    if error is not None:
                        self._jobs[identifier]["cleanup_error"] = error
                    self._resolve_cleanup(identifier)
                else:
                    self._jobs[identifier].update(status="CANCEL_REQUESTED", cancel_requested=True,
                                                 cancel_observed=token.observed)
            return deepcopy(self._jobs[identifier])

    def _resolve_cleanup(self, identifier: str):
        """Publish a deferred terminal snapshot only under the service lock."""
        job, token = self._jobs[identifier], self._job_tokens[identifier]
        job.update(cancel_requested=token.requested, cancel_observed=token.observed,
                   cleanup_pending=token.cleanup_pending, cleanup_owners=token.cleanup_owners)
        worker = self._job_threads[identifier]
        if job["status"] == "CLEANUP_PENDING" and not token.cleanup_pending and not worker.is_alive():
            job.update(status=job["deferred_terminal_status"], completed_utc=utc_now())
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
                token.request()
                job = self._jobs[self._active_job]
                job.update(cancel_requested=True, cancel_observed=token.observed)
                if job["status"] != "CLEANUP_PENDING":
                    job["status"] = "CANCEL_REQUESTED"
            workers = list(self._job_threads.values())
        # Workers publish their final snapshot under _lock, so never hold it
        # while joining. An uncooperative operation stays pending truthfully.
        for worker in workers:
            if worker is not threading.current_thread() and worker.is_alive():
                worker.join(max(0.0, deadline - time.monotonic()))
        with self._lock:
            cleanup_id = (self._active_job if self._active_job is not None and
                          self._jobs[self._active_job]["status"] == "CLEANUP_PENDING" else None)
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
            return {"accepting_jobs": False, "pending": pending,
                    "joined": (not any(worker.is_alive() for worker in workers) and
                               not any(token.cleanup_pending for token in self._job_tokens.values()))}
