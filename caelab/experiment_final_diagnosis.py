"""Explicit ordinary-residual Jacobian at ONE immutable selected candidate.

Reuses numerical._Evaluators/_Budget/_aligned and identification.diagnose.
No optimizer is run, no failed residual is penalized, and no holdout is evaluated.
Both difference scales and every actual trial output belong to this new attempt.
"""
from __future__ import annotations

from copy import deepcopy
import math
from time import perf_counter

import numpy as np

from .storage import canonical_hash
from .experiment_uncertainty import plain
from . import numerical

RANK_RTOL = 1e-6                 # Existing identification.diagnose threshold.
DIFFERENCE_RTOL = 1e-3           # Additional step-halving consistency gate.
DIFFERENCE_ATOL = 1e-10
REPRODUCE_RTOL = 1e-10
REPRODUCE_ATOL = 1e-12
MAX_PARAMETERS = 64
MAX_RESIDUALS = 32768


def problem_from_evidence(resolved, *, submitted_arguments=None):
    """Called after resolve_candidate_evidence, never instead of that gate."""
    # Permissions depend on the current consumer and are rechecked separately.
    # Only IMMUTABLE snapshot content belongs in a reusable Jacobian binding.
    snapshot = deepcopy(resolved['snapshot'])
    reference = deepcopy(resolved['reference'])
    if canonical_hash(plain(snapshot)) != reference['snapshot_sha256']:
        raise ValueError('선택 후보의 보존 근거가 달라졌습니다.')
    inputs = snapshot['fit_input']['inputs']
    candidate = snapshot['original_candidate']
    variables = numerical._variables(inputs['variables'])
    numerical._candidates([candidate], variables)
    if len(variables) > MAX_PARAMETERS:
        raise ValueError(f'최종점 명시 진단은 자유 계수 {MAX_PARAMETERS}개 이하를 지원합니다.')
    experiments = deepcopy(inputs['experiments'])
    if not any(e['role'] == 'fit' for e in experiments):
        raise ValueError('진단할 원 피팅 시험이 없습니다.')
    # Canonical and legacy carriers are different contracts, not aliases.
    # The service supplies the EXACT saved original run arguments; a freshly
    # compiled Plan or an experiment list relabelled as arguments is not enough.
    fit_input = snapshot['fit_input']
    from .data_processing_consumer import admit_snapshot, retained_assessment, is_canonical_observation
    packet = inputs.get('frozen_inclusion')
    legacy = fit_input.get('inclusion_packet')
    derived = any(e['observations'].get('sample_ids') or is_canonical_observation(e['observations'])
                  for e in experiments)
    if packet is not None:
        if submitted_arguments is None:
            raise ValueError('canonical 최종점 진단에는 보존 원 job의 실제 제출 인자가 필요합니다.')
        digest = canonical_hash(plain(submitted_arguments))
        if (digest != fit_input.get('submitted_arguments_sha256')
                or digest != snapshot['original_record'].get('arguments_sha256')
                or canonical_hash(plain(inputs)) != fit_input.get('inputs_sha256')):
            raise ValueError('보존 원 제출/입력과 immutable 후보 근거가 다릅니다.')
        # These existing consumers validate source/settings/DAG/mask/weights
        # and the original transported header/trial, without freezing a packet.
        accepted, admission = admit_snapshot(inputs, submitted_arguments, legacy_packet=legacy)
        assessment = retained_assessment(experiments)
        if (canonical_hash(plain(accepted)) != canonical_hash(plain(experiments))
                or admission != fit_input.get('data_inclusion')
                or assessment is None or assessment['packet_sha256'] != packet['packet_sha256']):
            raise ValueError('원 canonical packet/보존 header·trial/소비 판정이 다릅니다.')
        lineage = 'CANONICAL_DATA_CONSUMER_CHECKED'
    elif derived or fit_input.get('data_inclusion') is not None:
        raise ValueError('파생 표본의 원 canonical Data packet이 없습니다. legacy packet으로 대체하지 않습니다.')
    else:
        if submitted_arguments is not None:
            admit_snapshot(inputs, submitted_arguments, legacy_packet=legacy)
        if legacy is not None:
            if legacy.get('format') == 'frozen-fit-inclusion.v1':
                raise ValueError('canonical packet을 legacy inclusion_packet 이름으로 사용할 수 없습니다.')
            from .numerical_candidate_detail import consume_frozen_fit_inclusion
            consume_frozen_fit_inclusion(experiments, legacy)
        lineage = 'LEGACY_OR_INLINE_ORIGINAL_RESIDUAL_ONLY; NOT_CANONICAL_DATA'
    fixed = []
    plan = snapshot['original_plan']
    for row in plan.get('variables', []):
        if row.get('free') is False:
            fixed.append(deepcopy(row))
    return plain({'evidence_reference': reference, 'candidate': candidate, 'variables': variables,
        'experiments': experiments, 'selected_trials': snapshot['trials'], 'scope': snapshot['scope'],
        'selected_attempt': snapshot.get('selected_attempt'), 'fixed_parameters': fixed,
        'original_plan': plan, 'fit_input': snapshot['fit_input'],
        'original_fit_status': snapshot['original_fit_status'],
        'original_fit_holdout': snapshot['original_fit_holdout'],
        'original_fit_holdout_sha256': snapshot['original_fit_holdout_sha256'],
        'original_record': snapshot['original_record'],
        'readiness': snapshot['readiness'], 'lineage_status': lineage,
        'optimizer_method': inputs.get('method', 'least_squares'),
        'optimizer_loss': inputs.get('options', {}).get('loss', 'linear')})


