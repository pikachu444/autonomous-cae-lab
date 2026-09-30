"""Independent known-number and rejection checks for the uniaxial J2 reference."""

import copy
import json
import math

import pytest

from plugins.elasticity import plasticity_reference as reference


def _settings():
    return {"case": "uniaxial_j2_isotropic_hardening", "dimensions_mm": [20, 4, 2],
            "material": {"youngs_modulus_mpa": 210000, "poisson_ratio": 0.3,
                         "yield_stress_mpa": 250, "plastic_modulus_mpa": 1000},
            "history": {"times_s": list(range(10)),
                        "axial_strain": [0, .0005, .001, .0015, .002, .003, .006, .0055, .005, .0045]},
            "mesh_sizes_mm": [2, 1],
            "limits": {"displacement_relative": 1e-7, "displacement_absolute_mm": 1e-10,
                       "stress_relative": 1e-7, "stress_absolute_mpa": 1e-8,
                       "plastic_strain_absolute": 1e-9, "reaction_relative": 1e-7,
                       "reaction_absolute_n": 1e-8, "mesh_agreement_relative": 1e-7,
                       "plastic_dissipation_relative": 1e-6, "plastic_dissipation_absolute_mpa": 1e-8}}


# Hand-calculated tensile loading values: total strain = sigma/E + q,
# sigma = 250 + 1000*q. Unloading subtracts 105 MPa per .0005 strain.
# These observations never call the implementation's reference functions.
_KNOWN_Q = [0, 0, 0, 65 / 211000, 170 / 211000, 380 / 211000,
            1010 / 211000, 1010 / 211000, 1010 / 211000, 1010 / 211000]
_KNOWN_STRESS = [0, 105, 210, 250.3080568720379, 250.8056872037915,
                 251.8009478672986, 254.7867298578199, 149.7867298578199,
                 44.7867298578199, -60.2132701421801]
_CHANGED_Q = [0, 0, 10 / 212000, 115 / 212000, 220 / 212000, 430 / 212000,
              .005, .005, .005, .005]
# With yield=200 and H=2000, q=.005 gives sigma=200+2000*.005=210 MPa.
_CHANGED_STRESS = [0, 105, 200.0943396226415, 201.0849056603774,
                   202.0754716981132, 204.0566037735849, 210, 105, 0, -105]


def _records(settings=None, *, plastic=None, stress=None):
    settings = _settings() if settings is None else settings
    plastic = _KNOWN_Q if plastic is None else plastic
    stress = _KNOWN_STRESS if stress is None else stress
    length, breadth, height = settings["dimensions_mm"]
    young = settings["material"]["youngs_modulus_mpa"]
    poisson = settings["material"]["poisson_ratio"]
    coords = [[0, 0, 0], [length, 0, 0], [0, breadth, 0], [length, breadth, 0],
              [0, 0, height], [length, 0, height], [0, breadth, height],
              [length, breadth, height], [length / 2, breadth / 2, height / 2]]
    states = []
    for time, strain, q, sigma in zip(settings["history"]["times_s"], settings["history"]["axial_strain"], plastic, stress):
        lateral = -poisson * sigma / young - 0.5 * q
        states.append({"time_s": time,
                       "displacements_mm": [[strain * x, lateral * y, lateral * z] for x, y, z in coords],
                       "stresses_mpa": [[sigma, 0, 0, 0, 0, 0] for _ in range(10)],
                       "eq_plastic_strain": [q] * 10, "reaction_n": [-sigma * breadth * height, 0, 0]})
    return [{"mesh_size_mm": size, "node_ids": list(range(1, 10)), "coordinates_mm": copy.deepcopy(coords),
             "element_count": 2, "states": copy.deepcopy(states)} for size in settings["mesh_sizes_mm"]]


def _check(result, code):
    return next(item for item in result["checks"] if item["code"] == code)


def _assert_invalid(result, code):
    assert _check(result, code)["status"] == "FAIL"
    assert all(not item["valid"] and code in item["reason"] for item in result["metrics"].values())
    assert all(item["value"] is not None and math.isfinite(item["value"]) for item in result["metrics"].values())
    json.dumps(result, allow_nan=False)


