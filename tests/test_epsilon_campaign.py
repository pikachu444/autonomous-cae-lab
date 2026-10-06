"""Portable TEST ONLY epsilon orchestration; no Core store or native solver."""
from copy import deepcopy
import hashlib
import json

import pytest

from caelab import optimization as opt
from caelab.model_parameters import expected_declaration, expected_settings
from caelab.optimizers.scipy_de import ScipyDifferentialEvolution
from caelab.storage import canonical_hash

from caelab.optimizers import epsilon_campaign as epsilon


def _bytes_sha(value):
    return hashlib.sha256((json.dumps(value, sort_keys=True, indent=2) + '\n').encode()).hexdigest()


def _objectives():
    return [{'source': 'model', 'metric': 'loss', 'unit': 'mm', 'direction': 'minimize'},
            {'source': 'model', 'metric': 'gain', 'unit': 'N', 'direction': 'maximize'}]


def _template(primary_index=0):
    descriptor = {'id': 'x', 'label': 'TEST ONLY X', 'unit': '1', 'value': 1., 'lower': 0., 'upper': 4.,
                  'settings_path': ['inputs', 'x'], 'declaration_paths': [['model', 'geometry', 'values', 'x']]}
    variable = {'parameter_id': 'research_x', 'unit': '1', 'lower_bound': 0., 'upper_bound': 4.,
                'mode': 'free', 'kind': 'continuous', 'target': 'model_analysis', 'input_effect': {'status': 'PASS'},
                'native': {'path': 'x', 'backend': 'TEST_ONLY', 'document': 'b' * 64}, 'source_sha256': 'a' * 64}
    settings = {'inputs': {'x': 1.}, 'fixed': {'immutable': True, 'mesh': 1}}
    declaration = {'model': {'geometry': {'values': {'x': 1.}}, 'materials': []}, 'loads': [],
                   'outputs': {'metrics': ['loss', 'gain']}, 'reference': {'source': 'TEST ONLY synthetic arithmetic'}}
    constraints = [{'source': 'model', 'metric': 'loss', 'unit': 'mm', 'operator': '<=', 'limit': 4., 'scale': 4.}]
    return {'schema_version': '1.0', 'route': 'model_analysis', 'campaign_id': 'C-original', 'study_id': 'S-test',
            'status': 'PLANNED', 'backend': 'TEST_ONLY', 'model_template': settings,
            'model_template_revision': canonical_hash({'settings': settings, 'declaration': declaration}),
            'model_input_descriptors': [descriptor], 'model_declaration': declaration,
            'model_source_fingerprint': {'adapter': 'TEST_ONLY', 'version': 'test-1', 'source_files': {'TEST_ONLY': 'b' * 64},
                                         'runtime': {'version': 'TEST_ONLY-1'}},
            'model_adapter_version': 'test-1', 'registry_revision': 1, 'registry_sha256': 'c' * 64,
            'core_source_sha256': 'd' * 64, 'variables': [variable],
            'algorithm': ScipyDifferentialEvolution().describe([variable], seed=13, max_generations=1,
                          population_size=5, initial_values={'research_x': 1.}, constraint_count=len(constraints)),
            'objective': _objectives()[primary_index], 'constraints': constraints,
            'required_validations': {'model': ['test_numerical']}, 'failure_policy': {'failed_execution': 'STOP'},
            'created_utc': 'TEST_ONLY-original'}


def _arguments(**changes):
    template = _template()
    args = {'parent_id': 'C-tradeoff', 'template_plan': template, 'template_plan_sha256': _bytes_sha(template),
            'source_pins': epsilon.source_pins_for(template, _bytes_sha(template)), 'objectives': _objectives(),
            'primary_index': 0, 'threshold_grid': [
                [{'source': 'model', 'metric': 'gain', 'unit': 'N', 'limit': -3., 'scale': 1.}],
                [{'source': 'model', 'metric': 'gain', 'unit': 'N', 'limit': -2., 'scale': 1.}],
                [{'source': 'model', 'metric': 'gain', 'unit': 'N', 'limit': -1., 'scale': 1.}]],
            'child_budget': {'max_generations': 1, 'population_size': 5}, 'seed': 31, 'total_evaluation_budget': 30}
    args.update(changes)
    return args


