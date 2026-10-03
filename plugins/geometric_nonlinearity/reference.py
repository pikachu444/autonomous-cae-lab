"""Independent circular-beam mathematics for a bounded pure end moment.

This module neither runs a solver nor interprets native syntax. Observations
must already have an adapter-proved node/segment/time catalogue. The initial
frame is +X tangent, +Y section height, +Z section width. A positive global Z
moment produces positive Y displacement and positive global Z curvature.
Derived fiber stress and bending energy are not native Cauchy stress or ENEL.
"""

from __future__ import annotations

import copy
import math
import sys


__version__ = "1"

_DEFAULTS = {
    "case": "pure_end_moment_beam",
    "beam": {"length_mm": 1000.0, "width_z_mm": 1.0, "height_y_mm": 2.0},
    "material": {"youngs_modulus_mpa": 210000.0, "poisson_ratio": 0.3},
    "history": {"times_s": [0.0, 1.0, 2.0, 3.0, 4.0],
                "moments_n_mm": [0.0, 7.0, 35.0, 70.0, 140.0]},
    "mesh": {"element_counts": [8, 16, 32]},
    "limits": {
        "displacement_relative": 0.001, "displacement_absolute_mm": 1e-8,
        "finest_displacement_relative": 0.0001,
        "rotation_relative": 1e-5, "rotation_absolute_rad": 1e-8,
        "force_absolute_n": 1e-8,
        "moment_relative": 1e-5, "moment_absolute_n_mm": 1e-6,
        "curvature_relative": 1e-5, "curvature_absolute_per_mm": 1e-10,
        "derived_energy_relative": 1e-5, "derived_energy_absolute_n_mm": 1e-8,
        "min_mesh_rate": 1.8,
    },
}
_RECORD_KEYS = {"element_count", "node_ids", "coordinates_mm", "segments", "states"}
_STATE_KEYS = {"time_s", "displacements_mm", "rotations_rad", "nodal_forces_n",
               "nodal_moments_n_mm", "section_wrenches", "curvatures_per_mm"}
_NODE_FIELDS = ("displacements_mm", "rotations_rad", "nodal_forces_n", "nodal_moments_n_mm")
_PENDING = ["native_global_energy", "static_strength", "material_qualification",
            "model_qualification", "physical_validation", "fatigue_durability"]
_FRAME = {"tangent": [1.0, 0.0, 0.0], "local_y": [0.0, 1.0, 0.0],
          "local_z": [0.0, 0.0, 1.0], "positive_end_moment": "global_z",
          "curvature_basis": "updated_global_xyz",
          "section_wrench_components": ["N", "Vy", "Vz", "T", "My", "Mz"]}


def default_settings() -> dict:
    """A deep independent copy of the frozen benchmark defaults."""
    return copy.deepcopy(_DEFAULTS)


def _keys(value: object, expected: set[str], label: str) -> dict:
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError(f"{label} must contain exactly: {', '.join(sorted(expected))}")
    return value


def _number(value: object, label: str, *, positive: bool = False) -> float:
    if type(value) not in (int, float):
        raise ValueError(f"{label} must be a finite real number, not bool")
    try:
        result = float(value)
    except (ValueError, OverflowError) as error:
        raise ValueError(f"{label} must be a finite real number") from error
    if not math.isfinite(result) or (positive and result <= 0.0):
        raise ValueError(f"{label} must be finite{' and positive' if positive else ''}")
    return result


def _vector(value: object, length: int, label: str) -> list[float]:
    if not isinstance(value, list) or len(value) != length:
        raise ValueError(f"{label} requires exactly {length} finite components")
    return [_number(component, label) for component in value]


def _table(value: object, rows: int, columns: int, label: str) -> list[list[float]]:
    if not isinstance(value, list) or len(value) != rows:
        raise ValueError(f"{label} requires exactly {rows} rows")
    return [_vector(row, columns, label) for row in value]


def _sum(values, label: str) -> float:
    try:
        return _number(math.fsum(values), label)
    except OverflowError as error:
        raise ValueError(f"{label} is not finitely representable") from error


