"""Typed editor for actual Numerical request Plans, sharing the existing owner/UI.

The request is edited and saved independently of execution. Numeric libraries
and registered evaluators remain behind the shared service's numerical.run.
"""
from copy import deepcopy
import json
import math
import re
import uuid

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout,
    QInputDialog, QLabel, QLineEdit, QPushButton, QPlainTextEdit, QSplitter,
    QScrollArea, QStyledItemDelegate, QTableWidget, QTableWidgetItem, QHeaderView, QTabWidget, QToolBar, QTreeWidget,
    QTreeWidgetItem, QVBoxLayout, QWidget)

from caelab.numerical_document import request_draft
from caelab.storage import canonical_hash
from .numerical_window import NumericalWindow
from .runner_window import RunnerWindow, readonly_table, fill_tree, candidate_state
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure


DATA = Qt.ItemDataRole.UserRole
RETAINED_ROLES = {'doe': ('candidates',), 'analyze': ('table',), 'surrogate': ('training', 'holdout'),
                  'sensitivity': ('table', 'plan'), 'batch_export': ('candidates',),
                  'batch_import': ('batch', 'results')}
MODEL_OPERATIONS = {'evaluate', 'fit', 'doe', 'optimize', 'uq', 'epsilon'}
PDE_CANDIDATE_OPERATIONS = {'fit', 'doe', 'optimize', 'uq', 'epsilon'}


def value_text(value):
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)


def value_kind(value):
    return ('object' if isinstance(value, dict) else 'list' if isinstance(value, list) else
            'boolean' if type(value) is bool else 'number' if type(value) in (int, float) else
            'null' if value is None else 'string')


def numeric_text(text):
    try:
        value = json.loads(text)
        if type(value) in (int, float) and math.isfinite(value):
            return value
    except (ValueError, OverflowError):
        pass
    return text


def leaf_value(text, original):
    """Keep strings typed; numeric mistakes remain visible raw text for diagnostics."""
    if text == value_text(original):
        return deepcopy(original)
    kind = value_kind(original)
    if kind == 'string':
        return text
    try:
        parsed = json.loads(text)
    except ValueError:
        return text
    if kind == 'number' and type(parsed) in (int, float) and math.isfinite(parsed):
        return parsed
    if kind == 'boolean' and type(parsed) is bool or kind == 'null' and parsed is None:
        return parsed
    return text


class _InputDelegate(QStyledItemDelegate):
    def createEditor(self, parent, option, index):
        metadata = index.siblingAtColumn(0).data(DATA)
        if index.column() != 1 or not metadata or metadata['kind'] in {'object', 'list'}:
            return None
        return super().createEditor(parent, option, index)


class _WorksheetDelegate(QStyledItemDelegate):
    """Text precision and incomplete numbers remain visible editable drafts."""
    def createEditor(self, parent, option, index):
        binding = index.data(DATA) or {}
        if not binding.get('path'):
            return None
        if binding.get('choices'):
            editor = QComboBox(parent)
            editor.setEditable(True)  # Retain an existing unsupported value for repair.
            editor.addItems(binding['choices'])
            return editor
        return QLineEdit(parent)

    def setEditorData(self, editor, index):
        if isinstance(editor, QComboBox):
            editor.setCurrentText(index.data(Qt.ItemDataRole.DisplayRole) or '')
        else:
            editor.setText(index.data(Qt.ItemDataRole.DisplayRole) or '')
            editor.selectAll()

    def setModelData(self, editor, model, index):
        text = editor.currentText() if isinstance(editor, QComboBox) else editor.text()
        model.setData(index, text, Qt.ItemDataRole.EditRole)


