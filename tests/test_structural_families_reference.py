"""Independent synthetic observations exercise Domain semantics, not a solver.

Only the cylinder fixture is an analytical field. Beam/roof observations encode
the published response and independent load integrals; they are deliberately
not presented as complete physical solutions or native acceptance evidence.
"""

import copy
import itertools
import json
import math

import pytest

from plugins.structural_families import (
    assess,
    case_definition,
    model_declaration,
    specification,
    validate_settings,
)
from plugins.structural_families import reference as domain


BEAM = "ansys_vmd1_regular"
CYLINDER = "lame_cylinder_plane_strain"
ROOF = "scordelis_lo_solid"
CASES = (BEAM, CYLINDER, ROOF)
CELLS = [[1, 1, 1], [2, 2, 1]]
LBF = 4.4482216152605
FT = 304.8


def request(case, load=None, factor=1.0):
    return {
        "case": case,
        "load_case": load or {BEAM: "Fx", CYLINDER: "pressure", ROOF: "gravity"}[case],
        "load_factor": factor,
        "mesh_cells": copy.deepcopy(CELLS),
    }


def physical(case, logical):
    """A test-only exact-radius coordinate catalogue; no adapter dependency."""
    a, b, c = logical
    if case == BEAM:
        return [152.4 * a, 5.08 * b, 2.54 * c]
    if case == CYLINDER:
        radius, theta = 100.0 + 100.0 * a, math.pi / 2 * b
        return [radius * math.cos(theta), radius * math.sin(theta), 20.0 * c]
    radius, theta = 7581.9 + 76.2 * c, math.radians(40.0) * b
    return [7620.0 * a, radius * math.sin(theta), radius * math.cos(theta)]


def cylinder_fields(xyz, factor=1.0, young=220000.0):
    """Cartesian Lamé solution, derived directly with nu=0, Ri100/Ro200."""
    x, y, _ = xyz
    r2 = x*x + y*y
    a, b = 100.0 / 3 * factor, 4_000_000.0 / 3 * factor
    u = [(a + b/r2) * x / young, (a + b/r2) * y / young, 0.0]
    stress = [a + b*(y*y-x*x)/(r2*r2), a + b*(x*x-y*y)/(r2*r2),
              0.0, -2*b*x*y/(r2*r2), 0.0, 0.0]
    return u, stress


def integrals(case, load, factor):
    if case == BEAM:
        f = LBF * factor
        return {
            "Fx": ([f, 0.0, 0.0], [0.0, 1.27*f, -2.54*f]),
            "Fy": ([0.0, f, 0.0], [-1.27*f, 0.0, 152.4*f]),
            "Fz": ([0.0, 0.0, f], [2.54*f, -152.4*f, 0.0]),
        }[load]
    if case == CYLINDER:
        f = 200000.0 * factor
        return [f, f, 0.0], [-10.0*f, 10.0*f, 0.0]
    # Independent closed total weight from 25ft axial length, R25ft, t0.25ft,
    # 40deg sector and 360lbf/ft^3. Its total weight is 12500*pi lbf.
    fz = -12500.0 * math.pi * LBF * factor
    ri, ro, angle = 24.875, 25.125, math.radians(40.0)
    radial_mean = 2*(ro**3-ri**3)/(3*(ro**2-ri**2))
    yc = radial_mean * (1-math.cos(angle)) / angle * FT
    return [0.0, 0.0, fz], [yc*fz, -3810.0*fz, 0.0]


def displacement(case, load, factor, xyz):
    if case == CYLINDER:
        return cylinder_fields(xyz, factor)[0]
    if case == ROOF:
        return [0.0, 0.0, -92.17152 * factor * xyz[0] / 7620.0]
    axis = {"Fx": 0, "Fy": 1, "Fz": 2}[load]
    published_mm = {"Fx": 0.000762, "Fy": 2.74574, "Fz": 10.97534}[load]
    values = [0.0, 0.0, 0.0]
    values[axis] = published_mm * factor * xyz[0] / 152.4
    return values


