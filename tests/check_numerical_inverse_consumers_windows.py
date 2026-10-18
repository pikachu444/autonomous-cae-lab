"""Retained inverse evidence -> adoption/Study/Report; never evaluates a model."""
from contextlib import ExitStack
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from test_numerical_evaluation_workflow import wait


DOC='Nfddaddc8b86b4d17b447f1af66ddc58a'
JOB='Ja05c8a958ad94c31a0619ff1dcb0e0c9'
CANDIDATE='C000015'


def main(store, folder, cold_record=None):
    from PySide6.QtCore import QThreadPool, QTimer
    from PySide6.QtWidgets import QApplication, QMessageBox
    from scipy.interpolate import RBFInterpolator
    from unittest.mock import patch
    from examples.s1_windows_transfer import local_service
    from apps.research.numerical_window import NumericalWindow
    from apps.research.study_window import StudyWindow
    from apps.research.report_window import ReportWindow
    from caelab.storage import canonical_hash
    from caelab.study_document import default_draft
    from apps.research.numerical_candidate_evidence_report import candidate_evidence_blocks

    folder=Path(folder).resolve();folder.mkdir(parents=True,exist_ok=False)
    app=QApplication.instance() or QApplication([]);windows=[];calls=[];answers=[];dialogs=[]
    def forbidden(*args,**kwargs):
        calls.append('solve/fit/predict');raise AssertionError('Retained inverse inspection attempted calculation')
    def answer():
        box=app.activeModalWidget()
        if not isinstance(box,QMessageBox) or not answers:return
        accept=answers.pop(0)
        dialogs.append({'title':box.windowTitle(),'text':box.text(),'accepted':accept})
        assert box.grab().save(str(folder/('adoption-accept.png' if accept else 'adoption-cancel.png')))
        box.button(QMessageBox.StandardButton.Yes if accept else QMessageBox.StandardButton.Cancel).click()
    timer=QTimer();timer.setInterval(20);timer.timeout.connect(answer);timer.start()
    with local_service(Path(store).resolve()) as (wb,client),ExitStack() as stack:
        before={j['id'] for j in wb.manager.list()}
        for target in (wb,wb.manager):stack.enter_context(patch.object(target,'submit',forbidden))
        stack.enter_context(patch.object(RBFInterpolator,'__init__',forbidden))
        stack.enter_context(patch.object(RBFInterpolator,'__call__',forbidden))
        result_hash=canonical_hash(client.document_result(DOC,JOB))
        def ready(window,predicate=lambda:True):
            wait(app,lambda:not window._busy and not getattr(window,'_callbacks',[]) and
                 not getattr(window,'_workers',[]) and predicate(),lambda:window.message.text())
        try:
            plan=NumericalWindow(client,document_id=DOC,poll_interval=0);windows.append(plan);plan.show()
            ready(plan,lambda:plan.document is not None)
            plan.runs.selectRow(next(i for i,r in enumerate(plan.document['runs']) if r['job_id']==JOB))
            plan.retry_result();ready(plan,lambda:JOB in plan._result_cache)
            plan.candidates.selectRow(next(i for i,r in enumerate(plan._result_cache[JOB]['candidates']) if r['candidate_id']==CANDIDATE))
            plan.candidate_detail_button.click();detail=plan._candidate_detail_windows[-1];windows.append(detail)
            wait(app,lambda:detail.view is not None and detail._read_worker is None);detail.timer.stop()
            original=client.document_read(detail.view['fit_input']['material']['document_id']) if 'material' in detail.view['fit_input'] else client.document_read(plan._material['document_id'])
            original_hash=canonical_hash(original['draft'])
            if cold_record:
                retained=json.loads(Path(cold_record).read_text(encoding='utf-8'));reference=retained['evidence_reference']
                assert canonical_hash(original['draft'])==retained['adopted_material_draft_sha256']
                read=client.numerical_evidence_command(DOC,'numerical.evidence.read',
                    {'reference':reference,'consumer':'success_report'})['evidence']
                assert read['readiness']['success_judgment_permitted']
                study_id,report_id=retained['study_id'],retained['report_id']
                cold_consumer_hashes={identifier:canonical_hash(client.document_read(identifier)['draft'])
                    for identifier in (study_id,report_id)}
            else:
                detail.evidence_button.click()
                wait(app,lambda:not detail._writing and detail._evidence_reference is not None)
                reference=deepcopy(detail._evidence_reference)
                # CAPTURE may save the Numerical owner. Refresh its existing view before adoption.
                plan.refresh_document();ready(plan)
                assert plan.selected_candidate()==CANDIDATE
                answers.append(False);detail.evidence_adopt_button.click()
                ready(plan,lambda:len(dialogs)==1 and not answers and not plan._pending_adoption)
                assert canonical_hash(client.document_read(original['id'])['draft'])==original_hash
                answers.append(True);detail.evidence_adopt_button.click()
                ready(plan,lambda:len(dialogs)==2 and not answers and not plan._pending_adoption)
                adopted=client.document_read(original['id'])
                assert adopted['draft']['settings']['parameters']==detail.view['candidate']['values']
                if adopted['adoptions'][-1]['candidate_evidence']!=reference:
                    diagnostic={'message':plan.message.text(),'error':plan.message.toolTip(),'calls':calls,
                        'pending':plan._adoption_receipt['request'],'reference':reference}
                    (folder/'adoption-failure.json').write_text(json.dumps(diagnostic,ensure_ascii=False,indent=2),encoding='utf-8')
                    assert 'Material changed after this Plan was bound' in diagnostic['error'] and not calls
                    assert canonical_hash(adopted['draft'])==original_hash
                    reference=deepcopy(adopted['adoptions'][-1]['candidate_evidence'])
                    assert reference['source']==detail.view['source'] and reference['candidate_id']==CANDIDATE
                    assert client.numerical_evidence_command(DOC,'numerical.evidence.read',
                        {'reference':reference,'consumer':'adoption'})['evidence']['readiness']['success_judgment_permitted']
                material=plan.open_material();windows.append(material)
                wait(app,lambda:material.document is not None and not material._busy)
                material.timer.stop()
                material.save_document();wait(app,lambda:not material._busy and not material.document['dirty'])
                assert material.document['draft']==adopted['draft']
                assert material.grab().save(str(folder/'original-material-after-explicit-adoption.png'))
                report=ReportWindow(client,reference=reference);windows.append(report);report.show()
                ready(report,lambda:report.document is not None and len(report.draft['sections'])>0 and bool(report.assets))
                report.save_document();ready(report,lambda:not report.document['dirty'])
                report_id=report.document['id']
                draft=default_draft();draft['question']='동일 보존 후보의 피팅·별도 확인 잔차가 일관되는가?'
                draft['evidence']=[dict(id='Eselectedfit',label='두 시험 피팅과 별도 확인',kind='result',reference=reference,
                    note='공개 합성 관측과 선형 FELUPE. 물성 또는 Case A/B 공학 승인은 미확인.')]
                study_doc=client.document_open(kind='study',title='역해석 보존 후보 확인',draft=draft)
                study_id=study_doc['id']
            report=next((w for w in windows if isinstance(w,ReportWindow)),None)
            if report is None:
                report=ReportWindow(client,document_id=report_id);windows.append(report);report.show()
            ready(report,lambda:report.document is not None and bool(report.assets))
            assets=list(report.assets.values());payload=next(a['content'] for a in assets if 'candidate_evidence' in a.get('content',{}))
            assert payload['candidate_evidence']['reference']==reference
            blocks=list(candidate_evidence_blocks(payload))
            assert any(kind=='table' for kind,_ in blocks) and any(kind=='curve' for kind,_ in blocks)
            study=StudyWindow(client,document_id=study_id,poll_interval=0);windows.append(study);study.show()
            ready(study,lambda:study.document is not None)
            study.evidence.selectRow(0);app.processEvents()
            ready(study,lambda:study._content_pending is None and not study._content_queued)
            study.check_references();ready(study,lambda:bool(study._reference_checks))
            assert next(iter(study._reference_checks.values()))['status']=='AVAILABLE'
            assert study.edited_draft()['evidence'][0]['reference']==reference
            if not cold_record:
                study.save_document();ready(study,lambda:not study.local_dirty and not study.document['dirty'])
            # Holdout is explicitly separate from the optimizer residual vector.
            holdout=next(i for i,t in enumerate(detail.view['trials']) if t['role']=='holdout')
            detail.trials.setCurrentItem(detail.trials.topLevelItem(holdout));app.processEvents()
            assert '목적함수에서 제외' in detail.residual_summary.text()
            for width,height in ((1440,900),(1100,780)):
                for name,window in [('candidate-holdout',detail),('same-evidence-study',study),('same-evidence-report',report)]:
                    window.resize(width,height);app.processEvents()
                    if hasattr(window,'canvas'):window.canvas.draw()
                    assert window.grab().save(str(folder/f'{name}-{width}.png'))
            assert canonical_hash(client.document_result(DOC,JOB))==result_hash
            assert {j['id'] for j in wb.manager.list()}==before and not calls
            consumer_hashes={identifier:canonical_hash(client.document_read(identifier)['draft'])
                for identifier in (study_id,report_id)}
            if cold_record:
                assert consumer_hashes==cold_consumer_hashes
                if 'consumer_draft_sha256' in retained:assert consumer_hashes==retained['consumer_draft_sha256']
            record=dict(document_id=DOC,job_id=JOB,candidate_id=CANDIDATE,evidence_reference=reference,
                result_sha256=result_hash,material_document_id=original['id'],study_id=study_id,report_id=report_id,
                original_material_draft_sha256=original_hash,
                adopted_material_draft_sha256=canonical_hash(client.document_read(original['id'])['draft']),
                adoption_dialogs=dialogs,cold=bool(cold_record),new_jobs=0,solve_fit_predict_submissions=0,
                prior_explicit_adoption_preserved=True,repeated_adoption_blocked=not bool(cold_record),
                consumer_draft_sha256=consumer_hashes,
                study_release=study.edited_draft()['engineering_release'],
                evidence_readiness=payload['candidate_evidence']['readiness'],
                source_hashes={p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in (
                    'apps/research/numerical_window.py','apps/research/request_plan_window.py',
                    'apps/research/numerical_candidate_detail_window.py','apps/research/study_window.py',
                    'apps/research/report_pages.py','caelab/numerical.py','caelab/numerical_candidate_evidence.py')})
            (folder/'finish.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
            print(json.dumps(record,ensure_ascii=False),flush=True)
        finally:
            timer.stop()
            for window in reversed(windows):
                if hasattr(window,'_allow_close'):window._allow_close=True
                window.close()
            app.processEvents();assert QThreadPool.globalInstance().waitForDone(5000)


if __name__=='__main__':main(*sys.argv[1:])
