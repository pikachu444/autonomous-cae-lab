"""Real Core persistence and declared comparison controls; TEST-ONLY producer.

These fixtures contain no native CAD/solver/measurement and make no physics claim.
"""

from copy import deepcopy
import hashlib
import math
import pytest
from jsonschema.exceptions import ValidationError

from caelab import Lab
from caelab.storage import load_json, save_json
from caelab import response_comparison


class TestOnlyModel:
    backend = "test.observation.model"
    version = "TEST-ONLY"
    domain = "test"
    physics_domain = "test_only"
    analysis_type = "protocol_fixture"
    default_metrics = ["test_force", "test_vector", "invalid_diagnostic"]

    def describe_model(self, settings):
        return {"model": {"geometry": {"kind": "TEST_ONLY_NO_NATIVE_MODEL"}},
                "outputs": {"metrics": self.default_metrics}, "loads": []}

    def solve(self, output, settings):
        output.mkdir()
        save_json(output / "test-only.json", {"test_only": True, "settings": settings})
        return {"status": "COMPLETED", "solver_status": "COMPLETED", "converged": True,
                "checks": [{"code": "TEST_ONLY", "status": "PASS", "observed": "protocol fixture"}],
                "metrics": {"test_force": {"value": settings["force_N"], "unit": "N", "valid": True},
                            "test_vector": {"value": [0.0, -2.0, settings["force_N"]], "unit": "N", "valid": True},
                            "invalid_diagnostic": {"value": 999., "unit": "N", "valid": False, "reason": "TEST_ONLY invalid"}},
                "pending_validations": ["physical_qualification"],
                "provenance": {"test_only": True}, "raw_result": f"{output.name}/test-only.json"}


@pytest.fixture
def lab(tmp_path, monkeypatch):
    # Deterministic source identity fixture is separate from actual-runtime proof.
    monkeypatch.setattr(response_comparison, "source_identity", lambda root: {"test_only": True})
    model = TestOnlyModel()
    value = Lab(tmp_path / "store", adapters={}, analysis_adapters={}, pde_adapters={},
                model_analysis_adapters={model.backend: model}, doe_adapters={}, optimization_adapters={})
    value.create_study("S-test", "TEST_ONLY", "protocol comparison", "TEST_ONLY", "no physical approval")
    value.run_model_analysis(study_id="S-test", experiment_id="E-test", backend=model.backend,
                             settings={"force_N": 150., "declared_vector": [0., -2., 150.]})
    return value


def request(**changes):
    body = {"comparison_id": "C-test", "experiment_id": "E-test", "purpose": "JIG_FEASIBILITY",
            "hypothesis": "TEST ONLY hypothesis, not physical inference",
            "observation": {"name": "TEST ONLY target", "value": 149., "unit": "N",
                "source_kind": "SYNTHETIC", "source": "TEST_ONLY explicit expected value",
                "quantity": "force", "component": "declared scalar", "location": "TEST_ONLY",
                "coordinate_frame": "USER_DECLARED_TEST_FRAME", "condition": "force150N TEST ONLY",
                "tolerance": 1., "conditions": [{"source": "execution", "path": ["force_N"], "value": 150., "unit": "N"}]},
            "response": {"metric": "test_force"}}
    body.update(changes)
    return body


def originals(lab):
    return {p.relative_to(lab.store).as_posix(): p.read_bytes() for namespace in ("studies", "experiments", "ledger")
            for p in (lab.store / namespace).rglob("*") if p.is_file()}


