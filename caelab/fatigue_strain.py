"""Strain-life domain extension of the existing damage.rainflow Simulation.

CMB/NONE, uniaxial SWT and normal-strain-range-selected CP-SWT. No new owner,
queue, solver, interpolation or material estimate. All planes and cycle-to-row
associations are retained through the existing evaluation artifact reader.
"""
from __future__ import annotations

from copy import deepcopy
import math
import numpy as np

from .execution_control import check_cancelled, ExecutionCancelled
from .fatigue_life import (ROOT_DEFAULTS, calibration_draft, normalize_calibration,
                           number, validate_root, solve_life)
from .fatigue_tensor import (COMPONENTS, validate_source, read_bundle, admit_bundle,
                             orthogonal_basis, plane_grid, project)
from .fatigue_cycles import ASSOCIATION_VERSION, associate_cycles
from .storage import canonical_hash, check_id

VERSION = 'caelab.strain-fatigue.v1'
MODEL_NAMES = {'CP_SWT': 'CP-SWT maximum normal-strain range / sampled loops v1',
               'SWT': 'Uniaxial SWT / sampled loops v1',
               'NONE': 'Uniaxial total-strain CMB / no mean correction v1'}
MAX_PLANE_SAMPLES = 1_000_000
TIE_RTOL, TIE_ATOL = 1e-10, 1e-14
PAIR_RTOL, PAIR_STRAIN_ATOL, PAIR_STRESS_ATOL = 1e-12, 1e-15, 0.0


def default_settings(method='CP_SWT', mean_stress='SWT'):
    return {'method': method, 'mean_stress': mean_stress, 'source': None,
            'calibration': calibration_draft(), 'temperature_k': None, 'repeat_block': False,
            'root': deepcopy(ROOT_DEFAULTS),
            'interpretation': {'strain_shear': 'UNKNOWN', 'history_state': 'UNKNOWN',
                               'constitutive_source': '', 'sampling': ASSOCIATION_VERSION},
            'search': {'polar_steps': 6, 'refinement_levels': 1,
                       'basis': [[1., 0., 0.], [0., 1., 0.], [0., 0., 1.]],
                       'range_relative_tolerance': .01},
            'repeat_tolerance': {'strain_absolute': 0., 'stress_mpa_absolute': 0.},
            'selection': None}


def validate_selection(selection):
    if selection is None:
        return
    keys = {'job_id', 'result_sha256', 'plane_id', 'cycle', 'source_row'}
    if not isinstance(selection, dict) or set(selection) != keys:
        raise ValueError('저장 결과의 면/사이클/원행 선택이 손상되었습니다')
    check_id(selection['job_id'])
    h = selection['result_sha256']
    if not isinstance(h, str) or len(h) != 64 or any(c not in '0123456789abcdef' for c in h):
        raise ValueError('선택한 저장 결과의 identity가 손상되었습니다')
    for key in ('plane_id', 'cycle', 'source_row'):
        v = selection[key]
        if v is not None and (type(v) is not int or v < (0 if key == 'source_row' else 1)):
            raise ValueError('선택한 면/사이클/원행 번호가 손상되었습니다')


