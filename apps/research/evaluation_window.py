"""Independent Qt editor for the service-owned ordered EvaluationDefinition."""
from copy import deepcopy
import json
import uuid

from PySide6.QtCore import QThreadPool, QTimer, Qt
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QCheckBox, QHBoxLayout, QInputDialog,
    QLabel, QLineEdit, QListWidget, QMainWindow, QMessageBox, QPushButton, QSplitter,
    QTableWidget, QTableWidgetItem, QTabWidget, QToolBar, QVBoxLayout, QWidget, QComboBox)

from caelab.evaluation_definition import default_draft, diagnostics, document_reference, definition_hash
from caelab.storage import canonical_hash
from .data_window import _Read, display, integer_or_raw, number_or_raw, TERMINAL

ROLE = Qt.ItemDataRole.UserRole
_COLUMNS = {
    'stages': [('id', 'Stage ID'), ('name', 'Name'), ('source', 'Exact saved source')],
    'transfers': [('id', 'Transfer ID'), ('from_stage', 'From stage'), ('output', 'Output port'),
                  ('to_stage', 'To stage'), ('input', 'Input port'), ('mapping', 'Mapping'), ('lag', 'Lag')],
    'bindings': [('id', 'Research variable'), ('stage', 'Stage'), ('input_id', 'Declared input ID'), ('unit', 'Unit')],
    'responses': [('id', 'Exposed response'), ('stage', 'Stage'), ('response', 'Actual / declared response'), ('unit', 'Unit')],
    'checks': [('stage', 'Stage'), ('response', 'Response'), ('unit', 'Physical unit'),
               ('absolute', 'Absolute tolerance'), ('relative', 'Relative tolerance'), ('scale', 'Physical scale')],
}


