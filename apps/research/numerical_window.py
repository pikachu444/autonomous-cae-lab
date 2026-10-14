"""Independent Numerical Plan editor, using the shared document/run service."""
from __future__ import annotations
import argparse
from copy import deepcopy
import json
import math
import os
import sys
import uuid
from time import monotonic

from PySide6.QtCore import QThreadPool, QTimer, Qt
from shiboken6 import isValid
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (QApplication, QAbstractItemView, QComboBox, QDialog,
    QDialogButtonBox, QFormLayout, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QMainWindow,
    QMessageBox, QPushButton, QPlainTextEdit, QSizePolicy, QSplitter, QStyledItemDelegate, QTableWidget,
    QTableWidgetItem, QTabWidget, QToolBar, QVBoxLayout, QWidget)
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure

from caelab.numerical_document import from_material_document, default_draft
from caelab.workbench_client import Client
from caelab.material_document import diagnostics as material_diagnostics
from .data_window import _Read, display, TERMINAL
from .runner_window import candidate_state, actual_candidate


def number_or_raw(text):
    try:
        value = json.loads(text)
        return value if not isinstance(value, (dict, list)) and not (type(value) is float and not math.isfinite(value)) else text
    except ValueError:
        return text


def cell_value(table, row, column):
    item = table.item(row, column)
    if item is None:
        return ''
    original = item.data(Qt.ItemDataRole.UserRole)
    if item.text() == display(original):
        return deepcopy(original)
    return number_or_raw(item.text())


class _CoefficientDisplay(QStyledItemDelegate):
    """Compact painted values; the model and editor retain the exact input text."""
    def displayText(self, value, locale):
        parsed = number_or_raw(str(value))
        if type(parsed) in (int, float) and math.isfinite(parsed):
            return format(parsed, '.6g')
        return str(value)


class ProtocolDialog(QDialog):
    """Edit measured kinematics without inferring a lateral F or strain/time map."""
    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = deepcopy(settings)
        self.setWindowTitle('Explicit experiment protocol')
        self.resize(1080, 480)
        layout = QVBoxLayout(self)
        label = QLabel('Confirm the complete prescribed deformation gradient at each time. Values initially copy the selected Material protocol. No strain-to-time, lateral stretch or frame conversion is inferred.')
        label.setWordWrap(True)
        layout.addWidget(label)
        self.table = QTableWidget(len(settings.get('time', [])), 10)
        self.table.setHorizontalHeaderLabels(['time [' + settings.get('time_unit', '?') + ']'] + [f'F{i+1}{j+1}' for i in range(3) for j in range(3)])
        for row, time in enumerate(settings.get('time', [])):
            values = [time] + [settings['deformation_gradient'][row][i][j] for i in range(3) for j in range(3)]
            for col, value in enumerate(values):
                item = QTableWidgetItem(display(value))
                item.setData(Qt.ItemDataRole.UserRole, value)
                self.table.setItem(row, col, item)
        layout.addWidget(self.table)
        controls = QHBoxLayout()
        add, remove = QPushButton('Add state'), QPushButton('Remove selected states')
        def add_row():
            self.table.insertRow(self.table.rowCount())  # Empty is invalid, never fabricated identity F.
        def remove_rows():
            for row in sorted({item.row() for item in self.table.selectedIndexes()}, reverse=True):
                self.table.removeRow(row)
        add.clicked.connect(add_row)
        remove.clicked.connect(remove_rows)
        controls.addWidget(add)
        controls.addWidget(remove)
        layout.addLayout(controls)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def draft_settings(self):
        focus = QApplication.focusWidget()
        if focus:
            focus.clearFocus()
        settings = deepcopy(self.settings)
        settings['time'] = [cell_value(self.table, row, 0) for row in range(self.table.rowCount())]
        settings['deformation_gradient'] = [[[cell_value(self.table, row, 1+i*3+j) for j in range(3)] for i in range(3)] for row in range(self.table.rowCount())]
        return settings


class _OperationOptions(QWidget):
    """Reuse the Request Plan's typed tree, without duplicating its JSON parser."""
    def __init__(self, owner):
        super().__init__(owner)
        from .request_plan_window import RequestPlanWindow, _InputDelegate
        from PySide6.QtWidgets import QTreeWidget
        self.owner, self.message = owner, owner.message
        self._populating = False
        self._request_editor = RequestPlanWindow
        layout = QVBoxLayout(self)
        self.note = QLabel('Edit the selected operation definitions and numerical options. Each leaf keeps its type; incomplete values remain visible and block Run.')
        self.note.setWordWrap(True)
        layout.addWidget(self.note)
        self.inputs = QTreeWidget()
        self.inputs.setObjectName('materialOperationOptions')
        self.inputs.setHeaderLabels(['Operation field / index', 'Declared value', 'Type'])
        self.inputs.setColumnWidth(0, 230)
        self.inputs.setColumnWidth(1, 280)
        self.inputs.setItemDelegate(_InputDelegate(self.inputs))
        self.inputs.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked | QAbstractItemView.EditTrigger.EditKeyPressed)
        self.inputs.itemChanged.connect(self._input_edited)
        layout.addWidget(self.inputs)
        actions = QHBoxLayout()
        self.response_button = QPushButton('Add / select physical response…')
        self.constraint_button = QPushButton('Add response constraint…')
        self.distribution_button = QPushButton('Add coefficient distribution…')
        self.threshold_button = QPushButton('Add epsilon threshold…')
        for button, callback in ((self.response_button, owner.choose_operation_response),
                                 (self.constraint_button, owner.choose_operation_constraint),
                                 (self.distribution_button, owner.choose_distribution),
                                 (self.threshold_button, owner.choose_epsilon_threshold)):
            button.clicked.connect(callback)
            actions.addWidget(button)
        layout.addLayout(actions)
        structural = QHBoxLayout()
        for title, callback in (('Add typed member / list entry…', self.add_input),
                                ('Remove selected member', self.remove_input),
                                ('Change selected value type…', self.change_type)):
            button = QPushButton(title)
            button.clicked.connect(callback)
            structural.addWidget(button)
        layout.addLayout(structural)

    def _populate_inputs(self, value):
        self._request_editor._populate_inputs(self, value)
        self.inputs.topLevelItem(0).setText(0, 'operation_options')

    def _input_value(self, item):
        return self._request_editor._input_value(self, item)

    def value(self):
        item = self.inputs.topLevelItem(0)
        return self._input_value(item) if item is not None else {}

    def _input_edited(self, *_):
        if not self._populating:
            self.owner._edited()

    def _edited(self):
        self.owner._edited()

    def _edit_structure(self, callback):
        if self.owner._busy or self.owner.conflict or self.owner._view_error:
            return
        self.owner._commit_editor()
        value = self.value()
        callback(value)
        self._populate_inputs(value)
        self.owner._edited()

    @staticmethod
    def _at_path(value, path):
        for part in path:
            value = value[part]
        return value

    def add_input(self):
        self._request_editor.add_input(self)

    def remove_input(self):
        self._request_editor.remove_input(self)

    def change_type(self):
        self._request_editor.change_type(self)



