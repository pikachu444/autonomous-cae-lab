"""Explicit derived predictions from each candidate's actual accepted state.

The native response, tangent, failure status and accepted prefix are immutable.
No prescribed gradient or observation Jacobian is accepted as a substitute.
"""
from __future__ import annotations
from copy import deepcopy
import math
import numpy as np
from .storage import canonical_hash
from .data_processing_lineage import plain
from .finite_measure import (AXES, FRAME, number, coaxial_gradient, full_tensor_cauchy)

SCHEMA = 'caelab.finite-comparison/1'
PREDICTION_SCHEMA = 'caelab.finite-prediction/1'


def comparison_extension(axis):
    if axis not in AXES:
        raise ValueError('비교할 축 방향을 선택하세요.')
    return {'schema': SCHEMA, 'payload': {'operation': 'PK1_to_finite_Cauchy',
        'scope': 'uniaxial_coaxial', 'axis': axis, 'frame': FRAME,
        'kinematics': 'actual_accepted_candidate_state'}}


def request(experiment):
    ext = experiment.get('extensions', {}).get('finite_measure')
    if ext is None:
        return None
    if not isinstance(ext, dict) or set(ext) != {'schema', 'payload'} or ext.get('schema') != SCHEMA:
        raise ValueError('명시한 유한응력 비교 정의가 필요합니다.')
    spec = ext['payload']
    if not isinstance(spec, dict) or spec != comparison_extension(spec.get('axis'))['payload']:
        raise ValueError('예측 변환은 각 후보의 실제 수락 F/J만 사용합니다. 관측 J/지정 F를 전달할 수 없습니다.')
    obs = experiment.get('observations')
    if obs is not None and (obs.get('measure') != 'finite_Cauchy' or obs.get('component') != spec['axis']*2
            or obs.get('frame') != FRAME or obs.get('kind') != 'series'):
        raise ValueError('finite_Cauchy 관측의 방향·frame·series 선언과 비교 정의가 다릅니다.')
    if experiment.get('response') != 'stress_' + spec['axis']*2:
        raise ValueError('축방향 비교와 원 native 응력 성분이 다릅니다.')
    return spec


def observation_measure(obs, experiment, native_measure):
    """Small admission hook; the rest of Numerical's strict gates stay intact."""
    spec = request({**experiment, 'observations': obs})
    if spec is None:
        return native_measure
    if native_measure != 'first_Piola':
        raise ValueError('이 명시 변환은 finite PK1 법칙에만 적용합니다. 미소변형 Cauchy를 바꾸지 않습니다.')
    return 'finite_Cauchy'


def _same(a, b, label):
    if not math.isclose(number(a, label), number(b, label), rel_tol=1e-12, abs_tol=1e-12):
        raise ValueError(label + ': 실제 수락 증분과 원응답이 다릅니다.')


