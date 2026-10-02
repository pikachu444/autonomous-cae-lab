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

    setting = os.environ.get("CAELAB_STORE")
    store = Path(setting if setting is not None else
                 Path(__file__).resolve().parents[1] / "runs").resolve()
    if _resident is None:
        service = LabService(store)
        _bound_store, _bound_setting, _resident = store, setting, service
    elif setting != _bound_setting or store != _bound_store:
        raise ServiceError(409, "CAELAB_STORE changed; a new resident is required to preserve existing jobs")
    return _resident


def _control_metadata() -> dict:
    return {"scope": "PROCESS_RESIDENT", "cancel_supported": True,
            "cancel_mode": "COOPERATIVE_CHECKPOINTS", "immediate_stop_guaranteed": False,
            "completion_is_numerical_pass": False}


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
        return _resident.shutdown(timeout=timeout)


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
