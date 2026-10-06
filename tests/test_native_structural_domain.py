"""Declared capability admission, TEST_ONLY geometry; no runtime qualification."""
from copy import deepcopy
import pytest
from plugins.elasticity.native_conditions import support, project


def inputs():
    catalog={'cad_backend':'fixture.freecad','coordinate_systems':[{'id':'global'}],
        'native_catalog_revision':'a'*64,'selections':[{'id':'B-final','kind':'whole_final_solid','roles':['material']},
        *[{'id':f'F{i}','kind':'native_face','roles':['boundary','load']} for i in range(1,5)]]}
    declaration={'coordinate_system':'global','materials':[{'id':'M1','selection_id':'B-final',
        'law':'isotropic_linear_elastic','young_modulus_MPa':210000.,'poisson_ratio':.3,
        'source':{'category':'ASSUMED','description':'TEST_ONLY unmeasured elastic constants'}}],
        'boundary_conditions':[{'id':'BC1','selection_id':'F1','coordinate_system':'global',
        'components':{'UX':0},'source':'TEST_ONLY partial symmetry constraint'}],
        'loads':[{'id':'L1','selection_id':'F2','coordinate_system':'global',
        'components':{'FX':150.,'FY':0.,'FZ':0.},'source':'TEST_ONLY signed face force'}],
        'contact':{'mode':'none','source':'TEST_ONLY no contact'},'mesh':{'mode':'selected','max_size_mm':4.},
        'analysis_type':'linear_static','units':{'length':'mm','force':'N','stress':'MPa'}}
    return catalog,declaration


def test_partial_dof_projection_is_frozen_without_implicit_zero_or_runtime_qualification():
    c,d=inputs(); before=deepcopy((c,d))
    verdict=support(c,d)
    assert verdict=={'status':'SUPPORTED_DECLARED_INPUTS','reasons':[],'native_runtime':'NOT_CHECKED'}
    projected=project(c,d)
    assert projected['declaration']['boundary_conditions'][0]['components']=={'UX':0}
    d['boundary_conditions'][0]['components']['UY']=1
    assert projected['declaration']==before[1] and projected['native_catalog']==before[0]


@pytest.mark.parametrize('kind',['other_cad','no_faces','zero_load','no_boundary','contact'])
def test_unsupported_physics_is_saved_as_unsupported_and_never_projected(kind):
    c,d=inputs()
    if kind=='other_cad':c['cad_backend']='fixture.cadquery'
    if kind=='no_faces':
        for row in c['selections'][1:]:row['kind']='physical_group'
    if kind=='zero_load':d['loads'][0]['components']['FX']=0
    if kind=='no_boundary':d['boundary_conditions']=[]
    if kind=='contact':d['contact']={'mode':'frictionless','source':'TEST_ONLY',
        'pairs':[{'selection_a':'F1','selection_b':'F2'}]}
    assert support(c,d)['status'].startswith('UNSUPPORTED')
    with pytest.raises(ValueError):project(c,d)


@pytest.mark.parametrize('kind',['stale_face','wrong_role','empty_dofs','wrong_dof','nonfinite','unstable_material'])
def test_invalid_declared_geometry_and_values_are_refused(kind):
    c,d=inputs()
    if kind=='stale_face':d['loads'][0]['selection_id']='F-from-another-revision'
    if kind=='wrong_role':d['loads'][0]['selection_id']='B-final'
    if kind=='empty_dofs':d['boundary_conditions'][0]['components']={}
    if kind=='wrong_dof':d['boundary_conditions'][0]['components']={'FX':0}
    if kind=='nonfinite':d['loads'][0]['components']['FX']=float('nan')
    if kind=='unstable_material':d['materials'][0]['poisson_ratio']=.5
    with pytest.raises(ValueError):project(c,d)
