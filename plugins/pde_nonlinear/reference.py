"""Pure reference and numerical verdict for -div((1+alpha*u²)*grad(u))=f.

The declared capability is a real scalar, dimensionless unit square with P1
triangles and constant whole-boundary Dirichlet data. Existing bounded
expressions are reused, never evaluated as Python. The manufactured source
has an independent direct-divergence evaluator. Native fields and coordinates
remain the adapter's responsibility, and numerical agreement never qualifies
an engineering model or physical experiment.
"""

from __future__ import annotations

import copy
import math

if __name__ == "domain_reference":
    # The adapter loads its preserved source under this fixed trusted name.
    # A globally installed caelab must not replace the frozen helper copy.
    from fenicsx_expression import (PDEInputError, constant_expression, error_rate,
                                    finite_number, interpret_expression, parse_expression,
                                    validate_settings as _linear_settings)
else:
    from caelab.adapters.fenicsx_worker import (PDEInputError, constant_expression,
                                               error_rate, finite_number, interpret_expression,
                                               parse_expression, validate_settings as _linear_settings)


VERSION = "1"
NEWTON_RTOL = 1e-10
NEWTON_ATOL = 1e-10
NEWTON_MAX_ITERATIONS = 25
BOUNDARY_ATOL = 1e-12
LINEAR_COMPARISON_ATOL = 1e-10
_CONSISTENCY_ATOL = 1e-12
_VALIDATION_KEYS = {"max_l2_error", "min_l2_rate", "max_h1_seminorm_error",
                    "min_h1_rate", "max_residual_relative"}
_RECORD_KEYS = {"cells_per_axis", "degree", "global_cells", "global_dofs", "dirichlet_dofs",
                "boundary_value_error", "l2_error", "h1_seminorm_error", "l2_convergence_rate",
                "h1_seminorm_convergence_rate", "nonlinear_residual", "newton"}
_NEWTON_KEYS = {"convergence_reason", "iterations", "initial_residual", "final_residual",
                "relative_residual", "history", "native_options"}
_NATIVE_OPTIONS = {"snes_type": "newtonls", "snes_linesearch_type": "none",
                   "snes_linesearch_damping": 1.0,
                   "snes_rtol": NEWTON_RTOL, "snes_atol": NEWTON_ATOL, "snes_stol": 0.0,
                   "snes_max_it": NEWTON_MAX_ITERATIONS, "ksp_type": "preonly", "pc_type": "lu",
                   "ksp_error_if_not_converged": True}
_EFFECTIVE_OPTIONS = {"snes_type": "newtonls", "rtol": NEWTON_RTOL, "atol": NEWTON_ATOL,
                      "stol": 0.0, "max_iterations": NEWTON_MAX_ITERATIONS,
                      "ksp_type": "preonly", "pc_type": "lu",
                      "line_search_type": "none", "line_search_damping": 1.0}
_PENDING = ["model_qualification", "physical_validation"]
_LIMITATIONS = [
    "Dimensionless unit square, real scalar P1 triangles and constant Dirichlet data on the entire boundary.",
    "Only solution-dependent diffusion 1+alpha*u^2 with 0<=alpha<=2 is admitted; it is uniformly positive.",
    "Bounded mathematical expressions reuse the existing scalar parser; general nonlinear or coupled PDEs are not covered.",
    "Errors must be measured against the symbolic reference; H1 is the gradient seminorm, not the full H1 norm.",
    "Every mesh pair must pass the declared L2 and H1 rates; theoretical P1 orders are 2 and 1 for this smooth benchmark.",
    "Acceptance requires both absolute and initial-relative Newton residual limits, including an independent residual recomputation.",
    "Numerical reference agreement and a positive solver reason do not qualify a model or physical experiment.",
]


def _keys(value: object, expected: set[str], label: str) -> dict:
    if not isinstance(value, dict) or set(value) != expected:
        raise PDEInputError(f"{label} requires exactly these fields: {', '.join(sorted(expected))}")
    return value


