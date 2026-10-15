"""Scoped Korean Runner presentation checks over controlled retained records only."""
from copy import deepcopy
import os
from pathlib import Path
import threading

import pytest

from test_runner_dynamic_readback_qt import app, until, ControlledClient
from apps.research.runner_window import RunnerWindow, wall_time, state_description, candidate_state, backend_label, timestamp_label, fill_tree
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QTreeWidget


@pytest.mark.parametrize("record,expected", [
    ({"state": "QUEUED"}, "시작 전"), ({"state": "FAILED"}, "기록 없음"),
    ({"state": "FAILED", "started_utc": "2026-10-15T01:00:00Z"}, "종료 시각 미기록"),
    ({"state": "INTERRUPTED", "started_utc": "2026-10-15T01:00:00Z", "updated_utc": "2026-10-15T01:00:04Z"}, "4.0 s (마지막 갱신까지)"),
    ({"started_utc": "2026-10-15T01:00:00", "finished_utc": "2026-10-15T01:00:04"}, "시간대 미기록"),
    ({"started_utc": "2026-10-15T01:00:04Z", "finished_utc": "2026-10-15T01:00:00Z"}, "시각 순서 확인 필요"),
    ({"started_utc": "bad", "finished_utc": "bad"}, "시각 기록 확인 필요"),
])
def test_missing_and_inconsistent_elapsed_times_keep_their_meaning(record, expected):
    assert wall_time(record) == expected


def test_unknown_and_predicted_states_are_readable_without_promoting_them():
    assert state_description({"state": "UNKNOWN"}) == "상태 미확인"
    assert state_description({"state": "VENDOR_UNRECOGNIZED"}) == "상태 확인 필요"
    text = candidate_state({"execution_status": "SUCCEEDED", "prediction_status": "PREDICTED"})
    assert "예측값" in text and "가져온 실행 상태: 완료" in text
    assert "비선형" in backend_label("pde.fenicsx.nonlinear")
    assert "점탄성" in backend_label("material.mfront.viscoelastic")


def test_timezone_is_never_assumed_for_old_dates():
    assert timestamp_label("2026-10-15T01:00:00") == "2026-10-15T01:00:00 (시간대 미기록)"
    assert timestamp_label("2026-10-15T10:00:00+09:00") == "2026-10-15 01:00:00"
    assert timestamp_label("invalid") == "시각 기록 확인 필요"


def test_only_provenance_paths_are_hidden_while_same_named_engineering_inputs_survive(app):
    tree = QTreeWidget()
    mapping = {"job_id": "Jhidden", "request_hash": "HASHhidden", "operation": "run", "arguments": {
        "backend": "structure.calculix.contact", "origin": {"document_id": "Dhidden", "kind": "pre"},
        "settings": {"data_id": "Nhidden", "origin": [1., 2., 3.], "parameters": {
            "origin": 4., "data_id": 5., "job_id": 6., "source_record": 7.}}}}
    original = deepcopy(mapping)
    fill_tree(tree, mapping)
    try:
        assert not tree.findItems("Jhidden", Qt.MatchFlag.MatchExactly | Qt.MatchFlag.MatchRecursive, 1)
        assert not tree.findItems("Nhidden", Qt.MatchFlag.MatchExactly | Qt.MatchFlag.MatchRecursive, 1)
        assert len(tree.findItems("origin", Qt.MatchFlag.MatchExactly | Qt.MatchFlag.MatchRecursive)) == 2
        assert tree.findItems("data_id", Qt.MatchFlag.MatchExactly | Qt.MatchFlag.MatchRecursive)[0].text(1) == "5.0"
        assert tree.findItems("job_id", Qt.MatchFlag.MatchExactly | Qt.MatchFlag.MatchRecursive)[0].text(1) == "6.0"
        assert tree.findItems("source_record", Qt.MatchFlag.MatchExactly | Qt.MatchFlag.MatchRecursive)[0].text(1) == "7.0"
        assert mapping == original
    finally:
        tree.close()


