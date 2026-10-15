"""Coverage and integral checks for the existing native Post field consumer.

Detached arrays only; no solver, interpolator, owner or persistence mechanism.
Interpolation remains nonconservative even when a particular integral passes.
"""
from collections import Counter
from itertools import combinations
import math

import numpy as np


def capabilities():
    return {'consumer': 'post_comparison_v2', 'layouts': ['scalar', 'vector3', 'symmetric_tensor6', 'tensor9'],
            'response_basis': 'explicit_proper_cartesian_rotation',
            'associations': {'POINTS': 'P1', 'CELLS': 'cell_to_point_equal_incident'},
            'spatial': ['same_mesh', 'linear_tetra_b_to_a'], 'conservative_transfer': False,
            'conservation_check': 'same_boundary_linear_tetra_volume_integral',
            'receiver_solver_vector_tensor': 'UNSUPPORTED'}


def policy(recipe):
    """Legacy recipes keep their explicit partial-result/mask behavior."""
    coverage = recipe.get('coverage', {'policy': 'allow_partial', 'array': None})
    if (not isinstance(coverage, dict) or set(coverage) != {'policy', 'array'}
            or coverage['policy'] not in ('allow_partial', 'all_a_points', 'a_mask')):
        raise ValueError('필수 영역은 부분 비교 허용, A 전체 점, A의 점 마스크 중 선택하세요.')
    if coverage['policy'] == 'a_mask':
        if not isinstance(coverage['array'], str) or not coverage['array'].strip():
            raise ValueError('A 원자료의 필수 영역 점 마스크 배열을 선택하세요.')
    elif coverage['array'] is not None:
        raise ValueError('전체 점 또는 부분 비교에는 별도 필수 영역 배열을 지정하지 않습니다.')
    conservation = recipe.get('conservation', {'mode': 'none'})
    if not isinstance(conservation, dict) or conservation.get('mode') not in ('none', 'check_volume_integral'):
        raise ValueError('보존적 전달 알고리즘은 지원하지 않습니다. 보간 후 체적 적분 검사는 별도 선택하세요.')
    if conservation['mode'] == 'none':
        if set(conservation) != {'mode'}:
            raise ValueError('적분 검사를 사용하지 않을 때 허용값을 추정하지 않습니다.')
    else:
        if set(conservation) != {'mode', 'absolute_tolerance', 'relative_tolerance'}:
            raise ValueError('체적 적분의 절대·상대 허용값을 명시하세요.')
        for key in ('absolute_tolerance', 'relative_tolerance'):
            value = conservation[key]
            if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
                raise ValueError('체적 적분의 절대·상대 허용값은 유한한 0 이상의 수입니다.')
        if recipe['a'].get('temperature_kind') == 'absolute':
            raise ValueError('절대온도의 체적 적분은 열량이 아닙니다. 열량에 해당하는 밀도 응답을 선택하세요.')
    return coverage, conservation


def coverage_check(recipe, a, b, inside, required=None):
    coverage, _ = policy(recipe)
    a, b, inside = np.asarray(a), np.asarray(b), np.asarray(inside)
    if a.ndim != 2 or a.shape != b.shape or inside.shape != (len(a),):
        raise ValueError('필수 영역과 실제 공급·수신 성분 배열의 행 수가 다릅니다.')
    if inside.dtype.kind not in 'biuf' or not np.isfinite(inside).all() or not np.isin(inside, [0, 1]).all():
        raise ValueError('공간 유효성에는 각 A 점의 명시적인 0/1 마스크가 필요합니다.')
    if coverage['policy'] == 'a_mask':
        mask = np.asarray(required)
        if (mask.shape != (len(a),) or mask.dtype.kind not in 'biuf'
                or not np.isfinite(mask).all() or not np.isin(mask, [0, 1]).all()):
            raise ValueError('필수 영역 배열은 원 A의 모든 점에 대응하는 유한한 0/1 마스크여야 합니다.')
        required = mask.astype(bool)
        if not required.any():
            raise ValueError('필수 영역이 비었습니다. A의 필수 점을 하나 이상 지정하세요.')
    else:
        required = np.full(len(a), coverage['policy'] == 'all_a_points', dtype=bool)
    valid = inside.astype(bool) & np.isfinite(a).all(axis=1) & np.isfinite(b).all(axis=1)
    invalid = np.flatnonzero(required & ~valid).tolist()
    result = {'policy': coverage, 'required_count': int(required.sum()),
              'valid_count': int(valid.sum()), 'invalid_required_rows': invalid,
              'conservative_transfer': False}
    if invalid:
        raise ValueError('필수 비교 영역에 공급/수신 값이 없는 점 ' + str(len(invalid))
                         + '개가 있습니다(A 행 ' + ', '.join(map(str, invalid[:12]))
                         + '). 원자료·범위·유효성 마스크를 확인하세요. 적용하지 않았습니다.')
    return result


