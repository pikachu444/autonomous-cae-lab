"""Independent circular geometry and cold tampered-field tests.

All observations here are synthetic arithmetic fixtures, never native solver
evidence. A small prescribed O(h^2) position perturbation gives measurable
rates; exact circular fixtures must retain UNKNOWN rates instead of fake PASS.
"""

import copy
import json
import math

import pytest

from plugins.geometric_nonlinearity import reference


_FROZEN_LIMITS = {
    "displacement_relative": .001, "displacement_absolute_mm": 1e-8,
    "finest_displacement_relative": .0001,
    "rotation_relative": 1e-5, "rotation_absolute_rad": 1e-8,
    "force_absolute_n": 1e-8, "moment_relative": 1e-5, "moment_absolute_n_mm": 1e-6,
    "curvature_relative": 1e-5, "curvature_absolute_per_mm": 1e-10,
    "derived_energy_relative": 1e-5, "derived_energy_absolute_n_mm": 1e-8,
    "min_mesh_rate": 1.8,
}


def _settings():
    # Deliberately not obtained from default_settings: catch a changed default
    # section, history, mesh or acceptance limit as well as formula defects.
    return {"case": "pure_end_moment_beam",
            "beam": {"length_mm": 1000, "width_z_mm": 1, "height_y_mm": 2},
            "material": {"youngs_modulus_mpa": 210000, "poisson_ratio": .3},
            "history": {"times_s": [0, 1, 2, 3, 4], "moments_n_mm": [0, 7, 35, 70, 140]},
            "mesh": {"element_counts": [8, 16, 32]}, "limits": dict(_FROZEN_LIMITS)}


def _records(settings=None, *, amplitude=.02, rate=2, positions=None):
    """Independent scalar trigonometry, sparse IDs and explicitly fake fields."""
    settings = _settings() if settings is None else settings
    length = settings["beam"]["length_mm"]
    width, height = settings["beam"]["width_z_mm"], settings["beam"]["height_y_mm"]
    modulus = settings["material"]["youngs_modulus_mpa"]
    bending_stiffness = modulus * width * height ** 3 / 12
    peak = max(settings["history"]["moments_n_mm"])
    observations = []
    for count in settings["mesh"]["element_counts"]:
        coordinates = ([[length * j / count, 0, 0] for j in range(count + 1)]
                       if positions is None else [[s, 0, 0] for s in positions[count]])
        node_ids = [101 + 7 * index for index in range(count + 1)]
        states = []
        for time, moment in zip(settings["history"]["times_s"], settings["history"]["moments_n_mm"]):
            k = moment / bending_stiffness
            displacements, rotations = [], []
            for s, _, _ in coordinates:
                phi = k * s
                if moment == 0:
                    dx = dy = 0
                else:
                    dx, dy = math.sin(phi) / k - s, (1 - math.cos(phi)) / k
                dy += amplitude * (8 / count) ** rate * (s / length) * (moment / peak)
                displacements.append([dx, dy, 0])
                rotations.append([0, 0, phi])
            states.append({"time_s": time, "displacements_mm": displacements, "rotations_rad": rotations,
                "nodal_forces_n": [[0, 0, 0] for _ in coordinates],
                "nodal_moments_n_mm": [[0, 0, -moment]] + [[0, 0, 0] for _ in range(count)],
                "section_wrenches": [[0, 0, 0, 0, 0, moment] for _ in range(count)],
                "curvatures_per_mm": [[0, 0, k] for _ in range(count)]})
        observations.append({"element_count": count, "node_ids": node_ids, "coordinates_mm": coordinates,
                             "segments": [[a, b] for a, b in zip(node_ids, node_ids[1:])], "states": states,
                             "test_fixture_kind": "synthetic_not_native"})
    return observations


def _check(result, code):
    return next(check for check in result["checks"] if check["code"] == code)


