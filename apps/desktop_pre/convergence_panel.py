"""Native Qt convergence task page; uses the host's Qt and shared owner commands."""
from copy import deepcopy
import importlib

from caelab.calculix_controls import GROUPS, default_draft, draft_errors, tokens
from . import convergence


def add_convergence_page(panel, W, C):
    G = importlib.import_module(W.__package__ + '.QtGui')

    class ValueTable(W.QTableWidget):
        def moveCursor(self, action, modifiers):
            if action in (W.QAbstractItemView.MoveNext, W.QAbstractItemView.MovePrevious):
                delta = 1 if action == W.QAbstractItemView.MoveNext else -1
                for distance in range(1, self.rowCount()+1):
                    row = (self.currentRow()+delta*distance) % self.rowCount()
                    item = self.item(row,1)
                    if item is not None and item.flags() & C.Qt.ItemIsEditable:
                        return self.model().index(row,1)
            return super().moveCursor(action,modifiers)

    class Page(W.QWidget):
        def __init__(self):
            super().__init__()
            self.setObjectName('convergenceSettings')
            self.loaded = None
            self.buffer = default_draft()
            self.info = None
            self.loading = False
            self.modified = False
            self.buffers = {}
            self.errors = []
            layout = W.QVBoxLayout(self)
            layout.setContentsMargins(6, 8, 6, 8)
            self.solver = W.QComboBox()
            self.solver.setSizeAdjustPolicy(W.QComboBox.AdjustToMinimumContentsLengthWithIcon)
            self.solver.setMinimumContentsLength(10)
            self.solver.setAccessibleName('수렴 설정의 CalculiX solver')
            layout.addWidget(self.solver)
            row = W.QHBoxLayout()
            self.group = W.QComboBox()
            for caption, key in [('수렴 허용치', 'field'), ('반복 제한', 'iterations'),
                                 ('증분 조절', 'factors'), ('접촉 line search', 'line_search')]:
                self.group.addItem(caption, key)
            row.addWidget(self.group, 1)
            self.enabled = W.QCheckBox('사용자 지정')
            row.addWidget(self.enabled)
            layout.addLayout(row)
            scope = W.QLabel('FIELD / LINE SEARCH는 Lab 계산 입력에 적용')
            scope.setToolTip('FreeCAD 기본 solver 실행은 Lab의 추가 카드를 사용하지 않습니다. Lab의 입력 준비와 명시 실행을 사용하세요.')
            scope.setWordWrap(True)
            scope.setMinimumWidth(0)
            layout.addWidget(scope)
            self.table = ValueTable(0, 4)
            self.table.setObjectName('convergenceValues')
            self.table.setHorizontalHeaderLabels(['항목', '입력', '기본', '단위'])
            self.table.setSelectionMode(W.QAbstractItemView.SingleSelection)
            self.table.setMinimumSize(0, 230)
            self.table.horizontalHeader().setSectionResizeMode(0, W.QHeaderView.Stretch)
            self.table.setColumnWidth(1, 92)
            self.table.setColumnWidth(2, 68)
            self.table.setColumnWidth(3, 45)
            layout.addWidget(self.table, 1)
            self.description = W.QLabel()
            self.description.setWordWrap(True)
            self.description.setMinimumWidth(0)
            self.description.setSizePolicy(W.QSizePolicy.Ignored, W.QSizePolicy.Preferred)
            layout.addWidget(self.description)
            self.state = W.QLabel()
            self.state.setWordWrap(True)
            self.state.setMinimumWidth(0)
            self.state.setSizePolicy(W.QSizePolicy.Ignored, W.QSizePolicy.Preferred)
            layout.addWidget(self.state)
            row = W.QHBoxLayout()
            self.save_button = W.QPushButton('초안 저장')
            self.apply_button = W.QPushButton('설정 적용')
            self.error_button = W.QPushButton('오류로 이동')
            for b in (self.save_button, self.apply_button, self.error_button):
                row.addWidget(b)
            layout.addLayout(row)
            row = W.QHBoxLayout()
            self.native_button = W.QPushButton('증분값 읽기')
            self.steps_button = W.QPushButton('단계 설정…')
            self.defaults_button = W.QPushButton('기본값 사용')
            for b in (self.native_button, self.defaults_button, self.steps_button):
                row.addWidget(b)
            layout.addLayout(row)
            self.native_button.setToolTip('FreeCAD의 현재 TIME INCREMENTATION 값을 초안에 읽습니다. 자동 적용하지 않습니다.')
            self.defaults_button.setToolTip('선택한 그룹의 입력만 비워 CalculiX 기본값을 사용합니다. 명시 적용 전 계산에 반영되지 않습니다.')
            self.save_button.clicked.connect(lambda: self.send(False))
            self.apply_button.clicked.connect(lambda: self.send(True))
            self.error_button.clicked.connect(self.go_error)
            self.defaults_button.clicked.connect(self.defaults)
            self.native_button.clicked.connect(self.read_native)
            self.steps_button.clicked.connect(lambda: panel.tabs.setCurrentWidget(panel.steps_page))
            self.group.currentIndexChanged.connect(self.show_group)
            self.enabled.toggled.connect(self.changed_enabled)
            self.table.itemChanged.connect(self.changed)
            self.table.currentCellChanged.connect(self.describe)
            self.solver.currentIndexChanged.connect(self.load_solver)
            panel.analysis.currentIndexChanged.connect(lambda *_: self.refresh(load_forms=True))
            panel.tabs.addTab(self, '수렴 설정')

        def refresh(self, *, load_forms=True):
            aid = panel.analysis.currentData()
            previous = self.solver.currentData()
            self.solver.blockSignals(True)
            self.solver.clear()
            if aid:
                analysis = panel.editor.owner._object(aid)
                for obj in analysis.Group:
                    if convergence.native_type(obj) == 'Fem::SolverCcxTools' and not getattr(obj, 'Suppressed', False):
                        self.solver.addItem(str(analysis.Label)+' / '+str(obj.Label), (aid, obj.Name))
            index = next((i for i in range(self.solver.count()) if self.solver.itemData(i) == previous), -1)
            if index >= 0:
                self.solver.setCurrentIndex(index)
            self.solver.blockSignals(False)
            if self.solver.currentData() != self.loaded or load_forms and not self.modified:
                self.load_solver()
            self.sync_actions()

        def load_solver(self, *_):
            key = self.solver.currentData()
            if self.loaded and self.modified:
                self.buffers[tuple(self.loaded)] = deepcopy(self.buffer)
            self.loaded, self.info = key, None
            self.modified = False
            if key:
                try:
                    obj = panel.editor.owner._object(key[1])
                    self.info = convergence.read(panel.editor, obj, key[0])
                    self.buffer = deepcopy(self.buffers.get(tuple(key), self.info['draft']))
                    self.modified = tuple(key) in self.buffers
                except Exception as error:
                    self.state.setText(str(error))
                    self.sync_actions()
                    return
            else:
                self.buffer = default_draft()
            self.show_group()

        def show_group(self, *_):
            self.loading = True
            group = self.group.currentData()
            key = 'time_use' if group in ('iterations', 'factors') else group+'_use'
            self.enabled.setChecked(bool(self.buffer.get(key)))
            specs = GROUPS[group]
            try:
                values = tokens(self.buffer.get(group, ''), len(specs))
            except ValueError:
                values = [''] * len(specs)
            self.table.setRowCount(len(specs))
            for i, (spec, value) in enumerate(zip(specs, values)):
                name, symbol, caption, default, unit, meaning = spec
                for j, text in enumerate((symbol+' '+caption, value,
                                         '—' if default is None else format(default, '.6g'), unit)):
                    item = W.QTableWidgetItem(str(text))
                    item.setToolTip(meaning if j != 1 else value+'\n'+meaning)
                    if j != 1 or name == 'unused':
                        item.setFlags(item.flags() & ~C.Qt.ItemIsEditable)
                    self.table.setItem(i, j, item)
                self.table.setRowHeight(i, max(28, self.table.fontMetrics().height()+10))
            self.loading = False
            self.validate()
            self.describe()

        def describe(self, *_):
            group = self.group.currentData()
            i = self.table.currentRow()
            if i >= 0:
                self.description.setText(GROUPS[group][i][5])
            else:
                self.description.setText({'field':'비율은 무차원입니다. 0.005는 0.5%입니다.',
                    'iterations':'기본 열은 CalculiX 값입니다. 입력 열의 FreeCAD 값을 자동 교체하지 않습니다.',
                    'factors':'증분 크기와 단계 길이는 “단계 설정”에서 지정합니다.',
                    'line_search':'정적 면-면 penalty 접촉 전용입니다. 일반 Newton 옵션이 아닙니다.'}[group])

        def changed_enabled(self, value):
            if self.loading:
                return
            group = self.group.currentData()
            self.buffer['time_use' if group in ('iterations', 'factors') else group+'_use'] = bool(value)
            self.mark()

        def changed(self, item):
            if self.loading or item.column() != 1:
                return
            group = self.group.currentData()
            self.buffer[group] = ','.join(self.table.item(i, 1).text() for i in range(self.table.rowCount()))
            self.mark()

        def mark(self):
            self.modified = True
            panel._edited()
            if self.loaded:
                self.buffers[tuple(self.loaded)] = deepcopy(self.buffer)
            self.validate()

        def validate(self):
            self.errors = draft_errors(self.buffer)
            if not self.errors and self.loaded:
                try:
                    analysis = panel.editor.owner._object(self.loaded[0])
                    procedure, penalty = convergence._context(panel.editor, analysis)
                    convergence.validate_step_controls(convergence._cards(self.buffer), procedure=procedure, penalty=penalty)
                except (ValueError, KeyError, TypeError) as e:
                    self.errors.append({'path':'controls', 'message':str(e)})
            group = self.group.currentData()
            # Error palette is scoped to input cells; text and the error action
            # still convey status for users who do not distinguish the tint.
            blocked = self.table.blockSignals(True)
            for i in range(self.table.rowCount()):
                item = self.table.item(i, 1)
                errors = [e for e in self.errors if e['path'] == group+'.'+str(i)]
                item.setBackground(G.QBrush(G.QColor('#fff1da')) if errors else G.QBrush())
                item.setToolTip('\n'.join(e['message'] for e in errors) or item.text())
            self.table.blockSignals(blocked)
            if self.errors:
                self.state.setText('실행 차단: '+self.errors[0]['message'])
            elif not self.info:
                self.state.setText('해석과 CalculiX 설정을 선택하세요.')
            elif self.modified:
                self.state.setText('미저장 변경 — 적용 전에는 계산에 반영되지 않습니다.')
            elif self.info.get('errors'):
                self.state.setText(self.info['errors'][0]['message'])
            else:
                self.state.setText('적용됨 — Lab 새 계산에 사용' if self.info['applied'] else
                    ('저장된 초안 — 적용 필요' if self.info['source']=='saved_draft' else 'FreeCAD 현재 값 — 보존된 입력'))
            self.sync_actions()

        def sync_actions(self, busy=False):
            busy = busy or bool(getattr(panel, '_command_busy', False))
            active = self.loaded is not None and self.info is not None and not busy
            self.solver.setEnabled(not busy)
            self.group.setEnabled(not busy)
            self.enabled.setEnabled(active)
            self.table.setEnabled(active and self.enabled.isChecked())
            self.save_button.setEnabled(active)
            self.apply_button.setEnabled(active and not self.errors)
            self.error_button.setEnabled(active and bool(self.errors))
            self.defaults_button.setEnabled(active)
            self.native_button.setEnabled(active)
            self.steps_button.setEnabled(not busy)

        def defaults(self):
            self.buffer[self.group.currentData()] = ''
            self.mark()
            self.show_group()

        def read_native(self):
            if self.loaded:
                self.buffer.update(convergence.signature(panel.editor.owner._object(self.loaded[1])))
                self.mark()
                self.show_group()

        def go_error(self):
            if not self.errors:
                return
            parts = self.errors[0]['path'].split('.')
            if parts[0] in GROUPS:
                self.group.setCurrentIndex(self.group.findData(parts[0]))
                if len(parts) == 2 and parts[1].isdigit():
                    self.table.setCurrentCell(int(parts[1]), 1)
                    self.table.setFocus()
                    self.table.editItem(self.table.currentItem())

        def pending_changes(self, analysis_id, solver_id):
            # Do not block an unrelated analysis, but retain edits in a former
            # solver selection until that exact target has been saved/applied.
            key = (analysis_id, solver_id)
            return key in self.buffers or bool(self.modified and tuple(self.loaded or ()) == key)

        def send(self, apply):
            if not self.loaded:
                return
            key = tuple(self.loaded)
            value, serial = deepcopy(self.buffer), panel._edit_serial
            def done(payload):
                # A receipt for a former selection cannot populate another solver.
                if tuple(self.loaded or ()) != key or panel._edit_serial != serial:
                    self.state.setText('이전 선택의 처리가 끝났습니다. 현재 편집은 유지됩니다.')
                    return
                self.info, self.buffer = payload, deepcopy(payload['draft'])
                self.modified = False
                self.buffers.pop(key, None)
                self.show_group()
            try:
                panel._send('pre.fem.convergence_'+('apply' if apply else 'save'),
                            {'analysis_id':key[0], 'draft':value}, key[1], on_done=done)
            except Exception as e:
                self.state.setText(str(e))

    return Page()
