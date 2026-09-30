"""Ballistic flight and an ideal perfectly inelastic, unilateral ground stop.

This pure domain module has no native cards, commands or backend imports.
Mechanical energy is KE + m*g*z; impact dissipates the incident KE. It does
not describe elastic rebound, compliant contact, stress or physical material.
"""

from copy import deepcopy
import math


__version__ = "1.0"
KEYS = {"case", "edge_m", "mass_kg", "center_height_m", "gravity_m_s2",
        "initial_velocity_m_s", "end_time_s", "time_step_s", "history_interval_s", "limits"}
LIMIT_KEYS = {"displacement_abs_m", "velocity_abs_m_s", "energy_abs_j", "mass_relative",
              "impact_time_abs_s", "impulse_abs_n_s", "penetration_abs_m"}
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
    if not isinstance(settings, dict) or set(settings) != KEYS:
        raise ValueError("Explicit settings must contain exactly the supported bounded fields")
    if type(settings["case"]) is not str or settings["case"] not in {"rigid_cube_freefall", "rigid_cube_ground_stop"}:
        raise ValueError("Supported cases are rigid_cube_freefall and rigid_cube_ground_stop")
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
    if not isinstance(limits, dict) or set(limits) != LIMIT_KEYS:
        raise ValueError("Explicit limits must contain exactly the predeclared numerical gates")
    normalized["limits"] = {key: number(limits[key], key, True) for key in sorted(LIMIT_KEYS)}
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
    return normalized


def reference(settings, time_s, *, validate=True):
    s = validate_settings(settings) if validate else settings
    t = number(time_s, "reference time_s")
    if t < 0 or t > s["end_time_s"] + 1e-8:
        raise ValueError("Reference time lies outside the declared interval")
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
    return {"model": {"geometry": {"type": "cube", "edge": {"value": s["edge_m"], "unit": "m"},
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


def invalid_metrics(reason):
    return {name: {"value": None, "unit": unit, "valid": False, "reason": reason}
            for name, unit in (("final_displacement", "m"), ("final_velocity", "m/s"),
                               ("final_kinetic_energy", "J"), ("mechanical_energy_error", "J"),
                               ("impact_time", "s"), ("ground_impulse", "N s"))}


def assess(settings, rows):
    s = validate_settings(settings)
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