def test_closed_reference_known_peak_and_negative_elastic_unload():
    result = reference.analytical_reference(_settings())
    assert result["peak_index"] == 6
    assert result["stress_component_order"] == ["xx", "yy", "zz", "xy", "xz", "yz"]
    peak, final = result["history"][6], result["history"][-1]
    assert peak["eq_plastic_strain"] == pytest.approx(.004786729857819905, abs=1e-15)
    assert peak["plastic_axial_strain"] == peak["eq_plastic_strain"]
    assert peak["stress_components_mpa"] == pytest.approx([254.7867298578199, 0, 0, 0, 0, 0], abs=1e-10)
    assert final["stress_components_mpa"][0] == pytest.approx(-60.2132701421801, abs=1e-10)
    assert final["reaction_n"] == pytest.approx([481.7061611374408, 0, 0], abs=1e-9)
    assert peak["displacement_gradient"][0] == .006
    assert peak["displacement_gradient"][1:] == pytest.approx(
        [-.3 * 254.7867298578199 / 210000 - .5 * .004786729857819905] * 2, abs=1e-15)
    for state in result["history"][7:]:
        assert state["eq_plastic_strain"] == peak["eq_plastic_strain"]
        assert state["plastic_work_density_mpa"] == peak["plastic_work_density_mpa"]
        assert state["hardening_energy_density_mpa"] == pytest.approx(500 * (1010 / 211000) ** 2)
        assert state["plastic_dissipation_density_mpa"] == pytest.approx(1.1966824644549763)
        assert state["plastic_work_density_mpa"] == pytest.approx(
            state["hardening_energy_density_mpa"] + state["plastic_dissipation_density_mpa"])
    assert result["units"]["energy_density"] == "MPa"
    json.dumps(result, allow_nan=False)


def test_exact_canonical_observations_pass_with_scalar_metrics_and_unknown_release_gates():
    result = reference.assess(_settings(), _records())
    assert all(item["status"] == "PASS" for item in result["checks"])
    assert all(item["valid"] for item in result["metrics"].values())
    expected = {"peak_stress": (254.7867298578199, "MPa"), "final_stress": (-60.2132701421801, "MPa"),
                "peak_eq_plastic_strain": (.004786729857819905, "1"),
                "unload_residual_strain": (.004786729857819905, "1"),
                "plastic_dissipation_density": (1.1966824644549763, "MPa"),
                "reaction_x": (481.7061611374408, "N"), "mesh_agreement_relative": (0, "1")}
    for name, (value, unit) in expected.items():
        assert result["metrics"][name]["value"] == pytest.approx(value, abs=1e-9)
        assert result["metrics"][name]["unit"] == unit
    assert set(result["pending_validations"]) == {"static_strength", "material_qualification", "model_qualification",
                                                   "physical_validation", "fatigue_durability"}
    assert not any("convergence" in name or "order" in name or "rate" in name for name in result["metrics"])
    assert result["mesh_studies"][0]["stress_point_count"] == 10
    assert result["mesh_studies"][0]["right_face_node_count"] == 4
    assert result["derived_energy"]["native_energy_field"] is False
    assert result["derived_energy"]["physical_energy_balance"] is False
    json.dumps(result, allow_nan=False)


def test_changed_yield_and_hardening_are_independently_known_and_zero_stress_is_safe():
    settings = _settings()
    settings["material"].update(yield_stress_mpa=200, plastic_modulus_mpa=2000)
    analytical = reference.analytical_reference(settings)
    assert analytical["history"][6]["eq_plastic_strain"] == pytest.approx(.005, abs=1e-15)
    assert analytical["history"][6]["stress_components_mpa"][0] == pytest.approx(210, abs=1e-10)
    assert analytical["history"][8]["stress_components_mpa"][0] == 0
    assert analytical["history"][-1]["stress_components_mpa"][0] == pytest.approx(-105, abs=1e-10)
    result = reference.assess(settings, _records(settings, plastic=_CHANGED_Q, stress=_CHANGED_STRESS))
    assert all(item["status"] == "PASS" for item in result["checks"])
    assert result["metrics"]["plastic_dissipation_density"]["value"] == pytest.approx(1)


