"""Saved B75 Data observation reaches the existing Material owner without edits.

Set CAELAB_OBSERVATION_SOURCE to an existing saved B75 store. No fixture data or
solver result is manufactured; the test copies that store before opening it.
"""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import threading
import time
from types import SimpleNamespace
import uuid

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import pytest
pytest.importorskip('PySide6')
from PySide6.QtCore import QThreadPool,QTimer
from PySide6.QtWidgets import QApplication
from apps.lab.service import LabService
from apps.lab.server import LabHTTPServer
from apps.research import desktop,result_return
from apps.research.material_window import MaterialWindow
from apps.research.material_test_dialog import ExperimentDialog
from caelab.storage import canonical_hash,save_json
from caelab.workbench_client import Client

MATERIAL='Mdd53da666aed441ba1d19440672577d5'
DATA='Te8f2f17dbfd0447f9708241245dbf069'
JOB='J07f38496d02a4f8ea14e02486a1baea8'


def wait(app,predicate,seconds=60):
    end=time.monotonic()+seconds
    while time.monotonic()<end:
        app.processEvents()
        if predicate():return
        time.sleep(.005)
    raise AssertionError('Existing observation owner did not settle')


def inventory(root):
    return {p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob('*') if p.is_file()}


def test_panel_pending_guard_without_application():
    application_before=QApplication.instance()
    source={'document_id':'Tsource','job_id':'Jsource','response':'load',
            'input_revision':'Isource','input_sha256':'a'*64}
    other={**source,'response':'extension'}
    def forbidden():raise AssertionError('Pending observation must not reopen/read/review')
    for busy,dirty in ((False,False),(True,False),(False,True)):
        panel=SimpleNamespace(_pending_observation=deepcopy(source),_busy=False,
            _staged_observation=None,_observation_material_id='Mtarget',
            observation_button=SimpleNamespace(hide=lambda:None))
        messages=[]
        window=SimpleNamespace(_plan_panel=panel,_pending_observation_source=None,
            document={'id':'Mtarget','session_id':'Scurrent'},_busy=busy,local_dirty=dirty,conflict=False,
            message=SimpleNamespace(setText=messages.append),open_plan_variables=forbidden,_call=forbidden,
            _update_actions=lambda:None)
        assert MaterialWindow.stage_observation(window,other) is False
        assert MaterialWindow.stage_observation(window,deepcopy(source)) is True
        assert panel._pending_observation==source and window._pending_observation_source is None
        assert MaterialWindow.open_document(window,document_id='Mother') is False
        assert MaterialWindow.open_document(window) is False
        MaterialWindow._opened(window,{'id':'Mother','session_id':'Scurrent'})
        MaterialWindow._opened(window,{'id':'Mtarget','session_id':'Sstale'})
        assert window.document=={'id':'Mtarget','session_id':'Scurrent'}
        assert MaterialWindow.cancel_observation(window) is True
        assert panel._pending_observation is None and window._pending_observation_source is None
        opens=[]
        window.client=SimpleNamespace(document_open=lambda **kw:opens.append(kw) or {'id':kw['document_id']})
        window._opened=lambda _:None;window._call=lambda function,received:function()
        assert MaterialWindow.open_document(window,document_id='Mother')=={'id':'Mother'}
        assert len(opens)==1
    for panel_busy,staged in ((True,None),(False,{'command_id':'Cuncertain'})):
        panel=SimpleNamespace(_pending_observation=deepcopy(source),_busy=panel_busy,_staged_observation=staged)
        window=SimpleNamespace(_plan_panel=panel,_pending_observation_source=deepcopy(source),
            message=SimpleNamespace(setText=lambda _:None),_update_actions=forbidden)
        assert MaterialWindow.cancel_observation(window) is False
        assert panel._pending_observation==source and window._pending_observation_source==source
    assert QApplication.instance() is application_before


