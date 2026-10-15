"""Same Plan owners in Material and Numerical; no physics job is requested."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from copy import deepcopy
import threading
import time
import pytest
pytest.importorskip('PySide6')
pytest.importorskip('matplotlib')
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog
from apps.research.material_window import MaterialWindow
from apps.research.material_plan_panel import PlanPatchDialog


def wait(app, ready):
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        app.processEvents()
        if ready(): return
        QTest.qWait(10)
    raise AssertionError('Plan host reply timeout')


@pytest.fixture
def host(tmp_path):
    pytest.importorskip('caelab.plan_variables_api')
    pytest.importorskip('apps.research.plan_variables_widget')
    from apps.lab.server import LabHTTPServer
    from apps.lab.service import LabService
    from caelab.workbench_client import Client
    from caelab.numerical_document import from_material_document
    app = QApplication.instance() or QApplication([])
    service = LabService(tmp_path)
    server = LabHTTPServer(service, 0)
    thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .02}, daemon=True)
    thread.start()
    client = Client(f'http://127.0.0.1:{server.server_port}')
    material = MaterialWindow(client, poll_interval=0)
    wait(app, lambda: material.document and not material._busy)
    material.save_document(); wait(app, lambda: not material._busy)
    plans = [client.document_open(kind='numerical', title=name, draft=from_material_document(material.document))
             for name in ('인장 피팅 A', '인장 피팅 B')]
    material.show(); panel = material.open_plan_variables()
    wait(app, lambda: not panel._busy and panel.plans.count() == 2)
    try:
        yield app, client, material, panel, plans
    finally:
        wait(app, lambda: not material._busy and not panel._busy)
        for window in material._numerical_windows:
            window._allow_close = True; window.close()
        material._allow_close = True; material.close(); app.processEvents()
        server.shutdown(); server.server_close(); service.shutdown(); thread.join(2)


def test_two_plan_buffers_focus_and_parent_close_are_independent(host):
    app, client, material, panel, plans = host
    first_id, second_id = [plan['id'] for plan in plans]
    panel.plans.setCurrentIndex(panel.plans.findData(first_id))
    first = panel._widgets[first_id]
    first.table.item(0, 2).setText('1600')
    panel.plans.setCurrentIndex(panel.plans.findData(second_id))
    second = panel._widgets[second_id]
    second.table.item(0, 2).setText('1700')
    panel.plans.setCurrentIndex(panel.plans.findData(first_id))
    material.coefficients.item(0, 1).setText('1400')
    wait(app, lambda: first.undo_button.isEnabled())
    first.table.setFocus()
    QTest.keyClick(first.table, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
    assert first.buffer_snapshot()['variables'][0]['value'] == 1000
    assert material.edited_draft()['settings']['parameters']['E'] == 1400
    assert second.buffer_snapshot()['variables'][0]['value'] == 1700
    material.close(); app.processEvents()
    assert material.isVisible() and panel.has_pending_inputs()
    assert client.document_read(first_id)['draft']['variables'][0]['value'] == 1000


def test_explicit_plan_review_apply_save_and_same_standalone_owner(host, monkeypatch):
    app, client, material, panel, plans = host
    monkeypatch.setattr(PlanPatchDialog, 'exec', lambda self: QDialog.DialogCode.Accepted)
    identifier = panel.plans.currentData(); widget = panel._widgets[identifier]
    original = deepcopy(material.document['draft'])
    widget.table.item(0, 2).setText('1600')
    assert client.document_read(identifier)['draft']['variables'][0]['value'] == 1000
    widget.preview_changes()
    wait(app, lambda: not panel._busy and not widget.has_unapplied_buffer())
    assert client.document_read(identifier)['draft']['variables'][0]['value'] == 1600
    assert client.document_read(material.document['id'])['draft'] == original
    assert panel.has_pending_inputs()  # Applied owner draft still needs saving.
    panel.save_plan()
    wait(app, lambda: not panel._busy and not panel.has_pending_inputs())
    panel.open_plan()
    standalone = material._numerical_windows[-1]
    wait(app, lambda: standalone.document and not standalone._busy)
    assert standalone.document['id'] == identifier
    assert standalone.variables is not widget.table
    assert standalone.document['draft'] == widget.buffer_snapshot()
    assert not any(document.get('runs') for document in client.documents()['documents'])


def test_conflict_between_review_and_apply_keeps_cells(host, monkeypatch):
    app, client, material, panel, plans = host
    identifier = panel.plans.currentData(); widget = panel._widgets[identifier]
    before = widget.document_snapshot()
    def peer_edit(dialog):
        draft = deepcopy(before['draft']); draft['variables'][0]['value'] = 1800
        client.document_command(identifier, 'numerical.update', {'draft': draft},
            session_id=before['session_id'], expected_generation=before['generation'], command_id='Cpeerplan')
        return QDialog.DialogCode.Accepted
    monkeypatch.setattr(PlanPatchDialog, 'exec', peer_edit)
    widget.table.item(0, 2).setText('1600')
    widget.preview_changes()
    wait(app, lambda: not panel._busy and '변경' in widget.message.text())
    assert widget.has_unapplied_buffer()
    assert widget.buffer_snapshot()['variables'][0]['value'] == 1600
    assert client.document_read(identifier)['draft']['variables'][0]['value'] == 1800
    panel.save_plan()
    assert widget.has_unapplied_buffer()
