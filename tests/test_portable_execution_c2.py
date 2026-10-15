"""C2 exact file/owner regression. Fixtures are algebra, not physics approval."""
from copy import deepcopy
from pathlib import Path
import json
import shutil
import subprocess
import sys

import pytest
from caelab import numerical_candidate_evidence as evidence
from caelab.numerical_candidate_detail import DetailIdentityError, read_candidate_detail
from caelab.portable_project import inspect_copy, create_copy, open_project, verify_project
from caelab.portable_project_io import PortableProjectError
from caelab.portable_project_execution import load_execution, replay_proof
from caelab.storage import load_json, save_json, canonical_hash
from caelab.evaluation import file_hash
from caelab.workbench import Workbench
from examples.portable_connection_public import command, save
from _portable_connection_c2_support import (make_pending,make_bound,copied,run_cold,cold_guard,
                                            exact_ref,persisted_check)


def tree(folder):
    """Only the exact ACTIVE runtime byte-range lock is not read on Windows."""
    lock=Path(folder)/'workbench/controller.lock'
    return {p.relative_to(folder).as_posix():
        ('runtime-lock',p.stat().st_size,p.stat().st_mtime_ns) if p==lock else file_hash(p)
        for p in Path(folder).rglob('*') if p.is_file()}


@pytest.fixture(scope='module')
def pending_template(tmp_path_factory):
    folder=tmp_path_factory.mktemp('pending-c2')
    wb,chosen,request=make_pending(folder/'original')
    try:
        before=tree(wb.workspace);inspection=inspect_copy(wb,chosen)
        copied(wb,chosen,folder/'project')
        assert tree(wb.workspace)==before
        for row in inspection['files']:
            archived=folder/'project/portable/originals'/row['document_id']/row['saved_revision']/row['asset']
            assert file_hash(archived)==row['sha256']
    finally:wb.shutdown()
    (folder/'original').rename(folder/'original-disconnected')
    return folder,request


@pytest.fixture(scope='module')
def bound_template(tmp_path_factory):
    folder=tmp_path_factory.mktemp('bound-c2')
    wb,chosen,request=make_bound(folder/'original')
    try:copied(wb,chosen,folder/'project')
    finally:wb.shutdown()
    (folder/'original').rename(folder/'original-disconnected')
    return folder,request


@pytest.fixture
def project(tmp_path,pending_template):
    template,request=pending_template
    path=tmp_path/'한글 공백 작업 사본';shutil.copytree(template/'project',path)
    return path,deepcopy(request)


def numerical(wb):
    return next(d for d in wb.documents()['documents'] if d['kind']=='numerical')


def test_pending_complete_cold_no_origin_or_execution(project,tmp_path):
    path,request=project
    result=run_cold(path,request,tmp_path/'cold')
    assert result['status']=='PASSED' and result['raw_evidence_bytes_preserved']
    assert result['evaluator_and_dispatch_calls']==[] and result['jobs_on_reopen']==0
    assert result['report_intent']=='success_report'
    assert persisted_check(result['recopy'])['evidence_count']>=1


def test_real_bound_data_detail_report_compare_adoption_and_second_process(tmp_path,bound_template):
    folder,request=bound_template
    path=tmp_path/'사본';shutil.copytree(folder/'project',path)
    result=run_cold(path,request,tmp_path/'cold')
    assert result['adopted'] and result['comparison']
    assert result['engineering_release']=='NOT_RELEASED' and result['holdout_acceptance']=='NOT_ASSESSED'
    # Reopen actual saved Report in a different process, then reopen a re-copy.
    for i,(workspace,prior) in enumerate([(path,result),(Path(result['recopy']),None)]):
        args=[sys.executable,'-m','examples.portable_connection_c2_public','--cold',str(workspace),
              '--inspect-only','--result',str(tmp_path/f'inspect-{i}.json')]
        if prior:
            save_json(tmp_path/'prior.json',prior);args+=['--request',str(tmp_path/'prior.json')]
        p=subprocess.run(args,capture_output=True,text=True,timeout=90)
        assert p.returncode==0,p.stderr
        checked=load_json(tmp_path/f'inspect-{i}.json')
        assert checked['adoptions']==1 and checked['graph_broken']==0
        assert checked['evaluator_and_dispatch_calls']==[]
    # Original fit/holdout/Data/result bytes are not consumed or reauthored.
    assert not (folder/'original').exists()


