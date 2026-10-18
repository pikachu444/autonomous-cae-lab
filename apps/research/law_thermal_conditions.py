"""Scoped Simulation condition editor for the bonded thermal bilayer profile."""
from copy import deepcopy
import math
import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QFormLayout,QLabel,QLineEdit,
    QComboBox,QCheckBox,QTabWidget,QTableWidget,QTableWidgetItem,QHeaderView,QDialogButtonBox,
    QWidget,QPushButton,QScrollArea,QMessageBox)
from caelab.law_native_thermal_regions import reference_start_settings,validate_settings
from caelab.storage import canonical_hash


def _owner_key(window):
    document=window.document
    return ((document['id'],document['session_id'],document['generation'])
            if document else None)


def _same_target(window,owner,job=None):
    return (not getattr(window,'_closed',False) and _owner_key(window)==owner
            and (job is None or window._selected_job==job))


def _table(headers):
    t=QTableWidget(0,len(headers));t.setHorizontalHeaderLabels(headers)
    t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
    t.horizontalHeader().setStretchLastSection(True);t.setAlternatingRowColors(True)
    t.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    return t


def _row(table,values):
    n=table.rowCount();table.insertRow(n)
    for j,v in enumerate(values):table.setItem(n,j,QTableWidgetItem(str(v)))


def _cell(table,r,c):
    v=table.item(r,c);return v.text().strip() if v else ''


def _number(text, *, integer=False):
    """Keep an unfinished numeric entry as text for the existing draft owner."""
    try:
        value=int(text) if integer else float(text)
        return value if math.isfinite(value) else text
    except (ValueError,TypeError,OverflowError):return text


def _numeric_cell(table,r,c):
    item=table.item(r,c)
    return _number(item.text() if item else '')


def _required_cell(table,r,c):
    value=_numeric_cell(table,r,c)
    if type(value) not in (int,float):
        table.setCurrentCell(r,c);table.setFocus()
        raise ValueError(f'{r+1}행 {table.horizontalHeaderItem(c).text()}: 유한한 숫자를 입력하세요.')
    return value


