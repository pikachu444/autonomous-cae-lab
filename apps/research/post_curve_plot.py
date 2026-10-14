"""Original and aligned retained curves, with linked plot/table row identity."""
from copy import deepcopy
import math
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QLabel, QTableWidget, QTableWidgetItem,
    QAbstractItemView, QSplitter, QTabWidget, QHeaderView)
from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg

REASONS = {'valid': '대응', 'outside_b_range': 'B 범위 밖', 'no_exact_sample': '일치 표본 없음',
    'missing_segment': '결측 구간', 'gap_exceeds_limit': '허용 간격 초과',
    'b_excluded_or_missing': 'B 제외·결측', 'a_excluded_or_missing': 'A 제외·결측',
    'axis_missing': '축 결측', 'zero_a': '기준값 0', 'absolute_temperature_disabled': '절대온도 변화율 없음',
    'difference_unavailable': '차이 없음', 'nonfinite_difference': '연산 범위 초과',
    'nonfinite_percent': '변화율 범위 초과', 'b_axis_conversion_overflow': 'B 축 변환 범위 초과',
    'a_value_conversion_overflow': 'A 단위 변환 범위 초과', 'b_value_conversion_overflow': 'B 단위 변환 범위 초과'}


def text(value):
    if value is None:
        return '—'
    if isinstance(value, bool):
        return '유효' if value else '제외'
    if type(value) in (int, float):
        return format(value, '.7g')
    return REASONS.get(value, value) if isinstance(value, str) else str(value)


