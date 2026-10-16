"""Declared finite strain tensors to material Green–Lagrange endpoints only.

No field, frame, precision, missing value or deformation is inferred here.
Native adapters call this before association projection and time interpolation.
"""
from copy import deepcopy
import numpy as np

MEASURES = ('green_lagrange', 'euler_almansi', 'material_hencky')
LABELS = {'green_lagrange': 'Green–Lagrange 변형률', 'euler_almansi': 'Euler–Almansi 변형률',
          'material_hencky': '기준 기저 Hencky 변형률'}


def enabled(recipe):
    if 'strain_conversion' not in recipe:
        return False
    if recipe['strain_conversion'] != {'version': 1, 'target_measure': 'green_lagrange'}:
        raise ValueError('변형률 변환의 공통 출력은 Green–Lagrange E입니다.')
    if 'stress_conversion' in recipe:
        raise ValueError('응력 변환과 변형률 변환을 같은 비교에 함께 지정할 수 없습니다.')
    return True


def precision(side, *, required=False):
    from .post_comparison import number
    value = side.get('strain_precision')
    if value is None and not required:
        return None
    if (not isinstance(value, dict) or set(value) != {'kind', 'absolute_tolerance', 'relative_tolerance', 'producer', 'format', 'reference'}
            or value['kind'] != 'declared_C_bound'):
        raise ValueError('원 출력 정밀도에 근거한 변형률 정합 허용값과 출처를 명시하세요.')
    a = number(value['absolute_tolerance'], '정합 절대 허용값 [1]')
    r = number(value['relative_tolerance'], '정합 상대 허용값 [1]')
    if a < 0 or r < 0 or any(not isinstance(value[k], str) or not value[k].strip() for k in ('producer', 'format', 'reference')):
        raise ValueError('정합 허용값은 음수가 아니어야 하며 원 출력 정밀도 출처가 필요합니다.')
    return a, r


def validate_side(side):
    from . import post_comparison as p
    measure = side.get('measure')
    if side.get('quantity') != 'strain' or measure not in MEASURES:
        raise ValueError('Green–Lagrange / Euler–Almansi / 기준 기저 Hencky 전체 변형률을 선택하세요. 소변형·공간 Hencky·스칼라를 승격하지 않습니다.')
    if side.get('strain_role') != 'total':
        raise ValueError('같은 전체 변형의 total strain만 지원합니다. 탄성·소성·미확인 변형률을 total F와 섞지 마세요.')
    if not isinstance(side.get('reference_configuration'), str) or side['reference_configuration'].strip().upper() in ('', 'UNKNOWN', 'UNSPECIFIED'):
        raise ValueError('전체 변형률의 원 기준 배치를 명시하세요.')
    layout = side.get('layout') or {}
    if (layout.get('kind') != 'tensor' or p.layout_size(layout) not in (6, 9)
            or layout.get('indices') != 'same_cartesian_basis'):
        raise ValueError('변형률은 같은 직교 기저의 대칭 전체 텐서와 실제 전단 규약이 필요합니다.')
    if side.get('units') not in ('1', '%'):
        raise ValueError('변형률 단위는 명시한 무차원 [1] 또는 [%]여야 합니다.')
    if not isinstance(side.get('frame'), str) or side['frame'].strip().upper() in ('', 'UNKNOWN', 'UNSPECIFIED'):
        raise ValueError('원 변형률의 기준 또는 현재 기저 이름을 확인하세요.')
    if measure == 'euler_almansi' or side.get('deformation_gradient') is not None:
        precision(side, required=True)
        gradient = p.validate_deformation_gradient(side)
        expected = gradient['spatial_frame'] if measure == 'euler_almansi' else gradient['material_frame']
        if side['frame'] != expected:
            raise ValueError('원 변형률과 F의 현재·기준 기저가 일치하지 않습니다.')
    return measure


def effective_side(side, recipe):
    from .post_comparison import COMPONENTS
    measure = validate_side(side)
    result = deepcopy(side)
    result.update(measure='green_lagrange', units=recipe['target']['units'],
        frame=side['deformation_gradient']['material_frame'] if measure == 'euler_almansi' else side['frame'],
        layout={'kind': 'tensor', 'components': list(COMPONENTS), 'shear': 'tensor', 'indices': 'same_cartesian_basis'})
    return result


def _close(a, b, absolute, relative):
    # Declared bounds refer to the material C tensor's Frobenius norm, not
    # pointwise epsilon or an adjustable symmetry tolerance.
    with np.errstate(over='ignore', invalid='ignore'):
        residual = _norm(a-b)
        limit = absolute + relative * np.maximum(_norm(a), _norm(b))
    return np.isfinite(residual) & np.isfinite(limit) & (residual <= limit)


def _norm(value):
    return np.hypot.reduce(np.abs(value).reshape((-1, 9)), axis=1)


