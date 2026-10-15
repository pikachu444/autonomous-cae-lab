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


def _second_mesh(native):
    from test_pre_fem_edit import Object, Quantity
    values = {key: value for key, value in vars(native.mesh).items()
              if key not in {'Document', 'Name', 'Label', 'TypeId'}}
    other = Object(native.doc, 'SecondMesh', native.mesh.TypeId, **values)
    other.CharacteristicLengthMax = Quantity('4 mm')
    native.analysis.addObject(other)
    return other


def test_open_prepared_mesh_selects_exact_second_target_and_submits_it(panel, native):
    other = _second_mesh(native)
    panel.tabs.setCurrentIndex(1)
    panel.open_mesh_settings(other.Name)
    assert panel.mesh.currentData() == other.Name and panel.tabs.currentIndex() == 0
    assert panel.max_size.value() == 4
    panel.min_size.setValue(1)
    panel.apply_mesh_settings()
    assert panel.test_calls[-1][2] == {'object_id': other.Name}
    panel.test_complete()
    assert other.CharacteristicLengthMin.Value == 1
    assert native.mesh.CharacteristicLengthMin.Value == 0
    panel.open_mesh_settings(native.mesh.Name)
    assert panel.mesh.currentData() == native.mesh.Name


def test_open_prepared_mesh_preserves_unapplied_settings_and_pending_command(panel, native):
    other = _second_mesh(native)
    panel.max_size.setValue(7)
    with pytest.raises(ValueError, match='미적용'):
        panel.open_mesh_settings(other.Name)
    assert panel.mesh.currentData() == native.mesh.Name and panel.max_size.value() == 7
    panel.apply_mesh_settings()
    with pytest.raises(ValueError, match='메시 작업'):
        panel.open_mesh_settings(other.Name)
    panel.test_complete()
    panel.open_mesh_settings(other.Name)
    assert panel.mesh.currentData() == other.Name and panel.max_size.value() == 4


def _local_region(panel, native):
    from test_pre_fem_edit import region
    selected = region(native)
    panel.refresh()
    panel.local_region.setCurrentIndex(panel.local_region.findData(selected['id']))
    return selected


def test_global_apply_keeps_local_draft_pending_for_exact_mesh_handoff(panel, native):
    other = _second_mesh(native)
    selected = _local_region(panel, native)
    panel.local_size.setValue(.4)
    panel.max_size.setValue(7)
    panel.apply_mesh_settings()
    panel.test_complete()
    assert native.mesh.CharacteristicLengthMax.Value == 7
    assert not native.mesh.MeshRegionList and panel.local_size.value() == .4
    with pytest.raises(ValueError, match='미적용'):
        panel.open_mesh_settings(other.Name)
    assert panel.mesh.currentData() == native.mesh.Name
    panel.apply_local_size()
    assert panel.test_calls[-1][2] == {'object_id': native.mesh.Name}
    panel.test_complete()
    assert native.mesh.MeshRegionList[0].CharacteristicLength.Value == .4
    assert panel.refinement.findData(native.mesh.MeshRegionList[0].Name) >= 0
    panel.open_mesh_settings(other.Name)
    assert panel.mesh.currentData() == other.Name and panel.max_size.value() == 4
    assert panel.local_region.currentData() is None and panel.local_size.value() == 1
    panel.local_region.setCurrentIndex(panel.local_region.findData(selected['id']))
    panel.local_size.setValue(.2)
    panel.apply_local_size()
    assert panel.test_calls[-1][2] == {'object_id': other.Name}
    panel.test_complete()
    assert other.MeshRegionList[0].CharacteristicLength.Value == .2
    assert native.mesh.MeshRegionList[0].CharacteristicLength.Value == .4


