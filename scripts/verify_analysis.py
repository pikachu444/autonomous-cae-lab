"""Real CAD revision -> Gmsh/CalculiX -> immutable evidence acceptance."""

import argparse
import hashlib
import json
from pathlib import Path

from caelab import Lab


def run(store: Path):
    lab = Lab(store)
    lab.create_study("S-linear", "Bending support linear screen",
                     "What does an assumed static load do to a wider support?",
                     "A 38 mm support can be meshed and solved with traceable assumptions.",
                     "Verify solver input identity and numerical quality without release approval.")
    lab.register_parameter("S-linear", "fixture.cadquery", "roller_support",
                           "support_width_mm", "support_width", "Support width", 28, 60)
    cad = lab.run_experiment(study_id="S-linear", experiment_id="E-linear-cad",
                             backend="fixture.cadquery", model="roller_support",
                             values={"support_width": 38})
    assert cad["status"] == "COMPLETED_REVIEW_REQUIRED"
    cad_file = store / "experiments/E-linear-cad/result.json"
    original_parent = cad_file.read_bytes()
    material = json.loads((Path(__file__).resolve().parents[1] /
                           "plugins/fixture_design/upstream/examples/printed_material_ASSUMED.json").read_text())
    settings = {"load": {"force_per_support_N": 100.0,
                         "source": "Illustrative 100 N screen per support; unqualified, not measured"},
                "material": material, "mesh": {"max_sizes_mm": [4.0, 3.0, 2.0]}}
    analysis = lab.run_analysis(parent_experiment_id="E-linear-cad",
                                experiment_id="E-linear-solve", backend="fixture.calculix",
                                settings=settings)
    assert cad_file.read_bytes() == original_parent
    assert analysis["parent_experiment_id"] == "E-linear-cad"
    assert analysis["cad_revision"] == cad["cad_revision"]
    assert analysis["decision"] == "NOT_RELEASED"
    assert analysis["solver_status"] == "COMPLETED", analysis
    assert analysis["converged"] is True
    assert analysis["status"] in {"COMPLETED_REVIEW_REQUIRED", "REJECTED"}, [
        (v["type"], v["status"]) for v in analysis["validations"]]
    assert "static_strength" in lab.research_summary("E-linear-solve")["unknown"]
    numerical_failures = {v["type"] for v in analysis["validations"] if v["status"] == "FAIL"}
    assert numerical_failures <= {"displacement_mesh_trend"}, numerical_failures
    assert analysis["metrics"]["max_displacement"]["valid"] is (not numerical_failures)
    assert analysis["metrics"]["peak_stress"]["valid"] is False
    assert analysis["metrics"]["reaction_force"]["valid"] is True
    assert analysis["metrics"]["reaction_balance_ratio"]["value"] <= .01
    assert sum(v["type"].endswith("_reaction_balance") and v["status"] == "PASS"
               for v in analysis["validations"]) == 3
    assert "reaction_balance" not in lab.research_summary("E-linear-solve")["unknown"]
    parent_step = store / "experiments/E-linear-cad/cad/assembly.step"
    simulation = store / "experiments/E-linear-solve/simulation"
    assert hashlib.sha256(parent_step.read_bytes()).hexdigest() == hashlib.sha256(
        (simulation / "input.step").read_bytes()).hexdigest()
    artifacts = {a["path"] for a in analysis["artifacts"]}
    assert {"simulation/input.step", "simulation/result.json", "simulation/support_0/gmsh.inp",
            "simulation/support_0/saddle_load.json",
            "simulation/support_0/support_0.inp", "simulation/support_0/support_0.frd",
            "simulation/support_0/support_0.dat", "simulation/support_0/gmsh.log",
            "simulation/support_0/ccx.log"} <= artifacts
    thread = json.loads((store / "experiments/E-linear-solve/thread.json").read_text())
    assert set(thread["mesh"]) <= artifacts
    assert set(thread["solver_deck"]) <= artifacts
    assert lab.inspect_experiment("E-linear-solve")["cad_revision"] == cad["cad_revision"]
    summary = {"status": "PASS", "cad_revision": cad["cad_revision"],
               "parent_step_sha256": hashlib.sha256(parent_step.read_bytes()).hexdigest(),
               "solver_status": analysis["solver_status"], "decision": analysis["decision"],
               "analysis_status": analysis["status"],
               "displacement_valid": analysis["metrics"]["max_displacement"]["valid"],
               "displacement_mm": analysis["metrics"]["max_displacement"]["value"],
               "mesh_change_ratio": analysis["metrics"]["displacement_mesh_change_ratio"]["value"],
               "reaction_balance_ratio": analysis["metrics"]["reaction_balance_ratio"]["value"],
               "artifact_count": len(artifacts)}
    (store / "linear_acceptance.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--store", type=Path, required=True)
    run(parser.parse_args().store.resolve())
