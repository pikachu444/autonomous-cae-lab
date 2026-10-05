"""HTTP integration/security checks using real Core and bounded fault adapters."""

from contextlib import contextmanager
import hashlib
from http.client import HTTPConnection
import io
import json
from pathlib import Path
import threading
import time
from urllib.parse import urlencode
import zipfile

import pytest

from apps.lab.server import LabHTTPServer, MAX_BODY
from apps.lab.service import LabService, OPERATIONS
from caelab import Lab
from caelab.adapters.fixture_cadquery import FixtureCadQueryAdapter
from caelab.contracts import Outcome
from caelab.storage import save_json


class Client:
    def __init__(self, server):
        self.server = server
        self.token = None

    def request(self, path, body=None, *, headers=None, expected=200, raw=False, method=None):
        options = {}
        payload = None
        if body is not None:
            payload = body if isinstance(body, bytes) else json.dumps(body, allow_nan=False).encode()
            options.update({"Content-Type": "application/json", "X-CAE-Token": self.token or ""})
        options.update(headers or {})
        connection = HTTPConnection("127.0.0.1", self.server.server_port, timeout=30)
        try:
            connection.request(method or ("POST" if body is not None else "GET"), path,
                               body=payload, headers=options)
            response = connection.getresponse()
            data = response.read()
            response_headers = dict(response.getheaders())
            assert response.status == expected, (path, response.status, data[:1500])
            assert "Access-Control-Allow-Origin" not in response_headers
            return (data, response_headers) if raw else json.loads(data)
        finally:
            connection.close()

    def job(self, operation, arguments, *, expected_status="COMPLETED"):
        job = self.request("/api/jobs", {"operation": operation, "arguments": arguments}, expected=202)
        assert job["status"] == "RUNNING"
        return self.finish(job["id"], expected_status=expected_status)

    def finish(self, identifier, *, expected_status="COMPLETED", observation_timeout=40, poll_interval=.02):
        deadline = time.monotonic() + observation_timeout
        while True:
            job = self.request("/api/jobs/" + identifier)
            if job["status"] != "RUNNING":
                assert job["status"] == expected_status, job
                return job
            assert time.monotonic() < deadline, job
            time.sleep(poll_interval)


@contextmanager
def running(service):
    server = LabHTTPServer(service, 0)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": .02}, daemon=True)
    thread.start()
    client = Client(server)
    client.token = client.request("/api/overview")["token"]
    try:
        yield client
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def study_arguments(identifier="S-http"):
    return {"study_id": identifier, "name": "로컬 연구", "research_question": "형상 변화가 검증되는가?",
            "hypothesis": "폭 변경은 형상을 바꾼다.", "objective": "수치·증거와 UNKNOWN 보존"}


def test_http_recovered_job_and_original_result_remain_readable(tmp_path):
    from apps.lab.job_journal import HTTPJobJournal
    store = tmp_path / "retained"
    first = LabService(store, http_journal=HTTPJobJournal(store))
    with running(first) as client:
        terminal = client.job("study_create", study_arguments("S-retained-http"))
    restored = LabService(store, http_journal=HTTPJobJournal(store))
    with running(restored) as client:
        assert client.request("/api/jobs/" + terminal["id"]) == terminal
        assert client.request("/api/overview")["execution"]["state"] == "IDLE"


def test_http_foreign_claim_without_job_still_blocks_new_execution(tmp_path):
    from apps.lab.job_journal import HTTPJobJournal
    store = tmp_path / "broken"
    journal = HTTPJobJournal(store)
    (journal.root / "claim.json").write_text('{"kind":"FOREIGN"}', encoding="utf-8")
    restored = LabService(store, http_journal=HTTPJobJournal(store))
    with running(restored) as client:
        overview = client.request("/api/overview")
        assert overview["execution"]["state"] == "RECOVERY_REQUIRED"
        assert overview["execution"]["recovered_job_ids"] == []
        assert overview["execution"]["idle_confirmed"] is False
        client.request("/api/jobs", {"operation": "study_create", "arguments": study_arguments()}, expected=503)
    assert not list(store.glob("studies/*"))


def registration(native="support_width_mm", identifier="support_width", lower=28, upper=60):
    return {"study_id": "S-http", "backend": "fixture.cadquery", "model": "roller_support",
            "native_path": native, "parameter_id": identifier, "display_name": identifier,
            "lower": lower, "upper": upper}


