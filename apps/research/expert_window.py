"""Native Expert discussion view over the shared document owner and JobManager.

Run with python -m apps.research.expert_window --service http://127.0.0.1:PORT.
Opening and editing a discussion do not require a provider. Only an explicit
bounded round or Continue requests additional registered-role responses.
"""
from __future__ import annotations
import argparse
from copy import deepcopy
import json
import os
import sys
import threading
import uuid

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Qt, Signal
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
    QFormLayout, QHBoxLayout, QInputDialog, QLabel, QListWidget, QListWidgetItem, QMainWindow,
    QMessageBox, QPlainTextEdit, QPushButton, QSpinBox, QSplitter, QTabWidget,
    QToolBar, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

from caelab.discussion_document import diagnostics as discussion_diagnostics
from caelab.storage import canonical_hash
from caelab.workbench_client import Client
from .discussion_view import ConversationList
from .reference_content import ReferenceContent


class _Signals(QObject):
    finished = Signal(object, object)


class _Call(QRunnable):
    def __init__(self, function):
        super().__init__()
        self.function, self.signals = function, _Signals()
        self.completed = threading.Event()
        self._delivery_lock = threading.Lock()
        self._abandoned = False

    def abandon(self):
        # Closing a view stops delivery, not an already requested library job.
        with self._delivery_lock:
            self._abandoned = True

    def run(self):
        result, failure = None, None
        try:
            with self._delivery_lock:
                if self._abandoned:
                    return
            try:
                result = self.function()
            except Exception as error:
                if hasattr(error, 'read'):
                    try:
                        error = error.read().decode('utf-8')
                    except (OSError, UnicodeError):
                        pass
                failure = str(error)
            with self._delivery_lock:
                if not self._abandoned:
                    self.signals.finished.emit(result, failure)
        finally:
            self.completed.set()


