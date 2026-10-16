"""Task settings for existing experiment analysis; no owner or computation."""
from copy import deepcopy
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QFormLayout,QLabel,QComboBox,
    QLineEdit,QTabWidget,QWidget,QScrollArea,QTableWidget,QTableWidgetItem,QCheckBox,
    QDialogButtonBox,QPushButton,QHeaderView)
from caelab.experiment_observation_uncertainty import template, KINDS, LABELS, _source_channel
from caelab.experiment_uncertainty import MAX_SAMPLES, MAX_VARIABLES


def source_options(reader, source):
    value=deepcopy(source) if source['kind']=='observation_chain' else template(reader,source)
    choices={}
    for side,operand in value['operands'].items():
        first=next(iter(operand['channels'].values()))
        if first['kind']=='result_response':
            ref=first['reference'];result=reader.document_result(ref['document_id'],ref['job_id'])
            selections={name:{'kind':'result_response','reference':deepcopy(ref),'response':name}
                for name,response in result['responses'].items() if response['kind'] in ('scalar','series')}
        else:
            args={'document_id':first['document_id'],'processing_revision':first['revision']}
            if hasattr(reader,'data_documents'):
                from caelab.data_processing_document import result as read
                result=read(reader.data_documents,args['document_id'],args['processing_revision'])
            else:result=reader.request('/api/workbench/data-material',{'operation':'data.processing.result','arguments':args})
            from caelab.storage import canonical_hash
            selections={name:{**first,'channel':name,'channel_sha256':canonical_hash(channel)} for name,channel in result['channels'].items()}
        choices[side]={}
        for name,selected in selections.items():
            response=(result['responses'][name] if first['kind']=='result_response' else result['channels'][name])
            raw=response.get('raw_samples',{})
            count=(len(raw['source_rows']) if raw and response.get('calibration',response.get('mapping',{}).get('calibration'))
                   else len(response['samples']) if first['kind']=='processing_channel'
                   else len(response['value']) if isinstance(response['value'],list) else 1)
            limit=min(MAX_SAMPLES,MAX_VARIABLES-(3 if raw and response.get('calibration',response.get('mapping',{}).get('calibration')) else 0))
            choices[side][name]={'source':selected,'variables':None,
                'unavailable':('원 표본 한도를 넘거나 빈 채널입니다. 더 짧은 보존 구간을 선택하세요.' if not 0<count<=limit else None),
                '_load_variables':lambda selected=deepcopy(selected):_source_channel(reader,selected)['problem']['variables']}
    return value,choices


