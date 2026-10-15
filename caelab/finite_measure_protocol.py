"""Measured finite drivers compiled through the existing mixed-control helper."""
from copy import deepcopy
import math
import numpy as np
from .finite_measure import AXES, FRAME, number

KIND = 'finite_measured'


def validate(recipe):
    if (not isinstance(recipe, dict) or set(recipe) != {'version', 'kind', 'channel', 'axis', 'lateral', 'lateral_22', 'lateral_33'}
            or recipe['version'] != 2 or type(recipe['version']) is not int or recipe['kind'] != KIND
            or recipe['axis'] not in AXES or recipe['lateral'] not in {'free', 'fixed', 'prescribed'}
            or not isinstance(recipe['channel'], str) or not recipe['channel']):
        raise ValueError('유한 측정 driver에는 채널·축·명시한 횡방향 조건이 필요합니다.')
    if recipe['lateral'] == 'prescribed':
        for key in ('lateral_22', 'lateral_33'):
            number(recipe[key], key, positive=True)
    return recipe


def measured_protocol(settings, result, recipe):
    validate(recipe)
    if result.get('execution_status') != 'SUCCEEDED':
        raise ValueError('성공한 보존 driver를 선택하세요. 실패 prefix로 protocol을 만들지 않습니다.')
    response = result.get('responses', {}).get(recipe['channel'])
    if not isinstance(response, dict):
        raise ValueError('보존한 변형 채널이 없습니다.')
    if (response.get('kind') != 'series' or response.get('unit') != '1'
            or response.get('measure') not in {'stretch', 'engineering_strain', 'log_strain'}
            or response.get('component') != recipe['axis']*2 or response.get('frame') != FRAME
            or response.get('location') != 'material_point' or response.get('reduction') != 'none'
            or response.get('coordinate_system', 'UNSPECIFIED') != 'UNSPECIFIED' or 'coordinate_frame' in response
            or response.get('valid') is False or response.get('has_calculation_gaps')):
        raise ValueError('측정 driver의 물리량/방향/단위/무효·제외 구간을 확인하세요. 누락 구간을 보간하지 않습니다.')
    axes = response.get('axes', [])
    if (len(axes) != 1 or axes[0].get('name') != 'time' or axes[0].get('unit') != settings.get('time_unit')):
        raise ValueError('측정 driver와 Material 시간 단위가 다릅니다.')
    time = axes[0].get('values', []); values = response.get('value', [])
    if not values or len(time) != len(values):
        raise ValueError('측정 driver의 원행/time 길이가 다릅니다.')
    if 'processing_channel' in response:
        from .data_processing_lineage import verify_response
        verify_response(response, complete=True)
    for v in time: number(v, 'time')
    if any(b <= a for a, b in zip(time, time[1:])):
        raise ValueError('time은 acquisition 순서로 증가해야 합니다. 반복 deformation을 정렬하지 않습니다.')
    stretch = [number(v, '변형 이력') + 1. if response['measure'] == 'engineering_strain'
               else math.exp(number(v, '로그 변형률')) if response['measure'] == 'log_strain'
               else number(v, '신장비', positive=True) for v in values]
    for v in stretch: number(v, '신장비', positive=True)
    if settings.get('model') != 'neo_hooke':
        raise ValueError('이 유한변형 driver 연결은 기존 Neo-Hooke 경로를 선택하세요.')
    # Compile the established x-axis protocol, then permute its physical axes.
    # No new boundary solver or material response is defined here.
    from .material_control import uniaxial_settings
    native = 'initial_state' in settings
    carrier = {k: deepcopy(settings[k]) for k in ('model', 'parameters', 'stress_unit', 'time_unit')}
    carrier['time'] = list(time)
    kwargs = {}
    if recipe['lateral'] == 'prescribed':
        kwargs = {'lateral_22': [recipe['lateral_22']]*len(time), 'lateral_33': [recipe['lateral_33']]*len(time)}
    solver = settings.get('boundary_control', {}).get('solver')
    if native and solver is None:
        from plugins.material_point.law_native import BOUNDARY_OPTIONS
        solver = BOUNDARY_OPTIONS
    compiled = uniaxial_settings(carrier, stretch, control='stretch', lateral=recipe['lateral'], solver=solver, **kwargs)
    i = AXES[recipe['axis']]; order = [i] + [j for j in range(3) if j != i]
    if i:
        permuted = []
        for F in compiled['deformation_gradient']:
            transformed = np.zeros((3, 3))
            transformed[np.ix_(order, order)] = np.asarray(F)
            permuted.append(transformed.tolist())
        compiled['deformation_gradient'] = permuted
        if 'boundary_control' in compiled:
            bc = compiled['boundary_control']
            bc['stress_components'] = {''.join('xyz'[order['xyz'.index(c)]] for c in name): target
                                      for name, target in bc['stress_components'].items()}
    if native:
        compiled['initial_state'] = deepcopy(settings['initial_state'])
        if 'boundary_control' in compiled:
            bc = compiled['boundary_control']
            compiled['boundary_control'] = {key: bc[key] for key in ('stress_components', 'solver')}
    if 'tangent_probe' in settings: compiled['tangent_probe'] = deepcopy(settings['tangent_probe'])
    from .material_law_validation import validate_settings
    validate_settings(compiled)
    return compiled


def recipe(channel, axis, *, lateral, lateral_22=None, lateral_33=None):
    return dict(version=2, kind=KIND, channel=channel, axis=axis, lateral=lateral,
                lateral_22=lateral_22, lateral_33=lateral_33)
