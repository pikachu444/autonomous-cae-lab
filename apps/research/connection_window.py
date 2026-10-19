"""Independent Qt document/revision graph over the existing Workbench service.

python -m apps.research.connection_window --service http://127.0.0.1:8766
The service is shared infrastructure, not a requirement to run a Workbench UI.
Relationship edits delegate to existing owner commands. No calculations are submitted.
"""
from __future__ import annotations
import argparse
from copy import deepcopy
import json
import sys
import uuid
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, QThreadPool, Qt, Slot
from PySide6.QtGui import QAction, QKeySequence, QPalette, QPen
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QCheckBox, QDialog,
    QDialogButtonBox, QDockWidget, QFileDialog, QGraphicsScene, QHeaderView, QLabel,
    QHBoxLayout, QLineEdit, QMainWindow, QMenu, QMessageBox, QPlainTextEdit, QPushButton, QSplitter,
    QTabWidget, QTableWidget, QTableWidgetItem, QToolBar, QTreeWidget,
    QTreeWidgetItem, QVBoxLayout, QWidget)

from caelab.connection_graph import KIND_LABELS
from caelab.workbench_client import Client
from .appearance import apply_appearance
from .connection_window_items import ConnectionEdge, ConnectionNode, ConnectionView
from .expert_window import _Call
from .connection_window_workflows import ConnectionWorkflowMixin

_USER = Qt.ItemDataRole.UserRole


class CopyReviewDialog(QDialog):
    """Review the server-pinned exact inventory; no directory collection here."""
    def __init__(self, inspection, parent=None):
        super().__init__(parent)
        self.setWindowTitle('작업 사본 만들기')
        self.resize(880, 600)
        layout = QVBoxLayout(self)
        names = ', '.join(row['title'] for row in inspection.get('documents', []))
        note = QLabel(('문서에 반영한 초안과 저장본: ' if inspection.get('draft_policy') == 'acknowledged' else '선택한 저장본만: ') + names + '\n'
            '보존 원본과 편집용 사본을 함께 만듭니다. 계산하지 않으며 기존 폴더는 덮어쓰지 않습니다.\n'
            '명시 선택한 보관 원문 '+str(len(inspection.get('recovery_archives',[])))+'개를 함께 옮깁니다. 아직 보관하지 않은 셀은 포함하지 않습니다.')
        if any(row.get('kind') == 'report' for row in inspection.get('documents', [])):
            note.setText(note.text() + '\nReport 창의 미적용 설명은 포함하지 않습니다. 원 창의 「설명 적용」→「저장」 후 다시 검토하세요.')
        note.setWordWrap(True)
        layout.addWidget(note)
        table = QTableWidget(0, 3)
        table.setHorizontalHeaderLabels(['문서', '보존 자료', '크기 (bytes)'])
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        titles = {row['document_id']: row['title'] for row in inspection.get('documents', [])}
        from .portable_research_actions import append_knowledge_rows
        append_knowledge_rows(table, inspection)
        for row in inspection.get('files', []):
            index = table.rowCount(); table.insertRow(index)
            asset = row['asset']
            label = ('문서' if asset == 'document.json' else
                '원자료 연결' if asset.endswith('.navigation.json') else
                '고정 원자료' if asset.startswith('assets/') else
                '문서 연결' if asset.startswith('portable_execution/mappings/') else
                '보존 원본' if asset.startswith('portable_execution/') else
                {'sources': '원자료', 'inputs': '입력', 'jobs': '실행 기록', 'results': '결과',
                 'comparisons': '비교', 'candidate_evidence': '후보 근거'}.get(asset.split('/')[0], '보존 파일'))
            for column, text in enumerate((titles.get(row['document_id'], '문서'), label, str(row['bytes']))):
                item = QTableWidgetItem(text)
                item.setToolTip(asset if column == 1 else text)
                table.setItem(index, column, item)
        for row in inspection.get('recovery_archives', []):
            index = table.rowCount(); table.insertRow(index)
            total = sum(f['bytes'] for f in row['files'])
            state = '삭제 표시 원문' if row['state'] == 'DISCARDED' else '보관 원문·당시 문서·저장 기록'
            for column, text in enumerate((titles.get(row['document_id'], '문서'), state, str(total))):
                table.setItem(index, column, QTableWidgetItem(text))
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(table, 1)
        messages = [row['message'] for row in inspection.get('warnings', [])]
        for issue in inspection.get('issues', []):
            messages.append(issue['message'] + '\n위치: ' + issue['location'] + '\n복구: ' + issue['recovery'])
        self.problem = QPlainTextEdit('\n\n'.join(messages) or '필수 보존 자료가 확인되었습니다.')
        self.problem.setReadOnly(True)
        self.problem.setMaximumHeight(160)
        layout.addWidget(self.problem)
        self.approval = QCheckBox('목록을 확인하고 문헌을 이 작업 사본에서 읽도록 반입합니다.'
            if inspection.get('knowledge') or inspection.get('literature') else '복사할 문서와 보존 파일 목록을 확인했습니다.')
        layout.addWidget(self.approval)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Save).setText('새 폴더에 작업 사본 만들기…')
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('취소')
        self.buttons.button(QDialogButtonBox.StandardButton.Save).setEnabled(False)
        self.approval.toggled.connect(lambda value: self.buttons.button(QDialogButtonBox.StandardButton.Save).setEnabled(
            value and inspection.get('status') == 'READY'))
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)


