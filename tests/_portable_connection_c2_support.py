"""C2 public algebra fixtures on the actual existing owners, not a solver.

Only fixture *creation* enables synthetic dispatch. cold_actions installs the
Numerical team's existing tripwire at evaluator, dispatch, submit and DAG.
"""
from copy import deepcopy
from pathlib import Path
from contextlib import contextmanager
import json
import shutil
import subprocess
import sys
import uuid

import pytest
from caelab import numerical_candidate_evidence as evidence
from caelab.numerical_candidate_detail import read_candidate_detail
from caelab.portable_project import inspect_copy, create_copy, open_project, verify_project
from caelab.storage import canonical_hash, load_json, save_json
from caelab.evaluation import file_hash
from caelab.workbench import Workbench
from examples.portable_connection_public import create_public_store, command, save, wait
from _numerical_candidate_detail_support import DetailHost, synthetic, intermediate
from _numerical_candidate_evidence_support import algebra_stress
from test_numerical_candidate_evidence_c1 import complete, capture
from test_numerical_candidate_evidence_c2 import selection, failed_capture, no_current_write


def graft(wb, evaluator=synthetic):
    host = DetailHost.__new__(DetailHost)
    host.root, host.owner, host.manager = wb.root, wb.numerical_documents, wb.manager
    host.evaluator, host.dispatched = evaluator, []
    host.owner.prepare_request = lambda request: deepcopy(request['inputs'])
    host.owner.submit = host._submit
    original = wb.manager._execute
    wb.manager._execute = lambda operation, arguments, identifier: (
        host._execute(operation, arguments, identifier) if operation in {'fit', 'detail_eval'}
        else original(operation, arguments, identifier))
    return host


def make_pending(root):
    wb = Workbench(root)
    try:
        host = graft(wb)
        doc, job, view, args, identity = selection(host, undo_history=True)
        with pytest.MonkeyPatch.context() as patch:
            failed_capture(host, doc, args, identity, patch)
        request = dict(case='pending_evidence', document_id=doc, fit_job=job,
            candidate_id=view['candidate']['candidate_id'], detail_job=view['attempt_job_id'],
            old_capture={'arguments': args, 'identity': identity},
            evidence_hashes=evidence_hashes(wb,doc), result_hash=canonical_hash(host.owner.result(doc,job)))
        return wb, [doc], request
    except BaseException:
        wb.shutdown(); raise


def evidence_hashes(wb, doc):
    folder = wb.numerical_documents._folder(doc)
    return {p.stem:file_hash(p) for p in (folder/'candidate_evidence').glob('H*.json')}


def make_bound(root):
    """Real retained Data imports and Material binding, fit + holdout algebra."""
    wb, records = create_public_store(root)
    try:
        host = graft(wb, algebra_stress)
        fit_data = wb.document_read(records['data']['id'])
        # A second explicit physical unit-compatible table, with different raw
        # bytes and provenance. No implicit fit/holdout row reuse or mapping.
        upload = wb.upload('공개 검증 관측.csv', b'time,stress\n0,0\n1,1.3\n2,2.6\n')
        draft = deepcopy(fit_data['draft']); draft['data_id']=upload['id']
        draft['test_metadata']['test_id']='PUBLIC_HOLDOUT'
        holdout = wb.document_open(kind='data', title='별도 검증 관측', draft=draft)
        outcome = wb.document_command(holdout['id'],'data.import',{},session_id=wb.session_id,
                                     expected_generation=holdout['generation'])
        assert wait(wb,outcome['job']['id'])['state']=='SUCCEEDED'
        holdout = save(wb, wb.document_read(holdout['id']))
        material=wb.document_read(records['material']['id'])
        from caelab.numerical_document import from_material_document
        plan=from_material_document(material)
        for var in plan['variables']:
            if var['id']=='E': var.update(lower=500.,upper=2000.)
        plan.update(budget=32)
        for i,(data,jobid) in enumerate([(fit_data,records['success_job']['id']), (holdout,outcome['job']['id'])]):
            run=next(r for r in data['runs'] if r['job_id']==jobid)
            plan['experiments'].append(dict(id=f'Trial{i}',role='fit' if i==0 else 'holdout',
                source={**{k:run[k] for k in ('job_id','input_revision','input_sha256')},
                        'document_id':data['id'],'response':'stress'},response='stress_xx',
                settings=deepcopy(material['draft']['settings']),weight=2.,scale=1.))
        doc=host.owner.open(title='실제 자료 연결 후보',draft=plan)
        assert not doc['diagnostics'],doc['diagnostics']
        doc=doc['id']; response=host.command(doc,'numerical.run',{})
        job=response['job']['id']; assert host.wait(job)['state']=='SUCCEEDED'
        cid=intermediate(host,doc,job)
        view=complete(host,doc,job,cid)
        first=capture(host,view)['reference']
        candidates=host.owner.result(doc,job)['candidates']
        other=next(c['candidate_id'] for c in candidates if c['execution_status']=='SUCCEEDED' and c['candidate_id']!=cid)
        other_view=complete(host,doc,job,other)
        second=capture(host,other_view)['reference']
        # Preserve acknowledged editing + Undo without changing frozen runs.
        draft=deepcopy(host.owner.read(doc)['draft']); draft['count']+=1
        host.command(doc,'numerical.update',{'draft':draft})
        request=dict(case='bound_adoption', document_id=doc,fit_job=job,candidate_id=cid,
            detail_job=view['attempt_job_id'], other_candidate_id=other,other_detail_job=other_view['attempt_job_id'],
            material_id=material['id'], evidence_hashes=evidence_hashes(wb,doc),
            result_hash=canonical_hash(host.owner.result(doc,job)),original_source=view['source'],
            original_frozen=canonical_hash(view['fit_input']), original_plan=canonical_hash(view['original_plan']),
            data_ids=[fit_data['id'],holdout['id']])
        return wb,[fit_data['id'],holdout['id'],material['id'],doc],request
    except BaseException:
        wb.shutdown();raise


