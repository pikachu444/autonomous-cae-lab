"""Strict native OpenRadioss ASCII time-history parsing (no solver execution)."""

import hashlib
import math
from pathlib import Path
import re

from plugins.explicit_dynamics.reference import ANCHOR_Z_M, COMPLIANT_CASE


SOURCE_PATH = Path(__file__).resolve()
SOURCE_BYTES = SOURCE_PATH.read_bytes()
SOURCE_SHA256 = hashlib.sha256(SOURCE_BYTES).hexdigest()


class ASCIIHistory:
    """Pinned TH40 typed records, not an unlabelled guessed column table."""
    def __init__(self, path):
        if not path.is_file() or path.stat().st_size > 128 * 1024 ** 2:
            raise ValueError("Native ASCII T01 is missing or exceeds 128 MiB")
        self.lines = path.read_text(encoding="ascii").splitlines()
        self.cursor = 0

    def record(self, expected):
        while self.cursor < len(self.lines) and self.lines[self.cursor] == "dropT01 FORMAT":
            self.cursor += 1
        if self.cursor >= len(self.lines):
            raise ValueError("Truncated native typed history record")
        header = self.lines[self.cursor]
        if not re.fullmatch(r"ZZZZZEOR(?:\s+\d+[IRC])+\s*", header):
            raise ValueError("Malformed native typed history header")
        specs = [(int(n), kind) for n, kind in re.findall(r"(\d+)([IRC])", header)]
        if specs != expected:
            raise ValueError(f"Native typed history layout differs: {specs}, expected {expected}")
        self.cursor += 1
        if len(specs) > 1 or specs[0][1] == "C":
            if self.cursor >= len(self.lines) or self.lines[self.cursor].startswith("ZZZZZEOR"):
                raise ValueError("Truncated native mixed/text metadata")
            value = self.lines[self.cursor]
            self.cursor += 1
            widths = {((1, "I"), (72, "C")): 77, ((80, "C"),): 80,
                      ((1, "I"), (40, "C"), (4, "I")): 70,
                      ((1, "I"), (40, "C")): 50, ((5, "I"), (40, "C")): 90}
            if len(value) != widths.get(tuple(specs)):
                raise ValueError("Truncated or overlong native fixed-width metadata")
            return value
        count, kind = specs[0]
        per_line = 16 if kind == "I" else 5
        values = []
        for _ in range((count + per_line - 1) // per_line):
            if self.cursor >= len(self.lines):
                raise ValueError("Truncated native numeric payload")
            line = self.lines[self.cursor]
            self.cursor += 1
            if line.startswith("ZZZZZEOR"):
                raise ValueError("Truncated native numeric payload")
            try:
                values.extend(int(v) if kind == "I" else float(v.replace("D", "E")) for v in line.split())
            except ValueError as exc:
                raise ValueError("Malformed/nonfinite native numeric payload") from exc
        if len(values) != count or any(not math.isfinite(v) for v in values):
            raise ValueError("Incomplete/nonfinite native numeric payload")
        return values

    def remaining(self):
        return self.cursor < len(self.lines)


def _mixed_ints(value, count):
    try:
        values = [int(value[i * 10:(i + 1) * 10]) for i in range(count)]
    except ValueError as exc:
        raise ValueError("Invalid native entity metadata") from exc
    return values


def engine_progress(engine, settings):
    """Actual every-cycle native observations, including the reported percentage."""
    if re.search(r"^\s*(?:WARNING|ERROR\s+ID|FATAL|ABNORMAL|STOP DUE)\b", engine, re.MULTILINE | re.IGNORECASE):
        raise ValueError("Engine reported an invalid model/execution diagnostic")
    observations = []
    control = ("SPRIN", "2") if settings["case"] == COMPLIANT_CASE else ("FIXED", "0")
    for line in engine.splitlines():
        values = line.split()
        if len(values) < 6 or not values[0].isdigit() or not values[5].endswith("%"):
            continue
        try:
            if len(values) != 13 or tuple(values[3:5]) != control or not values[5].endswith("%"):
                raise ValueError("Unexpected native cycle print layout")
            numbers = [float(values[1]), float(values[2]), float(values[5][:-1]),
                       *(float(value) for value in values[6:])]
        except ValueError as exc:
            raise ValueError("Malformed native cycle observation") from exc
        if any(not math.isfinite(value) for value in numbers):
            raise ValueError("Nonfinite native cycle observation")
        observations.append(dict(zip(("time_s", "time_step_s", "native_energy_error_percent",
                                      "internal_energy_j", "kinetic_energy_j", "rotational_energy_j",
                                      "total_external_work_j", "native_mass_error", "mass_kg", "added_mass_kg"), numbers),
                                 cycle=int(values[0]), controlling_element_type=values[3], controlling_element_id=int(values[4])))
    if not observations or [row["cycle"] for row in observations] != list(range(len(observations))):
        raise ValueError("Every-cycle native print history is missing or has a cycle gap")
    dt, end = settings["time_step_s"], settings["end_time_s"]
    # ECRIT uses G11.4; T01 uses the separate nine-significant-digit format.
    def print_roundoff(value):
        return 1e-12 if value == 0 else .50001 * 10 ** (math.floor(math.log10(abs(value))) - 3)
    if (observations[0]["time_s"] != 0 or observations[-1]["time_s"] < end - print_roundoff(end)
            or observations[-1]["time_s"] > end + dt + print_roundoff(end)):
        raise ValueError("Actual Engine cycle history did not reach the declared end time")
    if any(abs(row["time_s"] - row["cycle"] * dt) > print_roundoff(row["cycle"] * dt)
           or abs(row["time_step_s"] - dt) > print_roundoff(dt) for row in observations):
        raise ValueError("Actual Engine cycle time/step is inconsistent with the fixed-step contract")
    cycle_match = re.search(r"TOTAL NUMBER OF CYCLES\s*:\s*(\d+)", engine)
    if not cycle_match or int(cycle_match[1]) not in {len(observations), len(observations) + 1}:
        raise ValueError("Native termination cycle count disagrees with actual printed cycles")
    return observations


def expected_history_times(settings):
    """Pinned HIST2/SORTIE_MAIN schedule on accumulated binary64 native TIME.

    This reconstructs record admission, never adjusts observed response times.
    Terminal animation cycles bypass HIST2 and are deliberately excluded.
    """
    dt, interval, end = (float(f"{settings[key]:.12g}") for key in
                         ("time_step_s", "history_interval_s", "end_time_s"))
    time_s, next_history = 0.0, 0.0
    times = []
    for _ in range(200002):
        if time_s > end:
            return times
        if time_s >= next_history:
            times.append(time_s)
            next_history = min(end, max(time_s, next_history + interval))
        time_s += dt
    raise ValueError("Native fixed-step history schedule exceeds the admission budget")


def starter_admission(output: Path, settings: dict) -> dict:
    """Native preprocessing must qualify the trusted deck before Engine starts."""
    output = Path(output)
    starter = (output / "drop_0000.out").read_text(encoding="ascii")
    if "NORMAL TERMINATION" not in starter or "NO SYNTAX ERROR DETECTED" not in starter:
        raise ValueError("Starter did not establish normal syntax-checked termination")
    errors = re.findall(r"^\s*(\d+) ERROR\(S\)\s*$", starter, re.MULTILINE)
    if not errors or any(int(value) != 0 for value in errors):
        raise ValueError("Starter lacks a zero-error completion record")
    warnings = re.findall(r"^\s*(\d+) WARNING\(S\)\s*$", starter, re.MULTILINE)
    if not warnings or any(int(value) != 0 for value in warnings):
        raise ValueError("Starter warnings prevent this exact canonical card acceptance")
    for label in ("WORK UNIT SYSTEM", "INPUT UNIT SYSTEM"):
        unit = re.search(label + r"[^\n]*\(\s*kg\s*,\s*m\s*,\s*s\s*\)\s+([0-9.E+-]+)\s+([0-9.E+-]+)\s+([0-9.E+-]+)", starter)
        if not unit or any(float(v) != 1 for v in unit.groups()):
            raise ValueError("Actual Starter units are not the declared unscaled SI system")
    compliant = settings["case"] == COMPLIANT_CASE
    counts = [("NUMNOD", 11 if compliant else 9), ("NUMELS", 1), ("NRBODY", 1),
              ("NRWALL", int(settings["case"] == "rigid_cube_ground_stop"))]
    if compliant:
        counts.extend((("NPART", 2), ("NUMGEO", 2), ("NUMELR", 1), ("NUMBCS", 1)))
    for label, expected in counts:
        count = re.search(r"^\s*" + label + r":[^\n]*?\s(\d+)\s*$", starter, re.MULTILINE)
        if not count or int(count[1]) != expected:
            raise ValueError("Starter model entity count differs from the declared bounded case")
    for label, expected in (("PRIMARY NODE", 9), ("REMOVE SECONDARY NODES FROM RIGID WALL(IF=0)", 0),
                            ("CENTER OF MASS FLAG", 3)):
        values = re.findall(re.escape(label) + r"\s+(\d+)\s*$", starter, re.MULTILINE)
        if not values or any(int(value) != expected for value in values):
            raise ValueError("Starter rigid-body node/constraint admission differs from the trusted template")
    if "NO TRUE INCOMPATIBLE KINEMATIC CONDITION" not in starter:
        raise ValueError("Starter did not rule out incompatible kinematic conditions")
    admitted = {"status": "PASS", "units": "unscaled kg,m,s", "errors": 0, "warnings": 0,
                "primary_node": 9, "secondary_nodes_removed_from_wall": True}
    if compliant:
        masses = re.findall(r"NEW MASS\s+([0-9.E+-]+)", starter)
        if len(masses) != 1:
            raise ValueError("Starter must record the actual single rigid-body assembled mass")
        moving_mass = float(masses[0])
        expected_moving = settings["mass_kg"] + settings["spring_mass_kg"] / 2
        mass_section = starter.split("TOTAL MASS AND MASS CENTER")
        if len(mass_section) != 2:
            raise ValueError("Starter total-mass assembly record is missing")
        total_mass = None
        for line in mass_section[1].split("TOTAL INERTIA")[0].splitlines():
            values = line.split()
            if len(values) == 4:
                try:
                    numbers = [float(value) for value in values]
                except ValueError:
                    continue
                if not all(math.isfinite(value) for value in numbers):
                    raise ValueError("Nonfinite Starter mass assembly")
                total_mass = numbers[0]
                break
        if total_mass is None or not math.isfinite(moving_mass):
            raise ValueError("Starter actual mass assembly is incomplete")
        expected_total = settings["mass_kg"] + settings["spring_mass_kg"]
        if abs(moving_mass - expected_moving) > 1e-8 * expected_moving or abs(total_mass - expected_total) > 1e-8 * expected_total:
            raise ValueError("Starter cube/spring mass assembly differs from declared moving/fixed masses")
        centers = re.findall(r"NEW X,Y,Z\s+([0-9.E+-]+)\s+([0-9.E+-]+)\s+([0-9.E+-]+)", starter)
        if len(centers) != 1 or any(abs(float(value) - expected) > 1e-8 for value, expected in zip(centers[0], (0, 0, settings["center_height_m"]))):
            raise ValueError("Starter actual rigid-body center differs from the declared initial center")
        secondary = re.search(r"NUMBER OF NODES\s+(\d+)", starter)
        if not secondary or int(secondary[1]) != 9:
            raise ValueError("Starter must assemble eight cube corners and the colocated secondary attachment")
        admitted.update(moving_mass_kg=moving_mass, fixed_mass_kg=total_mass - moving_mass, total_mass_kg=total_mass)
    return admitted


def parse_history(output: Path, settings: dict) -> dict:
    output = Path(output)
    admission = starter_admission(output, settings)
    engine = (output / "drop_0001.out").read_text(encoding="ascii")
    cycle_match = re.search(r"TOTAL NUMBER OF CYCLES\s*:\s*(\d+)", engine)
    if "NORMAL TERMINATION" not in engine or not cycle_match:
        raise ValueError("Engine did not record normal end-time termination")
    end = re.search(r"FINAL TIME[^\n]*?([0-9.]+(?:E[+-]?\d+)?)\s*$", engine, re.MULTILINE)
    if not end or abs(float(end[1]) - settings["end_time_s"]) > 1e-8:
        raise ValueError("Native Engine end-time declaration differs from settings")
    progress = engine_progress(engine, settings)
    history = ASCIIHistory(output / "dropT01")
    code = history.record([(1, "I"), (72, "C")])
    if int(code[:5]) != 3040:
        raise ValueError("Only pinned native TH40 ASCII metadata is supported")
    native_title = history.record([(80, "C")])
    hierarchy = history.record([(6, "I")])
    n_part, n_mat, n_prop, n_subset, n_group, n_global = hierarchy
    wall = settings["case"] == "rigid_cube_ground_stop"
    compliant = settings["case"] == COMPLIANT_CASE
    expected_hierarchy = [2, 2, 2, 1, 3, 22] if compliant else [1, 2, 1, 1, 3 if wall else 2, 22]
    if hierarchy != expected_hierarchy:
        raise ValueError("Native hierarchy does not cover the exact declared rigid-cube model/history")
    global_ids = history.record([(n_global, "I")])
    if global_ids != list(range(1, n_global + 1)):
        raise ValueError("Native global channel identities differ")
    expected_parts = [(1, "RIGID_CUBE", [0, 1, 1, 0])]
    if compliant:
        # HIST1 part associations are internal material/property indices.
        # TYPE4 material0 refers to the virtual external0/no_title slot2.
        expected_parts.append((2, "STOP_SPRING", [0, 2, 2, 0]))
    for expected_id, expected_title, association in expected_parts:
        part = history.record([(1, "I"), (40, "C"), (4, "I")])
        if int(part[:10]) != expected_id or part[10:50].strip() != expected_title:
            raise ValueError("Native part identity mismatch")
        if [int(part[i:i + 5]) for i in range(50, 70, 5)] != association:
            raise ValueError("Native part material/property association mismatch")
    expected_descriptions = [(1, "RIGID_MASS_CARRIER_NOT_QUALIFIED"), (0, "no_title"), (1, "RIGID_MASS_CARRIER")]
    if compliant:
        expected_descriptions.append((2, "STOP_SPRING_PROPERTY"))
    for expected_id, expected_title in expected_descriptions:
        metadata = history.record([(1, "I"), (40, "C")])
        if int(metadata[:10]) != expected_id or metadata[10:].strip() != expected_title:
            raise ValueError("Native material/property identity mismatch")
    for _ in range(n_subset):
        info = _mixed_ints(history.record([(5, "I"), (40, "C")]), 5)
        if info != [0, 0, 0, n_part, 0] or history.record([(n_part, "I")]) != list(range(1, n_part + 1)):
            raise ValueError("Native global subset identity mismatch")
    groups = []
    expected_groups = {1: (0, [1, 9, 10, 11] if compliant else [1, 9], [3, 6, 9, 18]), 2: (103, [1], [3, 7, 8, 9])}
    if wall:
        expected_groups[3] = (102, [1], [3])
    if compliant:
        expected_groups[4] = (6, [2], [1, 2, 3, 4, 5, 6, 7, 8, 14])
    seen = set()
    for group_index in range(n_group):
        raw = history.record([(5, "I"), (40, "C")])
        identifier, kind, skew, count, variable_count = _mixed_ints(raw, 5)
        if identifier not in expected_groups or identifier in seen:
            raise ValueError("Unexpected/duplicate native selected-history group")
        seen.add(identifier)
        expected_type, expected_ids, expected_vars = expected_groups[identifier]
        if kind != expected_type or skew != 0 or count != len(expected_ids) or variable_count != len(expected_vars):
            raise ValueError("Native selected-history group structure mismatch")
        entities, names = [], []
        for _ in range(count):
            description = history.record([(1, "I"), (40, "C")])
            entities.append(int(description[:10]))
            names.append(description[10:50].strip())
        if entities != expected_ids:
            raise ValueError("Native selected-history entity coverage mismatch")
        variables = history.record([(variable_count, "I")])
        if variables != expected_vars:
            raise ValueError("Native node/rigid-body channel semantics mismatch")
        groups.append({"id": identifier, "type": kind, "title": raw[50:].strip(), "entities": entities,
                       "entity_titles": names, "variables": variables, "width": count * variable_count})
    rows, raw_samples = [], []
    while history.remaining():
        if len(rows) >= 20000:
            raise ValueError("Native history exceeds the bounded 20000-sample parser budget")
        time_s = history.record([(1, "R")])[0]
        global_values = history.record([(n_global, "R")])
        group_values = [history.record([(group["width"], "R")]) for group in groups]
        by_id = {group["id"]: values for group, values in zip(groups, group_values)}
        dz_bottom, v_bottom, a_bottom, z_bottom, dz, velocity, acceleration, z = by_id[1][:8]
        if compliant:
            anchor_dz, anchor_v, anchor_a, anchor_z = by_id[1][8:12]
            if abs(anchor_z - ANCHOR_Z_M) > 1e-8 or max(abs(value) for value in (anchor_dz, anchor_v, anchor_a)) > 1e-8:
                raise ValueError("Native spring anchor is not fixed at the declared position")
        dt = global_values[6]
        mass = global_values[5]
        if mass <= 0:
            raise ValueError("Native total mass must be positive")
        if abs(dt - settings["time_step_s"]) > 1e-10 * settings["time_step_s"]:
            raise ValueError("Native cycle step differs from the fixed-step clock/impulse contract")
        moving_mass = admission["moving_mass_kg"] if compliant else mass
        if compliant and abs(mass - admission["total_mass_kg"]) > 1e-8 * mass:
            raise ValueError("Native Engine total mass differs from actual Starter assembly")
        centered = global_values[4] / moving_mass
        centered_expected = velocity if time_s == 0 else velocity + .5 * dt * acceleration
        centered_residual = centered - centered_expected
        if abs(centered_residual) > 1e-8 * max(1, abs(centered), abs(centered_expected)):
            raise ValueError("Native global momentum and TH main-node leapfrog clocks are inconsistent")
        zero_globals = (2, 3, 7, 10, 11, 12, 13, 14, 15, 18, 19, 20, 21)
        if not compliant:
            zero_globals = (*zero_globals, 9)
        if max(abs(global_values[index]) for index in zero_globals) > 1e-12:
            raise ValueError("Native output violates reduced rigid/lateral/contact-energy/inlet/outlet assumptions")
        if (not compliant and global_values[0] < -1e-12) or global_values[1] < -1e-12:
            raise ValueError("Native internal/kinetic energy is negative")
        if (abs((z - settings["center_height_m"]) - dz) > 1e-8
                or abs(z - z_bottom - settings["edge_m"] / 2) > 1e-8
                or abs(dz - dz_bottom) > 1e-8):
            raise ValueError("Native rigid-body witness fields are internally inconsistent")
        # RGBODV updates secondary A, not its raw incoming V, before TH output.
        # At contact the exact rigid relation is the next velocity advance.
        # DT12 is DT/2 initially, and DT for this admitted constant-step case.
        dt12 = .5 * dt if time_s == 0 else dt
        witness_residual = (velocity + dt12 * acceleration) - (v_bottom + dt12 * a_bottom)
        if abs(witness_residual) > 1e-8:
            raise ValueError("Native main/secondary next-advance velocity relation is inconsistent")
        auxiliary_fields = {}
        if compliant:
            auxiliary_dz, auxiliary_v, auxiliary_a, auxiliary_z = by_id[1][12:]
            auxiliary_residual = (velocity + dt12 * acceleration) - (auxiliary_v + dt12 * auxiliary_a)
            if abs(auxiliary_z - z) > 1e-8 or abs(auxiliary_dz - dz) > 1e-8 or abs(auxiliary_residual) > 1e-8:
                raise ValueError("Native center attachment is not rigidly colocated with main node")
            auxiliary_fields = {"attachment_z_m": auxiliary_z, "attachment_velocity_m_s": auxiliary_v,
                "attachment_acceleration_m_s2": auxiliary_a, "attachment_rigid_advance_residual_m_s": auxiliary_residual}
        if max(abs(v) for v in by_id[2][1:]) > 1e-9:
            raise ValueError("Native rigid body unexpectedly rotates")
        # FNZ is already a cumulative wall impulse, not a force or per-row impulse.
        body_impulse = -by_id[3][0] if wall else 0.0
        force_interval = time_s - rows[-1]["time_s"] if rows else None
        if force_interval is not None and force_interval <= 0:
            raise ValueError("Native wall-force interval has duplicate or decreasing time")
        average_force = ((body_impulse - rows[-1]["ground_impulse_n_s"]) / force_interval
                         if rows else None)
        spring_fields = {}
        if compliant:
            off, fx, fy, fz, mx, my, mz, lx, ie = by_id[4]
            if max(abs(value) for value in (fy, fz, mx, my, mz)) > 1e-12:
                raise ValueError("Native spring has unexpected transverse force or torque")
            force = -fx
            if force < -1e-8 or abs(off - 1) > 1e-12:
                raise ValueError("Native spring force/energy/deletion violates the unilateral elastic law")
            # REDEF3 integrates signed trapezoidal F*dL work; crossing the
            # unilateral kink can leave either-sign numerical residue. Keep it
            # unmodified and use the predeclared independent energy-error gates.
            # HIST2 channel10 is the spring category, already in total IE1.
            if max(abs(global_values[index] - ie) for index in (0, 9)) > 1e-7:
                raise ValueError("Native global/category spring energy does not match actual TH spring IE")
            # Raw current-time spring force is integrated using its actual
            # sampled clock, never replaced with an analytical contact impulse.
            body_impulse = (rows[-1]["ground_impulse_n_s"] + .5 * (force + rows[-1]["ground_force_n"]) * force_interval) if rows else 0.0
            average_force = (body_impulse - rows[-1]["ground_impulse_n_s"]) / force_interval if rows else None
            spring_fields = {"moving_mass_kg": moving_mass, "fixed_mass_kg": admission["fixed_mass_kg"],
                "ground_force_n": force, "spring_axial_force_n": fx, "spring_length_change_m": lx,
                "spring_length_m": settings["center_height_m"] - ANCHOR_Z_M + lx,
                "spring_internal_energy_j": ie, "spring_global_internal_energy_j": global_values[9], "spring_off": off,
                "spring_transverse_force_n": [fy, fz], "spring_local_moment_n_m": [mx, my, mz],
                "anchor_z_m": anchor_z, "anchor_velocity_m_s": anchor_v, "anchor_acceleration_m_s2": anchor_a, **auxiliary_fields}
        rows.append({"time_s": time_s, "velocity_time_s": max(0, time_s - .5 * dt), "z_m": z,
                     "velocity_m_s": velocity, "acceleration_m_s2": acceleration,
                     "energy_velocity_m_s": centered, "centered_velocity_residual_m_s": centered_residual,
                     "kinetic_energy_j": global_values[1], "internal_energy_j": global_values[0],
                     "external_work_j": global_values[8], "mass_kg": mass, "time_step_s": dt,
                     "added_mass_kg": global_values[16], "ground_impulse_n_s": body_impulse,
                     "ground_force_interval_average_n": average_force, "ground_force_interval_s": force_interval,
                     "bottom_z_m": z_bottom, "bottom_velocity_m_s": v_bottom,
                     "bottom_acceleration_m_s2": a_bottom, "rigid_advance_residual_m_s": witness_residual, **spring_fields})
        raw_samples.append({"time_s": time_s, "globals": global_values, "groups": group_values})
    expected_times = expected_history_times(settings)
    if len(rows) != len(expected_times) or any(abs(row["time_s"] - expected) > 1e-8 * max(1, abs(expected))
                                             for row, expected in zip(rows, expected_times)):
        raise ValueError("Native history is incomplete or differs from the exact pinned record schedule")
    return {"format": "OpenRadioss TH40 ASCII typed records", "hierarchy": hierarchy, "native_title": native_title,
            "global_variable_ids": global_ids, "groups": groups, "rows": rows, "raw_samples": raw_samples,
            "native_end_time_s": float(end[1]), "native_cycle_count": int(cycle_match[1]),
            "native_cycle_observations": progress,
            "units": "kg,m,s,N,J; raw cumulative RWALL impulse N s",
            "external_work_policy": "Compliant: actual gravity work and global KE+IE balance; wall: gravity plus constraint work",
            "force_policy": "Compliant: actual current-time local FX, upward force=-FX, trapezoidal native-force impulse; wall: delta(-FNZ)/deltaTIME",
            "spring_energy_policy": "TYPE4 IE is signed native trapezoidal constitutive work; global10 is its category in totalIE1, never double-counted/clamped/replaced",
            "witness_policy": "Raw main/secondary V can differ at an impulse; V+DT12*A must agree. Original observations retained.",
            "clock_policy": "Raw TH/NODE V is at TIME-DT/2, except initial TIME=0; native global KE/momentum and Z are at TIME. No fitted curve shift."}
