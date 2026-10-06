"""Pure epsilon-constraint coordination of existing single-objective DE plans.

No store, process, adapter, admission or native command is touched here. The
caller must supply Core-verified plan/result snapshots and their original byte
SHA256s, recheck the live sources, and persist each spec/receipt append-only.
Digests below identify canonical JSON data; byte SHA256s remain separate.
"""
from copy import deepcopy
import json
import math
import re

import numpy as np

from caelab import optimization as opt
from caelab.optimizers.campaign_analysis import _pareto
from caelab.optimizers.scipy_de import ScipyDifferentialEvolution
from caelab.storage import canonical_hash


ENGINE = 'scipy.differential_evolution'
_ID = re.compile(r'^[A-Za-z][A-Za-z0-9_-]{0,79}$')
_METRIC = re.compile(r'^[A-Za-z][A-Za-z0-9_.-]{0,127}$')
_SHA = re.compile(r'^[0-9a-f]{64}$')
_TERMINAL = {'COMPLETED_REVIEW_REQUIRED', 'NO_FEASIBLE_DESIGN'}
_PARTIAL = {'PLANNED', 'RUNNING', 'FAILED_EXECUTION', 'UNKNOWN'}
_MUTABLE_PLAN_KEYS = {'campaign_id', 'created_utc', 'objective', 'constraints', 'algorithm'}
_LIMITATIONS = [
    'Limited explicit epsilon-constraint search using the existing single-objective DE; not a global Pareto front.',
    'Pareto comparison uses original eligible experiment IDs and exact units, without scalarization, unit conversion or physical inference.',
    'Source/byte verification, Domain admission, native execution, job ownership and append-only persistence remain the existing Core responsibilities.',
    'UNKNOWN engineering checks remain UNKNOWN; numerical feasibility is not physical feasibility or release.',
]


def _json(value, label, limit=8 * 1024 * 1024):
    count = 0
    def visit(item, depth=0):
        nonlocal count
        count += 1
        if depth > 48 or count > 300000:
            raise ValueError(f'{label} exceeds the bounded JSON structure')
        if type(item) is float and not math.isfinite(item):
            raise ValueError(f'{label} contains a nonfinite value')
        if type(item) is dict:
            if any(type(key) is not str for key in item):
                raise ValueError(f'{label} requires string JSON keys')
            for child in item.values():
                visit(child, depth + 1)
        elif type(item) is list:
            for child in item:
                visit(child, depth + 1)
        elif type(item) not in (str, int, float, bool, type(None)):
            raise ValueError(f'{label} must be JSON data')
    try:
        visit(value)
        if len(json.dumps(value, allow_nan=False, ensure_ascii=False).encode()) > limit:
            raise ValueError(f'{label} exceeds the bounded JSON bytes')
    except (RecursionError, OverflowError, TypeError) as error:
        raise ValueError(f'{label} must be bounded finite JSON') from error


def _shape(value, keys, label):
    if type(value) is not dict or set(value) != set(keys):
        raise ValueError(f'{label} has unexpected or missing fields')


def _number(value, label):
    if not opt._number(value):
        raise ValueError(f'{label} must be finite and nonboolean')
    return value


def _identifier(value, label, maximum=80):
    if type(value) is not str or len(value) > maximum or not _ID.fullmatch(value):
        raise ValueError(f'{label} is not a bounded identifier')
    return value


def _sha(value, label):
    if type(value) is not str or not _SHA.fullmatch(value):
        raise ValueError(f'{label} must be an original SHA256')
    return value


def _seal(payload, key='digest'):
    return {**deepcopy(payload), key: canonical_hash(payload)}


def _same(first, second):
    """Keep typed JSON identity; Python equality conflates True, 1 and 1.0."""
    return canonical_hash(first) == canonical_hash(second)


def _context(plan):
    return {key: deepcopy(value) for key, value in plan.items() if key not in _MUTABLE_PLAN_KEYS}


