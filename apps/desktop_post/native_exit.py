"""Managed-session adapter for the official ParaView GUI exit plugin.

Callbacks run synchronously on the native GUI owner thread. The single process
callback and DLL reference outlive all registrations; owner references do not.
"""
from __future__ import annotations

import atexit
import itertools
import os
from pathlib import Path
import weakref
from typing import Any

if __package__:
    from . import native_exit_abi as abi
    from . import native_exit_gate as gate
else:
    import native_exit_abi as abi
    import native_exit_gate as gate

_clients: dict[int, weakref.ReferenceType] = {}
_libraries: dict[str, abi.Library] = {}
_ids = itertools.count(1)


def _callback(client: int, registration: int, attempt: int, event: int) -> int:
    # Absolutely no exception or unspecified integer may cross the C boundary.
    try:
        reference = _clients.get(client)
        session = reference() if reference else None
        if session is None or session.closed or session.registration != registration:
            return abi.UNKNOWN
        result = session.on_event(attempt, event)
        return result if type(result) is int and result in (abi.ALLOW, abi.BLOCK, abi.UNKNOWN) else abi.UNKNOWN
    except BaseException:
        return abi.UNKNOWN


_CALLBACK = abi.CALLBACK(_callback)


class _Prompts:
    def __init__(self, original: Any, session: "Session"):
        self.original, self.session = original, session

    def __getattr__(self, name: str) -> Any:
        return getattr(self.original, name)

    def ask_close(self, main: int) -> str:
        self.session.check_window(main)
        return self.session.library.ask_close(self.session.registration)

    def error(self, main: int, text: str) -> None:
        self.session.check_window(main)
        self.session.library.error(self.session.registration, text)


