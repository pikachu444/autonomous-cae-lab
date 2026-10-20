"""Actual offscreen Qt owner/editor checks; no PDE backend is run."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'

from copy import deepcopy
import time

import pytest
pytest.importorskip('PySide6')
pytest.importorskip('matplotlib')
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox

from apps.research.pde_window import PDEWindow, typed_value
from caelab.pde_document import PDEDocuments, default_draft


class EmptyJobs:
    def list(self):
        return []


class OwnerClient:
    def __init__(self, root):
        def absent(*args, **kwargs):
            raise AssertionError('Native evaluation forbidden in this edit/save UI test')
        self.owner = PDEDocuments(root, 'Sqt', absent, EmptyJobs())
        self.calls = []

    def document_open(self, **kwargs):
        assert kwargs.pop('kind') == 'pde'
        self.calls.append(('open', deepcopy(kwargs)))
        return self.owner.open(**kwargs)

    def document_read(self, identifier):
        return self.owner.read(identifier)

    def document_command(self, identifier, operation, arguments, **options):
        self.calls.append((operation, deepcopy(arguments)))
        return self.owner.command(identifier, operation, arguments, **options)

    def documents(self):
        return self.owner.list()


@pytest.fixture(scope='module')
def app():
    instance = QApplication.instance() or QApplication([])
    yield instance


def settle(app, window, predicate=lambda: True):
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        app.processEvents()
        if not window._busy and predicate():
            app.processEvents()
            return
        QTest.qWait(10)
    raise AssertionError('Offscreen owner/editor operation did not finish: ' + window.message.text())


@pytest.fixture
def window(app, tmp_path):
    result = PDEWindow(OwnerClient(tmp_path), poll_interval=0)
    result.show()
    settle(app, result, lambda: result.document is not None)
    yield result
    settle(app, result)
    result._allow_close = True
    result.close()
    app.processEvents()


def edit(window, path, value):
    widget = window.fields[path][0]
    widget.setFocus()
    if hasattr(widget, 'toPlainText'):
        widget.selectAll()
    else:
        widget.selectAll()
    QTest.keyClicks(widget, value)


def test_selected_property_question_keeps_exact_scope(window, app, monkeypatch):
    opened = []
    monkeypatch.setattr('apps.research.selection_discussion.open_discussion',
        lambda client, **arguments: opened.append(arguments))
    path = ('settings', 'problem', 'weak_form')
    window.tree.setCurrentItem(window._nodes[path])
    window.discuss_action.trigger()
    settle(app, window, lambda: bool(opened))
    assert opened[0]['document']['id'] == window.document['id']
    assert opened[0]['job_id'] is None
    assert opened[0]['selection'] == {'scope': {'kind': 'model', 'path': path}}
    assert all(call[0] != 'pde.evaluate' for call in window.client.calls)


def test_actual_typed_equation_invalid_save_undo_reopen(window, app):
    window.tree.setCurrentItem(window._nodes[('settings', 'problem', 'weak_form')])
    original = deepcopy(window.document['draft'])
    edit(window, ('settings', 'problem', 'weak_form', 'rhs'), 'sin(')
    window.validate_inputs()
    settle(app, window)
    assert window.local_dirty and '오류' in window.message.text()
    window.save_document()
    settle(app, window, lambda: bool(window.document['saved_revision']))
    identifier = window.document['id']
    assert window.document['draft']['settings']['problem']['weak_form']['rhs'] == 'sin('
    assert window.document['diagnostics'] and not window.evaluate_button.isEnabled()
    assert not window.document['dirty']
    window.command('document.undo')
    settle(app, window)
    assert window.document['draft'] == original
    # The editor must not accidentally reapply old widgets while showing Undo.
    assert window.edited_draft() == original
    window.command('document.redo')
    settle(app, window)
    assert window.document['draft']['settings']['problem']['weak_form']['rhs'] == 'sin('
    window.open_document(document_id=identifier)
    settle(app, window)
    assert window.document['diagnostics']
    assert not any(name == 'pde.evaluate' for name, _ in window.client.calls)


def test_domain_boundaries_space_and_time_are_separate_editable_nodes(window, app):
    draft = default_draft('pde.fenicsx.transient')
    window.open_document(draft=draft)
    settle(app, window)
    for path in [('settings', 'problem', 'domain'), ('settings', 'mesh', 'degree'),
                 ('settings', 'problem', 'initial'), ('settings', 'problem', 'boundaries', 'xmin'),
                 ('settings', 'time'), ('settings', 'validation')]:
        window.tree.setCurrentItem(window._nodes[path])
        assert window.fields
    window.tree.setCurrentItem(window._nodes[('settings', 'time')])
    edit(window, ('settings', 'time', 'end'), 'unfinished')
    window.tree.setCurrentItem(window._nodes[('settings', 'problem', 'initial')])
    edit(window, ('settings', 'problem', 'initial', 'value'), '0.0')
    assert window.edited_draft()['settings']['time']['end'] == 'unfinished'
    window.apply_inputs()
    settle(app, window)
    assert window.document['diagnostics']
    window.save_document()
    settle(app, window)
    assert window.document['saved_revision']


def test_list_record_nodes_edit_only_selected_user_state_and_preserve_raw_on_switch(window, app, monkeypatch):
    draft = default_draft('pde.scipy.ode')
    draft['settings']['states'][0]['label'] = '사용자 상태'
    second = deepcopy(draft['settings']['states'][0])
    second.update(name=second['name']+'_second', label='두 번째 상태')
    draft['settings']['states'].append(second)
    window.open_document(draft=draft); settle(app, window)
    before = deepcopy(window.client.owner.read(window.document['id']))
    first_path = ('settings','states',0)
    second_path = ('settings','states',1)
    assert window._nodes[first_path].text(0) == '사용자 상태 [' + draft['settings']['states'][0]['unit'] + ']'
    assert window._nodes[second_path].text(0).startswith('두 번째 상태')
    window.tree.setCurrentItem(window._nodes[first_path])
    assert all(path[:3] == first_path for path in window.fields)
    label=window.fields[(*first_path,'label')][0]
    label.setFocus();label.setText('편집한 사용자 상태');label.textEdited.emit(label.text())
    label.setCursorPosition(3)
    window._update_actions()
    assert window._nodes[first_path].text(0).startswith('편집한 사용자 상태')
    assert label.hasFocus() and label.cursorPosition()==3
    edit(window, (*first_path,'initial'), '1e')
    window.tree.setCurrentItem(window._nodes[second_path])
    assert all(path[:3] == second_path for path in window.fields)
    assert window.edited_draft()['settings']['states'][0]['initial'] == '1e'
    window.tree.setCurrentItem(window._nodes[first_path])
    assert window.fields[(*first_path,'initial')][0].text() == '1e'
    assert window.edited_draft()['settings']['states'][1] == second
    assert window.client.owner.read(before['id'])['draft'] == before['draft']
    questions=[]
    def cancel(*args,**kwargs):
        questions.append(args[1:3])
        return QMessageBox.StandardButton.Cancel
    monkeypatch.setattr(QMessageBox,'question',cancel)
    continued=[];window._abandon(lambda:continued.append(True))
    assert not continued and window.fields[(*first_path,'initial')][0].text() == '1e'
    assert questions==[('모델 저장','현재 모델의 변경 내용을 저장할까요?')]
    window.save_document(); settle(app, window)
    saved=window.client.owner.open(document_id=before['id'])
    assert saved['draft']['settings']['states'][0]['initial'] == '1e'
    assert saved['draft']['settings']['states'][1] == second
    assert not saved['runs']


def test_save_before_open_continues_after_owner_save(window, app, monkeypatch):
    original = window.document['id']
    window.tree.setCurrentItem(window._nodes[('settings', 'problem', 'weak_form')])
    edit(window, ('settings', 'problem', 'weak_form', 'diffusion'), '2')
    monkeypatch.setattr(QMessageBox, 'question', lambda *args, **kwargs: QMessageBox.StandardButton.Save)
    window._abandon(lambda: window.open_document(title='Second document', draft=default_draft('pde.fenicsx.coupled')))
    settle(app, window, lambda: window.document['id'] != original)
    old = window.client.owner.read(original)
    assert old['saved_revision'] and old['draft']['settings']['problem']['weak_form']['diffusion'] == 2
    assert window.document['draft']['backend'] == 'pde.fenicsx.coupled'


def test_malformed_backend_and_settings_remain_openable(window, app):
    draft = {'backend': [], 'settings': {'problem': []}, 'hidden': {'preserved': True}}
    window.open_document(draft=draft)
    settle(app, window)
    assert window.edited_draft() == draft
    window.validate_inputs()
    settle(app, window)
    window.save_document()
    settle(app, window)
    assert window.document['draft'] == draft and window.document['diagnostics']


def test_exact_field_components_nodes_time_and_post_study(window, app):
    opened = []
    window.result_open = lambda *args, **kwargs: opened.append((args, kwargs))
    window._selected_job = 'Jretained'
    result = {'execution_status': 'SUCCEEDED', 'responses': {}, 'checks': [], 'diagnostics': {
        'fixture': 'SOFTWARE DISPLAY FIXTURE, NO PHYSICS RUN', 'native_fields': [
            {'name': 'recorded time field', 'study_index': 2, 'step_index': 4, 'time': .25,
             'source': {'artifact': 'pde/study_2/step_4/dofs.json', 'sha256': 'b'*64},
             'field': {'node_ids': [100, 900, 700], 'coordinates': [[0, 0], [1, 0], [0, 1]],
                       'values': [[1, 10], [2, 20], [3, 30]], 'components': ['u0', 'u1'],
                       'coordinates_unit': '1', 'field_unit': '1'}}]}}
    window._accept_result(result)
    window.result_selector.setCurrentIndex(1)
    window.field_node.setCurrentIndex(window.field_node.findData(900))
    app.processEvents()
    assert '절점 900' in window.point_label.text() and '값 20' in window.point_label.text()
    assert '시간 0.25 [1]' in window.point_label.text()
    assert 'b'*64 not in window.point_label.text()
    assert 'b'*64 in window.point_label.toolTip()
    assert len(window.result_figure.axes) == 2  # One field axes and one colorbar; no accumulated colorbars.
    window.open_post()
    assert opened == [((window.document['id'], 'Jretained'), {'study_index': 2})]
    assert not window.client.calls[-1][0].startswith('pde.evaluate')


def test_typed_repair_never_evaluates_or_erases_invalid_original():
    assert typed_value('bad', 'bad', ('settings', 'mesh', 'degree')) == 'bad'
    assert typed_value('2', 'bad', ('settings', 'mesh', 'degree')) == 2
    assert typed_value('nan', 1, ('settings', 'problem', 'weak_form', 'diffusion')) == 'nan'
    assert typed_value('3', 'bad', ('settings', 'problem', 'weak_form', 'diffusion', 'left', 0, 1)) == 3


def test_open_chooser_reads_real_workbench_documents_envelope(window, app, monkeypatch):
    from PySide6.QtWidgets import QInputDialog
    first = window.document['id']
    second = window.client.owner.open(title='Another PDE model')
    window.client.documents = lambda: {'service_session_id': 'Sqt', 'documents': window.client.owner.list()}
    seen = []
    def choose(*args, **kwargs):
        choices = args[3]
        seen.extend(choices)
        return next(choice for choice in choices if second['id'] in choice), True
    monkeypatch.setattr(QInputDialog, 'getItem', choose)
    monkeypatch.setattr(QMessageBox, 'question', lambda *args, **kwargs: QMessageBox.StandardButton.Discard)
    window.choose_document()
    settle(app, window, lambda: window.document['id'] != first)
    assert window.document['id'] == second['id'] and len(seen) == 2


def test_standalone_launcher_matches_desktop_document_id_and_navigation(monkeypatch):
    from types import SimpleNamespace
    from apps.research import pde_window, desktop,result_return
    opened, navigation = [], []
    class Window:
        def __init__(self, client, **kwargs):
            opened.append((client, kwargs))
        def show(self):
            pass
    monkeypatch.setattr(pde_window, 'PDEWindow', Window)
    checked=[]
    def activate(client,identifier,**kwargs):
        checked.append((identifier,kwargs));return {'status':'ABSENT'}
    monkeypatch.setattr(result_return,'activate_existing',activate)
    monkeypatch.setattr(pde_window, 'QApplication', SimpleNamespace(instance=lambda: SimpleNamespace(exec=lambda: 0)))
    monkeypatch.setattr(desktop, 'launch_tool', lambda *args, **kwargs: navigation.append(('runner', args, kwargs)))
    monkeypatch.setattr(desktop, 'open_document_result', lambda *args, **kwargs: navigation.append(('post', args, kwargs)), raising=False)
    assert pde_window.main(['--service', 'http://127.0.0.1:9912', '--document-id', 'Qselected']) == 0
    client, options = opened[0]
    assert options['document_id'] == 'Qselected' and client.url == 'http://127.0.0.1:9912'
    assert checked==[('Qselected',{'kind':'pde'})]
    options['runner_open']('Jrecorded')
    options['result_open']('Qselected', 'Jrecorded', study_index=2)
    assert navigation[0] == ('runner', (client, 'runner'), {'job_id': 'Jrecorded'})
    assert navigation[1] == ('post', (client, 'Qselected', 'Jrecorded'), {'study_index': 2})
    monkeypatch.delenv('CAELAB_SERVICE_URL', raising=False)
    with pytest.raises(SystemExit) as error:
        pde_window.main([])
    assert error.value.code == 2


def test_numerical_plan_requires_applied_generation_and_retries_same_creation(window, app):
    calls = []
    first = True
    def open_plan(identifier, **options):
        nonlocal first
        calls.append((identifier, options))
        if first:
            first = False
            raise RuntimeError('TEST ONLY: creation response lost; retry the same command')
        return {'document_id': 'Nfrozenrequest', 'executed': False, 'status': 'LAUNCH_REQUESTED'}
    window.plan_open = open_plan
    assert window.plan_button.isEnabled() and window.plan_action.isEnabled()
    assert window.document['runs'] == []
    window.tree.setCurrentItem(window._nodes[('settings', 'problem', 'weak_form')])
    edit(window, ('settings', 'problem', 'weak_form', 'diffusion'), '3')
    assert not window.plan_button.isEnabled()
    assert window.open_numerical_plan() is False
    assert '변경 적용' in window.message.text() and calls == []
    window.apply_inputs()
    settle(app, window)
    assert window.document['generation'] == 1 and window.plan_button.isEnabled()
    window.open_numerical_plan()
    settle(app, window)
    assert 'response lost' in window.message.text() and window.plan_button.isEnabled()
    window.open_numerical_plan()
    settle(app, window)
    assert len(calls) == 2 and calls[0] == calls[1]
    identifier, options = calls[1]
    assert identifier == window.document['id']
    assert options['session_id'] == window.document['session_id'] and options['expected_generation'] == 1
    assert options['command_id'].startswith('C')
    assert '계산은 아직 시작하지 않았습니다' in window.message.text()
    assert 'Nfrozenrequest' not in window.message.text()
    assert 'Nfrozenrequest' in window.messages.toPlainText()
    assert window.document['runs'] == []
    assert not any(operation == 'pde.evaluate' for operation, _ in window.client.calls)


@pytest.fixture
def http_window(app, tmp_path, request):
    """Real HTTP commands/receipts, with every numerical submission forbidden."""
    import threading
    from apps.lab.server import LabHTTPServer
    from apps.lab.service import LabService
    from caelab.workbench_client import Client
    from apps.research.simulation_window import SimulationWindow
    from caelab.simulation_document import default_draft as simulation_draft
    kind=request.param
    server=LabHTTPServer(LabService(tmp_path/'사용자 모델 저장소'),0)
    thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.02},daemon=True)
    thread.start();win=None
    try:
        def forbidden(*args,**kwargs):raise AssertionError('Numerical submission forbidden in command recovery checks')
        server.workbench.submit=server.workbench.manager.submit=forbidden
        for owner in server.workbench.research_owners():owner.submit=forbidden
        client=Client('http://127.0.0.1:'+str(server.server_port))
        draft=default_draft('pde.scipy.ode') if kind=='pde' else simulation_draft('thermal.scikit_fem.rectangle')
        cls=PDEWindow if kind=='pde' else SimulationWindow
        doc=client.document_open(kind=kind,title='사용자 조건 모델',draft=draft)
        win=cls(client,auto_open=False,poll_interval=0);win._opened(doc);win.show();app.processEvents()
        path=('settings','states',0,'initial') if kind=='pde' else ('settings','boundary_gradient','values',0)
        parent=next(path[:n] for n in range(len(path),0,-1) if path[:n] in win._nodes)
        win.tree.setCurrentItem(win._nodes[parent]);app.processEvents()
        yield win,client,server.workbench,path
    finally:
        if win:
            settle(app,win);win._allow_close=True;win.close();app.processEvents()
        server.shutdown();server.server_close();thread.join(5)
        assert not thread.is_alive() and server.workbench.shutdown()['joined']


@pytest.mark.parametrize('http_window',['pde','simulation'],indirect=True)
@pytest.mark.parametrize('operation',['save','update','save_with_update'])
def test_http_lost_ack_retry_keeps_same_request_late_edit_and_blocks_switch(http_window,app,monkeypatch,operation):
    win,client,wb,path=http_window
    original=client.document_command;calls=[];lost=[True]
    def lose_once(identifier,op,args,**options):
        calls.append((identifier,op,deepcopy(args),deepcopy(options)))
        receipt=original(identifier,op,args,**options)
        if lost[0]:lost[0]=False;raise TimeoutError('CONTROLLED committed response loss')
        return receipt
    monkeypatch.setattr(client,'document_command',lose_once)
    if operation in ('update','save_with_update'):
        edit(win,path,'2')
        if operation=='save_with_update':win.save_document()
        else:win.apply_inputs()
    else:win.save_document()
    settle(app,win)
    pending=win._pending_command
    assert pending and pending['uncertain'] and len(calls)==1
    first=deepcopy(client.document_read(win.document['id']))
    edit(win,path,'1e')
    selected=win.tree.currentItem().data(0,Qt.ItemDataRole.UserRole)
    assert win.open_document(title='Must not replace the current model') is False
    assert win.new_document() is False
    assert win.choose_document() is False
    assert win.command(win.document_kind+'.evaluate') is False
    win.save_document();win.apply_inputs()
    monkeypatch.setattr(QMessageBox,'question',lambda *args,**kwargs:pytest.fail('Pending close must not ask to discard'))
    win.close();app.processEvents()
    assert win.isVisible() and len(calls)==1 and win._pending_command is pending
    if win.document_kind=='simulation':
        monkeypatch.setattr(win,'_impact_source_run',lambda:{'job_id':'Jretained'})
        assert win.reprocess_impact() is False
    assert not win.save_action.isEnabled() and win.retry_action.isEnabled()
    win.retry_command();settle(app,win)
    assert calls[0]==calls[1] and win._pending_command is None
    assert win.local_dirty and win.fields[path][0].text()=='1e'
    assert win.tree.currentItem().data(0,Qt.ItemDataRole.UserRole)==selected
    after=client.document_read(win.document['id'])
    assert after['generation']==first['generation'] and after['saved_revision']==first['saved_revision']
    assert after['draft']==first['draft'] and not wb.manager.list()
    assert len(list(wb._document_owner(after['id'])._folder(after['id']).joinpath('commands').glob('*.json')))==1


@pytest.mark.parametrize('http_window',['pde','simulation'],indirect=True)
@pytest.mark.parametrize('rejection',['generation','session'])
def test_http_definite_generation_rejection_preserves_buffer_and_unlocks_recovery(http_window,app,rejection):
    from caelab.storage import canonical_hash, load_json
    win,client,wb,path=http_window
    doc=deepcopy(win.document)
    if rejection=='generation':
        from apps.research.pde_window import set_path
        external=deepcopy(doc['draft']);set_path(external,path,3.)
        client.document_command(doc['id'],win.document_kind+'.update',{'draft':external},
            session_id=doc['session_id'],expected_generation=doc['generation'],command_id='CexternalEdit')
    else:wb._document_owner(doc['id']).session_id='SreplacementOwner'
    before=client.document_read(doc['id'])
    edit(win,path,'1e');win.apply_inputs()
    pending=deepcopy(win._pending_command)
    settle(app,win)
    assert win._pending_command is None and win.conflict
    assert win.fields[path][0].text()=='1e' and win.local_dirty
    assert win.reload_button.isVisible() and not wb.manager.list()
    receipts={p.stem:load_json(p) for p in wb._document_owner(doc['id'])._folder(doc['id']).joinpath('commands').glob('*.json')}
    if rejection=='generation':
        # The external edit applied once; the stale local command has its own
        # definite rejection receipt so retrying that UUID cannot apply it.
        assert set(receipts)=={'CexternalEdit',pending['command_id']}
        assert 'response' in receipts['CexternalEdit']
        rejected=receipts[pending['command_id']]
        assert rejected['state']=='REJECTED' and 'response' not in rejected
        assert rejected['operation']==win.document_kind+'.update'
        assert rejected['rejection']=='Document generation changed; reread before applying'
        assert rejected['request_hash']==canonical_hash(dict(document_id=doc['id'],operation=pending['operation'],
            arguments=pending['arguments'],session_id=doc['session_id'],expected_generation=doc['generation']))
    else:assert receipts=={}
    after=client.document_read(doc['id'])
    assert after['generation']==before['generation'] and after['draft']==before['draft']


@pytest.mark.parametrize('http_window',['pde','simulation'],indirect=True)
def test_http_rejection_after_lost_ack_and_post_receipt_400_remain_uncertain(http_window,app,monkeypatch):
    win,client,wb,path=http_window
    original=client.document_command
    def lost(*args,**kwargs):
        original(*args,**kwargs);raise TimeoutError('CONTROLLED committed response loss')
    monkeypatch.setattr(client,'document_command',lost)
    win.save_document();settle(app,win);pending=win._pending_command
    assert pending and pending['uncertain']
    owner=wb._document_owner(win.document['id'])
    owner.session_id='SreplacementOwner'
    monkeypatch.setattr(client,'document_command',original)
    edit(win,path,'1e');win.retry_command();settle(app,win)
    assert win._pending_command is pending and win.fields[path][0].text()=='1e'
    assert not pending['not_applied'] and not wb.manager.list()
    # A different known 400 can occur after APPLYING. It is not proof that a
    # fresh request had no effect, even without a previous transport failure.
    owner.session_id=win.document['session_id'];win.retry_command();settle(app,win)
    assert win._pending_command is None
    win.local_dirty=False;win._draft=deepcopy(win.document['draft']);win._capture_settings()
    # Keep the invalid buffer out of this deliberately malformed save request.
    win.fields={};win.local_dirty=False
    win.command('document.save',{'unexpected':'argument'});settle(app,win)
    assert win._pending_command and win._pending_command['uncertain'] and not wb.manager.list()


@pytest.mark.parametrize('http_window',['pde','simulation'],indirect=True)
@pytest.mark.parametrize('changed_selection',[False,True])
def test_http_lost_evaluate_ack_reuses_single_controlled_submission(http_window,app,monkeypatch,changed_selection):
    """One owner run record, with a controlled submit receipt and no evaluator."""
    win,client,wb,path=http_window
    from caelab.storage import utc_now
    owner=wb._document_owner(win.document['id']);submissions=[];calls=[]
    def controlled_submit(operation,args,**options):
        submissions.append((operation,deepcopy(args),deepcopy(options)))
        return {'id':'JcontrolledSubmission','operation':operation,'arguments':deepcopy(args),
                'created_utc':utc_now(),'request_id':options['request_id'],'state':'QUEUED'}
    monkeypatch.setattr(owner,'submit',controlled_submit)
    monkeypatch.setattr(win,'refresh_result',lambda:None)
    original=client.document_command
    def lost_once(*args,**kwargs):
        calls.append((deepcopy(args),deepcopy(kwargs)))
        result=original(*args,**kwargs)
        if len(calls)==1:raise TimeoutError('CONTROLLED run acknowledgement loss')
        return result
    monkeypatch.setattr(client,'document_command',lost_once)
    win.command(win.document_kind+'.evaluate');settle(app,win)
    assert win._pending_command and len(submissions)==1
    if changed_selection:win._selected_job='JexplicitViewSelection'
    edit(win,path,'1e');win.command(win.document_kind+'.evaluate')
    assert len(calls)==1
    win.retry_command();settle(app,win)
    assert len(submissions)==1 and calls[0]==calls[1]
    assert len(win.document['runs'])==1 and win.local_dirty and win.fields[path][0].text()=='1e'
    assert win._selected_job==('JexplicitViewSelection' if changed_selection else 'JcontrolledSubmission')
    assert not wb.manager.list()  # No actual JobManager execution or solver.


@pytest.mark.parametrize('http_window',['pde','simulation'],indirect=True)
def test_http_delayed_receipt_cannot_replace_another_displayed_owner(http_window,app,monkeypatch):
    import threading
    win,client,wb,path=http_window
    original=client.document_command;started=threading.Event();release=threading.Event()
    def delayed(*args,**kwargs):
        result=original(*args,**kwargs);started.set()
        assert release.wait(5)
        return result
    monkeypatch.setattr(client,'document_command',delayed)
    source=deepcopy(win.document)
    other=client.document_open(kind=win.document_kind,title='다른 사용자 문서',draft=source['draft'])
    try:
        win.save_document()
        deadline=time.monotonic()+5
        while not started.is_set() and time.monotonic()<deadline:app.processEvents();QTest.qWait(10)
        assert started.is_set()
        pending=win._pending_command
        # Force an unexpected display replacement to exercise the late-response
        # gate; ordinary open/new are blocked while the request is unresolved.
        win._show_document(other)
        shown=deepcopy(win.edited_draft());release.set();settle(app,win)
        assert win.document['id']==other['id'] and win.edited_draft()==shown
        assert win._pending_command is pending and not wb.manager.list()
    finally:release.set()
