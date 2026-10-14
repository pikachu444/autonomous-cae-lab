"""Windows process ownership checks; all children are harmless Python probes."""
import json
import os
from pathlib import Path
import sys
import time

import pytest

import scripts.native_check as native_check
from scripts.native_check import run_native_check


pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows Job Object launcher")


def _wait_for(path: Path, timeout=5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists():
            return
        time.sleep(0.02)
    raise AssertionError(f"process did not create {path}")


def _is_running(pid):
    import ctypes
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel.GetExitCodeProcess.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    process = kernel.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not process:
        return False
    try:
        code = wintypes.DWORD()
        return bool(kernel.GetExitCodeProcess(process, ctypes.byref(code)) and code.value == 259)
    finally:
        kernel.CloseHandle(process)


def _child_probe(pid_path, heartbeat_path):
    source = (
        "import os,sys,time; "
        "open(sys.argv[1],'w').write(str(os.getpid())); "
        "f=open(sys.argv[2],'a'); "
        "exec('while True:\\n f.write(\"x\\\\n\"); f.flush(); time.sleep(.03)')"
    )
    return [sys.executable, "-c", source, str(pid_path), str(heartbeat_path)]


def test_normal_and_failure_exits_preserve_logs_receipts_and_kill_orphan_children(tmp_path):
    for expected in (0, 9):
        case = tmp_path / f"exit-{expected}"
        pid_file, heartbeat = case / "child.pid", case / "heartbeat.txt"
        root = "import subprocess,sys,time; subprocess.Popen(sys.argv[1:]); time.sleep(.3); print('root finished'); sys.exit(int(sys.argv[-1]))"
        result = run_native_check([sys.executable, "-c", root, *_child_probe(pid_file, heartbeat), str(expected)],
                                  case, 8)
        _wait_for(pid_file)
        child_pid = int(pid_file.read_text())
        assert result.exit_code == expected and not result.timed_out
        assert "root finished" in Path(result.stdout_log).read_text()
        assert json.loads(Path(result.receipt).read_text())["pid"] == result.pid
        time.sleep(.15)
        assert not _is_running(child_pid)
        stable_size = heartbeat.stat().st_size
        time.sleep(.15)
        assert heartbeat.stat().st_size == stable_size


def test_timeout_kills_root_and_descendants_and_retains_partial_logs(tmp_path):
    pid_file, heartbeat = tmp_path / "child.pid", tmp_path / "heartbeat.txt"
    root = "import subprocess,sys,time; subprocess.Popen(sys.argv[1:]); print('before timeout',flush=True); time.sleep(60)"
    result = run_native_check([sys.executable, "-u", "-c", root, *_child_probe(pid_file, heartbeat)],
                              tmp_path, .5)
    _wait_for(pid_file)
    child_pid = int(pid_file.read_text())
    assert result.timed_out and result.exit_code == 124
    assert "before timeout" in Path(result.stdout_log).read_text()
    assert json.loads(Path(result.receipt).read_text())["timed_out"] is True
    assert not _is_running(result.pid)
    assert not _is_running(child_pid)


def test_nonempty_output_directory_is_refused_without_changing_prior_receipt_or_logs(tmp_path):
    output = tmp_path / "same-run"
    result = run_native_check([sys.executable, "-c", "print('first run')"], output, 5)
    before = {path.name: path.read_bytes() for path in output.iterdir()}
    with pytest.raises(FileExistsError, match="not empty"):
        run_native_check([sys.executable, "-c", "print('must not run')"], output, 5)
    assert {path.name: path.read_bytes() for path in output.iterdir()} == before
    assert "first run" in Path(result.stdout_log).read_text()


def test_assign_failure_records_error_and_terminates_suspended_root(tmp_path, monkeypatch):
    monkeypatch.setattr(native_check.kernel32, "AssignProcessToJobObject", lambda *_args: 0)
    output = tmp_path / "assign-failure"
    with pytest.raises(OSError, match="AssignProcessToJobObject"):
        run_native_check([sys.executable, "-c", "raise SystemExit(0)"], output, 5)
    receipt = json.loads((output / "native-check.json").read_text())
    assert receipt["pid"] > 0 and receipt["cleanup"] == "unassigned_root_terminated"
    assert "AssignProcessToJobObject" in receipt["error"]
    assert not _is_running(receipt["pid"])


def test_wait_failure_records_error_and_terminates_root_and_child(tmp_path, monkeypatch):
    original_wait = native_check.kernel32.WaitForSingleObject
    first_wait = True
    pid_file, heartbeat = tmp_path / "child.pid", tmp_path / "heartbeat.txt"

    def fail_first_wait(handle, timeout):
        nonlocal first_wait
        if first_wait:
            first_wait = False
            _wait_for(pid_file)
            return 0xFFFFFFFF  # WAIT_FAILED
        return original_wait(handle, timeout)

    monkeypatch.setattr(native_check.kernel32, "WaitForSingleObject", fail_first_wait)
    root = ("import os,subprocess,sys,time; subprocess.Popen(sys.argv[1:]); "
            "deadline=time.monotonic()+5; "
            "exec('while not os.path.exists(sys.argv[-2]) and time.monotonic()<deadline: time.sleep(.01)'); "
            "time.sleep(60)")
    with pytest.raises(OSError, match="WaitForSingleObject"):
        run_native_check([sys.executable, "-c", root, *_child_probe(pid_file, heartbeat)], tmp_path, 5)
    _wait_for(pid_file)
    child_pid = int(pid_file.read_text())
    receipt = json.loads((tmp_path / "native-check.json").read_text())
    assert receipt["pid"] > 0 and "WaitForSingleObject" in receipt["error"]
    assert receipt["cleanup"] == "job_empty"
    assert not _is_running(receipt["pid"])
    assert not _is_running(child_pid)
