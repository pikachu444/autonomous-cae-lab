"""Actual Qt/HTTP Data editing plus explicit comparison/follow-up callbacks."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from copy import deepcopy
import threading
import time

import pytest
pytest.importorskip('PySide6')
pytest.importorskip('matplotlib')
from PySide6.QtCore import QThreadPool
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
    raise AssertionError('Multichannel Data action did not settle')


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


def populated_draft(data_id):
    draft = default_draft()
    draft['data_id'] = data_id
    draft['mapping']['skip_header'] = 1
    spec = draft['mapping']['columns']['response']
    spec.update(column=1, unit='MPa', component='xx', location='point', measure='Cauchy', frame='lab')
    spec['axis'].update(column=0, name='time', unit='s')
    other = deepcopy(spec)
    other.update(column=2, component='yy')
    draft['mapping']['columns']['lateral'] = other
    return draft


def test_actual_http_mask_metadata_channel_edit_save_import_undo(app, tmp_path):
    source_root = tmp_path / 'source'
    source_root.mkdir()
    source = source_root / '다중 시험.csv'
    raw = b't,a,b\n0,10,20\n1,nan,21\n2,12,22\n3,13,23\n'
    source.write_bytes(raw)
    server = LabHTTPServer(LabService(tmp_path / 'workspace'), 0,
        workbench_config={'input_roots': {'test': str(source_root)}})
    thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .02}, daemon=True)
    thread.start()
    client = Client('http://127.0.0.1:' + str(server.server_port))
    window = DataWindow(client, auto_open=False, poll_interval=0)
    try:
        receipt = client.register_local_input('test', source.name)
        document = client.document_open(kind='data', draft=populated_draft(receipt['id']))
        window._show_document(document)
        assert window.channel_selector.count() == 2
        window.mapping.item(1, 8).setText('2')
        window.row_fields['exclude_rows'].setText('2')
        window.row_fields['reasons'].setText('2: missing sensor sample')
        window.row_fields['quality_rows'].setText('3')
        window.row_fields['display_hidden_rows'].setText('4')
        window.test_fields['test_id'].setText('coupon 7')
        window.test_fields['temperature'].setText('23 °C')
        window.channel_selector.setCurrentText('lateral')
        window.mapping.item(1, 9).setText('1')
        window.channel_selector.setCurrentText('response')
        assert float(window.mapping.item(1, 8).text()) == 2
        edited = window.edited_draft()
        assert edited['mapping']['columns']['lateral']['offset'] == 1
        assert edited['test_metadata']['temperature'] == '23 °C'
        window.apply_inputs()
        wait(app, lambda: not window._busy and not window.local_dirty)
        window.import_table()
        wait(app, lambda: bool(window.document['runs']) and not window._busy)
        job_id = window.document['runs'][0]['job_id']
        wait(app, lambda: client.status(job_id)['state'] in {'SUCCEEDED', 'FAILED'})
        imported = client.document_result(document['id'], job_id)
        assert imported['execution_status'] == 'SUCCEEDED'
        assert imported['responses']['response']['value'] == [20, 24, 26]
        assert imported['responses']['response']['raw_samples']['value'] == [10, 'nan', 12, 13]
        assert imported['responses']['lateral']['value'] == [21, 22, 23, 24]
        wait(app, lambda: not window._busy)
        window.save_document()
        wait(app, lambda: not window._busy and bool(window.document.get('saved_revision')))
        window.channel_selector.setCurrentText('lateral')
        window.row_fields['include_ranges'].setText('unfinished interval')
        window._edited()
        window.save_document()
        wait(app, lambda: not window._busy and not window.local_dirty)
        assert window.document['diagnostics'] and not window.import_button.isEnabled()
        assert window.document['draft']['mapping']['columns']['lateral']['row_selection']['include_ranges'] == 'unfinished interval'
        assert client.document_result(document['id'], job_id)['responses']['response']['raw_samples']['value'][1] == 'nan'
        window.command('document.undo')
        wait(app, lambda: not window._busy and not window.document['diagnostics'])
        assert window.document['draft'] == edited
        assert source.read_bytes() == raw
    finally:
        wait(app, lambda: not window._busy)
        window._allow_close = True
        window.close()
        try:
            # Keep the HTTP service alive until queued GUI continuations are
            # gated by close and the existing QRunnables have returned.
            app.processEvents()
            assert QThreadPool.globalInstance().waitForDone(5000), 'Data HTTP reads did not drain'
            app.processEvents()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


def test_channel_add_clone_remove_and_explicit_followups(app, monkeypatch):
    class ComparisonClient:
        calls = []
        def document_compare(self, source, prediction):
            self.calls.append((source, prediction))
            return {'rmse': .25, 'count': 3, 'unit': 'MPa'}
        def status(self, identifier):
            return {'state': 'SUCCEEDED', 'result_refs': []}
        def document_read(self, identifier):
            return deepcopy(document)
        def documents(self):
            return {'documents': [{'id': 'Mmodel', 'kind': 'material', 'title': 'Explicit model',
                'draft': {'backend':'material.felupe'}}]}
        def document_result(self, identifier, job_id, *, selection=None):
            assert (identifier,job_id)==('Tdata','Jactual')
            return {'execution_status':'SUCCEEDED','responses': {'response': {
                'kind':'series','unit':'MPa','component':'xx','measure':'infinitesimal_Cauchy',
                'axes':[{'name':'time','unit':'s'}]}}}
        def data_followup(self, source, kind, **kwargs):
            return {'executed': False, 'document': {'id': 'Followup-' + kind, 'title': kind}}
    client = ComparisonClient()
    window = DataWindow(client, auto_open=False, poll_interval=0)
    document = {'id': 'Tdata', 'session_id': 'Sowner', 'generation': 0, 'title': 'data',
        'draft': populated_draft('Dsource'), 'diagnostics': [], 'dirty': False,
        'runs': [{'job_id': 'Jactual', 'input_generation': 0, 'input_revision': 'Iactual', 'input_sha256': 'a' * 64}]}
    try:
        monkeypatch.setattr('apps.research.desktop.launch_tool', lambda *args, **kwargs: None)
        monkeypatch.setattr(QInputDialog, 'getItem',
            lambda parent,title,label,choices,*args,**kwargs: (choices[-1] if title=='피팅할 재료' else choices[0],True))
        window._show_document(document)
        monkeypatch.setattr(QInputDialog, 'getText', lambda *args, **kwargs: ('copied', True))
        window.edit_channels('clone')
        assert window.channel_selector.count() == 3
        assert window.edited_draft()['mapping']['columns']['copied'] == document['draft']['mapping']['columns']['response']
        window.edit_channels('remove')
        assert window.channel_selector.count() == 2
        window._show_document(document)
        window.result_channel.addItem('response')
        wait(app, lambda: not window._busy)
        source = window.selected_source()
        assert source['input_revision'] == 'Iactual'
        prediction = {'document_id': 'Pmodel', 'job_id': 'Jprediction', 'response': 'stress_xx'}
        window.compare_prediction(prediction)
        wait(app, lambda: window._comparison is not None and not window._busy)
        assert client.calls == [(source, prediction)]
        plans, experts = [], []
        window.numerical_requested.connect(plans.append)
        window.expert_requested.connect(experts.append)
        window.request_followup('numerical')
        wait(app, lambda: bool(plans) and not window._busy)
        window.request_followup('expert')
        wait(app, lambda: bool(experts) and not window._busy)
        assert plans[0]['source'] == experts[0]['source'] == source
        assert plans[0]['execute'] is False and experts[0]['comparison']['prediction_source'] == prediction
    finally:
        wait(app, lambda: not window._busy)
        window._allow_close = True
        window.close()


@pytest.mark.parametrize('field,value', [('test_metadata', {'temperature': 25}), ('row_selection', 'unfinished mask')])
def test_malformed_metadata_mask_shape_keeps_raw_invalid_draft(app, field, value):
    draft = populated_draft('Dsource')
    if field == 'row_selection':
        draft['mapping']['columns']['response'][field] = value
    else:
        draft[field] = value
    document = {'id': 'Tdata', 'session_id': 'Sowner', 'generation': 0, 'title': 'Malformed',
        'draft': draft, 'diagnostics': [], 'dirty': False, 'runs': []}
    window = DataWindow(None, auto_open=False, poll_interval=0)
    try:
        window._show_document(document)
        assert window._view_error and window.edited_draft() == draft
        assert window.save_action.isEnabled() and not window.import_button.isEnabled()
    finally:
        window._allow_close = True
        window.close()
