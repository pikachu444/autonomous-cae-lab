"""Native, modeless connector editor. Qt and the document editor are injected.

Selection is read-only until explicit draft storage/apply. This module owns no
FreeCAD document, solver, schema or execution service.
"""
from copy import deepcopy


_windows = []  # Qt Python lifetime only; no document authority.
MODES = ['병진 X', '병진 Y', '병진 Z', '회전 X', '회전 Y', '회전 Z']
UNIT_CHOICES = {
    'translation_k': [('N/mm', 'N/mm'), ('N/m', 'N/m')],
    'translation_c': [('N·s/mm', 'N*s/mm'), ('N·s/m', 'N*s/m')],
    'rotation_k': [('N·mm/rad', 'N*mm/rad'), ('N·m/rad', 'N*m/rad'), ('N·mm/°', 'N*mm/deg')],
    'rotation_c': [('N·mm·s/rad', 'N*mm*s/rad'), ('N·m·s/rad', 'N*m*s/rad'), ('N·mm·s/°', 'N*mm*s/deg')]}


def show(W, C, editor, *, connector_id=None):
    for window in list(_windows):
        if window.editor is editor and (connector_id is None or window.connector_id == connector_id) and window.isVisible():
            window.showNormal(); window.raise_(); window.activateWindow(); return window

    class Panel(W.QDialog):
        def __init__(self):
            super().__init__(None)
            self.editor = editor; self.connector_id = connector_id
            self._draft = {}; self._base = {}; self._loading = False; self._busy = False; self.prepared = None
            self._endpoint = 0; self._motion_endpoint = 0; self._discarding = False
            self.setWindowTitle('스프링과 댐퍼'); self.setModal(False); self.resize(510, 740)
            self.setMinimumSize(390, 600)
            font=self.font();font.setFamily('Malgun Gothic');font.setPointSize(max(9,font.pointSize()));self.setFont(font)
            root=W.QVBoxLayout(self);root.setContentsMargins(10,10,10,10);root.setSpacing(8)
            header=W.QHBoxLayout();self.records=W.QComboBox();self.records.setAccessibleName('연결 선택')
            self.records.setMinimumWidth(0);self.records.setSizeAdjustPolicy(W.QComboBox.AdjustToMinimumContentsLengthWithIcon);self.records.setMinimumContentsLength(12);header.addWidget(self.records,1)
            self.new_button=W.QPushButton('새 연결');self.new_button.setToolTip('현재 모델에 새 연결 초안을 만듭니다.')
            header.addWidget(self.new_button);root.addLayout(header)
            self.label=W.QLineEdit();self.label.setPlaceholderText('연결 이름');self.label.setAccessibleName('연결 이름');root.addWidget(self.label)
            self.tabs=W.QTabWidget();root.addWidget(self.tabs,1)
            self._targets();self._modes();self._time()
            self.notice=W.QLabel('연결을 선택하거나 새 연결을 만드세요.');self.notice.setWordWrap(True)
            self.notice.setTextInteractionFlags(C.Qt.TextSelectableByMouse);root.addWidget(self.notice)
            self.errors=W.QListWidget();self.errors.setMaximumHeight(85);self.errors.hide();root.addWidget(self.errors)
            actions=W.QHBoxLayout()
            self.save_button=W.QPushButton('초안 보관');self.save_button.setToolTip('미완성 입력도 초안으로 보관합니다. 문서 파일 저장과는 별도입니다.')
            self.apply_button=W.QPushButton('적용');self.apply_button.setToolTip('두 대상과 입력을 검증한 뒤 현재 모델에 적용합니다. 계산은 실행하지 않습니다. Ctrl+Enter')
            self.apply_button.setShortcut('Ctrl+Return')
            self.cancel_button=W.QPushButton('취소');self.cancel_button.setToolTip('보관하지 않은 이 창의 편집을 버리고 닫습니다.')
            for button in (self.save_button,self.apply_button,self.cancel_button):
                button.setAutoDefault(False);button.setDefault(False);actions.addWidget(button)
            root.addLayout(actions)
            self.freeze_button=W.QPushButton('해석 입력 준비…');self.freeze_button.setToolTip('적용 상태로 native 해석 입력을 준비합니다. 솔버 실행은 별도입니다.')
            root.addWidget(self.freeze_button)
            self.label.textEdited.connect(self._changed)
            self.records.currentIndexChanged.connect(self._choose)
            self.new_button.clicked.connect(self._new)
            self.save_button.clicked.connect(lambda:self._store(False))
            self.apply_button.clicked.connect(lambda:self._store(True))
            self.cancel_button.clicked.connect(self._cancel)
            self.freeze_button.clicked.connect(self._freeze)
            self.errors.itemActivated.connect(self._error_focus)
            self._load(editor.inspect(connector_id))

        def _page(self,title):
            page=W.QWidget();layout=W.QVBoxLayout(page);layout.setContentsMargins(8,8,8,8);layout.setSpacing(8)
            scroll=W.QScrollArea();scroll.setWidgetResizable(True);scroll.setWidget(page);scroll.setFrameShape(W.QFrame.NoFrame)
            self.tabs.addTab(scroll,title);return page,layout

        def _line(self,name):
            field=W.QLineEdit();field.setObjectName(name);field.setMinimumWidth(0);field.textEdited.connect(self._changed);return field

        def _combo(self,choices,name):
            field=W.QComboBox();field.setObjectName(name);field.setMinimumWidth(0);field.addItem('미지정',None)
            for label,value in choices:field.addItem(label,value)
            field.currentIndexChanged.connect(self._changed);return field

        def _set_combo(self,field,value):
            index=field.findData(value)
            if index<0:field.addItem('확인 필요: '+str(value),value);index=field.count()-1
            field.setCurrentIndex(index)

        def _vector(self,layout,title,names,prefix):
            layout.addWidget(W.QLabel(title));grid=W.QGridLayout();fields=[]
            for i,name in enumerate(names):
                label=W.QLabel(name);field=self._line(prefix+str(i));label.setBuddy(field)
                grid.addWidget(label,(i//3)*2,i%3);grid.addWidget(field,(i//3)*2+1,i%3);fields.append(field)
            layout.addLayout(grid);return fields

        def _targets(self):
            page,layout=self._page('대상과 부착')
            fe_row=W.QHBoxLayout();self.fe_sources=W.QComboBox();self.fe_sources.setMinimumWidth(0);self.fe_sources.setSizeAdjustPolicy(W.QComboBox.AdjustToMinimumContentsLengthWithIcon);self.fe_sources.setMinimumContentsLength(12);fe_row.addWidget(self.fe_sources,1)
            self.fe_capture=W.QPushButton('FE 원본 가져오기');fe_row.addWidget(self.fe_capture);layout.addLayout(fe_row)
            self.fe_status=W.QLabel();self.fe_status.setWordWrap(True);layout.addWidget(self.fe_status)
            self.fe_clear=W.QPushButton('독립 강체 입력으로 전환');layout.addWidget(self.fe_clear)
            self.fe_capture.clicked.connect(self._capture_fe);self.fe_clear.clicked.connect(self._clear_fe)
            row=W.QHBoxLayout();self.endpoint_choice=W.QComboBox();self.endpoint_choice.addItems(['기준점 A','기준점 B']);row.addWidget(self.endpoint_choice,1)
            self.capture_button=W.QPushButton('현재 선택 가져오기');row.addWidget(self.capture_button);layout.addLayout(row)
            tip=W.QLabel('영역과 기준 꼭짓점을 고르고, 꼭짓점은 마지막에 선택하세요.');tip.setWordWrap(True);layout.addWidget(tip)
            self.selection_label=W.QLabel('모델에서 기준점 또는 영역을 선택하세요.');self.selection_label.setWordWrap(True);layout.addWidget(self.selection_label)
            self.rigid=W.QCheckBox('이 영역을 기준점에 강체로 부착');layout.addWidget(self.rigid)
            self.manual_mass=W.QWidget();manual=W.QVBoxLayout(self.manual_mass);manual.setContentsMargins(0,0,0,0);manual.setSpacing(8);layout.addWidget(self.manual_mass)
            self.cog=W.QCheckBox('선택 기준점이 실제 질량중심임을 확인');manual.addWidget(self.cog)
            for field in (self.rigid,self.cog):field.toggled.connect(self._changed)
            form=W.QFormLayout();form.setRowWrapPolicy(W.QFormLayout.WrapLongRows)
            self.mass=self._line('mass');self.mass_unit=self._combo([('kg','kg'),('Mg','Mg')],'massUnit')
            pair=W.QWidget();box=W.QHBoxLayout(pair);box.setContentsMargins(0,0,0,0);box.addWidget(self.mass,1);box.addWidget(self.mass_unit)
            form.addRow('질량',pair);manual.addLayout(form)
            self.inertia=self._vector(manual,'질량중심의 관성 텐서',['Ixx','Iyy','Izz','Ixy','Iyz','Izx'],'inertia')
            form=W.QFormLayout();form.setRowWrapPolicy(W.QFormLayout.WrapLongRows)
            self.inertia_unit=self._combo([('kg·mm²','kg*mm^2'),('kg·m²','kg*m^2'),('Mg·mm²','Mg*mm^2')],'inertiaUnit')
            self.inertia_frame=self._combo([('전역 직교축','global_cartesian')],'inertiaFrame')
            form.addRow('관성 단위',self.inertia_unit);form.addRow('관성 성분 기저',self.inertia_frame);manual.addLayout(form)
            note=W.QLabel('영역 강체화와 질량중심은 모델링 선택입니다. 기하 중심을 물리적 질량중심으로 간주하지 않습니다.')
            note.setWordWrap(True);manual.addWidget(note);layout.addStretch()
            self.endpoint_choice.currentIndexChanged.connect(self._endpoint_changed);self.capture_button.clicked.connect(self._capture)

        def _modes(self):
            page,layout=self._page('6모드와 국부축')
            hint=W.QLabel('사용하지 않는 모드는 k와 c에 0을 명시하세요. 빈 값은 미결정입니다.');hint.setWordWrap(True);layout.addWidget(hint)
            self.coefficients=W.QTableWidget(6,3);self.coefficients.setHorizontalHeaderLabels(['국부 모드','강성 k','감쇠 c'])
            self.coefficients.verticalHeader().hide();self.coefficients.setFixedHeight(224)
            header=self.coefficients.horizontalHeader();header.setSectionResizeMode(W.QHeaderView.Stretch)
            self.k=[];self.c=[]
            for i,name in enumerate(MODES):
                item=W.QTableWidgetItem(name);item.setFlags(item.flags() & ~C.Qt.ItemIsEditable);self.coefficients.setItem(i,0,item)
                for column,fields,prefix in [(1,self.k,'k'),(2,self.c,'c')]:
                    field=self._line(prefix+str(i));field.setAccessibleName(name+(' 강성' if column==1 else ' 감쇠'));self.coefficients.setCellWidget(i,column,field);fields.append(field)
            for i in range(6):self.coefficients.setRowHeight(i,30)
            self.coefficients.setFixedHeight(sum(self.coefficients.rowHeight(i) for i in range(6))+self.coefficients.horizontalHeader().sizeHint().height()+2*self.coefficients.frameWidth()+4)
            layout.addWidget(self.coefficients)
            self.units={};form=W.QFormLayout();form.setRowWrapPolicy(W.QFormLayout.WrapLongRows)
            for prefix,label in [('translation','병진 단위'),('rotation','회전 단위')]:
                pair=W.QWidget();row=W.QHBoxLayout(pair);row.setContentsMargins(0,0,0,0);row.setSpacing(5)
                for suffix,title in [('k','k'),('c','c')]:
                    key=prefix+'_'+suffix;self.units[key]=self._combo(UNIT_CHOICES[key],key)
                    row.addWidget(W.QLabel(title));row.addWidget(self.units[key],1)
                form.addRow(label,pair)
            layout.addLayout(form)
            note=W.QLabel('국부 x는 A→B 방향이어야 합니다. x/y/z를 전역 성분으로 명시하세요. 자동 축은 만들지 않습니다.')
            note.setWordWrap(True);layout.addWidget(note)
            self.axes=W.QTableWidget(3,3);self.axes.setHorizontalHeaderLabels(['전역 X','전역 Y','전역 Z']);self.axes.setVerticalHeaderLabels(['국부 x','국부 y','국부 z'])
            self.axes.horizontalHeader().setSectionResizeMode(W.QHeaderView.Stretch);self.axes.setMaximumHeight(135)
            for i in range(3):
                for j in range(3):self.axes.setItem(i,j,W.QTableWidgetItem(''))
            self.axes.itemChanged.connect(self._changed);layout.addWidget(self.axes);layout.addStretch()

        def _time(self):
            page,layout=self._page('시간과 초기운동');form=W.QFormLayout();form.setRowWrapPolicy(W.QFormLayout.WrapLongRows)
            self.time={}
            for key,label in [('end_s','종료 시각 [s]'),('history_interval_s','결과 저장 간격 [s]'),('scale','시간 증분 계수 [1]')]:
                self.time[key]=self._line(key);form.addRow(label,self.time[key])
            self.connector_mass=self._line('connectorMass');self.connector_inertia=self._line('connectorInertia')
            self.connector_mass_unit=self._combo([('kg','kg'),('Mg','Mg')],'connectorMassUnit')
            self.connector_inertia_unit=self._combo([('kg·mm²','kg*mm^2'),('kg·m²','kg*m^2'),('Mg·mm²','Mg*mm^2')],'connectorInertiaUnit')
            for label,field,unit in [('연결요소 자체 질량',self.connector_mass,self.connector_mass_unit),('연결요소 자체 회전관성',self.connector_inertia,self.connector_inertia_unit)]:
                pair=W.QWidget();row=W.QHBoxLayout(pair);row.setContentsMargins(0,0,0,0);row.addWidget(field,1);row.addWidget(unit)
                form.addRow(label,pair)
            layout.addLayout(form)
            self.motion_source=W.QComboBox();self.motion_source.setObjectName('initialMotionSource')
            self.motion_source.addItem('원 FE 초기운동 유지','existing_fe');self.motion_source.addItem('선택 영역 초기운동 지정','endpoint_patch')
            layout.addWidget(self.motion_source);self.motion_source.currentIndexChanged.connect(self._motion_source_changed)
            self.motion_status=W.QLabel();self.motion_status.setWordWrap(True);layout.addWidget(self.motion_status)
            self.manual_motion=W.QWidget();motion=W.QVBoxLayout(self.manual_motion);motion.setContentsMargins(0,0,0,0);layout.addWidget(self.manual_motion)
            self.motion_choice=W.QComboBox();self.motion_choice.addItems(['기준점 A의 초기운동','기준점 B의 초기운동']);motion.addWidget(self.motion_choice)
            self.velocity=self._vector(motion,'전역 초기 속도 [mm/s]',['Vx','Vy','Vz'],'velocity')
            self.omega=self._vector(motion,'전역 초기 각속도 [rad/s]',['ωx','ωy','ωz'],'omega')
            motion.addWidget(W.QLabel('전역 고정 자유도'))
            grid=W.QGridLayout();self.fixed=[]
            for i,name in enumerate(['Ux','Uy','Uz','Rx','Ry','Rz']):
                field=W.QCheckBox(name);field.toggled.connect(self._changed);grid.addWidget(field,i//3,i%3);self.fixed.append(field)
            motion.addLayout(grid);self.motion_choice.currentIndexChanged.connect(self._motion_changed)
            self.clear_manual_fixed=W.QPushButton('이 연결의 수동 고정 해제');layout.addWidget(self.clear_manual_fixed)
            self.clear_manual_fixed.clicked.connect(self._clear_manual_fixed)
            self.source=self._line('source');self.source.setPlaceholderText('계수와 모델링 선택의 출처')
            layout.addWidget(W.QLabel('설정 출처'));layout.addWidget(self.source)
            note=W.QLabel('입력 준비와 실제 계산은 별도입니다. 필요한 질량·관성·구속이 없으면 해석 입력을 준비할 수 없습니다.')
            note.setWordWrap(True);layout.addWidget(note);layout.addStretch()

        def _literal(self,field,old):
            return deepcopy(old) if field.text()==str(old) else field.text()

        def _endpoint_fields(self,index):
            endpoint=self._draft['endpoints'][index]
            endpoint.update(rigid_attachment=self.rigid.isChecked(),reference_is_mass_center=self.cog.isChecked())
            mass=endpoint.setdefault('mass',{})
            mass.update(value=self._literal(self.mass,mass.get('value','')),unit=self.mass_unit.currentData())
            inertia=endpoint.setdefault('inertia',{})
            inertia.update(values=[self._literal(f,old) for f,old in zip(self.inertia,inertia.get('values',['']*6))],unit=self.inertia_unit.currentData(),frame=self.inertia_frame.currentData())

        def _motion_fields(self,index):
            endpoint=self._draft['endpoints'][index]
            endpoint.update(fixed=[f.isChecked() for f in self.fixed],velocity_mm_s=[self._literal(f,old) for f,old in zip(self.velocity,endpoint.get('velocity_mm_s',['']*3))],omega_rad_s=[self._literal(f,old) for f,old in zip(self.omega,endpoint.get('omega_rad_s',['']*3))])

        def draft(self):
            if not self._draft:return {}
            self._endpoint_fields(self._endpoint);self._motion_fields(self._motion_endpoint)
            value=deepcopy(self._draft);value['label']=self.label.text();value['k']=[self._literal(f,old) for f,old in zip(self.k,value.get('k',['']*6))];value['c']=[self._literal(f,old) for f,old in zip(self.c,value.get('c',['']*6))]
            value.setdefault('axes',{}).update({name:[self._literal(self.axes.item(i,j),value.get('axes',{}).get(name,['']*3)[j]) for j in range(3)] for i,name in enumerate('xyz')})
            value.setdefault('units',{}).update({key:field.currentData() for key,field in self.units.items()});value.setdefault('time',{}).update({key:self._literal(field,value.get('time',{}).get(key,'')) for key,field in self.time.items()});value['source']=self.source.text()
            for key,field,unit in [('connector_mass',self.connector_mass,self.connector_mass_unit),('connector_inertia',self.connector_inertia,self.connector_inertia_unit)]:
                value.setdefault(key,{})['value']=self._literal(field,value.get(key,{}).get('value',''));value[key]['unit']=unit.currentData()
            return value

        def pending_changes(self):return bool(self._draft) and self.draft()!=self._base

        def _changed(self,*args):
            if self._loading:return
            self.freeze_button.setEnabled(False);self.prepared=None
            self.notice.setText('보관하지 않은 편집이 있습니다. 초안 보관 또는 적용을 선택하세요.')

        def _read_endpoint(self,index):
            endpoint=self._draft['endpoints'][index];selection=endpoint.get('selection')
            if selection:
                point=selection.get('reference_mm',[])
                self.selection_label.setText(str(selection.get('label') or '선택한 대상')+'\n기준점 ('+', '.join(str(v) for v in point)+') mm')
            else:self.selection_label.setText('모델에서 기준점 또는 영역을 선택한 뒤 가져오세요.')
            self.rigid.setChecked(bool(endpoint.get('rigid_attachment')));self.cog.setChecked(bool(endpoint.get('reference_is_mass_center')))
            self.mass.setText(str(endpoint.get('mass',{}).get('value','')));self._set_combo(self.mass_unit,endpoint.get('mass',{}).get('unit'))
            inertia=endpoint.get('inertia',{})
            for field,value in zip(self.inertia,inertia.get('values',['']*6)):field.setText(str(value))
            self._set_combo(self.inertia_unit,inertia.get('unit'));self._set_combo(self.inertia_frame,inertia.get('frame'))

        def _read_motion(self,index):
            endpoint=self._draft['endpoints'][index]
            for key,fields in [('velocity_mm_s',self.velocity),('omega_rad_s',self.omega)]:
                for field,value in zip(fields,endpoint.get(key,['']*3)):field.setText(str(value))
            for field,value in zip(self.fixed,endpoint.get('fixed',[False]*6)):field.setChecked(bool(value))

        def _endpoint_changed(self,index):
            if self._loading or not self._draft:return
            self._endpoint_fields(self._endpoint);self._endpoint=index;self._loading=True
            try:self._read_endpoint(index)
            finally:self._loading=False

        def _motion_changed(self,index):
            if self._loading or not self._draft:return
            self._motion_fields(self._motion_endpoint);self._motion_endpoint=index;self._loading=True
            try:self._read_motion(index)
            finally:self._loading=False

        def _load(self,value):
            self.prepared=None;self._loading=True
            try:
                self.records.clear()
                for record in value.get('records',[]):self.records.addItem(record['label'],record['id'])
                record=value.get('record')
                self.connector_id=record['id'] if record else None
                self._draft=deepcopy(record['draft']) if record else {};self._base=deepcopy(self._draft)
                self.records.setCurrentIndex(self.records.findData(self.connector_id))
                self.tabs.setEnabled(bool(record));self.label.setEnabled(bool(record))
                if record:
                    self.label.setText(str(self._draft.get('label','')));self._read_endpoint(self._endpoint);self._read_motion(self._motion_endpoint)
                    for key,fields in [('k',self.k),('c',self.c)]:
                        for field,number in zip(fields,self._draft.get(key,['']*6)):field.setText(str(number))
                    for key,field in self.units.items():self._set_combo(field,self._draft.get('units',{}).get(key))
                    for i,name in enumerate('xyz'):
                        for j,number in enumerate(self._draft.get('axes',{}).get(name,['']*3)):self.axes.item(i,j).setText(str(number))
                    for key,field in self.time.items():field.setText(str(self._draft.get('time',{}).get(key,'')))
                    self.source.setText(str(self._draft.get('source','')))
                    self.connector_mass.setText(str(self._draft.get('connector_mass',{}).get('value','')))
                    self.connector_inertia.setText(str(self._draft.get('connector_inertia',{}).get('value','')))
                    self._set_combo(self.connector_mass_unit,self._draft.get('connector_mass',{}).get('unit'))
                    self._set_combo(self.connector_inertia_unit,self._draft.get('connector_inertia',{}).get('unit'))
                else:self.label.clear()
                self._discover_fe();self._fe_mode()
                self._show_errors(value.get('errors',[]))
                self.save_button.setEnabled(bool(record));self.apply_button.setEnabled(bool(record))
                self.freeze_button.setEnabled(bool(value.get('can_freeze')) and bool(record))
            finally:self._loading=False

        def _show_errors(self,issues):
            self.errors.clear()
            for issue in issues:
                item=W.QListWidgetItem(str(issue['message']));item.setData(C.Qt.UserRole,deepcopy(issue.get('path')));self.errors.addItem(item)
            self.errors.setVisible(bool(issues))
            self.notice.setText('수정할 입력 '+str(len(issues))+'개. 초안은 보관할 수 있습니다.' if issues else '현재 입력을 확인한 뒤 적용하세요.')

        def _error_focus(self,item):
            raw=item.data(C.Qt.UserRole)
            path='.'.join(str(v) for v in raw) if isinstance(raw,(list,tuple)) else str(raw).replace('/','.').replace('[','.').replace(']','')
            if 'endpoints' in path:
                if 'velocity' in path or 'omega' in path or 'fixed' in path:self.tabs.setCurrentIndex(2)
                else:self.tabs.setCurrentIndex(0)
                if '.1.' in path:self.endpoint_choice.setCurrentIndex(1);self.motion_choice.setCurrentIndex(1)
                elif '.0.' in path:self.endpoint_choice.setCurrentIndex(0);self.motion_choice.setCurrentIndex(0)
            elif path.startswith('fe'):self.tabs.setCurrentIndex(0)
            elif path.split('.')[0] in ('axes','units','k','c'):self.tabs.setCurrentIndex(1)
            elif 'time' in path or path.startswith('connector_'):self.tabs.setCurrentIndex(2)

        def _capture(self):
            if not self.connector_id:return
            try:
                self._draft=self.draft()
                value=editor.capture(self.connector_id,self._endpoint)
                self._draft['endpoints'][self._endpoint]['selection']=deepcopy(value['selection'])
                self._loading=True
                try:self._read_endpoint(self._endpoint)
                finally:self._loading=False
                self._changed();self.notice.setText('기준점 '+('A' if self._endpoint==0 else 'B')+'를 가져왔습니다. '+('FE 원본도 다시 가져와 부착 영역을 확인하세요.' if isinstance(self._draft.get('fe'),dict) else '아직 모델에 적용하지 않았습니다.'))
            except Exception as error:self.notice.setText(str(error))

        def _discover_fe(self):
            self.fe_sources.clear();self.fe_sources.addItem('기존 FE 해석 선택',None)
            self._fe_records=[]
            try:
                if callable(getattr(editor,'discover_fe',None)):self._fe_records=editor.discover_fe()
                for row in self._fe_records:
                    label=row['label']+(' / '+row['solver_label'] if row.get('solver_label') else '')
                    self.fe_sources.addItem(label,deepcopy(row))
                    fe=self._draft.get('fe')
                    if isinstance(fe,dict) and (row['analysis_id'],row['solver_id'])==(fe.get('analysis_id'),fe.get('solver_id')):
                        self.fe_sources.setCurrentIndex(self.fe_sources.count()-1)
            except Exception as error:self.fe_status.setText(str(error))

        def _fe_mode(self):
            fe=self._draft.get('fe');bound=isinstance(fe,dict)
            self.manual_mass.setVisible(not bound);self.fe_clear.setVisible(bound)
            if bound:
                row=next((r for r in self._fe_records if (r['analysis_id'],r['solver_id'])==(fe.get('analysis_id'),fe.get('solver_id'))),None)
                self.fe_status.setText((row['label'] if row else '연결된 기존 FE 해석')+' — 질량·관성은 원 FE 모델에서 사용합니다. 별도로 더하지 않습니다.')
            else:self.fe_status.setText('FE 원본을 연결하거나 아래에서 독립 강체의 질량·관성을 입력하세요.')
            mode=fe.get('initial_motion_source','existing_fe') if bound else None
            self.motion_source.setVisible(bound)
            if bound:self._set_combo(self.motion_source,mode)
            nonzero=False;has_fixed=False
            for endpoint in self._draft.get('endpoints',[]):
                if any(endpoint.get('fixed',[])):nonzero=True;has_fixed=True
                for value in endpoint.get('velocity_mm_s',[])+endpoint.get('omega_rad_s',[]):
                    try:nonzero |= float(value)!=0
                    except (ValueError,TypeError):nonzero=True
            self.manual_motion.setVisible(not bound or mode=='endpoint_patch' or nonzero)
            for field in self.fixed:field.setEnabled(not bound)
            self.clear_manual_fixed.setVisible(bound and has_fixed)
            self.motion_status.setText(('선택 영역의 초기 속도·각속도를 명시합니다. 기존 FE의 비0 초기운동과 충돌하면 적용할 수 없습니다.' if mode=='endpoint_patch' else
                '원 FE 모델의 초기운동을 유지합니다.'+(' 이전 수동 운동값은 0으로 수정하거나 위에서 영역 초기운동 지정을 선택하세요.' if nonzero else ''))+
                ' FE 구속은 원 모델에서 사용합니다.' if bound else '')

        def _motion_source_changed(self,*args):
            if self._loading or not isinstance(self._draft.get('fe'),dict):return
            self._draft=self.draft();self._draft['fe']['initial_motion_source']=self.motion_source.currentData()
            self._fe_mode();self._changed()

        def _clear_manual_fixed(self):
            if not isinstance(self._draft.get('fe'),dict):return
            self._draft=self.draft()
            for endpoint in self._draft['endpoints']:endpoint['fixed']=[False]*6
            self._loading=True
            try:self._read_motion(self._motion_endpoint);self._fe_mode()
            finally:self._loading=False
            self._changed();self.notice.setText('이 연결의 수동 고정만 해제했습니다. 원 FE 모델의 구속은 보존됩니다.')

        def _capture_fe(self):
            if not self.connector_id:return
            row=self.fe_sources.currentData()
            if row is None:
                self.notice.setText('기존 FE 해석과 솔버 설정을 먼저 선택하세요. 없으면 원 해석 설정을 만든 뒤 이 창을 다시 여세요.');return
            try:
                current=self.draft()
                if any(not e.get('selection') for e in current['endpoints']):
                    raise ValueError('대상 A와 B를 실제 모델에서 먼저 가져오세요.')
                value=editor.capture_fe(self.connector_id,current,row['analysis_id'],row['solver_id'])
                self._draft=deepcopy(value['draft']);self._loading=True
                try:self._read_endpoint(self._endpoint);self._read_motion(self._motion_endpoint);self._fe_mode()
                finally:self._loading=False
                self._changed();self.notice.setText('현재 FE 원본을 가져왔습니다. 부착 영역을 확인하고 적용하세요. 계산은 실행하지 않았습니다.')
            except Exception as error:self.notice.setText(str(error))

        def _clear_fe(self):
            self._draft=self.draft();self._draft['fe']=None;self._fe_mode();self._changed()
            self.notice.setText('독립 강체 입력으로 전환했습니다. 실제 질량·관성·질량중심을 확인한 뒤 적용하세요.')

        def _store(self,apply):
            if self._busy or not self.connector_id:return False
            draft=self.draft();self._busy=True;self.setEnabled(False)
            try:
                value=editor.apply(self.connector_id,draft) if apply else editor.save_draft(self.connector_id,draft)
                self._load(value)
                if not value.get('errors'):self.notice.setText('모델에 적용했습니다. 계산은 실행하지 않았습니다.' if apply else '초안을 보관했습니다. 모델 적용과 문서 저장은 별도입니다.')
                return True
            except Exception as error:
                if callable(getattr(error,'record',None)):
                    self._show_errors([error.record()]);self._error_focus(self.errors.item(0))
                else:self.notice.setText(str(error))
                return False
            finally:self._busy=False;self.setEnabled(True)

        def pending_snapshot(self):
            if self._busy:raise ValueError('연결요소 작업의 응답을 확인한 뒤 저장하세요.')
            return {'connector_id':self.connector_id,'draft':deepcopy(self.draft())} if self.pending_changes() else None

        def accept_saved_snapshot(self,snapshot,value):
            if snapshot['connector_id']!=self.connector_id:return
            if self.draft()==snapshot['draft'] and 'record' in value:self._load(value)
            else:self._base=deepcopy(snapshot['draft'])

        def keyPressEvent(self,event):
            if event.key()==C.Qt.Key_S and event.modifiers() & C.Qt.ControlModifier:
                try:
                    save=getattr(editor,'save_document',None)
                    if save is None:raise ValueError('프로젝트 창에서 문서를 저장하세요.')
                    save()
                except Exception as error:self.notice.setText(str(error))
                event.accept();return
            super().keyPressEvent(event)

        def _freeze(self):
            if self._busy or self.pending_changes():
                self.notice.setText('편집을 먼저 적용한 뒤 해석 입력을 준비하세요.');return
            try:
                self._busy=True;self.setEnabled(False);self.prepared=editor.freeze(self.connector_id)
                self.notice.setText('해석 입력을 준비했습니다. 계산은 실행하지 않았습니다.')
            except Exception as error:self.notice.setText(str(error))
            finally:self._busy=False;self.setEnabled(True)

        def _leave(self):
            if not self.pending_changes():return True
            box=W.QMessageBox(self);box.setWindowTitle('연결 편집');box.setText('보관하지 않은 편집이 있습니다.')
            save=box.addButton('초안 보관',W.QMessageBox.AcceptRole);discard=box.addButton('편집 버리기',W.QMessageBox.DestructiveRole)
            cancel=box.addButton('계속 편집',W.QMessageBox.RejectRole);box.setDefaultButton(cancel);box.exec()
            return self._store(False) if box.clickedButton() is save else box.clickedButton() is discard

        def _choose(self,index):
            if self._loading or index<0:return
            selected=self.records.itemData(index)
            if selected==self.connector_id:return
            if not self._leave():
                self._loading=True;self.records.setCurrentIndex(self.records.findData(self.connector_id));self._loading=False;return
            try:self._load(editor.inspect(selected))
            except Exception as error:self.notice.setText(str(error))

        def _new(self):
            if not self._leave():return
            try:self._load(editor.create('새 연결'))
            except Exception as error:self.notice.setText(str(error))

        def _cancel(self):self._discarding=True;self.close()
        def reject(self):self.close()
        def closeEvent(self,event):
            if self._busy or (not self._discarding and not self._leave()):event.ignore();return
            if self in _windows:_windows.remove(self)
            event.accept()

    panel=Panel();_windows.append(panel);panel.show();return panel