def observation(settings, cells):
    case, load, factor = settings["case"], settings["load_case"], settings["load_factor"]
    indices = itertools.product(*(range(2*n+1) for n in cells))
    logical = [[i/(2*cells[0]), j/(2*cells[1]), k/(2*cells[2])]
               for i, j, k in indices if (i % 2 + j % 2 + k % 2) <= 1]
    xyz = [physical(case, point) for point in logical]
    gauss = [-math.sqrt(3/5), 0.0, math.sqrt(3/5)]
    points = []
    for eid, element in enumerate(itertools.product(*(range(n) for n in cells)), 1):
        for pid, local in enumerate(itertools.product(gauss, repeat=3), 1):
            point = physical(case, [(i+(g+1)/2)/n for i, g, n in zip(element, local, cells)])
            stress = cylinder_fields(point, factor)[1] if case == CYLINDER else [0.0]*6
            points.append({"element_id": eid, "point_id": pid, "coordinates_mm": point,
                           "components_mpa": stress})
    force, moment = integrals(case, load, factor)
    return {
        "cells": list(cells), "node_ids": list(range(1, len(xyz)+1)), "coordinates_mm": xyz,
        "displacements_mm": [displacement(case, load, factor, point) for point in xyz],
        "reaction_n": [-v for v in force], "reaction_moment_n_mm": [-v for v in moment],
        "applied_force_n": force, "applied_moment_n_mm": moment, "stress_points": points,
        "element_count": math.prod(cells),
        "field_completeness": {"displacement": True, "stress": True, "reaction": True, "native_mesh": True},
        "native_fields_artifact": f"simulation/mesh-{cells[0]}-{cells[1]}-{cells[2]}/native-fields.med",
    }


def records(settings):
    return [observation(settings, cells) for cells in settings["mesh_cells"]]


def verdicts(outcome):
    return {row["code"]: row["status"] for row in outcome["checks"]}


def selected(record, targets, tolerance=1e-8):
    return [i for i, xyz in enumerate(record["coordinates_mm"])
            if any(max(abs(a-b) for a, b in zip(xyz, target)) <= tolerance for target in targets)]


@pytest.mark.parametrize("case,load,expected_cells", [
    (BEAM, "Fx", [[6, 1, 1], [12, 2, 2], [24, 4, 4]]),
    (CYLINDER, "pressure", [[2, 4, 1], [4, 8, 1], [8, 16, 2]]),
    (ROOF, "gravity", [[4, 4, 1], [8, 8, 1], [16, 16, 2]]),
])
def test_defaults_are_frozen_and_independent(case, load, expected_cells):
    value = specification(case)
    assert set(value) == {"case", "load_case", "load_factor", "mesh_cells"}
    assert value["load_case"] == load
    assert value["mesh_cells"] == expected_cells
    value["mesh_cells"][0][0] = 47
    assert specification(case)["mesh_cells"] == expected_cells
    raw = case_definition(case)
    raw["material"]["poisson_ratio"] = 0.49
    assert case_definition(case)["material"]["poisson_ratio"] in (0.0, 0.3)


@pytest.mark.parametrize("change", [
    {"case": "new_case"}, {"case": True}, {"load_case": "torsion"}, {"load_case": "pressure"},
    {"load_factor": True}, {"load_factor": 0.0}, {"load_factor": -1.0}, {"load_factor": 2.00001},
    {"load_factor": math.inf}, {"load_factor": math.nan}, {"load_factor": "1.0"},
    {"mesh_cells": [[1, 1, 1]]}, {"mesh_cells": [[1, 1, 1]]*4},
    {"mesh_cells": [[1, 1, 1], [1, 1, 1]]}, {"mesh_cells": [[2, 2, 1], [1, 2, 2]]},
    {"mesh_cells": [[1, 1, 1], [True, 2, 1]]}, {"mesh_cells": [[1, 1, 1], [2.0, 2, 1]]},
    {"mesh_cells": [[1, 1, 1], [49, 1, 1]]}, {"mesh_cells": [[1, 1, 1], [16, 16, 8]]},
    {"mesh_cells": [[1, 1, 1], [0, 2, 1]]}, {"numerical_tolerance": 1.0},
])
def test_invalid_settings_refuse_before_numerical_feedback(change):
    with pytest.raises(ValueError):
        validate_settings({**request(BEAM), **change})


