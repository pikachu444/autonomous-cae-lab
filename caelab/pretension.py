"""Actual C3D10 internal mesh cuts for CalculiX 2.22 pretension.

No display-plane section, remeshing, torque conversion or constant-force hold.
The native solver cuts the selected element faces and owns the extra DOF.
"""
from copy import deepcopy
import math
from .contact import number
from .contact_deck import FACES,name
from .impact_sets import facets,sub as _minus,dot as _dot

OPERATIONS=('pre.fem.pretension_read','pre.fem.pretension_faces',
            'pre.fem.pretension_set','pre.fem.pretension_remove','pre.fem.pretension_highlight',
            'pre.fem.pretension_save_editor')
PROFILE='calculix-2.22-c3d10-planar-internal-cut-static'


def normalize(draft):
    if not isinstance(draft,dict) or set(draft)!={'label','mesh_id','element_faces','axis','control'}:
        raise ValueError('체결 이름·메시·실제 절단면·축·조임 방식을 확인하세요.')
    if not isinstance(draft['label'],str) or not draft['label'].strip() or len(draft['label'])>160:
        raise ValueError('체결 조건 이름을 입력하세요.')
    name(draft['mesh_id'])
    faces=draft['element_faces']
    if (not isinstance(faces,list) or not faces or len(faces)>100000 or
        any(not isinstance(p,list) or len(p)!=2 or any(type(i) is not int for i in p)
            or p[0]<1 or p[1] not in FACES for p in faces) or len({tuple(p) for p in faces})!=len(faces)):
        raise ValueError('중복 없는 실제 고체 요소면을 선택하세요.')
    raw=draft['axis']
    if not isinstance(raw,list) or len(raw)!=3:raise ValueError('체결 축의 XYZ 성분을 입력하세요.')
    axis=[number(v) for v in raw];size=math.hypot(*axis)
    if not math.isfinite(size) or size<=0:raise ValueError('체결 축은 0이 아닌 유한한 방향이어야 합니다.')
    control=draft['control']
    if not isinstance(control,dict) or set(control)!={'kind','value'} or control['kind'] not in ('force_N','section_displacement_mm'):
        raise ValueError('조임력 [N] 또는 절단면 길이 변화 [mm]를 선택하세요. 토크 환산은 지원하지 않습니다.')
    value=number(control['value'])
    if value<=0:raise ValueError('선택한 인장 축의 조임값은 양수여야 합니다.')
    return {**deepcopy(draft),'element_faces':sorted(faces),'axis':[v/size for v in axis],
            'control':{'kind':control['kind'],'value':value}}


def face_catalog(model,body_id):
    """Exact 6-node incidence; shared vertices alone are never a cut face."""
    elements={r['element_id']:r for r in model['elements'] if r['body_id']==body_id}
    nodes={r['node_id']:r['position_mm'] for r in model['nodes']}
    for eid,row in elements.items():
        if row['type']!='C3D10' or len(row['node_ids'])!=10:raise ValueError('체결 절단면은 C3D10 고체 메시를 지원합니다.')
    # Adapt only the pure topology view. Impact source/name/recipe owners remain separate.
    view={'nodes':nodes,'elements':{e:{'type':r['type'],'nodes':r['node_ids']} for e,r in sorted(elements.items())}}
    incidence={}
    for face in facets(view):
        if face['internal']:incidence.setdefault(tuple(sorted(face['corners'])),[]).append(face)
    result=[]
    for owners in incidence.values():
        first,second=owners;area=first['area']
        result.append({'element_face':[first['element'],int(first['side'][1:])],
            'opposite_face':[second['element'],int(second['side'][1:])],
            'node_ids':list(first['nodes']),'centroid_mm':first['center'],
            'normal':[v/(2*area) for v in first['normal']],'area_mm2':area})
    return sorted(result,key=lambda r:r['element_face'])


