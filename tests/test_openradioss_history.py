"""TEST_ONLY protocol/typed-stream fixtures; these tests execute no native solver."""
from copy import deepcopy
import pytest

from caelab import Lab, response_comparison
from caelab.adapters.openradioss import OpenRadiossAdapter
from caelab.adapters.openradioss_history import OpenRadiossHistoryAdapter
from caelab.adapters.openradioss_worker import parse_history
from caelab.storage import save_json
from plugins.explicit_dynamics.reference import assess
from test_openradioss import native_fixture, small_settings


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
