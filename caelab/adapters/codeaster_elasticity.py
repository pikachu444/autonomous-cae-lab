"""Code_Aster 17.4 affine elasticity benchmark via a pinned vendor container.

The domain plugin owns the reference and numerical limits. This adapter owns
Gmsh/Code_Aster syntax, process isolation, mesh and native-table completeness.
It never imports the fixture mesher or assumes loaded/support nodes disjoint.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
from typing import Any

from plugins.elasticity import reference as _reference_domain
from plugins.elasticity.reference import (analytical_reference, assess, model_declaration,
                                         validate_settings)
from .codeaster_worker import coordinate_bijection, parse_field_tables
from ..storage import save_json


WORKER = Path(__file__).with_name("codeaster_worker.py")
_DOMAIN_SOURCE = Path(_reference_domain.__file__).resolve()
_DOMAIN_SOURCE_BYTES = _DOMAIN_SOURCE.read_bytes()
_DOMAIN_SOURCE_SHA256 = hashlib.sha256(_DOMAIN_SOURCE_BYTES).hexdigest()
_DOMAIN_VERSION = getattr(_reference_domain, "__version__", None)
OCI_MANIFEST_SHA256 = "d8d19ea91989eac0d38195bc5795c54c69f530f7196f53d67697ffa57c9106d5"
CONTAINER_SCRIPT = 'source /opt/activate.sh; exec run_aster "$1"'
PROCESS_TIMEOUT = 180
_PENDING = ["static_strength", "material_qualification", "physical_validation",
            "fatigue_durability", "model_qualification"]
_GROUPS = {"BODY": (3, 1001), "X0": (2, 1002), "XL": (2, 1003), "Y0": (2, 1004), "Z0": (2, 1005)}
_TET_EDGES = ((0, 1), (1, 2), (2, 0), (0, 3), (2, 3), (1, 3))
_TRI_EDGES = ((0, 1), (1, 2), (2, 0))
_MAX_NODES = 200000
_MAX_ELEMENTS = 500000
_MAX_AXIS_CELLS = 256
_GMSH_MEMORY_BYTES = 2 * 1024 ** 3
_GMSH_CPU_SECONDS = 120
_LIMITATIONS = [
    "Uniaxial affine constant-strain patch test; this is not a fixture strength or nonlinear benchmark.",
    "DX=0 on x=0, DY=0 on y=0, DZ=0 on z=0 preserve the exact Poisson contraction.",
    "Load/support face intersections are legitimate; reactions use one deduplicated support union.",
    "Only straight-edged quadratic tetrahedra and the declared rectangular block are supported.",
    "Pinned 17.4 GMSH importer matches all element tags; physical IDs must not collide with nonphysical tags of the same dimension.",
    "The pinned solver-only vendor image includes an MPI rank compatibility patch; it is not pristine upstream.",
    "No assembled linear residual is measured; raw native fields are compared against the analytical reference.",
]


class MeshRejected(ValueError):
    """A represented mesh fails the declared geometry/preflight gate."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _assert_domain_source(output: Path) -> None:
    """Reject source drift rather than mix one run with a changed domain rule."""
    if (not _DOMAIN_SOURCE.is_file() or _sha256(_DOMAIN_SOURCE) != _DOMAIN_SOURCE_SHA256 or
            _sha256(output / "domain_reference.py") != _DOMAIN_SOURCE_SHA256):
        raise RuntimeError("Elasticity domain source changed; captured source and old evidence are preserved")


def _mesh_workload(settings: dict) -> dict:
    """A conservative admission estimate, followed by exact actual-mesh caps.

    Four times the quadratic structured-grid nodes and twice its six-tet cell
    count provide a bounded policy estimate for the unstructured Gmsh mesher.
    This is a runtime policy, not a mesh accuracy or engineering threshold.
    """
    studies = []
    for size in settings["mesh_sizes_mm"]:
        ratios = [span / size for span in settings["dimensions_mm"]]
        if any(not math.isfinite(ratio) or ratio > _MAX_AXIS_CELLS for ratio in ratios):
            raise MeshRejected(f"Requested dimensions/mesh-size ratio exceeds the {_MAX_AXIS_CELLS}-cell axis budget")
        cells = [max(1, math.ceil(ratio)) for ratio in ratios]
        nodes = 4 * math.prod(2 * count + 1 for count in cells)
        elements = 12 * math.prod(cells)
        studies.append({"mesh_size_mm": size, "axis_cell_estimates": cells,
                        "estimated_nodes": nodes, "estimated_volume_elements": elements})
    return {"policy": "4x quadratic structured-grid nodes; 2x six-tetrahedra cells; actual mesh caps remain mandatory",
            "maximum_nodes": _MAX_NODES, "maximum_elements": _MAX_ELEMENTS,
            "maximum_axis_cells": _MAX_AXIS_CELLS, "studies": studies,
            "admitted": all(item["estimated_nodes"] <= _MAX_NODES and
                            item["estimated_volume_elements"] <= _MAX_ELEMENTS for item in studies)}


