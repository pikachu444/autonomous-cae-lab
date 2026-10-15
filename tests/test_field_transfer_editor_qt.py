"""Real Qt controls over declared manufactured source metadata; no native/solver calls."""
from copy import deepcopy
import os
from pathlib import Path

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
pytest.importorskip('PySide6')
from PySide6.QtCore import QTimer, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (QApplication, QComboBox, QDialog, QDialogButtonBox,
                              QLineEdit, QListWidget, QTabWidget, QTableWidget, QLabel)
from apps.research.appearance import apply_appearance
from apps.research.post_comparison_editor import ComparisonEditor, default_recipe


@pytest.fixture(scope='module')
def app():
    application = QApplication.instance() or QApplication([])
    apply_appearance(application)
    return application


def sources():
    return [{'source_ref': ref, 'label': title, 'metadata': {
        'arrays': [{'name': 'force', 'association': 'POINTS', 'components': 3},
                   {'name': 'required', 'association': 'POINTS', 'components': 1},
                   {'name': 'quality', 'association': 'POINTS', 'components': 1},
                   {'name': 'cell_quality', 'association': 'CELLS', 'components': 1}],
        'timesteps': [0., 2.]}, 'native_metadata': {
            'coordinate_units': 'm', 'coordinate_frame': 'global',
            'arrays': [{'name': 'force', 'association': 'POINTS', 'components': 3,
                        'quantity': 'force', 'units': unit, 'measure': 'force', 'frame': frame,
                        'layout': {'kind': 'vector', 'components': ['x', 'y', 'z']}}],
            'time': {'unit': 's', 'semantics': 'physical_time'}}}
        for ref, title, unit, frame in [('A', '기준 힘', 'N', 'global'),
                                        ('B', '비교 힘', 'kN', 'rotated')]]


@pytest.fixture
def editor(app):
    widget = ComparisonEditor(default_recipe(), sources())
    for side, ref in [('a', 'A'), ('b', 'B')]:
        widget.change_source(side, ref)
        widget.change_field(side, ['force', 'POINTS'])
    yield widget
    for dialog in widget.findChildren(QDialog): dialog.reject()
    widget.close()
    app.processEvents()


def settings_fields(dialog):
    return {name: dialog.findChild(kind, name) for name, kind in [
        ('transferCoverage', QComboBox), ('transferRequiredArray', QComboBox),
        ('transferConservation', QComboBox), ('transferIntegralAbsolute', QLineEdit),
        ('transferIntegralRelative', QLineEdit)]}


def test_required_region_selects_actual_point_array_and_explicit_integral_limits(editor, monkeypatch):
    def accept(dialog):
        fields = settings_fields(dialog)
        arrays = fields['transferRequiredArray']
        assert [arrays.itemData(i) for i in range(arrays.count())] == [None, 'required', 'quality']
        assert not arrays.isEnabled()
        fields['transferCoverage'].setCurrentIndex(fields['transferCoverage'].findData('a_mask'))
        assert arrays.isEnabled()
        arrays.setCurrentIndex(arrays.findData('required'))
        fields['transferConservation'].setCurrentIndex(1)
        fields['transferIntegralAbsolute'].setText('1e-12')
        fields['transferIntegralRelative'].setText('1e-10')
        return QDialog.DialogCode.Accepted
    monkeypatch.setattr(QDialog, 'exec', accept)
    editor.settings()
    assert editor.draft()['coverage'] == {'policy': 'a_mask', 'array': 'required'}
    assert editor.draft()['conservation'] == {'mode': 'check_volume_integral',
        'absolute_tolerance': 1e-12, 'relative_tolerance': 1e-10}
    reopened = ComparisonEditor(editor.draft(), sources())
    assert reopened.draft() == editor.draft()
    reopened.close()


def test_missing_retained_mask_is_preserved_until_explicit_repair(editor, monkeypatch):
    editor.value['coverage'] = {'policy': 'a_mask', 'array': 'missing-mask'}
    def accept(dialog):
        field = settings_fields(dialog)['transferRequiredArray']
        assert field.currentData() == 'missing-mask'
        assert '미확인' in field.currentText()
        return QDialog.DialogCode.Accepted
    monkeypatch.setattr(QDialog, 'exec', accept)
    editor.settings()
    assert editor.draft()['coverage']['array'] == 'missing-mask'


