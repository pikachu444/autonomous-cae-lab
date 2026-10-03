"""Synthetic observations test Domain semantics; no native solver is invoked."""

import copy
import json
import math

import pytest

from plugins.contact_patch import analytical_reference, assess, model_declaration, validate_settings


def settings(young=2e6, displacement=-0.1):
    return {"case": "ssnp121a_frictionless_patch", "material": {"youngs_modulus_pa": young, "poisson_ratio": 0},
            "top_displacement_m": displacement, "limits": {"reference_relative": 0.01, "force_balance_relative": 1e-6}}


def observation(young=2e6, displacement=-0.1):
    # Derive independently of the production reference and preserve signed pressure.
    traction = young * displacement / 2
    return {"samples": {name: {"normal_traction_pa": traction, "vertical_displacement_m": displacement / 2}
                        for name in ("A", "B", "N14")},
            "boundary_reactions_n_per_m": {"top": [0.0, 2 * traction], "bottom": [0.0, -2 * traction],
                                           "all_nodes": [0.0, 0.0]},
            "slave_contact": {"node_ids": [0, 1, *range(3, 14)], "normal_traction_pa": [traction] * 13},
            "projected_gaps_m": [0.0] * 13,
            "fields": {"displacement": {"node_count": 313, "complete": True}, "stress": {"solid_cells": 265}}}


def statuses(result):
    return {check["code"]: check["status"] for check in result["checks"]}


def test_canonical_signed_reference_matches_independent_published_formula():
    reference = analytical_reference(settings())
    assert reference["normal_traction_pa"] == -100000.0
    assert reference["pressure_magnitude_pa"] == 100000.0
    assert reference["interface_vertical_displacement_m"] == -0.05
    assert reference["bulk_vertical_strain"] == -0.05
    assert reference["boundary_reactions_n_per_m"] == {"top": [0.0, -200000.0], "bottom": [0.0, 200000.0],
                                                        "all_nodes": [0.0, 0.0]}
    assert reference["canonical_original_inputs"] is True
    assert reference["nafems_cgs1_replication"] is False
    assert reference["six_published_sample_relative_limits"] == 0.01


@pytest.mark.parametrize("young,displacement", [(1e6, -0.1), (2e6, -0.05), (1e4, -1e-4), (1e9, -0.2)])
def test_variants_have_independent_scaled_reference_and_are_distinguished(young, displacement):
    reference = analytical_reference(settings(young, displacement))
    assert reference["normal_traction_pa"] == pytest.approx(young * displacement / 2)
    assert reference["boundary_reactions_n_per_m"]["top"][1] == pytest.approx(young * displacement)
    assert reference["canonical_original_inputs"] is False
    assert reference["reference_kind"] == "analytical_parameter_variant"
    assert set(statuses(assess(settings(young, displacement), observation(young, displacement))).values()) == {"PASS"}


@pytest.mark.parametrize("path,value", [
    (("case",), "nafems_cgs1"), (("case",), True),
    (("material", "youngs_modulus_pa"), True), (("material", "youngs_modulus_pa"), "2000000"),
    (("material", "youngs_modulus_pa"), 9999), (("material", "youngs_modulus_pa"), 1e9 + 1),
    (("material", "youngs_modulus_pa"), 0), (("material", "youngs_modulus_pa"), -1),
    (("material", "youngs_modulus_pa"), math.inf), (("material", "youngs_modulus_pa"), math.nan),
    (("material", "youngs_modulus_pa"), 10 ** 1000),
    (("material", "poisson_ratio"), 0.3), (("material", "poisson_ratio"), 1e-30),
    (("material", "poisson_ratio"), False), (("material", "poisson_ratio"), "0"),
    (("top_displacement_m",), 0), (("top_displacement_m",), 0.1),
    (("top_displacement_m",), -0.200001), (("top_displacement_m",), -0.00009999),
    (("top_displacement_m",), True), (("top_displacement_m",), "-0.1"),
    (("top_displacement_m",), -math.inf), (("top_displacement_m",), math.nan),
    (("limits", "reference_relative"), 0.010001), (("limits", "reference_relative"), 0.009999),
    (("limits", "force_balance_relative"), 1e-5), (("limits", "force_balance_relative"), 1e-7),
    (("limits", "reference_relative"), "0.01"), (("limits", "force_balance_relative"), False),
])
def test_invalid_or_unsupported_settings_block_before_reference(path, value):
    request = settings()
    container = request
    for key in path[:-1]:
        container = container[key]
    container[path[-1]] = value
    with pytest.raises(ValueError):
        validate_settings(request)


@pytest.mark.parametrize("part", [None, "material", "limits"])
@pytest.mark.parametrize("operation", ["extra", "missing"])
def test_exact_setting_keys(part, operation):
    request = settings()
    target = request if part is None else request[part]
    if operation == "extra":
        target["unadmitted"] = 1
    else:
        target.pop(next(iter(target)))
    with pytest.raises(ValueError):
        validate_settings(request)


