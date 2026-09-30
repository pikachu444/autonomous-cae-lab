"""Pure mathematical/contract fixtures; none of these tests run a PDE solver."""

import builtins
import copy
import importlib.util
import json
import math
import sys

import pytest

from caelab.adapters import fenicsx_worker as expressions
from plugins.pde_nonlinear import reference as nonlinear


def _settings(alpha=1):
    return nonlinear.manufactured_settings(alpha)


def _records(alpha=1, *, l2=(.0256, .0064, .0016), h1=(.4, .2, .1)):
    """Hand-set synthetic numerical records, not observed native convergence."""
    records = []
    for index, count in enumerate([8, 16, 32]):
        iterations = 1 if alpha == 0 else 4
        history = ([{"iteration": 0, "residual_norm": 1.0}, {"iteration": 1, "residual_norm": 1e-13}]
                   if alpha == 0 else [{"iteration": step, "residual_norm": norm}
                                       for step, norm in enumerate([1.0, .1, .001, 1e-7, 1e-13])])
        item = {"cells_per_axis": count, "degree": 1, "global_cells": 2 * count**2,
                "global_dofs": (count + 1)**2, "dirichlet_dofs": 4 * count,
                "boundary_value_error": 0.0, "l2_error": l2[index], "h1_seminorm_error": h1[index],
                "l2_convergence_rate": (math.log2(l2[index - 1]) - math.log2(l2[index])
                                        if index and l2[index - 1] > 0 and l2[index] > 0 else None),
                "h1_seminorm_convergence_rate": (math.log2(h1[index - 1]) - math.log2(h1[index])
                                                 if index and h1[index - 1] > 0 and h1[index] > 0 else None),
                "nonlinear_residual": {"absolute": 1e-13, "rhs_norm": 2.0, "relative": 5e-14,
                                       "normalization": "free_dof_rhs_l2_norm"},
                "newton": {"convergence_reason": 2, "iterations": iterations,
                           "initial_residual": 1.0, "final_residual": 1e-13, "relative_residual": 1e-13,
                           "relative_normalization": "initial_residual_norm", "history": history,
                           "native_options": {"snes_type": "newtonls", "snes_linesearch_type": "none",
                                              "snes_rtol": 1e-10, "snes_atol": 1e-10, "snes_stol": 0.0,
                                              "snes_max_it": 25, "ksp_type": "preonly", "pc_type": "lu",
                                              "ksp_error_if_not_converged": True},
                           "effective": {"snes_type": "newtonls", "rtol": 1e-10, "atol": 1e-10,
                                         "stol": 0.0, "max_iterations": 25, "ksp_type": "preonly", "pc_type": "lu"}}}
        if alpha == 0:
            item["linear_comparison"] = {"max_dof_difference": 2e-15, "ksp_convergence_reason": 4,
                                         "ksp_iterations": 1}
        records.append(item)
    return records


def _check(result, code):
    return next(item for item in result["checks"] if item["code"] == code)


def _invalid(result, code):
    assert _check(result, code)["status"] == "FAIL"
    assert all(not metric["valid"] and code in metric["reason"] for metric in result["metrics"].values())
    json.dumps(result, allow_nan=False)


def _set_norm(study, final, *, initial=1.0, rhs_norm=2.0):
    study["newton"].update(initial_residual=initial, final_residual=final, relative_residual=final / initial)
    study["newton"]["history"][0]["residual_norm"] = initial
    study["newton"]["history"][-1]["residual_norm"] = final
    study["nonlinear_residual"].update(absolute=final, rhs_norm=rhs_norm, relative=final / rhs_norm)


@pytest.mark.parametrize("alpha", [0, 1, 2])
def test_known_source_values_from_direct_divergence(alpha):
    assert nonlinear.source_value(alpha, .5, .5) == pytest.approx(2 * math.pi**2 * (1 + alpha), abs=1e-13)
    assert nonlinear.source_value(alpha, .25, .25) == pytest.approx(math.pi**2 * (1 - alpha / 4), abs=1e-13)
    assert nonlinear.source_value(alpha, .5, .25) == pytest.approx(math.sqrt(2) * math.pi**2, abs=1e-13)
    assert nonlinear.source_value(alpha, 0, .37) == 0
    assert nonlinear.source_value(alpha, 1, .37) == pytest.approx(0, abs=1e-13)


