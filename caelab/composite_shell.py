"""Explicit S8R laminate profile; editable raw text, no homogenization or CAD imports."""
from copy import deepcopy
import math

from .shell_model import ShellError, issue, number, unit, prepare_geometry, EDGES

BACKEND = 'structure.calculix.shell.composite'
PROFILE = 'CCX222_S8R_COMPOSITE_GLOBAL_IP'
ORTHOTROPIC = ('E1_MPa','E2_MPa','E3_MPa','nu12','nu13','nu23','G12_MPa','G13_MPa','G23_MPa')
ISOTROPIC = ('E_MPa','nu')


def default_draft(analysis_id, mesh_id, solver_id):
    return {'analysis_id':analysis_id,'mesh_id':mesh_id,'solver_id':solver_id,
            'regions':[], 'materials':{}, 'fixed_nodes':[], 'binding':None}


def material_values(record):
    if not isinstance(record,dict) or record.get('law') not in ('isotropic_linear','orthotropic_linear'):
        raise ValueError('등방 또는 직교이방성 선형 탄성 법칙을 명시하세요.')
    names = ISOTROPIC if record['law']=='isotropic_linear' else ORTHOTROPIC
    if set(record.get('constants',{})) != set(names):
        raise ValueError('선택한 법칙의 모든 탄성 상수를 명시하세요.')
    values={name:number(record['constants'][name]) for name in names}
    if record['law']=='isotropic_linear':
        if values['E_MPa']<=0 or not -1<values['nu']<.5:
            raise ValueError('등방 탄성은 E>0, −1<ν<0.5를 요구합니다.')
    else:
        if any(values[n]<=0 for n in ('E1_MPa','E2_MPa','E3_MPa','G12_MPa','G13_MPa','G23_MPa')):
            raise ValueError('세 Young 계수와 세 전단 계수는 0보다 커야 합니다.')
        e1,e2,e3=(values[n] for n in ('E1_MPa','E2_MPa','E3_MPa'))
        # nu_ij = -epsilon_j/epsilon_i under uniaxial sigma_i. Reciprocity
        # gives nu21=nu12 E2/E1, etc. Orthotropic nu is not an isotropic nu.
        compliance=[[1/e1,-values['nu12']/e1,-values['nu13']/e1],
                    [-values['nu12']/e1,1/e2,-values['nu23']/e2],
                    [-values['nu13']/e1,-values['nu23']/e2,1/e3]]
        scale=max(abs(x) for row in compliance for x in row)
        matrix=[[x/scale for x in row] for row in compliance]
        factor=[[0.]*3 for _ in range(3)]
        for i in range(3):
            for j in range(i+1):
                value=matrix[i][j]-sum(factor[i][k]*factor[j][k] for k in range(j))
                if i==j:
                    if not math.isfinite(value) or value<=0:
                        raise ValueError('직교이방성 탄성 compliance가 양의 정부호가 아닙니다. 상수와 축 정의를 확인하세요.')
                    factor[i][j]=math.sqrt(value)
                else: factor[i][j]=value/factor[j][j]
    return {'law':record['law'],'constants':values}