def source_pins_for(template_plan, template_plan_sha256):
    """Derive the expected pins from an already verified original Core plan."""
    _sha(template_plan_sha256, 'Template plan byte hash')
    _json(template_plan, 'Template plan')
    if type(template_plan) is not dict or template_plan.get('route') not in ('model_analysis', 'fixed_cad_analysis'):
        raise ValueError('Only frozen declared-model and fixed-CAD condition plans are supported')
    for key in ('core_source_sha256', 'registry_sha256'):
        _sha(template_plan.get(key), key)
    return {'template_plan_sha256': template_plan_sha256,
            'template_digest': canonical_hash(template_plan),
            'context_digest': canonical_hash(_context(template_plan)),
            'core_source_sha256': template_plan['core_source_sha256'],
            'registry_sha256': template_plan['registry_sha256'],
            'engine_algorithm_digest': canonical_hash(template_plan.get('algorithm'))}


def _objectives(objectives, route, primary_index):
    if type(objectives) is not list or not 2 <= len(objectives) <= 4:
        raise ValueError('Declare 2..4 distinct scalar objectives')
    if type(primary_index) is not int or not 0 <= primary_index < len(objectives):
        raise ValueError('Select one exact primary objective index')
    names = set()
    for item in objectives:
        _shape(item, {'source', 'metric', 'unit', 'direction'}, 'Objective')
        if (item['source'] != ('model' if route == 'model_analysis' else 'analysis')
                or type(item['metric']) is not str or not _METRIC.fullmatch(item['metric'])
                or item['metric'] in names or type(item['unit']) is not str or not item['unit'].strip()
                or len(item['unit']) > 128 or item['direction'] not in ('minimize', 'maximize')):
            raise ValueError('Objectives require distinct advertised metrics, exact units and min/max directions')
        names.add(item['metric'])
    return [item for index, item in enumerate(objectives) if index != primary_index]


def _constraints(items, route):
    if type(items) is not list or len(items) > 16:
        raise ValueError('Original constraints must retain the existing bounded list')
    for item in items:
        _shape(item, {'source', 'metric', 'unit', 'operator', 'limit', 'scale'}, 'Original constraint')
        if (item['source'] != ('model' if route == 'model_analysis' else 'analysis')
                or type(item['metric']) is not str or not _METRIC.fullmatch(item['metric'])
                or type(item['unit']) is not str or not item['unit'].strip()
                or item['operator'] not in ('<=', '>=')):
            raise ValueError('Original constraint source/metric/unit/sense is unsupported')
        _number(item['limit'], 'Original constraint limit')
        if _number(item['scale'], 'Original constraint scale') <= 0:
            raise ValueError('Original constraint normalization must be positive')


