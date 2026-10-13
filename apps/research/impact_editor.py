"""Local, cancellable explicit settings editor; no calculation or model mutation."""
from copy import deepcopy
from pathlib import Path
import hashlib
import math
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog,QDialogButtonBox,QVBoxLayout,QHBoxLayout,QLabel,
    QPushButton,QFileDialog,QMessageBox,QTabWidget,QWidget,QTableWidget,QTableWidgetItem,
    QComboBox,QFormLayout,QLineEdit,QCheckBox,QInputDialog,QHeaderView)
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
        self.buttons(ml,self.add_motion,lambda:self.motion.removeRow(self.motion.currentRow()))
        self.tabs.addTab(motion_page,'초기 운동')
        self.contacts=self.table(['면 A','면 B','접촉 법칙','마찰계수'])
        contact_page=QWidget(); cl=QVBoxLayout(contact_page); cl.addWidget(self.contacts,1)
        self.buttons(cl,self.add_contact,lambda:self.contacts.removeRow(self.contacts.currentRow()))
        self.tabs.addTab(contact_page,'접촉')
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
        self.motion.setRowCount(0); self.contacts.setRowCount(0)
        for m in self.value['motions']: self.motion_row(m)
        for c in self.value['contacts']: self.contact_row(c)
        try:
            model=parse_inp(self.value['source']['text'])
            self.message.setText(f"절점 {len(model['nodes']):,}개 / 요소 {len(model['elements']):,}개 — Mg, mm, s, N, MPa")
        except (ValueError,KeyError,TypeError) as error: self.message.setText(str(error))

    def motion_row(self,m):
        r=self.motion.rowCount(); self.motion.insertRow(r)
        self.motion.setItem(r,0,QTableWidgetItem(m['node_set']))
        self.motion.setCellWidget(r,1,self.combo(MODES,m['mode']))
        values=[m.get('height_mm'),*m['velocity_mm_s'],*m['omega_rad_s'],*m['center_mm'],*m['translation_mm']]
        for c,value in enumerate(values,2): self.motion.setItem(r,c,QTableWidgetItem(text(value)))

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
            self.value['motions']=[]; self.value['contacts']=[]; self.populate()
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
