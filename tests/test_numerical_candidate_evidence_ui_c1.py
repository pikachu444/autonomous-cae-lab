"""Optional native PySide6 C1 actions. Offscreen does NOT certify Windows."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import pytest
pytest.importorskip('PySide6',reason='NOT_RUN: native PySide6 runtime required')
pytest.importorskip('matplotlib')
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest, QSignalSpy
from PySide6.QtWidgets import QApplication
from apps.research.numerical_candidate_detail_window import NumericalCandidateDetailWindow
from _numerical_candidate_detail_support import DetailHost, synthetic_inputs, intermediate
from test_numerical_candidate_detail_ui import LocalClient, until
from caelab.numerical_candidate_evidence import resolve_candidate_evidence


@pytest.fixture(scope='module')
def app():return QApplication.instance() or QApplication([])


def test_missing_detail_gates_keyboard_preservation_and_attempt_change(app,tmp_path):
    with DetailHost(tmp_path) as host:
        doc,job=host.create_fit(synthetic_inputs(retain=0));cid=intermediate(host,doc,job)
        window=NumericalCandidateDetailWindow(LocalClient(host),document_id=doc,job_id=job,candidate_id=cid,poll_interval=100)
        preserved=QSignalSpy(window.evidence_preserved);invalidated=QSignalSpy(window.evidence_invalidated)
        window.resize(1100,760);window.show()
        try:
            until(app,lambda:window.view is not None)
            assert not window.evidence_button.isEnabled() and not window.evidence_report_button.isEnabled()
            window.trials.setCurrentItem(window.trials.topLevelItem(2));window.refresh()
            until(app,lambda:window._read_worker is None)
            assert len(host.manager.list())==1
            QTest.mouseClick(window.detail_button,Qt.MouseButton.LeftButton)
            until(app,lambda:window.view is not None and window.view.get('attempt_state')=='SUCCEEDED')
            assert window.evidence_button.isEnabled()
            window.evidence_button.setFocus()
            QTest.keyClick(window.evidence_button,Qt.Key.Key_Space)
            until(app,lambda:preserved.count()==1 and window._read_worker is None and not window._writing)
            ref=window._evidence_reference
            assert resolve_candidate_evidence(host.owner,ref,consumer='adoption')['readiness']['success_judgment_permitted']
            assert window.evidence_report_button.isEnabled() and len(host.manager.list())==2
            window.attempts.setCurrentIndex(0)
            until(app,lambda:window.view is not None and window.attempt_job_id is None)
            assert invalidated.count()>0 and window._evidence_reference is None
            assert not window.evidence_report_button.isEnabled() and len(host.manager.list())==2
        finally:
            until(app,lambda:not window._writing)
            window.close();app.processEvents()


def test_failed_candidate_diagnostic_purpose_is_not_success(app,tmp_path):
    with DetailHost(tmp_path) as host:
        doc,job=host.create_fit(synthetic_inputs(retain=0));cid=intermediate(host,doc,job,'FAILED')
        window=NumericalCandidateDetailWindow(LocalClient(host),document_id=doc,job_id=job,candidate_id=cid)
        window.show()
        try:
            until(app,lambda:window.view is not None)
            assert not window.evidence_button.isEnabled()
            window.evidence_purpose.setCurrentIndex(1)
            assert window.evidence_button.isEnabled()
            window.preserve_evidence()
            until(app,lambda:window._evidence_reference is not None and not window._writing)
            ref=window._evidence_reference
            assert resolve_candidate_evidence(host.owner,ref,consumer='failure_report')['readiness']['failure_diagnostic_permitted']
            window.evidence_purpose.setCurrentIndex(0)
            assert window._evidence_reference is None and not window.evidence_report_button.isEnabled()
            assert len(host.manager.list())==1
        finally:
            until(app,lambda:not window._writing)
            window.close();app.processEvents()


def test_one_click_report_and_adoption_save_only_the_exact_selected_result(app,tmp_path):
    from test_numerical_candidate_evidence_c1 import complete
    with DetailHost(tmp_path) as host:
        doc,job=host.create_fit(synthetic_inputs(retain=0));cid=intermediate(host,doc,job)
        completed=complete(host,doc,job,cid);adopted=[];reports=[]
        window=NumericalCandidateDetailWindow(LocalClient(host),document_id=doc,job_id=job,
            candidate_id=cid,adopt_callback=adopted.append)
        window._show_evidence_report=reports.append;window.show()
        try:
            until(app,lambda:window.view is not None)
            assert not window.evidence_report_button.isEnabled() and not window.evidence_adopt_button.isEnabled()
            window.attempts.setCurrentIndex(window.attempts.findData(completed['attempt_job_id']))
            until(app,lambda:window.view is not None and window.attempt_job_id==completed['attempt_job_id'])
            assert window._evidence_reference is None and window.evidence_report_button.isEnabled()
            QTest.mouseClick(window.evidence_report_button,Qt.MouseButton.LeftButton)
            until(app,lambda:len(reports)==1 and not window._writing)
            reference=reports[0]
            assert reference['candidate_id']==cid and reference['attempt_job_id']==completed['attempt_job_id']
            assert resolve_candidate_evidence(host.owner,reference,consumer='success_report')['readiness']['success_judgment_permitted']
            QTest.mouseClick(window.evidence_adopt_button,Qt.MouseButton.LeftButton)
            assert adopted==[reference] and len(host.manager.list())==2
            assert 'H'+reference['snapshot_sha256'] not in window.evidence_state.text()
            window.attempts.setCurrentIndex(0)
            until(app,lambda:window.view is not None and window.attempt_job_id is None)
            assert not window.evidence_report_button.isEnabled() and not window.evidence_adopt_button.isEnabled()
        finally:
            until(app,lambda:not window._writing);window.close();app.processEvents()


def test_peer_plan_edit_is_not_reapproved_by_fresh_owner_read(app,tmp_path):
    from copy import deepcopy
    from test_numerical_candidate_evidence_c1 import complete
    with DetailHost(tmp_path) as host:
        doc,job=host.create_fit(synthetic_inputs(retain=0));cid=intermediate(host,doc,job)
        completed=complete(host,doc,job,cid);reports=[]
        window=NumericalCandidateDetailWindow(LocalClient(host),document_id=doc,job_id=job,
            candidate_id=cid,auto_load=False)
        window._show_evidence_report=reports.append;window.attempt_job_id=completed['attempt_job_id']
        window.refresh();window.show()
        try:
            until(app,lambda:window.view is not None)
            changed=deepcopy(host.owner.read(doc)['draft']);changed['request']['purpose']='다른 창의 아직 저장하지 않은 편집'
            host.command(doc,'numerical.update',{'draft':changed});before=host.owner.read(doc)
            QTest.mouseClick(window.evidence_report_button,Qt.MouseButton.LeftButton)
            until(app,lambda:not window._writing and window.view is None)
            after=host.owner.read(doc)
            assert not reports and window._evidence_reference is None and after==before
            assert 'Plan changed' in window.status.toolTip() and len(host.manager.list())==2
        finally:
            until(app,lambda:not window._writing);window.close();app.processEvents()
