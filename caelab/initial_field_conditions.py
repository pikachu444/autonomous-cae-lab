"""Explicit, finite elastic initial-field profiles over an existing C3D10 mesh.

No material history is reconstructed from stress. Coordinates remain reference
mm; tensors use true tensor shear, not engineering shear. Runtime is separate.
"""
from copy import deepcopy
import math
import numpy as np
from caelab.calculix_material import STRESS_FACTORS

COMPONENTS=('XX','YY','ZZ','XY','XZ','YZ')
BACKENDS={'calculix':'structure.calculix.initial_fields','codeaster':'structure.codeaster.initial_fields'}
OPERATIONS=('pre.initial.read','pre.initial.region','pre.initial.save_draft','pre.initial.apply','pre.initial.discard')
READ_ONLY=('pre.initial.read','pre.initial.region')


def number(value,label):
    if type(value) not in (int,float) or not math.isfinite(value):raise ValueError(label+'을 유한한 숫자로 입력하세요.')
    return float(value)


def matrix(value,label):
    if not isinstance(value,list) or len(value)!=3 or any(not isinstance(r,list) or len(r)!=3 for r in value):
        raise ValueError(label+'은 3×3 성분이 필요합니다.')
    return np.array([[number(v,label) for v in r] for r in value])


def rotation(value):
    R=matrix(value,'텐서 기저')
    if not np.allclose(R.T@R,np.eye(3),rtol=0,atol=1e-12) or not math.isclose(float(np.linalg.det(R)),1.,rel_tol=0,abs_tol=1e-12):
        raise ValueError('텐서 기저는 오른손 직교 단위축이어야 합니다.')
    return R


def tensor(values,label):
    if not isinstance(values,list) or len(values)!=6:raise ValueError(label+'의 XX, YY, ZZ, XY, XZ, YZ 여섯 성분이 필요합니다.')
    x,y,z,xy,xz,yz=[number(v,label) for v in values]
    return np.array([[x,xy,xz],[xy,y,yz],[xz,yz,z]])


def six(t):return [float(t[0,0]),float(t[1,1]),float(t[2,2]),float(t[0,1]),float(t[0,2]),float(t[1,2])]


def stress_factor(unit):
    if unit not in STRESS_FACTORS:raise ValueError('응력 단위 Pa, kPa, MPa 또는 GPa를 선택하세요.')
    return STRESS_FACTORS[unit]


def static_program(model):
    """Return the user's existing STATIC program without reconciling conditions."""
    from .contact_steps import default_program,compile_program
    value=deepcopy(model.get('analysis_steps') or default_program(model['step'],model['conditions']))
    rows=compile_program(value,model['conditions'])
    if value['procedure']!='static' or any(r['procedure']!='static' for r in rows):
        raise ValueError('온도·초기 상태의 현재 지원은 정적 단계입니다. 동적 단계는 지원하지 않습니다.')
    return value,rows


def default_draft(model=None):
    # UNKNOWN physical values are never silently made zero.
    result={'solver':'calculix','kind':'temperature','label':'온도 조건','mesh_id':None,
        'node_ids':[],'element_ids':[],'frame':[[1,0,0],[0,1,0],[0,0,1]],
        'temperature':{'mode':'absolute','unit':'K','reference_value':None,'reference_unit':'K',
            'expansion_per_K':None,'samples':[[0,None],[1,None],[2,None]]},
        'stress':{'unit':'MPa','values':[None]*6,'ip_rows':None},
        'compatible':{'origin_mm':[None]*3,'translation_mm':[None]*3,'gradient':[[None]*3 for _ in range(3)],
            'total_strain':[None]*6,'stress_values':[None]*6,'stress_unit':'MPa'},
        'states':[{'parameter':1.,'label':'첫 평형','load_factor':None},{'parameter':2.,'label':'후속 하중','load_factor':None}]}
    if model is not None:
        _,rows=static_program(model)
        result['states']=[{'parameter':r['end'],'label':r['label'],'load_factor':None} for r in rows]
        result['temperature']['samples']=[[0.,None]]+[[r['end'],None] for r in rows]
    return result


