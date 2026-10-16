"""Finite support: explicit full-tensor measures to common Cauchy, no solver."""
from pathlib import Path
from copy import deepcopy
import importlib.util,sys,json
import numpy as np
import pytest

ROOT=next(p for p in Path(__file__).resolve().parents if (p/'tests/test_post_comparison_physics.py').is_file())
sys.path.insert(0,str(ROOT/'tests'))
candidate=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('caelab.post_stress_candidate',candidate/'caelab/post_comparison.py')
c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)
from test_post_comparison_physics import recipe as base_recipe


def gradient(association='POINTS'):
    return {'array':'F','association':association,'units':'1','orientation':'current_from_reference',
        'basis':'fixed_cartesian','spatial_frame':'global','material_frame':'reference',
        'layout':{'kind':'tensor','components':list(c.COMPONENTS),'shear':'tensor','indices':'spatial_material_basis'},
        'validity_masks':[]}


def side(measure='pk1',association='POINTS'):
    result=base_recipe()['a']
    result.update(array='stress',measure=measure,association=association,
        frame='reference' if measure=='pk2' else 'global',
        layout={'kind':'tensor','components':list(c.COMPONENTS),'shear':'tensor',
                'indices':'spatial_material_basis' if measure=='pk1' else 'same_cartesian_basis'})
    if measure!='cauchy':result['deformation_gradient']=gradient(association)
    if measure=='pk1':result['material_frame']='reference'
    if association=='CELLS':result['projection']='cell_to_point_equal_incident'
    return result


def recipe():
    result=base_recipe();result.update(a=side('cauchy'),b=side(),selection='xy',
        stress_conversion={'version':1,'target_measure':'cauchy'})
    return result


@pytest.mark.parametrize('measure',['cauchy','pk1','pk2','kirchhoff'])
def test_shear_nonsymmetric_pk1_and_component_order(measure):
    F=np.array([[1,.5,0],[0,1,0],[0,0,1.]])
    S=np.diag([2.,3,5]);P=F@S;sigma=F@S@F.T
    values={'cauchy':sigma,'pk1':P,'pk2':S,'kirchhoff':sigma}[measure]
    s=side(measure);order=list(reversed(c.COMPONENTS));s['layout']['components']=order
    raw=np.array([[values['xyz'.index(k[0]),'xyz'.index(k[1])] for k in order]])
    actual=c.stress_to_cauchy(raw,s,[F.reshape(-1)],target_unit='MPa')
    np.testing.assert_allclose(actual.reshape(3,3),[[2.75,1.5,0],[1.5,3,0],[0,0,5]],rtol=0,atol=1e-14)
    if measure=='pk1': assert raw[0,order.index('xy')]!=raw[0,order.index('yx')]


def test_j_not_one_units_rotation_and_no_double_scaling():
    s=side();s['units']='Pa';F=np.diag([2.,1,1]);P=np.diag([6.,5,7])*1e6
    common=c.stress_to_cauchy([P.reshape(-1)],s,[F.reshape(-1)],target_unit='MPa')
    np.testing.assert_equal(common.reshape(3,3),np.diag([6.,2.5,3.5]))
    r=recipe();r['b']=s
    effective=c.effective_stress_side(s,r)
    Q=np.array([[0,-1,0],[1,0,0],[0,0,1.]])
    rotated=c.transform_values(common,effective,r['target'],Q)
    np.testing.assert_equal(rotated.reshape(3,3),Q@np.diag([6.,2.5,3.5])@Q.T)
    transformed=c.stress_to_cauchy([(Q@P).reshape(-1)],s,[(Q@F).reshape(-1)],target_unit='MPa')
    np.testing.assert_allclose(transformed,rotated,rtol=0,atol=1e-14)


