"""Fresh native SI freefall and rigidwall benchmark through the existing Core."""

import argparse
from copy import deepcopy
from pathlib import Path

from caelab import Lab
from caelab.adapters.openradioss import OpenRadiossAdapter, runtime
from caelab.storage import load_json, save_json, source_identity


def specification(case="rigid_cube_freefall"):
    return {"case": case, "edge_m": .1, "mass_kg": 1., "center_height_m": 1., "gravity_m_s2": 9.81,
            "initial_velocity_m_s": 0., "end_time_s": .2 if case == "rigid_cube_freefall" else .5,
            "time_step_s": 1e-4, "history_interval_s": 1e-3 if case == "rigid_cube_freefall" else 1e-4,
            "limits": {"displacement_abs_m": 2e-4, "velocity_abs_m_s": .002,
                       "energy_abs_j": .01, "mass_relative": 1e-8, "impact_time_abs_s": 2e-4,
                       "impulse_abs_n_s": .005, "penetration_abs_m": .001}}


def run(store):
    store = Path(store)
    if store.exists():
        raise ValueError("Native acceptance requires a new store; historical attempts are preserved")
    runtime()  # Verify the isolated runtime before creating a new campaign.
    plan = {"freeflight": specification(), "ground_stop": specification("rigid_cube_ground_stop"),
            "refinement_dt_s": 5e-5,
            "sensitivity": {"mass_kg": 2., "gravity_m_s2": 4.905,
                            "initial_velocity_m_s": -.5, "history_interval_s": .0002},
            "contact_full_history": True, "threshold_changes_allowed": False,
            "source": source_identity(Path(__file__).resolve().parents[1])}
    save_json(store / "acceptance_plan.json", plan)
    adapter = OpenRadiossAdapter()
    lab = Lab(store, adapters={}, analysis_adapters={}, doe_adapters={}, optimization_adapters={},
              pde_adapters={}, model_analysis_adapters={adapter.backend: adapter})
    lab.create_study("S-explicit-drop", "Native bounded explicit flight and ground stop",
                     "Do native displacement, velocity, mass, work and support histories reproduce independent mechanics?",
                     "Flight should pass; an ideal kinematic wall must satisfy every postimpact sample to pass contact.",
                     "Keep failed native histories and unqualified engineering requirements UNKNOWN.")
    results, retained = {}, {}

    def execute(identifier, settings):
        result = lab.run_model_analysis(study_id="S-explicit-drop", experiment_id=identifier,
                                        backend=adapter.backend, settings=settings)
        assert lab.inspect_experiment(identifier) == result
        assert result["cad_revision"] is None and "parent_experiment_id" not in result
        assert result["decision"] == "NOT_RELEASED"
        results[identifier] = result
        retained[identifier] = (store / "experiments" / identifier / "result.json").read_bytes()
        return result

    baseline = execute("E-freefall", specification())
    for identifier, settings in [("E-freefall", specification())] + [
            ("E-freefall-" + name.replace("_", "-"), {**specification(), name: value})
            for name, value in plan["sensitivity"].items()]:
        result = baseline if identifier == "E-freefall" else execute(identifier, settings)
        assert result["status"] == "COMPLETED_REVIEW_REQUIRED", result["validations"]
        assert result["solver_status"] == "COMPLETED" and all(m["valid"] for m in result["metrics"].values())
    ground = execute("E-ground-stop", specification("rigid_cube_ground_stop"))
    refined_settings = specification("rigid_cube_ground_stop")
    refined_settings.update(time_step_s=plan["refinement_dt_s"], history_interval_s=plan["refinement_dt_s"])
    finer = execute("E-ground-stop-finer", refined_settings)
    for result in (ground, finer):
        assert result["solver_status"] == "COMPLETED", result["validations"]
        assert not any(v["type"] == "native_history_integrity" and v["status"] == "FAIL" for v in result["validations"])
        assert (store / "experiments" / result["experiment_id"] / "simulation/parsed_history.json").is_file()
    invalid = deepcopy(specification())
    invalid["mass_kg"] = -1.
    rejected = execute("E-input-reject", invalid)
    assert rejected["status"] == "REJECTED" and rejected["solver_status"] == "NOT_RUN"
    assert not (store / "experiments/E-input-reject/simulation").exists()
    for identifier, original in retained.items():
        assert (store / "experiments" / identifier / "result.json").read_bytes() == original
        assert {"model_qualification", "physical_validation"} <= set(lab.research_summary(identifier)["unknown"])
    contact_pass = all(result["status"] == "COMPLETED_REVIEW_REQUIRED" for result in (ground, finer))
    report = {"status": "PASS" if contact_pass else "PARTIAL", "decision": "NOT_RELEASED",
              "freefall_sensitivity": "PASS", "ideal_ground_stop": "PASS" if contact_pass else "REJECTED",
              "invalid_input_admission": "PASS", "plan": plan,
              "experiments": {identifier: lab.research_summary(identifier) for identifier in results},
              "native": {identifier: {"provenance": result["provenance"]["solver"],
                                     "assessment": load_json(store / "experiments" / identifier / "simulation/analysis_raw.json")["assessment"],
                                     "history": {"sample_count": len(load_json(store / "experiments" / identifier / "simulation/parsed_history.json")["rows"]),
                                                 "native_cycle_count": load_json(store / "experiments" / identifier / "simulation/parsed_history.json")["native_cycle_count"]}}
                         for identifier, result in results.items() if result["solver_status"] == "COMPLETED"},
              "limitations": ["Freefall is a prerequisite, not completed impact/drop or the whole Phase6",
                              "Reduced nonrotating mainnode wall; rotating surface contact UNKNOWN",
                              "Reported native percent energy error is retained separately from absolute work closure",
                              "No physical/material/strength/fatigue/failure or finite peak qualification"]}
    save_json(store / "acceptance.json", report)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--store", type=Path, required=True)
    args = parser.parse_args()
    report = run(args.store)
    print(f"OpenRadioss acceptance: {report['status']} / freefall={report['freefall_sensitivity']} / contact={report['ideal_ground_stop']} / {report['decision']}")
    raise SystemExit(0 if report["status"] == "PASS" else 2)
