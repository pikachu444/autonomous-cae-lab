"""Read-only curves of exactly the currently fetched native comparison rows."""
from copy import deepcopy
import math
from PySide6.QtCore import Signal
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
        self.caption.setText(('적용 전 미리보기' if self.basis.get('preview') else '저장된 적용 결과')+
                             '   ' + str(self.recipe.get('selection','')))
        self.canvas.draw_idle()

    def pick(self,event):
        if len(event.ind):
            index=int(event.ind[0])
            if 0<=index<len(self.rows):
                self.pointSelected.emit(self.rows[index]['point_index'])
