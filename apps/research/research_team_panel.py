"""Research-team presentation in the existing Expert window.

This module edits authored drafts and presents owner records. It never runs a
role, collects an origin job, reads a raw response asset, or decides access.
"""
from __future__ import annotations

from copy import deepcopy
import json
import uuid

from PySide6.QtCore import QEvent, QObject, Qt, QThreadPool, QTimer
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog,
    QDialogButtonBox, QFormLayout, QHBoxLayout, QHeaderView, QInputDialog,
    QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPlainTextEdit, QSpinBox,
    QPushButton, QSplitter, QStackedWidget, QTabWidget, QTreeWidget,
    QTreeWidgetItem, QVBoxLayout, QWidget)

TEAM_ROLE = int(Qt.ItemDataRole.UserRole) + 1
TASK_LABELS = {
    'PROBLEM_DEFINITION': '문제 정리',
    'INITIAL_RESEARCH': '독립 조사', 'QUESTION': '대상 질문',
    'ANSWER': '근거 답변', 'EVIDENCE': '자료 조사', 'FINALIZE': '답변 마무리',
    'REPAIR': '응답 형식 확인', 'MAP_SERVICE': '논점 지도 반영',
    'REPORT_SERVICE': '보고서 정리',
}
STATUS_LABELS = {
    'PENDING': '조사 대기', 'RUNNING': '조사 중',
    'WAITING_BUDGET': '조사 계속 대기', 'WAITING_TIME': '조사 계속 대기',
    'WAITING_FINAL': '답변 마무리 대기', 'WAITING_REPAIR': '응답 확인 대기',
    'BLOCKED_SCOPE': '현재 공유 불가', 'OUTCOME_UNCONFIRMED': '완료 확인 필요',
    'COMPLETED': '응답 완료', 'COMPLETED_LOCAL': '개인 열람 응답 완료',
    'ACKNOWLEDGED_UNRESOLVED': '미해결로 유지', 'APPLIED': '지도 반영됨',
    'APPLYING': '지도 반영 중', 'FAILED': '지도 반영 실패',
    'ARCHIVED_PENDING': '이전 작업의 반영 대기', 'AVAILABLE': '읽을 수 있음',
    'DEPENDENCY_UNVERIFIED': '자료 확인 필요', 'SOURCE_UNAVAILABLE': '원 자료 없음',
}
TOOL_LABELS = {
    'knowledge.search': '선택 문헌 검색', 'knowledge.source': '선택 원문 읽기',
    'literature.search': '공개 논문 검색', 'literature.read': '보존 논문 읽기',
    'results.read': '선택 계산 결과 읽기', 'calculations.inputs': '계산 입력 확인',
    'results_read': '선택 계산 결과 읽기',
    'calculations.plan': '계산 계획 제안', 'calculations.status': '계산 상태 확인',
    'numerical.analyze': '선택 결과 수치 분석', 'experts.consult': '허용 담당자 자문',
}


def team_draft(draft):
    value = draft.get('context', {}).get('research_team')
    return value if isinstance(value, dict) else None


def records(document):
    value = (document or {}).get('discussion', {}).get('research_team', {})
    return value if isinstance(value, dict) else {}


def label_for_role(registry, identifier):
    role = next((row for row in registry if row.get('id') == identifier), {})
    return role.get('label') or role.get('name') or role.get('title') or '등록되지 않은 담당자'


def source_label(reference, titles=None):
    titles = titles or {}
    title = reference.get('title') or titles.get(reference.get('document_id')) or '선택 자료'
    return title + (' / 개정 ' + str(reference['revision']) if 'revision' in reference else '')


def result_label(reference):
    """Names and physical definitions only; source tokens remain widget data."""
    channels = reference.get('selector', {}).get('channels', [])
    names = []
    for row in channels:
        from .report_pages import physical_text
        name = row.get('label') or (physical_text('measure', row['measure']) if row.get('measure') else '선택 응답')
        if row.get('component') is not None:
            name += ' / ' + physical_text('component', row['component'])
        if row.get('unit') is not None:
            name += ' [' + str(row['unit']) + ']'
        names.append(name)
    return ', '.join(names) or '계산 상태'


def new_team(draft):
    return {'version': 2, 'phase_id': None, 'parent_phase_id': None,
        'objective': draft.get('composer', {}).get('text', ''), 'deliverable': '',
        'assignments': [], 'shared_evidence': [], 'carry_forward_turn_ids': [],
        'requested_next': None, 'turn_limit': 4, 'stop_when': []}


def team_selection_scope(draft):
    """Expose chosen team inputs to the EXISTING permission controls.

    This changes selection only. Transmission grants are left exactly as
    authored, so a newly selected source/result still needs explicit approval.
    """
    result = deepcopy(draft)
    cfg = team_draft(result)
    if not cfg or cfg.get('version') != 2:
        return result
    context = result['context']
    current = context.get('selected_sources', [])
    if not isinstance(current, list) or any(not isinstance(row, dict) for row in current):
        return result
    assigned, conflict = {}, []
    for assignment in cfg.get('assignments', []):
        for reference in assignment.get('source_refs', []):
            if 'document_id' not in reference:
                continue
            pin = {key: reference[key] for key in ('document_id', 'revision')}
            previous = assigned.get(pin['document_id'])
            if previous and previous != pin:
                conflict.append(pin)
            assigned[pin['document_id']] = pin
    selected = {row.get('document_id'): deepcopy(row) for row in current}
    selected.update(assigned)
    context['selected_sources'] = [*selected.values(), *conflict]
    context['selected_document_ids'] = [row['document_id'] for row in context['selected_sources']]
    ids = context.get('selected_result_ids', [])
    if isinstance(ids, list):
        context['selected_result_ids'] = list(dict.fromkeys([*ids, *[
            selected['reference']['job_id'] for assignment in cfg.get('assignments', [])
            for selected in assignment.get('result_refs', [])]]))
    return result


