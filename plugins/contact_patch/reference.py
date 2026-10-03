"""Independent small-strain SSNP121A contact patch mathematics and verdicts.

Adapters must prove native source, node/sample identities, full fields and
execution separately. This module neither invokes a solver nor contains native
contact syntax. The published six signed point comparisons are not a full
pointwise contact, gap, cross-solver or engineering qualification.
"""

from __future__ import annotations

import copy
import json
import math


__version__ = "1.0"
_CASE = "ssnp121a_frictionless_patch"
_LIMITS = {"reference_relative": 0.01, "force_balance_relative": 1e-6}
_SAMPLES = ("A", "B", "N14")
_SAMPLE_FIELDS = {"normal_traction_pa", "vertical_displacement_m"}
_REACTION_FIELDS = {"top", "bottom", "all_nodes"}
_REQUIRED_OBSERVATIONS = {"samples", "boundary_reactions_n_per_m", "slave_contact"}
_OPTIONAL_OBSERVATIONS = {"fields", "projected_gaps_m"}
_PENDING = [
    "model_qualification", "material_qualification", "physical_validation",
    "static_strength", "fatigue_durability", "pointwise_contact_gap",
    "cross_solver_contact", "fixture_joint_contact",
    "corporate_license_approval", "corporate_security_approval",
]
_WIDTH_M = 2.0
_TOTAL_HEIGHT_M = 2.0
_SLAVE_NODES = 13


def _keys(value: object, expected: set[str], label: str) -> dict:
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError(f"{label} requires exactly: {', '.join(sorted(expected))}")
    return value


def _number(value: object, label: str) -> float:
    if type(value) not in (int, float):
        raise ValueError(f"{label} must be a finite number, not bool or a string")
    try:
        result = float(value)
    except (ValueError, OverflowError) as error:
        raise ValueError(f"{label} must be finitely representable") from error
    if not math.isfinite(result):
        raise ValueError(f"{label} must be finite")
    return result


def _vector(value: object, length: int, label: str) -> list[float]:
    if not isinstance(value, list) or len(value) != length:
        raise ValueError(f"{label} requires exactly {length} finite components")
    return [_number(component, label) for component in value]


def validate_settings(settings: dict) -> dict:
    """Normalize only the frozen case, bounded E/displacement and fixed limits."""
    _keys(settings, {"case", "material", "top_displacement_m", "limits"}, "Contact settings")
    if type(settings["case"]) is not str or settings["case"] != _CASE:
        raise ValueError(f"Only {_CASE} is supported")
    material = _keys(settings["material"], {"youngs_modulus_pa", "poisson_ratio"}, "Material")
    young = _number(material["youngs_modulus_pa"], "youngs_modulus_pa")
    if not 1e4 <= young <= 1e9:
        raise ValueError("youngs_modulus_pa must be between 1e4 and 1e9 Pa")
    poisson = _number(material["poisson_ratio"], "poisson_ratio")
    if poisson != 0.0:
        raise ValueError("This uniaxial contact patch reference requires poisson_ratio=0")
    displacement = _number(settings["top_displacement_m"], "top_displacement_m")
    if not -0.2 <= displacement <= -1e-4:
        raise ValueError("top_displacement_m must be negative with 1e-4 <= magnitude <= 0.2 m")
    limits = _keys(settings["limits"], set(_LIMITS), "Limits")
    normalized_limits = {name: _number(limits[name], name) for name in _LIMITS}
    if normalized_limits != _LIMITS:
        raise ValueError("Contact reference and force-balance limits are fixed; changes require new admission")
    return {"case": _CASE, "material": {"youngs_modulus_pa": young, "poisson_ratio": poisson},
            "top_displacement_m": displacement, "limits": normalized_limits}


