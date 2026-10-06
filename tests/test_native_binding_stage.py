"""Private native registration stages, using persisted stand-in documents.

These tests start no FreeCAD process. The simulated two saves and independent
reopen exercise adapter publication boundaries, not native geometry acceptance.
"""

from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

from caelab.adapters import native_bridge
from caelab.adapters.fixture_freecad import FixtureFreeCADAdapter
from caelab.adapters.freecad_parameters import opaque_constraint
from caelab.contracts import Candidate, FileRevision


LEGACY = "LocatorProfile|constraint|0"
PROPERTY = "Block|property|Width"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def document_bytes(document):
    return (json.dumps(document, sort_keys=True) + "\n").encode("utf-8")


@pytest.fixture
def stage(tmp_path, monkeypatch):
    live = tmp_path / "native_designs" / "model" / "editable.FCStd"
    live.parent.mkdir(parents=True)
    document = {
        "final": "LocatorSolid", "save_count": 0,
        "parameters": [{"key": LEGACY, "name": "locator_radius", "label": "Original radius",
                        "min": 2.0, "max": 10.0, "unit": "mm", "object": "LocatorProfile",
                        "kind": "constraint", "constraint": "locator_radius", "value": 6.0}],
        "unregistered": [
            {"key": PROPERTY, "object": "Block", "object_label": "Native block",
             "dimension": "Width", "kind": "property", "value": 24.0, "unit": "mm"},
            {"key": "LocatorProfile|constraint|0", "object": "LocatorProfile",
             "object_label": "Native sketch", "dimension": "center_x", "kind": "constraint",
             "value": 2.0, "unit": "mm"}],
    }
    initial = document_bytes(document)
    live.write_bytes(initial)
    output = tmp_path / "private" / "binding"
    context = SimpleNamespace(live=live, output=output, initial=initial, document=document,
                              history=[], mode="normal", before_result=None, after_result=None,
                              on_phase=None, timeouts=[])

    def info(path, value=None):
        payload = path.read_bytes()
        value = json.loads(payload) if value is None else value
        sha = digest(payload)
        candidates = deepcopy(value["unregistered"])
        for item in candidates:
            if item["kind"] == "constraint":
                item["key"] = opaque_constraint(item, sha)
        return {"source_sha256": sha, "parameters": deepcopy(value["parameters"]),
                "candidates": candidates, "final": value["final"],
                "final_candidates": [{"name": "LocatorSolid", "label": "Locator solid"}],
                "document": "Simulated native document"}

    def run(command, **kwargs):
        worker = Path(native_bridge.__file__).resolve().with_name("freecad_parameter_worker.py")
        assert command == ["SIMULATED FREECAD", str(worker)]
        assert 0 < kwargs["timeout"] <= 150 and kwargs["cwd"] == native_bridge.UPSTREAM
        assert kwargs["stdout"] == subprocess.PIPE and kwargs["stderr"] == subprocess.PIPE and kwargs["text"]
        assert kwargs["env"]["CAELAB_FREECAD_PARAMETER_WORKER"] == str(worker)
        request_path = Path(kwargs["env"]["FIXTURE_FREECAD_REQUEST"])
        result_path = Path(kwargs["env"]["FIXTURE_FREECAD_RESULT"])
        request = json.loads(request_path.read_text(encoding="utf-8"))
        path = Path(request["document"])
        assert path == output / "editable.FCStd" and path != live
        phase = request_path.parent.name
        context.history.append((phase, deepcopy(request)))
        context.timeouts.append((phase, kwargs["timeout"]))
        if context.on_phase:
            context.on_phase(phase, path)
        value = json.loads(path.read_bytes())
        if request["action"] == "register":
            assert request["source_sha256"] == digest(initial)
            selected = next(item for item in info(path)["candidates"] if item["key"] == request["target"])
            original = next(item for item in value["unregistered"]
                            if item["object"] == selected["object"] and item["dimension"] == selected["dimension"])
            entry = {"key": original["key"], "name": request["name"], "label": request["label"],
                     "min": request["min"], "max": request["max"], "unit": "mm",
                     "object": selected["object"], "kind": selected["kind"], "value": selected["value"]}
            datum = "property" if selected["kind"] == "property" else "constraint"
            entry[datum] = selected["dimension"] if datum == "property" else request["name"]
            value["parameters"].append(entry)
            value["unregistered"].remove(original)
            value["save_count"] += 1
            if context.mode != "no-save":
                path.write_bytes(document_bytes(value))  # The pinned first save.
            if context.mode == "between-saves":
                result_path.write_text(json.dumps({"ok": False, "error": "SIMULATED_SECOND_SAVE_FAILED"}), encoding="utf-8")
                return SimpleNamespace(returncode=1, stdout="pinned save persisted\n", stderr="second save failed\n")
            entry["key"] = request["target"]
            value["save_count"] += 1
            if context.mode != "no-save":
                path.write_bytes(document_bytes(value))  # The owned literal-key save.
            answer = info(path, value)  # A successful in-memory answer alone is insufficient.
        else:
            answer = info(path)
            callback = context.before_result if phase == "inspect-before" else context.after_result
            if callback:
                callback(answer, path)
        result_path.write_text(json.dumps({"ok": True, "result": answer}), encoding="utf-8")
        return SimpleNamespace(returncode=0, stdout=request["action"] + " completed\n", stderr="")

    monkeypatch.setenv("FREECAD_CMD", "SIMULATED FREECAD")
    monkeypatch.setattr(native_bridge.subprocess, "run", run)
    monkeypatch.setattr(native_bridge.native_cad, "_path", lambda _: live)
    context.info = info
    context.request = {"model": "model", "target": PROPERTY, "source_sha256": digest(initial),
                       "parameter_id": "support_width", "display_name": "Support width",
                       "lower": 12.0, "upper": 36.0, "output": str(output)}
    return context