def _parent(**changes):
    return epsilon.build_parent(**_arguments(**changes))


def _child_plan(parent, index):
    spec = parent['children'][index - 1]
    plan = deepcopy(parent['template_plan'])
    plan.update(campaign_id=spec['campaign_id'], objective=deepcopy(spec['request']['objective']),
                constraints=deepcopy(spec['request']['constraints']), algorithm=deepcopy(spec['algorithm']),
                created_utc='TEST_ONLY-new-child')
    return plan


def _model_row(plan, index, x, *, metric_overrides=None, status='COMPLETED_REVIEW_REQUIRED', check='PASS'):
    identifier = f"E-{plan['campaign_id']}-{index:04d}"
    values = {'research_x': x}
    assignments = {'x': x}
    settings = expected_settings(plan['model_template'], plan['model_input_descriptors'], assignments)
    declaration = expected_declaration(plan['model_declaration'], plan['model_input_descriptors'], assignments)
    revision = canonical_hash({'settings': settings, 'declaration': declaration})
    validations = [{'type': 'test_numerical', 'status': check, 'evidence_ids': ['EV-TEST_ONLY']},
                   {'type': 'physical_validation', 'status': 'UNKNOWN', 'evidence_ids': []}]
    metrics = {'loss': {'value': x*x, 'unit': 'mm', 'valid': True},
               'gain': {'value': x-3, 'unit': 'N', 'valid': True}}
    metrics.update(deepcopy(metric_overrides or {}))
    native = {'experiment_id': identifier, 'study': {'id': 'S-test'}, 'status': status, 'decision': 'NOT_RELEASED',
              'solver_status': 'FAILED_EXECUTION' if status == 'FAILED_EXECUTION' else 'COMPLETED',
              'converged': status != 'FAILED_EXECUTION', 'metrics': metrics, 'validations': validations,
              'cad_revision': None, 'model_revision': revision, 'campaign_id': plan['campaign_id'], 'input_parameters': values,
              'extensions': {'model_analysis': {'declaration': declaration}},
              'provenance': {'adapter': 'TEST_ONLY', 'adapter_version': 'test-1', 'registry_sha256': plan['registry_sha256'],
                             'core_source_sha256': plan['core_source_sha256'], 'execution_settings': settings}}
    observed = opt._metric(plan['objective'], {'model': native})
    constraints = []
    for definition in plan['constraints']:
        metric = opt._metric(definition, {'model': native})
        residual = (metric['value'] - definition['limit']) / definition['scale'] if metric['valid'] else None
        if residual is not None and definition['operator'] == '>=':
            residual = -residual
        constraints.append({**metric, 'operator': definition['operator'], 'limit': definition['limit'],
                            'scale': definition['scale'], 'residual': residual,
                            'satisfied': residual <= 0 if residual is not None else None})
    usable = opt._usable(native, plan['required_validations']['model'], analysis=True) and observed['valid'] and all(
        c['residual'] is not None for c in constraints)
    row = {'index': index, 'values': values, 'key': opt._key(plan, values), 'model_experiment_id': identifier,
           'model_result_sha256': _bytes_sha(native), 'model_settings': settings, 'model_declaration': declaration,
           'model_revision': revision, 'model_status': status, 'objective': observed, 'constraints': constraints,
           'usable': bool(usable), 'numerically_feasible': bool(usable and all(c['satisfied'] for c in constraints)),
           'failed_execution': status == 'FAILED_EXECUTION', 'unknown': sorted(v['type'] for v in validations if v['status'] == 'UNKNOWN'),
           'failures': [{'experiment_id': identifier, 'type': v['type'], 'evidence_ids': v['evidence_ids']}
                        for v in validations if v['status'] == 'FAIL'], 'decision': 'NOT_RELEASED'}
    return row, (native, row['model_result_sha256'])


