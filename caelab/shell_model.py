"""E1 S8 domain rules. No native imports, process starts, or persistence side effects.

Raw property strings are deliberately not coerced in an editable draft. Validation
produces field-addressed errors; a saved invalid draft is not an applied model.
"""
from copy import deepcopy
from decimal import Decimal, InvalidOperation
import hashlib
import json
import math
import re

FIELDS = ('thickness_mm', 'offset', 'young_MPa', 'poisson', 'pressure_MPa',
          'axis_x', 'axis_y', 'axis_z')
DEFAULTS = dict(thickness_mm='2', offset='0', young_MPa='210000', poisson='0.3',
                pressure_MPa='0.001', axis_x='1', axis_y='0', axis_z='0',
                orientation='', fixed_nodes=[])
REVERSE_S8 = (0, 3, 2, 1, 7, 6, 5, 4)
EDGES = ((0, 1, 4), (1, 2, 5), (2, 3, 6), (3, 0, 7))
G = math.sqrt(3.0 / 5.0)
# Literal abscissae/order from CalculiX 2.22 src/gauss.f (not a surface grid).
NATIVE_G = 0.774596669241483
GAUSS27 = tuple((x, y, z) for z in (-NATIVE_G, 0., NATIVE_G)
                for y in (-NATIVE_G, 0., NATIVE_G) for x in (-NATIVE_G, 0., NATIVE_G))
NUMBER = re.compile(r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eEdD][+-]?\d+)?\Z')


class ShellError(ValueError):
    def __init__(self, errors):
        self.errors = errors
        super().__init__('; '.join(e['path'] + ': ' + e['message'] for e in errors))


def issue(path, message):
    return {'path': path, 'message': message}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
        ensure_ascii=False, allow_nan=False).encode('utf-8')).hexdigest()


def number(value):
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise ValueError('완성된 유한 숫자를 입력하세요.')
    token = str(value).strip()
    if len(token) > 80 or not NUMBER.fullmatch(token):
        raise ValueError('완성된 숫자를 입력하세요. 예: 2, 0.5, 1e-3')
    result = float(token.replace('d', 'e').replace('D', 'E'))
    if not math.isfinite(result):
        raise ValueError('유한 숫자를 입력하세요.')
    return result


def dot(a, b):
    return sum(x*y for x, y in zip(a, b))


def cross(a, b):
    return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])


def sub(a, b):
    return tuple(x-y for x, y in zip(a, b))


def unit(v):
    length = math.hypot(*v)
    if not math.isfinite(length) or length <= 0:
        raise ValueError('0이 아닌 방향을 지정하세요.')
    return tuple(x/length for x in v)


def basis(normal, reference):
    n = unit(normal)
    r = unit(reference)
    tangent = sub(r, tuple(dot(r, n)*v for v in n))
    if math.hypot(*tangent) <= 1e-10:
        raise ValueError('국부 1축이 법선과 평행합니다. 다른 방향을 지정하세요.')
    x = unit(tangent)
    return (x, cross(n, x), n)


def shape8(r, s):
    return (-(1-r)*(1-s)*(1+r+s)/4, -(1+r)*(1-s)*(1-r+s)/4,
            -(1+r)*(1+s)*(1-r-s)/4, -(1-r)*(1+s)*(1+r-s)/4,
            (1-r*r)*(1-s)/2, (1+r)*(1-s*s)/2,
            (1-r*r)*(1+s)/2, (1-r)*(1-s*s)/2)


def derivatives8(r, s):
    # Analytic serendipity derivatives in the submitted S8 order.
    dr = ((1-s)*(2*r+s)/4, (1-s)*(2*r-s)/4,
          (1+s)*(2*r+s)/4, (1+s)*(2*r-s)/4,
          -r*(1-s), (1-s*s)/2, -r*(1+s), -(1-s*s)/2)
    ds = ((1-r)*(r+2*s)/4, (1+r)*(-r+2*s)/4,
          (1+r)*(r+2*s)/4, (1-r)*(-r+2*s)/4,
          -(1-r*r)/2, -(1+r)*s, (1-r*r)/2, -(1-r)*s)
    return dr, ds