def _assert_invalid(result, code, status="FAIL"):
    assert _check(result, code)["status"] == status
    assert all(not metric["valid"] and code in metric["reason"] for metric in result["metrics"].values())
    assert all(metric["value"] is None or math.isfinite(metric["value"]) for metric in result["metrics"].values())
    json.dumps(result, allow_nan=False)


def test_defaults_are_exact_and_deep_independent():
    first = reference.default_settings()
    assert first == _settings()
    first["history"]["moments_n_mm"][2] = 0
    first["mesh"]["element_counts"].append(64)
    first["limits"]["min_mesh_rate"] = 0
    assert reference.default_settings() == _settings()
    original = _settings()
    normalized = reference.validate_settings(original)
    assert normalized == original
    normalized["beam"]["height_y_mm"] = 99
    normalized["history"]["times_s"][2] = 99
    assert original == _settings()


def test_default_reference_uses_declared_height_axis_and_known_circle():
    exact = reference.analytical_reference(_settings())
    assert exact["section"]["area_mm2"] == 2
    assert exact["section"]["iy_mm4"] == pytest.approx(1 / 6)
    assert exact["section"]["iz_mm4"] == pytest.approx(2 / 3)
    assert exact["section"]["bending_rigidity_n_mm2"] == 140000
    assert [state["end_rotations_rad"][2] for state in exact["history"]] == pytest.approx([0, .05, .25, .5, 1])
    final = exact["history"][-1]
    assert final["end_coordinates_mm"] == pytest.approx([841.4709848078965, 459.6976941318602, 0], abs=2e-12)
    assert final["end_displacements_mm"] == pytest.approx([-158.5290151921035, 459.6976941318602, 0], abs=2e-12)
    assert final["root_reaction"] == [0, 0, 0, 0, 0, -140]
    assert final["section_wrench"] == [0, 0, 0, 0, 0, 140]
    assert final["curvature_per_mm"] == [0, 0, .001]
    assert final["derived_section_fiber_stress_mpa"] == 210
    assert final["bending_energy_n_mm"] == 70
    assert exact["frame"]["local_y"] == [0, 1, 0]
    assert exact["frame"]["curvature_basis"] == "updated_global_xyz"
    assert exact["time_meaning"] == "quasi_static_load_parameter"
    assert exact["native_global_energy"] == "UNKNOWN"


def test_zero_archive_and_tiny_angle_retain_continuous_signed_limits():
    settings = _settings()
    settings["history"] = {"times_s": [0, 1, 2], "moments_n_mm": [0, 1.4e-10, 1.4e-8]}
    exact = reference.analytical_reference(settings)
    zero = exact["history"][0]
    assert zero["end_coordinates_mm"] == [1000, 0, 0]
    assert zero["end_displacements_mm"] == [0, 0, 0]
    assert zero["root_reaction"] == [0] * 6
    assert zero["section_wrench"] == [0] * 6
    assert zero["bending_energy_n_mm"] == 0
    small = exact["history"][-1]
    # Direct small-angle series gives DX=-L*theta^2/6 and DY=L*theta/2.
    assert small["end_displacements_mm"][0] < 0
    assert small["end_displacements_mm"][0] == pytest.approx(-1.6666666666666667e-18, rel=1e-15, abs=0)
    assert small["end_displacements_mm"][1] == pytest.approx(5e-8, rel=1e-15, abs=0)
    assert small["end_rotations_rad"][2] == pytest.approx(1e-10, rel=1e-15, abs=0)
    assert small["bending_energy_n_mm"] == pytest.approx(7e-19, rel=1e-15, abs=0)


@pytest.mark.parametrize("angle", [.009999999, .01, .010000001, .001, .5, 1])
def test_stable_branch_matches_independent_half_angle_geometry(angle):
    settings = _settings()
    settings["history"] = {"times_s": [0, 1, 2], "moments_n_mm": [0, 70 * angle, 140 * angle]}
    end = reference.analytical_reference(settings)["history"][-1]
    assert end["end_coordinates_mm"][0] == pytest.approx(1000 * math.sin(angle) / angle, abs=3e-12)
    assert end["end_coordinates_mm"][1] == pytest.approx(2000 * math.sin(angle / 2) ** 2 / angle, abs=3e-12)