def _reference(settings: dict) -> dict:
    strain = settings["top_displacement_m"] / _TOTAL_HEIGHT_M
    traction = settings["material"]["youngs_modulus_pa"] * strain
    pressure = -traction
    force = pressure * _WIDTH_M
    interface_displacement = settings["top_displacement_m"] / 2.0
    canonical = (settings["material"]["youngs_modulus_pa"] == 2e6 and
                 settings["top_displacement_m"] == -0.1)
    return {
        "case": _CASE, "reference_identity": "Code_Aster_SSNP121A",
        "canonical_original_inputs": canonical,
        "reference_kind": "original_published_analytical_case" if canonical else "analytical_parameter_variant",
        "nafems_cgs1_replication": False,
        "material": copy.deepcopy(settings["material"]),
        "bulk_vertical_strain": strain, "normal_traction_pa": traction,
        "pressure_magnitude_pa": pressure,
        "interface_vertical_displacement_m": interface_displacement,
        "boundary_reactions_n_per_m": {"top": [0.0, -force], "bottom": [0.0, force],
                                       "all_nodes": [0.0, 0.0]},
        "samples": {name: {"normal_traction_pa": traction,
                           "vertical_displacement_m": interface_displacement} for name in _SAMPLES},
        "units": {"length": "m", "normal_traction": "Pa", "strain": "1",
                  "reaction_resultant": "N/m", "thickness_meaning": "per_unit_out_of_plane_thickness"},
        "method": "epsilon=top_displacement/2; normal_traction=E*epsilon; interface_DY=top_displacement/2",
        "source_url": "https://codeaster.gitlab.io/doc/docaster/manuals/man_v/v6/v6.03.121/Solution_de_r_f_rence.html",
        "six_published_sample_relative_limits": settings["limits"]["reference_relative"],
        "force_reference_kind": "additional_analytical_unit_thickness_resultant",
    }


def analytical_reference(settings: dict) -> dict:
    """Signed analytical reference; pressure magnitude is a separate quantity."""
    return _reference(validate_settings(settings))


def model_declaration(settings: dict) -> dict:
    """Common geometry/material/interface metadata without native contact syntax."""
    normalized = validate_settings(settings)
    material = normalized["material"]
    interface = {"axis": "y", "coordinate": 0.0, "unit": "m", "x_interval_m": [-1.0, 1.0]}
    return {
        "case": _CASE,
        "geometry": {"type": "two_disconnected_rectangles", "unit": "m", "plane": "xy",
            "bodies": [{"id": "upper", "x_interval_m": [-1.0, 1.0], "y_interval_m": [0.0, 1.0]},
                       {"id": "lower", "x_interval_m": [-1.0, 1.0], "y_interval_m": [-1.0, 0.0]}],
            "out_of_plane_model": "plane_strain", "initial_interface_gap_m": 0.0},
        "materials": [{"id": "elastic", "body_ids": ["upper", "lower"],
            "model": "linear_elastic_isotropic", "kinematics": "small_strain",
            "youngs_modulus": {"value": material["youngs_modulus_pa"], "unit": "Pa"},
            "poisson_ratio": {"value": material["poisson_ratio"], "unit": "1"}}],
        "mesh": {"source": "fixed_original_nonmatching_mesh", "order": 1, "topology": "quadrilateral",
            "node_count": 313, "solid_cell_count": 265, "boundary_segment_count": 92,
            "documented_boundary_segment_count": 132,
            "slave_contact_segment_count": 12, "master_contact_segment_count": 11,
            "coincident_interface_nodes_merged": False, "original_coordinates_preserved": True,
            "source_discrepancy": "Published Model A says 132 segments; the frozen native mesh has 92."},
        "interfaces": [{"id": "upper_lower", "type": "nonmatching_surface_pair",
            "upper_surface": {"body_id": "upper", **copy.deepcopy(interface)},
            "lower_surface": {"body_id": "lower", **copy.deepcopy(interface)}}],
        "contact": [{"interface_id": "upper_lower", "type": "frictionless_unilateral",
            "slave_body_id": "upper", "master_body_id": "lower", "tangential_behavior": "free_sliding",
            "compression_sign": "negative_normal_traction", "initial_gap": {"value": 0.0, "unit": "m"}}],
        "coordinate_systems": [{"id": "global", "type": "cartesian", "origin": [0.0, 0.0, 0.0],
            "x_axis": [1.0, 0.0, 0.0], "y_axis": [0.0, 1.0, 0.0], "z_axis": [0.0, 0.0, 1.0], "unit": "m"}],
        "boundary_conditions": [
            {"type": "prescribed_displacement", "selection": {"body_id": "lower", "axis": "y",
                "coordinate": -1.0, "unit": "m"}, "components": ["x", "y"], "values": [0.0, 0.0], "unit": "m"},
            {"type": "prescribed_displacement", "selection": {"body_id": "upper", "axis": "y",
                "coordinate": 1.0, "unit": "m"}, "component": "x", "value": 0.0, "unit": "m"}],
        "loads": [{"type": "prescribed_displacement_history", "selection": {"body_id": "upper",
            "axis": "y", "coordinate": 1.0, "unit": "m"}, "component": "y", "load_parameter": [0.0, 1.0],
            "values": [0.0, normalized["top_displacement_m"]], "unit": "m"}],
        "history": {"load_parameter": [0.0, 1.0], "meaning": "quasi_static_load_parameter"},
        "outputs": {"load_parameter": [0.0, 1.0], "fields": [
            {"field": "displacement", "components": ["x", "y"], "location": "nodes", "unit": "m"},
            {"field": "normal_traction", "location": "slave_contact_nodes", "unit": "Pa",
             "compression_sign": "negative"},
            {"field": "reactions", "components": ["x", "y"], "location": "nodes", "unit": "N/m"},
            {"field": "stress", "location": "solid_elements", "unit": "Pa"},
            {"field": "projected_contact_gap", "location": "slave_contact_nodes", "unit": "m",
             "derived": True, "native_measured_gap": False}],
            "sample_points": {"A": [-1.0, 0.0], "B": [1.0, 0.0], "N14": [2.98023223876953e-08, 0.0]},
            "sample_coordinate_unit": "m"},
        "reference": _reference(normalized),
    }


