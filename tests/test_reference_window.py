"""Real Qt threads and cursor/view controls; reference reader boundary controlled.

No solver, inference, native host or shared owner campaign is started.
"""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from copy import deepcopy
import threading
import time
from types import SimpleNamespace

import pytest
pytest.importorskip('PySide6')
pytest.importorskip('matplotlib')
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from PySide6.QtCore import QCoreApplication, QEvent, Qt
from apps.research.reference_window import ReferenceWindow
from caelab.study_document import StudyDocuments, default_draft
from caelab.research_workflows import resolve_reference
from caelab.storage import canonical_hash


@pytest.fixture
def application():
    return QApplication.instance() or QApplication([])


def wait(app, predicate):
    end = time.monotonic() + 5
    while time.monotonic() < end:
        app.processEvents()
        if predicate():
            return
        time.sleep(.005)
    raise AssertionError('Reference read did not settle')


RESULT_REF = {'kind': 'result', 'document_id': 'Npublic', 'job_id': 'Jpublic',
              'input_revision': 'Ipublic', 'input_sha256': 'a' * 64,
              'result_sha256': 'b' * 64, 'response': 'stress_xx'}
PAYLOAD = {'status': 'AVAILABLE', 'kind': 'result', 'metadata': {'responses':
    [{'response': 'stress_xx', 'unit': 'MPa'}, {'response': 'stress_yy', 'unit': 'MPa'}]},
    'result': {'responses': {'stress_xx': {'kind': 'scalar', 'value': 1.234567891234,
                                             'unit': 'MPa'}}}}


class Reader:
    def __init__(self, replies):
        self.replies, self.calls = list(replies), []

    def research_reference(self, reference):
        self.calls.append(deepcopy(reference))
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return deepcopy(reply)


@pytest.mark.parametrize('backend,expected', [
    ('pde.scipy.ode', ['-rate*(temperature-ambient)', '0.5', '1/s', 'K']),
    ('pde.scikit_fem.dimensioned', ['k*inner(grad(u),grad(v))', 'left_value', 'W/(m*K)', '경계 조건'])])
def test_saved_pde_input_is_readable_without_loading_current_owner(application, backend, expected):
    from caelab.pde_document import default_draft as pde_draft
    draft = pde_draft(backend)
    # Authored expression text is escaped for display, never evaluated as HTML.
    draft['settings']['reference_note'] = '<original input>'
    payload = {'status': 'AVAILABLE', 'kind': 'document',
               'document': {'id': 'Qsaved', 'kind': 'pde', 'title': '저장한 PDE 입력', 'draft': draft}}
    original = deepcopy(payload)
    reference = {'kind': 'document', 'document_kind': 'pde', 'document_id': 'Qsaved',
                 'saved_revision': 'Rsaved', 'input_revision': 'Isaved', 'input_sha256': canonical_hash(draft)}
    reader = Reader([payload]); window = ReferenceWindow(reader, reference)
    try:
        wait(application, lambda: not window._busy)
        text = window.content.body.toPlainText()
        for value in expected:
            assert value in text
        assert '<original input>' in text and '현재 편집 중인 모델과 별도로' in text
        assert '원래 프로그램에서 저장된 모델을 열어' not in text
        assert reader.calls == [reference] and payload == original
        assert window.content.result_views.isHidden() and window.content.channel.isHidden()
    finally:
        window.close()


def test_retry_failed_initial_and_response_preserves_exact_request(application):
    selected = deepcopy(PAYLOAD)
    selected['result']['responses'] = {'stress_yy': {'kind': 'scalar', 'value': .234567891234,
                                                   'unit': 'MPa'}}
    reader = Reader([RuntimeError('private technical error'), PAYLOAD,
                     RuntimeError('subset unavailable'), selected])
    original = deepcopy(RESULT_REF)
    window = ReferenceWindow(reader, original)
    original['job_id'] = 'JchangedOutside'
    window.show()
    try:
        wait(application, lambda: not window._busy)
        assert window.content.payload is None and not window.open_button.isEnabled()
        assert 'private technical error' not in window.message.text()
        assert window._error == 'private technical error'
        QTest.keyClick(window, Qt.Key.Key_F5)
        wait(application, lambda: not window._busy)
        assert reader.calls[0] == reader.calls[1] == RESULT_REF
        assert window.open_button.isEnabled()
        window.content.channel.setCurrentIndex(window.content.channel.findData('stress_yy'))
        QTest.mouseClick(window.content.read, Qt.MouseButton.LeftButton)
        wait(application, lambda: not window._busy)
        requested = {key: value for key, value in RESULT_REF.items() if key != 'response'}
        requested['selection'] = {'responses': ['stress_yy'], 'rows': [0, 256]}
        assert window.reference == requested and not window.open_button.isEnabled()
        window.retry()
        wait(application, lambda: not window._busy)
        assert reader.calls[2] == reader.calls[3] == requested
        assert reader.calls[0]['input_sha256'] == reader.calls[3]['input_sha256']
        assert window.content.title.text() == 'stress_yy [MPa]'
        assert window.content.payload['result']['responses']['stress_yy']['value'] == .234567891234
    finally:
        window.close()