def test_real_core_roundtrip_rejects_duplicate_and_preserves_originals(lab):
    before = originals(lab)
    body = request()
    original = deepcopy(body)
    saved = lab.save_response_comparison(**body)
    assert body == original
    assert saved["comparison"]["difference"] == 1.
    assert saved["comparison"]["within_declared_tolerance"] is True
    assert saved["comparison"]["scope_alignment"] == "USER_DECLARED_UNVERIFIED"
    assert saved["comparison"]["physical_validation"] == "UNKNOWN"
    assert saved["comparison"]["causal_verdict"] == "NOT_EVALUATED"
    assert saved["comparison"]["decision"] == "NOT_RELEASED"
    assert lab.inspect_response_comparison("C-test") == saved
    assert lab.response_comparisons("S-test") == [{"record": saved, "integrity": "VERIFIED"}]
    with pytest.raises(FileExistsError):
        lab.save_response_comparison(**body)
    assert originals(lab) == before
    assert lab.inspect_response_comparison("C-test") == saved


def test_signed_array_selection_is_explicit_and_preserves_whole_metric(lab):
    body = request(response={"metric": "test_vector", "component": 1})
    body["observation"].update(value=-2., tolerance=0.)
    saved = lab.save_response_comparison(**body)
    assert saved["comparison"]["response_value"] == -2.
    assert saved["comparison"]["source_metric"]["value"] == [0., -2., 150.]
    assert saved["comparison"]["selection_kind"] == "USER_SELECTED_ARRAY_ITEM"
    assert saved["comparison"]["scope_alignment"] == "USER_DECLARED_UNVERIFIED"


@pytest.mark.parametrize("response", [{"metric": "invalid_diagnostic"}, {"metric": "missing"},
    {"metric": "test_vector"}, {"metric": "test_vector", "component": -1},
    {"metric": "test_vector", "component": 3}, {"metric": "test_vector", "component": True},
    {"metric": "test_vector", "component": "1"}, {"metric": "test_force", "component": 0}])
def test_unsupported_response_refuses_before_persistence(lab, response):
    with pytest.raises((ValueError, ValidationError)):
        lab.save_response_comparison(**request(response=response))
    assert not (lab.store / "response_comparisons/C-test").exists()


@pytest.mark.parametrize("key,value", [("value", True), ("value", math.inf), ("value", math.nan),
    ("tolerance", -1.), ("tolerance", math.inf), ("source_kind", "QUALIFIED_MEASUREMENT"),
    ("unit", "kN"), ("location", ""), ("component", " "), ("coordinate_frame", ""), ("source", "")])
def test_invalid_or_unaligned_observation_is_not_saved(lab, key, value):
    body = request()
    body["observation"][key] = value
    with pytest.raises((ValueError, ValidationError)):
        lab.save_response_comparison(**body)
    assert not (lab.store / "response_comparisons/C-test").exists()


@pytest.mark.parametrize("kind", ["MEASURED_REPORTED", "SPECIFICATION", "SYNTHETIC"])
def test_reported_source_kind_does_not_qualify_physical_measurement_or_specification(lab, kind):
    body = request()
    body["observation"]["source_kind"] = kind
    saved = lab.save_response_comparison(**body)
    assert saved["request"]["observation"]["source_kind"] == kind
    assert saved["comparison"]["within_declared_tolerance"] is True
    assert saved["comparison"]["physical_validation"] == "UNKNOWN"
    assert saved["comparison"]["decision"] == "NOT_RELEASED"


@pytest.mark.parametrize("path,value", [(["force_N"], 100.), (["missing"], 150.), (["force_N"], True)])
def test_declared_condition_mismatch_retains_values_without_computable_match(lab, path, value):
    body = request()
    body["observation"]["conditions"][0].update(path=path, value=value)
    saved = lab.save_response_comparison(**body)
    comparison = saved["comparison"]
    assert comparison["status"] == "DECLARED_CONDITION_MISMATCH"
    assert comparison["difference"] is None
    assert comparison["within_declared_tolerance"] is None
    assert comparison["response_value"] == 150.
    assert lab.inspect_response_comparison("C-test") == saved


def test_no_bindings_does_not_claim_condition_alignment(lab):
    body = request()
    body["observation"]["conditions"] = []
    saved = lab.save_response_comparison(**body)
    assert saved["comparison"]["condition_bindings_supplied"] is False
    assert saved["comparison"]["scope_alignment"] == "USER_DECLARED_UNVERIFIED"


