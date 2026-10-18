"""Scoped S1 mapping editor; edits only the existing Evaluation draft buffer."""
from copy import deepcopy

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QHeaderView)

from caelab.p1_temperature_transfer import (ABSOLUTE, DIFFERENCE, MAPPING, ABS_UNITS,
    TIME_UNITS, default_options, validate_options)
from .data_window import number_or_raw

MODES = {'exact': '기록된 동일 시각 선택', 'linear': '두 snapshot 사이 시간 선형 보간',
         'steady_relabel': '동일 정상 상태 선언으로 시계 재대응'}


def clock_origin_label(value):
    return '정상 상태 기준' if value == 'steady_reference' else str(value)


class TemperatureMappingDialog(QDialog):
    def __init__(self, row, stages, catalogs, parent=None):
        super().__init__(parent)
        self.setWindowTitle('온도 전달 설정'); self.resize(780, 610)
        self.setMinimumSize(540, 440)
        self.row = deepcopy(row)
        names = {s['id']: s['name'] for s in stages}
        self.candidates = []
        order = [s['id'] for s in stages]
        for stage in stages:
            if not row['lag'] and order.index(stage['id']) >= order.index(row['to_stage']):
                continue
            catalog = catalogs.get(stage['id'], {})
            for name, port in catalog.get('ports', {}).get('outputs', {}).items():
                if port.get('quantity') != ABSOLUTE or port.get('unit') not in ABS_UNITS or port.get('basis') != 'P1':
                    continue
                clock = catalog.get('clock') or {}
                caption = (names[stage['id']] + ' / ' + name + ' / ' + str(clock.get('value', '?'))
                           + ' ' + str(clock.get('unit', '?')) + ' / ' + clock_origin_label(clock.get('origin', '?')))
                self.candidates.append((caption, {'stage': stage['id'], 'output': name}))
        target = catalogs.get(row['to_stage'], {})
        target_port = target.get('ports', {}).get('inputs', {}).get(row['input'], {})
        initial = deepcopy(row.get('options') or default_options(row['from_stage'], row['output'],
                                                                 receiver_time=target.get('clock')))
        if 'options' not in row:
            initial['target_quantity'] = target_port.get('quantity', ABSOLUTE)
            initial['target_unit'] = target_port.get('unit', 'K')
        self.initial = initial
        layout = QVBoxLayout(self)
        header = QLabel(names.get(row['to_stage'], row['to_stage']) + ' / ' + row['input'])
        header.setProperty('appearanceRole', 'section'); layout.addWidget(header)
        note = QLabel('실제 원 삼각형 연결로 수신 P1 절점을 보간합니다. 보존적 전달이나 외삽이 아닙니다. '
                      '단일 정상 snapshot은 과도 해석이 아닙니다.'); note.setWordWrap(True); layout.addWidget(note)
        form = QFormLayout(); form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        self.mode = QComboBox(); self.mode.setObjectName('temperatureTimePolicy')
        for value, text in MODES.items(): self.mode.addItem(text, value)
        self.mode.setCurrentIndex(max(0, self.mode.findData(initial['time']['mode'])))
        form.addRow('시각 대응', self.mode)
        clock_layout = QHBoxLayout()
        self.instant = QLineEdit(str(initial['time']['receiver']['value'])); self.instant.setObjectName('temperatureReceiverInstant')
        self.unit = QComboBox(); self.unit.addItems(TIME_UNITS); self.unit.setCurrentText(initial['time']['receiver']['unit'])
        clock_layout.addWidget(self.instant, 1); clock_layout.addWidget(self.unit)
        form.addRow('수신 시각', clock_layout)
        self.origin = QLineEdit(initial['time']['receiver']['origin']); self.origin.setObjectName('temperatureReceiverOrigin')
        self.origin.setToolTip(clock_origin_label(initial['time']['receiver']['origin'])
                               + '\n원본과 대응하는 시계 원점의 식별값입니다. 저장 값은 그대로 유지합니다.')
        form.addRow('시계 원점', self.origin)
        original_clock = target.get('clock') or {}
        declared = QLabel('수신 원본 시각: ' + str(original_clock.get('value', '?')) + ' '
                          + str(original_clock.get('unit', '?')) + ' / '
                          + clock_origin_label(original_clock.get('origin', '?'))
                          + '\n수신 원본과 물리 시각·원점이 다르면 계산 전에 차단됩니다.')
        declared.setToolTip(str(original_clock.get('origin', '?')))
        declared.setWordWrap(True); form.addRow(declared)
        self.quantity = QComboBox(); self.quantity.setObjectName('temperatureTargetQuantity')
        self.quantity.addItem('절대 온도 [K]', (ABSOLUTE, 'K'))
        self.quantity.addItem('구조 Tref를 뺀 온도차 [ΔK]', (DIFFERENCE, 'delta_K'))
        self.quantity.setCurrentIndex(max(0, self.quantity.findData((initial['target_quantity'], initial['target_unit']))))
        form.addRow('수신 온도 의미', self.quantity)
        region = QComboBox(); region.addItem('수신 계산 영역의 모든 P1 절점 (필수)', 'all_receiver_nodes')
        region.setToolTip('이 첫 FE capability는 모든 수신 절점의 온도를 요구합니다. mask를 해제하거나 0으로 채울 수 없습니다.')
        form.addRow('필수 영역', region)
        layout.addLayout(form)
        self.sources = QTableWidget(0, 1); self.sources.setObjectName('temperatureSnapshots')
        self.sources.setHorizontalHeaderLabels(['공급 snapshot — 시각 오름차순'])
        self.sources.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.sources.setMinimumHeight(100); layout.addWidget(self.sources, 1)
        self.error = QLabel(); self.error.setWordWrap(True)
        for source in initial['time']['sources']: self.add_source(source)
        controls = QHBoxLayout()
        for text, action in [('snapshot 추가', lambda: self.add_source()), ('선택 삭제', self.remove_source),
                             ('위로', lambda: self.move_source(-1)), ('아래로', lambda: self.move_source(1))]:
            button = QPushButton(text); button.clicked.connect(action); controls.addWidget(button)
        layout.addLayout(controls)
        self.statement = QLineEdit((initial['time'].get('same_steady_state') or {}).get('statement', ''))
        self.statement.setObjectName('temperatureSteadyDeclaration')
        self.statement.setPlaceholderText('동일한 물리적 정상 상태라는 사용자의 명시 선언')
        layout.addWidget(self.statement)
        layout.addWidget(self.error)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText('정의에 적용')
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('취소')
        buttons.accepted.connect(self._accept); buttons.rejected.connect(self.reject); layout.addWidget(buttons)
        self.mode.currentIndexChanged.connect(self._mode_changed); self._mode_changed()

    def _mode_changed(self, *_):
        self.statement.setEnabled(self.mode.currentData() == 'steady_relabel')
        self.error.setText('시간 선형 보간: 서로 다른 2~32개 snapshot을 시각 오름차순으로 지정하세요.'
                           if self.mode.currentData() == 'linear' else '동일 시각 선택/정상 상태 재대응에는 snapshot 하나만 지정하세요.')

    def add_source(self, source=None):
        if self.sources.rowCount() >= 32:
            self.error.setText('공급 snapshot은 최대 32개입니다.'); return
        if not isinstance(source, dict): source = None
        choice = QComboBox(); choice.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        choice.setMinimumContentsLength(20)
        for caption, value in self.candidates: choice.addItem(caption, deepcopy(value))
        if source is not None:
            index = choice.findData(source)
            if index < 0:
                choice.addItem('확인되지 않은 원 snapshot: ' + str(source), deepcopy(source)); index = choice.count() - 1
            choice.setCurrentIndex(index)
        elif choice.count(): choice.setCurrentIndex(min(self.sources.rowCount(), choice.count() - 1))
        n = self.sources.rowCount(); self.sources.insertRow(n); self.sources.setCellWidget(n, 0, choice)
        self.sources.setCurrentCell(n, 0)

    def remove_source(self):
        index = self.sources.currentRow()
        if index >= 0: self.sources.removeRow(index)

    def move_source(self, direction):
        index = self.sources.currentRow(); target = index + direction
        if not 0 <= target < self.sources.rowCount(): return
        a, b = self.sources.cellWidget(index, 0), self.sources.cellWidget(target, 0)
        av, bv = deepcopy(a.currentData()), deepcopy(b.currentData())
        for widget, source in ((a, bv), (b, av)):
            selected = widget.findData(source)
            if selected < 0:
                widget.addItem('확인되지 않은 원 snapshot: ' + str(source), deepcopy(source))
                selected = widget.count() - 1
            widget.setCurrentIndex(selected)
        self.sources.setCurrentCell(target, 0)

    def options(self):
        quantity, unit = self.quantity.currentData()
        return {'time': {'mode': self.mode.currentData(), 'receiver': {'value': number_or_raw(self.instant.text()),
                'unit': self.unit.currentText(), 'origin': self.origin.text()},
                'sources': [deepcopy(self.sources.cellWidget(i, 0).currentData()) for i in range(self.sources.rowCount())],
                'same_steady_state': {'declared': True, 'statement': self.statement.text()}
                    if self.mode.currentData() == 'steady_relabel' else None},
                'required': 'all_receiver_nodes', 'target_quantity': quantity, 'target_unit': unit}

    def _accept(self):
        try: validate_options(self.options())
        except (ValueError, KeyError, TypeError) as error:
            self.error.setText(str(error)); return
        self.accept()

    def result_row(self):
        result = deepcopy(self.row); result['mapping'] = MAPPING; result['options'] = self.options()
        first = result['options']['time']['sources'][0]
        result.update(from_stage=first['stage'], output=first['output'])
        return result


def configure(window, row):
    # Capture edits before entering a modal dialog. Rejecting it does not apply,
    # save or discard the existing local draft, and never starts a calculation.
    draft = window.edited_draft()
    dialog = TemperatureMappingDialog(row, draft['stages'], {s['id']: window._catalog(s['id']) for s in draft['stages']}, window)
    was_dirty = window.local_dirty
    window.local_dirty = True  # An in-flight owner refresh must not replace the modal draft.
    try:
        return dialog.result_row() if dialog.exec() == QDialog.DialogCode.Accepted else None
    finally:
        window.local_dirty = was_dirty
        dialog.close(); dialog.deleteLater()