def test_history_rows_can_omit_status_without_losing_other_values(app):
    window = RunnerWindow(ControlledClient(), poll_interval=0)
    history = [{"iteration": 1, "execution_status": "SUCCEEDED", "best_objective": 9.}, {"iteration": 2, "objective": 3.}]
    try:
        until(app, lambda: not window._pending)
        window._set_ledger({"history": history})
        assert window.ledger_table.item(0, 1).text() == "완료"
        assert window.ledger_table.item(1, 1).text() == "기록 없음"
        assert window.ledger_table.horizontalHeaderItem(2).text() == "최선 목적함수"
        assert window.ledger_table.item(1, 3).text() == "3.0"
        assert history[1] == {"iteration": 2, "objective": 3.}
    finally:
        window.close()
        app.processEvents()


def test_same_named_engineering_parameters_keep_original_names_and_values(app):
    tree = QTreeWidget()
    mapping = {"operation": "run", "arguments": {"backend": "structure.calculix.contact", "settings": {
        "parameters": {"backend": 2.3, "operation": "multiply", "label": "physical_label", "threads": 4}}}}
    original = deepcopy(mapping)
    fill_tree(tree, mapping)
    try:
        for key, expected in (("backend", "2.3"), ("operation", "multiply"), ("label", "physical_label"), ("threads", "4")):
            found = tree.findItems(key, Qt.MatchFlag.MatchExactly | Qt.MatchFlag.MatchRecursive)
            assert len(found) == 1 and found[0].text(1) == expected
        assert tree.findItems("작업 종류", Qt.MatchFlag.MatchExactly)[0].text(1) == "실행"
        assert tree.findItems("계산 엔진", Qt.MatchFlag.MatchExactly | Qt.MatchFlag.MatchRecursive)[0].text(1) == "CalculiX 구조 해석"
        assert mapping == original
    finally:
        tree.close()


class DisplayClient(ControlledClient):
    def __init__(self):
        super().__init__()
        self.result_payload = {"execution_status": "PARTIAL_FAILURE", "responses": {"stress_xx": {
            "kind": "series", "unit": "MPa", "value": [0., 2., None, 6.],
            "axes": [{"name": "time", "unit": "s", "values": [0., 1., 2., 3.]}],
            "mask": [True, True, False, True], "component": "xx", "location": "material_point",
            "frame": "laboratory", "measure": "infinitesimal_Cauchy", "valid": True}}}
        self.jobs["Joriginal"]["result_refs"] = ["Roriginal"]
        self.jobs["Joriginal"]["phase"] = "CALCULATING"
        self.gate = threading.Event()
        self.read_started = threading.Event()

    def result(self, identifier, *, selection):
        assert identifier == "Joriginal"
        if not selection.get("metadata_only"):
            self.read_started.set()
            assert self.gate.wait(8)
        return deepcopy(self.result_payload)


def capture(window, name, width):
    folder = os.environ.get("RUNNER_KOREAN_RENDER_DIR")
    if folder:
        Path(folder).mkdir(parents=True, exist_ok=True)
        assert window.grab().save(str(Path(folder) / f"{name}-{width}.png"))