class ObservationDialog(QDialog):
    def __init__(self,definition,choices,parent=None):
        super().__init__(parent);self.setWindowTitle('관측 변환');self.resize(700,690);self.setMinimumSize(420,480)
        self.definition=deepcopy(definition);self.choices=choices;self.pages={}
        layout=QVBoxLayout(self);title=QLabel('관측량과 시간 정렬');title.setProperty('appearanceRole','section');layout.addWidget(title)
        info=QLabel('실제 원자료와 교정은 유지합니다. 변환한 값과 불확실성은 새 분석 계획으로 보관합니다.');info.setWordWrap(True);layout.addWidget(info)
        self.tabs=QTabWidget();layout.addWidget(self.tabs,1)
        for side,value in definition['operands'].items():self._operand(side,value)
        self.error=QLabel();self.error.setWordWrap(True);layout.addWidget(self.error)
        box=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
        box.button(QDialogButtonBox.StandardButton.Ok).setText('변환 설정 사용');box.button(QDialogButtonBox.StandardButton.Cancel).setText('취소')
        box.accepted.connect(self._accept);box.rejected.connect(self.reject);layout.addWidget(box)

    def _line(self,text='',hint=''):
        field=QLineEdit(str(text));field.setMinimumWidth(0);field.setPlaceholderText(hint);return field

    def _operand(self,side,value):
        page=QWidget();outer=QVBoxLayout(page);outer.setContentsMargins(0,0,0,0)
        sections=QTabWidget();outer.addWidget(sections);self.tabs.addTab(page,'관측 A' if side=='A' else '예측 B')
        def section(title):
            body=QWidget();layout=QVBoxLayout(body);layout.setContentsMargins(12,12,12,12);layout.setSpacing(10)
            scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setWidget(body);sections.addTab(scroll,title);return layout
        form=section('원 채널');details=section('기준과 치수');timed=section('시간과 공유 입력')
        fields={'original':deepcopy(value),'sections':sections};self.pages[side]=fields
        top=QFormLayout();top.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows);form.addLayout(top)
        q=fields['quantity']=QComboBox()
        for key in KINDS:q.addItem(LABELS[key],key)
        q.setCurrentIndex(q.findData(value['quantity']));top.addRow('사용할 관측량',q)
        order=fields['order']=QComboBox();order.addItem('원 시각에서 변환 → 시간 정렬','transform_then_align');order.addItem('성분별 시간 정렬 → 변환','align_then_transform')
        order.setCurrentIndex(order.findData(value['order']));top.addRow('저장할 연산 순서',order)
        gap=fields['gap']=self._line('' if value['max_gap_s'] is None else value['max_gap_s'],'실제 허용할 최대 원 시각 간격');top.addRow('최대 정렬 간격 [s]',gap)
        channel_table=QTableWidget(0,2);fields['channels']=channel_table;channel_table.setHorizontalHeaderLabels(['입력 성분','보존된 원 채널'])
        channel_table.horizontalHeader().setSectionResizeMode(0,QHeaderView.ResizeMode.ResizeToContents);channel_table.horizontalHeader().setStretchLastSection(True)
        form.addWidget(channel_table)
        geometry=fields['geometry']=QWidget();geo=QFormLayout(geometry);geo.setContentsMargins(0,0,0,0);geo.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        fields['direction']=self._line(', '.join(map(str,value.get('direction',[]))),'nx, ny, nz — 고정 단위벡터')
        fields['basis']=self._line(value.get('basis',''),'예: 시험기 전역 직교축')
        points=value.get('reference_points_mm',[[],[]]);fields['pointA']=self._line(', '.join(map(str,points[0])),'X, Y, Z');fields['pointB']=self._line(', '.join(map(str,points[1])),'X, Y, Z')
        for label,key in [('고정 방향 n','direction'),('공통 기저','basis'),('기준점 A [mm]','pointA'),('기준점 B [mm]','pointB')]:geo.addRow(label,fields[key])
        fields['protocol']=QCheckBox('힘·게이지·면적 축이 일치하는 단축/동축 시험');fields['protocol'].setChecked(value.get('protocol')=='uniaxial_coaxial_declared');geo.addRow(fields['protocol']);details.addWidget(geometry)
        dimensions=fields['dimensions']=QTableWidget(3,4);dimensions.setHorizontalHeaderLabels(['실제 입력','값','원단위','공유 입력 이름'])
        dimensions.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        fields['parameter_notes']={}
        for i,name in enumerate(('L0','A0','J')):
            r=value['parameters'].get(name,{})
            item=QTableWidgetItem(name);item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable);dimensions.setItem(i,0,item)
            dimensions.setItem(i,1,QTableWidgetItem(str(r.get('value',''))));units=QComboBox()
            for unit in {'L0':['mm','m','um'],'A0':['mm^2','m^2'],'J':['1']}[name]:units.addItem(unit)
            units.setCurrentText(r.get('unit',units.itemText(0)));dimensions.setCellWidget(i,2,units);dimensions.setItem(i,3,QTableWidgetItem(r.get('identity','')))
            note=fields['parameter_notes'][name]=self._line(r.get('source',''),name+'의 실제 측정 자료 또는 명시 가정')
        dimensions.setFixedHeight(136);details.addWidget(dimensions)
        notes=fields['notes_layout']=QFormLayout();notes.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        for name,note in fields['parameter_notes'].items():notes.addRow(name+' 제공 근거',note)
        fields['J_mode']=QComboBox();fields['J_mode'].addItem('J 실측값','measured');fields['J_mode'].addItem('명시한 비압축 가정 J=1','assumed_incompressible')
        fields['J_mode'].setCurrentIndex(max(0,fields['J_mode'].findData(value['parameters'].get('J',{}).get('interpretation','measured'))));notes.addRow('J의 해석',fields['J_mode']);details.addLayout(notes);details.addStretch()
        offset=value.get('time_offset',{});fields['offset_on']=QCheckBox('이 자료에 공통 시간 offset 적용: y(t + δt)');fields['offset_on'].setChecked(bool(offset));timed.addWidget(fields['offset_on'])
        timing=QFormLayout();timing.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        for key,label,hint in [('offset','offset 값 [s]','양/음의 실제 offset'),('offset_id','offset 공유 입력 이름','같은 offset이면 같은 이름'),('offset_note','offset 제공 근거','시각 교정/동기화 자료')]:
            field=fields[key]=self._line(offset.get({'offset':'value','offset_id':'identity','offset_note':'source'}[key],''),hint);timing.addRow(label,field)
            field.setEnabled(bool(offset));fields['offset_on'].toggled.connect(field.setEnabled)
        timed.addLayout(timing)
        shared=fields['shared']=QTableWidget(0,3);shared.setHorizontalHeaderLabels(['원 채널','원값 / 계수','공유 입력 이름 (선택)']);shared.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        shared.setMaximumHeight(165);timed.addWidget(shared)
        hint=QLabel('공유 이름이 같으면 하나의 불확실 입력입니다. 값·단위가 다르면 충돌로 차단합니다. 원값/계수·치수·offset의 불확실성과 상관은 다음 분석창에서 지정합니다. 고정 방향 투영은 일반 회전/전단의 실제 거리 신장이 아닙니다.')
        hint.setWordWrap(True);hint.setProperty('appearanceRole','muted');timed.addWidget(hint);timed.addStretch();form.addStretch()
        q.currentIndexChanged.connect(lambda *_:self._refresh(side));self._refresh(side)

    def _refresh(self,side):
        f=self.pages[side];q=f['quantity'].currentData();table=f['channels'];old={}
        for i in range(table.rowCount()):old[table.item(i,0).data(Qt.ItemDataRole.UserRole)]=table.cellWidget(i,1).currentData()
        names=(['value'] if q=='value' else ['force'] if q=='nominal_stress' else ['u'+p+a for p in 'AB' for a in 'xyz']+(['force'] if q=='cauchy_stress' else []))
        table.setRowCount(len(names));table.setFixedHeight(38+len(names)*33)
        for i,name in enumerate(names):
            label={'value':'교정/처리 값','force':'힘 F'}.get(name,name[1]+'점 변위 '+name[-1].upper())
            item=QTableWidgetItem(label);item.setData(Qt.ItemDataRole.UserRole,name);item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable);table.setItem(i,0,item)
            select=QComboBox();select.addItem('원 채널 선택',None)
            for title,r in self.choices[side].items():
                select.addItem(title,r['source']);index=select.count()-1
                if r.get('unavailable'):
                    select.model().item(index).setEnabled(False);select.setItemData(index,r['unavailable'],Qt.ItemDataRole.ToolTipRole)
            selected=old.get(name,f['original']['channels'].get(name))
            for j in range(select.count()):
                if select.itemData(j)==selected:select.setCurrentIndex(j)
            select.currentIndexChanged.connect(lambda *_:self._shared(side));table.setCellWidget(i,1,select)
        f['geometry'].setVisible(q not in ('value','nominal_stress'))
        needed={'L0'} if q in ('engineering_strain','stretch','log_strain') else {'A0'} if q=='nominal_stress' else {'L0','A0','J'} if q=='cauchy_stress' else set()
        f['dimensions'].setVisible(bool(needed))
        f['sections'].setTabEnabled(1,q!='value')
        for i,name in enumerate(('L0','A0','J')):
            f['dimensions'].setRowHidden(i,name not in needed);f['parameter_notes'][name].setVisible(name in needed)
            f['notes_layout'].labelForField(f['parameter_notes'][name]).setVisible(name in needed)
        f['J_mode'].setVisible('J' in needed);f['notes_layout'].labelForField(f['J_mode']).setVisible('J' in needed);self._shared(side)

    def _shared(self,side):
        f=self.pages[side];table=f['shared'];old={}
        for i in range(table.rowCount()):old[tuple(table.item(i,0).data(Qt.ItemDataRole.UserRole))]=table.item(i,2).text()
        rows=[]
        for i in range(f['channels'].rowCount()):
            name=f['channels'].item(i,0).data(Qt.ItemDataRole.UserRole);source=f['channels'].cellWidget(i,1).currentData()
            choice=next((r for r in self.choices[side].values() if r['source']==source),None)
            if choice and not choice.get('unavailable') and choice['variables'] is None:
                try:choice['variables']=choice['_load_variables']()
                except (OSError,ValueError,KeyError,TypeError) as error:choice['unavailable']=str(error)
            for v in (choice['variables'] or []) if choice and not choice.get('unavailable') else []:rows.append((name,v))
        table.setRowCount(len(rows))
        table.setVisible(bool(rows))
        for i,(name,v) in enumerate(rows):
            item=QTableWidgetItem(name);item.setData(Qt.ItemDataRole.UserRole,(name,v['id']));item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable);table.setItem(i,0,item)
            coefficient=v.get('coefficient',v['id'])
            label=coefficient if coefficient in ('a','x0','b') else '원행 '+str(v['source_row']) if 'source_row' in v else '표본 '+str(v.get('sample_index',i)+1)
            item=QTableWidgetItem(label);item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable);table.setItem(i,1,item)
            table.setItem(i,2,QTableWidgetItem(old.get((name,v['id']),f['original'].get('shared_identities',{}).get(name,{}).get(v['id'],''))))

    def value(self):
        out=deepcopy(self.definition)
        def number(text,label):
            try:value=float(text)
            except ValueError:raise ValueError(label+'의 실제 값을 입력하세요.') from None
            if not __import__('math').isfinite(value):raise ValueError(label+'는 유한해야 합니다.')
            return value
        def vector(field):
            result=[number(x.strip(),'좌표/방향 성분') for x in field.text().split(',')]
            if len(result)!=3:raise ValueError('좌표/방향은 쉼표로 구분한 세 성분을 입력하세요.')
            return result
        for side,f in self.pages.items():
            q=f['quantity'].currentData();definition={'quantity':q,'order':f['order'].currentData(),'channels':{},'parameters':{},
                'max_gap_s':number(f['gap'].text(),'최대 정렬 간격') if f['gap'].text().strip() else None}
            for i in range(f['channels'].rowCount()):
                name=f['channels'].item(i,0).data(Qt.ItemDataRole.UserRole);selected=f['channels'].cellWidget(i,1).currentData()
                if selected is None:raise ValueError(side+' '+name+'의 실제 원 채널을 선택하세요.')
                choice=next(r for r in self.choices[side].values() if r['source']==selected)
                if choice.get('unavailable'):raise ValueError(side+' '+name+': '+choice['unavailable'])
                definition['channels'][name]=deepcopy(selected)
            if q not in ('value','nominal_stress'):
                definition.update(direction=vector(f['direction']),basis=f['basis'].text(),reference_points_mm=[vector(f['pointA']),vector(f['pointB'])])
            if q=='cauchy_stress':
                if not f['protocol'].isChecked():raise ValueError('단축/동축 시험 조건을 확인하세요.')
                definition['protocol']='uniaxial_coaxial_declared'
            needed={'L0'} if q in ('engineering_strain','stretch','log_strain') else {'A0'} if q=='nominal_stress' else {'L0','A0','J'} if q=='cauchy_stress' else set()
            for i,name in enumerate(('L0','A0','J')):
                if name not in needed:continue
                table=f['dimensions'];record={'value':number(table.item(i,1).text(),name),'unit':table.cellWidget(i,2).currentText(),
                    'identity':table.item(i,3).text().strip(),'source':f['parameter_notes'][name].text().strip()}
                if name=='J':record['interpretation']=f['J_mode'].currentData()
                definition['parameters'][name]=record
            if f['offset_on'].isChecked():definition['time_offset']={'value':number(f['offset'].text(),'공통 offset'),'unit':'s','identity':f['offset_id'].text().strip(),'source':f['offset_note'].text().strip()}
            shared={}
            for i in range(f['shared'].rowCount()):
                identity=f['shared'].item(i,2).text().strip()
                if identity:
                    name,key=f['shared'].item(i,0).data(Qt.ItemDataRole.UserRole);shared.setdefault(name,{})[key]=identity
            if shared:definition['shared_identities']=shared
            out['operands'][side]=definition
        return out

    def _accept(self):
        try:self.value()
        except ValueError as error:self.error.setText(str(error));return
        self.accept()


def install_action(window,layout):
    button=QPushButton('관측 변환…');layout.addWidget(button)
    def open_dialog():
        if window.evidence_reference is not None or window._worker is not None:return
        if window.source is None:return
        def ready(payload):
            dialog=ObservationDialog(*payload,parent=window)
            if dialog.exec()!=QDialog.DialogCode.Accepted:return
            source=dialog.value()
            from .experiment_analysis_window import show_analysis_window
            show_analysis_window(window,source=source)
        window._call(lambda:source_options(window.client,window.source),ready)
    button.clicked.connect(open_dialog)
    window._observation_button=button
    button.setVisible(window.evidence_reference is None)
    return button


def show_from_source(window,source):
    """Direct Data result/comparison entry; preserve existing close/save guard."""
    from PySide6.QtCore import QTimer
    def ready(payload):
        dialog=ObservationDialog(*payload,parent=window)
        if dialog.exec()==QDialog.DialogCode.Accepted:
            from .experiment_analysis_window import show_analysis_window
            show_analysis_window(window,source=dialog.value())
    QTimer.singleShot(0,lambda:window._call(lambda:source_options(window.client,source),ready))
