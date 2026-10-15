"""Qt table selections reuse exact retained native commands; no ParaView run."""
from copy import deepcopy

import pytest

pytest.importorskip('PySide6')
pytest.importorskip('matplotlib')
from PySide6.QtCore import QSignalBlocker, QCoreApplication, QEvent
from PySide6.QtWidgets import QApplication, QInputDialog

from apps.research.post_curve_editor import default_recipe as curve_recipe
from apps.research.post_window import PostWindow, defaults
from test_research_post_ui import NativeClient, wait


class SelectionClient(NativeClient):
    def __init__(self, *, curve=False):
        super().__init__()
        self.curve = curve
        recipe = curve_recipe() if curve else defaults('comparison')
        if not curve:
            recipe['target']['units'] = recipe['a']['units'] = recipe['b']['units'] = 'MPa'
            recipe['a']['coordinate_units'] = 'mm'
        record = {'id': 'Vexact', 'recipe': recipe, 'summary': {}}
        obj = {'id': 'Aretained', 'kind': 'comparison', 'title': '선택한 비교 결과',
               'draft': deepcopy(recipe), 'history': [record], 'position': 0,
               'preview': None, 'diagnostics': []}
        self.document['state']['analysis'].update(objects=[obj], active_object=obj['id'])
        self.document['title'] = '원본 표본 선택'
        self.rows = ([{'row_index': i, 'x': float(i), 'a': 2., 'b': 3., 'delta': 1.,
                       'percent': 50., 'a_row': {'row': 100+i}, 'b_rows': [{'row': 200+i}],
                       'valid': True, 'a_valid': True, 'b_valid': True, 'a_segment': 0, 'b_segment': 0,
                       'reason': 'valid', 'percent_reason': 'valid'} for i in (7, 19)]
                     if curve else [{'point_index': i, 'a': 2., 'b': 3., 'delta': 1.,
                                     'coordinates': [float(i), 0., 0.],
                                     'valid': True} for i in (7, 19)])

    def payload(self, rows=None):
        result = {'object_ref': 'Aretained', 'revision': 'Vexact', 'preview': False,
                  'rows': deepcopy(self.rows if rows is None else rows)}
        if self.curve:
            source = {'title': '힘 이력', 'axis': {'name': '시간', 'unit': 's'}, 'declaration': {'units': 'N'}}
            originals = {tag: [{'row_index': row['row_index'], 'identity': {'row': row['row_index']},
                'x': row['x'], 'y': row[tag], 'quality': True, 'calculation': True,
                'visible': True, 'segment': 0} for row in self.rows] for tag in ('a', 'b')}
            result.update(semantics='retained_curve_comparison', originals=originals,
                summary={'recipe': {'target_unit': 'N'}, 'valid_count': 2, 'count_a': 2,
                         'sources': {'a': source, 'b': deepcopy(source)}})
        return result

    def _execute(self, command):
        if command['operation'] != 'post.sample':
            return super()._execute(command)
        args = command['arguments']
        assert args['expected_revision'] == 'Vexact'
        key = 'row_index' if self.curve else 'point_index'
        rows = [row for row in self.rows if row[key] == args[key]]
        self.execute_count[command['command_id']] = self.execute_count.get(command['command_id'], 0)+1
        self.document['generation'] += 1
        return self.payload(rows)


@pytest.fixture
def selection_window():
    app = QApplication.instance() or QApplication([])
    opened = []

    def create(*, curve=False):
        client = SelectionClient(curve=curve)
        window = PostWindow(client, document_id='Dpost', session_id='Snative',
                            auto_open=False, poll_interval=0)
        opened.append(window)
        window._show_document(client.document, initial=True)
        window._show_samples(client.payload())
        return app, client, window

    yield create
    for window in opened:
        try:
            window.client.release = True
            wait(app, lambda: not window._busy and window._pending is None)
        finally:
            window._allow_close = True
            window.close()
            window.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


@pytest.mark.parametrize('curve', [False, True])
def test_table_pick_uses_retained_identity_and_does_not_repeat_on_reply(selection_window, curve):
    app, client, window = selection_window(curve=curve)
    assert client.calls == []  # Filling the table must not select a native point.
    before = deepcopy(window._samples)
    window.samples.selectRow(1)
    wait(app, lambda: not window._busy and window._pending is None)
    assert len(client.calls) == 1
    _, operation, arguments = client.calls[0]
    key = 'row_index' if curve else 'point_index'
    assert operation == 'post.sample'
    assert arguments[key] == 19  # Original identity, not the displayed row 1.
    assert arguments['expected_revision'] == 'Vexact'
    assert arguments['object_ref'] == 'Aretained'
    assert arguments['preview'] is False
    assert window.samples.currentRow() == 1
    assert window._samples == before
    assert sum(client.execute_count.values()) == 1


def test_stale_table_does_not_select_a_different_native_revision(selection_window):
    _, client, window = selection_window()
    window.document['state']['analysis']['objects'][0]['history'][0]['id'] = 'Vnew'
    before = deepcopy(window._samples)
    window.samples.selectRow(1)
    assert client.calls == []
    assert window._samples == before
    assert '다시' in window.message.text()


def test_busy_or_failed_selection_requires_reread_without_replaying(selection_window):
    _, client, window = selection_window()
    window._busy = True
    window.samples.selectRow(1)
    window._busy = False
    assert client.calls == []
    window._sample_basis['failed'] = True
    window.samples.selectRow(0)
    assert client.calls == []
    assert '다시 읽으세요' in window.message.text()


def clone_owner(client, window):
    client.document.update(id='Dclone', session_id='Sclone')
    window.document_id, window.session_id = 'Dclone', 'Sclone'
    window._show_document(client.document)
    window._show_samples(client.payload())


@pytest.mark.parametrize('curve', [False, True])
def test_old_plot_cannot_select_a_clone_with_matching_object_and_revision(selection_window, curve):
    _, client, window = selection_window(curve=curve)
    old_basis = deepcopy(window._sample_basis)
    clone_owner(client, window)
    before = deepcopy(window._samples)
    select = window.select_curve_row if curve else window.select_comparison_point
    assert select(19, old_basis) is False
    assert client.calls == []
    assert window._samples == before


@pytest.mark.parametrize('curve', [False, True])
def test_reply_from_previous_owner_does_not_move_clone_selection(selection_window, curve):
    _, client, window = selection_window(curve=curve)
    pending = []
    window.queue_command = lambda *args, **options: pending.append(options['accepted']) or True
    basis = deepcopy(window._sample_basis)
    select = window.select_curve_row if curve else window.select_comparison_point
    assert select(19, basis) is True
    clone_owner(client, window)
    with QSignalBlocker(window.samples):
        window.samples.selectRow(0)
    pending[0]({'object_ref': 'Aretained', 'revision': 'Vexact'})
    assert window.samples.currentRow() == 0
    assert len(pending) == 1


def test_choosing_another_owner_clears_old_table_without_native_selection(selection_window, monkeypatch):
    app, client, window = selection_window()
    client.document.update(id='Dclone', session_id='Sclone')
    client.documents = lambda: {'documents': [deepcopy(client.document)]}
    monkeypatch.setattr(QInputDialog, 'getItem', lambda *args, **options: (args[3][0], True))
    assert window.choose_document() is True
    wait(app, lambda: not window._busy and window.document is not None and window.document_id == 'Dclone')
    assert (window.document_id, window.session_id) == ('Dclone', 'Sclone')
    assert window._samples is None and window._sample_basis is None
    assert window.samples.rowCount() == 0 and window.samples.columnCount() == 0
    assert client.calls == []