def test_normalized_settings_and_references_share_no_mutable_inputs():
    raw = settings()
    normalized = validate_settings(raw)
    assert type(normalized["material"]["poisson_ratio"]) is float
    normalized["material"]["youngs_modulus_pa"] = 123
    normalized["limits"]["reference_relative"] = 999
    assert raw == settings()
    first = analytical_reference(raw)
    first["material"]["youngs_modulus_pa"] = 0
    first["samples"]["A"]["normal_traction_pa"] = 0
    assert analytical_reference(raw)["normal_traction_pa"] == -1e5
    assert analytical_reference(raw)["samples"]["A"]["normal_traction_pa"] == -1e5


def test_declaration_preserves_geometry_nonmatching_mesh_units_and_original_near_zero_coordinate():
    declaration = model_declaration(settings())
    assert declaration["geometry"]["bodies"][0]["y_interval_m"] == [0.0, 1.0]
    assert declaration["geometry"]["bodies"][1]["y_interval_m"] == [-1.0, 0.0]
    assert declaration["mesh"]["slave_contact_segment_count"] == 12
    assert declaration["mesh"]["master_contact_segment_count"] == 11
    assert declaration["mesh"]["boundary_segment_count"] == 92
    assert declaration["mesh"]["documented_boundary_segment_count"] == 132
    assert declaration["mesh"]["coincident_interface_nodes_merged"] is False
    assert declaration["outputs"]["sample_points"]["N14"] == [2.98023223876953e-08, 0.0]
    assert declaration["loads"][0]["values"] == [0.0, -0.1]
    assert declaration["contact"][0]["compression_sign"] == "negative_normal_traction"
    assert "N/m" in {field["unit"] for field in declaration["outputs"]["fields"]}
    serialized = json.dumps(declaration)
    assert all(native not in serialized for native in ("DEFI_CONTACT", "LAGS_C", "D_PLAN", "SIMPSON", "REAC_NODA"))
    declaration["interfaces"][0]["upper_surface"]["x_interval_m"][0] = 999
    assert model_declaration(settings())["interfaces"][0]["upper_surface"]["x_interval_m"] == [-1.0, 1.0]


def test_upstream_nonregression_values_pass_original_six_analytical_gates_only():
    actual = observation()
    actual["samples"]["A"] = {"normal_traction_pa": -1.00080281e5, "vertical_displacement_m": -0.049996701}
    actual["samples"]["B"] = copy.deepcopy(actual["samples"]["A"])
    actual["samples"]["N14"] = {"normal_traction_pa": -1.00350687e5, "vertical_displacement_m": -0.049978357}
    result = assess(settings(), actual)
    published = [check for check in result["checks"] if check["code"].startswith("sample_")]
    assert len(published) == 6
    assert all(check["status"] == "PASS" and check["limit"] == 0.01 for check in published)
    assert result["metrics"]["N14_normal_traction"]["value"] == -1.00350687e5
    assert result["pending_validations"] == [
        "model_qualification", "material_qualification", "physical_validation", "static_strength", "fatigue_durability",
        "pointwise_contact_gap", "cross_solver_contact", "fixture_joint_contact", "corporate_license_approval",
        "corporate_security_approval"]


@pytest.mark.parametrize("sample", ["A", "B", "N14"])
@pytest.mark.parametrize("field", ["normal_traction_pa", "vertical_displacement_m"])
def test_each_published_response_can_fail_independently_and_observation_is_not_substituted(sample, field):
    actual = observation()
    actual["samples"][sample][field] *= 1.02
    result = assess(settings(), actual)
    failed = [key for key, status in statuses(result).items() if status == "FAIL"]
    assert failed == [f"sample_{sample}_{field}"]
    key = f"{sample}_normal_traction" if field == "normal_traction_pa" else f"{sample}_vertical_displacement"
    assert result["metrics"][key]["value"] == actual["samples"][sample][field]
    assert all(not metric["valid"] for metric in result["metrics"].values())


def test_positive_pressure_magnitude_cannot_replace_signed_pressure():
    actual = observation()
    actual["samples"]["A"]["normal_traction_pa"] = 1e5
    result = assess(settings(), actual)
    assert statuses(result)["sample_A_normal_traction_pa"] == "FAIL"
    assert result["metrics"]["A_normal_traction"]["value"] == 1e5
    assert result["metrics"]["max_sample_pressure_relative_error"]["value"] == 2.0


def test_force_balance_checks_vectors_and_cannot_be_masked_by_all_node_zero():
    actual = observation()
    actual["boundary_reactions_n_per_m"]["top"][0] = 0.21  # 0.21/200000 > 1e-6.
    result = assess(settings(), actual)
    assert statuses(result)["boundary_force_balance"] == "FAIL"
    assert statuses(result)["all_nodes_force_balance"] == "PASS"
    actual = observation()
    actual["boundary_reactions_n_per_m"]["all_nodes"][1] = 0.21
    assert statuses(assess(settings(), actual))["all_nodes_force_balance"] == "FAIL"


