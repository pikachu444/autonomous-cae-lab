"""Real Qt and shared EvaluationDocuments/JobManager; controlled stage outputs.

No solver, native runtime or inference runs. Only the expensive stage evaluator
boundary is controlled; edits, composition, retry, retention and reads are real.
"""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from copy import deepcopy
import threading
import time

import pytest
pytest.importorskip('PySide6')
pytest.importorskip('matplotlib')
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QInputDialog, QLineEdit
from PySide6.QtTest import QTest

from apps.research.evaluation_window import EvaluationWindow
from caelab.evaluation_definition import (EvaluationDocuments, compile_definition, default_draft,
    document_reference, execute)
from caelab.evaluation import read_result
from caelab.jobs import JobManager, TERMINAL
from caelab.material_document import MaterialDocuments
from caelab.research_operations import result_reference
from caelab.storage import load_json


@pytest.fixture
def application():
    return QApplication.instance() or QApplication([])


def wait(application, predicate, seconds=5):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        application.processEvents()
        if predicate(): return
        time.sleep(.005)
    raise AssertionError('Qt/owner operation did not settle')


class OwnerClient:
    """The existing owner API, without HTTP latency, over actual disk stores."""
    def __init__(self, root, session='Sfirst'):
        self.root, self.session = root, session
        self.stage_calls, self.calls = [], []
        self.fail_second_once = True
        self.manager = JobManager(root / 'jobs', self._execute, workers=1, cpu_budget=1)
        self.material = MaterialDocuments(root, session, self.manager.submit, self.manager)
        self.owner = EvaluationDocuments(root, session, self.manager.submit, self.manager,
            resolve_revision=lambda identifier, revision: self.material._verify_revision(identifier, revision))
        self.progress_entered, self.progress_release = threading.Event(), threading.Event()
        self.delay_progress = False
        self.stage_entered, self.stage_release = threading.Event(), threading.Event()
        self.delay_stage = False

    def _execute(self, operation, arguments, job_id):
        assert operation == 'evaluation.coupled'
        compiled = compile_definition(arguments['definition'], arguments['snapshots'])
        def stage(model, folder):
            self.stage_calls.append(folder.name)
            if folder.name.endswith('Stwo') and self.fail_second_once:
                self.fail_second_once = False
                return {'execution_status': 'FAILED', 'responses': {}, 'checks': [],
                        'diagnostics': {'reason': 'Controlled retained second-stage failure, no solver'}}
            return {'execution_status': 'SUCCEEDED', 'responses': {'cost': {'kind': 'scalar', 'value': 2.,
                'unit': 'MPa', 'component': 'scalar', 'location': 'controlled_fixture', 'reduction': 'none'}},
                'checks': [], 'diagnostics': {'scope': 'Controlled evaluator boundary, no solver'}}
        reuse = arguments['definition'].get('reuse')
        reused_result = read_result(self.manager.root / 'results' / reuse['source']['job_id']) if reuse else None
        return execute(compiled, self.manager.root / 'results' / job_id, stage,
            reuse_result=reused_result, reuse_folder=self.manager.root / 'results' / reuse['source']['job_id'] if reuse else None)

    def close(self):
        self.progress_release.set()
        self.stage_release.set()
        assert self.manager.shutdown()['joined']

    def document_open(self, *, kind='evaluation', **options):
        return (self.owner if kind == 'evaluation' else self.material).open(**{key: value for key, value in options.items() if value is not None})

    def document_read(self, identifier):
        return (self.owner if identifier.startswith('E') else self.material).read(identifier)

    def documents(self):
        return {'documents': self.material.list() + self.owner.list()}

    def document_command(self, identifier, operation, arguments, **options):
        self.calls.append(operation)
        return (self.owner if identifier.startswith('E') else self.material).command(identifier, operation, arguments, **options)

    def evaluation_inspect(self, identifier):
        self.calls.append('inspect')
        return self.owner.inspect_definition(identifier)

    def evaluation_progress(self, identifier, job_id):
        self.calls.append(('progress', identifier, job_id))
        if self.delay_progress:
            self.progress_entered.set()
            assert self.progress_release.wait(4)
        document = self.owner.read(identifier)
        assert any(row['job_id'] == job_id for row in document['runs'])
        return load_json(self.manager.root / 'results' / job_id / 'progress.json')

    def evaluation_stage_result(self, identifier, job_id, attempt_id, selection=None):
        self.calls.append(('stage_result', identifier, job_id, attempt_id))
        if self.delay_stage:
            self.stage_entered.set()
            assert self.stage_release.wait(4)
        progress = load_json(self.manager.root / 'results' / job_id / 'progress.json')
        attempt = next(row for row in progress['stages'] if row['attempt_id'] == attempt_id)
        assert any(row['job_id'] == job_id for row in self.owner.read(identifier)['runs'])
        return read_result(self.manager.root / 'results' / job_id / attempt['result_directory'], selection=selection)

    def document_result_reference(self, identifier, job_id):
        document = self.owner.read(identifier)
        return result_reference(document, job_id, self.owner.result(identifier, job_id))


