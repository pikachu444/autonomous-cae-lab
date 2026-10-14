from copy import deepcopy
import json
import pytest
from caelab.calculix_material import (J2, LINEAR, default_plasticity, plasticity_errors,
    normalize_plasticity, native_plasticity, native_yield_points, material_errors, plastic_cards)


def curve():
    result = default_plasticity()
    result['yield_points'] = [['250', '0'], ['270', '0.001'], ['310', '1.2e-2']]
    return result


def material():
    return {'law': J2, 'young_modulus_MPa': 210000, 'poisson_ratio': .3,
            'plasticity': normalize_plasticity(curve())}


def test_unit_only_conversion_is_explicit_and_does_not_modify_source():
    source = curve()
    source.update(stress_unit='GPa', strain_unit='%')
    source['yield_points'] = [['.25', '0'], ['.27', '.1'], ['.31', '1.2']]
    original = deepcopy(source)
    converted = normalize_plasticity(source)
    assert converted['yield_points'] == [[250, 0], [270, .001], [310, .012]]
    assert source == original
    assert converted['stress_unit'] == 'MPa' and converted['strain_unit'] == '1'


@pytest.mark.parametrize('field,value', [('stress_measure', 'engineering'), ('stress_measure', None),
    ('strain_measure', 'total_strain'), ('strain_measure', 'logarithmic'), ('hardening', 'kinematic'),
    ('stress_unit', 'unknown'), ('strain_unit', '')])
def test_unconfirmed_measures_and_unsupported_units_block_conversion(field, value):
    source = curve(); source[field] = value
    assert any(e['path'].endswith(field) for e in plasticity_errors(source))
    with pytest.raises(ValueError): normalize_plasticity(source)


@pytest.mark.parametrize('rows,ending', [
    ([['250', '0'], ['-1', '.01']], '.1.0'),
    ([['0', '0']], '.0.0'),
    ([['250', '.001']], '.0.1'),
    ([['250', '0'], ['270', '0']], '.1.1'),
    ([['250', '0'], ['270', '.02'], ['290', '.01']], '.2.1'),
    ([['250', '0'], ['249', '.01']], '.1.0'),
    ([['250', '0'], ['270', '1e']], '.1.1'),
    ([['nan', '0']], '.0.0'),
    ([['inf', '0']], '.0.0'),
    ([['250', '0', '293']], '.0'),
])
def test_invalid_curve_has_exact_edit_location_and_is_saveable(rows, ending):
    source = curve(); source['yield_points'] = rows
    saved = json.dumps(source, allow_nan=False)
    assert any(e['path'].endswith(ending) for e in plasticity_errors(source))
    with pytest.raises(ValueError): normalize_plasticity(source)
    assert json.loads(saved) == source


def test_explicit_perfect_plastic_limit_and_zero_origin_are_valid():
    source = curve(); source['yield_points'] = [[250, 0], [250, .1]]
    assert not plasticity_errors(source)
    source['yield_points'] = [[250, 0]]
    assert not plasticity_errors(source)


def test_native_roundtrip_preserves_small_numbers_and_is_not_an_elastic_substitute():
    source = curve(); source['yield_points'] = [['2.5e2', '0'], ['270', '1.2e-5'], ['300', '0.001']]
    native = native_yield_points(source)
    result = native_plasticity(native)
    assert result['yield_points'] == [[250, 0], [270, 1.2e-5], [300, .001]]
    value = material(); value['plasticity'] = result
    assert plastic_cards(value) == ['*PLASTIC,HARDENING=ISOTROPIC', *native]
    assert value['young_modulus_MPa'] == 210000


def test_native_unit_tokens_and_temperature_columns_are_not_guessed():
    for rows in [['250 MPa,0'], ['250,0,293'], ['250,0', '270,1e']]:
        with pytest.raises(ValueError): native_plasticity(rows)


def test_linear_backward_compatibility_and_no_silent_plastic_table_drop():
    value = {'law': LINEAR, 'young_modulus_MPa': 1000, 'poisson_ratio': .25}
    assert material_errors(value) == [] and plastic_cards(value) == []
    value['plasticity'] = curve()
    assert material_errors(value)
