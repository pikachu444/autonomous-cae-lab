"""Structured recipe editing; numerical processing stays in the service."""
from copy import deepcopy
import uuid
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDialog, QDialogButtonBox,
    QFormLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QPushButton,
    QTableWidget, QTableWidgetItem, QVBoxLayout)

OPERATIONS = {
    'convert': ('값 단위 변환', {'quantity': 'stress', 'to_unit': 'MPa'}),
    'convert_axis': ('축 단위 변환', {'quantity': 'time', 'to_unit': 's'}),
    'engineering_strain': ('공학 변형률', {'L0': 50., 'length_unit': 'mm', 'measurement': 'extensometer_gauge_extension'}),
    'stretch': ('신장비', {}),
    'nominal_stress': ('공칭 응력', {'A0': 1., 'area_unit': 'mm2'}),
    'zero_shift': ('영점 이동', {'source_rows': []}),
    'savgol': ('Savitzky–Golay 필터', {'window_length': 5, 'polyorder': 2, 'uniform_rtol': 1e-7, 'uniform_atol': 0.}),
    'resample': ('시간 재표본화', {'method': 'linear', 'max_gap': 1., 'range': [0., 1.], 'step': .1}),
}
LABELS = {'quantity': '물리량', 'to_unit': '변환 단위', 'L0': '초기 표점 거리',
    'length_unit': '길이 단위', 'measurement': '변위 측정', 'A0': '초기 단면적',
    'area_unit': '면적 단위', 'source_rows': '영점 원본 행', 'window_length': '창 표본 수',
    'polyorder': '다항식 차수', 'uniform_rtol': '등간격 상대 허용치',
    'uniform_atol': '등간격 절대 허용치', 'method': '보간', 'max_gap': '최대 간격 (축 단위)',
    'range': '시작, 끝 (축 단위)', 'step': '간격 (축 단위)'}
CHOICES = {
    'quantity': [('시간', 'time'), ('길이', 'length'), ('면적', 'area'), ('힘', 'force'),
        ('응력', 'stress'), ('무차원', 'dimensionless'), ('절대 온도', 'absolute_temperature'), ('온도차', 'temperature_difference')],
    'method': [('선형', 'linear'), ('최근접', 'nearest')],
    'measurement': [('표점 신율계 연신량', 'extensometer_gauge_extension')],
}
def text(value):
    return ', '.join(map(str, value)) if isinstance(value, list) else str(value)

class ProcessingStepDialog(QDialog):
    def __init__(self, operation, channels, parent=None):
        super().__init__(parent)
        self.original = deepcopy(operation)
        self.fields = {}
        self.setWindowTitle(OPERATIONS.get(operation['operation'], ('처리 단계',))[0])
        self.resize(510, 360)
        layout = QVBoxLayout(self); form = QFormLayout(); layout.addLayout(form)
        self.input = QComboBox(); self.input.setEditable(True); self.input.addItems(channels)
        self.input.setCurrentText(operation['input']); form.addRow('입력 채널', self.input)
        self.output = QLineEdit(operation['output']); form.addRow('출력 채널', self.output)
        for key, value in operation['settings'].items():
            if key in CHOICES:
                field = QComboBox()
                for label, canonical in CHOICES[key]: field.addItem(label, canonical)
                if field.findData(value) < 0: field.addItem(str(value), value)
                field.setCurrentIndex(field.findData(value))
            else:
                field = QLineEdit(text(value))
            self.fields[key] = field; form.addRow(LABELS.get(key, key), field)
        if operation['operation'] == 'engineering_strain':
            label = QLabel('크로스헤드 변위를 표점 연신량으로 대신하지 않습니다.'); label.setWordWrap(True); layout.addWidget(label)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText('단계 설정')
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('취소')
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject); layout.addWidget(buttons)

    def edited(self):
        from .material_window import edited_number
        operation = deepcopy(self.original)
        operation.update(input=self.input.currentText(), output=self.output.text())
        for key, field in self.fields.items():
            original = self.original['settings'][key]
            if isinstance(field, QComboBox): value = field.currentData()
            elif field.text() == text(original): value = deepcopy(original)
            elif key in ('range', 'source_rows'):
                value = [edited_number(part.strip()) for part in field.text().split(',') if part.strip()]
                if key == 'source_rows':
                    value = [int(v) if isinstance(v, float) and v.is_integer() else v for v in value]
            elif isinstance(original, (int, float)):
                value = edited_number(field.text())
                if isinstance(original, int) and isinstance(value, float) and value.is_integer(): value = int(value)
            else: value = field.text()
            operation['settings'][key] = value
        return operation