def test_changed_geometry_and_poisson_ratio_keep_reactions_and_lateral_fields_physical():
    settings = _settings()
    settings["dimensions_mm"] = [24, 6, 3]
    settings["mesh_sizes_mm"] = [3, 1.5, .75]
    settings["material"]["poisson_ratio"] = -.2
    result = reference.assess(settings, _records(settings))
    assert all(item["status"] == "PASS" for item in result["checks"])
    assert result["metrics"]["reaction_x"]["value"] == pytest.approx(1083.8388625592418)
    assert len(result["mesh_studies"]) == 3


def test_first_yield_crossing_work_uses_yield_boundary_not_prior_elastic_sample():
    result = reference.assess(_settings(), _records())
    first_plastic = result["mesh_studies"][0]["states"][3]
    q = 65 / 211000
    expected = 250 * q + 500 * q**2
    assert first_plastic["plastic_work_density_mpa"] == pytest.approx([expected] * 10, abs=1e-14)
    wrong_elastic_endpoint = .5 * (210 + 250.3080568720379) * q
    assert first_plastic["plastic_work_density_mpa"][0] != pytest.approx(wrong_elastic_endpoint)
    assert result["derived_energy"]["first_plastic_entry_lower_stress_mpa"] == 250
    assert result["derived_energy"]["subsequent_lower_stress"] == "previous_native_stress_xx"
    for observed, exact in zip(result["mesh_studies"][0]["states"], result["reference"]["history"]):
        assert observed["plastic_dissipation_density_mpa"] == pytest.approx(
            [exact["plastic_dissipation_density_mpa"]] * 10, abs=1e-13)


@pytest.mark.parametrize("state,field,row,column,change,code", [
    (0, "displacements_mm", 8, 2, 1e-5, "analytical_displacement"),
    (4, "displacements_mm", 8, 1, -1e-5, "analytical_displacement"),
    (0, "stresses_mpa", 9, 1, .02, "analytical_stress"),
    (6, "stresses_mpa", 9, 5, -.02, "analytical_stress"),
    (3, "eq_plastic_strain", 9, None, .0001, "analytical_eq_plastic_strain"),
    (9, "reaction_n", 1, None, .1, "signed_reaction_balance"),
])
def test_every_time_component_node_and_material_variable_point_is_compared(state, field, row, column, change, code):
    records = _records()
    values = records[0]["states"][state][field]
    if column is None:
        values[row] += change
    else:
        values[row][column] += change
    result = reference.assess(_settings(), records)
    _assert_invalid(result, code)


def test_unloading_requires_constant_q_at_every_point_even_with_imposed_dx_correct():
    records = _records()
    records[0]["states"][8]["eq_plastic_strain"][9] += 1e-5
    result = reference.assess(_settings(), records)
    _assert_invalid(result, "elastic_unloading_plastic_strain")
    assert _check(result, "plastic_strain_monotonic")["status"] == "FAIL"
    assert result["metrics"]["max_component_displacement_error"]["value"] < 1e-14


def test_residual_strain_subtracts_elastic_stress_from_right_face_dx_at_all_unload_times():
    records = _records()
    for row in records[0]["states"][7]["stresses_mpa"]:
        row[0] += 1
    result = reference.assess(_settings(), records)
    _assert_invalid(result, "unload_residual_strain")
    assert _check(result, "unload_residual_strain")["observed"] == pytest.approx(1 / 210000)
    assert result["metrics"]["unload_residual_strain"]["value"] == pytest.approx(1010 / 211000)


