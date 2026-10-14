"""Windows session-local Save and window-close gates; no foreign Qt binding.

Only the current ParaView GUI thread is hooked. The optional SDK plugin handles
Qt close events; without it File/Exit remains outside the Win32 fallback gate.
"""
import ctypes
from ctypes import wintypes as W
import json
import os

WM_CLOSE, WM_NCDESTROY = 0x10, 0x82
WM_KEYDOWN, WM_SYSKEYDOWN, WM_NULL = 0x100, 0x104, 0
_live_windows = set()  # Retain C callbacks even if native uninstall reports failure.


class Controls:
    def __init__(self, owner, platform, *, busy=lambda: False, log=None, on_closed=None):
        self.owner, self.platform, self.busy, self.log = owner, platform, busy, log
        self.on_closed = on_closed
        self.main = None
        self.in_action = self.closed = False

    def refresh(self):
        self.owner.assert_thread()
        if self.closed or self.main:
            return
        main = self.platform.main_window()
        if main:
            self.platform.install(main, self.window_message, self.key_message)
            self.main = main
            self._log('native_save_controls_installed', scope='current_process_gui_thread')

    def _log(self, event, **details):
        if self.log:
            self.log(event, **details)

    def _state(self):
        self.owner.refresh()
        snapshot = self.owner.snapshot
        pending = any(item.get('pending_properties') for item in
            snapshot.get('sources', []) + snapshot.get('views', []) +
            list(snapshot.get('representations', {}).values()))
        # Include unchecked fields: they can change without an applied generation.
        stamp = (self.owner.session_id, json.dumps(snapshot, sort_keys=True, default=str))
        return bool(self.owner.descriptor()['dirty']) or pending, stamp

    def _save(self):
        try:
            self.owner.save_project()
        except Exception as error:
            self._log('native_project_save_failed', error=str(error), error_type=type(error).__name__)
            if str(error).startswith('BUSY_EDIT:'):
                message = '적용하지 않은 변경이 있습니다. ParaView에서 적용 또는 되돌리기를 선택한 뒤 저장하세요.'
            else:
                message = '프로젝트를 저장하지 못했습니다. 현재 내용과 이전 저장본은 유지됩니다.'
            self.platform.error(self.main, message)
            return False
        self._log('native_project_saved')
        print('프로젝트를 저장했습니다.')
        return True

    def key_message(self):
        self.owner.assert_thread()
        if self.closed or self.in_action:
            return
        if self.busy():
            self.platform.error(self.main, '현재 작업이 끝난 뒤 저장하세요.')
            return
        self.in_action = True
        try:
            self._save()
        finally:
            self.in_action = False

    def window_message(self, message):
        self.owner.assert_thread()
        if self.closed:
            return False
        if message == WM_NCDESTROY:
            try:
                self.close()
            finally:
                if self.on_closed is not None:
                    self.on_closed()
            return False
        if message != WM_CLOSE:
            return False
        if getattr(self, 'qt_close_gate_active', False):
            # Let Qt emit its QCloseEvent. The scoped native filter owns the
            # same save decision; prompting here too would ask twice.
            return False
        return self.close_decision().decision != 'allow'

    def close_decision(self):
        if __package__:
            from .native_exit_gate import decide
        else:
            from native_exit_gate import decide
        return decide(self)

    def close(self):
        self.owner.assert_thread()
        if not self.closed:
            self.closed = True
            self.platform.close()


class _Message(ctypes.Structure):
    _fields_ = [('hwnd', W.HWND), ('message', W.UINT), ('wParam', ctypes.c_size_t),
                ('lParam', ctypes.c_ssize_t), ('time', W.DWORD), ('pt', W.POINT), ('private', W.DWORD)]


class _Button(ctypes.Structure):
    _pack_ = 1
    _fields_ = [('id', ctypes.c_int), ('text', W.LPCWSTR)]


