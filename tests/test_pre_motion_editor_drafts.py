"""Raw assembly editor persistence, isolated from applied native physics."""
from copy import deepcopy
from types import SimpleNamespace as NS

import pytest

from test_pre_motion import setup, qt_panel, native_modules
from apps.desktop_pre.motion import Motion, _hash
from apps.desktop_pre.motion_panel import make_panel
from apps.desktop_pre.connection import Connection


def edit_invalid(panel, setup):
    panel.joint.setCurrentIndex(panel.joint.findData(setup[3]['drives'][0]['joint_id']))
    panel.connector_a.setCurrentIndex(-1); panel.subelement_b.setText('Face99')
    panel.joint_parameters['Distance'][0].setText('1e'); panel._mark_joint_edited()
    panel.time['end'].setText('1e'); panel.tolerance.setText(''); panel._mark_edited()
    panel._item(panel.drives, 0, 2, 'sin(')
    panel._item(panel.traces, 0, 2, '-')
    return panel.editor_snapshot()


def test_invalid_editor_round_trip_without_native_definition_changes(qt_panel):
    app, widget, panel, queued, descriptor, setup = qt_panel
    owner, motion, target, definition = setup
    applied = _hash(owner.metadata['motion']['definition'])
    snapshot = edit_invalid(panel, setup)
    motion.dispatch('pre.motion.save_editor', {'editor': snapshot['editor']}, target)
    assert _hash(owner.metadata['motion']['definition']) == applied
    reopened = Motion(owner); reopened._modules = native_modules()
    fresh = make_panel(panel.QtCore, panel.Q, lambda *args: {'queued': True})
    data = descriptor(); data['session_id'] = 'FreshOwner'; data['motion'] = reopened.descriptor()
    fresh.refresh(data); other = fresh.motion_controller
    assert other.time['end'].text() == '1e' and other.connector_a.currentIndex() == -1
    assert other.subelement_b.text() == 'Face99' and other.joint_parameters['Distance'][0].text() == '1e'
    assert other.drives.item(0, 2).text() == 'sin(' and other.traces.item(0, 2).text() == '-'
    assert other.current_editor() == snapshot['editor'] and not other.has_unsaved_editor()
    assert other._edited and other._joint_edited and reopened.descriptor()['state'] == 'UNCOMPUTED'
    fresh.deleteLater(); app.processEvents()


@pytest.mark.parametrize('operation', ['calculate', 'frame', 'play', 'adopt_pose', 'path'])
def test_saved_draft_blocks_backend_execution(qt_panel, operation):
    app, widget, panel, queued, descriptor, setup = qt_panel
    owner, motion, target, definition = setup
    snapshot = edit_invalid(panel, setup)
    motion.dispatch('pre.motion.save_editor', {'editor': snapshot['editor']}, target)
    with pytest.raises(ValueError, match='편집을 적용하거나 취소'):
        motion.dispatch('pre.motion.'+operation, {}, target)
    assert not any(c[0] == 'generateSimulation' for c in owner.doc.calls)


def test_editor_before_first_motion_configuration_is_saved_and_reopened(qt_panel):
    app, widget, panel, queued, descriptor, setup = qt_panel
    owner, motion, target, definition = setup
    owner.metadata.pop('motion')
    snapshot = edit_invalid(panel, setup)
    before = len(owner.doc.Objects)
    motion.dispatch('pre.motion.save_editor', {'editor': snapshot['editor']}, target)
    assert 'motion' not in owner.metadata and len(owner.doc.Objects) == before
    data = descriptor(); data['session_id'] = 'NewUnconfigured'; widget.refresh(data)
    assert panel.time['end'].text() == '1e' and panel._edited and panel._joint_edited