def normal8(points, r=0., s=0.):
    dr, ds = derivatives8(r, s)
    # Translate first to avoid loss of significance far from the origin.
    shifted = [sub(p, points[0]) for p in points]
    return cross(tuple(sum(p[c]*v for p, v in zip(shifted, dr)) for c in range(3)),
                 tuple(sum(p[c]*v for p, v in zip(shifted, ds)) for c in range(3)))


def validate_draft(draft):
    errors, values = [], {}
    if not isinstance(draft, dict):
        return [issue('shell', '셸 초안을 읽을 수 없습니다.')], None
    for name in FIELDS:
        try:
            values[name] = number(draft.get(name, ''))
        except ValueError as exc:
            errors.append(issue(name, str(exc)))
    for name in ('thickness_mm', 'young_MPa'):
        if name in values and values[name] <= 0:
            errors.append(issue(name, '0보다 큰 값을 입력하세요.'))
    if 'poisson' in values and not -1 < values['poisson'] < .5:
        errors.append(issue('poisson', '-1보다 크고 0.5보다 작은 값을 입력하세요.'))
    if draft.get('orientation') not in ('native', 'reversed'):
        errors.append(issue('orientation', '요소 법선을 미리 본 뒤 방향을 명시적으로 선택하세요.'))
    if all(k in values for k in ('axis_x', 'axis_y', 'axis_z')):
        try:
            values['axis'] = list(unit([values[k] for k in ('axis_x','axis_y','axis_z')]))
        except ValueError as exc:
            errors.append(issue('axis_x', str(exc)))
    selected = draft.get('elements')
    if (not isinstance(selected, list) or not selected or
            any(type(e) is not int or e <= 0 for e in selected) or len(set(selected)) != len(selected)):
        errors.append(issue('elements', '참여할 서로 다른 S8 요소를 선택하세요.'))
    fixed = draft.get('fixed_nodes', [])
    if (not isinstance(fixed, list) or any(type(n) is not int or n <= 0 for n in fixed)
            or len(set(fixed)) != len(fixed)):
        errors.append(issue('fixed_nodes', '고정 절점은 중복 없는 양의 정수 번호로 지정하세요.'))
    if values.get('pressure_MPa') == 0:
        errors.append(issue('pressure_MPa', '첫 정적 압력 경로는 0이 아닌 압력을 요구합니다.'))
    values['orientation'] = draft.get('orientation')
    return errors, values


def reverse(draft, *, keep_physical_load=True):
    """Pure draft edit: keep occupied geometry fixed, exchange the named sides.

    Positive pressure means traction opposite the chosen positive shell normal.
    Negating offset preserves physical thickness position when the normal flips.
    Negating pressure additionally preserves the global traction direction.
    """
    if draft.get('orientation') not in ('native', 'reversed'):
        raise ShellError([issue('orientation', '먼저 현재 법선 방향을 선택하세요.')])
    out = deepcopy(draft)
    keys = ('offset', 'pressure_MPa') if keep_physical_load else ('offset',)
    for key in keys:
        try:
            number(out[key])
            out[key] = str(-Decimal(str(out[key]).replace('d','e').replace('D','E')))
        except (ValueError, InvalidOperation, KeyError):
            raise ShellError([issue(key, '불완전한 값을 먼저 고친 뒤 법선을 반전하세요.')])
    out['orientation'] = 'reversed' if out['orientation'] == 'native' else 'native'
    return out


