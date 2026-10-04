"""Bounded resident coordination checks with real Core metadata, no solvers."""

from concurrent.futures import ThreadPoolExecutor
import importlib.util
from pathlib import Path
import threading
import time

import pytest

from apps.lab import service as service_module
from apps.lab.service import LabService, ServiceError
from caelab import Lab
from openscience import jobs


@pytest.fixture
def resident(tmp_path, monkeypatch):
    store = tmp_path / "store"
    monkeypatch.setenv("CAELAB_STORE", str(store))
    monkeypatch.setattr(jobs, "_resident", None)
    monkeypatch.setattr(jobs, "_bound_store", None)
    monkeypatch.setattr(jobs, "_bound_setting", None)
    monkeypatch.setattr(jobs, "_synchronous_depth", 0)
    return store


def study_arguments(identifier="S-job"):
    return {"study_id": identifier, "name": "Resident research",
            "research_question": "Is metadata retained?", "hypothesis": "Yes",
            "objective": "Record execution without numerical approval"}


def test_execution_observer_does_not_initialize_store(resident):
    result = jobs.execution_status()
    assert result["idle_confirmed"] and result["scope"] == "PROCESS_RESIDENT"
    assert result["store_root"] == str(resident.resolve())
    assert jobs._resident is None and not resident.exists()


def test_execution_observer_sees_actual_synchronous_writer_without_waiting(resident):
    entered, release = threading.Event(), threading.Event()
    def hold():
        with jobs.synchronous_writer():
            entered.set()
            release.wait(3)
    thread = threading.Thread(target=hold)
    thread.start()
    try:
        assert entered.wait(2)
        started = time.monotonic()
        result = jobs.execution_status()
        assert result["state"] == "BUSY" and not result["idle_confirmed"]
        assert time.monotonic() - started < .5
    finally:
        release.set()
        thread.join(3)
    assert not thread.is_alive()
    assert jobs.execution_status()["idle_confirmed"]


def test_execution_observer_refuses_changed_store(resident, monkeypatch):
    with jobs.synchronous_writer():
        pass
    monkeypatch.setenv("CAELAB_STORE", str(resident.parent / "different"))
    result = jobs.execution_status()
    assert result["state"] == "UNKNOWN" and not result["idle_confirmed"]


def finish(identifier):
    deadline = time.monotonic() + 5
    while True:
        job = jobs.inspect(identifier)
        if job["status"] not in {"RUNNING", "CANCEL_REQUESTED", "CLEANUP_PENDING"}:
            return job
        assert time.monotonic() < deadline, job
        time.sleep(.01)


