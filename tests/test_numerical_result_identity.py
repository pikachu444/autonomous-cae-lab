"""Existing engine identity checks with tiny synthetic numeric inputs only.

These do not repeat a successful fit/DOE or execute a native solver/provider.
"""
from copy import deepcopy

import pytest

from caelab import numerical
from caelab.assist.experts import validate_plan_request


VARIABLES = [{'id': 'x', 'unit': '1', 'value': .5, 'lower': 0, 'upper': 1}]


def objectives(explicit=False):
    rows = [{'response': 'stress', 'unit': '1', 'reduction': 'max', 'direction': 'minimize'},
            {'response': 'stress', 'unit': '1', 'reduction': 'final', 'direction': 'minimize'}]
    if explicit:
        rows[0]['id'], rows[1]['id'] = 'stress_peak', 'stress_final'
    return rows


class TinyHistory:
    """Clearly synthetic opposing reductions; not physics validation."""
    def __init__(self):
        self.calls = []
    def __call__(self, values, settings):
        self.calls.append(deepcopy(values))
        x = values['x']
        return {'execution_status': 'SUCCEEDED', 'responses': {'stress': {
            'kind': 'series', 'unit': '1', 'value': [x + 3, 1 - x],
            'axes': [{'name': 'time', 'unit': 's', 'values': [0, 1]}]}}}


def epsilon(evaluator, definitions, retention='summary'):
    return numerical.epsilon_optimize(evaluator, VARIABLES, definitions, threshold_grid=[[1]],
        options={'population_size': 5, 'max_generations': 1, 'retain_responses': retention},
        total_evaluation_budget=10, seed=7)


def imported_table(tmp_path):
    variables = [{'id': 'x', 'unit': '1', 'value': 0, 'lower': 0, 'upper': 10}]
    candidates = [{'candidate_id': 'C' + str(i), 'values': {'x': i}} for i in range(10)]
    manifest = numerical.export_batch(variables, candidates, tmp_path / 'exchange', case_id='Kactual')
    results = []
    for i, candidate in enumerate(candidates[:9]):
        row = {**candidate, 'case_id': manifest['case_id'], 'exchange_id': manifest['exchange_id'],
               'execution_status': 'SUCCEEDED', 'responses': {'response': {'kind': 'scalar', 'value': 2 * i + 1, 'unit': '1'}}}
        if i == 8:
            row.update(prediction_status='PREDICTED', out_of_range=True,
                       source={'kind': 'synthetic_surrogate', 'training_id': 'Jtraining'},
                       prediction_source={'document_id': 'Nsurrogate', 'job_id': 'Jprediction'})
            row['responses']['response']['value'] = 99999
        results.append(row)
    return numerical.import_batch(manifest, results), results


def test_batch_success_retains_prediction_identity_and_excludes_it_from_actual_analysis(tmp_path):
    table, original = imported_table(tmp_path)
    predicted = next(row for row in table['candidates'] if row['candidate_id'] == 'C8')
    assert predicted['execution_status'] == 'SUCCEEDED' and predicted['prediction_status'] == 'PREDICTED'
    for key in ('out_of_range', 'source', 'prediction_source'):
        assert predicted[key] == original[-1][key]
    result = numerical.analyze_candidates(table, [{'response': 'response', 'unit': '1'}])
    assert result['statistics'][0]['count'] == 8 and result['statistics'][0]['max'] == 15
    assert result['sensitivity'][0]['sample_ids'] == ['C' + str(i) for i in range(8)]
    assert set(result['surrogate'][0]['train_ids'] + result['surrogate'][0]['test_ids']) == {'C' + str(i) for i in range(8)}
    assert {'id': 'C8', 'reason': 'PREDICTED'} in result['exclusions']
    assert {'id': 'C9', 'reason': 'ROW_UNUSABLE'} in result['exclusions']
    assert result['decision'] == 'NOT_RELEASED'
    with pytest.raises(numerical.EvaluationFailed, match='PREDICTED'):
        numerical._scalar(predicted, {'response': 'response', 'unit': '1'})
    assert table['candidates'][-1]['execution_status'] == 'NOT_EVALUATED'


