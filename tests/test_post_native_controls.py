"""Same-owner save/close gates and current-thread Win32 message scope. No solver."""
from copy import deepcopy
import ctypes
from ctypes import wintypes as W
import os
import threading
from types import SimpleNamespace
import pytest
from apps.desktop_post.native_controls import Controls, WM_CLOSE, _Windows, _Message, WM_KEYDOWN, WM_NULL
from test_desktop_post_bridge import bridge, command


class Owner:
    def __init__(self):
        self.thread=threading.get_ident();self.session_id='Sone';self.dirty=True;self.saved=0
        self.snapshot={'sources':[{'pending_properties':{}}],'views':[],'representations':{}}
        self.error=None
    def assert_thread(self):assert threading.get_ident()==self.thread
    def refresh(self):self.assert_thread();return self.snapshot
    def descriptor(self):return {'dirty':self.dirty}
    def save_project(self):
        self.assert_thread()
        if self.error:raise self.error
        if self.snapshot['sources'][0]['pending_properties']:raise ValueError('BUSY_EDIT: unchecked')
        self.saved+=1;self.dirty=False


class Platform:
    def __init__(self,choice='cancel'):
        self.choice=choice;self.errors=[];self.installs=0;self.closed=0;self.prompt=lambda:None
    def main_window(self):return 123
    def install(self,*args):self.installs+=1
    def ask_close(self,main):self.prompt();return self.choice
    def error(self,main,text):self.errors.append(text)
    def close(self):self.closed+=1


@pytest.mark.parametrize('choice,blocked,saves',[('cancel',True,0),('discard',False,0),('save',False,1)])
def test_close_choice_same_owner_and_cancel_preserves_unchecked_input(choice,blocked,saves):
    owner=Owner();platform=Platform(choice);controls=Controls(owner,platform);controls.refresh()
    before=deepcopy(owner.snapshot)
    assert controls.window_message(WM_CLOSE) is blocked
    assert owner.saved==saves and owner.snapshot==before and not controls.in_action


def test_pending_or_failed_save_and_changed_prompt_leave_window_open():
    owner=Owner();platform=Platform('save');controls=Controls(owner,platform);controls.refresh()
    owner.dirty=False;owner.snapshot['sources'][0]['pending_properties']={'Plane.Origin':'1e'}
    assert controls.window_message(WM_CLOSE) and owner.saved==0
    assert '적용하지 않은' in platform.errors[-1]
    owner.snapshot['sources'][0]['pending_properties']={};owner.dirty=True;owner.error=OSError('file missing')
    assert controls.window_message(WM_CLOSE) and owner.dirty
    owner.error=None;platform.choice='discard'
    platform.prompt=lambda:owner.snapshot['sources'][0]['pending_properties'].update({'Plane.Origin':'changed'})
    assert controls.window_message(WM_CLOSE) and owner.saved==0
    assert '내용이 바뀌었습니다' in platform.errors[-1]


def test_current_save_busy_reentrancy_and_cleanup():
    owner=Owner();platform=Platform();busy=[True];controls=Controls(owner,platform,busy=lambda:busy[0])
    controls.refresh();controls.refresh();assert platform.installs==1
    controls.key_message();assert owner.saved==0
    busy[0]=False;controls.key_message();assert owner.saved==1
    controls.in_action=True;controls.key_message();assert owner.saved==1
    controls.close();controls.close();assert platform.closed==1


def test_modal_choices_keep_heartbeat_without_running_queued_edits(bridge):
    owner=bridge.module.Owner();dispatcher=bridge.module.GuiDispatch(owner)
    dispatcher.native_controls=SimpleNamespace(refresh=lambda:None,in_action=True)
    dispatcher.ready=True;dispatcher._last_heartbeat=0
    request=command(owner);dispatcher.incoming.put(request)
    dispatcher._tick()
    assert dispatcher.outgoing.get_nowait()['event']=='heartbeat'
    assert dispatcher.last_tick>0 and dispatcher.incoming.get_nowait()==request
    assert dispatcher.command_gate.request is None and not owner.completed


@pytest.mark.parametrize('button,choice',[(6,'save'),(7,'discard'),(2,'cancel'),(0,'cancel')])
def test_missing_task_dialog_uses_native_yes_no_cancel_with_cancel_default(button,choice):
    api=_Windows.__new__(_Windows);api.task_dialog=None;calls=[]
    api.user=SimpleNamespace(MessageBoxW=lambda *args:(calls.append(args),button)[1])
    assert api.ask_close(123)==choice
    assert calls[0][3]==0x203 and '예: 저장' in calls[0][1] and '아니요: 저장하지' in calls[0][1]