class RequestPlanWindow(NumericalWindow):
    """Reuse NumericalWindow's service commands, retained jobs, save and close flow."""
    def __init__(self, client, document_id=None, poll_interval=2000, auto_open=True):
        self._post_observation = None
        self._observation_key = None
        self._return_messages = {}
        self._return_receipts = {}
        self._last_return_message = None
        self._worksheet_labels = {}
        self._candidate_plot_names = set()
        self._worksheet_responses = {}
        self._sheet_populating = False
        self._request_buffer = None
        self._runner_windows = []
        self._candidate_result_windows = []
        self._operation_inputs = {}
        self._shown_operation = None
        self._source_metadata = {}
        self._queued_result_retry = None
        self._queued_observation_read = None
        self._candidate_table_key = None
        self._candidate_selection_serial = 0
        self._pde_adoption_request = None
        super().__init__(client, document_id=document_id, poll_interval=poll_interval, auto_open=auto_open)
        self._observation_read_timer = QTimer(self)
        self._observation_read_timer.setSingleShot(True)
        self._observation_read_timer.timeout.connect(self._dispatch_observation_read)

    def _build_ui(self):
        self.resize(1440, 900)
        bar = QToolBar('계산 계획', self)
        self.addToolBar(bar)
        self.new_action = QAction('새 계획', self, shortcut=QKeySequence.New)
        self.open_action = QAction('계획 열기…', self, shortcut=QKeySequence.Open)
        self.save_action = QAction('저장', self, shortcut=QKeySequence.Save)
        self.undo_action = QAction('되돌리기', self, shortcut=QKeySequence.Undo)
        self.redo_action = QAction('다시 실행', self, shortcut=QKeySequence.Redo)
        file_menu, edit_menu = self.menuBar().addMenu('파일(&F)'), self.menuBar().addMenu('편집(&E)')
        file_menu.addActions([self.new_action, self.open_action, self.save_action])
        edit_menu.addActions([self.undo_action, self.redo_action])
        for action, callback in ((self.new_action, self.new_document), (self.open_action, self.choose_document),
            (self.save_action, self.save_document), (self.undo_action, lambda: self.command('document.undo')),
            (self.redo_action, lambda: self.command('document.redo'))):
            bar.addAction(action)
            action.triggered.connect(callback)
        self.apply_button, self.run_button = QPushButton('변경 적용'), QPushButton('계산 실행')
        self.run_button.setProperty('appearanceRole', 'primary')
        self.apply_button.clicked.connect(self.apply_inputs)
        self.run_button.clicked.connect(lambda: self.command('numerical.run'))
        bar.addWidget(self.apply_button)
        bar.addWidget(self.run_button)
        self.identity = QLabel()
        self.statusBar().addPermanentWidget(self.identity)
        root = QWidget()
        outer = QVBoxLayout(root)
        self.message = QLabel()
        self.message.setWordWrap(True)
        outer.addWidget(self.message)
        conflicts = QHBoxLayout()
        self.reload_button, self.copy_button = QPushButton('Reload service version'), QPushButton('Keep edits as new request Plan')
        self.reload_button.clicked.connect(self.reload_remote)
        self.copy_button.clicked.connect(lambda: self.open_document(draft=self.edited_draft(), title=self.document['title'] + ' (copy)'))
        conflicts.addWidget(self.reload_button)
        conflicts.addWidget(self.copy_button)
        outer.addLayout(conflicts)
        split = self.request_splitter = QSplitter(Qt.Orientation.Horizontal)
        outer.addWidget(split, 1)
        self.editor = QWidget()
        self.editor.setMinimumWidth(0)
        inputs_layout = QVBoxLayout(self.editor)
        self.input_tabs = QTabWidget()
        self.sheet = QWidget()
        self.sheet_layout = QVBoxLayout(self.sheet)
        self.advanced = QWidget()
        advanced_layout = QVBoxLayout(self.advanced)
        form = QFormLayout()
        self.purpose, self.backend, self.evaluations = QLineEdit(), QLineEdit(), QLineEdit()
        self.operation = QComboBox()
        methods = {'evaluate': '모델 평가', 'fit': '동정', 'doe': '실험계획 (DOE)', 'optimize': '최적화',
            'uq': '불확실성 분석', 'epsilon': '다목적 탐색', 'sample_sensitivity': '영향도 표본',
            'analyze': '후보 분석', 'surrogate': '대리모델', 'sensitivity': '영향도 분석',
            'batch_export': '계산 입력 내보내기', 'batch_import': '계산 결과 가져오기'}
        for name in ('evaluate', 'fit', 'doe', 'optimize', 'uq', 'epsilon', 'sample_sensitivity', 'analyze', 'surrogate', 'sensitivity', 'batch_export', 'batch_import'):
            self.operation.addItem(methods[name], name)
        self.purpose.setPlaceholderText('계산 목적이나 계획 이름')
        form.addRow('계산 목적', self.purpose)
        form.addRow('방법', self.operation)
        model_row = QHBoxLayout()
        model_row.addWidget(self.backend, 1)
        self.model_button = QPushButton('모델 선택…')
        self.model_button.clicked.connect(self.choose_model_document)
        model_row.addWidget(self.model_button)
        form.addRow('계산 모델', model_row)
        form.addRow('평가 횟수', self.evaluations)
        inputs_layout.addLayout(form)
        self.variables_button = QPushButton('변수 추가…')
        self.variables_button.setObjectName('useDeclaredModelVariables')
        self.variables_button.clicked.connect(self.choose_model_variables)
        variable_actions = QHBoxLayout()
        variable_actions.addWidget(QLabel('변수'), 1)
        variable_actions.addWidget(self.variables_button)
        self.remove_variable_button = QPushButton('제거')
        self.remove_variable_button.clicked.connect(self.remove_sheet_variables)
        variable_actions.addWidget(self.remove_variable_button)
        self.sheet_layout.addLayout(variable_actions)
        self.variable_sheet = self._sheet_table('planVariables', ['변수', '식별명', '시작값', '하한', '상한', '단위', '변환'])
        self.variable_sheet.setColumnHidden(1, True)
        self.sheet_layout.addWidget(self.variable_sheet, 2)
        self.model_response_button = QPushButton('응답 추가…')
        self.model_response_button.setObjectName('useRetainedModelResponse')
        self.model_response_button.clicked.connect(self.choose_model_response)
        response_actions = QHBoxLayout()
        response_actions.addWidget(QLabel('응답'), 1)
        response_actions.addWidget(self.model_response_button)
        self.constraint_button = QPushButton('제약 추가…')
        self.constraint_button.clicked.connect(lambda: self.choose_model_response(constraint=True))
        response_actions.addWidget(self.constraint_button)
        self.remove_response_button = QPushButton('제거')
        self.remove_response_button.clicked.connect(self.remove_sheet_responses)
        response_actions.addWidget(self.remove_response_button)
        self.sheet_layout.addLayout(response_actions)
        self.response_sheet = self._sheet_table('planResponses', ['역할', '응답', '축약', '방향 또는 관계', '한계값', '단위'])
        self.sheet_layout.addWidget(self.response_sheet, 2)
        self.method_sheet = self._sheet_table('planMethod', ['방법 설정', '값'])
        self.sheet_layout.addWidget(self.method_sheet, 1)
        self.input_tabs.addTab(self.sheet, '작업 조건')
        self.advanced_scroll = QScrollArea()
        self.advanced_scroll.setWidgetResizable(True)
        self.advanced_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.advanced_scroll.setWidget(self.advanced)
        self.input_tabs.addTab(self.advanced_scroll, '고급 입력')
        inputs_layout.addWidget(self.input_tabs, 1)
        self.observation_button = QPushButton('저장 관찰 추가…')
        self.observation_button.setObjectName('attachRetainedObservation')
        self.observation_button.clicked.connect(self.choose_fit_observation)
        advanced_layout.addWidget(self.observation_button)
        model_actions = QHBoxLayout()
        for label, callback in (('변수 선택…', self.choose_model_variables), ('응답 선택…', self.choose_model_response)):
            button = QPushButton(label)
            button.clicked.connect(callback)
            model_actions.addWidget(button)
        advanced_layout.addLayout(model_actions)
        self.backend.textEdited.connect(self._backend_edited)
        for field in (self.purpose, self.evaluations):
            field.textEdited.connect(self._edited)
        self.operation.currentIndexChanged.connect(self._edited)
        self.operation.currentIndexChanged.connect(self._operation_changed)
        retained = QHBoxLayout()
        self.retained_role = QComboBox()
        self.pin_button = QPushButton('저장 결과 선택…')
        self.pin_button.clicked.connect(self.choose_retained_result)
        self.response_button = QPushButton('응답 정의…')
        self.response_button.clicked.connect(self.choose_response_definition)
        for widget in (self.retained_role, self.pin_button, self.response_button):
            retained.addWidget(widget)
        advanced_layout.addLayout(retained)
        self.pinned_sources = readonly_table(['Role', 'Original document / job', 'Input revision', 'Exact result hash'])
        self.pinned_sources.setHorizontalHeaderLabels(['용도', '저장 결과', '입력 저장본', '결과 해시'])
        self.pinned_sources.setColumnHidden(2, True)
        self.pinned_sources.setColumnHidden(3, True)
        self.pinned_sources.setMaximumHeight(110)
        advanced_layout.addWidget(self.pinned_sources)
        self.declarations = readonly_table(['Physical response', 'Unit', 'Reduction', 'Component / location'])
        self.declarations.setMaximumHeight(105)
        advanced_layout.addWidget(self.declarations)
        self.operation_note = QLabel()
        self.operation_note.setWordWrap(True)
        advanced_layout.addWidget(self.operation_note)
        advanced_layout.addWidget(QLabel('모델과 방법의 상세 입력'))
        self.inputs = QTreeWidget()
        self.inputs.setObjectName('numericalRequestInputs')
        self.inputs.setHeaderLabels(['입력 항목', '값', '형식'])
        self.inputs.setMinimumHeight(230)
        self.inputs.setColumnWidth(0, 215)
        self.inputs.setColumnWidth(1, 230)
        self.inputs.setItemDelegate(_InputDelegate(self.inputs))
        self.inputs.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked | QAbstractItemView.EditTrigger.EditKeyPressed)
        self.inputs.itemChanged.connect(self._input_edited)
        self.inputs.setContextMenuPolicy(Qt.ContextMenuPolicy.ActionsContextMenu)
        self.add_input_action, self.remove_input_action, self.type_action = QAction('Add member / list entry…', self), QAction('Remove selected input', self), QAction('Change selected type…', self)
        self.add_input_action.triggered.connect(self.add_input)
        self.remove_input_action.triggered.connect(self.remove_input)
        self.type_action.triggered.connect(self.change_type)
        self.inputs.addActions([self.add_input_action, self.remove_input_action, self.type_action])
        advanced_layout.addWidget(self.inputs, 1)
        input_buttons = QHBoxLayout()
        for label, callback in (('항목 추가…', self.add_input), ('선택 제거', self.remove_input), ('형식 변경…', self.change_type)):
            button = QPushButton(label)
            button.clicked.connect(callback)
            input_buttons.addWidget(button)
        advanced_layout.addLayout(input_buttons)
        self.source_dialog = QDialog(self)
        self.source_dialog.setWindowTitle('연결 정보')
        self.source_dialog.resize(720, 420)
        source_layout = QVBoxLayout(self.source_dialog)
        self.source = QPlainTextEdit()
        self.source.setReadOnly(True)
        source_layout.addWidget(self.source)
        source_close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        source_close.rejected.connect(self.source_dialog.hide)
        source_layout.addWidget(source_close)
        self.source_context = QLabel()
        self.source_button = QPushButton('원본 문서 열기')
        self.source_button.clicked.connect(self.open_source)
        source_row = QHBoxLayout()
        source_row.addWidget(self.source_context, 1)
        source_row.addWidget(self.source_button)
        inputs_layout.addLayout(source_row)
        split.addWidget(self.editor)
        right = self.results_panel = QWidget()
        right.setMinimumWidth(0)
        result_layout = QVBoxLayout(right)
        result_layout.addWidget(QLabel('계산 이력'))
        self.runs = readonly_table(['계산', '상태', '계산 입력', '현재 계획과 관계'])
        self.runs.setColumnHidden(2, True)
        self.runs.setMaximumHeight(115)
        self.runs.itemSelectionChanged.connect(self._selection_changed)
        result_layout.addWidget(self.runs)
        actions = QHBoxLayout()
        self.read_button, self.runner_button = QPushButton('결과 읽기'), QPushButton('실행 작업')
        self.read_button.clicked.connect(self.retry_result)
        self.runner_button.clicked.connect(self.open_runner)
        actions.addWidget(self.read_button)
        actions.addWidget(self.runner_button)
        self.expert_button = QPushButton('전문가와 논의…')
        self.expert_button.clicked.connect(self.consult_expert)
        actions.addWidget(self.expert_button)
        self.return_button = QPushButton('결과 전달…')
        self.return_button.setObjectName('returnNumericalResult')
        self.return_button.clicked.connect(self.return_result)
        actions.addWidget(self.return_button)
        self.return_status_action = QAction('전달 상태 확인', self)
        self.return_status_action.triggered.connect(self.check_return_status)
        view_menu = self.menuBar().addMenu('보기(&V)')
        self.input_panel_action = QAction('입력 접기', self, checkable=True, checked=True)
        self.input_panel_action.toggled.connect(self._input_panel_toggled)
        view_menu.addAction(self.input_panel_action)
        bar.addAction(self.input_panel_action)
        source_details = QAction('연결 정보…', self)
        source_details.triggered.connect(self.show_source_details)
        view_menu.addAction(source_details)
        view_menu.addAction(self.return_status_action)
        result_layout.addLayout(actions)
        self.tabs = QTabWidget()
        self.candidates = readonly_table(['후보', '실행 상태', '변수 값', '목적값', '조건 충족', '실패 이유'])
        self.candidates.itemSelectionChanged.connect(self._candidate_changed)
        candidate_panel = QWidget()
        candidate_layout = QVBoxLayout(candidate_panel)
        self.tabs.addTab(candidate_panel, '계산 결과')
        self.responses = QTreeWidget()
        self.responses.setHeaderLabels(['응답 정보', '계산값'])
        self.tabs.addTab(self.responses, '응답 값')
        self.figure = Figure(figsize=(7, 4))
        self.canvas = FigureCanvasQTAgg(self.figure)
        plot_panel = QWidget()
        plot_layout = QVBoxLayout(plot_panel)
        self.plot_response = QComboBox()
        self.plot_response.currentIndexChanged.connect(self._plot_selected_result)
        plot_layout.addWidget(self.plot_response)
        plot_layout.addWidget(self.canvas)
        result_split = QSplitter(Qt.Orientation.Vertical)
        result_split.addWidget(self.candidates)
        result_split.addWidget(plot_panel)
        result_split.setSizes([260, 380])
        candidate_layout.addWidget(result_split)
        self.canvas.mpl_connect('pick_event', self._candidate_plot_picked)
        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        self.tabs.addTab(self.details, '기술 상세')
        observation_panel = self.observation_panel = QWidget()
        observation_layout = QVBoxLayout(observation_panel)
        observation_actions = QHBoxLayout()
        self.observed_trial = QComboBox()
        self.observed_trial.setObjectName('observedTrial')
        self.observed_trial.currentIndexChanged.connect(self._observation_trial_changed)
        observation_actions.addWidget(self.observed_trial, 1)
        self.observed_read = QPushButton('관찰 읽기')
        self.observed_read.clicked.connect(self.load_observation)
        observation_actions.addWidget(self.observed_read)
        self.observed_post = QPushButton('Post에서 열기')
        self.observed_post.setObjectName('openObservedPost')
        self.observed_post.clicked.connect(self.open_observed_post)
        observation_actions.addWidget(self.observed_post)
        observation_layout.addLayout(observation_actions)
        self.observed_info = QLabel('저장된 관찰을 선택하세요.')
        self.observed_info.setWordWrap(True)
        observation_layout.addWidget(self.observed_info)
        observed_split = QSplitter(Qt.Orientation.Vertical)
        self.observed_table = readonly_table(['자료 행', '원본 위치', '축 값', '관찰값', '사용 상태'])
        self.observed_table.setObjectName('observedPostSamples')
        self.observed_table.setColumnWidth(0, 85)
        self.observed_table.setColumnWidth(1, 100)
        self.observed_table.setColumnWidth(2, 100)
        self.observed_table.setColumnWidth(3, 100)
        self.observed_table.itemSelectionChanged.connect(self._observation_pick)
        observed_split.addWidget(self.observed_table)
        self.observed_figure = Figure(figsize=(6, 3))
        self.observed_canvas = FigureCanvasQTAgg(self.observed_figure)
        self.observed_canvas.mpl_connect('pick_event', self._observation_plot_pick)
        observed_split.addWidget(self.observed_canvas)
        observed_split.setSizes([220, 330])
        observation_layout.addWidget(observed_split, 1)
        self.tabs.addTab(observation_panel, '관찰 곡선')
        result_layout.addWidget(self.tabs, 1)
        self.candidate_results_button = QPushButton('선택 후보 결과 열기')
        self.candidate_results_button.setObjectName('openCandidateStageResults')
        self.candidate_results_button.clicked.connect(self.open_candidate_results)
        result_layout.addWidget(self.candidate_results_button)
        self.pde_adopt_button = QPushButton('Review / adopt candidate to PDE…')
        self.pde_adopt_button.setObjectName('reviewPDECandidate')
        self.pde_adopt_button.clicked.connect(self.review_pde_candidate)
        result_layout.addWidget(self.pde_adopt_button)
        self._build_adoption_receipt_ui(result_layout)
        split.addWidget(right)
        split.setSizes([640, 800])
        split.setStretchFactor(0, 1)
        split.setStretchFactor(1, 1)
        self.canvas.mpl_connect('resize_event', self._fit_plot_layout)
        self.observed_canvas.mpl_connect('resize_event', self._fit_plot_layout)
        self.setCentralWidget(root)
        self._update_actions()

    def _input_panel_toggled(self, visible):
        self.input_panel_action.setText('입력 접기' if visible else '입력 펼치기')
        if not visible:
            self._input_panel_sizes = self.request_splitter.sizes()
        self.editor.setVisible(visible)
        if visible:
            self.request_splitter.setSizes(getattr(self, '_input_panel_sizes', [640, 800]))

    def show_source_details(self):
        draft = self.edited_draft() if self.document else {}
        draft = draft if isinstance(draft, dict) else {}
        request = draft.get('request', {})
        inputs = request.get('inputs', {}) if isinstance(request, dict) else {}
        inputs = inputs if isinstance(inputs, dict) else {}
        self.source.setPlainText(json.dumps({'source': draft.get('source'),
            'result_refs': inputs.get('result_refs', {})},
            ensure_ascii=False, indent=2))
        self.source_dialog.show()
        self.source_dialog.raise_()

    def _fit_plot_layout(self, event):
        if event.canvas.width() >= 240 and event.canvas.height() >= 160 and event.canvas.figure.axes:
            event.canvas.figure.tight_layout()

    def selected_job(self):
        rows = sorted({item.row() for item in self.runs.selectedIndexes()})
        item = self.runs.item(rows[0], 0) if len(rows) == 1 else None
        return item.data(DATA) if item else None

    def _populate_runs(self, prefer_job=None):
        super()._populate_runs(prefer_job)
        states = {'SUCCEEDED': '완료', 'PARTIAL_FAILURE': '일부 실패', 'FAILED': '실패',
                  'REJECTED': '실행 불가', 'CANCELLED': '취소', 'RUNNING': '계산 중',
                  'QUEUED': '대기 중', 'Awaiting status': '상태 확인 중'}
        for row in range(self.runs.rowCount()):
            self.runs.item(row, 0).setText('계산 ' + str(row + 1))
            state = self.runs.item(row, 1)
            state.setText(states.get(state.data(DATA), state.text()))
            run = self.document['runs'][row]
            self.runs.item(row, 2).setText('계산 당시 입력')
            self.runs.item(row, 3).setText('현재 입력' if run.get('is_current_input') and not self.local_dirty else '이전 입력')

    def _sheet_table(self, name, headers):
        table = QTableWidget(0, len(headers))
        table.setObjectName(name)
        table.setHorizontalHeaderLabels(headers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        table.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked | QAbstractItemView.EditTrigger.EditKeyPressed)
        table.setItemDelegate(_WorksheetDelegate(table))
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        table.horizontalHeader().setStretchLastSection(True)
        table.verticalHeader().setVisible(False)
        table.itemChanged.connect(self._sheet_changed)
        widths = {'planVariables': [120, 100, 66, 66, 66, 50, 58],
                  'planResponses': [90, 175, 80, 105, 80, 65],
                  'planMethod': [220, 250]}
        for column, width in enumerate(widths[name]):
            table.setColumnWidth(column, width)
        return table

    def _sheet_cell(self, table, row, column, value, path=None, *, numeric=False, choices=(), entry=None, label=None):
        text = label if label is not None else '' if value is None else value_text(value)
        item = QTableWidgetItem(text)
        item.setToolTip(text)
        item.setData(DATA, {'path': path, 'numeric': numeric, 'choices': list(choices),
                            'shown': text, 'entry': entry})
        if path is None:
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        table.setItem(row, column, item)

    def _refresh_worksheet(self):
        """Project the one typed-input buffer; never normalize unsupported fields."""
        root = self.inputs.topLevelItem(0)
        if root is None or self._sheet_populating:
            return
        value = self._input_value(root)
        self._sheet_populating = True
        try:
            variables = value.get('variables', [])
            variables = variables if isinstance(variables, list) else []
            self.variable_sheet.setRowCount(len(variables))
            for index, variable in enumerate(variables):
                if not isinstance(variable, dict):
                    variable = {}
                identifier = variable.get('id')
                label = self._worksheet_labels.get(identifier, identifier) if isinstance(identifier, str) else value_text(identifier)
                self._sheet_cell(self.variable_sheet, index, 0, label or 'Unsupported row', entry=('variables', index))
                self._sheet_cell(self.variable_sheet, index, 1, identifier)
                for col, key in enumerate(('value', 'lower', 'upper', 'unit', 'transform'), 2):
                    self._sheet_cell(self.variable_sheet, index, col,
                        variable.get(key, 'linear' if key == 'transform' else None),
                        ('variables', index, key) if isinstance(variables[index], dict) else None,
                        numeric=key in {'value', 'lower', 'upper'}, choices=('linear', 'log') if key == 'transform' else ())
            rows = []
            operation = self.operation.currentData()
            if operation == 'doe':
                for index, response in enumerate(value.get('responses', []) if isinstance(value.get('responses', []), list) else []):
                    definition = self._worksheet_responses.get(response, {}) if isinstance(response, str) else {}
                    rows.append(('Response', response, definition, ('responses', index)))
            elif operation == 'optimize':
                if 'objective' in value:
                    definition = value['objective']
                    rows.append(('Objective', definition.get('response') if isinstance(definition, dict) else None, definition, ('objective',)))
                for index, definition in enumerate(value.get('constraints', []) if isinstance(value.get('constraints', []), list) else []):
                    rows.append(('Constraint', definition.get('response') if isinstance(definition, dict) else None, definition, ('constraints', index)))
            self.response_sheet.setHorizontalHeaderLabels(['Role', 'Response', 'Reduction', 'Direction / relation', 'Limit', 'Unit'])
            self.response_sheet.setRowCount(len(rows))
            for row, (role, selector, definition, path) in enumerate(rows):
                self._sheet_cell(self.response_sheet, row, 0, role, entry=path)
                self._sheet_cell(self.response_sheet, row, 1, selector or 'Use actual response…')
                definition = definition if isinstance(definition, dict) else {}
                editable = role != 'Response' and isinstance(self._at_path(value, path), dict)
                self._sheet_cell(self.response_sheet, row, 2, definition.get('reduction'),
                    path + ('reduction',) if editable else None, choices=('none', 'max', 'min', 'mean', 'final', 'abs_max'))
                key = 'operator' if role == 'Constraint' else 'direction'
                self._sheet_cell(self.response_sheet, row, 3, definition.get(key),
                    path + (key,) if editable else None,
                    choices=('<=', '>=') if role == 'Constraint' else ('minimize', 'maximize'))
                self._sheet_cell(self.response_sheet, row, 4, definition.get('limit'),
                    path + ('limit',) if editable and role == 'Constraint' else None, numeric=True)
                self._sheet_cell(self.response_sheet, row, 5, definition.get('unit', 'undeclared'))
                self.response_sheet.item(row, 1).setToolTip(json.dumps(definition, ensure_ascii=False, indent=2))
            settings = ([('Sample count', ('count',), 16, True, ()), ('Random seed', ('seed',), 0, True, ())]
                if operation == 'doe' else [
                    ('Generations', ('options', 'max_generations'), 40, True, ()),
                    ('Population size', ('options', 'population_size'), 12, True, ()),
                    ('Random seed', ('seed',), 0, True, ()),
                    ('Retain responses', ('options', 'retain_responses'), 'summary', False, ('summary', 'all'))]
                if operation == 'optimize' else [])
            if operation == 'fit':
                self.response_sheet.setHorizontalHeaderLabels(['관찰', '모델 응답', '역할', '가중치', '잔차 척도', '관찰 채널'])
                trials = value.get('experiments', [])
                trials = trials if isinstance(trials, list) else []
                self.response_sheet.setRowCount(len(trials))
                prior_trial = self.observed_trial.currentData()
                self.observed_trial.blockSignals(True)
                self.observed_trial.clear()
                for index, trial in enumerate(trials):
                    if not isinstance(trial, dict):
                        continue
                    path = ('experiments', index)
                    observation = trial.get('observation_ref', {})
                    observation = observation if isinstance(observation, dict) else {}
                    identifier = str(trial.get('id', ''))
                    label = '관찰 ' + str(index + 1) if re.fullmatch(r'post_[0-9a-f]{16}', identifier) else identifier
                    self._sheet_cell(self.response_sheet, index, 0, trial.get('id'), path + ('id',), entry=path, label=label)
                    self.response_sheet.item(index, 0).setToolTip(identifier)
                    self._sheet_cell(self.response_sheet, index, 1, trial.get('response') or 'Choose model response…')
                    self._sheet_cell(self.response_sheet, index, 2, trial.get('role', 'fit'), path + ('role',), choices=('fit', 'holdout'))
                    self._sheet_cell(self.response_sheet, index, 3, trial.get('weight', 1), path + ('weight',), numeric=True)
                    self._sheet_cell(self.response_sheet, index, 4, trial.get('scale', 1), path + ('scale',), numeric=True)
                    self._sheet_cell(self.response_sheet, index, 5, observation.get('response', 'unassigned'))
                    if observation.get('result'):
                        self.observed_trial.addItem(label + ' (' + str(observation.get('response', '')) + ')', index)
                prior_index = self.observed_trial.findData(prior_trial)
                if prior_index >= 0:
                    self.observed_trial.setCurrentIndex(prior_index)
                self.observed_trial.blockSignals(False)
                if self._post_observation and not self._observation_matches():
                    self._observation_trial_changed()
                method = value.get('method', 'least_squares')
                settings = [('Fit method', ('method',), 'least_squares', False, ('least_squares', 'differential_evolution'))]
                settings += ([('Function evaluations', ('options', 'max_nfev'), 100, True, ())]
                    if method == 'least_squares' else [
                        ('Generations', ('options', 'max_generations'), 40, True, ()),
                        ('Population size', ('options', 'population_size'), 12, True, ())])
            refs = value.get('result_refs', {})
            if operation == 'doe' and ('candidates' in value or isinstance(refs, dict) and 'candidates' in refs):
                settings = [] if isinstance(refs, dict) and 'candidates' in refs else settings[1:]
            self.method_sheet.setRowCount(len(settings))
            for row, (label, path, default, numeric, choices) in enumerate(settings):
                try:
                    setting = self._at_path(value, path)
                    implicit = False
                except (KeyError, TypeError):
                    setting, implicit = default, True
                editable = not ('options' in path and 'options' in value and not isinstance(value['options'], dict))
                self._sheet_cell(self.method_sheet, row, 0, label)
                self._sheet_cell(self.method_sheet, row, 1, setting, path if editable else None, numeric=numeric, choices=choices)
                if implicit:
                    self.method_sheet.item(row, 1).setToolTip('Existing engine default; no field is written until edited.')
        finally:
            self._sheet_populating = False

    def _sheet_changed(self, item):
        if self._sheet_populating or self._populating or self._view_error:
            return
        binding = item.data(DATA) or {}
        path = binding.get('path')
        if not path or item.text() == binding.get('shown'):
            return
        text = item.text()
        def change(value):
            parent = value
            for key in path[:-1]:
                if isinstance(parent, dict) and key not in parent:
                    parent[key] = {}
                parent = parent[key]
            parent[path[-1]] = numeric_text(text) if binding.get('numeric') else text
        # The tree remains the single authoritative buffer. Do not clear the
        # live table editor during its delegate commit or round partial text.
        value = self._input_value(self.inputs.topLevelItem(0))
        try:
            change(value)
        except (ValueError, TypeError, KeyError, IndexError) as error:
            self.message.setText('Repair the input structure in Model / advanced: ' + str(error))
            return
        self._sheet_populating = True
        try:
            self._populate_inputs(value)
            binding['shown'] = text
            item.setData(DATA, binding)
            item.setToolTip(text)
        finally:
            self._sheet_populating = False
        self._edited()

    def _remove_sheet_entries(self, table):
        entries = [table.item(index.row(), 0).data(DATA).get('entry')
                   for index in table.selectionModel().selectedRows()]
        def remove(value):
            # Descending indices preserve the original selected rows.
            for path in reversed(entries):
                if path:
                    self._at_path(value, path[:-1]).__delitem__(path[-1])
        if entries:
            entries.sort(key=lambda path: (str(path[0]), path[-1] if isinstance(path[-1], int) else -1))
            self._edit_structure(remove)

    def remove_sheet_variables(self):
        self._remove_sheet_entries(self.variable_sheet)

    def remove_sheet_responses(self):
        self._remove_sheet_entries(self.response_sheet)

    def choose_model_document(self):
        if not self.document or self._busy or self._callbacks or self.conflict:
            return False
        context = self._request_context()
        relevant = lambda: self._request_context() == context and not self.conflict
        def read(document):
            if not relevant():
                return
            if document.get('dirty') or not document.get('saved_revision') or document.get('diagnostics'):
                self.message.setText('Save a valid model in its own tool before selecting it.')
                return
            if document['kind'] == 'evaluation':
                inputs = {'backend': 'evaluation.definition', 'settings': {'definition_ref': {
                    'document_id': document['id'], 'kind': 'evaluation', 'saved_revision': document['saved_revision'],
                    'input_revision': document['input_revision'], 'input_sha256': canonical_hash(document['draft'])}}}
            else:
                inputs = document['draft']
            if not isinstance(inputs, dict) or not isinstance(inputs.get('backend'), str) or not isinstance(inputs.get('settings'), dict):
                self.message.setText('This saved model has no supported evaluator/settings declaration. Existing inputs remain.')
                return
            from PySide6.QtWidgets import QMessageBox
            answer = QMessageBox.question(self, 'Use saved model', 'Use ' + document['title'] +
                ' as the evaluator? Existing variable bounds, responses and method options will remain for review.')
            if answer != QMessageBox.StandardButton.Yes or not relevant():
                return
            self._worksheet_labels.clear()
            self._worksheet_responses.clear()
            if self.operation.currentData() == 'fit':
                trials = self.edited_draft()['request']['inputs'].get('experiments', [])
                if not isinstance(trials, list) or not trials or any(not isinstance(row, dict) for row in trials):
                    self.message.setText('Add a trial before choosing its model protocol.')
                    return
                selected = 0
                if len(trials) > 1:
                    labels = [str(index + 1) + ': ' + str(row.get('id')) for index, row in enumerate(trials)]
                    label, ok = QInputDialog.getItem(self, 'Use model protocol', 'Trial', labels, editable=False)
                    if not ok or not relevant():
                        return
                    selected = labels.index(label)
                def bind_model(value):
                    value['backend'] = inputs['backend']
                    value['experiments'][selected]['settings'] = deepcopy(inputs['settings'])
                self._edit_structure(bind_model)
            else:
                self._edit_structure(lambda value: value.update(backend=inputs['backend'], settings=deepcopy(inputs['settings'])))
        def listed(payload):
            documents = [row for row in payload['documents'] if row.get('kind') in {'material', 'pde', 'simulation', 'evaluation'}]
            labels = [row['title'] + ' (' + row['kind'] + ') — ' + row['id'] for row in documents]
            if not labels:
                self.message.setText('No saved model is available. Enter a registered evaluator and its settings in Model / advanced.')
                return
            label, ok = QInputDialog.getItem(self, 'Use saved model', 'Model', labels, editable=False)
            if ok and relevant():
                self._call(lambda: self.client.document_read(documents[labels.index(label)]['id']), read, relevant=relevant)
        return self._call(self.client.documents, listed, relevant=relevant)

    def _candidate_plot_picked(self, event):
        ids = getattr(event.artist, '_candidate_ids', [])
        if not len(getattr(event, 'ind', [])):
            return
        index = int(event.ind[0])
        if index >= len(ids):
            return
        for row in range(self.candidates.rowCount()):
            if self.candidates.item(row, 0).text() == ids[index]:
                self.candidates.selectRow(row)
                self.candidates.scrollToItem(self.candidates.item(row, 0))
                break

    def open_document(self, *, document_id=None, title='Numerical request Plan', draft=None):
        if document_id is None and draft is None:
            draft = request_draft()
        return super().open_document(document_id=document_id, title=title, draft=draft)

    def _opened(self, document):
        from .result_return import bind_receiver
        if not bind_receiver(self, document):
            return
        self.local_dirty = self.conflict = False
        self._result_cache.clear()
        self._result_errors.clear()
        self._statuses.clear()
        self._show_document(document)
        self.message.setText('계산 계획을 열었습니다.')
        self._post_observation = None
        self._observation_key = None
        if self.operation.currentData() == 'fit' and self.observed_trial.count():
            self.tabs.setCurrentWidget(self.observation_panel)
            self.load_observation()

    @staticmethod
    def _shape_error(draft):
        if not isinstance(draft, dict) or set(draft) - {'method_inputs'} != {'mode', 'request', 'source'} or draft.get('mode') != 'request':
            return 'This document is not a request Plan. Its original draft is retained; use its own editor or Undo.'
        if 'method_inputs' in draft and (not isinstance(draft['method_inputs'], dict)
                or any(not isinstance(value, dict) for value in draft['method_inputs'].values())):
            return 'Saved method inputs must be named editable objects. The invalid draft is preserved.'
        request = draft['request']
        if (not isinstance(request, dict) or set(request) != {'purpose', 'operation', 'inputs', 'budget'} or
            not isinstance(request['inputs'], dict) or not isinstance(request['budget'], dict) or
            set(request['budget']) != {'evaluations'} or not isinstance(request['purpose'], str)):
            return 'The request structure cannot fit this editor. It is retained in Diagnostics and can be saved or undone.'
        return None

    def _show_document(self, document, prefer_job=None):
        receiver = getattr(self, '_result_return', None)
        if (receiver and receiver.target and receiver.target[0] == document['id']
                and receiver.target[1] != document['session_id']):
            receiver.bind(document)
        self.document = deepcopy(document)
        self._request_buffer = deepcopy(document['draft'])
        self._view_error = self._shape_error(self._request_buffer)
        self._populating = True
        if not self._view_error:
            request = self._request_buffer['request']
            self.purpose.setText(request['purpose'])
            self.operation.setCurrentIndex(self.operation.findData(request['operation']))
            self.backend.setText(value_text(request['inputs'].get('backend', '')))
            self.evaluations.setText(value_text(request['budget']['evaluations']))
            self._operation_initial = self.operation.currentData()
            self._shown_operation = self.operation.currentData()
            self._operation_inputs = {**deepcopy(document['draft'].get('method_inputs', {})),
                                      self._shown_operation: deepcopy(request['inputs'])}
            self._populate_inputs(request['inputs'])
            self._operation_controls()
        else:
            self.inputs.clear()
        source = document['draft'].get('source') if isinstance(document['draft'], dict) else None
        self.source.setPlainText(json.dumps(source, ensure_ascii=False, indent=2) if source else '연결된 원본 문서가 없습니다.')
        self.source_context.setText('전문가 제안에서 만든 계획' if isinstance(source, dict) and source.get('discussion_id')
                                    else '연결된 원본 문서' if source else '')
        self.source_context.setVisible(bool(source))
        self.source_button.setVisible(bool(source))
        self._populating = False
        self._populate_runs(prefer_job)
        self._draw_result()
        self._update_actions()

    def _populate_inputs(self, value):
        prior = self._populating
        self._populating = True
        self.inputs.clear()
        def append(parent, key, item_value, path):
            kind = value_kind(item_value)
            item = QTreeWidgetItem([str(key), f'{len(item_value)} entries' if kind in {'object', 'list'} else value_text(item_value), kind])
            item.setData(0, DATA, {'path': path, 'kind': kind, 'original': deepcopy(item_value)})
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
            parent.addChild(item) if parent is not None else self.inputs.addTopLevelItem(item)
            if kind in {'object', 'list'}:
                entries = item_value.items() if kind == 'object' else enumerate(item_value)
                for child_key, child in entries:
                    append(item, child_key, child, path + (child_key,))
            return item
        append(None, 'inputs', value, ())
        self.inputs.expandToDepth(2)
        self._populating = prior
        if hasattr(self, 'pinned_sources'):
            self._refresh_input_summary()
        if hasattr(self, 'variable_sheet'):
            self._refresh_worksheet()

    def _backend_edited(self, text):
        if self._populating or self._view_error or not self.inputs.topLevelItem(0):
            return
        inputs = self._input_value(self.inputs.topLevelItem(0))
        if self.operation.currentData() not in MODEL_OPERATIONS:
            return
        self._worksheet_labels.clear()
        self._worksheet_responses.clear()
        if text:
            inputs['backend'] = text
        else:
            inputs.pop('backend', None)
        self._populate_inputs(inputs)
        self._edited()
        self._refresh_input_summary()

    def _input_edited(self, item, column):
        if self._populating:
            return
        metadata = item.data(0, DATA)
        if column == 1 and metadata and metadata['path'] == ('backend',):
            self.backend.setText(item.text(1))
        self._edited()
        self._refresh_input_summary()
        self._refresh_worksheet()

    def _operation_controls(self):
        operation = self.operation.currentData()
        self.retained_role.clear()
        self.retained_role.addItems(RETAINED_ROLES.get(operation, ()))
        active = operation in RETAINED_ROLES
        self.retained_role.setVisible(active)
        self.pin_button.setVisible(active)
        self.pinned_sources.setVisible(active)
        self.response_button.setVisible(operation in {'analyze', 'surrogate', 'sensitivity'})
        self.declarations.setVisible(operation in {'analyze', 'surrogate', 'sensitivity'})
        self.backend.setEnabled(operation in MODEL_OPERATIONS)
        self.model_response_button.setVisible(operation in {'fit', 'doe', 'uq', 'optimize', 'epsilon'})
        self.observation_button.setVisible(operation == 'fit')
        self.constraint_button.setVisible(operation == 'optimize')
        self.sheet.setEnabled(operation in {'fit', 'doe', 'optimize'})
        self.input_tabs.setCurrentWidget(self.sheet if operation in {'fit', 'doe', 'optimize'} else self.advanced_scroll)
        self.tabs.setTabVisible(self.tabs.indexOf(self.observation_panel), operation == 'fit')
        self.operation_note.setText({
            'analyze': 'Select the exact saved candidate table and declare each physical response/reduction. Failed rows remain exclusions.',
            'surrogate': 'Select separate retained training and holdout runs. Add physical response/reduction and typed points. Predictions remain PREDICTED; they cannot be adopted as evaluated coefficients.',
            'sensitivity': 'Select the matched retained Sobol sampling plan and actual response table. Ordinary DOE samples cannot substitute for its exact identities/order. Execution requires SALib on the service.',
            'sample_sensitivity': 'Declare variables, count (Sobol base count), seed and second_order. The downstream evaluation budget must cover count × (dimensions + 2), or count × (2 × dimensions + 2) for second order. Sampling requires SALib; it performs no model evaluation.',
            'doe': 'Edit the registered backend/settings and explicit variable declarations, or select retained candidate coordinates to evaluate them in their original order/IDs. Selecting a saved sampling plan never draws replacement points.',
            'batch_export': 'Select actual retained candidate coordinates and declare case_id. Export writes a file-exchange manifest; it performs no solver evaluation.',
            'batch_import': 'Select the retained batch manifest and exact actual imported result rows. Missing rows remain NOT_EVALUATED. Results may instead be entered as a typed results list.',
            'epsilon': 'Declare objectives, primary_index and physical threshold_grid explicitly. All child searches share the visible total evaluation budget.'
        }.get(operation, ''))
        self.operation_note.setVisible(bool(self.operation_note.text()))

    def _operation_changed(self, *_):
        if self._populating or not self.document or self._view_error:
            return
        self._commit_editor()
        if self._shown_operation is not None and self.inputs.topLevelItem(0):
            self._operation_inputs[self._shown_operation] = self._input_value(self.inputs.topLevelItem(0))
        previous = self._operation_inputs.get(self._shown_operation, {})
        operation = self.operation.currentData()
        templates = {'analyze': {'result_refs': {}, 'responses': []},
                     'sample_sensitivity': {'variables': [], 'count': 2, 'seed': 0, 'second_order': False},
                     'surrogate': {'result_refs': {}, 'response': {}, 'points': [], 'options': {}},
                     'sensitivity': {'result_refs': {}, 'response': {}},
                     'batch_export': {'result_refs': {}, 'case_id': ''},
                     'batch_import': {'result_refs': {}}}
        self._shown_operation = operation
        if operation not in self._operation_inputs:
            value = deepcopy(templates.get(operation, {}))
            if operation in MODEL_OPERATIONS:
                if 'backend' not in previous:
                    previous = next((entry for name, entry in reversed(list(self._operation_inputs.items()))
                                     if name in MODEL_OPERATIONS and 'backend' in entry), previous)
                # The source model remains the same when choosing a research
                # method. Each method still keeps its own later edits.
                for key in ('backend', 'variables'):
                    if key in previous and (key != 'variables' or operation != 'evaluate'):
                        value[key] = deepcopy(previous[key])
                settings = self._model_settings(previous)
                if settings is not None:
                    if operation == 'fit':
                        value['experiments'] = [{'id': 'trial_1', 'role': 'fit', 'settings': settings,
                                                 'response': '', 'weight': 1., 'scale': 1.}]
                    else:
                        value['settings'] = settings
            self._operation_inputs[operation] = value
        value = deepcopy(self._operation_inputs[operation])
        self._populate_inputs(value)
        self.backend.setText(value_text(value.get('backend', '')))
        self._operation_controls()
        self._edited()

    def _refresh_input_summary(self):
        item = self.inputs.topLevelItem(0)
        inputs = self._input_value(item) if item is not None else {}
        refs = inputs.get('result_refs', {})
        refs = refs if isinstance(refs, dict) else {}
        self.pinned_sources.setRowCount(len(refs))
        for row, (role, reference) in enumerate(refs.items()):
            reference = reference if isinstance(reference, dict) else {}
            values = (role, str(reference.get('document_id', '?')) + ' / ' + str(reference.get('job_id', '?')),
                      reference.get('input_revision'), reference.get('result_sha256'))
            for column, value in enumerate(values):
                self._set_cell(self.pinned_sources, row, column, value, False)
            metadata = self._source_metadata.get(canonical_hash(reference), {})
            self.pinned_sources.item(row, 1).setText(str(metadata.get('title') or '보존 결과 ' + str(row + 1)))
        declarations = inputs.get('responses', [inputs['response']] if 'response' in inputs else [])
        declarations = declarations if isinstance(declarations, list) else []
        self.declarations.setRowCount(len(declarations))
        for row, definition in enumerate(declarations):
            definition = definition if isinstance(definition, dict) else {'response': definition}
            values = (definition.get('response'), definition.get('unit'), definition.get('reduction'),
                      str(definition.get('component', 'undeclared')) + ' / ' + str(definition.get('location', 'undeclared')))
            for column, value in enumerate(values):
                self._set_cell(self.declarations, row, column, value, False)

    def choose_retained_result(self):
        operation, role = self.operation.currentData(), self.retained_role.currentText()
        if operation not in RETAINED_ROLES or role not in RETAINED_ROLES[operation]:
            return
        self._commit_editor()
        identity = self.document['id']
        initial = canonical_hash(self.edited_draft()['request']['inputs'])
        def relevant():
            return (self.document and self.document['id'] == identity and self.operation.currentData() == operation
                    and canonical_hash(self.edited_draft()['request']['inputs']) == initial)
        def listed(payload):
            documents = [row for row in payload['documents'] if row.get('kind') in {'data', 'material', 'numerical', 'pde', 'simulation', 'evaluation'}]
            labels = [row['title'] + ' · ' + row['id'] for row in documents]
            if not labels:
                self.message.setText('No retained research documents are available.')
                return
            selected, accepted = QInputDialog.getItem(self, 'Select retained ' + role, 'Original document', labels, editable=False)
            if accepted and relevant():
                self._call(lambda: self.client.document_read(documents[labels.index(selected)]['id']), read, relevant=relevant)
        def read(document):
            runs = [row for row in document.get('runs', []) if row.get('retention_complete') and row.get('retained_result')]
            labels = [row['job_id'] + ' · ' + row['input_revision'] for row in runs]
            if not labels:
                self.message.setText('Save and retain the exact source run before selecting it for this Plan.')
                return
            selected, accepted = QInputDialog.getItem(self, 'Select exact original run', 'Retained job / submitted input', labels, editable=False)
            if not accepted or not relevant():
                return
            job = runs[labels.index(selected)]['job_id']
            def lookup():
                return (self.client.document_result_reference(document['id'], job),
                        self.client.document_result_metadata(document['id'], job))
            self._call(lookup, pin, relevant=relevant)
        def pin(payload):
            reference, metadata = payload
            from caelab.research_operations import validate_result_reference
            validate_result_reference(reference)
            if role == 'plan' and metadata.get('sampling', {}).get('method') != 'SALib.sobol':
                self.message.setText('Select the actual matched SALib Sobol sampling plan; ordinary DOE is incompatible.')
                return
            if role == 'batch' and metadata.get('manifest_kind') != 'file_batch':
                self.message.setText('Select an actual retained file_batch export manifest.')
                return
            if role in {'table', 'training', 'holdout', 'candidates', 'results'} and not metadata.get('candidate_count'):
                self.message.setText('This role requires an actual retained candidate table.')
                return
            if role in {'table', 'training', 'holdout', 'candidates', 'results'} and set(metadata.get('execution_counts', {})) == {'PREDICTED'}:
                self.message.setText('Predicted rows cannot substitute for actual retained candidate evaluations.')
                return
            inputs = self.edited_draft()['request']['inputs']
            refs = inputs.get('result_refs', {})
            if not isinstance(refs, dict):
                self.message.setText('result_refs must remain a typed object. Its existing content was preserved.')
                return
            if operation == 'surrogate':
                other = refs.get('holdout' if role == 'training' else 'training', {})
                if (other.get('document_id'), other.get('job_id')) == (reference['document_id'], reference['job_id']) or other.get('result_sha256') == reference['result_sha256']:
                    self.message.setText('Training and holdout require distinct retained runs and results.')
                    return
            def edit(value):
                for key in ('job_id', 'training_job', 'holdout_job', 'batch_job', 'table', 'manifest'):
                    value.pop(key, None)
                if role in {'plan', 'results', 'candidates'}:
                    value.pop(role, None)
                if operation == 'doe':
                    value.pop('count', None)
                value.setdefault('result_refs', {})[role] = reference
            self._source_metadata[canonical_hash(reference)] = metadata
            self._edit_structure(edit)
            self.message.setText('Pinned ' + role + ' to ' + reference['job_id'] + '. Its exact submitted input and result hash are verified again at execution.')
            if metadata.get('diagnostics'):
                self.operation_note.setText(self.operation_note.text() + '\nRecorded source diagnostics: ' + '; '.join(metadata['diagnostics']))
        self._call(self.client.documents, listed, relevant=relevant)

    def choose_response_definition(self):
        operation = self.operation.currentData()
        if operation not in {'analyze', 'surrogate', 'sensitivity'}:
            return
        inputs = self.edited_draft()['request']['inputs']
        role = 'training' if operation == 'surrogate' else 'table'
        reference = inputs.get('result_refs', {}).get(role) if isinstance(inputs.get('result_refs', {}), dict) else None
        if not isinstance(reference, dict):
            self.message.setText('Select the exact retained ' + role + ' before declaring its physical responses.')
            return
        initial = canonical_hash(inputs)
        def relevant():
            return self.operation.currentData() == operation and canonical_hash(self.edited_draft()['request']['inputs']) == initial
        def select(metadata):
            definitions = [row for row in metadata.get('responses', []) if isinstance(row, dict) and row.get('unit') and row.get('reductions')]
            labels = [str(index) + ': ' + str(row['response']) + ' [' + str(row['unit']) + '] · '
                      + str(row.get('component', 'undeclared')) + ' / ' + str(row.get('location', 'undeclared'))
                      + ' · frame ' + str(row.get('frame', 'undeclared')) + ' · measure ' + str(row.get('measure', 'undeclared'))
                      for index, row in enumerate(definitions)]
            if not labels:
                self.message.setText('No compatible physical response metadata is retained for this source.')
                return
            chosen, accepted = QInputDialog.getItem(self, 'Declare actual physical response', 'Original response / unit / identity', labels, editable=False)
            if not accepted or not relevant():
                return
            definition = definitions[labels.index(chosen)]
            reduction, accepted = QInputDialog.getItem(self, 'Explicit response reduction', 'Available scalar statistic', definition['reductions'], editable=False)
            if not accepted or not relevant():
                return
            declaration = {key: deepcopy(definition[key]) for key in ('response', 'unit', 'component', 'location', 'measure', 'frame', 'coordinate_system', 'coordinate_frame') if key in definition}
            declaration['reduction'] = reduction
            def edit(value):
                if operation == 'analyze':
                    if not isinstance(value.get('responses', []), list):
                        self.message.setText('Responses must be a typed list. Existing declarations were preserved.')
                        return
                    value.setdefault('responses', []).append(declaration)
                else:
                    value['response'] = declaration
            self._source_metadata[canonical_hash(reference)] = metadata
            self._edit_structure(edit)
        cached = self._source_metadata.get(canonical_hash(reference))
        if cached is not None:
            select(cached)
        else:
            self._call(lambda: self.client.document_result_metadata(reference['document_id'], reference['job_id']), select, relevant=relevant)

    def _input_value(self, item):
        metadata = item.data(0, DATA)
        if metadata['kind'] == 'object':
            return {child.data(0, DATA)['path'][-1]: self._input_value(child) for child in (item.child(index) for index in range(item.childCount()))}
        if metadata['kind'] == 'list':
            return [self._input_value(item.child(index)) for index in range(item.childCount())]
        return leaf_value(item.text(1), metadata['original'])

    def _request_context(self):
        if not self.document or self._view_error:
            return None
        return (self.document['id'], self.document['session_id'], canonical_hash(self.edited_draft()))

    @staticmethod
    def _model_settings(inputs):
        if isinstance(inputs.get('settings'), dict):
            return deepcopy(inputs['settings'])
        experiments = inputs.get('experiments', [])
        if isinstance(experiments, list) and experiments and isinstance(experiments[0], dict):
            if isinstance(experiments[0].get('settings'), dict):
                return deepcopy(experiments[0]['settings'])
        return None

    def _pick_retained_curve(self, accepted, *, model=False):
        """Choose real retained bytes; nested dialogs cannot launch timer reads."""
        if not self.document or self._view_error or self._callbacks or self._pending_adoption or self._busy and not self._busy_background:
            return False
        context = self._request_context()
        relevant = lambda: self._request_context() == context and not self.conflict
        source = deepcopy(self.edited_draft().get('source') or {})
        source_id = source.get('document_id') or source.get('pde_document_id')
        backend = self.edited_draft()['request']['inputs'].get('backend')

        def document_read(document):
            runs = [row for row in document.get('runs', []) if row.get('retention_complete') and row.get('retained_result')]
            if model:
                runs = [row for row in runs if row.get('backend', row.get('draft', {}).get('backend')) == backend
                        or document.get('kind') == 'evaluation' and backend == 'evaluation.definition']
            if not runs:
                self.message.setText('Select a saved successful source run. Unsupported or missing runtimes still allow editing/saving the Plan.')
                return
            labels = [row['job_id'] + ' · ' + row['input_revision'] for row in runs]
            value, ok = QInputDialog.getItem(self, 'Actual retained run', 'Job / frozen input', labels, editable=False)
            if not ok or not relevant(): return
            job = runs[labels.index(value)]['job_id']
            def describe():
                return (self.client.document_result_reference(document['id'], job),
                        self.client.document_result_metadata(document['id'], job))
            def described(payload):
                from .response_selection import response_choices, choose_location
                reference, metadata = payload
                choices = response_choices(metadata)
                if not choices:
                    self.message.setText('No admitted scalar/history response is retained for this exact run. No field or node is inferred.')
                    return
                labels = [str(i + 1) + ': ' + item['label'] for i, item in enumerate(choices)]
                label, ok = QInputDialog.getItem(self, 'Select actual response', 'Component / exact native location', labels, editable=False)
                if not ok or not relevant(): return
                choice = choose_location(self, self.client, document['id'], job, choices[labels.index(label)], relevant=relevant)
                if choice is None or not relevant(): return
                selector = choice['selector']
                def checked(result):
                    if result.get('execution_status') != 'SUCCEEDED' or result.get('prediction_status'):
                        self.message.setText('A failed, unevaluated or surrogate-predicted response cannot be used as an actual observation.')
                        return
                    response = result.get('responses', {}).get(selector)
                    if not isinstance(response, dict) or response.get('kind') not in {'scalar', 'series'}:
                        self.message.setText('Select a scalar or one-component history, not an unselected field.')
                        return
                    accepted(reference, selector, response, relevant)
                self._call(lambda: self.client.document_result(document['id'], job,
                    selection={'responses': [selector], 'rows': [0, 1]}), checked, relevant=relevant)
            self._call(describe, described, relevant=relevant)

        def listed(payload):
            documents = [row for row in payload['documents'] if row.get('kind') in {'data', 'material', 'pde', 'simulation', 'evaluation'}]
            labels = [row['title'] + ' · ' + row['id'] for row in documents]
            if not labels:
                self.message.setText('No retained source document is available. Import/evaluate and save its result first.')
                return
            label, ok = QInputDialog.getItem(self, 'Select source document', 'Exact saved source', labels, editable=False)
            if ok and relevant():
                self._call(lambda: self.client.document_read(documents[labels.index(label)]['id']), document_read, relevant=relevant)
        def begin():
            if not relevant(): return
            if model and source_id and (source.get('kind') in {'material', 'simulation', 'pde', 'evaluation'} or source.get('pde_document_id')):
                self._call(lambda: self.client.document_read(source_id), document_read, relevant=relevant)
            else:
                self._call(self.client.documents, listed, relevant=relevant)
        if self._busy_background:
            self._pending_adoption = begin
            self._update_actions()
        else:
            begin()
        return True

    def choose_model_response(self, *, constraint=False):
        operation = self.operation.currentData()
        if operation not in {'doe', 'uq', 'fit', 'optimize', 'epsilon'}: return
        def selected(reference, selector, response, relevant):
            self._worksheet_responses[selector] = deepcopy(response)
            declaration = {key: deepcopy(response[key]) for key in
                ('unit', 'component', 'location', 'measure', 'frame', 'coordinate_system', 'coordinate_frame') if key in response}
            declaration['response'] = selector
            if operation in {'optimize', 'epsilon'}:
                reductions = [response.get('reduction', 'none')] if response['kind'] == 'scalar' else ['max', 'min', 'mean', 'final', 'abs_max']
                reduction, ok = QInputDialog.getItem(self, 'Response reduction', 'Scalar statistic', reductions, editable=False)
                if not ok or not relevant(): return
                declaration['reduction'] = reduction
                if constraint and operation == 'optimize':
                    relation, ok = QInputDialog.getItem(self, 'Constraint', 'Relation', ['<=', '>='], editable=False)
                    if not ok or not relevant(): return
                    limit, ok = QInputDialog.getText(self, 'Constraint', 'Limit [' + str(response.get('unit', 'undeclared')) + ']')
                    if not ok or not relevant(): return
                    declaration.update(operator=relation, limit=numeric_text(limit))
                else:
                    direction, ok = QInputDialog.getItem(self, 'Objective direction', 'Research objective', ['minimize', 'maximize'], editable=False)
                    if not ok or not relevant(): return
                    declaration['direction'] = direction
                declaration['id'] = 'metric_' + canonical_hash({'response': selector, 'reduction': reduction})[:12]
                if operation == 'optimize':
                    if constraint:
                        self._edit_structure(lambda value: value.setdefault('constraints', []).append(declaration))
                    else:
                        self._edit_structure(lambda value: value.__setitem__('objective', declaration))
                else:
                    if not isinstance(self.edited_draft()['request']['inputs'].get('objectives', []), list):
                        self.message.setText('Objectives must be an editable list; the invalid draft is unchanged.')
                        return
                    self._edit_structure(lambda value: value.setdefault('objectives', []).append(declaration))
            elif operation == 'fit':
                experiments = self.edited_draft()['request']['inputs'].get('experiments', [])
                if not isinstance(experiments, list) or any(not isinstance(row, dict) for row in experiments):
                    self.message.setText('Experiments must be a list of protocol records; the invalid draft is unchanged.')
                    return
                labels = [str(i + 1) + ': ' + str(row.get('id')) for i, row in enumerate(experiments)]
                if not labels:
                    self.message.setText('Add an explicit experiment/protocol before selecting its model response.')
                    return
                label, ok = QInputDialog.getItem(self, 'Fit / holdout protocol', 'Use this model response in', labels, editable=False)
                if not ok or not relevant(): return
                index = labels.index(label)
                self._edit_structure(lambda value: value['experiments'][index].__setitem__('response', selector))
            else:
                if not isinstance(self.edited_draft()['request']['inputs'].get('responses', []), list):
                    self.message.setText('Responses must be a list of exact native selectors; the invalid draft is unchanged.')
                    return
                def edit(value):
                    values = value.setdefault('responses', [])
                    if selector not in values: values.append(selector)
                self._edit_structure(edit)
            self.message.setText('Selected ' + selector + ' from ' + reference['job_id'] +
                '. Review the explicit protocol, objective or observation; no evaluation was submitted.')
        return self._pick_retained_curve(selected, model=True)

    def choose_fit_observation(self):
        if self.operation.currentData() != 'fit': return
        def selected(reference, selector, response, relevant):
            experiments = self.edited_draft()['request']['inputs'].get('experiments', [])
            if not isinstance(experiments, list) or not experiments or any(not isinstance(row, dict) for row in experiments):
                self.message.setText('Add an explicit model protocol before attaching observations.')
                return
            labels = [str(i + 1) + ': ' + str(row.get('id')) + ' · ' + str(row.get('role', 'fit')) for i, row in enumerate(experiments)]
            labels += ['New fit trial from first protocol', 'New holdout trial from first protocol']
            label, ok = QInputDialog.getItem(self, 'Attach actual observation', 'Trial and declared role', labels, editable=False)
            if not ok or not relevant(): return
            index = labels.index(label)
            def edit(value):
                rows = value['experiments']
                if index >= len(experiments):
                    trial = deepcopy(rows[0])
                    trial.update(id='trial_' + uuid.uuid4().hex[:12], role='fit' if index == len(experiments) else 'holdout')
                    trial.pop('mask', None)  # New observations require their own fixed mask.
                    rows.append(trial)
                else:
                    trial = rows[index]
                    trial.pop('mask', None)
                for key in ('observations', 'observation_job', 'observation_response'):
                    trial.pop(key, None)
                trial['observation_ref'] = {'result': deepcopy(reference), 'response': selector}
            self._edit_structure(edit)
            self.message.setText('Pinned actual ' + selector + ' from ' + reference['job_id'] +
                '. Review protocol, fit/holdout role, weight, scale and mask. No coefficient was changed or inferred.')
        return self._pick_retained_curve(selected)

    def _select_model_variables(self, descriptors):
        dialog = QDialog(self)
        dialog.setWindowTitle('Select explicitly declared model variables')
        dialog.resize(880, 440)
        layout = QVBoxLayout(dialog)
        note = QLabel('Select the variables to use. Values, units and bounds come from the registered model declaration. '
                      'Edit the selected bounds in the worksheet; no calculation is executed.')
        note.setWordWrap(True)
        layout.addWidget(note)
        table = readonly_table(['Variable ID', 'Label', 'Unit', 'Current value', 'Lower bound', 'Upper bound'])
        table.setObjectName('declaredModelVariables')
        table.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)
        table.setRowCount(len(descriptors))
        for row, descriptor in enumerate(descriptors):
            for column, key in enumerate(('id', 'label', 'unit', 'value', 'lower', 'upper')):
                self._set_cell(table, row, column, descriptor.get(key), False)
        layout.addWidget(table, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText('Use selected variables')
        buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)
        table.itemSelectionChanged.connect(lambda: buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(bool(table.selectionModel().selectedRows())))
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        return [deepcopy(descriptors[index.row()]) for index in sorted(table.selectionModel().selectedRows(), key=lambda index: index.row())]

    def choose_model_variables(self):
        if (not self.document or self._view_error or self._callbacks or self._pending_adoption
                or self._busy and not self._busy_background):
            return
        context = self._request_context()
        inputs = self.edited_draft()['request']['inputs']
        settings = self._model_settings(inputs)
        if not isinstance(inputs.get('backend'), str) or settings is None:
            self.message.setText('Select a registered backend and its explicit settings before reading model variables.')
            return
        relevant = lambda: self._request_context() == context and not self.conflict
        def declared(payload):
            descriptors = payload.get('inputs')
            required = {'id', 'label', 'unit', 'value', 'lower', 'upper'}
            if (not isinstance(descriptors, list) or not descriptors or
                    any(not isinstance(row, dict) or not required <= row.keys() for row in descriptors)):
                self.message.setText('This backend has no complete declared variable descriptors. Existing inputs were preserved.')
                return
            selected = self._select_model_variables(descriptors)
            if selected and relevant():
                # Labels and native binding paths describe the advertised input;
                # the numerical request stores only its supported variable keys.
                variables = [{key: deepcopy(row[key]) for key in ('id', 'unit', 'value', 'lower', 'upper')}
                             for row in selected]
                self._worksheet_labels.update({row['id']: row['label'] for row in selected})
                def append_variables(value):
                    current = value.setdefault('variables', [])
                    if not isinstance(current, list) or any(not isinstance(row, dict) for row in current):
                        raise ValueError('Repair the variables list in Model / advanced before adding declarations.')
                    if any(not isinstance(row.get('id'), str) for row in current):
                        raise ValueError('Repair variable IDs before adding declared variables.')
                    ids = {row['id'] for row in current}
                    current.extend(row for row in variables if row['id'] not in ids)
                if self._edit_structure(append_variables):
                    self.message.setText('Variables added. Existing bounds and units were kept.')
        def begin():
            if relevant():
                self._call(lambda: self.client.describe_inputs({'backend': inputs['backend'], 'settings': settings}),
                           declared, relevant=relevant)
        if self._busy_background:
            self._pending_adoption = begin
            self.message.setText('Waiting for the current read, then reading the exact declared model variables.')
            self._update_actions()
            return True
        begin()
        return True

    @staticmethod
    def _pde_target(source):
        if not isinstance(source, dict):
            return None
        target = source.get('pde_document_id') or (source.get('document_id') if source.get('kind') == 'pde' else None)
        return target if isinstance(target, str) and target else None

    @classmethod
    def _candidate_target(cls, source):
        pde = cls._pde_target(source)
        if pde: return 'pde', pde
        if isinstance(source, dict) and source.get('kind') in ('simulation', 'evaluation', 'material'):
            identifier = source.get('document_id')
            if isinstance(identifier, str) and identifier:
                return source['kind'], identifier
        return None, None

    def _candidate_changed(self):
        self._candidate_selection_serial += 1
        self._plot_selected_result()
        self._update_actions()

    def _selected_pde_candidate(self):
        candidate = self._selected_actual_candidate()
        return candidate.get('candidate_id') if candidate and candidate.get('execution_status') == 'SUCCEEDED' else None

    def _selected_actual_candidate(self):
        rows = self.candidates.selectionModel().selectedRows()
        if len(rows) != 1 or not self.document:
            return None
        job = self.selected_job()
        result = self._result_cache.get(job, {})
        key = (self.document['id'], self.document['session_id'], job, canonical_hash(result))
        if key != self._candidate_table_key:
            return None
        candidates = result.get('candidates', [])
        index = rows[0].row()
        if (index >= len(candidates) or candidates[index].get('execution_status') == 'PREDICTED'
                or candidates[index].get('prediction_status') == 'PREDICTED'):
            return None
        return candidates[index] if candidates[index].get('candidate_id') else None

    def open_candidate_results(self):
        candidate = self._selected_actual_candidate()
        if not candidate or not callable(getattr(self.client, 'numerical_evaluation_result', None)): return
        from .candidate_results_window import CandidateResultsWindow
        identity = (self.document['id'], self.document['session_id'], self.selected_job(), candidate['candidate_id'])
        serial = self._candidate_selection_serial
        def relevant():
            selected = self._selected_actual_candidate()
            return (self.document and selected and self._candidate_selection_serial == serial
                and (self.document['id'], self.document['session_id'], self.selected_job(), selected['candidate_id']) == identity)
        run = next((row for row in self.document['runs'] if row['job_id'] == identity[2]), {})
        inputs = run.get('draft', {}).get('request', {}).get('inputs', {})
        variables = self._result_cache.get(identity[2], {}).get('variables', inputs.get('variables', []))
        units = {row['id']: row['unit'] for row in variables if isinstance(row, dict) and 'id' in row and 'unit' in row}
        window = CandidateResultsWindow(self.client, document_id=identity[0], session_id=identity[1],
            job_id=identity[2], candidate_id=identity[3], values=deepcopy(candidate.get('values', {})),
            units=units, relevant=relevant, parent=self)
        self._candidate_result_windows.append(window)
        window.show()

    def _review_pde_changes(self, preview):
        dialog = QDialog(self)
        kind = preview.get('target_kind', 'pde')
        dialog.setWindowTitle('Review candidate changes to original ' + kind.title())
        dialog.resize(930, 520)
        layout = QVBoxLayout(dialog)
        action = ('Create changed stage branches and adopt their references into the original EvaluationDefinition. Existing stage source documents remain intact.'
                  if kind == 'evaluation' else 'Adoption changes the original ' + kind.title() + ' input draft.')
        label = QLabel('Candidate ' + str(preview['candidate_id']) + ' → ' + str(preview['target_document_id']) +
                       '\n' + action + ' It does not execute a solver or release an engineering design.')
        label.setWordWrap(True)
        layout.addWidget(label)
        table = readonly_table(['Original input path', 'Before', 'Candidate value', 'Declared unit', 'Stage'])
        changes = preview['changes']
        table.setRowCount(len(changes))
        for row, change in enumerate(changes):
            for column, value in enumerate(('/'.join(map(str, change['path'])), change.get('before'), change.get('after'), change.get('unit'), change.get('stage'))):
                self._set_cell(table, row, column, value, False)
        table.resizeColumnsToContents()
        layout.addWidget(table, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText('Create changed stage branches and adopt references'
            if kind == 'evaluation' else 'Adopt reviewed candidate input')
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        return dialog.exec() == QDialog.DialogCode.Accepted

    def review_pde_candidate(self):
        if self._adoption_receipt is not None:
            self.message.setText('An adoption receipt is unconfirmed. Retry that exact receipt before starting another adoption.')
            return False
        candidate = self._selected_pde_candidate()
        if (not candidate or not self.document or self._callbacks or self._pending_adoption
                or self._busy and not self._busy_background or self.conflict or self._view_error
                or self.operation.currentData() not in PDE_CANDIDATE_OPERATIONS):
            return
        context = self._request_context()
        source = deepcopy(self.edited_draft().get('source'))
        target_kind, target_id = self._candidate_target(source)
        if not target_id:
            return
        preview_method = getattr(self.client, 'pde_candidate_preview' if target_kind == 'pde' else 'domain_candidate_preview', None)
        if not callable(preview_method): return
        plan_id, session_id = self.document['id'], self.document['session_id']
        job, serial = self.selected_job(), self._candidate_selection_serial
        result_hash = self._candidate_table_key[-1]
        def relevant():
            return (not self.conflict and self._request_context() == context and self.selected_job() == job
                    and self._candidate_selection_serial == serial and self._selected_pde_candidate() == candidate
                    and self._candidate_table_key[-1] == result_hash)
        def current_target(target, preview):
            frozen = preview['source']
            return (target.get('id') == target_id and target.get('kind') == target_kind
                    and target.get('session_id') == session_id and target.get('input_revision') == frozen.get('input_revision')
                    and canonical_hash(target.get('draft')) == frozen.get('input_sha256'))
        def previewed(preview):
            if (preview.get('target_document_id') != target_id or preview.get('candidate_id') != candidate
                    or preview.get('target_kind', 'pde') != target_kind
                    or canonical_hash(preview.get('source')) != canonical_hash(source)
                    or preview.get('result_sha256') != result_hash or preview.get('executed') is not False
                    or not isinstance(preview.get('changes'), list) or not isinstance(preview.get('draft'), dict)):
                self.message.setText('Candidate preview does not match the exact selected source/result. Adoption was blocked.')
                return
            def target_read(target):
                if not current_target(target, preview):
                    self.message.setText('Original ' + target_kind.title() + ' input/session changed from the frozen Plan source. Adoption was blocked.')
                    return
                if not self._review_pde_changes(preview) or not relevant():
                    return
                def checked(fresh):
                    if not current_target(fresh, preview) or fresh.get('generation') != target.get('generation'):
                        self.message.setText('Original ' + target_kind.title() + ' changed during review. Reread and review before adopting.')
                        return
                    command_id = 'C' + uuid.uuid4().hex
                    request = {'plan_id': plan_id, 'job_id': job, 'candidate_id': candidate,
                               ('pde_document_id' if target_kind == 'pde' else 'target_document_id'): target_id, 'session_id': fresh['session_id'],
                               'expected_generation': fresh['generation'], 'command_id': command_id}
                    if target_kind == 'pde': self._pde_adoption_request = deepcopy(request)
                    def adopted(receipt):
                        from .desktop import launch_tool
                        if relevant():
                            self._call(lambda: launch_tool(self.client, target_kind, document_id=target_id), lambda _: None,
                                       relevant=relevant)
                    self._submit_adoption_receipt('pde' if target_kind == 'pde' else 'domain', request, adopted)
                self._call(lambda: self.client.document_read(target_id), checked, relevant=relevant)
            self._call(lambda: self.client.document_read(target_id), target_read, relevant=relevant)
        def begin():
            if relevant():
                self._call(lambda: preview_method(plan_id, job, candidate), previewed, relevant=relevant)
        if self._busy_background:
            self._pending_adoption = begin
            self.message.setText('Waiting for the current read, then reviewing the exact selected ' + target_kind.title() + ' candidate.')
            self._update_actions()
            return True
        begin()
        return True

    def command(self, operation, arguments=None, *, after=None):
        self._commit_editor()
        if not self.document or self.conflict or self.local_dirty and operation != 'numerical.update':
            self.message.setText('Apply edited study first; commands use the current service generation.')
            return False
        document, submitted = deepcopy(self.document), self.edited_draft()
        context = (document['id'], document['session_id'])
        def accepted(receipt):
            late = self.edited_draft() != submitted
            self.local_dirty = late
            if late:
                self.document = deepcopy(receipt['document'])
                self._populate_runs(receipt.get('job', {}).get('id'))
                self._draw_result()
                self.message.setText('Earlier edits applied. Newer edits remain; Apply them before Save or Run.')
            else:
                self._show_document(receipt['document'], receipt.get('job', {}).get('id'))
                self.message.setText('Study ' + operation + ' acknowledged.')
            if after and not late:
                QTimer.singleShot(0, after)
            elif receipt.get('job'):
                QTimer.singleShot(0, self.refresh_result)
        return self._call(lambda: self.client.document_command(document['id'], operation, deepcopy(arguments or {}),
            session_id=document['session_id'], expected_generation=document['generation'], command_id='C' + uuid.uuid4().hex),
            accepted, relevant=lambda: self.document and (self.document['id'], self.document['session_id']) == context)

    def edited_draft(self):
        self._commit_editor()
        draft = deepcopy(self._request_buffer)
        if self._view_error:
            return draft
        request = draft['request']
        request['purpose'] = self.purpose.text()
        if self.operation.currentData() is not None:
            request['operation'] = self.operation.currentData()
        request['inputs'] = self._input_value(self.inputs.topLevelItem(0))
        alternatives = {key: deepcopy(value) for key, value in self._operation_inputs.items()
                        if key != request['operation']}
        if alternatives or 'method_inputs' in draft:
            draft['method_inputs'] = alternatives
        original_budget = draft['request']['budget']['evaluations']
        request['budget']['evaluations'] = deepcopy(original_budget) if self.evaluations.text() == value_text(original_budget) else leaf_value(self.evaluations.text(), 0)
        return draft

    @staticmethod
    def _at_path(value, path):
        for part in path:
            value = value[part]
        return value

    def _edit_structure(self, callback):
        if self._view_error or not self.document or self._busy and not self._busy_background:
            return
        draft = self.edited_draft()
        try:
            callback(draft['request']['inputs'])
        except (ValueError, TypeError, KeyError, IndexError, AttributeError) as error:
            self.message.setText('Input edit was not applied; the current draft is retained. ' + str(error))
            return False
        self._request_buffer = draft
        self._populate_inputs(draft['request']['inputs'])
        self.backend.setText(value_text(draft['request']['inputs'].get('backend', '')))
        self._edited()
        return True

    def add_input(self):
        selected = self.inputs.currentItem() or self.inputs.topLevelItem(0)
        if not selected:
            return
        metadata = selected.data(0, DATA)
        if metadata['kind'] not in {'object', 'list'}:
            self.message.setText('Select an object or list to add a member; change type explicitly to replace a leaf.')
            return
        kind, accepted = QInputDialog.getItem(self, 'Add input', 'Value type', ['string', 'number', 'boolean', 'null', 'object', 'list'], editable=False)
        if not accepted:
            return
        value = {'string': '', 'number': 0, 'boolean': False, 'null': None, 'object': {}, 'list': []}[kind]
        key = None
        if metadata['kind'] == 'object':
            key, accepted = QInputDialog.getText(self, 'Add object member', 'Field name')
            if not accepted or not key:
                return
        def edit(inputs):
            parent = self._at_path(inputs, metadata['path'])
            if isinstance(parent, dict):
                if key in parent:
                    self.message.setText('This field already exists; its value was preserved.')
                    return
                parent[key] = value
            else:
                parent.append(value)
        self._edit_structure(edit)

    def remove_input(self):
        item = self.inputs.currentItem()
        if not item or not item.data(0, DATA)['path']:
            self.message.setText('The root inputs object is required; remove individual members instead.')
            return
        path = item.data(0, DATA)['path']
        self._edit_structure(lambda inputs: self._at_path(inputs, path[:-1]).__delitem__(path[-1]))

    def change_type(self):
        item = self.inputs.currentItem()
        if not item or not item.data(0, DATA)['path']:
            self.message.setText('The root inputs object keeps its object type.')
            return
        kind, accepted = QInputDialog.getItem(self, 'Change input type', 'Replacement type', ['string', 'number', 'boolean', 'null', 'object', 'list'], editable=False)
        if accepted:
            path = item.data(0, DATA)['path']
            value = {'string': '', 'number': 0, 'boolean': False, 'null': None, 'object': {}, 'list': []}[kind]
            self._edit_structure(lambda inputs: self._at_path(inputs, path[:-1]).__setitem__(path[-1], value))

    def _call(self, function, accepted, *, background=False, relevant=None, rejected=None):
        # The pending-review receiver owns its read workers and nested modal loop.
        # Timers and other window actions must not compete with that interaction.
        if getattr(self, '_incoming_review', False):
            return False
        return super()._call(function, accepted, background=background,
                             relevant=relevant, rejected=rejected)

    def refresh_document(self):
        if not self.document or self._busy or self._callbacks:
            return
        identifier = self.document['id']
        def received(remote):
            editing = self.local_dirty or any(view.state() == QAbstractItemView.State.EditingState
                for view in (self.inputs, self.variable_sheet, self.response_sheet, self.method_sheet))
            changed = remote['session_id'] != self.document['session_id'] or canonical_hash(remote['draft']) != canonical_hash(self.document['draft'])
            if editing and changed:
                self.conflict = True
                self.message.setText('Owner inputs/session changed while editing. Your typed inputs remain; reload or keep them as a new Plan.')
            elif not editing and not self.conflict:
                self._show_document(remote)
            elif editing and not changed:
                self.document = deepcopy(remote)
                self._populate_runs()
                self._draw_result()
            QTimer.singleShot(0, self.refresh_result)
        return self._call(lambda: self.client.document_read(identifier), received, background=True,
                          relevant=lambda: self.document['id'] == identifier)

    def retry_result(self):
        job = self.selected_job()
        if not self.document or not job:
            return
        self._queued_result_retry = (self.document['id'], job)
        self._dispatch_result_retry()

    def _dispatch_result_retry(self):
        pending = self._queued_result_retry
        if pending is None:
            return
        if self._allow_close or not self.document or pending != (self.document['id'], self.selected_job()):
            self._queued_result_retry = None
            return
        if self._busy or self._callbacks:
            QTimer.singleShot(25, self._dispatch_result_retry)
            return
        self._queued_result_retry = None
        super().retry_result()

    def _draw_result(self):
        job = self.selected_job()
        result = self._result_cache.get(job, {})
        rows = result.get('candidates', result.get('predictions', []))
        actual_selected = self._selected_actual_candidate()
        selected = actual_selected.get('candidate_id') if actual_selected else None
        key = (self.document['id'], self.document['session_id'], job, canonical_hash(result)) if self.document else None
        unchanged = key == self._candidate_table_key
        self.candidates.blockSignals(True)
        self.candidates.clearSelection()
        self.candidates.setRowCount(0)
        self.candidates.setRowCount(len(rows))
        self.candidates.setVisible(bool(rows) or not (result.get('responses') or result.get('curves')))
        for row, candidate in enumerate(rows):
            for column, value in enumerate((candidate.get('candidate_id'), candidate_state(candidate), candidate.get('values'), candidate.get('objective'), candidate.get('feasible'), candidate.get('failure_reason'))):
                self._set_cell(self.candidates, row, column, value, False)
            if unchanged and selected and candidate.get('candidate_id') == selected:
                self.candidates.selectRow(row)
        if not unchanged:
            self._candidate_selection_serial += 1
        self._candidate_table_key = key
        self.candidates.blockSignals(False)
        fill_tree(self.responses, result.get('responses', {}))
        previous = self.plot_response.currentData()
        self.plot_response.blockSignals(True)
        self.plot_response.clear()
        self.plot_response.addItem('계산 요약', None)
        for name, response in result.get('responses', {}).items():
            self.plot_response.addItem(name + ' [' + str(response.get('unit', 'undeclared')) + ']', name)
        self._candidate_plot_names = {name for row in rows for name, response in row.get('responses', {}).items()
                                      if isinstance(response, dict) and response.get('kind') in {'scalar', 'series'}}
        self._candidate_plot_names.update(entry['response'] for row in rows for entry in row.get('response_reductions', [])
                                          if isinstance(entry, dict) and isinstance(entry.get('response'), str))
        for name in sorted(self._candidate_plot_names):
            self.plot_response.addItem('Candidates: ' + name, {'candidate_response': name})
        index = self.plot_response.findData(previous)
        if not unchanged and previous is None and not rows and result.get('responses'):
            index = 1  # A direct evaluation opens its actual response, not an empty candidate summary.
        self.plot_response.setCurrentIndex(max(0, index))
        self.plot_response.blockSignals(False)
        self._plot_selected_result()
        self.details.setPlainText(json.dumps({'document_diagnostics': self.document.get('diagnostics') if self.document else [],
            'view_error': self._view_error, 'selected_status': self._statuses.get(job),
            'result_read_error': self._result_errors.get(job), 'submitted_run': next((run for run in self.document.get('runs', []) if run['job_id'] == job), None) if self.document else None,
            'actual_result': result, 'preserved_draft': self.document['draft'] if self.document and self._view_error else None}, ensure_ascii=False, indent=2))
        self._update_actions()

    def _plot_selected_result(self, *_):
        job = self.selected_job()
        result = self._result_cache.get(job, {})
        rows = result.get('candidates', result.get('predictions', []))
        self.figure.clear()
        name = self.plot_response.currentData()
        if isinstance(name, dict) and 'candidate_response' in name:
            self._plot_candidate_response(result, name['candidate_response'])
            self.canvas.draw_idle()
            return
        response = result.get('responses', {}).get(name)
        if isinstance(response, dict):
            ax = self.figure.add_subplot(111)
            values, axes = response.get('value'), response.get('axes', [])
            if response.get('kind') == 'series' and isinstance(values, list) and len(axes) == 1:
                coordinates, mask = axes[0].get('values'), response.get('mask')
                valid = (isinstance(coordinates, list) and len(values) == len(coordinates)
                         and all(type(value) in (int, float) and math.isfinite(value) for value in coordinates + values)
                         and (mask is None or isinstance(mask, list) and len(mask) == len(values) and all(type(value) is bool for value in mask))
                         and response.get('valid') is not False)
                if valid:
                    ax.plot(coordinates, [value if mask is None or mask[index] else math.nan for index, value in enumerate(values)])
                    ax.set_xlabel(str(axes[0].get('name', 'undeclared axis')) + ' [' + str(axes[0].get('unit', 'undeclared')) + ']')
                    ax.set_ylabel(name + ' [' + str(response.get('unit', 'undeclared')) + ']')
                    ax.set_title('Recorded response')
                else:
                    ax.text(.5, .5, 'Invalid retained coordinates, values or mask; inspect Responses.', ha='center', transform=ax.transAxes)
            elif response.get('kind') == 'scalar':
                ax.text(.5, .5, name + ' = ' + value_text(response.get('value')) + ' [' + str(response.get('unit', 'undeclared')) + ']', ha='center', transform=ax.transAxes)
                ax.set_axis_off()
            else:
                ax.text(.5, .5, 'This recorded response is not a one-dimensional curve. Inspect its metadata or open Runner/Post.', ha='center', wrap=True, transform=ax.transAxes)
                ax.set_axis_off()
        elif result.get('curves'):
            curves = result['curves']
            axes = self.figure.subplots(len(curves), 1, squeeze=False)
            for ax, curve in zip(axes[:, 0], curves):
                observation = curve.get('observations', {})
                source_axis = observation.get('axes', [{}])[0]
                coordinates = source_axis.get('values', [])
                observed, predicted = observation.get('value', []), curve.get('prediction', [])
                finite_axis = isinstance(coordinates, list) and all(type(value) in (int, float) and math.isfinite(value) for value in coordinates)
                def recorded_values(values):
                    return (isinstance(values, list) and len(values) == len(coordinates)
                            and all(value is None or type(value) in (int, float) and math.isfinite(value) for value in values))
                if finite_axis and recorded_values(observed):
                    ax.plot(coordinates, [math.nan if value is None else value for value in observed], 'o', label='recorded observation', markersize=3)
                if finite_axis and recorded_values(predicted):
                    ax.plot(coordinates, [math.nan if value is None else value for value in predicted], label='actual evaluated model response')
                ax.set_xlabel(str(source_axis.get('name', 'undeclared axis')) + ' [' + str(source_axis.get('unit', 'undeclared')) + ']')
                ax.set_ylabel(str(observation.get('component', 'response')) + ' [' + str(observation.get('unit', 'undeclared')) + ']')
                ax.set_title(str(curve.get('experiment_id', 'experiment')) + ' · ' + str(curve.get('execution_status', 'unknown')) + ' · RMSE ' + str(curve.get('rmse', 'unknown')), fontsize=9)
                if ax.lines:
                    ax.legend(fontsize=7)
        elif result.get('kind') == 'surrogate':
            ax = self.figure.add_subplot(111)
            points = [(index, next(iter(row.get('responses', {}).values()), {})) for index, row in enumerate(result.get('predictions', [])) if row.get('execution_status') == 'PREDICTED']
            points = [(index, item) for index, item in points if type(item.get('value')) in (int, float) and math.isfinite(item['value'])]
            if points:
                ax.scatter([index for index, _ in points], [item['value'] for _, item in points])
                ax.set_xlabel('Requested prediction point order')
                ax.set_ylabel('PREDICTED response [' + str(points[0][1].get('unit', 'undeclared')) + ']')
                ax.set_title('Surrogate predictions · independent holdout RMSE ' + str(result.get('validation', {}).get('rmse', 'unavailable')))
            else:
                ax.text(.5, .5, 'No retained finite predictions.', ha='center', transform=ax.transAxes)
        elif result.get('method') == 'SALib.sobol':
            ax = self.figure.add_subplot(111)
            values = result.get('indices', {}).get('S1', [])
            names = result.get('sampling', {}).get('problem', {}).get('names', [])
            if len(values) == len(names):
                ax.bar(names, values)
                ax.set_ylabel('Sobol first-order sensitivity index [1]')
                ax.set_title('Actual matched Sobol response analysis · ' + str(job))
        elif result.get('kind') == 'epsilon_optimization':
            run = next((row for row in self.document.get('runs', []) if row['job_id'] == job), {})
            definitions = run.get('draft', {}).get('request', {}).get('inputs', {}).get('objectives', [])
            ax = self.figure.add_subplot(111)
            from caelab.numerical import _scalar, EvaluationFailed
            points = []
            if len(definitions) >= 2:
                for row in result.get('candidates', []):
                    try:
                        points.append((_scalar(row, definitions[0]), _scalar(row, definitions[1])))
                    except (EvaluationFailed, ValueError, TypeError, KeyError):
                        continue
            if points:
                ax.scatter([row[0] for row in points], [row[1] for row in points])
                ax.set_xlabel(str(definitions[0]['response']) + ' [' + str(definitions[0]['unit']) + ']')
                ax.set_ylabel(str(definitions[1]['response']) + ' [' + str(definitions[1]['unit']) + ']')
                ax.set_title('Actual epsilon search candidates; global optimality unproven')
        elif result.get('statistics'):
            items = [item for item in result['statistics'] if type(item.get('mean')) in (int, float) and math.isfinite(item['mean'])]
            if items:
                axes = self.figure.subplots(len(items), 1, squeeze=False)
                for axis, item in zip(axes[:, 0], items):
                    deviation = item.get('std')
                    axis.errorbar([0], [item['mean']], yerr=deviation if type(deviation) in (int, float) and math.isfinite(deviation) else None, fmt='o', capsize=5)
                    axis.set_xticks([0], [str(item.get('metric', 'response'))])
                    axis.set_ylabel('mean ± sample std [' + str(item.get('unit', 'undeclared')) + ']')
                    axis.set_title('Actual retained candidate analysis · ' + str(item.get('count', 0)) + ' usable · ' + str(result.get('failure_count', 0)) + ' failed original rows', fontsize=9)
            else:
                ax = self.figure.add_subplot(111)
                ax.text(.5, .5, 'No usable retained candidate statistics. Inspect original exclusions.', ha='center', transform=ax.transAxes)
        else:
            if result.get('kind') in {'uq', 'optimization', 'epsilon_optimization'}:
                self._draw_study_summary(result, job)
            else:
                ax = self.figure.add_subplot(111)
                ax.text(.5, .5, 'Select a response to plot.' if rows else 'No calculated result selected.',
                        ha='center', va='center', wrap=True, transform=ax.transAxes)
                ax.set_axis_off()
        self.figure.tight_layout()
        self.canvas.draw_idle()

    def _plot_candidate_response(self, result, name):
        ax = self.figure.add_subplot(111)
        selected = self._selected_actual_candidate()
        rows = result.get('candidates', [])
        scalar_points, ids, units = [], [], set()
        for index, row in enumerate(rows):
            if row.get('execution_status') != 'SUCCEEDED' or row.get('prediction_status'):
                continue
            response = row.get('responses', {}).get(name)
            if not isinstance(response, dict) or 'value' not in response:
                reductions = [item for item in row.get('response_reductions', []) if item.get('response') == name]
                # Different reductions are different quantities, not one curve.
                response = reductions[0] if len(reductions) == 1 else None
            if not isinstance(response, dict) or response.get('valid') is False:
                continue
            value = response.get('value')
            if response.get('kind') == 'scalar' and type(value) in (int, float) and math.isfinite(value):
                scalar_points.append((index, value))
                ids.append(row['candidate_id'])
                units.add((response.get('unit'), response.get('reduction', 'none'),
                           response.get('component'), response.get('location'), response.get('frame'),
                           response.get('measure'), response.get('coordinate_system'), response.get('coordinate_frame')))
        if scalar_points and len(units) == 1:
            artist = ax.scatter([point[0] for point in scalar_points], [point[1] for point in scalar_points], picker=5)
            artist._candidate_ids = ids
            if selected and selected['candidate_id'] in ids:
                index = ids.index(selected['candidate_id'])
                ax.scatter(*scalar_points[index], s=95, facecolors='none', edgecolors='#d56c22', linewidths=2)
            unit, reduction, *_ = next(iter(units))
            ax.set_xlabel('Original candidate order')
            ax.set_ylabel(name + ' [' + str(unit) + '] / ' + str(reduction))
        elif scalar_points:
            ax.text(.5, .5, 'Candidate physical definitions differ; inspect each retained response.', ha='center', wrap=True, transform=ax.transAxes)
        elif selected:
            response = selected.get('responses', {}).get(name, {})
            values, axes = response.get('value'), response.get('axes', [])
            if (selected.get('execution_status') == 'SUCCEEDED' and response.get('valid') is not False
                    and response.get('kind') == 'series' and isinstance(values, list) and len(axes) == 1):
                coordinates, mask = axes[0].get('values'), response.get('mask')
                finite = (isinstance(coordinates, list) and len(coordinates) == len(values)
                    and all(type(value) in (int, float) and math.isfinite(value) for value in coordinates + values)
                    and (mask is None or isinstance(mask, list) and len(mask) == len(values) and all(type(value) is bool for value in mask)))
                if finite:
                    ax.plot(coordinates, [value if mask is None or mask[index] else math.nan for index, value in enumerate(values)])
                    ax.set_xlabel(str(axes[0].get('name')) + ' [' + str(axes[0].get('unit')) + ']')
                    ax.set_ylabel(name + ' [' + str(response.get('unit')) + ']')
                else:
                    ax.text(.5, .5, 'No valid retained curve for this candidate.', ha='center', transform=ax.transAxes)
            else:
                ax.text(.5, .5, str(selected.get('failure_reason') or 'Curve not retained. Open candidate results to inspect available evaluations.'),
                        ha='center', wrap=True, transform=ax.transAxes)
        else:
            ax.text(.5, .5, 'Select a candidate to inspect its retained curve.', ha='center', transform=ax.transAxes)
        ax.set_title(str(selected['candidate_id']) if selected else 'Actual candidate responses')

    def _select_return_channels(self, result):
        from PySide6.QtWidgets import QListWidget, QListWidgetItem
        dialog = QDialog(self)
        dialog.setWindowTitle('Return selected run')
        dialog.resize(600, 380)
        layout = QVBoxLayout(dialog)
        label = QLabel('Attach this exact run and the checked top-level responses.\n'
                       'Candidate records remain run evidence; a selected table row does not narrow the attachment.')
        label.setWordWrap(True)
        layout.addWidget(label)
        channels = QListWidget()
        for name in result.get('responses', {}):
            item = QListWidgetItem(name)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            channels.addItem(item)
        layout.addWidget(channels, 1)
        if not channels.count():
            layout.addWidget(QLabel('This run has no top-level channels. Its candidate records and diagnostics can still be reviewed.'))
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText('Present for review')
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        return [channels.item(row).text() for row in range(channels.count())
                if channels.item(row).checkState() == Qt.CheckState.Checked]

    def return_result(self):
        from .result_return import origin_id, result_message, verify_result, receive_local, deliver_result
        job = self.selected_job()
        if not self.document or not job or self._busy or self._callbacks:
            return False
        document_id, session_id = self.document['id'], self.document['session_id']
        run = next((row for row in self.document.get('runs', []) if row['job_id'] == job), None)
        if run is None:
            return False
        # The submitted run's source is immutable; newer Plan edits cannot redirect it.
        target_id = origin_id(run)
        def relevant():
            return (self.document and (self.document['id'], self.document['session_id'], self.selected_job())
                    == (document_id, session_id, job))
        def read():
            return (self.client.document_result_reference(document_id, job),
                    self.client.document_result(document_id, job, selection={'metadata_only': True}))
        def loaded(payload):
            reference, result = payload
            selection = self._select_return_channels(result)
            if selection is None or not relevant():
                return
            def present(target):
                if not relevant():
                    return
                message = result_message(self.client, target['id'], target['session_id'], reference, selection)
                signature = canonical_hash({key: value for key, value in message.items() if key != 'delivery_id'})
                prior = self._return_messages.get(signature)
                if prior and self._return_receipts.get(prior['delivery_id'], {}).get('status') not in {'CANCELLED', 'REJECTED'}:
                    message = prior
                self._return_messages[signature] = deepcopy(message)
                self._last_return_message = deepcopy(message)
                def received(receipt):
                    self._return_receipts[message['delivery_id']] = deepcopy(receipt)
                    self._return_message(receipt)
                def failed(error):
                    self.message.setText('Result return failed; current edits retained. ' + str(error))
                def verified(_payload):
                    # Same-process windows are already known. Receive on the GUI
                    # callback; never block a worker on a pipe back into this view.
                    try:
                        receipt = receive_local(message)
                    except (ValueError, TypeError, KeyError, RuntimeError) as error:
                        failed(error)
                        return
                    if receipt is not None:
                        received(receipt)
                    else:
                        # Only the existing socket route can establish absence
                        # in another process and open the exact closed origin.
                        self._call(lambda: deliver_result(self.client, message), received, rejected=failed)
                self._call(lambda: verify_result(self.client, message), verified,
                           relevant=relevant, rejected=failed)
            if target_id:
                self._call(lambda: self.client.document_read(target_id), present, relevant=relevant)
            else:
                def listed(payload):
                    documents = [row for row in payload['documents'] if row.get('kind') in {'expert', 'study'}]
                    labels = [row['title'] + ' (' + row['kind'] + ') — ' + row['id'] for row in documents]
                    if not labels:
                        self.message.setText('No existing Expert or Study is available. New discussion remains a separate action.')
                        return
                    label, accepted = QInputDialog.getItem(self, 'Attach to existing research', 'Existing document', labels, editable=False)
                    if accepted and relevant():
                        self._call(lambda: self.client.document_read(documents[labels.index(label)]['id']), present, relevant=relevant)
                self._call(self.client.documents, listed, relevant=relevant)
        return self._call(read, loaded, relevant=relevant)

    def _return_message(self, receipt):
        status = receipt.get('status', 'UNCONFIRMED')
        text = {'PRESENTED': 'Presented in the existing research window. Use Review returned result there to Attach or Cancel.',
                'ATTACHED': 'Evidence attached to the original local draft. Apply and Save remain explicit.',
                'ALREADY_ATTACHED': 'The exact run and channels are already in the original draft.',
                'CANCELLED': 'Return cancelled in the original window; its draft was unchanged.',
                'UNKNOWN': 'No retained delivery receipt in that window; inspect it before explicitly resending.'}.get(status)
        self.message.setText(text or 'Result return ' + status + ': ' + str(receipt.get('reason', 'Inspect the original window.')))

    def check_return_status(self):
        if not self._last_return_message or self._busy or self._callbacks:
            return False
        from .result_return import receive_local, send_message
        original = deepcopy(self._last_return_message)
        message = {key: value for key, value in original.items() if key not in {'reference', 'selection'}}
        message['operation'] = 'status'
        def received(receipt):
            self._return_receipts[original['delivery_id']] = deepcopy(receipt)
            self._return_message(receipt)
        try:
            receipt = receive_local(message)
        except (ValueError, TypeError, KeyError, RuntimeError) as error:
            self.message.setText('Result return status unavailable. ' + str(error))
            return False
        if receipt is not None:
            received(receipt)
            return True
        return self._call(lambda: send_message(message), received)

    def consult_expert(self):
        job = self.selected_job()
        if not self.document or not job:
            return
        identifier, session_id = self.document['id'], self.document['session_id']
        command_id = 'C' + uuid.uuid4().hex
        def opened(receipt):
            if receipt.get('executed') is not False:
                raise ValueError('Opening a result follow-up unexpectedly reported execution')
            from .desktop import launch_tool
            self._call(lambda: launch_tool(self.client, 'expert', document_id=receipt['document']['id']),
                       lambda _: self.message.setText('Opened Expert from the exact retained result. Review the context, then explicitly Ask.'))
        def create(reference):
            self._call(lambda: self.client.result_followup(reference, 'expert', session_id=session_id, command_id=command_id), opened)
        self._call(lambda: self.client.document_result_reference(identifier, job), create)

    def _update_actions(self):
        present = self.document is not None
        available = not (self._busy or self._callbacks or self._pending_adoption or getattr(self, '_incoming_review', False))
        enabled = present and available and not self.conflict
        # Background reads may finish while a cell editor is open. They preserve
        # local edits and never disable the editor or force its value to commit.
        self.editor.setEnabled(present and not self._view_error and not (self._busy and not self._busy_background))
        self.apply_button.setEnabled(enabled and self.local_dirty and not self._view_error)
        self.run_button.setEnabled(enabled and not self.local_dirty and not self._view_error and not self.document.get('diagnostics'))
        self.save_action.setEnabled(enabled)
        self.undo_action.setEnabled(enabled and not self.local_dirty and self.document.get('can_undo', False))
        self.redo_action.setEnabled(enabled and not self.local_dirty and self.document.get('can_redo', False))
        self.new_action.setEnabled(available)
        self.open_action.setEnabled(available)
        self.read_button.setEnabled(enabled and self.selected_job() is not None)
        self.runner_button.setEnabled(present and available and self.selected_job() is not None)
        self.expert_button.setEnabled(present and available and self.selected_job() is not None)
        self.return_button.setEnabled(present and available and self.selected_job() is not None)
        self.return_status_action.setEnabled(available and self._last_return_message is not None)
        read_available = present and not getattr(self, '_incoming_review', False) and not self.conflict and not self._callbacks and not self._pending_adoption and (not self._busy or self._busy_background)
        candidate_task = self.operation.currentData() in PDE_CANDIDATE_OPERATIONS or bool(
            self._result_cache.get(self.selected_job(), {}).get('candidates'))
        result = self._result_cache.get(self.selected_job(), {})
        self.candidates.setVisible(candidate_task and not (result.get('responses') or result.get('curves'))
                                   or bool(result.get('candidates', result.get('predictions', []))))
        self.candidate_results_button.setVisible(candidate_task)
        self.pde_adopt_button.setVisible(candidate_task)
        self.candidate_results_button.setEnabled(read_available and bool(self._selected_actual_candidate())
            and callable(getattr(self.client, 'numerical_evaluation_result', None)))
        self.variables_button.setEnabled(read_available and not self._view_error and self.operation.currentData() in MODEL_OPERATIONS
                                         and callable(getattr(self.client, 'describe_inputs', None)))
        for button in (self.model_response_button, self.observation_button):
            button.setEnabled(read_available and not self._view_error and callable(getattr(self.client, 'document_result_metadata', None)))
        source = self.document['draft'].get('source') if present and isinstance(self.document['draft'], dict) else None
        target_kind, target_id = self._candidate_target(source)
        self.pde_adopt_button.setText('선택 후보를 PDE에 채택…' if target_kind == 'pde' else '선택 후보를 원본에 채택…')
        self.pde_adopt_button.setEnabled(read_available and not self._view_error and bool(target_id)
                                        and self._adoption_receipt is None
                                        and self.operation.currentData() in PDE_CANDIDATE_OPERATIONS
                                        and bool(self._selected_pde_candidate())
                                        and callable(getattr(self.client, 'pde_candidate_preview' if target_kind == 'pde' else 'domain_candidate_preview', None))
                                        and callable(getattr(self.client, 'pde_adopt' if target_kind == 'pde' else 'domain_candidate_adopt', None)))
        self._update_adoption_receipt_actions()
        self.observed_read.setEnabled(enabled and self.operation.currentData() == 'fit' and self.observed_trial.count() > 0)
        self.observed_post.setEnabled(enabled and self._observation_matches() and bool(self._post_observation.get('source_available')))
        source_id = source.get('discussion_id',source.get('pde_document_id',source.get('document_id'))) if isinstance(source,dict) else None
        self.source_button.setEnabled(present and available and isinstance(source_id,str) and source_id.startswith(('X','S','Q','T','M','N','V','E')))
        self.reload_button.setVisible(self.conflict)
        self.copy_button.setVisible(self.conflict)
        self.reload_button.setEnabled(available)
        self.copy_button.setEnabled(available)
        if present:
            self.setWindowTitle('계산 계획 — ' + self.document['title'] + (' *' if self.local_dirty or self.document.get('dirty') else ''))
            self.identity.setText('변경 적용 전' if self.local_dirty else ('저장됨' if not self.document.get('dirty') else '저장 전'))
            self.identity.setToolTip(self.document['id'] + ' / generation ' + str(self.document['generation']))

    def open_runner(self):
        job = self.selected_job()
        if job:
            runner = RunnerWindow(self.client, job_id=job)
            self._runner_windows.append(runner)
            runner.show()

    def _selected_observation(self):
        if not self.document or self._view_error or not self.inputs.topLevelItem(0):
            return None
        index = self.observed_trial.currentData()
        if type(index) is not int:
            return None
        trials = self._input_value(self.inputs.topLevelItem(0)).get('experiments', [])
        if not isinstance(trials, list) or not 0 <= index < len(trials):
            return None
        trial = trials[index]
        observation = trial.get('observation_ref') if isinstance(trial, dict) else None
        return deepcopy(observation) if isinstance(observation, dict) else None

    def _observation_matches(self):
        selected = self._selected_observation()
        return bool(self._post_observation and selected and
                    self._observation_key == canonical_hash(selected))

    def _observation_trial_changed(self, *_):
        if hasattr(self, 'observed_table'):
            self._post_observation = None
            self._observation_key = None
            self.observed_table.setRowCount(0)
            self.observed_figure.clear()
            self.observed_canvas.draw_idle()
            self.observed_info.setText('Read this trial’s exact retained observation.')
            self._update_actions()

    def load_observation(self):
        selected = self._selected_observation()
        if self._allow_close or not selected or not callable(getattr(self.client, 'post_observation', None)):
            return False
        key = canonical_hash(selected)
        owner = (self.document['id'], self.document['session_id'])
        if self._busy or self._callbacks or self._pending_adoption or getattr(self, '_incoming_review', False):
            # Attaching a Post measurement can finish while an ordinary refresh
            # is in flight. Retain this read without replacing an adoption action.
            self._queued_observation_read = (*owner, key)
            self._observation_read_timer.start(25)
            return True
        self._queued_observation_read = None
        self._observation_read_timer.stop()
        def relevant():
            current = self._selected_observation()
            return (self.document is not None and (self.document['id'], self.document['session_id']) == owner
                    and current is not None and canonical_hash(current) == key)
        def received(payload):
            if selected.get('response') != 'measured' or payload['reference'] != selected['result']:
                raise ValueError('Observation reader returned another selected response')
            self._post_observation = payload
            self._observation_key = key
            response, origin = payload['response'], payload['origin']
            axis = response['axes'][0]
            raw = response.get('raw_samples')
            if raw:
                values, axes, source_rows = raw['value'], raw['axis'], raw['source_rows']
                valid, reasons = raw['calculation_valid'], raw['exclusion_reasons']
            else:
                values, axes = response['value'], axis['values']
                source_rows = response.get('source_rows', list(range(1, len(values) + 1)))
                valid, reasons = [True] * len(values), [''] * len(values)
            identities = {row['source_row']: row['native'] for row in origin['row_identity']}
            self._observed_rows = list(zip(source_rows, axes, values, valid, reasons))
            self.observed_table.setRowCount(len(values))
            for index, (source_row, x, y, good, reason) in enumerate(self._observed_rows):
                native = identities.get(source_row) or {}
                short_row = native.get('row', native.get('point_index', ''))
                for column, value in enumerate((source_row, short_row, x, y,
                                                '사용' if good else '제외: ' + reason)):
                    self._set_cell(self.observed_table, index, column, value, False)
                self.observed_table.item(index, 1).setToolTip(json.dumps(
                    {'native': native, 'object': origin['object_ref']}, ensure_ascii=False))
            mapping = origin['selection']
            self.observed_info.setText(mapping['value_array'] + ' / ' + response['component'] +
                ' [' + response['unit'] + '] at ' + response['location'] +
                ('\nOriginal Post unavailable: ' + str(payload['source_error']) if not payload['source_available'] else ''))
            self.observed_figure.clear()
            self._observed_axes = self.observed_figure.add_subplot(111)
            def finite_or_gap(value):
                try:
                    number = float(value)
                    return number if math.isfinite(number) else math.nan
                except (ValueError, TypeError):
                    return math.nan
            self._observed_axes.plot([finite_or_gap(x) for x in axes],
                [finite_or_gap(y) if good else math.nan for y, good in zip(values, valid)],
                marker='o', markersize=4, picker=6)
            self._observed_axes.set_xlabel(axis['name'] + ' [' + axis['unit'] + ']')
            self._observed_axes.set_ylabel(response['component'] + ' [' + response['unit'] + ']')
            self._observed_axes.grid(True, alpha=.2)
            self._observed_marker = None
            self.observed_figure.tight_layout()
            self.observed_canvas.draw_idle()
        def failed(error):
            if relevant():
                self._post_observation = None
                self._observation_key = None
                self.observed_info.setText('Observation unavailable: ' + error)
        return self._call(lambda: self.client.post_observation(selected['result']),
                          received, relevant=relevant, rejected=failed)

    def _dispatch_observation_read(self):
        pending, self._queued_observation_read = self._queued_observation_read, None
        selected = self._selected_observation()
        if (self._allow_close or not self.document or not selected or
                pending != (self.document['id'], self.document['session_id'], canonical_hash(selected))):
            return
        self.load_observation()

    def _observation_pick(self):
        if not self._observation_matches() or not hasattr(self, '_observed_axes'):
            return
        if self._observed_marker is not None:
            self._observed_marker.remove()
            self._observed_marker = None
        index = self.observed_table.currentRow()
        if 0 <= index < len(self._observed_rows):
            _, x, y, valid, _ = self._observed_rows[index]
            if valid:
                self._observed_marker, = self._observed_axes.plot([float(x)], [float(y)], 'o',
                                                                 color='#c55324', markersize=8)
        self.observed_canvas.draw_idle()

    def _observation_plot_pick(self, event):
        if len(getattr(event, 'ind', [])):
            row = int(event.ind[0])
            self.observed_table.selectRow(row)
            self.observed_table.scrollToItem(self.observed_table.item(row, 0))

    def open_observed_post(self):
        if not self._observation_matches():
            self.observed_info.setText('Read the selected observation before opening its Post source.')
            return False
        reference = deepcopy(self._post_observation['reference'])
        from .desktop import open_post_observation
        return self._call(lambda: open_post_observation(self.client, reference),
            lambda receipt: self.message.setText('Original Post: ' + str(receipt['status'])))

    def closeEvent(self, event):
        receiver = getattr(self, '_result_return', None)
        if receiver and receiver.reviewing:
            self.message.setText('Finish or cancel observation review before closing.')
            event.ignore()
            return
        super().closeEvent(event)
        if event.isAccepted() and receiver:
            receiver.close()

    def open_source(self):
        source = deepcopy(self.document['draft'].get('source'))
        identifier = source.get('discussion_id',source.get('pde_document_id',source.get('document_id'))) if isinstance(source,dict) else None
        if not isinstance(identifier,str) or not identifier.startswith(('X','S','Q','T','M','N','V','E')):
            self.message.setText('This request has no retained original source document.')
            return
        from .desktop import launch_tool
        def received(payload):
            self.message.setText('Requested the original source document: ' + str(payload.get('status', 'RETURNED')))
        tool = {'X':'expert', 'S':'study', 'Q':'pde', 'T':'data', 'M':'material', 'N':'numerical', 'V':'simulation', 'E':'evaluation'}[identifier[0]]
        return self._call(lambda: launch_tool(self.client,tool,document_id=identifier),received)

    def choose_document(self):
        def choose():
            def listed(payload):
                documents = [doc for doc in payload['documents'] if doc.get('kind') == 'numerical' and doc.get('draft', {}).get('mode') == 'request']
                labels = [f"{doc['title']} · {doc['id']}" for doc in documents]
                if not labels:
                    self.message.setText('No request Plans are available; Material-bound Plans use their own editor.')
                    return
                label, accepted = QInputDialog.getItem(self, 'Open request Plan', 'Document', labels, editable=False)
                if accepted:
                    self.open_document(document_id=documents[labels.index(label)]['id'])
            self._call(self.client.documents, listed)
        self._leave(choose)
