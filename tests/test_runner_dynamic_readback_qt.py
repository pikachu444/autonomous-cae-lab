"""Runner interaction with controlled service replies; no solver or physics evidence."""
from copy import deepcopy
import os
from pathlib import Path
import threading
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
pytest.importorskip("matplotlib")
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from apps.research.runner_window import RunnerWindow


def source(identifier="Joriginal", state="FAILED"):
    return {"id": identifier, "operation": "run", "state": state,
        "arguments": {"backend": "structure.calculix.contact", "label": "초기속도 시편",
            "settings": {"data_id": "Doriginal"}}, "result_refs": [],
        "created_utc": "2026-10-15T01:00:00Z", "error": {"message": "보존된 후처리 실패 기록"}}


class ControlledClient:
    def __init__(self):
        self.jobs = {"Joriginal": source(), "Jother": source("Jother", "SUCCEEDED")}
        self.calls = []
        self.submit_gate = None
        self.lose_reply = False
        self.preparation_error = False
        self.request_ids = {}
        self.result_payload = {"execution_status": "SUCCEEDED", "source_execution_status": "FAILED",
            "solver_execution": "NOT_PERFORMED", "responses": {}, "qualification": "UNKNOWN",
            "retained_attempt": {"dynamic_result": {"frame_count": 8}}, "post_input": {"id": "Dreadback"}}

    def request(self, path):
        assert path == "/api/workbench"
        return {"jobs": deepcopy(list(self.jobs.values()))}

    def status(self, identifier):
        self.calls.append(("status", identifier))
        return deepcopy(self.jobs[identifier])

    def dynamic_reprocess_request(self, identifier):
        self.calls.append(("prepare", identifier))
        if self.preparation_error:
            raise ValueError("원 출력이 없습니다")
        return {"source_job_id": identifier,
            "source_record": {"relative": "contact_execution.json", "bytes": 100, "sha256": "0" * 64}}

    def submit(self, operation, arguments, *, request_id):
        self.calls.append(("submit", operation, deepcopy(arguments), request_id))
        assert operation == "dynamic.reprocess"
        if self.submit_gate:
            assert self.submit_gate.wait(5)
        identifier = self.request_ids.setdefault(request_id, "Jreadback")
        self.jobs.setdefault(identifier, {"id": identifier, "operation": operation, "state": "QUEUED",
            "arguments": deepcopy(arguments), "request_id": request_id, "result_refs": [],
            "created_utc": "2026-10-15T02:00:00Z"})
        if self.lose_reply:
            self.lose_reply = False
            raise OSError("TEST_ONLY reply lost after admission")
        return deepcopy(self.jobs[identifier])

    def cancel(self, identifier):
        self.calls.append(("cancel", identifier))
        self.jobs[identifier]["state"] = "CANCEL_REQUESTED"
        return deepcopy(self.jobs[identifier])

    def result(self, identifier, *, selection):
        self.calls.append(("result", identifier, selection))
        assert identifier == "Jreadback"
        return deepcopy(self.result_payload)

    def job_navigation(self, identifier):
        self.calls.append(("navigation", identifier))
        return {"origin_document": {"id": "Noriginal", "kind": "pre"},
            "post_input": {"id": "Dreadback"} if identifier == "Jreadback" else {"id": "Doriginal"}}


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def until(app, predicate):
    deadline = time.monotonic() + 6
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return
        QTest.qWait(10)
    raise AssertionError("Controlled Runner response did not arrive")


@pytest.fixture
def viewer(app):
    client = ControlledClient()
    window = RunnerWindow(client, job_id="Joriginal", poll_interval=0)
    until(app, lambda: window.selected_job_id == "Joriginal" and not window._pending)
    yield window, client
    if client.submit_gate:
        client.submit_gate.set()
    until(app, lambda: not window._pending)
    window.close()
    app.processEvents()


@pytest.mark.parametrize("state,cleanup,enabled", [
    ("FAILED", False, True), ("CANCELLED", False, True), ("SUCCEEDED", False, True),
    ("RUNNING", False, False), ("INTERRUPTED", True, False), ("CLEANUP_PENDING", True, False)])
def test_select_only_never_submits_and_active_source_is_blocked(viewer, app, state, cleanup, enabled):
    window, client = viewer
    client.jobs["Joriginal"].update(state=state, cleanup_unconfirmed=cleanup)
    window.refresh_selected()
    until(app, lambda: not window._pending)
    assert window.reprocess_button.isEnabled() is enabled
    assert not any(call[0] in {"prepare", "submit"} for call in client.calls)
    if not enabled:
        window.reprocess_selected()
        assert not any(call[0] == "prepare" for call in client.calls)