def _cleanup_scratch(output: Path, scratch: Path) -> None:
    """Remove only a fresh, checked level scratch after native evidence is saved."""
    root = output / "scratch"
    if (output.is_symlink() or root.is_symlink() or scratch.is_symlink() or
            root.resolve() != output.resolve() / "scratch" or
            scratch.resolve().parent != root.resolve() or
            not re.fullmatch(r"level_[0-2]", scratch.name)):
        raise RuntimeError("Refusing cleanup outside the verified experiment scratch directory")
    shutil.rmtree(scratch)


def _sub(a: list[float], b: list[float]) -> list[float]:
    return [x - y for x, y in zip(a, b)]


def _cross(a: list[float], b: list[float]) -> list[float]:
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0]]


def _dot(a: list[float], b: list[float]) -> float:
    return math.fsum(x * y for x, y in zip(a, b))


def _section(lines: list[str], name: str) -> list[str]:
    start, end = "$" + name, "$End" + name
    if lines.count(start) != 1 or lines.count(end) != 1:
        raise ValueError(f"Missing/duplicate Gmsh section: {name}")
    begin, finish = lines.index(start), lines.index(end)
    if finish <= begin:
        raise ValueError(f"Malformed Gmsh section: {name}")
    return lines[begin + 1:finish]