@pytest.mark.parametrize("alpha", [0, .25, 1, 2])
@pytest.mark.parametrize("point", [(.13, .79), (.71, .18), (.5, .5), (.25, .25), (0, 1)])
def test_factory_expression_matches_independent_derivative_evaluator(alpha, point):
    tree = expressions.parse_expression(nonlinear.manufactured_rhs(alpha))
    value = expressions.interpret_expression(tree, list(point),
                                             {name: getattr(math, name) for name in ("sin", "cos", "exp")})
    assert value == pytest.approx(nonlinear.source_value(alpha, *point), rel=1e-13, abs=1e-13)


def test_zero_alpha_is_exact_previous_linear_rhs_and_factory_is_not_source_evaluator(monkeypatch):
    assert nonlinear.manufactured_rhs(0) == "2*pi**2*sin(pi*x[0])*sin(pi*x[1])"
    monkeypatch.setattr(nonlinear, "manufactured_rhs", lambda *_: pytest.fail("Direct divergence must be independent"))
    assert nonlinear.source_value(1, .5, .5) == pytest.approx(4 * math.pi**2)


def test_existing_expression_and_projection_validator_are_reused(monkeypatch):
    assert nonlinear.parse_expression is expressions.parse_expression
    assert nonlinear.interpret_expression is expressions.interpret_expression
    assert nonlinear.constant_expression is expressions.constant_expression
    assert nonlinear.finite_number is expressions.finite_number
    settings = _settings()
    receipts = []

    def existing_validator(projected):
        receipts.append(copy.deepcopy(projected))
        return expressions.validate_settings(projected)

    monkeypatch.setattr(nonlinear, "_linear_settings", existing_validator)
    nonlinear.validate_settings(settings)
    assert len(receipts) == 1
    assert receipts[0]["problem"]["weak_form"] == {
        "diffusion": 1.0, "reaction": 0.0, "rhs": settings["problem"]["weak_form"]["rhs"]}
    assert set(receipts[0]["validation"]) == {"max_l2_error", "min_l2_rate", "max_residual_relative"}
    assert receipts[0]["mesh"] == {"cell_counts": [8, 16, 32], "degree": 1}


def test_canonical_limits_and_newton_policy_are_declared_before_execution():
    settings = nonlinear.manufactured_settings()
    assert nonlinear.VERSION == "1"
    assert nonlinear.NEWTON_RTOL == nonlinear.NEWTON_ATOL == 1e-10
    assert nonlinear.NEWTON_MAX_ITERATIONS == 25
    assert settings["validation"] == {"max_l2_error": .003, "min_l2_rate": 1.8,
                                      "max_h1_seminorm_error": .12, "min_h1_rate": .9,
                                      "max_residual_relative": 1e-10}
    assert settings["problem"]["weak_form"]["alpha"] == 1.0
    settings["mesh"]["cell_counts"][0] = 99
    assert nonlinear.manufactured_settings()["mesh"]["cell_counts"] == [8, 16, 32]


@pytest.mark.parametrize("alpha", [0, 1, 2])
def test_complete_synthetic_records_pass_with_known_metrics_and_pending_unknowns(alpha):
    result = nonlinear.assess(_settings(alpha), _records(alpha))
    assert all(item["status"] == "PASS" for item in result["checks"])
    assert all(item["valid"] and item["unit"] == "1" for item in result["metrics"].values())
    expected = {"l2_error": .0016, "h1_seminorm_error": .1, "l2_convergence_rate": 2,
                "h1_seminorm_convergence_rate": 1, "nonlinear_residual_relative": 5e-14,
                "newton_residual_absolute": 1e-13, "newton_residual_relative": 1e-13,
                "newton_iterations": 1 if alpha == 0 else 4}
    for key, value in expected.items():
        assert result["metrics"][key]["value"] == pytest.approx(value, rel=1e-13, abs=1e-15)
    assert set(result["pending_validations"]) == {"model_qualification", "physical_validation"}
    assert result["reference"]["units"] == "dimensionless"
    assert result["reference"]["expected_l2_order"] == 2
    assert result["reference"]["expected_h1_seminorm_order"] == 1
    assert result["reference"]["newton_acceptance"]["combination"] == "both"
    if alpha == 0:
        assert result["metrics"]["linear_comparison_max_dof_difference"]["value"] == 2e-15
    else:
        assert set(result["metrics"]) == set(expected)
    json.dumps(result, allow_nan=False)


