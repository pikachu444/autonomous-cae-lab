"""Actual Qt event/geometry checks. Missing PySide6 is a SKIP, never a GUI pass.

Set QT_CAPTURE_DIR to retain real QWidget captures. No hand-drawn mock images.
Callbacks below test navigation contracts, not FreeCAD/ParaView activation.
"""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import json
from pathlib import Path
from copy import deepcopy
import threading
import time

import pytest
PySide6 = pytest.importorskip('PySide6', reason='PySide6 unavailable; Qt visual and interaction checks NOT EXECUTED')
from PySide6.QtCore import QPoint, Qt, QTimer, qVersion
from PySide6.QtGui import QTextLayout
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialogButtonBox

from apps.research.appearance import apply_appearance
from apps.research.connection_window import ConnectionWindow, CopyReviewDialog
from caelab.connection_graph import build_graph
from caelab.evaluation import file_hash
from caelab.portable_project import inspect_copy
from examples.portable_connection_public import create_public_store


@pytest.fixture(scope='module')
def app():
    application = QApplication.instance() or QApplication([])
    apply_appearance(application)
    return application


@pytest.fixture
def view(app, tmp_path):
    wb, docs = create_public_store(tmp_path / 'Qt 공개 자료')
    opened, references = [], []
    class NoNetwork:
        def __getattr__(self, name):
            raise AssertionError('Unexpected network/write call: ' + name)
    window = ConnectionWindow(NoNetwork(), auto_open=False, open_owner=opened.append,
                              open_reference=references.append, persist_view=False)
    window.set_graph(build_graph(wb))
    window.show(); app.processEvents()
    try:
        yield window, wb, docs, opened, references
    finally:
        window._writing = False
        window.close(); app.processEvents(); wb.shutdown()


def files(wb):
    runtime_lock = wb.workspace / 'workbench' / 'controller.lock'
    return {p.relative_to(wb.workspace).as_posix():
            (('runtime-lock', p.stat().st_size, p.stat().st_mtime_ns) if p == runtime_lock else file_hash(p))
            for p in wb.workspace.rglob('*') if p.is_file()}


@pytest.mark.parametrize('size', [(1200, 780), (820, 600)])
def test_actual_two_sizes_selection_korean_and_captures(app, view, size):
    window, wb, docs, opened, references = view
    before = files(wb)
    window.resize(*size); app.processEvents()
    key = 'document/' + docs['material']['id']
    window.select_key(key)
    assert window.owner_action.isEnabled() and window.reference_action.isEnabled()
    assert window.table.selectedItems()[0].data(Qt.ItemDataRole.UserRole) == key
    assert window.centralWidget().width() >= 350 and window.centralWidget().height() >= 350
    window.tabs.setCurrentIndex(1); window.table.setFocus(); app.processEvents()
    QTest.keyClick(window.table, Qt.Key.Key_Return)
    assert opened[-1]['owner_id'] == docs['material']['id']
    QTest.keyClick(window.table, Qt.Key.Key_Return, Qt.KeyboardModifier.ControlModifier)
    assert references[-1] == window.rows[key]['exact_reference']
    window.search.setFocus(); QTest.keyClick(window.search, Qt.Key.Key_Tab)
    assert QApplication.focusWidget() is not None
    layout = QTextLayout('한글연결저장복구', app.font())
    layout.beginLayout(); layout.createLine(); layout.endLayout()
    runs = layout.glyphRuns()
    assert runs and all(all(index != 0 for index in run.glyphIndexes()) for run in runs), 'Korean fallback font missing'
    assert files(wb) == before
    capture = os.environ.get('QT_CAPTURE_DIR')
    if capture:
        folder = Path(capture); folder.mkdir(parents=True, exist_ok=True)
        for tab, name in ((0, 'graph'), (1, 'list')):
            window.tabs.setCurrentIndex(tab); app.processEvents()
            assert window.grab().save(str(folder / f'{name}-{size[0]}x{size[1]}.png'))
        (folder / 'qt-environment.json').write_text(json.dumps({'PySide6': PySide6.__version__,
            'Qt': qVersion(), 'platform': QApplication.platformName(), 'font': app.font().family(),
            'native_windows_verified': False}, ensure_ascii=False, indent=2), encoding='utf-8')


