"""Bounded real scikit-fem/owned-worker checks. No positive physics test uses a double.

Fault-injection tests retain the original solved field separately and label the
altered transfer explicitly. Windows/Qt/native GUI acceptance is not claimed.
"""
from copy import deepcopy
from importlib.util import find_spec
import json
import os
from pathlib import Path
import shutil
import threading
import time
import uuid
import numpy as np
import pytest

if find_spec('skfem') is None:
    pytest.skip('NOT_RUN: scikit-fem 12.0.2 is not installed; no replacement solver or synthetic success',
                allow_module_level=True)

from caelab import evaluation,numerical
from caelab.storage import canonical_hash,save_json,load_json
from caelab.evaluation_definition import execute,definition_hash,DefinitionFactory
from caelab.execution_control import CancellationToken,cancellation_scope
from caelab.linear_adjoint_contract import configure
from tests.test_s2_shared_admission import compiled_case


@pytest.fixture(scope='module')
def evidence(tmp_path_factory):
    root=Path(os.environ.get('S2_EVIDENCE_ROOT',str(tmp_path_factory.mktemp('s2-real'))))
    root.mkdir(parents=True,exist_ok=False) if not root.exists() else None
    return root


def run_stage(model,output):
    return evaluation.run(model['backend'],model['settings'],output=output)


def create(comp,root,values=None,*,callback=run_stage,reserve=None,adjoint=None):
    path=root/('run-'+uuid.uuid4().hex)
    result=execute(comp,path,callback,values=values,reserve=reserve,derivative_request=adjoint)
    return path,evaluation.read_result(path,verify='all')


def record(root,name,value):
    save_json(root/(name+'.json'),value)


@pytest.fixture(scope='module')
def linear(evidence):
    comp,_,request=compiled_case('adjoint')
    vars=request['inputs']['variables']+[{'id':'T0','unit':'K','lower':295.,'upper':305.,'value':300.,'transform':'linear'}]
    admission=configure(comp,vars,[request['inputs']['objective']])
    path,result=create(comp,evidence,{'k':20.,'q':10000.,'T0':300.},adjoint=admission)
    assert result['execution_status']=='SUCCEEDED',result['diagnostics']
    return comp,request,path,result,admission


def test_actual_linear_transpose_nonzero_bc_direct_and_primal_link(evidence,linear):
    _,_,path,r,_=linear
    info=r['gradient_provenance'];receipt=info['adjoint_receipt']
    assert receipt['free_dofs']==9 and receipt['adjoint_solve_calls']==1
    assert receipt['primal_solve_calls']==receipt['assembly_calls']==receipt['finite_difference_calls']==0
    assert receipt['primal_relative_residual']<=1e-10 and receipt['adjoint_relative_residual']<=1e-10
    assert info['primal_reference']['result_sha256']==r['stages'][0]['result_sha256']
    g=r['gradients']['mean_temperature']
    assert abs(g['k']['value'])>1e-6 and abs(g['q']['value'])>1e-6
    assert abs(g['T0']['value']-1.)<1e-10
    parts=g['T0']['target_partials'][0]
    assert parts['direct']>0 and parts['residual_term']>0
    record(evidence,'linear-adjoint',{'directory':str(path),'gradient':g,'provenance':info})


@pytest.mark.parametrize('key,h', [('k',1e-3),('q',.1),('T0',.01)])
def test_independent_central_from_original_state(evidence,linear,key,h):
    comp,_,_,base,_=linear;values={'k':20.,'q':10000.,'T0':300.}
    raw=[]
    for sign in (1,-1):
        v=dict(values);v[key]+=sign*h
        path,result=create(comp,evidence,v)
        assert result['execution_status']=='SUCCEEDED'
        assert result['adjoint_execution_count']==0
        raw.append({'h':sign*h,'directory':str(path),'value':result['responses']['mean_temperature']['value']})
    fd=(raw[0]['value']-raw[1]['value'])/(2*h);g=base['gradients']['mean_temperature'][key]['value']
    assert abs(g-fd)<=2e-7+3e-5*max(abs(g),abs(fd))
    record(evidence,'central-'+key,{'samples':raw,'adjoint':g,'central':fd,'absolute_mismatch':abs(g-fd)})


def test_celsius_absolute_offset_but_bc_derivative_one(evidence,linear):
    comp,_,_,base,admission=linear;comp=deepcopy(comp)
    comp['stages']['Heat']['model']['settings']['boundary_temperature']={'value':26.85,'unit':'degC'}
    for b in comp['definition']['bindings']:
        if b['id']=='T0':b['unit']='degC'
    comp['definition_sha256']=definition_hash(comp['definition'])
    path,r=create(comp,evidence,{'k':20.,'q':10000.,'T0':26.85},adjoint=admission)
    assert r['execution_status']=='SUCCEEDED',r['diagnostics']
    assert abs(r['responses']['mean_temperature']['value']-base['responses']['mean_temperature']['value'])<1e-10
    assert abs(r['gradients']['mean_temperature']['T0']['value']-1)<1e-10
    assert r['gradients']['mean_temperature']['T0']['input_unit']=='degC'


