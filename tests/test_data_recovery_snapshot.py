import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from copy import deepcopy
import pytest
pytest.importorskip('PySide6')
from PySide6.QtWidgets import QApplication, QLineEdit
from PySide6.QtTest import QTest
from apps.research.data_window import DataWindow
from apps.research.data_recovery import data_raw_snapshot, restore_data_raw
from caelab.data_document import default_draft


def document():
    return dict(id='Tfixture', kind='data', session_id='Sfixture', generation=0,
        input_revision='Ifixture', draft=default_draft(), title='인장 원문', runs=[],
        diagnostics=[], dirty=False, saved_revision=None, can_undo=False, can_redo=False)


def test_data_pending_scale_is_not_committed_and_restores_only_fresh_view():
    app = QApplication.instance() or QApplication([])
    source = DataWindow(None, auto_open=False, poll_interval=0)
    target = DataWindow(None, auto_open=False, poll_interval=0)
    doc = document()
    try:
        source._show_document(doc); source.show(); app.processEvents()
        source.mapping.setCurrentCell(1, 8); source.mapping.setFocus()
        source.mapping.editItem(source.mapping.item(1, 8)); app.processEvents()
        editor = QApplication.focusWidget(); assert isinstance(editor, QLineEdit)
        editor.setText('1e'); editor.setCursorPosition(2)
        raw = data_raw_snapshot(source)
        assert data_raw_snapshot(source) == raw
        assert source.mapping.item(1, 8).text() == '1' and QApplication.focusWidget() is editor
        assert source.document == doc
        target._show_document(deepcopy(doc)); target.show(); target.activateWindow(); app.processEvents()
        restore_data_raw(target, raw); app.processEvents()
        restored = QApplication.focusWidget()
        assert isinstance(restored, QLineEdit) and restored.text() == '1e'
        assert target.mapping.item(1, 8).text() == '1' and target.document == doc
        assert data_raw_snapshot(target)['focus']['cursor'] == 2
        with pytest.raises(ValueError, match='편집을 마친'):
            restore_data_raw(target, raw)
    finally:
        for view in (source, target): view._allow_close = True; view.close()
        app.processEvents()


def test_data_recovery_preserves_other_channels_and_rejects_hidden_provenance():
    app = QApplication.instance() or QApplication([])
    source = DataWindow(None, auto_open=False, poll_interval=0)
    target = DataWindow(None, auto_open=False, poll_interval=0)
    doc = document(); doc['draft']['mapping']['case_id'] = 'original'
    doc['draft']['mapping']['columns']['other'] = deepcopy(doc['draft']['mapping']['columns']['response'])
    try:
        source._show_document(doc)
        source._working_draft['mapping']['columns']['other']['unit'] = 'kPa'
        source.mapping.item(1, 1).setText('인장')
        source.row_fields['exclude_ranges'].setText('1e:20')
        source.mapping.setCurrentCell(1, 4)
        raw = data_raw_snapshot(source)
        target._show_document(deepcopy(doc))
        bad = deepcopy(raw); bad['local_draft']['mapping']['case_id'] = 'foreign'
        with pytest.raises(ValueError, match='범위 밖'):
            restore_data_raw(target, bad)
        assert target.document == doc and not target.local_dirty
        restore_data_raw(target, raw)
        draft = target.edited_draft(commit=False)
        assert draft['mapping']['columns']['other']['unit'] == 'kPa'
        assert draft['mapping']['columns']['인장']['row_selection']['exclude_ranges'] == '1e:20'
        assert list(draft['mapping']['columns']) == ['인장', 'other']
        assert [[index.row(), index.column()] for index in target.mapping.selectedIndexes()] == [[1, 4]]
        assert target.document == doc and source.document == doc
    finally:
        for view in (source, target): view._allow_close = True; view.close()
        app.processEvents()
