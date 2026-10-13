"""Pure user-law declaration. Native source admission is operator-owned, never a model permission."""
from copy import deepcopy
import hashlib
import math
import os
import re

BACKEND='material.mfront.user'
COMPONENTS=('xx','yy','zz','xy','xz','yz')
EXAMPLE_SOURCE="""@Behaviour ResearchElastic;
@ModellingHypotheses {"Tridimensional"};
@ProvidesSymmetricTangentOperator;
@MaterialProperty stress young;
young.setGlossaryName("YoungModulus");
@MaterialProperty real nu;
nu.setGlossaryName("PoissonRatio");
@Integrator{
  const auto lambda = young*nu/((1+nu)*(1-2*nu));
  const auto mu = young/(2*(1+nu));
  sig = lambda*trace(eto+deto)*StrainStensor::Id()+2*mu*(eto+deto);
  if(computeTangentOperator_){
    Dt = lambda*Stensor4::IxI()+2*mu*Stensor4::Id();
  }
}
"""


def source_hash(source):return hashlib.sha256(source.encode('utf-8')).hexdigest()


def default_settings():
    return {'source':EXAMPLE_SOURCE,'behaviour':'ResearchElastic','action':'build',
        'interface':'generic','hypothesis':'Tridimensional','stress_unit':'Pa','strain_unit':'1','time_unit':'s',
        'properties':[{'name':'YoungModulus','value':1e9,'unit':'Pa'},{'name':'PoissonRatio','value':.25,'unit':'1'}],
        'external':[{'name':'Temperature','value':293.15,'unit':'K'}],
        'initial_internal':[],
        'history':[{'time':0.,'strain':[0.]*6},{'time':1.,'strain':[.001,0.,0.,0.,0.,0.]}],
        'probe':{'increment':1,'component':'xx','steps':[1e-6,1e-7]}}


def _number(value):
    if type(value) not in (float,int) or not math.isfinite(value):raise ValueError('유한한 수를 입력하세요.')
    return value


