"""TEST_ONLY protocol/typed-stream fixtures; these tests execute no native solver."""
from copy import deepcopy
import pytest

from caelab import Lab, response_comparison
from caelab.adapters.openradioss import OpenRadiossAdapter
from caelab.adapters.openradioss_history import OpenRadiossHistoryAdapter
from caelab.adapters.openradioss_worker import parse_history
from caelab.storage import save_json
from plugins.explicit_dynamics.reference import assess
from test_openradioss import native_fixture, small_settings, small_compliant_settings


class TestOnlyHistory(OpenRadiossAdapter):
    def solve(self, output, settings):
        output.mkdir()
        native_fixture(output, settings)
        raw = parse_history(output, settings)
        assessment = assess(settings, raw["rows"])
        outcome = {"status": "COMPLETED", "solver_status": "COMPLETED", "converged": True,
            "checks": [{"code": "TEST_ONLY", "status": "PASS", "observed": "no native solver executed"}],
            "metrics": assessment["metrics"], "pending_validations": ["physical_model"],
            "provenance": {"test_only": True}, "raw_result": "simulation/analysis_raw.json"}
        for name, value in (("parsed_history", raw), ("input", settings), ("analysis_raw", outcome)):
            save_json(output / (name + ".json"), value)
        return outcome


@pytest.fixture
def lab(tmp_path, monkeypatch):
    monkeypatch.setattr(response_comparison, "source_identity", lambda path: {"test_only": True})
    adapter = TestOnlyHistory()
    value = Lab(tmp_path / "store", adapters={}, analysis_adapters={}, doe_adapters={}, optimization_adapters={},
                pde_adapters={}, model_analysis_adapters={adapter.backend: adapter})
    value.create_study("S-history", "TEST_ONLY", "TEST_ONLY clock/semantic selection", "TEST_ONLY", "No solver")
    value.run_model_analysis(study_id="S-history", experiment_id="E-history", backend=adapter.backend, settings=small_settings())
    return value


def request(history):
    channel = next(c for c in history["channels"] if c["id"] == "radioss-center-vz")
    return {"comparison_id": "O-clock", "experiment_id": "E-history", "purpose": "GENERAL_CAE_RESEARCH",
        "hypothesis": "TEST_ONLY: compare raw velocity at its original half-step time",
        "response": {"history_channel": channel["id"], "sample_index": 1},
        "observation": {"name": "TEST_ONLY half-step velocity", "value": channel["values"][1], "unit": channel["unit"],
            "source_kind": "SYNTHETIC", "source": "TEST_ONLY typed stream; no measured data",
            "quantity": channel["quantity"], "component": channel["component"], "location": channel["location"],
            "coordinate_frame": channel["coordinate_frame"], "condition": "TEST_ONLY free flight",
            "axis": {"quantity": "time", "unit": "s", "value": channel["axis"]["values"][1]},
            "tolerance": 0., "conditions": []}}


def test_actual_core_retained_history_has_no_fabricated_metric_and_distinct_clocks(lab):
    history = lab.response_histories("E-history")
    assert len(history["channels"]) == 8
    position = next(c for c in history["channels"] if c["id"] == "radioss-center-z")
    velocity = next(c for c in history["channels"] if c["id"] == "radioss-center-vz")
    assert position["axis"]["values"][1] == pytest.approx(.0001)
    assert velocity["axis"]["values"][1] == pytest.approx(.00005)
    assert velocity["values"][1] < 0 and all(c["metric"] is None for c in history["channels"])
    before = {p: p.read_bytes() for root in ("studies", "experiments", "ledger") for p in (lab.store/root).rglob("*") if p.is_file()}
    saved = lab.save_response_comparison(**request(history))
    assert saved["schema_version"] == "1.3"
    assert "source_metric" not in saved["comparison"]
    assert saved["comparison"]["difference"] == 0.
    assert saved["comparison"]["physical_validation"] == "UNKNOWN"
    assert lab.inspect_response_comparison("O-clock") == saved
    assert all(p.read_bytes() == b for p, b in before.items())