def to_green_lagrange(values, side, gradient=None, *, target_unit):
    from . import post_comparison as p
    from .experiment_calibration import factor
    measure = validate_side(side)
    if target_unit not in ('1', '%'):
        raise ValueError('공통 변형률 단위 [1] 또는 [%]를 선택하세요.')
    raw = p.canonical(values, side['layout']).reshape((-1, 3, 3)) * factor(side['units'], '1')
    valid = np.isfinite(raw).all(axis=(1, 2))
    bounds = precision(side, required=True) if measure == 'euler_almansi' or side.get('deformation_gradient') is not None else None
    # Absent declared export error, only floating arithmetic roundoff is allowed.
    # This is not a numerical/engineering accuracy tolerance.
    strain = raw[valid]
    roundoff = 32 * np.finfo(float).eps * np.maximum(1., _norm(strain))
    residual = _norm(strain-strain.transpose(0,2,1))
    if not np.isfinite(roundoff).all() or not np.isfinite(residual).all() or np.any(residual > roundoff):
        raise ValueError('원 변형률 텐서가 산술 반올림 범위에서 대칭이 아닙니다. 원 성분을 확인하세요.')
    # Only accepted roundoff asymmetry is removed for a symmetric eigensolve;
    # the untouched source tuples remain in the native ORIGINAL arrays.
    strain = (strain + strain.transpose(0, 2, 1)) / 2
    if measure == 'euler_almansi' and np.any(np.linalg.eigvalsh(np.eye(3)-2*strain) <= 0):
        raise ValueError('Euler–Almansi의 I−2e는 양의 정부호여야 합니다. 정합 허용값으로 보정하지 않습니다.')
    f = None
    if measure == 'euler_almansi' or side.get('deformation_gradient') is not None:
        if gradient is None:
            raise ValueError('같은 원 시각·점/셀의 실제 F 배열이 없습니다. 원 결과는 유지됩니다.')
        f = p.canonical(gradient, side['deformation_gradient']['layout']).reshape((-1, 3, 3))
        if len(f) != len(raw):
            raise ValueError('F와 변형률의 원 표본 수가 다릅니다.')
        f = f[valid]
        if not np.isfinite(f).all():
            raise ValueError('유효 변형률 표본의 F가 유한하지 않습니다.')
        j = np.linalg.det(f)
        if not np.isfinite(j).all() or np.any(j <= 0):
            raise ValueError('유효 표본 det(F)는 유한한 양수여야 합니다. 보정하지 않습니다.')
    with np.errstate(over='ignore', invalid='ignore', under='ignore'):
        if measure == 'green_lagrange':
            result = strain
        elif measure == 'euler_almansi':
            result = f.transpose(0, 2, 1) @ strain @ f
        else:
            eigenvalues, vectors = np.linalg.eigh(strain)
            stretches2 = np.exp(2 * eigenvalues)
            if not np.isfinite(stretches2).all() or np.any(stretches2 <= 0):
                raise ValueError('Hencky 지수 변환의 양의 stretch를 유한하게 확인할 수 없습니다.')
            result = (vectors * np.expm1(2 * eigenvalues)[:, None, :]) @ vectors.transpose(0, 2, 1) / 2
        c = ((vectors * stretches2[:, None, :]) @ vectors.transpose(0, 2, 1)
             if measure == 'material_hencky' else 2 * result + np.eye(3))
    if not np.isfinite(c).all() or np.any(np.linalg.eigvalsh(c) <= 0):
        raise ValueError('I+2E는 양의 정부호 C여야 합니다. 음수 stretch를 보정하지 않습니다.')
    if f is not None:
        absolute, relative = bounds
        cf = f.transpose(0, 2, 1) @ f
        if not np.isfinite(cf).all() or not _close(c, cf, absolute, relative).all():
            raise ValueError('변형률의 C와 FᵀF가 원 출력 정밀도 내에서 일치하지 않습니다. 측도·기저·시각·원 성분을 확인하세요.')
    output = np.full(raw.shape, np.nan)
    with np.errstate(over='ignore', invalid='ignore'):
        output[valid] = result * factor('1', target_unit)
    if not np.isfinite(output[valid]).all():
        raise ValueError('공통 변형률의 단위 변환 결과가 유한하지 않습니다.')
    return output.reshape((-1, 9))


def validate_gradient_declaration(side, metadata):
    from .post_comparison import validate_gradient_metadata
    validate_side(side)
    if metadata is not None:
        row = next((r for r in metadata.get('arrays', [])
                    if (r.get('name'), r.get('association')) == (side['array'], side['association'])), {})
        for key in ('strain_role', 'reference_configuration', 'strain_precision'):
            if row.get(key) is not None and row[key] != side.get(key):
                raise ValueError('변형률 ' + key + '가 저장된 원 선언과 다릅니다.')
    if side.get('deformation_gradient') is not None and metadata is not None:
        validate_gradient_metadata(side['deformation_gradient'], metadata)


def provenance(recipe):
    return {'version': 1, 'target_measure': 'green_lagrange',
        'order': 'native_endpoint_before_association_and_time',
        'sides': {name: {'source_measure': recipe[name]['measure'], 'strain_role': 'total',
            'reference_configuration': recipe[name]['reference_configuration'],
            'F_checked': recipe[name].get('deformation_gradient') is not None,
            'C_consistency_bound': deepcopy(recipe[name].get('strain_precision')),
            'bound_authority': 'user_declared_producer_evidence; not native-verified'} for name in ('a', 'b')}}
