"""Independent declared-model elasticity acceptance; no CAD parent is created."""

import argparse
from copy import deepcopy
from pathlib import Path

from caelab import Lab
from caelab.storage import canonical_hash, load_json, save_json


def specification():
    return {"case": "uniaxial_block", "dimensions_mm": [20.0, 4.0, 2.0],
            "material": {"youngs_modulus_mpa": 210000.0, "poisson_ratio": .3},
            "traction_mpa": 10.0, "mesh_sizes_mm": [2.0, 1.0],
            "limits": {"displacement_relative": 1e-8, "displacement_absolute_mm": 1e-12,
                       "stress_relative": 1e-8, "reaction_relative": 1e-8,
                       "mesh_agreement_relative": 1e-8}}


def run(store: Path):
    lab = Lab(store)
    lab.create_study("S-elasticity", "Independent 3D affine elasticity benchmark",
                     "Does a declared solid model reproduce the analytical displacement, stress and resultant?",
                     "Quadratic tetrahedra represent this constant-strain solution on both meshes.",
                     "Verify a second domain through common records without claiming strength qualification.")
    settings = specification()
    canonical = lab.run_model_analysis(study_id="S-elasticity", experiment_id="E-aster-affine",
                                      backend="structural.code_aster", settings=settings)
    assert canonical["status"] == "COMPLETED_REVIEW_REQUIRED", canonical["validations"]
    assert canonical["solver_status"] == "COMPLETED" and canonical["converged"] is True
    assert canonical["cad_revision"] is None and "parent_experiment_id" not in canonical
    assert canonical["model_revision"] == canonical["extensions"]["model_analysis"]["model_revision"]
    proposal = load_json(store / "experiments/E-aster-affine/proposal.json")
    assert proposal["model"]["geometry"]["type"] == "block"
    assert proposal["model"]["materials"] and proposal["boundary_conditions"] and proposal["loads"]
    assert proposal["model_revision"] == canonical_hash({"settings": settings,
        "declaration": proposal["extensions"]["model_analysis"]["declaration"]})
    assert lab.inspect_experiment("E-aster-affine") == canonical
    original = (store / "experiments/E-aster-affine/result.json").read_bytes()
    changed = deepcopy(settings)
    changed.update(dimensions_mm=[10.0, 4.0, 2.0], traction_mpa=2.0)
    changed["material"].update(youngs_modulus_mpa=1000.0, poisson_ratio=.25)
    second = lab.run_model_analysis(study_id="S-elasticity", experiment_id="E-aster-altered",
                                   backend="structural.code_aster", settings=changed)
    assert second["status"] == "COMPLETED_REVIEW_REQUIRED", second["validations"]
    assert second["model_revision"] != canonical["model_revision"]
    assert abs(second["metrics"]["axial_tip_displacement"]["value"] - .02) <= 1e-10
    invalid = deepcopy(settings)
    invalid["material"]["poisson_ratio"] = .5
    blocked = lab.run_model_analysis(study_id="S-elasticity", experiment_id="E-aster-input-reject",
                                    backend="structural.code_aster", settings=invalid)
    assert blocked["status"] == "REJECTED" and blocked["solver_status"] == "NOT_RUN"
    assert not (store / "experiments/E-aster-input-reject/simulation").exists()
    for result in (canonical, second, blocked):
        checked = lab.inspect_experiment(result["experiment_id"])
        assert checked["decision"] == "NOT_RELEASED"
        assert checked["cad_revision"] is None
        assert {"model_qualification", "physical_validation"} <= set(
            lab.research_summary(result["experiment_id"])["unknown"])
    assert (store / "experiments/E-aster-affine/result.json").read_bytes() == original
    report = {"status": "PASS", "decision": "NOT_RELEASED", "settings": settings,
              "canonical": lab.research_summary("E-aster-affine"),
              "changed": lab.research_summary("E-aster-altered"),
              "rejected": lab.research_summary("E-aster-input-reject"),
              "provenance": canonical["provenance"],
              "limitations": ["Affine patch test, no estimated mesh convergence rate",
                              "No assembled matrix residual measured",
                              "Assumed material and load; no physical or strength qualification"]}
    save_json(store / "acceptance.json", report)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--store", type=Path, required=True)
    args = parser.parse_args()
    report = run(args.store)
    print(f"Code_Aster declared-model acceptance: {report['status']} / {report['decision']}")
