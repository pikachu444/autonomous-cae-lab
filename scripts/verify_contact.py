"""Fresh SSNP121A contact acceptance through the existing common model route.

Original six signed sample criteria stay1%; additional equilibrium stays1e-6.
This does not qualify NAFEMS CGS1, pointwise gap, a fixture joint or strength.
"""
import argparse
from copy import deepcopy
from pathlib import Path

from caelab import Lab
from caelab.storage import canonical_hash, load_json, save_json


BACKEND = "structural.code_aster.contact_patch"


def specification():
    return {"case": "ssnp121a_frictionless_patch",
            "material": {"youngs_modulus_pa": 2e6, "poisson_ratio": 0.0},
            "top_displacement_m": -0.1,
            "limits": {"reference_relative": 0.01, "force_balance_relative": 1e-6}}


def run(store: Path):
    store = Path(store)
    if store.exists():
        raise FileExistsError("Contact acceptance requires a new store; historical experiments stay preserved")
    lab = Lab(store)
    lab.create_study("S-contact-patch", "Official SSNP121A frictionless contact patch",
                     "Does actual nonmatching two-block contact recover signed pressure, displacement and equilibrium?",
                     "The published nu0 analytical solution applies to the fixed original native mesh.",
                     "Verify a bounded contact foundation through common records; keep physical and fixture qualification UNKNOWN.")
    settings = specification()
    canonical = lab.run_model_analysis(study_id="S-contact-patch", experiment_id="E-ssnp121a-canonical",
                                      backend=BACKEND, settings=settings)
    assert canonical["status"] == "COMPLETED_REVIEW_REQUIRED", canonical["validations"]
    assert canonical["solver_status"] == "COMPLETED" and canonical["converged"] is True
    assert canonical["cad_revision"] is None and "parent_experiment_id" not in canonical
    proposal = load_json(store / "experiments/E-ssnp121a-canonical/proposal.json")
    assert proposal["model"]["interfaces"] and proposal["model"]["contact"]
    assert canonical["model_revision"] == canonical_hash({"settings": settings,
        "declaration": proposal["extensions"]["model_analysis"]["declaration"]})
    assert lab.inspect_experiment("E-ssnp121a-canonical") == canonical
    original = (store / "experiments/E-ssnp121a-canonical/result.json").read_bytes()
    changed = deepcopy(settings)
    changed["material"]["youngs_modulus_pa"] = 1e6
    changed["top_displacement_m"] = -0.05
    altered = lab.run_model_analysis(study_id="S-contact-patch", experiment_id="E-patch-analytical-variant",
                                    backend=BACKEND, settings=changed)
    assert altered["status"] == "COMPLETED_REVIEW_REQUIRED", altered["validations"]
    assert altered["model_revision"] != canonical["model_revision"]
    invalid = deepcopy(settings)
    invalid["material"]["poisson_ratio"] = False
    blocked = lab.run_model_analysis(study_id="S-contact-patch", experiment_id="E-contact-input-reject",
                                    backend=BACKEND, settings=invalid)
    assert blocked["status"] == "REJECTED" and blocked["solver_status"] == "NOT_RUN"
    assert not (store / "experiments/E-contact-input-reject/simulation").exists()
    for result in (canonical, altered, blocked):
        assert result["decision"] == "NOT_RELEASED" and result["cad_revision"] is None
        assert lab.inspect_experiment(result["experiment_id"]) == result
        assert {"model_qualification", "physical_validation"} <= set(
            lab.research_summary(result["experiment_id"])["unknown"])
    assert (store / "experiments/E-ssnp121a-canonical/result.json").read_bytes() == original
    report = {"status": "PASS", "decision": "NOT_RELEASED", "settings": settings,
              "canonical": lab.research_summary("E-ssnp121a-canonical"),
              "analytical_variant": lab.research_summary("E-patch-analytical-variant"),
              "rejected": lab.research_summary("E-contact-input-reject"),
              "limitations": ["Original fixed MED; no measured mesh convergence or cross-solver proof",
                              "SSNP121A is distinct from NAFEMS CGS1",
                              "Projected gaps are derived, not native gap qualification",
                              "Full real fixture/material/physical/strength/durability remain UNKNOWN"]}
    save_json(store / "acceptance.json", report)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--store", type=Path, required=True)
    args = parser.parse_args()
    report = run(args.store)
    print(f"SSNP121A contact acceptance: {report['status']} / {report['decision']}")
