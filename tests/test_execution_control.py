"""User cancellation is a resource event, never a numerical verdict."""

from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

import pytest

from caelab.adapters.codeaster_elasticity import _process
from caelab.execution_control import (CancellationToken, ExecutionCancelled, ExecutionCleanupFailed,
    cancellation_scope, check_cancelled, stop_owned_process, wait_for_process)


def wait_for(path):
    deadline = time.monotonic() + 5
    while not path.exists():
        assert time.monotonic() < deadline, f"Missing tiny-process marker {path.name}"
        time.sleep(.01)


def test_request_is_distinct_from_observation_and_scope_is_reset():
    token = CancellationToken()
    token.request()
    assert token.requested and not token.observed
    with cancellation_scope(token):
        with pytest.raises(ExecutionCancelled, match="UNKNOWN"):
            check_cancelled()
    assert token.observed
    check_cancelled()


def test_token_does_not_leak_to_another_thread():
    token = CancellationToken()
    token.request()
    with cancellation_scope(token), ThreadPoolExecutor(max_workers=1) as pool:
        pool.submit(check_cancelled).result(timeout=5)
    assert not token.observed


def test_completed_process_is_not_falsely_cancelled_by_late_request():
    process = subprocess.Popen([sys.executable, "-c", "pass"])
    assert process.wait(timeout=5) == 0
    token = CancellationToken()
    token.request()
    with cancellation_scope(token):
        assert wait_for_process(process, timeout=None) == 0
    assert token.requested and not token.observed


def test_explicit_wall_budget_remains_a_timeout_without_cancellation():
    process = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"],
                               start_new_session=os.name == "posix")
    token = CancellationToken()
    try:
        with cancellation_scope(token), pytest.raises(subprocess.TimeoutExpired):
            wait_for_process(process, timeout=.1)
        assert not token.requested and not token.observed
    finally:
        stop_owned_process(process, isolated_group=os.name == "posix")


def test_prelaunch_request_blocks_process_and_records_resource_reason(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("A cancelled operation launched a process")
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    token = CancellationToken()
    token.request()
    with cancellation_scope(token), pytest.raises(ExecutionCancelled):
        _process([sys.executable, "-c", "pass"], tmp_path, "solver", timeout=None)
    state = json.loads((tmp_path / "solver.execution.json").read_text())
    assert state["status"] == "CANCELLED" and state["reason"] == "USER_REQUEST"
    assert state["pid"] is None and token.observed
    assert not (tmp_path / "analysis_raw.json").exists()


@pytest.mark.skipif(os.name != "posix", reason="Native solver groups run in Linux/WSL")
def test_failed_group_signal_keeps_ownership_and_cleanup_state_unknown(tmp_path, monkeypatch):
    from caelab import execution_control as control
    token = CancellationToken()
    source = "from pathlib import Path; import time; print('partial',flush=True); Path('entered').touch(); time.sleep(30)"
    def run():
        with cancellation_scope(token):
            return _process([sys.executable, "-u", "-c", source], tmp_path, "solver", timeout=None)
    def unavailable(*args):
        raise PermissionError("TEST_ONLY termination signal rejected")
    with ThreadPoolExecutor(max_workers=1) as pool:
        try:
            future = pool.submit(run)
            wait_for(tmp_path / "entered")
            with monkeypatch.context() as fault:
                fault.setattr(control.os, "killpg", unavailable)
                token.request()
                with pytest.raises(ExecutionCleanupFailed, match="UNKNOWN"):
                    future.result(timeout=5)
                assert token.observed and token.cleanup_pending
                assert token.cleanup_owners[0]["leader_reaped"] is False
                assert token.retry_cleanup(timeout=0) is True
                state = json.loads((tmp_path / "solver.execution.json").read_text())
                assert state["status"] == "CLEANUP_PENDING"
                assert state["reason"] == "GROUP_CLEANUP_UNCONFIRMED"
                assert "finished_utc" not in state
                assert "partial" in (tmp_path / "solver.stdout.log").read_text()
        finally:
            token.request()
            assert token.retry_cleanup() is False
    assert token.cleanup_owners == []
    assert not (tmp_path / "analysis_raw.json").exists()


@pytest.mark.skipif(os.name != "posix", reason="POSIX process group ownership")
def test_reaped_leader_never_authorizes_killing_a_reused_group(monkeypatch):
    from caelab import execution_control as control
    class Reaped:
        pid, returncode = 314159, 0
    signals = []
    monkeypatch.setattr(control.os, "killpg", lambda pid, sig: signals.append((pid, sig)))
    token = CancellationToken()
    token._retain_cleanup(Reaped(), True)
    assert token.retry_cleanup() is True
    assert signals == [(314159, 0)]


@pytest.mark.skipif(os.name != "posix", reason="POSIX process group ownership")
def test_concurrent_cleanup_retries_serialize_owner_check_signal_and_reap(monkeypatch):
    from caelab import execution_control as control
    class Owned:
        pid, returncode = 271828, None
        def wait(self, timeout):
            self.returncode = -9
            return -9
    entered, release, attempted, returned = (threading.Event() for _ in range(4))
    signals = []
    original_stop = control.stop_owned_process
    def stop(process, **options):
        entered.set()
        assert release.wait(5)
        return original_stop(process, **options)
    def second_retry(token):
        attempted.set()
        try:
            return token.retry_cleanup()
        finally:
            returned.set()
    monkeypatch.setattr(control, "stop_owned_process", stop)
    monkeypatch.setattr(control.os, "killpg", lambda pid, sig: signals.append((pid, sig)))
    token = CancellationToken()
    token._retain_cleanup(Owned(), True)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(token.retry_cleanup)
        try:
            assert entered.wait(5)
            second = pool.submit(second_retry, token)
            assert attempted.wait(5) and not returned.wait(.05)
        finally:
            release.set()
        assert first.result(timeout=5) is False
        assert second.result(timeout=5) is False
    assert signals == [(271828, control.signal.SIGKILL)]
    assert not token.cleanup_pending


@pytest.mark.skipif(os.name != "posix", reason="Native solver groups run in Linux/WSL")
def test_request_stops_owned_runner_and_child_and_preserves_partial_logs(tmp_path):
    token = CancellationToken()
    source = (
        "import subprocess,sys,time; from pathlib import Path; "
        "child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)']); "
        "print(child.pid,flush=True); print('partial native output',flush=True); "
        "Path('entered').touch(); time.sleep(30)"
    )
    def run():
        with cancellation_scope(token):
            return _process([sys.executable, "-u", "-c", source], tmp_path, "solver", timeout=None)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(run)
        try:
            wait_for(tmp_path / "entered")
            assert not future.done()
        finally:
            token.request()
        with pytest.raises(ExecutionCancelled):
            future.result(timeout=5)
    state = json.loads((tmp_path / "solver.execution.json").read_text())
    assert state["status"] == "CANCELLED" and state["reason"] == "USER_REQUEST"
    assert state["return_code"] != 0 and token.observed
    assert not Path(f"/proc/{state['pid']}").exists()
    output = (tmp_path / "solver.stdout.log").read_text()
    assert "partial native output" in output
    child = int(output.splitlines()[0])
    child_state = Path(f"/proc/{child}/stat")
    assert not child_state.exists() or child_state.read_text().split()[2] == "Z"
    assert "User cancellation observed" in (tmp_path / "solver.stderr.log").read_text()
    assert not (tmp_path / "analysis_raw.json").exists()
