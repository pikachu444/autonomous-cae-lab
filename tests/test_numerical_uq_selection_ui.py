"""Retained UQ interval/bin selection, without any new evaluation or statistics."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from copy import deepcopy
from types import SimpleNamespace

import pytest
pytest.importorskip('PySide6')
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from apps.research.numerical_uq_window import NumericalUQWindow
from apps.research.request_plan_window import RequestPlanWindow


def result():
    rows = []
    for index, value in enumerate((1., 2., 2., 4.)):
        rows.append({'candidate_id': f'C{index}', 'execution_status': 'SUCCEEDED',
                     'responses': {'stress': {'kind': 'scalar', 'value': value, 'unit': 'MPa'},
                                   'temperature': {'kind': 'scalar', 'value': 300. + index, 'unit': 'K'}}})
    rows += [{'candidate_id': 'failed', 'execution_status': 'FAILED', 'failure_reason': 'solver failed'},
             {'candidate_id': 'predicted', 'execution_status': 'SUCCEEDED', 'prediction_status': 'PREDICTED',
              'responses': {'stress': {'kind': 'scalar', 'value': 0., 'unit': 'MPa'}}},
             {'candidate_id': 'wrong-unit', 'execution_status': 'SUCCEEDED',
              'responses': {'stress': {'kind': 'scalar', 'value': 0., 'unit': 'Pa'}}}]
    return {'kind': 'uq', 'candidates': rows, 'probability_statistics': [
        {'response': 'stress', 'unit': 'MPa', 'threshold': {'response': 'stress', 'unit': 'MPa'},
         'valid_count': 4, 'failed_count': 3, 'mean': 2.25, 'std': 1.258305739,
         'quantiles': {'q05': 1.15, 'q50': 2., 'q95': 3.7}},
        {'response': 'temperature', 'unit': 'K', 'threshold': {'response': 'temperature', 'unit': 'K'},
         'valid_count': 4, 'failed_count': 3, 'mean': 301.5, 'std': 1.290994449,
         'quantiles': {'q05': 300.15, 'q50': 301.5, 'q95': 302.85}}]}


@pytest.fixture
def window():
    app = QApplication.instance() or QApplication([])
    original = result()
    window = NumericalUQWindow(original)
    window.show()
    QTest.qWaitForWindowExposed(window)
    yield app, window, original
    window.close()
    app.processEvents()


def test_histogram_bins_select_exact_original_ids_including_last_edge(window):
    app, view, _ = window
    assert view._values == {0: 1., 1: 2., 2: 2., 3: 4.}
    assert len(view.table.findItems('없음', Qt.MatchFlag.MatchExactly)) == 3
    assert sum(patch.get_height() for patch in view._patch_rows) == 4
    last = list(view._patch_rows)[-1]
    view._bin_picked(SimpleNamespace(artist=last))
    assert view.selected_candidate_ids() == ['C3']
    first = list(view._patch_rows)[0]
    view._bin_picked(SimpleNamespace(artist=first))
    assert view.selected_candidate_ids() == ['C0', 'C1', 'C2']
    # Keyboard row selection highlights the same retained bin.
    view.table.clearSelection()
    view.table.setCurrentCell(2, 0)
    app.processEvents()
    assert view.selected_candidate_ids() == ['C2']
    assert view._selected_bars[first].get_height() == 1
    assert view._selected_bars[last].get_height() == 0


def test_interval_enter_invalid_draft_and_response_change_preserve_evidence(window):
    app, view, original = window
    before = deepcopy(original)
    view.lower.setText('2')
    view.upper.setText('2')
    view.upper.setFocus()
    QTest.keyClick(view.upper, Qt.Key.Key_Return)
    assert view.selected_candidate_ids() == ['C1', 'C2']
    view.lower.setText('nan')
    assert view.select_interval() is False
    assert view.selected_candidate_ids() == ['C1', 'C2']
    assert '유한한' in view.message.text()
    view.response.setCurrentIndex(1)
    app.processEvents()
    assert view.selected_candidate_ids() == []
    assert view.unit.text() == '[K]'
    assert view._values == {0: 300., 1: 301., 2: 302., 3: 303.}
    assert '301.5' in view.summary.text()
    assert original == before
    original['candidates'][0]['responses']['temperature']['value'] = 999.
    view._show_response()
    assert view._values[0] == 300.  # Opened view is a retained snapshot.


def test_request_menu_reads_selected_uq_without_client_execution():
    app = QApplication.instance() or QApplication([])
    class NoCalls:
        def __getattr__(self, name):
            raise AssertionError('Read-only UQ window called client: ' + name)
    owner = RequestPlanWindow(NoCalls(), auto_open=False, poll_interval=0)
    owner.selected_job = lambda: 'Jretained'
    owner._result_cache['Jretained'] = result()
    child = None
    try:
        child = owner.open_uq_distribution()
        assert child.result['candidates'][2]['candidate_id'] == 'C2'
        child.lower.setText('1'); child.upper.setText('4')
        assert child.select_interval()
        assert child.selected_candidate_ids() == ['C0', 'C1', 'C2', 'C3']
        owner._result_cache['Jretained'] = {'kind': 'fit'}
        assert owner.open_uq_distribution() is None
    finally:
        if child:
            child.close()
        owner._allow_close = True
        owner.close()
        app.processEvents()


def test_known_exclusions_have_korean_actions_and_keep_original_diagnostics(window):
    _, view, original = window
    assert view.table.item(4, 3).text() == '계산 실패: 실행 기록을 확인하세요.'
    assert view.table.item(4, 3).toolTip() == 'solver failed'
    assert view.table.item(5, 3).text() == '예측값 제외: 실제 계산 결과를 선택하세요.'
    assert 'PREDICTED' in view.table.item(5, 3).toolTip()
    assert view.table.item(6, 3).text() == '응답 단위 불일치: 원값 Pa / 선언 MPa'
    assert view.table.item(6, 3).toolTip() == 'stress response unit differs from the declared unit'
    assert original['candidates'][4]['failure_reason'] == view.result['candidates'][4]['failure_reason'] == 'solver failed'
    assert original['candidates'][6]['responses']['stress']['unit'] == 'Pa'
