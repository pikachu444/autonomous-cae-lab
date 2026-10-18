"""Real HTTP/Qt Numerical workflow over exact saved Evaluation inputs.

Direct mode uses an explicitly named existing delivery store, preserves its
sources/results, and creates only new Numerical documents and bounded jobs.
"""
from collections import deque
from copy import deepcopy
import json
from pathlib import Path
import sys
import threading
import time


def wait(app,predicate,message=lambda:'Qt/HTTP did not settle',timeout=90):
    deadline=time.monotonic()+timeout;stable=None
    while time.monotonic()<deadline:
        app.processEvents()
        if predicate():
            if stable is None:stable=time.monotonic()
            if time.monotonic()-stable>=.04:return
        else:stable=None
        time.sleep(.01)
    raise AssertionError(message())


class Popups:
    def __init__(self,app,folder):
        from PySide6.QtCore import QTimer
        self.app,self.folder=app,folder;self.pending=deque();self.errors=[]
        self.timer=QTimer();self.timer.setInterval(20);self.timer.timeout.connect(self.tick);self.timer.start()
    def add(self,title,value=None,capture=None):self.pending.append((title,value,capture))
    def tick(self):
        from PySide6.QtWidgets import QInputDialog,QMessageBox,QComboBox,QLineEdit,QTableWidget,QDialogButtonBox
        dialog=self.app.activeModalWidget()
        if not dialog or not self.pending:return
        title,value,capture=self.pending[0]
        if title not in dialog.windowTitle():return
        self.pending.popleft()
        try:
            if isinstance(dialog,QMessageBox):
                dialog.button(QMessageBox.StandardButton.Yes).click();return
            if isinstance(dialog,QInputDialog):
                combo=dialog.findChild(QComboBox)
                if combo:
                    index=value if type(value) is int else next(i for i in range(combo.count()) if value in combo.itemText(i))
                    combo.setCurrentIndex(index)
                else:dialog.findChild(QLineEdit).setText(value)
            elif dialog.findChild(QTableWidget):
                dialog.findChild(QTableWidget).selectRow(value if type(value) is int else 0)
            if capture:
                self.app.processEvents();assert dialog.grab().save(str(self.folder/(capture+'.png')))
            if value=='cancel':dialog.reject();return
            dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Ok).click()
        except Exception as error:self.errors.append(str(error));dialog.reject()