def test_changed_length_section_modulus_load_and_time_are_not_default_constants():
    settings = _settings()
    settings["beam"] = {"length_mm": 500, "width_z_mm": 2, "height_y_mm": 1}
    settings["material"] = {"youngs_modulus_mpa": 100000, "poisson_ratio": -.2}
    settings["history"] = {"times_s": [0, .2, .9], "moments_n_mm": [0, 10, 20]}
    settings["mesh"]["element_counts"] = [10, 20]
    exact = reference.analytical_reference(settings)
    last = exact["history"][-1]
    assert exact["section"]["iz_mm4"] == pytest.approx(1 / 6)
    assert exact["section"]["iy_mm4"] == pytest.approx(2 / 3)
    assert last["end_rotations_rad"][2] == pytest.approx(.6)
    assert last["end_coordinates_mm"] == pytest.approx([470.5353944958628, 145.55365424193473, 0], abs=1e-10)
    assert last["bending_energy_n_mm"] == pytest.approx(6)
    assert last["derived_section_fiber_stress_mpa"] == pytest.approx(60)
    result = reference.assess(settings, _records(settings))
    assert all(item["status"] == "PASS" for item in result["checks"])
    assert result["metrics"]["root_moment_z"]["value"] == -20
    assert result["metrics"]["derived_bending_energy"]["value"] == pytest.approx(6)


def test_flat_model_declaration_matches_common_metadata_without_native_syntax():
    request = _settings()
    declaration = reference.model_declaration(request)
    assert {"geometry", "materials", "mesh", "loads", "boundary_conditions", "outputs"} <= set(declaration)
    assert "model" not in declaration
    assert declaration["geometry"]["cross_section"]["height_y_mm"] == 2
    assert declaration["materials"][0]["youngs_modulus"] == {"value": 210000, "unit": "MPa"}
    assert declaration["mesh"]["element_counts"] == [8, 16, 32]
    assert declaration["loads"][0]["component"] == "global_z"
    assert declaration["loads"][0]["values"] == [0, 7, 35, 70, 140]
    encoded = json.dumps(declaration, allow_nan=False)
    for native in ("POU_D_T_GD", "ELAS_POUTRE_GR", "GROT_GDEP", "DEPL", "SIEF_ELGA", ".comm", ".mail", "torsion"):
        assert native not in encoded
    declaration["mesh"]["element_counts"][0] = 99
    declaration["history"]["times_s"][0] = 99
    assert request == _settings()


def test_synthetic_second_order_fields_measure_every_pair_and_keep_blocking_unknowns():
    original = _records()
    retained = copy.deepcopy(original)
    result = reference.assess(_settings(), original)
    assert original == retained
    assert all(item["status"] == "PASS" for item in result["checks"])
    assert all(item["valid"] for item in result["metrics"].values())
    pairs = result["mesh_response"]["pairs"]
    assert [(p["coarse_element_count"], p["fine_element_count"]) for p in pairs] == [(8, 16), (8, 32), (16, 32)]
    assert [p["rate"] for p in pairs] == pytest.approx([2, 2, 2], abs=3e-9)
    assert result["metrics"]["minimum_mesh_rate"]["value"] == pytest.approx(2, abs=3e-9)
    assert result["metrics"]["max_position_error"]["value"] == pytest.approx(.02, abs=1e-11)
    assert result["metrics"]["finest_position_error"]["value"] == pytest.approx(.00125, abs=1e-11)
    assert result["metrics"]["tip_x"]["value"] == pytest.approx(841.4709848078965)
    assert result["metrics"]["tip_y"]["value"] == pytest.approx(459.6989441318602)
    assert result["metrics"]["root_moment_z"]["value"] == -140
    assert result["metrics"]["derived_section_fiber_stress"]["value"] == 210
    assert result["metrics"]["derived_bending_energy"]["value"] == 70
    assert set(result["pending_validations"]) == {"native_global_energy", "static_strength", "material_qualification",
        "model_qualification", "physical_validation", "fatigue_durability"}
    assert result["derived_energy"]["native_energy_field"] is False
    assert result["derived_energy"]["physical_energy_balance"] is False
    assert result["derived_stress"]["native_cauchy_stress"] is False
    assert "release" not in result and "solver_status" not in result
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize("amplitude", [0, 1e-10])
def test_exact_or_roundoff_position_error_is_unknown_not_fabricated_mesh_pass(amplitude):
    result = reference.assess(_settings(), _records(amplitude=amplitude))
    assert all(pair["status"] == "UNKNOWN" and pair["rate"] is None for pair in result["mesh_response"]["pairs"])
    _assert_invalid(result, "mesh_rate_8_to_16", "UNKNOWN")
    assert result["metrics"]["minimum_mesh_rate"]["value"] is None
    assert result["mesh_response"]["roundoff_floor_mm"] == 1e-8


