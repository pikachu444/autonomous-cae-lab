"""M3 controller integration. Recorded native-output doubles, not a 4R solver.

Actual FreeCAD 1.1.4/Windows acceptance is in the public generator and native_check.
These tests execute the shipped Motion class and existing document/Qt contracts.
"""
from copy import deepcopy
import json
from types import SimpleNamespace as NS

import pytest

from test_pre_motion import setup, qt_panel, Owner, Placement, Vector, Shape, native_modules
from apps.desktop_pre.motion import Motion, _pose
from apps.desktop_pre.motion_history import unpack_poses, pack_poses


def compute(fixture):
    owner, motion, target, _ = fixture
    result = motion.dispatch('pre.motion.calculate', {}, target)
    return owner, motion, target, result


def cold_owner(owner, tmp_path):
    """Exercise the real FCStd metadata JSON property, without claiming FCStd I/O."""
    from apps.desktop_pre import metadata
    document = deepcopy(owner.doc)
    cold = Owner(); cold.doc = document; document.owner = cold
    document.Name = 'NewDocumentName'  # Native reopen may change the in-memory name.
    document.calls = []; document.frames = []
    project = document.addObject('App::DocumentObjectGroup', metadata.NAME)
    project.PropertiesList = [metadata.PROPERTY]
    project.Definition = ''
    metadata.write(document, owner.read_metadata())
    file = tmp_path/'native-property.json'
    file.write_text(project.Definition, encoding='utf-8')
    project.Definition = file.read_text(encoding='utf-8')
    cold.read_metadata = lambda: metadata.read(document)
    cold.write_metadata = lambda value: metadata.write(document, value)
    motion = Motion(cold); motion._modules = native_modules()
    return cold, motion


def test_success_collects_all_native_poses_and_unread_paths_immediately(setup):
    owner, motion, target, result = compute(setup)
    saved = owner.metadata['motion_paths'][result['id']]
    payload = unpack_poses(saved['poses'], 4)
    moving = next(i for i, row in enumerate(payload['bindings']) if row['id'] == owner.doc.moving.Name)
    assert [row[moving][0] for row in payload['frames']] == [0, 4, 9, 12]
    assert payload['frame_times'] == [None, 2., 2.5, 3.]
    assert [row['point'] for row in saved['paths']['Tip']['rows']] == [[1, 2, 0], [5, 2, 0], [10, 2, 0], [13, 2, 0]]
    assert saved['paths']['Tip']['complete']
    assert 'poses' not in owner.metadata['motion']['last_completed']
    assert owner.metadata['motion_attempts'][0]['state'] == 'SUCCEEDED'
    assert owner.doc.moving.Placement.Base.x == 0 and not motion._preview
    assert len([call for call in owner.doc.calls if call[0] == 'generateSimulation']) == 1
    assert len([call for call in owner.doc.calls if call[0] == 'updateForFrame']) == 4
    assert 'poses' not in motion.descriptor()['path_results'][0]
    assert owner.preferences.values == {}


@pytest.mark.parametrize('status', [-1, -6])
def test_unread_success_survives_native_failure_save_and_cold_pose_read(setup, tmp_path, status):
    owner, motion, target, result = compute(setup)
    saved = deepcopy(owner.metadata['motion_paths'][result['id']])
    owner.doc.status = status
    with pytest.raises(RuntimeError): motion.dispatch('pre.motion.calculate', {}, target)
    assert owner.metadata['motion_paths'][result['id']] == saved
    failed = owner.metadata['motion_attempts'][-1]
    assert failed['state'] == 'FAILED' and failed['native_status'] == status
    assert failed['diagnostic']['category'] == 'UNKNOWN'
    assert failed['diagnostic']['cause_joints'] == [] and failed['diagnostic']['failure_time'] is None
    assert failed['previous_success_id'] == result['id']
    motion.before_design_action('save')
    cold, reopened = cold_owner(owner, tmp_path)
    assert reopened.descriptor()['calculation'] is None
    assert reopened.descriptor()['attempts'][-1]['state'] == 'FAILED'
    page = reopened.dispatch('pre.motion.path', {'calculation_id': result['id'], 'trace_id': 'Tip', 'start': 0, 'count': 4}, target)
    assert page['rows'] == saved['paths']['Tip']['rows']
    frame = reopened.dispatch('pre.motion.frame', {'calculation_id': result['id'], 'frame': 2}, target)
    assert frame['retained'] and frame['time'] == 2.5
    assert cold.doc.moving.Placement.Base.x == 9
    assert not cold.doc.calls  # No native generate, updateForFrame or recompute.
    reopened.dispatch('pre.motion.stop', {}, target)
    assert cold.doc.moving.Placement.Base.x == 0
    assert cold.read_metadata()['motion_paths'][result['id']] == saved


