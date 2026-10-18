"""Actual Qt candidate navigation over a controlled retained service boundary.

No solver, native application, inference or candidate execution is performed.
"""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from copy import deepcopy
import threading
import time

import pytest
pytest.importorskip('PySide6')
pytest.importorskip('matplotlib')
from PySide6.QtWidgets import QApplication
from apps.research.request_plan_window import RequestPlanWindow
from apps.research.candidate_results_window import CandidateResultsWindow
from caelab.numerical_document import request_draft


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


def wait(app, predicate):
    until = time.monotonic() + 5
    while time.monotonic() < until:
        app.processEvents()
        if predicate(): return
        time.sleep(.005)
    raise AssertionError('Candidate result Qt read did not settle')


class RetainedClient:
    def __init__(self):
        self.calls, self.posts = [], []
        self.entered, self.release = threading.Event(), threading.Event()
        self.delay = None
        self.foreign_identity = False
        self.changed_field = False
        draft = request_draft({'purpose': 'Controlled retained coupled study', 'operation': 'doe',
            'inputs': {'backend': 'evaluation.definition', 'settings': {'definition_ref': {}},
                       'variables': [{'id': 'conductivity', 'unit': 'W/(m K)', 'value': 200., 'lower': 100., 'upper': 300., 'free': True}]},
            'budget': {'evaluations': 2}})
        self.document = {'id': 'Nplan', 'kind': 'numerical', 'title': 'Retained candidate navigation',
            'session_id': 'Sowner', 'generation': 3, 'input_revision': 'Iplan', 'draft': draft,
            'diagnostics': [], 'dirty': False,
            'runs': [{'job_id': 'Jstudy', 'input_generation': 3, 'input_revision': 'Iplan',
                      'retention_complete': True, 'retained_state': 'FAILED', 'draft': deepcopy(draft)}]}
        self.parent_result = {'candidates': [
            {'candidate_id': 'Cfailed', 'execution_status': 'FAILED', 'values': {'conductivity': 200.}, 'failure_reason': 'Controlled later-stage failure'},
            {'candidate_id': 'Cother', 'execution_status': 'SUCCEEDED', 'values': {'conductivity': 220.}},
            {'candidate_id': 'Cpredicted', 'execution_status': 'PREDICTED', 'values': {'conductivity': 230.}}]}

    def numerical_evaluation_result(self, document, job, candidate, *, evaluation_index=None, attempt_id=None, selection=None):
        self.calls.append((document, job, candidate, evaluation_index, attempt_id, deepcopy(selection)))
        if self.delay == 'catalog' and evaluation_index is None or self.delay == 'stage' and attempt_id == 'i0000-Sthermal':
            self.entered.set(); assert self.release.wait(4)
        identity = {'document_id': 'Nforeign' if self.foreign_identity else document, 'job_id': job, 'candidate_id': candidate}
        if evaluation_index is None:
            return {**identity, 'evaluations': [{'evaluation_index': i, 'execution_status': 'FAILED',
                'stage_execution_count': 2, 'definition_sha256': 'a' * 64} for i in range(2)]}
        identity['evaluation_index'] = evaluation_index
        stages = [{'iteration': 0, 'stage_id': 'Sthermal', 'attempt_id': 'i0000-Sthermal', 'state': 'SUCCEEDED', 'backend': 'thermal.controlled'},
                  {'iteration': 0, 'stage_id': 'Sstructure', 'attempt_id': 'i0000-Sstructure', 'state': 'FAILED', 'backend': 'structural.controlled'}]
        if attempt_id:
            stage = next(row for row in stages if row['attempt_id'] == attempt_id)
            response = {'temperature': {'kind': 'field', 'unit': 'K', 'component': 'scalar', 'location': 'nodal',
                'association': 'POINTS', 'frame': 'global', 'time': 0., 'time_units': 's',
                'value': {'data_ref': {'path': 'arrays/temperature.npy', 'sha256': 'b' * 64, 'shape': [20]}}}} if stage['state'] == 'SUCCEEDED' else {}
            return {**identity, 'stage_attempt': stage, 'execution_status': stage['state'], 'responses': response,
                'diagnostics': {'scope': 'Controlled retained stage output; no solver'},
                'post_input': {'id': 'Dfield', 'sha256': 'c' * 64, 'format': 'vtu'} if response else None}
        return {**identity, 'execution_status': 'FAILED', 'stages': stages,
            'responses': {'cost': {'kind': 'scalar', 'value': 2. + evaluation_index, 'unit': 'MPa', 'component': 'scalar', 'location': 'controlled'}},
            'iterations': [{'iteration': 1, 'checks': [{'stage': 'Sthermal', 'response': 'temperature', 'unit': 'K', 'observed': .1, 'limit': .05, 'passed': False}]}],
            'diagnostics': {'reason': 'Controlled later-stage failure'}}

    def native_input(self, identifier):
        assert identifier == 'Dfield'
        return {'id': identifier, 'sha256': 'd' * 64 if self.changed_field else 'c' * 64}