def test_only_one_roundoff_mesh_still_prevents_minimum_rate_metric():
    records = _records()
    records[-1] = _records(amplitude=0)[-1]
    result = reference.assess(_settings(), records)
    assert _check(result, "mesh_rate_8_to_16")["status"] == "PASS"
    assert _check(result, "mesh_rate_8_to_32")["status"] == "UNKNOWN"
    assert result["metrics"]["minimum_mesh_rate"]["value"] is None


@pytest.mark.parametrize("rate", [0, 1, -1])
def test_slow_or_divergent_mesh_sequence_preserves_measured_failure(rate):
    result = reference.assess(_settings(), _records(rate=rate))
    _assert_invalid(result, "mesh_rate_8_to_16")
    assert result["metrics"]["minimum_mesh_rate"]["value"] == pytest.approx(rate, abs=1e-9)


def test_finest_bound_is_separately_stricter_than_general_displacement():
    # .16 mm finest error passes the general 1 mm bound but fails the separate
    # .1 mm bound, irrespective of the sequence's separate rate rejection.
    records = _records(amplitude=.64, rate=1)
    result = reference.assess(_settings(), records)
    assert _check(result, "analytical_displacement")["status"] == "PASS"
    _assert_invalid(result, "finest_displacement")
    assert result["metrics"]["finest_position_error"]["value"] == pytest.approx(.16)


@pytest.mark.parametrize("field,state,row,column,increment,code", [
    ("displacements_mm", 0, 3, 2, 2, "analytical_displacement"),
    ("displacements_mm", 2, 4, 0, -2, "analytical_displacement"),
    ("rotations_rad", 3, 2, 1, .02, "analytical_rotation"),
    ("rotations_rad", 4, 6, 2, -.2, "analytical_rotation"),
    ("nodal_forces_n", 0, 8, 2, .001, "all_nodal_forces"),
    ("nodal_forces_n", 2, 4, 0, -.001, "all_nodal_forces"),
    ("nodal_moments_n_mm", 2, 0, 2, 70, "signed_root_moment"),
    ("nodal_moments_n_mm", 3, 4, 0, .01, "all_nodal_moments"),
    ("section_wrenches", 0, 7, 1, -.001, "section_forces"),
    ("section_wrenches", 3, 2, 3, .01, "signed_section_moments"),
    ("section_wrenches", 4, 7, 5, -280, "signed_section_moments"),
    ("curvatures_per_mm", 0, 4, 0, .001, "updated_global_curvature"),
    ("curvatures_per_mm", 4, 7, 2, -.002, "updated_global_curvature"),
])
def test_every_field_component_point_interior_and_zero_history_is_checked(field, state, row, column, increment, code):
    records = _records()
    records[0]["states"][state][field][row][column] += increment
    result = reference.assess(_settings(), records)
    _assert_invalid(result, code)
    if field == "section_wrenches" and column == 5:
        assert result["mesh_studies"][0]["states"][state]["derived_section_fiber_stresses_mpa"][row] == -210


