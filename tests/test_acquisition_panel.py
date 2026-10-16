"""Selection and paging use the same acquisition evidence as the worksheet."""
from copy import deepcopy
import os
import threading
import time

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import pytest
pytest.importorskip('PySide6')
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMainWindow

from apps.research.acquisition_panel import AcquisitionPanel
from test_acquisition import plan


@pytest.fixture
def panel(monkeypatch):
    app = QApplication.instance() or QApplication([])
    host = QMainWindow()
    host.client = None
    host.local_dirty = host.conflict = False
    host.document = {'id': 'Tpreview', 'session_id': 'preview', 'generation': 0, 'draft': {}}
    monkeypatch.setattr(AcquisitionPanel, 'reload_runs', lambda self: None)
    window = AcquisitionPanel(host)
    window.timer.stop()
    window.run_id = 'Cfirst'
    calls = []
    monkeypatch.setattr(window, '_action', lambda action, arguments, accepted:
        calls.append((action, arguments, accepted)) or True)
    try:
        yield app, window, calls
    finally:
        window.close()
        host.close()
        app.processEvents()


def received(run='Cfirst', count=2, after=0):
    return {'run_id': run, 'job_state': None, 'state': {
        'plan': plan(), 'source': {'name': '기록.csv'}, 'state': 'PAUSED',
        'samples': 205, 'duplicates': 0, 'conflicts': 0, 'malformed': 0,
        'segment': 1, 'source_cursor': 5000, 'ledger_revision': 3},
        'events': [{'id': i + 1, 'kind': 'SAMPLE', 'sequence': i,
            'timestamp': i / 10, 'values': {'force': str(i)}, 'quality': [], 'segment': 0}
            for i in range(after, after + count)]}


def test_raw_response_tracks_selected_row_run_and_visibility(panel):
    app, window, calls = panel
    window._received(received())
    window.table.selectRow(0)
    window.details_button.setChecked(True)
    first = calls[-1]
    assert first[1]['raw'] and first[1]['after'] == 0
    window.table.selectRow(1)
    second = calls[-1]
    first[2]({'run_id': 'Cfirst', 'events': [{'id': 1, 'raw_hex': '61'}]})
    assert window.details.toPlainText() == ''
    second[2]({'run_id': 'Cfirst', 'events': [{'id': 2, 'raw_hex': '62'}]})
    assert '62' in window.details.toPlainText()
    window.details_button.setChecked(False)
    second[2]({'run_id': 'Cfirst', 'events': [{'id': 2, 'raw_hex': 'old'}]})
    assert window.details.toPlainText() == ''
    window.details_button.setChecked(True)
    old = calls[-1]
    window.runs.addItem('다른 취득', 'Csecond')
    window.select_run(window.runs.findData('Csecond'))
    old[2]({'run_id': 'Cfirst', 'events': [{'id': 2, 'raw_hex': 'old'}]})
    assert window.details.toPlainText() == '' and window.table.rowCount() == 0
    assert not window.start_button.isEnabled()
    window._received(received('Cfirst'))
    assert window.table.rowCount() == 0


def test_unchanged_head_still_drains_pages_and_preserves_selection(panel):
    app, window, calls = panel
    window._received(received(count=100))
    window.table.selectRow(5)
    selected = window.table.item(5, 0).data(Qt.ItemDataRole.UserRole)
    for after, count in [(100, 100), (200, 5)]:
        calls.clear()
        window.poll()
        assert calls[-1][0] == 'read' and calls[-1][1]['after'] == after
        calls[-1][2](received(count=count, after=after))
    assert window.table.rowCount() == 205
    assert window.table.item(window.table.currentRow(), 0).data(Qt.ItemDataRole.UserRole) == selected
    calls.clear()
    window.poll()
    assert calls[-1][0] == 'head'
    unchanged = deepcopy(window._head)
    calls[-1][2](unchanged)
    assert len(calls) == 1