@pytest.fixture
def editor(tmp_path, application):
    client = OwnerClient(tmp_path)
    source = client.material.open(title='Actual saved Material source')
    source = client.material.command(source['id'], 'document.save', {},
        session_id=source['session_id'], expected_generation=source['generation'])['document']
    draft = default_draft()
    draft['stages'] = [{'id': 'Sone', 'name': 'First controlled stage', 'source': document_reference(source)},
                       {'id': 'Stwo', 'name': 'Second controlled stage', 'source': document_reference(source)}]
    draft['bindings'] = [{'id': 'modulus', 'stage': 'Sone', 'input_id': 'E', 'unit': 'MPa'}]
    draft['responses'] = [{'id': 'cost', 'stage': 'Stwo', 'response': 'cost', 'unit': 'MPa'}]
    document = client.owner.open(title='Real owner / controlled stages', draft=draft)
    window = EvaluationWindow(client, auto_open=False, poll_interval=0)
    window._show_document(document)
    window.inspect_inputs()
    wait(application, lambda: not window._busy)
    try:
        yield window, client, source
    finally:
        client.progress_release.set()
        client.stage_release.set()
        wait(application, lambda: not window._busy)
        window._allow_close = True; window.close(); client.close()


def test_queued_inspection_never_applies_new_local_edits(editor,application,monkeypatch):
    window,client,_=editor
    before=deepcopy(client.document_read(window.document['id']))
    window.iteration_maximum.setText('1e')
    window.iteration_maximum.textEdited.emit('1e')
    assert window.local_dirty
    def forbidden(*a,**k):
        raise AssertionError('An automatic inspection cannot apply local edits')
    monkeypatch.setattr(window,'apply_inputs',forbidden)
    assert window._inspect_saved_inputs() is False
    application.processEvents()
    assert client.document_read(before['id'])==before
    assert window.local_dirty and window.iteration_maximum.text()=='1e'


def test_actual_saved_source_picker_order_bindings_and_callbacks(editor, application, monkeypatch):
    window, client, source = editor
    assert window.tabs.count() == 5 and window.run_button.isEnabled()
    choices = []
    def choose(parent, title, label, items, **options):
        choices.append((title, list(items), options.get('editable')))
        return items[0], True
    monkeypatch.setattr(QInputDialog, 'getItem', choose)
    monkeypatch.setattr(QInputDialog, 'getText', lambda *args, **kwargs: ('new_modulus', True))
    window.add_stage()
    wait(application, lambda: not window._busy and len(window.edited_draft()['stages']) == 3)
    assert window.edited_draft()['stages'][-1]['source'] == document_reference(source)
    window.stage_list.setCurrentRow(2); added_id = window.edited_draft()['stages'][2]['id']
    window.move_stage(-1)
    assert window.edited_draft()['stages'][1]['id'] == added_id
    window.apply_inputs(); wait(application, lambda: not window._busy and not window.local_dirty)
    window.inspect_inputs(); wait(application, lambda: not window._busy)
    window.add_binding()
    binding = window.edited_draft()['bindings'][-1]
    assert binding == {'id': 'new_modulus', 'stage': 'Sone', 'input_id': 'E', 'unit': 'MPa'}
    assert not window.tables['bindings'].item(1, 2).flags() & Qt.ItemFlag.ItemIsEditable
    assert all(editable is False for _, _, editable in choices)
    assert not client.stage_calls and 'evaluation.run' not in client.calls
    opened = []
    window.source_open = lambda reference: opened.append(reference)
    window.stage_list.setCurrentRow(0); window.open_source()
    assert opened == [document_reference(source)]


