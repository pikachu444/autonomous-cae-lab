from copy import deepcopy
import pytest
from pretension_fixture import model
from caelab.pretension import normalize,sections,validate_cut,face_catalog,expected_solver_mesh
from caelab.contact_deck import render
from caelab.pretension_deck import step_cards,output_cards


def test_actual_shared_faces_native_cards_hold_and_copy_identity():
    source=model();before=deepcopy(source);rows=sections(source)
    assert len(face_catalog(source,'Bolt'))==1 and rows[0]['node_ids']==[1,2,3,6,7,8]
    deck=render(source)
    assert '*PRE-TENSION SECTION,SURFACE=PTSECPbolt,NODE=15\n0,0,1' in deck
    assert step_cards(source,1)==['*CLOAD','15,1,600']
    assert step_cards(source,2)==step_cards(source,3)==['*BOUNDARY,FIXED','15,1,1']
    assert 'FREQUENCYF=1' in '\n'.join(output_cards(source,',FREQUENCY=1'))
    effective,copies=expected_solver_mesh(source)
    assert len(copies)==6 and {r['solver_node_id'] for r in copies}==set(range(16,22))
    assert len(effective['nodes'])==20 and 15 not in {r['node_id'] for r in effective['nodes']}
    assert effective['elements'][1]['node_ids']==source['elements'][1]['node_ids']
    assert set(effective['elements'][0]['node_ids'])&set(source['elements'][0]['node_ids'])=={4,9,10,11}
    assert source==before
    displacement=model('section_displacement_mm')
    assert step_cards(displacement,1)==['*BOUNDARY','15,1,1,0.01']
    assert step_cards(displacement,2)==['*BOUNDARY,FIXED','15,1,1']


@pytest.mark.parametrize('change',[
    lambda m:m['pretension_sections'][0]['draft'].update(axis=[0,0,0]),
    lambda m:m['pretension_sections'][0]['draft'].update(element_faces=[[1,2]]),
    lambda m:m['pretension_sections'][0]['draft'].update(element_faces=[[1,1],[2,1]]),
    lambda m:m['pretension_sections'][0]['draft'].update(axis=[1,0,0]),
    lambda m:m['pretension_sections'].append(deepcopy(m['pretension_sections'][0])),
    lambda m:m['pretension_sections'][0]['draft']['control'].update(kind='torque_Nmm'),
    lambda m:m['analysis_steps']['steps'].pop(),
])
def test_invalid_cut_axis_duplicate_and_control_are_not_exported(change):
    source=model();change(source);before=deepcopy(source)
    with pytest.raises(ValueError):sections(source)
    assert source==before


def test_existing_topology_rejects_nonconforming_quadratic_face_and_source_change():
    source=model();source['elements'][1]['node_ids'][4]=9
    with pytest.raises(ValueError,match='중간 절점'):face_catalog(source,'Bolt')
    source=model();source['pretension_sections'][0]['draft']['element_faces']=[[2,1]]
    with pytest.raises(ValueError,match='법선'):sections(source)
    source['pretension_sections'][0]['draft']['axis']=[0,0,-1]
    assert sections(source)[0]['node_ids']==[1,2,3,6,7,8]


def test_public_settings_and_exact_cut_support_boundary():
    from caelab.adapters.pretension_fem import PretensionFemCalculixAdapter as Adapter
    assert Adapter.validate_settings({'data_id':'Dbolt'})=={'data_id':'Dbolt'}
    with pytest.raises(ValueError):Adapter.validate_settings({'snapshot_path':'C:/any/snapshot.json'})
    source=model();source['conditions'][-1]['boundary_dofs'].append({'node_id':1,'component':3,'value_mm':0.})
    source['conditions'][-1]['components_mm'][3]=0.
    from caelab.pretension import three_step_program
    source['analysis_steps']=three_step_program(source['step'],source['conditions'])
    with pytest.raises(ValueError,match='축방향 지지'):sections(source)
