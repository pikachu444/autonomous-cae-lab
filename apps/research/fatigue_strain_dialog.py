"""Dedicated strain-life editor; all writes/runs remain with SimulationWindow.

The dialog edits a detached draft. Preview performs only existing retained reads.
The explicit synthetic-example action uses the existing Data owner/import job.
Cancel never changes Simulation, and a late read never replaces newer edits.
"""
from __future__ import annotations

from copy import deepcopy
import math
import time

from PySide6.QtCore import Qt, QThreadPool, QTimer, Slot
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout,
    QHeaderView, QInputDialog, QLabel, QLineEdit, QMessageBox, QPushButton, QScrollArea,
    QSplitter, QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget, QCheckBox)
from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg

from caelab.fatigue_strain import default_settings, validate_settings
from caelab.fatigue_tensor import (COMPONENTS, canonical_component, read_bundle, admit_bundle,
                                   channel_history)
from .fatigue_editor import _LocalRead
from .response_selection import response_choices, choose_location
from .appearance import configure_plot_fonts

METHODS = [('단축 CMB — 평균응력 보정 없음', 'STRAIN_LIFE', 'NONE'),
           ('단축 SWT — 같은 cycle의 최대 정상응력', 'STRAIN_LIFE', 'SWT'),
           ('다축 CP-SWT — 최대 정상변형률 범위 면', 'CP_SWT', 'SWT')]
CAL_NUMBERS = [('E', 'Young 탄성계수 E'), ('sigma_f', "피로강도계수 σf′"),
    ('epsilon_f', "피로연성계수 εf′"), ('b', '강도 지수 b'), ('c', '연성 지수 c'),
    ('cycles_min', '최소 교정 수명 Nf [cycles]'), ('cycles_max', '최대 교정 수명 Nf [cycles]'),
    ('strain_amplitude_min', '최소 total strain 진폭'), ('strain_amplitude_max', '최대 total strain 진폭'),
    ('max_stress_min', 'SWT 최소 σmax'), ('max_stress_max', 'SWT 최대 σmax'),
    ('temperature_min_k', '최소 교정 온도 [K]'), ('temperature_max_k', '최대 교정 온도 [K]')]


def text(value):
    return '' if value is None else str(value)


def numeric(value, *, integer=False):
    try:
        v = float(value)
        if not math.isfinite(v):
            return value
        return int(v) if integer and v.is_integer() else v
    except (ValueError, TypeError, OverflowError):
        return value


def combo(items, value=None):
    widget = QComboBox()
    for label, data in items:
        widget.addItem(label, data)
    # Qt converts tuple item data to QVariantList; match before that conversion.
    index = next((i for i,(_,data) in enumerate(items) if data == value),-1)
    if index < 0 and value is not None:
        widget.addItem('미완성 입력: ' + text(value), value)
        index = widget.count()-1
    widget.setCurrentIndex(max(0,index))
    return widget


def location_label(location):
    if isinstance(location, str):
        return location
    if isinstance(location, dict):
        labels={'element_id':'요소','element':'요소','point':'적분점','gauss':'적분점',
                'subpoint':'하위점','layer':'층','face':'면','node_id':'절점','id':'번호'}
        return ' / '.join(labels.get(k,k)+' '+str(v) for k,v in location.items())
    return '위치 미확인'