def test_failure_repair_new_success_never_overwrites_old_attempt_or_paths(setup):
    owner, motion, target, first = compute(setup)
    old = deepcopy(owner.metadata['motion_paths'][first['id']])
    owner.doc.status = -1
    with pytest.raises(RuntimeError): motion.dispatch('pre.motion.calculate', {}, target)
    failed = deepcopy(owner.metadata['motion_attempts'][-1])
    owner.doc.status = 0
    owner.doc.frames = [Placement(Vector(x)) for x in (0, 40, 90, 120)]
    newer = motion.dispatch('pre.motion.calculate', {}, target)
    assert first['id'] != newer['id']
    assert owner.metadata['motion_paths'][first['id']] == old
    assert owner.metadata['motion_attempts'][1] == failed
    assert [row['state'] for row in owner.metadata['motion_attempts']] == ['SUCCEEDED', 'FAILED', 'SUCCEEDED']
    assert owner.metadata['motion']['last_completed']['id'] == newer['id']
    motion.dispatch('pre.motion.frame', {'calculation_id': first['id'], 'frame': 3}, target)
    assert owner.doc.moving.Placement.Base.x == 12
    motion.dispatch('pre.motion.stop', {}, target)
    motion.dispatch('pre.motion.frame', {'calculation_id': newer['id'], 'frame': 3}, target)
    assert owner.doc.moving.Placement.Base.x == 120


def test_capture_failure_is_not_native_failure_and_cannot_publish_partial_curve(setup):
    owner, motion, target, first = compute(setup)
    old = deepcopy(owner.metadata['motion_paths'])
    owner.doc.frame_error = 2
    with pytest.raises(RuntimeError, match='native frame failure'):
        motion.dispatch('pre.motion.calculate', {}, target)
    failed = owner.metadata['motion_attempts'][-1]
    assert failed['native_status'] == 0 and failed['stage'] == 'CAPTURE'
    assert failed['capture_frame'] == 2 and failed['diagnostic']['failure_time'] is None
    assert owner.metadata['motion_paths'] == old
    assert owner.metadata['motion']['last_completed']['id'] == first['id']
    assert owner.doc.moving.Placement.Base.x == 0


def test_result_publish_failure_keeps_old_success_and_records_storage_stage(setup, monkeypatch):
    owner, motion, target, first = compute(setup)
    before = deepcopy(owner.metadata['motion_paths'])
    write = owner.write_metadata
    def reject_new(value):
        if len(value.get('motion_paths', {})) > len(before): raise OSError('retained storage full')
        write(value)
    monkeypatch.setattr(owner, 'write_metadata', reject_new)
    with pytest.raises(OSError, match='storage full'): motion.dispatch('pre.motion.calculate', {}, target)
    assert owner.metadata['motion_paths'] == before
    assert owner.metadata['motion']['last_completed']['id'] == first['id']
    failed = owner.metadata['motion_attempts'][-1]
    assert failed['state'] == 'FAILED' and failed['stage'] == 'STORE' and 'result_id' not in failed
    assert failed['native_status'] == 0
    assert owner.doc.moving.Placement.Base.x == 0 and owner.preferences.values == {}


def test_duplicate_drive_names_exact_input_rows_without_native_execution(setup):
    owner, motion, target, first = compute(setup)
    owner.metadata['motion']['definition']['drives'].append(deepcopy(setup[3]['drives'][0]))
    before = len([call for call in owner.doc.calls if call[0] == 'generateSimulation'])
    with pytest.raises(ValueError, match='중복'): motion.dispatch('pre.motion.calculate', {}, target)
    failed = owner.metadata['motion_attempts'][-1]
    assert failed['diagnostic']['category'] == 'INPUT'
    assert [row['row'] for row in failed['diagnostic']['input_rows']] == [0, 1]
    assert failed['native_status'] is None
    assert failed['diagnostic']['time_status'] == 'NOT_EXECUTED'
    assert len([call for call in owner.doc.calls if call[0] == 'generateSimulation']) == before
    assert owner.metadata['motion']['last_completed']['id'] == first['id']


