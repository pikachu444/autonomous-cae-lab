"""Affine uniaxial 3D elasticity patch test, with no solver-specific syntax.

The block starts at the origin. Its symmetry constraints are DX=0 on x=0,
DY=0 on y=0, DZ=0 on z=0; a positive X traction acts on x=L. Other surfaces
are free. A constant-strain field is represented exactly by linear and
quadratic tetrahedra, so mesh agreement here is a patch test, not an estimated
mesh convergence rate or qualification of a real component.
"""

from __future__ import annotations

import copy
import math
import sys


_SETTING_KEYS = {"case", "dimensions_mm", "material", "traction_mpa", "mesh_sizes_mm", "limits"}
_MATERIAL_KEYS = {"youngs_modulus_mpa", "poisson_ratio"}
_LIMIT_KEYS = {"displacement_relative", "displacement_absolute_mm", "stress_relative",
               "reaction_relative", "mesh_agreement_relative"}
_RECORD_KEYS = {"mesh_size_mm", "node_ids", "coordinates_mm", "displacements_mm",
                "stresses_mpa", "reaction_n", "element_count"}
_PENDING = ["static_strength", "material_qualification", "physical_validation",
            "fatigue_durability", "model_qualification"]
_COMPONENTS = ["xx", "yy", "zz", "xy", "xz", "yz"]


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


def _reference(settings: dict) -> dict:
    length, breadth, height = settings["dimensions_mm"]
    young = settings["material"]["youngs_modulus_mpa"]
    poisson = settings["material"]["poisson_ratio"]
    traction = settings["traction_mpa"]
    axial_strain = _number(traction / young, "Analytical strain", positive=True)
    gradient = [axial_strain, -poisson * axial_strain, -poisson * axial_strain]
    tips = [_number(slope * span, "Analytical tip displacement")
            for slope, span in zip(gradient, (length, breadth, height))]
    force = _number(traction * breadth * height, "Analytical resultant force", positive=True)
    energy = _number(0.5 * force * tips[0], "Analytical strain energy", positive=True)
    if tips[0] <= 0:
        raise ValueError("Analytical axial tip displacement must be representable and positive")
    return {"case": settings["case"], "axial_tip_displacement_mm": tips[0],
            "stress_components_mpa": [traction, 0.0, 0.0, 0.0, 0.0, 0.0],
            "stress_component_order": list(_COMPONENTS), "reaction_n": [-force, 0.0, 0.0],
            "strain_energy_n_mm": energy, "displacement_gradient": gradient,
            "transverse_tip_displacements_mm": tips[1:],
            "units": {"displacement": "mm", "stress": "MPa", "reaction": "N", "energy": "N mm"}}


def validate_settings(settings: dict) -> dict:
    """Return an independent normalized request; reject unsupported or bad inputs."""
    _keys(settings, _SETTING_KEYS, "Elasticity settings")
    if settings["case"] != "uniaxial_block":
        raise ValueError("Elasticity case must be uniaxial_block")
    dimensions = _vector(settings["dimensions_mm"], 3, "dimensions_mm")
    if any(value <= 0.0 for value in dimensions):
        raise ValueError("dimensions_mm must be positive")
    material = _keys(settings["material"], _MATERIAL_KEYS, "Elasticity material")
    young = _number(material["youngs_modulus_mpa"], "youngs_modulus_mpa", positive=True)
    poisson = _number(material["poisson_ratio"], "poisson_ratio")
    if not -1.0 < poisson < 0.5:
        raise ValueError("poisson_ratio must satisfy -1 < nu < 0.5")
    traction = _number(settings["traction_mpa"], "traction_mpa", positive=True)
    sizes = settings["mesh_sizes_mm"]
    if not isinstance(sizes, list) or not 2 <= len(sizes) <= 3:
        raise ValueError("mesh_sizes_mm requires two or three descending distinct sizes")
    sizes = [_number(value, "mesh_sizes_mm", positive=True) for value in sizes]
    if (any(coarse <= fine for coarse, fine in zip(sizes, sizes[1:])) or
            any(value > min(dimensions) for value in sizes)):
        raise ValueError("mesh_sizes_mm must be descending, distinct and <= every block dimension")
    limits = _keys(settings["limits"], _LIMIT_KEYS, "Elasticity limits")
    normalized = copy.deepcopy(settings)
    normalized.update({"dimensions_mm": dimensions,
                       "material": {"youngs_modulus_mpa": young, "poisson_ratio": poisson},
                       "traction_mpa": traction, "mesh_sizes_mm": sizes,
                       "limits": {name: _number(limits[name], name, positive=True)
                                  for name in sorted(_LIMIT_KEYS)}})
    # Refuse an unrepresentable reference before any solver is invoked; no
    # overflow/underflow value can become a JSON metric or a zero denominator.
    reference = _reference(normalized)
    scale = max(abs(slope * span) for slope, span in
                zip(reference["displacement_gradient"], dimensions))
    _number(normalized["limits"]["displacement_absolute_mm"] +
            normalized["limits"]["displacement_relative"] * scale,
            "Displacement tolerance", positive=True)
    return normalized