def test_local_apply_preserves_unsubmitted_global_draft_and_late_local_input(panel, native):
    other = _second_mesh(native)
    _local_region(panel, native)
    panel.max_size.setValue(7)
    panel.local_size.setValue(.4)
    panel.apply_local_size()
    panel.local_size.setValue(.6)
    panel.test_complete()
    assert native.mesh.CharacteristicLengthMax.Value == 2
    assert native.mesh.MeshRegionList[0].CharacteristicLength.Value == .4
    assert panel.max_size.value() == 7 and panel.local_size.value() == .6
    with pytest.raises(ValueError, match='미적용'):
        panel.open_mesh_settings(other.Name)
    panel.local_size.setValue(.4)
    with pytest.raises(ValueError, match='미적용'):
        panel.open_mesh_settings(other.Name)
    panel.apply_mesh_settings()
    panel.test_complete()
    panel.open_mesh_settings(other.Name)
    assert panel.mesh.currentData() == other.Name


def test_global_receipt_tracks_submitted_values_and_keeps_late_input_pending(panel, native):
    other = _second_mesh(native)
    panel.max_size.setValue(7)
    panel.apply_mesh_settings()
    panel.max_size.setValue(9)
    panel.test_complete()
    assert native.mesh.CharacteristicLengthMax.Value == 7 and panel.max_size.value() == 9
    with pytest.raises(ValueError, match='미적용'):
        panel.open_mesh_settings(other.Name)
    panel.max_size.setValue(7)
    panel.open_mesh_settings(other.Name)
    assert panel.mesh.currentData() == other.Name


def test_refresh_preserves_unsubmitted_mesh_fields_and_handoff_guard(panel, native):
    other = _second_mesh(native)
    _local_region(panel, native)
    panel.max_size.setValue(7)
    panel.local_size.setValue(.4)
    before = panel._mesh_fields()
    panel.refresh()
    assert panel._mesh_fields() == before
    with pytest.raises(ValueError, match='미적용'):
        panel.open_mesh_settings(other.Name)
    assert panel._mesh_fields() == before and panel.mesh.currentData() == native.mesh.Name


def _choose_draft_dialog(choice, title='미적용 메시 설정'):
    def choose():
        dialog = QtWidgets.QApplication.activeModalWidget()
        assert isinstance(dialog, QtWidgets.QMessageBox)
        assert dialog.windowTitle() == title
        assert dialog.defaultButton().text() == '취소' and dialog.escapeButton().text() == '취소'
        button = next(button for button in dialog.buttons() if button.text() == choice)
        button.click()
    QtCore.QTimer.singleShot(0, choose)


def _saved_refinements(panel, native):
    from test_pre_fem_edit import region
    first = region(native, label='첫 영역')
    second = region(native, 'Face2', label='둘째 영역')
    refs = [native.editor.dispatch('pre.fem.mesh_local_size',
        {'region_id': selected['id'], 'size': size, 'unit': 'mm'}, {'object_id': native.mesh.Name})
        for selected, size in ((first, .4), (second, .2))]
    panel.refresh()
    return first, second, refs


def test_saved_local_size_selection_reads_exact_native_size_and_region_without_applying_global(panel, native):
    from test_pre_fem_edit import Quantity
    first, second, refs = _saved_refinements(panel, native)
    panel.max_size.setValue(7)
    panel.refinement.setCurrentIndex(panel.refinement.findData(refs[0]['object_id']))
    assert panel.local_region.currentData() == first['id'] and panel.local_size.value() == .4
    assert panel.max_size.value() == 7 and panel._mesh_pending() and not panel.test_calls
    native._object(refs[0]['object_id']).CharacteristicLength = Quantity('.45 mm')
    panel.refinement.setCurrentIndex(panel.refinement.findData(refs[1]['object_id']))
    assert panel.local_region.currentData() == second['id'] and panel.local_size.value() == .2
    panel.refinement.setCurrentIndex(panel.refinement.findData(refs[0]['object_id']))
    assert panel.local_size.value() == .45  # Read native Quantity, not stale metadata size_mm.
    assert panel.max_size.value() == 7 and native.mesh.CharacteristicLengthMax.Value == 2