def test_condition_binding_supports_explicit_array_index_without_axis_inference(lab):
    # A protocol-only source array; its path is declared, never converted to XYZ.
    body = request()
    body["observation"]["conditions"] = [{"source": "execution", "path": ["declared_vector", "2"], "value": 150., "unit": "N"}]
    saved = lab.save_response_comparison(**body)
    assert saved["comparison"]["declared_condition_checks"][0]["matched"] is True
    assert lab.inspect_response_comparison("C-test") == saved
    for invalid in ["02", "-1", "3", "2.0"]:
        body["comparison_id"] = "C-invalid-" + invalid.replace(".", "_").replace("-", "_")
        body["observation"]["conditions"][0]["path"][-1] = invalid
        saved = lab.save_response_comparison(**body)
        assert saved["comparison"]["difference"] is None


@pytest.mark.parametrize("target", ["record", "receipt", "result", "artifact"])
def test_changed_record_or_original_source_refuses_reopen(lab, target):
    lab.save_response_comparison(**request())
    paths = {"record": lab.store / "response_comparisons/C-test/record.json",
             "receipt": lab.store / "response_comparisons/C-test/receipt.json",
             "result": lab.store / "experiments/E-test/result.json",
             "artifact": lab.store / "experiments/E-test/simulation/test-only.json"}
    paths[target].write_bytes(paths[target].read_bytes() + b" ")
    if target == "receipt":
        value = load_json(paths[target]); value["record_sha256"] = "0" * 64; save_json(paths[target], value)
    with pytest.raises(ValueError):
        lab.inspect_response_comparison("C-test")


def test_partial_receipt_kept_unknown_and_cannot_be_overwritten(lab):
    lab.save_response_comparison(**request())
    (lab.store / "response_comparisons/C-test/receipt.json").unlink()
    assert lab.response_comparisons("S-test")[0]["integrity"] == "UNKNOWN"
    with pytest.raises(FileExistsError):
        lab.save_response_comparison(**request())


def test_reopen_rechecks_all_source_metadata_not_only_envelope_hashes(lab):
    lab.save_response_comparison(**request())
    folder = lab.store / "response_comparisons/C-test"
    record = load_json(folder / "record.json")
    record["source"]["original_decision"] = "RELEASED"
    save_json(folder / "record.json", record)
    save_json(folder / "receipt.json", {"id": "C-test", "record_sha256": hashlib.sha256((folder / "record.json").read_bytes()).hexdigest()})
    with pytest.raises(ValueError, match="identity/metadata/hash"):
        lab.inspect_response_comparison("C-test")


def test_http_save_list_reopen_and_completed_job_survive_service_restart(lab):
    from test_lab_server import running
    from apps.lab.service import LabService
    from apps.lab.job_journal import HTTPJobJournal
    before = originals(lab)
    first = LabService(lab.store, lab_factory=lambda path: lab, http_journal=HTTPJobJournal(lab.store))
    with running(first) as client:
        terminal = client.job("response_comparison_save", request())
        saved = client.request("/api/response-comparisons/C-test")
        assert saved["integrity"] == "VERIFIED"
        assert saved["record"] == terminal["result"]
        assert client.request("/api/response-comparisons?study_id=S-test") == [saved]
        client.request("/api/response-comparisons", expected=400)
        client.request("/api/response-comparisons?study_id=S-test&study_id=S-test", expected=400)
        client.request("/api/response-comparisons?study_id=../private", expected=400)
        failed = client.job("response_comparison_save", request(), expected_status="FAILED")
        assert "FileExistsError" in failed["error"]
        assert client.request("/api/response-comparisons/C-test") == saved
    second = LabService(lab.store, lab_factory=lambda path: lab, http_journal=HTTPJobJournal(lab.store))
    with running(second) as client:
        assert client.request("/api/jobs/" + terminal["id"]) == terminal
        assert client.request("/api/response-comparisons/C-test") == saved
        assert client.request("/api/overview")["execution"]["state"] == "IDLE"
    assert originals(lab) == before


