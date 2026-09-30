"""Continue the fixed saddle-load benchmark to 1.5 mm without changing limits."""

import argparse
import hashlib
import json
from pathlib import Path

from caelab import Lab
from caelab.storage import load_json, save_json


def run(store: Path):
    lab = Lab(store)
    lab.create_study("S-finer", "Fixed saddle traction mesh continuation",
                     "Does the declared traction approximation stabilize at 1.5 mm?",
                     "Refinement preserves the same CAD, material, load patch and fixed base.",
                     "Check numerical evidence while keeping strength qualification unknown.")
    lab.register_parameter("S-finer", "fixture.cadquery", "roller_support",
                           "support_width_mm", "support_width", "Support width", 28, 60)
    cad = lab.run_experiment(study_id="S-finer", experiment_id="E-finer-cad",
                             backend="fixture.cadquery", model="roller_support",
                             values={"support_width": 38})
    assert cad["status"] == "COMPLETED_REVIEW_REQUIRED"
    parent_file = store / "experiments/E-finer-cad/result.json"
    original_parent = parent_file.read_bytes()
    material = load_json(Path(__file__).resolve().parents[1] /
                         "plugins/fixture_design/upstream/examples/printed_material_ASSUMED.json")
    settings = {"load": {"force_per_support_N": 100.0,
                         "source": "Illustrative 100 N screen per support; unqualified, not measured"},
                "material": material, "mesh": {"max_sizes_mm": [4.0, 3.0, 2.0, 1.5]}}
    analysis = lab.run_analysis(parent_experiment_id="E-finer-cad",
                                experiment_id="E-finer-solve", backend="fixture.calculix",
                                settings=settings)
    assert parent_file.read_bytes() == original_parent
    assert analysis["solver_status"] == "COMPLETED", analysis["validations"]
    assert analysis["converged"] is True
    raw = load_json(store / "experiments/E-finer-solve/simulation/result.json")
    assert [m["mesh_size_max_mm"] for m in raw["mesh_studies"]] == [4.0, 3.0, 2.0, 1.5]
    failures = [v for v in analysis["validations"] if v["status"] == "FAIL"]
    assert not failures, failures
    assert analysis["metrics"]["displacement_mesh_change_ratio"]["value"] <= .05
    assert analysis["metrics"]["reaction_balance_ratio"]["value"] <= .01
    assert analysis["metrics"]["max_displacement"]["valid"] is True
    assert analysis["metrics"]["peak_stress"]["valid"] is False
    assert analysis["decision"] == "NOT_RELEASED"
    assert {"static_strength", "joint_and_contact", "material_qualification",
            "physical_load_test", "fatigue_durability"} <= set(
                lab.research_summary("E-finer-solve")["unknown"])
    step = store / "experiments/E-finer-cad/cad/assembly.step"
    child_step = store / "experiments/E-finer-solve/simulation/input.step"
    assert step.read_bytes() == child_step.read_bytes()
    verified = lab.inspect_experiment("E-finer-solve")
    assert verified["cad_revision"] == cad["cad_revision"]
    rows = []
    for study in raw["mesh_studies"]:
        boundary = study["boundary"]
        rows.append({"mesh_max_mm": study["mesh_size_max_mm"],
                     "nodes": study["nodes"], "elements_C3D10": study["elements_C3D10"],
                     "loaded_nodes": boundary["loaded_node_count"],
                     "max_loaded_node_displacement_mm":
                         study["displacement"]["max_abs_vertical_displacement_mm"],
                     "patch_area_mm2": boundary["patch_area_mm2"],
                     "analytical_patch_area_mm2": boundary["analytical_patch_area_mm2"],
                     "patch_area_relative_error": boundary["patch_area_relative_error"],
                     "lip_force_fraction": boundary["lip_force_fraction"],
                     "outside_patch_force_fraction": boundary["outside_patch_force_fraction"],
                     "total_force_N": boundary["total_applied_force_N"],
                     "signed_reactions": study["reactions"],
                     "mesh_volume_relative_error": boundary["mesh_volume_relative_error"]})
    assert rows[-1]["patch_area_relative_error"] < rows[-2]["patch_area_relative_error"]
    report = {"status": "PASS", "cad_revision": cad["cad_revision"],
              "parent_step_sha256": hashlib.sha256(step.read_bytes()).hexdigest(),
              "source": {k: analysis["provenance"][k] for k in
                         ("core_commit", "core_dirty", "core_source_sha256", "source_commit")},
              "solver_versions": analysis["provenance"]["solver"]["versions"],
              "limits": {"displacement_last_pair": .05, "reaction_balance": .01},
              "mesh_change_ratio": analysis["metrics"]["displacement_mesh_change_ratio"]["value"],
              "meshes": rows, "decision": "NOT_RELEASED",
              "reference": "Analytical half-cylinder patch area; no exact structural solution claimed",
              "limitations": raw["limitations"],
              "artifact_hashes": {a["path"]: a["sha256"] for a in verified["artifacts"]},
              "result_sha256": hashlib.sha256(
                  (store / "experiments/E-finer-solve/result.json").read_bytes()).hexdigest()}
    save_json(store / "finer_acceptance.json", report)
    print(json.dumps({k: v for k, v in report.items() if k != "artifact_hashes"}))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--store", type=Path, required=True)
    run(parser.parse_args().store.resolve())