def copied(wb, chosen, destination, command_id='CportableC2'):
    inspection=inspect_copy(wb,chosen)
    assert inspection['status']=='READY',inspection
    return create_copy(wb,inspection,destination,approved=True,command_id=command_id,session_id=wb.session_id)


def tripwires(wb, patch, calls):
    def stop(*args, **kwargs):
        calls.append('forbidden execution')
        no_current_write(*args, **kwargs) # existing exact peer tripwire
    patch.setattr(wb.manager,'submit',stop)
    patch.setattr(wb.manager,'_execute',stop)
    for name in ('numerical_documents','material_documents','data_documents','report_documents'):
        owner=getattr(wb,name,None)
        if owner is not None:patch.setattr(owner,'submit',stop)
    from caelab import numerical, numerical_candidate_detail
    patch.setattr(numerical,'fit_model',stop)
    patch.setattr(numerical_candidate_detail,'evaluate_candidate_detail',stop)
    # Actual evaluation/DAG boundaries, only when present in this exact source.
    import caelab.evaluation as evaluation
    for name in ('evaluate','evaluate_definition','run_evaluation'):
        if hasattr(evaluation,name):patch.setattr(evaluation,name,stop)


def exact_ref(wb, doc, row):
    return evidence.evidence_reference(doc,row['retained_revision'],
        load_json(wb.numerical_documents._folder(doc)/'revisions'/row['retained_revision']/
                  'candidate_evidence'/(row['id']+'.json')), owner=wb.numerical_documents)


@contextmanager
def cold_guard():
    # Install before constructing the owner/controller, not only before reads.
    calls=[]
    with pytest.MonkeyPatch.context() as patch:
        def stop(*args,**kwargs):
            calls.append('forbidden execution')
            no_current_write(*args,**kwargs)
        from caelab.jobs import JobManager
        from caelab import numerical, numerical_candidate_detail, evaluation
        from caelab import evaluation_definition, research_workflows, research_execution
        patch.setattr(JobManager,'submit',stop)
        patch.setattr(Workbench,'_execute',stop)
        patch.setattr(numerical,'fit_model',stop)
        patch.setattr(numerical_candidate_detail,'evaluate_candidate_detail',stop)
        patch.setattr(evaluation,'evaluate',stop)
        patch.setattr(evaluation_definition,'execute',stop)
        patch.setattr(research_workflows,'execute_definition',stop)
        patch.setattr(research_execution,'run_domain',stop)
        yield calls
        assert calls==[]


def cold_actions(folder, request, *, adopt=True, recopy=True):
    with cold_guard() as calls:
        return _cold_actions(folder,request,adopt=adopt,recopy=recopy,calls=calls)


