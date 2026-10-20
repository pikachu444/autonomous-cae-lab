"""Small native Qt actions beside the existing frame selection and model tree.

No Qt distribution is imported: FreeCAD supplies its own QtCore/QtWidgets.
"""
from .assembly_pose_candidate import selected_body, require_valid

STATES = {'READY': '사용 가능', 'FAILED': '준비 실패', 'CANCELLED': '취소됨',
          'INTERRUPTED': '중단됨', 'PREPARING': '만드는 중', 'DRAFT': '준비 사본',
          'INVALID': '확인 필요'}



def model_actions(model, selected, *, busy=False, closed=False):
    """One policy for tree signals, viewport refresh and command callbacks."""
    editable = bool(selected) and not busy and not closed
    usable = editable and bool(model and model.get('ready') is True)
    return {'mesh': usable, 'material': usable, 'condition': usable, 'cad': editable}

def _message(reply):
    if reply.get('status') == 'FAILED' or reply.get('error'):
        return (reply.get('error') or {}).get('message', '작업을 완료하지 못했습니다.')
    return reply.get('message', '')


def attach_motion(connection, owner, controller):
    Q, C = connection.QtWidgets, connection.QtCore
    class Actions(Q.QGroupBox):
        def __init__(self):
            super().__init__('선택 자세로 해석')
            self.setObjectName('assemblyPoseActions')
            self._busy, self._opened, self._stamp = False, set(), None
            box = Q.QVBoxLayout(self)
            row = Q.QHBoxLayout(); box.addLayout(row)
            self.create = Q.QPushButton('해석 모델 만들기'); row.addWidget(self.create, 1)
            self.cancel = Q.QPushButton('취소'); row.addWidget(self.cancel)
            self.create.clicked.connect(self.start)
            self.cancel.clicked.connect(lambda: self.send('cancel', {}, {}))
            self.status = Q.QLabel('운동 결과와 프레임을 선택하세요.')
            self.status.setWordWrap(True); box.addWidget(self.status)
            self.history = Q.QComboBox(); self.history.setMinimumWidth(0)
            self.history.setSizeAdjustPolicy(Q.QComboBox.AdjustToMinimumContentsLengthWithIcon)
            box.addWidget(self.history)
            row = Q.QGridLayout(); box.addLayout(row)
            self.open_model = Q.QPushButton('해석 모델 열기')
            self.open_draft = Q.QPushButton('준비 사본 열기')
            self.open_source = Q.QPushButton('원 조립 사본 열기')
            for col, (button, kind) in enumerate(((self.open_model, 'model'), (self.open_draft, 'draft'), (self.open_source, 'source'))):
                row.addWidget(button, col//2, col%2)
                button.clicked.connect(lambda checked=False, kind=kind: self.open(kind))
            self.history.currentIndexChanged.connect(self.buttons)
            self.timer = C.QTimer(self); self.timer.setInterval(500)
            self.timer.timeout.connect(self.refresh); self.timer.start(); self.refresh()

        def send(self, action, args, target):
            self._busy = True
            def done(reply):
                self._busy = False
                text = _message(reply or {})
                if text: self.status.setText(text)
                if action == 'open' and reply.get('native_document'):
                    self.show_document(reply['native_document'])
                self.refresh()
            try:
                connection.submit_native('pre.assembly_candidate.'+action, args, target, done, owner=owner)
            except Exception as error:
                self._busy = False; self.status.setText(str(error))

        def start(self):
            if getattr(controller, '_edited', False) or getattr(controller, '_joint_edited', False):
                self.status.setText('관절과 구동 편집을 적용하거나 취소한 뒤 해석 모델을 만드세요.')
                return
            self.send('create', controller._frame_args(), {'assembly_id': controller.assembly.currentData()})

        def show_document(self, name):
            connection.tick()
            item = connection.owners.get(name)
            if item is None: return
            connection.App.setActiveDocument(name)
            if item[0].read_metadata().get('assembly_pose_candidate'):
                connection.show_panel('assembly_candidate', owner=item[0])
                gui = connection.Gui.getDocument(name)
                if gui is not None: gui.activeView().fitAll()

        def open(self, which):
            row = self.history.currentData() or {}
            if row.get('id'): self.send('open', {'attempt_id': row['id'], 'which': which}, {})

        def buttons(self, *unused):
            row = self.history.currentData() or {}
            for button, field in ((self.open_model, 'project'), (self.open_draft, 'draft_project'), (self.open_source, 'source_project')):
                available = row.get(field) or (field == 'draft_project' and row.get('prepared_project'))
                button.setEnabled(bool(available) and not self._busy and not owner.pose_candidates.busy)

        def refresh(self):
            if owner.closed: self.timer.stop(); return
            data = owner.pose_candidates.descriptor()
            result = controller._selected_calculation()
            enabled = bool(result.get('accepted') and result.get('poses', {}).get('sha256'))
            # Some descriptors intentionally omit the packed payload; accepted
            # saved results are admitted exactly by the native command itself.
            enabled = enabled or bool(result.get('accepted') and result.get('persisted'))
            dirty = getattr(controller, '_edited', False) or getattr(controller, '_joint_edited', False)
            self.create.setEnabled(enabled and not dirty and not data['busy'] and not self._busy and not controller._busy)
            self.cancel.setEnabled(data['busy'] and not self._busy)
            rows = data['history']
            stamp = tuple((r['id'], r['updated_utc'], r['state']) for r in rows)
            if stamp != self._stamp:
                self._stamp = stamp
                selected = (self.history.currentData() or {}).get('id')
                self.history.blockSignals(True); self.history.clear()
                for row in rows:
                    text = '프레임 '+str(row.get('frame', '—'))+' · '+STATES.get(row['state'], '미확인')
                    self.history.addItem(text, row)
                    if row['id'] == selected: self.history.setCurrentIndex(self.history.count()-1)
                self.history.blockSignals(False)
                current = data.get('current')
                if current:
                    self.status.setText(current.get('message', ''))
                    if current['state'] == 'READY' and current['id'] not in self._opened:
                        self._opened.add(current['id']); self.show_document(current['native_document'])
            self.buttons()
    actions = Actions()
    layout = controller.frame_table.parentWidget().layout()
    layout.insertWidget(layout.indexOf(controller.frame_table)+1, actions)
    controller.assembly_candidate_actions = actions
    return actions


def make_panel(connection, owner):
    Q, C = connection.QtWidgets, connection.QtCore
    class Panel(Q.QWidget):
        def __init__(self):
            super().__init__(); self.setObjectName('assemblyPoseModel')
            self._rows, self._busy, self._stamp = {}, False, None
            self._blocked_message = ''
            layout = Q.QVBoxLayout(self)
            self.title = Q.QLabel(); self.title.setWordWrap(True); layout.addWidget(self.title)
            self.tree = Q.QTreeWidget(); self.tree.setHeaderLabels(['부품', '상태'])
            self.tree.setSelectionMode(Q.QAbstractItemView.SingleSelection)
            self.tree.setMinimumWidth(0); self.tree.setColumnWidth(0, 225)
            self.tree.setUniformRowHeights(True); layout.addWidget(self.tree, 1)
            self.tree.itemSelectionChanged.connect(self.select)
            grid = Q.QGridLayout(); layout.addLayout(grid)
            self.mesh = Q.QPushButton('메시 설정'); self.material = Q.QPushButton('재료 지정')
            self.condition = Q.QPushButton('하중·구속'); self.cad = Q.QPushButton('원부품 편집')
            for i, button in enumerate((self.mesh, self.material, self.condition, self.cad)):
                grid.addWidget(button, i//2, i%2)
            self.mesh.clicked.connect(lambda: self.prepare('mesh'))
            self.material.clicked.connect(lambda: self.prepare('material'))
            self.condition.clicked.connect(self.conditions)
            self.cad.clicked.connect(self.edit_cad)
            self.status = Q.QLabel(); self.status.setWordWrap(True); layout.addWidget(self.status)
            self.status.setText('부품을 선택한 뒤 메시와 조건을 지정하세요. 조립의 기준 고정은 가져오지 않았습니다.')
            self.timer = C.QTimer(self); self.timer.setInterval(700)
            self.timer.timeout.connect(self.refresh); self.timer.start(); self.refresh()

        def row(self):
            item = self.tree.currentItem()
            return self._rows.get(item.data(0, C.Qt.UserRole)) if item else None

        def select(self):
            row = self.row()
            self.buttons(row, owner.pose_candidates.descriptor().get('model'))
            if row:
                connection.Gui.Selection.clearSelection()
                connection.Gui.Selection.addSelection(owner.doc.getObject(row['body_id']))

        def buttons(self, row, model):
            # Selection changes and timer refresh must use the SAME admission.
            # Retained drafts still expose copied CAD for ordinary editing/saving.
            flags = model_actions(model, row, busy=self._busy, closed=owner.closed)
            for name, enabled in flags.items():
                getattr(self, name).setEnabled(enabled)

        def admitted(self):
            try:
                return require_valid(owner)  # fresh, never the generation/UI cache
            except ValueError as error:
                self.status.setText(str(error))
                self.buttons(self.row(), None)
                return False

        def conditions(self):
            model = self.admitted()
            if not model: return
            if selected_body(owner) is None:
                self.status.setText('해석할 부품의 면이나 부품을 모델에서 선택하세요.'); return
            try:
                import FemGui
                owner.before_design_action('FEM conditions')
                connection.Gui.activateWorkbench('FemWorkbench')
                FemGui.setActiveAnalysis(owner.doc.getObject(model['analysis_id']))
                for dock in connection.Gui.getMainWindow().findChildren(Q.QDockWidget):
                    if dock.objectName() in ('Model', 'Tasks'):
                        dock.show()
                self.status.setText('FEM 메뉴에서 하중 또는 구속을 선택하세요. 현재 선택한 면과 부품을 사용합니다.')
            except Exception as error:
                self.status.setText(str(error))

        def edit_cad(self):
            row = self._rows.get(selected_body(owner))
            if row:
                source = owner.doc.getObject(row['source_id'])
                connection.Gui.Selection.clearSelection(); connection.Gui.Selection.addSelection(source)
                self.status.setText('복사된 CAD 원부품입니다. 치수 변경은 이 모델의 연결된 반복 부품에 함께 반영됩니다.')

        def prepare(self, kind):
            if not self.admitted(): return
            row = self._rows.get(selected_body(owner))
            if row is None:
                self.status.setText('해석할 부품 하나를 모델이나 트리에서 선택하세요.'); return
            self._busy = True
            for button in (self.mesh, self.material, self.condition, self.cad): button.setEnabled(False)
            def done(reply):
                self._busy = False
                error = _message(reply or {})
                if error: self.status.setText(error)
                elif reply.get('object_id'):
                    obj = owner.doc.getObject(reply['object_id'])
                    connection.Gui.Selection.clearSelection(); connection.Gui.Selection.addSelection(obj)
                    caption = ('재료 편집을 완료하세요.' if kind == 'material' else
                               'FreeCAD 메시 작업창에서 크기와 차수를 지정하고 생성하세요.')
                    connection.submit_native('pre.fem.task_edit', {}, {'object_id': obj.Name},
                        lambda r: self.status.setText(_message(r) or caption), owner=owner)
                self.refresh()
            try:
                connection.submit_native('pre.assembly_candidate.'+kind, {}, {'object_id': row['body_id']}, done, owner=owner)
            except Exception as error:
                self._busy = False; self.status.setText(str(error)); self.refresh()

        def refresh(self):
            if owner.closed: self.timer.stop(); return
            model = owner.pose_candidates.descriptor().get('model')
            if not model:
                self.title.setText('운동 결과에서 해석 모델을 만드세요.')
                for button in (self.mesh, self.material, self.condition, self.cad): button.setEnabled(False)
                return
            state = model.get('preparation_state', model['state'])
            label = '사용 가능' if model.get('ready') else ('확인 필요' if model['errors'] else STATES.get(state, '확인 필요'))
            self.title.setText('프레임 '+str(model.get('frame', '—'))+'의 독립 해석 모델 — '+label)
            blocked = model.get('blocked_reason', '')
            if blocked:
                self.status.setText(blocked)
            elif self._blocked_message and self.status.text() == self._blocked_message:
                self.status.setText('부품을 선택한 뒤 메시와 조건을 지정하세요.')
            self._blocked_message = blocked
            stamp = repr(model)
            if stamp != self._stamp:
                self._stamp = stamp
                selected = self.row(); selected = selected['body_id'] if selected else None
                self.tree.blockSignals(True); self.tree.clear(); self._rows = {}; groups = {}
                for row in model['bodies']:
                    parent = self.tree.invisibleRootItem()
                    labels = row['label'].split(' / ')
                    for depth in range(1, len(row['path'])-1):
                        key = tuple(row['path'][:depth+1])
                        if key not in groups:
                            groups[key] = Q.QTreeWidgetItem(parent, [labels[min(depth if len(row['path']) > 3 else depth-1, len(labels)-1)], ''])
                        parent = groups[key]
                    item = Q.QTreeWidgetItem(parent, [labels[-1], '배치 편집됨' if row['pose_edited'] else '선택 자세'])
                    item.setData(0, C.Qt.UserRole, row['body_id']); item.setToolTip(0, row['label'])
                    self._rows[row['body_id']] = row
                    if row['body_id'] == selected: self.tree.setCurrentItem(item)
                self.tree.expandAll(); self.tree.blockSignals(False)
            native_id = selected_body(owner)
            row = self._rows.get(native_id)
            # Do not clear a selected native FACE while following the viewport.
            self.tree.blockSignals(True)
            if row is None:
                self.tree.clearSelection(); self.tree.setCurrentItem(None)
            else:
                iterator = Q.QTreeWidgetItemIterator(self.tree)
                while iterator.value():
                    item = iterator.value()
                    if item.data(0, C.Qt.UserRole) == native_id:
                        self.tree.setCurrentItem(item); break
                    iterator += 1
            self.tree.blockSignals(False)
            self.buttons(row, model)
    return Panel()
