"""TEST_ONLY HTTP crash/identity controls; no solver, provider or old runs."""

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import uuid

import pytest

from apps.lab.job_journal import HTTPJobJournal, JournalError
from apps.lab.service import LabService, ServiceError


class MetadataLab:
    pde_adapters = {}

    def __init__(self, store):
        self.store = Path(store)
        self.calls = []

    def create_study(self, name):
        self.calls.append(name)
        return {"test_only": True, "name": name, "decision": "NOT_RELEASED"}


def service(store, **options):
    return LabService(store, lab_factory=MetadataLab,
                      http_journal=HTTPJobJournal(store), **options)


def finish(lab, identifier):
    lab._job_threads[identifier].join(5)
    assert not lab._job_threads[identifier].is_alive()
    return lab.job(identifier)


def intent():
    return {"id": "J" + uuid.uuid4().hex, "operation": "study_create", "status": "RUNNING",
            "store_id": "local", "created_utc": "TEST_ONLY", "cancel_requested": False,
            "cancel_observed": False, "cleanup_pending": False, "cleanup_owners": []}


def reserve(store):
    journal = HTTPJobJournal(store)
    job = intent()
    journal.reserve(job, {"name": "TEST_ONLY"})
    return journal, job


def test_completed_id_and_original_result_survive_fresh_service(tmp_path):
    first = service(tmp_path)
    job = first.submit("study_create", {"name": "원본"})
    terminal = finish(first, job["id"])
    assert terminal["status"] == "COMPLETED"
    frozen = {p: p.read_bytes() for p in (tmp_path / "_http_job_control/jobs" / job["id"]).iterdir()}
    second = service(tmp_path)
    assert second.job(job["id"]) == terminal
    assert second._selected().lab.calls == []
    assert second.execution_status()["idle_confirmed"]
    assert all(p.read_bytes() == raw for p, raw in frozen.items())
    assert not (tmp_path / "_http_job_control/claim.json").exists()


@pytest.mark.parametrize("damage", ["claim_association", "torn_release", "torn_claim", "foreign_claim", "torn_observation"])
def test_recovered_cancel_survives_uncertain_terminal_association(tmp_path, damage):
    journal, pending = reserve(tmp_path)
    terminal = {**pending, "status": "COMPLETED", "completed_utc": "TEST_ONLY",
                "result": {"test_only": True, "partial_observation": "preserved"}}
    journal._append(pending["id"], "TERMINAL", terminal)
    folder = tmp_path / "_http_job_control/jobs" / pending["id"]
    if damage == "claim_association":
        claim_path = tmp_path / "_http_job_control/claim.json"
        claim = json.loads(claim_path.read_text())
        claim["nonce"] = uuid.uuid4().hex
        claim_path.write_text(json.dumps(claim))
    elif damage == "torn_release":
        (folder / "000002.json").write_text("{")
    elif damage == "torn_claim":
        (tmp_path / "_http_job_control/claim.json").write_text("{")
    elif damage == "foreign_claim":
        claim_path = tmp_path / "_http_job_control/claim.json"
        claim = json.loads(claim_path.read_text())
        claim["schema_version"] = 999
        claim_path.write_text(json.dumps(claim))
    else:
        (tmp_path / "_http_job_control/observations" / ("0" * 32 + ".json")).write_text("{")
    preserved = {p: p.read_bytes() for p in folder.iterdir()}
    first = service(tmp_path)
    assert first.job(pending["id"])["status"] == "RECOVERY_REQUIRED"
    first.cancel(pending["id"])
    for _ in range(2):
        restored = service(tmp_path)
        job = restored.job(pending["id"])
        assert job["status"] == "RECOVERY_REQUIRED" and job["outcome"] == "UNKNOWN"
        assert job["cancel_requested"] and job["cancel_observed"] is False
        assert job["retained_status"] == "COMPLETED"
        assert job["result"] == terminal["result"]
        assert not restored._job_tokens and not restored._job_threads
        assert restored.execution_status()["idle_confirmed"] is False
    assert all(p.read_bytes() == raw for p, raw in preserved.items())


