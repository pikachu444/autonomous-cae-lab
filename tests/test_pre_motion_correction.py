"""M3 correction: actual Windows-returned samples + existing controller doubles.

No FreeCAD invocation, no new solver, no synthesized kinematics. The data fixture
is losslessly extracted from the user-supplied after-failures.FCStd and attempts.
"""
from copy import deepcopy
import json
import math
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from test_pre_motion import setup, Owner, Placement, Rotation, Vector, Shape, native_modules
from test_pre_motion_closed_loop import cold_owner, compute
from apps.desktop_pre.motion import Motion, _pose
from apps.desktop_pre.motion_history import (check_closed_motion, checked_result, unpack_poses,
    pack_poses, rotate_vector, CHECK_SCHEMA)
from apps.desktop_pre.motion_path import connect_samples, csv_payload, data_draft, _csv_records

DATA = json.loads((Path(__file__).with_name('data')/'motion_closed_loop_windows.json').read_text(encoding='utf-8'))


@pytest.mark.parametrize('case,state', [('normal', 'PASSED'), ('overconstrained', 'FAILED'),
                                        ('unreachable', 'FAILED'), ('singular', 'FAILED')])
def test_attached_windows_native_status_zero_is_not_a_success_certificate(case, state):
    raw = deepcopy(DATA['cases'][case])
    before = deepcopy(raw)
    check = check_closed_motion(raw['summary'], raw['model'])
    assert raw == before
    assert raw['summary']['native_status'] == 0
    assert check['state'] == state
    assert check['accepted'] == (state == 'PASSED')
    assert check['cause_joints'] == [] and check['failure_time'] is None
    assert check['time_status'] == 'UNKNOWN'
    assert check['tolerance']['native'] == 1e-6
    assert check['tolerance']['position_mm'] == 1e-6
    assert check['tolerance']['angle_rad'] == 1e-6


@pytest.mark.parametrize('case,joint,kind,value', [
    ('overconstrained', 'JointB', 'joint_origin', 9.742798373969684),
    ('singular', 'JointD', 'joint_origin', 9.427885910146898),
    ('unreachable', 'JointA', 'drive_angle', math.pi)])
def test_independently_reported_observations_are_reproduced_without_solver(case, joint, kind, value):
    raw = DATA['cases'][case]
    check = check_closed_motion(raw['summary'], raw['model'])
    measure = next(m for m in check['metrics'] if m['joint_id'] == joint and m['measure'] == kind)
    assert measure['maximum'] == pytest.approx(value, abs=1e-12, rel=0)
    assert measure['first_mismatch']['frame'] == (1 if case == 'unreachable' else 2)
    assert measure['first_mismatch']['time'] == (0.0 if case == 'unreachable' else 0.05)
    assert check['frame_states'][0] == 'DESIGN'
    if case != 'unreachable': assert check['frame_states'][1] == 'PASSED'


class RecordedPlacement(Placement):
    def multVec(self, point):
        v = rotate_vector(self.Rotation.Q, [point.x, point.y, point.z])
        return Vector(self.Base.x+v[0], self.Base.y+v[1], self.Base.z+v[2])


def placement(pose):
    return RecordedPlacement(Vector(*pose[:3]), Rotation(*pose[3:]))


