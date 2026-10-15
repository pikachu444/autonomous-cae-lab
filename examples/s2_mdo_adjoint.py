"""S2 actual FE through the existing saved owners/HTTP/JobManager, with cold read.

python -m examples.s2_mdo_adjoint --workspace "S2 결과" --case adjoint
python -m examples.s2_mdo_adjoint --workspace "S2 반복" --case mdo
No fixture evaluator, paid provider, WSL or CAD is used. Snapshots are steady.
"""
from copy import deepcopy
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time

from examples.s1_windows_transfer import local_service, command
from caelab import scikit_fem_models as domain
from caelab import p1_temperature_transfer as transfer
from caelab.evaluation_definition import default_draft, document_reference
from caelab.numerical_document import request_draft
from caelab.storage import canonical_hash
from caelab.jobs import TERMINAL


def declarations(case):
    heat = domain.default_settings(domain.THERMAL)
    heat['mesh']['cells'] = [4,4]
    heat['time'] = {'value':0.,'unit':'s','origin':'public_s2_steady_reference'}
    heat['conductivity']['value'] = 20.
    heat['heat_source']['value'] = 10000.
    heat['boundary_temperature']['value'] = 300.
    definition = default_draft()
    definition['responses'] = [{'id':'mean_temperature','stage':'Heat','response':'mean_temperature','unit':'K'}]
    models = [('Heat','정상상태 열전도',domain.THERMAL,heat)]
    if case == 'adjoint':
        definition['bindings'] = [{'id':key,'stage':'Heat','input_id':name,'unit':unit} for key,name,unit in
            [('k','conductivity','W/(m*K)'),('q','heat_source','W/m^3'),('T0','boundary_temperature','K')]]
        variables = [{'id':'k','unit':'W/(m*K)','lower':10.,'upper':40.,'value':20.,'transform':'log'},
                     {'id':'q','unit':'W/m^3','lower':5000.,'upper':20000.,'value':10000.,'transform':'linear'}]
        method='slsqp_adjoint'
        options={'maxiter':30,'ftol':1e-9,'verify_gradient':True,'retain_responses':'summary'}
        objective={'response':'mean_temperature','unit':'K','reduction':'native_integral','direction':'minimize','scale':10.}
        constraints=[{'response':'mean_temperature','unit':'K','reduction':'native_integral','operator':'<=','limit':302.,'scale':10.}]
        budget=80
    elif case == 'mdo':
        heat['conductivity'].update(value=40.,beta=.003)
        heat['heat_source']['value']=100000.
        heat['boundary_temperature']['value']=330.
        structure=domain.default_settings(domain.STRUCTURAL)
        structure['mesh']['cells']=[5,3] # 24 nodes vs thermal 25; topology is genuinely different.
        structure['time']=deepcopy(heat['time'])
        structure['validation']['free_expansion_max_error']=None # Not a uniform-temperature benchmark.
        models.append(('Structure','다른 메시의 열변형',domain.STRUCTURAL,structure))
        definition['bindings']=[{'id':'Tref','unit':'K','value':293.15,'bounds':[285.,305.],
            'targets':[{'stage':'Heat','input_id':'conductivity_reference_temperature'},
                       {'stage':'Structure','input_id':'reference_temperature'}]}]
        definition['transfers']=[
            {'id':'Picard','from_stage':'Heat','output':'temperature','to_stage':'Heat',
             'input':'linearization_temperature','mapping':'exact_same_mesh','lag':1},
            {'id':'TtoU','from_stage':'Heat','output':'temperature','to_stage':'Structure','input':'temperature',
             'mapping':'p1_temperature','lag':0,'options':transfer.default_options('Heat',receiver_time=structure['time'])}]
        definition['iteration']={'enabled':True,'maximum':12,'checks':[
            {'stage':'Heat','response':'temperature','unit':'K','absolute':1e-6,'relative':1e-8,'scale':300.}]}
        definition['responses'].append({'id':'max_displacement','stage':'Structure','response':'max_displacement','unit':'m'})
        variables=[{'id':'Tref','unit':'K','lower':285.,'upper':305.,'value':293.15,'transform':'linear'}]
        method='differential_evolution'; options={'max_generations':1,'population_size':5,'retain_responses':'summary'}
        objective={'response':'max_displacement','unit':'m','reduction':'nodal_max','direction':'minimize','scale':.001}
        constraints=[{'response':'mean_temperature','unit':'K','reduction':'native_integral','operator':'<=','limit':345.,'scale':10.}]
        budget=200
    else:
        raise ValueError('Choose mdo or adjoint')
    request={'purpose':'공유 기준온도 반복 열구조 설계' if case=='mdo' else '실제 이산 adjoint를 소비하는 열전도 설계',
             'operation':'optimize','inputs':{'backend':'evaluation.definition','settings':{},'variables':variables,
             'method':method,'objective':objective,'constraints':constraints,'seed':17,'options':options},
             'budget':{'evaluations':budget}}
    return models,definition,request


