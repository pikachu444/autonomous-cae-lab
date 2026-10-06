"""Candidate pure coupled admission with explicitly unsolved TEST_ONLY fields."""

from copy import deepcopy
import importlib.util
import math
from pathlib import Path
import sys

import pytest


BUNDLE = Path(__file__).resolve().parents[1]
ROOT = BUNDLE
# Reuse the retained small rectangle/coupled topology fixtures. No native test
# from those modules is collected or run by these candidate test files.
sys.path.insert(0, str(ROOT / "tests"))
from test_pde_coupled_reference import synthetic_coupled
from plugins.pde_coupled import reference as legacy

_SPEC = importlib.util.spec_from_file_location("selected_coupled_candidate_domain", BUNDLE / "plugins/pde_coupled/reference.py")
domain = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(domain)


def selected():
    settings = domain.selected_settings()
    settings["mesh"]["cell_counts"] = [2]
    settings["input_provenance"] = {"origin": "SYNTHETIC", "reference": "TEST_ONLY unsolved parser fixture"}
    return settings


def selected_observations(settings=None):
    """Reuse topology only; no reference is attached to the selected outcome.

    The selected interior field and tiny residual are declared unsolved test
    data. This verifies input/field admission, never actual PDE accuracy.
    """
    settings = settings or selected()
    n = settings["mesh"]["cell_counts"][0]
    geometry = legacy.manufactured_settings(lengths=settings["problem"]["domain"]["lengths"])
    geometry["mesh"]["cell_counts"] = [n, 2*n, 4*n]
    studies, fields, bindings = synthetic_coupled(geometry)
    study, field, binding = deepcopy(studies[0]), deepcopy(fields[0]), deepcopy(bindings[0])
    weak, trees = settings["problem"]["weak_form"], domain._trees(settings["problem"])
    field["values"] = [[-2., 3.] for _ in field["node_ids"]]
    union = set()
    for side in domain.SIDES:
        for region in domain.touching(side):
            segment = field["boundaries"][side][region]
            values = [[domain._value(tree, field["coordinates"][node]) for tree in trees["boundaries"][side][region]]
                      for node in segment["dof_ids"]]
            segment["prescribed_values"] = values
            if settings["problem"]["boundaries"][side]["type"] == "dirichlet":
                for node, value in zip(segment["dof_ids"], values): field["values"][node] = deepcopy(value)
                union.update(segment["dof_ids"])
    field["dirichlet_node_ids"] = sorted(union)
    study.update(dirichlet_nodes=len(union), dirichlet_dofs=2*len(union),
                 region_coefficients=deepcopy(weak["diffusion"]), reaction_matrix=deepcopy(weak["reaction"]))
    for row in [study, *study["components"]]:
        for name in domain._REFERENCE_METRICS: row[name] = None
    for region in domain.REGIONS:
        row = binding["regions"][region]
        row.update(diffusion=deepcopy(weak["diffusion"][region]), reaction=deepcopy(weak["reaction"]),
                   reference_values=None, rhs_values=[
                       [domain._value(tree, field["coordinates"][node]) for tree in trees["rhs"][region]]
                       for node in row["node_ids"]])
    return [study], [field], [binding]


def test_legacy_canonical_defaults_reference_thresholds_and_verdict_are_identical():
    settings = domain.manufactured_settings()
    assert settings == legacy.manufactured_settings()
    assert set(settings) == {"problem", "mesh", "validation"}
    assert settings["mesh"] == {"cell_counts": [8, 16, 32], "degree": 1}
    assert settings["validation"] == {"max_l2_error": .04, "min_l2_rate": 1.8,
        "max_h1_seminorm_error": .8, "min_h1_rate": .9, "max_residual_relative": 1e-10}
    settings["mesh"]["cell_counts"] = [2, 4, 8]
    studies, fields, bindings = synthetic_coupled(settings)
    assert domain.assess(settings, studies, fields, bindings) == legacy.assess(settings, studies, fields, bindings)
    declaration = domain.model_declaration(settings)
    expected = legacy.model_declaration(settings)
    expected["version"] = "1.1"  # Source version only; no canonical input/numerical change.
    assert declaration == expected