def evaluation_plan(problem, relative_step):
    """A nonexecuting cost/stencil preview. Both h and h/2 are explicit."""
    relative_step = numerical._number(relative_step, 'relative_step')
    if not 1e-8 <= relative_step <= 1e-2:
        raise ValueError('차분 간격은 선언 계수 범위의 1e-8…1e-2를 명시하세요.')
    variables = numerical._variables(problem['variables'])
    values = deepcopy(problem['candidate']['values'])
    numerical._candidates([{'candidate_id': 'Cdiagnosis', 'values': values}], variables)
    points = [{'id': 'base', 'values': values}]
    stencils = []
    for variable in variables:
        name = variable['id']
        logarithmic = variable['transform'] == 'log'
        encode = math.log if logarithmic else float
        decode = math.exp if logarithmic else float
        x, low, high = [encode(v) for v in (values[name], variable['lower'], variable['upper'])]
        step = (high-low)*relative_step
        left, right = x-low, high-x
        central = min(left, right) >= step
        direction = 0 if central else 1 if right >= left else -1
        if direction:
            step = min(step, (right if direction > 0 else left)/2.)
        offsets = (-step, step, -step/2., step/2.) if central else (direction*step, direction*2*step, direction*step/2.)
        ids = []
        encoded_actual = []
        for index, offset in enumerate(offsets):
            value = decode(x+offset)
            if not variable['lower'] <= value <= variable['upper'] or value == values[name]:
                raise ValueError('계수 차분점이 범위 밖이거나 float64에서 구별되지 않습니다: '+name)
            pid = name+':'+str(index)
            point = deepcopy(values)
            point[name] = value
            points.append({'id': pid, 'values': point})
            ids.append(pid)
            encoded_actual.append(encode(value)-x)
        # Use actual representable encoded coordinates, not the ideal offset.
        # The weights below are the derivative of the quadratic interpolant.
        groups = ([('base', 0.), (ids[0], encoded_actual[0]), (ids[1], encoded_actual[1])],
                  [('base', 0.), (ids[2], encoded_actual[2]), (ids[3], encoded_actual[3])]) if central else (
                  [('base', 0.), (ids[0], encoded_actual[0]), (ids[1], encoded_actual[1])],
                  [('base', 0.), (ids[2], encoded_actual[2]), (ids[0], encoded_actual[0])])
        if central:
            # Reuse the already budgeted half-step points for a two-sided
            # differentiability check: a symmetric |x-x*| cusp otherwise
            # yields two identical (zero) central differences.
            groups += ([('base', 0.), (ids[0], encoded_actual[0]), (ids[2], encoded_actual[2])],
                       [('base', 0.), (ids[1], encoded_actual[1]), (ids[3], encoded_actual[3])])
        weighted = []
        for group in groups:
            a, b = group[1][1], group[2][1]
            if a == b or a == 0 or b == 0:
                raise ValueError('유효한 서로 다른 차분 좌표가 필요합니다.')
            weighted.append([{'point': group[0][0], 'weight': -(a+b)/(a*b)},
                             {'point': group[1][0], 'weight': b/(a*(b-a))},
                             {'point': group[2][0], 'weight': -a/(b*(b-a))}])
        stencils.append({'parameter': name, 'transform': variable['transform'], 'encoded_step': step,
            'difference': 'central_quadratic' if central else 'one_sided_quadratic',
            'coarse': weighted[0], 'fine': weighted[1],
            'left': weighted[2] if central else None, 'right': weighted[3] if central else None,
            'active_bound': -1 if values[name] == variable['lower'] else 1 if values[name] == variable['upper'] else 0})
    fitted = [e for e in problem['experiments'] if e['role'] == 'fit']
    return {'points': points, 'stencils': stencils, 'relative_step': relative_step,
            'fit_experiment_ids': [e['id'] for e in fitted],
            'model_evaluations': len(points)*len(fitted), 'holdout_evaluations': 0,
            'rank_relative_tolerance': RANK_RTOL,
            'difference_tolerance': {'relative': DIFFERENCE_RTOL, 'absolute': DIFFERENCE_ATOL},
            'base_reproduction_tolerance': {'relative': REPRODUCE_RTOL, 'absolute': REPRODUCE_ATOL}}