def test_negative_finite_material_variable_and_dissipation_remain_numeric_failures():
    records = _records()
    records[0]["states"][0]["eq_plastic_strain"][0] = -1e-5
    result = reference.assess(_settings(), records)
    _assert_invalid(result, "plastic_strain_nonnegative")
    assert _check(result, "plastic_dissipation_nonnegative")["status"] == "FAIL"
    initial = result["mesh_studies"][0]["states"][0]
    assert initial["min_eq_plastic_strain"] == -1e-5
    assert initial["plastic_dissipation_density_mpa"][0] == pytest.approx(-5e-8)


def test_negative_derived_work_is_retained_and_invalidates_all_metrics():
    records = _records()
    for row in records[-1]["states"][6]["stresses_mpa"]:
        row[0] = -100000
    result = reference.assess(_settings(), records)
    _assert_invalid(result, "plastic_work_nonnegative")
    assert _check(result, "plastic_dissipation_nonnegative")["status"] == "FAIL"
    assert result["metrics"]["plastic_work_density"]["value"] < 0
    assert result["metrics"]["plastic_dissipation_density"]["value"] < 0
    assert result["mesh_studies"][-1]["states"][6]["plastic_work_density_mpa"][0] < 0


def test_dissipation_check_uses_native_stress_rather_than_reference_work_substitution():
    settings = _settings()
    settings["limits"]["stress_relative"] = 1
    records = _records()
    for row in records[0]["states"][4]["stresses_mpa"]:
        row[0] += .1
    result = reference.assess(settings, records)
    assert _check(result, "analytical_stress")["status"] == "PASS"
    _assert_invalid(result, "plastic_dissipation")
    assert result["mesh_studies"][0]["states"][4]["plastic_dissipation_density_mpa"][0] > 250 * _KNOWN_Q[4]


@pytest.mark.parametrize("field,expected_field", [
    ("stresses_mpa", "mean_stress_xx_mpa"), ("eq_plastic_strain", "mean_eq_plastic_strain"),
    ("reaction_n", "reaction_x_n"), ("displacements_mm", "right_face_axial_displacement_mm"),
])
def test_mesh_agreement_checks_all_times_and_stress_q_reaction_and_dx(field, expected_field):
    settings = _settings()
    settings["limits"].update(displacement_relative=1, stress_relative=1, plastic_strain_absolute=.001,
                              reaction_relative=1, plastic_dissipation_relative=1)
    records = _records()
    state = records[0]["states"][3]
    if field == "stresses_mpa":
        for row in state[field]:
            row[0] += .01
    elif field == "eq_plastic_strain":
        state[field] = [value + .0001 for value in state[field]]
    elif field == "reaction_n":
        state[field][0] += .5
    else:
        for node in [1, 3, 5, 7]:
            state[field][node][0] += 1e-4
    result = reference.assess(settings, records)
    _assert_invalid(result, "mesh_agreement")
    assert result["mesh_response"]["agreement_by_field"][expected_field] > 1e-7
    assert result["mesh_studies"][0]["states"][-1]["mean_stress_xx_mpa"] == pytest.approx(-60.2132701421801)


def test_absolute_plus_global_peak_relative_limits_handle_initial_zero_fields():
    settings = _settings()
    settings["limits"].update(displacement_absolute_mm=1e-5, stress_absolute_mpa=.02, reaction_absolute_n=.1)
    records = _records()
    records[0]["states"][0]["displacements_mm"][8][2] = 9e-6
    records[0]["states"][0]["stresses_mpa"][9][1] = .019
    records[0]["states"][0]["reaction_n"][2] = .09
    result = reference.assess(settings, records)
    assert all(item["status"] == "PASS" for item in result["checks"])
    displacement = _check(result, "analytical_displacement")
    assert displacement["limit"]["global_reference_scale"] == pytest.approx(.12)
    assert displacement["limit"]["combined_absolute"] == pytest.approx(1e-5 + 1e-7 * .12)
    stress = _check(result, "analytical_stress")
    assert stress["limit"]["global_reference_scale"] == pytest.approx(254.7867298578199)
    assert stress["limit"]["combined_absolute"] == pytest.approx(.02 + 1e-7 * 254.7867298578199)