def _child_record(parent, index, xs, *, status='COMPLETED_REVIEW_REQUIRED', metric_overrides=None, check='PASS'):
    plan = _child_plan(parent, index)
    receipt = epsilon.bind_child_plan(parent, parent_digest=parent['digest'], index=index,
                                      child_plan=plan, plan_sha256=_bytes_sha(plan))
    rows, resources = [], {}
    for evaluation_index, x in enumerate(xs, 1):
        row, resource = _model_row(plan, evaluation_index, x, metric_overrides=metric_overrides,
                                  status='FAILED_EXECUTION' if status == 'FAILED_EXECUTION' else 'COMPLETED_REVIEW_REQUIRED', check=check)
        rows.append(row); resources[row['model_experiment_id']] = resource
    record = {'schema_version': '1.0', 'campaign_id': plan['campaign_id'], 'route': plan['route'], 'study_id': plan['study_id'],
              'status': status, 'decision': 'NOT_RELEASED', 'plan_sha256': receipt['plan_sha256'],
              'registry_sha256': plan['registry_sha256'], 'algorithm': plan['algorithm'], 'objective': plan['objective'],
              'constraints': plan['constraints'], 'evaluations': rows}
    if status in epsilon._PARTIAL:
        record['plan'] = plan
    return {'receipt': receipt, 'plan': plan, 'record': record,
            'result_sha256': _bytes_sha(record) if status in epsilon._TERMINAL else None}, resources


def test_exact_tradeoff_collects_original_ids_signed_units_and_epsilon_boundaries():
    parent = _parent()
    before = deepcopy(parent)
    records, resources = [], {}
    for index, xs in enumerate(([0., 1., 2., 3.], [0., 1., 2.], [1., 2.]), 1):
        record, native = _child_record(parent, index, xs)
        records = epsilon.append_child_record(parent, parent_digest=parent['digest'], retained_records=records,
                                               child_record=record, experiment_results={**resources, **native})
        resources.update(native)
    result = epsilon.collect(parent, parent_digest=parent['digest'], child_records=records, experiment_results=resources)
    expected = [row['experiment_id'] for row in result['evaluations'] if row['eligible']]
    assert result['pareto']['nondominated_ids'] == expected  # x^2 vs signed x-3: every distinct value trades off.
    assert len(expected) == 6 and result['status'] == 'COMPLETED_REVIEW_REQUIRED'
    first = result['evaluations'][0]
    assert first['vector'][1]['metric'] == {'value': -3., 'unit': 'N', 'valid': True}
    assert first['original_row']['constraints'][-1]['residual'] == 0
    assert result['evaluations'][-1]['original_row']['constraints'][-1]['residual'] == 0
    assert any(item['reason'] == 'EPSILON_OR_ORIGINAL_CONSTRAINT_NOT_SATISFIED' for item in result['exclusions'])
    assert result['unknown'] == ['physical_validation']
    assert result['physical_qualification'] == 'UNKNOWN' and result['decision'] == 'NOT_RELEASED'
    assert 'not a global Pareto front' in ' '.join(result['limitations'])
    for row in result['evaluations']:
        assert row['result_sha256'] == resources[row['experiment_id']][1]
        assert row['original_row']['decision'] == 'NOT_RELEASED'
    assert parent == before


@pytest.mark.parametrize('family', ['model_analysis', 'pde'])
def test_collect_retains_exact_native_model_family_declaration(family):
    parent = _parent()
    child, resources = _child_record(parent, 1, [1.])
    row = child['record']['evaluations'][0]
    identifier = row['model_experiment_id']
    native = deepcopy(resources[identifier][0])
    context = native['extensions'].pop('model_analysis')
    native['extensions'][family] = context
    row['model_result_sha256'] = _bytes_sha(native)
    resources[identifier] = (native, row['model_result_sha256'])
    child['result_sha256'] = _bytes_sha(child['record'])
    result = epsilon.collect(parent, parent_digest=parent['digest'],
                             child_records=[child], experiment_results=resources)
    assert result['evaluations'][0]['result_sha256'] == row['model_result_sha256']
    assert result['evaluations'][0]['original_row']['model_declaration'] == context['declaration']
    assert result['physical_qualification'] == 'UNKNOWN'


