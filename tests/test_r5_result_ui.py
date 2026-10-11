"""Retained selectors and Evaluation transport controls; no native execution."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from copy import deepcopy
import threading
import time

import pytest
pytest.importorskip('PySide6')
pytest.importorskip('matplotlib')
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QPushButton

from apps.research.pde_window import PDEWindow
from apps.research.evaluation_window import EvaluationWindow
from caelab.pde_document import default_draft as pde_draft
from caelab.evaluation_definition import default_draft as evaluation_draft


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
    raise AssertionError('Controlled Qt reply did not settle')


def document(identifier, draft):
    return {'id': identifier, 'session_id': 'Sowner', 'generation': 0,
            'title': 'Controlled retained result', 'draft': deepcopy(draft),
            'diagnostics': [], 'dirty': False, 'runs': [], 'can_undo': False, 'can_redo': False}


def close(app, window):
    wait(app, lambda: not window._busy)
    window._allow_close = True
    window.close()


class NativeRead:
    def __init__(self, reader=None):
        self.started, self.release = threading.Event(), threading.Event()
        self.calls = []
        self.reader = reader

    def document_result(self, identifier, job, *, selection):
        self.calls.append((identifier, job, deepcopy(selection)))
        self.started.set()
        assert self.release.wait(5)
        selector = selection['responses'][0]
        if self.reader is not None:
            return {'responses': {selector: self.reader(selector)}}
        return {'responses': {selector: {'kind': 'series', 'value': [2., 4.], 'unit': 'm',
            'axes': [{'name': 'time', 'unit': 's', 'values': [.125, .25]}],
            'source': {'selector': selector, 'sample_slice': [0, 2]}}}}


def retained_window(client):
    window = PDEWindow(client, auto_open=False, poll_interval=0)
    window._show_document(document('Qmodel', pde_draft()))
    window._selected_job, window._result_key = 'Jstored', ('Qmodel', 'Jstored')
    return window


def exact_catalog():
    # Shape of the actual OpenRadioss catalog: source.selector, no node_ids.
    return {'radioss-center-z': {'kind': 'series', 'unit': 'm',
                'source': {'selector': 'radioss-center-z'}},
            'radioss-center-vz': {'kind': 'series', 'unit': 'm/s',
                'source': {'selector': 'radioss-center-vz'}}}


def test_exact_catalog_history_reads_without_node_and_preserves_channel(app, monkeypatch):
    from caelab.adapters import native_responses
    # Controlled parsed capture replaces only file/provenance admission. The
    # actual catalog and exact-selector reader retain the native half-step clock.
    raw = {'rows': [{'time_s': .125, 'velocity_time_s': .0625, 'z_m': 10., 'velocity_m_s': 2.},
                    {'time_s': .25, 'velocity_time_s': .1875, 'z_m': 20., 'velocity_m_s': 4.}]}
    monkeypatch.setattr(native_responses, '_explicit_context',
                        lambda outcome, output: (deepcopy(raw), 'a' * 64, {}))
    catalog = native_responses.catalog_native_responses('explicit.openradioss', {}, None)
    client = NativeRead(lambda selector: native_responses.read_native_response(
        'explicit.openradioss', {}, None, selector))
    window = retained_window(client)
    try:
        window._accept_result({'responses': {}, 'native_channels': catalog})
        window.channel.setCurrentIndex(1)
        selector = window.channel.currentData()
        assert window.node.count() == 0 and not window.node.isEnabled()
        assert window.read_curve_button.isEnabled()
        QTest.mouseClick(window.read_curve_button, Qt.MouseButton.LeftButton)
        wait(app, client.started.is_set)
        assert not window.read_curve_button.isEnabled()
        client.release.set()
        wait(app, lambda: not window._busy)
        assert client.calls == [('Qmodel', 'Jstored', {'responses': [selector], 'rows': [0, 2000]})]
        assert window.channel.currentData() == selector
        assert window.result_selector.currentData() == ('response', selector)
        assert list(window.result_axes.lines[0].get_xdata()) == [.0625, .1875]
        assert list(window.result_axes.lines[0].get_ydata()) == [2., 4.]
        assert window.read_curve_button.isEnabled()
    finally:
        client.release.set()
        close(app, window)


@pytest.mark.parametrize('template', [None, 'pde.study0.u@<node_id>'])
def test_node_history_retains_exact_advertised_node_selector(app, template):
    client = NativeRead()
    window = retained_window(client)
    try:
        descriptor = {'node_ids': [7, 31]}
        if template is not None:
            descriptor['selector_template'] = template
        window._accept_result({'responses': {}, 'native_channels': {'pde.study0.u': descriptor}})
        window.node.setCurrentIndex(1)
        window.read_native_curve()
        wait(app, client.started.is_set)
        client.release.set()
        wait(app, lambda: not window._busy)
        assert client.calls[0][2]['responses'] == ['pde.study0.u@31']
        assert window.node.currentData() == 31
        assert window.result_selector.currentData() == ('response', 'pde.study0.u@31')
    finally:
        client.release.set()
        close(app, window)


@pytest.mark.parametrize('switch', ['channel', 'job', 'session', 'document'])
def test_exact_history_late_reply_cannot_merge_into_changed_selection(app, switch):
    client = NativeRead()
    window = retained_window(client)
    try:
        window._accept_result({'responses': {}, 'native_channels': exact_catalog()})
        window.read_native_curve()
        wait(app, client.started.is_set)
        if switch == 'channel':
            window.channel.setCurrentIndex(1)
        elif switch == 'job':
            window._selected_job = 'Jother'
        elif switch == 'session':
            window.document['session_id'] = 'Sother'
        else:
            window._opened(document('Qother', pde_draft()))
        client.release.set()
        wait(app, lambda: not window._busy)
        assert not (window._result or {}).get('responses')
    finally:
        client.release.set()
        close(app, window)


def test_catalog_without_exact_or_node_selector_is_not_guessed(app):
    client = NativeRead()
    window = retained_window(client)
    try:
        window._accept_result({'responses': {}, 'native_channels': {'unknown': {'kind': 'series'}}})
        assert not window.read_curve_button.isEnabled()
        window.read_native_curve()
        assert client.calls == []
    finally:
        close(app, window)


def scalar_definition():
    draft = evaluation_draft()
    draft['stages'] = [{'id': 'Sscalar', 'name': 'Saved scalar Material', 'source': {
        'kind': 'material', 'document_id': 'Mscalar', 'saved_revision': 'Rsave',
        'input_revision': 'Rinput', 'input_sha256': 'a' * 64}}]
    draft['responses'] = [{'id': 'energy', 'stage': 'Sscalar', 'response': 'energy', 'unit': 'Pa'}]
    return document('Escalar', draft)


@pytest.mark.parametrize('failure', ['open', 'inspect'])
def test_scalar_only_evaluation_transport_error_remains_visible(app, failure):
    class Client:
        def document_open(self, **kwargs):
            if failure == 'open':
                raise ValueError('Scalar-only saved definition is unavailable: exact source revision missing')
            return scalar_definition()
        def evaluation_inspect(self, identifier):
            raise ValueError('Scalar-only stage advertises responses, no field transfer port')
    window = EvaluationWindow(Client(), auto_open=False, poll_interval=0)
    try:
        window.open_document(document_id='Escalar')
        wait(app, lambda: not window._busy and 'Scalar-only' in window.message.text())
        window._update_actions()
        assert 'Scalar-only' in window.message.text()
        assert 'Request failed; current edits retained.' in window.message.text()
        if failure == 'inspect':
            assert window.document['id'] == 'Escalar'
            assert window.tables['stages'].rowCount() == 1
            assert window.edited_draft() == scalar_definition()['draft']
        else:
            assert window.document is None
    finally:
        close(app, window)


def test_scalar_only_evaluation_post_open_failure_is_visible_and_retains_scalar_table(app):
    calls = []
    def open_result(document_id, job_id, attempt_id):
        calls.append((document_id, job_id, attempt_id))
        raise ValueError('Selected scalar-only stage has no captured native field to open in Post')
    window = EvaluationWindow(object(), auto_open=False, poll_interval=0, result_open=open_result)
    try:
        window._show_document(scalar_definition())
        window._selected_job, window._selected_attempt = 'Jretained', 'Astored'
        window._put_rows(window.channels, [('name', ''), ('kind', ''), ('unit', ''), ('component', ''),
            ('location', ''), ('value', ''), ('state', '')], [{'name': 'energy', 'kind': 'scalar',
            'unit': 'Pa', 'component': 'scalar', 'location': 'material', 'value': 12., 'state': 'SUCCEEDED'}])
        window._update_actions()
        assert window.result_button.isEnabled()
        QTest.mouseClick(window.result_button, Qt.MouseButton.LeftButton)
        wait(app, lambda: not window._busy and bool(calls))
        assert calls == [('Escalar', 'Jretained', 'Astored')]
        assert 'scalar-only stage has no captured native field' in window.message.text()
        assert window.channels.item(0, 5).text() == '12.0'
        assert window.edited_draft() == scalar_definition()['draft']
        assert window.result_button.isEnabled()
    finally:
        close(app, window)


def test_evaluation_pending_apply_blocks_structural_clicks_and_keeps_submitted_draft(app):
    class Client:
        def __init__(self):
            self.started, self.release = threading.Event(), threading.Event()
            self.calls = []
        def document_command(self, identifier, operation, arguments, **options):
            self.calls.append((identifier, operation, deepcopy(arguments), deepcopy(options)))
            self.started.set()
            assert self.release.wait(5)
            owner = scalar_definition()
            owner.update(generation=1, draft=deepcopy(arguments['draft']))
            return {'document': owner}
        def evaluation_inspect(self, identifier):
            return {'stages': [], 'diagnostics': []}
    client = Client()
    window = EvaluationWindow(client, auto_open=False, poll_interval=0)
    try:
        window._show_document(scalar_definition())
        window.tables['stages'].item(0, 1).setText('Edited scalar stage')
        window.tabs.setCurrentIndex(3)
        window.tables['responses'].selectRow(0)
        submitted = window.edited_draft()
        window.show()
        window.apply_inputs()
        wait(app, client.started.is_set)
        assert not window.tabs.isEnabled() and not window.stage_editor.isEnabled()
        buttons = [button for button in window.findChildren(QPushButton)
                   if button.text() in ('Remove stage', 'Remove selected rows', 'Clear prepared reuse')]
        assert buttons and all(not button.isEnabled() for button in buttons)
        for button in buttons:
            QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        assert window.edited_draft() == submitted
        client.release.set()
        wait(app, lambda: not window._busy and window.document['generation'] == 1)
        assert len(client.calls) == 1 and client.calls[0][1] == 'evaluation.update'
        assert client.calls[0][2]['draft'] == submitted
        assert window.edited_draft() == submitted
        assert window.tabs.isEnabled() and window.stage_editor.isEnabled()
    finally:
        client.release.set()
        close(app, window)