def test_http_readonly_history_allows_comparison_reads_and_refuses_append(lab, tmp_path):
    from test_lab_server import running
    from apps.lab.service import LabService
    lab.save_response_comparison(**request())
    before = originals(lab)
    def factory(path):
        return Lab(path, adapters={}, analysis_adapters={}, pde_adapters={},
                   model_analysis_adapters={}, doe_adapters={}, optimization_adapters={})
    service = LabService(tmp_path / "writable", libraries={"history": lab.store}, lab_factory=factory)
    with running(service) as client:
        client.request("/api/store", {"id": "history"})
        assert client.request("/api/response-comparisons/C-test")["integrity"] == "VERIFIED"
        client.request("/api/jobs", {"operation": "response_comparison_save", "arguments": request(comparison_id="C-new")}, expected=403)
    assert not (lab.store / "response_comparisons/C-new").exists()
    assert originals(lab) == before


def test_http_checks_source_paths_before_calling_core(lab, tmp_path, monkeypatch):
    from test_lab_server import running
    from apps.lab.service import LabService
    original = lab.store / "experiments/E-test/simulation/test-only.json"
    outside = tmp_path / "outside-test-only.json"
    outside.write_text('"TEST_ONLY outside-file"', encoding="utf-8")
    original.unlink()
    original.symlink_to(outside)
    called = []
    monkeypatch.setattr(lab, "save_response_comparison", lambda **kwargs: called.append(kwargs))
    with running(LabService(lab.store, lab_factory=lambda path: lab)) as client:
        terminal = client.job("response_comparison_save", request(), expected_status="FAILED")
        assert terminal["error"].startswith("ValueError: Path escapes verified root:")
    assert called == []
    assert not (lab.store / "response_comparisons/C-test").exists()


def test_http_preserves_expected_source_hashes_across_core_call(lab, monkeypatch):
    from test_lab_server import running
    from apps.lab.service import LabService
    original = lab.save_response_comparison
    def changed(**arguments):
        value = original(**arguments)
        result_path = lab.store / "experiments/E-test/result.json"
        result_path.write_bytes(result_path.read_bytes() + b" ")
        return value
    monkeypatch.setattr(lab, "save_response_comparison", changed)
    with running(LabService(lab.store, lab_factory=lambda path: lab)) as client:
        terminal = client.job("response_comparison_save", request(), expected_status="FAILED")
        assert "hash" in terminal["error"].lower() or "changed" in terminal["error"].lower()
        rows = client.request("/api/response-comparisons?study_id=S-test")
        assert rows[0]["integrity"] == "UNKNOWN"
    # Partial/changed evidence remains retained, never converted to a successful fit.
    assert (lab.store / "response_comparisons/C-test/record.json").exists()


@pytest.fixture
def field_request(lab, monkeypatch):
    """Core-only TEST fixture; pure adapter contract is tested independently.

    Real contained manifest bytes still pass through the production field reader.
    The patched native interpreter explicitly supplies a nonphysical test point.
    """
    from caelab.adapters import structural_response_fields
    result = lab.inspect_experiment("E-test")
    artifact = next(a for a in result["artifacts"] if a["path"] == "simulation/test-only.json")
    selector = {"artifact": artifact["path"], "sha256": artifact["sha256"],
                "cad_revision": "a" * 64, "node_id": 17, "component": "UZ"}

    def test_only_interpreter(result, proposal, raw, artifact, selection):
        assert raw["test_only"] is True and raw["settings"]["force_N"] == 150.
        if selection != selector:
            raise ValueError("TEST_ONLY selector differs from the explicit original point")
        return {"value": -0.125, "unit": "mm", "qualification": "UNKNOWN", "source_field": {
            **selection, "quantity": "DISPLACEMENT", "position_mm": [1., 2., 3.], "position_unit": "mm",
            "coordinate_frame": "TEST_ONLY_UNQUALIFIED", "value_origin": "NATIVE_COMPONENT",
            "static": {"step": 1, "increment": 1, "load_parameter": 1}, "coverage": "ALL_MESH_NODES"}}

    monkeypatch.setattr(structural_response_fields, "select_field_response", test_only_interpreter)
    body = request(purpose="GENERAL_CAE_RESEARCH", response={"field": selector})
    body["observation"].update(value=-0.125, unit="mm", quantity="DISPLACEMENT", component="UZ",
                               coordinate_frame="TEST_ONLY_UNQUALIFIED", tolerance=0.)
    return body


