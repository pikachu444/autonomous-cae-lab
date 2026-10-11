"""Typed editor for actual Numerical request Plans, sharing the existing owner/UI.

The request is edited and saved independently of execution. Numeric libraries
and registered evaluators remain behind the shared service's numerical.run.
"""
from copy import deepcopy
import json
import math
import uuid

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout,
    QInputDialog, QLabel, QLineEdit, QPushButton, QPlainTextEdit, QSplitter,
    QStyledItemDelegate, QTableWidget, QTabWidget, QToolBar, QTreeWidget,
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


class RequestPlanWindow(NumericalWindow):
    """Reuse NumericalWindow's service commands, retained jobs, save and close flow."""
    def __init__(self, client, document_id=None, poll_interval=2000, auto_open=True):
        self._request_buffer = None
        self._runner_windows = []
        self._candidate_result_windows = []
        self._operation_inputs = {}
        self._shown_operation = None
        self._source_metadata = {}
        self._queued_result_retry = None
        self._candidate_table_key = None
        self._candidate_selection_serial = 0
        self._pde_adoption_request = None
        super().__init__(client, document_id=document_id, poll_interval=poll_interval, auto_open=auto_open)

    def _build_ui(self):
        self.resize(1440, 940)
        bar = QToolBar('Numerical request Plan', self)
        self.addToolBar(bar)
        self.new_action = QAction('New request Plan', self, shortcut=QKeySequence.New)
        self.open_action = QAction('Open request Plan…', self, shortcut=QKeySequence.Open)
        self.save_action = QAction('Save', self, shortcut=QKeySequence.Save)
        self.undo_action = QAction('Undo request edit', self, shortcut=QKeySequence.Undo)
        self.redo_action = QAction('Redo request edit', self, shortcut=QKeySequence.Redo)
        for action, callback in ((self.new_action, self.new_document), (self.open_action, self.choose_document),
            (self.save_action, self.save_document), (self.undo_action, lambda: self.command('document.undo')),
            (self.redo_action, lambda: self.command('document.redo'))):
            bar.addAction(action)
            action.triggered.connect(callback)
        self.apply_button, self.run_button = QPushButton('Apply request'), QPushButton('Run explicit request')
        self.apply_button.clicked.connect(self.apply_inputs)
        self.run_button.clicked.connect(lambda: self.command('numerical.run'))
        bar.addWidget(self.apply_button)
        bar.addWidget(self.run_button)
        self.identity = QLabel()
        bar.addWidget(self.identity)
        root = QWidget()
        outer = QVBoxLayout(root)
        self.message = QLabel('Edit the proposed request, Apply, then explicitly Run. Opening or saving never executes it.')
        self.message.setWordWrap(True)
        outer.addWidget(self.message)
        conflicts = QHBoxLayout()
        self.reload_button, self.copy_button = QPushButton('Reload service version'), QPushButton('Keep edits as new request Plan')
        self.reload_button.clicked.connect(self.reload_remote)
        self.copy_button.clicked.connect(lambda: self.open_document(draft=self.edited_draft(), title=self.document['title'] + ' (copy)'))
        conflicts.addWidget(self.reload_button)
        conflicts.addWidget(self.copy_button)
        outer.addLayout(conflicts)
        split = QSplitter(Qt.Orientation.Horizontal)
        outer.addWidget(split, 1)
        self.editor = QWidget()
        inputs_layout = QVBoxLayout(self.editor)
        form = QFormLayout()
        self.purpose, self.backend, self.evaluations = QLineEdit(), QLineEdit(), QLineEdit()
        self.operation = QComboBox()
        for name in ('evaluate', 'fit', 'doe', 'optimize', 'uq', 'epsilon', 'sample_sensitivity', 'analyze', 'surrogate', 'sensitivity', 'batch_export', 'batch_import'):
            self.operation.addItem(name, name)
        form.addRow('Research purpose', self.purpose)
        form.addRow('Existing operation', self.operation)
        form.addRow('Registered backend (when required)', self.backend)
        form.addRow('Evaluation budget', self.evaluations)
        inputs_layout.addLayout(form)
        self.variables_button = QPushButton('Use declared model variables…')
        self.variables_button.setObjectName('useDeclaredModelVariables')
        self.variables_button.clicked.connect(self.choose_model_variables)
        inputs_layout.addWidget(self.variables_button)
        self.model_response_button = QPushButton('Use retained model response…')
        self.model_response_button.setObjectName('useRetainedModelResponse')
        self.model_response_button.clicked.connect(self.choose_model_response)
        inputs_layout.addWidget(self.model_response_button)
        self.observation_button = QPushButton('Attach saved fit / holdout observation…')
        self.observation_button.setObjectName('attachRetainedObservation')
        self.observation_button.clicked.connect(self.choose_fit_observation)
        inputs_layout.addWidget(self.observation_button)
        self.backend.textEdited.connect(self._backend_edited)
        for field in (self.purpose, self.evaluations):
            field.textEdited.connect(self._edited)
        self.operation.currentIndexChanged.connect(self._edited)
        self.operation.currentIndexChanged.connect(self._operation_changed)
        retained = QHBoxLayout()
        self.retained_role = QComboBox()
        self.pin_button = QPushButton('Select exact retained result…')
        self.pin_button.clicked.connect(self.choose_retained_result)
        self.response_button = QPushButton('Add declared response / reduction…')
        self.response_button.clicked.connect(self.choose_response_definition)
        for widget in (self.retained_role, self.pin_button, self.response_button):
            retained.addWidget(widget)
        inputs_layout.addLayout(retained)
        self.pinned_sources = readonly_table(['Role', 'Original document / job', 'Input revision', 'Exact result hash'])
        self.pinned_sources.setMaximumHeight(110)
        inputs_layout.addWidget(self.pinned_sources)
        self.declarations = readonly_table(['Physical response', 'Unit', 'Reduction', 'Component / location'])
        self.declarations.setMaximumHeight(105)
        inputs_layout.addWidget(self.declarations)
        self.operation_note = QLabel()
        self.operation_note.setWordWrap(True)
        inputs_layout.addWidget(self.operation_note)
        inputs_layout.addWidget(QLabel('Typed inputs · edit leaf values; add/remove object members and list entries explicitly'))
        self.inputs = QTreeWidget()
        self.inputs.setObjectName('numericalRequestInputs')
        self.inputs.setHeaderLabels(['Input field / index', 'Value', 'Type'])
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
        inputs_layout.addWidget(self.inputs, 1)
        input_buttons = QHBoxLayout()
        for label, callback in (('Add member / entry…', self.add_input), ('Remove selected', self.remove_input), ('Change type…', self.change_type)):
            button = QPushButton(label)
            button.clicked.connect(callback)
            input_buttons.addWidget(button)
        inputs_layout.addLayout(input_buttons)
        inputs_layout.addWidget(QLabel('Original proposal/source · read-only identity'))
        self.source = QPlainTextEdit()
        self.source.setReadOnly(True)
        self.source.setMaximumHeight(120)
        inputs_layout.addWidget(self.source)
        self.source_button = QPushButton('Open original source document')
        self.source_button.clicked.connect(self.open_source)
        inputs_layout.addWidget(self.source_button)
        split.addWidget(self.editor)
        right = QWidget()
        result_layout = QVBoxLayout(right)
        result_layout.addWidget(QLabel('Actual retained jobs · selecting a job never repeats it'))
        self.runs = readonly_table(['Job', 'State', 'Submitted input', 'Input relation'])
        self.runs.setMaximumHeight(170)
        self.runs.itemSelectionChanged.connect(self._selection_changed)
        result_layout.addWidget(self.runs)
        actions = QHBoxLayout()
        self.read_button, self.runner_button = QPushButton('Read / retry exact result'), QPushButton('Open selected job in Runner')
        self.read_button.clicked.connect(self.retry_result)
        self.runner_button.clicked.connect(self.open_runner)
        actions.addWidget(self.read_button)
        actions.addWidget(self.runner_button)
        self.expert_button = QPushButton('Consult Expert with selected result…')
        self.expert_button.clicked.connect(self.consult_expert)
        actions.addWidget(self.expert_button)
        result_layout.addLayout(actions)
        self.tabs = QTabWidget()
        self.candidates = readonly_table(['Candidate', 'Execution', 'Values', 'Objective', 'Failure'])
        self.candidates.itemSelectionChanged.connect(self._candidate_changed)
        self.tabs.addTab(self.candidates, 'Actual candidates')
        self.responses = QTreeWidget()
        self.responses.setHeaderLabels(['Response / metadata', 'Actual returned value'])
        self.tabs.addTab(self.responses, 'Responses')
        self.figure = Figure(figsize=(7, 4))
        self.canvas = FigureCanvasQTAgg(self.figure)
        plot_panel = QWidget()
        plot_layout = QVBoxLayout(plot_panel)
        self.plot_response = QComboBox()
        self.plot_response.currentIndexChanged.connect(self._plot_selected_result)
        plot_layout.addWidget(self.plot_response)
        plot_layout.addWidget(self.canvas)
        self.tabs.addTab(plot_panel, 'Actual result plots')
        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        self.tabs.addTab(self.details, 'Diagnostics / submitted input')
        result_layout.addWidget(self.tabs, 1)
        self.candidate_results_button = QPushButton('Open retained candidate curves / fields / stages')
        self.candidate_results_button.setObjectName('openCandidateStageResults')
        self.candidate_results_button.clicked.connect(self.open_candidate_results)
        result_layout.addWidget(self.candidate_results_button)
        self.pde_adopt_button = QPushButton('Review / adopt candidate to PDE…')
        self.pde_adopt_button.setObjectName('reviewPDECandidate')
        self.pde_adopt_button.clicked.connect(self.review_pde_candidate)
        result_layout.addWidget(self.pde_adopt_button)
        self._build_adoption_receipt_ui(result_layout)
        split.addWidget(right)
        split.setSizes([650, 790])
        self.setCentralWidget(root)
        self._update_actions()

    def open_document(self, *, document_id=None, title='Numerical request Plan', draft=None):
        if document_id is None and draft is None:
            draft = request_draft()
        return super().open_document(document_id=document_id, title=title, draft=draft)

    def _opened(self, document):
        self.local_dirty = self.conflict = False
        self._result_cache.clear()
        self._result_errors.clear()
        self._statuses.clear()
        self._show_document(document)
        self.message.setText('Request Plan opened. Source identity remains retained; edits and save do not execute a calculation.')

    @staticmethod
    def _shape_error(draft):
        if not isinstance(draft, dict) or set(draft) != {'mode', 'request', 'source'} or draft.get('mode') != 'request':
            return 'This document is not a request Plan. Its original draft is retained; use its own editor or Undo.'
        request = draft['request']
        if (not isinstance(request, dict) or set(request) != {'purpose', 'operation', 'inputs', 'budget'} or
            not isinstance(request['inputs'], dict) or not isinstance(request['budget'], dict) or
            set(request['budget']) != {'evaluations'} or not isinstance(request['purpose'], str)):
            return 'The request structure cannot fit this editor. It is retained in Diagnostics and can be saved or undone.'
        return None

    def _show_document(self, document, prefer_job=None):
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
            self._operation_inputs = {self._shown_operation: deepcopy(request['inputs'])}
            self._populate_inputs(request['inputs'])
            self._operation_controls()
        else:
            self.inputs.clear()
        self.source.setPlainText(json.dumps(document['draft'].get('source') if isinstance(document['draft'], dict) else None, ensure_ascii=False, indent=2))
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

    def _backend_edited(self, text):
        if self._populating or self._view_error or not self.inputs.topLevelItem(0):
            return
        inputs = self._input_value(self.inputs.topLevelItem(0))
        if self.operation.currentData() not in MODEL_OPERATIONS:
            return
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
        self.operation_note.setText({
            'analyze': 'Select the exact saved candidate table and declare each physical response/reduction. Failed rows remain exclusions.',
            'surrogate': 'Select separate retained training and holdout runs. Add physical response/reduction and typed points. Predictions remain PREDICTED; they cannot be adopted as evaluated coefficients.',
            'sensitivity': 'Select the matched retained Sobol sampling plan and actual response table. Ordinary DOE samples cannot substitute for its exact identities/order. Execution requires SALib on the service.',
            'sample_sensitivity': 'Declare variables, count (Sobol base count), seed and second_order. The downstream evaluation budget must cover count × (dimensions + 2), or count × (2 × dimensions + 2) for second order. Sampling requires SALib; it performs no model evaluation.',
            'doe': 'Edit the registered backend/settings and explicit variable declarations, or select retained candidate coordinates to evaluate them in their original order/IDs. Selecting a saved sampling plan never draws replacement points.',
            'batch_export': 'Select actual retained candidate coordinates and declare case_id. Export writes a file-exchange manifest; it performs no solver evaluation.',
            'batch_import': 'Select the retained batch manifest and exact actual imported result rows. Missing rows remain NOT_EVALUATED. Results may instead be entered as a typed results list.',
            'epsilon': 'Declare objectives, primary_index and physical threshold_grid explicitly. All child searches share the visible total evaluation budget.'
        }.get(operation, 'Edit explicit registered model inputs and budget; Apply and Run are separate commands.'))

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
                runs = [row for row in runs if row.get('backend', row.get('draft', {}).get('backend')) == backend]
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
                from .response_selection import response_choices
                reference, metadata = payload
                choices = response_choices(metadata)
                if not choices:
                    self.message.setText('No admitted scalar/history response is retained for this exact run. No field or node is inferred.')
                    return
                labels = [str(i + 1) + ': ' + item['label'] for i, item in enumerate(choices)]
                label, ok = QInputDialog.getItem(self, 'Select actual response', 'Component / exact native location', labels, editable=False)
                if not ok or not relevant(): return
                selector = choices[labels.index(label)]['selector']
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
            documents = [row for row in payload['documents'] if row.get('kind') in {'data', 'material', 'pde', 'simulation'}]
            labels = [row['title'] + ' · ' + row['id'] for row in documents]
            if not labels:
                self.message.setText('No retained source document is available. Import/evaluate and save its result first.')
                return
            label, ok = QInputDialog.getItem(self, 'Select source document', 'Exact saved source', labels, editable=False)
            if ok and relevant():
                self._call(lambda: self.client.document_read(documents[labels.index(label)]['id']), document_read, relevant=relevant)
        def begin():
            if not relevant(): return
            if model and source_id and (source.get('kind') in {'material', 'simulation', 'pde'} or source.get('pde_document_id')):
                self._call(lambda: self.client.document_read(source_id), document_read, relevant=relevant)
            else:
                self._call(self.client.documents, listed, relevant=relevant)
        if self._busy_background:
            self._pending_adoption = begin
            self._update_actions()
        else:
            begin()
        return True

    def choose_model_response(self):
        operation = self.operation.currentData()
        if operation not in {'doe', 'uq', 'fit', 'optimize', 'epsilon'}: return
        def selected(reference, selector, response, relevant):
            declaration = {key: deepcopy(response[key]) for key in
                ('unit', 'component', 'location', 'measure', 'frame', 'coordinate_system', 'coordinate_frame') if key in response}
            declaration['response'] = selector
            if operation in {'optimize', 'epsilon'}:
                reductions = ['none'] if response['kind'] == 'scalar' else ['max', 'min', 'mean', 'final', 'abs_max']
                reduction, ok = QInputDialog.getItem(self, 'Response reduction', 'Scalar statistic', reductions, editable=False)
                if not ok or not relevant(): return
                direction, ok = QInputDialog.getItem(self, 'Objective direction', 'Research objective', ['minimize', 'maximize'], editable=False)
                if not ok or not relevant(): return
                declaration.update(reduction=reduction, direction=direction)
                declaration['id'] = 'metric_' + canonical_hash({'response': selector, 'reduction': reduction})[:12]
                if operation == 'optimize':
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
                      'After selection, edit bounds in Typed inputs; no calculation is executed.')
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
                self._edit_structure(lambda value: value.__setitem__('variables', variables))
                self.message.setText('Selected declared variables added to Typed inputs. Review their bounds, then Apply; execution remains separate.')
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
        original_budget = draft['request']['budget']['evaluations']
        request['budget']['evaluations'] = deepcopy(original_budget) if self.evaluations.text() == value_text(original_budget) else leaf_value(self.evaluations.text(), 0)
        return draft

    @staticmethod
    def _at_path(value, path):
        for part in path:
            value = value[part]
        return value

    def _edit_structure(self, callback):
        if self._view_error or not self.document or self._busy:
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

    def refresh_document(self):
        if not self.document or self._busy or self._callbacks:
            return
        identifier = self.document['id']
        def received(remote):
            editing = self.local_dirty or self.inputs.state() == QAbstractItemView.State.EditingState
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
        selected = self._selected_pde_candidate()
        key = (self.document['id'], self.document['session_id'], job, canonical_hash(result)) if self.document else None
        unchanged = key == self._candidate_table_key
        self.candidates.blockSignals(True)
        self.candidates.clearSelection()
        self.candidates.setRowCount(0)
        self.candidates.setRowCount(len(rows))
        for row, candidate in enumerate(rows):
            for column, value in enumerate((candidate.get('candidate_id'), candidate_state(candidate), candidate.get('values'), candidate.get('objective'), candidate.get('failure_reason'))):
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
        self.plot_response.addItem('Study summary', None)
        for name, response in result.get('responses', {}).items():
            self.plot_response.addItem(name + ' [' + str(response.get('unit', 'undeclared')) + ']', name)
        index = self.plot_response.findData(previous)
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
        self.figure.clear()
        name = self.plot_response.currentData()
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
                    ax.set_title('Original retained response · ' + str(job))
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
            self._draw_study_summary(result, job)
        self.canvas.draw_idle()

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
        available = not (self._busy or self._callbacks or self._pending_adoption)
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
        read_available = present and not self.conflict and not self._callbacks and not self._pending_adoption and (not self._busy or self._busy_background)
        self.candidate_results_button.setEnabled(read_available and bool(self._selected_actual_candidate())
            and callable(getattr(self.client, 'numerical_evaluation_result', None)))
        self.variables_button.setEnabled(read_available and not self._view_error and self.operation.currentData() in MODEL_OPERATIONS
                                         and callable(getattr(self.client, 'describe_inputs', None)))
        for button in (self.model_response_button, self.observation_button):
            button.setEnabled(read_available and not self._view_error and callable(getattr(self.client, 'document_result_metadata', None)))
        source = self.document['draft'].get('source') if present and isinstance(self.document['draft'], dict) else None
        target_kind, target_id = self._candidate_target(source)
        self.pde_adopt_button.setText('Review / adopt candidate to PDE…' if target_kind == 'pde' else 'Review candidate in source…')
        self.pde_adopt_button.setEnabled(read_available and not self._view_error and bool(target_id)
                                        and self._adoption_receipt is None
                                        and self.operation.currentData() in PDE_CANDIDATE_OPERATIONS
                                        and bool(self._selected_pde_candidate())
                                        and callable(getattr(self.client, 'pde_candidate_preview' if target_kind == 'pde' else 'domain_candidate_preview', None))
                                        and callable(getattr(self.client, 'pde_adopt' if target_kind == 'pde' else 'domain_candidate_adopt', None)))
        self._update_adoption_receipt_actions()
        source_id = source.get('discussion_id',source.get('pde_document_id',source.get('document_id'))) if isinstance(source,dict) else None
        self.source_button.setEnabled(present and available and isinstance(source_id,str) and source_id.startswith(('X','Q','T','M','N','V','E')))
        self.reload_button.setVisible(self.conflict)
        self.copy_button.setVisible(self.conflict)
        self.reload_button.setEnabled(available)
        self.copy_button.setEnabled(available)
        if present:
            self.setWindowTitle('Numerical request Plan — ' + self.document['title'] + (' *' if self.local_dirty or self.document.get('dirty') else ''))
            self.identity.setText(f"g{self.document['generation']} · {self.document['id']}" + (' · unapplied edits' if self.local_dirty else ''))

    def open_runner(self):
        job = self.selected_job()
        if job:
            runner = RunnerWindow(self.client, job_id=job)
            self._runner_windows.append(runner)
            runner.show()

    def open_source(self):
        source = deepcopy(self.document['draft'].get('source'))
        identifier = source.get('discussion_id',source.get('pde_document_id',source.get('document_id'))) if isinstance(source,dict) else None
        if not isinstance(identifier,str) or not identifier.startswith(('X','Q','T','M','N','V','E')):
            self.message.setText('This request has no retained original source document.')
            return
        from .desktop import launch_tool
        def received(payload):
            self.message.setText('Requested the original source document: ' + str(payload.get('status', 'RETURNED')))
        tool = {'X':'expert', 'Q':'pde', 'T':'data', 'M':'material', 'N':'numerical', 'V':'simulation', 'E':'evaluation'}[identifier[0]]
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
