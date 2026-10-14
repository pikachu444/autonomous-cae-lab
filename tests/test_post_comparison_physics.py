"""Small manufactured physical contracts; no ParaView/solver/provider calls."""
from copy import deepcopy
import math
import numpy as np
import pytest
from caelab import post_comparison as c


def recipe():
    side = {'source_ref': 'A', 'array': 'stress', 'association': 'POINTS',
        'quantity': 'stress', 'units': 'MPa', 'measure': 'cauchy', 'frame': 'global',
        'coordinate_units': 'mm', 'coordinate_frame': 'global',
        'layout': {'kind': 'scalar', 'components': ['scalar']},
        'sampling': {'mode': 'exact', 'time': None}, 'time_units': None, 'time_origin': None}
    return {'version': 2, 'a': deepcopy(side), 'b': deepcopy(side), 'method': 'same_mesh',
        'tolerance': 0., 'target': {'units': 'MPa'}, 'selection': 'scalar', 'percent': 'relative_a',
        'difference': 'selected_difference', 'clock': {},
        'alignment': {'geometry_rotation': deepcopy(c.IDENTITY), 'response_rotation': deepcopy(c.IDENTITY),
            'translation': [0., 0., 0.], 'geometry_declared': False, 'response_declared': False}}


def test_pressure_units_missing_and_zero_denominator_are_independent():
    r = recipe(); r['b']['units'] = 'Pa'
    c.validate(r, [], [])
    a = c.transform_values([[2.], [0.], [4.], [1.]], r['a'], r['target'], c.IDENTITY)
    b = c.transform_values([[2e6], [1e6], [math.nan], [2e6]], r['b'], r['target'], c.IDENTITY)
    result = c.compare(a, b, r, [True, True, True, False])
    np.testing.assert_allclose(result['delta'][:2], [0, 1])
    assert result['valid'].tolist() == [True, True, False, False]
    assert result['percent_reason'].tolist() == [0, 5, 3, 1]
    assert np.isnan(result['percent'][1:]).all()


def test_geometry_scale_rotation_translation_does_not_scale_force():
    r = recipe()
    side = dict(r['b'], quantity='force', units='N', measure='force',
                layout={'kind': 'vector', 'components': ['x', 'y', 'z']})
    rotation = [[0., -1., 0.], [1., 0., 0.], [0., 0., 1.]]
    np.testing.assert_allclose(c.transform_points([[1,0,0]], 'm', 'mm', rotation, [10,20,30]), [[10,1020,30]])
    np.testing.assert_allclose(c.transform_values([[1,2,3]], side, {'units': 'N'}, rotation), [[-2,1,3]])


@pytest.mark.parametrize('shear,values', [
    ('tensor', [0,0,0,.01,0,0]), ('engineering', [0,0,0,.02,0,0]),
    ('kelvin', [0,0,0,.01 * math.sqrt(2),0,0])])
def test_explicit_tensor_convention_rotation(shear, values):
    s = math.sqrt(.5)
    layout = {'kind': 'tensor', 'components': ['xx','yy','zz','xy','yz','xz'], 'shear': shear}
    side = dict(recipe()['b'], units='1', quantity='strain', measure='strain', layout=layout)
    actual = c.transform_values([values], side, {'units': '1'}, [[s,-s,0],[s,s,0],[0,0,1]])
    np.testing.assert_allclose(actual.reshape(3,3), np.diag([-.01,.01,0]), atol=1e-17)


def test_non_symmetric_tensor_preserves_all_nine_components():
    side = dict(recipe()['b'], layout={'kind': 'tensor', 'components': c.COMPONENTS, 'shear': 'tensor'})
    tensor = np.array([[2,1,3],[7,4,5],[8,9,6.]])
    rotation = np.array([[0,-1,0],[1,0,0],[0,0,1.]])
    actual = c.transform_values([tensor.ravel()], side, {'units':'MPa'}, rotation.tolist())
    np.testing.assert_equal(actual.reshape(3,3), rotation @ tensor @ rotation.T)


