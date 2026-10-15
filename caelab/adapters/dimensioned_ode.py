"""Explicit installed SciPy IVP, retaining accepted output on failure/cancel."""
from copy import deepcopy
from pathlib import Path
import math
import numpy as np
from .. import dimensioned_models as domain
from ..dimensioned_expression import parse,evaluate,Meaning,UNITS
from ..execution_control import check_cancelled,ExecutionCancelled,ExecutionCleanupFailed
from ..storage import save_json


class DimensionedODEAdapter:
    backend=domain.ODE
    version='1'
    def default_settings(self):return domain.default_settings(self.backend)
    def validate_settings(self,settings):return domain.validate_settings(self.backend,settings)
    def describe_model(self,settings):return domain.model_declaration(self.backend,settings)
    def describe_inputs(self,settings):return domain.describe_inputs(self.backend,settings)
    def bind_inputs(self,settings,values):return domain.bind_inputs(self.backend,settings,values)

    def run(self,settings,*,output,runtime=None):
        from scipy.integrate import RK45,DOP853,Radau,BDF
        import scipy
        if runtime and set(runtime)-{'threads','memory_mb'}:raise ValueError('지원하지 않는 ODE 실행 설정입니다.')
        s=self.validate_settings(settings);folder=Path(output)/'pde';folder.mkdir(exist_ok=False)
        save_json(folder/'input.json',s)
        symbols,coefficients=domain.parameters(s)
        symbols.update(pi=Meaning(),t=Meaning(UNITS['s']))
        symbols.update({r['name']:Meaning(domain.unit_dimension(r['unit'])) for r in s['states']})
        rhs=[parse(r['rhs'],symbols)[0] for r in s['states']]
        names=[r['name'] for r in s['states']];evaluations=0
        def function(t,y):
            nonlocal evaluations
            check_cancelled();evaluations+=1
            if evaluations>200000:raise RuntimeError('미분식 평가 200000회 한도입니다. 허용치와 시간 구간을 확인하세요.')
            answer=np.asarray([evaluate(tree,{**coefficients,'pi':math.pi,'t':float(t),**dict(zip(names,y))})
                               for tree in rhs],dtype=float)
            if not np.isfinite(answer).all():raise ValueError('미분식이 유한하지 않습니다.')
            return answer
        requested=np.linspace(s['time']['start'],s['time']['end'],s['time']['samples'])
        initial=[r['initial'] for r in s['states']]
        times=[float(requested[0])];samples=[initial[:]]
        accepted={'time':times[0],'state':initial[:],'kind':'declared_initial_condition'}
        accepted_steps=0;solver=None;reason=None;status='SUCCEEDED'
        def checkpoint():
            save_json(folder/'ode_progress.json',{'times':times,'states':samples,'last_accepted':accepted,
                'accepted_steps':accepted_steps,'rhs_calls':evaluations,
                'output_sampling':'declared clock, dense output of accepted SciPy steps only'})
        checkpoint()
        try:
            check_cancelled()
            method={'RK45':RK45,'DOP853':DOP853,'Radau':Radau,'BDF':BDF}[s['solver']['method']]
            solver=method(function,requested[0],initial,requested[-1],max_step=s['solver']['max_step'],
                          rtol=s['solver']['rtol'],atol=[r['atol'] for r in s['states']])
            while solver.status=='running':
                check_cancelled()
                message=solver.step()
                if solver.status=='failed':raise RuntimeError(message or 'SciPy 적분 단계 실패')
                if not np.isfinite(solver.y).all():raise ValueError('수락된 상태가 유한하지 않습니다.')
                accepted_steps+=1
                accepted={'time':float(solver.t),'state':solver.y.tolist(),'kind':'accepted_solver_step'}
                # Trial RHS calls are NEVER saved as accepted output. The same
                # method-local interpolant used by solve_ivp samples this clock.
                stop=int(np.searchsorted(requested,solver.t,side='right'));start=len(times)
                if stop>start:
                    values=np.asarray(solver.dense_output()(requested[start:stop]),dtype=float)
                    if not np.isfinite(values).all():raise ValueError('수락 단계의 출력 보간이 유한하지 않습니다.')
                    times.extend(requested[start:stop].tolist());samples.extend(values.T.tolist())
                    checkpoint()
            check_cancelled() # completed samples remain retained if cancel arrived late
        except ExecutionCleanupFailed:raise
        except (ExecutionCancelled,ValueError,RuntimeError,ArithmeticError) as error:
            status='CANCELLED' if isinstance(error,ExecutionCancelled) else 'FAILED';reason=str(error)
        checkpoint()
        values=np.asarray(samples,dtype=float).T;clock=np.asarray(times)
        responses={};used=set(names);channels={};reference_errors={}
        checks=[{'name':'integration','status':'PASS' if status=='SUCCEEDED' else 'FAIL','observed':reason}]
        def derived(name,suffix):
            candidate=name+'_'+suffix;index=2
            while candidate in used:
                candidate=name+'_'+suffix+'_'+str(index);index+=1
            used.add(candidate);return candidate
        for i,row in enumerate(s['states']):
            response={'kind':'series','value':values[i].copy(),'unit':row['unit'],'component':row['name'],
                'location':'state','reduction':'none','frame':'declared_state','measure':row['label'],
                'axes':[{'name':'time','unit':'s','values':clock.copy()}]}
            responses[row['name']]=response;channels[row['name']]={'state':row['name']}
            if row['reference']:
                try:
                    ref_symbols={k:v for k,v in symbols.items() if k not in names}
                    tree=parse(row['reference'],ref_symbols)[0]
                    reference=np.asarray([evaluate(tree,{**coefficients,'pi':math.pi,'t':float(t)}) for t in clock],dtype=float)
                    if reference.shape!=clock.shape or not np.isfinite(reference).all():
                        raise ValueError('기준식이 유한한 스칼라가 아닙니다.')
                except (ValueError,TypeError,ArithmeticError) as error:
                    reference_errors[row['name']]=str(error)
                    checks.append({'name':row['name']+'_reference','status':'FAIL','reason':str(error)})
                    continue
                ref_id,error_id=derived(row['name'],'reference'),derived(row['name'],'error')
                responses[ref_id]={**deepcopy(response),'value':reference,'measure':'user_declared_reference'}
                responses[error_id]={**deepcopy(response),'value':values[i]-reference,'measure':'computed_minus_user_reference'}
                channels[row['name']].update(reference=ref_id,error=error_id)
        return {'execution_status':status,'responses':responses,'checks':checks,
            'diagnostics':{'library':'scipy','version':scipy.__version__,'solver_method':s['solver']['method'],'nfev':getattr(solver,'nfev',evaluations),
                'rhs_calls':evaluations,'accepted_steps':accepted_steps,'last_accepted':accepted,
                'reason':reason,'decision':'NOT_RELEASED','partial_output':len(times)!=len(requested),
                'residual':'NOT_REPORTED_BY_SOLVER','initial_state':initial,'response_channels':channels,
                'reference_errors':reference_errors,'output_sampling':'declared clock / accepted-step dense output'}}
