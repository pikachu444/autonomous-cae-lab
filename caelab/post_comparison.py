"""Explicit physical contracts for Post comparison v2 (no native side effects).

The native owner owns sources, interpolation filters and retained results. These
functions validate declarations and operate on detached float64 physical tuples.
"""
from copy import deepcopy
import math
import numpy as np
from .experiment_calibration import UNITS, factor

ORDER = ['freeze_endpoints', 'quality_to_missing', 'association_projection',
         'time_interpolation', 'geometry_transform', 'response_unit_and_basis',
         'spatial_transfer', 'component_or_norm', 'difference']
IDENTITY = [[1., 0., 0.], [0., 1., 0.], [0., 0., 1.]]
COMPONENTS = ['xx', 'xy', 'xz', 'yx', 'yy', 'yz', 'zx', 'zy', 'zz']


def number(value, name):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError(name + ': 유효한 수치를 입력하세요.')
    return float(value)


def rotation(value):
    try:
        matrix = np.asarray(value, dtype=float)
    except (TypeError, ValueError):
        raise ValueError('회전행렬에는 3×3 수치가 필요합니다.') from None
    if (matrix.shape != (3, 3) or not np.isfinite(matrix).all()
            or not np.allclose(matrix @ matrix.T, np.eye(3), atol=1e-12, rtol=0)
            or not math.isclose(float(np.linalg.det(matrix)), 1., abs_tol=1e-12, rel_tol=0)):
        raise ValueError('축 회전은 직교 정규 오른손 회전행렬이어야 합니다.')
    return matrix


def affine_unit(source, target, quantity, temperature_kind=None):
    temperature = {'K': (1., 0.), 'degC': (1., 273.15), '°C': (1., 273.15)}
    if source in temperature or target in temperature:
        if source not in temperature or target not in temperature or quantity != 'temperature':
            raise ValueError('온도와 다른 물리량의 단위를 변환할 수 없습니다.')
        if temperature_kind not in ('absolute', 'difference'):
            raise ValueError('절대온도인지 온도차인지 선택하세요.')
        a, b = temperature[source]; c, d = temperature[target]
        return a / c, (b - d) / c if temperature_kind == 'absolute' else 0.
    if source == target and isinstance(source, str) and source.strip() and source != 'UNKNOWN':
        return 1., 0.
    return factor(source, target), 0.


def layout_size(layout):
    if not isinstance(layout, dict):
        raise ValueError('스칼라·벡터·텐서와 성분 순서를 명시하세요.')
    kind, components = layout.get('kind'), layout.get('components')
    if kind == 'scalar' and components == ['scalar']:
        return 1
    if kind == 'vector' and isinstance(components, list) and sorted(components) == ['x', 'y', 'z']:
        return 3
    if kind == 'tensor' and isinstance(components, list) and len(set(components)) == len(components):
        full = set(COMPONENTS)
        symmetric = {'xx', 'yy', 'zz', 'xy', 'yz', 'xz'}
        if (set(components) == full or set(components) == symmetric) and layout.get('shear') in ('tensor', 'engineering', 'kelvin'):
            if len(components) == 9 and layout['shear'] != 'tensor':
                raise ValueError('비대칭 9성분 텐서는 실제 텐서 성분으로 지정하세요.')
            return len(components)
    raise ValueError('성분 수만으로 물리 의미를 추측하지 않습니다. 성분 순서와 전단 규약을 확인하세요.')


def canonical(values, layout):
    values = np.asarray(values, dtype=np.float64)
    size = layout_size(layout)
    if values.ndim == 1:
        values = values[:, None]
    if values.ndim != 2 or values.shape[1] != size:
        raise ValueError('선언한 성분 순서와 실제 배열 크기가 다릅니다.')
    components = layout['components']
    if layout['kind'] == 'scalar':
        return values.copy()
    if layout['kind'] == 'vector':
        return values[:, [components.index(key) for key in ('x', 'y', 'z')]].copy()
    result = np.zeros((len(values), 3, 3), dtype=np.float64)
    divisor = {'tensor': 1., 'engineering': 2., 'kelvin': math.sqrt(2.)}[layout['shear']]
    for index, key in enumerate(components):
        i, j = 'xyz'.index(key[0]), 'xyz'.index(key[1])
        result[:, i, j] = values[:, index] / (divisor if i != j else 1.)
        if size == 6:
            result[:, j, i] = result[:, i, j]
    return result.reshape((-1, 9))