def test_selected_factory_has_no_manufactured_reference_sweep_or_physical_interpretation():
    settings = domain.selected_settings()
    assert set(settings) == {"mode", "problem", "mesh", "validation", "input_provenance"}
    assert settings["mode"] == "selected_mesh" and settings["problem"]["reference"] is None
    assert settings["mesh"] == {"cell_counts": [16], "degree": 1}
    assert settings["validation"] == {"max_residual_relative": 1e-10}
    declaration = domain.model_declaration(settings)
    assert declaration["scope"] == domain.SELECTED_SCOPE
    assert declaration["reference"] is None and declaration["input_provenance"] == settings["input_provenance"]
    assert declaration["constitutive_law"]["diffusion_axis"] == "component_rows_of_grad_u"
    assert declaration["outputs"]["fields"][0]["components"] == ["u0", "u1"]
    assert declaration["model"]["geometry"]["unit"] == "1"
    declaration["input_provenance"]["reference"] = "changed"
    assert settings == domain.selected_settings()


def test_arbitrary_signed_safe_rhs_and_whole_component_mixed_side_conditions_are_admitted():
    settings = selected()
    settings["problem"]["weak_form"].update(
        rhs={"left": ["-exp(x[0])+x[1]", "sin(x[1])"], "right": ["2*x[0]-1", "-3"]},
        reaction=[[2., -.5], [-.5, 1.]])
    settings["problem"]["boundaries"]["xmax"] = {"type": "neumann", "value": {"right": ["-2*x[1]", "1"]}}
    settings["problem"]["boundaries"]["xmin"]["value"]["left"] = ["x[1]", "-x[1]"]
    assert domain.validate_settings(settings) == settings
    assert domain._trees(settings["problem"])["reference"] is None


@pytest.mark.parametrize("kind", ["mode", "extra", "provenance_missing", "provenance_unknown", "provenance_blank", "reference",
    "two_meshes", "odd", "zero_mesh", "degree", "residual_bool", "old_validation", "SPD", "PSD", "asymmetric", "nan",
    "unsafe_rhs", "missing_component", "pure_neumann", "partial_boundary", "corner", "interface_trace", "grid_singularity"])
def test_selected_invalid_inputs_refuse_without_reference_or_automatic_repair(kind):
    settings = selected()
    if kind == "mode": settings["mode"] = "benchmark"
    elif kind == "extra": settings["unused_gravity"] = 0
    elif kind == "provenance_missing": settings.pop("input_provenance")
    elif kind == "provenance_unknown": settings["input_provenance"]["origin"] = "INFERRED"
    elif kind == "provenance_blank": settings["input_provenance"]["reference"] = " "
    elif kind == "reference": settings["problem"]["reference"] = legacy.manufactured_settings()["problem"]["reference"]
    elif kind == "two_meshes": settings["mesh"]["cell_counts"] = [2, 4]
    elif kind == "odd": settings["mesh"]["cell_counts"] = [3]
    elif kind == "zero_mesh": settings["mesh"]["cell_counts"] = [0]
    elif kind == "degree": settings["mesh"]["degree"] = True
    elif kind == "residual_bool": settings["validation"]["max_residual_relative"] = True
    elif kind == "old_validation": settings["validation"]["max_l2_error"] = .04
    elif kind == "SPD": settings["problem"]["weak_form"]["diffusion"]["left"] = [[1., 2.], [2., 1.]]
    elif kind == "PSD": settings["problem"]["weak_form"]["reaction"] = [[0., .1], [.1, 0.]]
    elif kind == "asymmetric": settings["problem"]["weak_form"]["diffusion"]["left"][1][0] += 1e-15
    elif kind == "nan": settings["problem"]["weak_form"]["diffusion"]["right"][1][1] = math.nan
    elif kind == "unsafe_rhs": settings["problem"]["weak_form"]["rhs"]["left"][0] = "__import__('os').getcwd()"
    elif kind == "missing_component": settings["problem"]["weak_form"]["rhs"]["right"].pop()
    elif kind == "pure_neumann":
        for side in settings["problem"]["boundaries"].values(): side["type"] = "neumann"
    elif kind == "partial_boundary": settings["problem"]["boundaries"]["xmin"]["components"] = ["u0"]
    elif kind == "corner":
        settings["problem"]["boundaries"]["ymin"]["type"] = "dirichlet"
        settings["problem"]["boundaries"]["ymin"]["value"]["left"][1] = "1"
    elif kind == "interface_trace":
        settings["problem"]["boundaries"]["ymin"] = {"type": "dirichlet", "value": {"left": ["0", "0"], "right": ["x[0]*(2-x[0])", "0"]}}
    else: settings["problem"]["weak_form"]["rhs"]["left"][0] = "1/(x[0]-1)"
    before = deepcopy(settings)
    with pytest.raises(domain.PDEInputError): domain.validate_settings(settings)
    assert settings == before or kind == "nan"


