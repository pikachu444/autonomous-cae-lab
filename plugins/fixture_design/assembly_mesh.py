"""Bounded compression-path mesh intent; this is no mechanics qualification."""
from __future__ import annotations

import math

ACTIVE = (
    "printed_base", "printed_support_left", "printed_support_right",
    "metal_roller_left", "metal_roller_right", "metal_loading_nose", "specimen",
)
INACTIVE = tuple(f"metal_bolt_{side}_{dx}_{y}"
                 for side in ("left", "right") for dx in (-10, 10) for y in (-12, 12))
INACTIVE_REASON = "Original CAD has no thread/nut/base anchor/preload; fastener coupling is UNKNOWN"
LIMITS = {"center_absolute_mm": 1e-7, "bounds_absolute_mm": 2e-7,
          "measure_relative": 1e-8, "body_mesh_volume_relative": 0.01}
POINTS = ((0.25, 0.25, 0.25), (1/6, 1/6, 1/6),
          (0.5, 1/6, 1/6), (1/6, 0.5, 1/6), (1/6, 1/6, 0.5))
WEIGHTS = (-2/15, 3/40, 3/40, 3/40, 3/40)
LIMITATIONS = [
    "Five sampled geometric Jacobians do not prove positivity throughout an element",
    "This is mesh preprocessing, not Code_Aster Gauss/stress/contact/convergence evidence",
    "Materials, load path, fasteners, physical strength and release remain UNKNOWN",
]


def profile(value: float) -> dict:
    if type(value) not in (int, float) or not math.isfinite(value) or value not in (3.0, 1.5):
        raise ValueError("Only finite nonboolean 3.0/1.5 mm mesh profiles are admitted")
    return {"name": "coarse3" if value == 3 else "fine1_5", "mesh_size_mm": float(value),
            "units": "mm", "rule": "tetrahedron_degree3_five_point",
            "points": [list(p) for p in POINTS], "weights": list(WEIGHTS),
            "limits": dict(LIMITS)}


def intent(components: list[dict]) -> dict:
    if not isinstance(components, list) or len(components) != 15:
        raise ValueError("The complete fifteen-component CAD parent is required")
    names = [c["id"] for c in components]
    if len(set(names)) != 15 or set(names) != set(ACTIVE + INACTIVE):
        raise ValueError("Original active/inactive component identity differs")
    return {"active": list(ACTIVE), "inactive": [
        {"component_id": name, "reason": INACTIVE_REASON} for name in INACTIVE],
        "mechanics": "UNKNOWN", "decision": "NOT_RELEASED"}


def quality(cad_volumes: dict[str, float], rows: list[dict]) -> dict:
    """Retain invalid samples and compare each captured body volume separately."""
    if set(cad_volumes) != set(ACTIVE):
        raise ValueError("All seven captured native CAD volumes are required")
    grouped = {name: [] for name in ACTIVE}
    ids = set()
    for row in rows:
        eid, name = row["element_id"], row["component_id"]
        if type(eid) is not int or eid <= 0 or eid in ids or name not in grouped:
            raise ValueError("Duplicate, foreign or invalid Jacobian element identity")
        ids.add(eid)
        dets = row["determinants_mm3"]
        if not isinstance(dets, list) or len(dets) != 5 or any(
                type(v) not in (int, float) or not math.isfinite(v) for v in dets):
            raise ValueError("Complete finite five-point Jacobian observations required")
        grouped[name].append(dets)
    checks = []
    for name in ACTIVE:
        reference = cad_volumes[name]
        if type(reference) not in (int, float) or not math.isfinite(reference) or reference <= 0 or not grouped[name]:
            raise ValueError("Missing body elements or invalid actual CAD volume")
        samples = [v for dets in grouped[name] for v in dets]
        volume = math.fsum(math.fsum(w * d for w, d in zip(WEIGHTS, ds)) for ds in grouped[name])
        error = abs(volume - reference) / reference
        checks.append({"component_id": name, "tetra10_count": len(grouped[name]),
            "sample_count": len(samples), "minimum_determinant_mm3": min(samples),
            "maximum_determinant_mm3": max(samples), "nonpositive_count": sum(v <= 0 for v in samples),
            "cad_volume_mm3": reference, "integrated_mesh_volume_mm3": volume,
            "relative_volume_error": error, "relative_volume_limit": LIMITS["body_mesh_volume_relative"],
            "status": "PASS" if min(samples) > 0 and error <= LIMITS["body_mesh_volume_relative"] else "FAIL"})
    return {"status": "PASS" if all(c["status"] == "PASS" for c in checks) else "FAIL",
            "bodies": checks, "limitations": list(LIMITATIONS), "decision": "NOT_RELEASED"}