@pytest.mark.parametrize("phase", ["before", "after"])
def test_campaign_rechecks_payload_around_core_inspection(real_flow, monkeypatch, tmp_path, phase):
    client, service, _, _ = real_flow
    lab = service._selected().lab
    folder = tmp_path / ("C-wire-" + phase)
    # Only the service wiring is synthetic. The referenced CAD experiment and
    # its original, hash-registered bytes came from the real Core fixture.
    save_json(folder / "plan.json", {"test_only": True, "cad_experiment_id": "E-valid"})
    # Keep synthetic routing outside the shared real_flow store. The real
    # campaign/overview tests must see only campaigns they actually planned.
    monkeypatch.setattr(service, "_campaign", lambda selected, identifier: ("optimization", folder))
    target = lab.store / "experiments/E-valid/cad/assembly.step"
    original = target.read_bytes()
    calls = []

    def inspect(identifier):
        calls.append(identifier)
        if phase == "after":
            target.write_bytes(original + b"TEST ONLY: changed during aggregate inspection")
        return {"test_only": True}

    monkeypatch.setattr(lab, "inspect_optimization", inspect)
    try:
        if phase == "before":
            target.write_bytes(original + b"TEST ONLY: changed before aggregate inspection")
        client.request("/api/campaigns/" + folder.name, expected=400)
        assert calls == ([] if phase == "before" else [folder.name])
    finally:
        target.write_bytes(original)


@pytest.fixture
def client(tmp_path):
    library = tmp_path / "library"
    Lab(library).create_study(**study_arguments("S-history"))
    with running(LabService(tmp_path / "local", libraries={"history": library})) as client:
        yield client


@pytest.fixture(scope="module")
def real_flow(tmp_path_factory):
    root = tmp_path_factory.mktemp("lab-http-core")
    service = LabService(root / "local")
    with running(service) as client:
        client.job("study_create", study_arguments())
        discovered = client.job("parameter_discover", {"backend": "fixture.cadquery", "model": "roller_support"})["result"]
        assert {"support_width_mm", "bolt_pitch_x_mm"} <= {c["native"]["path"] for c in discovered}
        client.job("parameter_register", registration())
        client.job("parameter_register", registration("bolt_pitch_x_mm", "bolt_pitch", 18, 40))
        accepted = client.job("cad_run", {"study_id": "S-http", "experiment_id": "E-valid",
            "backend": "fixture.cadquery", "model": "roller_support", "values": {"support_width": 38}})["result"]
        rejected = client.job("cad_run", {"study_id": "S-http", "experiment_id": "E-invalid",
            "backend": "fixture.cadquery", "model": "roller_support", "values": {"bolt_pitch": 30}})["result"]
        yield client, service, accepted, rejected


@pytest.mark.parametrize("backend", ["structural.code_aster", "structural.code_aster.plasticity",
                                    "structural.code_aster.geometric_nonlinearity",
                                    "material.mfront", "material.mfront.hyperelastic", "explicit.openradioss"])
def test_declared_backend_http_dispatch_retains_preflight_rejection_without_cad_parent(client, backend):
    client.job("study_create", study_arguments())
    result = client.job("model_analysis_run", {"study_id": "S-http", "experiment_id": "E-model-invalid",
                                              "backend": backend, "settings": {}})["result"]
    assert result["status"] == "REJECTED" and result["solver_status"] == "NOT_RUN"
    assert result["cad_revision"] is None and "parent_experiment_id" not in result
    assert result["decision"] == "NOT_RELEASED"
    retained = client.request("/api/experiments/E-model-invalid")
    assert retained["result"] == result
    assert {"model_qualification", "physical_validation"} <= set(retained["summary"]["unknown"])


