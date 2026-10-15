"""Strict same-clock/location admission of retained small-strain tensor channels.

Only six explicitly supplied independent symmetric components are accepted for
critical-plane work. Scalar axial CMB has a separate, narrower requirement.
Input descriptors/bytes are never edited, completed, aligned or interpolated.
"""
from __future__ import annotations

from copy import deepcopy
import math
import numpy as np

from .storage import canonical_hash
from .fatigue_life import number

COMPONENTS = ('xx', 'yy', 'zz', 'xy', 'yz', 'xz')
KNOWN_MODEL_FRAMES = (
    'Tridimensional model component basis; sensor/world alignment UNKNOWN',
    'global Cartesian model; sensor/world alignment UNKNOWN',
)
STRAIN_MEASURES = {'infinitesimal_total_strain_tensor': 'TENSOR',
                   'infinitesimal_total_strain_engineering_shear': 'ENGINEERING',
                   'infinitesimal_total_strain': None,
                   'engineering_total_axial_strain': None}
STRESS_MEASURES = ('infinitesimal_Cauchy', 'Cauchy_stress', 'cauchy_stress')
MAX_SAMPLES = 100_000


def canonical_component(value):
    aliases = {'11': 'xx', '22': 'yy', '33': 'zz', '12': 'xy', '21': 'xy',
               '23': 'yz', '32': 'yz', '13': 'xz', '31': 'xz',
               'yx': 'xy', 'zy': 'yz', 'zx': 'xz'}
    if isinstance(value, str) and value.startswith('SIEF_ELGA.SI'):
        value = value[len('SIEF_ELGA.SI'):].lower()
    return aliases.get(value, value)


def validate_source(source, *, method, mean_stress):
    from .research_operations import validate_result_reference
    if not isinstance(source, dict) or set(source) != {'result', 'channels', 'title'}:
        raise ValueError('저장된 같은 결과의 tensor 채널과 제목을 선택하세요')
    validate_result_reference(source['result'])
    if not isinstance(source['title'], str):
        raise ValueError('보존 이력 제목이 필요합니다')
    channels = source['channels']
    roles = {'strain', 'stress'} if mean_stress == 'SWT' else {'strain'}
    if not isinstance(channels, dict) or not roles <= set(channels) or set(channels) - {'strain', 'stress'}:
        raise ValueError('선택 방법의 total strain/stress 채널이 부족합니다')
    selected = []
    for role in roles:
        group = channels[role]
        keys = set(COMPONENTS) if method == 'CP_SWT' else None
        if (not isinstance(group, dict) or (keys is not None and set(group) != keys) or
                (keys is None and (len(group) != 1 or next(iter(group)) not in COMPONENTS[:3]))):
            raise ValueError('critical plane은 6개 전체 tensor 성분, 단축은 정상 성분 하나가 필요합니다')
        for component, selector in group.items():
            if not isinstance(selector, str) or not selector or len(selector) > 2048:
                raise ValueError(role + '/' + component + '의 정확한 저장 채널을 선택하세요')
            selected.append(selector)
    if mean_stress == 'SWT' and set(channels['strain']) != set(channels['stress']):
        raise ValueError('stress와 strain의 성분 방향이 다릅니다')
    if len(selected) != len(set(selected)):
        raise ValueError('하나의 보존 채널을 서로 다른 tensor 성분으로 재사용할 수 없습니다')
    return selected


def read_bundle(provider, source, *, method, mean_stress):
    """Trust boundary reused by service and dialog; no private draft payload."""
    from .research_operations import _resolve
    selectors = validate_source(source, method=method, mean_stress=mean_stress)
    ref = source['result']
    before = _resolve(ref, provider.document_read, provider.document_result)
    if (before.get('execution_status') != 'SUCCEEDED' or before.get('prediction_status') or
            'candidates' in before or before.get('diagnostics', {}).get('mode') in ('PREDICTED', 'SURROGATE')):
        raise ValueError('성공한 실제 이력만 사용합니다. 예측/후보/집계 결과는 tensor 이력이 아닙니다')
    detached = provider.document_result(ref['document_id'], ref['job_id'], selection=selectors)
    if detached.get('execution_status') != 'SUCCEEDED' or detached.get('prediction_status') or 'candidates' in detached:
        raise ValueError('선택한 보존 이력의 실행 상태가 다릅니다')
    responses = detached.get('responses', {})
    if set(responses) != set(selectors):
        raise ValueError('요청한 tensor 채널과 reader 반환 채널이 다릅니다')
    _resolve(ref, provider.document_read, provider.document_result)
    return {'responses': deepcopy(responses), 'source': deepcopy(source),
            'source_result_sha256': ref['result_sha256'], 'origin': 'EXACT_RETAINED_RESULT'}


