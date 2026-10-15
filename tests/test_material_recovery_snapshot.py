import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from copy import deepcopy
import pytest
pytest.importorskip('PySide6')
pytest.importorskip('matplotlib')
from PySide6.QtWidgets import QApplication, QLineEdit
from apps.research.material_window import MaterialWindow
from apps.research.material_recovery import material_raw_snapshot, restore_material_raw
from test_research_material_ui import material_draft


def test_raw_snapshot_never_commits_or_parses_live_editor():
    app = QApplication.instance() or QApplication([])
    document = dict(id='Msnapshot', kind='material', session_id='Sowner', generation=0,
                    input_revision='Ioriginal', draft=material_draft(), title='재료', runs=[], diagnostics=[],
                    dirty=False, can_undo=False, can_redo=False, saved_revision=None)
    window = MaterialWindow(None, auto_open=False, poll_interval=0)
    try:
        window._show_document(document); window.show(); window.coefficients.setCurrentCell(0, 1)
        window.coefficients.setFocus(); window.coefficients.editItem(window.coefficients.item(0, 1)); app.processEvents()
        editor = app.focusWidget(); assert isinstance(editor, QLineEdit)
        editor.setText('1e'); editor.setCursorPosition(2)
        raw = material_raw_snapshot(window)
        assert material_raw_snapshot(window) == raw
        entry = next(cell for cell in raw['cells'] if cell['field_path'] == ['settings', 'parameters', 'E'])
        assert entry['raw_text'] == '1e' and entry['original_value'] == 1000 and entry['editor_kind'] == 'unfinished'
        assert window.coefficients.item(0, 1).text() == '1000'
        assert app.focusWidget() is editor and editor.text() == '1e'
        assert raw['local_draft']['settings']['parameters']['E'] == 1000
        assert window.document == document
        editor.setText('')
        assert material_raw_snapshot(window)['editor_revision'] != raw['editor_revision']
        target = MaterialWindow(None, auto_open=False, poll_interval=0)
        try:
            target._show_document(document); target.show(); target.activateWindow(); app.processEvents()
            wrong = deepcopy(raw); wrong['cells'][0]['original_value'] = 2345
            with pytest.raises(ValueError): restore_material_raw(target, wrong)
            assert target.document == document and not target.local_dirty
            restore_material_raw(target, raw); app.processEvents()
            restored = app.focusWidget()
            assert isinstance(restored, QLineEdit) and restored.text() == '1e'
            assert target.coefficients.item(0, 1).text() == '1000'
            assert target.document == document and target.local_dirty
        finally:
            target._allow_close = True; target.close(); app.processEvents()
    finally:
        window._allow_close = True; window.close(); app.processEvents()


def test_new_history_cell_preserves_missing_original_and_acknowledged_base():
    app = QApplication.instance() or QApplication([])
    document = dict(id='Msnapshot', kind='material', session_id='Sowner', generation=0,
                    input_revision='Ioriginal', draft=material_draft(), title='재료', runs=[], diagnostics=[],
                    dirty=False, can_undo=False, can_redo=False, saved_revision=None)
    window = MaterialWindow(None, auto_open=False, poll_interval=0)
    try:
        window._show_document(deepcopy(document)); window.add_state()
        raw = material_raw_snapshot(window)
        added = next(cell for cell in raw['cells'] if cell['field_path'] == ['settings', 'time', 3])
        assert added['original_exists'] is False and added['original_value'] is None and added['raw_text'] == ''
        assert len(raw['local_draft']['settings']['time']) == 4
        assert window.document == document
    finally:
        window._allow_close = True; window.close(); app.processEvents()
