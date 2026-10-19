"""Injected native Qt FEM panel. All edits go through the typed owner commands.

make_panel(QtWidgets, QtCore, editor, submit) takes FreeCAD's installed Qt
bindings; this module imports no PySide distribution. submit(op, args, target,
on_done=None) uses the shared asynchronous native command transport and returns
{'queued': True}; its callback receives the terminal payload/envelope.
"""


def make_panel(QtWidgets, QtCore, editor, submit):
    class TaskTabs(QtWidgets.QTabWidget):
        def __init__(self):
            super().__init__()
            self._pages = {}

        def addTab(self, page, label):
            scroll = QtWidgets.QScrollArea()
            scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
            scroll.setWidgetResizable(True)
            scroll.setWidget(page)
            self._pages[page] = scroll
            return super().addTab(scroll, label)

        def setCurrentWidget(self, page):
            super().setCurrentWidget(self._pages.get(page, page))

        def indexOf(self, page):
            return super().indexOf(self._pages.get(page, page))

        def widget(self, index):
            scroll = super().widget(index)
            return scroll.widget() if scroll is not None else None

        def currentWidget(self):
            return self.widget(self.currentIndex())

    class Panel(QtWidgets.QWidget):
        def __init__(self):
            super().__init__()
            self.setObjectName('caelabFemPanel')
            font = self.font()
            font.setFamily('Malgun Gothic')
            font.setPointSize(max(9, font.pointSize()))
            self.setFont(font)
            self.editor, self.submit = editor, submit
            self._description, self._mutating, self._last_history = {}, [], None
            self._actions, self._command_busy, self._edit_serial = [], False, 0
            self._mesh_form_id, self._view_epoch, self._disposed = None, 0, False
            self.destroyed.connect(lambda *_: setattr(self, '_disposed', True))
            outer = QtWidgets.QVBoxLayout(self)
            outer.setContentsMargins(6, 8, 6, 8)
            row = QtWidgets.QHBoxLayout()
            heading = QtWidgets.QLabel('해석 모델')
            heading.setWordWrap(True)
            row.addWidget(heading, 1)
            self.refresh_button = self._button('새로 고침', self.refresh, row, mutate=False)
            self.cancel_button = self._button('메시 생성 취소', self.cancel_mesh, row, mutate=False)
            outer.addLayout(row)
            self.tabs = TaskTabs()
            outer.addWidget(self.tabs, 1)
            self._mesh_tab()
            self._region_tab()
            self._material_tab()
            from .contact_panel import add_contact_page
            self.contact_page = add_contact_page(self, QtWidgets, QtCore)
            from .contact_steps_panel import add_steps_page
            self.steps_page = add_steps_page(self, QtWidgets, QtCore)
            from .periodic_panel import add_periodic_page
            self.periodic_page = add_periodic_page(self, QtWidgets, QtCore)
            from .pretension_panel import add_pretension_page
            self.pretension_page = add_pretension_page(self, QtWidgets, QtCore)
            from .initial_field_panel import add_initial_field_page
            self.initial_field_page = add_initial_field_page(self, QtWidgets, QtCore)
            from .convergence_panel import add_convergence_page
            self.convergence_page = add_convergence_page(self, QtWidgets, QtCore)
            self.status = QtWidgets.QPlainTextEdit()
            self.status.setObjectName('femStatus')
            self.status.setReadOnly(True)
            self.status.setVisible(False)
            self.details_dialog = QtWidgets.QDialog(self)
            self.details_dialog.setWindowTitle('처리 상세')
            self.details_dialog.resize(720, 320)
            details_layout = QtWidgets.QVBoxLayout(self.details_dialog)
            details_layout.addWidget(self.status, 1)
            close_details = QtWidgets.QPushButton('닫기')
            close_details.clicked.connect(self.details_dialog.close)
            details_layout.addWidget(close_details)
            self.status_summary = QtWidgets.QLabel('모델 설정을 편집하세요.')
            self.status_summary.setWordWrap(True)
            status_row = QtWidgets.QHBoxLayout()
            status_row.addWidget(self.status_summary, 1)
            self.details_button = QtWidgets.QToolButton()
            self.details_button.setText('상세')
            self.details_button.setCheckable(True)
            self.details_button.setEnabled(False)
            self.details_button.toggled.connect(self._toggle_details)
            self.details_dialog.finished.connect(lambda *_: self.details_button.setChecked(False))
            status_row.addWidget(self.details_button)
            outer.addLayout(status_row)
            self.status.textChanged.connect(self._status_changed)
            self.tabs.currentChanged.connect(self._condition_status)
            for field, signal in [(self.min_size, 'valueChanged'), (self.max_size, 'valueChanged'),
                    (self.order, 'currentIndexChanged'), (self.dimension, 'currentIndexChanged'),
                    (self.element_type, 'currentIndexChanged'), (self.local_size, 'valueChanged'),
                    (self.local_region, 'currentIndexChanged'), (self.refinement, 'currentIndexChanged'),
                    (self.region_label, 'textChanged'), (self.condition, 'currentIndexChanged'),
                    (self.condition_region, 'currentIndexChanged'), (self.force, 'valueChanged'),
                    (self.direction_region, 'currentIndexChanged')]:
                getattr(field, signal).connect(self._edited)
            self.timer = QtCore.QTimer(self)
            self.timer.setInterval(500)
            self.timer.timeout.connect(self.poll)
            self.refresh()
            self.timer.start()

        def _button(self, text, callback, layout, *, mutate=True, name=None):
            button = QtWidgets.QPushButton(text)
            if name:
                button.setObjectName(name)
            button.clicked.connect(lambda: self._action(callback))
            layout.addWidget(button)
            self._actions.append(button)
            if mutate:
                self._mutating.append(button)
            return button

        def _action(self, callback):
            try:
                callback()
            except Exception as error:
                self.status.setPlainText(str(error))

        def _edited(self, *unused):
            self._edit_serial += 1

        def hideEvent(self, event):
            self._view_epoch += 1
            super().hideEvent(event)

        def _status_changed(self):
            text = self.status.toPlainText()
            first = text.splitlines()[0] if text else '모델 설정을 편집하세요.'
            messages = {
                'STALE_SESSION:': '문서가 바뀌었습니다. 현재 모델을 다시 조회하세요.',
                'STALE_SELECTION:': '선택이 바뀌었습니다. 선택 대상을 다시 조회하세요.',
                'STALE_TARGET:': '적용 대상을 찾지 못했습니다. 3D 선택을 확인하세요.',
                'Contact draft applied.': '접촉 설정을 적용했습니다. 프로젝트 저장과 계산 실행은 별도 동작입니다.',
                'Separate body meshes prepared.': '물체별 메시를 준비했습니다. 크기를 정한 뒤 각 메시를 생성하세요.',
                'Native mesh settings applied.': '메시 설정을 적용했습니다. 메시 생성은 별도로 실행하세요.',
                'Native isotropic material values applied;': '탄성 물성을 적용했습니다. 다른 재료 설정은 유지됩니다.',
                'Actual current condition targets selected': '적용 대상을 3D에서 표시했습니다. 선택한 면을 확인하세요.',
                'Existing condition ': '조건의 적용 대상을 갱신했습니다.',
                'Native material values are unresolved;': '재료 물성을 확인하지 못했습니다. 값을 입력하거나 FreeCAD에서 편집하세요.',
                'Rebind cancelled.': '면 재지정을 취소했습니다. 현재 편집은 유지됩니다.',
                'Contact faces selected': '접촉면을 3D에서 표시했습니다.',
            }
            for prefix, message in messages.items():
                if first.startswith(prefix):
                    first = message
                    break
            self.status_summary.setText(first)
            self.status_summary.setToolTip(text)
            self.details_button.setEnabled(bool(text))

        def _toggle_details(self, checked):
            self.status.setVisible(checked)
            if checked:
                self.details_dialog.show()
                self.details_dialog.raise_()
            else:
                self.details_dialog.hide()

        def _condition_status(self, *_):
            if self.tabs.currentIndex() != 1:
                return
            row = next((r for r in self._description.get('conditions', [])
                        if r['object_id'] == self.condition.currentData()), None)
            errors = row['errors'] if row else []
            self.condition_message.setText('적용 대상을 3D에서 확인한 뒤 현재 적용 대상 확인을 누르세요. 면을 다시 지정하려면 선택한 면으로 변경을 사용하세요.' if errors else '')
            self.condition_message.setToolTip('\n'.join(str(e.get('message', e)) if isinstance(e, dict) else str(e) for e in errors))
            self.condition_message.setVisible(bool(errors))

        def _section(self, layout, text):
            heading = QtWidgets.QLabel(text)
            heading.setStyleSheet('font-weight: 600; margin-top: 4px;')
            layout.addWidget(heading)

        def _send(self, operation, args=None, object_id=None, on_done=None, on_error=None):
            if self._command_busy:
                raise ValueError('다른 명령을 처리 중입니다. 완료 후 다시 시도하세요.')
            owner, doc, serial = self.editor.owner, self.editor.owner.doc, self._edit_serial
            session = getattr(owner, 'session_id', None)
            self._command_busy = True
            delivered = False
            self.poll()
            def done(result):
                nonlocal delivered
                if delivered:
                    return
                delivered = True
                self._command_busy = False
                if self._disposed:
                    if on_error:
                        on_error(ValueError('CLOSED_PANEL: the mesh editor has been closed'))
                    return
                self._completion_serial = serial
                try:
                    if self.editor.owner is not owner or owner.doc is not doc or getattr(owner, 'closed', False) or getattr(owner, 'session_id', None) != session:
                        raise ValueError('STALE_SESSION: the native command receipt belongs to the earlier document/session')
                    if not isinstance(result, dict):
                        raise ValueError('처리 결과를 확인하지 못했습니다. 같은 요청을 다시 조회하세요.')
                    if result.get('status') == 'FAILED':
                        error = result.get('error', {})
                        failure = ValueError(error.get('message', str(error)))
                        failure.native_terminal = True  # A returned native rejection, not a transport timeout.
                        raise failure
                    payload = result.get('result', result)
                    if on_done:
                        on_done(payload)
                except Exception as error:
                    self.status.setPlainText(str(error))
                    if on_error:
                        on_error(error)
                finally:
                    self.poll()
            try:
                result = self.submit(operation, args or {}, {'object_id': object_id} if object_id else {}, on_done=done)
                if isinstance(result, dict) and not result.get('queued') and not delivered:
                    done(result)  # Explicit immediate receipts remain useful for injected local checks.
            except Exception as error:
                self._command_busy = False
                self.poll()
                if on_error:
                    on_error(error)
                raise

        def _refresh_after(self, result=None):
            self.refresh(load_forms=self._edit_serial == self._completion_serial)

        def _page(self, label):
            page = QtWidgets.QWidget()
            layout = QtWidgets.QVBoxLayout(page)
            self.tabs.addTab(page, label)
            return layout

        def _number(self, name, minimum=0, maximum=1e12, value=0):
            field = QtWidgets.QDoubleSpinBox()
            field.setObjectName(name)
            field.setDecimals(9)
            field.setRange(minimum, maximum)
            field.setValue(value)
            return field

        def _mesh_tab(self):
            layout = self._page('메시')
            self._section(layout, '요소 크기와 종류')
            form = QtWidgets.QFormLayout()
            self.mesh = QtWidgets.QComboBox()
            self.mesh.setObjectName('femMesh')
            self.mesh.currentIndexChanged.connect(lambda *_: self._action(self._mesh_changed))
            form.addRow('메시 선택', self.mesh)
            self.min_size = self._number('femMinimumSize')
            self.max_size = self._number('femMaximumSize')
            form.addRow('최소 요소 크기 [mm] (0: 자동)', self.min_size)
            form.addRow('최대 요소 크기 [mm] (0: 제한 없음)', self.max_size)
            self.order, self.dimension = QtWidgets.QComboBox(), QtWidgets.QComboBox()
            self.order.setObjectName('femElementOrder')
            self.dimension.setObjectName('femElementDimension')
            form.addRow('요소 차수', self.order)
            form.addRow('요소 차원', self.dimension)
            self.element_type = QtWidgets.QComboBox()
            self.element_type.addItem('현재 차수와 차원 유지', None)
            self.element_type.addItem('C3D10 2차 사면체 (실행 지원)', 'C3D10')
            self.element_type.addItem('C3D4 1차 사면체 (실행 미지원)', 'C3D4')
            form.addRow('요소 종류', self.element_type)
            layout.addLayout(form)
            row = QtWidgets.QHBoxLayout()
            self._button('메시 설정 적용', self.apply_mesh_settings, row, name='femApplyMeshSettings')
            self._button('메시 생성', self.generate_mesh, row, name='femGenerateMesh')
            self._button('FreeCAD에서 메시 편집', lambda: self.native_task(self.mesh.currentData()), row)
            layout.addLayout(row)
            self._section(layout, '국부 요소 크기')
            form = QtWidgets.QFormLayout()
            self.local_region, self.refinement = QtWidgets.QComboBox(), QtWidgets.QComboBox()
            self.refinement.currentIndexChanged.connect(lambda *_: self._action(self._refinement_changed))
            self.local_size = self._number('femLocalSize', minimum=.000000001, value=1)
            form.addRow('국부 크기 적용 영역', self.local_region)
            form.addRow('국부 크기 설정', self.refinement)
            form.addRow('국부 요소 크기 [mm]', self.local_size)
            layout.addLayout(form)
            self._button('국부 크기 적용', self.apply_local_size, layout)
            self._section(layout, '메시 품질')
            row = QtWidgets.QHBoxLayout()
            self.offset = QtWidgets.QSpinBox()
            self.offset.setRange(0, 2147483647)
            self.offset.setToolTip('앞에서 건너뛸 요소 수입니다. 0이면 첫 요소부터 조회합니다.')
            row.addWidget(QtWidgets.QLabel('건너뛸 요소 수'))
            row.addWidget(self.offset)
            self._button('메시 품질 조회', self.read_quality, row, mutate=False, name='femReadQuality')
            layout.addLayout(row)
            row = QtWidgets.QHBoxLayout()
            self._button('선택 요소 표시', self.highlight_quality, row, mutate=False)
            row.addStretch()
            layout.addLayout(row)
            self.quality = QtWidgets.QTableWidget(0, 5)
            self.quality.setObjectName('femQualityTable')
            self.quality.setHorizontalHeaderLabels(['요소 번호', '요소 종류', '최소 표본 J [mm³]', '정규화 J', '확인 사항'])
            self.quality.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
            self.quality.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
            self.quality.horizontalHeader().setStretchLastSection(True)
            self.quality.setColumnWidth(2, 140)
            self.quality.setColumnWidth(3, 130)
            layout.addWidget(self.quality, 1)
            self.distribution = QtWidgets.QTableWidget(0, 4)
            self.distribution.setObjectName('femQualityDistribution')
            self.distribution.setHorizontalHeaderLabels(['품질 지표', '구간 하한', '구간 상한', '요소 수'])
            self.distribution.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
            self.distribution.setMaximumHeight(160)
            self.distribution.horizontalHeader().setStretchLastSection(True)
            self.distribution.setColumnWidth(0, 170)
            self.distribution.setVisible(False)
            layout.addWidget(self.distribution)
            scope = QtWidgets.QLabel('기본 해석: 단일 고체 C3D10, 정적 선형, 고정과 힘. 야코비안 4개 표본은 요소 전체의 품질을 보장하지 않습니다.')
            scope.setWordWrap(True)
            layout.addWidget(scope)

        def _region_tab(self):
            layout = self._page('영역과 조건')
            self._section(layout, '선택 영역')
            self.regions = QtWidgets.QTreeWidget()
            self.regions.setObjectName('femRegions')
            self.regions.setHeaderLabels(['영역 이름', '적용 대상', '대상 상태'])
            self.regions.setColumnWidth(0, 230)
            self.regions.setColumnWidth(1, 420)
            layout.addWidget(self.regions, 1)
            self.region_label = QtWidgets.QLineEdit('선택 영역')
            self.region_label.setObjectName('femRegionLabel')
            layout.addWidget(self.region_label)
            row = QtWidgets.QHBoxLayout()
            self._button('선택을 영역으로 저장', self.capture_region, row)
            self._button('선택 영역 다시 지정', self.repair_region, row)
            layout.addLayout(row)
            row = QtWidgets.QHBoxLayout()
            self._button('영역 삭제', self.remove_region, row)
            row.addStretch()
            layout.addLayout(row)
            self._section(layout, '기존 조건')
            form = QtWidgets.QFormLayout()
            self.condition = QtWidgets.QComboBox()
            self.condition.setObjectName('femExistingCondition')
            self.condition.currentIndexChanged.connect(self._load_condition)
            form.addRow('조건 선택', self.condition)
            layout.addLayout(form)
            self.condition_message = QtWidgets.QLabel()
            self.condition_message.setWordWrap(True)
            self.condition_message.setVisible(False)
            layout.addWidget(self.condition_message)
            recovery = QtWidgets.QFormLayout()
            self.direction_region = QtWidgets.QComboBox()
            self.direction_region.setObjectName('femRepairForceDirection')
            self.direction_region.addItem('현재 힘 방향 유지', '__keep')
            self.direction_label = QtWidgets.QLabel('복구할 힘 방향')
            recovery.addRow(self.direction_label, self.direction_region)
            layout.addLayout(recovery)
            row = QtWidgets.QHBoxLayout()
            self._button('3D에서 확인', self.highlight_condition, row, mutate=False, name='femHighlightCondition')
            self._button('선택한 면으로 변경', self.repair_condition,
                         row, name='femRepairCondition')
            layout.addLayout(row)
            row = QtWidgets.QHBoxLayout()
            self.edit_condition_button = self._button('FreeCAD에서 조건 편집',
                lambda: self.native_task(self.condition.currentData()), row, name='femEditCondition')
            self.confirm_condition_button = self._button('현재 적용 대상 확인', self.confirm_condition,
                row, name='femConfirmCondition')
            layout.addLayout(row)
            self.displacement_message = QtWidgets.QLabel('지정 변위의 값은 FreeCAD 속성에서 편집합니다. 적용 면은 아래 영역에서 지정하세요.')
            self.displacement_message.setWordWrap(True)
            layout.addWidget(self.displacement_message)
            self.displacement_button = self._button('지정 변위 적용 면 변경', self.apply_condition, layout,
                                                    name='femApplyDisplacementRegion')
            form = QtWidgets.QFormLayout()
            self.analysis, self.new_condition = QtWidgets.QComboBox(), QtWidgets.QComboBox()
            for label, kind in [('고정', 'Fixed'), ('힘', 'Force'), ('지정 변위', 'Displacement')]:
                self.new_condition.addItem(label, kind)
            self._section(layout, '새 조건')
            form.addRow('해석 선택', self.analysis)
            form.addRow('추가할 조건', self.new_condition)
            self.condition_region = QtWidgets.QComboBox()
            form.addRow('적용 영역', self.condition_region)
            self.force = self._number('femInitialForce', minimum=0, value=0)
            form.addRow('초기 힘 [N]', self.force)
            self.new_condition.currentIndexChanged.connect(
                lambda *_: self.force.setEnabled(self.new_condition.currentData() == 'Force'))
            self.force.setEnabled(False)
            layout.addLayout(form)
            self._button('조건 추가', self.create_condition, layout)
            scope = QtWidgets.QLabel('형상을 바꾼 뒤에는 적용 대상을 확인하고 필요한 영역을 다시 지정하세요. 기존 조건은 유지됩니다.')
            scope.setWordWrap(True)
            layout.addWidget(scope)

        def _material_tab(self):
            from .material_panel import add_material_page
            self.material_page = add_material_page(self, QtWidgets, QtCore)

        def _fill_combo(self, widget, entries):
            previous = widget.currentData()
            blocked = widget.blockSignals(True)
            widget.clear()
            for text, data in entries:
                widget.addItem(text, data)
            index = widget.findData(previous)
            if index >= 0:
                widget.setCurrentIndex(index)
            widget.blockSignals(blocked)

        def refresh(self, *, load_forms=True):
            mesh_pending = self._mesh_pending()
            self._description = self.editor.descriptor()
            def label(identifier):
                try:
                    return self.editor.owner._object(identifier).Label
                except Exception:
                    return identifier
            self._fill_combo(self.mesh, [(label(row['object_id']), row['object_id']) for row in self._description['meshes']])
            missing_mesh = bool(self._mesh_form_id and self.mesh.findData(self._mesh_form_id) < 0)
            if missing_mesh:
                blocked = self.mesh.blockSignals(True)
                self.mesh.setCurrentIndex(-1)
                self.mesh.blockSignals(blocked)
                self.status.setPlainText('현재 메시를 찾지 못했습니다. 입력은 유지됩니다. 다른 메시를 명시적으로 선택하세요.')
            self._fill_combo(self.condition, [(label(row['object_id']) + (' (대상 확인 필요)' if row['errors'] else ''), row['object_id'])
                                            for row in self._description['conditions']])
            objs = self.editor.owner.doc.Objects
            def kind(obj):
                return getattr(getattr(obj, 'Proxy', None), 'Type', obj.TypeId)
            self._fill_combo(self.analysis, [(obj.Label, obj.Name) for obj in objs if kind(obj) == 'Fem::FemAnalysis'])
            regions = self._description['regions']
            entries = [(row['label'] + (' (대상 확인 필요)' if row['validation'] != 'EXACT_TARGET_MATCH' else ''), row['id']) for row in regions]
            self._fill_combo(self.local_region, [('적용 영역 선택', None)] + entries)
            self._fill_combo(self.condition_region, entries)
            edge_regions = [(row['label'], row['id']) for row in regions if len(row['target']['subelements']) == 1
                            and row['target']['subelements'][0]['name'].startswith('Edge')]
            self._fill_combo(self.direction_region, [('현재 힘 방향 유지', '__keep'),
                ('선택 면의 법선 방향', None)] + edge_regions)
            selected = self.regions.currentItem()
            selected_id = selected.data(0, 256) if selected else None
            self.regions.clear()
            for row in regions:
                target = row['target']
                names = [item['name'] for item in target['subelements']]
                displayed = [next((word + name[len(prefix):] for prefix, word in
                                  [('Face', '면 '), ('Edge', '모서리 '), ('Vertex', '꼭짓점 ')]
                                  if name.startswith(prefix)), name) for name in names]
                text = label(target['object_id']) + ': ' + (', '.join(displayed) if displayed else '물체 전체')
                state = {'EXACT_TARGET_MATCH': '대상 확인됨', 'UNRESOLVED': '대상 확인 필요'}.get(row['validation'], '상태 미확인')
                item = QtWidgets.QTreeWidgetItem([row['label'], text, state])
                item.setData(0, 256, row['id'])
                item.setToolTip(1, target['object_id'] + ': ' + ', '.join(names))
                item.setToolTip(2, row.get('error') or row['validation'])
                self.regions.addTopLevelItem(item)
                if row['id'] == selected_id:
                    self.regions.setCurrentItem(item)
            self.material_page.refresh(load_forms=load_forms)
            self.contact_page.refresh(load_forms=load_forms)
            self.steps_page.refresh(load_forms=load_forms)
            self.periodic_page.refresh(load_forms=load_forms)
            self.pretension_page.refresh(load_forms=load_forms)
            self.initial_field_page.refresh(load_forms=load_forms)
            self.convergence_page.refresh(load_forms=load_forms)
            if load_forms:
                if not mesh_pending and not missing_mesh:
                    self._load_mesh()
                self._load_condition()
            self.poll()

        def poll(self):
            try:
                description = self.editor.descriptor()
                self._description = description
                self._condition_status()
                busy = description['mesh_busy']
                native_task = bool(self.editor.owner.Gui.Control.activeDialog() or
                    (self.editor.owner.Gui.activeDocument() and self.editor.owner.Gui.activeDocument().getInEdit()))
                for button in self._actions:
                    button.setEnabled(not self._command_busy)
                for button in self._mutating:
                    button.setEnabled(not busy and not native_task and not self._command_busy)
                self._sync_condition_actions()
                self.material_page.sync_actions(busy or native_task)
                self.convergence_page.sync_actions(busy or native_task)
                self.cancel_button.setEnabled(busy and not self._command_busy)
                histories = description['mesh_history']
                stamp = repr(histories[-1]) if histories else None
                if stamp != self._last_history:
                    self._last_history = stamp
                    if histories:
                        row = histories[-1]
                        self.status.setPlainText('Mesh ' + row['mesh_id'] + ': ' + row['state'] +
                            '\nRun admission: ' + row.get('run_admissibility', 'UNKNOWN') +
                            '\nPrevious native mesh: ' + row.get('previous_mesh_object_id', 'original mesh retained') +
                            '\n' + row.get('error', '') + '\n' + row.get('native_log', ''))
                        state = {'QUEUED': '생성 대기', 'RUNNING': '생성 중', 'SUCCEEDED': '생성 완료',
                                 'FAILED': '생성 실패', 'CANCELLED': '생성 취소', 'CANCEL_REQUESTED': '취소 요청 중'}.get(row['state'], '상태 미확인')
                        self.status_summary.setText('메시 '+state+(' / 오류가 있습니다. 상세를 확인하세요.' if row.get('error') else ''))
            except Exception as error:
                self.status.setPlainText(str(error))

        def _load_mesh(self):
            identifier = self.mesh.currentData()
            if not identifier:
                return
            obj = self.editor.owner._object(identifier)
            if identifier != self._mesh_form_id:
                self.element_type.setCurrentIndex(0)
                self.local_region.setCurrentIndex(0)
                blocked = self.refinement.blockSignals(True)
                self.refinement.setCurrentIndex(0)
                self.refinement.blockSignals(blocked)
                self.local_size.setValue(1)
            self.min_size.setValue(float(obj.CharacteristicLengthMin.getValueAs('mm').Value))
            self.max_size.setValue(float(obj.CharacteristicLengthMax.getValueAs('mm').Value))
            order_labels = {'1st': '1차', '2nd': '2차'}
            dimension_labels = {'1D': '1차원', '2D': '2차원', '3D': '3차원'}
            self._fill_combo(self.order, [(order_labels.get(value, value), value) for value in obj.getEnumerationsOfProperty('ElementOrder')])
            self._fill_combo(self.dimension, [(dimension_labels.get(value, value), value) for value in obj.getEnumerationsOfProperty('ElementDimension')])
            self.order.setCurrentIndex(self.order.findData(obj.ElementOrder))
            self.dimension.setCurrentIndex(self.dimension.findData(obj.ElementDimension))
            self._fill_combo(self.refinement, [('새 국부 크기 설정', None)] + [(ref.Label, ref.Name) for ref in obj.MeshRegionList])
            self._mesh_form_id = identifier
            self._load_refinement(self.refinement.currentData())
            self._loaded_mesh_fields = self._mesh_fields()

        def _mesh_fields(self):
            return (self.min_size.value(), self.max_size.value(), self.order.currentData(),
                    self.dimension.currentData(), self.element_type.currentData(),
                    self.local_region.currentData(), self.refinement.currentData(), self.local_size.value())

        def _mesh_pending(self):
            return self._mesh_fields() != getattr(self, '_loaded_mesh_fields', self._mesh_fields())

        def _set_local_fields(self, fields):
            self.local_region.setCurrentIndex(self.local_region.findData(fields[0]))
            blocked = self.refinement.blockSignals(True)
            self.refinement.setCurrentIndex(self.refinement.findData(fields[1]))
            self.refinement.blockSignals(blocked)
            self.local_size.setValue(fields[2])

        def _load_refinement(self, identifier):
            mesh = self.editor.owner._object(self.mesh.currentData())
            region, size = None, 1
            if identifier:
                obj = self.editor.owner._object(identifier)
                if obj not in mesh.MeshRegionList:
                    raise ValueError('이 국부 크기는 현재 메시의 설정이 아닙니다. 현재 부품에서 다시 선택하세요.')
                size = float(obj.CharacteristicLength.getValueAs('mm').Value)
                if not self.local_size.minimum() <= size <= self.local_size.maximum():
                    raise ValueError('저장된 국부 크기를 이 입력란에 표시할 수 없습니다. FreeCAD에서 크기와 단위를 확인하세요.')
                records = self.editor.owner.read_metadata().get('mesh_local_sizes', [])
                rows = [row for row in records if isinstance(row, dict)
                        and row.get('mesh_id') == mesh.Name and row.get('object_id') == identifier] if isinstance(records, list) else []
                if len(rows) == 1:
                    region = rows[0].get('region_id')
                if self.local_region.findData(region) < 0 or region is None:
                    region = None
                    self.status.setPlainText('이 국부 크기의 적용 영역을 찾지 못했습니다. 영역을 다시 선택하고 국부 크기를 적용하세요.')
                else:
                    try:
                        target_errors = [error for error in self.editor._refinement_errors(mesh)
                                         if error.startswith(obj.Name + ': ')]
                    except Exception:
                        target_errors = ['unverified target']
                    if target_errors:
                        region = None
                        self.status.setPlainText('이 국부 크기의 저장된 대상이 현재 형상·면과 일치하는지 확인할 수 없습니다. 영역을 다시 선택하고 국부 크기를 적용하세요.')
            self._set_local_fields((region, identifier, size))
            if hasattr(self, '_loaded_mesh_fields'):
                self._loaded_mesh_fields = self._loaded_mesh_fields[:5] + self._mesh_fields()[5:]

        def _refinement_changed(self):
            identifier = self.refinement.currentData()
            if not hasattr(self, '_loaded_mesh_fields'):
                return
            previous = self._loaded_mesh_fields[6]
            if identifier == previous:
                return
            blocked = self.refinement.blockSignals(True)
            self.refinement.setCurrentIndex(self.refinement.findData(previous))
            self.refinement.blockSignals(blocked)
            if self._command_busy or self.editor.descriptor()['mesh_busy']:
                raise ValueError('메시 작업을 마친 뒤 다른 국부 크기를 선택하세요. 현재 입력은 유지됩니다.')
            if self._mesh_fields()[5:] != self._loaded_mesh_fields[5:]:
                self._resolve_mesh_draft(lambda: self._load_refinement(identifier), '선택', local_only=True)
            else:
                self._load_refinement(identifier)
            self.refinement.setFocus()

        def _mesh_changed(self):
            identifier = self.mesh.currentData()
            if not self._mesh_form_id or identifier == self._mesh_form_id:
                self._load_mesh()
                return
            blocked = self.mesh.blockSignals(True)
            self.mesh.setCurrentIndex(self.mesh.findData(self._mesh_form_id))
            self.mesh.blockSignals(blocked)
            if self._command_busy or self.editor.descriptor()['mesh_busy']:
                raise ValueError('메시 작업을 마친 뒤 다른 부품을 선택하세요. 현재 선택과 입력은 유지됩니다.')
            if self._mesh_pending():
                self._resolve_mesh_draft(lambda: self.open_mesh_settings(identifier), '선택')
                self.mesh.setFocus()
            else:
                self.open_mesh_settings(identifier)

        def _discard_mesh_draft(self):
            fields = self._loaded_mesh_fields
            self.min_size.setValue(fields[0])
            self.max_size.setValue(fields[1])
            for widget, value in zip((self.order, self.dimension, self.element_type), fields[2:5]):
                widget.setCurrentIndex(widget.findData(value))
            self._set_local_fields(fields[5:])
            self._load_mesh()

        def _resolve_mesh_draft(self, proceed, action, *, on_cancelled=None, local_only=False):
            owner, doc = self.editor.owner, self.editor.owner.doc
            session = getattr(owner, 'session_id', None)
            def fields():
                return self._mesh_fields()[5:] if local_only else self._mesh_fields()
            identifier, epoch, submitted = self._mesh_form_id, self._view_epoch, fields()
            cancelled = False
            def cancel(*unused):
                nonlocal cancelled
                if not cancelled and on_cancelled:
                    cancelled = True
                    on_cancelled()
            dialog = QtWidgets.QMessageBox(self)
            dialog.setWindowTitle('미적용 국부 크기' if local_only else '미적용 메시 설정')
            dialog.setText('변경한 국부 크기를 어떻게 처리할까요?' if local_only else '현재 메시의 변경한 설정을 어떻게 처리할까요?')
            dialog.setInformativeText('국부 크기만 적용합니다. 미적용 전역 설정은 유지됩니다. 메시 생성은 별도 동작입니다.'
                                      if local_only else '적용은 현재 부품의 설정만 변경합니다. 메시 생성은 별도 동작입니다.')
            apply = dialog.addButton('적용 후 ' + action, QtWidgets.QMessageBox.AcceptRole)
            discard = dialog.addButton('버리고 ' + action, QtWidgets.QMessageBox.DestructiveRole)
            cancel_button = dialog.addButton('취소', QtWidgets.QMessageBox.RejectRole)
            dialog.setDefaultButton(cancel_button)
            dialog.setEscapeButton(cancel_button)
            dialog.exec()
            if (self.editor.owner is not owner or owner.doc is not doc or getattr(owner, 'closed', False)
                    or getattr(owner, 'session_id', None) != session):
                cancel()
                raise ValueError('STALE_SESSION: the mesh draft belongs to the earlier document/session')
            if dialog.clickedButton() not in (apply, discard):
                cancel()
                return
            if (epoch != self._view_epoch or fields() != submitted or self._command_busy
                    or self.editor.descriptor()['mesh_busy']):
                cancel()
                raise ValueError('선택 확인 중 입력이나 작업 상태가 바뀌었습니다. 현재 메시와 입력을 유지합니다.')
            if dialog.clickedButton() is discard:
                if local_only:
                    self._set_local_fields(self._loaded_mesh_fields[5:])
                else:
                    self._discard_mesh_draft()
                proceed()
            elif dialog.clickedButton() is apply:
                if identifier != self.mesh.currentData():
                    cancel()
                    raise ValueError('현재 메시를 찾지 못해 설정을 적용할 수 없습니다. 입력을 버리거나 원 대상을 복구하세요.')
                def continued():
                    if epoch != self._view_epoch or identifier != self.mesh.currentData():
                        cancel()
                        return
                    if fields() != submitted:
                        self.status.setPlainText('새로 수정한 입력이 있어 현재 메시를 유지합니다. 미적용 설정을 확인하세요.')
                        cancel()
                        return
                    if not local_only and self._mesh_fields()[:5] != self._loaded_mesh_fields[:5]:
                        self.apply_mesh_settings(on_done=continued, on_error=cancel)
                    elif self._mesh_fields()[5:] != self._loaded_mesh_fields[5:]:
                        self.apply_local_size(on_done=continued, on_error=cancel)
                    else:
                        proceed()
                continued()

        def request_mesh_close(self, on_accepted, *, on_cancelled=None):
            """Resolve this mesh form before its owning document is closed."""
            if self._command_busy or self.editor.descriptor()['mesh_busy']:
                raise ValueError('메시 작업을 마친 뒤 문서를 닫으세요. 현재 입력은 유지됩니다.')
            if self._mesh_pending():
                self._resolve_mesh_draft(on_accepted, '닫기', on_cancelled=on_cancelled)
            else:
                on_accepted()

        def open_mesh_settings(self, identifier):
            """Select the exact prepared mesh without discarding another form."""
            if self._command_busy or self.editor.descriptor()['mesh_busy']:
                raise ValueError('메시 작업을 마친 뒤 다른 부품을 선택하세요.')
            previous = self.mesh.currentData()
            if previous != identifier and self._mesh_pending():
                raise ValueError('현재 메시의 미적용 설정을 적용하거나 되돌린 뒤 다른 부품의 메시 설정을 여세요.')
            self.refresh(load_forms=False)
            index = self.mesh.findData(identifier)
            if index < 0:
                raise ValueError('선택한 부품의 메시가 없습니다. 부품을 다시 선택하세요.')
            if previous != identifier:
                blocked = self.mesh.blockSignals(True)
                self.mesh.setCurrentIndex(index)
                self.mesh.blockSignals(blocked)
                self._load_mesh()
            self.tabs.setCurrentIndex(0)
            self.mesh.setFocus()

        def _load_condition(self):
            identifier = self.condition.currentData()
            if identifier:
                row = next((row for row in self._description.get('conditions', [])
                            if row['object_id'] == identifier), {})
                index = self.condition_region.findData(row.get('region_id'))
                if index >= 0:
                    self.condition_region.setCurrentIndex(index)
            self._condition_status()
            self._sync_condition_actions()

        def _sync_condition_actions(self):
            identifier = self.condition.currentData()
            obj = self.editor.owner._object(identifier) if identifier else None
            displacement = bool(obj and obj.TypeId == 'Fem::ConstraintDisplacement')
            self.displacement_message.setVisible(displacement)
            self.displacement_button.setVisible(displacement)
            self.edit_condition_button.setVisible(not displacement)
            row = next((row for row in self._description.get('conditions', [])
                        if row['object_id'] == identifier), {})
            self.confirm_condition_button.setVisible(bool(row.get('errors')) and not displacement)
            direction_recovery = bool(obj and obj.TypeId == 'Fem::ConstraintForce' and row.get('errors'))
            if not direction_recovery or identifier != getattr(self, '_direction_condition_id', None):
                blocked = self.direction_region.blockSignals(True)
                self.direction_region.setCurrentIndex(self.direction_region.findData('__keep'))
                self.direction_region.blockSignals(blocked)
            self._direction_condition_id = identifier
            self.direction_region.setVisible(direction_recovery)
            self.direction_label.setVisible(direction_recovery)

        def apply_mesh_settings(self, *, on_done=None, on_error=None):
            args = {'min_size': self.min_size.value(), 'max_size': self.max_size.value(), 'unit': 'mm',
                    'element_order': self.order.currentData(), 'element_dimension': self.dimension.currentData()}
            if self.element_type.currentData():
                args['element_type'] = self.element_type.currentData()
            identifier, submitted = self.mesh.currentData(), self._mesh_fields()[:5]
            def applied(result):
                if identifier == self.mesh.currentData():
                    self._loaded_mesh_fields = submitted + self._loaded_mesh_fields[5:]
                self.status.setPlainText('메시 설정을 적용했습니다. 메시 생성은 별도로 실행하세요.')
                if on_done:
                    on_done()
            self._send('pre.fem.mesh_settings', args, identifier, on_done=applied, on_error=on_error)

        def apply_local_size(self, *, on_done=None, on_error=None):
            if self.local_region.currentData() is None:
                raise ValueError('국부 크기를 적용할 영역을 선택하세요.')
            args = {'region_id': self.local_region.currentData(), 'size': self.local_size.value(), 'unit': 'mm'}
            if self.refinement.currentData():
                args['refinement_id'] = self.refinement.currentData()
            identifier, submitted = self.mesh.currentData(), self._mesh_fields()[5:]
            def applied(result):
                if identifier == self.mesh.currentData():
                    self.refresh(load_forms=False)
                    obj = self.editor.owner._object(identifier)
                    self._fill_combo(self.refinement, [('새 국부 크기 설정', None)] + [(ref.Label, ref.Name) for ref in obj.MeshRegionList])
                    self._loaded_mesh_fields = self._loaded_mesh_fields[:5] + submitted
                self.status.setPlainText('국부 요소 크기를 적용했습니다. 메시 생성은 별도로 실행하세요.')
                if on_done:
                    on_done()
            self._send('pre.fem.mesh_local_size', args, identifier, on_done=applied, on_error=on_error)

        def generate_mesh(self):
            if self._command_busy or self.editor.descriptor()['mesh_busy']:
                raise ValueError('메시 작업을 마친 뒤 다시 생성하세요. 현재 입력은 유지됩니다.')
            if self._mesh_pending():
                self._resolve_mesh_draft(self._generate_mesh, '생성')
            else:
                self._generate_mesh()

        def _generate_mesh(self):
            self._send('pre.fem.mesh_generate', {}, self.mesh.currentData(), on_done=lambda result:
                self.status.setPlainText('메시 생성 상태: ' + {'QUEUED': '대기 중', 'RUNNING': '생성 중', 'SUCCEEDED': '완료',
                    'FAILED': '실패', 'CANCELLED': '취소'}.get(result['state'], '미확인') + '\nNative Gmsh ' + result['state'] + '; receipt ' + result['history_id']))

        def cancel_mesh(self):
            description = self.editor.descriptor()
            rows = description['active_mesh_generations']
            if not rows:
                raise ValueError('생성 중인 메시가 없습니다.')
            selected = next((row for row in rows if row['mesh_id'] == self.mesh.currentData()), rows[0])
            self._send('pre.fem.mesh_cancel', {'history_id': selected['history_id']}, selected['mesh_id'])

        def read_quality(self):
            identifier = self.mesh.currentData()
            def show(data):
                if identifier != self.mesh.currentData() or data['mesh_id'] != identifier:
                    raise ValueError('STALE_SELECTION: quality receipt belongs to the earlier selected mesh')
                self._show_quality(data)
            self._send('pre.fem.mesh_quality', {'offset': self.offset.value(), 'limit': 200}, identifier, on_done=show)

        def _show_quality(self, data):
            self._quality_data = data
            self.quality.setRowCount(len(data['rows']))
            for i, row in enumerate(data['rows']):
                values = [row['element_id'], row['element_type'], row.get('minimum_sampled_jacobian_mm3'),
                          row.get('minimum_scaled_sampled_jacobian'), ', '.join(row['errors'])]
                for j, value in enumerate(values):
                    item = QtWidgets.QTableWidgetItem('미확인' if value is None else str(value))
                    if j == 4:
                        reasons = {'INVALID_OR_UNSUPPORTED_CONNECTIVITY': '절점 연결 또는 요소 종류 확인',
                                   'JACOBIAN_AT_OR_BELOW_1E_10_MM3': '야코비안 1e-10 mm³ 이하',
                                   'NORMALIZED_JACOBIAN_SINGULAR': '정규화 야코비안 특이'}
                        item.setText(', '.join(reasons.get(v, '확인 필요') for v in row['errors']))
                        item.setToolTip(', '.join(row['errors']))
                    self.quality.setItem(i, j, item)
            distributions = []
            for name, measure in [('표본 J [mm³]', data['absolute_jacobian_mm3']), ('정규화 J', data['normalized_jacobian'])]:
                distributions.extend((name, row['lower'], row['upper'], row['count']) for row in measure['bins'])
            self.distribution.setRowCount(len(distributions))
            for i, values in enumerate(distributions):
                for j, value in enumerate(values):
                    self.distribution.setItem(i, j, QtWidgets.QTableWidgetItem(str(value)))
            self.distribution.setVisible(bool(distributions))
            self.quality.setColumnWidth(0, 100)
            self.quality.setColumnWidth(1, 110)
            self.quality.setColumnWidth(2, 180)
            self.quality.setColumnWidth(3, 150)
            self.status.setPlainText(str(data['total_elements']) + ' native elements; ' + str(data['bad_element_count']) +
                ' fail the preserved absolute/normalized Jacobian or C3D10 type gates. ' + data['limitation'])
            self.status_summary.setText('요소 '+str(data['total_elements'])+'개를 조회했습니다. 확인이 필요한 요소는 '+str(data['bad_element_count'])+'개입니다.')

        def highlight_quality(self):
            if not hasattr(self, '_quality_data'):
                raise ValueError('메시 품질을 먼저 조회하세요.')
            rows = sorted({index.row() for index in self.quality.selectedIndexes()})
            if not rows:
                raise ValueError('표에서 표시할 요소 행을 선택하세요.')
            data = self._quality_data
            args = {'element_ids': [data['rows'][index]['element_id'] for index in rows]}
            if data['mesh_sha256']:
                args['mesh_sha256'] = data['mesh_sha256']
            self._send('pre.fem.mesh_highlight', args, data['mesh_id'])

        def _selection(self):
            rows = self.editor.owner.Gui.Selection.getSelectionEx(self.editor.owner.doc.Name)
            if not rows or len({row.Object.Name for row in rows}) != 1:
                raise ValueError('3D에서 한 물체 또는 그 물체의 면이나 모서리를 선택하세요.')
            obj = rows[0].Object
            if obj.Document is not self.editor.owner.doc:
                raise ValueError('선택한 대상이 다른 문서에 있습니다. 현재 문서에서 다시 선택하세요.')
            names = list(dict.fromkeys(name for row in rows for name in row.SubElementNames))
            return obj.Name, names

        def capture_region(self):
            object_id, names = self._selection()
            self._send('pre.fem.region_set', {'label': self.region_label.text(), 'subelements': names}, object_id, on_done=self._refresh_after)

        def repair_region(self):
            selected = self.regions.currentItem()
            if selected is None:
                raise ValueError('다시 지정할 영역을 목록에서 선택하세요.')
            row = next(row for row in self._description['regions'] if row['id'] == selected.data(0, 256))
            object_id, names = self._selection()
            self._send('pre.fem.region_set', {'region_id': row['id'], 'label': self.region_label.text(), 'subelements': names,
                                            'expected_target_sha256': row['target_sha256']}, object_id, on_done=self._refresh_after)

        def remove_region(self):
            item = self.regions.currentItem()
            if item is None:
                raise ValueError('삭제할 영역을 목록에서 선택하세요.')
            self._send('pre.fem.region_remove', {'region_id': item.data(0, 256)}, on_done=self._refresh_after)

        def highlight_condition(self):
            row = next(row for row in self.editor.descriptor()['conditions'] if row['object_id'] == self.condition.currentData())
            objects = [{'object_id': ref['object_id'], 'subelement': name}
                       for ref in row.get('native_references', []) for name in ref['subelements']]
            if not objects:
                raise ValueError('STALE_TARGET: this condition has no current native faces to highlight')
            self._send('pre.select', {'objects': objects}, on_done=lambda result:
                self.status.setPlainText('Actual current condition targets selected in the native 3D view. Review them before confirming or repairing.'))

        def repair_condition(self):
            condition_id = self.condition.currentData()
            if not condition_id:
                raise ValueError('대상을 바꿀 조건을 선택하세요.')
            object_id, names = self._selection()
            if not names or any(not name.startswith('Face') for name in names):
                raise ValueError('3D에서 이 조건을 적용할 면을 선택하세요.')
            obj = self.editor.owner._object(condition_id)
            direction_args = {}
            if (obj.TypeId == 'Fem::ConstraintForce' and not self.direction_region.isHidden()
                    and self.direction_region.currentData() != '__keep'):
                direction_args['direction_region_id'] = self.direction_region.currentData()
            initial_serial = self._edit_serial
            def region_ready(region):
                if self.condition.currentData() != condition_id or self._selection() != (object_id, names):
                    raise ValueError('STALE_SELECTION: condition/3D selection changed; prepared region retained, repair not applied')
                def repaired(result):
                    self._completion_serial = initial_serial
                    self._refresh_after()
                    self.status.setPlainText('Existing condition ' + condition_id + ' explicitly confirmed/repaired. Engineering release remains NOT_RELEASED.')
                self._send('pre.fem.condition_repair', {**direction_args, 'region_id': region['id']}, condition_id, on_done=repaired)
            self._send('pre.fem.region_set', {'label': (obj.Label + ' 적용 면')[:160],
                'subelements': names}, object_id, on_done=region_ready)

        def confirm_condition(self):
            identifier = self.condition.currentData()
            if not identifier:
                raise ValueError('적용 대상을 확인할 조건을 선택하세요.')
            self._send('pre.fem.condition_repair', {'use_native_references': True}, identifier,
                       on_done=self._refresh_after)

        def apply_condition(self):
            identifier = self.condition.currentData()
            if self.editor.owner._object(identifier).TypeId != 'Fem::ConstraintDisplacement':
                raise ValueError('고정과 힘은 FreeCAD에서 조건 편집을 사용하세요.')
            self._send('pre.fem.condition_set', {'region_id': self.condition_region.currentData()},
                       identifier, on_done=self._refresh_after)

        def create_condition(self):
            kind = self.new_condition.currentData()
            args = {'kind': kind, 'region_id': self.condition_region.currentData()}
            if kind == 'Force':
                args.update(force=self.force.value(), unit='N')
            def created(result):
                self._refresh_after()
                identifier = result['object_id']
                if self._edit_serial != self._completion_serial:
                    self.status.setPlainText('조건을 추가했습니다. 현재 편집을 유지합니다. 조건 목록에서 새 조건을 선택해 편집하세요.')
                    return
                self.condition.setCurrentIndex(self.condition.findData(identifier))
                if kind != 'Displacement':
                    self.native_task(identifier)
            self._send('pre.fem.condition_set', args, self.analysis.currentData(), on_done=created)

        def native_task(self, identifier):
            if not identifier:
                raise ValueError('FreeCAD에서 편집할 객체를 선택하세요.')
            self._send('pre.fem.task_edit', {}, identifier)

    return Panel()