def validate_settings(settings):
    if not isinstance(settings, dict) or set(settings) != set(default_settings()):
        raise ValueError('ε–N/SWT 설정은 전용 편집기로 입력하세요. private resolved payload는 금지됩니다')
    method, mean = settings['method'], settings['mean_stress']
    if method not in ('STRAIN_LIFE', 'CP_SWT') or mean not in ('NONE', 'SWT'):
        raise ValueError('CMB/NONE, 단축 SWT 또는 normal-strain CP-SWT를 선택하세요')
    if method == 'CP_SWT' and mean != 'SWT':
        raise ValueError('CP-SWT에는 명시 SWT가 필요합니다. 숨은 모델 전환은 없습니다')
    validate_source(settings['source'], method=method, mean_stress=mean)
    normalize_calibration(settings['calibration'], swt=mean == 'SWT')
    number(settings['temperature_k'], '평가 온도 [K]', positive=True)
    validate_root(settings['root'])
    interpretation = settings['interpretation']
    if not isinstance(interpretation, dict) or set(interpretation) != set(default_settings()['interpretation']):
        raise ValueError('strain shear/이력 상태/구성식 출처/표본 정책이 필요합니다')
    if interpretation['strain_shear'] not in ('TENSOR', 'ENGINEERING'):
        # Scalar has no shear input, but an explicit unused convention avoids
        # treating an UNKNOWN convention as tensor if the user later changes method.
        if method == 'CP_SWT':
            raise ValueError('engineering γ 또는 tensor εij를 명시하세요')
    if interpretation['history_state'] not in ('STABILIZED_CYCLIC', 'NONSTABILIZED', 'UNKNOWN'):
        raise ValueError('안정 cyclic/비안정/미확인 이력 상태를 선택하세요')
    if not isinstance(interpretation['constitutive_source'], str) or not interpretation['constitutive_source'].strip():
        raise ValueError('실제 공급된 total strain/stress의 시험 또는 구성식 출처를 적으세요')
    if interpretation['sampling'] != ASSOCIATION_VERSION:
        raise ValueError('지원되는 원 표본 cycle association 정책을 명시하세요')
    search = settings['search']
    if not isinstance(search, dict) or set(search) != set(default_settings()['search']):
        raise ValueError('면 검색 해상도와 고정 검색기저가 필요합니다')
    if type(search['polar_steps']) is not int or not 2 <= search['polar_steps'] <= 24:
        raise ValueError('극각 분할수는 2..24 정수여야 합니다')
    if type(search['refinement_levels']) is not int or not 0 <= search['refinement_levels'] <= 2:
        raise ValueError('추가 면 세분화는 0..2 단계여야 합니다')
    if search['polar_steps'] * 2**search['refinement_levels'] > 48:
        raise ValueError('최종 면 분할수가 48을 넘습니다')
    orthogonal_basis(search['basis'])
    v = number(search['range_relative_tolerance'], '격자 최대 range 상대변화 허용치', positive=True)
    if not 1e-8 <= v <= .1:
        raise ValueError('격자 range 비교 허용치는 1e-8..0.1이어야 합니다')
    if type(settings['repeat_block']) is not bool:
        raise ValueError('반복 블록 가정은 명시적으로 선택하세요')
    tolerances = settings['repeat_tolerance']
    if not isinstance(tolerances, dict) or set(tolerances) != set(default_settings()['repeat_tolerance']):
        raise ValueError('동시 tensor 반복 경계의 명시 절대 허용치가 필요합니다')
    for key, value in tolerances.items():
        if number(value, key) < 0:
            raise ValueError('반복 경계 허용치는 음수일 수 없습니다')
    validate_selection(settings['selection'])
    return deepcopy(settings)


def resolved_adapter(workbench, settings):
    from .fatigue import FatigueAdapter
    s = validate_settings(settings)
    bundle = read_bundle(workbench, s['source'], method=s['method'], mean_stress=s['mean_stress'])
    admit_bundle(bundle, s)
    return FatigueAdapter(bundle, s['source'])


