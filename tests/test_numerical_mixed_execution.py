"""Actual SciPy DOE/DE with independent analytic and finite exhaustive evidence."""
from copy import deepcopy
import numpy as np
import pytest

from caelab import numerical as n, variable_domains as vd
from caelab.contracts import CapabilityUnavailable
from caelab.evaluation import read_result, save_evaluation
from caelab.storage import canonical_hash
from examples.numerical_mixed_algebra import (variables, exhaustive, evaluate, BatchFactory,
                                               OBJECTIVE, CONSTRAINT, EXACT_OPTIMUM)


def test_exhaustive_reference_failures_and_actual_inputs_are_separate(tmp_path):
    table = n.run_doe(evaluate, variables(), candidates=exhaustive(), record={'path': tmp_path/'table', 'level': 'selected', 'selected': [r['candidate_id'] for r in exhaustive()]})
    assert len(table['candidates']) == 18
    assert table['timing']['model_calls'] == 16  # two dependent out-of-range combinations
    assert table['domain_accounting']['dependency_rejections'] == 2
    assert table['execution_status'] == 'PARTIAL_FAILURE'
    physical_failures = [r for r in table['candidates'] if r['execution_status'] == 'FAILED']
    assert len(physical_failures) == 3
    for row in table['candidates']:
        vd.verify_retained(table['domain_input'], table['variables'], row)
        if row['execution_status'] != 'REJECTED':
            assert row['diagnostics']['actual_values'] == row['values']
        else:
            assert row['diagnostics']['domain_error']['code'] == 'OUT_OF_BOUNDS'
            assert row['diagnostics']['model_dispatched'] is False
    successful = [r for r in table['candidates'] if r['execution_status'] == 'SUCCEEDED' and r['values']['capacity'] <= 8]
    best = min(successful, key=lambda r: r['responses']['cost']['value'])
    assert best['responses']['cost']['value'] == EXACT_OPTIMUM['objective']
    assert {k: best['values'][k] for k in ('count','level','branch','x')} == {k: EXACT_OPTIMUM[k] for k in ('count','level','branch','x')}
    saved = read_result(tmp_path/'table')
    assert saved['domain_input'] == table['domain_input']
    assert saved['variables'] == table['variables']
    for row in saved['candidates']:
        vd.verify_retained(saved['domain_input'], saved['variables'], row)


@pytest.mark.parametrize('mode', ['serial', 'batch', 'process'])
def test_real_de_mixed_optimum_integrality_and_total_dispatch(mode):
    table = n.optimize(BatchFactory() if mode == 'batch' else evaluate, variables(), OBJECTIVE,
        constraints=[CONSTRAINT], seed=7, options={'population_size': 18, 'max_generations': 70, 'retain_responses': 'all'},
        execution={'mode': mode, 'workers': 2 if mode == 'process' else 1, 'max_evaluations': 1400})
    assert table['best']['objective'] < 1e-8, table['best']
    assert table['best']['values']['count'] == 2 and table['best']['values']['level'] == 4
    assert table['best']['values']['branch'] == 'left'
    assert abs(table['best']['values']['x'] - .25) < 1e-4
    assert table['algorithm']['integrality'] == [True, True, False, True]
    assert table['timing']['dispatched_evaluations_total'] <= 1400
    assert table['domain_accounting']['model_calls'] == table['timing']['model_calls']
    assert table['solver_dispatch']['feedback_cache_hits'] > 0
    for row in table['candidates']:
        vd.verify_retained(table['domain_input'], table['variables'], row)
        if row['execution_status'] in ('SUCCEEDED', 'FAILED'):
            assert row['values'] == row['diagnostics']['actual_values']
        if row['execution_status'] == 'SUCCEEDED':
            assert row['objective'] == row['responses']['cost']['value']
            assert row['feasible'] == (row['responses']['capacity']['value'] <= 8.)


def test_finite_exhaustion_cache_and_explicit_repeated_rows_are_not_deduplicated():
    rows = exhaustive(finite=True)
    table = n.run_doe(evaluate, variables(finite=True), candidates=rows + [
        {'candidate_id': 'Crepeated', 'values': deepcopy(rows[0]['values'])}])
    accounting = table['domain_accounting']
    assert accounting['requested_rows'] == 19 and accounting['repeat_rows'] == 1
    assert accounting['finite_cartesian_size'] == 18 and accounting['finite_cartesian_covered']
    assert table['timing']['model_calls'] == 17
    opt = n.optimize(evaluate, variables(finite=True), OBJECTIVE, constraints=[CONSTRAINT],
        seed=4, options={'population_size': 12, 'max_generations': 25})
    assert opt['best']['objective'] == 0.
    assert opt['timing']['model_calls'] <= 16
    assert len({canonical_hash(r['values']) for r in opt['candidates']}) == len(opt['candidates'])
    assert opt['solver_dispatch']['feedback_cache_hits'] > 0
    assert opt['solver_dispatch']['unique_feedback_points'] == opt['resolved_encoded_points']


