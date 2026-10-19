"""Selected native mesh initial conditions, using the existing owner commands.

Qt is injected by FreeCAD. Applying a condition does not run a solver or rewrite
the user's STATIC program. Incomplete text remains part of the saved draft.
"""
from copy import deepcopy
import math
import os
import weakref

from caelab.initial_field_conditions import default_draft
from caelab.storage import canonical_hash


def _value(text):
    if text == '':
        return None
    try:
        value = float(text)
        return value if math.isfinite(value) else text
    except (ValueError, TypeError):
        return text


def add_initial_field_page(host, W, C):
    from . import initial_field_native as native

    class CurrentStack(W.QStackedWidget):
        # QStackedLayout normally reserves the largest hidden editor. A stress
        # table must not inherit the taller compatible-displacement form.
        def __init__(self):
            super().__init__()
            self.layout().setSizeConstraint(W.QLayout.SetNoConstraint)

        def sizeHint(self):
            page = self.currentWidget()
            return page.sizeHint() if page is not None else super().sizeHint()

        def minimumSizeHint(self):
            page = self.currentWidget()
            return page.minimumSizeHint() if page is not None else super().minimumSizeHint()

    class Page(W.QWidget):
        def __init__(self):
            super().__init__()
            self.setObjectName('initialFieldPage')
            if os.name == 'nt':
                font = self.font(); font.setFamily('Malgun Gothic'); font.setPointSizeF(10)
                self.setFont(font)
            self.loading = False; self.modified = False; self.pending = False
            self.loaded_analysis = None; self.current = None; self.selection = None
            self.buffer = default_draft(); self.buffer['states'] = []; self.buffer['temperature']['samples'] = [[0, None]]
            self._saved = None; self._history = []; self._index = -1
            self.static_steps = []; self.native_t = []; self._pending_request = None
            layout = W.QVBoxLayout(self); layout.setContentsMargins(4, 6, 4, 4); layout.setSpacing(8)
            self.analysis_info = self.label('해석 종류 확인 필요')
            layout.addWidget(self.analysis_info)
            form = W.QFormLayout(); form.setFieldGrowthPolicy(W.QFormLayout.AllNonFixedFieldsGrow)
            self.kind = W.QComboBox()
            for text, key in [('온도', 'temperature'), ('초기 응력', 'stress'), ('호환 초기 변형 상태', 'compatible')]:
                self.kind.addItem(text, key)
            self.name = W.QLineEdit(); form.addRow('초기조건 종류', self.kind); form.addRow('조건 이름', self.name)
            layout.addLayout(form)
            self.target_brief = self.label('적용 영역 미선택'); layout.addWidget(self.target_brief)
            self.tabs = W.QTabWidget(); self.tabs.setDocumentMode(True); layout.addWidget(self.tabs, 1)
            target = W.QWidget(); v = W.QVBoxLayout(target); v.setContentsMargins(0, 8, 0, 0); v.setSpacing(8)
            v.addWidget(self.label('메시를 고른 뒤 3D 화면에서 적용 영역을 선택하세요.'))
            self.mesh = W.QComboBox(); self.mesh.setSizeAdjustPolicy(W.QComboBox.AdjustToMinimumContentsLengthWithIcon)
            self.mesh.setMinimumContentsLength(10); v.addWidget(self.mesh)
            row = W.QHBoxLayout()
            self.whole_button = self.button('고체 전체 사용', lambda: self.region(False), row)
            self.selection_button = self.button('3D 선택 사용', lambda: self.region(True), row); v.addLayout(row)
            self.target = self.label('아직 적용 영역을 선택하지 않았습니다.')
            self.target.setStyleSheet('background:#eef3f7;color:#203849;padding:8px;')
            self.target.setMinimumHeight(self.target.fontMetrics().lineSpacing() * 3 + 16)
            v.addWidget(self.target)
            self.scope = self.label(''); v.addWidget(self.scope); v.addStretch(1)
            self.next_button = self.button('값 입력으로', lambda: self.tabs.setCurrentIndex(1), v)
            self.tabs.addTab(target, '적용 영역')
            values = W.QWidget(); v = W.QVBoxLayout(values); v.setContentsMargins(0, 8, 0, 0); v.setSpacing(8)
            self.stack = CurrentStack()
            self.values_scroll = W.QScrollArea(); self.values_scroll.setFrameShape(W.QFrame.NoFrame)
            self.values_scroll.setWidgetResizable(True); self.values_scroll.setMinimumHeight(180)
            self.values_scroll.setWidget(self.stack); v.addWidget(self.values_scroll, 1)
            self.stack.currentChanged.connect(self.stack.updateGeometry)
            thermal = W.QWidget(); tv = W.QVBoxLayout(thermal); tv.setContentsMargins(0, 0, 0, 0); tv.setSpacing(6)
            form = W.QFormLayout()
            self.tmode = W.QComboBox(); self.tmode.addItem('절대 온도', 'absolute'); self.tmode.addItem('온도 증분 ΔT', 'difference')
            self.tunit = W.QComboBox(); self.tunit.addItems(['K', '°C'])
            row = W.QHBoxLayout(); row.addWidget(self.tmode, 1); row.addWidget(self.tunit); form.addRow('입력', row)
            self.reference = W.QLineEdit(); self.runit = W.QComboBox(); self.runit.addItems(['K', '°C'])
            row = W.QHBoxLayout(); row.addWidget(self.reference, 1); row.addWidget(self.runit); form.addRow('응력 없는 기준 온도', row)
            self.alpha = W.QLineEdit(); form.addRow('선팽창 계수 [1/K]', self.alpha); tv.addLayout(form)
            self.temperatures = self.table(['상태', '하중 매개변수', '온도 [K]'])
            self.temperatures.setObjectName('initialTemperatures'); tv.addWidget(self.temperatures, 1)
            tv.addWidget(self.label('초기 온도는 기준 온도와 같아야 합니다. 하중 매개변수는 물리 시간이 아닙니다.'))
            tv.addStretch(1)
            self.stack.addWidget(thermal)
            stress_page = W.QWidget(); sv = W.QVBoxLayout(stress_page); sv.setContentsMargins(0, 0, 0, 0)
            self.sunit = W.QComboBox(); self.sunit.addItems(['MPa', 'Pa', 'kPa', 'GPa'])
            row = W.QHBoxLayout(); row.addWidget(W.QLabel('응력 단위')); row.addWidget(self.sunit); row.addStretch(); sv.addLayout(row)
            self.stress = self.table(['성분', '초기 응력']); self.stress.setObjectName('initialStress'); sv.addWidget(self.stress, 1)
            self.ip_info = self.label(''); sv.addWidget(self.ip_info)
            sv.addWidget(self.label('단일 고체 전체의 초기 응력입니다. 첫 평형에서 재분배될 수 있습니다.'))
            sv.addStretch(1)
            self.stack.addWidget(stress_page)
            compatible_page = W.QWidget(); cv = W.QVBoxLayout(compatible_page); cv.setContentsMargins(0, 0, 0, 0)
            self.compatible_section = W.QComboBox()
            self.compatible_section.addItems(['변위와 변위 구배', '총변형률과 응력'])
            cv.addWidget(self.compatible_section)
            self.compatible_stack = CurrentStack(); cv.addWidget(self.compatible_stack, 1)
            self.compatible_stack.currentChanged.connect(self.compatible_stack.updateGeometry)
            displacement = W.QWidget(); dv = W.QVBoxLayout(displacement); dv.setContentsMargins(0, 0, 0, 0)
            self.origin = self.table(['성분', '기준점 [mm]', '강체 이동 [mm]']); dv.addWidget(self.origin)
            self.gradient = self.table(['변위', '∂u/∂x', '∂u/∂y', '∂u/∂z']); dv.addWidget(self.gradient)
            self.gradient.setToolTip('초기 변위 구배의 각 성분은 무차원 [1]입니다.')
            dv.addStretch(1)
            self.compatible_stack.addWidget(displacement)
            tensors = W.QWidget(); ev = W.QVBoxLayout(tensors); ev.setContentsMargins(0, 0, 0, 0)
            self.csunit = W.QComboBox(); self.csunit.addItems(['MPa', 'Pa', 'kPa', 'GPa'])
            row = W.QHBoxLayout(); row.addWidget(W.QLabel('응력 단위')); row.addWidget(self.csunit); row.addStretch(); ev.addLayout(row)
            self.cstress = self.table(['성분', '총변형률 [1]', '초기 응력'])
            ev.addWidget(self.cstress); ev.addStretch(1); self.compatible_stack.addWidget(tensors)
            cv.addWidget(self.label('Code_Aster의 탄성 초기 상태입니다. 변위 구배·총변형률·응력이 같은 재료와 일치해야 합니다.'))
            self.stack.addWidget(compatible_page)
            self.tabs.addTab(values, '조건 값')
            row = W.QHBoxLayout()
            self.undo_button = self.button('되돌리기', self.undo, row)
            self.redo_button = self.button('다시 실행', self.redo, row)
            self.more_button = W.QToolButton(); self.more_button.setText('기타'); self.more_button.setPopupMode(W.QToolButton.InstantPopup)
            menu = W.QMenu(self.more_button)
            menu.addAction('좌표계…', self.edit_axes); menu.addAction('해석 단계와 외력 배율…', self.edit_states)
            menu.addAction('기존 온도 조건 읽기…', self.import_temperature)
            menu.addSeparator(); menu.addAction('저장된 조건 다시 읽기…', self.reload_saved)
            self.more_button.setMenu(menu); row.addWidget(self.more_button); layout.addLayout(row)
            self.check_request_button = self.button('요청 상태 확인', self.check_request, layout)
            self.check_request_button.setVisible(False)
            row = W.QHBoxLayout()
            self.save_button = self.button('초안 저장', self.store, row)
            self.discard_button = self.button('수정 취소', self.discard, row)
            self.apply_button = self.button('조건 적용', self.apply, row); layout.addLayout(row)
            self.status = self.label('적용 영역과 조건 값을 지정하세요.'); layout.addWidget(self.status)
            self.kind.currentIndexChanged.connect(self.change_kind)
            self.tmode.currentIndexChanged.connect(self.units_changed); self.tunit.currentIndexChanged.connect(self.units_changed)
            self.compatible_section.currentIndexChanged.connect(self.compatible_stack.setCurrentIndex)
            for obj in (self.name, self.reference, self.alpha):
                obj.textChanged.connect(self.mark); obj.installEventFilter(self)
            for obj in (self.mesh, self.runit):obj.currentIndexChanged.connect(self.mark)
            self.sunit.currentIndexChanged.connect(self.stress_units_changed)
            self.csunit.currentIndexChanged.connect(self.stress_units_changed)
            for obj in (self.temperatures, self.stress, self.origin, self.gradient, self.cstress):
                obj.itemChanged.connect(self.mark); obj.installEventFilter(self)
            host.analysis.currentIndexChanged.connect(lambda *_: self.refresh())
            host.tabs.addTab(self, '초기조건'); host.editor._initial_field_page = weakref.ref(self)
            self.load(self.buffer, None)

        def label(self, text):
            obj = W.QLabel(text); obj.setWordWrap(True); obj.setTextFormat(C.Qt.PlainText)
            obj.setSizePolicy(W.QSizePolicy.Preferred, W.QSizePolicy.Maximum)
            return obj

        def button(self, text, callback, layout):
            obj = W.QPushButton(text)
            def invoke():
                try:callback()
                except Exception as error:self.status.setText(str(error))
            obj.clicked.connect(invoke); layout.addWidget(obj)
            return obj

        def table(self, headers):
            obj = W.QTableWidget(0, len(headers)); obj.setHorizontalHeaderLabels(headers)
            obj.verticalHeader().hide(); obj.setSelectionBehavior(W.QAbstractItemView.SelectRows)
            obj.horizontalHeader().setSectionResizeMode(W.QHeaderView.Stretch)
            obj.setMinimumHeight(110); obj.setAlternatingRowColors(True)
            return obj

        def put(self, table, data, readonly=()):
            table.setRowCount(len(data))
            for i, row in enumerate(data):
                for j, value in enumerate(row):
                    item = W.QTableWidgetItem('' if value is None else str(value)); item.setToolTip(item.text())
                    item.setData(C.Qt.UserRole, deepcopy(value))
                    if j in readonly:item.setFlags(item.flags() & ~C.Qt.ItemIsEditable)
                    table.setItem(i, j, item)
            height = table.horizontalHeader().height() + sum(table.rowHeight(i) for i in range(min(len(data), 6))) + 4
            table.setMinimumHeight(height); table.setMaximumHeight(height)
            if data:table.selectRow(0)

        def rows(self, table):
            def get(item):
                if item is None:return None
                original = item.data(C.Qt.UserRole)
                if item.text() == ('' if original is None else str(original)):return deepcopy(original)
                return _value(item.text())
            return [[get(table.item(i, j)) for j in range(table.columnCount())] for i in range(table.rowCount())]

        def field_value(self, widget, original):
            return deepcopy(original) if widget.text() == ('' if original is None else str(original)) else _value(widget.text())

        def combo(self, obj, value, *, data=False):
            index = obj.findData(value) if data else obj.findText(str(value))
            if index < 0:
                obj.addItem(str(value), value); index = obj.count() - 1
            obj.setCurrentIndex(index)

        def units_changed(self, *_):
            prefix = 'ΔT' if self.tmode.currentData() == 'difference' else '온도'
            unit = self.tunit.currentText()
            self.temperatures.horizontalHeaderItem(2).setText(prefix + ' [' + unit + ']')
            self.mark()

        def stress_units_changed(self, *_):
            self.stress.horizontalHeaderItem(1).setText('초기 응력 [' + self.sunit.currentText() + ']')
            self.cstress.horizontalHeaderItem(2).setText('초기 응력 [' + self.csunit.currentText() + ']')
            self.mark()

        def change_kind(self, *_):
            key = self.kind.currentData(); self.stack.setCurrentIndex({'temperature':0, 'stress':1, 'compatible':2}.get(key, 0))
            self.scope.setText({'temperature':'온도: 선택 절점에 적용합니다. 선택하지 않은 절점에는 기준 온도를 사용합니다.',
                'stress':'초기 응력: 단일 고체 전체만 지원합니다. 부분 면 선택으로 적용하지 않습니다.',
                'compatible':'호환 초기 상태: 단일 고체 전체만 지원합니다. 기존 Code_Aster 실행 환경이 별도로 필요합니다.'}.get(key, '저장된 초기조건 종류를 확인하세요.'))
            self.selection_button.setEnabled(key == 'temperature' and not self.pending)
            self.mark()

        def load(self, draft, selection, *, reset_history=True):
            self.loading = True; self.buffer = deepcopy(draft); self.selection = deepcopy(selection)
            self.combo(self.kind, draft['kind'], data=True); self.name.setText(draft['label'])
            self.combo(self.mesh, draft['mesh_id'], data=True) if draft['mesh_id'] is not None else self.mesh.setCurrentIndex(-1)
            t = draft['temperature']; self.combo(self.tmode, t['mode'], data=True)
            for widget, key in ((self.tunit, 'unit'), (self.runit, 'reference_unit')):self.combo(widget, t[key])
            self.reference.setText('' if t['reference_value'] is None else str(t['reference_value']))
            self.alpha.setText('' if t['expansion_per_K'] is None else str(t['expansion_per_K']))
            labels = ['초기 상태'] + [s['label'] for s in draft['states']]
            self.put(self.temperatures, [[labels[i] if i < len(labels) else '추가 상태', *pair] for i, pair in enumerate(t['samples'])], (0,))
            self.combo(self.sunit, draft['stress']['unit'])
            self.put(self.stress, [[k, v] for k, v in zip(('XX', 'YY', 'ZZ', 'XY', 'XZ', 'YZ'), draft['stress']['values'])], (0,))
            ip = draft['stress']['ip_rows']; self.stress.setEnabled(ip is None)
            self.ip_info.setText('원 적분점 응력 ' + str(len(ip)) + '행을 유지합니다. 균일 응력으로 바꾸지 않습니다.' if ip is not None else '표의 균일 응력을 원 적분점에 적용합니다.')
            c = draft['compatible']; self.combo(self.csunit, c['stress_unit'])
            self.put(self.origin, [[k, c['origin_mm'][i], c['translation_mm'][i]] for i, k in enumerate(('X', 'Y', 'Z'))], (0,))
            self.put(self.gradient, [[k, *c['gradient'][i]] for i, k in enumerate(('uX', 'uY', 'uZ'))], (0,))
            self.put(self.cstress, [[k, c['total_strain'][i], c['stress_values'][i]] for i, k in enumerate(('XX', 'YY', 'ZZ', 'XY', 'XZ', 'YZ'))], (0,))
            self.units_changed(); self.stress_units_changed(); self.change_kind(); self.show_target(); self.loading = False
            self.modified = self._saved is not None and self.snapshot() != self._saved
            if reset_history:self._history = [self.snapshot()]; self._index = 0
            self.sync_buttons()

        def draft(self):
            d = deepcopy(self.buffer); key = self.kind.currentData()
            d.update(kind=key, label=self.name.text(), mesh_id=self.mesh.currentData())
            if key in ('temperature', 'stress', 'compatible'):
                # Preserve an unsupported stored solver until the user changes kind.
                if key != self.buffer['kind']:d['solver'] = 'codeaster' if key == 'compatible' else 'calculix'
            if self.selection:
                d['node_ids'] = deepcopy(self.selection['node_ids']); d['element_ids'] = deepcopy(self.selection['element_ids'])
            d['temperature'].update(mode=self.tmode.currentData(), unit=self.tunit.currentText(), reference_unit=self.runit.currentText(),
                reference_value=self.field_value(self.reference, self.buffer['temperature']['reference_value']),
                expansion_per_K=self.field_value(self.alpha, self.buffer['temperature']['expansion_per_K']), samples=[r[1:] for r in self.rows(self.temperatures)])
            d['stress'].update(unit=self.sunit.currentText(), values=[r[1] for r in self.rows(self.stress)])
            d['compatible'].update(origin_mm=[r[1] for r in self.rows(self.origin)], translation_mm=[r[2] for r in self.rows(self.origin)],
                gradient=[r[1:] for r in self.rows(self.gradient)], total_strain=[r[1] for r in self.rows(self.cstress)],
                stress_values=[r[2] for r in self.rows(self.cstress)], stress_unit=self.csunit.currentText())
            return d

        def snapshot(self):return {'draft': self.draft(), 'region': deepcopy(self.selection)}

        def mark(self, *_):
            if self.loading:return
            if _ and isinstance(_[0], W.QTableWidgetItem):
                item = _[0]; table = item.tableWidget(); was_blocked = table.blockSignals(True)
                try:item.setToolTip(item.text())
                finally:table.blockSignals(was_blocked)
            self.modified = True; host._edited(); snap = self.snapshot()
            if self._index < 0 or snap != self._history[self._index]:
                self._history = self._history[:self._index + 1] + [snap]; self._index += 1
            self.status.setText('미적용 편집입니다. 초안 저장은 계산 조건 적용과 별개입니다.'); self.sync_buttons()

        def undo(self):
            if self.pending or self._index <= 0:return
            self._index -= 1; self.restore_history()

        def redo(self):
            if self.pending or self._index + 1 >= len(self._history):return
            self._index += 1; self.restore_history()

        def restore_history(self):
            snap = self._history[self._index]; self.load(snap['draft'], snap['region'], reset_history=False)
            self.modified = snap != self._saved; host._edited(); self.status.setText('편집을 되돌렸습니다. 적용된 조건은 바꾸지 않았습니다.')

        def eventFilter(self, obj, event):
            if event.type() == C.QEvent.KeyPress and event.modifiers() & C.Qt.ControlModifier:
                if event.key() == C.Qt.Key_Z:
                    self.redo() if event.modifiers() & C.Qt.ShiftModifier else self.undo(); return True
                if event.key() == C.Qt.Key_Y:self.redo(); return True
            return super().eventFilter(obj, event)

        def sync_buttons(self):
            self.undo_button.setEnabled(not self.pending and self._index > 0)
            self.redo_button.setEnabled(not self.pending and self._index + 1 < len(self._history))
            for obj in (self.save_button, self.discard_button, self.apply_button, self.whole_button, self.more_button):obj.setEnabled(not self.pending)
            self.selection_button.setEnabled(not self.pending and self.kind.currentData() == 'temperature')
            self.check_request_button.setVisible(bool(self._pending_request and self._pending_request.get('uncertain')))

        def pending_changes(self):return bool(self.pending or (self.modified and self.snapshot() != self._saved))
        def token(self):return canonical_hash({'analysis':self.loaded_analysis, 'snapshot':self.snapshot(), 'pending':self.pending}) if self.modified or self.pending else None

        def refresh(self, load_forms=True):
            aid = host.analysis.currentData()
            if not aid or self.modified or self.pending or (not load_forms and aid == self.loaded_analysis):return
            info = native.read(host.editor, host.editor.owner._object(aid)); self.loaded_analysis = aid
            self.current = info['record']; self.native_t = info['native_temperatures']; self.static_steps = info.get('static_steps', [])
            self.analysis_info.setText('정적 구조 해석의 초기조건' if info.get('default_draft') is not None and self.static_steps else '해석 설정 확인 필요 — 정적 구조 해석만 지원')
            self.loading = True; self.mesh.clear()
            for mesh in info['meshes']:self.mesh.addItem(mesh['label'], mesh['id'])
            self.loading = False
            draft = (self.current or {}).get('draft') or info.get('default_draft')
            if draft is None:
                draft = default_draft(); draft['states'] = []; draft['temperature']['samples'] = [[0, None]]
            selection = (self.current or {}).get('region'); self._saved = {'draft':deepcopy(draft), 'region':deepcopy(selection)}
            self.load(draft, selection); self.modified = False
            applied = (self.current or {}).get('applied')
            status = '적용된 초기조건입니다.' if applied and applied['native_draft'] == draft and applied['region'] == selection else '적용 영역과 조건 값을 확인한 뒤 조건 적용을 누르세요.'
            self.status.setText('\n'.join(info['errors']) or status)

        def show_target(self):
            if not self.selection:
                self.target.setText('아직 적용 영역을 선택하지 않았습니다.'); self.target_brief.setText('적용 영역 미선택'); return
            names = [s['name'] for t in self.selection.get('targets', []) for s in t.get('subelements', [])]
            mesh_label = self.mesh.currentText()
            all_names = ', '.join('면 ' + n[4:] if n.startswith('Face') else '절점 ' + n[6:] if n.startswith('Vertex') else n for n in names)
            region = ', '.join(all_names.split(', ')[:5]) + (' 외 ' + str(len(names) - 5) + '개' if len(names) > 5 else '') if names else '고체 전체'
            self.target.setText(mesh_label + '\n' + region + '\n' + str(len(self.selection['node_ids'])) + ' 절점 / ' + str(len(self.selection['element_ids'])) + ' 요소')
            self.target.setToolTip(mesh_label + '\n' + (all_names or '고체 전체'))
            self.target_brief.setText('적용: ' + self.fontMetrics().elidedText(mesh_label, C.Qt.ElideMiddle, 210) + ' / ' + (str(len(names)) + '개 선택 영역' if names else '고체 전체'))
            self.target_brief.setToolTip(self.target.toolTip())

        def region(self, selected):
            if self.pending:raise ValueError('처리 중인 초기조건 요청을 먼저 확인하세요.')
            if host.analysis.currentData() != self.loaded_analysis:raise ValueError('편집 중인 해석 이름을 다시 선택하세요.')
            choice = native.region(host.editor, host.editor.owner._object(self.loaded_analysis), self.mesh.currentData(), selected=selected)
            self.selection = choice; self.show_target(); self.mark()

        def accept(self, snapshot, result):
            self.current = deepcopy(result['record']); self._saved = deepcopy(snapshot)
            if self.snapshot() == snapshot:self.modified = False; self.status.setText('\n'.join(result['errors']) or '초안을 저장했습니다. 계산 전 조건 적용이 필요합니다.')
            else:self.status.setText('이전 초안을 저장했습니다. 더 최근의 편집은 유지합니다.')

        def _send(self, op, args, done, on_error=None):
            if host.analysis.currentData() != self.loaded_analysis or self.pending:raise ValueError('편집 중인 해석과 처리 중인 요청을 먼저 확인하세요.')
            if getattr(host, '_command_busy', False):raise ValueError('다른 명령을 처리 중입니다. 완료 후 다시 시도하세요.')
            self.pending = True
            request = {'operation':op, 'arguments':deepcopy(args), 'snapshot':self.snapshot(),
                'previous_record':deepcopy(self.current),
                'owner':host.editor.owner, 'session':getattr(host.editor.owner, 'session_id', None),
                'analysis':self.loaded_analysis, 'done':done, 'uncertain':False}
            self._pending_request = request; self.sync_buttons()
            def ok(result):
                if self._pending_request is not request:return
                self.pending = False; self._pending_request = None; self.sync_buttons(); done(result)
            def failed(error):
                if self._pending_request is not request:return
                if getattr(error, 'native_terminal', False):
                    self.pending = False; self._pending_request = None
                    self.status.setText(str(error))
                    if on_error:on_error(error)
                else:
                    request['uncertain'] = True
                    self.status.setText('요청 결과를 확인하지 못했습니다. 원문을 유지합니다. 요청 상태 확인 후 저장·적용·닫기를 계속하세요.')
                    self.status.setToolTip(str(error))
                self.sync_buttons()
            try:host._send(op, args, self.loaded_analysis, on_done=ok, on_error=failed)
            except Exception as error:
                failed(error)

        def check_request(self):
            request = self._pending_request
            if not request or not request['uncertain']:return
            if (host.editor.owner is not request['owner'] or getattr(host.editor.owner, 'closed', False)
                    or getattr(host.editor.owner, 'session_id', None) != request['session']
                    or host.analysis.currentData() != request['analysis']):
                self.status.setText('요청한 모델과 해석으로 돌아가 상태를 확인하세요. 원문과 미확정 요청을 유지합니다.'); return
            try:info = native.read(host.editor, host.editor.owner._object(request['analysis']))
            except Exception as error:
                self.status.setText('요청 상태를 읽지 못했습니다. 연결을 복구한 뒤 다시 확인하세요.'); self.status.setToolTip(str(error)); return
            record = info['record']; op = request['operation']; snap = request['snapshot']; args = request['arguments']
            matches = False
            if op == 'pre.initial.save_draft':
                matches = bool(record and record['draft'] == args['draft'] and record['region'] == args['region'])
            elif op == 'pre.initial.apply':
                applied = (record or {}).get('applied')
                matches = bool(applied and applied['native_draft'] == snap['draft'] and applied['region'] == snap['region']
                    and record['draft'] == snap['draft'] and record['region'] == snap['region'])
            elif op == 'pre.initial.discard':
                applied = (record or {}).get('applied')
                previous = (request['previous_record'] or {}).get('applied')
                matches = (record is None and previous is None) or bool(applied and applied == previous
                    and record['draft'] == applied['native_draft'] and record['region'] == applied['region'])
            if not matches:
                self.status.setText('원 요청의 완료를 아직 확인하지 못했습니다. 자동 재전송하지 않고 현재 편집을 유지합니다.'); return
            self.pending = False; self._pending_request = None; self.sync_buttons()
            request['done'](info)

        def store(self, then=None, on_error=None):
            snap = self.snapshot(); args = {**deepcopy(snap), 'expected_revision':(self.current or {}).get('revision')}
            def done(result):
                self.accept(snap, result)
                if then:then(result)
            self._send('pre.initial.save_draft', args, done, on_error)

        def apply(self):
            def saved(result):
                snap = deepcopy(self._saved)
                # A late save acknowledgement must not apply an earlier draft
                # while a different current draft is displayed.
                if self.snapshot() != snap:
                    self.status.setText('저장 중 편집이 바뀌었습니다. 현재 값을 확인한 뒤 다시 적용하세요.'); return
                def applied(result):
                    self.current = deepcopy(result['record'])
                    if self.snapshot() == snap:self.modified = False; self.refresh()
                    else:self.status.setText('이전 초안이 적용됐습니다. 더 최근의 편집은 유지합니다.')
                self._send('pre.initial.apply', {'expected_revision':result['record']['revision']}, applied)
            self.store(saved)

        def discard(self):
            if self.pending:raise ValueError('처리 중인 초기조건 요청을 먼저 확인하세요.')
            if not self.confirm_discard('수정 취소', '미적용 초기조건 편집을 버리고 마지막 적용값으로 돌아갈까요?'):return
            snap = self.snapshot()
            def done(result):
                self.current = deepcopy(result['record'])
                if self.snapshot() == snap:self.modified = False; self.refresh()
                else:
                    self._saved = {'draft':deepcopy(self.current['draft']), 'region':deepcopy(self.current['region'])} if self.current else None
                    self.status.setText('이전 초안을 취소했습니다. 더 최근의 편집은 유지합니다.')
            self._send('pre.initial.discard', {'expected_revision':(self.current or {}).get('revision')}, done)

        def reload_saved(self):
            if self.pending:raise ValueError('미확정 요청의 상태를 먼저 확인하세요. 현재 원문을 유지합니다.')
            if host.analysis.currentData() != self.loaded_analysis:raise ValueError('편집 중인 해석 이름을 다시 선택하세요.')
            if self.modified and not self.confirm_discard('저장된 조건 다시 읽기',
                    '이 창의 미저장 편집을 버리고 같은 해석의 저장된 초안으로 돌아갈까요?'):return
            modified = self.modified; self.modified = False
            try:self.refresh()
            except Exception:
                self.modified = modified; raise

        def confirm_discard(self, title, text):
            box = W.QMessageBox(self); box.setWindowTitle(title); box.setText(text)
            box.setIcon(W.QMessageBox.Question); box.setStandardButtons(W.QMessageBox.Discard | W.QMessageBox.Cancel)
            box.button(W.QMessageBox.Discard).setText('편집 버리기')
            box.button(W.QMessageBox.Cancel).setText('계속 편집'); box.setDefaultButton(W.QMessageBox.Cancel)
            return box.exec() == W.QMessageBox.Discard

        def dialog(self, title):
            obj = W.QDialog(self); obj.setWindowTitle(title); obj.resize(520, 420)
            layout = W.QVBoxLayout(obj)
            buttons = W.QDialogButtonBox(W.QDialogButtonBox.Ok | W.QDialogButtonBox.Cancel)
            buttons.button(W.QDialogButtonBox.Ok).setText('확인'); buttons.button(W.QDialogButtonBox.Cancel).setText('취소')
            buttons.accepted.connect(obj.accept); buttons.rejected.connect(obj.reject)
            return obj, layout, buttons

        def edit_axes(self):
            dialog, layout, buttons = self.dialog('초기조건 좌표계')
            layout.addWidget(self.label('전역 좌표계에 대한 오른손 직교 단위축의 열벡터입니다. 전단은 공학 전단률이 아닌 텐서 성분입니다.'))
            axes = self.table(['축 X', '축 Y', '축 Z']); self.put(axes, self.buffer['frame']); layout.addWidget(axes, 1); layout.addWidget(buttons)
            if dialog.exec() == W.QDialog.Accepted:self.buffer['frame'] = self.rows(axes); self.mark()

        def edit_states(self):
            dialog, layout, buttons = self.dialog('해석 단계와 외력 배율')
            layout.addWidget(self.label('기존 정적 단계와 순서를 유지합니다. 매개변수는 물리 시간이 아닙니다. 외력 배율은 호환 초기 상태에서 명시해야 합니다.'))
            states = self.table(['상태 이름', '하중 매개변수', '외력 배율'])
            self.put(states, [[r['label'], r['parameter'], r['load_factor']] for r in self.buffer['states']]); layout.addWidget(states, 1)
            source = '\n'.join(str(r.get('label', '')) + ': ' + str(r.get('end', '')) for r in self.static_steps)
            layout.addWidget(self.label('원 해석 단계\n' + source if source else '원 해석 단계 확인 필요')); layout.addWidget(buttons)
            if dialog.exec() == W.QDialog.Accepted:
                self.buffer['states'] = [{'label':states.item(i, 0).text(), 'parameter':r[1], 'load_factor':r[2]} for i, r in enumerate(self.rows(states))]
                self.load(self.draft(), self.selection, reset_history=False); self.mark()

        def import_temperature(self):
            info = native.read(host.editor, host.editor.owner._object(self.loaded_analysis)); options = info['native_temperatures']
            if not options:raise ValueError('현재 해석에 기존 초기 온도 조건이 없습니다.')
            names = [r['label'] for r in options]; name, ok = W.QInputDialog.getItem(self, '기존 온도 조건', '온도 조건', names, 0, False)
            if not ok:return
            source = options[names.index(name)]
            if source['amplitude']:raise ValueError('기존 진폭을 임의 단계로 바꾸지 않습니다. 원 단계별 온도를 직접 입력하세요.')
            d = self.draft(); t = d['temperature']; d.update(kind='temperature', solver='calculix')
            t.update(reference_value=source['reference_K'], reference_unit='K', unit='K', mode='absolute')
            samples = deepcopy(t['samples'])
            if samples:
                samples[0][1] = source['reference_K']
                if len(samples) > 1:samples[-1][1] = source['final_K']
            t['samples'] = samples
            self.load(d, self.selection, reset_history=False); self.mark()
            self.status.setText('기준 온도와 마지막 온도를 읽었습니다. 중간 단계 온도·영역·선팽창 계수를 확인하세요.')

    return Page()