def _frame(response):
    frame, coordinate = response.get('frame'), response.get('coordinate_frame')
    if frame is not None and coordinate is not None and frame != coordinate:
        raise ValueError('원 tensor의 두 기준계 선언이 다릅니다')
    frame = frame if frame is not None else coordinate
    if not isinstance(frame, str) or not frame.strip():
        raise ValueError('tensor의 고정 모델 기준계가 필요합니다')
    unknown_external = frame in KNOWN_MODEL_FRAMES
    if not unknown_external and any(word in frame.casefold() for word in ('unknown', 'rotating', 'corotat', 'time-dependent', 'unspecified', '미확인', '미정', '알 수 없', '회전')):
        raise ValueError('tensor component basis가 미확인 또는 회전 기준계입니다')
    for key in ('frame_is_fixed', 'basis_is_fixed'):
        if key in response and response[key] is not True:
            raise ValueError('고정된 물리 기준계의 tensor만 지원합니다')
    basis = response.get('basis')
    if basis is not None:
        orthogonal_basis(basis)
    return frame, ('UNKNOWN' if unknown_external else 'NOT_REQUESTED'), deepcopy(basis)


def _native_interpretation(response, role, component):
    """Recognize only exact known declarations, preserving the source descriptor."""
    measure = response.get('measure')
    origin = response.get('source', {})
    if not isinstance(origin, dict):
        raise ValueError('native tensor 출처 선언이 손상되었습니다')
    backend = origin.get('backend')
    native = origin.get('native_origin', {})
    if not isinstance(native, dict):
        raise ValueError('native tensor 원채널 선언이 손상되었습니다')
    mapped = 'DECLARED_RESPONSE'
    if backend in ('material.mfront', 'material.mfront.viscoelastic'):
        expected = ('infinitesimal Cauchy stress; physical tensor components' if backend == 'material.mfront'
                    else 'infinitesimal Cauchy stress')
        if (role == 'stress' and response.get('quantity') == 'stress' and measure == expected and
                native.get('native_field') == 'stress_physical_mpa' and
                response.get('coordinate_frame') == KNOWN_MODEL_FRAMES[0]):
            measure, mapped = 'infinitesimal_Cauchy', 'RETAINED_NATIVE_PHYSICAL_CAUCHY'
    if backend == 'structural.code_aster.plasticity':
        selection = origin.get('exact_selection', {})
        if (role == 'stress' and response.get('quantity') == 'stress' and
                measure == 'small-strain Cauchy stress at native Gauss point' and
                response.get('coordinate_frame') == KNOWN_MODEL_FRAMES[1] and
                isinstance(selection, dict) and selection.get('kind') == 'fe_gauss' and
                selection.get('component') == response.get('component') and
                all(type(selection.get(k)) is int and selection[k] > 0 for k in ('element_id', 'point', 'subpoint'))):
            measure, mapped = 'infinitesimal_Cauchy', 'RETAINED_NATIVE_EXACT_GAUSS_CAUCHY'
    return measure, mapped


