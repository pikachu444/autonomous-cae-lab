"""Keep live delegates unfinished while the user reviews recovery in a modal."""
from PySide6.QtCore import QObject, QEvent
from PySide6.QtWidgets import QApplication, QAbstractItemView, QComboBox, QLineEdit
from shiboken6 import isValid


class RawEditorFocusGuard(QObject):
    def __init__(self, roots):
        super().__init__()
        self._editors = []
        self._focus = QApplication.focusWidget()
        for root in roots:
            for table in root.findChildren(QAbstractItemView):
                if table.state() != QAbstractItemView.State.EditingState: continue
                for kind in (QComboBox, QLineEdit):
                    self._editors.extend(editor for editor in table.findChildren(kind)
                                         if editor.isVisible() and editor not in self._editors)

    def __enter__(self):
        for editor in self._editors: editor.installEventFilter(self)
        return self

    def eventFilter(self, watched, event):
        if watched in self._editors and event.type() == QEvent.Type.FocusOut:
            return True
        return super().eventFilter(watched, event)

    def __exit__(self, *_):
        for editor in self._editors:
            if isValid(editor): editor.removeEventFilter(self)
        if self._focus is not None and isValid(self._focus) and self._focus.isVisible():
            self._focus.window().activateWindow()
            self._focus.setFocus()
