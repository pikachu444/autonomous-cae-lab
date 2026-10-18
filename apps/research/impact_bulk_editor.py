"""Local Impact B controls over the existing material/interface contracts."""
from copy import deepcopy
import math
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QWidget,QDialog,QVBoxLayout,QHBoxLayout,QFormLayout,QLabel,QPushButton,
    QLineEdit,QComboBox,QCheckBox,QTableWidget,QTableWidgetItem,QHeaderView,QAbstractItemView,
    QDialogButtonBox,QMessageBox,QTabWidget,QInputDialog)
from caelab import impact_b,impact_bulk,impact_interface,impact_bulk_results
from caelab.impact_model import model_from_settings
from .impact_source_editor import identity_label,field_value

BULK_SUPPORT=('시험 중인 해석 기능입니다. 솔버 실행·교정 유효성·공학 승인은 확인되지 않았습니다.\n\n'
    '원 소성 곡선을 가진 양의 체적의 아핀 C3D8/C3D8R, HEPH 1 적분점을 지원합니다. 배정 재료 전체에 적용하므로 일부 요소만 쓰려면 원 입력에서 재료를 분리하세요.\n\n'
    '열은 삼축응력비 η(원 카드 eta), 표 값은 시작 소성변형률입니다. 행은 LAW36이 파손 계산에 전달하는 EPSD [1/s]이며 DPLA/dt나 PLSR로 치환하지 않습니다. '
    '기준 변형률 속도는 원 카드 SR_REF이며 솔버 표의 속도 좌표는 EPSD/SR_REF입니다. 온도는 교정 적용범위이고 솔버의 온도 의존 축이 아닙니다.\n\n'
    '교정값과 출처가 필요합니다. 미완성 초안도 저장할 수 있지만 필수값 오류는 계산을 막습니다.')
INTERFACE_SUPPORT=('시험 중인 해석 기능입니다. 기존 LAW117과 유한 두께를 유지합니다.\n\n'
    '선택한 원 응집 요소의 아래·위 면과 실제 벌크 이웃, TYPE24 대향면과 중복 접촉을 검사합니다. '
    '활성 시각은 시간 조건이며 자동 요소 삭제 이벤트가 아닙니다. 삭제 관측 이전의 활성과 압축 이중계상 방지는 별도 솔버 확인이 필요합니다. '
    '자동 삭제 조건과 솔버의 압축·재접촉 수용은 확인되지 않았습니다.')


def number(value):
    value=value.strip()
    try:
        parsed=float(value)
        return parsed if math.isfinite(parsed) else value
    except ValueError:return value


def native_pair_groups(settings):
    from caelab.impact_native import parse_source
    definition=parse_source(settings['source'])['b_definition']
    return [g for g in (definition or {}).get('outputs',{}).get('groups',[]) if g['kind']=='pair']


def native_material_targets(settings):
    from caelab.impact_native import parse_source
    definition=parse_source(settings['source'])['b_definition'] or {}
    return {'bulk':sorted({g['members'][0] for g in definition.get('outputs',{}).get('groups',[]) if g['kind']=='bulk'}),
            'interface':sorted(int(e) for e in definition.get('cohesive',{}).get('elements',{}))}


def pair_label(settings,index,native_group=None):
    if not 0<=index<len(settings.get('contacts',[])):return '접촉 대상 다시 선택 필요'
    row=settings['contacts'][index]
    name='접촉 '+str(native_group['members'][0] if native_group else index+1)
    return name+': '+row['a']+' ↔ '+row['b']+' / '+row['law']


def element_label(model,identifier):
    row=model.get('lineage',{}).get('elements',{}).get(str(identifier),{})
    return identity_label(row if row.get('instance') else {'native_id':identifier})


def buttons(dialog,layout,apply):
    row=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
    row.button(QDialogButtonBox.StandardButton.Ok).setText('초안에 반영')
    row.button(QDialogButtonBox.StandardButton.Cancel).setText('취소')
    row.accepted.connect(apply);row.rejected.connect(dialog.reject);layout.addWidget(row)


