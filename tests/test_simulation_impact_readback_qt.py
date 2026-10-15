"""Actual Qt interactions over controlled command receipts; no HTTP/solver/provider run."""
from copy import deepcopy
import io
import os
from pathlib import Path
import threading
import time
from urllib.error import HTTPError

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
pytest.importorskip('PySide6')
from PySide6.QtCore import QTimer
from PySide6.QtGui import QAction
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QInputDialog

from apps.research.simulation_window import SimulationWindow
from caelab.simulation_document import default_draft
from caelab.workbench_client import WorkbenchHTTPError
from test_simulation_layout import Client as LayoutClient


def http_error(code):
    raw = HTTPError('http://127.0.0.1/test-only', code, 'controlled refusal', {}, io.BytesIO())
    return WorkbenchHTTPError(raw, b'{}', '보존된 출력의 요청을 확인하세요.')


def until(app, predicate):
    deadline = time.monotonic() + 6
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return
        QTest.qWait(10)
    raise AssertionError('Controlled Qt reply did not settle')


class ReadClient(LayoutClient):
    """Only submission/receipt boundary is doubled, never native physics."""
    def __init__(self, root):
        super().__init__(root)
        self.d0 = default_draft('explicit.opencourant.model')
        self.d1 = deepcopy(self.d0)
        self.d1['settings']['time']['end_s'] *= 2
        self.doc = self.owner.open(title='충격 시편', draft=self.d1)
        self.doc['runs'] = [
            {'job_id': job, 'operation': 'simulation.run', 'draft': deepcopy(self.d0),
             'is_current_input': False, 'state': 'FAILED'} for job in ('Jsource', 'Jother')]
        self.calls, self.reads, self.receipts = [], [], {}
        self.gate = None
        self.started = threading.Event()
        self.loss = None
        self.refusal = None
        self.bad_source = False

    def document_read(self, identifier):
        assert identifier == self.doc['id']
        return deepcopy(self.doc)

    def document_result(self, identifier, job):
        self.reads.append((identifier, job))
        return {'execution_status': 'SUCCEEDED' if job.startswith('Jread') else 'FAILED',
                'backend': 'impact.reprocess' if job.startswith('Jread') else 'explicit.opencourant.model',
                'source_execution_status': 'FAILED', 'solver_execution': 'NOT_PERFORMED',
                'responses': {'kinetic_energy': {'kind': 'scalar', 'value': 6.5e-6, 'unit': 'J'}}}

    def document_command(self, identifier, operation, arguments, **options):
        assert operation == 'simulation.reprocess', 'GUI applied/evaluated the current draft'
        self.calls.append((identifier, operation, deepcopy(arguments), deepcopy(options)))
        self.started.set()
        if self.gate:
            assert self.gate.wait(5)
        if self.refusal is not None:
            code, self.refusal = self.refusal, None
            raise http_error(code)
        command = options['command_id']
        if command not in self.receipts:
            job = {'id': 'Jread' + str(len(self.receipts) + 1), 'operation': 'impact.reprocess',
                   'arguments': deepcopy(arguments), 'state': 'QUEUED'}
            run = {'job_id': job['id'], 'operation': 'impact.reprocess', 'draft': deepcopy(self.d0),
                   'is_current_input': False}
            self.doc['runs'].append(run)
            self.receipts[command] = {'document': deepcopy(self.doc), 'job': job}
        receipt = deepcopy(self.receipts[command])
        if self.bad_source:
            receipt['job']['arguments']['source_job_id'] = 'Jother'
        if self.loss:
            kind, self.loss = self.loss, None
            raise OSError('Controlled reply lost after admission') if kind == 'transport' else http_error(503)
        return receipt


@pytest.fixture(scope='module')
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def viewer(tmp_path, app):
    client = ReadClient(tmp_path)
    window = SimulationWindow(client, auto_open=False, poll_interval=0)
    window._show_document(client.doc)
    window._selected_job = 'Jsource'
    window._result_key = (client.doc['id'], 'Jsource')
    window._accept_result(client.document_result(client.doc['id'], 'Jsource'))
    window._update_actions()
    yield window, client
    if client.gate:
        client.gate.set()
    until(app, lambda: not window._busy)
    window._allow_close = True
    window.close()
    app.processEvents()