@pytest.fixture
def plan(app):
    client = RetainedClient()
    window = RequestPlanWindow(client, auto_open=False, poll_interval=0)
    window._show_document(client.document)
    window._result_cache['Jstudy'] = deepcopy(client.parent_result)
    window._draw_result(); window.show(); app.processEvents()
    yield window, client
    client.release.set()
    for child in window._candidate_result_windows:
        wait(app, lambda: not child._busy)
        child.close()
    window._allow_close = True; window.close()


def open_failed(plan, app):
    window, client = plan
    window.candidates.selectRow(0)
    assert window.candidate_results_button.isEnabled()
    window.candidate_results_button.click()
    child = window._candidate_result_windows[-1]
    wait(app, lambda: not child._busy and child.stages.rowCount() == 2)
    return child


def test_failed_candidate_opens_exact_stages_units_and_registered_post(plan, app, monkeypatch):
    window, client = plan
    child = open_failed(plan, app)
    assert child.parameters.item(0, 1).text() == '200.0'
    assert child.parameters.item(0, 2).text() == 'W/(m K)'
    assert child.responses.item(0, 2).text() == 'MPa' and child.responses.item(0, 7).text() == '2.0'
    assert child.residuals.item(0, 3).text() == 'K' and child.residuals.item(0, 4).text() == '0.1'
    assert child.stages.item(1, 3).text() == '실패'
    assert child._composite['stages'][1]['state']=='FAILED'
    child.stages.selectRow(0); wait(app, lambda: not child._busy and child._stage_result is not None)
    assert child.responses.item(0, 0).text() == 'temperature'
    assert child.responses.item(0, 2).text() == 'K' and 'data_ref' in child.responses.item(0, 7).text()
    assert child.post_button.isEnabled()
    from apps.research import desktop
    monkeypatch.setattr(desktop, 'launch_post', lambda *args, **kwargs: client.posts.append((args, kwargs)))
    child.post_button.click(); wait(app, lambda: not child._busy and bool(client.posts))
    assert client.posts == [((client, 'Dfield'), {'job_id': 'Jstudy', 'research_source': {
        'document_id': 'Nplan', 'candidate_id': 'Cfailed', 'evaluation_index': 0, 'attempt_id': 'i0000-Sthermal'}})]
    assert all(call[0:3] == ('Nplan', 'Jstudy', 'Cfailed') for call in client.calls)
    assert all(call[-1] == {'metadata_only': True} for call in client.calls if call[3] is not None)
    child.evaluations.setCurrentIndex(1); wait(app, lambda: not child._busy and child._composite['evaluation_index'] == 1)
    assert child.responses.item(0, 7).text() == '3.0' and child.fields.count() == 0


def test_predicted_rows_are_not_candidate_stage_results(plan, app):
    window, client = plan
    window.candidates.selectRow(2); app.processEvents()
    assert not window.candidate_results_button.isEnabled()
    window.open_candidate_results()
    assert not window._candidate_result_windows and not client.calls


def test_late_catalog_is_rejected_after_parent_candidate_or_owner_changes(plan, app):
    window, client = plan
    client.delay = 'catalog'
    window.candidates.selectRow(0); window.open_candidate_results()
    child = window._candidate_result_windows[-1]; wait(app, client.entered.is_set)
    window.candidates.selectRow(1)
    client.release.set(); wait(app, lambda: not child._busy)
    assert child.stages.rowCount() == child.responses.rowCount() == 0
    assert 'late response' in child.message.text()
    assert not child.refresh_button.isEnabled()
    assert len(client.calls) == 1


def test_latest_stage_selection_wins_while_previous_read_is_pending(plan, app):
    _, client = plan
    child = open_failed(plan, app)
    client.delay = 'stage'
    child.stages.selectRow(0); wait(app, client.entered.is_set)
    child.stages.selectRow(1)
    client.release.set()
    wait(app, lambda: not child._busy and child._stage_result is not None)
    assert child._stage_result['stage_attempt']['stage_id'] == 'Sstructure'
    assert child.responses.rowCount() == 0 and child.fields.count() == 0
    assert '실패' in child.message.text()
    assert child._stage_result['execution_status']=='FAILED'


