"""Offscreen widget/transport contract checks; no material solver is simulated."""
import os

# These tests must never open a visible native window on the user's desktop.
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from copy import deepcopy
import threading
import time

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("matplotlib")
from PySide6.QtCore import QTimer, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox, QTableWidgetItem

from apps.research.material_window import MaterialWindow, edited_number


def material_draft():
    return {"backend": "material.felupe", "settings": {
        "model": "linear_elastic", "stress_unit": "MPa", "time_unit": "s",
        "parameters": {"E": 1000, "nu": .25}, "time": [0, 1, 2],
        "deformation_gradient": [[[1 + strain, 0, 0], [0, 1, 0], [0, 0, 1]]
                                 for strain in (0, .001, .002)],
    }}


class ContractClient:
    """Test-only owner replies and retained response fixture, never a solver."""
    def __init__(self):
        self.docs = {}
        self.commands = []
        self.open_calls = []
        self.results_read = []
        self.call_threads = []
        self.undo_states = []
        self.redo_states = []
        self.job_state = "SUCCEEDED"
        self.result_fixture = {"execution_status": "SUCCEEDED", "responses": {
            "stress_xx": {"kind": "series", "unit": "MPa", "measure": "infinitesimal_Cauchy",
                "value": [0., 1.2, 2.4], "axes": [{"name": "time", "unit": "s", "values": [0, 1, 2]}]}},
            "diagnostics": {"source": "TEST_ONLY_RETAINED_RESPONSE_FIXTURE"}, "checks": []}

    def _called(self):
        self.call_threads.append(threading.get_ident())

    def document_open(self, *, kind, title, draft=None, document_id=None):
        self._called()
        self.open_calls.append((kind, title, deepcopy(draft), document_id))
        if document_id is None:
            document_id = "M" + str(len(self.docs) + 1)
            self.docs[document_id] = {
                "id": document_id, "kind": kind, "title": title, "session_id": "owner-session",
                "generation": 0, "saved_revision": 0, "dirty": False,
                "draft": deepcopy(draft if draft is not None else material_draft()),
                "diagnostics": [], "can_undo": False, "can_redo": False, "runs": [],
            }
        return deepcopy(self.docs[document_id])

    def document_read(self, identifier):
        self._called()
        return deepcopy(self.docs[identifier])

    def documents(self):
        self._called()
        return {"documents": [deepcopy(value) for value in self.docs.values()]}

    def document_command(self, identifier, operation, arguments, *, session_id, expected_generation, command_id):
        self._called()
        document = self.docs[identifier]
        assert session_id == document["session_id"]
        if expected_generation != document["generation"]:
            raise ValueError("STALE_GENERATION")
        self.commands.append((identifier, operation, deepcopy(arguments), expected_generation, command_id))
        job = None
        if operation == "material.update":
            self.undo_states.append(deepcopy(document["draft"]))
            self.redo_states.clear()
            document["draft"] = deepcopy(arguments["draft"])
            document["generation"] += 1
            document["dirty"] = True
        elif operation == "document.undo":
            self.redo_states.append(deepcopy(document["draft"]))
            document["draft"] = self.undo_states.pop()
            document["generation"] += 1
            document["dirty"] = True
        elif operation == "document.redo":
            self.undo_states.append(deepcopy(document["draft"]))
            document["draft"] = self.redo_states.pop()
            document["generation"] += 1
            document["dirty"] = True
        elif operation == "document.save":
            document["saved_revision"] += 1
            document["dirty"] = False
        elif operation == "material.evaluate":
            job = {"id": "J1", "job_id": "J1", "state": "QUEUED"}
            document["runs"].append({"job_id": "J1", "input_generation": document["generation"],
                "input_revision": document["saved_revision"], "input_sha256": "retained-input-hash",
                "settings": deepcopy(document["draft"]["settings"])})
        else:
            raise AssertionError(operation)
        document["can_undo"] = bool(self.undo_states)
        document["can_redo"] = bool(self.redo_states)
        return {"document": deepcopy(document), **({"job": job} if job else {})}

    def status(self, identifier):
        self._called()
        return {"id": identifier, "state": self.job_state,
                "result_refs": ["results/" + identifier] if self.job_state == "SUCCEEDED" else [],
                "error": {"message": "TEST_ONLY_FAILURE"} if self.job_state == "FAILED" else None}

    def document_result(self, document_id, identifier, *, selection=None):
        self._called()
        self.results_read.append((document_id, identifier, selection))
        return deepcopy(self.result_fixture)


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
    raise AssertionError("Qt service reply did not arrive")


