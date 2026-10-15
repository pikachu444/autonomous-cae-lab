"""Exact retained DAT wrench projection; no integration of nodal projections.

Rows of basis_rows are the local unit axes expressed in document-global axes.
reference_point_mm is a document-global point, never an undeclared local point.
The DAT source is force-on-slave A only; a requested B/both side is not inferred.
"""
from copy import deepcopy
import math
from .contact import number

IDENTITY = [[1., 0., 0.], [0., 1., 0.], [0., 0., 1.]]


def cross(a, b):
    return [a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]]


def vector(value, label):
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise ValueError(label + ': 유한한 세 성분을 입력하세요.')
    return [number(v) for v in value]


def selection(value=None):
    if value is None:
        value = {'response': 'force', 'side': 'a', 'reference_point_mm': [0., 0., 0.],
                 'basis_rows': IDENTITY, 'frame_label': '문서 전체 좌표계'}
    if not isinstance(value, dict) or set(value) != {
            'response', 'side', 'reference_point_mm', 'basis_rows', 'frame_label'}:
        raise ValueError('합력/모멘트, A면, 기준점과 좌표축을 모두 명시하세요.')
    if value['response'] not in ('force', 'moment') or value['side'] != 'a':
        raise ValueError('DAT_RESULTANT_SIDE: 저장된 DAT 합력은 A면에 작용하는 값입니다. B면 또는 양면 합산을 추정하지 않습니다.')
    r = vector(value['reference_point_mm'], '기준점 [mm]')
    basis = value['basis_rows']
    if not isinstance(basis, list) or len(basis) != 3:
        raise ValueError('좌표계에는 X/Y/Z 세 축이 필요합니다.')
    q = [vector(row, '좌표축') for row in basis]
    for i in range(3):
        for j in range(3):
            if not math.isclose(math.fsum(q[i][k]*q[j][k] for k in range(3)), float(i == j), abs_tol=1e-10, rel_tol=0):
                raise ValueError('좌표축은 서로 직교하는 단위벡터여야 합니다. 자동 정규화하지 않습니다.')
    if not math.isclose(math.fsum(q[2][k]*cross(q[0], q[1])[k] for k in range(3)), 1., abs_tol=1e-10, rel_tol=0):
        raise ValueError('좌표계는 오른손 좌표계여야 합니다. 반사 좌표계는 허용하지 않습니다.')
    label = value['frame_label']
    if not isinstance(label, str) or not label.strip() or len(label) > 160:
        raise ValueError('좌표계 이름을 입력하세요.')
    return {**deepcopy(value), 'reference_point_mm': r, 'basis_rows': q}


def coefficients(spec, component):
    # A linear expression over [Fx,Fy,Fz,Mx,My,Mz] is used so a missing
    # mathematically unused component does not erase an otherwise valid scalar.
    row = spec['basis_rows'][component]
    if spec['response'] == 'force':
        return row + [0., 0., 0.]
    return cross(spec['reference_point_mm'], row) + row


def project(raw, spec, component):
    coeff = coefficients(spec, component)
    if raw is None:
        return None, 'NOT_PRODUCED'
    if raw.get('association') != 'contact_pair_resultant' or raw.get('basis') != 'FREECAD_DOCUMENT_GLOBAL':
        return None, 'UNKNOWN_ASSOCIATION'
    force, moment = raw.get('force_N'), raw.get('moment_origin_Nmm')
    if not isinstance(force, list) or len(force) != 3:
        return None, 'UNSUPPORTED_READER'
    # Moment is not required when the selected scalar does not depend on it.
    if not isinstance(moment, list) or len(moment) != 3:
        moment = [None] * 3
    values = force + moment
    terms = []
    for c, v in zip(coeff, values):
        if c == 0:
            continue
        if type(v) not in (float, int) or not math.isfinite(v):
            return None, 'NATIVE_NONFINITE_OR_MISSING_COMPONENT'
        terms.append(c*v)
    try:
        value = math.fsum(terms)
    except (OverflowError, ValueError):
        return None, 'TRANSFORM_NONFINITE'
    return (value, None) if math.isfinite(value) else (None, 'TRANSFORM_NONFINITE')


def history(bundle, pair_id, quantity, component, resultant=None, *, frame_indices=None):
    from .contact_inspection import bundle_axis
    if pair_id not in bundle['pairs'] or quantity not in ('CF', 'CFN', 'CFS') or type(component) is not int or component not in (0, 1, 2):
        raise ValueError('정확한 접촉쌍, CF/CFN/CFS, X/Y/Z 성분을 선택하세요.')
    spec = selection(resultant)
    count = len(bundle['frames'])
    chosen = list(range(count)) if frame_indices is None else frame_indices
    if (not isinstance(chosen, list) or not chosen or any(type(i) is not int or not 0 <= i < count for i in chosen)
            or chosen != sorted(set(chosen))):
        raise ValueError('저장 증분 선택은 중복 없이 원래 순서여야 합니다.')
    rows = []
    for index in chosen:
        frame = bundle['frames'][index]
        matches = [r for r in frame['pair_resultants'] if r['pair_id'] == pair_id and r['quantity'] == quantity]
        raw = matches[0] if len(matches) == 1 else None
        value, reason = project(raw, spec, component)
        if len(matches) > 1:
            value, reason = None, 'UNKNOWN_ASSOCIATION'
        if raw and raw.get('static') != frame['static']:
            value, reason = None, 'UNKNOWN_ASSOCIATION'
        rows.append({'static': deepcopy(frame['static']), 'value': value, 'valid': reason is None,
                     'reason': reason, 'raw_text': raw.get('raw_text') if raw else None,
                     'source_frame_index': index,
                     **({'input_activation': frame['input_activation'].get(pair_id)} if 'input_activation' in frame else {})})
    response = spec['response']
    unit = 'N' if response == 'force' else 'N*mm'
    global_axes = spec['basis_rows'] == IDENTITY
    frame = 'FREECAD_DOCUMENT_GLOBAL' if global_axes else 'USER_ORTHONORMAL_BASIS:' + spec['frame_label']
    measure = 'contact_pair_force_resultant' if response == 'force' else 'contact_pair_moment_about_reference_point'
    return {'pair_id': pair_id, 'quantity': quantity, 'component': component,
            'array': quantity + ('_F' if response == 'force' else '_M') + 'XYZ'[component] + ('_N' if response == 'force' else '_Nmm'),
            'unit': unit, 'frame': frame, 'measure': measure, 'force_on': 'slave_A',
            'resultant': spec, 'axis': bundle_axis(bundle), 'rows': rows,
            'frame_indices': chosen, 'source': deepcopy(bundle['manifest'].get('source')),
            'transformation': 'Q F' if response == 'force' else 'Q (M_origin - r_global cross F)',
            'integration': 'NONE_NATIVE_DAT_PAIR_RESULTANT',
            **({'execution': deepcopy(bundle['manifest']['execution'])} if 'execution' in bundle['manifest'] else {})}
