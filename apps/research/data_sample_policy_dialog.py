"""Review per-sample Plan policy; Core owns masks, lineage and adoption."""
from copy import deepcopy
import math
from PySide6.QtCore import Qt, QItemSelectionModel
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDialog, QDialogButtonBox,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QPushButton, QSpinBox,
    QTableWidget, QTableWidgetItem, QVBoxLayout)


class SamplePolicyDialog(QDialog):
    def __init__(self, proposal, channel, parent=None):
        super().__init__(parent)
        from caelab.data_processing_selection import sample_domain
        if proposal.get('domain') != sample_domain(channel) or set(proposal['entries']) != {sample['sample_id'] for sample in channel['samples']}:
            raise ValueError('검토할 표본 정책과 처리 결과가 다릅니다.')
        self.proposal, self.channel = deepcopy(proposal), deepcopy(channel)
        self.entries = deepcopy(proposal['entries'])
        self.setWindowTitle('관측 표본 용도')
        self.resize(960, 680)
        layout = QVBoxLayout(self)
        header = QHBoxLayout(); self.start = QSpinBox()
        self.start.setRange(1, max(1, len(channel['samples']))); self.start.setSingleStep(1000)
        header.addWidget(QLabel(channel['name'] + ' [' + channel['metadata']['unit'] + ']'))
        header.addStretch(); header.addWidget(QLabel('첫 표본')); header.addWidget(self.start)
        layout.addLayout(header)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(['축 값 [' + channel['axis']['unit'] + ']', '값', '원자료 / 처리', '포함', '용도', '가중치'])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table, 1)
        batch = QHBoxLayout(); self.role = QComboBox()
        self.role.addItem('피팅', 'fit'); self.role.addItem('검증 (holdout)', 'holdout')
        self.weight = QLineEdit('1'); self.weight.setMaximumWidth(110)
        include, exclude, apply = QPushButton('선택 포함'), QPushButton('선택 제외'), QPushButton('선택 용도 적용')
        for widget in (include, exclude, self.role, self.weight, apply): batch.addWidget(widget)
        batch.addStretch(); layout.addLayout(batch)
        self.contributors = QTableWidget(0, 4)
        self.contributors.setHorizontalHeaderLabels(['원본 열', '원본 행', '기여 계수', '원래 값'])
        self.contributors.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.contributors.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.contributors.setMaximumHeight(160); layout.addWidget(self.contributors)
        self.message = QLabel(); self.message.setWordWrap(True); layout.addWidget(self.message)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText('표본 정책 채택')
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('취소')
        buttons.accepted.connect(self._accept); buttons.rejected.connect(self.reject); layout.addWidget(buttons)
        include.clicked.connect(lambda: self._batch(included=True))
        exclude.clicked.connect(lambda: self._batch(included=False))
        apply.clicked.connect(self._batch)
        self.table.itemChanged.connect(self._edited)
        self.table.currentCellChanged.connect(self._trace)
        self.start.valueChanged.connect(self._show)
        self._show()

    def _show(self, *_ignored, selection=None):
        self.table.blockSignals(True)
        first = self.start.value() - 1; samples = self.channel['samples'][first:first + 1000]
        self.table.setRowCount(len(samples))
        for row, sample in enumerate(samples):
            index = first + row; sid = sample['sample_id']; entry = self.entries[sid]
            flags = [('품질 제외', self.channel['quality_valid'][index]), ('계산 제외', self.channel['calculation_valid'][index]),
                     ('처리 제외', self.channel['operation_valid'][index])]
            state = ', '.join(label for label, valid in flags if not valid) or '유효'
            values = (self.channel['axis']['values'][index], self.channel['values'][index], state,
                      entry['included'], entry['role'], entry['weight'])
            for column, value in enumerate(values):
                shown = '피팅' if column == 4 and value == 'fit' else '검증 (holdout)' if column == 4 and value == 'holdout' else '—' if value is None else str(value)
                item = QTableWidgetItem(shown); item.setData(Qt.ItemDataRole.UserRole, sid)
                if column < 3 or column == 4: item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if column == 3:
                    item.setText(''); item.setFlags((item.flags() & ~Qt.ItemFlag.ItemIsEditable) | Qt.ItemFlag.ItemIsUserCheckable)
                    item.setCheckState(Qt.CheckState.Checked if value else Qt.CheckState.Unchecked)
                self.table.setItem(row, column, item)
        self.table.blockSignals(False)
        self.message.setText(f"전체 {len(self.channel['samples'])}개 중 {first + 1}–{first + len(samples)}개 표시 / 원자료 품질과 처리 제외는 그대로 유지됩니다.")
        if samples:
            self.table.setCurrentCell(0, 0); self._trace(0)
            if selection:
                self.table.clearSelection()
                for row in selection:
                    self.table.selectionModel().select(self.table.model().index(row, 0),
                        QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows)
                self.table.setCurrentCell(selection[0], 0, QItemSelectionModel.SelectionFlag.NoUpdate)

    def _edited(self, item):
        sid = item.data(Qt.ItemDataRole.UserRole)
        if item.column() == 3: self.entries[sid]['included'] = item.checkState() == Qt.CheckState.Checked
        elif item.column() == 5:
            from .material_window import edited_number
            self.entries[sid]['weight'] = edited_number(item.text())

    def _batch(self, *, included=None):
        rows = sorted({index.row() for index in self.table.selectedIndexes()})
        if not rows: return
        from .material_window import edited_number
        for row in rows:
            sid = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
            if included is None:
                self.entries[sid].update(role=self.role.currentData(), weight=edited_number(self.weight.text()))
            else: self.entries[sid]['included'] = included
        self._show(selection=rows)

    def _trace(self, row, *_):
        self.contributors.setRowCount(0)
        if row < 0 or self.table.item(row, 0) is None: return
        from caelab.data_processing_lineage import trace_sample
        sid = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        result = trace_sample(self.channel, sid)
        for index, term in enumerate(result['terms']):
            self.contributors.insertRow(index); ref = term['raw_ref']
            for column, value in enumerate((ref.get('column', ref.get('source_column', '')), ref.get('source_row', ref.get('row', '')),
                                          term['coefficient'], term.get('value', term.get('raw_value', '')))):
                self.contributors.setItem(index, column, QTableWidgetItem(str(value)))

    def _accept(self):
        focus = self.focusWidget()
        if focus and self.table.isAncestorOf(focus): focus.clearFocus()
        for entry in self.entries.values():
            value = entry['weight']
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                self.message.setText('가중치는 0 이상의 유한수로 입력하세요. 편집은 보존됩니다.'); return
        self.accept()