@pytest.fixture
def window(app):
    client = ContractClient()
    window = MaterialWindow(client, poll_interval=0)
    until(app, lambda: window.document is not None and not window._busy)
    yield window, client
    until(app, lambda: not window._busy)
    window._allow_close = True
    window.close()
    app.processEvents()


def test_direct_new_document_has_complete_editable_history_and_no_fake_plot(window):
    editor, client = window
    assert editor.history.columnCount() == 10
    assert editor.history.rowCount() == 3
    assert editor.history.item(1, 1).text() == "1.001"
    assert editor.coefficients.item(0, 1).text() == "1000"
    assert not editor.axes.lines
    assert "Constrained lateral strain" in editor.protocol_label.text()
    assert not client.commands
    assert all(identifier != threading.get_ident() for identifier in client.call_threads)


def test_return_from_runner_keeps_unapplied_material_edits_and_original_job(window, app):
    editor, client = window
    editor.evaluate()
    until(app, lambda: len(editor.document["runs"]) == 1 and not editor._busy)
    editor.coefficients.item(0, 1).setText("1777")
    sent = deepcopy(client.commands)
    editor.open_run_origin("J1")
    until(app, lambda: not editor._busy)
    assert editor.coefficients.item(0, 1).text() == "1777"
    assert editor.local_dirty
    assert editor._selected_jobs() == ["J1"]
    assert client.commands == sent


def test_reopened_material_window_restores_close_guard_and_polling(window, app):
    editor, _ = window
    editor.timer.setInterval(100000)
    editor.show()
    app.processEvents()
    editor._allow_close = True
    editor.close()
    assert not editor.timer.isActive()
    editor.show()
    app.processEvents()
    assert not editor._allow_close and editor.timer.isActive()


def test_apply_preserves_invalid_coefficient_and_tensor_text(window, app):
    editor, client = window
    editor.coefficients.item(0, 1).setText("not a modulus")
    editor.history.item(1, 4).setText("")
    assert not editor.run_button.isEnabled()
    editor.apply_button.click()
    until(app, lambda: not editor._busy and editor.document["generation"] == 1)
    sent = client.commands[-1]
    assert sent[1] == "material.update"
    assert sent[2]["draft"]["settings"]["parameters"]["E"] == "not a modulus"
    assert sent[2]["draft"]["settings"]["deformation_gradient"][1][1][0] == ""
    assert editor.history.item(1, 4).text() == ""
    assert edited_number("nan") == "nan"
    assert edited_number(" ") == " "
    assert not editor.local_dirty


def test_undo_redo_and_save_are_service_commands_not_private_history(window, app):
    editor, client = window
    editor.coefficients.item(0, 1).setText("2000")
    editor.apply_inputs()
    until(app, lambda: not editor._busy)
    editor.undo_action.trigger()
    until(app, lambda: not editor._busy)
    assert editor.coefficients.item(0, 1).text() == "1000"
    editor.redo_action.trigger()
    until(app, lambda: not editor._busy)
    assert editor.coefficients.item(0, 1).text() == "2000.0"
    editor.save_action.trigger()
    until(app, lambda: not editor._busy)
    assert [item[1] for item in client.commands] == ["material.update", "document.undo", "document.redo", "document.save"]
    assert [item[3] for item in client.commands] == [0, 1, 2, 3]
    assert len({item[4] for item in client.commands}) == 4
    assert not editor.document["dirty"]
    assert editor.document["saved_revision"] == 1


def test_result_plot_uses_retained_values_and_labels_earlier_inputs(window, app):
    editor, client = window
    editor.run_button.click()
    until(app, lambda: bool(editor.axes.lines) and not editor._busy)
    assert list(editor.axes.lines[0].get_ydata()) == [0., 1.2, 2.4]
    assert editor.values.item(2, 2).text() == "2.4 MPa"
    assert "TEST_ONLY_RETAINED_RESPONSE_FIXTURE" in editor.diagnostics.toPlainText()
    editor.coefficients.item(0, 1).setText("3000")
    assert "earlier input" in editor.axes.lines[0].get_label()
    assert list(editor.axes.lines[0].get_ydata()) == [0., 1.2, 2.4]
    assert [item[1] for item in client.commands] == ["material.evaluate"]
    editor._selection_changed()
    assert [item[1] for item in client.commands] == ["material.evaluate"]