def _repeat_assessment(s, admitted, values, cycles, total):
    answer = {'status': 'UNKNOWN', 'blocks_to_D1': None, 'seconds_to_D1': None,
              'reason': 'FINITE_HISTORY_ONLY_NO_REPEATING_BLOCK_ASSUMPTION',
              'residual_pairs': [], 'boundary_tolerance': deepcopy(s['repeat_tolerance']),
              'residual_match_tolerance': {'relative': PAIR_RTOL, 'strain_absolute': PAIR_STRAIN_ATOL,
                                           'stress_mpa_absolute': PAIR_STRESS_ATOL}}
    if not s['repeat_block']:
        return answer
    strain, stress = admitted['strain'], admitted['stress']
    limits = s['repeat_tolerance']
    de = np.abs(strain[-1] - strain[0])
    ds = np.abs(stress[-1] - stress[0]) if stress is not None else None
    answer['tensor_boundary_difference'] = {'strain': de.tolist(), 'stress_mpa': ds.tolist() if ds is not None else None}
    if np.any(de > limits['strain_absolute']) or (ds is not None and np.any(ds > limits['stress_mpa_absolute'])):
        answer['reason'] = 'SIMULTANEOUS_TENSOR_BLOCK_BOUNDARY_MISMATCH'
        return answer
    if s['interpretation']['history_state'] != 'STABILIZED_CYCLIC':
        answer['reason'] = 'CYCLIC_STATE_NOT_CONFIRMED_STABILIZED'
        return answer
    # Conservative repeating-block policy: do not rotate an arbitrary-phase
    # record or synthesize cycles across its boundary without observed evidence.
    if values[0] not in (min(values), max(values)) or abs(values[-1]-values[0]) > limits['strain_absolute']:
        answer['reason'] = 'PROJECTED_BLOCK_NOT_CLOSED_AT_GLOBAL_STRAIN_EXTREMUM'
        return answer
    pending = [r for r in cycles if r['count'] == .5]
    while pending:
        a = pending.pop(0)
        candidates = [b for b in pending if
                      math.isclose(a['range'], b['range'], rel_tol=PAIR_RTOL, abs_tol=PAIR_STRAIN_ATOL) and
                      math.isclose(a['mean'], b['mean'], rel_tol=PAIR_RTOL, abs_tol=PAIR_STRAIN_ATOL) and
                      (values[a['end_row']] - values[a['start_row']]) *
                      (values[b['end_row']] - values[b['start_row']]) < 0]
        if not candidates:
            answer['reason'] = 'UNPAIRED_RESIDUAL_HALF_CYCLE'
            return answer
        if s['mean_stress'] == 'SWT':
            matched = [b for b in candidates if math.isclose(a['sigma_max_mpa'], b['sigma_max_mpa'], rel_tol=PAIR_RTOL, abs_tol=PAIR_STRESS_ATOL)]
            if not matched:
                answer.update(reason='RESIDUAL_SWT_MAX_MISMATCH', mismatched_half_cycles=[a['cycle'], candidates[0]['cycle']],
                              mismatched_sigma_max_mpa=[a['sigma_max_mpa'], candidates[0]['sigma_max_mpa']])
                return answer
            b = matched[0]
        else:
            b = candidates[0]
        pending.remove(b)
        answer['residual_pairs'].append({'cycles': [a['cycle'], b['cycle']],
            'sigma_max_mpa': [a['sigma_max_mpa'], b['sigma_max_mpa']],
            'members': [a['member_source_rows'], b['member_source_rows']]})
    if total is None or total <= 0:
        answer['reason'] = 'UNKNOWN_OR_NONPOSITIVE_BLOCK_DAMAGE'
        return answer
    blocks = 1 / total
    seconds = blocks * (admitted['times'][-1] - admitted['times'][0])
    if not math.isfinite(blocks) or not math.isfinite(seconds):
        answer['reason'] = 'NONFINITE_REPEATING_LIFE'
        return answer
    answer.update(status='ASSUMPTION_DEPENDENT', blocks_to_D1=blocks, seconds_to_D1=seconds,
                  reason='EXPLICIT_IDENTICAL_STABILIZED_BLOCK_LINEAR_MINER_D1')
    return answer


