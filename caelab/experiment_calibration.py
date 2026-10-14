"""Explicit affine sensor calibration; raw samples and supplied uncertainty survive.

No fitted uncertainty, independence, specimen strain or device acquisition is inferred.
"""
from copy import deepcopy
from datetime import datetime
import math

import numpy as np

UNITS = {
    'V': ('voltage', 1.), 'mV': ('voltage', .001), 'uV': ('voltage', .000001),
    'count': ('count', 1.), 'N': ('force', 1.), 'kN': ('force', 1000.),
    'm': ('length', 1.), 'mm': ('length', .001), 'um': ('length', .000001),
    'Pa': ('stress', 1.), 'kPa': ('stress', 1000.), 'MPa': ('stress', 1e6),
    '1': ('dimensionless', 1.), '%': ('dimensionless', .01),
    's': ('time', 1.), 'ms': ('time', .001),
}


def number(value, label):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError(label + '에 유효한 수치를 입력하세요.')
    return float(value)


def factor(source, target):
    if source not in UNITS or target not in UNITS or UNITS[source][0] != UNITS[target][0]:
        raise ValueError('호환되는 단위를 명시하세요: ' + str(source) + ' → ' + str(target))
    return UNITS[source][1] / UNITS[target][1]


def instant(value, label):
    try:
        result = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if result.tzinfo is None:
            raise ValueError()
        return result
    except (ValueError, AttributeError):
        raise ValueError(label + '에 시간대가 있는 ISO 관측 시각을 입력하세요.') from None


def default_calibration(unit='N'):
    return {'input_unit': 'mV', 'coefficient_input_unit': 'mV', 'output_unit': unit,
        'a': '', 'x0': 0., 'x0_unit': 'mV', 'b': 0.,
        'input_range': None, 'sensor_range': None, 'valid_from': '', 'valid_until': '',
        'observed_at': '', 'source': None, 'uncertainty': None,
        'sensor': '', 'gauge': '', 'displacement_role': 'UNDECLARED'}


def validate_calibration(recipe, output_unit=None):
    required = set(default_calibration())
    if not isinstance(recipe, dict) or set(recipe) != required:
        raise ValueError('교정에는 단위, 계수, 영점, 범위와 원본 기록이 필요합니다.')
    for key in ('input_unit', 'coefficient_input_unit', 'x0_unit'):
        factor(recipe[key], recipe['coefficient_input_unit'])
    if recipe['output_unit'] not in UNITS or output_unit is not None and recipe['output_unit'] != output_unit:
        raise ValueError('교정 출력 단위와 채널 단위를 일치시키세요.')
    for key in ('a', 'x0', 'b'):
        number(recipe[key], key)
    for key in ('input_range', 'sensor_range'):
        interval = recipe[key]
        if interval is not None:
            if not isinstance(interval, dict) or set(interval) != {'minimum', 'maximum', 'unit'}:
                raise ValueError('교정/센서 범위에는 하한, 상한, 단위가 필요합니다.')
            factor(interval['unit'], recipe['coefficient_input_unit'])
            if number(interval['minimum'], '범위 하한') >= number(interval['maximum'], '범위 상한'):
                raise ValueError('범위 하한은 상한보다 작아야 합니다.')
    source = recipe['source']
    from .storage import check_id
    import re
    if (not isinstance(source, dict) or set(source) != {'data_id', 'sha256', 'name'}
            or not check_id(source['data_id']).startswith('D')
            or not re.fullmatch('[0-9a-f]{64}', str(source['sha256']))):
        raise ValueError('교정 원본 파일을 선택하세요. 원본 없이 교정을 실행하지 않습니다.')
    for key in ('sensor', 'gauge', 'observed_at', 'valid_from', 'valid_until'):
        if not isinstance(recipe[key], str):
            raise ValueError(key + '는 제공된 설명 또는 시각이어야 합니다.')
    dates = {key: instant(recipe[key], key) for key in ('observed_at', 'valid_from', 'valid_until') if recipe[key]}
    if ('valid_from' in dates or 'valid_until' in dates) and 'observed_at' not in dates:
        raise ValueError('교정 유효기간을 확인하려면 관측 시각을 입력하세요.')
    if 'valid_from' in dates and 'valid_until' in dates and dates['valid_from'] > dates['valid_until']:
        raise ValueError('교정 유효기간의 순서를 확인하세요.')
    if recipe['displacement_role'] not in ('UNDECLARED', 'actuator', 'specimen_gauge', 'not_displacement'):
        raise ValueError('변위의 측정 위치를 명시하세요.')
    u = recipe['uncertainty']
    if u is not None:
        if not isinstance(u, dict) or set(u) != {'value', 'unit', 'kind', 'k', 'correlation', 'note'}:
            raise ValueError('제공 불확실성의 종류, 단위, 포함인자와 상관 정보를 보존하세요.')
        if number(u['value'], '불확실성') < 0:
            raise ValueError('불확실성은 음수일 수 없습니다.')
        factor(u['unit'], recipe['output_unit'])
        if u['kind'] not in (None, 'UNKNOWN', 'standard', 'expanded'):
            raise ValueError('제공된 종류를 선택하거나 미확인으로 남기세요.')
        if u['k'] is not None and number(u['k'], '포함인자') <= 0:
            raise ValueError('포함인자는 양수여야 합니다.')
        if u['correlation'] not in ('UNKNOWN', 'independent_declared', 'correlated_declared'):
            raise ValueError('상관 정보가 없으면 미확인으로 남기세요.')
        if not isinstance(u['note'], str):
            raise ValueError('불확실성 출처/상관 설명을 입력하세요.')
    return recipe


