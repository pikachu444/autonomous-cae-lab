"""Real Qt cell-editor drafts and existing beam save hooks; no native/solver."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from copy import deepcopy
from types import SimpleNamespace as NS
import pytest

from test_beam_support import model

W = pytest.importorskip('PySide6.QtWidgets')
from PySide6 import QtCore as C, QtTest as T


@pytest.fixture
def panel():
    from apps.desktop_pre.beam_panel import make_panel
    app = W.QApplication.instance() or W.QApplication([])
    data = model()
    record = {'draft': deepcopy(data['draft'])}
    reply = {'record': record, 'can_freeze': True, 'errors': [], 'preview': None}
    owner = NS(doc=NS(getObject=lambda name: NS(Label='시험 보')), project=NS(descriptor=lambda: {}))
    editor = NS(owner=owner, discover=lambda: [{'id': 'Analysis', 'label': '시험 해석',
        'meshes': [{'id': 'Mesh', 'label': '시험 선 메시'}]}], _records=lambda: {'Analysis': record},
        inspect=lambda key: deepcopy(reply))
    calls = []
    widget = make_panel(W, C, editor, lambda *args, **kwargs: calls.append((args, kwargs)),
        Gui=NS(), on_run=lambda *args: None, on_results=lambda *args: None,
        on_runner=lambda *args: None, on_save=lambda *args: None)
    widget.resize(900, 800); widget.show(); app.processEvents()
    tabs = widget.findChild(W.QTabWidget); tabs.setCurrentIndex(1)
    tables = [table for table in widget.findChildren(W.QTableWidget)
              if table.rowCount() == 4 and table.columnCount() == 3]
    tables.sort(key=lambda table: not table.isVisible())
    yield app, widget, tables, reply, calls
    widget.close(); widget.deleteLater(); app.processEvents()


def active_cell(fixture, row=0, column=0):
    app, widget, tables, reply, calls = fixture
    table = tables[0]
    table.setCurrentCell(row, column)
    table.editItem(table.item(row, column)); app.processEvents()
    field = app.focusWidget()
    assert isinstance(field, W.QLineEdit)
    field.selectAll(); T.QTest.keyClicks(field, '1e'); app.processEvents()
    return table, field


@pytest.mark.parametrize('row,key', [(0, 'force_N'), (1, 'moment_Nmm'), (3, 'rotation_deg')])
def test_active_end_cell_raw_text_is_in_snapshot_before_focus_out(panel, row, key):
    app, widget, tables, reply, calls = panel
    table, field = active_cell(panel, row)
    assert field.hasFocus() and table.item(row, 0).text() != '1e'  # Delegate has not committed.
    assert widget.pending_changes()
    assert widget.pending_snapshot()['ends'][0][key][0] == '1e'
    assert widget.editor_token() is not None
    assert not calls


def test_late_save_keeps_new_active_text_and_matching_receipt_acknowledges_it(panel):
    app, widget, tables, reply, calls = panel
    table, field = active_cell(panel)
    first = widget.pending_snapshot()
    field.selectAll(); T.QTest.keyClicks(field, '2e'); app.processEvents()
    saved = deepcopy(reply); saved['record']['draft'] = first
    widget.accept_saved_snapshot(first, saved)
    assert field.hasFocus() and field.text() == '2e'
    assert widget.pending_snapshot()['ends'][0]['force_N'][0] == '2e'
    assert widget.pending_changes()
    current = widget.pending_snapshot()
    saved['record']['draft'] = deepcopy(current)
    widget.accept_saved_snapshot(current, saved)
    assert not widget.pending_changes()
    assert tables[0].item(0, 0).text() == '2e'


def test_escape_reverts_only_active_cell_and_restores_clean_state(panel):
    app, widget, tables, reply, calls = panel
    table, field = active_cell(panel)
    T.QTest.keyClick(field, C.Qt.Key_Escape); app.processEvents()
    assert table.item(0, 0).text() == '0'
    assert not widget.pending_changes() and widget.pending_snapshot() is None


def test_escape_keeps_prior_edits_and_enter_commits_same_raw_value(panel):
    app, widget, tables, reply, calls = panel
    width = next(field for field in widget.findChildren(W.QLineEdit) if field.accessibleName() == '폭 [mm] — 1축')
    width.setFocus(); width.selectAll(); T.QTest.keyClicks(width, '12'); app.processEvents()
    table, field = active_cell(panel)
    T.QTest.keyClick(field, C.Qt.Key_Escape); app.processEvents()
    assert widget.pending_changes() and widget.pending_snapshot()['section']['width_mm'] == '12'
    table, field = active_cell(panel)
    T.QTest.keyClick(field, C.Qt.Key_Return); app.processEvents()
    assert table.item(0, 0).text() == '1e'
    assert widget.pending_snapshot()['ends'][0]['force_N'][0] == '1e'


def test_escape_before_late_save_receipt_keeps_visible_value_pending(panel):
    app, widget, tables, reply, calls = panel
    table, field = active_cell(panel)
    snapshot = widget.pending_snapshot()
    T.QTest.keyClick(field, C.Qt.Key_Escape); app.processEvents()
    assert not widget.pending_changes()
    saved = deepcopy(reply); saved['record']['draft'] = snapshot
    widget.accept_saved_snapshot(snapshot, saved)
    assert widget.pending_changes()
    assert widget.pending_snapshot()['ends'][0]['force_N'][0] == '0'


def test_matching_save_then_new_edit_escape_uses_new_saved_baseline(panel):
    app, widget, tables, reply, calls = panel
    table, field = active_cell(panel)
    snapshot = widget.pending_snapshot()
    saved = deepcopy(reply); saved['record']['draft'] = snapshot
    widget.accept_saved_snapshot(snapshot, saved)
    assert not widget.pending_changes()
    field.setFocus(); field.selectAll(); T.QTest.keyClicks(field, '2e'); app.processEvents()
    assert widget.pending_changes()
    T.QTest.keyClick(field, C.Qt.Key_Escape); app.processEvents()
    assert table.item(0, 0).text() == '1e'
    assert not widget.pending_changes()


def test_different_save_receipt_then_escape_still_needs_current_value_saved(panel):
    app, widget, tables, reply, calls = panel
    table, field = active_cell(panel)
    snapshot = widget.pending_snapshot()
    field.selectAll(); T.QTest.keyClicks(field, '2e'); app.processEvents()
    saved = deepcopy(reply); saved['record']['draft'] = snapshot
    widget.accept_saved_snapshot(snapshot, saved)
    T.QTest.keyClick(field, C.Qt.Key_Escape); app.processEvents()
    assert widget.pending_changes()
    current = widget.pending_snapshot()
    assert current['ends'][0]['force_N'][0] == '0'
    saved['record']['draft'] = current
    widget.accept_saved_snapshot(current, saved)
    assert not widget.pending_changes()


def test_other_analysis_receipt_does_not_change_current_clean_state(panel):
    app, widget, tables, reply, calls = panel
    snapshot = deepcopy(reply['record']['draft'])
    snapshot['analysis_id'] = 'OtherAnalysis'
    saved = deepcopy(reply); saved['record']['draft'] = snapshot
    widget.accept_saved_snapshot(snapshot, saved)
    assert not widget.pending_changes()
    assert tables[0].item(0, 0).text() == '0'
