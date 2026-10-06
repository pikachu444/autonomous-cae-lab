"""Pure Domain input scenarios on a TEST_ONLY catalog; no CAD/native execution."""

from copy import deepcopy
import math
import re
import sys

import pytest

from plugins.elasticity import native_condition_inputs as inputs
from plugins.elasticity import native_conditions


@pytest.fixture
def model():
    catalog = {
        "cad_backend": "fixture.freecad", "cad_revision": "a" * 64,
        "coordinate_systems": [{"id": "global", "basis": [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
                                "world_alignment": "UNKNOWN"}],
        "selections": [
            {"id": "B-final", "kind": "whole_final_solid", "roles": ["material"]},
            {"id": "F-fixed", "kind": "native_face", "roles": ["boundary", "load"],
             "native_object": "Final", "native_name": "Face1", "geometry_sha256": "b" * 64,
             "bounds_mm": {"min": [0, 0, 0], "max": [0, 10, 8]}},
            {"id": "F-load", "kind": "native_face", "roles": ["boundary", "load"],
             "native_object": "Final", "native_name": "Face6", "geometry_sha256": "c" * 64,
             "bounds_mm": {"min": [16, 0, 0], "max": [16, 10, 8]}},
        ],
    }
    declaration = {
        "analysis_type": "linear_static", "coordinate_system": "global",
        "units": {"length": "mm", "force": "N", "stress": "MPa"},
        "materials": [{"id": "M1", "selection_id": "B-final", "law": "isotropic_linear_elastic",
                       "young_modulus_MPa": 210000.0, "poisson_ratio": 0.3,
                       "source": {"category": "MEASURED_REPORTED", "description": "TEST_ONLY user-reported coupon source"}}],
        "boundary_conditions": [{"id": "BC1", "selection_id": "F-fixed", "type": "displacement",
                                 "components": {"UX": 0, "UZ": -0.01}, "unit": "mm",
                                 "coordinate_system": "global", "source": "TEST_ONLY partial displacement constraint"}],
        "loads": [{"id": "L1", "selection_id": "F-load", "type": "resultant_force",
                   "components": {"FX": 0, "FY": -15, "FZ": -150}, "unit": "N",
                   "coordinate_system": "global", "source": "TEST_ONLY user-reported force setting"}],
        "contact": {"mode": "none", "source": "TEST_ONLY one solid, no contact", "pairs": []},
        "mesh": {"mode": "selected", "max_size_mm": 4},
    }
    return catalog, declaration


def test_descriptors_are_scalar_item_bound_and_nonmutating(model):
    catalog, declaration = model
    original = deepcopy(model)
    descriptors = inputs.describe(catalog, declaration)
    assert [item["id"] for item in descriptors] == [
        "material_M1_E", "material_M1_nu", "load_L1_FX", "load_L1_FY", "load_L1_FZ"]
    assert [item["unit"] for item in descriptors] == ["MPa", "1", "N", "N", "N"]
    assert descriptors[0]["declaration_path"] == ["materials", 0, "young_modulus_MPa"]
    assert descriptors[-1]["declaration_path"] == ["loads", 0, "components", "FZ"]
    for descriptor in descriptors:
        assert set(descriptor) == {"id", "label", "unit", "value", "lower", "upper", "declaration_path"}
        assert descriptor["lower"] <= descriptor["value"] <= descriptor["upper"]
        assert descriptor["lower"] < descriptor["upper"]
        assert math.isfinite(descriptor["upper"] - descriptor["lower"])
        assert "numerical bounds" in descriptor["label"] and "UNKNOWN" in descriptor["label"]
    descriptors[0]["declaration_path"][0] = "mesh"
    assert model == original
    assert inputs.describe(catalog, declaration)[0]["declaration_path"][0] == "materials"


def test_apply_only_selected_leaves_and_sources_preserves_entire_fixed_context(model):
    catalog, declaration = model
    original = deepcopy(model)
    assignments = {"material_M1_E": 180000.0, "material_M1_nu": -0.2, "load_L1_FZ": -200.0}
    bound = inputs.apply(catalog, declaration, assignments)
    assert bound is not declaration
    assert model == original
    expected = deepcopy(declaration)
    expected["materials"][0]["young_modulus_MPa"] = 180000.0
    expected["materials"][0]["poisson_ratio"] = -0.2
    expected["materials"][0]["source"] = bound["materials"][0]["source"]
    expected["loads"][0]["components"]["FZ"] = -200.0
    expected["loads"][0]["source"] = bound["loads"][0]["source"]
    assert bound == expected
    assert "UY" not in bound["boundary_conditions"][0]["components"]
    assert bound["loads"][0]["components"] == {"FX": 0, "FY": -15, "FZ": -200.0}
    assert assignments == {"material_M1_E": 180000.0, "material_M1_nu": -0.2, "load_L1_FZ": -200.0}
    bound["mesh"]["max_size_mm"] = 99
    assert declaration["mesh"]["max_size_mm"] == 4


@pytest.mark.parametrize("category", ["ASSUMED", "MEASURED_REPORTED", "PUBLISHED_REFERENCE"])
def test_changed_material_retains_original_source_but_is_assumed_scenario(model, category):
    catalog, declaration = model
    declaration["materials"][0]["source"]["category"] = category
    source = deepcopy(declaration["materials"][0]["source"])
    bound = inputs.apply(catalog, declaration, {"material_M1_E": 180000})
    reported = bound["materials"][0]["source"]
    assert reported["category"] == "ASSUMED"
    assert "ASSUMED numerical scenario" in reported["description"]
    assert "qualification UNKNOWN" in reported["description"]
    assert f"Original source ({category}): {source['description']}" in reported["description"]
    assert declaration["materials"][0]["source"] == source
    assert bound["loads"][0]["source"] == declaration["loads"][0]["source"]


def test_force_scenario_retains_exact_text_and_does_not_change_material_source(model):
    catalog, declaration = model
    original = declaration["loads"][0]["source"] = "시험기 표시 -150 N\n실측 검증은 미완료"
    bound = inputs.apply(catalog, declaration, {"load_L1_FZ": -175})
    assert bound["loads"][0]["source"].endswith(original)
    assert "ASSUMED numerical scenario; qualification UNKNOWN" in bound["loads"][0]["source"]
    assert bound["materials"][0] == declaration["materials"][0]


def test_unchanged_values_retain_exact_source_and_deepcopy(model):
    catalog, declaration = model
    bound = inputs.apply(catalog, declaration, {"material_M1_E": 210000, "load_L1_FZ": -150.0})
    assert bound == declaration
    assert bound is not declaration and bound["materials"][0] is not declaration["materials"][0]


@pytest.mark.parametrize("assignments", [
    {}, [], {"mesh.max_size_mm": 2}, {"materials.0.young_modulus_MPa": 180000},
    {"boundary_BC1_UX": 0.1}, {"load_L1_unit": 1}, {"material_M1_source": 1},
    {"load_L1_FZ": {"value": -175, "unit": "kN"}}, {"load_L1_FZ": "-175"},
    {"load_L1_FZ": True}, {"material_M1_E": False}, {"material_M1_nu": math.nan},
    {"load_L1_FZ": math.inf}, {"material_M1_E": 10 ** 400},
    {"material_M1_E": 0}, {"material_M1_E": -1}, {"material_M1_nu": -1},
    {"material_M1_nu": 0.5}, {"load_L1_FZ": -1501},
    {"load_L1_FZ": -200, "coordinate_system": 1},
])
def test_unadvertised_nonfinite_and_out_of_bounds_assignments_fail_without_mutation(model, assignments):
    catalog, declaration = model
    original = deepcopy(model)
    with pytest.raises(ValueError):
        inputs.apply(catalog, declaration, assignments)
    assert model == original


@pytest.mark.parametrize("path,value", [
    (["units", "force"], "kN"), (["units", "stress"], "Pa"),
    (["materials", 0, "law"], "orthotropic"), (["loads", 0, "unit"], "kN"),
    (["loads", 0, "type"], "pressure"), (["loads", 0, "coordinate_system"], "world"),
    (["boundary_conditions", 0, "unit"], "m"), (["coordinate_system"], "sensor"),
    (["analysis_type"], "nonlinear_static"), (["mesh", "mode"], "sweep"),
    (["materials", 0, "young_modulus_MPa"], True),
    (["materials", 0, "poisson_ratio"], math.nan), (["loads", 0, "components", "FX"], True),
    (["mesh", "max_size_mm"], math.inf), (["mesh", "max_size_mm"], 0),
    (["materials", 0, "source", "category"], "QUALIFIED"),
])
def test_bad_baseline_contract_or_domain_is_not_advertised(model, path, value):
    catalog, declaration = model
    cursor = declaration
    for key in path[:-1]:
        cursor = cursor[key]
    cursor[path[-1]] = value
    with pytest.raises(ValueError):
        inputs.describe(catalog, declaration)
    with pytest.raises(ValueError):
        inputs.apply(catalog, declaration, {"material_M1_E": 180000})


def test_candidate_zero_resultants_reuses_domain_projection_before_execution(model, monkeypatch):
    catalog, declaration = model
    calls = []
    project = native_conditions.project

    def capture(catalog, candidate):
        calls.append(deepcopy(candidate))
        return project(catalog, candidate)

    monkeypatch.setattr(native_conditions, "project", capture)
    with pytest.raises(ValueError):
        inputs.apply(catalog, declaration, {"load_L1_FY": 0, "load_L1_FZ": 0})
    assert len(calls) == 1
    assert calls[0]["loads"][0]["components"] == {"FX": 0, "FY": 0, "FZ": 0}
    assert "ASSUMED numerical scenario" in calls[0]["loads"][0]["source"]
    assert declaration["loads"][0]["components"]["FZ"] == -150


def test_unsupported_contact_model_or_missing_boundary_cannot_advertise(model):
    catalog, declaration = model
    for unsupported in ("contact", "model", "boundary", "selection", "missing_component"):
        changed_catalog, changed = deepcopy(model)
        if unsupported == "contact":
            changed["contact"] = {"mode": "bonded", "source": "TEST_ONLY unsupported assembly",
                                  "pairs": [{"selection_a": "F-fixed", "selection_b": "F-load"}]}
        elif unsupported == "model":
            changed_catalog["cad_backend"] = "fixture.cadquery"
        elif unsupported == "boundary":
            changed["boundary_conditions"] = []
        elif unsupported == "selection":
            changed["loads"][0]["selection_id"] = "F-old-revision"
        else:
            del changed["loads"][0]["components"]["FX"]
        with pytest.raises(ValueError):
            inputs.describe(changed_catalog, changed)
    assert catalog["cad_backend"] == "fixture.freecad"
    assert declaration["contact"]["mode"] == "none"


def test_item_ids_survive_load_reorder_and_long_ids_cannot_alias(model):
    catalog, declaration = model
    long_prefix = "L" + "a" * 78
    declaration["loads"][0]["id"] = long_prefix + "x"
    other = deepcopy(declaration["loads"][0])
    other["id"] = long_prefix + "y"
    other["components"]["FZ"] = 100
    declaration["loads"].append(other)
    before = inputs.describe(catalog, declaration)
    declaration["loads"].reverse()
    after = inputs.describe(catalog, declaration)
    before_ids = {item["id"] for item in before}
    assert len(before_ids) == 8
    assert before_ids == {item["id"] for item in after}
    assert all(re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,63}", item["id"]) for item in before)
    target = next(item for item in after if item["declaration_path"] == ["loads", 1, "components", "FZ"])
    bound = inputs.apply(catalog, declaration, {target["id"]: -175})
    assert bound["loads"][1]["components"]["FZ"] == -175
    assert bound["loads"][0] == declaration["loads"][0]
    declaration["materials"][0]["id"] = "NewMaterial"
    assert inputs.describe(catalog, declaration)[0]["id"] == "material_NewMaterial_E"


@pytest.mark.parametrize("source_group", ["materials", "loads"])
def test_source_limit_refuses_truncation_and_preserves_original(model, source_group):
    catalog, declaration = model
    if source_group == "materials":
        declaration["materials"][0]["source"]["description"] = "a" * 2048
        name, value = "material_M1_E", 180000
    else:
        declaration["loads"][0]["source"] = "가" * 2048
        name, value = "load_L1_FZ", -175
    original = deepcopy(model)
    assert inputs.describe(catalog, declaration)
    with pytest.raises(ValueError, match="contract"):
        inputs.apply(catalog, declaration, {name: value})
    assert model == original


@pytest.mark.parametrize("modulus", [math.nextafter(0.0, 1.0), sys.float_info.max])
def test_extreme_finite_constants_have_contained_finite_numeric_bounds(model, modulus):
    catalog, declaration = model
    declaration["materials"][0]["young_modulus_MPa"] = modulus
    descriptor = inputs.describe(catalog, declaration)[0]
    assert 0 < descriptor["lower"] <= modulus <= descriptor["upper"]
    assert descriptor["lower"] < descriptor["upper"]
    assert math.isfinite(descriptor["upper"] - descriptor["lower"])


def test_multiple_changes_are_order_independent_and_only_mark_source_once(model):
    catalog, declaration = model
    values = {"material_M1_E": 180000, "material_M1_nu": 0.25, "load_L1_FY": -30, "load_L1_FZ": -175}
    bound = inputs.apply(catalog, declaration, values)
    assert bound == inputs.apply(catalog, declaration, dict(reversed(list(values.items()))))
    assert bound["materials"][0]["source"]["description"].count("ASSUMED numerical scenario") == 1
    assert bound["loads"][0]["source"].count("ASSUMED numerical scenario") == 1


@pytest.mark.parametrize("constrained,value", [("UY", 0), ("UY", -0.01), ("UZ", 0)])
def test_adjacent_load_and_partial_boundary_block_only_matching_axis_before_native(model, constrained, value):
    catalog, declaration = model
    load = declaration["loads"][0]
    load["components"] = {"FX": 150, "FY": 0, "FZ": 0}
    adjacent = deepcopy(catalog["selections"][1])
    adjacent.update(id="F-adjacent", native_name="Face3",
                    bounds_mm={"min": [0, 0, 0], "max": [16, 0, 8]})
    catalog["selections"].append(adjacent)
    declaration["boundary_conditions"].append({**deepcopy(declaration["boundary_conditions"][0]),
        "id": "BC2", "selection_id": "F-adjacent", "components": {constrained: value}})
    original = deepcopy(model)
    blocked = "load_L1_F" + constrained[-1]
    descriptors = inputs.describe(catalog, declaration)
    assert blocked not in {item["id"] for item in descriptors}
    assert "load_L1_FX" in {item["id"] for item in descriptors}
    assert inputs.apply(catalog, declaration, {"load_L1_FX": -200})["loads"][0]["components"]["FX"] == -200
    with pytest.raises(ValueError, match="advertised"):
        inputs.apply(catalog, declaration, {blocked: 100})
    assert model == original
    load["components"]["F" + constrained[-1]] = -100
    with pytest.raises(ValueError, match="before native execution"):
        inputs.describe(catalog, declaration)


@pytest.mark.parametrize("bounds", [None, {"min": [0, 0, 0], "max": [16, 10, 8]},
    {"min": [16 + 1e-8, 0, 0], "max": [16 + 1e-8, 10, 8]},
    {"min": [float('nan'), 0, 0], "max": [0, 10, 8]},
    {"min": [17, 0, 0], "max": [16, 10, 8]}])
def test_unresolved_overlapping_near_or_invalid_bounds_do_not_admit_force_scenarios(model, bounds):
    catalog, declaration = model
    catalog["selections"][1]["bounds_mm"] = bounds
    with pytest.raises(ValueError, match="not verified separated"):
        inputs.describe(catalog, declaration)
    with pytest.raises(ValueError, match="before native execution"):
        inputs.apply(catalog, declaration, {"material_M1_E": 180000})


def test_overlapping_faces_do_not_block_an_unconstrained_direction_or_invent_a_dof(model):
    catalog, declaration = model
    catalog["selections"][1]["bounds_mm"] = {"min": [0, 0, 0], "max": [16, 10, 8]}
    declaration["boundary_conditions"][0]["components"] = {"UX": 0}
    declaration["loads"][0]["components"] = {"FX": 0, "FY": -15, "FZ": -150}
    descriptors = inputs.describe(catalog, declaration)
    assert {item["id"] for item in descriptors} == {
        "material_M1_E", "material_M1_nu", "load_L1_FY", "load_L1_FZ"}
    bound = inputs.apply(catalog, declaration, {"load_L1_FY": -30})
    assert bound["boundary_conditions"][0]["components"] == {"UX": 0}
    assert declaration["loads"][0]["components"]["FY"] == -15
