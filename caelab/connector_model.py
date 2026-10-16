"""Finite TYPE13 connector input; native beam modes, not six uncoupled nodal DOFs.

Drafts retain incomplete text. ``model`` is the execution gate and never fills
physical mass, inertia, axes or CAD selections with numerical defaults.
"""
from copy import deepcopy
import math

BACKEND = 'explicit.opencourant.connector'
NAMESPACE = 'connector_programs'
MODES = ('LX', 'LY', 'LZ', 'RX', 'RY', 'RZ')
OPERATIONS = tuple('pre.connector.'+s for s in ('inspect','create','draft','apply','capture','freeze'))
READ_ONLY = ('pre.connector.inspect','pre.connector.capture')


class ConnectorInputError(ValueError):
    def __init__(self, path, message):
        self.path, self.message = path, message
        super().__init__(message)
    def record(self): return {'path':self.path,'message':self.message}


def default_draft(label='연결요소'):
    def end():
        return {'selection':None,'rigid_attachment':False,'reference_is_mass_center':False,
                'mass':{'value':'','unit':'kg'},
                'inertia':{'values':['']*6,'unit':'kg*mm^2','frame':'global_cartesian'},
                'fixed':[False]*6,'velocity_mm_s':['0']*3,'omega_rad_s':['0']*3}
    return {'version':1,'label':label,'endpoints':[end(),end()],
            'axes':{k:['']*3 for k in 'xyz'},'k':['']*6,'c':['']*6,
            'units':{'translation_k':'N/mm','translation_c':'N*s/mm',
                     'rotation_k':'N*mm/rad','rotation_c':'N*mm*s/rad'},
            'connector_mass':{'value':'','unit':'kg'},
            'connector_inertia':{'value':'','unit':'kg*mm^2'},
            'time':{'end_s':'','history_interval_s':'','scale':'0.9'},'source':'','fe':None}


def number(value, path):
    if isinstance(value,bool): raise ConnectorInputError(path,'참 또는 거짓 대신 수치를 입력하세요.')
    try: value=float(value)
    except (TypeError,ValueError,OverflowError) as exc:
        raise ConnectorInputError(path,'유한한 수치를 입력하세요.') from exc
    if not math.isfinite(value): raise ConnectorInputError(path,'유한한 수치를 입력하세요.')
    return value


def _keys(value, keys, path):
    if not isinstance(value,dict) or set(value)!=set(keys):
        raise ConnectorInputError(path,'지원되는 연결요소 입력 항목과 다릅니다.')


def _vec(values,n,path):
    if not isinstance(values,list) or len(values)!=n:
        raise ConnectorInputError(path,f'{n}개 값을 입력하세요.')
    return [number(x,f'{path}.{i}') for i,x in enumerate(values)]


def dot(a,b): return sum(x*y for x,y in zip(a,b))
def sub(a,b): return [x-y for x,y in zip(a,b)]
def cross(a,b): return [a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]]


def check_shape(draft):
    _keys(draft,default_draft(),'draft')
    if draft['version']!=1 or isinstance(draft['version'],bool):
        raise ConnectorInputError('version','지원되는 연결요소 초안 버전이 아닙니다.')
    if not isinstance(draft['label'],str) or not isinstance(draft['source'],str):
        raise ConnectorInputError('label','연결요소 이름과 출처는 문자열이어야 합니다.')
    if not isinstance(draft['endpoints'],list) or len(draft['endpoints'])!=2:
        raise ConnectorInputError('endpoints','실제 대상 A와 B를 각각 선택하세요.')
    for i,end in enumerate(draft['endpoints']):
        _keys(end,default_draft()['endpoints'][i],f'endpoints.{i}')
    return deepcopy(draft)


def _quantity(record, factors,path):
    _keys(record,('value','unit'),path)
    if record['unit'] not in factors: raise ConnectorInputError(path,'이 물리량의 지원 단위를 선택하세요.')
    return number(record['value'],path+'.value')*factors[record['unit']]