def test_lhs_finite_bins_only_generate_members_no_physical_category_codes():
    table = n.run_doe(evaluate, variables(), count=80, seed=24)
    assert table['sampling']['method'] == 'scipy.latin_hypercube'
    assert table['sampling']['count'] == 80
    assert table['sampling']['category_order'].startswith('declared choice order')
    for row in table['candidates']:
        assert type(row['values']['count']) is int and row['values']['count'] in (1,2,3)
        assert row['values']['level'] in (1,3,4) and type(row['values']['level']) is int
        assert row['values']['branch'] in ('left', 'right')


@pytest.mark.parametrize('mode', ['serial', 'batch', 'process'])
def test_budget_never_dispatches_beyond_actual_allowance(mode):
    execution = {'mode': mode, 'workers': 2 if mode == 'process' else 1, 'max_evaluations': 4}
    factory = BatchFactory() if mode == 'batch' else evaluate
    table = n.run_doe(factory, variables(), candidates=exhaustive(), execution=execution)
    assert table['execution_status'] == 'REJECTED'
    assert table['termination_reason'] == 'EVALUATION_BUDGET_EXHAUSTED'
    assert table['timing']['dispatched_evaluations_total'] <= 4
    assert table['domain_accounting']['requested_rows'] == 18
    assert len(table['candidates']) == 18
    opt = n.optimize(factory, variables(), OBJECTIVE, constraints=[CONSTRAINT], seed=8,
        options={'population_size': 8, 'max_generations': 5}, execution=execution)
    assert opt['execution_status'] == 'REJECTED'
    assert opt['timing']['dispatched_evaluations_total'] <= 4
    assert opt['timing']['model_calls'] <= 4


def test_cancellation_preserves_exact_completed_prefix_and_unrun_inputs():
    calls = []
    def model(v, s):
        calls.append(deepcopy(v)); return evaluate(v, s)
    table = n.run_doe(model, variables(), candidates=exhaustive(), execution={'cancelled': lambda: len(calls) >= 2})
    assert table['execution_status'] == 'CANCELLED' and len(calls) == 2
    assert [r['candidate_id'] for r in table['candidates']] == [r['candidate_id'] for r in exhaustive()]
    assert [r['values'] for r in table['candidates'][:2]] == calls
    assert all(r['execution_status'] == 'CANCELLED' for r in table['candidates'][2:])
    for row in table['candidates']:
        vd.verify_retained(table['domain_input'], table['variables'], row)


def test_all_fixed_and_integer_singleton_do_not_invent_free_coordinates():
    v = [{'id':'a','unit':'1','mode':'fixed','value':2.},
         {'id':'b','unit':'1','kind':'integer','lower':1,'upper':1},
         {'id':'c','unit':'1','mode':'dependent','lower':1,'upper':5,'expression':'a+b'}]
    def model(x,s):
        return {'execution_status':'SUCCEEDED','responses':{'cost':{'kind':'scalar','unit':'1','value':x['c']}}}
    result = n.optimize(model, v, OBJECTIVE, options={'population_size':5, 'max_generations':2})
    assert result['best']['values'] == {'b':1,'a':2.,'c':3.}
    assert result['timing']['model_calls'] == 1
    v[1].update(mode='fixed', value=1)
    result = n.optimize(model, v, OBJECTIVE)
    assert result['algorithm']['solver_called'] is False and result['timing']['model_calls'] == 1


def test_epsilon_reuses_typed_de_without_new_optimizer_or_relabelled_ids():
    result = n.epsilon_optimize(evaluate, variables(finite=True), [OBJECTIVE, {'response':'capacity','unit':'1'}],
        threshold_grid=[[6., 8.]], options={'population_size':6,'max_generations':3}, total_evaluation_budget=48)
    assert result['kind'] == 'epsilon_optimization'
    assert result['domain_accounting']['model_calls'] <= 48
    for row in result['candidates']:
        assert row['candidate_id'].startswith('E')
        vd.verify_retained(result['domain_input'], result['variables'], row)