def test_real_drag_updates_graph_only_and_persists_on_refresh(app, view):
    window, wb, docs, _, _ = view
    window.tabs.setCurrentIndex(0)
    window.fit_graph()
    key = 'document/' + docs['material']['id']
    item = window.items[key]
    window.view.ensureVisible(item); app.processEvents()
    before, position = files(wb), item.pos()
    start = window.view.mapFromScene(item.sceneBoundingRect().center())
    QTest.mousePress(window.view.viewport(), Qt.MouseButton.LeftButton, pos=start)
    QTest.mouseMove(window.view.viewport(), start + QPoint(25, 18), 20)
    QTest.mouseMove(window.view.viewport(), start + QPoint(55, 38), 20)
    QTest.mouseRelease(window.view.viewport(), Qt.MouseButton.LeftButton, pos=start + QPoint(55, 38))
    app.processEvents()
    assert item.pos() != position
    moved = item.pos()
    window.set_graph(build_graph(wb)); app.processEvents()
    assert window.items[key].pos() == moved
    assert files(wb) == before


def test_menu_and_broken_reference_have_same_selection(app, view):
    window, wb, docs, opened, references = view
    graph = build_graph(wb)
    row = next(n for n in graph['nodes'] if n['node_type'] == 'reference')
    row.update(status='BROKEN', status_label='참조 끊김', exact_reference=None)
    window.set_graph(graph); window.select_key(row['key'])
    assert not window.reference_action.isEnabled()
    assert window.owner_action.isEnabled()
    window.owner_action.trigger()
    assert opened[-1]['owner_id'] == row['owner_id'] and not references


def test_selected_relations_are_readable_without_rewriting_saved_layout_or_opening(app, view):
    window, wb, docs, opened, references = view
    before = files(wb); positions = deepcopy(window.positions)
    key = 'document/' + docs['material']['id']
    window.select_key(key); app.processEvents()
    related = [edge for edge in window.edges if key in (edge.row['source'], edge.row['target'])]
    visible = [item for item in window.items.values() if item.isVisible()]
    assert len(related) == window.relations.rowCount()
    assert window.focus_action.isChecked()
    assert all(key in (edge.row['source'], edge.row['target']) for edge in window.edges if edge.isVisible())
    for i, item in enumerate(visible):
        assert not any(item.sceneBoundingRect().intersects(other.sceneBoundingRect()) for other in visible[i + 1:])
    assert all(not edge.show_label for edge in window.edges)
    assert window.positions == positions and not opened and not references
    window.relations.selectRow(0); app.processEvents()
    target = window.relations.item(0, 0).data(Qt.ItemDataRole.UserRole)
    assert window.selected_key == key and window.follow_relation.isEnabled()
    assert all(not edge.show_label for edge in window.edges)
    assert sum(edge.relation_selected for edge in window.edges) == 1
    assert all(edge.opacity() <= .15 for edge in window.edges if not edge.relation_selected)
    window.follow_relation.click()
    assert window.selected_key == target and window.table.selectedItems()[0].data(Qt.ItemDataRole.UserRole) == target
    assert not opened and not references
    window.owner_action.trigger()
    assert opened[-1]['owner_id'] == window.rows[target]['owner_id']
    assert files(wb) == before and window.positions == positions


def test_large_arbitrary_graph_keeps_selection_access_and_full_layout(app, view):
    window, wb, _, opened, references = view
    graph = deepcopy(window.graph)
    template = deepcopy(graph['nodes'][0]); anchor = template['key']
    for index in range(55):
        row = deepcopy(template); row.update(key='user-item/' + str(index), owner_id='User' + str(index),
            node_type='reference', label=('사용자가 지정한 매우 긴 한글 자료 이름 ' * 8) + str(index), subtitle='시험 조건 입력',
            status='BROKEN' if index == 7 else 'AVAILABLE', status_label='참조 끊김' if index == 7 else '연결됨')
        graph['nodes'].append(row)
        graph['edges'].append(dict(source=anchor, target=row['key'], label='사용자가 연결한 시험 조건 ' + str(index)))
    original = deepcopy(graph)
    window.set_graph(graph); window.select_key(anchor)
    positions = deepcopy(window.positions)
    for size in ((1440, 900), (1100, 720)):
        window.resize(*size); app.processEvents()
        assert window.relations.rowCount() >= 55 and window.follow_relation.isVisible()
        assert window.relations.viewport().width() >= 350
        window.relations.selectRow(window.relations.rowCount() - 1); window.follow_relation.click()
        assert window.selected_key in window.rows
        assert window.height() <= size[1] and window.selection_caption.height() <= window.selection_caption.maximumHeight()
        assert window.selection_caption.toolTip() == window.rows[window.selected_key]['label']
        window.select_key(anchor)
    window.fit_graph()
    assert all(item.isVisible() for item in window.items.values())
    assert all(edge.isVisible() for edge in window.edges)
    assert set(window.positions) == set(window.items)
    whole = list(window.items.values())
    for i, item in enumerate(whole):
        assert not any(item.sceneBoundingRect().intersects(other.sceneBoundingRect()) for other in whole[i + 1:])
    assert window.positions == positions and graph == original
    assert not opened and not references