def _required(value: object, expected: set[str], label: str) -> dict:
    if not isinstance(value, dict) or not expected <= set(value):
        raise PDEInputError(f"{label} is missing required fields: {', '.join(sorted(expected))}")
    return value


def _number(value: object, label: str, *, nonnegative: bool = False) -> float:
    if not finite_number(value, nonnegative=nonnegative):
        raise PDEInputError(f"{label} must be finite{' and nonnegative' if nonnegative else ''}")
    return float(value)


def _integer(value: object, label: str, *, nonnegative: bool = False, positive: bool = False) -> int:
    if type(value) is not int or (nonnegative and value < 0) or (positive and value <= 0):
        raise PDEInputError(f"{label} must be an integer with the required sign")
    return value


def _alpha(value: object) -> float:
    alpha = _number(value, "alpha")
    if not 0.0 <= alpha <= 2.0:
        raise PDEInputError("alpha must satisfy 0 <= alpha <= 2")
    return alpha


def validate_settings(settings: dict) -> dict:
    """Normalize a deep independent request by projecting onto the old parser.

    This adds no expression language or mesh family: the existing linear PDE
    validator still owns AST safety, constant boundary data, source metadata,
    increasing doubling meshes and degree-1 restrictions.
    """
    _keys(settings, {"problem", "mesh", "validation"}, "Nonlinear PDE settings")
    problem = _keys(settings["problem"], {"domain", "weak_form", "dirichlet", "reference"}, "problem")
    weak = _keys(problem["weak_form"], {"alpha", "rhs"}, "nonlinear weak_form")
    alpha = _alpha(weak["alpha"])
    validation = _keys(settings["validation"], _VALIDATION_KEYS, "nonlinear validation")
    if any(not finite_number(value, positive=True) for value in validation.values()):
        raise PDEInputError("All numerical validation thresholds must be finite and strictly positive")
    projected = _linear_settings({
        "problem": {"domain": problem["domain"],
                    "weak_form": {"diffusion": 1.0, "reaction": 0.0, "rhs": weak["rhs"]},
                    "dirichlet": problem["dirichlet"], "reference": problem["reference"]},
        "mesh": settings["mesh"],
        "validation": {name: validation[name] for name in
                       ("max_l2_error", "min_l2_rate", "max_residual_relative")}})
    normalized = copy.deepcopy(projected)
    normalized["problem"]["weak_form"] = {"alpha": alpha, "rhs": projected["problem"]["weak_form"]["rhs"]}
    normalized["validation"] = {name: float(validation[name]) for name in sorted(_VALIDATION_KEYS)}
    return normalized


def manufactured_rhs(alpha: float) -> str:
    """Bounded source for u=sin(pi*x[0])*sin(pi*x[1]); alpha=0 is the old RHS."""
    alpha = _alpha(alpha)
    linear_rhs = "2*pi**2*sin(pi*x[0])*sin(pi*x[1])"
    if alpha == 0.0:
        return linear_rhs
    rhs = (linear_rhs + f"*(1+{alpha!r}*(3*sin(pi*x[0])**2*sin(pi*x[1])**2"
           "-sin(pi*x[0])**2-sin(pi*x[1])**2))")
    parse_expression(rhs)
    return rhs


def manufactured_settings(alpha: float = 1.0) -> dict:
    """Fresh canonical settings; all numerical thresholds are declared upfront."""
    alpha = _alpha(alpha)
    return validate_settings({
        "problem": {"domain": "unit_square", "weak_form": {"alpha": alpha, "rhs": manufactured_rhs(alpha)},
                    "dirichlet": "0.0",
                    "reference": {"solution": "sin(pi*x[0])*sin(pi*x[1])",
                                  "source": "Analytical manufactured solution for -div((1+alpha*u^2)*grad(u)) on the dimensionless unit square"}},
        "mesh": {"cell_counts": [8, 16, 32], "degree": 1},
        "validation": {"max_l2_error": .003, "min_l2_rate": 1.8, "max_h1_seminorm_error": .12,
                       "min_h1_rate": .9, "max_residual_relative": 1e-10}})


