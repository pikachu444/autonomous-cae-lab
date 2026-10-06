"""Scalar scenarios on one saved native CAD/condition declaration.

The caller verifies the revision-owned catalog and freezes these descriptors.
Bounds are finite numerical exploration ranges, not qualified engineering
limits. This module neither rebinds faces nor executes CAD, mesh or solvers.
Changed values are ASSUMED numerical scenarios; physical qualification remains
UNKNOWN. Core still owns records, source identities and execution admission.
"""

from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import sys

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

from .conditions import validate_declaration
from . import native_conditions


SCHEMA_PATH = (Path(__file__).resolve().parents[2] / "schemas" /
               "analysis-conditions-request.schema.json")
_MAX_FLOAT = sys.float_info.max
_MIN_POSITIVE = math.nextafter(0.0, 1.0)
_NU_BOUNDS = (math.nextafter(-1.0, 0.0), math.nextafter(0.5, 0.0))
_SCENARIO = "ASSUMED numerical scenario; qualification UNKNOWN."
_FORCE_DISPLACEMENT = {"FX": "UX", "FY": "UY", "FZ": "UZ"}


def _finite(value):
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


def _validate_contract(declaration):
    # Reuse the common typed declaration, including source and unit limits,
    # without importing Core or creating a fictitious condition record.
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    declaration_schema = {"$schema": schema["$schema"], "$defs": schema["$defs"],
                          **schema["properties"]["declaration"]}
    try:
        Draft202012Validator(declaration_schema).validate(declaration)
    except ValidationError as exc:
        raise ValueError(f"Native condition declaration contract: {exc.message}") from exc


def _admit(catalog, declaration):
    _validate_contract(declaration)
    validate_declaration(catalog, declaration)
    verdict = native_conditions.support(catalog, declaration)
    if verdict["status"] != "SUPPORTED_DECLARED_INPUTS":
        raise ValueError("Native condition inputs unavailable: " + "; ".join(verdict["reasons"]))
    for load in declaration["loads"]:
        for component, value in load["components"].items():
            if value != 0 and not _force_axis_supported(catalog, declaration, load, component):
                raise ValueError(f"Native condition input {load['id']}/{component}: the load face is not "
                                 "verified separated from faces constraining the same displacement DOF; "
                                 "this scalar scenario is unsupported before native execution")


def _bounds(face):
    bounds = face.get("bounds_mm")
    if (type(bounds) is not dict or set(bounds) != {"min", "max"} or
            any(type(bounds[key]) is not list or len(bounds[key]) != 3 or
                any(not _finite(value) for value in bounds[key]) for key in ("min", "max")) or
            any(low > high for low, high in zip(bounds["min"], bounds["max"]))):
        return None
    return bounds


def _force_axis_supported(catalog, declaration, load, component):
    """Conservative pre-mesh separation, never a face-intersection proof.

    Adjacent/overlapping or missing bounds cannot establish disjoint nodal
    support. Keep those scalar directions unavailable rather than executing
    a known unsupported force/constraint combination and stopping a campaign.
    The native deck still checks actual integrated forces against every DOF.
    """
    faces = {item["id"]: item for item in catalog["selections"]}
    for boundary in declaration["boundary_conditions"]:
        if _FORCE_DISPLACEMENT[component] not in boundary["components"]:
            continue
        first = _bounds(faces[load["selection_id"]])
        second = _bounds(faces[boundary["selection_id"]])
        if first is None or second is None:
            return False
        # Same conservative length/relative margins as the retained catalog.
        # An overlap does not assert actual contact or a shared native node.
        scale = max(1.0, *(abs(value) for box in (first, second) for edge in box.values() for value in edge))
        margin = 1e-7 + 1e-8 * scale
        if not any(first["max"][axis] + margin < second["min"][axis] or
                   second["max"][axis] + margin < first["min"][axis] for axis in range(3)):
            return False
    return True


def _identifier(group, item_id, component):
    name = f"{group}_{item_id}_{component}"
    if len(name) <= 64:
        return name
    # Declaration IDs can be longer than registry IDs. Preserve an explicit
    # readable prefix and an identity-dependent suffix instead of truncating
    # two different native declaration items to the same research ID.
    digest = hashlib.sha256(item_id.encode("ascii")).hexdigest()[:24]
    available = 64 - len(group) - len(component) - len(digest) - 3
    return f"{group}_{item_id[:available]}_{digest}_{component}"