def test_flat_common_model_wrapper_and_boundaries_contain_only_declared_mathematics():
    settings = _settings()
    settings["problem"]["dirichlet"] = "pi/2"
    declaration = nonlinear.model_declaration(settings)
    assert declaration["model"]["geometry"] == {
        "type": "unit_square", "dimensions": [1, 1], "origin": [0, 0], "unit": "1"}
    assert declaration["model"]["mesh"]["cell_counts"] == [8, 16, 32]
    assert declaration["constitutive_law"]["alpha"] == {"value": 1, "unit": "1"}
    assert declaration["constitutive_law"]["uniform_positive_lower_bound"] == 1
    assert declaration["boundary_conditions"] == [{"type": "dirichlet", "selection": {"type": "entire_boundary"},
                                                   "value": math.pi / 2, "unit": "1"}]
    assert declaration["outputs"]["fields"] == [{"field": "u", "type": "scalar", "unit": "1"}]
    assert declaration["loads"][0]["expression"] == settings["problem"]["weak_form"]["rhs"]
    text = json.dumps(declaration, allow_nan=False)
    assert "snes" not in text and "dolfinx" not in text and "PETSc" not in text


def test_settings_records_and_returned_nested_structures_are_independent():
    settings, records = _settings(), _records()
    old_settings, old_records = copy.deepcopy(settings), copy.deepcopy(records)
    normalized = nonlinear.validate_settings(settings)
    declaration = nonlinear.model_declaration(settings)
    result = nonlinear.assess(settings, records)
    assert settings == old_settings and records == old_records
    normalized["problem"]["weak_form"]["alpha"] = 2
    normalized["mesh"]["cell_counts"][0] = 1
    normalized["validation"]["max_h1_seminorm_error"] = 99
    declaration["model"]["mesh"]["cell_counts"][0] = 1
    declaration["reference"]["source"] = "changed"
    result["mesh_studies"][0]["newton"]["history"][0]["residual_norm"] = 99
    result["limitations"].append("invented")
    result["reference"]["source"] = "changed"
    assert settings == old_settings and records == old_records
    assert "invented" not in nonlinear.assess(settings, records)["limitations"]


@pytest.mark.parametrize("reason", [0, -3])
def test_complete_finite_failed_convergence_is_numerical_fail_not_shape_error(reason):
    records = _records()
    records[0]["newton"]["convergence_reason"] = reason
    result = nonlinear.assess(_settings(), records)
    _invalid(result, "pde_newton_convergence")
    assert result["mesh_studies"][0]["newton"]["convergence_reason"] == reason


def test_complete_history_above_iteration_budget_is_retained_numerical_fail():
    records = _records()
    records[0]["newton"]["iterations"] = 26
    records[0]["newton"]["history"] = [{"iteration": step,
                                        "residual_norm": 1 if step == 0 else 1e-13 if step == 26 else .1}
                                       for step in range(27)]
    result = nonlinear.assess(_settings(), records)
    _invalid(result, "pde_newton_iterations")
    assert result["metrics"]["newton_iterations"]["value"] == 26


@pytest.mark.parametrize("initial,final,expected", [
    (10, 2e-10, "pde_newton_absolute_residual"),
    (.01, 2e-11, "pde_newton_relative_residual"),
])
def test_acceptance_requires_both_absolute_and_relative_even_if_snes_can_stop_on_one(initial, final, expected):
    records = _records()
    _set_norm(records[0], final, initial=initial)
    result = nonlinear.assess(_settings(), records)
    _invalid(result, expected)


@pytest.mark.parametrize("changed_field,expected", [
    ("independent_absolute", "pde_newton_absolute_residual"),
    ("history_final", "pde_newton_absolute_residual"),
])
def test_roundoff_consistency_allowance_never_relaxes_actual_threshold_gate(changed_field, expected):
    records = _records()
    _set_norm(records[0], 9.99e-11, rhs_norm=1)
    if changed_field == "independent_absolute":
        records[0]["nonlinear_residual"].update(absolute=1.0001e-10, relative=1.0001e-10)
    else:
        records[0]["newton"]["history"][-1]["residual_norm"] = 1.0001e-10
    result = nonlinear.assess(_settings(), records)
    _invalid(result, expected)