@pytest.mark.skipif(os.name!='nt',reason='Windows same-thread native hook only')
def test_win32_owned_hidden_children_exact_ctrl_s_repeat_modal_and_close(monkeypatch):
    api=_Windows();u=api.user
    u.CreateWindowExW.argtypes=[W.DWORD,W.LPCWSTR,W.LPCWSTR,W.DWORD,ctypes.c_int,ctypes.c_int,
        ctypes.c_int,ctypes.c_int,W.HWND,W.HMENU,W.HINSTANCE,ctypes.c_void_p]
    u.CreateWindowExW.restype=W.HWND
    u.DestroyWindow.argtypes=[W.HWND];u.DestroyWindow.restype=W.BOOL
    u.IsWindow.argtypes=[W.HWND];u.IsWindow.restype=W.BOOL
    u.EnableWindow.argtypes=[W.HWND,W.BOOL]
    u.SendMessageW.argtypes=[W.HWND,W.UINT,ctypes.c_size_t,ctypes.c_ssize_t];u.SendMessageW.restype=ctypes.c_ssize_t
    main=u.CreateWindowExW(0,'STATIC','TEST ONLY ParaView',0,0,0,100,100,None,None,None,None)
    child=u.CreateWindowExW(0,'STATIC','TEST ONLY focus',0x40000000,0,0,50,50,main,None,None,None)
    foreign=u.CreateWindowExW(0,'STATIC','TEST ONLY unrelated',0,0,0,50,50,None,None,None,None)
    editor=u.CreateWindowExW(0,'STATIC','TEST ONLY modeless script editor',0,0,0,50,50,main,None,None,None)
    assert main and child and foreign
    owner=Owner();controls=Controls(owner,api);controls.main=main
    api.install(main,controls.window_message,controls.key_message)
    keys={0x11:-1,0x10:0,0x12:0}
    monkeypatch.setattr(u,'GetKeyState',lambda key:keys.get(key,0))
    monkeypatch.setattr(api,'ask_close',lambda _: 'cancel')
    monkeypatch.setattr(api,'error',lambda *_:None)
    def key(hwnd,removed=1,repeat=False):
        message=_Message();message.hwnd=hwnd;message.message=WM_KEYDOWN;message.wParam=ord('S')
        message.lParam=(1<<30) if repeat else 0
        api.callbacks[1](0,removed,ctypes.addressof(message))
        return message.message
    try:
        assert key(child)==WM_NULL and owner.saved==1
        assert key(child,repeat=True)==WM_NULL and owner.saved==1
        assert key(child,removed=0)==WM_KEYDOWN and owner.saved==1
        keys[0x10]=-1;assert key(child)==WM_KEYDOWN;keys[0x10]=0
        keys[0x12]=-1;assert key(child)==WM_KEYDOWN;keys[0x12]=0
        assert key(foreign)==WM_KEYDOWN
        assert key(editor)==WM_KEYDOWN  # Owned top-level editors keep their own Save.
        original_assert=owner.assert_thread
        def abort():raise SystemExit('callback boundary')
        monkeypatch.setattr(owner,'assert_thread',abort)
        assert key(child)==WM_NULL and 'callback boundary' in api.last_error
        u.SendMessageW(main,WM_CLOSE,0,0);assert u.IsWindow(main)
        monkeypatch.setattr(owner,'assert_thread',original_assert)
        u.EnableWindow(main,False);assert key(child)==WM_KEYDOWN;u.EnableWindow(main,True)
        owner.dirty=True;u.SendMessageW(main,WM_CLOSE,0,0);assert u.IsWindow(main)
        monkeypatch.setattr(api,'ask_close',lambda _: 'save');owner.error=OSError('failure')
        u.SendMessageW(main,WM_CLOSE,0,0);assert u.IsWindow(main)
        monkeypatch.setattr(api,'ask_close',lambda _: 'discard')
        u.SendMessageW(main,WM_CLOSE,0,0);assert not u.IsWindow(main) and controls.closed
        assert api.hook is None
    finally:
        controls.close()
        if u.IsWindow(main):u.DestroyWindow(main)
        if u.IsWindow(foreign):u.DestroyWindow(foreign)
        if u.IsWindow(editor):u.DestroyWindow(editor)