@pytest.mark.parametrize('fault',['missing_evidence','changed_snapshot','receipt_owner','receipt_hash','row_binding'])
def test_pending_prepublication_rejects_missing_or_contradictory_evidence(tmp_path,pending_template,fault):
    template,request=pending_template;source=tmp_path/'source'
    shutil.copytree(template/'original-disconnected',source)
    wb=Workbench(source)
    try:
        doc=request['document_id'];folder=wb.numerical_documents._folder(doc)
        prior=inspect_copy(wb,[doc]); assert prior['status']=='READY'
        if fault in ('missing_evidence','changed_snapshot'):
            path=next((folder/'candidate_evidence').glob('H*.json'))
            if fault=='missing_evidence':path.unlink()
            else:
                value=load_json(path);value['purpose']='wrong';save_json(path,value)
        elif fault.startswith('receipt'):
            path=folder/'commands/CscopeRetry.json';value=load_json(path)
            if fault=='receipt_owner':value['capture_scope']['document_id']='Nother'
            else:value['snapshot_sha256']='f'*64
            save_json(path,value)
        else:
            path=folder/'working.json';value=load_json(path)
            value['candidate_evidence'][0]['binding']['candidate_id']='Cwrong';save_json(path,value)
        before=tree(source)
        inspection=inspect_copy(wb,[doc]);assert inspection['status']=='BLOCKED'
        assert any('EVIDENCE' in r['code'] for r in inspection['issues']),inspection
        with pytest.raises(PortableProjectError):
            create_copy(wb,prior,tmp_path/'must not exist',approved=True,command_id='Creject',session_id=wb.session_id)
        assert not (tmp_path/'must not exist').exists()
        assert tree(source)==before
    finally:wb.shutdown()


@pytest.mark.parametrize('part',['proof','mapping','original_input','original_job','result','evidence'])
def test_immutable_tamper_is_rejected_not_recomputed(project,part):
    path,request=project
    manifest=load_json(path/'portable-project.json')
    needle={'proof':'/portable_execution/proofs/','mapping':'/portable_execution/maps/',
        'original_input':'/portable_execution/inputs/','original_job':'/portable_execution/jobs/',
        'result':'/results/','evidence':'/candidate_evidence/'}[part]
    target=next(path/r['path'] for r in manifest['files'] if needle in r['path'] and '/portable/originals/' not in r['path'])
    raw=target.read_bytes();target.write_bytes(raw+b' ')
    with cold_guard():
        assert verify_project(path)['status']=='BLOCKED'
        with pytest.raises(PortableProjectError):open_project(path)
    target.write_bytes(raw)
    assert verify_project(path)['status']=='READY'


def test_informational_origin_marker_cannot_override_verified_mapping(project):
    path,request=project
    with cold_guard():
        wb=open_project(path)
        try:
            doc=numerical(wb);owner=wb.numerical_documents
            raw=owner._documents[doc['id']]
            run=next(r for r in raw['runs'] if r['job_id']==request['fit_job'])
            run['portable_origin']['input_sha256']='f'*64
            with pytest.raises(DetailIdentityError,match='origin marker'):
                read_candidate_detail(owner,doc['id'],request['fit_job'],request['candidate_id'])
        finally:wb.shutdown()


@pytest.mark.parametrize('fault',['source_scope','input_hash','duplicate_owner','target_owner','raw_arguments'])
def test_rehashed_projection_file_still_requires_semantic_exact_replay(project,tmp_path,fault):
    path,request=project;wb=open_project(path)
    try:
        doc=numerical(wb);run=next(r for r in doc['runs'] if r['job_id']==request['fit_job'])
        folder,proof,original=load_execution(wb.numerical_documents,doc['id'],run)
        scratch=tmp_path/'proof-scratch';shutil.copytree(folder,scratch)
        link=deepcopy(run['portable_execution']);ref=proof['hops'][0]['mapping'];mapping=load_json(scratch/ref['file'])
        if fault=='source_scope':mapping['source_scope']='different-store'
        elif fault=='input_hash':mapping['inputs'][0]['source_input_sha256']='f'*64
        elif fault=='duplicate_owner':mapping['documents'].append(deepcopy(mapping['documents'][0]))
        elif fault=='target_owner':mapping['documents'][0]['document_id']='Nother'
        else:
            raw=proof['origin']['input'];value=load_json(scratch/raw['file']);value['arguments']['backend']='wrong'
            save_json(scratch/raw['file'],value);raw['sha256']=file_hash(scratch/raw['file'])
        save_json(scratch/ref['file'],mapping);ref['sha256']=file_hash(scratch/ref['file'])
        save_json(scratch/link['file'],proof);link['sha256']=file_hash(scratch/link['file'])
        with pytest.raises((DetailIdentityError,ValueError,KeyError)):
            replay_proof(scratch,link,doc['id'],run)
    finally:wb.shutdown()


