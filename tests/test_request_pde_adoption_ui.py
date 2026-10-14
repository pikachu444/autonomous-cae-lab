"""Controlled real Qt transport checks; no solver, inference or native process runs."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from copy import deepcopy
import threading
import time

import pytest
pytest.importorskip('PySide6')
pytest.importorskip('matplotlib')
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QDialog, QTableWidget

from apps.research.request_plan_window import RequestPlanWindow
from caelab.numerical_document import request_draft
from caelab.storage import canonical_hash


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


def wait(app, predicate):
    until = time.monotonic() + 5
    while time.monotonic() < until:
        app.processEvents()
        if predicate():
            return
        time.sleep(.005)
    raise AssertionError('Controlled Request Plan response did not settle')


def document(identifier, draft, kind='numerical'):
    return {'id': identifier, 'kind': kind, 'session_id': 'Sowner', 'generation': 4,
            'input_revision': 'Ioriginal', 'title': 'Controlled UI fixture', 'draft': deepcopy(draft),
            'diagnostics': [], 'dirty': False, 'runs': [], 'can_undo': False, 'can_redo': False}


class Client:
    def __init__(self):
        self.target = document('Qoriginal', {'backend': 'pde.controlled', 'settings': {'diffusion': 2}}, 'pde')
        self.source = {'pde_document_id': 'Qoriginal', 'saved_revision': 'Rsaved',
                       'input_revision': self.target['input_revision'], 'input_sha256': canonical_hash(self.target['draft'])}
        self.result = {'candidates': [
            {'candidate_id': 'Cactual', 'execution_status': 'SUCCEEDED', 'values': {'diffusion': 3}},
            {'candidate_id': 'Cfailed', 'execution_status': 'FAILED', 'values': {'diffusion': 4}},
            {'candidate_id': 'Cpredicted', 'execution_status': 'PREDICTED', 'values': {'diffusion': 5}},
            {'candidate_id': 'Cother', 'execution_status': 'SUCCEEDED', 'values': {'diffusion': 6}}]}
        self.plan = document('Nrequest', request_draft({'purpose': 'Declared variables research', 'operation': 'doe',
            'inputs': deepcopy(self.target['draft']), 'budget': {'evaluations': 2}}, source=self.source))
        self.plan['runs'] = [{'job_id': 'Jactual', 'input_generation': 4, 'input_revision': 'Iplan',
                             'retained_state': 'SUCCEEDED', 'draft': deepcopy(self.plan['draft'])}]
        self.descriptors = [{'id': 'diffusion', 'label': 'Declared diffusion', 'unit': 'm2/s', 'value': 2, 'lower': 1, 'upper': 9,
                             'settings_path': ['diffusion']},
                            {'id': 'forcing', 'label': 'Declared forcing', 'unit': '1', 'value': 1, 'lower': .1, 'upper': 2}]
        self.calls = []
        self.started, self.release = threading.Event(), threading.Event()
        self.delay = None
        self.read_count = 0
        self.change_after_review = False

    def describe_inputs(self, request):
        self.calls.append(('describe', deepcopy(request)))
        if self.delay == 'describe':
            self.started.set()
            assert self.release.wait(5)
        return {'backend': request['backend'], 'inputs': deepcopy(self.descriptors)}

    def pde_candidate_preview(self, plan_id, job_id, candidate_id):
        self.calls.append(('preview', plan_id, job_id, candidate_id))
        if self.delay == 'preview':
            self.started.set()
            assert self.release.wait(5)
        return {'target_document_id': 'Qoriginal', 'source': deepcopy(self.source), 'candidate_id': candidate_id,
                'draft': {'backend': 'pde.controlled', 'settings': {'diffusion': 3}},
                'changes': [{'path': ['settings', 'diffusion'], 'before': 2, 'after': 3}],
                'executed': False, 'result_sha256': canonical_hash(self.result)}

    def document_read(self, identifier):
        self.calls.append(('read', identifier))
        if identifier == 'Nrequest':
            if self.delay == 'background':
                self.started.set()
                assert self.release.wait(5)
            return deepcopy(self.plan)
        self.read_count += 1
        if self.change_after_review and self.read_count == 2:
            self.target['generation'] += 1
        return deepcopy(self.target)

    def pde_adopt(self, **request):
        self.calls.append(('adopt', deepcopy(request)))
        return {'document': deepcopy(self.target), 'executed': False, 'command_id': request['command_id']}


def setup(client):
    window = RequestPlanWindow(client, auto_open=False, poll_interval=0)
    window._show_document(client.plan)
    window._result_cache['Jactual'] = deepcopy(client.result)
    window._draw_result()
    return window


def close(app, window, client):
    client.release.set()
    wait(app, lambda: not window._busy and not window._callbacks)
    window._allow_close = True
    window.close()


def test_declared_variables_actual_multiselect_dialog_keeps_model_and_bounds(app):
    client = Client()
    window = setup(client)
    original = window.edited_draft()
    def select():
        dialog = next(widget for widget in QApplication.topLevelWidgets() if isinstance(widget, QDialog) and widget.isVisible())
        table = dialog.findChild(QTableWidget, 'declaredModelVariables')
        assert table.rowCount() == 2
        assert [table.item(0, col).text() for col in (2, 3, 4, 5)] == ['m2/s', '2', '1', '9']
        assert not table.selectionModel().selectedRows()
        table.selectRow(0)
        # Timer refresh cannot occupy the foreground continuation in this modal.
        window.refresh_document()
        assert not any(call[0] == 'read' for call in client.calls)
        dialog.accept()
    QTimer.singleShot(50, select)
    try:
        window.choose_model_variables()
        wait(app, lambda: window.local_dirty and not window._busy)
        result = window.edited_draft()
        assert result['request']['inputs']['variables'] == [
            {key: client.descriptors[0][key] for key in ('id', 'unit', 'value', 'lower', 'upper')}]
        assert result['request']['operation'] == original['request']['operation']
        assert result['request']['inputs']['settings'] == original['request']['inputs']['settings']
        assert result['source'] == original['source']
        assert client.calls == [('describe', deepcopy(client.target['draft']))]
    finally:
        close(app, window, client)


def test_late_descriptors_do_not_replace_new_settings(app, monkeypatch):
    client = Client()
    client.delay = 'describe'
    window = setup(client)
    dialogs = []
    monkeypatch.setattr(window, '_select_model_variables', lambda rows: dialogs.append(rows) or rows)
    try:
        window.choose_model_variables()
        wait(app, client.started.is_set)
        window._edit_structure(lambda inputs: None)  # busy edit is disabled
        window.purpose.setText('New research purpose while reply pending')
        client.release.set()
        wait(app, lambda: not window._busy)
        assert not dialogs
        assert 'variables' not in window.edited_draft()['request']['inputs']
    finally:
        close(app, window, client)


@pytest.mark.parametrize('source', [None, {'kind': 'expert', 'document_id': 'Qoriginal'}, {'document_id': 'Qoriginal'}])
def test_adoption_requires_explicit_pde_source_and_actual_candidate(app, monkeypatch, source):
    client = Client()
    client.plan['draft']['source'] = source
    window = setup(client)
    try:
        window.candidates.selectRow(0)
        # Live edits cannot retarget a candidate computed from the retained run.
        assert window.pde_adopt_button.isEnabled()
        frozen = deepcopy(client.plan['runs'][0]['draft'])
        assert window._candidate_target(frozen['source']) == ('pde', 'Qoriginal')
        assert window.edited_draft()['source'] == source
        assert not client.calls
        reviewed = []
        monkeypatch.setattr(window, '_review_pde_changes', lambda preview: reviewed.append(deepcopy(preview)) or False)
        window.pde_adopt_button.click()
        wait(app, lambda: bool(reviewed) and not window._busy)
        assert reviewed[0]['source'] == frozen['source']
        assert reviewed[0]['target_document_id'] == 'Qoriginal'
        assert client.calls == [('preview', 'Nrequest', 'Jactual', 'Cactual'), ('read', 'Qoriginal')]
        assert window.document['runs'][0]['draft'] == frozen
        before_calls = deepcopy(client.calls)
        # Missing/non-PDE provenance on the computed run must prevent adoption.
        client.plan['runs'][0]['draft']['source'] = deepcopy(source)
        window._show_document(deepcopy(client.plan))
        assert window._selected_pde_candidate() == 'Cactual'
        assert not window.pde_adopt_button.isEnabled()
        window.review_pde_candidate()
        assert client.calls == before_calls and len(reviewed) == 1
        assert window.document['runs'][0]['draft']['source'] == source
        assert client.target['generation'] == 4 and client.target['draft']['settings']['diffusion'] == 2
    finally:
        close(app, window, client)


def test_only_successful_candidate_can_be_reviewed_and_selection_survives_read(app):
    client = Client()
    window = setup(client)
    try:
        assert not window._selected_pde_candidate()
        for row in (1, 2):
            window.candidates.selectRow(row)
            assert not window.pde_adopt_button.isEnabled()
            window.review_pde_candidate()
        window.candidates.selectRow(0)
        assert window.pde_adopt_button.isEnabled()
        window._show_document(deepcopy(client.plan))
        assert window._selected_pde_candidate() == 'Cactual'
        assert not client.calls
    finally:
        close(app, window, client)


def test_scalar_analysis_does_not_offer_pde_candidate_adoption(app):
    client = Client()
    client.plan['draft']['request']['operation'] = 'analyze'
    window = setup(client)
    try:
        window.candidates.selectRow(0)
        assert not window.pde_adopt_button.isEnabled()
        window.review_pde_candidate()
        assert not client.calls
    finally:
        close(app, window, client)


def test_review_adopts_exact_target_and_returns_without_execution(app, monkeypatch):
    client = Client()
    window = setup(client)
    launches = []
    monkeypatch.setattr('apps.research.desktop.launch_tool', lambda _, tool, **options: launches.append((tool, options)))
    def review(preview):
        assert preview['changes'] == [{'path': ['settings', 'diffusion'], 'before': 2, 'after': 3}]
        window.refresh_document()
        assert len([call for call in client.calls if call[0] == 'read']) == 1
        return True
    monkeypatch.setattr(window, '_review_pde_changes', review)
    try:
        window.candidates.selectRow(0)
        window.review_pde_candidate()
        wait(app, lambda: bool(launches) and not window._busy)
        assert [call[0] for call in client.calls] == ['preview', 'read', 'read', 'adopt']
        request = client.calls[-1][1]
        assert window._pde_adoption_request is None
        assert window._adoption_receipt is None
        assert request['pde_document_id'] == 'Qoriginal' and request['candidate_id'] == 'Cactual'
        assert request['expected_generation'] == 4 and request['session_id'] == 'Sowner'
        assert request['command_id'].startswith('C')
        assert launches == [('pde', {'document_id': 'Qoriginal'})]
    finally:
        close(app, window, client)


@pytest.mark.parametrize('change', ['candidate', 'job', 'document', 'session', 'draft'])
def test_late_preview_cannot_adopt_different_owner_or_selection(app, monkeypatch, change):
    client = Client()
    client.delay = 'preview'
    window = setup(client)
    monkeypatch.setattr(window, '_review_pde_changes', lambda _: pytest.fail('Stale preview must not open review'))
    try:
        window.candidates.selectRow(0)
        window.review_pde_candidate()
        wait(app, client.started.is_set)
        if change == 'candidate':
            window.candidates.selectRow(3)
        elif change == 'job':
            window.runs.clearSelection()
        elif change == 'document':
            window.document['id'] = 'Nother'
        elif change == 'session':
            window.document['session_id'] = 'Sother'
        else:
            window.purpose.setText('Changed request')
        client.release.set()
        wait(app, lambda: not window._busy)
        assert [call[0] for call in client.calls] == ['preview']
    finally:
        close(app, window, client)


@pytest.mark.parametrize('change', ['source_input', 'review_generation', 'cancel'])
def test_changed_target_or_cancelled_review_never_adopts(app, monkeypatch, change):
    client = Client()
    if change == 'source_input':
        client.target['draft']['settings']['diffusion'] = 9
    client.change_after_review = change == 'review_generation'
    window = setup(client)
    monkeypatch.setattr(window, '_review_pde_changes', lambda _: change != 'cancel')
    try:
        window.candidates.selectRow(0)
        window.review_pde_candidate()
        wait(app, lambda: not window._busy and len(client.calls) >= 2)
        assert not any(call[0] == 'adopt' for call in client.calls)
        assert window._pde_adoption_request is None
    finally:
        close(app, window, client)


def test_explicit_review_waits_for_background_read_without_lost_action(app, monkeypatch):
    client = Client()
    client.delay = 'background'
    window = setup(client)
    monkeypatch.setattr(window, '_review_pde_changes', lambda _: False)
    try:
        window.candidates.selectRow(0)
        window.refresh_document()
        wait(app, client.started.is_set)
        assert window.pde_adopt_button.isEnabled()
        assert window.review_pde_candidate()
        assert window._pending_adoption
        client.release.set()
        wait(app, lambda: not window._busy and any(call[0] == 'preview' for call in client.calls))
        assert [call[0] for call in client.calls] == ['read', 'preview', 'read']
        assert not window._pending_adoption
    finally:
        close(app, window, client)