def source_value(alpha: float, x: float, y: float) -> float:
    """Independent direct divergence, using sin/cos derivatives, not the factory."""
    alpha = _alpha(alpha)
    x, y = _number(x, "x"), _number(y, "y")
    if not 0.0 <= x <= 1.0 or not 0.0 <= y <= 1.0:
        raise PDEInputError("Manufactured-source coordinates must lie on the unit square")
    sx, sy = math.sin(math.pi * x), math.sin(math.pi * y)
    cx, cy = math.cos(math.pi * x), math.cos(math.pi * y)
    u = sx * sy
    laplacian = -2.0 * math.pi**2 * u
    gradient_x, gradient_y = math.pi * cx * sy, math.pi * sx * cy
    gradient_squared = gradient_x**2 + gradient_y**2
    return _number(-((1.0 + alpha * u**2) * laplacian + 2.0 * alpha * u * gradient_squared),
                   "Manufactured direct-divergence source")


def model_declaration(settings: dict) -> dict:
    """Common declared-model wrapper, with only measured scalar u as a field."""
    normalized = validate_settings(settings)
    problem = normalized["problem"]
    return {"case": "unit_square_nonlinear_diffusion", "version": VERSION,
            "model": {"geometry": {"type": "unit_square", "dimensions": [1.0, 1.0],
                                   "origin": [0.0, 0.0], "unit": "1"},
                      "mesh": {"cell_counts": list(normalized["mesh"]["cell_counts"]),
                               "degree": 1, "cell_type": "triangle", "space": "scalar_lagrange"}},
            "constitutive_law": {"type": "solution_dependent_scalar_diffusion", "expression": "1+alpha*u^2",
                                 "alpha": {"value": problem["weak_form"]["alpha"], "unit": "1"},
                                 "uniform_positive_lower_bound": 1.0},
            "boundary_conditions": [{"type": "dirichlet", "selection": {"type": "entire_boundary"},
                                      "value": constant_expression(problem["dirichlet"]), "unit": "1"}],
            "loads": [{"type": "source", "expression": problem["weak_form"]["rhs"], "unit": "1"}],
            "outputs": {"fields": [{"field": "u", "type": "scalar", "unit": "1"}]},
            "reference": copy.deepcopy(problem["reference"])}


def _policy(options: object, expected: dict, label: str) -> dict:
    _keys(options, set(expected), label)
    for key, wanted in expected.items():
        observed = options[key]
        if expected is _EFFECTIVE_OPTIONS and key == "line_search_type" and wanted == "none":
            valid = type(observed) is str and observed in {"none", "basic"}
        elif type(wanted) in (str, bool, int):
            valid = type(observed) is type(wanted) and observed == wanted
        else:
            valid = finite_number(observed) and observed == wanted
        if not valid:
            raise PDEInputError(f"{label}.{key} differs from the fixed Newton policy")
    return copy.deepcopy(options)


def _consistent(observed: float, expected: float, label: str) -> None:
    if not finite_number(expected, nonnegative=True) or abs(observed - expected) > _CONSISTENCY_ATOL:
        raise PDEInputError(f"Inconsistent {label}")


def _consistent_ratio(observed: float, expected: float, label: str) -> None:
    if (not finite_number(expected, nonnegative=True) or
            not math.isclose(observed, expected, rel_tol=1e-12, abs_tol=0.0)):
        raise PDEInputError(f"Inconsistent {label}")