def test_cancel_saved_drafts_clears_backend_block_and_preserves_applied_definition(qt_panel):
    app, widget, panel, queued, descriptor, setup = qt_panel
    owner, motion, target, definition = setup
    snapshot = edit_invalid(panel, setup)
    motion.dispatch('pre.motion.save_editor', {'editor': snapshot['editor']}, target)
    widget.refresh(descriptor())
    panel._cancel_joint()
    op, args, selected, done = queued[-1]
    assert args['editor']['joint_draft'] is None and args['editor']['definition_draft'] is not None
    done({'result': motion.dispatch(op, args, selected)})
    panel._cancel_definition()
    op, args, selected, done = queued[-1]; done({'result': motion.dispatch(op, args, selected)})
    assert not panel._edited and not panel._joint_edited
    assert owner.metadata['motion']['definition'] == definition
    assert motion.dispatch('pre.motion.calculate', {}, target)['frame_count'] == 3


def test_saved_editor_receipt_keeps_later_raw_edit_dirty(qt_panel):
    app, widget, panel, queued, descriptor, setup = qt_panel
    snapshot = edit_invalid(panel, setup)
    panel.time['end'].setText('2e'); panel._mark_edited()
    panel.accept_saved_editor(snapshot)
    assert panel.time['end'].text() == '2e' and panel.has_unsaved_editor() and panel._edited


def test_editor_states_are_scoped_and_applying_one_draft_keeps_the_other(qt_panel):
    app, widget, panel, queued, descriptor, setup = qt_panel
    owner, motion, target, definition = setup
    snapshot = edit_invalid(panel, setup)
    motion.dispatch('pre.motion.save_editor', {'editor': snapshot['editor']}, target)
    second = motion.dispatch('pre.assembly.create', {'label': 'Other'}, {})
    motion.dispatch('pre.motion.save_editor', {'editor': snapshot['editor']}, second)
    motion.dispatch('pre.motion.configure', {'definition': definition}, target)
    editors = owner.metadata['motion_editors']
    assert editors[target['assembly_id']]['definition_draft'] is None
    assert editors[target['assembly_id']]['joint_draft'] is not None
    assert editors[second['assembly_id']] == snapshot['editor']


def test_view_only_editor_keeps_native_frame_cache_and_execution_enabled(qt_panel):
    app, widget, panel, queued, descriptor, setup = qt_panel
    owner, motion, target, definition = setup
    result = motion.dispatch('pre.motion.calculate', {}, target)
    snapshot = panel.editor_snapshot(); snapshot['editor']['view']['drive_row'] = 0
    motion.dispatch('pre.motion.save_editor', {'editor': snapshot['editor']}, target)
    motion.dispatch('pre.motion.frame', {'calculation_id': result['id'], 'frame': 2}, target)
    assert owner.doc.moving.Placement.Base.x == 9 and not owner.preferences.values


def test_local_disconnected_save_uses_exact_owner_and_never_bypasses_execution(qt_panel):
    app, widget, panel, queued, descriptor, setup = qt_panel
    owner, motion, target, definition = setup
    snapshot = edit_invalid(panel, setup)
    sent, completed = [], []
    owner.document_id = 'Dnative'; owner.session_id = 'Snative'; owner.refresh = lambda: None
    def dispatch(request):
        sent.append(deepcopy(request))
        if request['operation'] == 'document.save': return {'status': 'COMPLETED', 'result': {'status': 'SAVED'}}
        return {'status': 'COMPLETED', 'result': motion.dispatch(request['operation'], request['arguments'], request['target'])}
    owner.dispatch = dispatch
    connection = Connection.__new__(Connection)
    broker = NS(stop=NS(is_set=lambda: True), registered=NS(is_set=lambda: False))
    connection.owners = {owner.doc.Name: (owner, None, broker)}; connection.native_requests = {}
    connection.panels = {owner.doc.Name: {'motion': NS(widget=lambda: widget)}}
    connection.submit_native('document.save', {}, owner=owner, on_done=completed.append)
    assert [r['operation'] for r in sent] == ['pre.motion.save_editor', 'document.save']
    assert sent[0]['arguments']['editor'] == snapshot['editor'] and sent[0]['document_id'] == owner.document_id
    assert sent[1]['expected_generation'] == owner.generation and not panel.has_unsaved_editor()
    with pytest.raises(ValueError, match='연결이 끊겼습니다'):
        connection.submit_native('pre.motion.calculate', {}, target, owner=owner)


