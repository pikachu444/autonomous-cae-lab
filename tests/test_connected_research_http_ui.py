"""Real loopback/Qt document integration; native runtimes are never launched."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
import threading
import time
from urllib.error import HTTPError

import pytest
pytest.importorskip('PySide6')
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLineEdit

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
    raise AssertionError('Real HTTP/Qt request did not settle')


def test_qt_edit_http_reader_import_and_invalid_draft_share_one_owner(tmp_path, monkeypatch):
    application = QApplication.instance() or QApplication([])
    source = tmp_path / 'observations'
    source.mkdir()
    # Distinct column order/values; this is reader integration, not an elastic benchmark.
    (source / 'displacement.csv').write_text('u,t\n.20,0\n.45,1\n.70,2\n')
    service = LabService(tmp_path / 'workspace')
    server = LabHTTPServer(service, 0, workbench_config={'input_roots':{'tests':str(source)}})
    thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval':.02}, daemon=True)
    thread.start()
    client = Client('http://127.0.0.1:' + str(server.server_port))
    second_client = Client(client.url)  # Same transport used by the MCP wrappers, not a simulated MCP session.
    metadata_entered, metadata_release = threading.Event(), threading.Event()
    result_read = client.document_result
    command = client.document_command
    submitted = []

    def held_result_read(identifier, job_id, *, selection=None):
        result = result_read(identifier, job_id, selection=selection)
        if selection == {'metadata_only': True}:
            # Hold delivery of the REAL HTTP result to reproduce the CI timing:
            # job completion does not mean the GUI has finished reading it.
            metadata_entered.set()
            assert metadata_release.wait(6), 'Metadata delivery was not released'
        return result

    def recorded_command(identifier, operation, arguments, **kwargs):
        submitted.append(operation)
        return command(identifier, operation, arguments, **kwargs)

    monkeypatch.setattr(client, 'document_result', held_result_read)
    monkeypatch.setattr(client, 'document_command', recorded_command)
    window = DataWindow(client, auto_open=False, poll_interval=0)
    try:
        assert client.desktop_context()['export_root'] == str(server.workbench.desktop.root)
        entries = client.local_inputs('tests')['entries']
        registered = client.register_local_input('tests', entries[0]['relative'])
        draft = default_draft()
        draft['data_id'] = registered['id']
        draft['mapping']['skip_header'] = 1
        spec = draft['mapping']['columns']['response']
        spec.update(column=0, unit='mm', component='x', location='gauge',
                    measure='displacement', frame='laboratory')
        spec['axis'].update(column=1, name='time', unit='s')
        document = client.document_open(kind='data', title='Measured travel', draft=draft)
        window._show_document(document)
        window.show()
        # Human edits the actual table; a separate client reads the exact owner state.
        window.mapping.item(1, 7).setText('machine_cartesian')
        window.apply_button.click()
        wait(application, lambda:not window._busy and not window.local_dirty)
        current = second_client.document_read(document['id'])
        assert current['draft']['mapping']['columns']['response']['frame'] == 'machine_cartesian'
        assert current['generation'] == window.document['generation']
        window.import_button.click()
        wait(application, lambda: bool(window.document['runs']))
        job_id = window.document['runs'][0]['job_id']
        wait(application, lambda:client.status(job_id)['state'] in {'SUCCEEDED','FAILED'})
        result = second_client.document_result(document['id'], job_id)
        response = result['responses']['response']
        assert result['execution_status'] == 'SUCCEEDED'
        assert response['value'] == [.20, .45, .70]
        assert response['unit'] == 'mm' and response['frame'] == 'machine_cartesian'
        assert response['source_rows'] == [1,2,3]
        navigation = client.job_navigation(job_id)
        assert navigation['origin_document']['id'] == document['id'] and navigation['post_input'] is None
        wait(application, lambda: metadata_entered.is_set() or window.read_button.isEnabled())
        if not metadata_entered.is_set():
            window.read_button.click()
        wait(application, metadata_entered.is_set)
        assert window._busy and not window.editor.isEnabled() and not window.save_action.isEnabled()
        window.save_action.trigger()
        assert submitted == ['data.update', 'data.import']  # Disabled Save submits nothing.
        metadata_release.set()
        # Wait for the actual editable UI, not just the independently completed job.
        wait(application, lambda: not window._busy and window.values.rowCount() == 3
             and window.editor.isEnabled() and window.save_action.isEnabled())
        assert window.values.item(0, 0).text() == '1'
        # Invalid text survives save; no stale client or failed submit changes the valid old run.
        window.mapping.setCurrentCell(1, 2)
        window.mapping.setFocus()
        QTest.keyClick(window.mapping, Qt.Key.Key_F2)
        editor = QApplication.focusWidget()
        assert isinstance(editor, QLineEdit) and window.mapping.isAncestorOf(editor)
        QTest.keyClick(editor, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
        QTest.keyClicks(editor, 'unfinished column')
        QTest.keyClick(editor, Qt.Key.Key_Return)
        wait(application, lambda: window.local_dirty
             and window.mapping.item(1, 2).text() == 'unfinished column')
        assert window.local_dirty and window.save_action.isEnabled()
        window.save_action.trigger()
        wait(application, lambda:not window._busy and bool(window.document.get('saved_revision')))
        saved = second_client.document_read(document['id'])
        assert saved['diagnostics'] and saved['draft']['mapping']['columns']['response']['column'] == 'unfinished column'
        assert submitted == ['data.update', 'data.import', 'data.update', 'document.save']
        assert not window.import_button.isEnabled()
        with pytest.raises(HTTPError):
            second_client.document_command(document['id'], 'data.import', {},
                session_id=saved['session_id'], expected_generation=saved['generation'], command_id='Cinvalidimport')
        with pytest.raises(HTTPError):
            second_client.document_command(document['id'], 'data.update', {'draft':draft},
                session_id=current['session_id'], expected_generation=current['generation'], command_id='Cstale')
        with pytest.raises(HTTPError):
            second_client.native_submit('Cmissing')
        with pytest.raises(HTTPError):
            second_client.numerical_adopt('Nmissing',job_id,'candidate',material_document_id='Mmissing',
                session_id=saved['session_id'],expected_generation=0,command_id='Creject')
        assert len(server.workbench.manager.list()) == 1
        assert second_client.document_result(document['id'],job_id)['responses']['response'] == response
        wait(application, lambda: not window._busy)
        window.open_document(document_id=document['id'])
        wait(application, lambda: not window._busy and window.editor.isEnabled())
        assert window.document['saved_revision'] == saved['saved_revision']
        assert window.mapping.item(1, 2).text() == 'unfinished column'
        assert window.document['diagnostics'] and not window.import_button.isEnabled()
        assert len(window.document['runs']) == 1
        assert second_client.document_result(document['id'], job_id)['responses']['response'] == response
    finally:
        metadata_release.set()
        window._allow_close = True
        window.local_dirty = False
        if window.document:
            window.document['dirty'] = False
        wait(application, lambda:not window._busy)
        window.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