def _validated_observation(observation: dict) -> dict:
    if (not isinstance(observation, dict) or not _REQUIRED_OBSERVATIONS <= set(observation) or
            set(observation) - (_REQUIRED_OBSERVATIONS | _OPTIONAL_OBSERVATIONS)):
        raise ValueError("Contact observation has missing or unsupported fields")
    samples = _keys(observation["samples"], set(_SAMPLES), "Samples")
    normalized_samples = {}
    for name in _SAMPLES:
        sample = _keys(samples[name], _SAMPLE_FIELDS, f"Sample {name}")
        normalized_samples[name] = {field: _number(sample[field], f"{name}.{field}")
                                    for field in sorted(_SAMPLE_FIELDS)}
    reactions = _keys(observation["boundary_reactions_n_per_m"], _REACTION_FIELDS, "Reactions")
    normalized_reactions = {name: _vector(reactions[name], 2, f"Reaction {name}") for name in sorted(_REACTION_FIELDS)}
    slave = _keys(observation["slave_contact"], {"node_ids", "normal_traction_pa"}, "Slave contact")
    ids = slave["node_ids"]
    if (not isinstance(ids, list) or len(ids) != _SLAVE_NODES or
            any(type(node) is not int or not 0 <= node < 313 for node in ids) or len(set(ids)) != len(ids)):
        raise ValueError("Slave contact requires 13 unique native integer node indices in [0,313)")
    traction = _vector(slave["normal_traction_pa"], _SLAVE_NODES, "Slave normal_traction_pa")
    raw_gaps = observation.get("projected_gaps_m")
    gaps = None if raw_gaps is None else _vector(raw_gaps, _SLAVE_NODES, "projected_gaps_m")
    fields = observation.get("fields")
    if "fields" in observation:
        if not isinstance(fields, dict):
            raise ValueError("Optional fields metadata must be a dictionary")
        try:
            json.dumps(fields, allow_nan=False)
        except (ValueError, TypeError, OverflowError, RecursionError) as error:
            raise ValueError("Optional fields metadata must contain finite JSON data") from error
    return {"samples": normalized_samples, "boundary_reactions_n_per_m": normalized_reactions,
            "slave_contact": {"node_ids": list(ids), "normal_traction_pa": traction},
            "projected_gaps_m": gaps, **({"fields": copy.deepcopy(fields)} if "fields" in observation else {})}


