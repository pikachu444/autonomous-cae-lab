"""Real Qt commands share action state and only the focused editing owner."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
pytest.importorskip('PySide6')
from PySide6.QtCore import QCoreApplication, QEvent, Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMainWindow, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from apps.research.common.commands import action_button, FocusedUndoRedo


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


def test_button_menu_and_shortcut_share_one_action(app):
    window = QMainWindow()
    action = QAction('자료 준비', window)
    action.setShortcut(QKeySequence('Ctrl+R'))
    menu = window.menuBar().addMenu('자료'); menu.addAction(action)
    button = action_button(action, window, primary=True)
    window.setCentralWidget(button)
    calls = []
    action.triggered.connect(lambda: calls.append(True))
    window.show(); window.activateWindow(); app.processEvents()
    try:
        assert button.defaultAction() is menu.actions()[0]
        assert button.property('appearanceRole') == 'primary'
        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        assert calls == [True]
        action.setText('자료 다시 준비'); action.setEnabled(False)
        assert button.text() == '자료 다시 준비' and not button.isEnabled()
        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        QTest.keyClick(window, Qt.Key.Key_R, Qt.KeyboardModifier.ControlModifier)
        assert calls == [True]
        action.setEnabled(True)
        QTest.keyClick(window, Qt.Key.Key_R, Qt.KeyboardModifier.ControlModifier)
        assert calls == [True, True]
        action.setCheckable(True); action.setChecked(True)
        assert button.isCheckable() and button.isChecked()
    finally:
        window.close()


def test_focus_routes_menu_toolbar_and_keyboard_to_one_owner(app):
    window = QMainWindow()
    root = QWidget(); layout = QVBoxLayout(root); window.setCentralWidget(root)
    material = QTableWidget(1, 1); material.setItem(0, 0, QTableWidgetItem('재료'))
    plan = QTableWidget(1, 1); plan.setItem(0, 0, QTableWidgetItem('계획'))
    layout.addWidget(material); layout.addWidget(plan)
    undo, redo = QAction('Undo', window), QAction('Redo', window)
    undo.setShortcut(QKeySequence.Undo); redo.setShortcut(QKeySequence.Redo)
    menu = window.menuBar().addMenu('편집'); menu.addActions([undo, redo])
    button = action_button(undo); layout.addWidget(button)
    router = FocusedUndoRedo(window, undo, redo)
    calls = []
    state = {'material': True, 'plan': True}
    router.register_target(root, undo=lambda: calls.append('material undo'),
        redo=lambda: calls.append('material redo'), can_undo=lambda: state['material'],
        can_redo=lambda: False, label='재료')
    router.register_target(plan, undo=lambda: calls.append('plan undo'),
        redo=lambda: calls.append('plan redo'), can_undo=lambda: state['plan'],
        can_redo=lambda: True, label=lambda: '선택 계획')
    window.show(); window.activateWindow(); app.processEvents()
    try:
        plan.setFocus(); app.processEvents()
        assert undo.text() == '선택 계획: 실행 취소' and redo.isEnabled()
        QTest.keyClick(plan, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
        assert calls == ['plan undo']
        button.setFocus(); app.processEvents()
        QTest.keyClick(button, Qt.Key.Key_Space)
        assert calls == ['plan undo', 'plan undo']
        redo.trigger()
        assert calls[-1] == 'plan redo'
        state['plan'] = False; router.refresh()
        assert not undo.isEnabled() and not button.isEnabled()
        undo.trigger()
        assert calls == ['plan undo', 'plan undo', 'plan redo']
        material.setFocus(); app.processEvents()
        assert undo.text() == '재료: 실행 취소' and undo.isEnabled() and not redo.isEnabled()
        undo.trigger()
        assert calls[-1] == 'material undo'
        button.setFocus(); app.processEvents(); plan.setFocus(); app.processEvents()
        plan.setEnabled(False); router.refresh()
        assert router._current['widget'] is not plan or not undo.isEnabled()
        plan.setEnabled(True); plan.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        router.refresh()
        assert undo.text() == '재료: 실행 취소'
    finally:
        window.close()


def test_reentrant_undo_and_replaced_target_do_not_duplicate_commands(app):
    window = QMainWindow(); root = QWidget(); window.setCentralWidget(root)
    undo, redo = QAction(window), QAction(window)
    router = FocusedUndoRedo(window, undo, redo)
    calls = []
    def command():
        calls.append(True)
        undo.trigger()  # Reentrant command activation cannot edit twice.
    router.register_target(root, undo=command, redo=lambda: None,
        can_undo=lambda: True, can_redo=lambda: False)
    window.show(); app.processEvents()
    try:
        undo.trigger()
        assert calls == [True]
        router.register_target(root, undo=lambda: calls.append(False), redo=lambda: None,
            can_undo=lambda: True, can_redo=lambda: False)
        undo.trigger()
        assert calls == [True, False]
    finally:
        window.close()


def test_owner_destruction_ignores_late_focus_and_command_refresh(app):
    from shiboken6 import isValid
    window = QMainWindow()
    root = QWidget(); window.setCentralWidget(root)
    undo, redo = QAction(window), QAction(window)
    router = FocusedUndoRedo(window, undo, redo)
    calls = []
    router.register_target(root, undo=lambda: calls.append('undo'), redo=lambda: calls.append('redo'),
        can_undo=lambda: True, can_redo=lambda: True)
    target = router._targets[0]
    window.show(); app.processEvents()
    window.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert not isValid(window)
    survivor = QWidget()
    try:
        survivor.show(); survivor.setFocus(); app.processEvents()
        router._focus_changed(None, survivor)
        router.refresh()
        assert not router._available(target)
        assert calls == []
    finally:
        survivor.close()