@pytest.mark.parametrize('mutation', ['missing', 'ambiguous', 'changed_declaration', 'invalid_context'])
def test_collect_refuses_unbound_or_ambiguous_native_model_family(mutation):
    parent = _parent()
    child, resources = _child_record(parent, 1, [1.])
    row = child['record']['evaluations'][0]
    identifier = row['model_experiment_id']
    native = deepcopy(resources[identifier][0])
    context = native['extensions'].pop('model_analysis')
    native['extensions']['pde'] = context
    if mutation == 'missing':
        native['extensions'].pop('pde')
    elif mutation == 'ambiguous':
        native['extensions']['model_analysis'] = deepcopy(context)
    elif mutation == 'changed_declaration':
        context['declaration']['loads'].append({'TEST_ONLY_unbound_load': 1})
    else:
        native['extensions']['pde'] = None
    row['model_result_sha256'] = _bytes_sha(native)
    resources[identifier] = (native, row['model_result_sha256'])
    child['result_sha256'] = _bytes_sha(child['record'])
    with pytest.raises(ValueError, match='native model family|model status'):
        epsilon.collect(parent, parent_digest=parent['digest'],
                        child_records=[child], experiment_results=resources)


def test_max_primary_min_secondary_uses_original_less_equal_sense_and_retains_constraints():
    template = _template(primary_index=1)
    parent = _parent(template_plan=template, template_plan_sha256=_bytes_sha(template),
                     source_pins=epsilon.source_pins_for(template, _bytes_sha(template)), primary_index=1,
                     threshold_grid=[[{'source': 'model', 'metric': 'loss', 'unit': 'mm', 'limit': 1., 'scale': .5}]])
    child = parent['children'][0]
    assert child['request']['objective']['direction'] == 'maximize'
    assert child['request']['constraints'][:-1] == template['constraints']
    assert child['request']['constraints'][-1] == {'source': 'model', 'metric': 'loss', 'unit': 'mm',
                                                  'limit': 1., 'scale': .5, 'operator': '<='}
    record, resources = _child_record(parent, 1, [0., 1., 2.])
    result = epsilon.collect(parent, parent_digest=parent['digest'], child_records=[record], experiment_results=resources)
    assert result['pareto']['nondominated_ids'] == [row['experiment_id'] for row in result['evaluations'][:2]]
    assert result['evaluations'][1]['original_row']['constraints'][-1]['satisfied'] is True
    assert result['evaluations'][2]['eligible'] is False


@pytest.mark.parametrize('change', [
    {'primary_index': True}, {'primary_index': 2}, {'seed': True}, {'seed': -1}, {'seed': 2**32},
    {'child_budget': {'population_size': True, 'max_generations': 1}},
    {'child_budget': {'population_size': 4, 'max_generations': 1}},
    {'child_budget': {'population_size': 64, 'max_generations': 100}},
    {'total_evaluation_budget': True}, {'total_evaluation_budget': 29}, {'total_evaluation_budget': 513},
    {'parent_id': '../unsafe'}, {'parent_id': 'C' * 53}, {'threshold_grid': []}])
def test_invalid_count_identifiers_and_budgets_cannot_produce_child_specs(change):
    with pytest.raises(ValueError):
        _parent(**change)


@pytest.mark.parametrize('value', [True, float('nan'), float('inf'), -float('inf')])
def test_nonfinite_and_boolean_thresholds_refuse(value):
    args = _arguments()
    args['threshold_grid'][0][0]['limit'] = value
    with pytest.raises(ValueError):
        epsilon.build_parent(**args)


@pytest.mark.parametrize('field,value', [('unit', 'kN'), ('metric', 'loss'), ('source', 'cad'), ('scale', 0), ('scale', True)])
def test_threshold_units_order_source_and_normalization_are_exact(field, value):
    args = _arguments(); args['threshold_grid'][0][0][field] = value
    with pytest.raises(ValueError):
        epsilon.build_parent(**args)


