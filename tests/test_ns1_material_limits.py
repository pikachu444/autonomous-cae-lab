"""Regressions for the actual ccx plastics.f field width and plcopy.f cap."""
from copy import deepcopy
import json
import math

import pytest

from caelab.calculix_material import (
    J2, MAX_YIELD_POINTS, NATIVE_PRECISION, default_plasticity,
    material_errors, native_plasticity, native_yield_points,
    normalize_plasticity, plastic_cards, plasticity_errors, result_meanings,
)
from caelab.adapters.native_structural_deck import native_number


def definition(count=2):
    value = default_plasticity()
    value['yield_points'] = [[str(250 + i), str(i * .0001)] for i in range(count)]
    return value


def material(value):
    return dict(law=J2, young_modulus_MPa=210000., poisson_ratio=.3, plasticity=value)


@pytest.mark.parametrize('strain', [1.234567891234567e-5, 1.234567891234567e-100,
                                    1.234567891234567e-300, .1234567891234567])
def test_first_twenty_characters_read_the_intended_value(strain):
    source = definition()
    source['yield_points'][1] = ['270.12345678912345', repr(strain)]
    original = deepcopy(source)
    rows = native_yield_points(source)
    for row, expected in zip(rows, normalize_plasticity(source)['yield_points']):
        for token, value in zip(row.split(','), expected):
            token = token.strip()
            assert token == native_number(value)
            assert len(token) <= 20
            # Mirrors plastics.f textpart(i)(1:20); float accepts the same e form.
            actual_native_value = float(token[:20])
            assert actual_native_value == pytest.approx(value, rel=5e-13, abs=0)
    assert source == original
    assert '13 significant digits' in NATIVE_PRECISION


def test_old_seventeen_digit_token_reproduces_exponent_truncation():
    value = 1.234567891234567e-5
    unsafe = format(value, '.17g')
    assert len(unsafe) == 21
    assert float(unsafe[:20]) / value == pytest.approx(100000.)


def test_two_hundred_points_are_written_without_interpolation():
    source = definition(200)
    original = deepcopy(source)
    assert MAX_YIELD_POINTS == 200
    rows = native_yield_points(source)
    assert len(rows) == 200
    assert len(plastic_cards(material(normalize_plasticity(source)))) == 201
    assert source == original
    for actual, expected in zip(native_plasticity(rows)['yield_points'],
                                normalize_plasticity(source)['yield_points']):
        assert actual == pytest.approx(expected, rel=5e-13, abs=0)


def test_two_hundred_one_point_draft_survives_but_every_material_export_gate_blocks():
    source = definition(201)
    restored = json.loads(json.dumps(source, allow_nan=False))
    errors = plasticity_errors(restored)
    assert any(e['path'] == 'plasticity.yield_points.200' for e in errors)
    assert all(e['blocks_evaluation'] for e in errors)
    assert material_errors(material(restored))
    for action in (normalize_plasticity, native_yield_points):
        with pytest.raises(ValueError, match='200'): action(restored)
    with pytest.raises(ValueError, match='200'): plastic_cards(material(restored))
    with pytest.raises(ValueError, match='200'):
        native_plasticity([','.join(row) for row in restored['yield_points']])
    assert restored == source and len(restored['yield_points']) == 201


def test_rounding_must_not_collapse_distinct_abscissae():
    source = definition(3)
    source['yield_points'] = [[250, 0], [260, .01], [270, math.nextafter(.01, 1.)]]
    assert not plasticity_errors(source)
    with pytest.raises(ValueError, match=r'yield_points\.2\.1'):
        native_yield_points(source)


@pytest.mark.parametrize('nlgeom,expected', [(True, 'green_lagrange'),
                                            (False, 'infinitesimal'), (None, None)])
def test_total_strain_has_step_context_but_pe_is_always_scalar(nlgeom, expected):
    meanings = result_meanings(nlgeom)
    assert meanings['TOSTRAIN']['measure'] == expected
    assert meanings['TOSTRAIN']['requires_step_context'] is (nlgeom is None)
    assert meanings['PE']['quantity'] == 'equivalent_plastic_strain'
    assert meanings['PE']['native_request'] == 'PEEQ'
    assert meanings['FORC']['quantity'] == 'nodal_force'
    meanings['PE']['unit'] = 'changed by caller'
    assert result_meanings(nlgeom)['PE']['unit'] == '1'


@pytest.mark.parametrize('value', ['false', 0, 1])
def test_step_context_does_not_coerce_unknown_strings_or_numbers(value):
    with pytest.raises(ValueError): result_meanings(value)