def create_definition(client,case):
    models,draft,request=declarations(case)
    for identifier,title,backend,settings in models:
        doc=client.document_open(kind='simulation',title=title,draft={'backend':backend,'settings':settings})
        if doc['diagnostics']:raise ValueError(doc['diagnostics'])
        saved=command(client,doc,'document.save')['document']
        draft['stages'].append({'id':identifier,'name':title,'source':document_reference(saved)})
    doc=client.document_open(kind='evaluation',title='공유 변수 반복 열구조' if case=='mdo' else '선형 열전도 미분',draft=draft)
    check=client.evaluation_inspect(doc['id'])
    if check['diagnostics']:raise ValueError(check['diagnostics'])
    doc=command(client,doc,'document.save')['document']
    ref=document_reference(doc)
    request['inputs']['settings']={'definition_ref':ref}
    return doc,request,check


def wait(client,job,seconds):
    deadline=time.monotonic()+seconds
    while client.status(job)['state'] not in TERMINAL:
        if time.monotonic()>=deadline:
            client.cancel(job);raise TimeoutError('Explicit public deadline exceeded; owned job cancellation requested')
        time.sleep(.05)


def run_plan(client,definition,request,deadline_seconds):
    draft=request_draft(request,source=document_reference(definition))
    draft['model_source']=document_reference(definition)
    plan=client.document_open(kind='numerical',title=request['purpose'],draft=draft)
    if plan['diagnostics']:raise ValueError(plan['diagnostics'])
    plan=command(client,plan,'document.save')['document']
    receipt=command(client,plan,'numerical.run'); job=receipt['job']['id']
    try:
        wait(client,job,deadline_seconds)
    except TimeoutError:
        # Preserve the actual cancelled/late result and save it for cold reading.
        # Waiting for cleanup is not another evaluation or a success claim.
        wait(client,job,30.)
    result=client.document_result(plan['id'],job)
    plan=command(client,client.document_read(plan['id']),'document.save')['document']
    return plan,job,result


def summarize(result):
    return {'execution_status':result.get('execution_status'),'termination_reason':result.get('termination_reason'),
        'candidate_count':len(result.get('candidates',[])), 'best_values':(result.get('best') or {}).get('values'),
        'best_objective':(result.get('best') or {}).get('objective'),
        'gradient_verification':(result.get('gradient_verification') or {}).get('status'),
        'solver_dispatch':result.get('solver_dispatch'), 'timing':result.get('timing'),
        'failure_reason':result.get('failure_reason'), 'diagnostics':result.get('diagnostics')}