@pytest.mark.parametrize('choice', ['취소', '버리고 선택', '적용 후 선택'])
def test_saved_local_selection_resolves_only_local_draft_and_retains_global_draft(panel, native, choice):
    first, second, refs = _saved_refinements(panel, native)
    panel.refinement.setCurrentIndex(panel.refinement.findData(refs[0]['object_id']))
    panel.max_size.setValue(7)
    panel.local_size.setValue(.6)
    _choose_draft_dialog(choice, '미적용 국부 크기')
    panel.refinement.setCurrentIndex(panel.refinement.findData(refs[1]['object_id']))
    if choice == '적용 후 선택':
        assert panel.refinement.currentData() == refs[0]['object_id']
        assert panel.test_calls[-1] == ('pre.fem.mesh_local_size',
            {'region_id': first['id'], 'size': .6, 'unit': 'mm', 'refinement_id': refs[0]['object_id']},
            {'object_id': native.mesh.Name})
        panel.test_complete()
        assert native._object(refs[0]['object_id']).CharacteristicLength.Value == .6
    else:
        assert not panel.test_pending and native._object(refs[0]['object_id']).CharacteristicLength.Value == .4
    if choice == '취소':
        assert panel.refinement.currentData() == refs[0]['object_id'] and panel.local_size.value() == .6
    else:
        assert panel.refinement.currentData() == refs[1]['object_id'] and panel.local_size.value() == .2
        assert panel.local_region.currentData() == second['id']
        assert panel._mesh_fields()[5:] == panel._loaded_mesh_fields[5:]
    assert panel.max_size.value() == 7 and native.mesh.CharacteristicLengthMax.Value == 2
    assert panel._mesh_pending() and len(native.mesh.MeshRegionList) == 2


@pytest.mark.parametrize('late_field', ['local', 'global'])
def test_saved_local_selection_receipt_preserves_late_input_and_exact_original_target(panel, native, late_field):
    first, second, refs = _saved_refinements(panel, native)
    panel.refinement.setCurrentIndex(panel.refinement.findData(refs[0]['object_id']))
    panel.max_size.setValue(7)
    panel.local_size.setValue(.6)
    _choose_draft_dialog('적용 후 선택', '미적용 국부 크기')
    panel.refinement.setCurrentIndex(panel.refinement.findData(refs[1]['object_id']))
    if late_field == 'local':
        panel.local_size.setValue(.8)
    else:
        panel.max_size.setValue(9)
    panel.test_complete()
    assert native._object(refs[0]['object_id']).CharacteristicLength.Value == .6
    assert native._object(refs[1]['object_id']).CharacteristicLength.Value == .2
    assert len(panel.test_calls) == 1 and native.mesh.CharacteristicLengthMax.Value == 2
    if late_field == 'local':
        assert panel.refinement.currentData() == refs[0]['object_id'] and panel.local_size.value() == .8
        assert '새로 수정한 입력' in panel.status.toPlainText()
    else:
        assert panel.refinement.currentData() == refs[1]['object_id'] and panel.max_size.value() == 9
    assert panel._mesh_pending()


def test_saved_local_missing_region_stays_unassigned_until_explicit_repair(panel, native):
    first, second, refs = _saved_refinements(panel, native)
    native.metadata['regions'] = [row for row in native.metadata['regions'] if row['id'] != first['id']]
    panel.refresh()
    before = deepcopy(native.metadata)
    panel.refinement.setCurrentIndex(panel.refinement.findData(refs[0]['object_id']))
    assert panel.local_region.currentData() is None and panel.local_size.value() == .4
    assert '적용 영역을 찾지 못했습니다' in panel.status.toPlainText()
    assert native.metadata == before and not panel.test_calls
    panel.local_region.setCurrentIndex(panel.local_region.findData(second['id']))
    panel.local_size.setValue(.3)
    panel.apply_local_size()
    panel.test_complete()
    assert native._object(refs[0]['object_id']).References == [(native.shape, ['Face2'])]
    assert native._object(refs[0]['object_id']).CharacteristicLength.Value == .3


