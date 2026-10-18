"""Bounded installed native Data activation using an existing saved Data case.

Run under native_check.py. No acceptance workflow environment reaches LabPlot;
normal installed Data, real HTTP/local IPC and targeted Windows close events run.
"""
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM','windows')
from PySide6.QtWidgets import QApplication
from apps.lab.server import LabHTTPServer,LabHandler
from apps.lab.service import LabService
from apps.research import desktop
from apps.research.native_data_runtime import installed_runtime
from apps.research.result_return import activate_existing,send_message,service_identity,_route,_lock
from caelab.storage import canonical_hash
from caelab.workbench_client import Client

user=ctypes.windll.user32
user.GetWindowRect.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.RECT)]
user.PostMessageW.argtypes=[wintypes.HWND,wintypes.UINT,wintypes.WPARAM,wintypes.LPARAM]
user.IsWindow.argtypes=[wintypes.HWND]
user.SetForegroundWindow.argtypes=[wintypes.HWND]
user.SetWindowPos.argtypes=[wintypes.HWND,wintypes.HWND,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,wintypes.UINT]
CALLBACK=ctypes.WINFUNCTYPE(wintypes.BOOL,wintypes.HWND,wintypes.LPARAM)


def windows(pid):
    rows=[]
    @CALLBACK
    def collect(hwnd,_):
        owner=wintypes.DWORD();user.GetWindowThreadProcessId(hwnd,ctypes.byref(owner))
        if owner.value==pid and user.IsWindowVisible(hwnd):
            title=ctypes.create_unicode_buffer(1024);user.GetWindowTextW(hwnd,title,1024)
            if title.value:rows.append({'hwnd':int(hwnd),'title':title.value})
        return True
    user.EnumWindows(collect,0);return rows


def capture(hwnd,path):
    """Capture only this owned native window, with its actual Windows font/render."""
    from PIL import Image
    time.sleep(.3)  # Allow the native event loop to finish the requested resize.
    rect=wintypes.RECT();assert user.GetWindowRect(hwnd,ctypes.byref(rect))
    width,height=rect.right-rect.left,rect.bottom-rect.top
    gdi=ctypes.windll.gdi32
    user.GetWindowDC.argtypes=[wintypes.HWND];user.GetWindowDC.restype=wintypes.HDC
    user.ReleaseDC.argtypes=[wintypes.HWND,wintypes.HDC]
    user.PrintWindow.argtypes=[wintypes.HWND,wintypes.HDC,wintypes.UINT]
    gdi.CreateCompatibleDC.argtypes=[wintypes.HDC];gdi.CreateCompatibleDC.restype=wintypes.HDC
    gdi.CreateCompatibleBitmap.argtypes=[wintypes.HDC,ctypes.c_int,ctypes.c_int];gdi.CreateCompatibleBitmap.restype=wintypes.HBITMAP
    gdi.SelectObject.argtypes=[wintypes.HDC,wintypes.HGDIOBJ];gdi.SelectObject.restype=wintypes.HGDIOBJ
    gdi.DeleteDC.argtypes=[wintypes.HDC];gdi.DeleteObject.argtypes=[wintypes.HGDIOBJ]
    gdi.GetDIBits.argtypes=[wintypes.HDC,wintypes.HBITMAP,wintypes.UINT,wintypes.UINT,ctypes.c_void_p,ctypes.c_void_p,wintypes.UINT]
    class Header(ctypes.Structure):
        _fields_=[('size',wintypes.DWORD),('width',wintypes.LONG),('height',wintypes.LONG),('planes',wintypes.WORD),('bits',wintypes.WORD),('compression',wintypes.DWORD),('image_size',wintypes.DWORD),('x',wintypes.LONG),('y',wintypes.LONG),('colors',wintypes.DWORD),('important',wintypes.DWORD)]
    dc=user.GetWindowDC(hwnd);memory=gdi.CreateCompatibleDC(dc);bitmap=gdi.CreateCompatibleBitmap(dc,width,height);old=gdi.SelectObject(memory,bitmap)
    try:
        assert user.PrintWindow(hwnd,memory,2),'Native window render could not be captured'
        info=Header(ctypes.sizeof(Header),width,-height,1,32,0,0,0,0,0,0)
        bits=ctypes.create_string_buffer(width*height*4)
        assert gdi.GetDIBits(memory,bitmap,0,height,bits,ctypes.byref(info),0)==height
        Image.frombuffer('RGB',(width,height),bits.raw,'raw','BGRX',0,1).save(path)
    finally:gdi.SelectObject(memory,old);gdi.DeleteObject(bitmap);gdi.DeleteDC(memory);user.ReleaseDC(hwnd,dc)