def transform_values(values, side, target, matrix):
    raw = canonical(values, side['layout'])
    scale, offset = affine_unit(side['units'], target['units'], side['quantity'], side.get('temperature_kind'))
    kind = side['layout']['kind']
    if kind != 'scalar' and offset != 0:
        raise ValueError('벡터·텐서에 절대온도 오프셋을 적용할 수 없습니다.')
    r = rotation(matrix)
    converted = raw * scale + offset
    if kind == 'vector':
        converted = converted @ r.T
    elif kind == 'tensor':
        converted = np.einsum('ij,njk,lk->nil', r, converted.reshape((-1, 3, 3)), r).reshape((-1, 9))
    return converted


def scalar(values, kind, selection):
    values = np.asarray(values, dtype=np.float64)
    names = {'scalar': ['scalar'], 'vector': ['x', 'y', 'z'], 'tensor': COMPONENTS}[kind]
    if selection == 'magnitude' and kind in ('vector', 'tensor'):
        return np.linalg.norm(values, axis=1)
    if selection not in names:
        raise ValueError('선택한 물리량의 실제 성분 또는 크기를 선택하세요.')
    return values[:, names.index(selection)]


def transform_points(points, source_unit, target_unit, matrix, translation):
    if source_unit not in UNITS or UNITS[source_unit][0] != 'length' or target_unit not in UNITS or UNITS[target_unit][0] != 'length':
        raise ValueError('형상 좌표에는 길이 단위가 필요합니다.')
    shift = np.asarray(translation, dtype=float)
    if shift.shape != (3,) or not np.isfinite(shift).all():
        raise ValueError('좌표 이동은 기준 결과의 길이 단위로 XYZ를 입력하세요.')
    return np.asarray(points, dtype=np.float64) @ rotation(matrix).T * factor(source_unit, target_unit) + shift


def time_plan(side, native_times, common):
    times = [number(value, '원 결과 시각') for value in native_times]
    selection = side.get('sampling', {'mode': 'exact', 'time': side.get('time')})
    if not times:
        if selection.get('time') is not None or selection.get('mode') != 'exact':
            raise ValueError('시각이 없는 자료에는 시간 보간을 적용할 수 없습니다.')
        return {'times': [None], 'weights': [1.], 'common_time': None}
    if len(set(times)) != len(times) or times != sorted(times):
        raise ValueError('원 시각은 중복 없는 증가 순서여야 합니다.')
    semantics = side.get('time_origin')
    if semantics != common.get('semantics'):
        raise ValueError('물리 시간과 정적 진행값 또는 서로 다른 시간 의미를 혼합할 수 없습니다.')
    if str(semantics).lower() in ('load_parameter', 'static_load_parameter'):
        if selection.get('mode') != 'exact':
            raise ValueError('정적 하중 단계 사이의 보간은 지원하지 않습니다. 정확한 저장 증분을 선택하세요.')
        if side.get('time_units') != '1' or common.get('unit') != '1' or side.get('clock_offset', 0.) != 0:
            raise ValueError('정적 진행값에는 시간 단위나 원점 이동을 적용하지 않습니다.')
        scale = 1.
    else:
        if side.get('time_units') not in UNITS or UNITS[side['time_units']][0] != 'time':
            raise ValueError('시간 단위를 명시하세요.')
        if common.get('unit') not in UNITS or UNITS[common['unit']][0] != 'time':
            raise ValueError('비교 시간 단위를 명시하세요.')
        scale = factor(side['time_units'], common['unit'])
    offset = number(side.get('clock_offset', 0.), '시간 원점 이동')
    target = number(common.get('value'), '비교 시각')
    native_target = (target - offset) / scale
    if selection.get('mode') == 'exact':
        value = selection.get('time')
        if value not in times or not math.isclose(value * scale + offset, target, abs_tol=1e-12, rel_tol=1e-12):
            raise ValueError('정확 시각이 비교 시각과 일치하지 않습니다. 보간을 명시적으로 선택하세요.')
        return {'times': [value], 'weights': [1.], 'common_time': target}
    if selection.get('mode') != 'linear':
        raise ValueError('정확 시각 또는 구간 내 선형 보간을 선택하세요.')
    endpoints = selection.get('bracket')
    if not isinstance(endpoints, list) or len(endpoints) != 2 or any(t not in times for t in endpoints):
        raise ValueError('실제 저장된 두 보간 끝점을 선택하세요.')
    lo, hi = endpoints
    if times.index(hi) != times.index(lo) + 1 or not lo < native_target < hi:
        raise ValueError('연속한 저장 시각 사이에서만 보간할 수 있습니다. 외삽하지 않습니다.')
    max_gap = number(selection.get('max_gap'), '허용 시간 간격')
    if max_gap <= 0 or (hi - lo) * scale > max_gap:
        raise ValueError('선택 구간이 명시한 허용 시간 간격을 넘습니다.')
    weight = (native_target - lo) / (hi - lo)
    return {'times': endpoints, 'weights': [1. - weight, weight], 'common_time': target,
            'gap': (hi - lo) * scale, 'max_gap': max_gap}


