"""Native material-point acceptance through the public declared-model operation."""

import argparse
from copy import deepcopy
from pathlib import Path

from caelab import Lab
from caelab.adapters.mfront_material import MFrontMaterialAdapter, WORKER, sha256
from caelab.storage import canonical_hash, load_json, save_json, source_identity
from plugins.material_point import reference


def run(store):
    store = Path(store)
    if store.exists():
        raise ValueError("Native acceptance requires a fresh store; preserve every prior attempt")
    identity = source_identity(Path(__file__).resolve().parents[1])
    if identity.get("core_commit") in (None, "unavailable") or identity.get("core_dirty") is None:
        raise RuntimeError("Exact worktree source identity is unavailable; configure the Windows Git bridge in WSL")
    adapter = MFrontMaterialAdapter()
    lab = Lab(store, model_analysis_adapters={adapter.backend: adapter})
    lab.create_study("S-material-point", "MFront isotropic material-point benchmark",
        "Do real MGIS and MTest observations match an independent Hooke law and every finite-difference tangent?",
        "The fixed generic 3D behavior reproduces the declared small-strain history and Kelvin tangent",
        "Constitutive numerical verification only; material, physical and solver coupling qualification stay UNKNOWN")
    frozen = reference.canonical_settings()
    save_json(store / "frozen_acceptance.json", {"settings": frozen, "source_identity": identity,
        "settings_sha256": canonical_hash(frozen), "worker_sha256": sha256(WORKER),
        "plugin_sha256": sha256(Path(reference.__file__)),
        "adapter_sha256": sha256(Path(__file__).resolve().parents[1] / "caelab/adapters/mfront_material.py"),
        "script_sha256": sha256(__file__), "changed_modulus_mpa": 105000.,
        "gate": "Every integration return=1, both tensor bases, every FD h/column, same-binary MTest full stress history"})
    report = {"status": "FAIL", "decision": "NOT_RELEASED", "settings": frozen, "source_identity": identity,
              "cases": {}, "limitations": list(reference.PENDING)}
    try:
        canonical = lab.run_model_analysis(study_id="S-material-point", experiment_id="E-material-canonical",
            backend=adapter.backend, settings=deepcopy(frozen))
        report["cases"]["canonical"] = lab.research_summary("E-material-canonical")
        assert canonical["status"] == "COMPLETED_REVIEW_REQUIRED", canonical["validations"]
        assert canonical["converged"] is True and canonical["solver_status"] == "COMPLETED"
        folder = store / "experiments/E-material-canonical"
        original = (folder / "result.json").read_bytes()
        proposal = load_json(folder / "proposal.json")
        assert proposal["model"]["geometry"] is None and proposal["model"]["mesh"] is None
        assert proposal["model"]["materials"] and proposal["loads"] and proposal["initial_conditions"]
        assert canonical["model_revision"] == canonical_hash({"settings": frozen,
            "declaration": proposal["extensions"]["model_analysis"]["declaration"]})
        assert lab.inspect_experiment("E-material-canonical") == canonical
        changed = deepcopy(frozen)
        changed["material"]["youngs_modulus_mpa"] = 105000.
        second = lab.run_model_analysis(study_id="S-material-point", experiment_id="E-material-changed-modulus",
            backend=adapter.backend, settings=changed)
        report["cases"]["changed_modulus"] = lab.research_summary("E-material-changed-modulus")
        assert second["status"] == "COMPLETED_REVIEW_REQUIRED", second["validations"]
        assert second["model_revision"] != canonical["model_revision"]
        for a, b in zip(canonical["metrics"]["stress_history"]["value"], second["metrics"]["stress_history"]["value"]):
            assert all(abs(y - x / 2) <= 1e-10 for x, y in zip(a, b))
        invalid = deepcopy(frozen)
        invalid["material"]["poisson_ratio"] = .5
        blocked = lab.run_model_analysis(study_id="S-material-point", experiment_id="E-material-input-reject",
            backend=adapter.backend, settings=invalid)
        report["cases"]["invalid_input"] = lab.research_summary("E-material-input-reject")
        assert blocked["status"] == "REJECTED" and blocked["solver_status"] == "NOT_RUN"
        assert not (store / "experiments/E-material-input-reject/simulation").exists()
        for result in (canonical, second, blocked):
            identifier = result["experiment_id"]
            assert lab.inspect_experiment(identifier) == result
            assert result["decision"] == "NOT_RELEASED" and result["cad_revision"] is None
            assert "parent_experiment_id" not in result
            assert {"model_qualification", "physical_validation"} <= set(lab.research_summary(identifier)["unknown"])
            assert load_json(store / "experiments" / identifier / "thread.json")["model_revision"] == result["model_revision"]
        assert (folder / "result.json").read_bytes() == original
        report.update(status="PASS", provenance=canonical["provenance"],
                      changed_provenance=second["provenance"],
                      metrics=canonical["metrics"], changed_metrics=second["metrics"])
        return report
    except Exception as exc:
        report["failure"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        save_json(store / "acceptance.json", report)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--store", type=Path, required=True)
    args = parser.parse_args()
    report = run(args.store)
    print(f"Native material-point acceptance: {report['status']} / {report['decision']}")
