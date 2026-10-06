"""Verified retained response channels; no interpolation or numerical inference."""

import hashlib
import json

from .response_comparison import _path, _source
from .storage import check_id


def _read_native(lab, result, relative, *, maximum_bytes=33554432):
    entries = [a for a in result["artifacts"] if a["path"] == relative]
    if len(entries) != 1:
        raise ValueError("Native history must have exactly one recorded artifact")
    entry = entries[0]
    path = _path(lab, f"experiments/{result['experiment_id']}/{relative}")
    if (type(maximum_bytes) is not int or not 0 < maximum_bytes <= 536870912
            or type(entry["size_bytes"]) is not int or not 0 < entry["size_bytes"] <= maximum_bytes):
        raise ValueError("Retained history exceeds the declared native JSON bound")
    if path.stat().st_size != entry["size_bytes"]:
        raise ValueError("Native history size mismatch")
    payload = path.read_bytes()
    if len(payload) != entry["size_bytes"] or hashlib.sha256(payload).hexdigest() != entry["sha256"]:
        raise ValueError("Native history artifact hash mismatch")

    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError("Duplicate native history JSON key")
            value[key] = item
        return value

    def invalid(value):
        raise ValueError("Nonfinite native history JSON constant: " + value)

    raw = json.loads(payload.decode('utf-8'), parse_constant=invalid, object_pairs_hook=unique)
    if not isinstance(raw, dict):
        raise ValueError("Native history must be a JSON object")
    return raw, entry


def source_channels(lab, result, proposal):
    channels = []
    if result["provenance"]["adapter"] == "material.mfront.viscoelastic":
        from .adapters.mfront_history import channels as maxwell_channels
        relative = result["provenance"].get("adapter_details", {}).get("actual_native_raw")
        if relative != "simulation/native_raw.json":
            raise ValueError("Retained Maxwell native artifact identity is unsupported")
        raw, entry = _read_native(lab, result, relative)
        channels = maxwell_channels(result, proposal["execution"], raw, entry)
    else:
        reader = getattr(lab, "response_history_adapters", {}).get(result["provenance"]["adapter"])
        resources_hook = getattr(reader, "history_response_resources", None)
        channels_hook = getattr(reader, "response_history_channels", None)
        if callable(resources_hook) and callable(channels_hook):
            policy = resources_hook(result)
            if type(policy) is not dict or not 0 < len(policy) <= 8:
                raise ValueError("History adapter resources must have a bounded explicit contract")
            resources = {}
            for role, spec in policy.items():
                if type(role) is not str or type(spec) is not dict or set(spec) != {"path", "maximum_bytes"}:
                    raise ValueError("History adapter resource declaration differs")
                resources[role] = _read_native(lab, result, spec["path"], maximum_bytes=spec["maximum_bytes"])
            channels = channels_hook(result, proposal, resources)
    return channels


def history_catalog(lab, experiment_id):
    identifier = check_id(experiment_id)
    result, proposal, hashes = _source(lab, identifier)
    channels = source_channels(lab, result, proposal)
    _, _, again = _source(lab, identifier)
    if again != hashes:
        raise ValueError("History source changed during inspection")
    reader = getattr(lab, "response_history_adapters", {}).get(result["provenance"]["adapter"])
    limitations = ["Exact recorded samples; no interpolation, resampling or unit conversion"]
    if result["provenance"]["adapter"] == "material.mfront.viscoelastic":
        limitations.extend(["t=0 is an unprepared numerical initial condition, not integrated material evidence",
                            "Material point, not a spatial assembly; physical qualification remains UNKNOWN"])
    else:
        limitations.extend(getattr(reader, "history_limitations", []))
    return {"schema_version": "1.0", "integrity": "VERIFIED", "experiment_id": identifier,
            "study_id": result["study"]["id"], "result_sha256": hashes["result_sha256"],
            "channels": channels,
            "limitations": limitations}