def tetra_geometry(points, cells):
    """Exact boundary correspondence permits different interior tetra meshes.

    This deliberately does not infer equal domains from volume/bounds alone.
    Different boundary triangulations remain outside this integral check.
    """
    points = np.asarray(points, dtype=float)
    cells = np.asarray(cells)
    if (points.ndim != 2 or points.shape[1] != 3 or not np.isfinite(points).all()
            or cells.ndim != 2 or cells.shape[1] != 4 or cells.dtype.kind not in 'iu'
            or not len(cells) or np.any(cells < 0) or np.any(cells >= len(points))):
        raise ValueError('체적 적분 검사는 유한한 좌표와 실제 선형 사면체 연결이 필요합니다.')
    if any(len(set(cell)) != 4 for cell in cells.tolist()) or len({tuple(sorted(c)) for c in cells.tolist()}) != len(cells):
        raise ValueError('중복·퇴화 사면체는 체적 적분에 사용할 수 없습니다.')
    xyz = points[cells]
    volumes = np.abs(np.linalg.det(xyz[:, 1:] - xyz[:, :1])) / 6.
    if not np.isfinite(volumes).all() or np.any(volumes <= 0):
        raise ValueError('체적이 0이거나 비유한 사면체가 있습니다.')
    faces = Counter(tuple(sorted(face)) for c in cells.tolist() for face in combinations(c, 3))
    if any(count > 2 for count in faces.values()):
        raise ValueError('비다양체 사면체 연결은 적분 검사에서 지원하지 않습니다.')
    boundary = sorted(tuple(sorted(tuple(float(v) for v in points[i]) for i in face))
                      for face, count in faces.items() if count == 1)
    return cells, volumes, boundary


def volume_integral(points, cells, values, *, association='POINTS'):
    cells, volumes, boundary = tetra_geometry(points, cells)
    values = np.asarray(values, dtype=float)
    expected = len(points) if association == 'POINTS' else len(cells)
    if association not in ('POINTS', 'CELLS') or values.ndim != 2 or len(values) != expected or not np.isfinite(values).all():
        raise ValueError('전체 적분 영역의 모든 원 성분이 유효해야 합니다. 부분 영역의 보존은 미확인입니다.')
    means = values[cells].mean(axis=1) if association == 'POINTS' else values
    integral = (means * volumes[:, None]).sum(axis=0)
    if not np.isfinite(integral).all():
        raise ValueError('체적 적분이 수치 범위를 넘습니다.')
    return integral, float(volumes.sum()), boundary


def conservation_check(recipe, source_points, source_cells, source_values,
                       receiver_points, receiver_cells, receiver_values, *, source_association='POINTS'):
    _, check = policy(recipe)
    if check['mode'] == 'none':
        return {'mode': 'none', 'status': 'NOT_REQUESTED', 'conservative_transfer': False}
    source, source_volume, source_boundary = volume_integral(source_points, source_cells, source_values,
                                                            association=source_association)
    receiver, receiver_volume, receiver_boundary = volume_integral(receiver_points, receiver_cells, receiver_values)
    if source_boundary != receiver_boundary:
        raise ValueError('적분 영역의 실제 경계 삼각형이 다릅니다. 부분 중첩/다른 경계 분할의 보존은 미확인이므로 적용하지 않습니다.')
    # Boundary identity alone cannot validate a multiply covered interior.
    if not math.isclose(source_volume, receiver_volume, rel_tol=1e-12, abs_tol=0.):
        raise ValueError('같은 경계 안의 실제 사면체 체적 합이 다릅니다. 중복·누락 셀을 확인하세요.')
    if source.shape != receiver.shape:
        raise ValueError('원 공급과 수신 적분의 실제 성분 수가 다릅니다.')
    error = np.abs(receiver - source)
    limits = check['absolute_tolerance'] + check['relative_tolerance'] * np.maximum(np.abs(source), np.abs(receiver))
    if not np.isfinite(limits).all():
        raise ValueError('보존 검사 허용값이 수치 범위를 넘습니다.')
    result = {'mode': check['mode'], 'status': 'PASS' if np.all(error <= limits) else 'FAILED',
              'source_integral': source.tolist(), 'receiver_integral': receiver.tolist(),
              'absolute_error': error.tolist(), 'limits': limits.tolist(),
              'integral_units': recipe['target']['units'] + ' * ' + recipe['a']['coordinate_units'] + '^3',
              'source_volume': source_volume, 'receiver_volume': receiver_volume,
              'domain_correspondence': 'EXACT_BOUNDARY_TRIANGLES', 'conservative_transfer': False}
    if result['status'] != 'PASS':
        raise ValueError('보간 후 체적 적분 오차가 허용값을 넘습니다. 오차 '
                         + str(result['absolute_error']) + ' / 허용값 ' + str(result['limits'])
                         + ' [' + result['integral_units'] + ']. 보존적 전달로 대체하지 않았습니다.')
    return result