def test_temperature_absolute_and_difference_and_percent_basis():
    r = recipe()
    for side in ('a','b'):
        r[side].update(quantity='temperature', measure='temperature', temperature_kind='absolute')
    r['a']['units'] = 'degC'; r['b']['units'] = 'K'; r['target']['units'] = 'degC'
    with pytest.raises(ValueError, match='Kelvin'): c.validate(r, [], [])
    r['percent'] = 'absolute_kelvin'; c.validate(r, [], [])
    a = c.transform_values([[20]], r['a'], r['target'], c.IDENTITY)
    b = c.transform_values([[303.15]], r['b'], r['target'], c.IDENTITY)
    result = c.compare(a,b,r,[True])
    assert result['delta'][0] == pytest.approx(10)
    assert result['percent'][0] == pytest.approx(1000/293.15)
    assert c.affine_unit('degC','K','temperature','difference') == (1.,0.)


def test_exact_equivalent_clocks_and_explicit_bracket_gap():
    side = recipe()['b']; side.update(time_units='ms', time_origin='physical_time', clock_offset=1.)
    common = {'value': 1.25, 'unit': 's', 'semantics': 'physical_time'}
    side['sampling'] = {'mode':'linear','bracket':[0.,1000.], 'max_gap':1.}
    result = c.time_plan(side,[0.,1000.],common)
    assert result['weights'] == [.75,.25]
    side['sampling']['max_gap'] = .5
    with pytest.raises(ValueError, match='간격'): c.time_plan(side,[0.,1000.],common)
    side['sampling'] = {'mode':'exact','time':1000.}
    assert c.time_plan(side,[0.,1000.],dict(common,value=2.))['weights'] == [1.]
    with pytest.raises(ValueError): c.time_plan(side,[0.,1000.],dict(common,value=4.))


def test_norms_and_component_selection_are_after_interpolation():
    r = recipe()
    r.update(selection='magnitude', difference='selected_difference')
    for side in ('a','b'): r[side]['layout'] = {'kind':'vector','components':['x','y','z']}
    result = c.compare(np.array([[1.,0,0]]), np.array([[-1.,0,0]]), r, [True])
    assert result['delta'][0] == 0.
    r['difference'] = 'norm_of_difference'
    assert c.compare(np.array([[1.,0,0]]),np.array([[-1.,0,0]]),r,[True])['delta'][0] == 2.
    assert c.scalar(np.array([[1.,0,0]])*.5 + np.array([[-1.,0,0]])*.5,'vector','magnitude')[0] == 0.


def test_reflection_measure_and_component_basis_are_not_silently_repaired():
    r = recipe()
    r['alignment']['response_rotation'] = [[-1,0,0],[0,1,0],[0,0,1]]
    with pytest.raises(ValueError, match='회전행렬'): c.validate(r,[],[])
    r = recipe(); r['b']['measure']='second_piola'
    with pytest.raises(ValueError,match='measure'): c.validate(r,[],[])
    r = recipe(); r['b']['frame']='local'; r['alignment']['response_declared']=True
    with pytest.raises(ValueError,match='원 벡터'): c.validate(r,[],[])


def test_static_load_parameter_cannot_be_interpolated_or_renamed_seconds():
    side = recipe()['a']; side.update(time_units='1',time_origin='STATIC_LOAD_PARAMETER')
    side['sampling']={'mode':'linear','bracket':[0.,1.],'max_gap':1.}
    with pytest.raises(ValueError, match='정적'): c.time_plan(side,[0.,1.],{'value':.5,'unit':'1','semantics':'STATIC_LOAD_PARAMETER'})


