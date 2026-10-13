"""Pure declarations for separate dimensioned ODE and linear weak-form adapters."""
from copy import deepcopy
import math
import re
from .dimensioned_expression import Meaning, ExpressionError, ZERO, UNITS, add_dim, unit_dimension, parse

ODE = 'pde.scipy.ode'
WEAK = 'pde.fenicsx.dimensioned'
BACKENDS = (ODE, WEAK)
RESERVED = {'t','x','y','u','v','pi','sin','cos','exp','log','sqrt','grad','inner'}


def fail(path,message):
    raise ExpressionError(message,path='settings.'+path)


def number(value,path,positive=False):
    if type(value) not in (int,float) or not math.isfinite(value) or (positive and value<=0):
        fail(path,'유한한 양수가 필요합니다.' if positive else '유한한 수가 필요합니다.')
    return value


def default_settings(backend):
    if backend==ODE:
        return {'states':[{'name':'temperature','label':'온도','unit':'K','initial':300.,
                           'rhs':'-rate*(temperature-ambient)','reference':'ambient+(initial-ambient)*exp(-rate*t)','atol':1e-7}],
                'parameters':[{'name':'rate','unit':'1/s','value':.5},
                              {'name':'ambient','unit':'K','value':290.},
                              {'name':'initial','unit':'K','value':300.}],
                'time':{'start':0.,'end':10.,'samples':101,'unit':'s'},
                'solver':{'method':'RK45','rtol':1e-7,'max_step':.25}}
    if backend==WEAK:
        return {'field':{'name':'temperature','label':'온도','unit':'K'},
                'parameters':[{'name':'k','value':1.,'unit':'W/(m*K)'},
                              {'name':'q','value':0.,'unit':'W/m**3'},
                              {'name':'left_value','value':300.,'unit':'K'},
                              {'name':'right_value','value':310.,'unit':'K'},
                              {'name':'length','value':1.,'unit':'m'}],
                'domain':{'width':1.,'height':1.,'unit':'m'},
                'space':{'family':'Lagrange','degree':1},
                'mesh':{'levels':[4,8]},
                'forms':{'bilinear':'k*inner(grad(u),grad(v))','linear':'q*v'},
                'boundaries':[{'side':'left','kind':'Dirichlet','expression':'left_value'},
                              {'side':'right','kind':'Dirichlet','expression':'right_value'}],
                'reference':'left_value+(right_value-left_value)*x/length',
                'solver':{'residual_relative':1e-9}}
    raise ValueError('지원되지 않은 차원식 모델입니다.')


def parameters(settings):
    rows=settings.get('parameters')
    if not isinstance(rows,list) or len(rows)>64: fail('parameters','계수는 최대 64개입니다.')
    symbols={}; values={}
    for i,row in enumerate(rows):
        path=f'parameters.{i}'
        if not isinstance(row,dict) or set(row)!={'name','unit','value'}: fail(path,'계수 이름·값·단위가 필요합니다.')
        name=row['name']
        if not isinstance(name,str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,47}',name) or name in RESERVED or name in symbols:
            fail(path+'.name','고유한 영문 계수 이름을 입력하세요.')
        dim=unit_dimension(row['unit'],path='settings.'+path+'.unit')
        symbols[name]=Meaning(dim); values[name]=number(row['value'],path+'.value')
        if abs(values[name])>1e100: fail(path+'.value','계수의 지원 범위는 ±1e100입니다.')
    return symbols,values


def checked_expression(source,symbols,path,expected,weak=False):
    tree,meaning=parse(source,symbols,path='settings.'+path,weak=weak)
    if meaning!=expected: fail(path,'식의 차원·성분·시험/해 차수가 선언과 다릅니다.')
    return tree