def _coordinates(coords: object, settings: dict) -> list[list[float]]:
    rows = _table(coords, 3, "coordinates_mm")
    tolerance = 64.0 * sys.float_info.epsilon * max(1.0, max(settings["dimensions_mm"]))
    for row in rows:
        if any(value < -tolerance or value > span + tolerance
               for value, span in zip(row, settings["dimensions_mm"])):
            raise ValueError("coordinates_mm lies outside the declared block")
    return rows


def displacement_at(coords: list[list[float]], settings: dict) -> list[list[float]]:
    """Exact signed components [t*x/E, -nu*t*y/E, -nu*t*z/E], in mm."""
    normalized = validate_settings(settings)
    coordinates = _coordinates(coords, normalized)
    gradient = _reference(normalized)["displacement_gradient"]
    return [[_number(slope * value, "Analytical displacement")
             for slope, value in zip(gradient, row)] for row in coordinates]


def analytical_reference(settings: dict) -> dict:
    """Physical affine reference, with six stress components and signed reactions."""
    return _reference(validate_settings(settings))


def model_declaration(settings: dict) -> dict:
    """Domain-owned, solver-independent geometry, constitutive law and load case."""
    normalized = validate_settings(settings)
    return {"case": normalized["case"],
            "geometry": {"type": "block", "dimensions_mm": list(normalized["dimensions_mm"]),
                         "unit": "mm", "origin": [0.0, 0.0, 0.0]},
            "materials": [{"model": "isotropic_linear_elastic",
                           "youngs_modulus": {"value": normalized["material"]["youngs_modulus_mpa"],
                                             "unit": "MPa"},
                           "poisson_ratio": {"value": normalized["material"]["poisson_ratio"],
                                             "unit": "1"}}],
            "mesh": {"sizes_mm": list(normalized["mesh_sizes_mm"]),
                     "order": 2, "element_type": "TETRA10"},
            "boundary_conditions": [{"type": "prescribed_displacement",
                                      "selection": {"type": "plane", "axis": axis, "coordinate_mm": 0.0},
                                      "component": axis, "value": 0.0, "unit": "mm"}
                                     for axis in ("x", "y", "z")],
            "loads": [{"type": "traction",
                       "selection": {"type": "plane", "axis": "x",
                                     "coordinate_mm": normalized["dimensions_mm"][0]},
                       "value": [normalized["traction_mpa"], 0.0, 0.0], "unit": "MPa"}],
            "outputs": {"fields": [{"field": "displacement", "unit": "mm"},
                                   {"field": "stress", "unit": "MPa", "components": list(_COMPONENTS)},
                                   {"field": "reactions", "unit": "N"}]}}


