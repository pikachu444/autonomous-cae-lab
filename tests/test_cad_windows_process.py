"""Real Windows stdlib process-tree checks. No FreeCAD, Gmsh or solver runs."""
import ctypes
from ctypes import wintypes as W
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

import pytest

from caelab.execution_control import CancellationToken, cancellation_scope, run_owned_command, ExecutionCancelled

pytestmark = pytest.mark.skipif(os.name != 'nt', reason='Windows Job Object execution check')


def wait_file(path, errors, timeout=10):
    deadline = time.monotonic() + timeout
    while not path.exists():
        if errors:
            raise errors[0]
        if time.monotonic() >= deadline:
            raise AssertionError('Owned child did not reach its explicit readiness point')
        time.sleep(.02)


def test_owned_windows_cancel_stops_live_descendants_and_leaves_unrelated_process(tmp_path):
    base = str(Path(getattr(sys, '_base_executable', sys.executable)).resolve())
    folder = tmp_path / '후보 with spaces'; folder.mkdir()
    ready = folder / 'native-ready.json'
    child = folder / 'native_double.py'
    child.write_text(
        "import json,os,subprocess,sys,time\n"
        "from pathlib import Path\n"
        "p=subprocess.Popen([sys.executable,'-I','-S','-c','import time;time.sleep(60)'])\n"
        "Path(sys.argv[1]).write_text(json.dumps([os.getpid(),p.pid]),encoding='utf-8')\n"
        "p.wait()\n", encoding='utf-8')
    token, errors = CancellationToken(), []
    def execute():
        try:
            with cancellation_scope(token):
                run_owned_command([base, '-I', '-S', str(child), str(ready)],
                                  folder, 'owned', owned_tree=True)
        except BaseException as error:
            errors.append(error)
    unrelated = subprocess.Popen([base, '-I', '-S', '-c', 'import time;time.sleep(60)'])
    handles = []
    api = ctypes.WinDLL('kernel32', use_last_error=True)
    api.OpenProcess.argtypes = [W.DWORD, W.BOOL, W.DWORD]; api.OpenProcess.restype = W.HANDLE
    api.WaitForSingleObject.argtypes = [W.HANDLE, W.DWORD]; api.WaitForSingleObject.restype = W.DWORD
    api.CloseHandle.argtypes = [W.HANDLE]; api.CloseHandle.restype = W.BOOL
    thread = threading.Thread(target=execute)
    thread.start()
    try:
        wait_file(ready, errors)
        # Hold actual live handles before cancellation; never infer termination
        # from a reused PID or terminate any process by image name.
        for pid in json.loads(ready.read_text(encoding='utf-8')):
            handle = api.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE, read/wait only
            assert handle
            handles.append(handle)
            assert api.WaitForSingleObject(handle, 0) == 258
        token.request(); thread.join(10)
        assert not thread.is_alive()
        assert len(errors) == 1 and isinstance(errors[0], ExecutionCancelled)
        assert not token.cleanup_pending and token.observed
        assert all(api.WaitForSingleObject(handle, 0) == 0 for handle in handles)
        assert unrelated.poll() is None
        receipt = json.loads((folder / 'owned.execution.json').read_text(encoding='utf-8'))
        assert receipt['status'] == 'CANCELLED' and receipt['tree_ownership'] == 'WINDOWS_JOB'
    finally:
        token.request(); thread.join(10)
        token.retry_cleanup(2)
        for handle in handles:
            api.CloseHandle(handle)
        unrelated.kill(); unrelated.wait(timeout=5)


def test_normal_exit_waits_for_descendant_before_sealing(tmp_path):
    base = str(Path(getattr(sys, '_base_executable', sys.executable)).resolve())
    marker = tmp_path / 'finished.txt'
    descendant = "import time;from pathlib import Path;time.sleep(.3);Path(" + repr(str(marker)) + ").write_text('done')"
    command = "import subprocess,sys;subprocess.Popen([sys.executable,'-I','-S','-c'," + repr(descendant) + "])"
    result = run_owned_command([base, '-I', '-S', '-c', command], tmp_path, 'normal', owned_tree=True)
    assert result.returncode == 0 and marker.read_text(encoding='utf-8') == 'done'


def test_job_assignment_failure_never_releases_native_command(tmp_path, monkeypatch):
    from caelab.windows_job import WindowsJob
    monkeypatch.setattr(WindowsJob, 'assign',
                        lambda *args: (_ for _ in ()).throw(OSError('explicit assignment refusal')))
    marker = tmp_path / 'must-not-exist'
    base = str(Path(getattr(sys, '_base_executable', sys.executable)).resolve())
    code = "from pathlib import Path;Path(" + repr(str(marker)) + ").write_text('wrong')"
    with pytest.raises(OSError, match='assignment refusal'):
        run_owned_command([base, '-I', '-S', '-c', code], tmp_path, 'denied', owned_tree=True)
    assert not marker.exists()
