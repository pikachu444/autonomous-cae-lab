"""Independent small-strain uniaxial J2 isotropic-hardening reference.

The origin-aligned block has symmetry restraints on x=0, y=0 and z=0 and
prescribed axial displacement on x=L. Free lateral faces permit the affine
Poisson/plastic contraction. The admitted history is monotonic tension into
plasticity followed by elastic unloading, possibly into negative stress, but
without reverse yielding. A separate selected-mesh mode admits declared signed
histories without evaluating this tensile reference. No native solver command
or constitutive integration routine is used here.
"""

from __future__ import annotations

import copy
import math
import sys


__version__ = "1"

_SETTING_KEYS = {"case", "dimensions_mm", "material", "history", "mesh_sizes_mm", "limits"}
_SELECTED_SETTING_KEYS = _SETTING_KEYS | {"mode", "input_provenance"}
_MATERIAL_KEYS = {"youngs_modulus_mpa", "poisson_ratio", "yield_stress_mpa", "plastic_modulus_mpa"}
_HISTORY_KEYS = {"times_s", "axial_strain"}
_LIMIT_KEYS = {"displacement_relative", "displacement_absolute_mm", "stress_relative",
               "stress_absolute_mpa", "plastic_strain_absolute", "reaction_relative",
               "reaction_absolute_n", "mesh_agreement_relative", "plastic_dissipation_relative",
               "plastic_dissipation_absolute_mpa"}
_RECORD_KEYS = {"mesh_size_mm", "node_ids", "coordinates_mm", "element_count", "states"}
_STATE_KEYS = {"time_s", "displacements_mm", "stresses_mpa", "eq_plastic_strain", "reaction_n"}
_COMPONENTS = ["xx", "yy", "zz", "xy", "xz", "yz"]
_PENDING = ["static_strength", "material_qualification", "model_qualification",
            "physical_validation", "fatigue_durability"]
_SELECTED_PENDING = ["reference_agreement", "mesh_convergence", *_PENDING]
SELECTED_SCOPE = "SELECTED_SMALL_STRAIN_J2_BLOCK_HISTORY"
SELECTED_LIMITATIONS = [
    "Selected homogeneous block, small-strain J2 isotropic linear hardening and declared axial displacement history only.",
    "Loading, plateaus, unloading and reversal are native observations; no analytical history agreement is evaluated.",
    "One selected mesh gives no mesh agreement or convergence evidence.",
    "Plastic work, hardening energy and dissipation references are not evaluated for general signed histories; no native global energy is inferred.",
    "Seconds label the declared quasi-static load history; inertia and rate-dependent material behavior are not modeled.",
    "Input sources are user declarations, not material, model, physical, strength or fatigue qualification.",
]
SELECTED_METRICS = ["final_stress", "reaction_x", "stress_xx_min", "stress_xx_max", "max_eq_plastic_strain"]
_UNASSESSED_METRIC_UNITS = {
    "peak_stress": "MPa", "peak_eq_plastic_strain": "1", "unload_residual_strain": "1",
    "plastic_work_density": "MPa", "hardening_energy_density": "MPa", "plastic_dissipation_density": "MPa",
    "max_component_displacement_error": "mm", "displacement_relative_error": "1",
    "max_component_stress_error": "MPa", "stress_relative_error": "1", "max_eq_plastic_strain_error": "1",
    "reaction_absolute_error": "N", "reaction_relative_error": "1", "max_unload_residual_strain_error": "1",
    "plastic_dissipation_absolute_error": "MPa", "mesh_agreement_relative": "1",
}


def _keys(value: object, expected: set[str], label: str) -> dict:
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError(f"{label} must contain exactly: {', '.join(sorted(expected))}")
    return value


def _number(value: object, label: str, *, positive: bool = False) -> float:
    if type(value) not in (int, float):
        raise ValueError(f"{label} must be a finite number")
    try:
        answer = float(value)
    except (ValueError, OverflowError) as error:
        raise ValueError(f"{label} must be a finite number") from error
    if not math.isfinite(answer) or (positive and answer <= 0.0):
        raise ValueError(f"{label} must be finite{' and positive' if positive else ''}")
    return answer


def _vector(value: object, length: int, label: str) -> list[float]:
    if not isinstance(value, list) or len(value) != length:
        raise ValueError(f"{label} must be a list of {length} finite components")
    return [_number(component, label) for component in value]


def _table(value: object, columns: int, label: str) -> list[list[float]]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{label} must be a nonempty finite table")
    return [_vector(row, columns, label) for row in value]


def _mean(values: list[float]) -> float:
    return _number(math.fsum(value / len(values) for value in values), "Observed arithmetic mean")


