"""B32R/RECT admission and coordinate semantics; no beam stiffness solver.

Native connectivity is Seg3 [start, end, mid]. CalculiX input is
[start, mid, end]. Axes are (local1, local2, tangent), right handed.
Raw edit strings are kept by the native metadata owner, never rounded in-place.
"""
from copy import deepcopy
import math
import re

BACKEND = 'structure.calculix.beam'
NAMESPACE = 'beam_models'
SCHEMA = 'caelab-beam/1'
NUMBER = re.compile(r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?\Z')
OPERATIONS = ('pre.beam.inspect','pre.beam.create','pre.beam.draft','pre.beam.apply',
              'pre.beam.rebind','pre.beam.import_properties','pre.beam.freeze')
AXIS_TOL = 1e-11  # geometric direction/serialization gate, not a result tolerance


class BeamInputError(ValueError):
    def __init__(self, path, message):
        self.path, self.message = path, message
        super().__init__(path + ': ' + message)

    def record(self):
        return {'path': self.path, 'message': self.message}


def number(value, path='value'):
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise BeamInputError(path, '숫자를 입력하세요.')
    text = str(value).strip()
    if not NUMBER.fullmatch(text):
        raise BeamInputError(path, '숫자를 끝까지 입력하세요. 예: 1e3')
    result = float(text)
    if not math.isfinite(result):
        raise BeamInputError(path, '유한한 숫자를 입력하세요.')
    return result


def vector(value, path='vector'):
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise BeamInputError(path, '세 성분을 입력하세요.')
    return [number(v, f'{path}.{i}') for i, v in enumerate(value)]


def dot(a, b):
    return sum(x*y for x, y in zip(a, b))


def cross(a, b):
    return [a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]]


def sub(a, b):
    return [x-y for x, y in zip(a, b)]


def unit(v, path='axis'):
    v = vector(v, path)
    length = math.hypot(*v)
    if length == 0:
        raise BeamInputError(path, '방향이 없습니다. 서로 다른 끝점을 선택하세요.')
    return [x/length for x in v]


def native_axis_formula(tangent, rotation_deg):
    """Independent test oracle for installed meshtools.get_beam_main_axis_m.

    Source: supplied FreeCAD 1.1.4 femmesh/meshtools.py lines 587-671.
    The executable formula, not its older contradictory comment, is authoritative.
    Native collection calls the installed function and compares these axes.
    """
    t = unit(tangent)
    x, y, z = t
    if z == 0:
        n = [0., 0., -1.]
    elif x == 0 and y == 0:
        n = [-1., 0., 0.]
    else:
        n = [x, y, -(x*x+y*y)/z]
    n = unit([(-1 if z > 0 else 1)*v for v in n])
    angle = math.radians(number(rotation_deg, 'section.rotation_deg') + 90)
    m = [a*math.cos(angle)+b*math.sin(angle) for a, b in zip(n, cross(t, n))]
    return [0. if abs(v) <= 1e-15 else v for v in m]


def frame(tangent, local1):
    t, a = unit(tangent), unit(local1, 'section.local1')
    if abs(dot(t, a)) > AXIS_TOL:
        raise BeamInputError('section.local1', '단면 1축이 빔 길이 방향과 직각이 아닙니다.')
    b = unit(cross(t, a), 'section.local2')
    return {'local1': a, 'local2': b, 'tangent': t}


def to_global(values, system, axes):
    values = vector(values)
    if system == 'global':
        return values
    if system != 'local':
        raise BeamInputError('system', '전체 좌표계 또는 단면 좌표계를 선택하세요.')
    return [sum(values[j]*axes[k][i] for j, k in enumerate(('local1','local2','tangent')))
            for i in range(3)]


