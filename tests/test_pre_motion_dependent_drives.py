from copy import deepcopy
import math
import pytest
from test_pre_motion import setup, qt_panel
from apps.desktop_pre.motion_formula import compile_drives, interval
from apps.desktop_pre.motion import Motion


def relation_setup(setup):
    owner,motion,target,definition=setup
    definition=deepcopy(definition); master=definition['drives'][0]; master.update(name='회전 입력',formula='90*time',unit='deg')
    joint=owner._object(master['joint_id']); a,b=joint.Reference1[0].Name,joint.Reference2[0].Name
    slider=motion.dispatch('pre.joint.create',{'type':'Slider','connectors':[{'object_id':a,'subelement':''},{'object_id':b,'subelement':''}]},target)['joint_id']
    follower={'joint_id':slider,'type':'Linear','formula':'','unit':'mm','name':'이동 출력',
        'dependency':{'joint_id':master['joint_id'],'type':'Angular','ratio':2.,'ratio_unit':'mm/deg','offset':1.,'offset_unit':'mm'},
        'limits':{'min':0.,'max':600.,'unit':'mm'}}
    definition['drives'].append(follower)
    return owner,motion,target,definition


def test_declared_source_degree_relation_compiles_before_native_conversion_and_old_read_unchanged(setup):
    recorded=deepcopy(setup[0].doc.frames)
    owner,motion,target,d=relation_setup(setup); original=deepcopy(d)
    motion.dispatch('pre.motion.configure',{'definition':d},target)
    simulation=owner._object(owner.metadata['motion']['simulation_id'])
    assert simulation.Group[0].Formula=='((90*time)*pi/180)'
    assert simulation.Group[1].Formula=='(2.0*(90*time)+1.0)'
    assert owner.metadata['motion']['definition']==original
    cold=Motion(owner); cold._modules=motion._modules
    assert cold.descriptor()['calculation'] is None and owner.metadata['motion']['definition']==original
    owner.doc.frames=recorded  # native-output double was invalidated by configure
    calc=motion.dispatch('pre.motion.calculate',{},target)
    assert calc['frame_count']==4


@pytest.mark.parametrize('fault,match',[('cycle','순환'),('missing','기준 관절'),('unit','단위'),('duplicate','중복'),('ratio','유한'),('limit','전구간'),('reversed','하한')])
def test_invalid_relations_leave_native_definition_and_block_apply(setup,fault,match):
    owner,motion,target,d=relation_setup(setup); original=deepcopy(owner.metadata['motion'])
    if fault=='cycle': d['drives'][0]['dependency']={'joint_id':d['drives'][1]['joint_id'],'type':'Linear','ratio':1.,'ratio_unit':'deg/mm','offset':0.,'offset_unit':'deg'}
    elif fault=='missing': d['drives'][1]['dependency']['joint_id']='DeletedJoint'
    elif fault=='unit': d['drives'][0]['unit']='rad'
    elif fault=='duplicate': d['drives'].append(deepcopy(d['drives'][1]))
    elif fault=='ratio': d['drives'][1]['dependency']['ratio']='1e'
    elif fault=='limit': d['drives'][1]['limits']['max']=100.
    else: d['drives'][1]['limits'].update(min=601.,max=600.)
    with pytest.raises(ValueError,match=match): motion.dispatch('pre.motion.configure',{'definition':d},target)
    assert owner.metadata['motion']==original


def test_native_joint_limits_are_checked_for_driven_and_undriven_coordinates(setup):
    owner,motion,target,d=relation_setup(setup); joint=owner._object(d['drives'][0]['joint_id'])
    joint.EnableAngleMax=True; joint.AngleMax=300.
    motion.dispatch('pre.motion.configure',{'definition':d},target)
    joint.AngleMax=200.
    with pytest.raises(ValueError,match='허용 한계'): motion.dispatch('pre.motion.calculate',{},target)
    joint.AngleMax=300.; slider=owner._object(d['drives'][1]['joint_id']); slider.EnableLengthMax=True; slider.LengthMax=700.
    d['drives'].pop()
    with pytest.raises(ValueError,match='미구동 좌표'): motion.dispatch('pre.motion.configure',{'definition':d},target)


