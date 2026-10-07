"""Real numerical studies: independent histories, failure accounting and exchange."""
import os
import numpy as np
import pytest

from caelab.evaluation import PreparedEvaluation, prepare, read_result
from caelab.numerical import (fit_model, run_doe, optimize, run_uq, analyze_candidates,
                             fit_surrogate, export_batch, import_batch, load_observations,
                             sample_sensitivity, analyze_sensitivity, epsilon_optimize,
                             compare_curves, detect_event, compare_events)
from caelab.execution_control import ExecutionCleanupFailed


def scalar(value, unit='MPa'):
    return {'kind': 'scalar', 'value': value, 'unit': unit,
            'component': 'scalar', 'location': 'model', 'reduction': 'none'}


def quadratic(values, settings):
    x = values['x']
    if settings.get('fail_above') is not None and x > settings['fail_above']:
        return {'execution_status': 'FAILED', 'responses': {}, 'diagnostics': {'failure_reason': 'Outside solver domain'}}
    return {'execution_status': 'SUCCEEDED', 'responses': {'cost': scalar((x - .25) ** 2),
                                                          'position': scalar(x),
                                                          'opposite': scalar((x - .75) ** 2)},
            'diagnostics': {'pid': os.getpid()}}


class BatchFactory:
    def prepare(self, settings, *, runtime=None):
        return PreparedEvaluation(lambda v: quadratic(v, settings), settings,
                                  batch=lambda rows: [quadratic(v, settings) for v in rows])


class WorkerFactory:
    def prepare(self, settings, *, runtime=None):
        counter = 0
        def evaluate(values):
            nonlocal counter
            counter += 1
            result = quadratic(values, settings)
            result['diagnostics']['worker_call_number'] = counter
            return result
        return PreparedEvaluation(evaluate, settings)


class CurveBatchFactory:
    def prepare(self, settings, *, runtime=None):
        return PreparedEvaluation(lambda v: linear_curve(v, settings), settings,
                                  batch=lambda rows: [linear_curve(v, settings) for v in rows])


VARIABLES = [{'id': 'x', 'unit': '1', 'value': .5, 'lower': 0., 'upper': 1.}]
OBJECTIVE = {'response': 'cost', 'unit': 'MPa', 'direction': 'minimize'}


def linear_curve(values, settings):
    t = np.asarray(settings['time'])
    response = {'kind': 'series', 'value': values['a'] * t + values['b'], 'unit': 'MPa',
                'component': 'xx', 'location': 'material_point', 'reduction': 'none',
                'axes': [{'name': 'time', 'unit': 's', 'values': t}]}
    return {'execution_status': 'SUCCEEDED', 'responses': {'stress': response}}


def event_curve(values, settings):
    result = linear_curve(values, settings)
    result['responses']['crossing'] = detect_event(result['responses']['stress'], 3.)
    return result


def curve_experiment(identifier, time, values, role='fit', **kw):
    return {'id': identifier, 'role': role, 'settings': {'time': time}, 'response': 'stress',
            'observations': {'kind': 'series', 'value': values, 'unit': 'MPa', 'component': 'xx',
                             'location': 'material_point', 'reduction': 'none',
                             'axes': [{'name': 'time', 'unit': 's', 'values': time}]}, **kw}