@pytest.mark.parametrize("mismatch", ["time", "quantity", "component", "coordinate_frame"])
def test_wrong_clock_or_semantics_preserves_raw_value_and_suppresses_numeric_verdict(lab, mismatch):
    body = request(lab.response_histories("E-history"))
    if mismatch == "time": body["observation"]["axis"]["value"] = .0001
    else: body["observation"][mismatch] = "UNQUALIFIED_OTHER"
    saved = lab.save_response_comparison(**body)
    assert saved["comparison"]["status"] == ("DECLARED_AXIS_MISMATCH" if mismatch == "time" else "DECLARED_FIELD_MISMATCH")
    assert saved["comparison"]["response_value"] == body["observation"]["value"]
    assert saved["comparison"]["difference"] is None
    assert saved["comparison"]["within_declared_tolerance"] is None
    assert lab.inspect_response_comparison("O-clock") == saved


@pytest.mark.parametrize("mutation", ["clock", "position", "velocity", "unit", "raw", "group", "work", "version"])
def test_pure_adapter_refuses_unproven_or_mutated_native_mapping(lab, mutation):
    from caelab.response_history import _read_native
    result = lab.inspect_experiment("E-history")
    from caelab.storage import load_json
    proposal = load_json(lab.store/"experiments/E-history/proposal.json")
    reader = OpenRadiossHistoryAdapter()
    resources = {role: _read_native(lab, result, spec["path"], maximum_bytes=spec["maximum_bytes"])
                 for role, spec in reader.history_response_resources(result).items()}
    raw = resources["history"][0]
    if mutation == "clock": raw["rows"][1]["velocity_time_s"] = raw["rows"][1]["time_s"]
    if mutation == "position": raw["rows"][1]["z_m"] += 1
    if mutation == "velocity": raw["rows"][1]["velocity_m_s"] = abs(raw["rows"][1]["velocity_m_s"])
    if mutation == "unit": raw["units"] = "mm,N,s"
    if mutation == "raw": raw["raw_samples"].pop()
    if mutation == "group": raw["groups"][0]["variables"] = [3, 6, 9, 17]
    if mutation == "work": raw["rows"][1]["internal_energy_j"] = 999.
    if mutation == "version": result["provenance"]["adapter_version"] = "UNKNOWN"
    with pytest.raises(ValueError): reader.response_history_channels(result, proposal, resources)


def test_default_history_reader_does_not_admit_an_execution_adapter(tmp_path):
    value = Lab(tmp_path, model_analysis_adapters={}, analysis_adapters={})
    assert "explicit.openradioss" in value.response_history_adapters
    assert "explicit.openradioss" not in value.model_analysis_adapters


def test_http_new_history_comparison_and_reopen_use_same_source(lab):
    from test_lab_server import running
    from apps.lab.service import LabService
    with running(LabService(lab.store, lab_factory=lambda path: lab)) as client:
        history = client.request("/api/response-histories/E-history")
        saved = client.job("response_comparison_save", request(history))
        assert saved["result"]["schema_version"] == "1.3"
    with running(LabService(lab.store, lab_factory=lambda path: lab)) as client:
        saved = client.request("/api/response-comparisons/O-clock")
        assert saved["record"]["comparison"]["source_channel"]["metric"] is None
        assert saved["integrity"] == "VERIFIED"


def selected_settings(compliant=False):
    """Public synthetic input; retained streams remain explicitly TEST_ONLY."""
    legacy = small_compliant_settings() if compliant else small_settings()
    if not compliant:
        # This bounded accumulated native schedule actually records the
        # terminal sample. The older .002 flight fixture stops at .0019.
        legacy["end_time_s"] = .02
    legacy["history_interval_s"] = legacy["time_step_s"]
    value = deepcopy(legacy)
    gravity = value.pop("gravity_m_s2")
    value.update(mode="selected_history", limits={"mass_relative": 1e-8},
                 acceleration_history={"time_s": [0., value["end_time_s"]],
                                       "acceleration_z_m_s2": [-gravity, -gravity]},
                 input_provenance={"origin": "SYNTHETIC", "reference": "TEST_ONLY TH40 protocol data; no native solver"})
    return value, legacy