@pytest.fixture
def windows_controller():
    """Feed the exact uploaded output poses to the existing Motion controller."""
    owner = Owner(); owner.App.Placement = RecordedPlacement
    motion = Motion(owner); motion._modules = native_modules()
    doc = owner.doc
    assembly = doc.addObject('Assembly::AssemblyObject', 'FourBar'); assembly.Type = 'Assembly'
    group = assembly.newObject('Assembly::JointGroup', 'Joints')
    raw = DATA['cases']['normal']; payload = unpack_poses(raw['summary']['poses'], 22)
    for binding in payload['bindings'][1:]:
        source = doc.addObject('Part::Feature', binding['source']); source.Shape = Shape(binding['source'])
        obj = assembly.newObject('App::Link', binding['id']); obj.setLink(source)
    for row in raw['model']['joints']:
        obj = group.newObject('App::FeaturePython', row['id']); obj.Label = row['label']
        if 'ground' in row: obj.ObjectToGround = doc.getObject(row['ground'])
        else: motion._modules[1].Joint(obj, 1)
    doc.moving = doc.getObject('Link_crank')
    context = {'owner': owner, 'motion': motion, 'target': {'assembly_id': assembly.Name}, 'assembly': assembly}
    def load(case):
        motion.before_design_action('change recorded native input')
        raw = DATA['cases'][case]; context['payload'] = unpack_poses(raw['summary']['poses'], 22)
        for binding, pose in zip(context['payload']['bindings'], context['payload']['design']):
            doc.getObject(binding['id']).Placement = placement(pose)
        for row in raw['model']['joints']:
            obj = doc.getObject(row['id']); obj.Suppressed = row.get('suppressed', False)
            if 'type' in row:
                obj.JointType = row['type']
                for side in (1, 2):
                    name, elements = row['Reference'+str(side)]
                    setattr(obj, 'Reference'+str(side), (doc.getObject(name), elements[:]))
                    setattr(obj, 'Placement'+str(side), placement(row['Placement'+str(side)]))
                    setattr(obj, 'Offset'+str(side), placement(row['Offset'+str(side)]))
                    setattr(obj, 'Detach'+str(side), row['Detach'+str(side)])
        motion.dispatch('pre.motion.configure', {'definition': deepcopy(raw['summary']['definition_snapshot'])}, context['target'])
        simulation=owner._object(owner.metadata['motion']['simulation_id'])
        for drive in simulation.Group:
            drive.getTypeIdOfProperty=lambda name: DATA['native_motion_property_types'][name]
    def generate(simulation):
        assert owner.preview_depth > 0
        doc.calls.append(('generateSimulation', simulation.Name))
        return 0
    def update(index):
        assert owner.preview_depth > 0
        doc.calls.append(('updateForFrame', index))
        for binding, pose in zip(context['payload']['bindings'], context['payload']['frames'][index]):
            doc.getObject(binding['id']).Placement = placement(pose)
        return 0
    assembly.generateSimulation = generate
    assembly.numberOfFrames = lambda: len(context['payload']['frames'])
    assembly.updateForFrame = update
    context['load'] = load; load('normal')
    return context


def test_controller_rejects_native_zero_but_preserves_raw_and_last_success_then_repairs(windows_controller, tmp_path):
    c = windows_controller; owner, motion, target = c['owner'], c['motion'], c['target']
    good = motion.dispatch('pre.motion.calculate', {}, target)
    original = deepcopy(owner.metadata['motion_paths'][good['id']])
    assert good['constraint_check']['state'] == 'PASSED'
    bad_ids = []
    for case in ('overconstrained', 'unreachable', 'singular'):
        c['load'](case)
        with pytest.raises(RuntimeError, match='불일치|벌어짐'):
            motion.dispatch('pre.motion.calculate', {}, target)
        failed = owner.metadata['motion_attempts'][-1]
        assert failed['state'] == 'FAILED' and failed['stage'] == 'CHECK'
        assert failed['native_status'] == 0 and failed['diagnostic']['category'] == 'UNKNOWN'
        assert failed['diagnostic']['cause_joints'] == [] and failed['diagnostic']['failure_time'] is None
        assert failed['previous_success_id'] == good['id']
        bad = owner.metadata['motion_paths'][failed['raw_result_id']]; bad_ids.append(bad['id'])
        assert bad['accepted'] is False and bad['native_status'] == 0
        assert len(unpack_poses(bad['poses'], 22)['frames']) == 22
        assert bad['constraint_check']['state'] == 'FAILED'
        assert owner.metadata['motion']['last_completed']['id'] == good['id']
        assert owner.metadata['motion_paths'][good['id']] == original
        assert motion._calculation is None and motion._preview is False
        assert [_pose(owner.doc.getObject(b['id']).Placement) for b in c['payload']['bindings']] == c['payload']['design']
    motion.before_design_action('save')
    # Cold session simulated via the actual JSON metadata property, not FCStd I/O.
    cold, opened = cold_owner(owner, tmp_path)
    before = len(cold.doc.calls)
    path = opened.dispatch('pre.motion.path', {'calculation_id': good['id'], 'trace_id': '연결봉 중앙',
        'start': 0, 'count': 22}, target)
    assert path['rows'] == original['paths']['연결봉 중앙']['rows']
    pose = opened.dispatch('pre.motion.frame', {'calculation_id': good['id'], 'frame': 21}, target)
    assert pose['retained'] and len(cold.doc.calls) == before
    opened.dispatch('pre.motion.stop', {}, target)
    for identifier in bad_ids:
        raw = opened.dispatch('pre.motion.path', {'calculation_id': identifier, 'trace_id': '연결봉 중앙',
            'start': 0, 'count': 22}, target)
        assert raw['constraint_check']['accepted'] is False
        assert raw['rows'][-1]['validation'] == 'FAILED'
    c['load']('normal')
    repaired = motion.dispatch('pre.motion.calculate', {}, target)
    assert repaired['id'] != good['id'] and repaired['accepted']
    assert owner.metadata['motion_paths'][good['id']] == original
    assert len(owner.metadata['motion_paths']) == 5
    assert [a['state'] for a in owner.metadata['motion_attempts']] == ['SUCCEEDED','FAILED','FAILED','FAILED','SUCCEEDED']