def prepare(stage, **changes):
    return native_bridge._prepare_bind({**stage.request, **changes})


@pytest.mark.parametrize("kind", ["property", "constraint"])
def test_private_stage_reopens_persisted_definition_and_keeps_live_bytes(stage, kind):
    request = dict(stage.request)
    if kind == "constraint":
        request.update(target=stage.info(stage.live)["candidates"][1]["key"],
                       parameter_id="center_offset", display_name="Center offset", lower=1.0, upper=8.0)
    answer = native_bridge._prepare_bind(request)
    assert set(answer) == {"target", "prepared", "before_sha256", "after_sha256"}
    assert Path(answer["target"]) == stage.live
    prepared = Path(answer["prepared"])
    assert prepared == stage.output / "editable.FCStd"
    assert stage.live.read_bytes() == stage.initial and answer["before_sha256"] == digest(stage.initial)
    assert answer["after_sha256"] == digest(prepared.read_bytes()) != answer["before_sha256"]
    saved = json.loads(prepared.read_bytes())
    assert saved["save_count"] == 2 and saved["parameters"][:-1] == stage.document["parameters"]
    entry = saved["parameters"][-1]
    assert entry["key"] == request["target"] and entry["name"] == request["parameter_id"]
    assert entry["label"] == request["display_name"] and (entry["min"], entry["max"]) == (request["lower"], request["upper"])
    if kind == "constraint":
        assert entry["constraint"] == "center_offset" and saved["parameters"][0]["key"] == LEGACY
    assert [phase for phase, _ in stage.history] == ["inspect-before", "register", "inspect-after"]
    for phase in ("inspect-before", "register", "inspect-after"):
        evidence = stage.output / phase
        assert all((evidence / name).is_file() for name in ("request.json", "result.json", "stdout.log", "stderr.log"))
        assert not (evidence / "failure.json").exists()


def test_failure_between_native_saves_keeps_partial_stage_and_worker_logs(stage):
    stage.mode = "between-saves"
    selector = stage.info(stage.live)["candidates"][1]["key"]
    with pytest.raises(ValueError, match="SIMULATED_SECOND_SAVE_FAILED"):
        prepare(stage, target=selector, parameter_id="center_offset", lower=1.0, upper=8.0)
    assert stage.live.read_bytes() == stage.initial
    partial = json.loads((stage.output / "editable.FCStd").read_bytes())
    assert partial["save_count"] == 1 and partial["parameters"][-1]["key"] == LEGACY
    assert partial["parameters"][-1]["constraint"] == "center_offset"
    failed = stage.output / "register"
    assert json.loads((failed / "failure.json").read_text())["code"] == "NATIVE_WORKER_FAILED"
    assert "pinned save persisted" in (failed / "stdout.log").read_text()
    assert "second save failed" in (failed / "stderr.log").read_text()
    assert not (stage.output / "inspect-after").exists()


