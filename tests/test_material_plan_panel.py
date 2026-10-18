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


def test_two_plan_buffers_focus_and_parent_close_are_independent(host, monkeypatch):
    app, client, material, panel, plans = host
    first_id, second_id = [plan['id'] for plan in plans]
    panel.plans.setCurrentIndex(panel.plans.findData(first_id))
    first = panel._widgets[first_id]
    assert first.table.item(1, 0).text() == '포아송비 ν'
    assert first.buffer_snapshot()['variables'][1]['id'] == 'nu'
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
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, 'exec', lambda self: QMessageBox.StandardButton.Cancel)
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


def test_lost_related_save_reply_reopens_exact_receipt_with_unfinished_cells(host, monkeypatch):
    from PySide6.QtWidgets import QLineEdit
    from apps.research.material_related_save import RelatedSaveDialog
    app, client, material, panel, plans = host
    identifier = panel.plans.currentData(); widget = panel._widgets[identifier]
    original = client.data_material; calls = []; previews = []
    def lose_execute_reply(operation, arguments):
        calls.append((operation, deepcopy(arguments)))
        value = original(operation, arguments)
        if operation == 'related_save.execute':
            raise ConnectionError('Injected lost HTTP reply after the actual owner saves committed')
        return value
    monkeypatch.setattr(client, 'data_material', lose_execute_reply)
    def save_and_close(dialog):
        wait(app, lambda: dialog.preview is not None and not dialog._busy)
        previews.append(deepcopy(dialog.preview))
        dialog.save()
        assert panel._related_save_receipts[identifier] == dialog.preview['receipt_id']
        wait(app, lambda: not dialog._busy)
        assert dialog.receipt is None and dialog.pending_preview == previews[0]
        dialog.reject(); return QDialog.DialogCode.Rejected
    monkeypatch.setattr(RelatedSaveDialog, 'exec', save_and_close)
    assert panel.save_related()
    receipt_id = previews[0]['receipt_id']
    assert panel.save_receipt_button.isEnabled()
    assert identifier in panel._related_save_unconfirmed
    assert panel._related_save_pending[identifier] == previews[0]
    # Querying a committed receipt must remain available with an unfinished
    # editor, while every mutation control stays unavailable.
    widget.table.setCurrentCell(0, 2); widget.table.setFocus()
    widget.table.editItem(widget.table.item(0, 2)); app.processEvents()
    editor = QApplication.focusWidget(); assert isinstance(editor, QLineEdit)
    old_cell = widget.table.item(0, 2).text(); editor.setText('1e')
    def reopen_only(dialog):
        wait(app, lambda: dialog.receipt is not None and not dialog._busy)
        assert dialog.preview['receipt_id'] == receipt_id
        assert not dialog.allow_writes and not dialog.save_button.isEnabled()
        assert not dialog.link_button.isEnabled() and not dialog.retry_button.isEnabled()
        assert dialog.receipt['all_saved']
        assert all(len(target['attempts']) == 1 for target in dialog.receipt['targets'])
        dialog.reject(); return QDialog.DialogCode.Rejected
    monkeypatch.setattr(RelatedSaveDialog, 'exec', reopen_only)
    # The ordinary action routes an unresolved save to its original result.
    assert panel.save_related()
    assert identifier not in panel._related_save_unconfirmed
    assert editor.text() == '1e' and widget.table.item(0, 2).text() == old_cell
    assert [operation for operation, _ in calls] == ['related_save.preview', 'related_save.execute', 'related_save.receipt']
    assert calls[-1][1] == {'receipt_id': receipt_id}
    QTest.keyClick(editor, Qt.Key.Key_Escape); app.processEvents()
    material.coefficients.setCurrentCell(0, 1); material.coefficients.setFocus()
    material.coefficients.editItem(material.coefficients.item(0, 1)); app.processEvents()
    material_editor = QApplication.focusWidget(); assert isinstance(material_editor, QLineEdit)
    material_cell = material.coefficients.item(0, 1).text(); material_editor.setText('2e')
    assert panel.save_related(receipt_id=receipt_id)
    assert material_editor.text() == '2e' and material.coefficients.item(0, 1).text() == material_cell
    assert [operation for operation, _ in calls][-1] == 'related_save.receipt'
    assert sum(operation == 'related_save.execute' for operation, _ in calls) == 1
    receipt = original('related_save.receipt', {'receipt_id': receipt_id})
    assert all(len(target['attempts']) == 1 for target in receipt['targets'])
    assert not any(document.get('runs') for document in client.documents()['documents'])
