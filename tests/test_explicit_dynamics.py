"""Independent reference and admission tests; synthetic rows are not native proof."""

from copy import deepcopy
import math

import pytest

from plugins.explicit_dynamics.reference import (assess, invalid_metrics, model_declaration,
                                                reference, validate_settings, selected_history_settings,
                                                describe_inputs, bind_inputs)
from scripts.verify_openradioss import specification
from scripts.verify_compliant_drop import specification as compliant_specification


def ideal_rows(settings):
    """TEST ONLY: independent closed-form observations for assessment regressions."""
    m, g, h, v0 = (settings[key] for key in
                    ("mass_kg", "gravity_m_s2", "center_height_m", "initial_velocity_m_s"))
    dt, interval = settings["time_step_s"], settings["history_interval_s"]
    event = (v0 + math.sqrt(v0 * v0 + 2 * g * (h - settings["edge_m"] / 2))) / g
    rows = []
    for index in range(round(settings["end_time_s"] / interval) + 1):
        t = index * interval
        hit = settings["case"] == "rigid_cube_ground_stop" and t >= event
        vt = max(0, t - dt / 2)
        z = settings["edge_m"] / 2 if hit else h + v0 * t - g * t * t / 2
        centered = 0 if hit else v0 - g * t
        ke = m * centered * centered / 2
        rows.append({"time_s": t, "velocity_time_s": vt, "z_m": z,
                     "velocity_m_s": 0 if hit else v0 - g * vt,
                     "energy_velocity_m_s": centered, "acceleration_m_s2": 0 if hit else -g,
                     "kinetic_energy_j": ke, "internal_energy_j": 0,
                     "external_work_j": ke - m * v0 * v0 / 2,
                     "mass_kg": m, "added_mass_kg": 0, "time_step_s": dt,
                     "ground_impulse_n_s": m * (g * t - v0) if hit else 0})
    return rows


def test_closed_form_freeflight_and_perfectly_inelastic_event_values():
    flight = reference(specification(), .2)
    assert flight["z_m"] == pytest.approx(.8038)
    assert flight["velocity_m_s"] == pytest.approx(-1.962)
    assert flight["kinetic_energy_j"] == pytest.approx(1.924722)
    assert flight["mechanical_energy_j"] == pytest.approx(9.81)
    impact = reference(specification("rigid_cube_ground_stop"), .5)
    assert impact["impact_time_s"] == pytest.approx(.44009080705072745)
    assert impact["incident_speed_m_s"] == pytest.approx(4.3172908171676365)
    assert impact["z_m"] == .05 and impact["velocity_m_s"] == 0
    assert impact["ground_impulse_n_s"] == pytest.approx(4.905)
    assert impact["dissipated_impact_energy_j"] == pytest.approx(9.3195)
    assert impact["mechanical_energy_j"] == pytest.approx(.4905)


def test_mass_gravity_initial_velocity_change_independent_reference():
    s = specification()
    s["mass_kg"] = 2
    assert reference(s, .2)["kinetic_energy_j"] == pytest.approx(3.849444)
    s.update(mass_kg=1, gravity_m_s2=4.905)
    assert reference(s, .2)["displacement_m"] == pytest.approx(-.0981)
    s.update(gravity_m_s2=9.81, initial_velocity_m_s=-.5)
    assert reference(s, .2)["displacement_m"] == pytest.approx(-.2962)
    assert reference(s, .2)["velocity_m_s"] == pytest.approx(-2.462)


@pytest.mark.parametrize("key,value", [("edge_m", 0), ("mass_kg", -1), ("mass_kg", True),
    ("gravity_m_s2", float("nan")), ("initial_velocity_m_s", 1), ("initial_velocity_m_s", "-1"),
    ("case", {}), ("case", "arbitrary_deck"), ("center_height_m", .05),
    ("time_step_s", 1e-9), ("history_interval_s", 1e-5), ("end_time_s", 3)])
def test_invalid_parameters_rejected_before_backend(key, value):
    s = specification()
    s[key] = value
    with pytest.raises(ValueError):
        validate_settings(s)


def test_unknown_fields_missing_limits_and_contact_budget_rejected():
    s = specification()
    s["deck"] = "/RUN/arbitrary"
    with pytest.raises(ValueError, match="exactly"):
        validate_settings(s)
    s = specification()
    del s["limits"]["impulse_abs_n_s"]
    with pytest.raises(ValueError, match="limits"):
        validate_settings(s)
    s = specification("rigid_cube_ground_stop")
    s["history_interval_s"] = .001
    with pytest.raises(ValueError, match="every capped cycle"):
        validate_settings(s)
    s.update(time_step_s=1e-6, history_interval_s=1e-6)
    with pytest.raises(ValueError, match="cycle count"):
        validate_settings(s)