def assess(settings: dict, observation: dict) -> dict:
    """Keep signed failed observations, fixed reference gates and unresolved physics."""
    normalized = validate_settings(settings)
    reference = _reference(normalized)
    observed = _validated_observation(observation)
    checks = []
    errors = {"normal_traction_pa": [], "vertical_displacement_m": []}

    def reference_check(code: str, actual: float, expected: float) -> float:
        error = _number(abs(actual - expected) / abs(expected), f"{code} relative error")
        checks.append({"code": code, "status": "PASS" if error <= normalized["limits"]["reference_relative"] else "FAIL",
            "observed": actual, "reference": expected, "relative_error": error,
            "limit": normalized["limits"]["reference_relative"]})
        return error

    for name in _SAMPLES:
        for field in ("normal_traction_pa", "vertical_displacement_m"):
            errors[field].append(reference_check(f"sample_{name}_{field}", observed["samples"][name][field],
                                                reference["samples"][name][field]))
    reactions = observed["boundary_reactions_n_per_m"]
    for side in ("top", "bottom"):
        reference_check(f"{side}_normal_reaction", reactions[side][1],
                        reference["boundary_reactions_n_per_m"][side][1])
    try:
        boundary_sum = [_number(math.fsum((reactions["top"][axis], reactions["bottom"][axis])),
                                "Boundary resultant") for axis in range(2)]
    except OverflowError as error:
        raise ValueError("Boundary resultant is not finitely representable") from error
    force_scale = reference["boundary_reactions_n_per_m"]["bottom"][1]
    balances = {}
    for code, resultant in (("boundary_force_balance", boundary_sum), ("all_nodes_force_balance", reactions["all_nodes"])):
        relative = _number(math.hypot(*resultant) / force_scale, f"{code} relative error")
        balances[code] = relative
        checks.append({"code": code, "status": "PASS" if relative <= normalized["limits"]["force_balance_relative"] else "FAIL",
            "observed": relative, "resultant_n_per_m": list(resultant), "reference_scale_n_per_m": force_scale,
            "limit": normalized["limits"]["force_balance_relative"]})
    passed = all(check["status"] == "PASS" for check in checks)
    failures = ", ".join(check["code"] for check in checks if check["status"] == "FAIL")

    def metric(value: float | None, unit: str) -> dict:
        if value is None:
            return {"value": None, "unit": unit, "valid": False, "reason": "Derived projected gaps were not supplied; qualification remains UNKNOWN"}
        return {"value": value, "unit": unit, "valid": passed,
                **({"reason": f"Contact numerical gates failed: {failures}"} if not passed else {})}

    metrics = {}
    for name in _SAMPLES:
        metrics[f"{name}_normal_traction"] = metric(observed["samples"][name]["normal_traction_pa"], "Pa")
        metrics[f"{name}_vertical_displacement"] = metric(observed["samples"][name]["vertical_displacement_m"], "m")
    pressures = observed["slave_contact"]["normal_traction_pa"]
    gaps = observed["projected_gaps_m"]
    metrics.update({
        "max_sample_pressure_relative_error": metric(max(errors["normal_traction_pa"]), "1"),
        "max_sample_displacement_relative_error": metric(max(errors["vertical_displacement_m"]), "1"),
        "top_reaction_y": metric(reactions["top"][1], "N/m"),
        "bottom_reaction_y": metric(reactions["bottom"][1], "N/m"),
        "boundary_force_balance_relative": metric(balances["boundary_force_balance"], "1"),
        "all_nodes_force_balance_relative": metric(balances["all_nodes_force_balance"], "1"),
        "slave_normal_traction_min": metric(min(pressures), "Pa"),
        "slave_normal_traction_max": metric(max(pressures), "Pa"),
        "derived_projected_gap_min": metric(min(gaps) if gaps is not None else None, "m"),
        "derived_projected_gap_max": metric(max(gaps) if gaps is not None else None, "m"),
        "derived_projected_gap_max_absolute": metric(max(abs(gap) for gap in gaps) if gaps is not None else None, "m"),
    })
    return {"checks": checks, "metrics": metrics, "pending_validations": list(_PENDING), "reference": reference,
        "contact_observation": {"slave_node_ids": list(observed["slave_contact"]["node_ids"]),
            "normal_traction_pa": list(pressures), "projected_gaps_m": None if gaps is None else list(gaps),
            "projected_gap_method": "actual_displaced_slave_to_piecewise_linear_displaced_master_projection",
            "native_measured_gap": False, "pointwise_qualification": "UNKNOWN"},
        **({"fields": copy.deepcopy(observed["fields"])} if "fields" in observed else {}),
        "limitations": [
            "Distinct Code_Aster SSNP121A frictionless, small-strain, plane-strain elastic patch with nu=0; this is not NAFEMS CGS1 or MIDAS reproduction.",
            "Only unchanged E=2e6Pa and top DY=-0.1m reproduce the original published inputs; other admitted values are analytical parameter variants.",
            "The six published 1% sample gates do not qualify every slave pressure, pointwise gap or mesh convergence.",
            "Top/bottom reactions are per unit out-of-plane thickness and have an additional analytical reference; force balance has its own fixed 1e-6 gate.",
            "Projected gaps are derived from actual displaced geometry, not a native measured gap or a pointwise acceptance verdict.",
            "Full source/node/sample/field identities and solver convergence require separate adapter evidence; no missing observation is replaced with zero.",
            "The admitted maximum 0.2m displacement is 10% strain over the total 2m height; material and physical validity remain UNKNOWN.",
            "Cross-solver contact, friction/sliding/large-strain cases, real fixture joints and all engineering/deployment qualifications remain UNKNOWN; numerical agreement cannot authorize RELEASED.",
        ]}
