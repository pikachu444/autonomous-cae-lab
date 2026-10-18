"""Retained-only cold read, explicit cancelled/accepted adoption, original return."""
from contextlib import ExitStack
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from test_numerical_evaluation_workflow import wait,Popups


def main(store,folder,pareto_record,read_only=None):
    from PySide6.QtCore import QThreadPool
    from PySide6.QtWidgets import QApplication
    from scipy.interpolate import RBFInterpolator
    from apps.research.request_plan_window import RequestPlanWindow
    from apps.research.reference_window import ReferenceWindow
    from apps.research.evaluation_window import EvaluationWindow
    from apps.research import desktop
    from examples.s1_windows_transfer import local_service
    from caelab.storage import canonical_hash
    from caelab.evaluation_definition import document_reference

    folder=Path(folder).resolve();folder.mkdir(parents=True,exist_ok=False)
    record=json.loads(Path(pareto_record).read_text(encoding='utf-8'))
    app=QApplication.instance() or QApplication([]);windows=[];processes=[];launches=[];calls=[]
    def forbidden(*args,**kwargs):calls.append('solve/fit/predict');raise AssertionError('Cold read/adoption must not calculate')
    with local_service(Path(store).resolve()) as (wb,client),ExitStack() as stack:
        jobs_before={item['id'] for item in wb.manager.list()}
        stack.enter_context(patch.object(wb,'submit',forbidden))
        stack.enter_context(patch.object(RBFInterpolator,'__init__',forbidden))
        stack.enter_context(patch.object(RBFInterpolator,'__call__',forbidden))
        original_popen=desktop.subprocess.Popen
        def popen(*args,**kwargs):
            process=original_popen(*args,**kwargs);processes.append(process);return process
        stack.enter_context(patch.object(desktop.subprocess,'Popen',popen))
        actual_open_saved=desktop.open_saved_reference
        def open_saved(*args,**kwargs):
            receipt=actual_open_saved(*args,**kwargs);launches.append(receipt);return receipt
        stack.enter_context(patch.object(desktop,'open_saved_reference',open_saved))
        window=RequestPlanWindow(client,document_id=record['reference']['document_id'],poll_interval=0)
        windows.append(window);window.show();popups=Popups(app,folder)
        def settled(predicate=lambda:True):
            wait(app,lambda:not window._busy and not window._callbacks and not window._pending_adoption
                and not getattr(window,'_retained_labels_scheduled',False) and predicate(),lambda:window.message.text())
            assert not popups.errors,popups.errors
        try:
            settled(lambda:window.document is not None);job=record['reference']['job_id']
            window.retry_result();settled(lambda:job in window._result_cache)
            assert canonical_hash(window._result_cache[job])==record['reference']['result_sha256']
            source=deepcopy(record['input']['model_source'])
            original=client.research_reference({**source,'kind':'document','document_kind':'evaluation'})['document']
            original_stage=original['draft']['stages'][0]['source']
            stage_before=client.document_read(original_stage['document_id'])
            window.candidates.selectRow(1);app.processEvents();selected=deepcopy(window._selected_actual_candidate())
            assert selected and selected['values']['cooling_rate']!=.75
            before=canonical_hash(original['draft'])
            if not read_only:
                popups.add('후보 입력 채택 검토','cancel','adoption-cancel')
                window.pde_adopt_button.click();settled(lambda:not popups.pending)
                assert canonical_hash(client.document_read(original['id'])['draft'])==before
                popups.add('후보 입력 채택 검토',0,'adoption-accept')
                window.pde_adopt_button.click();settled(lambda:not popups.pending and len(processes)>0)
            changed=client.document_read(original['id'])
            assert canonical_hash(changed['draft'])!=before
            branch_ref=changed['draft']['stages'][0]['source']
            assert branch_ref['document_id']!=original_stage['document_id']
            branch=client.document_read(branch_ref['document_id'])
            assert branch['draft']['settings']['parameters'][0]['value']==selected['values']['cooling_rate']
            assert client.document_read(stage_before['id'])['draft']==stage_before['draft']
            # Actual source action launches the existing retained-reference process.
            window.model_open_button.click();settled(lambda:bool(launches))
            assert launches[0]['reference']['saved_revision']==source['saved_revision']
            assert all(process.poll() is None for process in processes)
            reference={**source,'kind':'document','document_kind':'evaluation'}
            retained=ReferenceWindow(client,reference);windows.append(retained);retained.show()
            wait(app,lambda:not retained._busy and retained.value is not None)
            assert retained.value['document']['draft']==original['draft']
            assert retained.grab().save(str(folder/'saved-evaluation-before-adoption.png'))
            current=EvaluationWindow(client,document_id=original['id'],poll_interval=0);windows.append(current);current.show()
            wait(app,lambda:not current._busy and not current._callback_calls and current.document is not None)
            assert current.document['draft']['stages'][0]['source']==branch_ref
            current.save_button.click()
            wait(app,lambda:not current._busy and not current._callback_calls and not current.document['dirty'])
            assert current.grab().save(str(folder/'original-evaluation-after-adoption.png'))
            # Read exact local-RBF and confirmation results in this separate process.
            cold=[]
            for doc_id,old_job in (
                ('N0d48bf017e9e4156bb465d13bbf53244','Jba226b468bb1442cbbdf876590e422bf'),
                ('Ne0e18c4cb7ce429180a326cbcabda6f0','J2bb1cee69cd942059cc6598c26c8c77d')):
                old_ref=client.document_result_reference(doc_id,old_job)
                window.open_document(document_id=doc_id);settled(lambda:window.document['id']==doc_id)
                window.retry_result();settled(lambda:old_job in window._result_cache)
                assert canonical_hash(window._result_cache[old_job])==old_ref['result_sha256']
                cold.append(old_ref)
            assert not calls
            assert {item['id'] for item in wb.manager.list()}==jobs_before
            result={'selected_candidate':selected['candidate_id'],'selected_values':selected['values'],
                'plan_result_reference':record['reference'],'old_source':source,
                'adopted_source':document_reference(client.document_read(original['id'])),'new_stage_source':branch_ref,
                'original_stage_unchanged':True,'cancel_preserved':True,'retained_reads':cold,'launches':launches,
                'solve_fit_predict_calls':0,'new_jobs':0,'qt_platform':app.platformName(),
                'source_hashes':{p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in (
                    'apps/research/numerical_window.py','apps/research/request_plan_window.py',
                    'apps/research/numerical_methods.py','apps/research/desktop.py','caelab/workbench.py')}}
            (folder/'finish.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
            print(json.dumps(result,ensure_ascii=False),flush=True)
        finally:
            popups.timer.stop()
            for item in reversed(windows):
                if hasattr(item,'_allow_close'):item._allow_close=True
                item.close()
            app.processEvents();assert QThreadPool.globalInstance().waitForDone(5000)
            for process in processes:
                if process.poll() is None:process.terminate()
                process.wait(timeout=5)


if __name__=='__main__':main(*sys.argv[1:])
