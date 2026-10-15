"""Read-only curves of exactly the currently fetched native comparison rows."""
from copy import deepcopy
import math
from PySide6.QtCore import Signal, Slot
from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from .appearance import configure_plot_fonts


class ComparisonPlot(QDialog):
    pointSelected = Signal(int)

    def __init__(self, payload, basis, parent=None):
        super().__init__(parent)
        self.rows = deepcopy(payload.get('rows', []))
        self.basis = deepcopy(basis)
        self.recipe = self.basis['draft']
        self._selected_index = None
        self._markers = []
        self.setWindowTitle('비교 곡선'); self.resize(900, 620)
        configure_plot_fonts()
        layout=QVBoxLayout(self)
        controls=QHBoxLayout()
        controls.addWidget(QLabel('표에서 읽은 ' + str(len(self.rows)) + '개 점'))
        controls.addStretch()
        self.axis=QComboBox()
        for title,key in [('원본 점 순서','point_index'),('X 좌표','x'),('Y 좌표','y'),('Z 좌표','z')]:
            self.axis.addItem(title,key)
        controls.addWidget(self.axis); layout.addLayout(controls)
        self.figure=Figure(constrained_layout=True)
        self.canvas=FigureCanvasQTAgg(self.figure); layout.addWidget(self.canvas,1)
        self.caption=QLabel(); layout.addWidget(self.caption)
        self.axis.currentIndexChanged.connect(self.draw)
        self.canvas.mpl_connect('pick_event', self.pick)
        self.draw()

    def draw(self):
        self.figure.clear()
        top,bottom=self.figure.subplots(2,1,sharex=True)
        self._axes, self._markers = (top, bottom), []
        axis=self.axis.currentData()
        x=[row.get('point_index') if axis=='point_index' else row['coordinates']['xyz'.index(axis)] for row in self.rows]
        def values(key):
            return [row.get(key) if row.get(key) is not None and math.isfinite(row[key]) else math.nan for row in self.rows]
        # Mesh point order is not a physical curve path. Markers avoid invented
        # connecting segments across spatial or quality gaps.
        top.plot(x,values('a'),'o',label='변환 A',picker=5)
        top.plot(x,values('b'),'x',label='변환 B',picker=5)
        bottom.plot(x,values('delta'),'o',label='차이',picker=5)
        units=self.recipe.get('target',{}).get('units','')
        top.set_ylabel('응답 ['+str(units)+']'); bottom.set_ylabel('차이 ['+str(units)+']')
        coordinate_unit=self.recipe.get('a',{}).get('coordinate_units','')
        bottom.set_xlabel('원본 점 순서' if axis=='point_index' else axis.upper()+' ['+str(coordinate_unit)+']')
        for ax in (top,bottom): ax.grid(alpha=.25); ax.legend()
        selection = self.recipe.get('selection', '')
        selection_label = {'scalar': '스칼라 값', 'magnitude': '크기'}.get(selection, str(selection).upper())
        self._caption = ('적용 전 미리보기' if self.basis.get('preview') else '저장된 적용 결과') + '   ' + selection_label
        self.caption.setText(self._caption)
        if self._selected_index is not None:
            self.select_sample(self._selected_index, self.basis)
        self.canvas.draw_idle()

    @Slot(int, object)
    def select_sample(self, index, basis):
        keys = ('document_id', 'session_id', 'object_ref', 'revision', 'preview')
        if (not all(self.basis.get(key) for key in keys[:4])
                or any(basis.get(key) != self.basis.get(key) for key in keys)):
            return False
        for marker in self._markers:
            marker.remove()
        self._markers = []
        self._selected_index = index
        self.caption.setText(self._caption)
        row = next((row for row in self.rows if row.get('point_index') == index), None)
        if row is not None:
            axis = self.axis.currentData()
            x = index if axis == 'point_index' else row['coordinates']['xyz'.index(axis)]
            for ax, fields in zip(self._axes, (('a', 'b'), ('delta',))):
                values = [row.get(key) for key in fields if isinstance(row.get(key), (int, float)) and math.isfinite(row[key])]
                if values:
                    self._markers.append(ax.scatter([x]*len(values), values, s=85, facecolors='none', edgecolors='black'))
            self.caption.setText(self._caption + ' / 선택한 점 ' + str(index))
        self.canvas.draw_idle()
        return row is not None

    def pick(self,event):
        if len(event.ind):
            index=int(event.ind[0])
            if 0<=index<len(self.rows):
                self.pointSelected.emit(self.rows[index]['point_index'])
