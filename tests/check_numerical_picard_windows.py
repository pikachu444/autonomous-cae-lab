"""One original S2 Picard definition and one deliberately bounded failed Plan.

This is not the retained 120-dispatch DE campaign or a new qualification.
"""
from copy import deepcopy
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from test_numerical_evaluation_workflow import wait


def main(folder,retained_store=None,retained_definition=None,retained_failure_plan=None):
    from PySide6.QtCore import QThreadPool
    from PySide6.QtWidgets import QApplication
    from apps.research.evaluation_window import EvaluationWindow
    from apps.research.request_plan_window import RequestPlanWindow
    from examples.s1_windows_transfer import local_service,command
    from examples.s2_mdo_adjoint import create_definition,declarations
    from caelab.evaluation_definition import document_reference
    from caelab.numerical_document import request_draft
    from caelab.storage import canonical_hash
    from caelab.jobs import TERMINAL

    folder=Path(folder).resolve();folder.mkdir(parents=True,exist_ok=False)
    app=QApplication.instance() or QApplication([])
    with local_service(Path(retained_store) if retained_store else folder/'store') as (wb,client):
        if retained_store:
            definition=client.document_open(kind='evaluation',document_id=retained_definition)
            _,_,request=declarations('mdo')
            request['inputs']['settings']={'definition_ref':document_reference(definition)}
        else:definition,request,inspection=create_definition(client,'mdo')
        window=EvaluationWindow(client,document_id=definition['id'],poll_interval=0)
        window.show();plan=None
        def settled(predicate=lambda:True):
            wait(app,lambda:not window._busy and not window._callback_calls and predicate(),lambda:window.message.text())
        try:
            settled(lambda:window.document is not None and window.run_button.isEnabled())
            before=len(wb.manager.list())
            if not retained_store:window.run_button.click();settled(lambda:bool(window.document['runs']))
            job=window.document['runs'][-1]['job_id']
            wait(app,lambda:client.status(job)['state'] in {'SUCCEEDED','FAILED','REJECTED'},lambda:str(client.status(job)),timeout=240)
            result=client.document_result(definition['id'],job)
            assert result['execution_status']=='SUCCEEDED',result['diagnostics']
            assert result['stage_execution_count']==12,result['stage_execution_count']
            assert result['diagnostics']['convergence_status']=='CONVERGED'
            definition=command(client,client.document_read(definition['id']),'document.save')['document']
            (folder/'direct.json').write_text(json.dumps({'document':definition,'job_id':job,'result':result},ensure_ascii=False,indent=2),encoding='utf-8')
            window.refresh_document();settled();window.refresh_progress();settled(lambda:window.attempts.rowCount()>0)
            window.attempts.selectRow(window.attempts.rowCount()-1);settled(lambda:window._result is not None)
            assert window._result['execution_status']=='SUCCEEDED'
            app.processEvents();assert window.grab().save(str(folder/'picard-direct.png'))
            # A separate definition deliberately ends after one iteration. Original
            # convergence tolerances and successful definition remain unchanged.
            if retained_failure_plan:
                old_plan=client.document_read(retained_failure_plan)
                failed=client.document_read(old_plan['draft']['model_source']['document_id'])
            else:
                failed=deepcopy(definition['draft']);failed['iteration']['maximum']=1
                failed=client.document_open(kind='evaluation',title='반복 미수렴의 목적 제외',draft=failed)
                failed=command(client,failed,'document.save')['document']
            request=deepcopy(request);request['purpose']='미수렴 후보의 목적 제외 확인'
            request['inputs']['settings']={'definition_ref':document_reference(failed)}
            request['inputs']['execution']={'on_failure':'stop'}
            # Existing public admission requires the minimum DE population plan.
            # on_failure=stop still dispatches only the first failed 2-stage row.
            request['budget']['evaluations']=10
            draft=request_draft(request,source=document_reference(failed));draft['model_source']=document_reference(failed)
            plan=RequestPlanWindow(client,auto_open=False,poll_interval=0);plan.show()
            if retained_failure_plan:plan.open_document(document_id=retained_failure_plan)
            else:plan.open_document(title=request['purpose'],draft=draft)
            def plan_settled(predicate=lambda:True):
                wait(app,lambda:not plan._busy and not plan._callbacks and predicate(),lambda:plan.message.text())
            plan_settled(lambda:plan.document is not None);assert plan.run_button.isEnabled(),plan.document['diagnostics']
            if not retained_failure_plan:plan.run_button.click();plan_settled(lambda:bool(plan.document['runs']))
            failed_job=plan.document['runs'][-1]['job_id']
            wait(app,lambda:client.status(failed_job)['state'] in TERMINAL,lambda:str(client.status(failed_job)),timeout=100)
            failed_result=client.document_result(plan.document['id'],failed_job)
            assert failed_result['best'] is None and len(failed_result['candidates'])==1
            candidate=failed_result['candidates'][0]
            assert candidate['objective'] is None and not candidate['feasible'] and candidate['responses']=={}
            assert all(value is None for value in candidate['constraint_residuals'])
            raw=client.numerical_evaluation_result(plan.document['id'],failed_job,candidate['candidate_id'],evaluation_index=0)
            assert raw['diagnostics']['convergence_status']=='NOT_CONVERGED' and raw['stage_execution_count']==2
            plan.refresh_document();plan_settled();plan.retry_result();plan_settled(lambda:failed_job in plan._result_cache)
            plan.save_document();plan_settled(lambda:not plan.document['dirty'])
            for width,height in ((1440,900),(1100,780)):
                plan.resize(width,height);app.processEvents();assert plan.grab().save(str(folder/f'picard-not-converged-{width}.png'))
            assert len(wb.manager.list())==before+(0 if retained_failure_plan else 1 if retained_store else 2)
            record={'direct_source':document_reference(definition),'direct_job':job,'direct_result_sha256':canonical_hash(result),
                'failed_source':document_reference(failed),'failed_plan':plan.document['id'],'failed_job':failed_job,
                'failed_result_sha256':canonical_hash(failed_result),'direct_dispatches':12,'failed_dispatches':2,
                'failed_candidate':candidate,'raw_failure':raw,'qualification':'UNKNOWN','qt_platform':app.platformName()}
            (folder/'picard.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
            print(json.dumps({k:v for k,v in record.items() if k not in {'failed_candidate','raw_failure'}},ensure_ascii=False),flush=True)
        finally:
            if plan:plan._allow_close=True;plan.close()
            window._allow_close=True;window.close();app.processEvents();assert QThreadPool.globalInstance().waitForDone(5000)


if __name__=='__main__':main(*sys.argv[1:])
