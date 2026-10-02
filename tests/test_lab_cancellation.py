"""Cooperative job cancellation with tiny controlled workers, no solver calls."""

from contextlib import contextmanager
from http.client import HTTPConnection
import json
import os
import subprocess
import sys
import threading
import time

import pytest

from apps.lab import server as server_module
from apps.lab.server import LabHTTPServer
from apps.lab.service import LabService, ServiceError
from caelab import execution_control as control
from caelab.execution_control import (ExecutionCancelled, ExecutionCleanupFailed, check_cancelled,
                                      stop_owned_process, wait_for_process)


def arguments(identifier="S-cancel"):
    return {"study_id": identifier, "name": "Cancellation metadata",
            "research_question": "Is an interruption actually observed?",
            "hypothesis": "Only a checkpoint can acknowledge cancellation",
            "objective": "Preserve partial evidence and distinguish late requests"}


@pytest.fixture
def service(tmp_path):
    return LabService(tmp_path / "store")


def finish(service, identifier):
    deadline = time.monotonic() + 5
    while True:
        snapshot = service.job(identifier)
        if snapshot["status"] not in {"RUNNING", "CANCEL_REQUESTED"}:
            return snapshot
        assert time.monotonic() < deadline, snapshot
        time.sleep(.01)


@pytest.mark.parametrize("identifier", [None, True, 4, [], {}, "", "../foreign"])
def test_invalid_job_ids_are_refused(service, identifier):
    for operation in (service.cancel, service.job):
        with pytest.raises(ServiceError) as failure:
            operation(identifier)
        assert failure.value.status == 400


def test_unknown_and_terminal_cancellation_are_truthful(service):
    with pytest.raises(ServiceError) as failure:
        service.cancel("J-unknown")
    assert failure.value.status == 404
    started = service.submit("study_create", arguments())
    completed = finish(service, started["id"])
    assert completed["status"] == "COMPLETED"
    assert not completed["cancel_requested"] and not completed["cancel_observed"]
    assert service.cancel(started["id"]) == completed
    assert service.cancel(started["id"]) == completed
    assert service.shutdown(timeout=1)["joined"]


def test_requested_and_observed_cancel_keep_writer_blocked_until_exit(service, monkeypatch):
    lab = service._selected().lab
    original = lab.create_study
    entered, checkpoint, observed, finish_cleanup = (threading.Event() for _ in range(4))

    def controlled(**values):
        original(**values)
        entered.set()
        assert checkpoint.wait(5)
        try:
            check_cancelled()
        except ExecutionCancelled:
            observed.set()
            assert finish_cleanup.wait(5)
            raise

    monkeypatch.setattr(lab, "create_study", controlled)
    started = service.submit("study_create", arguments())
    try:
        assert entered.wait(5)
        path = lab.store / "studies/S-cancel/study.json"
        old_bytes = path.read_bytes()
        requested = service.cancel(started["id"])
        assert requested["status"] == "CANCEL_REQUESTED"
        assert requested["cancel_requested"] and not requested["cancel_observed"]
        for call in (lambda: service.submit("study_create", arguments("S-other")),
                     lambda: service.select_store("local")):
            with pytest.raises(ServiceError) as failure:
                call()
            assert failure.value.status == 409
        checkpoint.set()
        assert observed.wait(5)
        cleanup_pending = service.cancel(started["id"])
        assert cleanup_pending["status"] == "CANCEL_REQUESTED" and cleanup_pending["cancel_observed"]
        assert service.shutdown(timeout=0)["pending"][0]["status"] == "CANCEL_REQUESTED"
    finally:
        checkpoint.set()
        finish_cleanup.set()
    cancelled = finish(service, started["id"])
    assert cancelled["status"] == "CANCELLED" and cancelled["cancel_observed"]
    assert "ExecutionCancelled" in cancelled["error"]
    assert path.read_bytes() == old_bytes
    assert service.cancel(started["id"]) == cancelled
    assert service.shutdown(timeout=1)["pending"] == []


def test_core_caught_cancellation_result_is_preserved(service, monkeypatch):
    entered, release = threading.Event(), threading.Event()
    core_result = {"status": "FAILED_EXECUTION", "solver_status": "FAILED_EXECUTION",
                   "decision": "NOT_RELEASED", "metrics": {},
                   "validations": [{"status": "UNKNOWN"}], "test_only": True}

    def controlled(**values):
        entered.set()
        assert release.wait(5)
        try:
            check_cancelled()
        except ExecutionCancelled:
            # Simulate the existing Core path which records the backend error.
            return core_result
        pytest.fail("Cancellation was not observed")

    monkeypatch.setattr(service._selected().lab, "run_model_analysis", controlled)
    started = service.submit("model_analysis_run", {"study_id": "S-cancel", "experiment_id": "E-cancel",
                                                    "backend": "test.cooperative", "settings": {}})
    try:
        assert entered.wait(5)
        service.cancel(started["id"])
    finally:
        release.set()
    cancelled = finish(service, started["id"])
    assert cancelled["status"] == "CANCELLED" and cancelled["cancel_observed"]
    assert cancelled["result"] == core_result
    assert service.shutdown(timeout=1)["joined"]