def test_inputs_and_nested_outputs_are_independent_deep_copies():
    settings, records = _settings(), _records()
    old_settings, old_records = copy.deepcopy(settings), copy.deepcopy(records)
    normalized = reference.validate_settings(settings)
    analytical = reference.analytical_reference(settings)
    declaration = reference.model_declaration(settings)
    result = reference.assess(settings, records)
    assert settings == old_settings and records == old_records
    normalized["material"]["yield_stress_mpa"] = 99
    normalized["dimensions_mm"][0] = 99
    normalized["history"]["axial_strain"][0] = 99
    normalized["limits"]["plastic_strain_absolute"] = 99
    declaration["history"]["times_s"][0] = 99
    declaration["loads"][0]["values_mm"][0] = 99
    declaration["materials"][0]["plastic_modulus"]["value"] = 99
    declaration["geometry"]["dimensions_mm"][0] = 99
    declaration["mesh"]["sizes_mm"][0] = 99
    analytical["history"][6]["displacement_gradient"][0] = 99
    result["mesh_studies"][0]["states"][0]["reaction_n"][0] = 99
    result["pending_validations"].append("invented")
    assert settings == old_settings and records == old_records
    assert reference.model_declaration(settings)["outputs"]["times_s"][0] == 0
    assert "invented" not in reference.assess(settings, records)["pending_validations"]


def test_flat_declaration_has_typed_generic_history_bc_material_and_outputs():
    declaration = reference.model_declaration(_settings())
    assert reference.__version__ == "1"
    assert declaration["geometry"] == {"type": "block", "dimensions_mm": [20, 4, 2], "unit": "mm", "origin": [0, 0, 0]}
    assert declaration["materials"][0]["model"] == "j2_isotropic_linear_hardening"
    assert declaration["materials"][0]["kinematics"] == "small_strain"
    assert declaration["materials"][0]["yield_stress"] == {"value": 250, "unit": "MPa"}
    assert declaration["materials"][0]["plastic_modulus"] == {
        "value": 1000, "unit": "MPa", "meaning": "d_yield_stress_d_equivalent_plastic_strain"}
    assert declaration["mesh"] == {"sizes_mm": [2, 1], "order": 2, "element_type": "TETRA10"}
    assert [(item["selection"]["axis"], item["component"], item["value"])
            for item in declaration["boundary_conditions"]] == [("x", "x", 0), ("y", "y", 0), ("z", "z", 0)]
    assert declaration["loads"][0]["type"] == "prescribed_displacement_history"
    assert declaration["loads"][0]["selection"] == {"type": "plane", "axis": "x", "coordinate_mm": 20}
    assert declaration["loads"][0]["values_mm"][6] == .12
    assert declaration["history"] == _settings()["history"]
    assert [item["field"] for item in declaration["outputs"]["fields"]] == [
        "displacement", "stress", "eq_plastic_strain", "reactions"]
    serialized = json.dumps(declaration, allow_nan=False)
    assert "Code_Aster" not in serialized and "STAT_NON_LINE" not in serialized and "VARI_ELGA" not in serialized


