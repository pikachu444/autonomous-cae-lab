from copy import deepcopy
import pytest
from initial_field_fixture import model,draft,applied
from caelab.initial_field_conditions import normalize,effective
from caelab.contact_deck import render


def test_temperature_absolute_difference_and_explicit_reference_cards():
    m=applied();text=render(m)
    assert '*INITIAL CONDITIONS,TYPE=TEMPERATURE' in text and '*EXPANSION,ZERO=293.15' in text
    assert text.count('*TEMPERATURE')==2 and '1,343.15' in text and '1,393.15' in text
    d=draft();d['temperature'].update(mode='difference',unit='°C',reference_value=20.,reference_unit='°C',samples=[[0,0.],[1,50.],[2,100.]])
    assert normalize(model(),d)['temperature']['samples_K']==effective(m)['temperature']['samples_K']
    d['temperature']['samples'][0][1]=20.
    with pytest.raises(ValueError,match='초기 온도'):normalize(model(),d)


def test_stress_rotation_units_and_exact_ip_contract_no_plastic_restart():
    d=draft('stress');d['stress'].update(unit='Pa',values=[1e8,0.,0.,0.,0.,0.]);d['frame']=[[0.,-1.,0.],[1.,0.,0.],[0.,0.,1.]]
    result=normalize(model(),d)
    assert len(result['stress_rows'])==4 and all(r['values_MPa']==[0.,100.,0.,0.,0.,0.] for r in result['stress_rows'])
    assert 'second_Piola' in result['initial_stress_measure']
    d['stress']['ip_rows']=[{'element_id':1,'point':1,'values':[0.]*6}]
    with pytest.raises(ValueError,match='빠짐없이'):normalize(model(),d)
    d['frame'][0][0]=1.
    with pytest.raises(ValueError,match='직교'):normalize(model(),d)


def test_compatible_affine_total_strain_stress_and_support_are_jointly_checked():
    d=draft('compatible');state=normalize(model(),d)['compatible']
    assert state['displacements_mm'][1]['value']==pytest.approx([.01,0.,0.])
    d['compatible']['total_strain'][0]=.002
    with pytest.raises(ValueError,match='대칭'):normalize(model(),d)
    d=draft('compatible');d['compatible']['stress_values'][0]=100.
    with pytest.raises(ValueError,match='탄성'):normalize(model(),d)
    d=draft('compatible');d['compatible']['translation_mm'][0]=1.
    with pytest.raises(ValueError,match='구속'):normalize(model(),d)


@pytest.mark.parametrize('mutation',[lambda d:d['temperature'].update(expansion_per_K='1e'),
    lambda d:d['states'][1].update(parameter=1.),lambda d:d['temperature'].update(unit='unknown'),
    lambda d:d['temperature']['samples'][1].__setitem__(1,float('nan'))])
def test_invalid_raw_is_not_admitted_or_filled(mutation):
    d=draft();mutation(d)
    with pytest.raises(ValueError):normalize(model(),d)


def test_explicit_existing_total_force_contributions_are_preserved():
    m=applied();m['conditions'].append({'object_id':'Force','label':'원 총힘','type':'Fem::ConstraintForce','body_id':'Solid',
        'total_force_N':25.,'force_weights':[{'node_id':2,'component':1,'weight':1.}]})
    m['loads']=[{'node_id':2,'component':1,'force_N':25.}]
    from caelab.adapters.initial_field_deck import program
    for step,value in zip(m['analysis_steps']['steps'],(0.,25.)):
        step['curves'].append({'condition_id':'Force','component':0,'unit':'N','points':[[0.,0.],[step['duration'],value]]})
    before=deepcopy(m['loads']);m['analysis_steps']=program(m,effective(m));text=render(m)
    assert '*CLOAD' in text and m['loads']==before
    assert m['analysis_steps']['steps'][0]['curves'][-1]['points'][-1][1]==0.
    assert m['analysis_steps']['steps'][1]['curves'][-1]['points'][-1][1]==25.


def test_user_static_program_and_arbitrary_names_are_retained_with_three_temperature_states():
    from caelab.initial_field_conditions import default_draft
    from caelab.adapters.initial_field_deck import program,decorate
    m=model()
    m['conditions'][0]['object_id']='UserClamp_Z9'
    for step in m['analysis_steps']['steps']:
        for c in step['curves']:
            if c['condition_id']=='Support1':c['condition_id']='UserClamp_Z9'
    third=deepcopy(m['analysis_steps']['steps'][-1]);third.update(id='Cooling3',label='냉각',duration=.5,initial=.25,maximum=.5,output_frequency=2)
    for c in third['curves']:c['points'][-1][0]=.5
    m['analysis_steps']['steps'].append(third)
    d=default_draft(m);d.update(mesh_id='UserMesh',node_ids=[r['node_id'] for r in m['nodes']],element_ids=[1])
    d['temperature'].update(reference_value=300.,expansion_per_K=1.1e-5,samples=[[0.,300.],[1.,320.],[2.,340.],[2.5,310.]])
    before=deepcopy(m);definition=normalize(m,d)
    assert program(m,definition)==before['analysis_steps'] and m==before
    m['initial_fields']={'draft':d,'definition':definition}
    # Direct decoration isolates this feature until the lead integrates render.
    text=decorate(m,render(before))
    assert text.count('*TEMPERATURE')==3 and '1,310' in text
    assert m['analysis_steps']==before['analysis_steps']
    d['states'][-1]['parameter']=3.
    with pytest.raises(ValueError,match='실제 누적'):normalize(m,d)


def test_aster_unsupported_changing_support_does_not_rewrite_user_program():
    from caelab.adapters.initial_field_deck import program
    m=model();m['step']['automatic']=False;d=draft('compatible');before=deepcopy(m['analysis_steps'])
    m['analysis_steps']['steps'][1]['curves'][0]['points'][-1][1]=.01
    authored=deepcopy(m['analysis_steps'])
    with pytest.raises(ValueError,match='불변 구속'):program(m,normalize(m,d))
    assert m['analysis_steps']==authored and authored!=before


@pytest.mark.parametrize('setting',['automatic','convergence','increment','output'])
def test_aster_does_not_silently_ignore_authored_native_settings(setting):
    from caelab.adapters.initial_field_deck import program
    m=model();m['step']['automatic']=False;d=draft('compatible')
    if setting=='automatic':m['step']['automatic']=True
    elif setting=='convergence':m['step']['controls']={'requested':'custom'}
    elif setting=='increment':m['analysis_steps']['steps'][0]['initial']=.25
    else:m['analysis_steps']['steps'][0]['output_frequency']=2
    before=deepcopy(m)
    with pytest.raises(ValueError,match='고정 증분'):program(m,normalize(m,d))
    assert m==before