def _validated_record(raw: dict, count: int, alpha: float) -> dict:
    _required(raw, _RECORD_KEYS, "Nonlinear mesh observation")
    if (_integer(raw["cells_per_axis"], "cells_per_axis", positive=True) != count or
            _integer(raw["degree"], "degree", positive=True) != 1):
        raise PDEInputError("Nonlinear mesh identity/degree differs from the frozen request")
    result = copy.deepcopy(raw)
    for key in ("global_cells", "global_dofs", "dirichlet_dofs"):
        _integer(raw[key], key, positive=True)
    for key in ("boundary_value_error", "l2_error", "h1_seminorm_error"):
        result[key] = _number(raw[key], key, nonnegative=True)
    residual = _keys(raw["nonlinear_residual"], {"absolute", "rhs_norm", "relative", "normalization"},
                     "nonlinear_residual")
    for key in ("absolute", "rhs_norm", "relative"):
        result["nonlinear_residual"][key] = _number(residual[key], f"nonlinear_residual.{key}", nonnegative=True)
    rhs_norm = residual["rhs_norm"]
    normalization = "free_dof_rhs_l2_norm" if rhs_norm > 0.0 else "absolute_for_zero_rhs"
    if residual["normalization"] != normalization:
        raise PDEInputError("Inconsistent nonlinear residual normalization")
    relative = residual["absolute"] / rhs_norm if rhs_norm > 0.0 else residual["absolute"]
    _consistent_ratio(residual["relative"], relative, "nonlinear residual relative norm")
    result["nonlinear_residual"]["recomputed_relative"] = relative
    newton = _required(raw["newton"], _NEWTON_KEYS, "newton")
    _integer(newton["convergence_reason"], "newton.convergence_reason")
    iterations = _integer(newton["iterations"], "newton.iterations", nonnegative=True)
    _policy(newton["native_options"], _NATIVE_OPTIONS, "newton.native_options")
    if "effective" in newton:
        _policy(newton["effective"], _EFFECTIVE_OPTIONS, "newton.effective")
    if "effective_after" in newton:
        _policy(newton["effective_after"], _EFFECTIVE_OPTIONS, "newton.effective_after")
    for key in ("initial_residual", "final_residual", "relative_residual"):
        result["newton"][key] = _number(newton[key], f"newton.{key}", nonnegative=True)
    initial, final = newton["initial_residual"], newton["final_residual"]
    if initial == 0.0:
        if rhs_norm != 0.0 or newton.get("relative_normalization") != "absolute_for_zero_initial":
            raise PDEInputError("Zero initial Newton norm requires explicit zero-initial and zero-RHS normalization")
        newton_relative = final
    else:
        if newton.get("relative_normalization", "initial_residual_norm") != "initial_residual_norm":
            raise PDEInputError("Inconsistent initial-relative Newton normalization")
        newton_relative = final / initial
    _consistent_ratio(newton["relative_residual"], newton_relative, "Newton relative norm")
    history = newton["history"]
    if not isinstance(history, list) or len(history) != iterations + 1:
        raise PDEInputError("Newton history must cover iterations 0 through iterations exactly once")
    for index, item in enumerate(history):
        _keys(item, {"iteration", "residual_norm"}, "Newton history entry")
        if _integer(item["iteration"], "Newton history iteration", nonnegative=True) != index:
            raise PDEInputError("Newton history iteration order is not sequential")
        _number(item["residual_norm"], "Newton history residual_norm", nonnegative=True)
    # These summaries are direct copies of the callback floats, not independent
    # numerical calculations. Any difference is malformed redundant metadata.
    if history[0]["residual_norm"] != initial:
        raise PDEInputError("Inconsistent Newton history initial norm")
    monitor_initial = history[0]["residual_norm"]
    if history[-1]["residual_norm"] != final:
        raise PDEInputError("Inconsistent Newton history final norm")
    _consistent(final, residual["absolute"], "monitor and independently recomputed nonlinear residual")
    recomputed_initial_relative = residual["absolute"] / initial if initial > 0.0 else residual["absolute"]
    _number(recomputed_initial_relative, "Independently recomputed initial-relative residual", nonnegative=True)
    result["newton"]["recomputed_relative"] = newton_relative
    result["newton"]["independent_initial_relative"] = recomputed_initial_relative
    result["newton"]["monitor_relative"] = (history[-1]["residual_norm"] / monitor_initial
                                             if monitor_initial > 0.0 else history[-1]["residual_norm"])
    result["newton"]["independent_monitor_initial_relative"] = (residual["absolute"] / monitor_initial
                                                                if monitor_initial > 0.0 else residual["absolute"])
    for key in ("monitor_relative", "independent_monitor_initial_relative"):
        _number(result["newton"][key], f"Newton {key}", nonnegative=True)
    if alpha == 0.0:
        comparison = _keys(raw.get("linear_comparison"),
                           {"max_dof_difference", "ksp_convergence_reason", "ksp_iterations"}, "linear_comparison")
        _number(comparison["max_dof_difference"], "linear comparison max_dof_difference", nonnegative=True)
        _integer(comparison["ksp_convergence_reason"], "linear comparison ksp_convergence_reason")
        _integer(comparison["ksp_iterations"], "linear comparison ksp_iterations", nonnegative=True)
    return result