@pytest.mark.parametrize("path,value", [
    (("case",), "uniaxial_block"), (("case",), True), (("case",), "__import__('os').system('unsafe')"),
    (("dimensions_mm",), [20, 4]), (("dimensions_mm",), [20, 4, 2, 1]),
    (("dimensions_mm",), [20, 0, 2]), (("dimensions_mm",), [20, -4, 2]),
    (("dimensions_mm",), [20, True, 2]), (("dimensions_mm",), [20, math.inf, 2]),
    (("dimensions_mm",), [20, math.nan, 2]), (("dimensions_mm",), (20, 4, 2)),
    (("material", "youngs_modulus_mpa"), 0), (("material", "youngs_modulus_mpa"), -1),
    (("material", "youngs_modulus_mpa"), True), (("material", "youngs_modulus_mpa"), math.inf),
    (("material", "poisson_ratio"), -1), (("material", "poisson_ratio"), .5),
    (("material", "poisson_ratio"), False), (("material", "poisson_ratio"), math.nan),
    (("material", "yield_stress_mpa"), 0), (("material", "yield_stress_mpa"), -250),
    (("material", "yield_stress_mpa"), True), (("material", "yield_stress_mpa"), math.inf),
    (("material", "yield_stress_mpa"), 3000),
    (("material", "plastic_modulus_mpa"), 0), (("material", "plastic_modulus_mpa"), -1000),
    (("material", "plastic_modulus_mpa"), True), (("material", "plastic_modulus_mpa"), math.nan),
    (("history", "times_s"), [0, 1, 2, 3, 4]), (("history", "times_s"), list(range(33))),
    (("history", "times_s"), tuple(range(10))), (("history", "times_s"), [1] + list(range(1, 10))),
    (("history", "times_s"), [0, 1, 2, 2, 4, 5, 6, 7, 8, 9]),
    (("history", "times_s"), [0, 1, 2, True, 4, 5, 6, 7, 8, 9]),
    (("history", "times_s"), [0, 1, 2, math.nan, 4, 5, 6, 7, 8, 9]),
    (("history", "axial_strain"), [0] * 9), (("history", "axial_strain"), [0] * 10),
    (("history", "axial_strain"), [.001, .002, .003, .004, .005, .006, .007, .006, .005, .004]),
    (("history", "axial_strain"), [0, .0005, -.001, .0015, .002, .003, .006, .0055, .005, .0045]),
    (("history", "axial_strain"), [0, .0005, .001, .0015, .002, .003, .011, .009, .008, .007]),
    (("history", "axial_strain"), [0, .0005, .001, .0015, .002, .003, .006, .006, .005, .0045]),
    (("history", "axial_strain"), [0, .0005, .001, .0015, .002, .003, .006, .0055, .0057, .0045]),
    (("history", "axial_strain"), [0, .0005, .001, .0015, .002, .003, .004, .005, .006, .0055]),
    (("history", "axial_strain"), [0, .0005, .001, .0015, .002, .003, .006, .0055, .005, .001]),
    (("history", "axial_strain"), [0, .0005, .001, .0015, .002, .003, .006, .0055, .005, False]),
    (("history", "axial_strain"), [0, .0005, .001, .0015, .002, .003, .006, .0055, .005, math.inf]),
    (("mesh_sizes_mm",), [2]), (("mesh_sizes_mm",), [2, 1.5, 1, .5]), (("mesh_sizes_mm",), [2, 2]),
    (("mesh_sizes_mm",), [1, 2]), (("mesh_sizes_mm",), [3, 1]), (("mesh_sizes_mm",), [2, 0]),
    (("mesh_sizes_mm",), [2, True]), (("mesh_sizes_mm",), [2, math.nan]),
    (("limits", "stress_relative"), 0), (("limits", "plastic_strain_absolute"), -1),
    (("limits", "reaction_absolute_n"), True), (("limits", "plastic_dissipation_relative"), math.inf),
    (("limits", "plastic_dissipation_absolute_mpa"), "1e-8"),
])
def test_bad_unsupported_or_unsafe_settings_fail_preflight(path, value):
    settings = _settings()
    parent = settings
    for key in path[:-1]:
        parent = parent[key]
    parent[path[-1]] = value
    with pytest.raises(ValueError):
        reference.validate_settings(settings)


@pytest.mark.parametrize("section", [None, "material", "history", "limits"])
@pytest.mark.parametrize("change", ["extra", "missing"])
def test_missing_or_extra_public_keys_are_rejected(section, change):
    settings = _settings()
    value = settings if section is None else settings[section]
    if change == "extra":
        value["native_commands"] = "unsafe"
    else:
        value.pop(next(iter(value)))
    with pytest.raises(ValueError):
        reference.validate_settings(settings)


@pytest.mark.parametrize("value", [None, [], "not a request", True])
def test_settings_must_be_a_dictionary(value):
    with pytest.raises(ValueError):
        reference.validate_settings(value)