def test_missing_setting_and_unrepresentable_reference_are_rejected():
    value = request(BEAM)
    del value["mesh_cells"]
    with pytest.raises(ValueError):
        validate_settings(value)
    with pytest.raises(ValueError, match="zero"):
        validate_settings(request(BEAM, factor=5e-324))


@pytest.mark.parametrize("case", CASES)
def test_common_declaration_is_solver_independent_and_uses_mpa(case):
    declaration = model_declaration(request(case))
    assert set(declaration["model"]) == {"geometry", "materials", "mesh"}
    material = declaration["model"]["materials"][0]
    assert material["youngs_modulus"]["unit"] == "MPa"
    assert material["poisson_ratio"]["unit"] == "1"
    assert declaration["model"]["mesh"]["element_type"] == "HEXA20"
    assert declaration["model"]["mesh"]["order"] == 2
    assert {row["field"] for row in declaration["outputs"]["fields"]} == {"displacement", "stress", "reactions"}
    assert declaration["definition_sha256"] == "3f198843b47b6f93c8ad81e4dfc86ce75c547ced983492f01d2210d386459038"
    encoded = json.dumps(declaration).lower()
    assert all(word not in encoded for word in ("c3d20", "calculix", "code_aster", "native_path", "c:/", "docker"))


def test_references_units_signs_and_cylinder_conflict_are_preserved():
    beam = model_declaration(request(BEAM, "Fy"))["reference"]
    assert beam["primary_response_mm"] == pytest.approx(2.74574)
    assert beam["material"]["youngs_modulus_mpa"] == pytest.approx(68947.57293168361)
    cylinder = model_declaration(request(CYLINDER))["reference"]
    assert cylinder["material"]["youngs_modulus_mpa"] == 220000.0
    assert cylinder["primary_response_mm"] == pytest.approx(5/66)
    assert cylinder["secondary_response_mm"] == pytest.approx(2/33)
    assert cylinder["inner_surface_hoop_stress_mpa"] == pytest.approx(500/3)
    assert cylinder["vendor_reference_conflict"]["printed_inner_displacement_mm"] == 0.07936
    assert "UNKNOWN" in cylinder["midas_replication"]
    roof = model_declaration(request(ROOF))["reference"]
    assert roof["primary_response_mm"] == pytest.approx(-92.17152)
    assert roof["published_reference"]["shallow_shell_ft"] == -0.3086
    assert roof["applied_force_n"][2] == pytest.approx(-12500*math.pi*LBF)


@pytest.mark.parametrize("case,load", [(BEAM, "Fx"), (BEAM, "Fy"), (BEAM, "Fz"),
                                       (CYLINDER, "pressure"), (ROOF, "gravity")])
@pytest.mark.parametrize("factor", [0.5, 1.0, 2.0])
def test_valid_complete_observations_and_linear_scaling_leave_engineering_unknown(case, load, factor):
    value = request(case, load, factor)
    raw = records(value)
    before = copy.deepcopy(raw)
    outcome = assess(value, raw)
    assert set(verdicts(outcome).values()) == {"PASS"}
    assert all(metric["valid"] is True for metric in outcome["metrics"].values())
    assert outcome["metrics"]["primary_response"]["value"] == pytest.approx(outcome["reference"]["primary_response_mm"])
    assert raw == before
    assert len(outcome["mesh_studies"]) == 2
    assert {"static_strength", "material_qualification", "physical_validation", "fatigue_durability",
            "model_qualification", "original_midas_replication"} == set(outcome["pending_validations"])
    assert "decision" not in outcome
    assert "energy" not in outcome["metrics"]
    assert "residual" not in outcome["metrics"]


