"""Synthetic observer output rendered through Qt; no native solver claim."""
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

def retained(case, tmp_path):
    from interface_history_fixtures import declared_settings
    from test_impact_damage import frames
    from caelab.impact_interface_history import observe
    from caelab.impact_b import model_identity
    from caelab.storage import canonical_hash
    settings = declared_settings(case)
    model, original, cohesive = frames(tmp_path)
    count = 160 if case == 'normal' else 161
    samples = []
    for i in range(count):
        raw = deepcopy(original[0][1]); raw['time'] = i * 2.5e-5
        for xyz, node in zip(raw['points'], raw['POINTS']['NODE_ID']['values']):
            if node >= 9:
                xyz[2] += i * 1e-5
                xyz[0] += i * 1e-6
        raw['CELLS']['3DELEM_Damage']['values'][1] = i / (2 * count)
        stress = raw['CELLS']['3DELEM_Stress']['values']
        stress[17] = i * .01
        stress[11] = stress[15] = i * 1e-10
        source = tmp_path / f'synthetic-array-{i}.json'
        source.write_text(json.dumps(raw), encoding='utf-8')
        samples.append((source, raw))
    histories = settings['interface_histories']
    audit = observe(samples, model, settings, cohesive, {
        'model_identity': model_identity(model), 'definition_sha256': canonical_hash(histories),
        'histories': deepcopy(histories)})
    path = tmp_path / 'synthetic-observations.json'
    path.write_text(json.dumps(audit), encoding='utf-8')
    return path, audit


@pytest.fixture(scope='module')
def app():
    app = QApplication.instance() or QApplication([])
    apply_appearance(app)
    return app


@pytest.mark.parametrize('case,count', [('normal', 160), ('mixed', 161)])
def test_observer_audit_table_curve_selection_close(app, tmp_path, monkeypatch, case, count):
    from caelab.workbench_client import Client
    calls = []
    def forbidden(*args, **kwargs):
        calls.append(True); raise AssertionError('Retained view must not create a Core client')
    monkeypatch.setattr(Client, '__init__', forbidden)
    path, audit = retained(case, tmp_path); original = deepcopy(audit)
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
    finally:
        view.close(); view.deleteLater(); app.processEvents()


def test_missing_invalid_samples_are_gaps_and_unknown_not_zero(app, tmp_path):
    _, audit = retained('mixed', tmp_path); element = audit['elements'][0]
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


def test_unknown_missing_clock_keeps_points_without_joining_and_failure_visible(app, tmp_path):
    _, audit = retained('normal', tmp_path); element = audit['elements'][0]
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
    _, audit = retained('mixed', tmp_path); before = deepcopy(audit)
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
