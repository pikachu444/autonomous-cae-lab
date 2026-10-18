"""Scoped Sol GUI recovery tests; no evaluator/provider/native host available."""
from copy import deepcopy
import pytest
pytest.importorskip('PySide6')
from PySide6.QtWidgets import QApplication
from apps.research.experiment_analysis_window import ExperimentAnalysisWindow


@pytest.fixture
def empty_window(monkeypatch):
    app=QApplication.instance() or QApplication([])
    monkeypatch.setattr(ExperimentAnalysisWindow,'_call',lambda *_args:False)
    window=ExperimentAnalysisWindow(object(),source={'kind':'result_response','reference':{},'response':'force'})
    yield app,window
    window.dirty=False;window._pending=None;window._study_pending=None
    window.close();window.deleteLater();app.processEvents()


def test_initial_source_failure_has_same_source_read_retry_without_new_action(empty_window):
    _,window=empty_window
    source=deepcopy(window.source);calls=[]
    window._finished(None,OSError('missing retained file'))
    assert window.read.isEnabled() and window.read.text()=='원자료 다시 읽기'
    assert not window.run.isEnabled() and not window.save.isEnabled()
    window._call=lambda fn,done:calls.append((fn,done))
    window._read_result()
    assert calls==[(window._load,window._loaded)]
    assert window.source==source and window._pending is None


def test_next_test_appends_to_existing_study_and_lost_save_retry_is_same_action(empty_window,monkeypatch):
    _,window=empty_window
    from caelab.study_document import default_draft,diagnostics
    import apps.research.study_window as study
    import apps.research.experiment_analysis_window as module
    ref={'document_id':'Nanalysis','job_id':'Janalysis','input_revision':'Rinput',
        'input_sha256':'a'*64,'result_sha256':'b'*64}
    draft=default_draft();draft['question']='사용자가 이미 작성한 연구 질문'
    draft['evidence']=[{'id':'Eexisting','kind':'result','label':'기존 선택 결과',
        'reference':{'kind':'result',**ref},'note':'기존 원자료 메모'}]
    draft['next_observations']=[{'id':'Oexisting','question':'이미 작성한 다음 시험',
        'hypothesis_ids':[],'evidence_ids':['Eexisting'],'status':'PLANNED','note':'기존 판단'}]
    assert not diagnostics(draft)
    class Client:
        def __init__(self):
            self.doc={'id':'Sstudy','session_id':'Ssession','generation':2,'draft':deepcopy(draft)}
            self.receipts={};self.fail=True;self.created=0
        def document_result_reference(self,*_):return deepcopy(ref)
        def result_followup(self,*_,**kwargs):
            self.created+=1;return {'document':deepcopy(self.doc)}
        def document_read(self,*_):return deepcopy(self.doc)
        def document_command(self,identifier,operation,arguments,**kwargs):
            key=kwargs['command_id']
            if key not in self.receipts:
                assert kwargs['expected_generation']==self.doc['generation']
                if operation=='study.update':self.doc['draft']=deepcopy(arguments['draft'])
                self.doc['generation']+=1;self.receipts[key]={'document':deepcopy(self.doc)}
            if operation=='document.save' and self.fail:
                self.fail=False;raise OSError('save committed but reply lost')
            return deepcopy(self.receipts[key])
    class Child:
        def __init__(self,*args,**kwargs):pass
        def show(self):pass
    monkeypatch.setattr(study,'StudyWindow',Child)
    monkeypatch.setattr(module,'choose_next_observation',lambda *args:{'question':'새로 확인할 시험 질문','note':'명시한 시험 조건'})
    window.client=Client();window.document={'id':'Nanalysis','session_id':'Ssession'}
    window.job_id=window._shown_job_id='Janalysis';window.result={'kind':'experiment_uncertainty'}
    window._call=lambda fn,done,**_kwargs:done(fn())
    with pytest.raises(OSError):window._study()
    pending=window._study_pending
    assert pending is not None
    window._study()
    saved=window.client.doc['draft']
    assert saved['question']==draft['question']
    assert saved['evidence']==draft['evidence']
    assert saved['next_observations'][0]==draft['next_observations'][0]
    assert [row['question'] for row in saved['next_observations']]==['이미 작성한 다음 시험','새로 확인할 시험 질문']
    assert len(window.client.receipts)==2 and window.client.created==1
    assert window._study_pending is None


def test_close_abandons_only_read_delivery_and_protects_uncertain_writes(empty_window):
    _,window=empty_window
    class Read:
        abandoned=False
        def abandon(self):self.abandoned=True
    worker=Read();window._worker=worker;window._worker_writes=True
    window.done(0)
    assert not window._closed and not worker.abandoned
    window._worker_writes=False;window.done(0)
    assert window._closed and worker.abandoned and window._worker is None
    assert not window.timer.isActive()
    window._callback=lambda *_:pytest.fail('Late read delivery reached a closed window')
    window._finished({},None)