def test_saved_observation_preserves_dirty_owner_and_actual_cli(tmp_path,monkeypatch):
    source=Path(os.environ.get('CAELAB_OBSERVATION_SOURCE',''))
    if not os.environ.get('CAELAB_OBSERVATION_SOURCE') or not (source/'workbench/documents'/DATA).is_dir():
        pytest.skip('Requires the declared existing B75 saved store; never synthesize an observation')
    output=Path(os.environ.get('CAELAB_OBSERVATION_CAPTURE',str(tmp_path/'capture')))
    output.mkdir(parents=True,exist_ok=False)
    repo=Path(__file__).resolve().parents[1]
    pins={name:hashlib.sha256((repo/name).read_bytes()).hexdigest() for name in (
        'apps/research/material_window.py','apps/research/result_return.py',
        'apps/research/desktop.py','tests/test_material_observation_owner_ui.py')}
    original=inventory(source);store=tmp_path/'owned B75 copy';shutil.copytree(source,store)
    def plan_states():
        states={}
        for path in (store/'workbench/documents').glob('N*/working.json'):
            value=json.loads(path.read_text(encoding='utf-8'))
            states[path.parent.name]={k:value[k] for k in ('draft','generation','runs','saved_revision')}
        return states
    plans_before=plan_states()
    app=QApplication.instance() or QApplication([])
    service=LabService(store);server=LabHTTPServer(service,0)
    thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.02},daemon=True);thread.start()
    client=Client(f'http://127.0.0.1:{server.server_port}');window=None;processes=[];dialogs=[]
    timer=QTimer();timer.setInterval(20);read_gate=threading.Event()
    def forbid(*a,**k):raise AssertionError('Observation delivery cannot submit/import/fit/solve')
    server.workbench.submit=server.workbench.manager.submit=forbid
    for owner in server.workbench.research_owners():owner.submit=forbid
    try:
        jobs=client.request('/api/workbench')['jobs']
        data=client.document_open(kind='data',document_id=DATA)
        reference=client.document_result_reference(DATA,JOB)
        result=client.document_result(DATA,JOB)
        assert 'fm_load' in result['responses'] and 'fm_deformation' in result['responses']
        assert canonical_hash(result)==reference['result_sha256']
        observation={k:reference[k] for k in ('document_id','job_id','input_revision','input_sha256')}
        observation['response']='fm_load'
        doc=client.document_open(kind='material',document_id=MATERIAL)
        assert doc['draft']['backend']=='material.felupe'
        window=MaterialWindow(client,document_id=MATERIAL,poll_interval=60000);window.show()
        wait(app,lambda:window.document is not None and not window._busy)
        token=(id(window),int(window.winId()),window._result_return.route)
        before=client.document_read(MATERIAL)
        # A real editable table cell keeps an incomplete numeric draft.
        window.coefficients.setCurrentCell(0,1);window.coefficients.setFocus()
        window.coefficients.item(0,1).setText('1e');app.processEvents()
        assert window.local_dirty
        dirty=deepcopy(window.edited_draft());undo=deepcopy(window._local_undo)
        receipt=result_return.review_material_observation(client,MATERIAL,observation)
        assert receipt['status']=='PRESENTED'
        assert window._pending_observation_source==observation
        assert window.edited_draft()==dirty and window._local_undo==undo
        for width,height in ((1440,900),(1000,720)):
            window.resize(width,height);app.processEvents()
            assert window.grab().save(str(output/f'dirty-observation-{width}.png'))
        tools=window.tools_menu
        assert window.cancel_observation_action.isEnabled()
        tools.popup(window.menuBar().mapToGlobal(window.menuBar().actionGeometry(tools.menuAction()).bottomLeft()))
        tools.setActiveAction(window.cancel_observation_action);app.processEvents()
        assert tools.isVisible() and tools.activeAction()==window.cancel_observation_action
        assert tools.grab().save(str(output/'dirty-observation-tools-menu.png'))
        tools.hide();app.processEvents()
        # A pending observation cannot migrate to a new/different document or
        # a late callback from another owner session. These guards run before
        # HTTP, so the controlled ID does not create another Material record.
        document_before=deepcopy(window.document)
        def no_open(*a,**k):raise AssertionError('Pending target switch reached HTTP')
        with monkeypatch.context() as patch:
            patch.setattr(client,'document_open',no_open)
            assert window.open_document(document_id='Mother') is False
            assert window.open_document() is False
            window._opened({**deepcopy(document_before),'id':'Mother'})
            window._opened({**deepcopy(document_before),'session_id':'SstaleCallback'})
        assert window.document==document_before and window.edited_draft()==dirty
        assert window._pending_observation_source==observation
        # Exercise the real QLocal wire on another thread, with a wrong session.
        message={'version':1,'operation':'material_observation','service':result_return.service_identity(client.url),
            'target_id':MATERIAL,'session_id':doc['session_id'],'delivery_id':'D'+uuid.uuid4().hex,
            'reference':deepcopy(observation)}
        def wired(value):
            with ThreadPoolExecutor(max_workers=1) as pool:
                future=pool.submit(result_return.send_message,value)
                wait(app,future.done);return future.result()
        stale=deepcopy(message);stale['session_id']='SwrongCurrentOwner'
        with pytest.raises(RuntimeError,match='identity/session did not acknowledge'):
            wired(stale)
        assert result_return.receive_local(stale)['status']=='REJECTED'
        other=deepcopy(message);other['reference']['response']='fm_deformation'
        assert wired(other)['status']=='BUSY'
        assert window._pending_observation_source==observation and window.edited_draft()==dirty
        # Actual desktop launcher -> actual CLI -> same QLocal target. Capture
        # the real Popen handle so only this child can be cleaned up.
        popen=subprocess.Popen
        def tracked(*a,**k):
            process=popen(*a,**k);processes.append(process);return process
        cli_received=[];stage=window.stage_observation
        def observed_stage(value):cli_received.append(deepcopy(value));return stage(value)
        receipts_before=set(window._result_return.receipts)
        with monkeypatch.context() as patch:
            patch.setattr(desktop.subprocess,'Popen',tracked)
            patch.setattr(window,'stage_observation',observed_stage)
            launched=desktop.launch_material_observation(client,observation,document_id=MATERIAL)
            assert launched['pid']==processes[-1].pid
            wait(app,lambda:processes[-1].poll() is not None)
        assert processes[-1].returncode==0
        assert cli_received==[observation]
        cli_receipts=set(window._result_return.receipts)-receipts_before
        assert len(cli_receipts)==1
        assert window._result_return.receipts[next(iter(cli_receipts))]['status']=='PRESENTED'
        assert window._pending_observation_source==observation and window.edited_draft()==dirty
        assert (id(window),int(window.winId()),window._result_return.route)==token
        assert window.document['id']==MATERIAL and window.document['session_id']==doc['session_id']
        # Existing local Undo restores the draft; review uses the existing Plan
        # and real ExperimentDialog, then Cancel leaves both owners unchanged.
        def reject_review():
            for candidate in app.topLevelWidgets():
                if isinstance(candidate,ExperimentDialog) and candidate.isVisible():
                    dialogs.append(candidate.windowTitle());candidate.reject()
        timer.timeout.connect(reject_review);timer.start()
        window.undo_inputs();assert not window.local_dirty
        # Keep one existing HTTP read pending in the real Qt worker to exercise
        # busy admission separately from the incomplete-cell branch.
        window._call(lambda:(read_gate.wait(10),client.document_read(MATERIAL))[1],lambda _:None)
        assert window._busy
        busy_other=deepcopy(other);busy_other['delivery_id']='D'+uuid.uuid4().hex
        assert wired(busy_other)['status']=='BUSY'
        busy=deepcopy(message);busy['delivery_id']='D'+uuid.uuid4().hex
        assert wired(busy)['status']=='PRESENTED'
        assert window._pending_observation_source==observation and not window.local_dirty
        read_gate.set()
        wait(app,lambda:bool(dialogs) and window._plan_panel is not None and not window._plan_panel._busy)
        panel=window._plan_panel
        assert panel._pending_observation==observation and window._pending_observation_source is None
        review_count=len(dialogs);duplicate_reviews=[]
        review=panel.review_observation
        def count_review():duplicate_reviews.append(True);return review()
        with monkeypatch.context() as patch:
            patch.setattr(panel,'review_observation',count_review)
            clean_other=deepcopy(other);clean_other['delivery_id']='D'+uuid.uuid4().hex
            assert wired(clean_other)['status']=='BUSY'
            clean_same=deepcopy(message);clean_same['delivery_id']='D'+uuid.uuid4().hex
            assert wired(clean_same)['status']=='PRESENTED'
            app.processEvents()
            assert not duplicate_reviews and len(dialogs)==review_count
        assert panel._pending_observation==observation and panel._staged_observation is None
        timer.stop()
        assert window.cancel_observation_action.isEnabled()
        window.cancel_observation_action.trigger();app.processEvents()
        assert panel._pending_observation is None and window._pending_observation_source is None
        # After explicit cancellation another channel from the same saved Data
        # source can be received. Keep this second delivery in a dirty buffer so
        # it requires no second Plan review/read, then cancel through the action.
        window.coefficients.item(0,1).setText('1e');app.processEvents()
        second_dirty=deepcopy(window.edited_draft());assert window.local_dirty
        after_cancel=deepcopy(other);after_cancel['delivery_id']='D'+uuid.uuid4().hex
        assert wired(after_cancel)['status']=='PRESENTED'
        assert window._pending_observation_source==after_cancel['reference']
        final_cancel_before=dict(panel_busy=panel._busy,staged=deepcopy(panel._staged_observation),
            action_enabled=window.cancel_observation_action.isEnabled())
        wait(app,lambda:not panel._busy and not window._busy)
        final_cancel_ready=dict(panel_busy=panel._busy,staged=deepcopy(panel._staged_observation),
            action_enabled=window.cancel_observation_action.isEnabled())
        window.cancel_observation_action.trigger();app.processEvents()
        assert window._pending_observation_source is None and panel._pending_observation is None
        assert window.edited_draft()==second_dirty
        window.undo_inputs();assert not window.local_dirty
        assert window._plan_panel._staged_observation is None
        after=client.document_read(MATERIAL)
        assert after['draft']==before['draft'] and after['generation']==before['generation'] and after['runs']==before['runs']
        assert plan_states()==plans_before
        assert client.request('/api/workbench')['jobs']==jobs
        assert canonical_hash(client.document_result(DATA,JOB))==reference['result_sha256']
        assert inventory(source)==original
        assert pins=={name:hashlib.sha256((repo/name).read_bytes()).hexdigest() for name in pins}
        save_json(output/'acceptance.json',dict(status='PASS',source_store=str(source.resolve()),owned_store=str(store),
            material_id=MATERIAL,material_session=doc['session_id'],window_token=token,observation=observation,
            original_result_sha256=reference['result_sha256'],dirty_draft_sha256=canonical_hash(dirty),
            target_generation=before['generation'],existing_cli_pid=processes[-1].pid,cli_exit_code=0,
            cli_exact_observation_received=cli_received,cli_new_presented_receipts=len(cli_receipts),
            original_plan_count=len(plans_before),plans_and_saved_revisions_unchanged=True,
            receipt=receipt,wrong_session='REJECTED',different_pending='BUSY',busy_delivery='PRESENTED',
            pending_new_or_other_target='BLOCKED_BEFORE_HTTP',stale_open_callback='BLOCKED_BEFORE_BUFFER_REPLACE',
            busy_other_pending='BUSY',clean_other_pending='BUSY',clean_same_pending='PRESENTED',
            duplicate_clean_reviews=0,clean_review_cancelled=dialogs,
            explicit_cancel_action='A and B cleared; Material/Plan untouched',after_cancel_other_source='PRESENTED_IN_DIRTY_BUFFER',
            final_cancel_before=final_cancel_before,final_cancel_ready=final_cancel_ready,
            new_jobs=0,new_import_fit_solver_provider=0,source_files_unchanged=len(original),
            source_pins=pins,
            cancel_menu='Actual Qt popup/grab, enabled action; no physical OS click claim',
            claim='Actual HTTP + same-process GUI + QLocal wire + separate real CLI; Qt input/rendering, not physical OS input'))
    finally:
        timer.stop();read_gate.set()
        for process in processes:
            if process.poll() is None:process.terminate();process.wait(5)
        if window is not None:
            wait(app,lambda:not window._busy)
            if window._plan_panel is not None:wait(app,lambda:not window._plan_panel._busy)
            window._allow_close=True;window.close();app.processEvents()
        server.shutdown();server.server_close();service.shutdown();thread.join(5)
        assert QThreadPool.globalInstance().waitForDone(5000)
