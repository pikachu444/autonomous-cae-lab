"""Independent Study question, competing hypotheses, evidence and judgment editor."""
from copy import deepcopy
from pathlib import Path
import argparse
import hashlib
import json
import os
import sys
import time
import uuid

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QAction, QFontMetrics, QKeySequence
from PySide6.QtWidgets import (QApplication, QBoxLayout, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QHeaderView, QInputDialog,
    QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPushButton, QPlainTextEdit,
    QScrollArea, QSizePolicy, QSplitter, QTabWidget, QToolBar, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget, QFileDialog)

from caelab.study_document import (default_draft, diagnostics, reference_error, HYPOTHESIS_STATUSES,
    DECISION_STATUSES, OBSERVATION_STATUSES)
from caelab.storage import canonical_hash
from caelab.workbench_client import Client
from .numerical_window import NumericalWindow
from .runner_window import readonly_table
from .reference_content import ReferenceContent
from . import study_presentation


DATA = Qt.ItemDataRole.UserRole
STATUS_LABELS = study_presentation.STATUS_LABELS
PENDING_LITERATURE_TARGET = '문헌 연결 결과 확인을 먼저 눌러 주세요. 확인 전에는 이 자료를 삭제하거나 문헌을 교체할 수 없습니다.'


class StudyWindow(NumericalWindow):
    """Navigation callbacks receive one exact reference/context dict on a worker.

    reference_open(reference), discussion_open(context), plan_open(context) may
    return an ordinary navigation receipt. Matching signals are emitted on the
    GUI thread when no callback is supplied. Follow-up context includes the
    saved Study identity and explicitly linked evidence; no work executes here.
    """
    reference_open_requested = Signal(dict)
    discussion_open_requested = Signal(dict)
    plan_open_requested = Signal(dict)

    def __init__(self, client, document_id=None, poll_interval=2000, auto_open=True, *,
                 reference_open=None, discussion_open=None, plan_open=None):
        self._buffer = default_draft()
        self._selected = None
        self._selection_serial = 0
        self._edit_serial = 0
        self._reference_checks = {}
        self._navigation = {'reference': reference_open, 'discussion': discussion_open, 'plan': plan_open}
        self._detail_original = None
        self._raw_mode = False
        self._content_key = None
        self._content_reference = None
        self._content_pending = None
        self._content_queued = False
        self._entry_read_context = {}
        self._reading_evidence_id = None
        self._literature_pending = None
        super().__init__(client, document_id=document_id, poll_interval=poll_interval, auto_open=auto_open)

    def _build_ui(self):
        from .appearance import configure_plot_fonts
        configure_plot_fonts()
        self.resize(1440, 900)
        bar = QToolBar('연구 기록', self)
        self.addToolBar(bar)
        self.new_action = QAction('새 연구 기록', self, shortcut=QKeySequence.New)
        self.open_action = QAction('연구 기록 열기…', self, shortcut=QKeySequence.Open)
        self.save_action = QAction('저장', self, shortcut=QKeySequence.Save)
        self.undo_action = QAction('실행 취소', self, shortcut=QKeySequence.Undo)
        self.redo_action = QAction('다시 실행', self, shortcut=QKeySequence.Redo)
        for action, callback in ((self.new_action, self.new_document), (self.open_action, self.choose_document),
                (self.save_action, self.save_document), (self.undo_action, lambda: self.command('document.undo')),
                (self.redo_action, lambda: self.command('document.redo'))):
            bar.addAction(action)
            action.triggered.connect(callback)
        self.apply_button = QAction('변경 적용', self)
        self.apply_button.triggered.connect(self.apply_inputs)
        self.identity = QLabel()
        self.identity.hide()
        files = self.menuBar().addMenu('파일(&F)')
        files.addActions([self.new_action, self.open_action, self.save_action])
        from .portable_research_actions import install
        install(self, files, 'study')
        report = files.addAction('보고서 만들기…')
        report.triggered.connect(self.open_report)
        self.literature_action = QAction('문헌 추가…', self)
        self.literature_action.triggered.connect(self.choose_literature)
        files.addAction(self.literature_action)
        tools = self.menuBar().addMenu('도구(&T)')
        self.details_action = QAction('진단 상세…', self)
        self.details_action.triggered.connect(self.show_diagnostics)
        tools.addActions([self.details_action, self.apply_button])
        root = QWidget()
        outer = QVBoxLayout(root)
        outer.setContentsMargins(16, 12, 16, 12)
        outer.setSpacing(10)
        self.message = QLabel('')
        self.message.setWordWrap(True)
        self.statusBar().addWidget(self.message, 1)
        conflict = QHBoxLayout()
        self.reload_button = QPushButton('저장된 내용 다시 열기')
        self.copy_button = QPushButton('다른 이름으로 보관')
        self.reload_button.clicked.connect(self.reload_remote)
        self.copy_button.clicked.connect(lambda: self.open_document(draft=self.edited_draft(), title=self.document['title'] + ' (copy)'))
        conflict.addWidget(self.reload_button)
        conflict.addWidget(self.copy_button)
        outer.addLayout(conflict)
        question_row = QHBoxLayout()
        self.question_preview = QLabel('연구 질문을 작성하세요.')
        self.question_preview.setWordWrap(True)
        self.question_preview.setProperty('appearanceRole', 'section')
        question_row.addWidget(self.question_preview, 1)
        self.question_edit_button = QPushButton('질문 수정')
        self.question_edit_button.clicked.connect(self.toggle_question)
        question_row.addWidget(self.question_edit_button)
        outer.addLayout(question_row)
        self.question = QPlainTextEdit()
        self.question.setObjectName('studyQuestion')
        self.question.setMaximumHeight(80)
        self.question.textChanged.connect(self._question_edited)
        self.question.hide()
        outer.addWidget(self.question)
        split = QSplitter(Qt.Orientation.Horizontal)
        outer.addWidget(split, 1)
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 8, 0)
        sources_heading = QHBoxLayout()
        label = QLabel('자료')
        label.setProperty('appearanceRole', 'section')
        sources_heading.addWidget(label, 1)
        self.add_source_button = QPushButton('자료 추가…')
        self.source_menu = self.menuBar().addMenu('자료(&D)')
        self.evidence_buttons = []
        self.source_menu.addAction(self.literature_action)
        self.literature_segment_action = self.source_menu.addAction('문헌 구간 선택…')
        self.literature_segment_action.triggered.connect(self.choose_literature_segment)
        self.literature_file_action = self.source_menu.addAction('문헌 파일 다시 연결…')
        self.literature_file_action.triggered.connect(lambda: self.reconnect_literature_file())
        self.evidence_buttons.append(self.literature_action)
        for label, kind in (('문서 추가…', 'document'), ('계산 결과 추가…', 'result'), ('대화 발언 추가…', 'expert_turn')):
            action = self.source_menu.addAction(label)
            action.triggered.connect(lambda checked=False, kind=kind: self.choose_evidence(kind))
            self.evidence_buttons.append(action)
        self.add_source_button.setMenu(self.source_menu)
        sources_heading.addWidget(self.add_source_button)
        left_layout.addLayout(sources_heading)
        self.evidence = readonly_table(['자료', '종류', '선택한 내용', '읽기 상태'])
        self.evidence.setObjectName('studyEvidence')
        self.evidence.hideColumn(1)
        self.evidence.hideColumn(2)
        self.evidence.horizontalHeader().setStretchLastSection(False)
        self.evidence.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.evidence.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self.evidence.setColumnWidth(3, 85)
        self.evidence.itemSelectionChanged.connect(self._evidence_selected)
        left_layout.addWidget(self.evidence, 3)
        label = QLabel('연구 개요')
        label.setProperty('appearanceRole', 'section')
        left_layout.addWidget(label)
        self.issues = QTreeWidget()
        self.issues.setObjectName('studyIssues')
        self.issues.setHeaderLabels(['내용', '상태'])
        self.issues.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.issues.header().setStretchLastSection(False)
        self.issues.setColumnWidth(1, 95)
        self.issues.itemSelectionChanged.connect(self._issue_selected)
        left_layout.addWidget(self.issues, 2)
        add = QHBoxLayout()
        self.add_buttons = []
        for label, kind in (('가설 추가', 'hypotheses'), ('판단 작성', 'decisions')):
            button = QPushButton(label)
            button.clicked.connect(lambda checked=False, kind=kind: self.add_entry(kind))
            add.addWidget(button)
            self.add_buttons.append(button)
        left_layout.addLayout(add)
        research_menu = self.menuBar().addMenu('연구(&R)')
        self.next_observation_action = research_menu.addAction('다음 확인사항 작성…')
        self.next_observation_action.triggered.connect(lambda: self.add_entry('next_observations'))
        self.add_buttons.append(self.next_observation_action)
        self.remove_button = research_menu.addAction('선택 항목 삭제')
        self.remove_button.triggered.connect(self.remove_entry)
        split.addWidget(left)
        self.content_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.content_splitter.setObjectName('studyContentPanels')
        self.content_splitter.setChildrenCollapsible(False)
        self.reading_page = QWidget()
        right_layout = QVBoxLayout(self.reading_page)
        right_layout.setContentsMargins(0, 0, 0, 0)
        self.source_kind = QLabel('자료를 선택하세요.')
        self.source_kind.setProperty('appearanceRole', 'muted')
        self.source_title = QLabel('')
        self.source_title.setWordWrap(True)
        self.source_title.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.source_title.setProperty('appearanceRole', 'title')
        source_heading = QHBoxLayout()
        source_heading.addWidget(self.source_kind, 1)
        self.replace_literature_button = QPushButton('문헌 다시 선택…')
        self.replace_literature_button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.replace_literature_button.clicked.connect(self.replace_literature)
        source_heading.addWidget(self.replace_literature_button)
        source_heading.addStretch(1)
        self.replace_literature_button.hide()
        right_layout.addLayout(source_heading)
        right_layout.addWidget(self.source_title)
        self.reading = ReferenceContent()
        self.reading.details.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.reading.title.hide()
        self.reading.response_requested.connect(self.read_response)
        right_layout.addWidget(self.reading, 1)
        preview_actions = QHBoxLayout()
        self.preview_difference = QLabel('')
        self.preview_difference.setWordWrap(True)
        self.preview_difference.setProperty('appearanceRole', 'muted')
        self.preview_difference.hide()
        self.pin_response = QPushButton('이 성분을 연구에 연결')
        self.pin_response.clicked.connect(self.keep_response_selection)
        self.pin_response.hide()
        preview_actions.addWidget(self.preview_difference, 1)
        preview_actions.addWidget(self.pin_response)
        right_layout.addLayout(preview_actions)
        reading_actions = QHBoxLayout()
        reading_actions.setSpacing(4)
        self.note_button = QPushButton('자료 메모')
        self.note_button.clicked.connect(self.edit_evidence_note)
        self.reference_button = QPushButton('원본 열기')
        self.check_button = QPushButton('다시 읽기')
        self.reference_button.clicked.connect(self.open_reference)
        self.check_button.clicked.connect(self.check_references)
        for button in (self.reference_button, self.check_button, self.note_button):
            reading_actions.addWidget(button)
        self.followup_basis = QLabel('')
        self.followup_basis.setWordWrap(True)
        self.followup_basis.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.followup_basis.setProperty('appearanceRole', 'muted')
        self.discussion_button = QPushButton('추가 질문…')
        self.plan_button = QPushButton('다음 계산…')
        self.discussion_button.clicked.connect(lambda: self.request_followup('discussion'))
        self.plan_button.clicked.connect(lambda: self.request_followup('plan'))
        reading_actions.addWidget(self.followup_basis, 1)
        right_layout.addLayout(reading_actions)
        followup_actions = QHBoxLayout()
        followup_actions.addStretch(1)
        followup_actions.addWidget(self.discussion_button)
        followup_actions.addWidget(self.plan_button)
        right_layout.addLayout(followup_actions)
        self.content_splitter.addWidget(self.reading_page)
        self.editor = QWidget()
        detail = QVBoxLayout(self.editor)
        detail.setContentsMargins(10, 0, 0, 0)
        heading = QHBoxLayout()
        self.detail_identity = QLabel('')
        self.detail_identity.setWordWrap(True)
        self.detail_identity.setProperty('appearanceRole', 'section')
        heading.addWidget(self.detail_identity, 1)
        self.close_editor_button = QPushButton('접기')
        self.close_editor_button.clicked.connect(self.hide_editor)
        self.cancel_entry_button = QPushButton('수정 취소')
        self.cancel_entry_button.clicked.connect(self.cancel_entry_edits)
        heading.addWidget(self.cancel_entry_button)
        heading.addWidget(self.close_editor_button)
        detail.addLayout(heading)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.editor_body = QWidget()
        body = QVBoxLayout(self.editor_body)
        body.setContentsMargins(0, 0, 0, 0)
        body.setAlignment(Qt.AlignmentFlag.AlignTop)
        scroll.setWidget(self.editor_body)
        detail.addWidget(scroll, 1)
        self.context_source = QPushButton()
        self.context_source.setFlat(True)
        self.context_source.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.context_source.clicked.connect(lambda: self.reading.setFocus())
        self.context_source.hide()
        body.addWidget(self.context_source)
        form = QFormLayout()
        form.setFormAlignment(Qt.AlignmentFlag.AlignTop)
        self.detail_title = QLineEdit()
        self.detail_title.setObjectName('studyEntryTitle')
        self.detail_text = QPlainTextEdit()
        self.detail_text.setObjectName('studyEntryStatement')
        self.detail_text.setFixedHeight(96)
        self.detail_status = QComboBox()
        form.addRow('제목', self.detail_title)
        self.statement_label = QLabel('내용')
        form.addRow(self.statement_label, self.detail_text)
        self.status_label = QLabel('상태')
        form.addRow(self.status_label, self.detail_status)
        body.addLayout(form)
        self.detail_title.textEdited.connect(self._detail_edited)
        self.detail_text.textChanged.connect(self._detail_edited)
        self.detail_status.currentIndexChanged.connect(self._detail_edited)
        self.refs_layout = QBoxLayout(QBoxLayout.Direction.TopToBottom)
        self.link_tabs = QTabWidget()
        self.link_tabs.setDocumentMode(True)
        self.link_lists, self.link_panels = {}, {}
        for key, label in (('hypothesis_ids', '관련 가설'), ('supporting', '지지하는 자료'),
                           ('conflicting', '반박하는 자료'), ('evidence_ids', '참고 자료')):
            panel = QWidget()
            column = QVBoxLayout(panel)
            column.setContentsMargins(0, 0, 0, 0)
            choices = QListWidget()
            choices.setObjectName('study_' + key)
            choices.setMinimumHeight(56)
            choices.setMaximumHeight(128)
            choices.itemChanged.connect(self._detail_edited)
            choices.itemClicked.connect(lambda item, key=key: self.read_linked_evidence(item.data(DATA))
                if key != 'hypothesis_ids' else None)
            column.addWidget(choices)
            self.link_lists[key], self.link_panels[key] = choices, panel
            self.link_tabs.addTab(panel, label)
        self.refs_layout.addWidget(self.link_tabs)
        body.addLayout(self.refs_layout)
        body.addStretch(1)
        self.reference_detail = QPlainTextEdit()
        self.reference_detail.setReadOnly(True)
        self.reference_detail.hide()
        self.editor_save_button = QPushButton('연구 기록 저장')
        self.editor_save_button.setProperty('appearanceRole', 'primary')
        self.editor_save_button.clicked.connect(self.save_document)
        detail.addWidget(self.editor_save_button)
        self.content_splitter.addWidget(self.editor)
        self.editor.hide()
        self.raw = QPlainTextEdit(self)
        self.raw.setObjectName('studyRawDraft')
        self.raw.textChanged.connect(self._raw_edited)
        self.raw.hide()
        split.addWidget(self.content_splitter)
        left.setMinimumWidth(280)
        left.setMaximumWidth(420)
        split.setSizes([350, 1070])
        split.setStretchFactor(1, 1)
        self.setCentralWidget(root)
        self._update_actions()

    def toggle_question(self):
        self.question.setVisible(self.question.isHidden())
        self.question_edit_button.setText('질문 접기' if self.question.isVisible() else '질문 수정')
        if self.question.isVisible():
            self.question.setFocus()

    def _show_editor(self):
        was_hidden = self.editor.isHidden()
        self.editor.show()
        self._arrange_editor()
        if was_hidden:
            self._size_editor()
        self.detail_text.setFocus()

    def hide_editor(self):
        self.editor.hide()
        self._arrange_editor()

    def cancel_entry_edits(self):
        if not self.document or not self._selected or self._busy or self._callbacks or self._raw_mode:
            return False
        if self._pending_literature_target():
            self.message.setText(PENDING_LITERATURE_TARGET)
            return False
        kind, identifier = self._selected
        original = next((row for row in self.document['draft'].get(kind, []) if row['id'] == identifier), None)
        rows = self._buffer.get(kind, [])
        index = next((i for i, row in enumerate(rows) if row['id'] == identifier), None)
        if index is None:
            return False
        if original is None:
            rows.pop(index)
            self._selected = None
        else:
            rows[index] = deepcopy(original)
        self._edit_serial += 1
        self.local_dirty = self.edited_draft() != self.document['draft']
        self._populate_entries()
        self._populate_evidence()
        self._show_detail()
        self.hide_editor()
        self.message.setText('선택 항목의 수정을 취소했습니다. 읽던 근거와 다른 편집은 유지합니다.')
        self._update_actions()
        return True

    def _size_editor(self):
        if self.content_splitter.orientation() == Qt.Orientation.Vertical:
            # Leave the judgment state visible below its statement on first open.
            # User splitter adjustments remain untouched while editing/selection changes.
            size = min(300, max(220, self.content_splitter.height() // 2))
            self.content_splitter.setSizes([max(250, self.content_splitter.height() - size), size])
        else:
            self.content_splitter.setSizes([max(400, self.content_splitter.width() - 360), 360])

    def _arrange_editor(self):
        vertical = self.width() < 1200
        orientation = Qt.Orientation.Vertical if vertical else Qt.Orientation.Horizontal
        if self.content_splitter.orientation() != orientation:
            self.content_splitter.setOrientation(orientation)
            self._size_editor()
        self.editor.setMinimumWidth(0 if vertical else 320)
        self.refs_layout.setDirection(QBoxLayout.Direction.LeftToRight if vertical else QBoxLayout.Direction.TopToBottom)
        self.editor.layout().setContentsMargins(0, 8, 0, 0) if vertical else self.editor.layout().setContentsMargins(10, 0, 0, 0)
        compact = vertical and not self.editor.isHidden()
        self.followup_basis.setVisible(bool(self.followup_basis.text()) and self.editor.isHidden())
        self.source_kind.setVisible(not compact)
        self._update_source_title(compact)
        QTimer.singleShot(0, self._update_source_title)

    def _update_source_title(self, compact=None):
        text = self.source_title.toolTip()
        compact = self.width() < 1200 and not self.editor.isHidden() if compact is None else compact
        self.source_title.setText(QFontMetrics(self.source_title.font()).elidedText(text,
            Qt.TextElideMode.ElideRight, max(100, self.source_title.width() - 16)) if compact else text)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'content_splitter'):
            self._arrange_editor()

    def read_linked_evidence(self, identifier):
        if any(row['id'] == identifier for row in self._buffer.get('evidence', [])):
            self._reading_evidence_id = identifier
            self._selection_serial += 1
            self._sync_evidence_content()
            self._populate_evidence()

    def _context(self, selection=False):
        owner = (self.document['id'], self.document['session_id']) if self.document else None
        return (owner, self._selection_serial) if selection else owner

    def _commit_editor(self):
        # Text/checkbox signals write the current buffer without closing editors.
        pass

    def _edited(self, *_):
        if not self._populating:
            self._edit_serial += 1
            self.local_dirty = True
            self._update_actions()

    def _question_edited(self):
        if not self._populating and not self._raw_mode:
            self._buffer['question'] = study_presentation.question_value(self.document,self._buffer,self.question.toPlainText())
            self.question_preview.setText(study_presentation.question(self.document,self._buffer) or '연구 질문을 작성하세요.')
            self._edited()

    def _raw_edited(self):
        if not self._populating and self._raw_mode:
            self._edited()

    def edited_draft(self):
        if self._raw_mode:
            try:
                value = json.loads(self.raw.toPlainText())
                if isinstance(value, dict):
                    return value
            except ValueError:
                pass
            return deepcopy(self._buffer)
        return deepcopy(self._buffer)

    def _shape_supported(self, draft):
        if not isinstance(draft, dict) or set(draft) != set(default_draft()) or not isinstance(draft.get('question'), str):
            return False
        specs = {'hypotheses': {'id', 'title', 'statement', 'status'}, 'evidence': {'id', 'label', 'kind', 'reference', 'note'},
                 'decisions': {'id', 'title', 'statement', 'hypothesis_ids', 'supporting', 'conflicting', 'status'},
                 'next_observations': {'id', 'question', 'hypothesis_ids', 'evidence_ids', 'status', 'note'}}
        return all(isinstance(draft.get(key), list) and all(isinstance(row, dict) and set(row) == fields
            and isinstance(row.get('id'), str) for row in draft[key]) for key, fields in specs.items())

    def _show_document(self, document, *, preserve_buffer=False):
        receiver = getattr(self, '_result_return', None)
        if (receiver and not preserve_buffer and receiver.target
                and receiver.target[0] == document['id'] and receiver.target[1] != document['session_id']):
            # Only a reconciled clean view accepts a fresh service session.
            receiver.bind(document)
        pending_raw = self.raw.toPlainText() if preserve_buffer and self._raw_mode else None
        if preserve_buffer:
            self._buffer = self.edited_draft()
        self.document = deepcopy(document)
        if not preserve_buffer:
            self._buffer = deepcopy(document['draft'])
        self._populating = True
        self._raw_mode = not self._shape_supported(self._buffer)
        self._view_error = 'Original draft has fields outside this editor. Edit its complete JSON object in Original draft; saving does not normalize it.' if self._raw_mode else None
        self.raw.setReadOnly(not self._raw_mode)
        self.raw.setPlainText(json.dumps(self._buffer, ensure_ascii=False, indent=2))
        if pending_raw is not None and self._raw_mode:
            self.raw.setPlainText(pending_raw)
        question=study_presentation.question(document,self._buffer)
        self.question.setPlainText(str(question))
        self.question_preview.setText(str(question) or '연구 질문을 작성하세요.')
        self._populate_entries()
        self._populate_evidence()
        self._show_detail()
        self._populating = False
        if self._raw_mode:
            self.message.setText('이 문서에는 현재 편집 화면에서 지원하지 않는 항목이 있습니다. 도구 → 진단 상세에서 원본을 확인할 수 있습니다.')
        self._update_actions()

    def _opened(self, document):
        from .result_return import bind_receiver
        if not bind_receiver(self, document):
            return
        self.local_dirty = self.conflict = False
        evidence = document.get('draft', {}).get('evidence', [])
        self._selected = ('evidence', evidence[0]['id']) if isinstance(evidence, list) and evidence and isinstance(evidence[0], dict) and evidence[0].get('id') else None
        self._selection_serial += 1
        self._reference_checks.clear()
        self._entry_read_context.clear()
        self._reading_evidence_id = None
        self.editor.hide()
        self.question.hide()
        self.question_edit_button.setText('질문 수정')
        self._show_document(document)
        self.message.setText('')

    def _populate_entries(self):
        self.issues.blockSignals(True)
        self.issues.clear()
        if not self._raw_mode:
            for kind, title in (('hypotheses', '가설'), ('decisions', '판단'), ('next_observations', '다음 확인사항')):
                parent = QTreeWidgetItem([title, ''])
                self.issues.addTopLevelItem(parent)
                for row in self._buffer[kind]:
                    child = QTreeWidgetItem([str(row.get('title', row.get('question', ''))), STATUS_LABELS.get(row.get('status'), str(row.get('status')))])
                    child.setData(0, DATA, (kind, row['id']))
                    parent.addChild(child)
                    if self._selected == (kind, row['id']):
                        self.issues.setCurrentItem(child)
                parent.setExpanded(True)
        self.issues.blockSignals(False)

    def _populate_evidence(self):
        self.evidence.blockSignals(True)
        self.evidence.clearSelection()
        rows = self._buffer.get('evidence', []) if not self._raw_mode else []
        self.evidence.setRowCount(len(rows))
        for index, row in enumerate(rows):
            ref = row.get('reference') if isinstance(row.get('reference'), dict) else {}
            selection = ref.get('selection', {})
            channels = selection.get('responses', []) if isinstance(selection, dict) else selection
            identity = ', '.join(channels) if isinstance(channels, list) else ''
            identity = identity or ref.get('response') or ('발언 본문' if row['kind'] == 'expert_turn' else '저장 자료')
            check = self._reference_checks.get(row['id'], {})
            message = {'AVAILABLE': '읽기 완료', 'UNKNOWN': '읽기 전', 'STALE': '원본 변경됨',
                       'UNAVAILABLE': '읽을 수 없음', 'INVALID': '잘못된 참조',
                       'INVALID_LOCATOR': '구간 없음'}.get(check.get('status'), '읽기 전')
            for column, value in enumerate((self._evidence_label(row), {'expert_turn': '대화', 'result': '계산 결과', 'document': '문서'}.get(row['kind'], row['kind']), identity, message)):
                self._set_cell(self.evidence, index, column, value, False)
                self.evidence.item(index, column).setToolTip(str(check.get('message') or value) if column == 3 else str(value))
            if self._selected == ('evidence', row['id']) or self._reading_evidence_id == row['id']:
                self.evidence.selectRow(index)
        self.evidence.blockSignals(False)

    def _row(self):
        if self._selected and not self._raw_mode:
            kind, identifier = self._selected
            return next((row for row in self._buffer.get(kind, []) if row.get('id') == identifier), None)
        return None

    def _select(self, key):
        if key != self._selected:
            self._selected = key
            self._selection_serial += 1
        self._show_detail()
        self._update_actions()

    def _issue_selected(self):
        item = self.issues.currentItem()
        if item and item.data(0, DATA):
            self.evidence.blockSignals(True)
            self.evidence.clearSelection()
            self.evidence.blockSignals(False)
            self._select(item.data(0, DATA))
            self._show_editor()

    def _evidence_selected(self):
        rows = self.evidence.selectionModel().selectedRows()
        if len(rows) == 1:
            self.issues.blockSignals(True)
            self.issues.clearSelection()
            self.issues.blockSignals(False)
            self._select(('evidence', self._buffer['evidence'][rows[0].row()]['id']))

    def _show_detail(self):
        prior, self._populating = self._populating, True
        row = self._row()
        self._detail_original = deepcopy(row)
        kind = self._selected[0] if row else None
        self.detail_identity.setText({'hypotheses': '가설 작성', 'decisions': '연구 판단',
            'next_observations': '다음 확인사항', 'evidence': '자료 메모'}.get(kind, ''))
        self.statement_label.setText('메모' if kind == 'evidence' else '진술' if kind in {'hypotheses', 'decisions'} else '내용')
        title = self._evidence_label(row) if kind == 'evidence' else str(row.get('title', row.get('question', ''))) if row else ''
        text = (study_presentation.evidence_note(row) if kind=='evidence'
            else str(row.get('statement', row.get('note', '')))) if row else ''
        if self.detail_title.text() != title:
            self.detail_title.setText(title)
        if self.detail_text.toPlainText() != text:
            self.detail_text.setPlainText(text)
        self.detail_status.clear()
        statuses = {'hypotheses': HYPOTHESIS_STATUSES, 'decisions': DECISION_STATUSES, 'next_observations': OBSERVATION_STATUSES}
        if row and 'status' in row:
            for value in statuses[self._selected[0]]:
                self.detail_status.addItem(STATUS_LABELS.get(value, value), value)
            if self.detail_status.findData(row['status']) < 0:
                self.detail_status.addItem(str(row['status']), row['status'])
            self.detail_status.setCurrentIndex(self.detail_status.findData(row['status']))
        self.detail_status.setVisible(bool(row and 'status' in row))
        self.status_label.setVisible(bool(row and 'status' in row))
        for key, choices in self.link_lists.items():
            self.link_tabs.setTabVisible(self.link_tabs.indexOf(self.link_panels[key]), bool(row and key in row))
            choices.clear()
            if row is None or key not in row:
                continue
            selected = row[key] if isinstance(row[key], list) else []
            options = self._buffer['hypotheses' if key == 'hypothesis_ids' else 'evidence']
            ids = {item['id'] for item in options}
            entries = [(item['id'], item.get('title', '') if key == 'hypothesis_ids' else self._evidence_label(item)) for item in options]
            entries += [(identifier, '연결된 항목이 없습니다.') for identifier in selected if isinstance(identifier, str) and identifier not in ids]
            for identifier, label in entries:
                item = QListWidgetItem(str(label))
                item.setData(DATA, identifier)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Checked if identifier in selected else Qt.CheckState.Unchecked)
                choices.addItem(item)
        self.reference_detail.setPlainText(json.dumps({'reference': row.get('reference'), 'check': self._reference_checks.get(row['id'])}, ensure_ascii=False, indent=2) if row and self._selected[0] == 'evidence' else
            '\n'.join(issue['path'] + ': ' + issue['message'] for issue in diagnostics(self._buffer)))
        self._populating = prior
        self._sync_evidence_content()

    @staticmethod
    def _evidence_label(row):
        label = study_presentation.evidence_label(row)
        # Old generated captions appended identities. Change presentation only;
        # never rename a user file or modify the saved evidence label.
        for key in ('job_id', 'turn_id'):
            value = (row.get('reference') or {}).get(key)
            if value and label.endswith(' · ' + value):
                label = label[:-len(' · ' + value)]
        return label

    def _sync_evidence_content(self):
        row = self._row()
        evidence = None
        if row and self._selected[0] == 'evidence':
            evidence = row
            self._reading_evidence_id = row['id']
        else:
            evidence = next((item for item in self._buffer.get('evidence', [])
                             if item['id'] == self._reading_evidence_id), None)
        self.context_source.setVisible(evidence is not None)
        if evidence is not None:
            self.context_source.setText('자료 보기: ' + self._evidence_label(evidence))
            self.source_title.setToolTip(self._evidence_label(evidence))
            self._update_source_title()
            self.source_kind.setText({'result': '계산 결과', 'expert_turn': '대화', 'document': '문서', 'knowledge': '문헌'}.get(evidence['kind'], '자료'))
            self._update_reading_title()
        self.followup_basis.setText(('판단: ' if self._selected and self._selected[0] == 'decisions' else '') +
            str(row.get('title', row.get('question', row.get('label', '')))) if row and self._selected[0] != 'evidence' else '')
        self.followup_basis.setVisible(bool(self.followup_basis.text()) and self.editor.isHidden())
        self.note_button.setEnabled(evidence is not None and not self._raw_mode)
        if evidence is None:
            self._content_key = self._content_reference = self._content_pending = None
            self.source_title.clear()
            self.source_title.setToolTip('')
            self.source_kind.setText('자료를 선택하세요.')
            self.reading.clear('자료 목록에서 대화 발언이나 계산 결과를 선택하세요.')
            self.pin_response.setEnabled(False)
            self._update_preview_difference()
            return
        reference = deepcopy(evidence['reference'])
        key = (self._context(selection=True), evidence['id'], canonical_hash(reference))
        if key == self._content_key:
            return
        self._content_key = key
        history=reference.get('selection')
        fixed_history=isinstance(history,dict) and history.get('schema')=='caelab.impact-history-selection/1'
        if isinstance(reference.get('response'), str) and reference['response'] and not fixed_history:
            reference['selection'] = {'responses': [reference.pop('response')], 'rows': [0, 256]}
        self._content_reference = reference
        self._content_label = self._evidence_label(evidence)
        self.reading.clear('자료를 읽는 중…')
        self._content_pending = (key, deepcopy(reference))
        self.pin_response.setEnabled(False)
        self._update_preview_difference()
        self._schedule_content_read()

    def _schedule_content_read(self):
        if (not self._content_pending or self._content_queued or self._busy or self._callbacks
                or getattr(self, '_incoming_review', False) or getattr(self, '_allow_close', False)):
            return
        self._content_queued = True
        QTimer.singleShot(0, self._read_content)

    def _read_content(self):
        self._content_queued = False
        if (not self._content_pending or self._busy or self._callbacks
                or getattr(self, '_incoming_review', False) or getattr(self, '_allow_close', False)):
            return False
        key, reference = self._content_pending
        method = getattr(self.client, 'research_reference', None)
        self._content_pending = None
        if not callable(method):
            self.reading.clear('현재 연결에서는 자료 본문을 읽을 수 없습니다.')
            return False
        def relevant():
            return self._content_key == key and self._content_reference == reference
        def read():
            try:
                return method(reference), None
            except Exception as error:
                if reference.get('kind') != 'knowledge':
                    raise
                try:
                    source = self._knowledge_source(reference)
                except Exception:
                    return None, dict(status='UNAVAILABLE', message='보관된 문헌을 읽을 수 없습니다. 문헌을 다시 선택하세요.', detail=str(error))
                if source.get('status') == 'NO_MATCHING_SEGMENTS':
                    return None, dict(status='INVALID_LOCATOR', message='선택한 문헌 구간이 없습니다. 문헌 구간 선택에서 보관된 구간을 다시 고르세요.', detail=str(error))
                if (source.get('sha256') == reference.get('source_sha256')
                        and canonical_hash(source) == reference.get('content_sha256')):
                    return None, dict(status='UNAVAILABLE', message='문헌 읽기 응답을 받지 못했습니다. 다시 읽기를 눌러 확인하세요.', detail=str(error))
                return None, dict(status='STALE', message='연결한 문헌 원본 또는 선택 구간이 변경되었습니다. 기존 근거와 판단은 유지됩니다.', detail=str(error))
        def received(value):
            payload, problem = value
            if problem:
                self._reference_checks[key[1]] = problem
                self._populate_evidence()
                self.reading.clear('자료 읽기 실패: ' + problem['message'])
                self.reading.body.setToolTip(problem['detail'])
                return
            # Content reads update only availability, never research judgment.
            evidence_id = key[1]
            self._reference_checks[evidence_id] = {
                'status': payload.get('status', 'UNKNOWN'), 'message': payload.get('message', '')}
            self._populate_evidence()
            self.reading.set_payload(payload, label=self._content_label)
            self.pin_response.setEnabled(reference.get('kind') == 'result' and
                self._selected is not None and self._selected[0] == 'evidence' and 'selection' in reference)
            self._update_preview_difference()
            # Legacy evidence with no channel selection gets a bounded, visible
            # first-channel preview. The saved reference changes only on Keep.
            if (reference.get('kind') == 'result' and 'selection' not in reference
                    and 'response' not in reference and self.reading.channel.count()):
                self.read_response(str(self.reading.channel.itemData(0)))
        def rejected(error):
            self._reference_checks[key[1]] = {'status': 'UNAVAILABLE', 'message': str(error)}
            self._populate_evidence()
            self.reading.clear('자료 읽기 실패: ' + str(error))
        started = self._call(read, received, relevant=relevant, rejected=rejected)
        if not started:
            self._content_pending = (key, reference)
        return started

    def read_response(self, name):
        if not self._content_reference or self._content_reference.get('kind') != 'result':
            return
        reference = deepcopy(self._content_reference)
        history=reference.get('selection')
        if isinstance(history,dict) and history.get('schema')=='caelab.impact-history-selection/1':
            index=self.reading.channel.findData(reference.get('response'))
            self.reading.channel.blockSignals(True)
            self.reading.channel.setCurrentIndex(index)
            self.reading.channel.blockSignals(False)
            self.reading._draw_result()
            if name!=reference.get('response'):
                self.message.setText('저장한 이력의 구간과 적분을 유지합니다. 다른 이력은 해석 창에서 새로 선택하세요.')
            return
        reference.pop('response', None)
        reference['selection'] = {'responses': [name], 'rows': [0, 256]}
        self._content_reference = reference
        self.reading.clear('Reading ' + name + '…')
        self._content_pending = (self._content_key, reference)
        self._update_preview_difference()
        self._schedule_content_read()

    def _update_preview_difference(self):
        def channels(reference):
            selection = reference.get('selection', {})
            values = selection.get('responses', []) if isinstance(selection, dict) else selection
            return list(values) if isinstance(values, list) and values else [reference['response']] if reference.get('response') else []
        preview = self._content_reference or {}
        evidence = next((row for row in self._buffer.get('evidence', [])
                         if row['id'] == self._reading_evidence_id), None)
        saved = (evidence or {}).get('reference', {})
        current, recorded = channels(preview), channels(saved)
        differs = preview.get('kind') == 'result' and bool(current) and current != recorded
        self.preview_difference.setText('연구에 연결된 성분: ' + ', '.join(recorded)
            if recorded else '이 성분은 아직 연구에 연결되지 않았습니다.')
        self.preview_difference.setVisible(differs)
        self.pin_response.setVisible(differs)

    def keep_response_selection(self):
        row = self._row()
        if (not row or self._selected[0] != 'evidence' or not self._content_reference
                or self._content_reference.get('kind') != 'result' or self._busy):
            return
        row['reference'] = deepcopy(self._content_reference)
        self._edited()
        self._populate_evidence()
        self._sync_evidence_content()

    def _detail_edited(self, *_):
        if self._populating or not self._row():
            return
        row = self._row()
        original = self._detail_original
        title_key = 'title' if 'title' in row else 'question' if 'question' in row else 'label'
        text_key = 'statement' if 'statement' in row else 'note'
        original_title = self._evidence_label(original) if self._selected[0] == 'evidence' else str(original[title_key])
        row[title_key] = deepcopy(original[title_key]) if self.detail_title.text() == original_title else self.detail_title.text()
        original_text = study_presentation.evidence_note(original) if self._selected[0]=='evidence' else str(original[text_key])
        row[text_key] = deepcopy(original[text_key]) if self.detail_text.toPlainText() == original_text else self.detail_text.toPlainText()
        if 'status' in row:
            row['status'] = deepcopy(self.detail_status.currentData())
        for key, choices in self.link_lists.items():
            if key in row:
                values = [choices.item(index).data(DATA) for index in range(choices.count())
                          if choices.item(index).checkState() == Qt.CheckState.Checked]
                row[key] = deepcopy(original[key]) if values == (original[key] if isinstance(original[key], list) else []) else values
        self._edited()
        self._populate_entries()
        self._populate_evidence()
        self._sync_evidence_content()

    def add_entry(self, kind):
        if not self.document or self._raw_mode or self._busy or self._callbacks:
            return
        selected = self._row()
        evidence_id = self._selected[1] if self._selected and self._selected[0] == 'evidence' else None
        hypothesis_ids = ([self._selected[1]] if self._selected and self._selected[0] == 'hypotheses'
                          else deepcopy((selected or {}).get('hypothesis_ids', [])))
        identifier = {'hypotheses': 'H', 'decisions': 'J', 'next_observations': 'O'}[kind] + uuid.uuid4().hex
        if kind == 'hypotheses':
            row = {'id': identifier, 'title': '새 가설', 'statement': '', 'status': 'UNKNOWN'}
        elif kind == 'decisions':
            row = {'id': identifier, 'title': '새 판단', 'statement': '', 'hypothesis_ids': [],
                   'supporting': [], 'conflicting': [], 'status': 'UNKNOWN'}
        else:
            row = {'id': identifier, 'question': '다음 확인사항', 'hypothesis_ids': [], 'evidence_ids': [], 'status': 'UNKNOWN', 'note': ''}
        if 'hypothesis_ids' in row:
            row['hypothesis_ids'] = hypothesis_ids
        if evidence_id:
            if kind == 'next_observations':
                row['evidence_ids'] = [evidence_id]
            # A judgment has no neutral stored evidence relation. Keep the
            # reading context; supporting/conflicting remain an explicit choice.
            self._entry_read_context[(self._context(), identifier)] = evidence_id
        self._buffer[kind].append(row)
        self._selected = (kind, identifier)
        self._selection_serial += 1
        self._edited()
        self._populate_entries()
        self._show_detail()
        self._update_actions()
        self._show_editor()

    def remove_entry(self):
        if not self._row() or self._busy or self._callbacks:
            return
        if self._pending_literature_target():
            self.message.setText(PENDING_LITERATURE_TARGET)
            return False
        kind, identifier = self._selected
        self._buffer[kind] = [row for row in self._buffer[kind] if row['id'] != identifier]
        self._selected = None
        if kind == 'evidence' and self._reading_evidence_id == identifier:
            self._reading_evidence_id = None
        self._selection_serial += 1
        self._edited()
        self._populate_entries()
        self._populate_evidence()
        self._show_detail()

    def receive_pending_result(self, message):
        return self._result_return.receive(message)

    def _call(self, function, accepted, *, background=False, relevant=None, rejected=None):
        if getattr(self, '_incoming_review', False):
            return False
        return super()._call(function, accepted, background=background, relevant=relevant, rejected=rejected)

    def closeEvent(self, event):
        if getattr(self, '_incoming_review', False):
            event.ignore()
            return
        if self._allow_close and getattr(self, '_result_return', None):
            self._result_return.close()
        if self._allow_close:
            from .portable_research_actions import close_children
            close_children(self)
        super().closeEvent(event)

    def open_document(self, *, document_id=None, title='새 연구 기록', draft=None):
        context = self._context()
        return self._call(lambda: self.client.document_open(kind='study', title=title, draft=draft,
            document_id=document_id), self._opened, relevant=lambda: self._context() == context)

    def command(self, operation, arguments=None, *, after=None):
        if not self.document or self.conflict:
            return False
        if operation in {'document.undo', 'document.redo'} and self._pending_literature_owner():
            self.message.setText('문헌 연결 결과 확인을 먼저 눌러 주세요. 확인 전에는 이 연구 기록의 실행 취소와 다시 실행을 할 수 없습니다.')
            return False
        if self._raw_mode:
            try:
                if not isinstance(json.loads(self.raw.toPlainText()), dict):
                    raise ValueError('Draft must be a JSON object')
            except ValueError:
                self.message.setText('Raw draft is not a JSON object. Its text remains in the editor; repair it before Apply or Save.')
                return False
        document, context = deepcopy(self.document), self._context()
        submitted = self.edited_draft()
        edit_serial = self._edit_serial
        def received(receipt):
            late = self._edit_serial != edit_serial or canonical_hash(self.edited_draft()) != canonical_hash(submitted)
            self.local_dirty = late
            self._show_document(receipt['document'], preserve_buffer=late)
            if late:
                self.message.setText('이전 편집을 적용했습니다. 그동안 입력한 내용은 그대로 남아 있습니다.')
            else:
                self.message.setText('저장했습니다.' if operation == 'document.save' else '편집을 적용했습니다.')
            if after and not late:
                QTimer.singleShot(0, after)
        return self._call(lambda: self.client.document_command(document['id'], operation, deepcopy(arguments or {}),
            session_id=document['session_id'], expected_generation=document['generation'], command_id='C' + uuid.uuid4().hex),
            received, relevant=lambda: self._context() == context)

    def apply_inputs(self, *, after=None):
        return self.command('study.update', {'draft': self.edited_draft()}, after=after)

    def save_document(self, *, after=None):
        if self.local_dirty:
            return self.apply_inputs(after=lambda: self.save_document(after=after))
        return self.command('document.save', after=after)

    def refresh_document(self):
        if not self.document or self._busy or self._callbacks:
            return False
        context = self._context()
        def received(remote):
            changed = remote['session_id'] != self.document['session_id'] or canonical_hash(remote['draft']) != canonical_hash(self.document['draft'])
            if self.local_dirty and changed:
                self.conflict = True
                self.message.setText('Study owner changed while editing. Your local research entries remain; reload or keep a new Study.')
            elif not self.conflict:
                if changed:self._show_document(remote)
                else:
                    self.document=deepcopy(remote)
                    self._update_actions()
        return self._call(lambda: self.client.document_read(context[0]), received, background=True,
                          relevant=lambda: self._context() == context)

    def reload_remote(self):
        if self.document:
            context = self._context()
            self._call(lambda: self.client.document_read(context[0]), self._opened, relevant=lambda: self._context() == context)

    def _modal(self, function):
        self._callbacks += 1
        self._update_actions()
        try:
            return function()
        finally:
            self._callbacks -= 1
            self._update_actions()

    def choose_document(self):
        def begin():
            context = self._context()
            def listed(payload):
                rows = [row for row in payload['documents'] if row.get('kind') == 'study']
                labels = [str(index + 1) + '. ' + row['title'] for index, row in enumerate(rows)]
                if not labels:
                    self.message.setText('저장된 연구 기록이 없습니다. 새 연구 기록을 만들 수 있습니다.')
                    return
                chosen, accepted = self._modal(lambda: QInputDialog.getItem(self, '연구 기록 열기', '연구 기록', labels, editable=False))
                if accepted and self._context() == context:
                    self.open_document(document_id=rows[labels.index(chosen)]['id'])
            self._call(self.client.documents, listed, relevant=lambda: self._context() == context)
        self._leave(begin)

    def new_document(self):
        self._leave(lambda: self.open_document())

    def _leave(self, continuation):
        if self._busy or self._callbacks:
            self.message.setText('현재 작업이 끝난 뒤 다른 문서를 열어 주세요.')
            return
        if not self.document or not (self.local_dirty or self.document.get('dirty')):
            continuation()
            return
        answer = self._modal(lambda: QMessageBox.question(self, '저장하지 않은 변경', '변경한 내용을 저장할까요?',
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel))
        if answer == QMessageBox.StandardButton.Save:
            self.save_document(after=continuation)
        elif answer == QMessageBox.StandardButton.Discard:
            continuation()

    def choose_literature(self):
        if not self.document or self._raw_mode or self._busy or self._callbacks or self.conflict:
            return False
        from .experiment_sources import choose_knowledge
        def selected(reference, label):
            identifier = 'E' + uuid.uuid4().hex
            self._buffer['evidence'].append({'id': identifier, 'label': label,
                'kind': 'knowledge', 'reference': deepcopy(reference), 'note': ''})
            self._selected = ('evidence', identifier)
            self._selection_serial += 1
            self._edited(); self._populate_evidence(); self._show_detail()
        self._modal(lambda: choose_knowledge(self.client, self, selected))

    def _knowledge_source(self, reference, *, locator=None):
        from .expert_sources import assist
        return assist(self.client, 'knowledge.source', {
            'document_id': reference['document_id'], 'revision': reference['revision'],
            'locator': deepcopy(reference['locator'] if locator is None else locator)})

    def _literature_selection(self):
        row = self._row()
        if (not row or self._selected[0] != 'evidence' or row.get('kind') != 'knowledge'
                or self._raw_mode or self._busy or self._callbacks or self.conflict):
            return None
        context, reference = self._context(selection=True), deepcopy(row['reference'])
        def relevant():
            current = self._row()
            return (self._context(selection=True) == context and current is not None
                    and current.get('reference') == reference)
        return row, reference, relevant

    def _pending_literature_target(self):
        pending, row = self._literature_pending, self._row()
        return bool(pending and row and pending['owner'] == self._context()
            and self._selected == ('evidence', pending['evidence_id'])
            and row.get('reference') == pending['reference'])

    def _pending_literature_owner(self):
        return bool(self._literature_pending and self._literature_pending['owner'] == self._context())

    def _append_literature(self, source, locator, label):
        if source.get('status') != 'AVAILABLE':
            self.message.setText('보관된 문헌 구간을 읽을 수 없습니다. 기존 근거는 유지됩니다.')
            return False
        reference = {'kind': 'knowledge', 'document_id': source['document_id'],
            'revision': source['revision'], 'locator': deepcopy(locator),
            'source_sha256': source['sha256'], 'content_sha256': canonical_hash(source)}
        identifier = 'E' + uuid.uuid4().hex
        self._buffer['evidence'].append({'id': identifier, 'label': label,
            'kind': 'knowledge', 'reference': reference, 'note': ''})
        self._selected = ('evidence', identifier)
        self._selection_serial += 1
        self._edited(); self._populate_evidence(); self._show_detail()
        return True

    def choose_literature_segment(self):
        target = self._literature_selection()
        if target is None:
            return False
        row, reference, relevant = target
        label = row['label']
        def loaded(source):
            if source.get('status') != 'AVAILABLE' or source.get('sha256') != reference['source_sha256']:
                self.message.setText('보관된 원문을 확인할 수 없습니다. 기존 근거는 유지됩니다.')
                return
            segments = source.get('segments', [])
            labels = ['전체 보관 본문']
            for index, segment in enumerate(segments, 1):
                locator = segment.get('locator', {})
                position = ('쪽 ' + str(locator['page']) if 'page' in locator else
                    str(locator.get('section') or '본문'))
                if 'line_start' in locator:
                    position += ' · 행 ' + str(locator['line_start']) + '–' + str(locator['line_end'])
                labels.append(str(index) + '. ' + position)
            chosen, accepted = self._modal(lambda: QInputDialog.getItem(self,
                '문헌 구간 선택', '실제로 읽고 근거로 보관할 구간', labels, editable=False))
            if not accepted or not relevant():
                return
            index = labels.index(chosen)
            locator = {} if index == 0 else deepcopy(segments[index - 1]['locator'])
            def selected(payload):
                if payload.get('sha256') != reference['source_sha256']:
                    self.message.setText('선택 중 원문이 변경되었습니다. 기존 근거는 유지됩니다.')
                    return
                if self._append_literature(payload, locator, label + (' 선택 구간' if locator else ' 보관 본문')):
                    self.message.setText('읽은 구간을 새 근거로 추가했습니다. 기존 근거와 판단 연결은 유지됩니다.')
            # Defer until the current callback releases the worker guard.
            QTimer.singleShot(0, lambda: self._call(lambda: self._knowledge_source(reference, locator=locator),
                selected, relevant=relevant) if relevant() else None)
        return self._call(lambda: self._knowledge_source(reference, locator={}), loaded, relevant=relevant)

    def reconnect_literature_file(self, filename=None):
        target = self._literature_selection()
        if target is None:
            return False
        row, reference, relevant = target
        owner, evidence_id = self._context(), row['id']
        pending = self._literature_pending
        if self._pending_literature_target():
            return self._resume_literature_file(pending, relevant)
        if pending:
            self.message.setText('먼저 “' + pending['study_title'] + '”의 “' + pending['label']
                + '” 자료에서 문헌 연결 결과 확인을 눌러 주세요. 미확정 연결을 유지합니다.')
            return False
        if filename is None:
            filename, _ = self._modal(lambda: QFileDialog.getOpenFileName(self,
                '문헌 파일 다시 연결', '', '연구 문헌 (*.pdf *.md *.txt *.csv)'))
        if not filename or not relevant():
            return False
        path = Path(filename)
        if path.suffix.lower() not in {'.pdf', '.md', '.txt', '.csv'}:
            self.message.setText('PDF, Markdown(.md), UTF-8 텍스트 또는 CSV를 선택하세요.')
            return False
        def inspect():
            with path.open('rb') as stream:
                data = stream.read(16 * 1024 * 1024 + 1)
            if len(data) > 16 * 1024 * 1024:
                raise ValueError('문헌 파일은 16 MiB 이내로 선택하세요.')
            source = self._knowledge_source(reference, locator={})
            if source.get('sha256') != reference['source_sha256']:
                raise ValueError('보관된 원문이 일치하지 않습니다. 기존 근거는 유지됩니다.')
            return data, source
        def inspected(value):
            data, source = value
            if hashlib.sha256(data).hexdigest() == reference['source_sha256']:
                self.message.setText('같은 내용의 파일입니다. 이동한 경로와 관계없이 기존 보관 원문과 판단을 유지합니다.')
                return
            answer = self._modal(lambda: QMessageBox.question(self, '내용이 다른 문헌',
                '선택한 파일의 내용이 다릅니다. 새 개정과 새 근거로 추가할까요?\n기존 근거와 판단 연결은 그대로 유지됩니다.',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel))
            if answer != QMessageBox.StandardButton.Yes or not relevant():
                return
            pending = {'owner': owner, 'evidence_id': evidence_id, 'reference': reference, 'data': data,
                'study_title': self.document['title'], 'label': row['label'],
                'name': path.name, 'collection': source['collection'],
                'request_id': 'study-source-' + uuid.uuid4().hex, 'arguments': None, 'job_id': None}
            self._literature_pending = pending
            QTimer.singleShot(0, lambda: self._resume_literature_file(pending, relevant) if relevant() else None)
        return self._call(inspect, inspected, relevant=relevant)

    def _resume_literature_file(self, pending, relevant):
        def run():
            if pending['arguments'] is None:
                upload = self.client.upload(pending['name'], pending['data'])
                pending['arguments'] = {'data_id': upload['id'], 'collection': pending['collection'],
                    'document_id': pending['reference']['document_id']}
            if pending['job_id'] is None:
                job = self.client.submit('knowledge.ingest', pending['arguments'], request_id=pending['request_id'])
                pending['job_id'] = job['id']
            deadline = time.monotonic() + 20
            while True:
                status = self.client.status(pending['job_id'])
                if status['state'] == 'SUCCEEDED':
                    result = self.client.result(pending['job_id'])
                    return self._knowledge_source(dict(result, locator={}), locator={})
                if status['state'] in {'FAILED', 'CANCELLED', 'REJECTED'}:
                    pending['terminal_failure'] = True
                    raise ValueError('문헌 가져오기에 실패했습니다. 기존 근거와 판단은 유지됩니다.')
                if time.monotonic() >= deadline:
                    raise TimeoutError('문헌 가져오기가 진행 중입니다. 파일 다시 연결을 눌러 같은 작업을 확인하세요.')
                time.sleep(.05)
        def received(source):
            if self._append_literature(source, {}, pending['name']):
                self._literature_pending = None
                self.message.setText('다른 내용을 새 개정과 새 근거로 추가했습니다. 기존 판단은 원래 근거를 계속 가리킵니다.')
        def rejected(error):
            if pending.get('terminal_failure'):
                self._literature_pending = None
            self.message.setText('문헌을 연결하지 못했습니다. 기존 근거와 판단은 유지됩니다. ' + error)
        self.message.setText('문헌의 새 개정을 보관하는 중… 응답이 끊기면 파일 다시 연결에서 재시도할 수 있습니다.')
        return self._call(run, received, relevant=relevant, rejected=rejected)

    def replace_literature(self):
        row = self._row()
        if (not row or self._selected[0] != 'evidence' or row.get('kind') != 'knowledge'
                or self._raw_mode or self._busy or self._callbacks or self.conflict):
            return False
        if self._pending_literature_target():
            self.message.setText(PENDING_LITERATURE_TARGET)
            return False
        from .experiment_sources import choose_knowledge
        context = self._context(selection=True)
        def selected(reference, _label):
            if self._context(selection=True) != context:
                return
            row['reference'] = deepcopy(reference)
            self._reference_checks.pop(row['id'], None)
            self._edited(); self._populate_evidence(); self._show_detail()
            self.message.setText('문헌을 다시 연결했습니다. 메모와 판단은 유지됩니다. 내용을 확인하고 저장하세요.')
        self._modal(lambda: choose_knowledge(self.client, self, selected, reference=deepcopy(row['reference'])))

    def open_report(self):
        if self.local_dirty or not self.document or self.document.get('dirty') or not self.document.get('saved_revision'):
            self.message.setText('연구 기록을 저장한 뒤 보고서로 적용하세요.')
            return False
        from .report_window import ReportWindow
        window = ReportWindow(self.client, auto_open=False)
        self._report_windows = getattr(self, '_report_windows', []) + [window]
        study = deepcopy(self.document)
        def opened(document):
            window._opened(document)
            # No assets yet: schedule Study apply after the initial empty read settles.
            def apply():
                if window._busy:
                    QTimer.singleShot(20, apply)
                elif not window._closed:
                    window.use_study(study)
            QTimer.singleShot(0, apply)
        window._call(lambda: self.client.document_open(kind='report'), opened)
        window.show()

    def choose_evidence(self, kind):
        if not self.document or self._raw_mode or self._busy or self._callbacks:
            return False
        context, draft_hash = self._context(selection=True), canonical_hash(self.edited_draft())
        def relevant():
            return self._context(selection=True) == context and canonical_hash(self.edited_draft()) == draft_hash
        def pin(reference, label):
            if not relevant():
                return
            issue = reference_error(reference)
            if issue:
                self.message.setText('Source reference is incomplete: ' + issue)
                return
            identifier = 'E' + uuid.uuid4().hex
            self._buffer['evidence'].append({'id': identifier, 'label': label, 'kind': kind, 'reference': deepcopy(reference), 'note': ''})
            self._selected = ('evidence', identifier)
            self._selection_serial += 1
            self._edited()
            self._populate_evidence()
            self._show_detail()
            self.message.setText('선택한 자료를 추가했습니다.')
        def read(source):
            if kind == 'document':
                if not source.get('saved_revision') or source.get('dirty') or not {'id', 'kind', 'input_revision', 'draft', 'title'} <= source.keys():
                    self.message.setText('Save the original document in its own editor before linking its exact revision.')
                    return
                pin({'kind': kind, 'document_kind': source['kind'], 'document_id': source['id'],
                     'saved_revision': source['saved_revision'], 'input_revision': source['input_revision'],
                     'input_sha256': canonical_hash(source['draft'])}, source['title'])
            elif kind == 'result':
                rows = [row for row in source.get('runs', []) if row.get('retained_result') and row.get('retention_complete')]
                labels = ['계산 ' + str(index + 1) + ' — ' + str(row.get('retained_state', 'UNKNOWN')) for index, row in enumerate(rows)]
                if not rows:
                    self.message.setText('No exact retained result is available. Save completed results in their original editor first.')
                    return
                chosen, accepted = self._modal(lambda: QInputDialog.getItem(self, '계산 결과 추가', '계산 선택', labels, editable=False))
                if accepted and relevant():
                    job = rows[labels.index(chosen)]['job_id']
                    self._call(lambda: self.client.document_result_reference(source['id'], job),
                               lambda reference: pin({'kind': kind, **reference}, source['title']), relevant=relevant)
            else:
                if source.get('kind') != 'expert' or not source.get('saved_revision') or source.get('dirty'):
                    self.message.setText('Select a saved, unchanged Discussion. Study cannot silently save or copy pending Expert output.')
                    return
                turns = source.get('discussion', {}).get('turns', [])
                labels = [str(index + 1) + '. ' + str(turn.get('author', turn.get('role', 'Participant'))) + ': ' + str(turn.get('text') or turn.get('status', ''))[:90] for index, turn in enumerate(turns)]
                if not labels:
                    self.message.setText('이 대화에는 저장된 발언이 없습니다.')
                    return
                chosen, accepted = self._modal(lambda: QInputDialog.getItem(self, '대화 발언 추가', '발언 선택', labels, editable=False))
                if accepted and relevant():
                    turn = turns[labels.index(chosen)]
                    pin({'kind': kind, 'discussion_id': source['id'], 'saved_revision': source['saved_revision'],
                         'turn_id': turn['id'], 'turn_sha256': canonical_hash(turn)}, source['title'] + ' — ' + str(turn.get('author', turn.get('role', 'Participant'))) + ': ' + ' '.join(str(turn.get('text') or turn.get('status', '')).split())[:70])
        def listed(payload):
            rows = [row for row in payload['documents'] if row.get('kind') != 'study' and (kind != 'expert_turn' or row.get('kind') == 'expert')]
            labels = [str(index + 1) + '. ' + row['title'] + ' (' + row['kind'] + ')' for index, row in enumerate(rows)]
            if not labels:
                self.message.setText('추가할 수 있는 문서가 없습니다.')
                return
            chosen, accepted = self._modal(lambda: QInputDialog.getItem(self, '자료 추가', '문서 선택', labels, editable=False))
            if accepted and relevant():
                self._call(lambda: self.client.document_read(rows[labels.index(chosen)]['id']), read, relevant=relevant)
        return self._call(self.client.documents, listed, relevant=relevant)

    def edit_evidence_note(self):
        if self._busy or self._callbacks or self._raw_mode:
            return False
        evidence_id = self._content_key[1] if self._content_key else None
        if evidence_id and any(row['id'] == evidence_id for row in self._buffer['evidence']):
            self._select(('evidence', evidence_id))
            self._show_editor()
            return True
        return False

    def show_diagnostics(self):
        dialog = QDialog(self)
        dialog.setWindowTitle('연구 문서 진단 상세')
        dialog.resize(800, 600)
        layout = QVBoxLayout(dialog)
        # Preserve the same raw editor and its partial text across modal close.
        layout.addWidget(self.raw)
        self.raw.show()
        close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close.rejected.connect(dialog.reject)
        layout.addWidget(close)
        self._modal(dialog.exec)
        layout.removeWidget(self.raw)
        self.raw.setParent(self)
        self.raw.hide()

    def retry_content(self):
        if not self._content_key or not self._content_reference:
            return False
        self.reading.clear('자료를 다시 읽는 중…')
        self._content_pending = (self._content_key, deepcopy(self._content_reference))
        self._schedule_content_read()
        return True

    def check_references(self):
        if not self.document or self._busy or self._callbacks:
            return False
        if self.local_dirty:
            # Re-read this exact selection without applying or discarding notes.
            return self.retry_content()
        method = getattr(self.client, 'study_references', None)
        if not callable(method):
            self.message.setText('Reference resolution is unavailable on this service. Existing exact links remain editable and saveable.')
            return False
        context, draft_hash = self._context(), canonical_hash(self.edited_draft())
        def received(payload):
            self._reference_checks = {row['evidence_id']: row for row in payload['references']}
            self._populate_evidence()
            self._show_detail()
            self.retry_content()
        return self._call(lambda: method(self.document['id']), received,
            relevant=lambda: self._context() == context and canonical_hash(self.edited_draft()) == draft_hash)

    def _navigation_context(self):
        if not self.document or self.local_dirty or self.document.get('dirty') or not self.document.get('saved_revision'):
            self.message.setText('변경 내용을 저장한 뒤 이어갈 수 있습니다.')
            return None
        if diagnostics(self._buffer):
            self.message.setText('Study has unresolved structural diagnostics. Edit or retain its draft before selecting a follow-up basis.')
            return None
        row = self._row()
        ids = set()
        if row:
            if self._selected[0] == 'evidence':
                ids.add(row['id'])
            for key in ('supporting', 'conflicting', 'evidence_ids'):
                ids.update(row.get(key, []) if isinstance(row.get(key), list) else [])
            if self._selected[0] == 'hypotheses':
                for decision in self._buffer['decisions']:
                    if row['id'] in decision['hypothesis_ids']:
                        ids.update(decision['supporting'] + decision['conflicting'])
        return {'study_id': self.document['id'], 'saved_revision': self.document['saved_revision'],
                'input_revision': self.document['input_revision'], 'input_sha256': canonical_hash(self.document['draft']),
                'question': self._buffer['question'], 'selected_kind': self._selected[0] if row else None,
                'selected_id': row['id'] if row else None, 'selected_entry': deepcopy(row),
                'evidence': [deepcopy(item['reference']) for item in self._buffer['evidence'] if item['id'] in ids],
                'engineering_release': 'NOT_RELEASED'}

    def _navigate(self, kind, payload):
        callback = self._navigation[kind]
        if callback is None:
            getattr(self, kind + '_open_requested').emit(deepcopy(payload))
            self.message.setText('Requested explicit ' + kind + ' navigation from the selected exact Study context.')
            return True
        context = self._context(selection=True)
        return self._call(lambda: callback(deepcopy(payload)),
            lambda receipt: self.message.setText('Opened selected ' + kind + ' context. Calculation and inference remain explicit.'),
            relevant=lambda: self._context(selection=True) == context)

    def open_reference(self):
        row = self._row()
        reference = self._content_reference if self._content_reference else (row or {}).get('reference')
        if reference and not reference_error(reference):
            return self._navigate('reference', reference)

    def request_followup(self, kind):
        if kind not in {'discussion', 'plan'} or self._busy or self._callbacks or self._raw_mode:
            return False
        if self.document and (self.local_dirty or self.document.get('dirty') or not self.document.get('saved_revision')):
            answer = self._modal(lambda: QMessageBox.question(self, '변경 내용 저장',
                '현재 내용을 저장하고 이어갈까요?',
                QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Save))
            if answer != QMessageBox.StandardButton.Save:
                return False
            selected = self._context(selection=True)
            def continue_saved():
                if self._context(selection=True) == selected:
                    self.request_followup(kind)
                else:
                    self.message.setText('선택이 변경되었습니다. 이어갈 항목을 확인하고 다시 눌러 주세요.')
            return self.save_document(after=continue_saved)
        context = self._navigation_context()
        if context is not None:
            return self._navigate(kind, context)

    def _update_actions(self):
        present = self.document is not None
        available = not self._busy and not self._callbacks and not getattr(self, '_incoming_review', False)
        enabled = present and available and not self.conflict
        self.apply_button.setEnabled(enabled and self.local_dirty)
        self.save_action.setEnabled(enabled)
        self.editor_save_button.setEnabled(enabled)
        self.undo_action.setEnabled(enabled and not self.local_dirty and not self._pending_literature_owner() and self.document.get('can_undo', False))
        self.redo_action.setEnabled(enabled and not self.local_dirty and not self._pending_literature_owner() and self.document.get('can_redo', False))
        self.new_action.setEnabled(available)
        self.open_action.setEnabled(available)
        self.question.setEnabled(present and not self._raw_mode)
        self._update_reading_title()
        self.question_edit_button.setEnabled(present and not self._raw_mode)
        self.add_source_button.setEnabled(enabled and not self._raw_mode)
        self.editor.setEnabled(present and not self._raw_mode and self._row() is not None)
        self.raw.setEnabled(present)
        for button in self.add_buttons + self.evidence_buttons:
            button.setEnabled(enabled and not self._raw_mode)
        pending_target = self._pending_literature_target()
        self.remove_button.setEnabled(enabled and self._row() is not None and not pending_target)
        self.remove_button.setToolTip(PENDING_LITERATURE_TARGET if pending_target else '')
        self.reference_button.setEnabled(enabled and bool(self._content_reference))
        self.note_button.setEnabled(enabled and bool(self._content_reference) and not self._raw_mode)
        self.check_button.setEnabled(enabled and bool(self._content_reference))
        row = self._row()
        literature = bool(row and self._selected[0] == 'evidence' and row.get('kind') == 'knowledge')
        self.replace_literature_button.setVisible(literature)
        self.replace_literature_button.setEnabled(enabled and literature and not self._raw_mode and not pending_target)
        self.replace_literature_button.setToolTip(PENDING_LITERATURE_TARGET if pending_target else '')
        self.literature_segment_action.setEnabled(enabled and literature and not self._raw_mode)
        self.literature_file_action.setEnabled(enabled and literature and not self._raw_mode)
        self.literature_file_action.setText('문헌 연결 결과 확인…' if pending_target else '문헌 파일 다시 연결…')
        for button in (self.discussion_button, self.plan_button):
            button.setEnabled(enabled and not self._raw_mode)
        self.reload_button.setVisible(self.conflict)
        self.copy_button.setVisible(self.conflict)
        self.reload_button.setEnabled(available)
        self.copy_button.setEnabled(available)
        if present:
            self.setWindowTitle(study_presentation.title(self.document) + (' *' if self.local_dirty or self.document.get('dirty') else ''))
            self.identity.setText('')
        self._schedule_content_read()

    def _update_reading_title(self):
        payload = self.reading.payload
        self.reading.title.setVisible(payload is not None and
            (payload.get('kind') != 'knowledge' or self.reading.title.text() != self.source_title.toolTip()))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--service', default=os.environ.get('CAELAB_SERVICE_URL'))
    parser.add_argument('--document-id')
    args = parser.parse_args(argv)
    if not args.service:
        parser.error('--service or CAELAB_SERVICE_URL is required')
    app = QApplication.instance() or QApplication(sys.argv[:1])
    from .desktop import open_saved_reference, open_study_followup
    client = Client(args.service)
    if args.document_id:
        from .result_return import activate_existing
        if activate_existing(client, args.document_id).get('status') == 'ACTIVATED':
            return 0
    window = StudyWindow(client, document_id=args.document_id,
        reference_open=lambda reference: open_saved_reference(client,reference),
        discussion_open=lambda context: open_study_followup(client,context,'expert'),
        plan_open=lambda context: open_study_followup(client,context,'numerical'))
    window.show()
    return app.exec()


if __name__ == '__main__':
    raise SystemExit(main())