class _Dialog(ctypes.Structure):
    _pack_ = 1
    _fields_ = [('size', W.UINT), ('parent', W.HWND), ('instance', W.HINSTANCE),
        ('flags', W.UINT), ('common', W.UINT), ('title', W.LPCWSTR), ('icon', ctypes.c_void_p),
        ('instruction', W.LPCWSTR), ('content', W.LPCWSTR), ('count', W.UINT),
        ('buttons', ctypes.POINTER(_Button)), ('default', ctypes.c_int), ('radio_count', W.UINT),
        ('radios', ctypes.c_void_p), ('radio_default', ctypes.c_int), ('verification', W.LPCWSTR),
        ('expanded', W.LPCWSTR), ('expand_text', W.LPCWSTR), ('collapse_text', W.LPCWSTR),
        ('footer_icon', ctypes.c_void_p), ('footer', W.LPCWSTR), ('callback', ctypes.c_void_p),
        ('data', ctypes.c_ssize_t), ('width', W.UINT)]


class _Windows:
    def __init__(self):
        self.user = ctypes.WinDLL('user32', use_last_error=True)
        self.common = ctypes.WinDLL('comctl32', use_last_error=True)
        self.kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        self.thread = self.kernel.GetCurrentThreadId()
        self.main = self.hook = None
        self.callbacks = []
        self.enabled = True
        self.last_error = None
        ptr, number = ctypes.c_void_p, ctypes.c_size_t
        self.subclass_type = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, W.HWND, W.UINT, number, ctypes.c_ssize_t, number, number)
        self.hook_type = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_int, number, ctypes.c_ssize_t)
        for library, name, result, arguments in [
            (self.common,'SetWindowSubclass',W.BOOL,[W.HWND,self.subclass_type,number,number]),
            (self.common,'RemoveWindowSubclass',W.BOOL,[W.HWND,self.subclass_type,number]),
            (self.common,'DefSubclassProc',ctypes.c_ssize_t,[W.HWND,W.UINT,number,ctypes.c_ssize_t]),
            (self.user,'SetWindowsHookExW',ptr,[ctypes.c_int,self.hook_type,W.HINSTANCE,W.DWORD]),
            (self.user,'CallNextHookEx',ctypes.c_ssize_t,[ptr,ctypes.c_int,number,ctypes.c_ssize_t]),
            (self.user,'UnhookWindowsHookEx',W.BOOL,[ptr]),
            (self.user,'GetAncestor',W.HWND,[W.HWND,W.UINT]),
            (self.user,'GetWindow',W.HWND,[W.HWND,W.UINT]),
            (self.user,'GetWindowTextW',ctypes.c_int,[W.HWND,W.LPWSTR,ctypes.c_int]),
            (self.user,'GetClassNameW',ctypes.c_int,[W.HWND,W.LPWSTR,ctypes.c_int]),
            (self.user,'GetWindowLongPtrW',ctypes.c_ssize_t,[W.HWND,ctypes.c_int]),
            (self.user,'IsWindowVisible',W.BOOL,[W.HWND]),
            (self.user,'IsWindowEnabled',W.BOOL,[W.HWND]),
            (self.user,'GetKeyState',ctypes.c_short,[ctypes.c_int]),
            (self.user,'MessageBoxW',ctypes.c_int,[W.HWND,W.LPCWSTR,W.LPCWSTR,W.UINT])]:
            function = getattr(library, name)
            function.restype, function.argtypes = result, arguments
        self.task_dialog = getattr(self.common,'TaskDialogIndirect',None)
        if self.task_dialog is not None:
            self.task_dialog.restype = ctypes.c_long
            self.task_dialog.argtypes = [ctypes.POINTER(_Dialog),ctypes.POINTER(ctypes.c_int),ptr,ptr]

    def main_window(self):
        found = []
        enum = ctypes.WINFUNCTYPE(W.BOOL, W.HWND, ctypes.c_ssize_t)
        @enum
        def visit(hwnd, _):
            try:
                title, name = ctypes.create_unicode_buffer(512), ctypes.create_unicode_buffer(256)
                self.user.GetWindowTextW(hwnd, title, len(title)); self.user.GetClassNameW(hwnd, name, len(name))
                style = self.user.GetWindowLongPtrW(hwnd, -16)
                if (name.value.startswith('Qt') and 'ParaView' in title.value
                    and not self.user.GetWindow(hwnd, 4)
                    and (style & 0x00C00000) == 0x00C00000 and (style & 0x000C0000) == 0x000C0000
                    and not (style & 0x40000000)):
                    found.append(hwnd)
            except BaseException as error:
                self.last_error = str(error)
            return True
        self.user.EnumThreadWindows.argtypes = [W.DWORD, enum, ctypes.c_ssize_t]
        self.user.EnumThreadWindows(self.thread, visit, 0)
        return found[0] if len(found) == 1 else None

    def install(self, main, on_message, on_save):
        self.main = main
        @self.subclass_type
        def subclass(hwnd, message, wparam, lparam, _identifier, _data):
            try:
                if on_message(message):
                    return 0
            except BaseException as error:
                self.last_error = str(error)
                if message == WM_CLOSE:
                    return 0
            try:
                return self.common.DefSubclassProc(hwnd, message, wparam, lparam)
            except BaseException as error:
                self.last_error = str(error)
                return 0
        @self.hook_type
        def keyboard(code, removed, address):
            try:
                if self.enabled and code >= 0 and removed == 1:
                    message = ctypes.cast(address, ctypes.POINTER(_Message)).contents
                    if (message.message in (WM_KEYDOWN, WM_SYSKEYDOWN) and message.wParam == ord('S')
                        and self.user.GetAncestor(message.hwnd, 2) == self.main
                        and self.user.IsWindowEnabled(self.main)
                        and self.user.GetKeyState(0x11) < 0
                        and self.user.GetKeyState(0x10) >= 0 and self.user.GetKeyState(0x12) >= 0
                        and self.user.GetKeyState(0x5B) >= 0 and self.user.GetKeyState(0x5C) >= 0):
                        repeated = bool(message.lParam & (1 << 30))
                        message.message, message.wParam, message.lParam = WM_NULL, 0, 0
                        if not repeated:
                            on_save()
            except BaseException as error:
                self.last_error = str(error)
            try:
                return self.user.CallNextHookEx(self.hook, code, removed, address)
            except BaseException as error:
                self.last_error = str(error)
                return 0
        self.callbacks = [subclass, keyboard]  # Keep C callbacks alive until native teardown.
        _live_windows.add(self)
        if not self.common.SetWindowSubclass(main, subclass, 0xCAE, 0):
            _live_windows.discard(self)
            raise ctypes.WinError(ctypes.get_last_error())
        self.hook = self.user.SetWindowsHookExW(3, keyboard, None, self.thread)
        if not self.hook:
            if self.common.RemoveWindowSubclass(main, subclass, 0xCAE):
                _live_windows.discard(self)
            raise ctypes.WinError(ctypes.get_last_error())

    def ask_close(self, main):
        if self.task_dialog is None:
            choice = self.user.MessageBoxW(main,
                '변경 내용을 저장하고 닫을까요?\n\n예: 저장하고 닫기\n아니요: 저장하지 않고 닫기\n취소: 편집 계속',
                '프로젝트 저장', 0x3 | 0x200)
            return {6:'save',7:'discard'}.get(choice,'cancel')
        buttons = (_Button*3)(_Button(1001,'저장'),_Button(1002,'저장 안 함'),_Button(2,'취소'))
        dialog = _Dialog(); dialog.size = ctypes.sizeof(dialog); dialog.parent = main
        dialog.flags = 8; dialog.title = '프로젝트 저장'; dialog.instruction = '변경 내용을 저장하고 닫을까요?'
        dialog.content = '현재 표시와 해석 설정을 같은 프로젝트에 저장합니다.'
        dialog.count = 3; dialog.buttons = buttons; dialog.default = 2
        choice = ctypes.c_int(2)
        if self.task_dialog(ctypes.byref(dialog),ctypes.byref(choice),None,None) != 0:
            self.error(main,'닫기 선택창을 열지 못했습니다. 창을 유지합니다.')
            return 'cancel'
        return {1001:'save',1002:'discard'}.get(choice.value,'cancel')

    def error(self, main, text):
        self.user.MessageBoxW(main,text,'프로젝트 저장',0x10)

    def close(self):
        self.enabled = False
        if self.hook:
            if self.user.UnhookWindowsHookEx(self.hook):
                self.hook = None
        removed = True
        if self.main and self.callbacks:
            removed = bool(self.common.RemoveWindowSubclass(self.main,self.callbacks[0],0xCAE))
        if removed and not self.hook:
            self.main = None
            _live_windows.discard(self)


def install(owner, *, busy=lambda: False, log=None, on_closed=None):
    owner.assert_thread()
    if os.name != 'nt':
        return None
    controls = Controls(owner, _Windows(), busy=busy, log=log, on_closed=on_closed)
    try:
        controls.refresh()
    except Exception:
        controls.close()
        raise
    return controls
