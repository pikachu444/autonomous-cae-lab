"""Fresh native reduced conservative-stop benchmark; no arbitrary solver deck."""

import argparse
from copy import deepcopy
from pathlib import Path

from caelab import Lab
from caelab.adapters.openradioss import OpenRadiossAdapter, runtime
from caelab.storage import load_json, save_json, source_identity
from plugins.explicit_dynamics.reference import reference


def specification(*, stiffness=10000., time_step=1e-4):
    return {"case": "rigid_cube_compliant_stop", "edge_m": .1, "mass_kg": 1.,
            "center_height_m": 1., "gravity_m_s2": 9.81, "initial_velocity_m_s": 0.,
            "spring_stiffness_n_m": stiffness, "spring_mass_kg": .002,
            "end_time_s": .5, "time_step_s": time_step, "history_interval_s": time_step,
            "limits": {"displacement_abs_m": 2e-4, "velocity_abs_m_s": .002, "energy_abs_j": .01,
                       "mass_relative": 1e-8, "impact_time_abs_s": 2e-4, "impulse_abs_n_s": .005,
                       "force_abs_n": 2., "restitution_abs": .001}}


def run(store):
    store = Path(store)
    if store.exists():
        raise ValueError("Compliant acceptance requires a fresh store; preserve every old attempt")
    source = source_identity(Path(__file__).resolve().parents[1])
    if source.get("core_dirty"):
        raise ValueError("Freeze and locally commit source before native compliant acceptance")
    runtime()
    cases = {"E-compliant": specification(), "E-compliant-finer": specification(time_step=5e-5),
             "E-compliant-stiffer": specification(stiffness=20000., time_step=5e-5)}
    plan = {"cases": cases, "source": source, "threshold_changes_allowed": False,
            "clock": "Actual FX/LX/IE/Z at TIME; incoming raw V at TIME-dt/2; centered momentum at TIME",
            "native_card": {"spring_type": 4, "h1": 8, "anchor_node": 10, "anchor_z_m": -1,
                "rigid_main_node": 9, "moving_attachment_node": 11, "contact_center_z_m": .05, "absolute_rest_length_m": 1.05,
                "spring_initial_length_m": 2, "local_force_sign": "upward on rigidly attached center11 = -FX",
                "mass": {"cube_kg": 1, "spring_kg": .002, "moving_kg": 1.001, "fixed_kg": .001, "total_kg": 1.002}},
            "resources": {"omp_threads": 2, "address_space_bytes": 2 * 1024 ** 3,
                "cpu_seconds": 60, "process_wall_seconds": 90, "max_requested_cycles": 200000,
                "max_history_samples_exclusive": 20000},
            "references": {key: reference(settings, settings["end_time_s"]) for key, settings in cases.items()},
            "admission": ["invalid cube mass", "invalid/nonpositive stiffness", "actual Starter warnings/errors or mass mismatch"],
            "scope": "Reduced finite-force conservative constitutive benchmark; existing ideal-wall failures unchanged"}
    save_json(store / "acceptance_plan.json", plan)
    adapter = OpenRadiossAdapter()
    lab = Lab(store, adapters={}, analysis_adapters={}, doe_adapters={}, optimization_adapters={},
              pde_adapters={}, model_analysis_adapters={adapter.backend: adapter})
    lab.create_study("S-compliant-drop", "Known conservative reduced contact and rebound",
        "Does native spring force, length and IE reproduce a declared finite-force unilateral law?",
        "Complete contact/rebound, energy, momentum and restitution follow the independent closed form under timestep refinement and stiffness change.",
        "Keep surface-contact, physical/material, strength and failure qualification UNKNOWN and retain rejected histories.")
    results, retained, native = {}, {}, {}
    for identifier, settings in cases.items():
        result = lab.run_model_analysis(study_id="S-compliant-drop", experiment_id=identifier,
                                        backend=adapter.backend, settings=settings)
        assert lab.inspect_experiment(identifier) == result
        assert result["cad_revision"] is None and "parent_experiment_id" not in result
        assert result["decision"] == "NOT_RELEASED"
        results[identifier] = result
        path = store / "experiments" / identifier
        retained[identifier] = (path / "result.json").read_bytes()
        raw = load_json(path / "simulation/analysis_raw.json") if (path / "simulation/analysis_raw.json").is_file() else None
        parsed = load_json(path / "simulation/parsed_history.json") if (path / "simulation/parsed_history.json").is_file() else None
        native[identifier] = {"provenance": result["provenance"].get("solver"),
                             "assessment": raw.get("assessment") if raw else None,
                             "starter_admission": load_json(path / "simulation/starter_admission.json") if (path / "simulation/starter_admission.json").is_file() else None,
                             "history": {"sample_count": len(parsed["rows"]), "native_cycle_count": parsed["native_cycle_count"],
                                         "hierarchy": parsed["hierarchy"], "groups": parsed["groups"]} if parsed else None}
    for identifier, key, value in (("E-invalid-mass", "mass_kg", -1.), ("E-invalid-stiffness", "spring_stiffness_n_m", 0.)):
        settings = deepcopy(specification()); settings[key] = value
        result = lab.run_model_analysis(study_id="S-compliant-drop", experiment_id=identifier,
                                        backend=adapter.backend, settings=settings)
        assert result["status"] == "REJECTED" and result["solver_status"] == "NOT_RUN"
        assert not (store / "experiments" / identifier / "simulation").exists()
        assert lab.inspect_experiment(identifier) == result
        results[identifier] = result
        retained[identifier] = (store / "experiments" / identifier / "result.json").read_bytes()
    for identifier, original in retained.items():
        assert (store / "experiments" / identifier / "result.json").read_bytes() == original
        unknown = set(lab.research_summary(identifier)["unknown"])
        assert {"physical_validation", "model_qualification"} <= unknown
        if identifier in cases:
            assert "material_qualification" in unknown
    passed = all(results[key]["status"] == "COMPLETED_REVIEW_REQUIRED" and
                 results[key]["solver_status"] == "COMPLETED" and
                 all(value["valid"] for value in results[key]["metrics"].values()) for key in cases)
    report = {"status": "PASS" if passed else "REJECTED", "decision": "NOT_RELEASED",
        "reduced_compliant_constitutive_contact": "PASS" if passed else "REJECTED",
        "invalid_input_admission": "PASS", "plan": plan, "native": native,
        "experiments": {key: lab.research_summary(key) for key in results},
        "limitations": ["Known conservative one-DOF spring stop; surface contact and qualified physical contact laws UNKNOWN",
                        "Numerical finite-force/rebound proof is not strength, failure, physical qualification or completion of Phase6",
                        "Previous ideal-wall cases remain REJECTED in their original retained stores"]}
    save_json(store / "acceptance.json", report)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--store", type=Path, required=True)
    report = run(parser.parse_args().store)
    print(f"OpenRadioss reduced compliant contact: {report['status']} / {report['decision']}")
    raise SystemExit(0 if report["status"] == "PASS" else 2)
