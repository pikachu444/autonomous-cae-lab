"""Canonical analytical weak-form proof, user form change and numerical rejection."""

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path

from caelab import Lab
from caelab.storage import load_json, save_json


def specification():
    return {"problem": {"domain": "unit_square",
                        "weak_form": {"diffusion": 1.0, "reaction": 0.0,
                                      "rhs": "2*pi**2*sin(pi*x[0])*sin(pi*x[1])"},
                        "dirichlet": "0.0",
                        "reference": {"solution": "sin(pi*x[0])*sin(pi*x[1])",
                                      "source": "Analytical manufactured solution on the dimensionless unit square"}},
            "mesh": {"cell_counts": [8, 16, 32], "degree": 1},
            "validation": {"max_l2_error": .003, "min_l2_rate": 1.8, "max_residual_relative": 1e-10}}


def run(store: Path):
    lab = Lab(store)
    lab.create_study("S-pde", "Canonical declared weak-form benchmark",
                     "Does the scalar weak form converge to its manufactured solution?",
                     "P1 L2 error decreases at approximately second order.",
                     "Verify analytical error and preserve fields without claiming physical qualification.")
    spec = specification()
    canonical = lab.run_pde(study_id="S-pde", experiment_id="E-pde-poisson",
                            backend="pde.fenicsx", settings=spec)
    assert canonical["status"] == "COMPLETED_REVIEW_REQUIRED", canonical["validations"]
    assert canonical["cad_revision"] is None and "parent_experiment_id" not in canonical
    assert canonical["metrics"]["l2_error"]["valid"] is True
    assert canonical["metrics"]["l2_error"]["value"] <= .003
    assert canonical["metrics"]["l2_convergence_rate"]["value"] >= 1.8
    assert canonical["metrics"]["linear_residual_relative"]["value"] <= 1e-10
    assert {"model_qualification", "physical_validation"} <= set(lab.research_summary("E-pde-poisson")["unknown"])
    raw = load_json(store / "experiments/E-pde-poisson/pde/worker_result.json")
    assert [row["cells_per_axis"] for row in raw["mesh_studies"]] == [8, 16, 32]
    assert all(row["ksp_convergence_reason"] > 0 for row in raw["mesh_studies"])
    assert raw["mesh_studies"][-1]["h1_seminorm_convergence_rate"] > .9
    assert lab.inspect_experiment("E-pde-poisson") == canonical
    original = (store / "experiments/E-pde-poisson/result.json").read_bytes()
    reaction = deepcopy(spec)
    reaction["problem"]["weak_form"].update(reaction=3.0,
        rhs="(2*pi**2+3)*sin(pi*x[0])*sin(pi*x[1])")
    second = lab.run_pde(study_id="S-pde", experiment_id="E-pde-reaction",
                         backend="pde.fenicsx", settings=reaction)
    assert second["status"] == "COMPLETED_REVIEW_REQUIRED", second["validations"]
    assert second["extensions"]["pde"]["model_revision"] != canonical["extensions"]["pde"]["model_revision"]
    bad_reference = deepcopy(spec)
    bad_reference["problem"]["reference"] = {"solution": "0.0", "source": "Intentionally incorrect reference for rejection acceptance"}
    rejected = lab.run_pde(study_id="S-pde", experiment_id="E-pde-reference-reject",
                           backend="pde.fenicsx", settings=bad_reference)
    assert rejected["solver_status"] == "COMPLETED" and rejected["status"] == "REJECTED"
    assert rejected["metrics"]["l2_error"]["valid"] is False
    assert rejected["metrics"]["l2_error"]["value"] > spec["validation"]["max_l2_error"]
    invalid = deepcopy(spec)
    invalid["problem"]["weak_form"]["rhs"] = "__import__('os').getcwd()"
    blocked = lab.run_pde(study_id="S-pde", experiment_id="E-pde-input-reject",
                          backend="pde.fenicsx", settings=invalid)
    assert blocked["status"] == "REJECTED" and blocked["solver_status"] == "NOT_RUN"
    assert not (store / "experiments/E-pde-input-reject/pde/command.json").exists()
    for experiment in (canonical, second, rejected, blocked):
        assert lab.inspect_experiment(experiment["experiment_id"])["decision"] == "NOT_RELEASED"
    assert (store / "experiments/E-pde-poisson/result.json").read_bytes() == original
    report = {"status": "PASS", "decision": "NOT_RELEASED", "canonical_experiment_id": "E-pde-poisson",
              "weak_form": spec["problem"], "limits": spec["validation"],
              "mesh_studies": raw["mesh_studies"], "versions": raw["versions"],
              "metrics": canonical["metrics"], "reaction_form_metrics": second["metrics"],
              "numerical_rejection": "E-pde-reference-reject", "preflight_rejection": "E-pde-input-reject",
              "source": {k: canonical["provenance"][k] for k in ("core_commit", "core_dirty", "core_source_sha256")},
              "artifact_hashes": {a["path"]: a["sha256"] for a in canonical["artifacts"]},
              "result_sha256": hashlib.sha256(original).hexdigest(),
              "limitations": ["Bounded scalar linear elliptic forms on a dimensionless unit square only.",
                              "Serial execution does not establish MPI/HPC acceptance.",
                              "Analytical mathematical proof does not qualify a physical model."]}
    save_json(store / "pde_acceptance.json", report)
    print(json.dumps({k: v for k, v in report.items() if k not in ("artifact_hashes", "mesh_studies")}))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--store", type=Path, required=True)
    run(parser.parse_args().store.resolve())