def test_unavailable_payload_does_not_enable_owner_or_show_previous_value(application):
    reader = Reader([PAYLOAD, {'status': 'UNAVAILABLE', 'message': 'internal missing path'}])
    window = ReferenceWindow(reader, RESULT_REF)
    try:
        wait(application, lambda: not window._busy)
        assert window.content.values.rowCount() == 1
        window.retry()
        wait(application, lambda: not window._busy)
        assert window.content.values.rowCount() == 0
        assert window.content.payload is None
        assert not window.open_button.isEnabled() and window.retry_action.isEnabled()
        assert window.value['message'] == 'internal missing path'
        assert 'internal missing path' not in window.content.body.toPlainText()
    finally:
        window.close()


def test_close_during_read_releases_view_and_ignores_late_delivery(application):
    started, release = threading.Event(), threading.Event()
    class Blocked:
        def research_reference(self, reference):
            started.set()
            release.wait(5)
            return deepcopy(PAYLOAD)
    window = ReferenceWindow(Blocked(), RESULT_REF)
    wait(application, started.is_set)
    worker = window._workers[0]
    message = window.message.text()
    window.close()
    assert window._closed and not window._workers and window.retry() is False
    assert window.message.text() == message and window.content.payload is None
    destroyed = []
    window.destroyed.connect(lambda: destroyed.append(True))
    window.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert destroyed
    release.set()
    wait(application, worker.completed.is_set)
    application.processEvents()


def test_saved_read_and_retry_do_not_replace_dirty_owner(application, tmp_path):
    def forbidden(*args, **kwargs):
        raise AssertionError('No calculation is permitted')
    owner = StudyDocuments(tmp_path, 'Spublic', forbidden, None)
    draft = default_draft()
    draft['question'] = '저장 당시 공개 질문'
    saved = owner.open(title='공개 연구', draft=draft)
    saved = owner.command(saved['id'], 'document.save', {},
        session_id=saved['session_id'], expected_generation=saved['generation'])['document']
    reference = {'kind': 'document', 'document_kind': 'study', 'document_id': saved['id'],
        'saved_revision': saved['saved_revision'], 'input_revision': saved['input_revision'],
        'input_sha256': canonical_hash(saved['draft'])}
    changed = deepcopy(saved['draft'])
    changed['question'] = '미저장 수정 질문'
    current = owner.command(saved['id'], 'study.update', {'draft': changed},
        session_id=saved['session_id'], expected_generation=saved['generation'])['document']
    wb = SimpleNamespace(_document_owner=lambda identifier: owner, native_commands=object())
    class ActualReader:
        def research_reference(self, ref):
            return resolve_reference(wb, ref)
    window = ReferenceWindow(ActualReader(), reference)
    try:
        for again in (False, True):
            if again:
                window.retry()
            wait(application, lambda: not window._busy)
            assert window.content.body.toPlainText() == '저장 당시 공개 질문'
            assert window.reference == reference
            after = owner.read(saved['id'])
            assert after['dirty'] and after['draft'] == changed
            assert after['generation'] == current['generation']
            assert after['input_revision'] == current['input_revision']
    finally:
        window.close()


@pytest.mark.parametrize('reference, expected', [
    (RESULT_REF, ('runner', {'job_id': 'Jpublic'})),
    ({'kind': 'document', 'document_kind': 'pde', 'document_id': 'Qpublic',
      'saved_revision': 'Rpublic', 'input_revision': 'Ipublic', 'input_sha256': 'c' * 64},
     ('pde', {'document_id': 'Qpublic'})),
    ({'kind': 'expert_turn', 'discussion_id': 'Xpublic', 'saved_revision': 'Rpublic',
      'turn_id': 'Tpublic', 'turn_sha256': 'd' * 64},
     ('expert', {'document_id': 'Xpublic'})),
])
def test_owner_navigation_failure_keeps_read_body_and_same_target(application, monkeypatch, reference, expected):
    payload = deepcopy(PAYLOAD)
    if reference['kind'] == 'document':
        payload = {'status': 'AVAILABLE', 'kind': 'document',
                   'document': {'title': '공개 PDE 모델', 'draft': {'notes': '공개 입력'}}}
    elif reference['kind'] == 'expert_turn':
        payload = {'status': 'AVAILABLE', 'kind': 'expert_turn',
                   'turn': {'id': 'Tpublic', 'author': 'user', 'text': '공개 기록'}}
    reader = Reader([payload])
    window = ReferenceWindow(reader, reference)
    calls = []
    def launch(client, kind, **arguments):
        calls.append((kind, arguments))
        if len(calls) == 1:
            raise RuntimeError('launch process unavailable')
    monkeypatch.setattr('apps.research.desktop.launch_tool', launch)
    try:
        wait(application, lambda: not window._busy)
        before = deepcopy(window.content.payload)
        assert window.open_owner() is False
        assert window.content.payload == before
        assert window.open_owner() is True
        assert calls == [expected, expected] and window.reference == reference
    finally:
        window.close()
