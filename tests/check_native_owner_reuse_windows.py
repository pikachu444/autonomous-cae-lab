"""Exact existing Pre/Post working owners: activate, close, and explicitly reopen.

Run inside scripts/native_check.py's private Windows Job. No solver, document
editing, save, capture, owner binding injection, or saved-intent deduplication.
"""
import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time
import uuid

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

PRE = r'''
import json,os,traceback
from pathlib import Path
from PySide import QtCore,QtGui
out=Path(os.environ['B81_NATIVE_CASE'])
def check():
    try:
        import cae_prep
        connection=cae_prep.CONNECTION
        if connection is None:QtCore.QTimer.singleShot(200,check);return
        owner=connection.active_owner()
        if not (out/'ready.json').exists():
            (out/'ready.json').write_text(json.dumps(owner.descriptor(),ensure_ascii=False),encoding='utf-8')
        if (out/'close.request').exists():
            def discard():
                for widget in QtGui.QApplication.topLevelWidgets():
                    if isinstance(widget,QtGui.QMessageBox) and widget.isVisible():
                        button=widget.button(QtGui.QMessageBox.Discard)
                        if button is not None:
                            (out/'discard-choice.json').write_text(json.dumps({'choice':'discard','native_dialog':True}),encoding='utf-8')
                            button.click()
            timer=QtCore.QTimer(connection.Gui.getMainWindow());timer.setInterval(100)
            timer.timeout.connect(discard);timer.start()
            connection._b81_discard_timer=timer
            (out/'close-dispatched.json').write_text(json.dumps({'owner':owner.document_id,'native_window_close':True}),encoding='utf-8')
            connection.Gui.getMainWindow().close()
            return
        QtCore.QTimer.singleShot(200,check)
    except BaseException:
        (out/'failed.txt').write_text(traceback.format_exc(),encoding='utf-8')
QtCore.QTimer.singleShot(1000,check)
'''