def test_multiple_histories_fit_mask_weight_and_holdout(tmp_path):
    variables = [{'id': 'a', 'unit': 'MPa/s', 'lower': .1, 'upper': 8., 'value': 1., 'transform': 'log'},
                 {'id': 'b', 'unit': 'MPa', 'lower': -4., 'upper': 4., 'value': 0.}]
    fit = curve_experiment('loading', [0., 1., 2., 3.], [1., 3., float('nan'), 7.], weight=4., scale=2.)
    unloading = curve_experiment('unloading', [0., .5, 1.5], [1., 2., 4.], scale=1.)
    holdout = curve_experiment('independent-history', [0., .7, 2.1], [100., 100., 100.], role='holdout')
    result = fit_model(linear_curve, variables, [fit, unloading, holdout],
                       record={'path': tmp_path / 'fit', 'level': 'summary'})
    assert result['execution_status'] == 'SUCCEEDED'
    assert result['parameters'] == pytest.approx({'a': 2., 'b': 1.}, abs=1e-7)
    assert result['identification']['jacobian_rank'] == 2
    curves = {row['experiment_id']: row for row in result['curves']}
    assert curves['loading']['mask'] == [True, True, False, True]
    assert curves['loading']['prediction'][2] is None
    assert curves['loading']['observations']['value'][2] is None
    assert len(curves['loading']['residual']) == 3
    assert curves['independent-history']['rmse'] > 90
    saved = read_result(tmp_path / 'fit')
    assert saved['parameters'] == result['parameters']
    assert saved['curves'][0]['residual'] == pytest.approx(result['curves'][0]['residual'])


def test_weighted_fixed_residual_formula_and_axis_alignment():
    experiment = curve_experiment('curve', [0., 1., 2.], [0., 0., 0.], weight=12., scale=2.)
    experiment['settings']['time'] = [0., .5, 1., 1.5, 2.]
    variables = [{'id': 'a', 'unit': 'MPa/s', 'lower': 0., 'upper': 3., 'value': 2.},
                 {'id': 'b', 'unit': 'MPa', 'lower': 0., 'upper': 3., 'value': 1.}]
    result = fit_model(linear_curve, variables, [experiment], options={'max_nfev': 1})
    # sqrt(12/3)/2 == 1, so the weighted residual is the physical difference.
    assert result['curves'][0]['residual'] == pytest.approx([1., 3., 5.])
    assert result['curves'][0]['prediction'] == pytest.approx([1., 3., 5.])


@pytest.mark.parametrize('problem', ['unit', 'component', 'location', 'axis_unit', 'support'])
def test_fit_rejects_unjustified_mapping_or_extrapolation(problem):
    experiment = curve_experiment('curve', [0., 1., 2.], [1., 3., 5.])
    if problem in ('unit', 'component', 'location'):
        experiment['observations'][problem] = 'different'
    elif problem == 'axis_unit':
        experiment['observations']['axes'][0]['unit'] = 'ms'
    else:
        experiment['settings']['time'] = [.5, 1., 1.5]
    variables = [{'id': 'a', 'unit': 'MPa/s', 'lower': 0., 'upper': 3., 'value': 2.},
                 {'id': 'b', 'unit': 'MPa', 'lower': 0., 'upper': 3., 'value': 1.}]
    with pytest.raises(ValueError):
        fit_model(linear_curve, variables, [experiment])


def test_least_squares_failure_is_preserved_and_stops():
    def failed(values, settings):
        return {'execution_status': 'FAILED', 'responses': {}, 'diagnostics': {'failure_reason': 'Integrator did not converge'}}
    result = fit_model(failed, [{'id': 'a', 'unit': '1', 'lower': 0, 'upper': 1}],
                       [curve_experiment('curve', [0., 1.], [0., 1.])])
    assert result['execution_status'] == 'FAILED'
    assert result['termination_reason'] == 'EVALUATION_FAILED'
    assert result['parameters'] is None
    assert len(result['candidates']) == 1
    assert 'Integrator did not converge' in result['failure_reason']


