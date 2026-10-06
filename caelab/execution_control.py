"""Cooperative, process-local execution control shared by existing runners.

Adapters still own native commands, isolation and budgets. A cancellation
request is acknowledged only at a checkpoint; completion is not a verdict.
"""

from contextlib import contextmanager
from contextvars import ContextVar
import os
import math
import signal
import subprocess
import threading
import time
from typing import Iterator


class ExecutionCancelled(RuntimeError):
    """The running operation observed its owner's cancellation request."""


class ExecutionCleanupFailed(RuntimeError):
    """An owned native process has not been confirmed stopped/reaped."""


class CancellationToken:
    def __init__(self):
        self._requested = threading.Event()
        self._observed = threading.Event()
        self._cleanup_lock = threading.RLock()
        self._cleanup: list[tuple[subprocess.Popen, bool]] = []

    @property
    def requested(self) -> bool:
        return self._requested.is_set()

    @property
    def observed(self) -> bool:
        return self._observed.is_set()

    @property
    def cleanup_pending(self) -> bool:
        with self._cleanup_lock:
            return bool(self._cleanup)

    @property
    def cleanup_owners(self) -> list[dict]:
        with self._cleanup_lock:
            return [{"pid": process.pid, "isolated_group": group,
                     "leader_reaped": process.returncode is not None}
                    for process, group in self._cleanup]

    def _retain_cleanup(self, process: subprocess.Popen, group: bool) -> None:
        with self._cleanup_lock:
            if not any(owner is process for owner, _ in self._cleanup):
                self._cleanup.append((process, group))

    def retry_cleanup(self, timeout: float = 1.0) -> bool:
        """Retry retained ownership, never signal a potentially reused group ID."""
        if type(timeout) not in (int, float) or not math.isfinite(timeout) or timeout < 0:
            raise ValueError("Cleanup confirmation budget must be finite and nonnegative")
        deadline = time.monotonic() + timeout
        with self._cleanup_lock:
            # A concurrent cancel/shutdown must not reap a leader between our
            # ownership check and signal. This lock also covers list removal.
            for process, group in list(self._cleanup):
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                if group and os.name == "posix" and process.returncode is not None:
                    # Reaping can release the leader PID. A later group with that
                    # number need not be ours; absence is safe proof, presence is not.
                    try:
                        os.killpg(process.pid, 0)
                    except ProcessLookupError:
                        pass
                    except OSError:
                        continue
                    else:
                        continue
                else:
                    try:
                        with cancellation_scope(self):
                            stop_owned_process(process, isolated_group=group, reap_timeout=min(1.0, remaining))
                    except ExecutionCleanupFailed:
                        continue
                self._cleanup = [(owner, isolated) for owner, isolated in self._cleanup
                                 if owner is not process]
            return bool(self._cleanup)

    def request(self) -> None:
        self._requested.set()

    def check(self) -> None:
        if self.requested:
            self._observed.set()
            raise ExecutionCancelled("User cancellation observed; partial evidence is retained; numerical verdict UNKNOWN")


_current: ContextVar[CancellationToken | None] = ContextVar("caelab_cancellation", default=None)


@contextmanager
def cancellation_scope(token: CancellationToken) -> Iterator[None]:
    binding = _current.set(token)
    try:
        yield
    finally:
        _current.reset(binding)


def check_cancelled() -> None:
    token = _current.get()
    if token is not None:
        token.check()


def cancelled_outcome(folder, backend: str, error: ExecutionCancelled, namespace: str) -> dict:
    """Retain a cancellation observation separately from numerical failure.

    Unconfirmed child cleanup must propagate instead of sealing mutable output.
    The lifecycle receipt is controller evidence, not a physical verdict.
    """
    from .storage import save_json, utc_now
    token = _current.get()
    if token is not None and token.cleanup_pending:
        raise ExecutionCleanupFailed('Cancellation cannot seal output while owned cleanup is pending')
    receipt = {'status': 'CANCELLED', 'reason': 'USER_REQUEST', 'backend': backend,
               'error_type': type(error).__name__, 'observation': str(error),
               'recorded_utc': utc_now(), 'numerical_verdict': 'UNKNOWN'}
    save_json(folder / 'execution.json', receipt)
    return {'status': 'REJECTED', 'solver_status': 'CANCELLED', 'converged': None,
            'checks': [{'code': namespace + '_cancelled', 'status': 'WARNING',
                        'observed': receipt, 'detail': 'User cancellation; retained partial evidence is not a completed solve'}],
            'metrics': {}, 'pending_validations': ['model_qualification', 'physical_validation'],
            'provenance': {'execution_lifecycle': receipt}, 'raw_result': 'execution.json'}