def calibrate(raw, recipe):
    validate_calibration(recipe)
    raw = np.asarray(raw, dtype=float)
    unit = recipe['coefficient_input_unit']
    x = raw * factor(recipe['input_unit'], unit)
    zero = recipe['x0'] * factor(recipe['x0_unit'], unit)
    with np.errstate(over='ignore', invalid='ignore'):
        values = recipe['a'] * (x - zero) + recipe['b']
    finite = np.isfinite(raw) & np.isfinite(values)
    outside = np.zeros(raw.shape, bool)
    saturated = np.zeros(raw.shape, bool)
    for key, flags, inclusive in (('input_range', outside, False), ('sensor_range', saturated, True)):
        interval = recipe[key]
        if interval:
            low, high = [interval[k] * factor(interval['unit'], unit) for k in ('minimum', 'maximum')]
            flags[:] = (x <= low) | (x >= high) if inclusive else (x < low) | (x > high)
    dates = {k: instant(recipe[k], k) for k in ('observed_at', 'valid_from', 'valid_until') if recipe[k]}
    expired = bool('observed_at' in dates and
        (('valid_from' in dates and dates['observed_at'] < dates['valid_from'])
         or ('valid_until' in dates and dates['observed_at'] > dates['valid_until'])))
    valid = finite & ~outside & ~saturated & (not expired)
    reasons = ['; '.join(reason for reason, applies in (
        ('nonfinite sample', not f), ('outside calibration range', o),
        ('sensor saturation', s), ('outside calibration validity period', expired)) if applies)
        for f, o, s in zip(finite, outside, saturated)]
    return values, {'calibration_valid': valid.tolist(), 'calibration_out_of_range': outside.tolist(),
        'sensor_saturated': saturated.tolist(), 'calibration_reasons': reasons,
        'validity_period_status': 'OUTSIDE' if expired else 'CHECKED' if len(dates) > 1 else 'UNKNOWN',
        'uncertainty': deepcopy(recipe['uncertainty'])}


def default_acquisition():
    return {'name': '', 'sample_rate_hz': '', 'duration_s': '', 'time_offset_s': 0.,
        'clock': '', 'device': '', 'channels': []}


def validate_acquisition(setup):
    if not isinstance(setup, dict) or set(setup) != set(default_acquisition()):
        raise ValueError('수집 설정의 이름, 시간과 채널을 확인하세요.')
    for key in ('sample_rate_hz', 'duration_s'):
        if number(setup[key], key) <= 0:
            raise ValueError('요청 수집 주기와 기간은 양수여야 합니다.')
    number(setup['time_offset_s'], '시간 오프셋')
    if not isinstance(setup['channels'], list) or not setup['channels']:
        raise ValueError('수집할 채널을 추가하세요.')
    names = set()
    for row in setup['channels']:
        if not isinstance(row, dict) or set(row) != {'name', 'role', 'unit', 'calibration'}:
            raise ValueError('채널 이름, 역할, 단위와 교정을 확인하세요.')
        if not isinstance(row['name'], str) or not row['name'].strip() or row['name'] in names:
            raise ValueError('서로 다른 채널 이름을 입력하세요.')
        names.add(row['name'])
        if row['role'] not in ('measurement', 'time', 'actuator', 'specimen_gauge', 'temperature'):
            raise ValueError('채널 역할을 선택하세요.')
        if not isinstance(row['unit'], str) or not row['unit']:
            raise ValueError('채널 단위를 명시하세요.')
        if row['calibration'] is not None:
            validate_calibration(row['calibration'], row['unit'])
    return setup