def test_local_selection_during_command_restores_previous_refinement_without_losing_input(panel, native):
    first, second, refs = _saved_refinements(panel, native)
    panel.refinement.setCurrentIndex(panel.refinement.findData(refs[0]['object_id']))
    panel.local_size.setValue(.6)
    panel.apply_local_size()
    panel.refinement.setCurrentIndex(panel.refinement.findData(refs[1]['object_id']))
    assert panel.refinement.currentData() == refs[0]['object_id'] and panel.local_size.value() == .6
    assert '메시 작업' in panel.status.toPlainText()
    panel.test_complete()
    assert panel.refinement.currentData() == refs[0]['object_id'] and panel.local_size.value() == .6


@pytest.mark.parametrize('changed_target', ['region', 'native'])
def test_saved_local_target_mismatch_requires_explicit_region_reselection(panel, native, changed_target):
    first, second, refs = _saved_refinements(panel, native)
    refinement = native._object(refs[0]['object_id'])
    if changed_target == 'region':
        from apps.desktop_pre.fem_edit import _hash
        native.editor.dispatch('pre.fem.region_set',
            {'region_id': first['id'], 'label': '첫 영역', 'subelements': ['Face2'],
             'expected_target_sha256': _hash(first['target'])},
            {'object_id': native.shape.Name})
    else:
        refinement.References = [(native.shape, ['Face2'])]
    panel.refresh()
    before, references = deepcopy(native.metadata), list(refinement.References)
    panel.refinement.setCurrentIndex(panel.refinement.findData(refs[0]['object_id']))
    assert panel.local_region.currentData() is None and panel.local_size.value() == .4
    assert '현재 형상·면' in panel.status.toPlainText()
    assert native.metadata == before and refinement.References == references
    panel.local_size.setValue(.6)
    with pytest.raises(ValueError, match='적용할 영역을 선택'):
        panel.apply_local_size()
    assert not panel.test_calls and refinement.CharacteristicLength.Value == .4
    panel.local_region.setCurrentIndex(panel.local_region.findData(second['id']))
    panel.apply_local_size()
    panel.test_complete()
    assert refinement.References == [(native.shape, ['Face2'])]
    assert refinement.CharacteristicLength.Value == .6
    assert not native.editor._refinement_errors(native.mesh)


def test_saved_local_valid_selection_does_not_inherit_another_refinement_target_error(panel, native):
    first, second, refs = _saved_refinements(panel, native)
    native._object(refs[0]['object_id']).References = [(native.shape, ['Face2'])]
    panel.refinement.setCurrentIndex(panel.refinement.findData(refs[1]['object_id']))
    assert panel.local_region.currentData() == second['id'] and panel.local_size.value() == .2
    assert native.editor._refinement_errors(native.mesh)  # The invalid sibling still blocks generation.
    assert not panel.test_calls


@pytest.mark.parametrize('choice', ['취소', '버리고 선택'])
def test_direct_mesh_selection_cancel_or_discard_preserves_exact_targets(panel, native, choice):
    other = _second_mesh(native)
    _local_region(panel, native)
    panel.max_size.setValue(7)
    panel.local_size.setValue(.4)
    before = panel._mesh_fields()
    _choose_draft_dialog(choice)
    panel.mesh.setCurrentIndex(panel.mesh.findData(other.Name))
    assert not panel.test_pending and native.mesh.CharacteristicLengthMax.Value == 2
    if choice == '취소':
        assert panel.mesh.currentData() == native.mesh.Name and panel._mesh_fields() == before
    else:
        assert panel.mesh.currentData() == other.Name and panel.max_size.value() == 4
        assert panel.local_size.value() == 1 and panel.local_region.currentData() is None
        assert not panel._mesh_pending()


