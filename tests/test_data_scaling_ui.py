"""Explicit Data transformations through actual Qt/HTTP/table code; no solver."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from copy import deepcopy
import json
import threading
import time
from urllib.error import HTTPError

import pytest
pytest.importorskip('PySide6')
pytest.importorskip('matplotlib')
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from apps.lab.server import LabHTTPServer
from apps.lab.service import LabService
from apps.research.data_window import DataWindow
from caelab.data_document import default_draft
from caelab.workbench_client import Client


def wait(application, condition):
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        application.processEvents()
        if condition():
            return
        time.sleep(.005)
    raise AssertionError('Data Qt/HTTP action did not settle')


@pytest.fixture
def application():
    return QApplication.instance() or QApplication([])


def test_scale_offset_cells_preserve_older_defaults_and_invalid_text(application):
    document = {'id': 'Ttest', 'session_id': 'Sowner', 'generation': 0,
        'title': 'Original mapping', 'draft': default_draft(), 'runs': [],
        'diagnostics': [], 'dirty': False, 'can_undo': False, 'can_redo': False}
    window = DataWindow(None, auto_open=False, poll_interval=0)
    try:
        window._show_document(document)
        for row in (0, 1):
            assert window.mapping.item(row, 8).text() == '1'
            assert window.mapping.item(row, 9).text() == '0'
            assert window.mapping.item(row, 8).flags() & Qt.ItemFlag.ItemIsEditable
            assert window.mapping.item(row, 9).flags() & Qt.ItemFlag.ItemIsEditable
        assert window.edited_draft() == document['draft']  # No silent schema rewrite.
        # Nonfinite/unfinished input must stay raw JSON text, not NaN/Infinity.
        for row, scale, offset in ((0, 'unfinished scale', 'nan'), (1, 'inf', 'bad offset')):
            window.mapping.item(row, 8).setText(scale)
            window.mapping.item(row, 9).setText(offset)
        invalid = window.edited_draft()
        spec = invalid['mapping']['columns']['response']
        assert (spec['axis']['scale'], spec['axis']['offset']) == ('unfinished scale', 'nan')
        assert (spec['scale'], spec['offset']) == ('inf', 'bad offset')
        json.dumps(invalid, allow_nan=False)
        changed = deepcopy(document)
        changed['draft'] = invalid
        window._show_document(changed)
        assert window.edited_draft() == invalid
    finally:
        window._allow_close = True
        window.close()


def test_axis_response_transform_apply_undo_save_and_invalid_block(application, tmp_path):
    source_root = tmp_path / 'source'
    source_root.mkdir()
    source = source_root / 'measured_stress.csv'
    raw = b't_ms,Pxx_Pa\n100,-250000\n250,750000\n700,3000000\n'
    source.write_bytes(raw)
    service = LabService(tmp_path / 'workspace')
    server = LabHTTPServer(service, 0,
        workbench_config={'input_roots': {'observations': str(source_root)}})
    thread = threading.Thread(target=server.serve_forever,
        kwargs={'poll_interval': .02}, daemon=True)
    thread.start()
    client = Client('http://127.0.0.1:' + str(server.server_port))
    reader = Client(client.url)
    window = DataWindow(client, auto_open=False, poll_interval=0)
    try:
        registered = client.register_local_input('observations', source.name)
        draft = default_draft()
        draft['data_id'] = registered['id']
        draft['mapping']['skip_header'] = 1
        spec = draft['mapping']['columns']['response']
        spec.update(column=1, unit='Pa', component='xx', location='material_point',
                    measure='first_piola', frame='reference')
        spec['axis'].update(column=0, name='time', unit='ms')
        document = client.document_open(kind='data', draft=draft)
        window._show_document(document)
        window.show()
        # Every transform is entered in a visible cell. Unit edits alone infer nothing.
        window.mapping.item(0, 3).setText('s')
        window.mapping.item(1, 3).setText('MPa')
        unscaled = window.edited_draft()['mapping']['columns']['response']
        assert 'scale' not in unscaled and 'scale' not in unscaled['axis']
        for row, scale, offset in ((0, '0.001', '-0.1'), (1, '1e-6', '-0.25')):
            window.mapping.item(row, 8).setText(scale)
            window.mapping.item(row, 9).setText(offset)
        window.apply_button.click()
        wait(application, lambda: not window._busy and not window.local_dirty)
        applied = reader.document_read(document['id'])
        spec = applied['draft']['mapping']['columns']['response']
        assert (spec['scale'], spec['offset']) == (1e-6, -.25)
        assert (spec['axis']['scale'], spec['axis']['offset']) == (.001, -.1)
        wait(application, window.import_button.isEnabled)
        window.import_button.click()
        wait(application, lambda: bool(window.document['runs']) and not window._busy)
        job_id = window.document['runs'][0]['job_id']
        wait(application, lambda: client.status(job_id)['state'] in {'SUCCEEDED', 'FAILED'})
        result = reader.document_result(document['id'], job_id)
        assert result['execution_status'] == 'SUCCEEDED'
        response = result['responses']['response']
        assert response['value'] == pytest.approx([-.5, .5, 2.75])
        assert response['axes'][0]['values'] == pytest.approx([0, .15, .6])
        assert response['unit'] == 'MPa' and response['axes'][0]['unit'] == 's'
        assert response['source_rows'] == [1, 2, 3]
        assert response['frame'] == 'reference' and response['measure'] == 'first_piola'
        assert source.read_bytes() == raw
        assert '-250000' in reader.document_source_preview(document['id'])['text']

        wait(application, window.save_action.isEnabled)
        window.save_action.trigger()
        wait(application, lambda: not window._busy and bool(window.document.get('saved_revision')))
        saved_revision = window.document['saved_revision']
        folder = server.workbench.data_documents._folder(document['id']) / 'revisions' / saved_revision
        assert json.loads((folder / 'document.json').read_text(encoding='utf-8'))['draft'] == applied['draft']
        wait(application, window.undo_action.isEnabled)
        window.undo_action.trigger()
        wait(application, lambda: not window._busy and window.document['draft'] == draft)
        assert window.mapping.item(0, 8).text() == '1'
        assert window.mapping.item(1, 9).text() == '0'
        wait(application, window.redo_action.isEnabled)
        window.redo_action.trigger()
        wait(application, lambda: not window._busy and window.document['draft'] == applied['draft'])
        assert reader.document_result(document['id'], job_id)['responses']['response'] == response

        # Invalid axis/response text survives Save; the previous actual result remains readable.
        window.mapping.item(0, 8).setText('unfinished axis scale')
        window.mapping.item(1, 9).setText('unfinished response offset')
        wait(application, window.save_action.isEnabled)
        window.save_action.trigger()
        wait(application, lambda: not window._busy and window.document['saved_revision'] != saved_revision)
        invalid = reader.document_read(document['id'])
        spec = invalid['draft']['mapping']['columns']['response']
        assert spec['axis']['scale'] == 'unfinished axis scale'
        assert spec['offset'] == 'unfinished response offset'
        assert invalid['diagnostics'] and not window.import_button.isEnabled()
        saved = server.workbench.data_documents._folder(document['id']) / 'revisions' / invalid['saved_revision'] / 'document.json'
        assert json.loads(saved.read_text(encoding='utf-8'))['draft'] == invalid['draft']
        with pytest.raises(HTTPError):
            client.document_command(document['id'], 'data.import', {},
                session_id=invalid['session_id'], expected_generation=invalid['generation'],
                command_id='Cinvalidtransform')
        assert len(server.workbench.manager.list()) == 1
        assert reader.document_result(document['id'], job_id)['responses']['response'] == response
        assert source.read_bytes() == raw
    finally:
        wait(application, lambda: not window._busy)
        window._allow_close = True
        window.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
