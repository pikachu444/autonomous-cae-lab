"""Versioned C ABI for our SDK-built ParaView plugin, not Qt/C++ memory access.

Only this plugin's exported C functions are called. No PySide/PyQt, QObject
pointers, offsets, mangled names, vtables, or other-process injection are used.
"""
from __future__ import annotations

import ctypes as C
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
from typing import Any

ABI = 1
ALLOW, BLOCK, UNKNOWN = 1, 0, -1
BEGIN, VALIDATE, ABORTED, CLOSED, DESTROYED, SHUTDOWN = range(1, 7)
OK, NOT_READY, WRONG_THREAD, WRONG_OWNER, BUSY, BAD_ABI, BAD_ARGUMENT = range(7)
CALLBACK = C.CFUNCTYPE(C.c_int32, C.c_uint64, C.c_uint64, C.c_uint64, C.c_uint32)


class Status(C.Structure):
    _fields_ = [
        ("abi", C.c_uint32), ("size", C.c_uint32),
        ("pid", C.c_uint64), ("window", C.c_uint64),
        ("registration", C.c_uint64), ("attempt", C.c_uint64),
        ("client", C.c_uint64),
        ("ready", C.c_uint32), ("installed", C.c_uint32),
        ("in_action", C.c_uint32), ("native_busy", C.c_uint32),
        ("settle_timer", C.c_uint32), ("filter_count", C.c_uint32),
        ("qt_compiled", C.c_uint32), ("qt_runtime", C.c_uint32),
        ("paraview_compiled", C.c_uint32), ("pointer_bits", C.c_uint32),
        ("last_decision", C.c_int32), ("observer_count", C.c_uint32),
    ]

    def as_dict(self) -> dict[str, int]:
        return {name: int(getattr(self, name)) for name, _ in self._fields_}


class Draft(C.Structure):
    _fields_ = [("abi", C.c_uint32), ("size", C.c_uint32),
                ("unapplied", C.c_uint32), ("editors", C.c_uint32), ("digest", C.c_char * 64)]


class NativeExitUnavailable(RuntimeError):
    pass


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_artifact(plugin: Path, runtime_root: Path) -> dict[str, Any]:
    """Require a sidecar pinned to the SDK build and the tested runtime.

    Hash equality proves artifact identity, NOT binary compatibility or GUI
    acceptance. CMake/SDK validation and native acceptance remain separate.
    """
    plugin = plugin.resolve(strict=True)
    root = runtime_root.resolve(strict=True)
    manifest_path = plugin.with_suffix(plugin.suffix + ".manifest.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema") != "cae.post-exit-artifact/1" or manifest.get("abi") != ABI:
        raise NativeExitUnavailable("Unknown native exit artifact manifest")
    if manifest.get("plugin_sha256") != file_sha256(plugin):
        raise NativeExitUnavailable("Native exit plugin hash mismatch")
    build = manifest.get("build", {})
    if (build.get("paraview") != "6.2.0" or build.get("qt") != "6.9.0" or
            build.get("configuration") != "Release" or build.get("pointer_bits") != 64):
        raise NativeExitUnavailable("Requires the recorded ParaView 6.2.0 / Qt 6.9.0 x64 Release build")
    if not build.get("sdk_evidence_sha256"):
        raise NativeExitUnavailable("Matching SDK evidence was not recorded")
    pins = manifest.get("runtime_files")
    if not isinstance(pins, dict) or not pins:
        raise NativeExitUnavailable("Runtime pins are missing")
    names = {Path(name).name.lower() for name in pins}
    required = {"paraview.exe", "qt6core.dll", "qt6gui.dll", "qt6widgets.dll", "python312.dll"}
    if not required.issubset(names) or not any(name.startswith("pqcore") for name in names):
        raise NativeExitUnavailable("Incomplete ParaView/Qt/Python runtime identity")
    for relative, expected in pins.items():
        candidate = (root / relative).resolve(strict=True)
        if not candidate.is_relative_to(root) or not candidate.is_file():
            raise NativeExitUnavailable("Runtime pin escapes the installation")
        if file_sha256(candidate) != expected:
            raise NativeExitUnavailable("Runtime file differs: " + relative)
    return manifest


