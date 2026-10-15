"""Independent Qt editor for the service-owned ordered EvaluationDefinition."""
from copy import deepcopy
import json
import uuid

from PySide6.QtCore import QThreadPool, QTimer, Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QCheckBox, QHBoxLayout, QInputDialog,
    QLabel, QLineEdit, QListWidget, QMainWindow, QMessageBox, QPushButton, QSplitter,
    QTableWidget, QTableWidgetItem, QTabWidget, QToolBar, QVBoxLayout, QWidget, QComboBox,
    QHeaderView, QMenu, QPlainTextEdit, QStyledItemDelegate)

from caelab.evaluation_definition import default_draft, diagnostics, document_reference, definition_hash
from caelab.storage import canonical_hash
from .data_window import _Read, display, integer_or_raw, number_or_raw, TERMINAL

ROLE = Qt.ItemDataRole.UserRole
DISPLAY_ROLE = int(ROLE) + 1
_COLUMNS = {
    'stages': [('id', '단계 식별자'), ('name', '단계 이름'), ('source', '저장된 원본 입력')],
    'transfers': [('id', '전달 식별자'), ('from_stage', '공급 단계'), ('output', '출력'),
                  ('to_stage', '수신 단계'), ('input', '입력'), ('mapping', '위치 연결'), ('lag', '전달 시점')],
    'bindings': [('id', '변수 이름'), ('stage', '단계'), ('input_id', '변경할 입력'), ('unit', '단위')],
    'responses': [('id', '응답 이름'), ('stage', '단계'), ('response', '단계 응답'), ('unit', '단위')],
    'checks': [('stage', '단계'), ('response', '응답'), ('unit', '단위'),
               ('absolute', '절대 허용값'), ('relative', '상대 허용값'), ('scale', '물리 기준값')],
}
_STATUS = {'SUCCEEDED':'완료', 'FAILED':'실패', 'REJECTED':'실행 불가', 'CANCELLED':'취소',
           'INTERRUPTED':'중단', 'PARTIAL_FAILURE':'일부 실패', 'NOT_CONVERGED':'미수렴',
           'CONVERGED':'수렴', 'RUNNING':'실행 중', 'QUEUED':'대기', 'STAGE_RUNNING':'단계 실행 중',
           'ITERATING':'반복 중', 'ONE_WAY_COMPLETED':'단방향 계산 완료',
           'CLEANUP_UNCONFIRMED':'종료 확인 필요'}


class _DraftDelegate(QStyledItemDelegate):
    def __init__(self, changed, parent):
        super().__init__(parent)
        self.changed = changed

    def createEditor(self, parent, option, index):
        editor = super().createEditor(parent, option, index)
        if isinstance(editor, QLineEdit):
            editor.textEdited.connect(self.changed)
        return editor

    def setEditorData(self, editor, index):
        if isinstance(editor, QLineEdit):
            text = index.data(Qt.ItemDataRole.DisplayRole)
            editor.setText(display(index.data(ROLE)) if text == index.data(DISPLAY_ROLE) else text)
        else:
            super().setEditorData(editor, index)


def item_value(item, numeric=False, integer=False, text=None):
    if item is None: return ''
    original = item.data(ROLE)
    text = item.text() if text is None else text
    if text == (item.data(DISPLAY_ROLE) or display(original)): return deepcopy(original)
    return integer_or_raw(text) if integer else number_or_raw(text) if numeric else text


