"""Independent Study question, competing hypotheses, evidence and judgment editor."""
from copy import deepcopy
import argparse
import json
import os
import sys
import uuid

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (QApplication, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QInputDialog,
    QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPushButton, QPlainTextEdit,
    QSplitter, QTabWidget, QToolBar, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

from caelab.study_document import (default_draft, diagnostics, reference_error, HYPOTHESIS_STATUSES,
    DECISION_STATUSES, OBSERVATION_STATUSES)
from caelab.storage import canonical_hash
from caelab.workbench_client import Client
from .numerical_window import NumericalWindow
from .runner_window import readonly_table
from .reference_content import ReferenceContent


DATA = Qt.ItemDataRole.UserRole
STATUS_LABELS = {'UNKNOWN': '미판단', 'PROVISIONAL': '잠정 판단', 'SUPPORTED': '지지 자료 있음',
    'CONFLICTED': '자료가 상충함', 'REFUTED': '반증됨', 'REJECTED': '기각',
    'NOT_RELEASED': '미승인', 'PLANNED': '확인 예정', 'OBSERVED': '관찰 기록됨'}


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
        super().__init__(client, document_id=document_id, poll_interval=poll_interval, auto_open=auto_open)

    def _build_ui(self):
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
        self.apply_button = QPushButton('편집 적용')
        self.apply_button.clicked.connect(self.apply_inputs)
        bar.addWidget(self.apply_button)
        self.identity = QLabel()
        self.identity.hide()
        files = self.menuBar().addMenu('파일(&F)')
        files.addActions([self.new_action, self.open_action, self.save_action])
        tools = self.menuBar().addMenu('도구(&T)')
        self.details_action = QAction('진단 상세…', self)
        self.details_action.triggered.connect(self.show_diagnostics)
        tools.addAction(self.details_action)
        root = QWidget()
        outer = QVBoxLayout(root)
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
        split = QSplitter(Qt.Orientation.Horizontal)
        outer.addWidget(split, 1)
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.addWidget(QLabel('연구 질문'))
        self.question = QPlainTextEdit()
        self.question.setObjectName('studyQuestion')
        self.question.setMaximumHeight(150)
        self.question.textChanged.connect(self._question_edited)
        left_layout.addWidget(self.question)
        left_layout.addWidget(QLabel('연구 내용'))
        self.issues = QTreeWidget()
        self.issues.setObjectName('studyIssues')
        self.issues.setHeaderLabels(['내용', '상태'])
        self.issues.setColumnWidth(0, 190)
        self.issues.itemSelectionChanged.connect(self._issue_selected)
        left_layout.addWidget(self.issues, 1)
        add = QVBoxLayout()
        self.add_buttons = []
        for label, kind in (('가설 추가', 'hypotheses'), ('판단 작성', 'decisions'), ('다음 확인사항', 'next_observations')):
            button = QPushButton(label)
            button.clicked.connect(lambda checked=False, kind=kind: self.add_entry(kind))
            add.addWidget(button)
            self.add_buttons.append(button)
        left_layout.addLayout(add)
        self.remove_button = QPushButton('선택 항목 삭제')
        self.remove_button.clicked.connect(self.remove_entry)
        left_layout.addWidget(self.remove_button)
        split.addWidget(left)
        right = QWidget()
        right_layout = QVBoxLayout(right)
        self.tabs = QTabWidget()
        self.reading = ReferenceContent()
        self.reading.response_requested.connect(self.read_response)
        self.tabs.addTab(self.reading, '자료·결과')
        self.pin_response = QPushButton('선택한 결과로 바꾸기')
        self.pin_response.clicked.connect(self.keep_response_selection)
        reading_actions = QHBoxLayout()
        self.note_button = QPushButton('메모 작성')
        self.note_button.clicked.connect(self.edit_evidence_note)
        reading_actions.addWidget(self.note_button)
        reading_actions.addWidget(self.pin_response)
        reading_actions.addStretch()
        self.reading.layout().addLayout(reading_actions)
        self.editor = QWidget()
        detail = QVBoxLayout(self.editor)
        self.detail_identity = QLabel('편집할 내용을 선택하세요.')
        detail.addWidget(self.detail_identity)
        self.context_source = QPushButton()
        self.context_source.clicked.connect(lambda: self.tabs.setCurrentWidget(self.reading))
        self.context_source.hide()
        detail.addWidget(self.context_source)
        form = QFormLayout()
        self.detail_title = QLineEdit()
        self.detail_title.setObjectName('studyEntryTitle')
        self.detail_text = QPlainTextEdit()
        self.detail_text.setObjectName('studyEntryStatement')
        self.detail_text.setMaximumHeight(200)
        self.detail_status = QComboBox()
        form.addRow('제목', self.detail_title)
        form.addRow('내용·메모', self.detail_text)
        form.addRow('판단 상태', self.detail_status)
        detail.addLayout(form)
        self.detail_title.textEdited.connect(self._detail_edited)
        self.detail_text.textChanged.connect(self._detail_edited)
        self.detail_status.currentIndexChanged.connect(self._detail_edited)
        refs = QHBoxLayout()
        self.link_lists, self.link_panels = {}, {}
        for key, label in (('hypothesis_ids', '관련 가설'), ('supporting', '지지하는 자료'),
                           ('conflicting', '반박하는 자료'), ('evidence_ids', '참고 자료')):
            panel = QWidget()
            column = QVBoxLayout(panel)
            column.setContentsMargins(0, 0, 0, 0)
            column.addWidget(QLabel(label))
            choices = QListWidget()
            choices.setObjectName('study_' + key)
            choices.itemChanged.connect(self._detail_edited)
            column.addWidget(choices)
            self.link_lists[key], self.link_panels[key] = choices, panel
            refs.addWidget(panel)
        detail.addLayout(refs, 1)
        self.reference_detail = QPlainTextEdit()
        self.reference_detail.setReadOnly(True)
        self.reference_detail.setMaximumHeight(150)
        self.reference_detail.hide()
        self.tabs.addTab(self.editor, '메모·판단')
        self.raw = QPlainTextEdit(self)
        self.raw.setObjectName('studyRawDraft')
        self.raw.textChanged.connect(self._raw_edited)
        self.raw.hide()  # Open only through the explicit diagnostics action.
        right_layout.addWidget(self.tabs, 1)
        right_layout.addWidget(QLabel('자료와 계산 결과'))
        self.evidence = readonly_table(['자료·결과', '종류', '선택한 내용', '읽기 상태'])
        self.evidence.setObjectName('studyEvidence')
        self.evidence.setMaximumHeight(180)
        self.evidence.itemSelectionChanged.connect(self._evidence_selected)
        right_layout.addWidget(self.evidence)
        links = QHBoxLayout()
        self.evidence_buttons = []
        for label, kind in (('문서 추가…', 'document'), ('계산 결과 추가…', 'result'), ('대화 발언 추가…', 'expert_turn')):
            button = QPushButton(label)
            button.clicked.connect(lambda checked=False, kind=kind: self.choose_evidence(kind))
            links.addWidget(button)
            self.evidence_buttons.append(button)
        right_layout.addLayout(links)
        navigation = QHBoxLayout()
        self.reference_button = QPushButton('원래 프로그램에서 열기')
        self.check_button = QPushButton('다시 읽기')
        self.discussion_button = QPushButton('추가 질문…')
        self.plan_button = QPushButton('다음 계산…')
        self.reference_button.clicked.connect(self.open_reference)
        self.check_button.clicked.connect(self.check_references)
        self.discussion_button.clicked.connect(lambda: self.request_followup('discussion'))
        self.plan_button.clicked.connect(lambda: self.request_followup('plan'))
        for button in (self.reference_button, self.check_button, self.discussion_button, self.plan_button):
            navigation.addWidget(button)
        right_layout.addLayout(navigation)
        split.addWidget(right)
        left.setMinimumWidth(260); left.setMaximumWidth(350)
        split.setSizes([310, 1130])
        self.setCentralWidget(root)
        self._update_actions()

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
            self._buffer['question'] = self.question.toPlainText()
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
        self.question.setPlainText(str(self._buffer.get('question', '')))
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
                       'UNAVAILABLE': '읽을 수 없음', 'INVALID': '잘못된 참조'}.get(check.get('status'), '읽기 전')
            for column, value in enumerate((self._evidence_label(row), {'expert_turn': '대화', 'result': '계산 결과', 'document': '문서'}.get(row['kind'], row['kind']), identity, message)):
                self._set_cell(self.evidence, index, column, value, False)
            if self._selected == ('evidence', row['id']):
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
            self.tabs.setCurrentWidget(self.editor)
            self.detail_text.setFocus()

    def _evidence_selected(self):
        rows = self.evidence.selectionModel().selectedRows()
        if len(rows) == 1:
            self.issues.blockSignals(True)
            self.issues.clearSelection()
            self.issues.blockSignals(False)
            self._select(('evidence', self._buffer['evidence'][rows[0].row()]['id']))
            self.tabs.setCurrentWidget(self.reading)

    def _show_detail(self):
        prior, self._populating = self._populating, True
        row = self._row()
        self._detail_original = deepcopy(row)
        self.detail_identity.setText({'hypotheses': '가설', 'decisions': '판단', 'next_observations': '다음 확인사항', 'evidence': '자료 메모'}.get(self._selected[0], '') if row else '편집할 내용을 선택하세요.')
        title = str(row.get('title', row.get('question', row.get('label', '')))) if row else ''
        text = str(row.get('statement', row.get('note', ''))) if row else ''
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
        for key, choices in self.link_lists.items():
            self.link_panels[key].setVisible(bool(row and key in row))
            choices.clear()
            if row is None or key not in row:
                continue
            selected = row[key] if isinstance(row[key], list) else []
            options = self._buffer['hypotheses' if key == 'hypothesis_ids' else 'evidence']
            ids = {item['id'] for item in options}
            entries = [(item['id'], item.get('title', item.get('label', ''))) for item in options]
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
        label = str(row.get('label', '자료·결과'))
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
        elif row:
            ids = row.get('supporting', []) + row.get('conflicting', []) + row.get('evidence_ids', [])
            evidence = next((item for item in self._buffer.get('evidence', []) if item['id'] in ids), None)
            if evidence is None:
                selected_id = self._entry_read_context.get((self._context(), row['id']))
                evidence = next((item for item in self._buffer.get('evidence', []) if item['id'] == selected_id), None)
        self.context_source.setVisible(evidence is not None)
        if evidence is not None:
            self.context_source.setText('자료 보기: ' + self._evidence_label(evidence))
        self.note_button.setEnabled(evidence is not None and not self._raw_mode)
        if evidence is None:
            self._content_key = self._content_reference = self._content_pending = None
            self.reading.clear('자료 목록에서 대화 발언이나 계산 결과를 선택하세요.')
            self.pin_response.setEnabled(False)
            return
        reference = deepcopy(evidence['reference'])
        key = (self._context(selection=True), evidence['id'], canonical_hash(reference))
        if key == self._content_key:
            return
        self._content_key = key
        if isinstance(reference.get('response'), str) and reference['response']:
            reference['selection'] = {'responses': [reference.pop('response')], 'rows': [0, 256]}
        self._content_reference = reference
        self._content_label = self._evidence_label(evidence)
        self.reading.clear('자료를 읽는 중…')
        self._content_pending = (key, deepcopy(reference))
        self.pin_response.setEnabled(False)
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
        def received(payload):
            # Content reads update only availability, never research judgment.
            evidence_id = key[1]
            self._reference_checks[evidence_id] = {
                'status': payload.get('status', 'UNKNOWN'), 'message': payload.get('message', '')}
            self._populate_evidence()
            self.reading.set_payload(payload, label=self._content_label)
            self.pin_response.setEnabled(reference.get('kind') == 'result' and
                self._selected is not None and self._selected[0] == 'evidence' and 'selection' in reference)
            # Legacy evidence with no channel selection gets a bounded, visible
            # first-channel preview. The saved reference changes only on Keep.
            if (reference.get('kind') == 'result' and 'selection' not in reference
                    and 'response' not in reference and self.reading.channel.count()):
                self.read_response(str(self.reading.channel.itemData(0)))
        def rejected(error):
            self._reference_checks[key[1]] = {'status': 'UNAVAILABLE', 'message': str(error)}
            self._populate_evidence()
            self.reading.clear('자료 읽기 실패: ' + str(error))
        started = self._call(lambda: method(reference), received, relevant=relevant, rejected=rejected)
        if not started:
            self._content_pending = (key, reference)
        return started

    def read_response(self, name):
        if not self._content_reference or self._content_reference.get('kind') != 'result':
            return
        reference = deepcopy(self._content_reference)
        reference.pop('response', None)
        reference['selection'] = {'responses': [name], 'rows': [0, 256]}
        self._content_reference = reference
        self.reading.clear('Reading ' + name + '…')
        self._content_pending = (self._content_key, reference)
        self._schedule_content_read()

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
        row[title_key] = deepcopy(original[title_key]) if self.detail_title.text() == str(original[title_key]) else self.detail_title.text()
        row[text_key] = deepcopy(original[text_key]) if self.detail_text.toPlainText() == str(original[text_key]) else self.detail_text.toPlainText()
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
        self.tabs.setCurrentWidget(self.editor)
        self.detail_text.setFocus()

    def remove_entry(self):
        if not self._row() or self._busy or self._callbacks:
            return
        kind, identifier = self._selected
        self._buffer[kind] = [row for row in self._buffer[kind] if row['id'] != identifier]
        self._selected = None
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
        super().closeEvent(event)

    def open_document(self, *, document_id=None, title='새 연구 기록', draft=None):
        context = self._context()
        return self._call(lambda: self.client.document_open(kind='study', title=title, draft=draft,
            document_id=document_id), self._opened, relevant=lambda: self._context() == context)

    def command(self, operation, arguments=None, *, after=None):
        if not self.document or self.conflict:
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
                self._show_document(remote, preserve_buffer=self.local_dirty)
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
            self.tabs.setCurrentWidget(self.editor)
            self.detail_text.setFocus()
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
        self.undo_action.setEnabled(enabled and not self.local_dirty and self.document.get('can_undo', False))
        self.redo_action.setEnabled(enabled and not self.local_dirty and self.document.get('can_redo', False))
        self.new_action.setEnabled(available)
        self.open_action.setEnabled(available)
        self.question.setEnabled(present and not self._raw_mode)
        self.editor.setEnabled(present and not self._raw_mode and self._row() is not None)
        self.raw.setEnabled(present)
        for button in self.add_buttons + self.evidence_buttons:
            button.setEnabled(enabled and not self._raw_mode)
        self.remove_button.setEnabled(enabled and self._row() is not None)
        self.reference_button.setEnabled(enabled and bool(self._content_reference))
        self.note_button.setEnabled(enabled and bool(self._content_reference) and not self._raw_mode)
        self.check_button.setEnabled(enabled and bool(self._content_reference))
        for button in (self.discussion_button, self.plan_button):
            button.setEnabled(enabled and not self._raw_mode)
        self.reload_button.setVisible(self.conflict)
        self.copy_button.setVisible(self.conflict)
        self.reload_button.setEnabled(available)
        self.copy_button.setEnabled(available)
        if present:
            self.setWindowTitle('Study — ' + self.document['title'] + (' *' if self.local_dirty or self.document.get('dirty') else ''))
            self.identity.setText('')
        self._schedule_content_read()


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
