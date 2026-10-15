"""C03 completion gates: real owner, revision store and JobManager; algebra only.

No test here labels synthetic protocol arithmetic as FELUPE or engineering
qualification. Optional real FELUPE / native Qt checks live in separate files.
"""
from copy import deepcopy
from pathlib import Path
import shutil

import pytest

from caelab.numerical_candidate_detail import DetailIdentityError, compare_candidate_details
from caelab.numerical_candidate_evidence import (
    CAPTURE, SUCCESS, FAILURE, DetailEvidenceBlocked, candidate_detail_readiness,
    prepare_candidate_evidence, resolve_candidate_evidence, candidate_report_payload,
    compare_selected_candidate_evidence, require_adoption_evidence,
)
from caelab.storage import canonical_hash, load_json, save_json
from _numerical_candidate_detail_support import DetailHost, synthetic_inputs, synthetic, intermediate


def capture(host, view, *, purpose=SUCCESS, required_experiments=None, **kwargs):
    args = {'source':view['source'], 'candidate_id':view['candidate']['candidate_id'],
            'attempt_job_id':view['attempt_job_id'], 'purpose':purpose}
    if required_experiments is not None:
        args['required_experiments'] = required_experiments
    return host.command(view['source']['document_id'], CAPTURE, args, **kwargs)


def complete(host, doc, job, cid):
    task = host.detail(host.view(doc,job,cid))['job']['id']
    assert host.wait(task)['state'] == 'SUCCEEDED'
    return host.view(doc,job,cid,attempt_job_id=task)


def test_summary_selection_incomplete_comparison_read_only_and_zero_submissions(tmp_path):
    with DetailHost(tmp_path) as host:
        doc,job = host.create_fit(synthetic_inputs(retain=0))
        cid = intermediate(host,doc,job)
        count = len(host.manager.list())
        for _ in range(3):
            view = host.view(doc,job,cid)
            assert view['candidate']['execution_status'] == 'SUCCEEDED'
            assert all(t['retention']=='NOT_RETAINED' for t in view['trials'])
            readiness = candidate_detail_readiness(view)
            assert readiness['state']=='BLOCKED' and not readiness['success_judgment_permitted']
            comparison = compare_candidate_details(view,view,'T0')
            assert comparison['ranking']=='NOT_PERFORMED'
            assert not comparison['success_judgment_permitted']
            assert comparison['completion']=='READ_ONLY_NOT_A_SUCCESS_JUDGMENT'
        with pytest.raises(DetailEvidenceBlocked):
            capture(host,view)
        # Missing detail is not proof of a computation failure either.
        with pytest.raises(DetailEvidenceBlocked):
            capture(host,view,purpose=FAILURE)
        with pytest.raises(DetailEvidenceBlocked):
            require_adoption_evidence(host.owner,None,{}, {},cid)
        assert len(host.manager.list()) == count
        assert not host.owner.read(doc).get('candidate_evidence')


def test_explicit_detail_capture_gates_and_separate_original_holdout(tmp_path):
    with DetailHost(tmp_path) as host:
        doc,job = host.create_fit(synthetic_inputs(retain=0))
        cid = intermediate(host,doc,job)
        original = host.owner.result(doc,job)
        original_hash = canonical_hash(original)
        run = next(r for r in host.owner.read(doc)['runs'] if r['job_id']==job)
        view = complete(host,doc,job,cid)
        assert len(host.manager.list())==2
        pending = prepare_candidate_evidence(host.owner,view['source'],cid,attempt_job_id=view['attempt_job_id'])
        assert pending['readiness']['ready_to_preserve']
        assert not pending['readiness']['success_judgment_permitted']
        answer = capture(host,view)
        ref = answer['reference']
        resolved = resolve_candidate_evidence(host.owner,ref,consumer='adoption',
            source=view['source'],candidate_id=cid,attempt_job_id=view['attempt_job_id'])
        snapshot = resolved['snapshot']
        assert resolved['readiness']['success_judgment_permitted']
        assert resolved['readiness']['holdout_acceptance']=='NOT_ASSESSED'
        assert resolved['readiness']['engineering_release']=='NOT_RELEASED'
        assert canonical_hash(snapshot)==ref['snapshot_sha256']
        assert snapshot['original_candidate']==view['candidate']
        assert snapshot['original_fit_holdout']==[c for c in original['curves'] if c['role']=='holdout']
        assert snapshot['selected_holdout_refs'][0]['job_id']==view['attempt_job_id']
        assert snapshot['selected_holdout_refs'][0]['job_id']!=job
        assert require_adoption_evidence(host.owner,ref,run,original,cid)==resolved
        payload=candidate_report_payload(host.owner,ref)
        assert payload['report_intent']=='success_report'
        assert payload['candidate_evidence']['readiness']['success_judgment_permitted']
        comp=compare_selected_candidate_evidence(host.owner,ref,ref,'T2')
        assert comp['completion']=='EVIDENCE_VERIFIED_COMPARISON'
        assert comp['success_judgment_permitted'] and comp['ranking']=='NOT_PERFORMED'
        # Retention limit is not silently extended in the original search result.
        assert canonical_hash(host.owner.result(doc,job))==original_hash
        assert all(t['retention']=='NOT_RETAINED' for t in host.view(doc,job,cid)['trials'])
        assert len(host.manager.list())==2