class ThermalConditions(QDialog):
    def __init__(self,settings=None,parent=None):
        super().__init__(parent);self.original=deepcopy(settings) if settings and 'thermal_regions' in settings else None
        self.setWindowTitle('두 영역 열변형 조건');self.resize(900,700);self.setMinimumSize(520,480)
        layout=QVBoxLayout(self);title=QLabel('접합된 두 재료층의 열변형');title.setObjectName('sectionHeading');layout.addWidget(title)
        note=QLabel('작은 변형률 Hex8 / mm / MPa / s / K\n완전 접합 벌크층의 지연 회복을 계산합니다. 계면 손상이나 영구 소성은 포함하지 않습니다.')
        note.setWordWrap(True);layout.addWidget(note)
        self.tabs=QTabWidget();layout.addWidget(self.tabs,1)
        geometry=QWidget();g=QVBoxLayout(geometry);form=QFormLayout();self.geometry={}
        for key,label in [('length','길이 (mm)'),('width','폭 (mm)'),('h0','아래층 두께 (mm)'),('h1','위층 두께 (mm)'),('nx','길이 요소 수'),('ny','폭 요소 수'),('nz0','아래층 두께 요소 수'),('nz1','위층 두께 요소 수')]:
            edit=QLineEdit();edit.setMaximumWidth(220);self.geometry[key]=edit;form.addRow(label,edit)
        g.addLayout(form);self.layers=_table(['영역','법칙','CTE (1/K)','Tref (K)','E (MPa)','ν','K0 (MPa)','G0 (MPa)','K1 (MPa)','G1 (MPa)','τ (s)'])
        g.addWidget(self.layers,1);self.tabs.addTab(geometry,'재료와 형상')
        self.law_choices=[]
        for i in range(2):
            _row(self.layers,['아래층' if i==0 else '위층','','','','','','','','','',''])
            combo=QComboBox();combo.addItem('탄성','linear_elastic');combo.addItem('단일 Maxwell 가지','single_branch_maxwell');self.layers.setCellWidget(i,1,combo);self.law_choices.append(combo)
        history=QWidget();h=QVBoxLayout(history);hf=QFormLayout();self.origin=QLineEdit();hf.addRow('시간 원점',self.origin)
        self.temp_mode=QComboBox();self.temp_mode.addItem('공통 온도 이력','uniform_history');self.temp_mode.addItem('Evaluation 온도 연결','port_history');hf.addRow('온도 입력',self.temp_mode)
        self.extrusion=QLineEdit();self.extrusion.setPlaceholderText('연결 시 필수: z 방향 온도가 일정하다는 사용자 선언');hf.addRow('압출 온도 가정',self.extrusion);h.addLayout(hf)
        self.history=_table(['시간 (s)','절대 온도 (K)']);h.addWidget(self.history,1)
        buttons=QHBoxLayout();add=QPushButton('시각 추가');remove=QPushButton('선택 시각 삭제');buttons.addWidget(add);buttons.addWidget(remove);buttons.addStretch();h.addLayout(buttons)
        add.clicked.connect(lambda:_row(self.history,['','']));remove.clicked.connect(lambda:self.history.removeRow(self.history.currentRow()))
        self.reference=QCheckBox('초기 T = 각 층 Tref, 변위 = 0, 점성 내부 변형률 = 0을 명시합니다.');self.reference.setChecked(False);h.addWidget(self.reference)
        self.tabs.addTab(history,'온도와 시간')
        supports=QWidget();b=QVBoxLayout(supports);bf=QFormLayout();self.preset=QComboBox();self.preset.addItem('자유 변형: 강체 모드만 고정','free');self.preset.addItem('구속: 양 끝면의 x, y, z 변위 고정','restrained');bf.addRow('새 모델 지지 조건',self.preset);b.addLayout(bf)
        self.constraints=_table(['절점 번호 (0부터, 쉼표 구분)','방향 (x/y/z)','각 시각 변위 (mm, 쉼표 구분)']);b.addWidget(self.constraints,1)
        self.constraints_note=QLabel('기존 모델은 실제 절점과 변위 이력을 편집합니다. 누락된 지지는 자동 생성하지 않습니다.');self.constraints_note.setWordWrap(True);b.addWidget(self.constraints_note)
        self.gauge=QLineEdit();bf.addRow('곡률 관측 절점 3개',self.gauge)
        self.ips=QLineEdit();bf.addRow('응력 관측 cell:q (쉼표 구분)',self.ips)
        self.tabs.addTab(supports,'지지와 관측')
        self.error=QLabel();self.error.setWordWrap(True);self.error.setStyleSheet('color: #a12828');layout.addWidget(self.error)
        self.buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText('입력 초안에 반영');self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('취소')
        self.buttons.accepted.connect(self._accept);self.buttons.rejected.connect(self.reject);layout.addWidget(self.buttons)
        self.setStyleSheet('QLabel#sectionHeading { font-size: 18px; font-weight: 600; } QTableWidget { gridline-color: #d9dfe7; }')
        if self.original:self._load(self.original)
        else:
            for _ in range(4):_row(self.history,['',''])
            self.constraints.setEnabled(False);self.gauge.setEnabled(False);self.ips.setEnabled(False)
        self.temp_mode.currentIndexChanged.connect(self._temperature_mode)
        self._temperature_mode()

    def _temperature_mode(self):
        port=self.temp_mode.currentData()=='port_history';self.extrusion.setEnabled(port)
        self.history.setHorizontalHeaderLabels(['시간 (s)','연결 슬롯 (미입력)' if port else '절대 온도 (K)'])
        if port:
            if not getattr(self,'_port_display',False):self._uniform_text=[_cell(self.history,i,1) for i in range(self.history.rowCount())]
            old=(self.original or {}).get('thermal_regions',{}).get('temperature',{})
            for i in range(self.history.rowCount()):
                item=self.history.item(i,1)
                item.setText('보존된 연결' if old.get('mode')=='port_history' and i<len(old['values']) and old['values'][i] is not None else '미입력')
                item.setFlags(item.flags()&~Qt.ItemFlag.ItemIsEditable)
        elif self.temp_mode.currentData()=='uniform_history':
            for i in range(self.history.rowCount()):
                item=self.history.item(i,1);item.setFlags(item.flags()|Qt.ItemFlag.ItemIsEditable)
                if getattr(self,'_port_display',False):item.setText(self._uniform_text[i] if i<len(self._uniform_text) else '')
        else:
            for i in range(self.history.rowCount()):self.history.item(i,1).setFlags(self.history.item(i,1).flags()&~Qt.ItemFlag.ItemIsEditable)
        self._port_display=port

    def _load(self,s):
        tr=s['thermal_regions'];points=np.asarray(s['mesh']['points']);extent=np.ptp(points,axis=0)
        vals=[extent[0],extent[1],*[r['thickness_mm'] for r in tr['regions']]]
        for key,val in zip(('length','width','h0','h1'),vals):self.geometry[key].setText(str(val))
        for key,axis in [('nx',0),('ny',1)]:self.geometry[key].setText(str(len(np.unique(points[:,axis]))-1))
        for key,r in zip(('nz0','nz1'),tr['regions']):
            nodes=np.unique(np.asarray(s['mesh']['cells'])[r['cell_ids']]);self.geometry[key].setText(str(len(np.unique(points[nodes,2]))-1))
        for edit in self.geometry.values():edit.setEnabled(False);edit.setToolTip('기존 실제 메시를 보존합니다. 다른 형상은 새 해석 모델에서 작성하세요.')
        for i,r in enumerate(tr['regions']):
            self.law_choices[i].setCurrentIndex(self.law_choices[i].findData(r['model']))
            for j,val in [(0,r['label']),(2,r['cte_per_K']),(3,r['reference_temperature_K'])]:self.layers.item(i,j).setText(str(val))
            for j,key in enumerate(('E','nu','K0','G0','K1','G1','tau'),4):self.layers.item(i,j).setText(str(r['parameters'].get(key,'')))
        self.origin.setText(tr['time_origin']);t=tr['temperature'];self.temp_mode.setCurrentIndex(self.temp_mode.findData(t['mode']))
        if t['mode']=='nodal_history':
            self.temp_mode.addItem('저장된 절점별 온도 이력','nodal_history');self.temp_mode.setCurrentIndex(2);self.temp_mode.setEnabled(False)
        self.extrusion.setText(t.get('extrusion',{}).get('statement',''))
        for i,time in enumerate(tr['time_s']):_row(self.history,[time,t['values'][i] if t['mode']=='uniform_history' else '저장된 절점 이력' if t['values'][i] is not None else '미입력'])
        self.reference.setEnabled(False);self.reference.setText('저장된 실제 초기 변위와 각 층 내부 상태를 보존합니다.')
        self.preset.setEnabled(False)
        for row in s['boundary']['constraints']:_row(self.constraints,[','.join(map(str,row['node_ids'])),row['component'],','.join(map(str,row['values_mm']))])
        self.gauge.setText(','.join(map(str,tr['observations']['curvature_nodes'])))
        self.ips.setText(','.join(str(v['cell'])+':'+str(v['quadrature']) for v in tr['observations']['integration_points']))

    def value(self):
        rr=[]
        for i in range(2):
            model=self.law_choices[i].currentData();keys=('E','nu') if model=='linear_elastic' else ('K0','G0','K1','G1','tau')
            r=deepcopy(self.original['thermal_regions']['regions'][i]) if self.original else {'id':'layer'+str(i)}
            parse=_numeric_cell if self.original else _required_cell
            r.update(label=_cell(self.layers,i,0),model=model,cte_per_K=parse(self.layers,i,2),reference_temperature_K=parse(self.layers,i,3),parameters={k:parse(self.layers,i,('E','nu','K0','G0','K1','G1','tau').index(k)+4) for k in keys});rr.append(r)
        times=[parse(self.history,i,0) for i in range(self.history.rowCount())];mode=self.temp_mode.currentData()
        if not self.original:
            if mode!='uniform_history':raise ValueError('새 모델은 실제 공통 온도 이력으로 먼저 작성한 뒤 온도 연결로 바꾸세요.')
            vals=[_required_cell(self.history,i,1) for i in range(self.history.rowCount())]
            vals_g={}
            for key,widget in self.geometry.items():
                integer=key in ('nx','ny','nz0','nz1');value=_number(widget.text(),integer=integer)
                if type(value) not in (int,float) or value<=0:
                    widget.setFocus();widget.selectAll()
                    names={'length':'길이','width':'폭','h0':'아래층 두께','h1':'위층 두께','nx':'길이 요소 수','ny':'폭 요소 수','nz0':'아래층 두께 요소 수','nz1':'위층 두께 요소 수'}
                    raise ValueError(names[key]+(': 양의 정수를 입력하세요.' if integer else ' (mm): 양의 숫자를 입력하세요.'))
                vals_g[key]=value
            s=reference_start_settings(length_mm=vals_g['length'],width_mm=vals_g['width'],thicknesses_mm=[vals_g['h0'],vals_g['h1']],counts=[vals_g[k] for k in ('nx','ny','nz0','nz1')],regions=rr,time_s=times,temperature_K=vals,time_origin=self.origin.text(),boundary_mode=self.preset.currentData(),reference_start_confirmed=self.reference.isChecked())
        else:
            s=deepcopy(self.original);tr=s['thermal_regions']
            if times!=tr['time_s'] and tr['temperature']['mode']!='uniform_history' and all(type(t) in (int,float) for t in times+tr['time_s']):raise ValueError('연결되거나 절점별로 저장된 온도의 원 시간 축은 바꿀 수 없습니다.')
            if any(a['model']!=b['model'] for a,b in zip(rr,tr['regions'])):raise ValueError('다른 법칙은 새 모델로 작성하세요. 기존 내부 상태를 다른 법칙으로 바꾸지 않습니다.')
            tr['regions']=rr;tr['time_s']=times;tr['time_origin']=self.origin.text()
            if mode=='uniform_history':tr['temperature']={'mode':mode,'unit':'K','values':[_numeric_cell(self.history,i,1) for i in range(len(times))]}
            elif mode=='port_history':
                if tr['temperature']['mode']!='port_history':tr['temperature']={'mode':mode,'unit':'K','values':[None]*len(times)}
                tr['temperature']['extrusion']={'axis':'z','invariant':True,'statement':self.extrusion.text()}
            s['boundary']['constraints']=[{'node_ids':[_number(v,integer=True) for v in self.constraints.item(i,0).text().split(',')],'component':_cell(self.constraints,i,1),'values_mm':[_number(v) for v in self.constraints.item(i,2).text().split(',')]} for i in range(self.constraints.rowCount())]
            tr['observations']={'curvature_nodes':[_number(v,integer=True) for v in self.gauge.text().split(',')],'integration_points':[dict(zip(('cell','quadrature'),(_number(part,integer=True) for part in v.split(':')))) for v in self.ips.text().split(',')]}
        return s if self.original else validate_settings(s,require_complete=False)

    def _accept(self):
        try:self.value()
        except (ValueError,TypeError,KeyError) as error:self.error.setText('조건을 확인하세요: '+str(error));return
        self.accept()


