"""Read-only view of retained interface-history observations; never evaluates."""
from copy import deepcopy
import json
import math

from PySide6 import QtCore as C, QtWidgets as W
from matplotlib.figure import Figure
from matplotlib.ticker import FuncFormatter
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from .appearance import configure_plot_fonts


COMPONENTS = [('법선', 'normal'), ('접선 1', 'tangent1'), ('접선 2', 'tangent2')]
PLOTS = [('traction–벌어짐 변화', 'traction_opening'), ('시간–손상', 'damage'),
         ('시간–변위 변화', 'change'), ('시간–traction', 'traction'), ('시간–할선 강성', 'secant')]


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def shown(value):
    return format(value, '.8g') if finite(value) else '기록 없음'


def activity(value):
    return '활성' if finite(value) and value == 1 else '비활성' if finite(value) and value == 0 else '미확인'


def observation(value):
    return {'OBSERVED': '관측됨', 'NOT_OBSERVED': '미관측', 'DECREASE_OBSERVED': '감소 관측',
            'VIOLATED': '위반 관측', 'SIGN_MISMATCH': '부호 불일치', 'UNKNOWN': '미확인'}.get(value, '미확인')


def secant_text(change, value):
    return shown(value) if finite(value) else '미정의 (변위 변화 0)' if finite(change) and change == 0 else '기록 없음'


def bulk_text(sample):
    rows = sample.get('adjacent_bulk_activity')
    if not isinstance(rows, dict) or not rows:
        return '기록 없음'
    parts = []
    for element, values in rows.items():
        states = [activity(v) for v in values] if isinstance(values, list) else []
        state = states[0] if states and all(v == states[0] for v in states) else '미확인'
        parts.append('요소 ' + str(element) + ' ' + state)
    return ', '.join(parts)