def dialog_buttons(hwnd):
    """Read native accessibility names/bounds; never infer a button from tab order."""
    script='''[Console]::OutputEncoding=New-Object System.Text.UTF8Encoding
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$root=[System.Windows.Automation.AutomationElement]::FromHandle([IntPtr]HWND)
$condition=New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty,[System.Windows.Automation.ControlType]::Button)
$rows=@($root.FindAll([System.Windows.Automation.TreeScope]::Descendants,$condition) | ForEach-Object { @{name=$_.Current.Name; x=$_.Current.BoundingRectangle.X; y=$_.Current.BoundingRectangle.Y; width=$_.Current.BoundingRectangle.Width; height=$_.Current.BoundingRectangle.Height} })
ConvertTo-Json -InputObject $rows -Compress
'''.replace('HWND',str(hwnd))
    result=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',script],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=15)
    assert result.returncode==0,result.stderr
    return json.loads(result.stdout)


def accessible_names(hwnd):
    script='''[Console]::OutputEncoding=New-Object System.Text.UTF8Encoding
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$root=[System.Windows.Automation.AutomationElement]::FromHandle([IntPtr]HWND)
$names=@($root.FindAll([System.Windows.Automation.TreeScope]::Descendants,[System.Windows.Automation.Condition]::TrueCondition) | ForEach-Object { $_.Current.Name } | Where-Object { $_ })
ConvertTo-Json -InputObject $names -Compress
'''.replace('HWND',str(hwnd))
    result=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',script],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=15)
    assert result.returncode==0,result.stderr
    return json.loads(result.stdout)


def click_button(hwnd,button):
    point=wintypes.POINT(round(button['x']+button['width']/2),round(button['y']+button['height']/2))
    user.ScreenToClient.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.POINT)];user.ScreenToClient(hwnd,ctypes.byref(point))
    packed=(point.y<<16)|(point.x&65535)
    user.PostMessageW(hwnd,0x0201,1,packed);user.PostMessageW(hwnd,0x0202,0,packed)


def wait(predicate,timeout=60):
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        value=predicate()
        if value:return value
        QApplication.processEvents();time.sleep(.05)
    raise TimeoutError('Exact native Data owner did not settle')


