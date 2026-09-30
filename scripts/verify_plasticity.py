"""Actual displacement-controlled J2 acceptance in a new append-only store."""

import argparse
from copy import deepcopy
from pathlib import Path

from caelab import Lab
from caelab.adapters.codeaster_plasticity import CodeAsterPlasticityAdapter
from caelab.storage import canonical_hash, load_json, save_json, source_identity, utc_now


def specification():
    return {"case": "uniaxial_j2_isotropic_hardening", "dimensions_mm": [20., 4., 2.],
        "material": {"youngs_modulus_mpa": 210000., "poisson_ratio": .3,
                     "yield_stress_mpa": 250., "plastic_modulus_mpa": 1000.},
        "history": {"times_s": list(range(10)),
                    "axial_strain": [0., .0005, .001, .0015, .002, .003, .006, .0055, .005, .0045]},
        "mesh_sizes_mm": [2., 1.],
        "limits": {"displacement_relative": 1e-7, "displacement_absolute_mm": 1e-10,
                   "stress_relative": 1e-7, "stress_absolute_mpa": 1e-8, "plastic_strain_absolute": 1e-9,
                   "reaction_relative": 1e-7, "reaction_absolute_n": 1e-8, "mesh_agreement_relative": 1e-7,
                   "plastic_dissipation_relative": 1e-6, "plastic_dissipation_absolute_mpa": 1e-8}}


def changed_specification():
    """Separate predeclared nonzero-force input-effect case after draft02 failure."""
    request = specification()
    request["material"].update(yield_stress_mpa=225., plastic_modulus_mpa=1500.)
    return request


def changed_nonzero_reference(request: dict) -> dict:
    """Independent scalar arithmetic before any native process is started."""
    material = request["material"]
    young, yield_stress, hardening = (material[key] for key in
        ("youngs_modulus_mpa", "yield_stress_mpa", "plastic_modulus_mpa"))
    plastic, stresses, plastic_history = 0., [], []
    for strain in request["history"]["axial_strain"]:
        plastic = max(plastic, (young * strain - yield_stress) / (young + hardening))
        stresses.append(young * (strain - plastic))
        plastic_history.append(plastic)
    if any(stress == 0. for stress in stresses[1:]):
        raise ValueError("The separately declared input-effect case must have nonzero post-initial reference stress")
    return {"stress_history_mpa": stresses, "eq_plastic_strain_history": plastic_history,
            "nonzero_after_initial": True, "method": "Independent E/yield/H scalar closed return map"}


def run(store: Path) -> dict:
    store = Path(store)
    if store.exists():
        raise ValueError("Plasticity acceptance requires a new store; previous runs cannot be overwritten")
    adapter = CodeAsterPlasticityAdapter()
    lab = Lab(store, model_analysis_adapters={adapter.backend: adapter})
    lab.create_study("S-plasticity", "Small-strain J2 isotropic-hardening load/unload",
        "Does a declared nonlinear 3D block reproduce an independent return map at every history instant?",
        "Free Poisson directions yield a homogeneous J2 path followed by elastic unloading with retained plastic strain.",
        "Compare complete fields, signed reactions and derived plastic work without claiming physical material qualification.")
    frozen = specification()
    changed = changed_specification()
    changed_reference = changed_nonzero_reference(changed)
    report = {"status": "RUNNING", "started_utc": utc_now(), "settings": deepcopy(frozen),
              "changed_settings": deepcopy(changed), "changed_case_preflight": changed_reference,
              "source": source_identity(Path(__file__).resolve().parents[1]), "decision": "NOT_RELEASED",
              "cases": {}, "limitations": ["Material nonlinear benchmark only; contact/geometric nonlinearity remain open",
                  "No physical calibration, strength, fatigue or release qualification", "No assembled matrix residual/global energy balance"]}
    save_json(store / "acceptance_progress.json", report)
    try:
        for experiment, request in (("E-j2-canonical", frozen), ("E-j2-changed", changed)):
            print(f"Starting {experiment}: two real meshes and ten stored instants", flush=True)
            result = lab.run_model_analysis(study_id="S-plasticity", experiment_id=experiment,
                backend=adapter.backend, settings=request)
            report["cases"][experiment] = lab.research_summary(experiment)
            save_json(store / "acceptance_progress.json", report)
            assert result["status"] == "COMPLETED_REVIEW_REQUIRED", result["validations"]
            assert result["solver_status"] == "COMPLETED" and result["converged"] is True
            assert all(metric["valid"] for metric in result["metrics"].values())
            assert result["cad_revision"] is None and "parent_experiment_id" not in result
            assert result["decision"] == "NOT_RELEASED" and lab.inspect_experiment(experiment) == result
            proposal = load_json(store / f"experiments/{experiment}/proposal.json")
            assert proposal["model"]["geometry"]["type"] == "block" and proposal["model"]["materials"]
            assert result["model_revision"] == canonical_hash({"settings": request,
                "declaration": proposal["extensions"]["model_analysis"]["declaration"]})
            raw = load_json(store / f"experiments/{experiment}/simulation/analysis_raw.json")
            assert len(raw["mesh_records"]) == 2 and all(len(record["states"]) == 10 for record in raw["mesh_records"])
            assert all(len(record["nonlinear_convergence"]["increments"]) == 9 for record in raw["mesh_records"])
            known = (254.7867298578199, .004786729857819905, -60.2132701421801) if experiment == "E-j2-canonical" else (
                232.340425531915, .004893617021276595, -82.6595744680851)
            assert abs(result["metrics"]["peak_stress"]["value"] - known[0]) < 1e-4
            assert abs(result["metrics"]["peak_eq_plastic_strain"]["value"] - known[1]) < 1e-9
            assert abs(result["metrics"]["final_stress"]["value"] - known[2]) < 1e-4
        canonical_bytes = (store / "experiments/E-j2-canonical/result.json").read_bytes()
        canonical = lab.inspect_experiment("E-j2-canonical")
        changed = lab.inspect_experiment("E-j2-changed")
        assert canonical["model_revision"] != changed["model_revision"]
        assert abs(canonical["metrics"]["peak_stress"]["value"] - changed["metrics"]["peak_stress"]["value"]) > 20
        invalid_material = deepcopy(frozen)
        invalid_material["material"]["plastic_modulus_mpa"] = -1.
        invalid_history = deepcopy(frozen)
        invalid_history["history"]["axial_strain"][-1] = 0.
        for experiment, request in (("E-j2-material-reject", invalid_material), ("E-j2-history-reject", invalid_history)):
            result = lab.run_model_analysis(study_id="S-plasticity", experiment_id=experiment,
                backend=adapter.backend, settings=request)
            assert result["status"] == "REJECTED" and result["solver_status"] == "NOT_RUN"
            assert not (store / f"experiments/{experiment}/simulation").exists()
            assert lab.inspect_experiment(experiment)["decision"] == "NOT_RELEASED"
            report["cases"][experiment] = lab.research_summary(experiment)
        assert (store / "experiments/E-j2-canonical/result.json").read_bytes() == canonical_bytes
        report.update(status="PASS", finished_utc=utc_now(), provenance=canonical["provenance"])
        save_json(store / "acceptance.json", report)
        save_json(store / "acceptance_progress.json", report)
        return report
    except Exception as exc:
        report.update(status="FAILED", finished_utc=utc_now(), failure=f"{type(exc).__name__}: {exc}")
        save_json(store / "acceptance_progress.json", report)
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--store", type=Path, required=True)
    args = parser.parse_args()
    report = run(args.store)
    print(f"Plasticity acceptance: {report['status']} / {report['decision']}")