def test_actual_felupe_two_coefficients_and_three_histories():
    pytest.importorskip('felupe')
    def history(time, deformation):
        F = np.tile(np.eye(3), (len(time), 1, 1))
        if deformation == 'axial':
            F[:, 0, 0] += np.linspace(0, .004, len(time))
        else:
            F[:, 0, 1] += np.linspace(0, .006, len(time))
        return {'model': 'linear_elastic', 'time': time, 'deformation_gradient': F,
                'parameters': {'E': 1500., 'nu': .29}, 'stress_unit': 'MPa'}
    experiments = []
    for identifier, time, deformation, response, role in [
            ('axial', [0., 1., 2., 3., 4.], 'axial', 'stress_yy', 'fit'),
            ('shear', [0., .5, 1., 1.5], 'shear', 'stress_xy', 'fit'),
            ('held-out-axial', [0., .7, 1.4, 2.1], 'axial', 'stress_xx', 'holdout')]:
        settings = history(time, deformation)
        with prepare('material.felupe', settings) as model:
            observations = model.evaluate({})['responses'][response]
        settings['parameters'] = {'E': 900., 'nu': .2}
        experiments.append({'id': identifier, 'role': role, 'settings': settings,
                            'response': response, 'observations': observations})
    variables = [{'id': 'E', 'unit': 'MPa', 'value': 900, 'lower': 200, 'upper': 2500, 'transform': 'log'},
                 {'id': 'nu', 'unit': '1', 'value': .2, 'lower': .05, 'upper': .45}]
    result = fit_model('material.felupe', variables, experiments)
    assert result['parameters'] == pytest.approx({'E': 1500., 'nu': .29}, rel=1e-7)
    assert all(curve['rmse'] < 1e-6 for curve in result['curves'])
    assert result['timing']['model_calls'] >= 3


def test_doe_serial_batch_and_real_worker_preparation_match():
    candidates = [{'x': x} for x in np.linspace(0, 1, 9).tolist()]
    serial = run_doe(quadratic, VARIABLES, candidates=candidates)
    batch = run_doe(BatchFactory(), VARIABLES, candidates=candidates, execution={'mode': 'batch'})
    process = run_doe(WorkerFactory(), VARIABLES, candidates=candidates, execution={'mode': 'process', 'workers': 2})
    for table in (batch, process):
        assert [r['responses']['cost']['value'] for r in table['candidates']] == [r['responses']['cost']['value'] for r in serial['candidates']]
        assert [r['candidate_id'] for r in table['candidates']] == [r['candidate_id'] for r in serial['candidates']]
    assert all(r['diagnostics']['pid'] != os.getpid() for r in process['candidates'])
    assert max(r['diagnostics']['worker_call_number'] for r in process['candidates']) > 1


def test_unsupported_execution_never_silently_falls_back():
    with pytest.raises(ValueError, match='Batch'):
        run_doe(quadratic, VARIABLES, count=2, execution={'mode': 'batch'})
    with pytest.raises(ValueError, match='serializable'):
        run_doe(lambda v, s: quadratic(v, s), VARIABLES, count=2, execution={'mode': 'process', 'workers': 2})
    with pytest.raises(ValueError, match='Multiple workers'):
        run_doe(quadratic, VARIABLES, count=2, execution={'mode': 'serial', 'workers': 2})


def test_partial_failures_cancellation_and_saved_completed_rows(tmp_path):
    result = run_doe(quadratic, VARIABLES, settings={'fail_above': .5}, candidates=[{'x': .2}, {'x': .8}, {'x': .4}],
                     record={'path': tmp_path / 'failed-study', 'level': 'summary'})
    assert [r['execution_status'] for r in result['candidates']] == ['SUCCEEDED', 'FAILED', 'SUCCEEDED']
    assert result['candidates'][1]['failure_reason'] == 'Outside solver domain'
    calls = 0
    def cancelled():
        nonlocal calls
        calls += 1
        return calls >= 4
    partial = run_doe(quadratic, VARIABLES, candidates=[{'x': .1}, {'x': .2}, {'x': .3}], execution={'cancelled': cancelled})
    assert partial['execution_status'] == 'CANCELLED'
    assert partial['candidates'][0]['execution_status'] == 'SUCCEEDED'
    assert partial['candidates'][-1]['execution_status'] == 'CANCELLED'
    assert read_result(tmp_path / 'failed-study')['candidates'][1]['execution_status'] == 'FAILED'