def test_native_motion_retarget_is_not_hidden_by_equal_formula(setup):
    owner, motion, target, first = compute(setup)
    simulation = owner._object(owner.metadata['motion']['simulation_id'])
    simulation.Group[0].Joint = (owner.doc.moving, [])
    with pytest.raises(ValueError, match='native 운동식'):
        motion.dispatch('pre.motion.calculate', {}, target)
    assert owner.metadata['motion_attempts'][-1]['native_status'] is None
    assert owner.metadata['motion']['last_completed']['id'] == first['id']


def test_replay_restores_current_design_not_old_design_or_joint_draft(setup):
    owner, motion, target, first = compute(setup)
    motion.before_design_action('edit')
    owner.doc.moving.Placement = Placement(Vector(37))
    joint = owner._object(setup[3]['drives'][0]['joint_id'])
    joint.Placement1 = Placement(Vector(8))
    before_joint = _pose(joint.Placement1)
    owner.generation += 1
    editor = {'view': {'joint_id': joint.Name, 'drive_row': 0, 'trace_row': 0},
              'joint_draft': None, 'definition_draft': None,
              'result_view': {'calculation_id': first['id'], 'frame': 2}}
    motion.dispatch('pre.motion.save_editor', {'editor': editor}, target)
    motion.dispatch('pre.motion.frame', {'calculation_id': first['id'], 'frame': 2}, target)
    assert owner.doc.moving.Placement.Base.x == 9 and _pose(joint.Placement1) == before_joint
    with pytest.raises(ValueError, match='읽기 전용'):
        motion.dispatch('pre.motion.adopt_pose', {'calculation_id': first['id'], 'frame': 2}, target)
    motion.before_design_action('save')
    assert owner.doc.moving.Placement.Base.x == 37 and _pose(joint.Placement1) == before_joint
    assert owner.metadata['motion_editors'][target['assembly_id']] == editor


def test_paths_do_not_read_new_native_cache_and_small_page_does_not_truncate_full_result(setup):
    owner, motion, target, first = compute(setup)
    count = len(owner.doc.calls)
    owner.doc.frames = []
    page = motion.dispatch('pre.motion.path', {'calculation_id': first['id'], 'trace_id': 'Tip', 'start': 1, 'count': 1}, target)
    assert [row['frame'] for row in page['rows']] == [1] and len(owner.doc.calls) == count
    assert len(owner.metadata['motion_paths'][first['id']]['paths']['Tip']['rows']) == 4
    motion.before_design_action('save')
    assert len(owner.metadata['motion_paths'][first['id']]['paths']['Tip']['rows']) == 4


@pytest.mark.parametrize('change', ['missing', 'geometry', 'reparent'])
def test_replay_refuses_wrong_occurrence_without_falling_back_but_path_stays_readable(setup, change):
    owner, motion, target, first = compute(setup)
    motion.before_design_action('edit')
    moving = owner.doc.moving; source = moving.getLinkedObject(); source_before = _pose(source.Placement)
    if change == 'missing': owner.doc.removeObject(moving.Name)
    elif change == 'geometry': source.Shape.brep = 'different CAD'
    else:
        root = owner._object(target['assembly_id'])
        inner = root.newObject('App::Part', 'MovedTo')
        root.Group.remove(moving); inner.Group.append(moving)
    with pytest.raises(ValueError):
        motion.dispatch('pre.motion.frame', {'calculation_id': first['id'], 'frame': 2}, target)
    assert _pose(source.Placement) == source_before
    page = motion.dispatch('pre.motion.path', {'calculation_id': first['id'], 'trace_id': 'Tip', 'start': 0, 'count': 4}, target)
    assert [row['point'][0] for row in page['rows']] == [1, 5, 10, 13]


