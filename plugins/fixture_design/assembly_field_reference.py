"""Frozen hypothetical affine-patch mathematics, with no native verdict.

These parameters are a numerical benchmark declaration, not fixture material,
contact, mounting or strength defaults. Mesh identity, boundary-node selection,
full-field comparison and all engineering approvals require separate gates.
"""

from __future__ import annotations

import math

from plugins.fixture_design.assembly_mesh import ACTIVE as _ACTIVE

__all__ = [
    "canonical_settings", "validate_settings", "constitutive_reference",
    "displacement_reference", "body_reference",
]

_GRADIENT = (
    (1e-4, 4e-5, -5e-5),
    (-2e-5, -2e-4, 6e-5),
    (9e-5, -8e-5, 3e-4),
)
_TRANSLATION_MM = (0.012, -0.007, 0.003)
_LIMITS = {
    "displacement_absolute_mm": 1e-7,
    "stress_absolute_mpa": 1e-6,
    "mesh_volume_relative": 1e-8,
    "energy_relative": 1e-6,
    "force_balance_scaled": 1e-7,
    "moment_balance_scaled": 1e-7,
}


def canonical_settings() -> dict:
    """Return independent JSON data for the one preregistered numerical case."""
    return {
        "case": "fixture_assembly_affine_field_patch_v1",
        "intent": "SYNTHETIC_HOMOGENEOUS_ISOTROPIC_NUMERICAL_PATCH",
        "units": {"length": "mm", "force": "N", "stress": "MPa"},
        "components": list(_ACTIVE),
        "material": {
            "youngs_modulus_mpa": 2000.0,
            "poisson_ratio": 0.25,
            "qualification": "HYPOTHETICAL_NOT_MEASURED",
        },
        "kinematics": {
            "gradient": [list(row) for row in _GRADIENT],
            "translation_mm": list(_TRANSLATION_MM),
        },
        "boundary": "AFFINE_ON_ALL_EXTERIOR_NODES_INTERIOR_FREE",
        "limits": dict(_LIMITS),
    }


def _number(value: object, label: str) -> float:
    if type(value) not in (int, float):
        raise ValueError(f"{label} must be a finite nonboolean JSON number")
    try:
        result = float(value)
    except (OverflowError, ValueError) as error:
        raise ValueError(f"{label} is not finitely representable") from error
    if not math.isfinite(result):
        raise ValueError(f"{label} must be finite")
    return result


def _normalize(value: object, expected: object, label: str) -> object:
    if type(expected) is dict:
        if type(value) is not dict or set(value) != set(expected):
            raise ValueError(f"{label} requires exactly the frozen keys")
        return {key: _normalize(value[key], template, f"{label}.{key}")
                for key, template in expected.items()}
    if type(expected) is list:
        if type(value) is not list or len(value) != len(expected):
            raise ValueError(f"{label} requires the frozen JSON list shape")
        return [_normalize(item, template, f"{label}[{index}]")
                for index, (item, template) in enumerate(zip(value, expected))]
    if type(expected) is str:
        if type(value) is not str or value != expected:
            raise ValueError(f"{label} differs from the frozen declaration")
        return expected
    result = _number(value, label)
    if result != expected:
        raise ValueError(f"{label} differs from the frozen numerical case")
    return result


def validate_settings(settings: dict) -> dict:
    """Reject any variant and return fresh normalized data without mutation."""
    return _normalize(settings, canonical_settings(), "settings")


def constitutive_reference(settings: dict) -> dict:
    """Return the independent small-strain isotropic tensor reference."""
    normalized = validate_settings(settings)
    material, gradient = normalized["material"], normalized["kinematics"]["gradient"]
    young, poisson = material["youngs_modulus_mpa"], material["poisson_ratio"]
    mu = _number(young / (2.0 * (1.0 + poisson)), "computed mu_mpa")
    lam = _number(young * poisson / ((1.0 + poisson) * (1.0 - 2.0 * poisson)),
                  "computed lambda_mpa")
    strain = [gradient[0][0], gradient[1][1], gradient[2][2],
              math.fsum((gradient[0][1], gradient[1][0])) / 2.0,
              math.fsum((gradient[0][2], gradient[2][0])) / 2.0,
              math.fsum((gradient[1][2], gradient[2][1])) / 2.0]
    strain = [_number(value, "computed strain6_tensor") for value in strain]
    trace = math.fsum(strain[:3])
    stress = [math.fsum((lam * trace, 2.0 * mu * value)) for value in strain[:3]]
    stress.extend(2.0 * mu * value for value in strain[3:])
    stress = [_number(value, "computed stress6_mpa") for value in stress]
    density = _number(0.5 * math.fsum(
        [stress[index] * strain[index] for index in range(3)] +
        [2.0 * stress[index] * strain[index] for index in range(3, 6)]),
        "computed energy_density_mpa")
    if density <= 0.0:
        raise ValueError("Computed strain energy density must remain positive")
    return {"strain6_tensor": strain, "stress6_mpa": stress,
            "lambda_mpa": lam, "mu_mpa": mu, "energy_density_mpa": density}


def displacement_reference(settings: dict, xyz_mm: list) -> list[float]:
    """Evaluate the prescribed affine displacement at actual supplied XYZ."""
    normalized = validate_settings(settings)
    if type(xyz_mm) is not list or len(xyz_mm) != 3:
        raise ValueError("xyz_mm requires exactly three JSON coordinates")
    xyz = [_number(value, f"xyz_mm[{index}]") for index, value in enumerate(xyz_mm)]
    kinematics = normalized["kinematics"]
    values = [math.fsum([kinematics["translation_mm"][index]] +
                       [coefficient * coordinate for coefficient, coordinate in zip(row, xyz)])
              for index, row in enumerate(kinematics["gradient"])]
    return [_number(value, "computed displacement_mm") for value in values]


def body_reference(settings: dict, mesh_volume_mm3: float) -> dict:
    """Reference energy and nonzero scales from a qualified supplied mesh volume."""
    reference = constitutive_reference(settings)
    volume = _number(mesh_volume_mm3, "mesh_volume_mm3")
    if volume <= 0.0:
        raise ValueError("mesh_volume_mm3 must be positive")
    stress_scale = max(abs(value) for value in reference["stress6_mpa"])
    energy = _number(reference["energy_density_mpa"] * volume, "computed strain_energy_n_mm")
    # The cube-root form avoids exponent-rounding drift for extreme finite volumes.
    force_scale = _number(stress_scale * math.cbrt(volume) ** 2, "computed force_scale_n")
    moment_scale = _number(stress_scale * volume, "computed moment_scale_n_mm")
    if min(energy, force_scale, moment_scale) <= 0.0:
        raise ValueError("Computed energy and normalization scales must remain strictly positive")
    return {"mesh_volume_mm3": volume, "strain_energy_n_mm": energy,
            "force_scale_n": force_scale, "moment_scale_n_mm": moment_scale,
            "expected_force_n": [0.0, 0.0, 0.0],
            "expected_moment_n_mm": [0.0, 0.0, 0.0]}