def calculate(workspace,case,deadline_seconds):
    workspace=Path(workspace).resolve()
    if workspace.exists() and any(workspace.iterdir()):
        raise ValueError('Use a fresh example workspace; old inputs/results are never overwritten')
    with local_service(workspace) as (wb,client):
        before=len(wb.manager.list())
        definition,request,inspection=create_definition(client,case)
        described=client.describe_inputs(request['inputs'])
        if len(wb.manager.list())!=before:raise AssertionError('Edit/Check/save submitted a calculation')
        plan,job,result=run_plan(client,definition,request,deadline_seconds)
        # Only existing exact nested readers; no subsequent solve is allowed here.
        selected=[]
        for row in result.get('candidates',[]):
            if not row.get('evaluation_refs'):continue
            evaluation=client.numerical_evaluation_result(plan['id'],job,row['candidate_id'],evaluation_index=0)
            attempts=[]
            for attempt in evaluation.get('stages',[])+evaluation.get('derivative_attempts',[]):
                if not attempt.get('result_sha256'):continue
                stage=client.numerical_evaluation_result(plan['id'],job,row['candidate_id'],evaluation_index=0,attempt_id=attempt['attempt_id'])
                attempts.append({'attempt_id':attempt['attempt_id'],'hash':canonical_hash(stage)})
                if stage.get('execution_status')=='SUCCEEDED' and stage.get('attempt_kind')!='adjoint':
                    expected={'temperature','displacement','stress'} if stage.get('backend')==domain.STRUCTURAL else {'temperature'}
                    if {p['response'] for p in stage.get('post_inputs',[])}!=expected:
                        raise AssertionError('Actual stage fields were not registered for Post')
                for post in stage.get('post_inputs',[]):client.native_input(post['id'])
            selected.append({'candidate_id':row['candidate_id'],'hash':canonical_hash(evaluation),'attempts':attempts})
        record={'schema':'public-s2-execution-v1','case':case,'workspace':str(workspace),
            'definition_id':definition['id'],'definition_hash':canonical_hash(definition['draft']),
            'document_id':plan['id'],'job_id':job,'saved_revision':plan['saved_revision'],
            'draft_hash':canonical_hash(plan['draft']),'result_hash':canonical_hash(result),
            'candidate_reads':selected,'check_solver_calls':0,'summary':summarize(result),
            'platform':sys.platform,'python':sys.version,'paid_calls':0,'Windows':'NOT_RUN' if sys.platform!='win32' else 'EXECUTED',
            'Qt':'NOT_RUN','ParaView_native':'NOT_RUN','qualification':'UNKNOWN'}
        dest=workspace/('s2-'+case+'-'+job+'.json')
        dest.write_text(json.dumps(record,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    return dest,record


def reopen(path):
    import builtins
    from caelab.workbench import Workbench
    from caelab.adapters.scikit_fem_spatial import _Spatial
    from caelab import evaluation
    expected=json.loads(Path(path).read_text(encoding='utf-8'))
    calls=[]
    def forbidden(*args,**kwargs):
        calls.append('FORBIDDEN');raise AssertionError('Cold read attempted a calculation/mapping')
    _Spatial.run=forbidden;_Spatial.run_adjoint=forbidden;transfer.map_temperature=forbidden
    evaluation.run=forbidden;evaluation.evaluate=forbidden
    original=builtins.__import__
    def guard(name,*args,**kwargs):
        if name.split('.')[0] in {'skfem','scipy','dolfinx','petsc4py'}:
            raise AssertionError('Cold read imported a solver dependency: '+name)
        return original(name,*args,**kwargs)
    builtins.__import__=guard
    wb=Workbench(Path(expected['workspace']))
    try:
        doc=wb.document_open(kind='numerical',document_id=expected['document_id'])
        definition=wb.document_open(kind='evaluation',document_id=expected['definition_id'])
        assert canonical_hash(doc['draft'])==expected['draft_hash']
        assert canonical_hash(definition['draft'])==expected['definition_hash']
        result=wb.document_result(doc['id'],expected['job_id'])
        assert canonical_hash(result)==expected['result_hash']
        reads=expected.get('candidate_reads')
        if reads is None and 'candidate_hashes' in expected and 'stage_hashes' in expected:
            # Early failure probe used separate catalogs. Select exactly the
            # originally hashed range; this does not repair/recompute a result.
            reads=[{**item,'attempts':[{**a,'selection':{'responses':[],'include_settings':True}}
                for a in expected['stage_hashes'] if a['candidate_id']==item['candidate_id'] and a['evaluation_index']==item['evaluation_index']]}
                for item in expected['candidate_hashes']]
        if not isinstance(reads,list):raise ValueError('Exact recorded candidate catalog is missing')
        for item in reads:
            index=item.get('evaluation_index',0)
            value=wb.numerical_evaluation_result(doc['id'],expected['job_id'],item['candidate_id'],evaluation_index=index)
            assert canonical_hash(value)==item['hash']
            for attempt in item['attempts']:
                raw=wb.numerical_evaluation_result(doc['id'],expected['job_id'],item['candidate_id'],evaluation_index=index,attempt_id=attempt['attempt_id'],selection=attempt.get('selection'))
                assert canonical_hash(raw)==attempt['hash']
                for post in raw.get('post_inputs',[]):wb.native_input(post['id'])
        assert not calls
        return {'cold_read':'PASS','new_process':True,'solve_calls':0,'mapping_calls':0,'adjoint_calls':0,
                'original_execution_status':result['execution_status']}
    finally:
        builtins.__import__=original
        if not wb.shutdown()['joined']:raise RuntimeError('Cold owner did not terminate')


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace',type=Path);parser.add_argument('--case',choices=['mdo','adjoint'],default='adjoint')
    parser.add_argument('--deadline-seconds',type=float,default=600.)
    parser.add_argument('--reopen',type=Path);parser.add_argument('--no-cold',action='store_true')
    parser.add_argument('--cold-deadline-seconds',type=float,default=400.)
    args=parser.parse_args(argv)
    if args.reopen:print(json.dumps(reopen(args.reopen),ensure_ascii=False));return 0
    if args.workspace is None or args.deadline_seconds<=0 or args.cold_deadline_seconds<=0:parser.error('Use --workspace and a positive deadline')
    path,record=calculate(args.workspace,args.case,args.deadline_seconds)
    process=None;cold=None
    try:
        if not args.no_cold:
            process=subprocess.Popen([sys.executable,'-m','examples.s2_mdo_adjoint','--reopen',str(path)],
                stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
            stdout,stderr=process.communicate(timeout=args.cold_deadline_seconds)
            if process.returncode:raise RuntimeError('Cold read failed; original result is retained: '+str(path)+'\n'+stderr)
            cold=json.loads(stdout)
        print(json.dumps({'record':str(path),**record['summary'],'cold':cold},ensure_ascii=False,indent=2))
        return 0 if record['summary']['execution_status']=='SUCCEEDED' else 2
    finally:
        if process is not None:
            if process.poll() is None:process.kill()
            process.wait(timeout=5)
            if process.stdout:process.stdout.close()
            if process.stderr:process.stderr.close()


if __name__=='__main__':
    import signal
    def interrupted(signum, frame):
        raise KeyboardInterrupt('Owned public test interrupted')
    signal.signal(signal.SIGTERM, interrupted)
    raise SystemExit(main())