@pytest.mark.parametrize('state', ['FAILED','CANCELLED','PARTIAL_FAILURE'])
def test_failed_or_cancelled_detail_cannot_complete_original_success(tmp_path,state):
    with DetailHost(tmp_path) as host:
        doc,job=host.create_fit(synthetic_inputs(retain=0));cid=intermediate(host,doc,job)
        original=deepcopy(host.owner.result(doc,job))
        run=next(r for r in host.owner.read(doc)['runs'] if r['job_id']==job)
        digest=canonical_hash(original);input_digest=canonical_hash(run['arguments'])
        def stopped(values,settings):
            raw=synthetic(values,settings)
            if state=='PARTIAL_FAILURE' and settings['factor']==1:
                return raw
            raw['execution_status']='CANCELLED' if state=='CANCELLED' else 'FAILED'
            raw['diagnostics']['failure_reason']='Deliberately stopped selected protocol; partial raw remains'
            return raw
        host.evaluator=stopped
        task=host.detail(host.view(doc,job,cid))['job']['id']
        assert host.wait(task)['state']==state
        view=host.view(doc,job,cid,attempt_job_id=task)
        with pytest.raises(DetailEvidenceBlocked): capture(host,view)
        # Even a completed prefix is not a completed selected attempt.
        with pytest.raises(DetailEvidenceBlocked): capture(host,view,required_experiments=['T0'])
        diagnostic=capture(host,view,purpose=FAILURE)['reference']
        report=candidate_report_payload(host.owner,diagnostic)
        evidence=report['candidate_evidence']
        assert report['report_intent']=='failure_report'
        assert evidence['readiness']['failure_diagnostic_permitted']
        assert not evidence['readiness']['success_judgment_permitted']
        assert evidence['snapshot']['selected_attempt']['job_id']==task
        assert evidence['snapshot']['selected_attempt']['state']==state
        assert evidence['snapshot']['original_candidate']['execution_status']=='SUCCEEDED'
        assert any(t.get('raw_evaluation',{}).get('diagnostics',{}).get('failure_reason')
                   for t in evidence['snapshot']['trials'] if t.get('raw_evaluation'))
        for consumer in ['adoption','comparison','success_report']:
            with pytest.raises(DetailEvidenceBlocked):
                resolve_candidate_evidence(host.owner,diagnostic,consumer=consumer)
        assert host.owner.result(doc,job)==original
        assert canonical_hash(host.owner.result(doc,job))==digest
        current=next(r for r in host.owner.read(doc)['runs'] if r['job_id']==job)
        assert current['input_sha256']==run['input_sha256'] and canonical_hash(current['arguments'])==input_digest
        assert host.view(doc,job,cid)['candidate']['execution_status']=='SUCCEEDED'
        assert len(host.manager.list())==2


def test_original_failed_summary_diagnostic_allowed_without_success_values(tmp_path):
    with DetailHost(tmp_path) as host:
        doc,job=host.create_fit(synthetic_inputs(retain=0));cid=intermediate(host,doc,job,'FAILED')
        view=host.view(doc,job,cid)
        assert view['candidate']['failure_reason']
        ref=capture(host,view,purpose=FAILURE)['reference']
        evidence=resolve_candidate_evidence(host.owner,ref,consumer='failure_report')
        assert evidence['snapshot']['original_candidate']['execution_status']=='FAILED'
        assert evidence['snapshot']['original_candidate']['objective'] is None
        assert evidence['snapshot']['selected_attempt_job_id'] is None
        assert all(t['raw_sha256'] is None for t in evidence['snapshot']['trial_refs'])
        assert all(t['job_id']==job for t in evidence['snapshot']['trial_refs'])
        assert not evidence['readiness']['success_judgment_permitted']
        with pytest.raises(DetailEvidenceBlocked): capture(host,view)
        assert len(host.manager.list())==1