def test_common_model_is_reduced_rigid_translation_and_preserves_input():
    settings = specification("rigid_cube_ground_stop")
    original = deepcopy(settings)
    declaration = model_declaration(settings)
    assert declaration["model"]["mesh"]["rigid"] is True
    assert declaration["model"]["materials"][0]["density"]["value"] == pytest.approx(1000)
    assert declaration["model"]["contact"][0]["physical_ground_z_m"] == 0
    assert declaration["model"]["contact"][0]["effective_center_plane_z_m"] == .05
    assert settings == original


@pytest.mark.parametrize("case", ["rigid_cube_freefall", "rigid_cube_ground_stop"])
def test_ideal_synthetic_history_passes_reference_gates_without_physical_release(case):
    s = specification(case)
    result = assess(s, ideal_rows(s))
    assert all(check["status"] == "PASS" for check in result["checks"])
    assert all(metric["valid"] for metric in result["metrics"].values())
    assert {"physical_validation", "material_qualification", "contact_peak_force",
            "contact_peak_acceleration", "rotational_surface_contact"} <= set(result["pending_validations"])


def test_full_postimpact_history_rejects_refall_even_when_last_record_is_rest():
    s = specification("rigid_cube_ground_stop")
    rows = ideal_rows(s)
    support = rows[4401]["ground_impulse_n_s"]
    for row in rows[4401:4451]:
        velocity = -s["gravity_m_s2"] * (row["time_s"] - rows[4401]["time_s"])
        row.update(velocity_m_s=velocity, energy_velocity_m_s=velocity,
                   kinetic_energy_j=.5 * velocity ** 2, external_work_j=.5 * velocity ** 2,
                   ground_impulse_n_s=support)
    result = assess(s, rows)
    failures = {c["code"] for c in result["checks"] if c["status"] == "FAIL"}
    assert {"post_impact_velocity", "post_impact_centered_velocity", "ground_impulse"} <= failures
    assert rows[-1]["velocity_m_s"] == 0
    assert all(not metric["valid"] for metric in result["metrics"].values())


@pytest.mark.parametrize("damage", ["tail", "alternate", "duplicate", "nan", "missing", "clock", "added_mass"])
def test_incomplete_or_inconsistent_histories_cannot_produce_valid_metrics(damage):
    s = specification("rigid_cube_ground_stop")
    rows = ideal_rows(s)
    if damage == "tail": rows.pop()
    elif damage == "alternate": rows = rows[::2]
    elif damage == "duplicate": rows[3] = deepcopy(rows[2])
    elif damage == "nan": rows[3]["velocity_m_s"] = float("nan")
    elif damage == "missing": del rows[3]["kinetic_energy_j"]
    elif damage == "clock": rows[3]["velocity_time_s"] += s["time_step_s"]
    else: rows[3]["added_mass_kg"] = .01
    if damage == "added_mass":
        result = assess(s, rows)
        assert any(c["code"] == "no_added_mass" and c["status"] == "FAIL" for c in result["checks"])
        assert not any(m["valid"] for m in result["metrics"].values())
    else:
        with pytest.raises(ValueError): assess(s, rows)
    assert all(m["value"] is None and not m["valid"] for m in invalid_metrics("TEST ONLY malformed observation").values())


@pytest.mark.parametrize("stiffness,release,peak_force,compression,impulse",[
    (10000,.4719772653957596,441.87630939381313,.044187630939381314,8.956335178490738),
    (20000,.46254375964229546,620.7610581314681,.031038052906573403,8.863699944357812)])
def test_compliant_independent_event_force_energy_and_restitution_constants(stiffness,release,peak_force,compression,impulse):
    s=compliant_specification(stiffness=stiffness)
    final=reference(s,.5)
    assert final["moving_mass_kg"] == pytest.approx(1.001)
    assert final["fixed_mass_kg"] == .001 and final["total_mass_kg"] == pytest.approx(1.002)
    assert final["impact_time_s"] == pytest.approx(.44009080705072745)
    assert final["release_time_s"] == pytest.approx(release)
    assert final["peak_force_n"] == pytest.approx(peak_force)
    assert final["maximum_compression_m"] == pytest.approx(compression)
    assert final["ground_impulse_n_s"] == pytest.approx(impulse)
    peak=reference(s,(final["impact_time_s"]+final["release_time_s"])/2)
    assert peak["velocity_m_s"] == pytest.approx(0,abs=1e-12)
    assert peak["spring_internal_energy_j"] == pytest.approx(.5*stiffness*compression**2)
    assert peak["acceleration_m_s2"] == pytest.approx(peak_force/1.001-9.81)
    assert reference(s,release)["velocity_m_s"] == pytest.approx(final["incident_speed_m_s"])
    assert reference(s,.2)["spring_force_n"] == 0 and final["spring_force_n"] == 0
    assert all(reference(s,t)["mechanical_energy_j"] == pytest.approx(9.81981) for t in [0,.2,.45,release,.5])
    assert final["fixed_anchor_potential_j"] == pytest.approx(-.00981)


