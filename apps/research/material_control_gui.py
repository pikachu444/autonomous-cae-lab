"""Typed mixed-control editing and retained evidence, using existing law contracts.

The legacy elastic compiler remains the implementation of its existing short form.
The law-native form edits the same settings consumed by law_native_history; it
never evaluates a constitutive response or constructs an owner/job.
"""
from copy import deepcopy
import math

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog,
    QDialogButtonBox, QHBoxLayout, QHeaderView, QLabel, QPushButton, QSplitter,
    QTabWidget, QTableWidget, QTableWidgetItem, QTreeWidget, QTreeWidgetItem,
    QVBoxLayout, QWidget)

from .material_control_dialog import MaterialControlDialog
from .material_editing import MaterialTable

F9 = ('xx', 'xy', 'xz', 'yx', 'yy', 'yz', 'zx', 'zy', 'zz')
K6 = ('xx', 'yy', 'zz', 'xy', 'xz', 'yz')
LAWS = {'neo_hooke': 'Neo-Hooke', 'drucker_prager_linear': 'Drucker–Prager',
        'single_branch_maxwell': '단일 분기 Maxwell'}


def shown(value):
    return '—' if value is None else str(value)


def _tree(tree, values):
    """Diagnostic details keep exact source keys and values; no inferred states."""
    tree.clear()
    def add(parent, key, value):
        item = QTreeWidgetItem(parent, [str(key), '' if isinstance(value, (list, dict)) else shown(value)])
        if isinstance(value, dict):
            for name, part in value.items(): add(item, name, part)
        elif isinstance(value, list):
            for index, part in enumerate(value): add(item, index, part)
    for key, value in (values if isinstance(values, dict) else {'원값': values}).items(): add(tree, key, value)
    tree.expandToDepth(0)