def test_old_cancelled_attempt_not_replaced_by_successful_retry(tmp_path):
    with DetailHost(tmp_path) as host:
        doc,job=host.create_fit(synthetic_inputs(retain=0));cid=intermediate(host,doc,job)
        def cancel(v,s):
            raw=synthetic(v,s);raw['execution_status']='CANCELLED';return raw
        host.evaluator=cancel
        old=host.detail(host.view(doc,job,cid))['job']['id'];host.wait(old)
        old_view=host.view(doc,job,cid,attempt_job_id=old)
        old_ref=capture(host,old_view,purpose=FAILURE)['reference']
        old_snapshot=resolve_candidate_evidence(host.owner,old_ref)['snapshot']
        host.evaluator=synthetic
        new=host.detail(old_view)['job']['id'];assert host.wait(new)['state']=='SUCCEEDED'
        new_ref=capture(host,host.view(doc,job,cid,attempt_job_id=new))['reference']
        new_snapshot=resolve_candidate_evidence(host.owner,new_ref,consumer='adoption')['snapshot']
        assert [r['record']['job_id'] for r in new_snapshot['attempt_chain']]==[old,new]
        assert all(t['job_id']==new for t in new_snapshot['trial_refs'])
        assert resolve_candidate_evidence(host.owner,old_ref)['snapshot']==old_snapshot
        with pytest.raises(DetailEvidenceBlocked): capture(host,host.view(doc,job,cid,attempt_job_id=old))
        with pytest.raises(DetailEvidenceBlocked): resolve_candidate_evidence(host.owner,old_ref,consumer='success_report')
        with pytest.raises(DetailIdentityError): resolve_candidate_evidence(host.owner,new_ref,attempt_job_id=old)
        with pytest.raises(DetailIdentityError): resolve_candidate_evidence(host.owner,old_ref,attempt_job_id=new)


def test_scope_is_explicit_subset_never_whole_candidate_adoption(tmp_path):
    with DetailHost(tmp_path) as host:
        doc,job=host.create_fit();cid=intermediate(host,doc,job)
        original_view=host.view(doc,job,cid)
        assert original_view['missing_experiments']==['T2']
        subset=capture(host,original_view,required_experiments=['T0'])['reference']
        assert resolve_candidate_evidence(host.owner,subset,consumer='success_report')['snapshot']['scope'][0]['experiment_id']=='T0'
        with pytest.raises(DetailEvidenceBlocked,match='every frozen'):
            resolve_candidate_evidence(host.owner,subset,consumer='adoption')
        comparison=compare_selected_candidate_evidence(host.owner,subset,subset,'T0')
        assert comparison['success_judgment_permitted']
        with pytest.raises(DetailEvidenceBlocked,match='outside'):
            compare_selected_candidate_evidence(host.owner,subset,subset,'T2')
        assert len(host.manager.list())==1


def test_revision_survives_move_new_process_owner_and_mutable_plan_edit(tmp_path):
    old,new=tmp_path/'old',tmp_path/'한글 폴더 이동'
    with DetailHost(old) as host:
        doc,job=host.create_fit(synthetic_inputs(retain=0));cid=intermediate(host,doc,job)
        view=complete(host,doc,job,cid)
        ref=capture(host,view)['reference']
        before=resolve_candidate_evidence(host.owner,ref,consumer='adoption')
        document=host.owner.read(doc)
        edited=deepcopy(document['draft']);edited['request']['purpose']='Current draft must never alter historic evidence'
        host.command(doc,'numerical.update',{'draft':edited})
        host.command(doc,'document.save',{})
        assert resolve_candidate_evidence(host.owner,ref,consumer='adoption')==before
    shutil.move(old,new)
    shutil.rmtree(new/'results',ignore_errors=True)
    (new/'documents'/doc/'draft.json').unlink(missing_ok=True)
    (new/'documents'/doc/'working.json').unlink(missing_ok=True)
    with DetailHost(new,cold=True) as cold:
        count=len(cold.manager.list())
        after=resolve_candidate_evidence(cold.owner,ref,consumer='adoption')
        assert after==before
        assert after['snapshot']['selected_holdout_refs']==before['snapshot']['selected_holdout_refs']
        assert cold.dispatched==[] and len(cold.manager.list())==count


