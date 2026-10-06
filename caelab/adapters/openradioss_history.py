"""Read-only TH40 history projection for the existing admitted rigid-body cases.

Core verifies retained files before/after reading; this adapter binds parsed
values to the retained raw typed samples. No native process, curve fitting,
reference substitution, implicit unit conversion or execution admission.
"""

from copy import deepcopy
import math
import re

from plugins.explicit_dynamics import reference as domain

validate_settings = domain.validate_settings
COMPLIANT_CASE = domain.COMPLIANT_CASE


BACKEND = "explicit.openradioss"
PATH = "simulation/parsed_history.json"
FRAME = "global Cartesian SI; sensor/world alignment UNKNOWN"
RESOURCE_POLICY = {
    "history": {"path": PATH, "maximum_bytes": 33554432},
    "input": {"path": "simulation/input.json", "maximum_bytes": 1048576},
    "outcome": {"path": "simulation/analysis_raw.json", "maximum_bytes": 1048576},
}
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
LIMITATIONS = [
    "Recorded SI rigid-body histories; no deformable surface/body contact capability is implied",
    "Raw TH/NODE velocity uses TIME-DT/2, except the initial sample; position/energy use TIME",
    "RWALL FNZ is cumulative signed wall impulse in N s, never instantaneous force",
    "Native spring IE is signed work and is not clamped or replaced by reference energy",
    "Selected acceleration histories retain native observations; reference agreement and time-step sensitivity remain UNKNOWN",
    "Physical model/material/contact/measurement alignment remain UNKNOWN; NOT_RELEASED",
]


def _producer(provenance, settings):
    # Original version-1 flight/wall records precede the version-1.1 spring
    # extension. They share the explicit TH40 raw/parsed contract checked below.
    if type(provenance) is not dict or type(settings) is not dict or provenance.get("adapter") != BACKEND:
        return False
    version, case = provenance.get("adapter_version"), settings.get("case")
    if "mode" in settings:
        return (version == "1.2" and settings["mode"] == "selected_history"
                and case in ("rigid_cube_freefall", COMPLIANT_CASE))
    return ((version in ("1.1", "1.2") and case in
             ("rigid_cube_freefall", "rigid_cube_ground_stop", COMPLIANT_CASE)) or
            (version == "1" and case in ("rigid_cube_freefall", "rigid_cube_ground_stop")))


def _need(condition, message):
    if not condition:
        raise ValueError(message)


def _finite(value):
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


def _vector(value, length):
    _need(type(value) is list and len(value) == length and all(_finite(v) for v in value),
          "Retained OpenRadioss history requires exact finite native array dimensions")
    return value


def _resources(result, resources):
    """Join the Core-verified JSON tuples to their exact bounded manifest entries."""
    _need(type(resources) is dict and set(resources) == set(RESOURCE_POLICY),
          "OpenRadioss history requires exact retained history/input/outcome resources")
    manifest = result["artifacts"]
    _need(type(manifest) is list and all(type(item) is dict for item in manifest),
          "Retained OpenRadioss artifacts require a typed manifest")
    values = {}
    for role, policy in RESOURCE_POLICY.items():
        pair = resources[role]
        _need(type(pair) in (tuple, list) and len(pair) == 2, "Malformed retained history resource tuple")
        raw, entry = pair
        _need(type(raw) is dict and type(entry) is dict
              and [item for item in manifest if item.get("path") == policy["path"]] == [entry]
              and type(entry.get("sha256")) is str and SHA256.fullmatch(entry["sha256"])
              and type(entry.get("size_bytes")) is int
              and 0 < entry["size_bytes"] <= policy["maximum_bytes"],
              "History resource path/hash/size differs from its exact bounded manifest")
        values[role] = pair
    return values