def test_saved_terminal_integrity_failure_does_not_fall_back_to_live_status_or_source(empty_window):
    _,window=empty_window
    class Client:
        def document_read(self,identifier):
            return {'id':identifier,'draft':{'request':{'operation':'experiment_uncertainty','inputs':{'source':{}}}},
                'runs':[{'job_id':'Jold','retained_state':'SUCCEEDED','retention_complete':True}]}
        def document_result(self,*_):raise ValueError('retained hash mismatch')
        def status(self,*_):pytest.fail('Saved terminal failure consulted live status')
    window.client=Client();window._document_id='Nold'
    with pytest.raises(ValueError,match='retained hash mismatch'):window._load()


@pytest.mark.parametrize('has_result',[False,True])
def test_interrupted_empty_plan_reads_same_source_for_explicit_new_run_only(empty_window,monkeypatch,has_result):
    _,window=empty_window
    import apps.research.experiment_analysis_window as module
    source={'kind':'result_response','reference':{'job_id':'Joriginal'},'response':'force'}
    reads=[]
    class Client:
        def document_read(self,identifier):
            return {'id':identifier,'draft':{'request':{'operation':'experiment_uncertainty',
                'inputs':{'source':deepcopy(source),'plan_mask':[True,False]}}},'runs':[{'job_id':'Jinterrupted'}]}
        def document_result(self,*_):raise ValueError('no retained result')
        def status(self,job):
            assert job=='Jinterrupted'
            return {'state':'INTERRUPTED','result_refs':['results/Jinterrupted'] if has_result else []}
        def document_command(self,*_a,**_k):pytest.fail('opening submitted a command')
    def read(*_a,**kwargs):reads.append(kwargs);return {'problem':{'original':True}}
    monkeypatch.setattr(module,'read_analysis_source',read)
    window.client=Client();window._document_id='Nsame'
    if has_result:
        with pytest.raises(ValueError,match='no retained result'):window._load()
        assert not reads
    else:
        view,doc,result,job,request,selected,_=window._load()
        assert view['interrupted_without_result'] and doc['id']=='Nsame'
        assert result is job is None and selected==source
        assert reads==[{'source':source,'evidence_reference':None,'plan_mask':[True,False]}]


def test_reread_keeps_table_selection_only_for_the_same_saved_job(empty_window,monkeypatch):
    _,window=empty_window
    import apps.research.experiment_analysis_window as module
    monkeypatch.setattr(module,'blocks',lambda _: [('table',(['표본 순서','원값 [N]'],[[i,i+.5] for i in range(30)]))])
    window.job_id='Jsaved';window._show_result({})
    window.results.setCurrentCell(5,0);window.results.item(5,1).setSelected(True)
    window._show_result({})
    assert (window.results.currentRow(),window.results.currentColumn())==(5,0)
    assert {(index.row(),index.column()) for index in window.results.selectedIndexes()}=={(5,0),(5,1)}
    window.job_id='Jother';window._show_result({})
    assert not window.results.selectedIndexes()


def test_source_close_waits_for_owned_analysis_cancel_then_closes_normally():
    from PySide6.QtWidgets import QMainWindow, QDialog
    from PySide6.QtCore import QEvent
    from apps.research.experiment_analysis_window import _AnalysisCloseGuard
    app=QApplication.instance() or QApplication([])
    source=QMainWindow()
    class Child(QDialog):
        allow=False
        def closeEvent(self,event):
            if self.allow:event.accept()
            else:event.ignore()
    child=Child(source);guard=_AnalysisCloseGuard(source,[child]);source.installEventFilter(guard)
    try:
        close=QEvent(QEvent.Type.Close)
        assert guard.eventFilter(source,close) is True and not close.isAccepted()
        child.allow=True;close=QEvent(QEvent.Type.Close)
        assert guard.eventFilter(source,close) is False
    finally:child.allow=True;child.close();source.close();source.deleteLater();app.processEvents()


def test_shared_source_opener_keeps_parent_when_owned_analysis_refuses_close(monkeypatch):
    from PySide6.QtWidgets import QMainWindow,QDialog
    import apps.research.experiment_analysis_window as module
    app=QApplication.instance() or QApplication([])
    source=QMainWindow();source.client=object()
    class Child(QDialog):
        allow=False
        def __init__(self,client,*,source,evidence_reference,parent):super().__init__(parent)
        def closeEvent(self,event):
            if self.allow:event.accept()
            else:event.ignore()
    monkeypatch.setattr(module,'ExperimentAnalysisWindow',Child)
    child=module.show_analysis_window(source,source={'selected':'retained'})
    source.show()
    try:
        assert not source.close() and source.isVisible()
        child.allow=True
        assert source.close()
    finally:
        child.allow=True;child.close();source.close();source.deleteLater();app.processEvents()
