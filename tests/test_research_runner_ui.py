"""Offscreen existing-job UI checks with retained-record fixtures, not solver evidence."""
import os

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from copy import deepcopy
import threading
import time

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("matplotlib")
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from apps.research.runner_window import RunnerWindow


def job(identifier, operation="evaluate", state="SUCCEEDED"):
    return {"id": identifier, "job_id": identifier, "operation": operation,
            "state": state, "arguments": {"backend": "material.felupe",
                "label": "Frozen " + identifier, "settings": {"parameters": {"E": 1234}}},
            "created_utc": "2026-10-11T01:00:00Z", "started_utc": "2026-10-11T01:00:01Z",
            "finished_utc": "2026-10-11T01:00:03Z" if state == "SUCCEEDED" else None,
            "resources": {"threads": 2, "memory_mb": 512},
            "resource_enforcement": {"cpu": "HINT_ONLY", "memory": "HINT_ONLY"},
            "request_id": "original-request-" + identifier, "request_hash": "input-hash-" + identifier,
            "result_refs": ["retained/" + identifier] if state == "SUCCEEDED" else []}


def series(values):
    return {"kind": "series", "unit": "MPa", "value": values,
            "axes": [{"name": "time", "unit": "s", "values": list(range(len(values)))}],
            "mask": [True] * len(values), "component": "xx", "location": "material_point",
            "frame": "laboratory", "measure": "infinitesimal_Cauchy", "valid": True}


class RecordsClient:
    def __init__(self):
        self.jobs = {"JA": job("JA"), "JB": job("JB"), "JF": job("JF", "fit", "RUNNING")}
        self.results = {identifier: {"execution_status": "SUCCEEDED", "responses": {
            "stress_xx": series(values)}, "diagnostics": {"source": "TEST_ONLY_RETAINED_RECORD"}}
            for identifier, values in (("JA", [0., 2., 4., 6.]), ("JB", [0., 9.]))}
        self.calls, self.thread_ids, self.blockers = [], [], {}

    def _read(self, operation, identifier=None, selection=None):
        self.calls.append((operation, identifier, deepcopy(selection)))
        self.thread_ids.append(threading.get_ident())
        blocker = self.blockers.get((operation, identifier))
        if blocker:
            assert blocker.wait(4), "Test did not release the queued service response"

    def job_navigation(self, identifier):
        self._read("navigation", identifier)
        return {"origin_document": {"id":"Dmaterial", "kind":"material", "connected":True}, "post_input":None}

    def request(self, path):
        assert path == "/api/workbench"
        self._read("catalog")
        return {"jobs": deepcopy(list(self.jobs.values()))}

    def status(self, identifier):
        self._read("status", identifier)
        return deepcopy(self.jobs[identifier])

    def result(self, identifier, *, selection):
        self._read("metadata" if selection.get("metadata_only") else "response", identifier, selection)
        result = deepcopy(self.results[identifier])
        if selection.get("metadata_only"):
            for response in result.get("responses", {}).values():
                if response.get("kind") == "series":
                    length = len(response.pop("value"))
                    response["data_ref"] = {"path": "arrays/stress.npy", "sha256": "retained-array-hash", "shape": [length]}
                    response.pop("mask")
                    response["mask_ref"] = {"path": "arrays/mask.npy", "sha256": "retained-mask-hash", "shape": [length]}
                    for axis in response["axes"]:
                        axis.pop("values")
                        axis["data_ref"] = {"path": "arrays/time.npy", "sha256": "retained-axis-hash", "shape": [length]}
            return result
        result["responses"] = {name: value for name, value in result.get("responses", {}).items() if name in selection["responses"]}
        if "rows" in selection:
            start, stop = selection["rows"]
            for response in result["responses"].values():
                response["value"] = response["value"][start:stop]
                response["mask"] = response["mask"][start:stop]
                response["axes"][0]["values"] = response["axes"][0]["values"][start:stop]
        return result

    def cancel(self, identifier):
        self._read("cancel", identifier)
        self.jobs[identifier]["state"] = "CANCEL_REQUESTED"
        self.jobs[identifier]["cancel_requested"] = True
        return deepcopy(self.jobs[identifier])

    def submit(self, *args, **kwargs):
        raise AssertionError("Existing-job navigation must never submit a calculation")


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def until(app, condition):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        app.processEvents()
        if condition():
            return
        QTest.qWait(10)
    raise AssertionError("Queued Runner reply did not arrive")


