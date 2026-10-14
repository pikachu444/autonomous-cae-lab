"""Real Qt and explicit native-owner/process doubles; no FreeCAD or solver."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace as NS
import pytest
W=pytest.importorskip('PySide6.QtWidgets')
C=pytest.importorskip('PySide6.QtCore')
from test_pre_fem_panel_ui import panel, app, native
from test_contact_execution import model
from test_contact_steps import staged, write_snapshot
from apps.desktop_pre.connection import Connection
from apps.research.contact_run_dialog import ContactRunDialog


def prepare_controls(panel,native):
    def q(v): return NS(getValueAs=lambda unit:NS(Value=v))
    for key,v in [('TimePeriod',1.),('TimeInitialIncrement',.1),
                  ('TimeMinimumIncrement',.001),('TimeMaximumIncrement',.2)]:
        setattr(native.solver,key,q(v))
    native.solver.IncrementsMaximum=100
    page=panel.steps_page
    page.refresh(load_forms=True)
    assert page.info and page.buffer
    panel.tabs.setCurrentWidget(page)
    panel.resize(1100,780); panel.show()
    W.QApplication.processEvents()
    return page


def test_steps_partial_owner_apply_late_edit_and_reread(panel,native):
    page=prepare_controls(panel,native)
    page.points.item(1,1).setText('1e')
    page.apply()
    assert panel.test_calls[-1][0]=='pre.contact.steps_set'
    page.points.item(1,1).setText('2e')
    panel.test_complete()
    assert native.metadata['contact_programs'][0]['draft']['steps'][0]['curves'][0]['points'][1][1]=='1e'
    assert page.points.item(1,1).text()=='2e' and page.modified
    page.discard()
    assert page.points.item(1,1).text()=='1e' and not page.modified
    page.points.item(1,1).setText('25.1234567890123')
    page.apply(); panel.test_complete()
    assert not page.modified and native.metadata['keep_other_owner_field']
    from apps.desktop_pre.contact import ContactEditor
    reread=ContactEditor(native.editor).step_inputs(native.analysis)
    assert reread['draft']['steps'][0]['curves'][0]['points'][1][1]=='25.1234567890123'
    page.add()
    assert len(page.buffer['steps'])==2 and page.modified
    page.mode.setCurrentIndex(page.mode.findData('release'))
    assert not page.points.isEnabled()
    page.apply(); panel.test_complete()
    assert native.metadata['contact_programs'][0]['draft']['steps'][1]['curves'][0]['mode']=='release'
    assert page.plot.height()>=170 and panel.size().width()==1100
    assert all(op[0]=='pre.contact.steps_set' for op in panel.test_calls)


def test_input_only_recovered_completion_uses_same_receipt_never_submits(model,tmp_path,app):
    snapshot=write_snapshot(staged(model),tmp_path/'input')
    called=[]
    owner=NS(document_id='Ptest',export_root=tmp_path)
    c=NS(pending={'command_id':'Ctest','document_id':'Ptest','stage':'command','export_only':True},
         owners={'Document':(owner,None,None)},message=W.QLabel(),
         show_export=lambda path:called.append(path),
         submit=lambda:pytest.fail('Input export must not submit a job'))
    Connection.command_status(c,{'command_id':'Ctest','state':'INTERRUPTED','completion_recoverable':True})
    assert c.pending['command_id']=='Ctest' and c.pending['retry']
    Connection.command_status(c,{'command_id':'Ctest','state':'SUCCEEDED',
        'outcome':{'result':{'status':'COMPLETED','result':{'snapshot_relative':'input/snapshot.json'}}}})
    assert c.pending is None and called==[snapshot]
    assert '계산은 실행하지 않았습니다' in c.message.text()


def test_exact_failed_input_opens_saved_copy_not_changed_live_source(model,app,monkeypatch):
    from apps.research import desktop
    calls=[]
    m=staged(model)
    class Runner(W.QWidget):
        def __init__(self):
            super().__init__()
            self.client=NS(
                job_navigation=lambda job:{'origin_document':{'id':'Pchanged','connected':True},
                    'retained_design_input_id':'Dfailed','post_input':{'id':'Dpartial'}},
                native_input=lambda identifier:{'id':identifier,'kind':'frozen_contact',
                    'editable_path':'retained/failed/editable.caepre'})
        def _request(self,key,work,done,**kwargs): done(work(),None)
    monkeypatch.setattr(desktop,'_spawn',lambda client,args:calls.append(args))
    monkeypatch.setattr(desktop,'launch_post',lambda client,identifier,**kw:calls.append(('post',identifier,kw)))
    runner=Runner()
    result={'execution_status':'FAILED','executed_setup':{
        'axis':{'unit':'1'},'program':m['analysis_steps'],'conditions':m['conditions']},
        'increment_history':{'rows':[{'step':2,'increment':1,'attempt':2,'iterations':8,
            'total':.5,'converged':False,'raw':'native U attempt','step_location':{'label':'제하'}}]}}
    dialog=ContactRunDialog(runner,'Jfailed',result)
    dialog.show(); app.processEvents()
    assert dialog.condition.currentText().startswith('누르는 힘')
    assert dialog.points.item(0,1).text()=='10'
    dialog.open_saved(); dialog.open_post()
    assert calls[0]==['pre','--source','retained/failed/editable.caepre','--source-label','계산 조건 수정']
    assert calls[1]==('post','Dpartial',{'job_id':'Jfailed'})
    assert dialog.canvas.height()>170 and dialog.width()==1100
    dialog.close(); runner.close(); app.processEvents()