def test_recovered_cancel_observation_cannot_change_intact_completed_history(tmp_path):
    first = service(tmp_path)
    pending = first.submit("study_create", {"name": "TEST_ONLY intact terminal"})
    terminal = finish(first, pending["id"])
    first._http_journal.cancellation_intent(pending["id"])
    restored = service(tmp_path)
    assert restored.job(pending["id"]) == terminal
    assert restored.execution_status()["idle_confirmed"]


@pytest.mark.parametrize("damage", ["torn", "schema"])
def test_corrupt_current_claim_preserves_separate_completed_history(tmp_path, damage):
    first = service(tmp_path)
    completed = first.submit("study_create", {"name": "TEST_ONLY preserved history"})
    original = finish(first, completed["id"])
    first._http_journal.cancellation_intent(completed["id"])
    journal, pending = reserve(tmp_path)
    journal.append(pending["id"], "WORKER_STARTED", pending)
    claim_path = journal.root / "claim.json"
    if damage == "torn":
        claim_path.write_text("{")
    else:
        claim = json.loads(claim_path.read_text())
        claim["schema_version"] = 999
        claim_path.write_text(json.dumps(claim))
    frozen = {p: p.read_bytes() for p in journal.root.rglob("*")
              if p.is_file() and p.name != "journal.lock"}
    restored = service(tmp_path)
    restored.cancel(pending["id"])
    for _ in range(2):
        restored = service(tmp_path)
        assert restored.job(completed["id"]) == original
        current = restored.job(pending["id"])
        assert current["status"] == "RECOVERY_REQUIRED" and current["outcome"] == "UNKNOWN"
        assert current["cancel_requested"] and current["cancel_observed"] is False
        assert not restored.execution_status()["accepting_jobs"]
        assert not restored.execution_status()["idle_confirmed"]
        assert not restored._job_tokens and not restored._job_threads
        with pytest.raises(ServiceError):
            restored.submit("study_create", {"name": "forbidden replay"})
    assert all(p.read_bytes() == raw for p, raw in frozen.items())


def test_worker_start_failure_is_durable_and_does_not_call_operation(tmp_path, monkeypatch):
    lab = service(tmp_path)
    monkeypatch.setattr(threading.Thread, "start", lambda self: (_ for _ in ()).throw(RuntimeError("TEST_ONLY start failure")))
    with pytest.raises(RuntimeError, match="start failure"):
        lab.submit("study_create", {"name": "never"})
    assert lab._selected().lab.calls == []
    restored = service(tmp_path)
    job = restored.overview()["jobs"][0]
    assert job["status"] == "FAILED" and "start failure" in job["error"]
    assert restored.execution_status()["idle_confirmed"]


