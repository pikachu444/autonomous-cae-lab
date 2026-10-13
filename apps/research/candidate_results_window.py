"""Read an exact candidate's retained evaluations, stage attempts and histories."""
from copy import deepcopy
import json
import math

from PySide6.QtCore import Qt, QThreadPool
from PySide6.QtWidgets import (QComboBox, QHBoxLayout, QLabel, QMainWindow, QPlainTextEdit,
    QPushButton, QSpinBox, QSplitter, QTabWidget, QTableWidgetItem, QVBoxLayout, QWidget)
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure

from .data_window import _Read, display
from .runner_window import readonly_table

DATA = Qt.ItemDataRole.UserRole


class CandidateResultsWindow(QMainWindow):
    """A read-only candidate view; all result access stays in the existing owner."""
    def __init__(self, client, *, document_id, session_id, job_id, candidate_id,
                 values=None, units=None, relevant=None, post_open=None, parent=None):
        super().__init__(parent)
        self.client = client
        self.identity = (document_id, session_id, job_id, candidate_id)
        self._parent_relevant = relevant or (lambda: True)
        self.post_open = post_open
        self._closed = self._busy = self._populating = False
        self._pending = None
        self._worker = None
        self._serial = 0
        self._evaluation_index = self._attempt_id = None
        self._composite = self._stage_result = None
        self._native_catalog = {}
        self._curve_result = None
        self.resize(1180, 820)
        self.setWindowTitle('Retained candidate results — ' + candidate_id)
        root = QWidget(); layout = QVBoxLayout(root)
        label = QLabel(f'{document_id} · {job_id} · {candidate_id} · owner session {session_id}')
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(label)
        self.message = QLabel('Reading the actual candidate record does not execute or adopt inputs.')
        self.message.setWordWrap(True); layout.addWidget(self.message)
        self.parameters = readonly_table(['Actual parameter', 'Submitted value', 'Declared unit'])
        self.parameters.setMaximumHeight(140)
        self._rows(self.parameters, [(name, value, (units or {}).get(name, 'undeclared')) for name, value in (values or {}).items()])
        self.parameters.setMaximumHeight(min(140, self.parameters.horizontalHeader().height() +
            sum(self.parameters.rowHeight(row) for row in range(self.parameters.rowCount())) + 4))
        layout.addWidget(self.parameters)
        row = QHBoxLayout(); self.evaluations = QComboBox()
        self.evaluations.setObjectName('candidateEvaluations')
        self.evaluations.currentIndexChanged.connect(self._evaluation_selected)
        self.refresh_button = QPushButton('Read / retry exact records')
        self.refresh_button.clicked.connect(self.refresh_catalog)
        row.addWidget(QLabel('Actual candidate evaluations')); row.addWidget(self.evaluations, 1); row.addWidget(self.refresh_button)
        layout.addLayout(row)
        split = QSplitter(Qt.Orientation.Vertical)
        self.stages = readonly_table(['Iteration', 'Stage', 'Actual attempt', 'Execution', 'Backend', 'Reused source'])
        self.stages.setObjectName('candidateStageAttempts')
        self.stages.itemSelectionChanged.connect(self._stage_selected)
        split.addWidget(self.stages)
        tabs = QTabWidget()
        self.responses = readonly_table(['Response', 'Kind', 'Unit', 'Component', 'Position', 'Association / frame', 'Time', 'Actual value / retained array'])
        tabs.addTab(self.responses, 'Actual responses')
        self.residuals = readonly_table(['Iteration', 'Stage', 'Response', 'Unit', 'Actual residual', 'Limit', 'Passed'])
        tabs.addTab(self.residuals, 'Iteration residuals')
        self.diagnostics = QPlainTextEdit(); self.diagnostics.setReadOnly(True)
        tabs.addTab(self.diagnostics, 'Retained diagnostics')
        curve = QWidget(); curve_layout = QVBoxLayout(curve)
        row = QHBoxLayout()
        self.native_channel, self.native_location = QComboBox(), QComboBox()
        self.native_channel.setObjectName('candidateNativeChannel')
        self.native_location.setObjectName('candidateNativeLocation')
        self.native_channel.currentIndexChanged.connect(self._native_channel_selected)
        self.native_location.currentIndexChanged.connect(self._curve_selection_changed)
        row.addWidget(QLabel('Advertised channel')); row.addWidget(self.native_channel, 1)
        row.addWidget(QLabel('Exact retained location')); row.addWidget(self.native_location, 1)
        curve_layout.addLayout(row)
        row = QHBoxLayout()
        self.curve_start, self.curve_count = QSpinBox(), QSpinBox()
        self.curve_start.setObjectName('candidateCurveStart'); self.curve_start.setRange(0, 2**31 - 1)
        self.curve_count.setObjectName('candidateCurveCount'); self.curve_count.setRange(1, 4096); self.curve_count.setValue(1000)
        self.curve_start.valueChanged.connect(self._curve_selection_changed)
        self.curve_count.valueChanged.connect(self._curve_selection_changed)
        self.curve_read = QPushButton('Read selected native curve')
        self.curve_read.setObjectName('candidateReadNativeCurve'); self.curve_read.clicked.connect(self.read_native_curve)
        row.addWidget(QLabel('First retained sample')); row.addWidget(self.curve_start)
        row.addWidget(QLabel('Maximum samples')); row.addWidget(self.curve_count); row.addWidget(self.curve_read); row.addStretch()
        curve_layout.addLayout(row)
        self.curve_figure = Figure(constrained_layout=True)
        self.curve_canvas = FigureCanvasQTAgg(self.curve_figure)
        self.curve_axes = self.curve_figure.add_subplot(111)
        self.curve_values = readonly_table(['Retained sample index', 'Actual axis value', 'Actual response value', 'Validity'])
        self.curve_values.setObjectName('candidateNativeCurveValues'); self.curve_values.setMaximumHeight(180)
        self.curve_split = QSplitter(Qt.Orientation.Vertical)
        self.curve_split.addWidget(self.curve_canvas); self.curve_split.addWidget(self.curve_values)
        self.curve_split.setStretchFactor(0, 3); self.curve_split.setStretchFactor(1, 1)
        self.curve_split.setSizes([420, 100])
        curve_layout.addWidget(self.curve_split, 1)
        self.curve_detail = QLabel('Select an advertised native channel and exact location, then Read. No evaluation is executed.')
        self.curve_detail.setWordWrap(True); curve_layout.addWidget(self.curve_detail)
        self.curve_metadata_toggle = QPushButton('Show source and physical metadata')
        self.curve_metadata_toggle.setCheckable(True)
        self.curve_metadata = QPlainTextEdit()
        self.curve_metadata.setReadOnly(True)
        self.curve_metadata.setMaximumHeight(170)
        self.curve_metadata.hide()
        self.curve_metadata_toggle.toggled.connect(self.curve_metadata.setVisible)
        curve_layout.addWidget(self.curve_metadata_toggle)
        curve_layout.addWidget(self.curve_metadata)
        self.result_tabs = tabs
        tabs.addTab(curve, 'Native curve / bounded samples')
        split.addWidget(tabs); split.setStretchFactor(0, 1); split.setStretchFactor(1, 3)
        self.stages.setMaximumHeight(180)
        split.setSizes([135, 550])
        layout.addWidget(split, 1)
        row = QHBoxLayout(); self.fields = QComboBox()
        self.fields.setObjectName('candidateRetainedFields')
        self.fields.currentIndexChanged.connect(self._update_actions)
        self.design_button = QPushButton('Open as new design…')
        self.design_button.clicked.connect(self.open_design)
        self.post_button = QPushButton('Open selected retained field in Post')
        self.post_button.clicked.connect(self.open_post)
        row.addWidget(self.fields, 1); row.addWidget(self.post_button); row.addWidget(self.design_button); layout.addLayout(row)
        self.setCentralWidget(root)
        self._update_actions()
        self.refresh_catalog()

    @staticmethod
    def _rows(table, rows):
        table.setRowCount(len(rows))
        for row, values in enumerate(rows):
            for column, value in enumerate(values):
                item = QTableWidgetItem(display(value)); item.setData(DATA, deepcopy(value))
                table.setItem(row, column, item)
        table.resizeColumnsToContents()

    def _current(self):
        return not self._closed and bool(self._parent_relevant())

    def _update_actions(self, *_):
        current = self._current()
        self.refresh_button.setEnabled(current and not self._busy)
        self.design_button.setEnabled(current and not self._busy and
            (self._composite or {}).get('execution_status') == 'SUCCEEDED' and
            bool((self._composite or {}).get('editable_design', {}).get('calculated')))
        self.post_button.setEnabled(current and not self._busy and self.fields.currentData() is not None)
        self.curve_read.setEnabled(current and not self._busy and self._evaluation_index is not None
                                   and self.native_location.currentData() is not None)

    def _call(self, function, accepted, key):
        if self._busy:
            self._pending = (function, accepted, key)
            return
        if not self._current():
            self.message.setText('The originating plan selection changed. Reopen from the selected candidate to read its records.')
            self._update_actions(); return
        self._busy = True; self._update_actions()
        worker = self._worker = _Read(function)
        def finished(value, error):
            self._busy = False; self._worker = None
            if self._current() and key == self._serial:
                if error: self.message.setText('Exact retained read failed; no execution started. ' + error)
                else:
                    try: accepted(value)
                    except (ValueError, TypeError, KeyError) as invalid:
                        self.message.setText('The retained response does not match this selected record. ' + str(invalid))
            elif not self._closed:
                self.message.setText('Selection changed while reading; the late response was ignored.')
            self._update_actions()
            pending, self._pending = self._pending, None
            if pending and not self._closed: self._call(*pending)
        worker.signals.finished.connect(finished, Qt.ConnectionType.QueuedConnection)
        QThreadPool.globalInstance().start(worker)

    def _check_identity(self, result, *, evaluation=False, attempt=False):
        document, _, job, candidate = self.identity
        if any(result.get(key) != expected for key, expected in
               [('document_id', document), ('job_id', job), ('candidate_id', candidate)]):
            raise ValueError('Document, job or candidate identity differs')
        if evaluation and result.get('evaluation_index') != self._evaluation_index:
            raise ValueError('Evaluation index differs')
        if attempt and result.get('stage_attempt', {}).get('attempt_id') != self._attempt_id:
            raise ValueError('Stage attempt differs')

    def refresh_catalog(self):
        self._serial += 1
        self._evaluation_index = self._attempt_id = None
        self._composite = self._stage_result = None
        self.stages.setRowCount(0); self.responses.setRowCount(0); self.residuals.setRowCount(0); self.fields.clear()
        self._clear_curve_catalog()
        self._populating = True; self.evaluations.clear(); self._populating = False
        self.diagnostics.clear()
        document, _, job, candidate = self.identity
        def accepted(result):
            self._check_identity(result)
            self._populating = True; self.evaluations.clear()
            for record in result.get('evaluations', []):
                label = f"{record['evaluation_index']} · {record.get('execution_status', '?')}"
                if 'stage_execution_count' in record:
                    label += f" · {record['stage_execution_count']} actual stage calls"
                else:
                    label += ' · retained evaluation'
                self.evaluations.addItem(label, record['evaluation_index'])
            self._populating = False
            if not self.evaluations.count():
                self.message.setText('This candidate has no retained evaluation. Its numerical failure/diagnostics remain in the Plan.')
                self.diagnostics.setPlainText(json.dumps(result, ensure_ascii=False, indent=2))
            else: self._evaluation_selected()
        self._call(lambda: self.client.numerical_evaluation_result(document, job, candidate), accepted, self._serial)

    def _evaluation_selected(self, *_):
        if self._populating: return
        self._serial += 1; self._evaluation_index = self.evaluations.currentData(); self._attempt_id = None
        self._composite = self._stage_result = None
        self.stages.setRowCount(0); self.responses.setRowCount(0); self.residuals.setRowCount(0); self.fields.clear()
        self._clear_curve_catalog()
        if self._evaluation_index is None: return
        document, _, job, candidate = self.identity
        index = self._evaluation_index
        def accepted(result):
            self._check_identity(result, evaluation=True)
            self._composite = deepcopy(result)
            self._populating = True
            self._rows(self.stages, [(r.get('iteration'), r.get('stage_id'), r.get('attempt_id'), r.get('state'), r.get('backend'), r.get('reused_from')) for r in result.get('stages', [])])
            self.stages.setVisible(bool(result.get('stages')))
            self.stages.setMaximumHeight(min(180, self.stages.horizontalHeader().height() +
                sum(self.stages.rowHeight(row) for row in range(self.stages.rowCount())) + 4))
            self._populating = False
            self._rows(self.residuals, [(i.get('iteration'), r.get('stage'), r.get('response'), r.get('unit'), r.get('observed'), r.get('limit'), r.get('passed')) for i in result.get('iterations', []) for r in i.get('checks', [])])
            self._display_result(result)
            detail = '. Select an attempt to read that stage independently.' if result.get('stages') else '. No stage graph was retained; native channels belong to this exact evaluation.'
            self.message.setText('Actual retained evaluation: ' + str(result.get('execution_status', 'unknown')) + detail)
        self._call(lambda: self.client.numerical_evaluation_result(document, job, candidate,
            evaluation_index=index, selection={'metadata_only': True}), accepted, self._serial)

    def _stage_selected(self):
        if self._populating: return
        rows = self.stages.selectionModel().selectedRows()
        if len(rows) != 1: return
        self._serial += 1
        self._attempt_id = self.stages.item(rows[0].row(), 2).data(DATA)
        self._stage_result = None; self.responses.setRowCount(0); self.fields.clear()
        self._clear_curve_catalog()
        document, _, job, candidate = self.identity
        index, attempt = self._evaluation_index, self._attempt_id
        def accepted(result):
            self._check_identity(result, evaluation=True, attempt=True)
            self._stage_result = deepcopy(result); self._display_result(result)
            self.message.setText('Actual stage ' + attempt + ': ' + str(result.get('execution_status', 'unknown')) + '. The parent candidate may have failed independently.')
        self._call(lambda: self.client.numerical_evaluation_result(document, job, candidate,
            evaluation_index=index, attempt_id=attempt, selection={'metadata_only': True}), accepted, self._serial)

    def _display_result(self, result):
        rows = []
        for name, response in result.get('responses', {}).items():
            value = response.get('value', response.get('data_ref'))
            if isinstance(value, list): value = {'count': len(value), 'first_values': value[:6]}
            rows.append((name, response.get('kind'), response.get('unit'), response.get('component'), response.get('location'),
                {'association': response.get('association'), 'frame': response.get('frame')},
                {'value': response.get('time'), 'unit': response.get('time_units')}, value))
        self._rows(self.responses, rows)
        self.diagnostics.setPlainText(json.dumps({'execution_status': result.get('execution_status'),
            'diagnostics': result.get('diagnostics'), 'checks': result.get('checks'), 'stage_attempt': result.get('stage_attempt')}, ensure_ascii=False, indent=2))
        self.fields.clear()
        fields = [result['post_input']] if result.get('post_input') else []
        fields += result.get('post_inputs', [])
        seen = set()
        for field in fields:
            if not isinstance(field, dict) or not field.get('id') or field['id'] in seen: continue
            seen.add(field['id'])
            self.fields.addItem(field['id'] + ' · ' + str(field.get('format', 'field')) + ' · ' + str(field.get('sha256', ''))[:12], deepcopy(field))
        if result.get('backend') == 'structure.calculix.design' and result.get('post_artifact'):
            self.fields.addItem('Calculated native fields', {'native_candidate': True})
        self._native_catalog = deepcopy(result.get('native_channels', {}))
        for name, response in result.get('responses', {}).items():
            if response.get('kind') == 'series':
                self._native_catalog.setdefault(name, {'unit': response.get('unit'),
                    'selectors': [{'selector': name, 'label': name}], 'axes': deepcopy(response.get('axes', []))})
        self.native_channel.blockSignals(True); self.native_channel.clear()
        for name, descriptor in self._native_catalog.items():
            self.native_channel.addItem(name + ' [' + str(descriptor.get('unit', 'undeclared')) + ']', name)
        self.native_channel.blockSignals(False)
        self._native_channel_selected()
        self._update_actions()

    def _clear_curve_data(self):
        self._curve_result = None
        self.curve_metadata.clear()
        self.curve_values.setRowCount(0)
        self.curve_axes.clear()
        self.curve_axes.text(.5, .5, 'Read the selected exact retained history.\nNo curve is inferred from scalar or field metadata.',
                             ha='center', va='center', transform=self.curve_axes.transAxes)
        self.curve_canvas.draw_idle()

    def _clear_curve_catalog(self):
        self._native_catalog = {}
        self.native_channel.blockSignals(True); self.native_channel.clear(); self.native_channel.blockSignals(False)
        self.native_location.blockSignals(True); self.native_location.clear(); self.native_location.blockSignals(False)
        self._clear_curve_data()
        self.curve_detail.setText('No advertised native history is selected for this record.')
        self._update_actions()

    def _native_channel_selected(self, *_):
        self.native_location.blockSignals(True); self.native_location.clear()
        name = self.native_channel.currentData()
        descriptor = self._native_catalog.get(name, {})
        selectors = descriptor.get('selectors', [])
        if descriptor.get('gauss_ids'):
            template = descriptor.get('selector_template')
            fields = ('element_id', 'point', 'subpoint')
            if isinstance(template, str) and all(template.count('<' + key + '>') == 1 for key in fields):
                for point in descriptor['gauss_ids']:
                    if not isinstance(point, dict) or not all(key in point for key in fields):
                        continue
                    selector = template
                    for key in fields:
                        selector = selector.replace('<' + key + '>', str(point[key]))
                    label = 'Element {} / point {} / subpoint {}'.format(*(point[key] for key in fields))
                    self.native_location.addItem(label, selector)
        elif selectors and not descriptor.get('selectors_truncated'):
            for row in selectors:
                if isinstance(row, dict) and isinstance(row.get('selector'), str) and row['selector']:
                    self.native_location.addItem(str(row.get('label', row['selector'])), row['selector'])
        elif descriptor.get('node_ids'):
            template = descriptor.get('selector_template', str(name) + '@<node_id>')
            if isinstance(template, str) and template.count('<node_id>') == 1:
                for node in descriptor['node_ids']:
                    self.native_location.addItem('Node ' + str(node), template.replace('<node_id>', str(node)))
        else:
            selector = descriptor.get('source', {}).get('selector')
            if isinstance(selector, str) and selector:
                self.native_location.addItem(selector, selector)
        self.native_location.blockSignals(False)
        self._curve_selection_changed()

    def _curve_selection_changed(self, *_):
        self._clear_curve_data()
        self.curve_detail.setText('Exact selector: ' + str(self.native_location.currentData()) if self.native_location.currentData() is not None
                                 else 'This record has no supported exact native history selector.')
        self._update_actions()

    def _curve_key(self):
        return (self.identity, self._evaluation_index, self._attempt_id, self.native_channel.currentData(),
                self.native_location.currentData(), self.curve_start.value(), self.curve_count.value())

    def read_native_curve(self):
        if not self._current() or self._busy or self._evaluation_index is None:
            return
        key = self._curve_key()
        selector = self.native_location.currentData()
        if selector is None:
            return
        document, _, job, candidate = self.identity
        index, attempt = self._evaluation_index, self._attempt_id
        start, count = self.curve_start.value(), self.curve_count.value()
        def accepted(result):
            if self._curve_key() != key:
                self.message.setText('Native channel, location or sample page changed; the late curve was ignored.')
                return
            self._check_identity(result, evaluation=True, attempt=attempt is not None)
            response = result.get('responses', {}).get(selector)
            if not isinstance(response, dict) or response.get('kind') != 'series':
                raise ValueError('Selected native response is not an actual retained series')
            values = response.get('value')
            axis = next((a for a in response.get('axes', []) if isinstance(a, dict) and isinstance(a.get('values'), list)), None)
            if (not isinstance(values, list) or not values or len(values) > count or axis is None
                    or len(axis['values']) != len(values)
                    or any(type(v) not in (int, float) or not math.isfinite(v) for v in values + axis['values'])):
                raise ValueError('Retained native curve has no matching bounded finite scalar axis/value rows')
            mask = response.get('mask')
            if mask is not None and (not isinstance(mask, list) or len(mask) != len(values) or any(type(v) is not bool for v in mask)):
                raise ValueError('Retained curve validity mask differs from the bounded samples')
            rows = response.get('source_rows', list(range(start, start + len(values))))
            if not isinstance(rows, list) or len(rows) != len(values):
                raise ValueError('Retained curve original sample identities differ from its values')
            self._curve_result = deepcopy(response)
            self._rows(self.curve_values, [(row, x, y, 'valid' if mask is None or mask[i] else 'excluded')
                for i, (row, x, y) in enumerate(zip(rows, axis['values'], values))])
            self.curve_axes.clear()
            self.curve_axes.plot(axis['values'], [v if mask is None or mask[i] else math.nan for i, v in enumerate(values)], label=selector)
            self.curve_axes.set_xlabel(str(axis.get('name', 'axis')) + ' [' + str(axis.get('unit', 'undeclared')) + ']')
            self.curve_axes.set_ylabel(selector + ' [' + str(response.get('unit', 'undeclared')) + ']')
            self.curve_axes.legend(); self.curve_canvas.draw_idle()
            self.curve_detail.setText(selector + ' · ' + str(response.get('unit', 'undeclared')) +
                ' · samples ' + str(start) + '–' + str(start + len(values)) + ' · exact retained values')
            self.curve_metadata.setPlainText(display({'selector': selector, 'component': response.get('component'),
                'quantity': response.get('quantity'), 'location': response.get('location'),
                'frame': response.get('frame', response.get('coordinate_frame')), 'measure': response.get('measure'),
                'axes': [{key: deepcopy(axis[key]) for key in ('name', 'unit', 'semantics') if key in axis}
                         for axis in response.get('axes', [])],
                'source': response.get('source'), 'sample_page': [start, start + len(values)]}))
            self.result_tabs.setCurrentIndex(self.result_tabs.count() - 1)
            self.message.setText('Read ' + str(len(values)) + ' actual retained native samples. No evaluation or adoption was executed.')
        options = {'evaluation_index': index, 'selection': {'responses': [selector], 'rows': [start, start + count]}}
        if attempt is not None:
            options['attempt_id'] = attempt
        self._call(lambda: self.client.numerical_evaluation_result(document, job, candidate, **options), accepted, self._serial)

    def open_design(self):
        if not self._current() or self._busy or self._evaluation_index is None:
            return
        from PySide6.QtWidgets import QMessageBox
        answer = QMessageBox.question(self, 'Open calculated design',
            'Open this calculated candidate as a separate editable CAD design?',
            QMessageBox.StandardButton.Open | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel)
        if answer != QMessageBox.StandardButton.Open:
            return
        document, _, job, candidate = self.identity
        index = self._evaluation_index
        def launch():
            receipt = self.client.cad_candidate_open(document, job, candidate, index)
            from .desktop import _spawn
            return _spawn(self.client, ['pre', '--input-id', receipt['input_id']])
        self._call(launch, lambda _: self.message.setText('Opened the retained calculated candidate as a new design.'), self._serial)

    def open_post(self):
        field = self.fields.currentData()
        if not field or not self._current(): return
        document, _, job, candidate = self.identity
        source = {'document_id': document, 'candidate_id': candidate, 'evaluation_index': self._evaluation_index, 'attempt_id': self._attempt_id}
        def launch():
            selected = field
            if field.get('native_candidate'):
                selected = self.client.cad_candidate_post(document, job, candidate, source['evaluation_index'])
            native = self.client.native_input(selected['id'])
            if not selected.get('sha256') or native.get('sha256') != selected['sha256']:
                raise ValueError('Registered field differs from this retained stage result')
            if self.post_open: return self.post_open(deepcopy(selected), deepcopy(source))
            from .desktop import launch_post
            return launch_post(self.client, selected['id'], job_id=job, research_source=source)
        self._call(launch, lambda _: self.message.setText('Requested Post for the exact retained field and parent Plan job.'), self._serial)

    def closeEvent(self, event):
        self._closed = True; self._serial += 1; self._pending = None
        event.accept()
