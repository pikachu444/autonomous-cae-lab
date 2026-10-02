"""Pure declared-time and complete synthetic-history tests; no native solve."""

from copy import deepcopy
import math

import pytest

from caelab.adapters import fenicsx_time_expression as expression
from caelab.adapters import fenicsx_worker as old_expression
from plugins.pde_transient import reference as domain
from test_pde_rectangle_reference import synthetic_observations


_DEFAULT = domain.manufactured_settings()


def small_settings():
    settings = deepcopy(_DEFAULT)
    settings["mesh"]["cell_counts"] = [1, 2, 4]
    settings["time"]["step_counts"] = [2]
    return settings


def synthetic_history(settings=None):
    """Synthetic protocol fixture with exact analytical nodal samples, not BE solutions."""
    settings = settings or small_settings()
    studies, native_fields, bindings = [], [], []
    trees = domain._trees(settings["problem"])
    for index, (n, count) in enumerate(domain.study_pairs(settings)):
        dt = settings["time"]["end"]/count
        study = {"study_index": index, "cells_per_axis": n, "step_count": count, "dt": dt,
                 "nominal_h": math.hypot(*settings["problem"]["domain"]["lengths"])/n,
                 "refinement_axis": settings["refinement_axis"], "steps": [],
                 "final_l2_convergence_rate": 2. if index else None, "final_h1_seminorm_convergence_rate": 1. if index else None}
        fields, study_bindings, previous_hash = [], [], None
        for j in range(count+1):
            instant = j*settings["time"]["end"]/count
            bound = domain.bound_rectangle(settings, instant)
            bound["mesh"]["cell_counts"] = [n]
            _, samples = synthetic_observations(bound)
            field = samples[0]
            field["values"] = [expression.scalar_value(trees["initial"] if j == 0 else trees["reference"], *point, instant) for point in field["coordinates"]]
            current_hash = domain.value_sha256(field["node_ids"], field["values"])
            study["steps"].append({"index": j, "time": instant, "dt": dt if j else 0., "native_time_value": instant,
                "solver_status": "COMPLETED" if j else "NOT_RUN", "previous_values_sha256": previous_hash, "current_values_sha256": current_hash,
                "distinct_state": True, "global_cells": 2*n*n, "global_dofs": (n+1)**2, "dirichlet_dofs": len(field["dirichlet_node_ids"]),
                "boundary_value_error": 0., "l2_error": .024/4**index, "h1_seminorm_error": .4/2**index,
                "linear_residual": {"absolute": 1e-13, "rhs_norm": 2., "relative": 5e-14, "normalization": "rhs_l2_norm"} if j else None,
                "ksp_convergence_reason": 4 if j else None, "ksp_iterations": 1 if j else None})
            study_bindings.append({"schema_version": "1", "time": instant, "node_ids": field["node_ids"],
                 "rhs_values": [expression.scalar_value(trees["rhs"], *point, instant) for point in field["coordinates"]],
                 "reference_values": [expression.scalar_value(trees["reference"], *point, instant) for point in field["coordinates"]]})
            fields.append(field)
            previous_hash = current_hash
        studies.append(study)
        native_fields.append(fields)
        bindings.append(study_bindings)
    return studies, native_fields, bindings


def test_time_syntax_uses_old_bounds_without_changing_old_language():
    tree = expression.parse_expression("exp(-t)*(x[0]+2*x[1]+1)")
    assert expression.scalar_value(tree, .2, .4, .5) == pytest.approx(math.exp(-.5)*2.)
    bound = expression.bind_expression("t+x[0]+x[1]", .25)
    assert old_expression.interpret_expression(old_expression.parse_expression(bound), (.2, .4), {}) == pytest.approx(.85)
    with pytest.raises(old_expression.PDEInputError): old_expression.parse_expression("t+x[0]")
    for source in ("x[2]", "t(1)", "t.__class__", "__import__('os')", "x[0]**t", "t**t", "exp(1000)", "t/0", "t+x[True]", "lambda: t", "unknown+t"):
        with pytest.raises(domain.PDEInputError): expression.parse_expression(source)
    for time in (True, float("nan"), float("inf")):
        with pytest.raises(domain.PDEInputError): expression.scalar_value(tree, 0., 0., time)
    with pytest.raises(domain.PDEInputError): expression.scalar_value(expression.parse_expression("1/(t-.5)"), 0., 0., .5)


def test_manufactured_math_matches_independent_time_derivatives_and_laplacians():
    for axis, case in (("mesh", "polynomial"), ("time", "temporal"), ("mesh", "zero_source")):
        settings = domain.manufactured_settings(axis, case)
        for x, y, t in ((.3, .2, 0.), (.6, .7, .5), (2., 1., 1.)):
            phi = x*x*y*y+x+2*y+1
            expected = phi-2*(1+t)*(x*x+y*y) if case == "polynomial" else -math.exp(-t)*(x+2*y+1) if case == "temporal" else 0.
            assert expression.scalar_value(expression.parse_expression(settings["problem"]["weak_form"]["rhs"]), x, y, t) == pytest.approx(expected)
        assert settings["validation"]["max_residual_relative"] == 1e-10
    zero = domain.manufactured_settings(case="zero_source")
    assert zero["problem"]["weak_form"]["rhs"] == "0.0"
    assert zero["refinement_axis"] == "mesh"
    with pytest.raises(domain.PDEInputError): domain.manufactured_settings("time", "zero_source")