@pytest.mark.parametrize('failure',['missing','orientation','association','frame','six_f','six_pk1','engineering','unit','same_array'])
def test_missing_or_ambiguous_auxiliary_input_blocks_only_conversion(failure):
    s=side();before=deepcopy(s)
    if failure=='missing':s.pop('deformation_gradient')
    elif failure=='orientation':s['deformation_gradient']['orientation']='reference_from_current'
    elif failure=='association':s['deformation_gradient']['association']='CELLS'
    elif failure=='frame':s['material_frame']='different'
    elif failure=='six_f':s['deformation_gradient']['layout']['components']=c.COMPONENTS[:6]
    elif failure=='six_pk1':s['layout']['components']=['xx','yy','zz','xy','xz','yz']
    elif failure=='engineering':s['layout']['shear']='engineering'
    elif failure=='unit':s['deformation_gradient']['units']='mm'
    elif failure=='same_array':s['deformation_gradient']['array']='stress'
    with pytest.raises(ValueError):c.stress_to_cauchy([np.eye(3).reshape(-1)],s,[np.eye(3).reshape(-1)],target_unit='MPa')
    assert before['measure']=='pk1'


@pytest.mark.parametrize('F',[np.diag([-1,1,1]),np.diag([0,1,1]),np.full((3,3),np.nan)])
def test_bad_unmasked_f_is_not_clamped_or_replaced(F):
    with pytest.raises(ValueError):c.stress_to_cauchy([np.eye(3).reshape(-1)],side(),[F.reshape(-1)],target_unit='MPa')
    result=c.stress_to_cauchy([np.full(9,np.nan)],side(),[F.reshape(-1)],target_unit='MPa')
    assert np.isnan(result).all()


def test_recipe_reopen_keeps_auxiliary_definition_and_output_measure():
    r=recipe();original=deepcopy(r);c.validate(r,[],[])
    reopened=json.loads(json.dumps(r));c.validate(reopened,[],[])
    assert reopened==original
    rows=c.output_declarations(r)['arrays']
    assert all(row['measure']=='cauchy' and row['frame']=='global' for row in rows)
    assert c.comparison_order(r).index('stress_measure_to_cauchy_at_native_endpoints')<c.comparison_order(r).index('association_projection')
    r.pop('stress_conversion')
    with pytest.raises(ValueError,match='measure'):c.validate(r,[],[])


def test_known_gradient_declaration_is_preserved():
    s=side();metadata={'arrays':[{'name':'F','association':'POINTS','components':9,'units':'1','frame':'global'}]}
    c.validate_gradient_declaration(s,metadata)
    metadata['arrays'][0]['units']='mm'
    with pytest.raises(ValueError,match='units'):c.validate_gradient_declaration(s,metadata)


@pytest.mark.parametrize('shear',['tensor','kelvin'])
def test_symmetric_six_pk2_uses_declared_shear_and_not_engineering(shear):
    s=side('pk2');s['layout']={'kind':'tensor','components':['xx','yy','zz','xy','yz','xz'],
        'shear':shear,'indices':'same_cartesian_basis'}
    F=np.array([[1,.5,0],[0,1,0],[0,0,1.]])
    S=np.array([[2.,1,0],[1,3,0],[0,0,5]])
    values=np.array([[2.,3,5,1,0,0]])
    if shear=='kelvin': values[:,3:]*=np.sqrt(2.)
    np.testing.assert_allclose(c.stress_to_cauchy(values,s,[F.reshape(-1)],target_unit='MPa').reshape(3,3),F@S@F.T)


def test_scaling_overflow_and_known_f_spatial_quality_are_not_silently_lost():
    s=side('cauchy');s['units']='MPa'
    with pytest.raises(ValueError,match='단위 변환'):c.stress_to_cauchy([np.full(9,1e308)],s,target_unit='Pa')
    s=side();metadata={'arrays':[{'name':'F','association':'POINTS','components':9,
        'validity_masks':['quality'],'spatial_mask':'inside'}]}
    with pytest.raises(ValueError,match='공간 마스크'):c.validate_gradient_declaration(s,metadata)
    s['deformation_gradient']['validity_masks']=['quality','inside']
    c.validate_gradient_declaration(s,metadata)


@pytest.mark.parametrize('test_name',[
    'test_pressure_units_missing_and_zero_denominator_are_independent',
    'test_temperature_absolute_and_difference_and_percent_basis',
    'test_reflection_measure_and_component_basis_are_not_silently_repaired'])
def test_selected_existing_physics_paths_remain_unchanged(test_name,monkeypatch):
    import test_post_comparison_physics as legacy
    monkeypatch.setattr(legacy,'c',c)
    getattr(legacy,test_name)()