def _inertia(record,path):
    _keys(record,('values','unit','frame'),path)
    if record['frame']!='global_cartesian':
        raise ConnectorInputError(path,'질량중심 기준의 전역 직교 관성텐서를 지정하세요.')
    factor={'kg*mm^2':.001,'kg*m^2':1000.,'Mg*mm^2':1.}.get(record['unit'])
    if factor is None: raise ConnectorInputError(path,'관성 단위를 확인하세요.')
    xx,yy,zz,xy,yz,zx=[x*factor for x in _vec(record['values'],6,path)]
    # SPD inertia and SPD second-moment matrix enforce physical principal
    # triangle inequalities without introducing an eigensolver dependency.
    def spd(a,b,c,d,e,f):
        return a>0 and a*b-d*d>0 and a*b*c+2*d*e*f-a*e*e-b*f*f-c*d*d>0
    def psd(a,b,c,d,e,f):
        return min(a,b,c,a*b-d*d,b*c-e*e,a*c-f*f,a*b*c+2*d*e*f-a*e*e-b*f*f-c*d*d)>=0
    if not spd(xx,yy,zz,xy,yz,zx) or not psd((yy+zz-xx)/2,(xx+zz-yy)/2,(xx+yy-zz)/2,-xy,-yz,-zx):
        raise ConnectorInputError(path,'실제 질량중심 관성은 양의 주관성과 강체 관성의 삼각조건을 만족해야 합니다.')
    return [xx,yy,zz,xy,yz,zx]


def validate_selection(selection,path):
    _keys(selection,('label','reference_mm','points_mm','kind','native_refs','identity'),path)
    xyz=_vec(selection['reference_mm'],3,path+'.reference_mm')
    points=selection['points_mm']
    if not isinstance(points,list) or not points:
        raise ConnectorInputError(path,'실제 CAD 또는 메시의 점·영역을 선택하세요.')
    points=[_vec(p,3,path+'.points_mm') for p in points]
    if selection['kind'] not in ('vertex','region') or not selection['native_refs'] or not isinstance(selection['identity'],dict) or not selection['identity']:
        raise ConnectorInputError(path,'원 CAD 선택 근거가 없습니다. 원 모델에서 다시 선택하세요.')
    if len({tuple(p) for p in points})!=len(points):
        raise ConnectorInputError(path,'선택한 영역에 중복 점이 있습니다.')
    return xyz,points