@pytest.mark.parametrize('damage', ['digest', 'size', 'count', 'time', 'quaternion'])
def test_corrupted_pose_payload_never_moves_design(setup, damage):
    owner, motion, target, first = compute(setup)
    motion.before_design_action('save')
    result = owner.metadata['motion_paths'][first['id']]
    if damage == 'digest': result['poses']['sha256'] = '0'*64
    elif damage == 'size': result['poses']['raw_bytes'] = 1
    elif damage == 'count': result['frame_count'] += 1
    elif damage == 'time': result['frame_times'][1] = 33.
    else:
        payload = unpack_poses(result['poses'], 4)
        payload['frames'][2][1][3:] = [0., 0., 0., 2.]
        with pytest.raises(ValueError, match='회전'): pack_poses(payload, 4)
        return
    with pytest.raises(ValueError): motion.dispatch('pre.motion.frame', {'calculation_id': first['id'], 'frame': 2}, target)
    assert owner.doc.moving.Placement.Base.x == 0


def test_no_trace_still_preserves_pose_and_frame_selection_on_cold_reopen(setup, tmp_path):
    owner, motion, target, definition = setup
    definition = deepcopy(definition); definition['traces'] = []
    motion.dispatch('pre.motion.configure', {'definition': definition}, target)
    owner.doc.frames = [Placement(Vector(i)) for i in (0, 4, 9, 12)]
    first = motion.dispatch('pre.motion.calculate', {}, target)
    editor = {'view': {'joint_id': None, 'drive_row': -1, 'trace_row': -1},
              'joint_draft': None, 'definition_draft': None,
              'result_view': {'calculation_id': first['id'], 'frame': 3}}
    motion.dispatch('pre.motion.save_editor', {'editor': editor}, target)
    motion.before_design_action('save')
    cold, reopened = cold_owner(owner, tmp_path)
    assert reopened.descriptor()['editors'][target['assembly_id']]['result_view'] == editor['result_view']
    assert reopened.descriptor()['path_results'][0]['replay_available']
    reopened.dispatch('pre.motion.frame', editor['result_view'], target)
    assert cold.doc.moving.Placement.Base.x == 12 and not cold.doc.calls


def test_native_nonfinite_output_and_archive_budget_failure_do_not_replace_success(setup, monkeypatch):
    owner, motion, target, first = compute(setup)
    import apps.desktop_pre.motion_history as history
    monkeypatch.setattr(history, 'MAX_RAW_BYTES', 8)
    with pytest.raises(ValueError, match='크기'): motion.dispatch('pre.motion.calculate', {}, target)
    assert owner.metadata['motion']['last_completed']['id'] == first['id']
    monkeypatch.undo()
    owner.doc.frames[2] = Placement(Vector(float('nan')))
    with pytest.raises(ValueError): motion.dispatch('pre.motion.calculate', {}, target)
    assert owner.metadata['motion']['last_completed']['id'] == first['id']
    assert owner.doc.moving.Placement.Base.x == 0


def test_retained_playback_timer_uses_saved_fps_without_generate_or_update(setup, tmp_path):
    owner, motion, target, first = compute(setup)
    motion.before_design_action('save')
    cold, reopened = cold_owner(owner, tmp_path)
    reopened.dispatch('pre.motion.play', {'calculation_id': first['id'], 'direction': 1}, target)
    assert reopened._timer.interval == 50
    for i in range(5): reopened._timer.callback()
    assert reopened._state == 'COMPLETED' and cold.doc.moving.Placement.Base.x == 0
    assert not cold.doc.calls


def test_invalid_draft_retains_previous_path_projection_after_failure(setup, tmp_path):
    owner, motion, target, first = compute(setup)
    owner.doc.status = -1
    with pytest.raises(RuntimeError): motion.dispatch('pre.motion.calculate', {}, target)
    editor = {'view': {'joint_id': None, 'drive_row': 0, 'trace_row': 0},
        'joint_draft': None, 'definition_draft': {'time': {'start': '0', 'end': '1e', 'step': '.1'},
        'fps': 20, 'tolerance': '1e-6', 'drives': [], 'traces': []},
        'path_view': {'calculation_id': first['id'], 'trace_id': 'Tip', 'frame': 2, 'projection': 'xy'},
        'result_view': {'calculation_id': first['id'], 'frame': 2}}
    motion.dispatch('pre.motion.save_editor', {'editor': editor}, target)
    motion.before_design_action('save')
    cold, reopened = cold_owner(owner, tmp_path)
    assert reopened.descriptor()['editors'][target['assembly_id']] == editor
    with pytest.raises(ValueError, match='편집'):
        reopened.dispatch('pre.motion.frame', editor['result_view'], target)
    assert reopened._replay is None and reopened._calculation is None
    assert cold.doc.moving.Placement.Base.x == 0
    page = reopened.dispatch('pre.motion.path', {'calculation_id': first['id'], 'trace_id': 'Tip',
        'start': 0, 'count': 4}, target)
    assert [row['point'][0] for row in page['rows']] == [1, 5, 10, 13]
    with pytest.raises(ValueError, match='편집'): reopened.dispatch('pre.motion.calculate', {}, target)
    reopened.before_design_action('save')
    assert cold.doc.moving.Placement.Base.x == 0


