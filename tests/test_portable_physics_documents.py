"""Portable physics owner/proof boundary checks; evaluation is labelled double.

Actual existing PDE/thermal evaluations and separate processes are exercised by
examples.portable_physics_public, never faked as numerical qualification here.
"""
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
import json
from unittest.mock import patch
import pytest
from caelab.workbench import Workbench
from caelab.portable_project import inspect_copy,create_copy,open_project,verify_project
from caelab.portable_project_physics import read_execution,check_run
from caelab.storage import canonical_hash,load_json,save_json
from caelab.evaluation import file_hash
from examples.portable_physics_public import command,save,wait,no_execution,hashes


@contextmanager
def workspace(folder):
    wb=Workbench(folder)
    try:yield wb
    finally:
        closed=wb.shutdown();assert closed['joined'] and not closed['pending']


def draft(kind):
    from caelab.pde_document import default_draft
    from caelab.simulation_document import default_draft as sim
    return default_draft('pde.scipy.ode') if kind=='pde' else sim('thermal.scikit_fem.rectangle')


def recorded(wb,kind,states=('SUCCEEDED',)):
    doc=wb.document_open(kind=kind,draft=draft(kind))
    calls=[]
    def controlled(operation,arguments,job):
        state=states[len(calls)];calls.append(deepcopy(arguments))
        if state=='RAISED':raise RuntimeError('CONTROLLED missing native runtime; NO PHYSICS')
        folder=wb.root/'results'/job;folder.mkdir(parents=True)
        (folder/'original-input.txt').write_bytes(b'CONTROLLED original input\r\n')
        (folder/'field.bin').write_bytes(b'CONTROLLED exact field bytes\x00\x01')
        from caelab.evaluation import save_evaluation
        value={'execution_status':state,'responses':{'temperature':{'kind':'series','value':[300.,301.],
            'unit':'K','component':'scalar','location':'fixture','axes':[{'name':'time','unit':'s','values':[0.,1.]}]}},
            'checks':[],'diagnostics':{'boundary':'CONTROLLED retention contract, NOT PHYSICS','qualification':'UNKNOWN'},
            'artifacts':[{'path':p.name,'sha256':file_hash(p)} for p in folder.iterdir()]}
        save_evaluation(value,folder,existing=True);return value
    with patch.object(wb.manager,'_execute',controlled):
        for _ in states:
            receipt=command(wb,doc,kind+'.evaluate');wait(wb,receipt['job']['id'])
            doc=save(wb,wb.document_read(doc['id']))
    return doc,calls


def copy(wb,doc,target):
    plan=inspect_copy(wb,[doc['id']]);assert plan['status']=='READY',plan['issues']
    return create_copy(wb,plan,target,approved=True,command_id='Ccopy',session_id=wb.session_id)


@pytest.mark.parametrize('kind',['pde','simulation'])
def test_original_success_failure_missing_runtime_bytes_edit_and_recopy(tmp_path,kind):
    with workspace(tmp_path/'origin') as wb:
        doc,calls=recorded(wb,kind,('SUCCEEDED','RAISED','FAILED'))
        original=deepcopy(doc);success,raised,partial=[r['job_id'] for r in doc['runs']]
        raw=hashes(wb,doc,success);result=canonical_hash(wb.document_result(doc['id'],success))
        failure=wb.manager.status(raised)['error']
        made=copy(wb,doc,tmp_path/'copy')
    (tmp_path/'origin').rename(tmp_path/'origin-preserved')
    cold=open_project(tmp_path/'copy')
    try:
        with no_execution(cold):
            doc=cold.document_read(made['documents'][0]['document_id'])
            assert [r['retained_state'] for r in doc['runs']]==['SUCCEEDED','FAILED','FAILED']
            assert doc['runs'][1]['retained_error']==failure
            assert canonical_hash(cold.document_result(doc['id'],success))==result
            assert hashes(cold,doc,success)==raw
            assert cold.document_result(doc['id'],partial)['execution_status']=='FAILED'
            with pytest.raises(ValueError,match='no response'):cold.document_result(doc['id'],raised)
            bridge=read_execution(cold._document_owner(doc['id']),doc['id'],success)
            assert bridge['source_document_id']==original['id']
            assert bridge['original_run']['arguments']==original['runs'][0]['arguments']
            altered=deepcopy(doc['draft']);altered['settings']['unfinished']='1e'
            doc=command(cold,doc,kind+'.update',{'draft':altered})['document']
            assert doc['diagnostics'] and not doc['runs'][0]['is_current_input']
            saved=save(cold,doc)
            doc=command(cold,saved,'document.undo')['document'];assert doc['draft']==original['draft']
            doc=command(cold,doc,'document.redo')['document'];assert doc['draft']==altered
            made=copy(cold,save(cold,doc),tmp_path/'recopy')
            assert not cold.manager.list()
    finally:cold.shutdown()

    (tmp_path/'copy').rename(tmp_path/'copy-preserved')
    final=open_project(tmp_path/'recopy')
    try:
        with no_execution(final):
            doc=final.document_read(made['documents'][0]['document_id'])
            assert doc['draft']==altered and doc['diagnostics']
            assert canonical_hash(final.document_result(doc['id'],success))==result
            assert hashes(final,doc,success)==raw
            assert len(calls)==3 and not final.manager.list()
    finally:final.shutdown()