def test_failed_run_does_not_make_a_curve(window, app):
    editor, client = window
    client.job_state = "FAILED"
    editor.evaluate()
    until(app, lambda: editor._job_status.get("J1", {}).get("state") == "FAILED" and not editor._busy)
    assert not editor.axes.lines
    assert not client.results_read
    assert "TEST_ONLY_FAILURE" in editor.diagnostics.toPlainText()


def test_saved_document_curve_reopens_without_original_job(window, app):
    editor, client = window
    identifier = editor.document["id"]
    client.docs[identifier]["runs"] = [{"job_id": "J-old", "input_generation": 0,
        "input_revision": 1, "input_sha256": "saved-hash", "settings": material_draft()["settings"],
        "retained_result": {"revision": 1, "job_id": "J-old"},
        "retained_state": "SUCCEEDED", "retention_complete": True}]
    def no_original_job(_):
        raise AssertionError("The old live job is unavailable")
    client.status = no_original_job
    editor.open_document(document_id=identifier)
    until(app, lambda: bool(editor.axes.lines) and not editor._busy)
    assert list(editor.axes.lines[0].get_ydata()) == [0., 1.2, 2.4]
    assert client.results_read[-1][0:2] == (identifier, "J-old")
    assert "saved document" in editor.diagnostics.toPlainText()


def test_remote_generation_conflict_preserves_local_cells_and_copy(window, app):
    editor, client = window
    identifier = editor.document["id"]
    editor.coefficients.item(0, 1).setText("local-invalid")
    client.docs[identifier]["generation"] = 1
    client.docs[identifier]["draft"]["settings"]["parameters"]["E"] = 9000
    editor.refresh_document()
    until(app, lambda: editor.conflict and not editor._busy)
    assert editor.coefficients.item(0, 1).text() == "local-invalid"
    assert not editor.apply_button.isEnabled()
    assert not editor.run_button.isEnabled()
    assert not editor.save_action.isEnabled()
    editor.copy_button.click()
    until(app, lambda: not editor._busy and editor.document["id"] != identifier)
    assert editor.document["draft"]["settings"]["parameters"]["E"] == "local-invalid"
    assert client.docs[identifier]["draft"]["settings"]["parameters"]["E"] == 9000
    assert not editor.conflict


def test_idle_remote_edit_refreshes_and_saved_document_reopens(window, app):
    editor, client = window
    identifier = editor.document["id"]
    client.docs[identifier]["generation"] = 2
    client.docs[identifier]["draft"]["settings"]["parameters"]["E"] = 4000
    editor.refresh_document()
    until(app, lambda: editor.document["generation"] == 2 and not editor._busy)
    assert editor.coefficients.item(0, 1).text() == "4000"
    editor.coefficients.item(0, 1).setText("draft-to-save")
    editor.save_document()
    until(app, lambda: not editor._busy and editor.document["saved_revision"] == 1)
    assert [item[1] for item in client.commands] == ["material.update", "document.save"]
    editor.open_document(document_id=identifier)
    until(app, lambda: not editor._busy)
    assert editor.coefficients.item(0, 1).text() == "draft-to-save"
    assert not editor.document["dirty"]


def test_close_cancel_keeps_unsent_text_then_save_closes_without_job_cancel(window, app):
    editor, client = window
    editor.show()  # QT_QPA_PLATFORM=offscreen: never a visible desktop window.
    editor.coefficients.item(0, 1).setText("2500")

    def choose(text):
        dialog = QApplication.activeModalWidget()
        assert isinstance(dialog, QMessageBox)
        next(button for button in dialog.buttons() if button.text() == text).click()

    QTimer.singleShot(0, lambda: choose("Cancel"))
    editor.close()
    assert editor.isVisible()
    assert editor.coefficients.item(0, 1).text() == "2500"
    assert not client.commands
    QTimer.singleShot(0, lambda: choose("Save"))
    editor.close()
    until(app, lambda: not editor.isVisible() and not editor._busy)
    assert [item[1] for item in client.commands] == ["material.update", "document.save"]


def test_new_law_requires_explicit_coefficients_instead_of_silent_conversion(window):
    editor, client = window
    editor.model.setCurrentIndex(editor.model.findData("neo_hooke"))
    assert editor.edited_draft()["settings"]["parameters"] == {"mu": "", "lmbda": ""}
    assert not editor.run_button.isEnabled()
    assert not client.commands


@pytest.mark.parametrize("settings", [None, {}, {"model": "other-law"},
    {**material_draft()["settings"], "deformation_gradient": []}])