def test_a_b_a_and_b_a_actual_picard_state_isolation(evidence):
    comp,_,_=compiled_case('mdo');original=canonical_hash(comp)
    results=[]
    for order in ([288.,301.,288.],[301.,288.]):
        factory=DefinitionFactory(comp,evidence/('order-'+uuid.uuid4().hex),run_stage)
        with factory.prepare() as prepared:
            for v in order:
                result=prepared.evaluate({'Tref':v})
                assert result['execution_status']=='SUCCEEDED',result['diagnostics']
                assert result['diagnostics']['convergence_status']=='CONVERGED'
                assert len(result['iterations'])>1 and not result.get('gradients')
                assert all(t['applied_value']==v for t in result['input_bindings'][0]['targets'])
                results.append(result)
    assert canonical_hash(comp)==original
    for a,b in ((0,2),(0,4),(1,3)):
        assert canonical_hash(results[a]['responses'])==canonical_hash(results[b]['responses'])
        assert results[a]['initial_state_sha256']==results[b]['initial_state_sha256']
        assert results[a]['evaluation_refs'][0]['relative']!=results[b]['evaluation_refs'][0]['relative']
    assert results[0]['initial_state_sha256']!=results[1]['initial_state_sha256']
    assert results[0]['responses']['max_displacement']['value']!=results[1]['responses']['max_displacement']['value']
    assert results[0]['responses']['mean_temperature']['value']!=results[1]['responses']['mean_temperature']['value']
    record(evidence,'state-isolation',[{'values':r['values'],'input_bindings':r['input_bindings'],
        'initial_state_sha256':r['initial_state_sha256'],'responses':r['responses'],'iterations':r['iterations'],
        'evaluation_refs':r['evaluation_refs']} for r in results])


def test_nonconvergence_is_not_objective_or_gradient(evidence):
    comp,_,req=compiled_case('mdo');comp['definition']['iteration']['maximum']=1
    comp['definition_sha256']=definition_hash(comp['definition'])
    factory=DefinitionFactory(comp,evidence/'nonconverged',run_stage)
    value=numerical.optimize(factory,req['inputs']['variables'],req['inputs']['objective'],
        constraints=req['inputs']['constraints'],seed=17,options={'max_generations':1,'population_size':5},
        execution={'max_evaluations':10,'on_failure':'stop'})
    assert value['best'] is None and value['termination_reason']=='STOPPED_AFTER_FAILURE'
    assert len(value['candidates'])==1
    c=value['candidates'][0]
    assert not c['feasible'] and c['objective'] is None and all(v is None for v in c['constraint_residuals'])
    assert c['responses']=={} and not c.get('gradients')
    ref=c['evaluation_refs'][0];r=evaluation.read_result(evidence/ref['relative'],verify='all')
    assert r['diagnostics']['convergence_status']=='NOT_CONVERGED'
    assert r['stage_execution_count']==2
    assert all(row['state']=='SUCCEEDED' for row in r['stages'])
    record(evidence,'nonconvergence',value)


@pytest.mark.parametrize('fault',['mask','clock','topology'])
def test_invalid_source_after_actual_solve_blocks_receiver(evidence,fault):
    comp,_,_=compiled_case('mdo');calls=[]
    from plugins.thermoelastic.reference import seal_field
    def injected(model,folder):
        calls.append(model['backend'])
        result=run_stage(model,folder/'original-physics')
        assert result['execution_status']=='SUCCEEDED'
        result=deepcopy(result);field=result['responses']['temperature']
        if fault=='mask':field['valid_mask'][0]=False
        elif fault=='clock':field['time_origin']='wrong-source-clock'
        else:field['cell_node_ids'][0]=[0,0,0]
        result['responses']['temperature']=seal_field(field)
        result['diagnostics']['negative_test_fault_injection']=fault
        result['artifacts']=[{'path':p.relative_to(folder).as_posix(),'sha256':evaluation.file_hash(p)} for p in folder.rglob('*') if p.is_file()]
        return result
    path,result=create(comp,evidence,{'Tref':293.15},callback=injected)
    assert result['execution_status']=='FAILED' and result['responses']=={}
    assert len(calls)==1 and result['stage_execution_count']==1
    assert result['stages'][-1]['dispatched'] is False
    assert next(path.rglob('original-physics/native/thermal_field.json')).is_file()
    record(evidence,'source-fault-'+fault,{'directory':str(path),'stages':result['stages'],'diagnostics':result['diagnostics']})