def parse_gmsh_mesh(path: Path, dimensions_mm: list[float]) -> dict:
    """Read actual MSH2.2 IDs, then prove affine TET10 Jacobians and groups.

    MSH IDs need not be dense or sorted. Mid-edge positions must be verified
    before interpreting a corner determinant as the quadratic-map Jacobian.
    """
    if not path.is_file() or path.stat().st_size > 128 * 1024 * 1024:
        raise ValueError("Gmsh mesh missing or exceeds the bounded 128 MiB parser limit")
    lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()]
    if _section(lines, "MeshFormat") != ["2.2 0 8"]:
        raise ValueError("Only ASCII Gmsh MSH 2.2 with 8-byte reals is supported")
    physical = _section(lines, "PhysicalNames")
    if not physical or int(physical[0]) != len(physical) - 1:
        raise ValueError("Incomplete Gmsh physical names")
    groups = {}
    for line in physical[1:]:
        match = re.fullmatch(r'(\d+)\s+(\d+)\s+"([A-Za-z0-9_]+)"', line)
        if not match or match[3] in groups:
            raise ValueError("Malformed/duplicate Gmsh physical group")
        groups[match[3]] = (int(match[1]), int(match[2]))
    if groups != _GROUPS:
        raise MeshRejected("Gmsh mesh requires the exact BODY/X0/XL/Y0/Z0 physical groups")
    node_section = _section(lines, "Nodes")
    if not node_section:
        raise ValueError("Empty Gmsh node section")
    count = int(node_section[0])
    if not 4 <= count <= _MAX_NODES or len(node_section) != count + 1:
        raise ValueError("Incomplete or unbounded Gmsh node table")
    nodes = {}
    coordinate_tolerance = 1e-10 * max(1.0, *dimensions_mm)
    for line in node_section[1:]:
        fields = line.split()
        if len(fields) != 4:
            raise ValueError("Malformed Gmsh node row")
        identifier = int(fields[0])
        coordinate = [float(value) for value in fields[1:]]
        if identifier <= 0 or identifier in nodes or not all(math.isfinite(value) for value in coordinate):
            raise ValueError("Duplicate/nonfinite Gmsh node")
        if any(value < -coordinate_tolerance or value > span + coordinate_tolerance
               for value, span in zip(coordinate, dimensions_mm)):
            raise MeshRejected("Gmsh node lies outside the declared block")
        nodes[identifier] = coordinate
    element_section = _section(lines, "Elements")
    if not element_section:
        raise ValueError("Empty Gmsh element section")
    count = int(element_section[0])
    if not 1 <= count <= _MAX_ELEMENTS or len(element_section) != count + 1:
        raise ValueError("Incomplete or unbounded Gmsh element table")
    seen, tets = set(), []
    surfaces = {name: [] for name in ("X0", "XL", "Y0", "Z0")}
    group_by_tag = {value[1]: name for name, value in groups.items()}
    for line in element_section[1:]:
        fields = [int(value) for value in line.split()]
        if len(fields) < 4:
            raise ValueError("Malformed Gmsh element row")
        identifier, kind, tag_count = fields[:3]
        if (identifier <= 0 or identifier in seen or tag_count < 2 or
                len(fields) < 3 + tag_count):
            raise ValueError("Duplicate/malformed Gmsh element metadata")
        seen.add(identifier)
        physical_tag = fields[3]
        connectivity = fields[3 + tag_count:]
        if len(set(connectivity)) != len(connectivity) or not set(connectivity) <= nodes.keys():
            raise ValueError("Gmsh element contains duplicate or missing node ids")
        group = group_by_tag.get(physical_tag)
        if group is not None:
            dimension = groups[group][0]
            physical_ids = {tag for dim, tag in groups.values() if dim == dimension}
            if physical_ids.intersection(fields[4:3 + tag_count]):
                raise MeshRejected("Gmsh nonphysical tags collide with physical IDs under the pinned Code_Aster 17.4 importer policy")
        if kind == 11 and group == "BODY" and len(connectivity) == 10:
            tets.append({"element_id": identifier, "node_ids": connectivity})
        elif kind == 9 and group in surfaces and len(connectivity) == 6:
            surfaces[group].append({"element_id": identifier, "node_ids": connectivity})
        else:
            raise MeshRejected("Gmsh mesh requires TET10 BODY and TRI6 boundary elements only")
    if not tets or any(not values for values in surfaces.values()):
        raise MeshRejected("Gmsh mesh has an empty volume or boundary group")
    used = {node for item in tets for node in item["node_ids"]}
    if used != nodes.keys():
        raise MeshRejected("Every Gmsh node must belong to the quadratic volume mesh")

    def midpoint_gate(connectivity: list[int], edges: tuple, offset: int) -> None:
        for middle, (a, b) in zip(connectivity[offset:], edges):
            expected = [(x + y) / 2 for x, y in zip(nodes[connectivity[a]], nodes[connectivity[b]])]
            if any(abs(x - y) > coordinate_tolerance for x, y in zip(nodes[middle], expected)):
                raise MeshRejected("Nonstraight quadratic midside nodes cannot use an affine Jacobian proof")

    determinants, volumes = [], []
    for item in tets:
        connectivity = item["node_ids"]
        midpoint_gate(connectivity, _TET_EDGES, 4)
        a, b, c, d = [nodes[node] for node in connectivity[:4]]
        determinant = _dot(_sub(b, a), _cross(_sub(c, a), _sub(d, a)))
        if not math.isfinite(determinant) or determinant <= 0:
            raise MeshRejected("Nonpositive quadratic tetrahedral Jacobian")
        determinants.append(determinant)
        volumes.append(determinant / 6)
    volume = math.fsum(volumes)
    expected_volume = math.prod(dimensions_mm)
    if not math.isfinite(expected_volume) or expected_volume <= 0:
        raise MeshRejected("Unrepresentable declared block volume")
    volume_error = abs(volume - expected_volume) / expected_volume
    if not math.isfinite(volume_error) or volume_error > 1e-10:
        raise MeshRejected(f"Gmsh volume mismatch: relative error {volume_error}")
    length, breadth, height = dimensions_mm
    planes = {"X0": (0, 0.0, breadth * height), "XL": (0, length, breadth * height),
              "Y0": (1, 0.0, length * height), "Z0": (2, 0.0, length * breadth)}
    group_nodes, areas, area_errors = {}, {}, {}
    for name, triangles in surfaces.items():
        axis, plane, expected_area = planes[name]
        node_ids = {node for item in triangles for node in item["node_ids"]}
        expected_nodes = {node for node, coords in nodes.items() if abs(coords[axis] - plane) <= coordinate_tolerance}
        if node_ids != expected_nodes:
            raise MeshRejected(f"Gmsh {name} group does not cover every node on its declared plane")
        face_areas, corner_sets = [], set()
        for triangle in triangles:
            connectivity = triangle["node_ids"]
            midpoint_gate(connectivity, _TRI_EDGES, 3)
            corner_key = tuple(sorted(connectivity[:3]))
            if corner_key in corner_sets:
                raise MeshRejected(f"Duplicate Gmsh boundary face: {name}")
            corner_sets.add(corner_key)
            a, b, c = [nodes[node] for node in connectivity[:3]]
            cross = _cross(_sub(b, a), _sub(c, a))
            area = math.sqrt(_dot(cross, cross)) / 2
            if not math.isfinite(area) or area <= 0:
                raise MeshRejected(f"Nonpositive Gmsh boundary area: {name}")
            face_areas.append(area)
        total = math.fsum(face_areas)
        error = abs(total - expected_area) / expected_area
        if not math.isfinite(error) or error > 1e-10:
            raise MeshRejected(f"Gmsh {name} area mismatch: relative error {error}")
        group_nodes[name], areas[name], area_errors[name] = sorted(node_ids), total, error
    return {"nodes": nodes, "tetrahedra": tets, "surfaces": surfaces, "group_node_ids": group_nodes,
            "node_count": len(nodes), "element_count": len(tets), "volume_mm3": volume,
            "volume_relative_error": volume_error, "minimum_jacobian_mm3": min(determinants),
            "boundary_areas_mm2": areas, "boundary_area_relative_errors": area_errors,
            "jacobian_method": "Verified straight TET10 midsides: constant affine-map determinant"}


