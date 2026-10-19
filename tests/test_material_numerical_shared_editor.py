"""Real loopback owners and Qt commands: one Plan, separate editable views."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from copy import deepcopy
from pathlib import Path
import time

import pytest
pytest.importorskip('PySide6')
pytest.importorskip('matplotlib')
from PySide6.QtWidgets import QDialog

from apps.research.material_plan_panel import PlanPatchDialog
from apps.research.plan_variables_widget import NumericalPlanVariablesWidget
from tests.test_material_plan_panel import host, wait


def wait_live(app, ready, seconds=25):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        app.processEvents()
        if ready():return
        time.sleep(.01)
    raise AssertionError('Real Material/Numerical workflow did not settle')


def imported_observation(app, client, filename):
    from tests.test_material_test_workflow import mapping
    payload=(Path(__file__).parents[1]/'examples/material-tests'/filename).read_bytes()
    upload=client.upload(filename,payload)
    document=client.document_open(kind='data',title=filename,draft=dict(data_id=upload['id'],
        mapping=dict(delimiter=',',skip_header=1,columns=mapping(shear=filename=='shear.csv'))))
    receipt=client.document_command(document['id'],'data.import',{},session_id=document['session_id'],
        expected_generation=document['generation'])
    job=receipt['job']['id']
    wait_live(app,lambda:client.status(job)['state'] in {'SUCCEEDED','FAILED','REJECTED'})
    assert client.status(job)['state']=='SUCCEEDED'
    document=client.document_read(document['id'])
    document=client.document_command(document['id'],'document.save',{},session_id=document['session_id'],
        expected_generation=document['generation'])['document']
    exact=client.document_result_reference(document['id'],job)
    return {key:exact[key] for key in ('document_id','job_id','input_revision','input_sha256')} | {'response':'stress'}


def measured_dialog(dialog):
    """Exercise the real dialog validator with explicit measured conditions."""
    observed=dialog.imported['responses'][dialog.observed.currentData()]
    dialog.model_response.setCurrentIndex(dialog.model_response.findData('stress_'+observed['component']))
    dialog.protocol.setCurrentIndex(dialog.protocol.findData('measured'))
    dialog.driver.setCurrentIndex(dialog.driver.findData('deformation'))
    dialog.lateral_22.setText('1');dialog.lateral_33.setText('1')
    dialog._accept()
    assert dialog.value is not None,dialog.message.text()
    return dialog.DialogCode.Accepted


def test_material_opens_existing_plan_and_creates_only_when_requested(host):
    app, client, material, panel, plans = host
    before = {document['id'] for document in client.documents()['documents']}
    assert material.open_numerical() is panel
    wait(app, lambda: not panel._busy)
    assert {document['id'] for document in client.documents()['documents']} == before
    panel.open_plan()
    numerical = material._numerical_windows[-1]
    wait(app, lambda: numerical.document and not numerical._busy)
    assert numerical.document['id'] == panel.plans.currentData()
    assert isinstance(numerical.variable_editor, NumericalPlanVariablesWidget)
    assert numerical.variable_editor.table is numerical.variables
    assert numerical.variable_editor.document_snapshot()['session_id'] == panel._widgets[numerical.document['id']].document_snapshot()['session_id']
    assert numerical.apply_button.defaultAction() is numerical.apply_action
    assert numerical.run_button.defaultAction() is numerical.run_action
    created = material.create_numerical()
    wait(app, lambda: created.document and not created._busy)
    assert created.document['id'] not in before
    assert len(client.documents()['documents']) == len(before) + 1
    assert all(not document['runs'] for document in client.documents()['documents'])


def test_focus_undo_preserves_other_fields_and_real_patch_updates_same_owner(host, monkeypatch):
    app, client, material, panel, plans = host
    panel.open_plan()
    numerical = material._numerical_windows[-1]
    wait(app, lambda: numerical.document and not numerical._busy)
    identifier = numerical.document['id']
    embedded = panel._widgets[identifier]
    embedded.table.item(0, 3).setText('unfinished bound')
    numerical.method.setCurrentText('differential_evolution')
    numerical.variables.item(0, 2).setText('1300')
    app.processEvents()
    numerical.variables.setFocus(); app.processEvents()
    numerical.undo_action.trigger(); app.processEvents()
    assert numerical.edited_draft()['variables'][0]['value'] == 1000
    assert numerical.edited_draft()['method'] == 'differential_evolution'
    assert embedded.buffer_snapshot()['variables'][0]['lower'] == 'unfinished bound'
    numerical.redo_action.trigger(); app.processEvents()
    assert numerical.edited_draft()['variables'][0]['value'] == 1300
    numerical.save_document()
    wait(app, lambda: not numerical._busy and not numerical.document['dirty'])
    assert client.document_read(identifier)['draft'] == numerical.edited_draft()
    numerical.variables.item(0, 2).setText('1400')
    monkeypatch.setattr(PlanPatchDialog, 'exec', lambda self: QDialog.DialogCode.Accepted)
    numerical.variable_editor.preview_changes()
    wait(app, lambda: not numerical._busy and not numerical.variable_editor._busy and not numerical.local_dirty)
    assert client.document_read(identifier)['draft']['variables'][0]['value'] == 1400
    assert client.document_read(material.document['id'])['draft']['settings']['parameters']['E'] == 1000
    panel.refresh_plans(); wait(app, lambda: not panel._busy)
    assert embedded.buffer_snapshot()['variables'][0]['lower'] == 'unfinished bound'
    numerical.variables.item(0,2).setText('1500');app.processEvents()
    numerical.variables.setFocus();app.processEvents()
    numerical.undo_action.trigger();app.processEvents()
    assert not numerical.local_dirty
    numerical.refresh_document();wait(app,lambda:not numerical._busy)
    assert numerical.redo_action.isEnabled()
    numerical.redo_action.trigger();app.processEvents()
    assert numerical.edited_draft()['variables'][0]['value']==1500
    assert all(not document['runs'] for document in client.documents()['documents'])


def test_exact_data_observation_registration_retries_same_lost_receipt(host, monkeypatch):
    from apps.research.material_test_dialog import ExperimentDialog
    app,client,material,panel,plans=host
    source=imported_observation(app,client,'axial.csv')
    monkeypatch.setattr(ExperimentDialog,'exec',measured_dialog)
    command=client.document_command
    commands=[]
    def lose_reply(identifier,operation,arguments,**kwargs):
        answer=command(identifier,operation,arguments,**kwargs)
        if operation=='numerical.update':
            commands.append(deepcopy(kwargs))
            if len(commands)==1:raise ConnectionError('Lost registration response after actual CAS applied')
        return answer
    monkeypatch.setattr(client,'document_command',lose_reply)
    assert material.stage_observation(source)
    wait_live(app,lambda:not panel._busy and panel._staged_observation is not None)
    identifier=panel.plans.currentData()
    assert len(client.document_read(identifier)['draft']['experiments'])==1
    assert panel.has_pending_inputs()
    panel.review_observation()
    wait_live(app,lambda:not panel._busy and panel._staged_observation is None)
    saved=client.document_read(identifier)
    assert saved['generation']==1 and len(saved['draft']['experiments'])==1
    assert saved['draft']['experiments'][0]['source']==source
    assert commands[0]['command_id']==commands[1]['command_id']
    assert panel.trials.item(0,0).text()=='axial.csv'
    assert panel.trials.item(0,1).text()=='피팅'
    assert not saved['runs'] and not material.document['runs']
    bad={**source,'input_sha256':'f'*64}
    assert material.stage_observation(bad)
    wait_live(app,lambda:not panel._busy)
    assert panel._pending_observation==bad
    assert client.document_read(identifier)['draft']==saved['draft']


def test_trial_plot_uses_frozen_input_and_clears_failed_or_other_plan(host):
    """Retained plot fixture checks presentation identity; no solver is invoked."""
    app,client,material,panel,plans=host
    identifier=panel.plans.currentData()
    document=deepcopy(panel._documents[identifier])
    frozen=dict(id='Test1',role='fit',source=dict(document_id='Toriginal',job_id='Joriginal',response='stress'),
        response='stress_xx',settings=deepcopy(material.document['draft']['settings']),weight=1.,scale=1.)
    original=deepcopy(document['draft']);original['experiments']=[frozen]
    document['draft']['experiments']=[{**deepcopy(frozen),'role':'holdout','source':{**frozen['source'],'document_id':'Tchanged'}}]
    document['runs']=[dict(job_id='Jretained',input_revision='Ioriginal',input_sha256='a'*64,draft=original)]
    panel._documents[identifier]=document
    panel._source_titles.update(Toriginal='original.csv',Tchanged='changed.csv')
    panel._trial_results[(identifier,'Jretained')]=dict(kind='fit',execution_status='SUCCEEDED',curves=[dict(experiment_id='Test1',role='fit',execution_status='SUCCEEDED',
        observations=dict(unit='MPa',axes=[dict(name='time',unit='s',values=[0,1])],value=[0,2]),prediction=[0,2],mask=[True,True])])
    panel._selected()
    context=material.curve_context.text()
    assert '이전 계획 입력' in context and '피팅' in context
    assert 'original.csv' in material.curve_context.toolTip()
    assert 'changed.csv' not in material.curve_context.toolTip() and '별도 확인' not in context
    panel._documents[identifier]['runs'].append(dict(job_id='Jfailed',input_revision='Ifailed',input_sha256='b'*64,draft=deepcopy(document['draft'])))
    panel._trial_results[(identifier,'Jfailed')]=dict(execution_status='FAILED',error='Retained failure fixture')
    panel.show_trial(force=True)
    assert not material.figure.axes[0].lines
    assert '곡선이 없습니다' in material.figure.axes[0].texts[0].get_text()
    other=next(plan['id'] for plan in plans if plan['id']!=identifier)
    panel.plans.setCurrentIndex(panel.plans.findData(other))
    assert not material.figure.axes[0].lines
    assert '저장된 계산 결과가 없습니다' in material.figure.axes[0].texts[0].get_text()


def test_selecting_another_material_keeps_its_actual_variable_ids(host, monkeypatch):
    app,client,material,panel,plans=host
    draft=deepcopy(material.document['draft'])
    draft['settings'].update(model='neo_hooke',parameters={'mu':2.,'lmbda':3.})
    other=client.document_open(kind='material',title='다른 재료',draft=draft)
    panel.open_plan();numerical=material._numerical_windows[-1]
    wait(app,lambda:numerical.document is not None and not numerical._busy)
    monkeypatch.setattr(numerical,'_list_select',lambda kind,chosen:chosen(other))
    numerical.choose_material()
    assert [variable['id'] for variable in numerical.edited_draft()['variables']]==['mu','lmbda']
    assert numerical.edited_draft()['material']['document_id']==other['id']
    numerical.apply_inputs();wait(app,lambda:not numerical._busy and not numerical.local_dirty)
    assert [variable['id'] for variable in client.document_read(numerical.document['id'])['draft']['variables']]==['mu','lmbda']
    assert not numerical.document['runs']


def test_trial_failure_cancelled_partial_and_segment_gaps_are_visible(host):
    """Controlled retained output tests UI meaning, never substitute physics."""
    app,client,material,panel,plans=host
    material.curve_view.setCurrentIndex(material.curve_view.findData(True))
    identifier=panel.plans.currentData()
    document=deepcopy(panel._documents[identifier])
    trial=dict(id='Test1',role='fit',source=dict(document_id='Toriginal',job_id='Joriginal',response='stress'),
        response='stress_xx',settings=deepcopy(material.document['draft']['settings']),weight=1.,scale=1.)
    document['draft']['experiments']=[trial]
    document['runs']=[dict(job_id='Jretained',input_revision='Ioriginal',input_sha256='a'*64,draft=deepcopy(document['draft']))]
    panel._documents[identifier]=document
    observed=dict(unit='MPa',component='xx',axes=[dict(name='time',unit='s',values=[0,1,4,5])],
        value=[0,1,4,5],segments=[dict(rows=[0,2]),dict(rows=[2,4])])
    for overall,status,prediction in (('FAILED','FAILED',[]),('CANCELLED','SUCCEEDED',[0,1.1,4.1,5.1]),('SUCCEEDED','SUCCEEDED',[0,1.1,4.1,5.1])):
        curve=dict(experiment_id='Test1',role='fit',execution_status=status,observations=observed,prediction=prediction)
        if status=='FAILED':curve['failure_reason']='Retained trial failure'
        result=dict(kind='fit',execution_status=overall,curves=[curve])
        panel._trial_results[(identifier,'Jretained')]=result
        panel._drawn_trial=None;panel._selected()
        top,bottom=material.figure.axes
        if overall=='FAILED':
            assert '실패' in panel.message.text() and 'Retained trial failure' in panel.message.text()
            assert not any(line.get_label()=='최종 예측' for line in top.lines)
        elif overall=='CANCELLED':
            assert '취소' in panel.message.text()
            assert any(line.get_label()=='보존한 부분 예측' for line in top.lines)
            assert not any(line.get_label()=='최종 예측' for line in top.lines)
        else:
            assert any(line.get_label().startswith('최종 예측') for line in top.lines)
        assert all(list(line.get_xdata()) in ([0,1],[4,5]) for line in top.lines)
        if prediction:
            assert [list(line.get_xdata()) for line in bottom.lines[:2]]==[[0,1],[4,5]]


def test_late_trial_success_or_failure_cannot_replace_explicit_material_view(host, monkeypatch):
    import threading
    app,client,material,panel,plans=host
    identifier=panel.plans.currentData()
    document=deepcopy(panel._documents[identifier])
    trial=dict(id='Test1',role='fit',source=dict(document_id='Toriginal',job_id='Joriginal',response='stress'),
        response='stress_xx',settings=deepcopy(material.document['draft']['settings']),weight=1.,scale=1.)
    document['draft']['experiments']=[trial]
    document['runs']=[dict(job_id='Jretained',input_revision='Ioriginal',input_sha256='a'*64,draft=deepcopy(document['draft']))]
    panel._documents[identifier]=document
    observations=dict(unit='MPa',component='xx',axes=[dict(name='time',unit='s',values=[0,1])],value=[0,2])
    retained=dict(kind='fit',execution_status='SUCCEEDED',curves=[dict(experiment_id='Test1',role='fit',
        execution_status='SUCCEEDED',observations=observations,prediction=[0,2])])
    own=deepcopy(material.document)
    own['runs']=[dict(job_id='Jmaterial',input_generation=0,input_revision=own['input_revision'],input_sha256='c'*64,
        is_current_input=True,settings=deepcopy(own['draft']['settings']))]
    material._result_cache['Jmaterial']=dict(execution_status='SUCCEEDED',responses={'stress_xx':{
        **deepcopy(observations),'value':[0,3]}})
    material._job_status['Jmaterial']=dict(state='SUCCEEDED',result_refs=['retained'])
    panel._busy=True
    try:material._show_document(own)
    finally:panel._busy=False
    for failure in (False,True):
        entered,release=threading.Event(),threading.Event()
        def delayed(*args,**kwargs):
            entered.set();release.wait(5)
            if failure:raise ConnectionError('Controlled delayed read failure')
            return deepcopy(retained)
        monkeypatch.setattr(client,'document_result',delayed)
        panel._drawn_trial=None
        panel._selected()
        try:
            wait_live(app,entered.is_set)
            if failure:
                material.runs.clearSelection();material.runs.selectRow(0)
            else:material.show_material_results()
            assert material._active_result_view=='material'
            title=material.figure.axes[0].get_title()
            release.set();wait_live(app,lambda:not panel._busy and not material._busy)
            assert material._active_result_view=='material' and len(material.figure.axes)==1
            assert material.figure.axes[0].get_title()==title
            assert list(material.figure.axes[0].lines[0].get_ydata())==[0,3]
        finally:release.set()


def test_public_trials_material_same_plan_felupe_adopt_and_new_process(tmp_path, monkeypatch):
    pytest.importorskip('felupe')
    import json
    import subprocess
    import sys
    import threading
    from apps.lab.server import LabHTTPServer
    from apps.lab.service import LabService
    from apps.research.material_window import MaterialWindow
    from apps.research.material_test_dialog import ExperimentDialog
    from apps.research.appearance import apply_appearance
    from caelab.numerical_document import from_material_document
    from caelab.workbench_client import Client
    from PySide6.QtWidgets import QApplication, QMessageBox
    app=QApplication.instance() or QApplication([])
    apply_appearance(app)
    store=tmp_path/'store'
    service=LabService(store)
    server=LabHTTPServer(service,0)
    thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.02},daemon=True)
    thread.start()
    client=Client(f'http://127.0.0.1:{server.server_port}')
    material=MaterialWindow(client,poll_interval=0)
    windows=[material]
    try:
        wait_live(app,lambda:material.document is not None and not material._busy)
        original=deepcopy(material.document['draft'])
        plan=client.document_open(kind='numerical',title='인장과 전단 재료 동정',draft=from_material_document(material.document))
        panel=material.open_plan_variables()
        wait_live(app,lambda:not panel._busy and panel.plans.count()==1)
        roles=iter(('fit','fit','holdout'))
        def review(dialog):
            dialog.role.setCurrentIndex(dialog.role.findData(next(roles)))
            return measured_dialog(dialog)
        monkeypatch.setattr(ExperimentDialog,'exec',review)
        for index,filename in enumerate(('axial.csv','shear.csv','holdout.csv')):
            source=imported_observation(app,client,filename)
            assert material.stage_observation(source)
            wait_live(app,lambda:not panel._busy and panel.trials.rowCount()==index+1)
        registered=client.document_read(plan['id'])
        assert [trial['role'] for trial in registered['draft']['experiments']]==['fit','fit','holdout']
        assert [panel.trials.item(i,0).text() for i in range(3)]==['axial.csv','shear.csv','holdout.csv']
        assert client.document_read(material.document['id'])['draft']==original
        assert not registered['runs']
        panel.open_plan()
        numerical=material._numerical_windows[-1];windows.append(numerical)
        wait_live(app,lambda:numerical.document is not None and not numerical._busy)
        assert numerical.document['id']==plan['id']
        for row,column,text in ((0,2,'900'),(0,3,'500'),(0,4,'2000'),(1,2,'0.2'),(1,3,'0.1'),(1,4,'0.4'),(1,5,'true')):
            numerical.variables.item(row,column).setText(text)
        numerical.apply_action.trigger()
        wait_live(app,lambda:not numerical._busy and not numerical.local_dirty)
        numerical.run_action.trigger()
        wait_live(app,lambda:not numerical._busy and len(numerical.document['runs'])==1)
        job=numerical.document['runs'][0]['job_id']
        wait_live(app,lambda:client.status(job)['state'] in {'SUCCEEDED','FAILED','REJECTED'})
        assert client.status(job)['state']=='SUCCEEDED'
        result=client.document_result(plan['id'],job)
        assert result['parameters']['E']==pytest.approx(1200,rel=1e-5)
        assert result['parameters']['nu']==pytest.approx(.25,abs=1e-5)
        assert result['curves'][-1]['role']=='holdout' and result['curves'][-1]['rmse']<1e-5
        wait_live(app,lambda:not numerical._busy)
        numerical.refresh_document();wait_live(app,lambda:not numerical._busy)
        numerical.refresh_result();wait_live(app,lambda:not numerical._busy and job in numerical._result_cache)
        candidate=min((row for row in result['candidates'] if row['execution_status']=='SUCCEEDED'),key=lambda row:row['objective'])
        row=next(i for i in range(numerical.candidates.rowCount()) if numerical.candidates.item(i,0).toolTip()==candidate['candidate_id'])
        numerical.candidates.selectRow(row)
        numerical.open_candidate_detail()
        detail=numerical._candidate_detail_windows[-1];windows.append(detail)
        wait_live(app,lambda:detail.view is not None and detail._read_worker is None)
        if not detail.evidence_button.isEnabled():
            assert detail.detail_button.isEnabled()
            detail.evaluate_missing()
            wait_live(app,lambda:detail.view is not None and detail.view.get('attempt_state')=='SUCCEEDED' and not detail._writing)
        assert detail.view['candidate']['candidate_id']==candidate['candidate_id']
        assert any(trial['role']=='holdout' for trial in detail.view['trials'])
        detail.preserve_evidence()
        wait_live(app,lambda:detail._evidence_reference is not None and not detail._writing and detail._read_worker is None)
        assert client.document_read(material.document['id'])['draft']==original
        numerical.refresh_document();wait_live(app,lambda:not numerical._busy)
        monkeypatch.setattr(QMessageBox,'question',lambda *args,**kwargs:QMessageBox.StandardButton.Yes)
        assert numerical.adopt_candidate()
        wait_live(app,lambda:not numerical._busy and numerical._adoption_receipt is None)
        adopted=client.document_read(material.document['id'])
        assert adopted['draft']['settings']['parameters']['E']==pytest.approx(1200,rel=1e-5)
        material.refresh_document();wait_live(app,lambda:not material._busy)
        material.save_document();wait_live(app,lambda:not material._busy and not material.document['dirty'])
        numerical.refresh_document();wait_live(app,lambda:not numerical._busy)
        numerical.save_document();wait_live(app,lambda:not numerical._busy and not numerical.document['dirty'])
        panel.refresh_plans();wait_live(app,lambda:not panel._busy and panel._drawn_trial is not None)
        material.curve_view.setCurrentIndex(material.curve_view.findData(True))
        assert len(material.figure.axes)==2
        assert len(material.figure.axes[0].lines)==2
        title=material.figure.axes[0].get_title();selection=panel.trials.currentRow()
        material.timer.timeout.emit();wait_live(app,lambda:not material._busy)
        assert len(material.figure.axes)==2 and material.figure.axes[0].get_title()==title
        assert panel.trials.currentRow()==selection
        material.show_material_results()
        assert len(material.figure.axes)==1 and material._active_result_view=='material'
        panel.show_trial(force=True)
        assert len(material.figure.axes)==2 and material._active_result_view=='plan'
        for name,window in (('material',material),('numerical',numerical),('candidate',detail)):
            for size,label in (((1440,900),'wide'),((1100,780),'narrow')):
                window.resize(*size);window.show();app.processEvents()
                window.grab().save(str(tmp_path/f'{name}-{label}.png'))
        snapshot=dict(material_id=material.document['id'],plan_id=plan['id'],job_id=job,
            material=material.document['draft'],plan=numerical.document['draft'],parameters=result['parameters'],runs=len(numerical.document['runs']))
    finally:
        for window in reversed(windows):
            if window is not material:window._allow_close=True
            window.close() if window is not material else None
        material._allow_close=True;material.close();app.processEvents()
        server.shutdown();server.server_close();service.shutdown();thread.join(3)
    code='''
import json,sys
from caelab.workbench import Workbench
from apps.research.material_window import MaterialWindow
from apps.research.numerical_window import NumericalWindow
from PySide6.QtWidgets import QApplication
root,snapshot=sys.argv[1],json.loads(sys.argv[2])
app=QApplication([])
wb=Workbench(root)
windows=[]
try:
    material=wb.document_open(kind='material',document_id=snapshot['material_id'])
    plan=wb.document_open(kind='numerical',document_id=snapshot['plan_id'])
    assert material['draft']==snapshot['material'] and plan['draft']==snapshot['plan']
    assert len(plan['runs'])==snapshot['runs']
    result=wb.document_result(plan['id'],snapshot['job_id'])
    assert result['parameters']==snapshot['parameters']
    m=MaterialWindow(None,auto_open=False,poll_interval=0);windows.append(m);m._show_document(material)
    n=NumericalWindow(None,auto_open=False,poll_interval=0);windows.append(n);n._show_document(plan)
    assert len(n.edited_draft()['experiments'])==3 and m.edited_draft()==material['draft']
    print(json.dumps({'reopened':True,'E':result['parameters']['E'],'nu':result['parameters']['nu'],'runs':len(plan['runs'])}))
finally:
    for window in windows:window._allow_close=True;window.close()
    assert wb.shutdown()['joined']
'''
    reopened=subprocess.run([sys.executable,'-c',code,str(store),json.dumps(snapshot)],capture_output=True,text=True,timeout=40,
        env={**os.environ,'QT_QPA_PLATFORM':'offscreen'})
    assert reopened.returncode==0,reopened.stdout+'\n'+reopened.stderr
    assert json.loads(reopened.stdout)['reopened'] is True