def test_direct_mesh_selection_apply_submits_global_then_local_to_original_mesh(panel, native):
    other = _second_mesh(native)
    _local_region(panel, native)
    panel.max_size.setValue(7)
    panel.local_size.setValue(.4)
    _choose_draft_dialog('적용 후 선택')
    panel.mesh.setCurrentIndex(panel.mesh.findData(other.Name))
    assert panel.mesh.currentData() == native.mesh.Name
    assert panel.test_calls[-1][0] == 'pre.fem.mesh_settings'
    panel.test_complete()
    assert panel.test_calls[-1][0] == 'pre.fem.mesh_local_size'
    assert panel.mesh.currentData() == native.mesh.Name
    panel.test_complete()
    assert [call[2] for call in panel.test_calls] == [{'object_id': native.mesh.Name}] * 2
    assert native.mesh.CharacteristicLengthMax.Value == 7
    assert native.mesh.MeshRegionList[0].CharacteristicLength.Value == .4
    assert other.CharacteristicLengthMax.Value == 4 and not other.MeshRegionList
    assert panel.mesh.currentData() == other.Name and panel.max_size.value() == 4


def test_direct_mesh_selection_rejects_busy_and_late_edits_stop_automatic_switch(panel, native):
    other = _second_mesh(native)
    panel.refresh()
    panel.max_size.setValue(7)
    _choose_draft_dialog('적용 후 선택')
    panel.mesh.setCurrentIndex(panel.mesh.findData(other.Name))
    panel.max_size.setValue(9)
    panel.mesh.setCurrentIndex(panel.mesh.findData(other.Name))
    assert panel.mesh.currentData() == native.mesh.Name and panel.max_size.value() == 9
    assert '메시 작업' in panel.status.toPlainText()
    panel.test_complete()
    assert native.mesh.CharacteristicLengthMax.Value == 7
    assert panel.mesh.currentData() == native.mesh.Name and panel.max_size.value() == 9
    assert '새로 수정한 입력' in panel.status.toPlainText() and panel._mesh_pending()


def test_partial_apply_failure_retains_original_selection_and_unapplied_local_draft(panel, native):
    other = _second_mesh(native)
    _local_region(panel, native)
    panel.max_size.setValue(7)
    panel.local_size.setValue(.4)
    _choose_draft_dialog('적용 후 선택')
    panel.mesh.setCurrentIndex(panel.mesh.findData(other.Name))
    panel.test_complete()
    operation, arguments, target, callback = panel.test_pending.pop(0)
    assert operation == 'pre.fem.mesh_local_size' and target == {'object_id': native.mesh.Name}
    callback({'status': 'FAILED', 'error': {'message': 'Local region is unresolved'}})
    assert not panel._command_busy and panel.mesh.currentData() == native.mesh.Name
    assert panel.max_size.value() == 7 and panel.local_size.value() == .4
    assert native.mesh.CharacteristicLengthMax.Value == 7 and not native.mesh.MeshRegionList
    assert panel._mesh_pending() and panel.status.toPlainText() == 'Local region is unresolved'


def test_dock_close_show_preserves_draft_and_stops_old_selection_continuation(panel, native, app):
    other = _second_mesh(native)
    _local_region(panel, native)
    window = QtWidgets.QMainWindow()
    dock = QtWidgets.QDockWidget('해석 설정', window)
    dock.setWidget(panel)
    window.addDockWidget(QtCore.Qt.RightDockWidgetArea, dock)
    window.show()
    app.processEvents()
    try:
        panel.max_size.setValue(7)
        panel.local_size.setValue(.4)
        _choose_draft_dialog('적용 후 선택')
        panel.mesh.setCurrentIndex(panel.mesh.findData(other.Name))
        dock.close()
        app.processEvents()
        dock.show()
        app.processEvents()
        panel.test_complete()
        assert not panel.test_pending  # No local apply or implicit switch after close/show.
        assert panel.mesh.currentData() == native.mesh.Name
        assert panel.max_size.value() == 7 and panel.local_size.value() == .4
        assert panel._mesh_pending() and not native.mesh.MeshRegionList
    finally:
        panel.setParent(None)
        window.close()
        window.deleteLater()
        app.processEvents()