def test_foreign_response_and_changed_native_field_do_not_launch(plan, app):
    _, client = plan
    child = open_failed(plan, app)
    client.foreign_identity = True
    child.evaluations.setCurrentIndex(1); wait(app, lambda: not child._busy)
    assert child.stages.rowCount() == child.responses.rowCount() == 0
    assert 'identity differs' in child.message.text()
    client.foreign_identity = False
    child.evaluations.setCurrentIndex(0); wait(app, lambda: not child._busy and child.stages.rowCount() == 2)
    child.stages.selectRow(0); wait(app, lambda: not child._busy and child._stage_result is not None)
    client.changed_field = True
    child.post_open = lambda *args: client.posts.append(args)
    child.open_post(); wait(app, lambda: not child._busy)
    assert not client.posts and 'Registered field differs' in child.message.text()


def test_http_owner_retention_reopens_actual_candidate_stage_arrays(tmp_path, app, monkeypatch):
    """Real HTTP/owner/disk reads; only parent execution output is controlled."""
    from apps.lab.server import LabHTTPServer
    from apps.lab.service import LabService
    from caelab.workbench_client import Client
    from caelab.material_document import default_draft
    from caelab.evaluation import save_evaluation, file_hash
    from caelab.jobs import TERMINAL
    server = LabHTTPServer(LabService(tmp_path / 'store'), 0)
    thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .02}, daemon=True)
    thread.start()
    client = Client('http://127.0.0.1:' + str(server.server_port))
    calls = []
    def controlled_result(operation, arguments, job_id):
        calls.append((operation, job_id))
        assert operation == 'doe'
        folder = server.workbench.root / 'results' / job_id
        coupled = folder / 'evaluations' / 'Ccontrolled' / '0000'
        records = []
        for name, status in [('Heat', 'SUCCEEDED'), ('Structure', 'FAILED')]:
            relative = 'stages/i0000-' + name
            response = {'temperature': {'kind': 'field', 'value': [300., 301.], 'unit': 'K',
                'component': 'scalar', 'location': 'controlled_test_capture', 'association': 'POINTS', 'frame': 'declared_fixture_frame'}} if name == 'Heat' else {}
            save_evaluation({'execution_status': status, 'responses': response,
                'diagnostics': {'scope': 'Injected controlled result, no physical solver'}}, coupled / relative)
            records.append({'iteration': 0, 'stage_id': name, 'attempt_id': 'i0000-' + name,
                'state': status, 'result_directory': relative, 'backend': 'controlled.fixture'})
        save_evaluation({'execution_status': 'FAILED', 'stages': records, 'responses': {},
            'iterations': [], 'diagnostics': {'reason': 'Controlled retained failure'}}, coupled, existing=True)
        parent = {'kind': 'doe', 'execution_status': 'FAILED', 'variables': [{'id': 'E', 'unit': 'MPa'}],
            'candidates': [{'candidate_id': 'Ccontrolled', 'execution_status': 'FAILED', 'values': {'E': 1000.},
                'evaluation_refs': [{'relative': coupled.relative_to(folder).as_posix(),
                    'result_sha256': file_hash(coupled / 'result.json'), 'execution_status': 'FAILED',
                    'stage_execution_count': 2, 'definition_sha256': 'a' * 64}]}]}
        save_evaluation(parent, folder, existing=True)
        return parent
    monkeypatch.setattr(server.workbench.manager, '_execute', controlled_result)
    window = None
    try:
        draft = request_draft({'purpose': 'Read controlled retained candidate stages', 'operation': 'doe',
            'inputs': {**default_draft(), 'variables': [{'id': 'E', 'unit': 'MPa', 'lower': 900., 'upper': 1100.}], 'count': 1},
            'budget': {'evaluations': 1}})
        document = client.document_open(kind='numerical', draft=draft)
        receipt = client.document_command(document['id'], 'numerical.run', {}, session_id=document['session_id'], expected_generation=document['generation'])
        job = receipt['job']['id']
        wait(app, lambda: client.status(job)['state'] in TERMINAL)
        document = client.document_read(document['id'])
        document = client.document_command(document['id'], 'document.save', {}, session_id=document['session_id'], expected_generation=document['generation'])['document']
        window = RequestPlanWindow(client, auto_open=False, poll_interval=0)
        window._show_document(client.document_open(kind='numerical', document_id=document['id']))
        window._result_cache[job] = client.document_result(document['id'], job)
        window._draw_result(); window.candidates.selectRow(0); window.open_candidate_results()
        child = window._candidate_result_windows[-1]
        wait(app, lambda: not child._busy and child.stages.rowCount() == 2)
        child.stages.selectRow(0)
        wait(app, lambda: not child._busy and child._stage_result is not None)
        assert child.responses.item(0, 2).text() == 'K'
        assert 'data_ref' in child.responses.item(0, 7).text()
        assert child.parameters.item(0, 2).text() == 'MPa'
        assert child._stage_result['stage_attempt']['stage_id'] == 'Heat'
        assert child._stage_result['execution_status'] == 'SUCCEEDED'
        assert len(calls) == len(server.workbench.manager.list()) == 1
        assert window.document['saved_revision'] == document['saved_revision']
    finally:
        if window:
            for child in window._candidate_result_windows:
                wait(app, lambda: not child._busy); child.close()
            window._allow_close = True; window.close()
        server.shutdown(); server.server_close(); thread.join(3)


