import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import pytest
pytest.importorskip('PySide6')
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QDialog, QLineEdit, QPushButton, QVBoxLayout
from apps.research.recovery_focus import RawEditorFocusGuard


@pytest.mark.parametrize('kind', ['data', 'material'])
def test_modal_review_preserves_live_delegate_text_and_original_cell(kind):
    app = QApplication.instance() or QApplication([])
    if kind == 'data':
        from apps.research.data_window import DataWindow
        from apps.research.data_recovery import data_raw_snapshot as snapshot
        from caelab.data_document import default_draft
        view = DataWindow(None, auto_open=False, poll_interval=0); table = view.mapping; row, column = 1, 8
    else:
        from apps.research.material_window import MaterialWindow
        from apps.research.material_recovery import material_raw_snapshot as snapshot
        from caelab.material_document import default_draft
        view = MaterialWindow(None, auto_open=False, poll_interval=0); table = view.coefficients; row, column = 0, 1
    document = dict(id='Tfixture' if kind == 'data' else 'Mfixture', kind=kind,
        session_id='Sfixture', generation=0, input_revision='Ifixture', draft=default_draft(),
        title='원문 입력', runs=[], diagnostics=[], dirty=False, saved_revision=None,
        can_undo=False, can_redo=False)
    dialog = QDialog(view); layout = QVBoxLayout(dialog); button = QPushButton('취소'); layout.addWidget(button)
    try:
        view._show_document(document); view.show(); view.activateWindow(); app.processEvents()
        table.setCurrentCell(row, column); table.setFocus(); table.scrollToItem(table.item(row, column))
        table.editItem(table.item(row, column)); app.processEvents()
        editor = QApplication.focusWidget(); assert isinstance(editor, QLineEdit)
        original = table.item(row, column).text(); editor.setText('1e'); editor.setSelection(0, 1)
        before = snapshot(view); seen = []
        def inspect():
            button.setFocus(); app.processEvents()
            seen.append(snapshot(view)); dialog.reject()
        with RawEditorFocusGuard([view]):
            QTimer.singleShot(30, inspect); dialog.exec()
        app.processEvents()
        assert seen == [before]
        assert table.item(row, column).text() == original and editor.text() == '1e'
        assert QApplication.focusWidget() is editor and editor.selectedText() == '1'
        assert view.document == document
    finally:
        dialog.close(); view._allow_close = True; view.close(); app.processEvents()


def test_unicode_reverse_selection_uses_qt_utf16_positions():
    from apps.research.material_recovery import _line_focus, _restore_line_focus
    app = QApplication.instance() or QApplication([])
    source, target = QLineEdit('🙂12'), QLineEdit('🙂12')
    source.setSelection(2, -2)
    focus = _line_focus(source)
    assert focus == dict(cursor=0, selection=[0, 2])
    _restore_line_focus(target, focus)
    assert target.selectedText() == '🙂' and target.cursorPosition() == 0
    with pytest.raises(ValueError, match='선택 범위'):
        _restore_line_focus(target, dict(cursor=8, selection=[0, 2]))
    source.close(); target.close(); app.processEvents()
