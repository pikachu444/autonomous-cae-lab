"""Actual Qt owner/editor and explicitly controlled result display fixtures."""
from copy import deepcopy
import pytest
pytest.importorskip('PySide6')
from test_research_pde_ui import app, window, edit, settle
from apps.research.pde_window import typed_value


@pytest.mark.parametrize('dimensions', [(1440, 900), (1100, 780)])
def test_model_property_graph_and_collapsed_details_keep_draft(window, app, dimensions):
    window.resize(*dimensions)
    app.processEvents()
    original = deepcopy(window.edited_draft())
    assert (window.width(), window.height()) == dimensions
    assert window.messages.isHidden() and window.point_controls.isHidden() and window.history_controls.isHidden()
    assert window.domain_canvas.height() > window.centralWidget().height() * .6
    assert window.document['id'] not in window.identity.text()
    assert window.document['id'] in window.identity.toolTip()
    assert '1 (무차원)' in window.space.text()
    window.details_action.setChecked(True)
    app.processEvents()
    assert window.messages.isVisible()
    window.details_button.click()
    assert window.messages.isHidden() and window.edited_draft() == original
    assert not any(op == 'pde.evaluate' for op, _ in window.client.calls)


def test_invalid_expression_visible_with_details_closed_and_repair_preserves_other_fields(window, app):
    original = deepcopy(window.edited_draft())
    window.tree.setCurrentItem(window._nodes[('settings', 'problem', 'weak_form')])
    edit(window, ('settings', 'problem', 'weak_form', 'rhs'), 'sin(')
    window.validate_inputs()
    settle(app, window)
    assert window.issue_summary.isVisible() and window.issue_summary.text()
    assert window.messages.isHidden() and window.local_dirty
    window.tree.setCurrentItem(window._nodes[('settings', 'problem', 'boundaries', 'xmin')])
    assert window.edited_draft()['settings']['problem']['weak_form']['rhs'] == 'sin('
    window.tree.setCurrentItem(window._nodes[('settings', 'problem', 'weak_form')])
    edit(window, ('settings', 'problem', 'weak_form', 'rhs'), original['settings']['problem']['weak_form']['rhs'])
    window.validate_inputs()
    settle(app, window)
    assert window.issue_summary.isHidden() and window.edited_draft() == original
    assert typed_value('', None, ('settings', 'problem', 'reference')) is None


def test_field_selection_and_exact_navigation_survive_details_and_graph_tabs(window, app):
    opened = []
    window.runner_open = lambda job: opened.append(('runner', job))
    window.result_open = lambda *args, **kwargs: opened.append(('post', args, kwargs))
    window._selected_job = 'Jretained'
    result = {'execution_status': 'SUCCEEDED', 'responses': {}, 'diagnostics': {'native_fields': [
        {'name': 'Display fixture', 'study_index': 2, 'field': {'node_ids': [0, 900],
         'coordinates': [[0, 0], [1, 0]], 'values': [1., 2.], 'coordinates_unit': '1', 'field_unit': '1'},
         'source': {'artifact': 'retained.json', 'sha256': 'a' * 64}}]}}
    window._accept_result(result)
    window.document['runs'] = [{'job_id': 'Jretained', 'is_current_input': True}]
    window.field_node.setCurrentIndex(window.field_node.findData(900))
    app.processEvents()
    assert window.point_controls.isVisible() and window.point_label.isVisible()
    assert not window.history_controls.isVisible()
    original_draft = deepcopy(window.edited_draft())
    window.graph_tabs.setCurrentIndex(0)
    app.processEvents()
    assert window.point_controls.isHidden() and window.result_selector.isHidden()
    window.details_action.setChecked(True)
    window.graph_tabs.setCurrentIndex(1)
    window.details_action.setChecked(False)
    window.resize(1100, 780)
    app.processEvents()
    assert window.field_node.currentData() == 900 and window._selected_job == 'Jretained'
    assert window._result == result and window.edited_draft() == original_draft
    window.tree.setCurrentItem(window._nodes[('settings', 'problem', 'weak_form')])
    edit(window, ('settings', 'problem', 'weak_form', 'diffusion'), '2')
    assert '편집 전 입력' in window.result_label.text()
    assert window._selected_job == 'Jretained' and window._result == result
    window.open_runner()
    window.open_post()
    assert opened == [('runner', 'Jretained'), ('post', (window.document['id'], 'Jretained'), {'study_index': 2})]
    assert 'a'*64 in window.point_label.toolTip() and 'a'*64 not in window.point_label.text()
    window._accept_result({'execution_status': 'FAILED', 'failure': 'Explicit display fixture: boundary solve failed',
                           'responses': {}, 'diagnostics': {}})
    assert window.issue_summary.isVisible() and 'boundary solve failed' in window.issue_summary.text()
    assert window.messages.isHidden()
