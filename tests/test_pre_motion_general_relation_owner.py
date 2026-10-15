"""Real owner/controller code with API-shaped native doubles, NOT FreeCAD runs."""
from copy import deepcopy
import json

import pytest

from test_pre_motion import setup, native_modules
from test_pre_motion_closed_loop import cold_owner
from apps.desktop_pre.motion import Motion, _hash
from apps.desktop_pre.motion_history import MotionInputError, check_closed_motion, unpack_poses
from apps.desktop_pre.motion_occurrence import hierarchy
from apps.desktop_pre.motion_relation import relation_values


def independent_definition(fixture):
    owner, motion, target, baseline = fixture
    definition = deepcopy(baseline)
    definition['time'] = {'start': 0., 'end': 1., 'step': .25, 'unit': 's'}
    definition['drives'][0].update(name='입력 A', formula='30*time', unit='deg')
    A = owner._object(definition['drives'][0]['joint_id'])
    ground = A.Reference1[0]
    assembly = owner._object(target['assembly_id'])
    created = []
    for label in ('입력 B', '출력 C'):
        moving = assembly.newObject('App::Link', 'Separate')
        moving.setLink(owner.doc.moving.getLinkedObject())
        jid = motion.dispatch('pre.joint.create', {'type': 'Revolute', 'connectors': [
            {'object_id': ground.Name, 'subelement': ''}, {'object_id': moving.Name, 'subelement': ''}]}, target)['joint_id']
        owner._object(jid).Label = label
        created.append(jid)
    B, C = created
    definition['drives'].append({'name': '입력 B', 'joint_id': B, 'type': 'Angular', 'formula': '10*time', 'unit': 'deg'})
    paths = hierarchy(assembly)
    relation = {'expression': 'amplitude*sin(A)+B', 'sources': [
        {'alias': alias, 'joint_id': jid, 'type': 'Angular', 'path': paths[jid][0]['path'], 'unit': 'deg'}
        for alias, jid in (('A', A.Name), ('B', B))],
        'constants': [{'name': 'amplitude', 'value': 30., 'unit': 'deg'}]}
    definition['drives'].append({'name': '출력 C', 'joint_id': C, 'type': 'Angular', 'formula': '', 'unit': 'deg', 'relation': relation})
    return owner, motion, target, definition


def raw_editor(definition):
    rows = deepcopy(definition['drives'])
    for row in rows:
        if row.get('relation') is not None:
            row['relation'] = relation_values(row['relation'], raw=True)
    return {'view': {'joint_id': rows[2]['joint_id'], 'drive_row': 2, 'trace_row': 0},
        'joint_draft': None, 'definition_draft': {
            'time': {k: str(definition['time'][k]) for k in ('start', 'end', 'step')},
            'fps': definition['fps'], 'tolerance': str(definition['native_error_tolerance']), 'drives': rows,
            'traces': [{'id': t['id'], 'occurrence_id': t['occurrence_id'], 'point': [str(x) for x in t['point']]}
                       for t in definition['traces']]},
        'relation_view': {'source_row': 1, 'constant_row': 0}}


def test_configure_persists_relation_not_expanded_native_no_execution(setup):
    owner, motion, target, definition = independent_definition(setup)
    before = len([c for c in owner.doc.calls if c[0] == 'generateSimulation'])
    original = deepcopy(definition)
    reply = motion.dispatch('pre.motion.configure', {'definition': definition}, target)
    assert reply['executed'] is False
    assert owner.metadata['motion']['definition'] == original == definition
    simulation = owner._object(reply['simulation_id'])
    assert 'sin(' in simulation.Group[2].Formula and 'amplitude' not in simulation.Group[2].Formula
    assert _hash(motion._native_definition(simulation)) != _hash(definition)
    assert len([c for c in owner.doc.calls if c[0] == 'generateSimulation']) == before
    assert motion.dispatch('pre.motion.inspect', {}, target)['joints'][1]['path']


def test_actual_editor_save_blocks_candidate_selection_before_any_geometry_read(setup, monkeypatch):
    from apps.desktop_pre.assembly_pose_geometry import select_frame
    owner, motion, target, definition = independent_definition(setup)
    owner.motion = motion
    motion.dispatch('pre.motion.configure', {'definition': definition}, target)
    editor = raw_editor(definition)
    editor['definition_draft']['drives'][2]['relation']['constants'][0]['value'] = '1e'
    motion.dispatch('pre.motion.save_editor', {'editor': editor}, target)
    calls = []
    def result_read(*args):
        calls.append(args)
        raise LookupError('candidate reached saved geometry admission')
    monkeypatch.setattr(motion, '_saved_result', result_read)
    with pytest.raises(ValueError, match='편집을 적용하거나 취소'):
        select_frame(owner, target['assembly_id'], 'Kretained', 2)
    assert not calls
    motion.dispatch('pre.motion.configure', {'definition': definition}, target)
    with pytest.raises(LookupError, match='saved geometry admission'):
        select_frame(owner, target['assembly_id'], 'Kretained', 2)
    assert len(calls) == 1