def test_invalid_typed_cells_save_and_reopen_without_execution(editor, application):
    window, client, _ = editor
    draft = window.edited_draft()
    draft['iteration']['checks'] = [{'stage': 'Sone', 'response': 'cost', 'unit': 'MPa', 'absolute': .1, 'relative': .01, 'scale': 1.}]
    window._replace_draft(draft)
    window.tables['checks'].item(0, 3).setText('unfinished physical tolerance')
    window.iteration_maximum.setText('unfinished iteration budget'); window._edited()
    assert window.local_dirty and not window.run_button.isEnabled() and window.save_button.isEnabled()
    window.save_document(); wait(application, lambda: not window._busy and not window.local_dirty)
    saved = deepcopy(window.document)
    assert saved['draft']['iteration']['checks'][0]['absolute'] == 'unfinished physical tolerance'
    assert saved['draft']['iteration']['maximum'] == 'unfinished iteration budget' and saved['diagnostics']
    reopened = client.owner.open(document_id=saved['id'])
    assert reopened['draft'] == saved['draft'] and not client.stage_calls
    assert 'evaluation.update' in client.calls and 'document.save' in client.calls and 'evaluation.run' not in client.calls


def test_source_conflict_preserves_local_edits(editor, application):
    window, client, _ = editor
    window.tables['stages'].item(0, 1).setText('Unapplied name')
    old = client.owner.read(window.document['id']); changed = deepcopy(old['draft']); changed['stages'][0]['name'] = 'Other owner edit'
    client.owner.command(old['id'], 'evaluation.update', {'draft': changed},
        session_id=old['session_id'], expected_generation=old['generation'])
    window.refresh_document(); wait(application, lambda: not window._busy)
    assert window.conflict and window.edited_draft()['stages'][0]['name'] == 'Unapplied name'
    assert not window.run_button.isEnabled() and window.copy_button.isVisibleTo(window)