def choose(monkeypatch, *, index=0, accepted=True, during=None):
    calls = []
    def answer(parent, title, prompt, labels, current, editable):
        assert threading.current_thread() is threading.main_thread()
        assert current == 0 and editable is False
        calls.append(list(labels))
        if during:
            during()
        return labels[index], accepted
    monkeypatch.setattr(QInputDialog, 'getItem', answer)
    return calls


@pytest.mark.parametrize('index,convert', [(0, False), (1, True)])
def test_selected_original_input_is_read_without_applying_current_draft(viewer, app, monkeypatch, index, convert):
    window, client = viewer
    window.tree.setCurrentItem(window._run_nodes['Jsource'])
    until(app, lambda: not window._busy)
    choices = choose(monkeypatch, index=index)
    original = deepcopy(client.doc['runs'][0])
    before = window.edited_draft()
    assert before == client.d1 and before != original['draft']
    assert isinstance(window.reprocess_impact_action, QAction)
    assert window.reprocess_impact_action.objectName() == 'impactReprocessAction'
    assert window.reprocess_impact_action.isEnabled()
    window.reprocess_impact_action.trigger()
    until(app, lambda: not window._busy and window._selected_job == 'Jread1' and window._result_key is not None)
    assert len(client.calls) == 1
    assert client.calls[0][2] == {'source_job_id': 'Jsource', 'convert_raw': convert}
    assert window.edited_draft() == before == client.doc['draft']
    assert client.doc['runs'][0] == original
    assert choices == [['저장된 결과 파일 읽기', '원 ANIM/TH를 다시 변환해 읽기']]
    assert not window._impact_read_requests
    assert (client.doc['id'], 'Jread1') in client.reads
    assert window.tree.currentItem() is window._run_nodes['Jread1']


def test_cancel_has_no_command(viewer, app, monkeypatch):
    window, client = viewer
    choose(monkeypatch, accepted=False)
    window.reprocess_impact_action.trigger()
    app.processEvents()
    assert client.calls == [] and not window._impact_read_requests
    assert window._selected_job == 'Jsource'


def edit_model(window):
    window.backend.setText('편집 중인 모델')
    assert window.local_dirty
    return window.edited_draft()


def test_unapplied_edit_blocks_new_request_and_keeps_input(viewer, app, monkeypatch):
    window, client = viewer
    edited = edit_model(window)
    monkeypatch.setattr(QInputDialog, 'getItem', lambda *a: pytest.fail('Dirty input opened a new request'))
    assert not window.reprocess_impact_action.isEnabled()
    window.reprocess_impact()
    app.processEvents()
    assert client.calls == [] and window.edited_draft() == edited


def test_session_changed_inside_modal_never_submits(viewer, app, monkeypatch):
    window, client = viewer
    choose(monkeypatch, during=lambda: window.document.update(session_id='Snew-owner'))
    window.reprocess_impact_action.trigger()
    app.processEvents()
    assert client.calls == [] and not window._impact_read_requests


@pytest.mark.parametrize('change', ['document', 'selected_source'])
def test_late_reply_cannot_open_another_selection(viewer, app, monkeypatch, change):
    window, client = viewer
    choose(monkeypatch)
    client.gate = threading.Event()
    window.reprocess_impact_action.trigger()
    until(app, client.started.is_set)
    if change == 'document':
        other = deepcopy(window.document)
        other.update(id='Vother', session_id='Sother', title='다른 충격 시편')
        window._show_document(other)
    window.tree.setCurrentItem(window._run_nodes['Jother'])
    window._selected_job = 'Jother'
    window._result_key = (window.document['id'], 'Jother')
    expected_owner = (window.document['id'], window.document['session_id'])
    client.gate.set()
    until(app, lambda: not window._busy)
    assert (window.document['id'], window.document['session_id']) == expected_owner
    assert window._selected_job == 'Jother'
    assert window._result_key == (expected_owner[0], 'Jother')
    assert window.tree.currentItem() is window._run_nodes['Jother']


def test_edit_while_waiting_survives_successful_receipt(viewer, app, monkeypatch):
    window, client = viewer
    choose(monkeypatch)
    client.gate = threading.Event()
    window.reprocess_impact_action.trigger()
    until(app, client.started.is_set)
    edited = edit_model(window)
    client.gate.set()
    until(app, lambda: not window._busy and window._selected_job == 'Jread1')
    assert window.local_dirty and window.edited_draft() == edited
    assert client.doc['draft'] == client.d1