@pytest.mark.parametrize('field',['document_id','saved_revision','candidate_id','candidate_sha256',
                                  'attempt_job_id','snapshot_sha256','source.input_sha256','source.result_sha256'])
def test_evidence_wrong_owner_candidate_attempt_or_input_rejected(project,field):
    path,request=project
    with cold_guard():
        wb=open_project(path)
        try:
            doc=save(wb,numerical(wb));ref=exact_ref(wb,doc['id'],doc['candidate_evidence'][0])
            broken=deepcopy(ref);parent=broken
            parts=field.split('.')
            for key in parts[:-1]:parent=parent[key]
            parent[parts[-1]]=('f'*64 if 'sha256' in field else {'document_id':'Nother','saved_revision':'Rother',
                'candidate_id':'Cother','attempt_job_id':'Jother'}[field])
            with pytest.raises((ValueError,FileNotFoundError,KeyError)):
                evidence.resolve_candidate_evidence(wb.numerical_documents,broken,consumer='adoption')
            assert evidence.resolve_candidate_evidence(wb.numerical_documents,ref)['snapshot']['source']['document_id']==request['document_id']
        finally:wb.shutdown()


def test_mid_retention_failure_current_capture_exact_retry_and_no_old_authority(project,monkeypatch):
    path,request=project
    with cold_guard():
        wb=open_project(path)
        try:
            doc=numerical(wb);owner=wb.numerical_documents
            view=read_candidate_detail(owner,doc['id'],request['fit_job'],request['candidate_id'],attempt_job_id=request['detail_job'])
            args=dict(source=view['source'],candidate_id=request['candidate_id'],attempt_job_id=request['detail_job'],purpose=evidence.SUCCESS)
            identity=dict(session_id=wb.session_id,expected_generation=doc['generation'],command_id='CnewC2PendingRetry')
            pointer=owner._folder(doc['id'])/'document.json';before=pointer.read_bytes()
            from caelab import portable_project_execution as execution
            original=execution.copy_verified;calls=[]
            def fail_second(*args,**kwargs):
                calls.append(1)
                if len(calls)==2:raise OSError('injected portable proof retain failure')
                return original(*args,**kwargs)
            with monkeypatch.context() as patch:
                patch.setattr(execution,'copy_verified',fail_second)
                with pytest.raises(OSError,match='proof retain'):
                    owner.command(doc['id'],evidence.CAPTURE,args,**identity)
            assert pointer.read_bytes()==before
            receipt=load_json(owner._folder(doc['id'])/'commands/CnewC2PendingRetry.json')
            assert receipt['state']=='PRESERVING' and receipt['phase']=='REGISTERED'
            result=owner.command(doc['id'],evidence.CAPTURE,args,**identity)
            assert evidence.resolve_candidate_evidence(owner,result['reference'],consumer='adoption')['readiness']['success_judgment_permitted']
            assert owner.command(doc['id'],evidence.CAPTURE,args,**identity)==result
            # Old C2 session receipt cannot be replayed even after a new success.
            old=request['old_capture']
            with pytest.raises(ValueError):owner.command(doc['id'],evidence.CAPTURE,old['arguments'],**old['identity'])
        finally:wb.shutdown()


def test_acknowledged_container_is_not_published_evidence(project):
    path,request=project;wb=open_project(path)
    try:
        doc=numerical(wb);row=doc['candidate_evidence'][0]
        manifest=load_json(path/'portable-project.json')
        ack=manifest['documents'][0]['acknowledged_revision']
        snapshot=load_json(wb.numerical_documents._folder(doc['id'])/'candidate_evidence'/(row['id']+'.json'))
        with pytest.raises(DetailIdentityError,match='Acknowledged container'):
            evidence.evidence_reference(doc['id'],ack,snapshot,owner=wb.numerical_documents)
        doc=save(wb,doc)
        assert exact_ref(wb,doc['id'],doc['candidate_evidence'][0])['saved_revision']==doc['saved_revision']
    finally:wb.shutdown()