def test_legacy_status_only_records_are_reassessed_without_rewriting_raw(windows_controller):
    c = windows_controller; owner, motion = c['owner'], c['motion']
    records = deepcopy(DATA['cases'])
    owner.metadata['motion_paths'] = {v['summary']['id']: v['summary'] for v in records.values()}
    owner.metadata['motion_attempts'] = [v['attempt'] for v in records.values()]
    owner.metadata['motion']['last_completed'] = deepcopy(records['singular']['summary'])
    before = deepcopy(owner.metadata)
    opened = Motion(owner); opened._modules = native_modules()
    descriptor = opened.descriptor()
    assert owner.metadata == before
    checked = {s['id']: s for s in descriptor['path_results']}
    assert checked[records['normal']['summary']['id']]['accepted'] is True
    for case in ('overconstrained','unreachable','singular'):
        assert checked[records[case]['summary']['id']]['accepted'] is False
        a = next(a for a in descriptor['attempts'] if a.get('result_id') == records[case]['summary']['id'])
        assert a['state'] == 'FAILED' and a['recorded_state'] == 'SUCCEEDED'
        assert a['native_status'] == 0
    assert descriptor['definition']['last_completed']['id'] == records['normal']['summary']['id']


@pytest.mark.parametrize('op', ['pre.motion.frame', 'pre.motion.play', 'pre.motion.calculate', 'pre.motion.adopt_pose'])
@pytest.mark.parametrize('draft', ['joint_draft', 'definition_draft'])
def test_unapplied_gate_precedes_retained_selection_and_preserves_state(setup, op, draft):
    owner, motion, target, good = compute(setup)
    motion.before_design_action('save')
    owner.metadata['motion_editors'] = {target['assembly_id']: {draft: {'raw': 'unchanged'}}}
    before = deepcopy(owner.metadata)
    args = {} if op == 'pre.motion.calculate' else {'calculation_id': good['id'],
            **({'direction': 1} if op == 'pre.motion.play' else {'frame': 2})}
    with pytest.raises(ValueError, match='편집'): motion.dispatch(op, args, target)
    assert motion._calculation is None and motion._replay is None and motion._base == []
    assert owner.doc.moving.Placement.Base.x == 0 and owner.metadata == before
    page = motion.dispatch('pre.motion.path', {'calculation_id': good['id'], 'trace_id': 'Tip', 'start': 0, 'count': 4}, target)
    assert len(page['rows']) == 4


@pytest.mark.parametrize('args', [
    {'calculation_id':'missing', 'trace_id':'Tip','start':0,'count':4},
    {'calculation_id':'saved', 'trace_id':'missing','start':0,'count':4}])
def test_draft_path_exception_requires_exact_persisted_result_and_trace(setup, args):
    owner, motion, target, good = compute(setup)
    args = deepcopy(args)
    if args['calculation_id'] == 'saved': args['calculation_id'] = good['id']
    motion.before_design_action('save')
    owner.metadata['motion_editors'] = {target['assembly_id']: {'joint_draft': {}}}
    with pytest.raises(ValueError, match='편집'): motion.dispatch('pre.motion.path', args, target)


def test_unpersisted_path_cannot_bypass_draft_gate(setup):
    owner, motion, target, good = compute(setup)
    del owner.metadata['motion_paths'][good['id']]
    owner.metadata['motion_editors'] = {target['assembly_id']: {'definition_draft': {}}}
    with pytest.raises(ValueError, match='편집'):
        motion.dispatch('pre.motion.path', {'calculation_id': good['id'], 'trace_id':'Tip','start':0,'count':4}, target)


