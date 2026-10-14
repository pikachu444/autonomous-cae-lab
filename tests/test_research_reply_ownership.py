"""Actual Qt delayed transport replies retain exact source and edit ownership.

No physics or provider is executed. Latency/error boundaries are labelled client
fixtures and the actual QWidget/QThreadPool callbacks are exercised.
"""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from copy import deepcopy
import threading
import time

import pytest
pytest.importorskip('PySide6')
pytest.importorskip('matplotlib')
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from apps.research.pde_window import PDEWindow
from apps.research.expert_window import ExpertWindow
from apps.research.request_plan_window import RequestPlanWindow, DATA
from caelab.pde_document import default_draft as pde_draft
from caelab.discussion_document import default_draft as expert_draft
from caelab.numerical_document import request_draft


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
    raise AssertionError('Delayed Qt ownership callback did not settle')


def document(identifier, draft):
    return {'id': identifier, 'session_id': 'Sowner', 'generation': 0, 'title': 'Software fixture',
            'draft': draft, 'diagnostics': [], 'dirty': False, 'runs': [], 'turns': [],
            'discussion': {'rounds': [], 'paused': False}, 'can_undo': False, 'can_redo': False}


class DelayedCommand:
    def __init__(self, source):
        self.source = deepcopy(source)
        self.started, self.release = threading.Event(), threading.Event()
        self.calls = []
    def document_command(self, identifier, operation, arguments, **options):
        self.calls.append((operation, deepcopy(arguments)))
        self.started.set()
        assert self.release.wait(5)
        if 'draft' in arguments:
            self.source['draft'] = deepcopy(arguments['draft'])
        self.source['generation'] += 1
        return {'document': deepcopy(self.source)}


def close(app, window):
    wait(app, lambda: not window._busy)
    window._allow_close = True
    window.close()


def test_pde_late_edit_retained_with_new_owner_generation_and_no_save_continuation(app):
    source = document('Pmodel', pde_draft())
    client = DelayedCommand(source)
    window = PDEWindow(client, auto_open=False, poll_interval=0)
    try:
        window._show_document(source)
        window.tree.setCurrentItem(window._nodes[('settings', 'problem', 'weak_form')])
        field = window.fields[('settings', 'problem', 'weak_form', 'diffusion')][0]
        field.setText('2')
        window._edited()
        window.save_document()
        wait(app, client.started.is_set)
        field.setText('9')
        window._edited()
        client.release.set()
        wait(app, lambda: not window._busy)
        assert window.document['generation'] == 1
        assert window.document['draft']['settings']['problem']['weak_form']['diffusion'] == 2
        assert window.edited_draft()['settings']['problem']['weak_form']['diffusion'] == 9
        assert window.local_dirty and '편집한 내용은 아직 적용 전' in window.message.text()
        assert [call[0] for call in client.calls] == ['pde.update']
    finally:
        client.release.set()
        close(app, window)


@pytest.mark.parametrize('switch', ['job', 'document', 'selection'])
def test_pde_native_reply_cannot_merge_into_new_selected_owner(app, switch):
    class NativeRead:
        started, release = threading.Event(), threading.Event()
        def document_result(self, *args, **kwargs):
            self.started.set()
            assert self.release.wait(5)
            return {'responses': {'u@1': {'kind': 'series', 'value': [1, 2], 'unit': 'm',
                'axes': [{'name': 'time', 'unit': 's', 'values': [0, 1]}]}}}
    source = document('Pmodel', pde_draft())
    client = NativeRead()
    window = PDEWindow(client, auto_open=False, poll_interval=0)
    try:
        window._show_document(source)
        window._selected_job, window._result_key = 'Jone', ('Pmodel', 'Jone')
        window._accept_result({'responses': {}, 'native_channels': {'u': {'node_ids': [1, 2]}}})
        window.read_native_curve()
        wait(app, client.started.is_set)
        if switch == 'job':
            window._selected_job = 'Jtwo'
            window._result = None
            window._result_key = None
        elif switch == 'document':
            other = document('Pother', pde_draft())
            window._opened(other)
        else:
            window.node.setCurrentIndex(window.node.findData(2))
        client.release.set()
        wait(app, lambda: not window._busy)
        assert not window._result or 'u@1' not in window._result.get('responses', {})
    finally:
        client.release.set()
        close(app, window)


def test_failed_expert_ask_never_authorizes_old_ready_round(app):
    source = document('Xdiscussion', expert_draft())
    source['draft']['composer']['text'] = 'Existing question'
    source['draft']['participants'] = ['material', 'skeptic']
    source['discussion']['rounds'] = [{'id': 'Bold', 'status': 'READY', 'roles': ['material', 'skeptic'], 'next_index': 1}]
    class FailedAsk:
        calls = []
        def document_command(self, identifier, operation, arguments, **options):
            self.calls.append(operation)
            if operation == 'expert.ask':
                raise ValueError('CONTROLLED Ask failure: old round already active')
            raise AssertionError('Failed Ask must not advance any prior round')
        def document_read(self, identifier):
            return deepcopy(source)
    window = ExpertWindow(FailedAsk(), auto_open=False, poll_interval=0)
    try:
        window._show_document(source)
        window.ask()
        wait(app, lambda: not window._busy and bool(window.client.calls))
        for _ in range(20):
            app.processEvents()
            time.sleep(.005)
        wait(app, lambda: not window._busy)
        assert window.client.calls == ['expert.ask']
        assert not window._round_started_here and window._auto_round_id is None
    finally:
        close(app, window)


def test_expert_late_composer_edit_survives_applied_question_and_blocks_save(app):
    source = document('Xdiscussion', expert_draft())
    client = DelayedCommand(source)
    window = ExpertWindow(client, auto_open=False, poll_interval=0)
    try:
        window._show_document(source)
        window.question.setPlainText('Submitted question')
        window.save_document()
        wait(app, client.started.is_set)
        window.question.setPlainText('New counterargument while waiting')
        client.release.set()
        wait(app, lambda: not window._busy)
        assert window.document['generation'] == 1
        assert window.document['draft']['composer']['text'] == 'Submitted question'
        assert window.question.toPlainText() == 'New counterargument while waiting'
        assert window.local_dirty
        assert [call[0] for call in client.calls] == ['expert.update']
    finally:
        client.release.set()
        close(app, window)


def test_request_backend_control_and_tree_share_one_source_on_removal(app):
    source = document('Nrequest', request_draft({'purpose': 'Software input editor fixture', 'operation': 'evaluate',
        'inputs': {'backend': 'material.felupe', 'settings': {}}, 'budget': {'evaluations': 1}}))
    window = RequestPlanWindow(None, auto_open=False, poll_interval=0)
    try:
        window._show_document(source)
        window.backend.selectAll()
        QTest.keyClicks(window.backend, 'registered.custom')
        assert window.edited_draft()['request']['inputs']['backend'] == 'registered.custom'
        root = window.inputs.topLevelItem(0)
        backend = next(root.child(index) for index in range(root.childCount()) if root.child(index).data(0, DATA)['path'] == ('backend',))
        backend.setText(1, 'registered.tree_edit')
        assert window.backend.text() == 'registered.tree_edit'
        window.inputs.setCurrentItem(backend)
        window.remove_input()
        assert 'backend' not in window.edited_draft()['request']['inputs']
        assert window.backend.text() == ''
        window.purpose.setText('Another purpose')
        assert 'backend' not in window.edited_draft()['request']['inputs']
    finally:
        close(app, window)
