"""TEST-ONLY retained protocol fixtures; no native material/solver or measurement."""

from copy import deepcopy
import hashlib
import pytest
from jsonschema.exceptions import ValidationError

from caelab import Lab
from caelab.adapters.mfront_history import channels
from caelab.storage import load_json, save_json
from caelab import response_comparison


def raw_fixture():
    rows = [{"time_s": t, "stress_physical_mpa": [t, 2*t, -t, -3*t, 4*t, 5*t],
             "branch_stress_physical_mpa": [t/2]*6, "stored_energy_mpa": t*0.1,
             "dissipated_energy_mpa": t*0.2} for t in (0., .2, 1.)]
    return {"conventions": {"physical": "xx,yy,zz,xy,xz,yz", "stress_unit": "MPa",
                "strain": "infinitesimal_tensor_not_engineering_shear", "energy_unit": "MPa = MJ/m^3 per reference volume"},
            "mgis": {"initial": rows[0], "steps": rows[1:]}, "mtest": {"states": deepcopy(rows)}}


def metrics_fixture(raw):
    rows = [raw["mgis"]["initial"], *raw["mgis"]["steps"]]
    metrics = {name: {"value": [r[field] for r in rows], "unit": "MPa", "valid": True}
               for name, field in (("stress_history", "stress_physical_mpa"), ("branch_stress_history", "branch_stress_physical_mpa"))}
    metrics["native_energy_history"] = {"value": [[[r["stored_energy_mpa"], r["dissipated_energy_mpa"]] for r in rr]
        for rr in (rows, raw["mtest"]["states"])], "unit": "MPa", "valid": True,
        "drivers": ["mgis", "mtest"], "components": ["stored", "dissipated"]}
    metrics["reference_work_history"] = {"value": [0., .3, .6], "unit": "MPa", "valid": True}
    return metrics


class TestOnlyMaxwell:
    backend = "material.mfront.viscoelastic"
    version = "TEST_ONLY_NOT_NATIVE"
    domain = "test"
    physics_domain = "test_only"
    analysis_type = "protocol_fixture"
    default_metrics = ["stress_history", "branch_stress_history", "native_energy_history"]

    def describe_model(self, settings):
        return {"model": {"geometry": {"kind": "TEST_ONLY_NO_NATIVE_MODEL"}}, "outputs": {"metrics": self.default_metrics}, "loads": []}

    def solve(self, output, settings):
        output.mkdir()
        raw = raw_fixture()
        save_json(output / "native_raw.json", raw)
        return {"status": "COMPLETED", "solver_status": "COMPLETED", "converged": True,
                "checks": [{"code": "TEST_ONLY", "status": "PASS", "observed": "not native"}],
                "metrics": metrics_fixture(raw), "pending_validations": ["physical_qualification"],
                "provenance": {"test_only": True, "actual_native_raw": f"{output.name}/native_raw.json"},
                "raw_result": f"{output.name}/native_raw.json"}


@pytest.fixture
def lab(tmp_path, monkeypatch):
    monkeypatch.setattr(response_comparison, "source_identity", lambda root: {"test_only": True})
    model = TestOnlyMaxwell()
    value = Lab(tmp_path / "store", adapters={}, analysis_adapters={}, pde_adapters={},
                model_analysis_adapters={model.backend: model}, doe_adapters={}, optimization_adapters={})
    value.create_study("S-test", "TEST_ONLY", "TEST_ONLY history protocol", "TEST_ONLY", "no qualification")
    value.run_model_analysis(study_id="S-test", experiment_id="E-test", backend=model.backend,
        settings={"history": [{"time_s": t, "strain": [0.]*6} for t in (0., .2, 1.)], "material": {"relaxation_time_s": 1.}})
    return value