def _configuration(template, objectives, primary_index, grid, budget, seed, total_budget):
    _json(template, 'Template plan')
    route = template.get('route')
    if (route not in ('model_analysis', 'fixed_cad_analysis') or template.get('schema_version') != '1.0'
            or template.get('status') != 'PLANNED' or 'observation_target' in template):
        raise ValueError('A frozen supported DE plan without a matching target is required')
    _identifier(template.get('campaign_id'), 'Template campaign', 58)
    _identifier(template.get('study_id'), 'Study')
    secondary = _objectives(objectives, route, primary_index)
    if template.get('objective') != objectives[primary_index]:
        raise ValueError('The frozen single-objective plan must match the selected primary exactly')
    _constraints(template.get('constraints'), route)
    if len(template['constraints']) + len(secondary) > 16:
        raise ValueError('Original and epsilon constraints exceed the existing child contract')
    required = ({'model_template', 'model_template_revision', 'model_input_descriptors', 'model_declaration',
                 'model_source_fingerprint', 'model_adapter_version'} if route == 'model_analysis' else
                {'fixed_cad', 'model', 'analysis', 'cad_adapter_version', 'cad_source_fingerprint', 'analysis_adapter_version'})
    if not required <= set(template) or not {'variables', 'registry_revision', 'required_validations', 'failure_policy',
                                            'algorithm', 'core_source_sha256', 'registry_sha256'} <= set(template):
        raise ValueError('Template omits original route/source/admission context')
    if (template['failure_policy'].get('failed_execution') != 'STOP'
            or type(template['variables']) is not list or not 1 <= len(template['variables']) <= 32):
        raise ValueError('Preserve the original fail-stop policy and bounded registered variables')
    _shape(budget, {'max_generations', 'population_size'}, 'Child budget')
    if (type(budget['max_generations']) is not int or not 1 <= budget['max_generations'] <= 100
            or type(budget['population_size']) is not int or not 5 <= budget['population_size'] <= 64
            or type(seed) is not int or not 0 <= seed <= 2**32 - 1
            or type(total_budget) is not int or not 1 <= total_budget <= 512):
        raise ValueError('Use existing bounded child DE budgets and an unsigned seed')
    if type(grid) is not list or not 1 <= len(grid) <= 16:
        raise ValueError('An explicit ordered threshold grid requires 1..16 children')
    maximum = budget['population_size'] * (budget['max_generations'] + 1)
    if maximum > 512 or maximum * len(grid) > total_budget:
        raise ValueError('The worst-case sum of child evaluation budgets exceeds the declared total')
    seen = set()
    for row in grid:
        if type(row) is not list or len(row) != len(secondary):
            raise ValueError('Each grid row must list every secondary objective in declared order')
        limits = []
        for item, objective in zip(row, secondary):
            _shape(item, {'source', 'metric', 'unit', 'limit', 'scale'}, 'Epsilon threshold')
            if any(item[key] != objective[key] for key in ('source', 'metric', 'unit')):
                raise ValueError('Epsilon threshold order/source/metric/unit differs from its objective')
            limit = _number(item['limit'], 'Epsilon threshold')
            if _number(item['scale'], 'Epsilon scale') <= 0:
                raise ValueError('Epsilon normalization must be positive')
            limits.append(float(limit))
        if tuple(limits) in seen:
            raise ValueError('Duplicate epsilon threshold vectors are not separate searches')
        seen.add(tuple(limits))
    return secondary, maximum


def _request(template, campaign_id, objective, constraints, budget, seed):
    value = {'study_id': template['study_id'], 'campaign_id': campaign_id,
             'parameter_ids': [v['parameter_id'] for v in template['variables']], 'objective': deepcopy(objective),
             'constraints': deepcopy(constraints), 'seed': seed, **deepcopy(budget),
             'initial_values': deepcopy(template['algorithm']['initial_values']),
             'required_validations': deepcopy(template['required_validations']), 'engine': ENGINE}
    if template['route'] == 'model_analysis':
        value.update(backend=template['backend'], settings=deepcopy(template['model_template']))
    else:
        value['conditions_id'] = template['fixed_cad']['conditions_id']
    return value


def build_parent(*, parent_id, template_plan, template_plan_sha256, source_pins, objectives, primary_index,
                 threshold_grid, child_budget, seed, total_evaluation_budget):
    """Freeze child requests; the caller creates real plans with existing Core."""
    _identifier(parent_id, 'Parent ID', 52)
    secondary, maximum = _configuration(template_plan, objectives, primary_index, threshold_grid,
                                        child_budget, seed, total_evaluation_budget)
    expected_pins = source_pins_for(template_plan, template_plan_sha256)
    if source_pins != expected_pins:
        raise ValueError('Source pins differ from the verified frozen template')
    numerical = ScipyDifferentialEvolution()
    algorithm = template_plan['algorithm']
    if algorithm.get('engine') != ENGINE or algorithm.get('version') != numerical.version:
        raise ValueError('Use the same explicitly frozen existing DE engine version')
    original = numerical.describe(template_plan['variables'], seed=algorithm['seed'],
                                   max_generations=algorithm['max_generations'], population_size=algorithm['population_size'],
                                   initial_values=algorithm['initial_values'], constraint_count=len(template_plan['constraints']))
    if canonical_hash(original) != canonical_hash(algorithm):
        raise ValueError('Template DE algorithm differs from its exact deterministic description')
    children = []
    for index, thresholds in enumerate(threshold_grid, 1):
        identifier = f'{parent_id}-e{index:04d}'
        if identifier == template_plan['campaign_id']:
            raise ValueError('A child cannot overwrite the original template campaign')
        epsilon = [{**{key: item[key] for key in ('source', 'metric', 'unit', 'limit', 'scale')},
                    'operator': '<=' if objective['direction'] == 'minimize' else '>='}
                   for item, objective in zip(thresholds, secondary)]
        constraints = deepcopy(template_plan['constraints']) + epsilon
        child_seed = (seed + index - 1) % 2**32
        request = _request(template_plan, identifier, objectives[primary_index], constraints, child_budget, child_seed)
        child_algorithm = numerical.describe(template_plan['variables'], seed=child_seed, **child_budget,
                                              initial_values=request['initial_values'], constraint_count=len(constraints))
        children.append(_seal({'index': index, 'campaign_id': identifier, 'request': request, 'algorithm': child_algorithm,
                               'context_digest': expected_pins['context_digest'], 'source_pins': deepcopy(expected_pins),
                               'maximum_evaluations': maximum}))
    return _seal({'schema_version': '1.0', 'type': 'epsilon_constraint_parent', 'parent_id': parent_id,
                  'template_plan': deepcopy(template_plan), 'template_plan_sha256': template_plan_sha256,
                  'source_pins': deepcopy(expected_pins), 'objectives': deepcopy(objectives), 'primary_index': primary_index,
                  'threshold_grid': deepcopy(threshold_grid), 'child_budget': deepcopy(child_budget), 'seed': seed,
                  'total_evaluation_budget': total_evaluation_budget, 'planned_maximum_evaluations': maximum * len(children),
                  'children': children, 'decision': 'NOT_RELEASED', 'physical_qualification': 'UNKNOWN',
                  'limitations': _LIMITATIONS[:]})


