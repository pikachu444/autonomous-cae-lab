"""Fresh-store structural family, cross-solver and immutable-record acceptance.

This is numerical/workflow evidence, never a release or whole MIDAS replication.
The fixed definition precedes execution; failed values and partial stores remain.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import math
from pathlib import Path
import subprocess

from caelab import Lab
from caelab.adapters.fixture_cadquery import FixtureCadQueryAdapter
from caelab.storage import load_json, save_json, source_identity, utc_now
from plugins.structural_families.reference import assess, specification


ROOT = Path(__file__).resolve().parents[1]
DEFINITION = ROOT / "benchmarks/specifications/structural-families-v1.json"
BACKENDS = ("structural.families.calculix", "structural.families.code_aster")
CASES = (("ansys_vmd1_regular", "Fx"), ("ansys_vmd1_regular", "Fy"),
         ("ansys_vmd1_regular", "Fz"), ("lame_cylinder_plane_strain", "pressure"),
         ("scordelis_lo_solid", "gravity"))
FIXTURE = ROOT / "plugins/fixture_design/upstream"


def freeze(folder: Path) -> dict:
    """Hash every file in a retained artifact folder."""
    return {str(path.relative_to(folder).as_posix()): {
        "bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        for path in sorted(folder.rglob("*")) if path.is_file()}


def _freeze_experiment(store: Path, identifier: str) -> dict:
    ledger = store / "ledger" / f"{identifier}.json"
    data = ledger.read_bytes()
    return {"files": freeze(store / "experiments" / identifier),
            "ledger": {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}}


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _source_snapshot() -> dict:
    """Pin committed identities and actual bytes across the whole acceptance."""
    tracked = subprocess.check_output(["git", "-C", str(ROOT), "ls-files", "-z"]).decode().split("\0")
    files = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
             for name in sorted(set(tracked)) if name and (ROOT / name).is_file()}
    pin = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse",
                                   "HEAD:plugins/fixture_design/upstream"], text=True).strip()
    fixture_dirty = bool(subprocess.check_output(["git", "-C", str(FIXTURE), "status", "--porcelain"],
                                                 text=True).strip())
    return {"core": source_identity(ROOT), "tracked_files_sha256": files,
            "fixture_pin": pin, "fixture": FixtureCadQueryAdapter.source_fingerprint(),
            "fixture_dirty": fixture_dirty}


def _check_source(snapshot: dict, result: dict | None = None) -> None:
    _require(_source_snapshot() == snapshot, "Source/HEAD/fixture identity changed during acceptance")
    if result is not None:
        provenance = result["provenance"]
        _require(provenance.get("source_commit") == snapshot["core"]["core_commit"],
                 "Core result source commit differs from frozen acceptance source")
        _require(all(provenance.get(key) == value for key, value in snapshot["core"].items()),
                 "Core result source bytes/clean identity differ from frozen acceptance source")


def _checked_completed(lab: Lab, store: Path, identifier: str, settings: dict,
                       result: dict, source: dict) -> tuple[dict, list[dict]]:
    """Apply identical evidence and qualification gates to baseline and changed loads."""
    _check_source(source, result)
    _require(result["status"] == "COMPLETED_REVIEW_REQUIRED" and result["solver_status"] == "COMPLETED"
             and result["converged"] is True, f"Native numerical checks failed: {identifier}")
    _require(result["decision"] == "NOT_RELEASED" and result["cad_revision"] is None,
             "Independent model qualification/CAD identity is invalid")
    _require(lab.inspect_experiment(identifier) == result, "Checked Core inspection differs")
    summary = lab.research_summary(identifier)
    _require(summary["experiment_id"] == identifier and summary["metrics"] == result["metrics"]
             and summary["status"] == result["status"] and summary["decision"] == result["decision"]
             and summary["model_revision"] == result["model_revision"], "Checked research summary differs")
    _require({"physical_validation", "model_qualification", "original_midas_replication"} <=
             set(summary["unknown"]), "Qualification UNKNOWN was lost")
    _require(result["metrics"]["primary_response"]["valid"] is True, "Native primary response is invalid")
    raw = load_json(store / "experiments" / identifier / "simulation/mesh_records.json")
    _require(assess(settings, raw)["metrics"] == result["metrics"],
             "Stored raw observations differ from Core metrics")
    _check_source(source, result)
    return summary, raw


def _cross_fields(settings: dict, left: list[dict], right: list[dict],
                  definition: dict) -> dict:
    """Compare every level/field by identity and physical position, not POINT."""
    a = assess(settings, left)
    b = assess(settings, right)
    scale = max(abs(a["reference"]["primary_response_mm"]), 1e-12)
    length = definition["normalization"]["characteristic_length_mm"][settings["case"]]
    position_tolerance = 1e-10 * length
    levels = []
    _require(len(left) == len(right) == len(settings["mesh_cells"]), "Cross-solver mesh count differs")
    for index, (first, second) in enumerate(zip(left, right)):
        _require(first["cells"] == second["cells"] == settings["mesh_cells"][index], "Cross-solver grids differ")
        _require(first["element_count"] == second["element_count"], "Cross-solver element counts differ")
        first_nodes = dict(zip(first["node_ids"], zip(first["coordinates_mm"], first["displacements_mm"])))
        second_nodes = dict(zip(second["node_ids"], zip(second["coordinates_mm"], second["displacements_mm"])))
        _require(first_nodes.keys() == second_nodes.keys(), "Cross-solver node catalogue differs")
        displacement_error = 0.0
        for node_id, (position, value) in first_nodes.items():
            other_position, other_value = second_nodes[node_id]
            _require(max(abs(x-y) for x,y in zip(position,other_position)) <= position_tolerance,
                     "Cross-solver node position differs")
            displacement_error = max(displacement_error, *(abs(x-y) for x,y in zip(value,other_value)))
        first_points, second_points = {}, {}
        for source, destination in ((first["stress_points"], first_points), (second["stress_points"], second_points)):
            for point in source:
                destination.setdefault(point["element_id"], []).append(point)
        _require(first_points.keys() == second_points.keys(), "Cross-solver stress element catalogue differs")
        stress_error, stress_scale, matched = 0.0, 1e-12, 0
        for element_id, points in first_points.items():
            other = second_points[element_id]
            _require(len(points) == len(other) == 27, "Cross-solver stress point count differs")
            used = set()
            for point in points:
                candidates = [j for j,p in enumerate(other) if
                    max(abs(x-y) for x,y in zip(point["coordinates_mm"],p["coordinates_mm"])) <= position_tolerance]
                _require(len(candidates) == 1 and candidates[0] not in used,
                         "Cross-solver physical Gauss-point matching is absent, duplicate or ambiguous")
                used.add(candidates[0]); paired = other[candidates[0]]
                stress_error = max(stress_error, *(abs(x-y) for x,y in
                    zip(point["components_mpa"],paired["components_mpa"])))
                stress_scale = max(stress_scale, *(abs(x) for x in point["components_mpa"]),
                                   *(abs(x) for x in paired["components_mpa"]))
                matched += 1
            _require(len(used) == 27, "Cross-solver stress matching is incomplete")
        response_error = abs(a["mesh_studies"][index]["primary_response_mm"] -
                             b["mesh_studies"][index]["primary_response_mm"]) / scale
        levels.append({"cells": first["cells"], "node_count": len(first_nodes), "matched_stress_points": matched,
                       "response_relative_error": response_error,
                       "displacement_field_relative_error": displacement_error / scale,
                       "stress_field_relative_error": stress_error / stress_scale,
                       "stress_scale_mpa": stress_scale, "point_matching_tolerance_mm": position_tolerance})
    limits = definition["numerical_limits"]
    checks = {"response": max(x["response_relative_error"] for x in levels) <= limits["cross_solver_response_relative"],
              "displacement_fields": max(x["displacement_field_relative_error"] for x in levels) <= limits["cross_solver_field_relative"],
              "stress_fields": max(x["stress_field_relative_error"] for x in levels) <= limits["cross_solver_field_relative"]}
    return {"status": "PASS" if all(checks.values()) else "FAIL", "checks": checks, "levels": levels,
            "normalization": deepcopy(definition["normalization"]), "limits": deepcopy(limits)}


def run(store: Path, source_commit: str) -> dict:
    store = store.resolve()
    _require(not store.exists(), "Use a fresh store; previous evidence is preserved")
    actual_commit = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip()
    _require(actual_commit == source_commit, "Acceptance source commit differs from the declared version")
    _require(not subprocess.check_output(["git", "-C", str(ROOT), "status", "--porcelain"], text=True).strip(),
             "Clean committed source is required before native acceptance")
    sources = _source_snapshot()
    _require(sources["core"]["core_commit"] == source_commit and sources["core"]["core_dirty"] is False
             and sources["fixture_dirty"] is False and sources["fixture"]["commit"] == sources["fixture_pin"],
             "Frozen source/fixture is not the clean committed revision")
    definition = load_json(DEFINITION)
    definition_bytes = DEFINITION.read_bytes()
    report = {"status": "RUNNING", "run_id": store.name, "source_commit": actual_commit,
              "started_utc": utc_now(), "decision": "NOT_RELEASED",
              "definition_sha256": hashlib.sha256(definition_bytes).hexdigest(),
              "definition_id": definition["definition_id"], "source_identity": sources,
              "experiments": [], "cross_solver": [],
              "changed_load": [], "expected_rejections": [], "original_preservation": "PENDING",
              "original_midas_replication": "UNKNOWN", "openscience_research": "NOT_RUN",
              "human_gui": "NOT_RUN"}
    lab = Lab(store)
    lab.create_study("S-structural-families", "Connected structural family verification",
        "Do two independent native solvers reproduce the frozen responses and a changed load on the same meshes?",
        "Linear force/pressure/gravity responses scale with load; complete fields agree at identical positions.",
        "Verify three physical families through common evidence, retaining source conflicts and qualification UNKNOWN.")
    save_json(store / "acceptance.json", report)
    completed, snapshots = {}, {}
    try:
        for case, load in CASES:
            settings = specification(case, load)
            pair, raw_pair = [], []
            for backend in BACKENDS:
                suffix = "ccx" if backend.endswith("calculix") else "aster"
                identifier = f"E-{case}-{load}-{suffix}"
                print(f"Native {case}/{load}/{suffix}", flush=True)
                result = lab.run_model_analysis(study_id="S-structural-families", experiment_id=identifier,
                                               backend=backend, settings=settings)
                report["experiments"].append(lab.research_summary(identifier))
                save_json(store / "acceptance.json", report)
                _, raw = _checked_completed(lab, store, identifier, settings, result, sources)
                completed[(case, load, backend)] = result
                snapshots[identifier] = _freeze_experiment(store, identifier)
                pair.append(result); raw_pair.append(raw)
            _require(pair[0]["model_revision"] == pair[1]["model_revision"], "The solvers used different model revisions")
            comparison = _cross_fields(settings, *raw_pair, definition)
            report["cross_solver"].append({"case": case, "load_case": load, **comparison})
            save_json(store / "acceptance.json", report)
            _require(comparison["status"] == "PASS", f"Cross-solver fields failed: {case}/{load}")
        for case, load in (CASES[2], CASES[3], CASES[4]):
            for backend in BACKENDS:
                suffix = "ccx" if backend.endswith("calculix") else "aster"
                identifier = f"E-{case}-{load}-half-{suffix}"
                settings = specification(case, load, .5)
                print(f"Changed load {case}/{suffix}", flush=True)
                result = lab.run_model_analysis(study_id="S-structural-families", experiment_id=identifier,
                                               backend=backend, settings=settings)
                report["experiments"].append(lab.research_summary(identifier))
                save_json(store / "acceptance.json", report)
                _checked_completed(lab, store, identifier, settings, result, sources)
                base = completed[(case, load, backend)]
                _require(result["model_revision"] != base["model_revision"], "Changed load did not produce a new model revision")
                full = base["metrics"]["primary_response"]["value"]
                half = result["metrics"]["primary_response"]["value"]
                error = abs(half - .5*full)/max(abs(full),1e-12)
                report["changed_load"].append({"experiment_id": identifier, "response_scaling_relative_error": error,
                    "limit": 1e-7, "status": "PASS" if error <= 1e-7 else "FAIL"})
                save_json(store / "acceptance.json", report)
                _require(error <= 1e-7, "Linear load scaling failed")
                _require(result["decision"] == "NOT_RELEASED" and lab.inspect_experiment(identifier) == result,
                         "Changed-load inspection or qualification failed")
                snapshots[identifier] = _freeze_experiment(store, identifier)
        for backend in BACKENDS:
            for label in ("torsion", "workload", "zero"):
                invalid = specification("ansys_vmd1_regular", "Fx")
                if label == "torsion": invalid["load_case"] = "Mx"
                if label == "workload": invalid["mesh_cells"] = [[48,48,1],[48,48,2]]
                if label == "zero": invalid["load_factor"] = 0
                suffix = "ccx" if backend.endswith("calculix") else "aster"
                identifier = f"E-refused-{label}-{suffix}"
                result = lab.run_model_analysis(study_id="S-structural-families", experiment_id=identifier,
                                               backend=backend, settings=invalid)
                _check_source(sources, result)
                _require(result["status"] == "REJECTED" and result["solver_status"] == "NOT_RUN",
                         f"Invalid declaration executed a solver: {identifier}")
                native_suffixes = {".msh", ".inp", ".comm", ".frd", ".med"}
                _require(not any(p.suffix.lower() in native_suffixes for p in
                    (store / "experiments" / identifier).rglob("*")), "Rejected request created native export/solver artifacts")
                _require(lab.inspect_experiment(identifier) == result and result["decision"] == "NOT_RELEASED",
                         "Rejected record inspection failed")
                report["expected_rejections"].append(lab.research_summary(identifier))
                snapshots[identifier] = _freeze_experiment(store, identifier)
        for identifier, original in snapshots.items():
            _require(_freeze_experiment(store, identifier) == original,
                     f"An original experiment changed: {identifier}")
        _require(DEFINITION.read_bytes() == definition_bytes, "Frozen benchmark definition changed during native execution")
        _check_source(sources)
        report.update(status="PASS_BOUNDED_NATIVE_FAMILIES", completed_utc=utc_now(),
                      original_preservation="PASS", frozen_experiments=snapshots,
                      limitations=["Three bounded solid derivatives, not whole MIDAS/NAFEMS certification.",
                                   "OpenScience/GUI acceptance is separate and is still NOT_RUN in this native runner.",
                                   "Unresolved references, independent shell rotations and engineering qualifications remain UNKNOWN."])
        save_json(store / "acceptance.json", report)
        return report
    except Exception as error:
        report.update(status="FAILED_OR_PARTIAL", stopped_utc=utc_now(),
                      failure={"type": type(error).__name__, "message": str(error)}, frozen_experiments=snapshots)
        save_json(store / "acceptance.json", report)
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--store", required=True, type=Path)
    parser.add_argument("--source-commit", required=True)
    args = parser.parse_args()
    result = run(args.store, args.source_commit)
    print(f"{result['status']} / NOT_RELEASED", flush=True)