def request():
    return {"comparison_id": "O-history-test", "experiment_id": "E-test", "purpose": "DEFECT_REPRODUCTION",
        "hypothesis": "TEST ONLY alternate material comparison, not a physical cause",
        "response": {"history_channel": "mgis-stress-xy", "sample_index": 1},
        "observation": {"name": "TEST ONLY shear target", "value": -.6, "unit": "MPa",
            "source_kind": "SYNTHETIC", "source": "TEST_ONLY finite sample", "quantity": "stress", "component": "xy",
            "location": "TEST_ONLY homogeneous point", "coordinate_frame": "TEST_ONLY component basis",
            "condition": "TEST_ONLY", "tolerance": 1e-12,
            "axis": {"quantity": "time", "value": .2, "unit": "s"},
            "conditions": [{"source": "execution", "path": ["material", "relaxation_time_s"], "value": 1., "unit": "s"}]}}


def test_adapter_keeps_native_driver_measure_signed_components_and_initial_state():
    raw = raw_fixture()
    result = {"provenance": {"adapter": "material.mfront.viscoelastic"}, "metrics": metrics_fixture(raw)}
    value = channels(result, {"history": [{"time_s": t} for t in (0., .2, 1.)]}, raw,
                     {"path": "simulation/native_raw.json", "sha256": "a"*64})
    assert len(value) == 16
    selected = next(c for c in value if c["id"] == "mgis-stress-xz")
    assert selected["values"] == [0., .8, 4.]
    assert selected["axis"]["values"] == [0., .2, 1.]
    assert selected["initial_state"]["kind"] == "UNPREPARED_INITIAL_CONDITION"
    assert all(c["metric"] != "reference_work_history" for c in value)
    assert next(c for c in value if c["id"] == "mtest-stored")["origin"]["driver"] == "mtest"


def test_real_core_append_reopen_and_history_axis_without_interpolation(lab):
    before = {p: p.read_bytes() for root in ("studies", "experiments", "ledger") for p in (lab.store/root).rglob("*") if p.is_file()}
    history = lab.response_histories("E-test")
    assert history["integrity"] == "VERIFIED" and len(history["channels"]) == 16
    saved = lab.save_response_comparison(**request())
    comparison = saved["comparison"]
    assert saved["schema_version"] == "1.1"
    assert comparison["response_value"] == pytest.approx(-.6)
    assert comparison["response_axis"] == {"quantity": "time", "value": .2, "unit": "s"}
    assert comparison["within_declared_tolerance"] is True
    assert comparison["physical_validation"] == "UNKNOWN" and comparison["decision"] == "NOT_RELEASED"
    assert lab.inspect_response_comparison(saved["id"]) == saved
    assert all(p.read_bytes() == contents for p, contents in before.items())
    with pytest.raises(FileExistsError):
        lab.save_response_comparison(**request())


def test_off_grid_declared_time_retains_response_and_suppresses_difference(lab):
    body = request(); body["observation"]["axis"]["value"] = .3
    saved = lab.save_response_comparison(**body)
    assert saved["comparison"]["status"] == "DECLARED_AXIS_MISMATCH"
    assert saved["comparison"]["response_value"] == pytest.approx(-.6)
    assert saved["comparison"]["difference"] is None
    assert saved["comparison"]["within_declared_tolerance"] is None
    assert lab.inspect_response_comparison(saved["id"]) == saved


@pytest.mark.parametrize("change", ["missing_axis", "missing_channel", "negative_index", "bool_index", "large_index", "wrong_unit", "wrong_axis_unit", "scalar_axis"])
def test_bad_history_selection_refused_before_persistence(lab, change):
    body = request()
    if change == "missing_axis": del body["observation"]["axis"]
    if change == "missing_channel": body["response"]["history_channel"] = "reference-work"
    if change == "negative_index": body["response"]["sample_index"] = -1
    if change == "bool_index": body["response"]["sample_index"] = True
    if change == "large_index": body["response"]["sample_index"] = 500
    if change == "wrong_unit": body["observation"]["unit"] = "Pa"
    if change == "wrong_axis_unit": body["observation"]["axis"]["unit"] = "ms"
    if change == "scalar_axis": body["response"] = {"metric": "reference_work_history", "component": 1}
    with pytest.raises((ValueError, ValidationError)):
        lab.save_response_comparison(**body)
    assert not (lab.store/"response_comparisons/O-history-test").exists()