def test_rectangle_pde_http_uses_declared_geometry_and_blocks_conflicting_boundaries(client, monkeypatch):
    """Actual HTTP/Core metadata; the solve below is explicitly a test stand-in."""
    from copy import deepcopy
    from caelab.adapters.fenicsx_rectangle import FenicsxRectanglePDEAdapter
    from plugins.pde_elliptic.reference import manufactured_settings
    from caelab.storage import canonical_hash

    calls = []

    def solve(self, output, settings):
        calls.append(deepcopy(settings))
        output.mkdir()
        save_json(output / "test_only.json", {"test_only": True, "settings": settings})
        return {"status": "COMPLETED", "solver_status": "COMPLETED", "converged": True,
            "checks": [{"code": "test_transport", "status": "PASS", "observed": "TEST ONLY: no native solve"}],
            "metrics": {"test_observation": {"value": 1.0, "unit": "1", "valid": True}},
            "pending_validations": ["model_qualification", "physical_validation"],
            "provenance": {"test_only": True}, "raw_result": "pde/test_only.json"}

    monkeypatch.setattr(FenicsxRectanglePDEAdapter, "solve", solve)
    client.job("study_create", study_arguments())
    preset = client.request("/api/presets")["pde_rectangle"]
    assert preset["operation"] == "pde_run" and preset["declared_inputs"] is False
    first_bytes = None
    revisions = []
    for suffix, settings in (("first", preset["settings"]),
                              ("changed", manufactured_settings(lengths=(1.5, .75), diffusion=2.0))):
        experiment = "E-http-rectangle-" + suffix
        result = client.job("pde_run", {"study_id": "S-http", "experiment_id": experiment,
            "backend": preset["backend"], "settings": settings})["result"]
        declaration = FenicsxRectanglePDEAdapter().describe_model(settings)
        assert result["model_revision"] == canonical_hash({"settings": settings, "declaration": declaration})
        assert result["extensions"]["pde"]["declaration"] == declaration
        assert result["cad_revision"] is None and "parent_experiment_id" not in result
        assert result["decision"] == "NOT_RELEASED"
        inspected = client.request("/api/experiments/" + experiment)
        assert inspected["integrity"] == "VERIFIED" and inspected["result"] == result
        assert {"model_qualification", "physical_validation"} <= set(inspected["summary"]["unknown"])
        payload, _ = client.request("/api/artifacts/" + experiment + "?path=pde%2Ftest_only.json", raw=True)
        if suffix == "first":
            first_bytes = payload
        revisions.append(result["model_revision"])
    assert len(calls) == 2 and len(set(revisions)) == 2
    invalid = deepcopy(preset["settings"])
    invalid["problem"]["boundaries"]["xmin"]["value"] = "2*x[1]+2"
    blocked = client.job("pde_run", {"study_id": "S-http", "experiment_id": "E-http-rectangle-blocked",
        "backend": preset["backend"], "settings": invalid})["result"]
    assert blocked["status"] == "REJECTED" and blocked["solver_status"] == "NOT_RUN" and len(calls) == 2
    assert blocked["metrics"] == {} and blocked["decision"] == "NOT_RELEASED"
    payload, _ = client.request("/api/artifacts/E-http-rectangle-first?path=pde%2Ftest_only.json", raw=True)
    assert payload == first_bytes


def test_allowlisted_operations_change_actual_core_and_retain_verdicts(real_flow):
    client, service, accepted, rejected = real_flow
    assert accepted["status"] == "COMPLETED_REVIEW_REQUIRED"
    assert rejected["status"] == "REJECTED"
    assert accepted["decision"] == rejected["decision"] == "NOT_RELEASED"
    assert not (service._selected().path / "experiments/E-invalid/cad/assembly.step").exists()
    study = client.request("/api/studies/S-http")
    assert study["study"]["name"] == "로컬 연구"
    assert {r["parameter_id"] for r in study["registry"]["entries"]} == {"support_width", "bolt_pitch"}
    overview = client.request("/api/overview")
    assert all(row["integrity"] == "NOT_CHECKED" for row in overview["experiments"])
    assert set(OPERATIONS) <= {row["operation"] for row in overview["capabilities"]}
    assert all(not row["callable"] for row in overview["capabilities"] if row["status"] == "PLANNED")
    inspected = client.request("/api/experiments/E-valid")
    assert inspected["integrity"] == "VERIFIED"
    assert inspected["result"] == accepted
    assert inspected["summary"]["unknown"]
    comparison = client.request("/api/compare?ids=E-valid,E-invalid")
    assert [row["status"] for row in comparison] == [accepted["status"], rejected["status"]]


