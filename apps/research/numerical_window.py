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


class NumericalWindow(QMainWindow):
    def __init__(self, client, *, document_id=None, material_document=None, poll_interval=2000, auto_open=True):
        super().__init__()
        self.client, self.document = client, None
        self.local_dirty = self.conflict = self._busy = self._populating = False
        self._busy_background = False
        self._callbacks = 0
        self._pending_adoption = None
        self._drawn_result_job = None
        self._allow_close = False
        self._worker = None
        self._result_cache, self._result_errors, self._statuses = {}, {}, {}
        self._result_after = {}
        self._view_error = None
        self._analysis_job = None
        self._material = None
        self._experiments = []
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
        self.mode.addItems(['fit', 'doe'])
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
        edit.addLayout(opts)
        self.variables = QTableWidget(0, 7)
        self.variables.setObjectName('numericalVariables')
        self.variables.setHorizontalHeaderLabels(['Coefficient', 'Unit', 'Current', 'Lower', 'Upper', 'Free', 'Transform'])
        self.variables.itemChanged.connect(self._edited)
        edit.addWidget(self.variables)
        buttons = QHBoxLayout()
        self.add_experiment = QPushButton('Add Data observation…')
        self.edit_protocol = QPushButton('Edit selected protocol…')
        self.remove_experiment = QPushButton('Remove selected experiments')
        self.add_experiment.clicked.connect(self.choose_observation)
        self.edit_protocol.clicked.connect(self.change_protocol)
        self.remove_experiment.clicked.connect(self.remove_experiments)
        for button in (self.add_experiment, self.edit_protocol, self.remove_experiment):
            buttons.addWidget(button)
        edit.addLayout(buttons)
        self.experiments = QTableWidget(0, 8)
        self.experiments.setObjectName('numericalExperiments')
        self.experiments.setHorizontalHeaderLabels(['Experiment', 'Role (fit / holdout)', 'Data import', 'Observed response', 'Model response', 'Weight', 'Error scale', 'Explicit protocol'])
        self.experiments.itemChanged.connect(self._edited)
        edit.addWidget(self.experiments)
        note = QLabel('Fit and holdout are separate histories. DOE evaluates the selected Material protocol. This editor supports FELUPE elastic material points, serial execution, bounded coefficients and explicit time/F histories. Other backends, objectives, constraints, masks and parallel options use the existing numerical API.')
        note.setWordWrap(True)
        edit.addWidget(note)
        layout.addWidget(self.editor)
        self.runs = QTableWidget(0, 4)
        self.runs.setHorizontalHeaderLabels(['Plan job', 'State', 'Submitted input', 'Ownership'])
        self.runs.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.runs.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.runs.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.runs.itemSelectionChanged.connect(self._selection_changed)
        layout.addWidget(self.runs)
        actions = QHBoxLayout()
        self.read_button, self.adopt_button, self.analysis_button = QPushButton('Read / retry selected run'), QPushButton('Adopt selected candidate into Material'), QPushButton('Analyze DOE response…')
        self.read_button.clicked.connect(self.retry_result)
        self.adopt_button.clicked.connect(self.adopt_candidate)
        self.analysis_button.clicked.connect(self.analyze_result)
        for button in (self.read_button, self.adopt_button, self.analysis_button):
            actions.addWidget(button)
        layout.addLayout(actions)
        self.tabs = QTabWidget()
        self.candidates = QTableWidget(0, 5)
        self.candidates.setHorizontalHeaderLabels(['Candidate', 'Status', 'Coefficients', 'Fit objective', 'Failure'])
        self.candidates.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.candidates.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.candidates.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabs.addTab(self.candidates, 'Actual candidates')
        self.figure = Figure(constrained_layout=True)
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.tabs.addTab(self.canvas, 'Fit / holdout curves')
        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        self.tabs.addTab(self.details, 'Diagnostics / retained input')
        layout.addWidget(self.tabs, 1)
        self.setCentralWidget(root)
        self._update_actions()

    def _call(self, function, accepted, *, background=False, relevant=None):
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

    def open_document(self, *, document_id=None, title='Numerical study', draft=None):
        return self._call(lambda: self.client.document_open(kind='numerical', title=title, draft=draft, document_id=document_id), self._opened)

    def _opened(self, document):
        self.local_dirty = self.conflict = False
        self._result_cache.clear()
        self._show_document(document)
        self.message.setText('Select Material, edit free coefficients/bounds, add explicit Data experiments, Apply plan, then Run. Adoption is a separate Material command.')

    def _show_document(self, document, prefer_job=None):
        self.document = deepcopy(document)
        draft = document['draft']
        self._populating = True
        self._view_error = None
        try:
            if set(draft) != set(default_draft()) or draft['mode'] not in ('fit', 'doe') or draft['method'] not in ('least_squares', 'differential_evolution'):
                raise ValueError('Unsupported visible plan shape')
            if not isinstance(draft['variables'], list) or any(set(v) != {'id', 'unit', 'value', 'lower', 'upper', 'free', 'transform'} for v in draft['variables']):
                raise ValueError('Unsupported coefficient shape')
            if not isinstance(draft['experiments'], list) or any(set(e) != {'id', 'role', 'source', 'response', 'settings', 'weight', 'scale'} for e in draft['experiments']):
                raise ValueError('Unsupported experiment shape')
            self._material = deepcopy(draft['material'])
            self._experiments = deepcopy(draft['experiments'])
            self.mode.setCurrentText(draft['mode'])
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
        draft['experiments'] = deepcopy(self._experiments)
        for row, experiment in enumerate(draft['experiments']):
            for col, key in ((0, 'id'), (1, 'role'), (4, 'response'), (5, 'weight'), (6, 'scale')):
                experiment[key] = cell_value(self.experiments, row, col)
        return draft

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
            editing = self.local_dirty or any(table.state() == QAbstractItemView.State.EditingState for table in (self.variables, self.experiments))
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
            values = [candidate['candidate_id'], candidate.get('execution_status'), candidate.get('values'), candidate.get('objective'), candidate.get('failure_reason')]
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
            ax = self.figure.add_subplot(111)
            ax.text(.5,.5,'No retained fit / holdout curves selected', ha='center', va='center', transform=ax.transAxes)
            ax.set_axis_off()
        self.canvas.draw_idle()
        self.details.setPlainText(json.dumps({'document': self.document, 'view_error': self._view_error, 'selected_status': self._statuses.get(job), 'read_error': self._result_errors.get(job), 'selected_result': result}, indent=2, ensure_ascii=False))

    def selected_candidate(self):
        rows = sorted({item.row() for item in self.candidates.selectedIndexes()})
        item = self.candidates.item(rows[0], 0) if len(rows) == 1 else None
        return item.text() if item is not None else None

    def adopt_candidate(self):
        self._commit_editor()
        job = self.selected_job()
        candidate = self.selected_candidate()
        if self.local_dirty or self.conflict or not job or not candidate:
            self.message.setText('Apply plan edits and select one actual candidate before adopting.')
            return
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
            if QMessageBox.question(self, 'Adopt candidate', 'Apply '+candidate+' coefficients to Material '+target['title']+' as one undoable Material edit?', QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Cancel) != QMessageBox.StandardButton.Yes:
                self.message.setText('Adoption cancelled; no Material coefficients changed.')
                return
            if not same_selection():
                return
            def adopted(receipt):
                self.message.setText('Adopted selected evaluated coefficients through the Material owner. Material Undo can restore the prior coefficients.')
            self._call(lambda: self.client.numerical_adopt(document_id, job, candidate, material_document_id=target['id'], session_id=target['session_id'], expected_generation=target['generation'], command_id='C'+uuid.uuid4().hex), adopted)
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
        if result.get('kind') != 'doe':
            self.message.setText('Select a retained DOE result for candidate analysis.')
            return
        names = sorted({name for row in result.get('candidates', []) for name in row.get('responses', {})})
        if not names:
            self.message.setText('No actual DOE responses are available.')
            return
        name, ok = QInputDialog.getItem(self, 'Analyze actual DOE', 'Response', names, editable=False)
        if not ok:
            return
        reduction, ok = QInputDialog.getItem(self, 'Explicit reduction', 'Scalar statistic', ['max','min','mean','final','abs_max'], editable=False)
        if not ok:
            return
        response = next(row['responses'][name] for row in result['candidates'] if name in row.get('responses', {}))
        declaration = {'response': name, 'unit': response['unit'], 'reduction': reduction, **{key: response[key] for key in ('component','location','measure','frame') if key in response}}
        def analyzed(job):
            self._analysis_job = job['id']
            self.message.setText('Candidate analysis submitted: '+job['id']+'. Read its actual result when the job finishes.')
            QTimer.singleShot(1000, self.refresh_analysis)
        self._call(lambda: self.client.submit('analyze', {'table': result, 'responses': [declaration]}), analyzed)

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
                                     not self._callbacks and self._pending_adoption is None and
                                     (not self._busy or self._busy_background) and bool(self.selected_job()))
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
    window = NumericalWindow(Client(args.service), document_id=args.document_id)
    window.show()
    return app.exec()


if __name__ == '__main__':
    raise SystemExit(main())