def test_duplicate_objectives_grids_and_target_matching_are_not_moo():
    args = _arguments(); args['objectives'][1] = deepcopy(args['objectives'][0])
    with pytest.raises(ValueError):
        epsilon.build_parent(**args)
    args = _arguments(); args['threshold_grid'][1] = deepcopy(args['threshold_grid'][0])
    with pytest.raises(ValueError):
        epsilon.build_parent(**args)
    args = _arguments(); args['threshold_grid'] = [deepcopy(args['threshold_grid'][0])] * 17
    with pytest.raises(ValueError):
        epsilon.build_parent(**args)
    args = _arguments(); args['template_plan']['objective']['direction'] = 'match'
    args['template_plan_sha256'] = _bytes_sha(args['template_plan'])
    args['source_pins'] = epsilon.source_pins_for(args['template_plan'], args['template_plan_sha256'])
    with pytest.raises(ValueError, match='primary'):
        epsilon.build_parent(**args)
    args = _arguments(); args['template_plan']['observation_target'] = {'TEST_ONLY': 'retained target'}
    with pytest.raises(ValueError, match='matching target'):
        epsilon.build_parent(**args)


def test_stable_child_ids_seed_wrap_and_pure_requests_have_no_solver_side_effects(monkeypatch):
    monkeypatch.setattr(ScipyDifferentialEvolution, 'run', lambda *args, **kwargs: pytest.fail('No optimizer execution in pure helper'))
    args = _arguments(seed=2**32 - 1)
    before = deepcopy(args)
    first, second = epsilon.build_parent(**args), epsilon.build_parent(**args)
    assert first == second and args == before
    assert [c['campaign_id'] for c in first['children']] == ['C-tradeoff-e0001', 'C-tradeoff-e0002', 'C-tradeoff-e0003']
    assert [c['request']['seed'] for c in first['children']] == [2**32 - 1, 0, 1]
    for child in first['children']:
        assert child['request']['constraints'][:1] == args['template_plan']['constraints']
        assert child['algorithm']['constraint_count'] == 2 and child['algorithm']['workers'] == 1
        assert child['algorithm']['engine'] == epsilon.ENGINE
    assert first['planned_maximum_evaluations'] == 30


def test_trusted_parent_digest_and_resume_compare_original_child_plans():
    parent = _parent()
    plan = _child_plan(parent, 1)
    receipt = epsilon.bind_child_plan(parent, parent_digest=parent['digest'], index=1,
                                      child_plan=plan, plan_sha256=_bytes_sha(plan))
    args = {'parent_digest': parent['digest'], 'template_plan': parent['template_plan'],
            'template_plan_sha256': parent['template_plan_sha256'], 'source_pins': parent['source_pins'],
            'child_receipts': [receipt], 'child_plans': {plan['campaign_id']: (plan, receipt['plan_sha256'])}}
    resumed = epsilon.verify_resume(parent, **args)
    assert resumed['verified_children'] == 1 and resumed['next_unbound_child_index'] == 2
    changed = deepcopy(plan); changed['model_template']['fixed']['mesh'] = 99
    with pytest.raises(ValueError, match='conditions/source'):
        epsilon.verify_resume(parent, **{**args, 'child_plans': {plan['campaign_id']: (changed, receipt['plan_sha256'])}})
    with pytest.raises(ValueError, match='hash changed'):
        epsilon.verify_resume(parent, **{**args, 'child_plans': {plan['campaign_id']: (plan, 'f' * 64)}})
    changed_parent = deepcopy(parent); changed_parent['children'][0]['request']['constraints'] = []
    with pytest.raises(ValueError, match='trusted receipt'):
        epsilon.verify_resume(changed_parent, **args)
    changed_parent['digest'] = canonical_hash({k: v for k, v in changed_parent.items() if k != 'digest'})
    with pytest.raises(ValueError, match='trusted receipt'):
        epsilon.verify_resume(changed_parent, **args)


@pytest.mark.parametrize('which', ['registry_sha256', 'core_source_sha256', 'model_source_fingerprint', 'model_input_descriptors',
                                  'model_declaration', 'required_validations', 'variables', 'constraints', 'objective', 'algorithm'])