def _validated_record(record: dict, size: float, settings: dict) -> dict:
    if not isinstance(record, dict) or not _RECORD_KEYS <= set(record):
        raise ValueError("Mesh observation is missing required elasticity data")
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
    coordinates = _coordinates(record["coordinates_mm"], settings)
    displacements = _table(record["displacements_mm"], 3, "displacements_mm")
    if len(coordinates) != len(identifiers) or len(displacements) != len(identifiers):
        raise ValueError("Mesh coordinates/displacements must cover every node_id exactly once")
    stresses = _table(record["stresses_mpa"], 6, "stresses_mpa")
    if len(stresses) < elements:
        raise ValueError("Stress observations must cover at least one point per volume element")
    reactions = _vector(record["reaction_n"], 3, "reaction_n")
    tolerance = 64.0 * sys.float_info.epsilon * max(1.0, max(settings["dimensions_mm"]))
    for axis, span in enumerate(settings["dimensions_mm"]):
        if (abs(min(row[axis] for row in coordinates)) > tolerance or
                abs(max(row[axis] for row in coordinates) - span) > tolerance):
            raise ValueError("Mesh coordinates must span all declared block boundary planes")
    right_nodes = [index for index, row in enumerate(coordinates)
                   if abs(row[0] - settings["dimensions_mm"][0]) <= tolerance]
    if len(right_nodes) < 3:
        raise ValueError("Mesh observations must contain the right traction face nodes")
    return {"mesh_size_mm": size, "node_ids": list(identifiers), "coordinates_mm": coordinates,
            "displacements_mm": displacements, "stresses_mpa": stresses,
            "reaction_n": reactions, "element_count": elements, "right_nodes": right_nodes}


