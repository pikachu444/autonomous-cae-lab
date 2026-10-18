"""One bounded dirty A / already-open B / native Project lifecycle correction."""
import hashlib
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

import check_native_data_owner_windows as ui
from apps.lab.server import LabHTTPServer,LabHandler
from apps.lab.service import LabService
from apps.research import desktop
from apps.research.native_data_runtime import installed_runtime
from apps.research.result_return import activate_existing
from caelab.workbench_client import Client
from PySide6.QtWidgets import QApplication


def main(case_path,out_path):
    app=QApplication.instance() or QApplication([])
    case=json.loads(Path(case_path).read_text(encoding='utf-8'))
    out=Path(out_path).resolve();out.mkdir(parents=True,exist_ok=False)
    workspace=out/'한글 두 자료';shutil.copytree(case['workspace'],workspace)
    server=LabHTTPServer(LabService(workspace),0,workbench_config={'input_roots':{'public':str(Path('examples/material-tests').resolve())}})
    native_reads=[]
    class NativeReadHandler(LabHandler):
        def do_GET(self):
            if not self.headers.get('User-Agent','').startswith('Python-urllib'):
                native_reads.append(self.path)
            super().do_GET()
    server.RequestHandlerClass=NativeReadHandler
    thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.02},daemon=True);thread.start()
    client=Client(f'http://127.0.0.1:{server.server_port}');children=[];spawn=subprocess.Popen;record={}
    pins=['native/data_labplot/CaelabDataBridge.h','native/data_labplot/patches/0005-connect-exact-core-save.patch',
        'apps/research/result_return.py','apps/research/desktop.py','tests/check_native_data_owner_lifecycle_windows.py']
    def hashes():return {name:hashlib.sha256(Path(name).read_bytes()).hexdigest() for name in pins}
    (out/'source-launch.json').write_text(json.dumps(hashes(),indent=2),encoding='utf-8')
    runtime=installed_runtime();assert runtime
    (out/'runtime-used.json').write_text(json.dumps({k:str(v) for k,v in runtime.items()},indent=2),encoding='utf-8')
    def forbidden(*a,**k):raise AssertionError('Owner lifecycle cannot execute a calculation/import/provider')
    server.workbench.submit=server.workbench.manager.submit=forbidden
    for owner in server.workbench.research_owners():owner.submit=forbidden
    def tracked(*a,**k):
        process=spawn(*a,**k);children.append(process);return process
    def active(identifier):
        try:
            receipt=activate_existing(client,identifier,kind='data')
            return receipt if receipt['status']=='ACTIVATED' else None
        except RuntimeError:return None
    def main_window(pid):return next((r for r in ui.windows(pid) if 'labplot' in r['title'].lower()),None)
    def modal(pid,hwnd):return next((r for r in ui.windows(pid) if r['hwnd']!=hwnd),None)
    def press(hwnd,key):ui.user.PostMessageW(hwnd,0x0100,key,0);ui.user.PostMessageW(hwnd,0x0101,key,0)
    def click_named(hwnd,name):
        buttons=ui.dialog_buttons(hwnd)
        row=next(row for row in buttons if row['name'].replace('&','').strip()==name)
        ui.click_button(hwnd,row);time.sleep(.15)
    uia=out/'native-uia.ps1'
    uia.write_text(r'''param([long]$Handle,[int]$OwnerPid,[string]$Name,[string]$Value,[string]$Operation)
[Console]::OutputEncoding=New-Object System.Text.UTF8Encoding
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$root=[System.Windows.Automation.AutomationElement]::FromHandle([IntPtr]$Handle)
 $roots=@($root)+@([System.Windows.Automation.AutomationElement]::RootElement.FindAll([System.Windows.Automation.TreeScope]::Children,(New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ProcessIdProperty,$OwnerPid))))
 $found=$null
 foreach($hostRoot in $roots) { foreach($element in $hostRoot.FindAll([System.Windows.Automation.TreeScope]::Descendants,[System.Windows.Automation.Condition]::TrueCondition)) {
  if (($element.Current.Name.Replace('&','').Trim() -replace '\([A-Za-z]\)$','') -eq $Name) { $found=$element; break }
 } if($found){break} }
 if(!$found) { throw ('Native action unavailable: '+$Name) }
 $invoke=$null
 if($Operation -eq 'point') { @{x=$found.Current.BoundingRectangle.X;y=$found.Current.BoundingRectangle.Y;width=$found.Current.BoundingRectangle.Width;height=$found.Current.BoundingRectangle.Height}|ConvertTo-Json -Compress }
 elseif($found.TryGetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern,[ref]$invoke)) { $invoke.Invoke() }
 else { $found.GetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern).Expand() }
''',encoding='utf-8-sig')
    def open_native_menu_action(hwnd,pid,menu_name,action_name):
        result=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-File',str(uia),str(hwnd),str(pid),menu_name,'__unused__','point'],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=15)
        assert result.returncode==0,result.stderr
        ui.click_button(hwnd,json.loads(result.stdout));time.sleep(.3)
        popups=[]
        @ui.CALLBACK
        def collect(handle,_):
            owner=wintypes.DWORD();ui.user.GetWindowThreadProcessId(handle,ctypes.byref(owner))
            if owner.value==pid and ui.user.IsWindowVisible(handle):
                name=ctypes.create_unicode_buffer(512);ui.user.GetClassNameW(handle,name,512)
                if 'Popup' in name.value:popups.append(int(handle))
            return True
        ui.user.EnumWindows(collect,0)
        assert popups,'Native Data menu did not open'
        result=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-File',str(uia),str(hwnd),str(pid),action_name,'__unused__','point'],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=15)
        assert result.returncode==0,result.stderr
        ui.click_button(popups[0],json.loads(result.stdout))
    def close_modal(pid,main_hwnd):
        for row in ui.windows(pid):
            if row['hwnd']==main_hwnd:continue
            try:
                names={button['name'].replace('&','').rsplit('(',1)[0].strip().lower() for button in ui.dialog_buttons(row['hwnd'])}
            except AssertionError:continue
            if names & {"don't save",'do not save','저장 안 함','저장하지 않음'} and names & {'cancel','취소'}:return row
    def file_controls(hwnd):
        # Admit a file dialog by its live child structure, never by its title.
        fields=[];controls=[];dialog_rect=wintypes.RECT();ui.user.GetWindowRect(hwnd,ctypes.byref(dialog_rect))
        ui.user.GetDlgCtrlID.argtypes=[wintypes.HWND]
        send=ui.user.SendMessageW;send.argtypes=[wintypes.HWND,wintypes.UINT,wintypes.WPARAM,wintypes.LPARAM];send.restype=wintypes.LPARAM
        @ui.CALLBACK
        def collect(handle,_):
            if not ui.user.IsWindowVisible(handle):return True
            name=ctypes.create_unicode_buffer(128);ui.user.GetClassNameW(handle,name,128)
            rect=wintypes.RECT();ui.user.GetWindowRect(handle,ctypes.byref(rect))
            if name.value=='Edit' and rect.top>dialog_rect.top+(dialog_rect.bottom-dialog_rect.top)//2:
                fields.append(int(handle))
            if name.value=='Button':
                label=ctypes.create_unicode_buffer(512);send(handle,0x000d,512,ctypes.cast(label,ctypes.c_void_p).value)
                controls.append({'hwnd':int(handle),'id':ui.user.GetDlgCtrlID(handle),'name':label.value,'enabled':bool(ui.user.IsWindowEnabled(handle))})
            return True
        ui.user.EnumChildWindows(hwnd,collect,0)
        return fields,controls
    def file_modal(pid,main_hwnd):
        for row in ui.windows(pid):
            if row['hwnd']==main_hwnd:continue
            fields,controls=file_controls(row['hwnd'])
            if len(fields)==1 and any(button['id']==1 and button['enabled'] for button in controls):return row
    def file_dialog(hwnd,pid,path):
        fields,controls=ui.wait(lambda:(lambda pair:pair if len(pair[0])==1 and any(button['id']==1 and button['enabled'] for button in pair[1]) else None)(file_controls(hwnd)),10)
        send=ui.user.SendMessageW
        value=ctypes.create_unicode_buffer(str(path));send(fields[0],0x000c,0,ctypes.cast(value,ctypes.c_void_p).value)
        current=ctypes.create_unicode_buffer(32768);send(fields[0],0x000d,32768,ctypes.cast(current,ctypes.c_void_p).value)
        assert current.value==str(path),(current.value,str(path))
        record.setdefault('file_dialogs',[]).append({'hwnd':hwnd,'filename_hwnd':fields[0],'filename':current.value,'buttons':controls,'uia_buttons':ui.dialog_buttons(hwnd)})
        (out/'file-dialogs.json').write_text(json.dumps(record['file_dialogs'],ensure_ascii=False,indent=2),encoding='utf-8')
        submit=next(row for row in controls if row['id']==1 and row['enabled'])
        ui.user.SetForegroundWindow(hwnd)
        send(submit['hwnd'],0x00f5,0,0)  # BM_CLICK on the real native default button.
    try:
        a=client.document_read(case['document_id'])
        if case.get('direct_project'):
            project=out/'정확 B 저장 자료.lml';shutil.copy2(case['direct_project'],project)
            assert hashlib.sha256(project.read_bytes()).hexdigest()==case['project_sha256']
            jobs={row['id'] for row in server.workbench.manager.list()}
            with patch.object(desktop.subprocess,'Popen',tracked),patch.dict(os.environ,{'XDG_CONFIG_HOME':str(out/'config'),'XDG_DATA_HOME':str(out/'data')}):
                first=desktop.launch_native_data(client,document_id=a['id']);ui.wait(lambda:active(a['id']))
                main=ui.wait(lambda:main_window(first['pid']))
                duplicate=desktop.launch_native_data(client,project=project)
                extra=next(child for child in children if child.pid==duplicate['pid'])
                ui.wait(lambda:extra.poll() is not None,35)
                assert extra.returncode==0 and ui.windows(extra.pid)==[]
                assert ui.user.IsWindow(main['hwnd']) and active(a['id'])
                after=client.document_read(a['id'])
                for key in ('draft','generation','input_revision','saved_revision','runs'):assert after[key]==a[key]
                assert hashlib.sha256(project.read_bytes()).hexdigest()==case['project_sha256']
                assert {row['id'] for row in server.workbench.manager.list()}==jobs
                (out/'result.json').write_text(json.dumps({'status':'PASS_NATIVE_DATA_FRESH_FILE_FORWARD_CLOSED_DUPLICATE',
                    'first':first,'file_startup':duplicate,'startup_exit_code':extra.returncode,'current_document_id':a['id'],
                    'project_sha256':case['project_sha256'],'source_unchanged':True,'new_jobs':0},ensure_ascii=False,indent=2),encoding='utf-8')
                return
        if case.get('existing_b'):
            b=client.document_read(case['existing_b'])
        else:
            raw=client.register_local_input('public','axial.csv')
            b=client.document_open(kind='data',title='B 선택 자료',draft={'data_id':raw['id'],'mapping':a['draft']['mapping']})
            b=client.document_command(b['id'],'document.save',{},session_id=b['session_id'],expected_generation=b['generation'])['document']
        jobs={row['id'] for row in server.workbench.manager.list()}
        with patch.object(desktop.subprocess,'Popen',tracked),patch.dict(os.environ,{'XDG_CONFIG_HOME':str(out/'config'),'XDG_DATA_HOME':str(out/'data')}):
            first=desktop.launch_native_data(client,document_id=a['id']);ui.wait(lambda:active(a['id']))
            second=desktop.launch_native_data(client,document_id=b['id']);ui.wait(lambda:active(b['id']))
            aw=ui.wait(lambda:main_window(first['pid']));bw=ui.wait(lambda:main_window(second['pid']));ah,bh=aw['hwnd'],bw['hwnd']
            ui.user.SetWindowPos(ah,0,30,30,1280,820,0x0040);time.sleep(.4)
            click_named(ah,'선택 행 계산 제외')
            assert any('계산 제외: 1행' in name for name in ui.accessible_names(ah))
            ui.capture(ah,out/'a-dirty-before.png')
            if not case.get('core_forward_already_verified'):
                open_native_menu_action(ah,first['pid'],'자료','자료 문서 열기…')
                choice=ui.wait(lambda:next((row for row in ui.windows(first['pid']) if row['hwnd']!=ah and row['title'] in {'자료 열기','자료 열기 - LabPlot'}),None),10)
                # Server's current explicit list is the same list read by openCoreData.
                options=[row for row in client.documents()['documents'] if row['kind']=='data'];index=next(i for i,row in enumerate(options) if row['id']==b['id'])
                press(choice['hwnd'],0x24)
                for _ in range(index):press(choice['hwnd'],0x28)
                mark=len(native_reads)
                press(choice['hwnd'],0x0d);time.sleep(.6)
                unexpected=modal(first['pid'],ah)
                if unexpected:
                    assert unexpected['title']=='Save Project - LabPlot',unexpected
                    record['unexpected_b_switch_discard_prompt']=unexpected
                    discard=next(row for row in ui.dialog_buttons(unexpected['hwnd']) if row['name'].replace('&','').rsplit('(',1)[0].strip().lower() in {"don't save",'do not save','저장 안 함','저장하지 않음'})
                    ui.click_button(unexpected['hwnd'],discard);time.sleep(.5)
                record['selected_b_native_reads']=native_reads[mark:]
                assert '/api/workbench/documents/'+b['id'] in native_reads[mark:],'Native Core selection did not read exact B'
                assert active(a['id']),'Opening already-owned B orphaned A activation'
                assert active(b['id'])
                assert any('계산 제외: 1행' in name for name in ui.accessible_names(ah)),'Opening B discarded dirty A'
                assert main_window(first['pid'])['title']==aw['title']
                ui.capture(ah,out/'a-after-core-b.png')
                record['core_b_forward_preserved_a']=True
            # Save B through its existing native/Core save action, then try its .lml from dirty A.
            if case.get('saved_b_file'):
                bfile=Path(case['saved_b_file']);assert bfile.exists()
            else:
                click_named(bh,'자료 저장')
                save_dialog=ui.wait(lambda:file_modal(second['pid'],bh),10);bfile=out/'B 저장 자료.lml';file_dialog(save_dialog['hwnd'],second['pid'],bfile)
                ui.wait(lambda:bfile.exists(),15)
            b_saved=client.document_read(b['id'])
            open_native_menu_action(ah,first['pid'],'파일','저장된 작업 열기…')
            open_dialog=ui.wait(lambda:file_modal(first['pid'],ah),10);file_dialog(open_dialog['hwnd'],first['pid'],bfile);time.sleep(.6)
            assert active(a['id']) and active(b['id'])
            assert any('계산 제외: 1행' in name for name in ui.accessible_names(ah))
            record['lml_b_forward_preserved_a']=True;record['saved_b_file']=str(bfile)
            original=bfile.read_bytes();record['b_file_sha256']=hashlib.sha256(original).hexdigest()
            # File New cancelled leaves A's exact lease and local draft alive.
            open_native_menu_action(ah,first['pid'],'파일','새 작업')
            close_choice=ui.wait(lambda:close_modal(first['pid'],ah),10);press(close_choice['hwnd'],0x1b);time.sleep(.3)
            assert active(a['id']) and any('계산 제외: 1행' in name for name in ui.accessible_names(ah))
            record['cancel_new_preserved_a']=True
            open_native_menu_action(ah,first['pid'],'파일','새 작업')
            close_choice=ui.wait(lambda:close_modal(first['pid'],ah),10)
            discard=next(row for row in ui.dialog_buttons(close_choice['hwnd']) if row['name'].replace('&','').rsplit('(',1)[0].strip().lower() in {"don't save",'do not save','저장 안 함','저장하지 않음'})
            ui.click_button(close_choice['hwnd'],discard);time.sleep(.4)
            assert activate_existing(client,a['id'],kind='data')['status']=='ABSENT','Destroyed A project retained its activation lease'
            reopened=desktop.launch_native_data(client,document_id=a['id']);ui.wait(lambda:active(a['id']))
            assert reopened['pid']!=first['pid']
            assert client.document_read(a['id'])['draft']==a['draft']
            assert client.document_read(b['id'])['draft']==b_saved['draft']
            assert {row['id'] for row in server.workbench.manager.list()}==jobs
            record.update(status='PASS_NATIVE_DATA_DIRTY_A_B_FORWARD_AND_PROJECT_LIFECYCLE',workspace=str(workspace),a=a['id'],b=b['id'],first=first,second=second,reopened=reopened,new_jobs=0,provider_calls=0,local_a_updates=0)
            (out/'result.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
    except BaseException as error:
        win={p.pid:ui.windows(p.pid) for p in children if p.poll() is None}
        for pid,rows in win.items():
            for row in rows:ui.capture(row['hwnd'],out/('failure-'+str(pid)+'-'+str(row['hwnd'])+'.png'))
        (out/'failure.json').write_text(json.dumps({'error':repr(error),'windows':win,**record},ensure_ascii=False,indent=2),encoding='utf-8');raise
    finally:
        for child in children:
            if child.poll() is None:child.terminate();child.wait(10)
        server.shutdown();server.server_close();thread.join(3);server.workbench.shutdown()
        (out/'source-end.json').write_text(json.dumps(hashes(),indent=2),encoding='utf-8')
        (out/'cleanup.json').write_text(json.dumps({'pids':[p.pid for p in children],'all_closed':all(p.poll() is not None for p in children)}),encoding='utf-8')


if __name__=='__main__':main(*sys.argv[1:])