class MixedControlDialog(MaterialControlDialog):
    """Same client/settings/result_settings contract as the elastic short form."""
    def __init__(self, client, settings, parent=None):
        self.native = 'initial_state' in settings
        if not self.native:
            super().__init__(client, settings, parent)
            return
        QDialog.__init__(self, parent)
        self.client, self.base = client, deepcopy(settings)
        self.result_settings = None
        self._cancelled = False
        self._worker = None
        self._loading = True
        self._boundary_changed = False
        self.setWindowTitle('혼합 제어 조건')
        self.resize(1160, 720)
        self.setMinimumSize(740, 560)
        layout = QVBoxLayout(self)
        model = settings.get('model')
        measure = '제1 Piola P' if model == 'neo_hooke' else '미소변형 Cauchy σ'
        self.heading = QLabel(f"{LAWS.get(model, model)}  |  {measure} [{settings.get('stress_unit', '—')}]  |  재료 직교좌표")
        self.heading.setWordWrap(True)
        self.heading.setProperty('appearanceRole', 'section')
        layout.addWidget(self.heading)
        self.support = QLabel(self._support_text(model))
        self.support.setWordWrap(True)
        layout.addWidget(self.support)
        row = QHBoxLayout()
        self.mode = QComboBox()
        self.mode.addItem('지정 F', 'prescribed')
        self.mode.addItem('측정한 횡변형 F22/F33', 'measured')
        self.mode.addItem('축 F와 응력 목표', 'mixed')
        row.addWidget(QLabel('시험 조건')); row.addWidget(self.mode, 1)
        self.zero = QPushButton('횡응력 0 입력')
        self.zero.setToolTip('yy와 zz의 모든 시간 목표를 명시적으로 0으로 설정합니다. 초기 수락 상태도 이 목표를 만족해야 합니다.')
        self.zero.clicked.connect(self.set_transverse_zero)
        row.addWidget(self.zero); layout.addLayout(row)
        component_row = QHBoxLayout()
        component_row.addWidget(QLabel('물리 응력 목표 성분'))
        self.controls = {}
        boundary = settings.get('boundary_control')
        boundary = boundary if isinstance(boundary, dict) else {}
        targets = boundary.get('stress_components', {})
        targets = targets if isinstance(targets, dict) else {}
        for name in K6:
            check = QCheckBox(name)
            check.setChecked(name in targets)
            check.toggled.connect(self._controls_changed)
            self.controls[name] = check
            component_row.addWidget(check)
        component_row.addStretch()
        self.all_f = QCheckBox('전체 F 9성분 표시')
        self.all_f.toggled.connect(lambda *_: self._controls_changed())
        component_row.addWidget(self.all_f); layout.addLayout(component_row)
        self.note = QLabel()
        self.note.setWordWrap(True)
        layout.addWidget(self.note)
        self.tabs = QTabWidget(); layout.addWidget(self.tabs, 1)
        self.table = MaterialTable(len(settings.get('time', [])), 1 + 9 + 6)
        self.table.setObjectName('mixedControlHistory')
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setDefaultSectionSize(112)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        self.tabs.addTab(self.table, '시간별 F와 응력 목표')
        gradients = settings.get('deformation_gradient', [])
        for r, time in enumerate(settings.get('time', [])):
            flat = [v for line in gradients[r] for v in line] if r < len(gradients) else []
            values = [time] + (flat if len(flat) == 9 else [''] * 9)
            for name in K6:
                target = targets.get(name, [])
                values.append(target[r] if isinstance(target, list) and r < len(target) else '' if isinstance(target, list) else target)
            for c, value in enumerate(values):
                item = QTableWidgetItem(str(value)); item.setData(Qt.ItemDataRole.UserRole, deepcopy(value))
                self.table.setItem(r, c, item)
        from plugins.material_point import law_native as law
        original_solver = boundary.get('solver', law.BOUNDARY_OPTIONS)
        self.solver_base = deepcopy(original_solver if isinstance(original_solver, dict) else law.BOUNDARY_OPTIONS)
        self.solver = MaterialTable(len(self.solver_base), 2)
        self.solver.setHorizontalHeaderLabels(['수렴 기준', '현재 값'])
        self.solver.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        solver_labels = {'atol': f"절대 잔차 허용값 [{settings.get('stress_unit', '—')}]",
                         'rtol': '상대 잔차 허용값 [1]', 'max_iterations': '최대 Newton 반복',
                         'max_backtracks': '최대 후퇴 횟수'}
        for r, (key, value) in enumerate(self.solver_base.items()):
            label = QTableWidgetItem(solver_labels.get(key, key)); label.setData(Qt.ItemDataRole.UserRole, key)
            label.setFlags(label.flags() & ~Qt.ItemFlag.ItemIsEditable)
            item = QTableWidgetItem(str(value)); item.setData(Qt.ItemDataRole.UserRole, deepcopy(value))
            self.solver.setItem(r, 0, label); self.solver.setItem(r, 1, item)
        self.tabs.addTab(self.solver, '수렴 기준')
        self.initial = QTreeWidget(); self.initial.setHeaderLabels(['초기 수락 상태', '원값'])
        _tree(self.initial, settings.get('initial_state', {}))
        self.initial.setColumnWidth(0, 310)
        self.tabs.addTab(self.initial, '초기 수락 상태')
        row = QHBoxLayout()
        add = QPushButton('행 추가'); remove = QPushButton('선택 행 삭제')
        add.clicked.connect(self.add_row); remove.clicked.connect(self.remove_row)
        row.addWidget(add); row.addWidget(remove); row.addStretch()
        self.check = QPushButton('입력 검사'); self.check.clicked.connect(self.validate_draft)
        row.addWidget(self.check); layout.addLayout(row)
        self.message = QLabel('조건을 편집해 초안에 적용하세요. 계산은 실행하지 않습니다.')
        self.message.setTextFormat(Qt.TextFormat.PlainText)
        self.message.setWordWrap(True); self.message.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.message)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText('초안에 적용')
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setProperty('appearanceRole', 'primary')
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('취소')
        self.buttons.accepted.connect(self._compile); self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self.table.pasteRejected.connect(self.message.setText)
        self.table.itemChanged.connect(self._edited)
        self.table.editBatchFinished.connect(self._edited)
        self.solver.itemChanged.connect(self._solver_edited)
        self.solver.editBatchFinished.connect(self._solver_edited)
        self.mode.setCurrentIndex(self.mode.findData('mixed' if targets else 'prescribed'))
        self.mode.currentIndexChanged.connect(self._mode_changed)
        self._controls_changed()
        self._loading = False

    @staticmethod
    def _support_text(model):
        limits = {'neo_hooke': '유한변형: 주신장비 0.5–2, det(F)>0. 탄성 상태이며 내부 변수는 없습니다.',
                  'drucker_prager_linear': '미소변형: Kelvin 성분 |ε|≤0.05, ‖F−Fᵀ‖≤0.15. 소성 상태를 증분 사이에 보존합니다.',
                  'single_branch_maxwell': '미소변형: 물리 변형률 성분 |ε|≤0.01. 실제 Δt [s]와 점성 상태를 사용합니다.'}
        return limits.get(model, '이 법칙의 지원 범위는 실행 전 입력 검사에서 확인합니다.') + ' 실행환경과 공학 적합성은 별도 확인이 필요합니다.'

    def _edited(self, *_):
        self._boundary_changed |= any(self.table.item(r, c).text() != str(self.table.item(r, c).data(Qt.ItemDataRole.UserRole))
                                      for r in range(self.table.rowCount()) for c in range(10, 16)
                                      if self.table.item(r, c) is not None)
        self.message.setText('편집한 조건은 아직 초안에 적용하지 않았습니다. 입력 검사로 실행 가능 여부를 확인하세요.')

    def _solver_edited(self, *_):
        self._boundary_changed = True
        self._edited()

    def _mode_changed(self, *_):
        self._boundary_changed = True
        if self.mode.currentData() != 'mixed':
            for control in self.controls.values():
                control.blockSignals(True); control.setChecked(False); control.blockSignals(False)
        self._controls_changed()
        if self.mode.currentData() == 'measured' and self.table.rowCount():
            self.table.setCurrentCell(min(max(self.table.currentRow(), 0), self.table.rowCount()-1), 5)
            self.table.setFocus()

    def _controls_changed(self, *_):
        if not hasattr(self, 'table'): return
        if _ and not self._loading: self._boundary_changed = True
        blocked = self.table.blockSignals(True)
        names = [name for name, check in self.controls.items() if check.isChecked()]
        if names and self.mode.currentData() != 'mixed':
            self.mode.blockSignals(True); self.mode.setCurrentIndex(self.mode.findData('mixed')); self.mode.blockSignals(False)
        self.zero.setEnabled(self.mode.currentData() == 'mixed')
        headers = [f"시간 [{self.base.get('time_unit', '—')}]"]
        headers += [f"F{1+F9.index(name)//3}{1+F9.index(name)%3}" + (' 제어 [1]' if name in names else ' 지정 [1]') for name in F9]
        headers += [f"{'P' if self.base.get('model') == 'neo_hooke' else 'σ'} {name} 목표 [{self.base.get('stress_unit', '—')}]" for name in K6]
        self.table.setHorizontalHeaderLabels(headers)
        self.table.setColumnWidth(0, 84)
        for c, name in enumerate(F9, 1):
            nonzero = False
            if name[0] != name[1]:
                for r in range(self.table.rowCount()):
                    try: nonzero |= float(self.table.item(r, c).text()) != 0.
                    except (ValueError, AttributeError): nonzero = True
            self.table.setColumnHidden(c, not (self.all_f.isChecked() or name[0] == name[1] or name in names or nonzero))
            self.table.setColumnWidth(c, 108)
        for r in range(self.table.rowCount()):
            for c, name in enumerate(F9, 1):
                item = self.table.item(r, c)
                if item is None: continue
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable if name in names else item.flags() | Qt.ItemFlag.ItemIsEditable)
                item.setToolTip('이 성분은 직전 수락 F에서 Newton 반복을 시작해 결정합니다. 저장된 F 원값을 표시합니다.' if name in names else '지정한 F 원값 [1]')
        for i, name in enumerate(K6):
            self.table.setColumnHidden(10+i, name not in names)
            self.table.setColumnWidth(10+i, 125)
        self.note.setText('응력 제어 F는 직전 수락 F에서 풀며 저장된 원값을 표시합니다. 첫 행은 초기 수락 상태 검사만 수행하며 목표와의 차이가 원 절대 허용값 이내여야 합니다.' if names else
                          '모든 F 성분을 그대로 지정합니다. 측정한 횡변형도 해당 F22/F33에 입력하세요. 횡방향 자유 조건은 응력 목표로 명시해야 합니다.')
        self.table.blockSignals(blocked)

    def set_transverse_zero(self):
        for name in ('yy', 'zz'):
            self.controls[name].setChecked(True)
            for row in range(self.table.rowCount()): self.table.item(row, 10+K6.index(name)).setText('0')
        self._controls_changed()
        self.message.setText('횡응력 yy/zz 목표를 0으로 입력했습니다. 원 초기 수락 상태는 변경하지 않았습니다.')

    def add_row(self):
        self._boundary_changed = True
        row = self.table.rowCount(); self.table.insertRow(row)
        for column in range(self.table.columnCount()): self.table.setItem(row, column, QTableWidgetItem(''))
        self._controls_changed()
        self.table.setCurrentCell(row, 0); self.table.setFocus()

    def remove_row(self):
        self._boundary_changed = True
        rows = sorted({i.row() for i in self.table.selectedIndexes()}, reverse=True)
        for row in rows: self.table.removeRow(row)

    def draft_settings(self):
        from .material_window import edited_number
        focus = QApplication.focusWidget()
        if focus and (self.table.isAncestorOf(focus) or self.solver.isAncestorOf(focus)): focus.clearFocus()
        draft = deepcopy(self.base)
        def number(item):
            original = item.data(Qt.ItemDataRole.UserRole)
            return deepcopy(original) if str(original) == item.text() else edited_number(item.text())
        values = [[number(self.table.item(r, c)) for c in range(self.table.columnCount())]
                  for r in range(self.table.rowCount())]
        draft['time'] = [v[0] for v in values]
        draft['deformation_gradient'] = [[v[1:4], v[4:7], v[7:10]] for v in values]
        names = [name for name, check in self.controls.items() if check.isChecked()]
        if not self._boundary_changed and 'boundary_control' in self.base:
            draft['boundary_control'] = deepcopy(self.base['boundary_control'])
        elif names:
            solver = {}
            for r in range(self.solver.rowCount()):
                key = self.solver.item(r, 0).data(Qt.ItemDataRole.UserRole)
                value = number(self.solver.item(r, 1))
                # Integer limits remain typed integers, incomplete text remains text.
                if key in ('max_iterations', 'max_backtracks') and isinstance(value, float) and value.is_integer(): value = int(value)
                solver[key] = value
            draft['boundary_control'] = dict(stress_components={name: [v[10+K6.index(name)] for v in values] for name in names}, solver=solver)
        else:
            draft.pop('boundary_control', None)
        return draft

    def validate_draft(self):
        from plugins.material_point.law_native import validate_settings
        draft = self.draft_settings()
        try:
            validate_settings(draft)
        except Exception as error:
            issue = self._numeric_issue(draft, str(error))
            if issue:
                row, column, label = issue
                time = draft['time'][row]
                when = f" (시각 {time} {draft.get('time_unit', '—')})" if column != 0 else ''
                value = self.table.item(row, column).text()
                self.tabs.setCurrentWidget(self.table)
                self.table.setColumnHidden(column, False)
                self.table.clearSelection(); self.table.setCurrentCell(row, column)
                self.table.item(row, column).setSelected(True)
                self.table.scrollToItem(self.table.item(row, column)); self.table.setFocus()
                self.message.setText(f"{row + 1}행{when}의 {label}에 완성된 숫자를 입력하세요. 현재 값: ‘{value}’.\n미완성 초안은 적용하고 저장할 수 있습니다.")
            else:
                self.message.setText('실행 전 입력을 확인하세요. 미완성 초안은 적용하고 저장할 수 있습니다.\n' + str(error))
            self.message.setToolTip(str(error))
            return False
        self.message.setText('입력 형식과 법칙별 범위를 확인했습니다. 초기 응력 평형과 실행환경은 실제 계산에서 확인합니다.')
        self.message.setToolTip('')
        return True

    def _numeric_issue(self, draft, error):
        """Locate only a recognized numeric error with the exact expected shape.

        A shape mismatch or unrelated producer error retains its original text;
        it must not be guessed into a cell correction.
        """
        times = draft.get('time')
        if not isinstance(times, list): return None
        n = len(times)
        def invalid(value):
            return type(value) not in (int, float) or not math.isfinite(value)
        def recognized(name, shape):
            return error in (f'{name}: require finite numeric shape {shape}; no text/bool',
                             f'{name}: nonfinite value')
        if recognized('time', (n,)):
            return next(((r, 0, f"시간 [{draft.get('time_unit', '—')}]") for r, value in enumerate(times) if invalid(value)), None)
        if recognized('F history', (n, 3, 3)):
            gradients = draft.get('deformation_gradient')
            if (not isinstance(gradients, list) or len(gradients) != n or
                    any(not isinstance(F, list) or len(F) != 3 or any(not isinstance(line, list) or len(line) != 3 for line in F) for F in gradients)):
                return None
            return next(((r, 1 + 3*i+j, f'F{i+1}{j+1} [1]') for r, F in enumerate(gradients)
                         for i, line in enumerate(F) for j, value in enumerate(line) if invalid(value)), None)
        boundary = draft.get('boundary_control')
        targets = boundary.get('stress_components') if isinstance(boundary, dict) else None
        if not isinstance(targets, dict): return None
        for name in K6:
            values = targets.get(name)
            if recognized('controlled ' + name, (n,)) and isinstance(values, list) and len(values) == n:
                measure = 'P' if draft.get('model') == 'neo_hooke' else 'σ'
                return next(((r, 10 + K6.index(name), f"{measure} {name} 목표 [{draft.get('stress_unit', '—')}]")
                             for r, value in enumerate(values) if invalid(value)), None)
        return None

    def _compile(self):
        if not self.native:
            return super()._compile()
        self.result_settings = self.draft_settings()
        self.accept()


