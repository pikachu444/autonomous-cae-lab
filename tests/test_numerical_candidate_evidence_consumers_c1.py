"""Native-owner/service consumers cannot bypass C03 by calling Python directly."""
from copy import deepcopy
import shutil

import pytest

from caelab.numerical_document import adopted_draft
from caelab.numerical_candidate_evidence import (CAPTURE, SUCCESS, FAILURE, DetailEvidenceBlocked,
    resolve_candidate_evidence, candidate_adoption_preview)
from caelab.storage import canonical_hash
from caelab.report_document import check_selection, compact_payload, ReportDocuments
from caelab.research_workflows import resolve_reference
from apps.research.numerical_candidate_evidence_report import candidate_evidence_blocks
from _numerical_candidate_detail_support import intermediate, DetailHost, synthetic_inputs
from _numerical_candidate_evidence_support import BoundHost, InProcessClient
from test_numerical_candidate_evidence_c1 import capture, complete


def test_direct_adopted_draft_and_legacy_service_block_then_verified_adopt(tmp_path):
    with BoundHost(tmp_path) as host:
        doc,job,mid=host.create_bound_fit();cid=intermediate(host,doc,job)
        result=host.owner.result(doc,job)
        run=next(r for r in host.owner.read(doc)['runs'] if r['job_id']==job)
        original_hash=canonical_hash(result)
        target=host.materials.read(mid)
        common=dict(material_document_id=mid,session_id=target['session_id'],
                    expected_generation=target['generation'],command_id='CmaterialAdopt')
        with pytest.raises(DetailEvidenceBlocked): adopted_draft(run,result,cid)
        with pytest.raises(DetailEvidenceBlocked): host.core.desktop.adopt(doc,job,cid,**common)
        client=InProcessClient(host.core)
        with pytest.raises(DetailEvidenceBlocked): client.numerical_adopt(doc,job,cid,**common)
        assert host.materials.read(mid)['draft']==target['draft']
        assert len(host.manager.list())==1
        view=complete(host,doc,job,cid);ref=capture(host,view)['reference']
        preview=candidate_adoption_preview(host.owner,ref)
        assert preview['proposed_draft']['settings']['parameters']['E']==view['candidate']['values']['E']
        assert preview['readiness']['success_judgment_permitted']
        receipt=client.numerical_adopt(doc,job,cid,**common,detail_evidence=ref)
        adopted=host.materials.read(mid)
        assert adopted['draft']==preview['proposed_draft']
        assert adopted['adoptions'][-1]['candidate_evidence']==ref
        assert client.numerical_adopt(doc,job,cid,**common,detail_evidence=ref)==receipt
        assert canonical_hash(host.owner.result(doc,job))==original_hash
        assert len(host.manager.list())==2
        assert any(path.endswith('/commands') and body['operation']=='numerical.evidence.adopt'
                   for path,body in client.requests if body)
        # No-ref legacy endpoint cannot reuse an earlier authorized receipt.
        with pytest.raises(DetailEvidenceBlocked): host.core.desktop.adopt(doc,job,cid,**common)


