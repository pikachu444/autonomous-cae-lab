"""Real Qt editor/owner, retained display fixtures; no evaluator or provider run."""
from copy import deepcopy
import pytest
pytest.importorskip('PySide6')
from PySide6.QtCore import Qt
from apps.research.appearance import apply_appearance
from apps.research.request_plan_window import RequestPlanWindow
from test_research_request_plan_ui import app, workbench, edit_windows, opened, find_input, wait


@pytest.mark.parametrize('dimensions', [(1440, 900), (1100, 780)])
def test_advanced_inputs_do_not_enlarge_window_and_optional_source_stays_outside(app, workbench, edit_windows, dimensions):
    apply_appearance(app)
    window = opened(app, workbench)
    window.show()
    window.resize(*dimensions)
    app.processEvents()
    original = deepcopy(window.edited_draft())
    assert (window.width(), window.height()) == dimensions
    assert window.minimumSizeHint().height() < 780
    assert window.input_tabs.currentWidget() is window.advanced_scroll
    assert window.candidate_results_button.isHidden() and window.pde_adopt_button.isHidden()
    assert window.candidates.isHidden()
    assert not window.source.isVisible() and not window.source_context.isVisible()
    assert window.figure.axes[0].texts[0].get_text() == 'No calculated result selected.'
    window.show_source_details()
    app.processEvents()
    assert window.source_dialog.isVisible() and window.source.isReadOnly()
    window.source_dialog.hide()
    assert window.edited_draft() == original and not workbench.manager.list()


def test_collapse_resize_and_advanced_scroll_preserve_live_edit_and_method_buffers(app, workbench, edit_windows):
    window = opened(app, workbench)
    window.show()
    window.resize(1100, 780)
    app.processEvents()
    find_input(window, ('settings', 'parameters', 'E')).setText(1, '1e')
    original = deepcopy(window.edited_draft())
    window.input_panel_action.setChecked(False)
    app.processEvents()
    assert window.editor.isHidden() and window.tabs.width() > 900
    assert window.input_panel_action.text() == '입력 펼치기'
    window.resize(1440, 900)
    window.input_panel_action.setChecked(True)
    app.processEvents()
    assert window.edited_draft() == original
    assert window.input_panel_action.text() == '입력 접기'
    window.operation.setCurrentIndex(window.operation.findData('analyze'))
    window.resize(1100, 780)
    app.processEvents()
    assert window.advanced_scroll.verticalScrollBar().maximum() > 0
    window.operation.setCurrentIndex(window.operation.findData('evaluate'))
    assert window.edited_draft()['request'] == original['request']
    assert window.edited_draft()['method_inputs']['analyze'] == {'result_refs': {}, 'responses': []}
    assert not workbench.manager.list()
    window.operation.setCurrentIndex(window.operation.findData('doe'))
    app.processEvents()
    assert not window.candidate_results_button.isHidden() and not window.pde_adopt_button.isHidden()
    assert not window.candidate_results_button.isEnabled() and not window.pde_adopt_button.isEnabled()


def test_human_run_labels_keep_exact_selection_and_actual_response_values(app, workbench, edit_windows):
    window = opened(app, workbench)
    window.show()
    displayed = deepcopy(window.document)
    displayed['runs'] = [{'job_id': 'Jretained', 'input_generation': 3, 'input_revision': 'Iexact',
        'is_current_input': True, 'retained_state': 'SUCCEEDED'}]
    window._show_document(displayed)
    assert window.selected_job() == 'Jretained'
    assert window.runs.item(0, 0).text() == '계산 1'
    assert window.runs.item(0, 0).data(Qt.ItemDataRole.UserRole) == 'Jretained'
    assert window.runs.item(0, 1).text() == '완료'
    actual = {'responses': {'stress': {'kind': 'series', 'unit': 'MPa', 'value': [0., 17., 21.],
        'axes': [{'name': 'strain', 'unit': '1', 'values': [0., .01, .02]}], 'mask': [True, False, True]}}}
    window._result_cache['Jretained'] = deepcopy(actual)
    window._draw_result()
    app.processEvents()
    assert window.candidates.isHidden() and window.plot_response.currentData() == 'stress'
    assert window.figure.axes[0].get_ylabel() == 'stress [MPa]'
    line = window.figure.axes[0].lines[0]
    assert list(line.get_xdata()) == [0., .01, .02]
    assert line.get_ydata()[0] == 0 and line.get_ydata()[2] == 21
    import math
    assert math.isnan(line.get_ydata()[1])
    window.plot_response.setCurrentIndex(0)
    window._draw_result()
    assert window.plot_response.currentData() is None  # An unchanged read never overrides an explicit view choice.
    assert window._result_cache['Jretained'] == actual and not workbench.manager.list()