def boundary_global(values, system, axes, path):
    """Preserve free DOFs; do not rotate a mask as if it were a vector.

    Partial local constraints are admitted only for axes that coincide with
    signed global axes. Fully prescribed triplets can always be transformed.
    No *TRANSFORM is attached to nodes carrying rotational constraints (ccx rule).
    """
    if not isinstance(values, list) or len(values) != 3:
        raise BeamInputError(path, '세 성분을 입력하세요. 자유 성분은 비워 둡니다.')
    v = [None if x is None or isinstance(x, str) and not x.strip()
         else number(x, f'{path}.{i}') for i, x in enumerate(values)]
    if system == 'global':
        return v
    if system != 'local':
        raise BeamInputError(path, '좌표계를 선택하세요.')
    if all(x is not None for x in v):
        return to_global(v, system, axes)
    result = [None]*3
    for value, key in zip(v, ('local1','local2','tangent')):
        if value is None:
            continue
        a = axes[key]
        i = max(range(3), key=lambda k: abs(a[k]))
        if abs(abs(a[i])-1) > AXIS_TOL or any(abs(a[j]) > AXIS_TOL for j in range(3) if j != i):
            raise BeamInputError(path, '기울어진 단면의 일부 구속은 아직 지원하지 않습니다. 전체 좌표계로 지정하거나 세 성분을 모두 지정하세요.')
        result[i] = value*(1 if a[i] > 0 else -1)
    return result


def default_end(label, reference=None):
    return {'label':label, 'reference':reference or {'object':'', 'subelement':''},
            'system':'global', 'force_N':['0']*3, 'moment_Nmm':['0']*3,
            'translation_mm':['']*3, 'rotation_deg':['']*3}


def default_draft(analysis_id='', mesh_id='', edge=None):
    return {'analysis_id':analysis_id, 'mesh_id':mesh_id,
            'edge':edge or {'object':'', 'subelement':''},
            'section':{'object_id':'', 'rotation_id':'', 'width_mm':'10', 'height_mm':'20', 'rotation_deg':'0'},
            'material':{'object_id':'', 'young_MPa':'210000', 'poisson':'0.3'},
            'ends':[default_end('끝 1'), default_end('끝 2')], 'diagnostic_oblique':False}


def check_draft_shape(draft):
    """Versioned command structure; unfinished scalar strings are intentional."""
    required={'analysis_id','mesh_id','edge','section','material','ends','diagnostic_oblique'}
    if not isinstance(draft,dict) or not required <= set(draft) or set(draft)-required-{'output','axis_regions'}:
        raise BeamInputError('draft','빔 초안의 필수 항목 또는 버전이 다릅니다.')
    from .beam_output import check_shape as check_output_shape, check_axis_shape
    if 'output' in draft: check_output_shape(draft['output'])
    if 'axis_regions' in draft: check_axis_shape(draft['axis_regions'])
    def keys(value,expected,path):
        if not isinstance(value,dict) or set(value)!=set(expected):
            raise BeamInputError(path,'설정 항목 또는 버전이 다릅니다.')
    keys(draft['section'],('object_id','rotation_id','width_mm','height_mm','rotation_deg'),'section')
    keys(draft['material'],('object_id','young_MPa','poisson'),'material')
    keys(draft['edge'],('object','subelement'),'edge')
    if not isinstance(draft['ends'],list) or len(draft['ends'])!=2:
        raise BeamInputError('ends','두 끝 조건이 필요합니다.')
    for i,end in enumerate(draft['ends']):
        keys(end,('label','reference','system','force_N','moment_Nmm','translation_mm','rotation_deg'),f'ends.{i}')
        keys(end['reference'],('object','subelement'),f'ends.{i}.reference')
        for key in ('force_N','moment_Nmm','translation_mm','rotation_deg'):
            if not isinstance(end[key],list) or len(end[key])!=3:
                raise BeamInputError(f'ends.{i}.{key}','세 성분이 필요합니다.')
        if not isinstance(end['label'],str) or len(end['label'])>160:
            raise BeamInputError(f'ends.{i}.label','끝 이름은 160자 이내로 입력하세요.')


