"""A research entry point using the existing Expert document and native tools."""
from __future__ import annotations

import argparse
import codecs
from copy import deepcopy
import os
from pathlib import Path
import sys
import uuid

from PySide6.QtCore import QSettings, QThreadPool, Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QApplication, QAbstractItemView, QFileDialog, QHBoxLayout, QHeaderView,
    QLabel, QLineEdit, QMainWindow, QPlainTextEdit, QPushButton, QScrollArea,
    QSplitter, QStackedWidget, QToolBar, QTreeWidget, QTreeWidgetItem,
    QVBoxLayout, QWidget,
)

from caelab.workbench_client import Client
from .appearance import apply_appearance
from .expert_window import _Call

PREVIEW_BYTES = 256 * 1024
MODEL_SUFFIXES = {'.fcstd', '.caepre'}
RESULT_SUFFIXES = {'.vtu', '.pvd', '.vtt', '.frd'}
DATA = Qt.ItemDataRole.UserRole


def _read_preview(path):
    with path.open('rb') as stream:
        raw = stream.read(PREVIEW_BYTES + 1)
    truncated = len(raw) > PREVIEW_BYTES
    raw = raw[:PREVIEW_BYTES]
    encoding = 'utf-16' if raw.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)) else 'utf-8-sig'
    try:
        if encoding != 'utf-16' and (b'\0' in raw or any(byte < 9 or 13 < byte < 32 for byte in raw)):
            raise UnicodeError('Binary control characters')
        text = codecs.getincrementaldecoder(encoding)().decode(raw, final=not truncated)
    except UnicodeError:
        return '', '이 파일의 원문은 해당 프로그램에서 열어 주세요.'
    return text, (f'앞 {PREVIEW_BYTES:,}바이트 표시' if truncated else f'{len(raw):,}바이트 읽음')