@pytest.mark.parametrize('loss', ['transport', 'server'])
def test_unknown_reply_reuses_exact_command_even_after_local_edit(viewer, app, monkeypatch, loss):
    window, client = viewer
    choices = choose(monkeypatch, index=1)
    client.loss = loss
    window.reprocess_impact_action.trigger()
    until(app, lambda: not window._busy)
    assert len(client.calls) == 1 and len(window._impact_read_requests) == 1
    edited = edit_model(window)
    assert window.reprocess_impact_action.isEnabled()
    window.reprocess_impact_action.trigger()
    until(app, lambda: not window._busy and window._selected_job == 'Jread1')
    assert client.calls[0] == client.calls[1]
    assert len(client.receipts) == 1 and len(choices) == 1
    assert not window._impact_read_requests
    assert window.local_dirty and window.edited_draft() == edited


def test_explicit_refusal_releases_request_and_retry_uses_new_identity(viewer, app, monkeypatch):
    window, client = viewer
    choices = choose(monkeypatch)
    client.refusal = 409
    window.reprocess_impact_action.trigger()
    until(app, lambda: not window._busy)
    assert not window._impact_read_requests and window._selected_job == 'Jsource'
    window.reprocess_impact_action.trigger()
    until(app, lambda: not window._busy and window._selected_job == 'Jread1')
    assert client.calls[0][3]['command_id'] != client.calls[1][3]['command_id']
    assert client.calls[0][2] == client.calls[1][2]
    assert len(choices) == 2


def test_receipt_for_different_source_is_not_opened(viewer, app, monkeypatch):
    window, client = viewer
    choose(monkeypatch)
    client.bad_source = True
    window.reprocess_impact_action.trigger()
    until(app, lambda: not window._busy)
    assert window._selected_job == 'Jsource' and window._impact_read_requests
    assert not any(job.startswith('Jread') for _, job in client.reads)


def test_partial_caption_uses_counts_when_indices_are_data_references(viewer, app):
    window, client = viewer
    result = client.document_result(client.doc['id'], 'Jsource')
    result.update(operation='impact.reprocess', execution_status='FAILED',
                  diagnostics={'readback_scopes': {
                      'history': {'status': 'PARTIAL', 'available_samples': 17,
                                  'sample_indices': {'data_ref': 'preserved-history'}},
                      'animation': {'status': 'PARTIAL', 'available_frame_count': 3,
                                    'unavailable_frame_count': 2, 'expected_slots': 5,
                                    'available_frame_indices': {'data_ref': 'preserved-frames'},
                                    'unavailable_frames': {'data_ref': 'missing-frames'}}}})
    window._accept_result(result)
    app.processEvents()
    caption = window.result_label.text()
    for expected in ('읽기 실패 또는 일부만 읽음', '이력 17개 (일부만 읽음)',
                     '공간 결과 3/5시각', '누락·손상 2시각', '원 계산: 실패', '새 솔버 계산 없음'):
        assert expected in caption
    assert window._result['execution_status'] == 'FAILED'
    assert client.calls == []


def test_actual_qt_research_menu_renders_normal_and_narrow(viewer, app):
    window, client = viewer
    research = next(action.menu() for action in window.menuBar().actions() if '연구' in action.text())
    assert window.reprocess_impact_action in research.actions()
    assert window.reprocess_impact_action.text() == '보존 결과 다시 읽기…'
    capture = os.environ.get('CAE_IMPACT_READBACK_CAPTURE_DIR')
    window.show()
    for name, size in [('normal', (1440, 900)), ('narrow', (1000, 680))]:
        window.resize(*size)
        app.processEvents()
        research.popup(window.menuBar().mapToGlobal(window.menuBar().actionGeometry(research.menuAction()).bottomLeft()))
        app.processEvents()
        if capture:
            folder = Path(capture)
            folder.mkdir(parents=True, exist_ok=True)
            assert window.grab().save(str(folder / (name + '-simulation.png')))
            assert research.grab().save(str(folder / (name + '-menu.png')))
        research.hide()
    assert client.calls == []
