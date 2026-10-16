"""Display retained sample columns; no native selection or numerical evaluation."""
import math

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QVBoxLayout, QWidget
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure


class ResultPlot(QWidget):
    rowSelected = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        from .appearance import configure_plot_fonts
        configure_plot_fonts()
        layout = QVBoxLayout(self)
        self.value_summary = QLabel()
        self.value_summary.setWordWrap(True)
        self.value_summary.setProperty('appearanceRole', 'section')
        layout.addWidget(self.value_summary)
        row = QHBoxLayout()
        row.addWidget(QLabel('표시할 응답'))
        self.column = QComboBox()
        self.column.setAccessibleName('그래프의 측정 응답')
        row.addWidget(self.column, 1)
        layout.addLayout(row)
        self.figure = Figure(figsize=(6, 4), constrained_layout=True)
        self.canvas = FigureCanvasQTAgg(self.figure)
        layout.addWidget(self.canvas, 1)
        self._payload, self._recipe = {}, {}
        self._row_indices = []
        self.canvas.mpl_connect('pick_event', self._picked)
        self.column.currentIndexChanged.connect(self.draw)
        self.draw()

    def set_samples(self, payload, recipe):
        self._payload, self._recipe = payload or {}, recipe or {}
        old = self.column.currentData()
        self.column.blockSignals(True)
        self.column.clear()
        seen = set()
        for row in self._payload.get('rows', []):
            for name, value in row.get('values', {}).items():
                measurement = self._recipe.get('measurement')
                primary = {'gauge': 'GaugeRelativeDisplacement', 'gauge_time': 'GaugeRelativeDisplacement', 'surface_time': 'SurfaceAreaAverage', 'surface_average': 'SurfaceAreaAverage'}.get(measurement)
                if primary and name != primary:
                    continue
                for component in range(len(value)) if isinstance(value, list) else [None]:
                    key = (name, component)
                    if key not in seen:
                        seen.add(key)
                        label = {'GaugeRelativeDisplacement': '두 점 상대변위', 'SurfaceAreaAverage': '면적 가중 면 평균'}.get(name, name)
                        self.column.addItem(label + (f' [{component}]' if component is not None else ''), key)
        index = self.column.findData(old)
        self.column.setCurrentIndex(max(0, index) if self.column.count() else -1)
        self.column.blockSignals(False)
        self.draw()

    def draw(self, *_):
        self.figure.clear()
        axes = self.figure.add_subplot(111)
        key = self.column.currentData()
        self._row_indices = []
        if key is None:
            self.value_summary.clear()
            axes.set_axis_off()
            axes.text(.5, .5, '측정 결과를 읽으면 그래프가 표시됩니다.', ha='center', va='center', transform=axes.transAxes)
        else:
            xs, ys = [], []
            invalid = 0
            measurement = self._recipe.get('measurement')
            axis_name = 'Time' if measurement in ('time', 'gauge_time', 'surface_time') else 'arc_length' if measurement == 'path' else 'SampleIndex' if measurement == 'surface_average' else None
            single_clock = measurement == 'gauge' and self._recipe.get('time') is not None
            single = len(self._payload.get('rows', [])) == 1
            for index, row in enumerate(self._payload.get('rows', [])):
                values = row.get('values', {})
                value = values.get(key[0])
                if key[1] is not None:
                    value = value[key[1]] if isinstance(value, list) and len(value) > key[1] else None
                x = values.get(axis_name) if axis_name else self._recipe['time'] if single_clock else index + 1
                state = row.get('validity', {}).get(key[0], 'valid')
                if isinstance(state, list) and key[1] is not None:
                    state = state[key[1]] if len(state) > key[1] else 'unknown'
                valid = state in ('valid', True) and row.get('valid', True) is not False and values.get('vtkValidMask', 1) != 0
                if isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x):
                    finite = isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
                    xs.append(x); ys.append(value if valid and finite else math.nan)
                    self._row_indices.append(index)
                    invalid += int(not (valid and finite))
            axes.plot(xs, ys, 'o-' if len(xs) > 1 else 'o', picker=5)
            axes.axhline(0, color='0.65', linewidth=.7)
            axes.grid(True, alpha=.2)
            unit = self._recipe.get('units') or '단위 미지정'
            axes.set_ylabel(self.column.currentText() + ' [' + str(unit) + ']')
            axes.set_xlabel(('시각 [' + str(self._recipe.get('time_units') or '?') + ']') if axis_name == 'Time' or single_clock else
                            ('경로 길이 [' + str(self._recipe.get('coordinate_units') or '?') + ']') if axis_name == 'arc_length' else '결과 행')
            if single and xs:
                axes.set_xticks(xs, [str(xs[0]) if axis_name or single_clock else '단일 측정'])
            if single and ys:
                value = format(ys[0], '+.6g') if math.isfinite(ys[0]) else '무효 값'
                clock = (' / 시각 ' + str(self._recipe['time']) + ' [' + str(self._recipe.get('time_units') or '?') + ']') if single_clock else ''
                self.value_summary.setText(self.column.currentText() + ': ' + value + ' [' + str(unit) + ']' + clock +
                    (' / (B − A) · 방향' if measurement == 'gauge' else '') + (' / 유효' if math.isfinite(ys[0]) else ' / 원표 확인'))
            else:
                self.value_summary.setText(self.column.currentText() + ': 조회 표본 ' + str(len(xs)) + '개 [' + str(unit) + ']')
            axes.set_title(('조회한 측정값' if any(math.isfinite(y) for y in ys) else '유효한 표시 값 없음') +
                           (f' — 무효 {invalid}행 (원표 보존)' if invalid else ''))
        self.canvas.draw()

    def _picked(self, event):
        if len(event.ind) and 0 <= int(event.ind[0]) < len(self._row_indices):
            self.rowSelected.emit(self._row_indices[int(event.ind[0])])