class MixedControlResultDialog(QDialog):
    """Inspect the producer's retained Newton and accepted-state evidence only."""
    def __init__(self, result, settings, parent=None):
        super().__init__(parent)
        self.setWindowTitle('혼합 제어 수렴과 수락 상태'); self.resize(1120, 760); self.setMinimumSize(740, 560)
        self.result, self.settings = deepcopy(result), deepcopy(settings)
        diagnostics = result.get('diagnostics', {})
        self.records = diagnostics.get('constitutive_increments', [])
        self.failure = diagnostics.get('failed_increment')
        layout = QVBoxLayout(self)
        declaration = diagnostics.get('declaration', {})
        measure = {'first_Piola': '제1 Piola P', 'infinitesimal_Cauchy': '미소변형 Cauchy σ'}.get(declaration.get('stress_measure'), '응력 측도 미기록')
        self.summary = QLabel(f"{LAWS.get(settings.get('model'), settings.get('model'))} | {measure} [{declaration.get('stress_unit', settings.get('stress_unit', '—'))}] | 수락 {len(self.records)}개 증분" + (' | 실패 증분 보존' if self.failure else ''))
        self.summary.setWordWrap(True); layout.addWidget(self.summary)
        self.increment = QComboBox()
        for record in self.records: self.increment.addItem(f"증분 {record['increment']} — {record['time']} {record.get('time_unit', settings.get('time_unit', '—'))} — 수락", record['increment'])
        if self.failure: self.increment.addItem(f"증분 {self.failure['increment']} — {self.failure['time']} {settings.get('time_unit', '—')} — 실패 / 수락 안 됨", self.failure['increment'])
        layout.addWidget(self.increment)
        self.message = QLabel(); self.message.setWordWrap(True); layout.addWidget(self.message)
        self.tabs = QTabWidget(); layout.addWidget(self.tabs, 1)
        self.residual = QTableWidget(0, 3); self.residual.setHorizontalHeaderLabels(['응력 성분', '목표', '실제 응력'])
        self.residual.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.residual.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.tabs.addTab(self.residual, '경계 수렴')
        self.states = QTreeWidget(); self.states.setHeaderLabels(['수락 상태와 trial', '보존값']); self.states.setColumnWidth(0, 340)
        self.tabs.addTab(self.states, '상태 원값')
        self.trace = QTreeWidget(); self.trace.setHeaderLabels(['Newton 반복 / 실패 진단', '보존값']); self.trace.setColumnWidth(0, 340)
        self.tabs.addTab(self.trace, '반복과 실패 진단')
        self.increment.currentIndexChanged.connect(self._select)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.button(QDialogButtonBox.StandardButton.Close).setText('닫기')
        buttons.rejected.connect(self.reject); layout.addWidget(buttons)
        self._select()

    def _select(self, *_):
        index = self.increment.currentData()
        record = next((r for r in self.records if r['increment'] == index), None)
        failed = self.failure if self.failure and self.failure['increment'] == index else None
        self.residual.setRowCount(0)
        if record is None:
            self.message.setText(('이 증분은 수락되지 않았습니다. 마지막 수락 상태와 원 실패 진단을 확인하세요.\n' + str(failed.get('error', failed.get('message', '')))) if failed else '보존된 증분이 없습니다.')
            _tree(self.states, {'마지막 수락 상태': (failed or {}).get('last_accepted_state')})
            _tree(self.trace, failed or {})
            if failed: self.tabs.setCurrentWidget(self.states)
            return
        boundary = record.get('boundary')
        targets = self.settings.get('boundary_control', {}).get('stress_components', {})
        self.message.setText(f"경계 Newton 반복 {shown(boundary.get('iterations'))} | 최대 절대 잔차 {shown(boundary.get('residual'))} / 허용값 {shown(boundary.get('tolerance'))} [{self.settings.get('stress_unit', '—')}]" if boundary else
                             '초기 수락 상태 검사: 경계 Newton을 수행하지 않았습니다. 초기 응력과 목표의 차이를 절대 허용값으로 확인합니다.' if index == 0 and targets else
                             '초기 수락 상태입니다. 경계 Newton을 수행하지 않았습니다.' if index == 0 else
                             '모든 F를 지정한 증분입니다. 경계 Newton 잔차는 생성되지 않았습니다.')
        for row, name in enumerate(targets):
            self.residual.insertRow(row)
            i, j = ('xyz'.index(c) for c in name)
            stress = record.get('stress_tensor')
            actual = stress[i][j] if isinstance(stress, list) else None
            for col, cell in enumerate((name, targets[name][index], actual)):
                self.residual.setItem(row, col, QTableWidgetItem(shown(cell)))
        _tree(self.states, {'증분 시작 수락 상태': record.get('initial_state'), 'trial 상태': record.get('trial_state'), '수락 상태': record.get('committed_state'), '실제 F': record.get('F')})
        _tree(self.trace, {'경계 반복': boundary, 'local 진단': record.get('local')})