def gmsh_source(settings: dict, mesh_size_mm: float) -> str:
    """Only validated numeric constants enter this adapter-owned CAD source."""
    length, breadth, height = settings["dimensions_mm"]
    epsilon = 1e-8 * max(1.0, length, breadth, height)
    return (
        'SetFactory("OpenCASCADE");\n'
        f"L={length:.17g}; B={breadth:.17g}; H={height:.17g}; h={mesh_size_mm:.17g}; eps={epsilon:.17g};\n"
        "Box(1)={0,0,0,L,B,H};\n"
        'Physical Volume("BODY",1001)={1};\n'
        'Physical Surface("X0",1002)=Surface In BoundingBox{-eps,-eps,-eps,eps,B+eps,H+eps};\n'
        'Physical Surface("XL",1003)=Surface In BoundingBox{L-eps,-eps,-eps,L+eps,B+eps,H+eps};\n'
        'Physical Surface("Y0",1004)=Surface In BoundingBox{-eps,-eps,-eps,L+eps,eps,H+eps};\n'
        'Physical Surface("Z0",1005)=Surface In BoundingBox{-eps,-eps,-eps,L+eps,B+eps,eps};\n'
        "Mesh.MeshSizeMin=h; Mesh.MeshSizeMax=h; Mesh.ElementOrder=2;\n"
        "Mesh.SecondOrderLinear=1; Mesh.MshFileVersion=2.2; Mesh.Binary=0; Mesh.SaveAll=0;\n")


def _expected_mesh(mesh: dict) -> dict:
    node_ids = sorted(mesh["nodes"])
    return {"schema_version": "1", "source_format": "GMSH2.2",
            "node_ids": node_ids, "coordinates_mm": [mesh["nodes"][node] for node in node_ids],
            "tetrahedra": mesh["tetrahedra"], "group_node_ids": mesh["group_node_ids"],
            "total_cell_count": len(mesh["tetrahedra"]) + sum(len(faces) for faces in mesh["surfaces"].values()),
            "physical_groups": {name: {"dimension": value[0], "tag": value[1]} for name, value in _GROUPS.items()},
            "importer_policy": "Pinned Code_Aster 17.4 gmlelt matches all tags; nonphysical tags disjoint from same-dimension physical IDs"}


def _text(value: str | bytes | None) -> str:
    return value.decode("utf-8", errors="replace") if isinstance(value, bytes) else value or ""


def _process(command: list[str], folder: Path, label: str, *, timeout: int = PROCESS_TIMEOUT) -> str:
    save_json(folder / f"{label}.command.json", {"argv": command, "timeout_seconds": timeout})
    try:
        process = subprocess.run(command, cwd=folder.resolve(), capture_output=True, text=True,
                                 timeout=timeout, check=False)
    except subprocess.TimeoutExpired as exc:
        (folder / f"{label}.stdout.log").write_text(_text(exc.stdout), encoding="utf-8")
        (folder / f"{label}.stderr.log").write_text(_text(exc.stderr) + "\nProcess timed out\n", encoding="utf-8")
        raise RuntimeError(f"{label} timed out; captured logs are retained") from exc
    except OSError as exc:
        (folder / f"{label}.stdout.log").write_text("", encoding="utf-8")
        (folder / f"{label}.stderr.log").write_text(f"{type(exc).__name__}: {exc}\n", encoding="utf-8")
        raise RuntimeError(f"Cannot start {label}; captured logs are retained") from exc
    (folder / f"{label}.stdout.log").write_text(_text(process.stdout), encoding="utf-8")
    (folder / f"{label}.stderr.log").write_text(_text(process.stderr), encoding="utf-8")
    if process.returncode != 0:
        raise RuntimeError(f"{label} failed (exit {process.returncode}); captured logs are retained: "
                           + _text(process.stderr).strip()[-1000:])
    return (_text(process.stdout) + "\n" + _text(process.stderr)).strip()