def _reference(settings: dict) -> dict:
    if settings.get("mode") == "selected_mesh":
        raise ValueError("No analytical reference is evaluated for selected_mesh signed histories")
    young = settings["material"]["youngs_modulus_mpa"]
    poisson = settings["material"]["poisson_ratio"]
    yield_stress = settings["material"]["yield_stress_mpa"]
    hardening = settings["material"]["plastic_modulus_mpa"]
    length, breadth, height = settings["dimensions_mm"]
    denominator = _number(young + hardening, "Analytical E+H", positive=True)
    area = _number(breadth * height, "Analytical cross-section area", positive=True)
    strains = settings["history"]["axial_strain"]
    peak_index = strains.index(max(strains))
    plastic = 0.0
    states = []
    for index, (time, strain) in enumerate(zip(settings["history"]["times_s"], strains)):
        trial = _number(young * strain, "Analytical elastic trial stress")
        if index <= peak_index:
            plastic = max(0.0, _number((trial - yield_stress) / denominator,
                                       "Analytical plastic strain"))
        stress = _number(young * (strain - plastic), "Analytical axial stress")
        current_yield = _number(yield_stress + hardening * plastic, "Analytical current yield stress")
        if index > peak_index and stress < -current_yield:
            raise ValueError("History causes reverse yielding; only elastic unloading is supported")
        lateral = _number(-poisson * stress / young - 0.5 * plastic, "Analytical lateral strain")
        gradient = [strain, lateral, lateral]
        for slope, span in zip(gradient, (length, breadth, height)):
            _number(slope * span, "Analytical displacement")
        stored = _number(0.5 * hardening * plastic * plastic, "Analytical hardening energy density")
        dissipated = _number(yield_stress * plastic, "Analytical plastic dissipation density")
        states.append({"time_s": time, "axial_strain": strain,
                       "stress_components_mpa": [stress, 0.0, 0.0, 0.0, 0.0, 0.0],
                       "eq_plastic_strain": plastic, "plastic_axial_strain": plastic,
                       "displacement_gradient": gradient,
                       "reaction_n": [_number(-stress * area, "Analytical signed reaction"), 0.0, 0.0],
                       "plastic_work_density_mpa": _number(stored + dissipated, "Analytical plastic work"),
                       "hardening_energy_density_mpa": stored,
                       "plastic_dissipation_density_mpa": dissipated})
    if states[peak_index]["eq_plastic_strain"] <= 0.0:
        raise ValueError("History must cause actual tensile yielding before elastic unloading")
    return {"case": settings["case"], "history": states, "peak_index": peak_index,
            "stress_component_order": list(_COMPONENTS),
            "units": {"time": "s", "strain": "1", "displacement": "mm", "stress": "MPa",
                      "reaction": "N", "energy_density": "MPa"}}


def _scales(settings: dict, reference: dict) -> dict:
    states = reference["history"]
    dimensions = settings["dimensions_mm"]
    return {"displacement_mm": _number(max(abs(slope * span) for state in states
                                           for slope, span in zip(state["displacement_gradient"], dimensions)),
                                        "Global displacement scale", positive=True),
            "axial_displacement_mm": _number(max(state["axial_strain"] for state in states) * dimensions[0],
                                              "Global axial displacement scale", positive=True),
            "stress_mpa": _number(max(abs(state["stress_components_mpa"][0]) for state in states),
                                  "Global stress scale", positive=True),
            "reaction_n": _number(max(abs(state["reaction_n"][0]) for state in states),
                                  "Global reaction scale", positive=True),
            "plastic_strain": _number(states[reference["peak_index"]]["eq_plastic_strain"],
                                      "Global plastic strain scale", positive=True),
            "plastic_dissipation_mpa": _number(max(state["plastic_dissipation_density_mpa"] for state in states),
                                              "Global plastic dissipation scale", positive=True)}


def _tolerances(settings: dict, scales: dict) -> dict:
    limits = settings["limits"]
    tolerances = {}
    for name, absolute, relative, scale in [
        ("displacement_mm", "displacement_absolute_mm", "displacement_relative", "displacement_mm"),
        ("stress_mpa", "stress_absolute_mpa", "stress_relative", "stress_mpa"),
        ("reaction_n", "reaction_absolute_n", "reaction_relative", "reaction_n"),
        ("plastic_dissipation_mpa", "plastic_dissipation_absolute_mpa", "plastic_dissipation_relative",
         "plastic_dissipation_mpa"),
    ]:
        tolerances[name] = _number(limits[absolute] + limits[relative] * scales[scale],
                                   f"Combined {name} tolerance", positive=True)
    tolerances["plastic_strain"] = limits["plastic_strain_absolute"]
    tolerances["residual_strain"] = _number(
        tolerances["displacement_mm"] / settings["dimensions_mm"][0] +
        tolerances["stress_mpa"] / settings["material"]["youngs_modulus_mpa"] +
        tolerances["plastic_strain"], "Combined residual strain tolerance", positive=True)
    return tolerances