@pytest.mark.parametrize('ticks', [0, 1, 2])
def test_retained_path_stops_timer_even_before_first_tick_and_ignores_queued_ticks(setup, ticks):
    owner, motion, target, good = compute(setup)
    motion.before_design_action('save')
    motion.dispatch('pre.motion.play', {'calculation_id': good['id'], 'direction':1}, target)
    for _ in range(ticks): motion._timer.callback()
    motion.dispatch('pre.motion.path', {'calculation_id':good['id'],'trace_id':'Tip','start':0,'count':4}, target)
    assert not motion._timer.active and not motion._preview
    assert motion._state == 'CALCULATED' and motion._frame is None
    before = _pose(owner.doc.moving.Placement)
    motion._timer.callback(); motion._timer.callback()
    assert _pose(owner.doc.moving.Placement) == before
    assert not motion._preview and motion._frame is None


@pytest.mark.parametrize('case', ['overconstrained','unreachable','singular'])
def test_invalid_curve_intervals_never_connect_and_data_marks_original_rows(case):
    raw=DATA['cases'][case]; result=checked_result(raw['summary'],raw['model'])
    path=next(iter(result['paths'].values()))
    for left, right in zip(path['rows'],path['rows'][1:]):
        if left['validation']!='PASSED' or right['validation']!='PASSED':
            assert not connect_samples(path,left,right)
    source = csv_payload(path).decode('utf-8')
    assert 'constraint_quality_rows' in source
    draft=data_draft(path,'upload')
    excluded=draft['mapping']['columns']['X']['row_selection']['exclude_rows']
    records, _, _=_csv_records(path)
    for i, row in enumerate(path['rows']):
        if row['validation']=='FAILED': assert i+2 in excluded
    # Coordinates are preserved, not replaced by zero/nan or interpolated.
    assert [r[2:] for r in records] == [r['point'] for r in path['rows']]


def test_bad_formula_is_unknown_not_success_and_no_arbitrary_tolerance(setup):
    raw=deepcopy(DATA['cases']['normal'])
    raw['summary']['definition_snapshot']['drives'][0]['formula']='time^2'
    raw['summary']['native_definition']['drives'][0]['formula']='time^2'
    check=check_closed_motion(raw['summary'],raw['model'])
    assert check['state']=='UNKNOWN' and not check['accepted']
    assert check['unknowns'] and check['tolerance']['native']==1e-6


def test_native_property_type_must_match_cpp_dispatch(setup):
    owner,motion,target,good=compute(setup)
    simulation=owner._object(owner.metadata['motion']['simulation_id'])
    simulation.Group[0].getTypeIdOfProperty=lambda prop: {'Joint':'App::PropertyLinkSub',
        'MotionType':'App::PropertyEnumeration','Formula':'App::PropertyString'}[prop]
    before=len([c for c in owner.doc.calls if c[0]=='generateSimulation'])
    with pytest.raises(ValueError,match='연결 형식'): motion.dispatch('pre.motion.calculate',{},target)
    assert len([c for c in owner.doc.calls if c[0]=='generateSimulation'])==before


# Execute the real _send guard with lightweight widget stand-ins. This is not
# a Qt render or an OS interaction test, and needs no optional Qt installation.
@pytest.mark.parametrize('persisted,trace,assembly,allowed', [
    (True,'Tip','Assembly',True), (False,'Tip','Assembly',False),
    (True,'missing','Assembly',False), (True,'Tip','AnotherAssembly',False)])
def test_actual_panel_path_guard_is_scoped_to_saved_assembly_result_trace(persisted,trace,assembly,allowed):
    from apps.desktop_pre.motion_panel import MotionPanel
    panel=MotionPanel.__new__(MotionPanel)
    panel._busy=False;panel._edited=True;panel._joint_edited=False
    panel.assembly=NS(currentData=lambda:'Assembly')
    panel._motion={'path_results':[{'id':'Ksaved','assembly_id':'Assembly','persisted':persisted,
                                  'paths':{'Tip':{'rows':[]}}}]}
    panel.status=NS(setText=lambda text:None)
    panel._edit_version=panel._joint_version=panel._serial=0
    panel._document='D';panel._session='S';panel._buttons=[]
    calls=[]
    panel.submit=lambda op,args,target,done:calls.append((op,args,target)) or {'queued':True}
    panel._send('pre.motion.path',{'calculation_id':'Ksaved','trace_id':trace,'start':0,'count':1},
                target={'assembly_id':assembly})
    assert bool(calls)==allowed


