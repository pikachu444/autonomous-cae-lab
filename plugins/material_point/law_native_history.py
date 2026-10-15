"""Accepted-state history and independent same-state tangent probes.

Mixed boundary conditions consume the EXISTING material_control Newton loop,
with one frozen accepted constitutive state per increment. No new optimizer.
"""
from copy import deepcopy
import numpy as np
from . import law_native as law
from .law_native_tensors import BASIS, K6, F9, tensor, kelvin
from caelab.storage import canonical_hash
from caelab.execution_control import check_cancelled, ExecutionCancelled, ExecutionCleanupFailed


def tangent_probe(settings, initial, F, time, steps, *, analytic_override=None):
    """Differentiate the discrete UPDATE, not the continuum rate tangent."""
    initial=deepcopy(initial);initial_hash=canonical_hash(initial)
    finite=settings['model']=='neo_hooke'
    nominal=law.update(settings,deepcopy(initial),np.asarray(F).copy(),time)
    analytic=nominal['tangent'] if analytic_override is None else np.asarray(analytic_override)
    n=9 if finite else 6
    base=np.asarray(nominal['stress']).reshape(n)
    scale=max(float(np.max(abs(analytic))) if analytic is not None else 1.,1.)
    relative=1e-8 if settings['model']=='single_branch_maxwell' else 2e-6
    absolute=2e-10*max(abs(v) for k,v in settings['parameters'].items() if k not in ('nu','alpha','beta','tau'))
    rows=[];all_smooth=True;any_failed=False
    for h in steps:
        row={'h':float(h),'initial_state_sha256':initial_hash,'initial_state':deepcopy(initial),
             'analytic':None if analytic is None else np.asarray(analytic).tolist(),'columns':[]}
        for j in range(n):
            check_cancelled()
            delta=np.zeros((3,3))
            if finite:delta.flat[j]=h
            else:delta=h*BASIS[j]
            signed={};observed={}
            for sign in (-1,1):
                Fi=np.asarray(F)+sign*delta
                try:
                    if finite:
                        result=law.update(settings,deepcopy(initial),Fi,time)
                    else:
                        # Perturb in the declared Kelvin gradient coordinates, not
                        # F=I+eps: adding tiny h near 1 needlessly loses precision.
                        ei=kelvin(np.asarray(F)-np.eye(3));ei[j]+=sign*h
                        result=(law.dp if settings['model']==law.dp.MODEL else law.sls).integrate(
                            settings['parameters'],deepcopy(initial),ei,time)
                    signed[sign]=result
                    observed[str(sign)]={'input_F':Fi.tolist(),'stress':np.asarray(result['stress']).reshape(n).tolist(),
                        'trial_state':deepcopy(result['state']),'active_set':result['diagnostics']['active_set'],
                        'differentiable':result['diagnostics']['differentiable'],
                        'initial_state_sha256':initial_hash,'local_residual':result['diagnostics'].get('local_residual'),
                        'actual_gradient':Fi.reshape(9).tolist() if finite else ei.tolist()}
                except (ExecutionCancelled,ExecutionCleanupFailed):raise
                except Exception as error:
                    observed[str(sign)]={'input_F':Fi.tolist(),'error':str(error),'error_type':type(error).__name__,
                                         'initial_state_sha256':initial_hash}
            same=[sign for sign in (-1,1) if sign in signed and signed[sign]['diagnostics']['active_set']==nominal['diagnostics']['active_set']
                  and signed[sign]['diagnostics']['differentiable']]
            scheme='central' if len(same)==2 else 'one_sided' if same else 'unavailable'
            fd=None
            if len(same)==2:
                fd=(np.asarray(signed[1]['stress']).reshape(n)-np.asarray(signed[-1]['stress']).reshape(n))/(2*h)
            elif same:
                sign=same[0];fd=(np.asarray(signed[sign]['stress']).reshape(n)-base)/(sign*h)
            smooth=nominal['diagnostics']['differentiable'] and analytic is not None
            err=None if fd is None or analytic is None else float(np.max(abs(fd-np.asarray(analytic)[:,j])))
            if not smooth or fd is None:
                verdict='NONDIFFERENTIABLE' if not smooth else 'UNAVAILABLE';all_smooth=False
            else:
                verdict='PASS' if err<=absolute+relative*scale else 'FAIL'
                any_failed |= verdict=='FAIL'
                if scheme!='central':all_smooth=False
            row['columns'].append({'component':(F9 if finite else K6)[j], 'scheme':scheme,'probes':observed,
                'finite_difference':None if fd is None else fd.tolist(),'maximum_absolute_error':err,
                'absolute_limit':absolute+relative*scale,'status':verdict})
        rows.append(row)
    if canonical_hash(initial)!=initial_hash:
        raise RuntimeError('Probe mutated accepted state')
    status='FAIL' if any_failed else 'PASS' if all_smooth else 'NONDIFFERENTIABLE_OR_ONE_SIDED'
    return {'status':status,'pair':law.declaration(settings)['tangent_pair'],'frame':law.FRAME,
            'unit':settings['stress_unit'],'gradient_unit':'1','tangent_kind':'consistent_discrete',
            'initial_state_sha256':initial_hash,'nominal_active_set':nominal['diagnostics']['active_set'],
            'nominal_state':deepcopy(nominal['state']),'rows':rows}


