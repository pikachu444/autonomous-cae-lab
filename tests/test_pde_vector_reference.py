"""Directed vector mathematics and labelled synthetic fields; no native solve."""

from copy import deepcopy
from functools import lru_cache
import math

import pytest

from plugins.pde_vector import reference as domain
from test_pde_rectangle_reference import synthetic_observations as scalar_observations


@lru_cache(maxsize=1)
def _baseline():
    return domain.manufactured_settings()


def small_settings():
    settings = deepcopy(_baseline())
    settings["mesh"]["cell_counts"] = [1, 2, 4]
    return settings


def synthetic_vector(settings=None):
    """Reuse existing rectangle topology; norms are protocol fixtures, not solves."""
    settings = settings or small_settings()
    scalar = [scalar_observations(domain.scalar_settings(settings, component)) for component in range(2)]
    trees = domain._trees(settings["problem"])
    studies, fields, bindings = [], [], []
    for index, count in enumerate(settings["mesh"]["cell_counts"]):
        study, field = deepcopy(scalar[0][0][index]), deepcopy(scalar[0][1][index])
        field.update(field_type="vector", components=["u0", "u1"], block_size=2)
        field["values"] = [[domain._value(tree, point) for tree in trees["reference"]] for point in field["coordinates"]]
        for side in domain.SIDES:
            field["boundaries"][side]["prescribed_values"] = [
                [scalar[component][1][index]["boundaries"][side]["prescribed_values"][row] for component in range(2)]
                for row in range(len(field["boundaries"][side]["dof_ids"]))]
            field["boundaries"][side]["prescribed_integral"] = [0., 0.]  # No native integral assertion.
        rows = [{"index": component, "field": f"u{component}", "l2_error": (.024, .036)[component]/4**index,
                 "h1_seminorm_error": (.4, .6)[component]/2**index,
                 "l2_convergence_rate": 2. if index else None, "h1_seminorm_convergence_rate": 1. if index else None,
                 "boundary_value_error": 0.} for component in range(2)]
        study.update(global_nodes=(count+1)**2, global_dofs=2*(count+1)**2,
                     dirichlet_nodes=len(field["dirichlet_node_ids"]), dirichlet_dofs=2*len(field["dirichlet_node_ids"]),
                     block_size=2, solution_sync_error=0., components=rows,
                     l2_error=math.hypot(*(row["l2_error"] for row in rows)),
                     h1_seminorm_error=math.hypot(*(row["h1_seminorm_error"] for row in rows)))
        binding = {"schema_version": "1", "node_ids": list(field["node_ids"]), "components": ["u0", "u1"],
                   **{key: [[domain._value(tree, point) for tree in trees[name]] for point in field["coordinates"]]
                      for key, name in (("rhs_values", "rhs"), ("reference_values", "reference"))}}
        studies.append(study)
        fields.append(field)
        bindings.append(binding)
    return studies, fields, bindings


def refresh_errors(studies):
    """Keep aggregate/rate identities true while testing numerical rejection."""
    for index, study in enumerate(studies):
        for name, rate in (("l2_error", "l2_convergence_rate"), ("h1_seminorm_error", "h1_seminorm_convergence_rate")):
            study[name] = math.hypot(*(row[name] for row in study["components"]))
            study[rate] = domain.expression.error_rate(studies[index-1][name], study[name]) if index else None
            for component, row in enumerate(study["components"]):
                row[rate] = domain.expression.error_rate(studies[index-1]["components"][component][name], row[name]) if index else None


@pytest.mark.parametrize("lam,mu,c,lengths", [(1., 1., 0., (2., 1.)), (3., .5, 2., (1.5, .75)), (0., 2., 3., (2., 1.))])
def test_polynomial_source_and_directed_traction_from_independent_jacobian_hessian(lam, mu, c, lengths):
    settings = domain.manufactured_settings(lame_lambda=lam, lame_mu=mu, reaction=c, lengths=lengths)
    trees = domain._trees(settings["problem"])
    for x, y in ((0., 0.), (.37, .29), lengths):
        u = (x*x*y*y+x+2*y+1, 2*x*x*y*y-3*x+y+2)
        jacobian = ((2*x*y*y+1, 2*x*x*y+2), (4*x*y*y-3, 4*x*x*y+1))
        hessians = (((2*y*y, 4*x*y), (4*x*y, 2*x*x)), ((4*y*y, 8*x*y), (8*x*y, 4*x*x)))
        grad_div = [hessians[0][axis][0]+hessians[1][axis][1] for axis in range(2)]
        for component in range(2):
            laplace = sum(hessians[component][axis][axis] for axis in range(2))
            expected = -mu*laplace-(lam+mu)*grad_div[component]+c*u[component]
            assert domain._value(trees["rhs"][component], (x, y)) == pytest.approx(expected)
        divergence = jacobian[0][0]+jacobian[1][1]
        stress = [[mu*(jacobian[i][j]+jacobian[j][i])+lam*divergence*(i == j) for j in range(2)] for i in range(2)]
        for side, axis in (("xmax", 0), ("ymax", 1)):
            assert [domain._value(tree, (x, y)) for tree in trees[side]] == pytest.approx([stress[component][axis] for component in range(2)])
    # Directions differ; a scalar diffusion flux or magnitude-only comparison cannot pass this.
    assert domain._value(trees["xmax"][0], lengths) != domain._value(trees["xmax"][1], lengths)


