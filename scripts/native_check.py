"""Run one native verification command with invocation-scoped Windows cleanup.

The root process is created suspended, assigned to a private Windows Job Object,
and only then resumed. Closing that job terminates only processes created inside
this invocation. Standard output, standard error, and a JSON receipt are retained.
"""
from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import time


if os.name == "nt":
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    class STARTUPINFOW(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("lpReserved", wintypes.LPWSTR),
                    ("lpDesktop", wintypes.LPWSTR), ("lpTitle", wintypes.LPWSTR),
                    ("dwX", wintypes.DWORD), ("dwY", wintypes.DWORD),
                    ("dwXSize", wintypes.DWORD), ("dwYSize", wintypes.DWORD),
                    ("dwXCountChars", wintypes.DWORD), ("dwYCountChars", wintypes.DWORD),
                    ("dwFillAttribute", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                    ("wShowWindow", wintypes.WORD), ("cbReserved2", wintypes.WORD),
                    ("lpReserved2", ctypes.POINTER(ctypes.c_ubyte)),
                    ("hStdInput", wintypes.HANDLE), ("hStdOutput", wintypes.HANDLE),
                    ("hStdError", wintypes.HANDLE)]

    class PROCESS_INFORMATION(ctypes.Structure):
        _fields_ = [("hProcess", wintypes.HANDLE), ("hThread", wintypes.HANDLE),
                    ("dwProcessId", wintypes.DWORD), ("dwThreadId", wintypes.DWORD)]

    class IO_COUNTERS(ctypes.Structure):
        _fields_ = [(name, ctypes.c_ulonglong) for name in
                    ("ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
                     "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]

    class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [("PerProcessUserTimeLimit", ctypes.c_longlong),
                    ("PerJobUserTimeLimit", ctypes.c_longlong), ("LimitFlags", wintypes.DWORD),
                    ("MinimumWorkingSetSize", ctypes.c_size_t),
                    ("MaximumWorkingSetSize", ctypes.c_size_t),
                    ("ActiveProcessLimit", wintypes.DWORD), ("Affinity", ctypes.c_size_t),
                    ("PriorityClass", wintypes.DWORD), ("SchedulingClass", wintypes.DWORD)]

    class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
                    ("IoInfo", IO_COUNTERS), ("ProcessMemoryLimit", ctypes.c_size_t),
                    ("JobMemoryLimit", ctypes.c_size_t), ("PeakProcessMemoryUsed", ctypes.c_size_t),
                    ("PeakJobMemoryUsed", ctypes.c_size_t)]

    class JOBOBJECT_BASIC_ACCOUNTING_INFORMATION(ctypes.Structure):
        _fields_ = [("TotalUserTime", ctypes.c_longlong), ("TotalKernelTime", ctypes.c_longlong),
                    ("ThisPeriodTotalUserTime", ctypes.c_longlong),
                    ("ThisPeriodTotalKernelTime", ctypes.c_longlong),
                    ("TotalPageFaultCount", wintypes.DWORD), ("TotalProcesses", wintypes.DWORD),
                    ("ActiveProcesses", wintypes.DWORD), ("TotalTerminatedProcesses", wintypes.DWORD)]

    kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    kernel32.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int,
                                                 ctypes.c_void_p, wintypes.DWORD]
    kernel32.SetInformationJobObject.restype = wintypes.BOOL
    kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
    kernel32.ResumeThread.argtypes = [wintypes.HANDLE]
    kernel32.ResumeThread.restype = wintypes.DWORD
    kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel32.WaitForSingleObject.restype = wintypes.DWORD
    kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel32.GetExitCodeProcess.restype = wintypes.BOOL
    kernel32.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
    kernel32.TerminateJobObject.restype = wintypes.BOOL
    kernel32.QueryInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int,
                                                    ctypes.c_void_p, wintypes.DWORD,
                                                    ctypes.POINTER(wintypes.DWORD)]
    kernel32.QueryInformationJobObject.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    kernel32.SetHandleInformation.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD]
    kernel32.SetHandleInformation.restype = wintypes.BOOL
    kernel32.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
    kernel32.TerminateProcess.restype = wintypes.BOOL
    kernel32.CreateProcessW.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, ctypes.c_void_p,
                                        ctypes.c_void_p, wintypes.BOOL, wintypes.DWORD,
                                        ctypes.c_void_p, wintypes.LPCWSTR,
                                        ctypes.POINTER(STARTUPINFOW), ctypes.POINTER(PROCESS_INFORMATION)]
    kernel32.CreateProcessW.restype = wintypes.BOOL