def test_opposite_local_moment_and_global_curvature_cannot_hide_inside_positive_energy():
    records = _records()
    state = records[0]["states"][-1]
    for wrench, curvature in zip(state["section_wrenches"], state["curvatures_per_mm"]):
        wrench[5] *= -1
        curvature[2] *= -1
    result = reference.assess(_settings(), records)
    assert _check(result, "derived_bending_energy")["status"] == "PASS"
    _assert_invalid(result, "signed_section_moments")
    assert _check(result, "updated_global_curvature")["status"] == "FAIL"
    assert result["mesh_studies"][0]["states"][-1]["derived_bending_energy_n_mm"] == 70


def test_nodal_forces_moments_and_full_union_balance_have_separate_gates():
    records = _records()
    state = records[0]["states"][-1]
    state["nodal_forces_n"][0][1] = 2e-8
    state["nodal_forces_n"][-1][1] = -2e-8
    result = reference.assess(_settings(), records)
    assert _check(result, "full_support_force_balance")["status"] == "PASS"
    _assert_invalid(result, "all_nodal_forces")
    # Opposite forces have zero net force but their lever moment must survive.
    assert result["mesh_studies"][0]["states"][-1]["moment_balance_error_n_mm"] == pytest.approx(2e-5)
    records = _records()
    for row in records[0]["states"][-1]["nodal_moments_n_mm"]:
        row[0] += .0005
    result = reference.assess(_settings(), records)
    assert _check(result, "all_nodal_moments")["status"] == "PASS"
    _assert_invalid(result, "full_support_moment_balance")
    assert result["mesh_studies"][0]["states"][-1]["full_support_moment_n_mm"][0] == pytest.approx(.0045)


def test_many_small_support_forces_fail_aggregate_without_observed_rescaling():
    records = _records()
    for row in records[0]["states"][-1]["nodal_forces_n"]:
        row[0] = 5e-9
    result = reference.assess(_settings(), records)
    assert _check(result, "all_nodal_forces")["status"] == "PASS"
    _assert_invalid(result, "full_support_force_balance")
    assert result["mesh_studies"][0]["states"][-1]["force_balance_error_n"] == pytest.approx(4.5e-8)


def test_nonuniform_native_segment_lengths_drive_rates_and_energy_integration():
    settings = _settings()
    positions = {n: [1000 * (j / n) ** 2 for j in range(n + 1)] for n in [8, 16, 32]}
    result = reference.assess(settings, _records(positions=positions))
    pairs = result["mesh_response"]["pairs"]
    assert pairs[0]["coarse_max_segment_length_mm"] == 234.375
    assert pairs[0]["fine_max_segment_length_mm"] == 121.09375
    assert pairs[0]["rate"] == pytest.approx(math.log(4) / math.log(234.375 / 121.09375), abs=1e-9)
    assert result["metrics"]["derived_bending_energy"]["value"] == pytest.approx(70, abs=2e-13)
    assert all(item["status"] == "PASS" for item in result["checks"])


def test_increasing_counts_without_finer_maximum_segment_is_not_a_valid_rate():
    positions = {8: [125 * j for j in range(9)],
                 16: [10 * j for j in range(16)] + [1000],
                 32: [1000 * j / 32 for j in range(33)]}
    result = reference.assess(_settings(), _records(positions=positions))
    _assert_invalid(result, "mesh_rate_8_to_16")
    assert result["mesh_response"]["pairs"][0]["rate"] is None