def assess(settings: dict, mesh_records: list[dict]) -> dict:
    """Assess complete finite observations; retain numerical FAIL values unchanged.

    Adapter code remains responsible for topology and proving that its node and
    SIEF_ELGA tables are complete; this domain API checks their shape/coverage.
    The selected mesh response is the mean signed DX on x=L, normalized by the
    analytical axial-tip value, never a displacement-vector magnitude.
    """
    normalized = validate_settings(settings)
    if not isinstance(mesh_records, list) or len(mesh_records) != len(normalized["mesh_sizes_mm"]):
        raise ValueError("A complete observation is required for every requested mesh")
    reference = _reference(normalized)
    gradient = reference["displacement_gradient"]
    displacement_scale = max(abs(slope * span) for slope, span in
                             zip(gradient, normalized["dimensions_mm"]))
    displacement_limit = (normalized["limits"]["displacement_absolute_mm"] +
                          normalized["limits"]["displacement_relative"] * displacement_scale)
    traction = normalized["traction_mpa"]
    force = abs(reference["reaction_n"][0])
    summaries = []
    for raw, size in zip(mesh_records, normalized["mesh_sizes_mm"]):
        record = _validated_record(raw, size, normalized)
        exact = [[slope * coord for slope, coord in zip(gradient, row)]
                 for row in record["coordinates_mm"]]
        displacement_error = _number(max(abs(actual - expected)
                                         for observed, expected_row in
                                         zip(record["displacements_mm"], exact)
                                         for actual, expected in zip(observed, expected_row)),
                                     "Displacement error")
        stress_error = _number(max(abs(actual - expected)
                                  for row in record["stresses_mpa"]
                                  for actual, expected in zip(row, reference["stress_components_mpa"])),
                              "Stress error")
        reaction_error = _number(max(abs(actual - expected) for actual, expected in
                                    zip(record["reaction_n"], reference["reaction_n"])),
                                "Reaction error")
        right_axial = _number(math.fsum(record["displacements_mm"][node][0] /
                                       len(record["right_nodes"]) for node in record["right_nodes"]),
                              "Right face axial displacement")
        summaries.append({"mesh_size_mm": size, "node_count": len(record["node_ids"]),
                          "element_count": record["element_count"],
                          "stress_point_count": len(record["stresses_mpa"]),
                          "max_component_displacement_error_mm": displacement_error,
                          "displacement_relative_error": _number(displacement_error / displacement_scale,
                                                                 "Relative displacement error"),
                          "max_component_stress_error_mpa": stress_error,
                          "stress_relative_error": _number(stress_error / traction, "Relative stress error"),
                          "reaction_n": record["reaction_n"],
                          "reaction_absolute_error_n": reaction_error,
                          "reaction_relative_error": _number(reaction_error / force, "Relative reaction error"),
                          "right_face_node_count": len(record["right_nodes"]),
                          "axial_tip_displacement_mm": right_axial})
    tips = [item["axial_tip_displacement_mm"] for item in summaries]
    mesh_difference = _number(max(tips) - min(tips), "Mesh displacement difference")
    agreement = _number(mesh_difference / reference["axial_tip_displacement_mm"], "Mesh agreement")
    displacement_error = max(item["max_component_displacement_error_mm"] for item in summaries)
    stress_relative = max(item["stress_relative_error"] for item in summaries)
    reaction_relative = max(item["reaction_relative_error"] for item in summaries)
    values = [("analytical_displacement", displacement_error <= displacement_limit,
               displacement_error, {"absolute_mm": normalized["limits"]["displacement_absolute_mm"],
                                    "relative": normalized["limits"]["displacement_relative"],
                                    "global_reference_scale_mm": displacement_scale,
                                    "combined_absolute_mm": displacement_limit}),
              ("analytical_stress", stress_relative <= normalized["limits"]["stress_relative"],
               stress_relative, normalized["limits"]["stress_relative"]),
              ("signed_reaction_balance", reaction_relative <= normalized["limits"]["reaction_relative"],
               reaction_relative, normalized["limits"]["reaction_relative"]),
              ("mesh_agreement", agreement <= normalized["limits"]["mesh_agreement_relative"],
               agreement, normalized["limits"]["mesh_agreement_relative"])]
    checks = [{"code": code, "status": "PASS" if passed else "FAIL", "observed": observed,
               "limit": limit} for code, passed, observed, limit in values]
    passed = all(check["status"] == "PASS" for check in checks)
    failures = ", ".join(check["code"] for check in checks if check["status"] == "FAIL")

    def metric(value: float, unit: str) -> dict:
        return {"value": value, "unit": unit, "valid": passed,
                **({"reason": f"Declared elasticity numerical validation failed: {failures}"}
                   if not passed else {})}

    metrics = {"axial_tip_displacement": metric(tips[-1], "mm"),
               "max_component_displacement_error": metric(displacement_error, "mm"),
               "displacement_relative_error": metric(max(item["displacement_relative_error"]
                                                         for item in summaries), "1"),
               "max_component_stress_error": metric(max(item["max_component_stress_error_mpa"]
                                                        for item in summaries), "MPa"),
               "stress_relative_error": metric(stress_relative, "1"),
               "reaction_x": metric(summaries[-1]["reaction_n"][0], "N"),
               "reaction_absolute_error": metric(max(item["reaction_absolute_error_n"]
                                                    for item in summaries), "N"),
               "reaction_relative_error": metric(reaction_relative, "1"),
               "mesh_axial_displacement_difference": metric(mesh_difference, "mm"),
               "mesh_agreement_relative": metric(agreement, "1")}
    return {"checks": checks, "metrics": metrics, "pending_validations": list(_PENDING),
            "reference": reference, "mesh_studies": summaries,
            "mesh_response": {"component": "DX", "location": "x=L", "statistic": "arithmetic_mean",
                              "normalization": "analytical_axial_tip_displacement",
                              "agreement_statistic": "max_minus_min_across_all_meshes"},
            "limitations": ["Affine constant-strain patch test; no mesh convergence rate is inferred.",
                            "Numerical reference agreement does not qualify a component or material."]}
