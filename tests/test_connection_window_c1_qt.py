"""Real C1 QWidget/QTest acceptance. PySide6 absence is NOT_RUN, not a pass.

Uses the real Workbench document owner as the window client. No native activation
or OS mouse claim. Windows runs may set QT_CAPTURE_DIR; no dependency downloads.
"""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from copy import deepcopy
from pathlib import Path
import time

import pytest
PySide6 = pytest.importorskip('PySide6', reason='NOT_RUN: C1 widget/QTest requires existing PySide6')
from PySide6.QtCore import QPoint, QTimer, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QDialogButtonBox, QLabel, QPlainTextEdit

from apps.research.appearance import apply_appearance
from apps.research.connection_window import ConnectionWindow
from apps.research.connection_window_workflows import RelationSelectionDialog, RelationImpactDialog
from caelab.connection_graph import build_graph
from caelab.connection_graph_edit import target_selection, preview_edit, source_selection
from caelab.connection_graph_view import read_view
from caelab.evaluation import file_hash
from examples.portable_connection_public import create_public_store, command


@pytest.fixture(scope='module')
def app():
    instance = QApplication.instance() or QApplication([])
    apply_appearance(instance)
    return instance


def spin(app, predicate, seconds=8):
    blocked = []
    watchdog = QTimer()
    watchdog.setSingleShot(True)
    def release_failed_modal():
        # A nested exec() otherwise prevents the polling deadline from running.
        modal = QApplication.activeModalWidget()
        if isinstance(modal, QDialog):
            text = [widget.text() for widget in modal.findChildren(QLabel)]
            text += [widget.toPlainText() for widget in modal.findChildren(QPlainTextEdit)]
            blocked.append({'dialog': modal.windowTitle(), 'text': '\n'.join(text)})
            modal.reject()
    watchdog.timeout.connect(release_failed_modal)
    watchdog.start(round(seconds * 1000))
    try:
        end = time.monotonic()+seconds
        while time.monotonic()<end:
            # Yield Python workers as the real app.exec() loop does while idle.
            app.processEvents(); time.sleep(.01)
            if predicate() and not blocked: return
        assert predicate() and not blocked, f'Qt worker/modal did not reach expected state: {blocked}'
    finally:
        watchdog.stop()


def documents(wb):
    return {p.relative_to(wb.root).as_posix():file_hash(p) for p in (wb.root/'documents').rglob('*') if p.is_file()}


@pytest.fixture
def view(app,tmp_path):
    wb,docs=create_public_store(tmp_path/'Qt C1 원본')
    window=ConnectionWindow(wb,auto_open=False)
    window.set_graph(build_graph(wb)); window.show(); app.processEvents()
    try: yield window,wb,docs
    finally:
        # Test cleanup only; domain writes are never suppressed during assertions.
        window._layout_timer.stop()
        spin(app,lambda:not window._busy)
        window._layout_dirty=False
        window.close(); app.processEvents(); wb.shutdown()


@pytest.mark.parametrize('size',[(1200,780),(820,600)])
def test_typed_dialog_actual_escape_and_sizes(app,view,size):
    window,wb,docs=view; window.resize(*size); app.processEvents()
    before=documents(wb)
    catalog=wb.connection_catalog(docs['plan']['id'])
    dialog=RelationSelectionDialog(catalog,'repair',port='material',parent=window)
    dialog.show(); app.processEvents()
    assert dialog.port.currentData()['port']=='material'
    assert dialog.source.count()>=1 and dialog.buttons.button(QDialogButtonBox.StandardButton.Ok).isEnabled()
    request=dialog.request()
    QTest.keyClick(dialog,Qt.Key.Key_Escape); app.processEvents()
    assert dialog.result()==QDialog.DialogCode.Rejected
    proposal=wb.connection_preview(**request)
    impact=RelationImpactDialog(proposal,parent=window); impact.show(); app.processEvents()
    assert docs['material']['title'] in impact.content.toPlainText()
    QTest.keyClick(impact,Qt.Key.Key_Escape); app.processEvents()
    assert impact.result()==QDialog.DialogCode.Rejected and documents(wb)==before
    capture=os.environ.get('QT_CAPTURE_DIR')
    if capture:
        folder=Path(capture);folder.mkdir(parents=True,exist_ok=True)
        window.tabs.setCurrentIndex(0);app.processEvents()
        assert window.grab().save(str(folder/f'c1-window-{size[0]}x{size[1]}.png'))


def drive_dialogs(window, *, confirm=True):
    """Actual dialog buttons inside the Qt nested event loop, no monkeypatched exec."""
    # Catalog and preview perform real retained-file checks before opening a dialog.
    # Keep this driver alive for the same bounded wait used by the test below.
    started=time.monotonic();deadline=started+20
    seen=[]
    def advance():
        modal=QApplication.activeModalWidget()
        if isinstance(modal,RelationSelectionDialog) and 'selection' not in seen:
            seen.append('selection')
            print(f'Qt relation selection after {time.monotonic()-started:.3f}s', flush=True)
            QTest.mouseClick(modal.buttons.button(QDialogButtonBox.StandardButton.Ok),Qt.MouseButton.LeftButton)
        elif isinstance(modal,RelationImpactDialog) and 'impact' not in seen:
            seen.append('impact')
            print(f'Qt relation impact after {time.monotonic()-started:.3f}s', flush=True)
            if confirm: QTest.mouseClick(modal.buttons.button(QDialogButtonBox.StandardButton.Ok),Qt.MouseButton.LeftButton)
            else: QTest.keyClick(modal,Qt.Key.Key_Escape)
        if time.monotonic()<deadline and ('impact' not in seen): QTimer.singleShot(20,advance)
    QTimer.singleShot(20,advance)
    return seen