def test_reference_substitutions_and_same_candidate_id_other_job_are_rejected(tmp_path):
    with DetailHost(tmp_path) as host:
        doc,job=host.create_fit(synthetic_inputs(retain=0));cid=intermediate(host,doc,job)
        ref=capture(host,complete(host,doc,job,cid))['reference']
        other_doc,other_job=host.create_fit(synthetic_inputs(retain=0))
        assert any(c['candidate_id']==cid for c in host.owner.result(other_doc,other_job)['candidates'])
        substitutions=[('attempt_job_id',job),('candidate_id','AnotherCandidate'),('candidate_sha256','a'*64),
                       ('scope_sha256','b'*64),('attempt_chain_sha256','c'*64),('purpose',FAILURE),
                       ('saved_revision','Rmissing')]
        for key,value in substitutions:
            changed=deepcopy(ref);changed[key]=value
            with pytest.raises((ValueError,FileNotFoundError)):
                resolve_candidate_evidence(host.owner,changed,consumer='adoption')
        changed=deepcopy(ref);changed['source']['job_id']=other_job
        with pytest.raises(DetailIdentityError): resolve_candidate_evidence(host.owner,changed)
        changed=deepcopy(ref);changed['source']['result_sha256']='e'*64
        with pytest.raises(DetailIdentityError): resolve_candidate_evidence(host.owner,changed)
        with pytest.raises(DetailIdentityError):
            resolve_candidate_evidence(host.owner,ref,source=host.view(other_doc,other_job,cid)['source'])
        other_run=next(r for r in host.owner.read(other_doc)['runs'] if r['job_id']==other_job)
        with pytest.raises(DetailIdentityError):
            require_adoption_evidence(host.owner,ref,other_run,host.owner.result(other_doc,other_job),cid)


def test_raw_unit_curve_tampering_never_promoted_from_cached_ready_flag(tmp_path):
    with DetailHost(tmp_path) as host:
        doc,job=host.create_fit(synthetic_inputs(retain=0));cid=intermediate(host,doc,job)
        view=complete(host,doc,job,cid)
        changed=deepcopy(view);changed['trials'][0]['raw_evaluation']['responses']['stress']['unit']='Pa'
        with pytest.raises(DetailIdentityError,match='raw response'):
            candidate_detail_readiness(changed)
        changed=deepcopy(view);changed['trials'][0]['curve']['prediction'][0]+=1.
        with pytest.raises(DetailIdentityError): candidate_detail_readiness(changed)
        ref=capture(host,view)['reference']
        path=host.owner._folder(doc)/'revisions'/ref['saved_revision']/'candidate_evidence'/(ref['evidence_id']+'.json')
        raw=load_json(path);raw['readiness']['engineering_release']='APPROVED';save_json(path,raw)
        with pytest.raises(ValueError,match='hash|integrity|changed|checksum'):
            resolve_candidate_evidence(host.owner,ref,consumer='adoption')


def test_capture_save_failure_has_no_completion_and_explicit_same_receipt_retry(tmp_path,monkeypatch):
    with DetailHost(tmp_path) as host:
        doc,job=host.create_fit(synthetic_inputs(retain=0));cid=intermediate(host,doc,job)
        view=complete(host,doc,job,cid)
        host.command(doc,'document.save',{})
        previous=host.owner.read(doc)['saved_revision']
        args={'source':view['source'],'candidate_id':cid,'attempt_job_id':view['attempt_job_id'],'purpose':SUCCESS}
        document=host.owner.read(doc)
        identity=dict(session_id=document['session_id'],expected_generation=document['generation'],command_id='CsaveRetry')
        original_save=host.owner._save
        monkeypatch.setattr(host.owner,'_save',lambda value:(_ for _ in ()).throw(OSError('injected full disk')))
        with pytest.raises(OSError): host.owner.command(doc,CAPTURE,args,**identity)
        assert host.owner.read(doc)['saved_revision']==previous
        receipt=load_json(host.owner._folder(doc)/'commands'/'CsaveRetry.json')
        assert receipt['state']=='PRESERVING' and 'response' not in receipt
        with pytest.raises(DetailEvidenceBlocked): require_adoption_evidence(host.owner,None,{}, {},cid)
        monkeypatch.setattr(host.owner,'_save',original_save)
        answer=host.owner.command(doc,CAPTURE,args,**identity)
        assert resolve_candidate_evidence(host.owner,answer['reference'],consumer='adoption')['readiness']['success_judgment_permitted']
        repeated=host.owner.command(doc,CAPTURE,args,**identity)
        assert repeated==answer
        assert len(host.manager.list())==2
        bad=deepcopy(args);bad['purpose']=FAILURE
        with pytest.raises(ValueError,match='conflicts'):
            host.owner.command(doc,CAPTURE,bad,**identity)