def test_conservative_whole_interval_does_not_use_sparse_output_or_widen_limit():
    joints={'A':{'type':'Revolute'}}
    drive={'joint_id':'A','type':'Angular','formula':'sin(2*pi*time)','unit':'rad','limits':{'min':-.5,'max':.5,'unit':'rad'}}
    _,errors=compile_drives([drive],(0.,1.),joints)
    assert '전구간' in errors[0][0]
    assert interval('0.1+0.2',(0.,1.))[1] >= .1+.2
    for formula in ('1/(time-.5)','sqrt(time-1)','log(time)','exp(1000)','time^2','tan(time)'):
        with pytest.raises((ValueError,OverflowError)): interval(formula,(0.,1.))
    assert interval('2*time+1',(2.,3.))==(5.,7.)


def test_qt_dependency_raw_edit_save_restore_and_apply_uses_relation(qt_panel):
    app,widget,panel,queued,descriptor,setup=qt_panel
    owner,motion,target,d=relation_setup(setup)
    panel._inspect_value(motion.dispatch('pre.motion.inspect',{},target))
    panel._loading=True; panel.drives.setRowCount(0)
    for value in d['drives']: panel._drive_row(value)
    panel._loading=False; panel.drives.selectRow(1); panel._drive_selected(); panel._validate_drives()
    import json
    assert json.loads(panel.drive_source.currentData())==[d['drives'][0]['joint_id'],'Angular']
    assert panel.drive_ratio_unit.currentText()=='mm/deg' and '회전 입력' in panel.drives.item(1,5).text()
    panel.drive_ratio.setText('1e'); panel._drive_options_edited()
    snapshot=panel.editor_snapshot(); raw=snapshot['editor']['definition_draft']['drives'][1]
    assert raw['dependency']['ratio']=='1e' and '유한' in panel.definition_notice.text()
    motion.dispatch('pre.motion.save_editor',{'editor':snapshot['editor']},target)
    panel._restore_editor(snapshot['editor']); assert panel._drive_values(raw=True)[1]['dependency']['ratio']=='1e'
    panel._configure(); assert not queued
    panel.drive_ratio.setText('2'); panel._drive_options_edited(); panel._configure()
    op,args,t,done=queued[-1]; assert op=='pre.motion.configure' and args['definition']['drives'][1]['dependency']['ratio']==2.
    done({'status':'COMPLETED','result':motion.dispatch(op,args,t)})
    assert owner.metadata['motion']['definition']['drives'][1]['dependency']['ratio_unit']=='mm/deg'


def test_changing_dependency_source_preserves_physical_ratio_unit_and_blocks_mismatch(qt_panel):
    import json
    app,widget,panel,queued,descriptor,setup=qt_panel
    owner,motion,target,d=relation_setup(setup)
    panel._inspect_value(motion.dispatch('pre.motion.inspect',{},target))
    panel._motion['joints'].append({'id':'OtherRotation','label':'새 기준 회전','type':'Revolute','issues':[]})
    panel._loading=True; panel.drives.setRowCount(0)
    for value in [*d['drives'],{'joint_id':'OtherRotation','type':'Angular','formula':'time','unit':'rad'}]: panel._drive_row(value)
    panel._loading=False; panel.drives.selectRow(1); panel._drive_selected()
    panel.drive_source.setCurrentIndex(panel.drive_source.findData(json.dumps(['OtherRotation','Angular'])))
    raw=panel._drive_values(raw=True)[1]['dependency']
    assert raw['joint_id']=='OtherRotation' and raw['ratio']=='2.0' and raw['ratio_unit']=='mm/deg'
    assert raw['offset']=='1.0' and raw['offset_unit']=='mm' and '단위' in panel.definition_notice.text()
    panel._configure(); assert not queued
    panel.drive_source.setCurrentIndex(panel.drive_source.findData(json.dumps([d['drives'][0]['joint_id'],'Angular'])))
    assert not panel._validate_drives() and panel._drive_values(raw=True)[1]['dependency']['ratio_unit']=='mm/deg'
