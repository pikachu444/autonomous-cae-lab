"""Independent ballistic, ideal-stop and conservative compliant-stop mechanics.

This pure domain module has no native cards, commands or backend imports.
Mechanical energy is KE + m*g*z; ideal impact dissipates the incident KE.
The separate compliant case has a known linear unilateral law and restitution
one. Neither reference qualifies surface contact, stress or physical material.
"""

from copy import deepcopy
import math


__version__ = "1.1"
KEYS = {"case", "edge_m", "mass_kg", "center_height_m", "gravity_m_s2",
        "initial_velocity_m_s", "end_time_s", "time_step_s", "history_interval_s", "limits"}
LIMIT_KEYS = {"displacement_abs_m", "velocity_abs_m_s", "energy_abs_j", "mass_relative",
              "impact_time_abs_s", "impulse_abs_n_s", "penetration_abs_m"}
COMPLIANT_CASE = "rigid_cube_compliant_stop"
COMPLIANT_KEYS = {"spring_stiffness_n_m", "spring_mass_kg"}
COMPLIANT_LIMIT_KEYS = (LIMIT_KEYS - {"penetration_abs_m"}) | {"force_abs_n", "restitution_abs"}
ANCHOR_Z_M = -1.0
PENDING = ["model_qualification", "material_qualification", "static_strength",
           "physical_validation", "fatigue_durability", "failure_model",
           "contact_peak_force", "contact_peak_acceleration", "rotational_surface_contact"]


def number(value, label, positive=False):
    if type(value) not in (int, float):
        raise ValueError(f"{label} must be a finite number")
    try:
        result = float(value)
    except (ValueError, OverflowError) as exc:
        raise ValueError(f"{label} must be finite") from exc
    if not math.isfinite(result) or (positive and result <= 0):
        raise ValueError(f"{label} must be finite{' and positive' if positive else ''}")
    return result