def validate(recipe, times_a, times_b):
    if recipe.get('version') != 2:
        raise ValueError('Unsupported comparison recipe version')
    if recipe.get('method') not in ('same_mesh', 'linear_tetra_b_to_a'):
        raise ValueError('동일 점 대응 또는 선형 사면체 보간을 선택하세요.')
    if number(recipe.get('tolerance'), '공간 허용 오차') < 0:
        raise ValueError('공간 허용 오차는 음수일 수 없습니다.')
    a, b = recipe['a'], recipe['b']
    for side in (a, b):
        for key in ('source_ref', 'array', 'quantity', 'units', 'measure', 'frame', 'coordinate_units', 'coordinate_frame'):
            if not isinstance(side.get(key), str) or not side[key].strip() or side[key] == 'UNKNOWN':
                raise ValueError(key + ': 원 자료의 물리 의미를 확인하세요. 원본 보기는 계속 사용할 수 있습니다.')
        if side.get('association') not in ('POINTS', 'CELLS'):
            raise ValueError('적분점은 명시적인 투영 adapter 없이는 비교하지 않습니다.')
        if side['association'] == 'CELLS' and side.get('projection') != 'cell_to_point_equal_incident':
            raise ValueError('셀 값을 점에서 비교하려면 인접 셀 동일 가중 투영을 명시하세요.')
        layout_size(side.get('layout'))
    for key in ('quantity', 'measure'):
        if a[key] != b[key]:
            raise ValueError('서로 다른 ' + key + '는 회전으로 변환할 수 없습니다.')
    if a['layout']['kind'] != b['layout']['kind'] or a.get('temperature_kind') != b.get('temperature_kind'):
        raise ValueError('양쪽 물리량의 스칼라/벡터/텐서 및 온도 의미를 일치시키세요.')
    if (a['measure'].lower() not in ('strain', 'infinitesimal_strain', 'small_strain', 'green_lagrange')
            and any(s['layout'].get('shear') == 'engineering' for s in (a, b))):
        raise ValueError('공학 전단 규약은 명시된 변형률에만 적용합니다.')
    target = recipe['target']
    affine_unit(a['units'], target['units'], a['quantity'], a.get('temperature_kind'))
    affine_unit(b['units'], target['units'], b['quantity'], b.get('temperature_kind'))
    alignment = recipe['alignment']
    for key in ('geometry_rotation', 'response_rotation'):
        rotation(alignment[key])
    if a['coordinate_frame'] != b['coordinate_frame'] and not alignment.get('geometry_declared'):
        raise ValueError('B 좌표계를 A 좌표계로 옮기는 정렬을 확인하세요.')
    if a['frame'] != b['frame'] and not alignment.get('response_declared'):
        raise ValueError('B 응답 기저를 A 응답 기저로 옮기는 회전을 확인하세요.')
    kind = a['layout']['kind']
    response_rotated = not np.array_equal(rotation(alignment['response_rotation']), np.eye(3)) or a['frame'] != b['frame']
    if kind == 'scalar' and response_rotated and any(s['layout'].get('scalar_semantics') != 'invariant' for s in (a, b)):
        raise ValueError('스칼라 성분의 기저 변경에는 원 벡터/텐서가 필요합니다. 불변량만 단독 변환할 수 있습니다.')
    if kind == 'tensor' and response_rotated:
        if any(s['layout'].get('indices') != 'same_cartesian_basis' for s in (a, b)):
            raise ValueError('텐서의 두 지표가 같은 직교 기저인지 명시하세요. 두 점 텐서는 별도 기저 대응이 필요합니다.')
        if any(s['measure'].lower() in ('pk1', 'first_piola', 'first_piola_kirchhoff', 'deformation_gradient', 'f') for s in (a, b)):
            raise ValueError('변형기울기/제1 Piola 텐서의 두 기저를 하나의 회전으로 변환하지 않습니다.')
    transform_points([[0., 0., 0.]], b['coordinate_units'], a['coordinate_units'],
                     alignment['geometry_rotation'], alignment['translation'])
    scalar(np.zeros((1, {'scalar': 1, 'vector': 3, 'tensor': 9}[a['layout']['kind']])), a['layout']['kind'], recipe['selection'])
    if recipe.get('difference', 'selected_difference') not in ('selected_difference', 'norm_of_difference'):
        raise ValueError('차이 정의를 선택하세요.')
    if recipe.get('difference') == 'norm_of_difference' and a['layout']['kind'] == 'scalar':
        raise ValueError('차이 벡터/텐서의 크기는 전체 성분에 적용합니다.')
    percent = recipe.get('percent', 'disabled')
    if percent not in ('disabled', 'relative_a', 'absolute_kelvin'):
        raise ValueError('변화율의 기준을 선택하세요.')
    if a.get('temperature_kind') == 'absolute' and percent == 'relative_a':
        raise ValueError('절대온도 변화율에는 Kelvin 절대기준을 선택하거나 변화율을 끄세요.')
    if percent == 'absolute_kelvin' and a.get('temperature_kind') != 'absolute':
        raise ValueError('Kelvin 기준은 절대온도에만 적용합니다.')
    plans = [time_plan(a, times_a, recipe.get('clock', {})), time_plan(b, times_b, recipe.get('clock', {}))]
    if (plans[0]['common_time'] is None) != (plans[1]['common_time'] is None):
        raise ValueError('정적 자료와 시각 자료를 같은 증분이라고 가정하지 않습니다.')
    return plans


