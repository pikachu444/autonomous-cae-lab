"""Bounded real HTTP/Qt PDE-to-Evaluation delivery using installed engines.

Direct execution retains Windows Qt captures. `first` and `pair` split the
delivery at its first integration point without re-running its completed jobs.
"""
from copy import deepcopy
from collections import deque
import json
from pathlib import Path
import subprocess
import sys
import threading
import time


def wait(app, predicate, message=lambda: 'Qt/owner did not settle', timeout=90):
    deadline=time.monotonic()+timeout
    stable=None
    while time.monotonic()<deadline:
        app.processEvents()
        if predicate():
            if stable is None:stable=time.monotonic()
            if time.monotonic()-stable>=.04:return
        else:stable=None
        time.sleep(.01)
    raise AssertionError(message())


def command(client,doc,operation,arguments=None):
    return client.document_command(doc['id'],operation,arguments or {},
        session_id=doc['session_id'],expected_generation=doc['generation'])


class DialogChoices:
    """Operate actual Qt modal controls, keeping their original product handlers."""
    def __init__(self,app,folder):
        from PySide6.QtCore import QTimer
        self.app,self.folder=app,folder
        self.pending=deque();self.errors=[]
        self.timer=QTimer();self.timer.setInterval(20);self.timer.timeout.connect(self.tick);self.timer.start()

    def add(self,title,choice=None,capture=None):
        self.pending.append((title,choice,capture))

    def tick(self):
        from PySide6.QtWidgets import QInputDialog,QComboBox,QLineEdit,QDialogButtonBox
        modal=self.app.activeModalWidget()
        if not modal or not self.pending:return
        title,choice,capture=self.pending[0]
        if title not in modal.windowTitle():return
        self.pending.popleft()
        try:
            if isinstance(modal,QInputDialog):
                combo=modal.findChild(QComboBox)
                if combo:
                    index=choice if type(choice) is int else next(i for i in range(combo.count()) if choice in combo.itemText(i))
                    combo.setCurrentIndex(index)
                else:
                    modal.findChild(QLineEdit).setText(choice)
            if capture:
                self.app.processEvents()
                assert modal.grab().save(str(self.folder/(capture+'.png')))
            buttons=modal.findChild(QDialogButtonBox)
            buttons.button(QDialogButtonBox.StandardButton.Ok).click()
        except Exception as error:
            self.errors.append(str(error));modal.reject()