class ExpertWindow(QMainWindow):
    """A service view and local question buffer, never a provider/controller."""
    def __init__(self, client, *, document_id=None, title='새 대화', poll_interval=1500,
                 auto_open=True, open_reference=None, open_plan=None):
        super().__init__()
        self.client, self.open_reference, self.open_plan = client, open_reference, open_plan
        self.document = None
        self.local_dirty = self.conflict = self._busy = self._populating = self._allow_close = False
        self._round_started_here = False
        self._auto_round_id = None
        self._foreground_busy = False
        self._registry, self._workers, self._references, self._plans = [], [], [], []
        self._registry_refresh_pending = self._registry_refresh_queued = False
        self._handling_reply = False
        self._buffer = None
        self._draft_problem = None
        self._control_initial = {}
        self._source_choosing = self._closed = False
        self._source_titles, self._source_collections = {}, {}
        self._source_titles_pending = False
        self._source_preview_binding = None
        self._topics_snapshot = None
        self._build_ui()
        self.timer = QTimer(self)
        self.timer.setInterval(poll_interval)
        self.timer.timeout.connect(self.refresh_document)
        if poll_interval > 0:
            self.timer.start()
        if auto_open:
            self.open_document(document_id=document_id, title=title)

    def _build_ui(self):
        self.setWindowTitle('새 대화')
        self.resize(1440, 900)
        self.setMinimumSize(850, 650)
        files = self.menuBar().addMenu('파일(&F)')
        self.new_action = QAction('새 대화…', self, shortcut=QKeySequence.New)
        self.open_action = QAction('대화 열기…', self, shortcut=QKeySequence.Open)
        self.save_action = QAction('저장', self, shortcut=QKeySequence.Save)
        files.addActions([self.new_action, self.open_action, self.save_action])
        self.new_action.triggered.connect(self.new_document)
        self.open_action.triggered.connect(self.choose_document)
        self.save_action.triggered.connect(self.save_document)
        edit = self.menuBar().addMenu('편집(&E)')
        self.undo_action = QAction('실행 취소', self, shortcut=QKeySequence.Undo)
        self.redo_action = QAction('다시 실행', self, shortcut=QKeySequence.Redo)
        edit.addActions([self.undo_action, self.redo_action])
        self.undo_action.triggered.connect(lambda: self.command('document.undo'))
        self.redo_action.triggered.connect(lambda: self.command('document.redo'))
        bar = QToolBar('대화', self)
        bar.setMovable(False)
        self.addToolBar(bar)
        bar.addActions([self.save_action, self.undo_action, self.redo_action])
        self.pause_button = QPushButton('일시 정지')
        self.resume_button = QPushButton('계속')
        self.pause_button.clicked.connect(self.pause_discussion)
        self.resume_button.clicked.connect(self.resume_discussion)
        bar.addWidget(self.pause_button)
        bar.addWidget(self.resume_button)
        self.connection_button = QPushButton('연결 설정…')
        self.connection_button.clicked.connect(self.open_connection)
        bar.addWidget(self.connection_button)
        self.identity = QLabel()
        bar.addWidget(self.identity)
        root = QWidget()
        outer = QVBoxLayout(root)
        self.message = QLabel('')
        self.message.setWordWrap(True)
        self.statusBar().addWidget(self.message, 1)
        conflict = QHBoxLayout()
        self.reload_button, self.copy_button = QPushButton('저장된 내용 다시 열기'), QPushButton('다른 이름으로 보관')
        self.reload_button.clicked.connect(self.reload_remote)
        self.copy_button.clicked.connect(self.copy_edits)
        conflict.addWidget(self.reload_button)
        conflict.addWidget(self.copy_button)
        conflict.addStretch()
        outer.addLayout(conflict)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        outer.addWidget(splitter, 1)
        left = QWidget()
        nav = QVBoxLayout(left)
        conversations = QHBoxLayout()
        new = QPushButton('새 대화')
        opened = QPushButton('대화 열기')
        new.clicked.connect(self.new_document)
        opened.clicked.connect(self.choose_document)
        conversations.addWidget(new); conversations.addWidget(opened)
        nav.addLayout(conversations)
        nav.addWidget(QLabel('논점'))
        self.topics = QTreeWidget()
        self.topics.setHeaderHidden(True)
        self.topics.setObjectName('discussionTopics')
        self.topics.itemClicked.connect(self._topic_clicked)
        nav.addWidget(self.topics, 3)
        topic_row = QHBoxLayout()
        add_topic, rename_topic = QPushButton('논점 추가…'), QPushButton('이름 바꾸기…')
        add_topic.clicked.connect(self.add_topic)
        rename_topic.clicked.connect(self.rename_topic)
        topic_row.addWidget(add_topic)
        topic_row.addWidget(rename_topic)
        nav.addLayout(topic_row)
        participant_tab = QWidget()
        participant_layout = QVBoxLayout(participant_tab)
        participant_layout.addWidget(QLabel('참여 역할'))
        self.registry_status = QLabel()
        self.registry_status.setWordWrap(True)
        self.registry_status.hide()
        participant_layout.addWidget(self.registry_status)
        self.roles = QListWidget()
        self.roles.setObjectName('discussionRoles')
        self.roles.itemChanged.connect(self._edited)
        self.roles.currentRowChanged.connect(self._update_actions)
        self.roles.itemDoubleClicked.connect(lambda *_: self.show_role_details())
        participant_layout.addWidget(self.roles, 1)
        registry = QPushButton('역할 목록 새로고침')
        registry.clicked.connect(self.refresh_registry)
        role_actions = QHBoxLayout()
        role_actions.addWidget(registry)
        self.role_details = QPushButton('역할 상세…')
        self.role_details.clicked.connect(self.show_role_details)
        role_actions.addWidget(self.role_details)
        participant_layout.addLayout(role_actions)
        splitter.addWidget(left)
        center = QWidget()
        conversation = QVBoxLayout(center)
        self.discussion_title = QLabel('대화')
        self.discussion_title.setWordWrap(True)
        heading_font = self.discussion_title.font(); heading_font.setPointSize(heading_font.pointSize() + 2)
        heading_font.setBold(True); self.discussion_title.setFont(heading_font)
        conversation.addWidget(self.discussion_title)
        selected_turn = QHBoxLayout()
        self.turn_context = QLabel('')
        self.turn_context.setWordWrap(True)
        self.selected_reply = QPushButton('답글')
        self.selected_reply.clicked.connect(lambda: self.reply_to_turn(
            self.turns.currentItem().data(Qt.ItemDataRole.UserRole)) if self.turns.currentItem() else None)
        selected_turn.addWidget(self.turn_context, 1)
        selected_turn.addWidget(self.selected_reply)
        conversation.addLayout(selected_turn)
        self.turns = ConversationList()
        self.turns.citation_requested.connect(self.open_turn_citation)
        self.turns.reply_requested.connect(self.reply_to_turn)
        self.turns.setObjectName('discussionTurns')
        self.turns.currentItemChanged.connect(self._turn_selected)
        conversation.addWidget(self.turns, 1)
        self.editor = QWidget()
        composer = QVBoxLayout(self.editor)
        composer.setContentsMargins(0, 4, 0, 0)
        composer.setSpacing(4)
        selector = QHBoxLayout()
        self.reply = QComboBox()
        self.reply.setObjectName('discussionReplyTarget')
        self.reply.currentIndexChanged.connect(self._edited)
        self.classification = QComboBox()
        for label, value in (('질문', 'question'), ('관찰', 'observation'), ('가정', 'assumption'), ('반론', 'challenge'), ('미확인', 'unknown')):
            self.classification.addItem(label, value)
        self.classification.currentIndexChanged.connect(self._edited)
        selector.addWidget(QLabel('답글 대상'))
        selector.addWidget(self.reply, 1)
        selector.addWidget(self.classification)
        composer.addLayout(selector)
        self.question = QPlainTextEdit()
        self.question.setObjectName('discussionQuestion')
        self.question.setPlaceholderText('질문이나 의견을 입력하세요.')
        self.question.setMaximumHeight(80)
        self.question.setMinimumHeight(56)
        self.question.textChanged.connect(self._edited)
        composer.addWidget(self.question)
        self.evidence_label = QLabel('첨부된 계산 결과 없음')
        self.evidence_label.setWordWrap(True)
        self.evidence_label.hide()  # Counts belong in the attachment row, not a separate banner.
        self.composer_evidence = QListWidget()
        self.composer_evidence.setObjectName('discussionAttachments')
        self.composer_evidence.setFixedHeight(38)
        attachments = QHBoxLayout()
        attachments.addWidget(self.composer_evidence, 1)
        self.remove_evidence_button = remove_evidence = QPushButton('첨부 제거')
        remove_evidence.clicked.connect(self.remove_evidence)
        attachments.addWidget(remove_evidence)
        composer.addLayout(attachments)
        actions = QHBoxLayout()
        self.attach_button = QPushButton('결과 첨부…')
        self.attach_button.clicked.connect(self.attach_result)
        self.apply_button = QPushButton('편집 적용')
        self.apply_button.clicked.connect(self.apply_inputs)
        self.intervene_button = QPushButton('발언 남기기')
        self.intervene_button.clicked.connect(self.intervene)
        self.ask_button = QPushButton('토론 시작')
        self.ask_button.clicked.connect(self.ask)
        self.attach_button.setToolTip('저장된 계산 결과에서 첨부할 값을 선택합니다.')
        self.apply_button.setToolTip('현재 질문과 대화 설정을 적용합니다.')
        self.intervene_button.setToolTip('내 발언을 대화에 남깁니다. AI 응답은 요청하지 않습니다.')
        self.ask_button.setToolTip('선택한 참여 역할에 현재 질문을 보냅니다.')
        for button in (self.attach_button, self.apply_button, self.intervene_button, self.ask_button):
            actions.addWidget(button)
        composer.addLayout(actions)
        conversation.addWidget(self.editor)
        splitter.addWidget(center)
        self.side = QTabWidget()
        self.side.setMinimumWidth(300)
        from .expert_sources import SourcePreview
        self.source_tab = QWidget()
        source_layout = QVBoxLayout(self.source_tab)
        buttons = QHBoxLayout()
        self.source_file = QPushButton('파일 추가…')
        self.source_library = QPushButton('저장 자료…')
        self.source_file.clicked.connect(lambda: self.choose_sources(add_file=True))
        self.source_library.clicked.connect(self.choose_sources)
        buttons.addWidget(self.source_file)
        buttons.addWidget(self.source_library)
        source_layout.addLayout(buttons)
        self.selected_sources = QListWidget()
        self.selected_sources.setObjectName('selectedResearchSources')
        self.selected_sources.setMaximumHeight(140)
        self.selected_sources.currentRowChanged.connect(self._update_actions)
        source_layout.addWidget(self.selected_sources)
        actions = QHBoxLayout()
        self.source_open, self.source_remove = QPushButton('원문 읽기'), QPushButton('제거')
        self.source_open.clicked.connect(self.read_selected_source)
        self.source_remove.clicked.connect(self.remove_source)
        actions.addWidget(self.source_open)
        actions.addWidget(self.source_remove)
        source_layout.addLayout(actions)
        self.source_preview = SourcePreview()
        source_layout.addWidget(self.source_preview, 1)
        self.side.addTab(self.source_tab, '참고 자료')
        evidence_tab = QWidget()
        evidence_layout = QVBoxLayout(evidence_tab)
        self.sources = QListWidget()
        self.sources.setMaximumHeight(130)
        self.sources.currentRowChanged.connect(self._citation_selected)
        evidence_layout.addWidget(self.sources)
        self.result_preview = ReferenceContent()
        self.result_preview.hide()
        evidence_layout.addWidget(self.result_preview, 1)
        self.reference_button = QPushButton('원문·결과 열기')
        self.reference_button.clicked.connect(self.open_selected_reference)
        evidence_layout.addWidget(self.reference_button)
        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.hide()
        technical = QPushButton('진단 상세…')
        technical.clicked.connect(self.show_technical_details)
        evidence_layout.addWidget(technical)
        evidence_layout.addStretch()
        self.side.addTab(evidence_tab, '인용 자료')
        plan_tab = QWidget()
        plan_layout = QVBoxLayout(plan_tab)
        self.plans = QListWidget()
        self.plans.currentRowChanged.connect(self._update_actions)
        plan_layout.addWidget(self.plans)
        self.plan_button = QPushButton('계산 계획 열기')
        self.plan_button.clicked.connect(self.open_selected_plan)
        plan_layout.addWidget(self.plan_button)
        proposal_explanation = QLabel('')
        proposal_explanation.setWordWrap(True)
        plan_layout.addWidget(proposal_explanation)
        self.side.addTab(plan_tab, '계산 계획')
        settings = QWidget()
        form = QFormLayout(settings)
        self.allow_question = QCheckBox('질문 전송 허용')
        self.allow_question.setToolTip('Permit question transmission for this request within the existing workspace/provider authorization.')
        self.allow_public = QCheckBox('공개 논문 검색 허용')
        self.allow_public.setToolTip('Permit public literature searches within the existing workspace search authorization.')
        self.allow_sources = QCheckBox('선택 자료 전송 허용')
        self.allow_sources.setToolTip('An explicit grant for the currently selected revisions, within the existing provider policy.')
        self.allow_sources.toggled.connect(self._source_permission_toggled)
        form.addRow(self.allow_sources)
        self.allow_results = QCheckBox('첨부 결과 전송 허용')
        self.allow_results.setToolTip('New attachments do not grant result access. Clear and check this option to explicitly include the currently attached results within existing provider authorization.')
        self.allow_results.toggled.connect(self._result_permission_toggled)
        for field in (self.allow_question, self.allow_public, self.allow_results):
            field.toggled.connect(self._edited)
            form.addRow(field)
        self.model_calls, self.tool_calls, self.seconds = QSpinBox(), QSpinBox(), QSpinBox()
        for field, maximum in ((self.model_calls, 100), (self.tool_calls, 100), (self.seconds, 3600)):
            field.setRange(1 if field != self.tool_calls else 0, maximum)
            field.valueChanged.connect(self._edited)
        form.addRow('역할별 응답 요청 수', self.model_calls)
        form.addRow('역할별 도구 사용 횟수', self.tool_calls)
        form.addRow('역할별 제한 시간(초)', self.seconds)
        runtime_explanation = QLabel('Connection…에서 기존 OpenScience 설정을 선택합니다. 각 요청에는 별도 전송 허용이 적용됩니다.')
        runtime_explanation.setWordWrap(True)
        form.addRow(runtime_explanation)
        self.side.addTab(participant_tab, '참여 역할')
        self.side.addTab(settings, '전송 설정')
        splitter.addWidget(self.side)
        left.setMinimumWidth(230); left.setMaximumWidth(300)
        splitter.setSizes([270, 830, 340])
        self.side.hide()
        for label, tab in (('참고 자료', self.source_tab), ('계산 계획', plan_tab),
                           ('참여 역할', participant_tab), ('전송 설정', settings)):
            action = QAction(label, self)
            action.triggered.connect(lambda checked=False, tab=tab: self.show_side(tab))
            bar.addAction(action)
        hide_side = QPushButton('닫기')
        hide_side.clicked.connect(self.side.hide)
        self.side.setCornerWidget(hide_side)
        splitter.setStretchFactor(1, 1)
        self.setCentralWidget(root)
        self._update_actions()

    def open_connection(self):
        if self._closed or self._busy or self._source_choosing or getattr(self, '_incoming_review', False):
            return False
        from .expert_connection_dialog import ConnectionDialog
        self._source_choosing = True
        self._update_actions()
        dialog = self._connection_dialog = ConnectionDialog(self.client, self)
        try:
            dialog.exec()
        finally:
            self._source_choosing = False
            self._update_actions()
            if not self._closed:
                self.refresh_registry()
        return True

    def _call(self, function, success, *, background=False):
        if self._closed or self._busy or self._source_choosing or getattr(self, '_incoming_review', False):
            return False
        self._busy = True
        self._foreground_busy = not background
        self._update_actions()
        worker = _Call(function)
        self._workers.append(worker)
        def finished(payload, error):
            self._workers.remove(worker)
            self._busy = False
            self._foreground_busy = False
            if self._closed:
                return
            self._handling_reply = True
            try:
                if error:
                    self.message.setText('Service request failed; question and evidence retained. ' + error)
                    if not background:
                        self._round_started_here = False
                        self._auto_round_id = None
                        QTimer.singleShot(0, self.refresh_document)
                else:
                    success(payload)
            finally:
                self._handling_reply = False
                # Success may have queued an explicit Save/Ask continuation.
                # Schedule the registry only after that callback has returned.
                self._update_actions()
        worker.signals.finished.connect(finished, Qt.ConnectionType.QueuedConnection)
        QThreadPool.globalInstance().start(worker)
        return True

    def receive_pending_result(self, message):
        return self._result_return.receive(message)

    def open_document(self, *, document_id=None, title='새 대화', draft=None):
        return self._call(lambda: self.client.document_open(kind='expert', title=title, draft=draft,
                         document_id=document_id), self._opened)

    def _opened(self, document):
        from .result_return import bind_receiver
        if not bind_receiver(self, document):
            return
        self.local_dirty = self.conflict = self._round_started_here = False
        self._auto_round_id = None
        self._show_document(document)
        self.message.setText('')
        self.refresh_registry()
        context = (self._buffer or {}).get('context', {})
        self._source_titles_pending = bool(context.get('selected_sources') or context.get('selected_document_ids'))

    def refresh_registry(self):
        if self._closed:
            return False
        # A busy worker/modal delays this intent; it must not discard it.
        # Repeated requests coalesce, and a completed HTTP error does not retry.
        self._registry_refresh_pending = True
        self._schedule_registry_refresh()
        return True

    def _schedule_registry_refresh(self):
        if (not self._registry_refresh_pending or self._registry_refresh_queued
                or self._closed or self._busy or self._handling_reply
                or self._source_choosing or getattr(self, '_incoming_review', False)):
            return
        self._registry_refresh_queued = True
        QTimer.singleShot(0, self._flush_registry_refresh)

    def _flush_registry_refresh(self):
        self._registry_refresh_queued = False
        if (not self._registry_refresh_pending or self._closed or self._busy
                or self._handling_reply or self._source_choosing
                or getattr(self, '_incoming_review', False)):
            return False
        self._registry_refresh_pending = False
        def received(payload):
            self._registry = payload.get('experts', [])
            self._populate_roles(self.edited_draft()['participants'] if self.document else [])
            if self.document:
                self._populate_turns()
            if self._buffer and self._buffer.get('context', {}).get('selected_sources'):
                self._source_titles_pending = any(ref.get('document_id') not in self._source_titles
                    for ref in self._buffer['context']['selected_sources'] if isinstance(ref, dict))
            packages=payload.get('packages',{})
            missing=[row for row in packages.get('missing_dependencies',[]) if row.get('extra')=='assist-core']
            runtime=payload.get('runtime',{})
            if missing:
                self.message.setText('Expert 실행 패키지가 없습니다. scripts/start-windows.ps1 -InstallOnly -ResearchUI 로 준비할 수 있습니다. 초안과 저장한 대화는 계속 편집할 수 있습니다.')
            elif runtime.get('status')=='NOT_CONFIGURED':
                self.message.setText('모델 미연결 — Connection…에서 연결할 수 있습니다.')
        started = self._call(lambda: self.client.request('/api/workbench/assist',
            {'operation': 'experts.list', 'arguments': {}}), received, background=True)
        if not started:
            self._registry_refresh_pending = True
        return started

    def show_role_details(self):
        current = self.roles.currentItem()
        if current is None:
            return False
        identifier = current.data(Qt.ItemDataRole.UserRole)
        definition = next((deepcopy(row) for row in self._registry if row['id'] == identifier), None)
        if definition is None:
            self.message.setText('선택한 역할 정의를 사용할 수 없습니다. 역할 목록을 새로 고치세요.')
            return False
        def received(connection):
            selected = next((row for row in connection.get('roles', []) if row['id'] == identifier), None)
            if selected is None:
                self.message.setText('역할 설정이 변경되었습니다. 역할 목록을 새로 고치세요.')
                return
            from .expert_connection_dialog import RoleDetailsDialog
            self._source_choosing = True
            self._update_actions()
            try:
                dialog = self._role_dialog = RoleDetailsDialog(definition, model=selected.get('model'),
                    provider=connection.get('provider'), parent=self)
                dialog.exec()
            finally:
                self._source_choosing = False
                if not self._closed:
                    self._update_actions()
        return self._call(self.client.expert_connection, received)

    def _populate_roles(self, selected):
        from .expert_connection_dialog import is_example_role
        current = self.roles.currentItem()
        current_id = current.data(Qt.ItemDataRole.UserRole) if current else None
        self._populating = True
        self.roles.clear()
        by_id = {entry['id']: entry for entry in self._registry}
        for identifier in list(by_id) + [role for role in selected if role not in by_id]:
            definition = by_id.get(identifier, {})
            item = QListWidgetItem(definition.get('label', definition.get('name', definition.get('title', identifier))) +
                (' · unavailable in registry' if identifier not in by_id else
                 ' (예제)' if is_example_role(definition) else ''))
            item.setData(Qt.ItemDataRole.UserRole, identifier)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if identifier in selected else Qt.CheckState.Unchecked)
            self.roles.addItem(item)
            if identifier == current_id:
                self.roles.setCurrentItem(item)
        self.registry_status.setText('No registered roles' if not by_id else '')
        self.registry_status.setToolTip('Configure expert definitions in the existing workbench service. No role or provider response is inferred from an empty registry.')
        self.registry_status.setVisible(not by_id)
        self._populating = False

    def _show_document(self, document, *, preserve_buffer=False):
        previous_owner = (self.document['id'], self.document['session_id']) if self.document else None
        if previous_owner != (document['id'], document['session_id']):
            self._clear_source_preview()
            self.result_preview.clear()
            self.result_preview.hide()
        receiver = getattr(self, '_result_return', None)
        if (receiver and not preserve_buffer and receiver.target
                and receiver.target[0] == document['id'] and receiver.target[1] != document['session_id']):
            # Only a reconciled clean view accepts a fresh service session.
            receiver.bind(document)
        self.document = deepcopy(document)
        if not preserve_buffer:
            self._buffer = deepcopy(document['draft'])
            self._populating = True
            draft = self._buffer
            self._draft_problem = discussion_diagnostics(draft)
            if self._draft_problem:
                self.topics.clear()
                self.roles.clear()
                self.question.clear()
                self._populating = False
                self._populate_turns()
                self.details.setPlainText(json.dumps({'diagnostics': self._draft_problem, 'preserved_draft': draft}, ensure_ascii=False, indent=2))
                self._update_actions()
                return
            composer = draft.get('composer', {})
            self.question.setPlainText(composer.get('text', ''))
            self.classification.setCurrentIndex(self.classification.findData(composer.get('classification')))
            scope = draft.get('context', {}).get('transmission_scope', {})
            self.allow_question.setChecked(scope.get('allow_question', False))
            self.allow_public.setChecked(scope.get('allow_public_search', False))
            self.allow_results.setChecked(bool(scope.get('result_ids')))
            self.allow_sources.setChecked(bool(scope.get('source_refs')))
            budget = draft.get('budget', {})
            self.model_calls.setValue(budget.get('model_calls', 4))
            self.tool_calls.setValue(budget.get('tool_calls', 8))
            self.seconds.setValue(int(budget.get('seconds', 120)))
            self._control_initial = {
                'allow_question': self.allow_question.isChecked(), 'allow_public_search': self.allow_public.isChecked(),
                'allow_results': self.allow_results.isChecked(), 'model_calls': self.model_calls.value(),
                'tool_calls': self.tool_calls.value(), 'seconds': self.seconds.value(),
                'classification': self.classification.currentData()}
            self._populating = False
            self._populate_roles(draft.get('participants', []))
            self._populate_topics()
        self._populate_turns()
        self._populate_reply()
        self._update_evidence_label()
        self._populate_sources()
        self._sync_source_preview()
        self._update_actions()

    def _populate_topics(self):
        topics = deepcopy(self._buffer.get('topics', []))
        for turn in self.document.get('turns', []):
            topic = turn.get('topic')
            if topic and not any(item['id'] == topic['id'] for item in topics):
                topics.append(deepcopy(topic))
        snapshot = ((self.document['id'], self.document['session_id']), topics)
        if snapshot == self._topics_snapshot:
            return
        current_item = self.topics.currentItem()
        selected = current_item.data(0, Qt.ItemDataRole.UserRole) if current_item else None
        if not self._topics_snapshot or self._topics_snapshot[0] != snapshot[0]:
            selected = self._buffer.get('composer', {}).get('topic_id')
        self._topics_snapshot = deepcopy(snapshot)
        self._populating = True
        self.topics.clear()
        nodes = {topic['id']: QTreeWidgetItem([topic['title']]) for topic in topics}
        for topic in topics:
            node = nodes[topic['id']]
            node.setData(0, Qt.ItemDataRole.UserRole, topic['id'])
            parent = nodes.get(topic.get('parent_id'))
            if parent:
                parent.addChild(node)
            else:
                self.topics.addTopLevelItem(node)
        self.topics.expandAll()
        current = nodes.get(selected) or nodes.get(self._buffer.get('composer', {}).get('topic_id'))
        if current:
            self.topics.setCurrentItem(current)
        self._populating = False

    def _populate_turns(self):
        turns = self.document.get('turns', self.document.get('discussion', {}).get('turns', []))
        self.turns.set_turns(turns, self._registry)
        self.discussion_title.setText(self.document.get('title') or '대화')
        self.ask_button.setText('질문 보내기' if turns else '토론 시작')

    def show_side(self, widget):
        self.side.setCurrentWidget(widget)
        self.side.show()

    def show_technical_details(self):
        dialog = QDialog(self)
        dialog.setWindowTitle('발언 진단 상세')
        dialog.resize(760, 560)
        layout = QVBoxLayout(dialog)
        text = QPlainTextEdit(self.details.toPlainText())
        text.setReadOnly(True)
        layout.addWidget(text)
        close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close.rejected.connect(dialog.reject)
        layout.addWidget(close)
        dialog.exec()

    def reply_to_turn(self, identifier):
        index = self.reply.findData(identifier)
        if index >= 0:
            self.reply.setCurrentIndex(index)
            self.question.setFocus()
        for row in range(self.turns.count()):
            if self.turns.item(row).data(Qt.ItemDataRole.UserRole) == identifier:
                self.turns.setCurrentRow(row)
                break

    def open_turn_citation(self, identifier, index):
        for row in range(self.turns.count()):
            if self.turns.item(row).data(Qt.ItemDataRole.UserRole) == identifier:
                self.turns.setCurrentRow(row)
                break
        turn = next((row for row in self.document.get('turns', []) if row['id'] == identifier), None)
        if turn is None:
            return
        source_index = len(turn.get('evidence', [])) + index
        if 0 <= source_index < len(self._references):
            self.sources.setCurrentRow(source_index)
            self.show_side(self.sources.parentWidget())
            self.open_selected_reference()

    def _populate_reply(self):
        target = self.reply.currentData() if self.local_dirty else self._buffer.get('composer', {}).get('reply_to')
        self._populating = True
        self.reply.clear()
        self.reply.addItem('새 질문', None)
        for turn in self.document.get('turns', []):
            from .discussion_view import author_label
            self.reply.addItem(author_label(turn, self._registry) + ': ' + str(turn.get('text') or turn['status'])[:65], turn['id'])
        index = self.reply.findData(target)
        self.reply.setCurrentIndex(max(0, index))
        self._populating = False

    def _edited(self, *_):
        if not self._populating and self.document:
            self.local_dirty = True
            self._update_actions()

    def _result_permission_toggled(self, checked):
        if self._populating or not self._buffer or self._draft_problem:
            return
        # A deliberate toggle grants only the attachments visible at this moment.
        # Later returns/manual attachments, including after cold reopen, do not
        # silently expand this persisted explicit scope.
        scope = self._buffer.setdefault('context', {}).setdefault('transmission_scope', {})
        ids = [item['job_id'] for item in self._buffer['composer']['evidence'] if 'job_id' in item]
        scope['result_ids'] = list(dict.fromkeys(scope.get('result_ids', []) + ids)) if checked else []
        self._edited()

    def edited_draft(self):
        if self._buffer is None:
            return {}
        draft = deepcopy(self._buffer)
        # Malformed saved drafts are retained rather than overwritten by controls.
        if self._draft_problem or not isinstance(draft.get('composer'), dict):
            return draft
        draft['composer'].update(text=self.question.toPlainText(), reply_to=self.reply.currentData())
        if self.classification.currentData() != self._control_initial.get('classification'):
            draft['composer']['classification'] = self.classification.currentData()
        draft['participants'] = [self.roles.item(row).data(Qt.ItemDataRole.UserRole) for row in range(self.roles.count())
                                if self.roles.item(row).checkState() == Qt.CheckState.Checked]
        current = {'allow_question': self.allow_question.isChecked(),
                   'allow_public_search': self.allow_public.isChecked()}
        for key, value in current.items():
            if value != self._control_initial.get(key):
                draft['context'].setdefault('transmission_scope', {})[key] = value
        for key, field in (('model_calls', self.model_calls), ('tool_calls', self.tool_calls), ('seconds', self.seconds)):
            if field.value() != self._control_initial.get(key):
                draft['budget'][key] = field.value()
        return draft

    def command(self, operation, arguments=None, *, after=None):
        if not self.document or self.conflict:
            return False
        document = deepcopy(self.document)
        owner_key = (document['id'], document['session_id'])
        submitted_buffer = self.edited_draft()
        arguments = deepcopy(arguments or {})
        command_id = 'C' + uuid.uuid4().hex
        def received(payload):
            if not self.document or (self.document['id'], self.document['session_id']) != owner_key:
                return
            late_edit = self.edited_draft() != submitted_buffer
            self.local_dirty = late_edit
            self._show_document(payload['document'], preserve_buffer=late_edit)
            if operation == 'expert.ask':
                active = next((row for row in self.document.get('discussion', {}).get('rounds', [])
                               if row.get('command_id') == command_id), None)
                self._auto_round_id = active['id'] if active else None
                self._round_started_here = self._auto_round_id is not None
            if late_edit:
                self.message.setText('Earlier question inputs were applied; newer composer edits remain unapplied. Apply them before Save or Ask.')
            if after and (not late_edit or operation == 'expert.ask'):
                QTimer.singleShot(0, after)
        return self._call(lambda: self.client.document_command(document['id'], operation, arguments,
            session_id=document['session_id'], expected_generation=document['generation'],
            command_id=command_id), received)

    def apply_inputs(self, *, after=None):
        return self.command('expert.update', {'draft': self.edited_draft()}, after=after)

    def save_document(self, *, after=None):
        if self.local_dirty:
            return self.apply_inputs(after=lambda: self.save_document(after=after))
        return self.command('document.save', after=after)

    def ask(self):
        def request():
            self.command('expert.ask', after=self.refresh_document)
        if self.local_dirty:
            return self.apply_inputs(after=request)
        request()

    def intervene(self):
        if self.local_dirty:
            return self.apply_inputs(after=lambda: self.command('expert.intervene'))
        return self.command('expert.intervene')

    def pause_discussion(self):
        self._round_started_here = False
        self._auto_round_id = None
        return self._progress_command('expert.pause')

    def resume_discussion(self):
        return self._progress_command('expert.resume', after=self.refresh_document)

    def _progress_command(self, operation, *, after=None):
        # Pausing must not discard an unapplied counterargument in the composer.
        if not self.document:
            return False
        document = deepcopy(self.document)
        owner_key = (document['id'], document['session_id'])
        submitted_buffer = self.edited_draft()
        def received(payload):
            if not self.document or (self.document['id'], self.document['session_id']) != owner_key:
                return
            preserve = self.local_dirty or self.edited_draft() != submitted_buffer
            self.local_dirty = preserve
            self._show_document(payload['document'], preserve_buffer=preserve)
            if operation == 'expert.resume':
                active = next((row for row in self.document.get('discussion', {}).get('rounds', [])
                               if row.get('status') in {'READY', 'RUNNING'}), None)
                self._auto_round_id = active['id'] if active else None
                self._round_started_here = self._auto_round_id is not None
            if after:
                QTimer.singleShot(0, after)
        return self._call(lambda: self.client.document_command(document['id'], operation, {},
            session_id=document['session_id'], expected_generation=document['generation'],
            command_id='C' + uuid.uuid4().hex), received)

    def refresh_document(self):
        if self._closed or not self.document or self._busy or self._source_choosing or getattr(self, '_incoming_review', False):
            return
        if getattr(self, '_citation_request', None):
            self._schedule_citation()
            return
        if self._registry_refresh_pending:
            # Polling cannot repeatedly take the idle slot reserved for roles.
            self._schedule_registry_refresh()
            return
        identifier, session = self.document['id'], self.document['session_id']
        def received(remote):
            if not self.document or (self.document['id'], self.document['session_id']) != (identifier, session):
                return
            changed_input = (remote['session_id'] != self.document['session_id'] or
                             canonical_hash(remote['draft']) != canonical_hash(self.document['draft']))
            if self.local_dirty and changed_input:
                self.conflict = True
                self.message.setText('Another client or owner session changed this draft. Local edits are retained; reload or keep them as a new discussion.')
                return
            self._show_document(remote, preserve_buffer=self.local_dirty)
            active = next((row for row in remote.get('discussion', {}).get('rounds', []) if row.get('id') == self._auto_round_id), None)
            dispatch_ready = active and (active['status'] == 'READY' or active.get('dispatch_pending'))
            if self._round_started_here and dispatch_ready and not remote.get('discussion', {}).get('paused') and not self.conflict:
                round_id = self._auto_round_id
                def advance():
                    if (self.document and (self.document['id'], self.document['session_id']) == (identifier, session)
                            and self._auto_round_id == round_id and self._round_started_here and not self.conflict
                            and not self.document.get('discussion', {}).get('paused')):
                        self._progress_command('expert.advance')
                QTimer.singleShot(0, advance)
        return self._call(lambda: self.client.document_read(identifier), received, background=True)

    def _topic_clicked(self, item, *_):
        if self._populating or not self._buffer:
            return
        topic = item.data(0, Qt.ItemDataRole.UserRole)
        if any(row['id'] == topic for row in self._buffer['topics']):
            self._buffer['composer']['topic_id'] = topic
            self._edited()
        related = next((turn for turn in self.document.get('turns', []) if turn.get('topic_id') == topic), None)
        if related:
            for row in range(self.turns.count()):
                if self.turns.item(row).data(Qt.ItemDataRole.UserRole) == related['id']:
                    self.turns.setCurrentRow(row)
                    self.turns.scrollToItem(self.turns.item(row))
                    break

    def _turn_selected(self, current, *_):
        self._citation_read_key = None
        self.sources.clear()
        self.plans.clear()
        self.result_preview.clear()
        self.result_preview.hide()
        self._references, self._plans = [], []
        self.turn_context.clear()
        self.selected_reply.setEnabled(bool(current and self.document))
        if not current or not self.document:
            return
        turn = next(row for row in self.document.get('turns', []) if row['id'] == current.data(Qt.ItemDataRole.UserRole))
        from .discussion_view import author_label
        topic = (turn.get('topic') or {}).get('title', '')
        self.turn_context.setText(author_label(turn, self._registry) + (' — ' + topic if topic else ''))
        iterator = self.topics.findItems('', Qt.MatchFlag.MatchContains | Qt.MatchFlag.MatchRecursive)
        for node in iterator:
            if node.data(0, Qt.ItemDataRole.UserRole) == turn.get('topic_id'):
                self.topics.setCurrentItem(node)
        self.details.setPlainText(json.dumps(turn, ensure_ascii=False, indent=2))
        self._references = deepcopy(turn.get('evidence', [])) + deepcopy(turn.get('response', {}).get('sources', []))
        if turn.get('job_id'):
            self._references.append({'document_id': self.document['id'], 'job_id': turn['job_id'],
                                     'input_revision': turn.get('input_revision'),
                                     'input_sha256': turn.get('input_sha256'), 'selection': []})
        for reference in self._references:
            label = ('계산 결과' if 'job_id' in reference or 'run_id' in reference else '논문' if 'paper_id' in reference
                     else self._source_titles.get(reference.get('document_id'), '참고 자료'))
            item = QListWidgetItem(label)
            item.setToolTip('진단 상세에서 원본 식별 정보를 확인할 수 있습니다.')
            self.sources.addItem(item)
        self._plans = turn.get('response', {}).get('proposed_actions', [])
        for index, proposal in enumerate(self._plans):
            plan = proposal.get('plan', {}) if isinstance(proposal, dict) else {}
            self.plans.addItem(str(index + 1) + '. ' + str(plan.get('purpose') or '계산 제안'))
        self._update_actions()

    def add_topic(self):
        if not self._buffer:
            return
        title, accepted = QInputDialog.getText(self, '논점 추가', '논점 제목')
        if accepted and title.strip():
            parent = self.topics.currentItem()
            identifier = 'Q' + uuid.uuid4().hex
            parent_id = parent.data(0, Qt.ItemDataRole.UserRole) if parent else None
            if not any(topic['id'] == parent_id for topic in self._buffer['topics']):
                parent_id = None
            self._buffer['topics'].append({'id': identifier, 'title': title.strip(), 'parent_id': parent_id})
            self._buffer['composer']['topic_id'] = identifier
            self._populate_topics()
            self._edited()

    def rename_topic(self):
        current = self.topics.currentItem()
        if not current:
            return
        topic = next((row for row in self._buffer['topics'] if row['id'] == current.data(0, Qt.ItemDataRole.UserRole)), None)
        if topic is None:
            self.message.setText('This topic belongs to a retained authored turn. Add a new current topic to continue it.')
            return
        title, accepted = QInputDialog.getText(self, '논점 이름 바꾸기', '제목', text=topic['title'])
        if accepted and title.strip():
            topic['title'] = title.strip()
            self._populate_topics()
            self._edited()

    def _update_evidence_label(self):
        refs = self._buffer.get('composer', {}).get('evidence', []) if self._buffer else []
        self.evidence_label.setText('Attachments' if refs else '')
        self.evidence_label.hide()
        self.composer_evidence.setVisible(bool(refs))
        self.remove_evidence_button.setVisible(bool(refs))
        self.composer_evidence.clear()
        for index, ref in enumerate(refs):
            channels = ref.get('selection', ref.get('response_selection', []))
            label = ('계산 결과' if 'job_id' in ref or 'run_id' in ref else '참고 자료') + ' ' + str(index + 1)
            if isinstance(channels, list) and channels:
                label += ' — ' + ', '.join(channels)
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, deepcopy(ref))
            self.composer_evidence.addItem(item)

    def remove_evidence(self):
        row = self.composer_evidence.currentRow()
        if self._buffer and row >= 0:
            del self._buffer['composer']['evidence'][row]
            self._update_evidence_label()
            self._edited()


    def _clear_source_preview(self, message='읽을 자료를 선택하세요.'):
        self._source_preview_binding = None
        self.source_preview.show_error(message)

    def _set_source_preview(self, payload, reference, *, historical=False):
        self.side.show()
        self.side.setCurrentWidget(self.source_tab)
        self._source_preview_binding = {
            'owner': (self.document['id'], self.document['session_id']),
            'reference': deepcopy(reference), 'historical': historical}
        self.source_preview.set_payload(payload)
        self._sync_source_preview()

    def _sync_source_preview(self):
        binding = self._source_preview_binding
        if not binding:
            return
        owner = (self.document['id'], self.document['session_id']) if self.document else None
        if binding['owner'] != owner:
            self._clear_source_preview()
            return
        if not binding['historical']:
            refs = (self._buffer or {}).get('context', {}).get('selected_sources', [])
            ref = {key: binding['reference'].get(key) for key in ('document_id', 'revision')}
            if not isinstance(refs, list) or ref not in refs:
                self._clear_source_preview()

    def _populate_sources(self):
        if not hasattr(self, 'selected_sources'):
            return
        context = (self._buffer or {}).get('context', {})
        refs = context.get('selected_sources')
        if not isinstance(refs, list):
            identifiers = context.get('selected_document_ids', [])
            refs = [{'document_id': identifier, 'revision': None}
                    for identifier in (identifiers if isinstance(identifiers, list) else [])
                    if isinstance(identifier, str)]
        rows = []
        for index, reference in enumerate(refs):
            if not isinstance(reference, dict):
                continue
            title = self._source_titles.get(reference.get('document_id'), '자료 ' + str(index + 1))
            if reference.get('revision') is None:
                title += ' — 저장본 선택 필요'
            rows.append((title, deepcopy(reference)))
        existing = [(self.selected_sources.item(index).text(),
                     self.selected_sources.item(index).data(Qt.ItemDataRole.UserRole))
                    for index in range(self.selected_sources.count())]
        if existing != rows:
            selected = self.selected_sources.currentItem()
            selected = deepcopy(selected.data(Qt.ItemDataRole.UserRole)) if selected else None
            self.selected_sources.blockSignals(True)
            self.selected_sources.clear()
            for title, reference in rows:
                item = QListWidgetItem(title)
                item.setData(Qt.ItemDataRole.UserRole, reference)
                item.setToolTip('저장된 원문을 읽습니다.')
                self.selected_sources.addItem(item)
                if reference == selected:
                    self.selected_sources.setCurrentItem(item)
            self.selected_sources.blockSignals(False)
        grants = context.get('transmission_scope', {}).get('source_refs', [])
        grants = grants if isinstance(grants, list) else []
        self.allow_sources.blockSignals(True)
        self.allow_sources.setChecked(bool(refs) and all(reference in grants for reference in refs))
        self.allow_sources.blockSignals(False)

    def refresh_source_titles(self):
        if self._closed or not self.document:
            return False
        self._source_titles_pending = False
        from .expert_sources import assist
        owner = (self.document['id'], self.document['session_id'])
        def received(payload):
            if not self.document or (self.document['id'], self.document['session_id']) != owner:
                return
            for source in payload['documents']:
                self._source_titles[source['document_id']] = source['title']
                self._source_collections[source['document_id']] = source['collection']
            self._populate_sources()
        started = self._call(lambda: assist(self.client, 'knowledge.list'), received, background=True)
        # A foreground read may win the initial queued prefetch. Retry on its
        # completion or modal release; a completed failed request is not looped.
        self._source_titles_pending = not started
        return started

    def choose_sources(self, _checked=False, *, add_file=False):
        if not self.document or self._busy or self.conflict or self._draft_problem or getattr(self, '_incoming_review', False):
            return False
        from .expert_sources import SourceDialog
        owner = (self.document['id'], self.document['session_id'])
        owner_hash = canonical_hash(self.document['draft'])
        collections = [name for role in self._registry for name in role.get('collections', [])]
        self._source_choosing = True
        self._update_actions()
        try:
            dialog = self._source_dialog = SourceDialog(self.client, self.edited_draft()['context'],
                                                         collections=collections, parent=self)
            if add_file:
                # Wait for initial library loading so file selection does not race it.
                def open_file():
                    if dialog._closed:
                        return
                    if dialog._busy:
                        QTimer.singleShot(25, open_file)
                    else:
                        dialog.choose_file()
                QTimer.singleShot(0, open_file)
            accepted = dialog.exec() == QDialog.DialogCode.Accepted
        finally:
            self._source_choosing = False
            self._update_actions()
        if not accepted:
            return False
        references = deepcopy(dialog.references)
        def checked(remote):
            if (not self.document or (self.document['id'], self.document['session_id']) != owner
                    or self.conflict or self._draft_problem):
                self.message.setText('대화가 변경되어 자료를 첨부하지 않았습니다.')
                return
            if (remote['session_id'] != owner[1] or canonical_hash(remote['draft']) != owner_hash):
                self.conflict = True
                self.message.setText('The saved discussion changed during source selection. Current edits are retained; reconcile before attaching.')
                return
            current = self.edited_draft()
            current['context']['selected_sources'] = references
            current['context']['selected_document_ids'] = [ref['document_id'] for ref in references]
            self._buffer = current
            self._source_titles.update(dialog.titles)
            for source in dialog.records.values():
                self._source_collections[source['document_id']] = source['collection']
            self._populate_sources()
            self._edited()
            self.side.setCurrentWidget(self.source_tab)
            if dialog.records:
                payload = next(iter(dialog.records.values()))
                self._set_source_preview(payload, {key: payload[key] for key in ('document_id', 'revision')})
            else:
                self._clear_source_preview('선택한 자료가 없습니다.')
            self.message.setText('선택한 자료를 첨부했습니다. 저장하면 다시 열 수 있습니다.')
        return self._call(lambda: self.client.document_read(owner[0]), checked)

    def remove_source(self):
        row = self.selected_sources.currentRow()
        if row < 0 or not self._buffer or self._draft_problem:
            return
        current = self.edited_draft()
        context = current['context']
        if isinstance(context.get('selected_sources'), list):
            del context['selected_sources'][row]
            context['selected_document_ids'] = [ref['document_id'] for ref in context['selected_sources']]
        else:
            del context['selected_document_ids'][row]
        self._buffer = current
        self._populate_sources()
        self._sync_source_preview()
        self._edited()

    def read_selected_source(self):
        item = self.selected_sources.currentItem()
        if item is None:
            return False
        reference = deepcopy(item.data(Qt.ItemDataRole.UserRole))
        if type(reference.get('revision')) is not int:
            self.message.setText('저장 자료에서 사용할 원문을 확인하고 선택하세요.')
            return False
        from .expert_sources import assist
        owner = (self.document['id'], self.document['session_id'])
        def received(payload):
            if self.document and (self.document['id'], self.document['session_id']) == owner:
                selected = self.selected_sources.currentItem()
                if selected and selected.data(Qt.ItemDataRole.UserRole) == reference:
                    self._set_source_preview(payload, reference)
                    self._source_titles[reference['document_id']] = payload.get('title') or selected.text()
                    self._populate_sources()
                    self.side.setCurrentWidget(self.source_tab)
        self._clear_source_preview('자료를 읽는 중…')
        return self._call(lambda: assist(self.client, 'knowledge.source', reference), received)

    def _source_permission_toggled(self, checked):
        if self._populating or not self.document or self._draft_problem:
            return
        current = self.edited_draft()
        if not checked:
            current['context'].setdefault('transmission_scope', {})['source_refs'] = []
            self._buffer = current
            self._edited()
            return
        from .expert_sources import assist
        from caelab.assist.knowledge import selected_source_refs
        try:
            references = selected_source_refs(current['context'])
        except ValueError as error:
            self.message.setText(str(error))
            self._populate_sources()
            return
        owner = (self.document['id'], self.document['session_id'])
        def read():
            return [assist(self.client, 'knowledge.source', reference) for reference in references]
        def received(records):
            if not self.document or (self.document['id'], self.document['session_id']) != owner or self.conflict:
                return
            latest = self.edited_draft()
            if selected_source_refs(latest['context']) != references or not self.allow_sources.isChecked():
                self.message.setText('자료 선택이 변경되었습니다. 현재 자료의 전송 허용을 확인하세요.')
                return
            scope = latest['context'].setdefault('transmission_scope', {})
            scope['source_refs'] = deepcopy(references)
            scope['collections'] = list(dict.fromkeys(scope.get('collections', []) +
                [record['collection'] for record in records]))
            self._buffer = latest
            self._edited()
        return self._call(read, received)

    def attach_result(self):
        def listed(payload):
            candidates = [(doc, run) for doc in payload['documents'] if doc.get('kind') != 'expert' for run in doc.get('runs', [])]
            if not candidates:
                self.message.setText('첨부할 계산 결과가 없습니다.')
                return
            labels = [str(index + 1) + '. ' + doc['title'] + ' — 계산 ' + str(
                1 + doc.get('runs', []).index(run)) for index, (doc, run) in enumerate(candidates)]
            selected, accepted = QInputDialog.getItem(self, '계산 결과 첨부', '계산 선택', labels, editable=False)
            if not accepted:
                return
            doc, run = candidates[labels.index(selected)]
            def read(result):
                channels = list(result.get('responses', {}))
                dialog = QDialog(self)
                dialog.setWindowTitle('첨부할 결과 선택')
                layout = QVBoxLayout(dialog)
                rows = QListWidget()
                for channel in channels:
                    item = QListWidgetItem(channel)
                    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                    item.setCheckState(Qt.CheckState.Unchecked)
                    rows.addItem(item)
                layout.addWidget(QLabel('전달할 값을 선택하세요. 선택하지 않으면 계산 상태만 첨부합니다.'))
                layout.addWidget(rows)
                buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
                buttons.accepted.connect(dialog.accept)
                buttons.rejected.connect(dialog.reject)
                layout.addWidget(buttons)
                if dialog.exec() == QDialog.DialogCode.Accepted:
                    reference = {key: deepcopy(run[key]) for key in ('job_id', 'input_revision', 'input_sha256')}
                    reference.update(document_id=doc['id'], selection=[rows.item(row).text() for row in range(rows.count())
                        if rows.item(row).checkState() == Qt.CheckState.Checked])
                    self._buffer['composer']['evidence'].append(reference)
                    self._update_evidence_label()
                    self._edited()
            QTimer.singleShot(0, lambda: self._call(lambda: self.client.document_result(doc['id'], run['job_id'],
                selection={'metadata_only': True}), read))
        return self._call(self.client.documents, listed)

    def _citation_selected(self, *_):
        # A list click alone also invalidates an in-flight older citation read.
        self._citation_read_key = None
        if (self._source_preview_binding or {}).get('historical'):
            self._clear_source_preview('읽을 인용 자료를 선택하세요.')
        self.result_preview.clear()
        self.result_preview.hide()
        self._update_actions()

    def open_selected_reference(self):
        row = self.sources.currentRow()
        if self.open_reference and 0 <= row < len(self._references):
            self.open_reference(deepcopy(self._references[row]))

    def open_selected_plan(self):
        row = self.plans.currentRow()
        if self.open_plan and 0 <= row < len(self._plans) and self.turns.currentItem():
            self.open_plan(self.document['id'], self.turns.currentItem().data(Qt.ItemDataRole.UserRole), row)

    def _update_actions(self, *_):
        if self._closed:
            return
        present = self.document is not None
        enabled = present and not self._busy and not self._source_choosing and not self.conflict and not getattr(self, '_incoming_review', False)
        if enabled and self._source_titles_pending:
            self._source_titles_pending = False
            QTimer.singleShot(0, self.refresh_source_titles)
        self.editor.setEnabled(present and not self._draft_problem and not self._foreground_busy)
        self.roles.setEnabled(present and not self._draft_problem and not self._foreground_busy)
        current_role = self.roles.currentItem()
        self.role_details.setEnabled(enabled and current_role is not None and
            any(row['id'] == current_role.data(Qt.ItemDataRole.UserRole) for row in self._registry))
        self.topics.setEnabled(present and not self._draft_problem and not self._foreground_busy)
        for button in (self.ask_button, self.intervene_button, self.apply_button, self.attach_button):
            button.setEnabled(enabled and not self._draft_problem)
        self.apply_button.setEnabled(enabled and self.local_dirty and not self._draft_problem)
        self.save_action.setEnabled(enabled)
        self.undo_action.setEnabled(enabled and not self.local_dirty and self.document.get('can_undo', False))
        self.redo_action.setEnabled(enabled and not self.local_dirty and self.document.get('can_redo', False))
        self.pause_button.setEnabled(enabled)
        self.resume_button.setEnabled(enabled)
        self.reload_button.setVisible(self.conflict)
        self.copy_button.setVisible(self.conflict)
        self.reload_button.setEnabled(not self._busy)
        self.copy_button.setEnabled(not self._busy)
        source_enabled = enabled and not self._draft_problem
        for button in (self.source_file, self.source_library, self.allow_sources):
            button.setEnabled(source_enabled)
        self.source_remove.setEnabled(source_enabled and self.selected_sources.currentRow() >= 0)
        self.source_open.setEnabled(source_enabled and self.selected_sources.currentRow() >= 0)
        self.reference_button.setEnabled(not self._busy and self.open_reference is not None and self.sources.currentRow() >= 0)
        proposal = self._plans[self.plans.currentRow()] if 0 <= self.plans.currentRow() < len(self._plans) else None
        self.plan_button.setEnabled(not self._busy and not self.conflict and self.open_plan is not None and isinstance(proposal, dict) and
                                    proposal.get('status') == 'PLANNED' and proposal.get('executed') is False)
        if present:
            paused = self.document.get('discussion', {}).get('paused', False)
            state = 'Paused; active calculations are independent' if paused else 'Discussion ready'
            active = next((row for row in self.document.get('discussion', {}).get('rounds', [])
                           if row.get('status') in {'READY', 'RUNNING'}), None)
            state = ('Pausing after current response' if paused and active and active.get('active_job_id')
                     else 'Paused' if paused else 'Responding…' if active and active.get('active_job_id')
                     else 'Ready to continue' if active else 'Ready')
            self.identity.setText({'Pausing after current response': '현재 응답 뒤 일시 정지', 'Paused': '일시 정지',
                'Responding…': '응답 작성 중…', 'Ready to continue': '계속할 수 있음', 'Ready': '대기'}.get(state, state))
            self.setWindowTitle(f"Expert — {self.document['title']}" + (' *' if self.local_dirty or self.document.get('dirty') else ''))
        # Explicit citation selection gets the next idle worker before polling.
        schedule = getattr(self, '_schedule_citation', None)
        if schedule is not None:
            schedule()
        # A modal release or worker completion makes retained refresh work ready.
        # Queue it so an accepted source selection can start its owner check first.
        self._schedule_registry_refresh()

    def reload_remote(self):
        return self._call(lambda: self.client.document_read(self.document['id']), self._opened)

    def copy_edits(self):
        return self.open_document(title=self.document['title'] + ' (question copy)', draft=self.edited_draft())

    def _leave(self, continuation):
        if self._busy:
            self.message.setText('Wait for the current service request before leaving.')
            return
        if not self.document or not (self.local_dirty or self.document.get('dirty')):
            continuation()
            return
        question = QMessageBox(self)
        question.setWindowTitle('저장하지 않은 변경')
        question.setText('변경한 대화를 저장할까요?')
        save = question.addButton('저장', QMessageBox.ButtonRole.AcceptRole)
        keep = question.addButton('저장하지 않고 나가기', QMessageBox.ButtonRole.DestructiveRole)
        question.addButton(QMessageBox.StandardButton.Cancel)
        question.exec()
        if question.clickedButton() == save:
            self.save_document(after=continuation)
        elif question.clickedButton() == keep:
            if self.conflict:
                self.message.setText('Resolve the conflict or keep edits as a new discussion first.')
            elif self.local_dirty:
                self.apply_inputs(after=continuation)
            else:
                continuation()

    def new_document(self):
        def create():
            title, accepted = QInputDialog.getText(self, '새 대화', '제목', text='새 대화')
            if accepted and title.strip():
                self.open_document(title=title.strip())
        self._leave(create)

    def choose_document(self):
        def choose():
            def listed(payload):
                documents = [doc for doc in payload['documents'] if doc.get('kind') == 'expert']
                labels = [str(index + 1) + ". " + doc["title"] for index, doc in enumerate(documents)]
                if not labels:
                    self.message.setText('No saved or working discussions are available.')
                    return
                label, accepted = QInputDialog.getItem(self, '대화 열기', '대화', labels, editable=False)
                if accepted:
                    self.open_document(document_id=documents[labels.index(label)]['id'])
            self._call(self.client.documents, listed)
        self._leave(choose)

    def closeEvent(self, event):
        if getattr(self, '_incoming_review', False):
            event.ignore()
            return
        if self._allow_close:
            self._closed = True
            for worker in self._workers:
                worker.abandon()
            source_dialog = getattr(self, '_source_dialog', None)
            if source_dialog is not None and not source_dialog._closed:
                source_dialog.reject()
            if getattr(self, '_result_return', None):
                self._result_return.close()
            connection = getattr(self, '_connection_dialog', None)
            if connection is not None and not connection._closed:
                connection.reject()
            role_dialog = getattr(self, '_role_dialog', None)
            if role_dialog is not None:
                role_dialog.reject()
            self.timer.stop()
            event.accept()
            return
        event.ignore()
        def leave():
            self._allow_close = True
            self.close()
        self._leave(leave)