def _section(settings: dict) -> dict:
    b, h = settings["beam"]["width_z_mm"], settings["beam"]["height_y_mm"]
    try:
        area = _number(b * h, "Section area", positive=True)
        iy = _number(h * b ** 3 / 12.0, "Section IY", positive=True)
        iz = _number(b * h ** 3 / 12.0, "Section IZ", positive=True)
    except OverflowError as error:
        raise ValueError("Section properties must be representable") from error
    rigidity = _number(settings["material"]["youngs_modulus_mpa"] * iz,
                       "Bending rigidity E*IZ", positive=True)
    return {"area_mm2": area, "iy_mm4": iy, "iz_mm4": iz, "bending_rigidity_n_mm2": rigidity}


def _displacement(s: float, angle: float) -> list[float]:
    # Computing sin(angle)/angle - 1 loses the entire signed DX near zero.
    # These even/odd Taylor forms join the ordinary trig expression smoothly.
    if abs(angle) < 0.01:
        q = angle * angle
        sinc_minus_one = q * (-1.0 / 6.0 + q * (1.0 / 120.0 + q * (-1.0 / 5040.0 + q / 362880.0)))
        half = angle * 0.5
        r = half * half
        half_sinc = 1.0 + r * (-1.0 / 6.0 + r * (1.0 / 120.0 + r * (-1.0 / 5040.0 + r / 362880.0)))
        dx, dy = s * sinc_minus_one, s * half * half_sinc * half_sinc
    else:
        dx = s * (math.sin(angle) / angle - 1.0)
        dy = s * (2.0 * math.sin(angle * 0.5) ** 2 / angle)
    return [_number(dx, "Reference displacement X"), _number(dy, "Reference displacement Y"), 0.0]


def _reference(settings: dict) -> dict:
    section = _section(settings)
    length, height = settings["beam"]["length_mm"], settings["beam"]["height_y_mm"]
    rigidity, iz = section["bending_rigidity_n_mm2"], section["iz_mm4"]
    history = []
    for time, moment in zip(settings["history"]["times_s"], settings["history"]["moments_n_mm"]):
        curvature = _number(moment / rigidity, "Reference curvature")
        angle = _number(curvature * length, "Reference end rotation")
        displacement = _displacement(length, angle)
        energy = _number(0.5 * moment * angle, "Reference bending energy")
        stress = _number(moment * (height / (2.0 * iz)), "Reference section fiber stress")
        if moment > 0.0 and any(value <= 0.0 for value in (curvature, angle, energy, stress, displacement[1])):
            raise ValueError("Nonzero reference history must be positively representable")
        history.append({"time_s": time, "moment_n_mm": moment,
                        "end_coordinates_mm": [length + displacement[0], displacement[1], 0.0],
                        "end_displacements_mm": displacement, "end_rotations_rad": [0.0, 0.0, angle],
                        "root_reaction": [0.0, 0.0, 0.0, 0.0, 0.0, -moment],
                        "section_wrench": [0.0, 0.0, 0.0, 0.0, 0.0, moment],
                        "curvature_per_mm": [0.0, 0.0, curvature],
                        "derived_section_fiber_stress_mpa": stress, "bending_energy_n_mm": energy})
    return {"case": settings["case"], "frame": copy.deepcopy(_FRAME), "section": section,
            "history": history, "units": {"length": "mm", "force": "N", "moment": "N mm",
                "rotation": "rad", "curvature": "1/mm", "stress": "MPa", "energy": "N mm"},
            "time_meaning": "quasi_static_load_parameter",
            "model": "independent_inextensible_elastic_circular_bending",
            "native_global_energy": "UNKNOWN"}


def _scales(settings: dict, reference: dict) -> dict:
    last = reference["history"][-1]
    return {"displacement_mm": settings["beam"]["length_mm"],
            "rotation_rad": last["end_rotations_rad"][2], "moment_n_mm": last["moment_n_mm"],
            "curvature_per_mm": last["curvature_per_mm"][2], "energy_n_mm": last["bending_energy_n_mm"]}


