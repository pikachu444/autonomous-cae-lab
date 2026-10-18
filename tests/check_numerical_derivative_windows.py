"""Actual saved Plan/descriptor first contact, without solver or optimizer calls."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from test_numerical_evaluation_workflow import wait


def main(store,folder,document_id,job_id,edit_save=None):
    from PySide6.QtCore import QThreadPool,Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication,QComboBox
    from examples.s1_windows_transfer import local_service
    from apps.research.request_plan_window import RequestPlanWindow
    from caelab.storage import canonical_hash
    folder=Path(folder).resolve();folder.mkdir(parents=True,exist_ok=False)
    app=QApplication.instance() or QApplication([]);calls=[]
    def forbidden(*args,**kwargs):calls.append('submit');raise AssertionError('Saved derivative reads must not calculate')
    with local_service(Path(store).resolve()) as (wb,client),patch.object(wb.manager,'submit',forbidden),patch.object(wb,'submit',forbidden):
        jobs={row['id'] for row in wb.manager.list()};before=client.document_read(document_id)
        result=client.document_result(document_id,job_id);result_hash=canonical_hash(result)
        window=RequestPlanWindow(client,document_id=document_id,poll_interval=0);window.show()
        def settled(predicate=lambda:True):wait(app,lambda:not window._busy and not window._callbacks and predicate(),lambda:window.message.text())
        try:
            settled(lambda:window.document is not None)
            inputs=deepcopy(window.edited_draft()['request']['inputs'])
            descriptor=client.describe_inputs(inputs)
            window.check_adjoint_support();settled()
            support_message=window.message.text()
            dialog=window._derivative_support_windows[-1]
            support_profiles=deepcopy(dialog.content.profiles)
            for width in (1000,760):
                dialog.resize(width,540);app.processEvents();assert dialog.grab().save(str(folder/f'plan-method-support-{width}.png'))
            QTest.keyClick(dialog,Qt.Key.Key_Escape);app.processEvents()
            selection_change=None
            if edit_save:
                old=deepcopy(window.edited_draft());method=inputs.get('method')
                selected='differential_evolution' if method=='slsqp_adjoint' else 'slsqp_adjoint'
                window.input_panel_action.setChecked(True);window.input_tabs.setCurrentWidget(window.sheet)
                item=window.method_sheet.item(0,1);window.method_sheet.setCurrentItem(item)
                window.method_sheet.editItem(item);app.processEvents();editor=window.method_sheet.findChild(QComboBox)
                assert editor is not None;editor.setCurrentIndex(editor.findData(selected));QTest.keyClick(editor,Qt.Key.Key_Return);app.processEvents()
                assert window.edited_draft()['request']['inputs']['method']==selected
                window.check_adjoint_support();settled();dialog=window._derivative_support_windows[-1]
                assert dialog.grab().save(str(folder/'explicit-method-selection-support.png'))
                selection_change={'from':method,'to':selected,'support_message':window.message.text()}
                QTest.keyClick(dialog,Qt.Key.Key_Escape);app.processEvents()
                assert window.undo_inputs() and window.edited_draft()==old
                if edit_save=='edit-save':window.save_document();settled(lambda:not window.document['dirty'])
            window.runs.selectRow(next(i for i,r in enumerate(window.document['runs']) if r['job_id']==job_id))
            window.retry_result();settled(lambda:job_id in window._result_cache)
            assert canonical_hash(window._result_cache[job_id])==result_hash
            window.tabs.setCurrentWidget(window.gradient_evidence)
            if result.get('kind')=='experiment_identification':window.gradient_evidence.tabs.setCurrentIndex(5)
            elif result.get('gradient_verification'):window.gradient_evidence.tabs.setCurrentIndex(2)
            for width,height in ((1440,900),(1100,780)):
                window.resize(width,height);app.processEvents();window.gradient_evidence.canvas.draw()
                assert window.grab().save(str(folder/f'derivative-result-{width}.png'))
            window.gradient_evidence.tabs.setCurrentWidget(window.gradient_evidence.support)
            for width,height in ((1440,900),(1100,780)):
                window.resize(width,height);app.processEvents()
                assert window.grab().save(str(folder/f'retained-method-support-{width}.png'))
            assert canonical_hash(client.document_read(document_id)['draft'])==canonical_hash(before['draft'])
            assert canonical_hash(client.document_result(document_id,job_id))==result_hash
            assert {row['id'] for row in wb.manager.list()}==jobs and not calls
            record={'document_id':document_id,'job_id':job_id,'source':client.document_result_reference(document_id,job_id),
                'inputs':inputs,'descriptor':descriptor,'support_message':support_message,
                'support_profiles':support_profiles,
                'result_method':result.get('method'),'algorithm':result.get('algorithm'),
                'gradient_verification':result.get('gradient_verification'),
                'callback_counts':result.get('callback_counts'),'gradient_summary':window.gradient_evidence.summary.text(),
                'fd_summary':window.gradient_evidence.fd_summary.text(),'timing':result.get('timing'),
                'method_selection_and_undo':selection_change,'save_requested':edit_save=='edit-save',
                'saved_revision':window.document.get('saved_revision'),
                'new_jobs':0,'solve_fit_predict_submissions':0,'qt_platform':app.platformName(),
                'source_hashes':{p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in (
                    'apps/research/request_plan_window.py','apps/research/numerical_window.py',
                    'apps/research/s2_gradient_widgets.py','caelab/linear_adjoint_contract.py','caelab/numerical_adjoint.py')}}
            (folder/'read.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
            print(json.dumps({k:record[k] for k in ('document_id','job_id','source','support_message','new_jobs','solve_fit_predict_submissions')},ensure_ascii=False),flush=True)
        finally:
            window._allow_close=True;window.close();app.processEvents();assert QThreadPool.globalInstance().waitForDone(5000)


if __name__=='__main__':main(*sys.argv[1:])