class ResultSelectionDialog(QDialog):
    """Existing saved-result picker and C's exact physical selection contract.

    Metadata preparation reads no numeric values and grants nothing. Only the
    later existing expert.update adopts this selection through the owner hook.
    """
    def __init__(self, client, parent=None, *, document_id=None):
        super().__init__(parent)
        self.client = client
        self.document_id = document_id
        self.selection = None
        self.descriptor = None
        self._workers, self._serial, self._closed = [], 0, False
        self.setWindowTitle('검토할 계산 결과')
        self.resize(820, 660)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.documents = QComboBox()
        self.runs = QComboBox()
        form.addRow('연구 문서', self.documents)
        form.addRow('저장한 계산', self.runs)
        layout.addLayout(form)
        self.channels = QListWidget()
        self.channels.setAccessibleName('저장 결과의 물리량')
        layout.addWidget(self.channels, 1)
        sample = QFormLayout()
        self.location = QComboBox()
        self.first, self.last = QSpinBox(), QSpinBox()
        self.first.setRange(1, 1)
        self.last.setRange(1, 1)
        sample.addRow('위치', self.location)
        sample.addRow('첫 표본', self.first)
        sample.addRow('마지막 표본', self.last)
        layout.addLayout(sample)
        self.metadata_only = QCheckBox('계산 상태만 선택')
        layout.addWidget(self.metadata_only)
        self.definition = QLabel()
        self.definition.setWordWrap(True)
        layout.addWidget(self.definition)
        self.message = QLabel()
        self.message.setWordWrap(True)
        layout.addWidget(self.message)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText('검토 대상으로 선택')
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('취소')
        self.buttons.accepted.connect(self.apply)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self.documents.currentIndexChanged.connect(self.read_document)
        self.runs.currentIndexChanged.connect(self.read_metadata)
        self.channels.currentRowChanged.connect(self.show_definition)
        self.metadata_only.toggled.connect(lambda _: self.show_definition())
        self.actions()
        QTimer.singleShot(0, lambda: self.read(self.client.documents, self.listed))

    def actions(self):
        busy = bool(self._workers)
        self.documents.setEnabled(not busy)
        self.runs.setEnabled(not busy and self.runs.count() > 0)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(not busy and bool(self.descriptor)
            and (self.metadata_only.isChecked() or self.channels.currentRow() >= 0))

    def read(self, function, accepted):
        if self._closed:
            return
        from .expert_window import _Call
        self._serial += 1
        serial = self._serial
        worker = _Call(function)
        self._workers.append(worker)
        self.actions()
        def finished(value, error):
            self._workers.remove(worker)
            if self._closed:
                return
            if serial == self._serial:
                if error:
                    self.message.setText('저장 결과를 읽을 수 없습니다. 원 문서와 선택을 유지했습니다.')
                    self.message.setToolTip(str(error))
                else:
                    accepted(value)
            self.actions()
        worker.signals.finished.connect(finished, Qt.ConnectionType.QueuedConnection)
        QThreadPool.globalInstance().start(worker)

    def listed(self, payload):
        self.documents.blockSignals(True)
        self.documents.clear()
        for row in payload.get('documents', []):
            if self.document_id is not None and row['id'] != self.document_id:
                continue
            if row.get('kind') in {'data', 'material', 'numerical', 'pde', 'simulation', 'evaluation'}:
                self.documents.addItem(row.get('title') or '연구 문서', row['id'])
        self.documents.blockSignals(False)
        if self.documents.count():
            self.read_document()
        else:
            self.message.setText('원 프로그램에서 계산 결과를 저장한 뒤 선택하세요.')

    def read_document(self, *_):
        identifier = self.documents.currentData()
        self.descriptor = None
        self.channels.clear()
        self.runs.blockSignals(True)
        self.runs.clear()
        self.runs.blockSignals(False)
        if not identifier:
            return
        def accepted(document):
            self.runs.blockSignals(True)
            for row in document.get('runs', []):
                if row.get('retention_complete') and row.get('retained_result'):
                    state = {'SUCCEEDED': '계산 완료', 'FAILED': '계산 실패', 'CANCELLED': '계산 취소'}.get(
                        row.get('retained_state'), '상태 미확인')
                    self.runs.addItem('저장 계산 ' + str(self.runs.count() + 1) + ' / ' + state,
                                      (document['id'], row['job_id']))
            self.runs.blockSignals(False)
            if self.runs.count():
                self.read_metadata()
            else:
                self.message.setText('이 문서에 저장한 계산 결과가 없습니다.')
        self.read(lambda: self.client.document_read(identifier), accepted)

    def read_metadata(self, *_):
        selected = self.runs.currentData()
        self.descriptor = None
        self.channels.clear()
        if not selected:
            return
        document, job = selected
        def accepted(pair):
            reference, metadata = pair
            catalog = metadata.get('research_team_descriptor')
            if (not isinstance(catalog, dict) or catalog.get('status') not in (None, 'AVAILABLE')
                    or not isinstance(catalog.get('descriptor'), dict)
                    or not isinstance(catalog['descriptor'].get('channels'), list)
                    or not isinstance(catalog.get('descriptor_digest'), str)):
                self.message.setText('이 결과의 원 표본 범위를 선택할 수 없습니다. 원 결과는 유지됩니다.')
                self.message.setToolTip(str(catalog.get('reason', '정확한 물리량 선택 정보를 제공하지 않습니다.'))
                    if isinstance(catalog, dict) else '정확한 물리량 선택 정보를 제공하지 않습니다.')
                self.actions()
                return
            self.descriptor = {'reference': reference, **deepcopy(catalog)}
            for row in catalog['descriptor']['channels']:
                item = QListWidgetItem(result_label({'selector': {'channels': [row]}}))
                item.setData(Qt.ItemDataRole.UserRole, deepcopy(row))
                item.setToolTip('원 응답: ' + str(row.get('response')))
                self.channels.addItem(item)
            if self.channels.count():
                self.channels.setCurrentRow(0)
            self.message.setText('선택한 물리량과 원 표본 범위를 담당자에게 전달합니다.')
            self.actions()
        self.read(lambda: (self.client.document_result_reference(document, job),
                           self.client.document_result_metadata(document, job)), accepted)

    def show_definition(self, *_):
        item = self.channels.currentItem()
        definition = item.data(Qt.ItemDataRole.UserRole) if item else {}
        values = not self.metadata_only.isChecked()
        self.channels.setEnabled(values)
        count = len(definition.get('reader_rows') or []) or sum(last - first
            for first, last in definition.get('row_intervals') or [])
        self.first.setRange(1, max(1, min(count, 2_000_000_000)))
        self.last.setRange(1, max(1, min(count, 2_000_000_000)))
        self.first.setValue(1)
        self.last.setValue(min(count or 1, 256))
        self.first.setEnabled(values and bool(count))
        self.last.setEnabled(values and bool(count))
        self.location.clear()
        self.location.addItem('선택 물리량의 전체 위치', None)
        for value in definition.get('location_ids') or []:
            self.location.addItem('원 위치 ' + str(value), value)
        self.location.setEnabled(values and self.location.count() > 1)
        from .report_pages import physical_text
        self.definition.setText(' / '.join(physical_text(key, definition.get(key)) for key in
            ('measure', 'frame', 'component')) if definition else '')
        self.actions()

    def apply(self):
        if not self.descriptor or self._workers:
            return
        from caelab.research_team_results import make_result_selection, _row_intervals
        request = {'metadata_only': self.metadata_only.isChecked(), 'channels': []}
        item = self.channels.currentItem()
        if not request['metadata_only'] and item:
            definition = item.data(Qt.ItemDataRole.UserRole)
            channel = {key: deepcopy(definition.get(key)) for key in
                ('response', 'association', 'component', 'unit', 'measure', 'frame', 'coordinate_system')}
            intervals = definition.get('row_intervals')
            rows = definition.get('reader_rows')
            if rows or intervals:
                if self.first.value() > self.last.value():
                    self.message.setText('첫 표본과 마지막 표본의 순서를 확인하세요.')
                    return
                if self.last.value() - self.first.value() + 1 > 1024:
                    self.message.setText('한 번에 검토할 표본은 1,024개 이하로 선택하세요.')
                    return
                if rows:
                    selected = rows[self.first.value() - 1:self.last.value()]
                else:
                    selected, offset = [], 0
                    for start, stop in intervals:
                        lo = max(0, self.first.value() - 1 - offset)
                        hi = min(stop - start, self.last.value() - offset)
                        if lo < hi:
                            selected.extend(range(start + lo, start + hi))
                        offset += stop - start
                channel['row_intervals'] = _row_intervals(selected)
            if self.location.currentData() is not None:
                channel['location_ids'] = [self.location.currentData()]
            request['channels'] = [channel]
        try:
            self.selection = make_result_selection(self.descriptor, source_id='S' + uuid.uuid4().hex,
                selection_request=request)
        except (KeyError, ValueError) as error:
            self.message.setText('선택한 물리량의 원 표본 범위를 확인하세요.')
            self.message.setToolTip(str(error))
            return
        self.accept()

    def done(self, result):
        self._closed = True
        self._serial += 1
        for worker in self._workers:
            worker.abandon()
        super().done(result)