def test_valid_joint_and_motion_application_clear_only_their_saved_drafts(qt_panel):
    app, widget, panel, queued, descriptor, setup = qt_panel
    owner, motion, target, definition = setup
    snapshot = edit_invalid(panel, setup)
    motion.dispatch('pre.motion.save_editor', {'editor': snapshot['editor']}, target)
    joint = owner._object(definition['drives'][0]['joint_id'])
    motion.dispatch('pre.joint.update', {'type': 'Revolute', 'connectors': [
        {'object_id': joint.Reference1[0].Name, 'subelement': 'Face1'},
        {'object_id': joint.Reference2[0].Name, 'subelement': ''}], 'parameters': {}},
        {**target, 'joint_id': joint.Name})
    stored = owner.metadata['motion_editors'][target['assembly_id']]
    assert stored['joint_draft'] is None and stored['definition_draft'] is not None
    motion.dispatch('pre.motion.configure', {'definition': definition}, target)
    assert owner.metadata['motion_editors'][target['assembly_id']]['definition_draft'] is None


@pytest.mark.parametrize('fail_cancel', [False, True])
def test_offline_cancel_is_a_metadata_reduction_and_failure_preserves_raw(qt_panel, fail_cancel):
    app, widget, panel, queued, descriptor, setup = qt_panel
    owner, motion, target, definition = setup
    owner.motion = motion
    snapshot = edit_invalid(panel, setup)
    motion.dispatch('pre.motion.save_editor', {'editor': snapshot['editor']}, target)
    widget.refresh(descriptor())
    owner.document_id = 'Dnative'; owner.session_id = 'Snative'; owner.refresh = lambda: None
    calls = []
    def dispatch(request):
        calls.append(request['operation'])
        if fail_cancel: return {'status': 'FAILED', 'error': {'message': 'metadata write failed'}}
        return {'status': 'COMPLETED', 'result': motion.dispatch(request['operation'], request['arguments'], request['target'])}
    owner.dispatch = dispatch
    connection = Connection.__new__(Connection)
    connection.native_requests = {}; connection.owners = {owner.doc.Name: (owner, None,
        NS(stop=NS(is_set=lambda: True), registered=NS(is_set=lambda: False)))}
    connection.panels = {owner.doc.Name: {'motion': NS(widget=lambda: widget)}}
    panel.submit = lambda op, args, target, done: connection.submit_native(op, args, target, done, owner=owner)
    panel._cancel_joint()
    if fail_cancel:
        assert panel.current_editor() == snapshot['editor'] and panel._joint_edited
        assert owner.metadata['motion_editors'][target['assembly_id']] == snapshot['editor']
        assert 'metadata write failed' in panel.status.text()
    else:
        stored = owner.metadata['motion_editors'][target['assembly_id']]
        assert stored['joint_draft'] is None and stored['definition_draft'] == snapshot['editor']['definition_draft']
        panel._cancel_definition()
        assert motion.dispatch('pre.motion.calculate', {}, target)['frame_count'] == 3
        assert calls == ['pre.motion.save_editor', 'pre.motion.save_editor']
    change = deepcopy(snapshot['editor']); change['definition_draft']['time']['end'] = 'another draft'
    with pytest.raises(ValueError, match='명시적 편집 취소'):
        connection.submit_native('pre.motion.save_editor', {'editor': change}, target, owner=owner)


def test_switch_to_another_assembly_restores_raw_references_before_inspection(qt_panel):
    app, widget, panel, queued, descriptor, setup = qt_panel
    owner, motion, target, definition = setup
    editor = edit_invalid(panel, setup)['editor']
    panel._joint_edited = panel._edited = False
    panel._joint_selected(0)
    second = motion.dispatch('pre.assembly.create', {'label': 'Saved draft assembly'}, {})
    editor['joint_draft']['joint_id'] = None; editor['view']['joint_id'] = None
    editor['joint_draft']['connectors'][0] = {'object_id': 'MissingPart', 'subelement': 'Face88'}
    motion.dispatch('pre.motion.save_editor', {'editor': editor}, second)
    widget.refresh(descriptor())
    panel.assembly.setCurrentIndex(panel.assembly.findData(second['assembly_id']))
    assert panel.assembly.currentData() == second['assembly_id']
    assert panel.connector_a.currentData() == 'MissingPart' and panel.subelement_a.text() == 'Face88'
    assert panel.joint_parameters['Distance'][0].text() == '1e' and panel.time['end'].text() == '1e'
    assert panel.current_editor() == editor
    op, args, selected, done = queued[-1]
    done({'result': motion.dispatch(op, args, selected)})
    assert panel.connector_a.currentData() == 'MissingPart' and panel._joint_edited and panel._edited