def _controlled(s, initial, previous_F, index):
    from caelab.material_control import solve_history
    F=np.asarray(s['deformation_gradient'][index])
    bc=s['boundary_control'];time=s['time'][index]
    carrier={'model':s['model'],'parameters':deepcopy(s['parameters']),'stress_unit':s['stress_unit'],'time_unit':'s',
             'boundary_control':{'stress_components':{key:[values[index]] for key,values in bc['stress_components'].items()},
                'solver':deepcopy(bc['solver']),'initial_state':{'deformation_gradient':np.asarray(previous_F).tolist()},
                'stress_measure':law.declaration(s)['stress_measure'],'frame':law.FRAME}}
    def response(Ftrial):
        result=law.update(s,deepcopy(initial),Ftrial,time)
        stress,tangent=law.physical_response(s,result)
        if tangent is None:
            raise ValueError('NONDIFFERENTIABLE: no unique local tangent for boundary Newton')
        return stress,tangent
    result=solve_history(carrier,response,check_cancelled=check_cancelled,
                         _validated_context=(s['model'],np.array([time]),F[None,:,:]))
    if result['execution_status']!='SUCCEEDED':
        error=RuntimeError('Mixed-boundary solve failed without constitutive commit')
        error.evidence=deepcopy(result['diagnostics']['failed_increment'])
        raise error
    row=result['diagnostics']['constitutive_increments'][0]
    return np.asarray(row['deformation_gradient']),{key:deepcopy(row[key]) for key in
        ('residual','tolerance','iterations','iteration_trace')}