def _admission(problem):
    candidate = problem['candidate']
    if candidate.get('execution_status') != 'SUCCEEDED' or candidate.get('prediction_status'):
        return '원 후보가 실제 성공한 계산점이 아닙니다.'
    if problem.get('selected_attempt') is not None and problem['selected_attempt']['state'] != 'SUCCEEDED':
        return '선택한 과거 상세 attempt가 성공하지 않았습니다. 나중 성공으로 대체하지 않습니다.'
    if problem['evidence_reference'].get('purpose') != 'success_judgment':
        return '실패 진단 근거는 성공 후보 진단에 사용할 수 없습니다.'
    scope = {e['experiment_id'] for e in problem['scope']}
    for e in problem['experiments']:
        if e['role'] != 'fit':
            continue
        if e['observations']['kind'] not in ('scalar', 'series'):
            return '이산 사건(event)의 국소 미분은 지원하지 않습니다.'
        if e['id'] not in scope:
            return '모든 원 피팅 시험을 포함한 상세 근거를 선택하세요.'
        matches = [t for t in problem['selected_trials'] if t['experiment_id'] == e['id']]
        if len(matches) != 1 or matches[0].get('retention') != 'RETAINED' or matches[0].get('execution_status') != 'SUCCEEDED':
            return '원 피팅 시험의 실제 상세가 보존되지 않았습니다: '+e['id']
        if not matches[0].get('raw_evaluation') or not matches[0].get('curve'):
            return '요약 또는 곡선만 있고 원 상세 평가가 없습니다: '+e['id']
        try:
            # Numerical owns mask/weight validation AND its single sqrt(weight)
            # application in _aligned. In particular a zero weight on an
            # included row is still invalid; excluded zero weights stay exact.
            numerical._experiment(e)
        except (ValueError, TypeError, KeyError) as error:
            return '원 Numerical 잔차 입력을 사용할 수 없습니다: ' + str(error)
    return None


def _row_binding(experiments):
    rows = []
    for e in experiments:
        normalized = numerical._experiment(e)
        obs = e['observations']
        ids, raw = obs.get('sample_ids'), obs.get('source_rows')
        weights = e.get('sample_weights')
        provenance = {
            'response_channel_id': obs.get('response_channel_id'),
            'observations_sha256': canonical_hash(plain(obs)),
            'observation_source_sha256': canonical_hash(plain(e.get('observation_source'))),
            'settings_sha256': canonical_hash(plain(e.get('settings', {}))),
            'mask_sha256': canonical_hash(normalized['_mask'].tolist()),
            'frozen_fit_packet_sha256': (e.get('frozen_fit_packet') or {}).get('packet_sha256')}
        for index in np.flatnonzero(normalized['_mask']):
            rows.append({'experiment_id': e['id'], 'index': int(index),
                'source_row': raw[index] if raw is not None else None,
                'sample_id': ids[index] if ids is not None else None,
                'response': e['response'], 'unit': obs['unit'], 'weight': e['weight'], 'scale': e['scale'],
                'sample_weight': weights[index] if weights is not None else None,
                'coordinate_sample_id': obs.get('coordinate_sample_ids', [None]*len(normalized['_mask']))[index],
                **provenance})
    if len(rows) > MAX_RESIDUALS:
        raise ValueError('최종점 잔차 행 한도를 넘습니다.')
    return rows