@pytest.mark.parametrize("section,field", [("nonlinear_residual", "relative"), ("newton", "relative_residual")])
@pytest.mark.parametrize("value", [0.0, 1.0001e-13])
def test_relative_norms_cannot_be_falsely_reported_within_an_absolute_roundoff_allowance(section, field, value):
    records = _records()
    records[0][section][field] = value
    with pytest.raises(expressions.PDEInputError, match="relative norm"):
        nonlinear.assess(_settings(), records)


def test_monitor_initial_norm_cannot_be_zero_without_explicit_zero_rhs_normalization():
    records = _records()
    _set_norm(records[0], 0.0, initial=1e-13)
    records[0]["newton"]["history"][0]["residual_norm"] = 0.0
    with pytest.raises(expressions.PDEInputError, match="zero-initial normalization"):
        nonlinear.assess(_settings(), records)


def test_rhs_relative_residual_is_distinct_from_initial_relative_newton_residual():
    records = _records()
    _set_norm(records[0], 1e-13, rhs_norm=1e-8)
    result = nonlinear.assess(_settings(), records)
    _invalid(result, "pde_nonlinear_residual")
    assert _check(result, "pde_newton_relative_residual")["status"] == "PASS"
    assert result["metrics"]["nonlinear_residual_relative"]["value"] == pytest.approx(1e-5)


@pytest.mark.parametrize("change", ["count", "boundary"])
def test_finite_topology_or_boundary_failures_retain_values(change):
    records = _records()
    if change == "count":
        records[0]["global_dofs"] += 1
    else:
        records[0]["boundary_value_error"] = 2e-12
    result = nonlinear.assess(_settings(), records)
    _invalid(result, "pde_boundary_and_mesh")
    assert result["mesh_studies"][0]["global_dofs"] == records[0]["global_dofs"]
    assert _check(result, "pde_boundary_and_mesh")["limit"]["max_boundary_value_error"] == 1e-12


@pytest.mark.parametrize("l2,h1,expected", [
    ((.0256, .0064, .0031), (.4, .2, .1), "pde_analytical_l2_error"),
    ((.02, .01, .0016), (.4, .2, .1), "pde_l2_convergence_rate"),
    ((.0256, .0064, .0016), (.4, .2, .121), "pde_analytical_h1_seminorm_error"),
    ((.0256, .0064, .0016), (.3, .2, .1), "pde_h1_seminorm_convergence_rate"),
    ((0, 0, 0), (.4, .2, .1), "pde_l2_convergence_rate"),
    ((.0256, .0064, .0016), (0, 0, 0), "pde_h1_seminorm_convergence_rate"),
])
def test_finest_errors_and_every_pair_rate_are_separate_finite_numerical_checks(l2, h1, expected):
    records = _records(l2=l2, h1=h1)
    result = nonlinear.assess(_settings(), records)
    _invalid(result, expected)
    assert result["metrics"]["l2_error"]["value"] == l2[-1]
    assert result["metrics"]["h1_seminorm_error"]["value"] == h1[-1]


@pytest.mark.parametrize("field,value", [("max_dof_difference", 1.0001e-10), ("ksp_convergence_reason", -3)])
def test_alpha_zero_comparison_uses_predeclared_difference_and_native_ksp_reason(field, value):
    records = _records(0)
    records[0]["linear_comparison"][field] = value
    result = nonlinear.assess(_settings(0), records)
    _invalid(result, "pde_alpha_zero_linear_comparison")
    assert _check(result, "pde_alpha_zero_linear_comparison")["limit"]["max_dof_difference"] == 1e-10


def test_explicit_zero_rhs_and_zero_initial_normalizations_do_not_invent_a_division():
    settings = _settings()
    settings["problem"]["weak_form"]["rhs"] = "0.0"
    settings["problem"]["reference"]["solution"] = "0.0"
    records = _records(l2=(0, 0, 0), h1=(0, 0, 0))
    for study in records:
        study["nonlinear_residual"] = {"absolute": 0, "rhs_norm": 0, "relative": 0,
                                        "normalization": "absolute_for_zero_rhs"}
        study["newton"].update(iterations=0, initial_residual=0, final_residual=0, relative_residual=0,
                                relative_normalization="absolute_for_zero_initial",
                                history=[{"iteration": 0, "residual_norm": 0}])
    result = nonlinear.assess(settings, records)
    assert _check(result, "pde_newton_absolute_residual")["status"] == "PASS"
    assert _check(result, "pde_newton_relative_residual")["status"] == "PASS"
    _invalid(result, "pde_l2_convergence_rate")
    assert result["metrics"]["l2_convergence_rate"]["value"] is None