class DomainClient(RetainedClient):
    """Controlled preview/adoption receipts; no domain solver or stage creation."""
    def __init__(self, kind='simulation'):
        super().__init__()
        from caelab.storage import canonical_hash
        self.kind = kind
        self.target = {'id': 'Voriginal' if kind == 'simulation' else 'Eoriginal', 'kind': kind,
            'session_id': 'Sowner', 'generation': 4, 'input_revision': 'Isource',
            'draft': {'backend': 'thermal.controlled', 'settings': {'conductivity': 200.}} if kind == 'simulation'
                     else {'stages': [{'id': 'Heat', 'source': {'document_id': 'Voriginal'}}]}}
        self.source = {'kind': kind, 'document_id': self.target['id'], 'saved_revision': 'Rsaved',
            'input_revision': 'Isource', 'input_sha256': canonical_hash(self.target['draft'])}
        self.document['draft']['source'] = deepcopy(self.source)
        self.document['runs'][0]['draft'] = deepcopy(self.document['draft'])
        self.adoptions, self.receipts = [], {}
        self.writes = 0
        self.lose_response = False

    def document_read(self, identifier):
        self.calls.append(('read', identifier))
        if identifier == self.document['id'] and self.delay == 'background':
            self.entered.set(); assert self.release.wait(4)
        return deepcopy(self.document if identifier == self.document['id'] else self.target)

    def domain_candidate_preview(self, plan, job, candidate):
        from caelab.storage import canonical_hash
        self.calls.append(('preview', plan, job, candidate))
        if self.delay == 'preview':
            self.entered.set(); assert self.release.wait(4)
        return {'target_document_id': self.target['id'], 'target_kind': self.kind, 'candidate_id': candidate,
            'source': deepcopy(self.source), 'result_sha256': canonical_hash(self.parent_result),
            'changes': [{'path': ['settings', 'conductivity'], 'before': 200., 'after': 220.,
                         'unit': 'W/(m K)', 'stage': 'Heat' if self.kind == 'evaluation' else None}],
            'draft': {'controlled_candidate_input': 220.}, 'executed': False}

    def domain_candidate_adopt(self, **request):
        self.adoptions.append(deepcopy(request))
        command = request['command_id']
        if command not in self.receipts:
            assert request['target_document_id'] == self.target['id']
            assert request['expected_generation'] == self.target['generation']
            self.target['generation'] += 1
            self.target['draft'] = {'controlled_candidate_input': 220.}
            self.writes += 1
            self.receipts[command] = {'command_id': command, 'document': deepcopy(self.target), 'executed': False}
            if self.lose_response:
                self.lose_response = False
                raise TimeoutError('Controlled discarded successful adoption response')
        return deepcopy(self.receipts[command])


@pytest.fixture
def domain_plan(app):
    windows, clients = [], []
    def create(kind):
        client = DomainClient(kind)
        window = RequestPlanWindow(client, auto_open=False, poll_interval=0)
        window._show_document(client.document)
        window._result_cache['Jstudy'] = deepcopy(client.parent_result)
        window._draw_result(); window.candidates.selectRow(1); window.show(); app.processEvents()
        windows.append(window); clients.append(client)
        return window, client
    yield create
    for window, client in zip(windows, clients):
        client.release.set(); wait(app, lambda: not window._busy)
        window._allow_close = True; window.close()