def test_existing_presets_and_core_campaign_inspection(real_flow):
    from scripts.verify_pde import specification as pde_spec
    from scripts.verify_codeaster import specification as aster_spec
    client, service, _, _ = real_flow
    presets = client.request("/api/presets")
    assert set(presets) == {"structural_linear", "pde_canonical", "pde_nonlinear", "pde_rectangle",
                            "pde_transient_mesh", "pde_transient_time", "pde_vector_lame", "pde_vector_harmonic", "pde_coupled_interface", "pde_coupled_harmonic", "pde_imported_l_shape", "pde_imported_harmonic", "codeaster_linear",
                            "codeaster_plasticity", "codeaster_geometric", "material_point", "material_inverse", "material_hyperelastic", "material_viscoelastic", "explicit_freefall",
                            "explicit_ground_stop", "explicit_compliant_stop"} | {
        f"family_{case}_{load}_{solver}" for case, load in (
            ("ansys_vmd1_regular", "Fx"), ("ansys_vmd1_regular", "Fy"), ("ansys_vmd1_regular", "Fz"),
            ("lame_cylinder_plane_strain", "pressure"), ("scordelis_lo_solid", "gravity"))
        for solver in ("calculix", "code_aster")}
    assert presets["pde_canonical"]["settings"] == pde_spec()
    assert presets["codeaster_linear"]["settings"] == aster_spec()
    assert presets["structural_linear"]["settings"]["material"]["qualification"] == "ASSUMED_NOT_MEASURED"
    assert presets["structural_linear"]["operation"] == "analysis_run"
    assert presets["structural_linear"]["parent_backends"] == ["fixture.cadquery"]
    assert presets["pde_canonical"]["operation"] == "pde_run"
    from plugins.pde_elliptic.reference import manufactured_settings
    assert presets["pde_rectangle"]["settings"] == manufactured_settings()
    assert presets["pde_rectangle"]["operation"] == "pde_run"
    assert presets["pde_rectangle"]["declared_inputs"] is False
    from plugins.pde_transient.reference import manufactured_settings as transient_settings
    assert presets["pde_transient_mesh"]["settings"] == transient_settings()
    assert presets["pde_transient_time"]["settings"] == transient_settings(axis="time", case="temporal")
    assert all(presets[key]["operation"] == "pde_run" and presets[key]["backend"] == "pde.fenicsx.transient"
               and presets[key]["declared_inputs"] is False and "UNKNOWN" in presets[key]["scope"]
               for key in ("pde_transient_mesh", "pde_transient_time"))
    from plugins.pde_vector.reference import manufactured_settings as vector_spec
    assert presets["pde_vector_lame"]["settings"] == vector_spec()
    assert presets["pde_vector_harmonic"]["settings"] == vector_spec(case="harmonic")
    assert all(presets[key]["operation"] == "pde_run" and presets[key]["backend"] == "pde.fenicsx.vector"
               and presets[key]["declared_inputs"] is False and "UNKNOWN" in presets[key]["scope"]
               for key in ("pde_vector_lame", "pde_vector_harmonic"))
    from plugins.pde_coupled.reference import manufactured_settings as coupled_spec
    assert presets["pde_coupled_interface"]["settings"] == coupled_spec()
    assert presets["pde_coupled_harmonic"]["settings"] == coupled_spec(case="harmonic")
    assert all(presets[key]["operation"] == "pde_run" and presets[key]["backend"] == "pde.fenicsx.coupled"
               and presets[key]["declared_inputs"] is False and "UNKNOWN" in presets[key]["scope"]
               for key in ("pde_coupled_interface", "pde_coupled_harmonic"))
    from caelab.adapters.fenicsx_imported import manufactured_settings as imported_spec
    assert presets["pde_imported_l_shape"]["settings"] == imported_spec()
    assert presets["pde_imported_harmonic"]["settings"] == imported_spec(case="harmonic")
    assert all(presets[key]["operation"] == "pde_run" and presets[key]["backend"] == "pde.fenicsx.imported"
               and presets[key]["declared_inputs"] is False and "UNKNOWN" in presets[key]["scope"]
               for key in ("pde_imported_l_shape", "pde_imported_harmonic"))
    assert all(preset["operation"] == "model_analysis_run" for key, preset in presets.items()
               if preset["operation"] != "pde_run" and key != "structural_linear")
    assert presets["explicit_ground_stop"]["status"] == "REJECTED"
    plan = client.job("doe_plan", {"study_id": "S-http", "campaign_id": "D-http",
        "backend": "fixture.cadquery", "model": "roller_support", "parameter_ids": ["support_width"],
        "sample_count": 2, "seed": 10})["result"]
    assert plan["campaign_id"] == "D-http"
    inspected = client.request("/api/campaigns/D-http")
    assert inspected["type"] == "doe"
    assert inspected["record"] == service._selected().lab.inspect_doe("D-http")
    assert {row["id"] for row in client.request("/api/overview")["campaigns"]} == {"D-http"}


@pytest.mark.parametrize("headers", [
    {"X-CAE-Token": ""}, {"X-CAE-Token": "wrong"}, {"Origin": "https://example.com"},
    {"Origin": "null"}, {"Host": "example.com:8766"}, {"Host": "localhost:1"},
    {"Sec-Fetch-Site": "cross-site"},
])
def test_post_token_origin_and_host_guards(client, headers):
    response = client.request("/api/jobs", {"operation": "study_create", "arguments": study_arguments()},
                              headers=headers, expected=403)
    assert response["error"]
    assert client.request("/api/overview")["studies"] == []


def test_foreign_get_origin_and_duplicate_host_are_rejected(client):
    client.request("/api/overview", headers={"Origin": "http://example.com"}, expected=403)
    connection = HTTPConnection("127.0.0.1", client.server.server_port)
    try:
        connection.putrequest("GET", "/api/overview")
        connection.putheader("Host", f"localhost:{client.server.server_port}")
        connection.endheaders()
        response = connection.getresponse()
        assert response.status == 403
        response.read()
    finally:
        connection.close()
    client.request("/api/overview", headers={"Host": f"localhost:{client.server.server_port}",
                   "Origin": f"http://localhost:{client.server.server_port}"})


