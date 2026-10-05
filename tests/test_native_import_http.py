"""Real HTTP/Core dispatch with TEST_ONLY native collaborators; no FreeCAD invocation."""

import hashlib
import io
import json
import threading
import zipfile

import pytest

from apps.lab import native_input
from apps.lab.job_journal import HTTPJobJournal
from apps.lab.service import LabService
from test_lab_server import running


@pytest.fixture(autouse=True)
def test_only_producer(monkeypatch):
    # These tests verify transport/job/storage, not the repository Git probe.
    monkeypatch.setattr(native_input, "source_identity", lambda _root: {"TEST_ONLY": True})


def payload(size=800):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr("Document.xml", "<Document name='TEST_ONLY_HTTP_TRANSPORT'/>")
        archive.writestr("TEST_ONLY.bin", b"x" * size)
    return stream.getvalue()


def native(service, monkeypatch, *, wait=None, mutate=None):
    calls = []
    def import_document(source):
        raw = source.read_bytes()
        calls.append((source, raw))
        if wait:
            wait[0].set()
            assert wait[1].wait(10)
        identifier = "native-test-" + str(len(calls))
        root = service._selected().path / "native_designs" / identifier
        root.mkdir(parents=True, exist_ok=False)
        (root / "editable.FCStd").write_bytes(raw)
        if mutate:
            mutate(source)
        return {"design": identifier, "document": "TEST_ONLY native collaborator",
                "source_sha256": hashlib.sha256(raw).hexdigest(), "final": None,
                "final_candidates": [], "parameters": [], "candidates": []}
    monkeypatch.setattr(service._selected().lab, "import_native_model", import_document)
    return calls


def upload(client, raw, **kwargs):
    headers = {"Content-Type": "application/octet-stream", **kwargs.pop("headers", {})}
    return client.request("/api/native-import", raw, headers=headers, expected=kwargs.pop("expected", 202), **kwargs)


def test_binary_upload_retains_bytes_appends_imports_and_reopens_after_restart(tmp_path, monkeypatch):
    store = tmp_path / "store"
    store.mkdir()
    original = store / "historical-cad.FCStd"
    original.write_bytes(b"TEST_ONLY OLD CAD MUST NOT CHANGE")
    service = LabService(store, http_journal=HTTPJobJournal(store))
    calls = native(service, monkeypatch)
    raw = payload(140 * 1024)  # Binary route is separate from JSON's128KiB bound.
    with running(service) as client:
        first = client.finish(upload(client, raw)["id"])
        second = client.finish(upload(client, raw)["id"])
        assert first["result"]["design"] != second["result"]["design"]
        imported = first["result"]["native_import"]
        assert imported["original_integrity"] == "VERIFIED"
        assert imported["input"] == {"sha256": hashlib.sha256(raw).hexdigest(), "size_bytes": len(raw)}
        root = store / "native_imports" / imported["id"]
        assert (root / "original.FCStd").read_bytes() == raw
        listing = client.request("/api/native-imports")
        assert len(listing["imports"]) == 2 and listing["omitted"] == 0
        assert all(item["original_integrity"] == "NOT_CHECKED" for item in listing["imports"])
        selected = client.request("/api/native-imports/" + imported["id"])
        assert selected["model"] == first["result"]["design"]
        assert selected["original_integrity"] == "VERIFIED" and selected["current_native_revision"] == "NOT_CHECKED"
        # Explicit later native editing is distinct from the preserved uploaded input.
        (store / "native_designs" / selected["model"] / "editable.FCStd").write_bytes(b"TEST_ONLY LATER NATIVE EDIT")
        assert client.request("/api/native-imports/" + imported["id"])["original_integrity"] == "VERIFIED"
    restored = LabService(store, http_journal=HTTPJobJournal(store))
    with running(restored) as client:
        assert client.request("/api/jobs/" + first["id"]) == first
        assert client.request("/api/native-imports/" + imported["id"])["input"] == imported["input"]
        assert client.request("/api/overview")["execution"]["state"] == "IDLE"
    assert len(calls) == 2 and all(item[1] == raw for item in calls)
    assert original.read_bytes() == b"TEST_ONLY OLD CAD MUST NOT CHANGE"


