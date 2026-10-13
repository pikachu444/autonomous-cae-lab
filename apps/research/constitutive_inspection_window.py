"""Read exact constitutive increments; explicit independent probes use Material owner jobs."""
from copy import deepcopy
import uuid
from PySide6.QtCore import Qt,QThreadPool
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QLabel,QComboBox,QPushButton,
 QSplitter,QTabWidget,QTableWidget,QTableWidgetItem,QHeaderView,QInputDialog,QMessageBox,QTreeWidget,QTreeWidgetItem)
from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from .pde_window import _Read
from .appearance import configure_plot_fonts

_READS=set()


def short(value):
    return '—' if value is None else format(value,'.7g') if type(value) in (float,int) else str(value)


def leaves(value,prefix=''):
    if isinstance(value,dict):
        for name,item in value.items():yield from leaves(item,(prefix+' / ' if prefix else '')+str(name))
    elif isinstance(value,list):
        for i,item in enumerate(value):yield from leaves(item,prefix+' ['+str(i)+']')
    else:yield prefix,value



MEASURES={'deformation_gradient':'변형구배 F',
 'infinitesimal_Cauchy':'미소변형 Cauchy','first_Piola':'제1 Piola',
 'physical tensor strain (not engineering shear)':'물리 텐서 변형률',
 'physical infinitesimal Cauchy stress':'물리 텐서 Cauchy',
 'Kelvin strain (sqrt(2) shear)':'Kelvin 변형률 · 전단 ×√2',
 'Kelvin Cauchy stress (sqrt(2) shear)':'Kelvin 응력 · 전단 ×√2'}


def component_value(values,index):
    if not isinstance(values,list):return None
    if len(values)==3 and all(isinstance(row,list) and len(row)==3 for row in values):
        values=[value for row in values for value in row]
    return values[index] if index<len(values) else None


def selected_probes(data,i,j):
    """Select the exact saved component order; no reconstruction of missing inputs/stress."""
    rows=[]
    for fd in data.get('finite_differences',[]):
        backend=data['backend'];name=data['components'][j]
        if backend=='material.felupe':
            if fd.get('increment')!=data['increment'] or fd.get('input_component')!=name:continue
            signed={sign:{'input':fd.get(key+'_input'),'stress':fd.get(key),
                'initial_state':fd.get('initial_state'),'baseline':fd.get('baseline')}
                for sign,key in ((-1,'minus'),(1,'plus'))}
            values=fd.get('finite_difference');difference=component_value(values,i)
        else:
            if backend=='material.mfront.user' and fd.get('component')!=name:continue
            actual=[p for p in fd.get('probes',[]) if backend=='material.mfront.user' or p.get('column')==j]
            signed={}
            for p in actual:
                finite=backend=='material.mfront.hyperelastic';user=backend=='material.mfront.user'
                state=p.get('state',{}).get('s1',{})
                signed[p['sign']]={'input':p.get('deformation_gradient') if finite else
                    p.get('input_strain_kelvin',state.get('gradients')) if user else p.get('gradients_kelvin'),
                    'stress':p.get('pk1_stress_mpa') if finite else
                    state.get('thermodynamic_forces') if user else p.get('stress_kelvin_mpa'),
                    'initial_state':p.get('initial_state',p.get('initial_manager')),
                    'final_state':p.get('state',p.get('final_state',p.get('final_manager'))),
                    'integration_return':p.get('integration_return')}
            matrix=fd.get('pk1_tangent_mpa',fd.get('tangent_kelvin_mpa',fd.get('tangent')))
            difference=component_value(fd.get('column_values'),i) if backend=='material.mfront.user' else (
                component_value(matrix[i],j) if isinstance(matrix,list) and i<len(matrix) else None)
        minus=signed.get(-1,{});plus=signed.get(1,{})
        rows.append({'h':fd['h'],'minus_input':component_value(minus.get('input'),j),
            'plus_input':component_value(plus.get('input'),j),'minus_stress':component_value(minus.get('stress'),i),
            'plus_stress':component_value(plus.get('stress'),i),'difference':difference,'signed':signed})
    return rows


