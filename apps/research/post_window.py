"""Qt analysis controls for an existing ParaView document owner.

The native render/plot views remain in ParaView. This process edits small typed
recipes and delegates every inspection, filter, sample and export to that owner.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
import math
import os
import re
import sys
import uuid
from urllib.error import HTTPError

from PySide6.QtCore import QThreadPool, QTimer, QSignalBlocker, Qt, Signal
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QApplication, QAbstractItemView, QCheckBox, QComboBox, QFormLayout,
    QDialog, QDialogButtonBox, QHBoxLayout, QHeaderView, QInputDialog, QLabel, QLineEdit, QMainWindow,
    QMenu, QMessageBox, QPlainTextEdit, QPushButton, QScrollArea, QSpinBox, QSplitter, QStyle,
    QTabWidget, QTableWidget, QTableWidgetItem, QToolBar, QTreeWidget,
    QTreeWidgetItem, QToolButton, QVBoxLayout, QWidget, QSizePolicy,
)

from apps.research.data_window import _Read, number_or_raw, integer_or_raw, display
from caelab.workbench_client import Client

TERMINAL = {'SUCCEEDED', 'FAILED', 'CANCELLED', 'INTERRUPTED'}
FILTERS = ('Slice', 'Clip', 'Contour', 'WarpByVector', 'PlotOverLine')
FILTER_FIELDS = {
    'Slice': ('origin', 'normal', 'offsets', 'triangulate', 'crinkle', 'time'),
    'Clip': ('origin', 'normal', 'invert', 'crinkle', 'time'),
    'Contour': ('array', 'association', 'values', 'time'),
    'WarpByVector': ('array', 'association', 'scale_factor', 'time'),
    'PlotOverLine': ('array', 'association', 'point1', 'point2', 'resolution', 'tolerance', 'time'),
}
MEASUREMENT_DECLARATIONS = ('quantity', 'units', 'measure', 'frame', 'coordinate_units', 'coordinate_frame')
MEASUREMENT_FIELDS = {
    'point': ('source_ref', 'array', 'association', 'point_indices', 'time', 'time_units', 'time_origin') + MEASUREMENT_DECLARATIONS,
    'path': ('source_ref', 'array', 'association', 'point1', 'point2', 'resolution', 'tolerance', 'time', 'time_units', 'time_origin') + MEASUREMENT_DECLARATIONS,
    'time': ('source_ref', 'array', 'association', 'point_indices', 'time_units', 'time_origin') + MEASUREMENT_DECLARATIONS,
    'gauge': ('source_ref', 'array', 'association', 'point_indices', 'point1', 'point2', 'direction',
              'basis', 'coordinate_configuration', 'time', 'time_units', 'time_origin') + MEASUREMENT_DECLARATIONS,
}
MEASUREMENT_FIELDS['gauge_time'] = tuple(key for key in MEASUREMENT_FIELDS['gauge'] if key != 'time') + ('time_range', 'reference_time')
MEASUREMENT_FIELDS['surface_time'] = ('source_ref', 'array', 'association', 'component', 'direction', 'basis', 'geometry',
    'time_range', 'reference_time', 'time_units', 'time_origin') + MEASUREMENT_DECLARATIONS
MEASUREMENT_FIELDS['surface_average'] = tuple(key for key in MEASUREMENT_FIELDS['surface_time'] if key not in ('time_range', 'reference_time')) + ('time',)
SIDE_FIELDS = ('source_ref', 'array', 'association', 'quantity', 'units', 'measure', 'frame',
               'coordinate_units', 'coordinate_frame', 'time', 'time_units', 'time_origin')
VECTORS = {'origin', 'normal', 'offsets', 'values', 'point1', 'point2', 'point_indices', 'direction', 'time_range'}
BOOLEANS = {'triangulate', 'crinkle', 'invert'}
NUMBERS = {'time', 'reference_time', 'tolerance', 'scale_factor'}
LABELS = {'source_ref': '원 자료', 'array': '필드', 'association': '자료 위치 (POINTS/CELLS)',
          'quantity': '물리량', 'units': '응답 단위', 'measure': '물리적 정의', 'frame': '응답 좌표계',
          'coordinate_units': '좌표 단위', 'coordinate_frame': '좌표계',
          'time': '원 결과 시각 (없으면 비움)', 'time_units': '시간 단위',
          'time_origin': '시간 기준', 'point_indices': '원본 VTK 점 번호 (0부터)',
          'origin': '평면 원점 [x, y, z]', 'normal': '평면 법선 [x, y, z]',
          'point1': '첫 점 [x, y, z]', 'point2': '끝 점 [x, y, z]',
          'direction': '상대변위의 단위 방향 [x, y, z]', 'basis': '방향의 기준',
          'coordinate_configuration': '좌표 상태', 'resolution': '선 구간 수', 'tolerance': '허용 오차',
          'offsets': '단면 위치', 'values': '등고값', 'scale_factor': '벡터 배율'}
LABELS.update(time_range='실제 시각 범위 [시작, 끝]', reference_time='기준 좌표의 실제 시각',
              component='평균할 성분', geometry='평균 면적의 기준')


def defaults(kind, source_ref=''):
    if kind == 'comparison':
        from .post_comparison_editor import default_recipe
        return default_recipe()
    if kind == 'legacy_comparison':
        side = {key: None if key in ('time', 'time_units', 'time_origin') else
                'POINTS' if key == 'association' else '' for key in SIDE_FIELDS}
        return {'a': deepcopy(side), 'b': deepcopy(side), 'method': 'same_mesh', 'tolerance': ''}
    if kind == 'filter':
        return {'source_ref': source_ref, 'filter': 'Slice', 'settings': {}}
    return {'source_ref': source_ref, 'measurement': 'point', 'array': '',
            'association': 'POINTS', 'point_indices': [], 'time': None,
            'time_units': None, 'time_origin': None}


def field_text(value):
    if value is None:
        return ''
    if isinstance(value, list):
        return ', '.join(display(item) for item in value)
    return display(value)


def parse_field(key, text, original):
    if text == field_text(original):
        return deepcopy(original)
    if key in ('time', 'time_units', 'time_origin') and not text.strip():
        return None
    if key in VECTORS:
        if not text.strip():
            return []
        try:
            parts = [part.strip() for part in text.split(',')]
            values = [integer_or_raw(part) if key == 'point_indices' else number_or_raw(part) for part in parts]
            return values
        except (ValueError, TypeError):
            return text
    if key == 'resolution':
        return integer_or_raw(text)
    if key in NUMBERS:
        return number_or_raw(text)
    if key in BOOLEANS:
        return {'true': True, 'false': False}.get(text.lower(), text)
    return text


def native_payload(command):
    """Unwrap the command outcome and native owner response, without guesses."""
    result = command.get('outcome', {}).get('result', {})
    if isinstance(result, dict) and result.get('status') == 'COMPLETED' and 'result' in result:
        return result['result']
    return result


class PostWindow(QMainWindow):
    sampleSelectionChanged = Signal(int, object)

    def __init__(self, client, *, document_id, session_id=None, poll_interval=1500, auto_open=True):
        super().__init__()
        from .appearance import apply_appearance
        apply_appearance(QApplication.instance())
        self.client, self.document_id, self.session_id = client, document_id, session_id
        self.document = None
        self._busy = self._populating = self._allow_close = self.local_dirty = self.conflict = False
        self._workers = []
        self._closed = False
        self._measurement_poll_pending = None
        self._measurement_poll_queued = False
        self._accepting = False
        self._callback_calls = []
        self._pending = None
        self._last_command = None
        self._source_ref = self._object_ref = None
        self._tree_selection = None
        self._kind = 'comparison'
        self._draft = defaults(self._kind)
        self._edit_serial = 0
        self._samples = None
        self._sample_basis = None
        self._confirmed_sample_selection = None
        self._contact_dialog = None
        self._curve_catalog = []
        self._build_ui()
        self.timer = QTimer(self)
        self.timer.setInterval(max(1, poll_interval))
        self.timer.timeout.connect(self.refresh_document)
        if poll_interval > 0:
            self.timer.start()
        self.command_timer = QTimer(self)
        self.command_timer.setInterval(200)
        self.command_timer.timeout.connect(self.poll_command)
        if auto_open:
            self.refresh_document(initial=True)

    def _build_ui(self):
        self.resize(440, 900)
        self.setMinimumSize(380, 650)
        toolbar = QToolBar('후처리')
        self.addToolBar(toolbar)
        self.open_action = QAction('열린 후처리로 전환…', self, shortcut=QKeySequence.Open)
        self.open_action.triggered.connect(self.choose_document)
        self.save_action = QAction('저장', self, shortcut=QKeySequence.Save)
        self.save_action.triggered.connect(self.save_document)
        toolbar.addActions([self.open_action, self.save_action])
        self.menuBar().addMenu('파일(&F)').addActions([self.open_action, self.save_action])
        self.refresh_button = QPushButton('새로고침')
        self.refresh_button.clicked.connect(lambda: self.refresh_document(explicit=True))
        toolbar.addWidget(self.refresh_button)
        self.numerical_button = QPushButton('Numerical로 보내기…')
        self.numerical_button.setProperty('appearanceRole', 'primary')
        self.numerical_button.setObjectName('useMeasurementInNumerical')
        self.numerical_button.clicked.connect(self.use_in_numerical)
        self.contact_button = QPushButton('접촉 결과…')
        self.contact_button.setObjectName('inspectContactResults')
        self.contact_button.clicked.connect(self.open_contact_inspector)
        self.handoff_retry = QPushButton('곡선 전달 이어가기')
        self.handoff_retry.clicked.connect(self._continue_measurement_handoff)
        self.handoff_retry.setVisible(False)
        toolbar.addWidget(self.handoff_retry)
        self._measurement_handoff = None
        self._measurement_delivery = None
        self._measurement_dialog = None
        self.identity = QLabel()
        root = QWidget()
        outer = QVBoxLayout(root)
        self.identity.setProperty('appearanceRole', 'title')
        outer.addWidget(self.identity)
        from .post_settings_pages import MessageLabel
        self.message = MessageLabel('ParaView에서 후처리 문서를 열면 원 결과와 측정값을 선택할 수 있습니다.')
        self.message.setWordWrap(True)
        outer.addWidget(self.message)
        split = QSplitter(Qt.Orientation.Horizontal)
        outer.addWidget(split, 1)
        left = QWidget()
        left_layout = QVBoxLayout(left)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(['원 결과와 분석', '상태'])
        self.tree.setColumnWidth(0, 185)
        self.tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.tree.itemSelectionChanged.connect(self._tree_selected)
        left_layout.addWidget(self.tree, 1)
        self.add_source_button = QPushButton('결과 파일 추가…')
        self.add_source_button.clicked.connect(lambda: self.choose_source(repair=False))
        self.repair_button = QPushButton('원파일 다시 연결…')
        self.repair_button.clicked.connect(lambda: self.choose_source(repair=True))
        self.changed_source_button = QPushButton('변경 자료로 새 프로젝트…')
        self.changed_source_button.clicked.connect(self.open_changed_source)
        self.show_source_button = QPushButton('ParaView에서 보기')
        self.show_source_button.clicked.connect(self.show_source)
        self.inspect_button = QPushButton('필드 정보 읽기')
        self.inspect_button.clicked.connect(self.inspect_source)
        left_layout.addWidget(self.add_source_button)
        self.array_table = QTableWidget(0, 5)
        self.array_table.setHorizontalHeaderLabels(['필드', '위치', '성분 수', '단위', '물리 의미'])
        self.array_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.array_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.array_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.array_table.itemSelectionChanged.connect(self._array_selected)
        self.array_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for col, width in ((1, 100), (2, 75), (3, 70), (4, 230)):
            self.array_table.setColumnWidth(col, width)
        self.array_description = QLabel('필드를 선택하면 출력 위치와 물리적 정의를 볼 수 있습니다.')
        self.array_description.setObjectName('postFieldMeaning')
        self.array_description.setTextFormat(Qt.TextFormat.PlainText)
        self.array_description.setWordWrap(True)
        self.array_description.setMinimumWidth(0)
        split.addWidget(left)
        center = QWidget()
        center_layout = QVBoxLayout(center)
        new_button = QToolButton()
        new_button.setText('분석 추가')
        new_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        new_menu = QMenu(new_button)
        self.new_buttons = []
        for kind, label in (('comparison', '결과 비교'), ('filter', '필터'), ('measurement', '측정')):
            action = new_menu.addAction(label + '…')
            action.triggered.connect(lambda checked=False, kind=kind: self.new_object(kind))
            self.new_buttons.append(action)
        curve_action = new_menu.addAction('시간·시험 곡선 비교…')
        curve_action.triggered.connect(self.new_curve_comparison)
        self.new_buttons.append(curve_action)
        new_button.setMenu(new_menu)
        toolbar.addWidget(new_button)
        self.object_label = QLabel('새 결과 비교')
        self.object_label.setProperty('appearanceRole', 'section')
        self.object_label.setWordWrap(True)
        center_layout.addWidget(self.object_label)
        self.selection_meaning = QLabel()
        self.selection_meaning.setWordWrap(True)
        center_layout.addWidget(self.selection_meaning)
        self.return_editor = QPushButton('보관 중인 편집으로 돌아가기')
        self.return_editor.clicked.connect(self.return_to_editor)
        self.return_editor.hide()
        center_layout.addWidget(self.return_editor)
        self.editor_toggle = QPushButton('설정 접기')
        self.editor_toggle.setCheckable(True)
        self.editor_toggle.setChecked(True)
        self.editor_toggle.toggled.connect(self._toggle_editor)
        center_layout.addWidget(self.editor_toggle, 0, Qt.AlignmentFlag.AlignLeft)
        self.editor_area = QWidget()
        editor_layout = QVBoxLayout(self.editor_area)
        editor_layout.setContentsMargins(0, 0, 0, 0)
        self.tabs = QTabWidget()
        self.tabs.tabBar().hide()
        self._pages, self._forms, self.fields = {}, {}, {}
        for kind in ('comparison', 'filter', 'measurement'):
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            page = QWidget()
            form = QFormLayout(page)
            form.setFormAlignment(Qt.AlignmentFlag.AlignTop)
            form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
            scroll.setWidget(page)
            self._pages[kind], self._forms[kind] = page, form
            self.tabs.addTab(scroll, {'comparison': '결과 비교', 'filter': '필터', 'measurement': '측정'}[kind])
        self.tabs.currentChanged.connect(self._tab_changed)
        editor_layout.addWidget(self.tabs, 1)
        self.editor_area.setMaximumHeight(290)
        # Let the scroll editor yield height before the action rows collide.
        self.editor_area.setMinimumHeight(210)
        controls = QHBoxLayout()
        self.edit_button = QPushButton('초안 보관')
        self.edit_button.clicked.connect(self.store_draft)
        self.preview_button = QPushButton('미리보기')
        self.preview_button.clicked.connect(self.preview)
        self.apply_button = QPushButton('적용')
        self.apply_button.setProperty('appearanceRole', 'primary')
        self.apply_button.clicked.connect(lambda: self.object_command('post.apply'))
        self.reset_button = QPushButton('편집 되돌리기')
        self.reset_button.clicked.connect(self.reset_draft)
        for button in (self.edit_button, self.preview_button, self.apply_button, self.reset_button):
            controls.addWidget(button)
        editor_layout.addLayout(controls)
        center_layout.addWidget(self.editor_area)
        display_controls = QHBoxLayout()
        display_controls.addWidget(QLabel('ParaView 뷰'))
        self.view_selector = QComboBox()
        self.view_selector.setObjectName('postNativeView')
        self.view_selector.addItem('현재 객체의 뷰', None)
        display_controls.addWidget(self.view_selector, 1)
        self.show_applied_button = QPushButton('적용 결과 보기')
        self.show_applied_button.clicked.connect(self.show_comparison_result)
        self.comparison_display = QComboBox()
        for title, role in [('차이', 'B_minus_A'), ('변환 A', 'A_original'), ('변환 B', 'B_at_A'),
                            ('원 A 값', 'A_source_value'), ('대응 위치의 원 B 값', 'B_source_sampled'),
                            ('유효 영역', 'comparison_valid'), ('변화율', 'percent_change')]:
            self.comparison_display.addItem(title, role)
        display_controls.addWidget(self.comparison_display)
        display_controls.addWidget(self.show_applied_button)
        display_controls.addWidget(self.show_source_button)
        display_controls.addWidget(self.contact_button)
        center_layout.addLayout(display_controls)
        history = QHBoxLayout()
        edit_menu = self.menuBar().addMenu('편집(&E)')
        self.undo_button, self.redo_button = QAction('적용 취소', self), QAction('다시 적용', self)
        self.undo_button.triggered.connect(lambda: self.object_command('post.undo'))
        self.redo_button.triggered.connect(lambda: self.object_command('post.redo'))
        edit_menu.addActions([self.undo_button, self.redo_button])
        self.export_format = QComboBox()
        self.export_format.addItems(['vtu', 'csv', 'png'])
        self.export_button = QPushButton('결과 내보내기')
        self.export_button.clicked.connect(lambda: self.object_command('post.export', {'format': self.export_format.currentText()}))
        history.addWidget(self.repair_button)
        history.addWidget(self.changed_source_button)
        history.addWidget(self.inspect_button)
        self.source_tools = QWidget()
        self.source_tools.setLayout(history)
        center_layout.addWidget(self.source_tools)
        center_layout.addWidget(self.array_table, 1)
        center_layout.addWidget(self.array_description)
        self.array_controls = QWidget()
        array_controls = QHBoxLayout(self.array_controls)
        array_controls.setContentsMargins(0, 0, 0, 0)
        array_controls.addWidget(QLabel('표시 성분'))
        self.array_component = QComboBox()
        self.array_component.setAccessibleName('선택 필드의 실제 성분')
        array_controls.addWidget(self.array_component, 1)
        self.select_array_button = QPushButton('선택 성분 보기')
        self.select_array_button.clicked.connect(self.show_selected_array)
        array_controls.addWidget(self.select_array_button)
        self.measure_array_button = QPushButton('이 필드 측정…')
        self.measure_array_button.setToolTip('점 필드의 전체 성분을 보존하는 측정 초안을 만듭니다. 선택과 계산은 자동 실행하지 않습니다.')
        self.measure_array_button.clicked.connect(self.measure_selected_array)
        array_controls.addWidget(self.measure_array_button)
        center_layout.addWidget(self.array_controls)
        self.progress = QLabel('요청 대기 중')
        self.progress.setWordWrap(True)
        self.statusBar().addWidget(self.progress, 1)
        self.retry_button = QPushButton('같은 요청 다시 확인')
        self.retry_button.clicked.connect(self.recover_request)
        self.statusBar().addPermanentWidget(self.retry_button)
        sample_controls = QFormLayout()
        self.sample_preview = QCheckBox('적용 전 미리보기 값 읽기')
        self.sample_preview.setChecked(True)
        sample_controls.addRow(self.sample_preview)
        self.offset = QSpinBox()
        self.offset.setRange(0, 2_000_000_000)
        self.limit = QSpinBox()
        self.limit.setRange(1, 1000)
        self.limit.setValue(100)
        self.point_index = QLineEdit()
        self.point_index.setPlaceholderText('비워 두면 표 구간 읽기')
        sample_controls.addRow('시작 행', self.offset)
        sample_controls.addRow('읽을 행 수', self.limit)
        sample_controls.addRow('원본 절점 번호', self.point_index)
        sample_options = QWidget()
        sample_options.setLayout(sample_controls)
        sample_options.hide()
        self.sample_controls = sample_options
        self.read_options = QPushButton('조회 범위')
        self.read_options.setCheckable(True)
        self.read_options.toggled.connect(sample_options.setVisible)
        self.sample_button = QPushButton('측정값 읽기')
        self.sample_button.clicked.connect(self.read_samples)
        self.comparison_curve_button = QPushButton('비교 곡선…')
        self.comparison_curve_button.clicked.connect(self.show_comparison_curve)
        sample_row = QHBoxLayout()
        for widget in (self.sample_button, self.read_options, self.comparison_curve_button):
            sample_row.addWidget(widget)
        sample_row.addStretch()
        sample_row.addWidget(self.export_format)
        sample_row.addWidget(self.export_button)
        sample_row.addWidget(self.numerical_button)
        self.sample_tools = QWidget()
        self.sample_tools.setLayout(sample_row)
        center_layout.addWidget(self.sample_tools)
        center_layout.addWidget(sample_options)
        self.sample_context = QLabel('아직 읽은 값이 없습니다.')
        self.sample_context.setWordWrap(True)
        center_layout.addWidget(self.sample_context)
        self.samples = QTableWidget(0, 0)
        self.samples.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.samples.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.samples.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.samples.itemSelectionChanged.connect(self._sample_selected)
        self.samples.setAlternatingRowColors(True)
        self.samples.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.samples.horizontalHeader().setStretchLastSection(True)
        center_layout.addWidget(self.samples, 1)
        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setMaximumHeight(280)
        self.details.hide()
        view_menu = self.menuBar().addMenu('보기(&V)')
        self.details_action = view_menu.addAction('기술 상세')
        self.details_action.setCheckable(True)
        self.details_action.toggled.connect(self.details.setVisible)
        center_layout.addWidget(self.details)
        split.addWidget(center)
        split.setSizes([260, 1180])
        self.setCentralWidget(root)
        self._arrange_desktop(toolbar)
        self._populate_editor()
        self._update_actions()

    def _arrange_desktop(self, toolbar):
        """Model tree / selected Settings / Graphics / lower Tables and Messages.

        Native 3D remains in the existing ParaView process. Every action below
        delegates to the original command and its owner/draft guards.
        """
        from .post_result_plot import ResultPlot
        old = self.takeCentralWidget()
        root = QWidget()
        outer = QVBoxLayout(root)
        outer.setContentsMargins(4, 4, 4, 4)
        self.desktop_split = QSplitter(Qt.Orientation.Horizontal)
        outer.addWidget(self.desktop_split, 1)
        model = QWidget()
        model_layout = QVBoxLayout(model)
        model_layout.setContentsMargins(0, 0, 0, 0)
        self.identity.setWordWrap(True)
        model_layout.addWidget(self.identity)
        self.tree.setHeaderLabels(['모델 / 결과', '상태'])
        self.tree.setColumnWidth(0, 140)
        self.tree.setIndentation(12)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._tree_menu)
        self.tree.itemDoubleClicked.connect(lambda *_: self.open_native_source() if self._tree_selection and self._tree_selection[0] == 'source' else self.edit_selected())
        model_layout.addWidget(self.tree, 1)
        self.desktop_split.addWidget(model)

        self.settings_panel = QWidget()
        settings = QVBoxLayout(self.settings_panel)
        settings.setContentsMargins(4, 0, 4, 0)
        heading = QLabel('설정')
        heading.setProperty('appearanceRole', 'section')
        settings.addWidget(heading)
        settings.addWidget(self.object_label)
        settings.addWidget(self.return_editor)
        self.selection_meaning.setVisible(False)
        self.editor_toggle.setText('설정 접기' if self.editor_toggle.isChecked() else '설정 편집')
        settings.addWidget(self.editor_toggle, 0, Qt.AlignmentFlag.AlignLeft)
        self.editor_area.setMaximumHeight(16777215)
        self.editor_area.setMinimumHeight(0)
        settings.addWidget(self.editor_area, 1)
        for form in self._forms.values():
            form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)
        # Source properties and field inspection are contextual Settings.
        self.source_settings = QWidget()
        source_layout = QVBoxLayout(self.source_settings)
        source_layout.setContentsMargins(0, 0, 0, 0)
        source_layout.addWidget(self.array_table, 1)
        source_layout.addWidget(self.array_description)
        source_layout.addWidget(self.array_controls)
        settings.addWidget(self.source_settings, 1)
        self.desktop_split.addWidget(self.settings_panel)

        results = QSplitter(Qt.Orientation.Vertical)
        graphics = QWidget()
        graphics_layout = QVBoxLayout(graphics)
        graphics_layout.setContentsMargins(0, 0, 0, 0)
        title = QLabel('그래픽 / 측정 결과')
        title.setProperty('appearanceRole', 'section')
        graphics_layout.addWidget(title)
        self.graphics_toolbar = QToolBar('그래픽')
        self.graphics_toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        graphics_layout.addWidget(self.graphics_toolbar)
        self.result_plot = ResultPlot(self)
        self.result_plot.rowSelected.connect(self.samples.selectRow)
        graphics_layout.addWidget(self.result_plot, 1)
        self.sample_context.setMaximumHeight(85)
        graphics_layout.addWidget(self.sample_context)
        results.addWidget(graphics)
        self.output_tabs = QTabWidget()
        self.output_tabs.setObjectName('postOutputTabs')
        table_page = QWidget()
        table_layout = QVBoxLayout(table_page)
        table_layout.setContentsMargins(0, 0, 0, 0)
        table_layout.addWidget(self.samples, 1)
        table_layout.addWidget(self.sample_controls)
        self.output_tabs.addTab(table_page, '표')
        messages = QWidget()
        messages_layout = QVBoxLayout(messages)
        self.message.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        messages_layout.addWidget(self.message)
        messages_layout.addStretch()
        self.output_tabs.addTab(messages, '메시지')
        self.details.setMaximumHeight(16777215)
        self.details.show()
        self.output_tabs.addTab(self.details, '기술 상세')
        results.addWidget(self.output_tabs)
        results.setSizes([540, 210])
        self.desktop_split.addWidget(results)
        model.setMinimumWidth(160)
        self.settings_panel.setMinimumWidth(280)
        self.desktop_split.setStretchFactor(0, 0)
        self.desktop_split.setStretchFactor(1, 0)
        self.desktop_split.setStretchFactor(2, 1)
        self.desktop_split.setSizes([215, 330, 870])
        self.setCentralWidget(root)
        old.hide()
        # Old button objects retain the single command/enabled implementation;
        # actions share those exact slots rather than duplicating operations.
        for widget in (self.edit_button, self.preview_button, self.apply_button, self.reset_button,
                       self.source_tools, self.sample_tools, self.add_source_button,
                       self.show_source_button, self.show_applied_button, self.contact_button,
                       self.comparison_display, self.view_selector, self.handoff_retry, self.refresh_button):
            widget.setParent(self)
            widget.hide()
        for action in self.new_buttons:
            action.setParent(self)
        self.menuBar().clear()
        self.handoff_retry.setParent(self); self.handoff_retry.hide()
        toolbar.clear()
        toolbar.setWindowTitle('빠른 실행')
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        style = self.style()
        self.open_action.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_DialogOpenButton))
        self.save_action.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton))
        self._command_actions = []
        def command(text, button, icon, shortcut=None):
            action = QAction(style.standardIcon(icon), text, self)
            action.setToolTip(text + (f' ({shortcut})' if shortcut else ''))
            if shortcut:
                action.setShortcut(QKeySequence(shortcut))
            action.triggered.connect(button.click)
            self._command_actions.append((action, button))
            return action
        self.refresh_action = command('새로고침', self.refresh_button, QStyle.StandardPixmap.SP_BrowserReload, 'F5')
        self.add_source_action = command('결과 파일 추가…', self.add_source_button, QStyle.StandardPixmap.SP_FileDialogNewFolder)
        self.preview_action = command('미리보기', self.preview_button, QStyle.StandardPixmap.SP_FileDialogContentsView, 'F6')
        self.apply_action = command('적용', self.apply_button, QStyle.StandardPixmap.SP_DialogApplyButton, 'F7')
        self.keep_action = command('초안 보관', self.edit_button, QStyle.StandardPixmap.SP_DialogSaveButton)
        self.reset_action = command('편집 되돌리기', self.reset_button, QStyle.StandardPixmap.SP_DialogResetButton)
        self.read_action = command('측정값 읽기', self.sample_button, QStyle.StandardPixmap.SP_FileDialogDetailedView, 'F8')
        self.export_action = command('결과 내보내기…', self.export_button, QStyle.StandardPixmap.SP_DialogSaveButton)
        self.numerical_action = command('Numerical로 보내기…', self.numerical_button, QStyle.StandardPixmap.SP_ArrowRight)
        self.contact_action = command('접촉 결과…', self.contact_button, QStyle.StandardPixmap.SP_FileDialogInfoView)
        self.show_result_action = command('ParaView에서 적용 결과 보기', self.show_applied_button, QStyle.StandardPixmap.SP_DesktopIcon)
        self.edit_action = QAction(style.standardIcon(QStyle.StandardPixmap.SP_FileDialogDetailedView), '설정 편집', self)
        self.edit_action.setShortcut(QKeySequence('Alt+Return'))
        self.edit_action.triggered.connect(self.edit_selected)
        self.native_action = QAction(style.standardIcon(QStyle.StandardPixmap.SP_DesktopIcon), 'ParaView로 이동', self)
        self.native_action.setToolTip('원 결과를 실제 ParaView 창에 표시합니다. 점 선택 도구는 ParaView에서 사용하세요. (F4)')
        self.native_action.setShortcut(QKeySequence('F4'))
        self.native_action.triggered.connect(self.open_native_source)
        self.new_gauge_action = QAction(style.standardIcon(QStyle.StandardPixmap.SP_FileIcon), '두 점 상대변위…', self)
        self.new_gauge_action.triggered.connect(self.new_gauge)
        self.new_buttons.append(self.new_gauge_action)
        file_menu = self.menuBar().addMenu('파일(&F)')
        file_menu.addActions([self.open_action, self.add_source_action, self.save_action])
        edit_menu = self.menuBar().addMenu('편집(&E)')
        edit_menu.addActions([self.edit_action, self.keep_action, self.reset_action, self.undo_button, self.redo_button])
        self.analysis_menu = self.menuBar().addMenu('분석(&A)')
        self.analysis_menu.addActions(self.new_buttons)
        measurement_menu = self.analysis_menu.addMenu('측정 추가')
        for kind, label in [('point', '점'), ('path', '경로'), ('time', '원본 점 시간 이력'),
                            ('gauge_time', '두 점 상대변위 시간 이력'), ('surface_average', '면 평균'), ('surface_time', '면 평균 시간 이력')]:
            action = measurement_menu.addAction(label + '…')
            action.triggered.connect(lambda checked=False, kind=kind: self.new_measurement_type(kind))
            self.new_buttons.append(action)
        self.analysis_menu.addSeparator()
        self.analysis_menu.addActions([self.preview_action, self.apply_action])
        self.results_menu = self.menuBar().addMenu('결과(&R)')
        self.results_menu.addActions([self.native_action, self.show_result_action, self.read_action, self.contact_action])
        self.results_menu.addAction(command('비교 곡선…', self.comparison_curve_button, QStyle.StandardPixmap.SP_FileDialogContentsView))
        export_menu = self.results_menu.addMenu('내보내기')
        for fmt in ('vtu', 'csv', 'png'):
            action = export_menu.addAction(fmt.upper(), lambda checked=False, fmt=fmt: self._export_format(fmt))
            self._command_actions.append((action, self.export_button))
        self.results_menu.addAction(self.numerical_action)
        view_menu = self.menuBar().addMenu('보기(&V)')
        view_menu.addAction(self.refresh_action)
        view_menu.addAction('설정', self.edit_selected)
        self._desktop_view_menu = view_menu
        view_menu.addAction('표', lambda: self.output_tabs.setCurrentIndex(0))
        view_menu.addAction('메시지', lambda: self.output_tabs.setCurrentIndex(1))
        view_menu.addAction('기술 상세', lambda: self.output_tabs.setCurrentIndex(2))
        self.results_menu.addAction('조회 범위…', self.read_options.toggle)
        self.inspect_action = command('필드 정보 읽기', self.inspect_button, QStyle.StandardPixmap.SP_FileDialogInfoView)
        self.results_menu.addAction(self.inspect_action)
        file_menu.addSeparator()
        file_menu.addAction(command('원파일 다시 연결…', self.repair_button, QStyle.StandardPixmap.SP_DialogOpenButton))
        file_menu.addAction(command('변경 자료로 새 프로젝트…', self.changed_source_button, QStyle.StandardPixmap.SP_FileIcon))
        toolbar.addActions([self.open_action, self.save_action])
        toolbar.addSeparator()
        toolbar.addAction(self.new_gauge_action)
        toolbar.addAction(self.native_action)
        toolbar.addSeparator()
        toolbar.addActions([self.preview_action, self.apply_action])
        toolbar.addWidget(self.handoff_retry)
        self.graphics_toolbar.addActions([self.native_action, self.read_action])
        self.graphics_toolbar.addSeparator()
        self.graphics_toolbar.addAction(self.numerical_action)
        self.graphics_toolbar.addWidget(self.comparison_display)
        self.graphics_toolbar.addWidget(self.view_selector)
        self.view_selector.setMinimumWidth(100)
        self.view_selector.setMaximumWidth(180)
        self.view_selector.show()
        self._desktop_ready = True
        self.preview_button.clicked.disconnect()
        self.preview_button.clicked.connect(self.preview_result)
        self.apply_button.clicked.disconnect()
        self.apply_button.clicked.connect(self.apply_result)
        self._compact_desktop(toolbar)

    def _compact_desktop(self, toolbar):
        """Nonmodal analysis settings beside the actual ParaView main window."""
        old = self.takeCentralWidget()
        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(4)
        self.compact_split = QSplitter(Qt.Orientation.Vertical)
        layout.addWidget(self.compact_split, 1)
        model = QWidget()
        model_layout = QVBoxLayout(model)
        model_layout.setContentsMargins(0, 0, 0, 0)
        self.identity.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.identity.setMinimumWidth(0)
        model_layout.addWidget(self.identity)
        self.tree.setMinimumSize(0, 80)
        self.tree.setColumnWidth(0, 260)
        model_layout.addWidget(self.tree, 1)
        self.compact_split.addWidget(model)
        selected = QWidget()
        selected_layout = QVBoxLayout(selected)
        selected_layout.setContentsMargins(0, 0, 0, 0)
        selected_layout.setSpacing(4)
        self.object_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.object_label.setMinimumWidth(0)
        selected_layout.addWidget(self.object_label)
        self.compact_state = QLabel()
        selected_layout.addWidget(self.compact_state)
        self.selected_toolbar = QToolBar('선택 분석')
        self.selected_toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.selected_toolbar.addActions([self.preview_action, self.apply_action])
        self.selected_toolbar.addAction(self.keep_action)
        self.apply_action.setShortcuts([QKeySequence('F7'), QKeySequence('Ctrl+Return')])
        self.apply_action.setToolTip('검증한 현재 초안을 적용합니다. F7 / Ctrl+Enter')
        selected_layout.addWidget(self.selected_toolbar)
        self.work_tabs = QTabWidget()
        self.work_tabs.setObjectName('postCompactWork')
        settings = QWidget()
        settings_layout = QVBoxLayout(settings)
        settings_layout.setContentsMargins(0, 0, 0, 0)
        settings_layout.setSpacing(3)
        self.compact_required = QLabel()
        self.compact_required.setWordWrap(True)
        settings_layout.addWidget(self.compact_required)
        settings_layout.addWidget(self.return_editor)
        settings_layout.addWidget(self.editor_area, 1)
        settings_layout.addWidget(self.source_settings, 1)
        self.work_tabs.addTab(settings, '설정')
        self._compact_settings_widget = settings
        result = QWidget()
        result_layout = QVBoxLayout(result)
        result_layout.setContentsMargins(0, 0, 0, 0)
        result_layout.setSpacing(4)
        result_controls = QToolBar('선택 결과')
        result_controls.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        result_controls.addActions([self.show_result_action, self.numerical_action])
        result_layout.addWidget(result_controls)
        native_options = QHBoxLayout()
        native_options.addWidget(self.view_selector, 1)
        native_options.addWidget(self.comparison_display, 1)
        result_layout.addLayout(native_options)
        self.view_selector.setMaximumWidth(16777215)
        self.view_selector.setMinimumWidth(0)
        result_layout.addWidget(self.handoff_retry)
        result_layout.addWidget(self.sample_context)
        self.sample_context.setMaximumHeight(48)
        raw, messages, details = [self.output_tabs.widget(i) for i in range(3)]
        self._compact_messages = messages
        for widget in (raw, messages, details): widget.setParent(self)
        self.output_tabs.clear()
        summary = QWidget()
        summary_layout = QVBoxLayout(summary)
        summary_layout.setContentsMargins(0, 0, 0, 0)
        self.compact_value = QLabel('아직 읽은 결과가 없습니다.')
        self.compact_value.setProperty('appearanceRole', 'section')
        self.compact_value.setWordWrap(True)
        summary_layout.addWidget(self.compact_value)
        self.compact_table = QTableWidget(0, 3)
        self.compact_table.setObjectName('postCompactValues')
        self.compact_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.compact_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.compact_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.compact_table.verticalHeader().hide()
        self.compact_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.compact_table.itemSelectionChanged.connect(self._compact_result_selected)
        summary_layout.addWidget(self.compact_table, 1)
        self.output_tabs.addTab(summary, '요약')
        self._compact_summary = summary
        self.output_tabs.addTab(raw, '원표')
        self.output_tabs.addTab(self.result_plot, '곡선')
        self.output_tabs.addTab(messages, '메시지')
        self.output_tabs.addTab(details, '상세')
        result_layout.addWidget(self.output_tabs, 1)
        self.work_tabs.addTab(result, '결과')
        selected_layout.addWidget(self.work_tabs, 1)
        self.compact_notice = QLabel()
        self.message.textChanged.connect(self.compact_notice.setText)
        self.message.textChanged.connect(self.compact_notice.setToolTip)
        self.compact_notice.setWordWrap(True)
        self.compact_notice.setMaximumHeight(74)
        selected_layout.addWidget(self.compact_notice)
        self.compact_split.addWidget(selected)
        self.compact_split.setSizes([210, 610])
        self.compact_split.setStretchFactor(0, 0)
        self.compact_split.setStretchFactor(1, 1)
        self.setCentralWidget(root)
        old.hide()
        self.editor_toggle.setParent(self); self.editor_toggle.hide()
        self.graphics_toolbar.setParent(self); self.graphics_toolbar.hide()
        self.settings_panel.setParent(self); self.settings_panel.hide()
        self.result_plot.setMinimumWidth(0)
        self.result_plot.canvas.setMinimumSize(0, 180)
        self.source_settings.setMinimumWidth(0)
        controls = self.array_controls.layout()
        while controls.count():
            item = controls.takeAt(0)
            if item.widget() not in (self.array_component, self.select_array_button, self.measure_array_button) and item.widget():
                item.widget().deleteLater()
        source_commands = QVBoxLayout()
        component_row = QHBoxLayout()
        component_row.addWidget(QLabel('표시 성분'))
        self.array_component.setMinimumWidth(0)
        self.array_component.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        component_row.addWidget(self.array_component, 1)
        source_commands.addLayout(component_row)
        buttons = QHBoxLayout()
        buttons.addWidget(self.select_array_button)
        buttons.addWidget(self.measure_array_button)
        source_commands.addLayout(buttons)
        controls.addLayout(source_commands)
        for column in range(1, self.array_table.columnCount()):
            self.array_table.setColumnHidden(column, True)
        toolbar.clear()
        toolbar.addAction(self.save_action)
        add = QToolButton()
        add.setText('분석 추가')
        add.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogNewFolder))
        add.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        add.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(add); menu.addActions(self.new_buttons); add.setMenu(menu)
        toolbar.addWidget(add)
        toolbar.addAction(self.native_action)
        self.native_action.setText('ParaView로 이동')
        self.show_result_action.setText('ParaView 결과')
        self.numerical_action.setText('수치 연구로…')
        view_menu = self._desktop_view_menu
        view_menu.clear()
        view_menu.addAction(self.refresh_action)
        view_menu.addAction('선택 설정', lambda: self.work_tabs.setCurrentIndex(0))
        for text, widget in [('결과 요약', summary), ('원표', raw), ('곡선', self.result_plot), ('메시지', messages), ('기술 상세', details)]:
            view_menu.addAction(text, lambda checked=False, widget=widget: self._compact_show_result(widget))
        self._compact_ready = True
        self._settings_page_index = 0
        self.progress.setMinimumWidth(0)
        self.progress.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.retry_button.setText('요청 재확인')
        self.retry_button.setToolTip('결과가 미확인인 같은 요청의 상태를 다시 확인합니다.')
        self.compact_notice.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        for action in self.results_menu.actions():
            if action.text() == '조회 범위…':
                action.triggered.disconnect()
                action.triggered.connect(self._compact_read_options)

    def _compact_read_options(self):
        self.read_options.toggle()
        self._compact_show_result(self.output_tabs.widget(1))

    def _compact_update(self, browsing, obj, idle):
        if not getattr(self, '_compact_ready', False):
            return
        self.editor_toggle.hide()
        self.editor_area.setVisible(not browsing)
        self.return_editor.setText('편집 중인 분석으로 돌아가기')
        self.compact_state.setText('원 결과 선택' if browsing else
            '편집 중 · 미보관' if self.local_dirty else self._analysis_state(obj) if obj else '새 분석')
        if self._samples is None:
            self.compact_table.setRowCount(0)
            self.compact_value.setText('아직 읽은 결과가 없습니다.')
        self.compact_notice.setText(self.message.text())
        self.compact_notice.setToolTip(self.message.text())
        self.selected_toolbar.setVisible(not browsing)
        self.compact_required.setVisible(not browsing)
        self.work_tabs.setTabEnabled(1, not browsing)
        if browsing:
            self.work_tabs.setCurrentIndex(0)
        draft = self.edited_draft()
        if self._kind == 'measurement' and draft.get('measurement') in MEASUREMENT_FIELDS:
            measurement = draft['measurement']
            required = ['source_ref', 'array', 'units', 'measure', 'frame', 'coordinate_units', 'coordinate_frame']
            if measurement in ('gauge', 'gauge_time'):
                required += ['point_indices', 'point1', 'point2', 'direction', 'basis', 'coordinate_configuration']
            elif measurement in ('surface_average', 'surface_time'):
                required += ['surface_faces', 'geometry']
                if draft.get('component') is not None: required += ['basis']
                if draft.get('component') == 'projection': required += ['direction']
            if measurement in ('surface_time', 'gauge_time'):
                required += ['time_range', 'reference_time', 'time_units', 'time_origin']
            elif measurement == 'time' or draft.get('time') is not None:
                required += ['time_units', 'time_origin']
            missing = [[] for _ in range(4)]
            for key in required:
                value = draft.get(key)
                if value is None or value == '' or value == []:
                    label = {'surface_faces':'원본 경계 면', 'point1':'A 기준 좌표', 'point2':'B 기준 좌표'}.get(key, LABELS.get(key, key))
                    missing[self.settings_pages.page_for(key, measurement)].append(label)
            self.settings_pages.missing(missing)
            for key, label in [('point1','A 기준 좌표'),('point2','B 기준 좌표')]:
                if (key,) in self._compact_field_labels:
                    self._compact_field_labels[(key,)].setText(label + ' [' + str(draft.get('coordinate_units') or '단위 미지정') + ']')
            needed = [name for page in missing for name in page]
            self.compact_required.setText('미결정: ' + ', '.join(needed[:3]) + (' 외 ' + str(len(needed)-3) + '개' if len(needed)>3 else '') if needed else '필수 선언 입력됨 · 미리보기로 검증하세요.')
            self.compact_required.setToolTip('미결정: ' + ', '.join(needed) if needed else '입력 여부만 표시합니다. 수치·선택·단위의 유효성은 기존 미리보기에서 검증합니다.')
            if measurement in ('surface_average','surface_time'):
                self._compact_field_labels[('direction',)].setVisible(draft.get('component') == 'projection')
        else:
            self.compact_required.clear()
        if self._sample_basis:
            full = self.sample_context.text()
            state = '이전 조회 · 다시 읽기 필요' if full.startswith('이전 조회') else '최근 조회 실패 · 이전 값' if full.startswith('최근 조회 실패') else '미리보기' if self._sample_basis['preview'] else '적용 결과'
            self.sample_context.setText(self._sample_basis['title'] + ' · ' + state)
            self.sample_context.setToolTip(full)

    def _compact_samples(self, payload, recipe):
        rows = payload.get('rows', [])[:1000]
        summary = payload.get('summary') or {}
        measurement = recipe.get('measurement')
        primary = {'surface_average':'SurfaceAreaAverage', 'surface_time':'SurfaceAreaAverage',
                   'gauge':'GaugeRelativeDisplacement', 'gauge_time':'GaugeRelativeDisplacement'}.get(measurement)
        if primary is None:
            self.compact_table.setRowCount(0)
            self.compact_value.setText('측정한 원래 값과 성분은 원표에서 확인하세요.')
            self._compact_show_result(self.output_tabs.widget(1))
            return
        title = {'SurfaceAreaAverage':'면 평균', 'GaugeRelativeDisplacement':'두 점 상대변위'}.get(primary, '측정 결과')
        unit = summary.get('units') or recipe.get('units') or '단위 미지정'
        blocker = QSignalBlocker(self.compact_table)
        self.compact_table.setRowCount(len(rows))
        history = measurement in ('surface_time','gauge_time','time')
        self.compact_table.setHorizontalHeaderLabels(['시각 [' + str(recipe.get('time_units') or '?') + ']' if history else '물리량', '값 [' + str(unit) + ']', '유효성'])
        valid_count = 0
        for index, row in enumerate(rows):
            values = row.get('values', {})
            value = values.get(primary) if primary else None
            validity = row.get('validity', {}).get(primary, 'valid')
            valid = (type(value) in (int, float) and math.isfinite(value) and row.get('valid', True) is not False
                     and values.get('vtkValidMask', 1) != 0 and validity in ('valid', True))
            valid_count += int(valid)
            # Display rounding only; payload, raw table and native provenance keep full values.
            text_value = format(value, '.8g') if type(value) in (int, float) else '값 없음' if value is None else display(value)
            texts = [display(values.get('Time')) if history else title, text_value, '유효' if valid else '무효 / 결측']
            for col, text in enumerate(texts):
                item = QTableWidgetItem(text)
                item.setToolTip('원본 행 ' + str(row.get('row', row.get('point_index', index))) + '\n' + display(row))
                self.compact_table.setItem(index, col, item)
        if len(rows) == 1:
            clock = rows[0].get('values', {}).get('Time') if history else recipe.get('time')
            stamp = '시각 정보 없음' if clock is None else '시각 ' + str(clock) + ' ' + str(recipe.get('time_units') or '단위 미지정')
            value = self.compact_table.item(0, 1).text()
            self.compact_value.setText(title + ': ' + value + ' ' + str(unit) + '\n' + stamp + ' · ' + ('유효' if valid_count else '무효 / 결측'))
        else:
            self.compact_value.setText(title + ' · ' + str(len(rows)) + '개 표본\n유효 ' + str(valid_count) + ' / 결측·무효 ' + str(len(rows)-valid_count))
        if summary.get('quadrature'):
            self.compact_value.setText(self.compact_value.text() + '\n고차 형상 적분 · 두 적분 규칙의 차이는 원표에서 확인 (오차 한계 미확정)')
        blocker.unblock()
        self._compact_show_result(self._compact_summary)

    def _compact_show_result(self, widget):
        self.work_tabs.setCurrentIndex(1)
        self.output_tabs.setCurrentWidget(widget)

    def _compact_result_selected(self):
        selected = self.compact_table.selectionModel().selectedRows()
        if selected and self._samples:
            self.samples.selectRow(selected[0].row())

    def capture_new_measurement(self):
        if self.local_dirty and self._object_ref:
            self.message.setText('현재 측정 편집을 초안으로 보관하거나 되돌린 뒤, 선택으로 새 측정을 추가하세요.')
            self.compact_notice.setText(self.message.text())
            return False
        return self.capture_selection()

    def preview_result(self):
        def validate():
            def ready(_payload):
                self.sample_preview.setChecked(True)
                self.read_samples()
            self.queue_command('post.mapping_validate', {'object_ref': self._object_ref}, accepted=ready)
        if self.local_dirty or not self._object_ref:
            return self.store_draft(after=validate)
        return validate()

    def apply_result(self):
        def read(_payload):
            self.sample_preview.setChecked(False)
            self.read_samples()
        return self.object_command('post.apply', after=read)

    def edit_selected(self):
        if self._busy or self._pending:
            return False
        self.editor_toggle.setChecked(True)
        self.return_to_editor() if self._tree_selection and self._tree_selection[0] == 'source' and self.local_dirty else self._update_actions()
        self.tabs.setFocus()
        self.work_tabs.setCurrentIndex(0)
        return True

    def new_gauge(self):
        return self.new_measurement_type('gauge')

    def new_measurement_type(self, kind):
        if not self.new_object('measurement'):
            return False
        self._draft = {key: value for key, value in self._draft.items() if key in MEASUREMENT_FIELDS[kind]}
        self._draft['measurement'] = kind
        if kind in ('gauge', 'gauge_time'):
            self._draft['direction'] = []
        elif kind in ('surface_average', 'surface_time'):
            self._draft['direction'] = None
        self._populate_editor()
        return True

    def _export_format(self, fmt):
        self.export_format.setCurrentText(fmt)
        self.export_button.click()

    def _tree_menu(self, position):
        item = self.tree.itemAt(position)
        if item is None or not item.data(0, Qt.ItemDataRole.UserRole):
            return
        self.tree.setCurrentItem(item)
        if self.tree.currentItem() is not item:
            return
        menu = QMenu(self.tree)
        if self._tree_selection[0] == 'source':
            menu.addActions([self.native_action, self.new_gauge_action])
            menu.addAction(self.inspect_action)
        else:
            menu.addActions([self.edit_action, self.preview_action, self.apply_action, self.read_action,
                             self.native_action, self.numerical_action])
        menu.exec(self.tree.viewport().mapToGlobal(position))

    def open_native_source(self):
        draft = self.edited_draft()
        ref = self._source_ref if self._tree_selection and self._tree_selection[0] == 'source' else draft.get('source_ref')
        if not ref or ref not in {source['source_ref'] for source in self._sources()}:
            self.message.setText('모델 트리에서 원 결과를 선택하세요.')
            return False
        view = self._view_arguments(source=True, source_ref=ref)
        if view is None:
            return False
        def shown(_payload):
            if 'document.activate' in (self.document or {}).get('capabilities', []):
                self.queue_command('document.activate', {})
        return self.queue_command('post.source_select', {'source_ref': ref, 'show': True, **view}, accepted=shown)

    def _toggle_editor(self, opened):
        self.editor_area.setVisible(opened)
        self.editor_toggle.setText('설정 접기' if opened else '설정 편집')

    def return_to_editor(self):
        self._tree_selection = ('object', self._object_ref) if self._object_ref else None
        self._restore_tree_selection()
        self._update_actions()

    def _restore_tree_selection(self):
        self.tree.blockSignals(True)
        self.tree.setCurrentItem(None)
        for root_index in range(self.tree.topLevelItemCount()):
            group = self.tree.topLevelItem(root_index)
            for index in range(group.childCount()):
                item = group.child(index)
                if item.data(0, Qt.ItemDataRole.UserRole) == self._tree_selection:
                    self.tree.setCurrentItem(item)
        self.tree.blockSignals(False)

    def _analysis(self, document=None):
        return (document or self.document or {}).get('state', {}).get('analysis', {})

    @staticmethod
    def source_title(source):
        label = source.get('label') or source.get('reader_name') or '원 결과'
        generated = re.fullmatch(r'Result \| (.+) \| [0-9a-f]{8}', label)
        return generated.group(1) if generated else label

    def _recipe_meaning(self, draft):
        if not isinstance(draft, dict):
            return '저장된 설정을 확인하세요.'
        def original(ref):
            source = next((row for row in self._sources() if row['source_ref'] == ref), None)
            obj = next((row for row in self._objects() if row['id'] == ref), None)
            return self.source_title(source) if source else obj.get('title', '저장 측정') if obj else '원 자료 미지정' if not ref else '다시 연결할 원 자료'
        def field_meaning(values):
            if not isinstance(values, dict):
                return '형식이 맞지 않은 설정입니다. 기술 상세에서 원문을 확인하세요.'
            time = ('시각 범위 ' + field_text(values.get('time_range')) + ' [' + str(values.get('time_units') or '?') + ']' if values.get('measurement') in ('gauge_time', 'surface_time') else '저장 시각의 이력' if values.get('measurement') == 'time' else
                    '시각 미지정' if values.get('time') is None else
                    '시각 ' + str(values['time']) + ' [' + str(values.get('time_units') or '단위 미지정') + ']')
            location = ('점 번호 ' + field_text(values['point_indices']) if values.get('point_indices') else
                        '선 ' + field_text(values.get('point1')) + ' → ' + field_text(values.get('point2'))
                        if values.get('measurement') == 'path' else str(values.get('association') or '위치 미지정'))
            return (original(values.get('source_ref')) + ': ' + str(values.get('array') or '필드 미지정') +
                    ' [' + str(values.get('units') or '단위 미지정') + '], ' + location + ', ' + time +
                    ', ' + str(values.get('frame') or '좌표계 미지정'))
        if draft.get('measurement') in ('surface_average', 'surface_time'):
            component = draft.get('component')
            response = '스칼라' if component is None else '방향 ' + field_text(draft.get('direction')) if component == 'projection' else str(component) + '번 성분'
            clock = ('시각 범위 ' + field_text(draft.get('time_range')) if draft['measurement'] == 'surface_time' else
                     '시각 정보 없음' if draft.get('time') is None else '시각 ' + str(draft['time']))
            return (original(draft.get('source_ref')) + ': ' + str(draft.get('array') or '필드 미지정') +
                ' / 경계 면 ' + str(len(draft.get('surface_faces') or [])) + '개 / ' + response +
                ' [' + str(draft.get('units') or '단위 미지정') + ']\n' + clock +
                ' [' + str(draft.get('time_units') or '?') + '] / 고정 기준 면적')
        if draft.get('measurement') == 'contact_force':
            component = draft.get('component', 0)
            axis = 'XYZ'[component] if isinstance(component, int) and 0 <= component < 3 else str(component)
            resultant = draft.get('resultant') or {}
            physical = '기준점 모멘트' if resultant.get('response') == 'moment' else '합력'
            frame = resultant.get('frame_label') or draft.get('frame', '문서 전체')
            axis_name = draft.get('axis_name', 'load_parameter')
            axis_name = {'load_parameter': '정적 하중 계수 λ', 'time': '시간'}.get(axis_name, axis_name)
            return (original(draft.get('source_ref')) + ': ' + str(draft.get('quantity', '')) + ' ' + frame + ' ' + axis +
                    ' 성분, A 면의 ' + physical + ' [' + str(draft.get('units', 'N')) + ']. 축: ' +
                    str(axis_name) + ' [' + str(draft.get('axis_unit', '1')) + '].' +
                    (' 기준점 [mm]: ' + str(resultant['reference_point_mm']) if resultant.get('response') == 'moment' else ''))
        if draft.get('version') == 3:
            return ('기준: ' + original(draft.get('a', {}).get('source_ref')) +
                    ' / 비교: ' + original(draft.get('b', {}).get('source_ref')) +
                    '    B − A [' + str(draft.get('target_unit') or '단위 미지정') + ']')
        if draft.get('version') == 2:
            clock = draft.get('clock', {})
            stamp = '시각 없는 자료' if clock.get('value') is None else '비교 시각 ' + str(clock['value']) + ' [' + str(clock.get('unit') or '미지정') + ']'
            selection = {'scalar':'스칼라 값', 'magnitude':'크기'}.get(draft.get('selection'), str(draft.get('selection') or '성분 미지정').upper())
            difference = '|B − A|' if draft.get('difference') == 'norm_of_difference' else 'B − A'
            return selection + ' [' + str(draft.get('target', {}).get('units') or '단위 미지정') + ']   ' + difference + '   ' + stamp
        if 'a' in draft and 'b' in draft:
            return '\n'.join(side.upper() + ': ' + field_meaning(draft[side]) for side in ('a', 'b'))
        if 'filter' in draft:
            return original(draft.get('source_ref')) + ': ' + str(draft['filter'])
        return field_meaning(draft)

    @staticmethod
    def operation_label(operation):
        return {'document.save': '저장', 'post.sample': '측정값 조회', 'post.inspect': '필드 조회', 'post.select_array': '성분 표시',
                'post.mapping_validate': '미리보기', 'post.apply': '적용', 'post.show_analysis': '적용 결과 표시',
                'post.contact_inspect': '접촉 결과 조회', 'post.measurement_snapshot': '측정 확인',
                'post.measurement_capture': '원본 점 선택 가져오기',
                'post.export': '내보내기', 'post.undo': '적용 취소', 'post.redo': '다시 적용',
                'post.measurement_edit': '측정 초안 보관', 'post.filter_edit': '필터 초안 보관',
                'post.comparison_edit': '비교 초안 보관'}.get(operation, '후처리 작업')

    def _command_progress(self, command):
        operation = command.get('operation') or (self._pending or {}).get('request', {}).get('operation', '')
        state = command.get('state')
        self.progress.setText(self.operation_label(operation) + ': ' +
            {'SUCCEEDED': '완료', 'FAILED': '실패', 'CANCELLED': '취소됨', 'INTERRUPTED': '중단됨',
             'RUNNING': '처리 중', 'QUEUED': '대기 중'}.get(state, '확인 중'))
        self.progress.setToolTip(json.dumps(command, ensure_ascii=False))

    def _sources(self):
        return self._analysis().get('sources', [])

    def _objects(self):
        objects = self._analysis().get('objects', [])
        return list(objects.values()) if isinstance(objects, dict) else objects

    def _object(self, ref=None):
        return next((obj for obj in self._objects() if obj['id'] == (ref or self._object_ref)), None)

    def _context_token(self):
        return (self.document_id, self.session_id, self._source_ref, self._object_ref, self._kind)

    def _defer_callback(self, action):
        self._callback_calls.append((self._context_token(), action))
        return True

    def _drain_callbacks(self):
        while self._callback_calls and not self._busy and self._pending is None:
            token, action = self._callback_calls.pop(0)
            if token == self._context_token():
                action()
            else:
                self.message.setText('Owner or selected source changed; the earlier chooser continuation was not applied.')

    def _call(self, function, accepted, *, failed=None, relevant=None, background=False):
        if self._closed:
            return False
        if self._busy:
            if self._accepting and not background:
                return self._defer_callback(lambda: self._call(function, accepted, failed=failed, relevant=relevant))
            return False
        self._busy = True
        self._update_actions()
        worker = _Read(function)
        self._workers.append(worker)
        def finished(value, error):
            self._workers.remove(worker)
            if self._closed:
                self._busy = False
                return
            self._accepting = True
            try:
                if relevant is None or relevant():
                    if error:
                        self.message.setText('Request failed; draft retained. ' + error)
                        if failed:
                            failed(error)
                    else:
                        accepted(value)
            finally:
                self._accepting = False
                self._busy = False
            self._update_actions()
            self._drain_callbacks()
        worker.signals.finished.connect(finished, Qt.ConnectionType.QueuedConnection)
        QThreadPool.globalInstance().start(worker)
        return True

    def refresh_document(self, *, initial=False, explicit=False):
        if self._measurement_poll_pending is not None and not (initial or explicit):
            self._schedule_measurement_poll()
            return False
        if (self._busy and not (self._accepting and (initial or explicit))) or self._pending:
            return False
        identifier = self.document_id
        def accepted(document):
            if identifier != self.document_id:
                return
            if self.session_id is not None and document.get('session_id') != self.session_id:
                self.conflict = True
                self.message.setText('The exact native owner session changed. Choose the current owner explicitly; the local draft is retained.')
                return
            if self.document and document['generation'] != self.document['generation'] and self.local_dirty and not explicit:
                self.conflict = True
                self.message.setText('Native inputs changed while editing. Refresh owner explicitly to keep this draft against the current generation.')
                self._show_document(document, preserve_buffer=True)
                return
            if explicit:
                self.conflict = False
            self.session_id = document['session_id']
            self._show_document(document, preserve_buffer=self.local_dirty, initial=initial)
        return self._call(lambda: self.client.document_read(identifier), accepted, background=not (initial or explicit))

    def _show_document(self, document, *, preserve_buffer=False, initial=False):
        from .result_return import bind_receiver
        if not bind_receiver(self, document):
            if self.document is None:
                # Only this fresh duplicate is disposable; never close the existing editor.
                self._allow_close = True
                self.close()
            return False
        self.document = deepcopy(document)
        analysis = self._analysis()
        if initial and not self._object_ref:
            self._object_ref = analysis.get('active_object')
            self._tree_selection = ('object', self._object_ref) if self._object_ref else self._tree_selection
        self.tree.blockSignals(True)
        self.tree.clear()
        sources = QTreeWidgetItem(['원 결과', ''])
        objects = QTreeWidgetItem(['분석과 측정', ''])
        self.tree.addTopLevelItems([sources, objects])
        selected = None
        for record in self._sources():
            ref = record['source_ref']
            item = QTreeWidgetItem([self.source_title(record), '연결됨' if record.get('available') else '파일 필요'])
            item.setData(0, Qt.ItemDataRole.UserRole, ('source', ref))
            item.setToolTip(0, ref)
            sources.addChild(item)
            if self._tree_selection == ('source', ref):
                selected = item
        for obj in self._objects():
            item = QTreeWidgetItem([obj.get('title', obj['kind']), self._analysis_state(obj)])
            item.setData(0, Qt.ItemDataRole.UserRole, ('object', obj['id']))
            item.setToolTip(0, obj['id'])
            objects.addChild(item)
            if self._tree_selection == ('object', obj['id']):
                selected = item
        self.tree.expandAll()
        if selected:
            self.tree.setCurrentItem(selected)
        self.tree.blockSignals(False)
        obj = self._object()
        if obj and not preserve_buffer:
            self._kind, self._draft = obj['kind'], deepcopy(obj['draft'])
            self.local_dirty = False
            self._populate_editor()
        elif not preserve_buffer:
            self._populate_editor()
        self.identity.setText(document.get('title', '후처리 문서'))
        self.identity.setToolTip(f"{document['id']} / {document['session_id']} / generation {document['generation']}")
        if initial:
            self.editor_toggle.setChecked(not bool(obj and obj.get('position', -1) >= 0))
        self._populate_views()
        self.setWindowTitle(document.get('title', '문서') + ' — Post 분석 설정' + (' *' if self.local_dirty else ''))
        self._show_arrays()
        self._show_details()
        self._update_actions()
        return True

    def _tree_selected(self):
        if self._populating or self._pending or self._busy:
            return
        item = self.tree.currentItem()
        selected = item.data(0, Qt.ItemDataRole.UserRole) if item else None
        if not selected:
            return
        if self.local_dirty and selected[0] == 'object':
            self.message.setText('현재 편집을 초안으로 보관하거나 되돌린 뒤 다른 분석을 선택하세요.')
            self._restore_tree_selection()
            return
        self._tree_selection = selected
        kind, ref = selected
        if kind == 'source':
            self._source_ref = ref
            self._show_arrays()
        else:
            self._object_ref = ref
            obj = self._object()
            self._kind, self._draft = obj['kind'], deepcopy(obj['draft'])
            self._populate_editor()
            self._samples = None
            self._sample_basis = None
            self.result_plot.set_samples(None, None)
            self.samples.setRowCount(0)
            self.samples.setColumnCount(0)
        self._update_actions()
        self._show_details()

        self.work_tabs.setCurrentIndex(0)

    def _source_choice_metadata(self, ref):
        source = next((row for row in self._sources() if row['source_ref'] == ref), None)
        if source:
            return source.get('metadata') or source.get('native_metadata') or {}, source.get('native_metadata')
        obj = next((row for row in self._objects() if row['id'] == ref), None)
        if obj and obj.get('position', -1) >= 0:
            declared = obj.get('output_metadata')
            if declared:
                return declared, declared
        return {}, None

    def _form_field(self, form, key, value, path):
        if key == 'source_ref':
            field = QComboBox()
            field.setEditable(True)
            field.addItem('', '')
            for source in self._sources():
                field.addItem(self.source_title(source), source['source_ref'])
            for obj in self._objects():
                if obj.get('position', -1) >= 0:
                    field.addItem(obj.get('title', obj['kind']), obj['id'])
            index = field.findData(value)
            field.setCurrentIndex(index if index >= 0 else 0)
            if index < 0 and value:
                field.setEditText(str(value))
            field.currentIndexChanged.connect(lambda *_args, path=path: self._source_field_changed(path))
            field.lineEdit().textEdited.connect(self._edited)
        elif key == 'array':
            field = QComboBox()
            field.setEditable(True)
            side = self._draft.get(path[0], {}) if len(path) == 2 and path[0] in ('a', 'b') else self._draft
            metadata, _ = self._source_choice_metadata(side.get('source_ref'))
            arrays = metadata.get('arrays', [])
            field.addItem('')
            field.addItems(list(dict.fromkeys(row['name'] for row in arrays if isinstance(row, dict) and row.get('name'))))
            field.setCurrentText(field_text(value))
            field.currentTextChanged.connect(self._edited)
            if self._draft.get('measurement') in ('surface_average', 'surface_time'):
                field.activated.connect(lambda *_: self._source_field_changed(path))
                field.lineEdit().editingFinished.connect(lambda: self._source_field_changed(path))
        elif key in ('basis', 'coordinate_configuration', 'geometry', 'component') or (key == 'measure' and self._kind == 'measurement' and self._draft.get('measurement') in ('gauge', 'gauge_time')):
            field = QComboBox()
            field.addItem('미지정', None)
            if key == 'component':
                field.setItemText(0, '스칼라 필드 전체')
                metadata, native = self._source_choice_metadata(self._draft.get('source_ref'))
                declared = next((row for row in [*(native or {}).get('arrays', []), *metadata.get('arrays', [])] if row.get('name') == self._draft.get('array')
                    and row.get('association') == self._draft.get('association')), {})
                count = declared.get('components')
                names = declared.get('component_names') or []
                if type(count) is int and count > 1:
                    for number in range(count):
                        label = names[number] if len(names) == count and isinstance(names[number], str) and names[number] else str(number) + '번 원 성분'
                        field.addItem(label, number)
                if count == 3:
                    field.addItem('지정 방향으로 투영', 'projection')
            else:
                label, declared = {'basis': ('고정 직교 좌표계', 'fixed_cartesian'),
                               'coordinate_configuration': ('변형 전 기준 좌표', 'reference'),
                               'geometry': ('기준 시각의 고정 면적', 'fixed_reference'),
                               'measure': ('변위', 'displacement')}[key]
                field.addItem(label, declared)
            if value is not None and value != '' and field.findData(value) < 0:
                field.addItem('지원하지 않는 물리량' if key == 'measure' else str(value), value)
            field.setCurrentIndex(max(0, field.findData(value)))
            field.currentIndexChanged.connect(self._surface_component_changed if key == 'component' else self._edited)
        elif key == 'association':
            field = QComboBox()
            field.addItem('점 자료', 'POINTS')
            field.addItem('셀 자료', 'CELLS')
            if field.findData(value) < 0:
                field.addItem('행 자료' if value == 'ROWS' else '저장된 위치: ' + str(value), value)
            field.setCurrentIndex(field.findData(value))
            field.setToolTip('ParaView의 원 자료 위치입니다. 셀 자료를 FE 요소로 추정하지 않습니다.')
            if self._draft.get('measurement') in ('surface_average', 'surface_time'):
                field.currentIndexChanged.connect(lambda *_: self._source_field_changed(path))
            else:
                field.currentIndexChanged.connect(self._edited)
        elif key in BOOLEANS:
            field = QComboBox()
            field.setEditable(True)
            field.addItems(['POINTS', 'CELLS'] if key == 'association' else ['true', 'false'])
            field.setCurrentText(field_text(value).lower() if key in BOOLEANS else field_text(value))
            field.currentTextChanged.connect(self._edited)
            if key == 'association' and self._draft.get('measurement') in ('surface_average', 'surface_time'):
                field.activated.connect(lambda *_: self._source_field_changed(path))
                field.lineEdit().editingFinished.connect(lambda: self._source_field_changed(path))
        else:
            field = QLineEdit(field_text(value))
            if key in VECTORS:
                field.setPlaceholderText('쉼표로 구분한 값')
            field.textEdited.connect(self._edited)
        field.setObjectName('post.' + '.'.join(path))
        self.fields[path] = (field, deepcopy(value))
        if form is not None:
            form.addRow(LABELS.get(key, key.replace('_', ' ').capitalize()), field)
        return field

    def _populate_editor(self):
        if getattr(self, '_compact_ready', False) and getattr(self, 'settings_pages', None) is not None:
            self._settings_page_index = self.settings_pages.currentIndex()
        self.settings_pages = None
        self._populating = True
        self.fields = {}
        # The form owns its editor widgets; do not retain one after deleteLater.
        self.comparison_editor = None
        for form in self._forms.values():
            while form.count():
                item = form.takeAt(0)
                if item.widget():
                    widget = item.widget()
                    widget.hide()
                    widget.setParent(None)
                    widget.deleteLater()
                elif item.layout():
                    while item.layout().count():
                        child = item.layout().takeAt(0)
                        if child.widget():
                            widget = child.widget()
                            widget.hide()
                            widget.setParent(None)
                            widget.deleteLater()
        form = self._forms[self._kind]
        draft = self._draft
        if not isinstance(draft, dict):
            form.addRow(QLabel('Malformed saved recipe remains in Details; Reset restores its last applied recipe.'))
        elif self._kind == 'comparison' and draft.get('version') == 3:
            from .post_curve_editor import CurveEditor, identity
            catalog = deepcopy(self._curve_catalog)
            for side in ('a', 'b'):
                current = draft[side]
                if current.get('source_ref') and not any(identity(o) == identity(current) for o in catalog):
                    catalog.append(deepcopy(current))
            self.comparison_editor = CurveEditor(draft, catalog, self)
            self.comparison_editor.changed.connect(self._edited)
            self.comparison_editor.refreshRequested.connect(self.refresh_curves)
            self.comparison_editor.importRequested.connect(self.import_data_curve)
            form.addRow(self.comparison_editor)
        elif self._kind == 'comparison' and draft.get('version') == 2:
            from .post_comparison_editor import ComparisonEditor
            sources = list(self._sources())
            for obj in self._objects():
                if obj.get('position', -1) >= 0 and obj.get('output_metadata'):
                    sources.append({'source_ref': obj['id'], 'label': obj.get('title', '저장 측정'),
                                    'metadata': obj['output_metadata'], 'native_metadata': obj['output_metadata']})
                elif obj.get('position', -1) >= 0 and obj.get('kind') == 'measurement':
                    history = obj['history'][obj['position']]
                    original = history['recipe']
                    if original.get('measurement') in ('point', 'path'):
                        row = {key: original.get(key) for key in MEASUREMENT_DECLARATIONS}
                        row.update(name=original.get('array'), association='POINTS')
                        metadata = {'arrays': [row], 'time': {'unit': original.get('time_units'),
                            'semantics': original.get('time_origin')} if original.get('time') is not None else None,
                            'timesteps': [], 'frozen_clock': {'value': original['time'], 'unit': original.get('time_units'),
                                'semantics': original.get('time_origin')} if original.get('time') is not None else None,
                            **{key: original.get(key) for key in ('coordinate_units', 'coordinate_frame')}}
                        sources.append({'source_ref': obj['id'], 'label': obj.get('title', '저장 측정'),
                                        'metadata': metadata, 'native_metadata': metadata})
            self.comparison_editor = ComparisonEditor(draft, sources, self)
            self.comparison_editor.changed.connect(self._edited)
            self.comparison_editor.showSource.connect(self.show_comparison_source)
            self.comparison_editor.showTogether.connect(self.show_comparison_originals)
            form.addRow(self.comparison_editor)
        elif self._kind == 'comparison':
            self.comparison_table = QTableWidget(len(SIDE_FIELDS), 3)
            table = self.comparison_table
            table.setObjectName('postComparisonFields')
            table.setHorizontalHeaderLabels(['Field', 'A', 'B'])
            table.verticalHeader().hide()
            table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
            table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
            table.setAlternatingRowColors(True)
            table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
            table.setColumnWidth(0, 170)
            for column in (1, 2):
                table.horizontalHeader().setSectionResizeMode(column, QHeaderView.ResizeMode.Stretch)
            for row, key in enumerate(SIDE_FIELDS):
                label = QLabel(LABELS.get(key, key.replace('_', ' ').capitalize()))
                label.setContentsMargins(7, 0, 4, 0)
                label.setWordWrap(True)
                table.setCellWidget(row, 0, label)
                table.setRowHeight(row, 36)
                for column, side in ((1, 'a'), (2, 'b')):
                    values = draft.get(side, {})
                    if not isinstance(values, dict):
                        table.setCellWidget(row, column, QLabel('Malformed side; see Details'))
                        continue
                    value = values.get(key, None if key in ('time', 'time_units', 'time_origin') else 'POINTS' if key == 'association' else '')
                    table.setCellWidget(row, column, self._form_field(None, key, value, (side, key)))
            table.setFixedHeight(sum(table.rowHeight(row) for row in range(table.rowCount())) + table.horizontalHeader().sizeHint().height() + 4)
            form.addRow(table)
            self.method = QComboBox()
            self.method.setEditable(True)
            self.method.addItem('같은 메시의 점 대응', 'same_mesh')
            self.method.addItem('B를 A에 선형 사면체 보간', 'linear_tetra_b_to_a')
            method = draft.get('method', 'same_mesh')
            index = self.method.findData(method)
            self.method.setCurrentIndex(index)
            if index < 0:
                self.method.setEditText(str(method))
            self.method.currentTextChanged.connect(self._edited)
            form.addRow('대응 방법', self.method)
            self._form_field(form, 'tolerance', draft.get('tolerance', ''), ('tolerance',))
            declarations = QHBoxLayout()
            for side in ('a', 'b'):
                button = QPushButton('Use retained ' + side.upper() + ' declarations')
                button.clicked.connect(lambda checked=False, side=side: self.use_declarations(side))
                declarations.addWidget(button)
            form.addRow(declarations)
        elif self._kind == 'filter':
            self._form_field(form, 'source_ref', draft.get('source_ref', ''), ('source_ref',))
            self.filter_kind = QComboBox()
            self.filter_kind.addItems(FILTERS)
            if draft.get('filter') not in FILTERS:
                self.filter_kind.addItem(display(draft.get('filter')))
            self.filter_kind.setCurrentText(draft.get('filter', 'Slice'))
            self.filter_kind.currentTextChanged.connect(self._filter_changed)
            form.addRow('필터', self.filter_kind)
            settings = draft.get('settings', {})
            if isinstance(settings, dict):
                for key in FILTER_FIELDS.get(draft.get('filter'), ()):
                    default = None if key == 'time' else 'POINTS' if key == 'association' else ''
                    self._form_field(form, key, settings.get(key, default), ('settings', key))
            else:
                form.addRow(QLabel('Malformed filter settings retained in Details.'))
        elif draft.get('measurement') == 'contact_force':
            title = QLabel(self._recipe_meaning(draft))
            title.setWordWrap(True)
            form.addRow(title)
            button = QPushButton('접촉 쌍 조회…')
            button.clicked.connect(self.open_contact_inspector)
            form.addRow(button)
        else:
            self.measurement_kind = QComboBox()
            for title, kind in (('선택한 원본 점', 'point'), ('두 점 사이 경로', 'path'), ('같은 원본 점의 시간 이력', 'time'), ('두 점 상대변위', 'gauge'), ('두 점 상대변위의 시간 이력', 'gauge_time'), ('면적 가중 면 평균', 'surface_average'), ('면적 가중 면 평균의 시간 이력', 'surface_time')):
                self.measurement_kind.addItem(title, kind)
            kind = draft.get('measurement', 'point')
            if kind not in MEASUREMENT_FIELDS:
                self.measurement_kind.addItem('미지원 저장 방식: ' + display(kind), kind)
            self.measurement_kind.setCurrentIndex(self.measurement_kind.findData(kind))
            self.measurement_kind.currentIndexChanged.connect(lambda _index: self._measurement_changed(self.measurement_kind.currentData()))
            form.addRow('측정 방식', self.measurement_kind)
            if kind in ('gauge', 'gauge_time'):
                self._gauge_settings(form, draft)
            elif kind in ('surface_average', 'surface_time'):
                self._surface_settings(form, draft)
            for key in (() if kind in ('gauge', 'gauge_time', 'surface_average', 'surface_time') else MEASUREMENT_FIELDS.get(draft.get('measurement'), ())):
                self._form_field(form, key, draft.get(key, None if key in ('time', 'time_units', 'time_origin') else 'POINTS' if key == 'association' else ''), (key,))
                if key in MEASUREMENT_DECLARATIONS:
                    self.fields[(key,)][0].setPlaceholderText('선언이 없으면 알 수 없음')
            note = QLabel('단위와 물리적 정의는 저장된 선언을 사용하거나 직접 지정하세요. 비워 두면 미확인으로 남습니다. 점 번호는 solver 절점 번호와 다른 VTK 인덱스입니다.')
            if draft.get('measurement') == 'gauge':
                note.setText('두 원본 점의 변위 차이를 지정한 단위 방향으로 투영합니다. 신장이나 변형률이 아닙니다. 원본 VTK 점 번호 두 개와 그 기준 좌표를 같은 순서로 지정하세요. 같은 고정 직교 좌표계의 변위 필드만 사용합니다.')
            note.setWordWrap(True)
            if kind not in ('gauge', 'gauge_time', 'surface_average', 'surface_time'):
                form.addRow(note)
            declarations_button = QPushButton('저장된 물리량 정보 사용')
            declarations_button.clicked.connect(lambda checked=False: self.use_declarations())
            if kind not in ('gauge', 'gauge_time', 'surface_average', 'surface_time'):
                form.addRow(declarations_button)
            else:
                declarations_button.deleteLater()
            self.capture_button = QPushButton('ParaView에서 선택한 원본 점 가져오기')
            self.capture_button.setToolTip('점 측정과 시간 이력에 사용합니다. 경로는 두 끝점 좌표를 지정하세요.')
            self.capture_button.clicked.connect(self.capture_selection)
            form.addRow(self.capture_button)
            if draft.get('measurement') in ('gauge', 'gauge_time'):
                self.capture_button.setText('2  선택한 두 점 가져오기')
                self.capture_button.setToolTip('선택한 두 원본 점의 번호와 현재 기준좌표를 함께 가져옵니다. 처음에는 점 번호 오름차순이며 순서는 바꿀 수 있습니다.')
                swap = QPushButton('두 점 순서 바꾸기')
                swap.setObjectName('swapGaugePoints')
                swap.clicked.connect(self.swap_gauge_points)
                form.removeWidget(self.capture_button)
                self.gauge_selection_layout.addWidget(self.capture_button)
                self.gauge_selection_layout.addWidget(swap)
            elif kind in ('surface_average', 'surface_time'):
                self.capture_button.setText('기준 시각의 원본 경계 면 선택…')
                self.capture_button.clicked.disconnect()
                self.capture_button.clicked.connect(self.capture_surface_faces)
                form.removeWidget(self.capture_button)
                self.surface_selection_layout.addWidget(self.capture_button)
        if getattr(self, '_compact_ready', False) and self._kind == 'measurement' and isinstance(draft, dict) and draft.get('measurement') in MEASUREMENT_FIELDS:
            self._compact_measurement_pages(form, draft)
        self.tabs.blockSignals(True)
        self.tabs.setCurrentIndex(('comparison', 'filter', 'measurement').index(self._kind))
        self.tabs.blockSignals(False)
        self._populating = False
        self._update_actions()

    def _compact_measurement_pages(self, form, draft):
        from .post_settings_pages import SettingsPages
        pages = SettingsPages()
        hold = QWidget(pages)
        hold.hide()
        measurement = draft['measurement']
        kept = [self.measurement_kind, *(field for field, _original in self.fields.values())]
        if hasattr(self, 'capture_button'):
            kept.append(self.capture_button)
        swap = self.findChild(QPushButton, 'swapGaugePoints') if measurement in ('gauge', 'gauge_time') else None
        native = self.findChild(QToolButton, 'postNativeSelect' if measurement in ('gauge', 'gauge_time') else 'postNativeSurface')
        for widget in (swap, native):
            if widget is not None: kept.append(widget)
        for name in ('gauge_points','gauge_notice','gauge_conditions') if measurement in ('gauge','gauge_time') else ('surface_summary','surface_conditions') if measurement in ('surface_average','surface_time') else ():
            kept.append(getattr(self, name))
        for widget in kept:
            widget.hide(); widget.setParent(hold)
        while form.count():
            item = form.takeAt(0)
            if item.widget():
                widget = item.widget(); widget.hide(); widget.setParent(None); widget.deleteLater()
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        form.addRow('측정', self.measurement_kind)
        self.measurement_kind.show()
        self.settings_pages = pages
        form.addRow(pages)
        pages.show()
        labels = {'source_ref':'원 결과', 'array':'필드', 'association':'자료 위치',
            'direction':'단위 방향 n', 'basis':'방향 기저', 'coordinate_configuration':'좌표 상태',
            'point1':'A 기준 좌표', 'point2':'B 기준 좌표', 'point_indices':'원본 점 번호',
            'time':'측정 시각', 'time_range':'시각 범위', 'reference_time':'기준 시각',
            'geometry':'면적 기준', 'component':'원 성분', 'tolerance':'허용 오차'}
        self._compact_field_labels = {}
        for path, (field, _original) in self.fields.items():
            key = path[-1]
            page = pages.page_for(key, measurement)
            self._compact_field_labels[path] = pages.field(page, labels.get(key, LABELS.get(key,key)), field)
        if native is None:
            native = QToolButton()
            native.setDefaultAction(self.native_action)
            native.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        pages.row(0, native)
        if measurement in ('point','time','gauge','gauge_time'):
            self.capture_button.clicked.disconnect()
            self.capture_button.clicked.connect(self.capture_new_measurement)
            self.capture_button.setText('선택으로 새 측정 추가')
            self.capture_button.setToolTip('ParaView의 원본 점 선택으로 새 측정을 만듭니다. 현재 측정의 편집 내용을 덮지 않습니다.')
        else:
            self.capture_button.setText('원본 경계 면 선택…')
        selection = QWidget()
        row = QHBoxLayout(selection)
        row.setContentsMargins(0,0,0,0)
        row.addWidget(self.capture_button, 1)
        self.capture_button.show()
        if swap is not None:
            swap.setText('A/B 순서 교환')
            row.addWidget(swap)
            swap.show()
        pages.row(0, selection)
        if measurement in ('gauge','gauge_time'):
            pages.row(0, self.gauge_points)
            pages.row(0, self.gauge_notice)
            self.gauge_notice.setVisible(bool(self.gauge_notice.text()))
        elif measurement in ('surface_average','surface_time'):
            pages.row(0, self.surface_summary)
        declarations = QPushButton('저장된 물리량 선언 사용')
        declarations.clicked.connect(lambda: self.use_declarations())
        pages.row(2, declarations)
        clock = QLabel()
        clock.setWordWrap(True)
        metadata, _ = self._source_choice_metadata(draft.get('source_ref'))
        times = metadata.get('timesteps') or []
        clock.setText('원 결과 시각: ' + (field_text(times[:8]) + (' …' if len(times)>8 else '') if times else '저장된 시각 정보 없음'))
        clock.setToolTip(field_text(times))
        pages.row(3, clock)
        pages.setCurrentIndex(max(0,min(3,getattr(self,'_settings_page_index',0))))

    @staticmethod
    def _analysis_state(obj):
        history, position = obj.get('history', []), obj.get('position', -1)
        active = history[position] if 0 <= position < len(history) else None
        preview = obj.get('preview')
        if preview and preview.get('id') != (active or {}).get('id'):
            return '미리보기'
        return '적용됨' if active else '초안'

    def _surface_settings(self, form, draft):
        main = ('source_ref', 'array', 'association', 'component', 'direction') + (('time_range', 'reference_time') if draft['measurement'] == 'surface_time' else ('time',))
        for key in main:
            default = 'POINTS' if key == 'association' else None if key in ('time', 'reference_time', 'component', 'direction') else [] if key in VECTORS else ''
            self._form_field(form, key, draft.get(key, default), (key,))
        native = QToolButton()
        native.setDefaultAction(self.native_action)
        native.setText('ParaView에서 원 결과 보기…')
        native.setObjectName('postNativeSurface')
        native.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        form.addRow(native)
        self.surface_summary = QLabel()
        self.surface_summary.setWordWrap(True)
        form.addRow(self.surface_summary)
        selection = QWidget()
        self.surface_selection_layout = QVBoxLayout(selection)
        self.surface_selection_layout.setContentsMargins(0, 0, 0, 0)
        form.addRow(selection)
        self.surface_conditions = QLabel()
        self.surface_conditions.setWordWrap(True)
        form.addRow(self.surface_conditions)
        toggle = QToolButton()
        toggle.setText('측정 조건 / 고정 기준 면적')
        toggle.setCheckable(True)
        toggle.setArrowType(Qt.ArrowType.RightArrow)
        toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        form.addRow(toggle)
        details = QWidget()
        conditions = QFormLayout(details)
        conditions.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)
        for key in MEASUREMENT_FIELDS[draft['measurement']]:
            if key not in main:
                self._form_field(conditions, key, draft.get(key), (key,))
        declarations = QPushButton('저장된 물리량 정보 사용')
        declarations.clicked.connect(lambda: self.use_declarations())
        conditions.addRow(declarations)
        details.hide()
        toggle.toggled.connect(details.setVisible)
        toggle.toggled.connect(lambda opened: toggle.setArrowType(Qt.ArrowType.DownArrow if opened else Qt.ArrowType.RightArrow))
        form.addRow(details)

    def _gauge_settings(self, form, draft):
        self._form_field(form, 'source_ref', draft.get('source_ref', ''), ('source_ref',))
        self._form_field(form, 'array', draft.get('array', ''), ('array',))
        native = QToolButton()
        native.setDefaultAction(self.native_action)
        native.setText('1  ParaView로 이동')
        native.setObjectName('postNativeSelect')
        native.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        native.setToolTip('실제 ParaView 창으로 이동합니다. 원 결과의 점 선택 도구로 두 점을 고른 뒤 이 창으로 돌아오세요.')
        form.addRow(native)
        self.gauge_points = QLabel()
        self.gauge_points.setObjectName('gaugePointSummary')
        self.gauge_points.setWordWrap(True)
        form.addRow(self.gauge_points)
        self.gauge_notice = QLabel()
        self.gauge_notice.setWordWrap(True)
        self.gauge_notice.setObjectName('gaugeSelectionNotice')
        self.gauge_notice.hide()
        form.addRow(self.gauge_notice)
        selection = QWidget()
        self.gauge_selection_layout = QVBoxLayout(selection)
        self.gauge_selection_layout.setContentsMargins(0, 0, 0, 0)
        form.addRow(selection)
        self._form_field(form, 'direction', draft.get('direction', []), ('direction',))
        self.fields[('direction',)][0].setPlaceholderText('단위 방향을 명시: x, y, z')
        axes = QComboBox()
        axes.setAccessibleName('명시적으로 선택할 전역 방향')
        axes.addItem('방향 직접 입력 / 전역축 선택…', None)
        for text, vector in [('X 방향', [1,0,0]), ('Y 방향', [0,1,0]), ('Z 방향', [0,0,1])]:
            axes.addItem(text, vector)
        def direction(index):
            vector = axes.itemData(index)
            if vector is not None:
                self.fields[('direction',)][0].setText(field_text(vector))
                self._edited()
        axes.currentIndexChanged.connect(direction)
        form.addRow(axes)
        self.gauge_conditions = QLabel()
        self.gauge_conditions.setObjectName('gaugeConditionSummary')
        self.gauge_conditions.setWordWrap(True)
        form.addRow(self.gauge_conditions)
        toggle = QToolButton()
        toggle.setText('측정 조건 / 기준 시각·좌표' if draft['measurement'] == 'gauge_time' else '측정 조건 / 기준 좌표')
        toggle.setCheckable(True)
        toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        toggle.setArrowType(Qt.ArrowType.RightArrow)
        toggle.setObjectName('gaugeConditionsToggle')
        form.addRow(toggle)
        details = QWidget()
        detail_form = QFormLayout(details)
        detail_form.setContentsMargins(0, 0, 0, 0)
        detail_form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)
        if draft.get('measurement') == 'gauge_time':
            for key in ('time_range', 'reference_time'):
                self._form_field(detail_form, key, draft.get(key), (key,))
        for key in MEASUREMENT_FIELDS[draft['measurement']]:
            if key not in ('source_ref', 'array', 'direction', 'time_range', 'reference_time'):
                default = None if key in ('time', 'time_units', 'time_origin') else 'POINTS' if key == 'association' else ''
                self._form_field(detail_form, key, draft.get(key, default), (key,))
        declarations = QPushButton('저장된 물리량 정보 사용')
        declarations.clicked.connect(lambda: self.use_declarations())
        detail_form.addRow(declarations)
        note = QLabel('δ = (두 번째 점의 변위 − 첫 번째 점의 변위) · 방향\n같은 고정 직교 좌표계의 변위만 사용합니다. 거리 변화나 변형률이 아닙니다.')
        note.setWordWrap(True)
        detail_form.addRow(note)
        details.hide()
        toggle.toggled.connect(details.setVisible)
        toggle.toggled.connect(lambda opened: toggle.setArrowType(Qt.ArrowType.DownArrow if opened else Qt.ArrowType.RightArrow))
        form.addRow(details)

    def _update_gauge_summary(self):
        if self._kind != 'measurement' or self.edited_draft().get('measurement') not in ('gauge', 'gauge_time'):
            return
        draft = self.edited_draft()
        points = draft.get('point_indices')
        if isinstance(points, list) and len(points) == 2:
            unit = str(draft.get('coordinate_units') or '단위 미지정')
            self.gauge_points.setText('A: 원본 점 ' + str(points[0]) + ' / (' + field_text(draft.get('point1')) + ') [' + unit + ']' +
                '\nB: 원본 점 ' + str(points[1]) + ' / (' + field_text(draft.get('point2')) + ') [' + unit + ']\n부호 순서: B − A')
            self.gauge_points.setToolTip(str(draft.get('original_point_ids') or '저장된 추가 원 ID 없음'))
        else:
            self.gauge_points.setText('원본 점 두 개 선택 필요 — ParaView에서 선택 후 가져오세요.')
        required = ('units', 'measure', 'frame', 'coordinate_units', 'coordinate_frame', 'basis', 'coordinate_configuration')
        if draft.get('measurement') == 'gauge_time':
            required += ('time_range', 'time_units', 'time_origin')
        missing = [LABELS[key] for key in required if not draft.get(key)]
        if draft.get('measurement') == 'gauge_time' and draft.get('reference_time') in (None, ''):
            missing.append(LABELS['reference_time'])
        clock = ('시각 범위 ' + (field_text(draft.get('time_range')) or '미지정') + ' [' + str(draft.get('time_units') or '단위 미지정') + '] / 기준 ' + str(draft.get('reference_time') if draft.get('reference_time') is not None else '미지정') if draft.get('measurement') == 'gauge_time' else '시각 정보 없음' if draft.get('time') is None else
                 '시각 ' + str(draft['time']) + ' [' + str(draft.get('time_units') or '단위 미지정') + '] / ' +
                 {'analysis_start':'해석 시작 기준'}.get(draft.get('time_origin'), str(draft.get('time_origin') or '시간 기준 미지정')))
        self.gauge_conditions.setText(('미결정: ' + ', '.join(missing) if missing else
            '응답 [' + str(draft['units']) + '] / 좌표계 ' + str(draft['frame']) + '\n기준 좌표 [' + str(draft['coordinate_units']) + ']') + '\n' + clock)
        self.gauge_conditions.setToolTip('시간 기준: ' + str(draft.get('time_origin')))

    def edited_draft(self):
        draft = deepcopy(self._draft)
        if not isinstance(draft, dict):
            return draft
        if self._kind == 'comparison' and draft.get('version') in (2, 3):
            return self.comparison_editor.draft()
        for path, (field, original) in self.fields.items():
            if isinstance(field, QComboBox):
                if path[-1] == 'source_ref':
                    text = field.currentData() if field.currentIndex() >= 0 and field.currentText() == field.itemText(field.currentIndex()) else field.currentText()
                elif path[-1] in ('basis', 'coordinate_configuration', 'measure', 'geometry', 'component', 'association'):
                    text = field.currentData()
                else:
                    text = field.currentText()
            else:
                text = field.text()
            value = parse_field(path[-1], text, original)
            parent = draft
            for key in path[:-1]:
                parent = parent.setdefault(key, {})
            # Displaying an absent default does not rewrite a saved invalid recipe.
            if path[-1] in parent or value != original:
                parent[path[-1]] = value
        if self._kind == 'comparison':
            text = self.method.currentText()
            method = self.method.currentData() if self.method.currentIndex() >= 0 and text == self.method.itemText(self.method.currentIndex()) else text
            if method != draft.get('method'):
                draft['method'] = method
        return draft

    def _edited(self, *_):
        if not self._populating:
            self.local_dirty = True
            self._edit_serial += 1
            self._update_actions()

    def _source_field_changed(self, path):
        if self._populating:
            return
        self._draft = self.edited_draft()
        self._populate_editor()
        self._edited()

    def _filter_changed(self, kind):
        if self._populating:
            return
        draft = self.edited_draft()
        draft.update(filter=kind, settings={})
        self._draft = draft
        self._populate_editor()
        self._edited()

    def _measurement_changed(self, kind):
        if self._populating:
            return
        draft = self.edited_draft()
        self._draft = {key: value for key, value in draft.items() if key in MEASUREMENT_FIELDS[kind]}
        if kind in ('gauge', 'gauge_time') and draft.get('measurement') in ('gauge', 'gauge_time') and 'original_point_ids' in draft:
            self._draft['original_point_ids'] = deepcopy(draft['original_point_ids'])
        if kind in ('surface_average', 'surface_time') and draft.get('measurement') in ('surface_average', 'surface_time') and 'surface_faces' in draft:
            self._draft['surface_faces'] = deepcopy(draft['surface_faces'])
        self._draft['measurement'] = kind
        self._populate_editor()
        self._edited()

    def _surface_component_changed(self, *_):
        if self._populating:
            return
        if self._kind != 'measurement' or self._draft.get('measurement') not in ('surface_average', 'surface_time'):
            self._edited()
            return
        self._draft = self.edited_draft()
        if self._draft.get('component') != 'projection':
            self._draft['direction'] = None
        self._populate_editor()
        self._edited()

    def _tab_changed(self, index):
        if self._populating:
            return
        kind = ('comparison', 'filter', 'measurement')[index]
        if kind != self._kind:
            self.new_object(kind)

    def new_object(self, kind):
        if self._busy or self._pending:
            return False
        if self.local_dirty:
            self.message.setText('현재 편집을 초안으로 보관한 뒤 새 분석을 만드세요.')
            self.tabs.blockSignals(True)
            self.tabs.setCurrentIndex(('comparison', 'filter', 'measurement').index(self._kind))
            self.tabs.blockSignals(False)
            return False
        self._kind, self._object_ref = kind, None
        self.work_tabs.setCurrentIndex(0)
        if self.settings_pages is not None:
            self.settings_pages.setCurrentIndex(0)
        self._tree_selection = None
        self._restore_tree_selection()
        self._samples = self._sample_basis = None
        self.samples.setRowCount(0)
        self.samples.setColumnCount(0)
        self._draft = defaults(kind, self._source_ref or '')
        self.local_dirty = True
        self._edit_serial += 1
        self._populate_editor()
        self.editor_toggle.setChecked(True)
        self.message.setText('새 ' + {'comparison': '결과 비교', 'filter': '필터', 'measurement': '측정'}[kind] +
                             ' 설정을 편집하세요. 초안 보관과 미리보기 후 적용할 수 있습니다.')
        self._update_actions()
        return True

    def new_curve_comparison(self):
        if not self.new_object('comparison'):
            return False
        from .post_curve_editor import default_recipe
        self._draft = default_recipe()
        self._populate_editor()
        return self.refresh_curves()

    def refresh_curves(self):
        token = self._context_token()
        def accepted(payload):
            if token != self._context_token():
                return
            draft = self.edited_draft()
            self._curve_catalog = deepcopy(payload['curves'])
            self._draft = draft
            self._populate_editor()
            if payload.get('issues'):
                self.message.setText('저장 곡선 일부를 읽지 못했습니다. 해당 측정을 저장하거나 원자료를 다시 연결하세요.')
                self.details.setPlainText(json.dumps(payload['issues'], ensure_ascii=False, indent=2))
        return self.queue_command('post.curve_catalog', {}, accepted=accepted)

    def import_data_curve(self):
        if self._busy or self._pending:
            return False
        from .post_curve_editor import DataCurvePicker
        token = self._context_token()
        picker = DataCurvePicker(self.client, self)
        if picker.exec() != QDialog.DialogCode.Accepted or picker.selected is None or token != self._context_token():
            return False
        selected = deepcopy(picker.selected)
        def ready(receipt):
            def added(payload):
                self.refresh_curves()
            self.queue_command('post.source_add', {'input_id': receipt['id'], 'label_text': receipt['name']}, accepted=added)
        return self._call(lambda: self.client.post_curve_snapshot(**selected), ready,
                          relevant=lambda: token == self._context_token())

    def use_declarations(self, side=None):
        draft = self.edited_draft()
        target = draft.get(side, {}) if side is not None else draft
        _, metadata = self._source_choice_metadata(target.get('source_ref'))
        if not isinstance(metadata, dict):
            self.message.setText('저장된 물리 선언이 없습니다. 필요한 단위와 물리 의미를 직접 지정하세요.')
            return
        declaration = next((row for row in metadata.get('arrays', []) if (row.get('name'), row.get('association')) == (target.get('array'), target.get('association'))), None)
        if not declaration:
            self.message.setText('이 결과에 저장된 물리량과 점·셀 위치를 선택하세요.')
            return
        for key in ('quantity', 'units', 'measure', 'frame', 'layout', 'temperature_kind', 'validity_masks', 'observable', 'validity_policy', 'spatial_mask'):
            if key in declaration:
                target[key] = deepcopy(declaration[key])
        for key in ('coordinate_units', 'coordinate_frame'):
            if key in metadata:
                target[key] = deepcopy(metadata[key])
        clock = metadata.get('frozen_clock') or metadata.get('time')
        if 'frozen_clock' in metadata:
            target['time'] = None
            if side is not None:
                target['frozen_clock'] = deepcopy(metadata['frozen_clock'])
                target['sampling'] = {'mode':'exact', 'time':None}
        if isinstance(clock, dict):
            if 'unit' in clock:
                target['time_units'] = clock['unit']
            if 'semantics' in clock:
                target['time_origin'] = clock['semantics']
        self._draft = draft
        self._populate_editor()
        self._edited()

    def queue_command(self, operation, arguments, *, accepted=None):
        if self._busy and self._accepting and self._pending is None:
            retained_arguments = deepcopy(arguments)
            return self._defer_callback(lambda: self.queue_command(operation, retained_arguments, accepted=accepted))
        if not self.document or self._busy or self._pending or self.conflict:
            self.message.setText('Wait for or recover the current request, then refresh the exact owner before applying edits.')
            return False
        request = {'document_id': self.document['id'], 'session_id': self.document['session_id'],
            'expected_generation': self.document['generation'], 'command_id': 'C' + uuid.uuid4().hex,
            'operation': operation, 'arguments': deepcopy(arguments)}
        pending = self._pending = {'request': request, 'accepted': accepted, 'edit_serial': self._edit_serial,
            'buffer': self.edited_draft(), 'object_ref': self._object_ref, 'kind': self._kind, 'phase': 'preflight'}
        self.progress.setText(self.operation_label(operation) + ': 현재 문서 확인 중')
        def submit():
            remote = self.client.document_read(request['document_id'])
            if not remote.get('connected') or remote.get('session_id') != request['session_id']:
                raise ValueError('The selected native owner is disconnected or its session changed')
            if remote['generation'] != request['expected_generation']:
                raise ValueError('Native generation changed; explicitly refresh owner and review this draft')
            pending['phase'] = 'submitted'
            return self.client.document_command(request['document_id'], operation, request['arguments'],
                session_id=request['session_id'], expected_generation=request['expected_generation'], command_id=request['command_id'])
        def received(command):
            if self._pending is not pending:
                return
            pending['command'] = command
            self._last_command = deepcopy(command)
            self._command_progress(command)
            self.command_timer.start()
            QTimer.singleShot(0, self.poll_command)
        def failed(error):
            if pending['phase'] == 'preflight':
                self._pending = None
                self.conflict = True
                self.progress.setText('No command submitted. Refresh owner explicitly; current draft retained.')
            else:
                self.progress.setText('Submission outcome is unconfirmed. Recover the same request ' + request['command_id'])
        return self._call(submit, received, failed=failed)

    def poll_command(self):
        if self._busy or not self._pending:
            return False
        pending = self._pending
        request = pending['request']
        def read():
            command = self.client.command_status(request['command_id'])
            if command['state'] in TERMINAL:
                return command, self.client.document_read(request['document_id'])
            return command, None
        return self._call(read, lambda result: self._command_polled(pending, *result), failed=self._poll_failed)

    def _poll_failed(self, error):
        self.command_timer.stop()
        if self._pending:
            self.progress.setText('Status unavailable. Recover exact request ' + self._pending['request']['command_id'] + '; no replay has occurred.')

    def _command_polled(self, pending, command, remote):
        if self._pending is not pending:
            return
        self._last_command = deepcopy(command)
        self._command_progress(command)
        if command['state'] not in TERMINAL:
            return
        self.command_timer.stop()
        self._pending = None
        owner = (pending['request']['document_id'], pending['request']['session_id'])
        if not self.document or (self.document['id'], self.document['session_id']) != owner:
            return
        late_edit = self._edit_serial != pending['edit_serial'] or self.edited_draft() != pending['buffer']
        changed_target = (self._object_ref, self._kind) != (pending['object_ref'], pending['kind'])
        self.local_dirty = late_edit or self.local_dirty
        if command['state'] == 'SUCCEEDED':
            payload = native_payload(command)
            if pending['request']['operation'].endswith('_edit') and isinstance(payload, dict) and payload.get('id'):
                if not changed_target:
                    self._object_ref = payload['id']
                    self._tree_selection = ('object', payload['id'])
                    self.local_dirty = late_edit
            if remote.get('session_id') != owner[1]:
                self.conflict = True
                self.message.setText('Native owner session changed after the request; local draft remains here.')
                return
            self._show_document(remote, preserve_buffer=late_edit or changed_target or self.local_dirty)
            if not late_edit and not changed_target:
                callback = pending.get('accepted')
                if callback:
                    callback(payload)
            self.message.setText(self.operation_label(pending['request']['operation']) + ' 완료.' +
                                 (' 새 편집은 아직 적용하지 않았습니다.' if late_edit or
                                  (self.local_dirty and pending['request']['operation'] == 'post.measurement_capture') else ''))
            if pending['request']['operation'] == 'document.activate':
                confirmed = isinstance(payload, dict) and payload.get('foreground_confirmed') is True
                self.message.setText('ParaView 창으로 이동했습니다. 점 선택 도구로 원본 점을 선택하세요.' if confirmed else
                    '원 결과는 선택했습니다. Windows가 창 전환을 허용하지 않았습니다. 작업 표시줄의 ParaView 창을 열어 점을 선택하세요.')
                self._compact_show_result(self._compact_messages)
            elif pending['request']['operation'] == 'post.source_select':
                self.message.setText('원 결과를 ParaView에서 선택했습니다. 점 선택 도구는 ParaView 창에서 사용하세요.')
        else:
            self._show_document(remote, preserve_buffer=True)
            error = command.get('outcome', {}).get('error', command.get('error', {}))
            error_text = str(error.get('message', error) if isinstance(error, dict) else error)
            if ('REFERENCE_REPAIR_REQUIRED' in error_text and
                    self.edited_draft().get('measurement') in ('gauge', 'gauge_time')):
                error_text = '기준 시각의 원래 두 점이나 좌표가 달라졌습니다. 두 점을 다시 선택하세요.'
            self.message.setText('요청을 완료하지 못했습니다. 편집은 보관했습니다. ' +
                                 error_text)
            if getattr(self, '_desktop_ready', False):
                self._compact_show_result(self._compact_messages)
                if self.edited_draft().get('measurement') == 'gauge':
                    self.gauge_notice.setText(self.message.text())
                    self.gauge_notice.show()
            if pending['request']['operation'] == 'post.sample' and self._sample_basis:
                self._sample_basis['failed'] = True
        self._show_details()
        self._update_actions()

    def recover_request(self):
        if self._busy or not self._pending:
            return False
        pending = self._pending
        request = pending['request']
        def recover():
            try:
                return self.client.command_status(request['command_id'])
            except HTTPError as error:
                if error.code != 404:
                    raise
                remote = self.client.document_read(request['document_id'])
                if remote.get('session_id') != request['session_id'] or remote['generation'] != request['expected_generation']:
                    # The exact request is absent and its owner generation no
                    # longer matches. Release only this provably unsubmitted ID.
                    return {'not_submitted': True, 'document': remote}
                return self.client.document_command(request['document_id'], request['operation'], request['arguments'],
                    session_id=request['session_id'], expected_generation=request['expected_generation'], command_id=request['command_id'])
        def received(command):
            if command.get('not_submitted'):
                self._last_command = {'state': 'NOT_SUBMITTED', 'request': deepcopy(request)}
                self._pending = None
                self.conflict = True
                self._show_document(command['document'], preserve_buffer=True)
                self.progress.setText('Exact request was not registered; its generation changed. Refresh owner and review this retained draft.')
                return
            pending['command'] = command
            self.command_timer.start()
            QTimer.singleShot(0, self.poll_command)
        return self._call(recover, received, failed=self._poll_failed)

    def store_draft(self, *, after=None):
        operation = 'post.' + self._kind + '_edit'
        arguments = {'draft': self.edited_draft()}
        if not self._object_ref and arguments['draft'].get('version') == 3:
            arguments['title'] = '곡선 비교'
        if self._object_ref:
            arguments['object_ref'] = self._object_ref
        def stored(payload):
            self.local_dirty = False
            if after:
                QTimer.singleShot(0, after)
        return self.queue_command(operation, arguments, accepted=stored)

    def preview(self):
        def validate():
            self.queue_command('post.mapping_validate', {'object_ref': self._object_ref})
        if self.local_dirty or not self._object_ref:
            return self.store_draft(after=validate)
        return validate()

    def reset_draft(self):
        if self._object_ref:
            return self.object_command('post.reset')
        if self._busy or self._pending:
            return False
        self._draft = defaults(self._kind, self._source_ref or '')
        self.local_dirty = False
        self._edit_serial += 1
        self._populate_editor()
        self.message.setText('Local new recipe reset. No native application or saved object was changed.')
        return True

    def object_command(self, operation, extra=None, *, after=None):
        if not self._object_ref:
            self.message.setText('Keep this explicit recipe first to create an analysis object.')
            return False
        if self.local_dirty and operation not in ('post.reset', 'post.show_analysis'):
            self.message.setText('Keep and Preview the edited draft first. This action uses the retained object recipe.')
            return False
        def accepted(payload):
            if operation == 'post.reset':
                self.local_dirty = False
                obj = self._object()
                if obj:
                    self._draft = deepcopy(obj['draft'])
                    self._populate_editor()
            if operation == 'post.export':
                self.details.setPlainText(json.dumps({'export': payload, 'command': self._last_command}, ensure_ascii=False, indent=2))
            if after:
                after(payload)
        arguments = {'object_ref': self._object_ref, **(extra or {})}
        if operation in ('post.apply', 'post.show_analysis'):
            view = self._view_arguments()
            if view is None:
                return False
            arguments.update(view)
        return self.queue_command(operation, arguments, accepted=accepted)

    def save_document(self):
        if self.local_dirty:
            return self.store_draft(after=self.save_document)
        return self.queue_command('document.save', {})

    def show_comparison_curve(self):
        if not self._samples or not self._sample_basis or self._sample_basis['draft'].get('version') not in (2, 3):
            self.message.setText('비교 값을 먼저 읽으세요.')
            return
        if self._sample_basis['draft'].get('version') == 3:
            from .post_curve_plot import CurvePlot
            dialog = CurvePlot(self._samples, self._sample_basis, self)
            dialog.rowSelected.connect(lambda index: self.select_curve_row(index, dialog.basis))
            from .post_curve_origin_ui import attach_origin_controls
            attach_origin_controls(dialog, self)
        else:
            from .post_comparison_plot import ComparisonPlot
            dialog = ComparisonPlot(self._samples, self._sample_basis, self)
            dialog.pointSelected.connect(lambda index: self.select_comparison_point(index, dialog.basis))
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.sampleSelectionChanged.connect(dialog.select_sample)
        if self._confirmed_sample_selection is not None:
            dialog.select_sample(*self._confirmed_sample_selection)
        dialog.show()

    def _current_sample_revision(self, preview):
        obj = self._object() or {}
        if preview:
            return (obj.get('preview') or {}).get('id')
        history, position = obj.get('history', []), obj.get('position', -1)
        return history[position]['id'] if 0 <= position < len(history) else None

    def select_comparison_point(self, index, basis):
        if ((basis.get('document_id'), basis.get('session_id')) != (self.document_id, self.session_id)
                or self._object_ref != basis['object_ref'] or not self._sample_basis
                or self._sample_basis.get('revision') != basis.get('revision')
                or self._current_sample_revision(basis['preview']) != basis.get('revision')):
            self.message.setText('선택한 곡선은 이전 조회입니다. 원 비교를 다시 열어 선택하세요.')
            return False
        owner = (self.document_id, self.session_id)
        token = (self._object_ref, basis.get('revision'))
        def selected(payload):
            if (owner != (self.document_id, self.session_id)
                    or token != (self._object_ref, (self._sample_basis or {}).get('revision'))
                    or token != (payload.get('object_ref'), payload.get('revision'))
                    or self._current_sample_revision(basis['preview']) != token[1]):
                return
            for row, value in enumerate((self._samples or {}).get('rows', [])):
                if value.get('point_index') == index:
                    self.samples.selectRow(row)
                    break
            self._confirmed_sample_selection = (index, deepcopy(basis))
            self.sampleSelectionChanged.emit(index, basis)
        return self.queue_command('post.sample', {'object_ref': self._object_ref,
            'preview': basis['preview'], 'point_index': index, 'limit': 1,
            'expected_revision': basis['revision']}, accepted=selected)

    def select_curve_row(self, index, basis):
        if ((basis.get('document_id'), basis.get('session_id')) != (self.document_id, self.session_id)
                or basis['object_ref'] != self._object_ref or not self._sample_basis
                or self._sample_basis.get('revision') != basis.get('revision')
                or self._current_sample_revision(basis['preview']) != basis['revision']):
            self.message.setText('이전 곡선 조회입니다. 현재 결과를 다시 읽으세요.')
            return False
        owner = (self.document_id, self.session_id)
        token = (self._object_ref, basis['revision'])
        def accepted(payload):
            if (owner != (self.document_id, self.session_id)
                    or token != (self._object_ref, (self._sample_basis or {}).get('revision'))
                    or token != (payload.get('object_ref'), payload.get('revision'))
                    or self._current_sample_revision(basis['preview']) != token[1]):
                return
            for row, item in enumerate((self._samples or {}).get('rows', [])):
                if item.get('row_index', item.get('row')) == index:
                    self.samples.selectRow(row); break
            self._confirmed_sample_selection = (index, deepcopy(basis))
            self.sampleSelectionChanged.emit(index, basis)
        return self.queue_command('post.sample', {'object_ref': self._object_ref,
            'preview': basis['preview'], 'row_index': index, 'expected_revision': basis['revision']},
            accepted=accepted)

    def read_samples(self):
        arguments = {'preview': self.sample_preview.isChecked(), 'offset': self.offset.value(), 'limit': self.limit.value()}
        if self.point_index.text().strip() and self.edited_draft().get('version') != 3:
            arguments['point_index'] = integer_or_raw(self.point_index.text())
        return self.object_command('post.sample', arguments) if not self._object_ref else self.queue_command('post.sample',
            {'object_ref': self._object_ref, **arguments}, accepted=self._show_samples)

    def _sample_selected(self):
        if self._busy or self._pending or not self._sample_basis:
            return False
        selected = self.samples.selectionModel().selectedRows()
        rows = (self._samples or {}).get('rows', [])
        if not selected or not 0 <= selected[0].row() < len(rows):
            return False
        if self._sample_basis.get('failed'):
            self.message.setText('이전 선택 요청을 완료하지 못했습니다. 현재 결과를 다시 읽으세요.')
            return False
        row, basis = rows[selected[0].row()], deepcopy(self._sample_basis)
        if basis['draft'].get('version') == 3 and type(row.get('row_index')) is int:
            return self.select_curve_row(row['row_index'], basis)
        if basis['draft'].get('measurement') in ('surface_average', 'surface_time', 'gauge_time') and type(row.get('row')) is int:
            return self.select_curve_row(row['row'], basis)
        if type(row.get('point_index')) is int:
            return self.select_comparison_point(row['point_index'], basis)
        return False

    def _show_samples(self, payload):
        sample_signals = QSignalBlocker(self.samples)
        self._samples = deepcopy(payload)
        obj = self._object()
        preview = payload.get('preview', self.sample_preview.isChecked())
        revision = next((row for row in (obj or {}).get('history', []) if row.get('id') == payload.get('revision')), None)
        if revision is None:
            if preview:
                revision = (obj or {}).get('preview')
            else:
                history, position = (obj or {}).get('history', []), (obj or {}).get('position', -1)
                revision = history[position] if 0 <= position < len(history) else None
        self._sample_basis = {'document_id': self.document_id, 'session_id': self.session_id,
                              'object_ref': self._object_ref, 'title': obj.get('title', '측정') if obj else '분석',
                              'preview': preview, 'revision': payload.get('revision'),
                              'draft': deepcopy((revision or {}).get('recipe', (obj or {}).get('draft', self._draft)))}
        rows = payload.get('rows', [])[:1000]
        if payload.get('semantics') == 'retained_curve_comparison' and not rows:
            rows = payload.get('originals', {}).get('a', [])[:1000]
        summary = payload.get('summary') or (revision or {}).get('summary', {})
        if (self._kind == 'comparison' and isinstance(self._draft, dict)
                and self._draft.get('version') in (2, 3)
                and hasattr(self.comparison_editor, 'set_result_summary')):
            self.comparison_editor.set_result_summary(summary)
        curve_table = payload.get('semantics') == 'retained_curve_comparison'
        if curve_table:
            self.message.setText(summary.get('blocked') or
                ('대응 가능한 표본 ' + str(summary.get('valid_count', 0)) + '개 / ' + str(summary.get('count_a', 0)) + '개'))
        if summary.get('comparison_version') == 2:
            counts = summary.get('finitecounts', {}).get('delta', {})
            self.message.setText('비교 ' + str(summary.get('recipe', {}).get('target', {}).get('units', ''))
                + '   유효 ' + str(counts.get('finite', counts.get('finite_count', '')))
                + ' / ' + str(summary.get('point_count', '')))

        def columns(row):
            values = {}
            for key, value in row.items():
                if key == 'block' and not value:
                    continue
                if key in ('values', 'validity') and isinstance(value, dict):
                    for name, item in value.items():
                        if isinstance(item, list):
                            for component, number in enumerate(item):
                                values[name + '[' + str(component) + ']'] = number
                        else:
                            values[name + (' 유효성' if key == 'validity' else '')] = item
                else:
                    values[key] = value
            return values
        flat_rows = [columns(row) for row in rows]
        headers = list(dict.fromkeys(key for row in flat_rows for key in row))
        if self._sample_basis['draft'].get('measurement') == 'gauge':
            primary = ['GaugeRelativeDisplacement', 'GaugeRelativeDisplacement 유효성', 'coordinates']
            headers = [key for key in primary if key in headers] + [key for key in headers if key not in primary]
        if curve_table:
            headers = (['row_index', 'a_row', 'b_rows', 'x', 'a', 'b', 'delta', 'percent', 'reason', 'percent_reason']
                if payload.get('rows') else ['row_index', 'identity', 'x', 'y', 'quality', 'calculation', 'exclusion_reason'])
        self.samples.setColumnCount(len(headers))
        labels = {'row_index': '표본', 'a_row': 'A 원행', 'b_rows': 'B 원행',
                  'b_axis': 'B 양쪽 표본 좌표', 'weight': '보간 가중치', 'x': '가로축',
                  'a_valid': 'A 유효', 'b_valid': 'B 유효', 'a_segment': 'A 구간', 'b_segment': 'B 구간',
                  'reason': '대응 상태', 'row': '원본 행', 'point_index': '원본 점 번호', 'block': '자료 블록',
                  'load_parameter': '하중 계수 λ [1]', 'step': '단계', 'increment': '증분',
                  'valid': '유효 여부', 'validity_reason': '유효성 이유', 'a': '변환 A', 'b': '변환 B', 'delta': 'B − A',
                  'percent': '변화율 [%]', 'percent_valid': '변화율 유효', 'percent_reason': '변화율 상태',
                  'a_raw': '원 A', 'b_raw': 'A 위치의 원 B', 'coordinates': 'A 위치',
                  'A_original_components': '원 A 성분', 'B_sampled_original_components': '대응 B 원성분',
                  'A_common_components': '변환 A 전체 성분', 'B_common_components': '변환 B 전체 성분',
                  'original_a_ids': '원본 식별', 'vtkValidMask': '유효 마스크'}
        if summary.get('measurement') == 'gauge':
            labels['point_index'] = '결과 점 번호'
            labels['vtkOriginalPointIds'] = '끝점의 원본 VTK 점 번호'
            labels['GaugeRelativeDisplacement'] = '두 점 상대변위 [' + str(summary.get('units') or '?') + ']'
            labels['coordinates'] = '끝점 B 기준좌표 [' + str(summary.get('coordinate_units') or '?') + ']'
        if self._sample_basis['draft'].get('version') == 2:
            recipe = self._sample_basis['draft']
            for key in ('a', 'b', 'delta', 'A_common_components', 'B_common_components'):
                labels[key] += ' [' + str(recipe['target']['units']) + ']'
            for key in ('a_raw', 'A_original_components'):
                labels[key] += ' [' + str(recipe['a']['units']) + ']'
            for key in ('b_raw', 'B_sampled_original_components'):
                labels[key] += ' [' + str(recipe['b']['units']) + ']'
            labels['coordinates'] += ' [' + str(recipe['a']['coordinate_units']) + ']'
            if recipe.get('difference') == 'norm_of_difference':
                labels['delta'] = '|B − A| [' + str(recipe['target']['units']) + ']'
        if curve_table:
            unit = str(summary.get('recipe', {}).get('target_unit') or '?')
            source = summary.get('sources', {}).get('a', {})
            labels.update(identity='원행', y='원값 [' + str(source.get('declaration', {}).get('units') or '?') + ']',
                quality='품질', calculation='계산 포함', exclusion_reason='제외 사유', reason='대응', percent_reason='변화율 상태')
            labels['x'] += ' [' + str(source.get('axis', {}).get('unit') or '?') + ']'
            for key in ('a', 'b', 'delta'):
                labels[key] += ' [' + unit + ']'
        labels.update({key: key.removesuffix(' 유효성') + ' 유효성' for key in headers if key.endswith(' 유효성')})
        if self._sample_basis['draft'].get('measurement') == 'gauge':
            labels['GaugeRelativeDisplacement 유효성'] = '유효성'
        labels.update(Time='시각 [' + str(summary.get('time_units') or '?') + ']', SampleIndex='결과 행',
            SurfaceAreaAverage='면 평균 [' + str(summary.get('units') or '?') + ']',
            SurfaceArea='기준 면적 [' + str(summary.get('area_unit') or '?') + ']')
        if summary.get('measurement') == 'gauge_time':
            labels['GaugeRelativeDisplacement'] = '두 점 상대변위 [' + str(summary.get('units') or '?') + ']'
        self.samples.setHorizontalHeaderLabels([labels.get(key, key) for key in headers])
        for column, key in enumerate(headers):
            self.samples.horizontalHeaderItem(column).setToolTip(key)
        self.samples.setRowCount(len(rows))
        for row, values in enumerate(flat_rows):
            for column, key in enumerate(headers):
                value = values.get(key)
                states = {'valid': '유효', 'outside_domain': '대응 영역 밖', 'outside_b_domain': 'B 영역 밖',
                          'nonfinite_a': 'A 결측 / 무효', 'nonfinite_b': 'B 결측 / 무효',
                          'nonfinite_difference': '차이 연산 범위 초과', 'zero_a': '기준값 0',
                          'nonfinite_percent': '변화율 범위 초과', 'nonfinite_denominator': '분모 범위 초과', 'percent_disabled': '계산 안 함', 'unknown': '알 수 없음'}
                text = ('값 없음' if value is None else ('유효' if value else '무효') if isinstance(value, bool)
                        else states.get(value, value) if isinstance(value, str) else display(value))
                if curve_table:
                    from .post_curve_plot import text as curve_text
                    text = curve_text(value)
                    if key == 'row_index':
                        text = str(int(value)+1) if value is not None else '—'
                    elif key in ('a_row', 'identity') and isinstance(value, dict):
                        text = str(value.get('row', '—'))
                    elif key == 'b_rows' and isinstance(value, list):
                        text = ' → '.join(str(v.get('row', '—')) for v in value) or '—'
                    elif key in ('quality', 'calculation') and value in (0, 1):
                        text = ('정상' if value else '결측·품질 실패') if key == 'quality' else ('포함' if value else '제외')
                item = QTableWidgetItem(text)
                item.setToolTip(display(value))
                self.samples.setItem(row, column, item)
                self.samples.setColumnWidth(column, max(100, min(180, len(key) * 9)))
        if self._sample_basis['draft'].get('measurement') == 'gauge':
            for key, width in [('GaugeRelativeDisplacement', 180), ('GaugeRelativeDisplacement 유효성', 70), ('coordinates', 190)]:
                if key in headers:
                    self.samples.setColumnWidth(headers.index(key), width)
        sample_signals.unblock()
        self.result_plot.set_samples(payload, self._sample_basis['draft'])
        self._compact_samples(payload, self._sample_basis['draft'])
        self._update_actions()
        self._show_details()

    def capture_selection(self):
        draft = self.edited_draft()
        if draft.get('measurement') not in ('point', 'time', 'gauge', 'gauge_time') or draft.get('association') != 'POINTS':
            self.message.setText('원본 점 선택은 점 측정과 시간 이력에서 사용합니다. 경로는 두 끝점 좌표를 지정하세요.')
            return False
        source, array = draft.get('source_ref'), draft.get('array')
        if not source or not array:
            self.message.setText('원자료와 정확한 점 필드를 먼저 선택하세요.')
            if draft.get('measurement') == 'gauge':
                self.gauge_notice.setText(self.message.text())
                self.gauge_notice.show()
            return False
        def accepted(payload):
            captured = payload['draft']
            prepared = deepcopy(captured)
            # Capture supplies original IDs and known declarations. Explicit
            # edits still need review/store through the existing owner gates.
            captured_fields = {'point_indices', 'point1', 'point2', 'original_point_ids', 'time', 'reference_time'} if draft.get('measurement') in ('gauge', 'gauge_time') else {'point_indices'}
            prepared.update({key: deepcopy(value) for key, value in draft.items()
                             if key not in captured_fields and value is not None})
            if prepared.get('measurement') == 'time':
                prepared.pop('time', None)
            self._object_ref = payload['id']
            self._tree_selection = ('object', payload['id'])
            self._kind, self._draft = 'measurement', deepcopy(captured)
            self.local_dirty = False
            self._show_document(self.document, preserve_buffer=False)
            if prepared != captured:
                self._draft = prepared
                self.local_dirty = True
                self._edit_serial += 1
                self._populate_editor()
        arguments = {'source_ref': source, 'array': array}
        if draft.get('measurement') in ('gauge', 'gauge_time'):
            arguments['measurement'] = draft['measurement']
            if draft.get('measurement') == 'gauge_time' and draft.get('reference_time') is not None:
                arguments['reference_time'] = draft['reference_time']
        return self.queue_command('post.measurement_capture', arguments, accepted=accepted)

    def capture_surface_faces(self):
        draft = self.edited_draft()
        if draft.get('measurement') not in ('surface_average', 'surface_time') or not draft.get('source_ref') or not draft.get('array'):
            self.message.setText('먼저 원 자료와 평균할 필드를 지정하세요.')
            return False
        token = self._context_token()
        serial = self._edit_serial
        def available(payload):
            dialog = QDialog(self)
            dialog.setModal(True)
            dialog.setWindowTitle('원본 경계 면 선택')
            dialog.resize(780, 520)
            layout = QVBoxLayout(dialog)
            clock = '시각 정보 없음' if payload['reference_time'] is None else '기준 시각 ' + str(payload['reference_time']) + ' [' + str(draft.get('time_units') or '단위 미지정') + ']'
            label = QLabel(clock + ': 평균에 포함할 원본 경계 면을 명시적으로 선택하세요.\n셀 전체나 내부 면을 자동 포함하지 않습니다.')
            label.setWordWrap(True)
            layout.addWidget(label)
            tree = QTreeWidget()
            tree.setHeaderLabels(['포함할 원본 셀 / 경계 면', '원본 VTK 점 번호', '기준 좌표'])
            tree.setColumnWidth(0, 180); tree.setColumnWidth(1, 160)
            layout.addWidget(tree, 1)
            page = QHBoxLayout()
            previous, next_page, count = QPushButton('이전 면'), QPushButton('다음 면'), QLabel()
            page.addWidget(previous); page.addWidget(count, 1); page.addWidget(next_page)
            layout.addLayout(page)
            buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
            buttons.button(QDialogButtonBox.StandardButton.Ok).setText('선택한 면 사용')
            buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)
            state = {'selected': {(face['cell_index'], face['face_index']): deepcopy(face) for face in draft.get('surface_faces', [])}, 'page': None, 'closed': False}
            def changed(item, _column):
                face = item.data(0, Qt.ItemDataRole.UserRole)
                key = (face['cell_index'], face['face_index'])
                if item.checkState(0) == Qt.CheckState.Checked:
                    state['selected'][key] = deepcopy(face)
                else:
                    state['selected'].pop(key, None)
                buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(bool(state['selected']))
            tree.itemChanged.connect(changed)
            def fill(result):
                if state['closed']:
                    return
                if token != self._context_token() or serial != self._edit_serial or result['reference_time'] != payload['reference_time']:
                    dialog.reject()
                    return
                state['page'] = result
                blocker = QSignalBlocker(tree)
                tree.clear()
                for face in result['faces']:
                    row = QTreeWidgetItem([str(face['cell_index']) + ' / ' + ('표면 셀' if face['face_index'] is None else str(face['face_index'])),
                        ({6:'TRI6 · 원 절점 6개',8:'QUAD8 · 원 절점 8개'}.get(len(face['point_indices']), field_text(face['point_indices']))), str(face['coordinates'])])
                    row.setData(0, Qt.ItemDataRole.UserRole, deepcopy(face))
                    row.setCheckState(0, Qt.CheckState.Checked if (face['cell_index'], face['face_index']) in state['selected'] else Qt.CheckState.Unchecked)
                    row.setToolTip(1, field_text(face['point_indices']))
                    row.setToolTip(2, str(face['coordinates']) + '\n원 ID: ' + str(face['original_point_ids']))
                    tree.addTopLevelItem(row)
                count.setText(str(result.get('offset', 0) + (1 if result['faces'] else 0)) + '–' + str(result.get('offset', 0) + len(result['faces'])) +
                    ' / ' + str(result.get('total', len(result['faces']))))
                previous.setEnabled(result.get('offset', 0) > 0)
                next_page.setEnabled(result.get('has_more', False))
                tree.setEnabled(True)
                buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(bool(state['selected']))
                blocker.unblock()
            def fetch(step):
                if state['closed'] or self._busy or self._pending:
                    return
                current = state['page']
                previous.setEnabled(False); next_page.setEnabled(False)
                tree.setEnabled(False)
                buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)
                count.setText('원본 경계 면을 읽는 중…')
                self.queue_command('post.measurement_capture', {'source_ref': draft['source_ref'], 'array': draft['array'],
                    'measurement': draft['measurement'], 'reference_time': payload['reference_time'],
                    'offset': max(0, current.get('offset', 0) + step * 200), 'limit': 200}, accepted=fill)
            previous.clicked.connect(lambda: fetch(-1)); next_page.clicked.connect(lambda: fetch(1))
            buttons.accepted.connect(dialog.accept); buttons.rejected.connect(dialog.reject)
            layout.addWidget(buttons)
            def finished(result):
                state['closed'] = True
                if (result == QDialog.DialogCode.Accepted and token == self._context_token()
                        and serial == self._edit_serial and not self._pending and not self._busy and not self.conflict):
                    self._draft = self.edited_draft()
                    self._draft.update(surface_faces=list(state['selected'].values()), geometry=payload['geometry'])
                    self._draft['time' if draft['measurement'] == 'surface_average' else 'reference_time'] = payload['reference_time']
                    self._populate_editor(); self._edited()
                dialog.deleteLater()
            dialog.finished.connect(finished)
            fill(payload)
            dialog.open()
        return self.queue_command('post.measurement_capture', {'source_ref': draft['source_ref'], 'array': draft['array'],
            'measurement': draft['measurement'], 'reference_time': draft.get('time' if draft['measurement'] == 'surface_average' else 'reference_time'),
            'offset': 0, 'limit': 200}, accepted=available)

    def swap_gauge_points(self):
        if self._busy or self._pending is not None or self.conflict:
            return False
        draft = self.edited_draft()
        if draft.get('measurement') not in ('gauge', 'gauge_time') or len(draft.get('point_indices', [])) != 2:
            self.message.setText('두 원본 점을 먼저 가져오세요.')
            return False
        draft['point_indices'] = list(reversed(draft['point_indices']))
        draft['point1'], draft['point2'] = draft.get('point2'), draft.get('point1')
        if isinstance(draft.get('original_point_ids'), dict):
            draft['original_point_ids'] = {name: list(reversed(values)) for name, values in draft['original_point_ids'].items()}
        self._draft = draft
        self._populate_editor()
        self._edited()
        return True

    def show_comparison_originals(self, a, b):
        if not a or not b:
            self.message.setText('두 원 자료를 선택하세요.')
            return False
        return self.queue_command('post.source_select', {'source_ref': a, 'compare_with': b})

    def show_comparison_result(self):
        obj = self._object()
        extra = {'array': self.comparison_display.currentData()} if obj and obj.get('kind') == 'comparison' and obj.get('draft', {}).get('version') == 2 else {}
        return self.object_command('post.show_analysis', extra)

    def show_comparison_source(self, source_ref):
        if not source_ref:
            self.message.setText('원 자료를 선택하세요.')
            return False
        view = self._view_arguments(source=True)
        if view is None:
            return False
        return self.queue_command('post.source_select', {'source_ref': source_ref, **view})

    def show_source(self):
        if self._source_ref:
            view = self._view_arguments(source=True)
            if view is None:
                return False
            return self.queue_command('post.source_select', {'source_ref': self._source_ref, 'show': True, **view})

    def _populate_views(self):
        selected = self.view_selector.currentData()
        self.view_selector.blockSignals(True)
        self.view_selector.clear()
        self.view_selector.addItem('현재 객체의 뷰', None)
        for view in (self.document or {}).get('state', {}).get('views', []):
            identifier = view.get('view_id')
            if isinstance(identifier, str) and identifier:
                self.view_selector.addItem(view.get('type', 'ParaView 뷰') + ' ' + str(self.view_selector.count()), identifier)
        index = self.view_selector.findData(selected)
        if index < 0 and selected is not None:
            self.view_selector.addItem('사용할 수 없는 뷰', selected)
            index = self.view_selector.count() - 1
        self.view_selector.setCurrentIndex(max(0, index))
        self.view_selector.blockSignals(False)

    def _view_arguments(self, *, source=False, source_ref=None):
        identifier = self.view_selector.currentData()
        if identifier is None:
            return {}
        view = next((item for item in (self.document or {}).get('state', {}).get('views', [])
            if item.get('view_id') == identifier), None)
        if view is None:
            self.message.setText('The exact selected native view is unavailable. Choose another view explicitly.')
            return None
        if source:
            record = next((item for item in self._sources() if item['source_ref'] == (source_ref or self._source_ref)), {})
            required = 'XYChartView' if (record.get('native_metadata') or {}).get('curve') else 'RenderView'
            if view.get('type') != required:
                self.message.setText('원 자료에 맞는 ' + ('차트' if required == 'XYChartView' else '3D') + ' 뷰를 선택하세요.')
                return None
        return {'view_id': identifier}

    def inspect_source(self):
        source = next((item for item in self._sources() if item['source_ref'] == self._source_ref), None)
        native = next((item for item in (self.document or {}).get('state', {}).get('sources', []) if source and item.get('label', item.get('name')) == source.get('reader_name')), None)
        if not native or not (native.get('id') or native.get('source_id') or native.get('proxy_id')):
            self.message.setText('This exact source has no current native proxy. Repair it before native inspection.')
            return False
        target = native.get('id') or native.get('source_id') or native.get('proxy_id')
        def accepted(payload):
            self.details.setPlainText(json.dumps({'native_inspection': payload, 'command': self._last_command}, ensure_ascii=False, indent=2))
            arrays = payload.get('data', {}).get('arrays')
            if arrays is not None:
                self._inspected_array_context = (self.document_id, self.session_id, self.document['generation'], self._source_ref)
                self._fill_arrays(arrays)
        return self.queue_command('post.inspect', {'target': {'source_id': target}}, accepted=accepted)

    def _fill_arrays(self, arrays):
        if isinstance(arrays, dict):
            arrays = [{**row, 'name': name} for name, row in arrays.items()]
        selected = self.array_table.selectionModel().selectedRows()
        previous = getattr(self, '_array_rows', [])
        key = None
        if selected and selected[0].row() < len(previous) and getattr(self, '_array_source_ref', None) == self._source_ref:
            item = previous[selected[0].row()]
            key = (item.get('association'), item.get('name'))
        matches = [i for i, item in enumerate(arrays) if key == (item.get('association'), item.get('name'))] if key else []
        self._array_source_ref = self._source_ref
        self._array_rows = deepcopy(arrays)
        blocker = QSignalBlocker(self.array_table)
        self.array_table.clearSelection()
        self.array_table.setCurrentCell(-1, -1)
        self.array_table.setRowCount(len(arrays))
        for row, item in enumerate(arrays):
            values = [item.get(key) for key in ('name', 'association', 'components', 'units')]
            values[1] = {'POINTS': '점 자료', 'CELLS': '셀 자료'}.get(values[1], values[1])
            values.append(self._array_meaning(item))
            for column, value in enumerate(values):
                cell = QTableWidgetItem('알 수 없음' if value is None else display(value))
                cell.setToolTip(str(item.get('measure') or '물리적 정의 미지정') if column == 4 else
                                str(item.get('association') or '') if column == 1 else cell.text())
                self.array_table.setItem(row, column, cell)
        if len(matches) == 1:
            self.array_table.selectRow(matches[0])
        blocker.unblock()
        self._array_selected()

    @staticmethod
    def _array_meaning(item):
        measure = item.get('measure')
        if not measure or measure in ('UNKNOWN', 'unknown'):
            return '미지정'
        if measure in ('section_force','section_moment','native_nodal_force') and item.get('quantity'):
            return str(item['quantity'])
        return {'displacement': '변위', 'cauchy_stress': 'Cauchy 응력', 'Cauchy': 'Cauchy 응력',
                'green_lagrange': 'Green–Lagrange 전체변형률', 'infinitesimal': '미소 전체변형률',
                'equivalent_plastic_strain': '등가 소성변형률', 'nodal_force': '절점힘'}.get(
                    measure, '기록된 정의')

    def _array_selected(self):
        rows = self.array_table.selectionModel().selectedRows()
        if not rows or rows[0].row() >= len(getattr(self, '_array_rows', [])):
            self.array_description.setText('필드를 선택하면 출력 위치와 물리적 정의를 볼 수 있습니다.')
            self.array_description.setToolTip('')
            self.array_component.clear()
            self._component_array_key = None
            self._update_actions()
            return
        item = self._array_rows[rows[0].row()]
        key = (self._source_ref, item.get('association'), item.get('name'))
        previous = self.array_component.currentData() if getattr(self, '_component_array_key', None) == key else None
        self.array_component.clear()
        if item.get('components') == 1:
            self.array_component.addItem('값', None)
        elif (isinstance(item.get('component_names'), list) and len(item['component_names']) == item.get('components')
              and all(isinstance(name, str) and name for name in item['component_names'])):
            self.array_component.addItem('크기 (ParaView)', 'Magnitude')
            for name in item['component_names']: self.array_component.addItem(name, name)
        index = self.array_component.findData(previous)
        if index >= 0: self.array_component.setCurrentIndex(index)
        self._component_array_key = key
        location = {'POINTS': '점 자료', 'CELLS': '셀 자료'}.get(item.get('association'), '출력 위치 미확인')
        units = '무차원 [1]' if item.get('units') == '1' else (str(item['units']) if item.get('units') else '단위 미지정')
        text = [str(item.get('name', '필드')) + ': ' + self._array_meaning(item) + ', ' + location + ', ' + units + '.']
        recovery = item.get('recovery')
        if recovery == 'native integration-point extrapolation and nodal averaging' and item.get('association') == 'POINTS':
            text.append('절점값은 적분점에서 외삽한 뒤 평균한 값입니다.')
            bounds = item.get('range') or []
            if item.get('measure') == 'equivalent_plastic_strain' and bounds and isinstance(bounds[0], (int, float)) and bounds[0] < 0:
                text.append('외삽·평균된 절점 결과에 음수가 포함되어 있습니다. 원값을 그대로 표시합니다.')
        elif recovery == 'native nodal force; reactions only at restrained DOFs':
            text.append('절점힘입니다. 구속된 자유도의 값만 반력으로 해석할 수 있습니다.')
        if item.get('shear_convention') == 'tensor_shear_not_engineering_shear':
            text.append('전단 성분은 텐서 전단변형률이며 공학 전단변형률과 구별합니다.')
        self.array_description.setText(' '.join(text))
        self.array_description.setToolTip('\n'.join(str(item[key]) for key in ('measure', 'recovery', 'shear_convention') if item.get(key)))
        if not self.array_component.count():
            self.array_description.setText(self.array_description.text()+' 실제 성분 목록이 없습니다. 필드 정보 읽기로 확인하세요.')
        self._update_actions()

    def _selected_measurement_field(self):
        selected = self.array_table.selectionModel().selectedRows()
        arrays = getattr(self, '_array_rows', [])
        if (not self._source_ref or self._tree_selection != ('source', self._source_ref)
                or getattr(self, '_array_source_ref', None) != self._source_ref
                or not selected or selected[0].row() >= len(arrays)):
            return None
        field = arrays[selected[0].row()]
        return field if field.get('association') == 'POINTS' and field.get('name') else None

    def measure_selected_array(self):
        field = self._selected_measurement_field()
        if not field or not (self.document or {}).get('connected') or self.conflict:
            self.message.setText('연결된 원자료에서 점 필드를 선택하세요. 셀 필드를 점 자료로 바꾸지는 않습니다.')
            return False
        if not self.new_object('measurement'):
            return False
        self._draft.update(array=field['name'], association=field['association'])
        self._populate_editor()
        _, declared = self._source_choice_metadata(self._source_ref)
        if any((row.get('name'), row.get('association')) == (field['name'], field['association'])
               for row in (declared or {}).get('arrays', [])):
            self.use_declarations()
        self.message.setText('선택한 필드의 전체 성분으로 측정을 준비했습니다. 원본 점이나 경로와 시각을 지정한 뒤 미리보기를 실행하세요.')
        self._update_actions()
        return True

    def show_selected_array(self):
        rows = self.array_table.selectionModel().selectedRows()
        if not rows or not self.array_component.count(): return False
        item = self._array_rows[rows[0].row()]
        source = next((row for row in self._sources() if row['source_ref'] == self._source_ref), None)
        state = (self.document or {}).get('state', {})
        native = [row for row in state.get('sources', []) if source and row.get('label', row.get('name')) == source.get('reader_name')]
        view_id = self.view_selector.currentData() or state.get('active_view_id')
        view = next((row for row in state.get('views', []) if row.get('view_id') == view_id), None)
        if len(native) != 1 or not (native[0].get('id') or native[0].get('source_id') or native[0].get('proxy_id')):
            self.message.setText('선택한 원자료를 ParaView에서 찾을 수 없습니다. 원파일을 다시 연결하세요.'); return False
        if not view or view.get('type') != 'RenderView':
            self.message.setText('표시할 ParaView 3D 뷰를 선택하세요.'); return False
        arguments = {'association':item['association'], 'array':item['name'],
            'target':{'source_id':native[0].get('id') or native[0].get('source_id') or native[0].get('proxy_id'), 'view_id':view_id}}
        component = self.array_component.currentData()
        if component is not None: arguments['component'] = component
        return self.queue_command('post.select_array', arguments)

    def _show_arrays(self):
        source = next((item for item in self._sources() if item['source_ref'] == self._source_ref), None)
        if source:
            metadata = source.get('native_metadata') or source.get('metadata') or {}
            arrays = deepcopy(metadata.get('arrays', []))
            if isinstance(arrays, dict): arrays = [{**row, 'name':name} for name,row in arrays.items()]
            context = (self.document_id, self.session_id, self.document['generation'], self._source_ref)
            if getattr(self, '_inspected_array_context', None) == context and getattr(self, '_array_source_ref', None) == self._source_ref:
                observed = {(row.get('association'), row.get('name')):row for row in getattr(self, '_array_rows', [])}
                for row in arrays:
                    actual = observed.get((row.get('association'), row.get('name')), {})
                    if 'component_names' not in row and row.get('components') == actual.get('components') and actual.get('component_names'):
                        row['component_names'] = actual['component_names']
            self._fill_arrays(arrays)
        else:
            self._fill_arrays([])

    def choose_source(self, *, repair=False):
        if repair and not self._source_ref:
            self.message.setText('Select the exact unavailable original source to repair.')
            return False
        token = self._context_token()
        def roots(payload):
            choices = [item['id'] for item in payload.get('roots', [])]
            if not choices:
                self.message.setText('No source folders are approved for this service.')
                return
            name, accepted = QInputDialog.getItem(self, 'Approved result folder', 'Folder', choices, editable=False)
            if accepted and token == self._context_token():
                self._choose_directory(name, repair=repair, token=token)
        return self._call(self.client.local_roots, roots, relevant=lambda: token == self._context_token())

    def open_changed_source(self):
        source = next((row for row in self._sources() if row['source_ref'] == self._source_ref), None)
        if source is None or not source.get('files'):
            self.message.setText('원자료를 선택하세요. 원파일 정보가 없으면 후처리 문서를 다시 열어 읽으세요.'); return
        from .post_source_dialogs import SourceUpdateDialog
        self._source_update_dialog = SourceUpdateDialog(self, source)
        self._source_update_dialog.show()

    def _choose_directory(self, root, relative='', cursor=0, *, repair=False, token=None):
        token = self._context_token() if token is None else token
        def listed(payload):
            choices = [('.. parent folder', 'parent')] if relative else []
            choices += [(('[Folder] ' if item['directory'] else '') + item['name'], item) for item in payload['entries']
                        if item['directory'] or item['name'].lower().endswith(('.vtu', '.pvd')) or item['name'] in ('contact-inspection.json','shell_inspection.json','beam_inspection.json')]
            if payload.get('next_cursor') is not None:
                choices.append(('More files…', 'next'))
            if not choices:
                self.message.setText('No files are listed in this approved result folder.')
                return
            name, accepted = QInputDialog.getItem(self, 'Choose exact original result', root + '/' + relative, [label for label, _ in choices], editable=False)
            if not accepted or token != self._context_token():
                return
            selected = next(item for label, item in choices if label == name)
            if selected == 'parent':
                self._choose_directory(root, relative.rpartition('/')[0], repair=repair, token=token)
            elif selected == 'next':
                self._choose_directory(root, relative, payload['next_cursor'], repair=repair, token=token)
            elif selected['directory']:
                self._choose_directory(root, selected['relative'], repair=repair, token=token)
            else:
                self.register_source(root, selected['relative'], repair=repair, token=token)
        return self._call(lambda: self.client.local_inputs(root, relative, cursor=cursor), listed, relevant=lambda: token == self._context_token())

    def register_source(self, root, relative, *, repair=False, token=None):
        token = self._context_token() if token is None else token
        source_ref = self._source_ref
        def registered(receipt):
            arguments = {'input_id': receipt['id']}
            if repair:
                arguments['source_ref'] = source_ref
            self.queue_command('post.source_repair' if repair else 'post.source_add', arguments)
        return self._call(lambda: self.client.register_local_input(root, relative), registered, relevant=lambda: token == self._context_token())

    def _show_details(self):
        self.details.setPlainText(json.dumps({'selected_source': self._source_ref, 'selected_object': self._object_ref,
            'draft': self.edited_draft(), 'object': self._object(), 'restore_issues': self._analysis().get('restore_issues', []),
            'repair': self._analysis().get('repair', []), 'command': self._last_command, 'samples': self._samples}, ensure_ascii=False, indent=2))

    def contact_source(self):
        obj = self._object()
        ref = self._source_ref if self._tree_selection and self._tree_selection[0] == 'source' else (
            obj.get('draft', {}).get('source_ref') if obj else self._source_ref)
        return next((row for row in self._sources() if row['source_ref'] == ref), None)

    def open_contact_inspector(self):
        record = self.contact_source()
        if not record or not (record.get('native_metadata') or {}).get('contact_inspection'):
            self.message.setText('Select an original result with a registered contact inspection bundle.')
            return False
        from .post_contact_dialog import ContactDialog
        if self._contact_dialog is not None:
            self._contact_dialog.close()
        self._contact_dialog = ContactDialog(self, record['source_ref'])
        self._contact_dialog.show()
        return True

    def use_in_numerical(self):
        if self._measurement_handoff:
            return self._continue_measurement_handoff()
        obj = self._object()
        if not obj or obj['kind'] != 'measurement' or self.local_dirty:
            self.message.setText('Select an applied saved measurement; Apply and Save any recipe edits first.')
            return False
        def extracted(_payload):
            command_id = self._last_command['command_id']
            token = self._context_token()
            def previewed(payload):
                from .post_measurement_dialog import MeasurementDialog
                from PySide6.QtWidgets import QDialog
                dialog = self._measurement_dialog = MeasurementDialog(payload['snapshot'], self, plans=payload['plans'])
                if dialog.exec() != QDialog.DialogCode.Accepted or token != self._context_token():
                    return
                selection = deepcopy(dialog.selection)
                if selection is None:
                    return
                # Existing targets receive a pending review; their live editor is not reloaded.
                def context_ready(context):
                    self._measurement_handoff = {'command_id': command_id, 'selection': selection,
                        'session_id': context['service_session_id'], 'handoff_id': 'C' + uuid.uuid4().hex,
                        'target_plan_id': dialog.destination.currentData()}
                    self.handoff_retry.setVisible(True)
                    self._continue_measurement_handoff()
                self._call(self.client.desktop_context, context_ready)
            def read_preview():
                payload = self.client.post_measurement_preview(command_id)
                payload['plans'] = [doc for doc in self.client.documents()['documents']
                    if doc.get('kind') == 'numerical' and doc.get('draft', {}).get('mode') == 'request'
                    and doc['draft'].get('request', {}).get('operation') == 'fit']
                return payload
            self._call(read_preview, previewed, relevant=lambda: token == self._context_token())
        return self.queue_command('post.measurement_snapshot', {'object_ref': obj['id']}, accepted=extracted)

    def _schedule_measurement_poll(self):
        if (self._closed or self._measurement_poll_pending is None or
                self._measurement_poll_queued or self._busy or self._pending is not None):
            return
        self._measurement_poll_queued = True
        QTimer.singleShot(0, self._drain_measurement_poll)

    def _drain_measurement_poll(self):
        self._measurement_poll_queued = False
        pending = self._measurement_poll_pending
        if pending is not None and pending is self._measurement_handoff:
            self._continue_measurement_handoff()
        else:
            self._measurement_poll_pending = None

    def _continue_measurement_handoff(self):
        pending = self._measurement_handoff
        if self._closed or pending is None:
            self._measurement_poll_pending = None
            return False
        # Keep one intent across an overlapping document/native refresh. This
        # polls the same handoff; it must not start another import or Plan.
        if self._busy or self._pending is not None:
            self._measurement_poll_pending = pending
            return False
        self._measurement_poll_pending = None
        def received(payload):
            if self._measurement_handoff is not pending:
                return
            state = payload['state']
            if state == 'OBSERVATION_READY':
                return self._present_observation(payload, pending)
            if state == 'READY':
                document_id = payload['document']['id']
                from .desktop import launch_tool
                def opened(_receipt):
                    self._measurement_handoff = None
                    self.handoff_retry.setVisible(False)
                    self.message.setText('Measured curve opened in Numerical. Select the model, variables and predicted response before Run.')
                self._call(lambda: launch_tool(self.client, 'numerical', document_id=document_id), opened)
            elif state in {'FAILED', 'REJECTED', 'CANCELLED', 'INTERRUPTED'}:
                identifier = payload['data_document']['id']
                self.message.setText('Measurement import ' + state + '. Open Data ' + identifier +
                    ' to repair the mapping. ' + str(payload.get('error') or ''))
            else:
                self.message.setText('Importing measured samples: ' + state)
                QTimer.singleShot(250, self._continue_measurement_handoff)
        started = self._call(lambda: self.client.post_measurement_plan(**deepcopy(pending)), received)
        if not started:
            self._measurement_poll_pending = pending
        return started

    def _present_observation(self, payload, pending):
        from .result_return import observation_message, verify_result, receive_local, deliver_result
        if self._measurement_delivery is None:
            self._measurement_delivery = observation_message(self.client, payload['target_document']['id'],
                payload['target_document']['session_id'], payload['reference'], payload['role'])
        message = deepcopy(self._measurement_delivery)
        def received(receipt):
            if self._measurement_handoff is not pending:
                return
            state = receipt.get('status')
            if state in {'ATTACHED', 'ALREADY_ATTACHED', 'CANCELLED'}:
                self._measurement_handoff = self._measurement_delivery = None
                self.handoff_retry.setVisible(False)
                self.message.setText('Observation ' + state.lower().replace('_', ' ') +
                    '. Existing Plan edits were preserved; Apply and Save remain explicit.')
            elif state == 'PRESENTED':
                self.handoff_retry.setText('Check Plan review')
                self.message.setText('Observation presented in the existing Plan. Review and Append or Cancel there.')
            else:
                if state == 'REJECTED':
                    self._measurement_delivery = None
                    self.handoff_retry.setText('Review in Plan again')
                self.message.setText('Observation was not appended: ' + str(receipt))
        def verified(_payload):
            receipt = receive_local(message)
            if receipt is not None:
                received(receipt)
            else:
                self._call(lambda: deliver_result(self.client, message), received)
        return self._call(lambda: verify_result(self.client, message), verified)

    def _update_actions(self):
        self._schedule_measurement_poll()
        present = self.document is not None
        idle = not self._busy and self._pending is None
        enabled = present and idle and not self.conflict and self.document.get('connected', False)
        swap = self.findChild(QPushButton, 'swapGaugePoints')
        if swap is not None:
            swap.setEnabled(enabled)
        self.tree.setEnabled(idle)
        self.tabs.tabBar().setEnabled(idle)
        self.open_action.setEnabled(idle)
        self.refresh_button.setEnabled(idle)
        self.save_action.setEnabled(enabled)
        self.retry_button.setEnabled(not self._busy and self._pending is not None)
        self.add_source_button.setEnabled(enabled)
        self.repair_button.setEnabled(enabled and bool(self._source_ref))
        self.changed_source_button.setEnabled(enabled and bool(self._source_ref))
        self.show_source_button.setEnabled(enabled and bool(self._source_ref))
        self.inspect_button.setEnabled(enabled and bool(self._source_ref))
        self.select_array_button.setEnabled(enabled and bool(self.array_table.selectionModel().selectedRows())
            and bool(self.array_component.count()) and 'post.select_array' in self.document.get('capabilities', []))
        self.measure_array_button.setEnabled(enabled and not self.local_dirty and bool(self._selected_measurement_field()))
        self.array_component.setEnabled(enabled and bool(self.array_component.count()))
        source = self.contact_source()
        self.contact_button.setEnabled(enabled and bool(source and
            (source.get('native_metadata') or {}).get('contact_inspection'))
            and 'post.contact_inspect' in self.document.get('capabilities', []))
        if self._contact_dialog is not None:
            self._contact_dialog.sync()
        self.edit_button.setEnabled(enabled)
        self.preview_button.setEnabled(enabled)
        obj = self._object()
        self.numerical_button.setEnabled(enabled and bool(obj and obj['kind'] == 'measurement'
            and obj.get('position', -1) >= 0) and not self.local_dirty
            and 'post.measurement_snapshot' in self.document.get('capabilities', []))
        self.handoff_retry.setEnabled(idle and self._measurement_handoff is not None)
        self.apply_button.setEnabled(enabled and bool(obj and obj.get('preview')) and not self.local_dirty)
        self.view_selector.setEnabled(enabled)
        self.show_applied_button.setEnabled(enabled and bool(obj and obj.get('position', -1) >= 0))
        self.reset_button.setEnabled(enabled and bool(self._object_ref or self.local_dirty))
        self.undo_button.setEnabled(enabled and bool(obj and obj.get('position', -1) >= 0) and not self.local_dirty)
        self.redo_button.setEnabled(enabled and bool(obj and (obj.get('redo_stack') or obj.get('redo'))) and not self.local_dirty)
        self.export_button.setEnabled(enabled and bool(obj and obj.get('position', -1) >= 0) and not self.local_dirty)
        self.sample_button.setEnabled(enabled and bool(self._object_ref) and not self.local_dirty)
        self.comparison_curve_button.setEnabled(bool(self._samples and self._sample_basis and self._sample_basis['draft'].get('version') in (2, 3)))
        self.comparison_curve_button.setVisible(self._kind == 'comparison')
        self.comparison_display.setVisible(not bool(self._tree_selection and self._tree_selection[0] == 'source') and self._kind == 'comparison' and self.edited_draft().get('version') != 3)
        self.point_index.setEnabled(self.edited_draft().get('version') != 3)
        for button in self.new_buttons:
            button.setEnabled(enabled and not self.local_dirty)
        browsing = bool(self._tree_selection and self._tree_selection[0] == 'source')
        self.array_table.setVisible(browsing)
        self.array_description.setVisible(browsing)
        self.array_controls.setVisible(browsing)
        self.source_tools.setVisible(browsing)
        self.show_source_button.setVisible(browsing)
        self.show_applied_button.setVisible(not browsing)
        self.editor_toggle.setVisible(not browsing)
        self.editor_area.setVisible(not browsing and self.editor_toggle.isChecked())
        self.sample_tools.setVisible(not browsing)
        self.sample_controls.setVisible(not browsing and self.read_options.isChecked())
        self.samples.setVisible(not browsing)
        self.sample_context.setVisible(not browsing)
        self.return_editor.setVisible(browsing and bool(self.local_dirty or self._object_ref))
        if browsing:
            source = next((row for row in self._sources() if row['source_ref'] == self._source_ref), {})
            self.object_label.setText(self.source_title(source))
            self.selection_meaning.setText('선택한 원 결과의 필드 정보입니다. 표시할 필드와 시각은 ParaView에서 선택합니다.')
            if self.local_dirty:
                self.return_editor.setText('보관 중인 ' + ((obj or {}).get('title') or '새 분석') + ' 편집으로 돌아가기')
            else:
                self.return_editor.setText('선택한 측정으로 돌아가기')
        else:
            self.object_label.setText((obj or {}).get('title') or '새 ' + {'comparison': '결과 비교', 'filter': '필터', 'measurement': '측정'}[self._kind])
            self.selection_meaning.setText(self._recipe_meaning(self.edited_draft()))
            self.selection_meaning.setToolTip(json.dumps(self.edited_draft(), ensure_ascii=False))
        if self._sample_basis:
            basis = self._sample_basis
            target = (obj or {}).get('preview') if basis['preview'] else None
            if not basis['preview']:
                history, position = (obj or {}).get('history', []), (obj or {}).get('position', -1)
                target = history[position] if 0 <= position < len(history) else None
            stale = basis['draft'] != self.edited_draft() or bool(basis.get('revision') and
                basis['revision'] != (target or {}).get('id'))
            self.sample_context.setText(basis['title'] + ': ' + ('적용 전 미리보기' if basis['preview'] else '적용 결과') +
                (' — 현재 편집은 미적용입니다.' if self.local_dirty else '') + '\n' + self._recipe_meaning(basis['draft']))
            if stale:
                self.sample_context.setText('이전 조회 값입니다. 설정이나 적용 결과가 바뀌었으므로 다시 조회하세요.\n' + self.sample_context.text())
            if basis.get('failed'):
                self.sample_context.setText('최근 조회 실패. 아래 표는 마지막 성공 조회입니다.\n' + self.sample_context.text())
        else:
            self.sample_context.setText('아직 읽은 값이 없습니다. 설정을 확인하고 측정값을 읽으세요.')
        if hasattr(self, 'capture_button'):
            try:
                self.capture_button.setEnabled(enabled and (self.edited_draft().get('measurement') in ('surface_average', 'surface_time') or
                    self.edited_draft().get('measurement') in ('point', 'time', 'gauge', 'gauge_time')
                    and self.edited_draft().get('association') == 'POINTS'))
            except RuntimeError:
                pass
        if getattr(self, '_desktop_ready', False):
            self.source_settings.setVisible(browsing)
            self.selection_meaning.hide()
            # These legacy command owners now live in menus/toolbars.
            for widget in (self.edit_button, self.preview_button, self.apply_button, self.reset_button,
                           self.source_tools, self.sample_tools, self.add_source_button,
                           self.show_source_button, self.show_applied_button, self.contact_button):
                widget.hide()
            self.view_selector.setVisible(self.view_selector.count() > 1)
            self.edit_action.setEnabled(enabled and not browsing)
            source_ref = self._source_ref if browsing else self.edited_draft().get('source_ref')
            self.native_action.setEnabled(enabled and any(row['source_ref'] == source_ref for row in self._sources()))
            for action, button in self._command_actions:
                action.setEnabled(button.isEnabled())
            self._update_gauge_summary()
            if self.edited_draft().get('measurement') in ('surface_average', 'surface_time'):
                draft = self.edited_draft()
                direction = self.fields[('direction',)][0]
                direction.setVisible(draft.get('component') == 'projection')
                direction_label = self._forms['measurement'].labelForField(direction)
                if direction_label is not None:
                    direction_label.setVisible(draft.get('component') == 'projection')
                self.surface_summary.setText('선택한 원본 경계 면: ' + str(len(draft.get('surface_faces') or [])) + '개')
                required = ('units', 'measure', 'frame', 'coordinate_units', 'coordinate_frame', 'geometry')
                if draft.get('component') is not None:
                    required += ('basis',)
                missing = [LABELS[key] for key in required if not draft.get(key)]
                self.surface_conditions.setText('미결정: ' + ', '.join(missing) if missing else
                    '응답 [' + str(draft['units']) + '] / ' + str(draft['frame']) + '\n기준 좌표 [' + str(draft['coordinate_units']) + '] / 고정 기준 면적')
        self._compact_update(browsing, obj, idle)

    def choose_document(self):
        if self.local_dirty:
            self.message.setText('Keep or Reset the current draft before opening another existing native owner.')
            return False
        token = self._context_token()
        def listed(payload):
            documents = [doc for doc in payload.get('documents', []) if doc.get('kind') == 'post' and doc.get('connected')]
            if not documents:
                self.message.setText('No existing native Post owners are connected. Open the saved analysis in ParaView first.')
                return
            labels = [doc.get('title', '후처리 문서') + ' (' + str(index + 1) + ')' for index, doc in enumerate(documents)]
            label, accepted = QInputDialog.getItem(self, '열린 후처리로 전환', 'ParaView에서 열린 문서', labels, editable=False)
            if accepted and token == self._context_token():
                selected = documents[labels.index(label)]
                self._open_selected_document(selected)
        return self._call(self.client.documents, listed, relevant=lambda: token == self._context_token())

    def _open_selected_document(self, selected):
        from .result_return import activate_existing, bind_receiver
        token = self._context_token()
        def checked():
            receipt = activate_existing(self.client, selected['id'], session_id=selected['session_id'])
            return receipt, self.client.document_read(selected['id'])
        def accepted(payload):
            receipt, document = payload
            if receipt['status'] == 'ACTIVATED':
                self.message.setText('이미 열린 설정창으로 이동했습니다. 이 창의 편집은 유지됩니다.')
                return
            if (document.get('session_id') != selected['session_id'] or document.get('kind') != 'post'
                    or not document.get('connected')):
                self.message.setText('후처리 세션이 달라져 전환하지 않았습니다. 현재 편집은 유지됩니다.')
                return
            if not bind_receiver(self, document):
                return
            self.document_id, self.session_id = document['id'], document['session_id']
            self._source_ref = self._object_ref = self._tree_selection = None
            self._samples = self._sample_basis = self._confirmed_sample_selection = None
            with QSignalBlocker(self.samples):
                self.samples.setRowCount(0)
                self.samples.setColumnCount(0)
            self._draft = defaults(self._kind)
            self.view_selector.setCurrentIndex(0)
            self._show_document(document, initial=True)
        return self._call(checked, accepted, relevant=lambda: token == self._context_token() and not self.local_dirty)

    def closeEvent(self, event):
        if self._pending and not self._allow_close:
            self.message.setText('Wait for or recover the native command before closing these controls. ParaView remains the owner.')
            event.ignore()
            return
        if self.local_dirty and not self._allow_close:
            answer = QMessageBox.question(self, 'Unapplied analysis draft', 'Close these controls and discard their local unapplied edits? Saved native recipes remain in ParaView.',
                QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Cancel)
            if answer != QMessageBox.StandardButton.Discard:
                event.ignore()
                return
        self._closed = True
        self._measurement_poll_pending = None
        self.timer.stop()
        self.command_timer.stop()
        receiver = getattr(self, '_result_return', None)
        if receiver:
            receiver.close()
        event.accept()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--service', default=os.environ.get('CAELAB_SERVICE_URL'))
    parser.add_argument('--document-id', required=True)
    parser.add_argument('--session-id')
    args = parser.parse_args(argv)
    if not args.service:
        parser.error('--service or CAELAB_SERVICE_URL must identify the existing local service')
    app = QApplication.instance() or QApplication(sys.argv[:1])
    client = Client(args.service)
    from .result_return import activate_existing
    try:
        receipt = activate_existing(client, args.document_id, session_id=args.session_id)
        if receipt['status'] == 'ACTIVATED':
            return 0
        document = client.document_read(args.document_id)
        if (document.get('kind') != 'post' or not document.get('connected')
                or args.session_id is not None and document.get('session_id') != args.session_id):
            raise ValueError('현재 연결된 후처리 세션을 확인할 수 없습니다.')
    except (ValueError, RuntimeError, OSError) as error:
        print('후처리 설정창을 열지 못했습니다. ' + str(error), file=sys.stderr)
        return 2
    window = PostWindow(client, document_id=args.document_id, session_id=document['session_id'], auto_open=False)
    if not window._show_document(document, initial=True):
        print(window.message.text(), file=sys.stderr)
        return 0
    window.show()
    return app.exec()


if __name__ == '__main__':
    raise SystemExit(main())