def test_unsupported_methods_are_blocked_without_hiding_statistics_or_reinterpreting_old_rows(monkeypatch):
    table = n.run_doe(evaluate, variables(), candidates=exhaustive())
    saved_hash = canonical_hash(table)
    analysis = n.analyze_candidates(table, [OBJECTIVE, {'response':'capacity','unit':'1'}])
    assert not analysis['analysis_capabilities']['regression']['available']
    assert all(row['status']=='UNAVAILABLE' and row['rank'] is None for row in analysis['sensitivity'])
    assert analysis['statistics'] and analysis['pareto']
    assert canonical_hash(table) == saved_hash
    def forbidden(*args, **kw):
        raise AssertionError('Unavailable method dispatched an evaluator')
    with pytest.raises(CapabilityUnavailable): n.fit_model(forbidden, variables(), [])
    with pytest.raises(CapabilityUnavailable): n.run_uq(forbidden, variables(), {})
    with pytest.raises(CapabilityUnavailable): n.sample_sensitivity(variables(), count=8)
    with pytest.raises(CapabilityUnavailable): n.analyze_sensitivity(table, table, OBJECTIVE)
    with pytest.raises(CapabilityUnavailable): n.fit_surrogate(table, table, OBJECTIVE)
    continuous = [{'id':'n','unit':'1','lower':1,'upper':3}]
    row = n.run_doe(lambda v,s: {'execution_status':'SUCCEEDED','responses':{'cost':{'kind':'scalar','unit':'1','value':v['n']}}},
                    continuous, candidates=[{'n':1.5}])
    assert row['candidates'][0]['values']['n'] == 1.5 and 'domain_input' not in row
    row['variables'][0]['kind'] = 'integer'
    with pytest.raises(ValueError):
        vd.validate_retained_table(row)


def test_retained_exchange_and_new_explicit_attempt_never_recalculate_dependencies(tmp_path, monkeypatch):
    table = n.run_doe(evaluate, variables(), candidates=exhaustive())
    from caelab import dimensioned_expression
    def forbidden(*a, **kw): raise AssertionError('Retained dependency was reevaluated')
    monkeypatch.setattr(vd.VariableDomains, 'resolve', forbidden)
    monkeypatch.setattr(dimensioned_expression, 'evaluate', forbidden)
    manifest = n.export_batch(table['variables'], table['candidates'], tmp_path/'export', case_id='K-case',
                              domain_input=table['domain_input'])
    restored = read_result(tmp_path/'export')
    assert restored['domain_input'] == table['domain_input']
    row = manifest['candidates'][0]
    received = {**row, 'execution_status':'SUCCEEDED', 'responses':deepcopy(table['candidates'][0]['responses'])}
    imported = n.import_batch(restored, [received])
    assert imported['imported_count']==1 and imported['missing_count']==17
    assert imported['candidates'][0]['domain_assignment']==table['candidates'][0]['domain_assignment']
    forged=deepcopy(received);forged['values']['count']=float(forged['values']['count'])
    with pytest.raises(ValueError): n.import_batch(restored,[forged])
    again=n.run_doe(evaluate,table['variables'],candidates=table['candidates'],domain_input=table['domain_input'])
    assert [r['values'] for r in again['candidates']]==[r['values'] for r in table['candidates']]
    assert again['timing']['model_calls']==16  # New explicit job, not resume or a read.


def test_actual_jobmanager_cancel_keeps_completed_prefix_and_typed_unrun_rows(tmp_path):
    import threading
    from caelab.jobs import JobManager
    entered, release = threading.Event(), threading.Event()
    calls = []
    def controlled(values, settings):
        calls.append(deepcopy(values))
        entered.set()
        assert release.wait(8)
        return evaluate(values, settings)
    def execute(operation, arguments, job_id):
        return n.run_doe(controlled, variables(), candidates=exhaustive(),
                         execution={'max_evaluations': 18})
    manager = JobManager(tmp_path, execute, workers=1, cpu_budget=1)
    try:
        job = manager.submit('doe', {})['id']
        try:
            assert entered.wait(8)
            manager.cancel(job)
        finally:
            release.set()
        manager._futures[job].result(timeout=12)
        assert manager.status(job)['state'] == 'CANCELLED'
        saved = manager.result(job)
        assert len(calls) == 1 and saved['timing']['model_calls'] == 1
        assert len(saved['candidates']) == 18
        assert saved['candidates'][0]['execution_status'] == 'SUCCEEDED'
        assert all(r['execution_status'] == 'CANCELLED' for r in saved['candidates'][1:])
        vd.validate_retained_table(saved)
    finally:
        release.set()
        assert manager.shutdown()['joined']