def model(draft):
    check_shape(draft)
    if not draft['label'].strip(): raise ConnectorInputError('label','연결요소 이름을 입력하세요.')
    endpoints=[];fe=draft['fe']
    if fe is not None:
        from .connector_fe import validate_fe
        fe_model=validate_fe(fe,draft)
    for i,e in enumerate(draft['endpoints']):
        p=f'endpoints.{i}'
        xyz,points=validate_selection(e['selection'],p+'.selection')
        if e['rigid_attachment'] is not True or (fe is None and e['reference_is_mass_center'] is not True):
            raise ConnectorInputError(p,'선택 영역의 강체 표현과 기준점이 실제 질량중심임을 확인하세요. 변형체를 자동 강체화하지 않습니다.')
        mass=_quantity(e['mass'],{'kg':.001,'Mg':1.},p+'.mass') if fe is None else 0.
        if fe is None and mass<=0: raise ConnectorInputError(p+'.mass','실제 양의 질량을 입력하세요. 숨은 질량은 추가하지 않습니다.')
        inertia=_inertia(e['inertia'],p+'.inertia') if fe is None else [0.]*6
        fixed=e['fixed']
        if not isinstance(fixed,list) or len(fixed)!=6 or any(type(v) is not bool for v in fixed):
            raise ConnectorInputError(p+'.fixed','병진·회전 여섯 구속을 명시하세요.')
        velocity=_vec(e['velocity_mm_s'],3,p+'.velocity_mm_s')
        omega=_vec(e['omega_rad_s'],3,p+'.omega_rad_s')
        if fe is not None and (any(fixed) or (fe.get('initial_motion_source','existing_fe')=='existing_fe' and any(velocity+omega))):
            raise ConnectorInputError(p,'FE 부착의 원 구속을 유지하세요. 초기 속도·각속도를 추가하려면 선택 영역 초기운동 지정을 명시 선택하세요.')
        if any(f and v!=0 for f,v in zip(fixed,velocity+omega)):
            raise ConnectorInputError(p,'구속한 방향에 초기 속도가 있습니다. 구속 또는 초기운동을 수정하세요.')
        endpoints.append({'reference_mm':xyz,'points_mm':points,'mass_Mg':mass,'inertia_Mg_mm2':inertia,
                          'fixed':fixed,'velocity_mm_s':velocity,'omega_rad_s':omega,'selection':deepcopy(e['selection'])})
    if fe is not None:
        from .connector_fe import initial_fields
        initial_fields(fe,endpoints,fe_model)
    if any(a==b for a in endpoints[0]['selection']['native_refs'] for b in endpoints[1]['selection']['native_refs']):
        raise ConnectorInputError('endpoints','두 강체 부착 영역이 겹칩니다. 서로 다른 실제 대상을 선택하세요.')
    delta=sub(endpoints[1]['reference_mm'],endpoints[0]['reference_mm']); length=math.sqrt(dot(delta,delta))
    if length<=0: raise ConnectorInputError('endpoints','길이가 0인 연결은 지원하지 않습니다. 서로 다른 기준점을 선택하세요.')
    _keys(draft['axes'],'xyz','axes'); axes={k:_vec(draft['axes'][k],3,'axes.'+k) for k in 'xyz'}
    if any(abs(dot(v,v)-1)>1e-10 for v in axes.values()) or any(abs(dot(axes[a],axes[b]))>1e-10 for a,b in [('x','y'),('y','z'),('z','x')]) or any(abs(a-b)>1e-10 for a,b in zip(cross(axes['x'],axes['y']),axes['z'])):
        raise ConnectorInputError('axes','단위 길이의 직교 오른손 국부축을 명시하세요.')
    if any(abs(a-b/length)>1e-10 for a,b in zip(axes['x'],delta)):
        raise ConnectorInputError('axes.x','국부 x축은 기준점 A에서 B를 향해야 합니다.')
    _keys(draft['units'],default_draft()['units'],'units')
    units=draft['units']; k=_vec(draft['k'],6,'k'); c=_vec(draft['c'],6,'c')
    conversions={'translation_k':{'N/mm':1.,'N/m':.001},'translation_c':{'N*s/mm':1.,'N*s/m':.001},
        'rotation_k':{'N*mm/rad':1.,'N*m/rad':1000.,'N*mm/deg':180/math.pi},
        'rotation_c':{'N*mm*s/rad':1.,'N*m*s/rad':1000.,'N*mm*s/deg':180/math.pi}}
    for name,factors in conversions.items():
        if units[name] not in factors: raise ConnectorInputError('units.'+name,'지원되는 계수 단위를 선택하세요.')
    k=[v*conversions['translation_k' if i<3 else 'rotation_k'][units['translation_k' if i<3 else 'rotation_k']] for i,v in enumerate(k)]
    c=[v*conversions['translation_c' if i<3 else 'rotation_c'][units['translation_c' if i<3 else 'rotation_c']] for i,v in enumerate(c)]
    if any(v<0 for v in k+c): raise ConnectorInputError('k','수동 선형 연결의 강성·감쇠는 음수가 될 수 없습니다.')
    mass=_quantity(draft['connector_mass'],{'kg':.001,'Mg':1.},'connector_mass')
    inertia=_quantity(draft['connector_inertia'],{'kg*mm^2':.001,'kg*m^2':1000.,'Mg*mm^2':1.},'connector_inertia')
    if mass<0: raise ConnectorInputError('connector_mass','연결요소의 실제 질량은 음수가 될 수 없습니다.')
    if inertia<=1e-20:
        raise ConnectorInputError('connector_inertia','TYPE13은 이 관성을 1e-20으로 변경합니다. 실제 관성을 명시하세요. 원 입력은 보존하며 작은 관성을 몰래 추가하지 않습니다.')
    _keys(draft['time'],('end_s','history_interval_s','scale'),'time')
    t={key:number(v,'time.'+key) for key,v in draft['time'].items()}
    if not 0<t['history_interval_s']<=t['end_s'] or not 0<t['scale']<=1:
        raise ConnectorInputError('time','종료·출력 간격은 양수이고 출력 간격은 종료 시각 이하, 시간증분 계수는 0 초과 1 이하이어야 합니다.')
    return {'version':1,'backend':BACKEND,'formulation':'SPR_BEAM_TYPE13','attachment':'rigid_selected_regions',
        'units':{'mass':'Mg','length':'mm','time':'s','force':'N','moment':'N*mm','rotation':'rad'},
        'endpoints':endpoints,'axes':axes,'length_mm':length,'k':k,'c':c,'time':t,
        'connector_mass_Mg':mass,'connector_inertia_Mg_mm2':inertia,'draft':deepcopy(draft),
        'fe':deepcopy(fe),'qualification':'UNKNOWN'}


def default_settings(): return {'connector':default_draft()}


def model_from_settings(settings):
    _keys(settings,('connector',),'settings')
    return model(settings['connector'])


def validate_settings(settings):
    model_from_settings(settings)
    return deepcopy(settings)