def _tolerances(settings: dict, scales: dict) -> dict:
    limits = settings["limits"]
    pairs = [("displacement_mm", "displacement_absolute_mm", "displacement_relative"),
             ("rotation_rad", "rotation_absolute_rad", "rotation_relative"),
             ("moment_n_mm", "moment_absolute_n_mm", "moment_relative"),
             ("curvature_per_mm", "curvature_absolute_per_mm", "curvature_relative"),
             ("energy_n_mm", "derived_energy_absolute_n_mm", "derived_energy_relative")]
    result = {quantity: _number(limits[absolute] + limits[relative] * scales[quantity],
                               f"{quantity} tolerance", positive=True)
              for quantity, absolute, relative in pairs}
    result["force_n"] = limits["force_absolute_n"]
    result["finest_displacement_mm"] = _number(
        limits["displacement_absolute_mm"] + limits["finest_displacement_relative"] * scales["displacement_mm"],
        "Finest displacement tolerance", positive=True)
    return result


def validate_settings(settings: dict) -> dict:
    """Normalize the exact bounded request without sharing mutable descendants."""
    _keys(settings, set(_DEFAULTS), "Geometric nonlinearity settings")
    if settings["case"] != "pure_end_moment_beam":
        raise ValueError("Only pure_end_moment_beam is supported")
    beam = _keys(settings["beam"], set(_DEFAULTS["beam"]), "Beam")
    beam = {name: _number(beam[name], name, positive=True) for name in _DEFAULTS["beam"]}
    length = beam["length_mm"]
    if max(beam["width_z_mm"], beam["height_y_mm"]) > length / 20.0:
        raise ValueError("Beam width and height must be <= length/20")
    raw_material = _keys(settings["material"], set(_DEFAULTS["material"]), "Material")
    material = {"youngs_modulus_mpa": _number(raw_material["youngs_modulus_mpa"], "youngs_modulus_mpa", positive=True),
                "poisson_ratio": _number(raw_material["poisson_ratio"], "poisson_ratio")}
    if not -1.0 < material["poisson_ratio"] < 0.5:
        raise ValueError("poisson_ratio must satisfy -1 < nu < 0.5")
    history = _keys(settings["history"], set(_DEFAULTS["history"]), "History")
    times, moments = history["times_s"], history["moments_n_mm"]
    if (not isinstance(times, list) or not isinstance(moments, list) or
            not 3 <= len(times) <= 32 or len(times) != len(moments)):
        raise ValueError("History requires 3 to 32 corresponding instants and moments")
    times = [_number(time, "times_s") for time in times]
    moments = [_number(moment, "moments_n_mm") for moment in moments]
    if (times[0] != 0.0 or moments[0] != 0.0 or any(moment < 0.0 for moment in moments) or
            any(a >= b for a, b in zip(times, times[1:])) or
            any(a >= b for a, b in zip(moments, moments[1:]))):
        raise ValueError("Instants and nonnegative moments must start at zero and strictly increase")
    mesh = _keys(settings["mesh"], {"element_counts"}, "Mesh")
    counts = mesh["element_counts"]
    if (not isinstance(counts, list) or not 2 <= len(counts) <= 3 or
            any(type(count) is not int or not 8 <= count <= 512 for count in counts) or
            any(a >= b for a, b in zip(counts, counts[1:]))):
        raise ValueError("Mesh requires 2 or 3 increasing distinct integer element_counts in [8,512]")
    raw_limits = _keys(settings["limits"], set(_DEFAULTS["limits"]), "Limits")
    limits = {name: _number(raw_limits[name], name, positive=True) for name in _DEFAULTS["limits"]}
    if limits != _DEFAULTS["limits"]:
        raise ValueError("Numerical limits are frozen for the bounded benchmark")
    result = {"case": settings["case"], "beam": beam, "material": material,
              "history": {"times_s": times, "moments_n_mm": moments},
              "mesh": {"element_counts": list(counts)}, "limits": limits}
    reference = _reference(result)
    peak_angle = reference["history"][-1]["end_rotations_rad"][2]
    if not 0.0 < peak_angle <= 1.0:
        raise ValueError("Maximum end rotation must be >0 and <=1 rad")
    fiber_strain = _number(peak_angle * (beam["height_y_mm"] / length) * 0.5,
                           "Maximum fiber strain")
    if fiber_strain > 0.005:
        raise ValueError("Maximum derived fiber strain must be <=0.005")
    _tolerances(result, _scales(result, reference))
    return result


