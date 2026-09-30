"""Fresh-store nonlinear manufactured proof; no physical qualification claim."""

import argparse
from copy import deepcopy
import hashlib
import math
from pathlib import Path

from caelab import Lab
from caelab.adapters.fenicsx_nonlinear import FenicsxNonlinearPDEAdapter
from caelab.adapters.fenicsx_pde import FenicsxPDEAdapter
from caelab.adapters.fenicsx_nonlinear_worker import NATIVE_OPTIONS
from caelab.storage import load_json, save_json, utc_now
from plugins.pde_nonlinear.reference import manufactured_settings, source_value


def _require(condition, description):
    if not condition:
        raise AssertionError(description)


def _checked(lab, experiment):
    result = lab.inspect_experiment(experiment)
    _require(result["decision"] == "NOT_RELEASED" and result["cad_revision"] is None and
             "parent_experiment_id" not in result, "PDE proof must have no CAD parent or release")
    _require({"model_qualification", "physical_validation"} <=
             set(lab.research_summary(experiment)["unknown"]), "Qualification must remain UNKNOWN")
    return result


def run(store: Path) -> dict:
    store = Path(store).resolve()
    if store.exists():
        raise ValueError("Acceptance requires a fresh store; previous attempts cannot be overwritten")
    started = utc_now()
    nonlinear = FenicsxNonlinearPDEAdapter()
    linear = FenicsxPDEAdapter()
    lab = Lab(store, pde_adapters={nonlinear.backend: nonlinear, linear.backend: linear})
    lab.create_study("S-nonlinear-pde", "Bounded nonlinear manufactured scalar weak form",
                     "Does q(u)=1+alpha*u² reproduce its independent manufactured solution and alpha=0 limit?",
                     "P1 errors converge at L2 order2/H1 seminorm order1 while actual Newton residuals meet both gates.",
                     "Keep source, full Newton histories and fields as mathematical evidence; no physical release.")
    settings = {alpha: manufactured_settings(alpha) for alpha in (1., 0., 2.)}
    # All specifications and limits are persisted before the first solver.
    save_json(store / "frozen_plan.json", {"schema_version": "1", "recorded_utc": started,
              "cases": {str(alpha): request for alpha, request in settings.items()},
              "independent_source_at_center": {str(alpha): source_value(alpha, .5, .5) for alpha in settings},
              "newton_policy": {"absolute": 1e-10, "relative": 1e-10, "max_iterations": 25,
                                "verdict": "BOTH absolute and relative, plus independent constrained residual",
                                "native_options": NATIVE_OPTIONS, "petsc_rc_disabled": True,
                                "excluded_environment_options": ["PETSC_OPTIONS", "PETSC_OPTIONS_YAML"]},
              "linear_limit_max_dof_difference": 1e-10,
              "linear_backend_max_metric_difference": 1e-10,
              "limitations": ["alpha in[0,2], scalar unit square, P1, serial only",
                              "Mathematical manufactured proof is not model/physical qualification."]})
    accepted, raw_cases = {}, {}
    for alpha, experiment in ((1., "E-nonlinear-alpha1"), (0., "E-nonlinear-alpha0"), (2., "E-nonlinear-alpha2")):
        result = lab.run_pde(study_id="S-nonlinear-pde", experiment_id=experiment,
                             backend=nonlinear.backend, settings=settings[alpha])
        _require(result["status"] == "COMPLETED_REVIEW_REQUIRED", result["validations"])
        _require(all(metric["valid"] for metric in result["metrics"].values()), "All nonlinear metrics must be valid")
        accepted[experiment] = _checked(lab, experiment)
        raw_cases[experiment] = load_json(store / "experiments" / experiment / "pde/worker_result.json")
        for row in raw_cases[experiment]["mesh_studies"]:
            _require(row["newton"]["iterations"] <= 25 and row["newton"]["convergence_reason"] > 0,
                     "Actual Newton reason/iteration cap failed")
            _require(row["newton"]["final_residual"] <= 1e-10 and row["newton"]["relative_residual"] <= 1e-10,
                     "Both frozen Newton criteria must pass")
            _require(row["nonlinear_residual"]["absolute"] <= 1e-10 and
                     row["nonlinear_residual"]["relative"] <= 1e-10,
                     "Independent constrained residual must pass")
    baseline = deepcopy(settings[0.])
    baseline["problem"]["weak_form"] = {"diffusion": 1.0, "reaction": 0.0,
                                             "rhs": baseline["problem"]["weak_form"]["rhs"]}
    baseline["validation"] = {key: baseline["validation"][key]
                              for key in ("max_l2_error", "min_l2_rate", "max_residual_relative")}
    result = lab.run_pde(study_id="S-nonlinear-pde", experiment_id="E-linear-existing",
                         backend=linear.backend, settings=baseline)
    _require(result["status"] == "COMPLETED_REVIEW_REQUIRED", result["validations"])
    accepted["E-linear-existing"] = _checked(lab, "E-linear-existing")
    linear_raw = load_json(store / "experiments/E-linear-existing/pde/worker_result.json")
    comparison = []
    for nonlin, old in zip(raw_cases["E-nonlinear-alpha0"]["mesh_studies"], linear_raw["mesh_studies"]):
        differences = {}
        for metric in ("l2_error", "h1_seminorm_error", "l2_convergence_rate", "h1_seminorm_convergence_rate"):
            difference = None if nonlin[metric] is None and old[metric] is None else abs(nonlin[metric] - old[metric])
            _require(difference is None or difference <= 1e-10, "alpha=0 differs from existing linear backend")
            differences[metric] = difference
        _require(nonlin["linear_comparison"]["max_dof_difference"] <= 1e-10, "alpha=0 native field limit differs")
        comparison.append({"cells_per_axis": nonlin["cells_per_axis"], "metric_differences": differences,
                           "same_dof_linear_max_difference": nonlin["linear_comparison"]["max_dof_difference"]})
    first = accepted["E-nonlinear-alpha1"]
    second = accepted["E-nonlinear-alpha2"]
    _require(first["model_revision"] != second["model_revision"], "Changed alpha must change frozen model revision")
    field_a = load_json(store / "experiments/E-nonlinear-alpha1/pde/level_n8/dofs.json")
    field_b = load_json(store / "experiments/E-nonlinear-alpha2/pde/level_n8/dofs.json")
    _require(field_a["node_ids"] == field_b["node_ids"] and field_a["coordinates"] == field_b["coordinates"],
             "Changed-alpha field identities must match before comparison")
    effect = max(abs(a - b) for a, b in zip(field_a["values"], field_b["values"]))
    _require(effect > 1e-12, "Changed alpha did not affect the actual discrete field")
    original = (store / "experiments/E-nonlinear-alpha1/result.json").read_bytes()
    wrong_reference = deepcopy(settings[1.])
    wrong_reference["problem"]["reference"] = {"solution": "0.0",
        "source": "Intentionally incorrect reference for finite numerical rejection acceptance"}
    rejected = lab.run_pde(study_id="S-nonlinear-pde", experiment_id="E-nonlinear-reference-reject",
                           backend=nonlinear.backend, settings=wrong_reference)
    _require(rejected["status"] == "REJECTED" and rejected["solver_status"] == "COMPLETED" and
             rejected["converged"] is True and all(not metric["valid"] for metric in rejected["metrics"].values()),
             "Wrong reference must retain the converged field with invalid metrics")
    _checked(lab, rejected["experiment_id"])
    blocked = []
    for name, bad_value in (("coefficient", -1.), ("boolean", True), ("expression", "__import__('os').getcwd()")):
        invalid = deepcopy(settings[1.])
        invalid["problem"]["weak_form"]["rhs" if name == "expression" else "alpha"] = bad_value
        experiment = "E-nonlinear-invalid-" + name
        result = lab.run_pde(study_id="S-nonlinear-pde", experiment_id=experiment,
                             backend=nonlinear.backend, settings=invalid)
        _require(result["status"] == "REJECTED" and result["solver_status"] == "NOT_RUN" and
                 not (store / "experiments" / experiment / "pde/command.json").exists(),
                 "Invalid coefficient/expression must block system Python")
        _checked(lab, experiment)
        blocked.append(experiment)
    _require((store / "experiments/E-nonlinear-alpha1/result.json").read_bytes() == original,
             "Later runs must not change an earlier experiment")
    report = {"schema_version": "1", "status": "PASS", "decision": "NOT_RELEASED", "started_utc": started,
              "finished_utc": utc_now(), "backend": nonlinear.backend, "settings": {str(k): v for k, v in settings.items()},
              "accepted_experiments": list(accepted), "numerical_rejection": rejected["experiment_id"],
              "preflight_rejections": blocked, "existing_linear_comparison": comparison,
              "alpha1_alpha2_coarse_field_max_difference": effect,
              "cases": {experiment: {"metrics": accepted[experiment]["metrics"], "versions": raw["versions"],
                                      "mesh_studies": raw["mesh_studies"]} for experiment, raw in raw_cases.items()},
              "source": {key: first["provenance"][key] for key in
                         ("core_commit", "core_dirty", "core_source_sha256")},
              "frozen_source": first["provenance"]["adapter_details"]["source_sha256"],
              "limitations": ["Scalar q=1+alpha*u² on unit square with alpha[0,2], constant all-boundary data, P1 only.",
                              "Serial mathematical benchmark; general nonlinear PDE/MPI/physical qualification remain open."]}
    save_json(store / "nonlinear_pde_acceptance.json", report)
    print(f"PASS: alpha1/0/2, existing linear limit, finite numerical rejection and3 preflight rejections; NOT_RELEASED")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--store", type=Path, required=True)
    run(parser.parse_args().store)