def _image_identity(output: Path) -> tuple[Path, str, str, str, str]:
    image_value = os.environ.get("CAELAB_CODEASTER_IMAGE", "")
    expected = os.environ.get("CAELAB_CODEASTER_IMAGE_SHA256", "")
    if not image_value or not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise RuntimeError("Configure CAELAB_CODEASTER_IMAGE and its exact CAELAB_CODEASTER_IMAGE_SHA256")
    image = Path(image_value).resolve()
    if not image.is_file() or _sha256(image) != expected:
        raise RuntimeError("Code_Aster vendor image is missing or its SIF hash drifted")
    runtime = shutil.which(os.environ.get("CAELAB_SINGULARITY_COMMAND", "singularity"))
    gmsh = shutil.which("gmsh")
    prlimit = shutil.which("prlimit")
    if not runtime or not gmsh or not prlimit:
        raise RuntimeError("Working Singularity, host Gmsh, and Linux prlimit executables are required")
    return image, expected, runtime, gmsh, prlimit


def _coordinates_equal(a: list[list[float]], b: list[list[float]]) -> bool:
    return coordinate_bijection(a, b) is not None


def _checked_worker(level: Path, mesh: dict, mesh_size: float, input_sha: str) -> tuple[dict, dict]:
    try:
        raw = json.loads((level / "worker_result.json").read_text(encoding="utf-8"))
        json.dumps(raw, allow_nan=False)
        if not isinstance(raw, dict):
            raise ValueError("Code_Aster worker result must be an object")
        versions = raw.get("versions", {})
        runtime = raw.get("code_aster_runtime", {})
        native_checks = raw.get("native_mesh_checks", {})
        if (not isinstance(versions, dict) or not isinstance(runtime, dict) or
                raw.get("input_sha256") != input_sha or versions.get("code_aster") != "17.4.0" or
                raw.get("mesh_input_sha256") != _sha256(level / "mesh.msh") or
                runtime.get("version") != versions["code_aster"] or
                any(not isinstance(versions.get(name), str) or not versions[name].strip()
                    for name in ("python", "numpy"))):
            raise ValueError("Code_Aster worker input/version identity is missing or drifted")
        if (not isinstance(native_checks, dict) or native_checks.get("status") != "PASS" or
                native_checks.get("support_union_verified") is not True or
                native_checks.get("expected_mesh_sha256") != _sha256(level / "expected_mesh.json") or
                native_checks.get("checked_msh_sha256") != _sha256(level / "mesh.msh") or
                native_checks.get("node_count") != mesh["node_count"] or
                native_checks.get("volume_element_count") != mesh["element_count"] or
                _sha256(level / "input.json") != input_sha):
            raise ValueError("Native mesh pre-MECA guard evidence is missing or drifted")
        if json.loads((level / "native_mesh_checks.json").read_text(encoding="utf-8")) != native_checks:
            raise ValueError("Native mesh pre-MECA guard artifact differs from raw evidence")
        record = parse_field_tables(raw, mesh_size)
        if (record["element_count"] != mesh["element_count"] or
                not _coordinates_equal(record["coordinates_mm"], list(mesh["nodes"].values()))):
            raise ValueError("Code_Aster mesh differs from the checked Gmsh volume mesh")
        lower = [min(point[axis] for point in mesh["nodes"].values()) for axis in range(3)]
        upper = [max(point[axis] for point in mesh["nodes"].values()) for axis in range(3)]
        coordinate_tolerance = 1e-12 * max(1., *upper)
        if any(any(position < low - coordinate_tolerance or position > high + coordinate_tolerance
                   for position, low, high in zip(point, lower, upper))
               for point in record["stress_point_coordinates_mm"]):
            raise ValueError("Code_Aster stress integration point lies outside the checked block")
        coordinates = dict(zip(record["node_ids"], record["coordinates_mm"]))
        for name, node_ids in record["group_node_ids"].items():
            if not _coordinates_equal([coordinates[node] for node in node_ids],
                                      [mesh["nodes"][node] for node in mesh["group_node_ids"][name]]):
                raise ValueError(f"Code_Aster boundary group differs from the checked mesh: {name}")
        if not (level / "results.med").is_file() or (level / "results.med").stat().st_size == 0:
            raise ValueError("Code_Aster MED field artifact is missing")
        return raw, record
    except (OSError, ValueError, TypeError, KeyError) as exc:
        raise RuntimeError(f"Incomplete/malformed Code_Aster fields at {level.name}: {exc}") from exc