def _plane(s, admitted, normal, index):
    values = (project(admitted['strain'], normal['normal_model']).tolist()
              if s['method'] == 'CP_SWT' else admitted['strain'][:, 0].tolist())
    stress = ((project(admitted['stress'], normal['normal_model']).tolist()
              if s['method'] == 'CP_SWT' else admitted['stress'][:, 0].tolist())
              if admitted['stress'] is not None else None)
    times, source_rows = admitted['times'], admitted['source_rows']
    records = associate_cycles(values)
    partial, unknown = 0.0, 0
    increments = []
    for i, row in enumerate(records):
        check_cancelled()
        members = row['member_indices']
        maximum = max(stress[j] for j in members) if stress is not None else None
        maxima = [j for j in members if stress[j] == maximum] if stress is not None else []
        amplitude = row['range'] / 2
        life = solve_life(amplitude, maximum, s['calibration'], mean_stress=s['mean_stress'],
                          temperature_k=s['temperature_k'], root=s['root'])
        increment = row['count'] / life['Nf_cycles'] if life['status'] == 'CALCULATED' else None
        if increment is None:
            unknown += 1
        else:
            increments.append(increment)
            partial = math.fsum(increments)
        bracket = row['closure_bracket_indices']
        row.update(cycle=i+1, amplitude=amplitude, sigma_max_mpa=maximum,
                   swt_parameter_mpa=maximum*amplitude if maximum is not None else None,
                   sigma_max_indices=maxima, sigma_max_source_rows=[source_rows[j] for j in maxima],
                   member_source_rows=[source_rows[j] for j in members], member_times_s=[times[j] for j in members],
                   start_source_row=source_rows[row['start_row']], end_source_row=source_rows[row['end_row']],
                   start_s=times[row['start_row']], end_s=times[row['end_row']],
                   closure_time_bracket_s=[times[j] for j in bracket] if bracket else None,
                   closure_source_row=source_rows[row['closure_index']] if row['closure_index'] is not None else None,
                   status=life['status'], reason=life['reason'], root=life,
                   calibrated_cycles=life['Nf_cycles'], damage=increment, admitted_partial_damage=partial)
    total = partial if records and unknown == 0 else None
    parameters = [r['swt_parameter_mpa'] for r in records if r['swt_parameter_mpa'] is not None]
    return {'plane_id': index, **deepcopy(normal), 'location': deepcopy(admitted['location']),
            'normal_strain_range': max(values)-min(values),
            'max_cycle_swt_mpa': max(parameters) if parameters else None,
            'history': {'time_s': times, 'source_rows': source_rows, 'sample_ids': admitted['sample_ids'],
                        'row_kind': admitted['row_kind'], 'strain': values, 'stress_mpa': stress},
            'cycles': records, 'unknown_cycle_count': unknown, 'admitted_partial_damage': partial,
            'miner_damage': total, 'status': 'CALCULATED' if total is not None else 'UNKNOWN',
            'repeating_block': _repeat_assessment(s, admitted, values, records, total)}


def _ties(planes, key):
    usable = [p for p in planes if p[key] is not None]
    if not usable:
        return []
    maximum = max(p[key] for p in usable)
    return [p for p in usable if math.isclose(p[key], maximum, rel_tol=TIE_RTOL, abs_tol=TIE_ATOL)]