def compare(a, b, recipe, inside):
    kind = recipe['a']['layout']['kind']; selection = recipe['selection']
    av, bv = scalar(a, kind, selection), scalar(b, kind, selection)
    valid_a, valid_b = np.isfinite(a).all(axis=1), np.isfinite(b).all(axis=1)
    reason = np.zeros(len(av), dtype=np.uint8)
    reason[~np.asarray(inside, dtype=bool)] = 1
    reason[(reason == 0) & ~valid_a] = 2
    reason[(reason == 0) & ~valid_b] = 3
    with np.errstate(over='ignore', invalid='ignore', divide='ignore'):
        delta = np.linalg.norm(b - a, axis=1) if recipe.get('difference') == 'norm_of_difference' else bv - av
        reason[(reason == 0) & ~np.isfinite(delta)] = 4
        delta[reason != 0] = np.nan
        denominator = np.abs(av)
        if recipe.get('percent') == 'absolute_kelvin':
            scale, shift = affine_unit(recipe['target']['units'], 'K', 'temperature', 'absolute')
            denominator = np.abs(av * scale + shift)
        pr = reason.copy()
        pr[(pr == 0) & (denominator == 0)] = 5
        percent = 100. * delta / denominator
        pr[(pr == 0) & ~np.isfinite(percent)] = 6
        if recipe.get('percent', 'disabled') == 'disabled':
            pr[:] = 7
        percent[pr != 0] = np.nan
    return {'a': av, 'b': bv, 'delta': delta, 'percent': percent,
            'valid': reason == 0, 'reason': reason, 'percent_valid': pr == 0, 'percent_reason': pr}
