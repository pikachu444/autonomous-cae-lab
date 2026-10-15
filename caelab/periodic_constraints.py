"""C3D10 periodic displacement equations for the existing FEM constraint owner.

x_B = origin + R (x_A - origin) + translation; u_B = R u_A.
Rotation here transforms coordinates and translation vectors; it never invents
solid rotational DOFs 4..6. This is not a solver or a contact law.
"""
from copy import deepcopy
from itertools import product
import math
import re
from .contact import number
from .contact_resultants import cross, vector, IDENTITY

OPERATIONS = ('pre.fem.periodic_read', 'pre.fem.periodic_set',
              'pre.fem.periodic_remove', 'pre.fem.periodic_highlight')
PROFILE = 'calculix-2.22-c3d10-static-linear-periodic-displacement-v1'


def normalize(draft):
    common = {'label', 'a_region_id', 'b_region_id', 'transform', 'tolerance_mm', 'dofs'}
    if not isinstance(draft, dict) or set(draft) != common:
        raise ValueError('PERIODIC_DRAFT: 이름·두 면·변환·허용오차·자유도가 필요합니다.')
    if not isinstance(draft['label'], str) or not draft['label'].strip() or len(draft['label']) > 160:
        raise ValueError('주기 구속 이름을 입력하세요.')
    for key in ('a_region_id', 'b_region_id'):
        if not isinstance(draft[key], str) or not draft[key]:
            raise ValueError('주기 경계 A와 B를 지정하세요.')
    if draft['a_region_id'] == draft['b_region_id']:
        raise ValueError('PERIODIC_SELF: 같은 면 집합을 양쪽에 지정할 수 없습니다.')
    if draft['dofs'] != [1, 2, 3] or any(type(v) is not int for v in draft['dofs']):
        raise ValueError('PERIODIC_DOFS: 고체의 병진 자유도 1·2·3만 지원합니다. 회전 자유도 4·5·6이 아닙니다.')
    tol = number(draft['tolerance_mm'])
    if tol <= 0:
        raise ValueError('주기 대응 허용오차 [mm]는 양수여야 합니다.')
    t = draft['transform']
    if not isinstance(t, dict):
        raise ValueError('주기 변환을 지정하세요.')
    if t.get('kind') == 'translation' and set(t) == {'kind', 'translation_mm'}:
        shift, origin, rotation = vector(t['translation_mm'], '주기 이동량 [mm]'), [0., 0., 0.], deepcopy(IDENTITY)
    elif t.get('kind') == 'rotation' and set(t) == {'kind', 'axis', 'origin_mm', 'angle_deg'}:
        axis = vector(t['axis'], '회전축 방향')
        magnitude = math.hypot(*axis)
        angle = number(t['angle_deg'])
        if magnitude == 0 or not math.isfinite(magnitude) or not 1e-10 < abs(angle) < 360:
            raise ValueError('회전축은 0이 아닌 방향이고 주기각은 0~360도 사이의 유한한 값이어야 합니다.')
        axis = [v/magnitude for v in axis]
        c, s = math.cos(math.radians(angle)), math.sin(math.radians(angle))
        skew = [[0., -axis[2], axis[1]], [axis[2], 0., -axis[0]], [-axis[1], axis[0], 0.]]
        rotation = [[(c if i == j else 0.) + (1-c)*axis[i]*axis[j] + s*skew[i][j]
                     for j in range(3)] for i in range(3)]
        # Remove only trigonometric roundoff at zero, never a user displacement.
        rotation = [[0. if abs(v) < 1e-15 else v for v in row] for row in rotation]
        origin, shift = vector(t['origin_mm'], '회전축 기준점 [mm]'), [0., 0., 0.]
    else:
        raise ValueError('PERIODIC_TRANSFORM: 병진 또는 축·각도 회전만 지원합니다.')
    return {'draft': deepcopy(draft), 'rotation': rotation, 'origin_mm': origin,
            'translation_mm': shift, 'tolerance_mm': tol, 'dofs': [1, 2, 3],
            'equation': 'u_B = R u_A', 'dependent_side': 'b', 'profile': PROFILE}


def transform_point(point, spec):
    r, o, t = spec['rotation'], spec['origin_mm'], spec['translation_mm']
    return [o[i] + math.fsum(r[i][j]*(point[j]-o[j]) for j in range(3)) + t[i] for i in range(3)]