def test_actual_client_http_uses_same_verified_read_and_command(project):
    from test_portable_connection_http import serving
    from caelab.numerical_candidate_evidence_cli import execute_request
    path,request=project
    with cold_guard():
        with serving(path) as (server,client):
            wb=server.workbench;doc=numerical(wb)
            expected=wb.numerical_candidate_detail(doc['id'],request['fit_job'],request['candidate_id'],attempt_job_id=request['detail_job'])
            actual=client.numerical_candidate_detail(doc['id'],request['fit_job'],request['candidate_id'],attempt_job_id=request['detail_job'])
            assert actual==expected
            assert actual['source']['document_id']!=actual['execution_source']['document_id']
            command_request={'document_id':doc['id'],'operation':evidence.CAPTURE,
                'arguments':dict(source=actual['source'],candidate_id=request['candidate_id'],attempt_job_id=request['detail_job'],purpose=evidence.SUCCESS),
                'session_id':doc['session_id'],'expected_generation':doc['generation'],'command_id':'ChttpC2Capture'}
            # Actual CLI request adapter -> actual HTTP Client -> same owner.
            captured=execute_request(client,command_request)
            assert captured==execute_request(client,command_request)
            assert wb.manager.list()==[]
            source=client.research_reference(captured['reference'])
            assert source['status']=='AVAILABLE'
            assert source['candidate_evidence']['snapshot']['source']['document_id']==request['document_id']


def test_remote_read_projection_does_not_authorize_server_writes(project):
    from types import SimpleNamespace
    from caelab.numerical_candidate_detail import client_read_candidate_detail
    path,request=project
    with cold_guard():
        wb=open_project(path)
        try:
            doc=numerical(wb);mutated=deepcopy(doc)
            run=next(r for r in mutated['runs'] if r['job_id']==request['fit_job'])
            run['portable_execution_read']['current_run_sha256']='f'*64
            client=SimpleNamespace(document_read=lambda ident:mutated,document_result=wb.document_result,status=wb.manager.status)
            with pytest.raises(DetailIdentityError,match='server did not supply'):
                client_read_candidate_detail(client,doc['id'],request['fit_job'],request['candidate_id'])
            # The actual owner uses retained proof bytes, not any caller read envelope.
            view=wb.numerical_candidate_detail(doc['id'],request['fit_job'],request['candidate_id'],attempt_job_id=request['detail_job'])
            assert view['execution_source']['document_id']==request['document_id']
        finally:wb.shutdown()


@pytest.mark.parametrize('field',['reference','publication'])
def test_completed_receipt_contradiction_rejected_before_copy(tmp_path,bound_template,field):
    template,request=bound_template;path=tmp_path/'original copy'
    shutil.copytree(template/'original-disconnected',path)
    wb=Workbench(path)
    try:
        doc=request['document_id'];folder=wb.numerical_documents._folder(doc)
        receipt_path=next(p for p in (folder/'commands').glob('*.json')
            if load_json(p).get('operation')==evidence.CAPTURE)
        receipt=load_json(receipt_path)
        if field=='reference':receipt['response']['reference']['candidate_id']='Cwrong'
        else:receipt['publication']['scope_sha256']='f'*64
        save_json(receipt_path,receipt)
        selected=request['data_ids']+[request['material_id'],doc]
        result=inspect_copy(wb,selected)
        assert result['status']=='BLOCKED'
        assert any(r['code']=='CANDIDATE_EVIDENCE_UNAVAILABLE' for r in result['issues']),result
    finally:wb.shutdown()


def test_current_capture_stale_generation_rejected_without_losing_saved_read(project):
    path,request=project
    with cold_guard():
        wb=open_project(path)
        try:
            doc=save(wb,numerical(wb));owner=wb.numerical_documents
            ref=exact_ref(wb,doc['id'],doc['candidate_evidence'][0])
            view=wb.numerical_candidate_detail(doc['id'],request['fit_job'],request['candidate_id'],attempt_job_id=request['detail_job'])
            draft=deepcopy(doc['draft']);draft['request']['purpose']+=' 명시 편집'
            edited=command(wb,doc,'numerical.update',{'draft':draft})
            args=dict(source=view['source'],candidate_id=request['candidate_id'],attempt_job_id=request['detail_job'],purpose=evidence.SUCCESS)
            with pytest.raises(ValueError,match='generation'):
                owner.command(doc['id'],evidence.CAPTURE,args,session_id=wb.session_id,
                    expected_generation=doc['generation'],command_id='CstaleCapture')
            assert owner.read(doc['id'])['draft']==edited['draft']
            assert evidence.resolve_candidate_evidence(owner,ref)['snapshot']['source']['document_id']==request['document_id']
        finally:wb.shutdown()
