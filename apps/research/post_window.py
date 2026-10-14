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

from PySide6.QtCore import QThreadPool, QTimer, Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QApplication, QAbstractItemView, QCheckBox, QComboBox, QFormLayout,
    QDialog, QHBoxLayout, QHeaderView, QInputDialog, QLabel, QLineEdit, QMainWindow,
    QMenu, QMessageBox, QPlainTextEdit, QPushButton, QScrollArea, QSpinBox, QSplitter,
    QTabWidget, QTableWidget, QTableWidgetItem, QToolBar, QTreeWidget,
    QTreeWidgetItem, QToolButton, QVBoxLayout, QWidget,
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
}
SIDE_FIELDS = ('source_ref', 'array', 'association', 'quantity', 'units', 'measure', 'frame',
               'coordinate_units', 'coordinate_frame', 'time', 'time_units', 'time_origin')
VECTORS = {'origin', 'normal', 'offsets', 'values', 'point1', 'point2', 'point_indices'}
BOOLEANS = {'triangulate', 'crinkle', 'invert'}
NUMBERS = {'time', 'tolerance', 'scale_factor'}
LABELS = {'source_ref': '원 자료', 'array': '필드', 'association': '자료 위치 (POINTS/CELLS)',
          'quantity': '물리량', 'units': '응답 단위', 'measure': '물리적 정의', 'frame': '응답 좌표계',
          'coordinate_units': '좌표 단위', 'coordinate_frame': '좌표계',
          'time': '원 결과 시각 (없으면 비움)', 'time_units': '시간 단위',
          'time_origin': '시간 기준', 'point_indices': '원본 점 번호',
          'origin': '평면 원점 [x, y, z]', 'normal': '평면 법선 [x, y, z]',
          'point1': '첫 점 [x, y, z]', 'point2': '끝 점 [x, y, z]',
          'resolution': '선 구간 수', 'tolerance': '허용 오차',
          'offsets': '단면 위치', 'values': '등고값', 'scale_factor': '벡터 배율'}


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
        self.resize(1440, 900)
        self.setMinimumSize(1060, 700)
        toolbar = QToolBar('후처리')
        self.addToolBar(toolbar)
        self.open_action = QAction('후처리 문서 열기…', self, shortcut=QKeySequence.Open)
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
        self.message = QLabel('ParaView에서 후처리 문서를 열면 원 결과와 측정값을 선택할 수 있습니다.')
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
        self.array_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for col, width in ((1, 100), (2, 85), (3, 80), (4, 100)):
            self.array_table.setColumnWidth(col, width)
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
        self.editor_area.setMinimumHeight(240)
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
        self._populate_editor()
        self._update_actions()

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
            time = ('저장 시각의 이력' if values.get('measurement') == 'time' else
                    '시각 미지정' if values.get('time') is None else
                    '시각 ' + str(values['time']) + ' [' + str(values.get('time_units') or '단위 미지정') + ']')
            location = ('점 번호 ' + field_text(values['point_indices']) if values.get('point_indices') else
                        '선 ' + field_text(values.get('point1')) + ' → ' + field_text(values.get('point2'))
                        if values.get('measurement') == 'path' else str(values.get('association') or '위치 미지정'))
            return (original(values.get('source_ref')) + ': ' + str(values.get('array') or '필드 미지정') +
                    ' [' + str(values.get('units') or '단위 미지정') + '], ' + location + ', ' + time +
                    ', ' + str(values.get('frame') or '좌표계 미지정'))
        if draft.get('measurement') == 'contact_force':
            component = draft.get('component', 0)
            axis = 'XYZ'[component] if isinstance(component, int) and 0 <= component < 3 else str(component)
            return (original(draft.get('source_ref')) + ': ' + str(draft.get('quantity', '')) + ' 문서 전체 ' + axis +
                    ' 성분, A 면의 합력 [N]. 축: 정적 하중 계수 λ [1].')
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
        return {'document.save': '저장', 'post.sample': '측정값 조회', 'post.inspect': '필드 조회',
                'post.mapping_validate': '미리보기', 'post.apply': '적용', 'post.show_analysis': '적용 결과 표시',
                'post.contact_inspect': '접촉 결과 조회', 'post.measurement_snapshot': '측정 확인',
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
            item = QTreeWidgetItem([obj.get('title', obj['kind']), '미리보기' if obj.get('preview') else '적용됨' if obj.get('position', -1) >= 0 else '초안'])
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
        self.setWindowTitle('후처리 — ' + document.get('title', '문서') + (' *' if self.local_dirty else ''))
        self._show_arrays()
        self._show_details()
        self._update_actions()

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
            self.samples.setRowCount(0)
            self.samples.setColumnCount(0)
        self._update_actions()
        self._show_details()

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
        elif key in ('association', *BOOLEANS):
            field = QComboBox()
            field.setEditable(True)
            field.addItems(['POINTS', 'CELLS'] if key == 'association' else ['true', 'false'])
            field.setCurrentText(field_text(value).lower() if key in BOOLEANS else field_text(value))
            field.currentTextChanged.connect(self._edited)
        else:
            field = QLineEdit(field_text(value))
            if key in VECTORS:
                field.setPlaceholderText('Explicit comma-separated values')
            field.textEdited.connect(self._edited)
        field.setObjectName('post.' + '.'.join(path))
        self.fields[path] = (field, deepcopy(value))
        if form is not None:
            form.addRow(LABELS.get(key, key.replace('_', ' ').capitalize()), field)
        return field

    def _populate_editor(self):
        self._populating = True
        self.fields = {}
        for form in self._forms.values():
            while form.count():
                item = form.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
                elif item.layout():
                    while item.layout().count():
                        child = item.layout().takeAt(0)
                        if child.widget():
                            child.widget().deleteLater()
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
            self.measurement_kind.addItems(['point', 'path', 'time'])
            if draft.get('measurement') not in MEASUREMENT_FIELDS:
                self.measurement_kind.addItem(display(draft.get('measurement')))
            self.measurement_kind.setCurrentText(draft.get('measurement', 'point'))
            self.measurement_kind.currentTextChanged.connect(self._measurement_changed)
            form.addRow('측정 방식 (point/path/time)', self.measurement_kind)
            for key in MEASUREMENT_FIELDS.get(draft.get('measurement'), ()):
                self._form_field(form, key, draft.get(key, None if key in ('time', 'time_units', 'time_origin') else 'POINTS' if key == 'association' else ''), (key,))
                if key in MEASUREMENT_DECLARATIONS:
                    self.fields[(key,)][0].setPlaceholderText('Unknown unless explicitly declared')
            note = QLabel('Measurement meaning, units and frames are optional declarations. Blank remains unknown; native array names do not supply these meanings.')
            note.setWordWrap(True)
            form.addRow(note)
            declarations_button = QPushButton('저장된 물리량 정보 사용')
            declarations_button.clicked.connect(lambda checked=False: self.use_declarations())
            form.addRow(declarations_button)
            self.capture_button = QPushButton('Capture original native point selection')
            self.capture_button.clicked.connect(self.capture_selection)
            form.addRow(self.capture_button)
        self.tabs.blockSignals(True)
        self.tabs.setCurrentIndex(('comparison', 'filter', 'measurement').index(self._kind))
        self.tabs.blockSignals(False)
        self._populating = False
        self._update_actions()

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
        self._draft['measurement'] = kind
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
            self.message.setText('Keep the current draft before creating another analysis object.')
            self.tabs.blockSignals(True)
            self.tabs.setCurrentIndex(('comparison', 'filter', 'measurement').index(self._kind))
            self.tabs.blockSignals(False)
            return False
        self._kind, self._object_ref = kind, None
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
                                 (' 새 편집은 아직 적용하지 않았습니다.' if late_edit else ''))
        else:
            self._show_document(remote, preserve_buffer=True)
            error = command.get('outcome', {}).get('error', command.get('error', {}))
            self.message.setText('요청을 완료하지 못했습니다. 편집은 보관했습니다. ' +
                                 str(error.get('message', error) if isinstance(error, dict) else error))
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

    def object_command(self, operation, extra=None):
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
        else:
            from .post_comparison_plot import ComparisonPlot
            dialog = ComparisonPlot(self._samples, self._sample_basis, self)
            dialog.pointSelected.connect(lambda index: self.select_comparison_point(index, dialog.basis))
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dialog.show()

    def _current_sample_revision(self, preview):
        obj = self._object() or {}
        if preview:
            return (obj.get('preview') or {}).get('id')
        history, position = obj.get('history', []), obj.get('position', -1)
        return history[position]['id'] if 0 <= position < len(history) else None

    def select_comparison_point(self, index, basis):
        if (self._object_ref != basis['object_ref'] or not self._sample_basis
                or self._sample_basis.get('revision') != basis.get('revision')
                or self._current_sample_revision(basis['preview']) != basis.get('revision')):
            self.message.setText('선택한 곡선은 이전 조회입니다. 원 비교를 다시 열어 선택하세요.')
            return False
        token = (self._object_ref, basis.get('revision'))
        def selected(payload):
            if (token != (self._object_ref, (self._sample_basis or {}).get('revision'))
                    or token != (payload.get('object_ref'), payload.get('revision'))
                    or self._current_sample_revision(basis['preview']) != token[1]):
                return
            for row, value in enumerate((self._samples or {}).get('rows', [])):
                if value.get('point_index') == index:
                    self.samples.selectRow(row)
                    break
        return self.queue_command('post.sample', {'object_ref': self._object_ref,
            'preview': basis['preview'], 'point_index': index, 'limit': 1,
            'expected_revision': basis['revision']}, accepted=selected)

    def select_curve_row(self, index, basis):
        if (basis['object_ref'] != self._object_ref or not self._sample_basis
                or self._sample_basis.get('revision') != basis.get('revision')
                or self._current_sample_revision(basis['preview']) != basis['revision']):
            self.message.setText('이전 곡선 조회입니다. 현재 결과를 다시 읽으세요.')
            return False
        token = (self._object_ref, basis['revision'])
        def accepted(payload):
            if (token != (self._object_ref, (self._sample_basis or {}).get('revision'))
                    or token != (payload.get('object_ref'), payload.get('revision'))
                    or self._current_sample_revision(basis['preview']) != token[1]):
                return
            for row, item in enumerate((self._samples or {}).get('rows', [])):
                if item.get('row_index') == index:
                    self.samples.selectRow(row); break
        return self.queue_command('post.sample', {'object_ref': self._object_ref,
            'preview': basis['preview'], 'row_index': index, 'expected_revision': basis['revision']},
            accepted=accepted)

    def read_samples(self):
        arguments = {'preview': self.sample_preview.isChecked(), 'offset': self.offset.value(), 'limit': self.limit.value()}
        if self.point_index.text().strip() and self.edited_draft().get('version') != 3:
            arguments['point_index'] = integer_or_raw(self.point_index.text())
        return self.object_command('post.sample', arguments) if not self._object_ref else self.queue_command('post.sample',
            {'object_ref': self._object_ref, **arguments}, accepted=self._show_samples)

    def _show_samples(self, payload):
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
        self._sample_basis = {'object_ref': self._object_ref, 'title': obj.get('title', '측정') if obj else '분석',
                              'preview': preview, 'revision': payload.get('revision'),
                              'draft': deepcopy((revision or {}).get('recipe', (obj or {}).get('draft', self._draft)))}
        rows = payload.get('rows', [])[:1000]
        if payload.get('semantics') == 'retained_curve_comparison' and not rows:
            rows = payload.get('originals', {}).get('a', [])[:1000]
        summary = payload.get('summary') or (revision or {}).get('summary', {})
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
        self._update_actions()
        self._show_details()

    def capture_selection(self):
        draft = self.edited_draft()
        source, array = draft.get('source_ref'), draft.get('array')
        if not source or not array:
            self.message.setText('Choose an admitted original source and exact array before capturing its native point selection.')
            return False
        def accepted(payload):
            self._object_ref = payload['id']
            self._tree_selection = ('object', payload['id'])
            self._kind, self._draft = 'measurement', deepcopy(payload['draft'])
            self.local_dirty = False
            self._show_document(self.document, preserve_buffer=False)
        return self.queue_command('post.measurement_capture', {'source_ref': source, 'array': array}, accepted=accepted)

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

    def _view_arguments(self, *, source=False):
        identifier = self.view_selector.currentData()
        if identifier is None:
            return {}
        view = next((item for item in (self.document or {}).get('state', {}).get('views', [])
            if item.get('view_id') == identifier), None)
        if view is None:
            self.message.setText('The exact selected native view is unavailable. Choose another view explicitly.')
            return None
        if source:
            record = next((item for item in self._sources() if item['source_ref'] == self._source_ref), {})
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
                self._fill_arrays(arrays)
        return self.queue_command('post.inspect', {'target': {'source_id': target}}, accepted=accepted)

    def _fill_arrays(self, arrays):
        if isinstance(arrays, dict):
            arrays = [{**row, 'name': name} for name, row in arrays.items()]
        self.array_table.setRowCount(len(arrays))
        for row, item in enumerate(arrays):
            values = [item.get(key) for key in ('name', 'association', 'components', 'units')]
            values[1] = {'POINTS': '점 (POINTS)', 'CELLS': '셀 (CELLS)'}.get(values[1], values[1])
            values.append(item.get('metadata_status', 'explicit' if item.get('units') is not None else 'unknown'))
            values[-1] = {'explicit': '명시됨', 'unknown': '미지정', 'UNKNOWN': '미지정'}.get(values[-1], values[-1])
            for column, value in enumerate(values):
                self.array_table.setItem(row, column, QTableWidgetItem('알 수 없음' if value is None else display(value)))

    def _show_arrays(self):
        source = next((item for item in self._sources() if item['source_ref'] == self._source_ref), None)
        if source:
            metadata = source.get('native_metadata') or source.get('metadata') or {}
            self._fill_arrays(metadata.get('arrays', []))
        else:
            self.array_table.setRowCount(0)

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
                        if item['directory'] or item['name'].lower().endswith(('.vtu', '.pvd')) or item['name'] == 'contact-inspection.json']
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
                self.capture_button.setEnabled(enabled)
            except RuntimeError:
                pass

    def choose_document(self):
        if self.local_dirty:
            self.message.setText('Keep or Reset the current draft before opening another existing native owner.')
            return False
        token = self._context_token()
        def listed(payload):
            documents = [doc for doc in payload.get('documents', []) if doc.get('kind') == 'post']
            if not documents:
                self.message.setText('No existing native Post owners are connected. Open the saved analysis in ParaView first.')
                return
            labels = [doc.get('title', '후처리 문서') + ' (' + str(index + 1) + ')' for index, doc in enumerate(documents)]
            label, accepted = QInputDialog.getItem(self, '후처리 문서 열기', 'ParaView에서 열린 문서', labels, editable=False)
            if accepted and token == self._context_token():
                selected = documents[labels.index(label)]
                self.document_id, self.session_id = selected['id'], selected['session_id']
                self.document = None
                self._source_ref = self._object_ref = None
                self._tree_selection = None
                self._draft = defaults(self._kind)
                self.view_selector.setCurrentIndex(0)
                self.refresh_document(initial=True)
        return self._call(self.client.documents, listed, relevant=lambda: token == self._context_token())

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
    window = PostWindow(Client(args.service), document_id=args.document_id, session_id=args.session_id)
    window.show()
    return app.exec()


if __name__ == '__main__':
    raise SystemExit(main())
