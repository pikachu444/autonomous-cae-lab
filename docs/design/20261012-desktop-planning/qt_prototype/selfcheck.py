"""Bounded offscreen widget/state check; not physical or real-desktop acceptance."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from copy import deepcopy
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtGui import QFont
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QCloseEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLineEdit, QMessageBox
from main import HERE, MaterialPrototype, configure_font, stable, result_input_hash, coefficient_text


def finish(window, app):
    for _ in range(12):
        QTest.qWait(220)
        app.processEvents()
        if window.running_id is None:
            return
    raise AssertionError("simulation timer did not complete")


def capture(window, app, path, width, height):
    window.resize(width, height)
    window.show()
    app.processEvents()
    window.canvas.draw()
    app.processEvents()
    assert window.grab().save(str(path))


def cold_reopen(path):
    app = QApplication([])
    configure_font(app)
    window = MaterialPrototype()
    window.load_document(path)
    assert window.fit_starts == 0 and not window.timer.isActive()
    assert window.doc["coefficients"] == {"E": 2.4, "b": .02}
    assert [r["status"] for r in window.doc["results"]] == ["cancelled", "failed", "complete", "complete"]
    assert not window.dirty
    assert base64.b64decode(window.source()["raw_bytes_base64"]) == (HERE / "demo_test.csv").read_bytes()
    assert window.doc["selection"] == [4, 17]
    print("cold reopen: saved source, inputs, coefficients and 4 records; zero fit starts")


def draft_reopen(path):
    app = QApplication([])
    configure_font(app)
    saved = json.loads(path.read_text(encoding="utf-8"))
    window = MaterialPrototype()
    window.load_document(path)
    assert window.doc["coefficients"] == saved["coefficients"]
    assert window.doc["source_contexts"] == saved["source_contexts"]
    assert window.fit_starts == 0 and not window.timer.isActive()
    assert not window.dirty and not window.readiness()[0] and not window.can_adopt()
    assert window.coefficientTable.item(0, 1).text() == coefficient_text(saved["coefficients"]["E"])
    print("cold invalid draft reopen: exact coefficient draft and source editors; zero fit starts")


def edit_coefficient_with_keyboard(window, app, text):
    table = window.coefficientTable
    item = table.item(0, 1)
    table.scrollToItem(item)
    QTest.mouseClick(table.viewport(), Qt.LeftButton, Qt.NoModifier, table.visualItemRect(item).center())
    QTest.keyClick(table, Qt.Key_F2)
    app.processEvents()
    editor = table.findChild(QLineEdit)
    assert editor is not None, "native coefficient editor did not open"
    QTest.keyClick(editor, Qt.Key_A, Qt.ControlModifier)
    QTest.keyClick(editor, Qt.Key_Backspace)
    QTest.keyClicks(editor, text)
    QTest.keyClick(editor, Qt.Key_Return)
    app.processEvents()


def check_review_regressions(app, out):
    window = MaterialPrototype()
    window.load_csv(HERE / "demo_test.csv")
    window.show()
    window.activateWindow()
    app.processEvents()
    table = window.dataTable
    table.setFocus()
    second = table.visualItemRect(table.item(1, 1)).center()
    fifth = table.visualItemRect(table.item(4, 1)).center()
    QTest.mouseClick(table.viewport(), Qt.LeftButton, Qt.NoModifier, second)
    app.processEvents()
    assert window.doc["selection"] == [2, 2] and table.currentRow() == 1
    QTest.mouseClick(table.viewport(), Qt.LeftButton, Qt.ShiftModifier, fifth)
    app.processEvents()
    assert window.doc["selection"] == [2, 5] and table.currentRow() == 4
    QTest.keyClick(table, Qt.Key_Down, Qt.ShiftModifier)
    app.processEvents()
    assert window.doc["selection"] == [2, 6] and table.currentRow() == 5
    QTest.keyClick(table, Qt.Key_Up, Qt.ShiftModifier)
    app.processEvents()
    assert window.doc["selection"] == [2, 5] and table.currentRow() == 4
    source_a = window.doc["active_source"]
    window.xUnit.setCurrentText("%")
    window.yUnit.setCurrentText("kPa")
    window.edit("시험 A 구간", selection=[4, 17])
    context_a = window.context()
    raw_a = deepcopy(window.source())
    window.load_csv(HERE / "demo_test.csv")
    source_b = window.doc["active_source"]
    assert source_b != source_a
    window.edit("시험 B 구간", selection=[2, 8])
    context_b = window.context()
    window.testList.setCurrentRow(0)
    assert window.context() == context_a and window.source() == raw_a
    window.testList.setCurrentRow(1)
    assert window.context() == context_b
    window.undo_stack.undo()
    assert window.context() == context_a
    window.undo_stack.redo()
    assert window.context() == context_b
    window.testList.setCurrentRow(0)
    window.resize(1440, 900)
    app.processEvents()
    edit_coefficient_with_keyboard(window, app, "-1")
    assert window.doc["coefficients"]["E"] == "-1"
    assert window.coefficientTable.item(0, 1).text() == "-1"
    assert not window.fitButton.isEnabled() and not window.start_fit()
    assert "계수 E" in window.diagnostic.text()
    capture(window, app, out / "06-invalid-coefficient-1440x900.png", 1440, 900)
    capture(window, app, out / "07-invalid-coefficient-1000x650.png", 1000, 650)
    with tempfile.TemporaryDirectory() as temp:
        path = Path(temp) / "invalid-coefficient.demo.json"
        window.save(path)
        subprocess.run([sys.executable, str(Path(__file__).resolve()), "--draft-reopen", str(path)],
                       check=True, env={**os.environ, "QT_QPA_PLATFORM": "offscreen"})
        reopened = MaterialPrototype()
        reopened.load_document(path)
        assert reopened.doc["coefficients"]["E"] == "-1"
        assert not reopened.fitButton.isEnabled() and not reopened.dirty
        assert reopened.context() == context_a and reopened.fit_starts == 0
        reopened.testList.setCurrentRow(1)
        assert reopened.context() == context_b
        reopened.testList.setCurrentRow(0)
        assert reopened.context() == context_a
        window.resize(1440, 900)
        app.processEvents()
        edit_coefficient_with_keyboard(window, app, "not-a-number")
        assert window.doc["coefficients"]["E"] == "not-a-number"
        window.save(path)
        subprocess.run([sys.executable, str(Path(__file__).resolve()), "--draft-reopen", str(path)],
                       check=True, env={**os.environ, "QT_QPA_PLATFORM": "offscreen"})
        reopened.load_document(path)
        assert reopened.doc["coefficients"]["E"] == "not-a-number"
        assert not reopened.readiness()[0]
        edit_coefficient_with_keyboard(window, app, "1.2")
        assert window.doc["coefficients"]["E"] == 1.2 and window.fitButton.isEnabled()
        window.undo_stack.undo()
        assert window.doc["coefficients"]["E"] == "not-a-number" and not window.fitButton.isEnabled()
        window.undo_stack.redo()
        assert window.doc["coefficients"]["E"] == 1.2 and window.readiness()[0]
        for draft in ("", "NaN", "Infinity"):
            edit_coefficient_with_keyboard(window, app, draft)
            assert window.doc["coefficients"]["E"] == draft
            assert window.coefficientTable.item(0, 1).text() == draft
            assert window.coefficientTable.item(0, 1).toolTip()
            assert not window.fitButton.isEnabled() and not window.can_adopt() and not window.start_fit()
            window.save(path)
            subprocess.run([sys.executable, str(Path(__file__).resolve()), "--draft-reopen", str(path)],
                           check=True, env={**os.environ, "QT_QPA_PLATFORM": "offscreen"})
        reopened.hide()
        reopened.deleteLater()
    window.hide()
    window.deleteLater()
    app.processEvents()


def respond_to_demo_warning(app, label, seen):
    warning = app.activeModalWidget()
    assert isinstance(warning, QMessageBox)
    assert "로컬 DEMO 타이머가 중단" in warning.text()
    assert warning.defaultButton().text() == "계속 보기"
    seen.append(warning.text())
    button = next(button for button in warning.buttons() if button.text() == label)
    QTest.mouseClick(button, Qt.LeftButton)


def assert_adoption_display(window, expected):
    assert window.can_adopt() == expected and window.adoptButton.isEnabled() == expected
    assert window.targetLabel.text().splitlines()[-1] == ("채택 가능" if expected else "채택 차단")


def respond_yes(app):
    dialog = app.activeModalWidget()
    assert isinstance(dialog, QMessageBox) and "계수 채택" in dialog.windowTitle()
    QTest.mouseClick(dialog.button(QMessageBox.Yes), Qt.LeftButton)


def check_remaining_review_regressions(app, out):
    window = MaterialPrototype()
    window.load_csv(HERE / "demo_test.csv")
    window.show()
    app.processEvents()
    window.start_fit()
    finish(window, app)
    result = deepcopy(window.selected_result())
    assert_adoption_display(window, True)
    window.resize(1000, 650)
    app.processEvents()
    QTimer.singleShot(0, lambda: respond_yes(app))
    QTest.mouseClick(window.adoptButton, Qt.LeftButton)
    assert window.doc["coefficients"] == {"E": 2.4, "b": .02}
    assert_adoption_display(window, False)
    assert "채택 차단" in window.diagnostic.text()
    app.processEvents()
    assert_adoption_display(window, False)
    capture(window, app, out / "09-adopted-target-1000x650.png", 1000, 650)
    window.undo_stack.undo()
    assert_adoption_display(window, True)
    window.undo_stack.redo()
    assert_adoption_display(window, False)
    window.undo_stack.undo()
    assert_adoption_display(window, True)
    window.edit("계수 변경", coefficients={"E": 5, "b": 0})
    assert window.readiness()[0] and not window.can_adopt()
    assert_adoption_display(window, False)
    try:
        window.adopt()
        raise AssertionError("changed coefficient adopted stale result")
    except ValueError:
        pass
    assert window.selected_result() == result
    window.undo_stack.undo()
    assert_adoption_display(window, True)
    window.edit("invalid 계수", coefficients={"E": "", "b": 0})
    assert not window.can_adopt() and not window.start_fit()
    window.undo_stack.undo()
    assert window.can_adopt()
    first_branch = window.revision_serial
    window.edit("분기 A", coefficients={"E": 3, "b": 0})
    branch_a = window.doc["revision"]
    window.undo_stack.undo()
    window.edit("분기 B", coefficients={"E": 4, "b": 0})
    assert window.doc["revision"] > branch_a > first_branch
    window.undo_stack.undo()
    assert window.can_adopt()
    with tempfile.TemporaryDirectory() as temp:
        path = Path(temp) / "valid.demo.json"
        window.save(path)
        saved = json.loads(path.read_text(encoding="utf-8"))
        invalid_with_result = Path(temp) / "invalid-with-result.demo.json"
        window.edit("보존 후보와 invalid 초안", coefficients={"E": "", "b": 0})
        window.save(invalid_with_result)
        subprocess.run([sys.executable, str(Path(__file__).resolve()), "--draft-reopen", str(invalid_with_result)],
                       check=True, env={**os.environ, "QT_QPA_PLATFORM": "offscreen"})
        window.undo_stack.undo()
        window.save(path)
        live = stable(window.doc)
        serial = window.revision_serial
        malformed = Path(temp) / "forged.demo.json"
        variants = []
        def forge(key, value):
            candidate = deepcopy(saved)
            candidate["results"][0][key] = value
            variants.append(candidate)
        forge("source_sha256", "0" * 64)
        forge("input_coefficients", {"E": 7, "b": 0})
        forge("input_coefficients", {"E": -1, "b": 0})
        forge("context", {**result["context"], "selection": [0, 999]})
        forge("context", {**result["context"], "mapping": {**result["context"]["mapping"], "x_unit": "psi"}})
        forge("observed", [result["observed"][0] + 123] + result["observed"][1:])
        # Recompute the local consistency hash to prove the independent source/range comparison rejects forged observations.
        source_checked = deepcopy(variants[-1])
        source_checked["results"][0]["input_sha256"] = result_input_hash(source_checked["results"][0])
        variants.append(source_checked)
        forge("x", [result["x"][0] + 123] + result["x"][1:])
        for candidate in variants:
            malformed.write_text(stable(candidate), encoding="utf-8")
            try:
                window.load_document(malformed)
                raise AssertionError("forged retained input accepted")
            except (ValueError, KeyError, TypeError):
                assert stable(window.doc) == live and window.revision_serial == serial
                assert window.path == path and not window.timer.isActive()
        window.load_document(path)
        assert window.revision_serial == serial
        window.edit("재열기 후 새 분기", coefficients={"E": 6, "b": 0})
        assert window.doc["revision"] > serial
        window.undo_stack.undo()
        assert window.can_adopt()
        window.resize(1000, 650)
        app.processEvents()
        assert window.targetLabel.isVisible()
        assert window.testDock.rect().contains(window.targetLabel.mapTo(window.testDock, window.targetLabel.rect().center()))
        assert "DEMO #1" in window.targetLabel.text() and "complete" in window.targetLabel.text()
        assert "현재 입력:" in window.stateLabel.text()
        assert "완료" in window.progress.format() and "종료" in window.progress.format()
        capture(window, app, out / "08-target-status-1000x650.png", 1000, 650)
        window.start_fit()
        window.save(path)
        assert not window.dirty and window.timer.isActive()
        malformed.write_text(stable(variants[0]), encoding="utf-8")
        live_running = stable(window.doc)
        try:
            window.load_document(malformed)
            raise AssertionError("forged reopen replaced running document")
        except ValueError:
            assert stable(window.doc) == live_running and window.timer.isActive() and window.running_id
        seen = []
        QTimer.singleShot(0, lambda: respond_to_demo_warning(app, "계속 보기", seen))
        event = QCloseEvent()
        window.closeEvent(event)
        assert not event.isAccepted() and window.timer.isActive() and window.running_id
        # Saved running input still warns on a document replacement, before opening a file dialog.
        QTimer.singleShot(0, lambda: respond_to_demo_warning(app, "계속 보기", seen))
        with patch("main.QFileDialog.getOpenFileName") as dialog:
            window.open_document_dialog()
            dialog.assert_not_called()
        assert window.timer.isActive() and window.running_id
        QTimer.singleShot(0, lambda: respond_to_demo_warning(app, "DEMO 중단 후 계속", seen))
        with patch("main.QFileDialog.getOpenFileName", return_value=(str(path), "")):
            window.open_document_dialog()
        assert len(seen) == 3 and not window.timer.isActive() and not window.running_id
        assert window.selected_result()["status"] == "interrupted"
        assert "interrupted" in window.targetLabel.text() and "중단" in window.progress.format()
        window.start_fit()
        window.save(path)
        QTimer.singleShot(0, lambda: respond_to_demo_warning(app, "DEMO 중단 후 계속", seen))
        event = QCloseEvent()
        window.closeEvent(event)
        assert event.isAccepted() and not window.timer.isActive()
    window.hide()
    window.deleteLater()
    app.processEvents()


def check():
    app = QApplication([])
    configure_font(app)
    window = MaterialPrototype()
    out = HERE / "evidence"
    out.mkdir(exist_ok=True)
    check_review_regressions(app, out)
    check_remaining_review_regressions(app, out)
    window.show()
    app.processEvents()
    assert not window.fitButton.isEnabled()
    capture(window, app, out / "01-empty-1440x900.png", 1440, 900)
    window.load_csv(HERE / "demo_test.csv")
    assert window.dirty and window.readiness()[0]
    window.yUnit.setCurrentText("psi")
    assert not window.readiness()[0] and not window.fitButton.isEnabled()
    assert window.start_fit() is False
    capture(window, app, out / "02-invalid-unit-1000x650.png", 1000, 650)
    window.yUnit.setCurrentText("MPa")
    assert window.readiness()[0]
    window.xColumn.setCurrentText("stress")
    assert not window.readiness()[0]
    window.xColumn.setCurrentText("strain")
    window.dataTable.clearSelection()
    window.dataTable.selectRow(4)
    assert window.doc["selection"] == [5, 5] and not window.readiness()[0]
    window.plot_selected(.03, .16)
    assert window.doc["selection"] == [4, 17]
    assert window.firstRow.value() == 4 and window.lastRow.value() == 17
    assert sorted({i.row() + 1 for i in window.dataTable.selectedIndexes()}) == list(range(4, 18))
    window.fitButton.click()
    QTest.qWait(250)
    assert window.running_id and window.progress.value() > 0
    window.cancelButton.click()
    assert window.doc["results"][-1]["status"] == "cancelled"
    window.failure_action.setChecked(True)
    window.fitButton.click()
    finish(window, app)
    assert window.doc["results"][-1]["status"] == "failed"
    assert "실패" in window.progress.format() and "종료" in window.progress.format()
    assert "failed" in window.targetLabel.text() and "현재 입력:" in window.stateLabel.text()
    assert window.readiness()[0]
    capture(window, app, out / "03-failed-1000x650.png", 1000, 650)
    window.failure_action.setChecked(False)
    window.fitButton.click()
    finish(window, app)
    assert window.doc["results"][-1]["status"] == "complete"
    first_complete = deepcopy(window.doc["results"][-1])
    window.plot_selected(.04, .13)
    assert not window.can_adopt()
    window.undo_stack.undo()
    assert window.can_adopt()
    old_coefficients = deepcopy(window.doc["coefficients"])
    window.adopt()
    assert window.doc["coefficients"] == {"E": 2.4, "b": .02}
    window.undo_stack.undo()
    assert window.doc["coefficients"] == old_coefficients
    window.undo_stack.redo()
    assert window.doc["coefficients"] == {"E": 2.4, "b": .02}
    window.fitButton.click()
    window.yUnit.setCurrentText("kPa")
    finish(window, app)
    assert window.doc["results"][-1]["context"]["mapping"]["y_unit"] == "MPa"
    assert not window.can_adopt()
    window.undo_stack.undo()
    assert window.can_adopt()
    assert window.doc["results"][2] == first_complete
    capture(window, app, out / "04-comparison-1440x900.png", 1440, 900)
    capture(window, app, out / "05-comparison-1000x650.png", 1000, 650)
    # Actual QDockWidget methods verify structure, not window-manager dragging on a desktop.
    window.testDock.setFloating(True)
    app.processEvents()
    assert window.testDock.isFloating()
    window.restore_layout()
    assert not window.testDock.isFloating()
    with tempfile.TemporaryDirectory() as temp:
        path = Path(temp) / "saved.demo.json"
        window.save(path)
        assert not window.dirty
        saved_bytes = path.read_bytes()
        window.edit("계수 수정", coefficients={"E": 3, "b": .02})
        assert window.dirty
        window.undo_stack.undo()
        assert not window.dirty
        before = stable(window.doc)
        bad = Path(temp) / "bad.demo.json"
        bad.write_text('{"format":"wrong"}', encoding="utf-8")
        try:
            window.load_document(bad)
            raise AssertionError("malformed document accepted")
        except ValueError:
            assert stable(window.doc) == before
        try:
            window.save(Path(temp) / "missing" / "saved.demo.json")
            raise AssertionError("unavailable directory accepted")
        except OSError:
            assert path.read_bytes() == saved_bytes
        subprocess.run([sys.executable, str(Path(__file__).resolve()), "--cold-reopen", str(path)],
                       check=True, env={**os.environ, "QT_QPA_PLATFORM": "offscreen"})
        invalid_draft = MaterialPrototype()
        invalid_draft.load_document(path)
        invalid_draft.yUnit.setCurrentText("psi")
        invalid_path = Path(temp) / "invalid-draft.demo.json"
        invalid_draft.save(invalid_path)
        invalid_draft.load_document(invalid_path)
        assert not invalid_draft.readiness()[0] and not invalid_draft.dirty
        assert invalid_draft.fit_starts == 0
        window.save(out / "review.demo.json")
        window.fitButton.click()
        window.save(path)
        reopened = MaterialPrototype()
        reopened.load_document(path)
        assert reopened.doc["results"][-1]["status"] == "interrupted"
        assert reopened.fit_starts == 0 and reopened.dirty
        window.cancel_fit()
        window.load_document(out / "review.demo.json")
        missing = Path(temp) / "missing.csv"
        # Reopen never reads the original file; the retained bytes suffice.
        window.source()["path"] = str(missing)
        window.save(path)
        reopened.load_document(path)
        assert reopened.readiness()[0] and reopened.fit_starts == 0
    report = {
        "artifact_status": "provisional planning technical check; existing Pro v2 basis",
        "mode": "QT_QPA_PLATFORM=offscreen; QWidget.grab; no desktop input or OS screenshots",
        "python": sys.version.split()[0], "pyside6": __import__("PySide6").__version__,
        "matplotlib": __import__("matplotlib").__version__,
        "source_sha256": {name: hashlib.sha256((HERE / name).read_bytes()).hexdigest()
                          for name in ("main.py", "material.ui", "selfcheck.py")},
        "checked": ["empty state", "unsupported unit and mapping block/correction", "table/plot linked selection",
                    "real offscreen QTest row2 click / Shift-row5 click / Shift-arrow selection preserves current index",
                    "source A-B-A retains each mapping/units/selection through undo/redo and save/reopen",
                    "native coefficient editor preserves negative/non-numeric drafts, blocks run, corrects, undo/redo and saves/reopens",
                    "empty/negative/text/NaN/Infinity coefficient drafts cold subprocess reopen, zero fits; invalid with complete result cannot adopt",
                    "edited input coefficients block stale adoption and preserve original result input",
                    "forged source hash/context/range/input coefficients/x/observed reject before replacing live or running document; no fit rerun",
                    "1000x650 fixed selected candidate/status; input readiness separate from terminal completion/failure progress",
                    "QTest adopt-button/Yes dialog then immediate/event-processed fixed target and button agree; Undo/Redo/coefficient edit keep gate display consistent",
                    "saved running close/replace QMessageBox warns local DEMO stops; offscreen QTest keep/stop actions preserve or stop timer",
                    "new Undo branch edit versions remain unique after save/reopen",
                    "timer start/cancel", "injected failure/new-run recovery", "fixed simulated comparison",
                    "stale-result adoption block", "adoption undo/redo", "raw bytes and old result preservation",
                    "atomic save error preserves previous file", "malformed reopen preserves current document",
                    "cold subprocess reopen without computation", "interrupted save reopens as interrupted",
                    "dirty state after edit and undo", "missing original source works from retained bytes",
                    "unsupported unit draft saves and reopens without fit",
                    "floating/redocking Qt API", "1440x900 and 1000x650 widget captures"],
        "unverified": ["actual desktop dragging/floating/keyboard/file dialogs/DPI/accessibility", "physical/numerical validity",
                       "product services, common owner/revisions/GUI-CLI-Python-MCP", "large data responsiveness",
                       "new actual Pro design acceptance and Astra final review"],
    }
    (out / "selfcheck-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("PASS: bounded offscreen path, Qt input/dialog regressions and cold reopen; 9 widget captures")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--cold-reopen", type=Path)
    parser.add_argument("--draft-reopen", type=Path)
    args = parser.parse_args()
    if args.cold_reopen:
        cold_reopen(args.cold_reopen)
    elif args.draft_reopen:
        draft_reopen(args.draft_reopen)
    else:
        check()