@pytest.mark.parametrize("body", [
    {"operation": "__getattribute__", "arguments": {"name": "store"}},
    {"operation": "import_native_model", "arguments": {"source": "/etc/passwd"}},
    {"operation": "study_create", "arguments": {**study_arguments(), "store": "/tmp/other"}},
    {"operation": "native_create", "arguments": {"template": "../../other.py"}},
    {"operation": "native_inspect", "arguments": {"model": "C:\\private\\model.FCStd"}},
    {"operation": "parameter_discover", "arguments": {"backend": "fixture.cadquery", "model": "/tmp/model"}},
    {"operation": "study_create", "arguments": {}},
    {"operation": "study_create", "arguments": study_arguments(), "command": "whoami"},
])
def test_dispatch_rejects_unknown_operations_extra_keywords_and_client_paths(client, body):
    client.request("/api/jobs", body, expected=400)
    assert client.request("/api/overview")["jobs"] == []


@pytest.mark.parametrize("body,headers,status", [
    (b'[]', {}, 400), (b'{"operation": "study_create", "operation": "cad_run"}', {}, 400),
    (b'{"value": NaN}', {}, 400), (b'{"value": 1e999}', {}, 400),
    (b'{}', {"Content-Type": "text/plain"}, 415), (b' ' * (MAX_BODY + 1), {}, 413),
])
def test_post_requires_bounded_unambiguous_json(client, body, headers, status):
    client.request("/api/jobs", body, headers=headers, expected=status)
    assert client.request("/api/overview")["jobs"] == []


def file_hashes(root):
    return {path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in root.rglob("*") if path.is_file()}


def test_configured_library_is_read_only_and_path_selection_is_rejected(client):
    library = client.server.service._stores["history"].path
    before = file_hashes(library)
    selected = client.request("/api/store", {"id": "history"})
    assert selected["active_store"] == "history"
    assert selected["stores"] == [{"id": "local", "label": "local", "writable": True},
                                   {"id": "history", "label": "history", "writable": False}]
    assert client.request("/api/studies/S-history")["study"]["id"] == "S-history"
    client.request("/api/jobs", {"operation": "study_create", "arguments": study_arguments()}, expected=403)
    for operation in ("model_parameters_register", "model_optimization_plan"):
        client.request("/api/jobs", {"operation": operation, "arguments": {}}, expected=403)
    client.job("parameter_discover", {"backend": "fixture.cadquery", "model": "roller_support"})
    client.request("/api/store", {"id": str(library)}, expected=400)
    client.request("/api/store", {"id": "local", "path": str(library)}, expected=400)
    assert file_hashes(library) == before
    client.request("/api/store", {"id": "local"})
    client.job("study_create", study_arguments())


def test_http_declared_input_metadata_uses_common_registry_and_plan_without_native(client, monkeypatch):
    from caelab.adapters.codeaster_elasticity import CodeAsterElasticityAdapter
    from scripts.verify_codeaster import specification

    # Only runtime identity is synthetic: the actual domain declarations,
    # parameter registry, bound checks and shared plan are exercised through HTTP.
    monkeypatch.setattr(CodeAsterElasticityAdapter, "input_runtime_identity",
                        lambda self: {"test_only": "No external runtime is executed"})
    def unexpected_solve(*args, **kwargs):
        raise AssertionError("Metadata operations must not run a native solver")
    monkeypatch.setattr(CodeAsterElasticityAdapter, "solve", unexpected_solve)
    client.job("study_create", study_arguments())
    arguments = {"backend": "structural.code_aster", "settings": specification()}
    discovered = client.job("model_parameters_discover", arguments)["result"]
    assert len(discovered) == 1 and discovered[0]["native"]["path"] == "youngs_modulus_mpa"
    registered = client.job("model_parameters_register", {
        **arguments, "study_id": "S-http", "input_id": "youngs_modulus_mpa",
        "parameter_id": "modulus", "display_name": "Elastic modulus",
        "lower": 100000, "upper": 300000})["result"]
    assert registered["parameter_id"] == "modulus"
    plan = client.job("model_optimization_plan", {
        **arguments, "study_id": "S-http", "campaign_id": "C-model-http", "parameter_ids": ["modulus"],
        "objective": {"source": "model", "metric": "axial_tip_displacement", "unit": "mm", "direction": "maximize"},
        "constraints": [], "seed": 13, "initial_values": {"modulus": 210000}})["result"]
    assert plan["route"] == "model_analysis" and plan["backend"] == "structural.code_aster"
    root = client.server.service._selected().path
    assert not (root / "experiments").exists()
    assert (root / "optimizations/C-model-http/plan.json").is_file()
    library = client.server.service._stores["history"].path
    before = file_hashes(library)
    client.request("/api/store", {"id": "history"})
    client.job("model_parameters_discover", arguments)
    assert file_hashes(library) == before