def _parent(parent, parent_digest):
    _json(parent, 'Parent record')
    _sha(parent_digest, 'Trusted parent canonical digest')
    if (type(parent) is not dict or parent.get('digest') != parent_digest
            or canonical_hash({key: value for key, value in parent.items() if key != 'digest'}) != parent_digest
            or parent.get('type') != 'epsilon_constraint_parent' or parent.get('schema_version') != '1.0'
            or parent.get('decision') != 'NOT_RELEASED' or parent.get('physical_qualification') != 'UNKNOWN'):
        raise ValueError('Parent identity/digest/qualification differs from its trusted receipt')
    _identifier(parent['parent_id'], 'Parent ID', 52)
    _configuration(parent['template_plan'], parent['objectives'], parent['primary_index'], parent['threshold_grid'],
                   parent['child_budget'], parent['seed'], parent['total_evaluation_budget'])
    if (source_pins_for(parent['template_plan'], parent['template_plan_sha256']) != parent['source_pins']
            or len(parent['children']) != len(parent['threshold_grid'])):
        raise ValueError('Parent source/child sequence changed')
    for index, child in enumerate(parent['children'], 1):
        if (child.get('index') != index or child.get('campaign_id') != f"{parent['parent_id']}-e{index:04d}"
                or child.get('context_digest') != parent['source_pins']['context_digest']
                or child.get('source_pins') != parent['source_pins']
                or child.get('digest') != canonical_hash({k: v for k, v in child.items() if k != 'digest'})):
            raise ValueError('Child spec digest/sequence/source changed')
    return parent


def bind_child_plan(parent, *, parent_digest, index, child_plan, plan_sha256):
    """Check a real Core child plan; return a receipt for append-only storage."""
    _parent(parent, parent_digest)
    if type(index) is not int or not 1 <= index <= len(parent['children']):
        raise ValueError('Child index must belong to the frozen parent')
    _sha(plan_sha256, 'Original child plan byte SHA256')
    _json(child_plan, 'Verified child plan')
    child = parent['children'][index - 1]
    request = child['request']
    if (child_plan.get('campaign_id') != child['campaign_id'] or not _same(_context(child_plan), _context(parent['template_plan']))
            or not _same(child_plan.get('objective'), request['objective'])
            or not _same(child_plan.get('constraints'), request['constraints'])
            or not _same(child_plan.get('algorithm'), child['algorithm'])):
        raise ValueError('Child plan changed frozen conditions/source/constraints/DE spec')
    return {'index': index, 'campaign_id': child['campaign_id'], 'parent_digest': parent_digest,
            'spec_digest': child['digest'], 'plan_digest': canonical_hash(child_plan), 'plan_sha256': plan_sha256}