def test_equal_opposite_wrong_reactions_fail_reference_even_when_balance_passes():
    actual = observation()
    actual["boundary_reactions_n_per_m"]["top"][1] *= 1.02
    actual["boundary_reactions_n_per_m"]["bottom"][1] *= 1.02
    result = assess(settings(), actual)
    assert statuses(result)["boundary_force_balance"] == "PASS"
    assert statuses(result)["top_normal_reaction"] == "FAIL"
    assert statuses(result)["bottom_normal_reaction"] == "FAIL"


@pytest.mark.parametrize("change", [
    lambda o: o.pop("samples"), lambda o: o["samples"].pop("A"),
    lambda o: o["samples"].update(C=o["samples"]["A"]),
    lambda o: o["samples"]["A"].pop("normal_traction_pa"),
    lambda o: o["samples"]["A"].update(normal_traction_pa=True),
    lambda o: o["samples"]["A"].update(vertical_displacement_m=math.nan),
    lambda o: o["boundary_reactions_n_per_m"].pop("all_nodes"),
    lambda o: o["boundary_reactions_n_per_m"].update(top=[0.0]),
    lambda o: o["boundary_reactions_n_per_m"].update(top=[0.0, math.inf]),
    lambda o: o["boundary_reactions_n_per_m"].update(top=[0.0, "-200000"]),
    lambda o: o["slave_contact"].update(node_ids=[1]*13),
    lambda o: o["slave_contact"].update(node_ids=[True, *range(1, 13)]),
    lambda o: o["slave_contact"].update(node_ids=[313, *range(1, 13)]),
    lambda o: o["slave_contact"].update(node_ids=[-1, *range(1, 13)]),
    lambda o: o["slave_contact"].update(normal_traction_pa=[-1e5]*12),
    lambda o: o["slave_contact"]["normal_traction_pa"].__setitem__(5, math.nan),
    lambda o: o.update(projected_gaps_m=[]),
    lambda o: o.update(projected_gaps_m=[False]*13),
    lambda o: o.update(fields=[]), lambda o: o.update(fields={"unknown": math.inf}),
    lambda o: o.update(unadmitted_native_response=0),
])
def test_invalid_missing_nonfinite_or_unpaired_observations_are_rejected(change):
    actual = observation()
    change(actual)
    with pytest.raises(ValueError):
        assess(settings(), actual)


def test_informative_pressure_and_derived_gap_values_do_not_claim_pointwise_qualification():
    actual = observation()
    actual["slave_contact"]["normal_traction_pa"][5] = -2e5
    actual["projected_gaps_m"][4] = -0.002
    actual["projected_gaps_m"][6] = 0.003
    result = assess(settings(), actual)
    assert set(statuses(result).values()) == {"PASS"}
    assert result["metrics"]["slave_normal_traction_min"]["value"] == -2e5
    assert result["metrics"]["derived_projected_gap_min"]["value"] == -0.002
    assert result["metrics"]["derived_projected_gap_max_absolute"]["value"] == 0.003
    assert result["contact_observation"]["pointwise_qualification"] == "UNKNOWN"
    assert result["contact_observation"]["native_measured_gap"] is False
    assert "pointwise_contact_gap" in result["pending_validations"]


@pytest.mark.parametrize("missing", [False, True])
def test_absent_optional_fields_and_gaps_are_not_fabricated(missing):
    actual = observation()
    actual.pop("fields")
    if missing:
        actual.pop("projected_gaps_m")
    else:
        actual["projected_gaps_m"] = None
    result = assess(settings(), actual)
    assert "fields" not in result
    assert result["contact_observation"]["projected_gaps_m"] is None
    metric = result["metrics"]["derived_projected_gap_max_absolute"]
    assert metric["value"] is None and metric["valid"] is False and "UNKNOWN" in metric["reason"]
    assert set(statuses(result).values()) == {"PASS"}


def test_assessment_preserves_input_bytes_and_independent_output_containers():
    request, actual = settings(), observation()
    before = json.dumps([request, actual], sort_keys=True, allow_nan=False)
    result = assess(request, actual)
    assert json.dumps([request, actual], sort_keys=True, allow_nan=False) == before
    result["contact_observation"]["normal_traction_pa"][0] = 0
    result["fields"]["displacement"]["complete"] = False
    result["pending_validations"].clear()
    fresh = assess(request, actual)
    assert fresh["contact_observation"]["normal_traction_pa"][0] == -1e5
    assert fresh["fields"]["displacement"]["complete"] is True
    assert len(fresh["pending_validations"]) == 10


def test_finite_failed_large_response_is_retained_as_invalid_metric():
    actual = observation()
    actual["samples"]["A"]["normal_traction_pa"] = 1e300
    result = assess(settings(), actual)
    assert result["metrics"]["A_normal_traction"] == {
        "value": 1e300, "unit": "Pa", "valid": False,
        "reason": "Contact numerical gates failed: sample_A_normal_traction_pa"}
    assert math.isfinite(result["metrics"]["max_sample_pressure_relative_error"]["value"])
