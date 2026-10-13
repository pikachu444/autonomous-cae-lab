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
    def __init__(self, snapshot, parent=None, *, plans=()):
        super().__init__(parent)
        self.snapshot = deepcopy(snapshot)
        self.selection = None
        self._last_axis = None
        self.projected = None
        self.setWindowTitle('측정 곡선을 계산 계획으로 보내기')
        self.resize(1100, 780)
        outer = QVBoxLayout(self)
        self.summary = QLabel('저장된 측정에서 응답 열과 곡선의 축을 선택하세요.')
        self.summary.setProperty('appearanceRole', 'section')
        if snapshot['summary'].get('measurement') == 'contact_force':
            self.summary.setText(snapshot['summary'].get('location', '').split(' / ')[0] +
                ': ' + snapshot['summary'].get('component_label', '') + ' A 면 합력 [N]')
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
            self.block.addItem('자료 블록 ' + str(block) if block else '점 자료', block)
        for combo in (self.value_column, self.axis_column):
            combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            combo.setMinimumContentsLength(22)
            combo.addItem('열 선택…', None)
        for name, count in available['arrays'].items():
            components = range(count) if count > 1 else [None]
            for component in components:
                label = name + (' [성분 ' + str(component) + ']' if component is not None else '')
                if name in measured:
                    self.value_column.addItem(label, {'name': name, 'component': component})
                measurement = snapshot['summary'].get('measurement')
                if name == {'time': 'Time', 'path': 'arc_length', 'contact_force': 'load_parameter'}.get(measurement) and component is None:
                    self.axis_column.addItem(label, {'kind': 'array', 'name': name, 'component': component})
        if available['coordinates'] and snapshot['summary'].get('measurement') != 'time':
            for component, label in enumerate(('X 좌표', 'Y 좌표', 'Z 좌표')):
                self.axis_column.addItem(label, {'kind': 'coordinate', 'component': component})
        if available['point_index'] and snapshot['summary'].get('measurement') != 'time':
            self.axis_column.addItem('원 결과 점 번호', {'kind': 'point_index'})
        self.role = QComboBox()
        self.role.addItem('피팅 관측값', 'fit')
        self.role.addItem('검증용 관측값', 'holdout')
        self.destination = QComboBox()
        self.destination.setObjectName('measurementDestination')
        self.destination.addItem('새 계산 계획', None)
        for plan in plans:
            self.destination.addItem(plan['title'], plan['id'])
        self.destination.currentIndexChanged.connect(self.update_preview)
        left.addRow('계산 계획', self.destination)
        left.addRow('자료 블록', self.block)
        left.addRow('응답 열과 성분', self.value_column)
        left.addRow('곡선의 축', self.axis_column)
        left.addRow('사용 목적', self.role)
        if len(available['blocks']) == 1:
            self.block.hide()
            left.labelForField(self.block).hide()
        self.fields = {}
        summary = snapshot['summary']
        defaults = {'unit': summary.get('units'), 'frame': summary.get('frame'),
                    'measure': summary.get('measure'),
                    'axis_name': summary.get('axis_name') or ('time' if summary.get('measurement') == 'time' else ''),
                    'axis_unit': summary.get('axis_unit') or (summary.get('time_units') if summary.get('measurement') == 'time' else summary.get('coordinate_units')),
                    'component_label': summary.get('component_label', ''), 'location': summary.get('location', '')}
        labels = {'unit': '응답 단위', 'component_label': '물리 성분 또는 통계량',
                  'location': '측정 위치', 'frame': '응답 좌표계', 'measure': '물리적 정의',
                  'axis_name': '축 이름', 'axis_unit': '축 단위'}
        for key, label in labels.items():
            edit = QLineEdit(defaults.get(key) or '', self)
            edit.setObjectName('measurement_' + key)
            edit.textChanged.connect(self.update_preview)
            self.fields[key] = edit
            known = (key in ('unit', 'frame', 'measure', 'axis_unit', 'axis_name') or
                     summary.get('measurement') == 'contact_force' and key in ('component_label', 'location')) and bool(defaults.get(key))
            edit.setReadOnly(known)
            if known:
                edit.hide()
            else:
                right.addRow(label, edit)
        self.declarations = QLabel()
        self.declarations.setWordWrap(True)
        right.addRow(self.declarations)
        self.exclude_invalid = QCheckBox('무효 행은 계산에서 제외 (원본 행은 모두 표시)')
        self.exclude_invalid.setObjectName('excludeInvalidMeasurementRows')
        outer.addWidget(self.exclude_invalid)
        self.notice = QLabel()
        self.notice.setWordWrap(True)
        outer.addWidget(self.notice)
        split = QSplitter(Qt.Orientation.Horizontal)
        self.table = QTableWidget(0, 5)
        self.table.setObjectName('measuredSamples')
        self.table.setHorizontalHeaderLabels(['원본 행', '축', '측정값', '유효성', '이유'])
        self.table.verticalHeader().hide()
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
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText('새 계획 만들기')
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setProperty('appearanceRole', 'primary')
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('취소')
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        outer.addWidget(self.buttons)
        for combo in (self.block, self.value_column, self.axis_column, self.role):
            combo.currentIndexChanged.connect(self.update_preview)
        self.exclude_invalid.toggled.connect(self.update_preview)
        self.canvas.mpl_connect('pick_event', self.picked)
        if summary.get('measurement') == 'contact_force':
            # This applied measurement already names one explicit pair component.
            self.value_column.setCurrentIndex(1)
            self.axis_column.setCurrentIndex(1)
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
            elif axis.get('name') == 'load_parameter' and summary.get('measurement') == 'contact_force':
                declarations = {'axis_name': 'load_parameter', 'axis_unit': '1'}
            elif axis.get('name') == 'arc_length':
                declarations = {'axis_name': 'arc length', 'axis_unit': summary.get('coordinate_units') or ''}
            else:
                declarations = {}
            axis_changed = axis != self._last_axis
            for key, value in declarations.items():
                field = self.fields[key]
                field.blockSignals(True)
                if value or axis_changed:
                    field.setText(value)
                field.setReadOnly(bool(value))
                if not value:
                    field.show()
                field.blockSignals(False)
            self._last_axis = deepcopy(axis)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText(
            '계획에서 추가 검토' if self.destination.currentData() else '새 계획 만들기')
        names = {'FREECAD_DOCUMENT_GLOBAL': '문서 전체 좌표계',
                 'contact_pair_force_resultant': '접촉 쌍의 합력'}
        self.declarations.setText(', '.join(names.get(self.fields[key].text(), self.fields[key].text())
            for key in ('unit', 'frame', 'measure') if self.fields[key].text()) +
            '\n축: ' + self.fields['axis_name'].text() + ' [' + self.fields['axis_unit'].text() + ']')
        try:
            selection = self.selected_mapping()
            projection = project_samples(self.snapshot, selection)
            self.selection, self.projected = selection, projection
            self.notice.setText(str(len(projection['rows'])) + '개 원본 행, 무효 ' +
                str(len(projection['invalid_rows'])) + '개. 재표본화와 단위 변환 없이 전달합니다.')
            self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(projection['importable'])
            rows = projection['rows']
            self.table.setColumnCount(5)
            self.table.setHorizontalHeaderLabels(['원본 행', '축', '측정값', '유효성', '이유'])
        except (ValueError, TypeError, KeyError) as error:
            self.notice.setText(str(error))
            self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)
            # Show actual columns while the mapping is incomplete, not JSON in a cell.
            native_rows = [row for row in self.snapshot['rows'] if row.get('block', []) == self.block.currentData()]
            columns = [(name, component) for name, count in choices(self.snapshot)['arrays'].items()
                       for component in (range(count) if count > 1 else [None])]
            self.table.setColumnCount(len(columns) + 1)
            self.table.setHorizontalHeaderLabels(['Row'] + [
                name + (' [' + str(component) + ']' if component is not None else '') for name, component in columns])
            self.table.setRowCount(len(native_rows))
            for index, row in enumerate(native_rows):
                identifier = row.get('row', row.get('point_index'))
                values = [identifier]
                for name, component in columns:
                    value = row['values'].get(name)
                    values.append(value[component] if isinstance(value, list) and component is not None else value)
                for column, value in enumerate(values):
                    item = QTableWidgetItem('' if value is None else str(value))
                    item.setToolTip(json.dumps({'block': row.get('block'), 'row': identifier,
                                                'object': self.snapshot['origin']['object_ref']}) if column == 0 else item.text())
                    self.table.setItem(index, column, item)
                    self.table.setColumnWidth(column, 70 if column == 0 else 140)
            self.draw()
            return
        self.table.setRowCount(len(rows))
        for index, row in enumerate(rows):
            identity = row['native']
            for column, value in enumerate((identity.get('row', identity.get('point_index')), row['axis'], row['value'],
                                            '유효' if row['valid'] else '무효' if row['valid'] is False else '미지정',
                                            row['reason'])):
                text = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else '' if value is None else str(value)
                item = QTableWidgetItem(text)
                item.setToolTip(json.dumps({'native': identity, 'object': self.snapshot['origin']['object_ref']}) if column == 0 else text)
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