def test_no_op_native_save_refuses_even_when_registration_returns_new_metadata(stage):
    stage.mode = "no-save"
    with pytest.raises(ValueError, match="NATIVE_STAGE_DEFINITION_MISMATCH"):
        prepare(stage)
    assert (stage.output / "editable.FCStd").read_bytes() == stage.initial
    returned = json.loads((stage.output / "register" / "result.json").read_text())["result"]
    reopened = json.loads((stage.output / "inspect-after" / "result.json").read_text())["result"]
    assert len(returned["parameters"]) == 2 and len(reopened["parameters"]) == 1
    assert stage.live.read_bytes() == stage.initial


@pytest.mark.parametrize("phase", ["inspect-before", "register", "inspect-after"])
def test_external_live_drift_during_stage_is_preserved_and_refused(stage, phase):
    external = b"UNRELATED EXTERNAL NATIVE EDIT\n"

    def drift(current, _path):
        if current == phase:
            stage.live.write_bytes(external)

    stage.on_phase = drift
    with pytest.raises(ValueError, match="NATIVE_SOURCE_CHANGED"):
        prepare(stage)
    assert stage.live.read_bytes() == external and (stage.output / "editable.FCStd").exists()


def test_stale_source_refuses_before_private_copy_or_native_worker(stage):
    stage.live.write_bytes(b"NEW LIVE REVISION\n")
    with pytest.raises(ValueError, match="NATIVE_SELECTOR_STALE"):
        prepare(stage)
    assert stage.history == [] and not stage.output.exists()


def test_missing_live_source_after_reopen_is_refused_without_restore(stage):
    stage.on_phase = lambda phase, _: stage.live.unlink() if phase == "inspect-after" else None
    with pytest.raises(ValueError, match="NATIVE_SOURCE_CHANGED"):
        prepare(stage)
    assert not stage.live.exists() and (stage.output / "editable.FCStd").is_file()


@pytest.mark.parametrize("historical_opaque", [False, True])
def test_registered_alias_preserves_native_name_label_bounds_and_historical_key(stage, historical_opaque):
    if historical_opaque:
        stage.document["parameters"][0]["key"] = "LocatorProfile|caelab-constraint-v1|" + "a" * 64 + "|8"
        stage.initial = document_bytes(stage.document)
        stage.live.write_bytes(stage.initial)
        stage.request["source_sha256"] = digest(stage.initial)
    target = stage.document["parameters"][0]["key"]
    answer = prepare(stage, target=target, parameter_id="research_radius", display_name="Research alias",
                     lower=3.0, upper=9.0)
    assert answer["before_sha256"] == answer["after_sha256"] == digest(stage.initial)
    assert Path(answer["prepared"]).read_bytes() == stage.initial == stage.live.read_bytes()
    assert [phase for phase, _ in stage.history] == ["inspect-before", "inspect-after"]
    assert json.loads(Path(answer["prepared"]).read_bytes())["parameters"] == stage.document["parameters"]


def test_registered_alias_cannot_widen_existing_native_bounds(stage):
    with pytest.raises(ValueError, match="bounds exceed"):
        prepare(stage, target=LEGACY, lower=1.0, upper=9.0)
    assert [phase for phase, _ in stage.history] == ["inspect-before"]
    assert (stage.output / "editable.FCStd").read_bytes() == stage.initial


@pytest.mark.parametrize("selector", ["LocatorProfile|constraint|5", "Block|property|Missing",
                                     "LocatorProfile|caelab-constraint-v1|" + "e" * 64 + "|0"])
def test_unadvertised_selector_never_reaches_registration(stage, selector):
    with pytest.raises(ValueError, match="NATIVE_SELECTOR_REDISCOVERY_REQUIRED"):
        prepare(stage, target=selector)
    assert [phase for phase, _ in stage.history] == ["inspect-before"]
    assert stage.live.read_bytes() == stage.initial


