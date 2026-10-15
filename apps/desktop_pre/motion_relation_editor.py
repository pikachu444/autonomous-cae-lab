"""Contextual native Qt relation editor; injected Qt, no FreeCAD import.

All edits remain in the parent's existing editor snapshot/dirty gate. The source
picker stages a copy and commits on explicit confirmation, never on selection.
There is no new document owner, timer, solver, save service or reconnect policy.
"""
from copy import deepcopy
import math

from apps.desktop_pre.motion_formula import compile_drives, UNITS
from apps.desktop_pre.motion_history import _expression_value
from apps.desktop_pre.motion_relation import binding_problem, relation_values, UNIT_CHOICES


def empty_relation():
    return {'expression': '', 'sources': [], 'constants': []}


class RelationEditor:
    """Selected-drive property widget. context() and scope() are read-only."""
    def __init__(self, QtCore, QtWidgets, *, changed, context, scope):
        self.C, self.Q = QtCore, QtWidgets
        self.changed, self.context, self.scope = changed, context, scope
        self._loading = False
        self._value = empty_relation()
        self._dialog = None
        self.widget = QtWidgets.QWidget()
        self.widget.setObjectName('CAELabMotionRelationEditor')
        layout = QtWidgets.QVBoxLayout(self.widget)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(8)
        form = QtWidgets.QFormLayout()
        form.setFieldGrowthPolicy(QtWidgets.QFormLayout.AllNonFixedFieldsGrow)
        form.setRowWrapPolicy(QtWidgets.QFormLayout.WrapLongRows)
        self.expression = QtWidgets.QLineEdit()
        self.expression.setPlaceholderText('예: 0.5*A+B 또는 amplitude*sin(A)+B')
        self.expression.setAccessibleName('관계식')
        form.addRow('관계식', self.expression)
        layout.addLayout(form)
        self.expression.textEdited.connect(self._expression_changed)
        self.sources = self._table(['식 이름', '기준 구동', '단위', '식 값', '확인'], layout)
        self.sources.setAccessibleName('관계식 기준 구동')
        self.sources.setColumnWidth(0, 70); self.sources.setColumnWidth(1, 220)
        self.sources.setColumnWidth(2, 55); self.sources.setColumnWidth(3, 90)
        self.source_buttons = self._actions(layout, (
            ('기준 추가', self.add_source), ('다시 선택', self.choose_source),
            ('단위 확인', self.confirm_unit), ('기준 삭제', lambda: self.remove('sources')),
            ('위로', lambda: self.move('sources', -1)), ('아래로', lambda: self.move('sources', 1))))
        self.source_notice = QtWidgets.QLabel()
        self.source_notice.setWordWrap(True); layout.addWidget(self.source_notice)
        self.sources.currentCellChanged.connect(lambda *args: self._selection_notice())
        self.sources.cellDoubleClicked.connect(lambda row, column: self.choose_source() if column != 0 else None)
        self.constants = self._table(['상수 이름', '값', '단위'], layout)
        self.constants.setAccessibleName('관계식 상수')
        self.constants.setColumnWidth(0, 140); self.constants.setColumnWidth(1, 125)
        self._actions(layout, (('상수 추가', self.add_constant), ('상수 삭제', lambda: self.remove('constants')),
            ('상수 위로', lambda: self.move('constants', -1)), ('상수 아래로', lambda: self.move('constants', 1))))
        note = QtWidgets.QLabel('sin/cos에는 각도, arctan에는 무차원 비율을 사용합니다. time은 초입니다.')
        note.setWordWrap(True); layout.addWidget(note)

    def _table(self, headers, layout):
        table = self.Q.QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setSelectionBehavior(self.Q.QAbstractItemView.SelectRows)
        table.setSelectionMode(self.Q.QAbstractItemView.SingleSelection)
        table.setAlternatingRowColors(True)
        table.horizontalHeader().setStretchLastSection(True)
        table.setMinimumHeight(110)
        table.setMaximumHeight(230)
        table.setSizePolicy(self.Q.QSizePolicy.Expanding, self.Q.QSizePolicy.Preferred)
        layout.addWidget(table)
        return table

    def _actions(self, layout, commands):
        grid = self.Q.QGridLayout(); buttons = []
        for index, (label, callback) in enumerate(commands):
            button = self.Q.QPushButton(label)
            button.setAutoDefault(False)
            button.clicked.connect(lambda checked=False, f=callback: f())
            grid.addWidget(button, index//3, index % 3); buttons.append(button)
        layout.addLayout(grid)
        return buttons

    def _item(self, table, row, column, text, *, editable=False, tooltip=None):
        item = self.Q.QTableWidgetItem(str(text))
        if not editable: item.setFlags(item.flags() & ~self.C.Qt.ItemIsEditable)
        if tooltip: item.setToolTip(tooltip)
        table.setItem(row, column, item)

    def _edit_cell(self, table, row, column, key, text, collection, *, units=False):
        # A delegate's pending editor text is not necessarily in item().text()
        # during Ctrl+S / heartbeat. Persist text on every edit, including '1e'.
        # Keep these widgets alive during refresh_context so caret/selection stay.
        if units:
            widget = self.Q.QComboBox()
            widget.setEditable(True)
            widget.setInsertPolicy(self.Q.QComboBox.NoInsert)
            widget.addItems(list(UNIT_CHOICES))
            widget.setCurrentText(str(text))
            signal = widget.currentTextChanged
        else:
            widget = self.Q.QLineEdit(str(text))
            signal = widget.textEdited
        widget.setAccessibleName(('기준 식 이름' if collection == 'sources' else
            {'name': '상수 이름', 'value': '상수 값', 'unit': '상수 단위'}[key])+f' {row+1}')
        widget.setMinimumWidth(0)
        if units: widget.setToolTip('단위: '+', '.join(UNIT_CHOICES))
        def edited(value):
            if self._loading or row >= len(self._value[collection]): return
            self._value[collection][row][key] = value
            table.setCurrentCell(row, column)
            self._emit()
        signal.connect(edited)
        C = self.C
        class SelectOnFocus(C.QObject):
            def eventFilter(self, watched, event):
                if event.type() == C.QEvent.FocusIn:
                    table.setCurrentCell(row, column)
                return False
        # Cell widgets receive focus without a viewport click; make the selected
        # source explicit before a toolbar action or snapshot reads currentRow.
        tracker = SelectOnFocus(widget)
        widget.installEventFilter(tracker)
        if units: widget.lineEdit().installEventFilter(tracker)
        widget.selection_tracker = tracker
        table.setCellWidget(row, column, widget)

    def value(self, *, raw=True):
        return relation_values(self._value, raw=raw)

    def view(self):
        return {'source_row': self.sources.currentRow(), 'constant_row': self.constants.currentRow()}

    def restore_view(self, value):
        for table, key in ((self.sources, 'source_row'), (self.constants, 'constant_row')):
            row = value.get(key, -1)
            if 0 <= row < table.rowCount(): table.setCurrentCell(row, 0)
            else: table.setCurrentCell(-1, -1); table.clearSelection()
        self._selection_notice()

    def load(self, value, *, preserve_view=False):
        self.cancel_picker()
        view = self.view() if preserve_view else {'source_row': -1, 'constant_row': -1}
        self._value = relation_values(value, raw=True)
        self._loading = True
        try:
            self.expression.setText(self._value['expression'])
            self.sources.setRowCount(len(self._value['sources']))
            for row, source in enumerate(self._value['sources']):
                self._edit_cell(self.sources, row, 0, 'alias', source['alias'], 'sources')
            self.constants.setRowCount(len(self._value['constants']))
            for row, constant in enumerate(self._value['constants']):
                for col, key in enumerate(('name', 'value', 'unit')):
                    self._edit_cell(self.constants, row, col, key, constant[key], 'constants', units=key == 'unit')
        finally:
            self._loading = False
        self.refresh_context()
        self.restore_view(view)

    def refresh_context(self):
        """Refresh labels/diagnostics, never replace alias, constants or expression."""
        context = self.context()
        self._context = context
        self.sources.blockSignals(True)
        try:
            for row, source in enumerate(self._value['sources']):
                joint = context['joints'].get(source.get('joint_id'), {})
                option = next((x for x in context['choices'] if
                    (x['binding']['joint_id'], x['binding']['type']) == (source.get('joint_id'), source.get('type'))), None)
                label = option['label'] if option else joint.get('label', '기준 구동 없음')
                issue = binding_problem(source, context['drives'], context['joints'])
                self._item(self.sources, row, 1, label, tooltip=label)
                self._item(self.sources, row, 2, source.get('unit', ''))
                self._item(self.sources, row, 3, option.get('value', '미확인') if option and not issue else '미확인',
                    tooltip='입력 시간식의 값 (t='+context.get('time_label', '미확인')+' s). 계산된 자세가 아닙니다.')
                self._item(self.sources, row, 4, '복구 필요' if issue else '선택됨', tooltip=issue)
        finally:
            self.sources.blockSignals(False)
        self._selection_notice()

    def _selection_notice(self):
        row = self.sources.currentRow()
        message = ''
        if 0 <= row < len(self._value['sources']) and hasattr(self, '_context'):
            message = binding_problem(self._value['sources'][row], self._context['drives'], self._context['joints'])
        self.source_notice.setText(message)

    def _emit(self):
        if not self._loading:
            self.changed(self.value())
            self.refresh_context()

    def _expression_changed(self, text):
        self._value['expression'] = text
        self._emit()

    def _next_name(self, prefix):
        used = {s['alias'] for s in self._value['sources']} | {c['name'] for c in self._value['constants']}
        n = 1
        while prefix+str(n) in used: n += 1
        return prefix+str(n)

    def add_source(self):
        if len(self._value['sources']) >= 32: return
        value = self.value()
        value['sources'].append({'alias': self._next_name('q'), 'joint_id': None, 'type': None, 'path': None, 'unit': ''})
        self.load(value, preserve_view=True)
        self.sources.setCurrentCell(len(value['sources'])-1, 0)
        self._emit()

    def add_constant(self):
        if len(self._value['constants']) >= 32: return
        value = self.value()
        value['constants'].append({'name': self._next_name('k'), 'value': '', 'unit': '1'})
        self.load(value, preserve_view=True)
        self.constants.setCurrentCell(len(value['constants'])-1, 1)
        self._emit()

    def remove(self, collection):
        table = getattr(self, collection); row = table.currentRow()
        if not 0 <= row < len(self._value[collection]): return
        value = self.value(); value[collection].pop(row)
        self.load(value, preserve_view=True)
        if value[collection]: table.setCurrentCell(min(row, len(value[collection])-1), 0)
        self._emit()

    def move(self, collection, direction):
        table = getattr(self, collection); row = table.currentRow(); following = row+direction
        if not (0 <= row < len(self._value[collection]) and 0 <= following < len(self._value[collection])): return
        value = self.value(); value[collection][row], value[collection][following] = value[collection][following], value[collection][row]
        self.load(value, preserve_view=True); table.setCurrentCell(following, 0)
        self._emit()

    def cancel_picker(self):
        if self._dialog is not None:
            self._dialog.reject()

    def confirm_unit(self):
        self.choose_source(unit_only=True)

    def choose_source(self, *, unit_only=False):
        row = self.sources.currentRow()
        if not 0 <= row < len(self._value['sources']): return
        self.cancel_picker()
        before = self.value(); previous = before['sources'][row]
        scope = self.scope()
        context = self.context()
        choices = deepcopy(context['choices'])
        if unit_only:
            choices = [c for c in choices if all(c['binding'][k] == previous[k] for k in ('joint_id', 'type', 'path'))]
        dialog = self.Q.QDialog(self.widget)
        dialog.setWindowTitle('기준 단위 확인' if unit_only else '기준 구동 선택')
        dialog.resize(520, 240)
        dialog.setAttribute(self.C.Qt.WA_DeleteOnClose)
        layout = self.Q.QVBoxLayout(dialog)
        combo = self.Q.QComboBox(); combo.setMinimumWidth(0)
        combo.setSizeAdjustPolicy(self.Q.QComboBox.AdjustToMinimumContentsLengthWithIcon)
        combo.setMinimumContentsLength(15)
        combo.addItem('기준 구동을 선택하세요', None)
        for index, choice in enumerate(choices):
            combo.addItem(choice['label']+' ['+choice['binding']['unit']+']', index)
            combo.setItemData(combo.count()-1, choice['label'], self.C.Qt.ToolTipRole)
        layout.addWidget(combo)
        notice = self.Q.QLabel(); notice.setWordWrap(True); layout.addWidget(notice)
        acknowledge = self.Q.QCheckBox('기준 단위 변경을 확인했습니다. 계수 값과 단위는 유지합니다.')
        layout.addWidget(acknowledge)
        buttons = self.Q.QDialogButtonBox()
        ok = buttons.addButton('선택 확인', self.Q.QDialogButtonBox.AcceptRole)
        buttons.addButton('취소', self.Q.QDialogButtonBox.RejectRole)
        layout.addWidget(buttons)
        def selected():
            index = combo.currentData()
            return choices[index] if type(index) is int and 0 <= index < len(choices) else None
        def update(*args):
            choice = selected()
            changed_unit = bool(choice and previous['unit'] and previous['unit'] != choice['binding']['unit'])
            acknowledge.setVisible(changed_unit)
            issue = choice.get('issue', '') if choice else '기준 구동을 선택하세요.'
            notice.setText(issue or ('기존 단위 '+previous['unit']+' → '+choice['binding']['unit'] if changed_unit
                else ('식 값: '+choice.get('value', '미확인')+' '+choice['binding']['unit']+' (t='+context['time_label']+' s)')))
            ok.setEnabled(bool(choice and not issue and (not changed_unit or acknowledge.isChecked())))
        def commit():
            choice = selected()
            if not choice or not ok.isEnabled(): return
            # Current owner/assembly/row and raw input must still be identical.
            # A late callback can never rebind a newly selected/editing drive.
            if scope != self.scope() or self.value() != before or self.sources.currentRow() != row:
                notice.setText('편집 대상이 바뀌었습니다. 취소한 뒤 현재 기준을 다시 선택하세요.'); ok.setEnabled(False); return
            latest = self.context()
            candidate = {**deepcopy(choice['binding']), 'alias': previous['alias']}
            issue = binding_problem(candidate, latest['drives'], latest['joints'])
            if issue:
                notice.setText(issue); ok.setEnabled(False); return
            self._value['sources'][row] = candidate
            dialog.accept()
            self._emit()
        def finished(*args):
            if self._dialog is dialog: self._dialog = None
            self.sources.setFocus()
        combo.currentIndexChanged.connect(update); acknowledge.toggled.connect(update)
        buttons.accepted.connect(commit); buttons.rejected.connect(dialog.reject)
        dialog.finished.connect(finished)
        dialog.relation_controls = (combo, acknowledge, ok, notice)  # focused Qt acceptance tests
        self._dialog = dialog
        existing = next((i+1 for i, c in enumerate(choices) if all(c['binding'][k] == previous[k]
                        for k in ('joint_id', 'type', 'path'))), 0)
        combo.setCurrentIndex(existing); update()
        dialog.open()  # window-modal, no nested exec/event loop


class RelationPanelBinding:
    """Small motion_panel hook adapter; uses its existing versions/commands."""
    def __init__(self, panel, details_layout):
        self.panel = panel
        self._selected = None
        positions = [(1, 2), (1, 3)] + [(row, column) for row in (2, 3) for column in range(4)]
        self._single_dependency_widgets = [details_layout.itemAtPosition(row, column).widget()
                                           for row, column in positions]
        panel.drive_mode.addItem('관계식')
        self.editor = RelationEditor(panel.QtCore, panel.Q, changed=self.changed,
                                     context=self.context, scope=self.scope)
        details_layout.addWidget(self.editor.widget, 7, 0, 1, 4)
        self.editor.widget.hide()

    def _show_relation(self, enabled):
        self.editor.widget.setVisible(enabled)
        for widget in self._single_dependency_widgets:
            widget.setVisible(not enabled)

    def scope(self):
        p = self.panel; row = p.drives.currentRow()
        item = p.drives.cellWidget(row, 0) if row >= 0 else None
        return p._document, p._session, p.assembly.currentData(), item, p._edit_version

    def context(self):
        p = self.panel
        drives = p._drive_values()
        joints = {j['id']: j for j in p._motion.get('joints', [])}
        compiled, problems = {}, {}
        try:
            start = float(p.time['start'].text()); end = float(p.time['end'].text())
            if not math.isfinite(start) or not math.isfinite(end): raise ValueError('nonfinite')
            compiled, problems = compile_drives(drives, (start, end), joints)
            time_label = format(start, '.6g')
        except (ValueError, TypeError, OverflowError):
            start, time_label = None, '미확인'
        choices = []
        for index, drive in enumerate(drives):
            joint = joints.get(drive.get('joint_id'), {})
            if not joint: continue
            kind = drive.get('type'); u = drive.get('unit', '')
            label = joint.get('label', '관절')+' / '+('회전' if kind == 'Angular' else '이동')
            if drive.get('name'): label += ' / '+drive['name']
            shown = '미확인'
            if start is not None and index in compiled and index not in problems:
                try: shown = format(_expression_value(compiled[index], start)/UNITS[kind][u], '.8g')
                except (ValueError, KeyError, TypeError, OverflowError, ZeroDivisionError, RecursionError): pass
            issue = '; '.join(problems.get(index, []))
            if index == p.drives.currentRow(): issue = '선택한 출력 구동은 자기 기준으로 사용할 수 없습니다.'
            choices.append({'label': label, 'value': shown, 'issue': issue,
                'binding': {'joint_id': drive.get('joint_id'), 'type': kind,
                    'path': deepcopy(joint.get('path')), 'unit': u}})
        return {'drives': drives, 'joints': joints, 'choices': choices, 'time_label': time_label}

    def select(self, value=None):
        p = self.panel; row = p.drives.currentRow()
        visible = row >= 0 and value is not None and value.get('relation') is not None
        self._show_relation(visible)
        item = p.drives.cellWidget(row, 0) if row >= 0 else None
        key = (p._document, p._session, p.assembly.currentData(), item)
        if visible:
            if key != self._selected or relation_values(value['relation'], raw=True) != self.editor.value():
                self.editor.load(value['relation'], preserve_view=key == self._selected)
            else: self.editor.refresh_context()
        else:
            self.editor.cancel_picker()
        self._selected = key

    def options(self, options):
        p = self.panel
        if p.drive_mode.currentIndex() == 2:
            options.pop('dependency', None)
            if options.get('relation') is None: options['relation'] = empty_relation()
            p._item(p.drives, p.drives.currentRow(), 2, '', readonly=True)
            self._show_relation(True)
            if options['relation'] != self.editor.value(): self.editor.load(options['relation'])
        else:
            options.pop('relation', None)
            self._show_relation(False); self.editor.cancel_picker()
        return options

    def changed(self, value):
        p = self.panel; row = p.drives.currentRow()
        if p._loading or p._loading_drive or row < 0 or p.drive_mode.currentIndex() != 2: return
        item = p.drives.cellWidget(row, 0)
        if self._selected != (p._document, p._session, p.assembly.currentData(), item): return
        options = deepcopy(item.motion_options)
        options.pop('dependency', None); options['relation'] = deepcopy(value)
        item.motion_options = options
        p._mark_edited()

    def put_view(self, editor):
        p = self.panel; row = p.drives.currentRow()
        if row >= 0 and p.drives.cellWidget(row, 0).motion_options.get('relation') is not None:
            editor['relation_view'] = self.editor.view()

    def restore_view(self, editor):
        p = self.panel; row = p.drives.currentRow()
        self.select(p._drive_values(raw=True)[row] if row >= 0 else None)
        self.editor.restore_view(editor.get('relation_view', {'source_row': -1, 'constant_row': -1}))

    def refresh_context(self):
        if self.editor.widget.isVisible(): self.editor.refresh_context()
