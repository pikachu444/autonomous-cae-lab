"""Actual HTTP/CSV/Qt checks for channel identity and original-row display masks."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from copy import deepcopy
import math
import threading
import time

import pytest
pytest.importorskip('PySide6')
pytest.importorskip('matplotlib')
from PySide6.QtWidgets import QApplication

from apps.lab.server import LabHTTPServer
from apps.lab.service import LabService
from apps.research.data_window import DataWindow
from caelab.data_document import default_draft
from caelab.workbench_client import Client


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


def wait(app, predicate):
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return
        time.sleep(.005)
    raise AssertionError('Data identity/mask callback did not settle')


def draft(data_id):
    value = default_draft()
    value['data_id'] = data_id
    value['mapping']['skip_header'] = 1
    response = value['mapping']['columns']['response']
    response.update(column=1, unit='MPa', component='xx', location='point', measure='Cauchy', frame='lab')
    response['axis'].update(column=0, name='time', unit='s')
    lateral = deepcopy(response)
    lateral.update(column=2, component='yy')
    value['mapping']['columns']['lateral'] = lateral
    return value


def test_actual_http_rename_switch_save_and_filtered_display_page(app, tmp_path):
    root = tmp_path / 'input'
    root.mkdir()
    source = root / '시험.csv'
    original = b't,axial,lateral\n0,10,100\n1,20,200\n2,30,300\n3,40,400\n4,50,500\n'
    source.write_bytes(original)
    server = LabHTTPServer(LabService(tmp_path / 'workspace'), 0, workbench_config={'input_roots': {'test': str(root)}})
    thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .02}, daemon=True)
    thread.start()
    client = Client('http://127.0.0.1:' + str(server.server_port))
    window = DataWindow(client, auto_open=False, poll_interval=0)
    try:
        registered = client.register_local_input('test', source.name)
        document = client.document_open(kind='data', draft=draft(registered['id']))
        window._show_document(document)
        window.mapping.item(1, 1).setText('axial')
        assert window._channel_name == 'axial'
        assert [window.channel_selector.itemText(index) for index in range(window.channel_selector.count())] == ['axial', 'lateral']
        window.channel_selector.setCurrentText('lateral')
        window.mapping.item(1, 9).setText('1')
        window.channel_selector.setCurrentText('axial')
        assert window.mapping.item(1, 1).text() == 'axial' and window.mapping.item(1, 2).text() == '1'
        window.row_fields['exclude_rows'].setText('2')
        window.row_fields['display_hidden_rows'].setText('4')
        window.save_document()
        wait(app, lambda: not window._busy and not window.local_dirty and bool(window.document.get('saved_revision')))
        assert window.document['draft']['mapping']['columns']['lateral']['offset'] == 1
        assert set(window.document['draft']['mapping']['columns']) == {'axial', 'lateral'}
        window.import_table()
        wait(app, lambda: bool(window.document['runs']) and not window._busy)
        job = window.document['runs'][-1]['job_id']
        wait(app, lambda: client.status(job)['state'] in {'SUCCEEDED', 'FAILED'})
        assert client.status(job)['state'] == 'SUCCEEDED'
        page = client.document_result(document['id'], job, selection={'responses': ['axial'], 'rows': [2, 3]})
        response = page['responses']['axial']
        assert response['source_rows'] == [4] and response['value'] == [40]
        assert response['raw_samples']['source_rows'] == [3] and response['raw_samples']['value'] == [30]
        wait(app, lambda: not window._busy)
        window._draw_result({'status': {'state': 'SUCCEEDED'}, 'result': page}, (document['id'], job, 2, 1, 'axial'))
        assert window.axes.lines
        assert all(math.isnan(value) for line in window.axes.lines for value in line.get_ydata())
        assert window.values.item(0, 0).text() == '3'  # original raw audit row remains independent
        # Duplicate rename preserves both channels as an invalid saveable draft.
        window.mapping.item(1, 1).setText('lateral')
        assert '' in window.edited_draft()['mapping']['columns']
        window.channel_selector.setCurrentText('lateral')
        window.channel_selector.setCurrentText('')
        assert window._channel_name == ''
        window.save_document()
        wait(app, lambda: not window._busy and not window.local_dirty and bool(window.document['diagnostics']))
        columns = window.document['draft']['mapping']['columns']
        assert len(columns) == 2 and columns['']['column'] == 1 and columns['lateral']['column'] == 2
        assert not window.import_button.isEnabled()
        assert source.read_bytes() == original
    finally:
        wait(app, lambda: not window._busy)
        window._allow_close = True
        window.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_multiple_duplicate_renames_never_overwrite_existing_channel(app):
    value = draft('Dsource')
    third = deepcopy(value['mapping']['columns']['response'])
    third['column'] = 3
    value['mapping']['columns']['third'] = third
    document = {'id': 'Tdata', 'session_id': 'Sowner', 'generation': 0, 'title': 'Draft identity fixture',
                'draft': value, 'diagnostics': [], 'dirty': False, 'runs': []}
    window = DataWindow(None, auto_open=False, poll_interval=0)
    try:
        window._show_document(document)
        window.mapping.item(1, 1).setText('lateral')
        window.channel_selector.setCurrentText('third')
        window.mapping.item(1, 1).setText('lateral')
        columns = window.edited_draft()['mapping']['columns']
        assert len(columns) == 3 and {row['column'] for row in columns.values()} == {1, 2, 3}
        assert set(columns) == {'', ' ', 'lateral'}
        window.channel_selector.setCurrentText('')
        window.mapping.item(1, 1).setText('axial')
        window.channel_selector.setCurrentText(' ')
        window.mapping.item(1, 1).setText('restored third')
        assert set(window.edited_draft()['mapping']['columns']) == {'axial', 'restored third', 'lateral'}
    finally:
        window._allow_close = True
        window.close()