@pytest.mark.parametrize('choice', ['취소', '버리고 생성', '적용 후 생성'])
def test_remesh_resolves_draft_before_using_exact_native_settings(panel, native, choice):
    panel.max_size.setValue(7)
    _choose_draft_dialog(choice)
    panel.generate_mesh()
    if choice == '취소':
        assert not panel.test_pending and panel.max_size.value() == 7
        return
    if choice == '적용 후 생성':
        assert panel.test_calls[-1][0] == 'pre.fem.mesh_settings'
        panel.test_complete()
        assert native.mesh.CharacteristicLengthMax.Value == 7
    else:
        assert native.mesh.CharacteristicLengthMax.Value == 2 and panel.max_size.value() == 2
    assert panel.test_calls[-1] == ('pre.fem.mesh_generate', {}, {'object_id': native.mesh.Name})
    _, _, _, callback = panel.test_pending.pop(0)
    callback({'status': 'COMPLETED', 'result': {'state': 'QUEUED', 'history_id': 'retained-test'}})


def test_missing_form_mesh_does_not_rebind_draft_to_first_remaining_mesh(panel, native):
    other = _second_mesh(native)
    panel.max_size.setValue(7)
    native.doc.Objects.remove(native.mesh)
    native.analysis.Group.remove(native.mesh)
    panel.refresh()
    assert panel.mesh.currentIndex() == -1 and panel.max_size.value() == 7
    assert '현재 메시를 찾지 못했습니다' in panel.status.toPlainText()
    _choose_draft_dialog('취소')
    panel.mesh.setCurrentIndex(panel.mesh.findData(other.Name))
    assert panel.mesh.currentIndex() == -1 and panel.max_size.value() == 7
    _choose_draft_dialog('버리고 선택')
    panel.mesh.setCurrentIndex(panel.mesh.findData(other.Name))
    assert panel.mesh.currentData() == other.Name and panel.max_size.value() == 4


def test_document_close_contract_waits_for_apply_and_preserves_cancelled_draft(panel, native):
    accepted, cancelled = [], []
    panel.max_size.setValue(7)
    _choose_draft_dialog('취소')
    panel.request_mesh_close(lambda: accepted.append(True), on_cancelled=lambda: cancelled.append(True))
    assert not accepted and panel._mesh_pending() and cancelled == [True]
    _choose_draft_dialog('적용 후 닫기')
    panel.request_mesh_close(lambda: accepted.append(True))
    assert not accepted and panel.test_calls[-1][2] == {'object_id': native.mesh.Name}
    with pytest.raises(ValueError, match='메시 작업'):
        panel.request_mesh_close(lambda: accepted.append(False))
    panel.test_complete()
    assert accepted == [True] and not panel._mesh_pending()


def test_document_close_failure_notifies_caller_without_erasing_draft(panel, native):
    accepted, cancelled = [], []
    panel.max_size.setValue(7)
    _choose_draft_dialog('적용 후 닫기')
    panel.request_mesh_close(lambda: accepted.append(True), on_cancelled=lambda: cancelled.append(True))
    _, _, _, callback = panel.test_pending.pop(0)
    callback({'status': 'FAILED', 'error': {'message': 'Controlled native failure'}})
    callback({'status': 'FAILED', 'error': {'message': 'Duplicate receipt'}})
    assert not accepted and cancelled == [True]
    assert panel.max_size.value() == 7 and panel._mesh_pending()


