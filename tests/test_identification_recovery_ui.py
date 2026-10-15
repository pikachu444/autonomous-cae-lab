"""Saved-fit read recovery only. No new numerical/provider evaluation."""
import time
from copy import deepcopy

import pytest
pytest.importorskip('PySide6')
pytest.importorskip('matplotlib')
from PySide6.QtCore import QThreadPool
from PySide6.QtTest import QTest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from apps.research.identification_window import IdentificationWindow


def wait(app, predicate):
    limit=time.monotonic()+5
    while time.monotonic()<limit:
        app.processEvents()
        if predicate():return
        time.sleep(.005)
    raise AssertionError('Saved read did not settle')


def test_failed_saved_fit_read_retry_keeps_authored_question_and_exact_result():
    app=QApplication.instance() or QApplication([])
    class Client:
        reads=[]
        fail=True
        def document_read(self, identifier):
            self.reads.append(('document',identifier))
            if self.fail:
                self.fail=False
                raise OSError('saved source temporarily unavailable')
            return {'runs':[{'job_id':'Jfit','draft':{'variables':[]}}]}
        def document_result(self,identifier,job_id):
            self.reads.append(('result',identifier,job_id))
            return {'kind':'fit','parameters':{},'identification':{'reason':'No retained diagnosis'}}
        def document_result_reference(self,identifier,job_id):
            return {'document_id':identifier,'job_id':job_id,'input_revision':'Rinput','result_sha256':'a'*64}
    client=Client();window=IdentificationWindow(client,'Nsaved','Jfit')
    try:
        window.question.setText('다음 시험에서 측정 위치의 영향을 확인한다')
        window.note.setPlainText('제공되지 않은 불확실성은 추정하지 않는다')
        window.show()
        wait(app,lambda:not window._workers)
        window.question.setFocus()
        QTest.keyClick(window.question,Qt.Key.Key_Return)
        assert window.isVisible()
        assert not window.keep.isEnabled() and not window.report.isEnabled()
        assert window.reload_result.isEnabled()
        assert 'saved source temporarily unavailable' in window.message.text()
        authored=(window.question.text(),window.note.toPlainText())
        QTest.mouseClick(window.reload_result,Qt.MouseButton.LeftButton)
        wait(app,lambda:not window._workers and window._payload is not None)
        assert (window.question.text(),window.note.toPlainText())==authored
        assert window.keep.isEnabled() and window.report.isEnabled()
        assert client.reads==[('document','Nsaved'),('document','Nsaved'),('result','Nsaved','Jfit')]
        assert window._payload[3]['input_revision']=='Rinput'
    finally:
        window.close()
        assert QThreadPool.globalInstance().waitForDone(5000)
        window.deleteLater();app.processEvents()


def test_final_detail_uses_retained_id_and_exact_reference_only(monkeypatch):
    app=QApplication.instance() or QApplication([])
    monkeypatch.setattr(IdentificationWindow,'_read',lambda self:None)
    import apps.research.numerical_candidate_detail_window as module
    from PySide6.QtWidgets import QMainWindow
    opened=[]
    class Detail(QMainWindow):
        def __init__(self,client,**kwargs):
            super().__init__(kwargs['parent']);opened.append(kwargs)
    monkeypatch.setattr(module,'NumericalCandidateDetailWindow',Detail)
    reference={'document_id':'Nold','job_id':'Jold','input_revision':'Rold',
        'input_sha256':'a'*64,'result_sha256':'b'*64}
    document={'session_id':'Sopened'}
    run={'draft':{'variables':[]}}
    result={'kind':'fit','parameters':{},'candidates':[{'candidate_id':'Clatest','values':{}}]}
    window=IdentificationWindow(object(),'Nold','Jold')
    try:
        window.show_result((document,run,deepcopy(result),reference))
        assert not window.final_detail.isEnabled()
        window.open_final_detail();assert opened==[]
        result['final_candidate_detail']={'retention':'NOT_RETAINED_AMBIGUOUS_FINAL_CANDIDATE'}
        window.show_result((document,run,deepcopy(result),reference))
        assert not window.final_detail.isEnabled()
        result['final_candidate_detail']={'candidate_id':'Cexact','retention':'PARTIAL_RETENTION'}
        window.show_result((document,run,deepcopy(result),reference))
        assert window.final_detail.isEnabled()
        window.open_final_detail()
        assert len(opened)==1 and opened[0]['candidate_id']=='Cexact'
        assert opened[0]['source']==reference and opened[0]['source'] is not reference
        assert opened[0]['session_id']=='Sopened'
        assert 'adopt_callback' not in opened[0]
        child=window._detail_windows[0];assert child.isVisible()
        window.done(0);assert not child.isVisible()
    finally:window.close();window.deleteLater();app.processEvents()


