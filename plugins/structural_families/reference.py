"""Fixed reference semantics for three declared linear structural families.

This module does not generate native meshes, run solvers, or extrapolate stress
to surfaces. Adapters prove their catalogue/topology, native extraction and
source identity. Here finite, complete observations receive numerical verdicts;
published comparisons and engineering qualification remain distinct.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
from pathlib import Path, PurePosixPath


_DEFINITION_PATH = Path(__file__).resolve().parents[2] / "benchmarks/specifications/structural-families-v1.json"
# Canonical JSON, not platform-specific line endings. Adapters additionally pin
# actual source bytes before/after execution. A new definition needs admission.
_DEFINITION_SHA256 = "3f198843b47b6f93c8ad81e4dfc86ce75c547ced983492f01d2210d386459038"
_SETTING_KEYS = {"case", "load_case", "load_factor", "mesh_cells"}
_RECORD_KEYS = {"cells", "node_ids", "coordinates_mm", "displacements_mm", "reaction_n",
                "reaction_moment_n_mm", "applied_force_n", "applied_moment_n_mm", "stress_points",
                "element_count", "field_completeness", "native_fields_artifact"}
_POINT_KEYS = {"element_id", "point_id", "coordinates_mm", "components_mpa"}
_COMPLETENESS_KEYS = {"displacement", "stress", "reaction", "native_mesh"}
_COMPONENTS = ["xx", "yy", "zz", "xy", "xz", "yz"]
_AXES = ["x", "y", "z"]
_FLOOR = 1e-12


def _pairs(pairs: list[tuple]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Structural definition has duplicate JSON keys")
        result[key] = value
    return result


def _definitions() -> dict:
    try:
        raw = _DEFINITION_PATH.read_text(encoding="utf-8")
        definition = json.loads(raw, object_pairs_hook=_pairs,
                                parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Nonfinite definition")))
        canonical = json.dumps(definition, sort_keys=True, separators=(",", ":"),
                               ensure_ascii=True, allow_nan=False).encode("utf-8")
    except (OSError, UnicodeError, ValueError, TypeError) as exc:
        raise ValueError("Frozen structural-family definition is unreadable") from exc
    if hashlib.sha256(canonical).hexdigest() != _DEFINITION_SHA256:
        raise ValueError("Frozen structural-family definition source changed")
    return definition


def _number(value: object, label: str, *, positive: bool = False) -> float:
    if type(value) not in (int, float):
        raise ValueError(f"{label} must be a finite number")
    try:
        result = float(value)
    except (ValueError, OverflowError) as exc:
        raise ValueError(f"{label} must be finite") from exc
    if not math.isfinite(result) or (positive and result <= 0):
        raise ValueError(f"{label} must be finite{' and positive' if positive else ''}")
    return result


def _vector(value: object, size: int, label: str) -> list[float]:
    if not isinstance(value, list) or len(value) != size:
        raise ValueError(f"{label} must contain {size} finite components")
    return [_number(x, label) for x in value]


def _cells(value: object, definition: dict) -> list[int]:
    limits = definition["execution_limits"]
    if (not isinstance(value, list) or len(value) != 3 or
            any(type(x) is not int or not 1 <= x <= limits["max_axis_cells"] for x in value)):
        raise ValueError("mesh_cells requires three bounded positive integer counts")
    nx, ny, nz = value
    nodes = ((nx + 1) * (ny + 1) * (nz + 1) + nx * (ny + 1) * (nz + 1) +
             (nx + 1) * ny * (nz + 1) + (nx + 1) * (ny + 1) * nz)
    if math.prod(value) > limits["max_elements_per_level"] or nodes > limits["max_nodes_per_level"]:
        raise ValueError("mesh_cells exceeds the frozen workload limits")
    return list(value)


def _case(case: object, definition: dict) -> dict:
    if type(case) is not str or case not in definition["cases"]:
        raise ValueError("Unsupported structural-family case")
    return definition["cases"][case]


def case_definition(case: str) -> dict:
    """An independent copy of the original frozen case, including source gaps."""
    return copy.deepcopy(_case(case, _definitions()))


def specification(case: str, load_case: str | None = None, load_factor: float = 1.0) -> dict:
    """Canonical four-key settings; defaults select the first declared load."""
    source = _case(case, _definitions())
    request = {"case": case, "load_case": next(iter(source["load_cases"])) if load_case is None else load_case,
               "load_factor": load_factor, "mesh_cells": copy.deepcopy(source["mesh_cells"])}
    return validate_settings(request)


def validate_settings(settings: dict) -> dict:
    """Reject unsupported input and freeze a bounded independent request."""
    if not isinstance(settings, dict) or set(settings) != _SETTING_KEYS:
        raise ValueError("Structural settings require exactly case, load_case, load_factor, mesh_cells")
    definition = _definitions()
    case = _case(settings["case"], definition)
    load_case = settings["load_case"]
    if type(load_case) is not str or load_case not in case["load_cases"]:
        raise ValueError("load_case is not supported for the declared structural case")
    factor = _number(settings["load_factor"], "load_factor", positive=True)
    if factor > definition["execution_limits"]["max_load_factor"]:
        raise ValueError("load_factor exceeds the frozen maximum")
    levels = settings["mesh_cells"]
    if not isinstance(levels, list) or not 2 <= len(levels) <= definition["execution_limits"]["max_mesh_levels"]:
        raise ValueError("mesh_cells requires two or three refinement levels")
    levels = [_cells(value, definition) for value in levels]
    if any(any(a > b for a, b in zip(left, right)) or left == right
           for left, right in zip(levels, levels[1:])):
        raise ValueError("Successive grids must be componentwise nondecreasing and refine at least one axis")
    result = {"case": settings["case"], "load_case": load_case, "load_factor": factor, "mesh_cells": levels}
    _reference(result, definition)
    return result


def _physics(settings: dict, definition: dict) -> tuple[dict, dict, dict]:
    case = definition["cases"][settings["case"]]
    units, geometry = definition["unit_conversion"], case["geometry"]
    material = case["material"]
    load = copy.deepcopy(case["load_cases"][settings["load_case"]])
    factor = settings["load_factor"]
    if case["family"] == "cantilever_force":
        geometry = {"type": "block", "origin_mm": list(geometry["origin_mm"]),
                    "dimensions_mm": [x * units["in_to_mm"] for x in geometry["dimensions_in"]]}
        young = material["youngs_modulus_psi"] * units["psi_to_mpa"]
        load["force_n"] = load.pop("force_lbf") * units["lbf_to_n"] * factor
        load.pop("reference_absolute_displacement_in")
    elif case["family"] == "pressurized_cylinder":
        geometry = copy.deepcopy(geometry)
        young = material["youngs_modulus_mpa"]
        load["pressure_mpa"] *= factor
        load["outer_pressure_mpa"] *= factor
    else:
        ft = units["ft_to_mm"]
        radius, thickness = geometry["midsurface_radius_ft"] * ft, geometry["thickness_ft"] * ft
        geometry = {"type": geometry["type"], "longitudinal_half_length_mm": geometry["longitudinal_half_length_ft"] * ft,
                    "midsurface_radius_mm": radius, "thickness_mm": thickness,
                    "inner_radius_mm": radius - thickness / 2, "outer_radius_mm": radius + thickness / 2,
                    "angle_degrees": list(geometry["angle_degrees"]), "mapping": geometry["mapping"]}
        young = material["youngs_modulus_lbf_per_ft2"] * units["lbf_to_n"] / ft**2
        load["weight_density_n_per_mm3"] = load.pop("weight_density_lbf_per_ft3") * units["lbf_to_n"] / ft**3 * factor
    return geometry, {"youngs_modulus_mpa": young, "poisson_ratio": material["poisson_ratio"]}, load


def _cross(left: list[float], right: list[float]) -> list[float]:
    return [left[1] * right[2] - left[2] * right[1], left[2] * right[0] - left[0] * right[2],
            left[0] * right[1] - left[1] * right[0]]


def _cylinder_at(coordinates: list[float], geometry: dict, material: dict, load: dict) -> tuple[list, list]:
    x, y, _ = coordinates
    r = math.hypot(x, y)
    if r <= 0:
        raise ValueError("Cylinder observation has zero radius")
    ri, ro = geometry["inner_radius_mm"], geometry["outer_radius_mm"]
    pressure, outer = load["pressure_mpa"], load["outer_pressure_mpa"]
    a = (pressure * ri**2 - outer * ro**2) / (ro**2 - ri**2)
    b = (pressure - outer) * ri**2 * ro**2 / (ro**2 - ri**2)
    young, nu = material["youngs_modulus_mpa"], material["poisson_ratio"]
    ur = (1 + nu) / young * ((1 - 2 * nu) * a * r + b / r)
    sr, st = a - b / r**2, a + b / r**2
    c, s = x / r, y / r
    return ([ur * c, ur * s, 0.0], [sr * c*c + st * s*s, sr * s*s + st * c*c,
                                  2 * nu * a, (sr - st) * c * s, 0.0, 0.0])


def _reference(settings: dict, definition: dict) -> dict:
    case = definition["cases"][settings["case"]]
    geometry, material, load = _physics(settings, definition)
    factor, units = settings["load_factor"], definition["unit_conversion"]
    secondary, inner_hoop = None, None
    if case["family"] == "cantilever_force":
        primary = case["load_cases"][settings["load_case"]]["reference_absolute_displacement_in"] * units["in_to_mm"] * factor
        force = [load["force_n"] if axis == load["component"] else 0.0 for axis in _AXES]
        length, width, height = geometry["dimensions_mm"]
        moment = _cross([length, width / 2, height / 2], force)
    elif case["family"] == "pressurized_cylinder":
        ri, ro, height = geometry["inner_radius_mm"], geometry["outer_radius_mm"], geometry["height_mm"]
        displacement, stress = _cylinder_at([ri, 0.0, 0.0], geometry, material, load)
        primary, inner_hoop = displacement[0], stress[1]
        secondary = _cylinder_at([ro, 0.0, 0.0], geometry, material, load)[0][0]
        resultant = height * (load["pressure_mpa"] * ri - load["outer_pressure_mpa"] * ro)
        force = [resultant, resultant, 0.0]
        moment = [-height * resultant / 2, height * resultant / 2, 0.0]
    else:
        primary = case["reference"]["signed_displacement_ft"] * units["ft_to_mm"] * factor
        ri, ro = geometry["inner_radius_mm"], geometry["outer_radius_mm"]
        length = geometry["longitudinal_half_length_mm"]
        angle = math.radians(geometry["angle_degrees"][1])
        area = (ro**2 - ri**2) / 2 * angle
        volume = area * length
        force = [0.0, 0.0, -load["weight_density_n_per_mm3"] * volume]
        centroid_y = (ro**3 - ri**3) / 3 * (1 - math.cos(angle)) / area
        centroid_z = (ro**3 - ri**3) / 3 * math.sin(angle) / area
        moment = _cross([length / 2, centroid_y, centroid_z], force)
    primary = _number(primary, "Primary reference")
    if primary == 0:
        raise ValueError("Primary reference is unrepresentable or zero")
    if secondary is not None:
        secondary = _number(secondary, "Outer radial reference", positive=True)
        inner_hoop = _number(inner_hoop, "Inner hoop reference", positive=True)
    force, moment = _vector(force, 3, "Analytic force"), _vector(moment, 3, "Analytic moment")
    _number(math.hypot(*force), "Analytic force norm", positive=True)
    return {"case": settings["case"], "load_case": settings["load_case"], "load_factor": factor,
            "definition_id": definition["definition_id"], "definition_sha256": _DEFINITION_SHA256,
            "primary_response_mm": primary, "secondary_response_mm": secondary,
            "inner_surface_hoop_stress_mpa": inner_hoop, "applied_force_n": force,
            "applied_moment_n_mm": moment, "material": material, "response": copy.deepcopy(case["response"]),
            "source_kind": case["source_kind"], "source_url": case["source_url"],
            "midas_replication": case["midas_replication"],
            "vendor_reference_conflict": copy.deepcopy(case.get("vendor_reference_conflict")),
            "published_reference": copy.deepcopy(case.get("reference")),
            "units": {"response": "mm", "stress": "MPa", "force": "N", "moment": "N mm"}}


def model_declaration(settings: dict) -> dict:
    """The existing common describe_model envelope, with no backend commands."""
    normalized = validate_settings(settings)
    definition = _definitions()
    case = definition["cases"][normalized["case"]]
    geometry, material, load = _physics(normalized, definition)
    return {"case": normalized["case"], "definition_id": definition["definition_id"],
            "definition_sha256": _DEFINITION_SHA256,
            "model": {"geometry": geometry, "materials": [{"model": "isotropic_linear_elastic",
                        "youngs_modulus": {"value": material["youngs_modulus_mpa"], "unit": "MPa"},
                        "poisson_ratio": {"value": material["poisson_ratio"], "unit": "1"}}],
                      "mesh": {"cells": copy.deepcopy(normalized["mesh_cells"]), "element_type": "HEXA20",
                               "order": 2, "cell_axis_order": ([_AXES[0], _AXES[1], _AXES[2]] if case["family"] == "cantilever_force"
                                   else ["radial", "angular", "axial"] if case["family"] == "pressurized_cylinder"
                                   else ["longitudinal", "angular", "radial"]) }},
            "boundary_conditions": copy.deepcopy(case["boundary_conditions"]), "loads": [load],
            "outputs": {"fields": [{"field": "displacement", "unit": "mm", "components": list(_AXES)},
                                     {"field": "stress", "unit": "MPa", "components": list(_COMPONENTS),
                                      "location": "native_integration_points"},
                                     {"field": "reactions", "unit": "N"}],
                        "response": copy.deepcopy(case["response"])},
            "reference": _reference(normalized, definition), "limitations": copy.deepcopy(case["limitations"])}


def _inside(coordinates: list[float], geometry: dict, tolerance: float) -> None:
    x, y, z = coordinates
    if geometry["type"] == "block":
        valid = all(-tolerance <= a <= b + tolerance for a, b in zip(coordinates, geometry["dimensions_mm"]))
    elif geometry["type"] == "quarter_annulus_extrusion":
        r = math.hypot(x, y)
        valid = (x >= -tolerance and y >= -tolerance and -tolerance <= z <= geometry["height_mm"] + tolerance and
                 geometry["inner_radius_mm"] - tolerance <= r <= geometry["outer_radius_mm"] + tolerance)
    else:
        r = math.hypot(y, z)
        angle = math.atan2(y, z)
        angle_tolerance = tolerance / geometry["inner_radius_mm"]
        valid = (-tolerance <= x <= geometry["longitudinal_half_length_mm"] + tolerance and
                 geometry["inner_radius_mm"] - tolerance <= r <= geometry["outer_radius_mm"] + tolerance and
                 -angle_tolerance <= angle <= math.radians(geometry["angle_degrees"][1]) + angle_tolerance)
    if not valid:
        raise ValueError("Observed coordinates lie outside the declared geometry")


def _validated_record(raw: dict, cells: list[int], geometry: dict, definition: dict, case: str) -> dict:
    if not isinstance(raw, dict) or set(raw) != _RECORD_KEYS:
        raise ValueError("Structural mesh record must contain exactly the shared observation fields")
    if _cells(raw["cells"], definition) != cells:
        raise ValueError("Observed grid/order differs from the frozen mesh request")
    nx, ny, nz = cells
    elements = math.prod(cells)
    nodes = ((nx + 1) * (ny + 1) * (nz + 1) + nx * (ny + 1) * (nz + 1) +
             (nx + 1) * ny * (nz + 1) + (nx + 1) * (ny + 1) * nz)
    if type(raw["element_count"]) is not int or raw["element_count"] != elements:
        raise ValueError("element_count differs from the declared structured grid")
    ids = raw["node_ids"]
    if (not isinstance(ids, list) or len(ids) != nodes or any(type(n) is not int or n <= 0 for n in ids) or
            len(set(ids)) != nodes):
        raise ValueError("Every structured HEXA20 node requires one unique positive catalogue ID")
    coordinates, displacement = raw["coordinates_mm"], raw["displacements_mm"]
    if (not isinstance(coordinates, list) or not isinstance(displacement, list) or
            len(coordinates) != nodes or len(displacement) != nodes):
        raise ValueError("Displacements and coordinates must cover every catalogue node")
    coordinates = [_vector(row, 3, "Node coordinates") for row in coordinates]
    displacement = [_vector(row, 3, "Nodal displacement") for row in displacement]
    if len({tuple(row) for row in coordinates}) != nodes:
        raise ValueError("Duplicate physical node coordinates")
    tolerance = 1e-10 * definition["normalization"]["characteristic_length_mm"][case]
    for row in coordinates:
        _inside(row, geometry, tolerance)
    completeness = raw["field_completeness"]
    if (not isinstance(completeness, dict) or set(completeness) != _COMPLETENESS_KEYS or
            any(value is not True for value in completeness.values())):
        raise ValueError("All four native field completeness attestations must be true")
    artifact = raw["native_fields_artifact"]
    if (type(artifact) is not str or not artifact.startswith("simulation/") or "\\" in artifact or
            any(part in ("", ".", "..") for part in artifact.split("/")) or
            PurePosixPath(artifact).is_absolute() or ":" in artifact or any(ord(char) < 32 for char in artifact)):
        raise ValueError("Native field evidence must be a contained simulation artifact reference")
    points = raw["stress_points"]
    if not isinstance(points, list) or len(points) != elements * 27:
        raise ValueError("All 27 native stress points of every volume element are required")
    seen_ids, seen_coordinates, counts, normalized_points = set(), set(), {}, []
    for point in points:
        if not isinstance(point, dict) or set(point) != _POINT_KEYS:
            raise ValueError("Stress point is missing components, coordinates or catalogue identity")
        eid, pid = point["element_id"], point["point_id"]
        if (type(eid) is not int or not 1 <= eid <= elements or type(pid) is not int or pid <= 0 or
                (eid, pid) in seen_ids):
            raise ValueError("Stress point identities must be unique and cover declared elements")
        xyz = _vector(point["coordinates_mm"], 3, "Stress coordinates")
        _inside(xyz, geometry, tolerance)
        if (eid, tuple(xyz)) in seen_coordinates:
            raise ValueError("Duplicate physical stress point in an element")
        seen_coordinates.add((eid, tuple(xyz)))
        seen_ids.add((eid, pid))
        counts[eid] = counts.get(eid, 0) + 1
        normalized_points.append({"element_id": eid, "point_id": pid, "coordinates_mm": xyz,
                                  "components_mpa": _vector(point["components_mpa"], 6, "Native stress")})
    if len(counts) != elements or any(count != 27 for count in counts.values()):
        raise ValueError("Every volume element requires exactly 27 unique native points")
    result = {"cells": list(cells), "node_ids": list(ids), "coordinates_mm": coordinates,
              "displacements_mm": displacement, "stress_points": normalized_points,
              "element_count": elements, "native_fields_artifact": artifact}
    for field in ("reaction_n", "reaction_moment_n_mm", "applied_force_n", "applied_moment_n_mm"):
        result[field] = _vector(raw[field], 3, field)
    return result


def _response(record: dict, settings: dict, case: dict, geometry: dict, tolerance: float) -> dict:
    coordinates, displacement = record["coordinates_mm"], record["displacements_mm"]
    if case["family"] == "cantilever_force":
        length, width, _ = geometry["dimensions_mm"]
        chosen = []
        for target in ([length, 0.0, 0.0], [length, width, 0.0]):
            matches = [i for i, row in enumerate(coordinates) if max(abs(a - b) for a, b in zip(row, target)) <= tolerance]
            if len(matches) != 1:
                raise ValueError("Beam response requires each exact declared endpoint once")
            chosen.append(matches[0])
        component = _AXES.index(case["load_cases"][settings["load_case"]]["component"])
        values = [displacement[i][component] for i in chosen]
        return {"primary_response_mm": math.fsum(abs(value) / 2 for value in values),
                "signed_response_mm": math.fsum(value / 2 for value in values),
                "selected_signed_components_mm": values, "response_node_ids": [record["node_ids"][i] for i in chosen]}
    if case["family"] == "pressurized_cylinder":
        result = {}
        _, angular, axial = record["cells"]
        boundary_nodes = ((angular + 1) * (axial + 1) + angular * (axial + 1) +
                          (angular + 1) * axial)
        for boundary, radius in (("inner", geometry["inner_radius_mm"]), ("outer", geometry["outer_radius_mm"])):
            indices = [i for i, row in enumerate(coordinates) if abs(math.hypot(row[0], row[1]) - radius) <= tolerance]
            if len(indices) != boundary_nodes:
                raise ValueError("Cylinder response requires the complete radial boundary nodes")
            values = [(displacement[i][0] * coordinates[i][0] + displacement[i][1] * coordinates[i][1]) / radius
                      for i in indices]
            result[boundary + "_radial_response_mm"] = math.fsum(value / len(values) for value in values)
            result[boundary + "_response_node_ids"] = [record["node_ids"][i] for i in indices]
        result["primary_response_mm"] = result["inner_radial_response_mm"]
        result["signed_response_mm"] = result["primary_response_mm"]
        return result
    angle = math.radians(geometry["angle_degrees"][1])
    r = geometry["inner_radius_mm"]
    target = [geometry["longitudinal_half_length_mm"], r * math.sin(angle), r * math.cos(angle)]
    matches = [i for i, row in enumerate(coordinates) if max(abs(a - b) for a, b in zip(row, target)) <= tolerance]
    if len(matches) != 1:
        raise ValueError("Roof response requires the exact inner-surface point B once")
    value = displacement[matches[0]][2]
    return {"primary_response_mm": value, "signed_response_mm": value,
            "response_node_ids": [record["node_ids"][matches[0]]], "response_coordinate_mm": target}


def _difference_norm(left: list[float], right: list[float], *, sum_vectors: bool = False) -> float:
    return _number(math.hypot(*[_number(a + b if sum_vectors else a - b, "Vector residual")
                                for a, b in zip(left, right)]), "Vector residual norm")


def assess(settings: dict, records: list[dict]) -> dict:
    """Finest reference/fields, all-grid loads/equilibrium, last-pair trend.

    Numerical FAIL retains actual values and makes every feedback metric invalid.
    Malformed native observations raise rather than inventing a numerical result.
    """
    normalized = validate_settings(settings)
    definition = _definitions()
    case = definition["cases"][normalized["case"]]
    geometry, material, load = _physics(normalized, definition)
    reference = _reference(normalized, definition)
    if not isinstance(records, list) or len(records) != len(normalized["mesh_cells"]):
        raise ValueError("Every requested mesh requires one complete observation in order")
    length = definition["normalization"]["characteristic_length_mm"][normalized["case"]]
    response_scale = max(abs(reference["primary_response_mm"]), _FLOOR)
    analytic_force_scale = max(math.hypot(*reference["applied_force_n"]), _FLOOR)
    analytic_moment_scale = max(analytic_force_scale * length, _FLOOR)
    summaries = []
    for raw, cells in zip(records, normalized["mesh_cells"]):
        record = _validated_record(raw, cells, geometry, definition, normalized["case"])
        response = _response(record, normalized, case, geometry, length * 1e-10)
        force_scale = max(math.hypot(*record["applied_force_n"]), _FLOOR)
        summary = {"cells": list(cells), "node_count": len(record["node_ids"]), "element_count": record["element_count"],
                   "stress_point_count": len(record["stress_points"]), **response,
                   "reference_relative_error": abs(response["primary_response_mm"] - reference["primary_response_mm"]) / response_scale,
                   "reaction_relative_error": _difference_norm(record["reaction_n"], record["applied_force_n"], sum_vectors=True) / force_scale,
                   "moment_relative_error": _difference_norm(record["reaction_moment_n_mm"], record["applied_moment_n_mm"], sum_vectors=True) / max(force_scale * length, _FLOOR),
                   "applied_force_relative_error": _difference_norm(record["applied_force_n"], reference["applied_force_n"]) / analytic_force_scale,
                   "applied_moment_relative_error": _difference_norm(record["applied_moment_n_mm"], reference["applied_moment_n_mm"]) / analytic_moment_scale,
                   "reaction_n": record["reaction_n"], "reaction_moment_n_mm": record["reaction_moment_n_mm"],
                   "applied_force_n": record["applied_force_n"], "applied_moment_n_mm": record["applied_moment_n_mm"],
                   "native_fields_artifact": record["native_fields_artifact"]}
        if case["family"] == "pressurized_cylinder":
            u_error = max(abs(actual - expected) for xyz, actual_row in zip(record["coordinates_mm"], record["displacements_mm"])
                          for actual, expected in zip(actual_row, _cylinder_at(xyz, geometry, material, load)[0]))
            s_error = max(abs(actual - expected) for point in record["stress_points"]
                          for actual, expected in zip(point["components_mpa"], _cylinder_at(point["coordinates_mm"], geometry, material, load)[1]))
            summary.update({"max_component_displacement_error_mm": u_error, "pointwise_displacement_relative_error": u_error / response_scale,
                            "max_component_stress_error_mpa": s_error,
                            "pointwise_stress_relative_error": s_error / max(abs(reference["inner_surface_hoop_stress_mpa"]), _FLOOR)})
        # Overflow in derived errors is not a usable finite observation either.
        for key, value in summary.items():
            if type(value) in (int, float):
                _number(value, key)
        summaries.append(summary)
    last, previous = summaries[-1], summaries[-2]
    trend = abs(last["primary_response_mm"] - previous["primary_response_mm"]) / response_scale
    limits, numerical = case["limits"], definition["numerical_limits"]
    check_values = [
        ("reference_response", last["reference_relative_error"], limits["reference_relative"]),
        ("last_two_mesh_response", trend, limits["last_two_mesh_response_relative"]),
        ("signed_reaction_balance", max(row["reaction_relative_error"] for row in summaries), numerical["reaction_relative"]),
        ("signed_moment_balance", max(row["moment_relative_error"] for row in summaries), numerical["moment_relative"]),
        ("applied_force_reference", max(row["applied_force_relative_error"] for row in summaries), numerical["mesh_volume_relative"]),
        ("applied_moment_reference", max(row["applied_moment_relative_error"] for row in summaries), numerical["mesh_volume_relative"])]
    if case["family"] == "pressurized_cylinder":
        check_values.extend([("analytical_displacement", last["pointwise_displacement_relative_error"], limits["pointwise_displacement_relative"]),
                             ("analytical_stress", last["pointwise_stress_relative_error"], limits["pointwise_stress_relative"])])
    checks = [{"code": code, "status": "PASS" if _number(value, code) <= limit else "FAIL",
               "observed": value, "limit": limit} for code, value, limit in check_values]
    if case["family"] == "cantilever_force":
        signed_values = [value for row in summaries for value in row["selected_signed_components_mm"]]
        checks.append({"code": "positive_load_response_sign", "status": "PASS" if min(signed_values) > 0 else "FAIL",
                       "observed": min(signed_values), "expected": "Both exact response nodes have positive load-component displacement at every grid"})
    passed = all(check["status"] == "PASS" for check in checks)
    failures = ", ".join(check["code"] for check in checks if check["status"] == "FAIL")

    def metric(value: float, unit: str) -> dict:
        return {"value": _number(value, "Metric"), "unit": unit, "valid": passed,
                **({"reason": f"Structural-family numerical checks failed: {failures}"} if not passed else {})}

    metrics = {"primary_response": metric(last["primary_response_mm"], "mm"),
               "signed_primary_response": metric(last["signed_response_mm"], "mm"),
               "reference_relative_error": metric(last["reference_relative_error"], "1"),
               "mesh_response_relative": metric(trend, "1")}
    for key in ("reaction_relative_error", "moment_relative_error", "applied_force_relative_error", "applied_moment_relative_error"):
        metrics[key] = metric(max(row[key] for row in summaries), "1")
    if case["family"] == "pressurized_cylinder":
        metrics["secondary_response"] = metric(last["outer_radial_response_mm"], "mm")
        for key, unit in (("max_component_displacement_error_mm", "mm"), ("pointwise_displacement_relative_error", "1"),
                          ("max_component_stress_error_mpa", "MPa"), ("pointwise_stress_relative_error", "1")):
            metrics[key] = metric(last[key], unit)
    return {"checks": checks, "metrics": metrics,
            "pending_validations": list(definition["qualification"]["pending"]) + ["original_midas_replication"],
            "reference": reference, "mesh_studies": summaries,
            "mesh_response": {**copy.deepcopy(case["response"]), "agreement_statistic": definition["normalization"]["mesh_agreement"],
                              "reference_scope": "finest mesh", "equilibrium_scope": "every requested mesh"},
            "limitations": copy.deepcopy(case["limitations"]) + ["Native field completeness/source/catalogue identity is also an adapter gate.",
                "No assembled residual, energy, independent shell rotations or physical strength acceptance is inferred."]}
