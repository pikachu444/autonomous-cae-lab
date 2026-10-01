"""Filesystem/Core fault tests with explicit stand-in bytes, not native CAD proof."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from caelab import Lab
from caelab.contracts import Candidate, FileRevision
from caelab import registration_transaction as transaction


class PreparedAdapter:
    backend = "test.prepared"
    def __init__(self, store):
        self.source = store / "models" / "source.bin"
        self.source.parent.mkdir()
        self.source.write_bytes(b"SIMULATED BEFORE REVISION")
        self.prepare_failure = False
    def document_id(self, model):
        return model
    def discover(self, model):
        return [Candidate({"backend": self.backend, "document": model, "object": "test", "path": "dimension"},
                          "Test dimension", "mm", 10, None, None, transaction.file_hash(self.source))]
    def probe_effect(self, *args):
        return {"status": "PASS", "method": "explicit test stand-in, no CAD"}
    def prepare_bind(self, model, candidate, parameter_id, display_name, lower, upper, output):
        output.mkdir(parents=True)
        prepared = output / "source.bin"
        prepared.write_bytes(b"SIMULATED AFTER REVISION")
        if self.prepare_failure:
            raise OSError("INJECTED_PRIVATE_PREPARATION_FAILURE")
        return FileRevision(self.source, prepared, candidate.source_sha256, transaction.file_hash(prepared))
    def regenerate(self, *args):
        pytest.fail("Pending transaction reached downstream regeneration")


@pytest.fixture
def lab(tmp_path):
    adapter = PreparedAdapter(tmp_path)
    lab = Lab(tmp_path, adapters={adapter.backend: adapter})
    lab.create_study("S-recovery", "Recovery", "Question", "Hypothesis", "Objective")
    return lab


def register(lab):
    return lab.register_parameter("S-recovery", "test.prepared", "model", "dimension",
                                  "dimension", "Dimension", 2, 20)


def public_before(lab):
    return {path: path.read_bytes() for path in [
        lab.adapters["test.prepared"].source,
        lab.store / "studies/S-recovery/parameters.json",
        lab.store / "studies/S-recovery/registry_history/0000.json"]}


def assert_restored(lab, before):
    for path, data in before.items():
        assert path.read_bytes() == data
    assert not (lab.store / "studies/S-recovery/registry_history/0001.json").exists()
    assert lab.registry("S-recovery") == {"revision": 0, "entries": []}
    assert lab.recover_registration("S-recovery")["status"] == "NO_PENDING_TRANSACTION"


def test_success_freezes_matching_native_registry_and_history(lab):
    entry = register(lab)
    registry = lab.registry("S-recovery")
    assert registry["revision"] == 1 and registry["entries"] == [entry]
    assert entry["source_sha256"] == transaction.file_hash(lab.adapters["test.prepared"].source)
    history = json.loads((lab.store / "studies/S-recovery/registry_history/0001.json").read_text())
    assert history == registry
    _, journal = next(transaction.journals(lab.store))
    assert journal["state"] == "COMMITTED"
    assert lab.recover_registration("S-recovery")["status"] == "NO_PENDING_TRANSACTION"


@pytest.mark.parametrize("point", ["native", "history", "registry", "commit-marker", "marker-after-write"])
def test_write_failure_blocks_reads_and_execution_until_exact_recovery(lab, monkeypatch, point):
    before = public_before(lab)
    original = transaction._atomic_bytes
    def failing(path, data):
        hit = ((point == "native" and path == lab.adapters["test.prepared"].source) or
               (point == "history" and path == lab.store / "studies/S-recovery/registry_history/0001.json") or
               (point == "registry" and path == lab.store / "studies/S-recovery/parameters.json") or
               (point in {"commit-marker", "marker-after-write"} and path.name == "journal.json" and
                json.loads(data)["state"] == "COMMITTED"))
        if hit:
            if point == "marker-after-write":
                original(path, data)
            raise OSError("INJECTED_PUBLICATION_FAILURE")
        original(path, data)
    monkeypatch.setattr(transaction, "_atomic_bytes", failing)
    with pytest.raises(OSError, match="INJECTED_PUBLICATION_FAILURE"):
        register(lab)
    monkeypatch.setattr(transaction, "_atomic_bytes", original)
    fresh = Lab(lab.store, adapters=lab.adapters)
    for call in [lambda: fresh.registry("S-recovery"),
                 lambda: fresh.discover_parameters("test.prepared", "model"),
                 lambda: register(fresh),
                 lambda: fresh.run_experiment(study_id="S-recovery", experiment_id="E-blocked",
                                              backend="test.prepared", model="model", values={"dimension": 12})]:
        with pytest.raises(ValueError, match="REGISTRATION_RECOVERY_REQUIRED"):
            call()
    assert not (lab.store / "experiments/E-blocked").exists()
    assert fresh.recover_registration("S-recovery")["transactions"][0]["status"] == "ROLLED_BACK"
    assert_restored(fresh, before)
    # Retrying appends exactly one native/Core binding and one history revision.
    entry = register(fresh)
    assert fresh.registry("S-recovery")["entries"] == [entry]
    assert len(list((lab.store / "studies/S-recovery/registry_history").glob("*.json"))) == 2


def test_private_preparation_failure_never_changes_public_files(lab):
    before = public_before(lab)
    lab.adapters["test.prepared"].prepare_failure = True
    with pytest.raises(OSError, match="PRIVATE_PREPARATION"):
        register(lab)
    assert_restored(lab, before)
    folder, journal = next(transaction.journals(lab.store))
    assert journal["state"] == "ABORTED" and (folder / "work/native/source.bin").is_file()


@pytest.mark.parametrize("conflict", ["foreign-native", "foreign-registry", "corrupt-before", "existing-history"])
def test_recovery_preserves_conflicting_or_corrupt_bytes(lab, monkeypatch, conflict):
    original = transaction._atomic_bytes
    registry = lab.store / "studies/S-recovery/parameters.json"
    def fail(path, data):
        if path == registry:
            raise OSError("INJECTED")
        original(path, data)
    monkeypatch.setattr(transaction, "_atomic_bytes", fail)
    with pytest.raises(OSError):
        register(lab)
    monkeypatch.setattr(transaction, "_atomic_bytes", original)
    folder, _ = next(transaction.journals(lab.store))
    target = {"foreign-native": lab.adapters["test.prepared"].source,
              "foreign-registry": registry,
              "corrupt-before": folder / "before/0000.bin",
              "existing-history": lab.store / "studies/S-recovery/registry_history/0001.json"}[conflict]
    target.write_bytes(b"FOREIGN BYTES MUST BE PRESERVED")
    public = {p: p.read_bytes() for p in public_before(lab)}
    with pytest.raises(ValueError, match="REGISTRATION_(RECOVERY_CONFLICT|IMAGE_INVALID)"):
        lab.recover_registration("S-recovery")
    assert target.read_bytes() == b"FOREIGN BYTES MUST BE PRESERVED"
    assert all(path.read_bytes() == value for path, value in public.items())
    with pytest.raises(ValueError, match="REGISTRATION_RECOVERY_REQUIRED"):
        lab.registry("S-recovery")


@pytest.mark.parametrize("published_files", [1, 2])
def test_hard_process_exit_after_publication_is_recoverable_from_fresh_lab(lab, published_files):
    before = public_before(lab)
    prepared = transaction.RegistrationTransaction(lab.store, "S-recovery")
    target = lab.adapters["test.prepared"].source
    after = prepared.work / "source.bin"
    after.write_bytes(b"SIMULATED AFTER CRASH")
    prepared.add(target, after, transaction.file_hash(target), transaction.file_hash(after))
    registry = lab.store / "studies/S-recovery/parameters.json"
    new_json = prepared.work / "parameters.json"
    new_json.write_bytes(transaction.json_bytes({"revision": 1, "entries": []}))
    history = registry.parent / "registry_history/0001.json"
    prepared.add(history, new_json, None, transaction.file_hash(new_json))
    prepared.add(registry, new_json, transaction.file_hash(registry), transaction.file_hash(new_json))
    prepared.prepare()
    child = """
