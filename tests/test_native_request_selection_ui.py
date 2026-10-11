"""Actual Qt editing with retained-read transport doubles; no solver is run."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from copy import deepcopy
import time

import pytest
pytest.importorskip('PySide6')
from PySide6.QtWidgets import QApplication, QInputDialog
from apps.research.request_plan_window import RequestPlanWindow
from caelab.numerical_document import request_draft
from caelab.storage import canonical_hash
from caelab.assist.experts import validate_plan_request


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


def wait(app, predicate):
    until = time.monotonic() + 5
    while time.monotonic() < until:
        app.processEvents()
        if predicate(): return
        time.sleep(.003)
    raise AssertionError('Retained response selection did not settle')


class Client:
    def __init__(self):
        self.calls = []
        self.model = {'backend': 'material.mfront', 'settings': {'material': {'E': 10}, 'history': [0, 1]}}
        self.source = {'kind': 'material', 'document_id': 'Msource', 'saved_revision': 'Rsource',
                       'input_revision': 'Imodel', 'input_sha256': canonical_hash(self.model)}
        self.response = {'kind': 'series', 'value': [1.], 'unit': 'MPa', 'component': 'XX',
            'location': 'material_point', 'measure': 'Cauchy', 'coordinate_frame': 'specimen', 'reduction': 'none',
            'axes': [{'name': 'time', 'unit': 's', 'semantics': 'EXPLICIT_TEST_CLOCK', 'values': [0.]}]}

    def documents(self):
        return {'documents': [{'id': 'Msource', 'title': 'Actual retained Material', 'kind': 'material'}]}

    def document_read(self, identifier):
        self.calls.append(('read', identifier))
        return {'id': identifier, 'kind': 'material', 'draft': deepcopy(self.model), 'runs': [{
            'job_id': 'Jsource', 'input_revision': 'Imodel', 'backend': self.model['backend'],
            'draft': deepcopy(self.model), 'retention_complete': True, 'retained_result': {'revision': 'Rsource'}}]}

    def document_result_reference(self, document, job):
        return {'document_id': document, 'job_id': job, 'input_revision': 'Imodel',
                'input_sha256': self.source['input_sha256'], 'result_sha256': 'b' * 64}

    def document_result_metadata(self, document, job):
        return {'responses': [], 'native_channels': {'stress': {**deepcopy(self.response),
            'value': None, 'source': {'selector': 'stress'}}}}

    def document_result(self, document, job, *, selection):
        self.calls.append(('result', document, job, deepcopy(selection)))
        return {'execution_status': 'SUCCEEDED', 'responses': {'stress': deepcopy(self.response)}}


@pytest.fixture
def window(app):
    client = Client()
    widget = RequestPlanWindow(client, auto_open=False, poll_interval=0)
    draft = request_draft({'purpose': 'Compare original constitutive assumptions', 'operation': 'evaluate',
                          'inputs': deepcopy(client.model), 'budget': {'evaluations': 2}}, source=client.source)
    widget._opened({'id': 'Nplan', 'kind': 'numerical', 'title': 'Native law Plan', 'session_id': 'Sowner',
        'generation': 0, 'input_revision': 'Iplan', 'draft': draft, 'runs': [], 'diagnostics': [], 'dirty': False,
        'can_undo': False, 'can_redo': False})
    yield widget
    wait(app, lambda: not widget._busy)
    widget._allow_close = True
    widget.close()


def switch(widget, name):
    widget.operation.setCurrentIndex(widget.operation.findData(name))


def test_switch_methods_preserves_source_settings_and_separate_edits(window):
    original = deepcopy(window.client.model)
    switch(window, 'doe')
    window._edit_structure(lambda value: value.update(count=2, variables=[{'id': 'E', 'unit': 'MPa', 'value': 10., 'lower': 1., 'upper': 20.}]))
    assert window.edited_draft()['request']['inputs']['settings'] == original['settings']
    switch(window, 'fit')
    trial = window.edited_draft()['request']['inputs']['experiments'][0]
    assert trial['settings'] == original['settings'] and trial['response'] == ''
    assert 'observations' not in trial and 'observation_ref' not in trial
    switch(window, 'analyze')
    switch(window, 'optimize')
    assert window.edited_draft()['request']['inputs']['settings'] == original['settings']
    switch(window, 'doe')
    assert window.edited_draft()['request']['inputs']['count'] == 2
    assert window.edited_draft()['source'] == window.client.source


def test_actual_retained_model_selector_and_pinned_holdout(app, window, monkeypatch):
    monkeypatch.setattr(QInputDialog, 'getItem', lambda parent, title, label, items, **kw: (items[0], True))
    switch(window, 'doe')
    window._edit_structure(lambda value: value.update(count=2, variables=[{'id': 'E', 'unit': 'MPa', 'value': 10., 'lower': 1., 'upper': 20.}]))
    window.choose_model_response()
    wait(app, lambda: not window._busy and window.edited_draft()['request']['inputs'].get('responses') == ['stress'])
    assert window.client.calls[-1] == ('result', 'Msource', 'Jsource', {'responses': ['stress'], 'rows': [0, 1]})
    validate_plan_request(window.edited_draft()['request'])
    switch(window, 'fit')
    window.choose_model_response()
    wait(app, lambda: not window._busy and window.edited_draft()['request']['inputs']['experiments'][0]['response'] == 'stress')
    window.choose_fit_observation()
    wait(app, lambda: not window._busy and 'observation_ref' in window.edited_draft()['request']['inputs']['experiments'][0])
    def select_holdout(parent, title, label, items, **kw):
        return (items[-1] if title == 'Attach actual observation' else items[0]), True
    monkeypatch.setattr(QInputDialog, 'getItem', select_holdout)
    window.choose_fit_observation()
    wait(app, lambda: not window._busy and len(window.edited_draft()['request']['inputs']['experiments']) == 2)
    trials = window.edited_draft()['request']['inputs']['experiments']
    assert [row['role'] for row in trials] == ['fit', 'holdout']
    assert trials[1]['settings'] == trials[0]['settings'] == window.client.model['settings']
    assert trials[1]['id'] != trials[0]['id']
    assert trials[1]['observation_ref']['result']['result_sha256'] == 'b' * 64
    validate_plan_request(window.edited_draft()['request'])


def test_changed_input_while_dialog_open_does_not_attach_late_response(app, window, monkeypatch):
    switch(window, 'doe')
    def select(parent, title, label, items, **kw):
        if title == 'Select actual response':
            window._edit_structure(lambda value: value.update(count=7))
        return items[0], True
    monkeypatch.setattr(QInputDialog, 'getItem', select)
    window.choose_model_response()
    wait(app, lambda: not window._busy and window.edited_draft()['request']['inputs'].get('count') == 7)
    assert 'responses' not in window.edited_draft()['request']['inputs']
    assert not any(call[0] == 'result' for call in window.client.calls)


def test_native_objective_uses_exact_selected_location_and_reduction(app, window, monkeypatch):
    switch(window, 'optimize')
    window.client.response.update(location='native BODY 12 point 4', measure='Cauchy')
    monkeypatch.setattr(QInputDialog, 'getItem', lambda parent, title, label, items, **kw: (items[0], True))
    window.choose_model_response()
    wait(app, lambda: not window._busy and 'objective' in window.edited_draft()['request']['inputs'])
    objective = window.edited_draft()['request']['inputs']['objective']
    assert objective['location'] == 'native BODY 12 point 4'
    assert objective['reduction'] == 'max' and objective['direction'] == 'minimize'
    assert objective['id'].startswith('metric_') and objective['coordinate_frame'] == 'specimen'
