"""Real adaptive fixture search, CAD gates and exact interruption replay."""

import argparse
import hashlib
import json
import math
from pathlib import Path

from caelab import Lab
from caelab.storage import load_json, save_json


def run(store: Path):
    lab = Lab(store)
    lab.create_study("S-opt", "Bounded support volume optimization",
                     "Can a numerical engine reduce CAD volume under a declared displacement screen?",
                     "Some narrower supports remain numerically usable under the assumed load.",
                     "Minimize volume with a research displacement constraint; do not qualify strength.")
    lab.register_parameter("S-opt", "fixture.cadquery", "roller_support",
                           "support_width_mm", "support_width", "Support width", 28, 42)
    material = load_json(Path(__file__).resolve().parents[1] /
                         "plugins/fixture_design/upstream/examples/printed_material_ASSUMED.json")
    settings = {"load": {"force_per_support_N": 100.0,
                         "source": "Illustrative 100 N screen per support; unqualified, not measured"},
                "material": material, "mesh": {"max_sizes_mm": [2.0, 1.5]}}
    baseline = lab.run_experiment(study_id="S-opt", experiment_id="E-opt-baseline-cad",
                                  backend="fixture.cadquery", model="roller_support",
                                  values={"support_width": 38})
    baseline_solve = lab.run_analysis(parent_experiment_id="E-opt-baseline-cad",
                                      experiment_id="E-opt-baseline-solve",
                                      backend="fixture.calculix", settings=settings)
    assert baseline_solve["status"] == "COMPLETED_REVIEW_REQUIRED"
    constraint = {"source": "analysis", "metric": "max_displacement", "unit": "mm",
                  "operator": "<=", "limit": .0065, "scale": .0065}
    plan = lab.plan_optimization(study_id="S-opt", campaign_id="C-opt", backend="fixture.cadquery",
                                  model="roller_support", parameter_ids=["support_width"],
                                  objective={"source": "cad", "metric": "cad_volume", "unit": "mm^3",
                                             "direction": "minimize"}, constraints=[constraint],
                                  seed=13, max_generations=1, population_size=5,
                                  initial_values={"support_width": 28.0},
                                  analysis_backend="fixture.calculix", analysis_settings=settings,
                                  required_validations={"cad": [], "analysis": ["displacement_mesh_trend",
                                      "mesh_0_reaction_balance", "mesh_1_reaction_balance"]})
    original = lab.run_experiment

    def interrupt_before_third(*args, **kwargs):
        if kwargs["experiment_id"] == "E-C-opt-0003":
            raise KeyboardInterrupt("Acceptance interruption after two completed evaluations")
        return original(*args, **kwargs)

    lab.run_experiment = interrupt_before_third
    try:
        lab.run_optimization("C-opt")
    except KeyboardInterrupt:
        pass
    else:
        raise AssertionError("Expected interruption was not exercised")
    progress = lab.inspect_optimization("C-opt")
    assert progress["completed_evaluations"] == 2
    saved = {path: path.read_bytes() for path in (store / "experiments").glob("E-C-opt-*/result.json")}
    lab.run_experiment = original
    result = lab.run_optimization("C-opt")
    assert all(path.read_bytes() == data for path, data in saved.items())
    assert lab.inspect_optimization("C-opt") == result
    assert lab.run_optimization("C-opt") == result
    assert result["algorithm"] == plan["algorithm"]
    assert result["termination"]["generations"] >= 1
    assert len(result["evaluations"]) > plan["algorithm"]["population_size"]
    best = result["incumbent"]
    assert best and best["numerically_feasible"] and best["usable"]
    assert best["objective"]["value"] < baseline["metrics"]["cad_volume"]["value"]
    assert best["constraints"][0]["value"] <= constraint["limit"]
    rejected = result["evaluations"][0]
    assert rejected["values"] == {"support_width": 28.0}
    assert rejected["cad_status"] == "REJECTED" and rejected["analysis_experiment_id"] is None
    assert rejected["feedback"]["objective"] is None
    assert not (store / "experiments/E-C-opt-0001-solve").exists()
    reference_errors, solver_runs = [], 0
    for row in result["evaluations"]:
        cad = lab.inspect_experiment(row["cad_experiment_id"])
        if cad["status"] == "COMPLETED_REVIEW_REQUIRED":
            width = row["values"]["support_width"]
            exact_volume = 40 * 26 * width - math.pi * 4.15**2 * 40 / 2 - 4 * math.pi * 2.25**2 * 26
            relative = abs(cad["metrics"]["cad_volume"]["value"] / exact_volume - 1)
            assert relative < 1e-9
            reference_errors.append(relative)
        if row["analysis_experiment_id"]:
            solve = lab.inspect_experiment(row["analysis_experiment_id"])
            assert solve["solver_status"] == "COMPLETED" and solve["converged"] is True
            assert solve["metrics"]["peak_stress"]["valid"] is False
            parent_step = store / "experiments" / row["cad_experiment_id"] / "cad/assembly.step"
            child_step = store / "experiments" / row["analysis_experiment_id"] / "simulation/input.step"
            assert parent_step.read_bytes() == child_step.read_bytes()
            assert solve["decision"] == "NOT_RELEASED"
            solver_runs += 1
        assert {"static_strength", "physical_load_test", "fatigue_durability"} <= set(row["unknown"])
    best_solve = lab.inspect_experiment(best["analysis_experiment_id"])
    report = {"status": "PASS", "campaign_id": "C-opt", "decision": "NOT_RELEASED",
              "algorithm": result["algorithm"], "termination": result["termination"],
              "evaluations": len(result["evaluations"]), "solver_children": solver_runs,
              "replayed_evaluations_without_rerun": 2,
              "objective": plan["objective"], "constraints": plan["constraints"],
              "baseline": {"width_mm": 38, "volume_mm3": baseline["metrics"]["cad_volume"]["value"],
                           "displacement_mm": baseline_solve["metrics"]["max_displacement"]["value"]},
              "best": {"values": best["values"], "volume_mm3": best["objective"]["value"],
                       "displacement_mm": best["constraints"][0]["value"],
                       "cad_experiment_id": best["cad_experiment_id"],
                       "analysis_experiment_id": best["analysis_experiment_id"]},
              "maximum_cad_volume_reference_error": max(reference_errors),
              "reference": "Analytical support volume; constrained quadratic engine regression has a known optimum",
              "source": {k: best_solve["provenance"][k] for k in
                         ("core_commit", "core_dirty", "core_source_sha256", "source_commit")},
              "solver_versions": result["provenance"]["solver_versions"],
              "result_sha256": hashlib.sha256((store / "optimizations/C-opt/result.json").read_bytes()).hexdigest(),
              "limitations": ["One bounded generation does not establish a global or converged fixture optimum.",
                              "The displacement bound is a research screen, not a strength allowable.",
                              "Material/contact/fasteners/physical qualification remains UNKNOWN."]}
    save_json(store / "optimization_acceptance.json", report)
    print(json.dumps(report))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--store", type=Path, required=True)
    run(parser.parse_args().store.resolve())