def test_shared_manager_cancellation_token_retains_actual_completed_candidate():
    from caelab.execution_control import CancellationToken, cancellation_scope
    token = CancellationToken()
    def evaluated(values, settings):
        token.request()
        return quadratic(values, settings)
    with cancellation_scope(token):
        table = run_doe(evaluated, VARIABLES, candidates=[{'x': .1}, {'x': .2}, {'x': .3}])
    assert token.observed
    assert table['execution_status'] == 'CANCELLED'
    assert [r['execution_status'] for r in table['candidates']] == ['SUCCEEDED', 'CANCELLED', 'CANCELLED']


def test_existing_de_plain_variables_constraints_and_response_reuse():
    calls = []
    def evaluated(values, settings):
        calls.append(values['x'].hex())
        return quadratic(values, settings)
    result = optimize(evaluated, VARIABLES, OBJECTIVE,
                      constraints=[{'response': 'position', 'unit': 'MPa', 'operator': '>=', 'limit': .4}],
                      options={'max_generations': 20, 'population_size': 8}, seed=3)
    assert result['best']['values']['x'] == pytest.approx(.4, abs=.005)
    assert result['best']['feasible']
    assert len(calls) == len(set(calls)) == len(result['candidates'])
    assert result['algorithm']['engine'] == 'scipy.differential_evolution'
    assert 'geometry_effect' not in result['variables'][0]


def test_series_reductions_are_explicit_and_shared_with_analysis():
    def history(values, settings):
        return {'execution_status': 'SUCCEEDED', 'responses': {'stress': {
            'kind': 'series', 'value': [values['x'], 2 * values['x']], 'unit': 'MPa',
            'component': 'xx', 'location': 'material_point', 'reduction': 'none',
            'axes': [{'name': 'time', 'unit': 's', 'values': [0., 1.]}]}}}
    table = run_doe(history, VARIABLES, candidates=[{'x': .1}, {'x': .2}, {'x': .3}, {'x': .4}])
    declaration = {'response': 'stress', 'unit': 'MPa', 'reduction': 'max', 'component': 'xx'}
    summary = analyze_candidates(table, [declaration])
    assert summary['statistics'][0]['mean'] == pytest.approx(.5)
    assert summary['response_definitions'][0]['reduction'] == 'max'
    with pytest.raises(ValueError, match='declared reduction'):
        analyze_candidates(table, ['stress'])
    with pytest.raises(ValueError, match='explicit'):
        optimize(history, VARIABLES, {'response': 'stress', 'unit': 'MPa'}, options={'max_generations': 1, 'population_size': 5})
    optimum = optimize(history, VARIABLES, dict(declaration, direction='minimize'),
                       options={'max_generations': 5, 'population_size': 5})
    assert optimum['best']['objective'] == pytest.approx(2 * optimum['best']['values']['x'])


@pytest.mark.parametrize('mode', ['serial', 'batch', 'process'])
def test_evaluation_budget_caps_candidate_dispatch_and_retains_unknown_rows(mode):
    evaluator = BatchFactory() if mode == 'batch' else quadratic
    result = run_doe(evaluator, VARIABLES, candidates=[{'x': .1}, {'x': .2}, {'x': .3}, {'x': .4}],
                     execution={'mode': mode, 'workers': 2 if mode == 'process' else 1, 'max_evaluations': 2})
    assert result['timing']['model_calls'] == result['timing']['dispatched_evaluations_total'] == 2
    assert result['termination_reason'] == 'EVALUATION_BUDGET_EXHAUSTED'
    assert [r['execution_status'] for r in result['candidates']] == ['SUCCEEDED', 'SUCCEEDED', 'REJECTED', 'REJECTED']
    assert all(not row['responses'] for row in result['candidates'][2:])


