"""Per-body affine reference comparison of complete, admitted native fields.

The adapter owns native syntax, identities, topology and field parsing. This
module never manufactures missing observations or qualifies fixture materials.
"""
from __future__ import annotations

import math

from .assembly_field_reference import (
    body_reference, constitutive_reference, displacement_reference, validate_settings,
)


def _real(value, label):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError("Complete finite observation required: " + label)
    return float(value)


def _sum(values):
    return _real(math.fsum(values), "derived sum")


def compare_fields(settings, fields):
    """Compare every body separately; retain failed metrics and UNKNOWN energy.

    Inputs are the adapter's full native-index records, not spatial averages.
    Native energy is a separate POST_ELEM observation. Boundary work and the
    native-weight volume sum are derived quantities and explicitly labelled.
    """
    settings = validate_settings(settings)
    reference = constitutive_reference(settings)
    components, limits = settings["components"], settings["limits"]
    if (fields.get("scope") != "COMPLETE_NATIVE_AFFINE_FIELDS" or
            set(fields["bodies"]) != set(components)):
        raise ValueError("Complete admitted seven-body native fields required")
    checks, bodies = [], []
    maxima = {key: 0.0 for key in limits}

    def check(code, observed, limit, component, *, detail=None):
        observed = _real(observed, code)
        checks.append({"code": code + ":" + component,
                       "status": "PASS" if observed <= limit else "FAIL",
                       "observed": observed, "limit": limit, "detail": detail})
        return observed

    for component in components:
        body = fields["bodies"][component]
        nodes, gauss = body["nodes"], body["gauss"]
        if not nodes or not gauss:
            raise ValueError("Empty admitted body")
        target = body_reference(settings, body["qualified_mesh_volume_mm3"])
        displacement_error = max(abs(_real(value, "U") - expected)
            for node in nodes for value, expected in zip(
                node["displacement_mm"], displacement_reference(settings, node["xyz_mm"])))
        stress_error = max(abs(_real(value, "stress") - expected)
            for point in gauss for value, expected in zip(
                point["stress6_mpa"], reference["stress6_mpa"]))
        native_volume = _sum(_real(point["weight_mm3"], "native W") for point in gauss)
        volume_error = abs(native_volume - target["mesh_volume_mm3"]) / target["mesh_volume_mm3"]
        force = [_sum(_real(n["reaction_n"][axis], "RF") for n in nodes) for axis in range(3)]
        moment = [_sum(n["xyz_mm"][(axis+1) % 3] * n["reaction_n"][(axis+2) % 3] -
                       n["xyz_mm"][(axis+2) % 3] * n["reaction_n"][(axis+1) % 3]
                       for n in nodes) for axis in range(3)]
        force_error = math.hypot(*force) / target["force_scale_n"]
        moment_error = math.hypot(*moment) / target["moment_scale_n_mm"]
        work = 0.5 * _sum(_real(u, "U") * _real(f, "RF")
                         for n in nodes for u, f in zip(n["displacement_mm"], n["reaction_n"]))
        work_error = abs(work - target["strain_energy_n_mm"]) / target["strain_energy_n_mm"]
        observations = {
            "displacement_absolute_mm": displacement_error,
            "stress_absolute_mpa": stress_error, "mesh_volume_relative": volume_error,
            "force_balance_scaled": force_error, "moment_balance_scaled": moment_error,
        }
        for name, value in observations.items():
            check(name, value, limits[name], component)
            maxima[name] = max(maxima[name], value)
        check("derived_boundary_work_relative", work_error, limits["energy_relative"], component,
              detail="DERIVED: 0.5*sum(actual native U dot actual native RF), all distinct body nodes")
        energy = body["native_energy"]
        energy_error = None
        if energy.get("status") != "OBSERVED":
            checks.append({"code": "native_energy_relative:" + component, "status": "UNKNOWN",
                           "observed": None, "limit": limits["energy_relative"],
                           "detail": energy.get("reason", "Native POST_ELEM energy unavailable")})
        else:
            value = _real(energy["value_n_mm"], "native energy")
            energy_error = abs(value - target["strain_energy_n_mm"]) / target["strain_energy_n_mm"]
            check("native_energy_relative", energy_error, limits["energy_relative"], component,
                  detail="NATIVE: POST_ELEM ENER_POT selected on this body's volume group")
            check("native_energy_vs_boundary_work_relative",
                  abs(value-work) / target["strain_energy_n_mm"], limits["energy_relative"], component)
        maxima["energy_relative"] = max(maxima["energy_relative"], work_error,
                                         energy_error if energy_error is not None else 0.0)
        interior = [n for n in nodes if not n["exterior"]]
        bodies.append({"component_id": component, "node_count": len(nodes),
            "interior_node_count": len(interior), "gauss_count": len(gauss),
            "reference": target, "native_weight_sum_volume_mm3": native_volume,
            "native_energy": energy, "derived_boundary_work_n_mm": work,
            "derived_force_n": force, "derived_original_coordinate_moment_n_mm": moment,
            "balance_vector_norm": "EUCLIDEAN",
            "interior_reaction_maximum_n": max((abs(f) for n in interior for f in n["reaction_n"]), default=0.0),
            "errors": observations | {"derived_boundary_work_relative": work_error,
                                       "native_energy_relative": energy_error}})
    energy_complete = all(b["native_energy"].get("status") == "OBSERVED" for b in bodies)
    units = {"displacement_absolute_mm": "mm", "stress_absolute_mpa": "MPa"}
    metrics = {name: {"value": value, "unit": units.get(name, "1"), "valid": True}
               for name, value in maxima.items()}
    if not energy_complete:
        metrics["energy_relative"] = {"value": None, "unit": "1", "valid": False,
                                      "reason": "At least one actual native body energy is UNKNOWN"}
    return {"status": "PASS" if all(c["status"] == "PASS" for c in checks) else
                      "FAIL" if any(c["status"] == "FAIL" for c in checks) else "UNKNOWN",
            "checks": checks, "metrics": metrics, "bodies": bodies,
            "reference": reference, "limits": limits, "decision": "NOT_RELEASED",
            "material_qualification": "HYPOTHETICAL_NOT_MEASURED",
            "limitations": ["Synthetic disconnected affine patch; no contact or fixture load-path qualification",
                "Physical material, mounting, fastening, strength and durability UNKNOWN",
                "Solver completion and numerical patch checks do not authorize release"]}