def derive(evaluation, response_name, spec, *, allow_failed_prefix=False):
    """Return a detached derived response; optionally inspect (never score) a prefix."""
    raw = evaluation.get('responses', {}).get(response_name)
    if not isinstance(raw, dict):
        raise ValueError('원 native 응답이 없습니다.')
    request({'response': response_name, 'extensions': {'finite_measure': {'schema': SCHEMA, 'payload': spec}}})
    if evaluation.get('execution_status') != 'SUCCEEDED' and not allow_failed_prefix:
        raise ValueError('실패 결과의 수락 prefix를 성공 관측으로 채점하지 않습니다.')
    if (raw.get('kind') != 'series' or raw.get('measure') != 'first_Piola'
            or raw.get('component') != spec['axis']*2 or raw.get('frame') != FRAME
            or raw.get('location') != 'material_point' or raw.get('reduction') != 'none'
            or raw.get('coordinate_system', 'UNSPECIFIED') != 'UNSPECIFIED'
            or 'coordinate_frame' in raw):
        raise ValueError('원 native PK1 응답의 측도·방향·좌표계가 다릅니다.')
    axes = raw.get('axes', [])
    if len(axes) != 1 or axes[0].get('name') != 'time':
        raise ValueError('수락 증분과 대응하는 실제 시간축이 필요합니다.')
    times = list(axes[0].get('values', [])); values = list(raw.get('value', []))
    records = evaluation.get('diagnostics', {}).get('constitutive_increments')
    if not isinstance(records, list) or len(records) != len(times) or len(values) != len(times) or not records:
        raise ValueError('실제 수락 증분 F/P/시간이 누락되었습니다. prescribed F 또는 관측 J로 대체하지 않습니다.')
    diagnostics=evaluation.get('diagnostics',{})
    if ('accepted_count' in diagnostics and diagnostics['accepted_count']!=len(records)) or (
            evaluation.get('execution_status')=='SUCCEEDED' and 'requested_count' in diagnostics
            and diagnostics['requested_count']!=len(records)):
        raise ValueError('원 요청/수락 증분 수와 실제 prefix 길이가 다릅니다.')
    if any(b <= a for a, b in zip(times, times[1:])):
        raise ValueError('실제 수락 시간이 acquisition 순서로 증가하지 않습니다.')
    i = AXES[spec['axis']]; derived, states = [], []
    for index, (time, value, row) in enumerate(zip(times, values, records)):
        if row.get('increment') != index or row.get('time') != time or row.get('time_unit') != axes[0].get('unit'):
            raise ValueError('수락 원행/증분/time identity 불일치입니다.')
        if (row.get('stress_measure') != 'first_Piola' or row.get('stress_unit') != raw['unit']
                or row.get('frame') != FRAME or row.get('gradient_unit', '1') != '1'):
            raise ValueError('수락 증분의 실제 측도·단위·frame이 다릅니다.')
        if row.get('status', 'SUCCEEDED') != 'SUCCEEDED' or ('committed_state' in row and row['committed_state'] is None):
            raise ValueError('미수락/미commit trial F를 사용할 수 없습니다.')
        boundary = row.get('boundary') if row.get('boundary') is not None else row if 'residual' in row else None
        if (diagnostics.get('controller') or diagnostics.get('boundary_control')) and boundary is None:
            raise ValueError('제어 결과의 원 residual/tolerance 근거가 누락되었습니다.')
        if boundary is not None:
            residual = number(boundary.get('residual'), '수락 residual')
            tolerance = number(boundary.get('tolerance'), '원 controller tolerance', positive=True)
            if residual < 0 or residual > tolerance:
                raise ValueError('원 controller 수렴 관문을 통과하지 못한 증분입니다.')
        F = row.get('F', row.get('deformation_gradient'))
        if 'F' in row and 'deformation_gradient' in row and row['F'] != row['deformation_gradient']:
            raise ValueError('중복 실제 F 근거가 서로 다릅니다.')
        F, J = coaxial_gradient(F)
        P = row.get('stress_tensor', row.get('stress'))
        sigma, determinant = full_tensor_cauchy(P, F.tolist(), stress_frame=FRAME, gradient_frame=FRAME)
        P = np.asarray(P, dtype=float)
        _same(float(P[i, i]), float(value), '원 PK1 성분')
        local = row.get('local') or {}
        if 'J' in local: _same(J, local['J'], '실제 J')
        if 'cauchy' in local:
            actual = np.asarray(local['cauchy'])
            if actual.shape != (3, 3) or not np.allclose(sigma, actual, rtol=1e-12, atol=1e-12):
                raise ValueError('기존 native Cauchy 진단과 실제 tensor 변환이 다릅니다.')
        derived.append(float(sigma[i, i]))
        states.append({'increment': index, 'time': float(time), 'F': F.tolist(), 'J': determinant,
            'native_P': P.tolist(), 'accepted_increment_sha256': canonical_hash(plain(row))})
    result = deepcopy(raw)
    result.update(value=derived, measure='finite_Cauchy')
    result.setdefault('extensions', {})['finite_measure'] = {'schema': PREDICTION_SCHEMA, 'payload': {
        'request': deepcopy(spec), 'raw_evaluation_sha256': canonical_hash(plain(evaluation)),
        'native_response_sha256': canonical_hash(plain(raw)), 'native_response': response_name,
        'actual_accepted_states': states, 'formula': 'sigma=P@F.T/det(F)',
        'failure_prefix_only': evaluation.get('execution_status') != 'SUCCEEDED',
        'original_execution_status': evaluation.get('execution_status'),
        'failed_increment': deepcopy(evaluation.get('diagnostics', {}).get('failed_increment'))}}
    return result


def selected_prediction(evaluation, experiment):
    spec = request(experiment)
    if spec is None:
        return evaluation.get('responses', {}).get(experiment['response'])
    try:
        return derive(evaluation, experiment['response'], spec)
    except (ValueError, TypeError, KeyError, OverflowError) as error:
        from .numerical import EvaluationFailed
        raise EvaluationFailed('FINITE_PREDICTION_TRANSFORM: ' + str(error)) from error


def row_metadata(curve, time, time_unit):
    """Actual state at an exact response time; never label interpolated F as accepted."""
    packet=curve.get('prediction_metadata',{}).get('extensions',{}).get('finite_measure')
    if not packet or packet.get('schema')!=PREDICTION_SCHEMA:return {}
    payload=packet['payload'];states=payload.get('actual_accepted_states',[])
    observation_axes=curve.get('observations',{}).get('axes',[])
    matches=[state for state in states if state['time']==time]
    if len(matches)!=1 or len(observation_axes)!=1 or observation_axes[0].get('unit')!=time_unit:
        return {'actual_state_status':'NO_EXACT_ACCEPTED_STATE_AT_DISPLAY_TIME',
                'actual_deformation_gradient':None,'actual_J':None}
    state=matches[0]
    return {'actual_state_status':'EXACT_ACCEPTED_CANDIDATE_STATE',
            'actual_deformation_gradient':deepcopy(state['F']),'actual_J':state['J'],
            'native_P':deepcopy(state['native_P']),'accepted_increment_sha256':state['accepted_increment_sha256']}
