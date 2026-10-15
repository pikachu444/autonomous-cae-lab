"""Explicit uniaxial/coaxial observation equations, not a constitutive solver.

Geometry is converted numerically through Data's existing quantity converter.
Only the operands of the chosen operation are admitted; an incomplete unused
field stays a draft. Assumptions are never presented as measured F or J.
"""
from __future__ import annotations
from copy import deepcopy
import math
import numpy as np

SCHEMA = 'caelab.finite-observation/1'
OPERATION = 'finite_observation'
AXES = {'x': 0, 'y': 1, 'z': 2}
F_COMPONENTS = tuple(a + b for a in 'xyz' for b in 'xyz')
STRESS_MEASURES = {'first_Piola', 'finite_Cauchy'}
STRAIN_MEASURES = {'engineering_strain', 'stretch', 'log_strain'}
OUTPUTS = STRESS_MEASURES | STRAIN_MEASURES
BASES = {'none', 'current_area', 'jacobian', 'full_F', 'isochoric_assumption'}
FRAME = 'material_cartesian'
# Roundoff consistency, NOT a controller or material convergence tolerance.
CONSISTENCY_RTOL = 1.e-8
CONSISTENCY_ATOL = 1.e-12


def number(value, label, *, positive=False):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError(f'{label}: 유한한 수치를 입력하세요 (미완성 원문은 저장할 수 있습니다).')
    if positive and value <= 0:
        raise ValueError(f'{label}: 0보다 커야 합니다.')
    return float(value)


def convert(value, source, target, quantity):
    from .data_processing import convert_quantity
    aliases = {'μm': 'um', 'µm': 'um', 'μm²': 'um2', 'µm²': 'um2'}
    source, target = aliases.get(source, source), aliases.get(target, target)
    # Preserve the existing converter; squared micrometres use its mm² path.
    if quantity == 'area' and source == 'um2':
        return float(convert_quantity([number(value, quantity) * 1e-6], 'mm2', target, quantity)[0])
    return float(convert_quantity([number(value, quantity)], source, target, quantity)[0])


def geometry(spec, key, quantity, target):
    item = spec.get('geometry', {}).get(key)
    if not isinstance(item, dict) or set(item) != {'value', 'unit', 'evidence'}:
        raise ValueError(f'{key}: 값·단위·측정 근거를 입력하세요.')
    if not isinstance(item['evidence'], str) or not item['evidence'].strip():
        raise ValueError(f'{key}: 측정 근거를 입력하세요.')
    number(item['value'], key, positive=True)
    result = convert(item['value'], item['unit'], target, quantity)
    return number(result, key, positive=True)


def _assumption(spec, name):
    entry = spec.get('assumptions', {}).get(name)
    if (not isinstance(entry, dict) or set(entry) != {'enabled', 'reason'}
            or entry['enabled'] is not True or not isinstance(entry['reason'], str)
            or not entry['reason'].strip()):
        raise ValueError(name + ': 자동 가정하지 않습니다. 명시 선택과 근거를 입력하세요.')


def validate_definition(spec):
    required = {'version', 'scope', 'axis', 'frame', 'output', 'unit', 'basis',
                'channels', 'geometry', 'measurement', 'assumptions'}
    if not isinstance(spec, dict) or set(spec) != required or type(spec['version']) is not int or spec['version'] != 1:
        raise ValueError('유한변환 정의에는 version=1, 방향·측도·단위·근거·채널이 필요합니다.')
    if spec['scope'] != 'uniaxial_coaxial' or spec['axis'] not in AXES or spec['frame'] != FRAME:
        raise ValueError('단축·동축 및 material_cartesian 방향을 명시하세요. 회전된 scalar 응력은 변환하지 않습니다.')
    if spec['output'] not in OUTPUTS or spec['basis'] not in BASES:
        raise ValueError('지원하는 응력/변형 측도와 면적 또는 J/F 근거를 선택하세요.')
    if not isinstance(spec['channels'], dict) or set(spec['channels']) - {'load', 'deformation', 'area', 'J', *('F'+c for c in F_COMPONENTS)}:
        raise ValueError('선택한 하중·변형·현재 면적·J 또는 전체 F 채널을 선언하세요.')
    for role, channel in spec['channels'].items():
        if not isinstance(channel, str) or not channel.strip():
            raise ValueError(role + ': 채널을 선택하거나 사용하지 않는 항목을 해제하세요.')
    if not isinstance(spec['geometry'], dict) or not isinstance(spec['assumptions'], dict):
        raise ValueError('geometry와 assumptions는 명시한 입력 객체여야 합니다.')
    if spec['output'] in STRAIN_MEASURES:
        if spec['unit'] != '1':
            raise ValueError('신장비·공학/로그 변형률 출력 단위는 1입니다.')
    else:
        convert(1., spec['unit'], 'MPa', 'stress')
    return spec


