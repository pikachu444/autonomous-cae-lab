"""Explicit user-face bindings for the pinned 3D_JOINT/CZM_LIN_REG path.

Native Code_Aster supplies the constitutive response. These functions check
input identity and emit separate joint connectivity without moving/welding any
bulk node. Definitions use body-local native node pairs, never nearest nodes.
"""
from copy import deepcopy
import math

from .contact import number
from .contact_deck import name
from .contact_resultants import cross
from .adapters.contact_aster_model import FACES, mesh_quality

SOURCE = '50ebc13c70ee9df62faf93ddcb746a3757b3042a'
BACKEND = 'structure.codeaster.implicit_interface'
PARAMETER_UNITS = {'SIGM_C': 'MPa', 'GC': 'N/mm',
                   'PENA_ADHERENCE': '1', 'PENA_CONTACT': '1'}
COMPRESSION_POLICY = {
    'inequality': 'PENA_CONTACT >= PENA_ADHERENCE',
    'reason': 'Positive compression support after a large opening in native lcejli',
    'source_commit': SOURCE,
    'native_catalogue_bound': None,
    'qualification': 'UNKNOWN',
}


def profile(model):
    """Finite native support, checked before any translation or execution."""
    if model.get('backend') != BACKEND or model.get('analysis_scope') is not None:
        raise ValueError('선택한 두 고체의 접합 계면 입력을 사용하세요.')
    if len(model.get('body_maps',{})) != 2 or model.get('contacts'):
        raise ValueError('현재 계면 연결은 독립된 두 고체를 지원하며 같은 면에 접촉을 중복 적용하지 않습니다.')
    if not model.get('interfaces') or any(e.get('type') != 'C3D8' for e in model['elements']):
        raise ValueError('현재 계면 연결에는 HEXA8 고체와 명시한 사각형 접합 면이 필요합니다.')
    if any(model.get(k) for k in ('dynamic','restart','periodic_constraints','pretension_sections','initial_fields')):
        raise ValueError('현재 계면 입력에서 동해석·재시작·주기·체결·초기 상태를 생략해 변환하지 않습니다.')
    if any(m.get('law') != 'isotropic_linear_elastic' or m.get('plasticity') for m in model['materials']):
        raise ValueError('현재 계면 연결의 두 고체에는 등방 선형 탄성 재료를 사용하세요.')
    if model['step']['geometry'] != 'linear' or model['step']['matrix_solver'] != 'default':
        raise ValueError('현재 계면 연결은 작은 변형 STATIC과 기본 Aster 해법을 지원합니다.')


def parameters(value):
    """Check native inputs and the declared positive-compression admission.

    PENA_CONTACT has no native catalogue bound. beta >= eta is the product's
    physical admission: rc=rk+beta*(r0-rk) stays positive for finite kappa.
    A draft outside this admission remains editable; it cannot become input.
    """
    if not isinstance(value, dict) or set(value) != set(PARAMETER_UNITS):
        raise ValueError('SIGM_C, GC, PENA_ADHERENCE, PENA_CONTACT를 모두 입력하세요.')
    result = {key: number(value[key]) for key in PARAMETER_UNITS}
    if result['SIGM_C'] <= 0 or result['GC'] <= 0:
        raise ValueError('임계 응력 [MPa]과 파괴 에너지 [N/mm]는 양수여야 합니다.')
    if not 1e-12 <= result['PENA_ADHERENCE'] < 1:
        raise ValueError('접착 정규화 비율은 1e-12 이상 1 미만이어야 합니다.')
    if result['PENA_CONTACT'] <= 0:
        raise ValueError('현재 계면 입력의 PENA_CONTACT는 양수여야 합니다.')
    if result['PENA_CONTACT'] < result['PENA_ADHERENCE']:
        raise ValueError('현재 압축 재접촉 지원에는 PENA_CONTACT가 PENA_ADHERENCE 이상이어야 합니다. 더 작은 값은 큰 개구 뒤 원 법칙의 압축 강성이 음수가 될 수 있습니다. 초안은 유지됩니다.')
    length = 2*result['GC']/result['SIGM_C']
    initial = length*result['PENA_ADHERENCE']
    if not math.isfinite(length) or not math.isfinite(initial) or initial <= 0:
        raise ValueError('계면 계수로 계산한 임계 분리 길이를 유한하게 표현할 수 없습니다.')
    initial_stiffness = result['SIGM_C']*(1-result['PENA_ADHERENCE'])/initial
    if not math.isfinite(initial_stiffness) or initial_stiffness <= 0:
        raise ValueError('계면 계수로 계산한 초기 강성을 양의 유한 수로 표현할 수 없습니다.')
    return result