@pytest.mark.parametrize("field,value", [
    ("key", "Block|property|Wrong"), ("name", "wrong_name"), ("label", "Wrong label"),
    ("min", 11.0), ("max", 37.0), ("unit", "inch"), ("object", "OtherBlock"),
    ("kind", "constraint"), ("property", "Height"), ("value", 25.0),
])
def test_reopen_requires_literal_requested_definition(stage, field, value):
    def wrong(info, _path):
        info["parameters"][-1][field] = value
        if field == "kind":
            info["parameters"][-1]["constraint"] = "support_width"

    stage.after_result = wrong
    with pytest.raises(ValueError, match="NATIVE_STAGE_DEFINITION_MISMATCH"):
        prepare(stage)
    assert stage.live.read_bytes() == stage.initial


@pytest.mark.parametrize("change", ["prefix", "final", "missing", "extra"])
def test_reopen_requires_complete_unchanged_old_prefix_and_final(stage, change):
    def wrong(info, _path):
        if change == "prefix":
            info["parameters"][0]["label"] = "Mutated old definition"
        elif change == "final":
            info["final"] = "DifferentSolid"
        elif change == "missing":
            info["parameters"].pop(0)
        else:
            info["parameters"].append({**info["parameters"][-1], "key": "Third|property|Width",
                                       "name": "third_width", "object": "Third"})

    stage.after_result = wrong
    with pytest.raises(ValueError, match="NATIVE_STAGE_DEFINITION_MISMATCH"):
        prepare(stage)
    assert stage.live.read_bytes() == stage.initial


@pytest.mark.parametrize("stage_name", ["before", "after"])
@pytest.mark.parametrize("ambiguity,code", [
    ("key", "NATIVE_DUPLICATE_PATH"), ("name", "NATIVE_DUPLICATE_PARAMETER_NAME"),
    ("identity", "NATIVE_DUPLICATE_IDENTITY"), ("unsupported", "NATIVE_REGISTERED_UNSUPPORTED"),
])
def test_each_inspection_refuses_ambiguous_or_unsupported_registered_metadata(stage, stage_name, ambiguity, code):
    def wrong(info, _path):
        entry = {**info["parameters"][0], "key": "Alias|property|Length", "name": "alias_name"}
        if ambiguity == "key":
            entry["key"] = info["parameters"][0]["key"]
        elif ambiguity == "name":
            entry["name"] = info["parameters"][0]["name"]
            entry["object"] = "OtherSketch"
        elif ambiguity == "unsupported":
            entry["kind"] = "unsupported"
        info["parameters"].append(entry)

    setattr(stage, stage_name + "_result", wrong)
    with pytest.raises(ValueError, match=code):
        prepare(stage)
    if stage_name == "before":
        assert [phase for phase, _ in stage.history] == ["inspect-before"]
    assert stage.live.read_bytes() == stage.initial


@pytest.mark.parametrize("phase", ["before", "after"])
def test_prepared_file_drift_after_worker_inspection_is_refused(stage, phase):
    def drift(_info, path):
        path.write_bytes(path.read_bytes() + b"\n")

    setattr(stage, phase + "_result", drift)
    with pytest.raises(ValueError, match="NATIVE_SOURCE_CHANGED"):
        prepare(stage)
    assert stage.live.read_bytes() == stage.initial


def test_alias_file_rewrite_is_refused_even_if_definitions_are_unchanged(stage):
    def rewrite(phase, path):
        if phase == "inspect-after":
            value = json.loads(path.read_bytes())
            value["save_count"] += 1
            path.write_bytes(document_bytes(value))

    stage.on_phase = rewrite
    with pytest.raises(ValueError, match="NATIVE_STAGE_SAVE_MISMATCH"):
        prepare(stage, target=LEGACY, lower=3.0, upper=9.0)
    assert stage.live.read_bytes() == stage.initial


def test_private_stage_never_overwrites_an_existing_prepared_file(stage):
    stage.output.mkdir(parents=True)
    prepared = stage.output / "editable.FCStd"
    prepared.write_bytes(b"RETAINED EARLIER STAGE\n")
    with pytest.raises(FileExistsError):
        prepare(stage)
    assert prepared.read_bytes() == b"RETAINED EARLIER STAGE\n" and stage.history == []


def test_private_stage_cannot_target_the_live_file(stage):
    with pytest.raises(ValueError, match="NATIVE_STAGE_PATH_INVALID"):
        prepare(stage, output=str(stage.live.parent))
    assert stage.live.read_bytes() == stage.initial and stage.history == []