def test_fit_budget_counts_derivatives_and_holdout_in_one_shared_total():
    variables = [{'id': 'a', 'unit': 'MPa/s', 'lower': .1, 'upper': 3., 'value': 2.},
                 {'id': 'b', 'unit': 'MPa', 'lower': -1., 'upper': 3., 'value': 1.}]
    curve = curve_experiment('fit', [0., 1., 2.], [1., 3., 5.])
    holdout = curve_experiment('holdout', [0., .5, 1.], [1., 2., 3.], role='holdout')
    result = fit_model(linear_curve, variables, [curve, holdout], options={'max_nfev': 1}, execution={'max_evaluations': 3})
    assert result['parameters'] == pytest.approx({'a': 2., 'b': 1.})
    assert result['timing']['dispatched_evaluations_total'] == result['timing']['model_calls'] == 3
    assert result['termination_reason'] == 'EVALUATION_BUDGET_EXHAUSTED'
    assert result['curves'][-1]['execution_status'] == 'REJECTED'
    limited = fit_model(linear_curve, variables, [curve], execution={'mode': 'process', 'workers': 2, 'max_evaluations': 1})
    assert limited['timing']['dispatched_evaluations_total'] == 1
    assert any(row['execution_status'] == 'REJECTED' for row in limited['candidates'])


def test_cleanup_failure_cannot_be_sealed_as_a_failed_candidate(tmp_path):
    def cleanup_failed(values, settings):
        raise ExecutionCleanupFailed('Owned native process is still running')
    with pytest.raises(ExecutionCleanupFailed):
        run_doe(cleanup_failed, VARIABLES, count=2,
                record={'path': tmp_path / 'unsafe', 'level': 'summary'})
    assert not (tmp_path / 'unsafe').exists()


def test_de_curve_fit_actual_objective():
    variables = [{'id': 'a', 'unit': 'MPa/s', 'lower': 0., 'upper': 3., 'value': 1.},
                 {'id': 'b', 'unit': 'MPa', 'lower': 0., 'upper': 3., 'value': .5}]
    result = fit_model(linear_curve, variables, [curve_experiment('curve', [0., 1., 2.], [1., 3., 5.])],
                       method='de', options={'max_generations': 35, 'population_size': 12, 'seed': 4})
    assert result['parameters'] == pytest.approx({'a': 2., 'b': 1.}, abs=.005)


@pytest.mark.parametrize('mode', ['batch', 'process'])
def test_least_squares_dispatches_finite_differences_to_prepared_workers(mode):
    variables = [{'id': 'a', 'unit': 'MPa/s', 'lower': 0., 'upper': 3., 'value': 1.},
                 {'id': 'b', 'unit': 'MPa', 'lower': 0., 'upper': 3., 'value': .5}]
    execution = {'mode': mode, 'workers': 2 if mode == 'process' else 1}
    evaluator = linear_curve if mode == 'process' else CurveBatchFactory()
    result = fit_model(evaluator, variables, [curve_experiment('curve', [0., 1., 2.], [1., 3., 5.])], execution=execution)
    assert result['parameters'] == pytest.approx({'a': 2., 'b': 1.}, abs=1e-7)
    assert result['timing']['mode'] == mode


def test_joint_curve_and_event_fit_and_unknown_event_failure():
    variables = [{'id': 'a', 'unit': 'MPa/s', 'lower': .5, 'upper': 4., 'value': 1.},
                 {'id': 'b', 'unit': 'MPa', 'lower': -.9, 'upper': 2., 'value': 0.}]
    curve = curve_experiment('curve', [0., 1., 2., 3., 4.], [1., 3., 5., 7., 9.])
    observed = detect_event(curve['observations'], 3.)
    event = {'id': 'event', 'settings': curve['settings'], 'response': 'crossing', 'observations': observed}
    result = fit_model(event_curve, variables, [curve, event])
    assert result['parameters'] == pytest.approx({'a': 2., 'b': 1.}, abs=1e-6)
    assert result['curves'][1]['prediction']['value'] == pytest.approx(1., abs=1e-6)
    failed = fit_model(event_curve, variables, [dict(event, observations=dict(observed, state='UNKNOWN', value=None))])
    assert failed['execution_status'] == 'FAILED' and failed['parameters'] is None
    assert 'MISSING_OR_UNDETERMINED' in failed['failure_reason']


