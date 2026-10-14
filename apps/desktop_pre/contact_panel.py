"""Contact page injected into the existing native FEM panel (FreeCAD's Qt)."""


def add_contact_page(panel, W, C):
    class Page(W.QWidget):
        def __init__(self):
            super().__init__()
            self.rows, self.loading = [], False
            layout = W.QVBoxLayout(self)
            self.pair = W.QComboBox()
            self.pair.setObjectName('contactPair')
            self.pair.currentIndexChanged.connect(self.load_pair)
            layout.addWidget(self.pair)
            form = W.QFormLayout()
            form.setVerticalSpacing(3)
            self.label = W.QLineEdit('접촉')
            self.label.setObjectName('contactName')
            form.addRow('이름', self.label)
            self.sides = {}
            for side, label in [('a', 'A 면 (slave)'), ('b', 'B 면 (master)')]:
                row = W.QHBoxLayout()
                combo = W.QComboBox()
                combo.setObjectName('contactSide' + side.upper())
                row.addWidget(combo, 1)
                panel._button('선택한 면 사용', lambda side=side: self.capture(side), row)
                panel._button('면 재지정…', lambda side=side: self.preview(side), row)
                form.addRow(label, row)
                self.sides[side] = combo
                combo.currentIndexChanged.connect(lambda *args: self.edited())
            self.fields = {}
            choices = {
                'normal_law': [('법칙 선택', None), ('선형 압력–침투', 'linear'),
                               ('강체 접촉 (미지원)', 'hard'), ('응집 법칙 (미지원)', 'cohesive')],
                'tangential_law': [('법칙 선택', None), ('마찰 없음', 'frictionless'), ('쿨롱 마찰', 'coulomb')],
                'gap_policy': [('실제 형상', 'geometry'), ('균일한 설정 간극', 'prescribed')],
                'normal': [('고체 바깥쪽 법선', 'outward_solid'), ('법선 반전 (미지원)', 'reversed')],
                'sliding': [('면 대 면', 'surface_to_surface'), ('작은 미끄럼 (미지원)', 'small')],
                'step': [('전체 단계', 'Step1')],
                'activation': [('전체 단계 유지', 'whole_step'), ('단계 중간 활성화 (미지원)', 'interval')],
            }
            labels = [('normal_law', '법선 법칙'), ('normal_stiffness_MPa_per_mm', '법선 강성 [MPa/mm]'),
                ('tangential_law', '마찰 법칙'), ('friction_coefficient', '마찰계수'),
                ('stick_stiffness_MPa_per_mm', '접선 강성 [MPa/mm]'), ('gap_policy', '간극 정책'),
                ('nominal_gap_mm', '설정 간극 [mm]'), ('adjustment_mm', '절점 조정 [mm] (미지원)'),
                ('normal', '법선'), ('sliding', '접촉 방식'), ('step', '작용 단계'),
                ('activation', '활성화')]
            for key, label in labels:
                if key in choices:
                    widget = W.QComboBox()
                    for text, value in choices[key]:
                        widget.addItem(text, value)
                    widget.currentIndexChanged.connect(lambda *args: self.edited())
                else:
                    widget = W.QLineEdit()
                    widget.textEdited.connect(lambda *args: self.edited())
                widget.setObjectName('contact_' + key)
                self.fields[key] = widget
                form.addRow(label, widget)
            self.label.textEdited.connect(panel._edited)
            layout.addLayout(form)
            row = W.QHBoxLayout()
            panel._button('접촉 적용', self.apply, row, name='contactApply')
            panel._button('A/B 교환', lambda: self.action('swap'), row)
            panel._button('면 보기', lambda: self.action('highlight'), row, mutate=False)
            panel._button('방향과 거리…', self.inspect_geometry, row, mutate=False)
            panel._button('접촉 삭제', lambda: self.action('remove'), row)
            layout.addLayout(row)
            panel._button('물체별 메시 준비', self.prepare, layout, name='contactPrepareMeshes')
            self.diagnostics = W.QListWidget()
            self.diagnostics.setObjectName('contactDiagnostics')
            self.diagnostics.itemActivated.connect(self.focus_error)
            layout.addWidget(self.diagnostics, 1)
            panel.tabs.addTab(self, '접촉')

        def edited(self):
            if not self.loading:
                panel._edited()

        def selected(self):
            return next((row for row in self.rows if row['object_id'] == self.pair.currentData()), None)

        def refresh(self, *, load_forms):
            self.rows = panel.editor.contact.descriptor()['pairs']
            panel._fill_combo(self.pair, [('새 접촉', None)] +
                              [(row['draft']['label'], row['object_id']) for row in self.rows])
            for side, combo in self.sides.items():
                regions = [(row['label'], row['id']) for row in panel._description['regions']
                           if row['target']['subelements'] and
                           all(face['name'].startswith('Face') for face in row['target']['subelements'])]
                selected = self.selected()
                # Rebound faces may intentionally have no shared named region.
                label = selected[side]['label'] if selected and selected.get(side) else '면 선택'
                panel._fill_combo(combo, [(label, None)] + regions)
            if load_forms:
                self.load_pair()

        def load_pair(self, *unused):
            if not self.fields:
                return
            from caelab.contact import default_contact
            selected = self.selected()
            draft = selected['draft'] if selected else default_contact()
            self.loading = True
            try:
                self.label.setText(draft['label'])
                for side, combo in self.sides.items():
                    combo.setCurrentIndex(max(0, combo.findData(draft.get(side + '_region_id'))))
                for key, widget in self.fields.items():
                    value = draft.get(key)
                    if isinstance(widget, W.QComboBox):
                        index = widget.findData(value)
                        if index < 0:
                            widget.addItem(str(value) + ' — unsupported', value)
                            index = widget.count() - 1
                        widget.setCurrentIndex(index)
                    else:
                        widget.setText('' if value is None else str(value))
                self.diagnostics.clear()
                for error in selected.get('diagnostics', []) if selected else []:
                    item = W.QListWidgetItem(error['message'])
                    item.setData(256, error['path'])
                    self.diagnostics.addItem(item)
            finally:
                self.loading = False

        def focus_error(self, item):
            path = item.data(256)
            widget = self.sides.get(path) or self.fields.get(path)
            if widget is not None:
                widget.setFocus()

        def draft(self):
            result = {'label': self.label.text()}
            result.update({key: widget.currentData() if isinstance(widget, W.QComboBox) else widget.text()
                           for key, widget in self.fields.items()})
            selected = self.selected()
            for side, combo in self.sides.items():
                value = combo.currentData()
                if value is not None or not selected or not selected.get(side):
                    result[side + '_region_id'] = value
            return result

        def apply(self):
            identifier = self.pair.currentData() or panel.analysis.currentData()
            if not identifier:
                raise ValueError('Create or choose a native FEM Analysis')
            submitted_pair, serial = self.pair.currentData(), panel._edit_serial
            def done(record):
                same_selection = self.pair.currentData() == submitted_pair
                untouched = panel._edit_serial == serial
                panel.refresh(load_forms=False)
                if same_selection:
                    blocked = self.pair.blockSignals(True)
                    self.pair.setCurrentIndex(self.pair.findData(record['object_id']))
                    self.pair.blockSignals(blocked)
                    if untouched:
                        self.load_pair()
                panel.status.setPlainText('Contact draft applied. Save uses the native project; Run checks faces, mesh and effective law.')
            panel._send('pre.contact.set', {'draft': self.draft()}, identifier, on_done=done)

        def capture(self, side):
            object_id, names = panel._selection()
            if not names or any(not name.startswith('Face') for name in names):
                raise ValueError('Select faces on one body in the 3D view')
            pair_id, serial = self.pair.currentData(), panel._edit_serial
            def ready(record):
                if self.pair.currentData() != pair_id or panel._edit_serial != serial:
                    raise ValueError('Selection/edit changed; the named faces remain available')
                panel.refresh(load_forms=False)
                self.sides[side].setCurrentIndex(self.sides[side].findData(record['id']))
                panel._edited()
            panel._send('pre.fem.region_set', {'label': self.label.text() + ' ' + side.upper(),
                        'subelements': names}, object_id, on_done=ready)

        def action(self, operation):
            if not self.pair.currentData():
                raise ValueError('Choose an existing contact pair')
            callback = (lambda result: panel.status.setPlainText('Contact faces selected in the native view.')) if operation == 'highlight' else panel._refresh_after
            panel._send('pre.contact.' + operation, {}, self.pair.currentData(), on_done=callback)

        def inspect_geometry(self):
            if not self.pair.currentData():
                raise ValueError('접촉을 적용한 뒤 면 방향과 거리를 확인하세요')
            def done(result):
                dialog=W.QDialog(self); dialog.setWindowTitle('접촉면 방향과 거리')
                layout=W.QVBoxLayout(dialog)
                nearest=result['nearest']
                layout.addWidget(W.QLabel('형상 최소 거리: '+format(nearest['distance_mm'],'.10g')+' mm'))
                layout.addWidget(W.QLabel('부호 없는 면 사이 거리입니다. 침투량이나 설정 간극이 아닙니다.'))
                table=W.QTableWidget(0,5)
                table.setHorizontalHeaderLabels(['면 집합','면','면적 [mm²]','중심 [mm]','바깥 법선 XYZ'])
                for side in ('a','b'):
                    for face in result['sides'][side]['faces']:
                        row=table.rowCount(); table.insertRow(row)
                        values=[side.upper()+' '+result['sides'][side]['label'],face['name'],
                            format(face['area_mm2'],'.8g'),
                            ', '.join(format(v,'.6g') for v in face['centroid_mm']),
                            ', '.join(format(v,'.6g') for v in face['center_normal'])]
                        for j,v in enumerate(values): table.setItem(row,j,W.QTableWidgetItem(v))
                table.setEditTriggers(W.QAbstractItemView.EditTrigger.NoEditTriggers)
                table.resizeColumnsToContents(); layout.addWidget(table,1)
                button=W.QDialogButtonBox(W.QDialogButtonBox.StandardButton.Close)
                button.rejected.connect(dialog.reject); layout.addWidget(button)
                dialog.resize(780,420); dialog.exec()
            panel._send('pre.contact.geometry',{},self.pair.currentData(),on_done=done)

        def prepare(self):
            selected = self.selected()
            identifier = selected['analysis_id'] if selected else panel.analysis.currentData()
            def ready(result):
                panel._refresh_after()
                panel.tabs.setCurrentIndex(0)
                if result['meshes']:
                    panel.mesh.setCurrentIndex(panel.mesh.findData(result['meshes'][0]['mesh_id']))
                panel.status.setPlainText('Separate body meshes prepared. Set size and Generate each body; existing meshes are retained.')
            panel._send('pre.contact.prepare_meshes', {}, identifier, on_done=ready)

        def preview(self, side):
            identifier = self.pair.currentData()
            if not identifier:
                raise ValueError('Apply the draft before rebinding its faces')
            object_id, names = panel._selection()
            def ready(result):
                dialog = W.QDialog(self)
                dialog.setWindowTitle('Rebind ' + side.upper())
                layout = W.QVBoxLayout(dialog)
                table = W.QTableWidget(4, 3)
                table.setHorizontalHeaderLabels(['Measure', 'Saved faces', 'Selected faces'])
                for index, (key, label) in enumerate([('face_count', 'Faces'), ('area_mm2', 'Area (mm²)'),
                                                     ('centroid_mm', 'Center (mm)'), ('face_normals', 'Face normals (x,y,z)')]):
                    values = [label, result['old'][key], result['new'][key]]
                    for column, value in enumerate(values):
                        table.setItem(index, column, W.QTableWidgetItem(str(value)))
                table.setEditTriggers(W.QAbstractItemView.EditTrigger.NoEditTriggers)
                table.resizeColumnsToContents()
                layout.addWidget(table)
                dialog.resize(660, 300)
                buttons = W.QDialogButtonBox(W.QDialogButtonBox.StandardButton.Apply |
                                             W.QDialogButtonBox.StandardButton.Cancel)
                buttons.button(W.QDialogButtonBox.StandardButton.Apply).clicked.connect(dialog.accept)
                buttons.rejected.connect(dialog.reject)
                layout.addWidget(buttons)
                accepted = dialog.exec() == W.QDialog.DialogCode.Accepted
                operation = 'apply_rebind' if accepted else 'cancel_rebind'
                panel._send('pre.contact.' + operation, {'preview_id': result['preview_id']},
                            identifier if accepted else None, on_done=panel._refresh_after if accepted else
                            lambda result: panel.status.setPlainText('Rebind cancelled. Current contact edits retained.'))
            panel._send('pre.contact.preview_rebind', {'side': side,
                'selection': {'object_id': object_id, 'subelements': names}}, identifier, on_done=ready)

    return Page()