class BulkLawDialog(QDialog):
    def __init__(self,settings,material,parent=None):
        super().__init__(parent);self.setWindowTitle('벌크 손상 교정');self.resize(870,720)
        self.settings=deepcopy(settings);self.material=material;self.applied=None
        existing=next((row for row in settings.get('bulk_damage',[]) if row['material']==material),None)
        self.law=deepcopy(existing or impact_bulk.default_law(material))
        layout=QVBoxLayout(self);self.context=QLabel();self.context.setWordWrap(True);layout.addWidget(self.context)
        self.elements=QComboBox();self.elements.setAccessibleName('선택 재료에 배정된 원 요소 전체')
        try:
            self.model=model_from_settings(settings);ids=[e for e,m in self.model['assignment'].items() if m==material]
            self.context.setText(material+' / 배정 요소 '+str(len(ids))+'개 전체에 적용\n'+', '.join(element_label(self.model,e) for e in ids[:8])+(' 외 '+str(len(ids)-8)+'개' if len(ids)>8 else ''))
            for eid in ids:self.elements.addItem(element_label(self.model,eid),eid)
        except (ValueError,KeyError,TypeError):self.model=None;self.context.setText(material+' / 원 요소와 재료를 확인해야 합니다.')
        row=QHBoxLayout();row.addWidget(QLabel('배정 원 요소 확인'));row.addWidget(self.elements,1);layout.addLayout(row)
        scope=QLabel('LAW36 + INIEVO / C3D8·C3D8R / HEPH 1 적분점');scope.setToolTip(BULK_SUPPORT)
        scope.setWordWrap(True);layout.addWidget(scope)
        self.rate=QCheckBox('LAW36 EPSD 속도별 시작표 사용 [1/s]');self.rate.setChecked(bool(self.law['initiation']['rates_s_inv']));layout.addWidget(self.rate)
        self.grid=QTableWidget();self.grid.horizontalHeader().hide();self.grid.verticalHeader().hide()
        self.grid.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch);layout.addWidget(self.grid,1)
        ini=self.law['initiation'];etas=ini['eta'] or ['',''];rates=ini['rates_s_inv'] or ['']
        self.grid.setColumnCount(len(etas)+1);self.grid.setRowCount(len(rates)+1)
        self.put(0,0,'EPSD [1/s] / η',False)
        self.grid.item(0,0).setToolTip('열: 삼축응력비 η (eta). 행: LAW36 파손 입력 EPSD [1/s]. 속도 좌표는 EPSD/SR_REF.')
        for col,value in enumerate(etas,1):self.put(0,col,value)
        for row,rate in enumerate(rates,1):
            self.put(row,0,rate if self.rate.isChecked() else '속도 축 없음',self.rate.isChecked())
            for col in range(1,len(etas)+1):
                values=ini['plastic_strain'];self.put(row,col,values[row-1][col-1] if row<=len(values) and col<=len(values[row-1]) else '')
        row=QHBoxLayout()
        for label,call in [('η 점 추가',self.add_eta),('선택 η 삭제',self.remove_eta),('속도 행 추가',self.add_rate),('선택 속도 삭제',self.remove_rate)]:
            button=QPushButton(label);button.clicked.connect(call);row.addWidget(button)
        layout.addLayout(row)
        self.rate.toggled.connect(self.toggle_rate)
        form=QFormLayout();self.fields={}
        for key,label,value in [('sr','기준 변형률 속도 [1/s]',ini['sr_ref_s_inv']),('gf','벌크 Gf [N/mm]',self.law['evolution']['gf_n_mm']),
                ('source','교정 출처',self.law['calibration']['source']),('low','교정 온도 하한 [K]',(self.law['calibration']['temperature_range_K'] or ['',''])[0]),
                ('high','교정 온도 상한 [K]',(self.law['calibration']['temperature_range_K'] or ['',''])[1]),('observed','관측 온도 [K]',self.law['calibration']['observed_temperature_K'])]:
            field=QLineEdit('' if value is None else str(value));self.fields[key]=field;form.addRow(label,field)
        layout.addLayout(form)
        self.fields['sr'].setToolTip('원 카드 SR_REF. LAW36 파손 입력 EPSD의 기준 속도이며 솔버 표 좌표는 EPSD/SR_REF입니다.')
        note=QLabel('표 값: 시작 소성변형률 [1]. 열: 삼축응력비 η. 행: LAW36 파손 입력 EPSD [1/s].')
        note.setWordWrap(True);layout.addWidget(note)
        self.status=QLabel('시험 중인 해석 기능입니다. 교정값과 출처를 입력하세요.');self.status.setWordWrap(True);layout.addWidget(self.status)
        row=QHBoxLayout();check=QPushButton('입력 검토');check.clicked.connect(self.check);row.addWidget(check)
        self.support=QPushButton('지원 범위…');self.support.setToolTip(BULK_SUPPORT)
        self.support.clicked.connect(lambda:QMessageBox.information(self,'벌크 손상 지원 범위',BULK_SUPPORT));row.addWidget(self.support);layout.addLayout(row)
        buttons(self,layout,self.apply)
    def put(self,row,col,value,editable=True):
        item=QTableWidgetItem(str(value));self.grid.setItem(row,col,item)
        if not editable:item.setFlags(item.flags()&~Qt.ItemFlag.ItemIsEditable)
    def cell(self,row,col):
        item=self.grid.item(row,col);return number(item.text()) if item else ''
    def add_eta(self):self.grid.insertColumn(self.grid.columnCount())
    def remove_eta(self):
        col=self.grid.currentColumn()
        if col>0:self.grid.removeColumn(col)
    def add_rate(self):
        if self.rate.isChecked():self.grid.insertRow(self.grid.rowCount())
    def remove_rate(self):
        row=self.grid.currentRow()
        if self.rate.isChecked() and row>0 and self.grid.rowCount()>2:self.grid.removeRow(row)
    def toggle_rate(self,enabled):
        if not enabled and self.grid.rowCount()>2:
            if QMessageBox.question(self,'속도 축 제외','첫 번째 행만 남기고 추가 속도 행을 제외할까요?',QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.Cancel)!=QMessageBox.StandardButton.Yes:
                self.rate.blockSignals(True);self.rate.setChecked(True);self.rate.blockSignals(False);return
            self.grid.setRowCount(2)
        if enabled and self.grid.rowCount()<3:self.grid.setRowCount(3)
        for row in range(1,self.grid.rowCount()):self.put(row,0,'' if enabled else '속도 축 없음',enabled)
    def edited(self):
        law=deepcopy(self.law);ini=law['initiation'];rows=range(1,self.grid.rowCount()) if self.rate.isChecked() else range(1,min(2,self.grid.rowCount()))
        ini['eta']=[self.cell(0,col) for col in range(1,self.grid.columnCount())]
        ini['rates_s_inv']=[self.cell(row,0) for row in rows] if self.rate.isChecked() else []
        ini['plastic_strain']=[[self.cell(row,col) for col in range(1,self.grid.columnCount())] for row in rows]
        ini['sr_ref_s_inv']=number(self.fields['sr'].text());law['evolution']['gf_n_mm']=number(self.fields['gf'].text())
        cal=law['calibration'];cal['source']=self.fields['source'].text()
        low,high=self.fields['low'].text(),self.fields['high'].text()
        cal['temperature_range_K']=None if not (low.strip() or high.strip()) else [number(low),number(high)]
        observed=self.fields['observed'].text();cal['observed_temperature_K']=number(observed) if observed.strip() else None
        return law
    def check(self):
        try:
            if self.model is None:raise ValueError('원 입력의 재료와 요소를 먼저 확인하세요.')
            law=self.edited();impact_bulk.validate(self.model,[law])
            for eid,material in self.model['assignment'].items():
                if material==self.material:impact_bulk.initial_geometry(self.model,eid)
            self.status.setText('입력 검토를 마쳤습니다. 시험 중인 해석 기능입니다.')
        except (ValueError,KeyError,TypeError) as error:self.status.setText(str(error).replace(' (미입력 UNKNOWN)',' (미입력)'));self.status.setToolTip(str(error))
    def apply(self):self.applied=impact_b.set_bulk_law(self.settings,self.material,self.edited());self.accept()