def analyze(settings, bundle):
    s = validate_settings(settings)
    admitted = admit_bundle(bundle, s)
    planes, levels, cancelled = [], [], False
    failure = None
    grid, full_grid = [], False
    try:
        check_cancelled()
        if s['method'] == 'CP_SWT':
            for level in range(s['search']['refinement_levels'] + 1):
                steps = s['search']['polar_steps'] * 2**level
                grid = plane_grid(steps, s['search']['basis'])
                if len(grid) * len(admitted['times']) > MAX_PLANE_SAMPLES:
                    raise ValueError('면×표본 한도를 넘었습니다. 더 작은 명시 검색 또는 독립 구간을 선택하세요')
                ranges = []
                for normal in grid:
                    check_cancelled()
                    projected = project(admitted['strain'], normal['normal_model'])
                    ranges.append(float(np.ptp(projected)))
                maximum = max(ranges)
                levels.append({'polar_steps': steps, 'plane_count': len(grid),
                               'angular_step_deg': 90/steps, 'max_normal_strain_range': maximum})
        else:
            component = admitted['components'][0]
            vector = [1.0 if component == c else 0.0 for c in COMPONENTS[:3]]
            grid = [{'normal_search': None, 'normal_model': vector, 'theta_deg': None, 'phi_deg': None}]
        full_grid = True
        for index, normal in enumerate(grid, 1):
            check_cancelled()
            planes.append(_plane(s, admitted, normal, index))
    except ExecutionCancelled:
        cancelled = True
    except (ValueError, OverflowError, FloatingPointError) as error:
        failure = {'error_type': type(error).__name__, 'message': str(error),
                   'completed_planes': len(planes), 'next_plane': len(planes)+1 if full_grid else None}
    complete = full_grid and len(planes) == len(grid) and not cancelled and failure is None
    critical = _ties(planes, 'normal_strain_range') if complete else []
    # Damage only breaks ties INSIDE the strain-range argmax set. It never
    # promotes a lower-strain plane to a critical plane.
    representative = max(critical, key=lambda p: (p['admitted_partial_damage'], -p['plane_id'])) if critical else (planes[0] if planes else None)
    total = (max(p['miner_damage'] for p in critical)
             if critical and all(p['miner_damage'] is not None for p in critical) else None)
    blocks = (min(p['repeating_block']['blocks_to_D1'] for p in critical)
              if total is not None and all(p['repeating_block']['blocks_to_D1'] is not None for p in critical) else None)
    seconds = blocks * (admitted['times'][-1]-admitted['times'][0]) if blocks is not None else None
    convergence = {'status': 'NOT_ESTABLISHED_SINGLE_GRID', 'levels': levels,
                   'not_global_convergence_proof': True, 'relative_max_range_change': None}
    if len(levels) > 1:
        previous, latest = levels[-2]['max_normal_strain_range'], levels[-1]['max_normal_strain_range']
        delta = abs(latest-previous) / latest if latest > 0 else None
        convergence.update(relative_max_range_change=delta,
            status='WITHIN_DECLARED_RANGE_CHANGE' if delta is not None and delta <= s['search']['range_relative_tolerance'] else 'REFINEMENT_NOT_CONVERGED')
    model = MODEL_NAMES['CP_SWT' if s['method'] == 'CP_SWT' else s['mean_stress']]
    life_reason = ('EXPLICIT_REPEATING_BLOCK_ASSUMPTIONS' if blocks is not None else
                   '; '.join(dict.fromkeys(p['repeating_block']['reason'] for p in critical)) if critical else
                   'INCOMPLETE_PLANE_SEARCH_NO_GLOBAL_ASSESSMENT')
    responses = {}
    if representative:
        history = representative['history']
        common = {'kind': 'series', 'axes': [{'name': 'time', 'unit': 's', 'values': history['time_s']}],
                  'location': deepcopy(admitted['location']), 'frame': admitted['frame'],
                  'source_rows': history['source_rows'], 'reduction': 'none',
                  'metadata': {'plane_id': representative['plane_id'], 'normal_model': representative['normal_model']}}
        responses['projected_total_strain_history'] = {**deepcopy(common), 'unit': '1', 'value': history['strain'],
            'component': 'normal_on_selected_plane', 'measure': 'infinitesimal_total_strain',
            'label': '표시 면의 total 정상변형률'}
        if history['stress_mpa'] is not None:
            responses['projected_normal_stress_history'] = {**deepcopy(common), 'unit': 'MPa', 'value': history['stress_mpa'],
                'component': 'normal_on_selected_plane', 'measure': 'infinitesimal_Cauchy', 'label': '표시 면의 정상응력'}
        responses['admitted_partial_damage'] = {'kind': 'scalar', 'unit': '1', 'value': representative['admitted_partial_damage'],
            'metadata': {'label': '표시 면의 교정 범위 내 부분 누적값', 'not_global_if_incomplete': not complete}}
        if representative['cycles']:
            responses['admitted_damage_history'] = {'kind': 'series', 'unit': '1',
                'value': [r['admitted_partial_damage'] for r in representative['cycles']],
                'axes': [{'name': 'cycle_count_record', 'unit': '1', 'values': list(range(1,len(representative['cycles'])+1))}],
                'metadata': {'label': '표시 면의 부분 누적값', 'not_physical_time': True}}
    if total is not None:
        responses['miner_damage'] = {'kind': 'scalar', 'unit': '1', 'value': total,
                                     'metadata': {'label': '선정 critical 면의 유한 이력 Miner 누적값'}}
    if blocks is not None:
        responses['repeating_blocks_to_D1'] = {'kind': 'scalar', 'unit': 'blocks', 'value': blocks}
        responses['repeating_seconds_to_D1'] = {'kind': 'scalar', 'unit': 's', 'value': seconds,
            'metadata': {'label': '명시 반복 가정의 D=1 시간, 실측 수명 아님'}}
    diagnosis = {'assessment': 'CALCULATED' if total is not None else 'PARTIAL' if planes else 'UNKNOWN',
        'life_status': 'ASSUMPTION_DEPENDENT' if blocks is not None else 'UNKNOWN', 'life_reason': life_reason,
        'model_name': model, 'equation_version': 'CMB-total-1970-SWT-normal-v1',
        'plane_selection': 'MAXIMUM_NORMAL_STRAIN_RANGE' if s['method']=='CP_SWT' else 'EXPLICIT_UNIAXIAL_COMPONENT',
        'tie_policy': 'MAX_DAMAGE_ONLY_WITHIN_EQUAL_MAX_STRAIN_RANGE; UNKNOWN_TIE_PREVENTS_TOTAL',
        'tie_relative_tolerance': TIE_RTOL, 'tie_absolute_tolerance': TIE_ATOL,
        'counter': 'vendored rainflow 3.2.0, unchanged', 'cycle_association': ASSOCIATION_VERSION,
        'mean_stress_correction': s['mean_stress'], 'decision': 'NOT_RELEASED',
        'calibration': deepcopy(s['calibration']), 'calibration_internal_units': normalize_calibration(s['calibration'], swt=s['mean_stress']=='SWT'),
        'assumed_temperature_k': s['temperature_k'], 'source': deepcopy(s['source']),
        'source_bundle_sha256': canonical_hash(bundle), 'search': deepcopy(s['search']), 'search_convergence': convergence,
        'history_state': s['interpretation']['history_state'], 'constitutive_source': s['interpretation']['constitutive_source'],
        'sensor_world_alignment': admitted['external_alignment'], 'complete_plane_search': complete,
        'plane_search_failure': failure,
        'model_limitations': [
            'Normal/tensile damage model; axial calibration is not shear-driven material qualification.',
            'SWT uses original sampled rows on contracted loops; intersample peaks are not reconstructed.',
            'Half cycles use observed half-branch maxima, not an invented complete hysteresis loop.',
            'Nonproportional path is projected in one fixed basis; this is not an additional-hardening constitutive model.',
            'Finite-history Miner damage and identical stabilized repeating-block life are different assumptions.',
            'No elastic stress/E replacement for plastic total strain, no cyclic/cohesive coupling, no FS model.',
            'Grid range-change check is not proof of the continuous global optimum; engineering qualification UNKNOWN.']}
    return {'execution_status': 'CANCELLED' if cancelled else 'FAILED' if failure is not None else 'SUCCEEDED', 'responses': responses, 'checks': [],
            'fatigue_format': VERSION, 'model_name': model, 'source_bundle': deepcopy(bundle),
            'tensor_admission': {k: deepcopy(v) for k, v in admitted.items() if k not in ('strain','stress')},
            'planes': planes, 'critical_plane_ids': [p['plane_id'] for p in critical],
            'display_plane_id': representative['plane_id'] if representative else None,
            'diagnostic_max_swt_plane_ids': [p['plane_id'] for p in _ties(planes,'max_cycle_swt_mpa')] if complete else [],
            'diagnostic_max_damage_plane_ids': [p['plane_id'] for p in _ties(planes,'miner_damage')] if complete else [],
            'diagnostic_damage_search_complete': complete and all(p['miner_damage'] is not None for p in planes),
            'cycles': deepcopy(representative['cycles']) if representative else [], 'diagnostics': diagnosis}


def select_result(result, *, job_id, plane_id, cycle=None, source_row=None):
    """Pure retained selection: never evaluate or change original result bytes."""
    if result.get('fatigue_format') != VERSION:
        raise ValueError('저장된 strain-life 결과를 선택하세요')
    plane = next((p for p in result.get('planes', []) if p['plane_id'] == plane_id), None)
    if plane is None:
        raise ValueError('저장 결과에 해당 면이 없습니다')
    selected_cycle = next((r for r in plane['cycles'] if r['cycle'] == cycle), None) if cycle is not None else None
    if cycle is not None and selected_cycle is None:
        raise ValueError('선택 면에 해당 cycle이 없습니다')
    rows = selected_cycle['member_source_rows'] if selected_cycle is not None else plane['history']['source_rows']
    if source_row is not None and source_row not in rows:
        raise ValueError('해당 원행은 선택 cycle의 membership에 없습니다')
    value = {'job_id': job_id, 'result_sha256': canonical_hash(result),
             'plane_id': plane_id, 'cycle': cycle, 'source_row': source_row}
    validate_selection(value)
    return value
