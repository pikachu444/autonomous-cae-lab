"""Native Qt dynamic workflow; no browser, auto-apply or secondary scheduler."""
from copy import deepcopy
import uuid
from .dynamic_buffer import Buffer
from caelab.dynamic_model import continuation_step


def _gui():
    try:
        from PySide import QtGui
        return QtGui
    except ImportError:
        from PySide6 import QtGui
        return QtGui


def style(widget, name):
    G = _gui(); widget.setObjectName(name)
    available = set(G.QFontDatabase().families())
    for family in ('Malgun Gothic', '맑은 고딕', 'Noto Sans CJK KR', 'Noto Sans KR'):
        if family in available:
            widget.setFont(G.QFont(family, 10)); break
    accent = widget.palette().highlight().color().name()
    widget.setStyleSheet(f'''#{name} QLineEdit, #{name} QComboBox {{ min-height:26px; padding:2px 4px; }}
      #{name} QPushButton {{ min-height:28px; padding:2px 8px; }}
      #{name} QLineEdit:focus, #{name} QTableWidget:focus {{ border:2px solid {accent}; }}
      #{name} QPushButton[primary="true"] {{ font-weight:600; border:2px solid {accent}; }}''')


def table(W, headers):
    t = W.QTableWidget(0, len(headers)); t.setHorizontalHeaderLabels(headers)
    t.setAlternatingRowColors(True); t.setSelectionBehavior(W.QAbstractItemView.SelectRows)
    t.setSelectionMode(W.QAbstractItemView.SingleSelection)
    t.horizontalHeader().setStretchLastSection(True); t.verticalHeader().setVisible(False)
    return t


def _item(W, C, value, editable=True):
    item = W.QTableWidgetItem(str(value))
    if not editable: item.setFlags(item.flags() & ~C.Qt.ItemIsEditable)
    item.setToolTip(str(value)); return item


def curves_dialog(W, C, parent, step):
    """Edit a single stage's native conditions and points, preserving numeric text."""
    dialog = W.QDialog(parent); dialog.setWindowTitle(step['label'] + ' — 하중 곡선'); dialog.resize(640, 510)
    layout = W.QVBoxLayout(dialog)
    note = W.QLabel('단계 좌표: ' + ('물리시간 [s]' if step.get('procedure') == 'dynamic' else '정적 가상시간 [1]') +
        '  |  유지: 이전 단계 끝값  |  해제: 힘 0, 지정변위 자유'); note.setWordWrap(True); layout.addWidget(note)
    rows = deepcopy(step['curves']); choice = W.QComboBox(); mode = W.QComboBox()
    for r in rows: choice.addItem(f"{r['condition_id']} / {r['component']} [{r['unit']}]")
    for label, value in [('곡선', 'curve'), ('유지', 'hold'), ('해제', 'release')]: mode.addItem(label, value)
    layout.addWidget(choice); layout.addWidget(mode)
    points = table(W, ['단계 좌표', '조건값']); layout.addWidget(points, 1)
    selected = [-1]; loading = [False]
    def save_row():
        i = selected[0]
        if i < 0: return
        rows[i]['mode'] = mode.currentData()
        rows[i]['points'] = [[points.item(j,k).text() if points.item(j,k) else '' for k in range(2)] for j in range(points.rowCount())]
    def load(index):
        save_row(); selected[0] = index; loading[0] = True
        points.setRowCount(0)
        if index >= 0:
            r = rows[index]; mode.setCurrentIndex(max(0, mode.findData(r.get('mode','curve'))))
            for j, row in enumerate(r.get('points', [])):
                points.insertRow(j)
                for k, text in enumerate(row): points.setItem(j,k,_item(W,C,text))
        points.setEnabled(mode.currentData() == 'curve'); loading[0] = False
    choice.currentIndexChanged.connect(load)
    mode.currentIndexChanged.connect(lambda *_: points.setEnabled(mode.currentData() == 'curve'))
    bar = W.QHBoxLayout()
    add = W.QPushButton('점 추가'); remove = W.QPushButton('점 삭제')
    def add_point():
        i = points.rowCount(); points.insertRow(i)
        for j in range(2): points.setItem(i,j,_item(W,C,''))
        points.setCurrentCell(i,0); points.editItem(points.item(i,0))
    add.clicked.connect(add_point); remove.clicked.connect(lambda: points.removeRow(points.currentRow()) if points.currentRow()>=0 else None)
    bar.addWidget(add); bar.addWidget(remove); bar.addStretch(); layout.addLayout(bar)
    buttons = W.QDialogButtonBox(W.QDialogButtonBox.Ok | W.QDialogButtonBox.Cancel)
    buttons.accepted.connect(dialog.accept); buttons.rejected.connect(dialog.reject); layout.addWidget(buttons)
    load(choice.currentIndex())
    if (getattr(dialog,'exec',None) or dialog.exec_)() != W.QDialog.Accepted: return None
    save_row(); return rows