def _descriptor(group, item, component, label, unit, value, bounds, path):
    lower, upper = bounds
    if (any(not _finite(number) for number in (value, lower, upper)) or
            not lower <= value <= upper or not lower < upper or
            not math.isfinite(upper - lower)):
        raise ValueError("Scalar input needs finite numerical bounds containing its value")
    return {"id": _identifier(group, item["id"], component),
            "label": f"{label} ({item['id']}; numerical bounds; qualification UNKNOWN)",
            "unit": unit, "value": value, "lower": lower, "upper": upper,
            "declaration_path": path}


def describe(catalog, declaration):
    """Advertise E/nu and already declared force components for this template.

    IDs depend on declaration item identities; paths are trusted output only.
    Bounds around the baseline must be frozen by the campaign, not recomputed
    from each candidate. All values remain user-declared and unqualified.
    """
    _admit(catalog, declaration)
    material = declaration["materials"][0]
    modulus = material["young_modulus_MPa"]
    bounds = (max(_MIN_POSITIVE, modulus / 10.0), min(_MAX_FLOAT, modulus * 10.0))
    inputs = [
        _descriptor("material", material, "E", "Young modulus E", "MPa", modulus,
                    bounds, ["materials", 0, "young_modulus_MPa"]),
        _descriptor("material", material, "nu", "Poisson ratio nu", "1", material["poisson_ratio"],
                    _NU_BOUNDS, ["materials", 0, "poisson_ratio"]),
    ]
    for index, load in enumerate(declaration["loads"]):
        scale = max(1.0, *(abs(value) for value in load["components"].values()))
        extent = min(_MAX_FLOAT / 4.0, scale * 10.0)
        for component in ("FX", "FY", "FZ"):
            # The current common schema explicitly requires XYZ. Keep this
            # guard so future partial-vector schemas cannot invent a DOF.
            if component not in load["components"]:
                continue
            if not _force_axis_supported(catalog, declaration, load, component):
                continue
            value = load["components"][component]
            bounds = ((value / 10.0, _MAX_FLOAT) if value > extent else
                      (-_MAX_FLOAT, value / 10.0) if value < -extent else (-extent, extent))
            inputs.append(_descriptor("load", load, component, f"Global resultant {component}",
                                      "N", value, bounds, ["loads", index, "components", component]))
    if len({item["id"] for item in inputs}) != len(inputs):
        raise ValueError("Ambiguous advertised native condition input identity")
    return inputs


def apply(catalog, declaration, assignments):
    """Return a new admitted declaration; only advertised scalar IDs are writable.

    Sources of actually changed items become explicit assumed scenarios while
    retaining their original category/text. Oversized source descriptions are
    refused by the existing schema rather than truncated. Signed components,
    unspecified displacement DOFs and every other condition stay unchanged.
    """
    descriptors = {item["id"]: item for item in describe(catalog, declaration)}
    if (type(assignments) is not dict or not assignments or
            any(type(name) is not str or name not in descriptors or not _finite(value) or
                not descriptors[name]["lower"] <= value <= descriptors[name]["upper"]
                for name, value in assignments.items())):
        raise ValueError("Assignments require advertised scalar IDs, finite values and numerical bounds")
    bound = deepcopy(declaration)
    changed_materials, changed_loads = set(), set()
    for name, value in assignments.items():
        path = descriptors[name]["declaration_path"]
        target = bound
        for key in path[:-1]:
            target = target[key]
        if value != target[path[-1]]:
            target[path[-1]] = value
            (changed_materials if path[0] == "materials" else changed_loads).add(path[1])
    for index in changed_materials:
        original = declaration["materials"][index]["source"]
        bound["materials"][index]["source"] = {
            "category": "ASSUMED",
            "description": (f"{_SCENARIO} Original source ({original['category']}): "
                            f"{original['description']}"),
        }
    for index in changed_loads:
        original = declaration["loads"][index]["source"]
        bound["loads"][index]["source"] = f"{_SCENARIO} Original declared source: {original}"
    _validate_contract(bound)
    # Reuse the actual Domain projection, including zero-force/contact/frame
    # refusals, before Core can create any native execution for the candidate.
    native_conditions.project(catalog, bound)
    return bound
