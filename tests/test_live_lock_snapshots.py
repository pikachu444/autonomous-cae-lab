"""Snapshot exclusions are exact live handles, never a lock-file wildcard."""
import hashlib
from pathlib import Path

import pytest


@pytest.fixture(params=["lab-server", "retained-locations"])
def snapshot(request):
    if request.param == "lab-server":
        from test_lab_server import file_hashes
        return file_hashes
    from test_retained_location_pages import fingerprints
    return fingerprints


@pytest.fixture
def stored_files(tmp_path):
    files = {"controller.lock": b"live controller handle",
             "retained.lock": b"retained artifact named lock",
             "history/controller.lock": b"different exact path",
             "result.json": b'{"status":"SUCCEEDED"}'}
    for relative, data in files.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return tmp_path, {relative: hashlib.sha256(data).hexdigest() for relative, data in files.items()}


def test_snapshot_defaults_to_every_file_and_exact_exclusion_keeps_retained_locks(snapshot, stored_files):
    root, expected = stored_files
    assert snapshot(root) == expected
    expected.pop("controller.lock")
    # FileLock.lock_file is a string; callers pass the actual manager's value.
    assert snapshot(root, live_lock=str(root / "controller.lock")) == expected
    assert "retained.lock" in expected and "history/controller.lock" in expected


def test_snapshot_exclusion_does_not_read_live_handle_or_ignore_other_errors(snapshot, stored_files, monkeypatch):
    root, expected = stored_files
    live_lock, unreadable = root / "controller.lock", root / "retained.lock"
    original = Path.read_bytes
    reads = []
    denied = {live_lock}

    def read_bytes(path):
        reads.append(path)
        if path in denied:
            raise PermissionError(13, "TEST_ONLY exclusive/read-denied handle", str(path))
        return original(path)

    monkeypatch.setattr(Path, "read_bytes", read_bytes)
    with pytest.raises(PermissionError) as error:
        snapshot(root)
    assert error.value.filename == str(live_lock)
    reads.clear()
    expected.pop("controller.lock")
    assert snapshot(root, live_lock=str(live_lock)) == expected
    assert live_lock not in reads and unreadable in reads
    denied.add(unreadable)
    with pytest.raises(PermissionError) as error:
        snapshot(root, live_lock=str(live_lock))
    assert error.value.filename == str(unreadable)
