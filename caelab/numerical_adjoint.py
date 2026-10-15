"""Thin SciPy SLSQP/jac binding over existing Numerical evaluators and budgets.

Only the declared linear DefinitionFactory produces gradients. Independent FD
is an explicitly requested validation, never the implementation of jac.
"""
from copy import deepcopy
import math
from time import perf_counter
import numpy as np
import scipy
from scipy.optimize import minimize
from . import linear_adjoint_contract as contract


def assess_direction(f0, gp, plus, minus, taylor):
    """Evaluate fixed, predeclared criteria from raw observations, without solves."""
    fd = (plus-minus)/(2*contract.CENTRAL_H)
    mismatch = abs(gp-fd)
    tolerance = contract.CENTRAL_ATOL + contract.CENTRAL_RTOL*max(abs(gp),abs(fd))
    floor = contract.ROUNDOFF_FACTOR*(1.+abs(f0))
    rows=[]
    for h,value in zip(contract.TAYLOR_H,taylor):
        rows.append({'h':h,'value':value,'R0':abs(value-f0),'R1':abs(value-f0-h*gp)})
    for before,after in zip(rows,rows[1:]):
        ratio=math.log(before['h']/after['h'])
        after['R0_order']=math.log(before['R0']/after['R0'])/ratio if before['R0']>0 and after['R0']>0 else None
        after['R1_order']=math.log(before['R1']/after['R1'])/ratio if before['R1']>0 and after['R1']>0 else None
    first=all(row['R0']<=floor or row.get('R0_order') is not None and contract.FIRST_ORDER[0]<=row['R0_order']<=contract.FIRST_ORDER[1] for row in rows[-2:])
    second=all(row['R1']<=floor or row.get('R1_order') is not None and contract.TAYLOR_ORDER[0]<=row['R1_order']<=contract.TAYLOR_ORDER[1] for row in rows[-2:])
    return {'status':'PASS' if mismatch<=tolerance and first and second else 'FAIL',
            'adjoint_directional':gp,'central_difference':fd,'central_h':contract.CENTRAL_H,
            'absolute_mismatch':mismatch,'tolerance':tolerance,'roundoff_floor':floor,
            'taylor':rows,'first_order_passed':first,'second_order_passed':second,
            'classification':'ROUNDOFF_FLOOR' if all(r['R1']<=floor for r in rows) else 'SECOND_ORDER_TEST'}


def invalidate_unverified_candidates(rows, verification):
    """Keep raw retained primal/adjoint evidence, never rank a failed check."""
    if verification is None or verification.get('status') == 'PASS':
        return
    for row in rows:
        if row.get('purpose') == 'optimization':
            row.update(objective=None, objective_gradient=None, constraint_gradients=None,
                       gradients=None, feasible=False,
                       constraint_residuals=[None] * len(row.get('constraint_residuals', [])),
                       gradient_admission='VERIFICATION_' + str(verification.get('status')),
                       failure_reason='Independent gradient verification did not pass; raw attempts retained')