class NumericalWindow(QMainWindow):
    def __init__(self, client, *, document_id=None, material_document=None, poll_interval=2000, auto_open=True):
        super().__init__()
        self.client, self.document = client, None
        self.local_dirty = self.conflict = self._busy = self._populating = False
        self._busy_background = False
        self._callbacks = 0
        self._pending_adoption = None
        self._adoption_receipt = None
        self._drawn_result_job = None
        self._allow_close = self._closed = False
        self._worker = None
        self._result_cache, self._result_errors, self._statuses = {}, {}, {}
        self._result_after = {}
        self._view_error = None
        self._analysis_job = None
        self._material = None
        self._experiments = []
        self._trial_sources, self._trial_source_errors = {}, {}
        self._trial_source_queue = {}
        self._operation_options_by_mode = {}
        self._shown_operation_mode = 'fit'
        self._build_ui()
        self.timer = QTimer(self)
        self.timer.setInterval(poll_interval)
        self.timer.timeout.connect(self.refresh_document)
        if poll_interval > 0:
            self.timer.start()
        if auto_open:
            self.open_document(document_id=document_id, draft=from_material_document(material_document) if material_document and not document_id else None)

    def _build_ui(self):
        from .appearance import configure_plot_fonts
        configure_plot_fonts()
        self.resize(1440, 900)
        self.setMinimumSize(960, 700)
        toolbar=QToolBar('재료 피팅'); toolbar.setMovable(False); self.addToolBar(toolbar)
        files=self.menuBar().addMenu('파일(&F)')
        edits=self.menuBar().addMenu('편집(&E)')
        view=self.menuBar().addMenu('보기(&V)')
        identification = view.addAction('계수 식별과 다음 시험…')
        identification.triggered.connect(self.open_identification)
        self.new_action=QAction('새 피팅 계획',self,shortcut=QKeySequence.New)
        self.open_action=QAction('열기…',self,shortcut=QKeySequence.Open)
        self.save_action=QAction('저장',self,shortcut=QKeySequence.Save)
        self.undo_action=QAction('실행 취소',self,shortcut=QKeySequence.Undo)
        self.redo_action=QAction('다시 실행',self,shortcut=QKeySequence.Redo)
        self.request_action=QAction('일반 수치 계획…',self)
        for action,handler in ((self.new_action,self.new_document),(self.open_action,self.choose_document),
            (self.save_action,self.save_document),(self.undo_action,lambda:self.command('document.undo')),
            (self.redo_action,lambda:self.command('document.redo')),(self.request_action,lambda:self.open_request_document())):
            action.triggered.connect(handler)
        files.addActions([self.new_action,self.open_action,self.save_action,self.request_action])
        material_action=QAction('재료 열기 / 저장…',self)
        material_action.triggered.connect(self.open_material); files.addAction(material_action)
        edits.addActions([self.undo_action,self.redo_action])
        check=QAction('입력 확인',self); check.triggered.connect(self.locate_input_error); edits.addAction(check)
        toolbar.addActions([self.open_action,self.save_action,self.undo_action,self.redo_action])
        self.apply_button=QPushButton('계획 적용'); self.apply_button.clicked.connect(self.apply_inputs)
        self.run_button=QPushButton('피팅 실행'); self.run_button.setProperty('appearanceRole','primary')
        self.run_button.clicked.connect(self.run_plan)
        self.stop_button=QPushButton('실행 취소'); self.stop_button.clicked.connect(self.cancel_run)
        for widget in (self.apply_button,self.run_button,self.stop_button): toolbar.addWidget(widget)
        self.identity=QLabel(); toolbar.addWidget(self.identity)
        root=QWidget(); layout=QVBoxLayout(root)
        self.message=QLabel('재료와 시험을 선택하세요.'); self.message.setWordWrap(True); layout.addWidget(self.message)
        conflict=QHBoxLayout()
        self.reload_button=QPushButton('서버 입력 다시 읽기')
        self.copy_button=QPushButton('편집을 새 계획으로 보관')
        self.reload_button.clicked.connect(self.reload_remote)
        self.copy_button.clicked.connect(lambda:self.open_document(draft=self.edited_draft(),title=self.document['title']+' 편집'))
        conflict.addWidget(self.reload_button); conflict.addWidget(self.copy_button); layout.addLayout(conflict)
        self.inputs_panel_button=QPushButton('입력 접기'); self.inputs_panel_button.hide()
        self.results_panel_button=QPushButton('결과 접기'); self.results_panel_button.hide()
        self.inputs_panel_button.clicked.connect(lambda:self._toggle_panel('inputs'))
        self.results_panel_button.clicked.connect(lambda:self._toggle_panel('results'))
        for label,name in [('입력 표시/접기','inputs'),('결과 표시/접기','results')]:
            action=QAction(label,self); action.triggered.connect(lambda checked=False,name=name:self._toggle_panel(name)); view.addAction(action)
        self.study_splitter=QSplitter(Qt.Orientation.Horizontal); layout.addWidget(self.study_splitter,1)
        self.editor=QWidget(); edit=QVBoxLayout(self.editor); edit.setContentsMargins(0,0,0,0)
        model=QHBoxLayout()
        self.material_button=QPushButton('재료 선택…'); self.material_button.clicked.connect(self.choose_material)
        self.material_label=QLabel('재료 선택'); self.material_label.setWordWrap(True)
        model.addWidget(self.material_button); model.addWidget(self.material_label,1); edit.addLayout(model)
        self.mode=QComboBox(); self.mode.addItems(['fit','doe','optimize','uq','epsilon'])
        self.method=QComboBox(); self.method.addItems(['least_squares','differential_evolution'])
        self.budget,self.count,self.seed,self.penalty=[QLineEdit() for _ in range(4)]
        settings=QWidget(); form=QFormLayout(settings); form.setContentsMargins(0,0,0,0)
        for label,widget in [('연구 방법',self.mode),('피팅 알고리즘',self.method),('최대 모델 호출',self.budget),
                             ('표본 수',self.count),('난수 seed',self.seed),('실패 벌점 (null = 중지)',self.penalty)]:
            form.addRow(label,widget)
            if isinstance(widget,QLineEdit): widget.textEdited.connect(self._edited)
            else: widget.currentTextChanged.connect(self._edited)
        self.mode.currentTextChanged.connect(self._mode_changed)
        self.settings_toggle=QPushButton('방법 설정'); self.settings_toggle.setCheckable(True)
        self.settings_toggle.toggled.connect(settings.setVisible); settings.hide()
        edit.addWidget(self.settings_toggle); edit.addWidget(settings)
        self.input_splitter=QSplitter(Qt.Orientation.Vertical); edit.addWidget(self.input_splitter,1)
        self.variables=QTableWidget(0,7); self.variables.setObjectName('numericalVariables')
        self.variables.setHorizontalHeaderLabels(['계수','단위','시작값','하한','상한','조정','좌표'])
        self.variables.itemChanged.connect(self._edited)
        self.variables.horizontalHeader().setDefaultSectionSize(65)
        self._coefficient_display = _CoefficientDisplay(self.variables)
        for column in (2, 3, 4):
            self.variables.setItemDelegateForColumn(column, self._coefficient_display)
        self.variables.setToolTip('현재 재료와 별개인 계획 시작값과 탐색 범위입니다.')
        self.input_splitter.addWidget(self.variables)
        self.experiments_panel=QWidget(); el=QVBoxLayout(self.experiments_panel); el.setContentsMargins(0,0,0,0)
        buttons=QHBoxLayout()
        self.add_experiment=QPushButton('시험 추가…'); self.add_experiment.clicked.connect(self.choose_observation)
        self.edit_protocol=QPushButton('조건…'); self.edit_protocol.clicked.connect(self.change_protocol)
        self.remove_experiment=QPushButton('제거'); self.remove_experiment.clicked.connect(self.remove_experiments)
        for button in (self.add_experiment,self.edit_protocol,self.remove_experiment): buttons.addWidget(button)
        el.addLayout(buttons)
        self.experiments=QTableWidget(0,8); self.experiments.setObjectName('numericalExperiments')
        self.experiments.setHorizontalHeaderLabels(['식별자','용도','시험','관측','모델 응답','가중치','오차 기준','조건'])
        self.experiments.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.experiments.itemChanged.connect(self._edited)
        self.experiments.setColumnHidden(0,True); self.experiments.setColumnHidden(4,True)
        self.experiments.setColumnHidden(7,True); self.experiments.horizontalHeader().setDefaultSectionSize(78)
        self.experiments.horizontalHeader().moveSection(2,0)
        for column,width in ((1,55),(2,120),(3,85),(5,60),(6,75)):
            self.experiments.setColumnWidth(column,width)
        el.addWidget(self.experiments,1)
        self.input_splitter.addWidget(self.experiments_panel)
        self.operation_options=_OperationOptions(self); self.input_splitter.addWidget(self.operation_options)
        self.input_splitter.setSizes([180,300,0])
        self.editor.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Preferred)
        self.editor.setMinimumWidth(320)
        self.editor.setMaximumWidth(480)
        self.study_splitter.addWidget(self.editor)
        self.results_panel=QWidget(); self.results_panel.setMinimumWidth(500); rl=QVBoxLayout(self.results_panel); rl.setContentsMargins(0,0,0,0)
        self.result_splitter=QSplitter(Qt.Orientation.Vertical); rl.addWidget(self.result_splitter,1)
        run_panel=QWidget(); run_layout=QVBoxLayout(run_panel); run_layout.setContentsMargins(0,0,0,0)
        self.runs=QTableWidget(0,4)
        self.runs.setHorizontalHeaderLabels(['실행','상태','입력','계획'])
        self.runs.setColumnHidden(2,True)
        self.runs.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.runs.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.runs.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.runs.itemSelectionChanged.connect(self._selection_changed)
        run_layout.addWidget(self.runs,1)
        actions=QHBoxLayout()
        self.read_button=QPushButton('결과 다시 읽기'); self.read_button.clicked.connect(self.retry_result)
        self.adopt_button=QPushButton('계수를 재료에 적용…'); self.adopt_button.clicked.connect(self.adopt_candidate)
        self.analysis_button=QPushButton('응답 분석…'); self.analysis_button.clicked.connect(self.analyze_result)
        for button in (self.read_button,self.adopt_button,self.analysis_button): actions.addWidget(button)
        run_layout.addLayout(actions); self._build_adoption_receipt_ui(run_layout)
        self.result_splitter.addWidget(run_panel)
        self.tabs=QTabWidget()
        self.candidates=QTableWidget(0,5)
        self.candidates.setHorizontalHeaderLabels(['후보','상태','계수','목적함수','실패 이유'])
        self.candidates.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.candidates.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.candidates.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.figure=Figure(constrained_layout=True); self.canvas=FigureCanvasQTAgg(self.figure)
        self.canvas.setMinimumSize(430,250)
        self.curve_selector=QComboBox(); self.curve_selector.currentIndexChanged.connect(self._curve_changed)
        self.curve_summary=QLabel(); self.curve_summary.setWordWrap(True)
        self.plot_axis=QComboBox(); self.plot_axis.addItem('시간','time')
        self.plot_axis.addItem('측정 변형','measured'); self.plot_axis.currentIndexChanged.connect(self._curve_changed)
        curve_controls=QWidget(); controls=QHBoxLayout(curve_controls); controls.setContentsMargins(0,0,0,0)
        self.curve_selector.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.curve_selector.setMinimumContentsLength(12)
        self.curve_selector.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Fixed)
        controls.addWidget(self.curve_selector,1); controls.addWidget(self.plot_axis)
        rl.insertWidget(0,curve_controls); rl.addWidget(self.curve_summary)
        self.tabs.addTab(self.canvas,'관측과 최종 예측'); self.tabs.addTab(self.candidates,'평가한 후보')
        self.details=QPlainTextEdit(); self.details.setReadOnly(True); self.tabs.addTab(self.details,'진단 상세')
        self.result_splitter.addWidget(self.tabs)
        self.result_splitter.setStretchFactor(0,0); self.result_splitter.setStretchFactor(1,1)
        self.result_splitter.setSizes([160,580])
        self.study_splitter.addWidget(self.results_panel)
        self.study_splitter.setStretchFactor(0,0); self.study_splitter.setStretchFactor(1,1)
        self.study_splitter.setSizes([430,940])
        self.setCentralWidget(root); self._update_actions()

    def _toggle_panel(self, name):
        panel = self.editor if name == 'inputs' else self.results_panel
        other = self.results_panel if name == 'inputs' else self.editor
        # Keep a panel available even if the user has collapsed its counterpart.
        visible = not panel.isHidden()
        if visible and other.isHidden():
            other.show()
        panel.setVisible(not visible)
        self.inputs_panel_button.setText('Show inputs' if self.editor.isHidden() else 'Hide inputs')
        self.results_panel_button.setText('Show results' if self.results_panel.isHidden() else 'Hide results')
        if not visible and 0 in self.study_splitter.sizes():
            self.study_splitter.setSizes([1, 2])

    def _call(self, function, accepted, *, background=False, relevant=None, rejected=None):
        # A confirmation dialog runs a nested Qt event loop. Its timer must not
        # start a background read between a foreground callback and its next
        # request (for example Material read -> confirm -> adopt).
        if self._closed or not isValid(self) or self._busy or background and self._callbacks:
            return False
        self._busy = True
        self._busy_background = background
        self._update_actions()
        self._worker = worker = _Read(function)
        def finished(value, error):
            if self._closed or not isValid(self) or self._worker is not worker:
                return
            self._busy, self._worker = False, None
            self._busy_background = False
            self._callbacks += 1
            try:
                if relevant is None or relevant():
                    if error:
                        if rejected is not None:
                            rejected(error)
                        else:
                            self.message.setText('Request failed; edited inputs retained. ' + error)
                    else:
                        accepted(value)
                # One explicit adoption click may wait for a read already in
                # flight. Dispatch it before another timer can claim _busy.
                pending, self._pending_adoption = self._pending_adoption, None
                if pending and not self._closed:
                    pending()
            finally:
                self._callbacks -= 1
                if not self._closed and isValid(self):
                    self._update_actions()
                    if getattr(self,'_trial_source_queue',None):
                        QTimer.singleShot(0,self._drain_trial_sources)
        worker.signals.finished.connect(finished, Qt.ConnectionType.QueuedConnection)
        QThreadPool.globalInstance().start(worker)
        return True

    def _build_adoption_receipt_ui(self, layout):
        self.adoption_receipt_label = QLabel()
        self.adoption_receipt_label.setObjectName('unconfirmedAdoptionReceipt')
        self.adoption_receipt_label.setWordWrap(True)
        self.adoption_receipt_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.retry_adoption_button = QPushButton('적용 결과 다시 확인')
        self.retry_adoption_button.setObjectName('retryAdoptionReceipt')
        self.retry_adoption_button.clicked.connect(self.retry_adoption_receipt)
        layout.addWidget(self.adoption_receipt_label)
        layout.addWidget(self.retry_adoption_button)

    def _update_adoption_receipt_actions(self):
        pending = self._adoption_receipt
        self.adoption_receipt_label.setVisible(pending is not None)
        self.retry_adoption_button.setVisible(pending is not None)
        if pending is None:
            return
        request = pending['request']
        target = request['target_document_id' if pending['kind'] == 'domain' else pending['kind'] + '_document_id']
        same_session = self.document is not None and self.document['session_id'] == pending['source_session']
        note = ('연결이 바뀌어 다시 확인할 수 없습니다. 원문서에서 적용 여부를 확인하세요.'
                if not same_session else '다른 후보를 적용하기 전에 아래 버튼으로 앞선 적용 결과를 확인하세요.')
        self.adoption_receipt_label.setText('후보가 원문서에 적용됐는지 아직 확인하지 못했습니다.\n' + note)
        self.adoption_receipt_label.setToolTip('진단 정보\n원문서: ' + target + '\n계산: ' + request['job_id'] +
            '\n후보: ' + request['candidate_id'] + '\n요청: ' + request['command_id'])
        self.retry_adoption_button.setEnabled(same_session and not self._callbacks and not self._pending_adoption
                                             and (not self._busy or self._busy_background))

    def _submit_adoption_receipt(self, kind, request, acknowledged=None):
        if self._adoption_receipt is not None:
            self.message.setText('앞선 적용 결과를 먼저 확인하세요. 아래의 적용 결과 다시 확인 버튼을 사용하세요.')
            return False
        self._adoption_receipt = {'kind': kind, 'request': deepcopy(request),
            'source_session': self.document['session_id'], 'acknowledged': acknowledged}
        return self._send_adoption_receipt(self._adoption_receipt)

    def _send_adoption_receipt(self, pending):
        if self._adoption_receipt is not pending:
            return False
        if self.document is None or self.document['session_id'] != pending['source_session']:
            self.message.setText('연결이 바뀌어 적용 여부를 확인하지 못했습니다. 원문서의 현재 값을 확인하세요.')
            self._update_adoption_receipt_actions()
            return False
        request = deepcopy(pending['request'])
        kind = pending['kind']
        target = request['target_document_id' if kind == 'domain' else kind + '_document_id']
        def failed(error):
            self.message.setText('적용 결과를 아직 확인하지 못했습니다. 적용 결과 다시 확인 버튼을 누르세요.')
            self.message.setToolTip(str(error))
        def accepted(receipt):
            if (not isinstance(receipt, dict) or receipt.get('command_id') != request['command_id']
                    or not isinstance(receipt.get('document'), dict) or receipt['document'].get('id') != target):
                failed('Response did not acknowledge this exact target and command ID.')
                return
            self._adoption_receipt = None
            if kind == 'pde':
                self._pde_adoption_request = None
            self.message.setText('선택한 후보를 원문서에 적용했습니다. 원문서에서 값을 확인하고 저장하세요.')
            self.message.setToolTip('')
            callback = pending['acknowledged']
            if callback is not None:
                callback(receipt)
        method = (self.client.domain_candidate_adopt if kind == 'domain' else
                  self.client.pde_adopt if kind == 'pde' else self.client.numerical_adopt)
        return self._call(lambda: method(**request), accepted, rejected=failed,
                          relevant=lambda: self._adoption_receipt is pending)

    def retry_adoption_receipt(self):
        pending = self._adoption_receipt
        if pending is None or self._callbacks or self._pending_adoption or self._busy and not self._busy_background:
            return False
        def begin():
            self._send_adoption_receipt(pending)
        if self._busy_background:
            self._pending_adoption = begin
            self.message.setText('현재 자료 읽기가 끝나면 앞선 적용 결과를 확인합니다.')
            self._update_actions()
            return True
        return self._send_adoption_receipt(pending)

    def open_document(self, *, document_id=None, title='Numerical study', draft=None):
        return self._call(lambda: self.client.document_open(kind='numerical', title=title, draft=draft, document_id=document_id), self._opened)

    def _opened(self, document):
        if document.get('draft', {}).get('mode') == 'request' and type(self) is NumericalWindow:
            self.open_request_document(document['id'])
            return
        self.local_dirty = self.conflict = False
        self._result_cache.clear()
        self._show_document(document)
        self.message.setText('시험 조건과 조정할 계수를 확인하세요. 적용 후 피팅을 실행할 수 있습니다.')

    def open_request_document(self, document_id=None):
        from .request_plan_window import RequestPlanWindow
        window = RequestPlanWindow(self.client,document_id=document_id)
        self.__dict__.setdefault('_request_windows',[]).append(window)
        window.show()
        return window

    def _show_document(self, document, prefer_job=None):
        self.document = deepcopy(document)
        draft = document['draft']
        self._populating = True
        self._view_error = None
        try:
            modes = {'fit', 'doe', 'optimize', 'uq', 'epsilon'}
            keys = set(default_draft())
            extra = {'operation_options'} if draft.get('mode') in {'optimize', 'uq', 'epsilon'} else set()
            if (not keys <= set(draft) or set(draft) - keys - extra or draft['mode'] not in modes
                    or draft['mode'] == 'fit' and draft['method'] not in ('least_squares', 'differential_evolution')):
                raise ValueError('Unsupported visible plan shape')
            if not isinstance(draft['variables'], list) or any(set(v) != {'id', 'unit', 'value', 'lower', 'upper', 'free', 'transform'} for v in draft['variables']):
                raise ValueError('Unsupported coefficient shape')
            if not isinstance(draft['experiments'], list) or any(set(e) - {'kinematics'} != {'id', 'role', 'source', 'response', 'settings', 'weight', 'scale'} for e in draft['experiments']):
                raise ValueError('Unsupported experiment shape')
            self._material = deepcopy(draft['material'])
            self._experiments = deepcopy(draft['experiments'])
            self._operation_options_by_mode = {}
            if 'operation_options' in draft:
                if not isinstance(draft['operation_options'], dict):
                    raise ValueError('Operation definitions require their visible typed object')
                self._operation_options_by_mode[draft['mode']] = deepcopy(draft['operation_options'])
            self._shown_operation_mode = draft['mode']
            self.mode.setCurrentText(draft['mode'])
            self._show_operation_options(draft['mode'])
            self.method.setCurrentText(draft['method'])
            for key in ('budget', 'count', 'seed'):
                getattr(self, key).setText(display(draft[key]))
            self.penalty.setText(display(draft['failure_penalty']))
            self._populate_variables(draft['variables'])
            self._populate_experiments()
        except (KeyError, TypeError, AttributeError, ValueError):
            self._view_error = 'This raw draft cannot fit the table editor; its complete content is preserved in Details and can be saved/undone.'
        self._populating = False
        settings=self._material.get('draft',{}).get('settings',{}) if isinstance(self._material,dict) else {}
        self.material_label.setText(str(settings.get('model','재료 선택'))+' ['+str(settings.get('stress_unit',''))+']')
        self.material_label.setToolTip(str(self._material.get('document_id','')) if isinstance(self._material,dict) else '')
        self._populate_runs(prefer_job)
        self._draw_result()
        self._update_actions()

    def _set_cell(self, table, row, col, value, editable=True):
        item = QTableWidgetItem(display(value))
        item.setToolTip(display(value))
        item.setData(Qt.ItemDataRole.UserRole, deepcopy(value))
        if not editable:
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        table.setItem(row, col, item)

    def _populate_variables(self, variables):
        self.variables.setRowCount(len(variables))
        for row, variable in enumerate(variables):
            for col, key in enumerate(('id', 'unit', 'value', 'lower', 'upper', 'free', 'transform')):
                self._set_cell(self.variables, row, col, variable[key], editable=col > 1)

    def _populate_experiments(self):
        self.experiments.setRowCount(len(self._experiments))
        for row, experiment in enumerate(self._experiments):
            source = experiment['source']
            values = [experiment['id'], experiment['role'], source['job_id'], source['response'], experiment['response'], experiment['weight'], experiment['scale'], str(len(experiment['settings'].get('time', []))) + ' states']
            for col, value in enumerate(values):
                self._set_cell(self.experiments, row, col, value, editable=col in (1, 4, 5, 6))
        self._refresh_experiment_labels()
        self._queue_trial_sources(self._experiments)


    @staticmethod
    def _trial_source_key(trial):
        source=trial.get('source',{})
        keys=('document_id','job_id','input_revision','input_sha256')
        return tuple(source.get(key) for key in keys)

    def _trial_label(self, trial, observed=None, index=1):
        cached=self._trial_sources.get(self._trial_source_key(trial),{})
        obs=observed or cached.get('result',{}).get('responses',{}).get(trial.get('source',{}).get('response'),{})
        filename=str(obs.get('source_selector',{}).get('file',''))
        title=cached.get('filename') or cached.get('title') or (filename if filename and not filename.startswith('source.') else '') or ('시험 '+str(index))
        component=obs.get('component') or str(trial.get('response','')).removeprefix('stress_')
        return str(title)+' / '+str(component or trial.get('source',{}).get('response',''))

    def _refresh_experiment_labels(self):
        # Only readonly display cells change; never repopulate edited weights,
        # roles or coefficients when a late title/driver read finishes.
        old=self._populating; self._populating=True
        try:
            for row,trial in enumerate(self._experiments):
                if row>=self.experiments.rowCount(): break
                cached=self._trial_sources.get(self._trial_source_key(trial),{})
                obs=cached.get('result',{}).get('responses',{}).get(trial.get('source',{}).get('response'),{})
                title=self._trial_label(trial,obs,row+1)
                item=self.experiments.item(row,2); item.setText(title); item.setToolTip(title)
                component=obs.get('component') or str(trial.get('response','')).removeprefix('stress_')
                unit=obs.get('unit',trial.get('settings',{}).get('stress_unit',''))
                self.experiments.item(row,3).setText(str(component)+' ['+str(unit)+']')
                self.experiments.item(row,3).setToolTip(str(trial.get('source',{}).get('response','')))
        finally:
            self._populating=old

    def _queue_trial_sources(self, trials):
        if self._closed or not isValid(self) or self.client is None or self._allow_close or not self.document: return
        owner=(self.document['id'],self.document['session_id'])
        for trial in trials:
            key=self._trial_source_key(trial)
            if all(key) and key not in self._trial_sources and key not in self._trial_source_errors:
                self._trial_source_queue[key]=owner
        if self._trial_source_queue: QTimer.singleShot(0,self._drain_trial_sources)

    def _drain_trial_sources(self):
        if self._closed or not isValid(self):
            return
        if self._busy or self._callbacks or self._pending_adoption or self._allow_close or not self.document: return
        owner=(self.document['id'],self.document['session_id'])
        active=list(self._experiments)
        run=next((r for r in self.document.get('runs',[]) if r['job_id']==self.selected_job()),{})
        active+=run.get('draft',{}).get('experiments',[])
        keys={self._trial_source_key(trial) for trial in active}
        for key,queued_owner in list(self._trial_source_queue.items()):
            if queued_owner!=owner or key not in keys or key in self._trial_sources or key in self._trial_source_errors:
                self._trial_source_queue.pop(key,None); continue
            self._trial_source_queue.pop(key,None)
            def read(key=key):
                identifier,job,revision,digest=key
                doc=self.client.document_read(identifier)
                source_run=next((r for r in doc.get('runs',[]) if r['job_id']==job),None)
                if (doc.get('kind')!='data' or source_run is None
                        or source_run.get('input_revision')!=revision or source_run.get('input_sha256')!=digest):
                    raise ValueError('선택 시험의 저장된 Data 입력이 다릅니다.')
                result=self.client.document_result(identifier,job)
                if result.get('execution_status')!='SUCCEEDED':
                    raise ValueError('선택 시험의 가져오기가 완료되지 않았습니다.')
                filename=''
                data_id=source_run.get('draft',{}).get('data_id')
                # Registration names, unlike private storage basenames, retain
                # the user's filename. Preview is bounded and never recomputes.
                try:
                    try:
                        preview=self.client.input_preview(data_id)
                    except Exception:
                        if doc.get('draft',{}).get('data_id')!=data_id: raise
                        preview=self.client.document_source_preview(identifier)
                    if preview.get('sha256')==result.get('diagnostics',{}).get('source_sha256') and preview.get('sha256'):
                        filename=str(preview.get('name',''))
                except Exception:
                    pass  # A title failure must not hide an intact retained curve.
                return {'title':doc.get('title',''), 'filename':filename, 'result':result}
            def received(payload,key=key):
                self._trial_sources[key]=payload
                self._refresh_experiment_labels()
                self._draw_result()
            def failed(error,key=key):
                self._trial_source_errors[key]=str(error)
                self._curve_changed()
            self._call(read,received,background=True,rejected=failed,
                relevant=lambda: not self._allow_close and self.document is not None
                and owner==(self.document['id'],self.document['session_id']))
            return

    def _edited(self, *_):
        if _ and isinstance(_[0], QTableWidgetItem) and _[0].tableWidget() is self.variables:
            blocked = self.variables.blockSignals(True)
            _[0].setToolTip(_[0].text())
            self.variables.blockSignals(blocked)
        if not self._populating:
            self.local_dirty = True
            self._update_actions()

    def _commit_editor(self):
        focus = QApplication.focusWidget()
        if focus and self.editor.isAncestorOf(focus):
            focus.clearFocus()

    def edited_draft(self):
        self._commit_editor()
        draft = deepcopy(self.document['draft'])
        if self._view_error:
            return draft
        draft.update(material=deepcopy(self._material), mode=self.mode.currentText(), method=self.method.currentText(), failure_penalty=number_or_raw(self.penalty.text()))
        for key in ('budget', 'count', 'seed'):
            draft[key] = number_or_raw(getattr(self, key).text())
        draft['variables'] = [{key: cell_value(self.variables, row, col) for col, key in enumerate(('id', 'unit', 'value', 'lower', 'upper', 'free', 'transform'))} for row in range(self.variables.rowCount())]
        if draft['mode'] in ('optimize', 'uq', 'epsilon'):
            draft['operation_options'] = self.operation_options.value()
        else:
            draft.pop('operation_options', None)
        draft['experiments'] = deepcopy(self._experiments)
        for row, experiment in enumerate(draft['experiments']):
            for col, key in ((0, 'id'), (1, 'role'), (4, 'response'), (5, 'weight'), (6, 'scale')):
                experiment[key] = cell_value(self.experiments, row, col)
        return draft

    def _option_template(self, mode):
        if mode == 'optimize':
            return {'objective': {}, 'constraints': [],
                    'options': {'population_size': 5, 'max_generations': 1, 'retain_responses': 'summary'}}
        if mode == 'uq':
            return {'distributions': {}, 'independence': '', 'source': {'origin': 'ASSUMED', 'reference': ''}, 'thresholds': []}
        if mode == 'epsilon':
            return {'objectives': [], 'constraints': [], 'primary_index': 0, 'threshold_grid': [],
                    'options': {'population_size': 5, 'max_generations': 1, 'retain_responses': 'summary'}}
        return {}

    def _show_operation_options(self, mode):
        active = mode in ('optimize', 'uq', 'epsilon')
        self.editor.setMaximumWidth(480 if mode=='fit' else 16777215)
        self.editor.setSizePolicy(QSizePolicy.Policy.Ignored if mode=='fit' else QSizePolicy.Policy.Preferred,
                                  QSizePolicy.Policy.Preferred)
        orientation=Qt.Orientation.Horizontal if mode=='fit' else Qt.Orientation.Vertical
        if self.study_splitter.orientation()!=orientation:
            self.study_splitter.setOrientation(orientation)
            self.study_splitter.setSizes([430,940] if mode=='fit' else [340,540])
        self.curve_selector.setVisible(mode=='fit')
        self.plot_axis.setVisible(mode=='fit')
        self.curve_summary.setVisible(mode=='fit')
        self.experiments_panel.setVisible(mode == 'fit')
        self.operation_options.setVisible(active)
        if active and self.input_splitter.sizes()[-1]==0:
            self.input_splitter.setSizes([120,0,240])
        elif mode=='fit' and self.input_splitter.sizes()[1]==0:
            self.input_splitter.setSizes([180,300,0])
        self.method.setEnabled(mode == 'fit')
        self.penalty.setEnabled(mode == 'fit')
        self.count.setEnabled(mode in ('doe', 'uq'))
        for button in (self.add_experiment, self.edit_protocol, self.remove_experiment):
            button.setEnabled(mode == 'fit')
        if active:
            options = self._operation_options_by_mode.setdefault(mode, self._option_template(mode))
            self.operation_options._populate_inputs(options)
            self.operation_options.response_button.setText('Add objective response…' if mode == 'epsilon' else
                                                          'Add probability threshold…' if mode == 'uq' else 'Select objective response…')
            self.operation_options.constraint_button.setVisible(mode in ('optimize', 'epsilon'))
            self.operation_options.distribution_button.setVisible(mode == 'uq')
            self.operation_options.threshold_button.setVisible(mode == 'epsilon')
            self.operation_options.note.setText({
                'optimize': 'Declare the objective and constraints, scalar history reductions and differential evolution options. Population × (generations + 1) must fit the visible total model-call budget.',
                'uq': 'Declare each free coefficient distribution, explicit independence and the source reference. Optional response thresholds use the bound Material units. Failed evaluations remain separate from probability estimates.',
                'epsilon': 'List at least two physical objectives, select primary_index, and declare threshold_grid entries in the order of the remaining objectives. Every child population shares the visible total evaluation budget.'}[mode])

    def _mode_changed(self, mode):
        if self._populating:
            return
        self._commit_editor()
        previous = self._shown_operation_mode
        if previous in ('optimize', 'uq', 'epsilon'):
            self._operation_options_by_mode[previous] = self.operation_options.value()
        self._shown_operation_mode = mode
        self._show_operation_options(mode)
        self._edited()

    def _replace_options(self, options):
        self.operation_options._populate_inputs(options)
        self._operation_options_by_mode[self.mode.currentText()] = deepcopy(options)
        self._edited()

    def _physical_definition(self, *, constraint=False, probability=False):
        if not isinstance(self._material, dict) or material_diagnostics(self._material.get('draft', {})):
            self.message.setText('Select a valid Material input before declaring a physical response.')
            return None
        settings = self._material['draft']['settings']
        names = ['stress_xx', 'stress_yy', 'stress_zz', 'stress_xy', 'stress_xz', 'stress_yz']
        if settings['model'] == 'neo_hooke':
            names.append('energy')
        name, accepted = QInputDialog.getItem(self, 'Material response', 'Exact response from the bound Material protocol', names, editable=False)
        if not accepted:
            return None
        reduction, accepted = QInputDialog.getItem(self, 'History reduction', 'Explicit scalar response measure', ['final', 'max', 'min', 'mean', 'abs_max'], editable=False)
        if not accepted:
            return None
        result = {'response': name, 'unit': settings['stress_unit'], 'reduction': reduction,
                  'component': name[7:] if name.startswith('stress_') else 'energy_per_reference_volume', 'location': 'material_point'}
        if constraint or probability:
            operator, accepted = QInputDialog.getItem(self, 'Declared threshold', 'Physical response operator', ['<=', '>='] if constraint else ['>', '>=', '<', '<='], editable=False)
            if not accepted:
                return None
            limit, accepted = QInputDialog.getDouble(self, 'Declared threshold', 'Limit [' + settings['stress_unit'] + ']', 0., -1e100, 1e100, 8)
            if not accepted:
                return None
            result.update(operator=operator, limit=limit)
            if constraint:
                result['scale'] = 1.
        else:
            direction, accepted = QInputDialog.getItem(self, 'Objective direction', 'Research objective', ['minimize', 'maximize'], editable=False)
            if not accepted:
                return None
            result.update(direction=direction, scale=1.)
        return result

    def choose_operation_response(self):
        mode = self.mode.currentText()
        if mode not in ('optimize', 'uq', 'epsilon'):
            return
        declaration = self._physical_definition(probability=mode == 'uq')
        if declaration is None:
            return
        self._commit_editor()
        options = self.operation_options.value()
        if mode == 'optimize':
            options['objective'] = declaration
        else:
            key = 'thresholds' if mode == 'uq' else 'objectives'
            if not isinstance(options.get(key, []), list):
                self.message.setText('The visible ' + key + ' field must be a list; its current content was preserved.')
                return
            options.setdefault(key, []).append(declaration)
        self._replace_options(options)

    def choose_operation_constraint(self):
        if self.mode.currentText() not in ('optimize', 'epsilon'):
            return
        declaration = self._physical_definition(constraint=True)
        if declaration is None:
            return
        self._commit_editor()
        options = self.operation_options.value()
        if not isinstance(options.get('constraints', []), list):
            self.message.setText('Constraints must be a typed list; its current content was preserved.')
            return
        options.setdefault('constraints', []).append(declaration)
        self._replace_options(options)

    def choose_distribution(self):
        if self.mode.currentText() != 'uq':
            return
        draft = self.edited_draft()
        variables = [row for row in draft['variables'] if row.get('free') is True]
        if not variables:
            self.message.setText('Select at least one free Material coefficient before declaring distributions.')
            return
        name, accepted = QInputDialog.getItem(self, 'Uncertain coefficient', 'Free Material coefficient', [row['id'] for row in variables], editable=False)
        if not accepted:
            return
        law, accepted = QInputDialog.getItem(self, 'Input distribution', 'Declared marginal (parameters remain editable)', ['uniform', 'normal', 'truncnorm', 'lognormal'], editable=False)
        if not accepted:
            return
        variable = next(row for row in variables if row['id'] == name)
        distribution = {'distribution': law, 'unit': variable['unit']}
        if law == 'uniform':
            distribution.update(lower=variable['lower'], upper=variable['upper'])
        else:
            distribution.update(mean=variable['value'], std='')
        options = self.operation_options.value()
        if not isinstance(options.get('distributions', {}), dict):
            self.message.setText('Distributions must be a typed object; its current content was preserved.')
            return
        if name in options.get('distributions', {}):
            self.message.setText('This coefficient already has a visible distribution. Edit its typed fields or remove it before replacing it.')
            return
        options.setdefault('distributions', {})[name] = distribution
        self._replace_options(options)
        self.message.setText('Distribution added as an editable declaration. Confirm its parameters, independence and source reference before Apply and Run.')

    def choose_epsilon_threshold(self):
        if self.mode.currentText() != 'epsilon':
            return
        self._commit_editor()
        options = self.operation_options.value()
        objectives, primary = options.get('objectives'), options.get('primary_index', 0)
        if not isinstance(objectives, list) or len(objectives) < 2 or type(primary) is not int or not 0 <= primary < len(objectives):
            self.message.setText('Declare at least two objectives and a valid primary_index before adding secondary thresholds.')
            return
        secondary = [definition for index, definition in enumerate(objectives) if index != primary]
        labels = [str(index) + ': ' + str(definition.get('response', 'undeclared')) + ' [' + str(definition.get('unit', '?')) + ']' for index, definition in enumerate(secondary)]
        chosen, accepted = QInputDialog.getItem(self, 'Epsilon threshold', 'Secondary objective order (primary excluded)', labels, editable=False)
        if not accepted:
            return
        index = labels.index(chosen)
        value, accepted = QInputDialog.getDouble(self, 'Epsilon threshold', 'Explicit limit [' + str(secondary[index].get('unit', '?')) + ']', 0., -1e100, 1e100, 8)
        if not accepted:
            return
        grid = options.get('threshold_grid', [])
        if not isinstance(grid, list) or any(not isinstance(row, list) for row in grid) or len(grid) > len(secondary):
            self.message.setText('Threshold grid must be a typed list of secondary threshold lists. Its current content was preserved.')
            return
        grid.extend([] for _ in range(len(secondary) - len(grid)))
        grid[index].append(value)
        options['threshold_grid'] = grid
        self._replace_options(options)


    def command(self, operation, arguments=None, *, after=None):
        self._commit_editor()
        if not self.document or self.conflict or self.local_dirty and operation != 'numerical.update':
            self.message.setText('Apply edited plan first; commands use an exact service generation.')
            return False
        document = deepcopy(self.document)
        submitted = self.edited_draft()
        def accepted(receipt):
            late = self.edited_draft() != submitted
            self.conflict = False
            if late:
                self.document=deepcopy(receipt['document'])
                self.local_dirty=True
                self._populate_runs(receipt.get('job',{}).get('id'))
                self._update_actions()
                self.message.setText('제출 뒤 편집한 입력을 유지했습니다. 새 입력을 적용한 뒤 계속하세요.')
                return
            self.local_dirty = False
            self._show_document(receipt['document'], receipt.get('job', {}).get('id'))
            self.message.setText('Applied through the Numerical document owner: ' + operation)
            if type(self) is NumericalWindow and self.document.get('diagnostics'):
                self.locate_input_error()
            if after:
                after()
            elif receipt.get('job'):
                QTimer.singleShot(0, self.refresh_result)
        return self._call(lambda: self.client.document_command(document['id'], operation, arguments or {}, session_id=document['session_id'], expected_generation=document['generation'], command_id='C'+uuid.uuid4().hex), accepted)

    def apply_inputs(self, *, after=None):
        return self.command('numerical.update', {'draft': self.edited_draft()}, after=after)

    def save_document(self, *, after=None):
        if self.local_dirty:
            return self.apply_inputs(after=lambda: self.command('document.save', after=after))
        return self.command('document.save', after=after)

    def _list_select(self, kind, callback):
        def listed(payload):
            documents = [item for item in payload['documents'] if item.get('kind') == kind]
            if not documents:
                self.message.setText('No ' + kind + ' documents are available.')
                return
            labels = [item['title'] + ' — ' + item['id'] for item in documents]
            label, ok = QInputDialog.getItem(self, 'Select '+kind, 'Document', labels, editable=False)
            if ok:
                callback(documents[labels.index(label)])
        self._call(self.client.documents, listed)

    def choose_material(self):
        def chosen(document):
            draft = self.edited_draft()
            replacement = from_material_document(document)
            draft.update(material=replacement['material'], variables=replacement['variables'])
            # Old experiments stay visible; incompatible protocol/model blocks running.
            self._show_document({**self.document, 'draft': draft})
            self._edited()
        self._list_select('material', chosen)

    def choose_observation(self):
        if not isinstance(self._material,dict) or material_diagnostics(self._material.get('draft',{})):
            self.message.setText('먼저 유효한 재료를 선택하세요.'); return
        def data_chosen(document):
            runs=document.get('runs',[])
            if not runs:
                self.message.setText('Data에서 열 설정을 적용하고 가져오기를 실행하세요.'); return
            labels=['가져오기 '+str(i+1) for i in range(len(runs))]
            label,ok=QInputDialog.getItem(self,'시험 추가',document['title'],labels,len(labels)-1,False)
            if not ok:return
            run=runs[labels.index(label)]
            token=(self.document['id'],self.document['session_id'])
            def inspected(result):
                if result.get('execution_status')!='SUCCEEDED':
                    self.message.setText('선택한 가져오기에 성공한 관측이 없습니다.');return
                from .material_test_dialog import ExperimentDialog
                dialog=ExperimentDialog(self._material['draft']['settings'],result,self)
                if dialog.exec()!=QDialog.DialogCode.Accepted:return
                if token!=(self.document['id'],self.document['session_id']):return
                value=dialog.value
                self._experiments=self.edited_draft()['experiments']
                index=1
                while 'Test'+str(index) in {e['id'] for e in self._experiments}: index+=1
                experiment={'id':'Test'+str(index),'role':value['role'],'source':{
                    'document_id':document['id'],'job_id':run['job_id'],'response':value['name'],
                    'input_revision':run['input_revision'],'input_sha256':run['input_sha256']},
                    'response':value['response'],'settings':value['settings'],'weight':value['weight'],'scale':value['scale']}
                if value['kinematics'] is not None:experiment['kinematics']=value['kinematics']
                self._experiments.append(experiment)
                self._populating=True; self._populate_experiments();self._populating=False
                self._edited()
            self._call(lambda:self.client.document_result(document['id'],run['job_id']),inspected,
                relevant=lambda:token==(self.document['id'],self.document['session_id']))
        self._list_select('data',data_chosen)

    def change_protocol(self):
        rows=sorted({item.row() for item in self.experiments.selectedIndexes()})
        if len(rows)!=1:
            self.message.setText('조건을 편집할 시험 하나를 선택하세요.'); return
        row=rows[0]; experiments=self.edited_draft()['experiments']
        experiment=deepcopy(experiments[row]); source=experiment['source']
        token=(self.document['id'],self.document['session_id'])
        def inspected(result):
            from .material_test_dialog import ExperimentDialog
            dialog=ExperimentDialog(experiment['settings'],result,self,experiment=experiment)
            if dialog.exec()!=QDialog.DialogCode.Accepted:return
            current=self.edited_draft()['experiments']
            if token!=(self.document['id'],self.document['session_id']) or row>=len(current) or current[row]!=experiment:
                self.message.setText('선택 시험이 변경되었습니다. 조건을 다시 여세요.');return
            value=dialog.value
            current[row].update(settings=value['settings'],role=value['role'],response=value['response'],
                weight=value['weight'],scale=value['scale'])
            current[row]['source']['response']=value['name']
            if value['kinematics'] is None:current[row].pop('kinematics',None)
            else:current[row]['kinematics']=value['kinematics']
            self._experiments=current
            self._populating=True;self._populate_experiments();self._populating=False
            self._edited()
        self._call(lambda:self.client.document_result(source['document_id'],source['job_id']),inspected,
            relevant=lambda:token==(self.document['id'],self.document['session_id']))

    def remove_experiments(self):
        rows = {item.row() for item in self.experiments.selectedIndexes()}
        self._experiments = [item for row, item in enumerate(self.edited_draft()['experiments']) if row not in rows]
        self._populating = True
        self._populate_experiments()
        self._populating = False
        self._edited()

    def open_identification(self):
        if not self.document or not self.selected_job():
            self.message.setText('저장한 피팅 계산을 선택하세요.')
            return False
        from .identification_window import IdentificationWindow
        window = IdentificationWindow(self.client, self.document['id'], self.selected_job(), self)
        self._identification_windows = getattr(self, '_identification_windows', []) + [window]
        window.show()
        return True

    def selected_job(self):
        rows = sorted({item.row() for item in self.runs.selectedIndexes()})
        return (self.runs.item(rows[0],0).data(Qt.ItemDataRole.UserRole) or self.runs.item(rows[0],0).text()) if len(rows)==1 else None

    def _populate_runs(self, prefer_job=None):
        selected = prefer_job or self.selected_job()
        self.runs.blockSignals(True)
        runs = self.document.get('runs', [])
        self.runs.setRowCount(len(runs))
        if selected is None and runs:
            selected = runs[-1]['job_id']
        for row, run in enumerate(runs):
            values = [run['job_id'], self._statuses.get(run['job_id'], {}).get('state', run.get('retained_state', 'Awaiting status')), f"g{run['input_generation']} / {run.get('input_revision')}", 'current plan' if run.get('is_current_input') and not self.local_dirty else 'earlier input']
            for col, value in enumerate(values):
                self._set_cell(self.runs, row, col, value, False)
            self.runs.item(row,0).setText('실행 '+str(row+1))
            self.runs.item(row,0).setToolTip(run['job_id'])
            if run['job_id'] == selected:
                self.runs.selectRow(row)
        self.runs.blockSignals(False)

    def _selection_changed(self):
        self._draw_result()
        self.refresh_result()

    def refresh_document(self):
        if self._closed or not isValid(self):
            return
        if self._callbacks or self._pending_adoption:
            return
        if self._analysis_job and not self._busy:
            return self.refresh_analysis()
        if self._busy or not self.document:
            return
        if getattr(self,'_trial_source_queue',None):
            return self._drain_trial_sources()
        identifier = self.document['id']
        def received(remote):
            changed = (remote['session_id'], remote['generation']) != (self.document['session_id'], self.document['generation'])
            editing = self.local_dirty or any(table.state() == QAbstractItemView.State.EditingState for table in (self.variables, self.experiments, self.operation_options.inputs))
            if changed and editing:
                self.conflict = True
                self.message.setText('Remote inputs changed while editing. Your cells are preserved; reload or keep edits as a new plan.')
            elif not editing and not self.conflict:
                self._show_document(remote)
            self._update_actions()
            QTimer.singleShot(0, self.refresh_result)
        self._call(lambda: self.client.document_read(identifier), received, background=True)

    def refresh_result(self):
        if self._closed or not isValid(self):
            return
        job = self.selected_job()
        if self._busy or self._callbacks or self._pending_adoption or not job or job in self._result_cache or monotonic() < self._result_after.get(job, 0):
            return
        document_id = self.document['id']
        session_id = self.document['session_id']
        run = next(item for item in self.document['runs'] if item['job_id'] == job)
        self._result_after[job] = monotonic() + max(1, self.timer.interval()/1000)
        def read():
            try:
                status = {'state': run['retained_state'], 'result_refs': [1] if run.get('retained_result') else [], 'error': run.get('retained_error')} if run.get('retention_complete') else self.client.status(job)
                result = self.client.document_result(document_id, job) if status.get('result_refs') else None
                return status, result, None
            except Exception as error:
                return {}, None, str(error)
        def received(payload):
            status, result, error = payload
            self._statuses[job] = status
            if result is not None:
                self._result_cache[job] = result
            elif status.get('state') in TERMINAL:
                self._result_cache[job] = {'execution_status': status['state'], 'error': status.get('error')}
            if error:
                self._result_errors[job] = error
            else:
                self._result_errors.pop(job, None)
            current_job=self.selected_job()
            self._populate_runs(current_job)
            self._draw_result()
        self._call(read, received, relevant=lambda: not self._allow_close and self.document is not None
            and (self.document['id'],self.document['session_id'])==(document_id,session_id), background=True)

    def retry_result(self):
        job = self.selected_job()
        self._result_after.pop(job, None)
        self._result_cache.pop(job, None)
        self._trial_source_errors.clear()
        self._draw_result()
        self.refresh_result()

    def _draw_result(self):
        job = self.selected_job()
        result = self._result_cache.get(job, {})
        candidates = result.get('candidates', [])
        selected = self.selected_candidate() if self._drawn_result_job == job else None
        self._drawn_result_job = job
        self.candidates.clearSelection()
        self.candidates.setRowCount(len(candidates))
        for row, candidate in enumerate(candidates):
            values = [candidate['candidate_id'], candidate_state(candidate), candidate.get('values'), candidate.get('objective'), candidate.get('failure_reason')]
            for col, value in enumerate(values):
                self._set_cell(self.candidates, row, col, value, False)
            self.candidates.item(row,0).setText('후보 '+str(row+1))
            self.candidates.item(row,0).setToolTip(candidate['candidate_id'])
            self.candidates.item(row,2).setText(', '.join(str(k)+'='+str(v) for k,v in (candidate.get('values') or {}).items()))
            if candidate['candidate_id'] == selected:
                self.candidates.selectRow(row)
        self.figure.clear()
        if hasattr(self,'curve_summary'): self.curve_summary.clear()
        curves = result.get('curves', [])
        if hasattr(self,'curve_selector'):
            previous=self.curve_selector.currentData()
            self.curve_selector.blockSignals(True); self.curve_selector.clear()
            for curve in curves:
                run=next((r for r in self.document.get('runs',[]) if r['job_id']==job),{})
                trial=next((e for e in run.get('draft',{}).get('experiments',[]) if e['id']==curve.get('experiment_id')), {})
                label=('검증' if curve.get('role')=='holdout' else '피팅')+' / '+self._trial_label(trial,curve.get('observations',{}),self.curve_selector.count()+1)
                self.curve_selector.addItem(label,curve.get('experiment_id'))
            selected_index=self.curve_selector.findData(previous)
            self.curve_selector.setCurrentIndex(max(0,selected_index))
            self.curve_selector.blockSignals(False)
        if curves:
            run=next((r for r in self.document.get('runs',[]) if r['job_id']==job),{})
            self._queue_trial_sources(run.get('draft',{}).get('experiments',[]))
            self._draw_fit_curve(result)
        else:
            if hasattr(self,'plot_axis'): self.plot_axis.setEnabled(False)
            self._draw_study_summary(result, job)
        self.canvas.draw_idle()
        self.details.setPlainText(json.dumps({'document': self.document, 'view_error': self._view_error, 'selected_status': self._statuses.get(job), 'read_error': self._result_errors.get(job), 'selected_result': result}, indent=2, ensure_ascii=False))

    def _curve_changed(self, *_):
        if self._populating: return
        self.curve_selector.setToolTip(self.curve_selector.currentText())
        result=self._result_cache.get(self.selected_job(),{})
        if result.get('curves'):
            self.figure.clear(); self._draw_fit_curve(result); self.canvas.draw_idle()

    def _draw_fit_curve(self,result):
        from caelab.material_test import physical_residual, deformation_plot_axis
        curves=result.get('curves',[])
        index=max(0,self.curve_selector.currentIndex())
        if index>=len(curves):return
        curve=curves[index]
        obs=curve.get('observations',{})
        axes=obs.get('axes',[{}]); axis=axes[0] if axes else {}
        x,y=axis.get('values',[]),obs.get('value',[])
        run=next((r for r in self.document.get('runs',[]) if r['job_id']==self.selected_job()),{})
        trial=next((e for e in run.get('draft',{}).get('experiments',[]) if e['id']==curve.get('experiment_id')), {})
        recipe=trial.get('kinematics')
        self.plot_axis.setEnabled(bool(recipe))
        if not recipe:
            self.plot_axis.blockSignals(True); self.plot_axis.setCurrentIndex(0); self.plot_axis.blockSignals(False)
        self.plot_axis.setToolTip('같은 원본 행과 시간의 측정값' if recipe else '이 시험은 측정 변형 채널을 연결하지 않았습니다.')
        if recipe and self.plot_axis.currentData()=='measured':
            key=self._trial_source_key(trial)
            retained=self._trial_sources.get(key)
            try:
                if retained is None:
                    raise ValueError(self._trial_source_errors.get(key,'저장된 변형 이력을 읽는 중입니다.'))
                axis=deformation_plot_axis(obs,retained['result'],recipe)
                x=axis['values']
            except (ValueError,KeyError,TypeError) as error:
                self.figure.add_subplot(111).set_title('측정 변형축을 표시할 수 없습니다.',fontsize=11)
                self.curve_summary.setText(str(error)+' 시간축은 계속 사용할 수 있습니다.')
                return
        prediction=curve.get('prediction',[])
        top,bottom=self.figure.subplots(2,1,sharex=True,gridspec_kw={'height_ratios':[3,1]})
        # Preserve explicit gaps; never join separated observed intervals.
        segments=obs.get('segments') or [{'rows':[0,len(x)]}]
        for segment in segments:
            first,last=segment.get('rows',[0,len(x)])
            if len(x)==len(y):
                top.plot(x[first:last],y[first:last],'o',markersize=3,label='관측' if first==0 else None)
            if isinstance(prediction,list) and len(prediction)==len(x):
                top.plot(x[first:last],prediction[first:last],label='최종 예측' if first==0 else None)
        _,residual=physical_residual(curve)
        rx=x if len(residual)==len(x) else []
        for segment in segments:
            first,last=segment.get('rows',[0,len(rx)])
            bottom.plot(rx[first:last],residual[first:last],'o-',markersize=2)
        bottom.axhline(0,color='gray',linewidth=.7)
        unit=obs.get('unit','?')
        top.set_ylabel(str(obs.get('component',''))+' ['+unit+']')
        bottom.set_ylabel('예측−관측\n['+unit+']')
        bottom.set_xlabel(str(axis.get('name','time'))+' ['+str(axis.get('unit','?'))+']')
        if top.lines:top.legend(fontsize=9)
        status=curve.get('execution_status','UNKNOWN')
        top.set_title(('검증' if curve.get('role')=='holdout' else '피팅')+' / '+str(obs.get('component',''))+' / '+status,fontsize=11)
        self.curve_summary.setText('최종 계수: '+', '.join(str(k)+'='+str(v) for k,v in result.get('parameters',{}).items())+
            '    RMSE '+str(curve.get('rmse','없음'))+' '+unit+
            ('    '+str(curve.get('failure_reason','')) if status!='SUCCEEDED' else ''))
        for ax in (top,bottom):ax.grid(True,alpha=.2)

    def locate_input_error(self):
        if not self.document or self._view_error:return
        from caelab.numerical_document import diagnostics
        draft=self.edited_draft()
        errors=diagnostics(draft)
        self.message.setText(errors[0]['message'] if errors else '입력 형식이 유효합니다. 실행 시 정확한 관측과 재료를 다시 확인합니다.')
        for row,variable in enumerate(draft.get('variables',[])):
            columns=[]
            for key,col in (('value',2),('lower',3),('upper',4)):
                value=variable.get(key)
                if (key=='value' or variable.get('free') is True) and (type(value) not in (int,float) or not math.isfinite(value)):
                    columns.append(col)
            if not columns and variable.get('free') is True:
                if not variable['lower']<variable['upper'] or not variable['lower']<=variable['value']<=variable['upper']:
                    columns=[3]
            if columns:
                self.variables.setCurrentCell(row,columns[0]);self.variables.scrollToItem(self.variables.currentItem())
                self.variables.setFocus();return
        if draft.get('mode')=='fit':
            if not draft.get('experiments'):
                self.add_experiment.setFocus();return
            if errors:
                self.experiments.selectRow(0);self.edit_protocol.setFocus()

    def run_plan(self):
        if self.local_dirty:
            return self.apply_inputs(after=lambda:self.command('numerical.run'))
        return self.command('numerical.run')

    def cancel_run(self):
        job=self.selected_job()
        if job and self._statuses.get(job,{}).get('state') in ('QUEUED','RUNNING'):
            return self._call(lambda:self.client.cancel(job),
                lambda _:self.message.setText('취소를 요청했습니다. 이미 계산한 후보와 이전 결과는 유지됩니다.'))

    def open_material(self):
        if not self._material:return
        from .material_window import MaterialWindow
        window=MaterialWindow(self.client,document_id=self._material['document_id'])
        self.__dict__.setdefault('_material_windows',[]).append(window);window.show()
        return window

    def _draw_study_summary(self, result, job):
        ax = self.figure.add_subplot(111)
        kind = result.get('kind')
        if kind == 'uq' and result.get('probability_statistics'):
            statistics = result['probability_statistics']
            values = [(item, item.get('mean')) for item in statistics if type(item.get('mean')) in (int, float) and math.isfinite(item['mean'])]
            if values:
                # Separate axes preserve distinct physical response units.
                self.figure.clear()
                axes = self.figure.subplots(len(values), 1, squeeze=False)
                for axis, (item, mean) in zip(axes[:, 0], values):
                    deviation = item.get('std')
                    axis.errorbar([0], [mean], yerr=deviation if type(deviation) in (int, float) and math.isfinite(deviation) else None, fmt='o', capsize=5)
                    axis.set_xticks([0], [str(item.get('response', 'response'))])
                    axis.set_ylabel('mean ± sample std [' + str(item.get('unit', '?')) + ']')
                    axis.set_title('Actual UQ: ' + str(item.get('valid_count', 0)) + ' valid, ' + str(item.get('failed_count', 0)) + ' failed; conditional on valid evaluations', fontsize=9)
                return
        if kind == 'optimization':
            rows = [(index, row) for index, row in enumerate(result.get('candidates', []))
                    if actual_candidate(row) and type(row.get('objective')) in (int, float) and math.isfinite(row['objective'])]
            if rows:
                ax.scatter([index for index, _ in rows], [row['objective'] for _, row in rows],
                           c=['tab:blue' if row.get('feasible') else 'tab:orange' for _, row in rows], s=20)
                definition = result.get('objective_definition', {})
                ax.set_xlabel('Actual evaluated candidate order')
                ax.set_ylabel(str(definition.get('response', 'objective')) + ' [' + str(definition.get('unit', '?')) + ']')
                ax.set_title('Actual optimization objectives · blue feasible / orange infeasible · ' + str(result.get('termination_reason', '')))
                return
        if kind == 'epsilon_optimization':
            run = next((row for row in self.document.get('runs', []) if row.get('job_id') == job), {}) if self.document else {}
            definitions = run.get('draft', {}).get('operation_options', {}).get('objectives', [])
            if len(definitions) >= 2:
                from caelab.numerical import _scalar, EvaluationFailed
                points = []
                for row in result.get('candidates', []):
                    try:
                        points.append((_scalar(row, definitions[0]), _scalar(row, definitions[1]), row))
                    except (EvaluationFailed, ValueError, KeyError, TypeError):
                        continue
                if points:
                    archive = set(result.get('pareto', {}).get('nondominated_ids', []))
                    ax.scatter([point[0] for point in points], [point[1] for point in points],
                               c=['tab:blue' if point[2]['candidate_id'] in archive else 'tab:gray' for point in points], s=20)
                    for axis, definition in ((ax.set_xlabel, definitions[0]), (ax.set_ylabel, definitions[1])):
                        axis(str(definition.get('response')) + ' / ' + str(definition.get('reduction')) + ' [' + str(definition.get('unit', '?')) + ']')
                    ax.set_title('Actual epsilon search candidates · blue retained nondominated candidates; global optimality unproven')
                    return
        ax.text(.5, .5, 'Actual candidate values and failures are retained in the table.\nSelect a study with curves, optimization objectives or declared UQ statistics to plot.',
                ha='center', va='center', transform=ax.transAxes)
        ax.set_axis_off()


    def selected_candidate(self):
        rows = sorted({item.row() for item in self.candidates.selectedIndexes()})
        item = self.candidates.item(rows[0], 0) if len(rows) == 1 else None
        return (item.data(Qt.ItemDataRole.UserRole) or item.text()) if item is not None else None

    def adopt_candidate(self):
        if self._adoption_receipt is not None:
            self.message.setText('앞선 적용 결과를 먼저 확인하세요. 아래의 적용 결과 다시 확인 버튼을 사용하세요.')
            return False
        self._commit_editor()
        job = self.selected_job()
        candidate = self.selected_candidate()
        if self.local_dirty or self.conflict or not job or not candidate:
            self.message.setText('계획의 변경 사항을 적용한 뒤 계산이 끝난 후보 하나를 선택하세요.')
            return
        selected = next((row for row in self._result_cache.get(job, {}).get('candidates', [])
                         if row.get('candidate_id', row.get('id')) == candidate), None)
        if selected is not None and selected.get('prediction_status') == 'PREDICTED':
            self.message.setText('이 후보는 예측값입니다. 실제 계산이 끝난 후보를 선택하세요.')
            return False
        if self._pending_adoption or self._callbacks or self._busy and not self._busy_background:
            self.message.setText('현재 작업이 끝나면 후보를 적용할 수 있습니다.')
            return False
        document_id, document_session = self.document['id'], self.document['session_id']
        run = next(item for item in self.document['runs'] if item['job_id'] == job)
        reference = deepcopy(run['draft']['material'])
        def same_selection():
            same = (self.document is not None and
                    (self.document['id'], self.document['session_id']) == (document_id, document_session) and
                    self.selected_job() == job and self.selected_candidate() == candidate and
                    not self.local_dirty and not self.conflict)
            if not same:
                self.message.setText('계획이나 선택이 바뀌어 적용을 취소했습니다. 적용할 후보를 다시 선택하세요.')
            return same
        def target_read(target):
            if not same_selection():
                return
            if target.get('id') != reference['document_id'] or target.get('session_id') != document_session:
                self.message.setText('원래 재료 문서의 연결이 바뀌어 적용하지 않았습니다. 재료를 다시 열어 확인하세요.')
                return
            from caelab.numerical_document import adopted_draft
            try:
                proposed=adopted_draft(run,self._result_cache[job],candidate)
            except (ValueError,KeyError,TypeError) as error:
                self.message.setText(str(error)); return
            old=target['draft']['settings']['parameters']
            changes='\n'.join(str(name)+': '+str(old.get(name,'?'))+' → '+str(value)+' '+('1' if name=='nu' else target['draft']['settings']['stress_unit'])
                for name,value in proposed['settings']['parameters'].items())
            if QMessageBox.question(self, '계수를 재료에 적용', target['title']+'\n\n'+changes+'\n\n적용 후 재료 창에서 별도로 저장할 수 있습니다.', QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Cancel) != QMessageBox.StandardButton.Yes:
                self.message.setText('적용을 취소했습니다. 재료 계수는 바뀌지 않았습니다.')
                return
            if not same_selection():
                return
            def adopted(receipt):
                self.message.setText('계수를 적용했습니다. 파일 → 재료 열기 / 저장에서 확인하고 저장하세요. 재료의 실행 취소로 되돌릴 수 있습니다.')
            request = dict(document_id=document_id, job_id=job, candidate_id=candidate,
                material_document_id=target['id'], session_id=target['session_id'],
                expected_generation=target['generation'], command_id='C'+uuid.uuid4().hex)
            self._submit_adoption_receipt('material', request, adopted)
        def begin():
            if same_selection():
                self._call(lambda: self.client.document_read(reference['document_id']), target_read)
        if self._busy_background:
            self._pending_adoption = begin
            self.message.setText('현재 자료 읽기가 끝나면 선택한 후보의 계수를 확인합니다.')
            self._update_actions()
            return True
        begin()
        return True

    def analyze_result(self):
        job = self.selected_job()
        result = self._result_cache.get(job, {})
        if result.get('kind') not in ('doe', 'uq', 'optimization', 'epsilon_optimization'):
            self.message.setText('Select an actual retained candidate study for response analysis.')
            return
        names = sorted({name for row in result.get('candidates', []) for name in row.get('responses', {})}
                       | {entry['response'] for row in result.get('candidates', []) for entry in row.get('response_reductions', [])})
        if not names:
            self.message.setText('No actual candidate responses are available.')
            return
        name, ok = QInputDialog.getItem(self, 'Analyze actual candidates', 'Physical response', names, editable=False)
        if not ok:
            return
        response = next((row['responses'][name] for row in result['candidates'] if name in row.get('responses', {})), None)
        retained_reductions = sorted({entry['reduction'] for row in result['candidates']
                                     for entry in row.get('response_reductions', [])
                                     if entry['response'] == name})
        if response is not None:
            choices = [response.get('reduction', 'none')] if response.get('kind') == 'scalar' else ['max','min','mean','final','abs_max']
        else:
            choices = retained_reductions
        if not choices:
            self.message.setText('No scalar reduction was retained for this physical response.')
            return
        reduction, ok = QInputDialog.getItem(self, 'Explicit reduction', 'Scalar statistic', choices, editable=False)
        if not ok:
            return
        if response is None:
            response = next((entry for row in result['candidates'] for entry in row.get('response_reductions', [])
                             if entry['response'] == name and entry['reduction'] == reduction), None)
        if response is None:
            self.message.setText('The selected reduction was not retained. Original results remain unchanged; select an available response/reduction.')
            return
        declaration = {'response': name, 'unit': response['unit'], 'reduction': reduction, **{key: response[key] for key in ('component','location','measure','frame') if key in response}}
        def analyzed(job):
            self._analysis_job = job['id']
            self.message.setText('Candidate analysis submitted: '+job['id']+'. Read its actual result when the job finishes.')
            QTimer.singleShot(1000, self.refresh_analysis)
        try:
            from caelab.research_operations import result_reference
            reference = result_reference(self.document, job, result)
        except ValueError as error:
            self.message.setText(str(error))
            return
        self._call(lambda: self.client.submit('analyze', {'result_refs': {'table': reference}, 'responses': [declaration]}), analyzed)

    def refresh_analysis(self):
        if self._closed or not isValid(self):
            return
        job = self._analysis_job
        if not job or self._busy or self._callbacks or self._pending_adoption:
            return
        def read():
            status = self.client.status(job)
            return status, self.client.result(job) if status.get('result_refs') else None
        def received(payload):
            status, result = payload
            if result is not None:
                self.details.setPlainText(json.dumps(result, indent=2, ensure_ascii=False))
                self.tabs.setCurrentWidget(self.details)
                self._analysis_job = None
                self.message.setText('Read actual candidate analysis: '+job)
            elif status.get('state') in TERMINAL:
                self._analysis_job = None
                self.message.setText('Candidate analysis '+status['state']+': '+display(status.get('error')))
        self._call(read, received, background=True)

    def _update_actions(self):
        present = self.document is not None
        available = not (self._busy or self._callbacks or self._pending_adoption)
        enabled = present and available and not self.conflict
        self.editor.setEnabled(enabled and not self._view_error)
        self.apply_button.setEnabled(enabled and self.local_dirty and not self._view_error)
        blocked = present and bool(self.document.get('diagnostics'))
        self.run_button.setEnabled(enabled and not self.local_dirty and not blocked)
        self.save_action.setEnabled(enabled)
        self.undo_action.setEnabled(enabled and not self.local_dirty and self.document.get('can_undo', False))
        self.redo_action.setEnabled(enabled and not self.local_dirty and self.document.get('can_redo', False))
        self.new_action.setEnabled(available)
        self.open_action.setEnabled(available)
        for button in (self.read_button, self.adopt_button, self.analysis_button):
            button.setEnabled(enabled and bool(self.selected_job()))
        # Polling is read-only; it must not swallow a user's adoption click.
        self.adopt_button.setEnabled(present and not self.conflict and not self.local_dirty and
                                     self._adoption_receipt is None and
                                     not self._callbacks and self._pending_adoption is None and
                                     (not self._busy or self._busy_background) and bool(self.selected_job()))
        self._update_adoption_receipt_actions()
        self.reload_button.setVisible(self.conflict)
        self.copy_button.setVisible(self.conflict)
        if present:
            self.setWindowTitle('Numerical Plan — '+self.document['title']+(' *' if self.local_dirty or self.document.get('dirty') else ''))
            self.identity.setText('적용할 변경 있음' if self.local_dirty else '입력 오류' if blocked else '저장할 변경 있음' if self.document.get('dirty') else '')
            self.identity.setToolTip(self.document['id'])
            if hasattr(self,'stop_button'):
                job=self.selected_job()
                self.stop_button.setEnabled(enabled and self._statuses.get(job,{}).get('state') in ('QUEUED','RUNNING'))
                self.run_button.setText('피팅 실행' if self.mode.currentText()=='fit' else '연구 실행')

    def _leave(self, continuation):
        self._commit_editor()
        if self._busy:
            self.message.setText('Wait for the document request before leaving; jobs remain service-owned.')
            return
        if not self.document or not (self.local_dirty or self.document.get('dirty')):
            continuation()
            return
        box = QMessageBox(self)
        box.setWindowTitle('Unsaved Numerical Plan')
        box.setText('Save the plan before leaving?')
        save = box.addButton('Save', QMessageBox.ButtonRole.AcceptRole)
        keep = box.addButton('Keep service draft', QMessageBox.ButtonRole.DestructiveRole)
        box.addButton(QMessageBox.StandardButton.Cancel)
        box.exec()
        if box.clickedButton() == save:
            self.save_document(after=continuation)
        elif box.clickedButton() == keep and not self.conflict:
            self.apply_inputs(after=continuation) if self.local_dirty else continuation()

    def new_document(self):
        self._leave(lambda: self.open_document())

    def choose_document(self):
        self._leave(lambda: self._list_select('numerical', lambda document: self.open_document(document_id=document['id'])))

    def reload_remote(self):
        if QMessageBox.question(self, 'Reload plan', 'Discard unapplied cells and reload the service version?', QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Cancel) == QMessageBox.StandardButton.Yes:
            self._call(lambda: self.client.document_read(self.document['id']), self._opened)

    def closeEvent(self, event):
        if self._allow_close:
            self._closed = True
            self.timer.stop()
            self._trial_source_queue.clear()
            self._pending_adoption = None
            if self._worker is not None:
                self._worker.abandon()
            self._worker = None
            self._busy = self._busy_background = False
            event.accept()
        else:
            event.ignore()
            def close():
                self._allow_close = True
                self.close()
            self._leave(close)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--service', default=os.environ.get('CAELAB_SERVICE_URL'))
    parser.add_argument('--document-id')
    args = parser.parse_args(argv)
    if not args.service:
        parser.error('--service or CAELAB_SERVICE_URL is required')
    app = QApplication.instance() or QApplication(sys.argv[:1])
    client = Client(args.service)
    if not args.document_id or client.document_read(args.document_id).get('draft',{}).get('mode') == 'request':
        from .request_plan_window import RequestPlanWindow
        window = RequestPlanWindow(client,document_id=args.document_id)
    else:
        window = NumericalWindow(client, document_id=args.document_id)
    window.show()
    return app.exec()


if __name__ == '__main__':
    raise SystemExit(main())