def edit(window):
    if window._busy or window.conflict:return
    draft=window.edited_draft();old=draft.get('settings',{})
    owner=_owner_key(window);buffer_hash=canonical_hash(draft)
    dialog=ThermalConditions(old,window)
    polling=window.timer.isActive();window.timer.stop()
    try:
        if dialog.exec()!=QDialog.DialogCode.Accepted:return
        if not _same_target(window,owner) or canonical_hash(window.edited_draft())!=buffer_hash:
            window.message.setText('모델이나 편집 중인 입력이 바뀌었습니다. 현재 모델에서 조건을 다시 여세요.');return
        draft={'backend':'structure.felupe.law_native','settings':dialog.value()}
        if window.document:
            window._show_document(deepcopy(window.document),preserve_draft=draft);window.local_dirty=True;window._update_actions()
            try:validate_settings(draft['settings'],require_complete=False)
            except (ValueError,TypeError,KeyError) as error:
                window.message.setText('미완성 입력을 초안에 보존했습니다. 저장할 수 있으며, 오류를 수정한 뒤 계산하세요.')
                window.message.setToolTip(str(error))
        else:window.open_document(title='두 영역 열변형',draft=draft)
    finally:
        dialog.deleteLater()
        if polling:window.timer.start()


class ContinuationConditions(QDialog):
    """Future times/temperatures only; frozen accepted IP data stay read-only."""
    def __init__(self,settings,result,parent=None):
        super().__init__(parent);self.settings=deepcopy(settings);self.result=result
        self.setWindowTitle('보존 상태에서 계속');self.resize(680,470);self.setMinimumSize(500,400)
        layout=QVBoxLayout(self);self.last=result['diagnostics']['steps'][-1]
        from caelab.law_native_thermal_regions import temperature_values
        tr=settings['thermal_regions'];T=temperature_values(settings)[tr['time_s'].index(self.last['time'])]
        if not np.all(T==T[0]):raise ValueError('절점별 초기 온도가 다른 연속 실행은 Python의 continue_settings에서 실제 미래 절점 온도를 지정하세요.')
        self.initial_temperature=float(T[0]);note=QLabel(f"마지막 평형 시각: {self.last['time']:g} s\n각 적분점의 기계적 변형률과 점성 내부 상태를 보존해 새 모델을 작성합니다.")
        note.setWordWrap(True);layout.addWidget(note)
        self.history=_table(['시간 (s)','절대 온도 (K)']);_row(self.history,[self.last['time'],self.initial_temperature]);_row(self.history,['',''])
        for j in range(2):self.history.item(0,j).setFlags(self.history.item(0,j).flags()&~Qt.ItemFlag.ItemIsEditable)
        layout.addWidget(self.history,1);add=QPushButton('미래 시각 추가');add.clicked.connect(lambda:_row(self.history,['','']));layout.addWidget(add)
        self.keep=QCheckBox('선택한 해석의 마지막 절점 구속 변위를 미래 시각에도 유지합니다.');layout.addWidget(self.keep)
        self.error=QLabel();self.error.setWordWrap(True);self.error.setStyleSheet('color:#a12828');layout.addWidget(self.error)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel);buttons.button(QDialogButtonBox.StandardButton.Ok).setText('새 모델 작성');buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('취소');buttons.accepted.connect(self._accept);buttons.rejected.connect(self.reject);layout.addWidget(buttons)

    def value(self):
        from caelab.law_native_thermal_regions import continue_settings
        if not self.keep.isChecked():raise ValueError('미래 지지 조건을 명시하세요. 새 모델 작성 뒤 실제 절점 조건을 다시 편집할 수 있습니다.')
        times=[float(_cell(self.history,i,0)) for i in range(self.history.rowCount())];values=[float(_cell(self.history,i,1)) for i in range(self.history.rowCount())]
        old=self.settings['thermal_regions'];index=old['time_s'].index(self.last['time'])
        b={'mode':'prescribed_displacement','constraints':[{**r,'values_mm':[r['values_mm'][index]]*len(times)} for r in self.settings['boundary']['constraints']]}
        return continue_settings(self.settings,self.result,time_s=times,temperature={'mode':'uniform_history','unit':'K','values':values},boundary=b)

    def _accept(self):
        try:self.value()
        except (ValueError,TypeError,KeyError) as error:self.error.setText(str(error));return
        self.accept()


