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
        layout=QVBoxLayout(self)
        layout.addWidget(QLabel('선택한 계산의 기준식과 norm. 다른 정의의 norm을 같은 곡선으로 합치지 않습니다.'))
        split=QSplitter(Qt.Orientation.Vertical);layout.addWidget(split,1)
        self.figure=Figure(constrained_layout=True);self.canvas=FigureCanvasQTAgg(self.figure);self.canvas.setMinimumHeight(300);split.addWidget(self.canvas)
        self.table=QTableWidget(len(self.rows),5);self.table.setHorizontalHeaderLabels(['한 축 셀 수','자유도','L2 오차','H1 준노름 오차','상대 대수 잔차'])
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        for i,row in enumerate(self.rows):
            for j,key in enumerate(('cells_per_axis','global_dofs','l2_error','h1_seminorm_error','relative_residual')):
                value=row.get(key);label='—' if value is None else format(value,'.7g')
                if key=='l2_error':label+=' ['+row.get('l2_unit','?')+']'
                if key=='h1_seminorm_error':label+=' ['+row.get('h1_unit','?')+']'
                item=QTableWidgetItem(label);item.setToolTip(repr(value));self.table.setItem(i,j,item)
        split.addWidget(self.table);split.setSizes([440,210]);self.table.currentCellChanged.connect(lambda *_:self.draw())
        self.detail=QLabel('선택한 생산자에 메시 norm 표가 없습니다.' if not self.rows else '')
        self.detail.setWordWrap(True);layout.addWidget(self.detail);self.draw()
    def draw(self):
        self.figure.clear()
        for index,(name,unitkey,label) in enumerate((('l2_error','l2_unit','L2'),('h1_seminorm_error','h1_unit','H1 준노름')),1):
            ax=self.figure.add_subplot(1,2,index)
            groups={}
            for row in self.rows:
                if row.get(name) is not None:
                    groups.setdefault((row.get(unitkey),row.get('reference'),row.get('norm_definition')),[]).append(row)
            for (unit,reference,definition),rows in groups.items():
                ax.plot([r['global_dofs'] for r in rows],[r[name] for r in rows],'o-',label=label+' ['+str(unit)+']')
            ax.set_xlabel('실제 자유도');ax.set_ylabel(label+' 오차')
            if groups:ax.legend()
        row=self.table.currentRow()
        if 0<=row<len(self.rows):
            data=self.rows[row];self.detail.setText('기준식: '+data['reference']+' / '+data['norm_definition'])
        self.canvas.draw_idle()
