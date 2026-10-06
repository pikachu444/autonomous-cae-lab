"""Checked bindings from research IDs to explicitly advertised model inputs.

The adapter declares scalar input names and implements their setters. Core
accepts neither native dictionary paths nor executable expressions from users.
Binding checks describe a declaration change, never physical qualification.
"""

from copy import deepcopy
import hashlib
import math
from pathlib import Path

from .contracts import Candidate, CapabilityUnavailable
from .storage import canonical_hash, core_source_hash, source_identity


ROOT = Path(__file__).resolve().parents[1]


class ModelInputRejected(ValueError):
    """An admitted assignment is rejected by the domain, before native work."""


def _finite(value):
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


def adapter_for(lab, backend):
    adapter = lab.model_analysis_adapters.get(backend)
    if adapter is None:
        raise CapabilityUnavailable(f"No executable model analysis adapter for {backend}")
    if not all(callable(getattr(adapter, name, None)) for name in
               ("describe_model", "describe_inputs", "bind_inputs")):
        raise CapabilityUnavailable(f"No declared parameter bindings for {backend}")
    if backend in lab.adapters:
        raise ValueError("Declared-input and CAD backends must have distinct identities")
    return adapter


def fingerprint(adapter):
    paths = getattr(adapter, "input_source_files", None)
    if not isinstance(paths, (list, tuple)) or not paths:
        raise ValueError("Declared bindings must advertise their source files")
    files = {}
    for item in paths:
        path = Path(item).resolve()
        if not path.is_relative_to(ROOT) or not path.is_file():
            raise ValueError("Binding source must be a file inside the project")
        key = path.relative_to(ROOT).as_posix()
        if key in files:
            raise ValueError("Binding source paths must be distinct")
        files[key] = hashlib.sha256(path.read_bytes()).hexdigest()
    runtime = getattr(adapter, "input_runtime_identity", None)
    if not callable(runtime):
        raise ValueError("Parameterized adapters must declare a callable runtime identity")
    runtime_identity = deepcopy(runtime())
    if not isinstance(runtime_identity, dict) or not runtime_identity:
        raise ValueError("Model runtime identity must be a nonempty mapping")
    identity = {"adapter": adapter.backend, "version": adapter.version,
                "source_files": files,
                "runtime": runtime_identity}
    canonical_hash(identity)
    return identity


def _inputs(adapter, settings):
    return _validated_inputs(adapter.describe_inputs(deepcopy(settings)))


def _validated_inputs(descriptors):
    descriptors = deepcopy(descriptors)
    if not isinstance(descriptors, list) or not 1 <= len(descriptors) <= 32:
        raise ValueError("Declared inputs must be a bounded nonempty list")
    names = set()
    for descriptor in descriptors:
        if (not isinstance(descriptor, dict) or
                set(descriptor) - {"settings_mirrors"} != {"id", "label", "unit", "value", "lower", "upper",
                                    "settings_path", "declaration_paths"} or
                not isinstance(descriptor["id"], str) or not descriptor["id"] or
                descriptor["id"] in names or
                any(not isinstance(descriptor[key], str) or not descriptor[key].strip()
                    for key in ("label", "unit")) or
                any(not _finite(descriptor[key]) for key in ("value", "lower", "upper")) or
                not descriptor["lower"] <= descriptor["value"] <= descriptor["upper"] or
                not descriptor["lower"] < descriptor["upper"]):
            raise ValueError("Malformed or duplicate declared scalar input")
        from .registry import ID
        if not ID.fullmatch(descriptor["id"]):
            raise ValueError("Declared input names must be stable identifiers")
        _path(descriptor["settings_path"])
        if 'settings_mirrors' in descriptor:
            mirrors = descriptor['settings_mirrors']
            if not isinstance(mirrors, list) or not 1 <= len(mirrors) <= 16:
                raise ValueError('Mirrored model settings require bounded trusted locations')
            for path in mirrors:
                _path(path)
        paths = descriptor["declaration_paths"]
        if not isinstance(paths, list) or not 1 <= len(paths) <= 16:
            raise ValueError("Model input requires bounded declaration locations")
        for path in paths:
            _path(path)
        names.add(descriptor["id"])
    for locations in ([path for item in descriptors for path in [item['settings_path'], *item.get('settings_mirrors', [])]],
                      [path for item in descriptors for path in item["declaration_paths"]]):
        for index, path in enumerate(locations):
            if any(path[:len(other)] == other or other[:len(path)] == path
                   for other in locations[:index]):
                raise ValueError("Input locations must not overlap or repeat")
    canonical_hash(descriptors)
    return descriptors