def test_independent_uq_distribution_and_failure_accounting():
    result = run_uq(quadratic, VARIABLES, {'x': {'distribution': 'uniform'}}, count=32,
                    settings={'fail_above': .75}, seed=8, source={'origin': 'ASSUMED', 'reference': 'Demonstration range'},
                    thresholds=[{'response': 'position', 'unit': 'MPa', 'limit': .5}])
    statistic = result['probability_statistics'][0]
    assert result['sampling']['method'] == 'independent_lhs_inverse_cdf'
    assert statistic['failed_count'] == 8
    assert statistic['failure_fraction'] == .25
    assert statistic['valid_count'] == 24
    assert statistic['exceedance_fraction_valid'] == pytest.approx(1 / 3)
    with pytest.raises(ValueError, match='independent'):
        run_uq(quadratic, VARIABLES, {'x': {'distribution': 'uniform'}}, source=None)


def test_existing_regression_and_rbf_disjoint_holdout_and_prediction_labels():
    training = run_doe(quadratic, VARIABLES, candidates=[{'candidate_id': f'T{i}', 'values': {'x': x}} for i, x in enumerate([0., .2, .4, .6, .8, 1.])])
    holdout = run_doe(quadratic, VARIABLES, candidates=[{'candidate_id': f'H{i}', 'values': {'x': x}} for i, x in enumerate([.1, .3, .5, .7, .9])])
    analysis = analyze_candidates(training, [OBJECTIVE])
    assert analysis['sensitivity'][0]['method'] == 'NORMALIZED_MULTIVARIATE_LEAST_SQUARES'
    assert analysis['surrogate'][0]['method'] == 'SEEDED_HOLDOUT_LEAST_SQUARES'
    surrogate = fit_surrogate(training, holdout, OBJECTIVE, options={'kernel': 'cubic'})
    assert surrogate.validation['rmse'] < .02
    predictions = surrogate.predict([{'x': .5}, {'x': 1.1}])
    assert predictions[0]['execution_status'] == 'PREDICTED'
    assert predictions[1]['out_of_range'] is True
    with pytest.raises(ValueError, match='parameter points overlap'):
        fit_surrogate(training, training, OBJECTIVE)


def test_explicit_file_exchange_preserves_unknown_missing_candidates(tmp_path):
    manifest = export_batch(VARIABLES, [{'x': .1}, {'x': .2}], tmp_path / 'export', case_id='specimen-A')
    assert all(r['execution_status'] == 'NOT_EVALUATED' for r in manifest['candidates'])
    actual = quadratic({'x': .1}, {})
    actual.update(candidate_id='C000000', case_id='specimen-A', values={'x': .1})
    imported = import_batch(manifest, [actual])
    assert imported['imported_count'] == 1
    assert imported['missing_count'] == 1
    assert imported['candidates'][1]['execution_status'] == 'NOT_EVALUATED'
    assert imported['candidates'][0]['responses']['cost']['value'] == pytest.approx(.0225)
    with pytest.raises(ValueError, match='case identity'):
        import_batch(manifest, [dict(actual, case_id='different')])
    with pytest.raises(ValueError, match='parameter values'):
        import_batch(manifest, [dict(actual, values={'x': .3})])


def test_csv_npz_mapping_and_missing_values_are_not_zero_filled(tmp_path):
    mapping = dict(value_column='stress', axis_column='time', axis_name='time', axis_unit='s',
                   unit='MPa', component='xx', location='material_point', reduction='none')
    source = tmp_path / 'observations.csv'
    source.write_text('time,stress\n0,1\n1,\n2,5\n')
    csv = load_observations(source, mapping)
    assert np.isnan(csv['value'][1])
    np.savez(tmp_path / 'observations.npz', time=[0., 1., 2.], stress=[1., np.nan, 5.])
    npz = load_observations(tmp_path / 'observations.npz', mapping)
    np.testing.assert_equal(csv['value'], npz['value'])