def test_explicit_readback_uses_new_job_and_cancel_preserves_original(viewer, app):
    window, client = viewer
    original = deepcopy(client.jobs["Joriginal"])
    window.reprocess_button.click()
    until(app, lambda: window.selected_job_id == "Jreadback" and not window._pending)
    assert "별도 작업" in window.readback_label.text()
    assert "실패" in window.readback_label.text()
    assert not window.reprocess_button.isVisible()
    window.cancel_button.click()
    until(app, lambda: not window._pending)
    assert ("cancel", "Jreadback") in client.calls
    assert client.jobs["Joriginal"] == original
    window.source_job_button.click()
    until(app, lambda: not window._pending)
    assert window.selected_job_id == "Joriginal"


def test_lost_admission_reply_reuses_exact_request(viewer, app):
    window, client = viewer
    client.lose_reply = True
    window.reprocess_button.click()
    until(app, lambda: not window._pending)
    assert window.selected_job_id == "Joriginal"
    assert window.reprocess_button.text() == "같은 읽기 요청 확인"
    assert "동일 요청" in window.message.text()
    window.reprocess_button.click()
    until(app, lambda: window.selected_job_id == "Jreadback" and not window._pending)
    submissions = [call for call in client.calls if call[0] == "submit"]
    assert submissions[0] == submissions[1]
    assert len(client.request_ids) == 1
    assert len([call for call in client.calls if call[0] == "prepare"]) == 1


def test_preparation_rejection_stays_at_original_and_can_retry(viewer, app):
    window, client = viewer
    client.preparation_error = True
    window.reprocess_button.click()
    until(app, lambda: not window._pending)
    assert "원 출력이 없습니다" in window.message.text()
    assert window.selected_job_id == "Joriginal"
    assert window.reprocess_button.text() == "결과 다시 읽기"
    assert not any(call[0] == "submit" for call in client.calls)


def test_receipt_with_different_pinned_source_cannot_replace_selection(viewer, app, monkeypatch):
    window, client = viewer
    submit = client.submit
    def changed(*args, **kwargs):
        receipt = submit(*args, **kwargs)
        receipt["arguments"]["source_record"]["sha256"] = "1" * 64
        return receipt
    monkeypatch.setattr(client, "submit", changed)
    window.reprocess_button.click()
    until(app, lambda: not window._pending)
    assert window.selected_job_id == "Joriginal"
    assert "원 실행이 다릅니다" in window.message.text()
    assert "Jreadback" not in window.jobs
    assert window.reprocess_button.text() == "같은 읽기 요청 확인"


def test_late_reply_does_not_steal_new_selection(viewer, app):
    window, client = viewer
    client.submit_gate = threading.Event()
    window.reprocess_button.click()
    until(app, lambda: any(call[0] == "submit" for call in client.calls))
    window.select_job("Jother")
    until(app, lambda: window.monitor_fields["Job ID"].text() == "Jother")
    client.submit_gate.set()
    until(app, lambda: not window._pending)
    assert window.selected_job_id == "Jother"
    assert "Jreadback" in window.jobs


def test_closed_window_ignores_late_registration_and_cold_listing_can_recover(viewer, app):
    window, client = viewer
    client.submit_gate = threading.Event()
    window.reprocess_button.click()
    until(app, lambda: any(call[0] == "submit" for call in client.calls))
    window.close()
    client.submit_gate.set()
    until(app, lambda: not window._workers)
    assert window.selected_job_id == "Joriginal"
    assert "Jreadback" not in window.jobs
    recovered = RunnerWindow(client, job_id="Jreadback", poll_interval=0)
    try:
        until(app, lambda: recovered.selected_job_id == "Jreadback" and not recovered._pending)
        assert recovered.jobs["Joriginal"]["state"] == "FAILED"
        assert len([call for call in client.calls if call[0] == "submit"]) == 1
    finally:
        recovered.close()
        app.processEvents()


