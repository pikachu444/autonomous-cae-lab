"""Preserve existing continuous sample/rank semantics; mixed rejection is separate."""
from copy import deepcopy
import math
import pytest
from caelab import numerical as n
from caelab.contracts import CapabilityUnavailable
from caelab.optimizers import campaign_analysis as ca
from caelab.storage import canonical_hash
from caelab.workbench import Workbench
from examples.numerical_mixed_domains import command

VARS = [{'id': 'x', 'unit': '1', 'lower': 0., 'upper': 1.},
        {'id': 'y', 'unit': '1', 'lower': 0., 'upper': 1.}]
RESP = [{'response': 'a', 'unit': 'K', 'direction': 'minimize'},
        {'response': 'b', 'unit': 'K', 'direction': 'maximize'}]

def model(values, settings):
    x,y = values['x'],values['y']
    def scalar(value):
        return {'kind': 'scalar', 'unit': 'K', 'value': value}
    return {'execution_status': 'SUCCEEDED', 'responses': {'a': scalar(2*x+3*y), 'b': scalar(4*x-y)},
            'diagnostics': {'actual_input': deepcopy(values)}}


def cohort(collinear=False):
    points = ([{'x': i/11, 'y': i/11} for i in range(12)] if collinear else
              [{'x': i/3, 'y': j/2} for i in range(4) for j in range(3)])
    table = n.run_doe(model, VARS, candidates=points)
    table['candidates'][-1].update(execution_status='FAILED', failure_reason='Retained physical failure', responses={})
    table['candidates'][-2]['responses'].pop('b')  # joint response cohort excludes this row
    return table


def as_campaign(table):
    samples = []
    for row in table['candidates']:
        samples.append({'id': row['candidate_id'], 'values': row['values'], 'usable': row['execution_status']=='SUCCEEDED',
            'responses': {r['response']: {'value': row['responses'].get(r['response'],{}).get('value'),
                'unit': 'K', 'valid': r['response'] in row['responses']} for r in RESP}})
    variables = [{'parameter_id': v['id'], 'lower_bound': v['lower'], 'upper_bound': v['upper'], 'unit': v['unit']} for v in VARS]
    responses = [{'metric': r['response'], 'unit': r['unit'], 'direction': r['direction']} for r in RESP]
    return samples, variables, responses


@pytest.mark.parametrize('collinear', [False, True])
def test_continuous_multiresponse_cohort_and_campaign_rank_are_retained(collinear):
    table = cohort(collinear)
    before = canonical_hash(table)
    result = n.analyze_candidates(table, RESP, seed=13)
    samples, variables, responses = as_campaign(table)
    # Public existing campaign consumer, not a new regression implementation.
    campaign = ca.summarize(samples, variables, responses, seed=13)
    for key in ('statistics', 'sensitivity', 'surrogate', 'pareto'):
        assert result[key] == campaign[key]
    eligible, excluded = ca._validate(samples, variables, responses, 13)
    import numpy as np
    x = np.asarray([[r['values'][v['parameter_id']] for v in variables] for r in eligible])
    ids = [r['id'] for r in eligible]
    for index, response in enumerate(responses):
        y = np.asarray([r['responses'][response['metric']]['value'] for r in eligible])
        original = ca._sensitivity(x, y, variables, response, ids)
        assert result['sensitivity'][index] == original
    assert [s['count'] for s in result['statistics']] == [10,10]
    assert result['candidate_count'] == 12 and result['failure_count'] == 1
    assert {r['id'] for r in result['exclusions']} == {table['candidates'][-1]['candidate_id'],table['candidates'][-2]['candidate_id']}
    for regression in result['sensitivity']:
        assert regression['sample_ids'] == ids and len(ids) == 10
        if collinear:
            assert not regression['valid'] and regression['reason'] == 'RANK_DEFICIENT'
            assert regression['rank'] == 2 and regression['condition_number'] is None
        else:
            assert regression['valid'] and regression['rank'] == 3
            assert math.isfinite(regression['condition_number']) and regression['condition_number'] < 1e12
    for row in table['candidates']:
        assert row['values'] == row['diagnostics']['actual_input']
    assert canonical_hash(table) == before


def test_old_campaign_cannot_interpret_integer_as_continuous_regression():
    samples, variables, responses = as_campaign(cohort())
    variables[0]['kind'] = 'integer'
    with pytest.raises(CapabilityUnavailable, match='continuous'):
        ca._validate(samples, variables, responses, 13)


def test_unsupported_method_draft_saves_and_reopens_without_job(tmp_path):
    request = {'purpose': '혼합 변수는 Sobol로 해석하지 않음', 'operation': 'sample_sensitivity',
        'inputs': {'variables': [{'id': 'count', 'kind': 'integer','unit': '1', 'lower':1,'upper':3}], 'count': 8},
        'budget': {'evaluations':8}}
    wb = Workbench(tmp_path)
    try:
        doc = wb.document_open(kind='numerical', draft={'mode':'request','request':request,'source':None})
        assert doc['diagnostics'] and 'continuous' in str(doc['diagnostics'])
        doc = command(wb, doc, 'document.save')['document']
        assert not wb.manager.list()
        with pytest.raises((ValueError, CapabilityUnavailable)):
            command(wb, doc, 'numerical.run')
        assert not wb.manager.list()
    finally:
        assert wb.shutdown()['joined']
    wb = Workbench(tmp_path)
    try:
        reopened = wb.document_open(kind='numerical', document_id=doc['id'])
        assert reopened['draft'] == doc['draft'] and reopened['diagnostics']
        assert not wb.manager.list()
    finally:
        assert wb.shutdown()['joined']