def evaluate_history(settings):
    s=law.validate_settings(settings);decl=law.declaration(s)
    accepted=deepcopy(s['initial_state']);lastF=np.asarray(s['deformation_gradient'][0])
    records=[];probes=[];failed=None
    for index,time in enumerate(s['time']):
        check_cancelled()
        before=deepcopy(accepted);F=np.asarray(s['deformation_gradient'][index]);control=None
        try:
            if index==0:
                result=law.initial_response(s)
                if s.get('boundary_control'):
                    sigma,_=law.physical_response(s,result)
                    for name,values in s['boundary_control']['stress_components'].items():
                        i,j=('xyz'.index(c) for c in name)
                        if abs(sigma[i,j]-values[0])>s['boundary_control']['solver']['atol']:
                            raise ValueError('Initial accepted state violates prescribed initial stress')
            else:
                if s.get('boundary_control'):
                    F,control=_controlled(s,before,lastF,index)
                result=law.update(s,deepcopy(before),F,time)
            stress,tangent=law.physical_response(s,result)
            row={'increment':index,'time':float(time),'time_unit':'s','F':F.tolist(),
                'strain_kelvin':None if s['model']=='neo_hooke' else result['state']['strain_kelvin'],
                'stress':np.asarray(result['stress']).tolist(),'stress_tensor':stress.tolist(),
                'stress_unit':s['stress_unit'],'stress_measure':decl['stress_measure'],
                'tangent':None if result['tangent'] is None else np.asarray(result['tangent']).tolist(),
                'tangent_pair':decl['tangent_pair'],'frame':law.FRAME,
                'initial_state':deepcopy(before),'initial_state_sha256':canonical_hash(before),
                'trial_state':deepcopy(result['state']),'committed_state':deepcopy(result['state']),
                'local':deepcopy(result['diagnostics']),'boundary':control,
                'stored_energy':result['stored_energy'],'dissipated_energy':result['dissipated_energy']}
            if s.get('tangent_probe',{}).get('increment')==index:
                probe=tangent_probe(s,before,F,time,s['tangent_probe']['steps'])
                row['tangent_probe']=probe;probes.append(probe)
                if probe['status']=='FAIL':
                    row['committed_state']=None
                    error=ValueError('Independent discrete tangent check failed; increment was not committed')
                    error.evidence={'failure':'INDEPENDENT_TANGENT_FAIL','partial_response':deepcopy(row)}
                    raise error
            # Commit only accepted nominal + requested-check success, never a failed trial.
            accepted=deepcopy(result['state']);lastF=F.copy();records.append(row)
        except (ExecutionCancelled,ExecutionCleanupFailed):raise
        except Exception as error:
            failed={'increment':index,'time':time,'trial_F':F.tolist(),'error':str(error),
                'error_type':type(error).__name__,'local_evidence':deepcopy(getattr(error,'evidence',None)),
                'last_accepted_state':deepcopy(before),'last_accepted_state_sha256':canonical_hash(before)}
            break
    responses={};axis=[{'name':'time','unit':'s','values':[r['time'] for r in records]}]
    for i,a in enumerate('xyz'):
        for j,b in enumerate('xyz'):
            responses['stress_'+a+b]={'kind':'series','value':[r['stress_tensor'][i][j] for r in records],
                'unit':s['stress_unit'],'component':a+b,'location':'material_point','reduction':'none',
                'axes':deepcopy(axis),'frame':law.FRAME,'measure':decl['stress_measure'],
                'partial':failed is not None,'valid':failed is None}
    for name in ('stored_energy','dissipated_energy'):
        if records and all(r[name] is not None for r in records):
            responses[name]={'kind':'series','value':[r[name] for r in records],'unit':s['stress_unit'],
                'component':name,'location':'material_point','reduction':'none','axes':deepcopy(axis),
                'measure':'energy_per_reference_volume','frame':law.FRAME,'valid':failed is None}
    tangent_failed=any(p['status']=='FAIL' for p in probes)
    return {'execution_status':'FAILED' if failed or tangent_failed else 'SUCCEEDED',
        'responses':responses,'checks':[{'name':'constitutive_history','status':'FAIL' if failed else 'PASS'},
            {'name':'independent_tangent','status':'FAIL' if tangent_failed else
             'PASS' if probes and all(p['status']=='PASS' for p in probes) else 'NOT_ASSESSED'},
            {'name':'physical_calibration','status':'NOT_ASSESSED'}],
        'diagnostics':{'declaration':decl,'constitutive_increments':records,'tangent_probes':probes,
            'last_accepted_state':accepted,'failed_increment':failed,
            'unattempted_increments':list(range(len(records)+(1 if failed else 0),len(s['time']))),
            'initial_state':deepcopy(s['initial_state']),'execution_layer':'material_point',
            'FE_execution':'NOT_RUN','build_execution':'NOT_REQUIRED_TRUSTED_BUILTIN_SOURCE',
            'strength':'UNKNOWN','engineering_release':'UNKNOWN',
            'unavailable':['DP dissipated energy not implemented'] if s['model']==law.dp.MODEL else []}}
