"""FN07/FN21 retained history, explicit attempts and owner/store integration."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
import threading
import uuid

import numpy as np
import pytest

from caelab import numerical
from caelab.numerical_candidate_detail import (
    COMMAND, OPERATION, INCLUSION_SCHEMA, DetailIdentityError,
    consume_frozen_fit_inclusion, experiment_snapshot, plain,
    prepare_detail_arguments, validate_detail_arguments, table_rows,
    compare_candidate_details, FitDetailRetention, trial_detail,
    client_read_candidate_detail,
)
from caelab.storage import canonical_hash, load_json, save_json
from _numerical_candidate_detail_support import DetailHost, synthetic, synthetic_inputs, intermediate


def hashes(root):
    return {p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
            for p in Path(root).rglob('*') if p.is_file()}


def test_retained_read_explicit_holdout_save_cold_owner(tmp_path):
    calls=[]
    def model(v,s):
        calls.append((deepcopy(v),deepcopy(s)))
        return synthetic(v,s)
    with DetailHost(tmp_path, model) as host:
        doc,job=host.create_fit()
        candidate=intermediate(host,doc,job)
        failed=intermediate(host,doc,job,'FAILED')
        original=host.owner.result(doc,job)
        original_hash=canonical_hash(original)
        file_hashes=hashes(tmp_path/'results'/job)
        run=deepcopy(host.owner.read(doc)['runs'][0])
        before_calls=len(calls)
        for _ in range(3):
            view=host.view(doc,job,candidate)
            failed_view=host.view(doc,job,failed)
            assert len(host.manager.list())==1
        assert len(calls)==before_calls
        assert view['missing_experiments']==['T2']
        assert [t['execution_status'] for t in failed_view['trials'][:2]]==['FAILED','FAILED']
        assert all(t['raw_evaluation']['diagnostics']['failure_reason'] for t in failed_view['trials'][:2])
        assert failed_view['candidate']['objective'] is None
        rows=table_rows(view,'T0')
        assert rows[1]['prediction'] is None and rows[1]['observation'] is not None
        assert rows[2]['included'] is True and rows[2]['observation_mask'] is False
        assert rows[2]['deformation_gradient']==run['arguments']['experiments'][0]['settings']['deformation_gradient'][2]
        assert rows[2]['weighted_residual']==pytest.approx(
            (rows[2]['prediction']-rows[2]['observation'])*np.sqrt(2/3)/3)
        # Current Plan and simulated current Material/observations are not consulted.
        draft=deepcopy(host.owner.read(doc)['draft'])
        draft['request']['inputs']['variables'][0]['value']=2.9
        draft['request']['inputs']['experiments'][0]['observations']['value'][0]=999.
        host.command(doc,'numerical.update',{'draft':draft})
        assert host.view(doc,job,candidate)['source']==view['source']
        answer=host.detail(view,command_id='DetailOnce')
        detail_job=answer['job']['id']
        assert host.wait(detail_job)['state']=='SUCCEEDED'
        assert len(calls)==before_calls+1 # holdout only; fit outputs reused
        fresh=host.view(doc,job,candidate,attempt_job_id=detail_job)
        assert all(t['retention']=='RETAINED' for t in fresh['trials'])
        assert not fresh['can_detail_eval']
        assert not host.view(doc,job,candidate)['can_detail_eval']
        with pytest.raises(ValueError):host.detail(view)
        with pytest.raises(ValueError):host.detail(fresh)
        assert canonical_hash(host.owner.result(doc,job))==original_hash
        assert hashes(tmp_path/'results'/job)==file_hashes
        assert host.owner.read(doc)['runs'][0]['draft']==run['draft']
        assert host.owner.read(doc)['runs'][0]['arguments']==run['arguments']
        assert len(host.manager.list())==2
        assert compare_candidate_details(fresh,failed_view,'T0')['rows'][0]['right_prediction'] is None
        host.command(doc,'document.save',{})
        retained_rows=table_rows(fresh,'T2')
    # The saved owner is sufficient; delete the original transient job results.
    shutil.rmtree(tmp_path/'results')
    with DetailHost(tmp_path, lambda *args:pytest.fail('Read/reopen evaluated')) as cold:
        reopened=cold.owner.open(document_id=doc)
        frozen=cold.view(doc,job,candidate,attempt_job_id=detail_job)
        assert frozen['session_id']==reopened['session_id']
        assert table_rows(frozen,'T2')==retained_rows
        assert canonical_hash(cold.owner.result(doc,job))==original_hash
        assert len(cold.manager.list())==2 and cold.dispatched==[]


def test_failure_detail_and_original_failure_are_distinct(tmp_path):
    with DetailHost(tmp_path) as host:
        doc,job=host.create_fit(synthetic_inputs(retain=0))
        candidate=intermediate(host,doc,job,'FAILED')
        view=host.view(doc,job,candidate)
        assert all(t['retention']=='NOT_RETAINED' for t in view['trials'])
        before=canonical_hash(host.owner.result(doc,job))
        detail=host.detail(view)['job']['id']
        assert host.wait(detail)['state']=='FAILED'
        after=host.view(doc,job,candidate,attempt_job_id=detail)
        assert after['candidate']['execution_status']=='FAILED'
        assert after['attempt_state']=='FAILED'
        assert all(t['execution_status']=='FAILED' for t in after['trials'])
        assert all(t['retention']=='RETAINED' for t in after['trials'])
        assert all(row['prediction'] is None and row['weighted_residual'] is None for row in table_rows(after,'T1'))
        assert canonical_hash(host.owner.result(doc,job))==before
        assert len(host.manager.list())==2


def test_partial_failure_is_not_full_success(tmp_path):
    with DetailHost(tmp_path) as host:
        doc,job=host.create_fit(synthetic_inputs(retain=0))
        candidate=intermediate(host,doc,job)
        view=host.view(doc,job,candidate)
        def partial(v,s):
            return synthetic(v,{**s,'fail_trial':s['factor']==2.})
        host.evaluator=partial
        detail=host.detail(view)['job']['id']
        assert host.wait(detail)['state']=='PARTIAL_FAILURE'
        after=host.view(doc,job,candidate,attempt_job_id=detail)
        assert [t['execution_status'] for t in after['trials']]==['SUCCEEDED','FAILED','SUCCEEDED']
        assert after['candidate']['execution_status']=='SUCCEEDED'
        assert len(table_rows(after,'T0'))==4
        assert all(r['prediction'] is None for r in table_rows(after,'T1'))
        host.command(doc,'document.save',{})


def test_stale_candidate_source_context_and_generation_block_before_job(tmp_path):
    with DetailHost(tmp_path) as host:
        doc,job=host.create_fit()
        cid=intermediate(host,doc,job)
        view=host.view(doc,job,cid)
        count=len(host.manager.list())
        bad=deepcopy(view['source']);bad['result_sha256']='0'*64
        with pytest.raises(DetailIdentityError,match='Stale'):host.view(doc,job,cid,source=bad)
        with pytest.raises(DetailIdentityError,match='absent'):host.view(doc,job,'Absent')
        with pytest.raises(DetailIdentityError,match='does not belong'):host.view(doc,job,cid,attempt_job_id=job)
        arguments=prepare_detail_arguments(host.owner,view['source'],cid)
        for key in ('unit','role','mask','weight','scale','source_rows','time','deformation_gradient'):
            broken=deepcopy(arguments);e=broken['experiments'][0]
            if key=='unit':e['observations']['unit']='Pa'
            elif key=='source_rows':e['observations']['source_rows'][0]=999
            elif key in ('time','deformation_gradient'):e['settings'][key]=[]
            elif key=='mask':e['mask']=[True]*4
            elif key=='role':e[key]='holdout'
            else:e[key]=99.
            with pytest.raises(DetailIdentityError):validate_detail_arguments(host.owner,broken)
        for key,value in [('candidate_values',{'x':2.}),('source_candidate_status','SUCCEEDED???'),('unexpected',True)]:
            broken=deepcopy(arguments);broken['context'][key]=value
            with pytest.raises(DetailIdentityError):validate_detail_arguments(host.owner,broken)
        with pytest.raises(ValueError,match='session'):
            host.owner.command(doc,COMMAND,{'source':view['source'],'candidate_id':cid},
                session_id='OldSession',expected_generation=view['generation'])
        with pytest.raises(ValueError,match='generation'):
            host.owner.command(doc,COMMAND,{'source':view['source'],'candidate_id':cid},
                session_id=view['session_id'],expected_generation=999)
        assert len(host.manager.list())==count


def test_cancel_preserves_completed_trial_and_explicit_retry_only_missing(tmp_path):
    entered=threading.Event();release=threading.Event();calls=[]
    with DetailHost(tmp_path) as host:
        doc,job=host.create_fit(synthetic_inputs(retain=0))
        cid=intermediate(host,doc,job)
        view=host.view(doc,job,cid)
        def blocking(v,s):
            calls.append(s['factor'])
            if s['factor']==2.:
                entered.set();assert release.wait(10)
                from caelab.execution_control import check_cancelled
                check_cancelled()
            return synthetic(v,s)
        host.evaluator=blocking
        detail=host.detail(view)['job']['id']
        assert entered.wait(10)
        assert not host.view(doc,job,cid)['can_detail_eval']
        with pytest.raises(ValueError):host.detail(view)
        host.manager.cancel(detail);release.set()
        assert host.wait(detail)['state']=='CANCELLED'
        after=host.view(doc,job,cid,attempt_job_id=detail)
        assert after['trials'][0]['execution_status']=='SUCCEEDED'
        assert after['missing_experiments']==['T1','T2']
        completed=deepcopy(after['trials'][0])
        calls.clear()
        host.evaluator=lambda v,s:(calls.append(s['factor']) or synthetic(v,s))
        retry=host.detail(after)['job']['id']
        assert host.wait(retry)['state']=='SUCCEEDED'
        final=host.view(doc,job,cid,attempt_job_id=retry)
        assert final['trials'][0]==completed
        assert calls==[2.,3.]
        assert len(host.manager.list())==3
        assert [a['state'] for a in final['attempts']]==['CANCELLED','SUCCEEDED']


def test_command_response_loss_recovers_without_resubmission(tmp_path,monkeypatch):
    with DetailHost(tmp_path) as host:
        doc,job=host.create_fit()
        cid=intermediate(host,doc,job)
        view=host.view(doc,job,cid)
        original_persist=host.owner._persist_draft
        def lost(document):
            if len(document['runs'])==2:
                raise OSError('Simulated response loss after JobManager admission')
            return original_persist(document)
        monkeypatch.setattr(host.owner,'_persist_draft',lost)
        with pytest.raises(OSError):host.detail(view,command_id='LostResponse')
        monkeypatch.setattr(host.owner,'_persist_draft',original_persist)
        document=host.owner.read(doc)
        assert len(document['runs'])==2
        detail=document['runs'][1]['job_id']
        host.wait(detail)
        before=len(host.manager.list())
        repeated=host.detail(view,command_id='LostResponse')
        assert repeated['job']['id']==detail
        assert len(host.manager.list())==before
        assert document['runs'][1]['recovered_after_response_loss'] is True


def test_result_corruption_is_never_classified_as_missing_failed_detail(tmp_path):
    with DetailHost(tmp_path) as host:
        doc,job=host.create_fit(synthetic_inputs(retain=0))
        cid=intermediate(host,doc,job,'FAILED')
        detail=host.detail(host.view(doc,job,cid))['job']['id'];host.wait(detail)
        host.command(doc,'document.save',{})
        run=next(r for r in host.owner.read(doc)['runs'] if r['job_id']==detail)
        revision=run['retained_result']['revision']
        folder=tmp_path/'documents'/doc/'revisions'/revision/'results'/detail
        target=next(p for p in folder.rglob('*') if p.is_file())
        target.write_bytes(target.read_bytes()+b'corrupt')
        with pytest.raises(ValueError):host.view(doc,job,cid,attempt_job_id=detail)


def test_frozen_data_packet_consumer_rejects_identity_changes():
    experiments=synthetic_inputs()['experiments']
    entries=[]
    for e in experiments:
        frozen=experiment_snapshot(e);obs=frozen['observations']
        entries.append(dict(experiment_id=e['id'],source_rows=obs['source_rows'],mask=frozen['mask'],
            role=frozen['role'],weight=frozen['weight'],scale=frozen['scale'],unit=obs['unit'],
            observations_sha256=canonical_hash(obs),settings_sha256=canonical_hash(frozen['settings']),
            observation_source_sha256=canonical_hash(frozen['observation_source'])))
    packet=dict(schema=INCLUSION_SCHEMA,experiments=entries)
    assert consume_frozen_fit_inclusion(experiments,packet)==experiments
    for key,value in [('source_rows',[2,4,6,8]),('mask',[True]*4),('role','holdout'),('weight',19.),
                      ('scale',19.),('unit','Pa'),('observations_sha256','0'*64),('settings_sha256','0'*64),
                      ('observation_source_sha256','0'*64)]:
        changed=deepcopy(packet);changed['experiments'][0][key]=value
        with pytest.raises(DetailIdentityError):consume_frozen_fit_inclusion(experiments,changed)
    assert experiments==synthetic_inputs()['experiments']


def test_retention_bounds_and_final_original_holdout(tmp_path):
    with DetailHost(tmp_path) as host:
        doc,job=host.create_fit(synthetic_inputs(retain=1))
        result=host.owner.result(doc,job)
        assert result['detail_retention']['retained_candidates']==1
        assert any(c.get('detail_retention')=='NOT_RETAINED_CANDIDATE_LIMIT' for c in result['candidates'])
        final=result['final_candidate_detail']
        view=host.view(doc,job,final['candidate_id'])
        assert all(t['retention']=='RETAINED' for t in view['trials'])
        assert not view['can_detail_eval'] and len(host.manager.list())==1
    retention=FitDetailRetention({'candidate_limit':1,'byte_limit':1})
    e=synthetic_inputs()['experiments'][0]
    row={'candidate_id':'C0','values':{'x':1.}}
    retention.capture(row,[e],[synthetic({'x':1.},e['settings'])])
    assert row['detail_retention']=='NOT_RETAINED_BYTE_LIMIT'
    assert 'candidate_detail' not in row and retention.bytes==0
    for invalid in ({'candidate_limit':True,'byte_limit':1},{'candidate_limit':129,'byte_limit':1},
                    {'candidate_limit':0,'byte_limit':1}):
        with pytest.raises(ValueError):FitDetailRetention(invalid)


def test_existing_client_reads_only_existing_endpoints(tmp_path):
    from types import SimpleNamespace
    with DetailHost(tmp_path) as host:
        doc,job=host.create_fit()
        cid=intermediate(host,doc,job)
        client=SimpleNamespace(document_read=host.owner.read,document_result=host.owner.result,
                               status=host.manager.status)
        before=len(host.manager.list())
        view=client_read_candidate_detail(client,doc,job,cid)
        assert view['candidate']['candidate_id']==cid
        assert len(host.manager.list())==before