class InterfaceDialog(QDialog):
    def __init__(self,settings,material,parent=None):
        super().__init__(parent);self.setWindowTitle('계면 압축과 재접촉');self.resize(780,680)
        self.settings=deepcopy(settings);self.applied=None;self.material=material
        old=next((row for row in settings.get('interface_controls',[]) if row['material']==material),{})
        layout=QVBoxLayout(self);layout.addWidget(QLabel(material+' / 기존 LAW117과 유한 두께 유지'))
        form=QFormLayout();self.mode=QComboBox()
        for label,value in [('방식 선택',''),('응집 압축만 유지','COHESIVE_ONLY'),('삭제 관측 확인이 필요한 지연 TYPE24','DELAYED_TYPE24_REQUIRE_DELETION')]:self.mode.addItem(label,value)
        self.mode.setCurrentIndex(self.mode.findData(old.get('reclosure','')));form.addRow('재접촉 방식',self.mode)
        self.pair=QComboBox();self.pair.addItem('기존 접촉쌍 선택',None)
        for index,row in enumerate(settings.get('contacts',[])):
            if row['law']=='TYPE24':self.pair.addItem(pair_label(settings,index),index)
        self.pair.setCurrentIndex(max(0,self.pair.findData(old.get('contact_index'))));form.addRow('원 벌크 대향면',self.pair)
        self.start=QLineEdit('' if old.get('contact_start_s') is None else str(old['contact_start_s']));form.addRow('접촉 활성 시각 [s]',self.start);layout.addLayout(form)
        from .impact_project import MeshPreview
        self.view=MeshPreview();layout.addWidget(self.view,1)
        try:self.model=model_from_settings(settings)
        except (ValueError,KeyError,TypeError):self.model=None
        self.status=QLabel('시험 중인 해석 기능입니다. 활성 시각은 자동 삭제 이벤트가 아닙니다.');self.status.setWordWrap(True);layout.addWidget(self.status)
        row=QHBoxLayout();check=QPushButton('입력 검토');check.clicked.connect(self.check);row.addWidget(check)
        self.support=QPushButton('지원 범위…');self.support.setToolTip(INTERFACE_SUPPORT)
        self.support.clicked.connect(lambda:QMessageBox.information(self,'계면 재접촉 지원 범위',INTERFACE_SUPPORT));row.addWidget(self.support);layout.addLayout(row);buttons(self,layout,self.apply)
        self.mode.currentIndexChanged.connect(self.enabled);self.pair.currentIndexChanged.connect(self.highlight);self.enabled()
    def enabled(self):
        delayed=self.mode.currentData()=='DELAYED_TYPE24_REQUIRE_DELETION';self.pair.setEnabled(delayed);self.start.setEnabled(delayed);self.highlight()
    def highlight(self):
        if self.model is None:return
        faces=[];index=self.pair.currentData()
        if self.mode.currentData()=='DELAYED_TYPE24_REQUIRE_DELETION' and type(index) is int:
            pair=self.settings['contacts'][index]
            for name in (pair['a'],pair['b']):
                for target,side in self.model['surfaces'].get(name,[]):
                    faces.extend((eid,side) for eid in ([int(target)] if str(target).isdigit() else self.model['elsets'][target]))
        self.view.set_model(self.model,selected=faces)
    def edited(self):
        result=deepcopy(self.settings);delayed=self.mode.currentData()=='DELAYED_TYPE24_REQUIRE_DELETION'
        row={'material':self.material,'compression':'INTACT_COMPRESSION_ISYM0','reclosure':self.mode.currentData(),
            'contact_index':self.pair.currentData() if delayed else None,'contact_start_s':number(self.start.text()) if delayed else None}
        rows=result.setdefault('interface_controls',[]);old=next((i for i,v in enumerate(rows) if v['material']==self.material),None)
        if old is None:rows.append(row)
        else:rows[old]=row
        return result
    def check(self):
        try:impact_interface.validate(model_from_settings(self.settings),self.edited());self.status.setText('대응면 확인됨. 활성 시각은 자동 삭제 이벤트가 아닙니다.')
        except (ValueError,KeyError,TypeError) as error:self.status.setText(str(error));self.status.setToolTip(str(error))
    def apply(self):self.applied=self.edited();self.accept()