class DataProcessingRecipeDialog(QDialog):
    def __init__(self, recipe, channels, parent=None):
        super().__init__(parent)
        self.recipe = deepcopy(recipe)
        self.channels = list(channels)
        self.setWindowTitle('데이터 처리 단계'); self.resize(840, 470)
        layout = QVBoxLayout(self)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(['처리', '입력 채널', '출력 채널', '설정'])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.doubleClicked.connect(self.edit_step); layout.addWidget(self.table, 1)
        row = QHBoxLayout(); self.operation = QComboBox()
        for key, (label, _) in OPERATIONS.items(): self.operation.addItem(label, key)
        row.addWidget(self.operation)
        for label, action in [('추가…', self.add_step), ('설정…', self.edit_step), ('위로', lambda: self.move(-1)),
                              ('아래로', lambda: self.move(1)), ('삭제', self.remove_step)]:
            button = QPushButton(label); button.clicked.connect(action); row.addWidget(button)
        layout.addLayout(row)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText('처리 단계 설정')
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('취소')
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject); layout.addWidget(buttons)
        self._show()

    def _show(self, selected=0):
        self.table.setRowCount(len(self.recipe['operations']))
        for row, op in enumerate(self.recipe['operations']):
            summary = '; '.join(LABELS.get(key, key) + ': ' + text(value) for key, value in op['settings'].items())
            for column, shown in enumerate((OPERATIONS.get(op['operation'], (op['operation'],))[0], op['input'], op['output'], summary)):
                item = QTableWidgetItem(shown); item.setToolTip(shown); self.table.setItem(row, column, item)
        self.table.selectRow(selected)

    def _edit(self, op):
        channels = list(dict.fromkeys(self.channels + [item['output'] for item in self.recipe['operations']]))
        dialog = ProcessingStepDialog(op, channels, self)
        return dialog.edited() if dialog.exec() == QDialog.DialogCode.Accepted else None

    def add_step(self):
        key = self.operation.currentData()
        op = self._edit(dict(id='O' + uuid.uuid4().hex, operation=key, input=self.channels[0] if self.channels else '',
                             output='', settings=deepcopy(OPERATIONS[key][1])))
        if op is not None: self.recipe['operations'].append(op); self._show(len(self.recipe['operations']) - 1)

    def edit_step(self):
        row = self.table.currentRow()
        if row < 0: return
        op = self._edit(self.recipe['operations'][row])
        if op is not None: self.recipe['operations'][row] = op; self._show(row)

    def move(self, delta):
        row = self.table.currentRow(); target = row + delta
        if 0 <= row < len(self.recipe['operations']) and 0 <= target < len(self.recipe['operations']):
            self.recipe['operations'][row], self.recipe['operations'][target] = self.recipe['operations'][target], self.recipe['operations'][row]
            self._show(target)

    def remove_step(self):
        row = self.table.currentRow()
        if row >= 0: del self.recipe['operations'][row]; self._show(max(0, row - 1))