def test_presets_advertise_complete_bindings_without_descriptor_or_runtime_calls(client, monkeypatch):
    adapters = client.server.service._selected().lab.model_analysis_adapters

    def unexpected_call(*args, **kwargs):
        raise AssertionError("Preset metadata must not discover, admit or solve")

    for backend in ("structural.code_aster", "material.mfront.inverse"):
        for name in ("describe_model", "describe_inputs", "bind_inputs", "input_runtime_identity", "solve"):
            monkeypatch.setattr(adapters[backend], name, unexpected_call)
    presets = client.request("/api/presets")
    assert {key for key, value in presets.items() if value["declared_inputs"]} == {
        "codeaster_linear", "material_inverse"}
    # A source/runtime declaration alone is insufficient. A missing binding
    # must immediately withdraw the model from the UI's advertised choices.
    monkeypatch.setattr(adapters["material.mfront.inverse"], "bind_inputs", None)
    assert not client.request("/api/presets")["material_inverse"]["declared_inputs"]


def test_http_model_campaign_run_exposes_verified_model_records_and_reuses_them(tmp_path):
    from test_model_parameters import STUDY, synthetic_lab, template_settings

    # Real Core/HTTP/SciPy, explicitly synthetic domain observations. No native
    # solver or provider call, and no numerical physics acceptance is claimed.
    lab, adapter = synthetic_lab(tmp_path / "local")
    service = LabService(lab.store, lab_factory=lambda path: lab)
    with running(service) as client:
        arguments = {"backend": adapter.backend, "settings": template_settings()}
        discovered = client.job("model_parameters_discover", arguments)["result"]
        assert discovered[0]["native"]["path"] == "input_x"
        client.job("model_parameters_register", {**arguments, "study_id": STUDY,
            "input_id": "input_x", "parameter_id": "research_x", "display_name": "TEST ONLY X",
            "lower": 0.0, "upper": 4.0})
        plan = client.job("model_optimization_plan", {**arguments, "study_id": STUDY,
            "campaign_id": "C-model-http-run", "parameter_ids": ["research_x"], "seed": 13,
            "objective": {"source": "model", "metric": "synthetic_objective", "unit": "1", "direction": "minimize"},
            "constraints": [], "initial_values": {"research_x": 1.0},
            "required_validations": {"model": ["synthetic_check"]}})["result"]
        assert plan["route"] == "model_analysis"
        job = client.request("/api/jobs", {"operation": "optimization_run",
            "arguments": {"campaign_id": plan["campaign_id"]}}, expected=202)
        result = client.finish(job["id"], observation_timeout=300, poll_interval=.2)["result"]
        assert result["decision"] == "NOT_RELEASED" and result["termination"]["evaluation_count"] > 5
        inspected = client.request("/api/campaigns/" + plan["campaign_id"])
        assert inspected["record"] == result
        for row in result["evaluations"]:
            assert not {"cad_experiment_id", "analysis_experiment_id"}.intersection(row)
            experiment = client.request("/api/experiments/" + row["model_experiment_id"])
            assert experiment["integrity"] == "VERIFIED"
            assert experiment["result"]["campaign_id"] == plan["campaign_id"]
            assert experiment["result"]["decision"] == "NOT_RELEASED"
        before = file_hashes(lab.store)
        calls = adapter.calls
        replay = client.request("/api/jobs", {"operation": "optimization_run",
            "arguments": {"campaign_id": plan["campaign_id"]}}, expected=202)
        assert client.finish(replay["id"], observation_timeout=300, poll_interval=.2)["result"] == result
        assert adapter.calls == calls and file_hashes(lab.store) == before


def test_single_writer_blocks_second_job_and_store_switch_while_reads_work(tmp_path):
    entered, release = threading.Event(), threading.Event()

    class BlockingAdapter(FixtureCadQueryAdapter):
        def discover(self, model):
            entered.set()
            assert release.wait(timeout=10)
            return super().discover(model)

    library = tmp_path / "library"
    library.mkdir()
    service = LabService(tmp_path / "local", libraries={"history": library},
                         lab_factory=lambda path: Lab(path, adapters={"fixture.cadquery": BlockingAdapter()}))
    with running(service) as client:
        first = client.request("/api/jobs", {"operation": "parameter_discover",
            "arguments": {"backend": "fixture.cadquery", "model": "roller_support"}}, expected=202)
        try:
            assert entered.wait(timeout=2)
            assert client.request("/api/jobs/" + first["id"])["status"] == "RUNNING"
            client.request("/api/jobs", {"operation": "study_create", "arguments": study_arguments()}, expected=409)
            client.request("/api/store", {"id": "history"}, expected=409)
            assert client.request("/api/overview")["active_store"] == "local"
        finally:
            release.set()
        client.finish(first["id"])
        client.job("study_create", study_arguments())


