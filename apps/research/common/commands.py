"""Present existing actions and route editing to exactly one focused owner.

These helpers never hold a document, edit buffer or Undo stack. Window owners
provide their existing callbacks and refresh availability after state changes.
"""
from PySide6.QtCore import QObject, Qt
from PySide6.QtWidgets import QApplication, QMenu, QMenuBar, QToolBar, QToolButton
from shiboken6 import isValid


def action_button(action, parent=None, *, primary=False):
    """Expose the same QAction used by a menu, context menu and shortcut."""
    button = QToolButton(parent)
    button.setProperty('caeCommandButton', True)
    button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
    button.setDefaultAction(action)
    if primary:
        button.setProperty('appearanceRole', 'primary')
    return button


class FocusedUndoRedo(QObject):
    """Connect previously unconnected Undo/Redo actions to focused editors.

    Register each owner root with its callbacks and availability getters. Nested
    editors win over enclosing roots. Menu/toolbar focus keeps the last editor;
    deleted, hidden or disabled roots cannot receive a command. Keep the native
    cell editor's ShortcutOverride behavior; it can handle a local keystroke
    without triggering these actions. Call refresh() after owner state changes.
    """
    def __init__(self, window, undo_action, redo_action):
        super().__init__(window)
        self.window = window
        self.undo_action, self.redo_action = undo_action, redo_action
        self._targets = []
        self._current = None
        self._invoking = False
        self._refreshing = False
        undo_action.triggered.connect(self._undo)
        redo_action.triggered.connect(self._redo)
        QApplication.instance().focusChanged.connect(self._focus_changed)
        self.refresh()

    def register_target(self, widget, *, undo, redo, can_undo, can_redo, label=''):
        """Register a QWidget root; replacing that root retains one binding."""
        self._targets = [target for target in self._targets
                         if isValid(target['widget']) and target['widget'] is not widget]
        target = dict(widget=widget, undo=undo, redo=redo, can_undo=can_undo,
                      can_redo=can_redo, label=label)
        self._targets.append(target)
        if self._current is None or self._current['widget'] is widget:
            self._current = target
        self.refresh()

    def _focus_changed(self, _old, new):
        if self._refreshing:
            return
        if new is not None and isValid(new):
            candidate = new
            while candidate is not None:
                if (candidate.property('caeCommandButton') or
                        isinstance(candidate, (QMenu, QMenuBar, QToolBar))):
                    self.refresh()
                    return
                candidate = candidate.parentWidget()
            # Walk up from the focus widget so the nearest registered root wins.
            candidate = new
            while candidate is not None:
                target = next((item for item in self._targets
                               if isValid(item['widget']) and item['widget'] is candidate), None)
                if target is not None:
                    self._current = target
                    target['focus'] = new
                    break
                candidate = candidate.parentWidget()
        self.refresh()

    def _available(self, target):
        widget = target['widget']
        return isValid(widget) and widget.isEnabled() and widget.isVisibleTo(self.window)

    def refresh(self):
        """Update the same menu/toolbar actions without changing owner state."""
        if self._refreshing:
            return
        self._targets = [item for item in self._targets if isValid(item['widget'])]
        if self._current not in self._targets or not self._current['widget'].isVisibleTo(self.window):
            self._current = next((item for item in self._targets if self._available(item)), None)
        target = self._current
        label = target['label'] if target else ''
        label = label() if callable(label) else label
        focus = QApplication.focusWidget()
        self._refreshing = True
        try:
            for action, command, text in ((self.undo_action, 'undo', '실행 취소'),
                                          (self.redo_action, 'redo', '다시 실행')):
                action.setText(f'{label}: {text}' if label else text)
                action.setIconText(text)
                action.setEnabled(bool(target and self._available(target)
                                       and target['can_' + command]()))
            # Disabling a focused command button otherwise jumps to another
            # owner and silently changes the next menu Undo's target.
            previous = target.get('focus') if target else None
            if (focus is not None and isValid(focus) and focus.property('caeCommandButton')
                    and not focus.isEnabled() and previous is not None and isValid(previous)
                    and previous.isEnabled() and previous.isVisibleTo(self.window)):
                previous.setFocus()
        finally:
            self._refreshing = False

    def _invoke(self, command):
        if self._invoking:
            return
        self.refresh()
        target = self._current
        if self._invoking or target is None or not self._available(target) or not target['can_' + command]():
            return
        self._invoking = True
        try:
            target[command]()
        finally:
            self._invoking = False
            if isValid(self):
                self.refresh()

    def _undo(self, _checked=False):
        self._invoke('undo')

    def _redo(self, _checked=False):
        self._invoke('redo')