class CurvePlot(QDialog):
    rowSelected = Signal(int)

    def __init__(self, payload, basis, parent=None):
        super().__init__(parent)
        from .appearance import configure_plot_fonts
        configure_plot_fonts()
        self.payload, self.basis = deepcopy(payload), deepcopy(basis)
        self.setWindowTitle('곡선 비교'); self.resize(1100, 780)
        layout = QVBoxLayout(self)
        summary = payload['summary']; sources = summary['sources']
        status = QLabel(summary.get('blocked') or
            ('대응 가능한 표본 '+str(summary['valid_count'])+'개 / '+str(summary['count_a'])+'개'))
        status.setWordWrap(True); layout.addWidget(status)
        split = QSplitter(Qt.Orientation.Vertical); layout.addWidget(split, 1)
        figure = Figure(constrained_layout=True)
        grid = figure.add_gridspec(2, 2)
        self.axes = {'a': figure.add_subplot(grid[0, 0]), 'b': figure.add_subplot(grid[0, 1]),
                     'aligned': figure.add_subplot(grid[1, :])}
        self.canvas = FigureCanvasQTAgg(figure); self.canvas.setMinimumHeight(310); split.addWidget(self.canvas)
        self.tabs = QTabWidget(); self.tables = {}; self.points = {}; self.markers = {}
        for tag, label in (('a', '원곡선 A'), ('b', '원곡선 B'), ('aligned', '대응과 차이')):
            table = QTableWidget(); table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
            table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
            table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
            table.setAlternatingRowColors(True); table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
            table.itemSelectionChanged.connect(lambda tag=tag: self.select_table(tag))
            self.tables[tag] = table; self.tabs.addTab(table, label)
        split.addWidget(self.tabs); split.setSizes([470, 210])
        for tag in ('a', 'b'):
            ax = self.axes[tag]; rows = payload['originals'][tag]; source = sources[tag]
            self.fill(tag, rows, [('row_index', '표본'), ('identity', '원행'), ('x', '가로축 ['+str(source['axis'].get('unit','?'))+']'),
                ('y', '원값 ['+str(source['declaration'].get('units','?'))+']'),
                ('quality', '품질'), ('calculation', '계산 포함'), ('exclusion_reason', '제외 사유')])
            self.draw_segments(ax, rows, 'x', 'y', 'C0' if tag == 'a' else 'C1', source['title'])
            ax.set_xlabel(str(source['axis'].get('name', '축'))+' ['+str(source['axis'].get('unit', '?'))+']')
            ax.set_ylabel('['+str(source['declaration'].get('units', '?'))+']')
            ax.set_title('원곡선 '+tag.upper()); ax.grid(True, alpha=.2)
            self.points[tag] = [(r['row_index'], r['x'], r['y']) for r in rows
                                if self.visible(r) and r.get('x') is not None and r.get('y') is not None]
        rows = payload['rows']; ax = self.axes['aligned']
        self.fill('aligned', rows, [('row_index', '표본'), ('a_row', 'A 원행'), ('b_rows', 'B 원행'),
            ('x', '가로축'), ('a', 'A'), ('b', '대응 B'), ('delta', 'B − A'), ('percent', '변화율 [%]'),
            ('reason', '대응 상태'), ('percent_reason', '변화율 상태')])
        self.points['aligned'] = []
        for key, name, color in (('a', '공통 단위 A', 'C0'), ('b', '대응 B', 'C1'), ('delta', 'B − A', 'C2')):
            grouped = []
            for r in rows:
                valid = r.get('a_valid') if key == 'a' else r.get('b_valid') if key == 'b' else r.get('valid')
                segment = r.get('a_segment') if key == 'a' else r.get('b_segment') if key == 'b' else (r.get('a_segment'), r.get('b_segment'))
                grouped.append({'x': r['x'], 'y': r[key], 'quality': bool(valid), 'calculation': bool(valid),
                                'visible': True, 'segment': segment})
            self.draw_segments(ax, grouped, 'x', 'y', color, name)
            self.points['aligned'].extend((r['row_index'], r['x'], r[key]) for r in rows
                if r.get('x') is not None and r.get(key) is not None)
        ax.set_xlabel(str(sources['a']['axis'].get('name','축'))+' ['+str(sources['a']['axis'].get('unit','?'))+']')
        ax.set_ylabel('['+str(summary['recipe'].get('target_unit','?'))+']')
        if rows: ax.legend()
        ax.grid(True, alpha=.2)
        self.canvas.mpl_connect('button_press_event', self.pick)
        self.canvas.draw_idle()

    @staticmethod
    def visible(row):
        return bool(row.get('visible', True))

    def fill(self, tag, rows, columns):
        table = self.tables[tag]
        table.setColumnCount(len(columns)); table.setHorizontalHeaderLabels([label for _, label in columns])
        table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            for j, (key, _) in enumerate(columns):
                value = row.get(key)
                shown = str(row['row_index']+1) if key == 'row_index' else text(value)
                if key in ('identity', 'a_row') and isinstance(value, dict):
                    shown = str(value.get('row', '—'))
                if key == 'b_rows' and isinstance(value, list):
                    shown = ' → '.join(str(v.get('row','—')) for v in value) or '—'
                if key in ('quality', 'calculation') and value in (0, 1):
                    shown = ('정상' if value else '결측·품질 실패') if key == 'quality' else ('포함' if value else '제외')
                item = QTableWidgetItem(shown)
                tooltip = str(value)
                if key == 'b_rows':
                    unit = self.payload['summary']['sources']['a']['axis'].get('unit', '?')
                    tooltip += '\n대응 좌표 ['+str(unit)+']: '+str(row.get('b_axis', []))
                    tooltip += '\n오른쪽 표본 가중치: '+text(row.get('weight'))
                item.setToolTip(tooltip); item.setData(Qt.ItemDataRole.UserRole, row['row_index'])
                table.setItem(i, j, item)

    def draw_segments(self, ax, rows, xkey, ykey, color, label):
        x, y = [], []
        previous = None; labelled = False
        def flush():
            nonlocal labelled
            if x:
                ax.plot(x, y, marker='.', color=color, label=None if labelled else label)
                labelled = True
                x.clear(); y.clear()
        for row in rows:
            # An excluded/invalid row is still visible as a marker; no line can
            # cross it. Hiding a marker never changes calculation inclusion.
            if previous is not None and row.get('segment') != previous: flush()
            previous = row.get('segment')
            if not self.visible(row) or not row.get('quality') or not row.get('calculation'):
                flush()
                if self.visible(row) and row.get(xkey) is not None and row.get(ykey) is not None:
                    ax.scatter([row[xkey]], [row[ykey]], marker='x', color='0.55')
                continue
            if row.get(xkey) is None or row.get(ykey) is None:
                flush(); continue
            x.append(row[xkey]); y.append(row[ykey])
        flush()

    def pick(self, event):
        tag = next((k for k, ax in self.axes.items() if ax is event.inaxes), None)
        if tag is None or not self.points.get(tag):
            return
        points = self.points[tag]; ax = self.axes[tag]
        i, _, _ = min(points, key=lambda row: sum((a-b)**2 for a, b in zip(ax.transData.transform(row[1:]), (event.x, event.y))))
        table = self.tables[tag]
        row = next((j for j in range(table.rowCount()) if table.item(j, 0).data(Qt.ItemDataRole.UserRole) == i), None)
        if row is not None:
            self.tabs.setCurrentWidget(table); table.selectRow(row)

    def select_table(self, tag):
        table = self.tables[tag]; row = table.currentRow()
        if row < 0 or table.item(row, 0) is None:
            return
        index = table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        points = [p for p in self.points.get(tag, []) if p[0] == index]
        if points:
            if tag in self.markers: self.markers[tag].remove()
            self.markers[tag] = self.axes[tag].scatter([p[1] for p in points], [p[2] for p in points],
                s=85, facecolors='none', edgecolors='black')
            self.canvas.draw_idle()
        if tag == 'aligned':
            self.rowSelected.emit(index)