def test_shared_menu_keyboard_cancel_then_unlink_then_add(app,view):
    window,wb,docs=view; planid=docs['plan']['id']
    node=next(r for r in window.rows.values() if r['node_type']=='reference' and r['consumer_id']==planid and r['path']==['draft','material'])
    # Window shortcuts require an active top-level window on Windows.
    window.activateWindow()
    assert QTest.qWaitForWindowActive(window, 1500)
    spin(app,lambda:not window._busy)
    window.select_key(node['key']);window.tabs.setCurrentIndex(1);window.table.setFocus()
    assert window.isActiveWindow() and window.table.hasFocus()
    assert window.unlink_action.isEnabled()
    before=documents(wb); seen=drive_dialogs(window,confirm=False)
    QTest.keyClick(window.table,Qt.Key.Key_Delete,Qt.KeyboardModifier.ControlModifier)
    spin(app,lambda:'impact' in seen and not window._busy and window._link_choice is None,seconds=20)
    assert documents(wb)==before
    seen=drive_dialogs(window)
    window.unlink_action.trigger()
    spin(app,lambda:'impact' in seen and not window._busy and wb.document_read(planid)['draft']['material'] is None,seconds=20)
    window.select_key('document/'+planid)
    assert window.add_link_action.isEnabled()
    seen=drive_dialogs(window)
    window.add_link_action.trigger()
    spin(app,lambda:'impact' in seen and not window._busy and wb.document_read(planid)['draft']['material'] is not None,seconds=20)
    assert wb.document_read(planid)['draft']['material']['document_id']==docs['material']['id']
    assert len(wb.manager.list())==2 and wb._assistance is None


def test_real_drag_persist_filter_selection_and_new_window_resume(app,view):
    window,wb,docs=view
    window.tabs.setCurrentIndex(0)
    key='document/'+docs['material']['id']; item=window.items[key]
    window.view.ensureVisible(item);app.processEvents()
    before=documents(wb);position=item.pos()
    start=window.view.mapFromScene(item.sceneBoundingRect().center())
    QTest.mousePress(window.view.viewport(),Qt.MouseButton.LeftButton,pos=start)
    QTest.mouseMove(window.view.viewport(),start+QPoint(25,15),20)
    QTest.mouseMove(window.view.viewport(),start+QPoint(50,40),20)
    QTest.mouseRelease(window.view.viewport(),Qt.MouseButton.LeftButton,pos=start+QPoint(50,40))
    app.processEvents();assert item.pos()!=position
    moved=item.pos();window.select_key(key)
    window.search.setText('재료'); window.tabs.setCurrentIndex(1)
    window._layout_timer.stop();window.save_layout()
    spin(app,lambda:not window._busy and not window._layout_dirty)
    state=read_view(wb)['state'];assert state['positions'][state['selected']]==[moved.x(),moved.y()]
    assert documents(wb)==before
    other=ConnectionWindow(wb,auto_open=False)
    try:
        other.set_graph(build_graph(wb));other.show();app.processEvents()
        assert other.selected_key==key and other.items[key].pos()==moved
        assert other.search.text()=='재료' and other.tabs.currentIndex()==1
        assert documents(wb)==before
    finally:
        other._layout_timer.stop();other._layout_dirty=False;other.close();app.processEvents()


def test_stale_cas_error_keeps_selected_source_and_retry_receipt(app,view,monkeypatch):
    window,wb,docs=view;planid=docs['plan']['id'];key='document/'+planid
    source=source_selection(wb,docs['material']['id'])
    proposal=preview_edit(wb,target_selection(wb,planid),'material','repair',source)
    window.select_key(key)
    window._link_choice={'target_id':planid,'action':'repair','port':'material','source':source}
    pending={'proposal':proposal,'confirmed':True,'command_id':'Cstale_qt'}
    window._link_pending=deepcopy(pending)
    draft=deepcopy(docs['plan']['draft']);draft['seed']+=1
    command(wb,docs['plan'],'numerical.update',{'draft':draft})
    before=documents(wb); errors=[]
    monkeypatch.setattr(window,'_text_dialog',lambda title,text:errors.append((title,text)))
    window.retry_relation();spin(app,lambda:not window._busy)
    assert errors and window._link_pending==pending and window._link_choice['source']==source
    assert window.selected_key==key and documents(wb)==before
    # Fresh picker preserves the same exact source identity while replacing CAS token.
    fresh=RelationSelectionDialog(wb.connection_catalog(planid),'repair',port='material',prior_source=source,parent=window)
    assert fresh.request()['source']['document_id']==source['document_id']
    fresh.close()