def pair_nodes(nodes, a_nodes, b_nodes, draft):
    spec = normalize(draft)
    for ids in (a_nodes, b_nodes):
        if (not isinstance(ids, list) or not ids or len(ids) > 200000 or len(set(ids)) != len(ids)
                or any(type(n) is not int or n not in nodes for n in ids)):
            raise ValueError('PERIODIC_NODE_SET: 정확한 비중복 면 절점 집합이 필요합니다.')
    if set(a_nodes) & set(b_nodes):
        raise ValueError('PERIODIC_SELF: A/B 경계의 공통 절점은 이 경로에서 지원하지 않습니다.')
    if len(a_nodes) != len(b_nodes):
        raise ValueError('PERIODIC_INCOMPLETE: 두 경계의 절점 수가 다릅니다. 중간 절점도 포함하세요.')
    tol = spec['tolerance_mm']
    def cell(point):
        try:
            return tuple(math.floor(v/tol) for v in point)
        except (OverflowError, ValueError):
            raise ValueError('PERIODIC_RANGE: 좌표 크기에 비해 허용오차가 너무 작습니다.') from None
    buckets, coordinates = {}, {}
    for node in b_nodes:
        point = vector(nodes[node], 'B 절점 좌표')
        coordinates[node] = point
        buckets.setdefault(cell(point), []).append(node)
    matched, out = set(), []
    for a in sorted(a_nodes):
        source = vector(nodes[a], 'A 절점 좌표')
        transformed = transform_point(source, spec)
        if not all(math.isfinite(v) for v in transformed):
            raise ValueError('PERIODIC_RANGE: 변환 좌표가 유한하지 않습니다.')
        center, candidates = cell(transformed), []
        for delta in product((-1, 0, 1), repeat=3):
            for b in buckets.get(tuple(center[j]+delta[j] for j in range(3)), []):
                error = math.dist(transformed, coordinates[b])
                if error <= tol:
                    candidates.append((b, error))
        if not candidates:
            raise ValueError('PERIODIC_UNMATCHED: A 절점 ' + str(a) + '의 변환 위치에 B 절점이 없습니다. 축·방향·누락 절점을 확인하세요.')
        if len(candidates) != 1:
            raise ValueError('PERIODIC_AMBIGUOUS: A 절점 ' + str(a) + '에 B 절점이 여러 개 대응합니다. 허용오차/메시를 확인하세요.')
        b, error = candidates[0]
        if b in matched:
            raise ValueError('PERIODIC_DUPLICATE: 여러 A 절점이 같은 B 절점에 대응합니다.')
        matched.add(b)
        out.append({'a_node': a, 'b_node': b, 'a_position_mm': source,
                    'transformed_a_mm': transformed, 'b_position_mm': coordinates[b], 'distance_mm': error})
    if matched != set(b_nodes):
        raise ValueError('PERIODIC_INCOMPLETE: 대응하지 않은 B 절점이 있습니다.')
    return {**spec, 'node_pairs': out}


def _surface(surface, model, nodes, elements):
    from .contact_deck import FACES
    if not isinstance(surface, dict) or not isinstance(surface.get('element_faces'), list) or not surface['element_faces']:
        raise ValueError('PERIODIC_SURFACE: 요소 면 집합이 필요합니다.')
    body = surface.get('body_id')
    result, seen = set(), set()
    owners = {e['element_id']: e['body_id'] for e in model['elements']}
    for row in surface['element_faces']:
        if (not isinstance(row, list) or len(row) != 2 or any(type(v) is not int for v in row)
                or tuple(row) in seen or row[0] not in elements or row[1] not in FACES or owners[row[0]] != body):
            raise ValueError('PERIODIC_SURFACE: 중복·다른 body·누락 요소 면을 확인하세요.')
        seen.add(tuple(row))
        result.update(elements[row[0]][slot] for slot in FACES[row[1]])
    cad = surface.get('cad_faces', [])
    if (not cad or any(not row.get('element_faces') for row in cad)
            or {tuple(x) for row in cad for x in row['element_faces']} != seen):
        raise ValueError('PERIODIC_FACE_COVERAGE: 선택한 모든 CAD 면의 정확한 요소 면이 필요합니다.')
    return sorted(result)