class CodeAsterElasticityAdapter:
    backend = "structural.code_aster"
    domain = "elasticity"
    physics_domain = "structural"
    analysis_type = "linear_static"
    version = "1"
    default_metrics = ["axial_tip_displacement", "max_component_displacement_error", "displacement_relative_error",
                       "max_component_stress_error", "stress_relative_error", "reaction_x",
                       "reaction_absolute_error", "reaction_relative_error",
                       "mesh_axial_displacement_difference", "mesh_agreement_relative"]

    def describe_model(self, settings: dict) -> dict:
        declaration = model_declaration(settings)
        model = {field: declaration.pop(field) for field in ("geometry", "materials", "mesh")}
        return {"model": model, **declaration}

    def solve(self, output: Path, settings: dict) -> dict:
        output = Path(output)
        if output.is_symlink() or (output.exists() and (not output.is_dir() or any(output.iterdir()))):
            raise ValueError("Analysis output must be new or empty; old evidence cannot be overwritten")
        output.mkdir(parents=True, exist_ok=True)
        provenance = {"adapter": self.backend, "adapter_version": self.version,
                      "worker_sha256": _sha256(WORKER), "oci_manifest_sha256": OCI_MANIFEST_SHA256,
                      "distribution": "Solver-only vendor OCI, with MPI rank compatibility patch",
                      "domain_plugin": {"module": "plugins.elasticity.reference", "version": _DOMAIN_VERSION,
                                        "version_status": "UNKNOWN" if _DOMAIN_VERSION is None else "DECLARED",
                                        "source_version": _DOMAIN_SOURCE_SHA256,
                                        "source_sha256": _DOMAIN_SOURCE_SHA256,
                                        "source_artifact": "simulation/domain_reference.py"},
                      "assumptions": list(_LIMITATIONS)}
        (output / "domain_reference.py").write_bytes(_DOMAIN_SOURCE_BYTES)
        _assert_domain_source(output)
        checks = []

        def reject(code: str, observed: Any,
                   limit: Any = "Declared uniaxial block and checked positive quadratic volume mesh") -> dict:
            checks.append({"code": code, "status": "FAIL", "observed": observed,
                           "limit": limit})
            result = {"status": "REJECTED", "checks": checks, "metrics": {},
                      "solver_status": "NOT_RUN", "converged": None, "provenance": provenance,
                      "pending_validations": list(_PENDING), "raw_result": "simulation/analysis_raw.json",
                      "limitations": list(_LIMITATIONS)}
            save_json(output / "analysis_raw.json", result)
            return result

        try:
            settings = validate_settings(settings)
        except ValueError as exc:
            return reject("elasticity_preflight", str(exc))
        save_json(output / "input.json", settings)
        try:
            workload = _mesh_workload(settings)
        except MeshRejected as exc:
            return reject("mesh_workload_preflight", str(exc),
                          {"maximum_axis_cells": _MAX_AXIS_CELLS, "maximum_nodes": _MAX_NODES,
                           "maximum_elements": _MAX_ELEMENTS})
        save_json(output / "mesh_workload.json", workload)
        provenance["mesh_workload"] = workload
        if not workload["admitted"]:
            return reject("mesh_workload_preflight", workload,
                          {"maximum_nodes": _MAX_NODES, "maximum_elements": _MAX_ELEMENTS})
        checks.append({"code": "mesh_workload_preflight", "status": "PASS", "observed": workload,
                       "limit": {"maximum_nodes": _MAX_NODES, "maximum_elements": _MAX_ELEMENTS,
                                 "maximum_axis_cells": _MAX_AXIS_CELLS},
                       "evidence_artifact": "simulation/mesh_workload.json"})
        shutil.copyfile(WORKER, output / "codeaster_worker.py")
        save_json(output / "analytical_reference.json", analytical_reference(settings))
        save_json(output / "model_declaration.json", self.describe_model(settings))
        _assert_domain_source(output)
        try:
            image, image_sha, runtime, gmsh, prlimit = _image_identity(output)
        except RuntimeError as exc:
            (output / "runtime_preflight.stderr.log").write_text(str(exc) + "\n", encoding="utf-8")
            raise
        gmsh_version = _process([gmsh, "-version"], output, "gmsh_version", timeout=10)
        runtime_version = _process([runtime, "--version"], output, "container_version", timeout=10)
        if not gmsh_version or not runtime_version:
            raise RuntimeError("Gmsh/container runtime did not report actual versions")
        provenance.update({"image_sha256": image_sha, "image_path": str(image),
                           "versions": {"gmsh": gmsh_version, "singularity": runtime_version},
                           "input_sha256": _sha256(output / "input.json")})
        meshes = []
        # All requested meshes pass preflight before the first solver invocation.
        for index, size in enumerate(settings["mesh_sizes_mm"]):
            _assert_domain_source(output)
            level = output / f"level_{index}"
            level.mkdir(exist_ok=False)
            (level / "model.geo").write_text(gmsh_source(settings, size), encoding="utf-8")
            _process([prlimit, f"--as={_GMSH_MEMORY_BYTES}", f"--cpu={_GMSH_CPU_SECONDS}", "--",
                      gmsh, "model.geo", "-3", "-order", "2", "-format", "msh2", "-o", "mesh.msh",
                      "-nopopup", "-v", "3"], level, "gmsh")
            try:
                mesh = parse_gmsh_mesh(level / "mesh.msh", settings["dimensions_mm"])
            except MeshRejected as exc:
                return reject(f"mesh_preflight_{index}", str(exc))
            except (ValueError, OSError, OverflowError) as exc:
                raise RuntimeError(f"Malformed Gmsh output at {level.name}: {exc}") from exc
            summary = {key: value for key, value in mesh.items() if key not in ("nodes", "tetrahedra", "surfaces")}
            save_json(level / "mesh_checks.json", summary)
            checks.append({"code": f"mesh_preflight_{index}", "status": "PASS", "observed": summary,
                           "limit": {"minimum_jacobian": ">0", "volume_and_area_relative_error": 1e-10},
                           "evidence_artifact": f"simulation/{level.name}/mesh_checks.json"})
            meshes.append((level, size, mesh))
        records, native_results = [], []
        preferences = output / "preferences"
        preferences.mkdir(exist_ok=False)
        scratch_root = output / "scratch"
        scratch_root.mkdir(exist_ok=False)
        for level, size, mesh in meshes:
            _assert_domain_source(output)
            if _sha256(image) != image_sha:
                raise RuntimeError("Code_Aster image changed before execution; old evidence is preserved")
            save_json(level / "expected_mesh.json", _expected_mesh(mesh))
            save_json(level / "input.json", {"settings": settings, "mesh_size_mm": size,
                                            "mesh_sha256": _sha256(level / "mesh.msh"),
                                            "expected_mesh_sha256": _sha256(level / "expected_mesh.json")})
            input_sha = _sha256(level / "input.json")
            (level / "model.comm").write_text(
                "import sys\nsys.path.insert(0, '/work')\nfrom codeaster_worker import solve_level\n"
                f"solve_level('/work/{level.name}/input.json')\n", encoding="utf-8")
            export = (
                "P actions make_etude\nP memory_limit 1024\nP time_limit 120\nP mpi_nbcpu 1\nP ncpus 1\n"
                f"F comm /work/{level.name}/model.comm D 1\n"
                f"F mmed /work/{level.name}/mesh.msh D 20\n"
                f"F rmed /work/{level.name}/results.med R 80\n"
                f"F mess /work/{level.name}/aster.mess R 6\n"
                f"F resu /work/{level.name}/aster.resu R 8\n")
            (level / "model.export").write_text(export, encoding="utf-8")
            scratch = scratch_root / level.name
            scratch.mkdir(exist_ok=False)
            scratch_record = {"path": f"simulation/scratch/{level.name}", "container_mount": "/tmp",
                              "policy": "Fresh experiment-local disk scratch; remove only after native tables/MED are verified and saved; preserve on execution failure",
                              "retention_status": "PRESERVED_UNTIL_VALID_EXTRACTION"}
            save_json(level / "scratch.json", scratch_record)
            command = [runtime, "exec", "--cleanenv", "--containall", "--no-home", "--bind",
                       str(output.resolve()) + ":/work:rw", "--bind",
                       str(preferences.resolve()) + ":" + str(Path.home()) + ":rw", "--bind",
                       str(scratch.resolve()) + ":/tmp:rw", "--pwd", "/work", str(image),
                       "/bin/bash", "--noprofile", "--norc", "-c", CONTAINER_SCRIPT,
                       "caelab-codeaster", f"/work/{level.name}/model.export"]
            _process(command, level, "solver")
            raw, record = _checked_worker(level, mesh, size, input_sha)
            save_json(level / "parsed_fields.json", record)
            _assert_domain_source(output)
            if _sha256(image) != image_sha:
                raise RuntimeError("Code_Aster image changed during execution; old evidence is preserved")
            _cleanup_scratch(output, scratch)
            scratch_record["retention_status"] = "REMOVED_AFTER_VALID_EXTRACTION"
            save_json(level / "scratch.json", scratch_record)
            records.append(record)
            native_results.append(raw)
        _assert_domain_source(output)
        if _sha256(image) != image_sha:
            raise RuntimeError("Code_Aster image changed during execution; old evidence is preserved")
        versions = native_results[0]["versions"]
        if any(result["versions"] != versions or result["code_aster_runtime"] != native_results[0]["code_aster_runtime"]
               for result in native_results[1:]):
            raise RuntimeError("Code_Aster runtime identity drifted between mesh levels")
        assessment = assess(settings, records)
        _assert_domain_source(output)
        checks.extend({**check, "evidence_artifact": "simulation/analysis_raw.json"}
                      for check in assessment["checks"])
        completed = all(check["status"] == "PASS" for check in checks)
        provenance["versions"].update(versions)
        provenance.update({"code_aster_runtime": native_results[0]["code_aster_runtime"],
                           "numerical_libraries": native_results[0].get("numerical_libraries"),
                           "mesh": [f"simulation/{level.name}/mesh.msh" for level, _, _ in meshes],
                           "solver_deck": [f"simulation/{level.name}/model.comm" for level, _, _ in meshes],
                           "native_fields": [f"simulation/{level.name}/results.med" for level, _, _ in meshes],
                           "native_mesh_guard": [f"simulation/{level.name}/native_mesh_checks.json" for level, _, _ in meshes],
                           "native_import_policy": {"format": "GMSH2.2", "code_aster": "17.4.0",
                                                    "physical_ids": {name: value[1] for name, value in _GROUPS.items()},
                                                    "nonphysical_tags": "Disjoint from same-dimension physical IDs",
                                                    "gate": "Coordinate bijection, groups and corner/midside topology verified before MECA_STATIQUE"},
                           "mesh_response": assessment["mesh_response"], "stress_quadrature": "TETRA10 RIGI=FPG5",
                           "container_isolation": {"cleanenv": True, "containall": True, "no_home": True,
                                                   "home_content": "Fresh experiment-local preferences only",
                                                   "tmp_content": "Fresh per-level disk scratch bound explicitly at /tmp",
                                                   "scratch_retention": "Verified extraction scratch removed; execution-failure scratch retained",
                                                   "tmp_repair": "Explicit disk bind replaces containall private 64 MiB tmpfs observed during failed fresh-02 execution"},
                           "process_budgets": {"gmsh_address_space_bytes": _GMSH_MEMORY_BYTES,
                                               "gmsh_cpu_seconds": _GMSH_CPU_SECONDS,
                                               "solver_memory_mb": 1024, "solver_time_seconds": 120,
                                               "subprocess_timeout_seconds": PROCESS_TIMEOUT,
                                               "singularity_address_space_limit": None},
                           "solver": {"linear_method": "MUMPS", "measured_linear_residual": None,
                                      "residual_status": "UNKNOWN: assembled matrix/vector not exported"}})
        result = {"status": "COMPLETED" if completed else "REJECTED", "checks": checks,
                  "metrics": assessment["metrics"], "solver_status": "COMPLETED", "converged": True,
                  "pending_validations": assessment["pending_validations"], "provenance": provenance,
                  "raw_result": "simulation/analysis_raw.json", "reference": assessment["reference"],
                  "mesh_studies": assessment["mesh_studies"], "mesh_records": records,
                  "limitations": [*assessment["limitations"], *_LIMITATIONS]}
        save_json(output / "analysis_raw.json", result)
        return result