class WorkbenchWindow(QMainWindow):
    """Navigation and selections belong to an Expert research, never QSettings."""

    def __init__(self, client, *, settings=None, document_id=None):
        super().__init__()
        apply_appearance(QApplication.instance())
        self.client = client
        self.document = None
        self._settings = settings if settings is not None else QSettings('AutonomousCAELab', 'Workbench')
        self._workers, self._pending = [], set()
        self._closed, self._selection_epoch, self._research_epoch = False, 0, 0
        self.conflict = False
        self._build_ui()
        geometry = self._settings.value('geometry')
        if geometry is not None:
            self.restoreGeometry(geometry)
        self.refresh_researches()
        if document_id:
            self.continue_research(document_id)

    @property
    def _busy(self):
        return bool(self._pending)

    def _build_ui(self):
        self.setWindowTitle('Autonomous CAE Lab — Workbench')
        self.resize(1280, 820)
        self.setMinimumSize(960, 680)
        menu = self.menuBar().addMenu('파일(&F)')
        toolbar = QToolBar('연구 작업', self)
        toolbar.setMovable(False)
        self.addToolBar(toolbar)
        self.start_action = QAction('시작', self)
        self.start_action.triggered.connect(self.show_start)
        self.open_file_action = QAction('열기…', self)
        self.open_file_action.setShortcut(QKeySequence.StandardKey.Open)
        self.open_file_action.triggered.connect(self.open_file)
        self.open_model_action = self.open_file_action
        self.save_action = QAction('연구 저장', self)
        self.save_action.setShortcut(QKeySequence.StandardKey.Save)
        self.save_action.triggered.connect(lambda: self.save_document())
        self.save_as_action = QAction('다른 이름으로 저장…', self)
        self.save_as_action.setShortcut(QKeySequence.StandardKey.SaveAs)
        self.save_as_action.triggered.connect(self.save_as)
        for action in (self.start_action, self.open_file_action, self.save_action):
            toolbar.addAction(action)
            menu.addAction(action)
        menu.addAction(self.save_as_action)
        self.recent_model_menu = menu.addMenu('최근 파일')
        self._refresh_recent_models()
        self.relink_source_action = menu.addAction('선택 자료 위치 다시 연결…')
        self.relink_source_action.triggered.connect(self.relink_source)
        menu.addSeparator()
        close = menu.addAction('닫기')
        close.setShortcut(QKeySequence.StandardKey.Close)
        close.triggered.connect(self.close)

        self.pages = QStackedWidget()
        self.start_page = QWidget()
        start = QVBoxLayout(self.start_page)
        start.setContentsMargins(32, 28, 32, 24)
        start.setSpacing(14)
        title = QLabel('모델에서 연구를 시작하세요')
        title.setProperty('appearanceRole', 'title')
        start.addWidget(title)
        intro = QLabel('FreeCAD FEM으로 모델을 편집하고 계산한 뒤, 결과와 로그를 같은 연구에서 검토합니다.')
        intro.setWordWrap(True)
        start.addWidget(intro)
        row = QHBoxLayout()
        self.start_model_button = QPushButton('모델 열기…')
        self.start_model_button.setProperty('appearanceRole', 'primary')
        self.start_model_button.clicked.connect(self.open_file)
        self.new_model_button = QPushButton('FreeCAD에서 새 모델')
        self.new_model_button.clicked.connect(lambda: self.open_tool('pre'))
        row.addWidget(self.start_model_button)
        row.addWidget(self.new_model_button)
        row.addStretch()
        start.addLayout(row)
        heading = QLabel('연구 계속하기')
        heading.setProperty('appearanceRole', 'section')
        start.addWidget(heading)
        self.research_list = QTreeWidget()
        self.research_list.setHeaderLabels(['연구', '연결 모델'])
        self.research_list.setRootIsDecorated(False)
        self.research_list.setAlternatingRowColors(True)
        self.research_list.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.research_list.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.research_list.itemDoubleClicked.connect(lambda item, column: self.continue_research(item.data(0, DATA)))
        self.research_list.itemSelectionChanged.connect(self._update_actions)
        start.addWidget(self.research_list, 1)
        row = QHBoxLayout()
        self.continue_button = QPushButton('선택한 연구 계속하기')
        self.continue_button.clicked.connect(self.continue_selected)
        refresh = QPushButton('목록 새로 고침')
        refresh.clicked.connect(self.refresh_researches)
        row.addWidget(self.continue_button)
        row.addWidget(refresh)
        row.addStretch()
        start.addLayout(row)
        self.pages.addWidget(self.start_page)

        self.research_page = QWidget()
        content = QVBoxLayout(self.research_page)
        content.setContentsMargins(22, 18, 22, 12)
        content.setSpacing(10)
        self.research_title = QLabel()
        self.research_title.setProperty('appearanceRole', 'title')
        self.research_title.setTextFormat(Qt.TextFormat.PlainText)
        self.research_title.setWordWrap(True)
        content.addWidget(self.research_title)
        self.model_path = QLineEdit()
        self.model_path.setReadOnly(True)
        self.model_path.setPlaceholderText('연결 모델을 선택하세요.')
        content.addWidget(self.model_path)
        self.original_path = QLabel()
        self.original_path.setTextFormat(Qt.TextFormat.PlainText)
        self.original_path.setWordWrap(True)
        self.original_path.setProperty('appearanceRole', 'muted')
        content.addWidget(self.original_path)
        row = QHBoxLayout()
        self.model_button = QPushButton('FreeCAD에서 편집')
        self.model_button.setProperty('appearanceRole', 'primary')
        self.model_button.clicked.connect(self.open_connected_model)
        self.relink_button = QPushButton('저장 모델 다시 연결…')
        self.relink_button.clicked.connect(self.relink_model)
        self.origin_button = QPushButton('원 대화 이어가기')
        self.origin_button.clicked.connect(self.open_origin_discussion)
        for button in (self.model_button, self.relink_button, self.origin_button):
            row.addWidget(button)
        row.addStretch()
        content.addLayout(row)
        heading = QLabel('선택 자료')
        heading.setProperty('appearanceRole', 'section')
        content.addWidget(heading)
        self.source_list = QTreeWidget()
        self.source_list.setHeaderLabels(['파일', '종류', '위치'])
        self.source_list.setRootIsDecorated(False)
        self.source_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.source_list.setAlternatingRowColors(True)
        self.source_list.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.source_list.header().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.source_list.setColumnWidth(1, 90)
        self.source_list.itemSelectionChanged.connect(self._files_selected)
        row = QHBoxLayout()
        self.add_sources_button = QPushButton('결과 또는 로그 선택…')
        self.add_sources_button.clicked.connect(self.choose_sources)
        self.refresh_button = QPushButton('다시 읽기')
        self.refresh_button.clicked.connect(self.refresh_files)
        self.post_button = QPushButton('ParaView에서 열기')
        self.post_button.clicked.connect(self.open_selected_result)
        self.discuss_button = QPushButton('선택 자료로 토론')
        self.discuss_button.clicked.connect(self.discuss_files)
        for button in (self.add_sources_button, self.refresh_button, self.post_button, self.discuss_button):
            row.addWidget(button)
        row.addStretch()
        content.addLayout(row)
        self.preview_path = QLabel('원문을 읽을 자료를 선택하세요.')
        self.preview_path.setWordWrap(True)
        self.preview_path.setTextFormat(Qt.TextFormat.PlainText)
        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setPlaceholderText('선택한 로그 또는 입력 파일의 원문')
        self.preview_note = QLabel()
        self.preview_note.setWordWrap(True)
        preview_panel = QWidget()
        preview_layout = QVBoxLayout(preview_panel)
        preview_layout.setContentsMargins(0, 4, 0, 0)
        preview_layout.addWidget(self.preview_path)
        preview_layout.addWidget(self.preview, 1)
        preview_layout.addWidget(self.preview_note)
        source_splitter = QSplitter(Qt.Orientation.Vertical)
        source_splitter.addWidget(self.source_list)
        source_splitter.addWidget(preview_panel)
        source_splitter.setChildrenCollapsible(False)
        source_splitter.setSizes([200, 300])
        content.addWidget(source_splitter, 1)
        self.pages.addWidget(self.research_page)

        navigation = QWidget()
        navigation.setObjectName('workbenchPrograms')
        nav = QVBoxLayout(navigation)
        nav.setContentsMargins(12, 18, 12, 12)
        title = QLabel('프로그램')
        title.setProperty('appearanceRole', 'section')
        nav.addWidget(title)
        self.program_buttons = {}
        for tool, text in (('pre', 'FreeCAD'), ('post', 'ParaView'), ('data', '데이터'),
                ('material', '재료'), ('numerical', '수치 연구'), ('pde', '방정식'),
                ('evaluation', '계산 절차'), ('expert', '전문가 토론'),
                ('study', '연구 기록'), ('report', '보고서')):
            button = QPushButton(text)
            button.setMinimumHeight(34)
            button.clicked.connect(lambda checked=False, tool=tool: self.open_tool(tool))
            nav.addWidget(button)
            self.program_buttons[tool] = button
        nav.addStretch()
        navigation.setStyleSheet('#workbenchPrograms QPushButton { text-align: left; padding-left: 12px; }')
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(navigation)
        scroll.setMinimumWidth(175)
        scroll.setMaximumWidth(220)
        self.workspace_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.workspace_splitter.addWidget(scroll)
        self.workspace_splitter.addWidget(self.pages)
        self.workspace_splitter.setChildrenCollapsible(False)
        self.workspace_splitter.setStretchFactor(1, 1)
        self.workspace_splitter.setSizes([190, 1090])
        self.setCentralWidget(self.workspace_splitter)
        self.message = QLabel('모델을 열거나 연구를 선택해 계속하세요.')
        self.message.setWordWrap(True)
        self.statusBar().addWidget(self.message, 1)
        self._update_actions()

    def _call(self, key, function, accepted, *, current=lambda: True):
        if self._closed or key in self._pending:
            return False
        worker = _Call(function)
        self._workers.append(worker)
        self._pending.add(key)
        self._update_actions()
        def finished(value, error):
            self._workers.remove(worker)
            self._pending.discard(key)
            if self._closed:
                return
            if current():
                if error:
                    self.message.setText('작업을 마치지 못했습니다: ' + str(error))
                else:
                    accepted(value)
            self._update_actions()
        worker.signals.finished.connect(finished, Qt.ConnectionType.QueuedConnection)
        QThreadPool.globalInstance().start(worker)
        return True

    def _state(self):
        return deepcopy((self.document or {}).get('draft', {}).get('context', {}).get('workbench', {}))

    def _mutate(self, change, *, after=None):
        if not self.document:
            return False
        identifier = self.document['id']
        epoch = self._research_epoch
        def update():
            document = self.client.document_read(identifier)
            draft = deepcopy(document['draft'])
            state = draft.setdefault('context', {}).setdefault('workbench', {})
            change(state)
            return self.client.document_command(identifier, 'expert.update', {'draft': draft},
                session_id=document['session_id'], expected_generation=document['generation'],
                command_id='C' + uuid.uuid4().hex)['document']
        def updated(document):
            self._show_document(document)
            if after:
                after()
        return self._call('update', update, updated, current=lambda: epoch == self._research_epoch)

    def _show_document(self, document):
        paths = {str(path) for path in self.selected_paths()}
        self.document = document
        self.research_title.setText(document.get('title', '연구'))
        state = self._state()
        model = state.get('model', {})
        actual = model.get('saved_path') or model.get('original_path') or ''
        original = model.get('original_path') or ''
        self.model_path.setText(actual)
        self.original_path.setText('처음 연 모델: ' + original if original and original != actual else '')
        self.original_path.setVisible(bool(original and original != actual))
        self.model_path.setToolTip(actual)
        self.source_list.clear()
        for source in state.get('sources', []):
            path = source['path']
            item = QTreeWidgetItem([source.get('label') or Path(path).name,
                                    source.get('kind', ''), path])
            item.setData(0, DATA, path)
            for column in (0, 2):
                item.setToolTip(column, path)
            self.source_list.addTopLevelItem(item)
            item.setSelected(path in paths)
        self.pages.setCurrentWidget(self.research_page)
        self._update_actions()

    def show_start(self):
        self.pages.setCurrentWidget(self.start_page)
        self.refresh_researches()

    def refresh_researches(self):
        def loaded(payload):
            self.research_list.clear()
            for document in payload.get('documents', []):
                if document.get('kind') != 'expert':
                    continue
                model = document.get('draft', {}).get('context', {}).get('workbench', {}).get('model', {})
                item = QTreeWidgetItem([document.get('title', '연구'),
                    model.get('saved_path') or model.get('original_path') or '연결 모델 없음'])
                item.setData(0, DATA, document['id'])
                self.research_list.addTopLevelItem(item)
            self._update_actions()
        self._call('catalog', self.client.documents, loaded)

    def continue_selected(self):
        items = self.research_list.selectedItems()
        if items:
            self.continue_research(items[0].data(0, DATA))

    def continue_research(self, identifier):
        self._research_epoch += 1
        epoch = self._research_epoch
        self._call('open', lambda: self.client.document_open(kind='expert', document_id=identifier),
            self._show_document, current=lambda: epoch == self._research_epoch)

    def _update_actions(self):
        paths = self.selected_paths()
        single = paths[0] if len(paths) == 1 else None
        busy = any(key in self._pending for key in ('open', 'update', 'save', 'discussion'))
        self.continue_button.setEnabled(bool(self.research_list.selectedItems()) and not busy)
        self.open_file_action.setEnabled(not busy)
        self.start_model_button.setEnabled(not busy)
        self.save_action.setEnabled(self.document is not None and not busy)
        self.save_as_action.setEnabled(self.document is not None and not busy)
        self.model_button.setEnabled(bool(self.model_path.text()) and not busy)
        self.relink_button.setEnabled(self.document is not None and not busy)
        self.origin_button.setEnabled(self.document is not None and not busy)
        self.add_sources_button.setEnabled(self.document is not None and not busy)
        self.post_button.setEnabled(single is not None and single.suffix.lower() in RESULT_SUFFIXES and not busy)
        self.discuss_button.setEnabled(bool(paths) and not busy)
        self.refresh_button.setEnabled(bool(paths) and not busy)
        self.relink_source_action.setEnabled(single is not None and not busy)

    def selected_paths(self):
        return [Path(item.data(0, DATA)) for item in self.source_list.selectedItems()]

    def _files_selected(self):
        self._selection_epoch += 1
        epoch = self._selection_epoch
        paths = self.selected_paths()
        self.preview.clear()
        self._update_actions()
        if len(paths) != 1:
            self.preview_path.setText(f'{len(paths)}개 자료 선택' if paths else '원문을 읽을 자료를 선택하세요.')
            self.preview_note.clear()
            return
        path = paths[0]
        self.preview_path.setText(str(path))
        if not path.is_file():
            self.preview_note.setText('파일을 찾을 수 없습니다. 파일 메뉴의 선택 자료 위치 다시 연결에서 위치를 지정하세요.')
            return
        self.preview_note.setText('읽는 중…')
        def displayed(value):
            self.preview.setPlainText(value[0])
            self.preview_note.setText(value[1])
        self._call('preview:' + str(epoch), lambda: _read_preview(path), displayed,
                   current=lambda: epoch == self._selection_epoch)

    def refresh_files(self):
        self._files_selected()

    def choose_sources(self):
        names, _ = QFileDialog.getOpenFileNames(self, '결과 또는 로그 선택', self._directory(),
            '결과와 계산 자료 (*.frd *.vtu *.pvd *.vtt *.inp *.sta *.cvg *.dat *.log *.txt);;모든 파일 (*)')
        if names:
            self.attach_paths(names)

    def relink_source(self):
        paths = self.selected_paths()
        if len(paths) != 1:
            return
        old = str(paths[0])
        name, _ = QFileDialog.getOpenFileName(self, '선택 자료 위치 다시 연결', str(paths[0].parent), '모든 파일 (*)')
        if not name:
            return
        path = Path(name).resolve()
        if not path.is_file():
            self.message.setText('디스크에서 열 수 있는 파일을 선택하세요.')
            return
        def change(state):
            for source in state.get('sources', []):
                if source['path'] == old:
                    source['path'], source['label'] = str(path), path.name
                    source['kind'] = '결과' if path.suffix.lower() in RESULT_SUFFIXES else '입력' if path.suffix.lower() == '.inp' else '로그'
        self._mutate(change, after=lambda: self.message.setText('자료의 디스크 위치를 다시 연결했습니다. 이전 토론의 근거는 보존됩니다.'))

    def attach_paths(self, names):
        paths = [Path(name).resolve() for name in names]
        if any(not path.is_file() for path in paths):
            self.message.setText('파일을 읽을 수 없습니다. 결과 또는 로그 선택에서 위치를 다시 지정하세요.')
            return
        def change(state):
            sources = state.setdefault('sources', [])
            for path in paths:
                if not any(item['path'] == str(path) for item in sources):
                    sources.append({'path': str(path), 'label': path.name,
                        'kind': '결과' if path.suffix.lower() in RESULT_SUFFIXES else '입력' if path.suffix.lower() == '.inp' else '로그'})
        def select():
            for index in range(self.source_list.topLevelItemCount()):
                item = self.source_list.topLevelItem(index)
                item.setSelected(item.data(0, DATA) in {str(path) for path in paths})
            self.message.setText('선택 자료를 연구에 연결했습니다. 토론하면 현재 파일 내용을 새 근거로 추가합니다.')
        self._mutate(change, after=select)

    def discuss_files(self):
        paths = self.selected_paths()
        if not paths or not self.document:
            return
        from .selection_discussion import open_file_discussion
        identifier, epoch = self.document['id'], self._research_epoch
        state = self._state()
        def opened(receipt):
            if receipt.get('document'):
                self._show_document(receipt['document'])
            self.message.setText('선택 자료를 원 대화에 추가했습니다.')
        self._call('discussion', lambda: open_file_discussion(self.client,
            [str(path) for path in paths], discussion_id=identifier, workbench=state), opened,
            current=lambda: epoch == self._research_epoch)

    def open_origin_discussion(self):
        if self.document:
            from .desktop import launch_tool
            identifier = self.document['id']
            self._call('expert', lambda: launch_tool(self.client, 'expert', document_id=identifier),
                lambda _: self.message.setText('원 대화를 열었습니다.'))

    def open_tool(self, tool):
        from .desktop import launch_tool
        self._call('app:' + tool, lambda: launch_tool(self.client, tool),
                   lambda _: self.message.setText('프로그램 열기를 요청했습니다.'))

    def open_connected_model(self):
        if self.model_path.text():
            self._launch_model(Path(self.model_path.text()), connect=False)

    def _launch_model(self, path, *, connect=True):
        if path.suffix.lower() not in MODEL_SUFFIXES or not path.is_file():
            self.message.setText('모델 파일을 찾을 수 없습니다. 저장 모델 다시 연결에서 디스크 위치를 지정하세요.')
            return
        path = path.resolve()
        from .desktop import launch_pre
        epoch = self._research_epoch
        def opened(receipt):
            if receipt.get('status') not in {'LAUNCH_REQUESTED', 'ACTIVATED', 'SHOWN'}:
                self.message.setText('모델을 열지 못했습니다. 파일 열기에서 모델을 다시 선택하세요.')
                return
            self._remember(path)
            saved_path = receipt.get('saved_path') or receipt.get('model_path') or str(path)
            def change(state):
                model = state.setdefault('model', {})
                if connect or not model.get('original_path'):
                    model['original_path'] = str(path)
                model['saved_path'] = str(saved_path)
            self._mutate(change, after=lambda: self.message.setText('FreeCAD에서 모델을 편집하고 계산하세요. 저장한 위치가 바뀌면 다시 연결하세요.'))
        def launch():
            identifier, state = self.document['id'], self._state()
            self._call('model', lambda: launch_pre(self.client, source=path,
                discussion_id=identifier, workbench=state), opened,
                       current=lambda: epoch == self._research_epoch)
        if self.document is None or self.pages.currentWidget() is self.start_page:
            self._research_epoch += 1
            epoch = self._research_epoch
            def created(document):
                self._show_document(document)
                launch()
            self._call('open', lambda: self.client.document_open(kind='expert', title=path.stem + ' 연구'), created)
        else:
            launch()

    def relink_model(self):
        name, _ = QFileDialog.getOpenFileName(self, '저장 모델 다시 연결', self._directory(),
            'FreeCAD 모델 (*.FCStd *.fcstd *.caepre)')
        if not name:
            return
        path = Path(name).resolve()
        if not path.is_file() or path.suffix.lower() not in MODEL_SUFFIXES:
            self.message.setText('디스크에 저장된 FreeCAD 모델을 선택하세요.')
            return
        def change(state):
            model = state.setdefault('model', {})
            model.setdefault('original_path', str(path))
            model['saved_path'] = str(path)
        self._mutate(change, after=lambda: self.message.setText('마지막 저장 모델의 위치를 연결했습니다.'))

    def open_selected_result(self):
        paths = self.selected_paths()
        if len(paths) == 1 and paths[0].suffix.lower() in RESULT_SUFFIXES:
            from .desktop import launch_result_file
            path = paths[0]
            identifier, state = self.document['id'], self._state()
            self._call('post', lambda: launch_result_file(self.client, path,
                discussion_id=identifier, workbench=state),
                lambda _: self.message.setText('선택 결과의 ParaView 열기를 요청했습니다.'))

    def save_document(self, *, after=None):
        if not self.document:
            return False
        identifier, epoch = self.document['id'], self._research_epoch
        def save():
            document = self.client.document_read(identifier)
            return self.client.document_command(identifier, 'document.save', {},
                session_id=document['session_id'], expected_generation=document['generation'],
                command_id='C' + uuid.uuid4().hex)['document']
        def saved(document):
            self._show_document(document)
            self.message.setText('모델 연결, 선택 자료와 대화를 저장했습니다.')
            if after:
                after()
        return self._call('save', save, saved, current=lambda: epoch == self._research_epoch)

    def save_as(self):
        from .portable_research_actions import prepare_copy
        prepare_copy(self)

    def _directory(self):
        path = self.model_path.text()
        return str(Path(path).parent) if path else ''

    def open_file(self):
        name, _ = QFileDialog.getOpenFileName(self, '파일 열기', self._directory(),
            '모든 파일 (*);;FreeCAD 모델 (*.FCStd *.fcstd *.caepre);;해석 결과 (*.frd *.vtu *.pvd *.vtt)')
        if not name:
            return
        path = Path(name)
        if not path.is_file():
            self.message.setText('디스크에서 열 수 있는 파일을 선택하세요.')
            return
        self._remember(path.resolve())
        if path.suffix.lower() in MODEL_SUFFIXES:
            self._launch_model(path)
        elif self.document and self.pages.currentWidget() is self.research_page:
            self.attach_paths([str(path)])
        else:
            def created(document):
                self._show_document(document)
                self.attach_paths([str(path)])
            self._call('open', lambda: self.client.document_open(kind='expert', title=path.stem + ' 연구'), created)

    def _remember(self, path):
        paths = self._settings.value('recentModels', [], type=list)
        self._settings.setValue('recentModels', [str(path), *[p for p in paths if p != str(path)]][:10])
        self._settings.sync()
        self._refresh_recent_models()

    def _refresh_recent_models(self):
        self.recent_model_menu.clear()
        paths = self._settings.value('recentModels', [], type=list)
        self.recent_model_menu.setEnabled(bool(paths))
        for name in paths:
            action = self.recent_model_menu.addAction(str(name))
            def open_recent(checked=False, name=name):
                path = Path(name)
                if path.suffix.lower() in MODEL_SUFFIXES:
                    self._launch_model(path)
                elif self.document:
                    self.attach_paths([name])
                else:
                    self.message.setText('연구를 선택한 뒤 최근 자료를 연결하세요.')
            action.triggered.connect(open_recent)

    def closeEvent(self, event):
        self._settings.setValue('geometry', self.saveGeometry())
        self._settings.sync()
        self._closed = True
        for worker in self._workers:
            worker.abandon()
        from .portable_research_actions import close_children
        close_children(self)
        event.accept()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--service', default=os.environ.get('CAELAB_SERVICE_URL'))
    parser.add_argument('--document-id')
    args = parser.parse_args(argv)
    if not args.service:
        parser.error('--service or CAELAB_SERVICE_URL must identify the existing local service')
    application = QApplication.instance() or QApplication(sys.argv[:1])
    window = WorkbenchWindow(Client(args.service), document_id=args.document_id)
    window.show()
    return application.exec()


if __name__ == '__main__':
    raise SystemExit(main())