@pytest.mark.parametrize('kind', ['simulation', 'evaluation'])
def test_domain_review_actual_dialog_exact_receipt_and_owner_return(domain_plan, app, monkeypatch, kind):
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QDialog, QTableWidget, QPushButton
    window, client = domain_plan(kind)
    launches = []
    monkeypatch.setattr('apps.research.desktop.launch_tool', lambda _, tool, **options: launches.append((tool, options)))
    original_review = window._review_pde_changes
    def review(preview):
        def inspect_dialog():
            dialog = next(widget for widget in QApplication.topLevelWidgets() if isinstance(widget, QDialog) and widget.isVisible())
            table = dialog.findChild(QTableWidget)
            assert table.item(0, 3).text() == 'W/(m K)'
            if kind == 'evaluation':
                assert table.item(0, 4).text() == 'Heat'
                assert any('확인한 입력 채택' in button.text() for button in dialog.findChildren(QPushButton))
            # Its nested event loop must not start a timer read during confirmation.
            window.refresh_document()
            assert len([call for call in client.calls if call[0] == 'read']) == 1
            dialog.accept()
        QTimer.singleShot(0, inspect_dialog)
        return original_review(preview)
    monkeypatch.setattr(window, '_review_pde_changes', review)
    assert window.pde_adopt_button.isEnabled()
    window.pde_adopt_button.click()
    wait(app, lambda: not window._busy and bool(launches))
    assert client.writes == len(client.adoptions) == 1
    assert client.adoptions[0]['candidate_id'] == 'Cother'
    assert client.adoptions[0]['expected_generation'] == 4
    assert client.adoptions[0]['target_document_id'] == client.target['id']
    assert launches == [(kind, {'document_id': client.target['id']})]
    assert window._adoption_receipt is None
    assert window.edited_draft()['source'] == client.source
    assert window.source_button.isEnabled()
    window.source_button.click(); wait(app, lambda: not window._busy and len(launches) == 2)
    assert launches[-1] == (kind, {'document_id': client.target['id']})


def test_domain_lost_response_retry_keeps_exact_command_and_target(domain_plan, app, monkeypatch):
    window, client = domain_plan('evaluation')
    launches = []
    monkeypatch.setattr('apps.research.desktop.launch_tool', lambda *args, **kwargs: launches.append((args, kwargs)))
    monkeypatch.setattr(window, '_review_pde_changes', lambda _: True)
    client.lose_response = True
    window.review_pde_candidate()
    wait(app, lambda: not window._busy and window._adoption_receipt is not None)
    original = deepcopy(client.adoptions[0])
    assert client.writes == 1 and not launches
    window.candidates.selectRow(0)  # Receipt retry must not adopt this failed row.
    window.retry_adoption_receipt()
    wait(app, lambda: not window._busy and window._adoption_receipt is None)
    assert client.adoptions == [original, original]
    assert client.writes == 1 and not launches


@pytest.mark.parametrize('changed', ['parent_selection', 'target_input', 'during_review', 'cancel'])
def test_domain_stale_or_cancelled_review_never_adopts(domain_plan, app, monkeypatch, changed):
    window, client = domain_plan('simulation')
    def review(_):
        if changed == 'during_review': client.target['generation'] += 1
        return changed != 'cancel'
    monkeypatch.setattr(window, '_review_pde_changes', review)
    if changed == 'target_input': client.target['draft']['settings']['conductivity'] = 201.
    if changed == 'parent_selection': client.delay = 'preview'
    window.review_pde_candidate()
    if changed == 'parent_selection':
        wait(app, client.entered.is_set); window.candidates.selectRow(0); client.release.set()
    wait(app, lambda: not window._busy)
    assert not client.adoptions and client.writes == 0 and window._adoption_receipt is None


def test_domain_review_waits_for_background_read_then_uses_same_candidate(domain_plan, app, monkeypatch):
    window, client = domain_plan('simulation')
    monkeypatch.setattr(window, '_review_pde_changes', lambda _: False)
    client.delay = 'background'
    window.refresh_document(); wait(app, client.entered.is_set)
    assert window.review_pde_candidate() is True
    assert window._pending_adoption is not None
    client.release.set(); wait(app, lambda: not window._busy and window._pending_adoption is None)
    previews = [call for call in client.calls if call[0] == 'preview']
    assert previews == [('preview', 'Nplan', 'Jstudy', 'Cother')]
    assert not client.adoptions