def channel_history(response, *, role, component, strain_shear, tensor_required):
    if not isinstance(response, dict) or response.get('kind') != 'series':
        raise ValueError('공간집계가 아닌 한 위치의 원 tensor 성분 시간 이력이 필요합니다')
    if canonical_component(response.get('component')) != component:
        raise ValueError('선택된 채널의 실제 tensor 성분과 지정 방향이 다릅니다')
    if response.get('reduction', 'none') not in ('none', 'NONE', None):
        raise ValueError('집계/최대값/평균 tensor는 exact location 이력으로 사용하지 않습니다')
    origin = response.get('source', {})
    if isinstance(origin, dict) and origin.get('value_origin') in ('PREDICTED', 'DERIVED', 'SURROGATE'):
        raise ValueError('예측 또는 파생 응력/변형률을 원 tensor로 바꾸어 계산하지 않습니다')
    if response.get('prediction_status') or response.get('is_prediction') or response.get('derived_from_stress'):
        raise ValueError('σ/E나 예측값을 실제 plastic total strain으로 대체할 수 없습니다')
    quantity = response.get('quantity')
    allowed = ('strain', 'total_strain') if role == 'strain' else ('stress',)
    if quantity is not None and quantity not in allowed:
        raise ValueError('원 물리량 선언과 선택 stress/total strain 역할이 다릅니다')
    measure, mapping = _native_interpretation(response, role, component)
    if role == 'strain':
        if measure not in STRAIN_MEASURES:
            raise ValueError('명시 total infinitesimal strain이 필요합니다. plastic-only/finite/PK 측도를 바꾸지 않습니다')
        convention = STRAIN_MEASURES[measure]
        if tensor_required and convention is None:
            raise ValueError('원 Data에서 tensor 또는 engineering total shear를 명시하세요')
        if (tensor_required or component in COMPONENTS[3:]) and convention is not None and convention != strain_shear:
            raise ValueError('원 strain shear 의미와 선택 변환이 다릅니다. γ/2 이중 변환을 차단했습니다')
        if response.get('unit') not in ('1', '%'):
            raise ValueError('total strain 단위는 1 또는 %여야 합니다')
        factor = .01 if response['unit'] == '%' else 1.0
        if component in COMPONENTS[3:] and convention == 'ENGINEERING':
            factor *= .5
    else:
        if measure not in STRESS_MEASURES:
            raise ValueError('미소변형과 동시 Cauchy stress만 지원합니다. PK1/공칭/등가응력은 거절합니다')
        if response.get('unit') not in ('Pa', 'MPa'):
            raise ValueError('stress 단위는 Pa 또는 MPa여야 합니다')
        if response.get('shear_convention') not in (None, 'TENSOR', 'tensor'):
            raise ValueError('물리 응력 tensor shear가 필요합니다. Kelvin/Mandel 변환을 추정하지 않습니다')
        factor = 1e-6 if response['unit'] == 'Pa' else 1.0
    frame, external, basis = _frame(response)
    location = response.get('location')
    if not isinstance(location, (str, dict)) or not location:
        raise ValueError('정확한 동일 위치(요소/적분점/층/면 또는 명시 시험점)가 필요합니다')
    location_text = str(location).casefold()
    if any(token in location_text for token in ('unknown', 'unspecified', '미정', '미확인')) or (
            isinstance(location, dict) and any(v is None or v == '' for v in location.values())):
        raise ValueError('선택한 원 위치가 미확인입니다. 같은 exact location을 명시하세요')
    spatial = origin.get('exact_selection') if isinstance(origin, dict) else None
    if isinstance(spatial, dict):
        spatial = {k: deepcopy(v) for k, v in spatial.items() if k != 'component'}
    axes, values = response.get('axes'), response.get('value')
    if (not isinstance(values, list) or not 3 <= len(values) <= MAX_SAMPLES or
            not isinstance(axes, list) or len(axes) != 1 or not isinstance(axes[0], dict)):
        raise ValueError('3..100000 원 표본과 한 물리 시간축이 필요합니다')
    axis = axes[0]
    times = axis.get('values')
    if (axis.get('name') != 'time' or axis.get('unit') != 's' or
            not isinstance(times, list) or len(times) != len(values)):
        raise ValueError('같은 실제 time [s] 표본이 필요합니다. index/load factor는 시간이 아닙니다')
    semantics = str(axis.get('semantics', '')).upper()
    if any(token in semantics for token in ('PSEUDO', 'LOAD_FACTOR', 'INDEX', 'ARC_LENGTH')):
        raise ValueError('선언된 시간축이 실제 물리 clock이 아닙니다')
    ts = [number(t, '원 시간') for t in times]
    vals = [number(v, '원 tensor 성분') * factor for v in values]
    if not all(math.isfinite(v) for v in vals) or any(b <= a for a, b in zip(ts, ts[1:])):
        raise ValueError('유한 값과 엄격히 증가하는 원 물리 시간이 필요합니다')
    if response.get('has_calculation_gaps') or len(response.get('segments', [])) > 1:
        raise ValueError('gap을 넘어 tensor 사이클을 만들 수 없습니다')
    mask = response.get('mask')
    if mask is not None and (not isinstance(mask, list) or len(mask) != len(vals) or any(v is not True for v in mask)):
        raise ValueError('무효/제외 mask 또는 mask 길이가 손상되었습니다')
    raw = response.get('raw_samples', {})
    if not isinstance(raw, dict):
        raise ValueError('원 표본 품질 선언이 손상되었습니다')
    for key in ('quality_valid', 'calculation_valid', 'finite'):
        if key in raw:
            flags = raw[key]
            if not isinstance(flags, list) or len(flags) != len(vals) or any(v is not True for v in flags):
                raise ValueError('원 이력에 무효/제외 행 또는 품질 길이 불일치가 있습니다')
    rows = response.get('source_rows', list(range(len(vals))))
    if (not isinstance(rows, list) or len(rows) != len(vals) or
            any(type(r) is not int or r < 0 for r in rows) or any(b <= a for a, b in zip(rows, rows[1:]))):
        raise ValueError('원행 배열의 순서/길이가 손상되었습니다')
    sample_ids = response.get('sample_ids', rows)
    if (not isinstance(sample_ids, list) or len(sample_ids) != len(vals) or
            any(type(v) not in (int, str) or v == '' for v in sample_ids) or len(set(sample_ids)) != len(sample_ids)):
        raise ValueError('동시 원 sample identity 길이가 다릅니다')
    return {'values': vals, 'times': ts, 'rows': deepcopy(rows), 'sample_ids': deepcopy(sample_ids),
            'row_kind': response.get('source_row_kind', 'retained_sample_index'),
            'frame': frame, 'basis': basis, 'external_alignment': external,
            'location': deepcopy(location), 'native_spatial_selection': spatial,
            'clock_id': axis.get('clock_id'), 'clock_semantics': axis.get('semantics'),
            'measure': measure, 'interpretation': mapping, 'factor_to_internal': factor,
            'component': component, 'unit': '1' if role == 'strain' else 'MPa',
            'source_response_sha256': canonical_hash(response)}