def _basis(points, xi, eta):
    signs = ((-1,-1), (1,-1), (1,1), (-1,1))
    derivative = [(sx*(1+sy*eta)/4, sy*(1+sx*xi)/4) for sx,sy in signs]
    # Subtract a common origin before differencing to retain a translated mesh.
    local = [[p[a]-points[0][a] for a in range(3)] for p in points]
    a1 = [math.fsum(p[a]*d[0] for p,d in zip(local,derivative)) for a in range(3)]
    a2 = [math.fsum(p[a]*d[1] for p,d in zip(local,derivative)) for a in range(3)]
    normal = cross(a1,a2)
    area = math.hypot(*normal)
    tangent = math.hypot(*a1)
    if not math.isfinite(area) or not math.isfinite(tangent) or area <= 0 or tangent <= 0:
        raise ValueError('선택한 접합 사각형 면이 퇴화했습니다. 원 메시를 수정하세요.')
    n = [v/area for v in normal]
    t1 = [v/tangent for v in a1]
    shape = [(1+sx*xi)*(1+sy*eta)/4 for sx,sy in signs]
    return {'normal': n, 'tangent1': t1, 'tangent2': cross(n,t1),
            'surface_jacobian_mm2': area, 'natural_coordinates':[xi,eta],
            'coordinates_mm':[points[0][a]+math.fsum(p[a]*w for p,w in zip(local,shape)) for a in range(3)]}