@pytest.mark.parametrize("raise_error", [False, True])
def test_unobserved_late_request_preserves_original_outcome(service, monkeypatch, raise_error):
    lab = service._selected().lab
    original = lab.create_study
    entered, release = threading.Event(), threading.Event()

    def no_later_checkpoint(**values):
        result = original(**values)
        entered.set()
        assert release.wait(5)
        if raise_error:
            raise RuntimeError("ordinary late failure")
        return result

    monkeypatch.setattr(lab, "create_study", no_later_checkpoint)
    started = service.submit("study_create", arguments())
    try:
        assert entered.wait(5)
        assert service.cancel(started["id"])["status"] == "CANCEL_REQUESTED"
    finally:
        release.set()
    terminal = finish(service, started["id"])
    assert terminal["status"] == ("FAILED" if raise_error else "COMPLETED")
    assert terminal["cancel_requested"] and not terminal["cancel_observed"]
    if not raise_error:
        assert terminal["result"] == lab.inspect_study("S-cancel")
    assert service.cancel(started["id"]) == terminal
    assert service.shutdown(timeout=1)["joined"]


def test_cancellation_during_preflight_prevents_method(service, monkeypatch):
    entered, release = threading.Event(), threading.Event()
    method_calls = []

    def preflight(*args, **kwargs):
        entered.set()
        assert release.wait(5)

    monkeypatch.setattr(service, "_campaign_preflight", preflight)
    monkeypatch.setattr(service._selected().lab, "run_doe", lambda campaign_id: method_calls.append(campaign_id))
    started = service.submit("doe_run", {"campaign_id": "C-pending"})
    try:
        assert entered.wait(5)
        service.cancel(started["id"])
    finally:
        release.set()
    terminal = finish(service, started["id"])
    assert terminal["status"] == "CANCELLED" and terminal["cancel_observed"]
    assert method_calls == []
    assert service.shutdown(timeout=1)["joined"]


@pytest.mark.parametrize("failure", [SystemExit(7), KeyboardInterrupt()])
def test_worker_baseexception_has_terminal_failure_and_retained_files(service, monkeypatch, failure):
    lab = service._selected().lab
    original = lab.create_study

    def controlled(**values):
        original(**values)
        raise failure

    monkeypatch.setattr(lab, "create_study", controlled)
    started = service.submit("study_create", arguments())
    terminal = finish(service, started["id"])
    assert terminal["status"] == "FAILED" and not terminal["cancel_observed"]
    assert terminal["error"] == f"{type(failure).__name__}: {failure}"
    assert lab.inspect_study("S-cancel")["id"] == "S-cancel"
    assert service.shutdown(timeout=1) == {"accepting_jobs": False, "pending": [], "joined": True}


def test_bounded_shutdown_retains_pending_then_completes_unobserved(service, monkeypatch):
    entered, release = threading.Event(), threading.Event()
    lab = service._selected().lab
    original = lab.create_study

    def controlled(**values):
        entered.set()
        assert release.wait(5)
        return original(**values)

    monkeypatch.setattr(lab, "create_study", controlled)
    started = service.submit("study_create", arguments())
    try:
        assert entered.wait(5)
        before = time.monotonic()
        pending = service.shutdown(timeout=0)
        assert time.monotonic() - before < 1
        assert not pending["accepting_jobs"] and not pending["joined"]
        assert pending["pending"][0]["status"] == "CANCEL_REQUESTED"
        assert not pending["pending"][0]["cancel_observed"]
        with pytest.raises(ServiceError) as failure:
            service.submit("study_create", arguments("S-after-shutdown"))
        assert failure.value.status == 503
    finally:
        release.set()
    assert finish(service, started["id"])["status"] == "COMPLETED"
    assert service.shutdown(timeout=1) == {"accepting_jobs": False, "pending": [], "joined": True}
    assert service.shutdown(timeout=0)["joined"]


@pytest.mark.parametrize("timeout", [True, -1, float("nan"), float("inf"), "1", 10 ** 1000])
def test_invalid_shutdown_timeout_does_not_close_admission(service, timeout):
    with pytest.raises(ServiceError) as failure:
        service.shutdown(timeout=timeout)
    assert failure.value.status == 400
    assert finish(service, service.submit("study_create", arguments())["id"])["status"] == "COMPLETED"


