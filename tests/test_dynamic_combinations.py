from copy import deepcopy
import pytest
from test_contact_execution import model as contact_model
from test_contact_steps import staged
from test_dynamic_support import base_model,draft_for
from caelab.dynamic_model import attach,default_draft
from caelab.contact_deck import render
from caelab.calculix_material import default_plasticity,J2


@pytest.mark.parametrize('plastic',[False,True])
@pytest.mark.parametrize('geometry',['linear','nonlinear'])
@pytest.mark.parametrize('mixed',[False,True])
def test_contact_elastic_j2_geometry_and_preload_cards(contact_model,plastic,geometry,mixed):
    m=staged(contact_model);m['step']['geometry']=geometry
    if plastic:
        for material in m['materials']:
            p=default_plasticity();p['yield_points']=[['200','0'],['250','.01']]
            material.update(law=J2,plasticity=p)
    draft=default_draft('Analysis','Solver',m['analysis_steps'],[
        {'body_id':r['body_id'],'material_id':r['object_id'],'kg_m3':'7800'} for r in m['materials']])
    if mixed:draft['program']['procedure']='mixed';draft['program']['steps'][0]['procedure']='static'
    result=attach(m,draft);text=render(result)
    assert '*DYNAMIC' in text and '*DAMPING' in text and '*CONTACT PAIR' in text
    assert ('*PLASTIC' in text)==plastic and ('PEEQ' in text)==plastic
    assert text.count('*DENSITY')==2
    assert ('*STATIC' in text)==mixed


def test_initial_velocity_without_external_load_is_not_replaced_by_force():
    m=base_model();m['loads']=[];m['conditions']=m['conditions'][:1]
    draft=draft_for(m);draft['initial_conditions']=[{'id':'v','label':'초기속도','kind':'V','component':3,
        'value':'1','target':{'body_id':'Solid','native_node_ids':[51]}}]
    text=render(attach(m,draft))
    assert '*INITIAL CONDITIONS,TYPE=VELOCITY' in text
    # Existing compiler explicitly clears prior loads. No CLOAD data/force
    # may be synthesized to replace the physical initial velocity.
    lines=text.splitlines()
    for index,line in enumerate(lines):
        if line.startswith('*CLOAD'):
            assert line=='*CLOAD,OP=NEW' and lines[index+1].startswith('*')


def test_dynamic_line_search_not_silently_applied_as_static_control():
    m=base_model();m['step']['line_search_controls']={'enabled':True,'minimum':'.01','maximum':'1.','residual_factor':'.25'}
    with pytest.raises(ValueError):attach(m,draft_for(m))