def test_consistent_node_catalogue_permutation_is_allowed_but_duplicate_fields_are_not():
    records = _records()
    record = records[0]
    permutation = list(reversed(range(9)))
    record["node_ids"] = [record["node_ids"][index] for index in permutation]
    record["coordinates_mm"] = [record["coordinates_mm"][index] for index in permutation]
    for state in record["states"]:
        for field in ("displacements_mm", "rotations_rad", "nodal_forces_n", "nodal_moments_n_mm"):
            state[field] = [state[field][index] for index in permutation]
    result = reference.assess(_settings(), records)
    assert all(item["status"] == "PASS" for item in result["checks"])
    assert result["mesh_studies"][0]["states"][-1]["root_reaction"][-1] == -140
    record["states"][-1]["rotations_rad"][3] = list(record["states"][-1]["rotations_rad"][2])
    _assert_invalid(reference.assess(_settings(), records), "analytical_rotation")


@pytest.mark.parametrize("target,key,value", [
    ("root", "case", "other"), ("root", "extra", 1),
    ("beam", "length_mm", 0), ("beam", "width_z_mm", -1), ("beam", "height_y_mm", 51),
    ("beam", "length_mm", True), ("beam", "length_mm", "1000"),
    ("beam", "height_y_mm", float("nan")), ("beam", "width_z_mm", float("inf")),
    ("material", "youngs_modulus_mpa", 0), ("material", "poisson_ratio", .5),
    ("material", "poisson_ratio", -1), ("material", "poisson_ratio", False),
    ("material", "yield_stress", 250),
    ("mesh", "element_counts", [8]), ("mesh", "element_counts", [8, 16, 32, 64]),
    ("mesh", "element_counts", [8, 8]), ("mesh", "element_counts", [16, 8]),
    ("mesh", "element_counts", [8., 16]), ("mesh", "element_counts", [True, 16]),
    ("mesh", "element_counts", [7, 16]), ("mesh", "element_counts", [8, 513]),
    ("history", "times_s", [0, 1]), ("history", "times_s", [0, 1, 1, 3, 4]),
    ("history", "times_s", [1, 2, 3, 4, 5]), ("history", "moments_n_mm", [0, 7, 7, 70, 140]),
    ("history", "moments_n_mm", [0, -7, 35, 70, 140]),
    ("history", "moments_n_mm", [0, 7, 35, 70, 141]),
    ("history", "moments_n_mm", [0, 7, 35, 70, float("nan")]),
    ("history", "moments_n_mm", [0, 7, 35, 70, True]),
    ("limits", "displacement_relative", .002), ("limits", "min_mesh_rate", 1.7),
    ("limits", "rotation_relative", True), ("limits", "extra", 0),
])
def test_settings_reject_unsupported_nonfinite_wrong_type_history_mesh_and_changed_limits(target, key, value):
    settings = _settings()
    (settings if target == "root" else settings[target])[key] = value
    with pytest.raises(ValueError):
        reference.validate_settings(settings)


@pytest.mark.parametrize("target,key", [("beam", "width_z_mm"), ("material", "poisson_ratio"),
                                      ("history", "times_s"), ("mesh", "element_counts"),
                                      ("limits", "force_absolute_n")])
def test_missing_nested_settings_keys_never_fall_back_to_defaults(target, key):
    settings = _settings()
    del settings[target][key]
    with pytest.raises(ValueError):
        reference.validate_settings(settings)


def test_shape_and_reference_arithmetic_overflow_underflow_are_rejected():
    for size in [1e-110, 1e105]:
        settings = _settings()
        settings["beam"] = {"length_mm": size * 1000, "width_z_mm": size, "height_y_mm": size * 2}
        with pytest.raises(ValueError):
            reference.validate_settings(settings)
    settings = _settings()
    settings["material"]["youngs_modulus_mpa"] = 10 ** 1000
    with pytest.raises(ValueError):
        reference.validate_settings(settings)
    settings = _settings()
    settings["beam"]["height_y_mm"] = 20
    settings["history"]["moments_n_mm"] = [0, 7000, 35000, 70000, 140000]
    # theta=1 is admissible as rotation, but 1*20/(2*1000)=.01 violates strain.
    with pytest.raises(ValueError, match="fiber strain"):
        reference.validate_settings(settings)