def verify_resume(parent, *, parent_digest, template_plan, template_plan_sha256, source_pins,
                  child_receipts=None, child_plans=None):
    """Refuse replacement of the template/pins or any previously bound child."""
    _parent(parent, parent_digest)
    if (canonical_hash(template_plan) != parent['source_pins']['template_digest']
            or template_plan_sha256 != parent['template_plan_sha256'] or source_pins != parent['source_pins']
            or source_pins_for(template_plan, template_plan_sha256) != source_pins):
        raise ValueError('Resume source/template differs from the exact frozen parent')
    receipts = child_receipts if child_receipts is not None else []
    if type(receipts) is not list or len(receipts) > len(parent['children']):
        raise ValueError('Child receipt sequence is invalid')
    plans = child_plans if child_plans is not None else {}
    if type(plans) is not dict or set(plans) != {r.get('campaign_id') for r in receipts}:
        raise ValueError('Resume requires the exact verified child plan snapshots')
    for index, receipt in enumerate(receipts, 1):
        _shape(receipt, {'index', 'campaign_id', 'parent_digest', 'spec_digest', 'plan_digest', 'plan_sha256'}, 'Child receipt')
        child = parent['children'][index - 1]
        if (type(receipt['index']) is not int or receipt['index'] != index or receipt['campaign_id'] != child['campaign_id']
                or receipt['parent_digest'] != parent_digest or receipt['spec_digest'] != child['digest']):
            raise ValueError('Resume child receipt order/spec changed')
        _sha(receipt['plan_digest'], 'Child plan canonical digest')
        _sha(receipt['plan_sha256'], 'Child plan original byte SHA256')
        resource = plans[receipt['campaign_id']]
        if type(resource) not in (tuple, list) or len(resource) != 2 or not _same(bind_child_plan(
                parent, parent_digest=parent_digest, index=index, child_plan=resource[0], plan_sha256=resource[1]), receipt):
            raise ValueError('Resume child plan/byte hash changed since binding')
    return {'verified_children': len(receipts),
            'next_unbound_child_index': len(receipts) + 1 if len(receipts) < len(parent['children']) else None,
            'parent_digest': parent_digest, 'decision': 'NOT_RELEASED'}


def _native(experiment_results, identifier, expected_sha, plan, row, model=True):
    _identifier(identifier, 'Original experiment ID')
    _sha(expected_sha, 'Original experiment result hash')
    resource = experiment_results.get(identifier)
    if type(resource) not in (tuple, list) or len(resource) != 2 or resource[1] != expected_sha:
        raise ValueError('Original native result is missing or its byte hash differs')
    result = resource[0]
    _json(result, 'Verified original native result')
    if (type(result) is not dict or result.get('experiment_id') != identifier
            or result.get('study', {}).get('id') != plan['study_id'] or result.get('decision') != 'NOT_RELEASED'
            or type(result.get('validations')) is not list or type(result.get('metrics')) is not dict):
        raise ValueError('Original native result identity/study/verdict is incompatible')
    if model:
        if (result.get('cad_revision') is not None or result.get('model_revision') != row.get('model_revision')
                or result.get('campaign_id') != plan['campaign_id'] or not _same(result.get('input_parameters'), row['values'])
                or result['provenance'].get('adapter') != plan['backend']
                or result['provenance'].get('adapter_version') != plan['model_adapter_version']
                or result['provenance'].get('core_source_sha256') != plan['core_source_sha256']
                or result['provenance'].get('registry_sha256') != plan['registry_sha256']):
            raise ValueError('Original model result changed frozen revision/source/binding')
    elif result.get('cad_revision') != plan['fixed_cad']['source']['cad_revision']:
        raise ValueError('Original fixed-CAD result changed CAD revision')
    return result