def test_cancel_and_enter_cannot_apply_partial_transfer_settings(editor, app):
    original = editor.draft()
    errors = []
    def edit_and_cancel():
        dialog = QApplication.activeModalWidget()
        try:
            fields = settings_fields(dialog)
            fields['transferConservation'].setCurrentIndex(1)
            edit = fields['transferIntegralAbsolute']
            edit.setText('1e'); edit.setFocus()
            QTest.keyClick(edit, Qt.Key.Key_Return)
            assert dialog.isVisible() and editor.draft() == original
            QTest.keyClick(edit, Qt.Key.Key_Escape)
        except BaseException as error:
            errors.append(error)
        finally:
            if dialog is not None: dialog.reject()
    QTimer.singleShot(0, edit_and_cancel)
    editor.settings()
    assert not errors and editor.draft() == original


def test_validity_masks_use_actual_association_and_preserve_declared_choices(editor, monkeypatch):
    def select(dialog):
        fields = dialog.findChild(QListWidget, 'comparisonValidityMasks')
        assert [fields.item(i).data(Qt.ItemDataRole.UserRole) for i in range(fields.count())] == ['required', 'quality']
        fields.item(1).setCheckState(Qt.CheckState.Checked)
        return QDialog.DialogCode.Accepted
    monkeypatch.setattr(QDialog, 'exec', select)
    editor.meaning('b')
    assert editor.draft()['b']['validity_masks'] == ['quality']
    assert editor.draft()['b']['units'] == 'kN'
    assert editor.draft()['b']['layout']['components'] == ['x', 'y', 'z']


def test_real_settings_render_normal_and_narrow(editor, app):
    output = os.environ.get('CAE_FIELD_COMPARISON_CAPTURE_DIR')
    editor.setWindowTitle('결과 장 비교'); editor.show()
    for name, width in [('normal', 920), ('narrow', 640)]:
        editor.resize(width, 300); app.processEvents()
        if output:
            folder = Path(output); folder.mkdir(parents=True, exist_ok=True)
            assert editor.grab().save(str(folder / (name + '-editor.png')))
    errors = []
    def capture():
        dialog = QApplication.activeModalWidget()
        try:
            fields = settings_fields(dialog)
            fields['transferCoverage'].setCurrentIndex(2)
            fields['transferRequiredArray'].setCurrentIndex(1)
            fields['transferConservation'].setCurrentIndex(1)
            fields['transferIntegralAbsolute'].setText('1e-12')
            fields['transferIntegralRelative'].setText('1e-10')
            tabs = dialog.findChild(QTabWidget)
            tabs.setCurrentIndex(3)
            for name, size in [('normal', (820, 660)), ('narrow', (620, 520))]:
                dialog.resize(*size); app.processEvents()
                buttons = dialog.findChild(QDialogButtonBox)
                assert buttons.isVisible() and buttons.geometry().bottom() < dialog.height()
                if output: assert dialog.grab().save(str(Path(output) / (name + '-transfer.png')))
        except BaseException as error:
            errors.append(error)
        finally:
            if dialog is not None: dialog.reject()
    QTimer.singleShot(0, capture)
    editor.settings()
    assert not errors


def test_integral_table_reads_exact_result_units_and_marks_earlier_recipe(editor, app):
    summary = {'recipe': editor.draft(), 'field_transfer': {
        'coverage': {'required_count': 5, 'valid_count': 5},
        'conservation': {'mode': 'check_volume_integral', 'status': 'PASS',
            'integral_units': 'N * m^3', 'source_integral': [.25, .5, .75],
            'receiver_integral': [.251, .5, .75], 'absolute_error': [.001, 0., 0.],
            'limits': [.002, .002, .002]}}}
    editor.set_result_summary(summary)
    editor.value['target']['units'] = 'kN'
    editor._refresh()
    assert editor.checks_button.isEnabled() and '이전 결과' in editor.checks_button.text()
    errors = []
    def inspect():
        dialog = QApplication.activeModalWidget()
        try:
            labels = ' '.join(label.text() for label in dialog.findChildren(QLabel))
            assert '이전 결과' in labels and 'N * m^3' in labels and 'kN' not in labels
            values = dialog.findChild(QTableWidget)
            assert values.item(0, 1).text() == '0.25'
            assert values.item(0, 2).text() == '0.251'
            assert values.horizontalHeaderItem(1).text() == '원 B 적분'
            assert values.horizontalHeaderItem(2).text() == 'A 위치 B 적분'
            output = os.environ.get('CAE_FIELD_COMPARISON_CAPTURE_DIR')
            for name, size in [('normal', (820, 420)), ('narrow', (620, 360))]:
                dialog.resize(*size); app.processEvents()
                if output: assert dialog.grab().save(str(Path(output) / (name + '-integrals.png')))
        except BaseException as error:
            errors.append(error)
        finally:
            if dialog is not None: dialog.reject()
    QTimer.singleShot(0, inspect)
    editor.show_transfer_result()
    assert not errors
    assert editor.result_summary == summary