def test_failed_job_retains_partial_core_experiment_and_visible_error(tmp_path):
    local = tmp_path / "local"
    original = Lab(local)
    original.create_study(**study_arguments())
    original.register_parameter(**registration())

    class FailingIdentityAdapter(FixtureCadQueryAdapter):
        def preflight_effects(self, model, values):
            return []

        def regenerate(self, model, values, output):
            output.mkdir()
            (output / "partial.txt").write_text("retained adapter evidence")
            return Outcome(decision="REJECTED", checks=[], generated=False)

        def source_commit(self):
            raise RuntimeError("bounded provenance failure after partial output")

    service = LabService(local, lab_factory=lambda path: Lab(path, adapters={"fixture.cadquery": FailingIdentityAdapter()}))
    with running(service) as client:
        failed = client.job("cad_run", {"study_id": "S-http", "experiment_id": "E-partial",
            "backend": "fixture.cadquery", "model": "roller_support", "values": {"support_width": 38}},
            expected_status="FAILED")
        assert "bounded provenance failure" in failed["error"]
        assert client.request("/api/jobs/" + failed["id"])["error"] == failed["error"]
        partial = local / "experiments/E-partial/cad/partial.txt"
        assert partial.read_text() == "retained adapter evidence"
        row = client.request("/api/overview")["experiments"][0]
        assert row["id"] == "E-partial" and row["error"] and row["integrity"] == "NOT_CHECKED"
        client.request("/api/experiments/E-partial", expected=404)
        client.job("study_create", study_arguments("S-after-failure"))
        assert partial.read_text() == "retained adapter evidence"


@pytest.mark.parametrize("relative,status", [
    ("../../study.json", 400), ("/etc/passwd", 400), ("C:\\private\\file", 400),
    ("cad/../report.html", 400), ("cad\\report.html", 400), ("result.json", 404),
])
def test_artifact_path_and_manifest_restrictions(real_flow, relative, status):
    client, _, _, _ = real_flow
    client.request("/api/artifacts/E-valid?" + urlencode({"path": relative}), expected=status)


def test_verified_artifact_downloads_reports_bundles_and_tamper_refusal(real_flow):
    client, service, _, _ = real_flow
    root = service._selected().path
    before = file_hashes(root)
    artifact, headers = client.request("/api/artifacts/E-valid?path=cad%2Freport.html", raw=True)
    assert headers["Content-Disposition"].startswith("attachment")
    assert headers["Content-Type"] == "application/octet-stream"
    assert artifact == (root / "experiments/E-valid/cad/report.html").read_bytes()
    html, headers = client.request("/api/report/E-valid.html", raw=True)
    assert b"NOT_RELEASED" in html and b"UNKNOWN" in html
    assert headers["Content-Type"].startswith("text/html")
    assert client.request("/api/report/E-valid.json")["integrity"] == "VERIFIED"
    bundle, headers = client.request("/api/report/E-valid.zip", raw=True)
    assert headers["Content-Type"] == "application/zip"
    with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
        manifest = json.loads(archive.read("bundle_manifest.json"))
        for row in manifest["files"]:
            data = archive.read(row["path"])
            assert len(data) == row["size_bytes"]
            assert hashlib.sha256(data).hexdigest() == row["sha256"]
    assert file_hashes(root) == before
    report = root / "experiments/E-valid/cad/report.html"
    original = report.read_bytes()
    try:
        report.write_bytes(b"modified")
        client.request("/api/experiments/E-valid", expected=400)
        client.request("/api/report/E-valid.zip", expected=400)
        client.request("/api/artifacts/E-valid?path=cad%2Freport.html", expected=400)
        client.request("/api/compare?ids=E-valid,E-invalid", expected=400)
    finally:
        report.write_bytes(original)


def test_symlink_escape_is_refused_before_artifact_read(real_flow, tmp_path):
    client, service, _, _ = real_flow
    report = service._selected().path / "experiments/E-valid/cad/report.html"
    original = report.read_bytes()
    outside = tmp_path / "outside.html"
    outside.write_bytes(original)
    report.unlink()
    try:
        try:
            report.symlink_to(outside)
        except OSError as exc:
            pytest.skip(f"Host does not permit symlink creation: {exc}")
        client.request("/api/artifacts/E-valid?path=cad%2Freport.html", expected=400)
        client.request("/api/experiments/E-valid", expected=400)
    finally:
        report.unlink(missing_ok=True)
        report.write_bytes(original)


def test_compare_limits_static_paths_and_pinned_viewer(client):
    client.request("/api/compare?ids=E1,E1", expected=400)
    client.request("/api/compare?ids=" + ",".join(f"E{i}" for i in range(13)), expected=400)
    client.request("/static/%2e%2e/server.py", expected=404)
    client.request("/api/overview?store=/tmp", expected=400)
    client.request("/api/jobs/not-known", expected=404)
    viewer, headers = client.request("/upstream/surface_viewer.js", raw=True)
    pinned = Path(__file__).resolve().parents[1] / "plugins/fixture_design/upstream/fixturelab/surface_viewer.js"
    assert viewer == pinned.read_bytes()
    assert headers["Content-Type"].startswith("text/javascript")


