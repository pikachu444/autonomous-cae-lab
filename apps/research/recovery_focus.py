"""Keep live delegates unfinished while the user reviews recovery in a modal."""
from PySide6.QtCore import QObject, QEvent
from PySide6.QtWidgets import QApplication, QAbstractItemView, QComboBox, QLineEdit
from shiboken6 import isValid


class RawEditorFocusGuard(QObject):
    def __init__(self, roots):
        super().__init__()
        self._editors = []
        self._positions = {}
        self._active = False
        self._focus = QApplication.focusWidget()
        self.protect_current(roots)

    def protect_current(self, roots, *, restore_focus=False):
        roots=list(roots); added=[]
        for root in roots:
            for table in root.findChildren(QAbstractItemView):
                if table.state() != QAbstractItemView.State.EditingState: continue
                for kind in (QComboBox, QLineEdit):
                    added.extend(editor for editor in table.findChildren(kind)
                                 if editor.isVisible() and editor not in self._editors and editor not in added)
        self._editors.extend(added)
        for editor in added:
            if isinstance(editor, QLineEdit):
                self._positions[editor] = (editor.text(), editor.cursorPosition(),
                                           editor.selectionStart(), editor.selectionLength())
        if self._active:
            for editor in added: editor.installEventFilter(self)
        if restore_focus:
            candidate=added[0] if added else next((root.focusWidget() for root in roots if root.focusWidget()),None)
            if candidate is not None: self._focus=candidate

    def __enter__(self):
        self._active=True
        for editor in self._editors: editor.installEventFilter(self)
        return self

    def eventFilter(self, watched, event):
        if watched in self._editors and event.type() == QEvent.Type.FocusOut:
            return True
        return super().eventFilter(watched, event)

    def __exit__(self, *_):
        self._active=False
        for editor in self._editors:
            if isValid(editor): editor.removeEventFilter(self)
        self.restore_focus()

    def restore_focus(self):
        if self._focus is not None and isValid(self._focus) and self._focus.isVisible():
            self._focus.window().activateWindow()
            self._focus.setFocus()
        for editor, (text, cursor, start, count) in self._positions.items():
            if not isValid(editor) or editor.text() != text:
                continue
            if count:
                editor.setSelection(start + count, -count) if cursor == start else editor.setSelection(start, count)
            else:
                editor.setCursorPosition(cursor)