def analytical_reference(settings: dict) -> dict:
    """Independent signed circle, section properties and entire load history."""
    return _reference(validate_settings(settings))


def model_declaration(settings: dict) -> dict:
    """Flat common metadata; native element/section/extraction syntax stays outside Domain."""
    normalized = validate_settings(settings)
    beam, material = normalized["beam"], normalized["material"]
    times = list(normalized["history"]["times_s"])
    return {"case": normalized["case"],
            "geometry": {"type": "straight_beam", "origin": [0.0, 0.0, 0.0], "unit": "mm",
                "length_mm": beam["length_mm"], "tangent": [1.0, 0.0, 0.0],
                "cross_section": {"type": "rectangle", "width_z_mm": beam["width_z_mm"],
                    "height_y_mm": beam["height_y_mm"], "local_y": [0.0, 1.0, 0.0], "local_z": [0.0, 0.0, 1.0]}},
            "materials": [{"model": "linear_elastic_isotropic", "kinematics": "finite_rotation_small_strain",
                "youngs_modulus": {"value": material["youngs_modulus_mpa"], "unit": "MPa"},
                "poisson_ratio": {"value": material["poisson_ratio"], "unit": "1"}}],
            "mesh": {"element_counts": list(normalized["mesh"]["element_counts"]),
                     "order": 1, "topology": "two_node_line"},
            "boundary_conditions": [{"type": "clamped", "selection": {"type": "point", "coordinates_mm": [0.0, 0.0, 0.0]},
                "translations": ["x", "y", "z"], "rotations": ["x", "y", "z"]},
                {"type": "prescribed_displacement", "selection": {"type": "all_nodes"},
                 "component": "z", "value": 0.0, "unit": "mm"}],
            "loads": [{"type": "moment_history", "selection": {"type": "point", "coordinates_mm": [beam["length_mm"], 0.0, 0.0]},
                       "component": "global_z", "times_s": times,
                       "values": list(normalized["history"]["moments_n_mm"]), "unit": "N mm"}],
            "history": copy.deepcopy(normalized["history"]),
            "outputs": {"times_s": list(times), "fields": [
                {"field": "displacement", "components": ["x", "y", "z"], "unit": "mm", "location": "nodes"},
                {"field": "rotation", "components": ["x", "y", "z"], "unit": "rad", "location": "nodes"},
                {"field": "reaction_force", "components": ["x", "y", "z"], "unit": "N", "location": "nodes"},
                {"field": "reaction_moment", "components": ["x", "y", "z"], "unit": "N mm", "location": "nodes"},
                {"field": "section_wrench", "force_components": ["N", "Vy", "Vz"], "force_unit": "N",
                 "moment_components": ["T", "My", "Mz"], "moment_unit": "N mm", "location": "segments", "basis": "local"},
                {"field": "curvature", "components": ["x", "y", "z"], "unit": "1/mm", "location": "segments", "basis": "updated_global"}]}}


