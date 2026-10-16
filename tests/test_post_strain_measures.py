"""Finite total strain formulas and rejected declarations, no solver."""
from copy import deepcopy
import json
import numpy as np
import pytest
from scipy.linalg import logm, expm
from caelab import post_comparison as p, post_strain_measures as s


def side(measure='green_lagrange', *, association='POINTS', gradient=False):
    result={'source_ref':'A','array':'strain','association':association,'quantity':'strain','units':'1',
        'measure':measure,'frame':'current' if measure=='euler_almansi' else 'reference',
        'coordinate_units':'mm','coordinate_frame':'current','strain_role':'total','reference_configuration':'undeformed specimen',
        'layout':{'kind':'tensor','components':list(p.COMPONENTS),'shear':'tensor','indices':'same_cartesian_basis'},
        'sampling':{'mode':'exact','time':None},'time_units':None,'time_origin':None,'validity_masks':[]}
    if gradient or measure=='euler_almansi':
        result['deformation_gradient']={'array':'F','association':association,'units':'1',
            'orientation':'current_from_reference','basis':'fixed_cartesian','spatial_frame':'current',
            'material_frame':'reference','validity_masks':[],
            'layout':{'kind':'tensor','components':list(p.COMPONENTS),'shear':'tensor','indices':'spatial_material_basis'}}
        result['strain_precision']={'kind':'declared_C_bound','absolute_tolerance':1e-13,'relative_tolerance':1e-13,
            'producer':'analytic manufactured fixture','format':'float64 strain/F, row-major9',
            'reference':'independent Schur log/exponential; float64 formula rounding bound'}
    if association=='CELLS':result['projection']='cell_to_point_equal_incident'
    return result


def recipe():
    a=side();b=side('euler_almansi');b['source_ref']='B'
    return {'version':2,'a':a,'b':b,'method':'same_mesh','tolerance':0.,'target':{'units':'1'},
        'selection':'xy','difference':'selected_difference','percent':'disabled','clock':{},
        'coverage':{'policy':'allow_partial','array':None},'conservation':{'mode':'none'},
        'strain_conversion':{'version':1,'target_measure':'green_lagrange'},
        'alignment':{'geometry_rotation':p.IDENTITY,'response_rotation':p.IDENTITY,'translation':[0.,0.,0.],
                     'geometry_declared':False,'response_declared':False}}


@pytest.mark.parametrize('measure',s.MEASURES)
def test_rotation_shear_analytic_and_independent_schur_exponential(measure):
    F=np.array([[1.,.7,0],[0,1.2,0],[0,0,.8]])
    Q=np.array([[0.,-1,0],[1,0,0],[0,0,1]])
    F=Q@F;C=F.T@F;E=(C-np.eye(3))/2
    H=logm(C)/2;e=(np.eye(3)-np.linalg.inv(F@F.T))/2
    original={'green_lagrange':E,'euler_almansi':e,'material_hencky':H}[measure]
    declaration=side(measure,gradient=True);raw=original.reshape(1,9).copy()
    actual=s.to_green_lagrange(raw,declaration,F.reshape(1,9),target_unit='1')
    np.testing.assert_allclose(actual.reshape(3,3),E,rtol=0,atol=1e-14)
    np.testing.assert_allclose(expm(2*H),C,rtol=0,atol=2e-14)
    np.testing.assert_equal(raw,original.reshape(1,9))


def test_uniaxial_hencky_no_f_and_small_values_avoid_cancellation():
    H=np.diag([np.log(2.),np.log(.5),1e-14])
    actual=s.to_green_lagrange(H.reshape(1,9),side('material_hencky'),target_unit='%').reshape(3,3)
    np.testing.assert_allclose(actual,np.diag([150.,-37.5,1e-12]),rtol=1e-14,atol=1e-14)
    compressed=s.to_green_lagrange(np.diag([-30.,0,0]).reshape(1,9),side('material_hencky'),target_unit='1')
    assert compressed[0,0]==-.5  # represented E limit; spectral C remains strictly positive


@pytest.mark.parametrize('shear,scale',[('tensor',1.),('engineering',2.),('kelvin',np.sqrt(2))])
def test_explicit_six_components_and_percent(shear,scale):
    declaration=side();declaration['units']='%'
    declaration['layout'].update(components=['yy','xx','zz','yz','xy','xz'],shear=shear)
    actual=s.to_green_lagrange([[20.,30.,0,0,5*scale,0]],declaration,target_unit='1')
    np.testing.assert_allclose(actual.reshape(3,3),[[.3,.05,0],[.05,.2,0],[0,0,0]],rtol=0,atol=1e-16)