import os, sys
from pathlib import Path
from caelab import registration_transaction as module
store, folder = Path(sys.argv[1]), Path(sys.argv[2])
value = module.load_json(folder / 'journal.json')
transaction = module.RegistrationTransaction.open(store, folder, value)
actual = module._atomic_bytes
targets = {store / row['target'] for row in value['files']}
count = 0
def write_then_exit(path, data):
    global count
    actual(path, data)
    if path in targets:
        count += 1
        if count == int(sys.argv[3]):
            os._exit(91)
module._atomic_bytes = write_then_exit
transaction.commit()
raise AssertionError('Expected a real process exit')
"""
    run = subprocess.run([sys.executable, "-c", child, str(lab.store), str(prepared.folder), str(published_files)],
                         cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=30)
    assert run.returncode == 91, run.stderr
    fresh = Lab(lab.store, adapters=lab.adapters)
    with pytest.raises(ValueError, match="REGISTRATION_RECOVERY_REQUIRED"):
        fresh.registry("S-recovery")
    assert fresh.recover_registration("S-recovery")["status"] == "RECOVERED"
    assert_restored(fresh, before)


def test_interrupted_rollback_can_be_retried_without_losing_originals(lab, monkeypatch):
    before = public_before(lab)
    actual = transaction._atomic_bytes
    registry = lab.store / "studies/S-recovery/parameters.json"
    def fail_registry(path, data):
        if path == registry:
            raise OSError("INJECTED")
        actual(path, data)
    monkeypatch.setattr(transaction, "_atomic_bytes", fail_registry)
    with pytest.raises(OSError):
        register(lab)
    source = lab.adapters["test.prepared"].source
    def fail_restore(path, data):
        if path == source and data == before[source]:
            raise OSError("INJECTED_ROLLBACK")
        actual(path, data)
    monkeypatch.setattr(transaction, "_atomic_bytes", fail_restore)
    with pytest.raises(OSError, match="INJECTED_ROLLBACK"):
        lab.recover_registration("S-recovery")
    with pytest.raises(ValueError, match="REGISTRATION_RECOVERY_REQUIRED"):
        lab.registry("S-recovery")
    monkeypatch.setattr(transaction, "_atomic_bytes", actual)
    assert lab.recover_registration("S-recovery")["status"] == "RECOVERED"
    assert_restored(lab, before)


def test_existing_history_is_never_overwritten_and_failed_stage_is_retained(lab):
    source = lab.adapters["test.prepared"].source
    before = source.read_bytes()
    history = lab.store / "studies/S-recovery/registry_history/0001.json"
    history.write_bytes(b"PREEXISTING HISTORY")
    with pytest.raises(ValueError, match="REGISTRATION_SOURCE_CHANGED"):
        register(lab)
    assert history.read_bytes() == b"PREEXISTING HISTORY" and source.read_bytes() == before
    assert lab.registry("S-recovery")["revision"] == 0
    folder, journal = next(transaction.journals(lab.store))
    assert journal["state"] == "ABORTED" and (folder / "after/0000.bin").read_bytes() == b"SIMULATED AFTER REVISION"


@pytest.mark.parametrize("path", ["experiments/E-old/result.json", "registration_transactions/control.bin",
                                 "registration_preparations/control.bin", ".registration.lock"])
def test_replacement_cannot_target_immutable_results_or_transaction_controls(lab, path):
    prepared = transaction.RegistrationTransaction(lab.store, "S-recovery")
    data = prepared.work / "data.bin"
    data.write_bytes(b"TEST DATA")
    with pytest.raises(ValueError, match="REGISTRATION_PATH_INVALID"):
        prepared.add(lab.store / path, data, None, transaction.file_hash(data))
    prepared.abort_preparation("EXPECTED_REFUSAL")


def test_acknowledgement_sync_and_marker_recreation_failure_cannot_remove_gate(lab, monkeypatch):
    before = public_before(lab)
    actual_ack, actual_sync, actual_write = (transaction.RegistrationTransaction._acknowledge,
                                           transaction._sync_directory, transaction._atomic_bytes)
    in_ack, recreation_attempts = False, []
    def acknowledge(instance):
        nonlocal in_ack
        in_ack = True
        try:
            actual_ack(instance)
        finally:
            in_ack = False
    def fail_sync(path):
        if in_ack:
            raise OSError("INJECTED_ACK_DIRECTORY_SYNC")
        actual_sync(path)
    def fail_recreation(path, data):
        if in_ack and path.name == "pending":
            recreation_attempts.append(path)
            raise OSError("INJECTED_PENDING_RECREATION")
        actual_write(path, data)
    monkeypatch.setattr(transaction.RegistrationTransaction, "_acknowledge", acknowledge)
    monkeypatch.setattr(transaction, "_sync_directory", fail_sync)
    monkeypatch.setattr(transaction, "_atomic_bytes", fail_recreation)
    with pytest.raises(OSError, match="INJECTED_ACK_DIRECTORY_SYNC"):
        register(lab)
    folder, value = next(transaction.journals(lab.store))
    assert value["state"] == "COMMITTED" and (folder / "pending").is_file()
    assert recreation_attempts == []
    with pytest.raises(ValueError, match="REGISTRATION_RECOVERY_REQUIRED"):
        lab.registry("S-recovery")
    monkeypatch.setattr(transaction.RegistrationTransaction, "_acknowledge", actual_ack)
    monkeypatch.setattr(transaction, "_sync_directory", actual_sync)
    monkeypatch.setattr(transaction, "_atomic_bytes", actual_write)
    fresh = Lab(lab.store, adapters=lab.adapters)
    assert fresh.recover_registration("S-recovery")["status"] == "RECOVERED"
    assert_restored(fresh, before)


def test_acknowledgement_unlink_failure_keeps_consumer_and_recovery_gate(lab, monkeypatch):
    before = public_before(lab)
    actual = Path.unlink
    def fail_pending(path, *args, **kwargs):
        if path.name == "pending":
            raise OSError("INJECTED_ACK_UNLINK")
        return actual(path, *args, **kwargs)
    monkeypatch.setattr(Path, "unlink", fail_pending)
    with pytest.raises(OSError, match="INJECTED_ACK_UNLINK"):
        register(lab)
    with pytest.raises(ValueError, match="REGISTRATION_RECOVERY_REQUIRED"):
        lab.registry("S-recovery")
    monkeypatch.setattr(Path, "unlink", actual)
    assert lab.recover_registration("S-recovery")["status"] == "RECOVERED"
    assert_restored(lab, before)


def test_failed_initial_journal_never_publishes_an_unrecoverable_folder(lab, monkeypatch):
    before = public_before(lab)
    actual = transaction._atomic_bytes
    def fail_initial(path, data):
        if path.name == "journal.json" and path.parent.parent.name == "registration_preparations":
            raise OSError("INJECTED_FIRST_JOURNAL")
        actual(path, data)
    monkeypatch.setattr(transaction, "_atomic_bytes", fail_initial)
    with pytest.raises(OSError, match="INJECTED_FIRST_JOURNAL"):
        register(lab)
    assert list(transaction.journals(lab.store)) == []
    assert list((lab.store / "registration_preparations").iterdir())
    assert_restored(Lab(lab.store, adapters=lab.adapters), before)


def test_hard_exit_during_initial_journal_preserves_originals_without_pending_gate(lab):
    before = public_before(lab)
    child = """
import os, sys
from pathlib import Path
from caelab.registration_transaction import RegistrationTransaction
RegistrationTransaction._write_journal = lambda self: os._exit(92)
RegistrationTransaction(Path(sys.argv[1]), 'S-recovery')
"""
    run = subprocess.run([sys.executable, "-c", child, str(lab.store)],
                         cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=30)
    assert run.returncode == 92, run.stderr
    assert list(transaction.journals(lab.store)) == []
    assert list((lab.store / "registration_preparations").iterdir())
    assert_restored(Lab(lab.store, adapters=lab.adapters), before)
