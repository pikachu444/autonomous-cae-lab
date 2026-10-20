"""Reader/deck negative tests use labelled synthetic output, no solver."""
from copy import deepcopy
import json
import pytest
from test_dynamic_support import base_model,snapshot,dynamic_model,outputs
from caelab.adapters.conservative_load import read_source,_profile
from caelab.adapters.frozen_fem import _sha
from caelab.storage import save_json


def fake_attempt(tmp_path,change=None):
    m=base_model();m['step'].update(initial=1.,maximum=1.)
    if change:change(m)
    path=snapshot(m,tmp_path/'frozen_input');native=tmp_path/'solver';native.mkdir()
    (native/'contact.inp').write_bytes((path.parent/'contact.inp').read_bytes())
    from caelab.contact_steps import default_program
    captured=deepcopy(m)
    if 'analysis_steps' not in captured:
        captured['analysis_steps']=default_program(captured['step'],captured['conditions'])
    frd,dat,sta=outputs(captured,omit='ENER')
    (native/'contact.frd').write_text(frd,encoding='ascii',newline='\n')
    (native/'contact.sta').write_text(sta,encoding='ascii',newline='\n')
    save_json(native/'ccx_contact.execution.json',{'status':'COMPLETED','return_code':0})
    result={'execution_status':'SUCCEEDED','native_version':'2.22','artifacts':[
        {'relative':p.relative_to(tmp_path).as_posix(),'bytes':p.stat().st_size,'sha256':_sha(p)}
        for p in native.iterdir()]}
    save_json(tmp_path/'contact_execution.json',result)
    return path,m


def test_selected_support_rf_exact_id_join(tmp_path):
    fake_attempt(tmp_path)
    field=read_source(tmp_path,[3,1])
    assert field['node_ids']==[3,1] and field['value']==[[-1.,0.,0.],[-1.,0.,0.]]
    assert field['static']['increment']==3


@pytest.mark.parametrize('change,match',[
    (lambda m:m['loads'].append({'node_id':1,'component':1,'force_N':1.}),'overlaps'),
    (lambda m:m['step'].__setitem__('geometry','nonlinear'),'linear static'),
    (lambda m:m['boundary_dofs'].__setitem__(0,{**m['boundary_dofs'][0],'value_mm':.1}),'contributions'),
])
def test_incompatible_source_is_not_relabelled_reaction(tmp_path,change,match):
    with pytest.raises(ValueError,match=match):
        fake_attempt(tmp_path,change);read_source(tmp_path,[1])


@pytest.mark.parametrize('card',['*DLOAD\n1,GRAV,9.8,0,0,-1','*TRANSFORM,NSET=Nall\n1,0,0,0,1,0','*MPC\nBEAM,1,2'])
def test_executed_extra_load_or_constraint_card_rejected(tmp_path,card):
    path,_=fake_attempt(tmp_path)
    original=(path.parent/'contact.inp').read_bytes()
    (tmp_path/'solver/contact.inp').write_bytes(original+card.encode('ascii')+b'\n')
    # Deliberately update only the declared result pin: frozen deck remains original.
    result=json.loads((tmp_path/'contact_execution.json').read_text())
    pin=next(r for r in result['artifacts'] if r['relative']=='solver/contact.inp')
    p=tmp_path/'solver/contact.inp';pin.update(bytes=p.stat().st_size,sha256=_sha(p))
    save_json(tmp_path/'contact_execution.json',result)
    with pytest.raises(ValueError,match='Executed deck differs'):read_source(tmp_path,[1])


def test_missing_force_and_tampered_native_bytes_fail_without_source_mutation(tmp_path):
    path,m=fake_attempt(tmp_path)
    raw=(tmp_path/'solver/contact.frd').read_bytes()
    (tmp_path/'solver/contact.frd').write_bytes(raw.replace(b'FORC',b'FORK',1))
    with pytest.raises(ValueError,match='changed'):read_source(tmp_path,[1])
    assert (path.parent/'contact.inp').read_bytes()==(tmp_path/'solver/contact.inp').read_bytes()


def authored_nonunit(model):
    from caelab.contact_steps import default_program
    model['step'].update(period=2.75,initial=.25,maximum=.5)
    model['conditions'][0].update(object_id='UserSupport47',label='사용자 지지')
    model['conditions'][1].update(object_id='UserRemoteLoad',label='다른 위치 하중')
    model['analysis_steps']=default_program(model['step'],model['conditions'])
    model['analysis_steps']['steps'][0].update(id='UserStaticStage',label='사용자 단계')


def test_exact_selected_converged_frame_preserves_nonunit_coordinate(tmp_path):
    fake_attempt(tmp_path,authored_nonunit)
    selected={'step':1,'increment':2,'load_parameter':1.375}
    field=read_source(tmp_path,[3,1],static=selected)
    assert field['static']==selected and field['value']==[[-1.375,0.,0.],[-1.375,0.,0.]]
    assert read_source(tmp_path,[1])['static']['load_parameter']==2.75
    with pytest.raises(ValueError,match='exact retained'):
        read_source(tmp_path,[1],static={**selected,'increment':7})


def test_zero_cload_card_at_selected_source_is_not_absence(tmp_path):
    def zero_load(model):
        model['loads'].append({'node_id':1,'component':1,'force_N':0.})
        model['conditions'].append({'object_id':'ZeroButPresent','type':'Fem::ConstraintForce',
            'body_id':'Solid','total_force_N':0.,'force_weights':[{'node_id':1,'component':1,'weight':1.}]})
    fake_attempt(tmp_path,zero_load)
    with pytest.raises(ValueError,match='also carries CLOAD'):read_source(tmp_path,[1])


def test_unselected_prescribed_displacement_does_not_ban_the_source(tmp_path):
    def prescribed_elsewhere(model):
        row={'node_id':4,'component':1,'value_mm':.1}
        model['boundary_dofs'].append(row)
        model['conditions'].append({'object_id':'GuideMotion','label':'Guide motion',
            'type':'Fem::ConstraintDisplacement','body_id':'Solid','components_mm':{1:.1},
            'boundary_dofs':[deepcopy(row)]})
        authored_nonunit(model)
    fake_attempt(tmp_path,prescribed_elsewhere)
    field=read_source(tmp_path,[1],static={'step':1,'increment':2,'load_parameter':1.375})
    assert field['node_ids']==[1] and field['static']['load_parameter']==1.375


def test_selected_nonzero_active_spc_is_not_a_fixed_support_reaction(tmp_path):
    def moving_support(model):
        support=model['conditions'][0]
        support.update(type='Fem::ConstraintDisplacement',components_mm={1:.1,2:0.,3:0.})
        for rows in (support['boundary_dofs'],model['boundary_dofs']):
            for row in rows:
                if row['component']==1:row['value_mm']=.1
        authored_nonunit(model)
    fake_attempt(tmp_path,moving_support)
    with pytest.raises(ValueError,match='active zero XYZ'):
        read_source(tmp_path,[1],static={'step':1,'increment':2,'load_parameter':1.375})