@pytest.mark.parametrize("mutation", [
    "mesh_missing", "mesh_duplicate", "mesh_order", "record_key", "node_missing", "node_duplicate", "node_bool",
    "node_zero", "coordinate_missing", "coordinate_nonfinite", "coordinate_axis", "coordinate_root", "coordinate_tip",
    "coordinate_duplicate", "segment_missing", "segment_duplicate", "segment_reverse", "segment_order", "segment_foreign",
    "state_missing", "state_duplicate", "state_order", "state_key", "time_nonfinite", "force_extra_row",
    "moment_missing_component", "section_missing", "curvature_extra", "state_nonfinite",
])
def test_incomplete_ambiguous_topology_and_histories_raise_before_numerical_verdict(mutation):
    records = _records()
    record = records[0]
    state = record["states"][2]
    if mutation == "mesh_missing": records.pop()
    elif mutation == "mesh_duplicate": records[1] = copy.deepcopy(record)
    elif mutation == "mesh_order": records.reverse()
    elif mutation == "record_key": del record["segments"]
    elif mutation == "node_missing": record["node_ids"].pop()
    elif mutation == "node_duplicate": record["node_ids"][1] = record["node_ids"][0]
    elif mutation == "node_bool": record["node_ids"][0] = True
    elif mutation == "node_zero": record["node_ids"][0] = 0
    elif mutation == "coordinate_missing": record["coordinates_mm"].pop()
    elif mutation == "coordinate_nonfinite": record["coordinates_mm"][2][0] = float("inf")
    elif mutation == "coordinate_axis": record["coordinates_mm"][2][1] = .001
    elif mutation == "coordinate_root": record["coordinates_mm"][0][0] = .001
    elif mutation == "coordinate_tip": record["coordinates_mm"][-1][0] = 999
    elif mutation == "coordinate_duplicate": record["coordinates_mm"][2] = list(record["coordinates_mm"][1])
    elif mutation == "segment_missing": record["segments"].pop()
    elif mutation == "segment_duplicate": record["segments"][1] = list(record["segments"][0])
    elif mutation == "segment_reverse": record["segments"][1].reverse()
    elif mutation == "segment_order": record["segments"].reverse()
    elif mutation == "segment_foreign": record["segments"][0][0] = 99999
    elif mutation == "state_missing": record["states"].pop(0)
    elif mutation == "state_duplicate": record["states"][2] = copy.deepcopy(record["states"][1])
    elif mutation == "state_order": record["states"].reverse()
    elif mutation == "state_key": del state["rotations_rad"]
    elif mutation == "time_nonfinite": state["time_s"] = float("nan")
    elif mutation == "force_extra_row": state["nodal_forces_n"].append([0, 0, 0])
    elif mutation == "moment_missing_component": state["nodal_moments_n_mm"][2].pop()
    elif mutation == "section_missing": state["section_wrenches"].pop()
    elif mutation == "curvature_extra": state["curvatures_per_mm"].append([0, 0, 0])
    elif mutation == "state_nonfinite": state["curvatures_per_mm"][4][2] = float("nan")
    else: raise AssertionError(mutation)
    with pytest.raises(ValueError):
        reference.assess(_settings(), records)


def test_adapter_metadata_cannot_bypass_missing_or_wrong_scientific_fields():
    records = _records()
    records[0].update(solver_status="COMPLETED", validated=True, converged=True,
                      support_node_ids=records[0]["node_ids"], reference_pass=True)
    records[0]["states"][-1]["section_wrenches"][-1][5] = 0
    _assert_invalid(reference.assess(_settings(), records), "signed_section_moments")
    del records[0]["states"][-1]["curvatures_per_mm"]
    with pytest.raises(ValueError):
        reference.assess(_settings(), records)