class ResponseDialog(QDialog):
    def __init__(self,settings,row=None,parent=None):
        self.native=settings.get('source',{}).get('format')=='RAD'
        self.native_groups=native_pair_groups(settings) if self.native else []
        self.native_targets=native_material_targets(settings) if self.native else {}
        if self.native and not (self.native_groups or any(self.native_targets.values())):
            raise ValueError('원 RAD에 선택할 재료·이력 출력 카드가 없습니다. 원 입력의 출력 설정을 확인하세요.')
        super().__init__(parent);self.setWindowTitle('벌크와 계면 결과 선택');self.resize(720,410)
        self.settings=deepcopy(settings);self.old=row;self.applied=None;self.model=model_from_settings(settings)
        layout=QVBoxLayout(self);form=QFormLayout();layout.addLayout(form)
        self.scope=QComboBox()
        for label,value in [('벌크 요소','bulk'),('원 응집 요소의 대응면','interface'),('원 접촉쌍','pair')]:
            if not self.native or (self.native_groups if value=='pair' else self.native_targets[value]):self.scope.addItem(label,value)
        self.quantity=QComboBox();self.identity=QComboBox();self.component=QComboBox()
        for label,widget in [('위치 종류',self.scope),('물리량',self.quantity),('원 대상',self.identity),('성분',self.component)]:form.addRow(label,widget)
        self.note=QLabel();self.note.setWordWrap(True);layout.addWidget(self.note);self.status=QLabel();self.status.setWordWrap(True);layout.addWidget(self.status)
        buttons(self,layout,self.apply);self.scope.currentIndexChanged.connect(self.populate);self.quantity.currentIndexChanged.connect(self.components)
        self.identity.currentIndexChanged.connect(self.components)
        self.scope.setCurrentIndex(max(0,self.scope.findData((row or {}).get('scope','bulk'))));self.populate()
        if row:
            self.quantity.setCurrentIndex(self.quantity.findData(row['quantity']));self.identity.setCurrentIndex(self.identity.findData(row['identity']));self.component.setCurrentIndex(self.component.findData(row['component']))
    def populate(self):
        self.quantity.blockSignals(True);self.quantity.clear();self.identity.clear();scope=self.scope.currentData()
        if scope=='bulk':
            for row in impact_b.editor_rows(self.settings)['quantities']:self.quantity.addItem(row['label']+' ['+row['unit']+']',row['id'])
            materials={row['material'] for row in self.settings.get('bulk_damage',[])}
            ids=[e for e,m in self.model['assignment'].items() if m in materials]
            if self.native:ids=[e for e in ids if e in self.native_targets['bulk']]
            self.note.setText('DAMA는 솔버의 손상 합입니다. 활성·삭제 및 고유 INIEVO 시작/진전 상태와 구분합니다. PLSR을 파손 계산에 쓰인 EPSD로 바꾸지 않습니다.')
        elif scope=='interface':
            for label,key in [('초기 기준계의 면 분리 [mm]','face_separation'),('초기 기준계의 벌어짐 변화 [mm]','face_opening_change'),('초기 기준계의 미끄럼 변화 [mm]','face_slip_change'),('원 응집 요소 활성 [1]','cohesive_active')]:self.quantity.addItem(label,key)
            ids=[e for e,row in self.model['elements'].items() if row['type']=='COH3D8']
            if self.native:ids=[e for e in ids if e in self.native_targets['interface']]
            self.note.setText('원 대응면의 기하량입니다. 솔버의 접촉 간극·관입·반력이나 삭제 뒤 부활한 응집 표면력으로 해석하지 않습니다.')
        else:
            for label,key in [('접촉쌍 구간 평균 힘 [N]','force'),('접촉쌍 누적 충격량 [N s]','native_impulse'),('평균 힘 표본 적분 [N s]','sampled_impulse')]:self.quantity.addItem(label,key)
            ids=list(range(len(self.settings.get('contacts',[]))))
            if self.native:ids=[group['contact_index'] for group in self.native_groups]
            self.note.setText('누적 충격량은 솔버의 원 출력값입니다. 힘은 저장 시각 사이의 평균값이며 표본 적분과 구분합니다. 지원하지 않는 솔버 버전은 미확인으로 표시합니다.')
        for eid in ids:
            group=next((g for g in self.native_groups if g['contact_index']==eid),None) if self.native and scope=='pair' else None
            self.identity.addItem(pair_label(self.settings,eid,group) if scope=='pair' else element_label(self.model,eid),eid)
        self.quantity.blockSignals(False);self.components()
    def components(self):
        self.component.clear();scope=self.scope.currentData();q=self.quantity.currentData()
        choices=('FNX','FNY','FNZ','FTX','FTY','FTZ') if scope=='pair' else ('tangent1','tangent2') if q=='face_slip_change' else ('normal',) if q in ('face_separation','face_opening_change') else ('scalar',)
        if self.native and scope=='pair':
            group=next((g for g in self.native_groups if g['contact_index']==self.identity.currentData()),{})
            choices=tuple(key for key in choices if key in group.get('tokens',[]))
        labels={'scalar':'값','normal':'법선','tangent1':'접선 1','tangent2':'접선 2','FNX':'법선 X','FNY':'법선 Y','FNZ':'법선 Z','FTX':'접선 X','FTY':'접선 Y','FTZ':'접선 Z'}
        for key in choices:self.component.addItem(labels[key],key)
    def apply(self):
        result=deepcopy(self.settings);rows=result.setdefault('b_responses',[])
        used={r['name'] for r in rows+result.get('responses',[])};index=1
        while 'bulk_result_'+str(index) in used:index+=1
        row={'name':self.old['name'] if self.old else 'bulk_result_'+str(index),'scope':self.scope.currentData(),
            'quantity':self.quantity.currentData(),'identity':self.identity.currentData(),'component':self.component.currentData()}
        if self.old:rows[rows.index(self.old)]=row
        else:rows.append(row)
        try:
            if self.native:
                if row['scope']=='pair':
                    from caelab.impact_native_b import select_response
                    group=next(g for g in self.native_groups if g['contact_index']==row['identity'])
                    result=select_response(self.settings,native_contact_id=group['members'][0],quantity=row['quantity'],
                        component=row['component'],name=row['name'],replace_name=self.old['name'] if self.old else None)
                else:
                    from caelab.impact_native_b import select_material_response
                    result=select_material_response(self.settings,scope=row['scope'],native_element_id=row['identity'],
                        quantity=row['quantity'],component=row['component'],name=row['name'],replace_name=self.old['name'] if self.old else None)
            else:impact_bulk_results.validate(self.model,result)
        except (ValueError,KeyError,TypeError,StopIteration) as error:self.status.setText(str(error) or '원 접촉쌍과 성분을 선택하세요.');return
        self.applied=result;self.accept()


