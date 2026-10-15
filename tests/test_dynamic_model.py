from copy import deepcopy
import pytest
from test_dynamic_support import base_model,draft_for,dynamic_model
from caelab.dynamic_model import density,attach,check_shape,DynamicInputError
from caelab.contact_deck import render
from caelab.contact_steps import compile_program
from caelab.calculix_dynamic import stage_contract,location


def test_units_native_initial_conditions_and_distinct_damping():
    m=base_model();d=draft_for(m);d['rayleigh']={'alpha_per_s':'2','beta_s':'.003'}
    for kind,v in [('U','.01'),('V','100')]:
        d['initial_conditions'].append({'id':kind,'label':kind,'kind':kind,'component':1,'value':v,
                                      'target':{'body_id':'Solid','native_node_ids':[51]}})
    result=attach(m,d);deck=render(result)
    assert density(7800)==7.8e-9
    assert '*DAMPING,ALPHA=2,BETA=0.003' in deck
    assert '*INITIAL CONDITIONS,TYPE=DISPLACEMENT\n4,1,0.01' in deck
    assert '*INITIAL CONDITIONS,TYPE=VELOCITY\n4,1,100' in deck
    assert ',ALPHA=-0.05' in deck
    assert '*RESTART,WRITE,FREQUENCY=1' in deck
    assert m==base_model() and d['initial_conditions'][0]['value']=='.01'


@pytest.mark.parametrize('bad',['1e','',-1,0,float('inf'),float('nan')])
def test_invalid_density_never_freezes(bad):
    m=base_model();d=draft_for(m);d['densities'][0]['kg_m3']=bad
    with pytest.raises(ValueError):attach(m,d)
    if isinstance(bad,str):check_shape(d)


@pytest.mark.parametrize('part,value',[('numerical_alpha',.1),('numerical_alpha',-.34),('restart_frequency','1.5'),('restart_frequency','0')])
def test_bad_numerical_settings(part,value):
    m=base_model();d=draft_for(m);d[part]=value
    with pytest.raises(ValueError):attach(m,d)


def test_missing_duplicate_fixed_initial_targets():
    for node,dof,duplicate in [(999,1,False),(11,1,False),(51,1,True)]:
        m=base_model();d=draft_for(m)
        row={'id':'i','label':'v','kind':'V','component':dof,'value':'1','target':{'body_id':'Solid','native_node_ids':[node]}}
        d['initial_conditions']=[row]
        if duplicate:d['initial_conditions'].append(dict(deepcopy(row),id='j'))
        with pytest.raises(ValueError):attach(m,d)


def test_static_preload_release_and_time_no_fabricated_seconds():
    m=dynamic_model(mixed=True);deck=render(m);stages=stage_contract(m)
    assert deck.index('*STATIC')<deck.index('*DYNAMIC')
    assert deck.count('ELKE,ELSE,ENER')==2
    assert stages[0]['physical_end_s'] is None
    assert stages[1]['physical_start_s']==0 and stages[1]['physical_end_s']==1
    loc=location(m,2,1.2)
    assert loc['physical_time_s']==pytest.approx(.2)
    assert loc['native_global_coordinate']==1.2 and loc['wall_time_s'] is None
    assert list(compile_program(m['analysis_steps'],m['conditions'])[1]['loads'].values())==[[[0.,0.],[1.,0.]]]


def test_dynamic_to_static_is_saved_but_not_admitted():
    m=dynamic_model(mixed=True);d=deepcopy(m['dynamic']['draft']);d['program']['steps'].reverse()
    check_shape(d)
    with pytest.raises(DynamicInputError,match='선행'):attach(base_model(),d)


def test_frozen_values_are_rederived():
    m=dynamic_model();m['dynamic']['rayleigh']['alpha_per_s']=1
    with pytest.raises(ValueError):render(m)
