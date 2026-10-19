"""Actual Qt layout and editing checks; controlled retained data, no solver run."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from copy import deepcopy

import pytest
pytest.importorskip('PySide6')
pytest.importorskip('matplotlib')
from PySide6.QtWidgets import QApplication

from apps.research.numerical_window import NumericalWindow
from apps.research.request_plan_window import RequestPlanWindow
from tests.test_numerical_adoption_polling import RetainedClient, wait


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def study(app):
    client = RetainedClient()
    draft = client.plan['draft']
    draft['mode'] = 'uq'
    draft['operation_options'] = {'distributions': {'E': {'kind': 'uniform', 'lower': 900., 'upper': 1100.}},
        'independence': 'independent', 'source': {'origin': 'ASSUMED', 'reference': 'Declared test input law'},
        'thresholds': []}
    # Keep an existing observation so hiding never becomes an implicit deletion.
    draft['experiments'] = [{'id': 'Eobserved', 'role': 'holdout',
        'source': {'job_id': 'Jobserved', 'response': 'stress', 'document_id': 'Tobserved'},
        'response': 'stress_xx', 'weight': 1., 'scale': 1.,
        'settings': deepcopy(client.material['draft']['settings'])}]
    client.plan['runs'][0]['draft'] = deepcopy(draft)
    client.result = {'kind': 'uq', 'execution_status': 'SUCCEEDED',
        'candidates': [{'candidate_id': 'C0001', 'execution_status': 'SUCCEEDED', 'values': {'E': 1000.}},
                       {'candidate_id': 'C0002', 'execution_status': 'FAILED', 'values': {'E': 1100.},
                        'failure_reason': 'Controlled retained failure'}],
        'probability_statistics': [{'response': 'stress_xx', 'unit': 'MPa', 'mean': 2., 'std': .2,
                                    'valid_count': 1, 'failed_count': 1}]}
    window = NumericalWindow(client, auto_open=False, poll_interval=0)
    window._show_document(client.plan)
    window._result_cache['Jretained'] = deepcopy(client.result)
    window._draw_result()
    window.show(); app.processEvents()
    yield window, client
    client.poll_release.set()
    wait(app, lambda: not window._busy)
    window._allow_close = True; window.close()


@pytest.mark.parametrize('dimensions', [(1440, 940), (1660, 1080)])
def test_uq_actual_results_have_readable_share_of_window(study, app, dimensions):
    window, _ = study
    window.resize(*dimensions); app.processEvents()
    assert window.experiments_panel.isHidden()
    assert not window.operation_options.isHidden()
    assert window.tabs.height() > window.centralWidget().height() / 4
    assert window.candidates.viewport().height() > 5 * window.candidates.rowHeight(0)
    assert window.candidates.item(1, 1).text() == '실패'
    window.tabs.setCurrentWidget(window.candidate_comparison_splitter); app.processEvents()
    assert window.canvas.height() > window.centralWidget().height() / 4
    assert window.figure.axes[0].get_title() == '유효 계산 1개 기준 / 실패 1개 제외'
    assert 'MPa' in window.figure.axes[0].get_ylabel()


def test_splitters_and_explicit_collapse_preserve_inputs_and_result_selection(study, app):
    window, _ = study
    original = window.edited_draft()
    window.candidates.selectRow(0)
    window.tabs.setCurrentWidget(window.candidate_comparison_splitter)
    before = window.tabs.height()
    window.study_splitter.setSizes([0, 1]); app.processEvents()
    assert window.study_splitter.sizes()[0] == 0 and window.tabs.height() > before
    assert window.edited_draft() == original and window.selected_candidate() == 'C0001'
    window.inputs_panel_button.click(); app.processEvents()
    assert window.editor.isHidden()
    window.inputs_panel_button.click(); app.processEvents()
    assert not window.editor.isHidden() and window.study_splitter.sizes()[0] > 0
    window.results_panel_button.click(); app.processEvents()
    assert window.results_panel.isHidden()
    window.inputs_panel_button.click(); app.processEvents()
    assert not window.results_panel.isHidden() and window.editor.isHidden()
    assert window.tabs.currentWidget() is window.candidate_comparison_splitter
    assert window.edited_draft() == original and window.selected_candidate() == 'C0001'


def test_hidden_observations_survive_mode_changes_and_background_poll(study, app):
    window, client = study
    observations = deepcopy(window.edited_draft()['experiments'])
    window.variables.item(0, 3).setText('unfinished coefficient bound')
    window.mode.setCurrentText('fit'); app.processEvents()
    assert not window.experiments_panel.isHidden() and window.operation_options.isHidden()
    window.mode.setCurrentText('uq'); app.processEvents()
    assert window.experiments_panel.isHidden() and not window.operation_options.isHidden()
    window.refresh_document(); wait(app, client.poll_entered.is_set)
    window.inputs_panel_button.click(); app.processEvents()
    client.poll_release.set(); wait(app, lambda: not window._busy)
    edited = window.edited_draft()
    assert edited['experiments'] == observations
    assert edited['variables'][0]['lower'] == 'unfinished coefficient bound'
    assert edited['operation_options']['source']['reference'] == 'Declared test input law'
    assert window.local_dirty and window.editor.isHidden()
    assert window.candidates.item(1, 1).text() == '실패'


def test_request_plan_keeps_its_independent_layout(app):
    window = RequestPlanWindow(None, auto_open=False, poll_interval=0)
    assert not hasattr(window, 'study_splitter')
    assert window.inputs is not None and window.tabs is not None
    window._allow_close = True; window.close()


def test_failed_request_optimization_has_an_editable_empty_objective_view(app):
    window=RequestPlanWindow(None,auto_open=False,poll_interval=0)
    result={'kind':'optimization','execution_status':'PARTIAL_FAILURE','candidates':[
        {'candidate_id':'Cfailed','execution_status':'FAILED','objective':None,'responses':{}}]}
    original=deepcopy(result)
    try:
        window.figure.clear()
        window._draw_study_summary(result,'Jretained')
        assert '유효 목적값이 없습니다' in window.figure.axes[0].texts[0].get_text()
        assert result==original
    finally:window._allow_close=True;window.close()