class TeamReviewDialog(QDialog):
    """Selected-role editing; source selection remains the existing picker."""
    def __init__(self, window, draft, *, next_phase=False, parent=None):
        super().__init__(parent or window)
        self.window = window
        self.original = deepcopy(draft)
        self.value = deepcopy(team_draft(draft) or new_team(draft))
        self.accepted_team = None
        self.source_titles = deepcopy(window._source_titles)
        self._selected = None
        self._loading = False
        self.setWindowTitle('다음 연구 단계' if next_phase else '팀과 자료 검토')
        self.resize(1000, 720)
        if next_phase:
            self.value['parent_phase_id'] = self.value.get('phase_id')
            self.value['phase_id'] = None
            self.value['requested_next'] = None
            self.value['carry_forward_turn_ids'] = []
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.objective = QPlainTextEdit(self.value.get('objective', ''))
        self.objective.setMaximumHeight(76)
        self.objective.setAccessibleName('이번 연구 질문')
        self.deliverable = QLineEdit(self.value.get('deliverable', ''))
        self.turn_limit = QSpinBox()
        self.turn_limit.setRange(1, 8)
        self.turn_limit.setValue(self.value.get('turn_limit', 4))
        form.addRow('연구 질문', self.objective)
        form.addRow('필요한 산출물', self.deliverable)
        form.addRow('이번 범위의 발언 상한', self.turn_limit)
        layout.addLayout(form)
        split = QSplitter()
        layout.addWidget(split, 1)
        self.roles = QTreeWidget()
        self.roles.setHeaderLabels(['담당자', '역할'])
        self.roles.header().setStretchLastSection(False)
        self.roles.setMinimumWidth(220)
        self.roles.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.roles.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        split.addWidget(self.roles)
        self.detail = QTabWidget()
        split.addWidget(self.detail)
        self.scope = QWidget()
        sl = QVBoxLayout(self.scope)
        sf = QFormLayout()
        self.mode = QComboBox()
        self.mode.addItem('독립 조사', 'investigator')
        self.mode.addItem('진행', 'coordinator')
        sf.addRow('맡을 역할', self.mode)
        sl.addLayout(sf)
        sl.addWidget(QLabel('이번에 답할 질문'))
        self.question = QPlainTextEdit()
        self.question.setAccessibleName('선택 담당자의 질문')
        sl.addWidget(self.question, 2)
        sl.addWidget(QLabel('확인할 항목 (한 줄에 하나)'))
        self.checks = QPlainTextEdit()
        self.checks.setMaximumHeight(100)
        sl.addWidget(self.checks)
        sl.addWidget(QLabel('사용할 도구'))
        self.tools = QListWidget()
        sl.addWidget(self.tools, 1)
        self.detail.addTab(self.scope, '담당 범위')
        sources = QWidget()
        so = QVBoxLayout(sources)
        self.sources = QListWidget()
        self.results = QListWidget()
        remove_result = QAction('선택 결과 제외', self.results)
        remove_result.setShortcut('Delete')
        remove_result.triggered.connect(self.remove_result)
        self.results.addAction(remove_result)
        self.results.setContextMenuPolicy(Qt.ContextMenuPolicy.ActionsContextMenu)
        so.addWidget(QLabel('검토할 문헌'))
        so.addWidget(self.sources, 1)
        self.choose_source = QPushButton('자료 선택…')
        self.choose_source.clicked.connect(self.select_sources)
        so.addWidget(self.choose_source)
        so.addWidget(QLabel('검토할 계산 결과'))
        so.addWidget(self.results, 1)
        self.choose_result = QPushButton('결과 선택…')
        self.choose_result.clicked.connect(self.select_results)
        so.addWidget(self.choose_result)
        self.detail.addTab(sources, '자료와 결과')
        self.carried = QListWidget()
        for turn in (window.document or {}).get('turns', []):
            if not turn.get('text'):
                continue
            item = QListWidgetItem(label_for_role(window._registry, turn.get('author')) + ': ' + str(turn['text'])[:110]
                if turn.get('author') != 'user' else '사용자: ' + str(turn['text'])[:110])
            item.setData(Qt.ItemDataRole.UserRole, turn['id'])
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if turn['id'] in self.value.get('carry_forward_turn_ids', []) else Qt.CheckState.Unchecked)
            item.setToolTip(str(turn['text']))
            self.carried.addItem(item)
        self.detail.addTab(self.carried, '이어갈 발언')
        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        budget = draft.get('budget', {})
        self.budget = QLabel('이번 상한: 모델 처리 ' + str(budget.get('model_calls', 4)) +
            ' / 도구 ' + str(budget.get('tool_calls', 8)) + ' / ' + str(budget.get('seconds', 120)) + '초')
        self.budget.setToolTip('모델 청구 횟수나 완료 시간의 예측이 아닙니다. 남은 과제는 다음 명시 진행에서 이어집니다.')
        layout.addWidget(self.budget)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText('편집에 반영')
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('취소')
        buttons.accepted.connect(self.apply)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.assignments = {row['expert_id']: deepcopy(row) for row in self.value.get('assignments', [])}
        registry = {row['id']: row for row in window._registry}
        ids = list(registry) + [key for key in self.assignments if key not in registry]
        for identifier in ids:
            assigned = self.assignments.get(identifier)
            item = QTreeWidgetItem([label_for_role(window._registry, identifier),
                '진행' if assigned and assigned.get('mode') == 'coordinator' else '조사' if identifier in registry else '등록 필요'])
            item.setData(0, Qt.ItemDataRole.UserRole, identifier)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(0, Qt.CheckState.Checked if assigned else Qt.CheckState.Unchecked)
            self.roles.addTopLevelItem(item)
            self.assignments.setdefault(identifier, {'expert_id': identifier,
                'mode': 'investigator', 'question': '', 'checks': [], 'tools': [],
                'source_refs': [], 'result_refs': []})
        self.roles.currentItemChanged.connect(self.role_selected)
        split.setSizes([260, 700])
        if self.roles.topLevelItemCount():
            self.roles.setCurrentItem(self.roles.topLevelItem(0))
        else:
            self.detail.setEnabled(False)
            self.status.setText('등록한 담당자가 없습니다. 연결 설정에서 역할을 선택한 뒤 계속 편집할 수 있습니다.')

    def stash(self):
        if self._selected is None or self._loading:
            return
        old = self.assignments.get(self._selected, {})
        self.assignments[self._selected] = {
            'expert_id': self._selected, 'mode': self.mode.currentData(),
            'question': self.question.toPlainText(),
            'checks': self.checks.toPlainText().splitlines(),
            'tools': [self.tools.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.tools.count())
                      if self.tools.item(i).checkState() == Qt.CheckState.Checked],
            'source_refs': deepcopy(old.get('source_refs', [])),
            'result_refs': deepcopy(old.get('result_refs', [])),
        }

    def role_selected(self, current, previous=None):
        self.stash()
        self._loading = True
        self._selected = current.data(0, Qt.ItemDataRole.UserRole) if current else None
        definition = next((row for row in self.window._registry if row['id'] == self._selected), {})
        row = self.assignments.get(self._selected, {})
        self.mode.setCurrentIndex(max(0, self.mode.findData(row.get('mode', 'investigator'))))
        self.question.setPlainText(row.get('question', ''))
        self.checks.setPlainText('\n'.join(row.get('checks', [])))
        self.tools.clear()
        for name in list(dict.fromkeys([*definition.get('tools', []), *row.get('tools', [])])):
            item = QListWidgetItem(TOOL_LABELS.get(name, '추가 등록 도구'))
            item.setData(Qt.ItemDataRole.UserRole, name)
            item.setToolTip(name)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if name in row.get('tools', []) else Qt.CheckState.Unchecked)
            if name not in definition.get('tools', []):
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEnabled)
            self.tools.addItem(item)
        self._loading = False
        self.show_sources()

    def show_sources(self):
        self.sources.clear()
        self.results.clear()
        row = self.assignments.get(self._selected, {})
        for reference in row.get('source_refs', []):
            self.sources.addItem(source_label(reference, self.source_titles))
        for reference in row.get('result_refs', []):
            item = QListWidgetItem(result_label(reference))
            item.setToolTip(result_label(reference))
            self.results.addItem(item)

    def select_sources(self):
        if self._selected is None:
            return
        self.stash()
        from .expert_sources import SourceDialog
        row = self.assignments[self._selected]
        definition = next((r for r in self.window._registry if r['id'] == self._selected), {})
        source_context = deepcopy(self.window.edited_draft().get('context', {}))
        source_context['selected_sources'] = deepcopy(row['source_refs'])
        source_context['selected_document_ids'] = [ref['document_id'] for ref in row['source_refs']]
        dialog = SourceDialog(self.window.client, source_context,
            collections=definition.get('collections', []), role_id=self._selected, parent=self)
        try:
            if dialog.exec() == QDialog.DialogCode.Accepted:
                row['source_refs'] = deepcopy(dialog.references)
                self.source_titles.update(dialog.titles)
                self.show_sources()
        finally:
            dialog.close()
            dialog.deleteLater()

    def select_results(self):
        if self._selected is None:
            return
        self.stash()
        picker = getattr(self.window, 'research_team_result_picker', None)
        if picker is None:
            self.status.setText('정확한 결과 선택 연결을 사용할 수 없습니다. 기존 첨부 결과는 유지합니다.')
            return
        selected = picker(self, deepcopy(self.assignments[self._selected]['result_refs']))
        if selected is not None:
            self.assignments[self._selected]['result_refs'] = deepcopy(selected)
            self.show_sources()

    def remove_result(self):
        if self._selected is not None and self.results.currentRow() >= 0:
            self.stash()
            self.assignments[self._selected]['result_refs'].pop(self.results.currentRow())
            self.show_sources()

    def apply(self):
        self.stash()
        self.value['objective'] = self.objective.toPlainText()
        self.value['deliverable'] = self.deliverable.text()
        self.value['turn_limit'] = self.turn_limit.value()
        self.value['carry_forward_turn_ids'] = [self.carried.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(self.carried.count()) if self.carried.item(i).checkState() == Qt.CheckState.Checked]
        self.value['assignments'] = [deepcopy(self.assignments[item.data(0, Qt.ItemDataRole.UserRole)])
            for item in (self.roles.topLevelItem(i) for i in range(self.roles.topLevelItemCount()))
            if item.checkState(0) == Qt.CheckState.Checked]
        revisions = {}
        for assignment in self.value['assignments']:
            for reference in assignment['source_refs']:
                key = reference.get('document_id')
                if key and key in revisions and revisions[key] != reference['revision']:
                    self.status.setText('같은 문헌의 서로 다른 개정은 함께 선택할 수 없습니다. 담당자별 선택 개정을 확인하세요.')
                    return
                if key:
                    revisions[key] = reference['revision']
        self.accepted_team = deepcopy(self.value)
        self.accept()