def test_observed_large_rotation_or_moment_does_not_inflate_its_tolerance():
    records = _records()
    records[0]["states"][-1]["rotations_rad"][-1][2] = 1000
    result = reference.assess(_settings(), records)
    _assert_invalid(result, "analytical_rotation")
    assert _check(result, "analytical_rotation")["limit"]["combined_absolute"] == pytest.approx(1.001e-5)
    records = _records()
    records[0]["states"][-1]["section_wrenches"][-1][5] = 1e8
    result = reference.assess(_settings(), records)
    _assert_invalid(result, "signed_section_moments")
    assert _check(result, "signed_section_moments")["limit"]["combined_absolute"] == pytest.approx(.001401)


def test_derived_energy_has_its_own_bound_even_when_individual_wrench_and_curvature_pass():
    records = _records()
    state = records[0]["states"][-1]
    for wrench, curvature in zip(state["section_wrenches"], state["curvatures_per_mm"]):
        wrench[5] = 140 * (1 + 7.5e-6)
        curvature[2] = .001 * (1 + 7.5e-6)
    result = reference.assess(_settings(), records)
    assert _check(result, "signed_section_moments")["status"] == "PASS"
    assert _check(result, "updated_global_curvature")["status"] == "PASS"
    _assert_invalid(result, "derived_bending_energy")
    derived = result["mesh_studies"][0]["states"][-1]["derived_bending_energy_n_mm"]
    assert derived == pytest.approx(70 * (1 + 7.5e-6) ** 2, abs=2e-13)


def test_every_interior_node_controls_maximum_position_rate_at_every_time():
    records = _records()
    # A large earlier interior error, although every final tip remains correct,
    # must be retained in the maximum used by the 16->32 comparison.
    records[1]["states"][2]["displacements_mm"][7][2] = .003
    result = reference.assess(_settings(), records)
    middle = result["mesh_studies"][1]
    assert middle["states"][2]["max_position_error_mm"] >= .003
    assert middle["max_position_error_mm"] == pytest.approx(.005)
    records[1]["states"][2]["displacements_mm"][7][2] = .04
    changed = reference.assess(_settings(), records)
    assert changed["mesh_studies"][1]["max_position_error_mm"] > .04
    _assert_invalid(changed, "mesh_rate_8_to_16")


@pytest.mark.parametrize("field", ["displacements_mm", "rotations_rad", "nodal_forces_n",
                                  "nodal_moments_n_mm", "section_wrenches", "curvatures_per_mm"])
def test_observation_boolean_or_tuple_is_not_a_finite_native_field(field):
    records = _records()
    records[0]["states"][2][field][0][0] = True
    with pytest.raises(ValueError):
        reference.assess(_settings(), records)
    records = _records()
    records[0]["states"][2][field][0] = tuple(records[0]["states"][2][field][0])
    with pytest.raises(ValueError):
        reference.assess(_settings(), records)


def test_history_and_mesh_admission_bounds_are_inclusive_but_not_unlimited():
    settings = _settings()
    settings["mesh"]["element_counts"] = [8, 512]
    settings["history"] = {"times_s": list(range(32)), "moments_n_mm": [140 * j / 31 for j in range(32)]}
    normalized = reference.validate_settings(settings)
    assert len(normalized["history"]["times_s"]) == 32
    assert normalized["mesh"]["element_counts"] == [8, 512]
    settings["history"]["times_s"].append(32)
    settings["history"]["moments_n_mm"].append(140.1)
    with pytest.raises(ValueError):
        reference.validate_settings(settings)


def test_changes_to_poisson_ratio_do_not_change_a_pure_bending_circle():
    request = _settings()
    initial = reference.analytical_reference(request)
    request["material"]["poisson_ratio"] = -.9
    changed = reference.analytical_reference(request)
    assert changed == initial
    assert reference.model_declaration(request)["materials"][0]["poisson_ratio"]["value"] == -.9
