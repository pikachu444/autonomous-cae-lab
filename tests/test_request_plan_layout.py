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
    assert window.work_pages.currentWidget() is window.plan_page
    assert window.input_tabs.currentWidget() is window.sheet
    window.input_tabs.setCurrentWidget(window.advanced_scroll)
    app.processEvents()
    assert window.advanced_scroll.isVisible()
    assert (window.width(), window.height()) == dimensions
    assert window.candidate_results_button.isHidden() and window.pde_adopt_button.isHidden()
    assert window.candidates.isHidden()
    assert not window.source.isVisible() and not window.source_context.isVisible()
    assert window.figure.axes[0].texts[0].get_text() == '아직 선택한 계산 결과가 없습니다.'
    window.show_source_details()
    app.processEvents()
    assert window.source_dialog.isVisible() and window.source.isReadOnly()
    window.source_dialog.hide()
    assert window.edited_draft() == original and not workbench.manager.list()


@pytest.mark.parametrize('dimensions', [(1440, 900), (1100, 780)])
def test_native_conditions_show_wrapped_purpose_and_freecad_instead_of_empty_tables(app, workbench, edit_windows, dimensions):
    from PySide6.QtWidgets import QPlainTextEdit
    from caelab.numerical_document import request_draft
    from test_research_request_plan_ui import InProcessClient
    purpose = '변위를 0.005 mm에서 0.006 mm로 수정합니다.\n' + '기존 재료, 하중과 구속을 유지하고 반력을 비교합니다. ' * 20
    draft = request_draft({'purpose': purpose, 'operation': 'evaluate',
        'inputs': {'backend': 'structure.calculix.frozen', 'settings': {}},
        'budget': {'evaluations': 1}}, source={'discussion_id': 'Xsource', 'turn_id': 'Aturn',
            'proposal_index': 0, 'proposal_sha256': 'a'*64, 'job_id': 'Jsource',
            'input_revision': 'Isource', 'input_sha256': 'b'*64})
    window = RequestPlanWindow(InProcessClient(workbench), auto_open=False, poll_interval=0)
    import os
    if os.name == 'nt':
        from pathlib import Path
        from PySide6.QtGui import QFont, QFontDatabase
        font_path = Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts' / 'malgun.ttf'
        if font_path.is_file() and QFontDatabase.addApplicationFont(str(font_path)) >= 0:
            window.setFont(QFont('Malgun Gothic', 10))
    window.open_document(draft=draft, title=purpose[:150])
    wait(app, lambda: window.document is not None and not window._busy)
    window.resize(*dimensions)
    window.show()
    app.processEvents()
    assert window.windowTitle() in {'계산 계획', '계산 계획 *'}
    assert isinstance(window.purpose, QPlainTextEdit) and window.purpose.text() == purpose
    assert window.purpose.lineWrapMode() == QPlainTextEdit.LineWrapMode.WidgetWidth
    assert window.purpose.horizontalScrollBar().maximum() == 0
    assert window.model_label.text() == 'CalculiX / FreeCAD FEM'
    assert not window.backend.isVisible()
    assert window.input_tabs.currentWidget() is window.native_page
    assert not any(table.isVisible() for table in (window.variable_sheet, window.response_sheet, window.method_sheet))
    assert window.native_instructions.isVisible() and 'CalculiX' in window.native_instructions.text()
    assert window.run_button.isEnabled() and window.run_button.text() == '계산 입력 준비…'
    assert window.model_open_button.text() == 'FreeCAD에서 모델 편집…'
    if os.environ.get('CAELAB_QT_CAPTURE_DIR'):
        from pathlib import Path
        folder = Path(os.environ['CAELAB_QT_CAPTURE_DIR'])
        folder.mkdir(parents=True, exist_ok=True)
        assert window.grab().save(str(folder / ('request-plan-' + str(dimensions[0]) + '.png')))
    window.input_tabs.setCurrentWidget(window.advanced_scroll)
    app.processEvents()
    assert window.backend.isVisible() and window.backend.text() == 'structure.calculix.frozen'
    assert window.edited_draft() == draft and not workbench.manager.list()


def test_page_switch_resize_and_advanced_scroll_preserve_live_edit_and_method_buffers(app, workbench, edit_windows):
    window = opened(app, workbench)
    window.show()
    window.resize(1100, 780)
    app.processEvents()
    window.input_tabs.setCurrentWidget(window.advanced_scroll)
    find_input(window, ('settings', 'parameters', 'E')).setText(1, '1e')
    original = deepcopy(window.edited_draft())
    window.work_pages.setCurrentWidget(window.results_panel)
    app.processEvents()
    assert not window.editor.isVisible() and window.tabs.isVisible()
    assert window.tabs.width() > 900
    window.resize(1440, 900)
    window.work_pages.setCurrentWidget(window.plan_page)
    app.processEvents()
    assert window.edited_draft() == original
    assert window.editor.isVisible() and window.advanced_scroll.isVisible()
    window.operation.setCurrentIndex(window.operation.findData('analyze'))
    window.resize(1100, 780)
    app.processEvents()
    assert window.advanced_scroll.verticalScrollBar().maximum() > 0
    window.operation.setCurrentIndex(window.operation.findData('evaluate'))
    assert window.edited_draft()['request'] == original['request']
    assert find_input(window, ('settings', 'parameters', 'E')).text(1) == '1e'
    assert window.edited_draft()['method_inputs']['analyze'] == {'result_refs': {}, 'responses': []}
    assert not workbench.manager.list()
    window.operation.setCurrentIndex(window.operation.findData('doe'))
    app.processEvents()
    assert not window.candidate_results_button.isHidden()
    assert window.pde_adopt_button.isHidden()  # No retained run with an original model to adopt into.
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