@pytest.mark.parametrize('edit_during_dialog', [False, True])
def test_plan_edit_keeps_one_current_draft_and_generation_snapshot(panel, monkeypatch, edit_during_dialog):
    from types import SimpleNamespace
    import apps.research.acquisition_panel as module
    app, window, calls = panel
    current = deepcopy(window.host.document)
    current.update(generation=1, draft={'data_id': 'Dhost',
        'mapping': {'columns': {'host_channel': {'unit': 'N'}}}, 'acquisition': plan()})
    window.host.document = current
    captured = {}
    class Dialog:
        DialogCode = SimpleNamespace(Accepted=1)
        reuse = SimpleNamespace(hide=lambda: None)
        def __init__(self, acquisition, columns, parent):
            assert acquisition == current['draft']['acquisition']
            assert columns == current['draft']['mapping']['columns']
        def exec(self):
            if edit_during_dialog:
                window.host.document = deepcopy(current)
                window.host.document['generation'] = 2
                window.host.document['draft']['data_id'] = 'Dnewer'
            return 1
        def edited(self):
            return {**plan(), 'name': '편집한 취득 계획'}
    def command(document_id, operation, arguments, **identity):
        captured.update(arguments=arguments, identity=identity)
        if identity['expected_generation'] != window.host.document['generation']:
            raise ValueError('Document generation changed; reread before applying')
        return {'document': {**deepcopy(current), 'draft': arguments['draft']}}
    monkeypatch.setattr(module, 'AcquisitionDialog', Dialog)
    window.client = SimpleNamespace(document_command=command)
    monkeypatch.setattr(window, '_call', lambda function, accepted: accepted(function()))
    if edit_during_dialog:
        with pytest.raises(ValueError, match='generation changed'):
            window.edit_plan()
        assert window.host.document['draft']['data_id'] == 'Dnewer'
    else:
        window.host._opened = lambda document: None
        window.edit_plan()
    assert captured['identity']['expected_generation'] == 1
    assert captured['arguments']['draft']['data_id'] == 'Dhost'
    assert captured['arguments']['draft']['mapping'] == current['draft']['mapping']


@pytest.mark.parametrize('changed_key', ['id', 'session_id'])
def test_host_document_or_session_switch_closes_actions_without_redirect(panel, monkeypatch, changed_key):
    app, window, calls = panel
    original = deepcopy(window.document)
    window._state = {'state': 'PAUSED', 'samples': 2}
    window.host.document = {**deepcopy(original), changed_key: 'different'}
    commands = []
    monkeypatch.setattr(window, '_call', lambda *arguments: commands.append(arguments))
    # Every mutating entry point handles the changed binding before submitting.
    window.save()
    window.start()
    window.request('stop')
    window.materialize()
    window.edit_plan()
    window.load_replay('unused.csv')
    assert window._closed and not calls and not commands
    assert window.document == original
    assert window.host.document[changed_key] == 'different'


@pytest.mark.parametrize('changed_key', ['id', 'session_id'])
def test_delayed_update_cannot_restore_previous_host_document(panel, changed_key):
    app, window, calls = panel
    original = deepcopy(window.document)
    window.host.document = {**deepcopy(original), changed_key: 'different'}
    opened = []
    window.host._opened = opened.append
    assert window._updated({'document': original}) is False
    assert not opened and window._closed
    assert window.host.document[changed_key] == 'different'


def test_async_completion_is_discarded_after_host_switch(panel):
    from PySide6.QtCore import QThreadPool
    app, window, calls = panel
    ready, release = threading.Event(), threading.Event()
    accepted = []
    def pending():
        ready.set()
        assert release.wait(3)
        return {'document': deepcopy(window.document)}
    try:
        assert window._call(pending, accepted.append)
        assert ready.wait(3)
        window.host.document = {**deepcopy(window.document), 'id': 'Tdifferent'}
        release.set()
        until = time.monotonic() + 3
        while not window._closed and time.monotonic() < until:
            app.processEvents()
            time.sleep(.005)
        assert window._closed and not accepted
        assert window.host.document['id'] == 'Tdifferent'
    finally:
        release.set()
        QThreadPool.globalInstance().waitForDone(3000)


def test_same_document_generation_refresh_and_update_remain_available(panel):
    app, window, calls = panel
    current = {**deepcopy(window.host.document), 'generation': 2,
        'draft': {'data_id': 'Dcurrent', 'mapping': {'columns': {}}}}
    window.host.document = current
    assert window._identity()['expected_generation'] == 2
    assert window.document['draft'] == current['draft']
    updated = {**deepcopy(current), 'generation': 3}
    opened = []
    window.host._opened = opened.append
    assert window._updated({'document': updated})
    assert opened == [updated] and not window._closed
