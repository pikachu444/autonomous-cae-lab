"""PDE Model Builder, typed Settings and retained Graphics on the owner service.

No native backend is constructed in the window. Expressions remain declarative
strings until the existing adapter validator and explicitly submitted job use them.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
import math
import os
import sys
import uuid

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Qt, Signal
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QApplication, QComboBox, QFormLayout, QHBoxLayout, QInputDialog, QLabel,
    QLineEdit, QMainWindow, QMessageBox, QPushButton, QPlainTextEdit, QScrollArea, QSizePolicy,
    QSplitter, QTabWidget, QToolBar, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure

from caelab.pde_document import BACKENDS, default_draft, diagnostics, support_details
from caelab.workbench_client import Client

TERMINAL = {'SUCCEEDED', 'FAILED', 'CANCELLED', 'REJECTED', 'INTERRUPTED', 'PARTIAL_FAILURE'}
ROLE = Qt.ItemDataRole.UserRole


def display(value):
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, allow_nan=False)


def typed_value(text, original, path):
    """Untouched invalid JSON stays exact; edited invalid numbers remain draft text."""
    if text == display(original):
        return deepcopy(original)
    if original is None and text == '':
        return None
    numeric = type(original) in (int, float) or path[-1] in {
        'degree', 'diffusion', 'reaction', 'alpha', 'lame_lambda', 'lame_mu', 'start', 'end',
        'fraction', 'axis', 'max_l2_error', 'min_l2_rate', 'max_h1_seminorm_error',
        'min_h1_rate', 'max_residual_relative'} or any(key in path for key in (
            'lengths', 'cell_counts', 'step_counts', 'diffusion', 'reaction'))
    if numeric:
        try:
            value = float(text)
            if not math.isfinite(value):
                return text
            if type(original) is int or path[-1] in ('degree', 'axis') or 'cell_counts' in path or 'step_counts' in path:
                return int(value) if value.is_integer() else value
            return value
        except (ValueError, OverflowError):
            return text
    if type(original) is bool:
        return {'true': True, 'false': False}.get(text.lower(), text)
    return text


def at_path(value, path):
    for key in path:
        value = value[key]
    return value


def set_path(value, path, replacement):
    for key in path[:-1]:
        value = value[key]
    value[path[-1]] = replacement


def setting_label(path):
    """Readable form captions; the exact adapter path remains in the tooltip."""
    names = {'rhs': '우변 식', 'degree': '함수 공간 차수',
             'diffusion': '확산 계수', 'reaction': '반응 계수',
             'lame_lambda': 'Lamé lambda', 'lame_mu': 'Lamé mu',
             'dirichlet': 'Dirichlet 식', 'solution': '해 표현식',
             'sha256': '원본 확인값', 'data': '원본 메시 데이터',
             'lengths': '길이', 'type': '종류', 'value': '값', 'expression': '식',
             'alpha': '비선형 계수', 'start': '시작', 'end': '끝',
             'max_residual_relative': '상대 잔차 허용값',
             'max_l2_error': 'L2 오차 허용값', 'min_l2_rate': '최소 L2 수렴률',
             'max_h1_seminorm_error': 'H1 반노름 오차 허용값'}
    if path[-2:] == ('domain', 'type'):
        return '영역 형상'
    if len(path) >= 2 and path[-2] == 'boundaries' and path[-1] in {'xmin', 'xmax', 'ymin', 'ymax', 'zmin', 'zmax'}:
        return path[-1][0] + (' 최소 경계' if path[-1].endswith('min') else ' 최대 경계')
    if 'lengths' in path and isinstance(path[-1], int):
        axis = ('x', 'y', 'z')[path[-1]] if path[-1] < 3 else str(path[-1] + 1)
        return axis + ' 길이 [1]'
    for collection, caption in (('cell_counts', '메시 분할 수'), ('step_counts', '시간 단계 수')):
        if collection in path:
            indexes = path[path.index(collection) + 1:]
            return caption + (' (수준 ' + str(indexes[0] + 1) + ')' if indexes and isinstance(indexes[0], int) else '') + (
                ' ' + ('x', 'y', 'z')[indexes[1]] if len(indexes) > 1 and isinstance(indexes[1], int) and indexes[1] < 3 else '')
    if isinstance(path[-1], int):
        key_index = next((index for index in range(len(path) - 1, -1, -1)
                          if isinstance(path[index], str)), 0)
        key = path[key_index]
        caption = names.get(key, key.replace('_', ' ').capitalize())
        indexes = ', '.join(str(index + 1) for index in path[key_index + 1:] if isinstance(index, int))
        return caption + ' [' + indexes + ']'
    key = path[-1]
    if key in names:
        return names[key]
    caption = str(key).replace('_', ' ').capitalize()
    context = next((str(key).replace('_', ' ') for key in reversed(path[1:-1])
                    if isinstance(key, str) and key not in ('problem', 'settings')), '')
    return context.capitalize() + ': ' + caption if context else caption


class _Signals(QObject):
    finished = Signal(object, object)


class _Read(QRunnable):
    def __init__(self, function):
        super().__init__()
        self.function, self.signals = function, _Signals()

    def run(self):
        try:
            value = self.function()
        except Exception as error:
            message = str(error)
            if hasattr(error, 'read'):
                try:
                    message = error.read().decode('utf-8')
                except (OSError, UnicodeError):
                    pass
            self.signals.finished.emit(None, message)
        else:
            self.signals.finished.emit(value, None)


class PDEWindow(QMainWindow):
    document_kind = 'pde'
    tool_label = 'PDE'
    model_backends = BACKENDS
    model_default = staticmethod(default_draft)
    model_diagnostics = staticmethod(diagnostics)
    model_support = staticmethod(support_details)
    settings_sections = None
    field_label = staticmethod(setting_label)

    def __init__(self, client, *, document_id=None, poll_interval=2000,
                 auto_open=True, runner_open=None, result_open=None, plan_open=None):
        super().__init__()
        from .appearance import apply_appearance
        apply_appearance(QApplication.instance())
        self.client, self.document = client, None
        self.runner_open, self.result_open = runner_open, result_open
        self.plan_open = plan_open
        self._plan_commands = {}
        self.local_dirty = self.conflict = self._busy = self._populating = False
        self._allow_close = False
        self._draft = {}
        self.fields = {}
        self._workers = []
        self._comparison_windows = []
        self._selected_job = None
        self._result = None
        self._result_key = None
        self._build_ui()
        self.timer = QTimer(self)
        self.timer.setInterval(max(1, poll_interval))
        self.timer.timeout.connect(self.refresh_document)
        if poll_interval > 0:
            self.timer.start()
        if auto_open:
            self.open_document(document_id=document_id)

    def _build_ui(self):
        self.resize(1440, 900)
        self.setMinimumSize(1000, 680)
        files, edit = self.menuBar().addMenu('파일(&F)'), self.menuBar().addMenu('편집(&E)')
        self.new_action = QAction('새 모델…', self, shortcut=QKeySequence.New)
        self.open_action = QAction('모델 열기…', self, shortcut=QKeySequence.Open)
        self.save_action = QAction('저장', self, shortcut=QKeySequence.Save)
        self.undo_action = QAction('되돌리기', self, shortcut=QKeySequence.Undo)
        self.redo_action = QAction('다시 실행', self, shortcut=QKeySequence.Redo)
        self.new_action.triggered.connect(self.new_document)
        self.open_action.triggered.connect(self.choose_document)
        self.save_action.triggered.connect(self.save_document)
        self.undo_action.triggered.connect(lambda: self.command('document.undo'))
        self.redo_action.triggered.connect(lambda: self.command('document.redo'))
        files.addActions([self.new_action, self.open_action, self.save_action])
        edit.addActions([self.undo_action, self.redo_action])
        research = self.menuBar().addMenu('연구(&R)')
        self.plan_action = QAction('수치 계산 계획 열기', self)
        self.plan_action.triggered.connect(self.open_numerical_plan)
        research.addAction(self.plan_action)
        self.compare_action = QAction('보존 곡선 비교…', self)
        self.compare_action.triggered.connect(self.open_curve_comparison)
        research.addAction(self.compare_action)
        toolbar = QToolBar('PDE commands')
        toolbar.setMovable(False)
        self.addToolBar(toolbar)
        toolbar.addActions([self.new_action, self.open_action, self.save_action, self.undo_action, self.redo_action])
        self.apply_button = QPushButton('변경 적용')
        self.validate_button = QPushButton('입력 검사')
        self.evaluate_button = QPushButton('모델 평가')
        self.evaluate_button.setProperty('appearanceRole', 'primary')
        self.plan_button = QPushButton('수치 계산 계획')
        self.plan_button.setObjectName('pdeNumericalPlan')
        self.plan_button.setToolTip('Apply the model first. Open a frozen Numerical request without running a solver.')
        self.runner_button = QPushButton('실행 작업')
        self.post_button = QPushButton('Post에서 열기')
        for button, callback in ((self.apply_button, self.apply_inputs),
                                 (self.validate_button, self.validate_inputs),
                                 (self.evaluate_button, self.evaluate),
                                 (self.plan_button, self.open_numerical_plan),
                                 (self.runner_button, self.open_runner),
                                 (self.post_button, self.open_post)):
            button.clicked.connect(callback)
            if button not in (self.runner_button, self.post_button):
                toolbar.addWidget(button)
        root = QWidget()
        layout = QVBoxLayout(root)
        self.identity = QLabel('모델을 여는 중…')
        self.identity.setProperty('appearanceRole', 'title')
        self.message = QLabel()
        self.message.setWordWrap(True)
        layout.addWidget(self.identity)
        layout.addWidget(self.message)
        self.issue_summary = QLabel()
        self.issue_summary.setWordWrap(True)
        self.issue_summary.setStyleSheet('color: #9a3412;')
        self.issue_summary.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.issue_summary)
        self.save_state = QLabel()
        self.statusBar().addPermanentWidget(self.save_state)
        conflicts = QHBoxLayout()
        self.reload_button = QPushButton('Reload service version')
        self.copy_button = QPushButton('Keep edits as a new document')
        self.reload_button.clicked.connect(self.reload_remote)
        self.copy_button.clicked.connect(self.copy_edits)
        conflicts.addWidget(self.reload_button)
        conflicts.addWidget(self.copy_button)
        conflicts.addStretch()
        layout.addLayout(conflicts)
        vertical = self.workspace_splitter = QSplitter(Qt.Orientation.Vertical)
        horizontal = self.model_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabel('모델')
        self.tree.setMinimumWidth(150)
        self.tree.setObjectName('pdeModelBuilder')
        self.tree.currentItemChanged.connect(self._selection_changed)
        horizontal.addWidget(self.tree)
        settings = self.settings_panel = QWidget()
        settings.setMinimumWidth(240)
        settings_layout = QVBoxLayout(settings)
        self.settings_title = QLabel('속성')
        self.settings_title.setProperty('appearanceRole', 'section')
        settings_layout.addWidget(self.settings_title)
        self.backend = QComboBox()
        self.backend.setObjectName('pdeBackend')
        self.backend.setEditable(True)
        self.backend.addItems(self.model_backends)
        self.backend.currentTextChanged.connect(self._backend_changed)
        backend_note = QLabel('계산 방법 선택은 모델을 자동 변환하지 않습니다.')
        backend_note.setWordWrap(True)
        settings_layout.addWidget(backend_note)
        settings_layout.addWidget(self.backend)
        self.equation = QLabel()
        self.equation.setWordWrap(True)
        settings_layout.addWidget(self.equation)
        self.space = QLabel()
        self.space.setWordWrap(True)
        settings_layout.addWidget(self.space)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        settings_layout.addWidget(self.scroll, 1)
        self.support = QLabel()
        self.support.setWordWrap(True)
        settings_layout.addWidget(self.support)
        horizontal.addWidget(settings)
        graphics = QWidget()
        graph_layout = QVBoxLayout(graphics)
        self.graph_tabs = QTabWidget()
        self.domain_figure = Figure(constrained_layout=True)
        self.domain_canvas = FigureCanvasQTAgg(self.domain_figure)
        self.domain_axes = self.domain_figure.add_subplot(111)
        self.result_figure = Figure(constrained_layout=True)
        self.result_canvas = FigureCanvasQTAgg(self.result_figure)
        self.result_axes = self.result_figure.add_subplot(111)
        self.graph_tabs.addTab(self.domain_canvas, '모델 영역')
        self.graph_tabs.addTab(self.result_canvas, '계산 결과')
        self.graph_tabs.currentChanged.connect(self._update_actions)
        graph_layout.addWidget(self.graph_tabs, 1)
        self.result_selector = QComboBox()
        self.result_selector.currentIndexChanged.connect(self._result_selection_changed)
        graph_layout.addWidget(self.result_selector)
        self.point_controls = QWidget()
        point_row = QHBoxLayout(self.point_controls)
        point_row.setContentsMargins(0, 0, 0, 0)
        self.field_node = QComboBox()
        self.field_node.setObjectName('pdeRetainedNode')
        self.field_node.currentIndexChanged.connect(self._draw_result)
        point_row.addWidget(QLabel('절점'))
        point_row.addWidget(self.field_node)
        graph_layout.addWidget(self.point_controls)
        self.point_label = QLabel()
        self.point_label.setWordWrap(True)
        graph_layout.addWidget(self.point_label)
        self.history_controls = QWidget()
        channel_row = QHBoxLayout(self.history_controls)
        channel_row.setContentsMargins(0, 0, 0, 0)
        self.channel = QComboBox()
        self.node = QComboBox()
        self.channel.currentIndexChanged.connect(self._channel_changed)
        self.node.currentIndexChanged.connect(self._update_actions)
        self.read_curve_button = QPushButton('선택 이력 읽기')
        self.read_curve_button.clicked.connect(self.read_native_curve)
        channel_row.addWidget(self.channel)
        channel_row.addWidget(self.node)
        channel_row.addWidget(self.read_curve_button)
        graph_layout.addWidget(self.history_controls)
        self.compare_button = QPushButton('곡선 비교…')
        self.compare_button.setObjectName('compareRetainedResearchCurves')
        self.compare_button.clicked.connect(self.open_curve_comparison)
        result_actions = QHBoxLayout()
        result_actions.addWidget(self.runner_button)
        result_actions.addWidget(self.post_button)
        result_actions.addWidget(self.compare_button)
        graph_layout.addLayout(result_actions)
        self.result_label = QLabel('No retained evaluation selected')
        self.result_label.setWordWrap(True)
        graph_layout.addWidget(self.result_label)
        horizontal.addWidget(graphics)
        horizontal.setSizes([210, 345, 835])
        horizontal.setStretchFactor(0, 0)
        horizontal.setStretchFactor(1, 0)
        horizontal.setStretchFactor(2, 1)
        vertical.addWidget(horizontal)
        self.messages = QPlainTextEdit()
        self.messages.setReadOnly(True)
        self.messages.setObjectName('pdeDiagnostics')
        vertical.addWidget(self.messages)
        vertical.setSizes([710, 160])
        self.messages.hide()
        layout.addWidget(vertical, 1)
        self.details_action = QAction('기술 상세 표시', self, checkable=True)
        self.details_action.toggled.connect(self._details_toggled)
        self.menuBar().addMenu('보기(&V)').addAction(self.details_action)
        details_row = QHBoxLayout()
        details_row.addStretch()
        self.details_button = QPushButton('기술 상세')
        self.details_button.setCheckable(True)
        self.details_button.toggled.connect(self.details_action.setChecked)
        self.details_action.toggled.connect(self.details_button.setChecked)
        details_row.addWidget(self.details_button)
        layout.addLayout(details_row)
        self.setCentralWidget(root)
        self._update_actions()

    def _details_toggled(self, visible):
        self.messages.setVisible(visible)
        if visible:
            self.workspace_splitter.setSizes([650, 150])

    def _refresh_issue_summary(self):
        checks = getattr(self, '_input_checks', [])
        text = '\n'.join(str(row.get('message', '')) for row in checks)
        result = self._result or {}
        state = result.get('execution_status', result.get('status'))
        if state in {'FAILED', 'REJECTED', 'INTERRUPTED', 'PARTIAL_FAILURE'}:
            failure = result.get('failure') or result.get('diagnostics', {}).get('reason')
            if isinstance(failure, dict):
                failure = failure.get('message') or failure.get('reason')
            text += ('\n' if text else '') + str(failure or '계산이 완료되지 않았습니다. 기술 상세에서 원인을 확인하세요.')
        delivery_error = result.get('diagnostics', {}).get('field_delivery_error')
        if delivery_error:
            text += ('\n' if text else '') + '필드를 읽지 못했습니다. 기술 상세에서 원인을 확인하세요.'
        self.issue_summary.setText(text)
        self.issue_summary.setVisible(bool(text))

    def _refresh_result_caption(self):
        runs = self.document.get('runs', []) if self.document else []
        run = next((row for row in runs if row['job_id'] == self._selected_job), {})
        for index, row in enumerate(runs):
            node = getattr(self, '_run_nodes', {}).get(row['job_id'])
            if node:
                relation = '편집 전 입력' if row.get('is_current_input') and self.local_dirty else (
                    '현재 입력' if row.get('is_current_input') else '이전 입력')
                node.setText(0, '계산 ' + str(index + 1) + ' (' + relation + ')')
        if not self._selected_job:
            self.result_label.setText('계산 결과를 선택하세요.')
        elif not self._result:
            self.result_label.setText('선택한 계산 결과를 읽는 중…')
        else:
            state = self._result.get('execution_status', self._result.get('status', 'UNKNOWN'))
            status = {'SUCCEEDED': '완료', 'COMPLETED': '완료', 'FAILED': '실패', 'REJECTED': '실행 불가',
                      'CANCELLED': '취소', 'INTERRUPTED': '중단', 'PARTIAL_FAILURE': '일부 실패'}.get(state, str(state))
            relation = (' (편집 전 입력)' if self.local_dirty else ' (현재 입력)') if run.get('is_current_input') else (
                ' (이전 입력)' if run else '')
            self.result_label.setText('보존 결과: ' + status + relation)
            self.result_label.setToolTip(display(run))

    def _call(self, function, accepted):
        if self._busy:
            return False
        self._busy = True
        self._update_actions()
        worker = _Read(function)
        self._workers.append(worker)

        def finished(value, error):
            self._busy = False
            self._workers.remove(worker)
            if error:
                self.message.setText(error)
            else:
                accepted(value)
            self._update_actions()

        worker.signals.finished.connect(finished)
        QThreadPool.globalInstance().start(worker)
        return True

    def open_document(self, *, document_id=None, title=None, draft=None):
        return self._call(lambda: self.client.document_open(kind=self.document_kind, title=title or self.tool_label + ' research',
                          draft=draft, document_id=document_id), self._opened)

    def _opened(self, document):
        self.local_dirty = self.conflict = False
        self._result_key = self._result = None
        self._selected_job = document.get('runs', [{}])[-1].get('job_id') if document.get('runs') else None
        self._show_document(document)
        self.message.setText('모델을 열었습니다.')
        self._accept_result({})
        if self._selected_job:
            QTimer.singleShot(0, self.refresh_result)

    def _show_document(self, document, *, preserve_draft=None):
        selected = self.tree.currentItem()
        old = selected.data(0, ROLE) if selected else None
        self.document = deepcopy(document)
        self._draft = deepcopy(document['draft'] if preserve_draft is None else preserve_draft)
        self._input_checks = deepcopy(document.get('diagnostics', []))
        self.fields = {}
        self._populating = True
        self.backend.setCurrentText(display(self._draft.get('backend', '')))
        self.tree.clear()
        self._nodes = {}
        self._run_nodes = {}
        definitions = self.settings_sections or [
            ('영역', ('settings', 'problem', 'domain')),
            ('함수 공간', ('settings', 'mesh', 'degree')),
            ('방정식', ('settings', 'problem', 'weak_form')),
            ('경계 조건', ('settings', 'problem', 'boundaries')),
            ('Dirichlet — whole boundary', ('settings', 'problem', 'dirichlet')),
            ('초기 조건', ('settings', 'problem', 'initial')),
            ('기준해', ('settings', 'problem', 'reference')),
            ('메시', ('settings', 'mesh')),
            ('시간 이산화', ('settings', 'time')),
            ('세분화 방향', ('settings', 'refinement_axis')),
            ('평가 방법', ('settings', 'mode')),
            ('입력 출처', ('settings', 'input_provenance')),
            ('수치 허용값', ('settings', 'validation')),
        ]
        covered = set()
        for label, path in definitions:
            try:
                value = at_path(self._draft, path)
            except (KeyError, TypeError):
                continue
            item = QTreeWidgetItem(self.tree, [label])
            item.setData(0, ROLE, {'path': path, 'label': label})
            self._nodes[path] = item
            covered.add(path)
            if isinstance(value, dict):
                for key in value:
                    child_path = (*path, key)
                    caption = self.field_label(child_path) if self.document_kind == 'pde' else str(key)
                    child = QTreeWidgetItem(item, [caption])
                    child.setToolTip(0, str(key))
                    child.setData(0, ROLE, {'path': child_path, 'label': caption})
                    self._nodes[child_path] = child
        # Every raw setting remains visible and saveable, including unsupported keys.
        known_settings = {path[1] for path in covered}
        settings = self._draft.get('settings')
        if isinstance(settings, dict):
            for key in set(settings) - known_settings:
                path = ('settings', key)
                item = QTreeWidgetItem(self.tree, ['Unsupported setting: ' + str(key)])
                item.setData(0, ROLE, {'path': path, 'label': str(key)})
                self._nodes[path] = item
            problem = settings.get('problem')
            if isinstance(problem, dict):
                for key in problem:
                    path = ('settings', 'problem', key)
                    if path not in covered:
                        item = QTreeWidgetItem(self.tree, ['Unsupported problem setting: ' + str(key)])
                        item.setData(0, ROLE, {'path': path, 'label': str(key)})
                        self._nodes[path] = item
        results = QTreeWidgetItem(self.tree, ['계산 결과'])
        results.setData(0, ROLE, {'label': 'Evaluations', 'path': None})
        for index, run in enumerate(document.get('runs', [])):
            item = QTreeWidgetItem(results, ['계산 ' + str(index + 1) + (' (현재 입력)' if run.get('is_current_input') else ' (이전 입력)')])
            item.setData(0, ROLE, {'job_id': run['job_id'], 'label': 'Retained evaluation', 'path': None})
            self._run_nodes[run['job_id']] = item
        self.tree.expandToDepth(0)
        target = (self._run_nodes.get(old['job_id']) if old and old.get('job_id') else
                  self._nodes.get(tuple(old.get('path') or ())) if old else None)
        self._populating = False
        self.tree.setCurrentItem(target or self.tree.topLevelItem(0))
        self.identity.setText(document['title'])
        self.identity.setToolTip(document['id'] + ' / generation ' + str(document['generation']))
        self.setWindowTitle(document['title'] + ' — ' + self.tool_label + ' Research')
        self._show_support()
        self._update_actions()

    def edited_draft(self):
        draft = deepcopy(self._draft)
        for path, (widget, original) in self.fields.items():
            text = widget.toPlainText() if isinstance(widget, QPlainTextEdit) else widget.text()
            set_path(draft, path, typed_value(text, original, path))
        return draft

    def _capture_settings(self):
        if self.fields:
            self._draft = self.edited_draft()
        self.fields = {}

    def _selection_changed(self, current, previous=None):
        if self._populating or current is None:
            return
        self._capture_settings()
        data = current.data(0, ROLE) or {}
        self.settings_title.setText('속성 — ' + data.get('label', ''))
        widget = QWidget()
        widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        form = QFormLayout(widget)
        form.setAlignment(Qt.AlignmentFlag.AlignTop)
        form.setFormAlignment(Qt.AlignmentFlag.AlignTop)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        path = data.get('path')
        if path:
            try:
                self._add_fields(form, at_path(self._draft, path), tuple(path))
            except (KeyError, TypeError):
                form.addRow(QLabel('Original malformed settings remain preserved; use Undo or create a new model.'))
        else:
            form.addRow(QLabel('Retained results belong to their exact submitted input revision.'))
        self.scroll.setWidget(widget)
        self._draw_domain(path)
        if data.get('job_id'):
            if self._selected_job != data['job_id']:
                self._selected_job = data['job_id']
                self._result_key = None
                self._accept_result({})
                self._result = None
                self.result_label.setText('Reading the selected retained evaluation: ' + self._selected_job)
            self.refresh_result()
        self._update_actions()

    def _add_fields(self, form, value, path):
        if isinstance(value, dict):
            if not value:
                form.addRow(QLabel('Empty declared object (preserved).'))
            for key, item in value.items():
                self._add_fields(form, item, (*path, key))
            return
        if isinstance(value, list):
            for index, item in enumerate(value):
                self._add_fields(form, item, (*path, index))
            # List edits are explicit and preserve exact existing entries.
            if path[-1] in ('cell_counts', 'step_counts', 'levels'):
                buttons = QHBoxLayout()
                add = QPushButton('Add ' + ('mesh source level' if path[-1] == 'levels' else 'level'))
                remove = QPushButton('Remove last level')
                add.clicked.connect(lambda _=False, p=path: self._resize_list(p, True))
                remove.clicked.connect(lambda _=False, p=path: self._resize_list(p, False))
                buttons.addWidget(add)
                buttons.addWidget(remove)
                form.addRow(buttons)
            return
        label = QLabel(self.field_label(path))
        label.setWordWrap(True)
        label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        adapter_path = '.'.join(str(key) for key in path[1:])
        label.setToolTip(adapter_path)
        if isinstance(value, str) and ('\n' in value or path[-1] in ('data', 'rhs', 'solution', 'source')):
            field = QPlainTextEdit('' if value is None else display(value))
            field.setFixedHeight(130 if path[-1] == 'data' else 90)
            field.textChanged.connect(self._edited)
        else:
            field = QLineEdit('' if value is None else display(value))
            field.textEdited.connect(self._edited)
        field.setObjectName('pde.' + '.'.join(map(str, path)))
        if value is None:
            field.setPlaceholderText('미지정')
        field.setToolTip(adapter_path + '\nNumbers are parsed without evaluating expressions. Invalid text can be saved.')
        if path[-1] == 'sha256':
            field.setToolTip(adapter_path + '\nExact mesh source content SHA-256. Editing bytes does not silently recompute or replace this identity.')
        self.fields[path] = (field, deepcopy(value))
        form.addRow(label, field)

    def _resize_list(self, path, add):
        self._capture_settings()
        rows = at_path(self._draft, path)
        if add:
            rows.append({'format': 'gmsh_msh2_ascii', 'source': '', 'sha256': '', 'data': ''}
                        if path[-1] == 'levels' else '')
        elif rows:
            rows.pop()
        self._edited()
        self._selection_changed(self.tree.currentItem())

    def _backend_changed(self, text):
        if self._populating:
            return
        self._draft['backend'] = text
        self._edited()

    def _edited(self, *_):
        if self._populating:
            return
        self.local_dirty = True
        self._update_actions()

    def validate_inputs(self):
        draft = self.edited_draft()

        def checked():
            return self.model_diagnostics(draft), self.model_support(draft)

        def accepted(result):
            checks, details = result
            self._input_checks = deepcopy(checks)
            self._show_support(draft, checks, details)
            self.message.setText('입력을 확인해 주세요. 오류가 있는 초안도 저장할 수 있습니다.' if checks else
                                 '입력 검사를 통과했습니다. 계산 환경은 실행할 때 확인합니다.')
            item = self.tree.currentItem()
            self._draw_domain((item.data(0, ROLE) or {}).get('path') if item else None)

        return self._call(checked, accepted)

    def _show_support(self, draft=None, checks=None, details=None):
        if draft is None and self.document:
            draft = self._draft
            details = self.document.get('pde_support', {})
            checks = self.document.get('diagnostics', [])
        else:
            draft = draft if draft is not None else self._draft
            details = details if details is not None else support_details(draft)
            checks = diagnostics(draft) if checks is None else checks
        backend = draft.get('backend')
        backend = backend if isinstance(backend, str) else None
        equations = {
            'pde.fenicsx.nonlinear': '−div((1 + α u²) ∇u) = f; scalar nonlinear weak form',
            'pde.fenicsx.transient': '∂u/∂t − div(k ∇u) + c u = f; backward Euler',
            'pde.fenicsx.vector': '−div(2 μ ε(u) + λ tr(ε(u)) I) + c u = f; two-component Lamé',
            'pde.fenicsx.coupled': '−div(K(region) ∇U) + C U = F; two scalar fields, region matrices',
        }
        self.equation.setText(equations.get(backend, '−div(k ∇u) + c u = f; a(u,v)=∫(k∇u·∇v+cuv), L(v)=∫fv + Neumann terms'))
        self.space.setText(('u[0], u[1]: vector Lagrange P1. ' if backend in ('pde.fenicsx.vector', 'pde.fenicsx.coupled') else
                            'u: scalar Lagrange P1. ') + '좌표 단위와 장 단위: 1 (무차원).')
        self.support.setText('solver 정책은 고정입니다. 임의 solver 옵션과 일반 UFL, ODE는 지원하지 않습니다.')
        policy = {}
        if backend == 'pde.fenicsx.nonlinear':
            from caelab.adapters.fenicsx_nonlinear_worker import NATIVE_OPTIONS
            policy = NATIVE_OPTIONS
        elif backend in BACKENDS:
            from caelab.adapters.fenicsx_rectangle_worker import NATIVE_OPTIONS
            policy = NATIVE_OPTIONS
        text = ['Input diagnostics:', *[entry['message'] for entry in checks],
                'Declared support (not an installed-runtime claim):', *details.get('limitations', []),
                details.get('units', ''), details.get('expression_language', ''),
                'Fixed native solver policy: ' + display(policy)]
        self.messages.setPlainText('\n'.join(text))
        self._input_checks = deepcopy(checks)
        self._refresh_issue_summary()

    def command(self, operation, arguments=None, *, after=None):
        if not self.document or self.conflict:
            return False
        if self.local_dirty and operation != self.document_kind + '.update':
            self.message.setText('편집한 내용을 먼저 변경 적용해 주세요.')
            return False
        document = deepcopy(self.document)
        submitted_buffer = self.edited_draft()
        arguments = deepcopy(arguments or {})
        owner_key = (document['id'], document['session_id'])

        def accepted(receipt):
            if not self.document or (self.document['id'], self.document['session_id']) != owner_key:
                return
            current_buffer = self.edited_draft()
            late_edit = current_buffer != submitted_buffer
            self.local_dirty, self.conflict = late_edit, False
            self._show_document(receipt['document'], preserve_draft=current_buffer if late_edit else None)
            job = receipt.get('job')
            self.message.setText('요청한 내용은 적용했습니다. 그동안 편집한 내용은 아직 적용 전입니다.' if late_edit else
                                 {'update': '변경을 적용했습니다.', 'save': '저장했습니다.',
                                  'undo': '이전 상태로 되돌렸습니다.', 'redo': '변경을 다시 적용했습니다.',
                                  'evaluate': '계산을 요청했습니다.'}.get(operation.rsplit('.', 1)[-1], '작업을 반영했습니다.'))
            if job:
                self._selected_job = job.get('id', job.get('job_id'))
                self._result_key = None
                QTimer.singleShot(0, self.refresh_result)
            if after and not late_edit:
                after()

        return self._call(lambda: self.client.document_command(document['id'], operation, arguments,
                          session_id=document['session_id'], expected_generation=document['generation'],
                          command_id='C' + uuid.uuid4().hex), accepted)

    def apply_inputs(self, *, after=None):
        return self.command(self.document_kind + '.update', {'draft': self.edited_draft()}, after=after)

    def save_document(self, *, after=None):
        if self.local_dirty:
            return self.apply_inputs(after=lambda: self.command('document.save', after=after))
        return self.command('document.save', after=after)

    def evaluate(self):
        return self.command(self.document_kind + '.evaluate')

    def refresh_document(self):
        if not self.document or self._busy:
            return
        identifier = self.document['id']

        def accepted(remote):
            changed = (remote['session_id'], remote['generation']) != (self.document['session_id'], self.document['generation'])
            if changed and self.local_dirty:
                self.conflict = True
                self.message.setText('The owner changed during local editing. Your settings remain here; reload or keep a new copy.')
            elif not self.local_dirty and not self.conflict:
                self._show_document(remote)
            QTimer.singleShot(0, self.refresh_result)

        self._call(lambda: self.client.document_read(identifier), accepted)

    def refresh_result(self):
        if not self._selected_job or not self.document or self._busy:
            return
        identifier, job = self.document['id'], self._selected_job
        key = (identifier, job)
        if self._result_key == key:
            return

        def read():
            # Saved owner results survive a service/job-manager restart; do not
            # require a live job status before trying the retained record.
            try:
                return self.client.document_result(identifier, job)
            except Exception:
                state = self.client.status(job)
                if state.get('state') not in TERMINAL:
                    return {'pending_job': state}
                raise

        def accepted(result):
            if (self.document['id'], self._selected_job) != key:
                return
            if result.get('pending_job'):
                self.result_label.setText('Evaluation ' + result['pending_job'].get('state', 'pending'))
                return
            self._result_key = key
            self._accept_result(result)

        self._call(read, accepted)

    def _accept_result(self, result):
        selected_channel, selected_node = self.channel.currentData(), self.node.currentData()
        self._result = deepcopy(result)
        self.result_selector.blockSignals(True)
        self.result_selector.clear()
        for name, response in result.get('responses', {}).items():
            self.result_selector.addItem(name + ' [' + response.get('unit', '') + ']', ('response', name))
        native_fields = result.get('diagnostics', {}).get('native_fields', [])
        if isinstance(native_fields, dict):
            native_fields = [{'name': name, 'field': field} for name, field in native_fields.items()]
        self._native_fields = native_fields
        for index, entry in enumerate(native_fields):
            field = entry.get('field', entry)
            components = field.get('components', ['u'])
            for component in range(len(components)):
                self.result_selector.addItem(str(entry.get('name', 'Native field ' + str(index + 1))) + ' (' + components[component] + ')',
                                             ('field', index, component))
        self.result_selector.blockSignals(False)
        self.channel.blockSignals(True)
        self.channel.clear()
        for name in result.get('native_channels', {}):
            self.channel.addItem(name, name)
        channel_index = self.channel.findData(selected_channel)
        if channel_index >= 0:
            self.channel.setCurrentIndex(channel_index)
        self.channel.blockSignals(False)
        self._channel_changed()
        if channel_index >= 0:
            node_index = self.node.findData(selected_node)
            if node_index >= 0:
                self.node.setCurrentIndex(node_index)
        self.graph_tabs.setCurrentIndex(1 if self._selected_job and result else 0)
        self._result_selection_changed()
        self._update_actions()

    def _result_selection_changed(self, *_):
        self.field_node.blockSignals(True)
        self.field_node.clear()
        selected = self.result_selector.currentData()
        if selected and selected[0] == 'field':
            entry = self._native_fields[selected[1]]
            field = entry.get('field', entry)
            for node in field.get('node_ids', []):
                self.field_node.addItem(str(node), node)
        self.field_node.blockSignals(False)
        self.field_node.setEnabled(bool(self.field_node.count()))
        self._draw_result()

    def _channel_changed(self, *_):
        self.node.clear()
        if self._result:
            descriptor = self._result.get('native_channels', {}).get(self.channel.currentData(), {})
            if descriptor.get('selectors'):
                for choice in descriptor['selectors']:
                    self.node.addItem(str(choice['label']), choice['selector'])
            else:
                for node in descriptor.get('node_ids', []):
                    self.node.addItem(str(node), node)
        self.node.setEnabled(bool(self.node.count()))
        self._update_actions()

    def _native_curve_selector(self):
        """Use the retained catalog's exact history identity, without guessing nodes."""
        if not isinstance(self._result, dict):
            return None
        name = self.channel.currentData()
        descriptor = self._result.get('native_channels', {}).get(name)
        if not isinstance(name, str) or not isinstance(descriptor, dict):
            return None
        if descriptor.get('selectors'):
            selected = self.node.currentData()
            return selected if any(row.get('selector') == selected for row in descriptor['selectors']) else None
        nodes = descriptor.get('node_ids', [])
        if nodes:
            node = self.node.currentData()
            if node is None or node not in nodes:
                return None
            template = descriptor.get('selector_template', name + '@<node_id>')
            if not isinstance(template, str) or template.count('<node_id>') != 1:
                return None
            return template.replace('<node_id>', str(node))
        selector = descriptor.get('source', {}).get('selector')
        return selector if isinstance(selector, str) and selector else None

    def read_native_curve(self):
        selector = self._native_curve_selector()
        if not self.document or not self._selected_job or selector is None:
            return
        identifier, job = self.document['id'], self._selected_job
        owner_key = (identifier, self.document['session_id'], job, self._result_key,
                     self.channel.currentData(), self.node.currentData(), selector, self.result_selector.currentData())
        result_owner = self._result

        def accepted(result):
            if not self.document or self._result is not result_owner or not isinstance(self._result, dict):
                return
            current_key = (self.document['id'], self.document['session_id'], self._selected_job, self._result_key,
                           self.channel.currentData(), self.node.currentData(), self._native_curve_selector(), self.result_selector.currentData())
            if current_key != owner_key:
                return
            self._result.setdefault('responses', {}).update(result.get('responses', {}))
            self._accept_result(self._result)
            for index in range(self.result_selector.count()):
                if self.result_selector.itemData(index) == ('response', selector):
                    self.result_selector.setCurrentIndex(index)
                    break

        self._call(lambda: self.client.document_result(identifier, job,
                   selection={'responses': [selector], 'rows': [0, 2000]}), accepted)

    def open_curve_comparison(self):
        if not self.document or self._busy:
            return
        selected = self.result_selector.currentData()
        response = selected[1] if selected and selected[0] == 'response' else self._native_curve_selector()
        if not self._selected_job or not response:
            self.message.setText('Select a retained scalar/history and its exact native location before comparing. Fields require a supported native curve selection.')
            return
        from .curve_comparison_window import CurveComparisonWindow
        source = {'document_id': self.document['id'], 'job_id': self._selected_job, 'response': response}
        # The comparison is an independent saved analysis of these exact
        # sources. Changing the current model does not invalidate old curves.
        window = CurveComparisonWindow(self.client, source=source)
        self._comparison_windows.append(window)
        window.show()

    def _draw_result(self, *_):
        self.result_figure.clear()
        self.result_axes = self.result_figure.add_subplot(111)
        axes = self.result_axes
        self.point_label.clear()
        selected = self.result_selector.currentData()
        if not self._result or not selected:
            axes.text(.5, .5, 'No retained result selected.',
                      ha='center', va='center', transform=axes.transAxes)
        elif selected[0] == 'response':
            name = selected[1]
            response = self._result['responses'][name]
            values = response.get('value')
            axis = next((item for item in response.get('axes', []) if isinstance(item.get('values'), list)), None)
            if response.get('kind') == 'series' and isinstance(values, list) and axis:
                axes.plot(axis['values'], values, label=name)
                axes.set_xlabel(axis.get('name', '') + ' [' + axis.get('unit', '') + ']')
                axes.set_ylabel(name + ' [' + response.get('unit', '') + ']')
                axes.legend()
            elif type(values) in (int, float):
                axes.text(.5, .5, name + '\n' + display(values) + ' [' + response.get('unit', '') + ']',
                          ha='center', va='center', transform=axes.transAxes)
            else:
                axes.text(.5, .5, 'This retained response has no supported 1D axis.\nOpen the exact native result in Post.',
                          ha='center', va='center', transform=axes.transAxes)
        else:
            entry = self._native_fields[selected[1]]
            field = entry.get('field', entry)
            coordinates, values = field.get('coordinates'), field.get('values')
            if isinstance(coordinates, list) and isinstance(values, list) and len(coordinates) == len(values) and coordinates:
                component = selected[2]
                scalar = [value[component] if isinstance(value, list) else value for value in values]
                points = axes.scatter([xy[0] for xy in coordinates], [xy[1] for xy in coordinates], c=scalar, s=14)
                self.result_figure.colorbar(points, ax=axes, label='Native nodal value [' + field.get('field_unit', '1') + ']')
                axes.set_aspect('equal')
                axes.set_xlabel('x [' + field.get('coordinates_unit', '1') + ']')
                axes.set_ylabel('y [' + field.get('coordinates_unit', '1') + ']')
                axes.set_title('Exact retained DOFs; no interpolation')
                selected_node = self.field_node.currentData()
                ids = field.get('node_ids', [])
                if selected_node in ids:
                    index = ids.index(selected_node)
                    xy = coordinates[index]
                    axes.scatter([xy[0]], [xy[1]], facecolors='none', edgecolors='#dc2626', s=100, linewidths=2)
                    source = entry.get('source', {})
                    instant = entry.get('time')
                    self.point_label.setText('Node ' + str(selected_node) + ' at ' + display(xy) +
                        ' [' + field.get('coordinates_unit', '1') + ']; value ' + display(scalar[index]) +
                        ' [' + field.get('field_unit', '1') + ']; ' +
                        ('static field' if instant is None else 'model time ' + display(instant) + ' [1]'))
                    self.point_label.setToolTip(display({'source': source, 'study_index': entry.get('study_index'),
                                                       'step_index': entry.get('step_index')}))
        if self._result:
            native = self._result.get('diagnostics', {}).get('native_outcome', {})
            self.messages.setPlainText(self.messages.toPlainText().split('\nRetained result:')[0] + '\nRetained result:\n' +
                display({'job_id': self._selected_job, 'checks': self._result.get('checks', []),
                         'execution_status': self._result.get('execution_status'),
                         'metrics': native.get('metrics', {}), 'pending_validations': native.get('pending_validations', []),
                         'decision': self._result.get('diagnostics', {}).get('decision', 'NOT_RELEASED'),
                         'failure': self._result.get('failure', self._result.get('diagnostics', {}).get('failure')),
                         'failure_reason': self._result.get('diagnostics', {}).get('reason'),
                         'error_type': self._result.get('diagnostics', {}).get('error_type'),
                         'field_delivery_error': self._result.get('diagnostics', {}).get('field_delivery_error')}))
        self.result_canvas.draw_idle()
        self._update_actions()

    def _draw_domain(self, path=None):
        axes = self.domain_axes
        axes.clear()
        draft = self.edited_draft()
        settings = draft.get('settings')
        problem = settings.get('problem', {}) if isinstance(settings, dict) else {}
        domain = problem.get('domain') if isinstance(problem, dict) else None
        side = path[-1] if path and 'boundaries' in path else None
        try:
            if isinstance(domain, dict) and domain.get('type') == 'imported_mesh':
                from caelab.adapters.fenicsx_gmsh import prepare
                mesh = prepare(settings)[0]
                nodes = {row['id']: row['coordinates'] for row in mesh['nodes']}
                for name, group in mesh['boundaries'].items():
                    for edge in group['elements']:
                        xy = [nodes[node] for node in edge['node_ids']]
                        axes.plot([point[0] for point in xy], [point[1] for point in xy],
                                  color='#dd6b20' if name == side else '#334155', linewidth=3 if name == side else 1)
                axes.set_title('Imported mesh boundary groups')
            else:
                lengths = domain.get('lengths') if isinstance(domain, dict) else [1, 1] if domain == 'unit_square' else None
                if not isinstance(lengths, list) or len(lengths) != 2 or any(type(v) not in (int, float) or not math.isfinite(v) or v <= 0 for v in lengths):
                    raise ValueError('Invalid or unsupported mathematical domain')
                lx, ly = lengths
                sides = {'xmin': ([0, 0], [0, ly]), 'xmax': ([lx, lx], [0, ly]),
                         'ymin': ([0, lx], [0, 0]), 'ymax': ([0, lx], [ly, ly])}
                for name, (x, y) in sides.items():
                    axes.plot(x, y, color='#dd6b20' if name == side else '#334155', linewidth=4 if name == side else 1.5)
                    axes.text(sum(x)/2, sum(y)/2, name, fontsize=9)
                if isinstance(domain, dict) and isinstance(domain.get('interface'), dict):
                    axis, fraction = domain['interface'].get('axis'), domain['interface'].get('fraction')
                    if axis == 0 and type(fraction) in (int, float):
                        axes.plot([lx*fraction]*2, [0, ly], '--', color='#2563eb')
                axes.set_xlim(-lx*.1, lx*1.1)
                axes.set_ylim(-ly*.1, ly*1.1)
                axes.set_title('Declared domain')
            axes.set_aspect('equal')
            axes.set_xlabel('x [1]')
            axes.set_ylabel('y [1]')
        except (ValueError, TypeError, KeyError, IndexError, OverflowError) as error:
            axes.text(.5, .5, str(error), ha='center', va='center', transform=axes.transAxes, wrap=True)
        self.domain_canvas.draw_idle()

    def _update_actions(self):
        available = bool(self.document) and not self._busy and not self.conflict
        self.new_action.setEnabled(not self._busy)
        self.open_action.setEnabled(not self._busy)
        self.save_action.setEnabled(available)
        self.undo_action.setEnabled(available and not self.local_dirty and bool(self.document.get('can_undo')))
        self.redo_action.setEnabled(available and not self.local_dirty and bool(self.document.get('can_redo')))
        self.apply_button.setEnabled(available and self.local_dirty)
        self.validate_button.setEnabled(bool(self.document) and not self._busy)
        self.evaluate_button.setEnabled(available and not self.local_dirty and not self.document.get('diagnostics'))
        can_plan = available and not self.local_dirty and not self.document.get('diagnostics')
        self.plan_button.setEnabled(can_plan)
        self.plan_action.setEnabled(can_plan)
        self.runner_button.setEnabled(bool(self._selected_job) and bool(self.runner_open) and not self._busy)
        self.post_button.setEnabled(bool(self._selected_job) and bool(self._result) and bool(self._result.get('post_input') or self._result.get('post_inputs')) and
                                    bool(self.result_open) and not self._busy)
        self.reload_button.setVisible(self.conflict)
        self.copy_button.setVisible(self.conflict)
        self.read_curve_button.setEnabled(bool(self.document) and bool(self._selected_job) and
                                         self._native_curve_selector() is not None and not self._busy)
        can_compare = bool(self.document) and bool(self._selected_job) and not self._busy
        self.compare_button.setEnabled(can_compare)
        self.compare_action.setEnabled(can_compare)
        showing_result = self.graph_tabs.currentWidget() is self.result_canvas
        self.result_selector.setVisible(showing_result and self.result_selector.count() > 0)
        self.point_controls.setVisible(showing_result and self.field_node.count() > 0)
        self.point_label.setVisible(showing_result and bool(self.point_label.text()))
        self.history_controls.setVisible(showing_result and self.channel.count() > 0)
        self.compare_button.setVisible(showing_result and bool(self._result))
        self.result_label.setVisible(showing_result)
        self.runner_button.setToolTip('보존 계산을 선택하면 실행 상태를 열 수 있습니다.')
        self.post_button.setToolTip('선택한 계산에 등록된 native 결과 파일을 엽니다.')
        self.save_state.setText('변경 적용 전' if self.local_dirty else '저장됨'
                               if self.document and not self.document.get('dirty') else '저장 전')
        self._refresh_issue_summary()
        self._refresh_result_caption()

    def open_numerical_plan(self):
        if not self.document or self._busy or self.conflict:
            return False
        if self.local_dirty:
            self.message.setText('수치 계산 계획을 만들기 전에 편집한 내용을 변경 적용해 주세요.')
            return False
        if self.document.get('diagnostics'):
            self.message.setText('입력 오류를 고친 뒤 변경 적용해 주세요. 현재 초안은 저장할 수 있습니다.')
            return False
        document = deepcopy(self.document)
        key = (document['id'], document['session_id'], document['generation'])
        command_id = self._plan_commands.setdefault(key, 'C' + uuid.uuid4().hex)

        def opened():
            options = {'session_id': document['session_id'], 'expected_generation': document['generation'],
                       'command_id': command_id}
            if self.plan_open:
                return self.plan_open(document['id'], **options)
            from .desktop import open_pde_plan
            return open_pde_plan(self.client, document['id'], **options)

        def accepted(receipt):
            if not isinstance(receipt, dict) or receipt.get('executed') is not False:
                self.message.setText('The Plan opener returned an unconfirmed creation response; inspect it before retrying.')
                return
            target = receipt.get('document_id') or receipt.get('document', {}).get('id', 'Numerical request')
            self.message.setText('현재 모델로 수치 계산 계획을 열었습니다. 계산은 아직 시작하지 않았습니다.')
            self.messages.appendPlainText('Numerical: ' + target + '\nSource generation: ' + str(document['generation']))

        return self._call(opened, accepted)

    def open_runner(self):
        if self.runner_open and self._selected_job:
            self.runner_open(self._selected_job)

    def open_post(self):
        if self.result_open and self._selected_job:
            selected = self.result_selector.currentData()
            study_index = None
            if selected and selected[0] == 'field':
                study_index = self._native_fields[selected[1]].get('study_index')
            self.result_open(self.document['id'], self._selected_job, study_index=study_index)

    def new_document(self):
        backend, accepted = QInputDialog.getItem(self, 'New PDE model', 'Declared adapter', list(self.model_backends), 0, False)
        if accepted:
            self._abandon(lambda: self.open_document(draft=self.model_default(backend)))

    def choose_document(self):
        def accepted(documents):
            if isinstance(documents, dict):
                documents = documents.get('documents', [])
            choices = {item['title'] + ' · ' + item['id']: item['id'] for item in documents if item.get('kind') == self.document_kind}
            choice, ok = QInputDialog.getItem(self, 'Open PDE document', 'Saved or working document', list(choices), 0, False)
            if ok and choice:
                self._abandon(lambda: self.open_document(document_id=choices[choice]))
        self._call(self.client.documents, accepted)

    def reload_remote(self):
        if QMessageBox.question(self, 'Reload owner version', 'Discard unapplied local settings and reload the owner version?',
                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel) == QMessageBox.StandardButton.Yes:
            self._call(lambda: self.client.document_read(self.document['id']), self._opened)

    def copy_edits(self):
        self.open_document(title=self.document['title'] + ' — local edits', draft=self.edited_draft())

    def _abandon(self, after):
        if not self.local_dirty and not (self.document and self.document.get('dirty')):
            after()
            return True
        answer = QMessageBox.question(self, 'PDE draft', 'Save the current model before closing this document?',
                                      QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel)
        if answer == QMessageBox.StandardButton.Save:
            self.save_document(after=after)
            return False
        if answer == QMessageBox.StandardButton.Discard:
            after()
            return True
        return False

    def closeEvent(self, event):
        if self._allow_close:
            event.accept()
        elif self._busy:
            self.message.setText('Wait for the owner command to finish before closing.')
            event.ignore()
        elif self.local_dirty or self.document and self.document.get('dirty'):
            answer = QMessageBox.question(self, 'Close PDE document', 'Save the current model before closing?',
                                          QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel)
            if answer == QMessageBox.StandardButton.Save:
                event.ignore()
                def saved():
                    self._allow_close = True
                    self.close()
                self.save_document(after=saved)
            elif answer == QMessageBox.StandardButton.Discard:
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--service', default=os.environ.get('CAELAB_SERVICE_URL'))
    parser.add_argument('--document-id')
    options = parser.parse_args(argv)
    if not options.service:
        parser.error('--service or CAELAB_SERVICE_URL must identify an existing local service')
    from .desktop import launch_tool, open_document_result
    client = Client(options.service)
    app = QApplication.instance() or QApplication(sys.argv[:1])
    window = PDEWindow(client, document_id=options.document_id,
        runner_open=lambda job: launch_tool(client, 'runner', job_id=job),
        result_open=lambda document_id, job_id, study_index=None: open_document_result(
            client, document_id, job_id, study_index=study_index))
    window.show()
    return app.exec()


if __name__ == '__main__':
    raise SystemExit(main())