@pytest.mark.parametrize("kind", ["axis", "end", "start", "scheme", "bool_count", "product", "non_doubling", "work", "initial", "late_corner", "pure_neumann", "bad_boundary"])
def test_bad_work_time_grid_or_initial_and_boundary_declarations_are_refused(kind):
    settings = small_settings()
    if kind == "axis": settings["refinement_axis"] = "both"
    elif kind == "end": settings["time"]["end"] = float("nan")
    elif kind == "start": settings["time"]["start"] = True
    elif kind == "scheme": settings["time"]["scheme"] = "bdf2"
    elif kind == "bool_count": settings["mesh"]["cell_counts"][0] = True
    elif kind == "product": settings["time"]["step_counts"] = [1, 2, 4]
    elif kind == "non_doubling": settings["mesh"]["cell_counts"] = [1, 3, 4]
    elif kind == "work": settings.update(refinement_axis="time", mesh={"cell_counts": [128], "degree": 1}); settings["time"]["step_counts"] = [32, 64, 128]
    elif kind == "initial": settings["problem"]["initial"]["value"] = "0.0"
    elif kind == "late_corner": settings["problem"]["boundaries"]["xmin"]["value"] += "+t"
    elif kind == "pure_neumann": [row.update(type="neumann") for row in settings["problem"]["boundaries"].values()]
    elif kind == "bad_boundary": settings["problem"]["boundaries"]["xmin"] = []
    with pytest.raises(domain.PDEInputError): domain.validate_settings(settings)


def test_declaration_preserves_time_expressions_initial_and_history_without_mutation():
    settings = small_settings()
    before = deepcopy(settings)
    declaration = domain.model_declaration(settings)
    normalized = domain.validate_settings(settings)
    normalized["time"]["step_counts"][0] = 99
    declaration["model"]["geometry"]["dimensions"][0] = 99
    assert settings == before
    assert declaration["loads"][0]["expression"] == settings["problem"]["weak_form"]["rhs"]
    assert declaration["initial_conditions"][0]["expression"] == settings["problem"]["initial"]["value"]
    assert declaration["outputs"]["history"][0]["time"] == settings["time"]


def test_complete_synthetic_history_has_no_initial_solve_and_keeps_qualification_unknown():
    settings = small_settings()
    records = synthetic_history(settings)
    original = deepcopy(records)
    outcome = domain.assess(settings, *records)
    assert all(row["status"] == "PASS" for row in outcome["checks"])
    assert all(metric["valid"] for metric in outcome["metrics"].values())
    assert outcome["pending_validations"] == ["physical_validation", "model_qualification"]
    assert records == original and outcome["time_studies"][0]["steps"][0]["solver_status"] == "NOT_RUN"


@pytest.mark.parametrize("kind", ["missing", "duplicate_time", "constant", "previous", "current", "alias", "initial_solve", "initial_dt", "rhs", "reference", "binding_ids", "normal", "topology", "static_facet", "residual"])
def test_missing_or_tampered_intermediate_history_is_malformed(kind):
    settings = small_settings()
    studies, fields, bindings = synthetic_history(settings)
    study, step, field, binding = studies[-1], studies[-1]["steps"][1], fields[-1][1], bindings[-1][1]
    if kind == "missing": study["steps"].pop(1)
    elif kind == "duplicate_time": step["time"] = 0.
    elif kind == "constant": step["native_time_value"] = 0.
    elif kind == "previous": step["previous_values_sha256"] = "0"*64
    elif kind == "current": step["current_values_sha256"] = "0"*64
    elif kind == "alias": step["distinct_state"] = False
    elif kind == "initial_solve": study["steps"][0]["solver_status"] = "COMPLETED"
    elif kind == "initial_dt": study["steps"][0]["dt"] = .5
    elif kind == "rhs": binding["rhs_values"][0] += .1
    elif kind == "reference": binding["reference_values"][0] += .1
    elif kind == "binding_ids": binding["node_ids"] = list(reversed(binding["node_ids"]))
    elif kind == "normal": field["boundaries"]["xmin"]["normal_integral"][0] *= -1
    elif kind == "topology": field["cell_node_ids"][0] = field["cell_node_ids"][1]
    elif kind == "static_facet":
        field["boundaries"]["xmin"]["facet_node_ids"][0].reverse()
    elif kind == "residual": step["linear_residual"]["relative"] = 0.
    with pytest.raises(domain.PDEInputError): domain.assess(settings, studies, fields, bindings)


def test_finite_intermediate_residual_failure_invalidates_final_metrics_without_losing_history():
    settings = small_settings()
    studies, fields, bindings = synthetic_history(settings)
    studies[0]["steps"][1]["linear_residual"].update(absolute=1e-8, relative=5e-9)
    outcome = domain.assess(settings, studies, fields, bindings)
    assert outcome["time_studies"][0]["steps"][1]["linear_residual"]["relative"] == 5e-9
    assert all(not metric["valid"] and metric["reason"] for metric in outcome["metrics"].values())
    assert outcome["metrics"]["l2_error"]["value"] == .0015


def test_canonical_hash_binds_sorted_ids_and_preserves_numeric_json_types():
    assert domain.value_sha256([0, 1], [1., 2.]) != domain.value_sha256([1, 0], [1., 2.])
    assert domain.value_sha256([0, 1], [1., 2.]) != domain.value_sha256([0, 1], [1, 2])