def test_import_creates_neither_service_nor_store(resident, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Module import constructed a Lab service")

    monkeypatch.setattr(service_module, "LabService", forbidden)
    spec = importlib.util.spec_from_file_location("job_import_check", jobs.__file__)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module._resident is None
    assert not resident.exists()


def test_lazy_singleton_and_real_core_study_metadata(resident):
    assert not resident.exists()
    assert jobs.list_jobs()["jobs"] == []
    service = jobs._resident
    started = jobs.start("study_create", study_arguments())
    assert started["status"] == "RUNNING"
    completed = finish(started["id"])
    assert jobs._resident is service
    assert completed["status"] == "COMPLETED"
    assert completed["result"] == service.study("S-job")["study"]
    assert completed["result"]["research_question"] == "Is metadata retained?"
    assert completed["job_control"] == {
        "scope": "PROCESS_RESIDENT", "cancel_supported": True,
        "cancel_mode": "COOPERATIVE_CHECKPOINTS", "immediate_stop_guaranteed": False,
        "completion_is_numerical_pass": False}
    listed = jobs.list_jobs()
    assert listed["jobs"] == [service.job(started["id"])]
    assert "token" not in listed
    # Returned job snapshots are detached from the resident service state.
    completed["result"]["name"] = "caller mutation"
    assert jobs.inspect(started["id"])["result"]["name"] == "Resident research"


def test_concurrent_first_calls_create_one_service(resident, monkeypatch):
    calls = []
    rendezvous = threading.Barrier(6)

    def factory(store):
        calls.append(store)
        return LabService(store)

    def first_call():
        rendezvous.wait(timeout=5)
        return jobs.list_jobs()

    monkeypatch.setattr(service_module, "LabService", factory)
    with ThreadPoolExecutor(max_workers=6) as executor:
        results = list(executor.map(lambda _: first_call(), range(6)))
    assert calls == [resident.resolve()]
    assert all(result["jobs"] == [] for result in results)


@pytest.mark.parametrize("operation,arguments", [
    ("shell", {"command": "arbitrary command"}),
    ("study_create", {**study_arguments(), "unexpected": True}),
    ("study_create", study_arguments("../escape")),
    ("model_analysis_run", {"study_id": "S-job", "experiment_id": "E-job",
                            "backend": "../../foreign", "settings": {}}),
])
def test_existing_admission_gates_reject_before_job(resident, operation, arguments):
    with pytest.raises(ServiceError) as failure:
        jobs.start(operation, arguments)
    assert failure.value.status == 400
    assert jobs.list_jobs()["jobs"] == []
    assert not (resident / "studies/S-job").exists()


def test_read_only_service_selection_is_not_bypassed(resident, tmp_path, monkeypatch):
    library = tmp_path / "library"
    Lab(library).create_study(**study_arguments("S-history"))
    history = library / "studies/S-history/study.json"
    original = history.read_bytes()
    service = LabService(resident, libraries={"history": library})
    service.select_store("history")
    monkeypatch.setattr(jobs, "_resident", service)
    monkeypatch.setattr(jobs, "_bound_store", resident.resolve())
    monkeypatch.setattr(jobs, "_bound_setting", str(resident))
    with pytest.raises(ServiceError) as failure:
        jobs.start("study_create", study_arguments("S-forbidden"))
    assert failure.value.status == 403
    assert jobs.list_jobs()["jobs"] == []
    assert history.read_bytes() == original
    assert not (library / "studies/S-forbidden").exists()


def test_running_job_blocks_second_writer_and_sync_context(resident, monkeypatch):
    jobs.list_jobs()
    lab = jobs._resident._selected().lab
    original = lab.create_study
    entered, release = threading.Event(), threading.Event()

    def controlled(**arguments):
        entered.set()
        assert release.wait(5)
        return original(**arguments)

    monkeypatch.setattr(lab, "create_study", controlled)
    started = jobs.start("study_create", study_arguments())
    try:
        assert entered.wait(5)
        assert jobs.inspect(started["id"])["status"] == "RUNNING"
        assert jobs.list_jobs()["jobs"][0]["status"] == "RUNNING"
        with pytest.raises(ServiceError) as failure:
            jobs.start("study_create", study_arguments("S-second"))
        assert failure.value.status == 409
        with pytest.raises(ServiceError) as failure:
            with jobs.synchronous_writer():
                pytest.fail("Synchronous writer overlapped an async job")
        assert failure.value.status == 409
        assert not (resident / "studies/S-second").exists()
    finally:
        release.set()
    assert finish(started["id"])["status"] == "COMPLETED"
    with jobs.synchronous_writer():
        pass


def test_sync_context_blocks_other_thread_start_until_released(resident):
    attempted, returned = threading.Event(), threading.Event()
    results, errors = [], []

    def submit():
        attempted.set()
        try:
            results.append(jobs.start("study_create", study_arguments()))
        except Exception as exc:
            errors.append(exc)
        finally:
            returned.set()

    with jobs.synchronous_writer():
        thread = threading.Thread(target=submit)
        thread.start()
        assert attempted.wait(5)
        assert not returned.wait(.1)
        assert not (resident / "studies/S-job").exists()
    thread.join(timeout=5)
    assert not thread.is_alive() and returned.is_set() and errors == []
    assert finish(results[0]["id"])["status"] == "COMPLETED"


def test_cancel_pending_keeps_writer_blocked_and_late_completion_is_truthful(resident, monkeypatch):
    jobs.list_jobs()
    lab = jobs._resident._selected().lab
    original = lab.create_study
    entered, release = threading.Event(), threading.Event()

    def uninterruptible_metadata(**arguments):
        entered.set()
        assert release.wait(5)
        return original(**arguments)

    monkeypatch.setattr(lab, "create_study", uninterruptible_metadata)
    started = jobs.start("study_create", study_arguments())
    try:
        assert entered.wait(5)
        requested = jobs.cancel(started["id"])
        assert requested["status"] == "CANCEL_REQUESTED"
        assert requested["cancel_requested"] and not requested["cancel_observed"]
        with pytest.raises(ServiceError) as failure:
            with jobs.synchronous_writer():
                pytest.fail("Cancellation request released the running writer")
        assert failure.value.status == 409
        with pytest.raises(ServiceError):
            jobs.start("study_create", study_arguments("S-overlap"))
    finally:
        release.set()
    completed = finish(started["id"])
    assert completed["status"] == "COMPLETED"
    assert completed["cancel_requested"] and not completed["cancel_observed"]
    assert (resident / "studies/S-job/study.json").exists()
    assert jobs.cancel(started["id"]) == completed


def test_shutdown_closes_owned_service_and_preserves_job_history(resident):
    completed = finish(jobs.start("study_create", study_arguments())["id"])
    closing = jobs.shutdown(timeout=0)
    assert not closing["accepting_jobs"] and closing["pending"] == []
    assert jobs.inspect(completed["id"]) == completed
    with pytest.raises(ServiceError) as failure:
        jobs.start("study_create", study_arguments("S-after-shutdown"))
    assert failure.value.status == 503
    with pytest.raises(ServiceError) as failure:
        with jobs.synchronous_writer():
            pytest.fail("A closed resident admitted a synchronous writer")
    assert failure.value.status == 503


def test_reentrant_sync_context_cannot_start_async_and_unlocks_after_error(resident):
    with pytest.raises(RuntimeError, match="controlled synchronous failure"):
        with jobs.synchronous_writer():
            with jobs.synchronous_writer():
                with pytest.raises(ServiceError) as failure:
                    jobs.start("study_create", study_arguments())
                assert failure.value.status == 409
            with pytest.raises(ServiceError) as failure:
                jobs.start("study_create", study_arguments())
            assert failure.value.status == 409
            raise RuntimeError("controlled synchronous failure")
    assert jobs._synchronous_depth == 0 and jobs.list_jobs()["jobs"] == []
    assert finish(jobs.start("study_create", study_arguments())["id"])["status"] == "COMPLETED"


def test_failed_operation_retains_partial_core_files_and_releases_writer(resident, monkeypatch):
    jobs.list_jobs()
    lab = jobs._resident._selected().lab
    original = lab.create_study
    entered, release = threading.Event(), threading.Event()
    partial = resident / "studies/S-job/partial-evidence.txt"

    def fail_after_core_write(**arguments):
        original(**arguments)
        partial.write_bytes(b"Retained bounded partial execution evidence")
        entered.set()
        assert release.wait(5)
        raise RuntimeError("controlled failure after Core metadata write")

    monkeypatch.setattr(lab, "create_study", fail_after_core_write)
    started = jobs.start("study_create", study_arguments())
    try:
        assert entered.wait(5)
        study = (resident / "studies/S-job/study.json").read_bytes()
        evidence = partial.read_bytes()
        assert jobs.inspect(started["id"])["status"] == "RUNNING"
    finally:
        release.set()
    failed = finish(started["id"])
    assert failed["status"] == "FAILED"
    assert failed["error"] == "RuntimeError: controlled failure after Core metadata write"
    assert partial.read_bytes() == evidence
    assert (resident / "studies/S-job/study.json").read_bytes() == study
    monkeypatch.setattr(lab, "create_study", original)
    assert finish(jobs.start("study_create", study_arguments("S-next"))["id"])["status"] == "COMPLETED"
    assert jobs.inspect(started["id"])["status"] == "FAILED"
    assert partial.read_bytes() == evidence


def test_store_change_refused_while_running_and_after_completion(resident, tmp_path, monkeypatch):
    jobs.list_jobs()
    lab = jobs._resident._selected().lab
    original = lab.create_study
    entered, release = threading.Event(), threading.Event()
    foreign = tmp_path / "foreign-uncreated"

    def controlled(**arguments):
        entered.set()
        assert release.wait(5)
        return original(**arguments)

    monkeypatch.setattr(lab, "create_study", controlled)
    started = jobs.start("study_create", study_arguments())

    def refuse_switch():
        monkeypatch.setenv("CAELAB_STORE", str(foreign))
        for call in (lambda: jobs.start("study_create", study_arguments("S-other")),
                     lambda: jobs.inspect(started["id"]), jobs.list_jobs,
                     jobs.synchronous_writer):
            with pytest.raises(ServiceError, match="new resident") as failure:
                if call is jobs.synchronous_writer:
                    with call():
                        pytest.fail("Changed store admitted a synchronous writer")
                else:
                    call()
            assert failure.value.status == 409
        assert not foreign.exists()
        monkeypatch.setenv("CAELAB_STORE", str(resident))

    try:
        assert entered.wait(5)
        refuse_switch()
        assert jobs.inspect(started["id"])["status"] == "RUNNING"
    finally:
        release.set()
    assert finish(started["id"])["status"] == "COMPLETED"
    refuse_switch()
    assert jobs.inspect(started["id"])["result"]["id"] == "S-job"