def test_single_full_original_fields_have_null_reference_and_signed_component_metrics():
    settings = selected()
    studies, fields, bindings = selected_observations(settings)
    before = deepcopy((settings, studies, fields, bindings))
    assessment = domain.assess(settings, studies, fields, bindings)
    assert {row["code"] for row in assessment["checks"]} == {
        "pde_boundary_and_mesh", "pde_solution_sync", "pde_solver_convergence", "pde_linear_residual"}
    assert all(row["status"] == "PASS" for row in assessment["checks"])
    assert assessment["reference"]["status"] == "UNKNOWN"
    assert assessment["reference"]["solution"] is None and assessment["reference"]["source"] is None
    assert assessment["reference"]["error_quadrature_degree"] is None
    assert assessment["pending_validations"] == domain.SELECTED_PENDING
    for name in [*domain._REFERENCE_METRICS, *[f"component_{i}_{kind}" for i in range(2) for kind in ("l2_error", "h1_seminorm_error")]]:
        metric = assessment["metrics"][name]
        assert metric["value"] is None and metric["valid"] is False and "Not evaluated" in metric["reason"]
    assert assessment["metrics"]["component_0_field_min"] == {"value": -2., "unit": "1", "valid": True}
    assert assessment["metrics"]["component_1_field_max"] == {"value": 3., "unit": "1", "valid": True}
    assert (settings, studies, fields, bindings) == before
    assert fields[0]["schema_version"] == bindings[0]["schema_version"] == "1"
    assert fields[0]["components"] == ["u0", "u1"] and fields[0]["block_size"] == 2


@pytest.mark.parametrize("kind", ["invented_error", "invented_component_rate", "invented_reference", "truncated_U", "component_order",
    "tag", "adjacency", "node", "axis", "RHS_trace", "matrix", "extra_mesh", "residual_normalization"])
def test_selected_original_topology_operator_and_no_reference_bindings_are_strict(kind):
    settings = selected()
    studies, fields, bindings = selected_observations(settings)
    if kind == "invented_error": studies[0]["l2_error"] = 0.
    elif kind == "invented_component_rate": studies[0]["components"][0]["l2_convergence_rate"] = 2.
    elif kind == "invented_reference": bindings[0]["regions"]["left"]["reference_values"] = [[0., 0.]] * len(bindings[0]["regions"]["left"]["node_ids"])
    elif kind == "truncated_U": fields[0]["values"][0].pop()
    elif kind == "component_order": fields[0]["components"].reverse()
    elif kind == "tag": fields[0]["cell_regions"][0] = "right"
    elif kind == "adjacency": fields[0]["interface"]["adjacent_cell_ids"][0].reverse()
    elif kind == "node": bindings[0]["regions"]["right"]["node_ids"].remove(fields[0]["interface"]["node_ids"][0])
    elif kind == "axis": fields[0]["interface"]["plus_x_normal"] = [-1., 0.]
    elif kind == "RHS_trace": bindings[0]["regions"]["left"]["rhs_values"][-1][1] = 0.
    elif kind == "matrix": studies[0]["region_coefficients"]["left"][0][0] = 3.
    elif kind == "extra_mesh": studies.append(deepcopy(studies[0]))
    else: studies[0]["linear_residual"]["relative"] = 0.
    with pytest.raises(domain.PDEInputError): domain.assess(settings, studies, fields, bindings)