@pytest.mark.parametrize("stage", ["before_worker", "during_worker"])
def test_actual_controller_exit_after_admission_recovers_unknown_without_replay(tmp_path, stage):
    # Actual tiny Python controller, not a fake source identity or native run.
    code = '''
import os, sys, threading
from pathlib import Path
from apps.lab.job_journal import HTTPJobJournal
from apps.lab.service import LabService
class Metadata:
    pde_adapters = {}
    def __init__(self, store): self.store = Path(store)
    def create_study(self, name):
        (self.store / "PARTIAL_TEST_ONLY").write_text(name)
        os._exit(24)
store = Path(sys.argv[1])
lab = LabService(store, lab_factory=Metadata, http_journal=HTTPJobJournal(store))
if sys.argv[2] == "before_worker": threading.Thread.start = lambda self: os._exit(23)
lab.submit("study_create", {"name": "TEST_ONLY"})
threading.Event().wait(5)
'''
    child = subprocess.Popen([sys.executable, "-c", code, str(tmp_path), stage], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = child.communicate(timeout=15)
    assert child.returncode == (23 if stage == "before_worker" else 24), (stdout, stderr)
    journal = HTTPJobJournal(tmp_path)
    recovered = LabService(tmp_path, lab_factory=MetadataLab, http_journal=journal)
    job = recovered.overview()["jobs"][0]
    assert job["status"] == "RECOVERY_REQUIRED" and job["outcome"] == "UNKNOWN"
    assert recovered._active_job is None and not recovered._job_tokens and not recovered._job_threads
    partial = tmp_path / "PARTIAL_TEST_ONLY"
    assert partial.exists() is (stage == "during_worker")
    if partial.exists():
        assert partial.read_text() == "TEST_ONLY"
    with pytest.raises(ServiceError, match="recovery"):
        recovered.submit("study_create", {"name": "second"})
    assert recovered.cancel(job["id"])["cancel_observed"] is False
    report = recovered.shutdown(timeout=0)
    assert report["joined"] and report["recovery_required"] and report["pending"]
    assert recovered.execution_status()["idle_confirmed"] is False
    restart = '''
import json, sys
from pathlib import Path
from apps.lab.job_journal import HTTPJobJournal
from apps.lab.service import LabService
store = Path(sys.argv[1])
lab = LabService(store, http_journal=HTTPJobJournal(store))
print(json.dumps({"job": lab.job(sys.argv[2]), "execution": lab.execution_status(),
                  "has_handles": bool(lab._job_tokens or lab._job_threads or lab._active_job),
                  "shutdown": lab.shutdown(timeout=0)}))
'''
    # Two actual fresh Python controllers must restore intent without acquiring
    # native reconnect/cancel authority or replaying the admitted operation.
    for _ in range(2):
        reader = subprocess.Popen([sys.executable, "-c", restart, str(tmp_path), job["id"]],
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = reader.communicate(timeout=15)
        assert reader.returncode == 0, (stdout, stderr)
        retained = json.loads(stdout)
        assert retained["job"]["cancel_requested"] and retained["job"]["cancel_observed"] is False
        assert retained["job"]["status"] == "RECOVERY_REQUIRED" and retained["job"]["outcome"] == "UNKNOWN"
        assert not retained["has_handles"] and retained["shutdown"]["joined"]
        assert retained["execution"]["idle_confirmed"] is False
        if partial.exists():
            assert partial.read_text() == "TEST_ONLY"


def test_job_capacity_refuses_new_worker_and_retains_all_completed_ids(tmp_path, monkeypatch):
    from apps.lab import job_journal as module
    monkeypatch.setattr(module, "MAX_JOBS", 2)  # TEST_ONLY small capacity.
    lab = service(tmp_path)
    retained = []
    for name in ("first", "second"):
        job = lab.submit("study_create", {"name": name})
        retained.append(finish(lab, job["id"]))
    frozen = {p: p.read_bytes() for p in (lab._http_journal.root / "jobs").rglob("*.json")}
    monkeypatch.setattr(threading.Thread, "start", lambda self: pytest.fail("Capacity refusal started a worker"))
    with pytest.raises(ServiceError) as failure:
        lab.submit("study_create", {"name": "forbidden third"})
    assert failure.value.status == 503
    assert lab._selected().lab.calls == ["first", "second"]
    assert len(list((lab._http_journal.root / "jobs").iterdir())) == 2
    assert not (lab._http_journal.root / "claim.json").exists()
    assert "capacity" in lab._recovery_reasons[-1]
    for _ in range(2):
        restarted = service(tmp_path)
        assert [restarted.job(job["id"]) for job in retained] == retained
        assert restarted.execution_status()["accepting_jobs"] is False
        assert all(p.read_bytes() == raw for p, raw in frozen.items())


def test_prior_over_limit_job_history_remains_readable_with_admission_blocked(tmp_path, monkeypatch):
    from apps.lab import job_journal as module
    monkeypatch.setattr(module, "MAX_JOBS", 3)
    lab = service(tmp_path)
    retained = []
    for index in range(3):
        job = lab.submit("study_create", {"name": f"TEST_ONLY historical {index}"})
        retained.append(finish(lab, job["id"]))
    monkeypatch.setattr(module, "MAX_JOBS", 2)  # Models the previous producer's overflow.
    restarted = service(tmp_path)
    assert [restarted.job(job["id"]) for job in retained] == retained
    assert any("capacity exceeded" in reason for reason in restarted._recovery_reasons)
    with pytest.raises(ServiceError):
        restarted.submit("study_create", {"name": "no replay"})
    assert restarted._selected().lab.calls == [] and not restarted._job_threads


@pytest.mark.parametrize("operation, capacity", [("study_create", 3), ("research_run", 4)])
def test_insufficient_event_capacity_refuses_admission_before_claim(tmp_path, monkeypatch, operation, capacity):
    from apps.lab import job_journal as module
    monkeypatch.setattr(module, "MAX_EVENTS", capacity)
    journal = HTTPJobJournal(tmp_path)
    pending = intent()
    pending["operation"] = operation
    with pytest.raises(JournalError, match="capacity.*start/terminal/release"):
        journal.reserve(pending, {"test_only": True})
    assert not (journal.root / "claim.json").exists()
    assert not list((journal.root / "jobs").iterdir())
    if operation == "study_create":
        lab = service(tmp_path)
        monkeypatch.setattr(threading.Thread, "start", lambda self: pytest.fail("Insufficient capacity started a worker"))
        with pytest.raises(ServiceError) as failure:
            lab.submit("study_create", {"name": "forbidden"})
        assert failure.value.status == 503 and lab._selected().lab.calls == []
        assert not lab._job_threads and not lab._job_tokens


def test_nonterminal_events_leave_exact_terminal_and_release_space(tmp_path, monkeypatch):
    from apps.lab import job_journal as module
    monkeypatch.setattr(module, "MAX_EVENTS", 5)
    journal, job = reserve(tmp_path)
    journal.append(job["id"], "WORKER_STARTED", job)
    requested = {**job, "status": "CANCEL_REQUESTED", "cancel_requested": True}
    journal.append(job["id"], "CANCEL_REQUESTED", requested)
    folder = journal.root / "jobs" / job["id"]
    frozen = {p: p.read_bytes() for p in folder.iterdir()}
    with pytest.raises(JournalError, match="terminal/release space is reserved.*UNKNOWN"):
        journal.append(job["id"], "CANCEL_REQUESTED", requested)
    assert all(p.read_bytes() == raw for p, raw in frozen.items()) and len(list(folder.iterdir())) == 3
    terminal = {**requested, "status": "COMPLETED", "result": {"test_only": True}}
    journal.append(job["id"], "TERMINAL", terminal)
    assert len(list(folder.iterdir())) == 5 and not (journal.root / "claim.json").exists()
    restarted = service(tmp_path)
    assert restarted.job(job["id"]) == terminal and restarted.execution_status()["idle_confirmed"]


def test_terminal_before_release_at_both_capacity_limits_preserves_original_result(tmp_path, monkeypatch):
    from apps.lab import job_journal as module
    monkeypatch.setattr(module, "MAX_JOBS", 1)
    monkeypatch.setattr(module, "MAX_EVENTS", 4)
    journal, job = reserve(tmp_path)
    journal.append(job["id"], "WORKER_STARTED", job)
    terminal = {**job, "status": "COMPLETED", "result": {"test_only": True, "original": [32, 38]}}
    with journal._locked():
        journal._append(job["id"], "TERMINAL", terminal)
    folder = journal.root / "jobs" / job["id"]
    frozen = {p: p.read_bytes() for p in folder.iterdir()}
    restarted = service(tmp_path)
    assert restarted.job(job["id"]) == terminal
    assert len(list(folder.iterdir())) == 4 and not (journal.root / "claim.json").exists()
    assert all(p.read_bytes() == raw for p, raw in frozen.items())
    assert not restarted._job_threads and not restarted._job_tokens
    with pytest.raises(ServiceError):
        restarted.submit("study_create", {"name": "full retained history"})
    assert restarted._selected().lab.calls == []
    assert service(tmp_path).job(job["id"]) == terminal


def test_live_event_capacity_failure_keeps_returned_result_unknown(tmp_path, monkeypatch):
    from apps.lab import job_journal as module
    monkeypatch.setattr(module, "MAX_EVENTS", 4)
    lab = service(tmp_path)
    entered, release = threading.Event(), threading.Event()

    def controlled(name):
        entered.set()
        assert release.wait(5)
        return {"test_only": True, "name": name}

    monkeypatch.setattr(lab._selected().lab, "create_study", controlled)
    started = lab.submit("study_create", {"name": "retain returned value"})
    try:
        assert entered.wait(5)
        requested = lab.cancel(started["id"])
        assert requested["status"] == "RECOVERY_REQUIRED"
        assert "capacity" in requested["persistence_error"] and requested["cancel_observed"] is False
    finally:
        release.set()
    unknown = finish(lab, started["id"])
    assert unknown["status"] == "RECOVERY_REQUIRED" and unknown["outcome"] == "UNKNOWN"
    assert unknown["result"] == {"test_only": True, "name": "retain returned value"}
    folder = lab._http_journal.root / "jobs" / started["id"]
    assert len(list(folder.iterdir())) == 2 and (lab._http_journal.root / "claim.json").exists()
    restarted = service(tmp_path)
    assert restarted.job(started["id"])["status"] == "RECOVERY_REQUIRED"
    assert not restarted.execution_status()["accepting_jobs"]


def test_preexisting_event_overflow_retains_bounded_snapshot_and_refuses_replay(tmp_path, monkeypatch):
    from apps.lab import job_journal as module
    monkeypatch.setattr(module, "MAX_EVENTS", 6)
    journal, job = reserve(tmp_path)
    journal.append(job["id"], "WORKER_STARTED", job)
    requested = {**job, "status": "CANCEL_REQUESTED", "cancel_requested": True}
    journal.append(job["id"], "CANCEL_REQUESTED", requested)
    journal.append(job["id"], "CANCEL_REQUESTED", requested)
    journal.append(job["id"], "TERMINAL", {**requested, "status": "COMPLETED", "result": {"test_only": True}})
    folder = journal.root / "jobs" / job["id"]
    frozen = {p: p.read_bytes() for p in folder.iterdir()}
    monkeypatch.setattr(module, "MAX_EVENTS", 4)
    restarted = service(tmp_path)
    retained = restarted.job(job["id"])
    assert retained["status"] == "RECOVERY_REQUIRED" and retained["retained_status"] == "CANCEL_REQUESTED"
    assert "capacity exceeded" in retained["recovery_reason"]
    with pytest.raises(ServiceError):
        restarted.submit("study_create", {"name": "no overflow replay"})
    assert restarted._selected().lab.calls == [] and not restarted._job_threads
    assert all(p.read_bytes() == raw for p, raw in frozen.items())


def test_recovered_cancel_intent_survives_observation_capacity_without_new_records(tmp_path, monkeypatch):
    from apps.lab import job_journal as module
    monkeypatch.setattr(module, "MAX_EVENTS", 4)
    journal, job = reserve(tmp_path)
    recovered = service(tmp_path)
    recovered.cancel(job["id"])
    for _ in range(2):
        recovered = service(tmp_path)
        assert recovered.job(job["id"])["cancel_requested"]
        assert recovered.job(job["id"])["cancel_observed"] is False
    folder = journal.root / "observations"
    frozen = {p: p.read_bytes() for p in folder.iterdir()}
    assert len(frozen) == 4
    with pytest.raises(JournalError, match="observation capacity exhausted.*UNKNOWN"):
        recovered._http_journal.cancellation_intent(job["id"])
    restarted = service(tmp_path)
    assert len(list(folder.iterdir())) == 4 and all(p.read_bytes() == raw for p, raw in frozen.items())
    assert restarted.job(job["id"])["cancel_requested"]
    assert restarted.job(job["id"])["status"] == "RECOVERY_REQUIRED"
    assert any("observation capacity exhausted" in reason for reason in restarted._recovery_reasons)


@pytest.mark.parametrize("legacy_intent", [False, True])
def test_recovered_cancel_records_cannot_assert_observed_stop(tmp_path, legacy_intent):
    journal, job = reserve(tmp_path)
    recovered = service(tmp_path)
    recovered.cancel(job["id"])
    path = next(p for p in (journal.root / "observations").iterdir()
                if json.loads(p.read_bytes())["kind"] == "HTTP_RECOVERED_CANCEL_REQUEST")
    record = json.loads(path.read_bytes())
    if legacy_intent:
        record.pop("cancel_requested")  # Previous R1 producer: kind alone retained intent.
        path.write_bytes(journal._bytes(record))
        restarted = service(tmp_path)
        assert restarted.job(job["id"])["cancel_requested"]
        assert restarted.job(job["id"])["cancel_observed"] is False
    else:
        record["cancel_observed"] = True  # A recovered observation cannot confer authority.
        path.write_bytes(journal._bytes(record))
        restarted = service(tmp_path)
        assert restarted.job(job["id"])["cancel_observed"] is False
        assert any("cannot confirm observation" in reason for reason in restarted._recovery_reasons)
    assert restarted.job(job["id"])["outcome"] == "UNKNOWN"
    assert not restarted._job_tokens and not restarted.execution_status()["accepting_jobs"]


def test_completed_history_accepts_new_source_but_unresolved_claim_does_not(tmp_path):
    first = service(tmp_path)
    job = first.submit("study_create", {"name": "historical exact result"})
    terminal = finish(first, job["id"])
    folder = tmp_path / "_http_job_control/jobs" / job["id"]
    raw = {p: p.read_bytes() for p in folder.iterdir()}
    # TEST_ONLY trusted fingerprint change models a source upgrade; actual tests
    # continue importing the real candidate and its dependencies from this repo.
    new_source = {**first._http_journal.source, "http_source_sha256": "f" * 64}
    updated = LabService(tmp_path, lab_factory=MetadataLab,
                         http_journal=HTTPJobJournal(tmp_path, source=new_source))
    assert updated.job(job["id"]) == terminal and updated.execution_status()["idle_confirmed"]
    next_job = updated.submit("study_create", {"name": "new source separately bound"})
    assert finish(updated, next_job["id"])["status"] == "COMPLETED"
    admission = json.loads((tmp_path / "_http_job_control/jobs" / next_job["id"] / "000000.json").read_bytes())
    assert admission["source"] == new_source and all(p.read_bytes() == value for p, value in raw.items())
    pending = intent()
    updated._http_journal.reserve(pending, {"name": "unresolved updated source"})
    old_observer = service(tmp_path)
    assert old_observer.job(pending["id"])["status"] == "RECOVERY_REQUIRED"
    assert old_observer.job(job["id"])["result"] == terminal["result"]
    assert not old_observer.execution_status()["idle_confirmed"]


def test_fsynced_journal_and_short_lock_on_actual_mounted_c_store():
    repo = Path(__file__).resolve().parents[1]
    if not repo.as_posix().startswith("/mnt/c/"):
        pytest.skip("Local WSL C: mount control; portable journal checks run separately")
    with tempfile.TemporaryDirectory(prefix="s3-r1-test-only-", dir=repo / "artifacts") as directory:
        path = Path(directory)
        print("TEST_ONLY actual mounted C: store:", path)
        first = service(path)
        job = first.submit("study_create", {"name": "mounted C: durability"})
        terminal = finish(first, job["id"])
        assert service(path).job(job["id"]) == terminal
        journal, pending = reserve(path)
        recovered = service(path)
        assert recovered.job(pending["id"])["status"] == "RECOVERY_REQUIRED"
        assert recovered.execution_status()["idle_confirmed"] is False


@pytest.mark.parametrize("stage", ["claim", "admission", "worker"])
def test_preexecution_storage_failure_never_invokes_operation(tmp_path, monkeypatch, stage):
    lab = service(tmp_path)
    original = lab._http_journal._write_new

    def fail(path, value):
        selected = (stage == "claim" and value.get("kind") == "HTTP_JOB_CLAIM"
                    or stage == "admission" and value.get("event") == "ADMITTED"
                    or stage == "worker" and value.get("event") == "WORKER_STARTED")
        if selected:
            raise OSError("TEST_ONLY preexecution persistence failure")
        return original(path, value)

    monkeypatch.setattr(lab._http_journal, "_write_new", fail)
    if stage == "worker":
        job = lab.submit("study_create", {"name": "forbidden"})
        assert finish(lab, job["id"])["status"] == "RECOVERY_REQUIRED"
    else:
        with pytest.raises(ServiceError):
            lab.submit("study_create", {"name": "forbidden"})
    assert lab._selected().lab.calls == []
    assert lab.execution_status()["idle_confirmed"] is False


@pytest.mark.parametrize("stage", ["TERMINAL", "RELEASED"])
@pytest.mark.parametrize("source_updated", [False, True])
def test_terminal_before_claim_removal_is_reconciled_without_replay(tmp_path, stage, source_updated):
    journal, job = reserve(tmp_path)
    original = deepcopy(job)
    original.update(status="COMPLETED", result={"test_only": True, "exact": [2, 3]}, completed_utc="TEST_ONLY")
    # Simulate the two publication crash windows, retaining actual serialized events.
    with journal._locked():
        journal._append(job["id"], "TERMINAL", original)
        if stage == "RELEASED":
            journal._append(job["id"], "RELEASED", original)
    updated = {**journal.source, "http_source_sha256": "f" * 64} if source_updated else journal.source
    restored = LabService(tmp_path, lab_factory=MetadataLab,
                          http_journal=HTTPJobJournal(tmp_path, source=updated))
    assert restored.job(job["id"]) == original
    assert restored._selected().lab.calls == []
    assert restored.execution_status()["idle_confirmed"]
    assert not (tmp_path / "_http_job_control/claim.json").exists()
    if source_updated:
        next_job = restored.submit("study_create", {"name": "new source after metadata release"})
        assert finish(restored, next_job["id"])["status"] == "COMPLETED"


def test_first_directory_publication_syncs_each_parent(tmp_path, monkeypatch):
    calls = []
    real = HTTPJobJournal._sync_directory

    def sync(path):
        calls.append(path)
        real(path)

    monkeypatch.setattr(HTTPJobJournal, "_sync_directory", staticmethod(sync))
    store = tmp_path / "new-parent" / "new-store"
    journal = HTTPJobJournal(store)
    assert not journal.blocked
    assert tmp_path in calls and store.parent in calls and store in calls
    assert journal.root in calls


@pytest.mark.parametrize("damage", ["torn", "schema", "store", "source", "controller", "argument",
                                    "sequence", "previous", "event", "foreign_file", "claim", "claim_missing",
                                    "duplicate_key", "nonfinite", "oversize", "observation"])
def test_corrupt_or_foreign_evidence_blocks_execution_and_preserves_bytes(tmp_path, damage):
    journal, job = reserve(tmp_path)
    journal.append(job["id"], "WORKER_STARTED", job)
    root = journal.root
    event = root / "jobs" / job["id"] / "000001.json"
    if damage == "claim_missing":
        (root / "claim.json").unlink()
    elif damage == "foreign_file":
        (root / "jobs" / job["id"] / "foreign.json").write_text("{}")
    elif damage == "claim":
        (root / "claim.json").write_text('{"kind":"FOREIGN"}')
    elif damage == "torn":
        event.write_text('{"schema_version":')
    elif damage == "duplicate_key":
        event.write_text('{"schema_version":1,"schema_version":1}')
    elif damage == "nonfinite":
        event.write_text('{"schema_version":1,"number":1e999}')
    elif damage == "oversize":
        with event.open("wb") as stream:
            stream.truncate(8 * 1024 * 1024 + 1)
    elif damage == "observation":
        (root / "observations" / ("1" * 32 + ".json")).write_text("{torn")
    else:
        value = json.loads(event.read_bytes())
        key, replacement = {"schema": ("schema_version", 99), "store": ("store_root", "/foreign"),
                            "source": ("source", {"foreign": True}), "controller": ("controller_id", "f" * 32),
                            "argument": ("argument_sha256", "f" * 64), "sequence": ("sequence", 6),
                            "previous": ("previous_sha256", "f" * 64), "event": ("event", "IDLE")} [damage]
        value[key] = replacement
        event.write_text(json.dumps(value))
    frozen = {p: p.read_bytes() for p in root.rglob("*") if p.is_file() and p.name != "journal.lock"}
    restored = service(tmp_path)
    state = restored.overview()["execution"]
    assert state["state"] == "RECOVERY_REQUIRED" and state["outcome"] == "UNKNOWN"
    assert not state["idle_confirmed"] and not state["accepting_jobs"]
    with pytest.raises(ServiceError):
        restored.submit("study_create", {"name": "forbidden"})
    assert restored._selected().lab.calls == []
    assert all(p.read_bytes() == raw for p, raw in frozen.items())


def test_store_path_escape_is_blocked_without_writing_foreign_directory(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    store = tmp_path / "local"
    store.mkdir()
    (store / "_http_job_control").symlink_to(outside, target_is_directory=True)
    restored = service(store)
    assert restored.execution_status()["state"] == "RECOVERY_REQUIRED"
    assert list(outside.iterdir()) == []


def test_result_then_persistence_failure_keeps_result_and_claim_unknown(tmp_path, monkeypatch):
    lab = service(tmp_path)
    original = lab._http_journal._write_new

    def fail_terminal(path, value):
        if value.get("event") == "TERMINAL":
            raise OSError("TEST_ONLY terminal storage failure")
        return original(path, value)

    monkeypatch.setattr(lab._http_journal, "_write_new", fail_terminal)
    job = lab.submit("study_create", {"name": "retain returned result"})
    failed = finish(lab, job["id"])
    assert failed["status"] == "RECOVERY_REQUIRED" and failed["retained_status"] == "COMPLETED"
    assert failed["result"]["name"] == "retain returned result"
    assert "storage failure" in failed["persistence_error"]
    assert lab.execution_status()["idle_confirmed"] is False
    assert service(tmp_path).job(job["id"])["status"] == "RECOVERY_REQUIRED"
    assert (tmp_path / "_http_job_control/claim.json").exists()


def test_default_mcp_service_never_acquires_http_journal(tmp_path, monkeypatch):
    import openscience.jobs as jobs
    monkeypatch.setenv("CAELAB_STORE", str(tmp_path))
    monkeypatch.setattr(jobs, "_resident", None)
    monkeypatch.setattr(jobs, "_bound_store", None)
    monkeypatch.setattr(jobs, "_bound_setting", None)
    with jobs._lock:
        resident = jobs._service()
    assert resident._http_journal is None
    assert not (tmp_path / "_http_job_control").exists()
    # An HTTP claim does not block this independent default resident observation.
    reserve(tmp_path)
    assert jobs.execution_status()["state"] == "IDLE"


def test_two_actual_http_controllers_have_one_overlapping_execution(tmp_path):
    code = '''
import sys, time
from pathlib import Path
from apps.lab.job_journal import HTTPJobJournal
from apps.lab.service import LabService, ServiceError
store, tag = Path(sys.argv[1]), sys.argv[2]
class Metadata:
    pde_adapters = {}
    def __init__(self, path): self.store = Path(path)
    def create_study(self, name):
        (store / (tag + ".entered")).write_text("TEST_ONLY")
        deadline = time.monotonic() + 12
        while not (store / "release").exists():
            if time.monotonic() > deadline: raise RuntimeError("TEST_ONLY latch expired")
            time.sleep(.01)
        return {"test_only": True}
lab = LabService(store, lab_factory=Metadata, http_journal=HTTPJobJournal(store))
(store / (tag + ".ready")).write_text("TEST_ONLY")
deadline = time.monotonic() + 12
while not (store / "start").exists():
    if time.monotonic() > deadline: raise RuntimeError("TEST_ONLY start expired")
    time.sleep(.01)
try:
    job = lab.submit("study_create", {"name": "TEST_ONLY"})
except ServiceError:
    (store / (tag + ".refused")).write_text("TEST_ONLY")
else:
    lab._job_threads[job["id"]].join(12)
'''
    children = [subprocess.Popen([sys.executable, "-c", code, str(tmp_path), tag],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE) for tag in ("a", "b")]
    deadline = time.monotonic() + 12
    try:
        while len(list(tmp_path.glob("*.ready"))) < 2:
            assert time.monotonic() < deadline
            time.sleep(.01)
        (tmp_path / "start").write_text("TEST_ONLY")
        while not list(tmp_path.glob("*.refused")) or not list(tmp_path.glob("*.entered")):
            assert time.monotonic() < deadline
            time.sleep(.01)
        assert len(list(tmp_path.glob("*.entered"))) == 1
        assert len(list(tmp_path.glob("*.refused"))) == 1
    finally:
        (tmp_path / "release").write_text("TEST_ONLY")
        for child in children:
            stdout, stderr = child.communicate(timeout=15)
            assert child.returncode == 0, (stdout, stderr)
    restored = service(tmp_path)
    assert restored.execution_status()["idle_confirmed"]
    assert len(restored.overview()["jobs"]) == 1
