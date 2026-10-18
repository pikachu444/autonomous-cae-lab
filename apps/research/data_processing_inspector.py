"""Paged inspection of existing processing samples; no processing or policy writer."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QDialog, QDialogButtonBox,
    QHBoxLayout, QHeaderView, QLabel, QPushButton, QSpinBox, QTableWidget,
    QTableWidgetItem, QVBoxLayout)

from .data_processing_dialog import DataProcessingPreviewDialog
from .numerical_methods import ResultDisplay

PAGE_SIZE = 1000


def _shown(value):
    return '—' if value is None else str(value)


def _row_text(rows, *, compact=False):
    rows = sorted(set(rows))
    if compact and len(rows) > 8: return f'{rows[0]}–{rows[-1]} ({len(rows)}행)'
    return ', '.join(map(str, rows)) or '없음'


def _validity_rows(sample):
    return sample.get('validity_source_rows', sample.get('source_rows', []))


def _state(channel, index):
    labels = []
    for key, label in (('quality_valid', '품질 제외'), ('calculation_valid', '계산 제외'),
                       ('operation_valid', '처리 제외')):
        if not channel[key][index]:
            labels.append(label)
    if not channel['display_visible'][index]:
        labels.append('보기 숨김')
    return ', '.join(labels) or '유효'


class ProcessingSampleTraceDialog(QDialog):
    """Read one selected canonical sample's existing signed raw-cell trace."""
    def __init__(self, channel, index, trace, segment, parent=None):
        super().__init__(parent)
        self.setWindowTitle('선택 표본 근거')
        self.resize(780, 540)
        self.channel, self.sample_index, self.trace = channel, index, trace
        sample = channel['samples'][index]
        root = QVBoxLayout(self)
        origin = '파생 표본' if channel['sample_domain'] == 'derived-grid-v2' else '원행 ' + str(sample['anchor_row'])
        header = QLabel(f"{channel['name']} / 표본 {index + 1} / {origin} / 구간 {_shown(segment)}\n"
            f"{_shown(channel['axis']['values'][index])} {channel['axis']['unit']} → "
            f"{_shown(channel['values'][index])} {channel['metadata']['unit']}")
        header.setWordWrap(True); root.addWidget(header)
        reasons = [channel[key][index] for key in ('quality_reasons', 'calculation_reasons', 'operation_reasons') if channel[key][index]]
        state = QLabel(_state(channel, index) + '\n값 기여 원행: ' + _row_text(sample.get('source_rows', []))
            + '\n판정 원행: ' + _row_text(_validity_rows(sample)) + ('\n' + '\n'.join(dict.fromkeys(reasons)) if reasons else ''))
        state.setWordWrap(True); root.addWidget(state)
        self.count = QLabel(); self.count.setWordWrap(True)
        pager = QHBoxLayout(); pager.addWidget(self.count, 1); pager.addWidget(QLabel('첫 기여 항'))
        self.start = QSpinBox(); self.start.setRange(1, max(1, len(trace['terms']))); self.start.setSingleStep(PAGE_SIZE)
        pager.addWidget(self.start); root.addLayout(pager)
        self.terms = QTableWidget(0, 4)
        self.terms.setHorizontalHeaderLabels(['원본 열', '원행', '값 기여 계수', '원래 값'])
        self.terms.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.terms.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        numeric = ResultDisplay(self.terms)
        for column in (2, 3): self.terms.setItemDelegateForColumn(column, numeric)
        root.addWidget(self.terms, 1)
        explanation = QLabel('값 기여 계수는 기존 처리 계보의 부호 있는 계수입니다. 연구용 표본 가중치와 포함·holdout은 피팅 계획에서 지정합니다.'
            + '\n상수항: ' + _shown(trace.get('bias')))
        explanation.setWordWrap(True); root.addWidget(explanation)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.button(QDialogButtonBox.StandardButton.Close).setText('닫기')
        buttons.rejected.connect(self.reject); root.addWidget(buttons)
        self.start.valueChanged.connect(self._show_terms); self._show_terms()

    def _show_terms(self, *_):
        first = self.start.value() - 1
        terms = self.trace['terms'][first:first + PAGE_SIZE]
        self.terms.setRowCount(len(terms))
        for row, term in enumerate(terms):
            ref = term['raw_ref']
            for column, value in enumerate((ref.get('column_identity', ref.get('column', '')), ref['source_row'],
                                             term.get('coefficient'), term.get('raw_value'))):
                item = QTableWidgetItem(_shown(value)); item.setToolTip('이전 가져오기에 원래 값이 보존되지 않았습니다.' if column == 3 and value is None else repr(value))
                self.terms.setItem(row, column, item)
        self.count.setText(f"원자료 기여 {len(self.trace['terms'])}개 / {first + 1 if terms else 0}–{first + len(terms)} 표시")