@pytest.mark.parametrize('kind',['pde','simulation'])
def test_qt_retained_no_response_and_corrupt_result_never_query_old_live_job(tmp_path,kind,monkeypatch):
    pytest.importorskip('PySide6')
    import os,threading,time
    from PySide6.QtWidgets import QApplication,QDialog,QPushButton
    from PySide6.QtCore import QThreadPool,QTimer,Qt
    from PySide6.QtTest import QTest
    from apps.lab.server import LabHTTPServer
    from apps.lab.service import LabService
    from apps.research.pde_window import PDEWindow
    from apps.research.simulation_window import SimulationWindow
    from caelab.workbench_client import Client
    with workspace(tmp_path/'origin') as origin:
        doc,_=recorded(origin,kind,('SUCCEEDED','RAISED'))
        copy(origin,doc,tmp_path/'copy')
    (tmp_path/'origin').rename(tmp_path/'origin-preserved')
    server=LabHTTPServer(LabService(tmp_path/'copy'),0);wb=server.workbench
    thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.02},daemon=True);thread.start()
    app=QApplication.instance() or QApplication([]);window=None
    def settle(predicate):
        deadline=time.monotonic()+20
        while time.monotonic()<deadline:
            app.processEvents()
            if window is not None and not window._busy and predicate():return
            time.sleep(.005)
        raise AssertionError(window.message.text())
    try:
        with no_execution(wb):
            client=Client('http://127.0.0.1:'+str(server.server_port))
            def forbidden_status(*args,**kwargs):raise AssertionError('retained job live status queried')
            monkeypatch.setattr(client,'status',forbidden_status)
            row=wb.documents()['documents'][0]
            cls=PDEWindow if kind=='pde' else SimulationWindow
            window=cls(client,document_id=row['id'],poll_interval=0);window.show()
            settle(lambda:window._result_key is not None)
            failed=window.document['runs'][-1]
            assert window._result is None and '실패 (결과 없음)' in window.result_label.text()
            assert failed['retained_error']['message']==window.message.text()
            # CANCELLED uses the same retained no-response path, without inventing a result.
            failed['retained_state']='CANCELLED';window._result_key=None;window.refresh_result()
            settle(lambda:window._result_key is not None)
            assert '취소 (결과 없음)' in window.result_label.text() and window._result is None
            render=os.environ.get('CAELAB_PHYSICS_FAILURE_RENDER_DIR')
            if render:
                out=Path(render);out.mkdir(parents=True,exist_ok=True)
                window.graph_tabs.setCurrentIndex(1);window.resize(1020,720);app.processEvents()
                window.grab().save(str(out/(kind+'-retained-cancelled.png')))
                from apps.research.portable_research_actions import prepare_copy
                def cancel_copy():
                    dialog=app.activeModalWidget();assert isinstance(dialog,QDialog)
                    assert dialog.grab().save(str(out/(kind+'-copy-choice.png')))
                    button=next(b for b in dialog.findChildren(QPushButton) if b.text()=='취소')
                    QTest.mouseClick(button,Qt.MouseButton.LeftButton)
                QTimer.singleShot(0,cancel_copy)
                assert not prepare_copy(window)
            original_read=client.document_result
            window._selected_job=window.document['runs'][0]['job_id'];window._result_key=None
            window.refresh_result();settle(lambda:bool(window._result))
            assert window.result_selector.count()>0
            def corrupt(*args,**kwargs):raise ValueError('CONTROLLED retained field digest mismatch')
            monkeypatch.setattr(client,'document_result',corrupt)
            window._selected_job=window.document['runs'][0]['job_id'];window._result_key=None
            window.refresh_result();settle(lambda:window._result_key is not None)
            assert window._result is None and window.result_label.text()=='보존 결과를 읽지 못했습니다.'
            assert window.message.text()=='CONTROLLED retained field digest mismatch'
            assert not window.result_selector.count() and not window._native_fields
            assert not window.point_label.text() and not window.field_node.count()
            assert not window.result_axes.lines and not window.result_axes.collections
            # A newly requested unretained job still polls its current job manager.
            calls=[]
            monkeypatch.setattr(client,'status',lambda job:calls.append(job) or {'state':'RUNNING'})
            window.document['runs'].append({'job_id':'JlocalPending'})
            window._selected_job='JlocalPending';window._result_key=None
            window.refresh_result();settle(lambda:bool(calls))
            assert calls==['JlocalPending']
            assert window._result_key is None and not wb.manager.list()
            monkeypatch.setattr(client,'document_result',original_read)
    finally:
        if window is not None:window.timer.stop();window._allow_close=True;window.close()
        app.processEvents();QThreadPool.globalInstance().waitForDone(10000)
        server.shutdown();server.server_close();thread.join(3)
        assert wb.shutdown()['joined']



