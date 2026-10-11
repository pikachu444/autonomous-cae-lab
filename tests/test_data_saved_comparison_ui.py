"""Actual CSV/HTTP comparison retention, with Qt ownership and chooser races."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from copy import deepcopy
import threading
import time

import pytest
pytest.importorskip('PySide6')
pytest.importorskip('matplotlib')
from PySide6.QtWidgets import QApplication, QInputDialog

from apps.lab.server import LabHTTPServer
from apps.lab.service import LabService
from apps.research.data_window import DataWindow
from caelab.data_document import default_draft
from caelab.workbench_client import Client


def wait(app, condition):
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        app.processEvents()
        if condition():
            return
        time.sleep(.005)
    raise AssertionError('Retained comparison UI action did not settle')


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


def draft_for(identifier):
    draft = default_draft()
    draft['data_id'] = identifier
    draft['mapping']['skip_header'] = 1
    response = draft['mapping']['columns']['response']
    response.update(unit='MPa', component='xx', location='material_point', measure='infinitesimal_Cauchy', frame='material_cartesian')
    response['axis'].update(name='time', unit='s')
    response['row_selection'] = {'exclude_rows': [2], 'reasons': {'2': 'sensor unavailable'}}
    lateral = deepcopy(response)
    lateral.update(column=2, component='yy')
    draft['mapping']['columns']['lateral'] = lateral
    return draft


def imported(client, app, root, name, values):
    (root / name).write_text(values, encoding='utf-8')
    receipt = client.register_local_input('test', name)
    document = client.document_open(kind='data', draft=draft_for(receipt['id']))
    result = client.document_command(document['id'], 'data.import', {}, session_id=document['session_id'],
        expected_generation=document['generation'])
    job_id = result['job']['id']
    wait(app, lambda: client.status(job_id)['state'] in {'SUCCEEDED', 'FAILED'})
    assert client.status(job_id)['state'] == 'SUCCEEDED'
    return client.document_read(document['id']), job_id


def close_window(window, app):
    wait(app, lambda: not window._busy)
    window._allow_close = True
    window.close()


def test_actual_http_saved_comparison_reopen_bounded_selection_and_unexecuted_followup(app, tmp_path, monkeypatch):
    root = tmp_path / 'source'
    root.mkdir()
    workspace = tmp_path / 'workspace'
    def server():
        owner = LabHTTPServer(LabService(workspace), 0, workbench_config={'input_roots': {'test': str(root)}})
        thread = threading.Thread(target=owner.serve_forever, kwargs={'poll_interval': .01}, daemon=True)
        thread.start()
        return owner, thread, Client('http://127.0.0.1:' + str(owner.server_port))
    owner, thread, client = server()
    windows = []
    launches = []
    monkeypatch.setattr('apps.research.desktop.launch_tool', lambda client, kind, **kwargs: launches.append((kind, kwargs['document_id'])))
    try:
        observation, job = imported(client, app, root, '새 측정.csv', 't,x,y\n0,3,6\n1,nan,nan\n2,5,8\n3,7,10\n')
        # An actual second CSV supplies a retained prediction without running physics.
        prediction, predicted_job = imported(client, app, root, '보존 예측.csv', 't,x,y\n0,3.25,6.5\n1,nan,nan\n2,5.25,8.5\n3,7.25,10.5\n')
        window = DataWindow(client, auto_open=False, poll_interval=0)
        windows.append(window)
        window.open_document(document_id=observation['id'])
        wait(app, lambda: window.result_channel.count() == 2 and not window._busy)
        window.result_channel.setCurrentText('response')
        wait(app, lambda: window.result_channel.currentText() == 'response' and not window._busy)
        window.compare_prediction({'document_id': prediction['id'], 'job_id': predicted_job, 'response': 'response'})
        wait(app, lambda: window._comparison is not None and not window._busy)
        comparison_id = window._comparison_id
        assert comparison_id and window._comparison['result']['comparison']['rmse'] == pytest.approx(.25)
        wait(app, lambda: not window._busy)
        window.save_document()
        wait(app, lambda: not window._busy and bool(window.document.get('saved_revision')))
        close_window(window, app)
        windows.remove(window)
        owner.shutdown(); owner.server_close(); thread.join(timeout=2)
        owner, thread, client = server()
        reopened = client.document_open(kind='data', document_id=observation['id'])
        window = DataWindow(client, auto_open=False, poll_interval=0)
        windows.append(window)
        window.open_document(document_id=reopened['id'])
        wait(app, lambda: window.result_channel.count() == 2 and not window._busy)
        window.result_channel.setCurrentText('response')
        wait(app, lambda: window.result_channel.currentText() == 'response' and not window._busy)
        assert window.comparison_selector.count() == 2
        window.row_start.setValue(1)
        window.row_count.setValue(1)
        window.comparison_selector.setCurrentIndex(1)
        wait(app, lambda: window._comparison is not None and not window._busy)
        assert window._comparison_id == comparison_id
        assert window._comparison['result']['page'] == {'start': 1, 'count': 1, 'total': 3}
        assert window._comparison['result']['comparison']['prediction'] == [5.25]
        window.refresh_document()
        wait(app, lambda: not window._busy)
        assert window.comparison_selector.currentData() == comparison_id
        window.result_channel.setCurrentText('lateral')
        wait(app, lambda: not window._busy)
        assert window._comparison is None and window.comparison_selector.count() == 1
        window.result_channel.setCurrentText('response')
        wait(app, lambda: not window._busy and window.comparison_selector.count() == 2)
        window.comparison_selector.setCurrentIndex(1)
        wait(app, lambda: window._comparison is not None and not window._busy)
        before_jobs = len(owner.workbench.manager.list())
        evidence = []
        window.expert_requested.connect(evidence.append)
        window.request_followup('expert')
        wait(app, lambda: evidence and launches and not window._busy)
        assert evidence[0]['source']['job_id'] == job
        assert evidence[0]['comparison']['result']['id'] == comparison_id
        assert evidence[0]['execute'] is False
        target = client.document_read(evidence[0]['document_id'])
        assert target['kind'] == 'expert' and target['runs'] == []
        assert len(owner.workbench.manager.list()) == before_jobs
        model = client.document_open(kind='material', title='Explicit identification model')
        monkeypatch.setattr(QInputDialog, 'getItem', lambda *args, **kwargs: (
            next(label for label in args[3] if model['id'] in label), True))
        plans = []
        window.numerical_requested.connect(plans.append)
        window.request_followup('numerical')
        wait(app, lambda: plans and len(launches) == 2 and not window._busy)
        plan = client.document_read(plans[0]['document_id'])
        assert plan['kind'] == 'numerical' and plan['runs'] == []
        assert plans[0]['source']['job_id'] == job and plans[0]['execute'] is False
        assert plan['draft']['experiments'][0]['source'] == window.selected_source()
        assert len(owner.workbench.manager.list()) == before_jobs
    finally:
        for window in windows:
            close_window(window, app)
        owner.shutdown(); owner.server_close(); thread.join(timeout=2)


def synthetic_document():
    return {'id': 'Tdata', 'session_id': 'Sowner', 'generation': 0, 'title': 'Data', 'draft': draft_for('Dsource'),
        'runs': [{'job_id': 'Jactual', 'input_generation': 0, 'input_revision': 'Iactual', 'input_sha256': 'a' * 64}],
        'diagnostics': [], 'comparisons': []}


def test_late_compare_reply_cannot_replace_other_channel_or_owner(app):
    started, released = threading.Event(), threading.Event()
    class DelayedClient:
        def document_compare(self, source, prediction):
            started.set()
            assert released.wait(8)
            return {'id': 'Kold', 'binding': {'source': source, 'prediction_source': prediction},
                'comparison': {'rmse': .25, 'count': 3}, 'page': {'start': 0, 'count': 3, 'total': 3}}
        def status(self, job):
            return {'state': 'SUCCEEDED', 'result_refs': []}
    window = DataWindow(DelayedClient(), auto_open=False, poll_interval=0)
    try:
        window._show_document(synthetic_document())
        window.result_channel.addItems(['response', 'lateral'])
        wait(app, lambda: not window._busy)
        window.compare_prediction({'document_id': 'Pmodel', 'job_id': 'Jprediction', 'response': 'stress'})
        wait(app, started.is_set)
        window.result_channel.setCurrentText('lateral')
        changed = synthetic_document()
        changed.update(id='Tother', session_id='Sother')
        window._show_document(changed)
        released.set()
        wait(app, lambda: not window._busy)
        assert window.document['id'] == 'Tother'
        assert window._comparison is None and window._comparison_id is None
    finally:
        released.set()
        close_window(window, app)


def test_modal_prediction_chain_keeps_callback_lock_and_executes_once(app, monkeypatch):
    calls = []
    document = synthetic_document()
    class ChooserClient:
        def documents(self):
            return {'documents': [{'id': 'Pmodel', 'title': 'Model', 'kind': 'material'}]}
        def document_read(self, identifier):
            calls.append(('read', identifier))
            return {'runs': [{'job_id': 'Jprediction', 'input_generation': 0}]} if identifier == 'Pmodel' else deepcopy(document)
        def document_result(self, identifier, job, **kwargs):
            calls.append(('metadata', identifier, job))
            return {'responses': {'stress': {}}}
        def document_compare(self, source, prediction):
            calls.append(('compare', source['response'], prediction['response']))
            return {'rmse': .25, 'count': 3}
        def status(self, job):
            return {'state': 'SUCCEEDED', 'result_refs': []}
    window = DataWindow(ChooserClient(), auto_open=False, poll_interval=0)
    def choose(*args, **kwargs):
        assert window._busy and window._accepting
        window.refresh_document()  # A timer event in the modal loop cannot take the lock.
        app.processEvents()
        return args[3][0], True
    monkeypatch.setattr(QInputDialog, 'getItem', choose)
    try:
        window._show_document(document)
        window.result_channel.addItem('response')
        wait(app, lambda: not window._busy)
        window.choose_prediction()
        wait(app, lambda: window._comparison is not None and not window._busy)
        assert calls.count(('compare', 'response', 'stress')) == 1
        assert calls[:2] == [('read', 'Pmodel'), ('metadata', 'Pmodel', 'Jprediction')]
    finally:
        close_window(window, app)