class ResearchTeamPanel(QWidget):
    """Contextual task navigation; the original transcript stays central."""
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self._refreshing = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        heading = QHBoxLayout()
        title = QLabel('연구팀')
        title.setProperty('appearanceRole', 'title')
        heading.addWidget(title, 1)
        self.review_button = QPushButton('팀 검토…')
        self.review_button.clicked.connect(self.review_team)
        heading.addWidget(self.review_button)
        layout.addLayout(heading)
        self.phase = QLabel()
        self.phase.setTextFormat(Qt.TextFormat.PlainText)
        self.phase.setWordWrap(True)
        layout.addWidget(self.phase)
        self.model = QLabel('모델 연결 확인 전')
        self.model.setTextFormat(Qt.TextFormat.PlainText)
        self.model.setProperty('appearanceRole', 'muted')
        self.model.setWordWrap(True)
        layout.addWidget(self.model)
        self.history = QComboBox()
        self.history.setAccessibleName('연구 단계 열람')
        self.history.currentIndexChanged.connect(lambda _: self.refresh_tasks())
        layout.addWidget(self.history)
        self.tasks = QTreeWidget()
        self.tasks.setHeaderLabels(['과제', '상태'])
        self.tasks.setObjectName('researchTeamTasks')
        self.tasks.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tasks.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.tasks.currentItemChanged.connect(self.select_task)
        self.tasks.setContextMenuPolicy(Qt.ContextMenuPolicy.ActionsContextMenu)
        self.acknowledge = QAction("미해결로 남기기…", self.tasks)
        self.acknowledge.triggered.connect(self.acknowledge_task)
        self.tasks.addAction(self.acknowledge)
        self.task_detail = QLabel()
        self.task_detail.setWordWrap(True)
        self.task_detail.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.tasks, 1)
        layout.addWidget(self.task_detail)
        self.pending = QLabel()
        self.pending.setWordWrap(True)
        layout.addWidget(self.pending)
        self.map_retry = QPushButton('지도 반영 다시 시도')
        self.map_retry.clicked.connect(lambda: self.window.protocol_action('expert.retry'))
        layout.addWidget(self.map_retry)
        self.next_phase = QPushButton('다음 연구 단계…')
        self.next_phase.clicked.connect(lambda: self.review_team(next_phase=True))
        layout.addWidget(self.next_phase)

    def selected(self):
        item = self.tasks.currentItem()
        return item.data(0, Qt.ItemDataRole.UserRole) if item else None

    def refresh(self):
        state = records(self.window.document)
        cfg = team_draft(self.window.edited_draft()) or {}
        previous = self.history.currentData()
        self.history.blockSignals(True)
        self.history.clear()
        self.history.addItem('현재 연구 범위', cfg.get('phase_id'))
        for identifier, phase in state.get('phases', {}).items():
            if identifier != cfg.get('phase_id'):
                self.history.addItem(phase.get('objective') or '이전 연구 단계', identifier)
        index = self.history.findData(previous) if previous else 0
        self.history.setCurrentIndex(max(0, index))
        self.history.blockSignals(False)
        self.history.setVisible(self.history.count() > 1)
        self.refresh_tasks()

    def refresh_tasks(self):
        state = records(self.window.document)
        selected = self.selected()
        self._refreshing = True
        self.task_detail.clear()
        self.tasks.clear()
        cfg = team_draft(self.window.edited_draft()) or {}
        view_phase = self.history.currentData()
        phase = state.get('phases', {}).get(view_phase, {})
        self.phase.setText((phase.get('objective') if view_phase != cfg.get('phase_id') else cfg.get('objective'))
            or '연구 질문과 담당자를 선택하세요.')
        runtime = getattr(self.window, '_research_team_runtime', {})
        self.model.setText(runtime.get('model') or ('모델 연결 필요' if runtime.get('status') == 'NOT_CONFIGURED' else '모델 연결 확인 전'))
        completed = pending = 0
        for identifier in phase.get('task_ids', []):
            task = state.get('tasks', {}).get(identifier, {})
            if not task:
                continue
            status = task.get('status', 'PENDING')
            completed += status == 'COMPLETED'
            pending += status not in ('COMPLETED', 'ACKNOWLEDGED_UNRESOLVED')
            item = QTreeWidgetItem([label_for_role(self.window._registry, task.get('actor_id')) + '\n' +
                TASK_LABELS.get(task.get('kind'), '연구 과제'), STATUS_LABELS.get(status, '상태 확인 필요')])
            item.setData(0, Qt.ItemDataRole.UserRole, ('task', identifier))
            assignment = next((row for row in cfg.get('assignments', []) if row['expert_id'] == task.get('actor_id')), {})
            item.setToolTip(0, assignment.get('question', ''))
            self.tasks.addTopLevelItem(item)
            if selected == ('task', identifier):
                self.tasks.setCurrentItem(item)
        waiting = [row for row in state.get('map_pending', {}).values() if row.get('status') != 'APPLIED'
                   and row.get('phase_id', view_phase) == view_phase]
        self.pending.setText('응답 완료 ' + str(completed) + ' / 남은 과제 ' + str(pending) +
            ('\n지도 반영 대기 ' + str(len(waiting)) if waiting else ''))
        self._refreshing = False
        selected = self.selected()
        task = state.get('tasks', {}).get(selected[1], {}) if selected else {}
        self.task_detail.setText((task.get('acknowledgement') or {}).get('reason', ''))
        self.update_actions()

    def update_actions(self):
        window = self.window
        enabled = bool(window.document and not window._closed and not window._busy and
            not window.conflict and not window._source_choosing and not window._protocol_delivery and not window._protocol_steps)
        state = records(window.document)
        cfg = team_draft(window.edited_draft()) or {}
        local = [row for row in state.get('actions', {}).values() if row.get('origin') == 'local'
                 and row.get('phase_id') == cfg.get('phase_id')]
        archived = not local and bool(state.get('actions'))
        pending = [row for row in state.get('map_pending', {}).values() if row.get('status') not in ('APPLIED', 'BLOCKED_SCOPE', 'ARCHIVED_PENDING')
                   and row.get('phase_id', cfg.get('phase_id')) == cfg.get('phase_id')]
        current_action = local[-1] if local else {}
        action_tasks = [state.get('tasks', {}).get(key, {}) for key in current_action.get('task_ids', [])]
        map_only = bool(action_tasks) and all(row.get('status') in ('COMPLETED', 'ACKNOWLEDGED_UNRESOLVED') for row in action_tasks)
        _, _, active = window._protocol_state()
        self.review_button.setEnabled(enabled)
        self.acknowledge.setEnabled(enabled and self.can_acknowledge())
        self.next_phase.setEnabled(enabled and not active)
        self.map_retry.setVisible(bool(pending) or archived)
        self.map_retry.setEnabled(enabled and map_only and bool(pending) and not archived and not active and
            not window.document.get('discussion', {}).get('paused', False))
        if archived:
            self.map_retry.setToolTip('이전 작업은 기록으로만 읽습니다. 다음 연구 단계에서 새 현지 요청을 작성하세요.')
        else:
            self.map_retry.setToolTip('현재 현지 작업의 남은 지도만 요청합니다. 완료한 담당자의 응답은 다시 만들지 않습니다.')

    def review_team(self, _checked=False, *, next_phase=False):
        window = self.window
        if not window.document or window._busy or window.conflict:
            return
        submitted = deepcopy(window.edited_draft())
        owner = (window.document['id'], window.document['session_id'])
        dialog = TeamReviewDialog(window, submitted, next_phase=next_phase)
        window._source_choosing = True
        window._update_actions()
        try:
            accepted = dialog.exec() == QDialog.DialogCode.Accepted
        finally:
            window._source_choosing = False
        if accepted and dialog.accepted_team is not None and window.document and (
                window.document['id'], window.document['session_id']) == owner and window.edited_draft() == submitted:
            submitted['context']['discussion_mode'] = 'costorm'
            submitted['context']['research_team'] = deepcopy(dialog.accepted_team)
            submitted['participants'] = [row['expert_id'] for row in dialog.accepted_team['assignments']]
            window._buffer = team_selection_scope(submitted)
            window._source_titles.update(dialog.source_titles)
            window._populate_roles(submitted['participants'])
            window._populate_sources()
            window._sync_source_preview()
            window.research_team.refresh_result_permission()
            window._edited()
            self.refresh()
        dialog.close()
        dialog.deleteLater()
        window._update_actions()

    def can_acknowledge(self):
        selected = self.selected()
        if not selected or selected[0] != 'task':
            return False
        window = self.window
        state = records(window.document)
        cfg = team_draft(window.edited_draft()) or {}
        phase_id = cfg.get('phase_id')
        phase = state.get('phases', {}).get(phase_id, {})
        task = state.get('tasks', {}).get(selected[1], {})
        _, _, active = window._protocol_state()
        return bool(not active and self.history.currentData() == phase_id and
            task.get('phase_id') == phase_id and selected[1] in phase.get('task_ids', []) and
            task.get('actor_id') in {row['expert_id'] for row in cfg.get('assignments', [])} and
            task.get('status') in {'PENDING', 'WAITING_BUDGET', 'WAITING_TIME',
                'WAITING_FINAL', 'WAITING_REPAIR', 'BLOCKED_SCOPE'} and
            not (task.get('continuation') or {}).get('cleanup_unconfirmed') and
            any(row.get('origin') == 'local' and row.get('phase_id') == phase_id
                for row in state.get('actions', {}).values()))

    def acknowledge_task(self):
        if not self.can_acknowledge() or self.window._busy or self.window.conflict:
            return
        identifier = self.selected()[1]
        reason, accepted = QInputDialog.getMultiLineText(self, '미해결로 남기기',
            '계속 조사하지 않고 미해결로 남기는 사유')
        if accepted and reason.strip() and self.can_acknowledge() and self.selected() == ('task', identifier):
            self.window.command('expert.acknowledge_unresolved', {'task_id': identifier, 'reason': reason.strip()})

    def select_task(self, current, previous=None):
        if self._refreshing or not current:
            return
        kind, identifier = current.data(0, Qt.ItemDataRole.UserRole)
        task = records(self.window.document).get('tasks', {}).get(identifier, {})
        self.task_detail.setText((task.get('acknowledgement') or {}).get('reason', ''))
        self.update_actions()
        target = task.get('target_turn_id')
        if target:
            self.window.reply_to_turn(target)