def test_harmonic_reference_is_divergence_free_and_literal_zero_vector_is_safe():
    settings = domain.manufactured_settings(case="harmonic", lame_lambda=5., lame_mu=.5)
    assert settings["problem"]["weak_form"]["rhs"] == ["0.0", "0.0"]
    trees = domain._trees(settings["problem"])
    for x, y in ((.37, .29), (2., 1.)):
        assert 2*x-2*x == 0. and (2.-2.) == 0.  # div and each component Laplacian.
        assert [domain._value(tree, (x, y)) for tree in trees["xmax"]] == pytest.approx([2*x, -2*y])
        assert [domain._value(tree, (x, y)) for tree in trees["ymax"]] == pytest.approx([-2*y, -2*x])
    changed = domain.manufactured_settings(case="harmonic", reaction=3.)
    parsed = domain._trees(changed["problem"])
    assert [domain._value(tree, (.37, .29)) for tree in parsed["rhs"]] == pytest.approx([3*domain._value(tree, (.37, .29)) for tree in parsed["reference"]])


def test_declaration_and_normalization_preserve_typed_input_and_vector_semantics():
    settings = small_settings()
    original = deepcopy(settings)
    declaration, normalized = domain.model_declaration(settings), domain.validate_settings(settings)
    assert declaration["case"] == "rectangle_vector_lame"
    assert declaration["model"]["mesh"]["space"] == "vector_lagrange"
    assert declaration["model"]["mesh"]["components"] == ["u0", "u1"]
    assert declaration["outputs"]["fields"] == [{"field": "u", "type": "vector", "components": ["u0", "u1"], "unit": "1"}]
    assert all("neumann_semantics" not in row and row["traction_semantics"] == "sigma(u)*outward_normal" for row in declaration["boundary_conditions"])
    normalized["mesh"]["cell_counts"][0] = 99
    declaration["loads"][0]["expression"][1] = "changed"
    assert settings == original


@pytest.mark.parametrize("path,value", [
    (("problem", "weak_form", "rhs"), ["0.0"]),
    (("problem", "weak_form", "rhs"), ["0.0", 0.]),
    (("problem", "weak_form", "rhs"), ["0.0", "t"]),
    (("problem", "reference", "solution"), ["x[0]", "x[2]"]),
    (("problem", "weak_form", "lame_lambda"), True),
    (("problem", "weak_form", "lame_mu"), 0.),
    (("problem", "weak_form", "reaction"), float("inf")),
    (("problem", "boundaries", "xmax", "value"), ["0.0", "__import__('os').getcwd()"]),
])
def test_both_component_shape_syntax_and_constant_operator_admission(path, value):
    settings = small_settings()
    target = settings
    for key in path[:-1]: target = target[key]
    target[path[-1]] = value
    with pytest.raises(domain.PDEInputError): domain.validate_settings(settings)


def test_second_component_corner_pure_traction_extra_keys_and_unsampled_interior_refuse():
    settings = small_settings()
    settings["problem"]["boundaries"]["xmin"]["value"][1] = "2*x[1]+3"
    with pytest.raises(domain.PDEInputError): domain.validate_settings(settings)
    settings = small_settings()
    for side in domain.SIDES: settings["problem"]["boundaries"][side]["type"] = "neumann"
    with pytest.raises(domain.PDEInputError): domain.validate_settings(settings)
    settings = small_settings()
    settings["problem"]["weak_form"]["plane_stress"] = True
    with pytest.raises(domain.PDEInputError): domain.validate_settings(settings)
    settings = small_settings()
    settings["problem"]["weak_form"]["rhs"][1] = "1/(x[0]-0.5)"
    with pytest.raises(domain.PDEInputError): domain.validate_settings(settings)