def validate_draft(draft, axes=None):
    """Return all scalar edit errors, not just the first failing cell."""
    try:check_draft_shape(draft)
    except BeamInputError as exc:return [exc.record()]
    errors = []
    def check(path, fn):
        try:
            fn()
        except (BeamInputError, KeyError, TypeError) as exc:
            errors.append(exc.record() if isinstance(exc, BeamInputError) else
                          {'path':path, 'message':'설정이 누락됐습니다.'})
    from .beam_output import validate as validate_output, settings
    check('output', lambda: validate_output(settings(draft)))
    for name in ('width_mm','height_mm'):
        def positive(name=name):
            if number(draft['section'][name], 'section.'+name) <= 0:
                raise BeamInputError('section.'+name, '단면 치수는 0보다 커야 합니다. 초안 저장은 가능합니다.')
        check('section.'+name, positive)
    check('section.rotation_deg', lambda: number(draft['section']['rotation_deg'], 'section.rotation_deg'))
    def material():
        if number(draft['material']['young_MPa'], 'material.young_MPa') <= 0:
            raise BeamInputError('material.young_MPa','탄성계수는 0보다 커야 합니다.')
        if not -1 < number(draft['material']['poisson'], 'material.poisson') < .5:
            raise BeamInputError('material.poisson','포아송비는 -1보다 크고 0.5보다 작아야 합니다.')
    check('material', material)
    if type(draft.get('diagnostic_oblique')) is not bool:
        errors.append({'path':'diagnostic_oblique','message':'진단 계산 선택이 잘못됐습니다.'})
    for key in ('analysis_id','mesh_id'):
        if not isinstance(draft.get(key),str) or not draft[key]:
            errors.append({'path':key,'message':'해석과 선 메시를 선택하세요.'})
    if not isinstance(draft.get('ends'),list) or len(draft['ends']) != 2:
        errors.append({'path':'ends','message':'서로 다른 두 끝점을 선택하세요.'})
    else:
        for i, end in enumerate(draft['ends']):
            path=f'ends.{i}'
            if end.get('system') not in ('global','local'):
                errors.append({'path':path+'.system','message':'좌표계를 선택하세요.'})
            for key in ('force_N','moment_Nmm'):
                check(path+'.'+key, lambda e=end,k=key,p=path: vector(e[k],p+'.'+k))
            for key in ('translation_mm','rotation_deg'):
                check(path+'.'+key, lambda e=end,k=key,p=path: boundary_global(e[k],e.get('system','global'),
                    axes or {'local1':[1,0,0],'local2':[0,1,0],'tangent':[0,0,1]},p+'.'+k))
    return errors