def _cold_actions(folder, request, *, adopt, recopy, calls):
    wb=open_project(folder)
    try:
        assert wb.manager.list()==[]
        with pytest.MonkeyPatch.context() as patch:
            tripwires(wb,patch,calls)
            manifest=load_json(Path(folder)/'portable-project.json')
            identities={r['source_document_id']:r['document_id'] for r in manifest['documents']}
            doc=identities[request['document_id']]
            owner=wb.numerical_documents
            current=owner.read(doc)
            # No approval/session migration: old receipt is NOT a new command.
            if request.get('old_capture'):
                old=request['old_capture']
                assert not (owner._folder(doc)/'commands'/(old['identity']['command_id']+'.json')).exists()
                assert all(r['authority']=='HISTORY_ONLY' for r in current['portable_capture_history'])
                with pytest.raises(ValueError):owner.command(doc,evidence.CAPTURE,old['arguments'],**old['identity'])
                assert not current.get('_candidate_evidence_publications')
            base=owner._verify_revision(doc,current['saved_revision'])
            assert current['draft']==base['draft'] or current['dirty']
            # Actual explicit save handles formerly pending evidence as data.
            current=command(wb,current,'document.save')
            refs=[]
            for row in current.get('candidate_evidence',[]):
                path=owner._folder(doc)/'revisions'/row['retained_revision']/'candidate_evidence'/(row['id']+'.json')
                if row['id'] in request.get('evidence_hashes',{}):
                    assert file_hash(path)==request['evidence_hashes'][row['id']]
                refs.append(exact_ref(wb,doc,row))
            view=read_candidate_detail(owner,doc,request['fit_job'],request['candidate_id'],attempt_job_id=request.get('detail_job'))
            assert canonical_hash(owner.result(doc,request['fit_job']))==request['result_hash']
            assert view['source']['document_id']==doc
            assert view['execution_source']['document_id']==request['document_id']
            if 'original_frozen' in request:
                assert canonical_hash(view['fit_input'])==request['original_frozen']
                assert canonical_hash(view['original_plan'])==request['original_plan']
            # Missing successful details are neither success evidence nor a
            # recorded failure. Preserve the metadata and prove both gates.
            selected_view = view
            selected_candidate = request['candidate_id']
            purpose = evidence.SUCCESS
            metadata_only = not request.get('detail_job')
            if metadata_only:
                args=dict(source=view['source'],candidate_id=selected_candidate,attempt_job_id=None)
                for prohibited in (evidence.SUCCESS,evidence.FAILURE):
                    with pytest.raises(evidence.DetailEvidenceBlocked):
                        evidence.prepare_candidate_evidence(owner,**args,purpose=prohibited)
                metadata={'kind':'result',**view['source'],'selection':{'metadata_only':True,'candidate_ids':[selected_candidate]}}
                metadata_report=wb.report_documents.open(title='미보존 상세의 원 메타데이터')
                metadata_binding=wb.report_documents.capture(metadata_report['id'],metadata)
                metadata_content=wb.report_documents.asset(metadata_report['id'],metadata_binding)['content']
                assert metadata_content['success_judgment_permitted'] is False
                failed=next((c['candidate_id'] for c in owner.result(doc,request['fit_job'])['candidates']
                             if c['execution_status']=='FAILED'),None)
                if failed is None:
                    # Some real fits have no failed candidate. Metadata is all
                    # their original record can support; never invent one.
                    save(wb,metadata_report)
                    assert calls==[] and wb.manager.list()==[]
                    return dict(status='PASSED',case=request['case'],detail_read=True,missing_detail_preserved=True,
                        report_intent='METADATA_ONLY_NOT_A_SUCCESS_JUDGMENT',adopted=False,
                        evaluator_and_dispatch_calls=calls,jobs_on_reopen=0)
                selected_candidate=failed
                selected_view=read_candidate_detail(owner,doc,request['fit_job'],failed)
                purpose=evidence.FAILURE
            # New explicit C2 scope/savehook, not a retry of the origin command.
            result=owner.command(doc,evidence.CAPTURE,dict(source=selected_view['source'],candidate_id=selected_candidate,
                attempt_job_id=selected_view['attempt_job_id'],purpose=purpose),session_id=wb.session_id,
                expected_generation=owner.read(doc)['generation'],command_id='CcoldExplicitCapture'+uuid.uuid4().hex)
            ref=result['reference']
            resolved=evidence.resolve_candidate_evidence(owner,ref,consumer='success_report' if purpose==evidence.SUCCESS else 'failure_report')
            assert resolved['readiness']['success_judgment_permitted']==(purpose==evidence.SUCCESS)
            if purpose==evidence.FAILURE:
                with pytest.raises(evidence.DetailEvidenceBlocked):evidence.resolve_candidate_evidence(owner,ref,consumer='adoption')
            payload=evidence.candidate_report_payload(owner,ref)
            report=wb.report_documents.open(title='원 증거 이동 보고서')
            binding=wb.report_documents.capture(report['id'],ref)
            draft=deepcopy(report['draft']);draft['sections']=[dict(id='Soriginal',title='원 후보 증거',text='',
                include=True,table=True,curve=True,asset=binding)]
            report=command(wb,report,'report.update',{'draft':draft});report=save(wb,report)
            assert wb.report_documents.content(report['id'],[binding])['assets'][0]['source_status']=='AVAILABLE'
            comparison=None
            if purpose==evidence.SUCCESS:
                other=next((r for r in refs if r['candidate_id']!=ref['candidate_id']),ref)
                comparison=evidence.compare_selected_candidate_evidence(owner,ref,other,resolved['snapshot']['scope'][0]['experiment_id'])
                assert comparison['engineering_release']=='NOT_RELEASED'
            adopted=False
            if request.get('material_id') and adopt:
                mid=identities[request['material_id']]; target=wb.material_documents.read(mid)
                preview=evidence.candidate_adoption_preview(owner,ref)
                stale=dict(material_document_id=mid,session_id=wb.session_id,
                    expected_generation=target['generation']+1,command_id='CstaleMustReject',detail_evidence=ref)
                with pytest.raises(ValueError):wb.desktop.adopt(doc,request['fit_job'],request['candidate_id'],**stale)
                assert wb.material_documents.read(mid)['draft']==target['draft']
                wb.desktop.adopt(doc,request['fit_job'],request['candidate_id'],material_document_id=mid,
                    session_id=wb.session_id,expected_generation=target['generation'],command_id='CcoldAdopt',detail_evidence=ref)
                target=wb.material_documents.read(mid)
                assert target['draft']==preview['proposed_draft']
                save(wb,target)
                adopted=True
            # Undo resumes the acknowledged editor independently of frozen runs.
            current=owner.read(doc);before=deepcopy(current['draft']); draft=deepcopy(before)
            if draft.get('mode')=='request':draft['request']['purpose']+=' 사본 편집'
            else:draft['count']+=1
            current=command(wb,current,'numerical.update',{'draft':draft})
            current=command(wb,current,'document.undo')
            assert current['draft']==before
            save(wb,current)
            copied_path=None
            if recopy:
                chosen=[r['document_id'] for r in manifest['documents']]
                copied_path=str(Path(folder).parent/('다시 이동 '+uuid.uuid4().hex[:8]))
                copied(wb,chosen,copied_path,'Crecopy'+uuid.uuid4().hex)
            assert calls==[] and wb.manager.list()==[]
            return dict(status='PASSED',case=request['case'],document_id=doc,reference=ref,report_id=report['id'],
                report_binding=binding,report_intent=payload['report_intent'],comparison=bool(comparison),adopted=adopted,
                raw_evidence_bytes_preserved=True,original_result_hash=request['result_hash'],
                jobs_on_reopen=0,evaluator_and_dispatch_calls=calls,recopy=copied_path,
                engineering_release='NOT_RELEASED',holdout_acceptance='NOT_ASSESSED')
    finally: wb.shutdown()


