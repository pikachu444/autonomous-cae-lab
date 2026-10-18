"""Actual local HTTP/Qt; controlled remote adapter, never a live SSH host."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
from copy import deepcopy
import hashlib
import re
import threading
import time
import json
import subprocess
import sys

import pytest
pytest.importorskip('PySide6')
from PySide6.QtCore import Qt,QTimer,QSettings
from PySide6.QtGui import QAction
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from apps.lab.server import LabHTTPServer
from apps.lab.service import LabService
from apps.research.appearance import apply_appearance
from apps.research.remote_execution_dialog import RemoteExecutionDialog,show_remote
from apps.research.runner_window import RunnerWindow
from caelab.workbench_client import Client
from test_remote_execution import ControlledSSH,host,wait


def pump(predicate,app):
    deadline=time.monotonic()+10
    while time.monotonic()<deadline:
        app.processEvents()
        if predicate(): return
        time.sleep(.005)
    raise AssertionError('Qt/HTTP action did not complete')


@pytest.fixture
def live(tmp_path,monkeypatch,request):
    ssh=ControlledSSH(); monkeypatch.setattr('caelab.remote_transport.SSHTransport',lambda config:ssh)
    config=host();config['label']='프로토콜 대역 — 외부 호스트 미실행'
    server=LabHTTPServer(LabService(tmp_path/'store'),0,workbench_config={'remote_hosts':{'public':config}})
    thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.02},daemon=True);thread.start()
    closed=False
    def close_service():
        nonlocal closed
        if closed:return
        closed=True;server.shutdown();server.server_close();thread.join(3)
        assert server.workbench.shutdown(timeout=10)['joined'] and not thread.is_alive()
    request.addfinalizer(close_service)
    client=Client('http://127.0.0.1:'+str(server.server_port));wb=server.workbench
    client._remote_test_server=server
    client._remote_test_settings_path=str(tmp_path/'remote-pending.ini')
    output=os.environ.get('CAELAB_REMOTE_RENDER_DIR')
    client._remote_evidence=None
    if output:
        name=re.sub(r'[^A-Za-z0-9_.-]','_',request.node.name)
        client._remote_evidence=Path(output)/(name+'-'+hashlib.sha256(request.node.name.encode()).hexdigest()[:8])
        client._remote_evidence.mkdir(parents=True,exist_ok=True)
        sources=('apps/research/remote_execution_dialog.py','caelab/remote_execution.py',
                 'caelab/remote_schedulers.py','caelab/remote_transport.py','tests/test_remote_execution_editor.py')
        pins={p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in sources}
        (client._remote_evidence/'source-launch.json').write_text(json.dumps(pins,indent=2),encoding='utf-8')
    monkeypatch.setattr('apps.research.remote_execution_dialog._settings',
        lambda:QSettings(client._remote_test_settings_path,QSettings.Format.IniFormat))
    job=client.submit('batch_export',{'variables':[{'id':'x','unit':'1','lower':0.,'upper':4.}],
        'candidates':[{'x':1.},{'x':3.}], 'case_id':'public-case','label':'공개 하중 비교'})
    wait(wb,job)
    try: yield client,wb,ssh
    finally:
        close_service()
        if client._remote_evidence:
            end={p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in sources}
            (client._remote_evidence/'source-end.json').write_text(json.dumps(end,indent=2),encoding='utf-8')
            (client._remote_evidence/'protocol-log.json').write_text(json.dumps({
                'boundary':'CONTROLLED_SSH_PROTOCOL_REPLAY_NOT_EXTERNAL_HOST',
                'pid':os.getpid(),'qt_platform':QApplication.platformName(),
                'calls':ssh.calls,'jobs':wb.manager.list(),'owned_service_closed':not thread.is_alive(),
                'external_hosts_provider_solver':0,'source_unchanged':pins==end,
                'all_owned_windows_closed':not any(w.isVisible() for w in QApplication.topLevelWidgets())},ensure_ascii=False,indent=2),encoding='utf-8')


def capture(window,client,name):
    if client._remote_evidence:
        for size,suffix in (((1000,720),'normal'),((700,600),'narrow')):
            window.resize(*size);QApplication.processEvents()
            assert (window.width(),window.height())==size
            assert window.grab().save(str(client._remote_evidence/(name+'-'+suffix+'.png')))


def saved_batch_plan(client,wb):
    from caelab.numerical_document import request_draft
    inputs={'variables':[{'id':'x','unit':'1','lower':0.,'upper':4.}],
        'candidates':[{'x':1.},{'x':3.}], 'case_id':'public-case'}
    doc=client.document_open(kind='numerical',title='대역 인수 공개 계획',draft=request_draft({
        'purpose':'외부 호스트 없이 기존 입력 교환 계약 확인','operation':'batch_export',
        'inputs':inputs,'budget':{'evaluations':2}}))
    assert not doc['diagnostics'],doc['diagnostics']
    reply=client.document_command(doc['id'],'numerical.run',{},session_id=doc['session_id'],expected_generation=doc['generation'])
    batch=reply['job'];assert wait(wb,batch)['state']=='SUCCEEDED'
    doc=client.document_read(doc['id'])
    doc=client.document_command(doc['id'],'document.save',{},session_id=doc['session_id'],expected_generation=doc['generation'])['document']
    return doc,batch


def test_actual_http_lost_reply_qt_retry_and_explicit_collection(live):
    client,wb,ssh=live;app=QApplication.instance() or QApplication([]);apply_appearance(app)
    plan,batch=saved_batch_plan(client,wb)
    original_manifest=deepcopy(wb.result(batch['id'])['manifest'])
    original_submit=client.submit; lost=[True]
    def lose_once(*args,**kwargs):
        job=original_submit(*args,**kwargs)
        if lost[0]: lost[0]=False;raise OSError('검사 대역: 제출 응답 유실')
        return job
    client.submit=lose_once
    window=RemoteExecutionDialog(client);window.show()
    try:
        pump(lambda:not window._busy and window.host.count()==1,app)
        assert ssh.calls==[]
        window.batch.setCurrentIndex(window.batch.findData(batch['id']))
        window.threads.setValue(3);window.memory.setValue(2000);window.wall.setValue(123)
        QTest.mouseClick(window.preview_button,Qt.MouseButton.LeftButton);pump(lambda:not window._busy,app)
        assert '후보 2개' in window.message.text() and ssh.calls==[]
        QTest.mouseClick(window.submit_button,Qt.MouseButton.LeftButton);pump(lambda:not window._busy,app)
        assert window._pending and '유실' in window.message.text()
        request_id=window._pending[2]
        QTest.mouseClick(window.submit_button,Qt.MouseButton.LeftButton);pump(lambda:not window._busy,app)
        assert window._pending is None
        job=wb.manager.status(window.selected_job);wait(wb,job)
        assert job['request_id']==request_id and ssh.calls.count('submit')==1 and 'fetch' not in ssh.calls
        original=window.selected_job
        window.action('reconnect');pump(lambda:not window._busy,app);wait(wb,wb.manager.status(window.selected_job))
        assert ssh.calls[-1]=='query' and 'fetch' not in ssh.calls
        window.action('collect');pump(lambda:not window._busy,app);collected=wait(wb,wb.manager.status(window.selected_job))
        assert collected['state']=='SUCCEEDED' and ssh.calls.count('submit')==1 and ssh.calls[-1]=='fetch'
        window.refresh();pump(lambda:not window._busy,app)
        assert (window.threads.value(),window.memory.value(),window.wall.value())==(3,2000,123)
        assert any(row.get('scheduler_id')=='731' for row in window._attempts.values())
        window.table.setFocus();app.processEvents()
        capture(window,client,'collected')
        assert wb.result(collected['id'])['responses']['후보 1 / force']['unit']=='N'
        assert wb.manager.status(original)['operation']=='remote.run'
        assert client.document_read(plan['id'])==plan and wb.result(batch['id'])['manifest']==original_manifest
        calls=list(ssh.calls);jobs=len(wb.manager.list())
        expected=wb.result(collected['id'])['responses']
        child=subprocess.run([sys.executable,'-X','utf8','-c',
            'import json,sys;from caelab.workbench_client import Client;c=Client(sys.argv[1]);'
            'r=c.result(sys.argv[2]);assert r["responses"]==json.loads(sys.argv[3]);'
            'print(json.dumps({"job":sys.argv[2],"responses":r["responses"],"read_only":True}))',
            client.url,collected['id'],json.dumps(expected)],cwd=Path(__file__).resolve().parents[1],
            capture_output=True,text=True,encoding='utf-8',timeout=20)
        assert child.returncode==0,child.stderr
        assert ssh.calls==calls and len(wb.manager.list())==jobs
        if client._remote_evidence:
            (client._remote_evidence/'cold-result.json').write_text(child.stdout,encoding='utf-8')
    finally:
        pump(lambda:not window._busy,app);window.close();app.processEvents()


def test_cancel_preserves_resource_edits_and_reopen_does_not_execute(live):
    client,wb,ssh=live;app=QApplication.instance() or QApplication([])
    run=client.submit('remote.run',{'host_id':'public','batch_job':next(j['id'] for j in wb.manager.list() if j['operation']=='batch_export')},request_id='initial')
    wait(wb,run)
    window=RemoteExecutionDialog(client,selected_job=run['id']);window.show()
    try:
        pump(lambda:not window._busy,app);window.threads.setValue(2);window.wall.setValue(99)
        window.action('cancel');pump(lambda:not window._busy,app);wait(wb,wb.manager.status(window.selected_job))
        assert window.threads.value()==2 and window.wall.value()==99 and 'fetch' not in ssh.calls
        before=list(ssh.calls);window.reject();app.processEvents()
        reopened=RemoteExecutionDialog(client,selected_job=window.selected_job);reopened.show()
        try:
            pump(lambda:not reopened._busy,app);assert ssh.calls==before
            assert reopened.table.rowCount()>=2
        finally:reopened.close();app.processEvents()
    finally:window.close();app.processEvents()


def test_runner_menu_and_unconfigured_dialog_leave_local_execution_independent(live):
    client,wb,ssh=live;app=QApplication.instance() or QApplication([])
    wb.config.pop('remote_hosts')
    window=RemoteExecutionDialog(client);runner=RunnerWindow(client,poll_interval=0)
    try:
        window.show();pump(lambda:not window._busy and bool(window.message.text()),app)
        assert not window.submit_button.isEnabled() and '로컬 실행' in window.message.text() and ssh.calls==[]
        actions=[action.text() for action in runner.findChildren(QAction)]
        assert '원격 실행…' in actions
    finally:
        window.close();runner.close();pump(lambda:not runner._workers,app);app.processEvents()


def test_runner_button_opens_same_collected_responses_and_candidate_table(live,monkeypatch):
    client,wb,ssh=live;app=QApplication.instance() or QApplication([])
    batch=next(j['id'] for j in wb.manager.list() if j['operation']=='batch_export')
    source=client.submit('remote.run',{'host_id':'public','batch_job':batch},request_id='open-run');wait(wb,source)
    result=client.submit('remote.collect',{'source_job':source['id']},request_id='open-collect');wait(wb,result)
    runner=RunnerWindow(client,job_id=result['id'],poll_interval=0);runner.show()
    receipts=[];original_exec=RemoteExecutionDialog.exec
    def executed(dialog):
        code=original_exec(dialog);receipts.append((code,dialog.selected_job,runner._closed));return code
    monkeypatch.setattr(RemoteExecutionDialog,'exec',executed)
    try:
        pump(lambda:runner.selected_job_id==result['id'] and not runner._workers,app)
        def choose():
            dialog=app.activeModalWidget()
            if not isinstance(dialog,RemoteExecutionDialog) or dialog._busy:
                QTimer.singleShot(10,choose);return
            QTest.mouseClick(dialog.result_button,Qt.MouseButton.LeftButton)
        QTimer.singleShot(10,choose);show_remote(runner)
        assert receipts==[(1,result['id'],False)]
        pump(lambda:runner.result_metadata is not None and not runner._workers,app)
        assert runner.selected_job_id==result['id'] and len(runner._ledger)==2
        assert runner.responses.count()==2 and ssh.calls.count('submit')==1 and ssh.calls.count('fetch')==1
        assert runner.result_metadata['remote']['origin_job']==source['id']
    finally:
        runner.close();pump(lambda:not runner._workers,app);app.processEvents()


def test_lost_reply_close_then_fresh_gui_process_recovers_exact_request(live):
    client,wb,ssh=live;app=QApplication.instance() or QApplication([])
    original_submit=client.submit
    def lost(*args,**kwargs):
        original_submit(*args,**kwargs);raise OSError('CONTROLLED reply lost before GUI acknowledgement')
    client.submit=lost;window=RemoteExecutionDialog(client);window.show()
    try:
        pump(lambda:not window._busy,app)
        window.threads.setValue(3);window.wall.setValue(145)
        window.submit();pump(lambda:not window._busy,app)
        pending=window._pending;assert pending is not None
        job=next(job for job in wb.manager.list() if job.get('request_id')==pending[2]);wait(wb,job)
        window.reject();app.processEvents()
        before=len(wb.manager.list());calls=list(ssh.calls)
        script=r'''
import json,sys,time
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication
from caelab.workbench_client import Client
import apps.research.remote_execution_dialog as module
module._settings=lambda:QSettings(sys.argv[2],QSettings.Format.IniFormat)
app=QApplication([]);window=module.RemoteExecutionDialog(Client(sys.argv[1]));window.show()
def wait():
 deadline=time.monotonic()+10
 while window._busy:
  app.processEvents();time.sleep(.005)
  assert time.monotonic()<deadline
try:
 wait();original=json.loads(sys.argv[3]);assert list(window._pending)==original
 assert window.threads.value()==3 and window.wall.value()==145
 window.submit();wait();assert window._pending is None
 print(json.dumps({'job_id':window.selected_job,'request_id':original[2],'restored_arguments':'IDENTICAL'}))
finally:window.close();app.processEvents();app.quit()
'''
        child=subprocess.run([sys.executable,'-c',script,client.url,client._remote_test_settings_path,
            json.dumps(pending,ensure_ascii=False)],cwd=Path(__file__).resolve().parents[1],
            capture_output=True,text=True,encoding='utf-8',timeout=25)
        assert child.returncode==0,child.stderr
        receipt=json.loads(child.stdout.strip())
        assert receipt['job_id']==job['id'] and receipt['request_id']==pending[2]
        assert len(wb.manager.list())==before and ssh.calls==calls and ssh.calls.count('submit')==1
        output=os.environ.get('CAELAB_REMOTE_RENDER_DIR')
        if output:
            target=Path(output);target.mkdir(parents=True,exist_ok=True)
            (target/'cold-gui.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8')
            (target/'cold-gui.stderr.txt').write_text(child.stderr,encoding='utf-8')
    finally:
        pump(lambda:not window._busy,app);window.close();app.processEvents()


def test_first_definite_admission_refusal_releases_pending_and_keeps_edits(live):
    client,wb,ssh=live;app=QApplication.instance() or QApplication([])
    window=RemoteExecutionDialog(client);window.show()
    try:
        pump(lambda:not window._busy,app);window.threads.setValue(3)
        wb.config['remote_hosts']['public']['enabled']=False
        window.submit();pump(lambda:not window._busy,app)
        assert window._pending is None and window.threads.isEnabled() and window.threads.value()==3
        assert '접수 전에 거절' in window.message.text() and ssh.calls==[]
        assert all(job['operation']!='remote.run' for job in wb.manager.list())
    finally:window.close();app.processEvents()


def test_uncertain_accepted_request_is_found_even_after_host_registration_changes(live):
    client,wb,ssh=live;app=QApplication.instance() or QApplication([])
    original=client.submit
    def lost(*args,**kwargs): original(*args,**kwargs);raise OSError('CONTROLLED lost reply')
    client.submit=lost;window=RemoteExecutionDialog(client);window.show()
    try:
        pump(lambda:not window._busy,app);window.submit();pump(lambda:not window._busy,app)
        request=window._pending;job=next(j for j in wb.manager.list() if j.get('request_id')==request[2]);wait(wb,job)
        before=list(ssh.calls);wb.config['remote_hosts']['public']['runtime']['version']='changed'
        window.submit();pump(lambda:not window._busy,app)
        assert window._pending is None and window.selected_job==job['id'] and ssh.calls==before
        assert len([j for j in wb.manager.list() if j['operation']=='remote.run'])==1
    finally:window.close();app.processEvents()


def test_pending_request_is_bound_to_original_store_across_same_url_catalog_switch(live,tmp_path):
    from caelab.workbench import Workbench
    client,wb,ssh=live;app=QApplication.instance() or QApplication([])
    server=client._remote_test_server
    other=Workbench(tmp_path/'other-store',configuration={'remote_hosts':{'public':host()}})
    submitted=[];original_submit=client.submit
    def lost_once(*a,**k):
        submitted.append('A' if server.workbench is wb else 'B')
        result=original_submit(*a,**k)
        if len(submitted)==1:raise OSError('CONTROLLED A acknowledgement loss')
        return result
    client.submit=lost_once
    window=RemoteExecutionDialog(client);window.show()
    try:
        pump(lambda:not window._busy,app)
        window.submit();pump(lambda:not window._busy,app)
        pending=deepcopy(window._pending);store=window._store_key
        assert pending and window._pending_store_key==store
        job=next(j for j in wb.manager.list() if j.get('request_id')==pending[2]);wait(wb,job)
        settings=QSettings(client._remote_test_settings_path,QSettings.Format.IniFormat)
        key=window._pending_key(pending[2]);raw=settings.value(key);keys=settings.allKeys()
        calls=list(ssh.calls);before_jobs=deepcopy(wb.manager.list())
        server.workbench=other
        other_key=window._api('catalog')['store_key'];assert other_key!=store
        window.refresh();pump(lambda:not window._busy,app)
        assert window._store_key==window._pending_store_key==store
        assert window._store_mismatch and not window.submit_button.isEnabled()
        window.submit();window._send_pending();app.processEvents()
        assert submitted==['A'] and other.manager.list()==[]
        settings.sync();assert settings.allKeys()==keys and settings.value(key)==raw
        assert not any(k.startswith('remote-pending/'+other_key+'/') for k in settings.allKeys())
        assert window._pending==pending and wb.manager.list()==before_jobs and ssh.calls==calls
        server.workbench=wb
        window.refresh();pump(lambda:not window._busy,app)
        assert not window._store_mismatch and window._pending==pending
        window.submit();pump(lambda:not window._busy,app)
        assert window._pending is None and window._pending_store_key is None and window.selected_job==job['id']
        assert submitted==['A'] and wb.manager.list()==before_jobs and ssh.calls==calls
        settings.sync();assert not settings.contains(key)
    finally:
        server.workbench=wb;window.close();app.processEvents()
        assert other.shutdown(timeout=10)['joined']


@pytest.mark.parametrize('raw', ['{"truncated":', '["remote.run", "not arguments", "broken"]'])
def test_corrupt_pending_request_keeps_raw_record_and_blocks_new_submit(live,raw):
    client,wb,ssh=live;app=QApplication.instance() or QApplication([])
    window=RemoteExecutionDialog(client,auto_load=False)
    catalog=window._api('catalog');settings=QSettings(client._remote_test_settings_path,QSettings.Format.IniFormat)
    key='remote-pending/'+catalog['store_key']+'/broken'
    settings.setValue(key,raw);settings.sync()
    try:
        window._catalog(catalog)
        window.show();app.processEvents()
        assert '복구 기록' in window.message.text()
        assert not window.submit_button.isEnabled() and not window.threads.isEnabled()
        before=list(wb.manager.list());window.submit()
        assert wb.manager.list()==before and ssh.calls==[]
        assert settings.value(key)==raw
        capture(window,client,'corrupt-pending-preserved')
    finally:window.close();app.processEvents()


@pytest.mark.parametrize('scenario',['partial','checksum','unconfirmed'])
def test_saved_plan_failure_and_termination_recovery_preserves_source(live,scenario):
    client,wb,ssh=live;app=QApplication.instance() or QApplication([])
    doc,batch=saved_batch_plan(client,wb)
    original=deepcopy(doc);manifest=deepcopy(wb.result(batch['id'])['manifest'])
    wb.config['remote_hosts']['public']['label']='프로토콜 대역 — 외부 호스트 미실행'
    if scenario=='unconfirmed':
        ssh.terminated=False
    window=RemoteExecutionDialog(client);window.show()
    try:
        pump(lambda:not window._busy,app)
        window.batch.setCurrentIndex(window.batch.findData(batch['id']))
        window.submit();pump(lambda:not window._busy,app)
        source=wait(wb,wb.manager.status(window.selected_job))
        assert ssh.calls.count('submit')==1
        if scenario=='unconfirmed':
            window.refresh();pump(lambda:not window._busy,app)
            assert '종료 미확인' in window.detail.text()
            assert 'cancel' not in ssh.calls and 'fetch' not in ssh.calls
            capture(window,client,'unknown-termination')
            window.action('collect');pump(lambda:not window._busy,app)
            assert wait(wb,wb.manager.status(window.selected_job))['state']=='FAILED'
            assert 'fetch' not in ssh.calls and 'cancel' not in ssh.calls
            window.action('cancel');pump(lambda:not window._busy,app)
            assert wait(wb,wb.manager.status(window.selected_job))['state']=='CANCELLED'
            assert ssh.calls.count('cancel')==1
        else:
            if scenario=='partial':
                def partial(rows):
                    rows.pop();rows[0].update(execution_status='FAILED',responses={},failure_reason='REPLAY declared nonconvergence')
                ssh.mutate=partial
            else:
                original_request=ssh.request
                def corrupted(action,payload,folder):
                    result=original_request(action,payload,folder)
                    if action=='fetch':
                        result['files']['results.json']['sha256']='0'*64
                        Path(folder).mkdir(parents=True,exist_ok=True)
                        (Path(folder)/'replayed-response.json').write_text(json.dumps(result),encoding='utf-8')
                    return result
                ssh.request=corrupted
            window.action('collect');pump(lambda:not window._busy,app)
            collected=wait(wb,wb.manager.status(window.selected_job));assert collected['state']=='FAILED'
            saved=wb.result(collected['id']);assert saved['responses']=={}
            window.refresh();pump(lambda:not window._busy,app)
            assert '실패' in window.detail.text() or 'checksum' in window.detail.text()
            if scenario=='partial':
                assert [r['execution_status'] for r in saved['candidates']]==['FAILED','NOT_EVALUATED']
                assert '후보 누락 1개' in window.detail.text()
                assert (wb.root/'results'/collected['id']/'recovered/results.json').is_file()
            else:
                assert 'checksum' in saved['failure_reason']
                assert list((wb.root/'results'/collected['id']/'commands').glob('*/replayed-response.json'))
            capture(window,client,scenario)
        assert wb.result(batch['id'])['manifest']==manifest and client.document_read(doc['id'])==original
        assert ssh.calls.count('submit')==1
    finally:
        pump(lambda:not window._busy,app);window.close();app.processEvents()


def test_fresh_service_process_reads_saved_plan_and_same_remote_token_without_execution(tmp_path,monkeypatch):
    from caelab.workbench import Workbench
    ssh=ControlledSSH();monkeypatch.setattr('caelab.remote_transport.SSHTransport',lambda config:ssh)
    config={'remote_hosts':{'public':host()}};config['remote_hosts']['public']['label']='프로토콜 대역 — 외부 호스트 미실행'
    store=tmp_path/'cold-store';wb=Workbench(store,configuration=config)
    try:
        plan,batch=saved_batch_plan(wb,wb)
        source=wb.submit('remote.run',{'host_id':'public','batch_job':batch['id']},request_id='same-cold-token')
        assert wait(wb,source)['state']=='SUCCEEDED'
        collect=wb.submit('remote.collect',{'source_job':source['id']},request_id='same-cold-collection')
        assert wait(wb,collect)['state']=='SUCCEEDED'
        expected=deepcopy(wb.result(collect['id'])['responses']);jobs=len(wb.manager.list())
    finally:assert wb.shutdown(timeout=10)['joined']
    script=r'''
import json,sys,threading,time,os
from pathlib import Path
from PySide6.QtWidgets import QApplication
from apps.lab.server import LabHTTPServer
from apps.lab.service import LabService
from apps.research.remote_execution_dialog import RemoteExecutionDialog
from caelab.workbench_client import Client
import caelab.remote_transport as transport
def forbidden(*a,**k):raise AssertionError('Cold read/retry must not construct any remote transport')
transport.SSHTransport=forbidden
server=LabHTTPServer(LabService(Path(sys.argv[1])),0,workbench_config=json.loads(sys.argv[2]))
thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.02},daemon=True);thread.start()
app=QApplication([]);client=Client('http://127.0.0.1:'+str(server.server_port))
window=RemoteExecutionDialog(client,selected_job=sys.argv[4]);window.show()
try:
 deadline=time.monotonic()+10
 while window._busy:
  app.processEvents();time.sleep(.005);assert time.monotonic()<deadline
 before=len(server.workbench.manager.list())
 again=client.submit('remote.run',{'host_id':'public','batch_job':sys.argv[3]},request_id='same-cold-token')
 assert again['id']==sys.argv[5] and len(server.workbench.manager.list())==before
 assert client.result(sys.argv[4])['responses']==json.loads(sys.argv[6])
 plan=client.document_read(sys.argv[7])
 assert plan['draft']==json.loads(sys.argv[8]) and plan['saved_revision']==sys.argv[9]
 output=os.environ.get('CAELAB_REMOTE_RENDER_DIR')
 if output:
  for size,name in (((1000,720),'normal'),((700,600),'narrow')):
   window.resize(*size);app.processEvents();window.grab().save(str(Path(output)/('cold-service-'+name+'.png')))
 print(json.dumps({'cold_service_pid':os.getpid(),'same_token_job':again['id'],'selected_job':window.selected_job,
                   'plan_id':plan['id'],'plan_revision':plan['saved_revision'],
                   'job_count':before,'remote_transport_constructed':False,'responses_identical':True}))
finally:
 window.close();app.processEvents();server.shutdown();server.server_close();thread.join(3)
 assert server.workbench.shutdown(timeout=10)['joined'] and not thread.is_alive()
'''
    child=subprocess.run([sys.executable,'-X','utf8','-c',script,str(store),json.dumps(config),batch['id'],
        collect['id'],source['id'],json.dumps(expected),plan['id'],json.dumps(plan['draft']),plan['saved_revision']],cwd=Path(__file__).resolve().parents[1],
        capture_output=True,text=True,encoding='utf-8',timeout=30)
    assert child.returncode==0,child.stderr
    receipt=json.loads(child.stdout.strip());assert receipt['job_count']==jobs and receipt['responses_identical']
    output=os.environ.get('CAELAB_REMOTE_RENDER_DIR')
    if output:
        (Path(output)/'cold-service.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