def test_retained_page_view_cannot_rewrite_original_record_on_next_configure(setup):
    owner, motion, target, definition = setup
    result = motion.dispatch('pre.motion.calculate', {}, target)
    before = deepcopy(owner.read_metadata()['motion_paths'][result['id']])
    page = motion.dispatch('pre.motion.path', {'calculation_id': result['id'], 'trace_id': 'Tip',
        'start': 1, 'count': 1}, target)
    assert len(page['rows']) == 1 and page['rows'][0]['frame'] == 1
    assert motion.descriptor()['path'] == page  # Current UI still shows its selected page.
    assert owner.read_metadata()['motion_paths'][result['id']] == before
    motion.dispatch('pre.motion.configure', {'definition': definition}, target)
    assert owner.read_metadata()['motion_paths'][result['id']] == before
    assert before['paths']['Tip']['rows'] != page['rows']  # Complete data was never replaced by the page.


@pytest.mark.parametrize('raw', [False, True])
def test_fresh_owner_metadata_read_save_keeps_bindings_selection_and_drafts(setup, tmp_path, raw):
    old = setup[1].dispatch('pre.motion.calculate', {}, setup[2])
    old_record = deepcopy(setup[0].metadata['motion_paths'][old['id']])
    owner, motion, target, definition = independent_definition(setup)
    motion.dispatch('pre.motion.configure', {'definition': definition}, target)
    editor = raw_editor(definition)
    if raw:
        editor['definition_draft']['drives'][2]['relation']['expression'] = 'amplitude*sin('
        editor['definition_draft']['drives'][2]['relation']['constants'][0]['value'] = '1e'
        editor['definition_draft']['drives'][2]['relation']['sources'][0].update(joint_id=None, path=None)
    else:
        editor['definition_draft'] = None
    applied = deepcopy(owner.metadata['motion']['definition'])
    motion.dispatch('pre.motion.save_editor', {'editor': editor}, target)
    cold, reopened = cold_owner(owner, tmp_path)
    before = deepcopy(cold.read_metadata()); calls = list(cold.doc.calls)
    assert reopened.descriptor()['editors'][target['assembly_id']] == editor
    assert reopened.descriptor()['calculation'] is None
    assert cold.read_metadata()['motion']['definition'] == applied
    assert cold.read_metadata()['motion_paths'][old['id']] == old_record
    reply = reopened.dispatch('pre.motion.save_editor', {'editor': editor}, target)
    assert reply['changed'] is False and cold.doc.calls == calls and cold.read_metadata() == before
    page = reopened.dispatch('pre.motion.path', {'calculation_id': old['id'], 'trace_id': 'Tip', 'start': 0, 'count': 4}, target)
    assert page['rows'] == old_record['paths']['Tip']['rows']
    assert cold.doc.calls == calls
    if raw:
        for op, args in (('calculate', {}), ('frame', {'calculation_id': old['id'], 'frame': 1}),
                         ('play', {'calculation_id': old['id'], 'direction': 1}),
                         ('adopt_pose', {'calculation_id': old['id'], 'frame': 1})):
            with pytest.raises(ValueError, match='편집'):
                reopened.dispatch('pre.motion.'+op, args, target)
        assert cold.doc.calls == calls
        reopened.dispatch('pre.motion.configure', {'definition': definition}, target)
        assert cold.read_metadata()['motion_editors'][target['assembly_id']]['definition_draft'] is None
        assert cold.read_metadata()['motion_paths'][old['id']] == old_record