def run_cold(folder, request, output, *, adopt=True, recopy=True):
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    save_json(output/'request.json',request)
    args=[sys.executable,'-X','utf8','-m','examples.portable_connection_c2_public','--cold',str(folder),
        '--request',str(output/'request.json'),'--result',str(output/'result.json')]
    if not adopt:args+=['--no-adopt']
    if not recopy:args+=['--no-recopy']
    p=subprocess.run(args,cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True,timeout=100)
    (output/'stdout.log').write_text(p.stdout,encoding='utf8');(output/'stderr.log').write_text(p.stderr,encoding='utf8')
    save_json(output/'process.json',{'command':args,'exit_code':p.returncode,'platform':sys.platform})
    assert p.returncode==0,p.stderr
    return load_json(output/'result.json')


def persisted_check(folder, previous=None):
    """Second process: exact saved evidence/report/adoption are still readable."""
    from caelab.connection_graph import build_graph
    with cold_guard() as calls:
        wb=open_project(folder)
        try:
            documents=wb.documents()['documents']; refs=[];reports=[];adoptions=[]
            for document in documents:
                if document['kind']=='numerical':
                    for row in document.get('candidate_evidence',[]):
                        if row.get('retained_revision'):
                            ref=exact_ref(wb,document['id'],row)
                            evidence.resolve_candidate_evidence(wb.numerical_documents,ref)
                            refs.append(ref)
                elif document['kind']=='material':
                    for adopted in document.get('adoptions',[]):
                        if adopted.get('candidate_evidence'):
                            evidence.resolve_candidate_evidence(wb.numerical_documents,adopted['candidate_evidence'],consumer='adoption')
                            adoptions.append(adopted['candidate_evidence'])
            if previous:
                report_id=previous.get('report_id'); binding=previous.get('report_binding')
                if report_id and binding:
                    asset=wb.report_documents.content(report_id,[binding])['assets'][0]
                    assert asset['source_status']=='AVAILABLE'
                    reports.append(report_id)
                evidence.resolve_candidate_evidence(wb.numerical_documents,previous['reference'])
            selected=[d['id'] for d in documents if d['kind'] in ('data','material','numerical')]
            graph=build_graph(wb,selected,include_history=True)
            broken=[n for n in graph['nodes'] if n['status']=='BROKEN']
            assert not broken,broken
            assert wb.manager.list()==[]
            return dict(status='PASSED',evidence_count=len(refs),reports=reports,adoptions=len(adoptions),
                        graph_broken=0,jobs_on_reopen=0,evaluator_and_dispatch_calls=calls)
        finally:wb.shutdown()