@dataclass
class Library:
    dll: Any
    path: Path

    @classmethod
    def load(cls, path: Path) -> "Library":
        # Loading the official ParaView plugin must precede opening its own C ABI.
        # CDLL/cdecl releases the GIL; CFUNCTYPE reacquires it on the GUI thread.
        # The Library object is retained for process lifetime by native_exit.py.
        dll = C.CDLL(str(path.resolve(strict=True)))
        signatures = {
            "draft": (C.c_int32, [C.c_uint64, C.POINTER(Draft), C.c_uint32]),
            "probe": (C.c_int32, [C.POINTER(Status), C.c_uint32]),
            "attach": (C.c_int32, [C.c_uint32, C.c_uint64, C.c_uint64, C.c_char_p,
                                    C.c_uint32, C.c_uint64, CALLBACK, C.POINTER(C.c_uint64)]),
            "detach": (C.c_int32, [C.c_uint64]),
            "status": (C.c_int32, [C.c_uint64, C.POINTER(Status), C.c_uint32]),
            "prompt": (C.c_int32, [C.c_uint64]),
            "error": (C.c_int32, [C.c_uint64, C.c_char_p, C.c_uint32]),
        }
        for suffix, (result, arguments) in signatures.items():
            function = getattr(dll, "cae_post_exit_v1_" + suffix)
            function.restype, function.argtypes = result, arguments
        return cls(dll, path.resolve())

    def _call(self, suffix: str, *args: Any) -> int:
        return int(getattr(self.dll, "cae_post_exit_v1_" + suffix)(*args))

    def probe(self) -> Status:
        status = Status(abi=ABI, size=C.sizeof(Status))
        code = self._call("probe", C.byref(status), C.sizeof(status))
        if code != OK:
            raise NativeExitUnavailable(f"Native exit probe failed ({code})")
        if (status.abi != ABI or status.size != C.sizeof(Status) or
                status.pointer_bits != C.sizeof(C.c_void_p) * 8 or
                status.qt_compiled != status.qt_runtime or status.qt_runtime != 0x060900 or
                status.paraview_compiled != 0x060200):
            raise NativeExitUnavailable("Native exit ABI/Qt/ParaView mismatch")
        if status.pid != os.getpid() or not status.ready or not status.window:
            raise NativeExitUnavailable("No exact current-process ParaView main window")
        return status

    def attach(self, session: str, window: int, client: int, callback: Any) -> int:
        raw = session.encode("utf-8")
        if not raw or len(raw) > 127 or b"\0" in raw:
            raise NativeExitUnavailable("Invalid native owner session")
        registration = C.c_uint64()
        code = self._call("attach", ABI, os.getpid(), window, raw, len(raw), client,
                          callback, C.byref(registration))
        if code != OK or not registration.value:
            raise NativeExitUnavailable(f"Native exit attach failed ({code})")
        return registration.value

    def status(self, registration: int) -> Status:
        result = Status(abi=ABI, size=C.sizeof(Status))
        code = self._call("status", registration, C.byref(result), C.sizeof(result))
        if code != OK:
            raise NativeExitUnavailable(f"Native exit status failed ({code})")
        return result

    def draft(self, registration: int) -> dict[str, Any]:
        result = Draft(abi=ABI, size=C.sizeof(Draft))
        code = self._call("draft", registration, C.byref(result), C.sizeof(result))
        digest = bytes(result.digest).decode("ascii", errors="strict")
        if (code != OK or result.abi != ABI or result.size != C.sizeof(Draft) or
                result.unapplied not in (0, 1) or len(digest) != 64 or
                any(char not in "0123456789abcdef" for char in digest)):
            raise NativeExitUnavailable("Native Properties draft state is UNKNOWN")
        return {"unapplied": bool(result.unapplied), "editors": int(result.editors), "sha256": digest}

    def detach(self, registration: int) -> bool:
        code = self._call("detach", registration)
        if code not in (OK, WRONG_OWNER):
            raise NativeExitUnavailable(f"Native exit detach failed ({code})")
        return True  # WRONG_OWNER means this exact old registration is no longer installed.

    def ask_close(self, registration: int) -> str:
        return {1: "save", 2: "discard", 3: "cancel"}.get(self._call("prompt", registration), "cancel")

    def error(self, registration: int, message: str) -> None:
        raw = message.encode("utf-8")
        if self._call("error", registration, raw, len(raw)) != OK:
            raise NativeExitUnavailable("Native error dialog unavailable")
