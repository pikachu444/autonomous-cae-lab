"""Real Qt construction/render check. Missing Qt is NOT_RUN, never fake-GUI PASS."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import pytest
QtWidgets=pytest.importorskip('PySide6.QtWidgets',reason='NOT_RUN: actual PySide6 absent')
from types import SimpleNamespace
from copy import deepcopy
import threading,time
from caelab.workbench import Workbench
from apps.research.law_native_material_window import LawNativeMaterialWindow,default_draft,LABELS


@pytest.mark.parametrize('model',list(LABELS))
def test_actual_qt_law_views(tmp_path,model):
    app=QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    wb=Workbench(tmp_path/'workspace');window=None
    try:
        d=wb.document_open(kind='material',draft=default_draft(model=model))
        window=LawNativeMaterialWindow(SimpleNamespace(),auto_open=False,poll_interval=0)
        window._show_document(d)
        window.show();app.processEvents()
        assert window.document['id']==d['id'] and window.equation.text() and not window.local_dirty
        assert ('settings','parameters','E' if model=='drucker_prager_linear' else 'mu' if model=='neo_hooke' else 'K0') in window.fields
        window.tree.setCurrentItem(window._nodes[('settings','model')]);app.processEvents()
        assert ('settings','model') not in window.fields
        assert window.edited_draft()==d['draft']
        window.tree.setCurrentItem(window._nodes[('settings','parameters')]);app.processEvents()
        for width,height in ((1440,900),(1000,680)):
            window.resize(width,height);app.processEvents()
            assert window.grab().save(str(tmp_path/f'{model}-{width}.png'))
        window.open_constitutive()
        assert '결과' in window.message.text()
        assert window.edited_draft()==d['draft']
    finally:
        if window is not None:window._allow_close=True;window.close();app.processEvents()
        assert wb.shutdown()['joined']


def test_transfer_review_shows_values_and_preserves_pending_close(tmp_path,monkeypatch):
    from apps.research.law_native_transfer_dialog import LawNativeTransferDialog
    app=QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    monkeypatch.setattr(LawNativeTransferDialog,'_call',lambda self,fn,done,failure=None:done(fn()))
    material={'id':'Mfixture','title':'공개 DP 시편','saved_revision':'Rfixture','draft':default_draft()}
    window=LawNativeTransferDialog(SimpleNamespace(documents=lambda:{'documents':[]}),material)
    try:
        app.processEvents()
        assert not window.actions['preview'].isEnabled() and not window.actions['apply'].isEnabled()
        assert not window.detail.isVisible()
        review={'status':'READY_FOR_EXPLICIT_APPLY','mapping':[{'coefficient':'E','source_value':210000000000.,
            'source_unit':'Pa','target_value':210000.,'target_unit':'MPa'}]}
        window.show_review(review);window.show();app.processEvents()
        assert window.summary.item(0,1).text()=='2.1e+11'
        assert window.summary.item(0,3).text()=='210000' and window.summary.item(0,4).text()=='MPa'
        for width,height in ((960,800),(820,740)):
            window.resize(width,height);app.processEvents()
            assert window.grab().save(str(tmp_path/f'transfer-{width}.png'))
        window.raw.setPlainText('1e');window.raw.document().setModified(True)
        window.pending={'id':'Cunconfirmed'};window.reject()
        assert window.isVisible() and window.raw.toPlainText()=='1e'
        assert '재조회' in window.note.text()
        window.pending=None;window.raw.document().setModified(False)
        window.reject();assert not window.isVisible()
    finally:
        window.pending=None;window.raw.document().setModified(False);window._finish_close();app.processEvents()


def wait_for(app,predicate):
    deadline=time.monotonic()+8
    while time.monotonic()<deadline:
        app.processEvents()
        if predicate():return
        time.sleep(.01)
    raise AssertionError('Qt/HTTP transition did not finish')


@pytest.fixture
def live_transfer(tmp_path):
    from apps.lab.server import LabHTTPServer
    from apps.lab.service import LabService
    from caelab.workbench_client import Client
    from apps.research.law_native_transfer_dialog import LawNativeTransferDialog
    from apps.desktop_pre.law_native_material import OPERATIONS
    app=QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    server=LabHTTPServer(LabService(tmp_path/'store'),0)
    thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.02},daemon=True);thread.start()
    client=Client('http://127.0.0.1:'+str(server.server_port));window=None
    descriptor={'id':'Pfixture','title':'공개 시편','kind':'pre','generation':0,'view_generation':0,
        'capabilities':list(OPERATIONS),'objects':[
            {'id':name,'label':name,'type':kind} for name,kind in (
                ('Analysis','Fem::FemAnalysis'),('Material','Fem::MaterialCommon'),
                ('Mesh','Fem::FemMeshObject'),('Solver','Fem::SolverCcxTools'))],
        'fem':{'regions':[{'id':'Rsolid','label':'전체 솔리드'}]}}
    registration=server.workbench.native_commands.register(host_id='Hfixture',session_id='Sfixture',
        application='freecad',version='CONTROLLED_NATIVE_BOUNDARY',execution_mode='headless',
        documents=[descriptor],registration_nonce='r'*64)
    try:
        material=client.document_open(kind='material',draft=default_draft())
        material=client.document_command(material['id'],'document.save',{},session_id=material['session_id'],
            expected_generation=material['generation'])['document']
        window=LawNativeTransferDialog(client,material);window.show()
        wait_for(app,lambda:window.target is not None and not window._busy and all(b.currentData() for b in window.fields.values()))
        yield app,server.workbench,client,window,descriptor,registration
    finally:
        if window is not None:
            wait_for(app,lambda:not window._busy)
            window.pending=None;window.raw.document().setModified(False);window._finish_close();app.processEvents()
        server.shutdown();server.server_close();thread.join(3)


def complete_native(wb,descriptor,registration,payload):
    commands=wb.native_commands
    queued=commands.next('Hfixture',session_id='Sfixture',host_token=registration['host_token'])['command']
    commands.event('Hfixture',session_id='Sfixture',host_token=registration['host_token'],event='started',command_id=queued['command_id'])
    commands.event('Hfixture',session_id='Sfixture',host_token=registration['host_token'],event='finished',
        command_id=queued['command_id'],outcome={'state':'SUCCEEDED','result':{'status':'COMPLETED','result':payload}},documents=[descriptor])
    return queued


def test_http_source_rejection_unlocks_transfer_without_replaying(live_transfer):
    from caelab.material_fe_transfer import make_review
    from caelab import law_native_fe as fe
    from caelab.storage import canonical_hash
    app,wb,client,window,descriptor,registration=live_transfer
    window.preview();wait_for(app,lambda:not window._busy)
    command=next(iter(wb.native_commands._commands.values()))
    mesh=fe.cube_mesh()
    target={'mesh':mesh,'mesh_sha256':canonical_hash(mesh),'admission_errors':[]}
    review=make_review(command['arguments']['_source_snapshot'],target,command['arguments']['options'])
    complete_native(wb,descriptor,registration,{'review':review})
    window.poll();wait_for(app,lambda:window.pending is None and not window._busy)
    draft=deepcopy(window.material['draft']);draft['settings']['parameters']['k0']=290.
    material=client.document_read(window.material['id'])
    client.document_command(material['id'],'material.update',{'draft':draft},session_id=material['session_id'],
        expected_generation=material['generation'])
    window.raw.setPlainText('1e');window.raw.document().setModified(True)
    window.submit('pre.fem.law_apply',{'review_command_id':window.preview_command},lambda *args:None)
    wait_for(app,lambda:window.pending is None and not window._busy)
    assert '등록되지 않았습니다' in window.note.text()
    assert window.review is None and window.actions['refresh'].isEnabled()
    assert window.raw.toPlainText()=='1e' and len(wb.native_commands._commands)==1


@pytest.mark.parametrize('registered',[False,True])
def test_lost_http_response_retries_exact_request_and_preserves_later_text(live_transfer,monkeypatch,registered):
    from urllib.error import URLError
    app,wb,client,window,descriptor,registration=live_transfer
    original=client.document_command;calls=[]
    def lost_once(**request):
        calls.append(deepcopy(request))
        if len(calls)==1:
            if registered:original(**request)
            raise URLError('Controlled lost HTTP response')
        return original(**request)
    monkeypatch.setattr(client,'document_command',lost_once)
    window.raw.setPlainText('1e');window.raw.document().setModified(True);window.save_draft()
    wait_for(app,lambda:not window._busy)
    assert window.pending['unconfirmed'] and len(wb.native_commands._commands)==int(registered)
    window.raw.setPlainText('나중 편집');window.raw.document().setModified(True)
    if not registered:
        window.poll();wait_for(app,lambda:not window._busy)
        assert window.pending['unconfirmed']  # A missing status alone never proves nonexecution.
    window.recover_pending();wait_for(app,lambda:not window._busy)
    assert len(calls)==2 and calls[0]==calls[1] and len(wb.native_commands._commands)==1
    complete_native(wb,descriptor,registration,{})
    window.poll();wait_for(app,lambda:window.pending is None and not window._busy)
    assert window.raw.toPlainText()=='나중 편집' and window.raw.document().isModified()


def test_unregistered_lost_request_then_native_change_unlocks_after_exact_rejection(live_transfer,monkeypatch):
    from urllib.error import URLError
    app,wb,client,window,descriptor,registration=live_transfer
    original=client.document_command;calls=[]
    def lost_once(**request):
        calls.append(deepcopy(request))
        if len(calls)==1:raise URLError('Controlled request lost before registration')
        return original(**request)
    monkeypatch.setattr(client,'document_command',lost_once)
    window.raw.setPlainText('1e');window.raw.document().setModified(True);window.save_draft()
    wait_for(app,lambda:not window._busy)
    assert window.pending['unconfirmed'] and not wb.native_commands._commands
    descriptor['generation']=1
    wb.native_commands.event('Hfixture',session_id='Sfixture',host_token=registration['host_token'],
        event='heartbeat',documents=[descriptor])
    window.recover_pending();wait_for(app,lambda:window.pending is None and not window._busy)
    assert len(calls)==2 and calls[0]==calls[1]
    assert not wb.native_commands._commands and window.actions['refresh'].isEnabled()
    assert window.review is None and window.target['generation']==1
    assert window.raw.toPlainText()=='1e' and '등록되지 않았습니다' in window.note.text()


def test_law_fit_menu_opens_existing_coefficient_and_holdout_plan(live_transfer):
    app,wb,client,transfer,descriptor,registration=live_transfer
    window=LawNativeMaterialWindow(client,auto_open=False,poll_interval=0);numerical=None
    try:
        window._show_document(transfer.material)
        numerical=window.open_numerical_plan()
        assert numerical
        wait_for(app,lambda:numerical.document is not None and not numerical._busy)
        draft=numerical.document['draft']
        assert draft['mode']=='fit' and draft['material']['document_id']==transfer.material['id']
        assert {v['id'] for v in draft['variables']}=={'E','nu','alpha','beta','k0','H'}
        assert draft['experiments']==[] and wb.manager.list()==[]
    finally:
        if numerical:numerical._allow_close=True;numerical.close()
        window._allow_close=True;window.close();app.processEvents()


def test_law_error_views_keep_draft_and_original_cause(live_transfer,tmp_path):
    """Actual Qt display, controlled service failures; no native/solver claim."""
    app,wb,client,transfer,descriptor,registration=live_transfer
    window=LawNativeMaterialWindow(client,auto_open=False,poll_interval=0)
    review={'status':'READY_FOR_EXPLICIT_APPLY','mapping':[{'coefficient':'E','source_value':210000000000.,
        'source_unit':'Pa','target_value':210000.,'target_unit':'MPa'}]}
    source_error='SOURCE_CONFLICT: source revision/working input changed after review Mfixture'
    solver_error='Select the Analysis CalculiX solver as the native context; FELUPE performs this specimen run Pfixture'
    try:
        window._show_document(transfer.material);window.show();window.resize(1440,900)
        original=deepcopy(window.edited_draft());app.processEvents()
        assert window.grab().save(str(tmp_path/'material-normal-1440.png'))
        window.local_dirty=True;window.open_transfer()
        assert not window._law_windows and window.edited_draft()==original
        window.local_dirty=False
        def source_failure():raise ValueError(source_error)
        window._call(source_failure,lambda _:pytest.fail('failure called success handler'))
        wait_for(app,lambda:not window._busy)
        assert source_error not in window.message.text() and source_error in window.messages.toPlainText()
        assert window.edited_draft()==original and not window.local_dirty
        assert window.grab().save(str(tmp_path/'material-error-1440.png'))
        window.details_action.setChecked(True);app.processEvents()
        assert window.grab().save(str(tmp_path/'material-error-details-1440.png'))

        transfer.show_review(review);transfer.summary.selectRow(0);transfer.resize(820,740);app.processEvents()
        assert transfer.grab().save(str(tmp_path/'transfer-normal-820.png'))
        transfer.raw.setPlainText('1e');transfer.raw.document().setModified(True)
        def solver_failure():raise ValueError(solver_error)
        transfer._call(solver_failure,lambda _:pytest.fail('failure called success handler'))
        wait_for(app,lambda:not transfer._busy)
        assert solver_error not in transfer.note.text() and solver_error in transfer.detail.toPlainText()
        assert transfer.raw.toPlainText()=='1e' and transfer.raw.document().isModified()
        assert transfer.summary.item(0,3).text()=='210000' and transfer.summary.item(0,4).text()=='MPa'
        assert transfer.pending is None and wb.manager.list()==[]
        assert transfer.grab().save(str(tmp_path/'transfer-error-820.png'))
        transfer.details_toggle.setChecked(True);app.processEvents()
        assert transfer.grab().save(str(tmp_path/'transfer-error-details-820.png'))
        failed={'command_id':'Cdisplay','state':'FAILED','outcome':{'error':solver_error}}
        transfer.pending={'id':'Cdisplay','done':lambda *_:None}
        transfer.handle_status(failed)
        assert transfer.pending is None and solver_error in transfer.detail.toPlainText()
        assert '실패' in transfer.note.text() and 'FAILED' not in transfer.note.text()
        transfer.fields['mesh_id'].setCurrentIndex(-1)
        transfer.submit('pre.fem.law_preview',{},lambda *_:pytest.fail('missing selection submitted'))
        assert transfer.pending is None and not wb.native_commands._commands
        assert transfer.raw.toPlainText()=='1e' and transfer.raw.document().isModified()
    finally:
        window._allow_close=True;window.close();app.processEvents()


def test_physical_error_views_keep_constraints_and_units(live_transfer,tmp_path):
    """Actual declaration validation and Qt; the native receipt is controlled."""
    from apps.research.law_native_transfer_dialog import law_error_text
    from caelab.material_fe_transfer import make_review
    from caelab import law_native_fe as fe
    from caelab.storage import canonical_hash
    from PySide6.QtTest import QTest
    app,wb,client,transfer,descriptor,registration=live_transfer
    document=client.document_open(kind='material',draft=default_draft(model='single_branch_maxwell'))
    window=LawNativeMaterialWindow(client,auto_open=False,poll_interval=0)
    try:
        window._show_document(document);window.show();window.resize(1440,900)
        field=window.fields[('settings','parameters','tau')][0]
        field.setFocus();field.selectAll();QTest.keyClicks(field,'1e-8')
        window.validate_inputs();wait_for(app,lambda:not window._busy)
        assert '[1e-6,1e6] s' in window.issue_summary.text()
        assert window._input_checks[0]['message']=='SLS tau requires [1e-6,1e6] s'
        assert window.edited_draft()['settings']['parameters']['tau']==1e-8 and window.local_dirty
        assert window.grab().save(str(tmp_path/'material-tau-error-1440.png'))

        transfer.boundary.setCurrentIndex(1);transfer.preview();wait_for(app,lambda:not transfer._busy)
        command=next(iter(wb.native_commands._commands.values()))
        mesh=fe.cube_mesh();target={'mesh':mesh,'mesh_sha256':canonical_hash(mesh),'admission_errors':[]}
        review=make_review(command['arguments']['_source_snapshot'],target,command['arguments']['options'])
        assert review['errors']==['Uniaxial FE pair requires explicit zero yy/zz point stress controls']
        complete_native(wb,descriptor,registration,{'review':review})
        transfer.poll();wait_for(app,lambda:transfer.pending is None and not transfer._busy)
        assert all(part in transfer.summary_title.text() for part in ('yy','zz','0'))
        assert not transfer.actions['apply'].isEnabled() and review['errors'][0] in transfer.detail.toPlainText()
        transfer.resize(820,740);app.processEvents()
        assert transfer.grab().save(str(tmp_path/'transfer-free-lateral-error-820.png'))

        # A compound blocked review must not collapse independent mesh constraints.
        errors=['Native Hex8 ordering/Jacobian differs from the declared SMESH convention; no guessed repair',
                'Small FE mesh requires 1..512 Hex8 cells',
                'Hex8 connectivity must contain eight distinct existing zero-based nodes',
                'DP: E,k0>0; -.99<=nu<.495; 0<=beta<=alpha<=1; H>=0']
        transfer.show_review({'status':'BLOCKED','errors':errors,'mapping':[]})
        text=transfer.summary_title.text()
        assert all(part in text for part in ('Jacobian','SMESH','1..512','8','0','-.99<=nu<.495','0<=beta<=alpha<=1'))
        assert '다른 요소를 자동 변환' not in text
        assert '1e9 MPa' in law_error_text('E: exceeds admitted 1e9 MPa scale')
        assert wb.manager.list()==[]
    finally:
        window._allow_close=True;window.close();app.processEvents()