@pytest.mark.parametrize('error',['missing_F','negative_J','nonsymmetric','not_SPD','wrong_measure','small','scalar','frame','reference','elastic','no_bound'])
def test_invalid_definition_or_kinematics_preserves_input(error):
    declaration=side('euler_almansi');F=np.eye(3).reshape(1,9);raw=np.zeros((1,9))
    if error=='missing_F':F=None
    elif error=='negative_J':F[0,0]=-1
    elif error=='nonsymmetric':raw[0,1]=1e-5
    elif error=='not_SPD':declaration=side();raw[0,0]=-.5
    elif error=='wrong_measure':declaration['measure']='spatial_hencky'
    elif error=='small':declaration['measure']='small_strain'
    elif error=='scalar':declaration['layout']={'kind':'scalar','components':['scalar']}
    elif error=='frame':declaration['frame']='reference'
    elif error=='reference':declaration['reference_configuration']='UNKNOWN'
    elif error=='elastic':declaration['strain_role']='elastic'
    elif error=='no_bound':declaration.pop('strain_precision')
    before=deepcopy(declaration);original=raw.copy()
    with pytest.raises(ValueError):s.to_green_lagrange(raw,declaration,F,target_unit='1')
    assert declaration==before;np.testing.assert_equal(raw,original)


def test_c_mismatch_is_not_hidden_by_symmetry_tolerance_and_masks_stay_missing():
    declaration=side('euler_almansi');F=np.diag([2.,1,1]).reshape(1,9)
    with pytest.raises(ValueError,match='FᵀF'):s.to_green_lagrange(np.zeros((1,9)),declaration,F,target_unit='1')
    declaration['strain_precision']['absolute_tolerance']=100.
    raw=np.zeros((1,9));raw[0,1]=.01
    with pytest.raises(ValueError,match='대칭'):s.to_green_lagrange(raw,declaration,F,target_unit='1')
    actual=s.to_green_lagrange(np.full((1,9),np.nan),declaration,np.full((1,9),np.nan),target_unit='1')
    assert np.isnan(actual).all()


def test_recipe_serialization_reference_basis_and_small_direct_comparison():
    value=recipe();before=deepcopy(value);p.validate(value,[],[])
    assert json.loads(json.dumps(value))==before
    assert all(row['frame']=='reference' and row['measure']=='green_lagrange' for row in p.output_declarations(value)['arrays'])
    assert p.comparison_order(value).index('strain_measure_to_green_lagrange_at_native_endpoints') < p.comparison_order(value).index('association_projection')
    value['b']['reference_configuration']='different'
    with pytest.raises(ValueError,match='기준 배치'):p.validate(value,[],[])
    value=recipe();value.pop('strain_conversion')
    value['a']=side();value['b']=side();value['a']['measure']=value['b']['measure']='small_strain'
    p.validate(value,[],[])  # old direct same-measure path remains available


def test_known_strain_role_and_gradient_declarations_cannot_be_overwritten():
    declaration=side('euler_almansi')
    metadata={'arrays':[{'name':'strain','association':'POINTS','strain_role':'elastic'},
                        {'name':'F','association':'POINTS','components':9}]}
    with pytest.raises(ValueError,match='원 선언'):s.validate_gradient_declaration(declaration,metadata)
    metadata['arrays'][0]['strain_role']='total';metadata['arrays'][1]['orientation']='reference_from_current'
    with pytest.raises(ValueError):s.validate_gradient_declaration(declaration,metadata)


def test_intrinsic_spd_and_offdiagonal_h_are_independent_of_declared_c_bound():
    declaration=side('euler_almansi');declaration['strain_precision']['absolute_tolerance']=100.
    with pytest.raises(ValueError,match='I−2e'):
        s.to_green_lagrange(np.diag([.5,0,0]).reshape(1,9),declaration,np.eye(3).reshape(1,9),target_unit='1')
    H=np.array([[0.,np.log(2),0],[np.log(2),0,0],[0,0,0]])
    no_f=side('material_hencky');no_f['strain_precision']={'incomplete_inactive_bound':'preserved'}
    actual=s.to_green_lagrange(H.reshape(1,9),no_f,target_unit='1')
    np.testing.assert_allclose(actual.reshape(3,3),[[.5625,.9375,0],[.9375,.5625,0],[0,0,0]],rtol=0,atol=1e-15)


def test_existing_stress_conversion_remains_on_its_original_route():
    F=np.diag([2.,1,1]);P=np.diag([6.,5,7])
    declaration=side('euler_almansi')
    declaration.update(quantity='stress',measure='pk1',units='MPa',frame='current',material_frame='reference')
    declaration['layout']['indices']='spatial_material_basis'
    actual=p.stress_to_cauchy(P.reshape(1,9),declaration,F.reshape(1,9),target_unit='MPa')
    np.testing.assert_equal(actual.reshape(3,3),np.diag([6.,2.5,3.5]))


def test_large_frobenius_residual_and_known_producer_bound_are_not_hidden():
    # Squared-sum norms would overflow here and could falsely compare inf<=inf.
    assert not s._close(np.eye(3)[None]*2e200,np.eye(3)[None]*1e200,0.,1e-13).any()
    assert not s._close(2*np.eye(3)[None],2*np.eye(3)[None],0.,1e308).any()
    declaration=side('euler_almansi')
    metadata={'arrays':[{'name':'strain','association':'POINTS','strain_precision':deepcopy(declaration['strain_precision'])},
                        {'name':'F','association':'POINTS','components':9}]}
    s.validate_gradient_declaration(declaration,metadata)
    declaration['strain_precision']['absolute_tolerance']=1.
    with pytest.raises(ValueError,match='원 선언'):s.validate_gradient_declaration(declaration,metadata)