def test_compliant_reference_newton_equation_and_velocity_are_independent_derivatives():
    s=compliant_specification();t=.455;delta=1e-6
    before,here,after=[reference(s,v) for v in (t-delta,t,t+delta)]
    assert (after["z_m"]-before["z_m"])/(2*delta) == pytest.approx(here["velocity_m_s"],abs=1e-7)
    assert (after["velocity_m_s"]-before["velocity_m_s"])/(2*delta) == pytest.approx(here["acceleration_m_s2"],abs=1e-5)
    assert here["moving_mass_kg"]*here["acceleration_m_s2"] == pytest.approx(here["spring_force_n"]-here["moving_mass_kg"]*9.81)
    assert here["spring_length_m"] == pytest.approx(here["z_m"]+1)


@pytest.mark.parametrize("key,value",[("spring_mass_kg",0),("spring_mass_kg",.004),
    ("spring_stiffness_n_m",0),("spring_stiffness_n_m",True),("spring_stiffness_n_m",float("inf")),
    ("end_time_s",.46),("history_interval_s",.001)])
def test_compliant_invalid_mass_stiffness_rebound_or_history_admission(key,value):
    s=compliant_specification();s[key]=value
    with pytest.raises(ValueError):validate_settings(s)


def test_compliant_declaration_explicitly_accounts_mass_law_boundary_and_unknowns():
    s=compliant_specification();declaration=model_declaration(s)
    contact=declaration["model"]["contact"][0]
    assert contact["moving_mass_kg"] == pytest.approx(1.001)
    assert contact["fixed_mass_kg"] == .001 and contact["restitution_reference"] == 1
    assert declaration["model"]["materials"][0]["density"]["value"] == pytest.approx(1000)
    assert declaration["boundary_conditions"][0]["location"] == [0,0,-1]
    assert {item["quantity"] for item in declaration["outputs"]["history"]} >= {"spring_axial_force","spring_internal_energy"}
    assert all(not m["valid"] and m["value"] is None for m in invalid_metrics("missing native channels",compliant=True).values())


def selected_settings(case="rigid_cube_freefall"):
    s = selected_history_settings(case)
    s.update(end_time_s=.02, initial_velocity_m_s=.5)
    s["acceleration_history"] = {"time_s": [0, .01, .02], "acceleration_z_m_s2": [-10, 20, -5]}
    s["input_provenance"] = {"origin": "MEASURED_REPORTED", "reference": "  TEST ONLY reported input; unqualified  "}
    return s


def selected_rows(s):
    """TEST ONLY finite native-shaped samples; no solve or trajectory proof.

    Two separate synthetic spring compressions check topology/law semantics,
    not the native dynamic evolution under the declared acceleration pulse.
    """
    compliant = s["case"] == "rigid_cube_compliant_stop"
    moving = s["mass_kg"] + (s["spring_mass_kg"] / 2 if compliant else 0)
    rows, impulse, previous_force = [], 0, 0
    count = round(s["end_time_s"] / s["time_step_s"])
    for index in range(count + 1):
        t, dt = index * s["time_step_s"], s["time_step_s"]
        z = s["center_height_m"] + s["initial_velocity_m_s"] * t
        if compliant and (50 <= index <= 70 or 120 <= index <= 140):
            z = s["edge_m"] / 2 - .001
        force = s.get("spring_stiffness_n_m", 0) * max(0, s["edge_m"] / 2 - z)
        if index:
            impulse += .5 * (force + previous_force) * dt
        previous_force = force
        work = -.0001 if compliant and index > 70 else 0
        row = {"time_s": t, "velocity_time_s": max(0, t - dt / 2), "z_m": z,
            "velocity_m_s": s["initial_velocity_m_s"], "energy_velocity_m_s": s["initial_velocity_m_s"],
            "acceleration_m_s2": 0, "kinetic_energy_j": .5 * moving * s["initial_velocity_m_s"] ** 2,
            "internal_energy_j": work, "external_work_j": work, "mass_kg": s["mass_kg"] + s.get("spring_mass_kg", 0),
            "added_mass_kg": 0, "time_step_s": dt, "ground_impulse_n_s": impulse}
        if compliant:
            row.update(moving_mass_kg=moving, fixed_mass_kg=.001, ground_force_n=force,
                spring_axial_force_n=-force, spring_length_change_m=z - s["center_height_m"], spring_length_m=z + 1,
                spring_internal_energy_j=work, spring_global_internal_energy_j=work, spring_off=1)
        rows.append(row)
    return rows


