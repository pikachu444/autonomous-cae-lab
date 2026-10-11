"""Actual candidate Qt reads of controlled retained native channels; no solve."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from copy import deepcopy
import math
import threading
import time

import pytest
pytest.importorskip('PySide6')
pytest.importorskip('matplotlib')
from PySide6.QtWidgets import QApplication

from apps.research.candidate_results_window import CandidateResultsWindow


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


def wait(app, predicate):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return
        time.sleep(.005)
    raise AssertionError('Controlled candidate read did not settle')


class RetainedNative:
    def __init__(self, kind='exact', stages=False):
        self.kind, self.has_stages = kind, stages
        self.calls = []
        self.delay, self.foreign, self.oversize = False, False, False
        self.started, self.release = threading.Event(), threading.Event()
        self.catalog = {
            'exact': {'radioss-ground-fz': {'unit': 'N', 'source': {'selector': 'radioss-ground-fz'}}},
            'node': {'pde.study0.u': {'unit': '1', 'node_ids': [7, 31], 'selector_template': 'pde.study0.u@<node_id>'}},
            'gauss': {'stress.xx': {'unit': 'Pa', 'selectors': [
                {'label': 'Element 9 · Gauss 1', 'selector': 'native-stress@9:gp1'},
                {'label': 'Element 9 · Gauss 2', 'selector': 'native-stress@9:gp2'}]}},
            'absent': {},
        }[kind]
        if kind != 'absent':
            self.catalog['other-exact'] = {'unit': 'Pa', 'source': {'selector': 'other-exact'}}

    def numerical_evaluation_result(self, document, job, candidate, **options):
        self.calls.append((document, job, candidate, deepcopy(options)))
        identity = {'document_id': document, 'job_id': job, 'candidate_id': candidate}
        index = options.get('evaluation_index')
        if index is None:
            return {**identity, 'evaluations': [{'evaluation_index': i, 'execution_status': 'SUCCEEDED'} for i in (0, 1)]}
        result = {**identity, 'evaluation_index': index, 'execution_status': 'SUCCEEDED'}
        if self.has_stages:
            result['stages'] = [{'iteration': 0, 'stage_id': 'Snative', 'attempt_id': 'Anative',
                                 'state': 'SUCCEEDED', 'backend': 'controlled.native'}]
        attempt = options.get('attempt_id')
        if attempt is not None:
            result['stage_attempt'] = {'attempt_id': attempt}
        selection = options.get('selection', {})
        if selection.get('metadata_only'):
            return {**result, 'native_channels': deepcopy(self.catalog), 'responses': {
                'cost': {'kind': 'scalar', 'unit': '1', 'value': 3.}}}
        assert set(selection) == {'responses', 'rows'}
        if self.delay:
            self.started.set(); assert self.release.wait(5)
        selector = selection['responses'][0]
        allowed = {'radioss-ground-fz', 'pde.study0.u@7', 'pde.study0.u@31',
                   'native-stress@9:gp1', 'native-stress@9:gp2', 'other-exact'}
        assert selector in allowed
        start, stop = selection['rows']
        if self.oversize:
            start, stop = 0, 6
        values, times = [10., 20., 30., 40., 50., 60.], [0., .125, .25, .375, .5, .625]
        response = {'kind': 'series', 'unit': 'N' if self.kind == 'exact' else 'Pa',
            'value': values[start:stop], 'axes': [{'name': 'time', 'unit': 's', 'values': times[start:stop]}],
            'source_rows': [100, 104, 109, 116, 125, 136][start:stop],
            'mask': [True, False, True, True, True, True][start:stop],
            'component': 'xx', 'quantity': 'recorded controlled stress', 'frame': 'native global',
            'measure': 'declared Cauchy', 'location': 'original recorded location',
            'source': {'selector': selector, 'artifact': 'retained/native.csv', 'sha256': 'a' * 64}}
        if self.foreign:
            result['candidate_id'] = 'Cforeign'
        return {**result, 'responses': {selector: response}}


def open_window(app, client, relevant=None):
    window = CandidateResultsWindow(client, document_id='Nplan', session_id='Sowner', job_id='Jretained',
        candidate_id='Cactual', relevant=relevant, values={'x': 2.}, units={'x': 'mm'})
    wait(app, lambda: not window._busy and window._composite is not None)
    return window


def close(app, window, client):
    client.release.set()
    wait(app, lambda: not window._busy)
    window.close()


@pytest.mark.parametrize('kind,selector', [('exact', 'radioss-ground-fz'), ('node', 'pde.study0.u@31'),
                                        ('gauss', 'native-stress@9:gp2')])
def test_exact_node_or_gauss_channel_reads_actual_bounded_candidate_curve_without_stages(app, kind, selector):
    client = RetainedNative(kind)
    window = open_window(app, client)
    try:
        assert window.stages.rowCount() == 0
        assert 'No stage graph was retained' in window.message.text()
        assert 'stage calls' not in window.evaluations.currentText()
        window.native_location.setCurrentIndex(window.native_location.findData(selector))
        window.curve_start.setValue(1); window.curve_count.setValue(2)
        assert window.curve_read.isEnabled()
        window.curve_read.click()
        wait(app, lambda: not window._busy and window._curve_result is not None)
        assert client.calls[-1] == ('Nplan', 'Jretained', 'Cactual', {
            'evaluation_index': 0, 'selection': {'responses': [selector], 'rows': [1, 3]}})
        assert window.native_location.currentData() == selector
        assert window.curve_values.rowCount() == 2
        assert window.curve_values.item(0, 0).text() == '104'
        assert window.curve_values.item(0, 1).text() == '0.125'
        assert window.curve_values.item(0, 2).text() == '20.0'
        assert window.curve_values.item(0, 3).text() == 'excluded'
        assert list(window.curve_axes.lines[0].get_xdata()) == [.125, .25]
        plotted = list(window.curve_axes.lines[0].get_ydata())
        assert math.isnan(plotted[0]) and plotted[1] == 30.
        assert '[s]' in window.curve_axes.get_xlabel()
        assert 'retained/native.csv' in window.curve_detail.text()
        assert 'No evaluation or adoption was executed' in window.message.text()
        assert window.stages.rowCount() == 0
    finally:
        close(app, window, client)


def test_stage_native_curve_read_keeps_exact_optional_attempt_in_existing_api(app):
    client = RetainedNative('gauss', stages=True)
    window = open_window(app, client)
    try:
        window.stages.selectRow(0)
        wait(app, lambda: not window._busy and window._stage_result is not None)
        window.native_location.setCurrentIndex(1)
        window.curve_count.setValue(3)
        window.curve_read.click()
        wait(app, lambda: not window._busy and window._curve_result is not None)
        assert client.calls[-1][3] == {'evaluation_index': 0, 'attempt_id': 'Anative',
            'selection': {'responses': ['native-stress@9:gp2'], 'rows': [0, 3]}}
        assert window._stage_result['stage_attempt']['attempt_id'] == 'Anative'
    finally:
        close(app, window, client)


@pytest.mark.parametrize('switch', ['channel', 'location', 'page', 'evaluation', 'parent', 'close'])
def test_late_curve_cannot_replace_changed_candidate_selection_or_page(app, switch):
    client = RetainedNative('node')
    current = [True]
    window = open_window(app, client, lambda: current[0])
    try:
        client.delay = True
        window.curve_read.click(); wait(app, client.started.is_set)
        assert not window.curve_read.isEnabled()
        if switch == 'channel':
            window.native_channel.setCurrentIndex(1)
        elif switch == 'location':
            window.native_location.setCurrentIndex(1)
        elif switch == 'page':
            window.curve_start.setValue(1)
        elif switch == 'evaluation':
            window.evaluations.setCurrentIndex(1)
        elif switch == 'parent':
            current[0] = False
        else:
            window.close()
        client.release.set()
        wait(app, lambda: not window._busy)
        assert window._curve_result is None and window.curve_values.rowCount() == 0
        assert not window.curve_axes.lines
        if switch == 'evaluation':
            assert window._composite['evaluation_index'] == 1
        assert len([call for call in client.calls if 'responses' in call[3].get('selection', {})]) == 1
    finally:
        close(app, window, client)


@pytest.mark.parametrize('failure', ['foreign', 'oversize'])
def test_changed_identity_or_unbounded_curve_is_not_displayed(app, failure):
    client = RetainedNative()
    window = open_window(app, client)
    try:
        setattr(client, failure, True)
        window.curve_count.setValue(2)
        window.curve_read.click(); wait(app, lambda: not window._busy)
        assert window._curve_result is None and not window.curve_axes.lines
        assert window.curve_values.rowCount() == 0
        assert 'does not match this selected record' in window.message.text()
    finally:
        close(app, window, client)


def test_absent_catalog_does_not_fabricate_native_location_or_read(app):
    client = RetainedNative('absent')
    window = open_window(app, client)
    try:
        assert window.native_channel.count() == window.native_location.count() == 0
        assert not window.curve_read.isEnabled()
        count = len(client.calls)
        window.read_native_curve()
        assert len(client.calls) == count and window.responses.item(0, 0).text() == 'cost'
    finally:
        close(app, window, client)