def _row(parent, child_plan, row, experiment_results):
    if type(row) is not dict or type(row.get('index')) is not int or row['index'] < 1:
        raise ValueError('Native evaluation index is malformed')
    if row.get('key') != opt._key(child_plan, row['values']):
        raise ValueError('Evaluation exact numerical key differs from its original values')
    route = child_plan['route']
    if route == 'model_analysis':
        from caelab.model_parameters import expected_settings, expected_declaration
        assignments = {v['native']['path']: row['values'][v['parameter_id']] for v in child_plan['variables']}
        if (canonical_hash(row['model_settings']) != canonical_hash(expected_settings(
                child_plan['model_template'], child_plan['model_input_descriptors'], assignments))
                or row['model_revision'] != canonical_hash({'settings': row['model_settings'], 'declaration': row['model_declaration']})
                or row['model_declaration'] and canonical_hash(row['model_declaration']) != canonical_hash(expected_declaration(
                    child_plan['model_declaration'], child_plan['model_input_descriptors'], assignments))):
            raise ValueError('Evaluation changed fixed model context or its declared scalar binding')
        identifier, result_sha = row['model_experiment_id'], row['model_result_sha256']
        if identifier != f"E-{child_plan['campaign_id']}-{row['index']:04d}":
            raise ValueError('Evaluation ID differs from its frozen child sequence')
        native = _native(experiment_results, identifier, result_sha, child_plan, row)
        namespaces = set(native.get('extensions', {})) & {'model_analysis', 'pde'}
        if len(namespaces) != 1:
            raise ValueError('Evaluation requires one unambiguous native model family')
        native_context = native['extensions'][next(iter(namespaces))]
        if (row.get('model_status') != native['status']
                or not _same(native['provenance'].get('execution_settings'), row['model_settings'])
                or type(native_context) is not dict
                or not _same(native_context.get('declaration', {}), row['model_declaration'])
                or not row['model_declaration'] and (native['status'] != 'REJECTED' or native['solver_status'] != 'NOT_RUN')):
            raise ValueError('Evaluation model status differs from its original result')
        results, required = {'model': native}, child_plan['required_validations']['model']
        admitted = opt._usable(native, required, analysis=True)
    else:
        from caelab.fixed_cad_optimization import validate_candidate
        validate_candidate(child_plan, row)
        cad_id = row['cad_experiment_id']
        if cad_id != child_plan['fixed_cad']['source']['experiment_id']:
            raise ValueError('Evaluation changed its immutable CAD parent')
        cad = _native(experiment_results, cad_id, row['cad_result_sha256'], child_plan, row, False)
        if row['cad_result_sha256'] != child_plan['fixed_cad']['source']['result_sha256'] or row.get('cad_status') != cad['status']:
            raise ValueError('Evaluation CAD source/status differs from its frozen parent')
        identifier, result_sha = row['analysis_experiment_id'], row['analysis_result_sha256']
        native = None
        if identifier is not None:
            if identifier != f"E-{child_plan['campaign_id']}-{row['index']:04d}":
                raise ValueError('Evaluation analysis ID differs from its child sequence')
            native = _native(experiment_results, identifier, result_sha, child_plan, row, False)
            if (row.get('analysis_status') != native['status'] or native.get('parent_experiment_id') != cad_id
                    or native['provenance'].get('adapter') != child_plan['analysis']['backend']
                    or native['provenance'].get('adapter_version') != child_plan['analysis_adapter_version']
                    or native['provenance'].get('core_source_sha256') != child_plan['core_source_sha256']
                    or native['provenance'].get('analysis_conditions', {}).get('id') != row['conditions_id']):
                raise ValueError('Original analysis changed condition/source/parent binding')
        elif (result_sha is not None or row.get('analysis_status') != 'SKIPPED_DOMAIN_CONDITION_REJECTED'
                or row.get('conditions_id') is not None or row.get('condition_declaration') is not None
                or not str(row.get('condition_input_rejection', '')).startswith('ConditionInputRejected: ')):
            raise ValueError('Missing analysis may only retain an explicit Domain rejection')
        results = {'cad': cad, 'analysis': native}
        admitted = (opt._usable(cad, child_plan['required_validations']['cad']) and
                    opt._usable(native, child_plan['required_validations']['analysis'], analysis=True))
    objective = opt._metric(child_plan['objective'], results)
    constraints = []
    for definition in child_plan['constraints']:
        observed = opt._metric(definition, results)
        residual = ((observed['value'] - definition['limit']) / definition['scale']) if observed['valid'] else None
        if residual is not None and definition['operator'] == '>=':
            residual = -residual
        if residual is not None and not opt._number(residual):
            residual = None
        constraints.append({**observed, 'operator': definition['operator'], 'limit': definition['limit'],
                            'scale': definition['scale'], 'residual': residual,
                            'satisfied': residual <= 0 if residual is not None else None})
    usable = bool(admitted and objective['valid'] and all(c['residual'] is not None for c in constraints))
    feasible = bool(usable and all(c['satisfied'] for c in constraints))
    failed = any(r and r['status'] == 'FAILED_EXECUTION' for r in results.values())
    unknown = sorted({v['type'] for r in results.values() if r for v in r['validations'] if v['status'] == 'UNKNOWN'})
    failures = [{'experiment_id': r['experiment_id'], 'type': v['type'], 'evidence_ids': deepcopy(v['evidence_ids'])}
                for r in results.values() if r for v in r['validations'] if v['status'] == 'FAIL']
    if (any(type(row.get(key)) is not bool for key in ('usable', 'numerically_feasible', 'failed_execution'))
            or row['usable'] != usable or row['numerically_feasible'] != feasible or row['failed_execution'] != bool(failed)
            or row.get('decision') != 'NOT_RELEASED' or not _same(row.get('objective'), objective)
            or not _same(row.get('constraints'), constraints)
            or not _same(row.get('unknown'), unknown) or not _same(row.get('failures'), failures)):
        raise ValueError('Evaluation feasibility/verdict differs from its original Core/native observations')
    vector, invalid = [], []
    for definition in parent['objectives']:
        metric = native['metrics'].get(definition['metric']) if native else None
        if metric is None:
            metric = {'value': None, 'unit': definition['unit'], 'valid': False, 'reason': 'MISSING_ORIGINAL_METRIC'}
        if (type(metric) is not dict or type(metric.get('valid')) is not bool or metric.get('unit') != definition['unit']
                or metric.get('value') is not None and not opt._number(metric['value'])
                or metric['valid'] and not opt._number(metric.get('value'))):
            raise ValueError('Original vector contains malformed values/validity or a different unit')
        vector.append({'definition': deepcopy(definition), 'metric': deepcopy(metric)})
        if not metric['valid']:
            invalid.append(definition['metric'])
    exclusion = ('FAILED_EXECUTION' if failed else 'ROW_UNUSABLE' if not usable else
                 'EPSILON_OR_ORIGINAL_CONSTRAINT_NOT_SATISFIED' if not feasible else
                 'INVALID_VECTOR:' + ','.join(invalid) if invalid else None)
    return {'child_campaign_id': child_plan['campaign_id'], 'evaluation_index': row['index'],
            'experiment_id': identifier, 'result_sha256': result_sha, 'original_row': deepcopy(row),
            'vector': vector, 'numerically_feasible': feasible, 'eligible': exclusion is None,
            'exclusion': exclusion, 'unknown': unknown, 'failures': failures, 'decision': 'NOT_RELEASED'}