@pytest.mark.parametrize('kind',['pde','simulation'])
@pytest.mark.parametrize('fault',['field','proof','original_input','current_alias','legacy'])
def test_tamper_or_missing_execution_proof_cannot_rebind_a_result(tmp_path,kind,fault):
    with workspace(tmp_path/'origin') as wb:
        doc,_=recorded(wb,kind);made=copy(wb,doc,tmp_path/'copy')
    identifier=made['documents'][0]['document_id'];folder=tmp_path/'copy/workbench/documents'/identifier
    if fault=='current_alias':
        live=load_json(folder/'working.json');live['runs'][0]['settings']['invented']='different'
        save_json(folder/'working.json',live)
    elif fault=='legacy':
        live=load_json(folder/'working.json');live['runs'][0].pop('portable_execution');save_json(folder/'working.json',live)
        assert verify_project(tmp_path/'copy')['status']=='BLOCKED'
        with pytest.raises(Exception):open_project(tmp_path/'copy')
        # Current header forgery cannot make an old derived run authoritative.
        from caelab.portable_project_physics import inspect_document
        from types import SimpleNamespace
        with pytest.raises(ValueError,match='LEGACY_PROOF'):
            inspect_document(SimpleNamespace(),live)
        return
    else:
        working=load_json(folder/'working.json');run=working['runs'][0]
        revision=folder/'revisions'/run['retained_record']['revision']
        if fault=='field':target=revision/'results'/run['job_id']/'field.bin'
        elif fault=='proof':target=revision/run['portable_execution']['file']
        else:
            proof=load_json(revision/run['portable_execution']['file']);target=revision/proof['origin']['input']['file']
        target.write_bytes(target.read_bytes()+b'TAMPER')
    assert verify_project(tmp_path/'copy')['status']=='BLOCKED'
    with pytest.raises(Exception):open_project(tmp_path/'copy')


@pytest.mark.parametrize('kind',['pde','simulation'])
def test_unimplemented_draft_stays_editable_and_old_result_remains_original(tmp_path,kind):
    with workspace(tmp_path/'origin') as wb:
        doc,_=recorded(wb,kind)
        changed={'backend':'unimplemented.adapter','settings':{'unfinished':'1e'}}
        doc=command(wb,doc,kind+'.update',{'draft':changed})['document'];doc=save(wb,doc)
        made=copy(wb,doc,tmp_path/'copy')
    cold=open_project(tmp_path/'copy')
    try:
        with no_execution(cold):
            doc=cold.document_read(made['documents'][0]['document_id']);assert doc['diagnostics']
            assert cold.document_result(doc['id'],doc['runs'][0]['job_id'])['responses']['temperature']['unit']=='K'
            assert not doc['runs'][0]['is_current_input']
            with pytest.raises(ValueError,match='Invalid draft'):command(cold,doc,kind+'.evaluate')
            assert not cold.manager.list()
    finally:cold.shutdown()