def evaluate_final(evaluator, problem, *, budget_evaluations, relative_step=1e-4, execution=None):
    """An explicit new Numerical job, including failures and cancellation."""
    from .numerical_candidate_detail import trial_detail
    from .execution_control import ExecutionCancelled, ExecutionCleanupFailed, check_cancelled
    from .identification import diagnose
    from .evaluation import file_hash
    import inspect
    started = perf_counter()
    frozen = plain(problem)
    binding_sha = canonical_hash(frozen)
    result = {'kind': 'experiment_identification', 'execution_status': 'REJECTED', 'responses': {}, 'checks': [],
        'identification': {'status': 'UNKNOWN', 'uncertainty': 'UNKNOWN', 'global_uniqueness': 'UNKNOWN',
            'engineering_release': 'NOT_RELEASED'},
        'experiment_analysis': {'source_problem': frozen, 'problem_sha256': binding_sha,
            'attempts': [], 'ordinary_jacobian': None, 'optimization_performed': False,
            'holdout_evaluations': 0, 'engineering_release': 'NOT_RELEASED',
            'original_fit_status': problem['original_fit_status'],
            'original_fit_holdout_sha256': problem['original_fit_holdout_sha256']},
        'timing': {'model_calls': 0, 'budget_used': 0}}
    issue = _admission(problem)
    if issue:
        result.update(failure_reason=issue)
        result['identification']['reason'] = issue
        return result
    plan = evaluation_plan(problem, relative_step)
    result['experiment_analysis']['evaluation_plan'] = plan
    if type(budget_evaluations) is not int or budget_evaluations < plan['model_evaluations']:
        result['failure_reason'] = '명시 예산이 최종점/차분점의 실제 시험 평가 수보다 작습니다.'
        result['identification']['reason'] = result['failure_reason']
        return result
    options = numerical._execution(execution)
    if options['mode'] != 'serial' or options['workers'] != 1:
        raise ValueError('최종점 진단은 기존 직렬 평가를 사용합니다.')
    options['max_evaluations'] = budget_evaluations
    budget = numerical._Budget(budget_evaluations)
    fitted = [e for e in problem['experiments'] if e['role'] == 'fit']
    rows = _row_binding(fitted)
    result['experiment_analysis']['residual_rows'] = rows
    residuals, errors = {}, []
    stopped = False
    def cancelled():
        try:
            check_cancelled()
        except ExecutionCancelled:
            return True
        return bool(options.get('cancelled') and options['cancelled']())
    for point in plan['points']:
        trials, vector = [], []
        for e in fitted:
            if stopped or cancelled():
                stopped = True
                trials.append({'experiment_id': e['id'], 'execution_status': 'CANCELLED', 'retention': 'NOT_EVALUATED'})
                continue
            try:
                with numerical._Evaluators(evaluator, [e.get('settings', {})], options, budget=budget) as models:
                    actual = models.one(deepcopy(point['values']))[0]
                    result['timing']['model_calls'] += models.model_calls
                trial = trial_detail(e, actual, origin={'kind': 'final_diagnosis', 'point_id': point['id']})
                trials.append(trial)
                if trial['execution_status'] == 'CANCELLED':
                    stopped = True
                if trial['execution_status'] != 'SUCCEEDED':
                    errors.append(point['id']+'/'+e['id']+': 실제 평가/응답 실패')
                else:
                    _, residual = numerical._aligned(actual, numerical._experiment(e))
                    vector.extend(residual.tolist())
            except ExecutionCleanupFailed:
                raise   # Do not publish success while owned processes survive.
            except (ExecutionCancelled, numerical.StudyCancelled):
                stopped = True
                trials.append({'experiment_id': e['id'], 'execution_status': 'CANCELLED', 'retention': 'NOT_EVALUATED'})
            except Exception as error:
                errors.append(point['id']+'/'+e['id']+': '+type(error).__name__+': '+str(error))
                trial = trial_detail(e, {'execution_status': 'FAILED', 'responses': {},
                    'diagnostics': {'reason': str(error), 'phase': 'PREPARE_EVALUATE_CLOSE'}},
                    origin={'kind': 'final_diagnosis', 'point_id': point['id']})
                trials.append(trial)
        result['experiment_analysis']['attempts'].append({'point_id': point['id'], 'values': deepcopy(point['values']), 'trials': trials})
        if len(vector) == len(rows) and all(t['execution_status'] == 'SUCCEEDED' for t in trials):
            residuals[point['id']] = np.asarray(vector)
    stopped = stopped or cancelled()
    result['timing'].update(budget_used=budget.used, seconds=perf_counter()-started)
    if stopped or errors or len(residuals) != len(plan['points']):
        reason = '명시 진단이 취소되었습니다.' if stopped else '; '.join(errors) or '차분점의 완전한 잔차가 없습니다.'
        result.update(execution_status='CANCELLED' if stopped else 'FAILED', failure_reason=reason)
        result['identification']['reason'] = reason
        return plain(result)
    # Reproducing a selected retained detail never fills the original attempt.
    original = {t['experiment_id']: t for t in problem['selected_trials']}
    expected = []
    for e in fitted:
        _, r = numerical._aligned(original[e['id']]['raw_evaluation'], numerical._experiment(e))
        expected.extend(r.tolist())
    if not np.allclose(residuals['base'], expected, rtol=REPRODUCE_RTOL, atol=REPRODUCE_ATOL):
        result.update(execution_status='FAILED', failure_reason='최종점 재평가가 선택한 보존 상세 잔차와 다릅니다.')
        result['identification']['reason'] = result['failure_reason']
        return plain(result)
    def derivative(stencil):
        # Difference against base avoids catastrophic cancellation of large
        # constant residuals. The base weight is still retained in the plan.
        return sum((residuals[row['point']]-residuals['base'])*row['weight'] for row in stencil)
    coarse = np.column_stack([derivative(s['coarse']) for s in plan['stencils']])
    fine = np.column_stack([derivative(s['fine']) for s in plan['stencils']])
    discrepancy = np.max(np.abs(fine-coarse), axis=0)
    limits = DIFFERENCE_ATOL + DIFFERENCE_RTOL*np.max(np.abs(fine), axis=0)
    halving_stable = bool(np.isfinite(fine).all() and np.all(discrepancy <= limits))
    directional = []
    for i, stencil in enumerate(plan['stencils']):
        if stencil['left'] is None:
            directional.append({'parameter': stencil['parameter'], 'status': 'ONE_SIDED_BOUND_SCOPE',
                                'two_sided_differentiability': 'UNKNOWN'})
        else:
            left, right = derivative(stencil['left']), derivative(stencil['right'])
            difference = float(np.max(np.abs(left-right)))
            limit = float(DIFFERENCE_ATOL + DIFFERENCE_RTOL*max(np.max(np.abs(left)), np.max(np.abs(right))))
            directional.append({'parameter': stencil['parameter'], 'status': 'CONSISTENT' if difference <= limit else 'INCONSISTENT',
                'left': left.tolist(), 'right': right.tolist(), 'max_difference': difference, 'limit': limit})
    directional_stable = all(row['status'] != 'INCONSISTENT' for row in directional)
    stable = halving_stable and directional_stable
    record = {'kind': 'ordinary_residual_jacobian', 'problem_sha256': binding_sha,
        'parameter_ids': [v['id'] for v in problem['variables']],
        'coordinate_system': 'declared linear or natural-log parameter coordinates',
        'parameter_values': deepcopy(problem['candidate']['values']),
        'residual_rows': rows, 'residual_base': residuals['base'].tolist(),
        'matrix': fine.tolist(), 'coarse_matrix': coarse.tolist(),
        'step_halving': {'stable': halving_stable, 'column_max_difference': discrepancy.tolist(), 'limits': limits.tolist()},
        'directional_consistency': {'stable': directional_stable, 'parameters': directional,
            'interpretation': 'local numerical check, not a proof of differentiability'},
        'evaluation_plan': plan, 'residual_engine_sha256': file_hash(inspect.getsourcefile(numerical._aligned)),
        'robust_modification_applied': False, 'input_optimizer_loss': problem['optimizer_loss']}
    record['sha256'] = canonical_hash(record)
    result['experiment_analysis']['ordinary_jacobian'] = record
    if not stable:
        result.update(execution_status='FAILED', failure_reason='차분 간격 절반 또는 좌우 미분 비교가 일치하지 않습니다. 원 행렬/평가를 보존합니다.')
        result['identification']['reason'] = result['failure_reason']
        return plain(result)
    diagnosis = diagnose(fine, problem['variables'], fitted, problem['candidate']['values'],
        loss='linear', jacobian_method='explicit ordinary residual / quadratic h,h/2 and directional consistency',
        active_mask=[s['active_bound'] for s in plan['stencils']], rtol=RANK_RTOL)
    diagnosis['residual_definition'] = 'existing numerical._aligned; original masks/weights/scales unchanged'
    diagnosis['optimizer_loss'] = problem['optimizer_loss']
    diagnosis['fixed_parameters'] = deepcopy(problem['fixed_parameters'])
    diagnosis['fixed_parameter_scope'] = 'not differentiated; exact values remain in original Plan/per-trial settings'
    diagnosis['jacobian_evidence_sha256'] = record['sha256']
    result['identification'] = diagnosis
    result['execution_status'] = 'SUCCEEDED' if diagnosis['status'] != 'UNKNOWN' else 'FAILED'
    return plain(result)