def prepare_mesh(nodes, elements, draft):
    """Select and orient arbitrary native S8 IDs, with sampled geometry guards.

    These are serialization/topology/numerical guards, not mesh qualification.
    Curved elements are allowed; knots/effective averaged normals are read from
    CalculiX .12d + FRD after execution, not guessed by this preview.
    """
    errors, values = validate_draft(draft)
    if errors:
        raise ShellError(errors)
    if any(e not in elements for e in draft['elements']):
        raise ShellError([issue('elements', '선택 요소가 없어졌습니다. 대상을 명시적으로 다시 선택하세요.')])
    chosen, normals, axes, areas = {}, {}, {}, {}
    edge_owners = {}
    for e in sorted(draft['elements']):
        conn = elements[e]
        path = f'elements/{e}'
        if (len(conn) != 8 or len(set(conn)) != 8 or
                any(type(n) is not int or n not in nodes for n in conn)):
            errors.append(issue(path, '8절점 사각형 셸 S8 연결을 확인하세요.'))
            continue
        order = REVERSE_S8 if values['orientation'] == 'reversed' else range(8)
        conn = tuple(conn[i] for i in order)
        try:
            points = [tuple(number(x) for x in nodes[n]) for n in conn]
            if any(len(p) != 3 for p in points):
                raise ValueError('절점 좌표는 세 성분이어야 합니다.')
            center = unit(normal8(points))
            scale = max(math.dist(a, b) for a in points for b in points)
            area = 0.
            for r, wr in ((-G,5/9),(0.,8/9),(G,5/9)):
                for s, ws in ((-G,5/9),(0.,8/9),(G,5/9)):
                    jac = normal8(points, r, s)
                    if dot(jac, center) <= 256*math.ulp(1.)*scale*scale:
                        raise ValueError('접히거나 퇴화한 요소입니다. 메시를 수정하세요.')
                    area += math.hypot(*jac)*wr*ws
            frames = basis(center, values['axis'])
            for a,b,m in EDGES:
                edge = (min(conn[a],conn[b]), max(conn[a],conn[b]))
                edge_owners.setdefault(edge, []).append((e, conn[a], conn[b], conn[m]))
            chosen[e], normals[e], axes[e], areas[e] = conn, center, frames, area
        except ValueError as exc:
            errors.append(issue(path, str(exc)))
    for edge, owners in edge_owners.items():
        if len(owners) > 2 or len(owners) == 2 and (owners[0][1] != owners[1][2]
                or owners[0][2] != owners[1][1] or owners[0][3] != owners[1][3]):
            errors.append(issue('elements/' + str(owners[0][0]),
                '공유 모서리의 법선 또는 중간 절점이 불일치합니다. native 메시 방향을 수정하세요.'))
    if errors:
        raise ShellError(errors)
    used = {n for conn in chosen.values() for n in conn}
    return {'nodes': {n: list(nodes[n]) for n in sorted(used)}, 'elements': chosen,
            'normals': normals, 'axes': axes, 'areas_mm2': areas, 'values': values}


def check_supports(mesh, fixed):
    """Each connected patch must be tied to explicitly fixed native nodes.

    First route uses XYZ plus rotational DOFs 4..6, matching native Fixed for
    shells. One fixed corner is not accepted as a generally stable shell support.
    """
    fixed = set(fixed)
    if not fixed or not fixed <= set(mesh['nodes']):
        raise ShellError([issue('fixed_nodes', '참여 메시 안의 실제 고정 절점을 확인하세요.')])
    remaining = set(mesh['elements'])
    while remaining:
        component = {remaining.pop()}
        nodes = set(mesh['elements'][next(iter(component))])
        changed = True
        while changed:
            changed = False
            for e in list(remaining):
                if nodes.intersection(mesh['elements'][e]):
                    component.add(e); remaining.remove(e)
                    nodes.update(mesh['elements'][e]); changed = True
        anchor = sorted(nodes & fixed)
        if len(anchor) < 2 or max(math.dist(mesh['nodes'][a], mesh['nodes'][b])
                                 for a in anchor for b in anchor) <= 0:
            raise ShellError([issue('fixed_nodes',
                f'분리된 셸 영역(요소 {min(component)})에 서로 다른 위치의 고정 절점이 필요합니다.')])
    return sorted(fixed)
