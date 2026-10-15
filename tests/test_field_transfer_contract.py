"""Detached physical checks; these are not solver or native Post evidence."""
from copy import deepcopy
import numpy as np
import pytest
from caelab import field_transfer_contract as t


POINTS = np.array([[0., 0., 0.], [1., 0., 0.], [0., 1., 0.], [0., 0., 1.]])
CELLS = [[0, 1, 2, 3]]
REFINED = np.vstack([POINTS, [.25, .25, .25]])
SPLIT = [[0, 1, 2, 4], [0, 1, 4, 3], [0, 4, 2, 3], [4, 1, 2, 3]]


def recipe():
    return {'a': {'coordinate_units': 'm'}, 'target': {'units': 'N/m3'},
            'coverage': {'policy': 'all_a_points', 'array': None},
            'conservation': {'mode': 'check_volume_integral',
                             'absolute_tolerance': 1e-12, 'relative_tolerance': 1e-12}}


def test_constant_and_linear_vector_real_different_internal_mesh_integrals():
    r = recipe()
    for field in (lambda p: np.full((len(p), 3), 2.),
                  lambda p: np.column_stack([1 + 3*p[:, 0], -2*p[:, 1], p[:, 2]])):
        source, received = field(POINTS), field(REFINED)
        before = source.copy()
        result = t.conservation_check(r, POINTS, CELLS, source, REFINED, SPLIT, received)
        assert result['status'] == 'PASS' and result['conservative_transfer'] is False
        np.testing.assert_allclose(result['source_integral'], result['receiver_integral'], atol=1e-14)
        np.testing.assert_array_equal(source, before)
    np.testing.assert_allclose(result['source_integral'], np.array([1.75, -.5, .25])/6)


def test_equal_numbers_and_equal_volume_do_not_establish_same_physical_domain():
    with pytest.raises(ValueError, match='경계'):
        t.conservation_check(recipe(), POINTS, CELLS, np.ones((4, 1)),
                             POINTS + [2, 0, 0], CELLS, np.ones((4, 1)))


def test_original_cell_integral_is_not_the_projected_nodal_integral():
    with pytest.raises(ValueError, match='적분 오차'):
        t.conservation_check(recipe(), REFINED, SPLIT, [[1], [1], [1], [4]],
                             POINTS, CELLS, [[2]]*4, source_association='CELLS')


def test_mask_required_rows_and_optional_invalid_are_distinct():
    r = recipe(); r['coverage'] = {'policy': 'a_mask', 'array': 'required'}
    values = np.array([[1., 2., 3.], [1., np.nan, 3.]])
    result = t.coverage_check(r, values, values, [1, 0], [1, 0])
    assert result['required_count'] == 1 and not result['invalid_required_rows']
    with pytest.raises(ValueError, match='A 행 1'):
        t.coverage_check(r, values, values, [1, 0], [0, 1])
    for mask in ([0, 0], [1, .1], [1], [1, np.nan]):
        with pytest.raises(ValueError): t.coverage_check(r, values, values, [1, 0], mask)


def test_invalid_components_are_not_hidden_by_selected_scalar_component():
    r = recipe()
    with pytest.raises(ValueError, match='필수 비교 영역'):
        t.coverage_check(r, [[1, np.nan, 3]], [[1, 2, 3]], [1])
    legacy = deepcopy(r); legacy.pop('coverage'); legacy.pop('conservation')
    assert t.coverage_check(legacy, [[1]], [[np.nan]], [0])['required_count'] == 0


def test_explicit_tolerances_conservative_capability_and_temperature_guard():
    r = recipe()
    r['conservation']['relative_tolerance'] = -1
    with pytest.raises(ValueError): t.policy(r)
    r['conservation'] = {'mode': 'conservative_transfer'}
    with pytest.raises(ValueError, match='지원하지'): t.policy(r)
    r = recipe(); r['a']['temperature_kind'] = 'absolute'
    with pytest.raises(ValueError, match='열량이 아닙니다'): t.policy(r)
    assert t.capabilities()['receiver_solver_vector_tensor'] == 'UNSUPPORTED'


def test_invalid_tetra_and_missing_values_cannot_produce_conservation_pass():
    for cells in ([[0, 1, 2, 2]], CELLS*2):
        with pytest.raises(ValueError): t.volume_integral(POINTS, cells, [[1]]*4)
    with pytest.raises(ValueError): t.volume_integral(POINTS, CELLS, [[np.nan]]*4)
