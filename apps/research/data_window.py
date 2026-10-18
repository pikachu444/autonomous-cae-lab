"""Independent Data editor backed by the shared local document service."""
from __future__ import annotations

import argparse
from copy import deepcopy
from .experiment_labels import sample_reason
import json
import math
import os
from time import monotonic
import sys
import threading
import uuid

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Qt, Signal, QItemSelectionModel, QEvent
from shiboken6 import isValid
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QApplication, QAbstractItemView, QComboBox, QDialog, QFileDialog, QHBoxLayout, QHeaderView, QInputDialog,
    QLabel, QLineEdit, QMainWindow, QMessageBox, QPushButton, QPlainTextEdit,
    QDockWidget, QFormLayout, QScrollArea, QSpinBox, QSplitter, QStyledItemDelegate, QTableWidget, QTableWidgetItem, QTabWidget, QToolBar,
    QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure

from caelab.workbench_client import Client
from caelab.workbench_cli import serializable


TERMINAL = {'SUCCEEDED', 'FAILED', 'CANCELLED', 'PARTIAL_FAILURE', 'INTERRUPTED', 'REJECTED'}
TABLE_EXTENSIONS = ('.csv', '.txt', '.dat', '.asc', '.npz')
MAX_ROWS = 4096

# Same display terms as Material, Runner and report pages; never stored labels.
_PHYSICAL_TERMS = {
    'measure': {'force': '힘', 'torque': '토크', 'displacement': '변위', 'stress': '응력',
                'infinitesimal_Cauchy': '미소변형 Cauchy 응력', 'first_Piola': '제1 Piola 응력',
                'position': '위치', 'native_frame_index': '기록된 프레임'},
    'component': {'x': 'X 방향', 'y': 'Y 방향', 'z': 'Z 방향',
                  **{value: value.upper() for value in ('xx', 'yy', 'zz', 'xy', 'yx', 'xz', 'zx', 'yz', 'zy')}},
    'location': {'material_point': '재료점'},
    'frame': {'laboratory': '실험실 좌표', 'lab': '실험실 좌표',
              'material_cartesian': '재료 직교좌표', 'global': '전체 좌표', 'local': '국부 좌표',
              'document_global': '세계 좌표'},
}


class _PhysicalTermDelegate(QStyledItemDelegate):
    """Paint known terms; the item and Data draft always keep exact raw text."""
    def __init__(self, terms, parent):
        super().__init__(parent)
        self.terms = terms

    def displayText(self, value, locale):
        return self.terms.get(str(value), str(value))

    def createEditor(self, parent, option, index):
        editor = QComboBox(parent)
        editor.setEditable(True)
        editor.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        editor.setCompleter(None)
        # Qt otherwise emits activated on focus-out when typed text matches a label.
        # Only an explicit item choice may replace free text with its raw token.
        editor.lineEdit().editingFinished.disconnect()
        for raw, label in self.terms.items():
            if editor.findText(label) < 0:
                editor.addItem(label, raw)
                editor.setItemData(editor.count()-1, '원 기록: ' + raw, Qt.ItemDataRole.ToolTipRole)
        editor.setProperty('dataPhysicalEditor', True)
        editor.lineEdit().textEdited.connect(lambda _: editor.setProperty('typed', True))
        def selected(_):
            editor.setProperty('choiceRaw', editor.currentData())
            editor.setProperty('choiceText', editor.currentText())
            editor.setProperty('typed', False)
            self.commitData.emit(editor)
            self.closeEditor.emit(editor, self.EndEditHint.NoHint)
        editor.activated.connect(selected)
        editor.lineEdit().installEventFilter(self)
        editor.view().setMinimumWidth(max(editor.fontMetrics().horizontalAdvance(label)
            for label in self.terms.values()) + 40)
        return editor

    def setEditorData(self, editor, index):
        raw = index.data(Qt.ItemDataRole.EditRole)
        selected = editor.findData(raw)
        if selected < 0 and raw in self.terms:
            selected = editor.findText(self.terms[raw])
            editor.setItemData(selected, raw)  # Preserve aliases such as lab/laboratory.
            editor.setItemData(selected, '원 기록: ' + raw, Qt.ItemDataRole.ToolTipRole)
        if selected < 0:
            editor.addItem(str(raw), raw)
            selected = editor.count()-1
        editor.setCurrentIndex(selected)
        editor.setProperty('choiceRaw', raw)
        editor.setProperty('choiceText', editor.currentText())
        editor.setProperty('typed', False)
        editor.lineEdit().selectAll()

    def setModelData(self, editor, model, index):
        text = editor.currentText()
        undone = text == editor.property('choiceText') and not editor.lineEdit().isUndoAvailable()
        raw = editor.property('choiceRaw') if not editor.property('typed') or undone else text
        model.setData(index, raw, Qt.ItemDataRole.EditRole)

    def eventFilter(self, watched, event):
        editor = watched if isinstance(watched, QComboBox) else watched.parentWidget()
        if isinstance(editor, QComboBox) and editor.property('dataPhysicalEditor'):
            if event.type() == QEvent.Type.KeyPress:
                key = event.key()
                if key == Qt.Key.Key_Escape:
                    self.closeEditor.emit(editor, self.EndEditHint.RevertModelCache)
                    return True
                hints = {Qt.Key.Key_Return: self.EndEditHint.NoHint, Qt.Key.Key_Enter: self.EndEditHint.NoHint,
                         Qt.Key.Key_Tab: self.EndEditHint.EditNextItem, Qt.Key.Key_Backtab: self.EndEditHint.EditPreviousItem}
                if key in hints:
                    # Commit before QComboBox can auto-select a matching typed label.
                    self.commitData.emit(editor)
                    self.closeEditor.emit(editor, hints[key])
                    return True
            if watched is not editor:
                return False
        return super().eventFilter(watched, event)


def display(value):
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=serializable)


def integer_or_raw(text):
    try:
        return int(text)
    except (TypeError, ValueError):
        return text


def number_or_raw(text):
    """Keep unfinished/nonfinite input as draft text, never as JSON NaN/Infinity."""
    try:
        value = float(text)
        return value if math.isfinite(value) else text
    except (TypeError, ValueError, OverflowError):
        return text


def view_error(draft):
    if not isinstance(draft, dict):
        return 'The original malformed draft remains in Details.'
    metadata = draft.get('test_metadata', {})
    if not isinstance(metadata, dict) or any(not isinstance(value, str) for value in metadata.values()):
        return 'Malformed test metadata remains in Details; Save and Undo preserve the original draft.'
    mapping = draft.get('mapping')
    if not isinstance(mapping, dict) or not isinstance(mapping.get('columns'), dict) or not mapping['columns']:
        return 'This draft cannot fit the channel mapping editor. Its original content remains in Details.'
    if any(not isinstance(spec, dict) or not isinstance(spec.get('axis'), dict) or not isinstance(spec.get('row_selection', {}), dict) for spec in mapping['columns'].values()):
        return 'This draft has no editable response and axis mapping. Its original content remains in Details.'
    return None


class _Signals(QObject):
    finished = Signal(object, object)


class _DataCanvas(FigureCanvasQTAgg):
    def _draw_idle(self):
        # A queued Matplotlib draw can outlive a deleted Data window.
        if isValid(self):
            super()._draw_idle()


class _Read(QRunnable):
    def __init__(self, function):
        super().__init__()
        self.function, self.signals = function, _Signals()
        self.completed = threading.Event()
        self._delivery_lock = threading.Lock()
        self._abandoned = False

    def abandon(self):
        # View lifetime only: never cancel an already submitted owner job.
        with self._delivery_lock:
            self._abandoned = True

    def run(self):
        value, message = None, None
        try:
            with self._delivery_lock:
                if self._abandoned:
                    return
            try:
                value = self.function()
            except Exception as error:
                if hasattr(error, 'read'):
                    try:
                        message = error.read().decode('utf-8')
                    except (OSError, UnicodeError):
                        message = str(error)
                else:
                    message = str(error)
            with self._delivery_lock:
                if not self._abandoned and isValid(self.signals):
                    try:
                        self.signals.finished.emit(value, message)
                    except RuntimeError:
                        # QApplication teardown can delete the C++ sender after
                        # the validity check. Other live-sender errors still fail.
                        if isValid(self.signals):
                            raise
        finally:
            self.completed.set()


