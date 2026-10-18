"""Existing robust fitter options must pass the same public Plan admission."""
from copy import deepcopy

import pytest

from caelab.assist.experts import validate_plan_request
from caelab.numerical_document import request_diagnostics, request_draft


def request():
    return {'purpose': '공개 대수 모델의 보존 관측 비교', 'operation': 'fit',
        'inputs': {'backend': 'public.algebra', 'method': 'least_squares',
            'variables': [{'id': 'x', 'unit': 'N', 'value': 1., 'lower': 0., 'upper': 4., 'transform': 'linear'}],
            'experiments': [{'id': 'Tforce', 'response': 'force', 'settings': {},
                'observations': {'kind': 'series', 'unit': 'N', 'component': 'z', 'location': 'specimen',
                    'reduction': 'none', 'value': [0., 1.], 'axes': [{'name': 'time', 'unit': 's', 'values': [0., 1.]}]}}],
            'options': {'loss': 'soft_l1', 'f_scale': 2., 'max_nfev': 50}},
        'budget': {'evaluations': 200}}


def test_existing_robust_options_preserve_authored_request_through_plan_check():
    authored = request(); before = deepcopy(authored)
    assert validate_plan_request(authored)['plan'] == before
    assert not request_diagnostics(request_draft(authored))
    assert authored == before


@pytest.mark.parametrize('change', [{'loss': 'unknown'}, {'f_scale': 0}, {'future_option': 1}])
def test_robust_admission_still_rejects_invalid_or_unknown_options(change):
    authored = request(); authored['inputs']['options'].update(change)
    with pytest.raises(ValueError, match='Invalid fit plan input'):
        validate_plan_request(authored)
