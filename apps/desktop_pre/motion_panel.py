"""Injected native Qt controls; every edit uses the owner's typed command queue.

No PySide6/FreeCAD import and no native object writes occur in this module.
"""
from copy import deepcopy
import json

from apps.desktop_pre.motion import JOINT_TYPES

JOINT_LABELS = {'Grounded': '고정 부품', 'Fixed': '고정 연결', 'Revolute': '회전',
    'Cylindrical': '원통 (회전·이동)', 'Slider': '직선 이동', 'Ball': '구면',
    'Distance': '거리', 'Parallel': '평행', 'Perpendicular': '수직', 'Angle': '각도'}
DRIVE_TYPES = {'Revolute': ('Angular',), 'Slider': ('Linear',), 'Cylindrical': ('Angular', 'Linear')}


def make_panel(QtCore, QtWidgets, submit, *, read=None, open_data=None):
    """Return QWidget with refresh(descriptor); submit(op,args,target,on_done).

    read, when supplied, reads the active owner's small descriptor on the GUI
    thread. Command completion is asynchronous. The parent owns HTTP retries.
    """
    controller = MotionPanel(QtCore, QtWidgets, submit, read=read, open_data=open_data)
    controller.widget.motion_controller = controller
    controller.widget.refresh = controller.refresh
    return controller.widget


