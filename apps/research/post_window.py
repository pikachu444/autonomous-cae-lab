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
import sys
import uuid
from urllib.error import HTTPError

from PySide6.QtCore import QThreadPool, QTimer, Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QApplication, QAbstractItemView, QCheckBox, QComboBox, QFormLayout,
    QHBoxLayout, QHeaderView, QInputDialog, QLabel, QLineEdit, QMainWindow,
    QMessageBox, QPlainTextEdit, QPushButton, QScrollArea, QSpinBox, QSplitter,
    QTabWidget, QTableWidget, QTableWidgetItem, QToolBar, QTreeWidget,
    QTreeWidgetItem, QVBoxLayout, QWidget,
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
LABELS = {'source_ref': 'Exact source', 'array': 'Native array', 'association': 'Association',
          'quantity': 'Physical quantity', 'units': 'Response unit', 'measure': 'Measure', 'frame': 'Response frame',
          'coordinate_units': 'Coordinate unit', 'coordinate_frame': 'Coordinate frame',
          'time': 'Exact native time (blank: none)', 'time_units': 'Clock unit (blank: none)',
          'time_origin': 'Clock origin (blank: none)', 'point_indices': 'Original point indexes',
          'origin': 'Plane origin [x, y, z]', 'normal': 'Plane normal [x, y, z]',
          'point1': 'First endpoint [x, y, z]', 'point2': 'Second endpoint [x, y, z]',
          'resolution': 'Line intervals', 'tolerance': 'Explicit native tolerance',
          'offsets': 'Slice offsets', 'values': 'Contour isovalues', 'scale_factor': 'Vector scale factor'}