def mesh_data(model):
    """Admit straight, consistently oriented, nonbranched Seg3 input without remeshing."""
    if (model.get('section_type')!='RECT' or model.get('units') !=
            {'length':'mm','force':'N','moment':'Nmm','elasticity':'MPa','rotation':'rad'}):
        raise BeamInputError('section','직사각 단면과 mm·N·Nmm·MPa·rad 단위가 필요합니다.')
    if model.get('schema') != SCHEMA or model.get('element') != 'B32R':
        raise BeamInputError('mesh_id','B32R 3절점 선 요소가 필요합니다.')
    nodes, elements = {}, {}
    for row in model['nodes']:
        n = row['id']
        if type(n) is not int or n <= 0 or n in nodes:
            raise BeamInputError('mesh_id','절점 번호가 중복되거나 잘못됐습니다.')
        nodes[n] = vector(row['xyz_mm'], 'mesh_id')
    if not nodes or len(nodes) > 500000:
        raise BeamInputError('mesh_id','선 메시가 없거나 읽기 한도를 넘었습니다.')
    axes = frame(model['axes']['tangent'], model['axes']['local1'])
    for key in axes:
        vector(model['axes'][key], 'section.'+key)
        if any(abs(a-b)>AXIS_TOL for a,b in zip(axes[key],model['axes'][key])):
            raise BeamInputError('section.local1','저장된 단면 좌표계가 일치하지 않습니다.')
    origin = vector(model['edge_start_mm'])
    end = vector(model['edge_end_mm'])
    length = math.hypot(*sub(end,origin))
    tolerance = max(1e-8, length*1e-10)  # geometric mesh/edge agreement, not numerical acceptance
    if length <= tolerance or dot(unit(sub(end,origin)),axes['tangent']) < 1-AXIS_TOL:
        raise BeamInputError('edge','모서리의 진행 방향과 요소 방향이 다릅니다.')
    stations = {}
    for n, xyz in nodes.items():
        rel = sub(xyz,origin)
        s=dot(rel,axes['tangent'])
        if math.hypot(*sub(rel,[s*v for v in axes['tangent']])) > tolerance or not -tolerance<=s<=length+tolerance:
            raise BeamInputError('mesh_id','메시가 선택한 직선 모서리와 일치하지 않습니다. 메시를 재생성하고 다시 지정하세요.')
        stations[n]=s
    degrees, used, mids, intervals = {}, set(), set(), []
    for row in model['elements']:
        e, native = row['id'], row['native_nodes']
        if type(e) is not int or e<=0 or e in elements or len(native)!=3 or len(set(native))!=3 or any(type(n) is not int or n not in nodes for n in native):
            raise BeamInputError('mesh_id','중복 요소 또는 올바르지 않은 Seg3 연결입니다.')
        a,b,m = native
        if row['ccx_nodes'] != [a,m,b]:
            raise BeamInputError('mesh_id','Seg3→B32R [0,2,1] 절점 순서가 다릅니다.')
        if stations[b]-stations[a] <= tolerance:
            raise BeamInputError('mesh_id','역방향 또는 길이 0인 요소가 있습니다. 원 메시 방향을 수정하세요.')
        if math.hypot(*sub(nodes[m],[(x+y)/2 for x,y in zip(nodes[a],nodes[b])]))>tolerance:
            raise BeamInputError('mesh_id','첫 경로는 직선의 중앙절점 Seg3만 지원합니다.')
        if m in mids:
            raise BeamInputError('mesh_id','서로 다른 요소가 중앙절점을 공유합니다.')
        mids.add(m); used.update(native)
        for n in (a,b): degrees[n]=degrees.get(n,0)+1
        intervals.append((stations[a],stations[b],a,b))
        elements[e]=[a,m,b]
    if not elements or used!=set(nodes) or mids & set(degrees) or any(v>2 for v in degrees.values()):
        raise BeamInputError('mesh_id','단일 연결 빔이어야 합니다. 분기·고립 절점·겹침을 확인하세요.')
    ordered=sorted(intervals)
    if abs(ordered[0][0])>tolerance or abs(ordered[-1][1]-length)>tolerance:
        raise BeamInputError('mesh_id','메시가 모서리 전체 길이를 덮지 않습니다.')
    for left,right in zip(ordered,ordered[1:]):
        if left[3]!=right[2] or abs(left[1]-right[0])>tolerance:
            raise BeamInputError('mesh_id','메시가 끊어졌거나 중복됐습니다.')
    return nodes,elements,stations,[ordered[0][2],ordered[-1][3]]


def effective_conditions(draft, axes, endpoint_ids):
    loads, constraints, end_rows = [], [], []
    seen = set()
    for i,(end,node) in enumerate(zip(draft['ends'],endpoint_ids)):
        if node in seen:
            raise BeamInputError(f'ends.{i}.reference','끝점이 중복됐습니다. 다른 끝점을 선택하세요.')
        seen.add(node)
        force=to_global(vector(end['force_N']),end['system'],axes)
        moment=to_global(vector(end['moment_Nmm']),end['system'],axes)
        translation=boundary_global(end['translation_mm'],end['system'],axes,f'ends.{i}.translation_mm')
        rotation=boundary_global(end['rotation_deg'],end['system'],axes,f'ends.{i}.rotation_deg')
        rotation=[math.radians(v) if v is not None else None for v in rotation]
        for v in force+moment+[v for v in translation+rotation if v is not None]:number(v,f'ends.{i}')
        for dof,value in enumerate(force+moment,1):
            if value != 0: loads.append({'node':node,'dof':dof,'value':value,'unit':'N' if dof<=3 else 'Nmm'})
        for dof,value in enumerate(translation+rotation,1):
            if value is not None: constraints.append({'node':node,'dof':dof,'value':value,'unit':'mm' if dof<=3 else 'rad'})
        end_rows.append({'node':node,'global_force_N':force,'global_moment_Nmm':moment,
                         'global_translation_mm':translation,'global_rotation_rad':rotation})
    return loads,constraints,end_rows


