"""Explicit test-column conversion and prescribed kinematics; no solver or owner.

The Data affine mappings retain raw columns. Kinematics recipes refer to another
channel of the SAME exact retained import, never to a latest file/result.
"""
from copy import deepcopy
import math

STRESS = {'Pa': 1., 'kPa': 1e3, 'MPa': 1e6, 'GPa': 1e9}
LENGTH = {'m': 1., 'mm': 1e-3, 'um': 1e-6}
FORCE = {'N': 1., 'kN': 1e3}
TIME = {'s': 1., 'ms': 1e-3, 'min': 60.}
DRIVES = {'engineering_strain', 'stretch', 'simple_shear'}


def finite(value, label, *, positive=False):
    if type(value) not in (int, float) or not math.isfinite(value) or positive and value <= 0:
        raise ValueError(label + '에 유효한' + (' 양수' if positive else ' 수치') + '를 입력하세요.')
    return value


def column_mapping(*, time_column, time_unit, response_column, response_kind,
                   response_unit, stress_unit, measure, component, drive_column,
                   drive_kind, drive_unit, area=None, area_unit='mm',
                   gauge=None, gauge_unit='mm'):
    """Compile only conversions explicitly chosen by the user."""
    if measure not in ('infinitesimal_Cauchy', 'first_Piola'):
        raise ValueError('응력 정의를 선택하세요.')
    if component not in ('xx', 'yy', 'zz', 'xy', 'xz', 'yz'):
        raise ValueError('응력 성분을 선택하세요.')
    if time_unit not in TIME or stress_unit not in STRESS:
        raise ValueError('시간과 응력 단위를 선택하세요.')
    if response_kind == 'force':
        if measure != 'first_Piola':
            raise ValueError('Force/A0는 공칭 응력입니다. 현재 면적 없이 Cauchy 응력으로 변환하지 않습니다.')
        factor = FORCE[response_unit] / (finite(area, '초기 단면적', positive=True) * LENGTH[area_unit]**2) / STRESS[stress_unit]
    elif response_kind == 'stress':
        factor = STRESS[response_unit] / STRESS[stress_unit]
    else:
        raise ValueError('응력 또는 힘 열을 선택하세요.')
    if drive_kind == 'displacement':
        drive_scale = LENGTH[drive_unit] / (finite(gauge, '초기 표점 거리', positive=True) * LENGTH[gauge_unit])
        converted_kind = 'engineering_strain'
    elif drive_kind in DRIVES:
        if drive_unit not in ('1', '%') or drive_kind == 'stretch' and drive_unit != '1':
            raise ValueError('변형률/전단량은 1 또는 %, 신장비는 1을 사용하세요.')
        drive_scale = .01 if drive_unit == '%' else 1.
        converted_kind = drive_kind
    else:
        raise ValueError('변형 이력의 물리량을 선택하세요.')
    axis = {'column': time_column, 'name': 'time', 'unit': 's', 'scale': TIME[time_unit]}
    shared = {'frame': 'material_cartesian', 'location': 'material_point', 'reduction': 'none'}
    return {'stress': dict(shared, column=response_column, unit=stress_unit, component=component,
                           measure=measure, scale=factor, axis=deepcopy(axis)),
            'deformation': dict(shared, column=drive_column, unit='1',
                component='xy' if converted_kind == 'simple_shear' else 'xx',
                measure=converted_kind, scale=drive_scale, axis=deepcopy(axis))}


def validate_kinematics(recipe):
    if not isinstance(recipe, dict) or set(recipe) != {'channel', 'kind', 'lateral_22', 'lateral_33'}:
        raise ValueError('시험 조건에는 변형 채널, 물리량, 명시한 횡방향 신장비가 필요합니다.')
    if not isinstance(recipe['channel'], str) or not recipe['channel'] or recipe['kind'] not in DRIVES:
        raise ValueError('변형 채널과 지원하는 변형 이력을 선택하세요.')
    for key in ('lateral_22', 'lateral_33'):
        finite(recipe[key], key, positive=True)
    if recipe['kind'] == 'simple_shear' and (recipe['lateral_22'], recipe['lateral_33']) != (1., 1.):
        raise ValueError('단순 전단은 대각 성분 1을 명시하세요. 다른 경로는 전체 변형구배 편집을 사용하세요.')


