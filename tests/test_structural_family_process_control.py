"""Local process-control checks, never CalculiX, provider or physics proof."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest

from caelab import execution_control as control
from caelab.adapters import structural_family_calculix as adapter


def _wait_for(path, seconds=5):
    deadline = time.monotonic() + seconds
    while not path.is_file():
        if time.monotonic() >= deadline:
            pytest.fail(f"Local test runner did not create {path.name}")
        time.sleep(.01)


def _stopped(pid):
    try:
        status = Path(f"/proc/{pid}/stat").read_text()
    except FileNotFoundError:
        # A killed child can be reaped between any existence check and read.
        return True
    return status.split()[2] == "Z"


@pytest.mark.parametrize("observation,expected", [
    (FileNotFoundError, True),
    ("7014 (python) Z 1 1 1", True),
    ("7014 (python) S 1 1 1", False),
    ("7014 (python) R 1 1 1", False),
    (PermissionError, PermissionError),
    ("malformed", IndexError),
])
def test_stopped_proc_read_preserves_absence_zombie_live_and_error_states(monkeypatch, observation, expected):
    class Status:
        def exists(self):
            pytest.fail("A separate existence check races with child reaping")

        def read_text(self):
            if isinstance(observation, type):
                raise observation("SYNTHETIC PROC READ ONLY")
            return observation

    def status_path(path):
        assert path == "/proc/7014/stat"
        return Status()

    monkeypatch.setattr(sys.modules[__name__], "Path", status_path)
    if isinstance(expected, type):
        with pytest.raises(expected):
            _stopped(7014)
    else:
        assert _stopped(7014) is expected


def test_prelaunch_user_cancel_records_refusal_without_a_process(tmp_path, monkeypatch):
    token = control.CancellationToken()
    token.request()
    monkeypatch.setattr(adapter.subprocess, "Popen",
                        lambda *args, **kwargs: pytest.fail("Prelaunch cancellation cannot start a process"))
    with control.cancellation_scope(token), pytest.raises(control.ExecutionCancelled):
        adapter._process(["TEST_ONLY_NOT_EXECUTED"], tmp_path, "solver")
    state = json.loads((tmp_path / "solver.exit.json").read_text())
    assert token.observed and state == {"returncode": None, "timed_out": False,
                                        "cancelled": True, "reason": "USER_REQUEST"}
    assert (tmp_path / "solver.stdout.log").read_bytes() == b""
    assert (tmp_path / "solver.stderr.log").read_bytes() == b""
    assert not (tmp_path / "analysis_raw.json").exists()


@pytest.mark.skipif(sys.platform != "linux", reason="Owned native process groups run in Linux/WSL")
def test_user_cancel_stops_owned_local_runner_and_child_preserves_partial_files(tmp_path):
    token = control.CancellationToken()
    source = (
        "from pathlib import Path; import os,subprocess,sys,time; "
        "child=subprocess.Popen([sys.executable,'-u','-c','import time; time.sleep(60)']); "
        "Path('runner.pid').write_text(str(os.getpid())); Path('child.pid').write_text(str(child.pid)); "
        "Path('partial_native.bin').write_bytes(b'LOCAL TEST ONLY; no native fields'); "
        "print('local runner partial stdout',flush=True); print('local runner partial stderr',file=sys.stderr,flush=True); "
        "Path('entered').touch(); time.sleep(60)"
    )
    sentinel = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"],
                                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL, start_new_session=True)
    def run():
        with control.cancellation_scope(token):
            return adapter._process([sys.executable, "-u", "-c", source], tmp_path, "solver")
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            job = pool.submit(run)
            try:
                _wait_for(tmp_path / "entered")
                runner, child = [int((tmp_path / name).read_text()) for name in ("runner.pid", "child.pid")]
                token.request()
                with pytest.raises(control.ExecutionCancelled): job.result(timeout=5)
            finally:
                token.request()
        assert token.observed and _stopped(runner) and _stopped(child)
        assert sentinel.poll() is None  # A separate owned group stays alive.
        state = json.loads((tmp_path / "solver.exit.json").read_text())
        assert state["returncode"] != 0 and state["cancelled"] is True
        assert state["timed_out"] is False and state["reason"] == "USER_REQUEST"
        assert "partial stdout" in (tmp_path / "solver.stdout.log").read_text()
        assert "partial stderr" in (tmp_path / "solver.stderr.log").read_text()
        assert (tmp_path / "partial_native.bin").read_bytes() == b"LOCAL TEST ONLY; no native fields"
        assert not (tmp_path / "analysis_raw.json").exists()
    finally:
        control.stop_owned_process(sentinel, isolated_group=True)


@pytest.mark.skipif(sys.platform != "linux", reason="Owned native process groups run in Linux/WSL")
def test_failed_group_kill_retains_actual_owner_until_explicit_cleanup_retry(tmp_path, monkeypatch):
    token = control.CancellationToken()
    launched, denied = [], []
    original_popen, original_killpg = subprocess.Popen, os.killpg
    source = (
        "from pathlib import Path; import os,subprocess,sys,time; "
        "child=subprocess.Popen([sys.executable,'-u','-c','import time; time.sleep(60)']); "
        "Path('child.pid').write_text(str(child.pid)); "
        "Path('partial_native.bin').write_bytes(b'LOCAL CLEANUP FAILURE TEST ONLY'); "
        "print('cleanup partial stdout',flush=True); print('cleanup partial stderr',file=sys.stderr,flush=True); "
        "Path('entered').touch(); time.sleep(60)"
    )
    def popen(*args, **kwargs):
        actual = original_popen(*args, **kwargs)
        launched.append(actual)
        return actual
    def deny_first_owned_kill(pid, sig):
        if launched and pid == launched[0].pid and not denied:
            denied.append(pid)
            raise PermissionError("LOCAL FAULT INJECTION ONLY")
        return original_killpg(pid, sig)
    monkeypatch.setattr(adapter.subprocess, "Popen", popen)
    monkeypatch.setattr(control.os, "killpg", deny_first_owned_kill)
    def run():
        with control.cancellation_scope(token):
            return adapter._process([sys.executable, "-u", "-c", source], tmp_path, "solver")
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            job = pool.submit(run)
            try:
                _wait_for(tmp_path / "entered")
                token.request()
                with pytest.raises(control.ExecutionCleanupFailed): job.result(timeout=5)
            finally:
                token.request()
        assert len(launched) == 1 and denied == [launched[0].pid]
        actual, child = launched[0], int((tmp_path / "child.pid").read_text())
        assert token.observed and token.cleanup_pending and actual.poll() is None and not _stopped(child)
        assert token.cleanup_owners == [{"pid": actual.pid, "isolated_group": True, "leader_reaped": False}]
        assert not issubclass(control.ExecutionCleanupFailed, control.ExecutionCancelled)
        pending_bytes = (tmp_path / "solver.exit.json").read_bytes()
        state = json.loads(pending_bytes)
        assert state["returncode"] is None and state["cancelled"] is False and state["cleanup_pending"] is True
        assert state["reason"] == "GROUP_CLEANUP_UNCONFIRMED" and state["original_reason"] == "USER_REQUEST"
        assert state["termination"] == "UNKNOWN" and state["timed_out"] is False
        assert "cleanup partial stdout" in (tmp_path / "solver.stdout.log").read_text()
        assert "cleanup partial stderr" in (tmp_path / "solver.stderr.log").read_text()
        monkeypatch.setattr(control.os, "killpg", original_killpg)
        assert token.retry_cleanup() is False
        assert not token.cleanup_pending and token.cleanup_owners == []
        assert actual.returncode is not None and _stopped(actual.pid) and _stopped(child)
        # Retain the original failed-stop observation; retry confirmation is
        # separate ownership evidence rather than a rewritten numerical result.
        assert (tmp_path / "solver.exit.json").read_bytes() == pending_bytes
        assert (tmp_path / "partial_native.bin").read_bytes() == b"LOCAL CLEANUP FAILURE TEST ONLY"
        assert not (tmp_path / "analysis_raw.json").exists()
    finally:
        monkeypatch.setattr(control.os, "killpg", original_killpg)
        token.request()
        if token.cleanup_pending: token.retry_cleanup()
        for actual in launched:
            if actual.returncode is None: control.stop_owned_process(actual, isolated_group=True)


def test_request_arriving_after_process_completion_does_not_invent_cancellation(tmp_path, monkeypatch):
    token = control.CancellationToken()
    original = control.wait_for_process
    def wait_then_request(process, timeout=None):
        result = original(process, timeout=timeout)
        token.request()  # The runner has already completed before this request.
        return result
    monkeypatch.setattr(control, "wait_for_process", wait_then_request)
    with control.cancellation_scope(token):
        text = adapter._process([sys.executable, "-u", "-c", "print('LOCAL COMPLETED; no native solver')"],
                                tmp_path, "solver", timeout=2)
    assert token.requested and not token.observed and "LOCAL COMPLETED" in text
    state = json.loads((tmp_path / "solver.exit.json").read_text())
    assert state == {"returncode": 0, "timed_out": False, "cancelled": False}


@pytest.mark.skipif(sys.platform != "linux", reason="Owned native process groups run in Linux/WSL")
def test_existing_wall_timeout_remains_distinct_from_user_cancel(tmp_path):
    token = control.CancellationToken()
    source = (
        "from pathlib import Path; import os,sys,time; Path('runner.pid').write_text(str(os.getpid())); "
        "Path('partial_native.bin').write_bytes(b'LOCAL TIMEOUT TEST ONLY'); "
        "print('timeout partial stdout',flush=True); print('timeout partial stderr',file=sys.stderr,flush=True); "
        "time.sleep(60)"
    )
    with control.cancellation_scope(token), pytest.raises(RuntimeError, match="timed out"):
        adapter._process([sys.executable, "-u", "-c", source], tmp_path, "solver", timeout=1)
    state = json.loads((tmp_path / "solver.exit.json").read_text())
    assert state["returncode"] != 0 and state["timed_out"] is True and state["cancelled"] is False
    assert state["reason"] == "WALL_TIME_BUDGET" and not token.requested and not token.observed
    assert _stopped(int((tmp_path / "runner.pid").read_text()))
    assert "timeout partial stdout" in (tmp_path / "solver.stdout.log").read_text()
    assert "timeout partial stderr" in (tmp_path / "solver.stderr.log").read_text()
    assert (tmp_path / "partial_native.bin").read_bytes() == b"LOCAL TIMEOUT TEST ONLY"


class _ShutdownSignal(BaseException):
    pass


@pytest.mark.parametrize("interruption,reason,timed_out", [
    (subprocess.TimeoutExpired(["TEST_ONLY"], 240), "WALL_TIME_BUDGET", True),
    (KeyboardInterrupt("TEST_ONLY_INTERRUPT"), "INTERRUPTED", False),
    (_ShutdownSignal("TEST_ONLY_INTERRUPT"), "INTERRUPTED", False),
])
def test_cleanup_failure_retains_original_timeout_or_interruption_cause(tmp_path, monkeypatch, interruption, reason, timed_out):
    class Process:
        pid, returncode = 91, None
    process = Process()
    def popen(command, **kwargs):
        kwargs["stdout"].write(b"partial cleanup-failure stdout")
        kwargs["stderr"].write(b"partial cleanup-failure stderr")
        return process
    def wait(*args, **kwargs): raise interruption
    def refuse_cleanup(actual, *, isolated_group):
        assert actual is process and isolated_group is (os.name == "posix")
        raise control.ExecutionCleanupFailed("TEST_ONLY_UNCONFIRMED_CLEANUP")
    monkeypatch.setattr(adapter.subprocess, "Popen", popen)
    monkeypatch.setattr(control, "wait_for_process", wait)
    monkeypatch.setattr(control, "stop_owned_process", refuse_cleanup)
    with pytest.raises(control.ExecutionCleanupFailed):
        adapter._process(["TEST_ONLY_NOT_EXECUTED"], tmp_path, "solver")
    state = json.loads((tmp_path / "solver.exit.json").read_text())
    assert state["cancelled"] is False and state["cleanup_pending"] is True and state["termination"] == "UNKNOWN"
    assert state["reason"] == "GROUP_CLEANUP_UNCONFIRMED" and state["original_reason"] == reason
    assert state["timed_out"] is timed_out and state["returncode"] is None
    if reason == "INTERRUPTED": assert state["exception_type"] == type(interruption).__name__
    assert "TEST_ONLY_INTERRUPT" not in json.dumps(state)
    assert "TEST_ONLY_UNCONFIRMED_CLEANUP" not in json.dumps(state)
    assert (tmp_path / "solver.stdout.log").read_bytes() == b"partial cleanup-failure stdout"
    assert (tmp_path / "solver.stderr.log").read_bytes() == b"partial cleanup-failure stderr"


@pytest.mark.parametrize("exception", [KeyboardInterrupt, SystemExit, _ShutdownSignal])
def test_baseexception_wait_stops_and_reaps_only_owned_process(tmp_path, monkeypatch, exception):
    cleaned = []
    class Process:
        pid, returncode, reaped = 91, None, False
    process = Process()
    def popen(command, **kwargs):
        assert kwargs["start_new_session"] is (os.name == "posix")
        kwargs["stdout"].write(b"partial interrupted stdout")
        kwargs["stderr"].write(b"partial interrupted stderr")
        return process
    def interrupt(*args, **kwargs): raise exception("TEST_ONLY_INTERRUPT")
    def cleanup(actual, *, isolated_group):
        cleaned.append((actual, isolated_group))
        actual.returncode, actual.reaped = -9, True
    monkeypatch.setattr(adapter.subprocess, "Popen", popen)
    monkeypatch.setattr(control, "wait_for_process", interrupt)
    monkeypatch.setattr(control, "stop_owned_process", cleanup)
    with pytest.raises(exception): adapter._process(["TEST_ONLY_NOT_EXECUTED"], tmp_path, "solver")
    assert cleaned == [(process, os.name == "posix")] and process.reaped
    state = json.loads((tmp_path / "solver.exit.json").read_text())
    assert state["returncode"] == -9 and state["reason"] == "INTERRUPTED"
    assert state["exception_type"] == exception.__name__ and state["cancelled"] is False and state["timed_out"] is False
    assert "TEST_ONLY_INTERRUPT" not in json.dumps(state)
    assert (tmp_path / "solver.stdout.log").read_bytes() == b"partial interrupted stdout"
    assert (tmp_path / "solver.stderr.log").read_bytes() == b"partial interrupted stderr"


@pytest.mark.parametrize("timeout", [None, 0, -1, 241, True, 1.5])
def test_existing_fixed_ccx_budget_is_unchanged_and_refuses_invalid_values(tmp_path, monkeypatch, timeout):
    assert adapter._TIMEOUT == 240
    monkeypatch.setattr(adapter.subprocess, "Popen",
                        lambda *args, **kwargs: pytest.fail("Invalid budget cannot launch"))
    with pytest.raises(ValueError, match="fixed timeout budget"):
        adapter._process(["TEST_ONLY_NOT_EXECUTED"], tmp_path, "solver", timeout=timeout)
    assert not (tmp_path / "solver.command.json").exists()


def test_common_control_source_is_frozen_with_native_input_provenance(tmp_path):
    path = Path(control.__file__).resolve()
    assert path in adapter.StructuralFamilyCalculiXAdapter.input_source_files
    assert adapter._SOURCE_HASHES[path] == hashlib.sha256(path.read_bytes()).hexdigest()
    files = adapter._capture_sources(tmp_path)
    key = path.relative_to(adapter._ROOT).as_posix()
    assert key == "caelab/execution_control.py"
    assert files[key]["sha256"] == adapter._SOURCE_HASHES[path]
    assert (tmp_path / "source_snapshot" / key).read_bytes() == path.read_bytes()
