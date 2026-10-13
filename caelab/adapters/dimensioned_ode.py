"""Explicit ODE execution through installed SciPy; pure edit/check stays solver-free."""
from copy import deepcopy
import math
import numpy as np
from .. import dimensioned_models as domain
from ..dimensioned_expression import parse, evaluate, Meaning, UNITS
from ..execution_control import check_cancelled
from ..storage import save_json


class DimensionedODEAdapter:
    backend=domain.ODE
    version='1'
    def default_settings(self): return domain.default_settings(self.backend)
    def validate_settings(self,settings): return domain.validate_settings(self.backend,settings)
    def describe_model(self,settings): return domain.model_declaration(self.backend,settings)
    def describe_inputs(self,settings): return domain.describe_inputs(self.backend,settings)
    def bind_inputs(self,settings,values): return domain.bind_inputs(self.backend,settings,values)

    def run(self,settings,*,output,runtime=None):
        from scipy.integrate import solve_ivp
        import scipy
        if runtime and set(runtime)-{'threads','memory_mb'}: raise ValueError('지원하지 않는 ODE 실행 설정입니다.')
        s=self.validate_settings(settings)
        save_json(output/'input.json',s)
        symbols,coefficients=domain.parameters(s)
        symbols.update(pi=Meaning(),t=Meaning(UNITS['s']))
        symbols.update({r['name']:Meaning(domain.unit_dimension(r['unit'])) for r in s['states']})
        rhs=[parse(r['rhs'],symbols)[0] for r in s['states']]
        names=[r['name'] for r in s['states']]
        evaluations=0
        def function(t,y):
            nonlocal evaluations
            check_cancelled();evaluations+=1
            if evaluations>200000:raise RuntimeError('미분식 평가 200000회 한도에 도달했습니다. 허용치와 시간 구간을 확인하세요.')
            values={**coefficients,'pi':math.pi,'t':float(t),**dict(zip(names,y))}
            answer=np.asarray([evaluate(tree,values) for tree in rhs],dtype=float)
            if not np.isfinite(answer).all(): raise ValueError('미분식이 유한하지 않습니다.')
            return answer
        times=np.linspace(s['time']['start'],s['time']['end'],s['time']['samples'])
        sol=solve_ivp(function,(times[0],times[-1]),[r['initial'] for r in s['states']],
                      t_eval=times,method=s['solver']['method'],rtol=s['solver']['rtol'],
                      atol=[r['atol'] for r in s['states']],max_step=s['solver']['max_step'])
        check_cancelled()
        responses={}
        for i,row in enumerate(s['states']):
            response={'kind':'series','value':sol.y[i].copy(),'unit':row['unit'],
                      'component':row['name'],'location':'state','reduction':'none',
                      'frame':'declared_state','measure':row['label'],
                      'axes':[{'name':'time','unit':'s','values':sol.t.copy()}]}
            responses[row['name']]=response
            if row['reference']:
                ref_symbols={k:v for k,v in symbols.items() if k not in names}
                tree=parse(row['reference'],ref_symbols)[0]
                reference=np.asarray([evaluate(tree,{**coefficients,'pi':math.pi,'t':float(t)}) for t in sol.t])
                if not np.isfinite(reference).all(): raise ValueError('기준식이 유한하지 않습니다.')
                responses[row['name']+'_reference']={**deepcopy(response),'value':reference,'measure':'user_declared_reference'}
                responses[row['name']+'_error']={**deepcopy(response),'value':sol.y[i]-reference,'measure':'computed_minus_user_reference'}
        return {'execution_status':'SUCCEEDED' if sol.success else 'FAILED','responses':responses,
                'checks':[{'name':'integration','status':'PASS' if sol.success else 'FAIL','observed':sol.message}],
                'diagnostics':{'library':'scipy','version':scipy.__version__,'nfev':sol.nfev,
                               'reason':None if sol.success else sol.message,'decision':'NOT_RELEASED',
                               'partial_output':len(sol.t)!=len(times),'residual':'NOT_REPORTED_BY_SOLVER',
                               'initial_state':[r['initial'] for r in s['states']]}}