def test_only_exact_two_beam_nodes_and_load_component_define_response():
    value = request(BEAM, "Fy")
    raw = records(value)
    for record in raw:
        chosen = selected(record, [[152.4, 0.0, 0.0], [152.4, 5.08, 0.0]])
        assert len(chosen) == 2
        for i, point in enumerate(record["coordinates_mm"]):
            record["displacements_mm"][i][0] = 99999.0
            if i not in chosen and point[0] == 152.4:
                record["displacements_mm"][i][1] = 77777.0
    outcome = assess(value, raw)
    assert outcome["metrics"]["primary_response"]["value"] == pytest.approx(2.74574)
    assert set(verdicts(outcome).values()) == {"PASS"}


def test_beam_wrong_axis_does_not_pass_using_vector_magnitude():
    value = request(BEAM, "Fy")
    raw = records(value)
    for record in raw:
        record["displacements_mm"] = [[row[1], 0.0, 0.0] for row in record["displacements_mm"]]
    outcome = assess(value, raw)
    assert verdicts(outcome)["reference_response"] == "FAIL"
    assert verdicts(outcome)["positive_load_response_sign"] == "FAIL"
    assert outcome["metrics"]["primary_response"]["value"] == 0.0
    assert all(metric["valid"] is False for metric in outcome["metrics"].values())


def test_absolute_beam_reference_does_not_hide_reversed_response_sign():
    value = request(BEAM, "Fz")
    raw = records(value)
    for record in raw:
        record["displacements_mm"] = [[x, y, -z] for x, y, z in record["displacements_mm"]]
    outcome = assess(value, raw)
    assert verdicts(outcome)["reference_response"] == "PASS"
    assert verdicts(outcome)["positive_load_response_sign"] == "FAIL"
    assert outcome["metrics"]["primary_response"]["value"] == pytest.approx(10.97534)
    assert outcome["metrics"]["signed_primary_response"]["value"] == pytest.approx(-10.97534)


def test_mixed_beam_node_signs_are_not_hidden_by_mean_signed_companion():
    value = request(BEAM, "Fy")
    raw = records(value)
    for record in raw:
        first, second = selected(record, [[152.4, 0.0, 0.0], [152.4, 5.08, 0.0]])
        record["displacements_mm"][first][1] = -2.74574/2
        record["displacements_mm"][second][1] = 2.74574*1.5
    outcome = assess(value, raw)
    assert verdicts(outcome)["reference_response"] == "PASS"
    assert outcome["metrics"]["signed_primary_response"]["value"] > 0
    assert verdicts(outcome)["positive_load_response_sign"] == "FAIL"


def test_roof_exact_inner_signed_z_response_excludes_outer_surface_and_norm():
    value = request(ROOF)
    raw = records(value)
    for record in raw:
        for i, xyz in enumerate(record["coordinates_mm"]):
            record["displacements_mm"][i][0] = 77777.0
            if math.hypot(xyz[1], xyz[2]) > 7581.9 + 1e-8:
                record["displacements_mm"][i][2] = 99999.0
    outcome = assess(value, raw)
    assert set(verdicts(outcome).values()) == {"PASS"}
    assert outcome["metrics"]["primary_response"]["value"] == pytest.approx(-92.17152)
    raw[-1]["displacements_mm"] = [[x, y, abs(z)] for x, y, z in raw[-1]["displacements_mm"]]
    changed = assess(value, raw)
    assert verdicts(changed)["reference_response"] == "FAIL"
    assert changed["metrics"]["primary_response"]["value"] == pytest.approx(92.17152)