def validate_model(model):
    nodes,elements,stations,ends=mesh_data(model)
    draft=model['draft']; errors=validate_draft(draft,model['axes'])
    if errors:
        raise BeamInputError(errors[0]['path'],errors[0]['message'])
    length_value=number(model['length_mm'],'edge')
    if length_value<=0:raise BeamInputError('edge','길이는 0보다 커야 합니다.')
    ids=model['end_node_ids']
    if any(type(n) is not int for n in ids) or len(ids)!=2 or set(ids)!=set(ends):
        raise BeamInputError('ends','양쪽 모서리 끝 절점을 정확히 지정하세요.')
    effective=effective_conditions(draft,model['axes'],ids)
    if (model['loads'],model['boundaries'],model['end_conditions'])!=effective:
        raise BeamInputError('ends','저장 조건과 실제 입력 성분이 다릅니다.')
    expected=native_axis_formula(model['axes']['tangent'],draft['section']['rotation_deg'])
    if any(abs(a-b)>AXIS_TOL for a,b in zip(model['axes']['local1'],expected)):
        raise BeamInputError('section.rotation_deg','회전값과 저장된 native 1축이 다릅니다.')
    from .beam_output import element_axes
    expected_axes = element_axes(draft, model['axes']['tangent'], elements)
    if expected_axes is not None:
        saved_axes = {int(e): a for e,a in model.get('element_axes', {}).items()}
        if expected_axes != saved_axes:
            raise BeamInputError('axis_regions', '영역별 입력 회전과 보존 축이 다릅니다.')
    elif 'element_axes' in model:
        raise BeamInputError('axis_regions', '요소별 축에 대응하는 원 영역 설정이 없습니다.')
    # Rank of constrained rigid motions; no material/beam stiffness approximation.
    import numpy as np
    rows=[]
    for row in model['boundaries']:
        n,dof=row['node'],row['dof']; r=sub(nodes[n],nodes[ends[0]])
        basis=[0.]*6
        if dof<=3:
            j=dof-1; basis[j]=1
            # Use one common length scale, not node-dependent scaling.
            scale=max(1.,model['length_mm'])
            for k in range(3):
                e=[0.,0.,0.];e[k]=1;basis[3+k]=cross(e,r)[j]/scale
        else:
            basis[dof-1]=1
        rows.append(basis)
    if not rows or np.linalg.matrix_rank(np.asarray(rows),tol=1e-10)<6:
        raise BeamInputError('ends','강체 이동 또는 회전이 남습니다. 끝점의 병진·회전 구속을 확인하세요.')
    if abs(model['length_mm']-math.hypot(*sub(model['edge_end_mm'],model['edge_start_mm'])))>1e-8:
        raise BeamInputError('edge','저장 길이가 다릅니다.')
    oblique=sum(abs(v)>AXIS_TOL for v in model['axes']['tangent'])!=1
    if oblique and not draft['diagnostic_oblique']:
        raise BeamInputError('diagnostic_oblique','비축정렬 빔은 CalculiX 2.22 회전·모멘트 결함 보고가 있습니다. 방향을 수정하거나 명시적으로 진단 계산을 선택하세요.')
    return nodes,elements,stations


def section_properties(draft):
    w=number(draft['section']['width_mm']);h=number(draft['section']['height_mm'])
    return {'area_mm2':w*h,'I1_mm4':w*h**3/12,'I2_mm4':h*w**3/12}