def validate_cut(model,section):
    """Complete planar separator, exact binding retained by the native collector."""
    draft=normalize(section['draft']);body=section['body_id']
    elements={r['element_id']:r['node_ids'] for r in model['elements'] if r['body_id']==body}
    nodes={r['node_id']:r['position_mm'] for r in model['nodes']}
    if not elements:raise ValueError('체결 메시의 원 body가 없습니다.')
    catalog=face_catalog(model,body);pairs={}
    for row in catalog:
        pairs[tuple(row['element_face'])]=row
        reverse=deepcopy(row);reverse['element_face'],reverse['opposite_face']=row['opposite_face'],row['element_face']
        reverse['normal']=[-x for x in row['normal']]
        pairs[tuple(reverse['element_face'])]=reverse
    chosen=[];used=set();selected_elements=set();cut_nodes=set()
    for face in draft['element_faces']:
        row=pairs.get(tuple(face))
        if row is None:raise ValueError('절단면은 같은 body의 두 고체 요소가 공유하는 실제 내부 면이어야 합니다.')
        key=tuple(sorted((tuple(row['element_face']),tuple(row['opposite_face']))))
        if key in used:raise ValueError('같은 절단면의 양쪽을 중복 선택하지 마세요.')
        used.add(key);chosen.append(row);selected_elements.add(face[0]);cut_nodes.update(row['node_ids'])
        if _dot(row['normal'],draft['axis'])<1-1e-10:
            raise ValueError('절단면 법선과 체결 축이 일치하지 않습니다. 반대쪽 요소면 또는 축을 선택하세요.')
    anchor=nodes[next(iter(cut_nodes))]
    scale=max(math.dist(anchor,nodes[n]) for n in cut_nodes)
    # Relative round-off gate on retained geometry, never a user fit tolerance.
    if any(abs(_dot(_minus(nodes[n],anchor),draft['axis']))>max(scale,1.)*1e-10 for n in cut_nodes):
        raise ValueError('첫 지원은 실제 메시의 평면 절단면입니다. 표시용 평면으로 요소를 자르지 않습니다.')
    adjacency={e:set() for e in elements}
    for row in catalog:
        a,b=tuple(row['element_face']),tuple(row['opposite_face'])
        if tuple(sorted((a,b))) not in used:adjacency[a[0]].add(b[0]);adjacency[b[0]].add(a[0])
    components=[];remaining=set(elements)
    while remaining:
        stack=[next(iter(remaining))];part=set()
        while stack:
            e=stack.pop()
            if e in part:continue
            part.add(e);stack.extend(adjacency[e]-part)
        remaining-=part;components.append(part)
    if len(components)!=2 or not any(selected_elements<=c for c in components):
        raise ValueError('선택한 면이 볼트 메시를 두 부분으로 완전히 나누지 않습니다. 누락되거나 섞인 면을 수정하세요.')
    # 2.22 duplicates nodes only in the selected face-owning elements.
    # Edge/vertex-only incident elements would leave an unintended ligament.
    touching={e for r in chosen for e in (r['element_face'][0],r['opposite_face'][0])}
    for eid,ids in elements.items():
        if set(ids)&cut_nodes and eid not in touching:
            raise ValueError('절단면에 꼭짓점/모서리로만 연결된 요소가 있습니다. 원 메시의 절단 구획을 수정하세요.')
    contact_elements={e for p in model.get('contacts',[]) for side in ('a','b') for e,f in p[side]['element_faces']}
    if any(set(ids)&cut_nodes for e,ids in elements.items() if e in contact_elements):
        raise ValueError('2차 접촉 요소에 인접한 절단면은 이 체결 경로에서 지원하지 않습니다.')
    return {'draft':draft,'node_ids':sorted(cut_nodes),'area_mm2':sum(r['area_mm2'] for r in chosen),
            'components':[sorted(c) for c in components]}