class DataWindow(QMainWindow):
    numerical_requested = Signal(object)
    expert_requested = Signal(object)

    def __init__(self, client, *, document_id=None, poll_interval=2000, auto_open=True, companion_task=None):
        if companion_task is not None:
            from caelab.storage import check_id
            if companion_task not in ('processing', 'acquisition') or not isinstance(document_id, str):
                raise ValueError('자료 처리·취득 도구는 선택한 Data 문서에서 여세요.')
            if not check_id(document_id).startswith('T'):
                raise ValueError('자료 처리·취득 도구의 정확한 Data 문서를 선택하세요.')
        super().__init__()
        self._companion_task = companion_task
        self._companion_document_id = document_id if companion_task else None
        self.client, self.document = client, None
        self.local_dirty = self.conflict = self._busy = self._populating = False
        self._foreground_busy = False
        self._allow_close = self._closed = False
        self._worker = None
        self._accepting = False
        self._callback_calls = []
        self._data_windows = []
        self._processed_plan_windows = []
        self._view_error = None
        self._working_draft = None
        self._channel_name = None
        self._result_channel = None
        self._comparison = None
        self._comparison_id = None
        self._comparison_serial = 0
        self._source_id = ''
        self._preview_key = None
        self._preview = None
        self._selected_job = None
        self._results = {}
        self._result_errors = {}
        self._result_pending = set()
        self._result_retry = {}
        self._preview_retry = 0
        self._history = None
        self._source_table = None
        self._source_table_key = None
        self._source_selected = False
        self._pending_command = None
        self._pending_recovery = None
        self._save_acknowledgement = None
        self._pending_view = None
        self._cache_only = False
        self._build_ui()
        self.timer = QTimer(self)
        self.timer.setInterval(poll_interval)
        self.timer.timeout.connect(self.refresh_document)
        if poll_interval > 0:
            self.timer.start()
        if auto_open:
            self.open_document(document_id=document_id)

    def _build_ui(self):
        from .appearance import apply_appearance,configure_plot_fonts
        apply_appearance(QApplication.instance())
        configure_plot_fonts()
        self.resize(1440, 940)
        self.setMinimumSize(800, 620)
        files, edit = self.menuBar().addMenu('파일(&F)'), self.menuBar().addMenu('편집(&E)')
        self.new_action = QAction('새 데이터…', self, shortcut=QKeySequence.New)
        self.open_action = QAction('열기…', self, shortcut=QKeySequence.Open)
        self.save_action = QAction('저장', self, shortcut=QKeySequence.Save)
        self.undo_action = QAction('실행 취소', self, shortcut=QKeySequence.Undo)
        self.redo_action = QAction('다시 실행', self, shortcut=QKeySequence.Redo)
        close = QAction('닫기', self, shortcut=QKeySequence.Close)
        self.new_action.triggered.connect(self.new_document)
        self.open_action.triggered.connect(self.choose_document)
        self.save_action.triggered.connect(self.save_document)
        from .data_material_recovery_host import install_recovery_action
        self.recovery_action=install_recovery_action(self,files)
        from .portable_recovery_host import install_portable_recovery_action
        self.portable_recovery_action = install_portable_recovery_action(self, files)
        close.triggered.connect(self.close)
        from .common.commands import FocusedUndoRedo
        self.focused_undo = FocusedUndoRedo(self, self.undo_action, self.redo_action)
        self.focused_undo.register_target(self, undo=lambda: self.undo_buffer(-1), redo=lambda: self.undo_buffer(1),
            can_undo=lambda: bool(self._history and self._history.index > 0 and not self._busy and not self.conflict and not self._pending_command and not self._cache_only),
            can_redo=lambda: bool(self._history and self._history.index < len(self._history.states)-1 and not self._busy and not self.conflict and not self._pending_command and not self._cache_only),
            label='자료 편집')
        files.addActions([self.new_action, self.open_action, self.save_action, close])
        edit.addActions([self.undo_action, self.redo_action])
        self.window_menu = self.menuBar().addMenu('창(&W)')
        self.next_window_action = QAction('다음 자료 창', self, shortcut=QKeySequence('Ctrl+Tab'))
        self.next_window_action.triggered.connect(self.next_data_window)
        self.window_menu.aboutToShow.connect(self._populate_window_menu)
        self.window_menu.addAction(self.next_window_action)
        toolbar = QToolBar('Data commands')
        toolbar.setMovable(False)
        self.addToolBar(toolbar)
        toolbar.addActions([self.new_action, self.open_action, self.save_action, self.undo_action, self.redo_action])
        from .common.commands import action_button
        self.source_action = QAction('표 파일 열기…', self)
        self.settings_action = QAction('가져오기 설정', self, checkable=True)
        self.settings_action.setChecked(True)
        self.apply_action = QAction('설정 적용', self, shortcut=QKeySequence('Ctrl+Return'))
        self.import_action = QAction('자료 준비', self, shortcut=QKeySequence('F5'))
        self.material_action = QAction('재료에서 사용…', self)
        self.material_action.triggered.connect(self.request_material)
        self.source_button = action_button(self.source_action, self)
        self.settings_button = action_button(self.settings_action, self)
        self.apply_button = action_button(self.apply_action, self)
        self.import_button = action_button(self.import_action, self, primary=True)
        self.settings_action.toggled.connect(self._settings_visible)
        self.source_action.triggered.connect(self.choose_local_csv)
        data_menu = self.menuBar().addMenu('자료(&D)')
        data_menu.addActions([self.source_action, self.settings_action, self.apply_action, self.import_action, self.material_action])
        browse = QAction('서비스 원본 선택…', self)
        browse.triggered.connect(self.choose_source)
        files.addAction(browse)
        self.open_tests_action = QAction('여러 시험 파일 열기…', self)
        self.open_tests_action.triggered.connect(self.choose_test_files)
        files.addAction(self.open_tests_action)
        self.test_columns_action = QAction('시험 열 설정…', self)
        self.test_columns_action.triggered.connect(self.configure_test_columns)
        edit.addAction(self.test_columns_action)
        from .finite_measure_gui import install_data_actions
        install_data_actions(self, edit)
        self.calibration_action = QAction('채널 교정…', self)
        self.calibration_action.triggered.connect(self.edit_calibration)
        edit.addAction(self.calibration_action)
        self.processing_recipe_action = QAction('처리 단계…', self)
        self.processing_recipe_action.triggered.connect(self.edit_processing_recipe)
        edit.addAction(self.processing_recipe_action)
        self.processing_preview_action = QAction('처리 미리보기…', self)
        self.processing_preview_action.triggered.connect(self.preview_processing)
        edit.addAction(self.processing_preview_action)
        self.processing_results_action = QAction('보존한 처리 결과…', self)
        self.processing_results_action.triggered.connect(self.read_processing_result)
        edit.addAction(self.processing_results_action)
        calibrated_result = QAction('교정 전후 결과…', self)
        calibrated_result.triggered.connect(self.read_calibrated_result)
        edit.addAction(calibrated_result)
        uncertainty_result = QAction('제공 불확실성 전파…', self)
        uncertainty_result.triggered.connect(self.open_uncertainty_analysis)
        edit.addAction(uncertainty_result)
        observation_result=QAction('관측 변환의 불확실성…',self)
        observation_result.triggered.connect(lambda:self.open_uncertainty_analysis(observation=True))
        edit.addAction(observation_result)
        affected = QAction('이 자료를 사용하는 계획…', self)
        affected.triggered.connect(self.show_dependents)
        edit.addAction(affected)
        self.acquisition_action = QAction('파일 수집 설정…', self)
        self.acquisition_action.triggered.connect(self.edit_acquisition)
        edit.addAction(self.acquisition_action)
        self.recorded_acquisition_action = QAction('기록 취득…', self)
        from .acquisition_panel import show_acquisition
        self.recorded_acquisition_action.triggered.connect(lambda: show_acquisition(self))
        edit.addAction(self.recorded_acquisition_action)
        report_action = QAction('선택 결과로 보고서…', self)
        report_action.triggered.connect(self.open_report)
        files.addAction(report_action)
        self.apply_action.triggered.connect(self.apply_inputs)
        self.import_action.triggered.connect(self.import_table)
        for button in (self.source_button, self.settings_button, self.apply_button, self.import_button):
            toolbar.addWidget(button)
        self.identity = QLabel()
        toolbar.addWidget(self.identity)
        root = QWidget()
        layout = QVBoxLayout(root)
        self.message = QLabel('Opening Data document…')
        self.message.setWordWrap(True)
        layout.addWidget(self.message)
        conflict = QHBoxLayout()
        self.reload_button = QPushButton('Reload service version')
        self.copy_button = QPushButton('Keep edits as a new document')
        self.reload_button.clicked.connect(self.reload_remote)
        self.copy_button.clicked.connect(lambda: self.open_document(title=self.document['title'] + ' — local edits', draft=self.edited_draft()))
        self.retry_command_button = QPushButton('요청 확인 및 재시도')
        self.retry_command_button.clicked.connect(self.retry_command)
        conflict.addWidget(self.reload_button)
        conflict.addWidget(self.copy_button)
        conflict.addWidget(self.retry_command_button)
        conflict.addStretch()
        layout.addLayout(conflict)
        self.tree = QTreeWidget()
        self.tree.setMinimumWidth(150)
        self.tree.setHeaderLabel('데이터 목록')
        self.tree.itemSelectionChanged.connect(self._selection_changed)
        self.navigator_dock = QDockWidget('데이터 목록', self)
        self.navigator_dock.setObjectName('dataNavigator')
        self.navigator_dock.setWidget(self.tree)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.navigator_dock)
        center = QWidget()
        central = QVBoxLayout(center)
        self.source_label = QLabel('원본 선택에서 가져올 표 파일을 고르세요.')
        self.source_label.setWordWrap(True)
        self.result_label = QLabel()
        self.result_label.setWordWrap(True)
        source_row = QHBoxLayout()
        source_row.addWidget(self.source_label, 1)
        source_row.addWidget(self.result_label, 1)
        central.addLayout(source_row)
        self.editor = QTabWidget()
        self.editor.setMinimumWidth(300)
        setting_pages = []
        for title in ('열과 단위', '시험', '행 선택', '읽기'):
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QScrollArea.Shape.NoFrame)
            page = QWidget()
            page_layout = QVBoxLayout(page)
            page_layout.setContentsMargins(6, 6, 6, 6)
            page_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
            scroll.setWidget(page)
            self.editor.addTab(scroll, title)
            setting_pages.append(page_layout)
        editor, test_settings, row_settings, read_settings = setting_pages
        parsing = QFormLayout()
        self.delimiter = QLineEdit(',')
        self.delimiter.setMaximumWidth(130)
        self.delimiter.setPlaceholderText(',  tab  space')
        self.skip_header = QLineEdit('0')
        self.skip_header.setMaximumWidth(90)
        self.layout_button = QPushButton('원본의 열 구성 사용')
        self.layout_button.clicked.connect(self.use_preview_layout)
        test_columns = QPushButton('시험 열 설정…')
        test_columns.clicked.connect(self.configure_test_columns)
        read_settings.addWidget(test_columns)
        parsing.addRow('구분 문자', self.delimiter)
        parsing.addRow('머리글 행 수', self.skip_header)
        read_settings.addLayout(parsing)
        read_settings.addWidget(self.layout_button)
        channel_controls = QHBoxLayout()
        self.channel_selector = QComboBox()
        self.channel_selector.currentTextChanged.connect(self._channel_changed)
        channel_controls.addWidget(QLabel('채널'))
        channel_controls.addWidget(self.channel_selector, 1)
        editor.addLayout(channel_controls)
        channel_commands = QHBoxLayout()
        for title, mode in (('추가', 'add'), ('복제', 'clone'), ('삭제', 'remove')):
            button = QPushButton(title)
            button.clicked.connect(lambda checked=False, mode=mode: self.edit_channels(mode))
            channel_commands.addWidget(button)
        channel_commands.addStretch()
        editor.addLayout(channel_commands)
        self.mapping = QTableWidget(2, 10)
        self.mapping.setObjectName('dataMapping')
        self.mapping.setHorizontalHeaderLabels(['역할', '채널 또는 축 이름', '원본 열', '단위', '성분', '위치', '물리량 정의', '좌표계', '배율', '보정값'])
        self.mapping.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.mapping.horizontalHeader().setDefaultSectionSize(90)
        for column, width in enumerate((90, 130, 60, 60, 55, 70, 185, 110)):
            self.mapping.setColumnWidth(column, width)
        for column, key in ((5, 'location'), (6, 'measure'), (7, 'frame')):
            self.mapping.setItemDelegateForColumn(column, _PhysicalTermDelegate(_PHYSICAL_TERMS[key], self.mapping))
        self.mapping.horizontalHeaderItem(3).setToolTip('Unit of the imported value after Scale and Offset. A label change does not convert values.')
        self.mapping.horizontalHeaderItem(8).setToolTip('Imported value = original value * Scale + Offset. Applied independently to axis and response; default Scale is 1.')
        self.mapping.horizontalHeaderItem(9).setToolTip('Added after scaling, in the declared imported unit; default Offset is 0.')
        self.mapping.verticalHeader().hide()
        self.mapping.verticalHeader().setDefaultSectionSize(28)
        self.mapping.setMaximumHeight(100)
        self.mapping.setMinimumHeight(100)
        self.mapping.itemChanged.connect(self._mapping_item_edited)
        self.delimiter.textEdited.connect(self._edited)
        self.skip_header.textEdited.connect(self._edited)
        editor.addWidget(self.mapping)
        example = QLabel('열 번호는 0부터 시작합니다. 가져올 값 = 원본 값 × 배율 + 보정값입니다. 단위 이름만 바꿔서는 값이 변환되지 않습니다.')
        example.setWordWrap(True)
        read_settings.addWidget(example)
        self.test_fields = {}
        for key, label in (('test_id', '시험 이름'), ('specimen', '시편'), ('protocol', '시험 방법'), ('temperature', '온도와 단위')):
            metadata = QHBoxLayout()
            field = self.test_fields[key] = QLineEdit()
            field.textEdited.connect(self._edited)
            metadata.addWidget(QLabel(label))
            metadata.addWidget(field)
            test_settings.addLayout(metadata)
        self.row_fields = {}
        for key, label, placeholder in (
            ('include_ranges', '계산에 포함할 구간', '예: 3:20, 30:40 / 비우면 전체'),
            ('exclude_rows', '계산에서 제외할 행', '예: 5, 8'),
            ('exclude_ranges', '계산에서 제외할 구간', '예: 10:15'),
            ('quality_rows', '품질이 불량한 행', '원본 행 번호 / 계산에서는 제외하지 않음'),
            ('display_hidden_rows', '화면에서 숨길 행', '원본 행 번호 / 계산에서는 제외하지 않음'),
            ('reasons', '계산 제외 이유', '행: 이유; 행: 이유'),
            ('quality_reasons', '품질 불량 이유', '행: 이유; 행: 이유')):
            line = QHBoxLayout()
            field = self.row_fields[key] = QLineEdit()
            field.setPlaceholderText(placeholder)
            field.textEdited.connect(self._edited)
            line.addWidget(QLabel(label))
            line.addWidget(field)
            row_settings.addLayout(line)
        note = QLabel('원본 행 번호는 0부터 시작하며 구간은 양 끝을 포함합니다(NPZ는 배열 인덱스). 계산 제외, 품질 표시, 화면 숨김은 각각 독립적입니다. 피팅용과 검증용 자료는 수치 연구에서 나눕니다.')
        note.setWordWrap(True)
        row_settings.addWidget(note)
        self.properties_dock = QDockWidget('가져오기 설정', self)
        self.properties_dock.setObjectName('dataProperties')
        self.properties_dock.setWidget(self.editor)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.properties_dock)
        self.properties_dock.visibilityChanged.connect(self.settings_action.setChecked)
        view_menu = self.menuBar().addMenu('보기(&V)')
        view_menu.addActions([self.navigator_dock.toggleViewAction(), self.properties_dock.toggleViewAction()])
        vertical = QSplitter(Qt.Orientation.Vertical)
        self.sheets = QTabWidget()
        self.sheets.setMinimumHeight(124)
        self.preview_table = self._table(['원본 행'])
        self.preview_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.preview_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.preview_table.itemSelectionChanged.connect(self._table_selection_changed)
        self.preview_table.horizontalHeader().setSortIndicator(0, Qt.SortOrder.AscendingOrder)
        self.preview_table.setContextMenuPolicy(Qt.ContextMenuPolicy.ActionsContextMenu)
        self.values = self._table(['원본 행', '축', '관측', '계산 포함', '원본 품질', '화면 표시', '이유'])
        self.values.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.values.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.values.itemSelectionChanged.connect(self._table_selection_changed)
        self.values.setContextMenuPolicy(Qt.ContextMenuPolicy.ActionsContextMenu)
        for label, mode in [('선택 구간만 사용', 'include'), ('계산에서 제외', 'exclude'),
                            ('선택 행 제외 해제', 'restore'), ('피팅 구간으로 복제', 'fit'),
                            ('검증 구간으로 복제', 'holdout')]:
            action=QAction(label,self.values)
            action.triggered.connect(lambda checked=False, mode=mode:self.select_calculation_rows(mode))
            self.values.addAction(action)
        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        for label, mode in [('선택 행 계산 제외', 'exclude'), ('선택 행 제외 해제', 'restore'),
                            ('선택 행 품질 표시', 'quality'), ('선택 행 품질 표시 해제', 'unquality'),
                            ('선택 행 화면 숨김', 'hide'), ('숨긴 행 모두 표시', 'show_all')]:
            action = QAction(label, self.preview_table)
            action.triggered.connect(lambda checked=False, mode=mode: self.select_calculation_rows(mode))
            self.preview_table.addAction(action)
        self.sheets.addTab(self.preview_table, '원자료')
        self.sheets.addTab(self.values, '가져온 값')
        self.sheets.addTab(self.details, '진단 상세')
        vertical.addWidget(self.sheets)
        graph = QWidget()
        graph_layout = QVBoxLayout(graph)
        rows = QHBoxLayout()
        self.row_start = QSpinBox()
        self.row_start.setRange(0, 2_000_000_000)
        self.row_count = QSpinBox()
        self.row_count.setRange(1, MAX_ROWS)
        self.row_count.setValue(MAX_ROWS)
        self.read_button = QPushButton('구간 읽기')
        self.read_button.clicked.connect(lambda: self.retry_result() if self._selected_job else self.refresh_source_table(force=True))
        rows.addWidget(QLabel('첫 표본'))
        rows.addWidget(self.row_start)
        rows.addWidget(QLabel('개수'))
        rows.addWidget(self.row_count)
        rows.addWidget(self.read_button)
        for label, offset in [('이전', -1), ('다음', 1)]:
            button = QPushButton(label)
            button.clicked.connect(lambda checked=False, offset=offset: self.source_page(offset))
            rows.addWidget(button)
        self.result_channel = QComboBox()
        self.result_channel.currentTextChanged.connect(self._result_channel_changed)
        self.result_channel_label = QLabel('결과 채널')
        rows.addWidget(self.result_channel_label)
        rows.addWidget(self.result_channel)
        rows.addStretch()
        graph_layout.addLayout(rows)
        followup = QHBoxLayout()
        self.material_button = action_button(self.material_action, self)
        followup.addWidget(self.material_button)
        self.compare_button = QPushButton('예측 결과와 비교…')
        self.compare_button.clicked.connect(self.choose_prediction)
        self.plan_button = QPushButton('재료 피팅…')
        self.plan_button.clicked.connect(lambda: self.request_followup('numerical'))
        self.expert_button = QPushButton('전문가에게 질문…')
        self.expert_button.clicked.connect(lambda: self.request_followup('expert'))
        for button in (self.compare_button, self.plan_button, self.expert_button):
            followup.addWidget(button)
        followup.addWidget(QLabel('저장한 비교'))
        self.comparison_selector = QComboBox()
        self.comparison_selector.setObjectName('dataSavedComparison')
        self.comparison_selector.currentIndexChanged.connect(self._comparison_changed)
        followup.addWidget(self.comparison_selector, 1)
        self.followup_bar = QWidget()
        self.followup_bar.setLayout(followup)
        followup.setContentsMargins(0, 0, 0, 0)
        graph_layout.addWidget(self.followup_bar)
        self.figure = Figure(constrained_layout=True)
        self.canvas = _DataCanvas(self.figure)
        self.canvas.setMinimumHeight(140)
        self.axes = self.figure.add_subplot(111)
        graph_layout.addWidget(self.canvas, 1)
        vertical.addWidget(graph)
        vertical.setSizes([220, 420])
        central.addWidget(vertical, 1)
        layout.addWidget(center, 1)
        self.resizeDocks([self.navigator_dock, self.properties_dock], [180, 370], Qt.Orientation.Horizontal)
        self.setCentralWidget(root)
        self._clear_result()
        self._update_actions()

    @staticmethod
    def _table(headers):
        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setAlternatingRowColors(True)
        table.verticalHeader().hide()
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        table.horizontalHeader().setStretchLastSection(True)
        return table

    def _settings_visible(self, visible):
        self.editor.setVisible(visible)
        self.properties_dock.setVisible(visible)

    def _call(self, function, accepted, *, relevant=None, background=False, settled=None):
        if self._closed or not isValid(self):
            return False
        if self._busy:
            if not background and (self._accepting or not self._foreground_busy):
                self._callback_calls.append((function, accepted, relevant, settled))
                return True
            if not background:
                self.message.setText('A document request is in progress. Your current edits are retained.')
            return False
        self._busy = True
        self._foreground_busy = not background
        self._update_actions()
        worker = self._worker = _Read(function)
        def finished(value, error):
            if self._closed or not isValid(self) or self._worker is not worker:
                return
            # Modal choosers process timer events. Keep the request lock until
            # their callback finishes, then start its explicit continuation.
            self._accepting = True
            try:
                if settled:
                    settled(value, error)
                if relevant is None or relevant():
                    if error:
                        self.message.setText(('캐시 보기 / 서비스 연결 안됨. 적용·저장·전달할 수 없습니다. ' if self._cache_only else
                                              '요청 실패 / 현재 편집은 보존했습니다. ') + error)
                    else:
                        accepted(value)
            finally:
                self._accepting = False
                self._busy, self._worker = False, None
                self._foreground_busy = False
            if self._closed or not isValid(self):
                return
            self._update_actions()
            if self._callback_calls:
                next_function, next_accepted, next_relevant, next_settled = self._callback_calls.pop(0)
                self._call(next_function, next_accepted, relevant=next_relevant, settled=next_settled)
            elif not background:
                QTimer.singleShot(0, self.refresh_result)
        worker.signals.finished.connect(finished, Qt.ConnectionType.QueuedConnection)
        QThreadPool.globalInstance().start(worker)
        return True

    def open_document(self, *, document_id=None, title='Data study', draft=None, after=None):
        if self._companion_task and (document_id != self._companion_document_id or draft is not None):
            raise ValueError('이 보조 도구는 처음 선택한 Data 문서에서만 사용합니다.')
        def settled(value, error):
            if error and document_id:
                self._open_cached_view(document_id)
        def opened(document):
            self._opened(document)
            if after and (document_id is None or document['id'] == document_id):
                identity = (document['id'], document['session_id'])
                QTimer.singleShot(0, lambda: after() if self.document and
                    (self.document['id'], self.document['session_id']) == identity else None)
        return self._call(lambda: self.client.document_open(kind='data', title=title, draft=draft, document_id=document_id), opened, settled=settled)

    def open_companion_task(self, task):
        """Wait for this exact document's existing reads before opening its editor."""
        if task not in ('processing', 'acquisition') or self._companion_task and task != self._companion_task:
            raise ValueError('명시한 자료 처리·취득 도구를 선택하세요.')
        if not self.document:
            return False
        identity = (self.document['id'], self.document['session_id'])
        action = self.processing_recipe_action if task == 'processing' else self.recorded_acquisition_action
        timer = QTimer(self); timer.setInterval(50)
        def ready():
            if self._closed or not self.document or (self.document['id'], self.document['session_id']) != identity:
                timer.stop(); timer.deleteLater(); return
            if self._busy or self._accepting or self._callback_calls or self._result_pending:
                return
            timer.stop(); timer.deleteLater()
            if self._cache_only or self.conflict or self.local_dirty or self._view_error or not action.isEnabled():
                self.message.setText('선택한 자료의 읽기 상태와 원본 결과를 확인한 뒤 처리·취득 메뉴에서 다시 여세요.')
                return
            action.trigger()
        timer.timeout.connect(ready); timer.start()
        return True

    def _opened(self, document):
        if self._companion_task:
            if document.get('id') != self._companion_document_id or document.get('kind') != 'data':
                raise ValueError('보조 도구에 연결한 Data 문서가 다릅니다.')
        else:
            from .result_return import bind_receiver
            if not bind_receiver(self,document):return
        self.local_dirty = self.conflict = False
        self._cache_only = False
        from .data_workspace import DraftHistory
        self._history = DraftHistory(document['draft'])
        self._pending_command = self._pending_view = None
        self._pending_recovery = None
        self._save_acknowledgement = None
        self._source_table = self._source_table_key = None
        self._source_selected = False
        self._selected_job = None
        self._comparison = self._comparison_id = None
        self._comparison_serial += 1
        self._results.clear()
        self._result_errors.clear()
        self._preview_key = None
        self._preview = None
        self.preview_table.setRowCount(0)
        self._show_document(document)
        self.settings_action.setChecked(not bool(document.get('runs')))
        self.editor.setCurrentIndex(0)
        self.sheets.setCurrentWidget(self.values if document.get('runs') else self.preview_table)
        self.message.setText('저장한 데이터를 읽었습니다. 내용을 바꾸려면 가져오기 설정을 여세요.' if document.get('runs') else
                             '원본의 열과 단위를 지정하고 설정 적용 후 가져오기를 누르세요.')
        QTimer.singleShot(0, self.refresh_preview)
        QTimer.singleShot(0, self.refresh_source_table)
        self._restore_view()

    def _show_document(self, document, *, prefer_job=None, buffer_draft=None):
        self.document = deepcopy(document)
        self._populating = True
        draft = document['draft'] if buffer_draft is None else buffer_draft
        from .data_workspace import DraftHistory
        if self._history is None:
            self._history = DraftHistory(draft)
        self._view_error = view_error(draft)
        if self._source_id != draft.get('data_id', ''):
            self._preview = None
            self._preview_key = None
            self._preview_retry = 0
            self.preview_table.setRowCount(0)
        self._source_id = draft.get('data_id', '')
        self._working_draft = deepcopy(draft)
        self.channel_selector.blockSignals(True)
        self.channel_selector.clear()
        if not self._view_error:
            self.channel_selector.addItems(list(draft['mapping']['columns']))
            if self._channel_name not in draft['mapping']['columns']:
                self._channel_name = next(iter(draft['mapping']['columns']))
            self.channel_selector.setCurrentText(self._channel_name)
            self._populate_mapping()
            mapping = draft['mapping']
            delimiter = mapping.get('delimiter', ',')
            self.delimiter.setText('space' if delimiter is None else 'tab' if delimiter == '\t' else display(delimiter))
            self.skip_header.setText(display(mapping.get('skip_header', 0)))
            for key, field in self.test_fields.items():
                field.setText(draft.get('test_metadata', {}).get(key, ''))
        else:
            self.mapping.clearContents()
        self.channel_selector.blockSignals(False)
        self._populating = False
        self._populate_tree(prefer_job)
        self._populate_comparisons()
        self._show_details()
        self._update_actions()
        self._draw_cached_result()

    def _populate_mapping(self):
        name = self._channel_name
        response = self._working_draft['mapping']['columns'][name]
        axis = response['axis']
        values = [['X axis', axis.get('name', ''), axis.get('column', ''), axis.get('unit', ''), '—', '—', '—', '—', axis.get('scale', 1), axis.get('offset', 0)],
                  ['Y response', name, response.get('column', ''), *[response.get(key, '') for key in ('unit', 'component', 'location', 'measure', 'frame')], response.get('scale', 1), response.get('offset', 0)]]
        for row, cells in enumerate(values):
            for column, value in enumerate(cells):
                item = QTableWidgetItem(display(value))
                item.setData(Qt.ItemDataRole.UserRole, {'original': deepcopy(value)})
                if column == 0 or row == 0 and 4 <= column <= 7:
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.mapping.setItem(row, column, item)
        selection = response.get('row_selection', {})
        for key, field in self.row_fields.items():
            value = selection.get(key, {} if 'reasons' in key else [])
            if isinstance(value, dict):
                text = '; '.join(f'{row}: {reason}' for row, reason in value.items())
            elif isinstance(value, list):
                text = ', '.join(':'.join(map(str, row)) if isinstance(row, list) else str(row) for row in value)
            else:
                text = display(value)
            field.setText(text)
            field.setProperty('original_text', text)
            field.setProperty('original_value', deepcopy(value))

    def _channel_changed(self, name):
        if self._populating or name == self._channel_name:
            return
        self._working_draft = self.edited_draft()
        if name not in self._working_draft['mapping']['columns']:
            self.message.setText('Channel identity changed; select its current explicit name.')
            return
        self._channel_name = name
        self._populating = True
        self._populate_mapping()
        self._populating = False

        self._draw_source_table()

    def _mapping_item_edited(self, item):
        if self._populating:
            return
        if item.row() == 1 and item.column() == 1 and not self._view_error:
            # Commit a rename and its selector together. Keep the live cell
            # editor's text, including duplicate/blank invalid names, visible.
            columns = self._working_draft['mapping']['columns']
            if self._channel_name in columns:
                index = list(columns).index(self._channel_name)
                self._populating = True
                try:
                    self._working_draft = self.edited_draft()
                    names = list(self._working_draft['mapping']['columns'])
                    self._channel_name = names[index]
                    self.channel_selector.blockSignals(True)
                    self.channel_selector.clear()
                    self.channel_selector.addItems(names)
                    self.channel_selector.setCurrentText(self._channel_name)
                    self.channel_selector.blockSignals(False)
                finally:
                    self._populating = False
        self._edited()

    def edit_channels(self, mode):
        draft = self.edited_draft()
        columns = draft['mapping']['columns']
        selected_name = self._cell(1, 1)
        if selected_name not in columns:
            self.message.setText('Resolve the duplicate channel name before changing the channel list.')
            return
        if mode == 'remove':
            if len(columns) <= 1:
                self.message.setText('Keep at least one channel in the editor.')
                return
            columns.pop(selected_name)
            name = next(iter(columns))
        else:
            name, accepted = QInputDialog.getText(self, 'Channel name', 'Unique explicit channel name')
            if not accepted:
                return
            if not name.strip() or name in columns:
                self.message.setText('Choose a nonempty unique channel name.')
                return
            if mode == 'clone':
                columns[name] = deepcopy(columns[selected_name])
            else:
                from caelab.data_document import default_draft
                columns[name] = default_draft()['mapping']['columns']['response']
        self._working_draft = draft
        self._channel_name = name
        self._populating = True
        self.channel_selector.blockSignals(True)
        self.channel_selector.clear()
        self.channel_selector.addItems(list(columns))
        self.channel_selector.setCurrentText(name)
        self.channel_selector.blockSignals(False)
        self._populate_mapping()
        self._populating = False
        self._edited()

    def _populate_tree(self, prefer_job=None):
        self.tree.blockSignals(True)
        self.tree.clear()
        source = QTreeWidgetItem(['원본 파일'])
        source.setToolTip(0, str(self._source_id))
        self.tree.addTopLevelItem(source)
        imports = QTreeWidgetItem(['가져온 데이터'])
        self.tree.addTopLevelItem(imports)
        self._selected_job = prefer_job or self._selected_job
        if prefer_job:
            self._source_selected = False
        if self._selected_job is None and self.document['runs'] and not self._source_selected:
            self._selected_job = self.document['runs'][-1]['job_id']
        for index, run in enumerate(self.document['runs']):
            text = f"데이터 {index + 1}"
            item = QTreeWidgetItem([text])
            item.setData(0, Qt.ItemDataRole.UserRole, run['job_id'])
            item.setToolTip(0, run['job_id'])
            imports.addChild(item)
            if run['job_id'] == self._selected_job:
                self.tree.setCurrentItem(item)
        self.tree.expandAll()
        self.tree.blockSignals(False)

    def _edited(self, *_):
        if not self._populating:
            draft = self.edited_draft(commit=False)
            self._history.push(draft)
            self.local_dirty = draft != self.document['draft']
            self._update_actions()
            self._draw_cached_result()
            if not self._selected_job:
                self._draw_source_table()

    def undo_buffer(self, offset):
        if self._busy or self.conflict or self._pending_command or self._history is None or self._cache_only:
            return
        draft = self._history.move(offset)
        self.local_dirty = draft != self.document['draft']
        self._show_document(self.document, buffer_draft=draft)
        self._draw_source_table()
        self.message.setText('현재 창의 편집을 되돌렸습니다. 적용된 입력은 유지됩니다.')

    def _cell(self, row, column, *, integer=False, number=False):
        item = self.mapping.item(row, column)
        if item is None:
            return ''
        original = (item.data(Qt.ItemDataRole.UserRole) or {}).get('original', '')
        if item.text() == display(original):
            return deepcopy(original)
        if number:
            return number_or_raw(item.text())
        return integer_or_raw(item.text()) if integer else item.text()

    def _commit_editor(self):
        focus = QApplication.focusWidget()
        if focus and self.editor.isAncestorOf(focus):
            focus.clearFocus()

    def _reveal_editor_focus(self):
        focus = QApplication.focusWidget()
        if focus is None or not self.editor.isAncestorOf(focus):
            return
        if self.mapping.isAncestorOf(focus) and self.mapping.currentItem() is not None:
            self.mapping.scrollToItem(self.mapping.currentItem())
        ancestor = focus.parentWidget()
        while ancestor is not None and ancestor is not self:
            if isinstance(ancestor, QScrollArea):
                ancestor.ensureWidgetVisible(focus, 8, 8)
            ancestor = ancestor.parentWidget()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'editor'):
            QTimer.singleShot(0, self._reveal_editor_focus)

    def edited_draft(self, *, commit=True):
        if commit:
            self._commit_editor()
        draft = deepcopy(self._working_draft or self.document['draft'])
        if self._view_error:
            return draft
        draft['data_id'] = self._source_id
        mapping = draft['mapping']
        old_name = self._channel_name
        response = mapping['columns'][old_name]
        response['column'] = self._cell(1, 2, integer=True)
        for column, key in enumerate(('unit', 'component', 'location', 'measure', 'frame'), 3):
            response[key] = self._cell(1, column)
        response['axis'].update(name=self._cell(0, 1), column=self._cell(0, 2, integer=True), unit=self._cell(0, 3))
        for row, spec in ((0, response['axis']), (1, response)):
            for column, key, default in ((8, 'scale', 1), (9, 'offset', 0)):
                value = self._cell(row, column, number=True)
                # An untouched displayed default does not rewrite an older mapping.
                if key in spec or value != default:
                    spec[key] = value
        name = self._cell(1, 1)
        if name != old_name:
            if name in mapping['columns']:
                # Duplicate names must remain a saveable invalid draft.
                name = ''
                while name in mapping['columns'] and name != old_name:
                    name += ' '
            mapping['columns'] = {name if key == old_name else key: value for key, value in mapping['columns'].items()}
        selection = deepcopy(response.get('row_selection', {}))
        for key, field in self.row_fields.items():
            if field.text() == field.property('original_text'):
                continue
            text = field.text().strip()
            try:
                if 'reasons' in key:
                    value = {part.split(':', 1)[0].strip(): part.split(':', 1)[1].strip() for part in text.split(';') if part.strip()}
                elif 'ranges' in key:
                    value = [[int(number.strip()) for number in part.split(':')] for part in text.split(',') if part.strip()]
                else:
                    value = [int(part.strip()) for part in text.split(',') if part.strip()]
            except (ValueError, IndexError):
                value = text
            if key == 'include_ranges' and not text:
                selection.pop(key, None)
            elif text or key in selection:
                selection[key] = value
        if selection or 'row_selection' in response:
            response['row_selection'] = selection
        metadata = deepcopy(draft.get('test_metadata', {}))
        for key, field in self.test_fields.items():
            if field.text() or key in metadata:
                metadata[key] = field.text()
        if metadata or 'test_metadata' in draft:
            draft['test_metadata'] = metadata
        old_delimiter = mapping.get('delimiter', ',')
        original = 'space' if old_delimiter is None else 'tab' if old_delimiter == '\t' else display(old_delimiter)
        if self.delimiter.text() != original:
            text = self.delimiter.text()
            if text in ('space', 'tab'):
                mapping['delimiter'] = None if text == 'space' else '\t'
            else:
                try:
                    mapping['delimiter'] = json.loads(text)
                except ValueError:
                    mapping['delimiter'] = text
        if self.skip_header.text() != display(mapping.get('skip_header', 0)):
            mapping['skip_header'] = integer_or_raw(self.skip_header.text())
        return draft

    def command(self, operation, arguments=None, *, after=None):
        self._commit_editor()
        if operation in ('document.undo', 'document.redo'):
            self.undo_buffer(-1 if operation == 'document.undo' else 1)
            return True
        if not self.document or self.conflict or self._cache_only:
            return False
        if self._pending_command:
            self.message.setText('앞선 요청의 응답을 먼저 확인하세요. 편집본은 보존했습니다.')
            return False
        if self.local_dirty and operation != 'data.update':
            self.message.setText('Apply the edited mapping first; import uses the exact applied document generation.')
            return False
        document = deepcopy(self.document)
        request = {'document': document, 'operation': operation, 'arguments': deepcopy(arguments or {}),
                   'command_id': 'C' + uuid.uuid4().hex, 'after': after, 'buffer': self.edited_draft()}
        self._pending_command = request
        return self._submit_command(request)

    def retry_command(self):
        if self._pending_command and not self._busy:
            return self._submit_command(self._pending_command)

    def _submit_command(self, request):
        document, operation = request['document'], request['operation']
        from caelab.storage import canonical_hash
        def input_identity(value):
            return (value['id'], value['session_id'], value['generation'], value.get('input_revision'), canonical_hash(value['draft']))
        def relevant():
            return self.document is not None and self.document['id'] == document['id'] and self.document['session_id'] == document['session_id']
        def accepted(response):
            receipt, current = response['receipt'], response['current']
            acknowledged = receipt['document']
            input_changed = input_identity(current) != input_identity(acknowledged)
            if input_changed:
                self.conflict = True
                self._pending_recovery = {'request_id': request['command_id'], 'buffer': deepcopy(request['buffer']),
                    'acknowledgement': deepcopy(receipt), 'current': deepcopy(current),
                    'reason': 'input_changed'}
                self.message.setText('앞선 요청은 확인됐지만 서비스 입력이 이후 바뀌었습니다.' +
                    ' 현재 편집과 확인 응답을 보존했습니다. 서비스 입력을 다시 읽거나 새 문서로 보존하세요.')
                return
            self._pending_command = None
            self._pending_recovery = None
            if operation == 'document.save':
                self._save_acknowledgement = deepcopy(acknowledged)
            self.local_dirty = self.conflict = False
            job = receipt.get('job')
            self._preview_key = None
            self._show_document(current, prefer_job=job['id'] if job else None)
            self.message.setText({'document.save':'저장했습니다.','data.update':'입력을 적용했습니다.',
                'data.import':'자료 가져오기를 시작했습니다.','document.undo':'실행을 취소했습니다.',
                'document.redo':'다시 적용했습니다.'}.get(operation,'처리했습니다.'))
            if request['after']:
                request['after']()
            else:
                QTimer.singleShot(0, self.refresh_preview)
                QTimer.singleShot(0, self.refresh_source_table)
        def settled(receipt, error):
            if error and relevant():
                # Keep the identical command ID/body, including the old generation.
                self._pending_command = request
        def submit_and_confirm():
            receipt = self.client.document_command(document['id'], operation, request['arguments'],
                session_id=document['session_id'], expected_generation=document['generation'], command_id=request['command_id'])
            request['acknowledgement'] = deepcopy(receipt)
            return {'receipt': receipt, 'current': self.client.document_read(document['id'])}
        return self._call(submit_and_confirm, accepted, relevant=relevant, settled=settled)

    def apply_inputs(self, *, after=None):
        return self.command('data.update', {'draft': self.edited_draft()}, after=after)

    def save_document(self, *, after=None):
        self._commit_editor()
        if not self.local_dirty and self._pending_view and self._pending_view['binding']['input_sha256'] == self._view_binding()['input_sha256']:
            return self._save_view(after=after, document=self._pending_view['document'])
        def saved():
            self._save_view(after=after, document=self._save_acknowledgement)
        if self.local_dirty:
            return self.apply_inputs(after=lambda: self.command('document.save', after=saved))
        return self.command('document.save', after=saved)

    def _view_binding(self):
        from .data_workspace import saved_binding
        return saved_binding(self.document)

    def _save_view(self, *, after=None, document=None):
        from .data_workspace import view_path, write_view, saved_binding
        snapshot = document or self.document
        binding = saved_binding(snapshot)
        if not self._pending_view or self._pending_view['binding'] != binding:
            self._pending_view = {'binding': binding, 'source_table': deepcopy(self._source_table),
                'document': deepcopy(snapshot),
                'channel': self._channel_name, 'properties_visible': self.properties_dock.isVisible(),
                'page_start': self.row_start.value(), 'page_count': self.row_count.value()}
        try:
            write_view(view_path(self.client, self.document['id']), self._pending_view)
        except (OSError, ValueError) as error:
            self.message.setText('자료 저장됨 / 보기 저장 실패: ' + str(error) + ' — 저장을 눌러 보기만 재시도하세요.')
            self._update_actions()
            return False
        self._pending_view = None
        self.message.setText('선택한 저장본과 보기를 저장했습니다. 서비스의 이후 결과 또는 저장 변경은 별도로 표시합니다.'
            if self.document.get('dirty') or binding != self._view_binding() else '자료와 보기를 저장했습니다.')
        if after:
            after()
        return True

    def _restore_view(self):
        from .data_workspace import view_path
        try:
            with view_path(self.client, self.document['id']).open(encoding='utf-8') as stream:
                view = json.load(stream)
        except (OSError, ValueError):
            return
        if view.get('binding') != self._view_binding():
            self.message.setText('저장한 보기의 입력 기준이 현재 자료와 다릅니다. 이전 보기 파일을 보존하고 현재 자료를 읽습니다.')
            return
        self.settings_action.setChecked(bool(view.get('properties_visible', False)))
        self.row_start.setValue(max(0, int(view.get('page_start', 0))))
        self.row_count.setValue(max(1, min(MAX_ROWS, int(view.get('page_count', MAX_ROWS)))))
        if view.get('channel') in self._working_draft['mapping']['columns']:
            self.channel_selector.setCurrentText(view['channel'])

    def _open_cached_view(self, identifier):
        from .data_workspace import saved_binding, view_path
        try:
            with view_path(self.client, identifier).open(encoding='utf-8') as stream:
                view = json.load(stream)
            document, table = view['document'], view['source_table']
            if (document['id'] != identifier or view['binding'] != saved_binding(document) or not table or
                    table['data_id'] != document['draft']['data_id']):
                return False
        except (OSError, ValueError, KeyError, TypeError):
            return False
        self._opened(document)
        self._cache_only = True
        self._selected_job = None
        self._source_selected = True
        self._source_table = table
        self._fill_source_table()
        self._draw_source_table()
        self._update_actions()
        return True

    def import_table(self):
        return self.command('data.import')

    def refresh_document(self):
        if self._closed or not isValid(self):
            return
        if not self.document or self._busy or self._cache_only:
            return
        identifier = self.document['id']
        session = self.document['session_id']
        def accepted(remote):
            changed = (remote['session_id'], remote.get('input_revision', remote['generation']), remote['draft']) != (self.document['session_id'], self.document.get('input_revision', self.document['generation']), self.document['draft'])
            if self._pending_command:
                self._pending_command['observed_document'] = deepcopy(remote)
                if changed:
                    self.conflict = True
                    self.message.setText('미확정 요청이 있는 동안 서비스 입력이 바뀌었습니다. 편집을 보존했습니다. 같은 요청의 결과를 확인하거나 서비스 입력을 다시 읽으세요.')
                self._update_actions()
                return
            editing = self.local_dirty or self.mapping.state() == QAbstractItemView.State.EditingState
            if changed and editing:
                self.conflict = True
                self.message.setText('The shared document changed while you were editing. Reload it or keep these edits as a new document.')
            elif not editing and not self.conflict:
                if changed:
                    from .data_workspace import DraftHistory
                    self._history = DraftHistory(remote['draft'])
                self._show_document(remote)
            self._update_actions()
        def refreshed(remote):
            accepted(remote)
            QTimer.singleShot(0, self.refresh_preview)
            QTimer.singleShot(0, self.refresh_result)
        self._call(lambda: self.client.document_read(identifier), refreshed, background=True,
            relevant=lambda: self.document is not None and (self.document['id'], self.document['session_id']) == (identifier, session))

    def reload_remote(self):
        if self._cache_only:
            return self.open_document(document_id=self.document['id'])
        if QMessageBox.question(self, 'Reload Data document', 'Discard this window’s unapplied mapping and reload the service version?',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Cancel) == QMessageBox.StandardButton.Yes:
            self._call(lambda: self.client.document_read(self.document['id']), self._opened)


    def choose_local_csv(self):
        if not self.document or self._busy or self.conflict: return
        path,_=QFileDialog.getOpenFileName(self,'시험 CSV 열기','','표 파일 (*.csv *.txt *.dat);;모든 파일 (*)')
        if not path: return
        from pathlib import Path
        document_id=self.document['id']
        def upload():
            source=Path(path)
            if source.stat().st_size>16*1024*1024: raise ValueError('16 MiB 이하의 표 파일을 선택하세요.')
            receipt=self.client.upload(source.name,source.read_bytes())
            return receipt
        def registered(receipt):
            self._source_id=receipt['data_id'] if 'data_id' in receipt else receipt['id']
            self._preview_key=None; self._preview_retry=0
            self._preview=None; self.preview_table.setRowCount(0)
            self.settings_action.setChecked(True); self.editor.setCurrentIndex(0)
            self._edited()
            self.source_label.setText('원본: '+Path(path).name)
            QTimer.singleShot(0,self.refresh_preview)
        self._call(upload,registered,relevant=lambda:self.document and self.document['id']==document_id)

    def choose_test_files(self):
        if self._busy:
            return
        paths, _ = QFileDialog.getOpenFileNames(self, '시험 파일 열기', '',
            '표 파일 (*.csv *.txt *.dat);;모든 파일 (*)')
        if paths:
            return self.open_test_files(paths)

    def _data_views(self):
        return sorted((window for window in QApplication.topLevelWidgets()
            if isinstance(window, DataWindow) and window.client is self.client and
            window.document and window.isVisible() and not window._closed),
            key=lambda window: window.document['title'])

    @staticmethod
    def _activate_data_window(window):
        window.setWindowState(window.windowState() & ~Qt.WindowState.WindowMinimized)
        window.show(); window.raise_(); window.activateWindow()

    def _populate_window_menu(self):
        self.window_menu.clear()
        windows = self._data_views()
        self.next_window_action.setEnabled(len(windows) > 1)
        self.window_menu.addAction(self.next_window_action)
        self.window_menu.addSeparator()
        for window in windows:
            action = self.window_menu.addAction(window.document['title'])
            action.setCheckable(True); action.setChecked(window is self)
            action.triggered.connect(lambda checked=False, target=window: self._activate_data_window(target))

    def next_data_window(self):
        windows = self._data_views()
        if self in windows and len(windows) > 1:
            self._activate_data_window(windows[(windows.index(self) + 1) % len(windows)])

    def open_test_files(self, paths):
        """Each raw file keeps its own existing Data owner and editable mapping."""
        from pathlib import Path
        from caelab.data_document import default_draft
        def opened():
            documents, failures = [], []
            for path in paths:
                source = Path(path)
                try:
                    if source.suffix.lower() not in TABLE_EXTENSIONS:
                        raise ValueError('지원되는 표 파일은 CSV, TXT, DAT, ASC, NPZ입니다.')
                    if source.stat().st_size > 16 * 1024 * 1024:
                        raise ValueError('16 MiB 이하의 표 파일을 선택하세요.')
                    receipt = self.client.upload(source.name, source.read_bytes())
                    draft = default_draft()
                    draft['data_id'] = receipt.get('data_id', receipt.get('id'))
                    documents.append(self.client.document_open(kind='data', title=source.stem, draft=draft))
                except (OSError, ValueError) as error:
                    failures.append(source.name + ': ' + str(error))
            return documents, failures
        def show(result):
            documents, failures = result
            for document in documents:
                window = DataWindow(self.client, auto_open=False)
                self._data_windows.append(window)
                window._opened(document)
                window.show()
            self.message.setText(f'{len(documents)}개 시험 파일을 열었습니다.' +
                ('\n열지 못한 파일: ' + '\n'.join(failures) if failures else ''))
        return self._call(opened, show, background=True)

    def edit_processing_recipe(self):
        if not self.document or self._busy or self.conflict or self._view_error or self._cache_only:
            return
        if not callable(getattr(self.client, 'data_material', None)):
            self.message.setText('연결한 서비스에서 데이터 처리를 지원하지 않습니다.'); return
        try:
            source = self.selected_source()
        except ValueError:
            self.message.setText('원본 가져오기 결과와 채널을 선택하세요.'); return
        from .data_processing_dialog import DataProcessingRecipeDialog
        base = deepcopy(self.document); before = self.edited_draft()
        existing = before.get('processing', {})
        dialog = DataProcessingRecipeDialog(existing.get('recipe', {'version': 1, 'operations': []}),
                                            list(before['mapping']['columns']), self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        draft = deepcopy(before)
        draft['processing'] = {'source': {key: source[key] for key in
            ('document_id', 'job_id', 'input_revision', 'input_sha256')}, 'recipe': deepcopy(dialog.recipe)}
        identity = lambda document: (document['id'], document['session_id'], document['generation'])
        if identity(self.document) != identity(base) or self.conflict:
            self.document = base; self.conflict = True
        self._working_draft = draft
        self._edited()
        self.message.setText('처리 단계를 설정했습니다. 설정 적용 후 처리 미리보기를 여세요.' if not self.conflict else
                             '자료가 변경되었습니다. 편집한 처리 단계는 보존했습니다. 충돌을 확인하세요.')

    def preview_processing(self):
        if not self.document or self._busy or self.conflict:
            return
        if self.local_dirty:
            self.message.setText('처리 단계의 설정을 적용한 뒤 미리보기를 여세요.'); return
        if not callable(getattr(self.client, 'data_material', None)):
            self.message.setText('연결한 서비스에서 데이터 처리를 지원하지 않습니다.'); return
        from .data_processing_inspector import DataProcessingInspectorDialog as DataProcessingPreviewDialog
        base = deepcopy(self.document)
        def reviewed(preview):
            dialog = DataProcessingPreviewDialog(preview, self)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            def retained(response):
                self._show_document(response['document'])
                self.message.setText('처리 결과를 보존했습니다. 자료 저장으로 함께 보관하세요.')
            self._call(lambda: self.client.data_material('data.processing.apply', dict(
                document_id=base['id'], preview_sha256=preview['preview_sha256'], session_id=base['session_id'],
                expected_generation=base['generation'], command_id='C' + uuid.uuid4().hex)), retained)
        self._call(lambda: self.client.data_material('data.processing.preview', {'document_id': base['id']}), reviewed)

    def read_processing_result(self):
        if not self.document or self._busy:
            return
        records = self.document.get('processing_revisions', [])
        if not records:
            self.message.setText('보존한 처리 결과가 없습니다.'); return
        labels = [f"처리 결과 {index + 1}  {record.get('created_utc', '')[:19].replace('T', ' ')}" for index, record in enumerate(records)]
        selected, accepted = QInputDialog.getItem(self, '보존한 처리 결과', '결과', labels, len(labels) - 1, False)
        if not accepted:
            return
        from .data_processing_inspector import DataProcessingInspectorDialog as DataProcessingPreviewDialog
        identifier = self.document['id']; revision = records[labels.index(selected)]['id']
        def shown(result):
            dialog = DataProcessingPreviewDialog(result, self, retained=True, allow_plan=True)
            dialog.exec()
            if dialog.analysis_source:
                from .experiment_analysis_window import show_analysis_window
                show_analysis_window(self,source=deepcopy(dialog.analysis_source))
            elif dialog.plan_requested:
                from .data_processing_plan import open_processing_plan
                open_processing_plan(self, result, dialog.channel.currentText())
        self._call(lambda: self.client.data_material('data.processing.result',
            {'document_id': identifier, 'processing_revision': revision}), shown)

    def edit_calibration(self):
        if not self.document or self._busy or self.conflict or self._view_error:
            return False
        draft = self.edited_draft()
        channel = self._channel_name
        token = (self.document['id'], self._source_id, channel)
        def show(preview):
            if token != (self.document['id'], self._source_id, self._channel_name):
                return
            from .experiment_dialogs import CalibrationDialog
            dialog = CalibrationDialog(self.client, draft['mapping']['columns'][channel], preview, self)
            active = self.timer.isActive(); self.timer.stop()
            try:
                accepted = dialog.exec() == QDialog.DialogCode.Accepted
            finally:
                if active and not self._closed: self.timer.start()
            if accepted and token == (self.document['id'], self._source_id, self._channel_name):
                original = draft['mapping']['columns'][channel]
                if (original.get('scale',1) != 1 or original.get('offset',0) != 0) and QMessageBox.question(self,
                    '교정식 적용', '기존 배율/오프셋을 새 교정식으로 교체할까요? 적용 전 입력은 실행 취소로 복구할 수 있습니다.',
                    QMessageBox.StandardButton.Ok|QMessageBox.StandardButton.Cancel,
                    QMessageBox.StandardButton.Cancel) != QMessageBox.StandardButton.Ok:
                    return
                recipe = dialog.edited()
                current = self.edited_draft()
                current['mapping']['columns'][channel]['calibration'] = recipe
                current['mapping']['columns'][channel]['unit'] = recipe['output_unit']
                # Affine composition must be explicit; the old mapping is retained by Undo.
                current['mapping']['columns'][channel].pop('scale', None)
                current['mapping']['columns'][channel].pop('offset', None)
                self._working_draft = current
                self._populating=True
                try:self._populate_mapping()
                finally:self._populating=False
                self._edited()
        # Only the matching raw source preview is eligible; never the previous file's cache.
        if self._preview and self._preview.get('id') == self._source_id:
            show(deepcopy(self._preview))
        elif draft == self.document['draft']:
            self._call(lambda: self.client.document_source_preview(self.document['id']), show)
        else:
            self.message.setText('새 원본/열 설정을 적용한 뒤 채널 교정을 여세요.')

    def open_uncertainty_analysis(self,*,observation=False):
        if self._busy:return False
        def launch(source):
            if observation:
                from .observation_uncertainty_dialog import show_from_source
                return show_from_source(self,source)
            from .experiment_analysis_window import show_analysis_window
            return show_analysis_window(self,source=source)
        if self._comparison_id:
            row=next((r for r in self.document.get('comparisons',[]) if r['id']==self._comparison_id),None)
            if not row or not row.get('retained_revision'):
                self.message.setText('비교를 먼저 저장한 뒤 차이의 불확실성을 계산하세요.');return False
            from .experiment_analysis_window import show_analysis_window
            reference={'kind':'comparison','document_id':self.document['id'],'document_kind':'data',
                'saved_revision':row['retained_revision'],'comparison_id':row['id'],'result_sha256':row['result_sha256'],
                'start':self.row_start.value(),'count':min(4096,self.row_count.value())}
            launch({'kind':'retained_comparison','reference':reference})
            return True
        try:source=deepcopy(self.selected_source())
        except ValueError as error:self.message.setText(str(error));return False
        token=self._source_token()
        def opened(reference):
            if self._source_token()!=token:return
            from .experiment_analysis_window import show_analysis_window
            launch({'kind':'result_response','reference':reference,'response':source['response']})
        return self._call(lambda:self.client.document_result_reference(source['document_id'],source['job_id']),opened)

    def read_calibrated_result(self):
        if self._busy:return False
        try:source=self.selected_source()
        except ValueError as error:self.message.setText(str(error));return False
        def show(result):
            from .experiment_dialogs import CalibrationDialog
            response=result.get('responses',{}).get(source['response'],{})
            recipe=response.get('calibration');raw=response.get('raw_samples')
            if not recipe or not raw:
                self.message.setText('선택한 가져오기에는 보존된 채널 교정이 없습니다.');return
            preview={'table_preview':{'headers':['원값'],'rows':[[v] for v in raw['value']],
                'row_numbers':raw['source_rows']}}
            mapping={'column':0,'unit':response['unit'],'calibration':recipe}
            dialog=CalibrationDialog(self.client,mapping,preview,self,retained_response=response)
            dialog.exec()
        return self._call(lambda:self.client.document_result(source['document_id'],source['job_id'],
            selection={'responses':[source['response']],'rows':[0,4096]}),show)

    def show_dependents(self):
        if not self.document or self._busy:return False
        identifier=self.document['id']
        def find(payload):
            rows=[]
            def uses(value):
                if isinstance(value,dict):
                    return value.get('document_id')==identifier or any(uses(v) for v in value.values())
                return isinstance(value,list) and any(uses(v) for v in value)
            for document in payload['documents']:
                if document.get('kind') in {'numerical','study','report'} and uses(document.get('draft',{})):
                    rows.append(document['title'])
            QMessageBox.information(self,'이 자료를 사용하는 계획',
                ('\n'.join(rows)+'\n\n저장된 계획은 선택 당시의 가져오기를 유지합니다. 새 교정은 각 계획에서 명시적으로 다시 선택하세요.')
                if rows else '현재 문서 목록에는 이 자료를 참조하는 계획이 없습니다.')
        return self._call(self.client.documents,find)

    def edit_acquisition(self):
        if not self.document or self._busy or self.conflict or self._view_error:
            return False
        from .experiment_dialogs import AcquisitionDialog
        draft = self.edited_draft()
        dialog = AcquisitionDialog(draft.get('acquisition'), draft['mapping']['columns'], self)
        active = self.timer.isActive()
        self.timer.stop()
        try:
            if dialog.exec() == QDialog.DialogCode.Accepted:
                current = self.edited_draft()
                current['acquisition'] = dialog.edited()
                if dialog.reuse.isChecked():
                    for row in current['acquisition']['channels']:
                        if row['name'] in current['mapping']['columns'] and row['calibration'] is not None:
                            target=current['mapping']['columns'][row['name']]
                            if target.get('scale',1)!=1 or target.get('offset',0)!=0:
                                self.message.setText('기존 배율이 있는 채널은 채널 교정에서 명시적으로 교체하세요.');return
                            target['calibration']=deepcopy(row['calibration'])
                            target['unit']=row['calibration']['output_unit']
                self._working_draft = current
                self._populating=True
                try:self._populate_mapping()
                finally:self._populating=False
                self._edited()
        finally:
            if active and not self._closed: self.timer.start()

    def open_report(self):
        if self._busy: return False
        try: source = self.selected_source()
        except ValueError as error:
            self.message.setText(str(error)); return False
        if self._comparison_id:
            row=next((r for r in self.document.get('comparisons',[]) if r['id']==self._comparison_id),None)
            if not row or not row.get('retained_revision'):
                self.message.setText('비교를 먼저 저장하세요.');return False
            from .report_window import ReportWindow
            reference={'kind':'comparison','document_id':self.document['id'],'document_kind':'data',
                'saved_revision':row['retained_revision'],'comparison_id':row['id'],'result_sha256':row['result_sha256'],
                'start':self.row_start.value(),'count':min(4096,self.row_count.value())}
            window=ReportWindow(self.client,reference=reference)
            self._report_windows=getattr(self,'_report_windows',[])+[window];window.show();return True
        rows = sorted(self._selected_original_rows())
        if not rows:
            self.message.setText('보고서에 넣을 원행을 표 또는 곡선에서 선택하세요.'); return False
        def selected(reference):
            from .report_window import ReportWindow
            frozen = {'kind': 'result', **reference,
                      'selection': {'responses': [source['response']], 'source_rows': rows}}
            window = ReportWindow(self.client, reference=frozen)
            self._report_windows = getattr(self, '_report_windows', []) + [window]
            window.show()
        return self._call(lambda: self.client.document_result_reference(source['document_id'], source['job_id']), selected)

    def configure_test_columns(self):
        if not self.document or self._busy or self.conflict: return
        preview=(self._preview or {}).get('table_preview')
        token=(self.document['id'],self.document['session_id'],self._source_id)
        if not preview or not self._preview_key or self._preview_key[:2]!=(token[0],token[2]):
            self.message.setText('현재 CSV의 원본 미리보기를 먼저 읽으세요.'); return
        from .material_test_dialog import TestColumnsDialog
        dialog=TestColumnsDialog(preview,self)
        if dialog.exec()!=QDialog.DialogCode.Accepted: return
        if token!=(self.document['id'],self.document['session_id'],self._source_id):
            self.message.setText('원본이 바뀌었습니다. 현재 CSV의 열 설정을 다시 여세요.'); return
        draft=self.edited_draft()
        # This explicit command replaces the mapping, never the uploaded bytes.
        if len(draft['mapping']['columns'])>1 and QMessageBox.question(self,'시험 열 설정',
            '현재 채널 설정을 선택한 시험 열로 바꾸시겠습니까?',
            QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel)!=QMessageBox.StandardButton.Yes: return
        draft['mapping']=dialog.result_mapping
        draft.setdefault('test_metadata',{})['protocol']=(
            '관측 '+dialog.response_kind.currentText()+' ['+dialog.response_unit.currentText()+']; '+
            '변형 '+dialog.drive_kind.currentText()+' ['+dialog.drive_unit.currentText()+']; '+
            'A0='+dialog.area.text()+' '+dialog.area_unit.currentText()+'; L0='+dialog.gauge.text()+' '+dialog.gauge_unit.currentText())
        self._show_document(self.document, buffer_draft=draft)
        self._edited()
        self.message.setText('열 설정을 확인하고 적용 후 가져오기를 실행하세요.')

    def choose_source(self):
        def roots(payload):
            choices = [item['id'] for item in payload['roots']]
            if not choices:
                self.message.setText('No local source folders are approved for this service. Configure an input root to register a source.')
                return
            name, accepted = QInputDialog.getItem(self, 'Approved source folder', 'Folder', choices, editable=False)
            if accepted:
                self._choose_directory(name)
        self._call(self.client.local_roots, roots)

    def _choose_directory(self, root, relative='', cursor=0):
        def listed(payload):
            entries = [item for item in payload['entries'] if item['directory'] or item['name'].lower().endswith(TABLE_EXTENSIONS)]
            choices = ([('.. parent folder', 'parent')] if relative else [])
            choices += [(('[Folder] ' if item['directory'] else '') + item['name'], item) for item in entries]
            if payload.get('next_cursor') is not None:
                choices.append(('More files…', 'next'))
            if not choices:
                self.message.setText('No supported numeric tables are listed in this approved folder.')
                return
            label, accepted = QInputDialog.getItem(self, 'Choose original table', root + '/' + relative, [item[0] for item in choices], editable=False)
            if not accepted:
                return
            selected = next(value for text, value in choices if text == label)
            if selected == 'parent':
                self._choose_directory(root, relative.rpartition('/')[0])
            elif selected == 'next':
                self._choose_directory(root, relative, payload['next_cursor'])
            elif selected['directory']:
                self._choose_directory(root, selected['relative'])
            else:
                self.register_source(root, selected['relative'])
        self._call(lambda: self.client.local_inputs(root, relative, cursor=cursor), listed)

    def register_source(self, root, relative):
        def registered(receipt):
            self._source_id = receipt['id']
            self._preview_key = None
            self._preview = None
            self._preview_retry = 0
            self.preview_table.setRowCount(0)
            self._edited()
            self.settings_action.setChecked(True)
            self.editor.setCurrentIndex(0)
            self.source_label.setText('선택한 원본: ' + receipt['name'] + ' (설정 적용 필요)')
            QTimer.singleShot(0, self.refresh_preview)
        return self._call(lambda: self.client.register_local_input(root, relative), registered)

    def refresh_preview(self):
        if self._closed or not isValid(self):
            return
        if not self.document or not self._source_id or self._busy or self._cache_only:
            return
        key = (self.document['id'], self._source_id, self.document.get('saved_revision'))
        if key == self._preview_key or monotonic() < self._preview_retry:
            return
        applied = self._source_id == self.document['draft'].get('data_id')
        def accepted(preview):
            self._preview_key = key
            self._preview = preview
            table = preview.get('table_preview', {})
            if self._source_table and self._source_table.get('data_id') == self._source_id:
                self._show_details()
                self._update_actions()
                return
            self.preview_table.setSortingEnabled(False)
            self.preview_table.clear()
            headers = ['원본 행'] + table.get('headers', [])
            self.preview_table.setColumnCount(len(headers))
            self.preview_table.setHorizontalHeaderLabels(headers)
            self.preview_table.setRowCount(len(table.get('rows', [])))
            for row, values in enumerate(table.get('rows', [])):
                for column, value in enumerate([table.get('row_numbers', [])[row] if row < len(table.get('row_numbers', [])) else 'unknown'] + values):
                    self.preview_table.setItem(row, column, QTableWidgetItem(str(value)))
            self.source_label.setText('원본: ' + preview.get('name', self._source_id) +
                (' (일부 행 미리보기)' if table else ' (미리보기 없음, 열 구성을 직접 지정하세요.)'))
            self._show_details()
            self._update_actions()
        method = (lambda: self.client.document_source_preview(self.document['id'])) if applied else (lambda: self.client.input_preview(self._source_id))
        def settled(value, error):
            if error:
                self._preview_retry = monotonic() + max(1, self.timer.interval() / 1000)
            QTimer.singleShot(0, self.refresh_result)
            QTimer.singleShot(0, self.refresh_source_table)
        self._call(method, accepted, settled=settled, relevant=lambda: key == (self.document['id'], self._source_id, self.document.get('saved_revision')), background=True)

    def source_page(self, direction):
        self.row_start.setValue(max(0, self.row_start.value() + direction * self.row_count.value()))
        if self._selected_job:
            self.retry_result()
        else:
            self.refresh_source_table(force=True)

    def refresh_source_table(self, *, force=False):
        method = getattr(self.client, 'document_source_table', None)
        if not self.document or not self._source_id or not method or self._busy or self._closed or self._cache_only:
            return False
        if self._source_id != self.document['draft'].get('data_id'):
            return False
        key = (self.document['id'], self.document['session_id'], self.document['generation'],
               self.document['input_revision'], self.row_start.value(), self.row_count.value())
        if not force and self._source_table_key == key:
            return False
        def accepted(table):
            from caelab.storage import canonical_hash
            if (table.get('document_id'), table.get('session_id'), table.get('generation'),
                    table.get('input_revision')) != key[:4] or table.get('data_id') != self._source_id or table.get('input_sha256') != canonical_hash(self.document['draft']):
                self.message.setText('원자료를 읽는 동안 입력이 바뀌었습니다. 기존 편집과 표를 보존했습니다. 다시 읽으세요.')
                return
            self._source_table, self._source_table_key = table, key
            self._fill_source_table()
            if not self._selected_job:
                self._draw_source_table()
        return self._call(lambda: method(key[0], start=key[4], count=key[5]), accepted,
            relevant=lambda: self.document is not None and key == (self.document['id'], self.document['session_id'],
                self.document['generation'], self.document['input_revision'], self.row_start.value(), self.row_count.value()), background=True)

    def _fill_source_table(self):
        from .data_workspace import SourceItem
        table = self._source_table
        if table is None:
            return
        widget = self.preview_table
        widget.blockSignals(True)
        widget.setSortingEnabled(False)
        try:
            widget.clear()
            columns, rows = table['columns'], table['source_rows']
            widget.setColumnCount(len(columns) + 4)
            widget.setHorizontalHeaderLabels(['원본 행'] + [str(column['name']) for column in columns] + ['계산 선택', '품질', '화면'])
            widget.setRowCount(len(rows))
            for position, source in enumerate(rows):
                for index, value in enumerate([source] + [column['values'][position] if position < len(column['values']) else '' for column in columns] + ['', '', '']):
                    item = SourceItem(display(value))
                    item.setData(Qt.ItemDataRole.UserRole, source)
                    widget.setItem(position, index, item)
            widget.resizeColumnsToContents()
            widget.setColumnWidth(0, 70)
        finally:
            widget.setSortingEnabled(True)
            widget.blockSignals(False)
        self.source_label.setText(f"{table.get('name', '원자료')} / 전체 {table['total_rows']}행 / {table['start']}부터 {table['count']}행")

    def _draw_source_table(self):
        if self._selected_job or not self._source_table or not self.document or self._view_error:
            return
        table = self._source_table
        if table.get('data_id') != self._source_id:
            return
        selected = self._selected_original_rows()
        self._clear_result()
        self.result_channel.hide()
        self.result_channel_label.hide()
        columns = {column['key']: column for column in table['columns']}
        mapping = self.edited_draft(commit=False)['mapping']
        if any(mapping.get(key, default) != table.get('mapping', {}).get(key, default) for key, default in (('delimiter', ','), ('skip_header', 0))):
            self.result_label.setText('읽기 설정이 바뀌었습니다. 설정 적용 후 원자료를 다시 읽으세요.')
            return
        spec = mapping['columns'].get(self._channel_name, {})
        axis = spec.get('axis', {})
        xcolumn, ycolumn = columns.get(axis.get('column')), columns.get(spec.get('column'))
        if not xcolumn or not ycolumn:
            self.result_label.setText('열 및 단위에서 원자료 열을 선택하세요.')
            return
        from caelab.adapters.file_table import validate_row_selection
        selection = spec.get('row_selection', {})
        try:
            validate_row_selection(selection)
        except ValueError:
            self.result_label.setText('행 선택 입력을 확인하세요. 원자료는 보존했습니다.')
            return
        self.axes.clear()
        self.axes.set_axis_on()
        points, excluded, quality = [], [], []
        self._selection_points, self._point_visible_rows = {}, set()
        includes = selection.get('include_ranges')
        display_rows = {self.preview_table.item(row, 0).data(Qt.ItemDataRole.UserRole): row for row in range(self.preview_table.rowCount())}
        states = {}
        self.preview_table.setSortingEnabled(False)
        for source in table['source_rows']:
            hidden = source in selection.get('display_hidden_rows', [])
            used = ((includes is None or any(first <= source <= last for first, last in includes)) and
                source not in selection.get('exclude_rows', []) and
                not any(first <= source <= last for first, last in selection.get('exclude_ranges', [])))
            poor = source in selection.get('quality_rows', [])
            states[source] = hidden, used, poor
            if source in display_rows:
                row = display_rows[source]
                for index, value in enumerate(('포함' if used else '제외', '확인 필요' if poor else '표시 없음', '숨김' if hidden else '표시'), len(columns) + 1):
                    self.preview_table.item(row, index).setText(value)
                self.preview_table.setRowHidden(row, hidden)
        self.preview_table.setSortingEnabled(True)
        for column in range(len(columns) + 1, len(columns) + 4):
            self.preview_table.resizeColumnToContents(column)
        for source, x, y in zip(table['source_rows'], xcolumn['values'], ycolumn['values']):
            hidden, used, poor = states[source]
            try:
                x, y = float(x), float(y)
            except (ValueError, TypeError, OverflowError):
                continue
            if not math.isfinite(x) or not math.isfinite(y):
                continue
            if hidden:
                points.append((x, float('nan')))
                continue
            self._selection_points[source] = (x, y)
            self._point_visible_rows.add(source)
            points.append((x, y if used else float('nan')))
            if not used:
                excluded.append((x, y))
            if poor:
                quality.append((x, y))
        if points:
            self.axes.plot([point[0] for point in points], [point[1] for point in points], marker='o', markersize=3, label='원본 값')
        for values, marker, color, label in ((excluded, 'x', 'gray', '계산 제외'), (quality, 's', '#c78b22', '품질 확인')):
            if values:
                self.axes.scatter([p[0] for p in values], [p[1] for p in values], marker=marker, c=color, label=label)
        self.axes.set_xlabel(str(xcolumn['name']) + ' (원본)')
        self.axes.set_ylabel(str(ycolumn['name']) + ' (원본)')
        self.axes.grid(True, alpha=.2)
        if points or excluded or quality:
            self.axes.legend(fontsize=8)
        self.canvas.draw_idle()
        self.result_label.setText('원자료 / ' + str(self._channel_name) + (' / 미적용 편집' if self.local_dirty else ' / 적용된 설정'))
        self._point_row_kind = table['source_row_kind']
        self._point_raw_total = table['total_rows']
        from matplotlib.widgets import SpanSelector
        self._span_selector = SpanSelector(self.axes, self._select_curve_interval, 'horizontal', useblit=False,
            props={'alpha': .15, 'facecolor': 'tab:blue'}, button=1, minspan=0)
        self._point_connections = [self.canvas.mpl_connect(name, callback) for name, callback in (
            ('button_press_event', self._curve_press), ('motion_notify_event', self._curve_motion), ('button_release_event', self._curve_release))]
        self._select_original_rows(selected)

    def use_preview_layout(self):
        table = (self._preview or {}).get('table_preview')
        if not table or self._view_error:
            return
        self.delimiter.setText(table['delimiter'])
        self.skip_header.setText(str(table['skip_rows']))
        self.mapping.item(0, 2).setText('0')
        self.mapping.item(1, 2).setText('1' if len(table['headers']) > 1 else '0')
        self._edited()

    def _selection_changed(self):
        item = self.tree.currentItem()
        identifier = item.data(0, Qt.ItemDataRole.UserRole) if item else None
        self._source_selected = identifier is None
        if identifier != self._selected_job:
            self._selected_job = identifier
            self._comparison = self._comparison_id = None
            self._comparison_serial += 1
            self._populate_comparisons()
            self.row_start.setValue(0)
            self._clear_result()
        if identifier:
            self.sheets.setCurrentWidget(self.values)
            self.refresh_result()
        else:
            self.sheets.setCurrentWidget(self.preview_table)
            self.refresh_source_table()
            self._draw_source_table()

    def _result_key(self):
        return (self.document['id'], self._selected_job, self.row_start.value(), self.row_count.value(), self._result_channel) if self.document else None

    def refresh_result(self):
        if self._closed or not isValid(self):
            return
        if not self.document or not self._selected_job or self._busy:
            return
        key = self._result_key()
        if key in self._results:
            self._draw_cached_result()
            return
        if key in self._result_pending or monotonic() < self._result_retry.get(key, 0):
            return
        run = next((item for item in self.document['runs'] if item['job_id'] == self._selected_job), None)
        if run is None:
            return
        identifier, job_id, start, count, channel = key
        def read():
            status = {'state': run['retained_state'], 'result_refs': [1] if run.get('retained_result') else [], 'error': run.get('retained_error')} if run.get('retention_complete') else self.client.status(job_id)
            if not status.get('result_refs'):
                return {'status': status}
            metadata = self.client.document_result(identifier, job_id, selection={'metadata_only': True})
            names = list(metadata.get('responses', {}))
            if not names:
                return {'status': status, 'metadata': metadata}
            return {'status': status, 'metadata': metadata, 'result': self.client.document_result(identifier, job_id,
                    selection={'responses': [channel if channel in names else names[0]], 'rows': [start, start + count]})}
        def accepted(receipt):
            if receipt['status']['state'] in TERMINAL or 'result' in receipt:
                self._results[key] = receipt
            self._draw_result(receipt, key)
        self._result_pending.add(key)
        def settled(receipt, error):
            self._result_pending.discard(key)  # Also clear failed and stale callbacks.
            self._result_retry[key] = monotonic() + max(1, self.timer.interval() / 1000)
            if error:
                self._result_errors[key] = error
            else:
                self._result_errors.pop(key, None)
        if not self._call(read, accepted, settled=settled, relevant=lambda: key == self._result_key(), background=True):
            self._result_pending.discard(key)

    def _result_channel_changed(self, name):
        if name and name != self._result_channel:
            self._result_channel = name
            self._comparison = self._comparison_id = None
            self._comparison_serial += 1
            self._populate_comparisons()
            self._clear_result()
            self.refresh_result()

    def selected_source(self):
        if not self.document or not self._selected_job:
            raise ValueError('Select a retained Data import first')
        run = next((item for item in self.document['runs'] if item['job_id'] == self._selected_job), None)
        if run is None:
            raise ValueError('The selected retained import is no longer in this document')
        name = self.result_channel.currentText()
        if not name:
            raise ValueError('Read an imported channel first')
        return {'document_id': self.document['id'], 'job_id': run['job_id'], 'response': name,
                'input_revision': run['input_revision'], 'input_sha256': run['input_sha256']}

    def _source_token(self):
        try:
            source = self.selected_source()
        except ValueError:
            return None
        return (self.document['session_id'], *[source[key] for key in
            ('document_id', 'job_id', 'response', 'input_revision', 'input_sha256')])

    def _matches_source(self, binding):
        try:
            source = self.selected_source()
        except ValueError:
            return False
        return isinstance(binding, dict) and all(binding.get(key) == value for key, value in source.items())

    def _populate_comparisons(self):
        selector = self.comparison_selector
        selector.blockSignals(True)
        selector.clear()
        selector.addItem('비교 없음', None)
        records = list((self.document or {}).get('comparisons', []))
        current = (self._comparison or {}).get('result', {})
        if current.get('id') and not any(row['id'] == current['id'] for row in records):
            records.append({'id': current['id'], 'binding': current.get('binding', {}), 'metrics': current.get('comparison', {})})
        for number, record in enumerate(records, 1):
            binding = record.get('binding', {})
            if not self._matches_source(binding.get('source')):
                continue
            prediction = binding.get('prediction_source', {})
            metrics = record.get('metrics', {})
            label = f"비교 {number}: {prediction.get('response', '?')} / RMSE {metrics.get('rmse', '?')} {metrics.get('unit', '')}"
            selector.addItem(label, record['id'])
            selector.setItemData(selector.count() - 1, f"{prediction.get('document_id', '?')} / {prediction.get('job_id', '?')}", Qt.ItemDataRole.ToolTipRole)
        index = selector.findData(self._comparison_id)
        selector.setCurrentIndex(max(0, index))
        if index < 0 and self._comparison_id is not None:
            self._comparison_id = None
            self._comparison = None
        selector.blockSignals(False)

    def _comparison_changed(self, index):
        self._comparison_id = self.comparison_selector.itemData(index)
        self._comparison = None
        self._comparison_serial += 1
        self._draw_cached_result()
        if self._comparison_id:
            self.refresh_comparison()
        else:
            self._show_details()

    def refresh_comparison(self):
        if self._closed or not isValid(self):
            return
        method = getattr(self.client, 'document_comparison', None)
        if not self.document or not self._comparison_id or method is None or self._busy:
            return False
        identifier, comparison_id = self.document['id'], self._comparison_id
        start, count = self.row_start.value(), self.row_count.value()
        token, serial = self._source_token(), self._comparison_serial
        current = (self._comparison or {}).get('result', {})
        page = current.get('page', {})
        if current.get('id') == comparison_id and page.get('start') == start and page.get('count') == min(count, max(0, page.get('total', 0) - start)):
            return True
        def relevant():
            return token == self._source_token() and serial == self._comparison_serial and comparison_id == self._comparison_id and (start, count) == (self.row_start.value(), self.row_count.value())
        return self._call(lambda: method(identifier, comparison_id, start=start, count=count),
            self._accept_comparison, relevant=relevant, background=True)

    def _accept_comparison(self, receipt, *, source=None, prediction_source=None):
        binding = receipt.get('binding', {})
        observed = binding.get('source', source)
        if not self._matches_source(observed):
            return
        predicted = binding.get('prediction_source', prediction_source)
        self._comparison = {'source': deepcopy(observed), 'prediction_source': deepcopy(predicted), 'result': deepcopy(receipt)}
        self._comparison_id = receipt.get('id')
        metrics = receipt.get('comparison', receipt)
        self.message.setText(f"Actual retained comparison: {metrics.get('count', '?')} samples · RMSE {metrics.get('rmse', '?')} {metrics.get('unit', '')}")
        self._draw_cached_result()
        self._show_details()
        QTimer.singleShot(0, self.refresh_result)

    def request_followup(self, kind):
        try:
            source = self.selected_source()
        except ValueError as error:
            self.message.setText(str(error))
            return
        payload = {'source': source, 'test_metadata': deepcopy(self.document['draft'].get('test_metadata', {})),
                   'comparison': deepcopy(self._comparison), 'execute': False}
        from .desktop import launch_tool
        command_id='C'+uuid.uuid4().hex
        session_id=self.document['session_id']
        token = self._source_token()
        def create(material_id=None):
            def opened(receipt):
                target=receipt['document']
                if receipt.get('executed') is not False:
                    raise ValueError('Opening a follow-up unexpectedly reported execution')
                signal=self.numerical_requested if kind=='numerical' else self.expert_requested
                signal.emit({**payload,'document_id':target['id']})
                self._call(lambda:launch_tool(self.client,kind,document_id=target['id']),
                    lambda _:self.message.setText('Opened '+target['title']+' from the exact retained source; review and explicitly Run/Ask.'), relevant=lambda: token == self._source_token())
            self._call(lambda:self.client.data_followup(source,kind,session_id=session_id,
                command_id=command_id,material_document_id=material_id),opened, relevant=lambda: token == self._source_token())
        if kind=='expert':
            create()
        else:
            # The display channel may be deformation. Ask for an actual stress
            # observation from this SAME retained import before choosing Material.
            def inspected(metadata):
                responses=metadata.get('responses',{})
                choices=[(name,row) for name,row in responses.items()
                    if row.get('kind')=='series' and row.get('measure') in ('infinitesimal_Cauchy','first_Piola')
                    and row.get('component') in ('xx','yy','zz','xy','xz','yz')]
                if not choices:
                    self.message.setText('응력 관측이 없습니다. 시험 열 설정에서 응력 정의·성분·단위를 지정하고 다시 가져오세요.')
                    return
                labels=[name+' / '+str(row['component'])+' ['+str(row.get('unit','?'))+']' for name,row in choices]
                default=next((i for i,(name,_) in enumerate(choices) if name==source['response']),0)
                selected,ok=QInputDialog.getItem(self,'재료 피팅','관측할 응력 채널',labels,default,False)
                if not ok or token!=self._source_token(): return
                name,observation=choices[labels.index(selected)]
                source['response']=name
                payload['source']=deepcopy(source)
                def choose(documents_receipt):
                    documents=[row for row in documents_receipt['documents'] if row.get('kind')=='material'
                        and row.get('draft',{}).get('backend')=='material.felupe']
                    names=['새 선형 탄성 재료…','새 Neo-Hooke 재료…']+[str(index+1)+'. '+row['title'] for index,row in enumerate(documents)]
                    selected,accepted=QInputDialog.getItem(self,'피팅할 재료','재료 법칙 또는 기존 재료',names,editable=False)
                    if not accepted or token != self._source_token(): return
                    index=names.index(selected)
                    if index>=2: create(documents[index-2]['id']); return
                    expected='infinitesimal_Cauchy' if index==0 else 'first_Piola'
                    if observation.get('measure')!=expected:
                        self.message.setText('선택 관측의 응력 정의가 이 법칙과 다릅니다. 관측 또는 재료 법칙을 다시 선택하세요.');return
                    from caelab.material_document import default_draft, diagnostics
                    draft=default_draft()
                    axis=observation.get('axes',[])
                    if len(axis)!=1 or axis[0].get('name')!='time':
                        self.message.setText('피팅에는 명시한 시간 이력이 필요합니다. 시간 열 설정을 확인하세요.');return
                    draft['settings'].update(stress_unit=observation.get('unit'),time_unit=axis[0].get('unit'))
                    if index==1:
                        draft['settings'].update(model='neo_hooke',parameters={'mu':1.0,'lmbda':2.0})
                    errors=diagnostics(draft)
                    if errors:
                        self.message.setText(errors[0]['message']);return
                    self._call(lambda:self.client.document_open(kind='material',title='시험 재료',draft=draft),
                        lambda model:create(model['id']),relevant=lambda:token==self._source_token())
                self._call(self.client.documents,choose,relevant=lambda:token==self._source_token())
            self._call(lambda:self.client.document_result(source['document_id'],source['job_id'],
                selection={'metadata_only':True}),inspected,relevant=lambda:token==self._source_token())

    def request_material(self):
        """Open the exact retained observation in Material's existing Plan editor."""
        if self._busy or self.conflict or self._pending_command or self._cache_only:
            return False
        try:
            source = self.selected_source()
        except ValueError as error:
            self.message.setText(str(error))
            return False
        from caelab.storage import canonical_hash
        if self.local_dirty or source['input_sha256'] != canonical_hash(self.document['draft']):
            self.message.setText('현재 설정을 적용하고 자료 준비를 실행한 결과를 선택하세요. 이전 결과는 유지됩니다.')
            return False
        token = self._source_token()
        def retained():
            def checked(reference):
                if any(reference.get(key) != source[key] for key in ('document_id', 'job_id', 'input_revision', 'input_sha256')) or not reference.get('result_sha256'):
                    self.message.setText('보존 결과의 신원이 선택한 입력과 다릅니다. 원 결과를 다시 선택하세요.')
                    return
                def choose(payload):
                    documents = [document for document in payload['documents'] if document.get('kind') == 'material'
                                 and document.get('draft', {}).get('backend') == 'material.felupe']
                    labels = ['새 재료…'] + [f"{index + 1}. {document['title']}" for index, document in enumerate(documents)]
                    label, accepted = QInputDialog.getItem(self, '재료에서 사용', '관측을 읽을 재료', labels, editable=False)
                    if not accepted or token != self._source_token():
                        return
                    index = labels.index(label)
                    identifier = documents[index - 1]['id'] if index else None
                    from .desktop import launch_material_observation
                    self._call(lambda: launch_material_observation(self.client, source, document_id=identifier),
                        lambda _: self.message.setText('재료 창 열기를 요청했습니다. 사용할 계획과 시험 조건을 확인해 등록하세요.'),
                        relevant=lambda: token == self._source_token())
                self._call(self.client.documents, choose, relevant=lambda: token == self._source_token())
            self._call(lambda: self.client.document_result_reference(source['document_id'], source['job_id']),
                checked, relevant=lambda: token == self._source_token())
        if self.document.get('dirty') or not self.document.get('saved_revision'):
            return self.save_document(after=retained)
        retained()
        return True

    def choose_prediction(self):
        try:
            source = self.selected_source()
        except ValueError as error:
            self.message.setText(str(error))
            return
        token = self._source_token()
        def listed(payload):
            documents = [item for item in payload['documents'] if item.get('kind') in {'material', 'pde'}]
            labels = [f"{item['title']} — {item['id']}" for item in documents]
            if not labels:
                self.message.setText('No retained Material / PDE prediction documents are available.')
                return
            label, accepted = QInputDialog.getItem(self, 'Prediction document', 'Choose a retained model result', labels, editable=False)
            if accepted and token == self._source_token():
                self._choose_prediction_run(documents[labels.index(label)]['id'], source, token=token)
        self._call(self.client.documents, listed, relevant=lambda: token == self._source_token())

    def _choose_prediction_run(self, identifier, source, *, token=None):
        token = token or self._source_token()
        def read(document):
            runs = document.get('runs', [])
            if not runs:
                self.message.setText('This model has no actual retained calculation result.')
                return
            labels = [f"{run['job_id']} · input g{run.get('input_generation', '?')}" for run in runs]
            label, accepted = QInputDialog.getItem(self, 'Prediction run', 'Actual retained run', labels, editable=False)
            if accepted and token == self._source_token():
                run = runs[labels.index(label)]
                self._choose_prediction_channel(identifier, run['job_id'], source, token=token)
        self._call(lambda: self.client.document_read(identifier), read, relevant=lambda: token == self._source_token())

    def _choose_prediction_channel(self, identifier, job_id, source, *, token=None):
        token = token or self._source_token()
        def read(result):
            names = list(result.get('responses', {}))
            if not names:
                self.message.setText('This run has no retained response channels.')
                return
            name, accepted = QInputDialog.getItem(self, 'Prediction channel', 'Explicit matching physical channel', names, editable=False)
            if accepted and token == self._source_token():
                self.compare_prediction({'document_id': identifier, 'job_id': job_id, 'response': name}, source=source)
        self._call(lambda: self.client.document_result(identifier, job_id, selection={'metadata_only': True}), read, relevant=lambda: token == self._source_token())

    def compare_prediction(self, prediction_source, *, source=None):
        source = deepcopy(source or self.selected_source())
        prediction_source = deepcopy(prediction_source)
        if not self._matches_source(source):
            self.message.setText('The imported source selection changed; select the prediction again for the current channel.')
            return False
        token = self._source_token()
        self._comparison_serial += 1
        serial = self._comparison_serial
        def accepted(result):
            comparison, remote = result
            if remote is not None:
                if remote.get('session_id') != self.document['session_id']:
                    self.conflict = True
                    self.message.setText('The Data owner session changed during comparison; refresh it before selecting a retained comparison.')
                    return
                if not self.local_dirty:
                    self._show_document(remote)
            self._accept_comparison(comparison, source=source, prediction_source=prediction_source)
        method = getattr(self.client, 'document_compare', None)
        if method is None:
            self.message.setText('The connected service does not expose retained Data comparison.')
            return False
        def compare():
            comparison = method(source, prediction_source)
            read = getattr(self.client, 'document_read', None)
            return comparison, read(source['document_id']) if read is not None else None
        return self._call(compare, accepted,
            relevant=lambda: token == self._source_token() and serial == self._comparison_serial)

    def retry_result(self):
        key = self._result_key()
        self._result_retry.pop(key, None)
        self._result_errors.pop(key, None)
        self._results.pop(key, None)
        self.refresh_result()

    def _draw_cached_result(self):
        if not self.document:
            return
        receipt = self._results.get(self._result_key())
        if receipt:
            self._draw_result(receipt, self._result_key())
        elif not self._selected_job:
            self._clear_result()
            self._draw_source_table()

    def _clear_result(self):
        for connection in getattr(self, '_point_connections', []):
            self.canvas.mpl_disconnect(connection)
        self._point_connections = []
        selector = getattr(self, '_span_selector', None)
        if selector is not None:
            selector.disconnect_events()
        self._point_press = None
        self._point_table_page = None
        self._drawn_result_key = None
        self._selection_points={}
        self._point_visible_rows = set()
        self._selection_artist=None
        self.followup_bar.setVisible(bool(self._selected_job))
        self.result_channel.setVisible(bool(self._selected_job))
        self.result_channel_label.setVisible(bool(self._selected_job))
        self.values.setRowCount(0)
        self.canvas.setToolTip('')
        self.axes.clear()
        self.axes.set_axis_off()
        self.axes.text(.5, .5, '가져온 결과를 선택하면 원래 값을 볼 수 있습니다.', ha='center', va='center', transform=self.axes.transAxes)
        self.canvas.draw_idle()
        self.result_label.setText('가져온 결과가 선택되지 않았습니다.')
        self.result_label.setToolTip('')

    def _draw_result(self, receipt, key):
        same_page = key == getattr(self, '_drawn_result_key', None)
        selected = self._selected_original_rows() if same_page else set()
        try: current_source = int(self.values.item(self.values.currentRow(), 0).text()) if same_page else None
        except (ValueError, AttributeError): current_source = None
        point_table = getattr(self, '_point_table_page', None) if same_page else None
        self._clear_result()
        self._drawn_result_key = key
        _, identifier, start, _, _ = key
        run = next(item for item in self.document['runs'] if item['job_id'] == identifier)
        stale = self.local_dirty or not run.get('is_current_input', run['input_generation'] == self.document['generation'])
        state = receipt['status']['state']
        state = {'SUCCEEDED': '가져오기 완료', 'FAILED': '가져오기 실패', 'RUNNING': '가져오는 중',
                 'QUEUED': '대기 중', 'CANCELLED': '취소됨', 'SAVED': '저장된 데이터'}.get(state, state)
        self.result_label.setText(state + (' / 이전 원본 또는 설정의 데이터' if stale else ' / 현재 적용된 설정'))
        responses = receipt.get('result', {}).get('responses', {})
        if not responses:
            error = receipt['status'].get('error')
            if error:
                message = error.get('message') if isinstance(error, dict) else error
                summary = message if isinstance(message, str) else '실패 원인을 진단 상세에서 확인하세요.'
                prefix = 'Missing or invalid table column:'
                if isinstance(message, str) and message.startswith(prefix):
                    token = message[len(prefix):].strip()
                    if token and len(token.splitlines()) == 1:
                        summary = '원자료 열 ‘' + token + '’의 지정과 가져오기 설정을 확인하세요.'
                self.result_label.setText(self.result_label.text() + ' · ' + summary)
                self.result_label.setToolTip(display(error))
            self._show_details()
            return
        name, response = next(iter(responses.items()))
        self.result_channel.blockSignals(True)
        names = list(receipt.get('metadata', {}).get('responses', {})) or list(responses)
        if [self.result_channel.itemText(i) for i in range(self.result_channel.count())] != names:
            self.result_channel.clear()
            self.result_channel.addItems(names)
        self.result_channel.setCurrentText(name)
        self.result_channel.blockSignals(False)
        self._populate_comparisons()
        if self._comparison_id:
            QTimer.singleShot(0, self.refresh_comparison)
        axes, values = response.get('axes', []), response.get('value', [])
        if response.get('kind') != 'series' or len(axes) != 1 or not isinstance(values, list) or len(axes[0].get('values', [])) != len(values):
            self.result_label.setText(self.result_label.text() + ' · unsupported retained response shape; see Details')
            return
        axis = axes[0]
        self.values.setRowCount(len(values))
        for row, (x, y) in enumerate(zip(axis['values'], values)):
            for column, value in enumerate([response.get('source_rows', [])[row] if row < len(response.get('source_rows', [])) else f'sample {start + row}', f"{display(x)} {axis.get('unit', 'unknown')}", f"{display(y)} {response.get('unit', 'unknown')}"]):
                self.values.setItem(row, column, QTableWidgetItem(str(value)))
        raw = response.get('raw_samples')
        self._point_raw_total = raw.get('total_count', len(raw.get('source_rows', []))) if isinstance(raw, dict) else 0
        self._point_row_kind = response.get('source_row_kind')
        if isinstance(raw, dict) and isinstance(raw.get('source_rows'), list):
            self._show_raw_rows(raw, start)
        try:
            x, y = [float(value) for value in axis['values']], [float(value) for value in values]
            if not all(math.isfinite(value) for value in x + y) or response.get('valid') is False:
                raise ValueError('invalid retained values')
        except (ValueError, TypeError, OverflowError):
            self.result_label.setText(self.result_label.text() + ' · invalid values preserved; no curve drawn')
            return
        self.axes.clear()
        self.axes.set_axis_on()
        original_rows = response.get('source_rows', [])
        hidden = set()
        if isinstance(raw, dict):
            hidden = {row for row, visible in zip(raw.get('source_rows', []), raw.get('display_visible', [])) if not visible}
        # Raw audit paging and calculation paging have different positions after
        # exclusions. The retained mapping names display-hidden ORIGINAL rows;
        # use those IDs even when the matching raw audit row is outside its page.
        retained_mapping = response.get('mapping', {})
        retained_selection = retained_mapping.get('row_selection', {}) if isinstance(retained_mapping, dict) else {}
        if isinstance(retained_selection, dict):
            explicit_hidden = retained_selection.get('display_hidden_rows', [])
            if isinstance(explicit_hidden, list):
                hidden.update(row for row in explicit_hidden if type(row) is int)
        # Explicit gaps and display-hidden samples must break the rendered line.
        segments = response.get('segments') or [{'source_rows': original_rows}]
        if original_rows:
            for segment in segments:
                keep = set(segment.get('source_rows', []))
                self._point_visible_rows.update(row for row in original_rows if row in keep and row not in hidden)
                points = [(a, float('nan') if source in hidden else b) for source, a, b in zip(original_rows, x, y) if source in keep]
                if points:
                    self.axes.plot([a for a, _ in points], [b for _, b in points], marker='o', markersize=3)
        else:
            self.axes.plot(x, y, marker='o', markersize=3)
        comparison = self._comparison or {}
        compared_source = comparison.get('source', {})
        metrics = comparison.get('result', {})
        metrics = metrics.get('comparison', metrics)
        if self._matches_source(compared_source) and compared_source.get('job_id') == identifier and compared_source.get('response') == name:
            observation = metrics.get('observation', {})
            compared_axes = observation.get('axes', []) if isinstance(observation, dict) else []
            prediction = metrics.get('prediction', [])
            if len(compared_axes) == 1 and isinstance(prediction, list) and len(compared_axes[0].get('values', [])) == len(prediction):
                comparison_x = compared_axes[0]['values']
                page_start = comparison.get('result', {}).get('page', {}).get('start', 0)
                segments = metrics.get('observation_segments') or [{'rows': [page_start, page_start + len(prediction)]}]
                for segment in segments:
                    first, last = segment.get('rows', [page_start, page_start + len(prediction)])
                    first, last = max(first, start, page_start) - page_start, min(last, start + len(values), page_start + len(prediction)) - page_start
                    points = [(a, b) for a, b in zip(comparison_x[first:last], prediction[first:last]) if a is not None and b is not None]
                    if points:
                        self.axes.plot([a for a, _ in points], [b for _, b in points], linestyle='--', marker='x', label='Retained prediction')
                self.axes.legend()
        axis_name = axis.get('name', 'unknown')
        physical = {key: _PHYSICAL_TERMS[key].get(value, value) if isinstance(value, str) else display(value)
                    for key in _PHYSICAL_TERMS for value in [response.get(key, '미기록')]}
        title = f"{physical['measure']} ({physical['component']})"
        self.canvas.setToolTip('\n'.join(
            caption + ': ' + physical[key] for key, caption in
            (('measure', '물리량'), ('component', '성분'), ('location', '위치'), ('frame', '좌표계')))
            + '\n단위: ' + str(response.get('unit', '미기록')))
        location = response.get('location', '')
        if (isinstance(location, str) and location.startswith('trace_point:')
                and response.get('frame') == 'document_global'
                and response.get('measure') in {'position', 'native_frame_index'}):
            point_name = location.removeprefix('trace_point:')
            title = (f'{point_name}의 {name} 경로 (세계 좌표)' if response['measure'] == 'position'
                     else f'{point_name}의 기록된 프레임')
            if axis_name == 'nominal_time':
                axis_name = '출력 격자 시간'
            elif axis_name == 'time':
                axis_name = '계산 시각'
        self.axes.set_xlabel(f"{axis_name} [{axis.get('unit', 'unknown')}]")
        self.axes.set_ylabel(f"{name} [{response.get('unit', 'unknown')}]")
        self.axes.set_title(title, fontsize=9)
        self.axes.grid(True, alpha=.25)
        self.canvas.draw_idle()
        self.result_label.setText(self.result_label.text() + f' / 표본 {start}부터 {len(values)}개')
        self._selection_points = {row:point for row,point in zip(original_rows,zip(x,y)) if row not in hidden}
        if isinstance(raw,dict):
            excluded=[]
            for row,a,b,used,visible in zip(raw.get('source_rows',[]),raw.get('transformed_axis',[]) or [],
                    raw.get('transformed_value',[]),raw.get('calculation_valid',[]),raw.get('display_visible',[])):
                if visible and not used and type(a) in (int,float) and type(b) in (int,float) and math.isfinite(a) and math.isfinite(b):
                    excluded.append((a,b));self._selection_points[row]=(a,b)
                    self._point_visible_rows.add(row)
            if excluded:
                self.axes.scatter([p[0] for p in excluded],[p[1] for p in excluded],marker='x',c='gray',label='계산 제외')
        from matplotlib.widgets import SpanSelector
        self._span_selector=SpanSelector(self.axes,self._select_curve_interval,'horizontal',
                useblit=False,props={'alpha':.15,'facecolor':'tab:blue'},button=1,minspan=0)
        # Connect after the selector: click-sized spans must not erase the pick.
        self._point_connections = [self.canvas.mpl_connect(name, callback) for name, callback in (
            ('button_press_event', self._curve_press), ('motion_notify_event', self._curve_motion),
            ('button_release_event', self._curve_release))]
        self._selection_artist = None
        if point_table is not None:
            self._show_raw_rows(point_table)
            self._point_table_page = point_table
        if selected:
            self._select_original_rows(selected, scroll_to=current_source)
        self._show_details()

    def _show_raw_rows(self, raw, start=0):
        offset = 0 if 'page_start' in raw else start
        indexes = range(offset, min(len(raw['source_rows']), offset + self.row_count.value()))
        blocked = self.values.blockSignals(True)
        try:
            self.values.setRowCount(len(indexes))
            for row, index in enumerate(indexes):
                cells = [raw['source_rows'][index], (raw.get('transformed_axis') or raw.get('axis') or [None]*len(raw['source_rows']))[index],
                    raw.get('transformed_value',raw['value'])[index],
                    '포함' if raw['calculation_valid'][index] else '제외',
                    '정상' if raw['quality_valid'][index] else '확인 필요',
                    '표시' if raw['display_visible'][index] else '숨김',
                    sample_reason('; '.join(reason for reason in (raw['exclusion_reasons'][index], raw['quality_reasons'][index]) if reason))]
                for column, cell in enumerate(cells):
                    self.values.setItem(row, column, QTableWidgetItem(display(cell)))
                self.values.item(row,2).setToolTip('원본 값: '+display(raw['value'][index]))
                self.values.item(row,1).setToolTip('원본 축: '+display((raw.get('axis') or [None]*len(raw['source_rows']))[index]))
        finally:
            self.values.blockSignals(blocked)

    def _selected_original_rows(self):
        rows = set()
        table = self.values if self._selected_job else self.preview_table
        for index in table.selectionModel().selectedRows():
            try: rows.add(int(table.item(index.row(), 0).text()))
            except (ValueError, AttributeError): pass
        return rows

    def _select_original_rows(self, sources, *, additive=False, scroll_to=None):
        table = self.values if self._selected_job else self.preview_table
        selection = table.selectionModel()
        blocked = table.blockSignals(True)
        try:
            if not additive: table.clearSelection()
            for row in range(table.rowCount()):
                item = table.item(row, 0)
                try: source = int(item.text())
                except (ValueError, AttributeError): continue
                if source in sources:
                    index = table.model().index(row, 0)
                    selection.select(index, QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows)
                if source == scroll_to:
                    selection.setCurrentIndex(table.model().index(row, 0), QItemSelectionModel.SelectionFlag.NoUpdate)
                    table.scrollToItem(item)
        finally:
            table.blockSignals(blocked)
        self.highlight_rows()

    def _curve_press(self, event):
        self._point_press = None
        if event.button == 1 and event.inaxes is self.axes and not self.axes.get_navigate_mode():
            self._point_lookup_serial = getattr(self, '_point_lookup_serial', 0) + 1
            self._point_press = (event.x, event.y)
            self._point_dragged = False

    def _curve_motion(self, event):
        if self._point_press is not None:
            self._point_dragged |= math.dist(self._point_press, (event.x, event.y)) > 4 * self.canvas.device_pixel_ratio

    def _curve_release(self, event):
        if self._point_press is None: return
        self._curve_motion(event)
        click = not self._point_dragged and event.button == 1 and event.inaxes is self.axes
        self._point_press = None
        if not click or self.axes.get_navigate_mode(): return
        selected = self._selected_original_rows()
        candidates = []
        for order, (source, point) in enumerate(self._selection_points.items()):
            if source not in self._point_visible_rows or type(source) is not int or not all(math.isfinite(value) for value in point): continue
            pixel = self.axes.transData.transform(point)
            distance = math.dist(pixel, (event.x, event.y))
            if self.axes.bbox.contains(*pixel) and distance <= 6 * self.canvas.device_pixel_ratio:
                candidates.append((distance, source not in selected, order, source))
        if not candidates: return
        source = min(candidates)[-1]
        additive = 'ctrl' in (event.key or '') or 'control' in (event.key or '')
        self._point_lookup_serial = getattr(self, '_point_lookup_serial', 0) + 1
        table = self.values if self._selected_job else self.preview_table
        if any(table.item(row, 0).text() == str(source) for row in range(table.rowCount())):
            self.sheets.setCurrentWidget(table)
            self._select_original_rows({source}, additive=additive, scroll_to=source)
            self.message.setText('원본 행 ' + str(source) + '을 선택했습니다.')
        else:
            self._read_point_row(source, additive)

    def _read_point_row(self, source, additive):
        if self._point_row_kind not in ('physical_line', 'array_index') or type(self._point_raw_total) is not int or self._point_raw_total <= 0:
            self.message.setText('이 점의 원본 행을 현재 표에서 찾을 수 없습니다. 구간을 다시 읽어 주세요.')
            return
        token, key, draft = self._source_token(), self._result_key(), deepcopy(self.edited_draft())
        serial, count, total = self._point_lookup_serial, self.row_count.value(), self._point_raw_total
        channel = self.result_channel.currentText()
        def read():
            lower, upper = 0, total - 1
            bounds = (-1, math.inf)
            # file_table retains enumerate physical lines or range array indices,
            # both strictly increasing; never infer a raw offset from a row ID.
            while lower <= upper:
                middle = (lower + upper) // 2
                result = self.client.document_result(key[0], key[1], selection={'responses':[channel], 'rows':[middle, middle+1]})
                raw = result['responses'][channel].get('raw_samples', {})
                rows = raw.get('source_rows', [])
                if len(rows) != 1 or type(rows[0]) is not int or not bounds[0] < rows[0] < bounds[1]: break
                if rows[0] == source:
                    first = middle // count * count
                    result = self.client.document_result(key[0], key[1], selection={'responses':[channel], 'rows':[first, first+count]})
                    page = result['responses'][channel].get('raw_samples', {})
                    if source in page.get('source_rows', []): return page
                    break
                if rows[0] < source:
                    lower, bounds = middle+1, (rows[0], bounds[1])
                else:
                    upper, bounds = middle-1, (bounds[0], rows[0])
            raise ValueError('선택한 원본 행을 저장 자료에서 확인할 수 없습니다.')
        def accepted(raw):
            self._show_raw_rows(raw)
            self._point_table_page = raw
            self.sheets.setCurrentWidget(self.values)
            self._select_original_rows({source}, scroll_to=source)
            self.message.setText('원본 행 ' + str(source) + '을 선택했습니다.' +
                (' 다른 표 구간으로 이동해 이전 선택을 바꿨습니다.' if additive else ''))
        self._call(read, accepted, background=True, relevant=lambda: token == self._source_token() and
                   key == self._result_key() and serial == self._point_lookup_serial and draft == self.edited_draft())

    def _select_curve_interval(self, first, last):
        if self._point_press is not None and not self._point_dragged: return
        self._point_lookup_serial = getattr(self, '_point_lookup_serial', 0) + 1
        # Mouse coordinates are integral pixels; include the boundary pixel.
        tolerance = abs(self.axes.get_xlim()[1] - self.axes.get_xlim()[0]) / max(1, self.axes.bbox.width)
        wanted={row for row,(x,y) in getattr(self,'_selection_points',{}).items() if first-tolerance<=x<=last+tolerance}
        table = self.values if self._selected_job else self.preview_table
        selection=table.selectionModel()
        table.blockSignals(True); table.clearSelection()
        for row in range(table.rowCount()):
            try: source=int(table.item(row,0).text())
            except (ValueError,AttributeError): continue
            if source in wanted:
                selection.select(table.model().index(row,0),QItemSelectionModel.SelectionFlag.Select|QItemSelectionModel.SelectionFlag.Rows)
        table.blockSignals(False);self.highlight_rows()

    def _table_selection_changed(self):
        self._point_lookup_serial = getattr(self, '_point_lookup_serial', 0) + 1
        self.highlight_rows()

    def highlight_rows(self):
        artist=getattr(self,'_selection_artist',None)
        if artist is not None:
            try: artist.remove()
            except (ValueError,NotImplementedError): pass
        selected=[]
        table = self.values if self._selected_job else self.preview_table
        for row in sorted({item.row() for item in table.selectedIndexes()}):
            item=table.item(row,0)
            try: source=int(item.text())
            except (ValueError,AttributeError): continue
            point=getattr(self,'_selection_points',{}).get(source)
            if point is not None: selected.append(point)
        limits = self.axes.get_xlim(), self.axes.get_ylim()
        self._selection_artist=(self.axes.scatter([p[0] for p in selected],[p[1] for p in selected],
            s=48,facecolors='none',edgecolors='tab:red',zorder=5) if selected else None)
        self.axes.set_xlim(limits[0]); self.axes.set_ylim(limits[1])
        self.canvas.draw_idle()

    def select_calculation_rows(self, mode):
        if not self.document or self._busy or self.conflict or self._view_error or self._cache_only or self._pending_command:
            return
        rows=[]
        table = self.values if self._selected_job else self.preview_table
        for row in sorted({item.row() for item in table.selectedIndexes()}):
            try: rows.append(int(table.item(row,0).text()))
            except (ValueError,AttributeError): return
        if not rows and mode != 'show_all': return
        # Edit the channel actually displayed, using its original row identities.
        name=self.result_channel.currentText() if self._selected_job else self._channel_name
        draft=self.edited_draft()
        columns=draft['mapping']['columns']
        if name not in columns or self._source_id != self.document['draft'].get('data_id'):
            self.message.setText('현재 원본의 같은 채널을 선택한 뒤 구간을 편집하세요.'); return
        run=next((r for r in self.document['runs'] if r['job_id']==self._selected_job),{})
        if self._selected_job and run.get('input_sha256') != __import__('caelab.storage',fromlist=['canonical_hash']).canonical_hash(self.document['draft']):
            self.message.setText('이전 설정의 결과입니다. 현재 설정을 가져온 뒤 구간을 선택하세요.'); return
        selected=deepcopy(columns[name].get('row_selection',{}))
        from caelab.adapters.file_table import validate_row_selection
        try: validate_row_selection(selected)
        except ValueError as error:
            self.settings_action.setChecked(True); self.editor.setCurrentIndex(2)
            self.message.setText('행 선택의 미완성 입력을 먼저 고치세요: '+str(error))
            return
        if mode in ('fit','holdout'):
            target=name+('_fit' if mode=='fit' else '_holdout')
            if target in columns:
                self.message.setText('같은 구간 채널이 있습니다. 그 채널의 구간을 편집하거나 이름을 바꾸세요.'); return
            columns[target]=deepcopy(columns[name]); name=target
        if mode in ('include','fit','holdout'):
            selected['include_ranges']=[[value,value] for value in sorted(set(rows))]
        elif mode=='exclude':
            selected['exclude_rows']=sorted(set(selected.get('exclude_rows',[]))|set(rows))
        elif mode in ('quality', 'hide'):
            key = 'quality_rows' if mode == 'quality' else 'display_hidden_rows'
            selected[key] = sorted(set(selected.get(key, [])) | set(rows))
        elif mode == 'unquality':
            selected['quality_rows'] = [row for row in selected.get('quality_rows', []) if row not in rows]
        elif mode == 'show_all':
            selected['display_hidden_rows'] = []
        elif mode=='restore':
            selected['exclude_rows']=[value for value in selected.get('exclude_rows',[]) if value not in rows]
            # Split existing ranges precisely; retain other rows and their reasons.
            ranges=[]
            for first,last in selected.get('exclude_ranges',[]):
                remaining=[v for v in rows if first<=v<=last]
                start=first
                for v in sorted(set(remaining)):
                    if start<v: ranges.append([start,v-1])
                    start=v+1
                if start<=last: ranges.append([start,last])
            selected['exclude_ranges']=ranges
        columns[name]['row_selection']=selected
        self._working_draft=draft; self._channel_name=name
        self._populating=True
        self.channel_selector.blockSignals(True); self.channel_selector.clear()
        self.channel_selector.addItems(list(columns)); self.channel_selector.setCurrentText(name)
        self.channel_selector.blockSignals(False)
        self._populate_mapping(); self._populating=False
        self._edited()
        self.message.setText('구간을 변경했습니다. 설정 적용 후 자료 준비를 실행하세요.' +
            (' 이전 결과는 그대로 유지됩니다.' if self.document.get('runs') else ''))

    def _show_details(self):
        self.details.setPlainText(json.dumps({'document': self.document, 'view_diagnostic': self._view_error,
            'source_preview': self._preview, 'selected_result': self._results.get(self._result_key()),
            'result_read_errors': list(self._result_errors.values()), 'comparison': self._comparison}, ensure_ascii=False, indent=2, default=serializable))

    def _update_actions(self):
        present = self.document is not None
        enabled = present and not self._busy and not self.conflict and not self._pending_command and not self._cache_only
        self.editor.setEnabled(present and not self._foreground_busy and not self._view_error and not self._pending_command and not self._cache_only)
        self.source_action.setEnabled(enabled and not self._view_error)
        self.apply_action.setEnabled(enabled and self.local_dirty and not self._view_error)
        blocked = present and any(item.get('blocks_evaluation') for item in self.document.get('diagnostics', []))
        self.import_action.setEnabled(enabled and not self.local_dirty and not blocked and not self._view_error)
        from caelab.storage import canonical_hash
        run = next((row for row in (self.document or {}).get('runs', []) if row['job_id'] == self._selected_job), {})
        current_result = present and run.get('input_sha256') == canonical_hash(self.document['draft'])
        self.material_action.setEnabled(enabled and not self.local_dirty and bool(current_result))
        self.save_action.setEnabled(enabled)
        self.processing_recipe_action.setEnabled(enabled and bool(self._selected_job) and not self._view_error)
        self.processing_preview_action.setEnabled(enabled and not self.local_dirty and bool((self.document or {}).get('draft', {}).get('processing')))
        self.processing_results_action.setEnabled(present and not self._busy and bool((self.document or {}).get('processing_revisions')))
        self.focused_undo.refresh()
        self.new_action.setEnabled(not self._busy and not self._companion_task)
        self.open_action.setEnabled(not self._busy and not self._companion_task)
        self.open_tests_action.setEnabled(not self._busy and not self._companion_task)
        self.read_button.setEnabled(present and bool(self._source_id) and not self._busy)
        for button in (self.compare_button, self.plan_button, self.expert_button):
            button.setEnabled(enabled and bool(self._selected_job) and not self.local_dirty)
        self.comparison_selector.setEnabled(enabled and bool(self._selected_job) and not self.local_dirty)
        self.layout_button.setEnabled(bool((self._preview or {}).get('table_preview')) and not self._view_error)
        self.reload_button.setVisible(self.conflict or self._cache_only)
        self.reload_button.setText('서비스에 다시 연결' if self._cache_only else '서비스 입력 다시 읽기')
        self.copy_button.setVisible(self.conflict)
        self.reload_button.setEnabled(not self._busy)
        self.copy_button.setEnabled(not self._busy)
        self.retry_command_button.setVisible(self._pending_command is not None)
        self.retry_command_button.setEnabled(not self._busy)
        if present:
            title = {'processing': '자료 처리 도구', 'acquisition': '기록 취득 도구'}.get(self._companion_task, 'Data')
            self.setWindowTitle(title + ' — ' + self.document['title'] + (' *' if self.local_dirty or self.document.get('dirty') else ''))
            self.identity.setText('설정 적용 필요' if self.local_dirty else '입력 오류' if blocked or self._view_error else
                '저장하지 않은 변경' if self.document.get('dirty') else '저장됨' if self.document.get('saved_revision') is not None else '새 문서')
            self.identity.setToolTip(f"Document: {self.document['id']}\nSession: {self.document['session_id']}\nSaved: {self.document.get('saved_revision')}")

    def _leave(self, continuation):
        if self._pending_command:
            self.message.setText('요청 결과를 먼저 확인하세요. 현재 편집과 같은 명령의 재시도 정보를 유지합니다.')
            return
        if self._pending_view:
            question = QMessageBox(self)
            question.setWindowTitle('보기 저장 실패')
            question.setText('자료는 저장됐지만 보기를 저장하지 못했습니다. 보기를 다시 저장한 뒤 계속할 수 있습니다.')
            retry = question.addButton('보기 저장 재시도', QMessageBox.ButtonRole.AcceptRole)
            question.addButton('취소', QMessageBox.ButtonRole.RejectRole)
            question.exec()
            if question.clickedButton() is retry:
                self.save_document(after=lambda: self._leave(continuation))
            return
        from .data_material_recovery_host import leave_with_recovery
        leave_with_recovery(self, continuation)

    def new_document(self):
        def create():
            title, accepted = QInputDialog.getText(self, 'New Data document', 'Title', text='Data study')
            if accepted and title.strip():
                self.open_document(title=title.strip())
        self._leave(create)

    def choose_document(self):
        def choose():
            def listed(payload):
                documents = [item for item in payload['documents'] if item.get('kind') == 'data']
                if not documents:
                    self.message.setText('열 수 있는 시험 데이터가 없습니다.')
                    return
                from .data_material_document_dialog import DataMaterialDocumentDialog
                dialog = DataMaterialDocumentDialog(documents, kind='data', parent=self)
                if dialog.exec() == dialog.DialogCode.Accepted:
                    self.open_document(document_id=dialog.selected_document['id'])
            self._call(self.client.documents, listed)
        self._leave(choose)

    def closeEvent(self, event):
        if self._allow_close:
            from .result_return import close_receiver
            close_receiver(self)
            self._closed = True
            self.timer.stop()
            self._callback_calls.clear()
            if self._worker is not None:
                self._worker.abandon()
            self._worker = None
            self._busy = self._accepting = False
            self._result_pending.clear()
            event.accept()
            return
        event.ignore()
        def leave():
            self._allow_close = True
            QTimer.singleShot(0, self.close)
        self._leave(leave)

    def showEvent(self, event):
        self._allow_close = self._closed = False
        if self.timer.interval() > 0:
            self.timer.start()
        super().showEvent(event)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--service', default=os.environ.get('CAELAB_SERVICE_URL'))
    parser.add_argument('--document-id')
    parser.add_argument('--data-task', choices=('processing', 'acquisition'))
    args = parser.parse_args(argv)
    if not args.service:
        parser.error('--service or CAELAB_SERVICE_URL must identify the existing local service')
    if args.data_task and not args.document_id:
        parser.error('--data-task requires the selected Data document')
    app = QApplication.instance() or QApplication(sys.argv[:1])
    client=Client(args.service)
    if args.data_task:
        from caelab.storage import check_id
        identifier = check_id(args.document_id)
        selected = client.document_read(identifier)
        if not identifier.startswith('T') or selected.get('id') != identifier or selected.get('kind') != 'data':
            raise ValueError('처리·취득할 정확한 Data 문서를 선택하세요.')
    elif args.document_id:
        from .result_return import activate_existing
        if activate_existing(client,args.document_id,kind='data').get('status')=='ACTIVATED':
            return 0
    window = DataWindow(client, document_id=args.document_id, auto_open=not bool(args.data_task), companion_task=args.data_task)
    window.show()
    if args.data_task:
        window.open_document(document_id=args.document_id, after=lambda: window.open_companion_task(args.data_task))
    return app.exec()


if __name__ == '__main__':
    raise SystemExit(main())
