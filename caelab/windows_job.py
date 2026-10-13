"""Windows handle-owned candidate process tree, using only stdlib/Win32.

The native command starts only after a stdlib gate is attached to this unnamed
Job. No process-name scans, persistent PID ownership or breakaway fallback.
"""
import ctypes
from ctypes import wintypes as W
import json
import os
from pathlib import Path
import subprocess
import sys
import time


class _BasicLimits(ctypes.Structure):
    _fields_ = [('PerProcessUserTimeLimit', ctypes.c_longlong),
        ('PerJobUserTimeLimit', ctypes.c_longlong), ('LimitFlags', W.DWORD),
        ('MinimumWorkingSetSize', ctypes.c_size_t), ('MaximumWorkingSetSize', ctypes.c_size_t),
        ('ActiveProcessLimit', W.DWORD), ('Affinity', ctypes.c_size_t),
        ('PriorityClass', W.DWORD), ('SchedulingClass', W.DWORD)]


class _IO(ctypes.Structure):
    _fields_ = [(name, ctypes.c_ulonglong) for name in (
        'ReadOperationCount', 'WriteOperationCount', 'OtherOperationCount',
        'ReadTransferCount', 'WriteTransferCount', 'OtherTransferCount')]


class _ExtendedLimits(ctypes.Structure):
    _fields_ = [('BasicLimitInformation', _BasicLimits), ('IoInfo', _IO),
        ('ProcessMemoryLimit', ctypes.c_size_t), ('JobMemoryLimit', ctypes.c_size_t),
        ('PeakProcessMemoryUsed', ctypes.c_size_t), ('PeakJobMemoryUsed', ctypes.c_size_t)]


class _Accounting(ctypes.Structure):
    _fields_ = [(name, ctypes.c_longlong) for name in (
        'TotalUserTime', 'TotalKernelTime', 'ThisPeriodTotalUserTime', 'ThisPeriodTotalKernelTime')]
    _fields_ += [(name, W.DWORD) for name in
        ('TotalPageFaultCount', 'TotalProcesses', 'ActiveProcesses', 'TotalTerminatedProcesses')]


class WindowsJob:
    def __init__(self):
        if os.name != 'nt':
            raise OSError('Windows Jobs require Windows')
        self.api = ctypes.WinDLL('kernel32', use_last_error=True)
        signatures = {
            'CreateJobObjectW': ([ctypes.c_void_p, W.LPCWSTR], W.HANDLE),
            'SetInformationJobObject': ([W.HANDLE, ctypes.c_int, ctypes.c_void_p, W.DWORD], W.BOOL),
            'AssignProcessToJobObject': ([W.HANDLE, W.HANDLE], W.BOOL),
            'QueryInformationJobObject': ([W.HANDLE, ctypes.c_int, ctypes.c_void_p, W.DWORD, ctypes.c_void_p], W.BOOL),
            'TerminateJobObject': ([W.HANDLE, W.UINT], W.BOOL),
            'CloseHandle': ([W.HANDLE], W.BOOL)}
        for name, (args, result) in signatures.items():
            function = getattr(self.api, name)
            function.argtypes, function.restype = args, result
        self.handle = self.api.CreateJobObjectW(None, None)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        info = _ExtendedLimits()
        info.BasicLimitInformation.LimitFlags = 0x2000  # KILL_ON_JOB_CLOSE; no breakaway.
        try:
            self._check(self.api.SetInformationJobObject(self.handle, 9, ctypes.byref(info), ctypes.sizeof(info)))
        except BaseException:
            self.close()
            raise

    @staticmethod
    def _check(result):
        if not result:
            raise ctypes.WinError(ctypes.get_last_error())

    def assign(self, process):
        # Popen's live Windows handle stays alive; an old PID is never reopened.
        self._check(self.api.AssignProcessToJobObject(self.handle, W.HANDLE(int(process._handle))))

    def active(self):
        info = _Accounting()
        self._check(self.api.QueryInformationJobObject(self.handle, 1, ctypes.byref(info), ctypes.sizeof(info), None))
        return int(info.ActiveProcesses)

    def terminate(self):
        self._check(self.api.TerminateJobObject(self.handle, 1))

    def close(self):
        if self.handle:
            self._check(self.api.CloseHandle(self.handle))
            self.handle = None


def spawn_gated(command, *, cwd, stdout, stderr, env, label):
    """Return a Popen still blocked at a one-byte gate and its ready-file path."""
    interpreter = Path(getattr(sys, '_base_executable', sys.executable)).resolve(strict=True)
    ready = Path(cwd) / (label + '.gate-ready.json')
    if ready.exists():
        raise ValueError('Candidate process gate requires a fresh receipt')
    job = WindowsJob()
    try:
        process = subprocess.Popen([str(interpreter), '-I', '-S', str(Path(__file__).resolve()),
            '--gate', str(ready), json.dumps([str(item) for item in command])],
            cwd=cwd, stdout=stdout, stderr=stderr, stdin=subprocess.PIPE, env=env,
            close_fds=True)
    except BaseException:
        job.close()
        raise
    process._caelab_windows_job = job
    return process, ready


def release_gate(process, ready, check_cancelled):
    """Verify actual Python identity before assigning and releasing the gate."""
    deadline = time.monotonic() + 10.0  # stdlib gate startup, not native/solver wall time.
    while not ready.is_file():
        check_cancelled()
        if process.poll() is not None:
            raise RuntimeError('Candidate process gate exited before readiness')
        if time.monotonic() >= deadline:
            raise RuntimeError('Candidate process gate did not become ready')
        time.sleep(.02)
    value = json.loads(ready.read_text(encoding='utf-8'))
    if value != {'pid': process.pid}:
        raise RuntimeError('Configured Python launched a different gate process; native launch refused')
    process._caelab_windows_job.assign(process)
    process.stdin.write(b'R')
    process.stdin.flush()
    process.stdin.close()


def _gate_main():
    if len(sys.argv) != 4 or sys.argv[1] != '--gate':
        return 2
    path = Path(sys.argv[2])
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps({'pid': os.getpid()}), encoding='utf-8')
    temporary.replace(path)
    if sys.stdin.buffer.read(1) != b'R':
        return 3
    command = json.loads(sys.argv[3])
    if not isinstance(command, list) or not command or any(not isinstance(v, str) for v in command):
        return 2
    # Descendants inherit the already assigned Job. No control pipe is inherited.
    return subprocess.call(command, stdin=subprocess.DEVNULL, close_fds=True)


if __name__ == '__main__':
    raise SystemExit(_gate_main())