def workflow(folder,phase):
    from PySide6.QtWidgets import QApplication
    from apps.lab.server import LabHTTPServer
    from apps.lab.service import LabService
    from apps.research.evaluation_window import EvaluationWindow
    from apps.research import desktop
    from caelab.workbench_client import Client
    from caelab.pde_document import default_draft as pde_draft
    from caelab.dimensioned_models import ODE,SCIKIT_WEAK
    from caelab import scikit_fem_models as spatial
    from caelab.evaluation_definition import document_reference
    from caelab.storage import canonical_hash
    import numpy as np

    folder=Path(folder).resolve();folder.mkdir(parents=True,exist_ok=True)
    receipt_path=folder/'workflow.json'
    receipt=json.loads(receipt_path.read_text(encoding='utf-8')) if receipt_path.exists() else {'evaluations':[]}
    if phase=='first':assert not (folder/'store').exists(),'Use a fresh delivery store'
    app=QApplication.instance() or QApplication([])
    server=LabHTTPServer(LabService(folder/'store'),0)
    thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.02},daemon=True);thread.start()
    client=Client('http://127.0.0.1:'+str(server.server_port))
    launched=[];source_receipts=[]
    real_popen=desktop.subprocess.Popen
    def tracked_popen(*args,**kwargs):
        process=real_popen(*args,**kwargs);launched.append(process);return process
    desktop.subprocess.Popen=tracked_popen
    def open_source(reference):
        opened=desktop.open_saved_reference(client,reference)
        source_receipts.append({'reference':deepcopy(reference),'launch':opened,
                                'resolved':client.research_reference({**reference,'document_kind':reference['kind'],'kind':'document'})})
    window=EvaluationWindow(client,auto_open=False,poll_interval=0,source_open=open_source)
    window.show();dialogs=DialogChoices(app,folder)

    def settled(predicate=lambda:True):
        wait(app,lambda:not window._busy and not window._callback_calls and predicate(),lambda:window.message.text())
        assert not dialogs.errors,dialogs.errors
    def capture(name):
        app.processEvents();time.sleep(.1);app.processEvents()
        assert window.grab().save(str(folder/(name+'.png')))
    def save_source(kind,title,draft):
        doc=client.document_open(kind=kind,title=title,draft=draft)
        assert not doc['diagnostics'],doc['diagnostics']
        return command(client,doc,'document.save')['document']
    def add_source(title,name):
        dialogs.add('저장된 원본 선택',title,name+'-source-picker')
        before=len(window.edited_draft()['stages']);window.add_stage()
        settled(lambda:len(window.edited_draft()['stages'])==before+1)
        window.stage_list.setCurrentRow(before)
        return window.edited_draft()['stages'][-1]['id']
    def choose_response(stage,name,unit=None,identifier=None):
        dialogs.add('읽을 응답 선택',stage)
        dialogs.add('읽을 응답 선택',name if unit is None else '직접 지정')
        if unit is not None:
            dialogs.add('읽을 응답 선택',name);dialogs.add('읽을 응답 선택',unit)
        dialogs.add('응답 이름',identifier or name)
        window.add_response();settled()
    def run_once(label):
        before=len(server.workbench.manager.list())
        window.inspect_inputs();settled()
        assert not window._inspection['diagnostics'],window._inspection
        assert len(server.workbench.manager.list())==before
        window.run_button.click();settled(lambda:bool(window._selected_job))
        job=window._selected_job
        wait(app,lambda:client.status(job)['state'] in {'SUCCEEDED','FAILED','CANCELLED','REJECTED'},lambda:str(client.status(job)))
        window.refresh_document();settled()
        window.refresh_progress();settled(lambda:bool(window._progress.get('stages')))
        result=client.document_result(window.document['id'],job)
        assert result['execution_status']=='SUCCEEDED',result
        for i in range(window.attempts.rowCount()):
            window.attempts.selectRow(i);settled(lambda:bool(window._result))
        window.save_document();settled(lambda:not window.document['dirty'])
        doc=window.document
        record={'label':label,'document_id':doc['id'],'job_id':job,'saved_revision':doc['saved_revision'],
                'draft_sha256':canonical_hash(doc['draft']),'result_sha256':canonical_hash(result),
                'sources':[deepcopy(s['source']) for s in doc['draft']['stages']],
                'stage_attempts':deepcopy(result['stages'])}
        receipt['evaluations'].append(record)
        receipt_path.write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(record,ensure_ascii=False),flush=True)
        return result,record

    try:
        if phase=='first':
            draft=pde_draft(ODE)
            source=save_source('pde','냉각 상태 방정식',draft)
            reference=document_reference(source)
            receipt['initial_pde_reference']=reference
            window.open_document(title='PDE 원본 연결');settled(lambda:bool(window.document))
            stage=add_source(source['title'],'ode')
            assert window.edited_draft()['stages'][0]['source']==reference
            window.open_source();assert source_receipts[-1]['reference']==reference
            assert source_receipts[-1]['resolved']['status']=='AVAILABLE'
            window.inspect_inputs();settled()
            dialogs.add('변경할 단계 선택',source['title'])
            dialogs.add('변경할 입력 선택','rate')
            dialogs.add('변수 이름','cooling_rate')
            window.add_binding();settled()
            choose_response(source['title'],'temperature','K')
            result,record=run_once('PDE ODE exact saved source')
            series=result['responses']['temperature']
            clock=np.asarray(series['axes'][0]['values'])
            assert np.max(np.abs(np.asarray(series['value'])-(290+10*np.exp(-.5*clock))))<1e-4
            window.resize(1440,900);capture('ode-evaluation-normal')
            window.resize(1100,780);capture('ode-evaluation-narrow')
            # Save a new PDE source revision; the existing Evaluation stays fixed.
            edited=deepcopy(source['draft']);edited['settings']['parameters'][0]['value']=.75
            source=command(client,client.document_read(source['id']),'pde.update',{'draft':edited})['document']
            source=command(client,source,'document.save')['document']
            assert document_reference(source)!=reference
            assert client.document_read(record['document_id'])['draft']['stages'][0]['source']==reference
            assert canonical_hash(client.document_result(record['document_id'],record['job_id']))==record['result_sha256']
            window.stage_list.setCurrentRow(0);window.open_source()
            assert source_receipts[-1]['reference']==reference
            # Explicit source replacement changes only the editable definition.
            dialogs.add('저장된 원본 선택',source['title'],'ode-replace-source')
            window.replace_source();settled(lambda:window.local_dirty)
            assert window.edited_draft()['stages'][0]['source']==document_reference(source)
            assert not window.run_button.isEnabled()
            assert client.document_read(record['document_id'])['draft']['stages'][0]['source']==reference
            receipt['new_pde_reference']=document_reference(source)
            receipt['old_evaluation_unchanged_after_source_edit']=True
            receipt['explicit_replace_unapplied_no_run']=True
        elif phase=='pair':
            draft=pde_draft(SCIKIT_WEAK);s=draft['settings']
            # Original uniform free-expansion case, declared through admitted PDE forms.
            s['domain']['height']=.25;s['mesh']['levels']=[2]
            for row in s['parameters']:
                if row['name']=='k':row['value']=200.
                if row['name'] in ('left_value','right_value'):row['value']=323.15
            source=save_source('pde','균일 정상 온도장',draft)
            structure=spatial.default_settings(spatial.STRUCTURAL);structure['mesh']['cells']=[3,2]
            target=save_source('simulation','자유 열팽창 평면응력',{'backend':spatial.STRUCTURAL,'settings':structure})
            window.open_document(title='PDE 온도와 열팽창');settled(lambda:bool(window.document))
            heat_id=add_source(source['title'],'heat')
            structure_id=add_source(target['title'],'structure')
            window.inspect_inputs();settled()
            dialogs.add('공급 단계 선택',source['title']);dialogs.add('공급 출력 선택','temperature')
            dialogs.add('수신 단계 선택',target['title']);dialogs.add('수신 입력 선택','temperature')
            dialogs.add('전달 시점','현재 반복');dialogs.add('공간 전달 방법','다른 P1')
            dialogs.add('온도 전달 설정',capture='temperature-mapping')
            window.add_transfer();settled(lambda:len(window.edited_draft()['transfers'])==1)
            choose_response(target['title'],'변위장',identifier='displacement')
            choose_response(target['title'],'응력장',identifier='stress')
            result,record=run_once('PDE P1 temperature to 2D plane-stress thermal expansion')
            transfer_id=window.document['draft']['transfers'][0]['id']
            mapped=client.evaluation_transfer(record['document_id'],record['job_id'],transfer_id,0)
            assert mapped['exact_values_match'] and mapped['original_source_and_receiver_are_different_meshes']
            assert mapped['reference_temperature']==293.15
            assert max(abs(row['mapped']-323.15) for row in mapped['receiver_rows'])<=1e-10
            last=client.evaluation_stage_result(record['document_id'],record['job_id'],result['stages'][-1]['attempt_id'])
            xy=np.asarray(last['responses']['displacement']['coordinates']);u=np.asarray(last['responses']['displacement']['value'])
            error=float(np.max(np.linalg.norm(u-23e-6*30*xy,axis=1)))
            assert error<=1e-10
            assert last['diagnostics']['reference_subtractions_in_structural_solver']==1
            record['transfer_sha256']=canonical_hash(mapped)
            record['transfer']=mapped
            record['free_expansion_error_m']=error
            record['reference_subtractions']=1
            record['structural_diagnostics']=last['diagnostics']
            window.resize(1440,900);capture('pair-evaluation-normal')
            window.resize(1100,780);capture('pair-evaluation-narrow')
            window.open_transfer_values()
            transfer_window=window._transfer_windows[-1]
            wait(app,lambda:bool(getattr(transfer_window,'_data',None)),lambda:transfer_window.status.text())
            assert transfer_window._data['exact_values_match']
            assert transfer_window.grab().save(str(folder/'temperature-transfer-values.png'))
            transfer_window.close()
        elif phase=='cold':
            from apps.research.reference_window import ReferenceWindow
            jobs_before=len(server.workbench.manager.list())
            for record in receipt['evaluations']:
                window.open_document(document_id=record['document_id'])
                settled(lambda:bool(window.document) and window.document['id']==record['document_id'])
                assert window._selected_job==record['job_id']
                assert canonical_hash(window.document['draft'])==record.get('current_draft_sha256',record['draft_sha256'])
                result=client.document_result(record['document_id'],record['job_id'])
                assert canonical_hash(result)==record['result_sha256']
                window.refresh_progress();settled(lambda:window.attempts.rowCount()==len(record['stage_attempts']))
                window.attempts.selectRow(window.attempts.rowCount()-1)
                settled(lambda:bool(window._result))
                window.result_tabs.setCurrentWidget(window.channels)
                if record['label'].startswith('PDE ODE'):
                    window.stage_list.setCurrentRow(0);window.open_source()
                    assert source_receipts[-1]['reference']==record.get('explicit_replaced_reference',record['sources'][0])
                    # The result-origin action must open the submitted old source
                    # even after the editable definition adopts the newer one.
                    assert window.result_source_action.isEnabled()
                    window.result_source_action.trigger();settled()
                    assert source_receipts[-1]['reference']==record['sources'][0]
                    view=ReferenceWindow(client,source_receipts[-1]['launch']['reference']);view.show()
                    try:
                        wait(app,lambda:not view._busy and bool(view.value),lambda:str(view._error))
                        assert view.value['status']=='AVAILABLE'
                        assert '-rate*(temperature-ambient)' in view.content.body.toPlainText()
                        assert '0.5' in view.content.body.toPlainText()
                        assert view.grab().save(str(folder/'old-pde-exact-source.png'))
                        count=len(launched);view.open_button.click()
                        assert len(launched)==count+1 and record['sources'][0]['document_id'] in launched[-1].args
                        receipt['pde_owner_return']={'pid':launched[-1].pid,'arguments':launched[-1].args,
                            'document_id':record['sources'][0]['document_id'],'executed':False}
                    finally:view.close();app.processEvents()
                    # Return to the current PDE owner without replacing it by
                    # the old submitted snapshot or evaluating either revision.
                    from apps.research.pde_window import PDEWindow
                    pde=PDEWindow(client,document_id=record['sources'][0]['document_id'],poll_interval=0)
                    pde.show()
                    try:
                        wait(app,lambda:not pde._busy and bool(pde.document),lambda:pde.message.text())
                        pde.tree.setCurrentItem(pde._nodes[('settings','parameters')]);app.processEvents()
                        assert pde.edited_draft()['settings']['parameters'][0]['value']==.75
                        assert pde.grab().save(str(folder/'current-pde-owner.png'))
                    finally:pde._allow_close=True;pde.close();app.processEvents()
                    # Adopt the new PDE revision explicitly; preserve the old run.
                    if not record.get('current_draft_sha256'):
                        dialogs.add('저장된 원본 선택','냉각 상태 방정식','explicit-pde-replacement')
                        window.replace_source();settled(lambda:window.local_dirty)
                        assert window.edited_draft()['stages'][0]['source']==receipt['new_pde_reference']
                        window.save_document();settled(lambda:not window.document['dirty'])
                        run=next(r for r in window.document['runs'] if r['job_id']==record['job_id'])
                        assert run['draft']['stages'][0]['source']==record['sources'][0]
                        assert not run['is_current_input']
                        record['current_draft_sha256']=canonical_hash(window.document['draft'])
                        record['current_saved_revision']=window.document['saved_revision']
                        record['explicit_replaced_reference']=deepcopy(window.document['draft']['stages'][0]['source'])
                    name='ode-cold'
                else:
                    name='pair-cold'
                    window.stage_list.setCurrentRow(window.stage_list.count()-1)
                    mapped=client.evaluation_transfer(record['document_id'],record['job_id'],
                        window.document['draft']['transfers'][0]['id'],0)
                    assert canonical_hash(mapped)==record['transfer_sha256']
                    window.open_transfer_values()
                    view=window._transfer_windows[-1]
                    wait(app,lambda:bool(getattr(view,'_data',None)),lambda:view.status.text())
                    assert view._data['exact_values_match']
                    view.mapped_view.table.selectRow(5);app.processEvents()
                    assert view.grab().save(str(folder/'temperature-transfer-values.png'))
                    view.mapped_view.selector.setCurrentIndex(1);app.processEvents()
                    assert view.grab().save(str(folder/'temperature-source-values.png'))
                    view.close();app.processEvents()
                for dimensions,suffix in (((1440,900),'normal'),((1100,780),'narrow')):
                    window.resize(*dimensions);capture(name+'-'+suffix)
            assert len(server.workbench.manager.list())==jobs_before
            receipt['cold_reopen']={'process_id':__import__('os').getpid(),'new_jobs':0,
                'same_result_hashes':True,'same_saved_inputs':True,'http_qt':True,'qt_platform':app.platformName()}
        else:raise ValueError('Choose first, pair or cold')
        receipt.setdefault('source_open_calls',[]).extend(source_receipts)
        receipt['qt_platform']=app.platformName()
        from hashlib import sha256
        root=Path(__file__).resolve().parents[1]
        receipt['source_sha256']={name:sha256((root/name).read_bytes()).hexdigest() for name in (
            'apps/research/evaluation_window.py','apps/research/reference_content.py',
            'apps/research/temperature_mapping_dialog.py','apps/research/pde_window.py',
            'tests/test_evaluation_pde_workflow.py')}
        receipt_path.write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8')
    finally:
        dialogs.timer.stop();window._allow_close=True;window.close();app.processEvents()
        desktop.subprocess.Popen=real_popen
        for process in launched:
            if process.poll() is None:process.terminate()
            process.wait(timeout=5)
        server.shutdown()
        try:assert server.workbench.shutdown(timeout=10)['joined']
        finally:server.server_close();thread.join(5)
    return receipt


def test_actual_saved_pde_selection_temperature_transfer_and_cold_reopen(tmp_path):
    import os
    import pytest
    pytest.importorskip('PySide6');pytest.importorskip('skfem')
    os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
    folder=tmp_path/'evaluation-pde'
    workflow(folder,'first');workflow(folder,'pair')
    cold=subprocess.run([sys.executable,str(Path(__file__).resolve()),str(folder),'cold'],
        cwd=str(Path(__file__).resolve().parents[1]),capture_output=True,text=True,encoding='utf-8',timeout=60)
    (folder/'cold-stdout.log').write_text(cold.stdout,encoding='utf-8')
    (folder/'cold-stderr.log').write_text(cold.stderr,encoding='utf-8')
    assert cold.returncode==0,cold.stderr
    receipt=json.loads((folder/'workflow.json').read_text(encoding='utf-8'))
    assert receipt['cold_reopen']['new_jobs']==0 and receipt['cold_reopen']['same_result_hashes']


if __name__=='__main__':
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    workflow(Path(sys.argv[1]),sys.argv[2])