def build_joints(model, definitions):
    """Resolve exact selected bulk faces into native eight-node joint cells.

    a/b.element_faces are the effective faces of this same capture. node_pairs
    are native IDs in those two bodies. The original model is never modified.
    """
    if (not isinstance(definitions,list) or not definitions
            or len(model.get('body_maps',{})) != 2
            or any(e['type'] != 'C3D8' for e in model['elements'])):
        raise ValueError('현재 계면 연결은 독립된 두 HEXA8 고체와 명시한 접합 면을 지원합니다.')
    mesh_quality(model)  # Bulk cells only; a zero-thickness joint is not a bulk cell.
    nodes = {row['node_id']: row for row in model['nodes']}
    elements = {row['element_id']: row for row in model['elements']}
    next_id = max(elements)+1
    result = []
    seen_ids, occupied_faces = set(), set()
    gp = 1/math.sqrt(3)
    for definition in definitions:
        if (not isinstance(definition,dict) or set(definition) !=
                {'object_id','label','a','b','node_pairs','material'}):
            raise ValueError('계면의 이름, 두 면, 명시한 절점 대응과 재료 계수가 필요합니다.')
        identifier = name(definition['object_id'])
        if identifier.upper() in seen_ids:
            raise ValueError('계면 식별자가 중복됐습니다.')
        seen_ids.add(identifier.upper())
        if not isinstance(definition['label'],str) or not definition['label'].strip() or len(definition['label']) > 160:
            raise ValueError('계면 이름은 1~160자의 읽을 수 있는 이름으로 입력하세요.')
        material = parameters(definition['material'])
        sides = {}
        for side in ('a','b'):
            surface = definition[side]
            body = surface['body_id']
            if body not in model['body_maps'] or not surface['element_faces']:
                raise ValueError('각 계면에서 현재 고체에 속한 메시 면을 선택하세요.')
            faces = []
            for element,face in surface['element_faces']:
                key = (body,element,face)
                if (type(element) is not int or type(face) is not int or element not in elements
                        or elements[element]['body_id'] != body or face not in FACES['C3D8']
                        or key in occupied_faces):
                    raise ValueError('접합 면이 중복됐거나 원 고체의 HEXA8 면과 다릅니다.')
                occupied_faces.add(key)
                faces.append([elements[element]['node_ids'][i] for i in FACES['C3D8'][face]])
            sides[side] = (body,faces)
        if sides['a'][0] == sides['b'][0]:
            raise ValueError('서로 다른 두 고체의 대향 면을 선택하세요.')
        mapping = {}
        raw_pairs = definition['node_pairs']
        if not isinstance(raw_pairs,list) or not raw_pairs:
            raise ValueError('접합할 원 절점의 명시한 대응을 선택하세요.')
        for pair in raw_pairs:
            if (not isinstance(pair,(list,tuple)) or len(pair) != 2
                    or any(type(n) is not int or n <= 0 for n in pair)):
                raise ValueError('각 절점 대응은 두 고체의 양의 원 절점 번호여야 합니다.')
            effective = []
            for side,native in zip(('a','b'),pair):
                body = sides[side][0]
                table = {int(k):v for k,v in model['body_maps'][body]['nodes'].items()}
                if native not in table:
                    raise ValueError('명시한 원 절점이 선택한 고체에 없습니다.')
                effective.append(table[native])
            a,b = effective
            if a in mapping or b in mapping.values() or a == b:
                raise ValueError('접합 절점은 서로 다른 DOF로 일대일 대응해야 합니다.')
            if nodes[a]['position_mm'] != nodes[b]['position_mm']:
                raise ValueError('영두께 계면의 대응 절점은 같은 위치여야 합니다. 절점을 자동 이동하지 않습니다.')
            mapping[a] = b
        if (set(mapping) != {n for f in sides['a'][1] for n in f}
                or set(mapping.values()) != {n for f in sides['b'][1] for n in f}):
            raise ValueError('선택한 두 면의 모든 원 절점에 명시한 일대일 대응이 필요합니다.')
        for a_face in sides['a'][1]:
            b_face = [mapping[n] for n in a_face]
            matching = [f for f in sides['b'][1] if set(f) == set(b_face)]
            if len(matching) != 1:
                raise ValueError('대응 절점이 정확히 하나의 B면을 이루지 않습니다.')
            points = [nodes[n]['position_mm'] for n in a_face]
            basis = _basis(points,0.,0.)
            b_basis = _basis([nodes[n]['position_mm'] for n in matching[0]],0.,0.)
            if math.fsum(a*b for a,b in zip(basis['normal'],b_basis['normal'])) >= 0:
                raise ValueError('두 고체의 접합 면은 서로 반대인 바깥쪽 법선을 가져야 합니다.')
            quadrature = [_basis(points,x,y) for x,y in ((-gp,-gp),(gp,-gp),(gp,gp),(-gp,gp))]
            for point,sample in enumerate(quadrature,1):
                sample.update(point=point,reference_weight=1.)
            if any(math.fsum(a*b for a,b in zip(q['normal'],basis['normal'])) <= 0 for q in quadrature):
                raise ValueError('접합 사각형 면의 법선 방향이 내부에서 반전됩니다.')
            result.append(dict(element_id=next_id, interface_id=identifier,
                label=definition['label'], node_ids=a_face+b_face,
                material=deepcopy(material), compression_policy=deepcopy(COMPRESSION_POLICY),
                source_node_pairs=deepcopy(raw_pairs),
                source_body_ids=[sides['a'][0],sides['b'][0]],
                local_basis=basis, local_basis_location='FACE_CENTER_PREVIEW_ONLY',
                b_outward_normal=b_basis['normal'], quadrature=quadrature,
                quadrature_order='CODE_ASTER_QU4_FPG4_REFERENCE',
                modelisation='3D_JOINT', native_type='HEXA8',
                source_commit=SOURCE, node_policy='COINCIDENT_SEPARATE_BODY_DOFS'))
            next_id += 1
    return result
