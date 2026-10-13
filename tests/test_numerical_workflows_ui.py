"""Focused real Qt + real owners; algebra is an explicit test-only evaluator."""
import os
os.environ['QT_QPA_PLATFORM']='offscreen'
from copy import deepcopy
from types import SimpleNamespace
import time
import pytest
pytest.importorskip('PySide6')
pytest.importorskip('scipy')
from PySide6.QtCore import QThreadPool
from PySide6.QtWidgets import QApplication,QInputDialog,QMessageBox
from apps.research.request_plan_window import RequestPlanWindow
from apps.research.numerical_methods import MethodDialog
from caelab.workbench import Workbench
from caelab.numerical_document import request_draft
from caelab.material_document import default_draft
from caelab.backends import Backend,_registry


class Client:
    """In-process transport only; owner, jobs and numerical calculations are real."""
    def __init__(self,wb):self.wb=wb
    def __getattr__(self,name):return getattr(self.wb,name)
    def status(self,identifier):return self.wb.manager.status(identifier)


def wait(app,predicate,window=None):
    deadline=time.monotonic()+10
    while time.monotonic()<deadline:
        app.processEvents()
        if predicate():return
        time.sleep(.005)
    raise AssertionError(window.message.text() if window else 'Qt callback did not settle')


@pytest.fixture
def environment(tmp_path):
    app=QApplication.instance() or QApplication([])
    wb=Workbench(tmp_path)
    windows=[]
    def open_window(draft=None,identifier=None):
        w=RequestPlanWindow(Client(wb),auto_open=False,poll_interval=0)
        windows.append(w);w.show()
        w.open_document(document_id=identifier,draft=draft)
        wait(app,lambda:w.document is not None and not w._busy,w)
        return w
    yield app,wb,open_window
    for w in windows:
        w.timer.stop()
        wait(app,lambda:not w._busy and not w._callbacks,w)
        w._allow_close=True;w.close()
    assert QThreadPool.globalInstance().waitForDone(3000)
    app.processEvents()
    assert wb.shutdown()['joined']
    for w in windows:w.deleteLater()
    app.processEvents()


def request(operation,inputs,budget=32):
    return request_draft({'purpose':'공개 수치 연구','operation':operation,
                          'inputs':inputs,'budget':{'evaluations':budget}})


def inputs():
    return {'backend':'test.d6.ui','settings':{},
        'variables':[dict(id='x',unit='1',value=.5,lower=0.,upper=1.,transform='linear')],
        'distributions':{'x':dict(distribution='uniform',unit='1',lower=0.,upper=1.)},
        'source':dict(origin='SYNTHETIC',reference='Public algebra; not engineering evidence'),
        'independence':'INDEPENDENT_USER_DECLARED','count':32,'seed':4,
        'thresholds':[dict(response='cost',unit='MPa',reduction='none',component='scalar',location='model',limit=.25,operator='>')]}


def install_algebra(monkeypatch):
    def evaluate(values,settings):
        x=values['x']
        if settings.get('fail') and x>.75:
            return {'execution_status':'FAILED','responses':{},'diagnostics':{'failure_reason':'Declared failure'}}
        return {'execution_status':'SUCCEEDED','responses':{'cost':{
            'kind':'scalar','value':x*x,'unit':'MPa','component':'scalar','location':'model','reduction':'none'}}}
    monkeypatch.setitem(_registry,'test.d6.ui',Backend('test.d6.ui',('prepared',),lambda:evaluate))


def save(app,w):
    w.save_document()
    wait(app,lambda:not w._busy and not w.local_dirty and bool(w.document.get('saved_revision')),w)


def execute(app,wb,w):
    if w.local_dirty:
        w.apply_inputs();wait(app,lambda:not w._busy and not w.local_dirty,w)
    assert not w.document['diagnostics'],w.document['diagnostics']
    before=len(wb.manager.list())
    w.run_button.click()
    wait(app,lambda:len(wb.manager.list())==before+1 and not w._busy,w)
    job=w.selected_job()
    wait(app,lambda:wb.manager.status(job)['state'] in {'SUCCEEDED','FAILED','PARTIAL_FAILURE','REJECTED'},w)
    assert wb.manager.status(job)['state'] in {'SUCCEEDED','PARTIAL_FAILURE'},wb.manager.status(job)
    w.retry_result();wait(app,lambda:not w._busy and job in w._result_cache,w)
    return job,w._result_cache[job]