def measured_protocol(settings, result, recipe):
    validate_kinematics(recipe)
    if result.get('execution_status') != 'SUCCEEDED':
        raise ValueError('변형 이력을 가져오지 못했습니다.')
    response = result.get('responses', {}).get(recipe['channel'])
    if not isinstance(response, dict):
        raise ValueError('저장된 가져오기에 변형 채널이 없습니다.')
    if (response.get('kind') != 'series' or response.get('unit') != '1'
            or response.get('measure') != recipe['kind']
            or response.get('component') != ('xy' if recipe['kind'] == 'simple_shear' else 'xx')
            or response.get('frame') != 'material_cartesian'
            or response.get('location') != 'material_point' or response.get('reduction') != 'none'
            or response.get('coordinate_system','UNSPECIFIED') != 'UNSPECIFIED'
            or 'coordinate_frame' in response or response.get('valid') is False):
        raise ValueError('변형 채널의 물리량·성분·좌표계·단위를 열 설정에서 확인하세요.')
    axes = response.get('axes', [])
    if (len(axes) != 1 or axes[0].get('name') != 'time'
            or axes[0].get('unit') != settings.get('time_unit')):
        raise ValueError('명시한 시간 열/단위가 재료의 시간 단위와 다릅니다.')
    times, values = axes[0].get('values', []), response.get('value', [])
    if not len(times) or len(times) != len(values):
        raise ValueError('시간과 변형 이력의 행 수가 다릅니다.')
    for t, v in zip(times, values):
        finite(t, '시간'); finite(v, '변형 이력')
    if any(b <= a for a, b in zip(times, times[1:])):
        raise ValueError('시간은 순서대로 증가해야 합니다. 재시작 구간을 따로 선택하세요.')
    if 'target_grid' in response:
        from .data_processing_lineage import aligned_driver_indexes
        aligned_driver_indexes(response, response)
    # Missing drive segments cannot be interpolated into a prescribed loading path.
    if response.get('has_calculation_gaps'):
        raise ValueError('변형 이력에 제외 구간이 있습니다. 연속된 이력을 선택하거나 전체 변형구배를 명시하세요.')
    gradients = []
    for value in values:
        if recipe['kind'] == 'simple_shear':
            F = [[1., value, 0.], [0., 1., 0.], [0., 0., 1.]]
        else:
            stretch = value + 1. if recipe['kind'] == 'engineering_strain' else value
            finite(stretch, '축방향 신장비', positive=True)
            F = [[stretch, 0., 0.], [0., recipe['lateral_22'], 0.], [0., 0., recipe['lateral_33']]]
        gradients.append(F)
    compiled = deepcopy(settings)
    compiled.update(time=list(times), deformation_gradient=gradients)
    return compiled


def physical_residual(curve):
    """Unweighted prediction-minus-observation; never label optimizer r as stress."""
    obs = curve.get('observations', {})
    axes = obs.get('axes', [])
    x, y, p = (axes[0].get('values', []) if len(axes) == 1 else []), obs.get('value', []), curve.get('prediction', [])
    if not isinstance(p, list) or len(x) != len(y) or len(x) != len(p):
        return [], []
    mask = curve.get('mask', [True] * len(x))
    if len(mask) != len(x):
        return [], []
    residual = [b-a if used and type(a) in (int, float) and type(b) in (int, float)
                and math.isfinite(a) and math.isfinite(b) else None for a, b, used in zip(y, p, mask)]
    return list(x), residual


def deformation_plot_axis(observation, imported, recipe):
    """Display the measured driver at the exact observed rows/times, without sorting.

    The evaluator continues to use its time axis. Reversing/repeated deformation
    coordinates remain in acquisition order, including unloading loops.
    """
    axes=observation.get('axes',[])
    if len(axes)!=1 or axes[0].get('name')!='time':
        raise ValueError('관측의 시간축이 없습니다.')
    measured_protocol({'time_unit':axes[0].get('unit')},imported,recipe)
    driver=imported['responses'][recipe['channel']]
    from .data_processing_lineage import aligned_driver_indexes
    indexes = aligned_driver_indexes(observation, driver)
    labels={'engineering_strain':'측정 변형률','stretch':'측정 신장비','simple_shear':'측정 전단량'}
    return {'name':labels[recipe['kind']],'unit':driver['unit'],
            'values':[driver['value'][i] for i in indexes]}
