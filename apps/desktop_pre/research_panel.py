"""Compact native Analysis variables/response worksheet, using existing commands."""
from copy import deepcopy
import re


def _variable_label(row):
    field = row['target'].get('field')
    names = {'Length': '길이', 'Width': '폭', 'Height': '높이', 'Radius': '반지름',
             'Diameter': '지름', 'Angle': '각도', 'YoungsModulus': '탄성계수',
             'PoissonRatio': '푸아송 비', 'Force': '힘', 'xDisplacement': 'X 변위',
             'yDisplacement': 'Y 변위', 'zDisplacement': 'Z 변위',
             'normal_stiffness_MPa_per_mm': '법선 강성',
             'stick_stiffness_MPa_per_mm': '접선 강성', 'friction_coefficient': '마찰계수'}
    label = row['label']
    if field in names and label.endswith(' / ' + field):
        return label[:-len(field)] + names[field]
    return label


def response_dialog(QtWidgets, pairs, definition=None, parent=None):
    """Select an actual supported channel; dimensional units follow that channel."""
    dialog = QtWidgets.QDialog(parent)
    dialog.setWindowTitle('해석 응답 선택')
    layout = QtWidgets.QVBoxLayout(dialog)
    form = QtWidgets.QFormLayout()
    name = QtWidgets.QLineEdit((definition or {}).get('id', 'response'))
    name.setObjectName('responseName')
    kind = QtWidgets.QComboBox(); kind.setObjectName('responseKind')
    kind.addItem('변위', 'displacement')
    if pairs:
        kind.addItem('접촉 쌍의 힘', 'pair')
        kind.addItem('접촉면 결과', 'contact_field')
    pair = QtWidgets.QComboBox(); pair.setObjectName('responsePair')
    for row in pairs:
        pair.addItem(row['draft']['label'], row['object_id'])
    field, component, reduction = (QtWidgets.QComboBox() for _ in range(3))
    field.setObjectName('responseField'); component.setObjectName('responseComponent')
    reduction.setObjectName('responseReduction')
    frame = QtWidgets.QComboBox(); frame.addItems(['마지막 증분', '저장된 증분 선택'])
    frame.setObjectName('responseFrame')
    index = QtWidgets.QSpinBox(); index.setRange(0, 1000000); index.setObjectName('responseFrameIndex')
    increment = QtWidgets.QWidget(); increment_layout = QtWidgets.QHBoxLayout(increment)
    increment_layout.setContentsMargins(0, 0, 0, 0)
    increment_layout.addWidget(frame); increment_layout.addWidget(index)
    unit, scope = QtWidgets.QLabel(), QtWidgets.QLabel()
    unit.setObjectName('responseUnit'); scope.setWordWrap(True)
    name.setToolTip('계산 계획에서 쓸 짧은 영문 이름입니다. 예: force_z, gap_max')
    for label, widget in [('응답 이름', name), ('결과 종류', kind), ('접촉 쌍', pair),
                          ('물리량', field), ('성분 또는 면', component), ('증분', increment),
                          ('값 추출 방법', reduction), ('단위', unit)]:
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
            choices(field, [('접촉 압력 (CPRESS)', 'CPRESS'), ('솔버 간극 (COPEN)', 'COPEN'),
                ('미끄럼 1 (CSLIP1)', 'CSLIP1'), ('미끄럼 2 (CSLIP2)', 'CSLIP2'), ('전단 응력 1 (CSHEAR1)', 'CSHEAR1'),
                ('전단 응력 2 (CSHEAR2)', 'CSHEAR2'), ('형상에서 구한 간극', 'GeomGap_mm')])
            choices(component, [('A 면', 'a'), ('B 면', 'b'), ('양쪽 면', 'both')])
            choices(reduction, [('최댓값', 'max'), ('최솟값', 'min'), ('평균', 'mean'), ('절점별 값', 'field')])
            scope.setText('공통 절점에 투영한 값입니다. 형상에서 구한 간극과 솔버의 COPEN은 별도 결과입니다.')
        else:
            choices(field, [('접촉력 (CFN)', 'CFN'), ('전체 힘 (CF)', 'CF'), ('전단력 (CFS)', 'CFS')]
                    if selected == 'pair' else [('변위', 'displacement')])
            choices(component, [(axis, axis) for axis in 'XYZ']); set_value(component, 'Z')
            choices(reduction, [('선택한 증분의 값', 'value'), ('모든 저장 증분의 이력', 'series')]
                    if selected == 'pair' else [('최댓값', 'max'), ('최솟값', 'min'), ('평균', 'mean'), ('절점별 값', 'field')])
            scope.setText('A 면에 작용하는 접촉 쌍의 합력이며 문서 전체 좌표의 성분입니다. 하중 계수는 무차원입니다.'
                          if selected == 'pair' else '마지막 저장 증분의 절점 변위를 문서 전체 좌표의 성분으로 읽습니다.')
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
            error.setText('영문 소문자로 시작하고 소문자, 숫자, 밑줄을 사용하세요. 최대 48자입니다.')
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
            self.method.addItems(['실험계획 (DOE)', '최적화'])
            from .fem_edit import _native_type
            for obj in owner.doc.Objects:
                if _native_type(obj) == 'Fem::FemAnalysis':
                    self.analysis.addItem(obj.Label, obj.Name)
            connect = QtWidgets.QPushButton('조립 형상 연결…')
            connect.setObjectName('connectAssemblyAnalysis')
            connect.clicked.connect(self.connect_assembly)
            row.addWidget(connect)
            refresh = QtWidgets.QPushButton('새로고침')
            refresh.clicked.connect(self.refresh)
            self.analysis.currentIndexChanged.connect(self.refresh)
            row.addWidget(QtWidgets.QLabel('해석')); row.addWidget(self.analysis, 2)
            row.addWidget(QtWidgets.QLabel('솔버')); row.addWidget(self.solver, 1); row.addWidget(refresh)
            layout.addLayout(row)
            layout.addWidget(QtWidgets.QLabel('변경할 모델 변수'))
            self.table = QtWidgets.QTableWidget(0, 7)
            self.table.setHorizontalHeaderLabels(['모델 변수', '현재값', '단위', '허용 하한', '허용 상한', '계산 변수명', '등록 상태'])
            self.table.verticalHeader().hide()
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
            for text, callback in [('모델에서 선택', self.highlight), ('변수 등록 / 변경', self.register),
                                   ('등록 해제', self.remove)]:
                button = QtWidgets.QPushButton(text); button.clicked.connect(callback); row.addWidget(button)
            row.addStretch(); layout.addLayout(row)
            layout.addWidget(QtWidgets.QLabel('비교할 해석 응답'))
            self.responses = QtWidgets.QTableWidget(0, 8)
            self.responses.setHorizontalHeaderLabels(['응답 이름', '결과 종류', '접촉 쌍', '물리량', '성분 또는 면', '증분', '값 추출 방법', '단위'])
            self.responses.verticalHeader().hide()
            self.responses.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
            self.responses.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
            self.responses.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
            self.responses.cellDoubleClicked.connect(lambda *_: self.edit_response())
            self.responses.horizontalHeader().setStretchLastSection(True)
            layout.addWidget(self.responses, 2)
            row = QtWidgets.QHBoxLayout()
            add = QtWidgets.QPushButton('응답 추가…'); add.clicked.connect(self.add_response)
            remove = QtWidgets.QPushButton('응답 제거')
            remove.clicked.connect(self.remove_response)
            edit = QtWidgets.QPushButton('응답 편집…'); edit.clicked.connect(self.edit_response)
            self.prepare = QtWidgets.QPushButton('계산 계획 만들기…'); self.prepare.clicked.connect(self.plan)
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
                    self.message.setText(result.get('error', {}).get('message', '요청을 완료하지 못했습니다.'))
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
                current = item.get('value', row['value'])
                values = [_variable_label(row), format(current, '.12g') if isinstance(current, (int, float)) else current, item['unit'],
                          item.get('lower', ''), item.get('upper', ''), item.get('id', ''),
                          row['diagnostic'] or ('등록됨' if registered else '하한과 상한 입력')]
                for col, value in enumerate(values):
                    cell = QtWidgets.QTableWidgetItem(str(value) if value is not None else '')
                    cell.setToolTip(str(current) if col == 1 else row['label'] if col == 0 else cell.text())
                    if col in (0, 1, 6) or not row['writable']:
                        cell.setFlags(cell.flags() & ~QtCore.Qt.ItemIsEditable)
                    self.table.setItem(index, col, cell)
            self.table.resizeColumnsToContents()
            self.show_coordinate()
            self.message.setText('허용 범위는 CAD와 함께 저장합니다. 이 범위 안의 탐색 조건은 계산 계획에서 정합니다.')
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
                raise ValueError('모델 변수 표에서 변경할 항목을 선택하세요.')
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
                    {'pair': '접촉 쌍의 힘', 'contact_field': '접촉면 결과', 'displacement': '변위'}[definition['kind']],
                    labels.get(definition.get('pair_id'), ''),
                    definition.get('quantity', definition.get('field', '변위')),
                    definition.get('component', {'a': 'A', 'b': 'B', 'both': 'A + B'}.get(definition.get('side'))),
                    '마지막' if definition['increment'] == 'final' else str(definition['increment']),
                    {'max': '최댓값', 'min': '최솟값', 'mean': '평균', 'field': '절점별 값',
                     'value': '선택 증분', 'series': '증분 이력'}.get(definition['reduction'], definition['reduction']), definition['unit']]
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
                    self.message.setText('이미 사용 중인 응답 이름입니다.'); return
                self.response_defs.append(value); self.render_responses()

        def edit_response(self):
            index = self.responses.currentRow()
            if index < 0:
                return
            value = response_dialog(QtWidgets, self.pairs(), self.response_defs[index], self)
            if value:
                if any(row['id'] == value['id'] for i, row in enumerate(self.response_defs) if i != index):
                    self.message.setText('이미 사용 중인 응답 이름입니다.'); return
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
                    self.message.setText('계산 계획을 열었습니다. 입력을 확인한 뒤 계획 창에서 계산을 실행하세요.')
                self.send('pre.research.prepare', args, prepared)
            except Exception as error:
                self.message.setText(str(error))
    return Panel()