class TestOnlySelectedHistory(OpenRadiossAdapter):
    version = "1.2"

    def solve(self, output, settings):
        output.mkdir()
        _, legacy = selected_settings(settings["case"] == "rigid_cube_compliant_stop")
        native_fixture(output, legacy)
        raw = parse_history(output, settings)
        assessment = assess(settings, raw["rows"])
        outcome = {"status": "COMPLETED", "solver_status": "COMPLETED", "converged": True,
                   "checks": assessment["checks"], "metrics": assessment["metrics"],
                   "pending_validations": assessment["pending_validations"], "assessment": assessment,
                   "mode": settings["mode"], "input_provenance": deepcopy(settings["input_provenance"]),
                   "provenance": {"test_only": True, "mode": settings["mode"],
                                  "input_provenance": deepcopy(settings["input_provenance"])},
                   "raw_result": "simulation/analysis_raw.json"}
        for name, value in (("parsed_history", raw), ("input", settings), ("analysis_raw", outcome)):
            save_json(output / (name + ".json"), value)
        return outcome


def selected_record(tmp_path, compliant=False):
    adapter = TestOnlySelectedHistory()
    value = Lab(tmp_path / "selected-store", adapters={}, analysis_adapters={}, doe_adapters={},
                optimization_adapters={}, pde_adapters={}, model_analysis_adapters={adapter.backend: adapter})
    value.create_study("S-selected", "TEST_ONLY", "Native clock protocol", "TEST_ONLY", "No native solver")
    settings, _ = selected_settings(compliant)
    result = value.run_model_analysis(study_id="S-selected", experiment_id="E-selected", backend=adapter.backend,
                                      settings=settings)
    from caelab.storage import load_json
    from caelab.response_history import _read_native
    proposal = load_json(value.store / "experiments/E-selected/proposal.json")
    reader = OpenRadiossHistoryAdapter()
    resources = {role: _read_native(value, result, spec["path"], maximum_bytes=spec["maximum_bytes"])
                 for role, spec in reader.history_response_resources(result).items()}
    return value, result, proposal, resources


@pytest.mark.parametrize("compliant", [False, True])
def test_selected_history_keeps_native_samples_two_clocks_and_unknown_reference(tmp_path, compliant):
    value, result, proposal, resources = selected_record(tmp_path, compliant)
    assert "cad_revision" not in proposal and "parent_experiment_id" not in proposal
    assert result["status"] == "COMPLETED_REVIEW_REQUIRED"
    assert result["decision"] == "NOT_RELEASED"
    original = deepcopy((result, proposal, resources))
    channels = OpenRadiossHistoryAdapter().response_history_channels(result, proposal, resources)
    by_id = {channel["id"]: channel for channel in channels}
    assert len(channels) == (12 if compliant else 8)
    rows = resources["history"][0]["rows"]
    assert by_id["radioss-center-z"]["values"] == [row["z_m"] for row in rows]
    assert by_id["radioss-center-vz"]["values"] == [row["velocity_m_s"] for row in rows]
    assert by_id["radioss-center-vz"]["axis"]["values"] == [row["velocity_time_s"] for row in rows]
    assert by_id["radioss-center-vz"]["axis"]["values"][1] != by_id["radioss-center-z"]["axis"]["values"][1]
    assert all(channel["metric"] is None for channel in channels)
    assert {"reference_agreement", "time_step_sensitivity"} <= set(resources["outcome"][0]["pending_validations"])
    assert resources["outcome"][0]["assessment"]["reference"] is None
    assert any(metric["valid"] is False and metric["value"] is None for metric in result["metrics"].values())
    native = next(entry for entry in result["artifacts"] if entry["path"] == "simulation/dropT01")
    assert all(channel["origin"]["native_sha256"] == native["sha256"] for channel in channels)
    assert (result, proposal, resources) == original
    assert value.response_histories("E-selected")["channels"] == channels