def test_qt_failure_refresh_keeps_unread_result_frame_and_path_selection(qt_panel):
    app, widget, panel, queued, descriptor, fixture = qt_panel
    owner, motion, target, first = compute(fixture)
    widget.refresh(descriptor()); panel.frame.setValue(2)
    panel.path_browser.table.selectRow(2); panel.path_browser.mode.setCurrentIndex(1)
    selection = panel.path_browser.current_view()
    owner.doc.status = -1
    panel._send('pre.motion.calculate', {})
    op, args, target, done = queued[-1]
    with pytest.raises(RuntimeError) as error: motion.dispatch(op, args, target)
    done({'status': 'FAILED', 'error': {'message': str(error.value)}})
    assert panel.frame.maximum() == 3 and panel.frame.value() == 2
    assert panel.path_browser.current_view() == selection
    assert panel.attempt_table.item(panel.attempt_table.rowCount()-1, 2).text() == '실패'
    assert panel.path_browser.pose_button.isEnabled()
    assert '보존' in panel.status.text()


def test_qt_cold_result_frame_selection_and_save_hook_are_existing_commands(qt_panel, tmp_path):
    app, widget, panel, queued, descriptor, fixture = qt_panel
    owner, motion, target, first = compute(fixture)
    widget.refresh(descriptor()); panel.frame.setValue(3)
    editor = panel.current_editor()
    motion.dispatch('pre.motion.save_editor', {'editor': editor}, target)
    motion.before_design_action('save')
    cold, reopened = cold_owner(owner, tmp_path)
    def read(): return {'id': 'Dnative', 'session_id': 'ColdM3', 'motion': reopened.descriptor(), 'objects': []}
    panel.read = read; widget.refresh(read())
    assert panel.frame.value() == 3 and panel._calculation_id() == first['id']
    assert panel.path_browser.pose_button.isEnabled()
    panel._send('pre.motion.frame', panel._frame_args())
    op, args, selected, done = queued[-1]
    assert op == 'pre.motion.frame'
    done({'result': reopened.dispatch(op, args, selected)})
    assert cold.doc.moving.Placement.Base.x == 12 and not cold.doc.calls


def test_qt_spinner_selection_is_not_reset_by_unchanged_preview_heartbeat(qt_panel):
    app, widget, panel, queued, descriptor, fixture = qt_panel
    owner, motion, target, first = compute(fixture)
    motion.dispatch('pre.motion.frame', {'calculation_id': first['id'], 'frame': 1}, target)
    widget.refresh(descriptor()); assert panel.frame.value() == 1
    panel.frame.setValue(3); widget.refresh(descriptor())
    assert panel.frame.value() == 3  # Selecting a row is not applying that pose.
    assert owner.doc.moving.Placement.Base.x == 4


def test_native_brep_read_normalization_is_copy_only_and_still_rejects_geometry_edit(setup):
    owner, motion, target, _ = setup
    class StoredShape(Shape):
        def importBrepFromString(self, text): self.brep = text.replace('flags-before', 'flags-after')
    source = owner.doc.moving.getLinkedObject()
    source.Shape = StoredShape('geometry-A flags-before')
    first = motion.dispatch('pre.motion.calculate', {}, target)
    assert source.Shape.brep == 'geometry-A flags-before'  # no CAD healing/edit
    motion.before_design_action('save')
    source.Shape = StoredShape('geometry-A flags-after')  # native read representation
    motion.dispatch('pre.motion.frame', {'calculation_id': first['id'], 'frame': 2}, target)
    assert owner.doc.moving.Placement.Base.x == 9
    motion.before_design_action('edit')
    source.Shape = StoredShape('geometry-B flags-after')
    with pytest.raises(ValueError, match='형상'):
        motion.dispatch('pre.motion.frame', {'calculation_id': first['id'], 'frame': 2}, target)