@pytest.mark.parametrize("case", ["rigid_cube_freefall", "rigid_cube_compliant_stop"])
def test_selected_factory_and_model_preserve_complete_signed_load_and_source_without_reference(case, monkeypatch):
    from plugins.explicit_dynamics import reference as domain
    monkeypatch.setattr(domain, "reference", lambda *a, **k: pytest.fail("Selected inputs must not request a reference"))
    s = selected_settings(case); before = deepcopy(s)
    model = model_declaration(s)
    assert "gravity_m_s2" not in s
    assert model["loads"][0]["acceleration_z_m_s2"] == [-10, 20, -5]
    assert model["loads"][0]["time_s"] == [0, .01, .02]
    assert model["loads"][0]["coordinate_system"] == "global"
    assert "not prescribed" in model["loads"][0]["application"]
    assert model["input_provenance"] == before["input_provenance"]
    assert s == before and validate_settings(s) == before
    model["loads"][0]["acceleration_z_m_s2"][0] = 99
    assert s == before
    if case == "rigid_cube_compliant_stop":
        assert model["model"]["contact"][0]["restitution_reference"] is None
    first = selected_history_settings(case); first["acceleration_history"]["time_s"][0] = 1
    assert selected_history_settings(case)["acceleration_history"]["time_s"][0] == 0


@pytest.mark.parametrize("mutate", [
    lambda s: s.update(case="rigid_cube_ground_stop"),
    lambda s: s.update(case=[]),
    lambda s: s.update(mode="invented_mode"),
    lambda s: s.update(gravity_m_s2=9.81),
    lambda s: s.update(initial_velocity_m_s=10.1),
    lambda s: s.update(initial_velocity_m_s=True),
    lambda s: s.update(mass_kg=0),
    lambda s: s.update(end_time_s=.02005),
    lambda s: s.update(limits={"mass_relative": 1e-7}),
    lambda s: s["limits"].update(energy_abs_j=.01),
    lambda s: s["input_provenance"].update(origin="QUALIFIED"),
    lambda s: s["input_provenance"].update(reference="  "),
    lambda s: s["input_provenance"].update(reference="a" * 2001),
    lambda s: s["input_provenance"].update(path="/native"),
    lambda s: s["acceleration_history"].update(time_s=[0]),
    lambda s: s["acceleration_history"].update(time_s=[0, .01, .01]),
    lambda s: s["acceleration_history"].update(time_s=[.001, .01, .02]),
    lambda s: s["acceleration_history"].update(time_s=[0, .01, .019]),
    lambda s: s["acceleration_history"].update(acceleration_z_m_s2=[0, 1]),
    lambda s: s["acceleration_history"].update(acceleration_z_m_s2=[0, True, 0]),
    lambda s: s["acceleration_history"].update(acceleration_z_m_s2=[0, float("nan"), 0]),
    lambda s: s["acceleration_history"].update(acceleration_z_m_s2=[0, float("inf"), 0]),
    lambda s: s["acceleration_history"].update(acceleration_z_m_s2=[0, 100.1, 0]),
    lambda s: s["acceleration_history"].update(acceleration_z_m_s2=[[0], 1, 0]),
    lambda s: s["acceleration_history"].update(extra="native-card"),
])
def test_selected_invalid_inputs_refuse_before_any_native_call(mutate):
    s = selected_settings(); mutate(s)
    with pytest.raises(ValueError): validate_settings(s)