def collect(parent, *, parent_digest, child_records, experiment_results):
    """Retain every child row; archive eligible original experiments only."""
    _parent(parent, parent_digest)
    if (type(child_records) is not list or len(child_records) > len(parent['children'])
            or type(experiment_results) is not dict):
        raise ValueError('Child records and verified native results have incompatible shapes')
    rows, children, ids, unresolved = [], [], set(), False
    for index, item in enumerate(child_records, 1):
        if unresolved:
            raise ValueError('Do not advance past a failed/unfinished/unknown child')
        _shape(item, {'receipt', 'plan', 'record', 'result_sha256'}, 'Child record envelope')
        receipt = item['receipt']
        bound = bind_child_plan(parent, parent_digest=parent_digest, index=index,
                                child_plan=item['plan'], plan_sha256=receipt['plan_sha256'])
        if not _same(bound, receipt):
            raise ValueError('Child receipt changed original plan/spec identity')
        record, plan = item['record'], item['plan']
        _json(record, 'Verified child record')
        status = record.get('status')
        if status not in _TERMINAL | _PARTIAL or record.get('decision') != 'NOT_RELEASED':
            raise ValueError('Child status/release verdict is unsupported')
        if status in _TERMINAL:
            _sha(item['result_sha256'], 'Original completed child result byte SHA256')
            if (record.get('campaign_id') != plan['campaign_id'] or record.get('route') != plan['route']
                    or record.get('study_id') != plan['study_id'] or record.get('plan_sha256') != receipt['plan_sha256']
                    or record.get('registry_sha256') != plan['registry_sha256'] or not _same(record.get('algorithm'), plan['algorithm'])
                    or not _same(record.get('objective'), plan['objective']) or not _same(record.get('constraints'), plan['constraints'])):
                raise ValueError('Completed child result changed its frozen plan')
        elif item['result_sha256'] is not None or not _same(record.get('plan'), plan):
            raise ValueError('Partial child must retain its Core plan without inventing a published result hash')
        evaluations = record.get('evaluations')
        if type(evaluations) is not list or len(evaluations) > parent['children'][index - 1]['maximum_evaluations']:
            raise ValueError('Child evaluations exceed the explicit numerical budget')
        child_rows = []
        for evaluation_index, original in enumerate(evaluations, 1):
            if original.get('index') != evaluation_index:
                raise ValueError('Child evaluation sequence contains a gap/reordering')
            row = _row(parent, plan, original, experiment_results)
            if row['experiment_id'] is not None:
                if row['experiment_id'] in ids:
                    raise ValueError('Original experiment ID is reused across child evaluations')
                ids.add(row['experiment_id'])
            child_rows.append(row)
        any_failed = any(r['original_row']['failed_execution'] for r in child_rows)
        if (status in _TERMINAL and (not child_rows or any_failed)
                or status == 'FAILED_EXECUTION' and not any_failed
                or status == 'COMPLETED_REVIEW_REQUIRED' and not any(r['numerically_feasible'] for r in child_rows)
                or status == 'NO_FEASIBLE_DESIGN' and any(r['numerically_feasible'] for r in child_rows)):
            raise ValueError('Child status differs from its retained native evaluation state')
        unresolved = status not in _TERMINAL
        rows.extend(child_rows)
        children.append({'index': index, 'receipt': deepcopy(receipt), 'status': status,
                         'result_sha256': item['result_sha256'], 'record_digest': canonical_hash(record),
                         'evaluation_count': len(evaluations), 'unknown': sorted({u for r in child_rows for u in r['unknown']}),
                         'failure_or_unknown_record': deepcopy(record) if unresolved else None})
    eligible = [row for row in rows if row['eligible']]
    values = np.array([[entry['metric']['value'] for entry in row['vector']] for row in eligible], dtype=float).reshape(
        len(eligible), len(parent['objectives']))
    definitions = [{key: d[key] for key in ('metric', 'unit', 'direction')} for d in parent['objectives']]
    archive = _pareto(values, definitions, [r['experiment_id'] for r in eligible])
    complete = len(children) == len(parent['children']) and not unresolved
    return {'schema_version': '1.0', 'type': 'epsilon_constraint_result', 'parent_id': parent['parent_id'],
            'parent_digest': parent_digest, 'status': 'COMPLETED_REVIEW_REQUIRED' if complete else 'PARTIAL',
            'children': children, 'evaluations': rows, 'pareto': archive,
            'exclusions': [{'child_campaign_id': r['child_campaign_id'], 'experiment_id': r['experiment_id'],
                            'evaluation_index': r['evaluation_index'], 'reason': r['exclusion']} for r in rows if not r['eligible']],
            'unknown': sorted({u for r in rows for u in r['unknown']}),
            'decision': 'NOT_RELEASED', 'physical_qualification': 'UNKNOWN', 'limitations': _LIMITATIONS[:]}


def append_child_record(parent, *, parent_digest, retained_records, child_record, experiment_results):
    """Return a new prefix; existing receipts/records can never be replaced."""
    collect(parent, parent_digest=parent_digest, child_records=retained_records, experiment_results=experiment_results)
    records = deepcopy(retained_records) + [deepcopy(child_record)]
    collect(parent, parent_digest=parent_digest, child_records=records, experiment_results=experiment_results)
    return records
