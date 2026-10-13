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
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (QApplication, QAbstractItemView, QComboBox, QDialog,
    QDialogButtonBox, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QMainWindow,
    QMessageBox, QPushButton, QPlainTextEdit, QSplitter, QTableWidget,
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
        return value if not isinstance(value, (dict, list)) else text
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
        self._allow_close = False
        self._worker = None
        self._result_cache, self._result_errors, self._statuses = {}, {}, {}
        self._result_after = {}
        self._view_error = None
        self._analysis_job = None
        self._material = None
        self._experiments = []
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
        self.resize(1440, 940)
        toolbar = QToolBar('Numerical Plan')
        self.addToolBar(toolbar)
        self.new_action = QAction('New plan', self, shortcut=QKeySequence.New)
        self.request_action = QAction('New calculation request', self)
        self.request_action.triggered.connect(lambda: self.open_request_document())
        toolbar.addAction(self.request_action)
        self.open_action = QAction('Open plan', self, shortcut=QKeySequence.Open)
        self.save_action = QAction('Save', self, shortcut=QKeySequence.Save)
        self.undo_action = QAction('Undo', self, shortcut=QKeySequence.Undo)
        self.redo_action = QAction('Redo', self, shortcut=QKeySequence.Redo)
        for action, handler in ((self.new_action, self.new_document), (self.open_action, self.choose_document),
                                (self.save_action, self.save_document), (self.undo_action, lambda: self.command('document.undo')),
                                (self.redo_action, lambda: self.command('document.redo'))):
            action.triggered.connect(handler)
            toolbar.addAction(action)
        self.apply_button, self.run_button = QPushButton('Apply plan'), QPushButton('Run plan')
        self.apply_button.clicked.connect(self.apply_inputs)
        self.run_button.clicked.connect(lambda: self.command('numerical.run'))
        toolbar.addWidget(self.apply_button)
        toolbar.addWidget(self.run_button)
        self.identity = QLabel()
        toolbar.addWidget(self.identity)
        root = QWidget()
        layout = QVBoxLayout(root)
        self.message = QLabel('Opening Numerical Plan…')
        self.message.setWordWrap(True)
        layout.addWidget(self.message)
        conflicts = QHBoxLayout()
        self.reload_button, self.copy_button = QPushButton('Reload service version'), QPushButton('Keep edits as a new plan')
        self.reload_button.clicked.connect(lambda: self.reload_remote())
        self.copy_button.clicked.connect(lambda: self.open_document(draft=self.edited_draft(), title=self.document['title'] + ' — edits'))
        conflicts.addWidget(self.reload_button)
        conflicts.addWidget(self.copy_button)
        layout.addLayout(conflicts)
        panels = QHBoxLayout()
        self.inputs_panel_button = QPushButton('Hide inputs')
        self.results_panel_button = QPushButton('Hide results')
        self.inputs_panel_button.clicked.connect(lambda: self._toggle_panel('inputs'))
        self.results_panel_button.clicked.connect(lambda: self._toggle_panel('results'))
        panels.addWidget(self.inputs_panel_button)
        panels.addWidget(self.results_panel_button)
        panels.addWidget(QLabel('Drag the dividers to resize or collapse panels.'), 1)
        layout.addLayout(panels)
        self.study_splitter = QSplitter(Qt.Orientation.Vertical)
        self.study_splitter.setObjectName('numericalStudyPanels')
        layout.addWidget(self.study_splitter, 1)
        self.editor = QWidget()
        edit = QVBoxLayout(self.editor)
        model = QHBoxLayout()
        self.material_button = QPushButton('Select Material document…')
        self.material_button.clicked.connect(self.choose_material)
        self.material_label = QLabel('No model selected')
        self.material_label.setWordWrap(True)
        model.addWidget(self.material_button)
        model.addWidget(self.material_label, 1)
        edit.addLayout(model)
        opts = QHBoxLayout()
        self.mode = QComboBox()
        self.mode.addItems(['fit', 'doe', 'optimize', 'uq', 'epsilon'])
        self.method = QComboBox()
        self.method.addItems(['least_squares', 'differential_evolution'])
        self.budget, self.count, self.seed, self.penalty = [QLineEdit() for _ in range(4)]
        for label, widget in [('Mode', self.mode), ('Fit method', self.method), ('Total model-call budget', self.budget), ('DOE count', self.count), ('Seed', self.seed), ('Failure penalty (null = none)', self.penalty)]:
            opts.addWidget(QLabel(label))
            opts.addWidget(widget)
            if isinstance(widget, QLineEdit):
                widget.setMaximumWidth(90)
                widget.textEdited.connect(self._edited)
            else:
                widget.currentTextChanged.connect(self._edited)
        self.mode.currentTextChanged.connect(self._mode_changed)
        edit.addLayout(opts)
        self.variables = QTableWidget(0, 7)
        self.variables.setObjectName('numericalVariables')
        self.variables.setHorizontalHeaderLabels(['Coefficient', 'Unit', 'Current', 'Lower', 'Upper', 'Free', 'Transform'])
        self.variables.itemChanged.connect(self._edited)
        self.input_splitter = QSplitter(Qt.Orientation.Vertical)
        self.input_splitter.setObjectName('numericalInputPanels')
        self.input_splitter.addWidget(self.variables)
        edit.addWidget(self.input_splitter, 1)
        self.experiments_panel = QWidget()
        experiment_layout = QVBoxLayout(self.experiments_panel)
        experiment_layout.setContentsMargins(0, 0, 0, 0)
        buttons = QHBoxLayout()
        self.add_experiment = QPushButton('Add Data observation…')
        self.edit_protocol = QPushButton('Edit selected protocol…')
        self.remove_experiment = QPushButton('Remove selected experiments')
        self.add_experiment.clicked.connect(self.choose_observation)
        self.edit_protocol.clicked.connect(self.change_protocol)
        self.remove_experiment.clicked.connect(self.remove_experiments)
        for button in (self.add_experiment, self.edit_protocol, self.remove_experiment):
            buttons.addWidget(button)
        experiment_layout.addLayout(buttons)
        self.experiments = QTableWidget(0, 8)
        self.experiments.setObjectName('numericalExperiments')
        self.experiments.setHorizontalHeaderLabels(['Experiment', 'Role (fit / holdout)', 'Data import', 'Observed response', 'Model response', 'Weight', 'Error scale', 'Explicit protocol'])
        self.experiments.itemChanged.connect(self._edited)
        experiment_layout.addWidget(self.experiments, 1)
        self.input_splitter.addWidget(self.experiments_panel)
        self.operation_options = _OperationOptions(self)
        self.input_splitter.addWidget(self.operation_options)
        self.input_splitter.setStretchFactor(0, 1)
        self.input_splitter.setStretchFactor(1, 2)
        self.input_splitter.setStretchFactor(2, 3)
        note = QLabel('Fit and holdout are separate histories. DOE, optimization, UQ and epsilon searches evaluate the selected Material protocol with the visible free coefficients and total model-call budget. Objectives use explicit stress/energy reductions. UQ input laws and their source are declarations; epsilon thresholds apply to the listed secondary objectives. Candidate adoption is a separate Material edit.')
        note.setWordWrap(True)
        edit.addWidget(note)
        self.study_splitter.addWidget(self.editor)
        self.results_panel = QWidget()
        results_layout = QVBoxLayout(self.results_panel)
        results_layout.setContentsMargins(0, 0, 0, 0)
        self.result_splitter = QSplitter(Qt.Orientation.Vertical)
        self.result_splitter.setObjectName('numericalResultPanels')
        results_layout.addWidget(self.result_splitter, 1)
        run_panel = QWidget()
        run_layout = QVBoxLayout(run_panel)
        run_layout.setContentsMargins(0, 0, 0, 0)
        self.runs = QTableWidget(0, 4)
        self.runs.setHorizontalHeaderLabels(['Plan job', 'State', 'Submitted input', 'Ownership'])
        self.runs.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.runs.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.runs.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.runs.itemSelectionChanged.connect(self._selection_changed)
        run_layout.addWidget(self.runs, 1)
        actions = QHBoxLayout()
        self.read_button, self.adopt_button, self.analysis_button = QPushButton('Read / retry selected run'), QPushButton('Adopt selected candidate into Material'), QPushButton('Analyze DOE response…')
        self.read_button.clicked.connect(self.retry_result)
        self.adopt_button.clicked.connect(self.adopt_candidate)
        self.analysis_button.clicked.connect(self.analyze_result)
        for button in (self.read_button, self.adopt_button, self.analysis_button):
            actions.addWidget(button)
        run_layout.addLayout(actions)
        self._build_adoption_receipt_ui(run_layout)
        self.result_splitter.addWidget(run_panel)
        self.tabs = QTabWidget()
        self.candidates = QTableWidget(0, 5)
        self.candidates.setHorizontalHeaderLabels(['Candidate', 'Status', 'Coefficients', 'Actual objective', 'Failure'])
        self.candidates.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.candidates.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.candidates.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabs.addTab(self.candidates, 'Actual candidates')
        self.figure = Figure(constrained_layout=True)
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.tabs.addTab(self.canvas, 'Actual curves / study summary')
        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        self.tabs.addTab(self.details, 'Diagnostics / retained input')
        self.result_splitter.addWidget(self.tabs)
        self.result_splitter.setStretchFactor(0, 1)
        self.result_splitter.setStretchFactor(1, 4)
        self.result_splitter.setSizes([120, 420])
        self.study_splitter.addWidget(self.results_panel)
        self.study_splitter.setStretchFactor(0, 1)
        self.study_splitter.setStretchFactor(1, 2)
        self.study_splitter.setSizes([340, 540])
        self.setCentralWidget(root)
        self._update_actions()

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
        if self._busy or background and self._callbacks:
            return False
        self._busy = True
        self._busy_background = background
        self._update_actions()
        self._worker = worker = _Read(function)
        def finished(value, error):
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
                if pending:
                    pending()
            finally:
                self._callbacks -= 1
                self._update_actions()
        worker.signals.finished.connect(finished, Qt.ConnectionType.QueuedConnection)
        QThreadPool.globalInstance().start(worker)
        return True

    def _build_adoption_receipt_ui(self, layout):
        self.adoption_receipt_label = QLabel()
        self.adoption_receipt_label.setObjectName('unconfirmedAdoptionReceipt')
        self.adoption_receipt_label.setWordWrap(True)
        self.adoption_receipt_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.retry_adoption_button = QPushButton('Retry adoption receipt')
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
        note = ('Session changed: this receipt remains unresolved. Its request cannot be rebased or resubmitted in the new session.'
                if not same_session else 'Retry resends this exact reviewed request and command ID; it never selects another candidate.')
        self.adoption_receipt_label.setText('Unconfirmed ' + pending['kind'].title() + ' adoption · target ' + target +
            ' · job ' + request['job_id'] + ' · candidate ' + request['candidate_id'] +
            '\nCommand ' + request['command_id'] + '\n' + note)
        self.retry_adoption_button.setEnabled(same_session and not self._callbacks and not self._pending_adoption
                                             and (not self._busy or self._busy_background))

    def _submit_adoption_receipt(self, kind, request, acknowledged=None):
        if self._adoption_receipt is not None:
            self.message.setText('An adoption receipt is unconfirmed. Retry that exact receipt before starting another adoption.')
            return False
        self._adoption_receipt = {'kind': kind, 'request': deepcopy(request),
            'source_session': self.document['session_id'], 'acknowledged': acknowledged}
        return self._send_adoption_receipt(self._adoption_receipt)

    def _send_adoption_receipt(self, pending):
        if self._adoption_receipt is not pending:
            return False
        if self.document is None or self.document['session_id'] != pending['source_session']:
            self.message.setText('Service session changed. The original adoption receipt remains unresolved; no rebased request was submitted.')
            self._update_adoption_receipt_actions()
            return False
        request = deepcopy(pending['request'])
        kind = pending['kind']
        target = request['target_document_id' if kind == 'domain' else kind + '_document_id']
        def failed(error):
            self.message.setText('Adoption receipt unconfirmed for ' + target + ' · ' + request['job_id'] + ' · ' +
                                 request['candidate_id'] + '. Use Retry adoption receipt with the same command ID. ' + error)
        def accepted(receipt):
            if (not isinstance(receipt, dict) or receipt.get('command_id') != request['command_id']
                    or not isinstance(receipt.get('document'), dict) or receipt['document'].get('id') != target):
                failed('Response did not acknowledge this exact target and command ID.')
                return
            self._adoption_receipt = None
            if kind == 'pde':
                self._pde_adoption_request = None
            self.message.setText('Acknowledged ' + kind.title() + ' adoption · target ' + target + ' · job ' +
                                 request['job_id'] + ' · candidate ' + request['candidate_id'] + '. No solver was executed.')
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
            self.message.setText('Waiting for the current read, then retrying the original adoption receipt with its exact command ID.')
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
        self.message.setText('Select Material, choose the operation, edit free coefficients and explicit response/distribution definitions, Apply plan, then Run. Fit requires Data observations. Adoption is a separate Material command.')

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
            if not isinstance(draft['experiments'], list) or any(set(e) != {'id', 'role', 'source', 'response', 'settings', 'weight', 'scale'} for e in draft['experiments']):
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
        self.material_label.setText(f"{self._material['document_id']} · g{self._material['generation']} · input {self._material['input_revision']}" if isinstance(self._material, dict) and {'document_id', 'generation', 'input_revision'} <= set(self._material) else 'No complete Material reference selected')
        self._populate_runs(prefer_job)
        self._draw_result()
        self._update_actions()

    def _set_cell(self, table, row, col, value, editable=True):
        item = QTableWidgetItem(display(value))
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
                self._set_cell(self.experiments, row, col, value, editable=col in (0, 1, 4, 5, 6))

    def _edited(self, *_):
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
        self.experiments_panel.setVisible(mode == 'fit')
        self.operation_options.setVisible(active)
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
        def accepted(receipt):
            self.local_dirty = self.conflict = False
            self._show_document(receipt['document'], receipt.get('job', {}).get('id'))
            self.message.setText('Applied through the Numerical document owner: ' + operation)
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
        if not isinstance(self._material, dict) or 'draft' not in self._material or material_diagnostics(self._material['draft']):
            self.message.setText('Select a valid Material model before defining a measured protocol.')
            return
        def data_chosen(document):
            runs = document.get('runs', [])
            if not runs:
                self.message.setText('The selected Data document has no retained import. Import its mapping first.')
                return
            labels = [run['job_id'] + ' · input g' + str(run['input_generation']) for run in runs]
            label, ok = QInputDialog.getItem(self, 'Select Data import', 'Exact import job', labels, editable=False)
            if not ok:
                return
            run = runs[labels.index(label)]
            def inspected(result):
                if result.get('execution_status') != 'SUCCEEDED' or not result.get('responses'):
                    self.message.setText('Selected import has no successful response.')
                    return
                names = list(result['responses'])
                name, ok = QInputDialog.getItem(self, 'Select observed response', 'Imported channel', names, editable=False)
                if not ok:
                    return
                response, ok = QInputDialog.getItem(self, 'Select model response', 'No conversion is inferred', ['stress_xx','stress_yy','stress_zz','stress_xy','stress_xz','stress_yz'], editable=False)
                if not ok:
                    return
                dialog = ProtocolDialog(self._material['draft']['settings'], self)
                if dialog.exec() != QDialog.DialogCode.Accepted:
                    return
                self._experiments = self.edited_draft()['experiments']
                self._experiments.append({'id': 'E'+uuid.uuid4().hex[:12], 'role': 'fit', 'source': {'document_id': document['id'], 'job_id': run['job_id'], 'response': name, 'input_revision': run['input_revision'], 'input_sha256': run['input_sha256']}, 'response': response, 'settings': dialog.draft_settings(), 'weight': 1, 'scale': 1})
                self._populating = True
                self._populate_experiments()
                self._populating = False
                self._edited()
            self._call(lambda: self.client.document_result(document['id'], run['job_id'], selection={'metadata_only': True}), inspected)
        self._list_select('data', data_chosen)

    def change_protocol(self):
        rows = sorted({item.row() for item in self.experiments.selectedIndexes()})
        if len(rows) != 1:
            self.message.setText('Select one experiment protocol to edit.')
            return
        self._experiments = self.edited_draft()['experiments']
        row = rows[0]
        dialog = ProtocolDialog(self._experiments[row]['settings'], self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._experiments[row]['settings'] = dialog.draft_settings()
            self._populating = True
            self._populate_experiments()
            self._populating = False
            self._edited()

    def remove_experiments(self):
        rows = {item.row() for item in self.experiments.selectedIndexes()}
        self._experiments = [item for row, item in enumerate(self.edited_draft()['experiments']) if row not in rows]
        self._populating = True
        self._populate_experiments()
        self._populating = False
        self._edited()

    def selected_job(self):
        rows = sorted({item.row() for item in self.runs.selectedIndexes()})
        return self.runs.item(rows[0], 0).text() if len(rows) == 1 else None

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
            if run['job_id'] == selected:
                self.runs.selectRow(row)
        self.runs.blockSignals(False)

    def _selection_changed(self):
        self._draw_result()
        self.refresh_result()

    def refresh_document(self):
        if self._callbacks or self._pending_adoption:
            return
        if self._analysis_job and not self._busy:
            return self.refresh_analysis()
        if self._busy or not self.document:
            return
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
        job = self.selected_job()
        if self._busy or self._callbacks or self._pending_adoption or not job or job in self._result_cache or monotonic() < self._result_after.get(job, 0):
            return
        document_id = self.document['id']
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
            self._populate_runs(job)
            self._draw_result()
        self._call(read, received, relevant=lambda: self.document['id'] == document_id, background=True)

    def retry_result(self):
        job = self.selected_job()
        self._result_after.pop(job, None)
        self._result_cache.pop(job, None)
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
            if candidate['candidate_id'] == selected:
                self.candidates.selectRow(row)
        self.figure.clear()
        curves = result.get('curves', [])
        if curves:
            axes = self.figure.subplots(len(curves), 1, squeeze=False)
            for ax, curve in zip(axes[:, 0], curves):
                obs = curve.get('observations', {})
                x = obs.get('axes', [{}])[0].get('values', [])
                y, predicted = obs.get('value', []), curve.get('prediction', [])
                if len(x) == len(y):
                    ax.plot(x, y, 'o', label='observed', markersize=3)
                if isinstance(predicted, list) and len(x) == len(predicted):
                    ax.plot(x, predicted, label='actual model prediction')
                ax.set_title(f"{curve.get('role')} · {curve.get('experiment_id')} · {curve.get('execution_status')} · RMSE {curve.get('rmse', 'unknown')}", fontsize=9)
                ax.set_xlabel('time ['+obs.get('axes', [{}])[0].get('unit', '?')+']')
                ax.set_ylabel(obs.get('component', '?')+' ['+obs.get('unit', '?')+']')
                if ax.lines:
                    ax.legend(fontsize=7)
        else:
            self._draw_study_summary(result, job)
        self.canvas.draw_idle()
        self.details.setPlainText(json.dumps({'document': self.document, 'view_error': self._view_error, 'selected_status': self._statuses.get(job), 'read_error': self._result_errors.get(job), 'selected_result': result}, indent=2, ensure_ascii=False))

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
        return item.text() if item is not None else None

    def adopt_candidate(self):
        if self._adoption_receipt is not None:
            self.message.setText('An adoption receipt is unconfirmed. Retry that exact receipt before starting another adoption.')
            return False
        self._commit_editor()
        job = self.selected_job()
        candidate = self.selected_candidate()
        if self.local_dirty or self.conflict or not job or not candidate:
            self.message.setText('Apply plan edits and select one actual candidate before adopting.')
            return
        selected = next((row for row in self._result_cache.get(job, {}).get('candidates', [])
                         if row.get('candidate_id', row.get('id')) == candidate), None)
        if selected is not None and selected.get('prediction_status') == 'PREDICTED':
            self.message.setText('This candidate is a surrogate prediction. Select an actual evaluated candidate before Material adoption.')
            return False
        if self._pending_adoption or self._callbacks or self._busy and not self._busy_background:
            self.message.setText('A foreground request is still in progress; no adoption was submitted.')
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
                self.message.setText('Plan, run, candidate or edits changed; adoption cancelled. Select the intended candidate again.')
            return same
        def target_read(target):
            if not same_selection():
                return
            if target.get('id') != reference['document_id'] or target.get('session_id') != document_session:
                self.message.setText('Original Material identity/session changed. No adoption was submitted.')
                return
            if QMessageBox.question(self, 'Adopt candidate', 'Apply '+candidate+' coefficients to Material '+target['title']+' as one undoable Material edit?', QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Cancel) != QMessageBox.StandardButton.Yes:
                self.message.setText('Adoption cancelled; no Material coefficients changed.')
                return
            if not same_selection():
                return
            def adopted(receipt):
                self.message.setText('Adopted selected evaluated coefficients through the Material owner. Material Undo can restore the prior coefficients.')
            request = dict(document_id=document_id, job_id=job, candidate_id=candidate,
                material_document_id=target['id'], session_id=target['session_id'],
                expected_generation=target['generation'], command_id='C'+uuid.uuid4().hex)
            self._submit_adoption_receipt('material', request, adopted)
        def begin():
            if same_selection():
                self._call(lambda: self.client.document_read(reference['document_id']), target_read)
        if self._busy_background:
            self._pending_adoption = begin
            self.message.setText('Waiting for the current read, then confirming '+candidate+' from '+job+'.')
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
            self.identity.setText('g'+str(self.document['generation'])+(' · unapplied edits' if self.local_dirty else ''))

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
            self.timer.stop()
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