def validate_settings(settings: dict) -> dict:
    """Return a deep independent normalized request before backend execution.

    H is d(yield stress)/d(equivalent plastic strain), not the uniaxial tangent
    d(stress)/d(total strain). Inputs and historical records are never changed.
    """
    selected = isinstance(settings, dict) and settings.get("mode") == "selected_mesh"
    _keys(settings, _SELECTED_SETTING_KEYS if selected else _SETTING_KEYS, "Plasticity settings")
    if selected:
        source = _keys(settings["input_provenance"], {"origin", "reference"}, "Input provenance")
        if (not isinstance(source["origin"], str) or
                source["origin"] not in {"ASSUMED", "MEASURED_REPORTED", "PUBLISHED_REFERENCE", "SYNTHETIC"} or
                not isinstance(source["reference"], str) or not source["reference"].strip() or
                len(source["reference"]) > 2000):
            raise ValueError("Input provenance needs a declared origin and a nonempty reference of at most 2000 characters")
    if settings["case"] != "uniaxial_j2_isotropic_hardening":
        raise ValueError("Plasticity case must be uniaxial_j2_isotropic_hardening")
    dimensions = _vector(settings["dimensions_mm"], 3, "dimensions_mm")
    if any(value <= 0.0 for value in dimensions):
        raise ValueError("dimensions_mm must be positive")
    material = _keys(settings["material"], _MATERIAL_KEYS, "Plasticity material")
    material = {name: _number(material[name], name, positive=name != "poisson_ratio")
                for name in sorted(_MATERIAL_KEYS)}
    if not -1.0 < material["poisson_ratio"] < 0.5:
        raise ValueError("poisson_ratio must satisfy -1 < nu < 0.5")
    history = _keys(settings["history"], _HISTORY_KEYS, "Plasticity history")
    times, strains = history["times_s"], history["axial_strain"]
    if (not isinstance(times, list) or not isinstance(strains, list) or
            not (2 if selected else 6) <= len(times) <= 32 or len(strains) != len(times)):
        raise ValueError(f"History requires {2 if selected else 6} to 32 corresponding time and strain entries")
    times = [_number(value, "times_s") for value in times]
    strains = [_number(value, "axial_strain") for value in strains]
    if (times[0] != 0.0 or strains[0] != 0.0 or
            any(previous >= current for previous, current in zip(times, times[1:]))):
        raise ValueError("History must start at time=0/strain=0 with strictly increasing times")
    if selected:
        if any(abs(value) > 0.01 for value in strains):
            raise ValueError("selected_mesh axial_strain must be in [-0.01,0.01]")
    else:
        if any(value < 0.0 or value > 0.01 for value in strains):
            raise ValueError("axial_strain must be nonnegative and <= 0.01")
        peak_index = strains.index(max(strains))
        if (peak_index < 1 or peak_index > len(strains) - 3 or
                any(previous >= current for previous, current in zip(strains[:peak_index], strains[1:peak_index + 1])) or
                any(previous <= current for previous, current in zip(strains[peak_index:-1], strains[peak_index + 1:]))):
            raise ValueError("History must strictly load to one peak then strictly unload for at least two steps")
    sizes = settings["mesh_sizes_mm"]
    if not isinstance(sizes, list) or not ((len(sizes) == 1) if selected else (2 <= len(sizes) <= 3)):
        raise ValueError("selected_mesh requires one mesh size" if selected else
                         "mesh_sizes_mm requires two or three descending distinct sizes")
    sizes = [_number(value, "mesh_sizes_mm", positive=True) for value in sizes]
    if (any(coarse <= fine for coarse, fine in zip(sizes, sizes[1:])) or
            any(value > min(dimensions) for value in sizes)):
        raise ValueError("mesh_sizes_mm must be descending, distinct and <= every block dimension")
    limits = _keys(settings["limits"], _LIMIT_KEYS, "Plasticity limits")
    normalized = copy.deepcopy(settings)
    normalized.update({"dimensions_mm": dimensions, "material": material,
                       "history": {"times_s": times, "axial_strain": strains}, "mesh_sizes_mm": sizes,
                       "limits": {name: _number(limits[name], name, positive=True) for name in sorted(_LIMIT_KEYS)}})
    if selected:
        # Check representability of the existing native material translation and
        # prescribed displacement, without a tensile/reverse-history oracle.
        young, hardening = material["youngs_modulus_mpa"], material["plastic_modulus_mpa"]
        total = _number(young + hardening, "Native E+H", positive=True)
        _number(young * (hardening / total), "Native total-strain tangent", positive=True)
        for strain in strains:
            _number(strain * dimensions[0], "Declared axial displacement")
    else:
        reference = _reference(normalized)
        _tolerances(normalized, _scales(normalized, reference))
    return normalized


def analytical_reference(settings: dict) -> dict:
    """Closed scalar tensile return map and elastic-unloading history."""
    return _reference(validate_settings(settings))


def selected_settings() -> dict:
    """Editable assumed inputs; no manufactured history/reference or sweep."""
    return validate_settings({
        "mode": "selected_mesh", "case": "uniaxial_j2_isotropic_hardening",
        "dimensions_mm": [20.0, 4.0, 2.0],
        "material": {"youngs_modulus_mpa": 210000.0, "poisson_ratio": 0.3,
                     "yield_stress_mpa": 250.0, "plastic_modulus_mpa": 1000.0},
        "history": {"times_s": [0.0, 1.0], "axial_strain": [0.0, 0.001]}, "mesh_sizes_mm": [2.0],
        "limits": {"displacement_relative": 1e-7, "displacement_absolute_mm": 1e-10,
                   "stress_relative": 1e-7, "stress_absolute_mpa": 1e-8, "plastic_strain_absolute": 1e-9,
                   "reaction_relative": 1e-7, "reaction_absolute_n": 1e-8, "mesh_agreement_relative": 1e-7,
                   "plastic_dissipation_relative": 1e-6, "plastic_dissipation_absolute_mpa": 1e-8},
        "input_provenance": {"origin": "ASSUMED", "reference":
            "User-editable hypothetical J2 material and axial displacement history; material/physical qualification UNKNOWN"},
    })