def test_native_zero_check_failure_preserves_raw_when_metadata_write_fails_then_retries(windows_controller, monkeypatch):
    c=windows_controller; owner,motion,target=c['owner'],c['motion'],c['target']
    good=motion.dispatch('pre.motion.calculate',{},target)
    c['load']('unreachable')
    original=deepcopy(owner.metadata['motion_paths'][good['id']])
    write=owner.write_metadata
    def fail_raw(value):
        if len(value.get('motion_paths',{}))>1: raise OSError('simulated disk full')
        write(value)
    monkeypatch.setattr(owner,'write_metadata',fail_raw)
    with pytest.raises(RuntimeError): motion.dispatch('pre.motion.calculate',{},target)
    assert motion._pending_summary['accepted'] is False
    raw_id=motion._pending_summary['id']
    assert motion._unsaved_attempts and motion._unsaved_attempts[-1]['stage']=='CHECK'
    assert owner.metadata['motion']['last_completed']['id']==good['id']
    monkeypatch.setattr(owner,'write_metadata',write)
    motion.before_design_action('retry save')
    assert owner.metadata['motion_paths'][raw_id]['accepted'] is False
    assert owner.metadata['motion_paths'][good['id']]==original
    assert owner.metadata['motion']['last_completed']['id']==good['id']
    assert owner.metadata['motion_attempts'][-1]['state']=='FAILED'
    assert not motion._unsaved_attempts


def test_checker_exception_is_unknown_and_complete_raw_is_retained(windows_controller, monkeypatch):
    import apps.desktop_pre.motion as module
    c=windows_controller; owner,motion,target=c['owner'],c['motion'],c['target']
    check=module.check_closed_motion
    def broken(summary,model):
        if model is not None: raise ValueError('injected unavailable audit')
        return check(summary,model)
    monkeypatch.setattr(module,'check_closed_motion',broken)
    with pytest.raises(RuntimeError,match='검사'): motion.dispatch('pre.motion.calculate',{},target)
    failed=owner.metadata['motion_attempts'][-1]
    raw=owner.metadata['motion_paths'][failed['raw_result_id']]
    assert raw['native_status']==0 and raw['accepted'] is False
    assert raw['constraint_check']['state']=='UNKNOWN'
    assert len(unpack_poses(raw['poses'],22)['frames'])==22
    assert 'last_completed' not in owner.metadata['motion']


def test_invalid_saved_path_request_still_cancels_queued_playback(setup):
    owner,motion,target,good=compute(setup)
    motion.before_design_action('save')
    motion.dispatch('pre.motion.play',{'calculation_id':good['id'],'direction':1},target)
    with pytest.raises(ValueError):
        motion.dispatch('pre.motion.path',{'calculation_id':good['id'],'trace_id':'Tip','start':-1,'count':4},target)
    motion._timer.callback();motion._timer.callback()
    assert not motion._timer.active and not motion._preview
    assert owner.doc.moving.Placement.Base.x==0


@pytest.mark.parametrize('fault',['version','scale','time','tolerance'])
def test_unverifiable_native_meaning_is_not_silently_accepted(fault):
    raw=deepcopy(DATA['cases']['normal']); s=raw['summary']
    if fault=='version': s['clock_source']['native_version']='FreeCAD 1.1.40'
    elif fault=='scale':
        p=unpack_poses(s['poses'],22);p['bindings'][1]['scale']=[2.,2.,2.]
        s['poses']=pack_poses(p,22)
    elif fault=='time':s['clock_source']['complete']=False
    else:s['native_definition']['tolerance']=1e-5
    result=check_closed_motion(s,raw['model'])
    assert result['state']=='UNKNOWN' and not result['accepted']