def optimize_adjoint(factory, variables, objective, *, settings=None, constraints=None,
                     seed=0, options=None, execution=None, record=None):
    from . import numerical as base
    from . import variable_domains as domains
    from .evaluation_definition import DefinitionFactory
    if not isinstance(factory,DefinitionFactory):
        raise ValueError('Adjoint 방법은 저장된 선형 Evaluation을 선택해야 합니다. 다른 backend에는 차분 진화를 사용하세요.')
    if type(seed) is not int or not 0 <= seed <= 2**32-1:
        raise ValueError('seed must be an unsigned 32-bit integer')
    opts=dict(options or {})
    if set(opts)-{'maxiter','ftol','initial_values','verify_gradient','retain_responses'}:
        raise ValueError('SLSQP adjoint options: maxiter, ftol, initial_values, verify_gradient, retain_responses')
    maxiter=opts.get('maxiter',30);ftol=base._number(opts.get('ftol',1e-8),'SLSQP ftol')
    if type(maxiter) is not int or not 1<=maxiter<=10000 or ftol<=0:
        raise ValueError('SLSQP maxiter/ftol must be positive')
    verify=opts.get('verify_gradient',False)
    if type(verify) is not bool:
        raise ValueError('verify_gradient must be explicitly true or false')
    retention=opts.get('retain_responses','summary')
    if retention not in {'summary','all'}:
        raise ValueError('retain_responses must be summary or all')
    execution=base._execution(execution)
    if execution['mode']!='serial' or execution['workers']!=1:
        raise ValueError('First adjoint SLSQP is serial, one existing worker owner')
    constraints=deepcopy(list(constraints or []))
    direction=objective.get('direction','minimize');scale=base._number(objective.get('scale',1.),'objective scale')
    if direction not in {'minimize','maximize'} or scale<=0:
        raise ValueError('Choose objective direction and positive scale')
    sign=1. if direction=='minimize' else -1.
    for c in constraints:
        if c.get('operator') not in {'<=','>='} or base._number(c.get('scale',1.),'constraint scale')<=0:
            raise ValueError('Constraints require <=/>= and positive scale')
        base._number(c.get('limit'),'constraint limit')
    admission=factory.configure_adjoint(variables,[objective]+constraints)
    domain=domains.VariableDomains(variables); names=[v['id'] for v in domain.free]
    encoded=domain.encoded(); lows=np.array([r['lower_bound'] for r in encoded]);widths=np.array([r['upper_bound']-r['lower_bound'] for r in encoded])
    initial=domain.encode(opts.get('initial_values'))
    z0=(np.array([initial[n] for n in names])-lows)/widths
    if verify and len(names)<2:
        raise ValueError('두 독립 방향 검사는 최소 두 자유 변수가 필요합니다. 검사 없이 adjoint 최적화는 가능합니다.')
    def physical(z):
        z=np.asarray(z,dtype=float)
        if z.shape!=lows.shape or not np.isfinite(z).all() or np.any(z<0.) or np.any(z>1.):
            raise ValueError('SciPy trial is outside its declared normalized bounds')
        free={}
        for i,v in enumerate(domain.free):
            value = v['lower'] if z[i]==0 else v['upper'] if z[i]==1 else (
                math.exp(lows[i]+widths[i]*z[i]) if v['transform']=='log' else lows[i]+widths[i]*z[i])
            free[v['id']]=value
        return domain.resolve(free)
    def chain(values):
        return np.array([widths[i]*(values[v['id']] if v['transform']=='log' else 1.) for i,v in enumerate(domain.free)])
    directions=[]
    if verify:
        for pair in ((.8,.6),(-.6,.8)):
            p=np.zeros(len(names));p[:2]=pair;directions.append(p)
            for h in (contract.CENTRAL_H,-contract.CENTRAL_H,*contract.TAYLOR_H):
                try:
                    physical(z0+h*p)
                except ValueError as error:
                    raise ValueError('독립 중앙/Taylor 검사는 모든 고정 검사점이 변수 범위 안에 드는 내부 초기값이 필요합니다. '
                                     '초기값을 조정하거나 독립 검사를 해제하세요 (verify_gradient=False).') from error
    rows=[];cache={};history=[];verification=None;verification_timing={};solver_result=None;termination='NOT_STARTED'
    counts={name:0 for name in ('objective','jacobian','constraint','constraint_jacobian','accepted_iteration')}
    started=perf_counter()
    with base._Evaluators(factory,[settings or {}],execution) as models:
        def evaluate(z, *, active=models, purpose='optimization'):
            resolution=physical(z);values=resolution['values'];key=domains.value_key(values)
            if purpose=='optimization' and key in cache:
                if models.cancelled(): raise base.StudyCancelled('USER_CANCELLED')
                return cache[key]
            if active.cancelled(): raise base.StudyCancelled('USER_CANCELLED')
            value=active.one(values)[0]
            row=domain.attach(base._row('C'+str(len(rows)).zfill(6),values,value),resolution)
            row.update(purpose=purpose,normalized_coordinates=np.asarray(z).tolist(),objective=None,
                       constraint_residuals=[None]*len(constraints),feasible=False,objective_gradient=None,constraint_gradients=None)
            rows.append(row)
            if value.get('diagnostics',{}).get('stop_reason')=='EVALUATION_BUDGET_EXHAUSTED':
                raise base.EvaluationBudgetExceeded('Stage/adjoint budget exhausted')
            if value.get('execution_status')=='CANCELLED' or active.cancelled():
                raise base.StudyCancelled('USER_CANCELLED')
            try:
                raw=base._scalar(value,objective)
                residuals=[(base._scalar(value,c)-c['limit'])/c.get('scale',1.)*(1. if c['operator']=='<=' else -1.) for c in constraints]
                row.update(objective=raw, constraint_residuals=residuals, feasible=all(r<=0 for r in residuals))
                numerical=sign*raw/scale
                if purpose!='optimization':
                    return row, numerical, None, None
                gradient=value.get('gradients')
                if not isinstance(gradient,dict):
                    raise base.EvaluationFailed('Actual successful discrete adjoint is unavailable')
                def physical_gradient(response):
                    selected=gradient.get(response['response'],{})
                    result=[]
                    for v in domain.free:
                        entry=selected.get(v['id'],{})
                        if entry.get('input_unit')!=v['unit'] or entry.get('response_unit')!=response['unit']:
                            raise base.EvaluationFailed('Adjoint variable/response units do not match the exact primal')
                        result.append(base._number(entry.get('value'),'actual adjoint component'))
                    return np.array(result)
                dx_dz=chain(values)
                g=physical_gradient(objective)*dx_dz*sign/scale
                cg=[physical_gradient(c)*dx_dz/c.get('scale',1.)*(1. if c['operator']=='<=' else -1.) for c in constraints]
                row['objective_gradient']={'values':g.tolist(),'coordinates':names,'unit':'scaled_objective/normalized_coordinate',
                    'dx_dz':dx_dz.tolist(),'direction_factor':sign,'response_scale':scale,
                    'physical_gradient':physical_gradient(objective).tolist(),'source':'discrete_linear_adjoint',
                    'formula':'g_z=(direction/response_scale)*g_x*dx_dz'}
                def components(physical,scaled):
                    return [{'id':v['id'],'input_unit':v['unit'],'physical':float(physical[i]),
                        'dx_dz':float(dx_dz[i]),'value':float(scaled[i])} for i,v in enumerate(domain.free)]
                row['objective_gradient']['components']=components(physical_gradient(objective),g)
                row['constraint_gradients']=[{'response':c['response'],'response_unit':c['unit'],
                    'operator':c['operator'],'limit':c['limit'],'response_scale':c.get('scale',1.),
                    'operator_factor':1. if c['operator']=='<=' else -1.,
                    'unit':'scaled_constraint_residual/normalized_coordinate',
                    'physical_gradient':physical_gradient(c).tolist(),'values':cg[i].tolist(),
                    'scipy_inequality_values':(-cg[i]).tolist(),'coordinates':names,
                    'components':components(physical_gradient(c),cg[i]),'source':'discrete_linear_adjoint',
                    'formula':'g_z=(operator_factor/response_scale)*g_x*dx_dz; SciPy ineq jac=-g_z'}
                    for i,c in enumerate(constraints)]
                answer=(row,numerical,g,cg);cache[key]=answer
                return answer
            except (ValueError,KeyError,base.EvaluationFailed) as error:
                row.update(objective=None,objective_gradient=None,gradients=None,constraint_gradients=None,
                           constraint_residuals=[None]*len(constraints),feasible=False,failure_reason=str(error))
                raise base.EvaluationFailed(str(error)) from error
        try:
            first,f0,g0,_=evaluate(z0)
            if verify:
                verification={'status':'RUNNING','base_candidate':first['candidate_id'],'base_value':f0,
                    'coordinate_system':'normalized existing linear/log encoded bounds','directions':[],
                    'thresholds':{'central_atol':contract.CENTRAL_ATOL,'central_rtol':contract.CENTRAL_RTOL,
                        'taylor_order':list(contract.TAYLOR_ORDER),'first_order':list(contract.FIRST_ORDER),
                        'roundoff_factor':contract.ROUNDOFF_FACTOR}}
                with base._Evaluators(factory.primal_only(),[settings or {}],execution,budget=models.budget) as checks:
                    for p in directions:
                        raw_rows=[]
                        def probe(h):
                            row,f,_,_=evaluate(z0+h*p,active=checks,purpose='gradient_verification')
                            raw_rows.append({'h':h,'candidate_id':row['candidate_id'],'value':f,
                                             'evaluation_refs':deepcopy(row.get('evaluation_refs',[]))})
                            return f
                        plus=probe(contract.CENTRAL_H);minus=probe(-contract.CENTRAL_H)
                        taylor=[probe(h) for h in contract.TAYLOR_H]
                        verdict=assess_direction(f0,float(g0@p),plus,minus,taylor)
                        verification['directions'].append({**verdict,'direction':p.tolist(),'samples':raw_rows})
                    verification['verification_model_calls']=checks.model_calls
                    verification_timing=checks.timing()
                verification['status']='PASS' if all(d['status']=='PASS' for d in verification['directions']) else 'FAIL'
                if verification['status']!='PASS':
                    raise base.EvaluationFailed('Independent central/Taylor check failed; original tolerances retained')
            def objective_fun(z):
                counts['objective']+=1
                row,f,_,_=evaluate(z);history.append({'callback':'objective','candidate_id':row['candidate_id']})
                return f
            def jac(z):
                counts['jacobian']+=1
                row,_,g,_=evaluate(z);history.append({'callback':'jacobian','candidate_id':row['candidate_id'],'gradient':g.tolist()})
                return g.copy()
            scipy_constraints=[]
            for i in range(len(constraints)):
                def cfun(z,index=i):
                    counts['constraint']+=1
                    row,_,_,_=evaluate(z);return -row['constraint_residuals'][index]
                def cjac(z,index=i):
                    counts['constraint_jacobian']+=1
                    _,_,_,cg=evaluate(z);return -cg[index].copy()
                scipy_constraints.append({'type':'ineq','fun':cfun,'jac':cjac})
            def accepted(z):
                counts['accepted_iteration']+=1
                row,_,_,_=evaluate(z);history.append({'callback':'accepted_iteration','candidate_id':row['candidate_id']})
            solved=minimize(objective_fun,z0,method='SLSQP',jac=jac,bounds=[(0.,1.)]*len(names),
                            constraints=scipy_constraints,callback=accepted,options={'maxiter':maxiter,'ftol':ftol,'disp':False})
            solver_result={key:deepcopy(getattr(solved,key)) for key in ('success','status','message','nit','nfev','njev')}
            solver_result['x']=solved.x.tolist()
            solver_result['fun']=float(solved.fun)
            if hasattr(solved,'multipliers'):solver_result['multipliers']=solved.multipliers.tolist()
            termination='CONVERGED' if solved.success else 'SCIPY_NOT_CONVERGED'
        except base.StudyCancelled:
            termination='USER_CANCELLED'
        except base.EvaluationBudgetExceeded:
            termination='EVALUATION_BUDGET_EXHAUSTED'
        except base.EvaluationFailed as error:
            termination='GRADIENT_CHECK_FAILED' if verification and verification['status']=='FAIL' else 'STOPPED_AFTER_FAILURE'
            history.append({'callback':'stopped','reason':str(error)})
        except base.ExecutionCleanupFailed:
            raise
        except Exception as error:
            termination='ENGINE_ERROR';history.append({'callback':'stopped','reason':type(error).__name__+': '+str(error)})
        timing=models.timing()
        timing['optimization_candidate_calls']=models.model_calls
        timing['verification_candidate_calls']=sum(r.get('purpose')=='gradient_verification' for r in rows)
        timing['model_calls']=timing['optimization_candidate_calls']+timing['verification_candidate_calls']
        timing['verification_model_seconds_sum']=verification_timing.get('model_seconds_sum')
        if verification_timing:
            timing['model_seconds_sum']+=verification_timing['model_seconds_sum']
    if verification and verification['status']=='RUNNING':
        verification['status']='INCOMPLETE';verification['stop_reason']=termination
    invalidate_unverified_candidates(rows,verification)
    eligible=[r for r in rows if r['purpose']=='optimization' and r['execution_status']=='SUCCEEDED' and r['feasible'] and r['objective'] is not None and r['objective_gradient'] is not None]
    best=deepcopy(min(eligible,key=lambda r:sign*r['objective'])) if eligible else None
    if retention=='summary':
        for row in rows:
            row['responses']={k:v for k,v in row['responses'].items() if v.get('kind') in {'scalar','event'}}
    timing.update(total_seconds=perf_counter()-started, primal_dispatches=sum(ref['stage_execution_count'] for r in rows for ref in r.get('evaluation_refs',[])),
                  actual_adjoint_dispatches=sum(ref.get('adjoint_execution_count',0) for r in rows for ref in r.get('evaluation_refs',[])))
    status='SUCCEEDED' if termination=='CONVERGED' and best else 'CANCELLED' if termination=='USER_CANCELLED' else 'REJECTED' if termination=='EVALUATION_BUDGET_EXHAUSTED' else 'PARTIAL_FAILURE' if best else 'FAILED'
    result={'kind':'optimization','method':contract.METHOD,'variables':domain.variables,'objective_definition':deepcopy(objective),
        'constraint_definitions':constraints,'candidates':rows,'best':best,'execution_status':status,'termination_reason':termination,
        'algorithm':{'engine':'scipy.optimize.minimize','method':'SLSQP','scipy_version':scipy.__version__,
                     'jac':'callable: actual discrete_linear_adjoint','finite_difference_jac':False,
                     'options':{'maxiter':maxiter,'ftol':ftol},'admission':admission},
        'solver_result':solver_result,'callback_counts':counts,'optimizer_history':history,
        'gradient_verification':verification,'timing':timing,
        'response_retention':{'candidates':retention,'best':'all','native_originals':'retained'},
        'limitations':['First steady linear scalar adjoint only; nonlinear Picard uses DE.',
                       'SLSQP is a local optimizer; solver convergence is not global optimality or engineering qualification.']}
    return base._record(domains.annotate_result(result,domain),record)