@pytest.mark.parametrize("kind", ["residual", "boundary", "KSP", "sync"])
def test_numerical_failures_invalidate_actual_component_metrics_without_changing_limits(kind):
    settings = selected()
    studies, fields, bindings = selected_observations(settings)
    if kind == "residual": studies[0]["linear_residual"].update(absolute=1e-6, relative=5e-7)
    elif kind == "boundary":
        fields[0]["values"][0][0] += .25
        studies[0]["boundary_value_error"] = studies[0]["components"][0]["boundary_value_error"] = .25
    elif kind == "KSP": studies[0]["ksp_convergence_reason"] = -3
    else: studies[0]["solution_sync_error"] = .1
    assessment = domain.assess(settings, studies, fields, bindings)
    assert any(row["status"] == "FAIL" for row in assessment["checks"])
    assert all(not metric["valid"] for metric in assessment["metrics"].values())
    assert settings["validation"] == {"max_residual_relative": 1e-10}


def test_bounded_symmetric_input_binding_changes_only_declared_locations_and_model_effect():
    settings = selected()
    before = deepcopy(settings)
    descriptors = domain.describe_inputs(settings)
    assert len(descriptors) == 11 and all(item["unit"] == "1" for item in descriptors)
    coupled = next(item for item in descriptors if item["id"] == "diffusion_left_01")
    assert coupled["settings_mirrors"] == [["problem", "weak_form", "diffusion", "left", 1, 0]]
    assert len(coupled["declaration_paths"]) == 2
    assignments = {"length_0": 3., "diffusion_left_01": -.25, "reaction_00": 1., "reaction_11": 2., "reaction_01": -.5}
    bound = domain.bind_inputs(settings, assignments)
    assert bound["problem"]["weak_form"]["diffusion"]["left"] == [[2., -.25], [-.25, 1.]]
    assert bound["problem"]["weak_form"]["reaction"] == [[1., -.5], [-.5, 2.]]
    assert bound["problem"]["domain"]["lengths"] == [3., 1.]
    expected = deepcopy(settings)
    for item in descriptors:
        if item["id"] not in assignments: continue
        for path in [item["settings_path"], *item.get("settings_mirrors", [])]:
            cursor = expected
            for key in path[:-1]: cursor = cursor[key]
            cursor[path[-1]] = assignments[item["id"]]
    assert expected == bound and settings == before
    declarations = [domain.model_declaration(settings), domain.model_declaration(bound)]
    assert declarations[0] != declarations[1]
    assert declarations[1]["constitutive_law"]["diffusion"]["left"]["value"] == [[2., -.25], [-.25, 1.]]
    assert declarations[1]["input_provenance"] == settings["input_provenance"]
    after = {item["id"]: item for item in domain.describe_inputs(bound)}
    assert all(after[item["id"]] == {**item, "value": assignments.get(item["id"], item["value"])} for item in descriptors)


@pytest.mark.parametrize("values", [{}, {"unadvertised": 1}, {"length_0": True}, {"length_1": math.nan},
    {"length_0": .0001}, {"diffusion_left_01": 2.}, {"diffusion_left_00": .01},
    {"reaction_01": .1}, {"diffusion_right_00": math.inf}])
def test_binding_refuses_unknown_nonfinite_bounds_or_incompatible_spd_psd_before_execution(values):
    settings = selected()
    before = deepcopy(settings)
    with pytest.raises(domain.PDEInputError): domain.bind_inputs(settings, values)
    assert settings == before
