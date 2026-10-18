"""Compare recorded mesh norms from one actual PDE run; no re-evaluation."""
from copy import deepcopy
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog,QVBoxLayout,QLabel,QSplitter,QTableWidget,QTableWidgetItem,QHeaderView
from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from .appearance import configure_plot_fonts


class PDEStudyWindow(QDialog):
    def __init__(self,result,parent=None):
        super().__init__(parent);configure_plot_fonts()
        self.setWindowTitle('메시와 오차 비교');self.resize(1100,780)
        result=deepcopy(result);diagnostics=result.get('diagnostics',{})
        self.rows=diagnostics.get('mesh_studies',[])
        # The installed scikit-fem producer records `dofs`; FEniCSx records
        # `global_dofs`. Keep the retained rows and norm definitions unchanged.
        self.reference=diagnostics.get('declaration',{}).get('model',{}).get('reference')
        layout=QVBoxLayout(self)
        layout.addWidget(QLabel('저장된 메시별 기준 오차'))
        split=QSplitter(Qt.Orientation.Vertical);layout.addWidget(split,1)
        self.figure=Figure(constrained_layout=True);self.canvas=FigureCanvasQTAgg(self.figure);self.canvas.setMinimumHeight(300);split.addWidget(self.canvas)
        self.table=QTableWidget(len(self.rows),5);self.table.setHorizontalHeaderLabels(['한 축 셀 수','자유도','L2 오차','H1 반노름 오차','상대 대수 잔차'])
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        for i,row in enumerate(self.rows):
            for j,key in enumerate(('cells_per_axis','global_dofs','l2_error','h1_seminorm_error','relative_residual')):
                value=self.dofs(row) if key=='global_dofs' else row.get(key)
                label='미제공' if value is None else format(value,'.7g')
                if key=='l2_error':label+=' ['+row.get('l2_unit','?')+']'
                if key=='h1_seminorm_error':label+=' ['+row.get('h1_unit','?')+']'
                item=QTableWidgetItem(label);item.setToolTip(repr(value));self.table.setItem(i,j,item)
        split.addWidget(self.table);split.setSizes([440,210]);self.table.currentCellChanged.connect(lambda *_:self.draw())
        self.detail=QLabel('선택한 생산자에 메시 norm 표가 없습니다.' if not self.rows else '')
        self.detail.setWordWrap(True);layout.addWidget(self.detail)
        self.canvas.mpl_connect('pick_event', self._point_picked)
        if self.rows:self.table.selectRow(0)
        self.draw()

    @staticmethod
    def dofs(row):
        return row.get('global_dofs',row.get('dofs'))

    def row_reference(self,row):
        return row.get('reference',self.reference)

    def _point_picked(self,event):
        rows=getattr(event.artist,'_study_rows',[])
        if len(getattr(event,'ind',[])) and int(event.ind[0])<len(rows):
            row=rows[int(event.ind[0])]
            self.table.selectRow(row)
            self.table.scrollToItem(self.table.item(row,0))

    def draw(self):
        self.figure.clear()
        selected=self.table.currentRow()
        for index,(name,unitkey,label) in enumerate((('l2_error','l2_unit','L2'),('h1_seminorm_error','h1_unit','H1 반노름')),1):
            ax=self.figure.add_subplot(1,2,index)
            groups={}
            for row_index,row in enumerate(self.rows):
                if row.get(name) is not None and self.dofs(row) is not None:
                    groups.setdefault((row.get(unitkey),self.row_reference(row),row.get('norm_definition')),[]).append((row_index,row))
            for (unit,reference,definition),rows in groups.items():
                line,=ax.plot([self.dofs(r) for _,r in rows],[r[name] for _,r in rows],'o-',
                    picker=5,label=label+' ['+str(unit)+']'+(' / '+str(reference) if len(groups)>1 else ''))
                line._study_rows=[i for i,_ in rows]
                for row_index,row in rows:
                    if row_index==selected:
                        ax.scatter([self.dofs(row)],[row[name]],s=95,facecolors='none',
                                   edgecolors='#d56c22',linewidths=2,zorder=3)
            ax.set_xlabel('실제 자유도');ax.set_ylabel(label+' 오차')
            if groups:ax.legend()
        row=self.table.currentRow()
        if 0<=row<len(self.rows):
            data=self.rows[row];self.detail.setText('기준식: '+str(self.row_reference(data) or '미제공')+' / '+str(data.get('norm_definition') or '노름 정의 미제공')+
                ('\n잔차 정의: '+str(data['residual_definition']) if data.get('residual_definition') else '')+
                (' / 적분 차수: '+str(data['quadrature_degree']) if data.get('quadrature_degree') is not None else '')+
                (' / 자유도 미제공: 그래프에 표시하지 않습니다.' if self.dofs(data) is None else '')+
                (' / 기준식 평가 실패: '+data['reference_error'] if data.get('reference_error') else ''))
        self.canvas.draw_idle()