def test_real_stage_retention_explicit_retry_reuses_only_successful_prefix(editor, application, monkeypatch):
    window, client, source = editor
    window.run_once()
    wait(application, lambda: not window._busy and bool(window.document['runs']))
    job_id = window.document['runs'][-1]['job_id']
    wait(application, lambda: client.manager.status(job_id)['state'] in TERMINAL)
    window.refresh_document(); wait(application, lambda: not window._busy)
    window.refresh_progress(); wait(application, lambda: not window._busy and window.attempts.rowCount() == 2)
    assert [window.attempts.item(row, 3).data(Qt.ItemDataRole.UserRole) for row in range(2)] == ['SUCCEEDED', 'FAILED']
    assert len(client.stage_calls) == 2
    window.attempts.selectRow(0)
    wait(application, lambda: not window._busy and window.channels.rowCount() == 1)
    assert window.channels.item(0, 0).text() == 'cost' and window.channels.item(0, 5).text() == '2.0'
    assert window.channels.item(0, 6).data(Qt.ItemDataRole.UserRole) == 'SUCCEEDED'
    window.prepare_retry()
    assert '완료된 계산을 먼저 저장' in window.message.text()
    window.save_document(); wait(application, lambda: not window._busy)
    monkeypatch.setattr(QInputDialog, 'getInt', lambda *args, **kwargs: (1, True))
    window.prepare_retry(); wait(application, lambda: not window._busy and window.local_dirty)
    retry = window.edited_draft()['reuse']
    assert retry['stages'] == ['Sone'] and retry['source']['job_id'] == job_id
    assert len(client.stage_calls) == 2 and len(client.manager.list()) == 1
    assert not window.run_button.isEnabled()  # Preparation is an unapplied draft edit.
    window.apply_inputs(); wait(application, lambda: not window._busy and not window.local_dirty)
    window.run_once(); wait(application, lambda: not window._busy and len(window.document['runs']) == 2)
    retry_job = window.document['runs'][-1]['job_id']
    wait(application, lambda: client.manager.status(retry_job)['state'] in TERMINAL)
    assert client.manager.status(retry_job)['state'] == 'SUCCEEDED'
    assert len(client.stage_calls) == 3 and client.stage_calls.count('i0000-Sone') == 1
    result = client.owner.result(window.document['id'], retry_job)
    assert result['stages'][0]['reused_from']['job_id'] == job_id
    assert result['responses']['cost']['value'] == 2.
    assert window.edited_draft()['stages'][0]['source'] == document_reference(source)
    window.save_document(); wait(application, lambda: not window._busy)
    saved = deepcopy(window.document)
    other_owner = EvaluationDocuments(client.root, client.session, client.manager.submit, client.manager,
        resolve_revision=lambda identifier, revision: client.material._verify_revision(identifier, revision))
    assert other_owner.open(document_id=saved['id'])['draft'] == saved['draft']
    assert other_owner.result(saved['id'], job_id)['execution_status'] == 'FAILED'
    assert other_owner.result(saved['id'], retry_job)['responses']['cost']['value'] == 2.
    window.open_document(document_id=saved['id'])
    wait(application, lambda: not window._busy and window.document['saved_revision'] == saved['saved_revision'])
    wait(application, lambda: not window._busy and bool(window._inspection['stages']))
    window.refresh_progress(); wait(application, lambda: not window._busy and window.attempts.rowCount() == 2)
    assert len(client.stage_calls) == 3  # Reading/reopening never executes a stage.


def test_late_progress_and_stage_read_cannot_overwrite_another_owner_or_attempt(editor, application):
    window, client, _ = editor
    window.run_once(); wait(application, lambda: not window._busy and bool(window.document['runs']))
    job_id = window.document['runs'][-1]['job_id']; wait(application, lambda: client.manager.status(job_id)['state'] in TERMINAL)
    window.refresh_progress(); wait(application, lambda: not window._busy and window.attempts.rowCount() == 2)
    client.delay_progress = True
    window.refresh_progress(); wait(application, client.progress_entered.is_set)
    second = client.owner.open(title='Another independent evaluation', draft=deepcopy(window.document['draft']))
    window._show_document(second); window._selected_job = None
    window.attempts.setRowCount(0); window._progress = {}
    client.progress_release.set(); wait(application, lambda: not window._busy)
    assert window.document['id'] == second['id'] and window.attempts.rowCount() == 0 and window._progress == {}

    # A late scalar read from one attempt must not become another attempt's value.
    original = client.owner.read(next(row['id'] for row in client.owner.list() if row['id'] != second['id']))
    window._show_document(original, prefer_job=job_id)
    window.refresh_progress(); wait(application, lambda: not window._busy and window.attempts.rowCount() == 2)
    client.delay_stage = True
    window.attempts.selectRow(0); wait(application, client.stage_entered.is_set)
    window.attempts.item(1,3).setData(Qt.ItemDataRole.UserRole,'RUNNING')
    window._progress['stages'][1]['state']='RUNNING'
    window.attempts.selectRow(1)
    client.stage_release.set(); wait(application, lambda: not window._busy)
    assert window.channels.rowCount() == 0 and window._result is None


def test_explicit_save_is_not_dropped_behind_background_progress(editor, application):
    window, client, _ = editor
    window.run_once(); wait(application, lambda: not window._busy and bool(window.document['runs']))
    job_id = window.document['runs'][-1]['job_id']
    wait(application, lambda: client.manager.status(job_id)['state'] in TERMINAL)
    client.delay_progress = True
    window.refresh_progress(); wait(application, client.progress_entered.is_set)
    assert window.save_document() is True
    client.progress_release.set()
    wait(application, lambda: not window._busy and bool(window.document['saved_revision']))
    assert window.document['runs'][-1]['retention_complete']
    assert client.calls.count('document.save') == 1 and len(client.stage_calls) == 2