def run_first(store,folder,evaluation_id):
    from PySide6.QtCore import Qt,QThreadPool
    from PySide6.QtWidgets import QApplication,QLineEdit
    from PySide6.QtTest import QTest
    from apps.lab.server import LabHTTPServer
    from apps.lab.service import LabService
    from apps.research.numerical_window import NumericalWindow
    from caelab.workbench_client import Client
    from caelab.evaluation_definition import document_reference
    from caelab.storage import canonical_hash

    folder=Path(folder).resolve();folder.mkdir(parents=True,exist_ok=False)
    app=QApplication.instance() or QApplication([])
    server=LabHTTPServer(LabService(Path(store).resolve()),0)
    thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.02},daemon=True);thread.start()
    client=Client('http://127.0.0.1:'+str(server.server_port))
    source=client.document_open(kind='evaluation',document_id=evaluation_id)
    reference=document_reference(source);source_hash=canonical_hash(source['draft'])
    original_results={r['job_id']:canonical_hash(client.document_result(source['id'],r['job_id']))
                      for r in source['runs'] if r.get('retention_complete') and r.get('retained_result')}
    # Use the product's existing Numerical -> general Plan delegation.
    parent=NumericalWindow(client,auto_open=False,poll_interval=0)
    window=parent.open_request_document();window.timer.stop()
    popups=Popups(app,folder)
    def settled(predicate=lambda:True):
        wait(app,lambda:not window._busy and not window._callbacks and not window._pending_adoption
             and not getattr(window,'_retained_labels_scheduled',False) and predicate(),lambda:window.message.text())
        assert not popups.errors,popups.errors
    def edit(table,row,column,text):
        table.setCurrentCell(row,column);table.editItem(table.item(row,column));app.processEvents()
        field=QApplication.focusWidget();assert isinstance(field,QLineEdit)
        field.selectAll();QTest.keyClicks(field,text);field.clearFocus();app.processEvents()
    try:
        settled(lambda:bool(window.document))
        window.purpose.setFocus();QTest.keyClicks(window.purpose,'Cooling Evaluation DOE')
        window.operation.setCurrentIndex(window.operation.findData('doe'));app.processEvents()
        popups.add('Use saved model',source['title'],'saved-evaluation-picker')
        popups.add('Use saved model','yes')
        window.choose_model_document();settled(lambda:window.edited_draft().get('model_source')==reference)
        assert window.edited_draft()['request']['inputs']['settings']['definition_ref']==reference
        popups.add('모델 변수 선택',0,'evaluation-variable-picker')
        window.choose_model_variables();settled(lambda:window.variable_sheet.rowCount()==1)
        edit(window.variable_sheet,0,3,'0.25');edit(window.variable_sheet,0,4,'1.25')
        popups.add('Actual retained run',0)
        popups.add('Select actual response',0,'actual-response-picker')
        window.choose_model_response();settled(lambda:window.response_sheet.rowCount()==1)
        edit(window.method_sheet,0,1,'3');edit(window.method_sheet,1,1,'17')
        window.evaluations.setFocus();window.evaluations.selectAll();QTest.keyClicks(window.evaluations,'3')
        window.evaluations.clearFocus();app.processEvents()
        assert not window.run_button.isEnabled()
        before=len(server.workbench.manager.list())
        window.apply_inputs();settled(lambda:not window.local_dirty)
        assert not window.document['diagnostics'],window.document['diagnostics']
        assert len(server.workbench.manager.list())==before
        assert window.run_button.isEnabled()
        window.run_button.click();settled(lambda:bool(window.document['runs']))
        job=window.selected_job()
        wait(app,lambda:client.status(job)['state'] in {'SUCCEEDED','PARTIAL_FAILURE','FAILED','REJECTED'},lambda:str(client.status(job)))
        window.refresh_document();settled()
        window.retry_result();settled(lambda:job in window._result_cache)
        result=window._result_cache[job]
        assert result['execution_status']=='SUCCEEDED',result
        assert len(result['candidates'])==3 and all(r['execution_status']=='SUCCEEDED' for r in result['candidates'])
        window.save_document();settled(lambda:not window.document['dirty'])
        assert canonical_hash(client.document_read(source['id'])['draft'])==source_hash
        for old_job,old_hash in original_results.items():assert canonical_hash(client.document_result(source['id'],old_job))==old_hash
        for width,height in ((1440,900),(1100,780)):
            window.resize(width,height);app.processEvents()
            assert window.grab().save(str(folder/('first-plan-'+str(width)+'.png')))
        record={'source':reference,'source_draft_sha256':source_hash,'plan_id':window.document['id'],
            'job_id':job,'saved_revision':window.document['saved_revision'],
            'draft_sha256':canonical_hash(window.document['draft']),'result_sha256':canonical_hash(result),
            'budget':window.document['draft']['request']['budget'],'candidate_count':3,
            'candidates':result['candidates'],'timing':result.get('timing'),
            'qt_platform':app.platformName(),'original_results_unchanged':True}
        (folder/'first.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({k:v for k,v in record.items() if k!='candidates'},ensure_ascii=False),flush=True)
        return record
    finally:
        popups.timer.stop();window._allow_close=True;window.close();parent._allow_close=True;parent.close()
        app.processEvents();assert QThreadPool.globalInstance().waitForDone(5000)
        server.shutdown()
        try:assert server.workbench.shutdown(timeout=10)['joined']
        finally:server.server_close();thread.join(5)


def run_retained(store,folder,first_record):
    """Small real ODE holdout/confirmation and retained local-RBF workflow."""
    from PySide6.QtCore import QThreadPool
    from PySide6.QtWidgets import QApplication
    from apps.lab.server import LabHTTPServer
    from apps.lab.service import LabService
    from apps.research.request_plan_window import RequestPlanWindow
    from caelab.workbench_client import Client
    from caelab.numerical_document import request_draft
    from caelab.storage import canonical_hash

    folder=Path(folder).resolve();folder.mkdir(parents=True,exist_ok=False)
    first=json.loads(Path(first_record).read_text(encoding='utf-8'))
    app=QApplication.instance() or QApplication([])
    server=LabHTTPServer(LabService(Path(store).resolve()),0)
    thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.02},daemon=True);thread.start()
    client=Client('http://127.0.0.1:'+str(server.server_port))
    window=RequestPlanWindow(client,auto_open=False,poll_interval=0);window.show()
    popups=Popups(app,folder);records=[]
    def settled(predicate=lambda:True):
        wait(app,lambda:not window._busy and not window._callbacks and not window._pending_adoption
             and not getattr(window,'_retained_labels_scheduled',False) and predicate(),lambda:window.message.text())
        assert not popups.errors,popups.errors
    def execute():
        settled();assert window.run_button.isEnabled(),window.message.text()
        window.run_button.click();settled(lambda:bool(window.document['runs']))
        job=window.selected_job()
        wait(app,lambda:client.status(job)['state'] in {'SUCCEEDED','FAILED','REJECTED'},lambda:str(client.status(job)))
        window.refresh_document();settled();window.retry_result();settled(lambda:job in window._result_cache)
        result=window._result_cache[job];assert result['execution_status']=='SUCCEEDED',result
        window.save_document();settled(lambda:not window.document['dirty'])
        ref=client.document_result_reference(window.document['id'],job)
        records.append({'reference':ref,'input':deepcopy(window.document['draft']),'result':deepcopy(result)})
        (folder/'completed.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')
        return ref,result
    def open_plan(title,operation,inputs,budget):
        draft=request_draft({'purpose':title,'operation':operation,'inputs':inputs,'budget':{'evaluations':budget}},source=first['source'])
        draft['model_source']=deepcopy(first['source'])
        window.open_document(title=title,draft=draft);settled(lambda:window.document is not None)
    try:
        training=client.document_result_reference(first['plan_id'],first['job_id'])
        original=client.document_read(first['plan_id'])
        prior=deepcopy(original['draft']['request']['inputs'])
        prior.pop('count',None);prior['candidates']=[{'values':{'cooling_rate':value}} for value in (.5,.8)]
        open_plan('냉각 모델 별도 검증 표본','doe',prior,2)
        holdout,_=execute()
        response={'response':'temperature','unit':'K','component':'temperature','location':'lumped','reduction':'final'}
        # Use the exact actual response identity instead of inventing its metadata.
        training_result=client.document_result(first['plan_id'],first['job_id'])
        metadata=training_result['candidates'][0]['responses']['temperature']
        response.update({key:metadata[key] for key in ('component','location') if key in metadata})
        open_plan('냉각 온도 국소 대리모델','surrogate',{'result_refs':{'training':training,'holdout':holdout},
            'response':response,'points':[{'cooling_rate':.7}],'options':{'neighbors':2}},1)
        model_ref,prediction=execute()
        assert prediction['model_artifact']['format']=='scipy-local-rbf-v1'
        assert prediction['predictions'][0]['execution_status']=='PREDICTED'
        window.candidates.selectRow(0);app.processEvents();assert window._selected_actual_candidate() is None
        for width,height in ((1440,900),(1100,780)):
            window.resize(width,height);app.processEvents();assert window.grab().save(str(folder/f'local-rbf-{width}.png'))
        original_model_id=window.document['id']
        window.next_method.setCurrentIndex(window.next_method.findData('confirm'))
        before=len(server.workbench.manager.list())
        popups.add('예측점 실제 평가','yes')
        window.next_method_button.click();settled(lambda:window.document['id']!=original_model_id)
        assert len(server.workbench.manager.list())==before
        assert window.document['draft']['request']['inputs']['candidates'][0]['values']=={'cooling_rate':.7}
        confirmed,actual=execute()
        assert actual['candidates'][0]['execution_status']=='SUCCEEDED'
        # The product's paired reader/dialog itself computes the comparison.
        from apps.research.numerical_methods import ConfirmationDialog
        from PySide6.QtCore import QTimer
        dialogs=[]
        def close_comparison():
            modal=app.activeModalWidget()
            if isinstance(modal,ConfirmationDialog):
                dialogs.append(True);app.processEvents();modal.grab().save(str(folder/'prediction-actual.png'));modal.reject()
        closer=QTimer();closer.timeout.connect(close_comparison);closer.start(25)
        window.candidates.selectRow(0);window.confirmation_button.click();settled(lambda:bool(dialogs));closer.stop()
        # Three distinct, explicitly reduced metrics from the same physical trace.
        # This checks full-dimensional Pareto mechanics, not independent design physics.
        objectives=[{**response,'reduction':reduction,'direction':direction}
            for reduction,direction in (('final','minimize'),('mean','maximize'),('max','minimize'))]
        epsilon={k:deepcopy(v) for k,v in prior.items() if k not in {'candidates','responses'}}
        epsilon.update(objectives=objectives,primary_index=0,threshold_grid=[[0.],[400.]],
            total_evaluation_budget=10,options={'max_generations':1,'population_size':5})
        open_plan('냉각 곡선 세 지표 비교','epsilon',epsilon,10)
        pareto_ref,pareto=execute()
        assert len(pareto['pareto']['response_definitions'])==3
        original_pareto=canonical_hash(pareto)
        window.pareto_x.setCurrentIndex(2);window.pareto_y.setCurrentIndex(1);app.processEvents()
        assert window.pareto_x.currentData()==2
        assert canonical_hash(window._result_cache[window.selected_job()])==original_pareto
        for width,height in ((1440,900),(1100,780)):
            window.resize(width,height);app.processEvents();assert window.grab().save(str(folder/f'pareto-three-metrics-{width}.png'))
        assert canonical_hash(client.document_result(first['plan_id'],first['job_id']))==first['result_sha256']
        record={'qt_platform':app.platformName(),'original_training_unchanged':True,'records':records,
            'declared_new_ode_stage_budget':13,'qualification':'UNKNOWN'}
        (folder/'retained.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({'result_references':[r['reference'] for r in records],
            'declared_new_ode_stage_budget':13,'qualification':'UNKNOWN'},ensure_ascii=False),flush=True)
    finally:
        popups.timer.stop();window._allow_close=True;window.close();app.processEvents()
        assert QThreadPool.globalInstance().waitForDone(5000)
        server.shutdown()
        try:assert server.workbench.shutdown(timeout=10)['joined']
        finally:server.server_close();thread.join(5)