def fill_tree(tree,value):
    tree.clear()
    labels={'initial_state':'독립 시작 상태','final_state':'적분 후 상태','input':'섭동한 입력',
            'stress':'응력 원값','baseline':'시작 조건','integration_return':'적분 반환값',
            's0':'초기','s1':'trial','parameters':'물성','deformation_gradient':'변형구배 F','internal_variables':'내부 변수'}
    def add(parent,name,entry):
        item=QTreeWidgetItem(parent,[labels.get(str(name),str(name)),'' if isinstance(entry,(list,dict)) else short(entry)])
        if isinstance(entry,dict):
            for key,part in entry.items():add(item,key,part)
        elif isinstance(entry,list):
            for index,part in enumerate(entry):add(item,str(index+1),part)
    for key,item in value.items():add(tree,'− 섭동' if key==-1 else '+ 섭동',item)
    tree.expandToDepth(1)


class ConstitutiveInspectionWindow(QDialog):
    def __init__(self,client,document_id,job_id,parent=None):
        super().__init__(parent);configure_plot_fonts()
        self.client=client;self.document_id=document_id;self.job_id=job_id
        self._serial=0;self._closed=False;self._data=None;self._children=[]
        self.setWindowTitle('구성식 증분');self.resize(1100,780)
        layout=QVBoxLayout(self);row=QHBoxLayout()
        self.increment=QComboBox();self.increment.currentIndexChanged.connect(self._select)
        self.probe=QPushButton('독립 섭동 계산…');self.probe.clicked.connect(self.request_probe)
        row.addWidget(QLabel('증분'));row.addWidget(self.increment,1);row.addWidget(self.probe);layout.addLayout(row)
        self.status=QLabel('선택한 계산을 읽는 중…');self.status.setWordWrap(True);layout.addWidget(self.status)
        split=QSplitter(Qt.Orientation.Horizontal);layout.addWidget(split,1)
        tabs=self.tabs=QTabWidget();split.addWidget(tabs)
        self.tangent=QTableWidget();self.tangent.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tangent.currentCellChanged.connect(lambda *_:self._plot())
        tabs.addTab(self.tangent,'접선')
        self.states=QTableWidget(0,4);self.states.setHorizontalHeaderLabels(['상태','초기','trial','committed'])
        self.states.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.states.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        tabs.addTab(self.states,'적분 상태')
        self.stress=QTableWidget(0,6);self.stress.setHorizontalHeaderLabels(['물리량','성분','값','단위','측도','기준계'])
        self.stress.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.stress.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        tabs.insertTab(0,self.stress,'변형과 응력')
        evidence=QSplitter(Qt.Orientation.Vertical)
        self.probes=QTableWidget(0,6)
        self.probes.setHorizontalHeaderLabels(['h','− 입력 [1]','+ 입력 [1]','− 응력','+ 응력','중앙차분'])
        self.probes.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.probes.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.probes.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.probes.currentCellChanged.connect(self._probe_selected)
        self.probe_states=QTreeWidget();self.probe_states.setHeaderLabels(['시작 상태와 원자료','보존값'])
        evidence.addWidget(self.probes);evidence.addWidget(self.probe_states);evidence.setSizes([220,350])
        tabs.addTab(evidence,'섭동 원자료')
        self.build=QTableWidget(0,2);self.build.setHorizontalHeaderLabels(['빌드 항목','값'])
        self.build.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.build.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        tabs.addTab(self.build,'빌드')
        self.figure=Figure(constrained_layout=True);self.canvas=FigureCanvasQTAgg(self.figure)
        self.canvas.setMinimumWidth(420);split.addWidget(self.canvas);split.setSizes([500,560])
        self.availability=QLabel();self.availability.setWordWrap(True);layout.addWidget(self.availability)
        tabs.setCurrentIndex(0)
        self._fd_rows=[]
        self._read(0)

    def _read(self,index):
        self._serial+=1;serial=self._serial;self._data=None
        self.tangent.setRowCount(0);self.states.setRowCount(0);self.stress.setRowCount(0)
        self.build.setRowCount(0);self._fd_rows=[];self.probes.setRowCount(0);self.probe_states.clear()
        self.figure.clear();self.canvas.draw_idle();self.probe.setEnabled(False)
        work=_Read(lambda:self.client.constitutive_inspect(self.document_id,self.job_id,index));_READS.add(work)
        def done(data,error):
            _READS.discard(work)
            if self._closed or serial!=self._serial:return
            if error:self.status.setText(str(error));return
            self._show(data)
        work.signals.finished.connect(done,Qt.ConnectionType.QueuedConnection);QThreadPool.globalInstance().start(work)

    def _select(self,*_):
        selected=self.increment.currentData()
        if selected is not None:self._read(selected)

    def _show(self,data):
        self._data=deepcopy(data);self.increment.blockSignals(True);self.increment.clear()
        for row in data['increments']:
            self.increment.addItem(str(row['index']+1)+' / '+short(row['time'])+' ['+row['unit']+']',row['index'])
        self.increment.setCurrentIndex(self.increment.findData(data['increment']));self.increment.blockSignals(False)
        self.status.setText(data['pair']+' ['+data['tangent_unit']+']')
        self.status.setToolTip(data.get('frame',''))
        matrix=data.get('tangent') or [];names=data['components']
        self.tangent.setColumnCount(len(names));self.tangent.setRowCount(len(matrix))
        self.tangent.setHorizontalHeaderLabels(names);self.tangent.setVerticalHeaderLabels(names)
        for i,row in enumerate(matrix):
            for j,value in enumerate(row):
                item=QTableWidgetItem(short(value));item.setToolTip(repr(value));self.tangent.setItem(i,j,item)
        states=[dict(leaves(data.get(name))) for name in ('state_initial','state_trial','state_committed')]
        keys=list(dict.fromkeys(key for state in states for key in state));self.states.setRowCount(len(keys))
        for i,key in enumerate(keys):
            for j,value in enumerate([key]+[state.get(key) for state in states]):
                self.states.setItem(i,j,QTableWidgetItem(short(value)))
        quantities=[(q,name,value) for q in data.get('quantities',[]) for name,value in zip(q['components'],q['values'])]
        self.stress.setRowCount(len(quantities))
        for i,(q,name,value) in enumerate(quantities):
            frame='재료 직교 기준계' if q['frame']=='material_cartesian' else '재료 성분 / 공간 정렬 미확인'
            entries=[q['name'],name,'미보존' if value is None else short(value),q['unit'],MEASURES.get(q['measure'],q['measure']),frame]
            for j,label in enumerate(entries):
                item=QTableWidgetItem(label);item.setToolTip(repr(value) if j==2 else q['frame'] if j==5 else q['measure'])
                self.stress.setItem(i,j,item)
        build=list(leaves(data.get('build',{})))
        self.build.setRowCount(len(build))
        for i,(name,value) in enumerate(build):
            self.build.setItem(i,0,QTableWidgetItem(name));self.build.setItem(i,1,QTableWidgetItem(short(value)))
        self.availability.setText(' / '.join(data['unavailable'])+
            (' / 실제 substep: '+short(data['substeps']) if data.get('substeps') is not None else ''))
        self.probe.setEnabled(data['backend']=='material.felupe')
        if matrix:self.tangent.setCurrentCell(0,0)
        self._plot()

    def _plot(self):
        self.figure.clear();ax=self.figure.add_subplot(111)
        if not self._data:self.canvas.draw_idle();return
        data=self._data;i=self.tangent.currentRow();j=self.tangent.currentColumn()
        matrix=data.get('tangent') or []
        if i<0 or j<0 or i>=len(matrix) or j>=len(matrix[i]):
            self.canvas.draw_idle();return
        self._fd_rows=selected_probes(data,i,j)
        self.probes.setRowCount(len(self._fd_rows))
        self.probes.setHorizontalHeaderLabels(['h','− '+data['components'][j]+' [1]','+ '+data['components'][j]+' [1]',
            '− '+data['components'][i]+' ['+data['tangent_unit']+']','+ '+data['components'][i]+' ['+data['tangent_unit']+']','중앙차분'])
        for row,values in enumerate(self._fd_rows):
            for col,key in enumerate(('h','minus_input','plus_input','minus_stress','plus_stress','difference')):
                item=QTableWidgetItem(short(values[key]));item.setToolTip(repr(values[key]));self.probes.setItem(row,col,item)
        if self._fd_rows:self.probes.selectRow(0);self._probe_selected()
        else:self.probe_states.clear()
        exact=matrix[i][j];points=[]
        for fd in data.get('finite_differences',[]):
            if data['backend']=='material.felupe':
                if fd.get('increment')!=data['increment'] or fd.get('input_component')!=data['components'][j]:continue
                values=fd.get('finite_difference')
                if values is not None:points.append((fd['h'],values[i//3][i%3]))
            elif data['backend']=='material.mfront.user':
                if fd.get('component')==data['components'][j] and 'column_values' in fd:
                    points.append((fd['h'],fd['column_values'][i]))
            else:
                values=fd.get('tangent_kelvin_mpa',fd.get('pk1_tangent_mpa',fd.get('tangent')))
                if values is not None:points.append((fd['h'],values[i][j]))
        ax.axhline(exact,label='기록된 접선',color='#2563eb')
        if points:
            ax.plot([p[0] for p in points],[p[1] for p in points],'o-',label='독립 중앙차분');ax.set_xscale('log')
        else:ax.text(.5,.15,'선택 성분의 독립 섭동 기록 없음',ha='center',transform=ax.transAxes)
        ax.set_xlabel('섭동 크기 h');ax.set_ylabel(data['tangent_unit'])
        ax.set_title(data['components'][i]+' / '+data['components'][j]);ax.legend();self.canvas.draw_idle()

    def _probe_selected(self,*_):
        row=self.probes.currentRow()
        if 0<=row<len(self._fd_rows):fill_tree(self.probe_states,self._fd_rows[row]['signed'])
        else:self.probe_states.clear()

    def request_probe(self):
        if not self._data or self._data['backend']!='material.felupe':return
        names=self._data['components'];column=self.tangent.currentColumn()
        selected,ok=QInputDialog.getItem(self,'독립 섭동','변형구배 성분',names,max(0,column),False)
        if not ok:return
        text,ok=QInputDialog.getText(self,'독립 섭동','섭동 크기 (쉼표로 구분)',text='1e-5, 1e-6, 1e-7')
        if not ok:return
        try:
            steps=[float(x.strip()) for x in text.split(',')]
            draft=deepcopy(self._data['draft'])
            draft['settings']['tangent_probe']={'increment':self._data['increment'],'input_component':selected,'steps':steps}
            from caelab.material_document import diagnostics
            errors=diagnostics(draft)
            if errors:raise ValueError(errors[0]['message'])
        except (ValueError,TypeError) as error:
            QMessageBox.warning(self,'섭동 크기 확인',str(error));return
        if QMessageBox.question(self,'새 비교 계산','선택한 계산의 입력을 새 재료 문서로 복사해 독립 섭동을 실행할까요?')!=QMessageBox.StandardButton.Yes:return
        # Explicit new owner, original live edits never read/replaced. A lost
        # creation reply is reported unconfirmed; no automatic duplicate retry.
        self.probe.setEnabled(False);serial=self._serial
        command='C'+uuid.uuid4().hex
        def execute():
            document=self.client.document_open(kind='material',title='독립 접선 비교',draft=draft)
            return self.client.document_command(document['id'],'material.evaluate',{},
                session_id=document['session_id'],expected_generation=document['generation'],command_id=command)
        work=_Read(execute);_READS.add(work)
        def done(result,error):
            _READS.discard(work)
            if self._closed or serial!=self._serial:return
            if error:
                self.status.setText('비교 계산 응답 미확인: 새 재료 문서와 실행 작업을 확인하세요. '+str(error));return
            document=result.get('document',result)
            from .material_window import MaterialWindow
            window=MaterialWindow(self.client,document_id=document['id']);self._children.append(window);window.show()
            self.status.setText('새 재료 문서에서 비교 계산을 시작했습니다.')
        work.signals.finished.connect(done,Qt.ConnectionType.QueuedConnection);QThreadPool.globalInstance().start(work)

    def closeEvent(self,event):
        self._closed=True;self._serial+=1;super().closeEvent(event)