def active_roles(spec):
    """Select dependencies without inspecting any values or guessing a missing J."""
    validate_definition(spec)
    declared = spec['channels']
    if spec['output'] in STRAIN_MEASURES:
        if 'deformation' in declared:
            return ['deformation']
        return ['F'+c for c in F_COMPONENTS]
    roles = ['load']
    if spec['basis'] == 'none':
        return roles
    if spec['basis'] == 'current_area':
        roles.append('area')
    elif spec['basis'] == 'jacobian':
        roles.extend(['deformation', 'J'])
    elif spec['basis'] == 'full_F':
        roles.extend('F'+c for c in F_COMPONENTS)
    elif spec['basis'] == 'isochoric_assumption':
        roles.append('deformation')
    # Explicitly supplied redundant evidence is checked, never silently preferred.
    for role in ('area', 'J', 'deformation', *('F'+c for c in F_COMPONENTS)):
        if role in declared and role not in roles:
            roles.append(role)
    if any(role.startswith('F') for role in roles) and not all('F'+c in declared for c in F_COMPONENTS):
        raise ValueError('F 근거에는 대각·비대각을 포함한 전체 9개 성분이 필요합니다.')
    return roles


def _metadata(meta, spec, role, *, measures, component):
    if (meta.get('measure') not in measures or meta.get('component') != component
            or meta.get('frame') != spec['frame'] or meta.get('location') != 'material_point'
            or meta.get('reduction', 'none') != 'none'
            or meta.get('coordinate_system', 'UNSPECIFIED') != 'UNSPECIFIED'
            or 'coordinate_frame' in meta):
        raise ValueError(f'{role}: 물리량·방향·frame·location·reduction을 확인하세요.')


def _close(a, b, label):
    if not math.isclose(a, b, rel_tol=CONSISTENCY_RTOL, abs_tol=CONSISTENCY_ATOL):
        raise ValueError(f'중복 근거 충돌 ({label}): {a:.16g} ≠ {b:.16g}. 근거를 수정하거나 선택을 해제하세요.')


def full_tensor_cauchy(P, F, *, stress_frame, gradient_frame):
    """Full PF^T/J in one explicitly common orthonormal Cartesian basis.

    This helper never promotes one axial scalar to a tensor. A rotated scalar
    observation is outside the separate uniaxial observation contract.
    """
    if stress_frame != FRAME or gradient_frame != FRAME:
        raise ValueError('전체 P와 F의 동일한 material_cartesian 성분 기저가 필요합니다.')
    tensors = []
    for value, label in ((P, '전체 P'), (F, '전체 F')):
        raw = np.asarray(value, dtype=object)
        if raw.shape != (3, 3):
            raise ValueError(label + ': 전체 3×3 tensor가 필요합니다. scalar를 확장하지 않습니다.')
        tensors.append(np.array([[number(v, label) for v in row] for row in raw.tolist()]))
    stress, gradient = tensors
    J = number(float(np.linalg.det(gradient)), 'det(F)', positive=True)
    sigma = stress @ gradient.T / J
    if not np.isfinite(sigma).all():
        raise ValueError('변환 응력이 비유한 값입니다.')
    return sigma, J