def sections(model):
    rows=model.get('pretension_sections',[])
    if not rows:return []
    from .contact_steps import compile_program
    from .calculix_material import has_plasticity
    if (model.get('restart') or model.get('dynamic') or model.get('periodic_constraints') or model['step']['geometry']!='linear' or has_plasticity(model)):
        raise ValueError('체결 첫 지원은 새 계산의 소변형·선형 탄성 정적 단계입니다.')
    program=model.get('analysis_steps')
    if not program:raise ValueError('체결은 조임→길이 고정→외력의 세 정적 단계를 작성하세요.')
    stages=compile_program(program,model['conditions'])
    if len(stages)<3 or any(s['procedure']!='static' for s in stages):
        raise ValueError('체결은 조임→길이 고정→외력의 세 정적 단계가 필요합니다.')
    for step in stages[:2]:
        if any(v!=0 for points in step['loads'].values() for t,v in points):
            raise ValueError('외력은 세 번째 단계부터 적용하세요. 처음 두 단계는 조임과 길이 고정입니다.')
        if any(v!=0 for points in step['boundary'].values() for t,v in points):
            raise ValueError('처음 두 체결 단계의 일반 지정 변위는 0이어야 합니다.')
    used=set();ids=set();result=[];next_node=max(r['node_id'] for r in model['nodes'])
    for index,row in enumerate(rows,1):
        identifier=name(row['id'])
        if len(identifier)>48 or identifier.upper() in ids:raise ValueError('중복 체결 조건을 수정하세요.')
        ids.add(identifier.upper());cut=validate_cut(model,row)
        overlap=set(cut['node_ids'])&used
        if overlap:raise ValueError('같은 절단면/절점을 둘 이상의 체결 조건에 사용하지 마세요.')
        axis=cut['draft']['axis'];cut_ids=set(cut['node_ids'])
        for condition in model.get('conditions',[]):
            if any(row['node_id'] in cut_ids and axis[int(row['component'])-1]!=0
                   for row in condition.get('boundary_dofs',[])):
                raise ValueError('절단 절점의 축방향 지지는 복제 쪽을 구분할 수 없습니다. 원 끝면에서 지지를 선택하세요.')
            if any(row['node_id'] in cut_ids and axis[int(row['component'])-1]!=0 and row['weight']!=0
                   for row in condition.get('force_weights',[])):
                raise ValueError('절단 절점의 축방향 하중 대신 실제 끝면을 선택하세요.')
        used.update(cut['node_ids'])
        result.append({**deepcopy(row),**cut,'reference_node':next_node+index,
            'surface_name':'PTSEC'+identifier,'reference_set':'PTRP'+identifier,
            'tighten_step':1,'hold_step':2,'external_load_start_step':3})
    return result


def expected_solver_mesh(model):
    """2.22 pretensionsections.f face/node iteration, not inferred FRD repair."""
    rows=sections(model);result=deepcopy(model)
    if not rows:return result,[]
    nodes={r['node_id']:r for r in result['nodes']};elements={r['element_id']:r for r in result['elements']}
    next_node=max(r['reference_node'] for r in rows);copies=[]
    for section in rows:
        mapping={}
        for eid,face in section['draft']['element_faces']:
            for slot in FACES[face]:
                original=elements[eid]['node_ids'][slot]
                if original not in mapping:
                    next_node+=1;mapping[original]=next_node
                    clone={**deepcopy(nodes[original]),'node_id':next_node,'pretension_source_node_id':original,
                           'pretension_section_id':section['id']}
                    result['nodes'].append(clone)
                    copies.append({'source_node_id':original,'solver_node_id':next_node,'section_id':section['id']})
                elements[eid]['node_ids'][slot]=mapping[original]
    if next_node>=2**31:raise ValueError('체결 참조/복제 절점이 native 정수 한도를 넘습니다.')
    result['pretension_node_copies']=copies
    return result,copies


def three_step_program(step,conditions):
    """Explicit UI proposal in the existing contact stage schema; no apply here."""
    from .contact_steps import default_program
    base=deepcopy(step) if 'duration' in step else default_program(step,conditions)['steps'][0];out=[]
    for i,label in enumerate(('조임','길이 고정','외력'),1):
        row=deepcopy(base);row.update(id='Step'+str(i),label=label)
        for curve in row['curves']:
            value=curve['points'][-1][1] if i==3 else 0.
            curve['points']=[[0.,0.],[row['duration'],value]]
        out.append(row)
    return {'schema_version':'1','procedure':'static','steps':out}