def test_original_diagnosis_is_optional_and_read_only(monkeypatch):
    import json
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QPlainTextEdit
    app=QApplication.instance() or QApplication([])
    monkeypatch.setattr(IdentificationWindow,'_read',lambda self:None)
    original={'status':'UNKNOWN','reason':'UNSUPPORTED_PRIVATE_REASON','raw_jacobian_ref':'Jinternal'}
    reference={'document_id':'Nold','result_sha256':'c'*64}
    window=IdentificationWindow(object(),'Nold','Jold');read=[]
    try:
        window.show_result(({}, {'draft':{'variables':[]}},
            {'kind':'fit','identification':deepcopy(original)},reference))
        assert 'UNSUPPORTED_PRIVATE_REASON' not in window.summary.text()
        def inspect():
            dialog=app.activeModalWidget()
            editor=dialog.findChild(QPlainTextEdit)
            read.append((json.loads(editor.toPlainText()),editor.isReadOnly()))
            dialog.reject()
        QTimer.singleShot(0,inspect);window.open_diagnostics()
        assert read==[({'identification':original,'reference':reference},True)]
        assert window._payload[2]['identification']==original
    finally:window.close();window.deleteLater();app.processEvents()


def test_nonfit_clears_fit_view_blocks_actions_and_recovers_on_fit(monkeypatch):
    """State-only Qt regression; no shown window, worker, model or provider."""
    app=QApplication.instance() or QApplication([])
    monkeypatch.setattr(IdentificationWindow,'_read',lambda self:None)
    window=IdentificationWindow(object(),'Nretained','Jretained')
    run={'draft':{'variables':[{'id':'E','free':True,'unit':'MPa'}]}}
    result={'kind':'fit','parameters':{'E':1000},'final_candidate_detail':{'candidate_id':'Cfinal'}}
    reference={'document_id':'Nretained','job_id':'Jretained'}
    try:
        window.show_result(({},run,result,reference))
        assert window.table.rowCount()==1
        assert all(button.isEnabled() for button in (window.keep,window.report,window.final_detail))
        window.figure.subplots().plot([0,1],[2,3])
        window.question.setText('다음 시험 질문')
        window.note.setPlainText('보존할 작성 내용')
        # A look-alike final field does not make a non-fit response a fit result.
        window.show_result(({},run,{'kind':'evaluate','final_candidate_detail':{'candidate_id':'Cother'}},reference))
        assert window.table.rowCount()==0 and not window.figure.axes
        assert not any(button.isEnabled() for button in (window.keep,window.report,window.final_detail))
        window._run=lambda *args:pytest.fail('Non-fit response submitted an action')
        window.save_study();window.open_report()
        # Guard the handler itself, including stale/enabled button state.
        window.final_detail.setEnabled(True);window.open_final_detail();window._update_actions()
        assert not hasattr(window,'_detail_windows') and not hasattr(window,'_children')
        window.show_result(({},run,result,reference))
        assert window.table.rowCount()==1
        assert all(button.isEnabled() for button in (window.keep,window.report,window.final_detail))
        assert window.question.text()=='다음 시험 질문' and window.note.toPlainText()=='보존할 작성 내용'
    finally:window.close();window.deleteLater();app.processEvents()