def test_distribution_draft_cancel_partial_save_reopen_repair(environment,monkeypatch):
    app,wb,open_window=environment
    install_algebra(monkeypatch)
    value=inputs();value['distributions']['x']['operator_note']='keep extension'
    w=open_window(request('uq',value))
    before=deepcopy(w.edited_draft())
    d=MethodDialog(w,value,'uq')
    d.tables[0].item(0,4).setText('1e')
    d.reject()
    assert w.edited_draft()==before
    edited=d.value()
    assert edited['distributions']['x']['std']=='1e'
    assert edited['distributions']['x']['operator_note']=='keep extension'
    # Required count partial text blocks execution but is an ordinary saved draft.
    w.method_sheet.item(0,1).setText('1e')
    save(app,w)
    assert w.document['diagnostics'] and not w.run_button.isEnabled()
    reopened=open_window(identifier=w.document['id'])
    assert reopened.method_sheet.item(0,1).text()=='1e'
    reopened.method_sheet.item(0,1).setText('32')
    save(app,reopened)
    assert not reopened.document['diagnostics']
    reopened.undo_action.trigger()
    wait(app,lambda:not reopened._busy and reopened.method_sheet.item(0,1).text()=='1e',reopened)
    reopened.redo_action.trigger()
    wait(app,lambda:not reopened._busy and reopened.method_sheet.item(0,1).text()=='32',reopened)
    assert wb.manager.list()==[]


def test_actual_uq_linked_rows_full_width_and_late_read_preserves_edit(environment,monkeypatch):
    app,wb,open_window=environment
    install_algebra(monkeypatch)
    value=inputs();value['settings']['fail']=True
    w=open_window(request('uq',value))
    job,result=execute(app,wb,w)
    w.work_pages.setCurrentWidget(w.results_panel)
    assert '전체 32 / 유효 24' in w.result_summary.text()
    assert str(8/24) in w.result_summary.text() and str(8/32) in w.result_summary.text()
    artist=w.figure.axes[0].collections[0]
    identifier=artist._candidate_ids[4]
    w._candidate_plot_picked(SimpleNamespace(artist=artist,ind=[4]))
    assert w._selected_actual_candidate()['candidate_id']==identifier
    for size in ((1100,780),(1440,900)):
        w.resize(*size);app.processEvents()
        assert w.canvas.width()>700
        assert w.canvas.height()>170
    w._edit_structure(lambda current:current['thresholds'][0].update(unit='Pa'))
    draft=deepcopy(w.edited_draft())
    w._draw_result()  # A result callback only redraws the frozen run.
    assert w.edited_draft()==draft and w.work_pages.currentWidget() is w.results_panel
    assert w._selected_actual_candidate()['candidate_id']==identifier
    assert '[MPa]' in w.figure.axes[0].get_xlabel()
    assert result['probability_statistics'][0]['threshold']['unit']=='MPa'
    w._result_cache.pop(job)
    w._draw_result()
    assert not w.result_summary.text()


def test_independent_plan_selects_real_saved_material_and_runs_existing_adapter(environment,monkeypatch):
    pytest.importorskip('felupe')
    app,wb,open_window=environment
    model=wb.document_open(kind='material',title='공개 탄성 시험',draft=default_draft())
    model=wb.document_command(model['id'],'document.save',{},session_id=model['session_id'],
        expected_generation=model['generation'])['document']
    model_before=deepcopy(model['draft'])
    w=open_window(request('doe',{'backend':'','settings':{},'variables':[],'count':2,'seed':4},2))
    monkeypatch.setattr(QInputDialog,'getItem',lambda parent,title,label,items,**kwargs:(items[0],True))
    monkeypatch.setattr(QMessageBox,'question',lambda *a,**k:QMessageBox.StandardButton.Yes)
    w.choose_model_document()
    wait(app,lambda:not w._busy and w.backend.text()=='material.felupe',w)
    monkeypatch.setattr(w,'_select_model_variables',lambda rows:[row for row in rows if row['id']=='E'])
    w.choose_model_variables()
    wait(app,lambda:not w._busy and w.variable_sheet.rowCount()==1,w)
    assert w.variable_sheet.item(0,0).text()=='탄성계수'
    assert w.edited_draft()['source']['document_id']==model['id']
    job,result=execute(app,wb,w)
    assert len(result['candidates'])==2
    assert all(row['execution_status']=='SUCCEEDED' for row in result['candidates'])
    assert result['candidates'][0]['responses']['stress_xx']['unit']==model_before['settings']['stress_unit']
    save(app,w)
    reopened=open_window(identifier=w.document['id'])
    assert reopened.document['runs'][-1]['job_id']==job
    assert wb.document_read(model['id'])['draft']==model_before