@pytest.mark.parametrize("change", ["shape", "time", "convention", "driver_order", "physical_value", "bool_time", "bool_energy", "bool_input_time", "huge_energy"])
def test_adapter_refuses_unproven_mapping(change):
    raw = raw_fixture(); metrics = metrics_fixture(raw)
    if change == "shape": metrics["stress_history"]["value"][1].pop()
    if change == "time": raw["mtest"]["states"][1]["time_s"] = .3
    if change == "convention": raw["conventions"]["physical"] = "guess"
    if change == "driver_order": metrics["native_energy_history"]["drivers"].reverse()
    if change == "physical_value": metrics["stress_history"]["value"] = deepcopy(metrics["stress_history"]["value"]); metrics["stress_history"]["value"][1][4] += 1
    if change == "bool_time": raw["mtest"]["states"][-1]["time_s"] = True
    if change == "bool_energy": raw["mtest"]["states"][-1]["stored_energy_mpa"] = True; metrics["native_energy_history"]["value"][1][-1][0] = 1.
    if change == "huge_energy": raw["mtest"]["states"][-1]["stored_energy_mpa"] = 10**400; metrics["native_energy_history"]["value"][1][-1][0] = 1.
    settings = {"history": [{"time_s": t} for t in (0., .2, 1.)]}
    if change == "bool_input_time": settings["history"][-1]["time_s"] = True
    with pytest.raises(ValueError):
        channels({"provenance": {"adapter": "material.mfront.viscoelastic"}, "metrics": metrics},
                 settings, raw, {"path": "simulation/native_raw.json", "sha256": "a"*64})


def test_native_mutation_and_outside_manifest_refuse_core_reads(lab):
    lab.save_response_comparison(**request())
    path = lab.store/"experiments/E-test/simulation/native_raw.json"
    path.write_bytes(path.read_bytes()+b" ")
    with pytest.raises(ValueError, match="hash mismatch"):
        lab.response_histories("E-test")
    with pytest.raises(ValueError):
        lab.inspect_response_comparison("O-history-test")
    result_path = lab.store/"experiments/E-test/result.json"
    result = load_json(result_path); result["artifacts"][0]["path"] = "../../outside.json"; save_json(result_path, result)
    with pytest.raises(ValueError, match="path is invalid"):
        lab.response_histories("E-test")


def test_http_history_comparison_survives_controller_restart(lab):
    from test_lab_server import running
    from apps.lab.service import LabService
    with running(LabService(lab.store, lab_factory=lambda path: lab)) as client:
        assert len(client.request("/api/response-histories/E-test")["channels"]) == 16
        job = client.job("response_comparison_save", request())
        assert job["result"]["comparison"]["response_axis"]["value"] == .2
    with running(LabService(lab.store, lab_factory=lambda path: lab)) as client:
        reopened = client.request("/api/response-comparisons/O-history-test")
        assert reopened["integrity"] == "VERIFIED"
        assert reopened["record"]["comparison"]["selection_kind"] == "EXACT_RECORDED_HISTORY_SAMPLE"


def test_http_readonly_and_source_race_preserve_history_evidence(lab, tmp_path, monkeypatch):
    from test_lab_server import running
    from apps.lab.service import LabService
    with running(LabService(tmp_path/"writable", libraries={"history": lab.store}, lab_factory=lambda path: lab)) as client:
        client.request("/api/store", {"id": "history"})
        assert len(client.request("/api/response-histories/E-test")["channels"]) == 16
        client.request("/api/jobs", {"operation": "response_comparison_save", "arguments": request()}, expected=403)
    original = lab.response_histories
    def changed(identifier):
        value = original(identifier)
        path = lab.store/"experiments/E-test/simulation/native_raw.json"
        path.write_bytes(path.read_bytes()+b" ")
        return value
    monkeypatch.setattr(lab, "response_histories", changed)
    with running(LabService(lab.store, lab_factory=lambda path: lab)) as client:
        client.request("/api/response-histories/E-test", expected=400)