def test_report_capture_metadata_allowed_selected_success_requires_exact_evidence(tmp_path):
    with BoundHost(tmp_path) as host:
        doc,job,mid=host.create_bound_fit();cid=intermediate(host,doc,job)
        host.command(doc,'document.save',{})
        source=host.view(doc,job,cid)['source']
        report=host.reports.open()
        metadata={'kind':'result',**source,'selection':{'metadata_only':True,'candidate_ids':[cid]}}
        summary=host.reports.capture(report['id'],metadata)
        content=host.reports.asset(report['id'],summary)['content']
        assert content['report_intent']=='METADATA_ONLY_NOT_A_SUCCESS_JUDGMENT'
        assert content['success_judgment_permitted'] is False
        legacy={'kind':'result',**source,'selection':{'candidate_ids':[cid],'responses':['stress_xx']}}
        with pytest.raises(ValueError): host.reports.capture(report['id'],legacy)
        assert len(host.manager.list())==1
        view=complete(host,doc,job,cid);ref=capture(host,view)['reference']
        binding=host.reports.capture(report['id'],ref)
        frozen=host.reports.asset(report['id'],binding)
        assert frozen['content']['report_intent']=='success_report'
        assert frozen['content']['candidate_evidence']['reference']==ref
        blocks=list(candidate_evidence_blocks(frozen['content']))
        assert any(kind=='table' for kind,_ in blocks) and any(kind=='curve' for kind,_ in blocks)
        assert any('별도 확인' in str(value) and '공학 승인은 미확인' in str(value) for kind,value in blocks)
        draft=deepcopy(report['draft'])
        draft['sections']=[dict(id='Section1',title='Exact selected fit',text='',include=True,table=True,curve=True,asset=binding)]
        host.report_command(report['id'],'report.update',{'draft':draft})
        host.report_command(report['id'],'document.save',{})
        actual=host.reports.content(report['id'],[binding])['assets'][0]
        assert actual['source_status']=='AVAILABLE'
        assert actual['content']==frozen['content']
        assert len(host.manager.list())==2
        # Same report snapshot remains readable even if source becomes unavailable.
        host.reports.resolve_reference=lambda ref:(_ for _ in ()).throw(ValueError('Source owner temporarily unavailable'))
        unavailable=host.reports.content(report['id'],[binding])['assets'][0]
        assert unavailable['source_status']=='UNAVAILABLE'
        assert unavailable['content']==frozen['content']


def test_failure_diagnostic_report_preserved_and_new_report_owner_after_move(tmp_path):
    old,new=tmp_path/'old',tmp_path/'새 연구 폴더'
    with DetailHost(old) as host:
        doc,job=host.create_fit(synthetic_inputs(retain=0));cid=intermediate(host,doc,job,'FAILED')
        ref=capture(host,host.view(doc,job,cid),purpose=FAILURE)['reference']
        # Use actual shared reference consumer for candidate evidence.
        from types import SimpleNamespace
        core=SimpleNamespace(numerical_documents=host.owner)
        reports=ReportDocuments(old,host.owner.session_id,host._submit,host.manager,
            resolve_reference=lambda reference:resolve_reference(core,reference))
        report=reports.open();rid=report['id']
        binding=reports.capture(rid,ref)
        frozen=reports.asset(rid,binding)
        assert frozen['content']['report_intent']=='failure_report'
        detail=frozen['content']['candidate_evidence']
        assert detail['readiness']['failure_diagnostic_permitted']
        assert not detail['readiness']['success_judgment_permitted']
        blocks=list(candidate_evidence_blocks(frozen['content']))
        assert any('계산 실패' in str(value) for _,value in blocks)
        assert not any(kind=='curve' and '예측' in value.get('y_label','') for kind,value in blocks if isinstance(value,dict))
        draft=deepcopy(report['draft']);draft['sections']=[dict(id='Diagnostic',title='원 실패',text='',include=True,table=True,curve=True,asset=binding)]
        for op,args in [('report.update',{'draft':draft}),('document.save',{})]:
            current=reports.read(rid)
            reports.command(rid,op,args,session_id=current['session_id'],expected_generation=current['generation'])
    shutil.move(old,new)
    shutil.rmtree(new/'results',ignore_errors=True)
    shutil.rmtree(new/'documents'/rid/'assets',ignore_errors=True)
    (new/'documents'/rid/'working.json').unlink(missing_ok=True)
    with DetailHost(new) as cold:
        core=SimpleNamespace(numerical_documents=cold.owner)
        reports=ReportDocuments(new,cold.owner.session_id,cold._submit,cold.manager,
            resolve_reference=lambda reference:resolve_reference(core,reference))
        reopened=reports.content(rid,[binding])['assets'][0]
        assert reopened['source_status']=='AVAILABLE'
        assert reopened['content']==frozen['content']
        assert reopened['reference']==ref
        assert cold.dispatched==[]