class Session:
    def __init__(self, dispatcher: Any, library: abi.Library, native: Any):
        self.dispatcher, self.owner = dispatcher, dispatcher.owner
        self.controls, self.library = dispatcher.native_controls, library
        self.native = native
        self.closed = False
        self.registration = self.attempt = 0
        self.permission = None
        self.client = next(_ids)
        self.window = 0
        self._held = False
        self._original = {}

    def install(self) -> "Session":
        self.owner.assert_thread()
        controls = self.controls
        if controls is None or controls.closed:
            raise abi.NativeExitUnavailable("Current owner Save controls are unavailable")
        if getattr(controls, "qt_close_gate_active", False):
            raise abi.NativeExitUnavailable("This owner already has a native close gate")
        status = self.library.probe()
        if status.installed:
            raise abi.NativeExitUnavailable("A different registration already owns the native close gate")
        self.window = int(status.window)
        # Use the SDK's exact mainWidget HWND, not an English window-title match.
        if controls.main is None:
            controls.platform.install(self.window, controls.window_message, controls.key_message)
            controls.main = self.window
        if int(controls.main) != self.window:
            raise abi.NativeExitUnavailable("Win32 controls and Qt mainWidget do not match")
        names = ("platform", "busy", "require_save_receipt", "close_fingerprint", "close_pending_inputs", "qt_close_gate_active")
        self._original = {name: (hasattr(controls, name), getattr(controls, name, None)) for name in names}
        _clients[self.client] = weakref.ref(self)
        try:
            self.registration = self.library.attach(self.owner.session_id, self.window, self.client, _CALLBACK)
            controls.platform = _Prompts(controls.platform, self)
            controls.require_save_receipt = True
            def fingerprint():
                return {"unchecked": gate.unchecked_fingerprint(native=self.native),
                        "native_draft": self.library.draft(self.registration)}
            controls.close_fingerprint = fingerprint
            controls.close_pending_inputs = lambda: self.library.draft(self.registration)["unapplied"]
            old_busy = self._original["busy"][1]

            def busy() -> bool:
                # UNKNOWN state must raise, not become false via bool(None).
                old = old_busy()
                if type(old) is not bool:
                    raise gate.UnknownState("existing native operation state is unknown")
                current = self._status()
                if current.native_busy not in (0, 1):
                    raise gate.UnknownState("native ParaView progress state is unknown")
                return old or bool(current.native_busy)

            controls.busy = busy
            controls.qt_close_gate_active = True
            controls._log("native_qt_close_gate_installed", session=self.owner.session_id,
                          registration=self.registration, scope="exact_current_process_main_window")
            return self
        except BaseException:
            self.close()
            raise

    def check_window(self, main: int) -> None:
        self.owner.assert_thread()
        if self.closed or int(main) != self.window:
            raise abi.NativeExitUnavailable("The prompt does not belong to this managed main window")

    def _status(self) -> abi.Status:
        self.owner.assert_thread()
        status = self.library.status(self.registration)
        if (not status.ready or not status.installed or status.registration != self.registration or
                status.client != self.client or status.window != self.window or status.pid != os.getpid()):
            raise abi.NativeExitUnavailable("Native exit registration is no longer current")
        return status

    @property
    def in_action(self) -> bool:
        if self.closed:
            return False
        try:
            return self._held or bool(self._status().in_action)
        except BaseException:
            # Never let transport mutations run inside an unobservable modal gate.
            return True

    def _release(self) -> None:
        if self._held:
            self.controls.in_action = False
        self._held = False
        self.permission = None
        self.attempt = 0

    def on_event(self, attempt: int, event: int) -> int:
        self.owner.assert_thread()
        if self.closed or self.dispatcher.owner is not self.owner:
            return abi.UNKNOWN
        if event == abi.BEGIN:
            if not attempt or self._held or self.dispatcher.closed:
                return abi.BLOCK
            self.attempt = attempt
            self.permission = self.controls.close_decision()
            if self.permission.decision != "allow":
                result = abi.BLOCK if self.permission.decision == "block" else abi.UNKNOWN
                self._release()
                return result
            # Pause Ctrl+S and queued mutation until the original Qt handler has
            # either really closed the window or vetoed it. No second save dialog.
            self._held = True
            self.controls.in_action = True
            return abi.ALLOW
        if event == abi.VALIDATE:
            if attempt != self.attempt or not self._held:
                return abi.UNKNOWN
            decision = gate.validate(self.controls, self.permission)
            return {"allow": abi.ALLOW, "block": abi.BLOCK}.get(decision.decision, abi.UNKNOWN)
        if event == abi.ABORTED:
            if attempt != self.attempt:
                return abi.UNKNOWN
            self._release()
            return abi.ALLOW
        if event in (abi.CLOSED, abi.DESTROYED, abi.SHUTDOWN):
            if event == abi.CLOSED and (attempt != self.attempt or not self._held):
                return abi.UNKNOWN
            # SHUTDOWN / DESTROYED are cleanup notifications, NOT cancellable
            # save decisions. Existing busy protection/closed receipts are kept.
            self.dispatcher.close()
            if not self.closed:  # Also support a test dispatcher with no adapter hook.
                self.close()
            return abi.ALLOW
        return abi.UNKNOWN

    def close(self) -> None:
        self.owner.assert_thread()
        if self.closed:
            return
        # Detach first. Failure retains the callable registration and owner;
        # freeing a callback still installed in Qt would be unsafe.
        if self.registration:
            self.library.detach(self.registration)
        self._release()
        for name, (existed, value) in self._original.items():
            if existed:
                setattr(self.controls, name, value)
            elif hasattr(self.controls, name):
                delattr(self.controls, name)
        self.closed = True
        _clients.pop(self.client, None)
        self.registration = 0
        self._original.clear()
        # Break ownership cycles after callbacks have been removed.
        self.dispatcher = self.native = None


def install(dispatcher: Any) -> Session | None:
    """Optional integration. No configuration means explicit degraded mode."""
    path = os.environ.get("CAE_POST_EXIT_PLUGIN")
    root = os.environ.get("CAE_POST_PARAVIEW_ROOT")
    if not path or not root:
        print("native 전체 종료 보호 미설치: File > Exit/Ctrl+Q는 보호되지 않습니다. "
              "기존 X/Alt+F4 또는 저장 매크로를 사용하세요.")
        return None
    dispatcher.owner.assert_thread()
    plugin, runtime = Path(path), Path(root)
    abi.verify_artifact(plugin, runtime)
    from paraview import simple as native
    # Official plugin loader constructs the GUI auto-start interface. A plain
    # ctypes load alone is not a ParaView plugin installation.
    native.LoadPlugin(str(plugin.resolve()), remote=False)
    key = str(plugin.resolve())
    if key not in _libraries:
        _libraries[key] = abi.Library.load(plugin)
    return Session(dispatcher, _libraries[key], native).install()


def _at_exit() -> None:
    # Normal main-thread interpreter finalization only. This is not a close veto.
    for reference in list(_clients.values()):
        session = reference()
        if session is not None:
            try:
                session.close()
            except BaseException:
                pass


atexit.register(_at_exit)