def validate_settings(settings):
    compliant = isinstance(settings, dict) and settings.get("case") == COMPLIANT_CASE
    expected_keys = KEYS | COMPLIANT_KEYS if compliant else KEYS
    if not isinstance(settings, dict) or set(settings) != expected_keys:
        raise ValueError("Explicit settings must contain exactly the supported bounded fields")
    if type(settings["case"]) is not str or settings["case"] not in {"rigid_cube_freefall", "rigid_cube_ground_stop", COMPLIANT_CASE}:
        raise ValueError("Unsupported bounded rigid-cube case")
    normalized = deepcopy(settings)
    for key in KEYS - {"case", "limits", "initial_velocity_m_s"}:
        normalized[key] = number(settings[key], key, True)
    normalized["initial_velocity_m_s"] = number(settings["initial_velocity_m_s"], "initial_velocity_m_s")
    if (not .001 <= normalized["edge_m"] <= 1 or not .001 <= normalized["mass_kg"] <= 100
            or not normalized["edge_m"] / 2 < normalized["center_height_m"] <= 10
            or not .1 <= normalized["gravity_m_s2"] <= 100
            or not -10 <= normalized["initial_velocity_m_s"] <= 0
            or not .001 <= normalized["end_time_s"] <= 2
            or not 1e-6 <= normalized["time_step_s"] <= 1e-3
            or not normalized["time_step_s"] <= normalized["history_interval_s"] <= .01):
        raise ValueError("Input exceeds the bounded SI rigid-cube benchmark range")
    if normalized["end_time_s"] / normalized["time_step_s"] > 200000:
        raise ValueError("Requested cycle count exceeds the 200000-cycle admission budget")
    if normalized["end_time_s"] / normalized["history_interval_s"] >= 20000:
        raise ValueError("Requested history exceeds the bounded 20000-sample parser budget")
    if normalized["end_time_s"] / normalized["history_interval_s"] < 10:
        raise ValueError("At least ten history intervals are required")
    limits = settings["limits"]
    limit_keys = COMPLIANT_LIMIT_KEYS if compliant else LIMIT_KEYS
    if not isinstance(limits, dict) or set(limits) != limit_keys:
        raise ValueError("Explicit limits must contain exactly the predeclared numerical gates")
    normalized["limits"] = {key: number(limits[key], key, True) for key in sorted(limit_keys)}
    if compliant:
        for key in COMPLIANT_KEYS:
            normalized[key] = number(settings[key], key, True)
        if normalized["spring_mass_kg"] != .002 or not 1000 <= normalized["spring_stiffness_n_m"] <= 1e6:
            raise ValueError("Compliant benchmark requires declared spring mass .002 kg and bounded positive stiffness")
    ref = reference(normalized, normalized["end_time_s"], validate=False)
    if normalized["case"] == "rigid_cube_freefall" and ref["free_height_m"] <= normalized["edge_m"] / 2:
        raise ValueError("Freefall benchmark must end before the ground-contact event")
    if normalized["case"] == "rigid_cube_ground_stop":
        if ref["impact_time_s"] < 10 * normalized["time_step_s"]:
            raise ValueError("Ground-stop benchmark requires ten resolved pre-impact cycles")
        if normalized["end_time_s"] <= ref["impact_time_s"] + 10 * normalized["time_step_s"]:
            raise ValueError("Ground-stop benchmark must cover impact and a post-impact interval")
        if normalized["history_interval_s"] != normalized["time_step_s"]:
            raise ValueError("Ground-stop raw impulse assessment requires history on every capped cycle")
        cycles = normalized["end_time_s"] / normalized["time_step_s"]
        if abs(cycles - round(cycles)) > 1e-8:
            raise ValueError("Ground-stop terminal time must be an exact declared capped cycle")
    if compliant:
        if normalized["history_interval_s"] != normalized["time_step_s"]:
            raise ValueError("Compliant-stop force/energy assessment requires history on every capped cycle")
        cycles = normalized["end_time_s"] / normalized["time_step_s"]
        if abs(cycles - round(cycles)) > 1e-8:
            raise ValueError("Compliant-stop terminal time must be an exact declared capped cycle")
        if ref["impact_time_s"] < 10 * normalized["time_step_s"] or ref["contact_duration_s"] < 100 * normalized["time_step_s"]:
            raise ValueError("Compliant benchmark requires resolved freeflight and at least 100 contact cycles")
        if normalized["end_time_s"] <= ref["release_time_s"] + 10 * normalized["time_step_s"]:
            raise ValueError("Compliant benchmark must cover complete contact and rebound")
        # This one-contact canonical reference does not conceal a second impact.
        if normalized["end_time_s"] >= ref["release_time_s"] + 2 * ref["incident_speed_m_s"] / normalized["gravity_m_s2"]:
            raise ValueError("Compliant benchmark must end before the second contact")
        if normalized["edge_m"] / 2 - ref["maximum_compression_m"] <= ANCHOR_Z_M + 1e-6:
            raise ValueError("Predicted spring length reaches its fixed anchor and loses the declared orientation")
    return normalized


def reference(settings, time_s, *, validate=True):
    s = validate_settings(settings) if validate else settings
    t = number(time_s, "reference time_s")
    if t < 0 or t > s["end_time_s"] + 1e-8:
        raise ValueError("Reference time lies outside the declared interval")
    if s["case"] == COMPLIANT_CASE:
        return compliant_reference(s, t)
    m, g, h, v0 = (s[key] for key in ("mass_kg", "gravity_m_s2", "center_height_m", "initial_velocity_m_s"))
    floor = s["edge_m"] / 2
    speed = math.sqrt(v0 * v0 + 2 * g * (h - floor))
    event = (v0 + speed) / g
    free = h + v0 * t - .5 * g * t * t
    hit = s["case"] == "rigid_cube_ground_stop" and t >= event
    z, v = (floor, 0.0) if hit else (free, v0 - g * t)
    kinetic, potential = .5 * m * v * v, m * g * z
    return {"z_m": z, "displacement_m": z - h, "velocity_m_s": v,
            "acceleration_m_s2": 0.0 if hit else -g, "kinetic_energy_j": kinetic,
            "potential_energy_j": potential, "mechanical_energy_j": kinetic + potential,
            "impact_time_s": event, "incident_speed_m_s": speed,
            "impact_impulse_n_s": m * speed,
            "ground_impulse_n_s": m * speed + m * g * (t - event) if hit else 0.0,
            "dissipated_impact_energy_j": .5 * m * speed * speed if hit else 0.0,
            "free_height_m": free, "units": "SI: kg, m, s, N, J"}