def read_jacobian(result, problem):
    """Verify a retained ordinary J; NEVER prepare/call an evaluator."""
    data = result.get('experiment_analysis', {})
    record = deepcopy(data.get('ordinary_jacobian'))
    if result.get('kind') != 'experiment_identification' or result.get('execution_status') != 'SUCCEEDED' or not isinstance(record, dict):
        raise ValueError('성공한 명시 최종점 진단에 보존된 일반 잔차 Jacobian이 없습니다.')
    digest = record.pop('sha256', None)
    if canonical_hash(record) != digest or record.get('problem_sha256') != canonical_hash(plain(problem)):
        raise ValueError('보존 Jacobian의 최종점/원행/단위/상세 근거가 다릅니다.')
    if record.get('kind') != 'ordinary_residual_jacobian' or record.get('robust_modification_applied') is not False or record.get('step_halving', {}).get('stable') is not True or record.get('directional_consistency', {}).get('stable') is not True:
        raise ValueError('robust 수정 또는 미검증 Jacobian은 일반 잔차 진단이 아닙니다.')
    if (data.get('problem_sha256') != record['problem_sha256'] or canonical_hash(data.get('source_problem')) != record['problem_sha256']
            or record['parameter_values'] != problem['candidate']['values'] or record['parameter_ids'] != [v['id'] for v in problem['variables']]):
        raise ValueError('보존 Jacobian과 원 입력의 결합이 다릅니다.')
    matrix = np.asarray(record['matrix'], dtype=float)
    fitted = [e for e in problem['experiments'] if e['role'] == 'fit']
    expected_rows = _row_binding(fitted)
    if record['residual_rows'] != expected_rows:
        # Pre-C1 ordinary records could only use unweighted, noncanonical
        # observations. Preserve their exact old row format and already checked
        # whole-problem hash; never reinterpret a weighted/canonical record as
        # legacy, add missing fields, or invoke an evaluator while reading.
        added = {'response_channel_id', 'observations_sha256', 'observation_source_sha256',
                 'settings_sha256', 'mask_sha256', 'frozen_fit_packet_sha256'}
        legacy_rows = [{key: value for key, value in row.items() if key not in added}
                       for row in expected_rows]
        if (any(e.get('sample_weights') is not None or e.get('frozen_fit_packet') for e in fitted)
                or record['residual_rows'] != legacy_rows):
            raise ValueError('보존 Jacobian의 원행/가중치/계보가 다릅니다.')
    if matrix.shape != (len(record['residual_rows']), len(problem['variables'])) or not np.isfinite(matrix).all():
        raise ValueError('보존 Jacobian의 행/열/값이 다릅니다.')
    return {**record, 'sha256': digest}
