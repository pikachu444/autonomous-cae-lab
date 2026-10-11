"""Independent Data editor backed by the shared local document service."""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
import math
import os
from time import monotonic
import sys
import uuid

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Qt, Signal
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QApplication, QAbstractItemView, QComboBox, QHBoxLayout, QHeaderView, QInputDialog,
    QLabel, QLineEdit, QMainWindow, QMessageBox, QPushButton, QPlainTextEdit,
    QSpinBox, QSplitter, QTableWidget, QTableWidgetItem, QTabWidget, QToolBar,
    QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure

from caelab.workbench_client import Client


TERMINAL = {'SUCCEEDED', 'FAILED', 'CANCELLED', 'PARTIAL_FAILURE', 'INTERRUPTED', 'REJECTED'}
TABLE_EXTENSIONS = ('.csv', '.txt', '.dat', '.asc', '.npz')
MAX_ROWS = 2000


def display(value):
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)


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


class _Read(QRunnable):
    def __init__(self, function):
        super().__init__()
        self.function, self.signals = function, _Signals()

    def run(self):
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
            self.signals.finished.emit(None, message)
        else:
            self.signals.finished.emit(value, None)


class DataWindow(QMainWindow):
    numerical_requested = Signal(object)
    expert_requested = Signal(object)

    def __init__(self, client, *, document_id=None, poll_interval=2000, auto_open=True):
        super().__init__()
        self.client, self.document = client, None
        self.local_dirty = self.conflict = self._busy = self._populating = False
        self._allow_close = False
        self._worker = None
        self._accepting = False
        self._callback_calls = []
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
        self._build_ui()
        self.timer = QTimer(self)
        self.timer.setInterval(poll_interval)
        self.timer.timeout.connect(self.refresh_document)
        if poll_interval > 0:
            self.timer.start()
        if auto_open:
            self.open_document(document_id=document_id)

    def _build_ui(self):
        self.resize(1440, 940)
        self.setMinimumSize(960, 690)
        files, edit = self.menuBar().addMenu('&File'), self.menuBar().addMenu('&Edit')
        self.new_action = QAction('&New data document…', self, shortcut=QKeySequence.New)
        self.open_action = QAction('&Open data document…', self, shortcut=QKeySequence.Open)
        self.save_action = QAction('&Save', self, shortcut=QKeySequence.Save)
        self.undo_action = QAction('&Undo mapping', self, shortcut=QKeySequence.Undo)
        self.redo_action = QAction('&Redo mapping', self, shortcut=QKeySequence.Redo)
        close = QAction('&Close', self, shortcut=QKeySequence.Close)
        self.new_action.triggered.connect(self.new_document)
        self.open_action.triggered.connect(self.choose_document)
        self.save_action.triggered.connect(self.save_document)
        close.triggered.connect(self.close)
        self.undo_action.triggered.connect(lambda: self.command('document.undo'))
        self.redo_action.triggered.connect(lambda: self.command('document.redo'))
        files.addActions([self.new_action, self.open_action, self.save_action, close])
        edit.addActions([self.undo_action, self.redo_action])
        toolbar = QToolBar('Data commands')
        toolbar.setMovable(False)
        self.addToolBar(toolbar)
        toolbar.addActions([self.new_action, self.open_action, self.save_action, self.undo_action, self.redo_action])
        self.source_button = QPushButton('Choose approved source…')
        self.apply_button = QPushButton('Apply mapping')
        self.import_button = QPushButton('Import table')
        self.source_button.clicked.connect(self.choose_source)
        self.apply_button.clicked.connect(self.apply_inputs)
        self.import_button.clicked.connect(self.import_table)
        for button in (self.source_button, self.apply_button, self.import_button):
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
        conflict.addWidget(self.reload_button)
        conflict.addWidget(self.copy_button)
        conflict.addStretch()
        layout.addLayout(conflict)
        horizontal = QSplitter(Qt.Orientation.Horizontal)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabel('Source and retained imports')
        self.tree.itemSelectionChanged.connect(self._selection_changed)
        horizontal.addWidget(self.tree)
        center = QWidget()
        central = QVBoxLayout(center)
        self.source_label = QLabel('Choose an original numeric table from an approved source folder.')
        self.source_label.setWordWrap(True)
        central.addWidget(self.source_label)
        self.editor = QWidget()
        editor = QVBoxLayout(self.editor)
        editor.setContentsMargins(0, 0, 0, 0)
        parsing = QHBoxLayout()
        self.delimiter = QLineEdit(',')
        self.delimiter.setMaximumWidth(130)
        self.delimiter.setPlaceholderText(',  tab  space')
        self.skip_header = QLineEdit('0')
        self.skip_header.setMaximumWidth(90)
        self.layout_button = QPushButton('Use preview column layout')
        self.layout_button.clicked.connect(self.use_preview_layout)
        parsing.addWidget(QLabel('Delimiter'))
        parsing.addWidget(self.delimiter)
        parsing.addWidget(QLabel('Skip header rows'))
        parsing.addWidget(self.skip_header)
        parsing.addWidget(self.layout_button)
        parsing.addStretch()
        editor.addLayout(parsing)
        channel_controls = QHBoxLayout()
        self.channel_selector = QComboBox()
        self.channel_selector.currentTextChanged.connect(self._channel_changed)
        channel_controls.addWidget(QLabel('Edit channel'))
        channel_controls.addWidget(self.channel_selector, 1)
        for title, mode in (('Add channel', 'add'), ('Clone channel', 'clone'), ('Remove channel', 'remove')):
            button = QPushButton(title)
            button.clicked.connect(lambda checked=False, mode=mode: self.edit_channels(mode))
            channel_controls.addWidget(button)
        editor.addLayout(channel_controls)
        self.mapping = QTableWidget(2, 10)
        self.mapping.setObjectName('dataMapping')
        self.mapping.setHorizontalHeaderLabels(['Role', 'Channel / axis name', 'Source column', 'Unit', 'Component', 'Location', 'Measure', 'Frame', 'Scale', 'Offset'])
        self.mapping.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.mapping.horizontalHeaderItem(3).setToolTip('Unit of the imported value after Scale and Offset. A label change does not convert values.')
        self.mapping.horizontalHeaderItem(8).setToolTip('Imported value = original value * Scale + Offset. Applied independently to axis and response; default Scale is 1.')
        self.mapping.horizontalHeaderItem(9).setToolTip('Added after scaling, in the declared imported unit; default Offset is 0.')
        self.mapping.verticalHeader().hide()
        self.mapping.setMaximumHeight(116)
        self.mapping.itemChanged.connect(self._mapping_item_edited)
        self.delimiter.textEdited.connect(self._edited)
        self.skip_header.textEdited.connect(self._edited)
        editor.addWidget(self.mapping)
        example = QLabel('Column indexes start at 0; named columns use the exact header. For each row: imported value = original value * Scale + Offset (defaults: 1 and 0). Unit labels do not convert values. Original source values are preserved; no unit or frame conversion is inferred.')
        example.setWordWrap(True)
        editor.addWidget(example)
        self.test_fields = {}
        metadata = QHBoxLayout()
        for key, label in (('test_id', 'Test ID'), ('specimen', 'Specimen'), ('protocol', 'Protocol'), ('temperature', 'Temperature / unit')):
            field = self.test_fields[key] = QLineEdit()
            field.textEdited.connect(self._edited)
            metadata.addWidget(QLabel(label))
            metadata.addWidget(field)
        editor.addLayout(metadata)
        self.row_fields = {}
        for key, label, placeholder in (
            ('include_ranges', 'Calculation intervals', 'original row intervals: 3:20, 30:40; blank = all'),
            ('exclude_rows', 'Calculation exclusions', 'original row IDs: 5, 8'),
            ('exclude_ranges', 'Excluded intervals', 'original row intervals: 10:15'),
            ('quality_rows', 'Raw quality invalid', 'original row IDs; does not exclude calculations'),
            ('display_hidden_rows', 'Display hidden rows', 'original row IDs; does not exclude calculations'),
            ('reasons', 'Exclusion reasons', 'row: reason; row: reason'),
            ('quality_reasons', 'Quality reasons', 'row: reason; row: reason')):
            line = QHBoxLayout()
            field = self.row_fields[key] = QLineEdit()
            field.setPlaceholderText(placeholder)
            field.textEdited.connect(self._edited)
            line.addWidget(QLabel(label))
            line.addWidget(field)
            editor.addLayout(line)
        note = QLabel('Row IDs are zero-based original physical lines (NPZ: array indexes). Intervals include both endpoints. Raw quality, calculation selection and display hiding are independent. Fit / holdout roles belong to the Numerical Plan.')
        note.setWordWrap(True)
        editor.addWidget(note)
        central.addWidget(self.editor)
        vertical = QSplitter(Qt.Orientation.Vertical)
        self.sheets = QTabWidget()
        self.preview_table = self._table(['Original row'])
        self.values = self._table(['Original row', 'Axis', 'Response', 'Calculation', 'Raw quality', 'Display', 'Reason'])
        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        self.sheets.addTab(self.preview_table, 'Original source preview')
        self.sheets.addTab(self.values, 'Imported values')
        self.sheets.addTab(self.details, 'Details / diagnostics')
        vertical.addWidget(self.sheets)
        graph = QWidget()
        graph_layout = QVBoxLayout(graph)
        rows = QHBoxLayout()
        self.row_start = QSpinBox()
        self.row_start.setRange(0, 2_000_000_000)
        self.row_count = QSpinBox()
        self.row_count.setRange(1, MAX_ROWS)
        self.row_count.setValue(MAX_ROWS)
        self.read_button = QPushButton('Read selected rows')
        self.read_button.clicked.connect(self.retry_result)
        rows.addWidget(QLabel('First response sample'))
        rows.addWidget(self.row_start)
        rows.addWidget(QLabel('Count'))
        rows.addWidget(self.row_count)
        rows.addWidget(self.read_button)
        self.result_channel = QComboBox()
        self.result_channel.currentTextChanged.connect(self._result_channel_changed)
        rows.addWidget(QLabel('Imported channel'))
        rows.addWidget(self.result_channel)
        rows.addStretch()
        graph_layout.addLayout(rows)
        followup = QHBoxLayout()
        self.compare_button = QPushButton('Compare retained prediction…')
        self.compare_button.clicked.connect(self.choose_prediction)
        self.plan_button = QPushButton('Open / create Numerical Plan…')
        self.plan_button.clicked.connect(lambda: self.request_followup('numerical'))
        self.expert_button = QPushButton('Consult Expert with selected result…')
        self.expert_button.clicked.connect(lambda: self.request_followup('expert'))
        for button in (self.compare_button, self.plan_button, self.expert_button):
            followup.addWidget(button)
        graph_layout.addLayout(followup)
        saved_comparisons = QHBoxLayout()
        saved_comparisons.addWidget(QLabel('Retained comparison'))
        self.comparison_selector = QComboBox()
        self.comparison_selector.setObjectName('dataSavedComparison')
        self.comparison_selector.currentIndexChanged.connect(self._comparison_changed)
        saved_comparisons.addWidget(self.comparison_selector, 1)
        graph_layout.addLayout(saved_comparisons)
        self.result_label = QLabel()
        self.result_label.setWordWrap(True)
        graph_layout.addWidget(self.result_label)
        self.figure = Figure(constrained_layout=True)
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.axes = self.figure.add_subplot(111)
        graph_layout.addWidget(self.canvas, 1)
        vertical.addWidget(graph)
        vertical.setSizes([330, 310])
        central.addWidget(vertical, 1)
        horizontal.addWidget(center)
        horizontal.setSizes([225, 1190])
        layout.addWidget(horizontal, 1)
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

    def _call(self, function, accepted, *, relevant=None, background=False, settled=None):
        if self._busy:
            if self._accepting and not background:
                self._callback_calls.append((function, accepted, relevant, settled))
                return True
            if not background:
                self.message.setText('A document request is in progress. Your current edits are retained.')
            return False
        self._busy = True
        self._update_actions()
        worker = self._worker = _Read(function)
        def finished(value, error):
            # Modal choosers process timer events. Keep the request lock until
            # their callback finishes, then start its explicit continuation.
            self._accepting = True
            try:
                if settled:
                    settled(value, error)
                if relevant is None or relevant():
                    if error:
                        self.message.setText('Request failed; current edits retained. ' + error)
                    else:
                        accepted(value)
            finally:
                self._accepting = False
                self._busy, self._worker = False, None
            self._update_actions()
            if self._callback_calls:
                next_function, next_accepted, next_relevant, next_settled = self._callback_calls.pop(0)
                self._call(next_function, next_accepted, relevant=next_relevant, settled=next_settled)
            elif not background:
                QTimer.singleShot(0, self.refresh_result)
        worker.signals.finished.connect(finished, Qt.ConnectionType.QueuedConnection)
        QThreadPool.globalInstance().start(worker)
        return True

    def open_document(self, *, document_id=None, title='Data study', draft=None):
        return self._call(lambda: self.client.document_open(kind='data', title=title, draft=draft, document_id=document_id), self._opened)

    def _opened(self, document):
        self.local_dirty = self.conflict = False
        self._selected_job = None
        self._comparison = self._comparison_id = None
        self._comparison_serial += 1
        self._results.clear()
        self._result_errors.clear()
        self._preview_key = None
        self._preview = None
        self.preview_table.setRowCount(0)
        self._show_document(document)
        self.message.setText('Map the original axis and response, Apply mapping, then Import table. Opening a document never imports it again.')
        QTimer.singleShot(0, self.refresh_preview)

    def _show_document(self, document, *, prefer_job=None):
        self.document = deepcopy(document)
        self._populating = True
        draft = document['draft']
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
        source = QTreeWidgetItem(['Original source'])
        source.setToolTip(0, str(self._source_id))
        self.tree.addTopLevelItem(source)
        imports = QTreeWidgetItem(['Retained imports'])
        self.tree.addTopLevelItem(imports)
        self._selected_job = prefer_job or self._selected_job
        if self._selected_job is None and self.document['runs']:
            self._selected_job = self.document['runs'][-1]['job_id']
        for index, run in enumerate(self.document['runs']):
            text = f"Import {index + 1} · input g{run['input_generation']}"
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
            self.local_dirty = True
            self._update_actions()
            self._draw_cached_result()

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

    def edited_draft(self):
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
        if not self.document or self.conflict:
            return False
        if self.local_dirty and operation != 'data.update':
            self.message.setText('Apply the edited mapping first; import uses the exact applied document generation.')
            return False
        document = deepcopy(self.document)
        def accepted(receipt):
            self.local_dirty = self.conflict = False
            job = receipt.get('job')
            self._preview_key = None
            self._show_document(receipt['document'], prefer_job=job['id'] if job else None)
            self.message.setText('Applied through the Data document owner: ' + operation)
            if after:
                after()
            else:
                QTimer.singleShot(0, self.refresh_preview)
        return self._call(lambda: self.client.document_command(document['id'], operation, arguments or {},
            session_id=document['session_id'], expected_generation=document['generation'], command_id='C' + uuid.uuid4().hex), accepted)

    def apply_inputs(self, *, after=None):
        return self.command('data.update', {'draft': self.edited_draft()}, after=after)

    def save_document(self, *, after=None):
        self._commit_editor()
        if self.local_dirty:
            return self.apply_inputs(after=lambda: self.command('document.save', after=after))
        return self.command('document.save', after=after)

    def import_table(self):
        return self.command('data.import')

    def refresh_document(self):
        if not self.document or self._busy:
            return
        identifier = self.document['id']
        session = self.document['session_id']
        def accepted(remote):
            changed = (remote['session_id'], remote['generation']) != (self.document['session_id'], self.document['generation'])
            if changed and self.local_dirty:
                self.conflict = True
                self.message.setText('The shared document changed while you were editing. Reload it or keep these edits as a new document.')
            elif not self.local_dirty and not self.conflict:
                self._show_document(remote)
            self._update_actions()
        def refreshed(remote):
            accepted(remote)
            QTimer.singleShot(0, self.refresh_preview)
            QTimer.singleShot(0, self.refresh_result)
        self._call(lambda: self.client.document_read(identifier), refreshed, background=True,
            relevant=lambda: self.document is not None and (self.document['id'], self.document['session_id']) == (identifier, session))

    def reload_remote(self):
        if QMessageBox.question(self, 'Reload Data document', 'Discard this window’s unapplied mapping and reload the service version?',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Cancel) == QMessageBox.StandardButton.Yes:
            self._call(lambda: self.client.document_read(self.document['id']), self._opened)

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
            self.source_label.setText('Selected original: ' + receipt['name'] + ' · unapplied source change')
            QTimer.singleShot(0, self.refresh_preview)
        return self._call(lambda: self.client.register_local_input(root, relative), registered)

    def refresh_preview(self):
        if not self.document or not self._source_id or self._busy:
            return
        key = (self.document['id'], self._source_id, self.document.get('saved_revision'))
        if key == self._preview_key or monotonic() < self._preview_retry:
            return
        applied = self._source_id == self.document['draft'].get('data_id')
        def accepted(preview):
            self._preview_key = key
            self._preview = preview
            table = preview.get('table_preview', {})
            self.preview_table.clear()
            headers = ['Original row'] + table.get('headers', [])
            self.preview_table.setColumnCount(len(headers))
            self.preview_table.setHorizontalHeaderLabels(headers)
            self.preview_table.setRowCount(len(table.get('rows', [])))
            for row, values in enumerate(table.get('rows', [])):
                for column, value in enumerate([table.get('row_numbers', [])[row] if row < len(table.get('row_numbers', [])) else 'unknown'] + values):
                    self.preview_table.setItem(row, column, QTableWidgetItem(str(value)))
            self.source_label.setText(('Retained original: ' if preview.get('retained') else 'Registered original: ') +
                preview.get('name', self._source_id) + (' · bounded preview' if table else ' · ' + preview.get('preview', 'No simple table preview; mapping remains explicit.')))
            self._show_details()
            self._update_actions()
        method = (lambda: self.client.document_source_preview(self.document['id'])) if applied else (lambda: self.client.input_preview(self._source_id))
        def settled(value, error):
            if error:
                self._preview_retry = monotonic() + max(1, self.timer.interval() / 1000)
            QTimer.singleShot(0, self.refresh_result)
        self._call(method, accepted, settled=settled, relevant=lambda: key == (self.document['id'], self._source_id, self.document.get('saved_revision')), background=True)

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
        if identifier != self._selected_job:
            self._selected_job = identifier
            self._comparison = self._comparison_id = None
            self._comparison_serial += 1
            self._populate_comparisons()
            self.row_start.setValue(0)
            self._clear_result()
        if identifier:
            self.refresh_result()
        else:
            self.sheets.setCurrentWidget(self.preview_table)

    def _result_key(self):
        return (self.document['id'], self._selected_job, self.row_start.value(), self.row_count.value(), self._result_channel) if self.document else None

    def refresh_result(self):
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
        selector.addItem('No comparison overlay', None)
        records = list((self.document or {}).get('comparisons', []))
        current = (self._comparison or {}).get('result', {})
        if current.get('id') and not any(row['id'] == current['id'] for row in records):
            records.append({'id': current['id'], 'binding': current.get('binding', {}), 'metrics': current.get('comparison', {})})
        for record in records:
            binding = record.get('binding', {})
            if not self._matches_source(binding.get('source')):
                continue
            prediction = binding.get('prediction_source', {})
            metrics = record.get('metrics', {})
            label = f"{prediction.get('response', '?')} · {prediction.get('document_id', '?')} / {prediction.get('job_id', '?')} · RMSE {metrics.get('rmse', '?')} {metrics.get('unit', '')}"
            selector.addItem(label, record['id'])
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
            def choose(payload):
                documents=[row for row in payload['documents'] if row.get('kind')=='material']
                if not documents:
                    self.message.setText('Open a Material model and edit its protocol, then select it here. Data remains independent.')
                    return
                names=[row['title']+' — '+row['id'] for row in documents]
                selected,accepted=QInputDialog.getItem(self,'Identification model','Explicit Material model and load history',names,editable=False)
                if accepted and token == self._source_token(): create(documents[names.index(selected)]['id'])
            self._call(self.client.documents,choose, relevant=lambda: token == self._source_token())

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

    def _clear_result(self):
        self.values.setRowCount(0)
        self.axes.clear()
        self.axes.set_axis_off()
        self.axes.text(.5, .5, 'Select a retained import to read its original values', ha='center', va='center', transform=self.axes.transAxes)
        self.canvas.draw_idle()
        self.result_label.setText('No imported response selected.')

    def _draw_result(self, receipt, key):
        self._clear_result()
        _, identifier, start, _, _ = key
        run = next(item for item in self.document['runs'] if item['job_id'] == identifier)
        stale = self.local_dirty or not run.get('is_current_input', run['input_generation'] == self.document['generation'])
        self.result_label.setText(f"Import g{run['input_generation']} · {receipt['status']['state']}" + (' · earlier mapping/source' if stale else ' · current applied input'))
        responses = receipt.get('result', {}).get('responses', {})
        if not responses:
            error = receipt['status'].get('error')
            if error:
                self.result_label.setText(self.result_label.text() + ' · ' + display(error))
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
        if isinstance(raw, dict) and isinstance(raw.get('source_rows'), list):
            offset=0 if 'page_start' in raw else start
            raw_indexes = list(range(len(raw['source_rows'])))[offset:offset + self.row_count.value()]
            self.values.setRowCount(len(raw_indexes))
            for row, index in enumerate(raw_indexes):
                cells = [raw['source_rows'][index], raw.get('axis', [None] * len(raw['source_rows']))[index] if raw.get('axis') is not None else '',
                    raw['value'][index], raw['calculation_valid'][index], raw['quality_valid'][index], raw['display_visible'][index],
                    '; '.join(reason for reason in (raw['exclusion_reasons'][index], raw['quality_reasons'][index]) if reason)]
                for column, cell in enumerate(cells):
                    self.values.setItem(row, column, QTableWidgetItem(display(cell)))
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
        self.axes.set_xlabel(f"{axis.get('name', 'unknown')} [{axis.get('unit', 'unknown')}]")
        self.axes.set_ylabel(f"{name} [{response.get('unit', 'unknown')}]")
        self.axes.set_title(' · '.join(f'{key}: {response.get(key, "UNSPECIFIED")}' for key in ('component', 'location', 'measure', 'frame')), fontsize=9)
        self.axes.grid(True, alpha=.25)
        self.canvas.draw_idle()
        self.result_label.setText(self.result_label.text() + f' · response samples [{start}, {start + len(values)})')
        self._show_details()

    def _show_details(self):
        self.details.setPlainText(json.dumps({'document': self.document, 'view_diagnostic': self._view_error,
            'source_preview': self._preview, 'selected_result': self._results.get(self._result_key()),
            'result_read_errors': list(self._result_errors.values()), 'comparison': self._comparison}, ensure_ascii=False, indent=2))

    def _update_actions(self):
        present = self.document is not None
        enabled = present and not self._busy and not self.conflict
        self.editor.setEnabled(enabled and not self._view_error)
        self.source_button.setEnabled(enabled and not self._view_error)
        self.apply_button.setEnabled(enabled and self.local_dirty and not self._view_error)
        blocked = present and any(item.get('blocks_evaluation') for item in self.document.get('diagnostics', []))
        self.import_button.setEnabled(enabled and not self.local_dirty and not blocked and not self._view_error)
        self.save_action.setEnabled(enabled)
        self.undo_action.setEnabled(enabled and not self.local_dirty and self.document.get('can_undo', False))
        self.redo_action.setEnabled(enabled and not self.local_dirty and self.document.get('can_redo', False))
        self.new_action.setEnabled(not self._busy)
        self.open_action.setEnabled(not self._busy)
        self.read_button.setEnabled(present and bool(self._selected_job) and not self._busy)
        for button in (self.compare_button, self.plan_button, self.expert_button):
            button.setEnabled(enabled and bool(self._selected_job) and not self.local_dirty)
        self.comparison_selector.setEnabled(enabled and bool(self._selected_job) and not self.local_dirty)
        self.layout_button.setEnabled(bool((self._preview or {}).get('table_preview')) and not self._view_error)
        self.reload_button.setVisible(self.conflict)
        self.copy_button.setVisible(self.conflict)
        self.reload_button.setEnabled(not self._busy)
        self.copy_button.setEnabled(not self._busy)
        if present:
            self.setWindowTitle('Data — ' + self.document['title'] + (' *' if self.local_dirty or self.document.get('dirty') else ''))
            self.identity.setText(f"  g{self.document['generation']}" + (' · unapplied edits' if self.local_dirty else ''))
            self.identity.setToolTip(f"Document: {self.document['id']}\nSession: {self.document['session_id']}\nSaved: {self.document.get('saved_revision')}")

    def _leave(self, continuation):
        self._commit_editor()
        if self._busy:
            self.message.setText('Wait for the document request before leaving. Existing imports remain service-owned.')
            return
        if not self.document or not (self.local_dirty or self.document.get('dirty')):
            continuation()
            return
        question = QMessageBox(self)
        question.setWindowTitle('Unsaved Data document')
        question.setText('Save this document before leaving?')
        question.setInformativeText('Keep service draft preserves unapplied mapping edits without saving a revision. Closing does not cancel a job.')
        save = question.addButton('Save', QMessageBox.ButtonRole.AcceptRole)
        keep = question.addButton('Keep service draft', QMessageBox.ButtonRole.DestructiveRole)
        question.addButton(QMessageBox.StandardButton.Cancel)
        question.exec()
        if question.clickedButton() == save:
            self.save_document(after=continuation)
        elif question.clickedButton() == keep:
            if self.conflict:
                self.message.setText('Resolve the conflict or keep edits as a new document before leaving.')
            elif self.local_dirty:
                self.apply_inputs(after=continuation)
            else:
                continuation()

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
                    self.message.setText('No Data documents are available.')
                    return
                labels = [f"{item['title']} — {item['id']}" for item in documents]
                label, accepted = QInputDialog.getItem(self, 'Open Data document', 'Document', labels, editable=False)
                if accepted:
                    self.open_document(document_id=documents[labels.index(label)]['id'])
            self._call(self.client.documents, listed)
        self._leave(choose)

    def closeEvent(self, event):
        if self._allow_close:
            self.timer.stop()
            event.accept()
            return
        event.ignore()
        def leave():
            self._allow_close = True
            self.close()
        self._leave(leave)

    def showEvent(self, event):
        self._allow_close = False
        if self.timer.interval() > 0:
            self.timer.start()
        super().showEvent(event)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--service', default=os.environ.get('CAELAB_SERVICE_URL'))
    parser.add_argument('--document-id')
    args = parser.parse_args(argv)
    if not args.service:
        parser.error('--service or CAELAB_SERVICE_URL must identify the existing local service')
    app = QApplication.instance() or QApplication(sys.argv[:1])
    window = DataWindow(Client(args.service), document_id=args.document_id)
    window.show()
    return app.exec()


if __name__ == '__main__':
    raise SystemExit(main())