@pytest.fixture
def runner(app):
    client = RecordsClient()
    origins = []
    viewer = RunnerWindow(client, job_id="JA", poll_interval=0, on_open_origin=origins.append)
    until(app, lambda: viewer.selected_job_id == "JA" and not viewer._pending)
    yield viewer, client, origins
    for blocker in client.blockers.values():
        blocker.set()
    until(app, lambda: not viewer._pending)
    viewer.close()
    app.processEvents()


def select_row(viewer, identifier):
    for row in range(viewer.job_table.rowCount()):
        if viewer.job_table.item(row, 0).data(Qt.ItemDataRole.UserRole) == identifier:
            viewer.job_table.selectRow(row)
            return
    raise AssertionError(identifier)


def test_existing_selection_reads_frozen_inputs_and_bounded_original_rows(runner, app):
    viewer, client, _ = runner
    assert viewer.monitor_fields["Input hash"].text() == "input-hash-JA"
    assert "HINT_ONLY" in viewer.monitor_fields["Enforcement"].text()
    assert viewer.monitor_fields["Host"].text() == "Not recorded"
    assert viewer.inputs.findItems("arguments", Qt.MatchFlag.MatchExactly)[0].child(2).child(0).child(0).text(1) == "1234"
    assert not [call for call in client.calls if call[0] in {"metadata", "response", "cancel"}]
    viewer.result_button.click()
    until(app, lambda: viewer.values.rowCount() == 4 and not viewer._pending)
    viewer.row_start.setValue(1)
    viewer.row_count.setValue(2)
    viewer.read_rows_button.click()
    until(app, lambda: viewer.values.rowCount() == 2 and not viewer._pending)
    assert client.calls[-1] == ("response", "JA", {"responses": ["stress_xx"], "rows": [1, 3]})
    assert viewer.values.item(0, 0).text() == "1"
    assert viewer.values.item(0, 2).text() == "2.0 MPa"
    assert list(viewer.axes.lines[0].get_ydata()) == [2., 4.]
    assert viewer.axes.get_xlabel() == "time [s]"
    assert "infinitesimal_Cauchy" in viewer.axes.get_title()
    assert all(identifier != threading.get_ident() for identifier in client.thread_ids)


@pytest.mark.parametrize("blocked_operation", ["metadata", "response"])
def test_late_result_cannot_replace_another_selected_job(runner, app, blocked_operation):
    viewer, client, _ = runner
    gate = client.blockers[(blocked_operation, "JA")] = threading.Event()
    viewer.result_button.click()
    until(app, lambda: any(call[:2] == (blocked_operation, "JA") for call in client.calls))
    select_row(viewer, "JB")
    until(app, lambda: viewer.selected_job_id == "JB" and not any(key.startswith("status:JB:") for key in viewer._pending))
    viewer.result_button.click()
    until(app, lambda: viewer.values.rowCount() == 2 and "JB" in viewer.result_summary.text())
    gate.set()
    until(app, lambda: not viewer._pending)
    assert viewer.selected_job_id == "JB"
    assert list(viewer.axes.lines[0].get_ydata()) == [0., 9.]
    assert "JB" in viewer.result_summary.text()
    assert viewer.monitor_fields["Input hash"].text() == "input-hash-JB"


