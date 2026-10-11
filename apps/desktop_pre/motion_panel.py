"""Injected native Qt controls; every edit uses the owner's typed command queue.

No PySide6/FreeCAD import and no native object writes occur in this module.
"""
from copy import deepcopy
import json

from apps.desktop_pre.motion import JOINT_TYPES


def make_panel(QtCore, QtWidgets, submit, *, read=None):
    """Return QWidget with refresh(descriptor); submit(op,args,target,on_done).

    read, when supplied, reads the active owner's small descriptor on the GUI
    thread. Command completion is asynchronous. The parent owns HTTP retries.
    """
    controller = MotionPanel(QtCore, QtWidgets, submit, read=read)
    controller.widget.motion_controller = controller
    controller.widget.refresh = controller.refresh
    return controller.widget


class MotionPanel:
    def __init__(self, QtCore, QtWidgets, submit, *, read=None):
        self.Q, self.QtCore, self.submit, self.read = QtWidgets, QtCore, submit, read
        self.widget = QtWidgets.QWidget()
        self._document = None; self._session = None; self._serial = 0; self._busy = False; self._loading = False
        self._edited = False; self._definition_stamp = None; self._data = {}; self._motion = {}
        self._buttons = []
        layout = QtWidgets.QVBoxLayout(self.widget)
        row = QtWidgets.QHBoxLayout(); self.assembly = QtWidgets.QComboBox()
        row.addWidget(QtWidgets.QLabel('Native Assembly')); row.addWidget(self.assembly, 1)
        self._button(row, 'Inspect', lambda: self._send('pre.motion.inspect', {}, inspect=True))
        layout.addLayout(row)
        self.status = QtWidgets.QLabel('Select a connected native document and assembly.')
        self.status.setWordWrap(True); layout.addWidget(self.status)
        tabs = QtWidgets.QTabWidget(); layout.addWidget(tabs)
        assembly_tab, assembly_layout = self._tab(tabs, 'Assembly / joints')
        form = QtWidgets.QFormLayout()
        self.assembly_label = QtWidgets.QLineEdit(); self.assembly_label.setPlaceholderText('New assembly label')
        form.addRow('Assembly label', self.assembly_label)
        self.source = QtWidgets.QComboBox(); self.occurrence_label = QtWidgets.QLineEdit()
        self.occurrence_label.setPlaceholderText('Occurrence label')
        form.addRow('Existing native source', self.source); form.addRow('Occurrence label', self.occurrence_label)
        assembly_layout.addLayout(form)
        buttons = QtWidgets.QHBoxLayout()
        self._button(buttons, 'Create native Assembly', lambda: self._send('pre.assembly.create', {'label': self.assembly_label.text()}, target={}))
        self._button(buttons, 'Link occurrence', lambda: self._send('pre.assembly.link', {'source_id': self.source.currentData(), 'label': self.occurrence_label.text()}))
        assembly_layout.addLayout(buttons)
        form = QtWidgets.QFormLayout(); self.joint = QtWidgets.QComboBox(); self.joint_type = QtWidgets.QComboBox()
        self.joint_type.addItems(['Grounded', *JOINT_TYPES])
        self.connector_a, self.connector_b = QtWidgets.QComboBox(), QtWidgets.QComboBox()
        self.subelement_a, self.subelement_b = QtWidgets.QLineEdit(), QtWidgets.QLineEdit()
        for field in (self.subelement_a, self.subelement_b): field.setPlaceholderText('Face1 / Edge1 / Vertex1; empty = occurrence origin')
        form.addRow('Existing joint', self.joint); form.addRow('Joint type', self.joint_type)
        form.addRow('Occurrence A / grounded', self.connector_a); form.addRow('Native subelement A', self.subelement_a)
        form.addRow('Occurrence B', self.connector_b); form.addRow('Native subelement B', self.subelement_b)
        self.joint_parameters = {}
        for name, unit in [('Distance', 'mm'), ('Distance2', 'mm'), ('Angle', 'deg')]:
            field = QtWidgets.QLineEdit(); field.setPlaceholderText('Optional explicit value')
            self.joint_parameters[name] = (field, unit); form.addRow(name + ' [' + unit + ']', field)
        assembly_layout.addLayout(form)
        buttons = QtWidgets.QHBoxLayout()
        self._button(buttons, 'Create joint', lambda: self._edit_joint('pre.joint.create'))
        self._button(buttons, 'Update selected joint', lambda: self._edit_joint('pre.joint.update'))
        self._button(buttons, 'Remove selected joint', lambda: self._send('pre.joint.remove', {}, target=self._target(joint=True)))
        assembly_layout.addLayout(buttons)
        _, definition_layout = self._tab(tabs, 'Time / drives / trace points')
        form = QtWidgets.QFormLayout(); self.time = {}
        for key in ('start', 'end', 'step'):
            self.time[key] = QtWidgets.QLineEdit(); form.addRow(key.title() + ' [s]', self.time[key])
            self.time[key].textEdited.connect(self._mark_edited)
        self.fps = QtWidgets.QSpinBox(); self.fps.setRange(1, 120); self.fps.setValue(30)
        self.tolerance = QtWidgets.QLineEdit(); self.tolerance.setPlaceholderText('Native solver global error tolerance')
        form.addRow('Playback [frames/s]', self.fps); form.addRow('Native error tolerance', self.tolerance)
        self.fps.valueChanged.connect(self._mark_edited); self.tolerance.textEdited.connect(self._mark_edited)
        definition_layout.addLayout(form)
        self.drives = QtWidgets.QTableWidget(0, 4); self.drives.setHorizontalHeaderLabels(['Native joint', 'Drive', 'Native formula(time)', 'Unit'])
        self.drives.cellChanged.connect(self._mark_edited); definition_layout.addWidget(self.drives)
        buttons = QtWidgets.QHBoxLayout()
        self._button(buttons, 'Add drive', lambda: self._drive_row({}))
        self._button(buttons, 'Remove drive', lambda: self._remove_row(self.drives))
        definition_layout.addLayout(buttons)
        self.traces = QtWidgets.QTableWidget(0, 7)
        self.traces.setHorizontalHeaderLabels(['Trace ID', 'Occurrence', 'Local x', 'Local y', 'Local z', 'Unit', 'Output frame'])
        self.traces.cellChanged.connect(self._mark_edited); definition_layout.addWidget(self.traces)
        buttons = QtWidgets.QHBoxLayout()
        self._button(buttons, 'Add trace point', lambda: self._trace_row({}))
        self._button(buttons, 'Remove trace point', lambda: self._remove_row(self.traces))
        self._button(buttons, 'Apply motion definition', self._configure)
        definition_layout.addLayout(buttons)
        _, frames_layout = self._tab(tabs, 'Calculated frames / path')
        frames_layout.addWidget(QtWidgets.QLabel('Native kinematics only. Calculate is synchronous and cannot be interrupted once applying.\n'
            'Displayed times are the declared nominal output grid; FreeCAD exposes frame indices, not frame timestamps.\n'
            'Preview restores design pose on Stop, completion, Save, close and FEM transition.'))
        buttons = QtWidgets.QHBoxLayout()
        self._button(buttons, 'Calculate native frames', lambda: self._send('pre.motion.calculate', {}))
        self.frame = QtWidgets.QSpinBox(); self.frame.setRange(0, 0); buttons.addWidget(self.frame)
        self._button(buttons, 'Preview selected frame', lambda: self._send('pre.motion.frame', self._frame_args()))
        self._button(buttons, 'Adopt displayed frame as design', lambda: self._send('pre.motion.adopt_pose', self._frame_args()))
        frames_layout.addLayout(buttons)
        buttons = QtWidgets.QHBoxLayout()
        for label, operation, extra in [('Play', 'play', {'direction': 1}), ('Reverse', 'play', {'direction': -1}),
                                         ('Pause', 'pause', None), ('Stop / restore', 'stop', None), ('Cancel preview', 'cancel', None)]:
            self._button(buttons, label, lambda op=operation, value=extra: self._send('pre.motion.' + op,
                {'calculation_id': self._calculation_id(), **value} if value is not None else {}))
        frames_layout.addLayout(buttons)
        row = QtWidgets.QHBoxLayout(); self.trace_select = QtWidgets.QComboBox()
        self.path_start, self.path_count = QtWidgets.QSpinBox(), QtWidgets.QSpinBox()
        self.path_start.setRange(0, 2000); self.path_count.setRange(1, 200); self.path_count.setValue(100)
        row.addWidget(self.trace_select, 1); row.addWidget(self.path_start); row.addWidget(self.path_count)
        self._button(row, 'Read native tracked path', lambda: self._send('pre.motion.path', {
            'calculation_id': self._calculation_id(), 'trace_id': self.trace_select.currentData(),
            'start': self.path_start.value(), 'count': self.path_count.value()}))
        frames_layout.addLayout(row)
        self.path = QtWidgets.QTableWidget(0, 5)
        self.path.setHorizontalHeaderLabels(['Native frame', 'Nominal time [s]', 'Global x [mm]', 'Global y [mm]', 'Global z [mm]'])
        self.path.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers); frames_layout.addWidget(self.path)
        self.assembly.currentIndexChanged.connect(self._assembly_changed)
        self.joint.currentIndexChanged.connect(self._joint_selected)

    def _tab(self, tabs, label):
        widget = self.Q.QWidget(); layout = self.Q.QVBoxLayout(widget); tabs.addTab(widget, label)
        return widget, layout

    def _button(self, layout, label, callback):
        button = self.Q.QPushButton(label)
        button.clicked.connect(lambda checked=False: callback()); layout.addWidget(button); self._buttons.append(button)
        return button

    def _mark_edited(self, *args):
        if not self._loading: self._edited = True

    def _target(self, *, joint=False):
        target = {'assembly_id': self.assembly.currentData()}
        if joint: target['joint_id'] = self.joint.currentData()
        return target

    def _calculation_id(self):
        calculation = self._motion.get('calculation') or {}
        return calculation.get('id') if calculation.get('assembly_id') == self.assembly.currentData() else None

    def _frame_args(self):
        return {'calculation_id': self._calculation_id(), 'frame': self.frame.value()}

    def _send(self, operation, args, *, target=None, inspect=False):
        if self._busy: return
        target = self._target() if target is None else target
        self._serial += 1; serial = self._serial; scope = (self._document, self._session, self.assembly.currentData())
        self._busy = True
        for button in self._buttons: button.setEnabled(False)
        self.status.setText('Queued ' + operation + ('; native calculation cannot be interrupted once applying.' if operation.endswith('calculate') else ''))
        def done(reply):
            if serial != self._serial: return
            self._busy = False
            for button in self._buttons: button.setEnabled(True)
            if scope != (self._document, self._session, self.assembly.currentData()): return
            reply = reply or {}
            if reply.get('status') == 'FAILED' or reply.get('error'):
                error = reply.get('error', {}); self.status.setText(error.get('message', str(error)) if isinstance(error, dict) else str(error)); return
            value = reply.get('result', reply)
            if 'frame_count' in value and 'id' in value:
                self._motion['calculation'] = deepcopy(value); self._motion.update(state='CALCULATED', preview=False, frame=None)
            if 'calculation' in value: self._motion.update(deepcopy(value))
            if 'calculation_id' in value and 'preview' in value: self._motion.update(preview=value['preview'], frame=value.get('frame'), state='PAUSED')
            if 'rows' in value and 'trace_id' in value: self._show_path(value)
            if operation.endswith('configure'): self._edited = False
            if self.read is not None:
                self.refresh(self.read())
            if inspect:
                self._inspect_value(value)
            self._show_runtime()
        try:
            reply = self.submit(operation, args, target, done)
            if not isinstance(reply, dict) or not reply.get('queued'): done(reply)
        except Exception as error:
            done({'status': 'FAILED', 'error': {'message': str(error)}})

    def _fill_combo(self, combo, rows, selected=None):
        old = combo.currentData() if selected is None else selected
        combo.blockSignals(True); combo.clear()
        for row in rows: combo.addItem(row.get('label', row['id']), row['id'])
        index = combo.findData(old); combo.setCurrentIndex(index if index >= 0 else 0); combo.blockSignals(False)

    def refresh(self, descriptor):
        if not isinstance(descriptor, dict): return
        document, session = descriptor.get('id', self._document), descriptor.get('session_id', self._session)
        if (document, session) != (self._document, self._session):
            self._serial += 1; self._busy = False; self._edited = False; self._definition_stamp = None
            for button in self._buttons: button.setEnabled(True)
            for combo in (self.joint, self.connector_a, self.connector_b): self._fill_combo(combo, [])
            self.path.setRowCount(0)
        self._document, self._session = document, session; self._data = deepcopy(descriptor)
        self._motion = deepcopy(descriptor.get('motion', descriptor))
        self._loading = True
        try:
            self._fill_combo(self.assembly, self._motion.get('assemblies', []))
            self._fill_combo(self.source, [row for row in descriptor.get('objects', []) if row['type'].startswith(('Part::', 'PartDesign::')) or row['type'] in ('App::Part', 'App::Link')])
            metadata = self._motion.get('definition') or {}
            definition = metadata.get('definition') if metadata.get('assembly_id') == self.assembly.currentData() else None
            stamp = json.dumps(definition, sort_keys=True)
            if not self._edited and stamp != self._definition_stamp:
                self._definition_stamp = stamp; self.drives.setRowCount(0); self.traces.setRowCount(0)
                if definition:
                    for name, field in self.time.items(): field.setText(str(definition['time'][name]))
                    self.fps.setValue(definition['fps']); self.tolerance.setText(str(definition['native_error_tolerance']))
                    for drive in definition['drives']: self._drive_row(drive)
                    for trace in definition['traces']: self._trace_row(trace)
                else:
                    for field in self.time.values(): field.clear()
                    self.tolerance.clear()
            self._fill_combo(self.trace_select, (definition or {}).get('traces', []))
            self._show_runtime()
            if self._motion.get('path'): self._show_path(self._motion['path'])
        finally: self._loading = False

    def _show_runtime(self):
        calculation = self._motion.get('calculation') or {}
        self.frame.setRange(0, max(0, calculation.get('frame_count', 1)-1))
        if self._motion.get('frame') is not None: self.frame.setValue(self._motion['frame'])
        if not self._busy:
            self.status.setText(str(self._motion.get('state', 'UNCOMPUTED')) +
                (' · preview pose; design preserved' if self._motion.get('preview') else ' · design pose') +
                ' · native frames: ' + str(calculation.get('frame_count', 0)) +
                (' · ' + str(self._motion['error']) if self._motion.get('error') else ''))

    def _assembly_changed(self, index):
        if self._loading: return
        self._edited = False; self._definition_stamp = None
        self.refresh(self._data)
        for combo in (self.joint, self.connector_a, self.connector_b): self._fill_combo(combo, [])
        self.path.setRowCount(0)
        self._send('pre.motion.inspect', {}, inspect=True)

    def _inspect_value(self, value):
        if 'occurrences' not in value: return
        self._loading = True
        try:
            self._motion.update(deepcopy(value))
            self._fill_combo(self.joint, value.get('joints', []))
            for combo in (self.connector_a, self.connector_b): self._fill_combo(combo, value['occurrences'])
            for row in range(self.drives.rowCount()):
                combo = self.drives.cellWidget(row, 0); self._fill_combo(combo, value.get('joints', []))
            for row in range(self.traces.rowCount()):
                combo = self.traces.cellWidget(row, 1); self._fill_combo(combo, value['occurrences'])
        finally: self._loading = False
        self._joint_selected(0)

    def _joint_selected(self, index):
        if self._loading: return
        joint = next((j for j in self._motion.get('joints', []) if j['id'] == self.joint.currentData()), None)
        if not joint: return
        self.joint_type.setCurrentText(joint['type'])
        if joint.get('grounded_occurrence'):
            self.connector_a.setCurrentIndex(self.connector_a.findData(joint['grounded_occurrence']))
        for ref, combo, field in zip(joint.get('references', []), (self.connector_a, self.connector_b), (self.subelement_a, self.subelement_b)):
            if ref: combo.setCurrentIndex(combo.findData(ref[0])); field.setText(ref[1][0] if ref[1] else '')

    def _edit_joint(self, operation):
        kind = self.joint_type.currentText()
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
        self._fill_combo(joint, self._motion.get('joints') or ([{'id': value['joint_id']}] if value.get('joint_id') else []), value.get('joint_id'))
        kind = self.Q.QComboBox(); kind.addItems(['Angular', 'Linear']); kind.setCurrentText(value.get('type', 'Angular'))
        self.drives.setCellWidget(row, 0, joint); self.drives.setCellWidget(row, 1, kind)
        self._item(self.drives, row, 2, value.get('formula', ''))
        self._item(self.drives, row, 3, 'rad' if kind.currentText() == 'Angular' else 'mm', readonly=True)
        def changed(*args):
            current_row = next((r for r in range(self.drives.rowCount()) if self.drives.cellWidget(r, 1) is kind), None)
            if current_row is not None: self._item(self.drives, current_row, 3, 'rad' if kind.currentText() == 'Angular' else 'mm', readonly=True)
            self._mark_edited()
        kind.currentIndexChanged.connect(changed); joint.currentIndexChanged.connect(self._mark_edited)
        self._mark_edited()

    def _trace_row(self, value):
        row = self.traces.rowCount(); self.traces.insertRow(row)
        self._item(self.traces, row, 0, value.get('id', ''))
        combo = self.Q.QComboBox()
        self._fill_combo(combo, self._motion.get('occurrences') or ([{'id': value['occurrence_id']}] if value.get('occurrence_id') else []), value.get('occurrence_id'))
        self.traces.setCellWidget(row, 1, combo); combo.currentIndexChanged.connect(self._mark_edited)
        for column, coordinate in enumerate(value.get('point', ['', '', '']), 2): self._item(self.traces, row, column, coordinate)
        self._item(self.traces, row, 5, 'mm', readonly=True); self._item(self.traces, row, 6, 'document_global', readonly=True)
        self._mark_edited()

    def _remove_row(self, table):
        row = table.currentRow()
        if row >= 0: table.removeRow(row); self._mark_edited()

    def _configure(self):
        def text(table, row, column):
            item = table.item(row, column); return item.text() if item else ''
        definition = {'time': {**{key: self._numeric(field.text()) for key, field in self.time.items()}, 'unit': 's'},
            'fps': self.fps.value(), 'native_error_tolerance': self._numeric(self.tolerance.text()),
            'drives': [{'joint_id': self.drives.cellWidget(row, 0).currentData(), 'type': self.drives.cellWidget(row, 1).currentText(),
                        'formula': text(self.drives, row, 2), 'unit': text(self.drives, row, 3)} for row in range(self.drives.rowCount())],
            'traces': [{'id': text(self.traces, row, 0), 'occurrence_id': self.traces.cellWidget(row, 1).currentData(),
                        'point': [self._numeric(text(self.traces, row, c)) for c in (2, 3, 4)], 'frame': 'occurrence_local',
                        'coordinate_unit': 'mm', 'output_frame': 'document_global'} for row in range(self.traces.rowCount())]}
        self._send('pre.motion.configure', {'definition': definition})

    def _show_path(self, value):
        self.path.setRowCount(len(value.get('rows', [])))
        for row, sample in enumerate(value.get('rows', [])):
            for column, number in enumerate([sample['frame'], sample['nominal_time'], *sample['point']]): self._item(self.path, row, column, number, readonly=True)