def test_selected_bounds_resource_coverage_and_native_knot_representability():
    s = selected_settings()
    s["acceleration_history"] = {"time_s": [i * .02 / 15 for i in range(16)],
                                 "acceleration_z_m_s2": [-100 + i * 200 / 15 for i in range(16)]}
    s["initial_velocity_m_s"] = 10
    assert len(validate_settings(s)["acceleration_history"]["time_s"]) == 16
    s["acceleration_history"]["time_s"].insert(1, .0001)
    s["acceleration_history"]["acceleration_z_m_s2"].insert(1, 0)
    with pytest.raises(ValueError, match="sixteen"): validate_settings(s)
    s = selected_settings(); s["acceleration_history"] = {"time_s": [0, .01, .0100000000000001, .02],
        "acceleration_z_m_s2": [0, 0, 0, 0]}
    with pytest.raises(ValueError, match="native card"): validate_settings(s)
    s = selected_settings(); s["time_step_s"] = 1e-6; s["end_time_s"] = .3
    s["acceleration_history"]["time_s"][-1] = .3
    with pytest.raises(ValueError, match="cycle count"): validate_settings(s)
    s = selected_settings(); s["history_interval_s"] = .01
    with pytest.raises(ValueError, match="ten intervals"): validate_settings(s)
    s = selected_settings("rigid_cube_compliant_stop"); s["history_interval_s"] = .0002
    with pytest.raises(ValueError, match="every capped cycle"): validate_settings(s)
    with pytest.raises(ValueError, match="no canonical"): reference(selected_settings(), .01)


@pytest.mark.parametrize("case", ["rigid_cube_freefall", "rigid_cube_compliant_stop"])
def test_selected_exact_leaf_bindings_match_common_context_and_do_not_change_units_mass_or_source(case):
    from caelab.model_parameters import bind, expected_settings, expected_declaration
    from caelab.adapters.openradioss import OpenRadiossAdapter
    s = selected_settings(case); before = deepcopy(s); descriptors = describe_inputs(s)
    assignments = {"initial_velocity_m_s": -.5, "acceleration_z_1": -25}
    if case == "rigid_cube_compliant_stop": assignments["spring_stiffness_n_m"] = 20000
    bound = bind(OpenRadiossAdapter(), s, assignments)
    assert bound == expected_settings(s, descriptors, assignments)
    assert model_declaration(bound) == expected_declaration(model_declaration(s), descriptors, assignments)
    assert bound["input_provenance"] == s["input_provenance"]
    assert bound["mass_kg"] == s["mass_kg"] and bound["edge_m"] == s["edge_m"]
    assert s == before
    for bad in ({"mass_kg": 2}, {"acceleration_z_3": 0}, {"initial_velocity_m_s": True}, {"acceleration_z_1": 101}):
        with pytest.raises(ValueError): bind_inputs(s, bad)


@pytest.mark.parametrize("case", ["rigid_cube_freefall", "rigid_cube_compliant_stop"])
def test_selected_retains_actual_responses_two_clocks_signed_work_and_unknown_reference(case):
    s = selected_settings(case); rows = selected_rows(s); original = deepcopy(rows)
    result = assess(s, rows)
    assert all(check["status"] == "PASS" for check in result["checks"])
    assert result["reference"] is None and result["reference_qualification"] == "UNKNOWN"
    assert {"reference_agreement", "time_step_sensitivity", "physical_validation", "material_qualification"} <= set(result["pending_validations"])
    assert "mesh_convergence" not in result["pending_validations"]
    assert result["metrics"]["final_velocity_sample_time"]["value"] == pytest.approx(.01995)
    assert result["metrics"]["final_sample_time"]["value"] == .02
    assert result["metrics"]["final_displacement"]["value"] == pytest.approx(.01)
    for name in ("mechanical_energy_error", "impact_time") + (("release_time", "restitution") if case.endswith("compliant_stop") else ()):
        assert result["metrics"][name]["value"] is None and not result["metrics"][name]["valid"]
    if case.endswith("compliant_stop"):
        assert result["metrics"]["minimum_signed_spring_work"]["value"] == -.0001
        assert result["metrics"]["ground_impulse"]["value"] == rows[-1]["ground_impulse_n_s"]
    assert rows == original


@pytest.mark.parametrize("damage", ["tail", "interior", "clock", "nan", "missing", "mass", "added_mass"])
def test_selected_complete_output_refuses_invalid_coverage_or_marks_native_mass_responses_invalid(damage):
    s = selected_settings(); rows = selected_rows(s)
    if damage == "tail": rows.pop()
    elif damage == "interior": rows.pop(50)
    elif damage == "clock": rows[30]["velocity_time_s"] += .001
    elif damage == "nan": rows[30]["kinetic_energy_j"] = float("nan")
    elif damage == "missing": del rows[30]["external_work_j"]
    elif damage == "mass": rows[30]["mass_kg"] = 1.01
    else: rows[30]["added_mass_kg"] = .01
    if damage in {"mass", "added_mass"}:
        result = assess(s, rows)
        assert any(check["status"] == "FAIL" for check in result["checks"])
        assert not any(metric["valid"] for metric in result["metrics"].values())
    else:
        with pytest.raises(ValueError): assess(s, rows)