def test_budget_primal_retained_adjoint_not_dispatched(evidence,linear):
    comp,req,_,_,_=linear
    factory=DefinitionFactory(comp,evidence/'budget',run_stage)
    value=numerical.optimize(factory,req['inputs']['variables'],req['inputs']['objective'],
        method='slsqp_adjoint',options={'verify_gradient':False},execution={'max_evaluations':1})
    assert value['termination_reason']=='EVALUATION_BUDGET_EXHAUSTED'
    assert value['best'] is None and len(value['candidates'])==1
    row=value['candidates'][0]
    assert row['objective'] is None and row['objective_gradient'] is None and not row['feasible']
    assert value['timing']['primal_dispatches']==1 and value['timing']['actual_adjoint_dispatches']==0
    retained=evaluation.read_result(evidence/row['evaluation_refs'][0]['relative'],verify='all')
    assert retained['stages'][0]['state']=='SUCCEEDED' and not retained['derivative_attempts'][0]['dispatched']
    record(evidence,'budget',value)


@pytest.mark.parametrize('when',['after_primal','during_adjoint','after_adjoint'])
def test_cancel_exact_owned_worker_and_no_later_use(evidence,linear,monkeypatch,when):
    comp,_,_,_,admission=linear
    from caelab.adapters import scikit_fem_spatial as spatial
    token=CancellationToken();runner=spatial._run_process;watch=[];stop=threading.Event()
    def wrapped(command,output,environment,timeout,**kwargs):
        spec=load_json(output/'input.json');is_adjoint=spec.get('task')=='adjoint'
        if when=='during_adjoint' and is_adjoint:
            def monitor():
                deadline=time.monotonic()+15
                while not stop.is_set() and time.monotonic()<deadline:
                    try:
                        state=load_json(output/'execution.json')
                        if state.get('status')=='RUNNING':watch.append(state['pid']);token.request();return
                    except (OSError,ValueError):pass
                    time.sleep(.002)
            thread=threading.Thread(target=monitor);thread.start()
            try:return runner(command,output,environment,timeout,**kwargs)
            finally:stop.set();thread.join(timeout=20);assert not thread.is_alive()
        answer=runner(command,output,environment,timeout,**kwargs)
        if (when=='after_primal' and not is_adjoint) or (when=='after_adjoint' and is_adjoint):token.request()
        return answer
    monkeypatch.setattr(spatial,'_run_process',wrapped)
    with cancellation_scope(token):
        path,result=create(comp,evidence,{'k':20.,'q':10000.},adjoint=admission)
    assert result['execution_status']=='CANCELLED' and result['responses']=={} and not result.get('gradients')
    assert result['stage_execution_count']==1 and not token.cleanup_pending
    if when=='after_primal':assert result['adjoint_execution_count']==0
    elif when=='during_adjoint':
        assert watch and result['adjoint_execution_count']==1
        executions=[load_json(p) for p in path.rglob('execution.json')]
        state=next(s for s in executions if s.get('pid')==watch[0])
        assert state['status']=='CANCELLED' and not state['cleanup_pending'] and state['return_code'] is not None
    else:
        attempt=result['derivative_attempts'][0]
        assert attempt['state']=='SUCCEEDED'
        raw=evaluation.read_result(path/attempt['result_directory'],verify='all')
        assert raw['diagnostics']['adjoint']['adjoint_solve_calls']==1
    record(evidence,'cancel-'+when,{'directory':str(path),'state':result['execution_status'],'stages':result['stages'],
        'derivative_attempts':result['derivative_attempts'],'cleanup_pending':token.cleanup_pending,'monitored_pids':watch})


def test_corrupt_or_missing_adjoint_raw_bytes_never_reconstructed(evidence,linear):
    _,_,path,result,_=linear
    clone=evidence/'corrupt-copy';shutil.copytree(path,clone)
    original=next(clone.rglob('adjoint-system.npz'));b=original.read_bytes()
    original.write_bytes(b[:-1]+bytes([b[-1]^1]))
    with pytest.raises((ValueError,OSError)):evaluation.read_result(clone,verify='all')
    original.unlink()
    with pytest.raises((ValueError,OSError)):evaluation.read_result(clone,verify='all')
    assert evaluation.read_result(path,verify='all')['execution_status']=='SUCCEEDED'