def run_pareto(store,folder,first_record,retained_plan_id=None):
    """Continue after the preserved 0-generation invalid draft; no RBF refit."""
    from PySide6.QtCore import QThreadPool
    from PySide6.QtWidgets import QApplication
    from apps.lab.server import LabHTTPServer
    from apps.lab.service import LabService
    from apps.research.request_plan_window import RequestPlanWindow
    from caelab.workbench_client import Client
    from caelab.storage import canonical_hash
    folder=Path(folder).resolve();folder.mkdir(parents=True,exist_ok=False)
    first=json.loads(Path(first_record).read_text(encoding='utf-8'))
    app=QApplication.instance() or QApplication([])
    server=LabHTTPServer(LabService(Path(store).resolve()),0)
    thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.02},daemon=True);thread.start()
    client=Client('http://127.0.0.1:'+str(server.server_port))
    window=RequestPlanWindow(client,auto_open=False,poll_interval=0);window.show()
    def settled(predicate=lambda:True):
        wait(app,lambda:not window._busy and not window._callbacks and
             not getattr(window,'_retained_labels_scheduled',False) and predicate(),lambda:window.message.text())
    try:
        # Exact completed inputs/results from attempt 04, preserved independently.
        refs=[]
        for document_id,job_id in (
            ('Nfd91da75bb614f31af888a2dc20eb28f','J576abf70288b48d8adb581b9d59683fd'),
            ('N0d48bf017e9e4156bb465d13bbf53244','Jba226b468bb1442cbbdf876590e422bf'),
            ('Ne0e18c4cb7ce429180a326cbcabda6f0','J2bb1cee69cd942059cc6598c26c8c77d')):
            refs.append({'reference':client.document_result_reference(document_id,job_id),
                'input':client.document_read(document_id)['draft'],'result':client.document_result(document_id,job_id)})
        (folder/'prior-rbf-completed.json').write_text(json.dumps(refs,ensure_ascii=False,indent=2),encoding='utf-8')
        old=client.document_read('N128fead851284d81afcaac211ccf1183')
        assert old['diagnostics'] and old['runs']==[]
        # Save the invalid, editable draft before making a separate corrected plan.
        window.open_document(document_id=old['id']);settled(lambda:window.document is not None)
        assert not window.run_button.isEnabled();window.save_document();settled(lambda:not window.document['dirty'])
        invalid=deepcopy(window.document)
        draft=deepcopy(invalid['draft']);draft['request']['budget']['evaluations']=10
        draft['request']['inputs']['total_evaluation_budget']=10
        draft['request']['inputs']['options']['max_generations']=1
        if retained_plan_id:
            window.open_document(document_id=retained_plan_id);settled(lambda:window.document['id']==retained_plan_id)
            assert window.document['draft']==draft
            job=window.document['runs'][-1]['job_id']
        else:
            window.open_document(title='냉각 곡선 세 지표 비교',draft=draft)
            settled(lambda:window.document['id']!=old['id'])
            assert not window.document['diagnostics'],window.document['diagnostics']
            window.run_button.click();settled(lambda:bool(window.document['runs']))
            job=window.selected_job()
            wait(app,lambda:client.status(job)['state'] in {'SUCCEEDED','FAILED','REJECTED'},lambda:str(client.status(job)))
            window.refresh_document();settled()
        window.retry_result();settled(lambda:job in window._result_cache)
        result=window._result_cache[job];assert result['execution_status']=='SUCCEEDED',result
        window.save_document();settled(lambda:not window.document['dirty'])
        assert len(result['candidates'])==10 and len(result['pareto']['response_definitions'])==3
        assert sum(child['dispatched_evaluations_total'] for child in result['children'])==10
        before=canonical_hash(result)
        window.pareto_x.setCurrentIndex(2);window.pareto_y.setCurrentIndex(1);app.processEvents()
        assert window.pareto_x.currentData()==2 and canonical_hash(window._result_cache[job])==before
        window.candidates.selectRow(1);app.processEvents()
        assert window._selected_actual_candidate()['candidate_id']==result['candidates'][1]['candidate_id']
        assert window.candidates.item(1,0).data(256)==result['candidates'][1]['candidate_id']
        for width,height in ((1440,900),(1100,780)):
            window.resize(width,height);app.processEvents();assert window.grab().save(str(folder/f'pareto-three-metrics-{width}.png'))
        assert window._selected_actual_candidate()
        assert window.pde_adopt_button.isEnabled()
        for item in refs:
            ref=item['reference'];assert canonical_hash(client.document_result(ref['document_id'],ref['job_id']))==canonical_hash(item['result'])
        record={'reference':client.document_result_reference(window.document['id'],job),'input':window.document['draft'],
            'result':result,'invalid_saved_reference':{'document_id':invalid['id'],'saved_revision':invalid['saved_revision']},
            'prior_rbf_recalculated':False,'qt_platform':app.platformName(),'qualification':'UNKNOWN'}
        (folder/'pareto.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({k:v for k,v in record.items() if k not in {'input','result'}},ensure_ascii=False),flush=True)
    finally:
        window._allow_close=True;window.close();app.processEvents();assert QThreadPool.globalInstance().waitForDone(5000)
        server.shutdown()
        try:assert server.workbench.shutdown(timeout=10)['joined']
        finally:server.server_close();thread.join(5)


if __name__=='__main__':
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    if sys.argv[1]=='retained':run_retained(*sys.argv[2:])
    elif sys.argv[1]=='pareto':run_pareto(*sys.argv[2:])
    elif sys.argv[1]=='pareto-read':run_pareto(*sys.argv[2:])
    else:run_first(Path(sys.argv[1]),Path(sys.argv[2]),sys.argv[3])