def test_replay_preserves_recorded_world_pose_after_outer_parent_rotates_and_restores_current_design(setup, monkeypatch):
    """Rigid coordinate transforms of recorded output only, not a motion solver."""
    import math
    from test_pre_motion import Rotation
    owner, motion, target, _ = setup
    class RigidPlacement(Placement):
        def multVec(self, point):
            qx, qy, qz, qw = self.Rotation.Q
            # Quaternion-vector rotation; this test uses rotations about z.
            angle = 2*math.atan2(qz, qw)
            return Vector(self.Base.x + math.cos(angle)*point.x - math.sin(angle)*point.y,
                          self.Base.y + math.sin(angle)*point.x + math.cos(angle)*point.y,
                          self.Base.z + point.z)
        def multiply(self, other):
            a, b = self.Rotation.Q, other.Rotation.Q
            rotation = Rotation(0, 0, a[3]*b[2]+a[2]*b[3], a[3]*b[3]-a[2]*b[2])
            return RigidPlacement(self.multVec(other.Base), rotation)
        def inverse(self):
            q = self.Rotation.Q
            rotation = Rotation(-q[0], -q[1], -q[2], q[3])
            inv = RigidPlacement(Vector(), rotation)
            inv.Base = inv.multVec(Vector(-self.Base.x, -self.Base.y, -self.Base.z))
            return inv
    owner.App.Placement = RigidPlacement
    root = owner._object(target['assembly_id'])
    parent = owner.doc.addObject('App::Part', 'OuterParent')
    parent.Placement = RigidPlacement(Vector(10, 20), Rotation(0, 0, math.sin(.2), math.cos(.2)))
    root.Placement = RigidPlacement(Vector(3, 4)); root.Parents = [(parent, root.Name+'.')]
    parent.getSubObject = lambda path, kind: root
    def world(assembly, obj):
        root_world = parent.Placement.multiply(root.Placement)
        return root_world if obj is root else root_world.multiply(obj.Placement)
    monkeypatch.setattr('apps.desktop_pre.motion.world_placement', world)
    first = motion.dispatch('pre.motion.calculate', {}, target)
    saved_point = owner.metadata['motion_paths'][first['id']]['paths']['Tip']['rows'][2]['point']
    motion.before_design_action('save')
    parent.Placement = RigidPlacement(Vector(-30, 7), Rotation(0, 0, math.sin(.7), math.cos(.7)))
    current_parent, current_design = _pose(parent.Placement), _pose(root.Placement)
    calls = len(owner.doc.calls)
    motion.dispatch('pre.motion.frame', {'calculation_id': first['id'], 'frame': 2}, target)
    point = world(root, owner.doc.moving).multVec(Vector(1, 2))
    assert [point.x, point.y, point.z] == pytest.approx(saved_point, abs=1e-12, rel=0)
    assert _pose(parent.Placement) == current_parent and len(owner.doc.calls) == calls
    assert motion.descriptor()['path_results'][0]['source_status'] == 'STALE'
    motion.before_design_action('restore')
    assert _pose(root.Placement) == current_design and _pose(parent.Placement) == current_parent


def test_native_tolerance_change_requires_explicit_reapply_not_silent_looser_run(setup):
    owner, motion, target, first = compute(setup)
    native = owner._object(owner.metadata['motion']['simulation_id'])
    native.fGlobalErrorTolerance = 1e-3
    count = len([call for call in owner.doc.calls if call[0] == 'generateSimulation'])
    with pytest.raises(ValueError, match='허용값'):
        motion.dispatch('pre.motion.calculate', {}, target)
    assert native.fGlobalErrorTolerance == 1e-3  # Human edit is not silently overwritten.
    assert len([call for call in owner.doc.calls if call[0] == 'generateSimulation']) == count
    assert owner.metadata['motion']['last_completed']['id'] == first['id']
    assert owner.metadata['motion_attempts'][-1]['native_status'] is None