def make_panel(W, C, editor, submit, *, Gui, on_run, on_results, on_runner, on_save):
    class Panel(W.QWidget):
        def __init__(self):
            super().__init__(); self.buffer = Buffer(); self.loading = False; self.info = {}; self.ready = False
            self.fields = {}; self.step_data = []; self.ic_data = []; self.analysis_key = None
            style(self,'DynamicPanel'); self.setMinimumWidth(310)
            layout = W.QVBoxLayout(self); layout.setContentsMargins(12,10,12,10); layout.setSpacing(8)
            top = W.QGridLayout(); top.setColumnStretch(1,1)
            self.analysis = W.QComboBox(); self.solver = W.QComboBox()
            self.analysis.setAccessibleName('동해석 대상 해석'); self.solver.setAccessibleName('동해석 solver')
            top.addWidget(W.QLabel('해석'),0,0); top.addWidget(self.analysis,0,1)
            top.addWidget(W.QLabel('솔버'),1,0); top.addWidget(self.solver,1,1)
            self.create = W.QPushButton('설정 만들기'); self.reload_button = W.QPushButton('저장본 읽기')
            top.addWidget(self.reload_button,0,2); top.addWidget(self.create,1,2); layout.addLayout(top)
            self.status = W.QLabel('탄성/J2 C3D10 implicit 동해석'); self.status.setWordWrap(True); layout.addWidget(self.status)
            self.tabs = W.QTabWidget(); layout.addWidget(self.tabs,1)
            initial = W.QWidget(); il = W.QVBoxLayout(initial)
            self.densities = table(W,['고체 / 재료','밀도 [kg/m³]']); self.densities.setMaximumHeight(145); il.addWidget(self.densities)
            form = W.QFormLayout(); form.setFieldGrowthPolicy(W.QFormLayout.AllNonFixedFieldsGrow)
            form.setRowWrapPolicy(W.QFormLayout.WrapLongRows)
            for key,label in [('alpha_per_s','Rayleigh α [1/s]'),('beta_s','Rayleigh β [s]'),
                              ('numerical_alpha','수치감쇠 α [무차원]'),('restart_frequency','저장 주기 [완료 단계 수]')]:
                e=W.QLineEdit(); e.setAccessibleName(label); self.fields[key]=e; form.addRow(label,e); e.textEdited.connect(self.changed)
            il.addLayout(form)
            self.initial = table(W,['이름','종류','전역 DOF','초기값','원 대상']); il.addWidget(self.initial,1)
            note=W.QLabel('U [mm], V [mm/s]. 초기조건은 지정변위나 CAD 이동이 아닙니다.');note.setWordWrap(True);il.addWidget(note)
            bar=W.QHBoxLayout();self.add_ic=W.QPushButton('대상 선택…'); self.remove_ic=W.QPushButton('조건 삭제')
            bar.addWidget(self.add_ic);bar.addWidget(self.remove_ic);bar.addStretch();il.addLayout(bar)
            scroll=W.QScrollArea();scroll.setWidgetResizable(True);scroll.setWidget(initial);self.initial_scroll=scroll;self.tabs.addTab(scroll,'초기 상태')
            stages=W.QWidget();sl=W.QVBoxLayout(stages)
            note=W.QLabel('정적 가상시간은 물리시간에 더하지 않습니다. 단계를 고른 뒤 하중 곡선에서 유지·해제를 편집하세요.')
            note.setWordWrap(True);sl.addWidget(note)
            self.steps=table(W,['단계','절차','길이','초기 증분','최소 증분','최대 증분','최대 횟수','출력 간격'])
            sl.addWidget(self.steps,1);sb=W.QGridLayout()
            for i,(label,fn) in enumerate([('단계 추가',self.add_step),('단계 삭제',self.remove_step),
                ('위로',lambda:self.move_step(-1)),('아래로',lambda:self.move_step(1)),('하중 곡선…',self.curves)]):
                b=W.QPushButton(label);b.clicked.connect(self.safe(fn));sb.addWidget(b,i//3,i%3)
            sl.addLayout(sb);self.tabs.addTab(stages,'시간 단계')
            self.errors=W.QListWidget();self.errors.setMaximumHeight(100);layout.addWidget(self.errors)
            self.errors.itemActivated.connect(self.focus_error)
            bottom=W.QGridLayout();self.buttons={}
            for i,(key,label,fn) in enumerate([
                ('draft','초안 저장',lambda:self.command('pre.dynamic.draft',self.edited_args())),
                ('apply','적용',lambda:self.command('pre.dynamic.apply',self.edited_args())),
                ('cancel','수정 취소',self.reload),('export','입력 생성',lambda:on_run(self.analysis_key,True)),
                ('run','계산',lambda:on_run(self.analysis_key,False)),('result','저장 결과…',on_results),
                ('save','프로젝트 저장',on_save),('runner','계산 목록',on_runner)]):
                b=W.QPushButton(label);b.clicked.connect(self.safe(fn));self.buttons[key]=b;bottom.addWidget(b,i//3,i%3)
            self.buttons['apply'].setProperty('primary',True);layout.addLayout(bottom)
            self.analysis.currentIndexChanged.connect(self.safe(self.select_analysis))
            self.create.clicked.connect(self.safe(lambda:self.command('pre.dynamic.create',
                {'analysis_id':self.analysis.currentData(),'solver_id':self.solver.currentData()})))
            self.reload_button.clicked.connect(self.safe(self.reload))
            self.add_ic.clicked.connect(self.safe(self.capture));self.remove_ic.clicked.connect(self.safe(self.delete_ic))
            for t in (self.initial,self.steps,self.densities): t.itemChanged.connect(self.changed)
            self.destroyed.connect(lambda *_:self.buffer.close())
            self.discover()
        def safe(self,fn):
            def call(*unused):
                try:fn()
                except Exception as exc:self.status.setText(str(exc))
            return call
        def discover(self):
            data=editor.inspect();self.catalog=data['analyses'];self.loading=True
            for row in self.catalog:self.analysis.addItem(row['label'],row['id'])
            self.loading=False;self.select_analysis()
        def discard(self):
            self.sync()
            return not self.buffer.pending() or W.QMessageBox.question(self,'미저장 수정',
                '현재 화면 수정을 취소하고 저장본을 읽겠습니까?',W.QMessageBox.Yes|W.QMessageBox.No,
                W.QMessageBox.No)==W.QMessageBox.Yes
        def select_analysis(self):
            if self.loading:return
            if not self.discard():
                self.analysis.blockSignals(True);self.analysis.setCurrentIndex(self.analysis.findData(self.analysis_key));self.analysis.blockSignals(False);return
            self.analysis_key=self.analysis.currentData();self.loading=True;self.solver.clear()
            row=next((r for r in self.catalog if r['id']==self.analysis_key),None)
            for s in row['solvers'] if row else []:self.solver.addItem(s['label'],s['id'])
            self.loading=False;self.load_current()
        def reload(self):
            if self.discard():self.load_current()
        def load_current(self):
            all_info=editor.inspect()
            if self.analysis_key in all_info['models']:self.display(editor.inspect(self.analysis_key))
            else:
                self.buffer.select(None);self.ready=False;self.info={};self.loading=True
                self.initial.setRowCount(0);self.steps.setRowCount(0);self.densities.setRowCount(0)
                for e in self.fields.values():e.clear()
                self.loading=False;self.status.setText('이 해석에 동해석 설정이 없습니다. 설정 만들기를 선택하세요.');self.update_buttons()
        def display(self,info):
            self.info=info;d=info['record']['draft'];self.buffer.select(d);self.loading=True
            self.solver.setCurrentIndex(self.solver.findData(d['solver_id']))
            self.densities.setRowCount(len(d['densities']))
            for i,r in enumerate(d['densities']):
                self.densities.setItem(i,0,_item(W,C,r['body_id']+' / '+r['material_id'],False));self.densities.setItem(i,1,_item(W,C,r['kg_m3']))
            for key,e in self.fields.items():e.setText(str(d['rayleigh'][key] if key in d['rayleigh'] else d[key]))
            self.ic_data=deepcopy(d['initial_conditions']);self.fill_initial();self.step_data=deepcopy(d['program']['steps']);self.fill_steps()
            self.errors.clear()
            for error in info.get('errors',[]):
                item=W.QListWidgetItem(error['message']);item.setData(C.Qt.UserRole,error['path']);self.errors.addItem(item)
            self.ready=info['can_freeze'];self.loading=False
            self.status.setText('입력 생성 가능 — 물리 검증은 별도입니다.' if self.ready else '초안 유지 — 오류를 수정하고 적용하세요.')
            self.update_buttons()
        def combo(self,options,value):
            c=W.QComboBox()
            for label,v in options:c.addItem(label,v)
            c.setCurrentIndex(c.findData(value));c.currentIndexChanged.connect(self.changed);return c
        def fill_initial(self):
            self.initial.setRowCount(len(self.ic_data))
            for i,r in enumerate(self.ic_data):
                self.initial.setItem(i,0,_item(W,C,r['label']))
                self.initial.setCellWidget(i,1,self.combo([('변위 U','U'),('속도 V','V')],r['kind']))
                self.initial.setCellWidget(i,2,self.combo([(a,j) for j,a in enumerate('XYZ',1)],r['component']))
                self.initial.setItem(i,3,_item(W,C,r['value']));t=r['target']
                text=f"{t.get('body_id','?')} / {len(t.get('native_node_ids',[]))}절점"
                item=_item(W,C,text,False);item.setToolTip('원 절점: '+', '.join(map(str,t.get('native_node_ids',[]))))
                self.initial.setItem(i,4,item)
        def fill_steps(self):
            self.steps.setRowCount(len(self.step_data))
            for i,r in enumerate(self.step_data):
                self.steps.setItem(i,0,_item(W,C,r['label']))
                self.steps.setCellWidget(i,1,self.combo([('정적 [1]','static'),('동적 [s]','dynamic')],r.get('procedure','dynamic')))
                for j,k in enumerate(('duration','initial','minimum','maximum','increments','output_frequency'),2):
                    self.steps.setItem(i,j,_item(W,C,r.get(k,'')))
        def sync(self):
            if self.loading or self.buffer.value is None:return
            d=deepcopy(self.buffer.value)
            for i,r in enumerate(d['densities']):r['kg_m3']=self.densities.item(i,1).text()
            for k,e in self.fields.items():
                if k in d['rayleigh']:d['rayleigh'][k]=e.text()
                else:d[k]=e.text()
            d['initial_conditions']=deepcopy(self.ic_data)
            for i,r in enumerate(d['initial_conditions']):
                r.update(label=self.initial.item(i,0).text(),kind=self.initial.cellWidget(i,1).currentData(),
                         component=self.initial.cellWidget(i,2).currentData(),value=self.initial.item(i,3).text())
            d['program']['steps']=deepcopy(self.step_data)
            for i,r in enumerate(d['program']['steps']):
                r.update(label=self.steps.item(i,0).text(),procedure=self.steps.cellWidget(i,1).currentData())
                for j,k in enumerate(('duration','initial','minimum','maximum','increments','output_frequency'),2):r[k]=self.steps.item(i,j).text()
            procedures={r['procedure'] for r in d['program']['steps']}
            d['program']['procedure']=next(iter(procedures)) if len(procedures)==1 else 'mixed'
            self.buffer.value=d
        def changed(self,*unused):
            if self.loading:return
            self.sync();self.ready=False;self.status.setText('미적용 수정 — 초안 저장 또는 적용');self.update_buttons()
        def update_buttons(self):
            ready=self.buffer.value is not None and not self.buffer.busy
            self.tabs.setEnabled(ready);self.analysis.setEnabled(not self.buffer.busy);self.reload_button.setEnabled(not self.buffer.busy)
            self.solver.setEnabled(self.buffer.value is None and not self.buffer.busy)
            self.create.setEnabled(self.buffer.value is None and not self.buffer.busy and self.solver.currentData() is not None)
            for k in ('draft','apply','cancel','save'):self.buttons[k].setEnabled(ready)
            for k in ('run','export'):self.buttons[k].setEnabled(ready and self.ready and not self.buffer.pending())
        def edited_args(self):
            self.sync();return {'analysis_id':self.analysis_key,'draft':deepcopy(self.buffer.value)}
        def command(self,op,args):
            self.sync();ticket=self.buffer.begin();self.update_buttons()
            def done(info):
                current=self.buffer.complete(ticket,info.get('record',{}).get('draft'))
                if not self.buffer.alive or ticket[0]!=self.buffer.epoch:return
                if info.get('status')=='FAILED':self.status.setText(info.get('error',{}).get('message','작업 실패'))
                elif 'record' in info and current:self.display(info)
                self.update_buttons()
            try:submit(op,args,on_done=done)
            except Exception:
                self.buffer.complete(ticket);self.update_buttons();raise
        def capture(self):
            self.sync();dialog=W.QDialog(self);dialog.setWindowTitle('초기조건 대상');l=W.QFormLayout(dialog)
            b=W.QComboBox()
            for row in self.info.get('bodies',[]):b.addItem(row['id']+' / '+row['mesh_id'],row['id'])
            use_faces=W.QCheckBox('3D 화면에서 선택한 면 사용');use_faces.setChecked(True)
            nodes=W.QLineEdit();nodes.setPlaceholderText('원 메시 절점 번호: 11, 23, 37');nodes.setEnabled(False)
            use_faces.toggled.connect(lambda checked:nodes.setEnabled(not checked))
            l.addRow('고체',b);l.addRow(use_faces);l.addRow('원 절점',nodes)
            buttons=W.QDialogButtonBox(W.QDialogButtonBox.Ok|W.QDialogButtonBox.Cancel);l.addRow(buttons)
            buttons.accepted.connect(dialog.accept);buttons.rejected.connect(dialog.reject)
            if (getattr(dialog,'exec',None) or dialog.exec_)()!=W.QDialog.Accepted:return
            faces=None;ids=None
            if use_faces.isChecked():
                selection=Gui.Selection.getSelectionEx(editor.owner.doc.Name)
                pairs=[(s.Object,n) for s in selection for n in s.SubElementNames]
                if not pairs or any(obj.Document is not editor.owner.doc or obj.Name!=b.currentData() or not n.startswith('Face') for obj,n in pairs):
                    raise ValueError('선택한 고체의 실제 면만 선택하세요.')
                faces=[n for obj,n in pairs]
            else:
                try:ids=[int(v.strip()) for v in nodes.text().split(',')]
                except ValueError:raise ValueError('원 절점 번호를 쉼표로 구분하세요.') from None
            ticket=self.buffer.begin();self.update_buttons()
            def captured(value):
                self.buffer.complete(ticket)
                if not self.buffer.alive or ticket[0]!=self.buffer.epoch:return
                if value.get('status')=='FAILED':self.status.setText(value['error']['message']);self.update_buttons();return
                self.sync();self.ic_data=deepcopy(self.buffer.value['initial_conditions'])
                self.ic_data.append({'id':'IC'+uuid.uuid4().hex,'label':'초기 속도','kind':'V','component':1,'value':'0','target':value['target']})
                self.loading=True;self.fill_initial();self.loading=False;self.changed()
            try:submit('pre.dynamic.capture',{'analysis_id':self.analysis_key,'body_id':b.currentData(),'native_node_ids':ids,'faces':faces},on_done=captured)
            except Exception:self.buffer.complete(ticket);self.update_buttons();raise
        def delete_ic(self):
            i=self.initial.currentRow()
            if i<0:return
            self.sync();self.ic_data=deepcopy(self.buffer.value['initial_conditions']);del self.ic_data[i]
            self.loading=True;self.fill_initial();self.loading=False;self.changed()
        def add_step(self):
            self.sync();rows=deepcopy(self.buffer.value['program']['steps'])
            if not rows:raise ValueError('기본 단계를 삭제했다면 저장본 읽기로 복구하세요.')
            i=self.steps.currentRow();at=i+1 if i>=0 else len(rows)
            r=continuation_step(rows[i] if i>=0 else rows[-1],identifier='S'+uuid.uuid4().hex,label='동적 단계')
            rows.insert(at,r);self.step_data=rows
            self.loading=True;self.fill_steps();self.steps.setCurrentCell(at,0);self.loading=False;self.changed()
        def remove_step(self):
            self.sync();i=self.steps.currentRow()
            if i<0:return
            if self.steps.rowCount()==1:raise ValueError('최소 한 단계는 유지하세요.')
            self.step_data=deepcopy(self.buffer.value['program']['steps']);del self.step_data[i]
            self.loading=True;self.fill_steps();self.loading=False;self.changed()
        def move_step(self,delta):
            self.sync();i=self.steps.currentRow();j=i+delta
            if not 0<=j<self.steps.rowCount() or i<0:return
            self.step_data=deepcopy(self.buffer.value['program']['steps'])
            self.step_data[i],self.step_data[j]=self.step_data[j],self.step_data[i]
            self.loading=True;self.fill_steps();self.steps.selectRow(j);self.loading=False;self.changed()
        def curves(self):
            self.sync();i=self.steps.currentRow()
            if i<0:raise ValueError('편집할 단계를 선택하세요.')
            self.step_data=deepcopy(self.buffer.value['program']['steps'])
            curves=curves_dialog(W,C,self,self.step_data[i])
            if curves is not None:self.step_data[i]['curves']=curves;self.changed()
        def focus_error(self,item):
            path=item.data(C.Qt.UserRole) or ''
            self.tabs.setCurrentIndex(1 if path.startswith('program') else 0)
            key=path.split('.')[-1]
            if key in self.fields:
                self.fields[key].setFocus();self.fields[key].selectAll()
                self.initial_scroll.ensureWidgetVisible(self.fields[key],0,8)
            else:
                parts=path.split('.')
                target=None;column=0;row_index=1
                if parts[0]=='initial_conditions':
                    target=self.initial;column={'label':0,'kind':1,'component':2,'value':3,'target':4}.get(key,3)
                elif parts[0]=='densities':target=self.densities;column=1
                elif parts[:2]==['program','steps']:
                    target=self.steps;row_index=2
                    column={'label':0,'procedure':1,'duration':2,'initial':3,'minimum':4,
                            'maximum':5,'increments':6,'output_frequency':7}.get(key,0)
                if target is None:return
                try:row=int(parts[row_index])
                except (IndexError,ValueError):return
                if not 0<=row<target.rowCount():return
                target.setCurrentCell(row,column)
                target.scrollToItem(target.item(row,column) or target.item(row,0))
                control=target.cellWidget(row,column)
                (control or target).setFocus()
                if target is not self.steps:
                    index=target.model().index(row,column)
                    point=target.viewport().mapTo(self.initial_scroll.widget(),target.visualRect(index).center())
                    self.initial_scroll.ensureVisible(point.x(),point.y(),0,24)
        def editor_token(self):self.sync();return self.buffer.token()
        def pending_snapshot(self):self.sync();return deepcopy(self.buffer.value) if self.buffer.pending() else None
        def accept_saved_snapshot(self,snapshot,value):
            self.sync()
            if self.buffer.value==snapshot and 'record' in value:self.display(value)
            else:self.buffer.saved=deepcopy(snapshot)
    return Panel()
