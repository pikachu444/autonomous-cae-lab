"""Read actual interrupted Co-STORM completions through the existing result API.

These are received texts, never adopted turns, citations or engineering verdicts.
Opening, selecting and retrying a read do not dispatch any discussion operation.
"""
from copy import deepcopy
import json
from functools import lru_cache
from importlib import import_module

from PySide6.QtCore import Qt, QThreadPool, Slot
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QHBoxLayout,
    QLabel, QListWidget, QPlainTextEdit, QPushButton, QSplitter, QTabWidget, QVBoxLayout)

from .data_window import _Read
from .readable_text import ReadingBrowser, show_markdown


def interrupted_attempts(document):
    runs = {row['job_id'] for row in document.get('runs', [])}
    return [{'job_id': row['completed_job_id'], 'label': '중단된 작성 ' + str(index + 1)}
        for index, row in enumerate(document.get('discussion', {}).get('rounds', []))
        if row.get('protocol') == 'costorm' and row.get('status') == 'FAILED'
        and row.get('completed_job_id') in runs]


LABELS = {'answer': '답변', 'question': '질문', 'utterance': '발언', 'output': '내용',
          'queries': '검색 질문', 'outline': '개요', 'experts': '참여 역할',
          'resposne': '내용', 'response': '내용', 'decision': '검토 내용', 'choice': '선택 내용'}


@lru_cache(maxsize=1)
def output_fields():
    """Read the retained stages' actual output declarations, without invoking Predict."""
    from caelab.assist._vendor.costorm.prompting import Field
    stages = {
        'grounded_question_answering': ('QuestionToQuery', 'AnswerQuestion'),
        'expert_generation': ('GenerateExpertGeneral', 'GenerateExpertWithFocus'),
        'warmstart_hierarchical_chat': ('WarmStartModerator', 'SectionToConvTranscript', 'GenerateWarmStartOutline'),
        'grounded_question_generation': ('ConvertUtteranceStyle', 'GroundedQuestionGeneration'),
        'information_insertion_module': ('InsertInformation', 'InsertInformationCandidateChoice', 'ExpandSection'),
        'knowledge_base_summary': ('KnowledgeBaseSummmary',), 'article_generation': ('WriteSection',),
    }
    result = []
    for module, names in stages.items():
        source = import_module('caelab.assist._vendor.costorm.collaborative_storm.modules.' + module)
        for name in names:
            result.append({key: (value.prefix or key.replace('_', ' ').capitalize() + ':').strip()
                for key, value in vars(getattr(source, name)).items()
                if isinstance(value, Field) and value.output and key in LABELS})
    return result


def received_view(text):
    """Bounded reading projection; unsupported structured output stays in diagnostics."""
    unsupported = '이 응답은 읽기 형식으로 표시할 수 없습니다. 원문 보기로 확인하세요.'
    try:
        fields = output_fields()
    except (ImportError, AttributeError):
        return unsupported, True
    try:
        payload = json.loads(text)
    except (TypeError, ValueError):
        if text.lstrip().startswith(('{', '[')):
            return unsupported, True
        # Keep multiline content while replacing only known output-field labels.
        for schema in fields:
            for key, prefix in schema.items():
                if text.startswith(prefix):
                    text = '### ' + LABELS[key] + '\n\n' + text[len(prefix):].lstrip()
                text = text.replace('\n' + prefix, '\n\n### ' + LABELS[key] + '\n\n')
        return text, False
    allowed = {key for schema in fields for key in schema}
    if not isinstance(payload, dict) or not payload or set(payload) - allowed:
        return unsupported, True
    paragraphs = []
    needs_original = not any(set(payload) == set(schema) for schema in fields)
    for key, value in payload.items():
        if isinstance(value, str):
            if not value.strip():
                return unsupported, True
            body = value
        elif key in {'queries', 'outline', 'experts'} and isinstance(value, list) and value and all(isinstance(v, str) for v in value):
            body = '\n'.join(str(index + 1) + '. ' + entry for index, entry in enumerate(value))
            # The actual protocol fields require strings. This is only a reading
            # projection of received list content, never a successful parse/replay.
            needs_original = True
        else:
            return unsupported, True
        paragraphs.append('### ' + LABELS[key] + '\n\n' + body)
    return '\n\n'.join(paragraphs), needs_original


def stop_reason(reason):
    reason = str(reason)
    return {'model call budget exhausted': '응답 요청 한도에 도달했습니다. 이번 한도를 확인하세요.',
            'Consultation time budget exhausted': '응답 작성 시간 한도에 도달했습니다. 이번 한도를 확인하세요.'}.get(reason, str(reason))