class EvaluationWindow(QMainWindow):
    """Editable local buffer; shared HTTP owner retains all inputs and results."""
    def __init__(self, client, *, document_id=None, auto_open=True, poll_interval=1500,
                 runner_open=None, result_open=None, plan_open=None, source_open=None):
        super().__init__()
        self.client, self.document = client, None
        self.runner_open, self.result_open, self.plan_open, self.source_open = runner_open, result_open, plan_open, source_open
        self.local_dirty = self.conflict = self._busy = self._populating = self._accepting = False
        self._allow_close = False
        self._worker = None
        self._foreground_busy = False
        self._callback_calls = []
        self._draft = default_draft()
        self._view_error = None
        self._inspection = {'stages': [], 'diagnostics': []}
        self._catalog_sources = {}
        self._source_titles = {}
        self._selected_job = None
        self._transfer_windows = []
        self._selected_attempt = None
        self._progress = {}
        self._result = None
        self._build_ui()
        self.timer = QTimer(self)
        self.timer.setInterval(max(1, poll_interval))
        self.timer.timeout.connect(self.refresh_document)
        if poll_interval > 0: self.timer.start()
        if auto_open: self.open_document(document_id=document_id)

    def _build_ui(self):
        self.resize(1440, 900)
        self.setMinimumSize(950, 640)
        self.setWindowTitle('계산 절차')
        toolbar = QToolBar('Evaluation commands', self)
        toolbar.setMovable(False)
        self.addToolBar(toolbar)
        self.new_button = QPushButton('새 계산 절차…')
        self.open_button = QPushButton('계산 절차 열기…')
        self.apply_button = QPushButton('변경 적용')
        self.run_button = QPushButton('한 번 계산')
        self.save_button = QPushButton('저장')
        self.undo_button = QPushButton('되돌리기')
        self.redo_button = QPushButton('다시 실행')
        self.inspect_button = QPushButton('입출력 확인')
        self.plan_button = QPushButton('수치 계산 계획')
        self.runner_button = QPushButton('실행 작업')
        for button in (self.save_button, self.apply_button, self.run_button): toolbar.addWidget(button)
        self.run_button.setProperty('appearanceRole', 'primary')
        self._button_actions = []
        for button in (self.new_button, self.open_button, self.undo_button, self.redo_button, self.inspect_button, self.plan_button, self.runner_button):
            button.setParent(self)
            button.hide()
        for title, commands in [('파일(&F)', [(self.new_button,'Ctrl+N'),(self.open_button,'Ctrl+O'),(self.save_button,'Ctrl+S')]),
                                ('편집(&E)', [(self.undo_button,'Ctrl+Z'),(self.redo_button,'Ctrl+Y'),(self.apply_button,'Ctrl+Return')]),
                                ('연구(&R)', [(self.run_button,'F5'),(self.inspect_button,None),(self.plan_button,None),(self.runner_button,None)])]:
            menu = self.menuBar().addMenu(title)
            for button, shortcut in commands:
                action = menu.addAction(button.text())
                action.triggered.connect(button.click)
                if shortcut: action.setShortcut(QKeySequence(shortcut))
                self._button_actions.append((button, action))
        self.save_button.setToolTip('편집한 정의를 적용하고 저장합니다. 계산은 시작하지 않습니다.')
        self.run_button.setToolTip('적용된 정의로 한 번 계산합니다. 편집 중이거나 입력 오류가 있으면 실행할 수 없습니다.')
        self.new_button.clicked.connect(lambda: self._leave(lambda: self.open_document()))
        self.open_button.clicked.connect(self.choose_document)
        self.apply_button.clicked.connect(lambda: self.apply_inputs())
        self.run_button.clicked.connect(self.run_once)
        self.save_button.clicked.connect(lambda: self.save_document())
        self.undo_button.clicked.connect(lambda: self.command('document.undo'))
        self.redo_button.clicked.connect(lambda: self.command('document.redo'))
        self.inspect_button.clicked.connect(lambda: self.inspect_inputs())
        self.plan_button.clicked.connect(self.open_plan)
        self.runner_button.clicked.connect(self.open_runner)
        root = QWidget()
        outer = QVBoxLayout(root)
        self.identity = QLabel('로컬 서비스에 연결하세요.')
        self.identity.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.message = QLabel('단계를 추가해 계산 순서와 입력을 정하세요. 열기만으로 계산을 실행하지 않습니다.')
        self.message.setWordWrap(True)
        self.support = QLabel()
        self.support.setWordWrap(True)
        self.identity.setProperty('appearanceRole', 'section')
        outer.addWidget(self.identity)
        outer.addWidget(self.message)
        conflict = QHBoxLayout()
        self.reload_button, self.copy_button = QPushButton('현재 버전 다시 읽기'), QPushButton('편집 내용 별도 저장')
        self.reload_button.clicked.connect(self.reload_remote)
        self.copy_button.clicked.connect(lambda: self.open_document(draft=self.edited_draft(), title='복사한 계산 절차'))
        conflict.addWidget(self.reload_button); conflict.addWidget(self.copy_button); conflict.addStretch()
        outer.addLayout(conflict)
        vertical = self.vertical_splitter = QSplitter(Qt.Orientation.Vertical)
        vertical.setChildrenCollapsible(False)
        top = QSplitter(Qt.Orientation.Horizontal)
        top.setChildrenCollapsible(False)
        left = QWidget(); layout = QVBoxLayout(left)
        layout.addWidget(QLabel('계산 단계'))
        self.stage_list = QListWidget()
        self.stage_list.setObjectName('evaluationStageList')
        self.stage_list.currentRowChanged.connect(self._stage_selected)
        layout.addWidget(self.stage_list, 1)
        row = QHBoxLayout()
        add_stage = QPushButton('단계 추가…')
        add_stage.clicked.connect(self.add_stage)
        row.addWidget(add_stage, 1)
        for text, direction in [('↑', -1), ('↓', 1)]:
            button = QPushButton(text)
            button.setToolTip('선택 단계 ' + ('위로' if direction < 0 else '아래로'))
            button.clicked.connect(lambda checked=False, delta=direction: self.move_stage(delta))
            row.addWidget(button)
        layout.addLayout(row)
        selected_menu = QMenu(self)
        for text, handler in [('원본 입력 열기',self.open_source),('원본 교체…',self.replace_source),('단계 삭제',self.remove_stage)]:
            selected_menu.addAction(text, handler)
        selected = QPushButton('선택 단계 작업')
        selected.setMenu(selected_menu)
        layout.addWidget(selected)
        self.stage_summary = QLabel()
        self.stage_summary.setWordWrap(True)
        self.stage_summary.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.stage_summary)
        self.stage_editor = left
        top.addWidget(left)
        self.tabs = QTabWidget()
        self.tables = {}
        for key, title in [('stages', '단계'), ('transfers', '장 전달'), ('bindings', '변수'), ('responses', '응답')]:
            page = QWidget(); page_layout = QVBoxLayout(page)
            note = {'stages': '원본은 저장된 입력을 참조합니다. 물리 조건은 선택 단계의 원본 입력에서 편집하세요.',
                    'transfers': '같은 메시 전달 또는 명시한 P1 온도 보간을 선택합니다. 시간·온도 의미는 전달 설정에서 편집하며 이전 반복 전달에는 반복 계산이 필요합니다.',
                    'bindings': '변수는 등록된 단일 값 입력에 연결합니다. 단위와 실제 입력을 확인하세요.',
                    'responses': '계산에서 읽을 단계 응답과 단위를 정합니다. 응답 이름은 실제 계산과 같아야 합니다.'}[key]
            text = QLabel(note); text.setWordWrap(True); page_layout.addWidget(text)
            table = self._table(_COLUMNS[key], editable=True)
            table.setObjectName('evaluation' + {'stages':'Stages','transfers':'Transfers','bindings':'Variables','responses':'Responses'}[key])
            table.itemChanged.connect(self._edited)
            self.tables[key] = table
            page_layout.addWidget(table, 1)
            if key != 'stages':
                row = QHBoxLayout(); add = QPushButton(title + ' 추가…'); remove = QPushButton('선택 행 삭제')
                add.clicked.connect({'transfers': self.add_transfer, 'bindings': self.add_binding, 'responses': self.add_response}[key])
                remove.clicked.connect(lambda checked=False, name=key: self.remove_rows(name))
                row.addWidget(add); row.addWidget(remove)
                if key == 'transfers':
                    self.mapping_button = QPushButton('전달 설정…')
                    self.mapping_button.clicked.connect(self.edit_temperature_mapping)
                    row.addWidget(self.mapping_button)
                row.addStretch(); page_layout.addLayout(row)
            self.tabs.addTab(page, title)
        iteration = QWidget(); layout = QVBoxLayout(iteration)
        row = QHBoxLayout()
        self.iteration_enabled = QCheckBox('이전 반복의 결과를 받아 반복 계산')
        self.iteration_maximum = QLineEdit()
        self.iteration_maximum.setMaximumWidth(100)
        self.iteration_enabled.toggled.connect(self._edited)
        self.iteration_maximum.textEdited.connect(self._edited)
        row.addWidget(self.iteration_enabled); row.addWidget(QLabel('최대 반복 횟수')); row.addWidget(self.iteration_maximum); row.addStretch()
        layout.addLayout(row)
        note = QLabel('연속 계산값의 L∞ 차이를 절대 허용값 + 상대 허용값 × max(응답 크기, 물리 기준값)와 비교합니다. 허용값의 단위를 지정하세요. 첫 반복은 이전 값이 없습니다.')
        note.setWordWrap(True); layout.addWidget(note)
        self.tables['checks'] = self._table(_COLUMNS['checks'], editable=True)
        self.tables['checks'].setObjectName('evaluationConvergenceChecks')
        self.tables['checks'].itemChanged.connect(self._edited)
        layout.addWidget(self.tables['checks'], 1)
        row = QHBoxLayout(); add = QPushButton('수렴 기준 추가…'); remove = QPushButton('선택 기준 삭제')
        add.clicked.connect(self.add_check); remove.clicked.connect(lambda: self.remove_rows('checks'))
        row.addWidget(add); row.addWidget(remove); row.addStretch(); layout.addLayout(row)
        self.reuse_label = QLabel('재사용할 성공 단계 없음')
        self.reuse_label.setWordWrap(True); layout.addWidget(self.reuse_label)
        clear_reuse = QPushButton('재사용 선택 해제'); clear_reuse.clicked.connect(self.clear_reuse); layout.addWidget(clear_reuse)
        self.tabs.addTab(iteration, '반복 계산')
        top.addWidget(self.tabs); top.setSizes([245, 1180]); vertical.addWidget(top)
        bottom = QWidget(); layout = QVBoxLayout(bottom)
        row = QHBoxLayout(); self.runs = QComboBox(); self.runs.setMinimumWidth(120)
        self.runs.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.runs.currentIndexChanged.connect(self._run_selected)
        self.refresh_button = QPushButton('진행 다시 읽기')
        self.retry_button = QPushButton('성공 단계 재사용…')
        self.result_button = QPushButton('선택 결과 열기')
        self.transfer_button = QPushButton('전달값 보기…')
        self.refresh_button.clicked.connect(self.refresh_progress)
        self.retry_button.clicked.connect(self.prepare_retry)
        self.result_button.clicked.connect(self.open_stage_result)
        self.transfer_button.clicked.connect(self.open_transfer_values)
        row.addWidget(QLabel('계산')); row.addWidget(self.runs, 1)
        row.addWidget(self.refresh_button)
        row.addWidget(self.result_button)
        row.addWidget(self.transfer_button)
        result_menu = QMenu(self)
        retry_action = result_menu.addAction('같은 입력의 성공 단계 재사용…', self.retry_button.click)
        self._button_actions.append((self.retry_button, retry_action))
        result_more = QPushButton('계산 작업')
        result_more.setMenu(result_menu)
        row.addWidget(result_more)
        layout.addLayout(row)
        self.result_context = QLabel()
        self.result_context.setWordWrap(True)
        layout.addWidget(self.result_context)
        result_tabs = self.result_tabs = QTabWidget()
        self.attempts = self._table([('iteration', '반복'), ('stage_id', '단계'), ('attempt_id', '시도 식별자'), ('state', '상태'), ('backend', '계산 방법'), ('reused_from', '결과 재사용')])
        self.attempts.setObjectName('evaluationAttempts')
        self.attempts.itemSelectionChanged.connect(self._attempt_selected)
        result_tabs.addTab(self.attempts, '단계 실행')
        self.residuals = self._table([('iteration', '반복'), ('stage', '단계'), ('response', '응답'), ('unit', '단위'), ('observed', 'L∞ 차이'), ('limit', '실제 허용값'), ('passed', '기준 충족')])
        result_tabs.addTab(self.residuals, '수렴 기록')
        self.channels = self._table([('name', '응답'), ('kind', '형태'), ('unit', '단위'), ('component', '성분'), ('location', '위치'), ('value', '보존 값'), ('state', '단계 상태')])
        result_tabs.addTab(self.channels, '선택 단계의 값')
        layout.addWidget(result_tabs, 1)
        self.results_panel = bottom
        vertical.addWidget(bottom); vertical.setSizes([500, 290]); outer.addWidget(vertical, 1)
        outer.addWidget(self.support)
        self.details_toggle = QPushButton('기술 상세 펼치기')
        self.details_toggle.setCheckable(True)
        self.details_toggle.setFlat(True)
        self.details_toggle.toggled.connect(self._toggle_details)
        outer.addWidget(self.details_toggle, 0, Qt.AlignmentFlag.AlignLeft)
        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setMaximumHeight(150)
        self.details.hide()
        outer.addWidget(self.details)
        self.setCentralWidget(root)
        self._update_actions()

    def _table(self, columns, editable=False):
        table = QTableWidget(0, len(columns))
        table.setHorizontalHeaderLabels([label for _, label in columns])
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setAlternatingRowColors(True)
        table.verticalHeader().hide()
        table.verticalHeader().setDefaultSectionSize(28)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        if editable: table.setItemDelegate(_DraftDelegate(self._edited, table))
        if not editable: table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        return table

    def _put_rows(self, table, columns, rows, *, key=None):
        table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            for column, (name, _) in enumerate(columns):
                value = row.get(name, '')
                text = display(value)
                if name == 'source' and isinstance(value, dict):
                    text = self._source_titles.get(value.get('document_id')) or '저장된 ' + {'material':'재료', 'pde':'PDE', 'simulation':'해석'}.get(value.get('kind'), '원본') + ' 입력'
                elif name in ('stage', 'stage_id', 'from_stage', 'to_stage'):
                    text = self._stage_name(value, frozen=key is None)
                elif name in ('state', 'status'):
                    text = _STATUS.get(value, '상태 확인 전')
                elif name == 'mapping' and value == 'exact_same_mesh':
                    text = '같은 메시의 동일 위치'
                elif name == 'mapping' and value == 'p1_temperature':
                    text = '다른 P1 메시의 온도 보간'
                elif name == 'lag':
                    text = {0:'현재 반복', 1:'이전 반복'}.get(value, display(value))
                elif name == 'passed':
                    text = '충족' if value is True else '불충족' if value is False else '확인 전'
                elif name == 'reused_from':
                    text = '보존 결과 재사용' if value else '새 평가'
                elif name == 'value' and isinstance(value, dict):
                    text = ('저장 배열' if 'retained_array' in value else
                            str(value.get('count', '?')) + '개 값 (배열 요약)')
                elif name == 'kind':
                    text = {'scalar':'단일 값', 'series':'이력', 'field':'장'}.get(value, text)
                elif name == 'location':
                    text = {'controlled_fixture':'계산 대역', 'material_point':'재료점'}.get(value, text)
                item = QTableWidgetItem(text); item.setData(ROLE, deepcopy(value))
                item.setData(DISPLAY_ROLE, text)
                item.setToolTip(display(value))
                editable = key == 'stages' and name == 'name' or key == 'transfers' and name == 'lag' or key == 'bindings' and name == 'id' or key == 'responses' and name in ('id', 'response', 'unit') or key == 'checks' and name in ('absolute', 'relative', 'scale')
                if not editable: item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                table.setItem(row_index, column, item)
        for column, (name, _) in enumerate(columns):
            table.setColumnHidden(column, name == 'attempt_id' or name == 'backend' or
                                  name == 'id' and key in ('stages', 'transfers'))

    def _stage_name(self, identifier, *, frozen=False):
        draft = self._draft
        if frozen:
            run = next((r for r in (self.document or {}).get('runs', []) if r['job_id'] == self._selected_job), None)
            draft = run.get('draft', {}) if run else {}
        stage = next((s for s in draft.get('stages', []) if s.get('id') == identifier), None)
        if not frozen and not self._populating:
            table = self.tables.get('stages')
            for row in range(table.rowCount()) if table else []:
                item = table.item(row, 0)
                if item and item.data(ROLE) == identifier:
                    return table.item(row, 1).text()
        return stage.get('name', '이름 없음') if stage else '연결되지 않은 단계'

    def _toggle_details(self, checked):
        self.details.setVisible(checked)
        self.details_toggle.setText('기술 상세 접기' if checked else '기술 상세 펼치기')

    def _commit_editor(self):
        focus = QApplication.focusWidget()
        if focus and any(table.isAncestorOf(focus) for table in self.tables.values()):
            focus.clearFocus()

    def _show_document(self, document, *, preserve_draft=None, prefer_job=None):
        previous = (self.document or {}).get('id'), (self.document or {}).get('session_id'), self._selected_job
        self.document = deepcopy(document)
        self._draft = deepcopy(document['draft'] if preserve_draft is None else preserve_draft)
        self._populating = True
        self._view_error = None
        try:
            for key, table in self.tables.items():
                rows = self._draft['iteration']['checks'] if key == 'checks' else self._draft[key]
                if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows): raise ValueError('Malformed ' + key + ' structure remains preserved in the service draft')
                self._put_rows(table, _COLUMNS[key], rows, key=key)
            iteration = self._draft['iteration']
            if not isinstance(iteration, dict) or type(iteration.get('enabled')) is not bool: raise ValueError('Malformed iteration declaration is preserved')
            self.iteration_enabled.setChecked(iteration['enabled'])
            self.iteration_maximum.setText(display(iteration.get('maximum', '')))
            self._refresh_stage_list()
        except (ValueError, KeyError, TypeError) as error:
            self._view_error = str(error)
        self._selected_job = prefer_job or self._selected_job
        self.runs.clear()
        for number, run in enumerate(document.get('runs', []), 1):
            self.runs.addItem('계산 ' + str(number) + ' — ' + _STATUS.get(run.get('retained_state'), '진행 상태 확인 전') +
                             (' (현재 입력)' if run.get('is_current_input') else ' (이전 입력)'), run['job_id'])
        index = self.runs.findData(self._selected_job)
        if index < 0 and self.runs.count(): index = self.runs.count() - 1
        self.runs.setCurrentIndex(index)
        self._selected_job = self.runs.currentData()
        if previous != (document['id'], document['session_id'], self._selected_job):
            self._selected_attempt = None
            self._progress, self._result = {}, None
            for table in (self.attempts, self.residuals, self.channels):
                table.setRowCount(0)
        reuse = self._draft.get('reuse')
        self.reuse_label.setText('재사용할 성공 단계: ' + ', '.join(self._stage_name(s, frozen=True) for s in reuse['stages'])
                                 if reuse else '재사용할 성공 단계 없음')
        self.identity.setText(document.get('title', '계산 절차'))
        self.identity.setTextFormat(Qt.TextFormat.PlainText)
        self.results_panel.setVisible(bool(document.get('runs')))
        self._populating = False
        self._update_actions()

    def _refresh_stage_list(self):
        selected = self.stage_list.currentRow()
        self.stage_list.clear()
        for row in self._draft.get('stages', []): self.stage_list.addItem(self._stage_name(row.get('id')))
        if self.stage_list.count(): self.stage_list.setCurrentRow(max(0, min(selected, self.stage_list.count() - 1)))

    def edited_draft(self):
        focus = QApplication.focusWidget()
        result = deepcopy(self._draft)
        if self._view_error: return result
        for key, table in self.tables.items():
            rows = result['iteration']['checks'] if key == 'checks' else result[key]
            for index, row in enumerate(rows):
                for column, (name, _) in enumerate(_COLUMNS[key]):
                    if name == 'source': continue
                    pending = focus.text() if isinstance(focus, QLineEdit) and table.isAncestorOf(focus) and table.currentRow() == index and table.currentColumn() == column else None
                    row[name] = item_value(table.item(index, column), numeric=key == 'checks' and name in ('absolute', 'relative', 'scale'), integer=key == 'transfers' and name == 'lag', text=pending)
        result['iteration']['enabled'] = self.iteration_enabled.isChecked()
        original = self._draft['iteration'].get('maximum')
        text = self.iteration_maximum.text()
        result['iteration']['maximum'] = original if text == display(original) else integer_or_raw(text)
        return result

    def _edited(self, *args):
        if self._populating or not self.document: return
        self.local_dirty = canonical_hash(self.edited_draft()) != canonical_hash(self.document['draft'])
        if args and isinstance(args[0], QTableWidgetItem) and args[0].tableWidget() is self.tables['stages'] and args[0].column() == 1:
            self._refresh_stage_list()
        self._update_actions()

    def _replace_draft(self, draft):
        self._show_document(self.document, preserve_draft=draft)
        self._edited()

    def _update_actions(self):
        exists = self.document is not None
        usable = exists and not self._busy and not self.conflict
        errors = diagnostics(self.edited_draft()) if exists else []
        support = errors + self._inspection.get('diagnostics', [])
        self.support.setText('입력 확인 필요: ' + (self._view_error or support[0].get('message', ''))
                             if self._view_error or support else
                             '변경 사항 적용 전' if self.local_dirty else
                             '설정 검사를 통과했습니다. 계산 환경과 수치 검증은 실행 후 별도 확인합니다.')
        self.details.setPlainText(display({'document': self.document, 'input_diagnostics': support,
                                         'inspection': self._inspection, 'progress': self._progress}))
        for button in (self.apply_button, self.save_button, self.inspect_button): button.setEnabled(usable)
        self.run_button.setEnabled(usable and not self.local_dirty and not errors and not self._inspection.get('diagnostics'))
        self.undo_button.setEnabled(usable and not self.local_dirty and bool((self.document or {}).get('can_undo')))
        self.redo_button.setEnabled(usable and not self.local_dirty and bool((self.document or {}).get('can_redo')))
        self.plan_button.setEnabled(usable and not self.local_dirty and bool(self.plan_open))
        self.new_button.setEnabled(not self._busy); self.open_button.setEnabled(not self._busy)
        self.tabs.setEnabled(not self._foreground_busy); self.stage_list.setEnabled(not self._foreground_busy)
        self.stage_editor.setEnabled(not self._foreground_busy)
        self.runner_button.setEnabled(bool(self._selected_job) and bool(self.runner_open))
        self.refresh_button.setEnabled(exists and bool(self._selected_job) and not self._busy)
        self.retry_button.setEnabled(usable and bool(self._selected_job))
        self.result_button.setEnabled(bool(self._selected_attempt) and bool(self.result_open))
        self.transfer_button.setEnabled(exists and bool(self._selected_job) and not self._busy)
        self.reload_button.setVisible(self.conflict); self.copy_button.setVisible(self.conflict)
        for button, action in self._button_actions:
            action.setEnabled(button.isEnabled())
        self.result_context.setText('선택 계산의 보존 결과입니다. 편집 중인 내용은 반영되지 않았습니다.'
                                    if self.local_dirty else '선택 계산의 원 입력과 결과를 표시합니다.')
        self._stage_context()

    def _stage_context(self):
        index = self.stage_list.currentRow()
        stages = self.edited_draft().get('stages', [])
        if not 0 <= index < len(stages):
            self.stage_summary.setText('저장한 원본 입력을 추가해 단계 순서를 정하세요.')
            return
        stage = stages[index]
        catalog = self._catalog(stage['id']) or {}
        entries = catalog.get('inputs', [])
        inputs = ', '.join(str(e.get('label') or e['id']) + ' [' + str(e.get('unit', '?')) + ']' for e in entries[:3])
        outputs = catalog.get('ports', {}).get('outputs', {})
        self.stage_summary.setText(stage['name'] + '\n입력: ' + (inputs or '등록된 입력 확인 필요') +
                                   '\n출력: ' + (', '.join(name + ' [' + str(e.get('unit', '?')) + ']' for name, e in list(outputs.items())[:3]) or '응답에서 직접 지정'))

    def _call(self, function, accepted, *, relevant=None, background=False):
        if self._busy:
            if not background and (self._accepting or not self._foreground_busy):
                self._callback_calls.append((function, accepted, relevant, background)); return True
            return False
        self._busy = True; self._foreground_busy = not background; self._update_actions()
        worker = self._worker = _Read(function)
        def finished(value, error):
            self._accepting = True
            try:
                if relevant is None or relevant():
                    if error: self.message.setText('Request failed; current edits retained. ' + error)
                    else: accepted(value)
            finally:
                self._accepting = False; self._busy = False; self._foreground_busy = False; self._worker = None
            self._update_actions()
            if self._callback_calls:
                action, callback, guard, is_background = self._callback_calls.pop(0)
                self._call(action, callback, relevant=guard, background=is_background)
        worker.signals.finished.connect(finished, Qt.ConnectionType.QueuedConnection)
        QThreadPool.globalInstance().start(worker)
        return True

    def open_document(self, *, document_id=None, draft=None, title='계산 절차'):
        def accepted(document):
            self.local_dirty = self.conflict = False
            self._inspection = {'stages': [], 'diagnostics': []}; self._catalog_sources = {}
            self._selected_job = self._selected_attempt = None; self._progress = {}; self._result = None
            self.attempts.setRowCount(0); self.residuals.setRowCount(0); self.channels.setRowCount(0)
            self._show_document(document)
            QTimer.singleShot(0, self.inspect_inputs)
            if self._selected_job: QTimer.singleShot(20, self.refresh_progress)
        return self._call(lambda: self.client.document_open(kind='evaluation', document_id=document_id, title=title, draft=draft), accepted)

    def command(self, operation, arguments=None, *, after=None):
        if not self.document or self.conflict: return False
        if self.local_dirty and operation != 'evaluation.update':
            self.message.setText('편집한 정의를 먼저 변경 적용하세요.'); return False
        document = deepcopy(self.document)
        key = (document['id'], document['session_id'], document['generation'])
        def accepted(receipt):
            self.local_dirty = self.conflict = False
            job = receipt.get('job')
            self._show_document(receipt['document'], prefer_job=job.get('id') if job else None)
            self.message.setText({'evaluation.update':'변경을 적용했습니다.','document.save':'저장했습니다.','document.undo':'되돌렸습니다.','document.redo':'변경을 다시 적용했습니다.','evaluation.run':'계산을 요청했습니다.'}.get(operation,'작업을 반영했습니다.'))
            if after: after()
            elif job: QTimer.singleShot(0, self.refresh_progress)
            elif operation in ('evaluation.update', 'document.undo', 'document.redo'): QTimer.singleShot(0, self.inspect_inputs)
        return self._call(lambda: self.client.document_command(document['id'], operation, arguments or {},
            session_id=document['session_id'], expected_generation=document['generation'], command_id='C' + uuid.uuid4().hex), accepted,
            relevant=lambda: self.document and (self.document['id'], self.document['session_id'], self.document['generation']) == key)

    def apply_inputs(self, *, after=None):
        self._commit_editor()
        return self.command('evaluation.update', {'draft': self.edited_draft()}, after=after)

    def save_document(self, *, after=None):
        self._commit_editor()
        if self.local_dirty: return self.apply_inputs(after=lambda: self.command('document.save', after=after))
        return self.command('document.save', after=after)

    def run_once(self):
        self._commit_editor()
        return self.command('evaluation.run')

    def refresh_document(self):
        if not self.document or self._busy: return
        identity = (self.document['id'], self.document['session_id'])
        def accepted(remote):
            changed = (remote['session_id'], remote['generation']) != (self.document['session_id'], self.document['generation'])
            if changed and self.local_dirty:
                self.conflict = True; self.message.setText('다른 창에서 정의가 바뀌었습니다. 현재 버전을 다시 읽거나 편집 내용을 별도로 저장하세요.')
            elif not self.local_dirty and not self.conflict: self._show_document(remote)
            if self._selected_job: QTimer.singleShot(0, self.refresh_progress)
        return self._call(lambda: self.client.document_read(identity[0]), accepted, background=True,
            relevant=lambda: self.document and (self.document['id'], self.document['session_id']) == identity)

    def inspect_inputs(self, *, after=None):
        if not self.document: return False
        if self.local_dirty: return self.apply_inputs(after=lambda: self.inspect_inputs(after=after))
        identity = (self.document['id'], self.document['session_id'], self.document['generation'])
        def read():
            payload = self.client.evaluation_inspect(identity[0])
            documents = self.client.documents()
            return payload, {d['id']:d.get('title') for d in documents.get('documents', []) if d.get('title')}
        def accepted(values):
            payload, titles = values
            self._source_titles = titles
            self._inspection = deepcopy(payload)
            self._catalog_sources = {row['id']: canonical_hash(row['source']) for row in self.document['draft'].get('stages', [])}
            if after: after()
            self._populating = True
            for row in range(self.tables['stages'].rowCount()):
                item = self.tables['stages'].item(row, 2)
                source = item.data(ROLE)
                title = self._source_titles.get(source.get('document_id'))
                if title:
                    item.setText(title)
                    item.setData(DISPLAY_ROLE, title)
            self._populating = False
        return self._call(read, accepted,
            relevant=lambda: self.document and (self.document['id'], self.document['session_id'], self.document['generation']) == identity)

    def _source_picker(self, selected):
        if not self.document: return False
        identity = (self.document['id'], self.document['session_id'])
        relevant = lambda: self.document and (self.document['id'], self.document['session_id']) == identity
        def listed(payload):
            self._source_titles.update({row['id']:row.get('title', '') for row in payload['documents']})
            sources = [row for row in payload['documents'] if row.get('kind') in ('material', 'pde', 'simulation') and row.get('saved_revision') and not row.get('dirty')]
            if not sources: self.message.setText('먼저 재료·PDE·해석 문서의 입력을 저장한 뒤 단계를 추가하세요.'); return
            labels = [str(i + 1) + '. ' + row.get('title', '저장된 입력') for i, row in enumerate(sources)]
            choice, ok = QInputDialog.getItem(self, '저장된 원본 선택', '원본 입력', labels, editable=False)
            if ok:
                source = sources[labels.index(choice)]
                self._call(lambda: self.client.document_read(source['id']), lambda document: selected(document_reference(document)), relevant=relevant)
        return self._call(self.client.documents, listed, relevant=relevant)

    def add_stage(self):
        if self._foreground_busy: return
        def selected(reference):
            draft = self.edited_draft()
            draft['stages'].append({'id': 'S' + uuid.uuid4().hex[:12], 'name': self._source_titles.get(reference['document_id']) or {'material':'재료 단계','pde':'PDE 단계','simulation':'해석 단계'}[reference['kind']], 'source': reference})
            self._replace_draft(draft)
        return self._source_picker(selected)

    def replace_source(self):
        if self._foreground_busy: return
        index = self.stage_list.currentRow()
        if index < 0: return
        stage_id = self.edited_draft()['stages'][index]['id']
        def selected(reference):
            draft = self.edited_draft(); stage = next((row for row in draft['stages'] if row['id'] == stage_id), None)
            if stage: stage['source'] = reference; self._replace_draft(draft)
        return self._source_picker(selected)

    def move_stage(self, direction):
        if self._foreground_busy: return
        index = self.stage_list.currentRow(); draft = self.edited_draft()
        if not 0 <= index + direction < len(draft['stages']) or index < 0: return
        draft['stages'][index], draft['stages'][index + direction] = draft['stages'][index + direction], draft['stages'][index]
        self._replace_draft(draft); self.stage_list.setCurrentRow(index + direction)

    def remove_stage(self):
        if self._foreground_busy: return
        index = self.stage_list.currentRow()
        if index < 0: return
        draft = self.edited_draft(); draft['stages'].pop(index); self._replace_draft(draft)
        self.message.setText('Stage removed. Existing dependent rows stay visible; edit or remove missing-stage references before Run.')

    def _stage_selected(self, index):
        if index >= 0: self.tables['stages'].selectRow(index)
        self._stage_context()

    def _catalog(self, stage_id):
        stage = next((row for row in self.edited_draft()['stages'] if row['id'] == stage_id), None)
        if not stage or self._catalog_sources.get(stage_id) != canonical_hash(stage['source']): return None
        return next((row for row in self._inspection.get('stages', []) if row['id'] == stage_id), None)

    def _choose_stage(self, label):
        stages = self.edited_draft()['stages']
        choices = [str(i + 1) + '. ' + row['name'] for i, row in enumerate(stages)]
        if not choices: self.message.setText('먼저 저장된 원본으로 단계를 추가하세요.'); return None
        selected, ok = QInputDialog.getItem(self, label, '단계', choices, editable=False)
        return stages[choices.index(selected)]['id'] if ok else None

    def _ensure_catalog(self, continuation, checked):
        if all(self._catalog(row['id']) for row in self.edited_draft()['stages']): return True
        if not checked: self.inspect_inputs(after=continuation)
        else: self.message.setText('선택 원본의 입출력을 확인할 수 없습니다. 원본 오류를 수정한 뒤 입출력 확인을 다시 실행하세요.')
        return False

    def add_transfer(self, checked=False):
        if not self._ensure_catalog(lambda: self.add_transfer(True), checked): return
        from_stage = self._choose_stage('공급 단계 선택')
        if not from_stage: return
        outputs = self._catalog(from_stage).get('ports', {}).get('outputs', {})
        if not outputs: self.message.setText('이 원본에는 전달 가능한 출력이 없습니다.'); return
        output, ok = QInputDialog.getItem(self, '공급 출력 선택', '출력', list(outputs), editable=False)
        if not ok: return
        to_stage = self._choose_stage('수신 단계 선택')
        if not to_stage: return
        inputs = self._catalog(to_stage).get('ports', {}).get('inputs', {})
        inputs = {name: spec for name, spec in inputs.items() if spec.get('transfer') == 'exact_same_mesh' or 'p1_temperature' in spec.get('mappings', [])}
        if not inputs: self.message.setText('이 원본에는 지원되는 장 전달 입력이 없습니다.'); return
        port, ok = QInputDialog.getItem(self, '수신 입력 선택', '입력', list(inputs), editable=False)
        if not ok: return
        lag, ok = QInputDialog.getItem(self, '전달 시점', '시점', ['현재 반복 (0)', '이전 반복 (1)'], editable=False)
        if not ok: return
        transfer = {'id': 'F' + uuid.uuid4().hex[:12], 'from_stage': from_stage,
            'output': output, 'to_stage': to_stage, 'input': port, 'mapping': 'exact_same_mesh', 'lag': ['현재 반복 (0)', '이전 반복 (1)'].index(lag)}
        if 'p1_temperature' in inputs[port].get('mappings', []) and outputs[output].get('quantity') == 'absolute_temperature':
            choice, ok = QInputDialog.getItem(self, '공간 전달 방법', '방법',
                ['완전히 동일한 메시', '다른 P1 메시로 온도 보간'], 1, False)
            if not ok: return
            if choice == '다른 P1 메시로 온도 보간':
                from .temperature_mapping_dialog import configure
                transfer = configure(self, transfer)
                if transfer is None: return
        draft = self.edited_draft(); draft['transfers'].append(transfer)
        self._replace_draft(draft)

    def edit_temperature_mapping(self, checked=False):
        draft = self.edited_draft(); index = self.tables['transfers'].currentRow()
        if not 0 <= index < len(draft['transfers']):
            self.message.setText('설정할 전달을 선택하세요.'); return
        if not self._ensure_catalog(lambda: self.edit_temperature_mapping(True), checked): return
        row = draft['transfers'][index]
        target = self._catalog(row['to_stage']).get('ports', {}).get('inputs', {}).get(row['input'], {})
        if 'p1_temperature' not in target.get('mappings', []):
            self.message.setText('이 수신 capability는 기존 동일 메시 전달만 지원합니다.'); return
        from .temperature_mapping_dialog import configure
        replacement = configure(self, row)
        if replacement is not None:
            draft = self.edited_draft()
            # Modal edits change only this stable row, retaining pending names,
            # other mappings/options and uncommitted table values.
            for i, current in enumerate(draft['transfers']):
                if current['id'] == row['id']:
                    draft['transfers'][i] = replacement; self._replace_draft(draft); break

    def add_binding(self, checked=False):
        if not self._ensure_catalog(lambda: self.add_binding(True), checked): return
        stage_id = self._choose_stage('변경할 단계 선택')
        if not stage_id: return
        inputs = self._catalog(stage_id).get('inputs', [])
        if not inputs: self.message.setText('선택 단계에 등록된 단일 값 입력이 없습니다.'); return
        labels = [str(i + 1) + '. ' + row.get('label', row['id']) + ' [' + row['unit'] + ']' for i, row in enumerate(inputs)]
        selected, ok = QInputDialog.getItem(self, '변경할 입력 선택', '입력', labels, editable=False)
        if not ok: return
        descriptor = inputs[labels.index(selected)]
        identifier, ok = QInputDialog.getText(self, '변수 이름', '변수 이름', text=descriptor['id'])
        if not ok: return
        draft = self.edited_draft(); draft['bindings'].append({'id': identifier, 'stage': stage_id, 'input_id': descriptor['id'], 'unit': descriptor['unit']})
        self._replace_draft(draft)

    def _response_choice(self, title):
        stage_id = self._choose_stage(title)
        if not stage_id: return None
        catalog = self._catalog(stage_id) or {}
        outputs = catalog.get('ports', {}).get('outputs', {})
        choices = list(outputs) + ['응답 이름과 단위 직접 지정…']
        response, ok = QInputDialog.getItem(self, title, '응답', choices, editable=False)
        if not ok: return None
        if response in outputs: return stage_id, response, outputs[response]['unit']
        response, ok = QInputDialog.getText(self, title, '단계의 실제 응답 이름')
        if not ok: return None
        unit, ok = QInputDialog.getText(self, title, '응답 단위')
        return (stage_id, response, unit) if ok else None

    def add_response(self):
        selected = self._response_choice('읽을 응답 선택')
        if not selected: return
        stage_id, response, unit = selected
        identifier, ok = QInputDialog.getText(self, '응답 이름', '응답 이름', text=response)
        if ok:
            draft = self.edited_draft(); draft['responses'].append({'id': identifier, 'stage': stage_id, 'response': response, 'unit': unit}); self._replace_draft(draft)

    def add_check(self):
        selected = self._response_choice('반복 수렴 응답 선택')
        if not selected: return
        stage_id, response, unit = selected
        draft = self.edited_draft(); draft['iteration']['checks'].append({'stage': stage_id, 'response': response,
            'unit': unit, 'absolute': '', 'relative': '', 'scale': ''}); self._replace_draft(draft)
        self.message.setText('반복 계산 전에 절대·상대 허용값과 물리 기준값을 입력하세요.')

    def remove_rows(self, key):
        draft = self.edited_draft(); rows = draft['iteration']['checks'] if key == 'checks' else draft[key]
        for index in sorted({cell.row() for cell in self.tables[key].selectedIndexes()}, reverse=True): rows.pop(index)
        self._replace_draft(draft)

    def clear_reuse(self):
        draft = self.edited_draft(); draft['reuse'] = None; self._replace_draft(draft)

    def _run_selected(self, *args):
        if self._populating: return
        self._selected_job = self.runs.currentData(); self._selected_attempt = None; self._progress = {}; self._result = None
        self.attempts.setRowCount(0); self.residuals.setRowCount(0); self.channels.setRowCount(0)
        self._update_actions()
        QTimer.singleShot(0, self.refresh_progress)

    def refresh_progress(self):
        if not self.document or not self._selected_job: return
        identity = (self.document['id'], self.document['session_id'], self._selected_job)
        def accepted(payload):
            progress = payload.get('progress', payload)
            if not isinstance(progress, dict):
                self.message.setText('아직 진행 기록이 없습니다. 같은 계산을 다시 읽어 확인하세요.'); return
            self._progress = deepcopy(progress)
            self._populating = True
            self._put_rows(self.attempts, [('iteration', ''), ('stage_id', ''), ('attempt_id', ''), ('state', ''), ('backend', ''), ('reused_from', '')], progress.get('stages', []))
            residuals = [row for iteration in progress.get('iterations', []) for row in iteration.get('checks', [])]
            self._put_rows(self.residuals, [('iteration', ''), ('stage', ''), ('response', ''), ('unit', ''), ('observed', ''), ('limit', ''), ('passed', '')], residuals)
            self._populating = False
            if self._selected_attempt:
                match = next((i for i, row in enumerate(progress.get('stages', [])) if row.get('attempt_id') == self._selected_attempt), None)
                if match is not None: self.attempts.selectRow(match)
            self.message.setText('선택 계산: ' + _STATUS.get(progress.get('phase'), _STATUS.get(progress.get('execution_status'), '진행 상태 확인 필요')))
            index = self.runs.findData(identity[2])
            if index >= 0:
                run = next((r for r in self.document.get('runs', []) if r['job_id'] == identity[2]), {})
                status = _STATUS.get(progress.get('phase'), _STATUS.get(progress.get('execution_status'), '진행 상태 확인 필요'))
                self.runs.setItemText(index, '계산 ' + str(index + 1) + ' — ' + status +
                                      (' (현재 입력)' if run.get('is_current_input') else ' (이전 입력)') +
                                      (' / 미저장' if not run.get('retention_complete') else ''))
        return self._call(lambda: self.client.evaluation_progress(identity[0], identity[2]), accepted, background=True,
            relevant=lambda: self.document and (self.document['id'], self.document['session_id'], self._selected_job) == identity)

    def _attempt_selected(self):
        if self._populating: return
        indexes = self.attempts.selectedIndexes()
        if not indexes: return
        row = indexes[0].row()
        self._selected_attempt = self.attempts.item(row, 2).data(ROLE)
        state = self.attempts.item(row, 3).data(ROLE)
        self._update_actions()
        if state not in ('RUNNING', 'QUEUED'): QTimer.singleShot(0, self.read_stage_result)

    def read_stage_result(self):
        if not self.document or not self._selected_attempt: return
        identity = (self.document['id'], self.document['session_id'], self._selected_job, self._selected_attempt)
        def accepted(result):
            self._result = deepcopy(result)
            rows = []
            for name, response in result.get('responses', {}).items():
                value = response.get('value', response.get('data_ref'))
                if isinstance(value, dict) and 'data_ref' in value: value = {'retained_array': value['data_ref']}
                elif isinstance(value, list): value = {'count': len(value), 'first_values': value[:6]}
                rows.append({'name': name, **{key: response.get(key, '') for key in ('kind', 'unit', 'component', 'location')}, 'value': value, 'state': result.get('execution_status')})
            self._put_rows(self.channels, [('name', ''), ('kind', ''), ('unit', ''), ('component', ''), ('location', ''), ('value', ''), ('state', '')], rows)
        return self._call(lambda: self.client.evaluation_stage_result(identity[0], identity[2], identity[3], selection={'metadata_only': True}), accepted,
            relevant=lambda: self.document and (self.document['id'], self.document['session_id'], self._selected_job, self._selected_attempt) == identity)

    def prepare_retry(self):
        if not self.document or not self._selected_job: return
        job_id = self._selected_job
        run = next((row for row in self.document.get('runs', []) if row['job_id'] == job_id), None)
        if not run or not run.get('retention_complete') or not run.get('retained_result'):
            self.message.setText('완료된 계산을 먼저 저장한 뒤 성공 단계 재사용을 준비하세요.'); return
        draft = self.edited_draft()
        if definition_hash(draft) != definition_hash(run['draft']):
            self.message.setText('재사용은 계산 당시와 같은 입력에서만 가능합니다. 정의를 다시 열거나 입력 변경을 되돌리세요.'); return
        if draft['iteration']['enabled']:
            self.message.setText('반복은 지정한 초기 상태부터 다시 시작합니다. 반복 중간 상태의 재사용은 지원하지 않습니다.'); return
        successful = []
        for stage in draft['stages']:
            attempts = [row for row in self._progress.get('stages', []) if row.get('stage_id') == stage['id']]
            if not attempts or attempts[-1].get('state') != 'SUCCEEDED': break
            successful.append(stage['id'])
        count, ok = QInputDialog.getInt(self, '같은 입력 다시 계산 준비', '앞에서부터 재사용할 성공 단계 수', len(successful), 0, len(successful))
        if not ok: return
        identity = (self.document['id'], self.document['session_id'], job_id, canonical_hash(draft))
        def accepted(reference):
            current = self.edited_draft(); current['reuse'] = {'source': reference, 'stages': successful[:count]}; self._replace_draft(current)
            self.message.setText('같은 입력의 성공 단계 재사용을 준비했습니다. 변경 적용 후 한 번 계산을 명시적으로 실행하세요.')
        return self._call(lambda: self.client.document_result_reference(identity[0], job_id), accepted,
            relevant=lambda: self.document and (self.document['id'], self.document['session_id'], self._selected_job, canonical_hash(self.edited_draft())) == identity)

    def open_runner(self):
        if self.runner_open and self._selected_job: self.runner_open(self._selected_job)

    def open_stage_result(self):
        if self.result_open and self.document and self._selected_job and self._selected_attempt:
            identity = (self.document['id'], self._selected_job, self._selected_attempt)
            return self._call(lambda: self.result_open(*identity),
                lambda result: self.message.setText('선택한 단계의 보존 결과를 Post에서 열었습니다.'),
                relevant=lambda: self.document and (self.document['id'], self._selected_job, self._selected_attempt) == identity)

    def open_transfer_values(self):
        if not self.document or not self._selected_job or self._busy:
            return
        from .transfer_inspection_window import open_transfer_inspection
        window = open_transfer_inspection(self.client, self.document['id'], self._selected_job, parent=self)
        self._transfer_windows.append(window)

    def open_plan(self):
        if self.plan_open and self.document and not self.local_dirty:
            self.plan_open(self.document['id'], self.document['session_id'], self.document['generation'], 'C' + uuid.uuid4().hex)

    def open_source(self):
        index = self.stage_list.currentRow()
        if self.source_open and index >= 0: self.source_open(deepcopy(self.edited_draft()['stages'][index]['source']))

    def reload_remote(self):
        if self.document and QMessageBox.question(self, '현재 정의 다시 읽기', '적용하지 않은 편집을 버리고 현재 정의를 다시 읽을까요?', QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel) == QMessageBox.StandardButton.Yes:
            self.open_document(document_id=self.document['id'])

    def _leave(self, continuation):
        self._commit_editor()
        if not self.document or not self.local_dirty and not self.document.get('dirty'): continuation(); return
        box = QMessageBox(self); box.setWindowTitle('계산 절차 닫기'); box.setText('닫기 전에 정의를 저장할까요? 창을 닫아도 진행 중인 계산은 계속됩니다.')
        save = box.addButton('저장', QMessageBox.ButtonRole.AcceptRole)
        keep = box.addButton('입력을 적용하고 저장은 나중에', QMessageBox.ButtonRole.DestructiveRole)
        box.addButton(QMessageBox.StandardButton.Cancel); box.exec()
        if box.clickedButton() == save: self.save_document(after=continuation)
        elif box.clickedButton() == keep:
            if self.local_dirty: self.apply_inputs(after=continuation)
            else: continuation()

    def choose_document(self):
        def choose():
            def listed(payload):
                documents = [row for row in payload['documents'] if row.get('kind') == 'evaluation']
                labels = [str(i + 1) + '. ' + row.get('title', '계산 절차') for i, row in enumerate(documents)]
                if not labels: self.message.setText('저장된 계산 절차가 없습니다.'); return
                selected, ok = QInputDialog.getItem(self, '계산 절차 열기', '정의', labels, editable=False)
                if ok: self.open_document(document_id=documents[labels.index(selected)]['id'])
            self._call(self.client.documents, listed)
        self._leave(choose)

    def closeEvent(self, event):
        if self._allow_close:
            self.timer.stop(); event.accept(); return
        event.ignore()
        def close(): self._allow_close = True; self.close()
        self._leave(close)


def main(argv=None):
    import argparse
    from caelab.workbench_client import Client
    from .desktop import launch_tool, open_domain_plan, open_stage_result, open_saved_reference
    parser = argparse.ArgumentParser(description='Open the independent EvaluationDefinition editor')
    parser.add_argument('--service', required=True)
    parser.add_argument('--document-id', '--document', dest='document_id')
    args = parser.parse_args(argv)
    application = QApplication.instance() or QApplication([])
    client = Client(args.service)
    window = EvaluationWindow(client, document_id=args.document_id,
        runner_open=lambda job: launch_tool(client, 'runner', job),
        result_open=lambda document, job, attempt: open_stage_result(client, document, job, attempt),
        plan_open=lambda document, session, generation, command: open_domain_plan(client, document,
            session_id=session, expected_generation=generation, command_id=command),
        source_open=lambda reference: open_saved_reference(client, reference))
    window.show()
    return application.exec()


if __name__ == '__main__':
    raise SystemExit(main())