def test_slow_producer_is_observed_as_an_owned_async_job(tmp_path, monkeypatch):
    service = LabService(tmp_path / "store")
    calls = native(service, monkeypatch)
    entered, release = threading.Event(), threading.Event()
    def producer(_root):
        entered.set()
        assert release.wait(10)
        return {"TEST_ONLY": "blocked producer"}
    monkeypatch.setattr(native_input, "source_identity", producer)
    try:
        with running(service) as client:
            job = upload(client, payload())
            assert entered.wait(5)
            assert client.request("/api/jobs/" + job["id"])["status"] == "RUNNING"
            upload(client, payload(), expected=409)
            assert calls == [], "Native execution waits for the producer capture"
            release.set()
            assert client.finish(job["id"])["result"]["native_import"]["original_integrity"] == "VERIFIED"
    finally:
        release.set()
    assert len(calls) == 1


def test_cancel_during_metadata_capture_blocks_native_and_keeps_original(tmp_path, monkeypatch):
    service = LabService(tmp_path / "store")
    calls = native(service, monkeypatch)
    entered, release = threading.Event(), threading.Event()
    raw = payload()
    def producer(_root):
        entered.set()
        assert release.wait(10)
        return {"TEST_ONLY": "blocked producer"}
    monkeypatch.setattr(native_input, "source_identity", producer)
    try:
        with running(service) as client:
            job = upload(client, raw)
            assert entered.wait(5)
            assert client.request("/api/jobs/" + job["id"] + "/cancel", {}, expected=202)["status"] == "CANCEL_REQUESTED"
            release.set()
            service._job_threads[job["id"]].join(5)
            assert not service._job_threads[job["id"]].is_alive()
            cancelled = client.finish(job["id"], expected_status="CANCELLED")
            assert cancelled["cancel_observed"] is True and not cancelled["cleanup_pending"]
            assert client.request("/api/native-imports")["imports"][0]["status"] == "UNCONFIRMED"
    finally:
        release.set()
    assert calls == []
    assert next(service._selected().path.glob("native_imports/*/original.FCStd")).read_bytes() == raw


@pytest.mark.parametrize("raw", [b"x" * 99, b"x" * 100, b"x" * 1000])
def test_invalid_input_stops_before_native_or_storage(tmp_path, monkeypatch, raw):
    service = LabService(tmp_path / "store")
    calls = native(service, monkeypatch)
    with running(service) as client:
        upload(client, raw, expected=400)
    assert calls == [] and not (service._selected().path / "native_imports").exists()


def test_zip_without_native_history_is_refused(tmp_path, monkeypatch):
    service = LabService(tmp_path / "store")
    calls = native(service, monkeypatch)
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("ordinary.txt", b"TEST_ONLY_NOT_FCSTD" * 10)
    with running(service) as client:
        upload(client, stream.getvalue(), expected=400)
    assert calls == [] and not (service._selected().path / "native_imports").exists()


def test_transport_guards_and_json_path_injection(tmp_path, monkeypatch):
    service = LabService(tmp_path / "store")
    calls = native(service, monkeypatch)
    raw = payload()
    with running(service) as client:
        upload(client, raw, headers={"X-CAE-Token": "wrong"}, expected=403)
        upload(client, raw, headers={"Origin": "https://external.test"}, expected=403)
        upload(client, raw, headers={"Host": "external.test"}, expected=403)
        upload(client, raw, headers={"Content-Type": "application/json"}, expected=415)
        upload(client, b"", headers={"Content-Length": str(native_input.MAX_NATIVE_BYTES + 1)}, expected=413)
        upload(client, b"", headers={"Transfer-Encoding": "chunked"}, expected=400)
        client.request("/api/native-import?path=C%3A%2Foutside.FCStd", raw,
                       headers={"Content-Type": "application/octet-stream"}, expected=400)
        client.request("/api/jobs", {"operation": "native_import", "arguments": {"source": "C:/outside.FCStd"}}, expected=400)
        client.request("/api/jobs", b" " * (128 * 1024 + 1), expected=413)
    assert calls == [] and not (service._selected().path / "native_imports").exists()


def test_readonly_and_busy_block_before_input_creation(tmp_path, monkeypatch):
    library = tmp_path / "library"
    library.mkdir()
    sentinel = library / "original.bin"
    sentinel.write_bytes(b"TEST_ONLY READONLY")
    service = LabService(tmp_path / "store", libraries={"history": library})
    entered, release = threading.Event(), threading.Event()
    calls = native(service, monkeypatch, wait=(entered, release))
    try:
        with running(service) as client:
            client.request("/api/store", {"id": "history"})
            upload(client, payload(), expected=403)
            assert not (library / "native_imports").exists()
            client.request("/api/store", {"id": "local"})
            first = upload(client, payload())
            assert entered.wait(5)
            upload(client, payload(), expected=409)
            client.request("/api/store", {"id": "history"}, expected=409)
            assert len(list((service._selected().path / "native_imports").iterdir())) == 1
            release.set()
            client.finish(first["id"])
    finally:
        release.set()
    assert len(calls) == 1 and sentinel.read_bytes() == b"TEST_ONLY READONLY"