class InterfaceHistoryView(W.QDialog):
    def __init__(self, audit, parent=None):
        super().__init__(parent)
        self.setWindowTitle('계면 이력 관측')
        self.resize(1120, 850)
        self._audit = deepcopy(audit) if isinstance(audit, dict) else {}
        self._elements = self._audit.get('elements') or []
        self._elements = self._elements if isinstance(self._elements, list) else []
        unavailable = self._audit.get('unavailable_frames') or []
        self._missing = [row for row in unavailable if isinstance(row, dict)] if isinstance(unavailable, list) else []
        self._samples = []
        self._row = -1
        layout = W.QVBoxLayout(self)
        self.qualification = W.QLabel('공학 적합성: ' + self._verdict('qualification') +
            ' / 구성법칙 수치 기준: ' + self._verdict('constitutive_numerical_criterion'))
        self.qualification.setWordWrap(True); layout.addWidget(self.qualification)
        self.limits = W.QLabel('초기 대응면 기준의 투영 traction입니다. solver의 현재 국소 기준계와 다릅니다.\n'
            'native 4적분점 평균 traction과 대응면 4모서리 평균 변위·평균 손상의 비교이며, 적분점 구성식의 등식 검사가 아닙니다.')
        self.limits.setWordWrap(True); layout.addWidget(self.limits)
        bar = W.QHBoxLayout()
        self.element = W.QComboBox(); self.element.setObjectName('observedInterfaceElement')
        self.element.setAccessibleName('관측할 원 계면 요소')
        self.component = W.QComboBox(); self.component.setObjectName('observedInterfaceComponent')
        self.component.setAccessibleName('초기 대응면 기준의 관측 성분')
        for label, code in COMPONENTS:
            self.component.addItem(label, code)
        self.plot_kind = W.QComboBox(); self.plot_kind.setObjectName('interfaceHistoryPlot')
        self.plot_kind.setAccessibleName('계면 이력 곡선의 물리량')
        for label, code in PLOTS:
            self.plot_kind.addItem(label, code)
        for label, widget, stretch in [('계면', self.element, 2), ('성분', self.component, 1), ('곡선', self.plot_kind, 2)]:
            bar.addWidget(W.QLabel(label)); bar.addWidget(widget, stretch)
            widget.setSizeAdjustPolicy(W.QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            widget.setMinimumContentsLength(7)
        layout.addLayout(bar)
        self.summary = W.QLabel(); self.summary.setWordWrap(True); layout.addWidget(self.summary)
        self.selected = W.QLabel(); self.selected.setObjectName('selectedInterfaceSample')
        self.selected.setWordWrap(True); layout.addWidget(self.selected)

        splitter = W.QSplitter(C.Qt.Orientation.Vertical); layout.addWidget(splitter, 1)
        configure_plot_fonts()
        self.figure = Figure(layout='constrained')
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.canvas.setMinimumSize(0, 155)
        self.canvas.setSizePolicy(W.QSizePolicy.Policy.Ignored, W.QSizePolicy.Policy.Expanding)
        splitter.addWidget(self.canvas)
        self.tabs = W.QTabWidget(); self.tabs.setUsesScrollButtons(True)
        splitter.addWidget(self.tabs); splitter.setSizes([290, 300])
        self.table = self._table(['시간 [s]', '평균 손상 [1]', '변위 변화 [mm]', '투영 traction [MPa]',
            '할선 강성 [MPa/mm]', '계면 상태', '인접 벌크 상태', '기록 사유'])
        self.table.setObjectName('interfaceHistorySamples')
        self.table.horizontalHeader().setSectionResizeMode(W.QHeaderView.ResizeMode.ResizeToContents)
        self.tabs.addTab(self.table, '원 표본')
        self.values = self._table(['선택 표본의 관측값', '원값', '단위'])
        self.tabs.addTab(self.values, '선택 표본')
        declared_page = W.QWidget(); declared_layout = W.QVBoxLayout(declared_page)
        declared_layout.setContentsMargins(0, 0, 0, 0)
        self.declared = self._table(['이력 이름', '재료', '원 절점 집합', '전역 축', '점 수'])
        self.declared.setMaximumHeight(130); declared_layout.addWidget(self.declared)
        self.declared_points = self._table(['시간 [s]', '부과 변위 [mm]'])
        declared_layout.addWidget(self.declared_points, 1)
        self.tabs.addTab(declared_page, '부과한 입력')
        self.evidence = self._table(['보존한 관측 근거', '내용'])
        self.tabs.addTab(self.evidence, '관측 범위')
        self.missing = self._table(['누락 시각 [s]', '읽지 못한 이유'])
        self._fill(self.missing, [(shown(row.get('time_s')), row.get('reason') or '사유 미기록') for row in self._missing])
        self.tabs.addTab(self.missing, '누락 표본 (' + str(len(self._missing)) + ')')
        self.raw = W.QPlainTextEdit(); self.raw.setReadOnly(True)
        self.raw.setObjectName('interfaceHistoryOriginalDetails')
        self.tabs.addTab(self.raw, '원 기록 상세')
        self.note = W.QLabel('점은 원 표본입니다. 선은 기록 순서만 잇습니다. 표본 사이의 연속 이력은 미확인입니다.\n'
            '할선 강성(secant)은 접선 강성이 아닙니다. native 손상 소산 에너지는 미확인이며 합성하지 않습니다. 피로 법칙은 구현되지 않았습니다.')
        self.note.setWordWrap(True); layout.addWidget(self.note)
        self.close_buttons = W.QDialogButtonBox(W.QDialogButtonBox.StandardButton.Close)
        self.close_buttons.button(W.QDialogButtonBox.StandardButton.Close).setText('닫기')
        self.close_buttons.rejected.connect(self.reject); layout.addWidget(self.close_buttons)
        self.element.currentIndexChanged.connect(self._element_changed)
        self.component.currentIndexChanged.connect(self._component_changed)
        self.plot_kind.currentIndexChanged.connect(self._draw)
        self.table.currentCellChanged.connect(self._sample_changed)
        self.declared.currentCellChanged.connect(self._declared_changed)
        self.canvas.mpl_connect('pick_event', self._picked)
        self.element.blockSignals(True)
        for i, element in enumerate(self._elements):
            if isinstance(element, dict):
                self.element.addItem('요소 ' + str(element.get('element_id', '미확인')) + ' / ' + str(element.get('material', '재료 미확인')), i)
        self.element.blockSignals(False)
        self._populate_declared()
        self._element_changed()

    def _verdict(self, key):
        # This window never admits engineering release from execution success.
        value = self._audit.get(key)
        return '미확인' if value == 'UNKNOWN' or value is None else '원 기록 확인 필요'

    def _table(self, headers):
        table = W.QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setEditTriggers(W.QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(W.QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(W.QAbstractItemView.SelectionMode.SingleSelection)
        table.setMinimumSize(0, 120)
        table.horizontalHeader().setSectionResizeMode(W.QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setStretchLastSection(True)
        return table

    @staticmethod
    def _fill(table, rows):
        table.blockSignals(True); table.setRowCount(len(rows))
        for i, values in enumerate(rows):
            for j, value in enumerate(values):
                item = W.QTableWidgetItem(str(value))
                item.setToolTip(str(value)); table.setItem(i, j, item)
        table.blockSignals(False)

    def _current_element(self):
        index = self.element.currentData()
        return self._elements[index] if type(index) is int and 0 <= index < len(self._elements) else {}

    def _populate_declared(self):
        rows = self._audit.get('declared_histories') or []
        self._declared = rows if isinstance(rows, list) else []
        self._fill(self.declared, [(row.get('name', '이름 미기록'), row.get('material', '미기록'), row.get('node_set', '미기록'),
            row.get('component', '미기록'), len(row.get('time_s', [])) if isinstance(row.get('time_s'), list) else '미기록')
            for row in self._declared if isinstance(row, dict)])
        if self.declared.rowCount():
            self.declared.setCurrentCell(0, 0)

    def _declared_changed(self, row, *_):
        if not 0 <= row < len(self._declared):
            return
        value = self._declared[row]
        times, displacements = value.get('time_s', []), value.get('displacement_mm', [])
        times = times if isinstance(times, list) else []
        displacements = displacements if isinstance(displacements, list) else []
        self._fill(self.declared_points, [(shown(times[i]) if i < len(times) else '기록 없음',
            shown(displacements[i]) if i < len(displacements) else '기록 없음') for i in range(max(len(times), len(displacements)))])

    def _element_changed(self, *_):
        element = self._current_element()
        samples = element.get('samples') or []
        self._samples = samples if isinstance(samples, list) else []
        self.summary.setText('부분 손상: ' + observation(element.get('partial_state')) +
            ' (' + str(len(element.get('strict_partial_times_s') or [])) + '표본) / 표본 손상 비감소: ' + observation(element.get('sampled_damage_nondecrease')) +
            ' / 초기 기준계 압축 부호: ' + observation(element.get('sampled_initial_basis_compressive_sign')) +
            '\n원 표본 ' + str(len(self._samples)) + '개 / 누락 ' + str(len(self._missing)) + '개' +
            (' — 누락 시각과 사유는 누락 표본 탭에서 확인하세요. 누락 구간은 미확인입니다.' if self._missing else ''))
        evidence = [('부분 손상으로 보존한 시각', str(len(element.get('strict_partial_times_s') or [])) + '개'),
            ('손상 감소로 보존한 단계', str(len(element.get('damage_decrease_steps') or [])) + '개'),
            ('초기 기준계 압축 표본', str(len(element.get('compression_samples') or [])) + '개'),
            ('연속 이력', '표본 사이 구간은 미확인'), ('구성법칙 수치 기준', self._verdict('constitutive_numerical_criterion')),
            ('native 손상 소산 에너지', '미확인 — 계산하거나 합성하지 않음'), ('피로 법칙', '미구현')]
        for step in element.get('damage_decrease_steps') or []:
            if isinstance(step, dict):
                evidence.append(('손상 감소 원 단계', shown(step.get('before_time_s')) + ' → ' + shown(step.get('after_time_s')) +
                    ' s / 손상 ' + shown(step.get('before')) + ' → ' + shown(step.get('after'))))
        for time in element.get('strict_partial_times_s') or []:
            evidence.append(('부분 손상 원 시각 [s]', shown(time)))
        for sample in element.get('compression_samples') or []:
            if isinstance(sample, dict):
                evidence.append(('압축 원 시각 ' + shown(sample.get('time_s')) + ' s',
                    '변위 변화 ' + shown(sample.get('opening_change_mm')) + ' mm / traction ' + shown(sample.get('traction_mpa')) + ' MPa'))
        self._fill(self.evidence, evidence)
        partial = element.get('strict_partial_times_s') or []
        self._row = next((i for i, s in enumerate(self._samples) if isinstance(s, dict) and s.get('time_s') in partial), 0) if self._samples else -1
        self._component_changed()

    def _quantities(self, sample):
        component = self.component.currentData()
        return ((sample.get('paired_change_mm') or {}).get(component),
            (sample.get('derived_initial_basis_traction_mpa') or {}).get(component),
            ((sample.get('mean_comparison') or {}).get(component) or {}))

    def _component_changed(self, *_):
        rows = []
        for sample in self._samples:
            sample = sample if isinstance(sample, dict) else {}
            change, traction, comparison = self._quantities(sample)
            rows.append((shown(sample.get('time_s')), shown(sample.get('native_mean_damage')), shown(change), shown(traction),
                secant_text(change, comparison.get('secant_mpa_per_mm')), activity(sample.get('active')), bulk_text(sample),
                ' / '.join(str(reason) for reason in sample.get('reasons', [])) or '사유 기록 없음'))
        self._fill(self.table, rows)
        self.table.blockSignals(True)
        if self._row >= 0:
            self.table.setCurrentCell(self._row, 0); self.table.selectRow(self._row)
        self.table.blockSignals(False)
        self._update_selected(); self._draw()

    def _sample_changed(self, row, *_):
        self._row = row; self._update_selected(); self._draw()

    def _update_selected(self):
        sample = self._samples[self._row] if 0 <= self._row < len(self._samples) else {}
        sample = sample if isinstance(sample, dict) else {}
        change, traction, comparison = self._quantities(sample)
        self.selected.setText('선택 시각 ' + shown(sample.get('time_s')) + ' s / 계면 ' + activity(sample.get('active')) +
            ' / 인접 벌크: ' + bulk_text(sample))
        self._fill(self.values, [('원 시각', shown(sample.get('time_s')), 's'),
            ('native 평균 손상', shown(sample.get('native_mean_damage')), '1'),
            (self.component.currentText() + ' 대응면 변위 변화', shown(change), 'mm'),
            ('초기 기준계 투영 traction', shown(traction), 'MPa'),
            ('평균값 surrogate', shown(comparison.get('mean_surrogate_mpa')), 'MPa'),
            ('native 투영값 − surrogate', shown(comparison.get('native_projection_minus_surrogate_mpa')), 'MPa'),
            ('할선 강성 (접선 강성 아님)', secant_text(change, comparison.get('secant_mpa_per_mm')), 'MPa/mm'),
            ('계면 활성 상태', activity(sample.get('active')), '—'), ('인접 벌크', bulk_text(sample), '—'),
            ('사유', ' / '.join(str(v) for v in sample.get('reasons', [])) or '사유 기록 없음', '—')])
        raw = {'selected_sample': sample, 'element': {k: v for k, v in self._current_element().items() if k != 'samples'},
            'audit': {k: v for k, v in self._audit.items() if k != 'elements'}}
        self.raw.setPlainText(json.dumps(raw, ensure_ascii=False, indent=2))

    def _plot_values(self, sample):
        change, traction, comparison = self._quantities(sample)
        kind = self.plot_kind.currentData()
        if kind == 'traction_opening':
            return change, traction
        return sample.get('time_s'), {'damage': sample.get('native_mean_damage'), 'change': change,
            'traction': traction, 'secant': comparison.get('secant_mpa_per_mm')}.get(kind)

    def _draw(self, *_):
        self.figure.clear(); axes = self.figure.add_subplot(111)
        kind = self.plot_kind.currentData()
        xy = [self._plot_values(s if isinstance(s, dict) else {}) for s in self._samples]
        # Preserve position/order and gaps. Never drop missing points and bridge the gap.
        xs, ys, self._curve_rows = [], [], []
        unknown_clock = any(not finite(row.get('time_s')) for row in self._missing)
        missing_times = [row['time_s'] for row in self._missing if finite(row.get('time_s'))]
        for index, (x, y) in enumerate(xy):
            before = self._samples[index - 1].get('time_s') if index and isinstance(self._samples[index - 1], dict) else None
            after = self._samples[index].get('time_s') if isinstance(self._samples[index], dict) else None
            # An unavailable frame is absent from samples, not an interpolated point.
            # Unknown missing clock cannot justify connecting any two retained samples.
            gap = index and (unknown_clock or finite(before) and finite(after) and any(before <= t <= after for t in missing_times))
            if gap:
                xs.append(math.nan); ys.append(math.nan); self._curve_rows.append(None)
            xs.append(x if finite(x) and finite(y) else math.nan)
            ys.append(y if finite(x) and finite(y) else math.nan)
            self._curve_rows.append(index)
        self._curve, = axes.plot(xs, ys, '.-', linewidth=1, markersize=3, picker=5, label='원 표본')
        if 0 <= self._row < len(xy) and finite(xy[self._row][0]) and finite(xy[self._row][1]):
            axes.plot([xy[self._row][0]], [xy[self._row][1]], 'o', markerfacecolor='none', markeredgecolor='#dc7100', markersize=9, label='선택 표본')
        if not any(finite(x) and finite(y) for x, y in xy):
            axes.text(.5, .5, '이 곡선에 사용할 원값이 없습니다.', ha='center', transform=axes.transAxes)
        labels = {'traction_opening': ('대응면 변위 변화 [mm]', '초기 기준계\ntraction [MPa]'),
            'damage': ('시간 [s]', 'native 평균\n손상 [1]'), 'change': ('시간 [s]', '대응면 변위 변화\n[mm]'),
            'traction': ('시간 [s]', '초기 기준계\ntraction [MPa]'), 'secant': ('시간 [s]', '할선 강성\n[MPa/mm]')}
        xlabel, ylabel = labels[kind]
        axes.set_xlabel(xlabel); axes.set_ylabel(ylabel)
        axes.set_title(('계면 평균 손상' if kind == 'damage' else self.component.currentText()) + ' / 기록 순서 ' + str(len(self._samples)) + '표본')
        axes.ticklabel_format(style='plain', axis='x', useOffset=False)
        # ASCII scientific notation keeps tiny retained traction readable without
        # an additive offset, zero threshold, altered locator or data rounding.
        axes.yaxis.set_major_formatter(FuncFormatter(lambda value, position: format(value, '.6g')))
        axes.grid(alpha=.2); axes.legend(loc='best'); self.canvas.draw_idle()

    def _picked(self, event):
        if event.artist is self._curve and len(event.ind):
            index = int(event.ind[0])
            row = self._curve_rows[index] if 0 <= index < len(self._curve_rows) else None
            if row is not None:
                self.table.setCurrentCell(row, 0); self.table.selectRow(row)