class ObservationReviewDialog(QDialog):
    """Review retained Data values before appending to a live Plan's local draft."""
    def __init__(self, payload, title, role, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Append measured curve')
        self.resize(850, 620)
        layout = QVBoxLayout(self)
        response = payload['response']
        origin = payload['origin']
        label = QLabel(origin['selection']['value_array'] + ' → ' + title + '\n' +
            response['unit'] + ' / ' + response['frame'] + ' / ' + response['measure'] +
            '\nAppend as ' + role + '. Existing variables, protocols and unapplied edits remain. '
            'Assign the new trial’s model protocol and response before Run.')
        label.setWordWrap(True)
        layout.addWidget(label)
        split = QSplitter(Qt.Orientation.Vertical)
        table = QTableWidget(0, 3)
        table.setHorizontalHeaderLabels(['Axis', 'Measured', 'State'])
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        raw, axis = response.get('raw_samples'), response['axes'][0]
        values = raw['value'] if raw else response['value']
        xvalues = raw['axis'] if raw else axis['values']
        valid = raw['calculation_valid'] if raw else [True] * len(values)
        table.setRowCount(len(values))
        for row, (x, y, good) in enumerate(zip(xvalues, values, valid)):
            for column, value in enumerate((x, y, 'Used' if good else 'Excluded')):
                table.setItem(row, column, QTableWidgetItem(str(value)))
        split.addWidget(table)
        figure = Figure(figsize=(6, 3))
        canvas = FigureCanvasQTAgg(figure)
        axes = figure.add_subplot(111)
        def number(value):
            try:
                result = float(value)
                return result if math.isfinite(result) else math.nan
            except (ValueError, TypeError):
                return math.nan
        axes.plot([number(value) for value in xvalues],
                  [number(value) if good else math.nan for value, good in zip(values, valid)], marker='o')
        axes.set_xlabel(axis['name'] + ' [' + axis['unit'] + ']')
        axes.set_ylabel(response['component'] + ' [' + response['unit'] + ']')
        figure.tight_layout()
        split.addWidget(canvas)
        split.setSizes([170, 300])
        layout.addWidget(split, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText('Append observation')
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
