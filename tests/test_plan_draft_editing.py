"""Plan editing contracts in real Qt widgets, without solver/provider execution."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from copy import deepcopy
from types import SimpleNamespace
import pytest
pytest.importorskip('PySide6')
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLineEdit
from apps.research.request_plan_window import RequestPlanWindow
from apps.research.numerical_window import ProtocolDialog, NumericalWindow
from caelab.numerical_document import request_draft, from_material_document
from caelab.material_document import default_draft


@pytest.fixture
def windows():
    app = QApplication.instance() or QApplication([])
    draft = request_draft({'purpose': '시험 계획', 'operation': 'doe', 'budget': {'evaluations': 8},
        'inputs': {'backend': 'material', 'settings': {}, 'count': 4, 'seed': 3,
            'variables': [{'id': name, 'unit': 'MPa', 'value': 2., 'lower': 1., 'upper': 3., 'transform': 'linear'}
                          for name in ('a', 'b')]}})
    result = []
    for identifier in ('Nfirst', 'Nsecond'):
        window = RequestPlanWindow(None, auto_open=False, poll_interval=0)
        window._show_document({'id': identifier, 'session_id': 'S1', 'generation': 0,
            'title': identifier, 'draft': deepcopy(draft), 'runs': [], 'diagnostics': [],
            'dirty': False, 'can_undo': False, 'can_redo': False})
        window.show()
        QTest.qWaitForWindowExposed(window)
        result.append(window)
    app.processEvents()
    yield app, result
    for window in result:
        window._allow_close = True
        window.close()
    app.processEvents()


def clipboard_text(window, value):
    window.raise_(); window.activateWindow()
    QTest.qWait(100)
    QApplication.clipboard().setText(value)
    QTest.qWait(50)
    assert QApplication.clipboard().text() == value


def test_block_paste_is_one_local_undo_and_does_not_touch_other_plan(windows):
    app, (first, second) = windows
    before = deepcopy(first.edited_draft())
    other = deepcopy(second.edited_draft())
    first.variable_sheet.setCurrentCell(0, 2)
    clipboard_text(first, '2.123456789012345\t1e\t4\n2.5\t1.5\t5')
    assert first.variable_sheet.paste_cells()
    app.processEvents()
    edited = first.edited_draft()
    assert edited['request']['inputs']['variables'][0]['value'] == 2.123456789012345
    assert edited['request']['inputs']['variables'][0]['lower'] == '1e'
    assert edited['request']['inputs']['variables'][1]['upper'] == 5
    assert first.local_dirty and first.undo_action.isEnabled()
    assert second.edited_draft() == other and not second.local_dirty
    first.undo_action.trigger(); app.processEvents()
    assert first.edited_draft() == before and not first.local_dirty
    # An unchanged polling receipt can update run metadata without erasing Redo.
    first._show_document(deepcopy(first.document)); app.processEvents()
    assert first.redo_action.isEnabled()
    first.redo_action.trigger(); app.processEvents()
    assert first.edited_draft() == edited and first.local_dirty
    assert first.document['draft'] != edited


def test_paste_preflight_preserves_readonly_and_out_of_bounds(windows):
    app, (first, _) = windows
    before = first.edited_draft()
    first.variable_sheet.setCurrentCell(0, 0)
    clipboard_text(first, 'renamed\t22')
    assert not first.variable_sheet.paste_cells()
    assert '읽기 전용' in first.message.text()
    first.variable_sheet.setCurrentCell(1, 2)
    clipboard_text(first, '4\n5')
    assert not first.variable_sheet.paste_cells()
    assert '범위' in first.message.text()
    app.processEvents()
    assert first.edited_draft() == before and not first.local_dirty
    first.variable_sheet.setCurrentCell(0, 2)
    clipboard_text(first, '2.2\n\n')
    assert first.variable_sheet.paste_cells()
    app.processEvents()
    assert first.edited_draft()['request']['inputs']['variables'][1]['value'] == ''


def test_enter_esc_and_foreign_focus_remain_local(windows):
    app, (first, second) = windows
    first.raise_(); first.activateWindow(); QTest.qWait(100); first.variable_sheet.setFocus()
    first.variable_sheet.editItem(first.variable_sheet.item(0, 2))
    app.processEvents()
    editor = QApplication.focusWidget()
    assert isinstance(editor, QLineEdit)
    QTest.keyClick(editor, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
    QTest.keyClicks(editor, 'unfinished')
    QTest.keyClick(editor, Qt.Key.Key_Escape); app.processEvents()
    assert first.edited_draft()['request']['inputs']['variables'][0]['value'] == 2.
    first.variable_sheet.editItem(first.variable_sheet.item(0, 2)); app.processEvents()
    editor = QApplication.focusWidget()
    QTest.keyClick(editor, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
    QTest.keyClicks(editor, '2.75')
    QTest.keyClick(editor, Qt.Key.Key_Return); app.processEvents()
    assert first.edited_draft()['request']['inputs']['variables'][0]['value'] == 2.75
    second.raise_(); second.activateWindow(); QTest.qWait(100); second.variable_sheet.setFocus()
    second.variable_sheet.editItem(second.variable_sheet.item(0, 2)); app.processEvents()
    foreign = QApplication.focusWidget()
    QTest.keyClicks(foreign, '1e')
    first.edited_draft()
    dialog = ProtocolDialog(default_draft()['settings'], first)
    dialog.draft_settings()
    assert QApplication.focusWidget() is foreign
    QTest.keyClick(foreign, Qt.Key.Key_Escape)
    dialog.close()


def test_committed_edit_undo_is_local_then_owner_fallback(windows):
    app, (first, second) = windows
    before = first.edited_draft()
    first.variable_sheet.item(0, 3).setText('1e')
    app.processEvents()
    first.undo_action.trigger(); app.processEvents()
    assert first.edited_draft() == before and not first.local_dirty
    first.redo_action.trigger(); app.processEvents()
    assert first.edited_draft()['request']['inputs']['variables'][0]['lower'] == '1e'
    assert not second.local_dirty
    first.undo_action.trigger(); app.processEvents()
    calls = []
    first.command = lambda operation: calls.append(operation)
    first.undo_inputs()
    assert calls == ['document.undo']


def test_three_objective_axes_keep_actual_candidate_identity(windows):
    app, (first, _) = windows
    definitions = [{'response': name, 'unit': unit, 'direction': direction, 'scale': 1.,
                    'reduction': 'none', 'component': 'scalar', 'location': 'model'}
                   for name, unit, direction in [('mass', 'kg', 'minimize'),
                                                 ('stress', 'MPa', 'minimize'),
                                                 ('stiffness', 'N/m', 'maximize')]]
    document = deepcopy(first.document)
    document['draft']['request']['operation'] = 'epsilon'
    document['draft']['request']['inputs']['objectives'] = definitions
    document['runs'] = [{'job_id': 'Jpareto', 'input_generation': 0, 'input_revision': 'I1',
                         'draft': deepcopy(document['draft']), 'is_current_input': True}]
    result = {'kind': 'epsilon_optimization', 'execution_status': 'SUCCEEDED',
              'pareto': {'nondominated_ids': ['C1']}, 'children': [], 'candidates': []}
    for identifier, values, feasible in [('C1', (2., 12., 100.), True), ('C2', (3., 15., 90.), False)]:
        result['candidates'].append({'candidate_id': identifier, 'execution_status': 'SUCCEEDED',
            'values': {'a': 2.}, 'feasible': feasible, 'responses': {
                definition['response']: {'kind': 'scalar', 'value': value,
                    'unit': definition['unit'], 'component': 'scalar', 'location': 'model'}
                for definition, value in zip(definitions, values)}})
    first._result_cache['Jpareto'] = result
    first._show_document(document)
    first.candidates.selectRow(0); app.processEvents()
    first.pareto_y.setCurrentIndex(2); app.processEvents()
    assert not first.pareto_y.isHidden()
    assert first.figure.axes[0].get_ylabel().endswith('[N/m] 최대화')
    artist = next(artist for artist in first.figure.axes[0].collections
                  if getattr(artist, '_candidate_ids', []) == ['C2'])
    assert list(artist.get_offsets()[0]) == [3., 90.]
    first._candidate_plot_picked(SimpleNamespace(artist=artist, ind=[0])); app.processEvents()
    assert first.candidates.item(first.candidates.currentRow(), 0).text() == 'C2'
    first._draw_result(); app.processEvents()
    assert first.pareto_y.currentData() == 2
    assert first.candidates.item(first.candidates.currentRow(), 0).text() == 'C2'
    assert first.document['draft'] == document['draft'] and not first.local_dirty


def test_material_picker_preserves_service_baseline_for_local_undo(windows):
    app, _ = windows
    material = {'id': 'Mfirst', 'generation': 0, 'input_revision': 'I1', 'draft': default_draft()}
    draft = from_material_document(material)
    window = NumericalWindow(None, auto_open=False, poll_interval=0)
    try:
        document = {'id': 'Nfit', 'session_id': 'S1', 'generation': 0, 'title': '피팅',
                    'draft': draft, 'diagnostics': [], 'runs': [], 'dirty': False}
        window._show_document(document)
        replacement = deepcopy(material)
        replacement['id'] = 'Msecond'
        replacement['draft']['settings']['parameters']['E'] = 2200.
        window._list_select = lambda kind, chosen: chosen(replacement)
        window.choose_material(); app.processEvents()
        assert window.document['draft'] == draft
        assert window.edited_draft()['material']['document_id'] == 'Msecond'
        window.undo_action.trigger(); app.processEvents()
        assert window.edited_draft() == draft and not window.local_dirty
        window.redo_action.trigger(); app.processEvents()
        assert window.edited_draft()['material']['document_id'] == 'Msecond'
    finally:
        window._allow_close = True
        window.close()
