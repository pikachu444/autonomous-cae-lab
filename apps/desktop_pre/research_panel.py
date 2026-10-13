"""Compact native Analysis variables/response worksheet, using existing commands."""
from copy import deepcopy
import re


def response_dialog(QtWidgets, pairs, definition=None, parent=None):
    """Select an actual supported channel; dimensional units follow that channel."""
    dialog = QtWidgets.QDialog(parent)
    dialog.setWindowTitle('Response')
    layout = QtWidgets.QVBoxLayout(dialog)
    form = QtWidgets.QFormLayout()
    name = QtWidgets.QLineEdit((definition or {}).get('id', 'response'))
    name.setObjectName('responseName')
    kind = QtWidgets.QComboBox(); kind.setObjectName('responseKind')
    kind.addItem('Displacement', 'displacement')
    if pairs:
        kind.addItem('Pair force', 'pair')
        kind.addItem('Contact field', 'contact_field')
    pair = QtWidgets.QComboBox(); pair.setObjectName('responsePair')
    for row in pairs:
        pair.addItem(row['draft']['label'], row['object_id'])
    field, component, reduction = (QtWidgets.QComboBox() for _ in range(3))
    field.setObjectName('responseField'); component.setObjectName('responseComponent')
    reduction.setObjectName('responseReduction')
    frame = QtWidgets.QComboBox(); frame.addItems(['Final increment', 'Retained increment index'])
    frame.setObjectName('responseFrame')
    index = QtWidgets.QSpinBox(); index.setRange(0, 1000000); index.setObjectName('responseFrameIndex')
    increment = QtWidgets.QWidget(); increment_layout = QtWidgets.QHBoxLayout(increment)
    increment_layout.setContentsMargins(0, 0, 0, 0)
    increment_layout.addWidget(frame); increment_layout.addWidget(index)
    unit, scope = QtWidgets.QLabel(), QtWidgets.QLabel()
    unit.setObjectName('responseUnit'); scope.setWordWrap(True)
    for label, widget in [('Name', name), ('Response', kind), ('Pair', pair),
                          ('Quantity', field), ('Selection', component), ('Increment', increment),
                          ('Reduction', reduction), ('Unit', unit)]:
        form.addRow(label, widget)
    layout.addLayout(form); layout.addWidget(scope)
    error = QtWidgets.QLabel(); error.setWordWrap(True); layout.addWidget(error)
    def choices(widget, rows):
        widget.clear()
        for label, value in rows:
            widget.addItem(label, value)
    def set_value(widget, value):
        found = widget.findData(value)
        if found >= 0:
            widget.setCurrentIndex(found)
    def field_changed(*_):
        selected = kind.currentData()
        value = field.currentData()
        unit.setText('N' if selected == 'pair' else
                     'MPa' if value in ('CPRESS', 'CSHEAR1', 'CSHEAR2') else 'mm')
    def changed(*_):
        selected = kind.currentData()
        pair.setEnabled(selected != 'displacement')
        if selected == 'contact_field':
            choices(field, [('Pressure', 'CPRESS'), ('Raw COPEN', 'COPEN'),
                ('Slip 1', 'CSLIP1'), ('Slip 2', 'CSLIP2'), ('Shear 1', 'CSHEAR1'),
                ('Shear 2', 'CSHEAR2'), ('Geometric gap', 'GeomGap_mm')])
            choices(component, [('Side A', 'a'), ('Side B', 'b'), ('Both sides', 'both')])
            choices(reduction, [('Maximum', 'max'), ('Minimum', 'min'), ('Mean', 'mean'), ('Nodal field', 'field')])
            scope.setText('Shared nodal projection. Geometric gap is derived; raw COPEN is kept distinct.')
        else:
            choices(field, [('Normal force', 'CFN'), ('Total force', 'CF'), ('Shear force', 'CFS')]
                    if selected == 'pair' else [('Displacement', 'displacement')])
            choices(component, [(axis, axis) for axis in 'XYZ']); set_value(component, 'Z')
            choices(reduction, [('Selected increment', 'value'), ('All retained increments', 'series')]
                    if selected == 'pair' else [('Maximum', 'max'), ('Minimum', 'min'), ('Mean', 'mean'), ('Nodal field', 'field')])
            scope.setText('Pair-specific DAT resultant on side A; global component. Load parameter is dimensionless.'
                          if selected == 'pair' else 'Global nodal component at the retained final increment.')
        frame.setEnabled(selected != 'displacement')
        if selected == 'displacement':
            frame.setCurrentIndex(0)
        index.setEnabled(frame.currentIndex() == 1 and selected != 'displacement')
        field_changed()
    def frame_changed(*_):
        index.setEnabled(frame.currentIndex() == 1 and kind.currentData() != 'displacement')
    def reduction_changed(*_):
        all_frames = reduction.currentData() == 'series'
        frame.setEnabled(kind.currentData() != 'displacement' and not all_frames)
        if all_frames:
            frame.setCurrentIndex(0)
        frame_changed()
    kind.currentIndexChanged.connect(changed)
    field.currentIndexChanged.connect(field_changed)
    frame.currentIndexChanged.connect(frame_changed)
    reduction.currentIndexChanged.connect(reduction_changed)
    if definition:
        set_value(kind, definition['kind'])
    changed()
    if definition:
        set_value(pair, definition.get('pair_id'))
        set_value(field, definition.get('quantity', definition.get('field', 'displacement')))
        set_value(component, definition.get('component', definition.get('side')))
        set_value(reduction, definition['reduction'])
        if definition['increment'] != 'final':
            frame.setCurrentIndex(1); index.setValue(definition['increment'])
    result = {}
    def accept():
        identifier = name.text().strip()
        if not re.fullmatch('[a-z][a-z0-9_]{0,47}', identifier):
            error.setText('Use a short lower-case response name.')
            return
        selected = kind.currentData()
        result.update(id=identifier, kind=selected, unit=unit.text(), reduction=reduction.currentData(),
                      increment='final' if frame.currentIndex() == 0 else index.value())
        if selected == 'pair':
            result.update(pair_id=pair.currentData(), quantity=field.currentData(), component=component.currentData())
        elif selected == 'contact_field':
            result.update(pair_id=pair.currentData(), field=field.currentData(), side=component.currentData())
        else:
            result.update(component=component.currentData())
        dialog.accept()
    buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
    buttons.accepted.connect(accept); buttons.rejected.connect(dialog.reject); layout.addWidget(buttons)
    return result if dialog.exec() == QtWidgets.QDialog.Accepted else None