class DataProcessingInspectorDialog(DataProcessingPreviewDialog):
    """Original preview/retention/Plan actions plus bounded canonical audit pages.

    The original result is already read by DataWindow. Paging and selection only
    read that retained payload and trace one selected sample's existing DAG.
    """
    def __init__(self, result, parent=None, *, retained=False, allow_plan=False):
        self._audit_ready = False
        super().__init__(result, parent, retained=retained, allow_plan=allow_plan)
        self.stage_recovery = None
        for row in range(self.stages.rowCount()):
            item = self.stages.item(row, 2)
            if item.text() == 'Savitzky-Golay requires uniform sampling; explicitly resample first':
                item.setText('간격이 일정하지 않아 평활화하지 못했습니다. 먼저 재표본화하세요.')
                if self.stage_recovery is None:
                    self.stage_recovery = QLabel(item.text()); self.stage_recovery.setWordWrap(True)
                    self.stage_recovery.setToolTip(item.toolTip())
                    self.layout().insertWidget(self.layout().indexOf(self.stages) + 1, self.stage_recovery)
        self._page_selection = {}
        self._current_channel = None
        self._trace_cache = {}
        self._valid_counts = {}
        self._trace = None
        self._segments = []
        self.audit_count = QLabel(); self.audit_count.setWordWrap(True)
        self.page_start = QSpinBox(); self.page_start.setMinimum(1); self.page_start.setSingleStep(PAGE_SIZE)
        self.page_start.setAccessibleName('첫 처리 표본')
        pager = QHBoxLayout(); pager.addWidget(self.audit_count, 1); pager.addWidget(QLabel('첫 표본')); pager.addWidget(self.page_start)
        layout = self.layout(); layout.insertLayout(layout.indexOf(self.table), pager)
        self.sample_status = QLabel('표본을 선택하면 원자료와 처리 상태를 확인합니다.'); self.sample_status.setWordWrap(True)
        self.trace_button = QPushButton('선택 표본 근거…'); self.trace_button.setEnabled(False)
        detail = QHBoxLayout(); detail.addWidget(self.sample_status, 1); detail.addWidget(self.trace_button)
        layout.insertLayout(layout.indexOf(self.status), detail)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setStretchLastSection(True)
        numeric = ResultDisplay(self.table)
        for column in (1, 2): self.table.setItemDelegateForColumn(column, numeric)
        self.page_start.valueChanged.connect(self._show_page)
        self.table.currentCellChanged.connect(self._selected)
        self.trace_button.clicked.connect(self.show_sample_trace)
        self.channel.blockSignals(True)
        for stage in self.processing_result.get('stages', []):
            name = stage.get('output')
            if name in self.processing_result.get('channels', {}) and self.channel.findText(name) < 0: self.channel.addItem(name)
        self.channel.blockSignals(False)
        self._audit_ready = True
        self._channel(self.channel.currentText())
        self.resize(1020, 780)

    def _channel(self, name):
        if self._audit_ready and self._current_channel is not None:
            self._page_selection[self._current_channel] = (self.page_start.value(), self.selected_sample_index())
        if self._audit_ready: self.table.blockSignals(True)
        try:
            super()._channel(name)
        finally:
            if self._audit_ready: self.table.blockSignals(False)
        if not self._audit_ready: return
        self.status.setText(self.status.text().replace(' / 표는 처음 1000개 표본', ''))
        self._current_channel = name; self._trace_cache = {}; self._trace = None
        channel = self.processing_result.get('channels', {}).get(name)
        self.page_start.setEnabled(bool(channel))
        self.trace_button.setEnabled(False)
        if not channel or not channel.get('samples'):
            self.table.setColumnCount(4); self.table.setHorizontalHeaderLabels(['축 값', '값', '단위', '원본 행'])
            self.audit_count.setText('이전 결과의 유효값 미리보기 / 원자료 계보가 제공되지 않았습니다.')
            self.sample_status.setText('원자료 계보를 확인할 수 없습니다.')
            return
        response = self.processing_result.get('responses', {}).get(name, {})
        segment_by_id = {}
        for ordinal, segment in enumerate(response.get('segments', []), 1):
            first, last = segment['rows']
            for sid in segment.get('sample_ids', response.get('sample_ids', [])[first:last]): segment_by_id[sid] = ordinal
        self._segments = [segment_by_id.get(sample['sample_id']) for sample in channel['samples']]
        if name not in self._valid_counts:
            self._valid_counts[name] = sum(all(channel[key][index] for key in ('quality_valid', 'calculation_valid', 'operation_valid')) for index in range(len(channel['samples'])))
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(['표본', '축 값 [' + channel['axis']['unit'] + ']', '값 [' + channel['metadata']['unit'] + ']', '원자료 / 파생', '사용 상태', '구간'])
        for column, width in enumerate((65, 115, 120, 125, 210, 65)): self.table.setColumnWidth(column, width)
        first, selected = self._page_selection.get(name, (1, 0))
        self.page_start.blockSignals(True); self.page_start.setMaximum(len(channel['samples'])); self.page_start.setValue(first); self.page_start.blockSignals(False)
        self._show_page(selected=selected)

    def selected_sample_index(self):
        return self.page_start.value() - 1 + max(0, self.table.currentRow())

    def _show_page(self, *_, selected=None):
        channel = self.processing_result.get('channels', {}).get(self._current_channel)
        if not channel: return
        first = self.page_start.value() - 1; samples = channel['samples'][first:first + PAGE_SIZE]
        self.table.blockSignals(True); self.table.setRowCount(len(samples))
        for row, sample in enumerate(samples):
            index = first + row
            origin = '파생' if channel['sample_domain'] == 'derived-grid-v2' else '원행 ' + str(sample['anchor_row'])
            values = (index + 1, channel['axis']['values'][index], channel['values'][index], origin,
                      _state(channel, index), self._segments[index])
            for column, value in enumerate(values):
                item = QTableWidgetItem(_shown(value)); item.setToolTip(repr(value)); self.table.setItem(row, column, item)
        self.table.blockSignals(False)
        valid = self._valid_counts[self._current_channel]
        self.audit_count.setText(f"전체 처리 표본 {len(channel['samples'])}개 / 유효값 {valid}개 / {first + 1}–{first + len(samples)} 표시")
        if samples:
            row = max(0, min(len(samples) - 1, (first if selected is None else selected) - first))
            self.table.blockSignals(True); self.table.setCurrentCell(row, 0); self.table.blockSignals(False)
            self._selected(row)

    def _selected(self, row, *_):
        if not self._audit_ready or row < 0: return
        channel = self.processing_result.get('channels', {}).get(self._current_channel)
        if not channel: return
        index = self.page_start.value() - 1 + row
        if index >= len(channel['samples']): return
        sample = channel['samples'][index]
        from caelab.data_processing_lineage import trace_sample
        try:
            self._trace = trace_sample(channel, sample['sample_id'], cache=self._trace_cache)
        except (ValueError, KeyError, TypeError) as error:
            self._trace = None; self.trace_button.setEnabled(False)
            self.sample_status.setText('표본 근거를 읽지 못했습니다. 원래 결과는 보존됩니다.')
            self.sample_status.setToolTip(str(error)); return
        self.trace_button.setEnabled(True); self.sample_status.setToolTip('')
        self.sample_status.setText(f"표본 {index + 1} / 구간 {_shown(self._segments[index])} / 값 기여 원행 "
            + _row_text(sample.get('source_rows', []), compact=True) + ' / 판정 원행 '
            + _row_text(_validity_rows(sample), compact=True) + ' / ' + _state(channel, index))

    def show_sample_trace(self):
        if self._trace is None: return
        channel = self.processing_result['channels'][self._current_channel]
        index = self.selected_sample_index()
        dialog = ProcessingSampleTraceDialog(channel, index, self._trace, self._segments[index], self)
        dialog.exec()