def test_queued_cancelled_attempt_has_exact_receipt_but_no_fabricated_result(tmp_path):
    import threading
    with DetailHost(tmp_path) as host:
        doc,job=host.create_fit(synthetic_inputs(retain=0));cid=intermediate(host,doc,job)
        blocked,release=threading.Event(),threading.Event()
        execute=host.manager._execute
        def hold(operation,arguments,identifier):
            if operation=='test_block':
                blocked.set();assert release.wait(10)
                return {'execution_status':'SUCCEEDED','kind':'test_only','responses':{}}
            return execute(operation,arguments,identifier)
        host.manager._execute=hold
        blocker=host.manager.submit('test_block',{})['id']
        assert blocked.wait(5)
        try:
            task=host.detail(host.view(doc,job,cid))['job']['id']
            host.manager.cancel(task)
            assert host.wait(task)['state']=='CANCELLED'
            view=host.view(doc,job,cid,attempt_job_id=task)
            with pytest.raises(DetailEvidenceBlocked): capture(host,view)
            ref=capture(host,view,purpose=FAILURE)['reference']
            snapshot=resolve_candidate_evidence(host.owner,ref,consumer='failure_report')['snapshot']
            assert snapshot['selected_attempt']['result_sha256'] is None
            assert all(t['raw_evaluation'] is None for t in snapshot['trials'])
            assert all(r['result_sha256'] is None for r in snapshot['trial_refs'])
            assert snapshot['selected_attempt']['state']=='CANCELLED'
        finally:
            release.set();host.wait(blocker)


def test_capsule_preserves_mixed_json_numeric_types_and_large_source_metadata(tmp_path):
    from caelab.evaluation import save_evaluation, read_result
    from caelab.numerical_candidate_detail import SCHEMA, INPUT_SCHEMA
    capsule={'schema':INPUT_SCHEMA,'identity':[[1,0.,9007199254740993],[True,1,1.]],
             'nested':{'extensions':{'grid':[0,1.,2]}}}
    trial={'schema':SCHEMA,'raw_evaluation':{'diagnostics':{'protocol':capsule['identity']}}}
    original={'kind':'fit','execution_status':'SUCCEEDED','fit_input_snapshot':capsule,
              'candidates':[{'candidate_id':'C1','candidate_detail':trial}]}
    save_evaluation(original,tmp_path/'out')
    result=read_result(tmp_path/'out',verify='all')
    assert canonical_hash(result['fit_input_snapshot'])==canonical_hash(capsule)
    assert canonical_hash(result['candidates'][0]['candidate_detail'])==canonical_hash(trial)


def test_cold_separate_python_process_resolves_exact_saved_ref_without_manager(tmp_path):
    import json
    import os
    import subprocess
    import sys
    with DetailHost(tmp_path/'old') as host:
        doc,job=host.create_fit(synthetic_inputs(retain=0));cid=intermediate(host,doc,job)
        ref=capture(host,complete(host,doc,job,cid))['reference']
        expected=resolve_candidate_evidence(host.owner,ref,consumer='success_report')
    shutil.move(tmp_path/'old',tmp_path/'다른 프로세스 공간')
    root=tmp_path/'다른 프로세스 공간'
    shutil.rmtree(root/'results',ignore_errors=True)
    shutil.rmtree(root/'jobs',ignore_errors=True)
    code='''import json,sys
from types import SimpleNamespace
from caelab.numerical_document import NumericalDocuments
from caelab.numerical_candidate_evidence import resolve_candidate_evidence
from caelab.storage import canonical_hash
def forbidden(*args,**kwargs): raise AssertionError("No submission/current source allowed")
owner=NumericalDocuments(sys.argv[1],"SnewProcess",forbidden,SimpleNamespace(),
    resolve_document=forbidden,resolve_result=forbidden)
reference=json.load(sys.stdin)
answer=resolve_candidate_evidence(owner,reference,consumer="success_report")
print(json.dumps({"reference":answer["reference"],"sha256":canonical_hash(answer)}))
'''
    env=dict(os.environ);env['PYTHONPATH']=str(Path(__file__).resolve().parents[1])
    result=subprocess.run([sys.executable,'-c',code,str(root)],input=json.dumps(ref),text=True,
        capture_output=True,timeout=20,env=env,check=True)
    received=json.loads(result.stdout)
    assert received['reference']==ref and received['sha256']==canonical_hash(expected)
