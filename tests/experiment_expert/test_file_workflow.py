"""Actual CSV Data owner → explicit analytic Plan → Study/Report → cold reopen."""
from copy import deepcopy
import shutil
import pytest
from caelab.storage import canonical_hash
from caelab.experiment_analysis_service import uncertainty_request,source_problem,final_request
from caelab.experiment_analysis_reporting import blocks,study_draft,suggested_questions
from caelab.report_document import default_draft as report_draft
from .support import ServiceHost
from .test_uncertainty import calibration,spec
from .test_service import algebra_registered
from .test_final_diagnosis import direct_problem


def import_source(h):
    raw=h.core.upload('전압.csv',b't,v\n0,0.001\n1,0.002\n2,0.004\n3,0.005\n4,0.006\n')
    cert=h.core.upload('공개 교정서.txt',b'Public synthetic calibration, not instrument evidence')
    recipe=calibration();recipe['source']={'data_id':cert['id'],'name':cert['name'],'sha256':cert['sha256']}
    mapping={'delimiter':',','skip_header':1,'columns':{'force':{'column':1,'unit':'N','component':'z',
        'location':'gauge_A','measure':'force','frame':'lab','axis':{'column':0,'name':'time','unit':'s'},
        'calibration':recipe,'row_selection':{'display_hidden_rows':[3]}}}}
    d=h.data.open(title='힘 시험',draft={'data_id':raw['id'],'mapping':mapping})
    receipt=h.command(d['id'],'data.import');job=receipt['job']['id']
    status=h.wait(job);assert status['state']=='SUCCEEDED',status
    h.save(d['id'])
    source={'kind':'result_response','reference':h.core.document_result_reference(d['id'],job),'response':'force'}
    return d['id'],job,source


def capture(h,doc,job):
    reference=h.core.document_result_reference(doc,job)
    report=h.reports.open()
    asset=h.core.report_capture(report['id'],{'kind':'result',**reference})
    draft=report_draft();draft['title']='시험과 판단'
    draft['sections']=[{'id':'Eexperiment','title':'원 시험과 명시 분석','text':'공학 승인 아님',
        'include':True,'table':True,'curve':True,'asset':asset}]
    h.command(report['id'],'report.update',{'draft':draft});h.save(report['id'])
    return report['id'],asset


def test_file_calibration_uq_study_report_cold_reopen_without_source_or_calls(tmp_path):
    root=tmp_path/'wb'
    with ServiceHost(root) as h:
        data,original,source=import_source(h)
        before=canonical_hash(h.data.result(data,original))
        problem=source_problem(h.core,{'source':source})
        req=uncertainty_request(source,spec(problem),plan_mask=[True,False,True])
        plan,job,r=h.run_plan(req)
        assert r['execution_status']=='SUCCEEDED',r
        a=r['experiment_analysis'];assert a['source_problem']['calibration_reapplied'] is False
        assert [row['status'] for row in a['rows']]==['COMPUTED_FIRST_ORDER','EXCLUDED','COMPUTED_FIRST_ORDER','EXCLUDED','EXCLUDED']
        assert a['source_problem']['supplied_output_uncertainty']['k'] is None
        assert canonical_hash(h.data.result(data,original))==before
        h.save(plan);reference=h.core.document_result_reference(plan,job)
        questions=suggested_questions(r)
        draft=study_draft(r,reference,question='어떤 시험 정보를 보강할 것인가?',selected_questions=questions)
        study=h.study.open(draft=draft);h.save(study['id'])
        report,asset=capture(h,plan,job)
        content=h.core.report_content(report,[asset])['assets'][0]['content']['result']
        assert content['experiment_analysis']['source_problem']['values']==[.5,2.5,6.5,8.5,10.5]
        assert any(k=='curve' for k,v in blocks(content))
        original_digest=canonical_hash(content)
        total=len(h.manager.list())
    # Source upload and volatile run result dirs removed; saved owner revisions
    # and report assets must supply reads. This is NOT a source availability claim.
    shutil.rmtree(root/'inputs');shutil.rmtree(root/'results')
    with ServiceHost(root) as cold:
        assert canonical_hash(cold.core.report_content(report,[asset])['assets'][0]['content']['result'])==original_digest
        assert cold.study.read(study['id'])['draft']['next_observations']==draft['next_observations']
        assert cold.owner.result(plan,job)['experiment_analysis']['source_problem']['values']==[.5,2.5,6.5,8.5,10.5]
        assert len(cold.manager.list())==total


def test_bad_or_unknown_uncertainty_is_retained_not_silently_completed(tmp_path):
    with ServiceHost(tmp_path) as h:
        _,_,source=import_source(h);p=source_problem(h.core,{'source':source})
        provided=spec(p);provided['dependence']={'kind':'UNKNOWN'}
        doc,job,r=h.run_plan(uncertainty_request(source,provided))
        assert r['execution_status']=='REJECTED' and all(row['standard_uncertainty'] is None for row in r['experiment_analysis']['rows'])
        h.save(doc);report,asset=capture(h,doc,job)
        assert h.core.report_content(report,[asset])['assets'][0]['content']['result']['execution_status']=='REJECTED'
        provided=spec(p);provided['uncertainties']['a']['value']=-1
        doc,job,r=h.run_plan(uncertainty_request(source,provided))
        assert r['execution_status']=='REJECTED' and r['experiment_analysis']['source_problem']['values']==p['values']
        assert r['timing']['model_calls']==0
        assert '음수' in r['failure_reason']
        h.save(doc)


def test_final_diagnostic_report_rechecks_exact_success_gate(tmp_path,algebra_registered,monkeypatch):
    with ServiceHost(tmp_path) as h:
        _,_,reference=h.original(direct_problem())
        plan,job,r=h.run_plan(final_request(reference,evaluations=9));h.save(plan)
        report,asset=capture(h,plan,job)
        assert h.core.report_content(report,[asset])['assets'][0]['content']['result']['identification']['status']=='LOCAL_RANK_COMPLETE'
        import caelab.numerical_candidate_evidence as evidence
        original=evidence.resolve_candidate_evidence
        def reject(owner,ref,*,consumer='read'):
            if consumer=='success_report':raise ValueError('required fit/holdout detail unavailable')
            return original(owner,ref,consumer=consumer)
        monkeypatch.setattr(evidence,'resolve_candidate_evidence',reject)
        with pytest.raises(ValueError,match='detail unavailable'):capture(h,plan,job)
        # Already frozen report remains readable; no retroactive replacement.
        assert h.core.report_content(report,[asset])['assets'][0]['content']['result']['identification']['status']=='LOCAL_RANK_COMPLETE'


def test_bounded_expert_summary_retains_unknown_and_partial_scope_without_replacing_raw(tmp_path):
    from caelab.experiment_analysis_reporting import expert_summary
    from caelab.experiment_uncertainty import calibration_problem,propagate
    from .test_uncertainty import imported
    import json
    problem=calibration_problem(imported(tmp_path)['responses']['force'])
    raw=propagate(problem,spec(problem));digest=canonical_hash(raw)
    summary=expert_summary(raw)
    assert len(json.dumps(summary,ensure_ascii=False).split())<400
    assert summary['measurement_uncertainty']=='UNKNOWN' and summary['engineering_release']=='NOT_RELEASED'
    assert summary['preview_rows'][0]['original_value']==.5
    assert summary['source_result_sha256']==digest and canonical_hash(raw)==digest
    assert expert_summary({'kind':'unrelated_result'}) is None