def test_child_spec_refuses_changed_source_conditions_original_constraints_and_algorithm(which):
    parent = _parent(); plan = _child_plan(parent, 1)
    if which.endswith('sha256'):
        plan[which] = 'e' * 64
    elif which == 'constraints':
        plan[which] = plan[which][1:]
    elif which == 'objective':
        plan[which]['direction'] = 'maximize'
    elif which == 'algorithm':
        plan[which]['seed'] += 1
    elif which == 'variables':
        plan[which][0]['upper_bound'] = 5
    elif which == 'model_input_descriptors':
        plan[which][0]['settings_path'] = ['fixed', 'mesh']
    else:
        plan[which]['TEST_ONLY_tamper'] = True
    with pytest.raises(ValueError, match='conditions/source'):
        epsilon.bind_child_plan(parent, parent_digest=parent['digest'], index=1, child_plan=plan, plan_sha256=_bytes_sha(plan))


@pytest.mark.parametrize('check', ['FAIL', 'UNKNOWN'])
def test_unknown_or_failed_required_validation_is_preserved_not_admitted(check):
    parent = _parent(); record, resources = _child_record(parent, 1, [1.], status='NO_FEASIBLE_DESIGN', check=check)
    result = epsilon.collect(parent, parent_digest=parent['digest'], child_records=[record], experiment_results=resources)
    row = result['evaluations'][0]
    assert not row['eligible'] and row['exclusion'] == 'ROW_UNUSABLE'
    assert not result['pareto']['valid'] and result['pareto']['reason'] == 'NO_ELIGIBLE_SAMPLES'
    assert row['vector'][0]['metric']['valid'] and row['vector'][1]['metric']['valid']
    if check == 'UNKNOWN':
        assert 'test_numerical' in row['unknown']
    else:
        assert row['failures'][0]['type'] == 'test_numerical'


def test_invalid_signed_vector_retains_original_value_and_reason_without_zero_substitution():
    parent = _parent()
    metric = {'value': -2., 'unit': 'N', 'valid': False, 'reason': 'TEST ONLY unverified observation'}
    record, resources = _child_record(parent, 1, [1.], status='NO_FEASIBLE_DESIGN', metric_overrides={'gain': metric})
    result = epsilon.collect(parent, parent_digest=parent['digest'], child_records=[record], experiment_results=resources)
    assert result['evaluations'][0]['vector'][1]['metric'] == metric
    assert not result['evaluations'][0]['eligible']


@pytest.mark.parametrize('tamper', ['native_hash', 'vector_unit', 'vector_bool', 'row_feasible', 'row_source', 'row_key', 'row_fixed_context'])
def test_native_hash_vector_feasibility_and_frozen_context_tamper_refuse(tamper):
    parent = _parent(); record, resources = _child_record(parent, 1, [1.])
    row = record['record']['evaluations'][0]
    native, sha = resources[row['model_experiment_id']]
    if tamper == 'native_hash':
        resources[row['model_experiment_id']] = (native, 'f' * 64)
    elif tamper == 'vector_unit':
        native['metrics']['gain']['unit'] = 'kN'
    elif tamper == 'vector_bool':
        native['metrics']['gain']['value'] = True
    elif tamper == 'row_feasible':
        row['numerically_feasible'] = False
    elif tamper == 'row_source':
        native['provenance']['core_source_sha256'] = 'e' * 64
    elif tamper == 'row_key':
        row['key'] = [float(2).hex()]
    else:
        row['model_settings']['fixed']['mesh'] = 99
    with pytest.raises(ValueError):
        epsilon.collect(parent, parent_digest=parent['digest'], child_records=[record], experiment_results=resources)


