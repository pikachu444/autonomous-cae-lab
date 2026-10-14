"""Explicit derived targets on the admitted original impact mesh.

Topology uses original IDs (never coordinate welding); TYPE24 uses corner facets.
These checks do not certify curved-element Jacobians or engineering mesh quality.
"""
from copy import deepcopy
from collections import defaultdict
import hashlib
import math

TET = ((0,2,1),(0,1,3),(1,2,3),(2,0,3))
TET10 = ((0,2,1,6,5,4),(0,1,3,4,8,7),(1,2,3,5,9,8),(2,0,3,6,7,9))
HEX = ((0,3,2,1),(7,4,5,6),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7))


def sub(a,b): return [x-y for x,y in zip(a,b)]
def cross(a,b): return [a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]]
def dot(a,b): return sum(x*y for x,y in zip(a,b))
def center(points): return [sum(p[i] for p in points)/len(points) for i in range(3)]


def facets(model):
    result = []
    for eid, element in model['elements'].items():
        kind, conn = element['type'], element['nodes']
        patterns = TET if kind in ('C3D4','C3D10') else HEX
        middle = center([model['nodes'][n] for n in conn[:4 if kind.startswith('C3D1') or kind=='C3D4' else 8]])
        if kind == 'COH3D8':
            from .impact_damage import geometry
            geometry(model, eid)
        for index, pattern in enumerate(patterns):
            corners = tuple(conn[i] for i in pattern)
            full = tuple(conn[i] for i in TET10[index]) if kind=='C3D10' else corners
            xyz = [model['nodes'][n] for n in corners]
            normal = cross(sub(xyz[1],xyz[0]),sub(xyz[2],xyz[0]))
            if not math.isfinite(dot(normal,normal)) or dot(normal,normal)<=0 or dot(normal, sub(center(xyz), middle))<=0:
                raise ValueError(f'요소 {eid} S{index+1}: 퇴화하거나 뒤집힌 모서리 면입니다')
            if len(xyz)==4 and dot(normal,cross(sub(xyz[2],xyz[0]),sub(xyz[3],xyz[0])))<=0:
                raise ValueError(f'요소 {eid} S{index+1}: 접힌 사각면입니다')
            edges = tuple(sorted((tuple(sorted((corners[j],corners[(j+1)%3]))),full[3+j]) for j in range(3))) if kind=='C3D10' else ()
            result.append({'element':eid,'side':f'S{index+1}','type':kind,'corners':corners,
                'nodes':full,'edges':edges,'normal':normal,'center':center(xyz),
                'area':math.sqrt(dot(normal,normal))/2 + (math.sqrt(dot(cross(sub(xyz[2],xyz[0]),sub(xyz[3],xyz[0])),cross(sub(xyz[2],xyz[0]),sub(xyz[3],xyz[0]))))/2 if len(xyz)==4 else 0)})
    groups = defaultdict(list)
    for face in result: groups[tuple(sorted(face['corners']))].append(face)
    for group in groups.values():
        if len(group)>2: raise ValueError('세 요소 이상이 공유하는 비다양체 면: '+str([f['element'] for f in group]))
        if len(group)==2:
            a,b = group
            if a['edges'] != b['edges']: raise ValueError(f"요소 {a['element']}/{b['element']}: 중간 절점 대응이 다른 비정합 면입니다")
            reverse = tuple(reversed(a['corners']))
            if not any(b['corners']==reverse[k:]+reverse[:k] for k in range(len(reverse))):
                raise ValueError('공유 면 방향이 같은 중복/뒤집힌 요소입니다')
        for face in group: face['internal'] = len(group)==2
    return result


def candidates(model, elset, mode='exterior'):
    if elset not in model['elsets']: raise ValueError('원 요소 집합을 선택하세요')
    if mode not in ('exterior','explicit'): raise ValueError('면 선택 방식을 확인하세요')
    members = model['elsets'][elset]
    return [f for f in facets(model) if f['element'] in members
            and (f['type']!='COH3D8' or f['side'] in ('S1','S2'))
            and (mode=='explicit' or not f['internal'])]


def source_digest(source):
    from .impact_source import resolve
    text,_ = resolve(source)
    return hashlib.sha256(text.encode('ascii')).hexdigest()


