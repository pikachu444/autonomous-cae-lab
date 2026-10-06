"""Generic command lifetime tests use owned child handles, never saved PID adoption."""

from concurrent.futures import ThreadPoolExecutor
import json
import os
import sys
import time

import pytest

from caelab.execution_control import (CancellationToken, ExecutionCancelled, ExecutionCleanupFailed,
                                     cancellation_scope, run_owned_command)


def wait_for(path):
    deadline = time.monotonic() + 5
    while not path.exists():
        assert time.monotonic() < deadline
        time.sleep(.01)


def test_owned_completion_captures_output_and_real_exit_without_engineering_verdict(tmp_path):
    result = run_owned_command([sys.executable, '-c', "import sys; print('observed'); print('diagnostic',file=sys.stderr)"],
                               tmp_path, 'native')
    assert result.returncode == 0 and result.stdout == 'observed\n' and result.stderr == 'diagnostic\n'
    state = json.loads((tmp_path / 'native.execution.json').read_text())
    assert state['status'] == 'COMPLETED' and state['return_code'] == 0
    assert state['timeout_seconds'] is None and 'finished_utc' in state
    assert 'engineering' not in state and 'converged' not in state


def test_prelaunch_cancellation_never_creates_child(tmp_path, monkeypatch):
    import subprocess
    def forbidden(*args, **kwargs):
        pytest.fail('Cancelled operation started a command')
    monkeypatch.setattr(subprocess, 'Popen', forbidden)
    token = CancellationToken()
    token.request()
    with cancellation_scope(token), pytest.raises(ExecutionCancelled):
        run_owned_command([sys.executable, '-c', 'pass'], tmp_path, 'native')
    state = json.loads((tmp_path / 'native.execution.json').read_text())
    assert state['status'] == 'CANCELLED' and state['pid'] is None and token.observed


def test_actual_owned_child_cancellation_preserves_partial_output_and_reaps_handle(tmp_path):
    token = CancellationToken()
    code = "from pathlib import Path; import time; print('partial response',flush=True); Path('entered').touch(); time.sleep(30)"
    def run():
        with cancellation_scope(token):
            return run_owned_command([sys.executable, '-u', '-c', code], tmp_path, 'native')
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(run)
        wait_for(tmp_path / 'entered')
        token.request()
        with pytest.raises(ExecutionCancelled):
            future.result(timeout=5)
    state = json.loads((tmp_path / 'native.execution.json').read_text())
    assert state['status'] == 'CANCELLED' and state['return_code'] is not None
    assert token.observed and not token.cleanup_pending
    assert 'partial response' in (tmp_path / 'native.stdout.log').read_text()


@pytest.mark.skipif(os.name != 'posix', reason='Native isolated solver group lifetime runs in Linux/WSL')
def test_unconfirmed_stop_retains_live_ownership_until_cleanup_retry(tmp_path, monkeypatch):
    from caelab import execution_control as control
    token = CancellationToken()
    code = "from pathlib import Path; import time; Path('entered').touch(); time.sleep(30)"
    def run():
        with cancellation_scope(token):
            return run_owned_command([sys.executable, '-u', '-c', code], tmp_path, 'native')
    def refused(*args):
        raise PermissionError('TEST_ONLY signal rejection')
    with ThreadPoolExecutor(max_workers=1) as pool:
        try:
            future = pool.submit(run)
            wait_for(tmp_path / 'entered')
            with monkeypatch.context() as fault:
                fault.setattr(control.os, 'killpg', refused)
                token.request()
                with pytest.raises(ExecutionCleanupFailed):
                    future.result(timeout=5)
                state = json.loads((tmp_path / 'native.execution.json').read_text())
                assert state['status'] == 'CLEANUP_PENDING' and 'finished_utc' not in state
                assert token.cleanup_pending and not token.cleanup_owners[0]['leader_reaped']
        finally:
            assert token.retry_cleanup() is False


def test_receipt_write_failure_after_launch_cleans_the_same_handle(tmp_path, monkeypatch):
    from caelab import storage
    original = storage.save_json
    def fail_running(path, value):
        if value.get('status') == 'RUNNING':
            raise ValueError('TEST_ONLY receipt write failed')
        return original(path, value)
    monkeypatch.setattr(storage, 'save_json', fail_running)
    token = CancellationToken()
    with cancellation_scope(token), pytest.raises(ValueError, match='receipt write failed'):
        run_owned_command([sys.executable, '-c', 'import time; time.sleep(30)'], tmp_path, 'native')
    state = json.loads((tmp_path / 'native.execution.json').read_text())
    assert state['status'] == 'INTERRUPTED' and state['return_code'] is not None
    assert not token.cleanup_pending
