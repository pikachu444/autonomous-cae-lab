"""Local, cancellable explicit settings editor; no calculation or model mutation."""
from copy import deepcopy
from pathlib import Path
import hashlib
import math
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog,QDialogButtonBox,QVBoxLayout,QHBoxLayout,QLabel,
    QPushButton,QFileDialog,QMessageBox,QTabWidget,QWidget,QTableWidget,QTableWidgetItem,
    QComboBox,QFormLayout,QLineEdit,QCheckBox,QInputDialog,QHeaderView,QGridLayout,QSizePolicy)
from caelab.impact_model import parse_inp,default_settings

MODES={'velocity':'입력 속도','release_height':'높이에서 놓기','impact_height':'높이를 충돌 속도로 환산'}


def numeric(text):
    try:
        value=float(text)
        return value if math.isfinite(value) else text
    except ValueError: return text


def text(value):
    return '' if value is None else str(value)


class ImpactEditor(QDialog):
    def __init__(self,settings,parent=None):
        super().__init__(parent); self.setWindowTitle('충격 조건'); self.resize(1060,700)
        self.value=deepcopy(settings); self.setMinimumSize(760,500)
        layout=QVBoxLayout(self); top=QHBoxLayout()
        self.source_label=QLabel(); self.source_label.setWordWrap(True)
        choose=QPushButton('유한요소 파일 열기…'); choose.clicked.connect(self.choose_file)
        top.addWidget(self.source_label,1); top.addWidget(choose); layout.addLayout(top)
        self.tabs=QTabWidget(); layout.addWidget(self.tabs,1)
        self.motion=self.table(['절점 집합','방식','높이 [mm]','Vx [mm/s]','Vy','Vz',
            'ωx [rad/s]','ωy','ωz','중심 X [mm]','Y','Z','위치 ΔX [mm]','ΔY','ΔZ'])
        motion_page=QWidget(); ml=QVBoxLayout(motion_page); ml.addWidget(self.motion,1)
        self.motion.setMaximumHeight(220)
        self.motion.model().rowsInserted.connect(self.resize_motion_table)
        self.motion.model().rowsRemoved.connect(self.resize_motion_table)
        for col in range(3,15): self.motion.setColumnHidden(col,True)
        self.motion.horizontalHeader().setSectionResizeMode(1,QHeaderView.ResizeMode.Stretch)
        self.motion.setColumnWidth(0,160); self.motion.setColumnWidth(2,140)
        details=QWidget();details.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Maximum)
        grid=QGridLayout(details);grid.setContentsMargins(0,0,0,0);self.components={}
        for col,axis in enumerate('XYZ',1): grid.addWidget(QLabel(axis),0,col)
        for row,(start,label) in enumerate(((3,'병진 속도 [mm/s]'),(6,'각속도 [rad/s]'),
                (9,'회전 중심 [mm]'),(12,'위치 이동 [mm]')),1):
            grid.addWidget(QLabel(label),row,0)
            for col in range(3):
                field=QLineEdit();field.setMinimumWidth(100);self.components[start+col]=field
                field.textEdited.connect(lambda value,c=start+col:self.set_component(c,value))
                grid.addWidget(field,row,col+1)
        ml.addWidget(details)
        self.motion.itemSelectionChanged.connect(self.show_motion)
        self.buttons(ml,self.add_motion,lambda:self.motion.removeRow(self.motion.currentRow()))
        ml.addStretch(1)
        self.tabs.addTab(motion_page,'초기 운동')
        self.contacts=self.table(['면 A','면 B','접촉 법칙','마찰계수'])
        contact_page=QWidget(); cl=QVBoxLayout(contact_page); cl.addWidget(self.contacts,1)
        self.buttons(cl,self.add_contact,lambda:self.contacts.removeRow(self.contacts.currentRow()))
        self.tabs.addTab(contact_page,'접촉')
        self.damage=self.table(['응집 재료','혼합 모드','소실 적분점'])
        damage_page=QWidget();dl=QVBoxLayout(damage_page);dl.addWidget(self.damage)
        self.damage_fields={};damage_form=QFormLayout()
        for key,label in (('normal_strength_mpa','법선 강도 [MPa]'),('shear_strength_mpa','전단 강도 [MPa]'),
            ('mode_I_n_mm','모드 I 파괴 에너지 [N/mm]'),('mode_II_n_mm','모드 II 파괴 에너지 [N/mm]'),
            ('power_exponent','거듭제곱 지수'),('bk_exponent','BK 지수'),('gamma','BK 가중 지수')):
            field=QLineEdit();self.damage_fields[key]=field
            field.textEdited.connect(lambda value,k=key:self.damage_value(k,value));damage_form.addRow(label,field)
        dl.addLayout(damage_form)
        dl.addWidget(QLabel('LAW117 / 양의 두께 / 체적 밀도. 소실 뒤 재접촉은 벌크 면의 접촉쌍으로 지정합니다.'))
        self.damage.itemSelectionChanged.connect(self.show_damage)
        self.tabs.addTab(damage_page,'응집 손상')
        self.responses=self.table(['영문 응답명','물리량','원 절점 / 요소','성분'])
        self.responses.horizontalHeader().setStretchLastSection(False)
        self.responses.horizontalHeader().setSectionResizeMode(1,QHeaderView.ResizeMode.Stretch)
        self.responses.horizontalHeader().setSectionResizeMode(3,QHeaderView.ResizeMode.Interactive)
        self.responses.setColumnWidth(3,110)
        response_page=QWidget();rl=QVBoxLayout(response_page);rl.addWidget(self.responses,1)
        self.buttons(rl,self.add_response,lambda:self.responses.removeRow(self.responses.currentRow()))
        self.tabs.addTab(response_page,'결과 이력')
        timing=QWidget(); form=QFormLayout(timing); self.times={}
        for key,label in (('end_s','종료 [s]'),('field_interval_s','장 출력 간격 [s]'),
            ('history_interval_s','이력 간격 [s]'),('scale','안정 시간증분 계수'),('target_step_s','목표 증분 [s]')):
            field=QLineEdit(text(self.value['time'].get(key))); self.times[key]=field; form.addRow(label,field)
        self.mass=QCheckBox('질량 스케일링 사용'); self.mass.setChecked(self.value['time'].get('mass_scaling') is True)
        form.addRow(self.mass)
        self.gravity=[]
        for i,axis in enumerate('XYZ'):
            field=QLineEdit(text(self.value['gravity_mm_s2'][i])); self.gravity.append(field)
            form.addRow('중력 '+axis+' [mm/s²]',field)
        self.tabs.addTab(timing,'시간과 중력')
        self.message=QLabel(); self.message.setWordWrap(True); layout.addWidget(self.message)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText('편집 반영')
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('취소')
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject); layout.addWidget(buttons)
        self.populate()
        if self.motion.rowCount(): self.motion.selectRow(0)

    def resize_motion_table(self,*_):
        header=self.motion.horizontalHeader().sizeHint().height()
        rows=max(1,self.motion.rowCount())*self.motion.verticalHeader().defaultSectionSize()
        self.motion.setMaximumHeight(min(220,header+rows+2*self.motion.frameWidth()+4))

    def table(self,headers):
        table=QTableWidget(0,len(headers)); table.setHorizontalHeaderLabels(headers)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setStretchLastSection(True)
        return table

    def buttons(self,layout,add,remove):
        row=QHBoxLayout()
        for label,call in (('추가…',add),('삭제',remove)):
            button=QPushButton(label); button.clicked.connect(call); row.addWidget(button)
        row.addStretch(); layout.addLayout(row)

    def combo(self,choices,value):
        widget=QComboBox()
        for raw,label in choices.items(): widget.addItem(label,raw)
        if widget.findData(value)<0: widget.addItem('미지원 값: '+str(value),value)
        widget.setCurrentIndex(widget.findData(value)); return widget

    def populate(self):
        self.source_label.setText(self.value['source'].get('title') or '유한요소 메시를 선택하세요')
        self.motion.setRowCount(0); self.contacts.setRowCount(0); self.responses.setRowCount(0)
        for row in self.value.get('responses',[]):self.response_row(row)
        for m in self.value['motions']: self.motion_row(m)
        for c in self.value['contacts']: self.contact_row(c)
        self.damage.setRowCount(0)
        try:
            model=parse_inp(self.value['source']['text'])
            from caelab.impact_damage import default_law
            old={law['material']:law for law in self.value.get('cohesive',[])}
            names=sorted({model['assignment'][e] for e,row in model['elements'].items() if row['type']=='COH3D8'})
            self.value['cohesive']=[deepcopy(old.get(name,default_law(name))) for name in names]
            for index,law in enumerate(self.value['cohesive']):
                self.damage.insertRow(index);item=QTableWidgetItem(law['material'])
                item.setFlags(item.flags()&~Qt.ItemFlag.ItemIsEditable);self.damage.setItem(index,0,item)
                self.damage.setCellWidget(index,1,self.combo({'POWER':'거듭제곱','BK':'Benzeggagh–Kenane'},law['criterion']))
                self.damage.setCellWidget(index,2,self.combo({i:str(i)+'개' for i in range(1,5)},law['deletion_points']))
            if self.damage.rowCount():self.damage.selectRow(0)
            self.show_damage()
            self.message.setText(f"절점 {len(model['nodes']):,}개 / 요소 {len(model['elements']):,}개 — Mg, mm, s, N, MPa")
        except (ValueError,KeyError,TypeError) as error: self.message.setText(str(error))

    def motion_row(self,m):
        r=self.motion.rowCount(); self.motion.insertRow(r)
        self.motion.setItem(r,0,QTableWidgetItem(m['node_set']))
        mode=self.combo(MODES,m['mode']);mode.setMinimumContentsLength(20)
        mode.setProperty('accepted_mode',m['mode'])
        self.motion.setCellWidget(r,1,mode)
        values=[m.get('height_mm'),*m['velocity_mm_s'],*m['omega_rad_s'],*m['center_mm'],*m['translation_mm']]
        for c,value in enumerate(values,2): self.motion.setItem(r,c,QTableWidgetItem(text(value)))
        mode.currentIndexChanged.connect(lambda:self.change_mode(mode))
        self.motion.selectRow(r)
        self.show_motion()

    def set_component(self,column,value):
        row=self.motion.currentRow()
        if row>=0 and self.motion.item(row,column):
            self.motion.item(row,column).setText(value)

    def show_motion(self):
        row=self.motion.currentRow()
        mode=self.motion.cellWidget(row,1) if row>=0 else None
        complete=mode is not None and all(self.motion.item(row,c) is not None for c in range(2,15))
        nonzero=any(numeric(self.motion.item(row,c).text())!=0 for c in range(3,6)) if complete else False
        for col,field in self.components.items():
            item=self.motion.item(row,col) if complete else None
            field.blockSignals(True);field.setText(item.text() if item else '');field.blockSignals(False)
            field.setEnabled(bool(item) and (col>=6 or mode.currentData()=='velocity' or nonzero))
        if complete:
            height=self.motion.item(row,2);flags=height.flags()
            height.setFlags(flags|Qt.ItemFlag.ItemIsEditable if mode.currentData()!='velocity' else flags&~Qt.ItemFlag.ItemIsEditable)

    def change_mode(self,combo):
        row=next((r for r in range(self.motion.rowCount()) if self.motion.cellWidget(r,1) is combo),-1)
        if row<0:return
        selected=combo.currentData(); previous=combo.property('accepted_mode')
        nonzero=any(numeric(self.motion.item(row,c).text())!=0 for c in range(3,6))
        if selected!='velocity' and nonzero:
            answer=QMessageBox.question(self,'높이 조건','높이 조건은 병진 초기속도 0에서 시작합니다. 현재 속도를 0으로 바꿀까요?',
                QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.Cancel)
            if answer!=QMessageBox.StandardButton.Yes:
                combo.blockSignals(True);combo.setCurrentIndex(combo.findData(previous));combo.blockSignals(False);return
            for c in range(3,6):self.motion.item(row,c).setText('0')
        combo.setProperty('accepted_mode',selected);self.show_motion()

    def damage_value(self,key,value):
        index=self.damage.currentRow()
        if 0<=index<len(self.value.get('cohesive',[])):self.value['cohesive'][index][key]=numeric(value)

    def show_damage(self):
        index=self.damage.currentRow()
        laws=self.value.get('cohesive',[])
        for key,field in self.damage_fields.items():
            field.blockSignals(True);field.setText(text(laws[index][key]) if 0<=index<len(laws) else '')
            field.setEnabled(0<=index<len(laws));field.blockSignals(False)

    def response_row(self,row):
        from caelab.impact_responses import QUANTITIES
        index=self.responses.rowCount();self.responses.insertRow(index)
        self.responses.setItem(index,0,QTableWidgetItem(row['name']))
        self.responses.setItem(index,2,QTableWidgetItem(str(row['identity'])))
        quantity=self.combo({k:v[0]+' ['+v[3]+']' for k,v in QUANTITIES.items()},row['quantity'])
        quantity.setMinimumContentsLength(24)
        self.responses.setCellWidget(index,1,quantity)
        self.response_components(index,row['component'])
        quantity.currentIndexChanged.connect(lambda:self.response_changed(quantity))

    def response_components(self,index,selected=None):
        from caelab.impact_responses import QUANTITIES
        quantity=self.responses.cellWidget(index,1).currentData()
        values=QUANTITIES.get(quantity,(None,None,None,None,('scalar',)))[4]
        labels={'scalar':'값','normal':'법선','tangent1':'접선 1','tangent2':'접선 2'}
        combo=self.combo({v:labels.get(v,v) for v in values},selected if selected is not None else values[0])
        self.responses.setCellWidget(index,3,combo)
        item=self.responses.item(index,2)
        if item:item.setToolTip('원 절점 번호' if QUANTITIES.get(quantity,(None,'CELLS'))[1]=='POINTS' else '원 요소 번호')

    def response_changed(self,combo):
        index=next((i for i in range(self.responses.rowCount()) if self.responses.cellWidget(i,1) is combo),-1)
        if index>=0:self.response_components(index)

    def add_response(self):
        from caelab.impact_responses import QUANTITIES
        try:model=parse_inp(self.value['source']['text'])
        except (ValueError,KeyError) as error:self.message.setText(str(error));return
        labels=[v[0] for v in QUANTITIES.values()]
        label,ok=QInputDialog.getItem(self,'결과 이력','물리량',labels,0,False)
        if not ok:return
        quantity=next(k for k,v in QUANTITIES.items() if v[0]==label);definition=QUANTITIES[quantity]
        ids=list(model['nodes'] if definition[1]=='POINTS' else model['elements'])
        if quantity.startswith('cohesive_'):ids=[e for e in ids if model['elements'][e]['type']=='COH3D8']
        if not ids:self.message.setText('이 응답을 선택할 원 요소가 없습니다');return
        value,ok=QInputDialog.getItem(self,'결과 이력','원 절점 번호' if definition[1]=='POINTS' else '원 요소 번호',[str(i) for i in ids],0,False)
        if ok:
            used={self.responses.item(i,0).text() for i in range(self.responses.rowCount())}
            index=1
            while quantity+'_'+str(index) in used:index+=1
            self.response_row({'name':quantity+'_'+str(index),'quantity':quantity,'identity':int(value),'component':definition[4][0]})

    def contact_row(self,c):
        r=self.contacts.rowCount(); self.contacts.insertRow(r)
        for j,k in ((0,'a'),(1,'b'),(3,'friction')): self.contacts.setItem(r,j,QTableWidgetItem(text(c[k])))
        self.contacts.setCellWidget(r,2,self.combo({'UNSELECTED':'법칙 선택','TYPE24':'TYPE24 / 면 접촉'},c['law']))

    def add_motion(self):
        try: names=list(parse_inp(self.value['source']['text'])['nsets'])
        except (ValueError,KeyError) as error: self.message.setText(str(error)); return
        name,ok=QInputDialog.getItem(self,'초기 운동','절점 집합',names,0,False)
        if ok: self.motion_row({'node_set':name,'mode':'velocity','height_mm':None,
            'velocity_mm_s':[0.,0.,0.],'omega_rad_s':[0.,0.,0.],'center_mm':[0.,0.,0.],'translation_mm':[0.,0.,0.]})

    def add_contact(self):
        try: names=list(parse_inp(self.value['source']['text'])['surfaces'])
        except (ValueError,KeyError) as error: self.message.setText(str(error)); return
        a,ok=QInputDialog.getItem(self,'접촉','면 A',names,0,False)
        if not ok: return
        b,ok=QInputDialog.getItem(self,'접촉','면 B',[n for n in names if n!=a],0,False)
        if ok: self.contact_row({'a':a,'b':b,'law':'UNSELECTED','friction':0.})

    def choose_file(self):
        filename,_=QFileDialog.getOpenFileName(self,'유한요소 파일','', '평탄화 솔리드 입력 (*.inp)')
        if not filename: return
        try:
            path=Path(filename)
            if path.stat().st_size>6*1024**2: raise ValueError('6 MiB 이하의 입력을 선택하세요')
            payload=path.read_bytes(); source=payload.decode('ascii'); parse_inp(source)
            answer=QMessageBox.question(self,'입력 단위','이 파일의 단위가 Mg, mm, s, N, MPa입니까? 기존 운동·접촉 선택은 새 메시 기준으로 비워집니다.',
                QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.Cancel)
            if answer!=QMessageBox.StandardButton.Yes: return
            self.value['source']={'title':path.name,'format':'INP','units':'Mg/mm/s','text':source,
                'provenance':{'filename':path.name,'sha256':hashlib.sha256(payload).hexdigest(),'units_declared_by_user':True}}
            self.value['motions']=[]; self.value['contacts']=[]; self.value['cohesive']=[]; self.value['responses']=[]; self.populate()
        except (ValueError,OSError,UnicodeError) as error: self.message.setText(str(error))

    def edited(self):
        value=deepcopy(self.value); motions=[]; contacts=[]
        def cell(table,r,c):
            item=table.item(r,c); return item.text().strip() if item else ''
        for r in range(self.motion.rowCount()):
            values=[numeric(cell(self.motion,r,c)) for c in range(2,15)]
            motions.append({'node_set':cell(self.motion,r,0),'mode':self.motion.cellWidget(r,1).currentData(),
                'height_mm':None if cell(self.motion,r,2)=='' else values[0],
                'velocity_mm_s':values[1:4],'omega_rad_s':values[4:7],'center_mm':values[7:10],'translation_mm':values[10:13]})
        for r in range(self.contacts.rowCount()):
            contacts.append({'a':cell(self.contacts,r,0),'b':cell(self.contacts,r,1),
                'law':self.contacts.cellWidget(r,2).currentData(),'friction':numeric(cell(self.contacts,r,3))})
        value['motions']=motions; value['contacts']=contacts
        value['responses']=[]
        for i in range(self.responses.rowCount()):
            ident=cell(self.responses,i,2)
            try:ident=int(ident)
            except ValueError:pass
            value['responses'].append({'name':cell(self.responses,i,0),
                'quantity':self.responses.cellWidget(i,1).currentData(),'identity':ident,
                'component':self.responses.cellWidget(i,3).currentData()})
        for i,law in enumerate(value.get('cohesive',[])):
            law['criterion']=self.damage.cellWidget(i,1).currentData()
            law['deletion_points']=self.damage.cellWidget(i,2).currentData()
        value['time']={k:numeric(w.text().strip()) for k,w in self.times.items()}
        if not self.times['target_step_s'].text().strip(): value['time']['target_step_s']=None
        value['time']['mass_scaling']=self.mass.isChecked()
        value['gravity_mm_s2']=[numeric(w.text().strip()) for w in self.gravity]
        return value


def edit(window):
    draft=window.edited_draft()
    if draft.get('backend')!='explicit.opencourant.model': return
    dialog=ImpactEditor(draft['settings'],window)
    if dialog.exec()!=QDialog.DialogCode.Accepted: return
    draft['settings']=dialog.edited()
    window._show_document(window.document,preserve_draft=draft)
    window.local_dirty=True
    window._update_actions()
