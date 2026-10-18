"""Existing pinned converter/postflight on newly admitted hierarchical families."""
from copy import deepcopy
from pathlib import Path
import sys
import pytest
from test_assembly_physics import flat_source, hierarchical
from caelab.impact_model import default_settings, model_from_settings, render
from caelab.impact_assembly import target_key
from caelab.impact_initial_state import describe
from caelab.execution_control import run_owned_command
from caelab.adapters import inp2rad_worker
from caelab.adapters.impact import converted_mesh
from caelab.adapters.impact_admission import global_gravity, normalize_surfaces, normalize_elastic_tetra4, validate_physics


def settings(kind, plastic=False):
    result=default_settings();result['source']['text']=hierarchical(flat_source(kind,plastic))
    model=model_from_settings(result)
    result['motions']=[{'node_set':target_key(model,'nsets','DROP.BODY-2.BODY'), 'mode':'velocity','height_mm':None,
        'velocity_mm_s':[2.,-3.,4.],'omega_rad_s':[0.,0.,2.],'center_mm':[0.,30.,0.],
        'translation_mm':[1.,2.,3.], 'pose':{'rotation':[[0.,-1.,0.],[1.,0.,0.],[0.,0.,1.]], 'frame':'MODEL_GLOBAL','vector_frame':'INITIAL_BODY'}}]
    if kind=='COH3D8':
        from examples.impact.cohesive_model import settings as cohesive
        result['cohesive']=[{**cohesive()['cohesive'][0],'material':'MAT'}]
    return result


@pytest.mark.parametrize('kind,plastic',[('C3D10',False),('C3D8',True),('C3D8R',True),('COH3D8',False)])
def test_hierarchy_existing_converter_mesh_physics_material_ip_ic(tmp_path,kind,plastic):
    definition=settings(kind,plastic);model=model_from_settings(definition);text,initial=render(definition)
    flat=deepcopy(definition);flat['source']['text']=model['compiled_text']
    flat_text,flat_initial=render(flat)
    assert flat_text==text and flat_initial==initial
    original_nodes={n:position for n,position in model['nodes'].items() if n in model['nsets'][target_key(model,'nsets','DROP.BODY-1.BODY')]}
    assert {n:initial['nodes'][n] for n in original_nodes}==original_nodes
    assert set(initial['velocities_mm_s'])==model['nsets'][target_key(model,'nsets','DROP.BODY-2.BODY')]
    report=describe(model,initial,definition)
    assert report['original']['status']==report['initial']['status']=='UNKNOWN'
    assert report['native_body_mass_inertia']=='UNKNOWN'
    path=tmp_path/'impact.inp';path.write_text(text,encoding='ascii')
    result=run_owned_command([sys.executable,inp2rad_worker.__file__,str(path)],tmp_path,'convert',timeout=30,owned_tree=True)
    assert result.returncode==0
    native=tmp_path/'impact_0000.rad'
    assert converted_mesh(native,model,initial['nodes'])['element_count']==2
    effective,_=normalize_surfaces(native.read_text(encoding='ascii'),model)
    effective,_=global_gravity(effective,definition['gravity_mm_s2'])
    normalized,receipt=normalize_elastic_tetra4(effective,model,initial,definition)
    assert normalized==effective and not receipt['changed']
    physics=validate_physics(effective,model,initial,definition)
    assert len(physics['material_by_element'])==2
    assert physics['velocity_node_count']==len(initial['velocities_mm_s'])
    if plastic:
        assert '/MAT/PLAS_TAB/' in effective or '/MAT/LAW36/' in effective
    if kind=='COH3D8':
        from caelab.impact_damage import apply_laws,verify_laws
        changed,law=apply_laws(effective,{**model,'nodes':initial['nodes']},definition['cohesive'])
        verify_laws(changed,model,definition['cohesive'],law)
        assert set(law['elements'])=={'1','2'}
