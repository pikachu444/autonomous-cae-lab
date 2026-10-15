"""Read-only P1 transfer view: distinct original snapshots and receiver mesh."""
import json
import math
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QLabel, QComboBox, QSplitter,
    QTableWidget, QTableWidgetItem, QHeaderView)
from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg


def text(value):
    if value is None:
        return '—'
    if type(value) is bool:
        return '예' if value else '아니오'
    if type(value) in (int, float):
        return format(value, '.8g')
    if isinstance(value, list):
        return ', '.join(text(item) for item in value)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, indent=2)
    return str(value)


class TemperatureTransferView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.data = None
        layout = QVBoxLayout(self)
        self.details = QLabel(); self.details.setWordWrap(True)
        self.selector = QComboBox(); self.selector.setObjectName('temperatureSnapshotView')
        self.selector.currentIndexChanged.connect(self._show_selection)
        layout.addWidget(self.details); layout.addWidget(self.selector)
        splitter = QSplitter(Qt.Orientation.Vertical); layout.addWidget(splitter, 1)
        self.figure = Figure(constrained_layout=True); self.canvas = FigureCanvasQTAgg(self.figure)
        self.canvas.setMinimumHeight(180); splitter.addWidget(self.canvas)
        self.table = QTableWidget(0, 0); self.table.setObjectName('temperatureExactValues')
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.itemSelectionChanged.connect(self._draw)
        splitter.addWidget(self.table); splitter.setSizes([300, 240])
        self.point = QLabel(); self.point.setWordWrap(True); layout.addWidget(self.point)
        self.canvas.mpl_connect('pick_event', self._pick)

    def clear(self, *, keep_selection=False):
        self.data = None; self.table.setRowCount(0); self.details.clear(); self.point.clear()
        if not keep_selection:
            self.selector.blockSignals(True); self.selector.clear(); self.selector.blockSignals(False)
        self.figure.clear(); self.canvas.draw_idle()

    def set_data(self, data):
        selected = self.selector.currentData()
        self.data = data
        self.selector.blockSignals(True); self.selector.clear()
        self.selector.addItem('수신 메시 — 보간값 / 실제 수신 입력', ('receiver', None))
        for source in data['source_snapshots']:
            metadata = source['metadata']
            self.selector.addItem('공급 시점 ' + str(source['snapshot_index'] + 1) + ' / ' + source.get('name', source['stage'])
                + ' / ' + text(metadata.get('time')) + ' ' + str(metadata.get('time_units') or '?'), ('source', source['snapshot_index']))
            self.selector.setItemData(self.selector.count() - 1, text(metadata), Qt.ItemDataRole.ToolTipRole)
        index = next((i for i in range(self.selector.count()) if self.selector.itemData(i) == selected), -1)
        self.selector.setCurrentIndex(index if index >= 0 else 0); self.selector.blockSignals(False)
        policy = data['declaration']['options']['time']
        clock = data.get('clock') or {}
        sources = ', '.join(text(s['metadata'].get('time')) + ' ' + str(s['metadata'].get('time_units') or '?')
                            for s in data['source_snapshots'])
        self.details.setText('P1 절점 보간 · 보존적 전달 아님 · 모든 수신 절점 필수\n'
            + '공급 ' + sources + ' → 수신 ' + text(policy['receiver']['value']) + ' ' + policy['receiver']['unit']
            + ' (가중치 ' + (' / '.join(text(w) for w in (clock.get('weights') or [])) or '확인 불가') + ')'
            + (' · 동일 정상 상태 선언' if policy['mode'] == 'steady_relabel' else '')
            + ('\n전달할 수 없는 수신 절점: ' + text(data['invalid_receiver_ids']) if data.get('invalid_receiver_ids') else ''))
        self.details.setToolTip(text({'time_policy':policy, 'clock':clock, 'temperature':data.get('temperature'),
            'source_references':[s['reference'] for s in data['source_snapshots']]}))
        self._show_selection()

    def _show_selection(self, *_):
        if not self.data or self.selector.currentData() is None:
            return
        kind, index = self.selector.currentData()
        if kind == 'receiver':
            self.rows = self.data['receiver_rows']; self.metadata = self.data['metadata']
            unit = str(self.metadata.get('unit') or '?')
            headers = ['절점', '좌표 [m]', '보간 ['+unit+']', '수신 ['+unit+']', '유효', '차이 ['+unit+']', '공급 시점']
            columns = lambda row: [row['node'], row['coordinates'], row['mapped'], row['received'],
                row['valid_mask'], row['difference'], str(len(row['spatial_sources'])) + '개 시점']
        else:
            source = self.data['source_snapshots'][index]
            self.rows = source['rows']; self.metadata = source['metadata']
            headers = ['원 절점', '좌표 [m]', '공급 ['+str(self.metadata.get('unit') or '?')+']', '유효', '유한값']
            columns = lambda row: [row['node'], row['coordinates'], row['value'], row['mask'], row['finite']]
        self.table.blockSignals(True); self.table.setRowCount(0); self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers); self.table.setRowCount(len(self.rows))
        for i, row in enumerate(self.rows):
            for j, value in enumerate(columns(row)):
                item = QTableWidgetItem(text(value))
                detail = text(row)
                if kind == 'receiver' and j == 6:
                    detail = '\n'.join('공급 시점 ' + str(k + 1) + ': 삼각형 ' + text(s.get('source_cell'))
                        + ' / 원 절점 ' + text(s.get('source_node_ids')) + ' / 가중치 ' + text(s.get('weights'))
                        for k, s in enumerate(row['spatial_sources'])) + '\n\n' + text(row)
                item.setToolTip(detail); self.table.setItem(i, j, item)
        self.table.blockSignals(False)
        self._draw()

    def _draw(self):
        self.figure.clear(); ax = self.figure.add_subplot(111); self.point.clear()
        if not self.data or self.selector.currentData() is None:
            self.canvas.draw_idle(); return
        receiver = self.selector.currentData()[0] == 'receiver'
        key = 'mapped' if receiver else 'value'
        # Never join node-ID curves from different meshes or invent triangle
        # faces across holes. This is a paged scatter of exact retained rows.
        def point(row):
            xy=row.get('coordinates')
            return isinstance(xy,list) and len(xy)==2 and all(type(v) in (int,float) and math.isfinite(v) for v in xy)
        self.plotted = [i for i, row in enumerate(self.rows) if point(row) and type(row.get(key)) in (float, int) and math.isfinite(row[key])]
        if self.plotted:
            rows = [self.rows[i] for i in self.plotted]
            points = ax.scatter([r['coordinates'][0] for r in rows], [r['coordinates'][1] for r in rows],
                c=[r[key] for r in rows], s=24, picker=True)
            self.figure.colorbar(points, ax=ax, label=str(self.metadata.get('unit') or '?'))
        missing = [r for r in self.rows if r.get(key) is None and point(r)]
        if missing:
            ax.scatter([r['coordinates'][0] for r in missing], [r['coordinates'][1] for r in missing], marker='x', label='전달 불가')
            ax.legend()
        selected = self.table.currentRow()
        if 0 <= selected < len(self.rows) and point(self.rows[selected]):
            row = self.rows[selected]
            ax.scatter(*row['coordinates'], s=95, facecolors='none', edgecolors='black')
            self.point.setText('절점 '+str(row['node'])+' / 좌표 '+text(row['coordinates'])+' m / '+text(row.get(key))+' '+str(self.metadata.get('unit') or '?'))
            self.point.setToolTip(text(row))
        ax.set_aspect('equal'); ax.set_xlabel('x [m]'); ax.set_ylabel('y [m]')
        ax.set_title('수신 메시의 보간값' if receiver else '원 공급 메시의 보존값')
        self.canvas.draw_idle()

    def _pick(self, event):
        if len(event.ind) and int(event.ind[0]) < len(self.plotted):
            self.table.selectRow(self.plotted[int(event.ind[0])])
