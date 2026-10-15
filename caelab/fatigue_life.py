"""Cyclic total-strain CMB / SWT life roots, in cycles (not reversals).

No coefficients, fatigue limits, extrapolation or constitutive approximations
are inferred. See docs/fatigue/MATHEMATICS.md for the model and source boundary.
"""
from __future__ import annotations

from copy import deepcopy
import math

from .execution_control import check_cancelled

ROOT_DEFAULTS = {'relative_tolerance': 1e-10,
                 'residual_relative_tolerance': 1e-10, 'max_iterations': 128}
COEFFICIENT_BASIS = 'FULLY_REVERSED_AXIAL_STRAIN_LIFE'


def number(value, label, *, positive=False):
    if type(value) not in (int, float) or not math.isfinite(value) or (positive and value <= 0):
        raise ValueError(label + ('에는 유한한 양수가 필요합니다' if positive else '에는 유한한 수가 필요합니다'))
    return float(value)


def calibration_draft():
    return dict(E=None, sigma_f=None, epsilon_f=None, b=None, c=None,
                stress_unit='MPa', strain_unit='1', cycles_min=None, cycles_max=None,
                strain_amplitude_min=None, strain_amplitude_max=None,
                max_stress_min=None, max_stress_max=None,
                temperature_min_k=None, temperature_max_k=None,
                reference='', conditions='', failure_definition='',
                coefficient_basis=COEFFICIENT_BASIS, cyclic_state='UNKNOWN', test_basis='AXIAL_NORMAL')


def normalize_calibration(value, *, swt=True):
    if not isinstance(value, dict) or set(value) != set(calibration_draft()):
        raise ValueError('ε–N 계수, 단위, 교정 범위와 시험 출처를 명시하세요')
    c = deepcopy(value)
    if c['stress_unit'] not in ('MPa', 'Pa') or c['strain_unit'] not in ('1', '%'):
        raise ValueError('교정 응력 단위는 Pa/MPa, 변형률 단위는 1/%만 지원합니다')
    for key in ('reference', 'conditions', 'failure_definition'):
        if not isinstance(c[key], str) or not c[key].strip():
            raise ValueError('교정 ' + key + '를 명시하세요. 기본 재료 자료는 생성하지 않습니다')
    if c['coefficient_basis'] != COEFFICIENT_BASIS:
        raise ValueError('완전 양진 축방향 cyclic ε–N 계수가 필요합니다. 평균응력 이중 보정은 금지됩니다')
    if c['test_basis'] != 'AXIAL_NORMAL' or c['cyclic_state'] != 'STABILIZED':
        raise ValueError('정상 축방향 시험과 안정 cyclic 계수의 근거를 확인하세요. monotonic 계수로 대체하지 않습니다')
    sf = 1e-6 if c['stress_unit'] == 'Pa' else 1.0
    ef = .01 if c['strain_unit'] == '%' else 1.0
    for key in ('E', 'sigma_f'):
        c[key] = number(c[key], key, positive=True) * sf
    c['epsilon_f'] = number(c['epsilon_f'], 'epsilon_f', positive=True) * ef
    for key in ('b', 'c'):
        c[key] = number(c[key], key)
        if c[key] >= 0:
            raise ValueError('이번 단조 감소 양의 root 모델에서는 b,c<0이어야 합니다')
    for lower, upper, factor in (('cycles_min', 'cycles_max', 1.0),
                                  ('strain_amplitude_min', 'strain_amplitude_max', ef),
                                  ('temperature_min_k', 'temperature_max_k', 1.0)):
        c[lower] = number(c[lower], lower, positive=True) * factor
        c[upper] = number(c[upper], upper, positive=True) * factor
        if c[lower] >= c[upper]:
            raise ValueError(lower + '은 ' + upper + '보다 작아야 합니다')
    if swt:
        for key in ('max_stress_min', 'max_stress_max'):
            c[key] = number(c[key], key, positive=True) * sf
        if c['max_stress_min'] >= c['max_stress_max']:
            raise ValueError('SWT 최대 정상응력의 교정 최소/최대를 확인하세요')
    else:
        # Stress calibration is not an input requirement of CMB/NONE.
        c['max_stress_min'] = c['max_stress_max'] = None
    c.update(stress_unit='MPa', strain_unit='1')
    if any(not math.isfinite(v) for v in c.values() if type(v) is float):
        raise ValueError('단위 변환 후 교정값이 유한하지 않습니다')
    return c


def validate_root(root):
    if not isinstance(root, dict) or set(root) != set(ROOT_DEFAULTS):
        raise ValueError('양의 root의 상대폭, 잔차 허용치와 반복 횟수가 필요합니다')
    for key in ('relative_tolerance', 'residual_relative_tolerance'):
        v = number(root[key], key, positive=True)
        if not 1e-14 <= v <= 1e-4:
            raise ValueError('root 허용치는 1e-14..1e-4 사이에 명시하세요')
    if type(root['max_iterations']) is not int or not 1 <= root['max_iterations'] <= 512:
        raise ValueError('root 반복 횟수는 1..512의 정수여야 합니다')
    return deepcopy(root)