def resume(window):
    if window._busy or window.conflict or not window.document:return
    job=window._selected_job
    run=next((r for r in window.document.get('runs',[]) if r['job_id']==job),None)
    settings=deepcopy((run or {}).get('draft',{}).get('settings',{}))
    if 'thermal_regions' not in settings:
        window.message.setText('보존된 두 영역 열변형 결과를 먼저 선택하세요.');return
    owner=_owner_key(window);title=window.document['title'];buffer_hash=canonical_hash(window.edited_draft())
    def loaded(result):
        if not _same_target(window,owner,job):return
        dialog=None;polling=window.timer.isActive();window.timer.stop()
        try:
            if not result.get('diagnostics',{}).get('steps'):raise ValueError('이 결과에 계속할 수 있는 평형 상태가 없습니다.')
            dialog=ContinuationConditions(settings,result,window)
            if dialog.exec()==QDialog.DialogCode.Accepted:
                if not _same_target(window,owner,job) or canonical_hash(window.edited_draft())!=buffer_hash:
                    window.message.setText('모델이나 선택한 결과가 바뀌었습니다. 보존 결과를 다시 선택하세요.');return
                draft={'backend':'structure.felupe.law_native','settings':dialog.value()}
                def create():
                    # An explicitly requested save may advance this same owner's generation.
                    current=_owner_key(window)
                    if (not getattr(window,'_closed',False) and current and current[:2]==owner[:2]
                            and window._selected_job==job):
                        window.open_document(title=title+' 계속',draft=draft)
                window._abandon(create)
        except (ValueError,KeyError,TypeError) as error:window.message.setText('보존 상태를 확인하세요: '+str(error))
        finally:
            if dialog is not None:dialog.deleteLater()
            if polling and not getattr(window,'_closed',False):window.timer.start()
    window._call(lambda:window.client.document_result(owner[0],job),loaded)