def test_copy_review_requires_explicit_approval_and_missing_blocks(app, view):
    window, wb, docs, _, _ = view
    inspection = inspect_copy(wb, [docs[k]['id'] for k in ('data', 'material', 'plan', 'second_plan')])
    dialog = CopyReviewDialog(inspection, window)
    button = dialog.buttons.button(QDialogButtonBox.StandardButton.Save)
    assert not button.isEnabled()
    dialog.approval.setChecked(True); assert button.isEnabled()
    dialog.close()
    inspection['status'] = 'BLOCKED'
    inspection['issues'] = [{'message': '자료 없음', 'location': '공개 원자료/source.csv', 'recovery': '동일 원본 선택'}]
    dialog = CopyReviewDialog(inspection, window)
    dialog.approval.setChecked(True)
    assert not dialog.buttons.button(QDialogButtonBox.StandardButton.Save).isEnabled()
    assert '동일 원본 선택' in dialog.problem.toPlainText()
    dialog.close()


def test_close_write_gate_and_late_read_reply_discarded(app, view):
    window, wb, docs, _, _ = view
    window._writing = True
    assert not window.close() and window.isVisible()
    window._writing = False
    started, release = threading.Event(), threading.Event()
    called = []
    def delayed():
        started.set(); release.wait(5)
        return {'must_not_reach_closed_view': True}
    assert window._call(delayed, called.append)
    assert started.wait(3)
    worker = window._workers[-1]
    try:
        assert window.close()
    finally:
        release.set()
    assert worker.completed.wait(3)
    app.processEvents()
    assert not called and not window._workers


