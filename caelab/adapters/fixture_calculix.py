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

from ..storage import save_json


UPSTREAM = Path(__file__).resolve().parents[2] / "plugins/fixture_design/upstream"
SCREEN = UPSTREAM / "scripts/run_structural_screen.py"
SHA256 = re.compile(r"^[0-9a-f]{64}$")
_PENDING = ["machine_interface", "static_strength", "physical_load_test",
            "fatigue_durability", "joint_and_contact", "material_qualification",
            "reaction_balance", "stress_convergence"]


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


class FixtureCalculiXAdapter:
    backend = "fixture.calculix"
    version = "1"
    analysis_type = "linear_static"
    default_metrics = ["max_displacement", "peak_stress", "displacement_mesh_change_ratio",
                       "applied_force_per_support"]

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
        if not isinstance(mesh_settings, dict) or set(mesh_settings) != {"max_sizes_mm"}:
            return reject("mesh_settings", mesh_settings, "max_sizes_mm: descending list")
        sizes = mesh_settings["max_sizes_mm"]
        if (not isinstance(sizes, list) or len(sizes) < 2 or len(sizes) > 8 or
                any(not _finite_positive(x) for x in sizes) or
                any(a <= b for a, b in zip(sizes, sizes[1:]))):
            return reject("mesh_settings", sizes, "2–8 finite positive strictly descending sizes")
        provenance.update({"force_per_support_N": load["force_per_support_N"],
                           "load_source": load["source"], "material": material,
                           "mesh_max_sizes_mm": sizes,
                           "model_idealization": "fixed bottom; distributed saddle nodal force; one printed support"})

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
            gmsh = subprocess.run(gmsh_cmd, cwd=folder, text=True, capture_output=True, timeout=180)
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
            checks.append({"code": f"mesh_{index}_cad_volume", "status": "PASS",
                           "observed": boundary["mesh_volume_relative_error"], "limit": .08})
            ccx = subprocess.run(["ccx", job], cwd=folder, text=True, capture_output=True, timeout=300)
            (folder / "ccx.log").write_text(ccx.stdout + "\n" + ccx.stderr)
            frd, dat = folder / f"{job}.frd", folder / f"{job}.dat"
            if ccx.returncode or not frd.is_file() or not dat.is_file():
                raise RuntimeError(f"CalculiX failed: {folder / 'ccx.log'}")
            loaded_nodes = set(boundary["loaded_node_ids"])
            _finite_displacement_table(dat, loaded_nodes)
            displacement = screen.extract_vertical_displacements(dat, loaded_nodes)
            if displacement["min_vertical_displacement_mm"] >= 0:
                raise RuntimeError("Loaded saddle did not move in the expected -Z direction")
            stress = screen.extract_stress_diagnostic(frd, nodes)
            studies.append({"mesh_size_max_mm": size, "nodes": len(nodes),
                            "elements_C3D10": len(elements),
                            "minimum_quadratic_jacobian_mm3": jac,
                            "boundary": boundary, "displacement": displacement,
                            "stress_diagnostic": stress,
                            "files": {"mesh": f"{job}/gmsh.inp", "deck": f"{job}/{job}.inp",
                                      "commands": f"{job}/commands.json",
                                      "gmsh_log": f"{job}/gmsh.log", "ccx_log": f"{job}/ccx.log",
                                      "field_results": f"{job}/{job}.frd",
                                      "displacement_table": f"{job}/{job}.dat"}})
        coarse, fine = studies[-2:]
        numerator = abs(coarse["displacement"]["max_abs_vertical_displacement_mm"] -
                        fine["displacement"]["max_abs_vertical_displacement_mm"])
        denominator = fine["displacement"]["max_abs_vertical_displacement_mm"]
        if not _finite_positive(denominator):
            raise RuntimeError("Fine-mesh displacement is zero or invalid")
        trend = numerator / denominator
        # This is a numerical screen only. A mesh trend is evidence, not an
        # allowable stress, contact, bolted-base, or physical qualification.
        checks.append({"code": "displacement_mesh_trend", "status": "PASS" if trend <= .05 else "FAIL",
                       "observed": trend, "limit": .05})
        mesh_trend_passed = trend <= .05
        metrics = {
            "max_displacement": {"value": denominator, "unit": "mm", "valid": mesh_trend_passed,
                                 **({"reason": "Declared mesh trend threshold exceeded"}
                                    if not mesh_trend_passed else {})},
            "peak_stress": {"value": fine["stress_diagnostic"]["max_averaged_nodal_von_mises_MPa"],
                            "unit": "MPa", "valid": False,
                            "reason": "Averaged nodal diagnostic; no stress convergence or material allowable"},
            "displacement_mesh_change_ratio": {"value": trend, "unit": "1", "valid": True},
            "applied_force_per_support": {"value": load["force_per_support_N"], "unit": "N", "valid": True},
        }
        provenance.update({"mesh": ["simulation/" + v["files"]["mesh"] for v in studies],
                           "solver_deck": ["simulation/" + v["files"]["deck"] for v in studies]})
        result = {"status": "COMPLETED" if mesh_trend_passed else "REJECTED", "checks": checks,
                  "metrics": metrics, "solver_status": "COMPLETED",
                  "converged": True, "pending_validations": list(_PENDING),
                  "provenance": provenance, "raw_result": "simulation/result.json",
                  "mesh_studies": studies,
                  "limitations": ["Fixed bottom substitutes for actual fasteners and base.",
                                  "Distributed nodal load substitutes for roller contact.",
                                  "Averaged nodal peak stress is diagnostic only.",
                                  "Material allowables and physical evidence remain unknown."]}
        save_json(output / "result.json", result)
        return result