def validate_settings(settings):
    base=default_settings()
    if not isinstance(settings,dict) or set(settings)!=set(base):raise ValueError('사용자 법칙의 선언된 입력만 허용됩니다.')
    s=deepcopy(settings)
    if not isinstance(s['source'],str) or not 1<=len(s['source'].encode('utf-8'))<=48*1024 or '\x00' in s['source']:
        raise ValueError('UTF-8 법칙 원문은 1~48 KiB입니다.')
    if not isinstance(s['behaviour'],str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,63}',s['behaviour']):
        raise ValueError('MFront behaviour 이름을 입력하세요.')
    for key,value in {'interface':'generic','hypothesis':'Tridimensional','stress_unit':'Pa','strain_unit':'1','time_unit':'s'}.items():
        if s[key]!=value:raise ValueError('현재 지원 선언: generic / 3차원 미소변형 / Pa, 1, s')
    if s['action'] not in ('build','evaluate'):raise ValueError('빌드만 또는 빌드하고 평가를 선택하세요.')
    if s['action']=='build':
        # Build discovers the source's actual descriptor. Numerical mapping and
        # state values are not inputs to compilation and may still be a draft.
        for key,limit in (('properties',32),('external',32),('history',32),('initial_internal',128)):
            if not isinstance(s[key],list) or len(s[key])>limit:raise ValueError('입력 목록의 지원 크기를 확인하세요.')
        if not isinstance(s['probe'],dict):raise ValueError('섭동 초안 형식을 확인하세요.')
        return s
    for key in ('properties','external'):
        if not isinstance(s[key],list) or len(s[key])>32:raise ValueError('물성/외부 상태는 최대 32개입니다.')
        names=set()
        for index,row in enumerate(s[key]):
            if (not isinstance(row,dict) or set(row)!={'name','value','unit'} or
                not isinstance(row['name'],str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,63}',row['name']) or row['name'] in names):
                raise ValueError('고유한 native 변수 이름, 값, 단위를 입력하세요.')
            names.add(row['name']);_number(row['value'])
            if abs(row['value'])>1e100:raise ValueError('계수 지원 범위는 ±1e100입니다.')
            from .dimensioned_expression import unit_dimension
            unit_dimension(row['unit'],path=f'settings.{key}.{index}.unit')
    history=s['history']
    if not isinstance(history,list) or not 2<=len(history)<=32:raise ValueError('초기행을 포함해 2~32개 이력을 입력하세요.')
    previous=None
    for row in history:
        if not isinstance(row,dict) or set(row)!={'time','strain'}:raise ValueError('이력은 시간과 물리 텐서 변형률 6성분입니다.')
        time=_number(row['time'])
        if previous is not None and time<=previous:raise ValueError('시간은 증가해야 합니다.')
        previous=time
        if not isinstance(row['strain'],list) or len(row['strain'])!=6 or any(abs(_number(v))>.05 for v in row['strain']):
            raise ValueError('미소변형 이력은 xx yy zz xy xz yz이며 절댓값 0.05 이내입니다.')
    if history[0]['time']!=0 or history[0]['strain']!=[0.]*6:raise ValueError('초기 시간·변형률·응력은 0으로 선언됩니다.')
    if not isinstance(s['initial_internal'],list) or len(s['initial_internal'])>128:raise ValueError('초기 내부 상태 크기를 확인하세요.')
    for value in s['initial_internal']:_number(value)
    probe=s['probe']
    if (not isinstance(probe,dict) or set(probe)!={'increment','component','steps'} or type(probe['increment']) is not int
            or not 1<=probe['increment']<len(history) or probe['component'] not in COMPONENTS):
        raise ValueError('섭동할 실제 증분과 Kelvin 성분을 선택하세요.')
    if not isinstance(probe['steps'],list) or not 1<=len(probe['steps'])<=3 or any(not 0<_number(h)<=.001 for h in probe['steps']):
        raise ValueError('섭동 크기는 0~0.001 사이의 양수 1~3개입니다.')
    return s


def require_admission(settings):
    s=validate_settings(settings);digest=source_hash(s['source'])
    allowed={x.strip() for x in os.environ.get('CAELAB_MFRONT_ALLOWED_SOURCE_SHA256','').split(',') if re.fullmatch(r'[0-9a-f]{64}',x.strip())}
    from .material_build_permission import is_admitted
    if digest not in allowed and not is_admitted(s['source'],s['behaviour']):
        raise PermissionError('이 원문 버전의 빌드 허용이 필요합니다. 재료 창에서 원문을 검토하고 이 버전 빌드를 선택하세요.')
    return digest


def model_declaration(settings):
    s=validate_settings(settings)
    return {'kind':'user_mfront_small_strain','model':s,'source_sha256':source_hash(s['source']),
            'pair':'dσKelvin/dεKelvin','initial_state':'zero strain/stress; explicit internal state',
            'field_units':'Pa / 1 / s','interface':'generic MGIS material point; no FE export',
            'qualification':'UNKNOWN'}



def inputs_from_build(settings,build):
    """Prepare a local editable mapping from the exact compiled descriptor.

    Unreported units/values remain blank. No owner write, compile or integration.
    """
    s=deepcopy(settings)
    if (not isinstance(build,dict) or build.get('source_sha256')!=source_hash(s['source'])
            or build.get('descriptor',{}).get('behaviour')!=s['behaviour']):
        raise ValueError('선택한 빌드와 현재 법칙 원문이 다릅니다. 현재 버전을 먼저 빌드하세요.')
    descriptor=build['descriptor']
    for key,native in (('properties','material_properties'),('external','external_state_variables')):
        rows=descriptor.get(native)
        if not isinstance(rows,list) or len(rows)>32 or any(r.get('size')!=1 for r in rows):
            raise ValueError('선택한 선언의 물성/외부 상태 형식은 이 편집기가 지원하지 않습니다.')
        old={r['name']:r for r in s[key] if isinstance(r,dict) and isinstance(r.get('name'),str)}
        s[key]=[deepcopy(old[r['name']]) if r['name'] in old else
                {'name':r['name'],'value':'','unit':''} for r in rows]
    variables=descriptor.get('internal_state_variables',[])
    if any(type(r.get('size')) is not int or r['size']<1 for r in variables):
        raise ValueError('내부 상태 선언의 크기를 읽을 수 없습니다.')
    count=sum(r['size'] for r in variables)
    if count>128:raise ValueError('초기 내부 상태는 128성분까지 지원합니다.')
    if len(s['initial_internal'])!=count:s['initial_internal']=['']*count
    s['action']='evaluate'
    return s