def test_shutdown_observes_checkpoint_and_reaps_one_tiny_owned_python_child(service, monkeypatch):
    entered = threading.Event()
    children = []

    def controlled(**values):
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"],
                                 cwd=service._selected().path, stdin=subprocess.DEVNULL,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                 start_new_session=os.name == "posix")
        children.append(child)
        entered.set()
        try:
            wait_for_process(child, timeout=5)
        finally:
            stop_owned_process(child, isolated_group=os.name == "posix")

    monkeypatch.setattr(service._selected().lab, "create_study", controlled)
    started = service.submit("study_create", arguments())
    try:
        assert entered.wait(5)
        assert service.shutdown(timeout=2) == {"accepting_jobs": False, "pending": [], "joined": True}
    finally:
        for child in children:
            if child.poll() is None:
                stop_owned_process(child, isolated_group=os.name == "posix")
    terminal = service.job(started["id"])
    assert terminal["status"] == "CANCELLED" and terminal["cancel_observed"]
    assert len(children) == 1 and children[0].poll() is not None


@pytest.mark.skipif(os.name != "posix", reason="POSIX group cleanup failure control")
@pytest.mark.parametrize("return_core_failure", [False, True])
def test_cleanup_failure_retains_writer_until_child_reaped_and_worker_dead(
        service, monkeypatch, return_core_failure):
    entered, operation_done, worker_exit = (threading.Event() for _ in range(3))
    children = []
    real_killpg = control.os.killpg
    original_execute = service._execute
    core_result = {"status": "FAILED_EXECUTION", "solver_status": "FAILED_EXECUTION",
                   "metrics": {}, "decision": "NOT_RELEASED", "test_only": True}
    evidence = service._selected().path / "partial-cleanup-evidence.txt"

    def deny_owned_group(pid, sig):
        if children and pid == children[0].pid and sig == control.signal.SIGKILL:
            raise PermissionError("test-only owned group cleanup failure")
        return real_killpg(pid, sig)

    def controlled(**values):
        evidence.write_bytes(b"Retain original partial execution evidence")
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"],
                                 cwd=service._selected().path, stdin=subprocess.DEVNULL,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                 start_new_session=True)
        children.append(child)
        entered.set()
        try:
            wait_for_process(child, timeout=5)
        except ExecutionCancelled:
            try:
                stop_owned_process(child, isolated_group=True)
            except ExecutionCleanupFailed:
                if return_core_failure:
                    return core_result
                raise
            raise
        else:
            stop_owned_process(child, isolated_group=True)

    def held_worker(*args):
        original_execute(*args)
        operation_done.set()
        assert worker_exit.wait(5)

    monkeypatch.setattr(control.os, "killpg", deny_owned_group)
    monkeypatch.setattr(service._selected().lab, "create_study", controlled)
    if return_core_failure:
        monkeypatch.setattr(service, "_execute", held_worker)
    started = service.submit("study_create", arguments())
    try:
        assert entered.wait(5)
        service.cancel(started["id"])
        pending = finish(service, started["id"])
        assert pending["status"] == "CLEANUP_PENDING"
        assert pending["cancel_observed"] and pending["cleanup_pending"]
        assert pending["deferred_terminal_status"] == "CANCELLED"
        assert "operation_finished_utc" in pending and "completed_utc" not in pending
        assert pending["cleanup_owners"] == [{"pid": children[0].pid, "isolated_group": True,
                                              "leader_reaped": False}]
        if return_core_failure:
            assert operation_done.wait(5) and pending["result"] == core_result
        else:
            service._job_threads[started["id"]].join(timeout=1)
            assert not service._job_threads[started["id"]].is_alive()
            assert "ExecutionCleanupFailed" in pending["error"]
        for call in (lambda: service.submit("study_create", arguments("S-not-admitted")),
                     lambda: service.select_store("local")):
            with pytest.raises(ServiceError) as failure:
                call()
            assert failure.value.status == 409
        assert service.cancel(started["id"])["status"] == "CLEANUP_PENDING"
        before = time.monotonic()
        shutdown = service.shutdown(timeout=.05)
        elapsed = time.monotonic() - before
        assert not shutdown["joined"] and shutdown["pending"][0]["status"] == "CLEANUP_PENDING"
        assert .04 <= elapsed < .5
        assert evidence.read_bytes() == b"Retain original partial execution evidence"
        assert children[0].poll() is None
        monkeypatch.setattr(control.os, "killpg", real_killpg)
        retry = service.cancel(started["id"])
        assert children[0].poll() is not None and not retry["cleanup_pending"]
        if return_core_failure:
            # Confirmed native cleanup alone cannot release a still-live worker.
            assert retry["status"] == "CLEANUP_PENDING" and "completed_utc" not in retry
            assert service._active_job == started["id"]
            worker_exit.set()
            service._job_threads[started["id"]].join(timeout=1)
            retry = service.cancel(started["id"])
        assert retry["status"] == "CANCELLED" and "completed_utc" in retry
        assert service._active_job is None and service.cancel(started["id"]) == retry
        assert service.shutdown(timeout=1) == {"accepting_jobs": False, "pending": [], "joined": True}
        if return_core_failure:
            assert retry["result"] == core_result
        assert evidence.read_bytes() == b"Retain original partial execution evidence"
    finally:
        worker_exit.set()
        monkeypatch.setattr(control.os, "killpg", real_killpg)
        for child in children:
            if child.poll() is None:
                stop_owned_process(child, isolated_group=True)
        service.shutdown(timeout=1)