class DataProcessingPreviewDialog(QDialog):
    def __init__(self, result, parent=None, *, retained=False, allow_plan=False):
        super().__init__(parent)
        from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
        from matplotlib.figure import Figure
        self.processing_result = deepcopy(result)
        self.plan_requested = False
        self.plan_button = None
        self.analysis_source = None
        self.analysis_button = None
        self.setWindowTitle('처리 결과' if retained else '처리 미리보기'); self.resize(900, 640)
        layout = QVBoxLayout(self)
        self.stages = QTableWidget(0, 3)
        self.stages.setHorizontalHeaderLabels(['출력 채널', '처리 상태', '결과'])
        self.stages.setMaximumHeight(120)
        self.stages.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.stages.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        for row, stage in enumerate(result.get('stages', [])):
            self.stages.insertRow(row)
            for column, value in enumerate((stage['output'], '처리됨' if stage.get('state') == 'READY' else '처리 실패',
                stage.get('error', {}).get('message') or f"유효 {stage.get('valid_count', 0)}, 제외 {stage.get('invalid_count', 0)}")):
                item = QTableWidgetItem(value); item.setToolTip(value); self.stages.setItem(row, column, item)
        layout.addWidget(self.stages)
        self.channel = QComboBox(); self.channel.addItems(list(result.get('responses', {}))); layout.addWidget(self.channel)
        self.figure = Figure(figsize=(6, 3), tight_layout=True)
        self.canvas = FigureCanvasQTAgg(self.figure); layout.addWidget(self.canvas, 1)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(['축 값', '값', '단위', '원본 행'])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table, 1)
        from .numerical_methods import ResultDisplay
        display=ResultDisplay(self.table)
        for column in (0,1): self.table.setItemDelegateForColumn(column,display)
        self.status = QLabel(); self.status.setWordWrap(True); layout.addWidget(self.status)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.button(QDialogButtonBox.StandardButton.Close).setText('닫기')
        from .finite_measure_gui import add_audit_button
        add_audit_button(self, buttons)
        if not retained:
            apply = buttons.addButton('처리 결과 보존', QDialogButtonBox.ButtonRole.AcceptRole)
            apply.clicked.connect(self.accept)
        elif allow_plan:
            self.plan_button = buttons.addButton('피팅 계획으로…', QDialogButtonBox.ButtonRole.ActionRole)
            self.plan_button.clicked.connect(self._plan)
        if retained:
            self.analysis_button = buttons.addButton('제공 불확실성 전파…', QDialogButtonBox.ButtonRole.ActionRole)
            self.analysis_button.clicked.connect(self._analysis)
        buttons.rejected.connect(self.reject); layout.addWidget(buttons)
        self.channel.currentTextChanged.connect(self._channel); self._channel(self.channel.currentText())

    def _channel(self, name):
        response = self.processing_result.get('responses', {}).get(name)
        self.figure.clear(); axis = self.figure.add_subplot(111); self.table.setRowCount(0)
        processing_status = self.processing_result.get('diagnostics', {}).get('processing_status')
        self.status.setText('일부 처리 실패' if processing_status == 'PARTIAL' else '처리 실패' if self.processing_result.get('execution_status') == 'FAILED' else '처리 결과')
        if response:
            values = response.get('value', []); axes = response.get('axes', [])
            x = axes[0].get('values', []) if axes else []
            if len(x) == len(values):
                ranges = [segment['rows'] for segment in response.get('segments', [])] if 'segments' in response else [[0, len(values)]]
                for first, last in ranges:
                    axis.plot(x[first:last], values[first:last], color='C0', linewidth=1.4, marker='.' if last - first == 1 else None)
            axis.set_xlabel((axes[0].get('name', '') + ' [' + axes[0].get('unit', '') + ']') if axes else '')
            axis.set_ylabel(name + ' [' + response.get('unit', '') + ']')
            rows = response.get('source_rows', [])
            # A derived sample never borrows a source-row number for display.
            self.table.setRowCount(min(1000, len(values)))
            for row in range(self.table.rowCount()):
                for col, value in enumerate((x[row] if row < len(x) else '', values[row], response.get('unit', ''),
                                              rows[row] if row < len(rows) and rows[row] is not None else '—')):
                    item=QTableWidgetItem(str(value));item.setToolTip(repr(value) if col in (0,1) else str(value))
                    self.table.setItem(row,col,item)
            if len(values) > 1000: self.status.setText(self.status.text() + ' / 표는 처음 1000개 표본')
        if self.plan_button:
            self.plan_button.setEnabled(bool(response and response.get('measure') in ('infinitesimal_Cauchy', 'first_Piola', 'finite_Cauchy')))
        if self.analysis_button:
            self.analysis_button.setEnabled(self._analysis_selection(name) is not None)
        # This modal preview can close before an idle callback reaches its canvas.
        axis.grid(alpha=.2); self.canvas.draw()

    def _plan(self):
        self.plan_requested = True
        self.accept()

    def _analysis_selection(self, name):
        record=self.processing_result.get('diagnostics',{}).get('processing_record',{})
        channel=self.processing_result.get('channels',{}).get(name)
        identifier=record.get('source',{}).get('document_id')
        if not identifier or not record.get('id') or not isinstance(channel,dict):
            return None
        from caelab.storage import canonical_hash
        return dict(kind='processing_channel',document_id=identifier,revision=record['id'],
            channel=name,channel_sha256=canonical_hash(channel))

    def _analysis(self):
        source=self._analysis_selection(self.channel.currentText())
        if source is None or self.analysis_button is None:
            return False
        self.analysis_source=source
        self.accept()
        return True