class StrainLifeEditor(QDialog):
    def __init__(self, client, settings, parent=None):
        super().__init__(parent)
        configure_plot_fonts()
        self.client, self.value = client, deepcopy(settings)
        self._closed, self._serial, self._worker, self._after, self._loading = False, 0, None, None, True
        self._reference = deepcopy((settings.get('source') or {}).get('result'))
        self._source_title = (settings.get('source') or {}).get('title','')
        self._bundle = None
        self._host_key = self._current_host_key()
        self.setWindowTitle('변형률 피로 조건'); self.resize(1180,820); self.setMinimumSize(720,540)
        self.finished.connect(self._closed_dialog)
        layout=QVBoxLayout(self); layout.setSpacing(10)
        header=QHBoxLayout(); self.source_label=QLabel(self._source_title or '저장된 total strain/stress 이력을 선택하세요')
        self.source_label.setWordWrap(True); header.addWidget(self.source_label,1)
        self.choose_button=QPushButton('저장 이력 선택…');self.choose_button.clicked.connect(self.choose_source);header.addWidget(self.choose_button)
        self.example_button=QPushButton('공개 합성 예제…');self.example_button.clicked.connect(self.import_example);header.addWidget(self.example_button)
        layout.addLayout(header)
        self.tabs=QTabWidget();layout.addWidget(self.tabs,1)
        self._build_source_tab(settings)
        self._build_calibration_tab(settings)
        self._build_search_tab(settings)
        self.message=QLabel();self.message.setWordWrap(True);self.message.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.message)
        self.buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText('조건 적용')
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('취소')
        self.buttons.accepted.connect(self.accept);self.buttons.rejected.connect(self.reject);layout.addWidget(self.buttons)
        self._loading=False;self._method_changed()
        self._load_saved_selectors()
        self._show_validation()
        if self._reference:QTimer.singleShot(0,self.load_metadata)

    def _current_host_key(self):
        parent=self.parent()
        doc=getattr(parent,'document',None)
        return (doc.get('id'),doc.get('session_id'),doc.get('generation')) if isinstance(doc,dict) else None

    def relevant(self):
        return not self._closed and self._current_host_key()==self._host_key

    def _build_source_tab(self, settings):
        page=QWidget();outer=QVBoxLayout(page);self.tabs.addTab(page,'입력과 원 이력')
        controls=self.source_controls=QFormLayout();outer.addLayout(controls)
        self.method=combo([(a,(b,c)) for a,b,c in METHODS],(settings.get('method'),settings.get('mean_stress')))
        controls.addRow('평가 방법',self.method)
        initial=next(iter(((settings.get('source') or {}).get('channels',{}).get('strain') or {'xx':''})))
        self.axis=combo([(c,c) for c in COMPONENTS[:3]],initial);controls.addRow('단축 방향',self.axis)
        interpretation=settings.get('interpretation',{})
        self.shear=combo([('미확인','UNKNOWN'),('tensor εij','TENSOR'),('engineering γij → εij=γij/2','ENGINEERING')],interpretation.get('strain_shear'))
        controls.addRow('원 변형률 shear',self.shear)
        self.state=combo([('안정 cyclic 이력','STABILIZED_CYCLIC'),('비안정 이력','NONSTABILIZED'),('상태 미확인','UNKNOWN')],interpretation.get('history_state'))
        controls.addRow('이력 상태',self.state)
        self.constitutive=QLineEdit(text(interpretation.get('constitutive_source')));controls.addRow('시험 / 구성식 출처',self.constitutive)
        self.temperature=QLineEdit(text(settings.get('temperature_k')));controls.addRow('평가 온도 [K]',self.temperature)
        split=QSplitter(Qt.Orientation.Horizontal);outer.addWidget(split,1)
        left=QWidget();left_layout=QVBoxLayout(left);split.addWidget(left)
        self.channels=QTableWidget(12,4);self.channels.setHorizontalHeaderLabels(['입력','성분','저장 채널과 단위','위치'])
        self.channels.setObjectName('strainFatigueChannels')
        self.channels.horizontalHeader().setSectionResizeMode(2,QHeaderView.ResizeMode.Stretch)
        self.channels.horizontalHeader().setSectionResizeMode(0,QHeaderView.ResizeMode.ResizeToContents)
        self.channels.horizontalHeader().setSectionResizeMode(1,QHeaderView.ResizeMode.ResizeToContents)
        self.channels.horizontalHeader().setSectionResizeMode(3,QHeaderView.ResizeMode.ResizeToContents)
        self.channel_boxes={};self.location_buttons={}
        for i,(role,c) in enumerate((r,c) for r in ('strain','stress') for c in COMPONENTS):
            for j,v in enumerate(('전체 변형률' if role=='strain' else 'Cauchy 응력',c)):
                item=QTableWidgetItem(v);item.setFlags(item.flags()&~Qt.ItemFlag.ItemIsEditable);self.channels.setItem(i,j,item)
            box=QComboBox();box.addItem('선택 안 함',None);box.setMinimumContentsLength(12)
            box.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            box.currentIndexChanged.connect(self._edited);self.channels.setCellWidget(i,2,box);self.channel_boxes[(role,c)]=box
            button=QPushButton('위치…');button.clicked.connect(lambda checked=False,r=role,k=c:self.choose_channel_location(r,k))
            self.channels.setCellWidget(i,3,button);self.location_buttons[(role,c)]=button
        left_layout.addWidget(self.channels,1)
        self.review_button=QPushButton('단위·동시 시각·위치 검토');self.review_button.setProperty('appearanceRole','primary')
        self.review_button.clicked.connect(self.review);left_layout.addWidget(self.review_button)
        self.review_label=QLabel('원 채널의 단위/측도/기준계를 바꾸려면 Data의 명시 mapping을 수정하고 새로 가져오세요. 누락 성분은 채우지 않습니다.')
        self.review_label.setWordWrap(True);left_layout.addWidget(self.review_label)
        self.figure=Figure(figsize=(5,4),layout='constrained');self.canvas=FigureCanvasQTAgg(self.figure);split.addWidget(self.canvas)
        split.setSizes([600,510])
        self.method.currentIndexChanged.connect(self._method_changed);self.axis.currentIndexChanged.connect(self._method_changed)
        for box in (self.shear,self.state):box.currentIndexChanged.connect(self._edited)
        for field in (self.temperature,self.constitutive):field.textEdited.connect(self._edited)

    def _build_calibration_tab(self, settings):
        scroller=QScrollArea();scroller.setWidgetResizable(True);page=QWidget();form=QFormLayout(page)
        scroller.setWidget(page);self.tabs.addTab(scroller,'ε–N 교정 자료')
        c=settings.get('calibration',{})
        label=QLabel('εa = (σf′/E)(2Nf)^b + εf′(2Nf)^c\nSWT: σmax εa = (σf′²/E)(2Nf)^(2b) + σf′ εf′(2Nf)^(b+c)\nNf는 cycles, 2Nf는 reversals입니다. 기본 재료 계수는 없습니다.')
        label.setWordWrap(True);form.addRow(label)
        self.stress_unit=combo([('MPa','MPa'),('Pa','Pa')],c.get('stress_unit'))
        self.strain_unit=combo([('무차원 [1]','1'),('퍼센트 [%]','%')],c.get('strain_unit'))
        form.addRow('E, σf′, σmax의 교정 단위',self.stress_unit)
        form.addRow('εf′, εa의 교정 단위',self.strain_unit)
        self.cal_fields={}
        for key,label in CAL_NUMBERS:
            field=QLineEdit(text(c.get(key)));field.setObjectName('fatigueCalibration_'+key)
            field.textEdited.connect(self._edited);form.addRow(label,field);self.cal_fields[key]=field
        for key,label in [('reference','자료 출처'),('conditions','시험 조건과 적용 범위'),('failure_definition','실패 정의')]:
            field=QLineEdit(text(c.get(key)));field.textEdited.connect(self._edited);form.addRow(label,field);self.cal_fields[key]=field
        self.coefficient_basis=combo([('완전 양진 축방향 ε–N (평균응력 보정 전)','FULLY_REVERSED_AXIAL_STRAIN_LIFE')],c.get('coefficient_basis'))
        self.test_basis=combo([('축방향 정상 시험','AXIAL_NORMAL')],c.get('test_basis'))
        form.addRow('계수의 평균응력 기준',self.coefficient_basis);form.addRow('교정 시험 기준',self.test_basis)
        self.cal_state=combo([('계수 상태 미확인','UNKNOWN'),('안정 cyclic 계수','STABILIZED')],c.get('cyclic_state'))
        form.addRow('교정 상태',self.cal_state)
        note=QLabel('완전 양진 축방향 ε–N 시험 기준입니다. 이미 평균응력 보정한 계수는 이중 보정하지 않습니다. 축방향 교정은 전단 지배 파괴의 실재 재료 검증이 아닙니다.')
        note.setWordWrap(True);form.addRow(note)
        for box in (self.stress_unit,self.strain_unit,self.cal_state,self.coefficient_basis,self.test_basis):box.currentIndexChanged.connect(self._edited)

    def _build_search_tab(self, settings):
        scroller=QScrollArea();scroller.setWidgetResizable(True);page=QWidget();form=QFormLayout(page)
        scroller.setWidget(page);self.tabs.addTab(scroller,'면 탐색과 수명 가정')
        note=QLabel('기본 CP-SWT는 최대 정상변형률 범위 면입니다. 최대 SWT 또는 최대 damage 면은 별도 진단값이며 선정 기준을 몰래 바꾸지 않습니다. n과 −n은 같은 면입니다.')
        note.setWordWrap(True);form.addRow(note)
        self.search_fields={}
        for key,label in [('polar_steps','극각 분할수'),('refinement_levels','추가 세분화 단계'),('range_relative_tolerance','격자 최대 range 상대변화 허용치')]:
            field=QLineEdit(text(settings.get('search',{}).get(key)));field.textEdited.connect(self._edited)
            form.addRow(label,field);self.search_fields[key]=field
        self.basis=QTableWidget(3,3);self.basis.setMaximumHeight(140)
        self.basis.setHorizontalHeaderLabels(['검색축 1','검색축 2','검색축 3']);self.basis.setVerticalHeaderLabels(['모델 x','모델 y','모델 z'])
        self.basis.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        basis=settings.get('search',{}).get('basis',[[1,0,0],[0,1,0],[0,0,1]])
        for i in range(3):
            for j in range(3):self.basis.setItem(i,j,QTableWidgetItem(text(basis[i][j])))
        self.basis.itemChanged.connect(self._edited);form.addRow('고정 검색기저 (열 벡터)',self.basis)
        self.root_fields={}
        for key,label in [('relative_tolerance','양의 Nf root 상대폭'),('residual_relative_tolerance','식의 상대잔차 허용치'),('max_iterations','root 최대 반복 횟수')]:
            field=QLineEdit(text(settings.get('root',{}).get(key)));field.textEdited.connect(self._edited)
            form.addRow(label,field);self.root_fields[key]=field
        self.repeat=QCheckBox('같은 안정 tensor 블록이 반복된다고 명시적으로 가정');self.repeat.setChecked(settings.get('repeat_block') is True)
        self.repeat.toggled.connect(self._edited);form.addRow(self.repeat)
        self.boundary_fields={}
        for key,label in [('strain_absolute','반복 tensor 경계 절대 허용치 [1]'),('stress_mpa_absolute','반복 tensor 경계 절대 허용치 [MPa]')]:
            field=QLineEdit(text(settings.get('repeat_tolerance',{}).get(key)));field.textEdited.connect(self._edited)
            form.addRow(label,field);self.boundary_fields[key]=field
        note=QLabel('유한 이력의 부분 damage와 반복 블록 D=1 수명은 다릅니다. 전체 동시 tensor 경계와 residual half-cycle σmax 대응이 맞지 않으면 반복 수명은 미정입니다. 없는 peak/성분은 보간하지 않습니다.')
        note.setWordWrap(True);form.addRow(note)

    def _load_saved_selectors(self):
        channels=(self.value.get('source') or {}).get('channels',{})
        for (role,c),box in self.channel_boxes.items():
            selector=channels.get(role,{}).get(c)
            if selector:
                box.blockSignals(True)
                box.addItem('보존 선택 (메타데이터 확인)',{'selector':selector,'label':'보존 선택','definition':{}})
                box.setCurrentIndex(box.count()-1);box.blockSignals(False)

    def _method_changed(self,*_):
        method,mean=self.method.currentData()
        axis=self.axis.currentData();self.axis.setEnabled(method!='CP_SWT')
        self.source_controls.setRowVisible(self.axis,method!='CP_SWT')
        self.source_controls.setRowVisible(self.shear,method=='CP_SWT')
        for row,((role,c),box) in enumerate(self.channel_boxes.items()):
            active=(role=='strain' or mean=='SWT') and (method=='CP_SWT' or c==axis)
            self.channels.setRowHidden(row,not active)
        if hasattr(self,'cal_fields'):
            for key in ('max_stress_min','max_stress_max'):self.cal_fields[key].setEnabled(mean=='SWT')
        self._edited()

    def _edited(self,*_):
        if self._loading:return
        self._serial+=1;self._bundle=None;self._show_validation()

    def _show_validation(self):
        if not hasattr(self,'message'):return
        try:validate_settings(self.edited())
        except (ValueError,KeyError,TypeError,IndexError) as error:
            self.message.setText('미완성 조건 — '+str(error)+'\n초안 적용·저장은 가능하며 잘못된 필수값은 실행을 차단합니다.')
        else:self.message.setText('조건 입력을 확인했습니다. 원 이력을 검토한 뒤 조건 적용 → 기존 Simulation의 실행을 명시적으로 누르세요.')

    def edited(self):
        value=deepcopy(self.value);method,mean=self.method.currentData();value.update(method=method,mean_stress=mean)
        c=value['calibration']
        for key,field in self.cal_fields.items():
            c[key]=field.text() if key in ('reference','conditions','failure_definition') else numeric(field.text().strip())
        c.update(stress_unit=self.stress_unit.currentData(),strain_unit=self.strain_unit.currentData(),cyclic_state=self.cal_state.currentData(),coefficient_basis=self.coefficient_basis.currentData(),test_basis=self.test_basis.currentData())
        value['temperature_k']=numeric(self.temperature.text().strip())
        value['interpretation'].update(strain_shear=self.shear.currentData(),history_state=self.state.currentData(),constitutive_source=self.constitutive.text())
        value['source']=None
        if self._reference:
            groups={'strain':{},**({'stress':{}} if mean=='SWT' else {})}
            for (role,component),box in self.channel_boxes.items():
                if role in groups and (method=='CP_SWT' or component==self.axis.currentData()):
                    choice=box.currentData();groups[role][component]=choice.get('selector') or '' if isinstance(choice,dict) else ''
            value['source']={'result':deepcopy(self._reference),'title':self._source_title,'channels':groups}
        for key,field in self.search_fields.items():value['search'][key]=numeric(field.text().strip(),integer=key!='range_relative_tolerance')
        value['search']['basis']=[[numeric(self.basis.item(i,j).text().strip()) for j in range(3)] for i in range(3)]
        value['root']={key:numeric(field.text().strip(),integer=key=='max_iterations') for key,field in self.root_fields.items()}
        value['repeat_tolerance']={key:numeric(field.text().strip()) for key,field in self.boundary_fields.items()}
        value['repeat_block']=self.repeat.isChecked()
        return value

    def _closed_dialog(self,*_):
        self._closed=True;self._serial+=1;self._after=None

    def call(self,function,after):
        if self._worker or not self.relevant():return False
        self._after=after;self._request_serial=self._serial
        self._worker=_LocalRead(function)
        self._worker.signals.finished.connect(self._done,Qt.ConnectionType.QueuedConnection)
        for button in (self.choose_button,self.example_button,self.review_button):button.setEnabled(False)
        QThreadPool.globalInstance().start(self._worker);return True

    @Slot(object,object)
    def _done(self,value,error):
        after=self._after;self._worker=None;self._after=None
        if self._closed:return
        for button in (self.choose_button,self.example_button,self.review_button):button.setEnabled(True)
        if not self.relevant() or self._request_serial!=self._serial:
            self.message.setText('조건 또는 현재 문서가 바뀌어 늦은 읽기 응답을 적용하지 않았습니다. 다시 검토하세요.');return
        if error:self.message.setText('읽기/가져오기 실패 — '+str(error));return
        try:
            if after:after(value)
        except (ValueError,TypeError,KeyError,IndexError) as error:self.message.setText(str(error))

    def choose_source(self):
        def listed(payload):
            docs=[d for d in payload['documents'] if d.get('kind') in ('data','simulation','material','pde','evaluation')]
            if not docs:self.message.setText('Data에서 tensor CSV를 명시 mapping으로 가져와 저장하거나 공개 합성 예제를 여세요.');return
            labels=[str(i+1)+'. '+d['title'] for i,d in enumerate(docs)]
            label,ok=QInputDialog.getItem(self,'저장된 tensor 이력','문서',labels,0,False)
            if ok and self.relevant():self.call(lambda:self.client.document_read(docs[labels.index(label)]['id']),opened)
        def opened(doc):
            runs=[r for r in doc.get('runs',[]) if r.get('retention_complete') and r.get('retained_result')]
            labels=['보존 계산 '+str(i+1) for i in range(len(runs))]
            if not runs:self.message.setText('원 계산과 Data import 결과를 먼저 저장하세요.');return
            label,ok=QInputDialog.getItem(self,'동시 tensor 원자료','보존 계산',labels,0,False)
            if not ok or not self.relevant():return
            job=runs[labels.index(label)]['job_id']
            def described(payload):
                ref,metadata=payload;self._reference=ref;self._source_title=doc['title']
                self._method_changed()
                self.source_label.setText(self._source_title);self._populate_choices(metadata,retain=False)
                self.message.setText('실제 채널·위치와 shear 의미를 검토하세요. 채널 선택은 계산하지 않습니다.')
            self.call(lambda:(self.client.document_result_reference(doc['id'],job),self.client.document_result_metadata(doc['id'],job)),described)
        self.call(self.client.documents,listed)

    def load_metadata(self):
        ref=deepcopy(self._reference)
        def read():
            if self.client.document_result_reference(ref['document_id'],ref['job_id'])!=ref:raise ValueError('보존 원결과가 변경되었습니다')
            metadata=self.client.document_result_metadata(ref['document_id'],ref['job_id'])
            if self.client.document_result_reference(ref['document_id'],ref['job_id'])!=ref:raise ValueError('읽는 중 원결과가 변경되었습니다')
            return metadata
        self.call(read,lambda metadata:self._populate_choices(metadata,retain=True))

    def _populate_choices(self,metadata,*,retain):
        choices=response_choices(metadata)
        self._loading=True
        try:
            for (role,component),box in self.channel_boxes.items():
                old=box.currentData() if retain else None
                matches=[c for c in choices if c['definition'].get('unit') in (('1','%') if role=='strain' else ('Pa','MPa'))
                         and canonical_component(c['definition'].get('component'))==component]
                box.blockSignals(True);box.clear();box.addItem('선택 안 함',None)
                chosen=0
                for c in matches:
                    box.addItem(c['label'],deepcopy(c))
                    if old and old.get('selector')==c.get('selector'):chosen=box.count()-1
                if old and chosen==0 and old.get('selector'):
                    box.addItem('보존 위치 선택 (재검토 필요)',deepcopy(old));chosen=box.count()-1
                if not old and len(matches)==1:chosen=1  # Visible unique-channel proposal; review is still explicit.
                box.setCurrentIndex(chosen);box.blockSignals(False)
        finally:self._loading=False
        self._serial+=1;self._bundle=None;self._show_validation()

    def choose_channel_location(self,role,component):
        choice=self.channel_boxes[(role,component)].currentData()
        if not choice or not self._reference:return
        ref=deepcopy(self._reference);serial=self._serial
        selected=choose_location(self,self.client,ref['document_id'],ref['job_id'],choice,
                                 relevant=lambda:self.relevant() and self._serial==serial)
        if selected:
            box=self.channel_boxes[(role,component)];box.setItemData(box.currentIndex(),selected);self._edited()
            self.message.setText('정확한 위치를 선택했습니다. 모든 성분의 같은 위치·clock 여부는 이력 검토에서 확인합니다.')

    def review(self):
        s=self.edited()
        def read():
            bundle=read_bundle(self.client,s['source'],method=s['method'],mean_stress=s['mean_stress'])
            return bundle,admit_bundle(bundle,s)
        def shown(payload):
            bundle,a=payload;self._bundle=bundle
            self.figure.clear();ax=self.figure.add_subplot(211);stress_ax=self.figure.add_subplot(212,sharex=ax)
            for i,c in enumerate(a['components']):
                ax.plot(a['times'],a['strain'][:,i],label=c)
                if a['stress'] is not None:stress_ax.plot(a['times'],a['stress'][:,i],label=c)
            ax.set_ylabel('total strain [1]');stress_ax.set_ylabel('Cauchy stress [MPa]');stress_ax.set_xlabel('시간 [s]')
            ax.legend(ncols=3,fontsize='small')
            if a['stress'] is not None:stress_ax.legend(ncols=3,fontsize='small')
            else:stress_ax.text(.5,.5,'CMB/NONE에는 응력 입력이 필요하지 않습니다',ha='center',transform=stress_ax.transAxes)
            self.canvas.draw_idle()
            lines=[location_label(a['location']),a['frame']]
            for role,channels in a['channels'].items():
                for c,r in channels.items():
                    unit=bundle['responses'][s['source']['channels'][role][c]]['unit']
                    lines.append(role+' '+c+': '+unit+' → '+r['unit']+', 배율 '+format(r['factor_to_internal'],'.7g'))
            self.review_label.setToolTip('\n'.join(lines))
            self.review_label.setText(str(len(a['times']))+'개 동시 표본 / '+format(a['times'][0],'.6g')+'–'+format(a['times'][-1],'.6g')+
                ' s\n전체 변형률 [1]'+(' / Cauchy 응력 [MPa]' if a['stress'] is not None else '')+'\n'+location_label(a['location']))
            self.message.setText('원 단위·동시 시각·위치를 확인했습니다. 조건 적용 후 평가를 실행하세요.')
        self.call(read,shown)

    def import_example(self):
        answer=QMessageBox.question(self,'공개 합성 예제','실재 재료가 아닌 공개 합성 CSV와 교정 계수를 명시적으로 불러옵니다.\n기존 Data 문서에서 가져오기·저장을 수행합니다. 피로 계산은 실행하지 않습니다.\n현재 조건 입력을 이 예제로 바꾸시겠습니까?',
                                   QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.Cancel,QMessageBox.StandardButton.Cancel)
        if answer!=QMessageBox.StandardButton.Yes:return
        method,mean=self.method.currentData()
        def imported():
            from caelab.fatigue_example import csv_bytes,data_draft,settings as example_settings
            upload=self.client.upload('synthetic-total-strain-tensor.csv',csv_bytes())
            doc=self.client.document_open(kind='data',title='공개 합성 tensor (실재 재료 아님)',draft=data_draft(upload.get('data_id',upload.get('id'))))
            def command(document,operation):
                return self.client.document_command(document['id'],operation,{},session_id=document['session_id'],expected_generation=document['generation'])
            submission=command(doc,'data.import');job=submission['job']['id'];deadline=time.monotonic()+30
            while time.monotonic()<deadline:
                state=self.client.status(job)
                if state['state'] in {'SUCCEEDED','FAILED','CANCELLED','REJECTED','INTERRUPTED','PARTIAL_FAILURE'}:
                    if state['state']!='SUCCEEDED':raise ValueError('공개 Data 가져오기 실패: '+state['state'])
                    break
                time.sleep(.05)
            else:
                self.client.cancel(job)
                raise ValueError('Data 가져오기 응답을 확인하지 못했습니다. Data 문서에서 실제 종료 상태를 확인하세요.')
            doc=command(self.client.document_read(doc['id']),'document.save')['document']
            ref=self.client.document_result_reference(doc['id'],job)
            return example_settings(ref,method=method,mean_stress=mean),self.client.document_result_metadata(doc['id'],job)
        def shown(payload):
            value,metadata=payload;self.value=value;self._reference=deepcopy(value['source']['result']);self._source_title=value['source']['title']
            self._loading=True
            try:
                for key,field in self.cal_fields.items():field.setText(text(value['calibration'][key]))
                self.stress_unit.setCurrentIndex(self.stress_unit.findData('MPa'));self.strain_unit.setCurrentIndex(self.strain_unit.findData('1'))
                self.cal_state.setCurrentIndex(self.cal_state.findData('STABILIZED'))
                self.coefficient_basis.setCurrentIndex(self.coefficient_basis.findData(value['calibration']['coefficient_basis']))
                self.test_basis.setCurrentIndex(self.test_basis.findData(value['calibration']['test_basis']))
                self.temperature.setText(text(value['temperature_k']))
                self.shear.setCurrentIndex(self.shear.findData('TENSOR'));self.state.setCurrentIndex(self.state.findData('STABILIZED_CYCLIC'))
                self.constitutive.setText(value['interpretation']['constitutive_source'])
                for key,field in self.search_fields.items():field.setText(text(value['search'][key]))
                self.axis.setCurrentIndex(self.axis.findData('xx'))
                for key,field in self.root_fields.items():field.setText(text(value['root'][key]))
                for key,field in self.boundary_fields.items():field.setText(text(value['repeat_tolerance'][key]))
                for i in range(3):
                    for j in range(3):self.basis.item(i,j).setText(text(value['search']['basis'][i][j]))
                self.repeat.setChecked(True)
            finally:self._loading=False
            self._method_changed()
            self.source_label.setText(self._source_title);self._populate_choices(metadata,retain=False)
            self.message.setText('공개 합성 Data를 실제로 가져와 저장했습니다. 이력 검토 → 조건 적용 → Simulation 실행으로 계산하세요. 취소해도 명시 생성한 Data 문서는 보존됩니다.')
        self.call(imported,shown)


def choose_editor(client,settings,parent):
    labels=['기존 S–N 응력 수명',*[m[0] for m in METHODS]]
    active=next((i+1 for i,(_,m,c) in enumerate(METHODS) if (m,c)==(settings.get('method'),settings.get('mean_stress'))),0)
    label,ok=QInputDialog.getItem(parent,'반복하중 조건','평가 방법',labels,active,False)
    if not ok:return None
    choice=labels.index(label)
    if choice==0:
        from .fatigue_editor import FatigueEditor
        from caelab.fatigue import default_settings as sn_defaults
        return FatigueEditor(client,settings if 'method' not in settings else sn_defaults(),parent)
    _,method,mean=METHODS[choice-1]
    value=deepcopy(settings) if 'method' in settings else default_settings(method,mean)
    value.update(method=method,mean_stress=mean)
    return StrainLifeEditor(client,value,parent)
