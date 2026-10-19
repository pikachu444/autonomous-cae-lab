"""Actual Qt adoption recovery against controlled lost owner acknowledgements.

No numerical engine, solver, provider or desktop process runs here.
"""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from copy import deepcopy
import threading
import time

import pytest
pytest.importorskip('PySide6')
pytest.importorskip('matplotlib')
from PySide6.QtWidgets import QApplication, QMessageBox

from apps.research.numerical_window import NumericalWindow
from apps.research.request_plan_window import RequestPlanWindow
from caelab.material_document import default_draft as material_draft
from caelab.numerical_document import from_material_document, request_draft
from caelab.storage import canonical_hash


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


def wait(app, predicate):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return
        time.sleep(.005)
    raise AssertionError('Controlled adoption receipt did not settle')


def document(identifier, draft, kind):
    return {'id': identifier, 'kind': kind, 'title': 'Receipt software fixture', 'session_id': 'Sowner',
            'generation': 4, 'input_revision': 'Ioriginal', 'draft': deepcopy(draft), 'diagnostics': [],
            'dirty': False, 'runs': [], 'can_undo': False, 'can_redo': False}


class LostReceipt:
    def __init__(self, kind):
        self.kind = kind
        draft = material_draft() if kind == 'material' else {'backend': 'pde.controlled', 'settings': {'diffusion': 2}}
        self.target = document('Moriginal' if kind == 'material' else 'Qoriginal', draft, kind)
        self.source = {'pde_document_id': self.target['id'], 'saved_revision': 'Rsaved',
                       'input_revision': 'Ioriginal', 'input_sha256': canonical_hash(draft)}
        self.result = {'candidates': [{'candidate_id': 'Cactual', 'execution_status': 'SUCCEEDED', 'values': {}, 'objective': 1},
                                     {'candidate_id': 'Cother', 'execution_status': 'SUCCEEDED', 'values': {}, 'objective': 2}]}
        plan_draft = (from_material_document(self.target) if kind == 'material' else
            request_draft({'purpose': 'Receipt recovery', 'operation': 'doe', 'inputs': deepcopy(draft),
                           'budget': {'evaluations': 2}}, source=self.source))
        if kind == 'material':
            # The coefficient preview validates a real plan before sending an adoption.
            plan_draft.update(mode='doe', count=2, budget=2)
            self.result['kind'] = 'doe'
            for candidate, value in zip(self.result['candidates'], (1100, 1200)):
                candidate['values'] = {'E': value}
        self.plan = document('Noriginal', plan_draft, 'numerical')
        self.plan['runs'] = [{'job_id': 'Joriginal', 'input_generation': 4, 'input_revision': 'Iplan',
                             'draft': deepcopy(plan_draft), 'retained_state': 'SUCCEEDED', 'retention_complete': True}]
        self.requests, self.reads = [], []
        self.first_failure = 'lost'
        self.delay_retry = False
        self.started, self.release = threading.Event(), threading.Event()
        self.applications = 0
        self.receipt = None

    def document_read(self, identifier):
        self.reads.append(identifier)
        return deepcopy(self.target if identifier == self.target['id'] else self.plan)

    def pde_candidate_preview(self, plan_id, job_id, candidate_id):
        return {'target_document_id': self.target['id'], 'candidate_id': candidate_id, 'source': deepcopy(self.source),
                'draft': deepcopy(self.target['draft']), 'changes': [], 'executed': False,
                'result_sha256': canonical_hash(self.result)}

    def _adopt(self, request):
        self.requests.append(deepcopy(request))
        if self.receipt is None:
            self.applications += 1
            self.target['generation'] += 1
            self.receipt = {'command_id': request['command_id'], 'document': deepcopy(self.target)}
        else:
            assert request == self.requests[0], 'Recovery must resend the exact original request'
        if len(self.requests) == 1:
            if self.first_failure == 'lost':
                raise ConnectionError('CONTROLLED owner applied; acknowledgement lost')
            if self.first_failure == 'wrong_id':
                return {**deepcopy(self.receipt), 'command_id': 'Cunrelated'}
        if self.delay_retry:
            self.started.set()
            assert self.release.wait(5)
        return deepcopy(self.receipt)

    def numerical_adopt(self, document_id, job_id, candidate_id, **options):
        return self._adopt(dict(document_id=document_id, job_id=job_id, candidate_id=candidate_id, **options))

    def pde_adopt(self, plan_id, job_id, candidate_id, **options):
        return self._adopt(dict(plan_id=plan_id, job_id=job_id, candidate_id=candidate_id, **options))


def setup(client, monkeypatch):
    cls = NumericalWindow if client.kind == 'material' else RequestPlanWindow
    window = cls(client, auto_open=False, poll_interval=0)
    window._show_document(client.plan)
    assert window.edited_draft() == client.plan['draft']
    window._result_cache['Joriginal'] = deepcopy(client.result)
    window._draw_result()
    window.candidates.selectRow(0)
    monkeypatch.setattr(QMessageBox, 'question', lambda *args, **kwargs: QMessageBox.StandardButton.Yes)
    monkeypatch.setattr('apps.research.desktop.launch_tool', lambda *args, **kwargs: {'status': 'CONTROLLED_NO_PROCESS'})
    if client.kind == 'pde':
        monkeypatch.setattr(window, '_review_pde_changes', lambda _: True)
    return window


