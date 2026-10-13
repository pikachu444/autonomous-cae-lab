"""Read-only presentation of the existing exact research-reference payload."""
from copy import deepcopy
from html import escape
import json
import math

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QComboBox, QHBoxLayout, QLabel, QPushButton,
    QSplitter, QTabWidget, QTextBrowser, QVBoxLayout, QWidget)
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from .runner_window import readonly_table, table_row, text_value
from .discussion_view import turn_text, author_label


class ReferenceContent(QWidget):
    response_requested = Signal(str)
    def __init__(self, parent=None):
        super().__init__(parent)
        self.payload = None
        self._rows = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.title = QLabel('Evidence')
        self.title.setWordWrap(True)
        font = self.title.font(); font.setBold(True); self.title.setFont(font)
        layout.addWidget(self.title)
        choices = QHBoxLayout()
        self.channel = QComboBox(); self.channel.setObjectName('evidenceChannel')
        self.channel.currentIndexChanged.connect(self._draw_result)
        self.read = QPushButton('Read response')
        self.read.clicked.connect(lambda: self.response_requested.emit(str(self.channel.currentData())))
        self.candidate = QComboBox(); self.candidate.setObjectName('evidenceCandidate')
        self.candidate.currentIndexChanged.connect(self._draw_result)
        choices.addWidget(self.channel, 2); choices.addWidget(self.read)
        choices.addWidget(self.candidate, 1)
        layout.addLayout(choices)
        self.body = QTextBrowser()
        self.body.setObjectName('evidenceBody')
        self.body.setOpenExternalLinks(False)
        self.body.setOpenLinks(False)
        self.body.setMinimumHeight(120)
        self.result_views = QTabWidget()
        self.figure = Figure(figsize=(6, 3), tight_layout=True)
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.axes = self.figure.add_subplot(111)
        self.values = readonly_table(['Position', 'Value', 'Unit', 'Included'])
        self.values.setObjectName('evidenceValues')
        self.result_views.addTab(self.canvas, 'Curve')
        self.result_views.addTab(self.values, 'Values')
        layout.addWidget(self.body, 1)
        layout.addWidget(self.result_views, 2)
        self.clear('Select evidence to read its content.')

    def clear(self, message=''):
        self.payload = None
        self.title.setText('Evidence')
        self.body.setPlainText(message)
        self.body.show()
        for widget in (self.channel, self.read, self.candidate, self.result_views):
            widget.hide()
        self.values.setRowCount(0)
        self.axes.clear()
        self.canvas.draw_idle()

    def set_payload(self, payload, *, label='Evidence'):
        self.clear()
        self.payload = deepcopy(payload)
        self.title.setText(label)
        if payload.get('status') != 'AVAILABLE':
            self.body.setPlainText(str(payload.get('message') or 'Source unavailable'))
            return
        kind = payload.get('kind')
        if kind == 'expert_turn':
            turn = payload['turn']
            self.title.setText(author_label(turn) + ' — ' + str((turn.get('topic') or {}).get('title', label)))
            self.body.setPlainText(turn_text(turn))
            return
        if kind == 'document':
            document = payload['document']
            self.title.setText(document.get('title', label))
            draft = document.get('draft', {})
            texts = []
            for key in ('question', 'purpose', 'description', 'notes'):
                if isinstance(draft.get(key), str) and draft[key]:
                    texts.append(draft[key])
            if isinstance(draft.get('composer'), dict) and draft['composer'].get('text'):
                texts.append(draft['composer']['text'])
            self.body.setPlainText('\n\n'.join(texts) or 'Open the original tool to inspect this saved model.')
            return
        if kind == 'job':
            job = payload.get('job') or {}
            self.title.setText('Calculation status')
            self.body.setPlainText(str(job.get('state', job.get('status', 'UNKNOWN'))) +
                '\n' + str(job.get('operation', '')) + '\n' + str(job.get('error') or ''))
            return
        if kind != 'result':
            self.body.setPlainText('This reference has no supported content view.')
            return
        metadata = payload.get('metadata') or {}
        self.channel.blockSignals(True)
        self.channel.clear()
        for item in metadata.get('responses', []):
            name = item.get('response')
            if name:
                self.channel.addItem(name + ' [' + str(item.get('unit', 'unit unavailable')) + ']', name)
        for name, item in metadata.get('native_channels', {}).items():
            if not item.get('requires_location') and self.channel.findData(name) < 0:
                self.channel.addItem(name + ' [' + str(item.get('unit', 'unit unavailable')) + ']', name)
        result = payload.get('result') or {}
        self._result = result
        self._rows = result.get('candidates', result.get('predictions', []))
        for row in ([result] + self._rows):
            for name, response in (row.get('responses') or {}).items():
                if self.channel.findData(name) < 0:
                    self.channel.addItem(name + ' [' + str(response.get('unit', 'unit unavailable')) + ']', name)
        self.channel.blockSignals(False)
        self.channel.setVisible(self.channel.count() > 0)
        self.read.setVisible(self.channel.count() > 0)
        self.candidate.blockSignals(True)
        self.candidate.clear()
        for index, row in enumerate(self._rows):
            self.candidate.addItem('Candidate ' + str(index + 1) + ' — ' +
                str(row.get('execution_status', row.get('prediction_status', 'UNKNOWN'))), index)
        self.candidate.blockSignals(False)
        self.candidate.setVisible(bool(self._rows))
        self._draw_result()

    def _draw_result(self, *_):
        if not self.payload or self.payload.get('kind') != 'result':
            return
        source = self._rows[max(0, self.candidate.currentIndex())] if self._rows else self._result
        responses = source.get('responses') or {}
        if not responses:
            reason = source.get('failure_reason') or source.get('error') or 'Choose a response to read its values.'
            self.body.setPlainText(str(reason))
            self.body.show(); self.result_views.hide()
            return
        # A previously selected exact response remains the displayed response.
        name = self.channel.currentData()
        if name not in responses:
            name = next(iter(responses))
        response = responses[name]
        unit = str(response.get('unit', 'unit unavailable'))
        labels = [str(response[key]) for key in ('component', 'frame', 'measure')
                  if isinstance(response.get(key), (str, int, float))]
        location = response.get('location')
        if isinstance(location, str):
            labels.append(location)
        elif isinstance(location, dict) and isinstance(location.get('label'), str):
            labels.append(location['label'])
        self.title.setText(name + ' [' + unit + ']' + (' — ' + ' / '.join(labels) if labels else ''))
        self.result_views.show()
        self.values.setRowCount(0)
        self.axes.clear()
        value = response.get('value')
        if response.get('kind') == 'scalar':
            self.values.setRowCount(1)
            table_row(self.values, 0, ['Scalar', text_value(value), unit,
                'Invalid' if response.get('valid') is False else ''])
            self.body.setPlainText(text_value(value) + ' ' + unit)
            self.body.show()
            self.result_views.setCurrentWidget(self.values)
            return
        axes = response.get('axes') or []
        if (response.get('kind') != 'series' or not isinstance(value, list) or len(axes) != 1
                or not isinstance(axes[0].get('values'), list) or len(axes[0]['values']) != len(value)):
            self.body.setPlainText('This field needs its original result viewer and an explicit location. Open original tool.')
            self.body.show(); self.result_views.hide()
            return
        axis, mask = axes[0], response.get('mask')
        if mask is not None and (not isinstance(mask, list) or len(mask) != len(value)
                                 or any(type(item) is not bool for item in mask)):
            self.body.setPlainText('Invalid saved mask. Open the original result; no curve is drawn.')
            self.body.show(); self.result_views.hide()
            return
        self.values.setRowCount(len(value))
        plotted_x, plotted_y = [], []
        for index, (x, y) in enumerate(zip(axis['values'], value)):
            included = mask[index] if mask is not None else None
            table_row(self.values, index, [text_value(x) + ' ' + str(axis.get('unit', '')),
                text_value(y), unit, included if included is not None else 'Not supplied'])
            finite = (type(x) in (int, float) and type(y) in (int, float)
                      and math.isfinite(x) and math.isfinite(y))
            plotted_x.append(x if finite else math.nan)
            plotted_y.append(y if finite and included is not False and response.get('valid') is not False else math.nan)
        self.axes.plot(plotted_x, plotted_y, marker='o', markersize=3)
        self.axes.set_xlabel(str(axis.get('name', 'Position')) + ' [' + str(axis.get('unit', 'unit unavailable')) + ']')
        self.axes.set_ylabel(name + ' [' + unit + ']')
        self.axes.grid(True, alpha=.2)
        self.canvas.draw_idle()
        self.body.setPlainText('Saved samples; gaps retain missing or excluded values.' if
            any(not math.isfinite(item) for item in plotted_y) else '')
        self.body.setVisible(bool(self.body.toPlainText()))
        self.result_views.setCurrentWidget(self.canvas)