def model_declaration(settings: dict) -> dict:
    """Flat common declaration; native constitutive and history syntax stays in adapters."""
    normalized = validate_settings(settings)
    material = normalized["material"]
    times = normalized["history"]["times_s"]
    length = normalized["dimensions_mm"][0]
    declaration = {"case": normalized["case"],
            "geometry": {"type": "block", "dimensions_mm": list(normalized["dimensions_mm"]),
                         "unit": "mm", "origin": [0.0, 0.0, 0.0]},
            "materials": [{"model": "j2_isotropic_linear_hardening", "kinematics": "small_strain",
                           "youngs_modulus": {"value": material["youngs_modulus_mpa"], "unit": "MPa"},
                           "poisson_ratio": {"value": material["poisson_ratio"], "unit": "1"},
                           "yield_stress": {"value": material["yield_stress_mpa"], "unit": "MPa"},
                           "plastic_modulus": {"value": material["plastic_modulus_mpa"], "unit": "MPa",
                                               "meaning": "d_yield_stress_d_equivalent_plastic_strain"}}],
            "mesh": {"sizes_mm": list(normalized["mesh_sizes_mm"]), "order": 2, "element_type": "TETRA10"},
            "boundary_conditions": [{"type": "prescribed_displacement",
                                      "selection": {"type": "plane", "axis": axis, "coordinate_mm": 0.0},
                                      "component": axis, "value": 0.0, "unit": "mm"}
                                     for axis in ("x", "y", "z")],
            "loads": [{"type": "prescribed_displacement_history",
                       "selection": {"type": "plane", "axis": "x", "coordinate_mm": length},
                       "component": "x", "times_s": list(times),
                       "values_mm": [strain * length for strain in normalized["history"]["axial_strain"]],
                       "unit": "mm"}],
            "history": copy.deepcopy(normalized["history"]),
            "outputs": {"times_s": list(times),
                        "fields": [{"field": "displacement", "unit": "mm"},
                                   {"field": "stress", "unit": "MPa", "components": list(_COMPONENTS)},
                                   {"field": "eq_plastic_strain", "unit": "1"},
                                   {"field": "reactions", "unit": "N"}]}}
    if normalized.get("mode") == "selected_mesh":
        declaration.update(mode="selected_mesh", scope=SELECTED_SCOPE,
                           input_provenance=copy.deepcopy(normalized["input_provenance"]))
        declaration["mesh"]["mode"] = "selected_mesh"
        declaration["outputs"]["metrics"] = [*SELECTED_METRICS, *_UNASSESSED_METRIC_UNITS]
        declaration["outputs"]["metric_semantics"] = {
            "final_stress": "Final archived SIXX UNWEIGHTED arithmetic mean over every native Gauss point; MPa",
            "reaction_x": "Final signed X0.DX support reaction sum in global X; N",
            "stress_xx_min": "Minimum signed SIXX over every native Gauss point and archived instant; MPa",
            "stress_xx_max": "Maximum signed SIXX over every native Gauss point and archived instant; MPa",
            "max_eq_plastic_strain": "Maximum native VARI_ELGA.V1 over every Gauss point and archived instant; 1",
        }
    return declaration


def _validated_record(record: dict, size: float, settings: dict) -> dict:
    if not isinstance(record, dict) or not _RECORD_KEYS <= set(record):
        raise ValueError("Mesh observation is missing required plasticity data")
    if _number(record["mesh_size_mm"], "Observed mesh_size_mm", positive=True) != size:
        raise ValueError("Mesh observation order/sizes differ from the frozen request")
    identifiers = record["node_ids"]
    if (not isinstance(identifiers, list) or len(identifiers) < 4 or
            any(type(node) is not int or node <= 0 for node in identifiers) or
            len(set(identifiers)) != len(identifiers)):
        raise ValueError("Mesh node_ids must contain at least four unique positive integers")
    elements = record["element_count"]
    if type(elements) is not int or elements <= 0:
        raise ValueError("Mesh element_count must be a positive integer")
    coordinates = _table(record["coordinates_mm"], 3, "coordinates_mm")
    if len(coordinates) != len(identifiers):
        raise ValueError("Mesh coordinates must cover every node_id exactly once")
    tolerance = 64.0 * sys.float_info.epsilon * max(1.0, max(settings["dimensions_mm"]))
    for row in coordinates:
        if any(value < -tolerance or value > span + tolerance
               for value, span in zip(row, settings["dimensions_mm"])):
            raise ValueError("coordinates_mm lies outside the declared block")
    for axis, span in enumerate(settings["dimensions_mm"]):
        if (abs(min(row[axis] for row in coordinates)) > tolerance or
                abs(max(row[axis] for row in coordinates) - span) > tolerance):
            raise ValueError("Mesh coordinates must span all declared block boundary planes")
    right_nodes = [index for index, row in enumerate(coordinates)
                   if abs(row[0] - settings["dimensions_mm"][0]) <= tolerance]
    if len(right_nodes) < 3:
        raise ValueError("Mesh observations must contain at least three right face nodes")
    raw_states = record["states"]
    times = settings["history"]["times_s"]
    if not isinstance(raw_states, list) or len(raw_states) != len(times):
        raise ValueError("Mesh states must cover every requested time exactly once")
    states = []
    for raw, time in zip(raw_states, times):
        if not isinstance(raw, dict) or not _STATE_KEYS <= set(raw):
            raise ValueError("Mesh state is missing required plasticity data")
        if _number(raw["time_s"], "Observed time_s") != time:
            raise ValueError("Mesh state times/order differ from the frozen history")
        displacements = _table(raw["displacements_mm"], 3, "displacements_mm")
        stresses = _table(raw["stresses_mpa"], 6, "stresses_mpa")
        plastic = _vector(raw["eq_plastic_strain"], 5 * elements, "eq_plastic_strain")
        if len(displacements) != len(identifiers) or len(stresses) != 5 * elements:
            raise ValueError("Fields must cover every node and all five TETRA10 integration points per element")
        states.append({"time_s": time, "displacements_mm": displacements, "stresses_mpa": stresses,
                       "eq_plastic_strain": plastic, "reaction_n": _vector(raw["reaction_n"], 3, "reaction_n")})
    return {"mesh_size_mm": size, "node_ids": list(identifiers), "coordinates_mm": coordinates,
            "element_count": elements, "right_nodes": right_nodes, "states": states}