@dataclass
class NativeCheckResult:
    command: list[str]
    cwd: str
    pid: int
    started_at: str
    finished_at: str
    timeout_seconds: float
    timed_out: bool
    exit_code: int
    stdout_log: str
    stderr_log: str
    receipt: str
    cleanup: str
    error: str | None = None
    cleanup_error: str | None = None


def _winerror(operation: str) -> OSError:
    return ctypes.WinError(ctypes.get_last_error(), operation)


def _job_active_count(job) -> int:
    info = JOBOBJECT_BASIC_ACCOUNTING_INFORMATION()
    if not kernel32.QueryInformationJobObject(job, 1, ctypes.byref(info), ctypes.sizeof(info), None):
        raise _winerror("QueryInformationJobObject")
    return int(info.ActiveProcesses)


def run_native_check(command, output_dir, timeout_seconds: float, cwd=None) -> NativeCheckResult:
    """Run a command with a hard timeout and invocation-scoped descendant cleanup.

    Logs and `native-check.json` are written after a process is created, including
    when setup or execution fails. In that case the receipt records the error and
    the same error is re-raised. A timeout is reported as exit code 124; ordinary
    process exit codes pass through. Existing nonempty output directories are refused.
    """
    if os.name != "nt":
        raise OSError("native_check requires Windows Job Objects")
    command = [os.fspath(part) for part in command]
    if not command or timeout_seconds <= 0:
        raise ValueError("command and a positive timeout are required")
    out_dir = Path(output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    if any(out_dir.iterdir()):
        raise FileExistsError(f"native check output directory is not empty: {out_dir}")
    stdout_path, stderr_path = out_dir / "stdout.log", out_dir / "stderr.log"
    receipt_path = out_dir / "native-check.json"
    workdir = str(Path(cwd or os.getcwd()).resolve())
    job = kernel32.CreateJobObjectW(None, None)
    if not job:
        raise _winerror("CreateJobObjectW")
    process = thread = None
    stdin = None
    assigned = False
    root_pid = 0
    timed_out = False
    exit_code = 1
    cleanup = "job_closed"
    run_error = cleanup_error = None
    run_error_tb = None
    started = datetime.now(timezone.utc).isoformat()
    try:
        limits = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        limits.BasicLimitInformation.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not kernel32.SetInformationJobObject(job, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            raise _winerror("SetInformationJobObject")
        with open(stdout_path, "wb") as stdout, open(stderr_path, "wb") as stderr:
            stdin = open(os.devnull, "rb")
            for stream in (stdout, stderr, stdin):
                handle = wintypes.HANDLE(msvcrt_handle(stream))
                if not kernel32.SetHandleInformation(handle, 1, 1):
                    raise _winerror("SetHandleInformation")
            startup = STARTUPINFOW()
            startup.cb = ctypes.sizeof(startup)
            startup.dwFlags = 0x100  # STARTF_USESTDHANDLES
            startup.hStdOutput = msvcrt_handle(stdout)
            startup.hStdError = msvcrt_handle(stderr)
            startup.hStdInput = msvcrt_handle(stdin)
            info = PROCESS_INFORMATION()
            mutable_command = ctypes.create_unicode_buffer(subprocess.list2cmdline(command))
            flags = 0x4 | 0x8000000  # CREATE_SUSPENDED | CREATE_NO_WINDOW
            if not kernel32.CreateProcessW(command[0], mutable_command, None, None, True,
                                           flags, None, workdir, ctypes.byref(startup), ctypes.byref(info)):
                raise _winerror("CreateProcessW")
            process, thread, root_pid = info.hProcess, info.hThread, int(info.dwProcessId)
            if not kernel32.AssignProcessToJobObject(job, process):
                raise _winerror("AssignProcessToJobObject")
            assigned = True
            if kernel32.ResumeThread(thread) == 0xFFFFFFFF:
                raise _winerror("ResumeThread")
            kernel32.CloseHandle(thread)
            thread = None
            wait_ms = max(1, int(timeout_seconds * 1000))
            waited = kernel32.WaitForSingleObject(process, wait_ms)
            if waited == 0x102:  # WAIT_TIMEOUT
                timed_out = True
                if not kernel32.TerminateJobObject(job, 124):
                    raise _winerror("TerminateJobObject(timeout)")
                if kernel32.WaitForSingleObject(process, 10000) != 0:
                    raise RuntimeError("timed-out native root did not exit after job termination")
                exit_code = 124
            elif waited != 0:
                raise _winerror("WaitForSingleObject")
            else:
                code = wintypes.DWORD()
                if not kernel32.GetExitCodeProcess(process, ctypes.byref(code)):
                    raise _winerror("GetExitCodeProcess")
                exit_code = int(code.value)
        # A native verifier can leave helper processes behind after the root exits.
        # Terminate only members of this private job, then confirm the job is empty.
        if _job_active_count(job):
            if not kernel32.TerminateJobObject(job, 125):
                raise _winerror("TerminateJobObject(child cleanup)")
            deadline = time.monotonic() + 10
            while _job_active_count(job) and time.monotonic() < deadline:
                time.sleep(0.05)
            cleanup = "job_empty" if not _job_active_count(job) else "kill_on_close_unverified"
        else:
            cleanup = "job_empty"
    except BaseException as exc:
        run_error = exc
        run_error_tb = exc.__traceback__
    finally:
        if process and not assigned:
            if not kernel32.TerminateProcess(process, 125):
                cleanup_error = f"TerminateProcess(unassigned root): {_winerror('TerminateProcess')}"
            elif kernel32.WaitForSingleObject(process, 10000) != 0:
                cleanup_error = "unassigned suspended root did not exit after termination"
            else:
                cleanup = "unassigned_root_terminated"
        elif process and assigned and cleanup != "job_empty":
            try:
                if _job_active_count(job):
                    if not kernel32.TerminateJobObject(job, 125):
                        raise _winerror("TerminateJobObject(final cleanup)")
                    deadline = time.monotonic() + 10
                    while _job_active_count(job) and time.monotonic() < deadline:
                        time.sleep(0.05)
                cleanup = "job_empty" if not _job_active_count(job) else "kill_on_close_unverified"
            except BaseException as exc:
                cleanup_error = str(exc)
                cleanup = "kill_on_close_unverified"
        if thread:
            kernel32.CloseHandle(thread)
        if process:
            kernel32.CloseHandle(process)
        if stdin:
            stdin.close()
        kernel32.CloseHandle(job)  # KILL_ON_JOB_CLOSE is the bounded final cleanup.
    if cleanup_error and run_error is None:
        run_error = RuntimeError(f"native process cleanup failed: {cleanup_error}")
        run_error_tb = run_error.__traceback__
    result = NativeCheckResult(command, workdir, root_pid, started,
                               datetime.now(timezone.utc).isoformat(), float(timeout_seconds),
                               timed_out, exit_code, str(stdout_path), str(stderr_path),
                               str(receipt_path), cleanup,
                               str(run_error) if run_error else None, cleanup_error)
    if root_pid:
        receipt_path.write_text(json.dumps(asdict(result), indent=2) + "\n", encoding="utf-8")
    if run_error:
        raise run_error.with_traceback(run_error_tb)
    return result


def msvcrt_handle(stream):
    import msvcrt
    return msvcrt.get_osfhandle(stream.fileno())


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Run a native verification with exact process cleanup")
    parser.add_argument("--timeout", type=float, required=True, help="wall timeout in seconds")
    parser.add_argument("--output-dir", required=True, help="directory for logs and receipt")
    parser.add_argument("--cwd", help="working directory (defaults to current directory)")
    parser.add_argument("command", nargs=argparse.REMAINDER, help="native executable and arguments; prefix with --")
    args = parser.parse_args(argv)
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    try:
        result = run_native_check(command, args.output_dir, args.timeout, args.cwd)
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(json.dumps(asdict(result), indent=2))
    return result.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