def test_late_remesh_apply_receipt_keeps_new_input_without_starting_generation(panel, native):
    panel.max_size.setValue(7)
    _choose_draft_dialog('적용 후 생성')
    panel.generate_mesh()
    panel.local_size.setValue(.6)
    panel.test_complete()
    assert not panel.test_pending and len(panel.test_calls) == 1
    assert native.mesh.CharacteristicLengthMax.Value == 7
    assert panel.local_size.value() == .6 and panel._mesh_pending()


def test_native_meshing_blocks_selection_without_losing_draft(panel, native, monkeypatch):
    other = _second_mesh(native)
    panel.refresh()
    panel.max_size.setValue(7)
    descriptor = native.editor.descriptor
    monkeypatch.setattr(native.editor, 'descriptor', lambda: dict(descriptor(), mesh_busy=True))
    panel.mesh.setCurrentIndex(panel.mesh.findData(other.Name))
    assert panel.mesh.currentData() == native.mesh.Name and panel.max_size.value() == 7
    assert not panel.test_pending and '메시 작업' in panel.status.toPlainText()


def test_old_document_receipt_cannot_continue_switch_or_clean_draft(panel, native):
    other = _second_mesh(native)
    panel.refresh()
    panel.max_size.setValue(7)
    _choose_draft_dialog('적용 후 선택')
    panel.mesh.setCurrentIndex(panel.mesh.findData(other.Name))
    _, _, _, callback = panel.test_pending.pop(0)
    original = native.doc
    native.doc = NS(Name=original.Name, Objects=original.Objects)
    try:
        callback({'status': 'COMPLETED', 'result': {'mesh_id': native.mesh.Name}})
        assert panel.mesh.currentData() == native.mesh.Name and panel._mesh_pending()
        assert 'STALE_SESSION' in panel.status.toPlainText() and not panel.test_pending
    finally:
        native.doc = original


def test_destroyed_panel_ignores_late_mesh_receipt(panel, native, app):
    other_panel = make_panel(QtWidgets, QtCore, native.editor, panel.submit)
    other_panel.timer.stop()
    other_panel.max_size.setValue(7)
    other_panel.apply_mesh_settings()
    _, _, _, callback = panel.test_pending.pop(0)
    other_panel.deleteLater()
    QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
    assert other_panel._disposed
    callback({'status': 'COMPLETED', 'result': {'mesh_id': native.mesh.Name}})
    assert not other_panel._command_busy


def test_keyboard_selection_escape_restores_draft_and_exact_mesh(panel, native, app):
    from PySide6 import QtTest
    other = _second_mesh(native)
    panel.refresh()
    panel.max_size.setValue(7)
    panel.show()
    panel.mesh.setFocus()
    app.processEvents()
    QtCore.QTimer.singleShot(0, lambda: QtTest.QTest.keyClick(
        QtWidgets.QApplication.activeModalWidget(), QtCore.Qt.Key_Escape))
    QtTest.QTest.keyClick(panel.mesh, QtCore.Qt.Key_Down)
    app.processEvents()
    assert panel.mesh.currentData() == native.mesh.Name and panel.max_size.value() == 7
    assert panel.focusWidget() is panel.mesh and not panel.test_pending


def test_confirmation_with_new_input_cannot_discard_the_new_value(panel, native):
    other = _second_mesh(native)
    panel.refresh()
    panel.max_size.setValue(7)
    def changed_then_discard():
        dialog = QtWidgets.QApplication.activeModalWidget()
        panel.max_size.setValue(9)
        next(button for button in dialog.buttons() if button.text() == '버리고 선택').click()
    QtCore.QTimer.singleShot(0, changed_then_discard)
    panel.mesh.setCurrentIndex(panel.mesh.findData(other.Name))
    assert panel.mesh.currentData() == native.mesh.Name and panel.max_size.value() == 9
    assert panel._mesh_pending() and not panel.test_pending
    assert '선택 확인 중' in panel.status.toPlainText()


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