def test_exact_clock_has_no_epoch_relative_tolerance_and_requires_unique_sample():
    side = recipe()['a']; side.update(time_units='s', time_origin='physical_time')
    side['sampling'] = {'mode':'exact', 'time':1e9 + .0005}
    clock = {'unit':'s', 'semantics':'physical_time', 'value':1e9}
    with pytest.raises(ValueError, match='정확 시각'):
        c.time_plan(side,[1e9 + .0005],clock)
    clock['exact_tolerance']=.001
    assert c.time_plan(side,[1e9 + .0005],clock)['exact_tolerance']==.001
    with pytest.raises(ValueError, match='모호'):
        c.time_plan(side,[1e9,1e9 + .0005],clock)


def test_large_vector_norm_and_norm_relative_difference_use_full_baseline():
    r=recipe(); r.update(selection='x',difference='norm_of_difference')
    for side in ('a','b'): r[side]['layout']={'kind':'vector','components':['x','y','z']}
    result=c.compare(np.array([[1e200,0,0.]]),np.array([[1e200,1,0.]]),r,[True])
    assert result['delta'][0]==1. and result['percent_valid'][0]
    assert result['percent'][0] > 0.
    assert result['percent'][0]==pytest.approx(1e-198, rel=1e-12, abs=0)
    r['selection']='magnitude'
    assert c.scalar(np.array([[1e200,0,0.]]),'vector','magnitude')[0] == 1e200
    assert c.compare(np.array([[1e200,0,0.]]),np.array([[1e200,1,0.]]),r,[True])['percent'][0] > 0.
    result=c.compare(np.array([[0.,10,0]]),np.array([[0.,11,0]]),r,[True])
    assert result['percent'][0]==pytest.approx(10.)



def test_ordered_match_uses_declared_absolute_distance_without_rounding_coordinates():
    a = np.array([[1., 0., 0.], [0., 1., 0.], [0., 0., 1.]])
    s = math.sqrt(.5); rotation = np.array([[s,-s,0.],[s,s,0.],[0.,0.,1.]])
    raw_b = a @ rotation
    transformed = c.transform_points(raw_b, 'mm', 'mm', rotation, [0.,0.,0.])
    cells = [(5, (0,1,2))]
    assert not np.array_equal(a, transformed)
    original = transformed.copy()
    match = c.ordered_match(a, cells, transformed, cells, 1e-12)
    assert 0 < match['maximum_distance'] <= 1e-12
    np.testing.assert_array_equal(transformed, original)
    with pytest.raises(ValueError, match='허용 오차'):
        c.ordered_match(a, cells, transformed, cells, 0.)
    with pytest.raises(ValueError, match='허용 오차'):
        c.ordered_match(a, cells, transformed + [0.,0.,.001], cells, 1e-12)
    with pytest.raises(ValueError, match='연결 순서'):
        c.ordered_match(a, cells, transformed, [(5,(1,0,2))], 1.)
    with pytest.raises(ValueError, match='셀 종류'):
        c.ordered_match(a, cells, transformed, [(3,(0,1,2))], 1.)


def test_retained_fixed_clock_is_physical_time_without_reader_frame_search():
    side = recipe()['a']
    side['frozen_clock'] = {'value': 500., 'unit':'ms', 'semantics':'physical_time'}
    clock = {'value':.5, 'unit':'s', 'semantics':'physical_time'}
    result = c.time_plan(side, [], clock)
    assert result['times'] == [None] and result['common_time'] == .5
    assert result['frozen_clock'] == side['frozen_clock']
    with pytest.raises(ValueError, match='일치'):
        c.time_plan(side, [], dict(clock,value=.6))
    side['clock_offset'] = .1
    assert c.time_plan(side, [], dict(clock,value=.6))['common_time'] == .6
    side['sampling'] = {'mode':'exact','time':500.}
    with pytest.raises(ValueError, match='고정'):
        c.time_plan(side, [500.], clock)


def test_timeless_data_cannot_be_relabelled_with_a_sample_clock():
    r = recipe()
    r['clock'] = {'value':2., 'unit':'s', 'semantics':'physical_time'}
    with pytest.raises(ValueError, match='부여'):
        c.validate(r, [], [])