def _selected_assessment(settings: dict, mesh_records: list[dict]) -> dict:
    """Check complete tables and declared BCs, without a constitutive oracle.

    Native order/node/Gauss joins and full nodal reactions are proved by the
    adapter's existing parser. This pure assessment keeps every signed native
    response and checks only the imposed displacement and cumulative V1 rules.
    """
    record = _validated_record(mesh_records[0], settings["mesh_sizes_mm"][0], settings)
    coordinates, dimensions = record["coordinates_mm"], settings["dimensions_mm"]
    coordinate_tolerance = 64.0 * sys.float_info.epsilon * max(1.0, *dimensions)
    fixed = [[index for index, row in enumerate(coordinates) if abs(row[axis]) <= coordinate_tolerance]
             for axis in range(3)]
    if any(len(nodes) < 3 for nodes in fixed):
        raise ValueError("Selected observations must cover all three support planes")
    prescribed = [_number(strain * dimensions[0], "Declared axial displacement")
                  for strain in settings["history"]["axial_strain"]]
    scale = max(abs(value) for value in prescribed)
    boundary_limit = _number(settings["limits"]["displacement_absolute_mm"] +
                             settings["limits"]["displacement_relative"] * scale,
                             "Declared displacement tolerance", positive=True)
    boundary_error = 0.0
    drop = 0.0
    previous_q = None
    summaries = []
    all_stress, all_q = [], []
    for state, strain, drive in zip(record["states"], settings["history"]["axial_strain"], prescribed):
        displacements, stress, q = state["displacements_mm"], state["stresses_mpa"], state["eq_plastic_strain"]
        error = max(abs(displacements[node][0] - drive) for node in record["right_nodes"])
        error = max(error, *(abs(displacements[node][axis]) for axis, nodes in enumerate(fixed) for node in nodes))
        boundary_error = max(boundary_error, _number(error, "Native prescribed-displacement error"))
        if previous_q is not None:
            drop = max(drop, *(_number(a - b, "Native cumulative V1 decrease") for a, b in zip(previous_q, q)))
        previous_q = q
        stress_x = [row[0] for row in stress]
        all_stress.extend(stress_x)
        all_q.extend(q)
        summaries.append({"time_s": state["time_s"], "axial_strain": strain,
                          "right_face_axial_displacement_mm": _mean([displacements[node][0] for node in record["right_nodes"]]),
                          "mean_stress_xx_mpa": _mean(stress_x), "mean_eq_plastic_strain": _mean(q),
                          "min_eq_plastic_strain": min(q), "reaction_n": list(state["reaction_n"]),
                          "prescribed_displacement_error_mm": error})
    checks = [
        {"code": "selected_field_coverage", "status": "PASS",
         "observed": {"states": len(record["states"]), "nodes_per_state": len(record["node_ids"]),
                      "gauss_points_per_state": 5 * record["element_count"]},
         "limit": "Every requested instant, every node DX/DY/DZ, every TETRA10 point SIXX/SIYY/SIZZ/SIXY/SIXZ/SIYZ/V1; native identities checked by adapter"},
        {"code": "selected_prescribed_displacement", "status": "PASS" if boundary_error <= boundary_limit else "FAIL",
         "observed": boundary_error, "limit": {"absolute_mm": settings["limits"]["displacement_absolute_mm"],
             "relative": settings["limits"]["displacement_relative"], "declared_drive_scale_mm": scale,
             "combined_absolute_mm": boundary_limit}},
        {"code": "plastic_strain_nonnegative", "status": "PASS" if min(all_q) >= 0.0 else "FAIL",
         "observed": min(all_q), "limit": {"minimum": 0.0}},
        {"code": "plastic_strain_monotonic", "status": "PASS" if drop <= settings["limits"]["plastic_strain_absolute"] else "FAIL",
         "observed": drop, "limit": settings["limits"]["plastic_strain_absolute"]},
    ]
    passed = all(check["status"] == "PASS" for check in checks)
    failures = ", ".join(check["code"] for check in checks if check["status"] == "FAIL")

    def metric(value: float, unit: str) -> dict:
        return {"value": value, "unit": unit, "valid": passed,
                **({"reason": "Selected J2 numerical validation failed: " + failures} if not passed else {})}

    metrics = {"final_stress": metric(summaries[-1]["mean_stress_xx_mpa"], "MPa"),
               "reaction_x": metric(record["states"][-1]["reaction_n"][0], "N"),
               "stress_xx_min": metric(min(all_stress), "MPa"),
               "stress_xx_max": metric(max(all_stress), "MPa"),
               "max_eq_plastic_strain": metric(max(all_q), "1")}
    metrics.update({name: {"value": None, "unit": unit, "valid": False,
                          "reason": "Not evaluated: selected_mesh has no tensile reference, input-peak benchmark statistic, mesh comparison or signed-history energy reference"}
                    for name, unit in _UNASSESSED_METRIC_UNITS.items()})
    return {"mode": "selected_mesh", "scope": SELECTED_SCOPE,
            "input_provenance": copy.deepcopy(settings["input_provenance"]),
            "checks": checks, "metrics": metrics, "pending_validations": list(_SELECTED_PENDING),
            "reference": {"status": "UNKNOWN", "history": None, "peak_index": None, "source": None,
                          "units": {"time": "s", "strain": "1", "displacement": "mm", "stress": "MPa", "reaction": "N"}},
            "mesh_studies": [{"mesh_size_mm": record["mesh_size_mm"], "node_count": len(record["node_ids"]),
                              "element_count": record["element_count"], "stress_point_count": 5 * record["element_count"],
                              "right_face_node_count": len(record["right_nodes"]), "states": summaries}],
            "mesh_response": {"fields": ["right_face_axial_displacement_mm", "mean_stress_xx_mpa", "mean_eq_plastic_strain", "reaction_x_n"],
                              "times_s": list(settings["history"]["times_s"]), "agreement_by_field": None,
                              "statistic": "UNWEIGHTED arithmetic mean of native right-face DX or native Gauss field; signed X0.DX support reaction sum",
                              "normalization": None, "agreement_statistic": None},
            "derived_energy": {"status": "UNKNOWN", "method": None, "native_energy_field": False,
                               "physical_energy_balance": False, "reason": "No derived plastic-energy reference evaluated for general signed histories"},
            "limitations": list(SELECTED_LIMITATIONS)}