@pytest.mark.parametrize('predicted_role', ['training', 'holdout'])
def test_imported_prediction_cannot_train_or_confirm_real_surrogate(tmp_path, predicted_role):
    table, _ = imported_table(tmp_path)
    actual, predicted = table['candidates'][:3], table['candidates'][8]
    training = dict(table, candidates=actual + ([predicted] if predicted_role == 'training' else []))
    holdout = dict(table, candidates=[predicted] if predicted_role == 'holdout' else [table['candidates'][5]])
    with pytest.raises(numerical.EvaluationFailed, match='PREDICTED'):
        numerical.fit_surrogate(training, holdout, {'response': 'response', 'unit': '1'})


@pytest.mark.parametrize('explicit,retention', [(False, 'summary'), (True, 'all')])
def test_actual_epsilon_same_response_max_final_have_distinct_metric_identity(explicit, retention):
    evaluator = TinyHistory()
    declarations = objectives(explicit)
    original = deepcopy(declarations)
    result = epsilon(evaluator, declarations, retention)
    assert result['execution_status'] == 'SUCCEEDED'
    assert 2 <= len(evaluator.calls) <= 10
    ids = ['stress_peak', 'stress_final'] if explicit else ['stress@max', 'stress@final']
    assert [row['metric'] for row in result['pareto']['response_definitions']] == ids
    assert result['pareto']['valid'] and result['pareto']['nondominated_ids']
    assert declarations == original  # engine identities do not mutate the caller's declaration
    for row in result['candidates']:
        if row['execution_status'] != 'SUCCEEDED':
            continue
        peak = numerical._scalar(row, declarations[0])
        final = numerical._scalar(row, declarations[1])
        assert peak == pytest.approx(row['values']['x'] + 3)
        assert final == pytest.approx(1 - row['values']['x'])
        assert peak != final
    analysis = numerical.analyze_candidates(result, declarations)
    assert [row['metric'] for row in analysis['statistics']] == ids
    assert analysis['statistics'][0]['min'] > analysis['statistics'][1]['max']


@pytest.mark.parametrize('identity', [None, '', '   ', 3, False, [], {}, 'x' * 201])
def test_invalid_supplied_metric_id_is_rejected_before_any_evaluation(identity):
    evaluator = TinyHistory()
    declarations = objectives(True)
    declarations[0]['id'] = identity
    with pytest.raises(ValueError, match='metric IDs'):
        epsilon(evaluator, declarations)
    assert evaluator.calls == []


@pytest.mark.parametrize('duplicate', ['explicit_id', 'same_definition'])
def test_genuine_duplicate_metric_identity_is_rejected_before_evaluation(duplicate):
    evaluator = TinyHistory()
    declarations = objectives(duplicate == 'explicit_id')
    if duplicate == 'explicit_id':
        declarations[1]['id'] = declarations[0]['id']
    else:
        declarations[1] = deepcopy(declarations[0])
    with pytest.raises(ValueError, match='metric IDs'):
        epsilon(evaluator, declarations)
    assert evaluator.calls == []


def test_expert_optional_metric_id_schema_preserves_distinct_objective_ids_without_execution():
    request = {'purpose': 'Separate peak and final response reductions', 'operation': 'epsilon',
               'inputs': {'backend': 'synthetic.no_native', 'variables': VARIABLES, 'objectives': objectives(True),
                          'threshold_grid': [[1]], 'options': {'population_size': 5, 'max_generations': 1}},
               'budget': {'evaluations': 10}}
    receipt = validate_plan_request(request)
    assert receipt['executed'] is False and receipt['plan']['inputs']['objectives'] == objectives(True)
    invalid = deepcopy(request)
    invalid['inputs']['objectives'][0]['id'] = None
    with pytest.raises(ValueError, match='id'):
        validate_plan_request(invalid)