def test_explicit_retained_store_graph_readonly_workflow_and_captures(app, monkeypatch):
    """Opt-in actual saved-store UI read; navigation callbacks do not launch apps."""
    source = os.environ.get('CAELAB_CONNECTION_SAVED_STORE')
    if not source: pytest.skip('Actual retained store was not explicitly selected')
    from caelab.workbench import Workbench
    source = Path(source).resolve()
    assert (source / 'workbench' / 'documents').is_dir()
    def fingerprint():
        return {p.relative_to(source).as_posix(): file_hash(p) for p in source.rglob('*')
                if p.is_file() and p.name != 'controller.lock'}
    before = fingerprint(); wb = Workbench(source); window = None
    opened, references = [], []
    catalogs = []
    class ReadOnly:
        def connection_catalog(self, identifier):
            catalogs.append(identifier)
            return wb.connection_catalog(identifier)
        def __getattr__(self, name): raise AssertionError('Unexpected service mutation: ' + name)
    try:
        jobs = deepcopy(wb.manager.list()); graph = build_graph(wb)
        window = ConnectionWindow(ReadOnly(), auto_open=False, persist_view=False,
                                  open_owner=opened.append, open_reference=references.append)
        window.set_graph(graph); window.show(); app.processEvents()
        candidates = [row for row in graph['nodes'] if row.get('owner_id') and row.get('exact_reference')
                      and row['status'] != 'BROKEN']
        selected = max(candidates, key=lambda row: sum(row['key'] in (edge['source'], edge['target']) for edge in graph['edges']))
        folder = Path(os.environ['QT_CAPTURE_DIR']) if os.environ.get('QT_CAPTURE_DIR') else None
        if folder: folder.mkdir(parents=True, exist_ok=True)
        for width, height, suffix in [(1440, 900, 'normal'), (1100, 780, 'narrow')]:
            window.resize(width, height); window.select_key(selected['key']); window._fit_current_graph(); app.processEvents()
            assert window.owner_action.isEnabled() and window.reference_action.isEnabled()
            assert window.relations.rowCount() > 0 and window.follow_relation.isVisible()
            visible = [item for item in window.items.values() if item.isVisible()]
            for index, item in enumerate(visible):
                assert not any(item.sceneBoundingRect().intersects(other.sceneBoundingRect()) for other in visible[index + 1:])
            assert all(not edge.show_label for edge in window.edges)
            if folder: assert window.grab().save(str(folder / ('connection-' + suffix + '.png')))
            window.relations.selectRow(0); app.processEvents()
            if folder: assert window.grab().save(str(folder / ('connection-relation-' + suffix + '.png')))
            window.follow_relation.click()
            assert window.selected_key in window.rows
            window.select_key(selected['key']); window.owner_action.trigger(); window.reference_action.trigger()
            assert opened[-1]['key'] == selected['key'] and references[-1] == selected['exact_reference']
            window.tabs.setCurrentIndex(1); app.processEvents()
            if folder: assert window.grab().save(str(folder / ('connection-list-' + suffix + '.png')))
            window.tabs.setCurrentIndex(0)
        def cancel():
            modal = QApplication.activeModalWidget()
            if modal: QTest.keyClick(modal, Qt.Key.Key_Escape)
        QTimer.singleShot(50, cancel); window.show_relations()
        assert window.selected_key == selected['key'] and wb.manager.list() == jobs
        repairable = next((row for row in graph['nodes'] if row.get('actions', {}).get('repair', {}).get('enabled')), None)
        cancelled = []
        if repairable:
            from apps.research.connection_window_workflows import RelationSelectionDialog
            timer = QTimer()
            def cancel_selection():
                modal = QApplication.activeModalWidget()
                if isinstance(modal, RelationSelectionDialog):
                    if folder: modal.grab().save(str(folder / 'connection-cancel.png'))
                    cancelled.append(True); QTest.keyClick(modal, Qt.Key.Key_Escape)
                elif modal:
                    modal.reject()
            timer.timeout.connect(cancel_selection); timer.start(25)
            try:
                window.select_key(repairable['key']); window.repair_link_action.trigger()
                deadline = time.monotonic() + 15
                while time.monotonic() < deadline and (window._busy or not cancelled):
                    app.processEvents(); time.sleep(.01)
                assert cancelled and not window._busy and window._link_choice is None
                assert catalogs and not window._link_pending
            finally: timer.stop()
            window.select_key(selected['key'])
        assert wb.manager.list() == jobs
        evidence = dict(platform=QApplication.platformName(),
            documents=sum(row['node_type'] == 'document' for row in graph['nodes']), nodes=len(graph['nodes']),
            edges=len(graph['edges']), selected_key=selected['key'], exact_reference=selected['exact_reference'],
            navigation='controlled exact callbacks; no child app launched', relation_edit_cancelled=bool(cancelled),
            source_unchanged=True, jobs_unchanged=True)
    finally:
        if window:
            window._layout_dirty = False; window.close(); app.processEvents()
        wb.shutdown()
    assert fingerprint() == before
    if folder:
        (folder / 'qt-environment.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding='utf-8')


def test_explicit_retained_store_full_overview_captures(app):
    """Read-only overview delta; no catalog, editor, navigation or copy command."""
    source = os.environ.get('CAELAB_CONNECTION_SAVED_STORE')
    if not source: pytest.skip('Actual retained store was not explicitly selected')
    from caelab.workbench import Workbench
    source = Path(source).resolve()
    def fingerprint():
        return {p.relative_to(source).as_posix(): file_hash(p) for p in source.rglob('*')
                if p.is_file() and p.name != 'controller.lock'}
    before = fingerprint(); wb = Workbench(source); window = None
    class ReadOnly:
        def __getattr__(self, name): raise AssertionError('Overview issued a command: ' + name)
    try:
        jobs = deepcopy(wb.manager.list()); graph = build_graph(wb)
        window = ConnectionWindow(ReadOnly(), auto_open=False, persist_view=False)
        window.set_graph(graph); window.show(); app.processEvents()
        positions = deepcopy(window.positions); selected = window.selected_key
        folder = Path(os.environ['QT_CAPTURE_DIR']) if os.environ.get('QT_CAPTURE_DIR') else None
        if folder: folder.mkdir(parents=True, exist_ok=True)
        for width, height, suffix in [(1440, 900, 'normal'), (1100, 780, 'narrow')]:
            window.resize(width, height); window.fit_graph(); app.processEvents()
            assert all(item.isVisible() for item in window.items.values())
            assert all(edge.isVisible() and not edge.show_label for edge in window.edges)
            whole = list(window.items.values())
            for index, item in enumerate(whole):
                assert not any(item.sceneBoundingRect().intersects(other.sceneBoundingRect()) for other in whole[index + 1:])
            assert window.selected_key == selected and window.positions == positions
            if folder: assert window.grab().save(str(folder / ('connection-overview-' + suffix + '.png')))
            window.focus_action.trigger(); app.processEvents()
            assert window.selected_key == selected and window.positions == positions
            if folder: assert window.grab().save(str(folder / ('connection-first-selection-' + suffix + '.png')))
        assert wb.manager.list() == jobs
    finally:
        if window:
            window._layout_dirty = False; window.close(); app.processEvents()
        wb.shutdown()
    assert fingerprint() == before
