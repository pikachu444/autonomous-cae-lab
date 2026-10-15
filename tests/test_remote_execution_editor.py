"""Actual local HTTP/Qt; controlled remote adapter, never a live SSH host."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
import threading
import time
import json
import subprocess
import sys

import pytest
pytest.importorskip('PySide6')
from PySide6.QtCore import Qt,QTimer,QSettings
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
def live(tmp_path,monkeypatch):
    ssh=ControlledSSH(); monkeypatch.setattr('caelab.remote_transport.SSHTransport',lambda config:ssh)
    server=LabHTTPServer(LabService(tmp_path/'store'),0,workbench_config={'remote_hosts':{'public':host()}})
    thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.02},daemon=True);thread.start()
    client=Client('http://127.0.0.1:'+str(server.server_port));wb=server.workbench
    client._remote_test_settings_path=str(tmp_path/'remote-pending.ini')
    monkeypatch.setattr('apps.research.remote_execution_dialog._settings',
        lambda:QSettings(client._remote_test_settings_path,QSettings.Format.IniFormat))
    job=client.submit('batch_export',{'variables':[{'id':'x','unit':'1','lower':0.,'upper':4.}],
        'candidates':[{'x':1.},{'x':3.}], 'case_id':'public-case','label':'공개 하중 비교'})
    wait(wb,job)
    try: yield client,wb,ssh
    finally: server.shutdown();server.server_close();thread.join(3)


def test_actual_http_lost_reply_qt_retry_and_explicit_collection(live):
    client,wb,ssh=live;app=QApplication.instance() or QApplication([]);apply_appearance(app)
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
        output=os.environ.get('CAELAB_REMOTE_RENDER_DIR')
        if output:
            target=Path(output);target.mkdir(parents=True,exist_ok=True)
            for size,name in (((1000,720),'normal'),((700,600),'narrow')):
                window.resize(*size);app.processEvents()
                assert window.width()<=size[0] and window.height()<=size[1]
                assert window.grab().save(str(target/(name+'.png')))
        assert wb.result(collected['id'])['responses']['후보 1 / force']['unit']=='N'
        assert wb.manager.status(original)['operation']=='remote.run'
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
        actions=[action.text() for menu in runner.menuBar().actions() if menu.menu() for action in menu.menu().actions()]
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