@pytest.mark.parametrize("when", ["before", "during_producer", "after"])
def test_original_drift_rejects_without_success_record(tmp_path, monkeypatch, when):
    service = LabService(tmp_path / "store")
    if when == "before":
        retain = native_input.retain_input
        def changed(store, raw):
            capture = retain(store, raw)
            target = native_input.folder(store, capture["id"]) / "original.FCStd"
            target.write_bytes(raw + b"TEST_ONLY DRIFT")
            return capture
        monkeypatch.setattr(native_input, "retain_input", changed)
    if when == "during_producer":
        def changed_producer(_root):
            target = next(service._selected().path.glob("native_imports/*/original.FCStd"))
            target.write_bytes(target.read_bytes() + b"TEST_ONLY DRIFT")
            return {"TEST_ONLY": "changed input during producer capture"}
        monkeypatch.setattr(native_input, "source_identity", changed_producer)
    calls = native(service, monkeypatch, mutate=(lambda path: path.write_bytes(path.read_bytes() + b"TEST_ONLY DRIFT")) if when == "after" else None)
    with running(service) as client:
        result = client.finish(upload(client, payload())["id"], expected_status="FAILED")
        assert "Retained original native bytes changed" in result["error"]
        assert "result" not in result
    assert len(calls) == (1 if when == "after" else 0)
    assert not list(service._selected().path.glob("native_imports/*/import.json"))


def test_namespace_escape_blocks_before_write(tmp_path, monkeypatch):
    service = LabService(tmp_path / "store")
    calls = native(service, monkeypatch)
    outside = tmp_path / "outside"
    outside.mkdir()
    (service._selected().path / "native_imports").symlink_to(outside, target_is_directory=True)
    with running(service) as client:
        upload(client, payload(), expected=400)
    assert calls == [] and not list(outside.iterdir())


def test_final_original_guard_failure_keeps_partial_without_completion_seal(tmp_path, monkeypatch):
    service = LabService(tmp_path / "store")
    calls = native(service, monkeypatch)
    save = native_input._save_new
    def changed(path, value):
        result = save(path, value)
        if path.name == "import.json":
            original = path.parent / "original.FCStd"
            original.write_bytes(original.read_bytes() + b"TEST_ONLY LATE DRIFT")
        return result
    monkeypatch.setattr(native_input, "_save_new", changed)
    with running(service) as client:
        result = client.finish(upload(client, payload())["id"], expected_status="FAILED")
        assert "Retained original native bytes changed" in result["error"]
        listing = client.request("/api/native-imports")["imports"]
        assert len(listing) == 1 and listing[0]["status"] == "UNCONFIRMED"
        assert "model" not in listing[0]
    root = next(service._selected().path.glob("native_imports/*"))
    assert (root / "import.json").exists() and not (root / "import-receipt.json").exists()
    assert len(calls) == 1


def test_inspection_detects_input_result_and_capture_corruption(tmp_path, monkeypatch):
    service = LabService(tmp_path / "store")
    native(service, monkeypatch)
    with running(service) as client:
        result = client.finish(upload(client, payload())["id"])["result"]
        identifier = result["native_import"]["id"]
        root = native_input.folder(service._selected().path, identifier)
        result_file = root / "import.json"
        original_result = result_file.read_bytes()
        result_file.write_bytes(original_result + b" ")
        client.request("/api/native-imports/" + identifier, expected=400)
        result_file.write_bytes(original_result)
        original_input = (root / "original.FCStd").read_bytes()
        (root / "original.FCStd").write_bytes(original_input + b"TEST_ONLY_DRIFT")
        client.request("/api/native-imports/" + identifier, expected=400)
        # List remains metadata-only and does not claim original verification.
        assert client.request("/api/native-imports")["imports"][0]["original_integrity"] == "NOT_CHECKED"
        (root / "original.FCStd").write_bytes(original_input)
        changed = json.loads(original_result)
        changed["capture"]["id"] = "U" + "0" * 32
        raw = json.dumps(changed).encode()
        result_file.write_bytes(raw)
        receipt = json.loads((root / "import-receipt.json").read_bytes())
        receipt["result"] = {"sha256": hashlib.sha256(raw).hexdigest(), "size_bytes": len(raw)}
        (root / "import-receipt.json").write_text(json.dumps(receipt))
        client.request("/api/native-imports/" + identifier, expected=400)
