"""Actual Qt nested-dialog dispatch with controlled retained results; no solver run."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'

from copy import deepcopy
import threading
import time

import pytest
pytest.importorskip('PySide6')
pytest.importorskip('matplotlib')
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QMessageBox

from apps.research.numerical_window import NumericalWindow
from caelab.material_document import default_draft
from caelab.numerical_document import from_material_document


def wait(app, condition, seconds=3):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        app.processEvents()
        if condition():
            return
        time.sleep(.005)
    raise AssertionError('Numerical GUI action did not settle')


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


class RetainedClient:
    """A controllable service boundary; candidates are retained fixture data."""
    def __init__(self):
        self.material = {'id': 'Mtarget', 'title': 'Target material',
                         'session_id': 'Sservice', 'generation': 0,
                         'input_revision': 'Imaterial', 'draft': default_draft()}
        draft = from_material_document(self.material)
        # Retained fit candidates need the submitted observation/protocol too.
        # No import or solve is performed by this controlled service boundary.
        draft['experiments'] = [{
            'id': 'Efixture', 'role': 'fit',
            'source': {'document_id': 'Tfixture', 'job_id': 'Jimport',
                       'response': 'measured_stress', 'input_revision': 'Idata',
                       'input_sha256': 'a' * 64},
            'response': 'stress_xx', 'settings': deepcopy(self.material['draft']['settings']),
            'weight': 1., 'scale': 1.,
        }]
        self.plan = {'id': 'Nplan', 'title': 'Retained Plan',
                     'session_id': 'Sservice', 'generation': 0, 'input_revision': 'Iplan',
                     'draft': draft, 'dirty': False, 'diagnostics': [],
                     'runs': [{'job_id': 'Jretained', 'input_generation': 0,
                               'input_revision': 'Iplan', 'draft': deepcopy(draft),
                               'is_current_input': True, 'retention_complete': True,
                               'retained_state': 'SUCCEEDED', 'retained_result': {'revision': 'Rsaved'}}]}
        self.result = {'kind': 'fit', 'execution_status': 'SUCCEEDED', 'curves': [],
                       'candidates': [{'candidate_id': 'C000015', 'execution_status': 'SUCCEEDED',
                                       'values': {'E': 1234}, 'objective': .01},
                                      {'candidate_id': 'C000016', 'execution_status': 'SUCCEEDED',
                                       'values': {'E': 1250}, 'objective': .02}]}
        self.poll_entered = threading.Event()
        self.poll_release = threading.Event()
        self.plan_reads = 0
        self.adoption_attempts, self.adoptions = [], []

    def document_read(self, identifier):
        if identifier == self.material['id']:
            return deepcopy(self.material)
        if identifier == 'Tfixture':
            return {'id': identifier, 'kind': 'data', 'title': 'Retained test observations',
                    'runs': [{'job_id': 'Jimport', 'input_revision': 'Idata',
                              'input_sha256': 'a' * 64}]}
        assert identifier == self.plan['id']
        self.plan_reads += 1
        self.poll_entered.set()
        assert self.poll_release.wait(3), 'Test did not release its background read'
        return deepcopy(self.plan)

    def document_result(self, identifier, job_id):
        assert (identifier, job_id) == ('Tfixture', 'Jimport')
        return {'execution_status': 'SUCCEEDED', 'responses': {'measured_stress': {
            'kind': 'curve', 'unit': 'MPa', 'value': [0., 10.],
            'axes': [{'name': 'time', 'unit': 's', 'values': [0., 1.]}]}}}

    def numerical_adopt(self, document_id, job_id, candidate_id, **options):
        args = (document_id, job_id, candidate_id, deepcopy(options))
        self.adoption_attempts.append(args)
        if (options['session_id'], options['expected_generation']) != (self.material['session_id'], self.material['generation']):
            raise ValueError('Target Material generation changed; no coefficients applied')
        assert options['material_document_id'] == self.material['id']
        self.adoptions.append(args)
        self.material['generation'] += 1
        return {'command_id': options['command_id'], 'document': deepcopy(self.material)}


def make_window(client):
    window = NumericalWindow(client, auto_open=False, poll_interval=100)
    window.timer.stop()
    window._show_document(client.plan)
    window._result_cache['Jretained'] = deepcopy(client.result)
    window._draw_result()
    window.candidates.selectRow(0)
    window.show()
    wait(QApplication.instance(), lambda: not window._busy and not window._trial_source_queue)
    return window


def dialog_answer(monkeypatch, window, *, answer, in_dialog=None):
    """Use the real modal event loop, while the 100 ms refresh timer runs."""
    real_question = QMessageBox.question
    seen = []

    def question(*args):
        seen.append(args[2])
        window.timer.start(100)
        def respond():
            box = QApplication.activeModalWidget()
            assert isinstance(box, QMessageBox)
            if in_dialog:
                in_dialog()
            box.button(answer).click()
        QTimer.singleShot(250, respond)
        return real_question(*args)

    monkeypatch.setattr(QMessageBox, 'question', question)
    return seen


def close_window(app, window, client):
    window.timer.stop()
    client.poll_release.set()
    wait(app, lambda: not window._busy)
    window._allow_close = True
    window.close()


def test_adoption_survives_refresh_timer_during_real_confirmation(app, monkeypatch):
    client = RetainedClient()
    window = make_window(client)
    seen = dialog_answer(monkeypatch, window, answer=QMessageBox.StandardButton.Yes)
    try:
        assert window.adopt_button.isEnabled()
        window.adopt_button.click()
        wait(app, lambda: client.material['generation'] == 1, seconds=1.5)
        assert len(seen) == 1 and 'Target material' in seen[0] and '1234' in seen[0]
        assert len(client.adoption_attempts) == len(client.adoptions) == 1
        assert client.adoptions[0][:3] == ('Nplan', 'Jretained', 'C000015')
        assert client.adoptions[0][3]['expected_generation'] == 0
        client.poll_release.set()
        wait(app, lambda: client.poll_entered.is_set())
        assert window.timer.isActive()  # Read-only refresh resumes after the action.
    finally:
        close_window(app, window, client)


def test_click_during_background_read_is_retained_once(app, monkeypatch):
    client = RetainedClient()
    window = make_window(client)
    seen = dialog_answer(monkeypatch, window, answer=QMessageBox.StandardButton.Yes)
    try:
        window.refresh_document()
        wait(app, client.poll_entered.is_set)
        assert window._busy and window.adopt_button.isEnabled()
        window.adopt_button.click()
        assert window._pending_adoption is not None
        assert not window.adopt_button.isEnabled()
        window.adopt_button.click()  # Disabled duplicate must not enqueue another action.
        assert not client.adoption_attempts
        client.poll_release.set()
        wait(app, lambda: client.material['generation'] == 1)
        assert len(seen) == len(client.adoption_attempts) == 1
        assert client.adoptions[0][:3] == ('Nplan', 'Jretained', 'C000015')
        assert window._pending_adoption is None
    finally:
        close_window(app, window, client)


def test_cancel_confirmation_does_not_adopt_and_polling_resumes(app, monkeypatch):
    client = RetainedClient()
    window = make_window(client)
    seen = dialog_answer(monkeypatch, window, answer=QMessageBox.StandardButton.Cancel)
    try:
        window.adopt_button.click()
        wait(app, lambda: bool(seen) and not window._busy)
        assert client.material['generation'] == 0 and not client.adoption_attempts
        client.poll_release.set()
        wait(app, client.poll_entered.is_set)
        assert window.timer.isActive() and window.selected_candidate() == 'C000015'
    finally:
        close_window(app, window, client)


@pytest.mark.parametrize('change', ['candidate', 'run', 'local_edit'])
def test_confirmation_never_applies_after_selection_or_edit_changes(app, monkeypatch, change):
    client = RetainedClient()
    other_run = {**deepcopy(client.plan['runs'][0]), 'job_id': 'Jother'}
    client.plan['runs'].append(other_run)
    window = make_window(client)
    window._result_cache['Jother'] = deepcopy(client.result)
    window.runs.selectRow(0)
    window.candidates.selectRow(0)
    def alter_selection():
        if change == 'candidate':
            window.candidates.selectRow(1)
        elif change == 'run':
            window.runs.selectRow(1)
            window.candidates.selectRow(0)  # Same candidate label, different immutable run.
        else:
            window.variables.item(0, 3).setText('unfinished bound')
    seen = dialog_answer(monkeypatch, window, answer=QMessageBox.StandardButton.Yes,
                         in_dialog=alter_selection)
    try:
        window.adopt_button.click()
        wait(app, lambda: bool(seen) and not window._busy)
        assert client.material['generation'] == 0 and not client.adoption_attempts
        assert client.plan['runs'][0]['job_id'] == 'Jretained'
        if change == 'local_edit':
            assert window.local_dirty
            assert window.edited_draft()['variables'][0]['lower'] == 'unfinished bound'
    finally:
        close_window(app, window, client)


def test_material_change_during_confirmation_uses_original_guard(app, monkeypatch):
    client = RetainedClient()
    window = make_window(client)
    dialog_answer(monkeypatch, window, answer=QMessageBox.StandardButton.Yes,
                  in_dialog=lambda: client.material.update(generation=1))
    try:
        window.adopt_button.click()
        wait(app, lambda: bool(client.adoption_attempts) and not window._busy)
        assert 'Target Material generation changed' in window.message.toolTip()
        assert client.material['generation'] == 1 and not client.adoptions
        assert len(client.adoption_attempts) == 1
        assert client.adoption_attempts[0][3]['expected_generation'] == 0
        assert window.selected_candidate() == 'C000015'
    finally:
        close_window(app, window, client)