def main(case_path,out_path):
    app=QApplication.instance() or QApplication([])
    case=json.loads(Path(case_path).read_text(encoding='utf-8'));assert case['kind']=='data'
    out=Path(out_path).resolve();out.mkdir(parents=True,exist_ok=False)
    source=Path(case['workspace']).resolve();services=[];processes=[];record={};probe_timers=[]
    runtime=installed_runtime();assert runtime
    (out/'runtime-used.json').write_text(json.dumps({k:str(v) for k,v in runtime.items()},indent=2),encoding='utf-8')
    shutil.copy2(runtime['root']/'caelab-build-manifest.json',out/'runtime-build-manifest.json')
    pins=['native/data_labplot/CaelabDataBridge.h','apps/research/result_return.py','apps/research/desktop.py',
        'tests/check_native_data_owner_windows.py']
    import hashlib
    def source_hashes():return {name:hashlib.sha256(Path(name).read_bytes()).hexdigest() for name in pins}
    launched_source=source_hashes()
    (out/'source-launch.json').write_text(json.dumps(launched_source,indent=2),encoding='utf-8')
    def service(path):
        shutil.copytree(source,path)
        server=LabHTTPServer(LabService(path),0)
        if case.get('absence_probe_race') and not services:
            class ProbeRaceHandler(LabHandler):
                def do_GET(self):
                    if (self.path=='/api/workbench/documents/'+case['document_id'] and
                            not self.headers.get('User-Agent','').startswith('Python-urllib') and not probe_timers):
                        name,path=_route(service_identity(f'http://127.0.0.1:{server.server_port}'),case['document_id'])
                        lease=_lock(path);assert lease.tryLock(0)
                        (out/'absence-probe.json').write_text(json.dumps({'server_name':name,'held_ms':400,'native_user_agent':self.headers.get('User-Agent','')}),encoding='utf-8')
                        timer=threading.Timer(.4,lease.unlock);timer.daemon=True;probe_timers.append((timer,lease));timer.start()
                    super().do_GET()
            server.RequestHandlerClass=ProbeRaceHandler
        thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.02},daemon=True);thread.start();services.append((server,thread))
        def forbidden(*a,**k):raise AssertionError('Opening Data cannot execute an import/provider/calculation')
        server.workbench.submit=server.workbench.manager.submit=forbidden
        for owner in server.workbench.research_owners():owner.submit=forbidden
        return server.workbench,Client(f'http://127.0.0.1:{server.server_port}')
    spawn=subprocess.Popen
    def tracked(*a,**k):
        child=spawn(*a,**k);processes.append(child);return child
    def activated(client):
        try:
            receipt=activate_existing(client,case['document_id'],kind='data')
            return receipt if receipt['status']=='ACTIVATED' else None
        except RuntimeError:return None
    def main_window(pid):return next((r for r in windows(pid) if 'labplot' in r['title'].lower()),None)
    try:
        wb,client=service(out/'한글 공백 자료 보관소');wb2,client2=service(out/'다른 보관소 같은 자료')
        before=client.document_read(case['document_id']);before2=client2.document_read(case['document_id'])
        jobs=[{j['id'] for j in w.manager.list()} for w in (wb,wb2)]
        with patch.object(desktop.subprocess,'Popen',tracked), patch.dict(os.environ,{
                'XDG_CONFIG_HOME':str(out/'private-config'),'XDG_DATA_HOME':str(out/'private-data')}):
            first=desktop.launch_native_data(client,document_id=before['id']);wait(lambda:activated(client),15 if case.get('first_only') else 60)
            first_window=wait(lambda:main_window(first['pid']));hwnd=first_window['hwnd']
            if case.get('first_only'):
                assert probe_timers,'Native HTTP did not enter the deliberate transient absence-probe boundary'
                (out/'result.json').write_text(json.dumps({'status':'PASS_NATIVE_TRANSIENT_ABSENCE_PROBE','first':first,'window':first_window,'probe_count':len(probe_timers),'new_jobs':0},ensure_ascii=False,indent=2),encoding='utf-8')
                return
            if case.get('local_edit_only'):
                user.SetWindowPos(hwnd,0,50,50,1280,820,0x0040);capture(hwnd,out/'local-before.png')
                buttons=dialog_buttons(hwnd)
                exclusion=next(row for row in buttons if row['name'].replace('&','').strip()=='선택 행 계산 제외')
                click_button(hwnd,exclusion);time.sleep(.3)
                edited_names=accessible_names(hwnd)
                assert any('계산 제외: 1행' in name for name in edited_names),edited_names
                capture(hwnd,out/'local-edited.png')
                count=len(processes);second=desktop.launch_native_data(client,document_id=before['id'])
                assert second['status']=='ACTIVATED' and len(processes)==count
                names_after_activation=accessible_names(hwnd)
                assert any('계산 제외: 1행' in name for name in names_after_activation)
                user.PostMessageW(hwnd,0x0010,0,0)
                modal=wait(lambda:next((r for r in windows(first['pid']) if r['hwnd']!=hwnd),None),10)
                user.PostMessageW(modal['hwnd'],0x0100,0x1b,0);user.PostMessageW(modal['hwnd'],0x0101,0x1b,0)
                wait(lambda:not user.IsWindow(modal['hwnd']),10)
                assert activated(client) and user.IsWindow(hwnd)
                names_after_cancel=accessible_names(hwnd)
                assert any('계산 제외: 1행' in name for name in names_after_cancel)
                capture(hwnd,out/'local-after-activation-cancel.png')
                after=client.document_read(before['id'])
                for key in ('draft','generation','input_revision','saved_revision','runs'):assert after[key]==before[key],key
                assert {j['id'] for j in wb.manager.list()}==jobs[0]
                (out/'result.json').write_text(json.dumps({'status':'PASS_NATIVE_LOCAL_EXCLUSION_PRESERVED_ACTIVATION_AND_CANCEL',
                    'first':first,'second':second,'accessibility_before_activation':edited_names,
                    'accessibility_after_activation':names_after_activation,'accessibility_after_cancel':names_after_cancel,
                    'source_unchanged':True,'new_jobs':0,'data_updates':0},ensure_ascii=False,indent=2),encoding='utf-8')
                return
            count=len(processes);second=desktop.launch_native_data(client,document_id=before['id'])
            assert second['status']=='ACTIVATED' and len(processes)==count
            message={'version':1,'operation':'activate','service':service_identity(client.url),'target_id':before['id'],'session_id':'Sforged'}
            try:send_message(message)
            except RuntimeError as error:forged=str(error)
            else:raise AssertionError('Forged session was activated')
            assert activated(client)
            user.SetWindowPos(hwnd,0,50,50,1280,820,0x0040);capture(hwnd,out/'data-normal.png')
            user.SetWindowPos(hwnd,0,50,50,960,720,0x0040);capture(hwnd,out/'data-narrow.png')
            user.PostMessageW(hwnd,0x0010,0,0)
            modal=wait(lambda:next((r for r in windows(first['pid']) if r['hwnd']!=hwnd),None),10)
            capture(modal['hwnd'],out/'data-close-cancel.png')
            user.PostMessageW(modal['hwnd'],0x0100,0x1b,0);user.PostMessageW(modal['hwnd'],0x0101,0x1b,0)
            wait(lambda:not user.IsWindow(modal['hwnd']),10)
            assert user.IsWindow(hwnd) and activated(client)
            cancelled={'modal':modal,'main_window_preserved':True,'activation_after_cancel':activated(client)}
            other=desktop.launch_native_data(client2,document_id=before['id']);wait(lambda:activated(client2))
            assert other['pid']!=first['pid'] and before['session_id']!=before2['session_id']
            # Finish the same real close dialog using its standard don't-save accelerator.
            user.PostMessageW(hwnd,0x0010,0,0)
            modal2=wait(lambda:next((r for r in windows(first['pid']) if r['hwnd']!=hwnd),None),10)
            record.update(close_modal=modal2)
            buttons=dialog_buttons(modal2['hwnd']);record['close_buttons']=buttons
            (out/'close-buttons.json').write_text(json.dumps(buttons,ensure_ascii=False,indent=2),encoding='utf-8')
            discard=next(row for row in buttons if row['name'].replace('&','').rsplit('(',1)[0].strip().lower() in {"don't save",'do not save','저장 안 함','저장하지 않음'})
            click_button(modal2['hwnd'],discard)
            wait(lambda:not user.IsWindow(hwnd),12)
            first_process=next(p for p in processes if p.pid==first['pid']);first_process.wait(10)
            reopened=desktop.launch_native_data(client,document_id=before['id']);wait(lambda:activated(client))
            assert reopened['pid']!=first['pid']
            for current,original in ((client,before),(client2,before2)):
                after=current.document_read(original['id'])
                for key in ('draft','generation','input_revision','saved_revision','runs'):assert after[key]==original[key],key
            assert [{j['id'] for j in w.manager.list()} for w in (wb,wb2)]==jobs
            name,lock=_route(service_identity(client.url),before['id'])
            record.update(status='PASS_NATIVE_DATA_EXACT_OWNER_REUSE_CANCEL_SEPARATE_STORE_CLOSED_REOPEN',
                runtime={k:str(v) for k,v in runtime.items()},first=first,second=second,other=other,reopened=reopened,
                first_window=first_window,cancelled_close=cancelled,forged_session_rejected=forged,
                python_route={'server_name':name,'lock':str(lock)},document_id=before['id'],draft_sha256=canonical_hash(before['draft']),
                source_unchanged=True,new_jobs=0,provider_calls=0,native_calculations=0,native_api_and_targeted_window_events=True)
            (out/'result.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
            print(record['status'],flush=True)
    except BaseException as error:
        for process in processes:
            for row in windows(process.pid):capture(row['hwnd'],out/('failed-window-'+str(process.pid)+'-'+str(row['hwnd'])+'.png'))
        (out/'failure.json').write_text(json.dumps({'error':repr(error),'windows':{p.pid:windows(p.pid) for p in processes},**record},ensure_ascii=False,indent=2),encoding='utf-8');raise
    finally:
        for child in processes:
            if child.poll() is None:child.terminate();child.wait(10)
        for timer,lease in probe_timers:timer.join(2);lease.unlock()
        for server,thread in reversed(services):server.shutdown();server.server_close();thread.join(3);server.workbench.shutdown()
        (out/'cleanup.json').write_text(json.dumps({'pids':[p.pid for p in processes],'all_closed':all(p.poll() is not None for p in processes)}),encoding='utf-8')
        (out/'source-end.json').write_text(json.dumps(source_hashes(),indent=2),encoding='utf-8')


if __name__=='__main__':main(*sys.argv[1:])