def connect_desktop_actions(window, client, *, evidence_opener=None, plan_opener=None):
    """Bind direct-entry actions to shared desktop helpers on the Qt worker boundary."""
    if evidence_opener is None or plan_opener is None:
        from apps.research.desktop import open_evidence_reference, open_discussion_plan
        evidence_opener = evidence_opener or open_evidence_reference
        plan_opener = plan_opener or open_discussion_plan
    window._plan_transfer_commands = {}

    def received(payload, source_reference=None):
        if isinstance(payload, dict) and payload.get('status') == 'RESULT_READ':
            window.result_preview.set_payload(payload['payload'], label='Cited result')
            # Runtime markers carry channel names, not an original row/time slice.
            # Browse only these returned channels; no implicit new result read.
            window.result_preview.read.hide()
            window.result_preview.show()
            window.show_side(window.sources.parentWidget())
            window.message.setText('Saved result channels' if source_reference.get('response_selection') else 'Calculation status')
            return
        if isinstance(payload, dict) and payload.get('status') == 'SOURCE_READ':
            window.message.setText('Saved source')
            source = payload.get('source') or {}
            window._set_source_preview(source, source_reference or
                {key: source[key] for key in ('document_id', 'revision')}, historical=True)
            window.side.setCurrentWidget(window.source_tab)
            return
        if isinstance(payload, dict) and payload.get('status') == 'LAUNCH_REQUESTED':
            window.message.setText('Requested the existing document/editor launch. Review its inputs before executing calculations.')
        else:
            status = payload.get('status', 'RETURNED') if isinstance(payload, dict) else 'RETURNED'
            window.message.setText('Source / Numerical Plan action returned: ' + status)
        window.details.appendPlainText(json.dumps(payload, ensure_ascii=False, indent=2))

    window._citation_request = None
    window._citation_dispatch_queued = False
    window._citation_read_key = None

    def available():
        return not (window._closed or window._busy or window._handling_reply or window._source_choosing
                    or getattr(window, '_incoming_review', False))

    def dispatch_reference():
        window._citation_dispatch_queued = False
        if not window._citation_request or not available():
            return
        key, frozen = window._citation_request
        window._citation_request = None
        def relevant():
            return (window.document and (window.document['id'], window.document['session_id']) == key[0]
                    and window._citation_read_key == key)
        if not relevant():
            return
        def read(payload):
            if relevant():
                received(payload, frozen)
        if not window._call(lambda: evidence_opener(client, frozen), read):
            window._citation_request = (key, frozen)

    def schedule_reference():
        if window._citation_request and not window._citation_dispatch_queued and available():
            window._citation_dispatch_queued = True
            QTimer.singleShot(0, dispatch_reference)

    window._schedule_citation = schedule_reference

    def reference(reference):
        frozen = deepcopy(reference)
        owner = (window.document['id'], window.document['session_id'])
        item = window.turns.currentItem()
        turn_id = item.data(Qt.ItemDataRole.UserRole) if item else None
        key = (owner, turn_id, canonical_hash(frozen))
        window._citation_read_key = key
        window._citation_request = (key, frozen)  # One latest explicit selection.
        window._clear_source_preview('Reading selected citation…')
        window.result_preview.clear('Reading selected citation…')
        schedule_reference()
        return True

    def plan(discussion_id, turn_id, proposal_index):
        selection = (discussion_id, turn_id, proposal_index)
        # The exact append-only turn/proposal identity survives response loss,
        # repeated clicks and reopening this view. A retry creates one Plan.
        command_id = window._plan_transfer_commands.setdefault(selection, 'C' + canonical_hash({
            'operation': 'expert.plan-transfer', 'discussion_id': discussion_id,
            'turn_id': turn_id, 'proposal_index': proposal_index}))
        return window._call(lambda: plan_opener(client, discussion_id, turn_id, proposal_index,
                                              command_id=command_id), received)

    window.open_reference, window.open_plan = reference, plan
    window._update_actions()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--service', default=os.environ.get('CAELAB_SERVICE_URL'))
    parser.add_argument('--document-id')
    parser.add_argument('--title', default='새 대화')
    args = parser.parse_args(argv)
    if not args.service:
        parser.error('--service or CAELAB_SERVICE_URL must identify an existing local service')
    app = QApplication.instance() or QApplication(sys.argv[:1])
    client = Client(args.service)
    if args.document_id:
        from .result_return import activate_existing
        if activate_existing(client, args.document_id).get('status') == 'ACTIVATED':
            return 0
    window = ExpertWindow(client, document_id=args.document_id, title=args.title)
    connect_desktop_actions(window, client)
    window.show()
    return app.exec()


if __name__ == '__main__':
    raise SystemExit(main())
