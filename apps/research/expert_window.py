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
    def __init__(self, client, *, document_id=None, title='Expert discussion', poll_interval=1500,
                 auto_open=True, open_reference=None, open_plan=None):
        super().__init__()
        self.client, self.open_reference, self.open_plan = client, open_reference, open_plan
        self.document = None
        self.local_dirty = self.conflict = self._busy = self._populating = self._allow_close = False
        self._round_started_here = False
        self._auto_round_id = None
        self._foreground_busy = False
        self._registry, self._workers, self._references, self._plans = [], [], [], []
        self._buffer = None
        self._draft_problem = None
        self._control_initial = {}
        self._source_choosing = self._closed = False
        self._source_titles, self._source_collections = {}, {}
        self._source_titles_pending = False
        self._source_preview_binding = None
        self._build_ui()
        self.timer = QTimer(self)
        self.timer.setInterval(poll_interval)
        self.timer.timeout.connect(self.refresh_document)
        if poll_interval > 0:
            self.timer.start()
        if auto_open:
            self.open_document(document_id=document_id, title=title)

    def _build_ui(self):
        self.setWindowTitle('Expert discussion')
        self.resize(1440, 900)
        self.setMinimumSize(850, 650)
        files = self.menuBar().addMenu('&File')
        self.new_action = QAction('New discussion…', self, shortcut=QKeySequence.New)
        self.open_action = QAction('Open discussion…', self, shortcut=QKeySequence.Open)
        self.save_action = QAction('Save discussion', self, shortcut=QKeySequence.Save)
        files.addActions([self.new_action, self.open_action, self.save_action])
        self.new_action.triggered.connect(self.new_document)
        self.open_action.triggered.connect(self.choose_document)
        self.save_action.triggered.connect(self.save_document)
        edit = self.menuBar().addMenu('&Edit')
        self.undo_action = QAction('Undo question/topic edit', self, shortcut=QKeySequence.Undo)
        self.redo_action = QAction('Redo question/topic edit', self, shortcut=QKeySequence.Redo)
        edit.addActions([self.undo_action, self.redo_action])
        self.undo_action.triggered.connect(lambda: self.command('document.undo'))
        self.redo_action.triggered.connect(lambda: self.command('document.redo'))
        bar = QToolBar('Discussion', self)
        bar.setMovable(False)
        self.addToolBar(bar)
        bar.addActions([self.new_action, self.open_action, self.save_action, self.undo_action, self.redo_action])
        self.pause_button = QPushButton('Pause discussion')
        self.resume_button = QPushButton('Continue round')
        self.pause_button.clicked.connect(self.pause_discussion)
        self.resume_button.clicked.connect(self.resume_discussion)
        bar.addWidget(self.pause_button)
        bar.addWidget(self.resume_button)
        self.connection_button = QPushButton('Connection…')
        self.connection_button.clicked.connect(self.open_connection)
        bar.addWidget(self.connection_button)
        self.identity = QLabel()
        bar.addWidget(self.identity)
        root = QWidget()
        outer = QVBoxLayout(root)
        self.message = QLabel('Open a discussion, edit the question, and select registered roles.')
        self.message.setWordWrap(True)
        outer.addWidget(self.message)
        conflict = QHBoxLayout()
        self.reload_button, self.copy_button = QPushButton('Reload service version'), QPushButton('Keep edits as new discussion')
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
        nav.addWidget(QLabel('Topics · click to move to related turns'))
        self.topics = QTreeWidget()
        self.topics.setHeaderHidden(True)
        self.topics.setObjectName('discussionTopics')
        self.topics.itemClicked.connect(self._topic_clicked)
        nav.addWidget(self.topics, 3)
        topic_row = QHBoxLayout()
        add_topic, rename_topic = QPushButton('Add topic…'), QPushButton('Rename…')
        add_topic.clicked.connect(self.add_topic)
        rename_topic.clicked.connect(self.rename_topic)
        topic_row.addWidget(add_topic)
        topic_row.addWidget(rename_topic)
        nav.addLayout(topic_row)
        nav.addWidget(QLabel('Participants · existing registered roles'))
        self.registry_status = QLabel()
        self.registry_status.setWordWrap(True)
        self.registry_status.hide()
        nav.addWidget(self.registry_status)
        self.roles = QListWidget()
        self.roles.setObjectName('discussionRoles')
        self.roles.itemChanged.connect(self._edited)
        nav.addWidget(self.roles, 2)
        registry = QPushButton('Refresh registered roles')
        registry.clicked.connect(self.refresh_registry)
        nav.addWidget(registry)
        splitter.addWidget(left)
        center = QWidget()
        conversation = QVBoxLayout(center)
        conversation.addWidget(QLabel('Actual authored turns · click for reply linkage and evidence'))
        self.turns = QListWidget()
        self.turns.setWordWrap(True)
        self.turns.setObjectName('discussionTurns')
        self.turns.currentItemChanged.connect(self._turn_selected)
        conversation.addWidget(self.turns, 1)
        self.editor = QWidget()
        composer = QVBoxLayout(self.editor)
        selector = QHBoxLayout()
        self.reply = QComboBox()
        self.reply.setObjectName('discussionReplyTarget')
        self.reply.currentIndexChanged.connect(self._edited)
        self.classification = QComboBox()
        for label in ('question', 'observation', 'assumption', 'challenge', 'unknown'):
            self.classification.addItem(label, label)
        self.classification.currentIndexChanged.connect(self._edited)
        selector.addWidget(QLabel('Reply to'))
        selector.addWidget(self.reply, 1)
        selector.addWidget(self.classification)
        composer.addLayout(selector)
        self.question = QPlainTextEdit()
        self.question.setObjectName('discussionQuestion')
        self.question.setPlaceholderText('Question, counterargument or new observation. Apply preserves the draft; request a round invokes the selected roles.')
        self.question.setMaximumHeight(155)
        self.question.textChanged.connect(self._edited)
        composer.addWidget(self.question)
        self.evidence_label = QLabel('No attached result evidence')
        self.evidence_label.setWordWrap(True)
        composer.addWidget(self.evidence_label)
        self.composer_evidence = QListWidget()
        self.composer_evidence.setObjectName('discussionAttachments')
        self.composer_evidence.setMaximumHeight(75)
        composer.addWidget(self.composer_evidence)
        remove_evidence = QPushButton('Remove selected attachment')
        remove_evidence.clicked.connect(self.remove_evidence)
        composer.addWidget(remove_evidence)
        actions = QHBoxLayout()
        self.attach_button = QPushButton('Attach result…')
        self.attach_button.clicked.connect(self.attach_result)
        self.apply_button = QPushButton('Apply edits')
        self.apply_button.clicked.connect(self.apply_inputs)
        self.intervene_button = QPushButton('Add intervention')
        self.intervene_button.clicked.connect(self.intervene)
        self.ask_button = QPushButton('Request round')
        self.ask_button.clicked.connect(self.ask)
        self.attach_button.setToolTip('Attach an exact retained document job and selected response channels.')
        self.apply_button.setToolTip('Apply the edited question, topic, participants and request settings to the shared owner.')
        self.intervene_button.setToolTip('Add this user-authored question, observation or counterargument without requesting a provider reply.')
        self.ask_button.setToolTip('Request one bounded round using the selected actual registered roles.')
        for button in (self.attach_button, self.apply_button, self.intervene_button, self.ask_button):
            actions.addWidget(button)
        composer.addLayout(actions)
        conversation.addWidget(self.editor)
        splitter.addWidget(center)
        self.side = QTabWidget()
        from .expert_sources import SourcePreview
        self.source_tab = QWidget()
        source_layout = QVBoxLayout(self.source_tab)
        buttons = QHBoxLayout()
        self.source_file = QPushButton('Add file…')
        self.source_library = QPushButton('Library…')
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
        self.source_open, self.source_remove = QPushButton('Read source'), QPushButton('Remove')
        self.source_open.clicked.connect(self.read_selected_source)
        self.source_remove.clicked.connect(self.remove_source)
        actions.addWidget(self.source_open)
        actions.addWidget(self.source_remove)
        source_layout.addLayout(actions)
        self.source_preview = SourcePreview()
        source_layout.addWidget(self.source_preview, 1)
        self.side.addTab(self.source_tab, 'Sources')
        evidence_tab = QWidget()
        evidence_layout = QVBoxLayout(evidence_tab)
        self.sources = QListWidget()
        self.sources.currentRowChanged.connect(self._update_actions)
        evidence_layout.addWidget(self.sources)
        self.reference_button = QPushButton('Open exact source / result')
        self.reference_button.clicked.connect(self.open_selected_reference)
        evidence_layout.addWidget(self.reference_button)
        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        evidence_layout.addWidget(self.details, 2)
        self.side.addTab(evidence_tab, 'Evidence / status')
        plan_tab = QWidget()
        plan_layout = QVBoxLayout(plan_tab)
        self.plans = QListWidget()
        self.plans.currentRowChanged.connect(self._update_actions)
        plan_layout.addWidget(self.plans)
        self.plan_button = QPushButton('Open editable Numerical Plan')
        self.plan_button.clicked.connect(self.open_selected_plan)
        plan_layout.addWidget(self.plan_button)
        proposal_explanation = QLabel('A proposal is an editable draft. This action does not execute calculations.')
        proposal_explanation.setWordWrap(True)
        plan_layout.addWidget(proposal_explanation)
        self.side.addTab(plan_tab, 'Plan proposals')
        settings = QWidget()
        form = QFormLayout(settings)
        self.allow_question = QCheckBox('Transmit question')
        self.allow_question.setToolTip('Permit question transmission for this request within the existing workspace/provider authorization.')
        self.allow_public = QCheckBox('Public literature searches')
        self.allow_public.setToolTip('Permit public literature searches within the existing workspace search authorization.')
        self.allow_sources = QCheckBox('Transmit selected sources')
        self.allow_sources.setToolTip('An explicit grant for the currently selected revisions, within the existing provider policy.')
        self.allow_sources.toggled.connect(self._source_permission_toggled)
        form.addRow(self.allow_sources)
        self.allow_results = QCheckBox('Transmit attached results')
        self.allow_results.setToolTip('New attachments do not grant result access. Clear and check this option to explicitly include the currently attached results within existing provider authorization.')
        self.allow_results.toggled.connect(self._result_permission_toggled)
        for field in (self.allow_question, self.allow_public, self.allow_results):
            field.toggled.connect(self._edited)
            form.addRow(field)
        self.model_calls, self.tool_calls, self.seconds = QSpinBox(), QSpinBox(), QSpinBox()
        for field, maximum in ((self.model_calls, 100), (self.tool_calls, 100), (self.seconds, 3600)):
            field.setRange(1 if field != self.tool_calls else 0, maximum)
            field.valueChanged.connect(self._edited)
        form.addRow('Model calls per role', self.model_calls)
        form.addRow('Tool calls per role', self.tool_calls)
        form.addRow('Seconds per role', self.seconds)
        runtime_explanation = QLabel('Connection… selects the local subscription setup; each request keeps these permissions.')
        runtime_explanation.setWordWrap(True)
        form.addRow(runtime_explanation)
        self.side.addTab(settings, 'Request scope')
        splitter.addWidget(self.side)
        splitter.setSizes([260, 870, 310])
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
                QTimer.singleShot(0, self.refresh_registry)
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
            if error:
                self.message.setText('Service request failed; question and evidence retained. ' + error)
                if not background:
                    self._round_started_here = False
                    self._auto_round_id = None
                    QTimer.singleShot(0, self.refresh_document)
            else:
                success(payload)
            self._update_actions()
        worker.signals.finished.connect(finished, Qt.ConnectionType.QueuedConnection)
        QThreadPool.globalInstance().start(worker)
        return True

    def receive_pending_result(self, message):
        return self._result_return.receive(message)

    def open_document(self, *, document_id=None, title='Expert discussion', draft=None):
        return self._call(lambda: self.client.document_open(kind='expert', title=title, draft=draft,
                         document_id=document_id), self._opened)

    def _opened(self, document):
        from .result_return import bind_receiver
        if not bind_receiver(self, document):
            return
        self.local_dirty = self.conflict = self._round_started_here = False
        self._auto_round_id = None
        self._show_document(document)
        self.message.setText('Discussion opened. Saved turns and question drafts do not invoke a model. Continue explicitly to request further replies.')
        QTimer.singleShot(0, self.refresh_registry)
        context = (self._buffer or {}).get('context', {})
        self._source_titles_pending = bool(context.get('selected_sources') or context.get('selected_document_ids'))

    def refresh_registry(self):
        def received(payload):
            self._registry = payload.get('experts', [])
            self._populate_roles(self.edited_draft()['participants'] if self.document else [])
            if self._buffer and self._buffer.get('context', {}).get('selected_sources'):
                self._source_titles_pending = any(ref.get('document_id') not in self._source_titles
                    for ref in self._buffer['context']['selected_sources'] if isinstance(ref, dict))
            packages=payload.get('packages',{})
            missing=[row for row in packages.get('missing_dependencies',[]) if row.get('extra')=='assist-core']
            runtime=payload.get('runtime',{})
            if missing:
                self.message.setText('Expert 실행 패키지가 없습니다. scripts/start-windows.ps1 -InstallOnly -ResearchUI 로 준비할 수 있습니다. 초안과 저장한 대화는 계속 편집할 수 있습니다.')
            elif runtime.get('status')=='NOT_CONFIGURED':
                self.message.setText('Expert 모델은 NOT_CONFIGURED입니다. 초안·논점·저장한 대화는 사용할 수 있으며, Ask 실패는 계산이나 다음 발언을 시작하지 않습니다.')
        return self._call(lambda: self.client.request('/api/workbench/assist',
            {'operation': 'experts.list', 'arguments': {}}), received, background=True)

    def _populate_roles(self, selected):
        self._populating = True
        self.roles.clear()
        by_id = {entry['id']: entry for entry in self._registry}
        for identifier in list(by_id) + [role for role in selected if role not in by_id]:
            definition = by_id.get(identifier, {})
            item = QListWidgetItem(definition.get('label', definition.get('name', definition.get('title', identifier))) +
                (' · unavailable in registry' if identifier not in by_id else ''))
            item.setData(Qt.ItemDataRole.UserRole, identifier)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if identifier in selected else Qt.CheckState.Unchecked)
            self.roles.addItem(item)
        self.registry_status.setText('No registered roles' if not by_id else '')
        self.registry_status.setToolTip('Configure expert definitions in the existing workbench service. No role or provider response is inferred from an empty registry.')
        self.registry_status.setVisible(not by_id)
        self._populating = False

    def _show_document(self, document, *, preserve_buffer=False):
        previous_owner = (self.document['id'], self.document['session_id']) if self.document else None
        if previous_owner != (document['id'], document['session_id']):
            self._clear_source_preview()
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
        self._populating = True
        self.topics.clear()
        topics = deepcopy(self._buffer.get('topics', []))
        for turn in self.document.get('turns', []):
            topic = turn.get('topic')
            if topic and not any(item['id'] == topic['id'] for item in topics):
                topics.append({**deepcopy(topic), 'title': topic['title'] + ' · retained topic'})
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
        current = nodes.get(self._buffer.get('composer', {}).get('topic_id'))
        if current:
            self.topics.setCurrentItem(current)
        self._populating = False

    def _populate_turns(self):
        selected = self.turns.currentItem()
        identifier = selected.data(Qt.ItemDataRole.UserRole) if selected else None
        self.turns.clear()
        for turn in self.document.get('turns', self.document.get('discussion', {}).get('turns', [])):
            text = turn.get('text')
            response = turn.get('response', {})
            if text is None:
                text = response.get('reason', response.get('error', 'No authored answer was returned.'))
            item = QListWidgetItem(f"{turn['author']} · {turn.get('classification', '')} · {turn['status']}\n"
                f"Topic {turn.get('topic_id')} · reply {turn.get('reply_to') or 'none'}\n{text}")
            item.setData(Qt.ItemDataRole.UserRole, turn['id'])
            self.turns.addItem(item)
            if turn['id'] == identifier:
                self.turns.setCurrentItem(item)
        if not self.turns.currentItem() and self.turns.count():
            self.turns.setCurrentRow(self.turns.count() - 1)

    def _populate_reply(self):
        target = self.reply.currentData() if self.local_dirty else self._buffer.get('composer', {}).get('reply_to')
        self._populating = True
        self.reply.clear()
        self.reply.addItem('New question / no reply target', None)
        for turn in self.document.get('turns', []):
            self.reply.addItem(f"{turn['author']} · {str(turn.get('text') or turn['status'])[:65]}", turn['id'])
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
        self.sources.clear()
        self.plans.clear()
        self._references, self._plans = [], []
        if not current or not self.document:
            return
        turn = next(row for row in self.document.get('turns', []) if row['id'] == current.data(Qt.ItemDataRole.UserRole))
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
            label = ('Result' if 'job_id' in reference else 'Literature source' if 'paper_id' in reference
                     else self._source_titles.get(reference.get('document_id'), 'Research source'))
            item = QListWidgetItem(label)
            item.setToolTip(json.dumps(reference, ensure_ascii=False))
            self.sources.addItem(item)
        self._plans = turn.get('response', {}).get('proposed_actions', [])
        for index, proposal in enumerate(self._plans):
            plan = proposal.get('plan', {}) if isinstance(proposal, dict) else {}
            self.plans.addItem(f"{index + 1}. {proposal.get('status', 'PROPOSED') if isinstance(proposal, dict) else 'PROPOSED'} · {plan.get('purpose', str(proposal))}")
        self._update_actions()

    def add_topic(self):
        if not self._buffer:
            return
        title, accepted = QInputDialog.getText(self, 'Add topic', 'Topic title')
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
        title, accepted = QInputDialog.getText(self, 'Rename topic', 'Title', text=topic['title'])
        if accepted and title.strip():
            topic['title'] = title.strip()
            self._populate_topics()
            self._edited()

    def _update_evidence_label(self):
        refs = self._buffer.get('composer', {}).get('evidence', []) if self._buffer else []
        self.evidence_label.setText(f'{len(refs)} attached references · select one to remove it' if refs else 'No attached result evidence')
        self.composer_evidence.clear()
        for ref in refs:
            self.composer_evidence.addItem(f"{ref.get('document_id', ref.get('paper_id'))} / {ref.get('job_id', 'source')} / {ref.get('selection', [])}")

    def remove_evidence(self):
        row = self.composer_evidence.currentRow()
        if self._buffer and row >= 0:
            del self._buffer['composer']['evidence'][row]
            self._update_evidence_label()
            self._edited()


    def _clear_source_preview(self, message='Select a source to read.'):
        self._source_preview_binding = None
        self.source_preview.show_error(message)

    def _set_source_preview(self, payload, reference, *, historical=False):
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
            title = self._source_titles.get(reference.get('document_id'), 'Source ' + str(index + 1))
            if reference.get('revision') is None:
                title += ' — review version'
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
                item.setToolTip(json.dumps(reference, ensure_ascii=False))
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
                self.message.setText('Source selection was not attached: the current discussion changed.')
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
                self._clear_source_preview('No source selected.')
            self.message.setText('Sources attached to the local question. Apply or Save when ready.')
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
            self.message.setText('Open Library to preview and pin this earlier selection explicitly.')
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
        self._clear_source_preview('Reading selected source…')
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
                self.message.setText('Source selection changed. Review transmission permission for the current sources.')
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
                self.message.setText('No retained domain result jobs are available.')
                return
            labels = [f"{doc['title']} · {run['job_id']} · input {run.get('input_revision')}" for doc, run in candidates]
            selected, accepted = QInputDialog.getItem(self, 'Attach exact result', 'Document / submitted job', labels, editable=False)
            if not accepted:
                return
            doc, run = candidates[labels.index(selected)]
            def read(result):
                channels = list(result.get('responses', {}))
                dialog = QDialog(self)
                dialog.setWindowTitle('Select actual response channels')
                layout = QVBoxLayout(dialog)
                rows = QListWidget()
                for channel in channels:
                    item = QListWidgetItem(channel)
                    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                    item.setCheckState(Qt.CheckState.Unchecked)
                    rows.addItem(item)
                layout.addWidget(QLabel('Unchecked channels remain outside this attachment; no selection attaches the whole returned result metadata.'))
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
            self.identity.setText(f"{state} · g{self.document['generation']}")
            self.setWindowTitle(f"Expert — {self.document['title']}" + (' *' if self.local_dirty or self.document.get('dirty') else ''))

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
        question.setWindowTitle('Unsaved discussion')
        question.setText('Save this discussion before leaving?')
        save = question.addButton('Save', QMessageBox.ButtonRole.AcceptRole)
        keep = question.addButton('Keep service draft', QMessageBox.ButtonRole.DestructiveRole)
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
            title, accepted = QInputDialog.getText(self, 'New discussion', 'Title', text='Expert discussion')
            if accepted and title.strip():
                self.open_document(title=title.strip())
        self._leave(create)

    def choose_document(self):
        def choose():
            def listed(payload):
                documents = [doc for doc in payload['documents'] if doc.get('kind') == 'expert']
                labels = [f"{doc['title']} · {doc['id']}" for doc in documents]
                if not labels:
                    self.message.setText('No saved or working discussions are available.')
                    return
                label, accepted = QInputDialog.getItem(self, 'Open discussion', 'Discussion', labels, editable=False)
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
        if isinstance(payload, dict) and payload.get('status') == 'SOURCE_READ':
            window.message.setText('Read the exact indexed source returned by the existing source service.')
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

    def reference(reference):
        frozen = deepcopy(reference)
        owner = (window.document['id'], window.document['session_id'])
        def read(payload):
            if window.document and (window.document['id'], window.document['session_id']) == owner:
                received(payload, frozen)
        return window._call(lambda: evidence_opener(client, frozen), read)

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
    parser.add_argument('--title', default='Expert discussion')
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