@pytest.mark.parametrize('flag', ['--document-id', '--document'])
def test_launcher_aliases_and_exact_shared_callbacks(application, monkeypatch, flag):
    from apps.research import evaluation_window, desktop, result_return
    from caelab import workbench_client
    from types import SimpleNamespace
    calls, windows, activations = [], [], []
    client = SimpleNamespace(url='http://127.0.0.1:9000',
        document_read=lambda identifier: {'id': identifier, 'kind': 'evaluation', 'session_id': 'Ssession'})
    monkeypatch.setattr(result_return, 'send_message',
        lambda message: (activations.append(message), {'status': 'ABSENT'})[1])
    monkeypatch.setattr(workbench_client, 'Client', lambda service: client)
    for name in ('launch_tool', 'open_stage_result', 'open_domain_plan', 'open_saved_reference'):
        monkeypatch.setattr(desktop, name,
            lambda *args, _name=name, **kwargs: calls.append((_name, args, kwargs)), raising=False)
    class Window:
        def __init__(self, actual_client, **options):
            assert actual_client is client
            self.options = options; windows.append(self)
        def show(self): pass
    monkeypatch.setattr(evaluation_window, 'EvaluationWindow', Window)
    monkeypatch.setattr(QApplication, 'exec', lambda self: 0)
    assert evaluation_window.main(['--service', 'http://127.0.0.1:9000', flag, 'Edefinition']) == 0
    assert len(activations) == 1 and activations[0]['target_id'] == 'Edefinition'
    assert activations[0]['session_id'] == 'Ssession' and activations[0]['operation'] == 'activate'
    options = windows[0].options
    assert options['document_id'] == 'Edefinition'
    options['runner_open']('Jrun')
    options['result_open']('Edefinition', 'Jrun', 'i0000-Sone')
    options['plan_open']('Edefinition', 'Ssession', 4, 'Ccommand')
    options['source_open']({'kind': 'pde', 'document_id': 'Qsource'})
    assert calls == [
        ('launch_tool', (client, 'runner', 'Jrun'), {}),
        ('open_stage_result', (client, 'Edefinition', 'Jrun', 'i0000-Sone'), {}),
        ('open_domain_plan', (client, 'Edefinition'), {'session_id': 'Ssession', 'expected_generation': 4, 'command_id': 'Ccommand'}),
        ('open_saved_reference', (client, {'kind': 'pde', 'document_id': 'Qsource'}), {})]


def test_forward_transfer_and_explicit_feedback_use_real_stage_ports(editor, application, monkeypatch):
    from caelab.adapters.thermoelastic_fenicsx import ThermalFenicsxAdapter, ThermoelasticFenicsxAdapter
    window, client, _ = editor
    catalogs = [ThermalFenicsxAdapter(), ThermoelasticFenicsxAdapter()]
    window._inspection['stages'] = [{'id': stage['id'], 'ports': adapter.describe_ports(adapter.default_settings()), 'inputs': []}
        for stage, adapter in zip(window.edited_draft()['stages'], catalogs)]
    answers = iter(['1. First controlled stage', 'temperature', '2. Second controlled stage', 'temperature', '현재 반복 (0)'])
    monkeypatch.setattr(QInputDialog, 'getItem', lambda *args, **kwargs: (next(answers), True))
    window.add_transfer()
    first = window.edited_draft()['transfers'][0]
    assert (first['from_stage'], first['to_stage'], first['mapping'], first['lag']) == ('Sone', 'Stwo', 'exact_same_mesh', 0)
    answers = iter(['1. First controlled stage', 'temperature', '1. First controlled stage', 'linearization_temperature', '이전 반복 (1)'])
    window.add_transfer()
    assert window.edited_draft()['transfers'][1]['lag'] == 1 and not window.run_button.isEnabled()
    window.iteration_enabled.setChecked(True)
    assert window.edited_draft()['iteration']['enabled'] is True
    assert not client.stage_calls  # Real adapter declarations, no native evaluation.