def _terms(log_n, c, model):
    x = math.log(2.0) + log_n
    if model == 'NONE':
        return (c['sigma_f'] / c['E'] * math.exp(c['b'] * x),
                c['epsilon_f'] * math.exp(c['c'] * x))
    return (c['sigma_f'] ** 2 / c['E'] * math.exp(2 * c['b'] * x),
            c['sigma_f'] * c['epsilon_f'] * math.exp((c['b'] + c['c']) * x))


def solve_life(amplitude, sigma_max_mpa, calibration, *, mean_stress, temperature_k,
               root=None):
    """Return an auditable root or UNKNOWN; never substitute infinite life.

    `amplitude` is total normal strain amplitude [1]. `sigma_max_mpa` is the
    sampled concurrent maximum on THIS cycle, and is unused for NONE.
    """
    result = {'status': 'UNKNOWN', 'reason': '', 'Nf_cycles': None, 'reversals': None,
              'iterations': 0, 'residual': None, 'relative_residual': None,
              'bracket_initial_cycles': None, 'bracket_final_cycles': None,
              'elastic_term': None, 'plastic_term': None,
              'rhs_unit': 'MPa' if mean_stress == 'SWT' else '1',
              'mean_stress_correction': mean_stress}
    def unknown(reason):
        result['reason'] = reason
        return result
    try:
        if mean_stress not in ('NONE', 'SWT'):
            return unknown('UNSUPPORTED_MEAN_STRESS_MODEL')
        c = normalize_calibration(calibration, swt=mean_stress == 'SWT')
        options = validate_root(ROOT_DEFAULTS if root is None else root)
        result['root_options'] = options
        a = number(amplitude, 'total strain amplitude')
        temperature = number(temperature_k, '온도 [K]', positive=True)
        if a <= 0:
            return unknown('ZERO_OR_NEGATIVE_AMPLITUDE_NO_LIFE_CLAIM')
        if not c['strain_amplitude_min'] <= a <= c['strain_amplitude_max']:
            return unknown('STRAIN_AMPLITUDE_OUTSIDE_CALIBRATION')
        if not c['temperature_min_k'] <= temperature <= c['temperature_max_k']:
            return unknown('TEMPERATURE_OUTSIDE_CALIBRATION')
        target = a
        if mean_stress == 'SWT':
            maximum = number(sigma_max_mpa, '같은 cycle의 최대 정상응력 [MPa]')
            if maximum <= 0:
                return unknown('SWT_NON_TENSILE_CYCLE_OUTSIDE_MODEL')
            if not c['max_stress_min'] <= maximum <= c['max_stress_max']:
                return unknown('SWT_MAX_STRESS_OUTSIDE_CALIBRATION')
            target *= maximum
        if not math.isfinite(target) or target <= 0:
            return unknown('NONFINITE_OR_UNDERFLOW_TARGET')
        low, high = math.log(c['cycles_min']), math.log(c['cycles_max'])
        initial = [c['cycles_min'], c['cycles_max']]
        result.update(target=target, bracket_initial_cycles=initial, bracket_final_cycles=initial)
        fl, fh = sum(_terms(low, c, mean_stress)), sum(_terms(high, c, mean_stress))
        if not all(math.isfinite(v) and v > 0 for v in (fl, fh)) or fl <= fh:
            return unknown('INVALID_POSITIVE_ROOT_BRACKET')
        result['bracket_rhs'] = [fl, fh]
        if not fh <= target <= fl:
            return unknown('NO_ROOT_IN_CALIBRATED_CYCLE_RANGE_NO_EXTRAPOLATION')
        if target == fl or target == fh:
            low = high = low if target == fl else high
        for iteration in range(1, options['max_iterations'] + 1):
            check_cancelled()
            mid = low + (high - low) / 2.0
            terms = _terms(mid, c, mean_stress)
            residual = sum(terms) - target
            relative = abs(residual) / target
            result.update(iterations=iteration, residual=residual, relative_residual=relative,
                          elastic_term=terms[0], plastic_term=terms[1],
                          bracket_final_cycles=[math.exp(low), math.exp(high)])
            # A relative log width is checked without exponent overflow.
            if high - low <= math.log1p(options['relative_tolerance']) and relative <= options['residual_relative_tolerance']:
                n = math.exp(mid)
                if not math.isfinite(2 * n):
                    return unknown('NONFINITE_REVERSALS')
                result.update(status='CALCULATED', reason='', Nf_cycles=n, reversals=2 * n)
                return result
            if residual > 0:
                low = mid
            else:
                high = mid
        return unknown('ROOT_DID_NOT_CONVERGE')
    except (ValueError, TypeError, OverflowError, ZeroDivisionError) as error:
        return unknown('INVALID_OR_MISSING_CALIBRATION: ' + str(error))
