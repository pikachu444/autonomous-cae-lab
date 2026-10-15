"""Actual saved nonconvergence/cancellation and new-owner read, with no solver doubles."""
from copy import deepcopy
from pathlib import Path
import json
import subprocess
import sys
import time
from examples.s2_mdo_adjoint import create_definition,run_plan,wait,summarize
from examples.s1_windows_transfer import local_service,command
from caelab.evaluation_definition import document_reference
from caelab.storage import canonical_hash
from caelab.jobs import TERMINAL


def scenario(workspace,mode):
    workspace=Path(workspace).resolve()
    with local_service(workspace) as (wb,client):
        definition,request,_=create_definition(client,'mdo' if mode=='nonconverged' else 'adjoint')
        if mode=='nonconverged':
            draft=deepcopy(definition['draft']);draft['iteration']['maximum']=1
            definition=command(client,definition,'evaluation.update',{'draft':draft})['document']
            definition=command(client,definition,'document.save')['document']
            request['inputs']['settings']['definition_ref']=document_reference(definition)
            request['inputs']['execution']={'on_failure':'stop'}
            plan,job,result=run_plan(client,definition,request,120.)
            assert result['termination_reason']=='STOPPED_AFTER_FAILURE' and result['best'] is None
            assert result['candidates'][0]['diagnostics']['convergence_status']=='NOT_CONVERGED'
        else:
            request['inputs']['options']['verify_gradient']=False
            plan=client.document_open(kind='numerical',title='실제 adjoint 취소 보존',draft={'mode':'request',
                'request':request,'source':document_reference(definition),'model_source':document_reference(definition)})
            plan=command(client,plan,'document.save')['document']
            job=command(client,plan,'numerical.run')['job']['id']
            limit=time.monotonic()+90;observed=None
            while time.monotonic()<limit:
                for p in (wb.root/'results'/job).glob('evaluations/*/derivatives/*/native/execution.json'):
                    try:raw=json.loads(p.read_text())
                    except (OSError,ValueError):continue
                    if raw.get('status')=='RUNNING':observed=raw;break
                if observed is not None:break
                if client.status(job)['state'] in TERMINAL:raise AssertionError('Adjoint finished before cancellation observation')
                time.sleep(.003)
            assert observed is not None,'No actual owned adjoint process was observed'
            client.cancel(job);wait(client,job,60.)
            result=client.document_result(plan['id'],job)
            assert result['execution_status']=='CANCELLED' and result['best'] is None
            assert all(not row['feasible'] and row.get('objective') is None for row in result['candidates'])
            plan=command(client,client.document_read(plan['id']),'document.save')['document']
        candidates=[];stages=[]
        for row in result['candidates']:
            for index,_ in enumerate(row.get('evaluation_refs',[])):
                saved=client.numerical_evaluation_result(plan['id'],job,row['candidate_id'],evaluation_index=index)
                candidates.append({'candidate_id':row['candidate_id'],'evaluation_index':index,'hash':canonical_hash(saved)})
                for attempt in saved.get('stages',[])+saved.get('derivative_attempts',[]):
                    if not attempt.get('result_sha256'):continue
                    stage=client.numerical_evaluation_result(plan['id'],job,row['candidate_id'],evaluation_index=index,
                        attempt_id=attempt['attempt_id'],selection={'responses':[],'include_settings':True})
                    stages.append({'candidate_id':row['candidate_id'],'evaluation_index':index,
                        'attempt_id':attempt['attempt_id'],'hash':canonical_hash(stage)})
        receipt={'case':mode,'workspace':str(workspace),'document_id':plan['id'],'job_id':job,'summary':summarize(result),
            'definition_id':definition['id'],'definition_hash':canonical_hash(definition['draft']),
            'draft_hash':canonical_hash(plan['draft']),'result_hash':canonical_hash(result),
            'candidate_hashes':candidates,'stage_hashes':stages,'actual_saved_status':result['execution_status']}
        path=workspace/('s2-'+mode+'.json');path.write_text(json.dumps(receipt,ensure_ascii=False,indent=2))
    process=None
    try:
        process=subprocess.Popen([sys.executable,'-m','examples.s2_mdo_adjoint','--reopen',str(path)],
            stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        stdout,stderr=process.communicate(timeout=100)
        assert process.returncode==0,stderr
        print(json.dumps({'record':str(path),'saved_status':receipt['actual_saved_status'],'cold':json.loads(stdout)},ensure_ascii=False))
    finally:
        if process is not None:
            if process.poll() is None:process.kill()
            process.wait(timeout=10)
            if process.stdout:process.stdout.close()
            if process.stderr:process.stderr.close()


if __name__=='__main__':scenario(sys.argv[1],sys.argv[2])
