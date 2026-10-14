"""Live Data cell buffers must survive owner polling before itemChanged."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from copy import deepcopy
import time
import threading

import pytest
pytest.importorskip('PySide6')
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLineEdit

from apps.research.data_window import DataWindow
from caelab.data_document import default_draft


@pytest.mark.parametrize('changed', [False, True])
def test_data_poll_preserves_live_cell_and_detects_remote_conflict(changed):
    app = QApplication.instance() or QApplication([])
    document = {'id': 'Tedit', 'session_id': 'Sedit', 'generation': 0, 'title': 'Data edit',
                'draft': default_draft(), 'runs': [], 'diagnostics': [], 'dirty': False}
    remote = deepcopy(document)
    if changed:
        remote['generation'] = 1
        remote['draft']['mapping']['columns']['response']['unit'] = 'Pa'

    class Client:
        def document_read(self, identifier):
            return deepcopy(remote)

    window = DataWindow(Client(), auto_open=False, poll_interval=0)
    try:
        window._show_document(document)
        window.show(); app.processEvents()
        window.mapping.setCurrentCell(1, 3)
        window.mapping.editItem(window.mapping.item(1, 3))
        app.processEvents()
        cell = QApplication.focusWidget()
        assert isinstance(cell, QLineEdit)
        cell.selectAll(); QTest.keyClicks(cell, 'unfinished unit')
        assert not window.local_dirty
        window.refresh_document()
        deadline = time.monotonic() + 5
        while window._busy and time.monotonic() < deadline:
            app.processEvents(); QTest.qWait(5)
        assert not window._busy
        assert cell.text() == 'unfinished unit'
        assert window.conflict is changed
        QTest.keyClick(cell, Qt.Key.Key_Return); app.processEvents()
        assert window.edited_draft()['mapping']['columns']['response']['unit'] == 'unfinished unit'
        assert window.document['generation'] == 0
    finally:
        window._allow_close = True
        window.close(); app.processEvents()


def test_multiple_test_files_open_independent_owners_and_preserve_partial_success(tmp_path):
    from apps.lab.server import LabHTTPServer
    from apps.lab.service import LabService
    from caelab.workbench_client import Client
    app = QApplication.instance() or QApplication([])
    first = tmp_path / 'tensile_A.csv'
    second = tmp_path / 'tensile_B.csv'
    first.write_text('time,force\n0,0\n1,10\n', encoding='utf-8')
    second.write_text('extension\tload\n0\t0\n10\t1\n', encoding='utf-8')
    service = LabService(tmp_path / 'store')
    server = LabHTTPServer(service, 0)
    thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .02}, daemon=True)
    thread.start()
    client = Client(f'http://127.0.0.1:{server.server_port}')
    window = DataWindow(client, auto_open=False, poll_interval=0)

    def wait(condition):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            app.processEvents(); QTest.qWait(5)
            if condition():
                return
        raise AssertionError('Data owner reply timeout')

    try:
        original = client.document_open(kind='data', title='Current draft')
        window._opened(original)
        wait(lambda: not window._busy)
        window.row_fields['quality_rows'].setText('3')
        window.local_dirty = True
        before = deepcopy(window.edited_draft())
        window.open_test_files([first, tmp_path / 'missing.csv', tmp_path / 'unsupported.json', second])
        wait(lambda: not window._busy and len(window._data_windows) == 2)
        assert 'missing.csv' in window.message.text()
        assert 'unsupported.json' in window.message.text() and '지원되는 표 파일' in window.message.text()
        assert window.edited_draft() == before and window.local_dirty
        one, two = window._data_windows
        wait(lambda: not one._busy and not two._busy)
        one._populate_window_menu()
        actions = {action.text(): action for action in one.window_menu.actions()}
        assert 'tensile_A' in actions and 'tensile_B' in actions
        assert one.next_window_action.isEnabled()
        before_switch = deepcopy(one.document)
        actions['tensile_B'].trigger(); app.processEvents()
        assert one.document == before_switch
        assert one.document['id'] != two.document['id'] != original['id']
        assert one.document['draft']['data_id'] != two.document['draft']['data_id']
        assert one.document['title'] == 'tensile_A' and two.document['title'] == 'tensile_B'
        one.mapping.item(1, 3).setText('MPa')
        one.save_document(); wait(lambda: not one._busy and not one.document['dirty'])
        assert client.document_read(one.document['id'])['draft']['mapping']['columns']['response']['unit'] == 'MPa'
        assert client.document_read(two.document['id'])['draft']['mapping']['columns']['response']['unit'] == ''
        assert not one.document['runs'] and not two.document['runs']
        assert first.read_text(encoding='utf-8') == 'time,force\n0,0\n1,10\n'
    finally:
        for opened in [window] + window._data_windows:
            wait(lambda: not opened._busy)
            opened._allow_close = True; opened.close()
        app.processEvents()
        server.shutdown(); server.server_close(); service.shutdown(); thread.join(2)