def test_complete_directed_fields_and_every_component_rate_use_reused_geometry_checks():
    settings = small_settings()
    studies, fields, bindings = synthetic_vector(settings)
    originals = deepcopy((settings, studies, fields, bindings))
    result = domain.assess(settings, studies, fields, bindings)
    assert all(check["status"] == "PASS" for check in result["checks"])
    assert len(result["metrics"]) == 9 and all(metric["valid"] for metric in result["metrics"].values())
    assert result["metrics"]["component_1_h1_seminorm_error"]["value"] == .15
    assert result["reference"]["h1_semantics"] == "full Frobenius gradient seminorm"
    assert result["pending_validations"] == ["physical_validation", "model_qualification"]
    assert (settings, studies, fields, bindings) == originals
    result["reference"]["components"].pop()
    assert domain.COMPONENTS == ["u0", "u1"]


@pytest.mark.parametrize("kind", ["block", "dof_count", "D_count", "component_order", "field_order", "truncated_field",
                                  "source_swap", "truncated_binding", "traction", "topology", "aggregate", "rate", "nonfinite"])
def test_malformed_directed_observations_cannot_become_numerical_verdicts(kind):
    studies, fields, bindings = synthetic_vector()
    study, field, binding = studies[-1], fields[-1], bindings[-1]
    if kind == "block": study["block_size"] = 1
    elif kind == "dof_count": study["global_dofs"] = study["global_nodes"]
    elif kind == "D_count": study["dirichlet_dofs"] = study["dirichlet_nodes"]
    elif kind == "component_order": study["components"].reverse()
    elif kind == "field_order": field["components"].reverse()
    elif kind == "truncated_field": field["values"][0].pop()
    elif kind == "source_swap": binding["rhs_values"][1].reverse()
    elif kind == "truncated_binding": binding["reference_values"][0].pop()
    elif kind == "traction": field["boundaries"]["xmax"]["prescribed_values"][0][1] += 1.
    elif kind == "topology": field["cell_node_ids"][0] = list(field["cell_node_ids"][1])
    elif kind == "aggregate": study["l2_error"] = study["components"][0]["l2_error"]
    elif kind == "rate": study["components"][1]["l2_convergence_rate"] = 3.
    else: field["values"][0][1] = float("nan")
    with pytest.raises(domain.PDEInputError): domain.assess(small_settings(), studies, fields, bindings)


def test_finite_component_rate_failure_remains_invalid_even_when_vector_rate_passes():
    studies, fields, bindings = synthetic_vector()
    studies[-1]["components"][1]["l2_error"] = .0027
    refresh_errors(studies)
    assert studies[-1]["l2_convergence_rate"] > 1.8
    assert studies[-1]["components"][1]["l2_convergence_rate"] < 1.8
    result = domain.assess(small_settings(), studies, fields, bindings)
    assert next(row for row in result["checks"] if row["code"] == "pde_l2_convergence_rate")["status"] == "FAIL"
    assert all(not metric["valid"] and metric["reason"] for metric in result["metrics"].values())
    studies, fields, bindings = synthetic_vector()
    for study in studies:
        for row in study["components"]: row["l2_error"] = row["h1_seminorm_error"] = 0.
    refresh_errors(studies)
    result = domain.assess(small_settings(), studies, fields, bindings)
    assert all(study["l2_convergence_rate"] is None for study in result["mesh_studies"])
    assert all(not metric["valid"] for metric in result["metrics"].values())


def test_second_component_dirichlet_error_and_actual_residual_are_independent_rejections():
    studies, fields, bindings = synthetic_vector()
    fields[-1]["values"][0][1] += .25
    studies[-1]["components"][1]["boundary_value_error"] = studies[-1]["boundary_value_error"] = .25
    studies[0]["linear_residual"].update(absolute=1e-6, relative=5e-7)
    result = domain.assess(small_settings(), studies, fields, bindings)
    failures = {row["code"] for row in result["checks"] if row["status"] == "FAIL"}
    assert {"pde_boundary_and_mesh", "pde_linear_residual"} <= failures
    assert result["metrics"]["linear_residual_relative"]["value"] == 5e-7
    studies[0]["linear_residual"]["relative"] = 0.
    with pytest.raises(domain.PDEInputError): domain.assess(small_settings(), studies, fields, bindings)