def test_unconfigured_saved_editor_is_readable_without_manual_inspect(qt_panel):
    app, widget, panel, queued, descriptor, setup = qt_panel
    owner, motion, target, definition = setup
    snapshot = edit_invalid(panel, setup)
    owner.metadata.pop('motion')
    motion.dispatch('pre.motion.save_editor', {'editor': snapshot['editor']}, target)
    data = descriptor(); data['session_id'] = 'ColdEditorOwner'; widget.refresh(data)
    assert panel.current_editor() == snapshot['editor'] and not panel.has_unsaved_editor()
    assert '편집 (저장됨)' in panel.status.text()


@pytest.mark.parametrize('field', ['joint_draft', 'definition_draft'])
def test_new_assembly_cannot_retarget_an_unapplied_editor(qt_panel, field):
    app, widget, panel, queued, descriptor, setup = qt_panel
    owner, motion, target, definition = setup
    edit_invalid(panel, setup)
    panel._joint_edited = field == 'joint_draft'; panel._edited = field == 'definition_draft'
    before = panel.editor_snapshot(); objects = len(owner.doc.Objects); requests = len(queued)
    panel._send('pre.assembly.create', {'label': 'Other'}, target={})
    assert len(queued) == requests and len(owner.doc.Objects) == objects
    assert panel.editor_snapshot() == before
    assert '적용하거나 취소' in panel.status.text()


def test_new_assembly_receipt_keeps_edits_started_during_creation_on_original_assembly(qt_panel):
    app, widget, panel, queued, descriptor, setup = qt_panel
    owner, motion, target, definition = setup
    panel._send('pre.assembly.create', {'label': 'Other'}, target={})
    op, args, selected, done = queued[-1]
    before = edit_invalid(panel, setup)
    result = motion.dispatch(op, args, selected); done({'result': result})
    assert result['assembly_id'] != target['assembly_id']
    assert panel.editor_snapshot() == before
    assert panel.pending_editor()['assembly_id'] == target['assembly_id']


@pytest.mark.parametrize('cancel_field', ['joint_draft', 'definition_draft'])
@pytest.mark.parametrize('edit_cancelled_field', [False, True])
def test_cancel_failure_restores_only_unchanged_cancelled_field(qt_panel, cancel_field, edit_cancelled_field):
    app, widget, panel, queued, descriptor, setup = qt_panel
    owner, motion, target, definition = setup
    before = edit_invalid(panel, setup)['editor']
    motion.dispatch('pre.motion.save_editor', {'editor': before}, target)
    widget.refresh(descriptor())
    (panel._cancel_joint if cancel_field == 'joint_draft' else panel._cancel_definition)()
    op, args, selected, done = queued[-1]
    assert args['editor'][cancel_field] is None
    edit_field = cancel_field if edit_cancelled_field else ('definition_draft' if cancel_field == 'joint_draft' else 'joint_draft')
    if edit_field == 'joint_draft':
        panel.joint_parameters['Distance'][0].setText('NEW'); panel._mark_joint_edited()
    else:
        panel.time['end'].setText('NEW'); panel._mark_edited()
    newest = panel.current_editor()
    done({'status': 'FAILED', 'error': {'message': 'metadata write failed'}})
    expected = deepcopy(newest)
    if not edit_cancelled_field: expected[cancel_field] = before[cancel_field]
    assert panel.current_editor() == expected
    assert panel.pending_editor()['editor'] == expected
    assert owner.metadata['motion_editors'][target['assembly_id']] == before