POST = r'''
import os,json,runpy,traceback,ctypes,threading,time
from ctypes import wintypes as W
from pathlib import Path
out=Path(os.environ['B81_NATIVE_CASE'])
lock=threading.Lock()
def event(name,**values):
    with lock:
        with (out/'close-events.jsonl').open('a',encoding='utf-8') as stream:
            stream.write(json.dumps({'event':name,'monotonic':time.monotonic(),'pid':os.getpid(),**values},ensure_ascii=False)+'\n')
try:
    scope=runpy.run_path(str(Path(os.environ['B81_REPO'])/'apps/desktop_post/startup.py'))
    owner,dispatch,broker=scope['cae_post_bridge']
    user=ctypes.WinDLL('user32',use_last_error=True)
    user.GetWindowThreadProcessId.argtypes=[W.HWND,ctypes.POINTER(W.DWORD)]
    user.PostMessageW.argtypes=[W.HWND,W.UINT,W.WPARAM,W.LPARAM]
    user.GetDlgItem.argtypes=[W.HWND,ctypes.c_int];user.GetDlgItem.restype=W.HWND
    callback=ctypes.WINFUNCTYPE(W.BOOL,W.HWND,W.LPARAM)
    user.EnumWindows.argtypes=[callback,W.LPARAM];user.EnumWindows.restype=W.BOOL
    for name in ('IsWindow','IsWindowVisible','IsWindowEnabled'):
        getattr(user,name).argtypes=[W.HWND];getattr(user,name).restype=W.BOOL
    user.GetWindowTextW.argtypes=[W.HWND,W.LPWSTR,ctypes.c_int]
    user.GetClassNameW.argtypes=[W.HWND,W.LPWSTR,ctypes.c_int]
    user.SendMessageTimeoutW.argtypes=[W.HWND,W.UINT,W.WPARAM,W.LPARAM,W.UINT,W.UINT,ctypes.POINTER(ctypes.c_size_t)]
    user.SendMessageTimeoutW.restype=ctypes.c_ssize_t
    user.PostMessageW.restype=W.BOOL
    def window(hwnd):
        pid=W.DWORD();user.GetWindowThreadProcessId(hwnd,ctypes.byref(pid))
        title=ctypes.create_unicode_buffer(512);kind=ctypes.create_unicode_buffer(128)
        user.GetWindowTextW(hwnd,title,512);user.GetClassNameW(hwnd,kind,128)
        return {'hwnd':int(hwnd or 0),'pid':pid.value,'exists':bool(user.IsWindow(hwnd)),
            'visible':bool(user.IsWindowVisible(hwnd)),'enabled':bool(user.IsWindowEnabled(hwnd)),
            'title':title.value,'class':kind.value}
    def discard_dialog(main):
        end=time.monotonic()+35;observed=set();clicked=set();previous=None
        while time.monotonic()<end:
            state=window(main)
            if state!=previous:event('main_window_state',window=state);previous=state
            def visit(hwnd,_):
                pid=W.DWORD();user.GetWindowThreadProcessId(hwnd,ctypes.byref(pid))
                if pid.value!=os.getpid() or not user.IsWindowVisible(hwnd):return True
                state=window(hwnd)
                if (hwnd,state['title']) not in observed:
                    observed.add((hwnd,state['title']));event('owned_visible_window',window=state)
                if state['title']=='프로젝트 저장':
                    for button_id in (1002,7):
                        button=user.GetDlgItem(hwnd,button_id)
                        if not button or button in clicked:continue
                        detail=window(button)
                        if not any(label in detail['title'] for label in ('저장 안 함','아니요','No','Discard')):continue
                        clicked.add(button);event('discard_button_found',dialog=state,button=detail,button_id=button_id)
                        # Official native TaskDialog click, not an assumed return value.
                        # https://learn.microsoft.com/en-us/windows/win32/controls/tdm-click-button
                        target,message,wparam=(hwnd,0x400+102,button_id) if button_id==1002 else (button,0x00F5,0)
                        result=ctypes.c_size_t();ctypes.set_last_error(0)
                        ok=user.SendMessageTimeoutW(target,message,wparam,0,2,2000,ctypes.byref(result))
                        event('discard_click_message',delivered=bool(ok),message=message,button_id=button_id,
                            result=result.value,last_error=ctypes.get_last_error())
                return True
            user.EnumWindows(callback(visit),0);time.sleep(.1)
    closing=False;instrumented=False
    def check(*_):
        global closing,instrumented
        try:
            controls=dispatch.native_controls
            if not dispatch.ready or controls is None or not controls.main:return
            if not instrumented:
                instrumented=True;event('native_ready',window=window(controls.main),exit_plugin_installed=dispatch.native_exit is not None)
                original_ask=controls.platform.ask_close
                def ask(*args,**kwargs):
                    event('ask_close_enter');answer=original_ask(*args,**kwargs)
                    event('ask_close_return',choice=answer);return answer
                controls.platform.ask_close=ask
                original_decide=controls.close_decision
                def decide(*args,**kwargs):
                    decision=original_decide(*args,**kwargs)
                    event('gate_decision',decision=decision.decision,reason=decision.reason);return decision
                controls.close_decision=decide
                controls.log=lambda name,**values:event(name,**values)
                original_forward=controls.platform.common.DefSubclassProc
                def forward(hwnd,message,wparam,lparam):
                    if message in (0x0010,0x0002,0x0082):event('native_forward_message',message=message,window=window(hwnd))
                    return original_forward(hwnd,message,wparam,lparam)
                controls.platform.common.DefSubclassProc=forward
                original_delivery=broker.deliver_event
                def deliver(*args,**kwargs):
                    payload=args[-1] if args else kwargs.get('event',{})
                    closed=isinstance(payload,dict) and payload.get('event')=='closed'
                    if closed:event('broker_closed_delivery_begin')
                    delivered=original_delivery(*args,**kwargs)
                    if closed:event('broker_closed_delivery_return',delivered=delivered)
                    return delivered
                broker.deliver_event=deliver
            if not (out/'ready.json').exists():
                (out/'ready.json').write_text(json.dumps(owner.descriptor(),ensure_ascii=False),encoding='utf-8')
            if (out/'close.request').exists() and not closing:
                closing=True
                assert window(controls.main)['pid']==os.getpid()
                threading.Thread(target=discard_dialog,args=(controls.main,),daemon=True).start()
                (out/'close-dispatched.json').write_text(json.dumps({'owner':owner.document_id,'native_window_close':True}),encoding='utf-8')
                ok=user.PostMessageW(controls.main,0x0010,0,0)
                event('wm_close_posted',accepted=bool(ok),window=window(controls.main))
        except BaseException:(out/'failed.txt').write_text(traceback.format_exc(),encoding='utf-8')
    dispatch._b81_observer=dispatch.interactor.AddObserver('TimerEvent',check)
except BaseException:
    (out/'failed.txt').write_text(traceback.format_exc(),encoding='utf-8');raise
'''


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def write(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
def cid():return 'C'+uuid.uuid4().hex


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--kind',choices=('all','pre','post'),default='all')
    args=parser.parse_args();source=args.source.resolve(strict=True);out=args.output.resolve()
    out.mkdir(parents=True,exist_ok=False);workspace=out/'workspace';workspace.mkdir()
    manifest=json.loads((source/'portable-project.json').read_text(encoding='utf-8'))
    target_ids={'K399b1645266042f7a104d9553f582750','K47bb36b1959a4688aaaddca26acbf1aa'}
    targets=[t for t in manifest['native_projects'] if t['target_id'] in target_ids]
    assert len(targets)==2
    copied={};paths=[source/'portable-project.json']
    paths.extend(source/item['path'] for item in manifest['files'])
    for entry in manifest['native_inputs']:
        paths.extend(p for p in (source/'workbench/inputs'/entry['local_input_id']).rglob('*') if p.is_file())
    for target in targets:
        head_path=source/target['head_file'];head=json.loads(head_path.read_text(encoding='utf-8'))
        paths.append(head_path)
    if args.kind!='all':targets=[target for target in targets if target['native_kind']==args.kind]
    for path in dict.fromkeys(paths):
        relative=path.relative_to(source);destination=workspace/relative
        destination.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,destination)
        copied[str(relative)]=digest(path);assert digest(destination)==copied[str(relative)]
    write(out/'copied-inputs.json',{'source':str(source),'sha256':copied,
        'total_bytes':sum((source/p).stat().st_size for p in copied)})
    from apps.lab.server import LabHTTPServer
    from apps.lab.service import LabService
    from apps.research.native_project_actions import NativeProjectActions
    from apps.research.desktop import launch_tool
    from caelab.workbench_client import Client
    tools=ROOT/'runs/prepost-session-20261008-01/tools'
    freecad=tools/'FreeCAD_1.1.4-Windows-x86_64-py311/bin/FreeCAD.exe'
    paraview=tools/'ParaView-6.2.0-Windows-Python3.12-msvc2017-AMD64/bin/paraview.exe'
    assert freecad.is_file() and paraview.is_file()
    server=LabHTTPServer(LabService(workspace),0,workbench_config={'desktop':{
        'freecad_executable':str(freecad),'paraview_executable':str(paraview)}})
    thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.02},daemon=True);thread.start()
    client=Client(f'http://127.0.0.1:{server.server_port}')
    jobs={row['id'] for row in server.workbench.manager.list()}
    def forbidden(*a,**k):raise AssertionError('Owner reuse cannot submit a calculation')
    server.workbench.submit=server.workbench.manager.submit=forbidden
    for owner in server.workbench.research_owners():owner.submit=forbidden
    real_spawn=subprocess.Popen;processes=[];records=[];current={};activation_limits=[]
    def spawn(arguments,*a,**kw):
        name=Path(str(arguments[0])).name.lower() if isinstance(arguments,list) else ''
        if name in {'freecad.exe','paraview.exe'}:
            case=current['case'];environment=dict(kw.get('env',os.environ),B81_NATIVE_CASE=str(case),B81_REPO=str(ROOT))
            kw['env']=environment
            if name=='freecad.exe':
                original=Path(arguments[-1]);wrapper=case/'probe.FCMacro'
                wrapper.write_text(original.read_text(encoding='utf-8')+'\n'+PRE,encoding='utf-8')
                arguments=[*arguments[:-1],str(wrapper)]
            else:
                script=case/'probe.py';script.write_text(POST,encoding='utf-8')
                arguments=[('--script='+str(script)) if str(value).startswith('--script=') else value for value in arguments]
            process=real_spawn(arguments,*a,**kw);processes.append(process);return process
        return real_spawn(arguments,*a,**kw)
    subprocess.Popen=spawn
    def wait(condition,label,seconds=50):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            failures=list(out.glob('*/failed.txt'))
            if failures:raise AssertionError(failures[0].read_text(encoding='utf-8'))
            if condition():return
            time.sleep(.15)
        raise AssertionError(label+' did not settle')
    try:
        actions=NativeProjectActions(client)
        for target in targets:
            kind=target['native_kind'];head=json.loads((workspace/target['head_file']).read_text(encoding='utf-8'))
            request={'reference':head['reference'],'intent':'working','target_id':target['target_id'],
                'expected_head':{'generation':head['head_generation'],'reference':head['reference']},
                'selection':None,'allow_partial':False}
            first=None
            for cycle in (1,2):
                case=out/(kind+'-'+str(cycle));case.mkdir();current['case']=case
                count=len(processes);opened=actions.open(deepcopy(request),command_id=cid())
                write(case/'initial-open.json',opened)
                open_id=opened['open_id'];wait(lambda:actions.check_open(open_id)['status']=='OPENED',kind+' opened')
                wait(lambda:(case/'ready.json').exists(),kind+' ready')
                owner_id=actions.check_open(open_id)['owner_document_id']
                assert owner_id==head['working_document_id'] and len(processes)==count+1
                original=client.document_read(owner_id);process=processes[-1]
                if cycle==1:
                    first={'open_id':open_id,'owner':owner_id,'session':original['session_id'],'pid':process.pid}
                    command_id=cid();repeat=actions.open(deepcopy(request),command_id=command_id)
                    assert repeat['reuse_existing'] is True and repeat['open_id']==open_id and repeat['owner_document_id']==owner_id
                    activation='C'+hashlib.sha256((command_id+':activate').encode()).hexdigest()[:40]
                    wait(lambda:client.command_status(activation)['state']=='SUCCEEDED',kind+' repeat activation')
                    activation_receipt=client.command_status(activation)
                    actual=activation_receipt.get('outcome',{}).get('result',{}).get('result',{})
                    if actual.get('status')=='NOT_PERFORMED':activation_limits.append({'kind':kind,'path':'repeat','native':actual})
                    live=launch_tool(client,kind,document_id=owner_id)
                    assert live['status'] in {'ACTIVATED','NOT_PERFORMED'} and live['document_id']==owner_id
                    if live['status']=='NOT_PERFORMED':activation_limits.append({'kind':kind,'path':'live launch_tool','native':live.get('activation')})
                    same=client.document_read(owner_id)
                    assert same['session_id']==original['session_id'] and len(processes)==count+1
                    write(case/'reuse.json',{'first':first,'repeat':repeat,'activation':activation_receipt,'live_launch_tool':live,'pid_count_unchanged':True})
                else:
                    assert open_id!=first['open_id'] and owner_id==first['owner']
                    assert original['session_id']!=first['session'] and process.pid!=first['pid']
                (case/'close.request').write_text('Close exact owned native window without saving',encoding='utf-8')
                def owner_closed():
                    descriptor=client.document_read(owner_id)
                    state={key:descriptor.get(key) for key in ('id','session_id','connected','owner_closed','generation','view_generation')}
                    state['process_exit_code']=process.poll();state['monotonic']=time.monotonic()
                    write(case/'close-owner-state.json',state)
                    return descriptor.get('owner_closed') is True
                wait(owner_closed,kind+' accepted owner close')
                wait(lambda:process.poll() is not None,kind+' process exit',seconds=20)
                closed=actions.check_open(open_id);assert closed['status']=='CLOSED'
                events=[json.loads(line) for line in (case/'close-events.jsonl').read_text(encoding='utf-8').splitlines()] if (case/'close-events.jsonl').exists() else []
                if kind=='post':
                    assert any(e['event']=='gate_decision' and e['decision']=='allow' for e in events)
                    assert any(e['event']=='native_forward_message' and e['message']==0x0082 for e in events)
                record={'kind':kind,'cycle':cycle,'opened':opened,'descriptor':original,'closed':closed,
                    'pid':process.pid,'exit_code':process.returncode,'native_window_close':(case/'close-dispatched.json').exists(),
                    'close_events':events,'discard_choice':json.loads((case/'discard-choice.json').read_text(encoding='utf-8')) if (case/'discard-choice.json').exists() else None}
                assert record['native_window_close'];records.append(record);write(case/'record.json',record)
        assert len(processes)==2*len(targets) and all(p.poll() is not None for p in processes)
        assert {row['id'] for row in server.workbench.manager.list()}==jobs
        assert all(digest(source/p)==sha and digest(workspace/p)==sha for p,sha in copied.items())
        write(out/'result.json',{'status':'PASS_EXACT_WORKING_NATIVE_REUSE_CLOSE_REOPEN','scope':args.kind,'records':records,
            'activation_limits':activation_limits,'foreground_activation_pass':not activation_limits,
            'original_and_copied_pins_unchanged':True,'new_jobs':0,'new_solver_provider':0,'native_edits_saves_captures':0,
            'native_spawn_count':len(processes),'physical_OS_input':False,'geometry_render_claim':False,
            'reused_existing_negative_tests':'tests/test_native_project_actions.py:199,276',
            'source_sha256':{str(p.relative_to(ROOT)):digest(p) for p in [Path(__file__).resolve(),ROOT/'apps/research/native_project_actions.py',ROOT/'apps/research/desktop.py']}})
        print('B81_EXACT_WORKING_NATIVE_REUSE_OK',flush=True)
    except BaseException as error:
        write(out/'failure.json',{'status':'INCOMPLETE_NATIVE_OWNER_CHECK','error':str(error),
            'accepted_close_records':records,'activation_limits':activation_limits,
            'native_processes_before_finally':[{'pid':p.pid,'exit_code':p.poll()} for p in processes],
            'original_and_copied_pins_unchanged':all(digest(source/p)==sha and digest(workspace/p)==sha for p,sha in copied.items()),
            'new_jobs':len({row['id'] for row in server.workbench.manager.list()}-jobs)})
        raise
    finally:
        subprocess.Popen=real_spawn
        for process in processes:
            if process.poll() is None:
                process.terminate()
                try:process.wait(8)
                except subprocess.TimeoutExpired:process.kill();process.wait(8)
        server.shutdown();server.server_close();thread.join(3);server.workbench.shutdown()
        write(out/'cleanup.json',{'native_pids':[p.pid for p in processes],'all_closed':all(p.poll() is not None for p in processes)})


if __name__=='__main__':main()