def test_initial_live_payload_is_read_once_then_the_same_bytes_are_staged(stage, monkeypatch):
    original = Path.read_bytes
    live_reads = []

    def read(path):
        if path == stage.live:
            live_reads.append(path)
        return original(path)

    monkeypatch.setattr(Path, "read_bytes", read)
    prepare(stage)
    assert len(live_reads) == 2  # One immutable payload, then the final live comparison.
    before = json.loads((stage.output / "inspect-before" / "result.json").read_text())["result"]
    assert before["source_sha256"] == digest(stage.initial)


def test_adapter_returns_generic_file_revision_and_preserves_existing_bind(stage, monkeypatch):
    adapter = FixtureFreeCADAdapter(stage.live.parents[2])
    candidate = Candidate(native={"backend": adapter.backend, "document": "model", "object": "Block", "path": PROPERTY},
                          label="Width", unit="mm", value=24.0, lower=None, upper=None,
                          source_sha256=digest(stage.initial))
    calls = []

    def call(action, **request):
        calls.append((action, request))
        if action == "prepare_bind":
            return native_bridge._prepare_bind(request)
        return {"source_sha256": "f" * 64}

    monkeypatch.setattr(adapter, "_call", call)
    revision = adapter.prepare_bind("model", candidate, "support_width", "Support width", 12.0, 36.0, stage.output)
    assert isinstance(revision, FileRevision) and revision.target == stage.live
    assert revision.prepared == stage.output / "editable.FCStd" and adapter.version == "4"
    assert revision.after_sha256 == digest(revision.prepared.read_bytes())
    assert calls[0][1]["source_sha256"] == candidate.source_sha256
    assert adapter.bind("model", candidate, "support_width", "Support width", 12.0, 36.0) == "f" * 64
    assert [action for action, _ in calls] == ["prepare_bind", "bind"]


def test_bridge_preparation_returns_only_generic_revision_metadata(stage, monkeypatch, capsys):
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"store": str(stage.live.parents[2]),
                                                           "action": "prepare_bind", **stage.request})))
    native_bridge.main()
    answer = json.loads(capsys.readouterr().out)
    assert set(answer) == {"target", "prepared", "before_sha256", "after_sha256"}
    assert answer["before_sha256"] == digest(stage.initial) and stage.live.read_bytes() == stage.initial


def test_timed_out_worker_retains_private_inputs_partial_outputs_and_original_bound(tmp_path, monkeypatch):
    evidence = tmp_path / "failed-worker"
    monkeypatch.setenv("FREECAD_CMD", "SIMULATED FREECAD")

    def timeout(command, **kwargs):
        assert kwargs["timeout"] == 150
        raise subprocess.TimeoutExpired(command, 150, output=b"PARTIAL NATIVE OUTPUT\n", stderr=b"PARTIAL NATIVE ERROR\n")

    monkeypatch.setattr(native_bridge.subprocess, "run", timeout)
    request = {"action": "inspect", "document": str(tmp_path / "private.FCStd")}
    with pytest.raises(subprocess.TimeoutExpired):
        native_bridge._parameter_run(request, evidence=evidence)
    assert json.loads((evidence / "request.json").read_text()) == request
    assert json.loads((evidence / "failure.json").read_text())["code"] == "NATIVE_WORKER_TIMEOUT"
    assert (evidence / "stdout.log").read_text() == "PARTIAL NATIVE OUTPUT\n"
    assert (evidence / "stderr.log").read_text() == "PARTIAL NATIVE ERROR\n"
    assert not (evidence / "result.json").exists()


def test_worker_evidence_never_overwrites_an_earlier_attempt(tmp_path, monkeypatch):
    evidence = tmp_path / "retained-worker"
    evidence.mkdir()
    (evidence / "request.json").write_text("EARLIER ATTEMPT", encoding="utf-8")
    monkeypatch.setenv("FREECAD_CMD", "SIMULATED FREECAD")
    monkeypatch.setattr(native_bridge.subprocess, "run", lambda *_a, **_k: pytest.fail("Evidence reuse launched a worker"))
    with pytest.raises(FileExistsError):
        native_bridge._parameter_run({"action": "inspect"}, evidence=evidence)
    assert (evidence / "request.json").read_text() == "EARLIER ATTEMPT"