def begin(window, kind):
    return window.adopt_candidate() if kind == 'material' else window.review_pde_candidate()


def close(app, window, client):
    client.release.set()
    wait(app, lambda: not window._busy and not window._callbacks)
    window._allow_close = True
    window.close()


@pytest.mark.parametrize('kind', ['material', 'pde'])
@pytest.mark.parametrize('failure', ['lost', 'wrong_id'])
def test_explicit_receipt_retry_uses_frozen_payload_without_new_target_or_uuid(app, monkeypatch, kind, failure):
    client = LostReceipt(kind)
    client.first_failure = failure
    window = setup(client, monkeypatch)
    try:
        begin(window, kind)
        wait(app, lambda: len(client.requests) == 1 and not window._busy)
        pending = window._adoption_receipt
        assert pending and window.retry_adoption_button.isEnabled()
        frozen = deepcopy(client.requests[0])
        assert all(value in window.adoption_receipt_label.toolTip() for value in
                   (client.target['id'], 'Joriginal', 'Cactual', frozen['command_id']))
        assert '아직 확인하지 못했습니다' in window.message.text()
        assert not (window.adopt_button if kind == 'material' else window.pde_adopt_button).isEnabled()
        # New selection/document/target state cannot replace the frozen request.
        window.candidates.selectRow(1)
        begin(window, kind)
        assert client.requests == [frozen]
        other = deepcopy(client.plan)
        other['id'] = 'Nother'
        window._show_document(other)
        client.target['generation'] = 90
        reads = list(client.reads)
        assert window._adoption_receipt is pending
        assert 'Cactual' in window.adoption_receipt_label.toolTip()
        assert window.retry_adoption_receipt()
        wait(app, lambda: window._adoption_receipt is None and not window._busy)
        assert client.requests == [frozen, frozen]
        assert client.reads == reads
        assert client.applications == 1
        assert window.document['id'] == 'Nother'
        assert window.retry_adoption_button.isHidden()
        if kind == 'pde':
            assert window._pde_adoption_request is None
    finally:
        close(app, window, client)


@pytest.mark.parametrize('kind', ['material', 'pde'])
def test_session_change_preserves_unresolved_info_and_rejects_rebased_retry(app, monkeypatch, kind):
    client = LostReceipt(kind)
    window = setup(client, monkeypatch)
    try:
        begin(window, kind)
        wait(app, lambda: len(client.requests) == 1 and not window._busy)
        pending = window._adoption_receipt
        window.document['session_id'] = 'Srestarted'
        window._update_actions()
        assert not window.retry_adoption_button.isEnabled()
        assert '연결이 바뀌어' in window.adoption_receipt_label.text()
        assert not window.retry_adoption_receipt()
        begin(window, kind)
        assert window._adoption_receipt is pending and len(client.requests) == 1
        assert pending['request']['session_id'] == 'Sowner'
    finally:
        close(app, window, client)


@pytest.mark.parametrize('kind', ['material', 'pde'])
def test_late_retry_acknowledges_exact_receipt_without_overwriting_new_document(app, monkeypatch, kind):
    client = LostReceipt(kind)
    window = setup(client, monkeypatch)
    try:
        begin(window, kind)
        wait(app, lambda: len(client.requests) == 1 and not window._busy)
        client.delay_retry = True
        window.retry_adoption_receipt()
        wait(app, client.started.is_set)
        other = deepcopy(client.plan)
        other['id'], other['session_id'] = 'Nnew', 'Snew'
        window._show_document(other)
        client.release.set()
        wait(app, lambda: not window._busy)
        assert window._adoption_receipt is None  # exact old receipt was acknowledged
        assert window.document['id'] == 'Nnew' and window.document['session_id'] == 'Snew'
        assert client.requests[0] == client.requests[1] and client.applications == 1
    finally:
        close(app, window, client)


def test_receipt_retry_waits_behind_background_read_and_is_not_automatic(app, monkeypatch):
    client = LostReceipt('material')
    window = setup(client, monkeypatch)
    started, release = threading.Event(), threading.Event()
    try:
        begin(window, 'material')
        wait(app, lambda: len(client.requests) == 1 and not window._busy)
        for _ in range(10):
            app.processEvents()
        assert len(client.requests) == 1  # no hidden resend
        def read():
            started.set()
            assert release.wait(5)
            return deepcopy(client.plan)
        window._call(read, lambda _: None, background=True)
        wait(app, started.is_set)
        assert window.retry_adoption_receipt()
        assert window._pending_adoption
        release.set()
        wait(app, lambda: window._adoption_receipt is None and not window._busy)
        assert len(client.requests) == 2 and client.requests[0] == client.requests[1]
    finally:
        release.set()
        close(app, window, client)