def test_failed_and_unknown_children_preserve_records_and_cannot_advance_or_overwrite():
    parent = _parent()
    failed, resources = _child_record(parent, 1, [1.], status='FAILED_EXECUTION')
    result = epsilon.collect(parent, parent_digest=parent['digest'], child_records=[failed], experiment_results=resources)
    assert result['status'] == 'PARTIAL' and result['children'][0]['status'] == 'FAILED_EXECUTION'
    assert result['children'][0]['result_sha256'] is None
    assert result['children'][0]['failure_or_unknown_record'] == failed['record']
    second, extra = _child_record(parent, 2, [1.])
    with pytest.raises(ValueError, match='Do not advance'):
        epsilon.append_child_record(parent, parent_digest=parent['digest'], retained_records=[failed], child_record=second,
                                    experiment_results={**resources, **extra})
    unknown, resources = _child_record(parent, 1, [], status='UNKNOWN')
    unknown['record']['reason'] = 'TEST ONLY lost scheduler ownership; native state not inferred'
    result = epsilon.collect(parent, parent_digest=parent['digest'], child_records=[unknown], experiment_results=resources)
    assert result['children'][0]['failure_or_unknown_record']['reason'] == unknown['record']['reason']
    with pytest.raises(ValueError, match='Do not advance'):
        epsilon.collect(parent, parent_digest=parent['digest'], child_records=[unknown, second], experiment_results=extra)
    completed, resources = _child_record(parent, 1, [1.])
    with pytest.raises(ValueError, match='conditions/source'):
        epsilon.append_child_record(parent, parent_digest=parent['digest'], retained_records=[completed], child_record=completed,
                                    experiment_results=resources)


def test_full_four_objective_order_and_duplicate_zero_thresholds_are_explicit():
    args = _arguments()
    args['objectives'] += [{'source': 'model', 'metric': 'cost', 'unit': 'N', 'direction': 'minimize'},
                           {'source': 'model', 'metric': 'reserve', 'unit': 'N', 'direction': 'maximize'}]
    args['threshold_grid'] = [[{'source': 'model', 'metric': d['metric'], 'unit': d['unit'], 'limit': 1., 'scale': 2.}
                               for d in args['objectives'][1:]]]
    parent = epsilon.build_parent(**args)
    assert [c['operator'] for c in parent['children'][0]['request']['constraints'][1:]] == ['>=', '<=', '>=']
    args = _arguments(); args['threshold_grid'] = [deepcopy(args['threshold_grid'][0]), deepcopy(args['threshold_grid'][0])]
    args['threshold_grid'][0][0]['limit'] = 0.
    args['threshold_grid'][1][0]['limit'] = -0.
    with pytest.raises(ValueError, match='Duplicate'):
        epsilon.build_parent(**args)


def test_resume_refuses_template_bytes_pins_missing_snapshots_and_reordered_children():
    parent = _parent(); plan = _child_plan(parent, 1)
    receipt = epsilon.bind_child_plan(parent, parent_digest=parent['digest'], index=1, child_plan=plan, plan_sha256=_bytes_sha(plan))
    args = {'parent_digest': parent['digest'], 'template_plan': parent['template_plan'],
            'template_plan_sha256': parent['template_plan_sha256'], 'source_pins': parent['source_pins']}
    with pytest.raises(ValueError, match='source/template'):
        epsilon.verify_resume(parent, **{**args, 'template_plan_sha256': 'f' * 64})
    changed = deepcopy(parent['source_pins']); changed['core_source_sha256'] = 'f' * 64
    with pytest.raises(ValueError, match='source/template'):
        epsilon.verify_resume(parent, **{**args, 'source_pins': changed})
    with pytest.raises(ValueError, match='snapshots'):
        epsilon.verify_resume(parent, **args, child_receipts=[receipt])
    receipt['index'] = 2
    with pytest.raises(ValueError, match='order/spec'):
        epsilon.verify_resume(parent, **args, child_receipts=[receipt], child_plans={plan['campaign_id']: (plan, _bytes_sha(plan))})


@pytest.mark.parametrize('which', ['fixed_context', 'algorithm', 'constraint', 'receipt_index', 'native_input', 'objective_value'])
def test_boolean_numeric_aliases_cannot_replace_frozen_typed_json(which):
    parent = _parent()
    if which in ('fixed_context', 'algorithm', 'constraint'):
        plan = _child_plan(parent, 1)
        if which == 'fixed_context':
            plan['model_template']['fixed']['mesh'] = True
        elif which == 'algorithm':
            plan['algorithm']['workers'] = True
        else:
            plan['constraints'][-1]['scale'] = True
        with pytest.raises(ValueError, match='conditions/source'):
            epsilon.bind_child_plan(parent, parent_digest=parent['digest'], index=1, child_plan=plan, plan_sha256=_bytes_sha(plan))
    else:
        record, resources = _child_record(parent, 1, [1.])
        row = record['record']['evaluations'][0]
        if which == 'receipt_index':
            record['receipt']['index'] = True
        elif which == 'native_input':
            resources[row['model_experiment_id']][0]['input_parameters']['research_x'] = True
        else:
            row['objective']['value'] = True
        with pytest.raises(ValueError):
            epsilon.collect(parent, parent_digest=parent['digest'], child_records=[record], experiment_results=resources)