def _path(path):
    if (not isinstance(path, list) or not 1 <= len(path) <= 16 or
            any(not ((type(key) is str and key) or (type(key) is int and key >= 0))
                for key in path)):
        raise ValueError("Input locations require bounded typed mapping/list keys")


def _leaf(model, path):
    cursor = model
    for key in path[:-1]:
        cursor = _get(cursor, key)
    return cursor, path[-1], _get(cursor, path[-1])


def _get(cursor, key):
    if (type(cursor) is dict and type(key) is str and key in cursor or
            type(cursor) is list and type(key) is int and 0 <= key < len(cursor)):
        return cursor[key]
    raise ValueError("Declared input location does not exist with the stated type")


def _locations(descriptors, settings, model):
    for item in descriptors:
        locations = [(settings, path) for path in [item['settings_path'], *item.get('settings_mirrors', [])]] + [
                     *((model, path) for path in item["declaration_paths"])]
        for target, path in locations:
            _, _, value = _leaf(target, path)
            if not _finite(value) or value != item["value"]:
                raise ValueError("Input location must contain its actual finite scalar value")


def expected_settings(settings, descriptors, assignments):
    """Apply trusted, frozen locations independently of the adapter setter."""
    bound = deepcopy(settings)
    by_name = {item["id"]: item for item in descriptors}
    if (not isinstance(assignments, dict) or not assignments or
            any(name not in by_name or not _finite(value) or
                not by_name[name]["lower"] <= value <= by_name[name]["upper"]
                for name, value in assignments.items())):
        raise ValueError("Model assignments require advertised, finite, in-domain inputs")
    for name, value in assignments.items():
        for path in [by_name[name]['settings_path'], *by_name[name].get('settings_mirrors', [])]:
            target, key, old = _leaf(bound, path)
            if not _finite(old):
                raise ValueError("Input setting must be a finite scalar")
            target[key] = value
    canonical_hash(bound)
    return bound


def expected_declaration(model, descriptors, assignments):
    """Reconstruct selected declaration leaves without executing an adapter."""
    expected = deepcopy(model)
    by_name = {item["id"]: item for item in descriptors}
    for name, value in assignments.items():
        if (name not in by_name or not _finite(value) or
                not by_name[name]["lower"] <= value <= by_name[name]["upper"]):
            raise ValueError("Declaration assignments must be admitted finite inputs")
        for path in by_name[name]["declaration_paths"]:
            target, key, original = _leaf(expected, path)
            target[key] = float(value) if type(original) is float else value
    canonical_hash(expected)
    return expected


def declaration(adapter, settings):
    if not isinstance(settings, dict):
        raise ValueError("Model template settings must be a mapping")
    canonical_hash(settings)
    return _validated_declaration(adapter.describe_model(deepcopy(settings)))


def _validated_declaration(model):
    model = deepcopy(model)
    if not isinstance(model, dict) or not isinstance(model.get("model"), dict):
        raise ValueError("Parameterized models need a complete model declaration")
    canonical_hash(model)
    return model


def describe(lab, backend, settings):
    adapter = adapter_for(lab, backend)
    model = declaration(adapter, settings)
    identity = fingerprint(adapter)
    revision = canonical_hash({"settings": settings, "declaration": model})
    descriptors = _inputs(adapter, settings)
    _locations(descriptors, settings, model)
    source_hash = canonical_hash({"fingerprint": identity, "inputs": descriptors,
                                  "model_revision": revision})
    candidates = [Candidate(native={"backend": backend, "document": revision,
                                   "object": "declared_inputs", "path": item["id"], "alias": ""},
                            label=item["label"], unit=item["unit"], value=item["value"],
                            lower=item["lower"], upper=item["upper"], source_sha256=source_hash)
                  for item in descriptors]
    return {"adapter": adapter, "declaration": model, "revision": revision,
            "descriptors": descriptors, "fingerprint": identity, "candidates": candidates}


