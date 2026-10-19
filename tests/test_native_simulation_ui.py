"""Contextual Simulation transport/display only; no native executable or solver."""
from copy import deepcopy
from pathlib import Path
import importlib.util
import sys
import time
import pytest
from PySide6.QtWidgets import QApplication, QLineEdit
from PySide6.QtGui import QFontDatabase

ROOT=next(p for p in Path(__file__).resolve().parents if (p/'apps/research/pde_window.py').is_file())
sys.path.insert(0,str(ROOT))
spec=importlib.util.spec_from_file_location('apps.research.simulation_native_ui_candidate',
    Path(__file__).resolve().parents[1]/'apps/research/simulation_window.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


def document(backend='explicit.opencourant.connector'):
    return {'id':'Vdisplay','kind':'simulation','session_id':'Sdisplay','title':'공개 모델 연결 해석',
        'generation':1,'input_revision':1,'dirty':False,'can_undo':False,'can_redo':False,
        'draft':{'backend':backend,'settings':{'data_id':'Dinput','snapshot_path':'/diagnostic/only/snapshot.json'}},
        'diagnostics':[],'simulation_support':{},'runs':[],'service_platform':'win32'}


class Client:
    def __init__(self,value):self.value=deepcopy(value);self.calls=[];self.url='http://controlled-test'
    def native_input(self,key):return {'id':key,'kind':'frozen_connector','editable_path':'C:/controlled-test/editable.caepre'}
    def document_command(self,id,operation,arguments,**options):
        self.calls.append((operation,deepcopy(arguments)))
        self.value['generation']+=1
        if operation.endswith('.update'):self.value['draft']=deepcopy(arguments['draft'])
        if operation=='document.save':self.value['dirty']=False
        return {'document':deepcopy(self.value),'command_id':options['command_id']}
    def document_read(self,id):return deepcopy(self.value)


class DisplayWindow(module.SimulationWindow):
    # Domain admission and native runtime discovery are tested separately. These
    # doubles isolate visible commands, never certify a backend or native input.
    model_diagnostics=staticmethod(lambda draft:[])
    _execution_environment=staticmethod(lambda: {
        'blocked': False, 'label': 'TEST_ONLY', 'message': 'Controlled transport; no native runtime.'})


@pytest.fixture
def window():
    app=QApplication.instance() or QApplication([])
    for name in ('segoeui.ttf','malgun.ttf'):QFontDatabase.addApplicationFont('C:/Windows/Fonts/'+name)
    value=document();win=DisplayWindow(Client(value),auto_open=False,poll_interval=0)
    win._show_document(value);win.show();app.processEvents()
    yield win,app
    wait(win,app);win._allow_close=True;win.close();app.processEvents()


def wait(win,app):
    deadline=time.monotonic()+5
    while win._busy and time.monotonic()<deadline:app.processEvents();time.sleep(.01)
    app.processEvents();assert not win._busy


@pytest.mark.parametrize('backend',list(module.NATIVE_MODELS))
def test_frozen_profiles_show_model_and_preserve_exact_raw_definition(window,backend):
    win,app=window;value=document(backend);original=deepcopy(value['draft']);win._show_document(value);app.processEvents()
    assert win.backend.isHidden() and win._backend_note.isHidden()
    assert win._nodes[('settings','data_id')].text(0)=='입력 모델'
    assert win._nodes[('settings','snapshot_path')].isHidden()
    assert not win.fields and win.edited_draft()==original
    assert 'Dinput' in win.messages.toPlainText() and not win.messages.isVisible()
    assert not any(field.isVisible() and field.text()=='Dinput' for field in win.findChildren(QLineEdit))
    assert win.identity.text()==value['title'] and win.save_action.isEnabled() and win.evaluate_button.isVisible()


def test_registered_input_open_reuses_real_desktop_helper_and_never_runs(window,monkeypatch):
    win,app=window
    from apps.research import desktop
    launched=[];monkeypatch.setattr(desktop,'_spawn',lambda client,args:launched.append(args) or {'status':'LAUNCH_REQUESTED'})
    original=win.edited_draft();assert win.open_input_model();wait(win,app)
    assert launched==[['pre','--source','C:/controlled-test/editable.caepre','--source-label','해석 입력 모델']]
    assert win.edited_draft()==original and not win.client.calls
    assert '요청' in win.message.text() and '완료' not in win.message.text()


def test_dirty_conflict_bad_id_and_late_document_do_not_open_or_misreport(window,monkeypatch):
    win,app=window
    for attr in ('local_dirty','conflict','_busy'):
        setattr(win,attr,True);assert not win.open_input_model();setattr(win,attr,False)
    win._draft['settings']['data_id']='../unbound';win._update_actions()
    assert not win.input_model_action.isEnabled() and not win.open_input_model()
    win._draft['settings']['data_id']='Dinput';callbacks=[]
    win._call=lambda f,accepted:callbacks.append(accepted) or True
    win.message.setText('이전 안내');assert win.open_input_model()
    win.document['generation']+=1;callbacks[0]({'status':'LAUNCH_REQUESTED'})
    assert win.message.text()=='이전 안내'


def test_legacy_editing_and_explicit_save_run_commands_remain_existing_paths(window):
    win,app=window
    assert win.evaluate_button.text()=='계산 실행'
    win.save_document();wait(win,app);assert win.client.calls[-1][0]=='document.save'
    win.evaluate();wait(win,app);assert win.client.calls[-1][0]=='simulation.evaluate'
    value=document('structural.code_aster.plasticity');value['draft']['settings']={'case':'uniaxial_j2_isotropic_hardening'}
    win._show_document(value);app.processEvents()
    assert not win.backend.isHidden() and not win.input_model_action.isVisible()
    assert ('settings','case') in win.fields and win.evaluate_button.text()=='모델 평가'


@pytest.mark.parametrize('backend', [{}, []])
def test_invalid_backend_draft_stays_editable_without_native_commands(window, backend):
    win,app=window; value=document(backend)
    win._show_document(value); app.processEvents()
    assert win._draft['backend']==backend
    assert not win.backend.isHidden() and not win.input_model_action.isVisible()
    assert win.evaluate_button.text()=='모델 평가' and not win.client.calls


def test_connector_actual_unit_labels_and_invalid_gaps_preserve_raw_arrays(window):
    win,app=window;win._selected_job='Jdisplay'
    response={'kind':'series','value':[1.,None,3.],'unit':'N','axes':[{'name':'time','unit':'s','values':[0.,.1,.2]}],
        'has_calculation_gaps':True,'segments':[{'rows':[0,1]},{'rows':[2,3]}]}
    payload={'backend':'explicit.opencourant.connector','execution_status':'FAILED',
        'responses':{'connector.FX':response},'native_channels':{'connector.FX':{'unit':'N','node_ids':[1]}},
        'diagnostics':{'scope':'controlled display only'},'failure':'화면 시험의 보존 실패'}
    win._accept_result(payload);app.processEvents()
    assert win._result==payload and win.channel.itemData(0)=='connector.FX'
    assert win.channel.itemText(0)=='국부 일반화 힘 X [N]'
    assert win.result_axes.get_xlabel()=='시간 [s]' and win.result_axes.get_ylabel()=='국부 일반화 힘 X [N]'
    assert len(win.result_axes.lines)==2 and '실패' in win.issue_summary.text()