def model_declaration(settings):
    s = validate_settings(settings)
    wall = s["case"] == "rigid_cube_ground_stop"
    declaration = {"model": {"geometry": {"type": "cube", "edge": {"value": s["edge_m"], "unit": "m"},
                                     "center": [0, 0, s["center_height_m"]], "unit": "m"},
                      "mesh": {"type": "single_hexahedron", "node_count": 8, "rigid": True},
                      "materials": [{"model": "ideal_rigid_body", "mass": {"value": s["mass_kg"], "unit": "kg"},
                                     "density": {"value": s["mass_kg"] / s["edge_m"] ** 3, "unit": "kg/m^3"}}],
                      "contact": [{"type": "frictionless_unilateral_kinematic_ground_stop", "physical_ground_z_m": 0,
                                   "effective_center_plane_z_m": s["edge_m"] / 2,
                                   "equivalence": "Reduced translation only: center>=edge/2 iff cube bottom>=0; rotating surface contact is unverified",
                                   "rebound": "No elastic restitution; ideal perfectly inelastic stop"}] if wall else []},
            "loads": [{"type": "uniform_gravity", "value": [0, 0, -s["gravity_m_s2"]], "unit": "m/s^2"}],
            "initial_conditions": [{"type": "velocity", "value": [0, 0, s["initial_velocity_m_s"]], "unit": "m/s"}],
            "boundary_conditions": [],
            "outputs": {"fields": [{"field": "nodal_displacement", "unit": "m"},
                                    {"field": "nodal_velocity", "unit": "m/s"}],
                        "history": [{"quantity": key, "unit": unit} for key, unit in
                                    (("center_position", "m"), ("center_velocity", "m/s"),
                                     ("kinetic_energy", "J"), ("mechanical_energy", "J"),
                                     ("ground_impulse", "N s"), ("ground_force_interval_average", "N"),
                                     ("time_step", "s"))]}}
    if s["case"] == COMPLIANT_CASE:
        declaration["model"]["contact"] = [{"type": "conservative_unilateral_linear_compliant_stop",
            "stiffness": {"value": s["spring_stiffness_n_m"], "unit": "N/m"},
            "effective_center_contact_z_m": s["edge_m"] / 2, "fixed_anchor_z_m": ANCHOR_Z_M,
            "spring_mass": {"value": s["spring_mass_kg"], "unit": "kg"},
            "moving_mass_kg": s["mass_kg"] + s["spring_mass_kg"] / 2,
            "fixed_mass_kg": s["spring_mass_kg"] / 2, "restitution_reference": 1,
            "force_application": "Colocated rigid secondary at the center; isolated rigid main point, zero moment arm",
            "scope": "Reduced nonrotating constitutive stop; compliant compression is not surface-contact penetration qualification"}]
        declaration["boundary_conditions"] = [{"type": "fixed_translation", "location": [0, 0, ANCHOR_Z_M], "unit": "m"}]
        declaration["outputs"]["history"].extend({"quantity": key, "unit": unit} for key, unit in
            (("spring_axial_force", "N"), ("spring_length_change", "m"), ("spring_internal_energy", "J")))
    return declaration


def invalid_metrics(reason, *, compliant=False):
    result = {name: {"value": None, "unit": unit, "valid": False, "reason": reason}
            for name, unit in (("final_displacement", "m"), ("final_velocity", "m/s"),
                               ("final_kinetic_energy", "J"), ("mechanical_energy_error", "J"),
                               ("impact_time", "s"), ("ground_impulse", "N s"))}
    if compliant:
        result.update({name: {"value": None, "unit": unit, "valid": False, "reason": reason} for name, unit in
            (("peak_contact_force", "N"), ("peak_spring_internal_energy", "J"), ("minimum_signed_spring_work", "J"), ("release_time", "s"), ("restitution", "1"))})
    return result