def assess(settings: dict, mesh_records: list[dict]) -> dict:
    """Compare every finite point, component and requested time to the reference.

    The adapter must prove actual integration-point identity and stable row
    ordering across time. Derived plastic work is a trapezoidal integral of
    native sigma_xx dq. At first plastic entry its lower endpoint is the
    declared yield stress, rather than a preceding elastic sample below yield;
    subsequent increments use the preceding native stress. Subtracting Hq²/2
    gives a derived dissipation check, not a native energy-field observation or
    a whole-model physical energy balance. Negative finite q/work/dissipation
    are retained and cause numerical FAIL, rather than malformed-output errors.
    """
    normalized = validate_settings(settings)
    if not isinstance(mesh_records, list) or len(mesh_records) != len(normalized["mesh_sizes_mm"]):
        raise ValueError("A complete observation is required for every requested mesh")
    if normalized.get("mode") == "selected_mesh":
        return _selected_assessment(normalized, mesh_records)
    reference = _reference(normalized)
    scales = _scales(normalized, reference)
    tolerances = _tolerances(normalized, scales)
    peak_index = reference["peak_index"]
    length = normalized["dimensions_mm"][0]
    material = normalized["material"]
    young, hardening = material["youngs_modulus_mpa"], material["plastic_modulus_mpa"]
    summaries = []
    for raw, size in zip(mesh_records, normalized["mesh_sizes_mm"]):
        record = _validated_record(raw, size, normalized)
        point_count = 5 * record["element_count"]
        work = [0.0] * point_count
        previous_q = [0.0] * point_count
        previous_stress = [0.0] * point_count
        entered_plastic = [False] * point_count
        states = []
        max_drop = max_unload_q_change = max_residual_error = 0.0
        peak_q = record["states"][peak_index]["eq_plastic_strain"]
        for index, (state, exact) in enumerate(zip(record["states"], reference["history"])):
            displacement_error = _number(max(abs(observed - slope * coordinate)
                                            for row, coords in zip(state["displacements_mm"], record["coordinates_mm"])
                                            for observed, slope, coordinate in zip(row, exact["displacement_gradient"], coords)),
                                        "Displacement error")
            stress_error = _number(max(abs(observed - expected) for row in state["stresses_mpa"]
                                      for observed, expected in zip(row, exact["stress_components_mpa"])), "Stress error")
            q_error = max(abs(value - exact["eq_plastic_strain"]) for value in state["eq_plastic_strain"])
            reaction_error = _number(max(abs(observed - expected) for observed, expected in
                                        zip(state["reaction_n"], exact["reaction_n"])), "Reaction error")
            right_dx = _mean([state["displacements_mm"][node][0] for node in record["right_nodes"]])
            stress_x = [row[0] for row in state["stresses_mpa"]]
            mean_stress = _mean(stress_x)
            residual = _number(right_dx / length - mean_stress / young, "Observed residual strain")
            q = state["eq_plastic_strain"]
            for point, (plastic, stress) in enumerate(zip(q, stress_x)):
                increment = plastic - previous_q[point]
                max_drop = max(max_drop, -increment)
                if increment != 0.0:
                    first_entry = increment > 0.0 and not entered_plastic[point]
                    lower_stress = material["yield_stress_mpa"] if first_entry else previous_stress[point]
                    work[point] = _number(work[point] + 0.5 * (lower_stress + stress) * increment,
                                          "Derived plastic work density")
                    entered_plastic[point] = entered_plastic[point] or increment > 0.0
                previous_q[point], previous_stress[point] = plastic, stress
            stored = [_number(0.5 * hardening * value * value, "Derived hardening energy density") for value in q]
            dissipation = [_number(value - energy, "Derived plastic dissipation density")
                           for value, energy in zip(work, stored)]
            dissipation_error = max(abs(value - exact["plastic_dissipation_density_mpa"]) for value in dissipation)
            residual_error = 0.0
            if index > peak_index:
                max_unload_q_change = max(max_unload_q_change, max(abs(value - peak) for value, peak in zip(q, peak_q)))
                residual_error = abs(residual - reference["history"][peak_index]["plastic_axial_strain"])
                max_residual_error = max(max_residual_error, residual_error)
            states.append({"time_s": state["time_s"], "axial_strain": exact["axial_strain"],
                           "max_component_displacement_error_mm": displacement_error,
                           "max_component_stress_error_mpa": stress_error, "max_eq_plastic_strain_error": q_error,
                           "reaction_absolute_error_n": reaction_error, "reaction_n": list(state["reaction_n"]),
                           "right_face_axial_displacement_mm": right_dx, "mean_stress_xx_mpa": mean_stress,
                           "mean_eq_plastic_strain": _mean(q), "min_eq_plastic_strain": min(q),
                           "unload_residual_strain": residual, "unload_residual_strain_error": residual_error,
                           "plastic_work_density_mpa": list(work), "hardening_energy_density_mpa": stored,
                           "plastic_dissipation_density_mpa": dissipation,
                           "plastic_dissipation_absolute_error_mpa": dissipation_error})
        summaries.append({"mesh_size_mm": size, "node_count": len(record["node_ids"]),
                          "element_count": record["element_count"], "stress_point_count": point_count,
                          "right_face_node_count": len(record["right_nodes"]), "states": states,
                          "max_plastic_strain_decrease": max_drop,
                          "max_unload_plastic_strain_change": max_unload_q_change,
                          "max_unload_residual_strain_error": max_residual_error})
    states = [state for summary in summaries for state in summary["states"]]
    maxima = {"displacement_mm": max(state["max_component_displacement_error_mm"] for state in states),
              "stress_mpa": max(state["max_component_stress_error_mpa"] for state in states),
              "plastic_strain": max(state["max_eq_plastic_strain_error"] for state in states),
              "reaction_n": max(state["reaction_absolute_error_n"] for state in states),
              "plastic_dissipation_mpa": max(state["plastic_dissipation_absolute_error_mpa"] for state in states)}
    agreement_by_field = {}
    for field, scale in [("right_face_axial_displacement_mm", "axial_displacement_mm"),
                         ("mean_stress_xx_mpa", "stress_mpa"), ("mean_eq_plastic_strain", "plastic_strain"),
                         ("reaction_x_n", "reaction_n")]:
        difference = 0.0
        for index in range(len(reference["history"])):
            values = [summary["states"][index]["reaction_n"][0] if field == "reaction_x_n"
                      else summary["states"][index][field] for summary in summaries]
            difference = max(difference, max(values) - min(values))
        agreement_by_field[field] = _number(difference / scales[scale], "Mesh agreement")
    agreement = max(agreement_by_field.values())
    checks = []

    def check(code: str, observed: float, limit: object, passed: bool) -> None:
        checks.append({"code": code, "status": "PASS" if passed else "FAIL", "observed": observed, "limit": limit})

    for code, quantity, absolute, relative in [
        ("analytical_displacement", "displacement_mm", "displacement_absolute_mm", "displacement_relative"),
        ("analytical_stress", "stress_mpa", "stress_absolute_mpa", "stress_relative"),
        ("signed_reaction_balance", "reaction_n", "reaction_absolute_n", "reaction_relative"),
        ("plastic_dissipation", "plastic_dissipation_mpa", "plastic_dissipation_absolute_mpa", "plastic_dissipation_relative"),
    ]:
        check(code, maxima[quantity], {"absolute": normalized["limits"][absolute],
                                      "relative": normalized["limits"][relative],
                                      "global_reference_scale": scales[quantity], "combined_absolute": tolerances[quantity]},
              maxima[quantity] <= tolerances[quantity])
    check("analytical_eq_plastic_strain", maxima["plastic_strain"], tolerances["plastic_strain"],
          maxima["plastic_strain"] <= tolerances["plastic_strain"])
    minimum_q = min(state["min_eq_plastic_strain"] for state in states)
    check("plastic_strain_nonnegative", minimum_q, {"minimum": 0.0}, minimum_q >= 0.0)
    drop = max(summary["max_plastic_strain_decrease"] for summary in summaries)
    check("plastic_strain_monotonic", drop, tolerances["plastic_strain"], drop <= tolerances["plastic_strain"])
    change = max(summary["max_unload_plastic_strain_change"] for summary in summaries)
    check("elastic_unloading_plastic_strain", change, tolerances["plastic_strain"], change <= tolerances["plastic_strain"])
    residual_error = max(summary["max_unload_residual_strain_error"] for summary in summaries)
    check("unload_residual_strain", residual_error, tolerances["residual_strain"], residual_error <= tolerances["residual_strain"])
    minimum_work = min(value for state in states for value in state["plastic_work_density_mpa"])
    minimum_dissipation = min(value for state in states for value in state["plastic_dissipation_density_mpa"])
    check("plastic_work_nonnegative", minimum_work, {"minimum": 0.0}, minimum_work >= 0.0)
    check("plastic_dissipation_nonnegative", minimum_dissipation, {"minimum": 0.0}, minimum_dissipation >= 0.0)
    check("mesh_agreement", agreement, normalized["limits"]["mesh_agreement_relative"],
          agreement <= normalized["limits"]["mesh_agreement_relative"])
    passed = all(item["status"] == "PASS" for item in checks)
    failures = ", ".join(item["code"] for item in checks if item["status"] == "FAIL")

    def metric(value: float, unit: str) -> dict:
        return {"value": value, "unit": unit, "valid": passed,
                **({"reason": f"Declared plasticity numerical validation failed: {failures}"} if not passed else {})}

    finest_peak = summaries[-1]["states"][peak_index]
    finest_final = summaries[-1]["states"][-1]
    metrics = {"peak_stress": metric(finest_peak["mean_stress_xx_mpa"], "MPa"),
               "final_stress": metric(finest_final["mean_stress_xx_mpa"], "MPa"),
               "peak_eq_plastic_strain": metric(finest_peak["mean_eq_plastic_strain"], "1"),
               "unload_residual_strain": metric(finest_final["unload_residual_strain"], "1"),
               "plastic_work_density": metric(_mean(finest_final["plastic_work_density_mpa"]), "MPa"),
               "hardening_energy_density": metric(_mean(finest_final["hardening_energy_density_mpa"]), "MPa"),
               "plastic_dissipation_density": metric(_mean(finest_final["plastic_dissipation_density_mpa"]), "MPa"),
               "max_component_displacement_error": metric(maxima["displacement_mm"], "mm"),
               "displacement_relative_error": metric(maxima["displacement_mm"] / scales["displacement_mm"], "1"),
               "max_component_stress_error": metric(maxima["stress_mpa"], "MPa"),
               "stress_relative_error": metric(maxima["stress_mpa"] / scales["stress_mpa"], "1"),
               "max_eq_plastic_strain_error": metric(maxima["plastic_strain"], "1"),
               "reaction_x": metric(finest_final["reaction_n"][0], "N"),
               "reaction_absolute_error": metric(maxima["reaction_n"], "N"),
               "reaction_relative_error": metric(maxima["reaction_n"] / scales["reaction_n"], "1"),
               "max_unload_residual_strain_error": metric(residual_error, "1"),
               "plastic_dissipation_absolute_error": metric(maxima["plastic_dissipation_mpa"], "MPa"),
               "mesh_agreement_relative": metric(agreement, "1")}
    return {"checks": checks, "metrics": metrics, "pending_validations": list(_PENDING),
            "reference": reference, "mesh_studies": summaries,
            "mesh_response": {"fields": list(agreement_by_field), "agreement_by_field": agreement_by_field,
                              "times_s": list(normalized["history"]["times_s"]),
                              "statistic": "arithmetic_mean_of_right_face_DX_or_integration_point_field",
                              "normalization": "global_peak_reference_scale_per_field",
                              "agreement_statistic": "max_minus_min_across_all_meshes_at_every_time"},
            "derived_energy": {"method": "trapezoidal_native_stress_xx_d_eq_plastic_strain",
                               "first_plastic_entry_lower_stress_mpa": material["yield_stress_mpa"],
                               "subsequent_lower_stress": "previous_native_stress_xx",
                               "stored_hardening": "0.5 * H * native_q^2",
                               "dissipation": "derived_plastic_work - stored_hardening",
                               "native_energy_field": False, "physical_energy_balance": False},
            "limitations": ["Small-strain J2 isotropic linear hardening; monotonic tension and elastic unloading only.",
                            "Affine constant-strain patch test; no mesh convergence order is inferred.",
                            "Derived stress-plastic-strain work is not a native energy field or physical energy balance.",
                            "Numerical agreement does not qualify strength, material, model, physical or fatigue requirements."]}