def test_false_completed_classification_cannot_hide_an_infeasible_child():
    parent = _parent()
    record, resources = _child_record(parent, 1, [3.])  # Original loss<=4 is violated.
    with pytest.raises(ValueError, match='status differs'):
        epsilon.collect(parent, parent_digest=parent['digest'], child_records=[record], experiment_results=resources)
    record['record']['status'] = 'NO_FEASIBLE_DESIGN'
    record['result_sha256'] = _bytes_sha(record['record'])
    result = epsilon.collect(parent, parent_digest=parent['digest'], child_records=[record], experiment_results=resources)
    assert not result['evaluations'][0]['eligible'] and result['pareto']['reason'] == 'NO_ELIGIBLE_SAMPLES'


def test_fixed_cad_child_request_keeps_one_conditions_revision_and_refuses_rebinding():
    template = _template()
    for key in list(template):
        if key.startswith('model_'):
            del template[key]
    template.update(route='fixed_cad_analysis', backend='TEST_ONLY_CAD', model='retained_model',
                    cad_adapter_version='test-cad-1', cad_source_fingerprint={'commit': 'TEST_ONLY'},
                    analysis_adapter_version='test-analysis-1', analysis={'backend': 'TEST_ONLY_ANALYSIS', 'settings': {'preserved': True}},
                    fixed_cad={'conditions_id': 'C-saved', 'template_revision': 'e' * 64,
                               'source': {'experiment_id': 'E-parent', 'cad_revision': 'f' * 64, 'result_sha256': 'a' * 64},
                               'fingerprint': {'input_policy': {'TEST_ONLY': 'b' * 64}}},
                    required_validations={'cad': [], 'analysis': ['test_numerical']})
    template['variables'][0]['target'] = 'analysis_conditions'
    for definition in [template['objective'], *template['constraints']]:
        definition['source'] = 'analysis'
    template['algorithm'] = ScipyDifferentialEvolution().describe(template['variables'], seed=13, max_generations=1,
        population_size=5, initial_values={'research_x': 1.}, constraint_count=1)
    objectives = _objectives()
    for objective in objectives:
        objective['source'] = 'analysis'
    grid = [[{'source': 'analysis', 'metric': 'gain', 'unit': 'N', 'limit': -2., 'scale': 1.}]]
    parent = _parent(template_plan=template, template_plan_sha256=_bytes_sha(template),
        source_pins=epsilon.source_pins_for(template, _bytes_sha(template)), objectives=objectives, threshold_grid=grid)
    child = parent['children'][0]
    assert child['request']['conditions_id'] == 'C-saved'
    assert 'backend' not in child['request'] and 'settings' not in child['request']
    plan = _child_plan(parent, 1)
    bound = epsilon.bind_child_plan(parent, parent_digest=parent['digest'], index=1, child_plan=plan, plan_sha256=_bytes_sha(plan))
    changed = deepcopy(plan); changed['fixed_cad']['source']['cad_revision'] = '0' * 64
    with pytest.raises(ValueError, match='conditions/source'):
        epsilon.bind_child_plan(parent, parent_digest=parent['digest'], index=1, child_plan=changed, plan_sha256=bound['plan_sha256'])
    changed = deepcopy(plan); changed['fixed_cad']['conditions_id'] = 'C-other'
    with pytest.raises(ValueError, match='conditions/source'):
        epsilon.bind_child_plan(parent, parent_digest=parent['digest'], index=1, child_plan=changed, plan_sha256=bound['plan_sha256'])
