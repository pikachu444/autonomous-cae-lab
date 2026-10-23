"""Real Qt controls with delayed command receipts; no native app or mesher."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from copy import deepcopy
from types import SimpleNamespace as NS
import pytest

from test_pre_fem_edit import native  # Explicit native-shaped fixture, no FreeCAD import.
from apps.desktop_pre.fem_panel import make_panel

QtWidgets = pytest.importorskip('PySide6.QtWidgets')
QtCore = pytest.importorskip('PySide6.QtCore')


@pytest.fixture(scope='module')
def app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture
def panel(native, app):
    pending, calls = [], []
    def submit(operation, arguments, target, on_done=None):
        request = (operation, deepcopy(arguments), deepcopy(target), on_done)
        pending.append(request)
        calls.append(request[:3])
        return {'queued': True}
    widget = make_panel(QtWidgets, QtCore, native.editor, submit)
    widget.timer.stop()
    def complete():
        operation, arguments, target, callback = pending.pop(0)
        if operation == 'pre.select':
            native.selection = [NS(Object=native._object(row['object_id']), SubElementNames=[row['subelement']])
                                for row in arguments['objects']]
            value = {'selected': len(native.selection)}
        else:
            value = native.editor.dispatch(operation, arguments, target)
        callback({'status': 'COMPLETED', 'result': value})
    widget.test_pending, widget.test_calls, widget.test_complete = pending, calls, complete
    yield widget
    widget.close()
    widget.deleteLater()
    app.processEvents()


def test_existing_condition_highlight_then_confirm_uses_only_async_typed_owner_commands(panel, native):
    existing_conditions = [obj for obj in native.doc.Objects if obj.TypeId.startswith('Fem::Constraint')]
    panel.findChild(QtWidgets.QPushButton, 'femHighlightCondition').click()
    assert panel.test_calls[0][0] == 'pre.select' and not native.selection
    assert panel._command_busy
    panel.test_complete()
    assert native.selection[0].Object is native.shape and native.selection[0].SubElementNames == ['Face1']
    panel.findChild(QtWidgets.QPushButton, 'femRepairCondition').click()
    assert panel.test_calls[-1][0] == 'pre.fem.region_set'
    assert not native.metadata.get('conditions')
    panel.test_complete()
    assert panel.test_calls[-1][0] == 'pre.fem.condition_repair'
    assert panel.test_pending[0][2] == {'object_id': native.fixed.Name}
    panel.test_complete()
    assert [obj for obj in native.doc.Objects if obj.TypeId.startswith('Fem::Constraint')] == existing_conditions
    assert native.metadata['conditions'][0]['object_id'] == native.fixed.Name
    assert not native.editor._condition_errors(native.fixed, native.editor._metadata())
    assert 'NOT_RELEASED' in panel.status.toPlainText()


def test_quality_callback_populates_actual_rows_and_rejects_changed_selection_or_owner(panel, native):
    panel.read_quality()
    assert panel.quality.rowCount() == 0 and panel._command_busy
    panel.test_complete()
    assert panel.quality.item(0, 0).text() == '73'
    assert panel.distribution.rowCount() == 2
    panel.quality.selectRow(0)
    panel.highlight_quality()
    assert panel.test_calls[-1][1]['element_ids'] == [73]
    assert not native.mesh.ViewObject.HighlightedNodes
    panel.test_complete()
    assert native.mesh.ViewObject.HighlightedNodes == list(range(1, 11))
    panel.read_quality()
    panel.mesh.addItem('Another explicit selection', 'Other')
    blocked = panel.mesh.blockSignals(True)
    panel.mesh.setCurrentIndex(1)
    panel.mesh.blockSignals(blocked)
    panel.test_complete()
    assert 'STALE_SELECTION' in panel.status.toPlainText()
    blocked = panel.mesh.blockSignals(True)
    panel.mesh.setCurrentIndex(0)
    panel.mesh.blockSignals(blocked)
    panel.read_quality()
    _, _, _, callback = panel.test_pending.pop(0)
    old_doc = native.doc
    native.doc = NS(Name='ReopenedNativeOwner', Objects=[])
    callback({'status': 'COMPLETED', 'result': {'mesh_id': native.mesh.Name, 'rows': []}})
    assert 'STALE_SESSION' in panel.status.toPlainText()
    native.doc = old_doc
    assert panel.quality.item(0, 0).text() == '73'


def test_queued_continuation_preserves_late_form_edits_and_failure_releases_buttons(panel, native):
    native.selection = [NS(Object=native.shape, SubElementNames=['Face1'])]
    panel.capture_region()
    panel.min_size.setValue(9)
    panel.region_label.setText('Late local region label')
    panel.test_complete()
    assert panel.min_size.value() == 9 and panel.region_label.text() == 'Late local region label'
    assert native.metadata['regions'][0]['label'] == 'Selected native region'
    panel.apply_mesh_settings()
    assert not panel.findChild(QtWidgets.QPushButton, 'femApplyMeshSettings').isEnabled()
    _, _, _, callback = panel.test_pending.pop(0)
    callback({'status': 'FAILED', 'error': {'message': 'Controlled owner rejection'}})
    assert not panel._command_busy
    assert panel.findChild(QtWidgets.QPushButton, 'femApplyMeshSettings').isEnabled()
    assert panel.min_size.value() == 9 and panel.status.toPlainText() == 'Controlled owner rejection'


def test_late_condition_selection_stops_dependent_repair_and_keeps_prepared_region(panel, native):
    native.selection = [NS(Object=native.shape, SubElementNames=['Face1'])]
    panel.repair_condition()
    assert panel.test_calls[-1][0] == 'pre.fem.region_set'
    panel.condition.setCurrentIndex(panel.condition.findData(native.force.Name))
    panel.test_complete()
    assert len(panel.test_calls) == 1 and not panel.test_pending
    assert len(native.metadata['regions']) == 1 and not native.metadata.get('conditions')
    assert 'STALE_SELECTION' in panel.status.toPlainText()