def test_field_comparison_roundtrip_and_research_context_keep_the_exact_point(lab, field_request):
    before = originals(lab)
    saved = lab.save_response_comparison(**field_request)
    assert saved["schema_version"] == "1.2"
    assert saved["comparison"]["difference"] == 0.
    assert saved["comparison"]["response_value"] == -.125
    assert "source_metric" not in saved["comparison"] and "response_axis" not in saved["comparison"]
    assert saved["comparison"]["selection_kind"] == "EXACT_RECORDED_FIELD_NODE"
    assert saved["comparison"]["source_field"]["position_mm"] == [1., 2., 3.]
    assert lab.inspect_response_comparison("C-test") == saved
    context = lab.research_summary("E-test")["comparison_context"]
    assert context["records"][0]["record"] == saved
    assert context["physical_validation"] == "UNKNOWN" and context["decision"] == "NOT_RELEASED"
    assert originals(lab) == before


@pytest.mark.parametrize("key,value", [("quantity", "STRESS"), ("component", "UY"), ("coordinate_frame", "SENSOR_GLOBAL")])
def test_field_declaration_mismatch_retains_signed_response_with_null_verdict(lab, field_request, key, value):
    field_request["observation"][key] = value
    saved = lab.save_response_comparison(**field_request)
    actual = saved["comparison"]
    assert actual["status"] == "DECLARED_FIELD_MISMATCH"
    assert actual["response_value"] == -.125 and actual["observed_value"] == -.125
    assert actual["difference"] is None and actual["within_declared_tolerance"] is None
    assert sum(check["matched"] is False for check in actual["declared_field_checks"]) == 1
    assert lab.inspect_response_comparison("C-test") == saved


def test_field_rejects_stale_hash_implicit_time_and_wrong_unit_before_append(lab, field_request):
    for damage in ("hash", "time", "unit"):
        body = deepcopy(field_request)
        if damage == "hash":
            body["response"]["field"]["sha256"] = "0" * 64
        elif damage == "time":
            body["observation"]["axis"] = {"quantity": "time", "value": 1., "unit": "s"}
        else:
            body["observation"]["unit"] = "m"
        with pytest.raises(ValueError):
            lab.save_response_comparison(**body)
        assert not (lab.store / "response_comparisons/C-test").exists()
    saved = lab.save_response_comparison(**field_request)
    assert lab.inspect_response_comparison("C-test") == saved
    raw = lab.store / "experiments/E-test/simulation/test-only.json"
    raw.write_bytes(raw.read_bytes() + b" ")
    with pytest.raises(ValueError):
        lab.inspect_response_comparison("C-test")


