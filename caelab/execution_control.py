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
