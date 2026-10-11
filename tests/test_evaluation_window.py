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
from PySide6.QtWidgets import QApplication, QInputDialog

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
    assert [window.attempts.item(row, 3).text() for row in range(2)] == ['SUCCEEDED', 'FAILED']
    assert len(client.stage_calls) == 2
    window.attempts.selectRow(0)
    wait(application, lambda: not window._busy and window.channels.rowCount() == 1)
    assert window.channels.item(0, 0).text() == 'cost' and window.channels.item(0, 5).text() == '2.0'
    assert window.channels.item(0, 6).text() == 'SUCCEEDED'
    window.prepare_retry()
    assert 'Save the completed run' in window.message.text()
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
    window._selected_attempt = window._progress['stages'][0]['attempt_id']
    window.read_stage_result(); wait(application, client.stage_entered.is_set)
    window._selected_attempt = window._progress['stages'][1]['attempt_id']
    window.channels.setRowCount(0); window._result = None
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
    from apps.research import evaluation_window, desktop
    from caelab import workbench_client
    calls, windows = [], []
    client = object()
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
    answers = iter(['First controlled stage · Sone', 'temperature', 'Second controlled stage · Stwo', 'temperature', '0 · current iteration'])
    monkeypatch.setattr(QInputDialog, 'getItem', lambda *args, **kwargs: (next(answers), True))
    window.add_transfer()
    first = window.edited_draft()['transfers'][0]
    assert (first['from_stage'], first['to_stage'], first['mapping'], first['lag']) == ('Sone', 'Stwo', 'exact_same_mesh', 0)
    answers = iter(['First controlled stage · Sone', 'temperature', 'First controlled stage · Sone', 'linearization_temperature', '1 · previous iteration / feedback'])
    window.add_transfer()
    assert window.edited_draft()['transfers'][1]['lag'] == 1 and not window.run_button.isEnabled()
    window.iteration_enabled.setChecked(True)
    assert window.edited_draft()['iteration']['enabled'] is True
    assert not client.stage_calls  # Real adapter declarations, no native evaluation.