class OpenRadiossHistoryAdapter:
    backend = BACKEND
    history_limitations = LIMITATIONS

    @staticmethod
    def history_response_resources(result):
        p = result.get("provenance", {})
        _need(_producer(p, p.get("execution_settings", {})),
              "Unsupported retained OpenRadioss producer version")
        return deepcopy(RESOURCE_POLICY)

    @staticmethod
    def response_history_channels(result, proposal, resources):
        try:
            return _channels(result, proposal, resources)
        except (KeyError, IndexError, TypeError, AttributeError, OverflowError) as exc:
            raise ValueError("Incomplete retained OpenRadioss history contract") from exc


def _channels(result, proposal, resources):
    resources = _resources(result, resources)
    raw, entry = resources["history"]
    settings, _ = resources["input"]
    outcome, _ = resources["outcome"]
    _need(result["status"] == "COMPLETED_REVIEW_REQUIRED" and result["solver_status"] == "COMPLETED"
          and result["converged"] is True and result["decision"] == "NOT_RELEASED"
          and proposal["physics"]["backend"] == result["provenance"]["adapter"] == BACKEND
          and _producer(result["provenance"], settings)
          and proposal["id"] == result["experiment_id"] and proposal["study_id"] == result["study"]["id"]
          and proposal["execution"] == result["provenance"]["execution_settings"] == settings
          and validate_settings(settings) == settings,
          "Same completed unreleased OpenRadioss model/settings/result are required")
    _need(outcome["status"] == "COMPLETED" and outcome["solver_status"] == "COMPLETED"
          and outcome["converged"] is True and outcome["metrics"] == result["metrics"]
          and outcome.get("raw_result") == RESOURCE_POLICY["outcome"]["path"]
          and outcome.get("provenance") == result["provenance"].get("adapter_details")
          and type(outcome["checks"]) is list and outcome["checks"]
          and all(c["status"] == "PASS" for c in outcome["checks"]),
          "Retained native assessment must agree with the successful result")
    manifest = result["artifacts"]
    history_entries = [a for a in manifest if a["path"] == PATH]
    native_entries = [a for a in manifest if a["path"] == "simulation/dropT01"]
    _need(history_entries == [entry] and len(native_entries) == 1
          and raw["format"] == "OpenRadioss TH40 ASCII typed records"
          and raw["units"] == "kg,m,s,N,J; raw cumulative RWALL impulse N s"
          and raw["global_variable_ids"] == list(range(1, 23))
          and all(type(v) is int for v in raw["global_variable_ids"]),
          "Exact retained TH40 history/raw source/unit declarations are required")
    native_entry = native_entries[0]
    _need(type(native_entry.get("sha256")) is str and SHA256.fullmatch(native_entry["sha256"])
          and type(native_entry.get("size_bytes")) is int and native_entry["size_bytes"] > 0,
          "Original TH40 raw artifact requires its recorded byte/hash identity")
    compliant = settings["case"] == COMPLIANT_CASE
    wall = settings["case"] == "rigid_cube_ground_stop"
    _need(raw["hierarchy"] == ([2, 2, 2, 1, 3, 22] if compliant else [1, 2, 1, 1, 3 if wall else 2, 22]),
          "Retained native history hierarchy differs from its model")
    _need(all(type(v) is int for v in raw["hierarchy"]), "Native hierarchy requires exact integer identifiers")
    expected = {1: (0, [1, 9, 10, 11] if compliant else [1, 9], [3, 6, 9, 18]),
                2: (103, [1], [3, 7, 8, 9])}
    if compliant:
        expected[4] = (6, [2], [1, 2, 3, 4, 5, 6, 7, 8, 14])
    if wall:
        expected[3] = (102, [1], [3])
    groups = raw["groups"]
    _need(type(groups) is list and len(groups) == len(expected), "Complete native selected group coverage required")
    seen = set()
    for group in groups:
        key = group["id"]
        _need(type(key) is int and key in expected and key not in seen, "Duplicate/unsupported native history group")
        seen.add(key)
        kind, entities, variables = expected[key]
        _need(type(group["type"]) is int and group["type"] == kind and group["entities"] == entities
              and all(type(v) is int for v in group["entities"] + group["variables"])
              and group["variables"] == variables and type(group["width"]) is int
              and group["width"] == len(entities) * len(variables), "Native entity/variable order changed")
    rows, samples = raw["rows"], raw["raw_samples"]
    _need(type(rows) is list and 2 <= len(rows) <= 20000 and type(samples) is list and len(samples) == len(rows),
          "Complete bounded raw and parsed native samples required")
    times = _vector([r["time_s"] for r in rows], len(rows))
    velocity_times = _vector([r["velocity_time_s"] for r in rows], len(rows))
    from .openradioss_worker import expected_history_times
    expected_times = expected_history_times(settings)
    _need(len(times) == len(expected_times) and all(abs(t - e) <= 1e-8 * max(1, abs(e)) for t, e in zip(times, expected_times))
          and _finite(raw["native_end_time_s"]) and abs(raw["native_end_time_s"] - settings["end_time_s"]) <= 1e-8
          and type(raw["native_cycle_count"]) is int and raw["native_cycle_count"] > 0,
          "Retained native history must cover the exact declared record schedule/end time")
    _need(times[0] == 0 and all(b > a for a, b in zip(times, times[1:]))
          and all(b > a for a, b in zip(velocity_times, velocity_times[1:])), "Native history clocks must increase strictly")
    for row, sample in zip(rows, samples):
        glob = _vector(sample["globals"], 22)
        vectors = sample["groups"]
        _need(type(vectors) is list and len(vectors) == len(groups) and _finite(sample["time_s"])
              and sample["time_s"] == row["time_s"], "Native raw/parsed history clocks differ")
        by_id = {g["id"]: _vector(v, g["width"]) for g, v in zip(groups, vectors)}
        node = by_id[1]
        bindings = {"z_m": node[7], "velocity_m_s": node[5], "acceleration_m_s2": node[6],
                    "bottom_z_m": node[3], "bottom_velocity_m_s": node[1], "bottom_acceleration_m_s2": node[2],
                    "kinetic_energy_j": glob[1], "internal_energy_j": glob[0], "external_work_j": glob[8],
                    "mass_kg": glob[5], "time_step_s": glob[6], "added_mass_kg": glob[16]}
        _need(all(_finite(row[k]) and row[k] == v for k, v in bindings.items())
              and glob[6] > 0 and abs(glob[6] - settings["time_step_s"]) <= 1e-10 * settings["time_step_s"]
              and row["velocity_time_s"] == max(0, row["time_s"] - .5 * glob[6]),
              "Retained position/velocity/energy/half-step clock differs from raw TH samples")
        if compliant:
            spring = by_id[4]
            _need(all(_finite(row[k]) for k in ("spring_axial_force_n", "ground_force_n", "spring_length_change_m", "spring_internal_energy_j"))
                  and row["spring_axial_force_n"] == spring[1] and row["ground_force_n"] == -spring[1]
                  and row["spring_length_change_m"] == spring[7] and row["spring_internal_energy_j"] == spring[8],
                  "Signed native spring force/length/work differs from raw TH samples")
        if wall:
            _need(row["ground_impulse_n_s"] == -by_id[3][0], "Native cumulative wall impulse sign changed")

    if settings.get("mode") == "selected_history":
        # Reuse the Domain's recorded-observation verdict; selected inputs do
        # not inherit the older ballistic/compliant reference qualification.
        assessed = domain.assess(settings, rows)
        _need(type(result.get("model_revision")) is str and SHA256.fullmatch(result["model_revision"])
              and proposal.get("model_revision") == result["model_revision"]
              and outcome.get("mode") == settings["mode"]
              and outcome.get("input_provenance") == settings["input_provenance"]
              and outcome["provenance"].get("mode") == settings["mode"]
              and outcome["provenance"].get("input_provenance") == settings["input_provenance"]
              and outcome["checks"] == assessed["checks"] and outcome["metrics"] == assessed["metrics"]
              and outcome.get("pending_validations") == assessed["pending_validations"]
              and assessed.get("reference") is None,
              "Selected native assessment/unknown reference differs from retained observations")
        if "assessment" in outcome:
            _need(outcome["assessment"] == assessed, "Selected retained Domain assessment differs")

    channels = []

    def add(identifier, label, field, quantity, component, measure, unit, location, *, clock="time_s",
            kind="NATIVE", raw_field=None, values=None, mapping="EXACT_RETAINED_TH40_SAMPLE"):
        values = _vector(values if values is not None else [r[field] for r in rows], len(rows))
        channels.append({"id": identifier, "label": label, "metric": None,
            "quantity": quantity, "component": component, "measure": measure, "unit": unit,
            "coordinate_frame": FRAME, "location": location,
            "axis": {"quantity": "time", "unit": "s", "values": list(velocity_times if clock == "velocity_time_s" else times),
                     "semantics": "NATIVE_HALF_STEP_VELOCITY_TIME" if clock == "velocity_time_s" else "NATIVE_CURRENT_TIME"},
            "values": list(values), "initial_state": {"index": 0, "kind": "NATIVE_DECLARED_INITIAL_STATE"},
            "origin": {"kind": kind, "driver": "openradioss", "artifact": PATH, "sha256": entry["sha256"],
                "native_artifact": native_entry["path"], "native_sha256": native_entry["sha256"],
                "native_field": raw_field or field, "mapping": mapping}})

    for identifier, label, field, quantity, component, measure, unit, location, clock in (
        ("radioss-center-z", "질량 중심 Z 위치", "z_m", "position", "Z", "native position", "m", "main node 9", "time_s"),
        ("radioss-bottom-z", "바닥 절점 Z 위치", "bottom_z_m", "position", "Z", "native position", "m", "secondary node 1", "time_s"),
        ("radioss-center-vz", "질량 중심 Z 속도", "velocity_m_s", "velocity", "Z", "raw leapfrog velocity", "m/s", "main node 9", "velocity_time_s"),
        ("radioss-bottom-vz", "바닥 절점 Z 속도", "bottom_velocity_m_s", "velocity", "Z", "raw leapfrog velocity", "m/s", "secondary node 1", "velocity_time_s"),
        ("radioss-center-az", "질량 중심 Z 가속도", "acceleration_m_s2", "acceleration", "Z", "native acceleration", "m/s^2", "main node 9", "time_s"),
        ("radioss-kinetic", "전체 운동 에너지", "kinetic_energy_j", "kinetic_energy", "scalar", "native global energy", "J", "whole admitted model", "time_s"),
        ("radioss-internal", "전체 내부 에너지", "internal_energy_j", "internal_energy", "scalar", "signed native global energy", "J", "whole admitted model", "time_s"),
        ("radioss-external-work", "전체 외력 일", "external_work_j", "external_work", "scalar", "native global work", "J", "whole admitted model", "time_s"),
    ):
        add(identifier, label, field, quantity, component, measure, unit, location, clock=clock)
    if compliant:
        add("radioss-spring-fx", "접촉 스프링 축력 FX", "spring_axial_force_n", "force", "local FX",
            "signed native spring axial force", "N", "spring element 2")
        add("radioss-ground-fz", "모델에 작용한 위쪽 접촉력", "ground_force_n", "force", "global Z",
            "native spring axial force with explicit sign mapping", "N", "spring element 2 / moving body",
            kind="DERIVED", raw_field="spring_axial_force_n", mapping="GLOBAL_UPWARD_FORCE_EQUALS_MINUS_LOCAL_FX")
        add("radioss-spring-lx", "접촉 스프링 길이 변화", "spring_length_change_m", "length_change", "local X",
            "native spring length change", "m", "spring element 2")
        add("radioss-spring-work", "접촉 스프링 내부 일", "spring_internal_energy_j", "internal_work", "scalar",
            "signed native trapezoidal constitutive work", "J", "spring element 2")
    if wall:
        wall_index = next(i for i, g in enumerate(groups) if g["id"] == 3)
        add("radioss-wall-fnz", "벽에 전달된 누적 충격량 FNZ", None, "impulse", "FNZ",
            "signed native cumulative wall impulse", "N s", "rigid wall 1",
            raw_field="RWALL/FNZ", values=[s["groups"][wall_index][0] for s in samples])
    return deepcopy(channels)