def defaults(kind, source_ref=''):
    if kind == 'comparison':
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
        self.client, self.document_id, self.session_id = client, document_id, session_id
        self.document = None
        self._busy = self._populating = self._allow_close = self.local_dirty = self.conflict = False
        self._workers = []
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
        self.resize(1440, 940)
        self.setMinimumSize(1060, 700)
        toolbar = QToolBar('Native Post analysis')
        self.addToolBar(toolbar)
        self.open_action = QAction('Open owner…', self, shortcut=QKeySequence.Open)
        self.open_action.triggered.connect(self.choose_document)
        self.save_action = QAction('Save analysis', self, shortcut=QKeySequence.Save)
        self.save_action.triggered.connect(self.save_document)
        toolbar.addActions([self.open_action, self.save_action])
        self.menuBar().addMenu('&File').addActions([self.open_action, self.save_action])
        self.refresh_button = QPushButton('Refresh owner; keep draft')
        self.refresh_button.clicked.connect(lambda: self.refresh_document(explicit=True))
        toolbar.addWidget(self.refresh_button)
        self.numerical_button = QPushButton('Use in Numerical…')
        self.numerical_button.setObjectName('useMeasurementInNumerical')
        self.numerical_button.clicked.connect(self.use_in_numerical)
        toolbar.addWidget(self.numerical_button)
        self.handoff_retry = QPushButton('Resume measurement import')
        self.handoff_retry.clicked.connect(self._continue_measurement_handoff)
        self.handoff_retry.setVisible(False)
        toolbar.addWidget(self.handoff_retry)
        self._measurement_handoff = None
        self._measurement_dialog = None
        self.identity = QLabel()
        toolbar.addWidget(self.identity)
        root = QWidget()
        outer = QVBoxLayout(root)
        self.message = QLabel('Connect to the existing native Post document. ParaView retains its native render and plot views.')
        self.message.setWordWrap(True)
        outer.addWidget(self.message)
        split = QSplitter(Qt.Orientation.Horizontal)
        outer.addWidget(split, 1)
        left = QWidget()
        left_layout = QVBoxLayout(left)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(['Original sources / analysis objects', 'State'])
        self.tree.setColumnWidth(0, 260)
        self.tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.tree.itemSelectionChanged.connect(self._tree_selected)
        left_layout.addWidget(self.tree, 1)
        self.add_source_button = QPushButton('Add approved result…')
        self.add_source_button.clicked.connect(lambda: self.choose_source(repair=False))
        self.repair_button = QPushButton('Repair selected source…')
        self.repair_button.clicked.connect(lambda: self.choose_source(repair=True))
        self.show_source_button = QPushButton('Show source in native view')
        self.show_source_button.clicked.connect(self.show_source)
        self.inspect_button = QPushButton('Inspect exact native arrays')
        self.inspect_button.clicked.connect(self.inspect_source)
        for button in (self.add_source_button, self.repair_button, self.show_source_button, self.inspect_button):
            left_layout.addWidget(button)
        self.array_table = QTableWidget(0, 5)
        self.array_table.setHorizontalHeaderLabels(['Array', 'Association', 'Components', 'Unit', 'Declaration'])
        self.array_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.array_table.setMaximumHeight(200)
        self.array_table.horizontalHeader().setStretchLastSection(True)
        left_layout.addWidget(self.array_table)
        split.addWidget(left)
        center = QWidget()
        center_layout = QVBoxLayout(center)
        new_buttons = QHBoxLayout()
        self.new_buttons = []
        for kind in ('comparison', 'filter', 'measurement'):
            button = QPushButton('New ' + kind)
            button.clicked.connect(lambda checked=False, kind=kind: self.new_object(kind))
            self.new_buttons.append(button)
            new_buttons.addWidget(button)
        center_layout.addLayout(new_buttons)
        self.object_label = QLabel('New comparison · declarations are explicit')
        self.object_label.setWordWrap(True)
        center_layout.addWidget(self.object_label)
        self.tabs = QTabWidget()
        self._pages, self._forms, self.fields = {}, {}, {}
        for kind in ('comparison', 'filter', 'measurement'):
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            page = QWidget()
            form = QFormLayout(page)
            scroll.setWidget(page)
            self._pages[kind], self._forms[kind] = page, form
            self.tabs.addTab(scroll, kind.title())
        self.tabs.currentChanged.connect(self._tab_changed)
        center_layout.addWidget(self.tabs, 1)
        controls = QHBoxLayout()
        self.edit_button = QPushButton('Keep draft')
        self.edit_button.clicked.connect(self.store_draft)
        self.preview_button = QPushButton('Preview')
        self.preview_button.clicked.connect(self.preview)
        self.apply_button = QPushButton('Apply to native view')
        self.apply_button.clicked.connect(lambda: self.object_command('post.apply'))
        self.reset_button = QPushButton('Reset draft')
        self.reset_button.clicked.connect(self.reset_draft)
        for button in (self.edit_button, self.preview_button, self.apply_button, self.reset_button):
            controls.addWidget(button)
        center_layout.addLayout(controls)
        display_controls = QHBoxLayout()
        display_controls.addWidget(QLabel('Native display view'))
        self.view_selector = QComboBox()
        self.view_selector.setObjectName('postNativeView')
        self.view_selector.addItem('Owned view / new appropriate view', None)
        display_controls.addWidget(self.view_selector, 1)
        self.show_applied_button = QPushButton('Show applied result')
        self.show_applied_button.clicked.connect(lambda: self.object_command('post.show_analysis'))
        display_controls.addWidget(self.show_applied_button)
        center_layout.addLayout(display_controls)
        history = QHBoxLayout()
        self.undo_button, self.redo_button = QPushButton('Undo application'), QPushButton('Redo application')
        self.undo_button.clicked.connect(lambda: self.object_command('post.undo'))
        self.redo_button.clicked.connect(lambda: self.object_command('post.redo'))
        self.export_format = QComboBox()
        self.export_format.addItems(['vtu', 'csv', 'png'])
        self.export_button = QPushButton('Export selected result')
        self.export_button.clicked.connect(lambda: self.object_command('post.export', {'format': self.export_format.currentText()}))
        for widget in (self.undo_button, self.redo_button, self.export_format, self.export_button):
            history.addWidget(widget)
        center_layout.addLayout(history)
        scope = QLabel('These controls edit the selected analysis recipe. ParaView Properties, camera, field display and animation remain native. Preview does not apply or export a result.')
        scope.setWordWrap(True)
        center_layout.addWidget(scope)
        split.addWidget(center)
        right = QWidget()
        right_layout = QVBoxLayout(right)
        self.progress = QLabel('No native command in progress.')
        self.progress.setWordWrap(True)
        right_layout.addWidget(self.progress)
        self.retry_button = QPushButton('Recover same request')
        self.retry_button.clicked.connect(self.recover_request)
        right_layout.addWidget(self.retry_button)
        sample_controls = QFormLayout()
        self.sample_preview = QCheckBox('Read validated preview (unchecked: applied result)')
        self.sample_preview.setChecked(True)
        sample_controls.addRow(self.sample_preview)
        self.offset = QSpinBox()
        self.offset.setRange(0, 2_000_000_000)
        self.limit = QSpinBox()
        self.limit.setRange(1, 1000)
        self.limit.setValue(100)
        self.point_index = QLineEdit()
        self.point_index.setPlaceholderText('blank: bounded page')
        sample_controls.addRow('Sample offset', self.offset)
        sample_controls.addRow('Page limit', self.limit)
        sample_controls.addRow('Exact original point index', self.point_index)
        right_layout.addLayout(sample_controls)
        self.sample_button = QPushButton('Read actual samples')
        self.sample_button.clicked.connect(self.read_samples)
        right_layout.addWidget(self.sample_button)
        self.samples = QTableWidget(0, 0)
        self.samples.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.samples.setAlternatingRowColors(True)
        self.samples.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.samples.horizontalHeader().setStretchLastSection(True)
        right_layout.addWidget(self.samples, 1)
        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setMaximumHeight(280)
        right_layout.addWidget(self.details)
        split.addWidget(right)
        split.setSizes([340, 650, 450])
        self.setCentralWidget(root)
        self._populate_editor()
        self._update_actions()

    def _analysis(self, document=None):
        return (document or self.document or {}).get('state', {}).get('analysis', {})

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
        sources = QTreeWidgetItem(['Original sources', ''])
        objects = QTreeWidgetItem(['Analysis objects', ''])
        self.tree.addTopLevelItems([sources, objects])
        selected = None
        for record in self._sources():
            ref = record['source_ref']
            item = QTreeWidgetItem([record.get('label', ref), 'Available' if record.get('available') else 'Repair required'])
            item.setData(0, Qt.ItemDataRole.UserRole, ('source', ref))
            item.setToolTip(0, ref)
            sources.addChild(item)
            if self._tree_selection == ('source', ref):
                selected = item
        for obj in self._objects():
            item = QTreeWidgetItem([obj.get('title', obj['kind']), obj['kind'] + ' · ' + ('Preview' if obj.get('preview') else 'Applied' if obj.get('position', -1) >= 0 else 'Draft')])
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
        self.object_label.setText((obj.get('title', self._kind.title()) + ' · ' + obj['id']) if obj else 'New ' + self._kind + ' · explicit editable recipe')
        self.identity.setText(f"{document['id']} · g{document['generation']} · {'connected' if document.get('connected') else 'disconnected'}")
        self.identity.setToolTip('Exact owner session: ' + document['session_id'])
        self._populate_views()
        self.setWindowTitle('Post Analysis — ' + document.get('title', document['id']) + (' *' if self.local_dirty else ''))
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
            self.message.setText('Keep or Reset the edited recipe before selecting another analysis object. Current edits remain here.')
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
            self.object_label.setText(obj.get('title', obj['kind']) + ' · ' + ref)
            self._samples = None
            self.samples.setRowCount(0)
        self._update_actions()
        self._show_details()

    def _form_field(self, form, key, value, path):
        if key == 'source_ref':
            field = QComboBox()
            field.setEditable(True)
            field.addItem('', '')
            for source in self._sources():
                field.addItem(source.get('label', source['source_ref']) + ' · ' + source['source_ref'], source['source_ref'])
            for obj in self._objects():
                if obj.get('position', -1) >= 0:
                    field.addItem(obj.get('title', obj['id']) + ' · ' + obj['id'], obj['id'])
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
            source = next((row for row in self._sources() if row['source_ref'] == side.get('source_ref')), None)
            metadata = (source.get('metadata') or source.get('native_metadata') or {}) if source else {}
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
            self.method.addItems(['same_mesh', 'linear_tetra_b_to_a'])
            self.method.setCurrentText(draft.get('method', 'same_mesh'))
            self.method.currentTextChanged.connect(self._edited)
            form.addRow('Correspondence method', self.method)
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
            form.addRow('Native filter', self.filter_kind)
            settings = draft.get('settings', {})
            if isinstance(settings, dict):
                for key in FILTER_FIELDS.get(draft.get('filter'), ()):
                    default = None if key == 'time' else 'POINTS' if key == 'association' else ''
                    self._form_field(form, key, settings.get(key, default), ('settings', key))
            else:
                form.addRow(QLabel('Malformed filter settings retained in Details.'))
        else:
            self.measurement_kind = QComboBox()
            self.measurement_kind.addItems(['point', 'path', 'time'])
            if draft.get('measurement') not in MEASUREMENT_FIELDS:
                self.measurement_kind.addItem(display(draft.get('measurement')))
            self.measurement_kind.setCurrentText(draft.get('measurement', 'point'))
            self.measurement_kind.currentTextChanged.connect(self._measurement_changed)
            form.addRow('Measurement', self.measurement_kind)
            for key in MEASUREMENT_FIELDS.get(draft.get('measurement'), ()):
                self._form_field(form, key, draft.get(key, None if key in ('time', 'time_units', 'time_origin') else 'POINTS' if key == 'association' else ''), (key,))
                if key in MEASUREMENT_DECLARATIONS:
                    self.fields[(key,)][0].setPlaceholderText('Unknown unless explicitly declared')
            note = QLabel('Measurement meaning, units and frames are optional declarations. Blank remains unknown; native array names do not supply these meanings.')
            note.setWordWrap(True)
            form.addRow(note)
            declarations_button = QPushButton('Use exact source declarations')
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
        if self._kind == 'comparison' and self.method.currentText() != draft.get('method'):
            draft['method'] = self.method.currentText()
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
        self._draft = defaults(kind, self._source_ref or '')
        self.local_dirty = True
        self._edit_serial += 1
        self._populate_editor()
        self.object_label.setText('New ' + kind + ' · explicit editable recipe')
        return True

    def use_declarations(self, side=None):
        draft = self.edited_draft()
        target = draft.get(side, {}) if side is not None else draft
        source = next((source for source in self._sources() if source['source_ref'] == target.get('source_ref')), None)
        metadata = source.get('native_metadata') if source else None
        if not isinstance(metadata, dict):
            self.message.setText('This source has no retained physical declarations. Enter meaning, units and frames explicitly.')
            return
        declaration = next((row for row in metadata.get('arrays', []) if (row.get('name'), row.get('association')) == (target.get('array'), target.get('association'))), None)
        if not declaration:
            self.message.setText('Select an exact array and association declared in this source receipt.')
            return
        for key in ('quantity', 'units', 'measure', 'frame'):
            if key in declaration:
                target[key] = deepcopy(declaration[key])
        for key in ('coordinate_units', 'coordinate_frame'):
            if key in metadata:
                target[key] = deepcopy(metadata[key])
        clock = metadata.get('time')
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
        self.progress.setText(operation + ' · checking exact owner generation')
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
            self.progress.setText(operation + ' · ' + command.get('state', 'QUEUED') + ' · ' + request['command_id'])
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
        self.progress.setText(pending['request']['operation'] + ' · ' + command['state'] + ' · ' + command['command_id'])
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
            self.message.setText('Native owner completed ' + pending['request']['operation'] + ('; newer edits remain unapplied.' if late_edit else '.'))
        else:
            self._show_document(remote, preserve_buffer=True)
            error = command.get('outcome', {}).get('error', command.get('error', {}))
            self.message.setText('Native command ' + command['state'] + '; draft retained. ' + display(error))
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

    def read_samples(self):
        arguments = {'preview': self.sample_preview.isChecked(), 'offset': self.offset.value(), 'limit': self.limit.value()}
        if self.point_index.text().strip():
            arguments['point_index'] = integer_or_raw(self.point_index.text())
        return self.object_command('post.sample', arguments) if not self._object_ref else self.queue_command('post.sample',
            {'object_ref': self._object_ref, **arguments}, accepted=self._show_samples)

    def _show_samples(self, payload):
        self._samples = deepcopy(payload)
        rows = payload.get('rows', [])[:1000]
        headers = list(dict.fromkeys(key for row in rows for key in row))
        self.samples.setColumnCount(len(headers))
        self.samples.setHorizontalHeaderLabels(headers)
        self.samples.setRowCount(len(rows))
        for row, values in enumerate(rows):
            for column, key in enumerate(headers):
                self.samples.setItem(row, column, QTableWidgetItem(display(values.get(key))))
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
        self.view_selector.addItem('Owned view / new appropriate view', None)
        for view in (self.document or {}).get('state', {}).get('views', []):
            identifier = view.get('view_id')
            if isinstance(identifier, str) and identifier:
                self.view_selector.addItem(view.get('type', 'Native view') + ' · ' + identifier, identifier)
        index = self.view_selector.findData(selected)
        if index < 0 and selected is not None:
            self.view_selector.addItem('Unavailable native view · ' + selected, selected)
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
        if source and view.get('type') != 'RenderView':
            self.message.setText('Choose an exact native RenderView to show this original source.')
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
            values.append(item.get('metadata_status', 'explicit' if item.get('units') is not None else 'unknown'))
            for column, value in enumerate(values):
                self.array_table.setItem(row, column, QTableWidgetItem(display(value)))

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

    def _choose_directory(self, root, relative='', cursor=0, *, repair=False, token=None):
        token = self._context_token() if token is None else token
        def listed(payload):
            choices = [('.. parent folder', 'parent')] if relative else []
            choices += [(('[Folder] ' if item['directory'] else '') + item['name'], item) for item in payload['entries']
                        if item['directory'] or item['name'].lower().endswith(('.vtu', '.pvd'))]
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
                dialog = self._measurement_dialog = MeasurementDialog(payload['snapshot'], self)
                if dialog.exec() != QDialog.DialogCode.Accepted or token != self._context_token():
                    return
                selection = deepcopy(dialog.selection)
                if selection is None:
                    return
                # Explicit New Plan never reopens/replaces another live Plan.
                def context_ready(context):
                    self._measurement_handoff = {'command_id': command_id, 'selection': selection,
                        'session_id': context['service_session_id'], 'handoff_id': 'C' + uuid.uuid4().hex}
                    self.handoff_retry.setVisible(True)
                    self._continue_measurement_handoff()
                self._call(self.client.desktop_context, context_ready)
            self._call(lambda: self.client.post_measurement_preview(command_id), previewed,
                       relevant=lambda: token == self._context_token())
        return self.queue_command('post.measurement_snapshot', {'object_ref': obj['id']}, accepted=extracted)

    def _continue_measurement_handoff(self):
        pending = self._measurement_handoff
        if pending is None:
            return False
        def received(payload):
            if self._measurement_handoff is not pending:
                return
            state = payload['state']
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
        return self._call(lambda: self.client.post_measurement_plan(**deepcopy(pending)), received)

    def _update_actions(self):
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
        self.show_source_button.setEnabled(enabled and bool(self._source_ref))
        self.inspect_button.setEnabled(enabled and bool(self._source_ref))
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
        for button in self.new_buttons:
            button.setEnabled(enabled and not self.local_dirty)
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
            labels = [doc.get('title', doc['id']) + ' · ' + doc['id'] for doc in documents]
            label, accepted = QInputDialog.getItem(self, 'Open existing Post owner', 'Exact native document', labels, editable=False)
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
