"""Solver-free selection of recorded native histories for direct workbench runs.

The input is the native adapter's own outcome and output directory, not a Lab
Study.  The old Study readers remain responsible for their existing contracts.
Only the two native history families admitted here are advertised.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path


_PDE = "pde.fenicsx.transient"
_EXPLICIT = "explicit.openradioss"
_EXPLICIT_CHANNELS = (
    ("radioss-center-z", "z_m", "m", "Z", "main node 9", "time_s", "position"),
    ("radioss-bottom-z", "bottom_z_m", "m", "Z", "secondary node 1", "time_s", "position"),
    ("radioss-center-vz", "velocity_m_s", "m/s", "Z", "main node 9", "velocity_time_s", "velocity"),
    ("radioss-bottom-vz", "bottom_velocity_m_s", "m/s", "Z", "secondary node 1", "velocity_time_s", "velocity"),
    ("radioss-center-az", "acceleration_m_s2", "m/s^2", "Z", "main node 9", "time_s", "acceleration"),
    ("radioss-kinetic", "kinetic_energy_j", "J", "scalar", "whole model", "time_s", "kinetic_energy"),
    ("radioss-internal", "internal_energy_j", "J", "scalar", "whole model", "time_s", "internal_energy"),
    ("radioss-external-work", "external_work_j", "J", "scalar", "whole model", "time_s", "external_work"),
    ("radioss-spring-fx", "spring_axial_force_n", "N", "local FX", "spring element 2", "time_s", "force"),
    ("radioss-ground-fz", "ground_force_n", "N", "global Z", "spring element 2 / moving body", "time_s", "force"),
    ("radioss-spring-lx", "spring_length_change_m", "m", "local X", "spring element 2", "time_s", "length_change"),
    ("radioss-spring-work", "spring_internal_energy_j", "J", "scalar", "spring element 2", "time_s", "internal_work"),
    ("radioss-wall-fnz", "ground_impulse_n_s", "N s", "FNZ", "rigid wall 1", "time_s", "impulse"),
)


def _need(condition, message):
    if not condition:
        raise ValueError(message)


def _json(output, relative, *, maximum=33554432, expected_hash=None):
    root = Path(output).resolve(strict=True)
    target = root / relative
    _need(not target.is_symlink() and target.resolve().is_relative_to(root) and target.is_file(),
          f"Native response source is missing or escapes output: {relative}")
    data = target.read_bytes()
    _need(0 < len(data) <= maximum, f"Native response source has invalid size: {relative}")
    digest = hashlib.sha256(data).hexdigest()
    _need(expected_hash is None or digest == expected_hash,
          f"Native response source hash changed: {relative}")
    value = json.loads(data)
    return value, digest


def _finite(values):
    return isinstance(values, list) and bool(values) and all(
        type(value) in (int, float) and math.isfinite(value) for value in values)


def _outcome(output, outcome, relative):
    saved, digest = _json(output, relative, maximum=1048576)
    _need(saved == outcome and outcome.get("solver_status") == "COMPLETED" and
          outcome.get("status") in {"COMPLETED", "REJECTED"},
          "Recorded native outcome and supplied outcome differ or solve did not complete")
    return digest


def _pde_context(outcome, output):
    _outcome(output, outcome, "result.json")
    raw, raw_hash = _json(output, "worker_result.json", maximum=16777216)
    input_settings, input_hash = _json(output, "input.json", maximum=1048576)
    _need(raw.get("schema_version") == "1" and raw.get("status") == "COMPLETED" and
          raw.get("spec_sha256") == input_hash == outcome.get("provenance", {}).get("spec_sha256") and
          raw.get("mpi_size") == 1 and raw.get("scalar_type") == "float64" and
          isinstance(raw.get("studies"), list) and raw["studies"] == outcome.get("time_studies"),
          "Transient native history has incomplete execution/input identity")
    from plugins.pde_transient import reference as domain
    _need(domain.validate_settings(input_settings) == input_settings and
          len(raw["studies"]) == len(domain.study_pairs(input_settings)),
          "Transient declared history and native study count differ")
    return raw, raw_hash, input_settings


def _pde_field(output, step):
    relative = step.get("files", {}).get("dofs")
    hashes = step.get("artifact_sha256", {})
    _need(isinstance(relative, str) and isinstance(hashes, dict) and
          isinstance(hashes.get("dofs"), str), "Transient native field reference is missing")
    field, digest = _json(output, relative, expected_hash=hashes["dofs"])
    from plugins.pde_transient.reference import value_sha256
    ids, values, coordinates = field.get("node_ids"), field.get("values"), field.get("coordinates")
    _need(isinstance(ids, list) and ids and len(ids) == len(set(ids)) and
          all(type(node) is int for node in ids) and _finite(values) and
          len(ids) == len(values) and isinstance(coordinates, list) and len(coordinates) == len(ids) and
          all(_finite(xy) and len(xy) == 2 for xy in coordinates) and
          field.get("field_unit") == "1" and field.get("coordinates_unit") == "1" and
          value_sha256(ids, values) == step.get("current_values_sha256"),
          "Transient native nodal values or identity differ from recorded step")
    return field, digest


def _pde_catalog(outcome, output):
    raw, raw_hash, settings = _pde_context(outcome, output)
    catalog = {}
    for index, study in enumerate(raw["studies"]):
        steps = study.get("steps")
        _need(study.get("study_index") == index and isinstance(steps, list) and len(steps) == study.get("step_count", -1) + 1,
              "Transient study history is incomplete")
        field, _ = _pde_field(output, steps[0])
        key = f"pde.study{index}.u"
        catalog[key] = {
            "kind": "series", "unit": "1", "component": "u", "location": "native node",
            "reduction": "none", "quantity": "scalar PDE solution",
            "axes": [{"name": "time", "unit": "1", "semantics": "DIMENSIONLESS_MODEL_TIME"}],
            "coordinate_frame": "dimensionless rectangle Cartesian", "node_ids": field["node_ids"],
            "coordinates": field["coordinates"], "selector_template": f"{key}@<node_id>",
            "source": {"backend": _PDE, "artifact": "worker_result.json", "sha256": raw_hash,
                       "settings_artifact": "input.json", "field_artifact_template":
                       f"study_{index}_n{study['cells_per_axis']}_N{study['step_count']}/step_<index>/dofs.json"},
            "model_conditions": {**settings,"cells_per_axis": study["cells_per_axis"], "step_count": study["step_count"],
                                 "time": settings["time"]},
        }
    return catalog


def _explicit_context(outcome, output):
    _outcome(output, outcome, "analysis_raw.json")
    settings, _ = _json(output, "input.json", maximum=1048576)
    raw, raw_hash = _json(output, "parsed_history.json")
    from .openradioss_worker import parse_history, expected_history_times
    from plugins.explicit_dynamics import reference as domain
    _need(domain.validate_settings(settings) == settings and
          outcome.get("raw_result") == "simulation/analysis_raw.json" and
          raw == parse_history(Path(output), settings, outcome.get('provenance')),
          "Retained OpenRadioss parsed history differs from original typed output")
    rows = raw.get("rows")
    expected_times = expected_history_times(settings)
    _need(isinstance(rows, list) and len(rows) == len(expected_times) and
          _finite([row.get("time_s") for row in rows]) and
          all(abs(row["time_s"] - t) <= 1e-8 * max(1, abs(t)) for row, t in zip(rows, expected_times)),
          "Retained OpenRadioss history does not cover declared clock")
    assessment = domain.assess(settings, rows)
    _need(assessment == outcome.get("assessment") and assessment.get("metrics") == outcome.get("metrics") and
          assessment.get("checks") == outcome.get("checks"),
          "Retained native history no longer agrees with recorded numerical assessment")
    return raw, raw_hash, settings


def _explicit_catalog(outcome, output):
    raw, digest, settings = _explicit_context(outcome, output)
    fields = set(raw["rows"][0])
    catalog = {}
    for name, field, unit, component, location, clock, quantity in _EXPLICIT_CHANNELS:
        if field not in fields:
            continue
        if field == "ground_impulse_n_s":
            # The wall reader defines RWALL/FNZ as cumulative impulse.  Keep
            # the native sign/quantity instead of changing it into force.
            continue
        catalog[name] = {"kind": "series", "unit": unit, "component": component,
                         "location": location, "reduction": "none", "quantity": quantity,
                         "axes": [{"name": "time", "unit": "s", "semantics":
                                   "NATIVE_HALF_STEP_VELOCITY_TIME" if clock == "velocity_time_s" else "NATIVE_CURRENT_TIME"}],
                         "coordinate_frame": "spring local Cartesian" if component.startswith('local') else "global Cartesian SI",
                         "coordinate_system": "spring local Cartesian" if component.startswith('local') else "global Cartesian SI",
                         "sensor_alignment": "UNKNOWN",
                         "source": {"backend": _EXPLICIT, "artifact": "parsed_history.json", "sha256": digest,
                                    "native_artifact": "dropT01", "native_field": field,
                                    "selector": name},
                         "model_conditions": dict(settings)}
    return catalog


def catalog_native_responses(backend, outcome, output):
    """Describe supported native channels without loading their full arrays."""
    if backend == _PDE:
        return _pde_catalog(outcome, output)
    if backend == _EXPLICIT:
        return _explicit_catalog(outcome, output)
    return {}


def read_native_response(backend, outcome, output, selector, *, start=None, stop=None):
    """Read one selected native response and a bounded half-open sample slice."""
    catalog = catalog_native_responses(backend, outcome, output)
    if backend == _PDE:
        name, separator, node_text = selector.partition("@")
        _need(separator and name in catalog and node_text.isdecimal(),
              f"Unknown native response selection {selector!r}; available: {list(catalog)}")
        node = int(node_text)
        _need(node in catalog[name]["node_ids"], f"Native node {node} is absent; available nodes: {catalog[name]['node_ids']}")
        raw, _, _ = _pde_context(outcome, output)
        study_index = int(name.split("study", 1)[1].split(".", 1)[0])
        steps = raw["studies"][study_index]["steps"]
        descriptor = {key: value for key, value in catalog[name].items() if key not in {"node_ids", "coordinates", "selector_template"}}
        coordinates=catalog[name]["coordinates"][catalog[name]["node_ids"].index(node)]
        descriptor["location"] = f"native node {node} at {coordinates}"
        descriptor["node_id"] = node
        descriptor["coordinates"] = coordinates
        descriptor["coordinate_unit"] = "1"
        descriptor["coordinate_system"] = catalog[name]["coordinate_frame"]
        values, times, sources = [], [], []
        for step in steps:
            field, digest = _pde_field(output, step)
            _need(node in field["node_ids"] and step.get("index") == len(values) and
                  type(step.get("time")) in (int, float) and math.isfinite(step["time"]),
                  "Transient selected native node/time is incomplete")
            position = field["node_ids"].index(node)
            _need(field["coordinates"][position] == descriptor["coordinates"],
                  "Transient native node moved between snapshots")
            values.append(field["values"][position])
            times.append(step["time"])
            sources.append({"artifact": step["files"]["dofs"], "sha256": digest})
        _need(all(right > left for left, right in zip(times, times[1:])), "Transient time axis is not increasing")
        descriptor["source"] = {**descriptor["source"], "selector": selector, "sample_artifacts": sources}
    elif backend == _EXPLICIT:
        _need(selector in catalog, f"Unknown native response selection {selector!r}; available: {list(catalog)}")
        descriptor = dict(catalog[selector])
        raw, _, _ = _explicit_context(outcome, output)
        field = descriptor["source"]["native_field"]
        clock = "velocity_time_s" if descriptor["axes"][0]["semantics"] == "NATIVE_HALF_STEP_VELOCITY_TIME" else "time_s"
        values = [row[field] for row in raw["rows"]]
        times = [row[clock] for row in raw["rows"]]
        _need(_finite(values) and _finite(times) and all(right > left for left, right in zip(times, times[1:])),
              "OpenRadioss selected native values/clock are invalid")
    else:
        raise ValueError(f"No native response reader for {backend}")
    _need(start is None or type(start) is int and start >= 0, "start must be a nonnegative sample index")
    _need(stop is None or type(stop) is int and stop >= 0, "stop must be a nonnegative sample index")
    begin, end = 0 if start is None else start, len(values) if stop is None else stop
    _need(begin < end <= len(values), "Selected native response slice is empty or outside the history")
    descriptor["value"] = values[begin:end]
    descriptor["axes"] = [{**descriptor["axes"][0], "values": times[begin:end]}]
    descriptor["source"] = {**descriptor["source"], "sample_slice": [begin, end]}
    return descriptor