def test_partial_editor_focus_and_second_edit_preserve_unapplied_value(editor, application):
    window, client, _ = editor
    draft = window.edited_draft()
    draft['iteration']['checks'] = [{'stage':'Sone','response':'cost','unit':'MPa',
                                    'absolute':.123456789123,'relative':.01,'scale':1.}]
    window._replace_draft(draft)
    window.show(); window.activateWindow()
    window.tabs.setCurrentIndex(4)
    application.processEvents()
    table = window.tables['checks']
    item = table.item(0, 3)
    table.setCurrentItem(item)
    table.editItem(item)
    application.processEvents()
    active = QApplication.focusWidget()
    assert isinstance(active, QLineEdit) and active.text() == '0.123456789123'
    active.selectAll(); QTest.keyClicks(active, '1e')
    assert active.text() == '1e' and window.edited_draft()['iteration']['checks'][0]['absolute'] == '1e'
    window.refresh_document(); wait(application, lambda:not window._busy)
    window._update_actions()
    assert QApplication.focusWidget() is active and active.text() == '1e'
    QTest.keyClicks(active, '2')
    window._commit_editor(); application.processEvents()
    assert window.edited_draft()['iteration']['checks'][0]['absolute'] == 100.
    table.editItem(item); application.processEvents()
    again = QApplication.focusWidget()
    assert isinstance(again, QLineEdit) and again.text() == '1e2'
    again.selectAll(); QTest.keyClicks(again, '.002')
    window._commit_editor(); application.processEvents()
    assert window.edited_draft()['iteration']['checks'][0]['absolute'] == .002
    window.iteration_maximum.setFocus(); window.iteration_maximum.selectAll()
    QTest.keyClicks(window.iteration_maximum, '1e')
    window._update_actions()
    assert QApplication.focusWidget() is window.iteration_maximum and window.iteration_maximum.text() == '1e'
    assert not client.stage_calls


def test_display_names_preserve_raw_definition_and_frozen_attempt_meaning(editor, application):
    window, client, _ = editor
    original = window.edited_draft()
    assert window.tables['stages'].isColumnHidden(0)
    assert window.tables['stages'].item(0, 2).text() == 'Actual saved Material source'
    assert window.edited_draft() == original
    window.run_once(); wait(application, lambda:not window._busy and bool(window.document['runs']))
    job = window.document['runs'][-1]['job_id']
    wait(application, lambda:client.manager.status(job)['state'] in TERMINAL)
    window.refresh_progress(); wait(application, lambda:not window._busy and window.attempts.rowCount()==2)
    window.tables['stages'].item(0, 1).setText('Unapplied new name')
    assert window.stage_list.item(0).text() == 'Unapplied new name'
    assert window.attempts.item(0, 1).text() == original['stages'][0]['name']
    assert window.attempts.item(0, 1).data(Qt.ItemDataRole.UserRole) == 'Sone'
    assert '실패' in window.runs.currentText()
    window._show_document(client.owner.open(title='Different owner', draft=original))
    assert window.attempts.rowCount()==0 and window.channels.rowCount()==0 and window._result is None


def test_attempt_source_opens_submitted_revision_instead_of_new_editor_source(editor, application):
    window,client,source=editor
    original=document_reference(source)
    # A retained attempt is a selection fixture; no evaluator is needed here.
    window.document['runs']=[{'job_id':'Jfixed','draft':deepcopy(window.document['draft'])}]
    window._selected_job='Jfixed';window._selected_attempt='Afixed'
    window._progress={'stages':[{'stage_id':'Sone','attempt_id':'Afixed'}]}
    replacement=deepcopy(original);replacement['saved_revision']='Rnewer'
    replacement['input_revision']='Inewer';replacement['input_sha256']='b'*64
    edited=window.edited_draft();edited['stages'][0]['source']=replacement
    window._replace_draft(edited)
    opened=[];window.source_open=lambda reference:opened.append(reference)
    assert window._attempt_source()==original
    assert window.open_attempt_source()
    wait(application,lambda:not window._busy)
    assert opened==[original] and not client.stage_calls
    window.stage_list.setCurrentRow(0);window.open_source()
    assert opened[-1]==replacement
    window._selected_attempt='Aother'
    assert window.open_attempt_source() is False and opened==[original,replacement]
    assert '현재 입력으로 대체하지 않습니다' in window.message.text()


