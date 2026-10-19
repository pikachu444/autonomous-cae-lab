"""Same Plan owners in Material and Numerical; no physics job is requested."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from copy import deepcopy
import threading
import time
import pytest
pytest.importorskip('PySide6')
pytest.importorskip('matplotlib')
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog
from apps.research.material_window import MaterialWindow
from apps.research.material_plan_panel import PlanPatchDialog


def wait(app, ready):
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        app.processEvents()
        if ready(): return
        time.sleep(.005)
    raise AssertionError('Plan host reply timeout')


@pytest.fixture
def host(tmp_path):
    pytest.importorskip('caelab.plan_variables_api')
    pytest.importorskip('apps.research.plan_variables_widget')
    from apps.lab.server import LabHTTPServer
    from apps.lab.service import LabService
    from caelab.workbench_client import Client
    from caelab.numerical_document import from_material_document
    app = QApplication.instance() or QApplication([])
    from apps.research.appearance import apply_appearance
    apply_appearance(app)
    service = LabService(tmp_path)
    server = LabHTTPServer(service, 0)
    thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .02}, daemon=True)
    thread.start()
    client = Client(f'http://127.0.0.1:{server.server_port}')
    material = MaterialWindow(client, poll_interval=0)
    wait(app, lambda: material.document and not material._busy)
    material.save_document(); wait(app, lambda: not material._busy)
    plans = [client.document_open(kind='numerical', title=name, draft=from_material_document(material.document))
             for name in ('인장 피팅 A', '인장 피팅 B')]
    material.show(); panel = material.open_plan_variables()
    wait(app, lambda: not panel._busy and panel.plans.count() == 2)
    try:
        yield app, client, material, panel, plans
    finally:
        wait(app, lambda: not material._busy and not panel._busy)
        for window in material._numerical_windows:
            window._allow_close = True; window.close()
        material._allow_close = True; material.close(); app.processEvents()
        server.shutdown(); server.server_close(); service.shutdown(); thread.join(2)


def test_two_plan_buffers_focus_and_parent_close_are_independent(host, monkeypatch):
    app, client, material, panel, plans = host
    first_id, second_id = [plan['id'] for plan in plans]
    panel.plans.setCurrentIndex(panel.plans.findData(first_id))
    first = panel._widgets[first_id]
    assert first.table.item(1, 0).text() == '포아송비 ν [1]'
    assert first.buffer_snapshot()['variables'][1]['id'] == 'nu'
    first.table.item(0, 2).setText('1600')
    panel.plans.setCurrentIndex(panel.plans.findData(second_id))
    second = panel._widgets[second_id]
    second.table.item(0, 2).setText('1700')
    panel.plans.setCurrentIndex(panel.plans.findData(first_id))
    material.coefficients.item(0, 1).setText('1400')
    wait(app, lambda: first.undo_button.isEnabled())
    first.table.setFocus()
    QTest.keyClick(first.table, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
    assert first.buffer_snapshot()['variables'][0]['value'] == 1000
    assert material.edited_draft()['settings']['parameters']['E'] == 1400
    assert second.buffer_snapshot()['variables'][0]['value'] == 1700
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, 'exec', lambda self: QMessageBox.StandardButton.Cancel)
    material.close(); app.processEvents()
    assert material.isVisible() and panel.has_pending_inputs()
    assert client.document_read(first_id)['draft']['variables'][0]['value'] == 1000


def test_test_list_and_explicit_coefficient_contexts_keep_one_owner(host):
    app,client,material,panel,plans=host
    assert panel.compact
    assert material._plan_dock is material._material_dock
    assert panel.coefficient_tabs.widget(0) is material.editor
    assert panel.coefficient_tabs.tabBar().isHidden()
    assert panel.coefficient_mode.currentText()=='피팅 시작값과 범위'
    assert panel.fit_output.tabText(2)=='피팅 계수'
    assert material.dockWidgetArea(material._plan_dock)==Qt.DockWidgetArea.LeftDockWidgetArea
    assert panel.content_splitter.orientation()==Qt.Orientation.Vertical
    assert panel.content_splitter.widget(0).isAncestorOf(panel.trials)
    assert panel.content_splitter.widget(1).isAncestorOf(panel.coefficient_tabs)
    identifier=panel.plans.currentData();widget=panel._widgets[identifier]
    widget.table.item(0,2).setText('1e')
    material.resize(1100,780);app.processEvents()
    assert material.canvas.width()>500
    material._active_result_view='plan'
    material._material_dock.show();material._material_dock.raise_();app.processEvents()
    assert material._active_result_view=='plan'
    assert widget.buffer_snapshot()['variables'][0]['value']=='1e'
    material._plan_dock.raise_();app.processEvents()
    assert panel.plans.currentData()==identifier and widget.buffer_snapshot()['variables'][0]['value']=='1e'
    assert not any(d.get('runs') for d in client.documents()['documents'])


def test_default_entry_uses_calibration_shell_and_model_selector_stays_visible(host):
    app,client,material,panel,plans=host
    assert material._material_dock.widget() is panel
    assert panel.isAncestorOf(material.model) and not material.editor.isAncestorOf(material.model)
    material.model.setCurrentIndex(material.model.findData('neo_hooke'));app.processEvents()
    assert material.edited_draft()['settings']['model']=='neo_hooke'
    assert material.local_dirty
    panel.trials.setRowCount(2)
    for row in range(2):
        for col in range(4):
            from PySide6.QtWidgets import QTableWidgetItem
            panel.trials.setItem(row,col,QTableWidgetItem(str(row)+':'+str(col)))
    panel.trials.setCurrentCell(1,1);app.processEvents()
    assert {index.row() for index in panel.trials.selectedIndexes()}=={1}
    assert {index.column() for index in panel.trials.selectedIndexes()}=={0,1}


def test_save_action_uses_existing_two_owner_save_and_binding_cancel_keeps_both(host,monkeypatch):
    app,client,material,panel,plans=host
    calls=[]
    monkeypatch.setattr(panel,'save_related',lambda:calls.append('related'))
    material.save_action.trigger()
    assert calls==['related']
    before=deepcopy(panel._documents[panel.plans.currentData()])
    material_before=deepcopy(material.document)
    monkeypatch.setattr(PlanPatchDialog,'exec',lambda self:QDialog.DialogCode.Rejected)
    panel.bind_current_material()
    assert panel._documents[before['id']]==before and material.document==material_before


def test_explicit_plan_review_apply_save_and_same_standalone_owner(host, monkeypatch):
    app, client, material, panel, plans = host
    monkeypatch.setattr(PlanPatchDialog, 'exec', lambda self: QDialog.DialogCode.Accepted)
    identifier = panel.plans.currentData(); widget = panel._widgets[identifier]
    original = deepcopy(material.document['draft'])
    widget.table.item(0, 2).setText('1600')
    assert client.document_read(identifier)['draft']['variables'][0]['value'] == 1000
    widget.preview_changes()
    wait(app, lambda: not panel._busy and not widget.has_unapplied_buffer())
    assert client.document_read(identifier)['draft']['variables'][0]['value'] == 1600
    assert client.document_read(material.document['id'])['draft'] == original
    assert panel.has_pending_inputs()  # Applied owner draft still needs saving.
    panel.save_plan()
    wait(app, lambda: not panel._busy and not panel.has_pending_inputs())
    panel.open_plan()
    standalone = material._numerical_windows[-1]
    wait(app, lambda: standalone.document and not standalone._busy)
    assert standalone.document['id'] == identifier
    assert standalone.variables is not widget.table
    assert standalone.document['draft'] == widget.buffer_snapshot()
    assert not any(document.get('runs') for document in client.documents()['documents'])


def test_conflict_between_review_and_apply_keeps_cells(host, monkeypatch):
    app, client, material, panel, plans = host
    identifier = panel.plans.currentData(); widget = panel._widgets[identifier]
    before = widget.document_snapshot()
    def peer_edit(dialog):
        draft = deepcopy(before['draft']); draft['variables'][0]['value'] = 1800
        client.document_command(identifier, 'numerical.update', {'draft': draft},
            session_id=before['session_id'], expected_generation=before['generation'], command_id='Cpeerplan')
        return QDialog.DialogCode.Accepted
    monkeypatch.setattr(PlanPatchDialog, 'exec', peer_edit)
    widget.table.item(0, 2).setText('1600')
    widget.preview_changes()
    wait(app, lambda: not panel._busy and '변경' in widget.message.text())
    assert widget.has_unapplied_buffer()
    assert widget.buffer_snapshot()['variables'][0]['value'] == 1600
    assert client.document_read(identifier)['draft']['variables'][0]['value'] == 1800
    panel.save_plan()
    assert widget.has_unapplied_buffer()


def test_fit_button_uses_selected_owner_once_and_blocks_unapplied_raw(host,monkeypatch):
    app,client,material,panel,plans=host
    identifier=panel.plans.currentData();document=deepcopy(panel._documents[identifier])
    calls=[]
    def command(target,operation,arguments,**identity):
        calls.append((target,operation,deepcopy(arguments),identity))
        return {'document':deepcopy(document),'command_id':identity['command_id']}
    monkeypatch.setattr(client,'document_command',command)
    QTest.mouseClick(panel.fit_button,Qt.MouseButton.LeftButton)
    wait(app,lambda:not panel._busy)
    assert len(calls)==1 and calls[0][:3]==(identifier,'numerical.run',{})
    assert calls[0][3]['expected_generation']==document['generation']
    assert calls[0][3]['session_id']==document['session_id']
    panel._widgets[identifier].table.item(0,2).setText('1e')
    panel.fit_button.click();app.processEvents()
    assert len(calls)==1
    assert panel._widgets[identifier].buffer_snapshot()['variables'][0]['value']=='1e'
    assert not material._numerical_windows


def test_trial_modal_cancel_late_selection_and_final_parameters_do_not_adopt(host,monkeypatch):
    app,client,material,panel,plans=host
    identifier=panel.plans.currentData();document=deepcopy(panel._documents[identifier])
    before=deepcopy(material.document['draft']);original=deepcopy(document['draft'])
    from apps.research import material_test_dialog
    class Cancel:
        def __init__(self,*args,**kwargs):pass
        def exec(self):return QDialog.DialogCode.Rejected
    monkeypatch.setattr(material_test_dialog,'ExperimentDialog',Cancel)
    panel._trial_dialog(document,{'document_id':'Duser'},{'execution_status':'SUCCEEDED'})
    assert panel._documents[identifier]['draft']==original and material.document['draft']==before
    # A read completing after switching Plans must never open a stale modal.
    opened=[]
    class Trap(Cancel):
        def __init__(self,*args,**kwargs):opened.append(True)
    monkeypatch.setattr(material_test_dialog,'ExperimentDialog',Trap)
    panel.plans.setCurrentIndex(1-panel.plans.currentIndex())
    panel._trial_dialog(document,{}, {'execution_status':'SUCCEEDED'})
    assert not opened
    selected=panel._documents[panel.plans.currentData()]
    selected['runs']=[{'job_id':'Jread'}]
    panel._trial_results[(selected['id'],'Jread')]={'parameters':{'E':1200.,'nu':.25},
        'parameter_units':{'E':'MPa','nu':'1'},'execution_status':'SUCCEEDED'}
    panel._show_final_parameters()
    assert panel.final_parameters.item(0,2).text()=='1200'
    assert panel.final_parameters.item(1,2).text()=='0.25'
    assert material.document['draft']==before
    assert selected['draft']['variables'][0]['value']==original['variables'][0]['value']


def test_lost_fit_reply_reuses_one_request_and_keeps_late_raw_and_other_selection(host,monkeypatch):
    app,client,material,panel,plans=host
    identifier=panel.plans.currentData();document=deepcopy(panel._documents[identifier])
    requests=[];submitted=set()
    def command(target,operation,arguments,**identity):
        requests.append((target,operation,deepcopy(arguments),identity))
        if identity['command_id'] not in submitted:
            submitted.add(identity['command_id']);raise OSError('controlled lost acknowledgement after submit')
        return {'document':deepcopy(document),'command_id':identity['command_id']}
    monkeypatch.setattr(client,'document_command',command)
    panel.fit_button.click();wait(app,lambda:not panel._busy)
    assert panel.has_pending_plan_request() and panel.has_pending_inputs()
    material.close();app.processEvents()
    assert material.isVisible()
    assert material.open_document(document_id='Mother') is False
    assert material.copy_edits() is False
    panel._widgets[identifier].table.item(0,2).setText('1e')
    panel.fit_button.click();assert len(requests)==1
    panel.plans.setCurrentIndex(1-panel.plans.currentIndex())
    selected=panel.plans.currentData();before=deepcopy(panel._documents[selected])
    panel.retry_command_button.click();wait(app,lambda:not panel._busy)
    assert len(submitted)==1 and requests[0]==requests[1]
    assert not panel.has_pending_plan_request()
    assert panel.plans.currentData()==selected and panel._documents[selected]==before
    assert panel._widgets[identifier].buffer_snapshot()['variables'][0]['value']=='1e'


def test_run_once_sends_exact_selected_trial_and_keeps_both_drafts(host,monkeypatch):
    from caelab.storage import canonical_hash
    app,client,material,panel,plans=host
    identifier=panel.plans.currentData();plan=panel._documents[identifier]
    plan['draft']['experiments']=[dict(id='UserTest',role='fit',source={'document_id':'Duser','response':'stress'},
        response='stress_xx',settings=deepcopy(material.document['draft']['settings']))]
    panel.update_badge();panel.trials.setCurrentCell(0,0)
    original=deepcopy(material.document);plan_before=deepcopy(plan)
    requests=[]
    def command(target,operation,arguments,**identity):
        requests.append((target,operation,deepcopy(arguments),identity))
        return {'document':deepcopy(original),'command_id':identity['command_id']}
    monkeypatch.setattr(client,'document_command',command)
    material.run_action.trigger();wait(app,lambda:not panel._busy and not material._busy)
    assert len(requests)==1 and requests[0][:2]==(material.document['id'],'material.evaluate')
    assert requests[0][2]=={'trial':dict(document_id=identifier,input_revision=plan['input_revision'],
        input_sha256=canonical_hash(plan['draft']),experiment_id='UserTest')}
    assert material.document['draft']==original['draft'] and panel._documents[identifier]==plan_before


@pytest.mark.parametrize('matching',[True,False])
def test_only_exact_typed_pre_submit_rejection_releases_pending(host,monkeypatch,matching):
    from urllib.error import HTTPError
    from caelab.storage import canonical_hash
    from caelab.workbench_client import WorkbenchHTTPError
    app,client,material,panel,plans=host
    document=deepcopy(panel._documents[panel.plans.currentData()])
    def reject(target,operation,arguments,**identity):
        error=WorkbenchHTTPError(HTTPError('http://127.0.0.1',400,'rejected',{},None),b'{}','No free fit coefficients')
        error.command_rejection=dict(document_id=target,command_id=identity['command_id'],
            request_hash=canonical_hash(dict(document_id=target,operation=operation,arguments=arguments,
                session_id=identity['session_id'],expected_generation=identity['expected_generation'])),outcome='REJECTED')
        if not matching:error.command_rejection['request_hash']='0'*64
        raise error
    monkeypatch.setattr(client,'document_command',reject)
    panel.run_fit();wait(app,lambda:not panel._busy)
    assert panel.has_pending_plan_request() is (not matching)
    assert panel._documents[document['id']]==document
    if matching:assert '접수 전에 거절' in panel.message.text()
    else:
        assert panel.retry_command_button.isVisible()
        # Release only this controlled fixture for teardown; production has no such reset.
        panel._pending_plan_command=None


def test_current_coefficient_evaluation_plots_all_groups_without_final_fit_label(host):
    from caelab.storage import canonical_hash
    app,client,material,panel,plans=host
    curve={'execution_status':'SUCCEEDED','observations':{'axes':[{'name':'time','unit':'s','values':[0,1,2]}],
        'value':[0.,1.,2.],'component':'xx','unit':'MPa'},'prediction':[0.,.9,1.8],
        'mask':[True,False,True],'observation_source':{'data_source':{'document_id':'TtestB'}}}
    panel._source_titles['TtestB']='시험 B.csv'
    selection=panel.trials.currentRow();draft=deepcopy(material.document['draft'])
    result={'execution_status':'SUCCEEDED','material_trial':{'parameters':{'E':900.,'nu':.2},
        'material_source':dict(document_id=material.document['id'],input_revision=material.document['input_revision'],
            input_sha256=canonical_hash(material.document['draft'])),
        'source':{'document_id':'Nselected'},'curves':[{**deepcopy(curve),'role':'fit'},
            {**deepcopy(curve),'role':'holdout'}]}}
    original=deepcopy(result)
    material.document['runs']=[dict(job_id='Jevaluate',draft=deepcopy(material.document['draft']))]
    assert material._draw_trial_evaluation('Jevaluate',result)
    assert len(material.figure.axes)==1 and len(material.axes.lines)==4
    assert all('최종' not in line.get_label() for line in material.axes.lines)
    assert any('별도 확인' in line.get_label() for line in material.axes.lines)
    assert 'E=900 MPa' in material.curve_context.text() and 'ν=0.2' in material.curve_context.text()
    assert material.axes.get_xlabel()=='시간 [s]' and result==original
    assert '현재 계수 평가' in material.curve_context.text() and '시험 B.csv' in material.curve_context.text()
    assert panel.trials.currentRow()==selection and material.document['draft']==draft
    assert [material.values.item(row,6).text() for row in (3,4,5)]==['포함','제외','포함']
    assert material.values.item(4,5).text()=='미제공'
    material.document['input_revision']='Iother'
    material._draw_trial_evaluation('Jevaluate',result)
    assert '이전 계수 평가' in material.curve_context.text()
    assert all('현재 계수' not in line.get_label() for line in material.axes.lines)
    assert result==original


def test_final_fit_trial_reads_all_compiled_parent_groups(host):
    from caelab.storage import canonical_hash
    app,client,material,panel,plans=host
    identifier=panel.plans.currentData();document=panel._documents[identifier]
    document['draft']['experiments']=[dict(id='OriginalTrial',role='fit',source={'document_id':'Tsource','response':'stress'},
        response='stress_xx')]
    document['runs']=[dict(job_id='Jgroup',input_revision='Igroup',input_sha256=canonical_hash(document['draft']),draft=deepcopy(document['draft']))]
    observation={'axes':[{'name':'time','unit':'s','values':[0,1,2]}],'value':[0.,1.,2.],'component':'xx','unit':'MPa'}
    curves=[dict(experiment_id='Ehash'+str(i),role=role,execution_status='SUCCEEDED',observations=deepcopy(observation),
        prediction=[0.,.9,1.8],mask=[True,False,True],observation_source={'parent_experiment_id':'OriginalTrial'})
        for i,role in enumerate(('fit','holdout'))]
    result=dict(kind='fit',execution_status='SUCCEEDED',parameters={'E':1200,'nu':.25},parameter_units={'E':'MPa','nu':'1'},curves=curves)
    original=deepcopy(result);panel._trial_results[(identifier,'Jgroup')]=result
    panel.update_badge();panel.show_trial(force=True)
    assert len(material.figure.axes)==1 and len(material.figure.axes[0].lines)==4
    labels=[line.get_label() for line in material.figure.axes[0].lines]
    assert any('피팅' in label for label in labels) and any('별도 확인' in label for label in labels)
    assert result==original


def test_single_observation_model_plot_keeps_time_units_and_optional_raw_residual():
    from matplotlib.figure import Figure
    from apps.research.numerical_window import plot_fit_trial
    result={'execution_status':'SUCCEEDED'}
    curve={'execution_status':'SUCCEEDED','observations':{'axes':[{'name':'time','unit':'s','values':[0,1,2]}],
        'value':[0.,1.,2.],'component':'xx','unit':'MPa'},'prediction':[0.,1.2,1.8]}
    original=deepcopy(curve);figure=Figure()
    main,residual=plot_fit_trial(figure,result,curve,show_residual=False)
    assert residual is None and len(figure.axes)==1 and main.get_xlabel()=='시간 [s]'
    assert main.get_ylabel()=='xx [MPa]'
    assert list(main.lines[1].get_ydata())==[0.,1.2,1.8]
    figure.clear();main,residual=plot_fit_trial(figure,result,curve)
    assert list(residual.lines[0].get_ydata())==pytest.approx([0.,.2,-.2])
    assert curve==original


def test_lost_related_save_reply_reopens_exact_receipt_with_unfinished_cells(host, monkeypatch):
    from PySide6.QtWidgets import QLineEdit
    from apps.research.material_related_save import RelatedSaveDialog
    app, client, material, panel, plans = host
    identifier = panel.plans.currentData(); widget = panel._widgets[identifier]
    original = client.data_material; calls = []; previews = []
    def lose_execute_reply(operation, arguments):
        calls.append((operation, deepcopy(arguments)))
        value = original(operation, arguments)
        if operation == 'related_save.execute':
            raise ConnectionError('Injected lost HTTP reply after the actual owner saves committed')
        return value
    monkeypatch.setattr(client, 'data_material', lose_execute_reply)
    def save_and_close(dialog):
        wait(app, lambda: dialog.preview is not None and not dialog._busy)
        previews.append(deepcopy(dialog.preview))
        dialog.save()
        assert panel._related_save_receipts[identifier] == dialog.preview['receipt_id']
        wait(app, lambda: not dialog._busy)
        assert dialog.receipt is None and dialog.pending_preview == previews[0]
        dialog.reject(); return QDialog.DialogCode.Rejected
    monkeypatch.setattr(RelatedSaveDialog, 'exec', save_and_close)
    assert panel.save_related()
    receipt_id = previews[0]['receipt_id']
    assert panel.save_receipt_button.isEnabled()
    assert identifier in panel._related_save_unconfirmed
    assert panel._related_save_pending[identifier] == previews[0]
    # Querying a committed receipt must remain available with an unfinished
    # editor, while every mutation control stays unavailable.
    material._plan_dock.show();material._plan_dock.raise_();material.activateWindow()
    app.processEvents();QTest.qWait(20)
    widget.table.setCurrentCell(0, 2); widget.table.setFocus()
    widget.table.editItem(widget.table.item(0, 2)); app.processEvents()
    editor = QApplication.focusWidget(); assert isinstance(editor, QLineEdit)
    old_cell = widget.table.item(0, 2).text(); editor.setText('1e')
    def reopen_only(dialog):
        wait(app, lambda: dialog.receipt is not None and not dialog._busy)
        assert dialog.preview['receipt_id'] == receipt_id
        assert not dialog.allow_writes and not dialog.save_button.isEnabled()
        assert not dialog.link_button.isEnabled() and not dialog.retry_button.isEnabled()
        assert dialog.receipt['all_saved']
        assert all(len(target['attempts']) == 1 for target in dialog.receipt['targets'])
        dialog.reject(); return QDialog.DialogCode.Rejected
    monkeypatch.setattr(RelatedSaveDialog, 'exec', reopen_only)
    # The ordinary action routes an unresolved save to its original result.
    assert panel.save_related()
    assert identifier not in panel._related_save_unconfirmed
    assert editor.text() == '1e' and widget.table.item(0, 2).text() == old_cell
    assert [operation for operation, _ in calls] == ['related_save.preview', 'related_save.execute', 'related_save.receipt']
    assert calls[-1][1] == {'receipt_id': receipt_id}
    QTest.keyClick(editor, Qt.Key.Key_Escape); app.processEvents()
    material._material_dock.show();material._material_dock.raise_();app.processEvents()
    material.coefficients.setCurrentCell(0, 1); material.coefficients.setFocus()
    material.coefficients.editItem(material.coefficients.item(0, 1)); app.processEvents()
    material_editor = QApplication.focusWidget(); assert isinstance(material_editor, QLineEdit)
    material_cell = material.coefficients.item(0, 1).text(); material_editor.setText('2e')
    assert panel.save_related(receipt_id=receipt_id)
    assert material_editor.text() == '2e' and material.coefficients.item(0, 1).text() == material_cell
    assert [operation for operation, _ in calls][-1] == 'related_save.receipt'
    assert sum(operation == 'related_save.execute' for operation, _ in calls) == 1
    receipt = original('related_save.receipt', {'receipt_id': receipt_id})
    assert all(len(target['attempts']) == 1 for target in receipt['targets'])
    assert not any(document.get('runs') for document in client.documents()['documents'])


@pytest.mark.skipif(not os.environ.get('CAE_MATERIAL_UX_STORE'),reason='requires retained input and exclusive desktop lease')
def test_actual_saved_material_edit_context_and_curves_ui(tmp_path,monkeypatch):
    """Read a supplied saved fit, edit its owned copy; no numerical execution."""
    import hashlib,json,shutil
    from pathlib import Path
    from PySide6.QtCore import QThreadPool
    from PySide6.QtWidgets import QLineEdit
    from apps.lab.server import LabHTTPServer
    from apps.lab.service import LabService
    from caelab.workbench_client import Client
    from caelab.storage import canonical_hash
    source=Path(os.environ['CAE_MATERIAL_UX_STORE']).resolve()
    output=Path(os.environ['CAE_MATERIAL_UX_OUTPUT']).resolve();output.mkdir(parents=True,exist_ok=False)
    reused=os.environ.get('CAE_MATERIAL_UX_REUSE_STORE')
    store=Path(reused).resolve() if reused else output/'store'
    if not reused:shutil.copytree(source,store)
    def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
    originals={str(path.relative_to(source)):digest(path) for path in source.rglob('*') if path.is_file()}
    paths=['apps/research/material_window.py','apps/research/material_plan_panel.py','apps/research/numerical_window.py','tests/test_material_plan_panel.py']
    pins={name:digest(Path(name)) for name in paths}
    (output/'source-launch.json').write_text(json.dumps(pins,indent=2),encoding='utf-8')
    def wait(app,ready):
        deadline=time.monotonic()+30
        while time.monotonic()<deadline:
            app.processEvents()
            if ready():return
            time.sleep(.005)
        raise AssertionError('retained HTTP/Qt read did not settle within 30 seconds')
    app=QApplication.instance() or QApplication([])
    from apps.research.appearance import apply_appearance
    apply_appearance(app)
    service=LabService(store);server=LabHTTPServer(service,0)
    thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.01},daemon=True);thread.start()
    client=Client(f'http://127.0.0.1:{server.server_port}');windows=[]
    allow_once=os.environ.get('CAE_MATERIAL_UX_RUN_ONCE')=='1'
    submitted=[];submit=server.workbench.submit
    def forbidden(*args,**kwargs):raise AssertionError('saved UI must not execute')
    def one_evaluation(operation,arguments,**kwargs):
        assert not submitted and operation=='evaluate' and arguments.get('backend')=='material.felupe'
        assert arguments.get('material_trial')
        submitted.append(deepcopy(arguments))
        return submit(operation,arguments,**kwargs)
    monkeypatch.setattr(server.workbench,'submit',one_evaluation if allow_once else forbidden)
    if not allow_once:monkeypatch.setattr(server.workbench.manager,'submit',forbidden)
    def capture(window,name):
        window.raise_();window.activateWindow();app.processEvents();QTest.qWait(80)
        assert window.grab().save(str(output/(name+'.png')))
    try:
        docs=client.documents()['documents']
        plans=[client.document_read(row['id']) for row in docs if row['kind']=='numerical']
        plan=next(document for document in plans if document.get('runs'))
        material=client.document_read(plan['draft']['material']['document_id'])
        jobs=deepcopy(server.workbench.manager.list());job=plan['runs'][-1]['job_id']
        result=client.document_result(plan['id'],job);result_hash=canonical_hash(result)
        w=MaterialWindow(client,document_id=material['id'],poll_interval=0);windows.append(w);w.show()
        wait(app,lambda:w.document is not None and not w._busy)
        wait(app,lambda:w._plan_panel is not None)
        panel=w._plan_panel
        wait(app,lambda:not panel._busy and panel.plans.findData(plan['id'])>=0)
        panel.plans.setCurrentIndex(panel.plans.findData(plan['id']))
        wait(app,lambda:not panel._busy and len(w.figure.axes)==1)
        assert set(curve['role'] for curve in result['curves']) >= {'fit','holdout'}
        for size,label in (((1440,900),'normal'),((1100,780),'narrow')):
            w.resize(*size);app.processEvents();panel.trials.selectRow(0)
            wait(app,lambda:not panel._busy and len(w.figure.axes)==1)
            capture(w,'material-plan-'+label)
            assert w.canvas.width()>500
        if os.environ.get('CAE_MATERIAL_UX_CAPTURE_ONLY')=='1':
            assert canonical_hash(client.document_result(plan['id'],job))==result_hash
            assert server.workbench.manager.list()==jobs
            assert originals=={str(path.relative_to(source)):digest(path) for path in source.rglob('*') if path.is_file()}
            assert pins=={name:digest(Path(name)) for name in paths}
            (output/'result.json').write_text(json.dumps(dict(platform=app.platformName(),source_pins=pins,
                source=str(source),material_id=material['id'],plan_id=plan['id'],job_id=job,result_sha256=result_hash,
                jobs_before=len(jobs),jobs_after=len(jobs),new_jobs=0,
                scope='Retained-result Windows Qt display only; editing/adoption/cold not exercised'),ensure_ascii=False,indent=2),encoding='utf-8')
            return
        evaluation=None
        candidate_review=None
        if os.environ.get('CAE_MATERIAL_UX_REVIEW_CANDIDATE')=='1':
            from PySide6.QtWidgets import QMessageBox
            before_review=deepcopy(client.document_read(material['id']))
            panel.fit_output.setCurrentIndex(2);panel.review_final_button.click()
            owner=panel._adoption_owner
            wait(app,lambda:owner is not None and bool(owner._candidate_detail_windows))
            detail=owner._candidate_detail_windows[-1]
            wait(app,lambda:detail.view is not None and detail._read_worker is None)
            detail.resize(1100,780);capture(detail,'material-final-coefficient-review')
            cancelled=[]
            with monkeypatch.context() as temporary:
                temporary.setattr(QMessageBox,'question',lambda *a,**k:cancelled.append(True) or QMessageBox.StandardButton.Cancel)
                assert detail.evidence_adopt_button.isEnabled()
                detail.evidence_adopt_button.click()
                wait(app,lambda:not detail._writing and not owner._busy and not owner._callbacks and not owner._pending_adoption)
            candidate_review=dict(preview_cancel=bool(cancelled),message=owner.message.text(),
                exact_original_reference=True,scope='Existing candidate inspection and Cancel or preserved stale refusal; no successful adoption claimed')
            assert client.document_read(material['id'])['draft']==before_review['draft']
            assert not owner._adoption_receipt
            detail.close();app.processEvents()
            wait(app,lambda:not w._busy)
        resumed_evaluation=os.environ.get('CAE_MATERIAL_UX_RESUME_EVALUATION')
        if resumed_evaluation:
            assert not allow_once
            retained=client.document_result(material['id'],resumed_evaluation)
            assert retained['execution_status']=='SUCCEEDED' and retained['material_trial']['source']['document_id']==plan['id']
            assert any(run['job_id']==resumed_evaluation for run in w.document['runs'])
            w._result_cache[resumed_evaluation]=deepcopy(retained)
            w._populate_runs(prefer_job=resumed_evaluation);w.show_material_results()
            wait(app,lambda:not w._busy)
            for size,label in (((1440,900),'normal'),((1100,780),'narrow')):
                w.resize(*size);app.processEvents();capture(w,'material-current-evaluation-'+label)
            evaluation=dict(job_id=resumed_evaluation,result_sha256=canonical_hash(retained),
                parameters=deepcopy(retained['material_trial']['parameters']),source=deepcopy(retained['material_trial']['source']),
                scope='Resumed existing actual03 result; no new evaluation')
        if os.environ.get('CAE_MATERIAL_UX_READONLY')=='1':
            assert not allow_once and not submitted
            assert w.document['draft']==material['draft'] and w.document['saved_revision']==material['saved_revision']
            assert canonical_hash(client.document_result(plan['id'],job))==result_hash
            assert server.workbench.manager.list()==jobs
            assert originals=={str(path.relative_to(source)):digest(path) for path in source.rglob('*') if path.is_file()}
            assert pins=={name:digest(Path(name)) for name in paths}
            w.result_tabs.setCurrentWidget(w.values);capture(w,'material-evaluation-values-narrow')
            assert w.values.rowCount()>0
            (output/'result.json').write_text(json.dumps(dict(platform=app.platformName(),source_pins=pins,
                store=str(store),material_id=material['id'],material_draft=material['draft'],saved_revision=material['saved_revision'],
                plan_id=plan['id'],job_id=job,result_sha256=result_hash,run_once=evaluation,
                jobs_before=len(jobs),jobs_after=len(jobs),new_jobs=0,
                scope='Separate-process saved-owner Windows Qt readback only; no new evaluation/fit'),ensure_ascii=False,indent=2),encoding='utf-8')
            return
        if allow_once:
            panel.trials.selectRow(panel.trials.rowCount()-1)
            panel.coefficient_mode.setCurrentIndex(0);app.processEvents()
            old=w.coefficients.item(0,1).data(Qt.ItemDataRole.UserRole)['original']
            w.coefficients.item(0,1).setText(str(float(old)*1.25))
            w.apply_action.trigger();wait(app,lambda:not w._busy and not w.local_dirty)
            current=deepcopy(w.document);plan_before=deepcopy(client.document_read(plan['id']))
            panel.coefficient_mode.setCurrentIndex(1)
            variables=panel._widgets[plan['id']]
            variables.table.item(0,2).setText('1e')
            w.run_action.trigger();wait(app,lambda:not panel._busy and not w._busy and len(submitted)==1)
            evaluation_job=w.document['runs'][-1]['job_id']
            def evaluated():
                if w._busy:return False
                if evaluation_job in w._result_cache:return True
                w.refresh_results();return False
            wait(app,evaluated)
            evaluated_result=w._result_cache[evaluation_job]
            assert evaluated_result['execution_status']=='SUCCEEDED'
            assert evaluated_result['material_trial']['parameters']==current['draft']['settings']['parameters']
            assert evaluated_result['material_trial']['curves']
            assert w.document['draft']==current['draft'] and w.document['input_revision']==current['input_revision']
            assert client.document_read(plan['id'])['draft']==plan_before['draft']
            assert variables.buffer_snapshot()['variables'][0]['value']=='1e'
            for size,label in (((1440,900),'normal'),((1100,780),'narrow')):
                w.resize(*size);app.processEvents();capture(w,'material-current-evaluation-'+label)
            evaluation=dict(job_id=evaluation_job,result_sha256=canonical_hash(evaluated_result),
                parameters=deepcopy(evaluated_result['material_trial']['parameters']),source=deepcopy(evaluated_result['material_trial']['source']))
            variables.undo_button.click();app.processEvents()
            assert not variables.has_unapplied_buffer()
        last=panel.trials.rowCount()-1;panel.trials.selectRow(last)
        panel.show_trial(force=True)
        wait(app,lambda:not panel._busy and panel._drawn_trial[-1]==plan['draft']['experiments'][last]['id'])
        capture(w,'material-selected-trial-narrow')
        selected=panel.trials.currentRow()
        widget=panel._widgets[plan['id']];widget.table.item(0,2).setText('1e')
        w._material_dock.raise_();panel.coefficient_mode.setCurrentIndex(0);app.processEvents()
        before=deepcopy(w.edited_draft());cell=w.coefficients.item(0,1)
        w.coefficients.setCurrentItem(cell);w.coefficients.editItem(cell);app.processEvents()
        editor=QApplication.focusWidget();assert isinstance(editor,QLineEdit)
        editor.setText('1e');capture(w,'material-unfinished-narrow')
        assert w._active_result_view=='plan' and len(w.figure.axes)==1
        QTest.keyClick(editor,Qt.Key.Key_Escape);app.processEvents()
        assert w.edited_draft()==before
        w._plan_dock.raise_();panel.coefficient_mode.setCurrentIndex(1);app.processEvents()
        assert panel.trials.currentRow()==selected and widget.buffer_snapshot()['variables'][0]['value']=='1e'
        widget.undo_button.click();app.processEvents()
        assert not widget.has_unapplied_buffer()
        w._material_dock.raise_();panel.coefficient_mode.setCurrentIndex(0);app.processEvents()
        binding=w.coefficients.item(0,1).data(Qt.ItemDataRole.UserRole)
        changed=float(binding['original'])+.125
        w.coefficients.item(0,1).setText(str(changed));w.apply_inputs()
        wait(app,lambda:not w._busy and not w.local_dirty)
        assert w.document['draft']['settings']['parameters'][binding['parameter']]==changed
        from apps.research.material_related_save import RelatedSaveDialog
        from PySide6.QtCore import QTimer
        saved_dialogs=[];save_errors=[];save_clicked=[]
        save_timer=QTimer();save_timer.setInterval(10);save_deadline=time.monotonic()+20
        def save_modal():
            dialog=app.activeModalWidget()
            if not isinstance(dialog,RelatedSaveDialog):return
            if time.monotonic()>save_deadline:
                save_errors.append(dialog.message.text());dialog.reject();save_timer.stop();return
            if dialog._busy:return
            if dialog.receipt:
                saved_dialogs.append(deepcopy(dialog.receipt))
                capture(dialog,'material-save-both')
                dialog.close_button.click();save_timer.stop()
            elif dialog.save_button.isEnabled() and not save_clicked:
                save_clicked.append(True);dialog.save_button.click()
        save_timer.timeout.connect(save_modal);save_timer.start()
        try:w.save_action.trigger()
        finally:save_timer.stop()
        assert not save_errors and len(saved_dialogs)==1 and saved_dialogs[0]['all_saved']
        wait(app,lambda:not w._busy and not w.document['dirty'])
        assert w._active_result_view=='plan' and len(w.figure.axes)==1
        saved=deepcopy(w.document)
        w._allow_close=True;w.close();app.processEvents()
        reopened=MaterialWindow(client,document_id=material['id'],poll_interval=0);windows.append(reopened);reopened.show()
        wait(app,lambda:reopened.document is not None and not reopened._busy)
        assert reopened.document['draft']==saved['draft'] and reopened.document['saved_revision']==saved['saved_revision']
        restored=reopened.open_plan_variables()
        wait(app,lambda:not restored._busy and restored.plans.findData(plan['id'])>=0)
        restored.plans.setCurrentIndex(restored.plans.findData(plan['id']));restored.trials.selectRow(selected)
        wait(app,lambda:not restored._busy and len(reopened.figure.axes)==1)
        reopened.resize(1100,780);capture(reopened,'material-reopened-narrow')
        assert client.document_read(plan['id'])['draft']==plan['draft']
        assert canonical_hash(client.document_result(plan['id'],job))==result_hash
        actual_jobs=server.workbench.manager.list()
        assert len(actual_jobs)==len(jobs)+len(submitted)
        assert all(row in actual_jobs for row in jobs)
        assert originals=={str(path.relative_to(source)):digest(path) for path in source.rglob('*') if path.is_file()}
        assert pins=={name:digest(Path(name)) for name in paths}
        record=dict(platform=app.platformName(),source=str(source),material_id=material['id'],plan_id=plan['id'],job_id=job,
            result_sha256=result_hash,source_pins=pins,selected_trial=selected,raw_cancel=True,plan_buffer_preserved=True,
            store=str(store),material_apply_save_reopen=True,related_save_receipt=saved_dialogs[0]['receipt_id'],run_once=evaluation,candidate_review=candidate_review,
            jobs_before=len(jobs),jobs_after=len(actual_jobs),new_jobs=len(submitted),scope='Qt events; no physical OS input or engineering qualification')
        (output/'result.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
    finally:
        for window in reversed(windows):window._allow_close=True;window.close()
        assert QThreadPool.globalInstance().waitForDone(5000)
        app.processEvents();server.shutdown();server.server_close();thread.join(3);service.shutdown()