@pytest.mark.parametrize('kind',['pde','simulation'])
def test_destination_missing_native_runtime_is_a_new_failed_attempt_not_old_result(tmp_path,kind):
    with workspace(tmp_path/'origin') as wb:
        doc,_=recorded(wb,kind);old=doc['runs'][0]['job_id'];made=copy(wb,doc,tmp_path/'copy')
    cold=open_project(tmp_path/'copy')
    try:
        doc=cold.document_read(made['documents'][0]['document_id'])
        from caelab.pde_document import default_draft
        from caelab.simulation_document import default_draft as simulation
        native=default_draft('pde.fenicsx.dimensioned') if kind=='pde' else simulation('thermal.fenicsx.rectangle')
        doc=command(cold,doc,kind+'.update',{'draft':native})['document']
        calls=[]
        def unavailable(operation,arguments,job):
            calls.append((operation,arguments))
            from caelab.contracts import CapabilityUnavailable
            raise CapabilityUnavailable('CONTROLLED absent native runtime — no solver launched')
        with patch.object(cold.manager,'_execute',unavailable):
            receipt=command(cold,doc,kind+'.evaluate');new=wait(cold,receipt['job']['id'])
        assert new['state']=='FAILED' and new['id']!=old
        assert calls[0][0]==('pde.evaluate' if kind=='pde' else 'simulation.run')
        assert calls[0][1]==native
        doc=save(cold,cold.document_read(doc['id']))
        with no_execution(cold):
            assert cold.document_result(doc['id'],old)['execution_status']=='SUCCEEDED'
            assert not doc['runs'][0]['is_current_input']
            assert doc['runs'][-1]['retained_error']['message'].startswith('CONTROLLED absent native')
            copy(cold,doc,tmp_path/'recopy')
    finally:cold.shutdown()