def test_readback_result_and_post_keep_source_and_derived_ids_separate(viewer, app, monkeypatch):
    from apps.research import desktop
    window, client = viewer
    opened = []
    monkeypatch.setattr(desktop, "launch_post", lambda c, data, **kw: opened.append((data, kw)) or {"status": "SHOWN"})
    monkeypatch.setattr(desktop, "open_origin", lambda c, job: opened.append(("origin", job)) or {"status": "SHOWN"})
    window.reprocess_button.click()
    until(app, lambda: window.selected_job_id == "Jreadback" and not window._pending)
    client.jobs["Jreadback"].update(state="SUCCEEDED", result_refs=["Rreadback"])
    window.refresh_selected()
    until(app, lambda: not window._pending)
    window.result_button.click()
    until(app, lambda: not window._pending)
    assert "원 계산: 실패" in window.result_summary.text()
    assert "공학적 승인은 확인되지" in window.result_summary.text()
    assert "보존된 시간 출력: 8개" in window.response_label.text()
    assert window.result_views.isHidden() and window.response_controls.isHidden()
    assert "NOT_PERFORMED" not in window.response_details.toPlainText()
    assert "NOT_PERFORMED" in window.details.toPlainText()
    window.readback_details_button.click()
    assert window.tabs.currentWidget() is window.technical_panel
    window.tabs.setCurrentWidget(window.result_panel)
    window.readback_post_button.click()
    until(app, lambda: not window._pending)
    window.origin_button.click()
    until(app, lambda: not window._pending)
    assert opened == [("Dreadback", {"job_id": "Jreadback"}), ("origin", "Joriginal")]
    assert client.jobs["Joriginal"]["state"] == "FAILED"


@pytest.mark.parametrize("state", ["FAILED", "CANCELLED"])
def test_no_response_failure_keeps_actionable_readback_and_registration_errors(viewer, app, state):
    window, client = viewer
    window.reprocess_button.click()
    until(app, lambda: window.selected_job_id == "Jreadback" and not window._pending)
    client.jobs["Jreadback"].update(state=state, result_refs=["Rreadback"])
    client.result_payload.update(execution_status=state, retained_attempt={}, post_input=None,
        diagnostics={"readback": {"dynamic_readback": "TEST_ONLY 원 FRD 출력 누락"},
            "post_registration": {"status": "FAILED", "message": "TEST_ONLY 등록할 시간 결과가 없습니다"}})
    window.refresh_selected()
    until(app, lambda: not window._pending)
    window.result_button.click()
    until(app, lambda: not window._pending)
    assert "원 계산: 실패" in window.result_summary.text()
    assert "원 FRD 출력 누락" in window.response_label.text()
    assert "후처리 등록 실패" in window.response_label.text()
    assert "등록할 시간 결과가 없습니다" in window.response_label.text()
    assert "시간 출력 수는 기록되지" in window.response_label.text()
    assert not window.readback_post_button.isEnabled()
    assert window.result_views.isHidden() and window.response_controls.isHidden()
    assert not window.response_details.toPlainText()
    assert '"post_registration"' in window.details.toPlainText()
    window.readback_details_button.click()
    assert window.tabs.currentWidget() is window.technical_panel


@pytest.mark.parametrize("width,height", [(980, 650), (1420, 900)])
def test_readback_controls_remain_readable_at_two_sizes(viewer, app, width, height):
    window, client = viewer
    from apps.research.appearance import apply_appearance
    apply_appearance(app)
    window.resize(width, height)
    window.show()
    window.reprocess_button.setFocus()
    app.processEvents()
    assert window.reprocess_button.hasFocus()
    assert window.reprocess_button.width() >= window.reprocess_button.sizeHint().width()
    assert window.readback_label.height() >= window.readback_label.heightForWidth(window.readback_label.width())
    folder = os.environ.get("DYNAMIC_RUNNER_RENDER_DIR")
    if folder:
        Path(folder).mkdir(parents=True, exist_ok=True)
        assert window.grab().save(str(Path(folder) / f"readback-source-{width}.png"))
    window.reprocess_button.click()
    until(app, lambda: window.selected_job_id == "Jreadback" and not window._pending)
    window.tabs.setCurrentIndex(0)
    app.processEvents()
    assert window.source_job_button.isVisible()
    if folder:
        assert window.grab().save(str(Path(folder) / f"readback-derived-{width}.png"))
    client.jobs["Jreadback"].update(state="SUCCEEDED", result_refs=["Rreadback"])
    window.refresh_selected()
    until(app, lambda: not window._pending)
    window.result_button.click()
    until(app, lambda: not window._pending)
    window.readback_post_button.setFocus()
    app.processEvents()
    assert window.readback_post_button.hasFocus()
    assert window.readback_post_button.width() >= window.readback_post_button.sizeHint().width()
    assert window.response_label.height() >= window.response_label.heightForWidth(window.response_label.width())
    if folder:
        assert window.grab().save(str(Path(folder) / f"readback-result-{width}.png"))