def coaxial_gradient(value):
    raw = np.asarray(value, dtype=object)
    if raw.shape != (3, 3):
        raise ValueError('전체 3×3 F가 필요합니다.')
    F = np.array([[number(v, 'F') for v in row] for row in raw.tolist()])
    J = number(float(np.linalg.det(F)), 'det(F)', positive=True)
    if np.any(np.diag(F) <= 0) or not np.allclose(F, np.diag(np.diag(F)), rtol=0., atol=1e-12):
        raise ValueError('비동축/회전 F: 축 scalar에 λ/J를 적용할 수 없습니다. 전체 tensor 경로를 사용하세요.')
    return F, J


def evaluate_row(spec, operands):
    """Evaluate a row from {role: {value, metadata}}; deterministic audit replay."""
    validate_definition(spec)
    expected = active_roles(spec)
    if set(operands) != set(expected):
        raise ValueError('선택한 변환의 보조 채널이 누락되었거나 불일치합니다: ' + ', '.join(expected))
    axis = spec['axis']; component = axis * 2; i = AXES[axis]
    audit = {'axis': axis, 'basis': spec['basis'], 'assumptions': deepcopy(spec['assumptions'])}
    def read(role, quantity, unit, measures, comp=component):
        value = operands[role]
        _metadata(value['metadata'], spec, role, measures=measures, component=comp)
        return convert(value['value'], value['metadata'].get('unit'), unit, quantity)
    stretch = None
    if 'deformation' in operands:
        v = operands['deformation']; measure = v['metadata'].get('measure')
        _metadata(v['metadata'], spec, 'deformation', measures=STRAIN_MEASURES | {'gauge_extension', 'crosshead_extension'}, component=component)
        if measure in {'gauge_extension', 'crosshead_extension'}:
            measurement = spec['measurement']
            if measure == 'crosshead_extension':
                if measurement != 'crosshead_assumed_gauge':
                    raise ValueError('crosshead 변위를 gauge로 자동 해석하지 않습니다.')
                _assumption(spec, 'crosshead_equals_gauge')
            elif measurement not in {'extensometer_gauge_extension', 'optical_gauge_extension'}:
                raise ValueError('표점 변위의 측정 방식을 명시하세요.')
            extension = convert(v['value'], v['metadata'].get('unit'), 'mm', 'length')
            L0 = geometry(spec, 'L0', 'length', 'mm')
            stretch = 1. + extension / L0
            audit.update(extension_mm=extension, L0_mm=L0)
        else:
            if spec['measurement'] not in {'measured_axial_strain', 'measured_axial_stretch', 'measured_log_strain'}:
                raise ValueError('변형 열의 축방향 측정 방식을 명시하세요.')
            required_measurement = {'engineering_strain':'measured_axial_strain', 'stretch':'measured_axial_stretch', 'log_strain':'measured_log_strain'}[measure]
            if spec['measurement'] != required_measurement:
                raise ValueError('변형 물리량과 측정 방식이 서로 다릅니다.')
            strain = convert(v['value'], v['metadata'].get('unit'), '1', 'dimensionless')
            if measure == 'stretch' and v['metadata'].get('unit') != '1':
                raise ValueError('신장비 입력 단위는 1이어야 합니다.')
            stretch = strain + 1. if measure == 'engineering_strain' else math.exp(strain) if measure == 'log_strain' else strain
        number(stretch, '축방향 λ', positive=True)
    J = None
    if any('F'+c in operands for c in F_COMPONENTS):
        F = [[read('F'+a+b, 'dimensionless', '1', {'deformation_gradient'}, a+b) for b in 'xyz'] for a in 'xyz']
        if any(operands['F'+c]['metadata'].get('unit') != '1' for c in F_COMPONENTS):
            raise ValueError('전체 F의 각 성분 단위는 1입니다.')
        F, J = coaxial_gradient(F)
        if stretch is not None:
            _close(stretch, float(F[i, i]), '표점 λ와 F 축 성분')
        stretch = float(F[i, i]); audit['F'] = F.tolist()
    if 'J' in operands:
        supplied = read('J', 'dimensionless', '1', {'volume_ratio'}, 'J')
        if operands['J']['metadata'].get('unit') != '1':
            raise ValueError('J 단위는 1입니다.')
        number(supplied, 'J', positive=True)
        if J is not None:
            _close(J, supplied, 'det(F)와 관측 J')
        J = supplied
    if spec['basis'] == 'isochoric_assumption' and spec['output'] in STRESS_MEASURES:
        _assumption(spec, 'isochoric')
        if J is not None:
            _close(J, 1., '관측 J와 명시한 J=1 가정')
        J = 1.; audit['J_origin'] = 'EXPLICIT_ASSUMPTION_NOT_MEASURED'
    area = None
    if 'area' in operands:
        area = read('area', 'area', 'mm2', {'current_normal_area'})
        number(area, '현재 면적', positive=True)
    if stretch is not None:
        audit.update(stretch=stretch, engineering_strain=stretch-1., log_strain=math.log(stretch))
    if J is not None: audit['J'] = J
    if area is not None: audit['current_area_mm2'] = area
    if spec['output'] in STRAIN_MEASURES:
        if stretch is None: raise ValueError('표점 변형 또는 전체 F가 필요합니다.')
        return audit[spec['output']], audit
    load = operands['load']; measure = load['metadata'].get('measure')
    _metadata(load['metadata'], spec, 'F_axial/응력', measures={'axial_force', *STRESS_MEASURES}, component=component)
    A0 = None
    def reference_area():
        nonlocal A0
        if A0 is None: A0 = geometry(spec, 'A0', 'area', 'mm2'); audit['A0_mm2'] = A0
        return A0
    if measure == 'axial_force':
        raw = convert(load['value'], load['metadata'].get('unit'), 'N', 'force')
        audit['F_axial_N'] = raw
        if spec['output'] == 'finite_Cauchy' and spec['basis'] == 'current_area':
            answer = raw / area
        else:
            answer = raw / reference_area()
            if spec['output'] == 'finite_Cauchy':
                if stretch is None or J is None:
                    raise ValueError('진응력에는 현재 면적 또는 관측 λ와 J/전체 F가 필요합니다. J=1을 추정하지 않습니다.')
                answer *= stretch / J
    else:
        answer = convert(load['value'], load['metadata'].get('unit'), 'MPa', 'stress')
        if measure != spec['output']:
            if spec['basis'] == 'current_area':
                factor = reference_area() / area
            elif stretch is not None and J is not None:
                factor = stretch / J
            else:
                raise ValueError('P↔Cauchy 변환에 현재/초기 면적 또는 관측 λ와 J가 필요합니다.')
            answer *= factor if spec['output'] == 'finite_Cauchy' else 1. / factor
    if spec['basis'] == 'none' and spec['output'] != measure and not (measure == 'axial_force' and spec['output'] == 'first_Piola'):
        raise ValueError('이 응력 측도 변환에는 명시한 면적/J/F 근거가 필요합니다.')
    if area is not None and J is not None:
        if stretch is None:
            raise ValueError('현재 면적의 중복 검증에는 λ와 J를 함께 제공하세요.')
        _close(area, reference_area() * J / stretch, '현재 A와 A0·J/λ')
    answer = convert(number(answer, '변환 응력'), 'MPa', spec['unit'], 'stress')
    audit.update(output=spec['output'], unit=spec['unit'], value=answer)
    return answer, audit


def make_definition(*, output, channels, axis, unit='MPa', basis='none', geometry=None,
                    measurement='', assumptions=None):
    """Draft builder: intentionally does not parse or discard incomplete raw text."""
    return dict(version=1, scope='uniaxial_coaxial', axis=axis, frame=FRAME,
        output=output, unit='1' if output in STRAIN_MEASURES else unit, basis=basis,
        channels=deepcopy(channels), geometry=deepcopy(geometry or {}),
        measurement=measurement, assumptions=deepcopy(assumptions or {}))


def operation(identifier, definition, output):
    from .storage import check_id
    check_id(identifier)
    roles = ['deformation'] if definition.get('output') in STRAIN_MEASURES and 'deformation' in definition.get('channels', {}) else ['Fxx'] if definition.get('output') in STRAIN_MEASURES else ['load']
    return dict(id=identifier, operation=OPERATION, input=definition.get('channels', {}).get(roles[0], ''),
                settings=deepcopy(definition), output=output)