def item_value(item, numeric=False, integer=False):
    if item is None: return ''
    original = item.data(ROLE)
    if item.text() == display(original): return deepcopy(original)
    return integer_or_raw(item.text()) if integer else number_or_raw(item.text()) if numeric else item.text()


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
        self._selected_job = None
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
        self.setWindowTitle('Evaluation Definition')
        toolbar = QToolBar('Evaluation commands', self)
        toolbar.setMovable(False)
        self.addToolBar(toolbar)
        self.new_button = QPushButton('New')
        self.open_button = QPushButton('Open saved definition')
        self.apply_button = QPushButton('Apply definition')
        self.run_button = QPushButton('Run once')
        self.save_button = QPushButton('Save')
        self.undo_button = QPushButton('Undo')
        self.redo_button = QPushButton('Redo')
        self.inspect_button = QPushButton('Inspect declared inputs / ports')
        self.plan_button = QPushButton('Numerical Plan')
        self.runner_button = QPushButton('Runner')
        for button in (self.new_button, self.open_button, self.apply_button, self.run_button, self.save_button,
                       self.undo_button, self.redo_button, self.inspect_button, self.plan_button, self.runner_button): toolbar.addWidget(button)
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
        self.identity = QLabel('Connect to an existing local service')
        self.identity.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.message = QLabel('Opening an EvaluationDefinition never starts a stage.')
        self.message.setWordWrap(True)
        self.support = QLabel()
        self.support.setWordWrap(True)
        outer.addWidget(self.identity)
        outer.addWidget(self.message)
        conflict = QHBoxLayout()
        self.reload_button, self.copy_button = QPushButton('Reload shared version'), QPushButton('Keep edits as new definition')
        self.reload_button.clicked.connect(self.reload_remote)
        self.copy_button.clicked.connect(lambda: self.open_document(draft=self.edited_draft(), title='Copied EvaluationDefinition'))
        conflict.addWidget(self.reload_button); conflict.addWidget(self.copy_button); conflict.addStretch()
        outer.addLayout(conflict)
        vertical = QSplitter(Qt.Orientation.Vertical)
        top = QSplitter(Qt.Orientation.Horizontal)
        left = QWidget(); layout = QVBoxLayout(left)
        layout.addWidget(QLabel('Ordered domain stages'))
        self.stage_list = QListWidget()
        self.stage_list.setObjectName('evaluationStageList')
        self.stage_list.currentRowChanged.connect(self._stage_selected)
        layout.addWidget(self.stage_list, 1)
        for label, handler in [('Add saved source', self.add_stage), ('Replace selected source', self.replace_source),
                               ('Move up', lambda: self.move_stage(-1)), ('Move down', lambda: self.move_stage(1)),
                               ('Remove stage', self.remove_stage), ('Open original source', self.open_source)]:
            button = QPushButton(label); button.clicked.connect(handler); layout.addWidget(button)
        self.stage_editor = left
        top.addWidget(left)
        self.tabs = QTabWidget()
        self.tables = {}
        for key, title in [('stages', 'Stages'), ('transfers', 'Transfers'), ('bindings', 'Variables'), ('responses', 'Responses')]:
            page = QWidget(); page_layout = QVBoxLayout(page)
            note = {'stages': 'Source revisions are exact and read-only here. Open the source owner to edit physical inputs.',
                    'transfers': 'Choose real advertised ports. exact_same_mesh preserves declared unit, position, frame and time. Lag 1 requires explicit iteration.',
                    'bindings': 'Research variables bind only to advertised scalar input IDs; native settings paths are not editable bindings.',
                    'responses': 'Expose an advertised channel or explicitly declare a stage response name and unit. No values are generated by this editor.'}[key]
            text = QLabel(note); text.setWordWrap(True); page_layout.addWidget(text)
            table = self._table(_COLUMNS[key], editable=True)
            table.setObjectName('evaluation' + title)
            table.itemChanged.connect(self._edited)
            self.tables[key] = table
            page_layout.addWidget(table, 1)
            if key != 'stages':
                row = QHBoxLayout(); add = QPushButton('Add ' + title.lower().rstrip('s')); remove = QPushButton('Remove selected rows')
                add.clicked.connect({'transfers': self.add_transfer, 'bindings': self.add_binding, 'responses': self.add_response}[key])
                remove.clicked.connect(lambda checked=False, name=key: self.remove_rows(name))
                row.addWidget(add); row.addWidget(remove); row.addStretch(); page_layout.addLayout(row)
            self.tabs.addTab(page, title)
        iteration = QWidget(); layout = QVBoxLayout(iteration)
        row = QHBoxLayout()
        self.iteration_enabled = QCheckBox('Enable explicitly lagged physical iteration')
        self.iteration_maximum = QLineEdit()
        self.iteration_maximum.setMaximumWidth(100)
        self.iteration_enabled.toggled.connect(self._edited)
        self.iteration_maximum.textEdited.connect(self._edited)
        row.addWidget(self.iteration_enabled); row.addWidget(QLabel('Maximum iterations')); row.addWidget(self.iteration_maximum); row.addStretch()
        layout.addLayout(row)
        note = QLabel('Residual uses successive actual stage values, L∞ norm and absolute + relative × max(response norm, physical scale). Declare tolerance units explicitly; the first iteration has no previous result.')
        note.setWordWrap(True); layout.addWidget(note)
        self.tables['checks'] = self._table(_COLUMNS['checks'], editable=True)
        self.tables['checks'].setObjectName('evaluationConvergenceChecks')
        self.tables['checks'].itemChanged.connect(self._edited)
        layout.addWidget(self.tables['checks'], 1)
        row = QHBoxLayout(); add = QPushButton('Add convergence check'); remove = QPushButton('Remove selected checks')
        add.clicked.connect(self.add_check); remove.clicked.connect(lambda: self.remove_rows('checks'))
        row.addWidget(add); row.addWidget(remove); row.addStretch(); layout.addLayout(row)
        self.reuse_label = QLabel('No retained prefix selected for reuse')
        self.reuse_label.setWordWrap(True); layout.addWidget(self.reuse_label)
        clear_reuse = QPushButton('Clear prepared reuse'); clear_reuse.clicked.connect(self.clear_reuse); layout.addWidget(clear_reuse)
        self.tabs.addTab(iteration, 'Iteration / reuse')
        top.addWidget(self.tabs); top.setSizes([245, 1180]); vertical.addWidget(top)
        bottom = QWidget(); layout = QVBoxLayout(bottom)
        row = QHBoxLayout(); self.runs = QComboBox(); self.runs.setMinimumWidth(430)
        self.runs.currentIndexChanged.connect(self._run_selected)
        self.refresh_button = QPushButton('Refresh actual progress')
        self.retry_button = QPushButton('Prepare Retry from saved successful prefix')
        self.result_button = QPushButton('Open selected stage result')
        self.refresh_button.clicked.connect(self.refresh_progress)
        self.retry_button.clicked.connect(self.prepare_retry)
        self.result_button.clicked.connect(self.open_stage_result)
        row.addWidget(QLabel('Retained / active run')); row.addWidget(self.runs, 1)
        for button in (self.refresh_button, self.retry_button, self.result_button): row.addWidget(button)
        layout.addLayout(row)
        result_tabs = QTabWidget()
        self.attempts = self._table([('iteration', 'Iteration'), ('stage_id', 'Stage'), ('attempt_id', 'Attempt'), ('state', 'Actual state'), ('backend', 'Backend'), ('reused_from', 'Retained reuse')])
        self.attempts.setObjectName('evaluationAttempts')
        self.attempts.itemSelectionChanged.connect(self._attempt_selected)
        result_tabs.addTab(self.attempts, 'Actual stage attempts')
        self.residuals = self._table([('iteration', 'Iteration'), ('stage', 'Stage'), ('response', 'Response'), ('unit', 'Unit'), ('observed', 'L∞ difference'), ('limit', 'Actual limit'), ('passed', 'Passed')])
        result_tabs.addTab(self.residuals, 'Iteration residuals')
        self.channels = self._table([('name', 'Channel'), ('kind', 'Kind'), ('unit', 'Unit'), ('component', 'Component'), ('location', 'Position'), ('value', 'Actual value / retained array'), ('state', 'Stage status')])
        result_tabs.addTab(self.channels, 'Selected stage responses')
        layout.addWidget(result_tabs, 1)
        vertical.addWidget(bottom); vertical.setSizes([555, 270]); outer.addWidget(vertical, 1)
        outer.addWidget(self.support)
        self.setCentralWidget(root)
        self._update_actions()

    @staticmethod
    def _table(columns, editable=False):
        table = QTableWidget(0, len(columns))
        table.setHorizontalHeaderLabels([label for _, label in columns])
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setAlternatingRowColors(True)
        table.horizontalHeader().setStretchLastSection(True)
        if not editable: table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        return table

    def _put_rows(self, table, columns, rows, *, key=None):
        table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            for column, (name, _) in enumerate(columns):
                value = row.get(name, '')
                text = (f"{value.get('kind', '?')} · {value.get('document_id', '?')} · {value.get('saved_revision', '?')} · {value.get('input_sha256', '')[:12]}"
                        if name == 'source' and isinstance(value, dict) else display(value))
                item = QTableWidgetItem(text); item.setData(ROLE, deepcopy(value))
                editable = key == 'stages' and name == 'name' or key == 'transfers' and name == 'lag' or key == 'bindings' and name == 'id' or key == 'responses' and name in ('id', 'response', 'unit') or key == 'checks' and name in ('absolute', 'relative', 'scale')
                if not editable: item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                table.setItem(row_index, column, item)
        table.resizeColumnsToContents()

    def _show_document(self, document, *, preserve_draft=None, prefer_job=None):
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
        for run in document.get('runs', []):
            self.runs.addItem(run['job_id'] + ' · ' + run.get('retained_state', 'active / not yet saved') + (' · current input' if run.get('is_current_input') else ' · prior input'), run['job_id'])
        index = self.runs.findData(self._selected_job)
        if index < 0 and self.runs.count(): index = self.runs.count() - 1
        self.runs.setCurrentIndex(index)
        self._selected_job = self.runs.currentData()
        reuse = self._draft.get('reuse')
        self.reuse_label.setText('Prepared retained prefix: ' + display(reuse) if reuse else 'No retained prefix selected for reuse')
        self.identity.setText(f"{document.get('title', 'Evaluation')} · {document['id']} · generation {document['generation']} · saved {document.get('saved_revision') or 'unsaved'}")
        self._populating = False
        self._update_actions()

    def _refresh_stage_list(self):
        selected = self.stage_list.currentRow()
        self.stage_list.clear()
        for row in self._draft.get('stages', []): self.stage_list.addItem(row.get('name', '?') + ' · ' + row.get('id', '?'))
        if self.stage_list.count(): self.stage_list.setCurrentRow(max(0, min(selected, self.stage_list.count() - 1)))

    def edited_draft(self):
        focus = QApplication.focusWidget()
        if focus: focus.clearFocus()
        result = deepcopy(self._draft)
        if self._view_error: return result
        for key, table in self.tables.items():
            rows = result['iteration']['checks'] if key == 'checks' else result[key]
            for index, row in enumerate(rows):
                for column, (name, _) in enumerate(_COLUMNS[key]):
                    if name == 'source': continue
                    row[name] = item_value(table.item(index, column), numeric=key == 'checks' and name in ('absolute', 'relative', 'scale'), integer=key == 'transfers' and name == 'lag')
        result['iteration']['enabled'] = self.iteration_enabled.isChecked()
        original = self._draft['iteration'].get('maximum')
        text = self.iteration_maximum.text()
        result['iteration']['maximum'] = original if text == display(original) else integer_or_raw(text)
        return result

    def _edited(self, *args):
        if self._populating or not self.document: return
        self.local_dirty = canonical_hash(self.edited_draft()) != canonical_hash(self.document['draft'])
        self._update_actions()

    def _replace_draft(self, draft):
        self._show_document(self.document, preserve_draft=draft)
        self._edited()

    def _update_actions(self):
        exists = self.document is not None
        usable = exists and not self._busy and not self.conflict
        errors = diagnostics(self.edited_draft()) if exists else []
        support = errors + self._inspection.get('diagnostics', [])
        self.support.setText(self._view_error or '\n'.join(row.get('message', '') for row in support) or 'Declared graph ready. Runtime availability and numerical checks are evaluated separately.')
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
        self.reload_button.setVisible(self.conflict); self.copy_button.setVisible(self.conflict)

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

    def open_document(self, *, document_id=None, draft=None, title='Ordered EvaluationDefinition'):
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
            self.message.setText('Apply edited definition before ' + operation); return False
        document = deepcopy(self.document)
        key = (document['id'], document['session_id'], document['generation'])
        def accepted(receipt):
            self.local_dirty = self.conflict = False
            job = receipt.get('job')
            self._show_document(receipt['document'], prefer_job=job.get('id') if job else None)
            self.message.setText('Applied through the Evaluation owner: ' + operation)
            if after: after()
            elif job: QTimer.singleShot(0, self.refresh_progress)
            elif operation in ('evaluation.update', 'document.undo', 'document.redo'): QTimer.singleShot(0, self.inspect_inputs)
        return self._call(lambda: self.client.document_command(document['id'], operation, arguments or {},
            session_id=document['session_id'], expected_generation=document['generation'], command_id='C' + uuid.uuid4().hex), accepted,
            relevant=lambda: self.document and (self.document['id'], self.document['session_id'], self.document['generation']) == key)

    def apply_inputs(self, *, after=None):
        return self.command('evaluation.update', {'draft': self.edited_draft()}, after=after)

    def save_document(self, *, after=None):
        if self.local_dirty: return self.apply_inputs(after=lambda: self.command('document.save', after=after))
        return self.command('document.save', after=after)

    def run_once(self):
        return self.command('evaluation.run')

    def refresh_document(self):
        if not self.document or self._busy: return
        identity = (self.document['id'], self.document['session_id'])
        def accepted(remote):
            changed = (remote['session_id'], remote['generation']) != (self.document['session_id'], self.document['generation'])
            if changed and self.local_dirty:
                self.conflict = True; self.message.setText('Shared definition changed during editing. Reload or preserve edits as a new definition.')
            elif not self.local_dirty and not self.conflict: self._show_document(remote)
            if self._selected_job: QTimer.singleShot(0, self.refresh_progress)
        return self._call(lambda: self.client.document_read(identity[0]), accepted, background=True,
            relevant=lambda: self.document and (self.document['id'], self.document['session_id']) == identity)

    def inspect_inputs(self, *, after=None):
        if not self.document: return False
        if self.local_dirty: return self.apply_inputs(after=lambda: self.inspect_inputs(after=after))
        identity = (self.document['id'], self.document['session_id'], self.document['generation'])
        def accepted(payload):
            self._inspection = deepcopy(payload)
            self._catalog_sources = {row['id']: canonical_hash(row['source']) for row in self.document['draft'].get('stages', [])}
            if after: after()
        return self._call(lambda: self.client.evaluation_inspect(identity[0]), accepted,
            relevant=lambda: self.document and (self.document['id'], self.document['session_id'], self.document['generation']) == identity)

    def _source_picker(self, selected):
        if not self.document: return False
        identity = (self.document['id'], self.document['session_id'])
        relevant = lambda: self.document and (self.document['id'], self.document['session_id']) == identity
        def listed(payload):
            sources = [row for row in payload['documents'] if row.get('kind') in ('material', 'pde', 'simulation') and row.get('saved_revision') and not row.get('dirty')]
            if not sources: self.message.setText('Save a clean Material, PDE or Simulation document before adding a stage.'); return
            labels = [row.get('title', row['id']) + ' · ' + row['id'] + ' · ' + row['saved_revision'] for row in sources]
            choice, ok = QInputDialog.getItem(self, 'Saved domain source', 'Exact saved input', labels, editable=False)
            if ok:
                source = sources[labels.index(choice)]
                self._call(lambda: self.client.document_read(source['id']), lambda document: selected(document_reference(document)), relevant=relevant)
        return self._call(self.client.documents, listed, relevant=relevant)

    def add_stage(self):
        if self._foreground_busy: return
        def selected(reference):
            draft = self.edited_draft()
            draft['stages'].append({'id': 'S' + uuid.uuid4().hex[:12], 'name': reference['kind'].title() + ' stage', 'source': reference})
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

    def _catalog(self, stage_id):
        stage = next((row for row in self.edited_draft()['stages'] if row['id'] == stage_id), None)
        if not stage or self._catalog_sources.get(stage_id) != canonical_hash(stage['source']): return None
        return next((row for row in self._inspection.get('stages', []) if row['id'] == stage_id), None)

    def _choose_stage(self, label):
        stages = self.edited_draft()['stages']
        choices = [row['name'] + ' · ' + row['id'] for row in stages]
        if not choices: self.message.setText('Add a saved domain stage first.'); return None
        selected, ok = QInputDialog.getItem(self, label, 'Stage', choices, editable=False)
        return stages[choices.index(selected)]['id'] if ok else None

    def _ensure_catalog(self, continuation, checked):
        if all(self._catalog(row['id']) for row in self.edited_draft()['stages']): return True
        if not checked: self.inspect_inputs(after=continuation)
        else: self.message.setText('The selected source has no available declared catalog. Review source diagnostics and Inspect again.')
        return False

    def add_transfer(self, checked=False):
        if not self._ensure_catalog(lambda: self.add_transfer(True), checked): return
        from_stage = self._choose_stage('Transfer producer')
        if not from_stage: return
        outputs = self._catalog(from_stage).get('ports', {}).get('outputs', {})
        if not outputs: self.message.setText('This source advertises no transferable output port.'); return
        output, ok = QInputDialog.getItem(self, 'Actual output port', 'Output', list(outputs), editable=False)
        if not ok: return
        to_stage = self._choose_stage('Transfer consumer')
        if not to_stage: return
        inputs = self._catalog(to_stage).get('ports', {}).get('inputs', {})
        inputs = {name: spec for name, spec in inputs.items() if spec.get('transfer') == 'exact_same_mesh'}
        if not inputs: self.message.setText('This source advertises no exact_same_mesh input port.'); return
        port, ok = QInputDialog.getItem(self, 'Actual input port', 'Input', list(inputs), editable=False)
        if not ok: return
        lag, ok = QInputDialog.getItem(self, 'Transfer timing', 'Lag', ['0 · current iteration', '1 · previous iteration / feedback'], editable=False)
        if not ok: return
        draft = self.edited_draft(); draft['transfers'].append({'id': 'F' + uuid.uuid4().hex[:12], 'from_stage': from_stage,
            'output': output, 'to_stage': to_stage, 'input': port, 'mapping': 'exact_same_mesh', 'lag': int(lag[0])})
        self._replace_draft(draft)

    def add_binding(self, checked=False):
        if not self._ensure_catalog(lambda: self.add_binding(True), checked): return
        stage_id = self._choose_stage('Numerical input binding')
        if not stage_id: return
        inputs = self._catalog(stage_id).get('inputs', [])
        if not inputs: self.message.setText('The selected adapter advertises no scalar numerical input binding.'); return
        labels = [row.get('label', row['id']) + ' · ' + row['id'] + ' [' + row['unit'] + ']' for row in inputs]
        selected, ok = QInputDialog.getItem(self, 'Advertised scalar input', 'Input', labels, editable=False)
        if not ok: return
        descriptor = inputs[labels.index(selected)]
        identifier, ok = QInputDialog.getText(self, 'Research variable', 'Variable ID', text=descriptor['id'])
        if not ok: return
        draft = self.edited_draft(); draft['bindings'].append({'id': identifier, 'stage': stage_id, 'input_id': descriptor['id'], 'unit': descriptor['unit']})
        self._replace_draft(draft)

    def _response_choice(self, title):
        stage_id = self._choose_stage(title)
        if not stage_id: return None
        catalog = self._catalog(stage_id) or {}
        outputs = catalog.get('ports', {}).get('outputs', {})
        choices = list(outputs) + ['Declare explicit response name / unit…']
        response, ok = QInputDialog.getItem(self, title, 'Response', choices, editable=False)
        if not ok: return None
        if response in outputs: return stage_id, response, outputs[response]['unit']
        response, ok = QInputDialog.getText(self, title, 'Exact stage response name')
        if not ok: return None
        unit, ok = QInputDialog.getText(self, title, 'Declared physical unit')
        return (stage_id, response, unit) if ok else None

    def add_response(self):
        selected = self._response_choice('Expose stage response')
        if not selected: return
        stage_id, response, unit = selected
        identifier, ok = QInputDialog.getText(self, 'Exposed response', 'Research response ID', text=response)
        if ok:
            draft = self.edited_draft(); draft['responses'].append({'id': identifier, 'stage': stage_id, 'response': response, 'unit': unit}); self._replace_draft(draft)

    def add_check(self):
        selected = self._response_choice('Physical iteration residual')
        if not selected: return
        stage_id, response, unit = selected
        draft = self.edited_draft(); draft['iteration']['checks'].append({'stage': stage_id, 'response': response,
            'unit': unit, 'absolute': '', 'relative': '', 'scale': ''}); self._replace_draft(draft)
        self.message.setText('Enter explicit absolute / relative tolerances and physical scale before Run.')

    def remove_rows(self, key):
        draft = self.edited_draft(); rows = draft['iteration']['checks'] if key == 'checks' else draft[key]
        for index in sorted({cell.row() for cell in self.tables[key].selectedIndexes()}, reverse=True): rows.pop(index)
        self._replace_draft(draft)

    def clear_reuse(self):
        draft = self.edited_draft(); draft['reuse'] = None; self._replace_draft(draft)

    def _run_selected(self, *args):
        if self._populating: return
        self._selected_job = self.runs.currentData(); self._selected_attempt = None; self._progress = {}
        self.attempts.setRowCount(0); self.residuals.setRowCount(0); self.channels.setRowCount(0)
        self._update_actions()
        QTimer.singleShot(0, self.refresh_progress)

    def refresh_progress(self):
        if not self.document or not self._selected_job: return
        identity = (self.document['id'], self.document['session_id'], self._selected_job)
        def accepted(payload):
            progress = payload.get('progress', payload)
            if not isinstance(progress, dict):
                self.message.setText('No stage progress receipt is available yet. Refresh to read the same job.'); return
            self._progress = deepcopy(progress)
            self._populating = True
            self._put_rows(self.attempts, [('iteration', ''), ('stage_id', ''), ('attempt_id', ''), ('state', ''), ('backend', ''), ('reused_from', '')], progress.get('stages', []))
            residuals = [row for iteration in progress.get('iterations', []) for row in iteration.get('checks', [])]
            self._put_rows(self.residuals, [('iteration', ''), ('stage', ''), ('response', ''), ('unit', ''), ('observed', ''), ('limit', ''), ('passed', '')], residuals)
            self._populating = False
            if self._selected_attempt:
                match = next((i for i, row in enumerate(progress.get('stages', [])) if row.get('attempt_id') == self._selected_attempt), None)
                if match is not None: self.attempts.selectRow(match)
            self.message.setText('Actual progress: ' + progress.get('phase', progress.get('execution_status', '?')) + ' · ' + display(progress.get('diagnostics', {})))
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
            self.message.setText('Save the completed run before preparing an exact retained-prefix retry.'); return
        draft = self.edited_draft()
        if definition_hash(draft) != definition_hash(run['draft']):
            self.message.setText('Retry requires the unchanged submitted definition. Reopen or Undo changed inputs first.'); return
        if draft['iteration']['enabled']:
            self.message.setText('Iteration restarts from its declared initial state; partial loop-state reuse is unsupported.'); return
        successful = []
        for stage in draft['stages']:
            attempts = [row for row in self._progress.get('stages', []) if row.get('stage_id') == stage['id']]
            if not attempts or attempts[-1].get('state') != 'SUCCEEDED': break
            successful.append(stage['id'])
        count, ok = QInputDialog.getInt(self, 'Prepare explicit retry', 'Number of ordered successful stages to reuse', len(successful), 0, len(successful))
        if not ok: return
        identity = (self.document['id'], self.document['session_id'], job_id, canonical_hash(draft))
        def accepted(reference):
            current = self.edited_draft(); current['reuse'] = {'source': reference, 'stages': successful[:count]}; self._replace_draft(current)
            self.message.setText('Exact retained reuse prepared. Apply the definition, then explicitly Run once. No evaluation started.')
        return self._call(lambda: self.client.document_result_reference(identity[0], job_id), accepted,
            relevant=lambda: self.document and (self.document['id'], self.document['session_id'], self._selected_job, canonical_hash(self.edited_draft())) == identity)

    def open_runner(self):
        if self.runner_open and self._selected_job: self.runner_open(self._selected_job)

    def open_stage_result(self):
        if self.result_open and self.document and self._selected_job and self._selected_attempt:
            identity = (self.document['id'], self._selected_job, self._selected_attempt)
            return self._call(lambda: self.result_open(*identity),
                lambda result: self.message.setText('Opened this retained stage field in Post.'),
                relevant=lambda: self.document and (self.document['id'], self._selected_job, self._selected_attempt) == identity)

    def open_plan(self):
        if self.plan_open and self.document and not self.local_dirty:
            self.plan_open(self.document['id'], self.document['session_id'], self.document['generation'], 'C' + uuid.uuid4().hex)

    def open_source(self):
        index = self.stage_list.currentRow()
        if self.source_open and index >= 0: self.source_open(deepcopy(self.edited_draft()['stages'][index]['source']))

    def reload_remote(self):
        if self.document and QMessageBox.question(self, 'Reload definition', 'Discard unapplied edits and reload the shared definition?', QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel) == QMessageBox.StandardButton.Yes:
            self.open_document(document_id=self.document['id'])

    def _leave(self, continuation):
        if not self.document or not self.local_dirty and not self.document.get('dirty'): continuation(); return
        box = QMessageBox(self); box.setWindowTitle('Edited EvaluationDefinition'); box.setText('Save the definition before leaving? Closing does not cancel its jobs.')
        save = box.addButton('Save', QMessageBox.ButtonRole.AcceptRole)
        keep = box.addButton('Keep service draft', QMessageBox.ButtonRole.DestructiveRole)
        box.addButton(QMessageBox.StandardButton.Cancel); box.exec()
        if box.clickedButton() == save: self.save_document(after=continuation)
        elif box.clickedButton() == keep:
            if self.local_dirty: self.apply_inputs(after=continuation)
            else: continuation()

    def choose_document(self):
        def choose():
            def listed(payload):
                documents = [row for row in payload['documents'] if row.get('kind') == 'evaluation']
                labels = [row.get('title', row['id']) + ' · ' + row['id'] for row in documents]
                if not labels: self.message.setText('No EvaluationDefinitions are available.'); return
                selected, ok = QInputDialog.getItem(self, 'Open EvaluationDefinition', 'Document', labels, editable=False)
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