def test_stage_worker_timeouts_share_one_monotonic_budget_and_leave_domain_requests_unchanged(stage, monkeypatch):
    clock = SimpleNamespace(now=500.0)
    monkeypatch.setattr(native_bridge.time, "monotonic", lambda: clock.now)
    durations = {"inspect-before": 40.0, "register": 60.0, "inspect-after": 10.0}

    def elapsed(phase, _path):
        clock.now += durations[phase]

    stage.on_phase = elapsed
    prepare(stage)
    assert stage.timeouts == [("inspect-before", 150.0), ("register", 110.0), ("inspect-after", 50.0)]
    for phase, elapsed_before, elapsed_after, remaining in (
            ("inspect-before", 0.0, 40.0, 150.0), ("register", 40.0, 100.0, 110.0),
            ("inspect-after", 100.0, 110.0, 50.0)):
        evidence = stage.output / phase
        inputs = json.loads((evidence / "runtime-inputs.json").read_text())
        result = json.loads((evidence / "runtime-result.json").read_text())
        assert inputs == {"schema": 1, "phase": phase, "budget_seconds": 150,
                          "stage_start_monotonic_seconds": 500.0,
                          "phase_start_monotonic_seconds": 500.0 + elapsed_before,
                          "elapsed_seconds": elapsed_before, "remaining_seconds": remaining}
        assert result["status"] == "COMPLETED" and result["worker_attempted"] is True
        assert result["elapsed_seconds"] == elapsed_after
        assert result["phase_elapsed_seconds"] == durations[phase]
        assert result["remaining_seconds"] == 150.0 - elapsed_after
        request = json.loads((evidence / "request.json").read_text())
        assert not set(request) & {"timeout", "runtime_inputs", "budget_seconds", "remaining_seconds", "deadline"}
    assert stage.live.read_bytes() == stage.initial


@pytest.mark.parametrize("later_phase,readings,expected_history", [
    ("inspect-before", [500.0, 650.0, 650.0], []),
    ("register", [500.0, 500.0, 600.0, 650.0, 650.0], ["inspect-before"]),
    ("inspect-after", [500.0, 500.0, 540.0, 540.0, 640.0, 650.0, 650.0],
     ["inspect-before", "register"]),
])
def test_expired_budget_refuses_next_worker_before_start_and_retains_private_evidence(stage, monkeypatch, later_phase, readings, expected_history):
    values = iter(readings)
    monkeypatch.setattr(native_bridge.time, "monotonic", lambda: next(values, 650.0))
    with pytest.raises(ValueError, match="^NATIVE_STAGE_TIMEOUT:"):
        prepare(stage)
    assert [phase for phase, _ in stage.history] == expected_history
    refused = stage.output / later_phase
    inputs = json.loads((refused / "runtime-inputs.json").read_text())
    result = json.loads((refused / "runtime-result.json").read_text())
    assert inputs["remaining_seconds"] == 0 and inputs["elapsed_seconds"] == 150.0
    assert result["status"] == "REFUSED_BEFORE_START" and result["worker_attempted"] is False
    assert json.loads((refused / "stage-failure.json").read_text())["code"] == "NATIVE_STAGE_TIMEOUT"
    assert (refused / "request.json").is_file() and not (refused / "result.json").exists()
    assert not (refused / "stdout.log").exists() and not (refused / "stderr.log").exists()
    prepared = stage.output / "editable.FCStd"
    assert prepared.exists() and stage.live.read_bytes() == stage.initial
    if later_phase == "inspect-after":
        assert json.loads(prepared.read_bytes())["save_count"] == 2


def test_registered_alias_reopen_uses_the_same_budget_and_cannot_start_after_expiry(stage, monkeypatch):
    values = iter([500.0, 500.0, 600.0, 651.0, 651.0])
    monkeypatch.setattr(native_bridge.time, "monotonic", lambda: next(values, 651.0))
    with pytest.raises(ValueError, match="NATIVE_STAGE_TIMEOUT"):
        prepare(stage, target=LEGACY, lower=3.0, upper=9.0)
    assert [phase for phase, _ in stage.history] == ["inspect-before"]
    assert not (stage.output / "register").exists()
    assert (stage.output / "editable.FCStd").read_bytes() == stage.initial == stage.live.read_bytes()
    result = json.loads((stage.output / "inspect-after" / "runtime-result.json").read_text())
    assert result["elapsed_seconds"] == 151.0 and result["remaining_seconds"] == 0
    assert result["worker_attempted"] is False