def test_solver_rejection_keeps_actual_unvalidated_field(evidence,linear):
    comp,_,_,_,_=linear;comp=deepcopy(comp)
    path,r=create(comp,evidence,{'q':1e8,'k':20.})
    assert r['execution_status']=='FAILED' and r['responses']=={} and not r.get('gradients')
    assert next(path.rglob('thermal_solution.json')).is_file()
    field=load_json(next(path.rglob('thermal_solution.json')))
    assert field['status']=='UNVALIDATED' and max(field['values'])>5000.
    record(evidence,'solver-reject',{'directory':str(path),'stages':r['stages'],'diagnostics':r['diagnostics']})


def test_out_of_catalog_source_is_rejected_before_any_stage(evidence,linear):
    comp,_,_,_,_=linear
    path,r=create(comp,evidence,{'q':1e9,'k':20.})
    assert r['execution_status']=='FAILED' and r['stage_execution_count']==0 and r['responses']=={}


def test_actual_slsqp_active_constraint_and_exact_gradients(evidence,linear):
    comp,req,_,_,_=linear
    f=DefinitionFactory(comp,evidence/'active-constraint',run_stage)
    objective=req['inputs']['objective']
    constraint={'response':'mean_temperature','unit':'K','reduction':'native_integral','operator':'>=','limit':301.,'scale':1.}
    result=numerical.optimize(f,req['inputs']['variables'],objective,constraints=[constraint],
        method='slsqp_adjoint',options={'maxiter':30,'ftol':1e-9,'verify_gradient':False},
        execution={'max_evaluations':60})
    assert result['execution_status']=='SUCCEEDED' and result['termination_reason']=='CONVERGED',result
    assert result['best']['feasible'] and 301.<=result['best']['objective']<=301.00001
    assert result['callback_counts']['jacobian']>0 and result['callback_counts']['constraint_jacobian']>0
    assert result['solver_result']['njev']>0 and result['solver_result']['multipliers'][0]>0
    for c in result['candidates']:
        if c.get('objective') is not None:
            assert c['constraint_residuals'][0]==pytest.approx(301.-c['objective'],abs=1e-12)
            assert c['constraint_gradients'][0]['physical_gradient']
    record(evidence,'active-constraint',result)


def test_old_two_stage_two_candidate_budget_is_preserved(evidence):
    from caelab.evaluation_definition import compile_definition
    comp,snapshots,_=compiled_case('mdo');draft=comp['definition']
    snapshots['Heat']['draft']['settings']['conductivity']['beta']=0.
    draft['stages'][0]['source']['input_sha256']=canonical_hash(snapshots['Heat']['draft'])
    draft['bindings']=[{'id':'T0','stage':'Heat','input_id':'boundary_temperature','unit':'K'}]
    draft['transfers']=[row for row in draft['transfers'] if row['lag']==0]
    draft['iteration']={'enabled':False,'maximum':20,'checks':[]}
    comp=compile_definition(draft,snapshots)
    f=DefinitionFactory(comp,evidence/'legacy-budget',run_stage)
    result=numerical.run_doe(f,[{'id':'T0','unit':'K','lower':320.,'upper':350.,'value':330.}],
        candidates=[{'candidate_id':'Cold','values':{'T0':330.}},{'candidate_id':'Hot','values':{'T0':340.}}],
        execution={'max_evaluations':2})
    assert result['execution_status']=='SUCCEEDED' and len(result['candidates'])==2
    assert result['timing']['budget_unit']=='model_evaluation' and result['timing']['dispatched_evaluations_total']==2
    assert all(r['evaluation_refs'][0]['stage_execution_count']==2 for r in result['candidates'])
    record(evidence,'legacy-budget',result)


def test_exact_successful_prefix_reuse_and_value_drift(evidence,linear):
    from caelab.evaluation_definition import validate_draft
    comp,_,original_folder,original,_=linear;comp=deepcopy(comp)
    comp['definition']['reuse']={'source':{'document_id':'EOriginal','job_id':'JOriginal','input_revision':'IOriginal',
        'input_sha256':canonical_hash(comp['definition']),'result_sha256':canonical_hash(original)},'stages':['Heat']}
    validate_draft(comp['definition'])
    def no_solve(*a,**kw):raise AssertionError('Exact reuse attempted a solve')
    for changed in (False,True):
        values=dict(original['values'])
        if changed:values['q']+=100.
        out=evidence/('reuse-drift' if changed else 'reuse-exact')
        r=execute(comp,out,no_solve,values=values,reuse_result=original,reuse_folder=original_folder)
        assert r['stage_execution_count']==0
        assert r['execution_status']==('FAILED' if changed else 'SUCCEEDED')
        if changed:assert r['responses']=={}
        else:assert canonical_hash(r['responses'])==canonical_hash(original['responses'])
    mdo,_,_=compiled_case('mdo');mdo['definition']['reuse']=comp['definition']['reuse']
    with pytest.raises(ValueError,match='partial loop'):validate_draft(mdo['definition'])
