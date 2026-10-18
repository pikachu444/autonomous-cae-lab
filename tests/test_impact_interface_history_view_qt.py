"""Retained real interface audits rendered through Qt, with read-only gap checks."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import hashlib
import json
import math

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialogButtonBox

from apps.research.appearance import apply_appearance
from apps.research.impact_interface_history_view import InterfaceHistoryView

ROOT = Path(__file__).resolve().parents[1]
JOBS = {'normal': 'Ja811346664c34be8a539a14d308ea77b', 'mixed': 'Je7acb3438a524b73a37ddafb7ae037a4'}


def retained(case):
    path = ROOT / 'runs/interface-history-20261018/native-01' / case / 'store/workbench/results' / JOBS[case] / 'calculation/interface_history_observations.json'
    return path, json.loads(path.read_text(encoding='utf-8'))


@pytest.fixture(scope='module')
def app():
    app = QApplication.instance() or QApplication([])
    apply_appearance(app)
    return app


@pytest.mark.parametrize('case,count', [('normal', 160), ('mixed', 161)])
def test_actual_retained_audit_table_curve_selection_close(app, tmp_path, monkeypatch, case, count):
    from caelab.workbench_client import Client
    calls = []
    def forbidden(*args, **kwargs):
        calls.append(True); raise AssertionError('Retained view must not create a Core client')
    monkeypatch.setattr(Client, '__init__', forbidden)
    path, audit = retained(case); original = deepcopy(audit)
    pin = hashlib.sha256(path.read_bytes()).hexdigest()
    view = InterfaceHistoryView(audit)
    try:
        view.show(); app.processEvents()
        assert view.table.rowCount() == count
        assert '공학 적합성: 미확인' in view.qualification.text()
        assert '구성법칙 수치 기준: 미확인' in view.qualification.text()
        assert '할선 강성(secant)은 접선 강성이 아닙니다' in view.note.text()
        assert view.declared.rowCount() == (1 if case == 'normal' else 2)
        view.table.setCurrentCell(40, 0); view.table.setFocus()
        QTest.keyClick(view.table, Qt.Key.Key_Down); app.processEvents()
        assert view._row == 41 and view.table.currentRow() == 41
        assert view.table.hasFocus()
        sample = audit['elements'][0]['samples'][41]
        assert view.raw.toPlainText().find(sample['file']) >= 0
        for width, height, filename in [(1120, 850, case + '-observations-normal.png'), (800, 760, case + '-observations-narrow.png')]:
            view.resize(width, height); app.processEvents()
            assert view.grab().save(str(tmp_path / filename))
        view.component.setCurrentIndex(view.component.findData('tangent1')); app.processEvents()
        assert view.table.currentRow() == 41
        assert view.table.item(41, 2).text() == format(sample['paired_change_mm']['tangent1'], '.8g')
        view.plot_kind.setCurrentIndex(view.plot_kind.findData('damage')); app.processEvents()
        assert list(view._curve.get_ydata()) == [s['native_mean_damage'] for s in audit['elements'][0]['samples']]
        view._picked(SimpleNamespace(artist=view._curve, ind=[55])); app.processEvents()
        assert view.table.currentRow() == 55
        view.tabs.setCurrentWidget(view.values); app.processEvents()
        assert view.grab().save(str(tmp_path / (case + '-selected-sample-narrow.png')))
        assert not calls and audit == original and hashlib.sha256(path.read_bytes()).hexdigest() == pin
        QTest.mouseClick(view.close_buttons.button(QDialogButtonBox.StandardButton.Close), Qt.MouseButton.LeftButton)
        assert not view.isVisible()
        (tmp_path / 'receipt.json').write_text(json.dumps({'qt_platform': app.platformName(), 'case': case,
            'sample_count': count, 'source_file': path.relative_to(ROOT).as_posix(), 'source_sha256': pin,
            'audit_unchanged': audit == original, 'core_clients': len(calls), 'solver_runs': 0,
            'selected_row': 55, 'closed': not view.isVisible()}, indent=2), encoding='utf-8')
    finally:
        view.close(); view.deleteLater(); app.processEvents()


def test_missing_invalid_samples_are_gaps_and_unknown_not_zero(app, tmp_path):
    _, audit = retained('mixed'); element = audit['elements'][0]
    element['samples'] = element['samples'][:8]
    missing = element['samples'].pop(4)
    audit['unavailable_frames'] = [{'frame_index': 4, 'time_s': missing['time_s'], 'reason': '원 프레임 읽기 불가'}]
    element['sampled_damage_nondecrease'] = 'UNKNOWN'
    element['sampled_initial_basis_compressive_sign'] = 'UNKNOWN'
    element['samples'][2]['native_mean_damage'] = None
    element['samples'][2]['derived_initial_basis_traction_mpa']['normal'] = None
    element['samples'][2]['reasons'] = ['원 손상·traction 값 미보고']
    element['samples'][5]['active'] = 0
    element['samples'][5]['adjacent_bulk_activity']['1'] = []
    original = deepcopy(audit); view = InterfaceHistoryView(audit)
    try:
        view.show(); app.processEvents()
        assert '누락 1개' in view.summary.text() and '손상 비감소: 미확인' in view.summary.text()
        assert view.missing.rowCount() == 1 and '읽기 불가' in view.missing.item(0, 1).text()
        assert view.table.item(2, 1).text() == '기록 없음' and view.table.item(2, 3).text() == '기록 없음'
        assert view.table.item(5, 5).text() == '비활성' and '미확인' in view.table.item(5, 6).text()
        assert '미보고' in view.table.item(2, 7).text()
        assert view.table.item(0, 4).text() == '미정의 (변위 변화 0)'
        assert None in view._curve_rows
        assert math.isnan(view._curve.get_ydata()[view._curve_rows.index(2)])
        assert math.isnan(view._curve.get_xdata()[view._curve_rows.index(None)])
        view.plot_kind.setCurrentIndex(view.plot_kind.findData('secant')); app.processEvents()
        assert math.isnan(view._curve.get_ydata()[0])  # raw secant None at zero opening
        view.tabs.setCurrentWidget(view.missing); view.resize(800, 760); app.processEvents()
        assert view.grab().save(str(tmp_path / 'missing-frames-narrow.png'))
        assert audit == original
    finally:
        view.close(); view.deleteLater(); app.processEvents()


def test_unknown_missing_clock_keeps_points_without_joining_and_failure_visible(app):
    _, audit = retained('normal'); element = audit['elements'][0]
    element['samples'] = element['samples'][:4]
    element['sampled_damage_nondecrease'] = 'VIOLATED'
    element['sampled_initial_basis_compressive_sign'] = 'SIGN_MISMATCH'
    audit['unavailable_frames'] = [{'time_s': None, 'reason': '원 시각도 미확인'}]
    before = deepcopy(audit); view = InterfaceHistoryView(audit)
    try:
        view.show(); app.processEvents()
        assert '위반 관측' in view.summary.text() and '부호 불일치' in view.summary.text()
        assert view.missing.item(0, 0).text() == '기록 없음'
        assert view._curve_rows == [0, None, 1, None, 2, None, 3]
        assert audit == before
    finally:
        view.close(); view.deleteLater(); app.processEvents()


def test_empty_audit_opens_with_unknown_and_no_fabricated_samples(app):
    view = InterfaceHistoryView({})
    try:
        view.show(); app.processEvents()
        assert view.table.rowCount() == 0 and not list(view._curve.get_xdata())
        assert '미확인' in view.qualification.text()
        assert any('원값이 없습니다' in text.get_text() for text in view.figure.axes[0].texts)
        QTest.keyClick(view, Qt.Key.Key_Escape); assert not view.isVisible()
    finally:
        view.close(); view.deleteLater(); app.processEvents()


def test_narrow715_axis_captions_fit_without_changing_retained_values(app, tmp_path):
    _, audit = retained('mixed'); before = deepcopy(audit)
    view = InterfaceHistoryView(audit)
    try:
        view.show(); view.resize(800, 715); app.processEvents()
        view.table.setCurrentCell(11, 0)
        for index in range(view.plot_kind.count()):
            view.plot_kind.setCurrentIndex(index); app.processEvents(); view.canvas.draw()
            axes = view.figure.axes[0]
            bbox = axes.yaxis.label.get_window_extent(view.canvas.get_renderer())
            width, height = view.canvas.get_width_height()
            assert bbox.x0 >= -1 and bbox.x1 <= width + 1
            assert bbox.y0 >= -1 and bbox.y1 <= height + 1
            assert view.table.currentRow() == 11
            assert len(view._curve.get_xdata()) == 161
            assert view.grab().save(str(tmp_path / (view.plot_kind.currentData() + '-715.png')))
        view.component.setCurrentIndex(view.component.findData('tangent1'))
        view.plot_kind.setCurrentIndex(view.plot_kind.findData('traction_opening'))
        expected = [sample['derived_initial_basis_traction_mpa']['tangent1'] for sample in audit['elements'][0]['samples']]
        for height in (700, 715):
            view.resize(801, height); app.processEvents(); view.canvas.draw()
            axes = view.figure.axes[0]
            labels = [item.get_text() for item in axes.get_yticklabels()]
            assert any('e-' in label for label in labels)
            assert list(view._curve.get_ydata()) == expected
            assert not axes.yaxis.get_offset_text().get_text()
            assert view.table.currentRow() == 11
            box = axes.yaxis.label.get_window_extent(view.canvas.get_renderer())
            assert box.y0 >= -1 and box.y1 <= view.canvas.get_width_height()[1] + 1
            assert 'MPa' in axes.get_ylabel()
            assert view.grab().save(str(tmp_path / ('tangent1-traction-small-' + str(height) + '.png')))
        assert audit == before
    finally:
        view.close(); view.deleteLater(); app.processEvents()