def validate_settings(backend,settings):
    if not isinstance(settings,dict): fail('','설정이 필요합니다.')
    s=deepcopy(settings); symbols,_=parameters(s)
    symbols['pi']=Meaning()
    if backend==ODE:
        if set(s)!={'states','parameters','time','solver'}: fail('','알 수 없는 ODE 설정입니다.')
        time=s['time']; solver=s['solver']; rows=s['states']
        if not isinstance(time,dict) or set(time)!={'start','end','samples','unit'} or time['unit']!='s':
            fail('time','시간 단위는 s이며 시작·끝·표본 수를 지정하세요.')
        a=number(time['start'],'time.start'); b=number(time['end'],'time.end')
        if b<=a or type(time['samples']) is not int or not 2<=time['samples']<=4096: fail('time','시간 구간과 2~4096개 출력점을 확인하세요.')
        if not isinstance(solver,dict) or set(solver)!={'method','rtol','max_step'} or solver['method'] not in ('RK45','DOP853','Radau','BDF'):
            fail('solver','RK45, DOP853, Radau, BDF 중 선택하세요.')
        if not 0<number(solver['rtol'],'solver.rtol',True)<1: fail('solver.rtol','상대 허용치는 0과 1 사이입니다.')
        if solver['rtol']<100*math.ulp(1.):
            fail('solver.rtol','현재 SciPy float64 최소 상대 허용치보다 작습니다 (100 × 기계 정밀도).')
        number(solver['max_step'],'solver.max_step',True)
        if not isinstance(rows,list) or not 1<=len(rows)<=16: fail('states','상태는 1~16개입니다.')
        symbols['t']=Meaning(UNITS['s'])
        for i,row in enumerate(rows):
            path=f'states.{i}'
            if not isinstance(row,dict) or set(row)!={'name','label','unit','initial','rhs','reference','atol'}:
                fail(path,'상태 이름·단위·초기값·미분식·기준식·절대 허용치가 필요합니다.')
            name=row['name']
            if not isinstance(name,str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,47}',name) or name in symbols or name in RESERVED:
                fail(path+'.name','고유한 상태 이름을 입력하세요.')
            dim=unit_dimension(row['unit'],path='settings.'+path+'.unit')
            symbols[name]=Meaning(dim)
            number(row['initial'],path+'.initial');number(row['atol'],path+'.atol',True)
            if not isinstance(row['label'],str) or not row['label'].strip(): fail(path+'.label','표시 이름을 입력하세요.')
        ref_symbols={k:v for k,v in symbols.items() if k not in {r['name'] for r in rows}}
        for i,row in enumerate(rows):
            dim=symbols[row['name']].dimension
            checked_expression(row['rhs'],symbols,f'states.{i}.rhs',Meaning(add_dim(dim,UNITS['s'],-1)))
            if row['reference']: checked_expression(row['reference'],ref_symbols,f'states.{i}.reference',Meaning(dim))
    elif backend==WEAK:
        if set(s)!={'field','parameters','domain','space','mesh','forms','boundaries','reference','solver'}: fail('','알 수 없는 약형식 설정입니다.')
        field=s['field']; domain=s['domain']
        if not isinstance(field,dict) or set(field)!={'name','label','unit'} or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,47}',str(field['name'])):
            fail('field','스칼라 장 이름·표시 이름·단위가 필요합니다.')
        dim=unit_dimension(field['unit'],path='settings.field.unit')
        if not isinstance(domain,dict) or set(domain)!={'width','height','unit'} or domain['unit']!='m': fail('domain','영역 길이는 m로 선언하세요.')
        number(domain['width'],'domain.width',True);number(domain['height'],'domain.height',True)
        if s['space']!={'family':'Lagrange','degree':1}: fail('space','현재 차원 약형식은 스칼라 Lagrange P1 삼각형입니다.')
        if not isinstance(s['mesh'],dict) or set(s['mesh'])!={'levels'}: fail('mesh','메시 수준을 지정하세요.')
        levels=s['mesh']['levels']
        if (not isinstance(levels,list) or not 1<=len(levels)<=5 or any(type(n) is not int or not 2<=n<=128 for n in levels)
                or levels!=sorted(set(levels))): fail('mesh.levels','서로 다른 증가 순서의 2~128 메시 수준을 지정하세요.')
        symbols.update(x=Meaning(UNITS['m']),y=Meaning(UNITS['m']))
        no_uv=dict(symbols);symbols.update(u=Meaning(dim,0,(1,0)),v=Meaning(dim,0,(0,1)))
        if not isinstance(s['forms'],dict) or set(s['forms'])!={'bilinear','linear'}: fail('forms','체적 이중선형식 a와 선형식 L을 입력하세요.')
        _,a=parse(s['forms']['bilinear'],symbols,path='settings.forms.bilinear',weak=True)
        _,b=parse(s['forms']['linear'],symbols,path='settings.forms.linear',weak=True)
        if a.rank or b.rank or a.degree!=(1,1) or b.degree!=(0,1) or a.dimension!=b.dimension:
            fail('forms','a(u,v)와 L(v)의 스칼라 차원이 같고 각각 이중선형/선형이어야 합니다.')
        sides=set()
        if not isinstance(s['boundaries'],list) or not s['boundaries']: fail('boundaries','Dirichlet 경계를 하나 이상 지정하세요.')
        for i,bc in enumerate(s['boundaries']):
            if (not isinstance(bc,dict) or set(bc)!={'side','kind','expression'} or bc['side'] not in ('left','right','bottom','top')
                    or bc['side'] in sides or bc['kind']!='Dirichlet'): fail(f'boundaries.{i}','고유한 면의 Dirichlet 경계만 지원합니다. 미지정 면은 약형식의 자연 경계입니다.')
            sides.add(bc['side'])
            checked_expression(bc['expression'],no_uv,f'boundaries.{i}.expression',Meaning(dim))
        if s['reference']: checked_expression(s['reference'],no_uv,'reference',Meaning(dim))
        if not isinstance(s['solver'],dict) or set(s['solver'])!={'residual_relative'}: fail('solver','상대 대수 잔차 한계를 지정하세요.')
        number(s['solver']['residual_relative'],'solver.residual_relative',True)
    else: raise ValueError('지원되지 않은 차원식 모델입니다.')
    return s


def model_declaration(backend,settings):
    s=validate_settings(backend,settings)
    return {'kind':'dimensioned_ode' if backend==ODE else 'dimensioned_linear_weak_form',
            'backend':backend,'model':s,'coordinate_unit':None if backend==ODE else 'm',
            'time_unit':'s' if backend==ODE else None}


def describe_inputs(backend,settings):
    s=validate_settings(backend,settings)
    return [{'id':row['name'],'label':row['name'],'unit':row['unit'],'value':row['value'],
             'lower':-1e100,'upper':1e100,
             'settings_path':['parameters',i,'value'],'declaration_paths':[['model','parameters',i,'value']]}
            for i,row in enumerate(s['parameters'])]


def bind_inputs(backend,settings,values):
    s=validate_settings(backend,settings)
    known={row['name']:row for row in s['parameters']}
    if not isinstance(values,dict) or set(values)-set(known): raise ValueError('등록된 계수만 변경할 수 있습니다.')
    for name,value in values.items(): known[name]['value']=number(value,'parameters.'+name)
    return validate_settings(backend,s)