def normalize(model,draft):
    if not isinstance(draft,dict) or set(draft)!=set(default_draft()):raise ValueError('현재 영역의 온도 또는 초기 상태 정의를 확인하세요.')
    if draft['solver'] not in BACKENDS or draft['kind'] not in ('temperature','stress','compatible'):
        raise ValueError('지원되는 온도·초기 응력·호환 초기 상태를 선택하세요.')
    if (draft['kind']=='compatible')!=(draft['solver']=='codeaster'):
        raise ValueError('호환 초기 변위·변형률 상태는 Code_Aster, 온도와 초기 응력은 CalculiX를 사용합니다.')
    if (model.get('contacts') or model.get('pretension_sections') or model.get('periodic_constraints') or model.get('dynamic') or
        model.get('restart') or model['step']['geometry']!='linear' or len(model['materials'])!=1 or
        any(r.get('law')!='isotropic_linear_elastic' or r.get('plasticity') for r in model['materials'])):
        raise ValueError('첫 초기장 지원은 접촉·소성·재시작이 없는 한 고체의 소변형 등방 탄성 정적 해석입니다.')
    nodes={r['node_id']:r for r in model['nodes']};elements={r['element_id']:r for r in model['elements']}
    if not elements or any(r['type']!='C3D10' for r in elements.values()) or len({r['body_id'] for r in elements.values()})!=1:
        raise ValueError('같은 C3D10 고체와 원 절점·적분점 순서를 선택하세요.')
    def identifiers(values,catalog,label):
        if not isinstance(values,list) or not values or any(type(v)is not int for v in values) or len(values)!=len(set(values)) or not set(values)<=set(catalog):
            raise ValueError(label+' 선택이 비었거나 원 메시와 다릅니다.')
        return sorted(values)
    selected_nodes=identifiers(draft['node_ids'],nodes,'절점');selected_elements=identifiers(draft['element_ids'],elements,'요소')
    if draft['kind']!='temperature' and (set(selected_nodes)!=set(nodes) or set(selected_elements)!=set(elements)):
        raise ValueError('초기 응력·호환 상태의 첫 지원은 선택한 단일 고체 전체입니다. 부분 영역의 불연속 상태는 지원하지 않습니다.')
    states=draft['states']
    _,steps=static_program(model)
    if not isinstance(states,list) or len(states)!=len(steps):
        raise ValueError('현재 정적 단계마다 실제 누적 끝값에 초기장 상태를 지정하세요.')
    phases=[];previous=0.
    for s,step in zip(states,steps):
        if not isinstance(s,dict) or set(s)!={'parameter','label','load_factor'}:raise ValueError('상태의 하중 매개변수와 하중 배율을 확인하세요.')
        t=number(s['parameter'],'하중 매개변수')
        if t<=previous:raise ValueError('상태의 하중 매개변수는 0 이후 엄격히 증가해야 합니다.')
        if t!=step['end']:raise ValueError('초기장 상태는 현재 정적 단계의 실제 누적 끝값과 같아야 합니다.')
        if not isinstance(s['label'],str) or not s['label'].strip():raise ValueError('상태 이름을 입력하세요.')
        factor=None if s['load_factor'] is None else number(s['load_factor'],'외력 배율')
        if draft['solver']=='codeaster' and factor is None:raise ValueError('호환 초기 상태의 기존 외력 배율을 명시하세요.')
        phases.append({'parameter':t,'label':s['label'],'load_factor':factor});previous=t
    R=rotation(draft['frame']);out={'kind':draft['kind'],'solver':draft['solver'],'label':draft['label'],
        'node_ids':selected_nodes,'element_ids':selected_elements,'frame':R.tolist(),'states':phases,
        'tensor_components':list(COMPONENTS),'tensor_shear':'tensor_not_engineering','coordinate_frame':'FREECAD_DOCUMENT_GLOBAL',
        'units':{'coordinates':'mm','displacement':'mm','stress':'MPa','strain':'1','temperature':'K'},
        'reference_state':'undeformed_native_mesh','initial_stress_measure':'second_Piola_Kirchhoff_at_reference; Cauchy_equivalent_only_for_admitted_linear_small_strain','engineering_release':'UNKNOWN'}
    if draft['kind']=='temperature':
        t=draft['temperature']
        if set(t)!={'mode','unit','reference_value','reference_unit','expansion_per_K','samples'}:raise ValueError('온도 정의 항목을 확인하세요.')
        if t['mode'] not in ('absolute','difference'):raise ValueError('절대 온도와 온도 증분을 명시 구분하세요.')
        if t['unit'] not in ('K','degC','°C') or t['reference_unit'] not in ('K','degC','°C'):raise ValueError('온도 단위 K 또는 °C를 선택하세요.')
        ref=number(t['reference_value'],'응력 없는 기준 온도')+(273.15 if t['reference_unit']!='K' else 0)
        if ref<0:raise ValueError('기준 온도는 절대 영도 아래일 수 없습니다.')
        samples=t['samples'];wanted=[0.]+[p['parameter'] for p in phases]
        if not isinstance(samples,list) or len(samples)!=len(wanted):raise ValueError('초기 온도와 각 정적 단계 끝의 온도를 입력하세요.')
        absolute=[]
        for pair,time in zip(samples,wanted):
            if not isinstance(pair,list) or len(pair)!=2 or number(pair[0],'온도 시각')!=time:raise ValueError('온도 시각을 실제 하중 상태와 정확히 맞추세요.')
            val=number(pair[1],'온도')+(ref if t['mode']=='difference' else (273.15 if t['unit']!='K' else 0.))
            if val<0:raise ValueError('온도는 절대 영도 아래일 수 없습니다.')
            absolute.append([time,val])
        if not math.isclose(absolute[0][1],ref,rel_tol=0,abs_tol=1e-10):raise ValueError('초기 온도는 명시 기준 온도와 같아야 합니다. 초기 열응력 복원은 지원하지 않습니다.')
        out['temperature']={'reference_K':ref,'expansion_per_K':number(t['expansion_per_K'],'선팽창 계수 [1/K]'),
            'samples_K':absolute,'unselected_nodes':'explicit_reference_temperature','source':deepcopy(t)}
    elif draft['kind']=='stress':
        s=draft['stress'];factor=stress_factor(s['unit'])
        if s['ip_rows'] is None:
            values=six(R@tensor(s['values'],'초기 응력')@R.T)
            rows=[{'element_id':e,'point':i,'values_MPa':[v*factor for v in values]} for e in selected_elements for i in range(1,5)]
        else:
            rows=[];seen=set()
            for row in s['ip_rows']:
                if not isinstance(row,dict) or set(row)!={'element_id','point','values'}:raise ValueError('원 적분점 응력의 항목을 확인하세요.')
                key=row['element_id'],row['point']
                if key in seen or type(key[0])is not int or type(key[1])is not int:raise ValueError('적분점 응력이 중복되거나 잘못됐습니다.')
                seen.add(key);values=six(R@tensor(row['values'],'원 적분점 응력')@R.T)
                rows.append({'element_id':key[0],'point':key[1],'values_MPa':[v*factor for v in values]})
            if seen!={(e,i) for e in selected_elements for i in range(1,5)}:raise ValueError('같은 원 요소의 native 네 적분점 여섯 성분이 빠짐없이 필요합니다.')
        out['stress_rows']=rows;out['first_equilibrium']='native re-equilibration; initial stress is not assumed equilibrated'
    else:
        c=draft['compatible'];G=R@matrix(c['gradient'],'초기 변위 구배')@R.T
        epsilon=R@tensor(c['total_strain'],'초기 총변형률')@R.T
        if not np.allclose(epsilon,(G+G.T)/2,rtol=1e-10,atol=1e-12):raise ValueError('초기 총변형률은 변위 구배의 대칭 성분과 같아야 합니다.')
        material=model['materials'][0];E=number(material['young_modulus_MPa'],'탄성계수');nu=number(material['poisson_ratio'],'푸아송비')
        lame=E*nu/((1+nu)*(1-2*nu));mu=E/(2*(1+nu))
        expected=lame*np.trace(epsilon)*np.eye(3)+2*mu*epsilon
        stress=R@tensor(c['stress_values'],'초기 응력')@R.T*stress_factor(c['stress_unit'])
        if not np.allclose(stress,expected,rtol=1e-9,atol=1e-9):raise ValueError('초기 응력은 같은 등방 탄성 재료의 초기 총변형률과 일치해야 합니다. 고유·소성 변형률로 대체할 수 없습니다.')
        origin=np.array([number(v,'기준점 [mm]') for v in c['origin_mm']]);translation=np.array([number(v,'강체 이동 [mm]') for v in c['translation_mm']])
        if origin.shape!=(3,) or translation.shape!=(3,):raise ValueError('초기 변위의 기준점과 이동 세 성분이 필요합니다.')
        u={n:(translation+G@(np.array(row['position_mm'])-origin)).tolist() for n,row in nodes.items()}
        for bc in model['boundary_dofs']:
            if not math.isclose(u[bc['node_id']][bc['component']-1],bc['value_mm'],rel_tol=1e-9,abs_tol=1e-10):
                raise ValueError('초기 affine 변위와 실제 지지·변위 구속이 일치하지 않습니다.')
        out['compatible']={'gradient':G.tolist(),'total_strain':six(epsilon),'stress_MPa':six(stress),
            'displacements_mm':[{'node_id':n,'value':u[n]} for n in sorted(u)],'origin_mm':origin.tolist(),
            'translation_mm':translation.tolist(),'initial_parameter':0.,'internal_variables':'none; elastic only'}
    return out


def effective(model):
    row=model.get('initial_fields')
    if row is None:return None
    if not isinstance(row,dict) or set(row)!={'draft','definition'}:raise ValueError('원 초기장 초안과 적용 정의가 필요합니다.')
    value=normalize(model,row['draft'])
    if value!=row['definition']:raise ValueError('초기장 정의가 원 메시·재료·선택과 다릅니다.')
    from .adapters.initial_field_deck import program
    program(model,value)
    return value