@pytest.fixture
def pde_field_request(lab):
    """Core-only fake native interpreter, with real manifest/persistence guards.

    The five-family native layout parser is tested in test_pde_response_fields;
    these tests exercise additive schema1.4 routing and exact axis semantics.
    """
    from types import SimpleNamespace
    result = lab.inspect_experiment('E-test')
    artifact = next(a for a in result['artifacts'] if a['path'] == 'simulation/test-only.json')
    selector = {'kind': 'pde_nodal', 'artifact': artifact['path'], 'sha256': artifact['sha256'],
                'model_revision': result['model_revision'], 'study_index': 0, 'step_index': 1,
                'node_id': 0, 'component': 'u'}

    def selected(r, p, resources, selection):
        if selection != selector:
            raise ValueError('TEST_ONLY native node/field/revision selection differs')
        raw, entry = resources['field']
        assert raw['test_only'] is True and entry['sha256'] == selector['sha256']
        return {'value': -.125, 'unit': '1', 'source_field': {**selector,
                    'quantity': 'PDE_SCALAR_FIELD', 'coordinates': [0., 1.],
                    'coordinates_unit': '1', 'coordinate_frame': 'PDE_MODEL_CARTESIAN'},
                'response_axis': {'quantity': 'time', 'unit': '1', 'value': .25},
                'qualification': {'numeric': 'RECORDED_NATIVE_VALUE', 'reference': 'UNKNOWN',
                                  'physical': 'UNKNOWN', 'decision': 'NOT_RELEASED'}}

    lab.response_field_adapters[result['provenance']['adapter']] = SimpleNamespace(
        field_response_resources=lambda r: {'header': {'path': selector['artifact'], 'maximum_bytes': 1024}},
        field_selection_resources=lambda r, s, resources: {'field': {'path': selector['artifact'], 'maximum_bytes': 1024}},
        select_response_fields=selected)
    body = request(purpose='GENERAL_CAE_RESEARCH', response={'field': selector})
    body['observation'].update(value=-.125, unit='1', quantity='PDE_SCALAR_FIELD', component='u',
        coordinate_frame='PDE_MODEL_CARTESIAN', tolerance=0., axis={'quantity': 'time', 'unit': '1', 'value': .25})
    return body


def test_pde_node_zero_comparison_roundtrip_keeps_signed_value_original_axis_and_unknowns(lab, pde_field_request):
    before = originals(lab)
    saved = lab.save_response_comparison(**pde_field_request)
    assert saved['schema_version'] == '1.4'
    comparison = saved['comparison']
    assert comparison['response_value'] == -.125 and comparison['difference'] == 0.
    assert comparison['source_field']['node_id'] == 0
    assert comparison['response_axis'] == {'quantity': 'time', 'unit': '1', 'value': .25}
    assert comparison['physical_validation'] == 'UNKNOWN' and comparison['decision'] == 'NOT_RELEASED'
    assert 'source_metric' not in comparison and 'source_channel' not in comparison
    assert lab.inspect_response_comparison('C-test') == saved
    assert lab.research_summary('E-test')['comparison_context']['records'][0]['record'] == saved
    assert originals(lab) == before


def test_pde_time_mismatch_preserves_original_response_with_null_comparison(lab, pde_field_request):
    pde_field_request['observation']['axis']['value'] = .5
    saved = lab.save_response_comparison(**pde_field_request)
    comparison = saved['comparison']
    assert comparison['status'] == 'DECLARED_AXIS_MISMATCH'
    assert comparison['response_value'] == -.125 and comparison['response_axis']['value'] == .25
    assert comparison['difference'] is None and comparison['within_declared_tolerance'] is None
    assert lab.inspect_response_comparison('C-test') == saved


@pytest.mark.parametrize('damage', ['unit', 'axis_unit', 'missing_axis', 'foreign_node', 'wrong_revision', 'caller_value'])
def test_pde_field_rejects_implicit_units_foreign_selection_and_caller_value_before_append(lab, pde_field_request, damage):
    body = deepcopy(pde_field_request)
    if damage == 'unit': body['observation']['unit'] = 'mm'
    elif damage == 'axis_unit': body['observation']['axis']['unit'] = 's'
    elif damage == 'missing_axis': body['observation'].pop('axis')
    elif damage == 'foreign_node': body['response']['field']['node_id'] = 1
    elif damage == 'wrong_revision': body['response']['field']['model_revision'] = '0' * 64
    else: body['response']['field']['value'] = -.125
    with pytest.raises((ValueError, ValidationError)):
        lab.save_response_comparison(**body)
    assert not (lab.store / 'response_comparisons/C-test').exists()