@pytest.mark.parametrize("alpha", [-.01, 2.01, True, False, math.nan, math.inf, "1", None])
def test_alpha_bounds_nonboolean_and_finite_requirements_apply_to_all_factories(alpha):
    for function, arguments in [(nonlinear.manufactured_rhs, (alpha,)),
                                (nonlinear.manufactured_settings, (alpha,)),
                                (nonlinear.source_value, (alpha, .5, .5))]:
        with pytest.raises(expressions.PDEInputError):
            function(*arguments)


@pytest.mark.parametrize("point", [(True, .5), (math.inf, .5), (.5, math.nan), (-.1, .5), (.5, 1.1)])
def test_direct_divergence_requires_finite_unit_square_points(point):
    with pytest.raises(expressions.PDEInputError):
        nonlinear.source_value(1, *point)


@pytest.mark.parametrize("path,value", [
    (("problem", "domain"), "imported_mesh"), (("problem", "weak_form", "alpha"), True),
    (("problem", "weak_form", "alpha"), -.1), (("problem", "weak_form", "alpha"), 2.1),
    (("problem", "reference", "source"), " "), (("problem", "reference", "source"), "x" * 2001),
    (("problem", "dirichlet"), "x[0]"), (("problem", "dirichlet"), True),
    (("mesh", "cell_counts"), [8, 16]), (("mesh", "cell_counts"), [8, 32, 64]),
    (("mesh", "cell_counts"), [8, 16, 16]), (("mesh", "cell_counts"), [64, 128, 256]),
    (("mesh", "cell_counts"), [True, 2, 4]), (("mesh", "cell_counts"), (8, 16, 32)),
    (("mesh", "degree"), 2), (("mesh", "degree"), True),
    (("validation", "max_h1_seminorm_error"), 0), (("validation", "min_h1_rate"), -1),
    (("validation", "max_residual_relative"), math.inf), (("validation", "max_l2_error"), True),
])
def test_invalid_new_and_reused_public_settings_are_rejected(path, value):
    settings = _settings()
    target = settings
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(expressions.PDEInputError):
        nonlinear.validate_settings(settings)


@pytest.mark.parametrize("section", [None, "problem", "weak_form", "reference", "mesh", "validation"])
@pytest.mark.parametrize("change", ["missing", "extra"])
def test_exact_public_key_sets_prevent_undeclared_backend_controls(section, change):
    settings = _settings()
    if section is None:
        target = settings
    elif section in ("weak_form", "reference"):
        target = settings["problem"][section]
    else:
        target = settings[section]
    if change == "extra":
        target["python_command"] = "unrequested"
    else:
        target.pop(next(iter(target)))
    with pytest.raises(expressions.PDEInputError):
        nonlinear.validate_settings(settings)


@pytest.mark.parametrize("expression", [
    "__import__('os').system('unsafe')", "open('secret').read()", "x.__class__", "x[2]", "x[True]",
    "sin(value=x[0])", "True", "1e309", "x[0]**x[1]", "x[0]**17", "x[0]/0", "exp(1000)",
    "sin(" * 22 + "x[0]" + ")" * 22, "+".join(["x[0]"] * 40), " " * 1025,
])
@pytest.mark.parametrize("field", ["rhs", "solution"])
def test_old_ast_safety_and_resource_limits_apply_to_nonlinear_inputs(expression, field):
    settings = _settings()
    target = settings["problem"]["weak_form"] if field == "rhs" else settings["problem"]["reference"]
    target[field] = expression
    with pytest.raises(expressions.PDEInputError):
        nonlinear.validate_settings(settings)