def test_parallel_joint_edges_are_not_exempted_to_pass_an_unphysical_protocol_double(setup):
    from test_pre_motion_dependent_drives import relation_setup
    recorded=deepcopy(setup[0].doc.frames)
    owner,motion,target,definition=relation_setup(setup)
    motion.dispatch('pre.motion.configure',{'definition':definition},target)
    owner.doc.frames=recorded
    with pytest.raises(RuntimeError): motion.dispatch('pre.motion.calculate',{},target)
    assert owner.metadata['motion_attempts'][-1]['constraint_check']['state']=='FAILED'


def test_m1_dependency_compilation_remains_compatible_on_two_distinct_open_chains(setup):
    from test_pre_motion_dependent_drives import relation_setup
    recorded=deepcopy(setup[0].doc.frames)
    owner,motion,target,definition=relation_setup(setup)
    slider=owner._object(definition['drives'][1]['joint_id'])
    assembly=owner._object(target['assembly_id'])
    # Correct the protocol fixture topology, not the production audit: the
    # independent slider requires its own moving occurrence, not the revolute body.
    moving=assembly.newObject('App::Link','IndependentSlider')
    moving.setLink(owner.doc.moving.getLinkedObject())
    slider.Reference2=(moving,['',''])
    motion.dispatch('pre.motion.configure',{'definition':definition},target)
    simulation=owner._object(owner.metadata['motion']['simulation_id'])
    assert [m.Formula for m in simulation.Group]==['((90*time)*pi/180)','(2.0*(90*time)+1.0)']
    owner.doc.frames=recorded
    result=motion.dispatch('pre.motion.calculate',{},target)
    assert result['frame_count']==4 and result['constraint_check']['state']=='NOT_APPLICABLE'


@pytest.mark.parametrize('formula',['exp(time)','log(time+1)','sqrt(time)','tan(time)','e'])
def test_native_unconfirmed_function_is_not_interpreted_as_python(formula):
    raw=deepcopy(DATA['cases']['normal'])
    raw['summary']['definition_snapshot']['drives'][0]['formula']=formula
    raw['summary']['native_definition']['drives'][0]['formula']=formula
    check=check_closed_motion(raw['summary'],raw['model'])
    assert check['state']=='UNKNOWN' and not check['accepted']


def test_legacy_attached_jcs_snapshot_is_not_claimed_to_be_native_effective():
    raw=deepcopy(DATA['cases']['normal'])
    raw['model']['jcs_source']='PREFLIGHT_ONLY'
    next(j for j in raw['model']['joints'] if j.get('type'))['Detach1']=False
    check=check_closed_motion(raw['summary'],raw['model'])
    assert check['state']=='UNKNOWN' and 'JCS' in check['unknowns'][0]


def test_rejected_raw_pose_is_labelled_in_typed_reply_and_cannot_be_adopted(windows_controller):
    c=windows_controller;owner,motion,target=c['owner'],c['motion'],c['target']
    c['load']('unreachable')
    with pytest.raises(RuntimeError):motion.dispatch('pre.motion.calculate',{},target)
    raw_id=owner.metadata['motion_attempts'][-1]['raw_result_id']
    before=len(owner.doc.calls)
    row=motion.dispatch('pre.motion.frame',{'calculation_id':raw_id,'frame':1},target)
    assert row['accepted'] is False and row['validation']=='FAILED' and row['retained']
    assert len(owner.doc.calls)==before
    with pytest.raises(ValueError,match='읽기 전용'):
        motion.dispatch('pre.motion.adopt_pose',{'calculation_id':raw_id,'frame':1},target)
    motion.dispatch('pre.motion.stop',{},target)
    assert not motion._preview


def test_missing_row_quality_in_checked_path_is_not_transferred_as_valid():
    raw=DATA['cases']['overconstrained']
    path=next(iter(checked_result(raw['summary'],raw['model'])['paths'].values()))
    for row in path['rows']:row.pop('validation')
    draft=data_draft(path,'upload')
    assert set(draft['mapping']['columns']['X']['row_selection']['exclude_rows'])==set(range(2,24))


def test_matching_but_invented_saved_times_are_not_a_native_clock_certificate():
    raw=deepcopy(DATA['cases']['normal']);s=raw['summary'];p=unpack_poses(s['poses'],22)
    s['frame_times'][2]=0.051
    p['frame_times']=deepcopy(s['frame_times']);s['poses']=pack_poses(p,22)
    check=check_closed_motion(s,raw['model'])
    assert check['state']=='UNKNOWN' and not check['accepted']