def make_panel(QtWidgets, QtCore, research, submit, create_plan):
    owner = research.owner
    class Panel(QtWidgets.QWidget):
        def __init__(self):
            super().__init__()
            self.info, self.busy, self.capture_id = None, False, None
            self.response_defs = []
            layout = QtWidgets.QVBoxLayout(self)
            row = QtWidgets.QHBoxLayout()
            self.analysis, self.solver, self.method = QtWidgets.QComboBox(), QtWidgets.QComboBox(), QtWidgets.QComboBox()
            self.method.addItems(['DOE', 'Optimization'])
            from .fem_edit import _native_type
            for obj in owner.doc.Objects:
                if _native_type(obj) == 'Fem::FemAnalysis':
                    self.analysis.addItem(obj.Label, obj.Name)
            connect = QtWidgets.QPushButton('조립 형상 연결…')
            connect.setObjectName('connectAssemblyAnalysis')
            connect.clicked.connect(self.connect_assembly)
            row.addWidget(connect)
            refresh = QtWidgets.QPushButton('Refresh')
            refresh.clicked.connect(self.refresh)
            self.analysis.currentIndexChanged.connect(self.refresh)
            row.addWidget(self.analysis, 2); row.addWidget(self.solver, 1); row.addWidget(refresh)
            layout.addLayout(row)
            self.table = QtWidgets.QTableWidget(0, 7)
            self.table.setHorizontalHeaderLabels(['Variable', 'Current', 'Unit', 'Model lower', 'Model upper', 'Research name', 'Status'])
            self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
            self.table.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
            self.table.horizontalHeader().setStretchLastSection(True)
            layout.addWidget(self.table, 3)
            self.coordinate_context = QtWidgets.QLabel()
            self.coordinate_context.setWordWrap(True)
            self.coordinate_context.setObjectName('jointCoordinateContext')
            self.coordinate_context.hide()
            self.table.currentCellChanged.connect(self.show_coordinate)
            layout.addWidget(self.coordinate_context)
            row = QtWidgets.QHBoxLayout()
            for text, callback in [('Select in CAD', self.highlight), ('Register / update bounds', self.register),
                                   ('Remove registration', self.remove)]:
                button = QtWidgets.QPushButton(text); button.clicked.connect(callback); row.addWidget(button)
            row.addStretch(); layout.addLayout(row)
            self.responses = QtWidgets.QTableWidget(0, 8)
            self.responses.setHorizontalHeaderLabels(['Response', 'Kind', 'Pair', 'Field / quantity', 'Side / component', 'Increment', 'Reduction', 'Unit'])
            self.responses.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
            self.responses.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
            self.responses.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
            self.responses.cellDoubleClicked.connect(lambda *_: self.edit_response())
            self.responses.horizontalHeader().setStretchLastSection(True)
            layout.addWidget(self.responses, 2)
            row = QtWidgets.QHBoxLayout()
            add = QtWidgets.QPushButton('Add response'); add.clicked.connect(self.add_response)
            remove = QtWidgets.QPushButton('Remove response')
            remove.clicked.connect(self.remove_response)
            edit = QtWidgets.QPushButton('Edit response'); edit.clicked.connect(self.edit_response)
            self.prepare = QtWidgets.QPushButton('Create Numerical Plan…'); self.prepare.clicked.connect(self.plan)
            row.addWidget(add); row.addWidget(edit); row.addWidget(remove); row.addStretch(); row.addWidget(self.method); row.addWidget(self.prepare)
            layout.addLayout(row)
            self.message = QtWidgets.QLabel(); self.message.setWordWrap(True); layout.addWidget(self.message)
            self.refresh()

        def send(self, operation, arguments, accepted):
            if self.busy:
                return
            self.busy = True; self.setEnabled(False)
            def done(result):
                self.busy = False; self.setEnabled(True)
                if result.get('status') == 'FAILED':
                    self.message.setText(result.get('error', {}).get('message', 'Native command failed'))
                else:
                    try:
                        accepted(result)
                    except Exception as error:
                        self.message.setText(str(error))
            try:
                receipt = submit(operation, arguments, {}, done)
                self.capture_id = receipt.get('command_id')
            except Exception as error:
                done({'status': 'FAILED', 'error': {'message': str(error)}})

        def refresh(self, *_):
            if self.busy or self.analysis.currentData() is None:
                return
            from .fem_edit import _native_type
            analysis = owner._object(self.analysis.currentData())
            self.solver.clear()
            for obj in analysis.Group:
                if _native_type(obj) == 'Fem::SolverCcxTools' and not getattr(obj, 'Suppressed', False):
                    self.solver.addItem(obj.Label, obj.Name)
            self.send('pre.research.discover', {'analysis_id': analysis.Name}, self.populate)

        def populate(self, info):
            self.info = info
            self.table.setRowCount(len(info['candidates']))
            for index, row in enumerate(info['candidates']):
                registered = next((r for r in info['registered'] if r['target'] == row['target']), None)
                item = registered or row
                values = [row['label'], item.get('value', row['value']), item['unit'],
                          item.get('lower', ''), item.get('upper', ''), item.get('id', ''),
                          row['diagnostic'] or ('Registered' if registered else 'Select model bounds')]
                for col, value in enumerate(values):
                    cell = QtWidgets.QTableWidgetItem(str(value) if value is not None else '')
                    if col in (0, 1, 6) or not row['writable']:
                        cell.setFlags(cell.flags() & ~QtCore.Qt.ItemIsEditable)
                    self.table.setItem(index, col, cell)
            self.table.resizeColumnsToContents()
            self.show_coordinate()
            self.message.setText('Model limits are saved with CAD; search limits are edited in the Plan.')
            if not self.responses.rowCount():
                pairs = self.pairs()
                self.response_defs = ([{'id': 'force_z', 'kind': 'pair', 'pair_id': pairs[0]['object_id'],
                    'quantity': 'CFN', 'component': 'Z', 'increment': 'final', 'reduction': 'value', 'unit': 'N'}]
                    if pairs else [{'id': 'u_z', 'kind': 'displacement', 'component': 'Z',
                        'increment': 'final', 'reduction': 'max', 'unit': 'mm'}])
                self.render_responses()

        def connect_assembly(self):
            assemblies = [obj for obj in owner.doc.Objects if obj.isDerivedFrom('Assembly::AssemblyObject')]
            if not assemblies:
                self.message.setText('먼저 native Assembly에서 두 인스턴스와 관절을 만드세요.')
                return
            labels = [obj.Label + (' (' + str(i + 1) + ')' if sum(o.Label == obj.Label for o in assemblies) > 1 else '')
                      for i, obj in enumerate(assemblies)]
            label, accepted = QtWidgets.QInputDialog.getItem(self, '조립 형상 연결', '해석에 사용할 조립', labels, 0, False)
            if accepted:
                self.send('pre.research.connect_assembly', {'analysis_id': self.analysis.currentData(),
                    'assembly_id': assemblies[labels.index(label)].Name}, self.populate)

        def show_coordinate(self, *_):
            index = self.table.currentRow()
            row = (self.info or {}).get('candidates', [])
            selected = row[index] if 0 <= index < len(row) else {}
            detail = selected.get('joint_description')
            self.coordinate_context.setVisible(selected.get('target', {}).get('family') == 'joint_coordinate')
            if not detail:
                self.coordinate_context.setText(selected.get('diagnostic') or '')
                return
            axis = detail['axis']
            xyz = ', '.join(format(v, '.6g') for v in axis['axis_direction'])
            origin = ', '.join(format(v, '.6g') for v in axis['axis_origin_mm'])
            limits = detail['native_limits']
            low = '없음' if limits.get('min') is None else format(limits['min'], '.8g')
            high = '없음' if limits.get('max') is None else format(limits['max'], '.8g')
            self.coordinate_context.setText(
                detail['moving'] + ' / 기준 ' + detail['ground'] +
                '\n축 원점 (' + origin + ') mm (문서 전체 좌표)' +
                '\n양의 축 방향 (' + xyz + ')   관절 제한 ' + low + ' … ' + high + ' ' + selected['unit'])
            self.coordinate_context.setToolTip(
                '첫 번째 관절 좌표계(JCS1)에 대한 두 번째 좌표계의 상대 각도 또는 이동량입니다. '
                '원점과 양의 축은 문서 전체 좌표로 표시합니다. 회전은 오른손 방향이며 이동은 JCS1 +Z 방향입니다. '
                '해석 초기 자세이고 FEM 하중이나 변위 조건이 아닙니다.')

        def selected(self):
            index = self.table.currentRow()
            if self.info is None or index < 0:
                raise ValueError('Select a native variable')
            return index, self.info['candidates'][index]

        def highlight(self):
            try:
                _, row = self.selected()
                objects = [{'object_id': row['target']['object_id']}]
                detail = row.get('joint_description')
                if detail:
                    objects.append({'object_id': detail['occurrence_id']})
                self.send('pre.select', {'objects': objects}, lambda _: None)
            except Exception as error:
                self.message.setText(str(error))

        def register(self):
            try:
                index, row = self.selected()
                args = {'analysis_id': self.analysis.currentData(), 'source_stamp': self.info['source_stamp'],
                        'key': row['key'], 'id': self.table.item(index, 5).text().strip(),
                        'label': row['label'], 'unit': self.table.item(index, 2).text().strip(),
                        'lower': float(self.table.item(index, 3).text()), 'upper': float(self.table.item(index, 4).text())}
                self.send('pre.research.register', args, self.populate)
            except Exception as error:
                self.message.setText(str(error))

        def remove(self):
            try:
                index, row = self.selected()
                self.send('pre.research.remove', {'analysis_id': self.analysis.currentData(),
                          'id': self.table.item(index, 5).text()}, self.populate)
            except Exception as error:
                self.message.setText(str(error))

        def pairs(self):
            return [r for r in owner.fem.contact._data()['contacts']
                    if r['analysis_id'] == self.analysis.currentData()
                    and not getattr(owner._object(r['object_id']), 'Suppressed', False)]

        def render_responses(self):
            labels = {row['object_id']: row['draft']['label'] for row in self.pairs()}
            self.responses.setRowCount(len(self.response_defs))
            for row, definition in enumerate(self.response_defs):
                values = [definition['id'],
                    {'pair': 'Pair force', 'contact_field': 'Contact field', 'displacement': 'Displacement'}[definition['kind']],
                    labels.get(definition.get('pair_id'), ''),
                    definition.get('quantity', definition.get('field', 'Displacement')),
                    definition.get('component', {'a': 'A', 'b': 'B', 'both': 'A + B'}.get(definition.get('side'))),
                    'Final' if definition['increment'] == 'final' else str(definition['increment']),
                    definition['reduction'], definition['unit']]
                for col, value in enumerate(values):
                    cell = QtWidgets.QTableWidgetItem(str(value or ''))
                    if col == 2:
                        cell.setToolTip(definition.get('pair_id', 'Whole model'))
                    self.responses.setItem(row, col, cell)
            self.responses.resizeColumnsToContents()

        def add_response(self):
            value = response_dialog(QtWidgets, self.pairs(), parent=self)
            if value:
                if any(row['id'] == value['id'] for row in self.response_defs):
                    self.message.setText('Response name is already used.'); return
                self.response_defs.append(value); self.render_responses()

        def edit_response(self):
            index = self.responses.currentRow()
            if index < 0:
                return
            value = response_dialog(QtWidgets, self.pairs(), self.response_defs[index], self)
            if value:
                if any(row['id'] == value['id'] for i, row in enumerate(self.response_defs) if i != index):
                    self.message.setText('Response name is already used.'); return
                self.response_defs[index] = value; self.render_responses()

        def remove_response(self):
            index = self.responses.currentRow()
            if index >= 0:
                self.response_defs.pop(index); self.render_responses()

        def definitions(self):
            return deepcopy(self.response_defs)

        def plan(self):
            try:
                identifiers = [r['id'] for r in self.info['registered']]
                args = {'analysis_id': self.analysis.currentData(), 'solver_id': self.solver.currentData(),
                        'variable_ids': identifiers, 'responses': self.definitions()}
                operation = 'doe' if self.method.currentIndex() == 0 else 'optimize'
                def prepared(result):
                    create_plan(self.capture_id, operation)
                    self.message.setText('Opening the editable Numerical Plan. No candidate has run.')
                self.send('pre.research.prepare', args, prepared)
            except Exception as error:
                self.message.setText(str(error))
    return Panel()