def test_parent_cancel_is_request_then_cleanup_then_terminal_and_other_job_stays_live(runner, app):
    viewer, client, _ = runner
    select_row(viewer, "JF")
    until(app, lambda: not viewer._pending)
    assert viewer.cancel_button.text() == "Cancel entire fit"
    assert "Candidate-level cancellation is unavailable" in viewer.scope_label.text()
    viewer.cancel_button.click()
    until(app, lambda: not viewer._pending)
    assert "Cancellation requested" in viewer.state_label.text()
    assert not viewer.cancel_button.isEnabled()
    assert client.jobs["JB"]["state"] == "SUCCEEDED"
    client.jobs["JF"].update(state="CLEANUP_PENDING", cleanup_unconfirmed=True)
    viewer.refresh_action.trigger()
    until(app, lambda: not viewer._pending)
    assert "termination is unconfirmed" in viewer.state_label.text()
    assert viewer.cancel_button.text() == "Request owned cleanup retry"
    client.jobs["JF"].update(state="CANCELLED", cleanup_unconfirmed=False)
    viewer.refresh_action.trigger()
    until(app, lambda: not viewer._pending)
    assert "terminal receipt recorded" in viewer.state_label.text()
    assert not viewer.cancel_button.isEnabled()
    assert [call[1] for call in client.calls if call[0] == "cancel"] == ["JF"]


def test_partial_candidate_penalty_and_unsupported_field_remain_explicit(runner, app):
    viewer, client, _ = runner
    client.results["JA"] = {"execution_status": "PARTIAL_FAILURE", "failure_reason": "One candidate failed",
        "responses": {"stress_field": {"kind": "field", "unit": "MPa", "component": "xx",
            "data_ref": {"path": "arrays/field.npy", "shape": [8, 3], "sha256": "retained-field-hash"}}},
        "candidates": [
            {"candidate_id": "C0", "execution_status": "SUCCEEDED", "values": {"E": 1234}, "objective": .25},
            {"candidate_id": "C1", "execution_status": "FAILED", "values": {"E": -1}, "objective": 1e6,
             "penalty_applied": 1e6, "failure_reason": "Invalid modulus", "responses": {}},
        ]}
    viewer.result_button.click()
    until(app, lambda: viewer.ledger_table.rowCount() == 2 and not viewer._pending)
    assert "not a successful full execution" in viewer.result_summary.text()
    assert viewer.ledger_table.item(0, 3).text() == "0.25"
    assert viewer.ledger_table.item(1, 3).text() == "—"
    assert viewer.ledger_table.item(1, 4).text() == "1000000.0"
    assert viewer.ledger_table.item(1, 5).text() == "1000000.0"
    assert viewer.ledger_table.item(1, 6).text() == "Invalid modulus"
    assert "retained-field-hash" in viewer.response_details.toPlainText()
    assert not viewer.axes.lines and not viewer.read_rows_button.isEnabled()
    assert not any(call[0] == "response" for call in client.calls)


def test_refresh_and_close_reopen_preserve_selection_and_origin_without_submit(runner, app):
    viewer, client, origins = runner
    select_row(viewer, "JB")
    until(app, lambda: not viewer._pending)
    client.jobs["JNEW"] = job("JNEW")
    viewer.refresh_action.trigger()
    until(app, lambda: not viewer._pending)
    assert viewer.selected_job_id == "JB"
    assert viewer.job_table.item(viewer.job_table.currentRow(), 1).text() == "JB"
    viewer.origin_button.click()
    until(app, lambda: not viewer._pending)
    assert origins == ["JB"]
    viewer.close()
    client.jobs["JB"]["state"] = "INTERRUPTED"
    viewer.show()
    until(app, lambda: not viewer._pending and "Interrupted" in viewer.state_label.text())
    assert viewer.selected_job_id == "JB"
    assert "process termination is unconfirmed" in viewer.state_label.text()
    assert not any(call[0] == "cancel" for call in client.calls)