def test_malformed_remote_draft_is_preserved_and_can_still_be_saved(window, app, settings):
    editor, client = window
    draft = {"backend": "material.felupe", "settings": settings}
    editor.open_document(draft=draft)
    until(app, lambda: not editor._busy)
    assert not editor.editor.isEnabled()
    assert not editor.run_button.isEnabled()
    assert editor.edited_draft() == draft
    assert "preserved_draft" in editor.diagnostics.toPlainText()
    editor.save_document()
    until(app, lambda: not editor._busy)
    assert client.docs[editor.document["id"]]["draft"] == draft
    assert client.commands[-1][1] == "document.save"


def test_other_edits_do_not_coerce_untouched_invalid_json_values(window, app):
    editor, _ = window
    draft = material_draft()
    draft["settings"]["parameters"]["E"] = None
    draft["settings"]["deformation_gradient"][2][1][0] = {"invalid": True}
    editor.open_document(draft=draft)
    until(app, lambda: not editor._busy)
    editor.coefficients.item(1, 1).setText("0.3")
    # Removing a preceding row must carry that remaining cell's original JSON type.
    editor.history.selectRow(0)
    editor.remove_states()
    result = editor.edited_draft()["settings"]
    assert result["parameters"] == {"E": None, "nu": .3}
    assert result["deformation_gradient"][1][1][0] == {"invalid": True}


def test_save_commits_the_active_table_editor_before_sending(window, app):
    editor, client = window
    editor.show()  # The process is offscreen.
    item = editor.coefficients.item(0, 1)
    editor.coefficients.setCurrentItem(item)
    editor.coefficients.editItem(item)
    until(app, lambda: editor.coefficients.state() == editor.coefficients.State.EditingState)
    focus = QApplication.focusWidget()
    assert editor.coefficients.isAncestorOf(focus)
    QTest.keyClick(focus, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
    QTest.keyClicks(focus, "3456")
    editor.save_document()
    until(app, lambda: not editor._busy and not editor.document["dirty"])
    assert client.docs[editor.document["id"]]["draft"]["settings"]["parameters"]["E"] == 3456
    assert [item[1] for item in client.commands] == ["material.update", "document.save"]


def test_real_http_owner_edit_save_remote_undo_and_service_restart(app, tmp_path):
    """Real transport/owner integration, with no evaluation or solver execution."""
    from contextlib import contextmanager
    from apps.lab.server import LabHTTPServer
    from apps.lab.service import LabService
    from caelab.workbench_client import Client

    @contextmanager
    def connected(document_id=None):
        service = LabService(tmp_path / "new-http-store")
        server = LabHTTPServer(service, 0)
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": .02}, daemon=True)
        thread.start()
        client = Client(f"http://127.0.0.1:{server.server_port}")
        editor = MaterialWindow(client, document_id=document_id, poll_interval=0)
        try:
            until(app, lambda: editor.document is not None and not editor._busy)
            yield editor, client
        finally:
            until(app, lambda: not editor._busy)
            editor._allow_close = True
            editor.close()
            server.shutdown()
            server.server_close()
            service.shutdown()
            thread.join(timeout=2)

    with connected() as (editor, client):
        identifier = editor.document["id"]
        first_session = editor.document["session_id"]
        editor.coefficients.item(0, 1).setText("invalid but retained")
        editor.save_document()
        until(app, lambda: not editor._busy and editor.document["saved_revision"] is not None)
        assert editor.document["diagnostics"][0]["blocks_evaluation"]
        assert not editor.run_button.isEnabled()
        assert not editor.document["runs"]
        remote = client.document_read(identifier)
        draft = deepcopy(remote["draft"])
        draft["settings"]["parameters"]["E"] = 2345
        client.document_command(identifier, "material.update", {"draft": draft},
            session_id=remote["session_id"], expected_generation=remote["generation"])
        editor.refresh_document()
        until(app, lambda: not editor._busy and editor.coefficients.item(0, 1).text() == "2345")
        editor.undo_action.trigger()
        until(app, lambda: not editor._busy)
        assert editor.coefficients.item(0, 1).text() == "invalid but retained"
        editor.redo_action.trigger()
        until(app, lambda: not editor._busy)
        assert editor.coefficients.item(0, 1).text() == "2345"
        editor.save_document()
        until(app, lambda: not editor._busy and not editor.document["dirty"])
        saved_revision = editor.document["saved_revision"]
    with connected(identifier) as (editor, client):
        assert editor.document["session_id"] != first_session
        assert editor.document["saved_revision"] == saved_revision
        assert editor.coefficients.item(0, 1).text() == "2345"
        assert not editor.document["dirty"]
        assert not editor.document["runs"]
        assert not editor.axes.lines