def assess(settings, rows):
    s = validate_settings(settings)
    if s["case"] == COMPLIANT_CASE:
        return assess_compliant(s, rows)
    required = {"time_s", "velocity_time_s", "z_m", "velocity_m_s", "energy_velocity_m_s",
                "acceleration_m_s2", "kinetic_energy_j", "internal_energy_j", "external_work_j",
                "mass_kg", "added_mass_kg", "time_step_s", "ground_impulse_n_s"}
    if not isinstance(rows, list) or len(rows) < 10:
        raise ValueError("Native history is missing or incomplete")
    normalized = []
    for row in rows:
        if not isinstance(row, dict) or not required <= set(row):
            raise ValueError("Native history row lacks required time/field/mass/energy/impulse data")
        normalized.append({key: number(row[key], "observed " + key) for key in required})
    times = [row["time_s"] for row in normalized]
    dt, interval = s["time_step_s"], s["history_interval_s"]
    clock_epsilon = 1e-8 * max(1, s["end_time_s"])
    wall = s["case"] == "rigid_cube_ground_stop"
    if (abs(times[0]) > clock_epsilon or any(b <= a for a, b in zip(times, times[1:]))
            or any(b - a > interval + dt + clock_epsilon for a, b in zip(times, times[1:]))
            or abs(times[-1] - s["end_time_s"]) > interval + dt + clock_epsilon):
        raise ValueError("Native history times are truncated, duplicated or inconsistent with the declared coverage")
    if wall and (any(abs((b - a) - dt) > clock_epsilon for a, b in zip(times, times[1:]))
                 or abs(times[-1] - s["end_time_s"]) > clock_epsilon):
        raise ValueError("Ground-stop every-cycle history is missing a cycle or final coverage")
    if any(row["time_step_s"] <= 0 or row["time_step_s"] > dt + clock_epsilon for row in normalized[1:]):
        raise ValueError("Native time step is missing/nonpositive or exceeds the declared cap")
    if any(abs(row["velocity_time_s"] - max(0, row["time_s"] - .5 * row["time_step_s"])) > clock_epsilon for row in normalized):
        raise ValueError("Native velocity clock differs from the declared leapfrog convention")
    checks = []

    def check(code, value, limit):
        checks.append({"code": code, "status": "PASS" if value <= limit else "FAIL", "observed": value, "limit": limit})

    limits = s["limits"]
    exact = [reference(s, t, validate=False) for t in times]
    event = exact[0]["impact_time_s"]
    smooth = [(row, ref) for row, ref in zip(normalized, exact)
              if not wall or row["time_s"] < event - 2 * dt]
    displacement_error = max(abs(row["z_m"] - ref["z_m"]) for row, ref in smooth)
    velocity_error = max(abs(row["velocity_m_s"] - reference(s, row["velocity_time_s"], validate=False)["velocity_m_s"])
                         for row, ref in smooth)
    kinetic_error = max(abs(row["kinetic_energy_j"] - ref["kinetic_energy_j"]) for row, ref in smooth)
    energy_error = max(abs(row["kinetic_energy_j"] + s["mass_kg"] * s["gravity_m_s2"] * row["z_m"]
                           - ref["mechanical_energy_j"]) for row, ref in smooth)
    mass_error = max(abs(row["mass_kg"] - s["mass_kg"]) / s["mass_kg"] for row in normalized)
    kinetic_consistency = max(abs(row["kinetic_energy_j"] - .5 * row["mass_kg"] * row["energy_velocity_m_s"] ** 2)
                              for row in normalized)
    work_error = max(abs(row["external_work_j"] - s["mass_kg"] * s["gravity_m_s2"] *
                         (s["center_height_m"] - row["z_m"])) for row, _ in smooth)
    # Global EWORK includes rigidwall constraint dissipation as well as gravity.
    # ecrit.F's native energy identity is ENTOT=ENTOT0+WFEXT for this case.
    initial_kinetic = .5 * s["mass_kg"] * s["initial_velocity_m_s"] ** 2
    total_work_error = max(abs(row["external_work_j"] -
                              (row["kinetic_energy_j"] + row["internal_energy_j"] - initial_kinetic))
                           for row in normalized)
    check("ballistic_displacement", displacement_error, limits["displacement_abs_m"])
    check("ballistic_velocity", velocity_error, limits["velocity_abs_m_s"])
    check("ballistic_centered_momentum", max(abs(row["energy_velocity_m_s"] - ref["velocity_m_s"]) for row, ref in smooth), limits["velocity_abs_m_s"])
    check("ballistic_acceleration", max(abs(row["acceleration_m_s2"] + s["gravity_m_s2"]) for row, ref in smooth), 1e-6)
    check("ballistic_kinetic_energy", kinetic_error, limits["energy_abs_j"])
    check("ballistic_mechanical_energy", energy_error, limits["energy_abs_j"])
    check("native_mass", mass_error, limits["mass_relative"])
    check("no_added_mass", max(abs(row["added_mass_kg"]) for row in normalized), 1e-12)
    check("native_kinetic_consistency", kinetic_consistency, limits["energy_abs_j"])
    check("native_gravity_work", work_error, limits["energy_abs_j"])
    check("native_total_energy_work_balance", total_work_error, limits["energy_abs_j"])
    check("rigid_internal_energy", max(abs(row["internal_energy_j"]) for row in normalized), limits["energy_abs_j"])
    final, final_ref = normalized[-1], exact[-1]
    impact_time = None
    if wall:
        if any(row["ground_impulse_n_s"] < -1e-12 for row in normalized) or any(
                b["ground_impulse_n_s"] < a["ground_impulse_n_s"] - 1e-9
                for a, b in zip(normalized, normalized[1:])):
            raise ValueError("Unilateral ground impulse is negative or decreases")
        contacts = [row for row in normalized if abs(row["ground_impulse_n_s"]) > 1e-12]
        if not contacts:
            raise ValueError("Native rigidwall contact impulse history is missing")
        impact_time = contacts[0]["time_s"]
        check("impact_event_time", abs(impact_time - event), limits["impact_time_abs_s"])
        post = [(row, ref) for row, ref in zip(normalized, exact) if row["time_s"] >= event + 2 * dt]
        if not post:
            raise ValueError("Native contact history lacks the declared post-impact coverage")
        check("ground_impulse", max(abs(row["ground_impulse_n_s"] - ref["ground_impulse_n_s"])
                                    for row, ref in post), limits["impulse_abs_n_s"])
        # Integral momentum: m(v-v0) = -m*g*t + J_ground, including gravity during rest.
        momentum_error = max(abs(s["mass_kg"] * (row["energy_velocity_m_s"] - s["initial_velocity_m_s"])
                                 + s["mass_kg"] * s["gravity_m_s2"] * row["time_s"] - row["ground_impulse_n_s"])
                             for row in normalized)
        check("impulse_momentum_balance", momentum_error, limits["impulse_abs_n_s"])
        check("ground_penetration", max(0, s["edge_m"] / 2 - min(row["z_m"] for row in normalized)), limits["penetration_abs_m"])
        check("post_impact_velocity", max(abs(row["velocity_m_s"]) for row, _ in post), limits["velocity_abs_m_s"])
        check("post_impact_centered_velocity", max(abs(row["energy_velocity_m_s"]) for row, _ in post), limits["velocity_abs_m_s"])
        check("post_impact_position", max(abs(row["z_m"] - ref["z_m"]) for row, ref in post), limits["displacement_abs_m"])
        check("post_impact_kinetic_energy", max(abs(row["kinetic_energy_j"]) for row, _ in post), limits["energy_abs_j"])
        check("post_impact_mechanical_energy", max(abs(row["kinetic_energy_j"] + s["mass_kg"] * s["gravity_m_s2"] * row["z_m"]
                                                      - ref["mechanical_energy_j"]) for row, ref in post), limits["energy_abs_j"])
    else:
        check("no_ground_impulse", max(abs(row["ground_impulse_n_s"]) for row in normalized), 1e-12)
    valid = all(item["status"] == "PASS" for item in checks)
    values = {"final_displacement": (final["z_m"] - s["center_height_m"], "m"),
              "final_sample_time": (final["time_s"], "s"),
              "final_velocity_sample_time": (final["velocity_time_s"], "s"),
              "final_velocity": (final["velocity_m_s"], "m/s"),
              "final_kinetic_energy": (final["kinetic_energy_j"], "J"),
              "mechanical_energy_error": (energy_error, "J"),
              "ground_impulse": (final["ground_impulse_n_s"], "N s")}
    if impact_time is not None:
        values["impact_time"] = (impact_time, "s")
        values["impact_energy_loss"] = (initial_kinetic + s["mass_kg"] * s["gravity_m_s2"] * s["center_height_m"]
                                        - final["kinetic_energy_j"] - s["mass_kg"] * s["gravity_m_s2"] * final["z_m"], "J")
    metrics = {key: {"value": value, "unit": unit, "valid": valid,
                     **({} if valid else {"reason": "Native dynamics failed one or more predeclared numerical gates"})}
               for key, (value, unit) in values.items()}
    return {"checks": checks, "metrics": metrics, "reference": final_ref,
            "pending_validations": list(PENDING), "sample_count": len(rows),
            "limitations": ["Ideal rigid cube; no stress, deformation, fracture, compliant contact or elastic rebound",
                            "Raw native time labels are used without fitting or shifting a measured curve",
                            "Contact gates cover the full post-event history; eventual rest alone cannot pass the ideal-stop benchmark",
                            "Explicit end-time completion is not iterative residual convergence or physical qualification"]}


