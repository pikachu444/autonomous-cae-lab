"""Qt protocol editing against real owners; no solver job is launched."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from copy import deepcopy
import threading
import time
import pytest
pytest.importorskip('PySide6')
pytest.importorskip('matplotlib')
from PySide6.QtCore import QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLineEdit
from apps.research.material_window import MaterialWindow
from apps.research.material_control_dialog import MaterialControlDialog


def wait(app, ready):
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        app.processEvents()
        if ready():
            return
        QTest.qWait(10)
    raise AssertionError('Protocol reply timeout')


@pytest.fixture
def owners(tmp_path):
    pytest.importorskip('caelab.material_control')
    from apps.lab.service import LabService
    from apps.lab.server import LabHTTPServer
    from caelab.workbench_client import Client
    app = QApplication.instance() or QApplication([])
    service = LabService(tmp_path)
    server = LabHTTPServer(service, 0)
    thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .02}, daemon=True)
    thread.start()
    client = Client(f'http://127.0.0.1:{server.server_port}')
    windows = [MaterialWindow(client, title=title, poll_interval=0) for title in ('인장 A', '인장 B')]
    wait(app, lambda: all(window.document and not window._busy for window in windows))
    try:
        client._test_workbench = server.workbench
        yield app, client, windows
    finally:
        wait(app, lambda: all(not window._busy for window in windows))
        for window in windows:
            window._allow_close = True
            window.close()
        app.processEvents()
        server.shutdown(); server.server_close(); service.shutdown(); thread.join(2)


def configure(app, editor, control='stretch', lateral='free'):
    def edit():
        dialog = next(widget for widget in QApplication.topLevelWidgets() if isinstance(widget, MaterialControlDialog) and widget.isVisible())
        dialog.control.setCurrentIndex(dialog.control.findData(control))
        dialog.lateral.setCurrentIndex(dialog.lateral.findData(lateral))
        dialog._compile()
    QTimer.singleShot(0, edit)
    editor.configure_trial()


def test_trial_local_undo_redo_targets_apply_and_other_owner_unchanged(owners):
    app, client, (first, second) = owners
    before, other = deepcopy(first.document), deepcopy(second.document)
    configure(app, first)
    assert first.local_dirty
    assert client.document_read(first.document['id']) == before
    assert first.edited_draft()['settings']['boundary_control']['stress_components'] == {'yy': [0., 0., 0.], 'zz': [0., 0., 0.]}
    assert first.history.columnCount() == 12
    assert '초기 추정' in first.history.horizontalHeaderItem(5).text()
    first.undo_inputs()
    assert not first.local_dirty and 'boundary_control' not in first.edited_draft()['settings']
    first.redo_inputs()
    first.history.item(1, 10).setText('0.1')
    first.apply_inputs()
    wait(app, lambda: not first._busy)
    assert first.document['draft']['settings']['boundary_control']['stress_components']['yy'][1] == .1
    first.save_document()
    wait(app, lambda: not first._busy)
    reopened = client.document_open(kind='material', document_id=first.document['id'])
    assert reopened['draft'] == first.document['draft']
    assert client.document_read(second.document['id']) == other
    from caelab.material_document import MaterialDocuments
    owner = client._test_workbench.material_documents
    cold = MaterialDocuments(owner.root.parent, 'Scold', owner.submit, owner.manager)
    assert cold.open(document_id=first.document['id'])['draft'] == first.document['draft']


def test_invalid_live_cell_kept_in_dialog_without_owner_mutation(owners):
    app, client, (first, _) = owners
    before = deepcopy(first.document)
    dialog = MaterialControlDialog(client, first.document['draft']['settings'], first)
    dialog.show(); dialog.activateWindow(); app.processEvents()
    dialog.table.setCurrentCell(1, 1)
    dialog.table.editItem(dialog.table.item(1, 1))
    app.processEvents()
    entry = QApplication.focusWidget()
    assert isinstance(entry, QLineEdit)
    entry.setText('1e')
    dialog._compile()
    wait(app, lambda: dialog._worker is None)
    assert dialog.result_settings is None and dialog.isVisible()
    assert dialog.table.item(1, 1).text() == '1e'
    assert client.document_read(first.document['id']) == before
    dialog.reject()


def test_control_modes_keep_separate_raw_value_buffers(owners):
    app, client, (first, _) = owners
    dialog = MaterialControlDialog(client, first.document['draft']['settings'], first)
    dialog.table.item(1, 1).setText('1e')
    dialog.control.setCurrentIndex(dialog.control.findData('engineering_strain'))
    assert float(dialog.table.item(1, 1).text()) == pytest.approx(.001)
    dialog.control.setCurrentIndex(dialog.control.findData('stretch'))
    assert dialog.table.item(1, 1).text() == '1e'
    dialog.reject()


def test_peer_change_during_trial_preserves_proposed_protocol_and_blocks_apply(owners):
    app, client, (first, _) = owners
    before = deepcopy(first.document)
    def change_then_compile():
        dialog = next(widget for widget in QApplication.topLevelWidgets() if isinstance(widget, MaterialControlDialog) and widget.isVisible())
        peer = deepcopy(before['draft'])
        peer['settings']['parameters']['E'] = 1500
        client.document_command(before['id'], 'material.update', {'draft': peer},
            session_id=before['session_id'], expected_generation=before['generation'], command_id='Cpeertrial')
        first.refresh_document()
        wait(app, lambda: not first._busy and first.document['generation'] != before['generation'])
        dialog.lateral.setCurrentIndex(dialog.lateral.findData('free'))
        dialog._compile()
    QTimer.singleShot(0, change_then_compile)
    first.configure_trial()
    assert first.conflict and first.local_dirty
    proposed = first.edited_draft()['settings']
    assert proposed['parameters']['E'] == 1000 and 'boundary_control' in proposed
    assert not first.apply_inputs()
    assert client.document_read(first.document['id'])['draft']['settings']['parameters']['E'] == 1500


@pytest.mark.parametrize('values', [[0., 1.], []])
def test_stress_targets_visible_and_prefix_failure_is_distinct(owners, values):
    app, client, (first, _) = owners
    configure(app, first, control='stress')
    assert first.history.columnCount() == 13
    assert '목표 응력 xx' in first.history.horizontalHeaderItem(10).text()
    first.document['runs'] = [{'job_id': 'Jfixture', 'input_generation': 0, 'is_current_input': True}]
    first._result_cache['Jfixture'] = {'execution_status': 'FAILED', 'responses': {'stress_xx': {
        'kind': 'series', 'value': values, 'unit': 'MPa', 'component': 'xx',
        'location': 'material_point', 'frame': 'material_cartesian', 'measure': 'infinitesimal_Cauchy',
        'axes': [{'name': 'time', 'unit': 's', 'values': [float(i) for i in range(len(values))]}], 'partial': True, 'valid': False}},
        'diagnostics': {'fixture': 'Retained accepted prefix, no physics qualification'}}
    first._populate_runs(prefer_job='Jfixture')
    first._draw_results()
    if values:
        assert len(first.axes.lines) == 1
        assert '실패 전 유효 구간' in first.axes.lines[0].get_label()
        assert list(first.axes.lines[0].get_xdata()) == [0., 1.]
    else:
        assert not first.axes.lines
        assert '유효한 계산 값이 없습니다' in first._plot_errors['Jfixture']
