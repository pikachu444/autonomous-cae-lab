"""Explicit measured-column selection; no native/evaluator command runs here."""
from copy import deepcopy
import json
import math

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog,
    QDialogButtonBox, QFormLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QSplitter, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure

from caelab.post_observation import choices, measurement_columns, project_samples


class MeasurementDialog(QDialog):
    def __init__(self, snapshot, parent=None):
        super().__init__(parent)
        self.snapshot = deepcopy(snapshot)
        self.selection = None
        self.projected = None
        self.setWindowTitle('Use measured curve in Numerical')
        self.resize(1100, 780)
        outer = QVBoxLayout(self)
        self.summary = QLabel('Saved ' + str(snapshot['summary'].get('measurement', '')) +
            ' measurement. Select the actual native column and axis.')
        outer.addWidget(self.summary)
        forms = QHBoxLayout()
        left, right = QFormLayout(), QFormLayout()
        forms.addLayout(left, 1)
        forms.addLayout(right, 1)
        outer.addLayout(forms)
        available = choices(snapshot)
        measured = measurement_columns(snapshot)
        self.block, self.value_column, self.axis_column = QComboBox(), QComboBox(), QComboBox()
        for block in available['blocks']:
            self.block.addItem('Block ' + str(block) if block else 'Point dataset', block)
        for combo in (self.value_column, self.axis_column):
            combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            combo.setMinimumContentsLength(28)
            combo.addItem('Choose actual column…', None)
        for name, count in available['arrays'].items():
            components = range(count) if count > 1 else [None]
            for component in components:
                label = name + (' [component ' + str(component) + ']' if component is not None else ' [scalar]')
                if name in measured:
                    self.value_column.addItem(label, {'name': name, 'component': component})
                measurement = snapshot['summary'].get('measurement')
                if name == {'time': 'Time', 'path': 'arc_length'}.get(measurement) and component is None:
                    self.axis_column.addItem(label, {'kind': 'array', 'name': name, 'component': component})
        if available['coordinates'] and snapshot['summary'].get('measurement') != 'time':
            for component, label in enumerate(('X coordinate', 'Y coordinate', 'Z coordinate')):
                self.axis_column.addItem(label, {'kind': 'coordinate', 'component': component})
        if available['point_index'] and snapshot['summary'].get('measurement') != 'time':
            self.axis_column.addItem('Native output point index', {'kind': 'point_index'})
        self.role = QComboBox()
        self.role.addItem('Fit observation', 'fit')
        self.role.addItem('Holdout baseline', 'holdout')
        left.addRow('Native block', self.block)
        left.addRow('Value / component / statistic', self.value_column)
        left.addRow('Axis', self.axis_column)
        left.addRow('Use as', self.role)
        self.fields = {}
        summary = snapshot['summary']
        defaults = {'unit': summary.get('units'), 'frame': summary.get('frame'),
                    'measure': summary.get('measure'),
                    'axis_name': 'time' if summary.get('measurement') == 'time' else '',
                    'axis_unit': summary.get('time_units') if summary.get('measurement') == 'time' else summary.get('coordinate_units'),
                    'component_label': '', 'location': ''}
        labels = {'unit': 'Response unit', 'component_label': 'Physical component / statistic',
                  'location': 'Measured location', 'frame': 'Response frame', 'measure': 'Physical measure',
                  'axis_name': 'Axis name', 'axis_unit': 'Axis unit'}
        for key, label in labels.items():
            edit = QLineEdit(defaults.get(key) or '', self)
            edit.setObjectName('measurement_' + key)
            edit.textChanged.connect(self.update_preview)
            self.fields[key] = edit
            known = key in ('unit', 'frame', 'measure', 'axis_unit', 'axis_name') and bool(defaults.get(key))
            edit.setReadOnly(known)
            if known:
                edit.hide()
            else:
                right.addRow(label, edit)
        self.declarations = QLabel()
        self.declarations.setWordWrap(True)
        right.addRow(self.declarations)
        self.exclude_invalid = QCheckBox('Exclude invalid rows from calculation; keep all rows visible')
        self.exclude_invalid.setObjectName('excludeInvalidMeasurementRows')
        outer.addWidget(self.exclude_invalid)
        self.notice = QLabel()
        self.notice.setWordWrap(True)
        outer.addWidget(self.notice)
        split = QSplitter(Qt.Orientation.Horizontal)
        self.table = QTableWidget(0, 5)
        self.table.setObjectName('measuredSamples')
        self.table.setHorizontalHeaderLabels(['Native row', 'Axis', 'Value', 'State', 'Reason'])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        for col, width in enumerate((95, 90, 110, 80, 140)):
            self.table.setColumnWidth(col, width)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.itemSelectionChanged.connect(self.highlight)
        split.addWidget(self.table)
        self.figure = Figure(figsize=(5, 4))
        self.canvas = FigureCanvasQTAgg(self.figure)
        split.addWidget(self.canvas)
        split.setSizes([540, 540])
        outer.addWidget(split, 1)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText('Create new Plan')
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        outer.addWidget(self.buttons)
        for combo in (self.block, self.value_column, self.axis_column, self.role):
            combo.currentIndexChanged.connect(self.update_preview)
        self.exclude_invalid.toggled.connect(self.update_preview)
        self.canvas.mpl_connect('pick_event', self.picked)
        self.update_preview()

    def selected_mapping(self):
        value, axis = self.value_column.currentData(), self.axis_column.currentData()
        if value is None or axis is None:
            raise ValueError('Select an exact value column/component and its axis.')
        return {'block': self.block.currentData(), 'value_array': value['name'],
                'value_component': value['component'], 'axis': axis,
                **{key: edit.text() for key, edit in self.fields.items()},
                'role': self.role.currentData(), 'exclude_invalid': self.exclude_invalid.isChecked()}

    def update_preview(self, *_):
        if not hasattr(self, 'buttons'):
            return
        self.selection = self.projected = None
        axis = self.axis_column.currentData()
        if axis:
            summary = self.snapshot['summary']
            if axis['kind'] == 'point_index':
                declarations = {'axis_name': 'output point index', 'axis_unit': '1'}
            elif axis['kind'] == 'coordinate':
                declarations = {'axis_name': ('X', 'Y', 'Z')[axis['component']], 'axis_unit': summary.get('coordinate_units') or ''}
            elif axis.get('name') == 'Time':
                declarations = {'axis_name': 'time', 'axis_unit': summary.get('time_units') or ''}
            elif axis.get('name') == 'arc_length':
                declarations = {'axis_name': 'arc length', 'axis_unit': summary.get('coordinate_units') or ''}
            else:
                declarations = {}
            for key, value in declarations.items():
                if value:
                    self.fields[key].blockSignals(True)
                    self.fields[key].setText(value)
                    self.fields[key].setReadOnly(True)
                    self.fields[key].blockSignals(False)
        self.declarations.setText(' / '.join(
            str(self.fields[key].text()) for key in ('unit', 'frame', 'measure') if self.fields[key].text()) +
            '\nAxis: ' + self.fields['axis_name'].text() + ' [' + self.fields['axis_unit'].text() + ']')
        try:
            selection = self.selected_mapping()
            projection = project_samples(self.snapshot, selection)
            self.selection, self.projected = selection, projection
            self.notice.setText(str(len(projection['rows'])) + ' actual samples; ' +
                str(len(projection['invalid_rows'])) + ' invalid. No resampling or unit conversion.')
            self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(projection['importable'])
            rows = projection['rows']
        except (ValueError, TypeError, KeyError) as error:
            self.notice.setText(str(error))
            self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)
            # Keep the actual native table visible while completing its mapping.
            rows = [{'native': {'block': row.get('block'), 'row': row.get('row', row.get('point_index'))},
                     'axis': None, 'value': row['values'], 'valid': None, 'reason': ''}
                    for row in self.snapshot['rows'] if row.get('block', []) == self.block.currentData()]
        self.table.setRowCount(len(rows))
        for index, row in enumerate(rows):
            for column, value in enumerate((row['native'], row['axis'], row['value'],
                                            'Valid' if row['valid'] else 'Invalid' if row['valid'] is False else 'Unmapped',
                                            row['reason'])):
                text = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else '' if value is None else str(value)
                item = QTableWidgetItem(text)
                item.setToolTip(text)
                self.table.setItem(index, column, item)
        self.draw()

    def draw(self):
        self.figure.clear()
        self.axes = self.figure.add_subplot(111)
        if self.projected:
            rows = self.projected['rows']
            self.axes.plot([row['axis'] if isinstance(row['axis'], (int, float)) else math.nan for row in rows],
                           [row['value'] if row['valid'] else math.nan for row in rows],
                           marker='o', markersize=4, picker=6)
            self.axes.set_xlabel(self.selection['axis_name'] + ' [' + self.selection['axis_unit'] + ']')
            self.axes.set_ylabel(self.selection['component_label'] + ' [' + self.selection['unit'] + ']')
            self.axes.grid(True, alpha=.2)
        self.marker = None
        self.figure.tight_layout()
        self.canvas.draw_idle()

    def highlight(self):
        if not hasattr(self, 'axes'):
            return
        if self.marker is not None:
            self.marker.remove()
            self.marker = None
        row = self.table.currentRow()
        if self.projected and 0 <= row < len(self.projected['rows']):
            selected = self.projected['rows'][row]
            if selected['valid']:
                self.marker, = self.axes.plot([selected['axis']], [selected['value']], 'o', color='#c55324', markersize=8)
        self.canvas.draw_idle()

    def picked(self, event):
        if len(getattr(event, 'ind', [])):
            self.table.selectRow(int(event.ind[0]))
            self.table.scrollToItem(self.table.item(int(event.ind[0]), 0))