def test_stage_timeout_retains_partial_native_outputs_and_raises_only_fixed_refusal(stage, monkeypatch):
    clock = SimpleNamespace(now=500.0)
    monkeypatch.setattr(native_bridge.time, "monotonic", lambda: clock.now)
    original = native_bridge.subprocess.run

    def timeout(command, **kwargs):
        request_path = Path(kwargs["env"]["FIXTURE_FREECAD_REQUEST"])
        if request_path.parent.name == "register":
            assert kwargs["timeout"] == 110.0
            path = Path(json.loads(request_path.read_text())["document"])
            path.write_bytes(b"SIMULATED PARTIAL NATIVE SAVE\n")
            clock.now += kwargs["timeout"]
            raise subprocess.TimeoutExpired(["RAW COMMAND SENTINEL"], kwargs["timeout"],
                                            output=b"PARTIAL OUTPUT SENTINEL\n", stderr=b"PARTIAL ERROR SENTINEL\n")
        return original(command, **kwargs)

    stage.on_phase = lambda phase, _: setattr(clock, "now", clock.now + 40.0) if phase == "inspect-before" else None
    monkeypatch.setattr(native_bridge.subprocess, "run", timeout)
    with pytest.raises(ValueError, match="^NATIVE_STAGE_TIMEOUT:") as refusal:
        prepare(stage)
    assert "SENTINEL" not in str(refusal.value) and refusal.value.__suppress_context__
    failed = stage.output / "register"
    assert json.loads((failed / "failure.json").read_text())["code"] == "NATIVE_WORKER_TIMEOUT"
    assert json.loads((failed / "stage-failure.json").read_text())["code"] == "NATIVE_STAGE_TIMEOUT"
    assert (failed / "stdout.log").read_text() == "PARTIAL OUTPUT SENTINEL\n"
    assert (failed / "stderr.log").read_text() == "PARTIAL ERROR SENTINEL\n"
    result = json.loads((failed / "runtime-result.json").read_text())
    assert result == {"schema": 1, "status": "TIMED_OUT", "worker_attempted": True,
                      "elapsed_seconds": 150.0, "phase_elapsed_seconds": 110.0, "remaining_seconds": 0}
    assert not (stage.output / "inspect-after").exists() and not (failed / "result.json").exists()
    assert (stage.output / "editable.FCStd").read_bytes() == b"SIMULATED PARTIAL NATIVE SAVE\n"
    assert stage.live.read_bytes() == stage.initial


def test_last_worker_return_after_deadline_cannot_produce_file_revision(stage, monkeypatch):
    clock = SimpleNamespace(now=500.0)
    monkeypatch.setattr(native_bridge.time, "monotonic", lambda: clock.now)

    def elapsed(phase, _path):
        clock.now += {"inspect-before": 60.0, "register": 60.0, "inspect-after": 30.0}[phase]

    stage.on_phase = elapsed
    with pytest.raises(ValueError, match="NATIVE_STAGE_TIMEOUT"):
        prepare(stage)
    assert stage.timeouts == [("inspect-before", 150.0), ("register", 90.0), ("inspect-after", 30.0)]
    result = json.loads((stage.output / "inspect-after" / "runtime-result.json").read_text())
    assert result["status"] == "EXPIRED_AFTER_RETURN" and result["remaining_seconds"] == 0
    assert (stage.output / "inspect-after" / "result.json").is_file()
    assert json.loads((stage.output / "inspect-after" / "stage-failure.json").read_text())["code"] == "NATIVE_STAGE_TIMEOUT"
    assert json.loads((stage.output / "editable.FCStd").read_bytes())["save_count"] == 2
    assert stage.live.read_bytes() == stage.initial


def test_stage_budget_wrapper_does_not_overwrite_existing_phase_evidence(stage):
    phase = stage.output / "inspect-before"
    phase.mkdir(parents=True)
    retained = phase / "runtime-result.json"
    retained.write_bytes(b"RETAINED EARLIER PHASE\n")
    with pytest.raises(FileExistsError):
        prepare(stage)
    assert retained.read_bytes() == b"RETAINED EARLIER PHASE\n" and stage.history == []
    assert stage.live.read_bytes() == stage.initial
    assert (stage.output / "editable.FCStd").read_bytes() == stage.initial