def compliant_reference(s, t):
    """Closed-form single contact, followed by conservative elastic rebound.

    The spring's declared half mass is included in the moving rigid mass. Its
    other half is fixed; its gravitational potential is an irrelevant constant.
    The axial coordinate stays positive relative to the fixed anchor.
    """
    m = s["mass_kg"] + s["spring_mass_kg"] / 2
    g, h, v0, k = (s[key] for key in ("gravity_m_s2", "center_height_m", "initial_velocity_m_s", "spring_stiffness_n_m"))
    floor = s["edge_m"] / 2
    speed = math.sqrt(v0 * v0 + 2 * g * (h - floor))
    event = (v0 + speed) / g
    omega = math.sqrt(k / m)
    duration = (2 * math.pi - 2 * math.atan(omega * speed / g)) / omega
    release = event + duration
    peak_compression = (g + math.sqrt(g * g + omega * omega * speed * speed)) / (omega * omega)
    if t < event:
        z, v, delta = h + v0 * t - .5 * g * t * t, v0 - g * t, 0.0
        phase = "freeflight"
    elif t <= release:
        tau = t - event
        delta = g / (omega * omega) * (1 - math.cos(omega * tau)) + speed / omega * math.sin(omega * tau)
        delta = max(0.0, delta)  # Roundoff only at the exact release root.
        z, v = floor - delta, -g / omega * math.sin(omega * tau) - speed * math.cos(omega * tau)
        phase = "contact"
    else:
        tau = t - release
        z, v, delta = floor + speed * tau - .5 * g * tau * tau, speed - g * tau, 0.0
        phase = "rebound"
    force = k * delta
    kinetic, internal, potential = .5 * m * v * v, .5 * k * delta * delta, m * g * z
    impulse = 0.0 if t < event else m * (v + speed + g * (t - event)) if t <= release else m * (2 * speed + g * duration)
    return {"z_m": z, "displacement_m": z - h, "velocity_m_s": v,
            "acceleration_m_s2": force / m - g, "kinetic_energy_j": kinetic,
            "spring_internal_energy_j": internal, "potential_energy_j": potential,
            "mechanical_energy_j": kinetic + internal + potential,
            "moving_mass_kg": m, "fixed_mass_kg": s["spring_mass_kg"] / 2,
            "total_mass_kg": s["mass_kg"] + s["spring_mass_kg"],
            "fixed_anchor_potential_j": s["spring_mass_kg"] / 2 * g * ANCHOR_Z_M,
            "spring_length_m": z - ANCHOR_Z_M, "spring_length_change_m": z - h,
            "spring_force_n": force, "compression_m": delta, "phase": phase,
            "impact_time_s": event, "incident_speed_m_s": speed,
            "contact_duration_s": duration, "release_time_s": release,
            "maximum_compression_m": peak_compression, "peak_force_n": k * peak_compression,
            "omega_rad_s": omega, "restitution": 1.0, "ground_impulse_n_s": impulse,
            "free_height_m": h + v0 * t - .5 * g * t * t,
            "units": "SI: kg, m, s, N, J"}


