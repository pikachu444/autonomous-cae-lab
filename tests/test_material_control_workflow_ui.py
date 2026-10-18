"""Scoped editor checks; no constitutive execution is requested."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from copy import deepcopy
import pytest
pytest.importorskip('PySide6')
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from apps.research.material_control_gui import MixedControlDialog, MixedControlResultDialog
from material_control_workflow_inputs import cases


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


def test_unchanged_numbers_initial_state_and_solver_remain_exact(app):
    for case in cases()[:4]:
        original = case['settings']; before = deepcopy(original)
        window = MixedControlDialog(None, original)
        try:
            assert window.draft_settings() == original
            assert set(window.controls) == {'xx', 'yy', 'zz', 'xy', 'xz', 'yz'}
            window._compile()
            assert window.result_settings == before and original == before
        finally: window.close()


def test_enabled_target_is_empty_until_explicit_zero_and_cancel_preserves(app):
    original = cases()[1]['settings']; before = deepcopy(original)
    window = MixedControlDialog(None, original)
    try:
        window.controls['yy'].setChecked(True)
        draft = window.draft_settings()
        assert draft['boundary_control']['stress_components']['yy'] == ['', '', '']
        assert not window.validate_draft()
        window.set_transverse_zero()
        assert window.draft_settings()['boundary_control']['stress_components'] == {'yy': [0., 0., 0.], 'zz': [0., 0., 0.]}
        assert not window.table.item(1, 5).flags() & Qt.ItemFlag.ItemIsEditable
        assert window.draft_settings()['deformation_gradient'] == original['deformation_gradient']
        window.reject()
        assert window.result_settings is None and original == before
    finally: window.close()


def test_incomplete_draft_save_does_not_validate_or_zero_initial_state(app):
    original = cases()[0]['settings']
    original['initial_state']['time'] = 'unfinished'
    window = MixedControlDialog(None, original)
    try:
        window.table.item(1, 1).setText('1e')
        assert not window.validate_draft()
        window._compile()
        assert window.result_settings['deformation_gradient'][1][0][0] == '1e'
        assert window.result_settings['initial_state']['time'] == 'unfinished'
    finally: window.close()


@pytest.mark.parametrize('field,column,label,diagnostic', [
    ('target', 11, 'P yy 목표 [MPa]', 'controlled yy: require finite numeric shape (3,); no text/bool'),
    ('F', 1, 'F11 [1]', 'F history: require finite numeric shape (3, 3, 3); no text/bool'),
    ('time', 0, '시간 [s]', 'time: require finite numeric shape (3,); no text/bool')])
def test_numeric_recovery_selects_exact_cell_and_keeps_producer_diagnostic(app, field, column, label, diagnostic):
    settings = deepcopy(cases()[0]['settings'])
    if field == 'target': settings['boundary_control']['stress_components']['yy'][1] = '1e'
    elif field == 'F': settings['deformation_gradient'][1][0][0] = '1e'
    else: settings['time'][1] = '1e'
    window = MixedControlDialog(None, settings)
    try:
        assert not window.validate_draft()
        assert '2행' in window.message.text() and label in window.message.text()
        if field != 'time': assert '시각 1.0 s' in window.message.text()
        assert '‘1e’' in window.message.text() and '완성된 숫자' in window.message.text()
        assert window.message.toolTip() == diagnostic
        assert (window.table.currentRow(), window.table.currentColumn()) == (1, column)
        assert window.table.item(1, column).isSelected() and not window.table.isColumnHidden(column)
        window._compile(); assert window.result_settings == settings
    finally: window.close()


def test_unrecognized_and_malformed_numeric_error_are_not_guessed(app, monkeypatch):
    from plugins.material_point import law_native
    original = deepcopy(cases()[0]['settings'])
    original['boundary_control']['stress_components']['yy'] = []
    window = MixedControlDialog(None, original)
    try:
        assert not window.validate_draft()
        assert 'controlled yy: require finite numeric shape' in window.message.text()
        def refused(_): raise ValueError('unrecognized producer diagnosis')
        monkeypatch.setattr(law_native, 'validate_settings', refused)
        assert not window.validate_draft()
        assert 'unrecognized producer diagnosis' in window.message.text()
        assert window.message.toolTip() == 'unrecognized producer diagnosis'
        window._compile(); assert window.result_settings == original
    finally: window.close()


@pytest.mark.parametrize('index,label,target', [(0, 'Pxx 목표', [0., 3., 6.]), (2, 'σxx 목표', [0., 10., 30., 5.])])
def test_trial_axial_stress_control_plots_target_not_stored_F11(app, index, label, target):
    from apps.research.material_test_dialog import ExperimentDialog
    settings = deepcopy(cases()[index]['settings'])
    settings['boundary_control']['stress_components']['xx'] = target
    before = deepcopy(settings)
    observed = {'responses': {'observed': {'kind': 'series', 'measure': 'first_Piola' if index == 0 else 'infinitesimal_Cauchy',
        'value': [0.] * len(target), 'unit': 'MPa', 'component': 'xx', 'frame': 'material_cartesian',
        'axes': [{'name': 'time', 'unit': 's', 'values': settings['time']}]}}}
    window = ExperimentDialog(settings, observed)
    try:
        axis = window.figure.axes[1]
        assert axis.get_ylabel() == label + ' [MPa]'
        assert list(axis.lines[0].get_ydata()) == target
        assert window.explicit == before and settings == before
        window.reject(); assert window.value is None
    finally: window.close()


@pytest.mark.parametrize('boundary', [None, {}, {'stress_components': {'yy': '1e'}, 'solver': None}])
def test_invalid_boundary_is_not_silently_removed_by_open_or_view_toggle(app, boundary):
    original = deepcopy(cases()[1]['settings']); original['boundary_control'] = boundary
    window = MixedControlDialog(None, original)
    try:
        window.all_f.setChecked(True)
        assert window.draft_settings() == original
        window._compile()
        assert window.result_settings == original
    finally: window.close()


def test_row_operations_keep_missing_values_and_measured_selection(app):
    window = MixedControlDialog(None, cases()[1]['settings'])
    try:
        window.mode.setCurrentIndex(window.mode.findData('measured'))
        assert window.table.currentColumn() == 5
        window.add_row()
        draft = window.draft_settings()
        assert draft['time'][-1] == '' and draft['deformation_gradient'][-1] == [[''] * 3 for _ in range(3)]
        window.table.selectRow(window.table.rowCount()-1); window.remove_row()
        assert window.draft_settings() == window.base
    finally: window.close()


def test_failed_and_initial_result_never_invent_newton_or_trial(app):
    settings = cases()[4]['settings']
    state = settings['initial_state']
    failed = dict(increment=1, time=1., error='retained original error', last_accepted_state=state)
    result = {'diagnostics': {'constitutive_increments': [], 'failed_increment': failed}}
    window = MixedControlResultDialog(result, settings)
    try:
        assert '수락되지' in window.message.text()
        assert 'retained original error' in window.message.text()
        assert window.residual.rowCount() == 0
        assert window.states.topLevelItem(0).childCount() == len(state)
        assert result['diagnostics']['failed_increment'] == failed
    finally: window.close()