@pytest.mark.parametrize("width,height", [(980, 650), (1420, 900)])
def test_primary_list_empty_reading_series_and_failure_keep_korean_and_raw_diagnostics(app, width, height):
    from apps.research.appearance import apply_appearance
    apply_appearance(app)
    client = DisplayClient()
    original = deepcopy(client.result_payload)
    window = RunnerWindow(client, job_id="Joriginal", poll_interval=0)
    try:
        until(app, lambda: window.selected_job_id == "Joriginal" and not window._pending)
        window.resize(width, height)
        window.show()
        app.processEvents()
        assert window.job_table.isColumnHidden(1)
        assert window.monitor_fields["Wall time"].text() == "기록 없음"
        assert window.monitor_fields["Phase"].text() == "계산 중"
        assert "Joriginal" in window.details.toPlainText()
        assert not window.inputs.findItems("job_id", Qt.MatchFlag.MatchExactly | Qt.MatchFlag.MatchRecursive)
        assert not window.inputs.findItems("request_hash", Qt.MatchFlag.MatchExactly | Qt.MatchFlag.MatchRecursive)
        capture(window, "list-failed-source", width)
        original_job = deepcopy(client.jobs["Joriginal"])
        client.jobs["Joriginal"].update(started_utc="2026-10-15T10:00:00", finished_utc="2026-10-15T10:00:05")
        window.refresh_selected()
        until(app, lambda: not window._pending)
        assert "시간대 미기록" in window.monitor_fields["Started UTC"].text()
        assert window.monitor_fields["Wall time"].text() == "시간대 미기록"
        assert "2026-10-15T10:00:00" in window.details.toPlainText()
        capture(window, "timezone-missing", width)
        client.jobs["Joriginal"] = original_job
        window.refresh_selected()
        until(app, lambda: not window._pending)
        window.tabs.setCurrentWidget(window.result_panel)
        app.processEvents()
        assert "결과 보기" in window.axes.texts[0].get_text()
        capture(window, "empty", width)
        window.result_button.click()
        until(app, lambda: client.read_started.is_set())
        assert "읽고 있습니다" in window.response_label.text()
        assert "Joriginal" not in window.response_label.text()
        capture(window, "reading", width)
        client.gate.set()
        until(app, lambda: not window._pending)
        assert window.axes.get_xlabel() == "시간 [s]"
        assert window.values.item(2, 3).text() == "제외"
        assert "일부 계산 실패" in window.result_summary.text()
        assert window.axes.lines[0].get_ydata()[1] == 2.
        capture(window, "time-result", width)
        malformed = deepcopy(original["responses"]["stress_xx"])
        malformed["axes"][0]["values"] = [0.]
        window._draw_response("stress_xx", malformed, 0)
        app.processEvents()
        assert "1차원 계열" in window.response_label.text()
        assert not window.axes.lines
        assert window.result_views.currentWidget() is window.canvas
        assert '"time"' in window.response_details.toPlainText()
        capture(window, "invalid-series", width)
        client.result_payload = {"execution_status": "FAILED", "failure_reason": "TEST_ONLY 보존 출력 없음", "responses": {}}
        window.result_button.click()
        until(app, lambda: not window._pending)
        assert "실패 사유: TEST_ONLY 보존 출력 없음" in window.result_summary.text()
        assert "표시할 단일 값이나 곡선이 없습니다" in window.response_label.text()
        assert window.result_views.currentWidget() is window.canvas
        assert '"failure_reason"' in window.details.toPlainText()
        capture(window, "failed-empty-result", width)
        client.result_payload = {"execution_status": "PARTIAL_FAILURE", "responses": {}, "candidates": [
            {"candidate_id": "Craw_001", "execution_status": "FAILED", "objective": 1e6,
             "penalty_applied": 1e6, "values": {"E": -1}, "failure_reason": "TEST_ONLY 잘못된 탄성계수"},
            {"candidate_id": "Craw_002", "execution_status": "SUCCEEDED", "prediction_status": "PREDICTED",
             "objective": .1, "values": {"E": 2000}}]}
        window.result_button.click()
        until(app, lambda: not window._pending)
        window.tabs.setCurrentWidget(window.ledger_panel)
        window.ledger_table.selectRow(1)
        app.processEvents()
        assert window.ledger_table.item(0, 0).text() == "후보 1"
        assert "예측값" in window.ledger_table.item(1, 1).text()
        assert window.ledger_table.item(1, 3).text() == "—"
        assert "Craw_002" not in window.ledger_details.toPlainText()
        assert "Craw_002" in window.details.toPlainText()
        assert "전체 계산" in window.ledger_label.text()
        capture(window, "candidate-failure-prediction", width)
        assert original["responses"]["stress_xx"]["value"] == [0., 2., None, 6.]
    finally:
        client.gate.set()
        until(app, lambda: not window._workers)
        window.close()
        app.processEvents()
