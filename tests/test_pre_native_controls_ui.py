"""Real Qt native-menu guards, with controlled FreeCAD/transport doubles."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from copy import deepcopy
from pathlib import Path
import sys
from types import MethodType, SimpleNamespace as NS

import pytest

QtCore = pytest.importorskip('PySide6.QtCore')
QtGui = pytest.importorskip('PySide6.QtGui')
QtWidgets = pytest.importorskip('PySide6.QtWidgets')
from PySide6.QtTest import QTest

from apps.desktop_pre.native_controls import install
from apps.desktop_pre.bridge import Owner


@pytest.fixture(scope='module')
def app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture
def controls(app, tmp_path, monkeypatch):
    # FreeCAD supplies PySide; use the real Qt binding available to portable CI.
    monkeypatch.setitem(sys.modules, 'PySide', NS(QtGui=QtGui))
    main = QtWidgets.QMainWindow()
    main.setCentralWidget(QtWidgets.QWidget())
    menu = main.menuBar().addMenu('File')
    original_calls, native_documents, owners = [], {}, []
    for name in ('One', 'Two', 'Three'):
        document = NS(Name=name, Label='Native ' + name)
        owner = NS(doc=document, document_id='P' + name, session_id='S' + name,
            generation=10, saved_generation=9,
            project=NS(path=tmp_path / (name + '.caepre')), export_root=tmp_path,
            closed=False, preview=True, calls=[], block_reason=None)
        def before(reason, owner=owner):
            owner.calls.append(reason)
            if owner.block_reason:
                raise ValueError(owner.block_reason)
            owner.preview = False
        owner.before_design_action = before
        owner.assert_thread = owner.refresh = owner._idle = lambda: None
        owner.completed, owner.view_generation = {}, 0
        owner.fem = NS(_pending={})
        owner.descriptor = lambda owner=owner: {'id': owner.document_id, 'generation': owner.generation}
        owner.dispatch = MethodType(Owner.dispatch, owner)
        owners.append(owner)
        native_documents[name] = NS(Modified=True)
    actions = {}
    for name, text in [('Std_Save', 'Native Save'), ('Std_CloseAll', 'Native Close All'), ('Std_Close', 'Native Close')]:
        action = QtGui.QAction(text, main)
        action.setObjectName(name)
        if name == 'Std_Save':
            action.setShortcut(QtGui.QKeySequence('Ctrl+S'))
        action.triggered.connect(lambda checked=False, name=name: original_calls.append(name))
        menu.addAction(action)
        actions[name] = action
    after_action = menu.addAction('Unchanged following action')
    connection = NS(QtCore=QtCore, QtWidgets=QtWidgets,
        Gui=NS(getMainWindow=lambda: main, getDocument=lambda name: native_documents[name]), App=NS(),
        owners={owner.doc.Name: (owner, None, None) for owner in owners},
        message=QtWidgets.QLabel(main), active_owner=lambda: owners[0], show_panel=lambda kind: None,
        pending=[], calls=[])
    def submit(operation, arguments, target=None, on_done=None, *, owner=None):
        request = {'operation': operation, 'arguments': deepcopy(arguments), 'target': deepcopy(target),
                   'owner': owner or connection.active_owner(), 'callback': on_done,
                   'generation': (owner or connection.active_owner()).generation}
        connection.calls.append(request)
        connection.pending.append(request)
        return {'queued': True}
    connection.submit_native = submit
    def complete(*, success=True, late_edit=False):
        request = connection.pending.pop(0)
        owner = request['owner']
        def native_save():
            if not success:
                raise OSError('Controlled publication failure')
            owner.saved_generation = owner.generation
            return {'revision': 'Rcontrolled'}
        owner.project.save = native_save
        # Execute the real typed owner dispatch against GUI-shaped objects.
        # Only the file-publication boundary is controlled; the UI does not
        # directly restore a pose or assign a saved generation.
        receipt = owner.dispatch({'command_id': 'Csave' + str(len(connection.calls)),
            'document_id': owner.document_id, 'session_id': owner.session_id,
            'expected_generation': request['generation'], 'operation': request['operation'],
            'arguments': request['arguments'], 'target': request['target'] or {}})
        if late_edit:
            owner.generation += 1
        request['callback'](receipt)
    guard = install(connection, lambda: None)
    context = NS(main=main, menu=menu, actions=actions, following=after_action, guards=guard,
        connection=connection, owners=owners, native_documents=native_documents,
        originals=original_calls, complete=complete)
    yield context
    app.removeEventFilter(guard)
    guard.closing = False
    connection.owners.clear()
    main.close()
    main.deleteLater()
    app.processEvents()


def questions(monkeypatch, choices):
    replies = iter(choices)
    seen = []
    def question(parent, title, text, *args):
        seen.append(text)
        return next(replies)
    monkeypatch.setattr(QtWidgets.QMessageBox, 'question', question)
    return seen


def test_native_save_action_replacement_preserves_order_shortcut_and_uses_async_owner(controls):
    c = controls
    original, proxy = c.guards.replacements['Std_Save']
    assert original is c.actions['Std_Save']
    assert original not in c.menu.actions() and proxy is c.menu.actions()[0]
    assert not original.shortcuts() and proxy.shortcut().toString() == 'Ctrl+S'
    proxy.trigger()
    assert c.originals == []
    assert len(c.connection.pending) == 1
    assert c.connection.calls[0]['operation'] == 'document.save'
    assert c.owners[0].preview and c.native_documents['One'].Modified
    c.complete()
    assert c.owners[0].calls == ['document.save'] and not c.owners[0].preview
    assert not c.native_documents['One'].Modified


def test_rebuilt_same_name_native_save_action_is_replaced_in_every_live_menu(controls):
    c = controls
    proxy = c.guards.replacements['Std_Save'][1]
    rebuilt_menu = c.main.menuBar().addMenu('Rebuilt File')
    rebuilt = QtGui.QAction('Rebuilt native Save', c.main)
    rebuilt.setObjectName('Std_Save'); rebuilt.setShortcut(QtGui.QKeySequence('Ctrl+Shift+S'))
    rebuilt.triggered.connect(lambda: c.originals.append('unmanaged rebuilt Save'))
    rebuilt_menu.addAction(rebuilt)
    tail = rebuilt_menu.addAction('Rebuilt following action')
    c.guards.refresh()
    assert rebuilt_menu.actions() == [proxy, tail]
    assert c.menu.actions()[0] is proxy
    assert not rebuilt.shortcuts() and not c.actions['Std_Save'].shortcuts()
    assert proxy.shortcut().toString() == 'Ctrl+Shift+S'
    proxy.trigger(); c.complete()
    assert len(c.connection.calls) == 1 and c.originals == []


def test_close_all_discard_then_cancel_keeps_every_document_modified(controls, monkeypatch):
    c = controls
    seen = questions(monkeypatch, [QtWidgets.QMessageBox.Discard, QtWidgets.QMessageBox.Cancel])
    c.guards.replacements['Std_CloseAll'][1].trigger()
    assert len(seen) == 2 and not c.guards.closing
    assert c.originals == [] and c.connection.calls == []
    assert all(document.Modified for document in c.native_documents.values())
    assert c.guards.approved_close == {}
    assert c.owners[0].calls == ['close'] and c.owners[1].calls == ['close']
    assert not c.owners[0].preview and not c.owners[1].preview


def test_close_all_save_discard_then_cancel_keeps_unpublished_documents_modified(controls, monkeypatch):
    c = controls
    seen = questions(monkeypatch, [QtWidgets.QMessageBox.Save, QtWidgets.QMessageBox.Discard, QtWidgets.QMessageBox.Cancel])
    c.guards.replacements['Std_CloseAll'][1].trigger()
    assert c.guards.closing and len(c.connection.pending) == 1
    assert all(document.Modified for document in c.native_documents.values())
    c.complete()
    assert len(seen) == 3 and not c.guards.closing
    assert not c.native_documents['One'].Modified  # This document was explicitly saved.
    assert c.native_documents['Two'].Modified and c.native_documents['Three'].Modified
    assert c.guards.approved_close == {} and c.originals == []
    assert c.owners[0].calls == ['close', 'document.save']


def test_close_save_failure_keeps_dirty_state_and_does_not_continue_close(controls, monkeypatch):
    c = controls
    questions(monkeypatch, [QtWidgets.QMessageBox.Save])
    c.guards.replacements['Std_Close'][1].trigger()
    c.complete(success=False)
    assert not c.guards.closing and c.native_documents['One'].Modified
    assert c.guards.approved_close == {} and c.originals == []
    assert 'Controlled publication failure' in c.connection.message.text()


def test_late_native_edit_after_save_receipt_cannot_be_silently_approved_for_close(controls, monkeypatch):
    c = controls
    questions(monkeypatch, [QtWidgets.QMessageBox.Save])
    c.guards.replacements['Std_Close'][1].trigger()
    c.complete(late_edit=True)
    assert c.owners[0].saved_generation != c.owners[0].generation
    assert c.native_documents['One'].Modified
    assert c.originals == [] and c.guards.approved_close == {}
    assert not c.guards.closing


def test_actual_close_event_cancel_preserves_window_and_dirty_state(controls, monkeypatch, app):
    c = controls
    questions(monkeypatch, [QtWidgets.QMessageBox.Discard, QtWidgets.QMessageBox.Cancel])
    c.main.show(); app.processEvents()
    assert c.main.isVisible()
    assert not c.main.close()
    assert c.main.isVisible()
    assert all(document.Modified for document in c.native_documents.values())
    assert c.guards.approved_close == {} and not c.guards.closing


def test_edit_during_later_close_prompt_cannot_extend_an_earlier_discard_approval(controls, monkeypatch):
    c = controls
    c.connection.owners.pop('Three')
    calls = []
    def question(parent, title, text, *args):
        calls.append(text)
        if len(calls) == 2:
            # A real modal Qt dialog processes events; another native document
            # can receive an edit after its earlier explicit discard decision.
            c.owners[0].generation += 1
            c.native_documents['One'].Modified = True
        return QtWidgets.QMessageBox.Discard
    monkeypatch.setattr(QtWidgets.QMessageBox, 'question', question)
    c.guards.replacements['Std_CloseAll'][1].trigger()
    assert len(calls) == 2
    assert c.originals == [] and c.guards.approved_close == {}
    assert c.native_documents['One'].Modified and c.native_documents['Two'].Modified
    assert not c.guards.closing


def test_fem_workbench_keyboard_switch_restores_design_pose_before_native_selector_changes(controls, app):
    c = controls
    selector = QtWidgets.QComboBox(c.main)
    selector.addItem('Part', 'PartWorkbench'); selector.addItem('FEM', 'FemWorkbench')
    c.main.centralWidget().setLayout(QtWidgets.QVBoxLayout())
    c.main.centralWidget().layout().addWidget(selector)
    c.main.show(); selector.setFocus(); app.processEvents()
    QTest.keyClick(selector, QtCore.Qt.Key_Down)
    assert 'workbench switch' in c.owners[0].calls and not c.owners[0].preview
    assert selector.currentData() == 'FemWorkbench'


def test_fem_workbench_guard_failure_blocks_selector_change_and_shows_reason(controls, app):
    c = controls
    c.owners[0].block_reason = 'MESH_BUSY: native mesh generation is still applying'
    selector = QtWidgets.QComboBox(c.main)
    selector.addItem('Part', 'PartWorkbench'); selector.addItem('FEM', 'FemWorkbench')
    c.main.centralWidget().setLayout(QtWidgets.QVBoxLayout())
    c.main.centralWidget().layout().addWidget(selector)
    c.main.show(); selector.setFocus(); app.processEvents()
    QTest.keyClick(selector, QtCore.Qt.Key_Down)
    assert selector.currentData() == 'PartWorkbench'
    assert 'MESH_BUSY' in c.connection.message.text() and c.owners[0].preview


def attach_editor(c, owner, *, version=1):
    state = {'version': version, 'saved': 0}
    controller = NS(editor_token=lambda: state['version'], has_unsaved_editor=lambda: state['version'] != state['saved'])
    if not hasattr(c.connection, 'panels'): c.connection.panels = {}
    c.connection.panels[owner.doc.Name] = {'motion': NS(widget=lambda: NS(motion_controller=controller))}
    return state


def test_saved_native_document_with_local_raw_draft_still_prompts_before_close(controls, monkeypatch):
    c = controls; owner = c.owners[0]; owner.saved_generation = owner.generation
    state = attach_editor(c, owner)
    seen = questions(monkeypatch, [QtWidgets.QMessageBox.Cancel])
    c.guards.replacements['Std_Close'][1].trigger()
    assert len(seen) == 1 and not c.originals and state['version'] == 1 and not c.guards.closing


def test_close_all_cancel_preserves_distinct_local_editor_buffers(controls, monkeypatch):
    c = controls
    states = [attach_editor(c, owner, version=i+1) for i, owner in enumerate(c.owners)]
    questions(monkeypatch, [QtWidgets.QMessageBox.Discard, QtWidgets.QMessageBox.Cancel])
    c.guards.replacements['Std_CloseAll'][1].trigger()
    assert [s['version'] for s in states] == [1, 2, 3]
    assert not c.originals and not c.guards.approved_close


def test_late_editor_edit_after_file_save_cannot_close_document(controls, monkeypatch):
    c = controls; state = attach_editor(c, c.owners[0])
    questions(monkeypatch, [QtWidgets.QMessageBox.Save])
    c.guards.replacements['Std_Close'][1].trigger()
    state.update(saved=1, version=2)
    c.complete()
    assert c.owners[0].saved_generation == c.owners[0].generation
    assert not c.originals and not c.guards.closing and state['version'] == 2


def test_reconnect_cancel_after_discard_preserves_every_editor(controls, monkeypatch):
    c = controls; states = [attach_editor(c, owner, version=i+1) for i, owner in enumerate(c.owners)]
    questions(monkeypatch, [QtWidgets.QMessageBox.Discard, QtWidgets.QMessageBox.Cancel])
    completed = []
    c.guards.prepare_reconnect(c.owners, lambda: completed.append(True))
    assert not completed and not c.guards.closing and [s['version'] for s in states] == [1, 2, 3]


def test_reconnect_save_failure_keeps_editor_and_old_owner(controls, monkeypatch):
    c = controls; state = attach_editor(c, c.owners[0]); completed = []
    questions(monkeypatch, [QtWidgets.QMessageBox.Save])
    c.guards.prepare_reconnect(c.owners, lambda: completed.append(True)); c.complete(success=False)
    assert not completed and not c.guards.closing and state['version'] == 1
    assert c.connection.owners['One'][0] is c.owners[0]
