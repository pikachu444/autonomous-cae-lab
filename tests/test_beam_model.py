from copy import deepcopy
import math
import pytest
from caelab.beam_model import *
from caelab.beam_deck import render,parse_native_mesh
from test_beam_support import model,refresh


@pytest.mark.parametrize('value',['1e','1e+','',True,float('nan'),'inf','2 mm',None])
def test_unfinished_and_nonfinite_numbers_are_rejected(value):
    with pytest.raises(BeamInputError):number(value)


@pytest.mark.parametrize('value',['0','1e'])
def test_invalid_scalar_draft_remains_exact_json_data(value):
    import json
    d=model()['draft'];d['section']['width_mm']=value
    check_draft_shape(d);copy=json.loads(json.dumps(d));assert copy['section']['width_mm']==value
    assert validate_draft(copy)[0]['path']=='section.width_mm'


def test_rect_width_height_and_positive_native_rotation():
    v=model();p=section_properties(v['draft'])
    assert p==pytest.approx({'area_mm2':200.,'I1_mm4':6666.666666666667,'I2_mm4':1666.6666666666667})
    assert v['axes']=={'local1':[0.,1.,0.],'local2':[0.,0.,1.],'tangent':[1.,0.,0.]}
    rotated=model(90);assert rotated['axes']['local1']==pytest.approx([0,0,1])
    assert rotated['axes']['local2']==pytest.approx([0,-1,0])
    assert rotated['loads']==v['loads']  # Global load NEVER rotates with section.
    assert section_properties(rotated['draft'])==p


def test_direct_moment_dof_and_degree_boundary_are_not_a_force_couple():
    v=model();v['draft']['ends'][0]['rotation_deg'][1]='1';refresh(v)
    text=render(v)
    assert '*CLOAD\n509,5,1000\n' in text
    assert '101,5,5,'+format(math.pi/180,'.13G') in text
    assert '*RIGID BODY' not in text and 'C3D20' not in text
    assert '*NODE FILE, OUTPUT=2D, GLOBAL=YES' in text and 'OUTPUT=3D' not in text
    assert '*EL FILE, SECTION FORCES\nS' in text
    assert '*ELEMENT, TYPE=B32R' in text
    assert '88,101,408,207' in text


def test_static_step_explicitly_preserves_calculix_effective_increment_defaults():
    lines=render(model()).splitlines()
    increments=[float(value) for value in lines[lines.index('*STATIC')+1].split(',')]
    # ccx warns and replaces a missing/zero minimum by min(initial, period*1e-6).
    initial,period,minimum,maximum=increments
    assert initial==period==1.0
    assert minimum==min(initial,period*1e-6)
    assert maximum==1e30


def test_local_triplets_and_free_dofs_have_distinct_meanings():
    a=model(90)['axes']
    assert to_global([2,3,4],'local',a)==pytest.approx([4,-3,2])
    assert boundary_global(['','1',''],'local',a,'r')==[None,-1.,None]
    a=frame([1,0,0],native_axis_formula([1,0,0],45))
    with pytest.raises(BeamInputError):boundary_global(['1','',''],'local',a,'r')
    assert boundary_global(['0','0','0'],'local',a,'r')==pytest.approx([0,0,0])


@pytest.mark.parametrize('damage',['solid','linear_edge','reorder','reversed','duplicate_node','duplicate_element',
    'duplicate_mid','isolated','not_mid','off_edge','parallel_axis','bad_local2','wrong_units','free_body','same_end','forged_load','zero_length'])
def test_invalid_native_geometry_constraints_or_correspondence_blocks_input(damage):
    v=model()
    if damage=='solid':v['element']='C3D20'
    elif damage=='linear_edge':v['elements'][0]['native_nodes']=[101,207]
    elif damage=='reorder':v['elements'][0]['ccx_nodes']=[101,207,408]
    elif damage=='reversed':v['elements'][0].update(native_nodes=[207,101,408],ccx_nodes=[207,408,101])
    elif damage=='duplicate_node':v['nodes'].append(deepcopy(v['nodes'][0]))
    elif damage=='duplicate_element':v['elements'].append(deepcopy(v['elements'][0]))
    elif damage=='duplicate_mid':v['elements'][1].update(native_nodes=[207,509,408],ccx_nodes=[207,408,509])
    elif damage=='isolated':v['nodes'].append({'id':999,'xyz_mm':[600,0,0]})
    elif damage=='not_mid':v['nodes'][1]['xyz_mm'][0]=260
    elif damage=='off_edge':v['nodes'][1]['xyz_mm'][1]=1
    elif damage=='parallel_axis':v['axes']['local1']=[1,0,0]
    elif damage=='bad_local2':v['axes']['local2']=[0,1,0]
    elif damage=='wrong_units':v['units']['moment']='Nm'
    elif damage=='free_body':v['draft']['ends'][0]['rotation_deg']=['']*3;refresh(v)
    elif damage=='same_end':v['end_node_ids']=[101,101]
    elif damage=='forged_load':v['loads'][0]['value']=999
    elif damage=='zero_length':v['edge_end_mm']=[0,0,0]
    with pytest.raises((BeamInputError,ValueError)):render(v)


def test_oblique_requires_explicit_diagnostic_and_keeps_global_values():
    with pytest.raises(BeamInputError):model(direction=(.7,1.4,-2))
    v=model(direction=(.7,1.4,-2),diagnostic=True)
    assert v['loads']==[{'node':509,'dof':5,'value':1000.,'unit':'Nmm'}]
    assert cross(v['axes']['local1'],v['axes']['local2'])==pytest.approx(v['axes']['tangent'])


def test_native_mesh_portion_cannot_smuggle_solid_or_duplicate():
    text='*NODE\n101,0,0,0\n207,1,0,0\n408,.5,0,0\n*ELEMENT,TYPE=B32R\n88,101,408,207\n'
    nodes,elements=parse_native_mesh(text);assert elements=={88:[101,408,207]}
    with pytest.raises(ValueError):parse_native_mesh(text.replace('B32R','C3D20'))
    with pytest.raises(ValueError):parse_native_mesh(text+'88,101,408,207\n')


@pytest.mark.parametrize('value',[float('nan'),float('inf'),-1,0])
def test_nonfinite_or_negative_length_is_not_a_valid_snapshot(value):
    v=model();v['length_mm']=value
    with pytest.raises(BeamInputError):validate_model(v)