class ConnectionWindow(ConnectionWorkflowMixin, QMainWindow):
    """Selection/list/graph have one shared action target, never an editable model."""
    def __init__(self, client, *, document_id=None, auto_open=True, open_owner=None, open_reference=None,
                 persist_view=True, copy_draft_policy='acknowledged'):
        super().__init__()
        if copy_draft_policy not in {'acknowledged', 'saved_only'}:
            raise ValueError('알려진 사본 내용 정책을 선택하세요.')
        self._copy_draft_policy = copy_draft_policy
        self.client = client
        self._open_owner, self._open_reference = open_owner, open_reference
        self._initial = document_id
        self._closed = self._busy = self._writing = self._populating = False
        self._workers, self._children = [], []
        self._callback = None
        self.graph, self.error = None, None
        self.selected_key = None
        self.positions, self.items, self.rows = {}, {}, {}
        self.edges = []; self._arranging = False
        self._copy_pending = None
        self.setWindowTitle('연결 보기')
        self.resize(1200, 780)
        self.setMinimumSize(720, 500)
        self._init_workflows(persist_view)
        self._build()
        if auto_open:
            self.refresh()

    def _action(self, menu, text, function, shortcut=None):
        action = QAction(text, self)
        if shortcut:
            action.setShortcut(QKeySequence(shortcut))
        action.triggered.connect(function)
        menu.addAction(action)
        return action

    def _build(self):
        file_menu = self.menuBar().addMenu('파일(&F)')
        self.owner_action = self._action(file_menu, '해당 앱에서 열기', self.open_owner, 'Return')
        self.reference_action = self._action(file_menu, '저장본 열기', self.open_reference, 'Ctrl+Return')
        file_menu.addSeparator()
        self.copy_action = self._action(file_menu, '선택 문서를 새 작업 사본으로…', self.prepare_copy, 'Ctrl+Shift+S')
        if self._copy_draft_policy == 'saved_only':
            self.copy_action.setText('선택 저장본만 새 작업 사본으로…')
        other = 'saved_only' if self._copy_draft_policy == 'acknowledged' else 'acknowledged'
        self.other_copy_action = self._action(file_menu,
            '선택 저장본만 새 작업 사본으로…' if other == 'saved_only' else '현재 반영 초안도 새 작업 사본으로…',
            lambda: self.prepare_copy(draft_policy=other))
        self.retry_copy_action = self._action(file_menu, '사본 생성 응답 확인 / 같은 요청 재시도', self.retry_copy)
        self.verify_action = self._action(file_menu, '작업 사본 확인 / 누락 파일 복구…', self.verify_copy)
        self._action(file_menu, '닫기', self.close, QKeySequence.StandardKey.Close)
        view_menu = self.menuBar().addMenu('보기(&V)')
        self.refresh_action = self._action(view_menu, '연결 새로고침', self.refresh, QKeySequence.StandardKey.Refresh)
        self._action(view_menu, '그래프', lambda: self.tabs.setCurrentIndex(0), 'Alt+1')
        self._action(view_menu, '연결 목록', lambda: self.tabs.setCurrentIndex(1), 'Alt+2')
        self._action(view_menu, '전체 배치 보기', self.fit_graph, 'Ctrl+0')
        self.focus_action = self._action(view_menu, '선택 항목 중심 보기', self._graph_mode_changed)
        self.focus_action.setCheckable(True); self.focus_action.setChecked(True)
        self._action(view_menu, '확대', lambda: self.view.zoom(1.2), 'Ctrl++')
        self._action(view_menu, '축소', lambda: self.view.zoom(1 / 1.2), 'Ctrl+-')
        self._action(view_menu, '선택 항목의 관계', self.show_relations, 'Alt+Return')
        self._action(view_menu, '진단 상세…', self.show_diagnostics)
        self._workflow_menus(file_menu, view_menu)
        toolbar = QToolBar('문서와 연결', self)
        toolbar.setMovable(False)
        self.addToolBar(toolbar)
        for action in (self.owner_action, self.reference_action, self.refresh_action):
            toolbar.addAction(action)
        toolbar.addSeparator(); toolbar.addAction(self.focus_action)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(['포함할 항목', '종류'])
        self.tree.header().setStretchLastSection(False)
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.tree.setAccessibleName('실제 문서 목록과 포함 선택')
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tree.itemSelectionChanged.connect(self._tree_selection)
        self.tree.itemChanged.connect(self._tree_changed)
        self.tree.itemDoubleClicked.connect(lambda *_: self.open_owner())
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(lambda p: self._context(self.tree.viewport().mapToGlobal(p)))
        dock_body = QWidget()
        dock_layout = QVBoxLayout(dock_body)
        self.search = QLineEdit()
        self.search.setPlaceholderText('이름으로 찾기')
        self.search.textChanged.connect(self._filter_tree)
        dock_layout.addWidget(self.search)
        dock_layout.addWidget(self.tree, 1)
        apply = QPushButton('체크한 항목의 연결 보기')
        apply.clicked.connect(self.apply_selection)
        dock_layout.addWidget(apply)
        self.document_dock = QDockWidget('작업과 자료', self)
        self.document_dock.setObjectName('connectionDocumentDock')
        self.document_dock.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea)
        self.document_dock.setWidget(dock_body)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.document_dock)
        self.resizeDocks([self.document_dock], [230], Qt.Orientation.Horizontal)
        view_menu.addAction(self.document_dock.toggleViewAction())
        self.scene = QGraphicsScene(self)
        self.scene.selectionChanged.connect(self._scene_selection)
        self.view = ConnectionView(self.scene, on_open=self.open_owner)
        self.view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.view.customContextMenuRequested.connect(lambda p: self._context(self.view.viewport().mapToGlobal(p)))
        self.selection_caption = QLabel('항목을 선택하면 입력과 결과의 관계가 표시됩니다.')
        self.selection_caption.setWordWrap(True); self.selection_caption.setTextFormat(Qt.TextFormat.PlainText)
        self.selection_caption.setStyleSheet('font-weight:600; padding:4px 2px;')
        self.selection_caption.setMaximumHeight(self.fontMetrics().lineSpacing() * 2 + 14)
        self.relations = QTableWidget(0, 4)
        self.relations.setObjectName('selectedConnections')
        self.relations.setHorizontalHeaderLabels(['방향', '관계', '연결된 항목', '상태'])
        self.relations.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.relations.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.relations.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.relations.verticalHeader().hide(); self.relations.setMinimumHeight(110)
        self.relations.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.relations.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        self.relations.setColumnWidth(1, 170)
        self.relations.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.relations.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.relations.itemSelectionChanged.connect(self._relation_selection)
        self.relations.itemDoubleClicked.connect(lambda *_: self._follow_relation())
        relation_body = QWidget(); relation_layout = QVBoxLayout(relation_body)
        relation_layout.setContentsMargins(0, 0, 0, 0); relation_layout.setSpacing(4)
        relation_bar = QHBoxLayout(); self.relations_caption = QLabel('선택 항목의 관계')
        relation_bar.addWidget(self.relations_caption, 1)
        self.follow_relation = QPushButton('연결 항목 선택'); self.follow_relation.setEnabled(False)
        self.follow_relation.clicked.connect(self._follow_relation); relation_bar.addWidget(self.follow_relation)
        relation_layout.addLayout(relation_bar); relation_layout.addWidget(self.relations)
        self.graph_splitter = QSplitter(Qt.Orientation.Vertical)
        self.graph_splitter.addWidget(self.view); self.graph_splitter.addWidget(relation_body)
        self.graph_splitter.setChildrenCollapsible(False); self.graph_splitter.setSizes([450, 175])
        graph_page = QWidget(); graph_layout = QVBoxLayout(graph_page)
        graph_layout.setContentsMargins(6, 4, 6, 6); graph_layout.setSpacing(4)
        graph_layout.addWidget(self.selection_caption); graph_layout.addWidget(self.graph_splitter, 1)
        self.table = QTableWidget(0, 4)
        self.table.setAccessibleName('그래프와 동일한 연결 목록')
        self.table.setHorizontalHeaderLabels(['작업 / 자료', '종류', '연결 / 상태', '관계'])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.itemSelectionChanged.connect(self._table_selection)
        self.table.itemDoubleClicked.connect(lambda *_: self.open_owner())
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(lambda p: self._context(self.table.viewport().mapToGlobal(p)))
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in (1, 2, 3):
            self.table.horizontalHeader().setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setMinimumSectionSize(80)
        self.tabs = QTabWidget()
        self.tabs.addTab(graph_page, '연결 그래프')
        self.tabs.addTab(self.table, '연결 목록')
        self.setCentralWidget(self.tabs)
        self.tabs.currentChanged.connect(self._mark_layout)
        self.document_dock.visibilityChanged.connect(self._mark_layout)
        self.view.on_view_change = self._mark_layout
        self.message = QLabel('표시할 항목을 체크하고 연결을 확인하세요. 원래 자료는 바뀌지 않습니다.')
        self.message.setWordWrap(True)
        self.statusBar().addWidget(self.message, 1)
        QWidget.setTabOrder(self.search, self.tree)
        QWidget.setTabOrder(self.tree, apply)
        QWidget.setTabOrder(apply, self.tabs)
        self._actions()

    def _call(self, function, callback, *, writing=False):
        if self._busy or self._closed:
            return False
        self._busy, self._writing, self._callback = True, writing, callback
        self.error = None
        self.message.setText('확인한 변경을 기록하고 있습니다. 완료 전에는 이 창을 닫을 수 없습니다.' if writing else '읽는 중…')
        self._actions()
        failures = []
        self._request_failures = failures
        def retained_error():
            try:
                return function()
            except Exception as error:
                failures.append(error)
                raise
        worker = _Call(retained_error)
        self._workers.append(worker)
        worker.signals.finished.connect(self._finished, Qt.ConnectionType.QueuedConnection)
        QThreadPool.globalInstance().start(worker)
        return True

    @Slot(object, object)
    def _finished(self, value, error):
        sender = self.sender()
        self._workers = [worker for worker in self._workers if worker.signals is not sender]
        callback, self._callback = self._callback, None
        original_error = next(iter(getattr(self, '_request_failures', [])), None)
        self._request_failures = []
        self._busy = self._writing = False
        if self._closed:
            return
        self.error = error
        self._actions()
        if error:
            self._workflow_error()
            if callback == self._copy_created and self._copy_pending and self._copy_not_applied(original_error):
                self._copy_pending = None
                self._actions()
                self.message.setText('검토 뒤 원문서가 바뀌어 사본을 만들지 않았습니다. 포함 목록을 다시 확인하세요. 원문서와 편집은 유지됩니다.')
            else:
                self.message.setText('처리하지 못했습니다. 진단 상세와 서비스 연결을 확인하세요.')
            self._text_dialog('처리 실패 — 원문서와 기존 사본은 보존됩니다',
                str(getattr(original_error, 'service_message', error)))
        elif callback:
            callback(value)

    @staticmethod
    def _copy_not_applied(error):
        """Only the service's pre-stage stale-review refusal releases this request."""
        if getattr(error, 'code', None) != 400:
            return False
        try:
            stream = error.fp
            position = stream.tell()
            try:
                stream.seek(0)
                payload = json.loads(error.read().decode('utf-8'))
            finally:
                stream.seek(position)
            issues = payload.get('issues') if isinstance(payload, dict) else None
            return (payload.get('not_applied') is True and isinstance(issues, list) and bool(issues)
                and all(isinstance(row, dict) and row.get('code') == 'STALE_INSPECTION' for row in issues))
        except (AttributeError, OSError, TypeError, ValueError, UnicodeError):
            return False

    def _actions(self):
        row = self.rows.get(self.selected_key, {})
        usable = not self._closed and not self._busy
        self.owner_action.setText('실행 기록 열기' if row.get('node_type') == 'run' else '해당 앱에서 열기')
        self.owner_action.setEnabled(usable and bool(row.get('owner_id') and row.get('owner_kind')))
        self.reference_action.setEnabled(usable and bool(row.get('exact_reference')) and row.get('status') != 'BROKEN')
        can_copy = usable and self._copy_pending is None and bool(self.checked_documents())
        self.copy_action.setEnabled(can_copy)
        self.other_copy_action.setEnabled(can_copy)
        self.retry_copy_action.setEnabled(usable and self._copy_pending is not None)
        self.refresh_action.setEnabled(usable)
        self.verify_action.setEnabled(usable)
        self._workflow_actions(usable, row)

    def checked_documents(self):
        return [self.tree.topLevelItem(i).data(0, _USER) for i in range(self.tree.topLevelItemCount())
                if self.tree.topLevelItem(i).checkState(0) == Qt.CheckState.Checked]

    def _tree_changed(self, *_):
        if not self._populating:
            self._actions()
            self._mark_layout()

    def _filter_tree(self, text):
        for i in range(self.tree.topLevelItemCount()):
            row = self.tree.topLevelItem(i)
            row.setHidden(text.casefold() not in row.text(0).casefold())
        self._mark_layout()

    def refresh(self, *_):
        # Refresh the full document tree, then restore the project's graph filter.
        first = self.graph is None
        wanted = deepcopy((self.graph or {}).get('filter_document_ids'))
        def loaded(value):
            selected = wanted
            if first:
                selected = value.get('view_state', {}).get('state', {}).get('graph_documents')
            self.set_graph(value)
            if selected:
                self._call(lambda: self.client.connection_graph(selected),
                           lambda result: self.set_graph(result, refresh_catalog=False, restore_view=first))
        return self._call(lambda: self.client.connection_graph(), loaded)

    def apply_selection(self):
        chosen = self.checked_documents()
        if not chosen:
            self.message.setText('연결을 볼 문서를 하나 이상 체크하세요.')
            return False
        return self._call(lambda: self.client.connection_graph(chosen), lambda value: self.set_graph(value, refresh_catalog=False))

    def set_graph(self, graph, *, refresh_catalog=True, restore_view=False):
        if not isinstance(graph, dict) or graph.get('format') != 'caelab.connection-graph/1':
            raise ValueError('선택 연결 응답 형식이 다릅니다.')
        self._populating = True
        try:
            checks = set(self.checked_documents())
            initial = self.graph is None
            restored_checks = self._load_graph_view(graph, initial)
            if restored_checks is not None:
                checks = restored_checks
            self.graph = deepcopy(graph)
            self.rows = {r['key']: r for r in graph['nodes']}
            catalog = {self.tree.topLevelItem(i).data(0, _USER): self.tree.topLevelItem(i).text(0)
                       for i in range(self.tree.topLevelItemCount())}
            self.edges = []; self.scene.clear(); self.items = {}
            self.table.setRowCount(0)
            if initial or refresh_catalog:
                self.tree.clear()
            present = {self.tree.topLevelItem(i).data(0, _USER) for i in range(self.tree.topLevelItemCount())}
            columns = [0, 0, 0]
            for index, row in enumerate(graph['nodes']):
                key = row['key']
                if row['node_type'] == 'document' and row.get('owner_id') not in present:
                    tree = QTreeWidgetItem([row['label'], KIND_LABELS.get(row.get('kind'), '문서')])
                    tree.setData(0, _USER, row['owner_id'])
                    tree.setFlags(tree.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                    selected = (row['owner_id'] in checks if restored_checks is not None else
                                row['owner_id'] == self._initial if initial and self._initial else (initial or row['owner_id'] in checks))
                    tree.setCheckState(0, Qt.CheckState.Checked if selected else Qt.CheckState.Unchecked)
                    self.tree.addTopLevelItem(tree)
                    present.add(row['owner_id'])
                item = ConnectionNode(row, self._node_moved)
                self.scene.addItem(item)
                self.items[key] = item
                column = {'document': 0, 'reference': 1}.get(row['node_type'], 2)
                position = self.positions.get(key, QPointF(column * 345., columns[column] * 140.))
                # Qt emits no position change for the origin. Keep every global
                # position before the temporary selection layout is displayed.
                self.positions[key] = QPointF(position)
                item.setPos(position)
                columns[column] += 1
                self.table.insertRow(index)
                relations = sorted({e['label'] for e in graph['edges'] if key in (e['source'], e['target'])})
                for col, text in enumerate((row['label'], KIND_LABELS.get(row['kind'], {'result': '계산 기록', 'source': '원자료', 'reference': '저장 참조'}.get(row['kind'], '문서')),
                                           row['status_label'], ' · '.join(relations))):
                    cell = QTableWidgetItem(text)
                    cell.setToolTip(text)
                    cell.setData(_USER, key)
                    self.table.setItem(index, col, cell)
            for row in graph['edges']:
                if row['source'] in self.items and row['target'] in self.items:
                    edge = ConnectionEdge(self.items[row['source']], self.items[row['target']], row)
                    self.scene.addItem(edge); self.edges.append(edge)
            for edge in self.edges: edge.update_path()
            self.scene.setSceneRect(self.scene.itemsBoundingRect().adjusted(-40, -40, 40, 40))
        finally:
            self._populating = False
        key = self.selected_key if self.selected_key in self.rows else (
            'document/' + self._initial if self._initial and 'document/' + self._initial in self.rows else next(iter(self.rows), None))
        self.select_key(key)
        self._filter_tree(self.search.text())
        if (initial or restore_view) and self._view_base and self._view_base['revision']:
            self.view.resetTransform()
            self.view.scale(self._layout['panel']['zoom'], self._layout['panel']['zoom'])
            self._layout_dirty = False
            self._layout_timer.stop()
        else:
            self._fit_current_graph()
        problems = sum(n['status'] == 'BROKEN' for n in graph['nodes'])
        self.message.setText(f"항목 {len(self.rows)}개 / 연결 {len(graph['edges'])}개 / 끊긴 참조 {problems}개. 현재 작업과 저장본은 별도로 엽니다.")

    def _node_moved(self, key, value):
        if self._arranging: return
        self.positions[key] = QPointF(value)
        # No document command is issued. Positions are not relationship data.
        if not self._populating:
            self.scene.setSceneRect(self.scene.itemsBoundingRect().adjusted(-40, -40, 40, 40))
            self._mark_layout()

    def select_key(self, key):
        if self._populating:
            return
        changed = self.selected_key != key
        self.selected_key = key
        self._populating = True
        try:
            for candidate, item in self.items.items():
                item.setSelected(candidate == key)
            self.table.clearSelection()
            for index in range(self.table.rowCount()):
                if self.table.item(index, 0).data(_USER) == key:
                    self.table.selectRow(index)
                    break
            owner_id = self.rows.get(key, {}).get('owner_id')
            for index in range(self.tree.topLevelItemCount()):
                item = self.tree.topLevelItem(index)
                item.setSelected(item.data(0, _USER) == owner_id)
        finally:
            self._populating = False
        self._actions()
        self._show_graph()
        self._show_relation_rows()
        if key in self.items:
            self.view.ensureVisible(self.items[key], 24, 24)
        if changed:
            self._mark_layout()

    def _scene_selection(self):
        if not self._populating:
            nodes = [n for n in self.scene.selectedItems() if isinstance(n, ConnectionNode)]
            self.select_key(nodes[-1].row['key'] if nodes else None)

    def _table_selection(self):
        if not self._populating and self.table.selectedItems():
            self.select_key(self.table.selectedItems()[0].data(_USER))

    def _tree_selection(self):
        if not self._populating and self.tree.selectedItems():
            self.select_key('document/' + self.tree.selectedItems()[0].data(0, _USER))

    def _context(self, position):
        menu = QMenu(self)
        menu.addAction(self.owner_action)
        menu.addAction(self.reference_action)
        menu.addSeparator()
        menu.addAction(self.add_link_action)
        menu.addAction(self.repair_link_action)
        menu.addAction(self.unlink_action)
        menu.addAction(self.impact_action)
        menu.addAction('관계 확인', self.show_relations)
        menu.exec(position)

    def fit_graph(self):
        self.focus_action.setChecked(False)
        self._show_graph(); self._fit_current_graph()

    def _graph_mode_changed(self, *_):
        self._show_graph(); self._fit_current_graph()

    def _visible_rect(self):
        rect = QRectF()
        for item in self.items.values():
            if item.isVisible(): rect = rect.united(item.sceneBoundingRect())
        return rect.adjusted(-35, -35, 35, 35)

    def _fit_current_graph(self):
        if self.items:
            self.view.fitInView(self._visible_rect(), Qt.AspectRatioMode.KeepAspectRatio)
            # Prefer readable card text plus scrollbars over tiny fit-all text.
            scale = self.view.transform().m11()
            target = min(1.2, max(.85, scale))
            self.view.scale(target / scale, target / scale)
            if self.selected_key in self.items:
                self.view.ensureVisible(self.items[self.selected_key], 24, 24)

    def _show_graph(self):
        focused = self.focus_action.isChecked() and self.selected_key in self.items
        key = self.selected_key
        incoming = sorted({edge.row['source'] for edge in self.edges if edge.row['target'] == key} - {key},
                          key=lambda value: (self.rows[value]['label'], value))
        outgoing = sorted({edge.row['target'] for edge in self.edges if edge.row['source'] == key} - {key} - set(incoming),
                          key=lambda value: (self.rows[value]['label'], value))
        visible = {key, *incoming, *outgoing} if focused else set(self.items)
        temporary = {value: QPointF(0, i * 144) for i, value in enumerate(incoming)}
        temporary.update({value: QPointF(660, i * 144) for i, value in enumerate(outgoing)})
        temporary[key] = QPointF(330, max(0, max(len(incoming), len(outgoing)) - 1) * 72)
        self._arranging = True
        try:
            for value, item in self.items.items():
                item.setVisible(value in visible)
                item.setFlag(item.GraphicsItemFlag.ItemIsMovable, not focused)
                item.setPos(temporary[value] if focused and value in temporary else self.positions.get(value, item.pos()))
            for edge in self.edges:
                related = key in (edge.row['source'], edge.row['target'])
                edge.setVisible(not focused or related)
                pen = QPen(self.palette().color(QPalette.ColorRole.Link) if related else self.palette().mid().color(),
                           2.2 if related else 1.)
                if edge.row.get('status') == 'BROKEN': pen.setStyle(Qt.PenStyle.DashLine)
                edge.setPen(pen); edge.setOpacity(1. if related else .45)
                edge.show_label = False; edge.update_path()
            self.scene.setSceneRect(self._visible_rect())
        finally:
            self._arranging = False

    def _show_relation_rows(self):
        row = self.rows.get(self.selected_key)
        self._selection_caption()
        self.relations.setRowCount(0)
        self.follow_relation.setEnabled(False)
        for edge in self.edges:
            source, target = edge.row['source'], edge.row['target']
            if self.selected_key not in (source, target): continue
            other = target if source == self.selected_key else source
            neighbor = self.rows[other]; index = self.relations.rowCount(); self.relations.insertRow(index)
            values = ('선택 → 항목' if source == self.selected_key else '항목 → 선택', edge.row['label'],
                      neighbor['label'], neighbor['status_label'])
            for column, value in enumerate(values):
                item = QTableWidgetItem(value); item.setToolTip(value); item.setData(_USER, other)
                item.setData(_USER + 1, self.edges.index(edge)); self.relations.setItem(index, column, item)
        self.relations.resizeRowsToContents()
        self.relations_caption.setText('선택 항목의 관계 ' + str(self.relations.rowCount()) + '개' if self.relations.rowCount()
                                       else '연결된 항목이 없습니다.')

    def _selection_caption(self):
        row = self.rows.get(self.selected_key)
        width = max(240, self.view.viewport().width() - 18)
        if row:
            text = self.fontMetrics().elidedText(row['label'], Qt.TextElideMode.ElideMiddle, width)
            text += '\n' + self.fontMetrics().elidedText((row.get('subtitle', '') + ' / ' if row.get('subtitle') else '') +
                                                        row['status_label'], Qt.TextElideMode.ElideRight, width)
            self.selection_caption.setText(text); self.selection_caption.setToolTip(row['label'])
        else:
            self.selection_caption.setText('항목을 선택하세요.'); self.selection_caption.setToolTip('')

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'selection_caption'):
            self._selection_caption()
            if self.selected_key in self.items: self.view.ensureVisible(self.items[self.selected_key], 24, 24)

    def _relation_selection(self):
        selected = self.relations.selectedItems()
        self.follow_relation.setEnabled(bool(selected))
        chosen = selected[0].data(_USER + 1) if selected else None
        for index, edge in enumerate(self.edges):
            edge.relation_selected = index == chosen
            pen = edge.pen(); pen.setWidthF(3.6 if edge.relation_selected else
                2.2 if self.selected_key in (edge.row['source'], edge.row['target']) else 1.)
            edge.setOpacity(1. if edge.relation_selected else .15 if chosen is not None else
                            1. if self.selected_key in (edge.row['source'], edge.row['target']) else .45)
            edge.setPen(pen); edge.update()

    def _follow_relation(self):
        selected = self.relations.selectedItems()
        if selected: self.select_key(selected[0].data(_USER))

    def open_owner(self, *_):
        row = deepcopy(self.rows.get(self.selected_key, {}))
        if not self.owner_action.isEnabled():
            return False
        if self._open_owner:
            self._open_owner(row)
        else:
            from .desktop import launch_tool
            def launch():
                if row['node_type'] == 'run':
                    return launch_tool(self.client, 'runner', job_id=row['job_id'])
                return launch_tool(self.client, row['owner_kind'], document_id=row['owner_id'])
            return self._call(launch, self._opened)
        return True

    def open_reference(self, *_):
        row = self.rows.get(self.selected_key, {})
        if not self.reference_action.isEnabled():
            return False
        ref = deepcopy(row['exact_reference'])
        if self._open_reference:
            self._open_reference(ref)
        else:
            from .desktop import open_saved_reference
            return self._call(lambda: open_saved_reference(self.client, ref), self._opened)
        return True

    def _opened(self, receipt):
        self.message.setText('선택한 항목의 앱/저장본 열기를 요청했습니다. 원래 입력은 변경하지 않았습니다.')

    def _text_dialog(self, title, text):
        dialog = QDialog(self)
        dialog.setWindowTitle(title); dialog.resize(780, 500)
        layout = QVBoxLayout(dialog)
        content = QPlainTextEdit(text); content.setReadOnly(True)
        layout.addWidget(content)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.button(QDialogButtonBox.StandardButton.Close).setText('닫기')
        buttons.rejected.connect(dialog.reject); layout.addWidget(buttons)
        dialog.exec()

    def show_relations(self):
        lines = []
        for edge in (self.graph or {}).get('edges', []):
            if self.selected_key in (edge['source'], edge['target']):
                a, b = self.rows[edge['source']], self.rows[edge['target']]
                lines.append(a['label'] + ' → ' + edge['label'] + ' → ' + b['label'] + '\n' + b['status_label'])
        self._text_dialog('선택 항목의 관계', '\n\n'.join(lines) or '표시할 관계가 없습니다.')

    def show_diagnostics(self):
        self._text_dialog('선택 항목 진단 상세', json.dumps({'selected': self.rows.get(self.selected_key),
            'issues': (self.graph or {}).get('issues'), 'error': self.error,
            'pending_copy': self._copy_pending}, ensure_ascii=False, indent=2))

    def prepare_copy(self, *, draft_policy=None):
        if self._copy_pending is not None:
            self.message.setText('이전 사본 생성 응답을 먼저 확인하세요. 「사본 생성 응답 확인 / 같은 요청 재시도」에서 이어갈 수 있습니다.')
            return False
        chosen = self.checked_documents()
        if chosen:
            from .connection_window_recovery import prepare_copy
            prepare_copy(self, chosen, draft_policy=draft_policy or self._copy_draft_policy)

    def _review_copy(self, inspection):
        review = CopyReviewDialog(inspection, self)
        if review.exec() != QDialog.DialogCode.Accepted:
            self.message.setText('사본 생성을 취소했습니다. 원문서는 바뀌지 않았습니다.')
            return
        # Save-file chooser is used for a new directory name; existing folders
        # are NEVER passed through an overwrite permission from a native dialog.
        path, _ = QFileDialog.getSaveFileName(self, '새 작업 사본 폴더 이름', str(Path.home() / '새 작업 사본'),
                options=QFileDialog.Option.DontConfirmOverwrite)
        if not path:
            return
        self._copy_pending = {'inspection': deepcopy(inspection), 'destination': path, 'approved': True,
                             'command_id': 'C' + uuid.uuid4().hex,
                             'session_id': inspection['service_session_id']}
        self.retry_copy()

    def retry_copy(self):
        if self._copy_pending:
            request = deepcopy(self._copy_pending)
            started = self._call(lambda: self.client.portable_create(**request), self._copy_created, writing=True)
            if started:
                self.message.setText('사본을 보관하고 있습니다. 큰 저장 결과는 시간이 걸릴 수 있습니다. 완료 전에는 이 창을 닫을 수 없습니다.')
            return started

    def _copy_created(self, receipt):
        self._copy_pending = None
        self._actions()
        self.message.setText('작업 사본을 만들었습니다. 원자료와 계산 기록은 보존되며 새 계산은 실행하지 않았습니다.')
        self._text_dialog('작업 사본 저장 완료', '새 폴더: ' + receipt['workspace'] + '\n\n'
            '현재 창은 원 보관소에 그대로 연결되어 있습니다. 새 폴더를 기존 제품 서비스의 --store로 열면 '
            'Data·Material·Numerical·PDE·Simulation·Evaluation·Study·Expert·Report에서 사본을 편집할 수 있습니다. '
            '함께 보관한 FreeCAD·Post 프로젝트는 해당 도구에서 명시적으로 여세요. 필요한 실행 프로그램은 별도입니다.\n'
            '폴더 전체를 함께 이동하세요. 내부 파일을 따로 옮기지 마세요.')

    def verify_copy(self):
        folder = QFileDialog.getExistingDirectory(self, '확인할 작업 사본 폴더')
        if folder:
            self._call(lambda: self.client.portable_verify(folder), lambda value: self._verified(folder, value))

    def _verified(self, folder, value):
        if value['status'] == 'READY':
            self.message.setText('작업 사본의 보존 파일과 현재 저장 개정을 확인했습니다.')
            return
        issues = value.get('issues', [])
        self._text_dialog('자료 확인 / 복구 안내', '\n\n'.join(i['message'] + '\n위치: ' + i['location'] +
                                                   '\n복구: ' + i['recovery'] for i in issues))
        # Only manifest-named missing/changed files are eligible for exact repair.
        eligible = next((i for i in issues if i['code'] in {'MISSING_ASSET', 'ASSET_CHANGED'}), None)
        if not eligible:
            return
        target = Path(eligible['location'])
        try:
            relative = target.relative_to(Path(folder)).as_posix()
        except ValueError:
            return
        answer = QMessageBox.question(self, '동일 원본 파일 선택',
            '다음 파일만 복구할까요?\n' + relative + '\n선택한 파일이 원본과 정확히 같을 때만 반영됩니다.',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return
        replacement, _ = QFileDialog.getOpenFileName(self, '동일 원본 파일 선택')
        if replacement:
            self._call(lambda: self.client.portable_repair(folder, relative, replacement, approved=True),
                       lambda _: self._call(lambda: self.client.portable_verify(folder),
                                            lambda result: self._verified(folder, result)), writing=True)

    def closeEvent(self, event):
        if self._writing:
            self.message.setText('확인한 변경을 기록 중입니다. 창과 입력을 보호하기 위해 완료 전 닫기를 막았습니다.')
            event.ignore(); return
        if self._layout_close_guard(event):
            return
        self._closed = True
        for worker in self._workers:
            worker.abandon()
            try:
                worker.signals.finished.disconnect(self._finished)
            except (RuntimeError, TypeError):
                pass
        self._workers.clear()
        super().closeEvent(event)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--service', required=True)
    parser.add_argument('--document-id')
    args = parser.parse_args(argv)
    application = QApplication.instance() or QApplication(sys.argv[:1])
    apply_appearance(application)
    window = ConnectionWindow(Client(args.service), document_id=args.document_id)
    window.show()
    return application.exec()


if __name__ == '__main__':
    raise SystemExit(main())
