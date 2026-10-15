"""Explicit S8 property regions; raw drafts remain part of the existing owner.

A region is an assignment, not another mesh, material, solver or store.  Native
connectivity is checked before any explicitly requested normal reversal.  No
solver-averaged normal or expansion node identity is predicted here.
"""
from copy import deepcopy
import re

REGION_FIELDS = ('thickness_mm', 'offset', 'pressure_MPa',
                 'axis_x', 'axis_y', 'axis_z', 'orientation')
REGION_KEYS = frozenset(('id', 'label', 'elements', 'face_refs', 'geometry_id',
                         'pressure_id', *REGION_FIELDS))
MAX_REGIONS = 4096


def check_shape(regions):
    """Bound storage, not numeric validity: '-', '2e' and overlaps can be saved."""
    if not isinstance(regions, list) or len(regions) > MAX_REGIONS:
        raise ValueError('셸 영역 목록은 4096행 이하이어야 합니다.')
    for i, row in enumerate(regions):
        if not isinstance(row, dict) or set(row) != REGION_KEYS:
            raise ValueError(f'셸 영역 {i+1}의 저장 필드가 잘못됐습니다.')
        for key in ('id', 'label', 'geometry_id', 'pressure_id', *REGION_FIELDS):
            value = row[key]
            if isinstance(value, bool) or not isinstance(value, (str, int, float)):
                raise ValueError(f'셸 영역 {i+1}/{key}: 원문 숫자 또는 이름이 필요합니다.')
            if len(str(value)) > 256:
                raise ValueError(f'셸 영역 {i+1}/{key}: 입력 길이를 줄이세요.')
        if not isinstance(row['elements'], list) or len(row['elements']) > 1000000:
            raise ValueError('영역의 실제 요소 목록을 확인하세요.')
        if any(type(e) is not int or e <= 0 for e in row['elements']):
            raise ValueError('영역 대상에는 실제 양의 정수 요소 번호만 저장합니다.')
        if not isinstance(row['face_refs'], list) or len(row['face_refs']) > 4096:
            raise ValueError('영역 면 참조를 확인하세요.')
        for ref in row['face_refs']:
            if not isinstance(ref, dict) or set(ref) != {'object_id', 'subelements'}:
                raise ValueError('영역의 실제 native 면 참조를 확인하세요.')
            if not isinstance(ref['object_id'], str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*', ref['object_id']):
                raise ValueError('영역 native 객체 이름이 잘못됐습니다.')
            if (not isinstance(ref['subelements'], list) or not ref['subelements'] or
                    any(not isinstance(n, str) or not re.fullmatch(r'Face[1-9][0-9]*', n)
                        for n in ref['subelements'])):
                raise ValueError('영역 참조는 실제 면 이름이어야 합니다.')
    return deepcopy(regions)


def uniform_region(draft, *, region_id='R1', label='판재 영역 1'):
    """Explicit migration only; old drafts are never automatically rewritten."""
    return dict(id=region_id, label=label, elements=deepcopy(draft.get('elements', [])),
                face_refs=deepcopy(draft.get('face_refs', [])),
                geometry_id=draft.get('geometry_id') or '', pressure_id=draft.get('pressure_id') or '',
                **{key: deepcopy(draft.get(key, '')) for key in REGION_FIELDS})


def region_draft(draft, row):
    out = {k: deepcopy(v) for k, v in draft.items() if k != 'regions'}
    out.update({k: deepcopy(row[k]) for k in REGION_FIELDS})
    out['elements'] = deepcopy(row['elements'])
    return out


def validate(draft):
    from .shell_model import _validate_uniform_draft, DEFAULTS, issue
    errors = []
    try:
        regions = check_shape(draft['regions'])
    except (KeyError, ValueError) as exc:
        return [issue('regions', str(exc))], None
    # The inherited uniform geometry is retained for backwards editing only.
    # It does not override explicitly assigned region properties.
    common = {k: deepcopy(v) for k, v in draft.items() if k != 'regions'}
    common.update({k: DEFAULTS[k] for k in REGION_FIELDS})
    common['orientation'] = draft.get('orientation', '')  # Explicit source/rebind acknowledgement.
    common_errors, common_values = _validate_uniform_draft(
        common, require_nonzero_pressure=False)
    errors.extend(common_errors)
    if not regions:
        errors.append(issue('regions', '참여 요소에 속성 영역을 할당하세요.'))
    selected = set(draft.get('elements', [])) if isinstance(draft.get('elements'), list) else set()
    assigned, ids, native = {}, set(), {'geometry_id': {}, 'pressure_id': {}}
    values = {}
    has_pressure = False
    for index, row in enumerate(regions):
        path = f'regions/{index}'
        if (not isinstance(row['id'], str) or not re.fullmatch(r'R[A-Za-z0-9_]{1,63}', row['id'])
                or row['id'] in ids):
            errors.append(issue(path+'/id', '서로 다른 영역 식별자가 필요합니다.'))
        ids.add(row['id'])
        if not isinstance(row['label'], str) or not row['label'].strip():
            errors.append(issue(path+'/label', '구별할 수 있는 영역 이름을 입력하세요.'))
        row_errors, numeric = _validate_uniform_draft(
            region_draft(draft, row), require_nonzero_pressure=False)
        for error in row_errors:
            errors.append(issue(path+'/'+error['path'], error['message']))
        for key in native:
            name = row[key]
            if name:
                if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*', name):
                    errors.append(issue(path+'/'+key, 'native 속성 객체 이름을 확인하세요.'))
                if name in native[key]:
                    errors.append(issue(path+'/'+key, f'영역 {native[key][name]+1}과 native 속성이 중복됩니다.'))
                native[key][name] = index
        for e in row['elements']:
            if e not in selected:
                errors.append(issue(path+'/elements', f'요소 {e}는 참여 집합에 없습니다.'))
            if e in assigned:
                errors.append(issue(path+'/elements', f'요소 {e}가 영역 {assigned[e]+1}과 겹칩니다.'))
            assigned[e] = index
        values[row['id']] = numeric
        # Opposite signed loads do not cancel the existence of a load.
        # Invalid/missing numbers are never converted to a zero placeholder.
        has_pressure |= ('pressure_MPa' in numeric and numeric['pressure_MPa'] != 0)
    if not has_pressure:
        errors.append(issue('regions', '첫 정적 압력 경로는 참여 영역 하나 이상에 0이 아닌 압력을 요구합니다.'))
    missing = sorted(selected - set(assigned))
    if missing:
        errors.append(issue('regions', '속성이 없는 요소: '+', '.join(map(str, missing[:50]))))
    return errors, {'young_MPa': common_values.get('young_MPa'),
                    'poisson': common_values.get('poisson'), 'regional': True,
                    'regions': values}


def prepare(nodes, elements, draft):
    from .shell_model import _prepare_uniform_mesh, EDGES, ShellError, issue
    errors, values = validate(draft)
    if errors:
        raise ShellError(errors)
    selected = draft['elements']
    if any(e not in elements for e in selected):
        raise ShellError([issue('elements', '참여 요소가 없어졌습니다. 명시적으로 다시 선택하세요.')])
    # Preserve the original source winding/midside/manifold guard across region
    # borders.  A deliberate normal flip is applied only after this check.
    owners = {}
    for e in selected:
        conn = elements[e]
        if len(conn) != 8 or len(set(conn)) != 8:
            raise ShellError([issue(f'elements/{e}', 'S8 연결을 확인하세요.')])
        for a, b, m in EDGES:
            key = tuple(sorted((conn[a], conn[b])))
            owners.setdefault(key, []).append((e, conn[a], conn[b], conn[m]))
    for rows in owners.values():
        if len(rows) > 2 or len(rows) == 2 and (rows[0][1] != rows[1][2] or
                rows[0][2] != rows[1][1] or rows[0][3] != rows[1][3]):
            errors.append(issue(f'elements/{rows[0][0]}', '영역 경계의 native winding/중간 절점이 불일치합니다.'))
    if errors:
        raise ShellError(errors)
    combined = {k: {} for k in ('nodes', 'elements', 'normals', 'axes', 'areas_mm2')}
    by_element, assignments = {}, {}
    for index, row in enumerate(draft['regions']):
        piece = _prepare_uniform_mesh(
            nodes, elements, region_draft(draft, row), require_nonzero_pressure=False)
        for key in combined:
            combined[key].update(piece[key])
        for e in piece['elements']:
            by_element[e] = deepcopy(piece['values'])
            assignments[e] = {'id': row['id'], 'label': row['label'], 'row': index,
                              'geometry_id': row['geometry_id'], 'pressure_id': row['pressure_id']}
    for key in combined:
        combined[key] = dict(sorted(combined[key].items()))
    combined.update(values=values, values_by_element=by_element, region_by_element=assignments)
    return combined


def element_values(mesh, element):
    return mesh['values_by_element'][element] if 'values_by_element' in mesh else mesh['values']


def serialized_section(mesh, element):
    return mesh['section_values_by_element'][element] if 'section_values_by_element' in mesh else mesh['section_values']


def reverse_region(draft, region_id, *, keep_physical_load=True):
    from .shell_model import reverse
    out = deepcopy(draft)
    matches = [i for i, row in enumerate(out['regions']) if row['id'] == region_id]
    if len(matches) != 1:
        raise ValueError('반전할 영역을 하나 선택하세요.')
    i = matches[0]
    reversed_draft = reverse(region_draft(out, out['regions'][i]), keep_physical_load=keep_physical_load)
    for key in REGION_FIELDS:
        out['regions'][i][key] = reversed_draft[key]
    return out