def assess(settings: dict, mesh_records: list[dict]) -> dict:
    """Validate complete observations and retain finite numerical FAIL responses.

    Callback summaries must equal their callback norms exactly. Only the
    independently reassembled absolute residual allows 1e-12 roundoff against
    the monitor norm. Relative normalization uses the existing helper's strict
    1e-12 relative consistency without an absolute allowance. Every reported
    and recomputed norm must independently satisfy its numerical threshold.
    """
    normalized = validate_settings(settings)
    counts = normalized["mesh"]["cell_counts"]
    if not isinstance(mesh_records, list) or len(mesh_records) != len(counts):
        raise PDEInputError("A complete observation is required for every frozen mesh level")
    alpha = normalized["problem"]["weak_form"]["alpha"]
    studies = [_validated_record(raw, count, alpha) for raw, count in zip(mesh_records, counts)]
    for index, study in enumerate(studies):
        for field, rate_field in (("l2_error", "l2_convergence_rate"),
                                  ("h1_seminorm_error", "h1_seminorm_convergence_rate")):
            expected = error_rate(studies[index - 1][field], study[field]) if index else None
            observed = study[rate_field]
            if (expected is None and observed is not None) or (expected is not None and (
                    not finite_number(observed) or abs(observed - expected) > _CONSISTENCY_ATOL)):
                raise PDEInputError(f"Inconsistent {rate_field} at mesh level {study['cells_per_axis']}")
            study[f"recomputed_{rate_field}"] = expected
    fine = studies[-1]
    thresholds = normalized["validation"]
    l2_rates = [study["l2_convergence_rate"] for study in studies[1:]]
    h1_rates = [study["h1_seminorm_convergence_rate"] for study in studies[1:]]
    recomputed_l2_rates = [study["recomputed_l2_convergence_rate"] for study in studies[1:]]
    recomputed_h1_rates = [study["recomputed_h1_seminorm_convergence_rate"] for study in studies[1:]]
    residual = max(max(study["nonlinear_residual"]["relative"], study["nonlinear_residual"]["recomputed_relative"])
                   for study in studies)
    newton_absolute = max(max(study["newton"]["final_residual"], study["nonlinear_residual"]["absolute"],
                              study["newton"]["history"][-1]["residual_norm"]) for study in studies)
    newton_relative = max(max(study["newton"]["relative_residual"], study["newton"]["recomputed_relative"],
                              study["newton"]["independent_initial_relative"],
                              study["newton"]["monitor_relative"],
                              study["newton"]["independent_monitor_initial_relative"]) for study in studies)
    topology = all(study["global_cells"] == 2 * count**2 and study["global_dofs"] == (count + 1)**2 and
                   study["dirichlet_dofs"] == 4 * count for study, count in zip(studies, counts))
    checks = []

    def check(code: str, passed: bool, observed: object, limit: object) -> None:
        checks.append({"code": code, "status": "PASS" if passed else "FAIL", "observed": observed, "limit": limit})

    check("pde_boundary_and_mesh", topology and all(study["boundary_value_error"] <= BOUNDARY_ATOL for study in studies),
          [{"n": study["cells_per_axis"], "cells": study["global_cells"], "dofs": study["global_dofs"],
            "dirichlet_dofs": study["dirichlet_dofs"], "boundary_value_error": study["boundary_value_error"]}
           for study in studies], {"cells": "2*n^2", "dofs": "(n+1)^2", "boundary_dofs": "4*n",
                                  "max_boundary_value_error": BOUNDARY_ATOL})
    check("pde_newton_convergence", all(study["newton"]["convergence_reason"] > 0 for study in studies),
          [study["newton"]["convergence_reason"] for study in studies], "Positive native SNES convergence reason")
    iterations = max(study["newton"]["iterations"] for study in studies)
    check("pde_newton_iterations", iterations <= NEWTON_MAX_ITERATIONS, iterations, NEWTON_MAX_ITERATIONS)
    check("pde_newton_absolute_residual", newton_absolute <= NEWTON_ATOL, newton_absolute, NEWTON_ATOL)
    check("pde_newton_relative_residual", newton_relative <= NEWTON_RTOL, newton_relative, NEWTON_RTOL)
    check("pde_nonlinear_residual", residual <= thresholds["max_residual_relative"],
          residual, thresholds["max_residual_relative"])
    check("pde_analytical_l2_error", fine["l2_error"] <= thresholds["max_l2_error"],
          fine["l2_error"], thresholds["max_l2_error"])
    check("pde_l2_convergence_rate", all(rate is not None and rate >= thresholds["min_l2_rate"]
                                        for rate in l2_rates + recomputed_l2_rates),
          {"reported": l2_rates, "recomputed": recomputed_l2_rates}, thresholds["min_l2_rate"])
    check("pde_analytical_h1_seminorm_error", fine["h1_seminorm_error"] <= thresholds["max_h1_seminorm_error"],
          fine["h1_seminorm_error"], thresholds["max_h1_seminorm_error"])
    check("pde_h1_seminorm_convergence_rate", all(rate is not None and rate >= thresholds["min_h1_rate"]
                                                for rate in h1_rates + recomputed_h1_rates),
          {"reported": h1_rates, "recomputed": recomputed_h1_rates}, thresholds["min_h1_rate"])
    if alpha == 0.0:
        comparison = max(study["linear_comparison"]["max_dof_difference"] for study in studies)
        check("pde_alpha_zero_linear_comparison", comparison <= LINEAR_COMPARISON_ATOL and
              all(study["linear_comparison"]["ksp_convergence_reason"] > 0 for study in studies),
              {"max_dof_difference": comparison,
               "ksp_convergence_reasons": [study["linear_comparison"]["ksp_convergence_reason"] for study in studies]},
              {"max_dof_difference": LINEAR_COMPARISON_ATOL, "ksp_convergence_reason": "positive"})
    passed = all(item["status"] == "PASS" for item in checks)
    failures = ", ".join(item["code"] for item in checks if item["status"] == "FAIL")

    def metric(value: float | int | None) -> dict:
        return {"value": value, "unit": "1", "valid": passed,
                **({"reason": f"Declared nonlinear PDE numerical validation failed: {failures}"} if not passed else {})}

    metrics = {"l2_error": metric(fine["l2_error"]), "h1_seminorm_error": metric(fine["h1_seminorm_error"]),
               "l2_convergence_rate": metric(fine["l2_convergence_rate"]),
               "h1_seminorm_convergence_rate": metric(fine["h1_seminorm_convergence_rate"]),
               "nonlinear_residual_relative": metric(residual), "newton_residual_absolute": metric(newton_absolute),
               "newton_residual_relative": metric(newton_relative), "newton_iterations": metric(iterations)}
    if alpha == 0.0:
        metrics["linear_comparison_max_dof_difference"] = metric(comparison)
    return {"checks": checks, "metrics": metrics, "pending_validations": list(_PENDING),
            "reference": {**copy.deepcopy(normalized["problem"]["reference"]), "domain": "unit_square", "alpha": alpha,
                          "equation": "-div((1+alpha*u^2)*grad(u))=rhs", "units": "dimensionless",
                          "element_degree": 1, "error_quadrature_degree": 8,
                          "expected_l2_order": 2, "expected_h1_seminorm_order": 1,
                          "uniform_positive_diffusion_lower_bound": 1.0,
                          "newton_acceptance": {"absolute": NEWTON_ATOL, "relative": NEWTON_RTOL,
                                                "combination": "both", "max_iterations": NEWTON_MAX_ITERATIONS}},
            "mesh_studies": studies, "limitations": list(_LIMITATIONS)}
