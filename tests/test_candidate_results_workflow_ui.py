"""Bounded candidate-detail UI state checks; no evaluator is prepared or run."""
import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import io
import json
from types import SimpleNamespace
from urllib.error import HTTPError
import pytest
pytest.importorskip('PySide6')
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from apps.research.numerical_candidate_detail_window import NumericalCandidateDetailWindow
from caelab.workbench_client import WorkbenchHTTPError


def service_error(code):
    raw=json.dumps({'error':'Original candidate evidence refusal'}).encode()
    return WorkbenchHTTPError(HTTPError('http://127.0.0.1/test',code,'failure',{},io.BytesIO(raw)),raw,'Original candidate evidence refusal')


@pytest.mark.parametrize('error,expected', [
    (service_error(400),'요청이 거절'),
    (service_error(500),'처리 결과를 확인하지 못'),
    (TimeoutError('connection acknowledgement lost'),'처리 결과를 확인하지 못'),
    (RuntimeError('HTTP 400 is just unstructured text'),'처리 결과를 확인하지 못'),
    (ValueError('Plan changed after this result was read; reread before saving or adopting'),'요청하지 않았'),
    (ValueError('Owner session changed; reopen this view'),'요청하지 않았')])
def test_confirmed_refusal_stays_distinct_from_uncertain_transport(error,expected):
    app=QApplication.instance() or QApplication([])
    window=NumericalCandidateDetailWindow(SimpleNamespace(),document_id='Nfixture',job_id='Jfixture',candidate_id='Cfixture',auto_load=False)
    try:
        def fail():raise error
        window._write(fail,lambda value:pytest.fail('No success callback on refusal'))
        for _ in range(200):
            app.processEvents()
            if not window._writing:break
            QTest.qWait(5)
        assert not window._writing
        assert expected in window.status.text()
        assert window.status.toolTip()==str(error)
        assert window.view is None and window._command_generation is None
        assert not window.detail_button.isEnabled() and window.read_button.isEnabled()
    finally:window.close();app.processEvents()


def test_write_success_keeps_original_payload_and_refreshes_once():
    app=QApplication.instance() or QApplication([])
    window=NumericalCandidateDetailWindow(SimpleNamespace(),document_id='Nfixture',job_id='Jfixture',candidate_id='Cfixture',auto_load=False)
    received=[];refreshed=[];payload={'document':{'id':'Nfixture'},'reference':{'evidence_id':'Hfixture'}}
    window.refresh=lambda:refreshed.append(True)
    try:
        window._write(lambda:payload,received.append)
        for _ in range(200):
            app.processEvents()
            if not window._writing:break
            QTest.qWait(5)
        assert received==[payload] and refreshed==[True] and not window._writing
    finally:window.close();app.processEvents()


def test_existing_attempt_guidance_points_to_read_without_enabling_new_execution(monkeypatch):
    import caelab.numerical_candidate_evidence as evidence
    app=QApplication.instance() or QApplication([])
    window=NumericalCandidateDetailWindow(SimpleNamespace(),document_id='Nfixture',job_id='Jfixture',candidate_id='Cfixture',auto_load=False)
    try:
        monkeypatch.setattr(evidence,'candidate_detail_readiness',lambda *args,**kwargs:{
            'ready_to_preserve':False,'issues':[{'code':'DETAIL_NOT_RETAINED'}]})
        window.view={'can_detail_eval':False,'latest_attempt_job_id':'Jexisting', 'detail_eval_blocked':'SELECT_LATEST_ATTEMPT'}
        window._buttons()
        assert '최신 상세 선택' in window.evidence_state.text()
        assert not window.detail_button.isEnabled() and window.latest_button.isEnabled()
        assert not window.evidence_button.isEnabled() and not window.evidence_report_button.isEnabled()
    finally:window.close();app.processEvents()