def test_good_roof_outer_response_cannot_substitute_wrong_inner_point():
    value = request(ROOF)
    raw = records(value)
    target = physical(ROOF, [1.0, 1.0, 0.0])
    for record in raw:
        i, = selected(record, [target])
        record["displacements_mm"][i][2] = 0.0
    outcome = assess(value, raw)
    assert verdicts(outcome)["reference_response"] == "FAIL"
    assert outcome["metrics"]["primary_response"]["value"] == 0.0


@pytest.mark.parametrize("perturbation,failed_gate", [("wrong_E", "analytical_displacement"),
                                                      ("uz", "analytical_displacement"),
                                                      ("shear_sign", "analytical_stress"),
                                                      ("surface_hoop", "analytical_stress")])
def test_cylinder_cartesian_all_field_checks_at_physical_coordinates(perturbation, failed_gate):
    value = request(CYLINDER)
    raw = records(value)
    fine = raw[-1]
    if perturbation == "wrong_E":
        fine["displacements_mm"] = [cylinder_fields(xyz, young=210000.0)[0] for xyz in fine["coordinates_mm"]]
    elif perturbation == "uz":
        fine["displacements_mm"][len(fine["node_ids"])//2][2] = 0.002
    elif perturbation == "shear_sign":
        for point in fine["stress_points"]:
            point["components_mpa"][3] *= -1
    else:
        for point in fine["stress_points"]:
            point["components_mpa"][1] = 500/3
    outcome = assess(value, raw)
    assert verdicts(outcome)[failed_gate] == "FAIL"
    assert all(metric["valid"] is False for metric in outcome["metrics"].values())
    assert outcome["reference"]["material"]["youngs_modulus_mpa"] == 220000.0
    assert outcome["reference"]["vendor_reference_conflict"]["printed_inner_displacement_mm"] == 0.07936


def test_cylinder_coarse_pointwise_errors_are_retained_but_finest_gated():
    value = request(CYLINDER)
    raw = records(value)
    raw[0]["stress_points"][0]["components_mpa"][0] += 1000
    outcome = assess(value, raw)
    assert verdicts(outcome)["analytical_stress"] == "PASS"
    assert outcome["mesh_studies"][0]["pointwise_stress_relative_error"] > 1
    assert outcome["mesh_studies"][1]["pointwise_stress_relative_error"] < 1e-12


def test_cylinder_response_requires_entire_inner_boundary_cardinality():
    value = request(CYLINDER)
    raw = records(value)
    xyz = raw[-1]["coordinates_mm"][0]
    xyz[0] *= 1.001
    raw[-1]["displacements_mm"][0] = cylinder_fields(xyz)[0]
    with pytest.raises(ValueError, match="complete radial boundary"):
        assess(value, raw)


@pytest.mark.parametrize("field,gate", [("reaction_n", "signed_reaction_balance"),
                                       ("reaction_moment_n_mm", "signed_moment_balance")])
def test_signed_force_and_moment_check_every_grid_even_when_finest_is_correct(field, gate):
    value = request(BEAM, "Fy")
    raw = records(value)
    raw[0][field] = [-x for x in raw[0][field]]
    before = copy.deepcopy(raw)
    outcome = assess(value, raw)
    assert verdicts(outcome)[gate] == "FAIL"
    assert outcome["mesh_studies"][0][field] == before[0][field]
    assert outcome["mesh_studies"][1][field] == before[1][field]
    assert all(metric["valid"] is False and "failed" in metric["reason"] for metric in outcome["metrics"].values())
    assert raw == before


@pytest.mark.parametrize("field,opposite,gate", [
    ("applied_force_n", "reaction_n", "applied_force_reference"),
    ("applied_moment_n_mm", "reaction_moment_n_mm", "applied_moment_reference"),
])
def test_balanced_wrong_applied_catalogue_still_fails_independent_continuous_integral(field, opposite, gate):
    value = request(ROOF)
    raw = records(value)
    for record in raw:
        record[field] = [x*1.01 for x in record[field]]
        record[opposite] = [-x for x in record[field]]
    outcome = assess(value, raw)
    assert verdicts(outcome)["signed_reaction_balance"] == "PASS"
    assert verdicts(outcome)["signed_moment_balance"] == "PASS"
    assert verdicts(outcome)[gate] == "FAIL"


def test_declared_norms_use_positive_global_reference_scales_not_zero_components():
    value = request(CYLINDER)
    raw = records(value)
    fine = raw[-1]
    fine["reaction_n"][2] = 1.0
    fine["reaction_moment_n_mm"][2] = 1.0
    outcome = assess(value, raw)
    assert outcome["mesh_studies"][-1]["reaction_relative_error"] == pytest.approx(1/math.hypot(200000, 200000))
    assert outcome["mesh_studies"][-1]["moment_relative_error"] == pytest.approx(1/(200*math.hypot(200000, 200000)))
    assert verdicts(outcome)["signed_reaction_balance"] == "FAIL"
    assert verdicts(outcome)["signed_moment_balance"] == "PASS"


def test_finest_reference_and_last_pair_trend_are_distinct_and_all_errors_retained():
    value = request(BEAM)
    value["mesh_cells"] = [[1, 1, 1], [2, 1, 1], [3, 1, 1]]
    raw = records(value)
    for record, multiplier in zip(raw, [1.5, 1.015, 1.0]):
        record["displacements_mm"] = [[x*multiplier, y, z] for x, y, z in record["displacements_mm"]]
    outcome = assess(value, raw)
    assert verdicts(outcome)["reference_response"] == "PASS"
    assert verdicts(outcome)["last_two_mesh_response"] == "FAIL"
    assert outcome["metrics"]["mesh_response_relative"]["value"] == pytest.approx(0.015)
    assert [row["reference_relative_error"] for row in outcome["mesh_studies"]] == pytest.approx([0.5, 0.015, 0.0])
    assert outcome["metrics"]["primary_response"]["value"] == pytest.approx(0.000762)
    assert outcome["metrics"]["primary_response"]["valid"] is False


@pytest.mark.parametrize("corruption", [
    "missing_record", "reordered_grid", "wrong_count", "missing_node", "duplicate_node_id", "duplicate_node_xyz",
    "nan_u", "inf_stress", "missing_stress", "duplicate_stress_id", "duplicate_stress_xyz", "unknown_stress_component",
    "false_completeness", "integer_completeness", "extra_completeness", "extra_record", "nonfinite_force",
    "outside_node", "unsafe_artifact", "windows_artifact", "empty_artifact_component", "missing_endpoint",
])
def test_malformed_observations_refuse_rather_than_fabricate_metrics(corruption):
    value = request(BEAM)
    raw = records(value)
    fine = raw[-1]
    if corruption == "missing_record":
        raw.pop()
    elif corruption == "reordered_grid":
        raw.reverse()
    elif corruption == "wrong_count":
        fine["element_count"] += 1
    elif corruption == "missing_node":
        fine["displacements_mm"].pop()
    elif corruption == "duplicate_node_id":
        fine["node_ids"][1] = fine["node_ids"][0]
    elif corruption == "duplicate_node_xyz":
        fine["coordinates_mm"][1] = fine["coordinates_mm"][0][:]
    elif corruption == "nan_u":
        fine["displacements_mm"][0][2] = math.nan
    elif corruption == "inf_stress":
        fine["stress_points"][0]["components_mpa"][5] = math.inf
    elif corruption == "missing_stress":
        fine["stress_points"].pop()
    elif corruption == "duplicate_stress_id":
        fine["stress_points"][1]["point_id"] = fine["stress_points"][0]["point_id"]
    elif corruption == "duplicate_stress_xyz":
        fine["stress_points"][1]["coordinates_mm"] = fine["stress_points"][0]["coordinates_mm"][:]
    elif corruption == "unknown_stress_component":
        fine["stress_points"][0]["components_mpa"].append(0.0)
    elif corruption == "false_completeness":
        fine["field_completeness"]["reaction"] = False
    elif corruption == "integer_completeness":
        fine["field_completeness"]["stress"] = 1
    elif corruption == "extra_completeness":
        fine["field_completeness"]["energy"] = True
    elif corruption == "extra_record":
        fine["strength_accepted"] = True
    elif corruption == "nonfinite_force":
        fine["applied_force_n"][1] = math.inf
    elif corruption == "outside_node":
        fine["coordinates_mm"][0][0] = -1.0
    elif corruption == "unsafe_artifact":
        fine["native_fields_artifact"] = "simulation/../credentials.json"
    elif corruption == "windows_artifact":
        fine["native_fields_artifact"] = "simulation/C:\\data.frd"
    elif corruption == "empty_artifact_component":
        fine["native_fields_artifact"] = "simulation//native.frd"
    else:
        i, = selected(fine, [[152.4, 0.0, 0.0]])
        fine["coordinates_mm"][i][2] = 0.123
    with pytest.raises(ValueError):
        assess(value, raw)


def test_catalogue_ids_and_stress_point_numbers_need_not_equal_array_indices():
    value = request(CYLINDER)
    raw = records(value)
    for record in raw:
        order = list(reversed(range(len(record["node_ids"]))))
        for field in ("node_ids", "coordinates_mm", "displacements_mm"):
            record[field] = [record[field][i] for i in order]
        for point in record["stress_points"]:
            point["point_id"] += 200
        record["stress_points"].reverse()
    outcome = assess(value, raw)
    assert set(verdicts(outcome).values()) == {"PASS"}


@pytest.mark.parametrize("mutation", ["material", "threshold", "axis", "source", "duplicate_key", "nonfinite"])
def test_definition_semantic_drift_is_not_accepted(tmp_path, monkeypatch, mutation):
    original = json.loads(domain._DEFINITION_PATH.read_text(encoding="utf-8"))
    if mutation == "material":
        original["cases"][CYLINDER]["material"]["youngs_modulus_mpa"] = 210000.0
    elif mutation == "threshold":
        original["cases"][CYLINDER]["limits"]["pointwise_displacement_relative"] = 0.1
    elif mutation == "axis":
        original["cases"][ROOF]["response"]["component"] = "y"
    elif mutation == "source":
        original["cases"][BEAM]["source_url"] = "https://example.invalid/other"
    elif mutation == "nonfinite":
        original["cases"][BEAM]["material"]["poisson_ratio"] = math.nan
    text = json.dumps(original)
    if mutation == "duplicate_key":
        text = text.replace('"kind":', '"kind": "fake", "kind":', 1)
    path = tmp_path / "definition.json"
    path.write_text(text, encoding="utf-8")
    monkeypatch.setattr(domain, "_DEFINITION_PATH", path)
    with pytest.raises(ValueError):
        specification(CYLINDER)
    with pytest.raises(ValueError):
        assess(request(CYLINDER), [])


def test_json_order_and_line_endings_do_not_change_semantic_pin(tmp_path, monkeypatch):
    original = json.loads(domain._DEFINITION_PATH.read_text(encoding="utf-8"))
    path = tmp_path / "definition.json"
    path.write_bytes(json.dumps(original, sort_keys=True, indent=4).replace("\n", "\r\n").encode("utf-8"))
    monkeypatch.setattr(domain, "_DEFINITION_PATH", path)
    assert specification(CYLINDER)["load_case"] == "pressure"


def test_definition_is_rechecked_between_declaration_and_assessment(tmp_path, monkeypatch):
    path = tmp_path / "definition.json"
    path.write_bytes(domain._DEFINITION_PATH.read_bytes())
    monkeypatch.setattr(domain, "_DEFINITION_PATH", path)
    value = request(ROOF)
    model_declaration(value)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["cases"][ROOF]["reference"]["signed_displacement_ft"] = -0.1
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="source changed"):
        assess(value, records(value))