@pytest.mark.parametrize('fault', ['deleted', 'suppressed', 'reparent', 'unit', 'constant', 'domain'])
def test_owner_input_row_error_preserves_applied_native_and_results(setup, fault):
    old = setup[1].dispatch('pre.motion.calculate', {}, setup[2])
    owner, motion, target, definition = independent_definition(setup)
    motion.dispatch('pre.motion.configure', {'definition': definition}, target)
    previous = deepcopy(owner.metadata)
    simulation = owner._object(owner.metadata['motion']['simulation_id'])
    native = motion._native_definition(simulation)
    changed = deepcopy(definition); A = owner._object(changed['drives'][0]['joint_id'])
    if fault == 'deleted': changed['drives'][2]['relation']['sources'][0]['joint_id'] = 'Gone'
    elif fault == 'suppressed': A.Suppressed = True
    elif fault == 'reparent': changed['drives'][2]['relation']['sources'][0]['path'].insert(1, 'OtherOccurrence')
    elif fault == 'unit': changed['drives'][0]['unit'] = 'rad'
    elif fault == 'constant': changed['drives'][2]['relation']['constants'][0]['value'] = '1e'
    else: changed['drives'][0]['formula'] = '1/(time-0.5)'
    calls = list(owner.doc.calls)
    with pytest.raises(MotionInputError) as caught:
        motion.dispatch('pre.motion.configure', {'definition': changed}, target)
    assert any(row['row'] == 2 for row in caught.value.diagnostic['input_rows'])
    assert owner.metadata == previous
    assert motion._native_definition(simulation) == native
    assert old['id'] in owner.metadata['motion_paths']
    assert owner.doc.calls == calls


def test_actual_native_output_interval_not_only_requested_end(setup):
    owner, motion, target, definition = independent_definition(setup)
    definition['time'].update(end=.51, step=.26)
    definition['drives'][2]['relation']['expression'] = '0.5*A+B'
    definition['drives'][2]['limits'] = {'min': -1., 'max': 12.9, 'unit': 'deg'}
    with pytest.raises(MotionInputError, match='전구간'):
        motion.dispatch('pre.motion.configure', {'definition': definition}, target)


def test_raw_limit_128_kib_not_removed_and_no_semantic_coercion(setup):
    owner, motion, target, definition = independent_definition(setup)
    editor = raw_editor(definition)
    editor['definition_draft']['drives'][2]['relation']['expression'] = '한'*45000
    with pytest.raises(ValueError, match='128 KiB'):
        motion.dispatch('pre.motion.save_editor', {'editor': editor}, target)
    editor['definition_draft']['drives'][2]['relation']['expression'] = 'sin('
    editor['definition_draft']['drives'][2]['relation']['constants'][0]['value'] = '1e'
    motion.dispatch('pre.motion.save_editor', {'editor': editor}, target)
    assert owner.metadata['motion_editors'][target['assembly_id']] == editor


def test_new_relation_open_chain_cannot_bypass_existing_pose_check(setup):
    owner, motion, target, definition = setup
    result = motion.dispatch('pre.motion.calculate', {}, target)
    saved = deepcopy(owner.metadata['motion_paths'][result['id']])
    model = motion._attempt_model(owner._object(target['assembly_id']))
    # Legacy open-chain scope remains unchanged; adding a relation must not get
    # native-status-zero acceptance without complete frames/source definition.
    assert check_closed_motion(saved, model)['state'] == 'NOT_APPLICABLE'
    saved['definition_snapshot']['drives'][0]['relation'] = {'expression': 'A', 'sources': [], 'constants': []}
    check = check_closed_motion(saved, model)
    assert check['state'] in ('UNKNOWN', 'FAILED') and not check['accepted']
    assert check['scope'] == 'SAMPLED_RELATION_POSES'


def test_relation_source_exact_joint_path_through_existing_two_level_fixture(setup):
    from test_pre_motion_nested_assembly import nested
    owner, motion, target, definition = independent_definition(setup)
    root, outer, inner, ground, first = nested((owner, motion, target, definition))
    original = owner._object(definition['drives'][0]['joint_id'])
    group = next(g for g in root.Group if g.TypeId == 'Assembly::JointGroup')
    group.Group.remove(original)
    nested_group = owner.doc.addObject('Assembly::JointGroup', 'ChildJoints')
    nested_group.Group = [original]; inner.Group += [nested_group, original]
    outer.OutList = list(outer.Group); inner.OutList = list(inner.Group)
    paths = hierarchy(root)
    relation = definition['drives'][2]['relation']
    before = deepcopy(relation)
    # Same native joint name is insufficient after a different containment path.
    with pytest.raises(MotionInputError, match='배치 경로'):
        motion.dispatch('pre.motion.configure', {'definition': definition}, target)
    assert relation == before
    relation['sources'][0]['path'] = paths[original.Name][0]['path']
    assert len(relation['sources'][0]['path']) == 5
    # Existing hierarchy resolves repeated source Links independently.
    assert ground.getLinkedObject() is first.getLinkedObject()
    assert paths[ground.Name][0]['path'] != paths[first.Name][0]['path']
    # Check only compiler/identity here: no old M2 native campaign is rerun.
    formulas = motion._compile_drives(root, definition)
    assert 'sin(' in formulas[2]
    assert not any(call[0] == 'generateSimulation' for call in owner.doc.calls)
