"""Adapter-owned identities/selectors; no FreeCAD, Core or geometry algorithms."""

import re


CONSTRAINT_TYPES = frozenset(("Distance", "DistanceX", "DistanceY", "Radius", "Diameter"))
SELECTOR_KIND = "caelab-constraint-v1"
_SHA = re.compile(r"[0-9a-f]{64}")


def unique_paths(items, duplicate_code="NATIVE_DUPLICATE_PATH"):
    """Reject ambiguity before any path-keyed mapping or bounds lookup."""
    seen = set()
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get("key"), str) or not item["key"]:
            raise ValueError("NATIVE_SELECTOR_INVALID: Invalid native CAD dimension path")
        if item["key"] in seen:
            raise ValueError(duplicate_code + ": Duplicate native CAD dimension path")
        seen.add(item["key"])


def raw_constraint_index(target):
    parts = target["key"].split("|")
    if (len(parts) != 3 or parts[:2] != [target["object"], "constraint"] or
            not parts[2].isascii() or not parts[2].isdecimal() or str(int(parts[2])) != parts[2]):
        raise ValueError("NATIVE_SELECTOR_INVALID: Invalid current Sketcher dimension path")
    return int(parts[2])


def opaque_constraint(target, source_sha256):
    if not isinstance(source_sha256, str) or not _SHA.fullmatch(source_sha256):
        raise ValueError("NATIVE_SOURCE_REVISION_INVALID: Invalid native CAD source revision")
    return f'{target["object"]}|{SELECTOR_KIND}|{source_sha256}|{raw_constraint_index(target)}'


def registered_targets(doc, registry, targets, datum):
    """Resolve every registered definition to one actual supported target.

    Stable names survive index shifts. A same-name replacement cannot be
    distinguished from the original constraint by these upstream definitions.
    """
    if not isinstance(registry, dict) or not isinstance(registry.get("parameters"), list):
        raise ValueError("NATIVE_REGISTRY_INVALID: Invalid FCStd parameter definitions")
    unique_paths(targets)
    entries = registry["parameters"]
    unique_paths(entries, "NATIVE_DUPLICATE_KEY")
    names, identities, resolved = set(), set(), []
    for entry in entries:
        name, object_name, kind = entry.get("name"), entry.get("object"), entry.get("kind")
        if not isinstance(name, str) or not name or name in names or not isinstance(object_name, str):
            raise ValueError("NATIVE_DUPLICATE_PARAMETER_NAME: Duplicate or invalid registered CAD parameter name")
        names.add(name)
        obj = doc.getObject(object_name)
        if obj is None:
            raise ValueError("NATIVE_REGISTERED_DIMENSION_MISSING: A registered CAD feature was deleted")
        if kind == "property":
            prop = entry.get("property")
            if not isinstance(prop, str) or prop not in obj.PropertiesList:
                raise ValueError("NATIVE_REGISTERED_DIMENSION_MISSING: The registered CAD property was deleted")
            if obj.getTypeIdOfProperty(prop) not in ("App::PropertyLength", "App::PropertyDistance"):
                raise ValueError("NATIVE_REGISTERED_UNSUPPORTED: The registered CAD property no longer has a supported length unit")
            identity, raw_key = (object_name, kind, prop), f"{object_name}|property|{prop}"
            expected_datum = prop
        elif kind == "constraint":
            constraint = entry.get("constraint")
            if not isinstance(constraint, str) or not constraint or "constraint_index" in entry or obj.TypeId != "Sketcher::SketchObject":
                raise ValueError("NATIVE_REGISTERED_UNSUPPORTED: A registered Sketcher dimension requires its stable constraint name")
            matches = [(i, value) for i, value in enumerate(obj.Constraints) if value.Name == constraint]
            if not matches:
                raise ValueError("NATIVE_REGISTERED_DIMENSION_MISSING: The registered Sketcher constraint name was deleted or renamed")
            if len(matches) != 1:
                raise ValueError("NATIVE_DUPLICATE_IDENTITY: The registered Sketcher constraint name is ambiguous")
            index, value = matches[0]
            if value.Type not in CONSTRAINT_TYPES:
                raise ValueError("NATIVE_REGISTERED_UNSUPPORTED: The registered Sketcher dimension type is unsupported")
            if not obj.getDriving(index):
                raise ValueError("NATIVE_REGISTERED_NOT_DRIVING: The registered Sketcher dimension is not driving")
            identity, raw_key = (object_name, kind, constraint), f"{object_name}|constraint|{index}"
            expected_datum = index
        else:
            raise ValueError("NATIVE_REGISTERED_UNSUPPORTED: Unsupported registered CAD dimension kind")
        if identity in identities:
            raise ValueError("NATIVE_DUPLICATE_IDENTITY: Duplicate registered CAD dimension identity")
        identities.add(identity)
        matches = [target for target in targets if target["key"] == raw_key]
        if len(matches) != 1 or matches[0].get("object") != object_name or matches[0].get("kind") != kind:
            raise ValueError("NATIVE_REGISTERED_DIMENSION_MISSING: The registered CAD dimension is not a current supported target")
        actual_object, actual_datum = datum(doc, entry)
        if actual_object is not obj or actual_datum != expected_datum:
            raise ValueError("NATIVE_DUPLICATE_IDENTITY: The registered CAD dimension resolved ambiguously")
        resolved.append((entry, matches[0]))
    return resolved


def discovery_candidates(targets, resolved, source_sha256):
    used = {target["key"] for _, target in resolved}
    candidates = []
    for target in targets:
        if target["key"] in used:
            continue
        candidate = dict(target)
        if candidate["kind"] == "constraint":
            candidate["key"] = opaque_constraint(candidate, source_sha256)
        candidates.append(candidate)
    unique_paths([*candidates, *(entry for entry, _ in resolved)])
    return candidates


def resolve_selection(target, source_sha256, expected_sha256, targets, resolved):
    """Exact registry keys take precedence over historical selector revisions."""
    for entry, actual in resolved:
        if entry["key"] == target:
            return actual, entry
    if expected_sha256 != source_sha256:
        raise ValueError("NATIVE_SELECTOR_STALE: Native CAD selector is stale; rediscover the current document")
    if not isinstance(target, str):
        raise ValueError("NATIVE_SELECTOR_INVALID: Invalid native CAD selector")
    parts = target.split("|")
    if len(parts) == 4 and parts[1] == SELECTOR_KIND:
        if (not _SHA.fullmatch(parts[2]) or parts[2] != source_sha256 or not parts[3].isascii() or
                not parts[3].isdecimal() or str(int(parts[3])) != parts[3]):
            raise ValueError("NATIVE_SELECTOR_STALE: Native Sketcher selector is stale or invalid; rediscover the current document")
        raw_key = f"{parts[0]}|constraint|{parts[3]}"
    elif len(parts) == 3 and parts[1] == "property":
        raw_key = target
    else:
        raise ValueError("NATIVE_SELECTOR_REDISCOVERY_REQUIRED: Unregistered positional Sketcher selectors require rediscovery")
    matches = [candidate for candidate in targets if candidate["key"] == raw_key]
    if len(matches) != 1:
        raise ValueError("NATIVE_SELECTOR_MISSING: The selected CAD dimension is missing or is not driving")
    if any(actual["key"] == raw_key for _, actual in resolved):
        raise ValueError("NATIVE_SELECTOR_ALREADY_REGISTERED: The selected CAD dimension is already registered under its exact key")
    return matches[0], None
