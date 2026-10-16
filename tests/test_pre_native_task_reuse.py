"""Native-shaped owner/Qt checks, not acceptance of a live FreeCAD Task dialog."""
from copy import deepcopy
from types import SimpleNamespace as NS
import pytest
from test_pre_fem_edit import native, submit, repair_conditions, region, Quantity, Object
from test_pre_fem_panel_ui import panel, app, QtWidgets


def test_native_targets_require_explicit_adoption_and_preserve_native_fields(native):
    repair_conditions(native)
    old_regions = deepcopy(native.metadata['regions'])
    native.force.References = [(native.shape, ['Face1', 'Face2'])]
    native.force.Direction = (native.shape, ['Edge1'])
    native.force.Force, native.force.Reversed, native.force.EnableAmplitude = Quantity('23 N'), True, True
    assert native.editor._condition_errors(native.force, native.editor._metadata())
    result = submit(native, 'condition_repair', {'use_native_references': True}, native.force)
    assert result['region_id'] is None and result['direction_region_id'] is None
    assert native.metadata['regions'] == old_regions
    assert not native.editor._condition_errors(native.force, native.editor._metadata())
    assert native.force.Force.Value == 23 and native.force.Reversed and native.force.EnableAmplitude
    assert native.force.References == [(native.shape, ['Face1', 'Face2'])]


def test_current_exact_named_regions_are_retained_and_value_only_edit_needs_no_adoption(native):
    repair_conditions(native)
    before = deepcopy(native.metadata)
    native.force.Force = Quantity('24 N'); native.force.Reversed = True
    assert not native.editor._condition_errors(native.force, native.editor._metadata())
    assert native.metadata == before
    result = submit(native, 'condition_repair', {'use_native_references': True}, native.force)
    assert result['region_id'] == before['conditions'][1]['region_id']


@pytest.mark.parametrize('problem', ['active_task', 'geometry', 'empty', 'edge_reference', 'foreign', 'direction', 'boolean'])
def test_native_confirmation_does_not_bypass_invalid_target_or_active_task(native, problem):
    repair_conditions(native)
    before = deepcopy(native.metadata)
    args = {'use_native_references': True}
    if problem == 'active_task': native.edit = native.force.Name
    elif problem == 'geometry': native.shape.Shape.brep = 'changed CAD'
    elif problem == 'empty': native.force.References = []
    elif problem == 'edge_reference': native.force.References = [(native.shape, ['Edge1'])]
    elif problem == 'foreign':
        foreign = NS(Name=native.shape.Name, Document=NS(), Shape=native.shape.Shape)
        native.force.References = [(foreign, ['Face1'])]
    elif problem == 'direction': native.force.Direction = (native.shape, ['Face1'])
    elif problem == 'boolean': args['use_native_references'] = 1
    with pytest.raises(ValueError): submit(native, 'condition_repair', args, native.force)
    assert native.metadata == before


def test_task_open_and_cancel_leave_metadata_invariant_and_no_duplicate_forms(panel, native):
    repair_conditions(native); panel.refresh()
    before = deepcopy(native.metadata)
    panel.condition.setCurrentIndex(panel.condition.findData(native.force.Name))
    panel.findChild(QtWidgets.QPushButton, 'femEditCondition').click(); panel.test_complete()
    assert native.edit == native.force.Name and native.metadata == before
    native.edit = None  # Native reject restores its transaction; owner must not adopt anything.
    panel.poll()
    assert native.metadata == before and panel.confirm_condition_button.isHidden()
    assert panel.findChild(QtWidgets.QDoubleSpinBox, 'femForce') is None
    assert panel.findChild(QtWidgets.QDoubleSpinBox, 'femYoungModulus') is None
    native.force.References = [(native.shape, ['Face1'])]  # Native accepted edit.
    panel.poll(); assert not panel.confirm_condition_button.isHidden()
    panel.confirm_condition(); panel.test_complete()
    assert not native.editor._condition_errors(native.force, native.editor._metadata())
    assert panel.confirm_condition_button.isHidden()


def test_new_force_is_created_once_then_edited_in_its_native_task(panel, native):
    selected = region(native)
    panel.refresh(); panel.new_condition.setCurrentIndex(panel.new_condition.findData('Force'))
    panel.condition_region.setCurrentIndex(panel.condition_region.findData(selected['id']))
    panel.force.setValue(37)
    panel.create_condition(); panel.test_complete()
    identifier = panel.test_calls[-1][2]['object_id']
    assert panel.test_calls[-1][0] == 'pre.fem.task_edit'
    created = native._object(identifier)
    assert created in native.analysis.Group and created.Force.Value == 37
    panel.test_complete()
    assert native.edit == identifier and panel.condition.currentData() == identifier


def test_late_local_edit_does_not_open_created_task_or_discard_user_input(panel, native):
    selected = region(native)
    panel.refresh(); panel.new_condition.setCurrentIndex(panel.new_condition.findData('Force'))
    panel.condition_region.setCurrentIndex(panel.condition_region.findData(selected['id']))
    panel.force.setValue(37); panel.create_condition()
    panel.region_label.setText('새 영역 이름')
    panel.test_complete()
    assert native.edit is None and not panel.test_pending
    assert panel.region_label.text() == '새 영역 이름'
    assert panel.test_calls[-1][0] == 'pre.fem.condition_set'


def test_stale_force_edge_direction_can_be_explicitly_repaired_after_cad_change(panel, native):
    repair_conditions(native)
    native.force.Direction = (native.shape, ['Edge1'])
    submit(native, 'condition_repair', {'use_native_references': True}, native.force)
    native.shape.Shape.brep = 'edited CAD'
    native.shape.Shape.Edges[0].brep = 'edited edge'
    selected = region(native, 'Edge1')
    panel.refresh(); panel.condition.setCurrentIndex(panel.condition.findData(native.force.Name))
    assert not panel.direction_region.isHidden()
    assert panel.direction_region.currentData() == '__keep'
    panel.direction_region.setCurrentIndex(panel.direction_region.findData(selected['id']))
    native.selection = [NS(Object=native.shape, SubElementNames=['Face2'])]
    panel.repair_condition(); panel.test_complete(); panel.test_complete()
    assert not native.editor._condition_errors(native.force, native.editor._metadata())
    assert native.force.Direction == (native.shape, ['Edge1'])
    assert panel.direction_region.isHidden()


def test_hidden_old_direction_choice_cannot_override_later_native_direction_edit(panel, native):
    repair_conditions(native)
    edge = region(native, 'Edge1')
    native.force.Direction = (native.shape, ['Edge1'])
    panel.refresh(); panel.condition.setCurrentIndex(panel.condition.findData(native.force.Name))
    panel.direction_region.setCurrentIndex(panel.direction_region.findData(edge['id']))
    native.selection = [NS(Object=native.shape, SubElementNames=['Face2'])]
    panel.repair_condition(); panel.test_complete(); panel.test_complete()
    assert panel.direction_region.isHidden() and panel.direction_region.currentData() == '__keep'
    native.force.Direction = None
    panel.poll(); panel.confirm_condition(); panel.test_complete()
    native.selection = [NS(Object=native.shape, SubElementNames=['Face1'])]
    panel.repair_condition(); panel.test_complete()
    assert 'direction_region_id' not in panel.test_calls[-1][1]
    panel.test_complete()
    assert native.force.Direction is None