def create_node_set(source, model, name, elset):
    from .impact_model import NAME
    name = name.strip().upper()
    if not NAME.fullmatch(name) or name in model['nsets']: raise ValueError('중복되지 않는 영문 집합 이름을 입력하세요')
    if elset not in model['elsets']: raise ValueError('원 요소 집합을 선택하세요')
    nodes = sorted({n for e in model['elsets'][elset] for n in model['elements'][e]['nodes']})
    return {'kind':'nset','name':name,'elset':elset,'nodes':nodes,'source_sha256':source_digest(source)}


def create_surface(source, model, name, elset, mode, faces, *, allow_internal=False):
    from .impact_model import NAME
    name = name.strip().upper()
    if not NAME.fullmatch(name) or name in model['surfaces']: raise ValueError('중복되지 않는 영문 면 이름을 입력하세요')
    available = {(f['element'],f['side']):f for f in candidates(model,elset,mode)}
    if type(allow_internal) is not bool:
        raise ValueError('내부면 사용 여부를 명시하세요')
    if not isinstance(faces,list) or any(not isinstance(v,(list,tuple)) or len(v)!=2 or type(v[0]) is not int or v[0]<=0 or type(v[1]) is not str for v in faces):
        raise ValueError('요소 면은 양의 정수 요소 번호와 면 이름이 필요합니다')
    chosen = [tuple(v) for v in faces]
    if not chosen or len(set(chosen))!=len(chosen) or any(f not in available for f in chosen):
        raise ValueError('미리보기에서 유효한 요소 면을 하나 이상 선택하세요')
    if any(available[f]['internal'] for f in chosen) and not allow_internal:
        raise ValueError('선택에 내부면이 있습니다. 해당 요소 면의 사용을 명시적으로 확인하세요')
    return {'kind':'surface','name':name,'elset':elset,'mode':mode,'faces':[list(f) for f in sorted(chosen)],
        'allow_internal':bool(allow_internal),'source_sha256':source_digest(source)}


def apply(model, source, definitions):
    if not isinstance(definitions,list) or len(definitions)>256: raise ValueError('생성 집합은 최대 256개입니다')
    result=deepcopy(model)
    identity=source_digest(source) if definitions else None
    for definition in definitions:
        if definition.get('source_sha256')!=identity: raise ValueError('생성 집합의 원 메시가 변경되었습니다. 집합을 다시 선택하세요')
        if definition.get('kind')=='nset':
            if not isinstance(definition.get('nodes'),list) or any(type(n) is not int or n<=0 for n in definition['nodes']):
                raise ValueError('절점 번호는 양의 정수여야 합니다')
            checked=create_node_set(source,result,definition['name'],definition['elset'])
            if checked!=definition: raise ValueError('생성 절점 집합이 원 요소 연결과 다릅니다')
            result['nsets'][checked['name']]=set(checked['nodes'])
        elif definition.get('kind')=='surface':
            checked=create_surface(source,result,definition['name'],definition['elset'],definition['mode'],definition['faces'],allow_internal=definition.get('allow_internal',False))
            if checked!=definition: raise ValueError('생성 면 정의가 원 요소 면과 다릅니다')
            result['surfaces'][checked['name']]=[(str(e),s) for e,s in checked['faces']]
        else: raise ValueError('생성 집합의 종류를 확인하세요')
    return result


def references(settings, definition):
    name=definition['name']
    if definition['kind']=='nset':
        return ['초기 운동 '+str(i+1) for i,m in enumerate(settings['motions']) if m.get('node_set')==name]
    return ['접촉 '+str(i+1) for i,p in enumerate(settings['contacts']) if name in (p.get('a'),p.get('b'))]


def delete(settings, index):
    value=deepcopy(settings); definition=value['generated_sets'][index]
    used=references(value,definition)
    if used: raise ValueError('사용 중: '+', '.join(used)+'. 먼저 조건의 대상을 바꾸거나 조건을 삭제하세요')
    del value['generated_sets'][index]
    return value


def summary(model, node_ids, element_ids=(), face_count=0):
    points=[model['nodes'][n] for n in node_ids]
    return {'nodes':len(node_ids),'elements':len(element_ids),'faces':face_count,
        'bounds_mm':[[min(p[i] for p in points),max(p[i] for p in points)] for i in range(3)] if points else None}