class PartialResponsesDialog(QDialog):
    def __init__(self, client, document, parent=None):
        super().__init__(parent)
        self.client, self.document = client, deepcopy(document)
        self._owner = (document['id'], document['session_id'])
        self._workers = []
        self._closed = False
        self._journal = []
        self._displayed = None
        self.setWindowTitle('중단된 응답'); self.resize(1000, 720)
        layout = QVBoxLayout(self)
        hint = QLabel('중단 전에 받은 내용입니다. 완성된 발언·보고서가 아닙니다. 읽기는 새 응답을 요청하지 않습니다.')
        hint.setWordWrap(True); layout.addWidget(hint)
        line = QHBoxLayout(); self.attempts = QComboBox()
        for attempt in reversed(interrupted_attempts(document)):
            self.attempts.addItem(attempt['label'], attempt)
        line.addWidget(self.attempts, 1)
        self.refresh = QPushButton('다시 읽기'); self.refresh.clicked.connect(self.load)
        line.addWidget(self.refresh); layout.addLayout(line)
        self.displayed = QLabel(); self.displayed.setWordWrap(True); layout.addWidget(self.displayed)
        splitter = QSplitter()
        self.responses = QListWidget(); self.responses.setMinimumWidth(160)
        splitter.addWidget(self.responses)
        self.tabs = QTabWidget()
        self.body = ReadingBrowser(); self.body.setOpenLinks(False); self.body.setOpenExternalLinks(False)
        self.details = QPlainTextEdit(); self.details.setReadOnly(True)
        self.tabs.addTab(self.body, '받은 내용'); self.tabs.addTab(self.details, '진단')
        splitter.addWidget(self.tabs); splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter, 1)
        reading = QHBoxLayout()
        self.reading_state = QLabel(); self.reading_state.setWordWrap(True); reading.addWidget(self.reading_state, 1)
        self.original = QPushButton('원문 보기'); self.original.hide()
        self.original.clicked.connect(lambda: self.tabs.setCurrentWidget(self.details)); reading.addWidget(self.original)
        layout.addLayout(reading)
        self.message = QLabel(); self.message.setWordWrap(True)
        self.message.setTextFormat(Qt.TextFormat.PlainText); layout.addWidget(self.message)
        footer = QLabel('계속하려면 토론으로 돌아가 이번 한도를 확인한 뒤 다시 시도를 누르세요.')
        footer.setWordWrap(True); layout.addWidget(footer)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.button(QDialogButtonBox.StandardButton.Close).setText('토론으로 돌아가기')
        buttons.rejected.connect(self.reject); layout.addWidget(buttons)
        self.responses.currentRowChanged.connect(self.selected)
        self.attempts.currentIndexChanged.connect(self.load)
        self.load()

    def load(self, *_):
        if self._closed or self._workers:
            return
        attempt = deepcopy(self.attempts.currentData())
        if not attempt:
            self.message.setText('이 대화에는 읽을 중단 응답이 없습니다.'); return
        self.attempts.setEnabled(False); self.refresh.setEnabled(False)
        self.message.setText('선택한 작성에서 받은 내용을 읽고 있습니다.')
        self._reading = attempt
        worker = _Read(lambda: self.client.document_result(self._owner[0], attempt['job_id']))
        self._workers.append(worker)
        worker.signals.finished.connect(self.finished_read, Qt.ConnectionType.QueuedConnection)
        QThreadPool.globalInstance().start(worker)

    @Slot(object, object)
    def finished_read(self, result, error):
        self._workers.clear()
        if self._closed:
            return
        parent = self.parent()
        current = getattr(parent, 'document', self.document)
        if not current or (current['id'], current['session_id']) != self._owner:
            self.message.setText('원 대화가 바뀌었습니다. 이 창을 닫고 해당 대화에서 다시 여세요.'); return
        self.attempts.setEnabled(True); self.refresh.setEnabled(True)
        if error:
            self.message.setText('선택한 내용을 읽지 못했습니다. ' + str(error) +
                ('\n직전에 읽은 내용은 아래에 유지했습니다.' if self._displayed else '') +
                '\n연결이나 저장 자료를 복구한 뒤 다시 읽기를 누르세요.'); return
        protocol = result.get('costorm', {}) if isinstance(result, dict) else {}
        if not isinstance(protocol, dict):
            self.message.setText('중단 응답의 보존 형식을 읽지 못했습니다. 이전에 읽은 내용은 유지했습니다.'); return
        retry = protocol.get('retry') or {}
        if not isinstance(retry, dict):
            self.message.setText('중단 응답의 보존 형식을 읽지 못했습니다. 이전에 읽은 내용은 유지했습니다.'); return
        journal = retry.get('journal')
        if journal is None:
            journal = []
        if not isinstance(journal, list) or any(not isinstance(row, dict) or not isinstance(row.get('text'), str) for row in journal):
            self.message.setText('중단 응답의 보존 형식을 읽지 못했습니다. 이전에 읽은 내용은 유지했습니다.'); return
        self._journal = deepcopy(journal)
        self._invalid_completion_key = retry.get('invalid_completion_key')
        self._displayed = deepcopy(self._reading)
        self.responses.clear(); self.body.clear(); self.details.clear(); self.reading_state.clear(); self.original.hide()
        for index, row in enumerate(journal):
            rejected = row.get('key') is not None and row.get('key') == retry.get('invalid_completion_key')
            needs_original = received_view(row['text'])[1]
            self.responses.addItem('받은 응답 ' + str(index + 1) + (' (형식 확인 필요)' if rejected or needs_original else ''))
        self.displayed.setText('표시 중: ' + self._displayed['label'])
        self.message.setText('받은 응답 ' + str(len(journal)) + '개를 읽었습니다.'
            if journal else '이 작성에 보존된 중간 응답이 없습니다. 완료된 발언은 원래 대화에서 확인하세요.')
        if journal:
            self.responses.setCurrentRow(0)

    def selected(self, index):
        if not 0 <= index < len(self._journal):
            return
        row = self._journal[index]
        text, needs_original = received_view(row['text'])
        needs_original = needs_original or (row.get('key') is not None and
            row.get('key') == self._invalid_completion_key)
        show_markdown(self.body, text)
        self.reading_state.setText('형식 확인 필요. 원문은 진단에서 확인하세요.' if needs_original else '')
        self.original.setVisible(needs_original)
        self.details.setPlainText(json.dumps({'document_id': self._owner[0],
            'job_id': self._displayed['job_id'], 'received_completion': row}, ensure_ascii=False, indent=2))

    def done(self, result):
        self._closed = True
        for worker in self._workers:
            worker.abandon()
        super().done(result)


def show_partial_responses(window):
    if not window.document or not interrupted_attempts(window.document):
        window.message.setText('이 대화에는 읽을 중단 응답이 없습니다.'); return
    dialog = PartialResponsesDialog(window.client, window.document, window)
    dialog.exec()