@pytest.mark.parametrize('difference',['document','revision','session','dirty'])
def test_source_picker_rejects_different_read_instead_of_silently_replacing_choice(editor, application, monkeypatch,difference):
    window,client,source=editor
    original=window.edited_draft()
    replacement=deepcopy(source)
    if difference=='document':replacement['id']='Mother'
    elif difference=='revision':replacement['saved_revision']='Rother'
    elif difference=='session':replacement['session_id']='Sother'
    else:replacement['dirty']=True
    monkeypatch.setattr(QInputDialog,'getItem',lambda *a,**k:(a[3][0],True))
    monkeypatch.setattr(client,'document_read',lambda _:deepcopy(replacement))
    window.add_stage();wait(application,lambda:not window._busy)
    assert window.edited_draft()==original and not window.local_dirty
    assert '다시 읽고 선택' in window.message.text() and not client.stage_calls


def test_late_source_picker_cannot_change_another_document_or_session(editor,application,monkeypatch):
    window,client,source=editor
    entered,release=threading.Event(),threading.Event()
    def delayed_read(_):
        entered.set();assert release.wait(4);return deepcopy(source)
    monkeypatch.setattr(client,'document_read',delayed_read)
    monkeypatch.setattr(QInputDialog,'getItem',lambda *a,**k:(a[3][0],True))
    original=deepcopy(window.document['draft'])
    window.add_stage();wait(application,entered.is_set)
    other=client.owner.open(title='Another evaluation',draft=original)
    other['session_id']='Snewsession'
    window._show_document(other)
    release.set();wait(application,lambda:not window._busy)
    assert window.document['id']==other['id'] and window.document['session_id']=='Snewsession'
    assert window.edited_draft()==original and not window.local_dirty and not client.stage_calls


def test_late_save_ack_cannot_replace_another_session(editor,application,monkeypatch):
    window,client,_=editor
    entered,release=threading.Event(),threading.Event()
    actual=client.document_command
    def delayed_command(*args,**kwargs):
        receipt=actual(*args,**kwargs);entered.set();assert release.wait(4);return receipt
    monkeypatch.setattr(client,'document_command',delayed_command)
    window.save_document();wait(application,entered.is_set)
    other=client.owner.open(title='Another owner',draft=deepcopy(window.document['draft']))
    other['session_id']='Sother'
    window._show_document(other)
    release.set();wait(application,lambda:not window._busy)
    assert window.document['id']==other['id'] and window.document['session_id']=='Sother'
    assert not client.stage_calls


def test_invalid_saved_source_blocks_button_and_direct_run_dispatch(editor,application):
    window,client,_=editor
    changed=window.edited_draft();changed['stages'][0]['source']['input_sha256']='0'*64
    window._replace_draft(changed)
    assert not window.run_button.isEnabled() and window.run_once() is False
    window.apply_inputs();wait(application,lambda:not window._busy)
    window.inspect_inputs();wait(application,lambda:not window._busy)
    assert window._inspection['diagnostics'] and not window.run_button.isEnabled()
    window.run_once();wait(application,lambda:not window._busy)
    assert not client.stage_calls and not client.manager.list()


def test_stage_physical_labels_reuse_existing_names_and_keep_unknown_raw_inputs(editor,application):
    window,_,_=editor
    window._inspection['stages'][0]['inputs']=[
        {'id':'young_modulus','label':'young modulus','unit':'Pa'},
        {'id':'poisson_ratio','label':'poisson ratio','unit':'1'},
        {'id':'custom_input','label':'custom input','unit':'K'}]
    window.stage_list.setCurrentRow(0);window._stage_context()
    assert '탄성계수 [Pa]' in window.stage_summary.text()
    assert '포아송비 [1]' in window.stage_summary.text()
    assert 'custom input [K]' in window.stage_summary.text()
    assert 'young_modulus' in window.stage_summary.toolTip()
    columns=[('name',''),('kind',''),('unit',''),('component',''),('location',''),('value',''),('state','')]
    window._put_rows(window.channels,columns,[{'name':'displacement','kind':'field','unit':'m',
        'component':'vector','location':'node','value':{'retained_array':{}},'state':'SUCCEEDED'},
        {'name':'user_response','component':['custom_x','custom_y'],'location':'user_location'}],key='channels')
    assert window.channels.item(0,0).text()=='변위장' and window.channels.item(0,0).data(Qt.ItemDataRole.UserRole)=='displacement'
    assert window.channels.item(0,2).text()=='m' and window.channels.item(0,4).text()=='절점'
    assert window.channels.item(1,0).text()=='user_response'
    assert window.channels.item(1,3).data(Qt.ItemDataRole.UserRole)==['custom_x','custom_y']