def test_selected_compliant_negative_native_ie_is_not_clamped_or_used_as_reference(tmp_path):
    _, result, proposal, resources = selected_record(tmp_path, True)
    raw = resources["history"][0]
    groups = {group["id"]: index for index, group in enumerate(raw["groups"])}
    # Signed native release residue is permitted; change its exact corresponding
    # global/category/spring samples together, then retain the new Domain verdict.
    row, sample = raw["rows"][-1], raw["raw_samples"][-1]
    row["internal_energy_j"] = row["spring_internal_energy_j"] = row["spring_global_internal_energy_j"] = -1e-8
    sample["globals"][0] = sample["globals"][9] = sample["groups"][groups[4]][8] = -1e-8
    outcome = resources["outcome"][0]
    outcome["assessment"] = assess(proposal["execution"], raw["rows"])
    for key in ("checks", "metrics", "pending_validations"):
        outcome[key] = deepcopy(outcome["assessment"][key])
    result["metrics"] = deepcopy(outcome["metrics"])
    channels = OpenRadiossHistoryAdapter().response_history_channels(result, proposal, resources)
    by_id = {channel["id"]: channel for channel in channels}
    assert by_id["radioss-spring-work"]["values"][-1] == -1e-8
    assert by_id["radioss-internal"]["values"][-1] == -1e-8
    assert by_id["radioss-ground-fz"]["values"] == [-v for v in by_id["radioss-spring-fx"]["values"]]
    assert by_id["radioss-ground-fz"]["origin"]["kind"] == "DERIVED"
    assert by_id["radioss-spring-work"]["origin"]["kind"] == "NATIVE"


@pytest.mark.parametrize("mutation", [
    "legacy_version", "unknown_mode", "wall_case", "input_source", "outcome_source", "model_revision",
    "outcome_mode", "outcome_origin",
    "history_entry_hash", "input_entry_hash", "outcome_entry_path", "raw_hash", "duplicate_artifact",
    "resource_bound", "resource_bool_size", "half_step", "missing_sample", "reordered_time",
    "bool_time", "bool_dt", "nonfinite_native", "nonfinite_row", "group_order", "missing_group",
    "reference_promotion", "native_mass", "selected_check", "missing_unknown",
])
def test_selected_retained_reader_refuses_unproven_mapping_or_source(tmp_path, mutation):
    _, result, proposal, resources = selected_record(tmp_path)
    # Break resource-entry aliases so a tuple cannot change its trusted manifest.
    resources = deepcopy(resources)
    raw = resources["history"][0]
    outcome = resources["outcome"][0]
    if mutation == "legacy_version": result["provenance"]["adapter_version"] = "1.1"
    elif mutation == "unknown_mode": proposal["execution"]["mode"] = "OTHER"
    elif mutation == "wall_case": proposal["execution"]["case"] = "rigid_cube_ground_stop"
    elif mutation == "input_source": resources["input"][0]["input_provenance"]["reference"] = "OTHER"
    elif mutation == "outcome_source": outcome["provenance"]["test_only"] = False
    elif mutation == "model_revision": proposal["model_revision"] = "f" * 64
    elif mutation == "outcome_mode": outcome["mode"] = "OTHER"
    elif mutation == "outcome_origin": outcome["input_provenance"]["reference"] = "OTHER"
    elif mutation == "history_entry_hash": resources["history"][1]["sha256"] = "a" * 64
    elif mutation == "input_entry_hash": resources["input"][1]["sha256"] = "b" * 64
    elif mutation == "outcome_entry_path": resources["outcome"][1]["path"] = "simulation/OTHER.json"
    elif mutation == "raw_hash": next(e for e in result["artifacts"] if e["path"] == "simulation/dropT01")["sha256"] = "UNKNOWN"
    elif mutation == "duplicate_artifact": result["artifacts"].append(deepcopy(resources["history"][1]))
    elif mutation in ("resource_bound", "resource_bool_size"):
        resources["input"][1]["size_bytes"] = 1048577 if mutation == "resource_bound" else True
        next(e for e in result["artifacts"] if e["path"] == "simulation/input.json")["size_bytes"] = resources["input"][1]["size_bytes"]
    elif mutation == "half_step": raw["rows"][1]["velocity_time_s"] = raw["rows"][1]["time_s"]
    elif mutation == "missing_sample": raw["raw_samples"].pop()
    elif mutation == "reordered_time": raw["raw_samples"][1:3] = raw["raw_samples"][2:0:-1]
    elif mutation == "bool_time": raw["rows"][0]["time_s"] = raw["raw_samples"][0]["time_s"] = False
    elif mutation == "bool_dt": raw["raw_samples"][1]["globals"][6] = True
    elif mutation == "nonfinite_native": raw["raw_samples"][1]["groups"][0][0] = float("nan")
    elif mutation == "nonfinite_row": raw["rows"][1]["velocity_m_s"] = float("inf")
    elif mutation == "group_order": raw["groups"][0]["entities"].reverse()
    elif mutation == "missing_group": raw["groups"].pop()
    elif mutation == "reference_promotion": outcome["assessment"]["reference"] = {"status": "PASS"}
    elif mutation == "native_mass": raw["rows"][1]["mass_kg"] *= 2; raw["raw_samples"][1]["globals"][5] *= 2
    elif mutation == "selected_check": outcome["checks"][0]["observed"] = "UNPROVEN"
    elif mutation == "missing_unknown": outcome["pending_validations"].remove("reference_agreement")
    with pytest.raises(ValueError):
        OpenRadiossHistoryAdapter().response_history_channels(result, proposal, resources)


