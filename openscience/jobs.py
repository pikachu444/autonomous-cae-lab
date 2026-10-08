"""Resident job access through the existing Lab application service.

Importing this module creates no Lab or store. All helpers share one lazy
service and one writer lock; changing CAELAB_STORE requires a new resident.
Job completion describes execution, never a numerical or engineering verdict.
"""

from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path
import threading
from typing import TYPE_CHECKING, Iterator

if TYPE_CHECKING:
    from apps.lab.service import LabService


_lock = threading.RLock()
_resident: LabService | None = None
_bound_store: Path | None = None
_bound_setting: str | None = None
_synchronous_depth = 0


def _service() -> LabService:
    """Get the singleton while the caller holds the resident lock."""
    global _resident, _bound_store, _bound_setting
    from apps.lab.service import LabService, ServiceError

    if os.environ.get('CAELAB_SERVICE_URL'):
        raise ServiceError(409, 'Shared mode uses the workbench service; a second resident is forbidden')

    setting = os.environ.get("CAELAB_STORE")
    store = Path(setting if setting is not None else
                 Path(__file__).resolve().parents[1] / "runs").resolve()
    if _resident is None:
        from filelock import FileLock, Timeout
        control = store / 'workbench'
        control.mkdir(parents=True, exist_ok=True)
        owner = FileLock(control / 'controller.lock', timeout=0)
        try:
            owner.acquire()
        except Timeout as error:
            raise ServiceError(409, 'Workspace already has a controller; set CAELAB_SERVICE_URL') from error
        try:
            service = LabService(store)
            service._standalone_owner = owner
        except BaseException:
            owner.release()
            raise
        _bound_store, _bound_setting, _resident = store, setting, service
    elif setting != _bound_setting or store != _bound_store:
        raise ServiceError(409, "CAELAB_STORE changed; a new resident is required to preserve existing jobs")
    return _resident


def _control_metadata() -> dict:
    return {"scope": "PROCESS_RESIDENT", "cancel_supported": True,
            "cancel_mode": "COOPERATIVE_CHECKPOINTS", "immediate_stop_guaranteed": False,
            "completion_is_numerical_pass": False}


def execution_status() -> dict:
    """Observe the existing resident writer without creating a Lab or store.

    A busy synchronous lock cannot be mistaken for idle after an AI session
    abort. This is process-resident evidence, not an inventory of OS processes.
    """
    store = str(Path(os.environ.get("CAELAB_STORE", str(Path(__file__).resolve().parents[1] / "runs"))).resolve())
    base = {"scope": "PROCESS_RESIDENT", "store_root": store}
    if not _lock.acquire(blocking=False):
        return {**base, "state": "BUSY", "idle_confirmed": False}
    try:
        if _synchronous_depth:
            return {**base, "state": "BUSY", "idle_confirmed": False}
        if _resident is None:
            return {**base, "state": "IDLE", "idle_confirmed": True}
        if os.environ.get("CAELAB_STORE") != _bound_setting:
            return {**base, "state": "UNKNOWN", "idle_confirmed": False}
        return {**base, **_resident.execution_status()}
    finally:
        _lock.release()


def start(operation: str, arguments: dict) -> dict:
    """Submit one allowlisted operation; preserve the service's admission gates."""
    from apps.lab.service import ServiceError

    with _lock:
        service = _service()
        if _synchronous_depth:
            raise ServiceError(409, "Synchronous writing is active; asynchronous submission is blocked")
        job = service.submit(operation, arguments)
        return {**job, "job_control": _control_metadata()}


def inspect(job_id: str) -> dict:
    """Read a resident job without rerunning its Core operation."""
    with _lock:
        job = _service().job(job_id)
        return {**job, "job_control": _control_metadata()}


def list_jobs() -> dict:
    """List resident jobs through the existing public overview API."""
    with _lock:
        return {"jobs": _service().overview()["jobs"],
                "job_control": _control_metadata()}


def cancel(job_id: str) -> dict:
    """Request cancellation of this resident's job; keep reading until terminal."""
    with _lock:
        return {**_service().cancel(job_id), "job_control": _control_metadata()}


def shutdown(timeout: float = 5.0) -> dict:
    """Close admission and request owned jobs to stop; report any pending work."""
    with _lock:
        if _resident is None:
            return {"accepting_jobs": False, "pending": [], "joined": True}
        result = _resident.shutdown(timeout=timeout)
        if result['joined'] and not result['pending']:
            _resident._standalone_owner.release()
        return result


@contextmanager
def synchronous_writer() -> Iterator[None]:
    """Prevent synchronous MCP writes from overlapping resident async jobs."""
    global _synchronous_depth
    from apps.lab.service import ServiceError

    with _lock:
        overview = _service().overview()
        if not overview.get("accepting_jobs", True):
            raise ServiceError(503, "The resident is shutting down; synchronous writing is blocked")
        if any(job["status"] in {"RUNNING", "CANCEL_REQUESTED", "CLEANUP_PENDING"}
               for job in overview["jobs"]):
            raise ServiceError(409, "An asynchronous job is running; synchronous writing is blocked")
        _synchronous_depth += 1
        try:
            yield
        finally:
            _synchronous_depth -= 1