@pytest.mark.parametrize('target_state',['RUNNING','SUCCEEDED'])
def test_actual_attempt_row_selection_clears_previous_response_during_run_or_read_failure(
        editor,application,monkeypatch,target_state):
    window,client,_=editor
    document=deepcopy(window.document)
    document['title']='단계 선택 검사 — 계산 없음'
    document['runs']=[{'job_id':'Jselection','draft':deepcopy(document['draft']),
                      'retained_state':'SUCCEEDED','is_current_input':True}]
    window._show_document(document,prefer_job='Jselection')
    rows=[{'iteration':0,'stage_id':'Sone','attempt_id':'Aprevious','state':'SUCCEEDED'},
          {'iteration':0,'stage_id':'Stwo','attempt_id':'Aselected','state':target_state}]
    window._progress={'stages':deepcopy(rows)}
    window._populating=True
    window._put_rows(window.attempts,[('iteration',''),('stage_id',''),('attempt_id',''),
        ('state',''),('backend',''),('reused_from','')],rows)
    window._populating=False
    reads=[]
    def read(document,job,attempt,selection=None):
        reads.append(attempt)
        if attempt=='Aselected':raise OSError('Selected B retained result is unavailable (controlled read failure)')
        return {'execution_status':'SUCCEEDED','responses':{'old_pressure':{
            'kind':'scalar','value':123.,'unit':'MPa','component':'scalar','location':'material_point'}},
            'diagnostics':{'scope':'DISPLAY FIXTURE; no numerical evaluator'}}
    monkeypatch.setattr(client,'evaluation_stage_result',read)
    window.source_open=lambda *_:None;window.result_open=lambda *_:None
    window.show();window.activateWindow();application.processEvents()
    window.result_tabs.setCurrentWidget(window.channels)
    window.attempts.selectRow(0)
    wait(application,lambda:not window._busy and bool(window._result))
    assert window.channels.rowCount()==1 and window.channels.item(0,2).text()=='MPa'
    assert window.result_source_action.isEnabled() and window.result_button.isEnabled()
    previous=window._result
    window.attempts.selectRow(0);application.processEvents()
    assert window._result==previous and window.channels.rowCount()==1
    window.attempts.selectRow(1)
    assert window._selected_attempt=='Aselected'
    assert window._result is None and window.channels.rowCount()==0
    assert not window.result_source_action.isEnabled() and not window.result_button.isEnabled()
    if target_state=='RUNNING':
        application.processEvents()
        assert reads==['Aprevious'] and '실행 중' in window.result_context.text()
    else:
        wait(application,lambda:not window._busy and 'unavailable' in window.message.text())
        assert reads==['Aprevious','Aselected']
        assert window._result is None and window.channels.rowCount()==0
        assert not window.result_source_action.isEnabled() and not window.result_button.isEnabled()
        assert '보존 결과가 없습니다' in window.result_context.text()
    assert not client.stage_calls and not client.manager.list()
    capture=os.environ.get('CAELAB_EVALUATION_SELECTION_CAPTURE_DIR')
    if capture:
        from pathlib import Path
        folder=Path(capture);folder.mkdir(parents=True,exist_ok=True)
        for width,height in ((1440,900),(1100,780)):
            window.resize(width,height);application.processEvents()
            assert window.grab().save(str(folder/(target_state.lower()+'-'+str(width)+'.png')))