@pytest.mark.parametrize("version,case,allowed", [("1", "flight", True), ("1", "wall", True), ("1", "compliant", False),
                                                  ("1.1", "flight", True), ("1.1", "wall", True), ("1.1", "compliant", True),
                                                  ("1.2", "flight", True), ("1.2", "wall", True), ("1.2", "compliant", True)])
def test_historical_retained_contract_and_current_benchmark_remain_explicit(tmp_path, version, case, allowed):
    compliant, wall = case == "compliant", case == "wall"
    settings = small_compliant_settings() if compliant else small_settings(wall)
    output = tmp_path / "stream"
    native_fixture(output, settings)
    raw = parse_history(output, settings)
    assessment = assess(settings, raw["rows"])
    from caelab.storage import artifact_manifest
    for name, content in (("parsed_history", raw), ("input", settings)):
        save_json(output / (name + ".json"), content)
    outcome = {"status": "COMPLETED", "solver_status": "COMPLETED", "converged": True,
               "checks": [{"code": "TEST_ONLY", "status": "PASS"}], "metrics": assessment["metrics"],
               "raw_result": "simulation/analysis_raw.json", "provenance": {"test_only": True}}
    save_json(output / "analysis_raw.json", outcome)
    manifest = [{**entry, "path": "simulation/" + entry["path"]} for entry in artifact_manifest(output, revision="a" * 64)]
    result = {"status": "COMPLETED_REVIEW_REQUIRED", "solver_status": "COMPLETED", "converged": True,
              "decision": "NOT_RELEASED", "experiment_id": "E-old", "study": {"id": "S-old"},
              "metrics": assessment["metrics"], "artifacts": manifest,
              "provenance": {"adapter": "explicit.openradioss", "adapter_version": version,
                             "execution_settings": settings, "adapter_details": outcome["provenance"]}}
    proposal = {"id": "E-old", "study_id": "S-old", "physics": {"backend": "explicit.openradioss"}, "execution": settings}
    entries = {entry["path"]: entry for entry in manifest}
    resources = {"history": (raw, entries["simulation/parsed_history.json"]),
                 "input": (settings, entries["simulation/input.json"]),
                 "outcome": (outcome, entries["simulation/analysis_raw.json"])}
    if allowed:
        channels = OpenRadiossHistoryAdapter().response_history_channels(result, proposal, resources)
        assert len(channels) == (12 if compliant else 9 if wall else 8)
        if wall:
            impulse = next(channel for channel in channels if channel["id"] == "radioss-wall-fnz")
            assert impulse["quantity"] == "impulse" and impulse["unit"] == "N s"
            assert impulse["origin"]["native_field"] == "RWALL/FNZ"
    else:
        with pytest.raises(ValueError): OpenRadiossHistoryAdapter().response_history_channels(result, proposal, resources)