@pytest.mark.parametrize("mutation", [
    lambda r: r.pop(), lambda r: r[0].pop("newton"), lambda r: r[0].update(cells_per_axis=4),
    lambda r: r[0].update(cells_per_axis=True), lambda r: r[0].update(degree=2),
    lambda r: r[0].update(global_cells=True), lambda r: r[0].update(global_dofs=0),
    lambda r: r[0].update(boundary_value_error=math.nan), lambda r: r[0].update(l2_error=-1),
    lambda r: r[0].update(h1_seminorm_error=math.inf), lambda r: r[0].update(l2_convergence_rate=2),
    lambda r: r[1].update(h1_seminorm_convergence_rate=.5), lambda r: r[1].update(l2_convergence_rate=True),
    lambda r: r[0]["nonlinear_residual"].pop("normalization"),
    lambda r: r[0]["nonlinear_residual"].update(rhs_norm=False),
    lambda r: r[0]["nonlinear_residual"].update(relative=.01),
    lambda r: r[0]["nonlinear_residual"].update(normalization="rhs_l2_norm"),
    lambda r: r[0]["newton"].update(convergence_reason=True),
    lambda r: r[0]["newton"].update(iterations=-1), lambda r: r[0]["newton"].update(initial_residual=0),
    lambda r: r[0]["newton"].update(final_residual=math.inf),
    lambda r: r[0]["newton"].update(relative_residual=.01),
    lambda r: r[0]["newton"].pop("history"), lambda r: r[0]["newton"]["history"].pop(),
    lambda r: r[0]["newton"]["history"][0].update(iteration=1),
    lambda r: r[0]["newton"]["history"][0].update(iteration=False),
    lambda r: r[0]["newton"]["history"][0].update(residual_norm=-1),
    lambda r: r[0]["newton"]["history"][0].update(residual_norm=2),
    lambda r: r[0]["newton"]["history"][-1].update(residual_norm=1e-8),
    lambda r: r[0]["newton"]["native_options"].pop("snes_rtol"),
    lambda r: r[0]["newton"]["native_options"].update(snes_rtol=1e-3),
    lambda r: r[0]["newton"]["native_options"].update(snes_stol=False),
    lambda r: r[0]["newton"]["native_options"].update(ksp_error_if_not_converged=1),
    lambda r: r[0]["newton"]["effective"].update(atol=1e-3),
])
def test_missing_nonfinite_or_inconsistent_numerical_records_raise(mutation):
    records = _records()
    mutation(records)
    with pytest.raises(expressions.PDEInputError):
        nonlinear.assess(_settings(), records)


def test_native_effective_policy_is_checked_if_present_and_original_shape_remains_supported():
    records = _records()
    for record in records:
        record["newton"].pop("effective")
        record["newton"].pop("relative_normalization")
    assert all(item["status"] == "PASS" for item in nonlinear.assess(_settings(), records)["checks"])


@pytest.mark.parametrize("mutation", [
    lambda r: r[0].pop("linear_comparison"),
    lambda r: r[0]["linear_comparison"].update(max_dof_difference=-1),
    lambda r: r[0]["linear_comparison"].update(ksp_convergence_reason=True),
    lambda r: r[0]["linear_comparison"].update(ksp_iterations=-1),
])
def test_alpha_zero_requires_complete_finite_linear_comparison(mutation):
    records = _records(0)
    mutation(records)
    with pytest.raises(expressions.PDEInputError):
        nonlinear.assess(_settings(0), records)


def test_fixed_standalone_name_always_uses_trusted_helper_and_host_import_errors_propagate(monkeypatch):
    original_import = builtins.__import__
    monkeypatch.setitem(sys.modules, "fenicsx_expression", expressions)

    def forbidden_global_caelab(name, *args, **kwargs):
        if name.startswith("caelab"):
            pytest.fail("Copied domain_reference must use its preserved expression helper")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", forbidden_global_caelab)
    spec = importlib.util.spec_from_file_location("domain_reference", nonlinear.__file__)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.parse_expression is expressions.parse_expression
    assert module.manufactured_rhs(0) == "2*pi**2*sin(pi*x[0])*sin(pi*x[1])"

    for missing_name in ("caelab", "missing_dependency"):
        def missing_installed_dependency(name, *args, **kwargs):
            if name == "caelab.adapters.fenicsx_worker":
                raise ModuleNotFoundError(f"No module named {missing_name}", name=missing_name)
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", missing_installed_dependency)
        host_spec = importlib.util.spec_from_file_location("host_nonlinear_reference", nonlinear.__file__)
        module = importlib.util.module_from_spec(host_spec)
        with pytest.raises(ModuleNotFoundError) as error:
            host_spec.loader.exec_module(module)
        assert error.value.name == missing_name