def _validated_record(record: dict, count: int, settings: dict) -> dict:
    if not isinstance(record, dict) or not _RECORD_KEYS <= set(record):
        raise ValueError("Mesh observation is missing required beam data")
    if type(record["element_count"]) is not int or record["element_count"] != count:
        raise ValueError("Mesh element_count/order differs from the frozen request")
    ids = record["node_ids"]
    if (not isinstance(ids, list) or len(ids) != count + 1 or
            any(type(node) is not int or node <= 0 for node in ids) or len(set(ids)) != len(ids)):
        raise ValueError("Mesh requires exactly N+1 unique positive integer node_ids")
    coordinates = _table(record["coordinates_mm"], count + 1, 3, "coordinates_mm")
    length = settings["beam"]["length_mm"]
    # Identity roundoff is separate from the engineering displacement bound.
    identity_tolerance = 64.0 * sys.float_info.epsilon * length
    if any(abs(y) > identity_tolerance or abs(z) > identity_tolerance or
           x < -identity_tolerance or x > length + identity_tolerance for x, y, z in coordinates):
        raise ValueError("Original coordinates must lie on the declared straight +X beam")
    order = sorted(range(count + 1), key=lambda index: coordinates[index][0])
    abscissae = [coordinates[index][0] for index in order]
    if (abs(abscissae[0]) > identity_tolerance or abs(abscissae[-1] - length) > identity_tolerance or
            any(a >= b for a, b in zip(abscissae, abscissae[1:]))):
        raise ValueError("Mesh coordinates must uniquely cover root to tip in +X")
    expected = [[ids[a], ids[b]] for a, b in zip(order, order[1:])]
    segments = record["segments"]
    if (not isinstance(segments, list) or len(segments) != count or
            any(not isinstance(pair, list) or len(pair) != 2 or any(type(node) is not int for node in pair)
                for pair in segments) or segments != expected):
        raise ValueError("Segments must be the ordered, connected, oriented +X node-ID chain")
    times = settings["history"]["times_s"]
    if not isinstance(record["states"], list) or len(record["states"]) != len(times):
        raise ValueError("Mesh states must include every requested instant, including zero")
    states = []
    for raw, time in zip(record["states"], times):
        if not isinstance(raw, dict) or not _STATE_KEYS <= set(raw):
            raise ValueError("State is missing required beam fields")
        if _number(raw["time_s"], "Observed time_s") != time:
            raise ValueError("Native state times/order must match the complete request")
        state = {"time_s": time}
        state.update({field: _table(raw[field], count + 1, 3, field) for field in _NODE_FIELDS})
        state["section_wrenches"] = _table(raw["section_wrenches"], count, 6, "section_wrenches")
        state["curvatures_per_mm"] = _table(raw["curvatures_per_mm"], count, 3, "curvatures_per_mm")
        states.append(state)
    lengths = [_number(b - a, "Segment reference length", positive=True) for a, b in zip(abscissae, abscissae[1:])]
    return {"element_count": count, "node_ids": list(ids), "coordinates_mm": coordinates,
            "segments": copy.deepcopy(segments), "segment_lengths_mm": lengths,
            "root_index": order[0], "tip_index": order[-1], "max_segment_length_mm": max(lengths), "states": states}


def _component_error(observed: list, expected: list) -> float:
    return _number(max(abs(a - b) for a, b in zip(observed, expected)), "Component error")


def _cross(a: list[float], b: list[float]) -> list[float]:
    return [_number(a[1] * b[2] - a[2] * b[1], "Nodal force moment"),
            _number(a[2] * b[0] - a[0] * b[2], "Nodal force moment"),
            _number(a[0] * b[1] - a[1] * b[0], "Nodal force moment")]