def test_imported_curve_comparison_and_explicit_event_states():
    response = curve_experiment('curve', [0., 1., 2.], [0., 2., 4.])['observations']
    observation = curve_experiment('curve', [0., .5, 1., 1.5, 2.], [0., 1., 2., 3., 4.])['observations']
    comparison = compare_curves(response, observation)
    assert comparison['rmse'] == 0.
    crossing = detect_event(response, 3.)
    assert crossing['state'] == 'OCCURRED' and crossing['value'] == 1.5
    assert crossing['unit'] == 's' and crossing['observed_interval'] == [0., 2.]
    not_observed = detect_event(dict(response, value=[0., 1., 2.]), 3.)
    assert not_observed['state'] == 'NOT_OBSERVED' and not_observed['value'] is None
    unknown = detect_event(dict(response, value=[0., np.nan, 4.]), 3.)
    assert unknown['state'] == 'UNKNOWN' and unknown['value'] is None
    initial_exceeded = detect_event(dict(response, value=[4., 5., 6.]), 3.)
    assert initial_exceeded['state'] == 'UNKNOWN' and initial_exceeded['value'] is None
    assert compare_events(crossing, unknown)['residual'] is None
    with pytest.raises(ValueError, match='penalty'):
        compare_events(crossing, not_observed)
    mismatch = compare_events(crossing, not_observed, nonoccurrence_penalty=2., scale=2.)
    assert mismatch['comparable'] and mismatch['residual'] == 1.
    shifted = dict(crossing, value=1.7)
    assert compare_events(shifted, crossing)['residual'] == pytest.approx(.2)
    with pytest.raises(ValueError, match='definition'):
        compare_events(detect_event(response, 2.), crossing)


def test_optional_global_sensitivity_requires_matched_complete_plan():
    pytest.importorskip('SALib')
    plan = sample_sensitivity(VARIABLES, count=32, seed=8)
    table = run_doe(quadratic, VARIABLES, candidates=plan['candidates'])
    result = analyze_sensitivity(plan, table, OBJECTIVE)
    assert result['indices']['ST'][0] == pytest.approx(1., abs=.2)
    with pytest.raises(ValueError, match='matched'):
        analyze_sensitivity(dict(plan, sampling={'method': 'scipy.latin_hypercube'}), table, OBJECTIVE)
    table['candidates'][0]['execution_status'] = 'FAILED'
    with pytest.raises(Exception, match='FAILED'):
        analyze_sensitivity(plan, table, OBJECTIVE)


def test_epsilon_children_reuse_de_and_pareto():
    objectives = [OBJECTIVE, {'response': 'opposite', 'unit': 'MPa', 'direction': 'minimize'}]
    result = epsilon_optimize(quadratic, VARIABLES, objectives, threshold_grid=[[.01, .1]],
                              options={'max_generations': 4, 'population_size': 6}, total_evaluation_budget=60, seed=5)
    assert len(result['children']) == 2
    assert result['pareto']['nondominated_ids']
    assert all(row['candidate_id'].startswith('E') for row in result['candidates'])
    with pytest.raises(ValueError, match='budget'):
        epsilon_optimize(quadratic, VARIABLES, objectives, threshold_grid=[[.01, .1]],
                         options={'max_generations': 4, 'population_size': 6}, total_evaluation_budget=59)


def test_independent_default_doe_ids_can_confirm_surrogate():
    training=run_doe(quadratic,VARIABLES,candidates=[{'x':x} for x in [0.,.2,.4,.6,.8,1.]])
    holdout=run_doe(quadratic,VARIABLES,candidates=[{'x':x} for x in [.1,.3,.5,.7,.9]])
    model=fit_surrogate(training,holdout,OBJECTIVE,options={'kernel':'cubic'})
    assert model.validation['rmse'] < .02