def bind(adapter, settings, assignments):
    """Compare the entire bound context to independently applied locations."""
    before = _inputs(adapter, settings)
    known = {item["id"]: item for item in before}
    expected = expected_settings(settings, before, assignments)
    baseline = declaration(adapter, settings)
    _locations(before, settings, baseline)
    expected_model = expected_declaration(baseline, before, assignments)
    try:
        bound = deepcopy(adapter.bind_inputs(deepcopy(settings), deepcopy(assignments)))
    except ValueError as exc:
        raise ModelInputRejected(str(exc)) from exc
    if not isinstance(bound, dict):
        raise ValueError("Model binding must return settings")
    if canonical_hash(bound) != canonical_hash(expected):
        raise ValueError("Model binding changed settings outside its declared locations")
    try:
        raw_after = adapter.describe_inputs(deepcopy(bound))
        raw_model = adapter.describe_model(deepcopy(bound))
    except ValueError as exc:
        raise ModelInputRejected(str(exc)) from exc
    # Returned adapter data is a contract, not a domain verdict. Malformed
    # descriptors/declarations stop execution instead of becoming search data.
    after = _validated_inputs(raw_after)
    bound_model = _validated_declaration(raw_model)
    if len(after) != len(before):
        raise ValueError("Model binding changed its advertised input set")
    # Sort only for comparison. A descriptor's order remains part of the frozen
    # template and numerical parameter order is owned by the optimizer plan.
    after_map = {item["id"]: item for item in after}
    for original in before:
        value = assignments.get(original["id"], original["value"])
        # An admitted continuous scalar may be serialized as an integer while
        # a descriptor reports floats. Normalize only this selected numeric
        # leaf; every other setting/descriptor retains canonical identity.
        if original["id"] in assignments and type(original["value"]) is float:
            value = float(value)
        expected = {**original, "value": value}
        if canonical_hash(after_map.get(original["id"])) != canonical_hash(expected):
            raise ValueError("Model binding changed another input or failed round-trip")
    if canonical_hash(bound_model) != canonical_hash(expected_model):
        raise ValueError("Model binding changed a frozen declaration outside selected inputs")
    return bound


def probe(adapter, settings, input_id, lower, upper):
    baseline = declaration(adapter, settings)
    variants = [bind(adapter, settings, {input_id: value}) for value in (lower, upper)]
    declarations = [declaration(adapter, item) for item in variants]
    hashes = [canonical_hash(item) for item in declarations]
    if hashes[0] == hashes[1]:
        raise ValueError("Advertised input has no distinct effect on the declared model")
    return {"status": "PASS", "method": "declared_input_round_trip",
            "scope": "Model declaration only; physical effect and qualification are UNKNOWN",
            "baseline_declaration_sha256": canonical_hash(baseline),
            "bound_settings_sha256": [canonical_hash(item) for item in variants],
            "bound_declaration_sha256": hashes}


def verify_current(lab, plan, snapshot):
    if core_source_hash(ROOT) != plan["core_source_sha256"]:
        raise ValueError("Core source changed since model optimization planning")
    if canonical_hash(lab.registry(plan["study_id"])) != plan["registry_sha256"]:
        raise ValueError("Study registry changed since model optimization planning")
    description = describe(lab, plan["backend"], plan["model_template"])
    if (description["fingerprint"] != plan["model_source_fingerprint"] or
            description["revision"] != plan["model_template_revision"] or
            description["descriptors"] != plan["model_input_descriptors"] or
            description["declaration"] != plan["model_declaration"]):
        raise ValueError("Model input source, runtime or declaration changed since planning")
    candidates = {item.native["path"]: item for item in description["candidates"]}
    for entry in snapshot["entries"]:
        if (entry.get("target") != "model_analysis" or entry["native"]["backend"] != plan["backend"] or
                entry["native"]["document"] != plan["model_template_revision"]):
            continue
        candidate = candidates.get(entry["native"]["path"])
        if (candidate is None or entry["native"] != candidate.native or
                entry["source_sha256"] != candidate.source_sha256 or
                entry.get("input_descriptor_sha256") != canonical_hash(description["descriptors"]) or
                entry.get("model_template_revision") != description["revision"]):
            raise ValueError("Registered model binding changed since planning")