@contextmanager
def http_server(service):
    server = LabHTTPServer(service, 0)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": .01}, daemon=True)
    thread.start()

    def request(path, body=None, *, headers=None, expected=200):
        connection = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
        options = {"Content-Type": "application/json", "X-CAE-Token": service.token}
        options.update(headers or {})
        try:
            connection.request("POST" if body is not None else "GET", path,
                               body=None if body is None else json.dumps(body), headers=options)
            response = connection.getresponse()
            payload = json.loads(response.read())
            assert response.status == expected, payload
            return payload
        finally:
            connection.close()

    try:
        yield request
    finally:
        service.shutdown(timeout=1)
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_http_cancel_preserves_host_origin_token_json_and_terminal_idempotence(service, monkeypatch):
    entered, release = threading.Event(), threading.Event()

    def controlled(**values):
        entered.set()
        assert release.wait(5)
        check_cancelled()

    monkeypatch.setattr(service._selected().lab, "create_study", controlled)
    with http_server(service) as request:
        started = request("/api/jobs", {"operation": "study_create", "arguments": arguments()}, expected=202)
        try:
            assert entered.wait(5)
            path = "/api/jobs/" + started["id"] + "/cancel"
            for headers in ({"X-CAE-Token": "wrong"}, {"Origin": "https://foreign.example"},
                            {"Host": "foreign.example"}, {"Sec-Fetch-Site": "cross-site"}):
                request(path, {}, headers=headers, expected=403)
            request(path, {}, headers={"Content-Type": "text/plain"}, expected=415)
            request(path, {"extra": True}, expected=400)
            request(path, [], expected=400)
            request("/api/jobs/J-unknown/cancel", {}, expected=404)
            assert not service.job(started["id"])["cancel_requested"]
            assert request(path, {}, expected=202)["status"] == "CANCEL_REQUESTED"
            request("/api/store", {"id": "local"}, expected=409)
            request("/api/jobs", {"operation": "study_create", "arguments": arguments("S-other")}, expected=409)
        finally:
            release.set()
        terminal = finish(service, started["id"])
        assert terminal["status"] == "CANCELLED" and terminal["cancel_observed"]
        assert request(path, {}, expected=200) == terminal
        assert request("/api/jobs/" + started["id"]) == terminal


def test_server_main_keeps_process_until_pending_worker_terminal(tmp_path, monkeypatch, capsys):
    entered, release = threading.Event(), threading.Event()
    reports, instances = [], []

    class ControlledServer:
        def __init__(self, service, port):
            self.service, self.server_port = service, port
            self.closed = False
            instances.append(self)
            lab = service._selected().lab
            original_create = lab.create_study
            original_shutdown = service.shutdown

            def controlled(**values):
                entered.set()
                assert release.wait(5)
                return original_create(**values)

            def shutdown(timeout):
                report = original_shutdown(timeout=0 if not reports else timeout)
                reports.append(report)
                if len(reports) == 1:
                    release.set()
                return report

            monkeypatch.setattr(lab, "create_study", controlled)
            monkeypatch.setattr(service, "shutdown", shutdown)

        def serve_forever(self):
            self.job_id = self.service.submit("study_create", arguments())["id"]
            assert entered.wait(5)
            raise KeyboardInterrupt

        def server_close(self):
            assert reports[-1]["joined"] and reports[-1]["pending"] == []
            self.closed = True

    monkeypatch.setattr(server_module, "LabHTTPServer", ControlledServer)
    try:
        server_module.main(["--store", str(tmp_path / "main-store"), "--port", "0"])
    finally:
        release.set()
    assert reports[0]["pending"][0]["status"] == "CANCEL_REQUESTED"
    assert len(reports) >= 2 and instances[0].closed
    assert instances[0].service.job(instances[0].job_id)["status"] == "COMPLETED"
    assert capsys.readouterr().err.count("Waiting for cooperative Lab worker shutdown") == 1