def test_cli_uses_existing_service_gate_exact_generation_and_no_evaluation(tmp_path):
    from caelab.numerical_candidate_evidence_cli import execute_request
    from caelab.numerical_candidate_evidence import READ
    with BoundHost(tmp_path) as host:
        doc,job,mid=host.create_bound_fit();cid=intermediate(host,doc,job)
        client=InProcessClient(host.core)
        current=host.owner.read(doc);view=host.view(doc,job,cid)
        request={'document_id':doc,'operation':CAPTURE,'arguments':dict(source=view['source'],
            candidate_id=cid,attempt_job_id=None,purpose=SUCCESS),'session_id':current['session_id'],
            'expected_generation':current['generation'],'command_id':'CCliCapture'}
        with pytest.raises(DetailEvidenceBlocked): execute_request(client,request)
        assert len(host.manager.list())==1
        view=complete(host,doc,job,cid)
        request['arguments']['attempt_job_id']=view['attempt_job_id']
        request['command_id']='CCliVerifiedCapture'
        request['expected_generation']=host.owner.read(doc)['generation']
        response=execute_request(client,request)
        assert response['reference']['attempt_job_id']==view['attempt_job_id']
        assert execute_request(client,request)==response # exact idempotent retransmit
        current=host.owner.read(doc)
        read={**request,'operation':READ,'arguments':{'reference':response['reference'],'consumer':'adoption'},
              'expected_generation':current['generation'],'command_id':'CCliRead'}
        assert execute_request(client,read)['evidence']['readiness']['success_judgment_permitted']
        wrong=deepcopy(read);wrong['arguments']['reference']['candidate_sha256']='a'*64
        with pytest.raises(ValueError): execute_request(client,wrong)
        with pytest.raises(ValueError): execute_request(client,{**read,'operation':'numerical.detail_eval'})
        with pytest.raises(ValueError): execute_request(client,{**read,'expected_generation':True})
        assert len(host.manager.list())==2


def test_two_distinct_candidate_comparison_uses_each_explicit_saved_attempt(tmp_path):
    from caelab.numerical_candidate_evidence import COMPARE
    from caelab.numerical_candidate_detail import table_rows
    with DetailHost(tmp_path) as host:
        doc,job=host.create_fit(synthetic_inputs(retain=0))
        original=host.owner.result(doc,job)
        final=(original.get('final_candidate_detail') or {}).get('candidate_id')
        left_id=intermediate(host,doc,job)
        left_candidate=next(c for c in original['candidates'] if c['candidate_id']==left_id)
        right_id=next(c['candidate_id'] for c in original['candidates']
            if c['execution_status']=='SUCCEEDED' and c['candidate_id'] not in {left_id,final}
            and c['values']!=left_candidate['values'])
        left_view=complete(host,doc,job,left_id);left=capture(host,left_view)['reference']
        right_view=complete(host,doc,job,right_id);right=capture(host,right_view)['reference']
        answer=host.command(doc,COMPARE,{'left':left,'right':right,'experiment_id':'T2'})['evidence']
        assert answer['left_candidate_id']!=answer['right_candidate_id']
        assert answer['evidence_references']=={'left':left,'right':right}
        assert answer['left_attempt_job_id']==left_view['attempt_job_id']
        assert answer['right_attempt_job_id']==right_view['attempt_job_id']
        assert answer['completion']=='EVIDENCE_VERIFIED_COMPARISON' and answer['success_judgment_permitted']
        assert answer['preservation']=='IMMUTABLE_REVISION_VERIFIED'
        assert all(r['success_judgment_permitted'] for r in answer['readiness'].values())
        assert answer['ranking']=='NOT_PERFORMED' and answer['holdout_acceptance']=='NOT_ASSESSED'
        left_rows,right_rows=table_rows(left_view,'T2'),table_rows(right_view,'T2')
        for pair,a,b in zip(answer['rows'],left_rows,right_rows):
            assert pair['left_prediction']==a['prediction']
            assert pair['right_prediction']==b['prediction']
            assert pair['source_row']==a['source_row']==b['source_row']
        assert canonical_hash(host.owner.result(doc,job))==canonical_hash(original)
        assert len(host.manager.list())==3
