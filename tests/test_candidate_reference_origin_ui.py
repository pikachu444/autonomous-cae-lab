"""Bounded integration test for the proposed candidate-reference common patch.

Scripted retained rows/reader and a detail-window double verify presentation and
navigation only. They do not certify Numerical snapshot admission or model output.
No provider, evaluator, command, native host or real calculation is available.
"""
from copy import deepcopy

import pytest
pytest.importorskip('PySide6')
pytest.importorskip('matplotlib')
from PySide6.QtWidgets import QComboBox, QMainWindow
from apps.research.reference_window import ReferenceWindow
from caelab.numerical_candidate_evidence import evidence_reference
from test_reference_window import application, Reader, wait
from test_numerical_candidate_report_presentation import presentation


def retained(presentation):
    content,_=presentation
    content=deepcopy(content)
    snapshot=content['candidate_evidence']['snapshot']
    snapshot['source']={'document_id':'Norigin','job_id':'Joriginal','input_revision':'Rinput',
        'input_sha256':'a'*64,'result_sha256':'b'*64}
    snapshot['attempt_chain']=[]
    reference=evidence_reference('Norigin','Rsaved',snapshot)
    content['candidate_evidence']['reference']=deepcopy(reference)
    return reference,dict(content,status='AVAILABLE',reference=deepcopy(reference))


def test_saved_candidate_origin_keeps_exact_attempt_and_retries_open_without_evaluation(
        application,presentation,monkeypatch):
    import apps.research.numerical_candidate_detail_window as module
    reference,payload=retained(presentation)
    reader=Reader([payload]);calls=[]
    class Detail(QMainWindow):
        def __init__(self,client,**kwargs):
            super().__init__(kwargs['parent'])
            self.evidence_purpose=QComboBox()
            self.evidence_purpose.addItem('성공 결과','success_judgment')
            self.evidence_purpose.addItem('실패 기록','failure_diagnostic')
            self.refreshed=[]
        def refresh(self):
            self.refreshed.append(self.attempt_job_id)
    def open_detail(client,**kwargs):
        calls.append(deepcopy({k:v for k,v in kwargs.items() if k!='parent'}))
        if len(calls)==1:raise OSError('original source temporarily unavailable')
        return Detail(client,**kwargs)
    monkeypatch.setattr(module,'NumericalCandidateDetailWindow',open_detail)
    window=ReferenceWindow(reader,reference)
    try:
        wait(application,lambda:not window._busy)
        before=window.content.body.toPlainText()
        assert '인장 시험' in before and 'MPa' in before and '원단위 잔차' in before
        assert 'Joriginal' not in before and 'Cprivate-candidate' not in before
        assert window.open_button.text()=='선택 후보 상세 열기'
        assert window.open_owner() is False
        assert window.content.body.toPlainText()==before
        assert window.open_owner() is True and calls[0]==calls[1]
        assert calls[1]['auto_load'] is False and calls[1]['source']==reference['source']
        assert calls[1]['candidate_id']==reference['candidate_id']
        child=window._candidate_windows[0]
        assert child.refreshed==[reference['attempt_job_id']]
        assert window.reference==reference and reader.calls==[reference]
        window.close();assert not child.isVisible()
    finally:window.close();window.deleteLater();application.processEvents()


def test_candidate_read_error_retains_last_snapshot_and_same_reference_retry(application,presentation):
    reference,payload=retained(presentation)
    reader=Reader([payload,OSError('private missing original file'),payload])
    window=ReferenceWindow(reader,reference)
    try:
        wait(application,lambda:not window._busy)
        before=window.content.body.toPlainText()
        window.retry();wait(application,lambda:not window._busy)
        assert window.content.body.toPlainText()==before
        assert '마지막으로 읽은 저장 내용' in window.message.text()
        assert 'private missing' not in window.message.text()
        assert not window.open_button.isEnabled() and window.retry_action.isEnabled()
        window.retry();wait(application,lambda:not window._busy)
        assert window.open_button.isEnabled() and window.content.body.toPlainText()==before
        assert reader.calls==[reference,reference,reference]
        assert window.content.payload['candidate_evidence']['snapshot']==payload['candidate_evidence']['snapshot']
    finally:window.close();window.deleteLater();application.processEvents()


def test_reference_close_waits_for_candidate_analysis_discard_before_retiring_reader(
        application,presentation,monkeypatch):
    """Actual Reference -> candidate -> analysis close guards, readers controlled."""
    from shiboken6 import isValid
    import apps.research.experiment_analysis_window as analysis_module
    import apps.research.numerical_candidate_detail_window as detail_module
    from PySide6.QtWidgets import QMessageBox
    reference,payload=retained(presentation)
    monkeypatch.setattr(detail_module.NumericalCandidateDetailWindow,'refresh',lambda *_:None)
    monkeypatch.setattr(analysis_module.ExperimentAnalysisWindow,'_call',lambda *_a,**_k:False)
    answer=QMessageBox.StandardButton.Cancel
    monkeypatch.setattr(QMessageBox,'question',lambda *_a,**_k:answer)
    window=ReferenceWindow(Reader([payload]),reference);window.show()
    child=analysis=None
    class Signal:
        disconnected=False
        def disconnect(self,*_):self.disconnected=True
    class Worker:
        abandoned=False
        def __init__(self):
            from types import SimpleNamespace
            self.signals=SimpleNamespace(finished=Signal())
        def abandon(self):self.abandoned=True
    worker=Worker()
    try:
        wait(application,lambda:not window._busy)
        assert window.open_owner()
        child=window._candidate_windows[0]
        child._evidence_reference=deepcopy(reference);child.evidence_preserved.emit(reference)
        child._experiment_diagnosis_action.trigger()
        analysis=child._experiment_analysis_children[0];analysis.dirty=True
        window._workers.append(worker)
        assert not window.close()
        assert window.isVisible() and not window._closed
        assert not child._closed and child.timer.isActive() and analysis.isVisible()
        assert window._workers==[worker] and not worker.abandoned
        assert not worker.signals.finished.disconnected
        answer=QMessageBox.StandardButton.Discard
        assert window.close() and window._closed
        assert worker.abandoned and worker.signals.finished.disconnected and not window._workers
    finally:
        if analysis is not None and isValid(analysis):analysis.dirty=False;analysis.close()
        if child is not None and isValid(child):child.close()
        window.close();window.deleteLater();application.processEvents()
