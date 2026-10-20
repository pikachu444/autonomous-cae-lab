"""Real Qt local history editor events, authoritative admission; no Core/solver."""
from copy import deepcopy
import json
from pathlib import Path

import pytest
from PySide6.QtCore import Qt, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QDialogButtonBox, QLineEdit

from apps.research.appearance import apply_appearance
from apps.research.impact_interface_history_dialog import InterfaceHistoryDialog
from caelab.impact_interface_history import validate
from caelab.impact_model import model_from_settings
from examples.impact.cohesive_model import settings as coupon


@pytest.fixture(scope='module')
def app():
    app = QApplication.instance() or QApplication([])
    apply_appearance(app)
    return app


def settings():
    value = coupon(); value['motions'] = []
    value['interface_histories'] = [{'name': 'normal', 'material': 'BOND', 'node_set': 'MOVING',
        'component': 'Z', 'time_s': [0., .00025, .0005, .00075, .001],
        'displacement_mm': [0., .008, 0., -.002, .008], 'frame': 'MODEL_GLOBAL'}]
    return value


def edit(app, dialog, row, col, text):
    dialog.table.setCurrentCell(row, col)
    dialog.table.setFocus()
    QTest.keyClick(dialog.table, Qt.Key.Key_F2); app.processEvents()
    editor = app.focusWidget()
    assert isinstance(editor, QLineEdit)
    QTest.keyClick(editor, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
    QTest.keyClicks(editor, text)
    QTest.keyClick(editor, Qt.Key.Key_Tab); app.processEvents()
    assert dialog.table.item(row, col).text() == text


def test_exact_nochange_cancel_and_deepcopy(app):
    original = settings(); before = deepcopy(original)
    dialog = InterfaceHistoryDialog(original)
    try:
        dialog.show(); app.processEvents()
        assert dialog.draft == before
        assert dialog.check()
        dialog.accept(); assert dialog.result() == QDialog.DialogCode.Accepted
        returned = dialog.draft; returned['source']['title'] = 'mutated copy'
        assert original == before and dialog.draft == before
    finally:
        dialog.close(); dialog.deleteLater(); app.processEvents()
    dialog = InterfaceHistoryDialog(original)
    try:
        dialog.show(); app.processEvents()
        edit(app, dialog, 1, 1, '0.009')
        assert dialog.draft != before
        QTest.mouseClick(dialog.buttons.button(QDialogButtonBox.StandardButton.Cancel), Qt.MouseButton.LeftButton)
        assert dialog.result() == QDialog.DialogCode.Rejected
        assert original == before
    finally:
        dialog.close(); dialog.deleteLater(); app.processEvents()


def test_actual_edit_validation_recovery_preview_accept(app, tmp_path):
    original = settings(); before = deepcopy(original)
    dialog = InterfaceHistoryDialog(original)
    try:
        dialog.show(); app.processEvents()
        edit(app, dialog, 2, 0, '0.00025')
        QTest.mouseClick(dialog.check_button, Qt.MouseButton.LeftButton); app.processEvents()
        assert '엄격히 증가' in dialog.status.text()
        dialog.accept(); assert dialog.result() != QDialog.DialogCode.Accepted
        assert dialog.grab().save(str(tmp_path / 'history-invalid.png'))
        edit(app, dialog, 2, 0, '0.0005')
        assert dialog.check()
        assert dialog.table.currentRow() >= 0
        for width, height, filename in [(980, 740, 'history-normal.png'), (740, 650, 'history-narrow.png')]:
            dialog.resize(width, height); app.processEvents()
            assert dialog.grab().save(str(tmp_path / filename))
            assert dialog.table.columnViewportPosition(1) + dialog.table.columnWidth(1) <= dialog.table.viewport().width() + 2
        dialog.tabs.setCurrentIndex(1); app.processEvents()
        assert len(dialog.figure.axes[0].lines[0].get_xdata()) == 5
        assert dialog.grab().save(str(tmp_path / 'history-curve-narrow.png'))
        QTest.mouseClick(dialog.buttons.button(QDialogButtonBox.StandardButton.Ok), Qt.MouseButton.LeftButton)
        assert dialog.result() == QDialog.DialogCode.Accepted
        assert validate(model_from_settings(original), dialog.draft)
        assert original == before
        (tmp_path / 'receipt.json').write_text(json.dumps({'qt_platform': app.platformName(),
            'source_unchanged': original == before, 'core_commands': 0, 'solver_runs': 0,
            'accepted': True}, indent=2), encoding='utf-8')
    finally:
        dialog.close(); dialog.deleteLater(); app.processEvents()


def test_explicit_axis_rows_local_undo_and_redo(app):
    original = settings(); original.pop('interface_histories')
    before = deepcopy(original); dialog = InterfaceHistoryDialog(original)
    try:
        dialog.show(); app.processEvents()
        assert dialog.draft == original
        QTest.mouseClick(dialog.add_history, Qt.MouseButton.LeftButton); app.processEvents()
        assert dialog.component.currentData() == ''
        assert dialog.draft['interface_histories'][0]['time_s'] == ['', '']
        QTest.keyClicks(dialog.name, 'shear')
        for combo, value in [(dialog.material, 'BOND'), (dialog.node_set, 'MOVING'), (dialog.component, 'X')]:
            combo.setCurrentIndex(combo.findData(value))
        edit(app, dialog, 0, 0, '0'); edit(app, dialog, 0, 1, '0')
        edit(app, dialog, 1, 0, '0.001'); edit(app, dialog, 1, 1, '0.004')
        assert dialog.check()
        baseline = dialog.draft
        QTest.mouseClick(dialog.add_point, Qt.MouseButton.LeftButton); app.processEvents()
        assert dialog.table.rowCount() == 3 and not dialog.check()
        dialog.table.setFocus()
        QTest.keyClick(dialog.table, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier); app.processEvents()
        assert dialog.draft == baseline
        dialog.redo_action.trigger(); app.processEvents()
        assert dialog.table.rowCount() == 3
        QTest.mouseClick(dialog.remove_point, Qt.MouseButton.LeftButton); app.processEvents()
        # Selection is not implicitly invented after Undo/Redo: explicitly choose the blank row.
        if dialog.table.rowCount() == 3:
            dialog.table.selectRow(2); QTest.mouseClick(dialog.remove_point, Qt.MouseButton.LeftButton)
        assert dialog.table.rowCount() == 2 and dialog.check()
        dialog.undo_action.trigger(); dialog.undo_action.trigger()
        assert original == before
    finally:
        dialog.close(); dialog.deleteLater(); app.processEvents()


def test_invalid_original_values_remain_repairable(app):
    original = settings(); row = original['interface_histories'][0]
    row['component'] = 'BAD_AXIS'; row['node_set'] = 'MISSING'; row['time_s'][2] = 'unfinished'
    before = deepcopy(original); dialog = InterfaceHistoryDialog(original)
    try:
        dialog.show(); app.processEvents()
        assert dialog.draft == before
        assert dialog.component.currentData() == 'BAD_AXIS'
        assert not dialog.check()
        dialog.component.setCurrentIndex(dialog.component.findData('Z'))
        dialog.node_set.setCurrentIndex(dialog.node_set.findData('MOVING'))
        edit(app, dialog, 2, 0, '0.0005')
        assert dialog.check()
        assert original == before
        QTest.mouseClick(dialog.remove_history, Qt.MouseButton.LeftButton)
        assert dialog.check() and dialog.draft['interface_histories'] == []
        dialog.undo_action.trigger(); assert dialog.check()
    finally:
        dialog.close(); dialog.deleteLater(); app.processEvents()


def test_invalid_second_history_is_selected_without_changing_values(app):
    original = settings()
    second = deepcopy(original['interface_histories'][0]); second.update(name='shear', component='X')
    second['time_s'][2] = 'unfinished'
    original['interface_histories'].append(second)
    before = deepcopy(original); dialog = InterfaceHistoryDialog(original)
    try:
        dialog.show(); app.processEvents()
        assert dialog.histories.currentRow() == 0
        assert not dialog.check()
        assert dialog.histories.currentRow() == 1 and '이력 2' in dialog.status.text()
        assert dialog.draft == before and original == before
        edit(app, dialog, 2, 0, '0.0005')
        assert dialog.check()
        dialog.accept(); assert dialog.result() == QDialog.DialogCode.Accepted
        assert original == before
    finally:
        dialog.close(); dialog.deleteLater(); app.processEvents()


def test_accept_commits_active_table_editor_before_admission(app):
    original = settings(); before = deepcopy(original); dialog = InterfaceHistoryDialog(original)
    try:
        dialog.show(); app.processEvents()
        dialog.table.setCurrentCell(2, 0); dialog.table.setFocus()
        QTest.keyClick(dialog.table, Qt.Key.Key_F2); app.processEvents()
        editor = app.focusWidget(); assert isinstance(editor, QLineEdit)
        QTest.keyClick(editor, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
        QTest.keyClicks(editor, '0.00025')
        # No Tab/Enter: accepting must flush this delegate, then reject invalid time.
        dialog.accept(); app.processEvents()
        assert dialog.result() != QDialog.DialogCode.Accepted
        assert dialog.draft['interface_histories'][0]['time_s'][2] == .00025
        assert '엄격히 증가' in dialog.status.text() and original == before
    finally:
        dialog.close(); dialog.deleteLater(); app.processEvents()


def _declared_settings():
    from interface_history_fixtures import declared_settings
    return declared_settings('normal')


def _modal_click(app, button, callback):
    """Enter the actual button/exec route, collect Qt timer failures for pytest."""
    errors = []; seen = []
    def act():
        modal = app.activeModalWidget()
        try:
            assert isinstance(modal, InterfaceHistoryDialog)
            seen.append(modal)
            callback(modal)
        except BaseException as error:
            errors.append(error)
            if isinstance(modal, QDialog):
                modal.reject()
    QTimer.singleShot(0, act)
    QTest.mouseClick(button, Qt.MouseButton.LeftButton); app.processEvents()
    if errors:
        raise errors[0]
    assert len(seen) == 1


def test_bulk_page_actual_history_cancel_accept_and_return(app, tmp_path, monkeypatch):
    from apps.research.impact_editor import ImpactEditor
    from caelab import impact_reference_bindings as bindings
    from caelab.workbench_client import Client
    calls = []
    def no_core(*args, **kwargs):
        calls.append((args, kwargs)); raise AssertionError('Core command forbidden in local editor')
    monkeypatch.setattr(Client, 'document_command', no_core)
    original = _declared_settings(); before = deepcopy(original)
    editor = ImpactEditor(original)
    try:
        editor.show(); editor.tabs.setCurrentWidget(editor.bulk_page)
        editor.bulk_page.tabs.setCurrentIndex(1); app.processEvents()
        button = editor.bulk_page.history_button
        assert button.isEnabled() and button.text() == '변위 이력…'
        baseline = editor.edited()
        def cancel(dialog):
            edit(app, dialog, 1, 1, '0.009')
            QTest.mouseClick(dialog.buttons.button(QDialogButtonBox.StandardButton.Cancel), Qt.MouseButton.LeftButton)
        _modal_click(app, button, cancel)
        assert editor.edited() == baseline
        def accept(dialog):
            assert dialog.draft == baseline
            edit(app, dialog, 1, 1, '0.009')
            for width, height, filename in [(980, 740, 'integrated-history-normal.png'), (740, 650, 'integrated-history-narrow.png')]:
                dialog.resize(width, height); app.processEvents()
                assert dialog.grab().save(str(tmp_path / filename))
            QTest.mouseClick(dialog.buttons.button(QDialogButtonBox.StandardButton.Ok), Qt.MouseButton.LeftButton)
        _modal_click(app, button, accept)
        changed = editor.edited()
        assert changed['interface_histories'][0]['displacement_mm'][1] == .009
        assert changed[bindings.KEY] == bindings.snapshot(changed)
        assert changed['source'] == baseline['source'] and changed['cohesive'] == baseline['cohesive']
        assert original == before and not calls
        assert editor.tabs.currentWidget() is editor.bulk_page
        assert editor.bulk_page.tabs.currentIndex() == 1
        assert '계산은 실행하지 않았습니다' in editor.bulk_page.status.text()
        for width, height, filename in [(1060, 700, 'bulk-return-normal.png'), (800, 600, 'bulk-return-narrow.png')]:
            editor.resize(width, height); app.processEvents()
            assert editor.grab().save(str(tmp_path / filename))
        (tmp_path / 'integration.json').write_text(json.dumps({'qt_platform': app.platformName(),
            'source_and_material_unchanged': True, 'cancel_preserved': True,
            'same_bulk_tab_returned': True, 'bindings_exact': True, 'core_commands': len(calls), 'solver_runs': 0}, indent=2), encoding='utf-8')
    finally:
        editor.close(); editor.deleteLater(); app.processEvents()


def test_bulk_history_stale_binding_blocks_dialog_and_new_ack(app, monkeypatch, tmp_path):
    from apps.research.impact_editor import ImpactEditor
    from caelab import impact_reference_bindings as bindings
    original = _declared_settings(); original[bindings.KEY] = bindings.snapshot(original)
    original['source']['text'] = original['source']['text'].replace('*NSET,NSET=MOVING\n9,10,11,12,13,14,15,16', '*NSET,NSET=MOVING\n9,10,11,12,13,14,15')
    before = deepcopy(original)
    opened = []
    def forbidden(*args):
        opened.append(True); raise AssertionError('stale binding must block before history dialog')
    monkeypatch.setattr(InterfaceHistoryDialog, 'exec', forbidden)
    editor = ImpactEditor(original)
    try:
        editor.show(); editor.tabs.setCurrentWidget(editor.bulk_page); app.processEvents()
        assert editor.bulk_page.history_button.isEnabled()
        baseline = editor.edited()
        QTest.mouseClick(editor.bulk_page.history_button, Qt.MouseButton.LeftButton); app.processEvents()
        assert not opened and '원 대상 대응이 바뀌었습니다' in editor.bulk_page.status.text()
        assert editor.edited() == baseline and original == before
        assert editor.edited()[bindings.KEY] == original[bindings.KEY]
        editor.resize(800, 600); app.processEvents()
        assert editor.grab().save(str(tmp_path / 'history-binding-blocked-narrow.png'))
    finally:
        editor.close(); editor.deleteLater(); app.processEvents()


def test_history_reference_review_actual_targets_and_explicit_ack(app, tmp_path):
    from apps.research.impact_source_editor import ReferenceReviewDialog
    from caelab import impact_reference_bindings as bindings
    original = _declared_settings(); original['responses'] = []
    original[bindings.KEY] = bindings.snapshot(original)
    original['source']['text'] = original['source']['text'].replace('2,5,6,7,8,9,10,11,12', '4,5,6,7,8,9,10,11,12').replace('*NSET,NSET=MOVING\n9,10,11,12,13,14,15,16', '*NSET,NSET=MOVING\n9,10,11,12,13,14,15')
    before = deepcopy(original); dialog = ReferenceReviewDialog(original)
    try:
        dialog.show(); app.processEvents()
        rows = [(selection, combo) for selection, combo in dialog.choices if selection[0] == 'interface_histories']
        assert len(rows) == 2
        assert {tuple(selection) for selection, _ in rows} == {('interface_histories', 0, 'node_set'), ('interface_histories', 0, 'material')}
        dialog.show_review(); assert not dialog.confirm.isEnabled()
        for selection, combo in dialog.choices:
            if combo.currentIndex() < 0:
                combo.setCurrentIndex(combo.findData(original[selection[0]][selection[1]][selection[2]]))
        dialog.show_review(); app.processEvents()
        assert dialog.confirm.isEnabled()
        text = dialog.details.toPlainText()
        assert '기존 원 대상 전체 구성원' in text and '현재 원 대상 전체 구성원' in text
        assert '원 번호 2' in text and '원 번호 4' in text and '원 번호 16' in text
        for width, height, filename in [(940, 540, 'history-reference-normal.png'), (800, 540, 'history-reference-narrow.png')]:
            dialog.resize(width, height); app.processEvents()
            assert dialog.grab().save(str(tmp_path / filename))
        dialog.details.verticalScrollBar().setValue(dialog.details.verticalScrollBar().maximum())
        app.processEvents()
        assert dialog.grab().save(str(tmp_path / 'history-reference-current-narrow.png'))
        dialog.apply(); assert dialog.result() == QDialog.DialogCode.Accepted
        assert dialog.applied[bindings.KEY] == bindings.snapshot(dialog.applied)
        assert original == before
    finally:
        dialog.close(); dialog.deleteLater(); app.processEvents()
