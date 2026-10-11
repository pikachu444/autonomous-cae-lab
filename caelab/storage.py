"""Small append-only filesystem store for versioned experiments and evidence."""

from datetime import datetime, timezone
import hashlib
import json
import mimetypes
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time
from typing import Any


SAFE_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,79}$")
IO_RETRY_SECONDS = 2.0


def _retry_io(operation):
    """Retry only a transient Windows access/sharing/lock refusal.

    The callback must perform file I/O only, never a document edit or solver
    submission. Permission errors remain explicit after this bounded interval.
    """
    deadline, delay = time.monotonic() + IO_RETRY_SECONDS, .005
    while True:
        try:
            return operation()
        except OSError as error:
            remaining = deadline - time.monotonic()
            if getattr(error, 'winerror', None) not in {5, 32, 33} or remaining <= 0:
                raise
            time.sleep(min(delay, remaining))
            delay = min(delay * 2, .1)


def _read_utf8(path):
    if os.name != 'nt':
        return path.read_text(encoding='utf-8')
    # Microsoft's FILE_SHARE_DELETE also permits rename. Our normal readers
    # must not prevent atomic publication of the next JSON snapshot.
    # https://learn.microsoft.com/windows/win32/api/fileapi/nf-fileapi-createfilew
    import ctypes
    from ctypes import wintypes
    import msvcrt
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    create = kernel.CreateFileW
    create.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
                       wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    create.restype = wintypes.HANDLE
    close = kernel.CloseHandle
    close.argtypes, close.restype = [wintypes.HANDLE], wintypes.BOOL
    handle = create(str(path), 0x80000000, 0x1 | 0x2 | 0x4, None, 3, 0x80, None)
    if handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        descriptor = msvcrt.open_osfhandle(handle, os.O_RDONLY | os.O_BINARY)
    except BaseException:
        close(handle)
        raise
    with os.fdopen(descriptor, 'r', encoding='utf-8') as stream:
        return stream.read()


def _publish_json(temporary, path):
    """Publish these exact prepared bytes; failed originals are never removed."""
    try:
        _retry_io(lambda: temporary.replace(path))
    except OSError as error:
        # Preserve the concrete prepared file for recovery, not a new edit/run.
        error.temporary_path, error.target_path = str(temporary), str(path)
        error.add_note('Prepared JSON remains at ' + str(temporary) + '; publication target: ' + str(path))
        raise


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def save_json(path: Path, value: Any) -> None:
    path = Path(path)
    payload = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                     prefix=".caelab-", delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    _publish_json(temporary, path)


def load_json(path: Path) -> Any:
    # Retry the read, not JSON parsing. Corrupt/malformed files remain failures.
    return json.loads(_retry_io(lambda: _read_utf8(Path(path))))


def artifact_manifest(folder: Path, *, revision: str) -> list[dict[str, Any]]:
    records = []
    for path in sorted(p for p in folder.rglob("*") if p.is_file()):
        rel = path.relative_to(folder).as_posix()
        if rel in ("result.json", "thread.json"):
            continue
        records.append({"path": rel, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                        "size_bytes": path.stat().st_size,
                        "mime_type": mimetypes.guess_type(path.name)[0] or "application/octet-stream",
                        "revision": revision})
    return records


def check_artifacts(folder: Path, artifacts: list[dict[str, Any]]) -> list[str]:
    corrupt = []
    for record in artifacts:
        path = folder / record["path"]
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != record["sha256"]:
            corrupt.append(record["path"])
    return corrupt


def check_id(identifier: str) -> str:
    if not isinstance(identifier, str) or not SAFE_ID.fullmatch(identifier):
        raise ValueError("Invalid study or experiment ID")
    return identifier


def core_source_hash(root: Path) -> str:
    """Re-read every Core/schema byte without querying unrelated Git state."""
    files = [*sorted((root / "caelab").rglob("*.py")), *sorted((root / "schemas").glob("*.json"))]
    digest = hashlib.sha256()
    for path in files:
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def source_identity(root: Path) -> dict[str, Any]:
    try:
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root,
                                         text=True, stderr=subprocess.DEVNULL).strip()
        dirty = bool(subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=normal"],
                                             cwd=root, text=True, stderr=subprocess.DEVNULL).strip())
    except (OSError, subprocess.CalledProcessError):
        commit, dirty = "unavailable", None
    return {"core_commit": commit, "core_dirty": dirty, "core_source_sha256": core_source_hash(root)}