def compile_constraints(model, nodes=None, elements=None):
    rows = model.get('periodic_constraints', [])
    if not isinstance(rows, list) or len(rows) > 256:
        raise ValueError('주기 구속은 256개 이하의 명시적인 목록이어야 합니다.')
    if not rows:
        return []
    from .calculix_material import has_plasticity
    if model.get('contacts'):
        raise ValueError('PERIODIC_CONTACT_COMBINATION_UNKNOWN: 접촉/묶음과 주기 구속의 결합은 이번 실행 범위 밖입니다. 기존 각 경로는 유지합니다.')
    if (model.get('step', {}).get('geometry') != 'linear' or has_plasticity(model)
            or model.get('analysis_steps', {}).get('procedure', 'static') != 'static'
            or 'restart' in model or 'dynamic' in model):
        raise ValueError('PERIODIC_UNKNOWN_COMBINATION: 이번 경로는 정적·소변형·선형 탄성 고체의 병진 자유도만 지원합니다.')
    if any(p['draft'].get('tie_adjust') for p in model['contacts']):
        raise ValueError('PERIODIC_ADJUST_CONFLICT: 조정 후 초기좌표와의 주기 대응은 아직 지원하지 않습니다.')
    nodes = nodes or {r['node_id']: r['position_mm'] for r in model['nodes']}
    elements = elements or {r['element_id']: r['node_ids'] for r in model['elements']}
    boundaries = {(r['node_id'], r['component']) for r in model['boundary_dofs']}
    if 'analysis_steps' in model:
        from .contact_steps import compile_program
        for step in compile_program(model['analysis_steps'], model['conditions']):
            if step['procedure'] != 'static':
                raise ValueError('PERIODIC_UNKNOWN_COMBINATION: 모든 단계가 정적이어야 합니다.')
            boundaries.update(step['boundary'])
    from .contact_deck import FACES
    tie_dependent = {elements[e][i] for p in model['contacts'] if p['draft']['normal_law'] == 'tie'
                     for e, f in p['a']['element_faces'] for i in FACES[f]}
    ids, dependent, independent, output = set(), set(), set(), []
    for row in rows:
        identifier = row.get('id')
        if not isinstance(identifier, str) or not re.fullmatch(r'P[A-Za-z0-9_]{1,63}', identifier) or identifier in ids:
            raise ValueError('PERIODIC_ID: 주기 구속 식별자가 없거나 중복입니다.')
        ids.add(identifier)
        a = _surface(row['a'], model, nodes, elements)
        b = _surface(row['b'], model, nodes, elements)
        if (set(b) & (dependent | independent | tie_dependent) or set(a) & (dependent | tie_dependent)):
            raise ValueError('PERIODIC_DEPENDENCY: 중복 종속 절점, 순환·연쇄 또는 묶음 종속 절점과 겹칩니다.')
        if any((n, d) in boundaries for n in b for d in (1, 2, 3)):
            raise ValueError('PERIODIC_SPC_CONFLICT: B면 종속 자유도에 지정 변위/고정 조건이 겹칩니다.')
        mapped = pair_nodes(nodes, a, b, row['draft'])
        mapped['id'] = identifier
        equations = []
        for match in mapped['node_pairs']:
            for i, coefficients in enumerate(mapped['rotation'], 1):
                terms = [[match['b_node'], i, 1.]]
                terms += [[match['a_node'], j, -c] for j, c in enumerate(coefficients, 1) if c != 0]
                equations.append({'dependent': [match['b_node'], i], 'terms': terms})
        mapped['equations'] = equations
        if 'compiled' in row and row['compiled'] != mapped:
            raise ValueError('PERIODIC_MAPPING_CHANGED: 저장된 대응식이 현재 면/절점/변환과 다릅니다.')
        output.append(mapped)
        dependent.update(b); independent.update(a)
    return output


def cards(model):
    from .contact_deck import num
    result = []
    for constraint in compile_constraints(model):
        result.append('** PERIODIC ' + constraint['id'] + ' TRANSLATION DOFS 1 2 3')
        for row in constraint['equations']:
            result += ['*EQUATION', str(len(row['terms']))]
            # At most two triplets per line keeps the native 132-column limit.
            for i in range(0, len(row['terms']), 2):
                result.append(','.join(str(n)+','+str(d)+','+num(v) for n, d, v in row['terms'][i:i+2]))
    return result