def assess_compliant(s, rows):
    """All recorded flight/contact/rebound observations enter every gate.

    Native spring IE and force are mandatory independent observations; the
    analytical force or energy never stand in for a missing native channel.
    """
    required = {"time_s", "velocity_time_s", "z_m", "velocity_m_s", "energy_velocity_m_s",
                "acceleration_m_s2", "kinetic_energy_j", "internal_energy_j", "external_work_j",
                "mass_kg", "moving_mass_kg", "fixed_mass_kg", "added_mass_kg", "time_step_s",
                "ground_impulse_n_s", "ground_force_n", "spring_axial_force_n", "spring_length_change_m",
                "spring_length_m", "spring_internal_energy_j", "spring_global_internal_energy_j", "spring_off"}
    if not isinstance(rows, list) or len(rows) < 10:
        raise ValueError("Native compliant history is missing or incomplete")
    if any(not isinstance(row, dict) or not required <= set(row) for row in rows):
        raise ValueError("Native compliant history lacks actual spring force/length/IE or mass observations")
    observed = [{key: number(row[key], "observed " + key) for key in required} for row in rows]
    dt, end = s["time_step_s"], s["end_time_s"]
    eps = 1e-8 * max(1, end)
    times = [row["time_s"] for row in observed]
    if (len(times) != round(end / dt) + 1 or abs(times[0]) > eps or abs(times[-1] - end) > eps
            or any(abs(b - a - dt) > eps for a, b in zip(times, times[1:]))):
        raise ValueError("Native compliant every-cycle history is missing a cycle or terminal coverage")
    if any(abs(row["time_step_s"] - dt) > 1e-10 * dt or
           abs(row["velocity_time_s"] - max(0, row["time_s"] - dt / 2)) > eps for row in observed):
        raise ValueError("Native compliant fixed-step/half-step clock differs from the declared convention")
    refs = [compliant_reference(s, t) for t in times]
    exact = refs[0]
    m, g, k, h = exact["moving_mass_kg"], s["gravity_m_s2"], s["spring_stiffness_n_m"], s["center_height_m"]
    lim, checks = s["limits"], []

    def check(code, value, limit):
        checks.append({"code": code, "status": "PASS" if value <= limit else "FAIL", "observed": value, "limit": limit})

    check("compliant_full_position", max(abs(row["z_m"] - ref["z_m"]) for row, ref in zip(observed, refs)), lim["displacement_abs_m"])
    check("compliant_full_raw_velocity", max(abs(row["velocity_m_s"] - compliant_reference(s, row["velocity_time_s"])["velocity_m_s"]) for row in observed), lim["velocity_abs_m_s"])
    check("compliant_full_centered_velocity", max(abs(row["energy_velocity_m_s"] - ref["velocity_m_s"]) for row, ref in zip(observed, refs)), lim["velocity_abs_m_s"])
    check("compliant_full_kinetic_energy", max(abs(row["kinetic_energy_j"] - ref["kinetic_energy_j"]) for row, ref in zip(observed, refs)), lim["energy_abs_j"])
    check("compliant_full_spring_force", max(abs(row["ground_force_n"] - ref["spring_force_n"]) for row, ref in zip(observed, refs)), lim["force_abs_n"])
    check("compliant_full_spring_energy", max(abs(row["spring_internal_energy_j"] - ref["spring_internal_energy_j"]) for row, ref in zip(observed, refs)), lim["energy_abs_j"])
    energy_error = max(abs(row["kinetic_energy_j"] + row["spring_internal_energy_j"] + m * g * row["z_m"] - ref["mechanical_energy_j"]) for row, ref in zip(observed, refs))
    check("compliant_full_mechanical_energy", energy_error, lim["energy_abs_j"])
    check("native_total_mass", max(abs(row["mass_kg"] - exact["total_mass_kg"]) / exact["total_mass_kg"] for row in observed), lim["mass_relative"])
    check("native_moving_mass", max(abs(row["moving_mass_kg"] - m) / m for row in observed), lim["mass_relative"])
    check("native_fixed_mass", max(abs(row["fixed_mass_kg"] - exact["fixed_mass_kg"]) / exact["fixed_mass_kg"] for row in observed), lim["mass_relative"])
    check("no_added_mass", max(abs(row["added_mass_kg"]) for row in observed), 1e-12)
    check("native_kinetic_consistency", max(abs(row["kinetic_energy_j"] - .5 * m * row["energy_velocity_m_s"] ** 2) for row in observed), lim["energy_abs_j"])
    check("native_gravity_work", max(abs(row["external_work_j"] - m * g * (h - row["z_m"])) for row in observed), lim["energy_abs_j"])
    initial_ke = .5 * m * s["initial_velocity_m_s"] ** 2
    check("native_total_energy_work_balance", max(abs(row["kinetic_energy_j"] + row["internal_energy_j"] - initial_ke - row["external_work_j"]) for row in observed), lim["energy_abs_j"])
    check("native_global_spring_energy_consistency", max(abs(row["internal_energy_j"] - row["spring_internal_energy_j"]) for row in observed), 1e-7)
    check("native_category_spring_energy_consistency", max(abs(row["spring_global_internal_energy_j"] - row["spring_internal_energy_j"]) for row in observed), 1e-7)
    check("native_force_acceleration_balance", max(abs(m * (row["acceleration_m_s2"] + g) - row["ground_force_n"]) for row in observed), 1e-5)
    check("native_spring_force_sign", max(abs(row["ground_force_n"] + row["spring_axial_force_n"]) for row in observed), 1e-8)
    check("native_spring_constitutive_force", max(abs(row["ground_force_n"] - k * max(0, s["edge_m"] / 2 - row["z_m"])) for row in observed), 1e-3)
    check("native_spring_length", max(abs(row["spring_length_m"] - (row["z_m"] - ANCHOR_Z_M)) for row in observed), 1e-8)
    check("native_spring_length_change", max(abs(row["spring_length_change_m"] - (row["z_m"] - h)) for row in observed), 1e-8)
    check("native_spring_stays_active", max(abs(row["spring_off"] - 1) for row in observed), 1e-12)
    check("compliant_full_impulse", max(abs(row["ground_impulse_n_s"] - ref["ground_impulse_n_s"]) for row, ref in zip(observed, refs)), lim["impulse_abs_n_s"])
    check("compliant_full_momentum_balance", max(abs(m * (row["energy_velocity_m_s"] - s["initial_velocity_m_s"]) + m * g * row["time_s"] - row["ground_impulse_n_s"]) for row in observed), lim["impulse_abs_n_s"])
    active = [index for index, row in enumerate(observed) if row["ground_force_n"] > 1e-8]
    if not active or active[-1] + 1 >= len(observed) or any(b != a + 1 for a, b in zip(active, active[1:])):
        raise ValueError("Native compliant force does not cover a complete single contact and rebound")
    first, release_index = active[0], active[-1] + 1
    hit_time, release_time = times[first], times[release_index]
    check("compliant_impact_event", abs(hit_time - exact["impact_time_s"]), lim["impact_time_abs_s"])
    check("compliant_release_event", abs(release_time - exact["release_time_s"]), lim["impact_time_abs_s"])
    # Infer speed at the declared contact height from independently measured
    # post-release z/v and conservative ballistic energy, without moving a curve.
    release_row = observed[release_index]
    speed_squared = release_row["energy_velocity_m_s"] ** 2 + 2 * g * (release_row["z_m"] - s["edge_m"] / 2)
    if release_row["energy_velocity_m_s"] <= 0 or speed_squared <= 0:
        raise ValueError("Native compliant release is missing upward rebound")
    measured_out = math.sqrt(speed_squared)
    restitution = measured_out / exact["incident_speed_m_s"]
    check("compliant_restitution", abs(restitution - 1), lim["restitution_abs"])
    peak = max(row["ground_force_n"] for row in observed)
    check("compliant_peak_force", abs(peak - exact["peak_force_n"]), lim["force_abs_n"])
    valid = all(item["status"] == "PASS" for item in checks)
    final = observed[-1]
    values = {"final_displacement": (final["z_m"] - h, "m"), "final_sample_time": (final["time_s"], "s"),
              "final_velocity_sample_time": (final["velocity_time_s"], "s"), "final_velocity": (final["velocity_m_s"], "m/s"),
              "final_kinetic_energy": (final["kinetic_energy_j"], "J"), "mechanical_energy_error": (energy_error, "J"),
              "ground_impulse": (final["ground_impulse_n_s"], "N s"), "impact_time": (hit_time, "s"),
              "release_time": (release_time, "s"), "restitution": (restitution, "1"), "peak_contact_force": (peak, "N"),
              "peak_spring_internal_energy": (max(row["spring_internal_energy_j"] for row in observed), "J"),
              "minimum_signed_spring_work": (min(row["spring_internal_energy_j"] for row in observed), "J")}
    metrics = {key: {"value": value, "unit": unit, "valid": valid, **({} if valid else {"reason": "Native compliant dynamics failed predeclared gates"})} for key, (value, unit) in values.items()}
    return {"checks": checks, "metrics": metrics, "reference": refs[-1], "pending_validations": list(PENDING),
            "sample_count": len(rows), "limitations": ["Known conservative reduced unilateral spring; surface contact and physical constitutive qualification UNKNOWN",
            "Actual native spring force/IE/LX are retained and assessed at TIME; raw incoming velocity keeps its half-step clock",
            "TYPE4 IE is integrated signed constitutive work; its raw release residue is retained and checked against the fixed independent energy-error budget",
            "Declared .002 kg spring adds .001 kg moving and .001 kg fixed mass; original cube remains 1 kg at the canonical density",
            "Numerical finite-force/restitution evidence does not qualify material, stress, fracture, durability or release"]}