def test_unrepresentable_reference_and_tolerance_fail_before_execution():
    settings = _settings()
    settings["material"].update(youngs_modulus_mpa=1e308, plastic_modulus_mpa=1e308)
    with pytest.raises(ValueError, match="Analytical E\\+H"):
        reference.validate_settings(settings)
    settings = _settings()
    settings["limits"]["stress_relative"] = 1e308
    with pytest.raises(ValueError, match="tolerance"):
        reference.validate_settings(settings)


@pytest.mark.parametrize("mutation", [
    lambda r: r.pop(), lambda r: r[0].pop("states"), lambda r: r[0].update(mesh_size_mm=1.5),
    lambda r: r[0].update(node_ids=[1] * 9), lambda r: r[0]["node_ids"].__setitem__(0, True),
    lambda r: r[0]["node_ids"].__setitem__(0, 0), lambda r: r[0]["coordinates_mm"].pop(),
    lambda r: r[0]["coordinates_mm"][0].pop(), lambda r: r[0]["coordinates_mm"][0].__setitem__(0, -1),
    lambda r: r[0]["coordinates_mm"][0].__setitem__(0, math.nan),
    lambda r: r[0]["coordinates_mm"].__setitem__(0, [True, 0, 0]),
    lambda r: r[0].update(element_count=0), lambda r: r[0].update(element_count=True),
    lambda r: r[0].update(element_count=2.0), lambda r: r[0]["states"].pop(),
    lambda r: r[0]["states"][0].pop("reaction_n"), lambda r: r[0]["states"][0].update(time_s=1),
    lambda r: r[0]["states"][0].update(time_s=False),
    lambda r: r[0]["states"][3]["displacements_mm"].pop(),
    lambda r: r[0]["states"][3]["displacements_mm"][8].pop(),
    lambda r: r[0]["states"][3]["displacements_mm"][8].__setitem__(2, math.inf),
    lambda r: r[0]["states"][3]["displacements_mm"][8].__setitem__(2, True),
    lambda r: r[0]["states"][3]["stresses_mpa"].pop(),
    lambda r: r[0]["states"][3]["stresses_mpa"].append([0] * 6),
    lambda r: r[0]["states"][3]["stresses_mpa"][9].pop(),
    lambda r: r[0]["states"][3]["stresses_mpa"][9].__setitem__(5, math.nan),
    lambda r: r[0]["states"][3]["eq_plastic_strain"].pop(),
    lambda r: r[0]["states"][3].update(eq_plastic_strain=[[.001]] * 10),
    lambda r: r[0]["states"][3]["eq_plastic_strain"].__setitem__(9, True),
    lambda r: r[0]["states"][3]["eq_plastic_strain"].__setitem__(9, math.inf),
    lambda r: r[0]["states"][3].update(reaction_n=[0, 0]),
    lambda r: r[0]["states"][3]["reaction_n"].__setitem__(2, math.inf),
])
def test_malformed_missing_or_nonfinite_native_observations_raise(mutation):
    records = _records()
    mutation(records)
    with pytest.raises(ValueError):
        reference.assess(_settings(), records)


def test_mesh_requires_full_bounding_box_and_at_least_three_right_face_nodes():
    records = _records()
    for row in records[0]["coordinates_mm"]:
        if row[1] == 4:
            row[1] = 3
    with pytest.raises(ValueError, match="boundary planes"):
        reference.assess(_settings(), records)
    records = _records()
    for node in [1, 3]:
        records[0]["coordinates_mm"][node][0] = 19
    with pytest.raises(ValueError, match="three right face"):
        reference.assess(_settings(), records)


def test_extra_adapter_metadata_is_allowed_without_changing_inputs_or_domain_metrics():
    records = _records()
    records[0]["native_table_identity"] = "adapter-owned"
    records[0]["states"][0]["native_output_order"] = 0
    before = copy.deepcopy(records)
    result = reference.assess(_settings(), records)
    assert all(item["status"] == "PASS" for item in result["checks"])
    assert records == before