def admit_bundle(bundle, settings):
    source = settings['source']
    selectors = validate_source(source, method=settings['method'], mean_stress=settings['mean_stress'])
    if (not isinstance(bundle, dict) or bundle.get('source') != source or
            bundle.get('source_result_sha256') != source['result']['result_sha256'] or
            bundle.get('origin') != 'EXACT_RETAINED_RESULT' or
            set(bundle.get('responses', {})) != set(selectors)):
        raise ValueError('신뢰된 exact retained source bundle이 필요합니다. draft payload는 허용하지 않습니다')
    roles = ('strain', 'stress') if settings['mean_stress'] == 'SWT' else ('strain',)
    tensor = settings['method'] == 'CP_SWT'
    admitted, reference = {}, None
    for role in roles:
        admitted[role] = {}
        for component, selector in source['channels'][role].items():
            row = channel_history(bundle['responses'][selector], role=role, component=component,
                                  strain_shear=settings['interpretation']['strain_shear'], tensor_required=tensor)
            if reference is None:
                reference = row
            else:
                for key in ('times', 'rows', 'sample_ids', 'row_kind', 'frame', 'basis', 'location',
                            'native_spatial_selection', 'clock_id', 'clock_semantics'):
                    if row[key] != reference[key]:
                        raise ValueError('동시 tensor ' + key + ' 불일치: 자동 정렬/보간/최근접 위치는 사용하지 않습니다')
            admitted[role][component] = row
    order = COMPONENTS if tensor else tuple(source['channels']['strain'])
    strain = np.array([admitted['strain'][k]['values'] for k in order], dtype=float).T
    stress = (np.array([admitted['stress'][k]['values'] for k in order], dtype=float).T
              if 'stress' in admitted else None)
    return {'strain': strain, 'stress': stress, 'times': reference['times'], 'source_rows': reference['rows'],
            'sample_ids': reference['sample_ids'], 'row_kind': reference['row_kind'],
            'location': reference['location'], 'frame': reference['frame'],
            'external_alignment': reference['external_alignment'],
            'components': list(order), 'channels': {role: {c: {k: v for k, v in r.items()
                if k not in ('values', 'times', 'rows', 'sample_ids')} for c, r in entries.items()}
                for role, entries in admitted.items()}}


def orthogonal_basis(value):
    try:
        matrix = np.asarray(value, dtype=float)
    except (ValueError, TypeError) as error:
        raise ValueError('검색기저는 명시한 3×3 고정 직교행렬이어야 합니다') from error
    if (matrix.shape != (3, 3) or not np.isfinite(matrix).all() or
            not np.allclose(matrix.T @ matrix, np.eye(3), rtol=0, atol=1e-12) or
            abs(float(np.linalg.det(matrix)) - 1) > 1e-12):
        raise ValueError('검색기저는 det=+1인 3×3 직교행렬이어야 합니다')
    return matrix


def plane_grid(polar_steps, basis):
    """Hemisphere: antipodal normals are a single unoriented physical plane."""
    matrix = orthogonal_basis(basis)
    normals = []
    for j in range(polar_steps + 1):
        theta = math.pi * j / (2 * polar_steps)
        count = 1 if j == 0 else (2 * polar_steps if j == polar_steps else 4 * polar_steps)
        for k in range(count):
            phi = math.pi * k / (2 * polar_steps)
            local = np.array([math.sin(theta) * math.cos(phi), math.sin(theta) * math.sin(phi), math.cos(theta)])
            # Exact coordinate planes should remain exact, not tiny spurious cycles.
            local[np.abs(local) < 1e-15] = 0.
            local /= np.linalg.norm(local)
            normals.append({'normal_search': local.tolist(), 'normal_model': (matrix @ local).tolist(),
                            'theta_deg': math.degrees(theta), 'phi_deg': math.degrees(phi)})
    return normals


def project(tensor6, normal):
    n = np.asarray(normal, dtype=float)
    if n.shape != (3,) or not np.isfinite(n).all() or abs(float(n @ n) - 1) > 1e-12:
        raise ValueError('unit plane normal이 필요합니다')
    weights = [n[0]**2, n[1]**2, n[2]**2, 2*n[0]*n[1], 2*n[1]*n[2], 2*n[0]*n[2]]
    return np.asarray(tensor6, dtype=float) @ np.array(weights)