class MotionPanel:
    def __init__(self, QtCore, QtWidgets, submit, *, read=None, open_data=None):
        self.Q, self.QtCore, self.submit, self.read = QtWidgets, QtCore, submit, read
        self.widget = QtWidgets.QWidget()
        self._document = None; self._session = None; self._serial = 0; self._busy = False; self._loading = False
        self._edited = False; self._definition_stamp = None; self._data = {}; self._motion = {}
        self._edit_version = 0; self._joint_edited = False; self._joint_version = 0
        self._saved_view = {}; self._view_loaded = False
        self._active_assembly = None
        self._selected_joint = None
        self._pending_joint_id = None
        self._editor_loaded = False
        self._select_saved_assembly = True
        self._initial_editor = None
        self._path_read_scope = None
        self._buttons = []
        layout = QtWidgets.QVBoxLayout(self.widget)
        row = QtWidgets.QHBoxLayout(); self.assembly = QtWidgets.QComboBox()
        row.addWidget(QtWidgets.QLabel('조립')); row.addWidget(self.assembly, 1)
        self._button(row, '다시 읽기', lambda: self._send('pre.motion.inspect', {}, inspect=True))
        layout.addLayout(row)
        self.status = QtWidgets.QLabel('문서를 열고 조립을 선택하세요.')
        self.status.setWordWrap(True); layout.addWidget(self.status)
        tabs = QtWidgets.QTabWidget(); layout.addWidget(tabs)
        assembly_tab, assembly_layout = self._tab(tabs, '부품과 관절')
        setup_toggle = QtWidgets.QToolButton(); setup_toggle.setText('조립 만들기 / 부품 배치')
        setup_toggle.setCheckable(True); assembly_layout.addWidget(setup_toggle)
        setup_box = QtWidgets.QWidget(); setup_layout = QtWidgets.QVBoxLayout(setup_box)
        setup_layout.setContentsMargins(0, 0, 0, 0); assembly_layout.addWidget(setup_box)
        setup_box.hide(); setup_toggle.toggled.connect(setup_box.setVisible)
        form = QtWidgets.QFormLayout()
        self.assembly_label = QtWidgets.QLineEdit(); self.assembly_label.setPlaceholderText('새 조립 이름')
        form.addRow('조립 이름', self.assembly_label)
        self.source = QtWidgets.QComboBox(); self.occurrence_label = QtWidgets.QLineEdit()
        self.occurrence_label.setPlaceholderText('배치 부품 이름')
        form.addRow('추가할 부품 또는 조립', self.source); form.addRow('배치 부품 이름', self.occurrence_label)
        self.rigid = QtWidgets.QCheckBox('하위 조립을 강체로 배치')
        self.rigid.setChecked(True); form.addRow('', self.rigid)
        setup_layout.addLayout(form)
        buttons = QtWidgets.QHBoxLayout()
        self._button(buttons, '새 조립 만들기', lambda: self._send('pre.assembly.create', {'label': self.assembly_label.text()}, target={}))
        self._button(buttons, '부품 배치', self._link)
        setup_layout.addLayout(buttons)
        form = QtWidgets.QFormLayout(); self.joint = QtWidgets.QComboBox(); self.joint_type = QtWidgets.QComboBox()
        for kind in ['Grounded', *JOINT_TYPES]: self.joint_type.addItem(JOINT_LABELS[kind], kind)
        self.connector_a, self.connector_b = QtWidgets.QComboBox(), QtWidgets.QComboBox()
        self.subelement_a, self.subelement_b = QtWidgets.QLineEdit(), QtWidgets.QLineEdit()
        for field in (self.subelement_a, self.subelement_b): field.setPlaceholderText('예: Face1, Edge1, Vertex1 / 빈칸: 부품 원점')
        form.addRow('편집할 관절', self.joint); form.addRow('관절 종류', self.joint_type)
        form.addRow('부품 A / 고정 부품', self.connector_a); form.addRow('연결 A의 면·모서리·점', self.subelement_a)
        form.addRow('부품 B', self.connector_b); form.addRow('연결 B의 면·모서리·점', self.subelement_b)
        self.joint_parameters = {}
        for name, unit in [('Distance', 'mm'), ('Distance2', 'mm'), ('Angle', 'deg')]:
            field = QtWidgets.QLineEdit(); field.setPlaceholderText('값을 입력하세요')
            self.joint_parameters[name] = (field, unit); form.addRow({'Distance': '거리', 'Distance2': '보조 거리', 'Angle': '각도'}[name] + ' [' + unit + ']', field)
        assembly_layout.addLayout(form)
        buttons = QtWidgets.QHBoxLayout()
        self._button(buttons, '화면 선택을 연결 A로', lambda: self._use_selection(self.connector_a, self.subelement_a))
        self._button(buttons, '화면 선택을 연결 B로', lambda: self._use_selection(self.connector_b, self.subelement_b))
        assembly_layout.addLayout(buttons)
        self.joint_notice = QtWidgets.QLabel(); self.joint_notice.setWordWrap(True)
        assembly_layout.addWidget(self.joint_notice)
        buttons = QtWidgets.QHBoxLayout()
        self._button(buttons, '관절 추가', lambda: self._edit_joint('pre.joint.create'))
        self._button(buttons, '관절 적용', lambda: self._edit_joint('pre.joint.update'))
        self._button(buttons, '관절 삭제', lambda: self._send('pre.joint.remove', {}, target=self._target(joint=True)))
        self._button(buttons, '관절 편집 취소', self._cancel_joint)
        assembly_layout.addLayout(buttons)
        assembly_layout.addStretch(1)
        _, definition_layout = self._tab(tabs, '시간과 구동')
        form = QtWidgets.QFormLayout(); self.time = {}
        for key in ('start', 'end', 'step'):
            self.time[key] = QtWidgets.QLineEdit(); form.addRow({'start': '시작', 'end': '끝', 'step': '출력 간격'}[key] + ' [s]', self.time[key])
            self.time[key].textEdited.connect(self._mark_edited)
        self.fps = QtWidgets.QSpinBox(); self.fps.setRange(1, 120); self.fps.setValue(30)
        self.tolerance = QtWidgets.QLineEdit(); self.tolerance.setPlaceholderText('예: 1e-6')
        form.addRow('재생 속도 [프레임/s]', self.fps); form.addRow('계산 오차 허용값', self.tolerance)
        self.fps.valueChanged.connect(self._mark_edited); self.tolerance.textEdited.connect(self._mark_edited)
        definition_layout.addLayout(form)
        self.drives = QtWidgets.QTableWidget(0, 4); self.drives.setHorizontalHeaderLabels(['구동 관절', '운동 종류', '시간곡선 (time = 초)', '단위'])
        self.drives.cellChanged.connect(self._mark_edited); definition_layout.addWidget(self.drives)
        buttons = QtWidgets.QHBoxLayout()
        self._button(buttons, '구동 추가', lambda: self._drive_row({}))
        self._button(buttons, '구동 삭제', lambda: self._remove_row(self.drives))
        self._button(buttons, '구동 적용', self._configure)
        self._button(buttons, '구동 편집 취소', self._cancel_definition)
        definition_layout.addLayout(buttons)
        self.traces = QtWidgets.QTableWidget(0, 7)
        self.traces.setHorizontalHeaderLabels(['경로 이름', '부품', '로컬 x', '로컬 y', '로컬 z', '단위', '출력 좌표'])
        self.traces.cellChanged.connect(self._mark_edited); definition_layout.addWidget(self.traces)
        buttons = QtWidgets.QHBoxLayout()
        self._button(buttons, '경로점 추가', lambda: self._trace_row({}))
        self._button(buttons, '경로점 삭제', lambda: self._remove_row(self.traces))
        definition_layout.addLayout(buttons)
        self.definition_notice = QtWidgets.QLabel(); self.definition_notice.setWordWrap(True)
        definition_layout.addWidget(self.definition_notice)
        _, frames_layout = self._tab(tabs, '운동 미리보기')
        frames_layout.addWidget(QtWidgets.QLabel('운동학 미리보기입니다. 운동 계산은 시작 후 중단할 수 없습니다.\n'
            '시간은 지정한 출력 격자이며 FreeCAD의 실제 프레임 시각은 제공되지 않습니다.\n'
            '정지·취소·저장 시 설계 자세를 복원합니다.'))
        buttons = QtWidgets.QHBoxLayout()
        self._button(buttons, '운동 계산', lambda: self._send('pre.motion.calculate', {}))
        self.frame = QtWidgets.QSpinBox(); self.frame.setRange(0, 0); buttons.addWidget(self.frame)
        self._button(buttons, '자세 보기', lambda: self._send('pre.motion.frame', self._frame_args()))
        self._button(buttons, '현재 자세를 설계에 적용', lambda: self._send('pre.motion.adopt_pose', self._frame_args()))
        frames_layout.addLayout(buttons)
        buttons = QtWidgets.QHBoxLayout()
        for label, operation, extra in [('재생', 'play', {'direction': 1}), ('역재생', 'play', {'direction': -1}),
                                         ('일시정지', 'pause', None), ('정지 및 자세 복원', 'stop', None), ('미리보기 취소', 'cancel', None)]:
            self._button(buttons, label, lambda op=operation, value=extra: self._send('pre.motion.' + op,
                {'calculation_id': self._calculation_id(), **value} if value is not None else {}))
        frames_layout.addLayout(buttons)
        _, path_layout = self._tab(tabs, '점 경로')
        row = QtWidgets.QHBoxLayout(); self.trace_select = QtWidgets.QComboBox()
        self.path_start, self.path_count = QtWidgets.QSpinBox(), QtWidgets.QSpinBox()
        self.path_start.setRange(0, 2000); self.path_count.setRange(1, 200); self.path_count.setValue(100)
        row.addWidget(QtWidgets.QLabel('경로점')); row.addWidget(self.trace_select, 1)
        self._button(row, '전체 경로 읽기', lambda: self._read_path(all_frames=True)); path_layout.addLayout(row)
        row = QtWidgets.QHBoxLayout(); row.addWidget(QtWidgets.QLabel('시작 프레임')); row.addWidget(self.path_start)
        row.addWidget(QtWidgets.QLabel('읽을 개수')); row.addWidget(self.path_count)
        self._button(row, '구간 읽기', self._read_path)
        stop = QtWidgets.QPushButton('읽기 중지'); stop.clicked.connect(lambda: setattr(self, '_path_read_scope', None)); row.addWidget(stop)
        path_layout.addLayout(row)
        from .motion_path import PathBrowser
        self.path_browser = PathBrowser(QtCore, QtWidgets, path_layout,
            lambda calculation, frame: self._send('pre.motion.frame', {'calculation_id': calculation, 'frame': frame}), open_data)
        self.path = self.path_browser.table
        self.assembly.currentIndexChanged.connect(self._assembly_changed)
        self.joint.currentIndexChanged.connect(self._joint_selected)
        for field in (self.subelement_a, self.subelement_b, *[f for f, u in self.joint_parameters.values()]):
            field.textEdited.connect(self._mark_joint_edited)
        for combo in (self.connector_a, self.connector_b, self.joint_type):
            combo.currentIndexChanged.connect(self._mark_joint_edited)
        self.joint_type.currentIndexChanged.connect(self._joint_controls)
        for table in (self.drives, self.traces, self.path):
            table.horizontalHeader().setStretchLastSection(True)
            table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
            table.setAlternatingRowColors(True)
            table.setMinimumHeight(130)
        self.drives.setColumnWidth(0, 210); self.drives.setColumnWidth(1, 100); self.drives.setColumnWidth(2, 300)
        self.traces.setColumnWidth(0, 140); self.traces.setColumnWidth(1, 175)
        self.widget.setObjectName('CAELabMotionPanel')
        font = self.widget.font(); font.setFamily('Malgun Gothic'); font.setPointSize(max(9, font.pointSize())); self.widget.setFont(font)
        self.widget.setStyleSheet('''
            QWidget#CAELabMotionPanel { background: #f5f6f8; }
            QTableWidget { background: white; alternate-background-color: #f5f7fa; gridline-color: #dce1e6; }
            QHeaderView::section { padding: 5px; background: #edf0f4; border: 1px solid #dce1e6; }
            QLineEdit:focus, QComboBox:focus, QSpinBox:focus { border: 1px solid #286dad; }
            QPushButton { padding: 5px 9px; }
        ''')

    def _tab(self, tabs, label):
        widget = self.Q.QWidget(); layout = self.Q.QVBoxLayout(widget)
        scroll = self.Q.QScrollArea(); scroll.setWidgetResizable(True); scroll.setWidget(widget)
        scroll.setFrameShape(self.Q.QFrame.NoFrame); tabs.addTab(scroll, label)
        return widget, layout

    def _button(self, layout, label, callback):
        button = self.Q.QPushButton(label)
        button.clicked.connect(lambda checked=False: callback()); layout.addWidget(button); self._buttons.append(button)
        return button

    def _mark_edited(self, *args):
        if not self._loading:
            self._edited = True; self._edit_version += 1
            if hasattr(self, 'definition_notice'): self._validate_drives()

    def _mark_joint_edited(self, *args):
        if not self._loading: self._joint_edited = True; self._joint_version += 1

    def _link(self):
        args = {'source_id': self.source.currentData(), 'label': self.occurrence_label.text()}
        source = next((r for r in self._data.get('objects', []) if r['id'] == args['source_id']), {})
        if source.get('type') == 'Assembly::AssemblyObject': args['rigid'] = self.rigid.isChecked()
        self._send('pre.assembly.link', args)

    def _use_selection(self, combo, field):
        data = self.read() if self.read is not None else self._data
        selection = data.get('selection') or []
        motion = data.get('motion', {})
        connectors = motion.get('selection_connectors') if motion.get('inspection_assembly_id') == self.assembly.currentData() else None
        if connectors is not None and len(connectors) == 1:
            connector = connectors[0]; index = combo.findData(connector['object_id'])
            if index >= 0:
                combo.setCurrentIndex(index); field.setText(connector['subelement']); self._mark_joint_edited(); return
        if len(selection) != 1:
            self.joint_notice.setText('트리 또는 3D 화면에서 부품의 면·모서리·점 하나를 선택하세요.'); return
        name, elements = selection[0]
        index = combo.findData(name)
        if index < 0 and len(elements) == 1:
            path = [name, *elements[0].split('.')]
            if self.assembly.currentData() in path:
                start = path.index(self.assembly.currentData())+1
                for position in range(start, len(path)):
                    part = next((p for p in self._motion.get('occurrences', []) if p['id'] == path[position]), {})
                    if part and not (part['type'] == 'Assembly::AssemblyLink' and not part.get('rigid')):
                        index = combo.findData(part['id']); elements = ['.'.join(path[position+1:])]; break
        if index < 0 or len(elements) > 1:
            self.joint_notice.setText('선택한 조립 안의 부품과 연결 요소 하나를 선택하세요.'); return
        combo.setCurrentIndex(index); field.setText(elements[0] if elements else '')
        self._mark_joint_edited()

    def _cancel_joint(self):
        before = self.current_editor()
        self._joint_edited = False; self._joint_selected(0)
        self._persist_cancel('joint_draft', before)

    def _cancel_definition(self):
        before = self.current_editor()
        self._edited = False; self._definition_stamp = None
        self.refresh(self.read() if self.read is not None else self._data)
        self._inspect_value(self._motion)
        for table, key in ((self.drives, 'drive_row'), (self.traces, 'trace_row')):
            row = self._saved_view.get(key, -1)
            if 0 <= row < table.rowCount(): table.selectRow(row)
        self._validate_drives()
        self._persist_cancel('definition_draft', before)

    def _persist_cancel(self, field, before):
        stored = self._motion.get('editors', {}).get(self.assembly.currentData())
        if stored and stored.get(field) is not None:
            editor = deepcopy(stored); editor[field] = None
            cancelled = self.current_editor()
            version_name = '_joint_version' if field == 'joint_draft' else '_edit_version'
            version = getattr(self, version_name)
            def failed():
                current = self.current_editor()
                if getattr(self, version_name) == version and current[field] == cancelled[field]:
                    current[field] = deepcopy(before[field])
                    self._restore_editor(current)
            self._send('pre.motion.save_editor', {'editor': editor}, on_failure=failed)

    def _target(self, *, joint=False):
        target = {'assembly_id': self.assembly.currentData()}
        if joint: target['joint_id'] = self.joint.currentData()
        return target

    def _calculation_id(self):
        calculation = self._motion.get('calculation') or {}
        return calculation.get('id') if calculation.get('assembly_id') == self.assembly.currentData() else None

    def _frame_args(self):
        return {'calculation_id': self._calculation_id(), 'frame': self.frame.value()}

    def _send(self, operation, args, *, target=None, inspect=False, on_failure=None, on_done=None):
        if self._busy: return
        editor = self._motion.get('editors', {}).get(self.assembly.currentData(), {})
        if (self._edited or self._joint_edited or editor.get('joint_draft') is not None or editor.get('definition_draft') is not None) and operation in ('pre.assembly.create', 'pre.motion.calculate', 'pre.motion.frame', 'pre.motion.play', 'pre.motion.adopt_pose', 'pre.motion.path'):
            self.status.setText('관절과 구동 편집을 적용하거나 취소한 뒤 새 조립을 만드세요.' if operation == 'pre.assembly.create' else '관절과 구동 편집을 적용하거나 취소한 뒤 운동을 확인하세요.'); return
        target = self._target() if target is None else target
        edit_version, joint_version = self._edit_version, self._joint_version
        self._serial += 1; serial = self._serial; scope = (self._document, self._session, self.assembly.currentData())
        self._busy = True
        for button in self._buttons: button.setEnabled(False)
        self.status.setText('운동 계산 중입니다. 계산은 중단할 수 없습니다.' if operation.endswith('calculate') else '선택한 작업을 처리 중입니다.')
        def done(reply):
            if serial != self._serial: return
            self._busy = False
            for button in self._buttons: button.setEnabled(True)
            if scope != (self._document, self._session, self.assembly.currentData()): return
            reply = reply or {}
            if reply.get('status') == 'FAILED' or reply.get('error'):
                if on_failure is not None: on_failure()
                error = reply.get('error', {}); self.status.setText(error.get('message', str(error)) if isinstance(error, dict) else str(error)); return
            value = reply.get('result', reply)
            if operation == 'pre.motion.save_editor' and 'editor' in value:
                self.accept_saved_editor({'assembly_id': target['assembly_id'], 'editor': value['editor']})
            if operation == 'pre.joint.create' and joint_version == self._joint_version: self._pending_joint_id = value.get('joint_id')
            if 'frame_count' in value and 'id' in value:
                self._motion['calculation'] = deepcopy(value); self._motion.update(state='CALCULATED', preview=False, frame=None)
            if 'calculation' in value: self._motion.update(deepcopy(value))
            if 'calculation_id' in value and 'preview' in value: self._motion.update(preview=value['preview'], frame=value.get('frame'), state='PAUSED')
            if 'rows' in value and 'trace_id' in value: self._show_path(value)
            if operation.endswith('configure') and edit_version == self._edit_version: self._edited = False
            if operation in ('pre.joint.create', 'pre.joint.update') and joint_version == self._joint_version: self._joint_edited = False
            if self.read is not None:
                self.refresh(self.read())
                if operation == 'pre.assembly.create' and value.get('assembly_id') and (edit_version, joint_version) == (self._edit_version, self._joint_version):
                    self.assembly.blockSignals(True); self.assembly.setCurrentIndex(self.assembly.findData(value['assembly_id'])); self.assembly.blockSignals(False)
                    self._view_loaded = True; self._definition_stamp = None; self.refresh(self.read())
            if inspect:
                self._inspect_value(value)
            self._show_runtime()
            if on_done is not None: on_done(value)
            if operation in ('pre.joint.create', 'pre.joint.update', 'pre.joint.remove', 'pre.assembly.link', 'pre.assembly.create'):
                self._send('pre.motion.inspect', {}, inspect=True)
        try:
            reply = self.submit(operation, args, target, done)
            if not isinstance(reply, dict) or not reply.get('queued'): done(reply)
        except Exception as error:
            done({'status': 'FAILED', 'error': {'message': str(error)}})

    def _fill_combo(self, combo, rows, selected=None, *, preserve_missing=False):
        keep_empty = preserve_missing and selected is None and combo.count() > 0 and combo.currentIndex() < 0
        old = combo.currentData() if selected is None else selected
        combo.blockSignals(True); combo.clear()
        for row in rows:
            combo.addItem(row.get('label', row['id']), row['id'])
            combo.setItemData(combo.count()-1, row['id'], self.QtCore.Qt.ToolTipRole)
        index = combo.findData(old)
        if index < 0 and old is not None and preserve_missing:
            combo.addItem('참조 없음 — 다시 선택', old); index = combo.count()-1
            combo.setItemData(index, str(old), self.QtCore.Qt.ToolTipRole)
        combo.setCurrentIndex(-1 if keep_empty else index if index >= 0 else 0); combo.blockSignals(False)

    def refresh(self, descriptor):
        if not isinstance(descriptor, dict): return
        document, session = descriptor.get('id', self._document), descriptor.get('session_id', self._session)
        if (document, session) != (self._document, self._session):
            self._serial += 1; self._busy = False; self._edited = False; self._definition_stamp = None
            self._joint_edited = False; self._view_loaded = False; self._active_assembly = None
            self._pending_joint_id = None; self._selected_joint = None
            self._editor_loaded = False
            self._select_saved_assembly = True
            self._initial_editor = None
            self._path_read_scope = None
            self.path_browser.refresh([], None)
            for button in self._buttons: button.setEnabled(True)
            for combo in (self.joint, self.connector_a, self.connector_b): self._fill_combo(combo, [])
            self.path.setRowCount(0)
        self._document, self._session = document, session; self._data = deepcopy(descriptor)
        previous = self._motion
        self._motion = deepcopy(descriptor.get('motion', descriptor))
        if self._active_assembly == self.assembly.currentData():
            for key in ('joints', 'occurrences', 'inspection_assembly_id'):
                if (key not in self._motion or self._motion.get('inspection_assembly_id') != self._active_assembly) and key in previous:
                    self._motion[key] = previous[key]
        self._loading = True
        try:
            self._fill_combo(self.assembly, self._motion.get('assemblies', []))
            metadata = self._motion.get('definition') or {}
            if not self._editor_loaded and self._select_saved_assembly:
                drafts = [name for name, value in self._motion.get('editors', {}).items()
                          if value.get('joint_draft') is not None or value.get('definition_draft') is not None]
                selected = self._motion.get('editor_assembly_id') or (drafts[0] if drafts else None)
                if selected:
                    index = self.assembly.findData(selected)
                    if index >= 0: self.assembly.setCurrentIndex(index); self._view_loaded = True
            if not self._view_loaded and metadata.get('assembly_id'):
                index = self.assembly.findData(metadata['assembly_id'])
                if index >= 0: self.assembly.setCurrentIndex(index)
            self._active_assembly = self.assembly.currentData()
            self._fill_combo(self.source, [row for row in descriptor.get('objects', []) if row['id'] != self._active_assembly and (row['type'].startswith(('Part::', 'PartDesign::')) or row['type'] in ('App::Part', 'App::Link', 'Assembly::AssemblyObject'))])
            metadata = self._motion.get('definition') or {}
            if 'joints' in self._motion and self._motion.get('inspection_assembly_id') == self._active_assembly:
                self._fill_combo(self.joint, self._motion['joints'], metadata.get('view', {}).get('joint_id') if not self.joint.count() else None, preserve_missing=True)
                for combo in (self.connector_a, self.connector_b): self._fill_combo(combo, self._motion.get('occurrences', []), preserve_missing=True)
            definition = metadata.get('definition') if metadata.get('assembly_id') == self.assembly.currentData() else None
            stamp = json.dumps(definition, sort_keys=True)
            if not self._edited and stamp != self._definition_stamp:
                self._definition_stamp = stamp; self.drives.setRowCount(0); self.traces.setRowCount(0)
                if definition:
                    for name, field in self.time.items(): field.setText(str(definition['time'][name]))
                    self.fps.setValue(definition['fps']); self.tolerance.setText(str(definition['native_error_tolerance']))
                    for drive in definition['drives']: self._drive_row(drive)
                    for trace in definition['traces']: self._trace_row(trace)
                    self._saved_view = deepcopy(metadata.get('view', {}))
                    if not self._view_loaded:
                        for table, key in ((self.drives, 'drive_row'), (self.traces, 'trace_row')):
                            row = self._saved_view.get(key, -1)
                            if 0 <= row < table.rowCount(): table.selectRow(row)
                        self._view_loaded = True
                else:
                    for field in self.time.values(): field.clear()
                    self.tolerance.clear()
            self._fill_combo(self.trace_select, (definition or {}).get('traces', []))
            self._show_runtime()
            self._refresh_paths()
        finally: self._loading = False
        if not self._editor_loaded:
            self._editor_loaded = True
            self._select_saved_assembly = False
            editor = self._motion.get('editors', {}).get(self.assembly.currentData())
            if editor: self._restore_editor(editor)
        if not self._joint_edited: self._joint_selected(0)
        self._validate_drives()
        if self._initial_editor is None: self._initial_editor = self.current_editor()
        self._show_runtime()
        self._refresh_paths()

    def _show_runtime(self):
        calculation = self._motion.get('calculation') or {}
        self.frame.setRange(0, max(0, calculation.get('frame_count', 1)-1))
        if self._motion.get('frame') is not None: self.frame.setValue(self._motion['frame'])
        if not self._busy:
            states = {'UNCOMPUTED': '계산 전', 'CALCULATED': '계산 완료', 'PLAYING': '재생 중', 'PAUSED': '일시정지',
                'CANCELLED': '미리보기 취소', 'COMPLETED': '재생 완료', 'ADOPTED': '설계 자세 적용', 'FAILED': '작업 실패', 'STALE': '모델 변경 — 재계산 필요'}
            self.status.setText(states.get(self._motion.get('state'), '계산 전') +
                (' / 미리보기 자세' if self._motion.get('preview') else ' / 설계 자세') +
                ' / 계산 프레임 ' + str(calculation.get('frame_count', 0)) +
                (' / ' + str(self._motion['error']) if self._motion.get('error') else ''))
            if self._edited or self._joint_edited:
                self.status.setText(self.status.text() + (' / 미적용 편집 (미저장)' if self.has_unsaved_editor() else ' / 미적용 편집 (저장됨)'))

    def _assembly_changed(self, index):
        if self._loading: return
        if self._busy or self._edited or self._joint_edited:
            self.assembly.blockSignals(True); self.assembly.setCurrentIndex(self.assembly.findData(self._active_assembly)); self.assembly.blockSignals(False)
            self.status.setText('현재 조립의 편집을 적용하거나 취소한 뒤 다른 조립을 선택하세요.'); return
        self._edited = False; self._definition_stamp = None
        self._editor_loaded = False
        self._select_saved_assembly = False
        for combo in (self.joint, self.connector_a, self.connector_b): self._fill_combo(combo, [])
        self.refresh(self._data)
        self._refresh_paths()
        self._send('pre.motion.inspect', {}, inspect=True)

    def _inspect_value(self, value):
        if 'occurrences' not in value: return
        self._loading = True
        try:
            self._motion.update(deepcopy(value))
            self._fill_combo(self.joint, value.get('joints', []), self._pending_joint_id or (self._saved_view.get('joint_id') if not self.joint.count() else None), preserve_missing=True)
            self._pending_joint_id = None
            for combo in (self.connector_a, self.connector_b): self._fill_combo(combo, value['occurrences'], preserve_missing=True)
            for row in range(self.drives.rowCount()):
                combo = self.drives.cellWidget(row, 0); self._fill_combo(combo, [j for j in value.get('joints', []) if j['type'] in DRIVE_TYPES], preserve_missing=True)
            for row in range(self.traces.rowCount()):
                combo = self.traces.cellWidget(row, 1); self._fill_combo(combo, value['occurrences'], preserve_missing=True)
        finally: self._loading = False
        if not self._joint_edited: self._joint_selected(0)
        self._validate_drives()
        self._show_runtime()

    def _joint_selected(self, index):
        if self._loading: return
        if (self._busy or self._joint_edited) and self.joint.currentData() != self._selected_joint:
            self.joint.blockSignals(True); self.joint.setCurrentIndex(self.joint.findData(self._selected_joint)); self.joint.blockSignals(False)
            self.joint_notice.setText('현재 관절 편집을 적용하거나 취소한 뒤 다른 관절을 선택하세요.'); return
        self._selected_joint = self.joint.currentData()
        joint = next((j for j in self._motion.get('joints', []) if j['id'] == self.joint.currentData()), None)
        self._loading = True
        try:
            for field in (self.subelement_a, self.subelement_b, *[f for f, u in self.joint_parameters.values()]): field.clear()
            if not joint:
                self.joint_notice.setText('관절 참조가 없습니다. 새 관절을 추가한 뒤 구동 관절을 다시 선택하세요.'); return
            self.joint_type.setCurrentIndex(self.joint_type.findData(joint['type']))
            if joint.get('grounded_occurrence'):
                self.connector_a.setCurrentIndex(self.connector_a.findData(joint['grounded_occurrence']))
            for name, (field, unit) in self.joint_parameters.items():
                if name in joint.get('parameters', {}): field.setText(str(joint['parameters'][name]))
            for ref, combo, field in zip(joint.get('references', []) if joint['type'] != 'Grounded' else [], (self.connector_a, self.connector_b), (self.subelement_a, self.subelement_b)):
                if ref:
                    self._fill_combo(combo, self._motion.get('occurrences', []), ref[0], preserve_missing=True)
                    field.setText(ref[1][0] if ref[1] else '')
                    field.setToolTip(('연결 위치: ' + (ref[1][1] or '부품 원점') +
                        '\n같은 형상을 유지하면 이 위치도 유지됩니다.') if len(ref[1]) == 2
                        else '이전 형식의 참조입니다. 위치를 확인하고 명시적으로 수정하세요.')
                else: combo.setCurrentIndex(-1)
            self.joint_notice.setText(' '.join(joint.get('issues', [])) or
                ('하위 조립의 관절입니다. 원본 조립을 선택하여 편집하세요.' if not joint.get('editable', True) else ''))
        finally: self._loading = False
        self._joint_controls()

    def _joint_controls(self, *args):
        grounded = self.joint_type.currentData() == 'Grounded'
        for widget in (self.connector_b, self.subelement_a, self.subelement_b, *[f for f, u in self.joint_parameters.values()]):
            widget.setEnabled(not grounded)

    def _edit_joint(self, operation):
        kind = self.joint_type.currentData()
        args = {'type': kind, 'occurrence_id': self.connector_a.currentData()} if kind == 'Grounded' else {
            'type': kind, 'connectors': [{'object_id': combo.currentData(), 'subelement': field.text()} for combo, field in
                ((self.connector_a, self.subelement_a), (self.connector_b, self.subelement_b))],
            'parameters': {name: {'value': self._numeric(field.text()), 'unit': unit} for name, (field, unit) in self.joint_parameters.items() if field.text().strip()}}
        self._send(operation, args, target=self._target(joint=operation.endswith('update')))

    def _numeric(self, text):
        try: return float(text)
        except ValueError: return text  # Invalid cells remain visible and native validation rejects them.

    def _item(self, table, row, column, value, *, readonly=False):
        item = self.Q.QTableWidgetItem(str(value)); table.setItem(row, column, item)
        if readonly: item.setFlags(item.flags() & ~self.QtCore.Qt.ItemIsEditable)

    def _drive_row(self, value):
        row = self.drives.rowCount(); self.drives.insertRow(row)
        joint = self.Q.QComboBox()
        self._fill_combo(joint, [j for j in self._motion.get('joints', []) if j['type'] in DRIVE_TYPES], value.get('joint_id'), preserve_missing=True)
        kind = self.Q.QComboBox()
        kind.addItem('회전', 'Angular'); kind.addItem('이동', 'Linear')
        selected = next((j for j in self._motion.get('joints', []) if j['id'] == joint.currentData()), {})
        default = DRIVE_TYPES.get(selected.get('type'), ('Angular',))[0]
        kind.setCurrentIndex(kind.findData(value.get('type', default)))
        self.drives.setCellWidget(row, 0, joint); self.drives.setCellWidget(row, 1, kind)
        self._item(self.drives, row, 2, value.get('formula', ''))
        self._item(self.drives, row, 3, 'rad' if kind.currentData() == 'Angular' else 'mm', readonly=True)
        def changed(*args):
            current_row = next((r for r in range(self.drives.rowCount()) if self.drives.cellWidget(r, 1) is kind), None)
            if current_row is not None: self._item(self.drives, current_row, 3, 'rad' if kind.currentData() == 'Angular' else 'mm', readonly=True)
            self._mark_edited()
        def joint_changed(*args):
            selected = next((j for j in self._motion.get('joints', []) if j['id'] == joint.currentData()), {})
            allowed = DRIVE_TYPES.get(selected.get('type'), ())
            if len(allowed) == 1: kind.setCurrentIndex(kind.findData(allowed[0]))
            self._mark_edited()
        kind.currentIndexChanged.connect(changed); joint.currentIndexChanged.connect(joint_changed)
        self._mark_edited()

    def _trace_row(self, value):
        row = self.traces.rowCount(); self.traces.insertRow(row)
        self._item(self.traces, row, 0, value.get('id', ''))
        combo = self.Q.QComboBox()
        self._fill_combo(combo, self._motion.get('occurrences', []), value.get('occurrence_id'), preserve_missing=True)
        self.traces.setCellWidget(row, 1, combo); combo.currentIndexChanged.connect(self._mark_edited)
        for column, coordinate in enumerate(value.get('point', ['', '', '']), 2): self._item(self.traces, row, column, coordinate)
        self._item(self.traces, row, 5, 'mm', readonly=True); self._item(self.traces, row, 6, '전체 좌표', readonly=True)
        self._mark_edited()

    def _remove_row(self, table):
        row = table.currentRow()
        if row >= 0: table.removeRow(row); self._mark_edited()

    def _configure(self):
        if self._validate_drives():
            self.status.setText('구동 표에서 표시된 참조 또는 운동 종류를 수정하세요.'); return
        def text(table, row, column):
            item = table.item(row, column); return item.text() if item else ''
        definition = {'time': {**{key: self._numeric(field.text()) for key, field in self.time.items()}, 'unit': 's'},
            'fps': self.fps.value(), 'native_error_tolerance': self._numeric(self.tolerance.text()),
            'drives': [{'joint_id': self.drives.cellWidget(row, 0).currentData(), 'type': self.drives.cellWidget(row, 1).currentData(),
                        'formula': text(self.drives, row, 2), 'unit': text(self.drives, row, 3)} for row in range(self.drives.rowCount())],
            'traces': [{'id': text(self.traces, row, 0), 'occurrence_id': self.traces.cellWidget(row, 1).currentData(),
                        'point': [self._numeric(text(self.traces, row, c)) for c in (2, 3, 4)], 'frame': 'occurrence_local',
                        'coordinate_unit': 'mm', 'output_frame': 'document_global'} for row in range(self.traces.rowCount())]}
        self._send('pre.motion.configure', {'definition': definition, 'view': self.current_view()})

    def current_view(self):
        joint = self.joint.currentData()
        if not any(j['id'] == joint for j in self._motion.get('joints', [])): joint = None
        return {'joint_id': joint, 'drive_row': self.drives.currentRow(), 'trace_row': self.traces.currentRow()}

    def current_editor(self):
        def cell(table, row, column):
            item = table.item(row, column); return item.text() if item else ''
        joint = None
        if self._joint_edited:
            joint = {'joint_id': self.joint.currentData(), 'type': self.joint_type.currentData(),
                'connectors': [{'object_id': combo.currentData(), 'subelement': field.text()} for combo, field in
                    ((self.connector_a, self.subelement_a), (self.connector_b, self.subelement_b))],
                'parameters': {name: field.text() for name, (field, unit) in self.joint_parameters.items()}}
        definition = None
        if self._edited:
            definition = {'time': {name: field.text() for name, field in self.time.items()},
                'fps': self.fps.value(), 'tolerance': self.tolerance.text(),
                'drives': [{'joint_id': self.drives.cellWidget(row, 0).currentData(),
                    'type': self.drives.cellWidget(row, 1).currentData(), 'formula': cell(self.drives, row, 2),
                    'unit': cell(self.drives, row, 3)} for row in range(self.drives.rowCount())],
                'traces': [{'id': cell(self.traces, row, 0), 'occurrence_id': self.traces.cellWidget(row, 1).currentData(),
                    'point': [cell(self.traces, row, c) for c in (2, 3, 4)]} for row in range(self.traces.rowCount())]}
        editor = {'view': self.current_view(), 'joint_draft': joint, 'definition_draft': definition}
        path_view = self.path_browser.current_view()
        if path_view is not None: editor['path_view'] = path_view
        return editor

    def editor_token(self):
        return self._document, self._session, self.assembly.currentData(), self._edit_version, self._joint_version, json.dumps(self.current_editor(), sort_keys=True)

    def editor_snapshot(self):
        return {'assembly_id': self.assembly.currentData(), 'editor': self.current_editor(),
                'document_id': self._document, 'session_id': self._session}

    def pending_editor(self):
        if self.assembly.currentData() is None: return None
        editor = self.current_editor()
        stored = self._motion.get('editors', {}).get(self.assembly.currentData())
        if stored is None:
            applied = (self._motion.get('definition') or {}).get('view', {})
            if editor['joint_draft'] is None and editor['definition_draft'] is None and editor['view'] == applied and self._motion.get('editor_assembly_id') in (None, self.assembly.currentData()): return None
        elif editor == stored and self._motion.get('editor_assembly_id') in (None, self.assembly.currentData()): return None
        return self.editor_snapshot()

    def has_unsaved_editor(self):
        if self.assembly.currentData() not in self._motion.get('editors', {}):
            return self.current_editor() != self._initial_editor or self._motion.get('editor_assembly_id') not in (None, self.assembly.currentData())
        return self.pending_editor() is not None

    def accept_saved_editor(self, snapshot):
        if snapshot.get('session_id', self._session) != self._session or snapshot.get('document_id', self._document) != self._document: return
        self._motion.setdefault('editors', {})[snapshot['assembly_id']] = deepcopy(snapshot['editor'])
        self._motion['editor_assembly_id'] = snapshot['assembly_id']
        self._data.setdefault('motion', {}).setdefault('editors', {})[snapshot['assembly_id']] = deepcopy(snapshot['editor'])

    def _restore_editor(self, editor):
        self._loading = True
        try:
            view = editor.get('view', {})
            joint = editor.get('joint_draft')
            if joint is not None:
                self._fill_combo(self.joint, self._motion.get('joints', []), joint.get('joint_id'), preserve_missing=True)
                if joint.get('joint_id') is None: self.joint.setCurrentIndex(-1)
                self._selected_joint = self.joint.currentData()
                self.joint_type.setCurrentIndex(self.joint_type.findData(joint.get('type')))
                for ref, combo, field in zip(joint.get('connectors', []), (self.connector_a, self.connector_b), (self.subelement_a, self.subelement_b)):
                    self._fill_combo(combo, self._motion.get('occurrences', []), ref.get('object_id'), preserve_missing=True)
                    if ref.get('object_id') is None: combo.setCurrentIndex(-1)
                    field.setText(ref.get('subelement', ''))
                for name, (field, unit) in self.joint_parameters.items(): field.setText(joint.get('parameters', {}).get(name, ''))
            definition = editor.get('definition_draft')
            if definition is not None:
                for name, field in self.time.items(): field.setText(definition.get('time', {}).get(name, ''))
                self.fps.setValue(definition.get('fps', 30)); self.tolerance.setText(definition.get('tolerance', ''))
                self.drives.setRowCount(0); self.traces.setRowCount(0)
                for value in definition.get('drives', []):
                    self._drive_row(value)
                    self._item(self.drives, self.drives.rowCount()-1, 3, value.get('unit', ''), readonly=True)
                    if value.get('joint_id') is None: self.drives.cellWidget(self.drives.rowCount()-1, 0).setCurrentIndex(-1)
                for value in definition.get('traces', []):
                    self._trace_row(value)
                    if value.get('occurrence_id') is None: self.traces.cellWidget(self.traces.rowCount()-1, 1).setCurrentIndex(-1)
            if joint is None:
                self._fill_combo(self.joint, self._motion.get('joints', []), view.get('joint_id'), preserve_missing=True)
                if view.get('joint_id') is None: self.joint.setCurrentIndex(-1)
            for table, key in ((self.drives, 'drive_row'), (self.traces, 'trace_row')):
                row = view.get(key, -1)
                if 0 <= row < table.rowCount(): table.selectRow(row)
                else: table.setCurrentCell(-1, -1); table.clearSelection()
            self._joint_edited = joint is not None; self._edited = definition is not None
            if editor.get('path_view'): self.path_browser.restore_view(editor['path_view'])
        finally: self._loading = False
        self._joint_controls()

    def pending_view(self):
        """Save adapter flushes this selection before its existing document save."""
        metadata = self._motion.get('definition') or {}
        if self._edited or metadata.get('assembly_id') != self.assembly.currentData(): return None
        view = self.current_view()
        return {'assembly_id': self.assembly.currentData(), 'view': view} if view != metadata.get('view', {}) else None

    def accept_saved_view(self, snapshot):
        metadata = self._motion.get('definition') or {}
        if metadata.get('assembly_id') == snapshot.get('assembly_id'):
            metadata['view'] = deepcopy(snapshot['view'])
            self._saved_view = deepcopy(snapshot['view'])

    def _validate_drives(self):
        if self._loading: return []
        issues, seen = [], set()
        for row in range(self.drives.rowCount()):
            combo, kind = self.drives.cellWidget(row, 0), self.drives.cellWidget(row, 1)
            if combo is None or kind is None: continue
            joint = next((j for j in self._motion.get('joints', []) if j['id'] == combo.currentData()), None)
            message = ''
            if joint is None: message = '관절 참조 없음 — 다시 선택하세요.'
            elif kind.currentData() not in DRIVE_TYPES.get(joint['type'], ()): message = '이 관절의 운동 종류를 확인하세요.'
            elif joint.get('issues'): message = '관절 연결을 먼저 복구하세요.'
            key = (combo.currentData(), kind.currentData())
            if key in seen: message = '같은 관절에 같은 종류의 구동을 중복 지정했습니다.'
            seen.add(key); combo.setToolTip(message)
            if message: issues.append(str(row+1) + '행: ' + message)
        if hasattr(self, 'definition_notice'):
            self.definition_notice.setText('\n'.join(issues) if issues else ('구동 편집 중 — 적용 후 계산할 수 있습니다.' if self._edited else ''))
        return issues

    def _show_path(self, value):
        self._motion['path'] = deepcopy(value)
        summary = next((s for s in self._motion.get('path_results', []) if s['id'] == value['calculation_id']), None)
        if summary is None:
            summary = {'id': value['calculation_id'], 'assembly_id': self.assembly.currentData(), 'paths': {}, 'source_status': 'CURRENT'}
            self._motion.setdefault('path_results', []).append(summary)
        summary['paths'][value['trace_id']] = deepcopy(value)
        self._refresh_paths(latest=value)

    def _refresh_paths(self, *, latest=None):
        summaries = [s for s in self._motion.get('path_results', []) if s.get('assembly_id') == self.assembly.currentData()]
        self.path_browser.refresh(summaries, self._calculation_id(), latest=latest,
            can_preview=not (self._edited or self._joint_edited or self._busy))

    def _read_path(self, *, all_frames=False):
        calculation = self._motion.get('calculation') or {}
        if not self._calculation_id() or not self.trace_select.currentData():
            self.path_browser.notice.setText('현재 문서에 계산된 프레임이 없습니다. 보존 경로는 아래 표·곡선에서 읽을 수 있습니다.'); return
        if self._edited or self._joint_edited:
            self.path_browser.notice.setText('관절과 구동 편집을 적용하거나 취소한 뒤 계산된 경로를 읽으세요.'); return
        scope = (self._document, self._session, self.assembly.currentData(), self._edit_version, self._joint_version)
        self._path_read_scope = scope
        trace = self.trace_select.currentData(); start = 0 if all_frames else self.path_start.value()
        def page(index):
            current = (self._document, self._session, self.assembly.currentData(), self._edit_version, self._joint_version)
            if self._path_read_scope != scope or current != scope:
                self._path_read_scope = None; return
            count = min(200 if all_frames else self.path_count.value(), calculation['frame_count']-index)
            if count <= 0:
                self._path_read_scope = None; self.path_browser.notice.setText('시작 프레임이 계산 범위를 벗어났습니다.'); return
            def completed(value):
                if all_frames and index+count < calculation['frame_count']: page(index+count)
                else: self._path_read_scope = None
            def failed():
                self._path_read_scope = None
                self.path_browser._message('경로 읽기를 완료하지 못했습니다. 이미 읽은 원자료와 누락 프레임 수는 남아 있습니다.')
            self._send('pre.motion.path', {'calculation_id': calculation['id'], 'trace_id': trace,
                'start': index, 'count': count}, on_done=completed, on_failure=failed)
        page(start)