def test_qt_http_copy_menu_saved_results_and_unapplied_input(tmp_path,monkeypatch):
    pytest.importorskip('PySide6')
    import os,threading,time
    from PySide6.QtCore import Qt,QTimer,QThreadPool
    from PySide6.QtWidgets import QApplication,QDialog,QPushButton,QMessageBox
    from PySide6.QtTest import QTest
    from apps.lab.server import LabHTTPServer
    from apps.lab.service import LabService
    from apps.research.pde_window import PDEWindow
    from apps.research.simulation_window import SimulationWindow
    from apps.research.portable_research_actions import prepare_copy
    from caelab.workbench_client import Client
    source=os.environ.get('CAELAB_PHYSICS_SAVED_FOLDER')
    if source:
        origin=open_project(source)
        try:
            documents=origin.documents()['documents'];plan=inspect_copy(origin,[d['id'] for d in documents])
            assert plan['status']=='READY',plan['issues']
            create_copy(origin,plan,tmp_path/'copy',approved=True,command_id='CuiCopy',session_id=origin.session_id)
        finally:origin.shutdown()
    else:
        with workspace(tmp_path/'origin') as origin:
            docs=[recorded(origin,kind)[0] for kind in ('pde','simulation')]
            plan=inspect_copy(origin,[d['id'] for d in docs]);assert plan['status']=='READY'
            create_copy(origin,plan,tmp_path/'copy',approved=True,command_id='CuiCopy',session_id=origin.session_id)
    server=LabHTTPServer(LabService(tmp_path/'copy'),0);wb=server.workbench
    thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.02},daemon=True);thread.start()
    app=QApplication.instance() or QApplication([]);windows=[]
    def settle(window,predicate=lambda:True):
        deadline=time.monotonic()+20
        while time.monotonic()<deadline:
            app.processEvents()
            if not window._busy and predicate():return
            time.sleep(.005)
        raise AssertionError(window.message.text())
    def choose(text,capture=None):
        def clicked():
            dialog=app.activeModalWidget();assert isinstance(dialog,QDialog)
            if capture:
                folder=Path(capture);folder.mkdir(parents=True,exist_ok=True)
                dialog.grab().save(str(folder/'copy-choice.png'))
            button=next(b for b in dialog.findChildren(QPushButton) if b.text()==text)
            QTest.mouseClick(button,Qt.MouseButton.LeftButton)
        QTimer.singleShot(0,clicked)
    try:
        with no_execution(wb):
            client=Client('http://127.0.0.1:'+str(server.server_port))
            for row in wb.documents()['documents']:
                cls=PDEWindow if row['kind']=='pde' else SimulationWindow
                window=cls(client,document_id=row['id'],poll_interval=0);windows.append(window)
                window.show();settle(window,lambda:window.document is not None and window._result is not None)
                old=window.document['runs'][0]['job_id'];window._selected_job=old;window._result_key=None
                window.refresh_result();settle(window,lambda:window._result_key is not None)
                if source:
                    field=next((i for i in range(window.result_selector.count()) if window.result_selector.itemData(i)[0]=='field'),None)
                    assert field is not None;window.result_selector.setCurrentIndex(field)
                render=os.environ.get('CAELAB_PHYSICS_RENDER_DIR')
                if render:
                    folder=Path(render);folder.mkdir(parents=True,exist_ok=True)
                    for suffix,size in [('normal',(1280,850)),('narrow',(1020,720))]:
                        window.resize(*size);app.processEvents();assert window.grab().save(str(folder/(row['kind']+'-'+suffix+'.png')))
                before=deepcopy(window.document['draft'])
                path=('settings','parameters',0,'value') if row['kind']=='pde' else ('settings','boundary_temperature','value')
                node=('settings','parameters') if row['kind']=='pde' else ('settings','boundary_temperature')
                window.tree.setCurrentItem(window._nodes[node]);widget=window.fields[path][0]
                widget.setFocus();widget.selectAll();QTest.keyClicks(widget,'1e')
                selected=widget.selectedText() if hasattr(widget,'selectedText') else ''
                for choice in ('취소','저장된 내용만'):
                    choose(choice,render);child=prepare_copy(window);app.processEvents()
                    assert widget.text()=='1e' and window.local_dirty
                    assert wb.document_read(row['id'])['draft']==before
                    if child:
                        settle(child,lambda:child.graph is not None);child.close();app.processEvents()
                widget.selectAll();QTest.keyClicks(widget,'2.2' if row['kind']=='pde' else '304')
                choose('저장 후 계속');prepare_copy(window)
                settle(window,lambda:bool(getattr(window,'_portable_research_children',[])))
                settle(window)
                assert not window.local_dirty and not window.document['dirty']
                submitted=deepcopy(window.document['draft'])
                assert submitted!=before and not window.document['runs'][0]['is_current_input']
                window.command('document.undo');settle(window);assert window.document['draft']==before
                window.command('document.redo');settle(window);assert window.document['draft']==submitted
                window.save_document();settle(window)
                assert not wb.manager.list()
    finally:
        monkeypatch.setattr(QMessageBox,'question',lambda *a,**k:QMessageBox.StandardButton.Discard)
        for window in reversed(windows):window._allow_close=True;window.close()
        app.processEvents();QThreadPool.globalInstance().waitForDone(10000)
        server.shutdown();server.server_close();thread.join(3)
        assert wb.shutdown()['joined']

@pytest.mark.parametrize('kind',['pde','simulation'])
def test_save_pointer_failure_keeps_current_edit_old_result_and_previous_saved_head(tmp_path,kind,monkeypatch):
    with workspace(tmp_path/'origin') as wb:
        original,_=recorded(wb,kind);made=copy(wb,original,tmp_path/'copy')
    cold=open_project(tmp_path/'copy')
    try:
        doc=cold.document_read(made['documents'][0]['document_id']);job=doc['runs'][0]['job_id']
        root=cold._document_owner(doc['id'])._folder(doc['id']);pointer=(root/'document.json').read_bytes()
        old_result=canonical_hash(cold.document_result(doc['id'],job));old_revision=doc['saved_revision']
        changed=deepcopy(doc['draft']);changed['settings']['unfinished']='1e'
        doc=command(cold,doc,kind+'.update',{'draft':changed})['document']
        import caelab.material_document as module
        actual=module.save_json
        def failed_publish(path,value):
            if Path(path)==root/'document.json':raise OSError('CONTROLLED pointer publication failure')
            return actual(path,value)
        with monkeypatch.context() as scoped:
            scoped.setattr(module,'save_json',failed_publish)
            with pytest.raises(OSError,match='pointer publication'):save(cold,doc)
        with no_execution(cold):
            assert (root/'document.json').read_bytes()==pointer
            current=cold.document_read(doc['id']);assert current['draft']==changed and current['saved_revision']==old_revision
            assert canonical_hash(cold.document_result(doc['id'],job))==old_result
            assert not cold.manager.list()
    finally:cold.shutdown()
