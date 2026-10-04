"""Original pinned bending assembly behind the existing CADAdapter boundary.

This adapter offers four specimen geometry leaves only. Upstream owns all
dimensions, relations, hand checks and geometry. A static STEP is not a
parametric native document: its separately retained recipe rebuilds the input.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any

from ..contracts import Candidate, Outcome
from ..execution_control import check_cancelled, wait_for_process, stop_owned_process


BACKEND = "fixture.assembly"
MODEL = "bending_assembly"
RECORDED_UPSTREAM_PIN = "3e48bf6138f495299f45b1af254bfb4aaff307b8"
PARAMETERS = {
    "specimen.length": ("Specimen length", "mm"),
    "specimen.width": ("Specimen width", "mm"),
    "specimen.thickness": ("Specimen thickness", "mm"),
    "specimen.span_ratio": ("Support span / specimen thickness", "1"),
}
PENDING = ["printed_material_allowables", "print_anisotropy_process", "contact_friction_bearing",
    "fastener_grade_joint_preload", "roller_retention", "machine_interface", "static_strength",
    "physical_load_test", "fatigue_durability", "corporate_license_security"]


def _root() -> Path:
    for folder in Path(__file__).resolve().parents:
        if (folder / "PROJECT_SCOPE.md").is_file() and (folder / "plugins/fixture_design/upstream").is_dir():
            return folder
    raise RuntimeError("Trusted fixture repository root is unavailable")


ROOT = _root()
UPSTREAM = ROOT / "plugins/fixture_design/upstream"
BASELINE = UPSTREAM / "examples/bend_4mm.json"
WORKER = Path(__file__).with_name("fixture_assembly_worker.py")
DOMAIN = Path(__file__).resolve().parents[2] / "plugins/fixture_design/assembly_interfaces.py"


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_files() -> dict[str, Path]:
    files = {"adapter/fixture_assembly.py": Path(__file__).resolve(),
        "adapter/fixture_assembly_worker.py": WORKER,
        "domain/assembly_interfaces.py": DOMAIN,
        "platform/contracts.py": ROOT / "caelab/contracts.py",
        "platform/execution_control.py": ROOT / "caelab/execution_control.py",
        "upstream/examples/bend_4mm.json": BASELINE,
        "upstream/legacy/src/fixture.py": UPSTREAM / "legacy/src/fixture.py"}
    for file in sorted((UPSTREAM / "fixturelab").glob("*.py")):
        files["upstream/" + file.relative_to(UPSTREAM).as_posix()] = file
    return files


def fingerprint() -> dict[str, Any]:
    hashes = {}
    for name, file in source_files().items():
        if not file.is_file() or file.is_symlink():
            raise ValueError("Missing or symlinked trusted assembly source: " + name)
        hashes[name] = {"sha256": sha256(file), "size_bytes": file.stat().st_size}
    definition = {"backend": BACKEND, "model": MODEL, "version": "1", "paths": PARAMETERS,
        "intrinsic_bounds": "No independent usable bounds claimed; original positive/resource/coupled relation checks remain authoritative",
        "files": hashes}
    digest = hashlib.sha256(canonical(definition)).hexdigest()
    return {"commit": "UNKNOWN", "git_dirty": None, "recorded_upstream_pin": RECORDED_UPSTREAM_PIN,
        "git_observation": "NOT_QUERIED; actual source bytes are frozen independently", "files": hashes,
        "files_sha256": hashlib.sha256(canonical(hashes)).hexdigest(), "source_sha256": digest}


def assert_sources(expected: dict) -> None:
    if fingerprint() != expected:
        raise ValueError("Assembly source changed; preserved outputs must not be admitted")


def assembly_declarations(file: Path = DOMAIN) -> dict:
    spec = importlib.util.spec_from_file_location("_fixture_assembly_declarations", file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    roles, interfaces = module.component_roles(), module.intended_interfaces()
    if len(roles) != 15 or len(interfaces) != 15 or len({p["id"] for p in interfaces}) != 15:
        raise ValueError("Incomplete Domain assembly role/interface declaration")
    if any(p["a"] not in roles or p["b"] not in roles for p in interfaces):
        raise ValueError("Domain interface component is absent")
    return {"component_roles": roles, "interfaces": interfaces}


def full_input(native_values: dict[str, float]) -> dict:
    if not isinstance(native_values, dict) or not set(native_values) <= set(PARAMETERS):
        raise ValueError("Only the four discovered specimen geometry paths are supported")
    for name, value in native_values.items():
        if type(value) not in (int, float) or not math.isfinite(value):
            raise ValueError(name + ": finite numeric geometry value required; bool is not numeric")
    data = json.loads(BASELINE.read_text(encoding="utf-8"))
    for name, value in native_values.items():
        data["specimen"][name.split(".")[1]] = value
    return data


def _fresh(output: Path) -> None:
    if output.is_symlink() or (output.exists() and (not output.is_dir() or any(output.iterdir()))):
        raise ValueError("Fresh empty output directory required; old CAD remains preserved")
    output.mkdir(parents=True, exist_ok=True)


def _save(path: Path, value: dict) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as file:
        json.dump(value, file, ensure_ascii=True, indent=2, sort_keys=True, allow_nan=False)
        file.write("\n")


def _safe_path(root: Path, name: str) -> Path:
    if not isinstance(name, str) or "\\" in name or ":" in name or any(c in name for c in "\0\r\n"):
        raise ValueError("Unsafe retained assembly artifact path")
    parts = name.split("/")
    if not all(parts) or any(p in (".", "..") for p in parts):
        raise ValueError("Unsafe retained assembly artifact path")
    file = root.joinpath(*parts)
    if file.is_symlink() or not file.is_file() or not file.resolve().is_relative_to(root.resolve()):
        raise ValueError("Retained assembly artifact is missing or outside its root")
    return file


def revision_material(result: dict) -> dict:
    return {"source_sha256": result["source_sha256"], "input_sha256": result["input_sha256"],
        "catalog_sha256": result["catalog_sha256"], "surface_sha256": result["surface_sha256"], "recipe_sha256": result["recipe_sha256"],
        "native_files": result["native_files"]}


def validate_catalog(catalog: dict, surface: dict) -> None:
    """Check artifact joins only; native geometric observations belong to the worker."""
    def finite(values, length):
        return isinstance(values, list) and len(values) == length and all(type(x) in (int, float) and math.isfinite(x) for x in values)
    declarations = assembly_declarations()
    roles = declarations["component_roles"]
    components = catalog.get("components")
    if not isinstance(components, list) or len(components) != 15 or catalog.get("component_count") != 15:
        raise ValueError("Incomplete assembly catalog components")
    if len({c["id"] for c in components}) != 15 or {c["id"]: c["role"] for c in components} != roles:
        raise ValueError("Assembly catalog named component/role join differs")
    all_faces = {}
    for component in components:
        name = component["id"]
        if component.get("xde_product_name") != name or component.get("frame") != "global_assembly_cartesian_mm":
            raise ValueError("Native component name/frame differs")
        for key in ("area_mm2", "volume_mm3"):
            value = component[key]
            if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
                raise ValueError("Invalid native component geometric observation")
        if not finite(component["center_of_mass_mm"], 3) or component["solid_count"] != 1 or component["valid"] is not True:
            raise ValueError("Invalid native component identity")
        paths = [(component["native_brep_path"], component["native_geometry_sha256"]),
                 (component["global_step_path"], None)]
        if not component["faces"]:
            raise ValueError("Missing actual component faces")
        for face in component["faces"]:
            if face["component_id"] != name or face["id"] in all_faces or not finite(face["center_of_mass_mm"], 3):
                raise ValueError("Missing, duplicate or foreign catalog face identity")
            all_faces[face["id"]] = name
            paths.append((face["native_brep_path"], face["native_geometry_sha256"]))
        for path, digest in paths:
            if path not in catalog["native_files"] or (digest is not None and digest != catalog["native_files"][path]["sha256"]):
                raise ValueError("Catalog native geometry hash/path differs")
    if catalog.get("face_count") != len(all_faces):
        raise ValueError("Catalog full face coverage differs")
    interfaces = catalog.get("interfaces")
    wanted = {p["id"]: p for p in declarations["interfaces"]}
    if not isinstance(interfaces, list) or len(interfaces) != len(wanted) or {p["id"] for p in interfaces} != set(wanted):
        raise ValueError("Domain interface declarations/catalog coverage differs")
    for interface in interfaces:
        for side in ("a", "b"):
            mapping = interface[side]
            if mapping["component_id"] != wanted[interface["id"]][side] or not mapping["face_ids"] or any(all_faces.get(face) != mapping["component_id"] for face in mapping["face_ids"]):
                raise ValueError("Interface component/actual face join differs")
    if not isinstance(surface.get("bounds"), list) or len(surface["bounds"]) != 2 or not all(finite(row, 3) for row in surface["bounds"]):
        raise ValueError("Invalid assembled display bounds")
    if surface["bounds"] != [catalog["bounds"]["min_mm"], catalog["bounds"]["max_mm"]] or surface.get("display_only") is not True or surface.get("units") != "mm":
        raise ValueError("Display frame/native geometry bounds differ")
    faces = surface.get("faces")
    if not isinstance(faces, list) or len(faces) != len(all_faces):
        raise ValueError("Display/native face coverage differs")
    ids, catalog_ids = set(), set()
    for face in faces:
        identity = face["id"]
        if type(identity) is not int or not 1 <= identity <= 0xffffff or identity in ids:
            raise ValueError("Display ID must be a unique positive 24-bit integer")
        ids.add(identity)
        if face["catalog_face_id"] in catalog_ids or all_faces.get(face["catalog_face_id"]) != face["component_id"]:
            raise ValueError("Display face/native catalog join differs")
        catalog_ids.add(face["catalog_face_id"])
        if not face["triangles"] or not all(finite(triangle, 9) for triangle in face["triangles"]):
            raise ValueError("Malformed actual display triangles")


def verify_result(output: Path, result: dict, expected: dict) -> None:
    assert_sources(expected)
    if result.get("source_sha256") != expected["source_sha256"] or result.get("source_fingerprint_before") != expected:
        raise ValueError("Returned assembly source identity differs")
    if not result.get("cad_generated"):
        if result.get("native_revision") is not None:
            raise ValueError("Unadmitted CAD may not carry an admitted native revision")
        return
    if result.get("source_fingerprint_after") != expected or result.get("decision") != "REVIEW_REQUIRED":
        raise ValueError("Assembly completion/source gate differs")
    refs = {"input.json": result["input_sha256"], "assembly_catalog.json": result["catalog_sha256"],
        "surface.json": result["surface_sha256"], "rebuild_recipe.json": result["recipe_sha256"]}
    for name, digest in refs.items():
        if sha256(_safe_path(output, name)) != digest:
            raise ValueError("Retained assembly input/catalog/recipe drift: " + name)
    catalog = json.loads((output / "assembly_catalog.json").read_text(encoding="utf-8"))
    if catalog["input_sha256"] != result["input_sha256"] or catalog["source_sha256"] != result["source_sha256"]:
        raise ValueError("Assembly catalog/input/source identity differs")
    if catalog["native_files"] != result["native_files"]:
        raise ValueError("Assembly catalog/native file identities differ")
    surface = json.loads((output / "surface.json").read_text(encoding="utf-8"))
    if surface["input_sha256"] != result["input_sha256"] or surface["source_sha256"] != result["source_sha256"] or surface["assembly_step_sha256"] != result["native_files"]["assembly.step"]["sha256"]:
        raise ValueError("Assembly display surface/source/native identity differs")
    if catalog["assembly_step_sha256"] != result["native_files"]["assembly.step"]["sha256"]:
        raise ValueError("Catalog assembly STEP identity differs")
    request = json.loads(_safe_path(output, "request.json").read_text(encoding="utf-8"))
    data = json.loads(_safe_path(output, "input.json").read_text(encoding="utf-8"))
    recipe = json.loads(_safe_path(output, "rebuild_recipe.json").read_text(encoding="utf-8"))
    if data != full_input(request["native_values"]) or recipe["captured_input"] != data or recipe["native_values"] != request["native_values"] or recipe["input_sha256"] != result["input_sha256"] or recipe["source_sha256"] != expected["source_sha256"]:
        raise ValueError("Captured input/request/editable recipe differs")
    validate_catalog(catalog, surface)
    for name, entry in expected["files"].items():
        if sha256(_safe_path(output, "captured_source/" + name)) != entry["sha256"]:
            raise ValueError("Captured source bytes differ")
    for name, entry in result["native_files"].items():
        file = _safe_path(output, name)
        if sha256(file) != entry["sha256"] or file.stat().st_size != entry["size_bytes"]:
            raise ValueError("Retained native assembly file drift: " + name)
    if hashlib.sha256(canonical(revision_material(result))).hexdigest() != result["native_revision"]:
        raise ValueError("Assembly native revision does not bind actual inputs/catalog/files")


class FixtureAssemblyAdapter:
    backend = BACKEND
    version = "1"
    domain = "fixture_design"
    physics_domain = "structural"
    analysis_type = "cad_preflight"
    default_metrics = ["cad_bounds", "cad_volume", "cad_component_count"]

    def __init__(self):
        self.last_worker_evidence: str | None = None

    def document_id(self, model: str) -> str:
        if model != MODEL:
            raise ValueError("Only bending_assembly is supported")
        return "examples/bend_4mm.json"

    def discover(self, model: str) -> list[Candidate]:
        self.document_id(model)
        source = fingerprint()
        data = full_input({})
        return [Candidate(native={"backend": BACKEND, "document": self.document_id(model), "object": MODEL, "path": name},
            label=label, unit=unit, value=data["specimen"][name.split(".")[1]], lower=None, upper=None,
            source_sha256=source["source_sha256"]) for name, (label, unit) in PARAMETERS.items()]

    def _call(self, action: str, model: str, values: dict, output: Path | None = None, **extra) -> dict:
        self.document_id(model)
        source = fingerprint()
        # Validate trusted path/type shape before JSON transport; relation gates remain upstream.
        full_input(values)
        if output is None:
            output = Path(tempfile.mkdtemp(prefix="caelab-assembly-"))
        else:
            output = Path(output)
        _fresh(output)
        request = {"action": action, "model": model, "native_values": deepcopy(values), "source_fingerprint": source, **extra}
        _save(output / "request.json", request)
        self.last_worker_evidence = str(output)
        check_cancelled()
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONUTF8="1")
        command = [sys.executable, "-X", "utf8", "-B", str(WORKER), str(output / "request.json")]
        with (output / "worker.stdout.txt").open("x", encoding="utf-8") as stdout, (output / "worker.stderr.txt").open("x", encoding="utf-8") as stderr:
            process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=stdout, stderr=stderr, start_new_session=os.name == "posix")
            try:
                code = wait_for_process(process, timeout=None)
            except BaseException:
                stop_owned_process(process, isolated_group=os.name == "posix")
                _save(output / "process.json", {"command": command, "exit_code": process.poll(),
                    "wall_timeout_seconds": None, "fresh_worker": True, "interrupted": True,
                    "owned_process_reaped": process.poll() is not None, "git_queries": 0,
                    "solver_calls": 0, "provider_calls": 0})
                raise
        _save(output / "process.json", {"command": command, "exit_code": code, "wall_timeout_seconds": None,
            "fresh_worker": True, "git_queries": 0, "solver_calls": 0, "provider_calls": 0})
        if code != 0:
            raise RuntimeError(f"Assembly worker exited with code {code}; no result admitted; evidence retained at {output}")
        result_path = output / "result.json"
        if not result_path.is_file():
            raise ValueError("Assembly worker returned no retained result; see " + str(output))
        result = json.loads(result_path.read_text(encoding="utf-8"))
        assert_sources(source)
        if action == "regenerate":
            verify_result(output, result, source)
        elif result.get("source_sha256") != source["source_sha256"] or result.get("source_fingerprint_after") != source:
            raise ValueError("Assembly probe source identity changed")
        return result

    def probe_effect(self, model: str, candidate: Candidate, lower: float, upper: float) -> dict[str, Any]:
        candidates = {c.native["path"]: c for c in self.discover(model)}
        if candidate.native.get("path") not in candidates or candidate != candidates[candidate.native["path"]]:
            raise ValueError("Exact current assembly candidate required")
        if type(lower) not in (int, float) or type(upper) not in (int, float) or not all(math.isfinite(v) for v in (lower, upper)) or not lower < upper:
            raise ValueError("Finite increasing requested probe bounds required")
        return self._call("probe", model, {}, target=candidate.native["path"], bounds=[lower, upper])["effect"]

    def preflight_effects(self, model: str, native_values: dict[str, float]) -> list[dict[str, Any]]:
        self.document_id(model)
        actual, defaults = full_input(native_values), full_input({})
        if not native_values or all(actual["specimen"][name.split(".")[1]] == defaults["specimen"][name.split(".")[1]] for name in native_values):
            return []
        return self._call("effects", model, native_values)["checks"]

    def regenerate(self, model: str, native_values: dict[str, float], output: Path) -> Outcome:
        result = self._call("regenerate", model, native_values, output)
        return Outcome(decision=result["decision"], checks=[*result["checks"], *result.get("cad_checks", [])],
            generated=result["cad_generated"], metrics=result.get("cad_metrics", {}), pending_validations=list(PENDING),
            native_revision=result.get("native_revision"), source_sha256=result["source_sha256"], raw_result="cad/result.json")

    source_commit = staticmethod(lambda: "UNKNOWN")
    source_fingerprint = staticmethod(fingerprint)