def validate(draft):
    errors=[]; materials={}; regions=[]; occupied=set(); ply_ids=set()
    if not isinstance(draft,dict):return [issue('layup','적층 초안을 읽을 수 없습니다.')],None
    if not isinstance(draft.get('regions'),list) or not isinstance(draft.get('materials'),dict):
        return [issue('layup','참여 영역과 원 재료 목록을 확인하세요.')],None
    used={p.get('material_id') for r in draft.get('regions',[]) if isinstance(r,dict) and isinstance(r.get('plies'),list)
          for p in r.get('plies',[]) if isinstance(p,dict)}
    for name,record in draft.get('materials',{}).items():
        if name not in used:continue
        try:materials[name]=material_values(record)
        except (ValueError,TypeError,KeyError) as exc:errors.append(issue('materials/'+name,str(exc)))
    rows=draft.get('regions')
    if not isinstance(rows,list) or not rows or len(rows)>256:
        return errors+[issue('regions','참여할 셸 면 또는 요소 영역을 선택하세요.')],None
    names=set()
    for i,row in enumerate(rows):
        path=f'regions/{i}'
        try:
            if not isinstance(row,dict) or not isinstance(row.get('id'),str) or row['id'] in names:
                raise ValueError('영역의 고유 대상을 확인하세요.')
            names.add(row['id'])
            elements=row.get('elements')
            if (not isinstance(elements,list) or not elements or
                any(type(e) is not int or e<=0 for e in elements) or len(set(elements))!=len(elements) or occupied.intersection(elements)):
                raise ValueError('각 영역에는 중복하지 않는 실제 8절점 셸 요소를 지정하세요.')
            occupied.update(elements)
            if row.get('orientation') not in ('native','reversed'):
                raise ValueError('선택 요소의 법선을 확인하고 방향을 명시하세요.')
            axis=unit([number(v) for v in row['axis']])
            if len(axis)!=3:raise ValueError('기준축은 전역 세 성분입니다.')
            offset=number(row['offset']); pressure=number(row['pressure_MPa'])
            plies=row.get('plies')
            if not isinstance(plies,list) or not 2<=len(plies)<=16:
                raise ValueError('각 영역에 2–16개 층을 명시하세요.')
            prepared=[]
            for j,ply in enumerate(plies):
                pp=path+f'/plies/{j}'
                try:
                    if not isinstance(ply,dict) or not isinstance(ply.get('id'),str) or ply['id'] in ply_ids:
                        raise ValueError('층의 고유 대상을 확인하세요.')
                    ply_ids.add(ply['id'])
                    thickness=number(ply['thickness_mm']); angle=number(ply['angle_deg'])
                    if thickness<=0:raise ValueError('층 두께는 0보다 커야 합니다.')
                    if ply.get('material_id') not in materials:raise ValueError('이 층의 유효한 원 재료를 선택하세요.')
                    prepared.append({**ply,'thickness_mm':thickness,'angle_deg':angle})
                except (ValueError,KeyError,TypeError) as exc:errors.append(issue(pp,str(exc)))
            total=sum(p['thickness_mm'] for p in prepared)
            if not math.isfinite(total):raise ValueError('층 총두께가 유한 범위를 넘었습니다.')
            regions.append({**row,'axis':list(axis),'offset':offset,'pressure_MPa':pressure,
                            'plies':prepared,'thickness_mm':total})
        except (ValueError,KeyError,TypeError) as exc:errors.append(issue(path,str(exc)))
    fixed=draft.get('fixed_nodes',[])
    if not isinstance(fixed,list) or any(type(n) is not int or n<=0 for n in fixed) or len(set(fixed))!=len(fixed):
        errors.append(issue('fixed_nodes','고정 절점은 중복 없는 실제 절점 번호여야 합니다.'))
    return errors,None if errors else {'materials':materials,'regions':regions}


def prepare_mesh(nodes,elements,draft):
    errors,values=validate(draft)
    if errors:raise ShellError(errors)
    meshes=[]; lookup={}
    for region in values['regions']:
        properties={k:region[k] for k in ('axis','orientation','offset','pressure_MPa','thickness_mm')}
        mesh=prepare_geometry(nodes,elements,region,properties)
        meshes.append(mesh)
        for e in mesh['elements']:lookup[e]=region
    merged={key:{k:v for mesh in meshes for k,v in mesh[key].items()}
            for key in ('nodes','elements','normals','axes','areas_mm2')}
    # Enforce the same shared-edge orientation rule across region boundaries.
    edges={}
    for e,conn in merged['elements'].items():
        for a,b,m in EDGES:
            edges.setdefault(tuple(sorted((conn[a],conn[b]))),[]).append((conn[a],conn[b],conn[m]))
    if any(len(rows)>2 or len(rows)==2 and rows[0]!=(rows[1][1],rows[1][0],rows[1][2]) for rows in edges.values()):
        raise ShellError([issue('regions','서로 만나는 영역의 법선 또는 중간 절점이 다릅니다. 요소 방향을 수정하세요.')])
    merged.update(region_by_element=lookup,values=values)
    return merged


def ply_axes(axes,angle_deg):
    x,y,n=axes; angle=math.radians(angle_deg); c,s=math.cos(angle),math.sin(angle)
    return ([c*a+s*b for a,b in zip(x,y)],[-s*a+c*b for a,b in zip(x,y)],list(n))


def move_ply(draft,region_id,ply_id,delta):
    out=deepcopy(draft)
    region=next(r for r in out['regions'] if r['id']==region_id)
    index=next(i for i,p in enumerate(region['plies']) if p['id']==ply_id)
    if delta not in (-1,1) or not 0<=index+delta<len(region['plies']):raise ValueError('이동할 층 위치를 확인하세요.')
    region['plies'][index],region['plies'][index+delta]=region['plies'][index+delta],region['plies'][index]
    return out


def reverse_region(draft,region_id):
    """Explicit normal reversal preserving physical layer positions and axes."""
    out=deepcopy(draft);row=next(r for r in out['regions'] if r['id']==region_id)
    if row['orientation'] not in ('native','reversed'):raise ValueError('먼저 현재 법선을 선택하세요.')
    row['offset']=str(-number(row['offset']));row['pressure_MPa']=str(-number(row['pressure_MPa']))
    row['orientation']='reversed' if row['orientation']=='native' else 'native'
    row['plies'].reverse()
    for ply in row['plies']:ply['angle_deg']=str(-number(ply['angle_deg']))
    return out
