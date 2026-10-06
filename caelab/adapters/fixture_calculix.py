"""Preliminary linear fixture screen from a *verified parent CAD revision*.

This adapter reuses the pinned fixture project's mesh/deck/result routines, but
never calls its legacy `run()`: that function rebuilds a different CAD design.
Only the STEP named in the parent experiment's artifact manifest is meshed.
The fixed-bottom and distributed saddle load are idealizations, not a strength
rating or release decision.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Any

import cadquery as cq

from .fixture_saddle_load import saddle_nodal_forces
from .fixture_field import (capture_fixture_field_inputs, extract_fixture_field,
                            request_complete_displacement)
from ..storage import save_json
from ..execution_control import run_owned_command


UPSTREAM = Path(__file__).resolve().parents[2] / "plugins/fixture_design/upstream"
SCREEN = UPSTREAM / "scripts/run_structural_screen.py"
SHA256 = re.compile(r"^[0-9a-f]{64}$")
_PENDING = ["machine_interface", "static_strength", "physical_load_test",
            "fatigue_durability", "joint_and_contact", "material_qualification",
            "reaction_balance", "stress_convergence"]
_STRESS_LABELS = ("SXX 1 4 1 1", "SYY 1 4 2 2", "SZZ 1 4 3 3",
                  "SXY 1 4 1 2", "SYZ 1 4 2 3", "SZX 1 4 3 1")
_STRESS_NUMBER = re.compile(r"[-+]?\d+\.\d+E[-+]\d+")
_SELECTED_OBSERVATION = "Observed on selected mesh; mesh sensitivity unassessed"
_MESH_NOT_ASSESSED = "Mesh sensitivity not assessed for an explicitly selected single mesh"
_NATIVE_COMPLETION = "native linear solve completion; no mesh-independence verdict"


def _screen():
    """Load the exact upstream parser and solver helpers from the pinned tree."""
    if not SCREEN.is_file():
        raise RuntimeError("Fixture submodule missing: git submodule update --init")
    if str(UPSTREAM) not in sys.path:
        sys.path.insert(0, str(UPSTREAM))
    spec = importlib.util.spec_from_file_location("_caelab_fixture_structural_screen", SCREEN)
    if spec is None or spec.loader is None:
        raise RuntimeError("Cannot load pinned fixture structural screen")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _finite_positive(value: Any) -> bool:
    return (type(value) in (int, float) and math.isfinite(value) and value > 0)


def _per_mesh_responses(studies: list[dict], output: Path,
                        mesh_trend_passed: bool | None, *, selected_mesh: bool = False) -> tuple[dict, dict]:
    """Project loaded-saddle global UZ observations without another native parser.

    Both numeric lists use the native study order. The signed minimum is over
    ROLLER_NODES only; it is not a whole-model extremum or a magnitude.
    """
    if (not isinstance(studies, list) or type(selected_mesh) is not bool or
            (selected_mesh and (len(studies) != 1 or mesh_trend_passed is not None)) or
            (not selected_mesh and (not 2 <= len(studies) <= 8 or type(mesh_trend_passed) is not bool))):
        raise ValueError("Invalid per-mesh response sequence or trend verdict")
    root = Path(output).resolve(strict=True)
    if not root.is_dir():
        raise ValueError("Per-mesh response output directory is missing")
    sizes, displacements, sources = [], [], []
    for index, study in enumerate(studies):
        if not isinstance(study, dict):
            raise ValueError(f"Invalid per-mesh response study: {index}")
        size = study.get("mesh_size_max_mm")
        if not _finite_positive(size) or (sizes and sizes[-1] <= size):
            raise ValueError(f"Invalid per-mesh response mesh order: {index}")
        displacement = study.get("displacement")
        uz = (displacement.get("min_vertical_displacement_mm")
              if isinstance(displacement, dict) else None)
        if type(uz) not in (int, float) or not math.isfinite(uz):
            raise ValueError(f"Missing or nonfinite per-mesh signed UZ: {index}")
        boundary = study.get("boundary")
        count = boundary.get("loaded_node_count") if isinstance(boundary, dict) else None
        ids = boundary.get("loaded_node_ids") if isinstance(boundary, dict) else None
        if (type(count) is not int or count <= 0 or not isinstance(ids, list) or
                len(ids) != count or any(type(node) is not int or node <= 0 for node in ids) or
                len(set(ids)) != count):
            raise ValueError(f"Invalid per-mesh loaded-node identity: {index}")
        files = study.get("files")
        relative = files.get("displacement_table") if isinstance(files, dict) else None
        expected = f"support_{index}/support_{index}.dat"
        if relative != expected:
            raise ValueError(f"Invalid per-mesh DAT association: {index}")
        dat = root / relative
        if (dat.is_symlink() or dat.parent.is_symlink() or not dat.is_file() or
                not dat.resolve(strict=True).is_relative_to(root)):
            raise ValueError(f"Missing or unowned per-mesh DAT artifact: {index}")
        sizes.append(size)
        displacements.append(uz)
        sources.append({"index": index, "mesh_size_max_mm": size,
                        "loaded_node_count": count,
                        "displacement_table": "simulation/" + relative,
                        "displacement_table_sha256": hashlib.sha256(dat.read_bytes()).hexdigest()})
    metrics = {
        "mesh_size_max_mm": {"value": sizes, "unit": "mm", "valid": True},
        "loaded_saddle_min_global_uz": {"value": displacements, "unit": "mm",
                                        "valid": True if selected_mesh else mesh_trend_passed,
                                        **({"reason": _SELECTED_OBSERVATION} if selected_mesh else
                                           {"reason": "Declared mesh trend threshold exceeded"}
                                           if not mesh_trend_passed else {})},
    }
    provenance = {"source_result": "simulation/result.json", "node_set": "ROLLER_NODES",
                  "coordinate_system": "global Cartesian", "component": "UZ",
                  "statistic": "minimum over loaded saddle nodes", "unit": "mm",
                  "mesh_metric": "mesh_size_max_mm", "response_metric": "loaded_saddle_min_global_uz",
                  "studies": sources}
    return metrics, provenance


def _artifact(parent: dict, root: Path, name: str) -> tuple[Path, str, dict]:
    matching = [a for a in parent.get("artifacts", []) if a.get("path") == name]
    if len(matching) != 1:
        raise ValueError(f"Exactly one manifest record required: {name}")
    item = matching[0]
    relative = Path(name)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("Artifact path escapes the experiment")
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise ValueError(f"Artifact missing or outside experiment: {name}")
    expected = item.get("sha256")
    if not isinstance(expected, str) or not SHA256.fullmatch(expected):
        raise ValueError(f"Invalid artifact digest: {name}")
    if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
        raise ValueError(f"Artifact SHA-256 mismatch: {name}")
    return path, expected, item


def _version(command: str) -> str:
    try:
        result = subprocess.run([command, "-version" if command == "gmsh" else "-v"],
                                text=True, capture_output=True, timeout=10, check=False)
        return (result.stdout + "\n" + result.stderr).strip()[:400] or "unavailable"
    except (OSError, subprocess.TimeoutExpired):
        return "unavailable"


def _finite_displacement_table(dat: Path, loaded: set[int]) -> None:
    """Require every displacement component to be finite, not just extrema."""
    content = dat.read_text(errors="replace").lower()
    marker = "displacements (vx,vy,vz)"
    if marker not in content:
        raise RuntimeError("CalculiX displacement table not found")
    records = set()
    for line in content.rsplit(marker, 1)[1].splitlines():
        fields = line.strip().split()
        if len(fields) != 4:
            continue
        try:
            node = int(fields[0])
        except ValueError:
            continue
        if node not in loaded:
            continue
        try:
            values = [float(value.replace("d", "e")) for value in fields[1:]]
        except ValueError as exc:
            raise RuntimeError(f"Malformed loaded-node displacement: {node}") from exc
        if not all(math.isfinite(value) for value in values):
            raise RuntimeError(f"Nonfinite loaded-node displacement: {node}")
        records.add(node)
    if records != loaded:
        raise RuntimeError(f"Incomplete loaded-node displacement: {len(records)}/{len(loaded)}")


def _request_base_reactions(deck: Path) -> None:
    """Ask CalculiX for RF only where there are no applied nodal loads."""
    content = deck.read_text()
    marker = "*END STEP\n"
    if content.count(marker) != 1 or not content.endswith(marker):
        raise RuntimeError("Unexpected solver deck step structure")
    deck.write_text(content[:-len(marker)] +
                    "*NODE PRINT, NSET=BASE_FIXED\nRF\n" + marker)


def _apply_saddle_forces(deck: Path, nodal_loads: dict[int, float],
                         expected_old_count: int) -> None:
    """Replace the fixture screen's equal-node saddle BC, preserving the deck.

    The upstream writer owns material, element and fixed-base definitions. We
    require its exact section boundaries before replacing just the load set
    and nodal forces; an upstream deck format change fails closed.
    """
    if (not nodal_loads or any(type(node) is not int or node <= 0 or
                               not math.isfinite(force) or force >= 0
                               for node, force in nodal_loads.items())):
        raise ValueError("Invalid downward saddle nodal loads")
    content = deck.read_text()
    nset = "*NSET, NSET=ROLLER_NODES\n"
    material = "*MATERIAL, NAME=PRINT_INPUT\n"
    cload = "*CLOAD\n"
    print_set = "*NODE PRINT, NSET=ROLLER_NODES\n"
    if any(content.count(marker) != 1 for marker in (nset, material, cload, print_set)):
        raise RuntimeError("Unexpected solver deck structure for saddle loads")
    start, rest = content.split(nset, 1)
    old_set, rest = rest.split(material, 1)
    if not old_set.strip() or "*" in old_set:
        raise RuntimeError("Unexpected original saddle node set")
    before_load, rest = rest.split(cload, 1)
    old_loads, after_load = rest.split(print_set, 1)
    old_lines = old_loads.strip().splitlines()
    if len(old_lines) != expected_old_count or any(len(line.split(",")) != 3 for line in old_lines):
        raise RuntimeError("Unexpected original saddle force definition")
    identifiers = sorted(nodal_loads)
    new_set = "".join(", ".join(map(str, identifiers[i:i + 12])) + "\n"
                      for i in range(0, len(identifiers), 12))
    # CalculiX 2.21's *CLOAD reader rejects a 22-character numeric field.
    # Twelve significant digits keep this field below its observed limit and
    # lose far less than the declared 1% reaction-balance tolerance.
    formatted = [f"{nodal_loads[node]:.12g}" for node in identifiers]
    if any(len(value) > 20 for value in formatted):
        raise ValueError("A saddle force exceeds the verified *CLOAD field width")
    new_loads = "".join(f"{node}, 3, {value}\n"
                        for node, value in zip(identifiers, formatted))
    if abs(math.fsum(float(value) for value in formatted) -
           math.fsum(nodal_loads.values())) > 1e-8 * abs(math.fsum(nodal_loads.values())):
        raise ValueError("Saddle force serialization changed the applied load")
    deck.write_text(start + nset + new_set + material + before_load + cload +
                    new_loads + print_set + after_load)


def _base_reactions(dat: Path, fixed: set[int], applied_force_N: float) -> dict:
    """Read all fixed-node RF vectors and check signed, three-axis equilibrium.

    CalculiX RF is external force; it equals the reaction on this fixed set
    because the concentrated saddle load and fixed-node sets are disjoint.
    """
    lines = dat.read_text(errors="replace").splitlines()
    header = re.compile(r"^\s*forces\s*\(fx,fy,fz\)\s+for set\s+BASE_FIXED\b", re.I)
    starts = [i for i, line in enumerate(lines) if header.search(line)]
    if len(starts) != 1:
        raise RuntimeError(f"Expected one BASE_FIXED reaction table, found {len(starts)}")
    records: dict[int, list[float]] = {}
    started = False
    for line in lines[starts[0] + 1:]:
        fields = line.strip().split()
        if not fields:
            if started:
                break
            continue
        try:
            node = int(fields[0])
        except ValueError:
            if started:
                break
            continue
        if len(fields) != 4 or node not in fixed or node in records:
            raise RuntimeError(f"Invalid or duplicate fixed-node reaction: {node}")
        try:
            vector = [float(value.replace("D", "E").replace("d", "e"))
                      for value in fields[1:]]
        except ValueError as exc:
            raise RuntimeError(f"Malformed fixed-node reaction: {node}") from exc
        if not all(math.isfinite(value) for value in vector):
            raise RuntimeError(f"Nonfinite fixed-node reaction: {node}")
        records[node] = vector
        started = True
    if set(records) != fixed:
        raise RuntimeError(f"Incomplete fixed-node reactions: {len(records)}/{len(fixed)}")
    reaction = [math.fsum(v[axis] for v in records.values()) for axis in range(3)]
    residual = [reaction[0], reaction[1], reaction[2] - applied_force_N]
    relative = math.sqrt(math.fsum(component * component for component in residual)) / applied_force_N
    return {"reaction_force_N": reaction, "applied_force_N": [0.0, 0.0, -applied_force_N],
            "residual_force_N": residual, "relative_imbalance": relative,
            "fixed_node_count": len(records)}


def _extract_stress_field(frd: Path, nodes: dict, screen: Any) -> tuple[dict, dict]:
    """Retain the complete nodal tensor alongside the pinned diagnostic.

    The existing single linear step writes one averaged nodal STRESS block.
    CalculiX 2.21's frd.c/frdselect.c specify the six labels below, a ten-column
    node ID and six E12.5 values. Mesh coordinates come from the already checked
    Gmsh mesh, without substituting the lower-precision FRD coordinates.
    """
    if not isinstance(nodes, dict) or not nodes:
        raise RuntimeError("Stress field requires a nonempty verified mesh")
    for node, position in nodes.items():
        if type(node) is not int or node <= 0:
            raise RuntimeError("Invalid stress-field mesh node ID")
        if (not isinstance(position, (tuple, list)) or len(position) != 3 or
                any(type(value) not in (int, float) or not math.isfinite(value)
                    for value in position)):
            raise RuntimeError(f"Invalid or nonfinite stress-field mesh position: {node}")

    source = frd.read_bytes()
    try:
        lines = source.decode("ascii").splitlines()
    except UnicodeDecodeError as exc:
        raise RuntimeError("CalculiX stress field requires ASCII FRD") from exc
    starts = [index for index, line in enumerate(lines)
              if " -4  STRESS" in line]
    if len(starts) != 1:
        raise RuntimeError("Expected one CalculiX nodal STRESS block")
    index = starts[0]
    if lines[index].split() != ["-4", "STRESS", "6", "1"]:
        raise RuntimeError("Malformed six-component nodal STRESS header")
    if (not lines or lines[-1].strip() != "9999" or
            sum(line.strip() == "9999" for line in lines) != 1):
        raise RuntimeError("Incomplete CalculiX ASCII FRD end marker")
    index += 1
    for label in _STRESS_LABELS:
        if index >= len(lines) or lines[index].split() != ["-5", *label.split()]:
            raise RuntimeError("Incomplete or reordered nodal stress components")
        index += 1

    records = {}
    while index < len(lines) and lines[index].strip() != "-3":
        line = lines[index]
        if line[:3] != " -1" or len(line) < 85 or line[85:].strip():
            raise RuntimeError("Malformed six-component nodal stress record")
        label = line[3:13].strip()
        if not re.fullmatch(r"[1-9]\d*", label):
            raise RuntimeError("Malformed nodal stress ID")
        node = int(label)
        if node in records or node not in nodes:
            raise RuntimeError(f"Duplicate or unexpected nodal stress ID: {node}")
        tensor = []
        for component in range(6):
            token = line[13 + 12 * component:25 + 12 * component].strip()
            try:
                value = float(token)
            except ValueError as exc:
                raise RuntimeError(f"Malformed nodal stress component: {node}") from exc
            if not math.isfinite(value):
                raise RuntimeError(f"Nonfinite nodal stress component: {node}")
            if not _STRESS_NUMBER.fullmatch(token):
                raise RuntimeError(f"Malformed ASCII nodal stress component: {node}")
            tensor.append(value)
        sxx, syy, szz, sxy, syz, szx = tensor
        try:
            vm = math.sqrt(((sxx - syy)**2 + (syy - szz)**2 + (szz - sxx)**2) / 2 +
                           3 * (sxy * sxy + syz * syz + szx * szx))
        except ArithmeticError as exc:
            raise RuntimeError(f"Nonfinite computed von Mises stress: {node}") from exc
        if not math.isfinite(vm):
            raise RuntimeError(f"Nonfinite computed von Mises stress: {node}")
        records[node] = {"node_id": node, "position_mm": list(nodes[node]),
                         "stress_MPa": tensor, "von_mises_MPa": vm}
        index += 1
    if index == len(lines) or set(records) != set(nodes):
        raise RuntimeError(f"Incomplete nodal stress field: {len(records)}/{len(nodes)}")

    diagnostic = screen.extract_stress_diagnostic(frd, nodes)
    peak = max(records, key=lambda node: records[node]["von_mises_MPa"])
    values = sorted(row["von_mises_MPa"] for row in records.values())
    percentile_index = .95 * (len(values) - 1)
    lower = math.floor(percentile_index)
    upper = math.ceil(percentile_index)
    p95 = values[lower] + (percentile_index - lower) * (values[upper] - values[lower])
    expected = {"max_averaged_nodal_von_mises_MPa": records[peak]["von_mises_MPa"],
                "p95_averaged_nodal_von_mises_MPa": p95}
    if (not isinstance(diagnostic, dict) or
            set(diagnostic) != {*expected, "maximum_node_id", "maximum_node_xyz_mm", "node_count"} or
            type(diagnostic["node_count"]) is not int or diagnostic["node_count"] != len(nodes) or
            type(diagnostic["maximum_node_id"]) is not int or diagnostic["maximum_node_id"] != peak or
            diagnostic["maximum_node_xyz_mm"] != nodes[peak]):
        raise RuntimeError("Nodal stress field differs from pinned stress diagnostic")
    for name, value in expected.items():
        actual = diagnostic[name]
        # Independent percentile interpolation may differ by floating-point
        # roundoff; this is not an engineering acceptance tolerance.
        if (type(actual) not in (int, float) or not math.isfinite(actual) or
                abs(actual - value) > 64 * math.ulp(max(abs(actual), abs(value)))):
            raise RuntimeError("Nodal stress field differs from pinned stress diagnostic")
    if frd.read_bytes() != source:
        raise RuntimeError("CalculiX FRD changed during stress-field extraction")
    field = {"schema_version": "1.0", "field": "stress", "representation": "AVERAGED_NODAL",
             "unit": "MPa", "coordinate_frame": "SOLVER_GLOBAL_CARTESIAN",
             "component_order": [label.split()[0] for label in _STRESS_LABELS],
             "tensor_shear_components": True, "engineering_valid": False,
             "qualification": "UNKNOWN",
             "source_frd": {"path": frd.name, "sha256": hashlib.sha256(source).hexdigest()},
             "nodes": [records[node] for node in sorted(records)], "node_count": len(records)}
    return field, diagnostic


class FixtureCalculiXAdapter:
    backend = "fixture.calculix"
    version = "6"
    analysis_type = "linear_static"
    default_metrics = ["max_displacement", "peak_stress", "displacement_mesh_change_ratio",
                       "applied_force_per_support", "reaction_force", "reaction_balance_ratio",
                       "mesh_size_max_mm", "loaded_saddle_min_global_uz"]

    conditions_version = "1"

    def research_metric_semantics(self, result):
        if (result['provenance'].get('adapter') != self.backend
                or result['provenance'].get('adapter_version') != '6'):
            return None
        return {'max_displacement': {
            'label': '하중 새들 절점 최대 |UZ|', 'quantity': 'displacement',
            'component': 'UZ', 'reduction': 'MAX_ABSOLUTE', 'selection_id': 'S-saddle',
            'coordinate_system': 'global', 'unit': 'mm', 'source': 'ADAPTER_DECLARED_RESPONSE'}}

    @staticmethod
    def conditions_policy_identity() -> dict:
        root = Path(__file__).resolve().parents[2]
        return {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in (
            "caelab/adapters/fixture_calculix.py", "plugins/fixture_design/analysis_conditions.py",
            "plugins/elasticity/conditions.py", "plugins/fixture_design/upstream/scripts/run_structural_screen.py")}

    @staticmethod
    def conditions_preflight(catalog: dict, declaration: dict) -> dict:
        from plugins.fixture_design.analysis_conditions import support
        return support(catalog, declaration)

    def settings_from_conditions(self, catalog: dict, declaration: dict) -> dict:
        if self.conditions_preflight(catalog, declaration)["status"] != "SUPPORTED_DECLARED_INPUTS":
            raise ValueError("Unsupported declared conditions cannot be projected to solver settings")
        material = declaration["materials"][0]
        settings = {
            "load": {"force_per_support_N": -declaration["loads"][0]["components"]["FZ"],
                     "source": declaration["loads"][0]["source"]},
            "material": {"model": "isotropic", "elastic_modulus_MPa": material["young_modulus_MPa"],
                         "poisson_ratio": material["poisson_ratio"],
                         "provenance": material["source"]["category"] + ": " + material["source"]["description"],
                         "qualification": "USER_DECLARED_UNVERIFIED"},
            "mesh": {"mode": "selected", "max_sizes_mm": [declaration["mesh"]["max_size_mm"]]}
        }
        # Keep the pinned upstream material admission authoritative as well.
        _screen().elastic_material_lines(settings["material"])
        return settings

    def solve(self, parent_result: dict, parent_root: Path, output: Path,
              settings: dict) -> dict:
        """Screen one printed roller support, preserving every mesh/solver file.

        On invalid inputs return REJECTED with a failing preflight check. Missing
        executables or process failures raise for Core to record FAILED_EXECUTION.
        """
        output = Path(output)
        parent_root = Path(parent_root)
        checks: list[dict[str, Any]] = []
        provenance: dict[str, Any] = {
            "parent_experiment_id": parent_result.get("experiment_id"),
            "cad_revision": parent_result.get("cad_revision"),
            "adapter": self.backend, "adapter_version": self.version,
            "upstream_screen_sha256": (hashlib.sha256(SCREEN.read_bytes()).hexdigest()
                                       if SCREEN.is_file() else None),
        }

        def reject(code: str, observed: Any, limit: Any = None) -> dict:
            checks.append({"code": code, "status": "FAIL", "observed": observed,
                           "limit": limit})
            result = {"status": "REJECTED", "checks": checks, "metrics": {},
                      "solver_status": "NOT_RUN", "converged": None,
                      "pending_validations": list(_PENDING), "provenance": provenance,
                      "raw_result": "simulation/result.json"}
            output.mkdir(parents=True, exist_ok=True)
            save_json(output / "result.json", result)
            return result

        if (parent_result.get("status") != "COMPLETED_REVIEW_REQUIRED" or
                parent_result.get("decision") != "NOT_RELEASED" or
                not isinstance(parent_result.get("cad_revision"), str) or
                not SHA256.fullmatch(parent_result["cad_revision"])):
            return reject("parent_cad_state", parent_result.get("status"),
                          "COMPLETED_REVIEW_REQUIRED with a verified CAD revision")
        parent_provenance = parent_result.get("provenance")
        if not isinstance(parent_provenance, dict) or parent_provenance.get("adapter") != "fixture.cadquery":
            return reject("cad_backend", (parent_provenance.get("adapter")
                                         if isinstance(parent_provenance, dict) else parent_provenance),
                          "fixture.cadquery")
        artifacts = parent_result.get("artifacts")
        if not isinstance(artifacts, list) or not all(isinstance(a, dict) for a in artifacts):
            return reject("cad_artifacts", "Missing artifact manifest", "Verified manifest")
        steps = [a for a in artifacts if isinstance(a.get("path"), str)
                 and a["path"].lower().endswith(".step")]
        if len(steps) != 1:
            return reject("cad_step_unique", len(steps), 1)
        step_name = steps[0]["path"]
        try:
            step, step_sha, step_record = _artifact(parent_result, parent_root, step_name)
            input_path, input_sha, _ = _artifact(parent_result, parent_root, "cad/input.json")
            cad_path, cad_sha, _ = _artifact(parent_result, parent_root, "cad/result.json")
            if step_record.get("revision") != parent_result["cad_revision"]:
                raise ValueError("STEP revision does not match parent CAD revision")
            cad_input = json.loads(input_path.read_text(encoding="utf-8"))
            cad_result = json.loads(cad_path.read_text(encoding="utf-8"))
        except (ValueError, OSError, TypeError, json.JSONDecodeError) as exc:
            return reject("cad_artifact_integrity", str(exc), "Matching manifest hashes and revision")
        provenance.update({"parent_step_artifact": step_name, "parent_step_sha256": step_sha,
                           "parent_input_sha256": input_sha, "parent_cad_result_sha256": cad_sha})
        if not isinstance(cad_input, dict) or not isinstance(cad_result, dict):
            return reject("cad_model", "CAD metadata must be mappings", "roller_support metadata")
        params = cad_input.get("parameters", {})
        if (cad_input.get("model") != "roller_support" or
                cad_result.get("model") != "roller_support" or
                cad_result.get("cad_generated") is not True or
                cad_result.get("decision") != "REVIEW_REQUIRED" or
                cad_result.get("parameters") != params or
                not isinstance(params, dict)):
            return reject("cad_model", "Parent CAD input/result disagree or are not approved",
                          "roller_support generated and REVIEW_REQUIRED")
        if params.get("roller_diameter_mm") != 8.3 or not _finite_positive(params.get("support_depth_mm")) or params["support_depth_mm"] < 24:
            return reject("saddle_boundary_compatibility",
                          {"roller_diameter_mm": params.get("roller_diameter_mm"),
                           "support_depth_mm": params.get("support_depth_mm")},
                          {"roller_diameter_mm": 8.3, "minimum_support_depth_mm": 24})
        if not isinstance(settings, dict) or set(settings) != {"load", "material", "mesh"}:
            return reject("analysis_settings", "Explicit load, material and mesh required",
                          ["load", "material", "mesh"])
        load = settings["load"]
        if (not isinstance(load, dict) or set(load) != {"force_per_support_N", "source"} or
                not _finite_positive(load.get("force_per_support_N")) or
                not isinstance(load.get("source"), str) or not load["source"].strip()):
            return reject("load_definition", load, "Positive N per support and nonempty source")
        material = settings["material"]
        if (not isinstance(material, dict) or
                any(not isinstance(material.get(key), str) or not material[key].strip()
                    for key in ("provenance", "qualification"))):
            return reject("material_definition", material,
                          "Material mapping with nonempty provenance and qualification")
        try:
            screen = _screen()
            screen.elastic_material_lines(material)
        except (ValueError, KeyError, TypeError) as exc:
            return reject("material_definition", str(exc), "Valid elastic constants and qualification")
        mesh_settings = settings["mesh"]

        def reject_mesh(observed: Any, limit: str) -> dict:
            # Preserve nonfinite input visibly while keeping the rejection JSON
            # finite. Valid JSON observations retain their historical shape.
            try:
                json.dumps(observed, allow_nan=False)
            except (ValueError, TypeError, OverflowError):
                observed = repr(observed)
            return reject("mesh_settings", observed, limit)

        if not isinstance(mesh_settings, dict) or set(mesh_settings) not in ({"max_sizes_mm"}, {"mode", "max_sizes_mm"}):
            return reject_mesh(mesh_settings, "max_sizes_mm: descending list")
        selected_mesh = "mode" in mesh_settings
        if selected_mesh and (type(mesh_settings["mode"]) is not str or mesh_settings["mode"] != "selected"):
            return reject_mesh(mesh_settings, "Explicit mode must be selected")
        sizes = mesh_settings["max_sizes_mm"]
        size_limit = ("Exactly one finite positive size for explicit selected mode" if selected_mesh else
                      "2–8 finite positive strictly descending sizes")
        if (not isinstance(sizes, list) or (len(sizes) != 1 if selected_mesh else not 2 <= len(sizes) <= 8)):
            return reject_mesh(sizes, size_limit)
        try:
            invalid_sizes = any(not _finite_positive(x) for x in sizes)
        except OverflowError:
            invalid_sizes = True
        if (invalid_sizes or
                any(a <= b for a, b in zip(sizes, sizes[1:]))):
            return reject_mesh(sizes, size_limit)
        provenance.update({"force_per_support_N": load["force_per_support_N"],
                           "load_source": load["source"], "material": material,
                           "mesh_max_sizes_mm": sizes,
                           "load_discretization": "clipped_tessellated_saddle_surface_area_v1",
                           "model_idealization": "fixed bottom; distributed saddle nodal force; one printed support"})
        if selected_mesh:
            provenance.update({"mesh_policy": {"mode": "selected", "scope": "one explicitly selected mesh"},
                               "mesh_sensitivity": {"status": "NOT_ASSESSED",
                                                    "scope": "loaded saddle displacement on the selected mesh",
                                                    "limitation": _MESH_NOT_ASSESSED},
                               "converged_semantics": _NATIVE_COMPLETION})

        # Inspect only the hashed STEP. Do not regenerate the old hard-coded
        # bending assembly, whose holes and coordinate frame differ from this CAD.
        try:
            shape = cq.importers.importStep(str(step)).val()
            solids = shape.Solids()
            if len(solids) != 1 or not solids[0].isValid() or solids[0].Volume() <= 0:
                raise ValueError("Expected one valid positive-volume support solid")
            support = solids[0]
            bb = support.BoundingBox()
            bounds = [bb.xlen, bb.ylen, bb.zlen]
            expected_bounds = [params[k] for k in
                               ("support_width_mm", "support_depth_mm", "support_height_mm")]
            if any(not _finite_positive(x) for x in expected_bounds):
                raise ValueError("Missing positive support dimensions")
            if any(abs(a - b) > .001 for a, b in zip(bounds, expected_bounds)):
                raise ValueError(f"STEP bounds {bounds} differ from CAD input {expected_bounds}")
            if max(abs(bb.xmin + bb.xmax), abs(bb.ymin + bb.ymax), abs(bb.zmin)) > .001:
                raise ValueError("STEP origin differs from boundary selector assumptions")
            bom = cad_result.get("bom", [])
            if (not isinstance(bom, list) or len(bom) != 1 or
                    not isinstance(bom[0], dict) or bom[0].get("part") != "roller_support" or
                    any(abs(a - b) > .001 for a, b in zip(bom[0]["bounds_mm"], bounds)) or
                    abs(bom[0]["volume_mm3"] / support.Volume() - 1) > 1e-5):
                raise ValueError("STEP geometry differs from parent CAD bill of materials")
            saddle = []
            for face in support.Faces():
                if face.geomType() != "CYLINDER":
                    continue
                cylinder = face._geomAdaptor().Cylinder()
                axis = cylinder.Axis()
                location, direction = axis.Location(), axis.Direction()
                fb = face.BoundingBox()
                if (abs(cylinder.Radius() - 4.15) < .001 and
                        abs(location.X()) < .001 and abs(location.Z() - bb.zmax) < .001 and
                        abs(direction.Y()) > .999 and fb.ylen >= 24 - .001):
                    saddle.append(face)
            if len(saddle) != 1:
                raise ValueError("Expected one full-depth 4.15 mm cylindrical saddle")
        except (ValueError, KeyError, TypeError, OSError, IndexError, RuntimeError) as exc:
            return reject("cad_geometry_preflight", str(exc),
                          "Single roller support with verified bounds, origin and saddle")
        checks.append({"code": "cad_step_preflight", "status": "PASS",
                       "observed": {"sha256": step_sha, "bounds_mm": bounds,
                                    "volume_mm3": support.Volume(), "cad_revision": parent_result["cad_revision"]},
                       "limit": "Manifest, dimension and saddle consistency"})
        checks.append({"code": "material_source", "status": "PASS",
                       "observed": material["provenance"], "limit": material["qualification"]})

        executables = {name: shutil.which(name) for name in ("gmsh", "ccx")}
        for name, executable in executables.items():
            if not executable:
                raise RuntimeError(f"Missing open-source executable: {name}")
        provenance.update({"executables": executables,
                           "versions": {name: _version(name) for name in executables}})
        output.mkdir(parents=True, exist_ok=True)
        if any(output.iterdir()):
            raise ValueError("Analysis output directory must be empty")
        copied = output / "input.step"
        shutil.copyfile(step, copied)
        if hashlib.sha256(copied.read_bytes()).hexdigest() != step_sha:
            raise RuntimeError("Copied analysis STEP differs from verified parent")
        studies = []
        for index, size in enumerate(sizes):
            job = f"support_{index}"
            folder = output / job
            folder.mkdir()
            mesh = folder / "gmsh.inp"
            gmsh_cmd = ["gmsh", str(copied.resolve()), "-3", "-order", "2", "-format", "inp",
                        "-o", str(mesh.resolve()), "-clmin", str(size / 2), "-clmax", str(size),
                        "-setnumber", "Mesh.SecondOrderLinear", "1", "-nopopup", "-v", "2"]
            save_json(folder / "commands.json", {"gmsh": gmsh_cmd, "ccx": ["ccx", job]})
            gmsh = run_owned_command(gmsh_cmd, folder, 'gmsh', timeout=180)
            (folder / "gmsh.log").write_text(gmsh.stdout + "\n" + gmsh.stderr)
            if gmsh.returncode or not mesh.is_file():
                raise RuntimeError(f"Gmsh failed: {folder / 'gmsh.log'}")
            nodes, elements = screen.parse_gmsh_inp(mesh)
            jac = screen.quadratic_tet_jacobian_quality(nodes, elements)
            checks.append({"code": f"mesh_{index}_jacobian", "status": "PASS",
                           "observed": jac, "limit": "> 1e-10 mm^3"})
            deck = folder / f"{job}.inp"
            boundary = screen.write_deck(deck, nodes, elements, support, material,
                                         load["force_per_support_N"])
            weighted = saddle_nodal_forces(mesh, nodes, bb, radius_mm=4.15,
                                            force_N=load["force_per_support_N"])
            _apply_saddle_forces(deck, weighted["nodal_loads"], boundary["loaded_node_count"])
            boundary.pop("per_node_force_N")
            boundary.update({key: value for key, value in weighted.items() if key != "nodal_loads"})
            boundary["loaded_node_count"] = len(weighted["nodal_loads"])
            save_json(folder / "saddle_load.json", weighted)
            checks.append({"code": f"mesh_{index}_saddle_load", "status": "PASS",
                           "observed": {key: value for key, value in weighted.items()
                                        if key not in ("nodal_loads", "loaded_node_ids")},
                           "limit": "Unique cylindrical face; central 24 mm patch; normalized total force"})
            _request_base_reactions(deck)
            request_complete_displacement(deck, nodes)
            field_inputs = capture_fixture_field_inputs(folder, index)
            checks.append({"code": f"mesh_{index}_cad_volume", "status": "PASS",
                           "observed": boundary["mesh_volume_relative_error"], "limit": .08})
            ccx = run_owned_command(["ccx", job], folder, 'ccx', timeout=300)
            (folder / "ccx.log").write_text(ccx.stdout + "\n" + ccx.stderr)
            frd, dat = folder / f"{job}.frd", folder / f"{job}.dat"
            if ccx.returncode or not frd.is_file() or not dat.is_file():
                raise RuntimeError(f"CalculiX failed: {folder / 'ccx.log'}")
            loaded_nodes = set(boundary["loaded_node_ids"])
            _finite_displacement_table(dat, loaded_nodes)
            displacement = screen.extract_vertical_displacements(dat, loaded_nodes)
            if displacement["min_vertical_displacement_mm"] >= 0:
                raise RuntimeError("Loaded saddle did not move in the expected -Z direction")
            fixed_nodes = {node for node, (_, _, z) in nodes.items()
                           if abs(z - support.BoundingBox().zmin) < 1e-4}
            if len(fixed_nodes) != boundary["fixed_node_count"] or fixed_nodes & loaded_nodes:
                raise RuntimeError("Fixed node set differs from the declared solver boundary")
            reactions = _base_reactions(dat, fixed_nodes, load["force_per_support_N"])
            checks.append({"code": f"mesh_{index}_reaction_balance",
                           "status": "PASS" if reactions["relative_imbalance"] <= .01 else "FAIL",
                           "observed": reactions, "limit": .01})
            stress_field, stress = _extract_stress_field(frd, nodes, screen)
            save_json(folder / "stress_field.json", stress_field)
            fea_field = extract_fixture_field(
                folder, mesh_index=index, mesh_size_max_mm=size,
                parent_experiment_id=parent_result["experiment_id"],
                cad_revision=parent_result["cad_revision"], expected_inputs=field_inputs,
                adapter_version=self.version)
            save_json(folder / "fea_field.json", fea_field)
            studies.append({"mesh_size_max_mm": size, "nodes": len(nodes),
                            "elements_C3D10": len(elements),
                            "minimum_quadratic_jacobian_mm3": jac,
                            "boundary": boundary, "displacement": displacement,
                            "reactions": reactions,
                            "stress_diagnostic": stress,
                            "files": {"mesh": f"{job}/gmsh.inp", "deck": f"{job}/{job}.inp",
                                      "saddle_load": f"{job}/saddle_load.json",
                                      "commands": f"{job}/commands.json",
                                      "gmsh_log": f"{job}/gmsh.log", "ccx_log": f"{job}/ccx.log",
                                      "field_results": f"{job}/{job}.frd",
                                      "stress_field": f"{job}/stress_field.json",
                                      "fea_field": f"{job}/fea_field.json",
                                      "displacement_table": f"{job}/{job}.dat"}})
        fine = studies[-1]
        denominator = fine["displacement"]["max_abs_vertical_displacement_mm"]
        if not _finite_positive(denominator):
            raise RuntimeError("Fine-mesh displacement is zero or invalid")
        if selected_mesh:
            trend = mesh_trend_passed = None
        else:
            coarse, fine = studies[-2:]
            numerator = abs(coarse["displacement"]["max_abs_vertical_displacement_mm"] -
                            fine["displacement"]["max_abs_vertical_displacement_mm"])
            trend = numerator / denominator
            # This is a numerical screen only. A mesh trend is evidence, not an
            # allowable stress, contact, bolted-base, or physical qualification.
            checks.append({"code": "displacement_mesh_trend", "status": "PASS" if trend <= .05 else "FAIL",
                           "observed": trend, "limit": .05})
            mesh_trend_passed = trend <= .05
        reaction_passed = all(v["reactions"]["relative_imbalance"] <= .01 for v in studies)
        metrics = {
            "max_displacement": {"value": denominator, "unit": "mm", "valid": True if selected_mesh else mesh_trend_passed,
                                 **({"reason": _SELECTED_OBSERVATION} if selected_mesh else
                                    {"reason": "Declared mesh trend threshold exceeded"}
                                    if not mesh_trend_passed else {})},
            "peak_stress": {"value": fine["stress_diagnostic"]["max_averaged_nodal_von_mises_MPa"],
                            "unit": "MPa", "valid": False,
                            "reason": "Averaged nodal diagnostic; no stress convergence or material allowable"},
            "displacement_mesh_change_ratio": {"value": trend, "unit": "1", "valid": not selected_mesh,
                                                **({"reason": _MESH_NOT_ASSESSED} if selected_mesh else {})},
            "reaction_force": {"value": fine["reactions"]["reaction_force_N"], "unit": "N",
                               "valid": reaction_passed,
                               **({"reason": "A mesh exceeds the 1% signed force balance limit"}
                                  if not reaction_passed else {})},
            "reaction_balance_ratio": {"value": max(v["reactions"]["relative_imbalance"]
                                                    for v in studies), "unit": "1", "valid": True},
            "applied_force_per_support": {"value": load["force_per_support_N"], "unit": "N", "valid": True},
        }
        per_mesh_metrics, per_mesh_provenance = _per_mesh_responses(
            studies, output, mesh_trend_passed, selected_mesh=selected_mesh)
        metrics.update(per_mesh_metrics)
        provenance["per_mesh_displacement"] = per_mesh_provenance
        provenance.update({"mesh": ["simulation/" + v["files"]["mesh"] for v in studies],
                           "solver_deck": ["simulation/" + v["files"]["deck"] for v in studies]})
        result = {"status": "COMPLETED" if (selected_mesh or mesh_trend_passed) and reaction_passed else "REJECTED", "checks": checks,
                  "metrics": metrics, "solver_status": "COMPLETED",
                  "converged": True,
                  "pending_validations": [kind for kind in _PENDING if kind != "reaction_balance"],
                  "provenance": provenance, "raw_result": "simulation/result.json",
                  "mesh_studies": studies,
                  "limitations": ["Fixed bottom substitutes for actual fasteners and base.",
                                  "Distributed nodal load substitutes for roller contact.",
                                  "Tessellated surface-area loading approximates a uniform vertical traction, not measured roller contact.",
                                  "Averaged nodal peak stress is diagnostic only.",
                                  "Material allowables and physical evidence remain unknown."]}
        if selected_mesh:
            result["limitations"].extend([_MESH_NOT_ASSESSED, _NATIVE_COMPLETION])
        save_json(output / "result.json", result)
        return result
