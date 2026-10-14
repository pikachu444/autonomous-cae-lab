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
    assert native.metadata['regions'][0]['label'] == '선택 영역'
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


def test_korean_choices_keep_native_values_and_details_preserve_latest_failure(panel, native, app):
    panel.show()
    app.processEvents()
    assert panel.order.currentText() == '2차' and panel.order.currentData() == '2nd'
    assert panel.dimension.currentText() == '3차원' and panel.dimension.currentData() == '3D'
    panel.new_condition.setCurrentIndex(panel.new_condition.findData('Force'))
    assert panel.new_condition.currentText() == '힘'
    panel.force.setValue(12.123456789)
    panel.create_condition()
    assert panel.test_calls[-1][1]['kind'] == 'Force'
    assert panel.test_calls[-1][1]['force'] == 12.123456789
    panel.region_label.setText('사용자 지정 영역')
    panel.status.setPlainText('메시 생성 실패\n원 진단과 기존 결과는 유지됩니다.')
    before = panel.status.toPlainText()
    panel.tabs.setCurrentIndex(1)
    panel.condition.setCurrentIndex(panel.condition.findData(native.force.Name))
    panel.poll()
    assert panel.status.toPlainText() == before and panel.status_summary.text() == '메시 생성 실패'
    assert panel.condition_message.isVisible() and '선택한 면으로 변경' in panel.condition_message.text()
    assert panel.region_label.text() == '사용자 지정 영역'
    assert not panel.status.isVisible()
    panel.details_button.click()
    assert panel.status.isVisible() and panel.status.toPlainText() == before
    panel.details_button.click()
    assert not panel.status.isVisible() and panel.status_summary.text() == '메시 생성 실패'


def test_contact_read_cancel_and_late_first_apply_preserve_edit_buffer(panel, native, monkeypatch):
    from test_pre_fem_edit import Object, Quantity
    import ObjectsFem
    def make_contact(doc):
        return Object(doc, 'Contact', 'Fem::ConstraintContact', References=[],
            SurfaceBehavior='Linear', Slope=Quantity('0 MPa/mm'), Friction=False,
            FrictionCoefficient=0, StickSlope=Quantity('0 MPa/mm'), Adjust=Quantity('0 mm'),
            EnableThermalContact=False)
    monkeypatch.setattr(ObjectsFem, 'makeConstraintContact', make_contact, raising=False)
    page = panel.contact_page
    page.fields['normal_stiffness_MPa_per_mm'].setText('1e')
    page.apply()
    page.fields['normal_stiffness_MPa_per_mm'].setText('2e')
    page.fields['normal_stiffness_MPa_per_mm'].textEdited.emit('2e')
    panel.test_complete()
    assert page.pair.currentData() == 'Contact'
    assert page.fields['normal_stiffness_MPa_per_mm'].text() == '2e'
    assert native.metadata['contacts'][0]['draft']['normal_stiffness_MPa_per_mm'] == '1e'
    page.action('highlight')
    panel.test_complete()
    assert page.fields['normal_stiffness_MPa_per_mm'].text() == '2e'
    native.selection = [NS(Object=native.shape, SubElementNames=['Face1'])]
    original = native.editor.contact.preview
    def preview(obj, args):
        native.editor.contact.previews['Ptest'] = {}
        return {'preview_id': 'Ptest', 'old': {'face_count': 1, 'area_mm2': 1.,
            'centroid_mm': [0, 0, 0], 'face_normals': [[0, 0, 1]]},
            'new': {'face_count': 1, 'area_mm2': 1.,
            'centroid_mm': [0, 0, 0], 'face_normals': [[0, 0, -1]]}}
    monkeypatch.setattr(native.editor.contact, 'preview', preview)
    page.preview('a')
    def cancel():
        dialog = QtWidgets.QApplication.activeModalWidget()
        assert dialog is not None
        table = dialog.findChild(QtWidgets.QTableWidget)
        assert table.rowCount() == 4 and '-1' in table.item(3, 2).text()
        dialog.reject()
    QtCore.QTimer.singleShot(0, cancel)
    panel.test_complete()
    assert panel.test_calls[-1][0] == 'pre.contact.cancel_rebind'
    panel.test_complete()
    assert page.fields['normal_stiffness_MPa_per_mm'].text() == '2e'
    assert not native.editor.contact.previews