def test_fixture_conditions_script_and_form_are_served_from_the_same_source(client):
    page, _ = client.request("/", raw=True)
    controls, headers = client.request("/static/fixture-controls.js", raw=True)
    static = Path(__file__).resolve().parents[1] / "apps/lab/static"
    assert controls == (static / "fixture-controls.js").read_bytes()
    assert headers["Content-Type"].startswith("text/javascript")
    assert page.index(b'/static/fixture-controls.js') < page.index(b'/static/app.js')
    assert b'data-fixture-field="force_N"' in page
    assert b'data-fixture-field="provenance"' in page


def test_declared_campaign_controls_are_served_before_their_ui_consumer(client):
    static = Path(__file__).resolve().parents[1] / "apps/lab/static"
    controls, headers = client.request("/static/campaign-controls.js", raw=True)
    page, _ = client.request("/", raw=True)
    assert controls == (static / "campaign-controls.js").read_bytes()
    assert headers["Content-Type"].startswith("text/javascript")
    assert page.index(b'/static/campaign-controls.js') < page.index(b'/static/app.js')
    assert b'id="campaignTarget"' in page and b'id="modelRegisterForm"' in page


def test_imported_mesh_controls_are_served_before_bounded_file_selection(client):
    static = Path(__file__).resolve().parents[1] / "apps/lab/static"
    controls, headers = client.request("/static/imported-mesh-controls.js", raw=True)
    page, _ = client.request("/", raw=True)
    assert controls == (static / "imported-mesh-controls.js").read_bytes()
    assert headers["Content-Type"].startswith("text/javascript")
    assert page.index(b'/static/imported-mesh-controls.js') < page.index(b'/static/app.js')
    assert b'id="importedMeshFiles" type="file" accept=".msh" multiple' in page
    assert b'id="importedMeshSummary"' in page and b'id="importedMeshError"' in page


def test_retained_pde_field_reader_is_served_before_the_results_consumer(client):
    static = Path(__file__).resolve().parents[1] / "apps/lab/static"
    reader, headers = client.request("/static/pde-field-inspector.js", raw=True)
    page, _ = client.request("/", raw=True)
    assert reader == (static / "pde-field-inspector.js").read_bytes()
    assert headers["Content-Type"].startswith("text/javascript")
    assert page.index(b'/static/pde-field-inspector.js') < page.index(b'/static/app.js')


def test_retained_contact_field_reader_is_served_before_the_results_consumer(client):
    static = Path(__file__).resolve().parents[1] / "apps/lab/static"
    reader, headers = client.request("/static/contact-field-inspector.js", raw=True)
    page, _ = client.request("/", raw=True)
    assert reader == (static / "contact-field-inspector.js").read_bytes()
    assert headers["Content-Type"].startswith("text/javascript")
    assert page.index(b'/static/contact-field-inspector.js') < page.index(b'/static/app.js')


def test_writable_and_readonly_store_overlap_is_rejected(tmp_path):
    library = tmp_path / "store/history"
    library.mkdir(parents=True)
    with pytest.raises(ValueError, match="must not overlap"):
        LabService(tmp_path / "store", libraries={"history": library})


@pytest.mark.parametrize("operation", ["native_inspect", "native_final", "parameter_discover"])
@pytest.mark.parametrize("alias", ["directory", "file"])
def test_native_model_symlink_escape_is_denied_before_adapter_call(tmp_path, monkeypatch, operation, alias):
    service = LabService(tmp_path / "local")
    selected = service._selected()
    model = "a" * 32  # A valid pinned-upstream native design ID.
    native_root = selected.path / "native_designs"
    native_root.mkdir()
    outside = tmp_path / "outside-native"
    outside.mkdir()
    document = outside / "editable.FCStd"
    document.write_bytes(b"outside document must never be read or changed")
    target = native_root / model
    try:
        if alias == "directory":
            target.symlink_to(outside, target_is_directory=True)
        else:
            target.mkdir()
            (target / "editable.FCStd").symlink_to(document)
    except OSError as exc:
        pytest.skip(f"Host does not permit symlink creation: {exc}")
    before = file_hashes(outside)
    calls = []

    def unexpected_native_call(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("Native read/mutation must be blocked before the adapter")

    monkeypatch.setattr(selected.lab.adapters["fixture.freecad"], "_call", unexpected_native_call)
    arguments = {"model": model}
    if operation == "native_final":
        arguments["final"] = "Part"
    elif operation == "parameter_discover":
        arguments["backend"] = "fixture.freecad"
    with running(service) as client:
        rejected = client.request("/api/jobs", {"operation": operation, "arguments": arguments}, expected=400)
        assert "escapes" in rejected["error"]
        assert client.request("/api/overview")["jobs"] == []
    assert not calls
    assert file_hashes(outside) == before