def assess(settings: dict, records: list[dict]) -> dict:
    """Assess complete signed fields, equilibrium, reference and mesh rates.

    Finite wrong science returns FAIL with the original finite observations and
    invalid metrics. Missing/ambiguous/nonfinite catalogues raise ValueError.
    Every mesh pair is measured using its actual maximum original segment
    length; error at the declared absolute/identity-roundoff floor is UNKNOWN.
    """
    normalized = validate_settings(settings)
    counts = normalized["mesh"]["element_counts"]
    if not isinstance(records, list) or len(records) != len(counts):
        raise ValueError("Complete observations are required for every requested mesh")
    reference = _reference(normalized)
    scales = _scales(normalized, reference)
    tolerances = _tolerances(normalized, scales)
    height, iz = normalized["beam"]["height_y_mm"], reference["section"]["iz_mm4"]
    summaries = []
    for raw, count in zip(records, counts):
        record = _validated_record(raw, count, normalized)
        states = []
        root, tip = record["root_index"], record["tip_index"]
        for state, exact in zip(record["states"], reference["history"]):
            kappa = exact["curvature_per_mm"][2]
            position_error = displacement_error = rotation_error = moment_error = 0.0
            for index, coords in enumerate(record["coordinates_mm"]):
                angle = _number(kappa * coords[0], "Reference node rotation")
                displacement = _displacement(coords[0], angle)
                difference = [_number(a - b, "Displacement difference") for a, b in
                              zip(state["displacements_mm"][index], displacement)]
                position_error = max(position_error, _number(math.hypot(*difference), "Position error"))
                displacement_error = max(displacement_error, max(abs(value) for value in difference))
                rotation_error = max(rotation_error, _component_error(state["rotations_rad"][index], [0.0, 0.0, angle]))
                moment_error = max(moment_error, _component_error(state["nodal_moments_n_mm"][index],
                    [0.0, 0.0, -exact["moment_n_mm"] if index == root else 0.0]))
            force_error = max(abs(value) for row in state["nodal_forces_n"] for value in row)
            force_sum = [_sum((row[axis] for row in state["nodal_forces_n"]), "Full support force sum") for axis in range(3)]
            lever_moments = [_cross(coords, force) for coords, force in zip(record["coordinates_mm"], state["nodal_forces_n"])]
            moment_sum = [_sum((state["nodal_moments_n_mm"][index][axis] + lever_moments[index][axis]
                               for index in range(count + 1)), "Full support moment sum") for axis in range(3)]
            balance = [moment_sum[0], moment_sum[1], _number(moment_sum[2] + exact["moment_n_mm"], "Signed moment balance")]
            root_error = _component_error(state["nodal_moments_n_mm"][root], exact["root_reaction"][3:])
            section_force_error = max(abs(value) for row in state["section_wrenches"] for value in row[:3])
            section_moment_error = max(_component_error(row[3:], exact["section_wrench"][3:]) for row in state["section_wrenches"])
            curvature_error = max(_component_error(row, exact["curvature_per_mm"]) for row in state["curvatures_per_mm"])
            fiber_stress = [_number(row[5] * (height / (2.0 * iz)), "Derived section fiber stress") for row in state["section_wrenches"]]
            energy = _sum((0.5 * wrench[5] * curvature[2] * ds for wrench, curvature, ds in
                           zip(state["section_wrenches"], state["curvatures_per_mm"], record["segment_lengths_mm"])),
                          "Derived bending energy")
            tip_displacement = state["displacements_mm"][tip]
            tip_coordinates = [_number(a + b, "Observed tip position") for a, b in zip(record["coordinates_mm"][tip], tip_displacement)]
            states.append({"time_s": state["time_s"], "moment_n_mm": exact["moment_n_mm"],
                "max_position_error_mm": position_error, "max_component_displacement_error_mm": displacement_error,
                "max_rotation_error_rad": rotation_error, "max_nodal_force_error_n": force_error,
                "max_nodal_moment_error_n_mm": moment_error, "root_moment_error_n_mm": root_error,
                "root_reaction": state["nodal_forces_n"][root] + state["nodal_moments_n_mm"][root],
                "full_support_force_n": force_sum, "full_support_moment_n_mm": moment_sum,
                "force_balance_error_n": max(abs(value) for value in force_sum),
                "moment_balance_error_n_mm": max(abs(value) for value in balance),
                "max_section_force_error_n": section_force_error, "max_section_moment_error_n_mm": section_moment_error,
                "max_curvature_error_per_mm": curvature_error, "tip_coordinates_mm": tip_coordinates,
                "tip_displacements_mm": list(tip_displacement), "tip_rotations_rad": list(state["rotations_rad"][tip]),
                "derived_section_fiber_stresses_mpa": fiber_stress,
                "derived_bending_energy_n_mm": energy,
                "derived_energy_error_n_mm": _number(abs(energy - exact["bending_energy_n_mm"]), "Derived energy error")})
        summaries.append({"element_count": count, "node_count": count + 1,
            "node_ids": list(record["node_ids"]), "coordinates_mm": copy.deepcopy(record["coordinates_mm"]),
            "segments": copy.deepcopy(record["segments"]), "segment_lengths_mm": list(record["segment_lengths_mm"]),
            "max_segment_length_mm": record["max_segment_length_mm"], "states": states,
            "max_position_error_mm": max(state["max_position_error_mm"] for state in states)})
    states = [state for mesh in summaries for state in mesh["states"]]
    maxima = {name: max(state[name] for state in states) for name in (
        "max_position_error_mm", "max_component_displacement_error_mm", "max_rotation_error_rad",
        "max_nodal_force_error_n", "max_nodal_moment_error_n_mm", "root_moment_error_n_mm",
        "force_balance_error_n", "moment_balance_error_n_mm", "max_section_force_error_n",
        "max_section_moment_error_n_mm", "max_curvature_error_per_mm", "derived_energy_error_n_mm")}
    finest_error = summaries[-1]["max_position_error_mm"]
    checks = []

    def check(code: str, observed: object, tolerance: object, passed: bool) -> None:
        checks.append({"code": code, "status": "PASS" if passed else "FAIL", "observed": observed, "limit": tolerance})

    for code, field, quantity in [
        ("analytical_displacement", "max_position_error_mm", "displacement_mm"),
        ("analytical_rotation", "max_rotation_error_rad", "rotation_rad"),
        ("all_nodal_forces", "max_nodal_force_error_n", "force_n"),
        ("all_nodal_moments", "max_nodal_moment_error_n_mm", "moment_n_mm"),
        ("signed_root_moment", "root_moment_error_n_mm", "moment_n_mm"),
        ("full_support_force_balance", "force_balance_error_n", "force_n"),
        ("full_support_moment_balance", "moment_balance_error_n_mm", "moment_n_mm"),
        ("section_forces", "max_section_force_error_n", "force_n"),
        ("signed_section_moments", "max_section_moment_error_n_mm", "moment_n_mm"),
        ("updated_global_curvature", "max_curvature_error_per_mm", "curvature_per_mm"),
        ("derived_bending_energy", "derived_energy_error_n_mm", "energy_n_mm"),
    ]:
        check(code, maxima[field], {"combined_absolute": tolerances[quantity],
            "declared_reference_scale": scales.get(quantity), "normalization": "declared_history_maximum_or_L"},
            maxima[field] <= tolerances[quantity])
    check("finest_displacement", finest_error, {"combined_absolute": tolerances["finest_displacement_mm"],
        "declared_reference_scale": scales["displacement_mm"]}, finest_error <= tolerances["finest_displacement_mm"])
    roundoff_floor = max(normalized["limits"]["displacement_absolute_mm"],
                         64.0 * sys.float_info.epsilon * normalized["beam"]["length_mm"])
    mesh_pairs = []
    for i, coarse in enumerate(summaries):
        for fine in summaries[i + 1:]:
            coarse_error, fine_error = coarse["max_position_error_mm"], fine["max_position_error_mm"]
            h_coarse, h_fine = coarse["max_segment_length_mm"], fine["max_segment_length_mm"]
            pair = {"coarse_element_count": coarse["element_count"], "fine_element_count": fine["element_count"],
                    "coarse_max_segment_length_mm": h_coarse, "fine_max_segment_length_mm": h_fine,
                    "coarse_error_mm": coarse_error, "fine_error_mm": fine_error,
                    "roundoff_floor_mm": roundoff_floor, "rate": None}
            code = f"mesh_rate_{coarse['element_count']}_to_{fine['element_count']}"
            if h_coarse <= h_fine:
                pair.update(status="FAIL", reason="Requested mesh has not refined the maximum original segment length")
                check(code, None, normalized["limits"]["min_mesh_rate"], False)
            elif coarse_error <= roundoff_floor or fine_error <= roundoff_floor:
                pair.update(status="UNKNOWN", reason="Maximum position error is at zero/absolute/identity-roundoff floor")
                checks.append({"code": code, "status": "UNKNOWN", "observed": None,
                               "limit": normalized["limits"]["min_mesh_rate"], "reason": pair["reason"]})
            else:
                # Difference of logarithms avoids overflow in error/h ratios.
                rate = _number((math.log(coarse_error) - math.log(fine_error)) /
                               math.log1p((h_coarse - h_fine) / h_fine), "Measured mesh rate")
                pair.update(rate=rate, status="PASS" if rate >= normalized["limits"]["min_mesh_rate"] else "FAIL")
                check(code, rate, normalized["limits"]["min_mesh_rate"], pair["status"] == "PASS")
            mesh_pairs.append(pair)
    passed = all(item["status"] == "PASS" for item in checks)
    unresolved = ", ".join(f"{item['code']}={item['status']}" for item in checks if item["status"] != "PASS")

    def metric(value: float | None, unit: str) -> dict:
        return {"value": value, "unit": unit, "valid": passed,
                **({"reason": f"Declared beam numerical validation unresolved: {unresolved}"} if not passed else {})}

    finest_final = summaries[-1]["states"][-1]
    measured_rates = [pair["rate"] for pair in mesh_pairs if pair["rate"] is not None]
    minimum_rate = min(measured_rates) if len(measured_rates) == len(mesh_pairs) else None
    metrics = {"tip_x": metric(finest_final["tip_coordinates_mm"][0], "mm"),
        "tip_y": metric(finest_final["tip_coordinates_mm"][1], "mm"),
        "tip_rotation_z": metric(finest_final["tip_rotations_rad"][2], "rad"),
        "root_moment_z": metric(finest_final["root_reaction"][5], "N mm"),
        "derived_section_fiber_stress": metric(_sum((value / counts[-1] for value in
            finest_final["derived_section_fiber_stresses_mpa"]), "Mean fiber stress"), "MPa"),
        "derived_bending_energy": metric(finest_final["derived_bending_energy_n_mm"], "N mm"),
        "max_position_error": metric(maxima["max_position_error_mm"], "mm"),
        "finest_position_error": metric(finest_error, "mm"),
        "max_rotation_error": metric(maxima["max_rotation_error_rad"], "rad"),
        "max_force_error": metric(maxima["max_nodal_force_error_n"], "N"),
        "max_moment_error": metric(maxima["max_nodal_moment_error_n_mm"], "N mm"),
        "max_section_force_error": metric(maxima["max_section_force_error_n"], "N"),
        "max_section_moment_error": metric(maxima["max_section_moment_error_n_mm"], "N mm"),
        "max_curvature_error": metric(maxima["max_curvature_error_per_mm"], "1/mm"),
        "max_derived_energy_error": metric(maxima["derived_energy_error_n_mm"], "N mm"),
        "minimum_mesh_rate": metric(minimum_rate, "1")}
    return {"checks": checks, "metrics": metrics, "pending_validations": list(_PENDING),
        "reference": reference, "mesh_studies": summaries,
        "mesh_response": {"times_s": list(normalized["history"]["times_s"]), "pairs": mesh_pairs,
            "error_statistic": "maximum_euclidean_position_error_over_every_node_and_time",
            "mesh_size_statistic": "maximum_original_segment_length_mm", "pair_selection": "all_coarse_fine_pairs",
            "roundoff_floor_mm": roundoff_floor},
        "derived_energy": {"method": "0.5*sum(native_Mz*native_global_kappa_z*original_segment_length)",
            "reference": "M^2*L/(2*E*IZ)", "native_energy_field": False, "physical_energy_balance": False},
        "derived_stress": {"method": "native_Mz*h/(2*IZ)", "native_cauchy_stress": False,
                           "component": "signed_section_fiber_bending_stress"},
        "limitations": ["Planar pure end moment, finite rotation <=1 rad and derived fiber strain <=0.005 only.",
            "The circular reference is inextensible elastic bending; contact, reverse loading and wider nonlinear behavior are unqualified.",
            "Signed local section wrenches and updated global curvatures are distinct from nodal rotations and 3D stress.",
            "Native catalogue, archive identity and Newton convergence must be proved separately by the adapter.",
            "Derived bending energy/fiber stress are not native global energy, physical energy balance or Cauchy stress.",
            "Unmeasurable mesh rates remain UNKNOWN; numerical agreement cannot release an engineering design."]}