class _LayoutBinding(QObject):
    def __init__(self, window, splitter, navigation):
        super().__init__(window)
        self.window, self.splitter = window, splitter
        if not callable(getattr(window, 'research_team_result_picker', None)):
            window.research_team_result_picker = self.pick_results
        if not callable(getattr(window, 'research_team_transfer', None)):
            window.research_team_transfer = self.transfer_to_owner
        self._transfer_pending = None
        self.map_evidence = QAction('논점의 근거 읽기…', window.topics)
        self.map_evidence.triggered.connect(self.open_map_source)
        window.topics.addAction(self.map_evidence)
        window.topics.setContextMenuPolicy(Qt.ContextMenuPolicy.ActionsContextMenu)
        self.stack = QTabWidget()
        splitter.replaceWidget(splitter.indexOf(navigation), self.stack)
        self.stack.addTab(navigation, '논점 지도')
        self.panel = ResearchTeamPanel(window)
        self.stack.addTab(self.panel, '연구 과제')
        self.stack.tabBar().hide()
        self._team_view = 1
        self._was_team = False
        self.stack.currentChanged.connect(self.remember_view)
        self.mode_touched = False
        window.protocol_mode.addItem('연구팀', 'costorm')
        self.mode_index = window.protocol_mode.count() - 1
        window.protocol_mode.setItemData(self.mode_index, True, TEAM_ROLE)
        window.protocol_mode.currentIndexChanged.connect(self.mode_changed)
        self.narrow = False
        window.installEventFilter(self)
        self.show_tasks = QAction('연구 과제', window)
        self.show_tasks.triggered.connect(self.reveal)
        window.menuBar().addAction(self.show_tasks)
        for label, kind in (('이 주장에 질문…', 'question'), ('반례 추가…', 'challenge'),
                            ('관측 추가…', 'observation')):
            action = QAction(label, window.turns)
            action.triggered.connect(lambda checked=False, kind=kind: self.intervention(kind))
            window.turns.addAction(action)
        window.turns.setContextMenuPolicy(Qt.ContextMenuPolicy.ActionsContextMenu)
        self.transfer_actions = {}
        menu = window.menuBar().addMenu('연구')
        for key, label in (('study', '선택 내용을 Study에 반영…'),
                           ('report', '보고서 문서로 열기…'),
                           ('result', '결과로 후속 검토…')):
            action = menu.addAction(label)
            action.triggered.connect(lambda checked=False, key=key: self.transfer(key))
            self.transfer_actions[key] = action
        self.retry_transfer = menu.addAction('전달 확인 다시 시도')
        self.retry_transfer.triggered.connect(self.send_transfer)
        self.retry_transfer.setVisible(False)

    def map_sources(self):
        window = self.window
        item = window.topics.currentItem()
        topic_id = item.data(0, Qt.ItemDataRole.UserRole) if item else None
        topic = next((row for row in (window.document or {}).get('discussion', {}).get('costorm', {}).get('topics', [])
                      if row['id'] == topic_id), {})
        state = records(window.document)
        cfg = team_draft((window.document or {}).get('draft', {})) or {}
        phase = state.get('phases', {}).get(cfg.get('phase_id') or cfg.get('parent_phase_id'), {})
        facet = (window.document or {}).get('research_team_local_view', {}).get('facets', {}).get(
            'map_checkpoints', {}).get(phase.get('current_map_revision'), {})
        if facet.get('status') != 'AVAILABLE':
            return []
        infos = (facet.get('projection') or {}).get('info_uuid_to_info_dict', {})
        return [(str(number), infos[str(number)]) for number in topic.get('citations', [])
                if isinstance(infos.get(str(number)), dict) and infos[str(number)].get('meta', {}).get('source')]

    def open_map_source(self):
        if not self.selected() or self.window._busy or not self.window.open_reference:
            return
        rows = self.map_sources()
        if not rows:
            self.window.message.setText('이 논점에서 읽을 수 있는 원 근거가 없습니다.')
            return
        labels = ['[' + number + '] ' + str(info.get('title') or '원 자료') for number, info in rows]
        choice, accepted = QInputDialog.getItem(self.window, '논점의 근거', '읽을 원 자료', labels, 0, False)
        if accepted and choice in labels:
            self.window.open_reference(deepcopy(rows[labels.index(choice)][1]['meta']['source']))

    def selected(self):
        return bool(self.window.protocol_mode.currentData(TEAM_ROLE))

    def mode_changed(self, index):
        if self._was_team:
            self._team_view = self.stack.currentIndex()
        if not self.window._populating:
            self.mode_touched = True
            self.window._edited()
        self._was_team = self.selected()
        self.stack.tabBar().setVisible(self.selected())
        self.stack.setCurrentIndex(self._team_view if self.selected() else 0)
        self.refresh_result_permission()
        self.show_tasks.setVisible(self.selected())
        self.reflow()

    def refresh_result_permission(self):
        if self.selected():
            ids = self.result_ids() + [row['job_id'] for row in (self.window._buffer or {}).get('composer', {}).get('evidence', [])
                                       if 'job_id' in row]
            scope = (self.window._buffer or {}).get('context', {}).get('transmission_scope', {})
            self.window.allow_results.blockSignals(True)
            self.window.allow_results.setChecked(bool(ids) and set(ids) <= set(scope.get('result_ids', [])))
            self.window.allow_results.blockSignals(False)
            self.window.allow_results.setToolTip('팀 검토에서 선택한 결과를 현재 허용 범위 안에서 전송합니다. 새 선택은 별도로 허용하세요.')
    def remember_view(self, index):
        if self.selected() and not self.window._populating:
            self._team_view = index

    def populate(self, *, preserve_buffer=False):
        if not preserve_buffer:
            cfg = team_draft(self.window._buffer or {})
            initial = self.window._populating
            self.window._populating = True
            if cfg and cfg.get('version') == 2:
                self.window.protocol_mode.setCurrentIndex(self.mode_index)
            self.window._populating = initial
            self.mode_touched = False
        self.stack.tabBar().setVisible(self.selected())
        self.stack.setCurrentIndex(self._team_view if self.selected() else 0)
        self.refresh_result_permission()
        self.panel.refresh()
        self.reflow()

    def apply_draft(self, draft):
        result = deepcopy(draft)
        if self.selected():
            result.setdefault('context', {})['discussion_mode'] = 'costorm'
            cfg = team_draft(result)
            if not cfg or cfg.get('version') != 2:
                result['context']['research_team'] = new_team(result)
            result = team_selection_scope(result)
        elif self.mode_touched:
            result.get('context', {}).pop('research_team', None)
        return result

    def result_ids(self):
        cfg = team_draft(self.window._buffer or {}) or {}
        return list(dict.fromkeys(selection['reference']['job_id']
            for assignment in cfg.get('assignments', []) for selection in assignment.get('result_refs', [])))

    def update_actions(self):
        enabled = self.selected()
        self.show_tasks.setVisible(enabled)
        self.map_evidence.setVisible(enabled)
        self.map_evidence.setEnabled(enabled and not self.window._busy and bool(self.window.open_reference))
        for key, action in self.transfer_actions.items():
            action.setVisible(enabled)
            action.setEnabled(enabled and callable(getattr(self.window, 'research_team_transfer', None))
                and self.window.document is not None and not self.window._busy and not self.window.conflict)
        self.retry_transfer.setVisible(enabled and self._transfer_pending is not None)
        self.retry_transfer.setEnabled(enabled and not self.window._busy and not self.window.conflict)
        if not enabled:
            return
        self.panel.update_actions()
        window = self.window
        cfg = team_draft(window.edited_draft()) or {}
        state = records(window.document)
        started = cfg.get('phase_id') in state.get('phases', {})
        window.ask_button.setText('연구 시작' if not started else '개입 반영')
        window.ask_button.setToolTip('이번 질문과 팀 범위를 검토해 새 연구를 요청합니다.' if not started
                                    else '현재 의견을 남깁니다. 다음 범위 진행은 별도로 요청합니다.')
        window.next_button.setText('조사 계속')
        window.intervene_button.setVisible(False)
        window.protocol_budget.setText('모델 처리 ' + str(window.model_calls.value()) +
            ' / 도구 ' + str(window.tool_calls.value()) + ' — 설정…')
        current = state.get('phases', {}).get(cfg.get('phase_id'), {})
        waiting = [state.get('tasks', {}).get(key, {}) for key in current.get('task_ids', [])]
        _, _, active = window._protocol_state()
        base_enabled = bool(window.document and not window._busy and not window.conflict and
            not window._source_choosing and not window._protocol_steps and not window._protocol_delivery)
        window.next_button.setEnabled(base_enabled and started and any(row.get('status') not in
            ('COMPLETED', 'ACKNOWLEDGED_UNRESOLVED') for row in waiting) and not active and
            not window.document.get('discussion', {}).get('paused', False))
        if getattr(window, '_research_team_runtime', {}).get('status') == 'NOT_CONFIGURED':
            window.ask_button.setEnabled(False)
            window.next_button.setEnabled(False)
        window.protocol_budget.setToolTip('이번 범위에서 완료하지 못한 조사는 다음 명시 진행에서 이어집니다. 실제 청구량과 다릅니다.')
        if any(row.get('status') == 'WAITING_BUDGET' for row in waiting):
            window.identity.setText('조사 계속 대기')

    def start(self):
        if not self.selected():
            return None
        cfg = team_draft(self.window.edited_draft()) or {}
        if cfg.get('phase_id') not in records(self.window.document).get('phases', {}):
            return self.window.protocol_action('expert.ask')
        return self.window.protocol_action(None, participate=True)

    def reveal(self):
        self.stack.setCurrentIndex(1)
        if self.narrow:
            self.window.show_side(self.stack)
        else:
            self.stack.show()
            self.panel.tasks.setFocus()

    def reflow(self):
        narrow = self.window.width() < 1180 and self.selected()
        if narrow == self.narrow:
            return
        self.narrow = narrow
        if narrow:
            self.stack.setParent(None)
            self.window.side.addTab(self.stack, '연구 과제')
        else:
            index = self.window.side.indexOf(self.stack)
            if index >= 0:
                self.window.side.removeTab(index)
            self.stack.setParent(None)
            self.splitter.insertWidget(0, self.stack)
            self.stack.show()

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.Resize:
            self.reflow()
        return super().eventFilter(watched, event)

    def intervention(self, kind):
        window = self.window
        if not window.document or window.conflict or window._busy:
            return False
        item = window.turns.currentItem()
        turn_id = item.data(Qt.ItemDataRole.UserRole) if item else None
        cfg = team_draft(window.edited_draft())
        if not cfg:
            return False
        from caelab.research_team_followup import claim_rows
        claims = [row for row in claim_rows(window.document.get('discussion', {})) if row['turn_id'] == turn_id]
        target_claim = None
        if claims and kind in ('question', 'challenge'):
            labels = [(row.get('claim') or {}).get('text') or '선택 주장' for row in claims]
            selected, ok = QInputDialog.getItem(window, '질문할 주장', '선택 발언의 주장', labels, editable=False)
            if not ok:
                return False
            target_claim = claims[labels.index(selected)]['id']
        roles = cfg.get('assignments', [])
        if not roles:
            self.panel.review_team()
            return False
        names = [label_for_role(window._registry, row['expert_id']) for row in roles]
        selected, ok = QInputDialog.getItem(window, '답할 담당자', '담당자', names, editable=False)
        if not ok:
            return False
        draft = window.edited_draft()
        draft['context']['research_team']['requested_next'] = {
            'expert_id': roles[names.index(selected)]['expert_id'], 'task_id': None,
            'target_turn_id': turn_id, 'target_claim_id': target_claim}
        window._buffer = draft
        window.reply_to_turn(turn_id)
        window.classification.setCurrentIndex(window.classification.findData(kind))
        window.question.setFocus()
        window._edited()
        return True

    def transfer(self, kind):
        callback = getattr(self.window, 'research_team_transfer', None)
        if callable(callback):
            item = self.window.turns.currentItem()
            return callback(kind, item.data(Qt.ItemDataRole.UserRole) if item else None)
        return False

    def pick_results(self, parent, current):
        dialog = ResultSelectionDialog(self.window.client, parent)
        try:
            if dialog.exec() == QDialog.DialogCode.Accepted and dialog.selection:
                return [*deepcopy(current), deepcopy(dialog.selection)]
            return None
        finally:
            dialog.close()
            dialog.deleteLater()

    def choose_items(self, title, rows):
        """Explicit multi-selection, with identities only in item data."""
        dialog = QDialog(self.window)
        dialog.setWindowTitle(title)
        dialog.resize(640, 440)
        layout = QVBoxLayout(dialog)
        items = QListWidget()
        layout.addWidget(items, 1)
        for identity, text in rows:
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, identity)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            items.addItem(item)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText('선택')
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('취소')
        buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)
        items.itemChanged.connect(lambda _: buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(
            any(items.item(i).checkState() == Qt.CheckState.Checked for i in range(items.count()))))
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        try:
            if dialog.exec() == QDialog.DialogCode.Accepted:
                return [items.item(i).data(Qt.ItemDataRole.UserRole) for i in range(items.count())
                        if items.item(i).checkState() == Qt.CheckState.Checked]
            return None
        finally:
            dialog.close()
            dialog.deleteLater()

    def transfer_to_owner(self, kind, turn_id=None):
        window = self.window
        if not window.document or window._busy or window.conflict:
            return False
        if window.local_dirty:
            answer = QMessageBox.question(window, '연구 내용 저장', '편집한 연구 내용을 저장한 뒤 계속할까요?',
                QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel)
            if answer != QMessageBox.StandardButton.Save:
                return False
            return window.save_document(after=lambda: self.transfer_to_owner(kind, turn_id))
        if kind == 'study':
            from caelab.research_team_followup import claim_rows
            try:
                claims = claim_rows(window.document)
            except ValueError as error:
                window.message.setText('원 발언의 주장을 확인할 수 없습니다. 현재 편집은 유지됩니다.')
                window.message.setToolTip(str(error))
                return False
            if turn_id:
                claims = [row for row in claims if row['turn_id'] == turn_id]
            if not claims:
                window.message.setText('주장이 있는 연구 발언을 선택하세요.')
                return False
            selected = self.choose_items('Study에 반영할 주장', [(row['id'], row['claim']['text']) for row in claims])
            return self.prepare_transfer('study', {'claim_ids': selected}) if selected else False
        if kind == 'report':
            actions = [(key, row) for key, row in records(window.document).get('actions', {}).items()
                       if row.get('report', {}).get('status') == 'APPLIED']
            if not actions:
                window.conversation_pages.setCurrentWidget(window.report_view)
                window.message.setText('현재 자료 범위로 보고서를 작성한 뒤 보고서 문서로 열 수 있습니다.')
                return False
            labels = ['작성 보고서 ' + str(i + 1) for i in range(len(actions))]
            selected, accepted = QInputDialog.getItem(window, '보고서 문서로 열기', '작성한 보고서', labels, editable=False)
            if accepted:
                return self.prepare_transfer('report', {'action_id': actions[labels.index(selected)][0]})
            return False
        if kind == 'result':
            owner = (window.document['id'], window.document['session_id'])
            def listed(payload):
                if not window.document or owner != (window.document['id'], window.document['session_id']):
                    return
                plans = [row for row in payload.get('documents', []) if row.get('kind') == 'numerical']
                if not plans:
                    window.message.setText('이 연구의 계산 계획을 열고 계산 결과를 저장한 뒤 선택하세요.')
                    return
                labels = [str(i + 1) + '. ' + (row.get('title') or '계산 계획') for i, row in enumerate(plans)]
                selected, accepted = QInputDialog.getItem(window, '후속 검토할 계산', '계산 계획', labels, editable=False)
                if accepted:
                    window._call(lambda: window.client.document_read(plans[labels.index(selected)]['id']),
                        lambda plan: self.choose_followup_result(plan, owner))
            return window._call(window.client.documents, listed)
        return False

    def choose_followup_result(self, plan, owner):
        window = self.window
        if not window.document or owner != (window.document['id'], window.document['session_id']):
            return False
        source = plan.get('draft', {}).get('source') or {}
        if source.get('discussion_id') != window.document['id'] or 'proposal_index' not in source:
            window.message.setText('현재 연구 발언에서 연 계산 계획을 선택하세요.')
            return False
        dialog = ResultSelectionDialog(window.client, window, document_id=plan['id'])
        try:
            if dialog.exec() != QDialog.DialogCode.Accepted or not dialog.selection:
                return False
            result = deepcopy(dialog.selection)
        finally:
            dialog.close()
            dialog.deleteLater()
        cfg = team_draft(window.edited_draft()) or {}
        actors = self.choose_items('결과를 검토할 담당자', [(row['expert_id'], label_for_role(window._registry, row['expert_id']))
            for row in cfg.get('assignments', [])])
        if not actors:
            return False
        return self.prepare_transfer('result_review', {'turn_id': source['turn_id'],
            'proposal_index': source['proposal_index'], 'plan_document_id': plan['id'],
            'job_id': result['reference']['job_id'], 'selector': result['selector'], 'actor_ids': actors})

    def prepare_transfer(self, kind, selection):
        window = self.window
        if not window.document or window.local_dirty or window.conflict:
            window.message.setText('연구 입력이 변경되었습니다. 현재 내용을 저장한 뒤 다시 선택하세요.')
            return False
        from caelab.storage import canonical_hash
        signature = canonical_hash({'owner': window.document['id'], 'session': window.document['session_id'],
            'kind': kind, 'selection': selection})
        if not self._transfer_pending or self._transfer_pending['signature'] != signature:
            self._transfer_pending = {'signature': signature, 'document_id': window.document['id'],
                'kind': kind, 'selection': deepcopy(selection), 'session_id': window.document['session_id'],
                'expected_generation': window.document['generation'], 'command_id': 'C' + uuid.uuid4().hex,
                'submitted': deepcopy(window.edited_draft())}
        return self.send_transfer()

    def send_transfer(self, *_):
        window = self.window
        pending = deepcopy(self._transfer_pending)
        if not pending or not window.document or window._busy or window.conflict:
            return False
        if (window.document['id'], window.document['session_id']) != (pending['document_id'], pending['session_id']):
            window.message.setText('전달을 요청한 원 대화를 다시 여세요. 새 편집은 유지됩니다.')
            return False
        def accepted(payload):
            if not window.document or (window.document['id'], window.document['session_id']) != (pending['document_id'], pending['session_id']):
                return
            if pending['kind'] == 'result_review':
                if window.edited_draft() != pending['submitted']:
                    window.message.setText('후속 검토 초안을 준비했습니다. 이후 편집을 유지했으므로 자동 반영하지 않았습니다.')
                    return
                draft = team_selection_scope(payload['draft'])
                window._buffer = draft
                window._populating = True
                window.question.setPlainText(draft.get('composer', {}).get('text', ''))
                window.classification.setCurrentIndex(window.classification.findData(draft.get('composer', {}).get('classification')))
                window._populate_roles(draft.get('participants', []))
                window._populate_reply()
                window._populate_sources()
                window._populating = False
                window._edited()
                self.panel.refresh()
                window.message.setText('후속 검토 초안을 편집에 넣었습니다. 입력 검토 후 연구 시작을 요청하세요.')
            else:
                document = payload['document']
                if pending['kind'] == 'study':
                    from .study_window import StudyWindow
                    child = StudyWindow(window.client, document_id=document['id'])
                else:
                    from .report_window import ReportWindow
                    child = ReportWindow(window.client, document_id=document['id'])
                child.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
                children = getattr(window, '_portable_research_children', None)
                if children is None:
                    children = window._portable_research_children = []
                children.append(child)
                child.destroyed.connect(lambda: children.remove(child) if child in children else None)
                child.show()
                window.message.setText('연결한 연구 문서를 열었습니다.')
            self._transfer_pending = None
            window._update_actions()
        arguments = {key: pending[key] for key in ('document_id', 'kind', 'selection', 'session_id',
                                                  'expected_generation', 'command_id')}
        def failed(error):
            def notice():
                if not window._closed and self._transfer_pending == pending:
                    window.message.setText('전달 결과를 확인하지 못했습니다. 연구 메뉴에서 같은 요청을 다시 확인할 수 있습니다.')
                    window.message.setToolTip(str(error))
            QTimer.singleShot(0, notice)
        return window._call(lambda: window.client.research_team_transfer(**arguments), accepted, failure=failed)


def install(window, splitter, navigation):
    """Root's small ExpertWindow hunk installs this binding once."""
    if not hasattr(window, 'research_team'):
        window.research_team = _LayoutBinding(window, splitter, navigation)
    return window.research_team
