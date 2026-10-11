"""Retained curve comparison on the original domain owner, without evaluation."""
from __future__ import annotations

from copy import deepcopy
import json
import math
import uuid

from PySide6.QtCore import QThreadPool, QTimer, Qt
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QHBoxLayout, QLabel,
    QMainWindow, QPushButton, QPlainTextEdit, QSpinBox, QSplitter, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget)
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure

from .pde_window import _Read
from .response_selection import response_choices

KINDS = {'data', 'material', 'pde', 'simulation'}


def _matches(binding, source):
    return isinstance(binding, dict) and all(binding.get(key) == value for key, value in source.items())


def _number(value):
    return type(value) in (int, float) and math.isfinite(value)


class CurveComparisonWindow(QMainWindow):
    """Fixed exact source A; B is chosen from actual retained result catalogs.

    ``relevant`` optionally guards the originating editor's owner/job selection.
    The window does not open a solver or apply an input edit. Saving publishes
    the comparisons through A's existing document owner.
    """
    def __init__(self, client, *, source, relevant=None, parent=None):
        super().__init__(parent)
        if (not isinstance(source, dict) or not {'document_id', 'job_id', 'response'} <= set(source)
                or set(source) - {'document_id', 'job_id', 'response', 'input_revision', 'input_sha256'}):
            raise ValueError('Choose an exact source document, retained job and response')
        self.client, self.source = client, deepcopy(source)
        self._parent_relevant = relevant
        self.document = None
        self._session = None
        self._busy = self._accepting = self._closed = False
        self._queue, self._worker = [], None
        self._serial = 0
        self._comparison = None
        self._save_request = None
        self._build()
        QTimer.singleShot(0, self.refresh)

    def _build(self):
        self.setWindowTitle('Retained curve comparison — ' + self.source['response'])
        self.resize(1320, 900)
        root = QWidget(); layout = QVBoxLayout(root)
        self.source_label = QLabel('A · ' + json.dumps(self.source, ensure_ascii=False))
        self.source_label.setWordWrap(True); layout.addWidget(self.source_label)
        row = QHBoxLayout()
        self.documents = QComboBox(); self.documents.setObjectName('comparison_document_b')
        self.jobs = QComboBox(); self.jobs.setObjectName('comparison_job_b')
        self.responses = QComboBox(); self.responses.setObjectName('comparison_response_b')
        for label, widget in [('B document', self.documents), ('Retained job', self.jobs), ('Response', self.responses)]:
            row.addWidget(QLabel(label)); row.addWidget(widget, 1)
        layout.addLayout(row)
        row = QHBoxLayout()
        self.refresh_button = QPushButton('Refresh retained sources')
        self.compare_button = QPushButton('Compare selected curves')
        self.save_button = QPushButton('Save analysis in A document')
        self.retry_save = QPushButton('Retry Save receipt'); self.retry_save.hide()
        for button in (self.refresh_button, self.compare_button, self.save_button, self.retry_save):
            row.addWidget(button)
        layout.addLayout(row)
        row = QHBoxLayout()
        self.saved = QComboBox(); self.saved.setObjectName('retained_comparisons')
        row.addWidget(QLabel('Retained comparisons')); row.addWidget(self.saved, 1)
        self.start = QSpinBox(); self.start.setRange(0, 2_000_000_000); self.start.setObjectName('comparison_page_start')
        self.count = QSpinBox(); self.count.setRange(1, 4096); self.count.setValue(512)
        self.count.setObjectName('comparison_page_count')
        self.page_button = QPushButton('Read page')
        self.previous = QPushButton('Previous'); self.next = QPushButton('Next')
        for label, widget in [('Start', self.start), ('Count', self.count)]:
            row.addWidget(QLabel(label)); row.addWidget(widget)
        for button in (self.previous, self.next, self.page_button): row.addWidget(button)
        layout.addLayout(row)
        self.detail = QPlainTextEdit(); self.detail.setReadOnly(True); self.detail.setMaximumHeight(160)
        layout.addWidget(self.detail)
        split = QSplitter(Qt.Orientation.Vertical)
        figure = Figure(); self.axes = figure.add_subplot(111)
        self.canvas = FigureCanvasQTAgg(figure); split.addWidget(self.canvas)
        self.values = QTableWidget(0, 7)
        self.values.setHorizontalHeaderLabels(['Comparison index', 'Original A row', 'Axis', 'A value', 'Aligned B', 'Comparable', 'B − A'])
        self.values.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.values.setAlternatingRowColors(True); self.values.horizontalHeader().setStretchLastSection(True)
        split.addWidget(self.values); split.setSizes([420, 240]); layout.addWidget(split, 1)
        self.message = QLabel('Reading retained source A…'); self.message.setWordWrap(True); layout.addWidget(self.message)
        self.setCentralWidget(root)
        self.refresh_button.clicked.connect(self.refresh)
        self.documents.currentIndexChanged.connect(self._document_selected)
        self.jobs.currentIndexChanged.connect(self._job_selected)
        self.responses.currentIndexChanged.connect(self._selection_changed)
        self.saved.currentIndexChanged.connect(self._comparison_selected)
        self.compare_button.clicked.connect(self.compare)
        self.save_button.clicked.connect(self.save)
        self.retry_save.clicked.connect(self.retry_save_receipt)
        self.page_button.clicked.connect(self.read_page)
        self.previous.clicked.connect(lambda: self._move_page(-1))
        self.next.clicked.connect(lambda: self._move_page(1))
        self._actions()

    def _valid(self):
        return not self._closed and (self._parent_relevant is None or self._parent_relevant())

    def _key(self):
        return (self._session, self._serial, self.documents.currentData(), self.jobs.currentData(), self.responses.currentData())

    def _actions(self):
        available = not self._busy and self._valid()
        for widget in (self.documents, self.jobs, self.responses, self.saved, self.start, self.count, self.refresh_button):
            widget.setEnabled(available)
        self.compare_button.setEnabled(available and self.document is not None and self.responses.currentData() is not None and self._save_request is None)
        self.save_button.setEnabled(available and self.document is not None and self._save_request is None)
        self.retry_save.setVisible(self._save_request is not None)
        self.retry_save.setEnabled(available and self._save_request is not None)
        for button in (self.page_button, self.previous, self.next):
            button.setEnabled(available and self.saved.currentData() is not None)

    def _call(self, function, accepted, *, relevant=None):
        if self._busy:
            if self._accepting:
                self._queue.append((function, accepted, relevant)); return True
            self.message.setText('A retained-data request is in progress. Wait for its receipt.'); return False
        if not self._valid():
            self.message.setText('The originating document or result selection changed. Open a comparison from the current result.'); return False
        if relevant is not None and not relevant(): return False
        self._busy = True; self._actions()
        worker = self._worker = _Read(function)
        def finished(value, error):
            self._accepting = True
            try:
                if self._valid() and (relevant is None or relevant()):
                    if error: self.message.setText('Request failed; retained data and selections preserved. ' + error)
                    else: accepted(value)
            finally:
                self._accepting = False; self._busy = False; self._worker = None
            self._actions()
            if self._queue:
                request = self._queue.pop(0)
                self._call(request[0], request[1], relevant=request[2])
        worker.signals.finished.connect(finished, Qt.ConnectionType.QueuedConnection)
        QThreadPool.globalInstance().start(worker); return True

    def _accept_owner(self, document):
        if document.get('id') != self.source['document_id'] or document.get('kind') not in KINDS:
            self.message.setText('Comparison receipt belongs to a different domain owner.'); return False
        if self._session is not None and document.get('session_id') != self._session:
            self.message.setText('Source A session changed. Reopen the owner; unresolved receipts are retained.'); return False
        run = next((r for r in document.get('runs', []) if r['job_id'] == self.source['job_id']), None)
        if run is None or any(key in self.source and run.get(key) != self.source[key] for key in ('input_revision', 'input_sha256')):
            self.message.setText('Exact source A run no longer matches this comparison window.'); return False
        self._session = document['session_id']; self.document = deepcopy(document)
        selected = self.saved.currentData()
        self.saved.blockSignals(True); self.saved.clear()
        for item in document.get('comparisons', []):
            binding = item.get('binding', {})
            if not _matches(binding.get('source'), self.source): continue
            b = binding.get('prediction_source', {}); metrics = item.get('metrics', {})
            self.saved.addItem(f"{b.get('document_id')} / {b.get('job_id')} / {b.get('response')} · RMSE {metrics.get('rmse', '?')} {metrics.get('unit', '?')}" + (' · saved' if item.get('retained_revision') else ' · unsaved'), item['id'])
        index = self.saved.findData(selected)
        if index >= 0: self.saved.setCurrentIndex(index)
        self.saved.blockSignals(False)
        return True

    def refresh(self):
        key = self._key()
        selected_b = (self.documents.currentData(), self.jobs.currentData(), self.responses.currentData())
        def accepted(payload):
            document, listing = payload
            if not self._accept_owner(document): return
            selected = self.documents.currentData()
            self.documents.blockSignals(True); self.documents.clear()
            for row in listing['documents']:
                if row.get('kind') in KINDS:
                    self.documents.addItem(row.get('title', row['id']) + ' · ' + row['id'], row['id'])
            index = self.documents.findData(selected)
            if index >= 0: self.documents.setCurrentIndex(index)
            self.documents.blockSignals(False)
            self.message.setText('Choose an exact B curve, or reopen a retained comparison. No calculation is submitted.')
            self._document_selected(prefer_job=selected_b[1] if self.documents.currentData() == selected_b[0] else None,
                                    prefer_response=selected_b[2] if self.documents.currentData() == selected_b[0] else None)
            if self.saved.currentData() is not None: self.read_page()
        return self._call(lambda: (self.client.document_read(self.source['document_id']), self.client.documents()), accepted, relevant=lambda: self._key() == key)

    def _selection_changed(self, *_):
        self._serial += 1; self._actions()

    def _document_selected(self, *_, prefer_job=None, prefer_response=None):
        self._selection_changed(); identifier = self.documents.currentData()
        self.jobs.blockSignals(True); self.jobs.clear(); self.jobs.blockSignals(False)
        self.responses.blockSignals(True); self.responses.clear(); self.responses.blockSignals(False)
        if identifier is None: return
        key = self._key()
        def accepted(document):
            if document.get('id') != identifier or document.get('session_id') != self._session:
                self.message.setText('B document identity/session changed; refresh sources.'); return
            self.jobs.blockSignals(True)
            for run in document.get('runs', []):
                # The result metadata performs the final actual-status check.
                self.jobs.addItem(run['job_id'] + ' · ' + run.get('input_revision', ''), run['job_id'])
            index = self.jobs.findData(prefer_job)
            if index >= 0: self.jobs.setCurrentIndex(index)
            self.jobs.blockSignals(False); self._job_selected(prefer_response=prefer_response)
        self._call(lambda: self.client.document_read(identifier), accepted, relevant=lambda: self._key() == key)

    def _job_selected(self, *_, prefer_response=None):
        self._selection_changed()
        self.responses.blockSignals(True); self.responses.clear(); self.responses.blockSignals(False)
        document, job = self.documents.currentData(), self.jobs.currentData()
        if document is None or job is None: return
        key = self._key()
        def accepted(metadata):
            if metadata.get('execution_counts', {}).get('SUCCEEDED', 0) != 1 or metadata.get('execution_counts', {}).get('PREDICTED', 0):
                self.message.setText('B must be an actual successful retained evaluation.'); return
            self.responses.blockSignals(True)
            for choice in response_choices(metadata):
                if choice['definition'].get('kind', 'series') == 'series':
                    self.responses.addItem(choice['label'], choice['selector'])
            index = self.responses.findData(prefer_response)
            if index >= 0: self.responses.setCurrentIndex(index)
            self.responses.blockSignals(False); self._selection_changed()
            if not self.responses.count(): self.message.setText('This retained result advertises no selectable curve.')
        self._call(lambda: self.client.document_result_metadata(document, job), accepted, relevant=lambda: self._key() == key)

    def compare(self):
        if self._save_request is not None: return
        b = dict(document_id=self.documents.currentData(), job_id=self.jobs.currentData(), response=self.responses.currentData())
        if any(value is None for value in b.values()): return
        key = self._key(); source = deepcopy(self.source)
        def accepted(payload):
            if not _matches(payload.get('binding', {}).get('source'), source) or not _matches(payload.get('binding', {}).get('prediction_source'), b):
                self.message.setText('Comparison reply identity differs from the explicitly selected curves.'); return
            self._display(payload)
            def owner_read(document):
                if self._accept_owner(document):
                    self.saved.blockSignals(True); self.saved.setCurrentIndex(self.saved.findData(payload['id'])); self.saved.blockSignals(False)
                    self.message.setText('Actual comparison retained in A. Save analysis to publish it with this document.')
                    self.start.setValue(0); self.read_page()
            self._call(lambda: self.client.document_read(source['document_id']), owner_read, relevant=lambda: self._key() == key)
        session = self._session
        def retained_compare():
            if self.client.document_read(source['document_id']).get('session_id') != session:
                raise ValueError('Source A session changed; reopen before comparing')
            return self.client.document_compare(source, b)
        return self._call(retained_compare, accepted, relevant=lambda: self._key() == key)

    def _comparison_selected(self, *_):
        self.start.setValue(0); self.read_page()

    def _move_page(self, direction):
        self.start.setValue(max(0, self.start.value() + direction * self.count.value())); self.read_page()

    def read_page(self):
        identifier = self.saved.currentData()
        if identifier is None: return
        start, count = self.start.value(), self.count.value(); session = self._session
        def accepted(payload):
            if payload.get('id') != identifier or not _matches(payload.get('binding', {}).get('source'), self.source):
                self.message.setText('Stored comparison identity differs from source A.'); return
            self._display(payload)
        def retained_page():
            if self.client.document_read(self.source['document_id']).get('session_id') != session:
                raise ValueError('Source A session changed; reopen before reading its comparison')
            return self.client.document_comparison(self.source['document_id'], identifier, start=start, count=count)
        return self._call(retained_page, accepted,
            relevant=lambda: self._session == session and self.saved.currentData() == identifier and (self.start.value(), self.count.value()) == (start, count))

    def _display(self, payload):
        comparison = payload['comparison']; observation = comparison['observation']; page = payload['page']
        axes = observation.get('axes', [])
        if observation.get('kind') != 'series' or len(axes) != 1:
            self.message.setText('Stored comparison does not contain one declared curve axis.'); return
        a, b, mask = observation['value'], comparison['prediction'], comparison['mask']
        x = axes[0]['values']; size = len(a)
        if not (len(x) == len(b) == len(mask) == size <= 4096 and size == page['count']):
            self.message.setText('Invalid or unbounded comparison page; previous view preserved.'); return
        rows = comparison.get('observation_source_rows') or observation.get('source_rows', [])
        if rows and len(rows) != size:
            self.message.setText('Original row identity does not match the comparison page.'); return
        a_mask = observation.get('mask', [True] * size)
        if len(a_mask) != size:
            self.message.setText('Original A validity mask does not match the comparison page; previous view preserved.'); return
        self._comparison = deepcopy(payload)
        self.detail.setPlainText(json.dumps({'comparison_id': payload['id'], 'binding': payload['binding'],
            'method': comparison.get('method'), 'alignment_policy': comparison.get('alignment_policy'),
            'unit': comparison.get('unit'), 'rmse': comparison.get('rmse'), 'count': comparison.get('count'),
            'A_declarations': {k: observation[k] for k in ('component', 'location', 'measure', 'frame') if k in observation},
            'B_declarations': comparison.get('prediction_metadata', {}), 'page': page}, ensure_ascii=False, indent=2))
        self.values.setRowCount(size)
        for i in range(size):
            delta = b[i] - a[i] if mask[i] and _number(a[i]) and _number(b[i]) else None
            entries = [page['start'] + i, rows[i] if rows else None, x[i], a[i], b[i], bool(mask[i]), delta]
            for column, value in enumerate(entries):
                self.values.setItem(i, column, QTableWidgetItem('—' if value is None else str(value)))
        self.axes.clear()
        segments = comparison.get('observation_segments') or observation.get('segments') or [{'rows': [page['start'], page['start'] + size]}]
        for series, values, valid, color in [('A retained values', a, a_mask, 'C0'), ('B aligned to A', b, mask, 'C1')]:
            labelled = False
            for segment in segments:
                low, high = segment['rows']; low = max(0, low - page['start']); high = min(size, high - page['start'])
                if low >= high: continue
                y = [values[i] if i < len(valid) and valid[i] and _number(values[i]) else math.nan for i in range(low, high)]
                self.axes.plot(x[low:high], y, marker='.', color=color, label=None if labelled else series)
                labelled = True
        self.axes.set_xlabel(str(axes[0].get('name', '?')) + ' [' + str(axes[0].get('unit', '?')) + ']')
        self.axes.set_ylabel('[' + str(observation.get('unit', '?')) + ']')
        if self.axes.lines: self.axes.legend()
        self.axes.grid(True, alpha=.2); self.canvas.draw_idle()
        self.message.setText(f"Retained comparison · samples {page['start']}–{page['start'] + size} of {page['total']}. Gaps remain gaps; B − A is shown only for comparable samples.")

    def save(self):
        if self._save_request is not None: return
        session = self._session
        def accepted(document):
            if not self._accept_owner(document) or document['session_id'] != session: return
            self._save_request = dict(identifier=self.source['document_id'], operation='document.save', arguments={},
                session_id=session, expected_generation=document['generation'], command_id='C' + uuid.uuid4().hex)
            self._send_save()
        return self._call(lambda: self.client.document_read(self.source['document_id']), accepted)

    def _send_save(self):
        request = deepcopy(self._save_request)
        def accepted(receipt):
            if receipt.get('command_id') != request['command_id'] or not self._accept_owner(receipt.get('document', {})):
                self.message.setText('Save receipt identity is unconfirmed. The exact pending request is retained.'); return
            self._save_request = None
            self.message.setText('Comparison analysis saved in the original A document. Reopening reads retained curves without calculation.')
        return self._call(lambda: self.client.document_command(**request), accepted)

    def retry_save_receipt(self):
        if self._save_request is None: return
        request = deepcopy(self._save_request)
        def accepted(document):
            if document.get('session_id') != request['session_id'] or document.get('id') != request['identifier']:
                self.message.setText('Save receipt remains unresolved after an owner/session change. No rebased Save was submitted.'); return
            self._send_save()
        return self._call(lambda: self.client.document_read(request['identifier']), accepted)

    def closeEvent(self, event):
        self._closed = True; self._queue.clear(); super().closeEvent(event)