def run_owned_command(command, cwd, label, *, timeout=None, env=None):
    """Capture an adapter command using its live Popen ownership for cancellation.

    The adapter supplies all syntax and any existing budget. This helper does
    not reconnect to a recorded PID or treat a state file as a live handle.
    Logs and the termination receipt survive failure and requested cancellation.
    Optional adapter-owned environment values are passed to the live child only;
    credentials and the inherited environment are never copied into receipts.
    """
    from pathlib import Path
    from .storage import save_json, utc_now
    folder = Path(cwd)
    if env is not None:
        if (type(env) is not dict or any(type(key) is not str or not key or
                '=' in key or '\x00' in key or type(value) is not str or
                '\x00' in value for key, value in env.items())):
            raise ValueError('Native environment requires explicit string names and values')
        env = dict(env)
    if not isinstance(label, str) or not label or any(char not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for char in label):
        raise ValueError('Native log label must be a simple adapter-owned name')
    state = {'status': 'STARTING', 'started_utc': utc_now(), 'pid': None,
             'timeout_seconds': timeout, 'return_code': None,
             'stdout': f'{label}.stdout.log', 'stderr': f'{label}.stderr.log'}
    state_path = folder / f'{label}.execution.json'
    save_json(state_path, state)
    def finish(status, **details):
        state.update(status=status, finished_utc=utc_now(), **details)
        save_json(state_path, state)
    def stop(process, reason):
        try:
            stop_owned_process(process, isolated_group=os.name == 'posix')
        except ExecutionCleanupFailed:
            state.update(status='CLEANUP_PENDING', return_code=process.returncode,
                         termination_reason=reason, cleanup_observed_utc=utc_now())
            save_json(state_path, state)
            raise
    try:
        check_cancelled()
    except ExecutionCancelled:
        finish('CANCELLED', reason='USER_REQUEST')
        raise
    try:
        with (folder / state['stdout']).open('wb') as stdout, (folder / state['stderr']).open('wb') as stderr:
            process = subprocess.Popen(command, cwd=folder.resolve(), stdout=stdout, stderr=stderr,
                                       start_new_session=os.name == 'posix', env=env)
            try:
                state.update(status='RUNNING', pid=process.pid)
                save_json(state_path, state)
                wait_for_process(process, timeout=timeout)
            except ExecutionCancelled:
                stop(process, 'USER_REQUEST')
                finish('CANCELLED', reason='USER_REQUEST', return_code=process.returncode)
                raise
            except subprocess.TimeoutExpired:
                stop(process, 'WALL_TIME_BUDGET')
                finish('BUDGET_EXHAUSTED', reason='WALL_TIME_BUDGET', return_code=process.returncode)
                raise
            except BaseException:
                stop(process, 'INTERRUPTED')
                finish('INTERRUPTED', return_code=process.returncode)
                raise
    except OSError as error:
        finish('FAILED_EXECUTION', reason='PROCESS_START_ERROR', error_type=type(error).__name__)
        raise
    finish('COMPLETED' if process.returncode == 0 else 'FAILED_EXECUTION', return_code=process.returncode)
    output = (folder / state['stdout']).read_text(encoding='utf-8', errors='replace')
    error = (folder / state['stderr']).read_text(encoding='utf-8', errors='replace')
    return subprocess.CompletedProcess(command, process.returncode, output, error)


def wait_for_process(process: subprocess.Popen, timeout: float | None = None) -> int:
    """Observe cancellation while waiting, without imposing a new wall budget."""
    token = _current.get()
    if token is None:
        return process.wait(timeout=timeout)
    deadline = None if timeout is None else time.monotonic() + timeout
    while process.poll() is None:
        token.check()
        remaining = None if deadline is None else deadline - time.monotonic()
        if remaining is not None and remaining <= 0:
            raise subprocess.TimeoutExpired(process.args, timeout)
        try:
            return process.wait(timeout=0.1 if remaining is None else min(0.1, remaining))
        except subprocess.TimeoutExpired:
            pass
    return process.returncode


def stop_owned_process(process: subprocess.Popen, *, isolated_group: bool,
                       reap_timeout: float = 1.0) -> None:
    """Reap only this Popen child and its explicitly isolated POSIX group."""
    try:
        if isolated_group and os.name == "posix":
            if process.returncode is not None:
                # A wait interrupted by KeyboardInterrupt may have reaped the
                # leader already. Its released PID no longer proves ownership
                # of a group that now has the same number. Absence is safe;
                # presence remains UNKNOWN and must never authorize SIGKILL.
                try:
                    os.killpg(process.pid, 0)
                except ProcessLookupError:
                    pass
                else:
                    raise RuntimeError("Reaped leader cannot authorize termination of an existing group")
            else:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
        elif process.poll() is None:
            process.kill()
        # This is a stop-confirmation budget after termination was requested,
        # not a solver wall limit. Failure retains ownership and blocks writers.
        process.wait(timeout=reap_timeout)
    except BaseException as error:
        token = _current.get()
        if token is not None:
            token._retain_cleanup(process, isolated_group)
        raise ExecutionCleanupFailed(
            f"Owned process cleanup UNKNOWN for PID {process.pid}: {type(error).__name__}") from error