class BulkPage(QWidget):
    def __init__(self,editor):
        super().__init__(editor);self.editor=editor;layout=QVBoxLayout(self);self.tabs=QTabWidget();layout.addWidget(self.tabs,1)
        self.tables={};self.actions={}
        for key,title,headers in [('bulk','벌크 손상',['원 재료','법칙','Gf [N/mm]','교정 출처']),('interface','계면 재접촉',['원 응집 재료','방식','원 대향 접촉면','활성 시각 [s]']),('response','추가 결과',['물리량 [단위]','원 대상','성분'])]:
            page=QWidget();pl=QVBoxLayout(page);table=QTableWidget(0,len(headers));table.setHorizontalHeaderLabels(headers)
            table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers);table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
            table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents);table.horizontalHeader().setStretchLastSection(True);pl.addWidget(table,1);self.tables[key]=table
            row=QHBoxLayout()
            for verb,label in [('add','추가…'),('edit','선택 수정…'),('remove','선택 삭제')]:
                button=QPushButton(label);button.clicked.connect(lambda checked=False,k=key,v=verb:self.action(k,v));row.addWidget(button);self.actions[key,verb]=button
            row.addStretch();pl.addLayout(row);self.tabs.addTab(page,title)
        self.note=QLabel();self.note.setWordWrap(True);layout.addWidget(self.note)
        row=QHBoxLayout();check=QPushButton('입력 검토');check.clicked.connect(self.check);row.addWidget(check);self.check_button=check
        self.support=QPushButton('지원 범위…');self.support.setToolTip(BULK_SUPPORT+'\n\n'+INTERFACE_SUPPORT)
        self.support.clicked.connect(lambda:QMessageBox.information(self,'벌크와 계면 지원 범위',BULK_SUPPORT+'\n\n'+INTERFACE_SUPPORT));row.addWidget(self.support);layout.addLayout(row)
        self.status=QLabel();self.status.setWordWrap(True);layout.addWidget(self.status);self.refresh()
    def refresh(self):
        settings=self.editor.edited();native=settings.get('source',{}).get('format')=='RAD';self.native=native
        self.native_groups=[];self.native_error=''
        self.native_targets={}
        if native:
            try:
                self.native_groups=native_pair_groups(settings)
                self.native_targets=native_material_targets(settings)
            except (ValueError,KeyError,TypeError) as error:self.native_error=str(error)
        try:self.model=model_from_settings(settings)
        except (ValueError,KeyError,TypeError):self.model=None
        data=impact_b.editor_rows(settings)
        for key in self.tables:self.tables[key].setRowCount(0)
        def append(key,values):
            table=self.tables[key];row=table.rowCount();table.insertRow(row)
            for col,value in enumerate(values):table.setItem(row,col,QTableWidgetItem(str(value)))
        for row in data['bulk']:append('bulk',[row['label'],row['law'],field_value(row['gf_n_mm']),row['calibration_source'] or '미확인'])
        modes={'COHESIVE_ONLY':'응집 압축만','DELAYED_TYPE24_REQUIRE_DELETION':'지연 TYPE24'}
        for row in data['interfaces']:append('interface',[row['material'],modes.get(row['reclosure'],'방식 미선택'),pair_label(settings,row['contact_index']) if type(row['contact_index']) is int else '별도 접촉 없음',field_value(row['contact_start_s']) if row['contact_start_s'] is not None else '해당 없음'])
        for row in settings.get('b_responses',[]):
            q=row['quantity'];label=impact_bulk_results.BULK[q][0] if q in impact_bulk_results.BULK else {'face_separation':'면 분리','face_opening_change':'벌어짐 변화','face_slip_change':'미끄럼 변화','cohesive_active':'응집 요소 활성','force':'접촉쌍 구간 평균 힘','native_impulse':'접촉쌍 누적 충격량','sampled_impulse':'평균 힘 표본 적분'}.get(q,q)
            unit=impact_bulk_results.BULK[q][2] if q in impact_bulk_results.BULK else '1' if q=='cohesive_active' else 'mm' if row['scope']=='interface' else 'N' if q=='force' else 'N s'
            group=next((g for g in self.native_groups if g['contact_index']==row['identity']),None)
            target=pair_label(settings,row['identity'],group) if row['scope']=='pair' else element_label(self.model,row['identity']) if self.model is not None else '원 대상 확인 필요'
            append('response',[label+' ['+unit+']',target,{'scalar':'값','normal':'법선','tangent1':'접선 1','tangent2':'접선 2','FNX':'법선 X','FNY':'법선 Y','FNZ':'법선 Z','FTX':'접선 X','FTY':'접선 Y','FTZ':'접선 Z'}.get(row['component'],row['component'])])
        for (key,verb),button in self.actions.items():
            button.setEnabled(not native or key=='response' and (bool(settings.get('b_responses')) if verb=='remove' else
                bool(self.native_groups or any(self.native_targets.values())) and self.model is not None))
        self.check_button.setEnabled(not native or self.model is not None)
        self.note.setText(('원 재료·이력 카드의 요소·계면·접촉쌍 결과를 선택합니다. 물성·세트·출력 간격은 원 입력 조건에서 명시적으로 편집하세요.' if self.native_groups or any(self.native_targets.values()) else
            '원 RAD에 선택할 재료·이력 출력 카드가 없어 결과를 추가할 수 없습니다. 원 입력 조건에서 출력 설정을 확인하세요.')
            if native else '시험 중인 해석 기능입니다. 재료 교정값과 적용 범위를 확인하세요.')
        self.note.setToolTip(self.native_error)
    def action(self,key,verb):
        if self.native and key!='response':return
        settings=self.editor.edited();table=self.tables[key];index=table.currentRow();field={'bulk':'bulk_damage','interface':'interface_controls','response':'b_responses'}[key]
        rows=settings.get(field,[])
        if verb!='add' and not 0<=index<len(rows):self.status.setText('수정할 항목을 먼저 선택하세요.');return
        if self.native and verb!='remove' and (not (self.native_groups or any(self.native_targets.values())) or self.model is None):
            self.status.setText('재료·이력 출력 카드와 원 대상을 먼저 확인하세요.');return
        if verb=='remove':
            if QMessageBox.question(self,'설정 삭제','선택한 설정을 삭제할까요? 관련 결과 선택은 확인해야 합니다.',QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.Cancel)!=QMessageBox.StandardButton.Yes:return
            if self.native:
                from caelab import impact_reference_bindings as bindings
                try:bindings.validate(settings,self.model)
                except (ValueError,KeyError,TypeError) as error:self.status.setText(str(error));return
            settings[field].pop(index)
            if self.native and bindings.KEY in settings:
                try:settings[bindings.KEY]=bindings.snapshot(settings,self.model)
                except (ValueError,KeyError,TypeError) as error:self.status.setText(str(error));return
            self.editor.replace_settings(settings);return
        try:
            if key=='response':dialog=ResponseDialog(settings,rows[index] if verb=='edit' else None,self)
            else:
                if verb=='edit':material=rows[index]['material']
                else:
                    if self.model is None:raise ValueError('원 입력의 재료와 요소를 먼저 확인하세요.')
                    types={'COH3D8'} if key=='interface' else {'C3D8','C3D8R'}
                    materials=sorted({m for eid,m in self.model['assignment'].items() if self.model['elements'][eid]['type'] in types})
                    if not materials:raise ValueError('해당 재료와 지원 요소를 찾지 못했습니다. 벌크는 소성 곡선을 가진 C3D8/C3D8R, 계면은 기존 COH3D8 LAW117입니다.')
                    material,ok=QInputDialog.getItem(self,'원 재료 선택','배정된 원 재료',materials,0,False)
                    if not ok:return
                dialog=(BulkLawDialog if key=='bulk' else InterfaceDialog)(settings,material,self)
            if dialog.exec()==QDialog.DialogCode.Accepted and dialog.applied is not None:self.editor.replace_settings(dialog.applied)
        except (ValueError,KeyError,TypeError) as error:self.status.setText(str(error))
    def check(self):
        try:
            from caelab.impact_model import validate_settings
            settings=self.editor.edited();model=model_from_settings(settings);validate_settings(settings)
            for law in settings.get('bulk_damage',[]):
                for eid,material in model['assignment'].items():
                    if material==law['material']:impact_bulk.initial_geometry(model,eid)
            self.status.setText('입력 검토를 마쳤습니다.')
        except (ValueError,KeyError,TypeError) as error:self.status.setText(str(error).replace(' (미입력 UNKNOWN)',' (미입력)'));self.status.setToolTip(str(error))
