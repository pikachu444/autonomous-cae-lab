"""Injected native Qt FEM panel. All edits go through the typed owner commands.

make_panel(QtWidgets, QtCore, editor, submit) takes FreeCAD's installed Qt
bindings; this module imports no PySide distribution. submit(op, args, target,
on_done=None) uses the shared asynchronous native command transport and returns
{'queued': True}; its callback receives the terminal payload/envelope.
"""


def make_panel(QtWidgets, QtCore, editor, submit):
    class Panel(QtWidgets.QWidget):
        def __init__(self):
            super().__init__()
            self.setObjectName('caelabFemPanel')
            self.editor, self.submit = editor, submit
            self._description, self._mutating, self._last_history = {}, [], None
            self._actions, self._command_busy, self._edit_serial = [], False, 0
            outer = QtWidgets.QVBoxLayout(self)
            row = QtWidgets.QHBoxLayout()
            row.addWidget(QtWidgets.QLabel('Native FEM — explicit mesh and target edits'))
            self.refresh_button = self._button('Refresh actual document', self.refresh, row, mutate=False)
            self.cancel_button = self._button('Cancel mesh generation', self.cancel_mesh, row, mutate=False)
            outer.addLayout(row)
            self.tabs = QtWidgets.QTabWidget()
            outer.addWidget(self.tabs, 1)
            self._mesh_tab()
            self._region_tab()
            self._material_tab()
            from .contact_panel import add_contact_page
            self.contact_page = add_contact_page(self, QtWidgets, QtCore)
            self.status = QtWidgets.QPlainTextEdit()
            self.status.setObjectName('femStatus')
            self.status.setReadOnly(True)
            self.status.setMaximumHeight(110)
            outer.addWidget(self.status)
            for field, signal in [(self.min_size, 'valueChanged'), (self.max_size, 'valueChanged'),
                    (self.order, 'currentIndexChanged'), (self.dimension, 'currentIndexChanged'),
                    (self.element_type, 'currentIndexChanged'), (self.local_size, 'valueChanged'),
                    (self.local_region, 'currentIndexChanged'), (self.refinement, 'currentIndexChanged'),
                    (self.region_label, 'textChanged'), (self.condition, 'currentIndexChanged'),
                    (self.condition_region, 'currentIndexChanged'), (self.direction_region, 'currentIndexChanged'),
                    (self.force, 'valueChanged'), (self.reversed, 'toggled'),
                    (self.modulus, 'valueChanged'), (self.poisson, 'valueChanged')]:
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

        def _send(self, operation, args=None, object_id=None, on_done=None):
            if self._command_busy:
                raise ValueError('A foreground native command is pending; wait for its receipt')
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
                self._completion_serial = serial
                try:
                    if self.editor.owner is not owner or owner.doc is not doc or getattr(owner, 'closed', False) or getattr(owner, 'session_id', None) != session:
                        raise ValueError('STALE_SESSION: the native command receipt belongs to the earlier document/session')
                    if not isinstance(result, dict):
                        raise ValueError('The native command returned no acknowledged result')
                    if result.get('status') == 'FAILED':
                        error = result.get('error', {})
                        raise ValueError(error.get('message', str(error)))
                    payload = result.get('result', result)
                    if on_done:
                        on_done(payload)
                except Exception as error:
                    self.status.setPlainText(str(error))
                finally:
                    self.poll()
            try:
                result = self.submit(operation, args or {}, {'object_id': object_id} if object_id else {}, on_done=done)
                if isinstance(result, dict) and not result.get('queued') and not delivered:
                    done(result)  # Explicit immediate receipts remain useful for injected local checks.
            except Exception:
                self._command_busy = False
                self.poll()
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
            layout = self._page('Mesh and quality')
            form = QtWidgets.QFormLayout()
            self.mesh = QtWidgets.QComboBox()
            self.mesh.setObjectName('femMesh')
            self.mesh.currentIndexChanged.connect(self._load_mesh)
            form.addRow('Actual native Gmsh mesh', self.mesh)
            self.min_size = self._number('femMinimumSize')
            self.max_size = self._number('femMaximumSize')
            form.addRow('Minimum size (mm; 0 automatic)', self.min_size)
            form.addRow('Maximum size (mm; 0 unbounded)', self.max_size)
            self.order, self.dimension = QtWidgets.QComboBox(), QtWidgets.QComboBox()
            self.order.setObjectName('femElementOrder')
            self.dimension.setObjectName('femElementDimension')
            form.addRow('Native element order', self.order)
            form.addRow('Native element dimension', self.dimension)
            self.element_type = QtWidgets.QComboBox()
            self.element_type.addItem('Keep explicit native order/dimension', None)
            self.element_type.addItem('C3D10 tetrahedron — supported execution', 'C3D10')
            self.element_type.addItem('C3D4 tetrahedron — execution unsupported', 'C3D4')
            form.addRow('Tetrahedral type declaration', self.element_type)
            layout.addLayout(form)
            row = QtWidgets.QHBoxLayout()
            self._button('Apply mesh settings', self.apply_mesh_settings, row, name='femApplyMeshSettings')
            self._button('Generate with native Gmsh', self.generate_mesh, row, name='femGenerateMesh')
            self._button('Open native mesh Tasks', lambda: self.native_task(self.mesh.currentData()), row)
            layout.addLayout(row)
            form = QtWidgets.QFormLayout()
            self.local_region, self.refinement = QtWidgets.QComboBox(), QtWidgets.QComboBox()
            self.local_size = self._number('femLocalSize', minimum=.000000001, value=1)
            form.addRow('Named local region', self.local_region)
            form.addRow('Native refinement', self.refinement)
            form.addRow('Local size (mm)', self.local_size)
            layout.addLayout(form)
            self._button('Apply local sizing', self.apply_local_size, layout)
            row = QtWidgets.QHBoxLayout()
            self.offset = QtWidgets.QSpinBox()
            self.offset.setRange(0, 2147483647)
            row.addWidget(QtWidgets.QLabel('Quality row offset'))
            row.addWidget(self.offset)
            self._button('Read actual quality table', self.read_quality, row, mutate=False, name='femReadQuality')
            self._button('Highlight selected bad element / nodes', self.highlight_quality, row, mutate=False)
            layout.addLayout(row)
            self.quality = QtWidgets.QTableWidget(0, 5)
            self.quality.setObjectName('femQualityTable')
            self.quality.setHorizontalHeaderLabels(['Native element ID', 'Type', 'Minimum J (mm³)', 'Normalized J', 'Reasons'])
            self.quality.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
            self.quality.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
            layout.addWidget(self.quality, 1)
            self.distribution = QtWidgets.QTableWidget(0, 4)
            self.distribution.setObjectName('femQualityDistribution')
            self.distribution.setHorizontalHeaderLabels(['Measure', 'Lower bound', 'Upper bound', 'Element count'])
            self.distribution.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
            self.distribution.setMaximumHeight(160)
            layout.addWidget(self.distribution)
            layout.addWidget(QtWidgets.QLabel('Run: single-solid C3D10 static linear Fixed/Force. Four Jacobian samples do not prove quality everywhere.'))

        def _region_tab(self):
            layout = self._page('Regions and conditions')
            self.regions = QtWidgets.QTreeWidget()
            self.regions.setObjectName('femRegions')
            self.regions.setHeaderLabels(['Name', 'Exact native target', 'Validation'])
            layout.addWidget(self.regions, 1)
            self.region_label = QtWidgets.QLineEdit('Selected native region')
            self.region_label.setObjectName('femRegionLabel')
            layout.addWidget(self.region_label)
            row = QtWidgets.QHBoxLayout()
            self._button('Capture new named region from 3D selection', self.capture_region, row)
            self._button('Repair selected region from 3D selection', self.repair_region, row)
            self._button('Remove selected region', self.remove_region, row)
            layout.addLayout(row)
            form = QtWidgets.QFormLayout()
            self.condition = QtWidgets.QComboBox()
            self.condition.setObjectName('femExistingCondition')
            self.condition.currentIndexChanged.connect(self._load_condition)
            form.addRow('Existing native Fixed / Force', self.condition)
            self.condition_region, self.direction_region = QtWidgets.QComboBox(), QtWidgets.QComboBox()
            form.addRow('Named condition face region', self.condition_region)
            form.addRow('Force direction', self.direction_region)
            self.force = self._number('femForce', minimum=0, value=0)
            self.reversed = QtWidgets.QCheckBox('Reverse native direction')
            form.addRow('Force (N)', self.force)
            form.addRow('', self.reversed)
            layout.addLayout(form)
            row = QtWidgets.QHBoxLayout()
            self._button('Highlight actual condition target', self.highlight_condition, row, mutate=False, name='femHighlightCondition')
            self._button('Confirm / repair this condition from 3D selection', self.repair_condition,
                         row, name='femRepairCondition')
            layout.addLayout(row)
            row = QtWidgets.QHBoxLayout()
            self._button('Apply to selected existing condition', self.apply_condition, row)
            self._button('Open native condition Tasks', lambda: self.native_task(self.condition.currentData()), row)
            layout.addLayout(row)
            form = QtWidgets.QFormLayout()
            self.analysis, self.new_condition = QtWidgets.QComboBox(), QtWidgets.QComboBox()
            self.new_condition.addItems(['Fixed', 'Force'])
            form.addRow('Actual analysis for new condition', self.analysis)
            form.addRow('New condition kind', self.new_condition)
            layout.addLayout(form)
            self._button('Create explicitly selected Fixed / Force', self.create_condition, layout)
            layout.addWidget(QtWidgets.QLabel('Changed BRep targets require explicit repair. Existing conditions are retained; target confirmation is not engineering release.'))

        def _material_tab(self):
            layout = self._page('Native material')
            form = QtWidgets.QFormLayout()
            self.material = QtWidgets.QComboBox()
            self.material.setObjectName('femMaterial')
            self.material.currentIndexChanged.connect(self._load_material)
            self.modulus = self._number('femYoungModulus', minimum=0, value=0)
            self.modulus.setSpecialValueText('UNKNOWN — enter E')
            self.poisson = self._number('femPoissonRatio', minimum=-1, maximum=.499999999, value=-1)
            self.poisson.setSpecialValueText('UNKNOWN — enter nu')
            form.addRow('Existing native solid material', self.material)
            form.addRow('Young modulus (MPa)', self.modulus)
            form.addRow('Poisson ratio', self.poisson)
            layout.addLayout(form)
            row = QtWidgets.QHBoxLayout()
            self._button('Apply isotropic elastic values', self.apply_material, row)
            self._button('Open native material Tasks', lambda: self.native_task(self.material.currentData()), row)
            layout.addLayout(row)
            layout.addStretch(1)

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
            self._description = self.editor.descriptor()
            self._fill_combo(self.mesh, [(row['object_id'], row['object_id']) for row in self._description['meshes']])
            self._fill_combo(self.condition, [(row['object_id'] + (' — unresolved' if row['errors'] else ' — exact target'), row['object_id'])
                                            for row in self._description['conditions']])
            objs = self.editor.owner.doc.Objects
            def kind(obj):
                return getattr(getattr(obj, 'Proxy', None), 'Type', obj.TypeId)
            self._fill_combo(self.material, [(obj.Label, obj.Name) for obj in objs if kind(obj) == 'Fem::MaterialCommon' and obj.Category == 'Solid'])
            self._fill_combo(self.analysis, [(obj.Label, obj.Name) for obj in objs if kind(obj) == 'Fem::FemAnalysis'])
            regions = self._description['regions']
            entries = [(row['label'] + (' — unresolved' if row['validation'] != 'EXACT_TARGET_MATCH' else ''), row['id']) for row in regions]
            self._fill_combo(self.local_region, entries)
            self._fill_combo(self.condition_region, entries)
            edge_regions = [(row['label'], row['id']) for row in regions if len(row['target']['subelements']) == 1
                            and row['target']['subelements'][0]['name'].startswith('Edge')]
            self._fill_combo(self.direction_region, [('Keep exact tracked native direction', '__keep'),
                ('Explicit native reference normal', None)] + edge_regions)
            selected = self.regions.currentItem()
            selected_id = selected.data(0, 256) if selected else None
            self.regions.clear()
            for row in regions:
                target = row['target']
                text = target['object_id'] + ':' + ', '.join(item['name'] for item in target['subelements'])
                item = QtWidgets.QTreeWidgetItem([row['label'], text or 'Whole body', row['validation']])
                item.setData(0, 256, row['id'])
                self.regions.addTopLevelItem(item)
                if row['id'] == selected_id:
                    self.regions.setCurrentItem(item)
            self.contact_page.refresh(load_forms=load_forms)
            if load_forms:
                self._load_mesh()
                self._load_condition()
                self._load_material()
            self.poll()

        def poll(self):
            try:
                description = self.editor.descriptor()
                busy = description['mesh_busy']
                native_task = bool(self.editor.owner.Gui.Control.activeDialog() or
                    (self.editor.owner.Gui.activeDocument() and self.editor.owner.Gui.activeDocument().getInEdit()))
                for button in self._actions:
                    button.setEnabled(not self._command_busy)
                for button in self._mutating:
                    button.setEnabled(not busy and not native_task and not self._command_busy)
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
            except Exception as error:
                self.status.setPlainText(str(error))

        def _load_mesh(self):
            identifier = self.mesh.currentData()
            if not identifier:
                return
            obj = self.editor.owner._object(identifier)
            self.min_size.setValue(float(obj.CharacteristicLengthMin.getValueAs('mm').Value))
            self.max_size.setValue(float(obj.CharacteristicLengthMax.getValueAs('mm').Value))
            self._fill_combo(self.order, [(value, value) for value in obj.getEnumerationsOfProperty('ElementOrder')])
            self._fill_combo(self.dimension, [(value, value) for value in obj.getEnumerationsOfProperty('ElementDimension')])
            self.order.setCurrentText(obj.ElementOrder)
            self.dimension.setCurrentText(obj.ElementDimension)
            self._fill_combo(self.refinement, [('Create new native refinement', None)] + [(ref.Label, ref.Name) for ref in obj.MeshRegionList])

        def _load_condition(self):
            identifier = self.condition.currentData()
            if not identifier:
                return
            try:
                obj = self.editor.owner._object(identifier)
            except Exception as error:
                self.force.setEnabled(False)
                self.reversed.setEnabled(False)
                self.direction_region.setEnabled(False)
                self.status.setPlainText(str(error))
                return
            is_force = obj.TypeId == 'Fem::ConstraintForce'
            self.force.setEnabled(is_force)
            self.reversed.setEnabled(is_force)
            self.direction_region.setEnabled(is_force)
            if is_force:
                self.force.setValue(float(obj.Force.getValueAs('N').Value))
                self.reversed.setChecked(bool(obj.Reversed))
            row = next(row for row in self._description['conditions'] if row['object_id'] == identifier)
            index = self.condition_region.findData(row.get('region_id'))
            if index >= 0:
                self.condition_region.setCurrentIndex(index)

        def _load_material(self):
            identifier = self.material.currentData()
            if identifier:
                obj = self.editor.owner._object(identifier)
                try:
                    self.modulus.setValue(float(self.editor.owner.App.Units.Quantity(obj.Material['YoungsModulus']).getValueAs('MPa').Value))
                    self.poisson.setValue(float(obj.Material['PoissonRatio']))
                except (ValueError, KeyError, TypeError) as error:
                    self.modulus.setValue(0)
                    self.poisson.setValue(-1)
                    self.status.setPlainText('Native material values are unresolved; enter explicit elastic values or use native Tasks. ' + str(error))

        def apply_mesh_settings(self):
            args = {'min_size': self.min_size.value(), 'max_size': self.max_size.value(), 'unit': 'mm',
                    'element_order': self.order.currentData(), 'element_dimension': self.dimension.currentData()}
            if self.element_type.currentData():
                args['element_type'] = self.element_type.currentData()
            self._send('pre.fem.mesh_settings', args, self.mesh.currentData(), on_done=lambda result:
                self.status.setPlainText('Native mesh settings applied. Generation remains an explicit action.'))

        def apply_local_size(self):
            args = {'region_id': self.local_region.currentData(), 'size': self.local_size.value(), 'unit': 'mm'}
            if self.refinement.currentData():
                args['refinement_id'] = self.refinement.currentData()
            self._send('pre.fem.mesh_local_size', args, self.mesh.currentData(), on_done=self._refresh_after)

        def generate_mesh(self):
            self._send('pre.fem.mesh_generate', {}, self.mesh.currentData(), on_done=lambda result:
                self.status.setPlainText('Native Gmsh ' + result['state'] + '; receipt ' + result['history_id']))

        def cancel_mesh(self):
            description = self.editor.descriptor()
            rows = description['active_mesh_generations']
            if not rows:
                raise ValueError('No active mesh generation')
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
                    self.quality.setItem(i, j, QtWidgets.QTableWidgetItem('UNKNOWN' if value is None else str(value)))
            distributions = []
            for name, measure in [('Sampled J (mm³)', data['absolute_jacobian_mm3']), ('Normalized J', data['normalized_jacobian'])]:
                distributions.extend((name, row['lower'], row['upper'], row['count']) for row in measure['bins'])
            self.distribution.setRowCount(len(distributions))
            for i, values in enumerate(distributions):
                for j, value in enumerate(values):
                    self.distribution.setItem(i, j, QtWidgets.QTableWidgetItem(str(value)))
            self.quality.resizeColumnsToContents()
            self.status.setPlainText(str(data['total_elements']) + ' native elements; ' + str(data['bad_element_count']) +
                ' fail the preserved absolute/normalized Jacobian or C3D10 type gates. ' + data['limitation'])

        def highlight_quality(self):
            if not hasattr(self, '_quality_data'):
                raise ValueError('Read an actual quality table first')
            rows = sorted({index.row() for index in self.quality.selectedIndexes()})
            if not rows:
                raise ValueError('Select explicit quality rows to highlight their native nodes')
            data = self._quality_data
            args = {'element_ids': [data['rows'][index]['element_id'] for index in rows]}
            if data['mesh_sha256']:
                args['mesh_sha256'] = data['mesh_sha256']
            self._send('pre.fem.mesh_highlight', args, data['mesh_id'])

        def _selection(self):
            rows = self.editor.owner.Gui.Selection.getSelectionEx(self.editor.owner.doc.Name)
            if not rows or len({row.Object.Name for row in rows}) != 1:
                raise ValueError('Select one exact native body, or its explicit faces/edges, in the 3D view')
            obj = rows[0].Object
            if obj.Document is not self.editor.owner.doc:
                raise ValueError('Selection belongs to another native document')
            names = list(dict.fromkeys(name for row in rows for name in row.SubElementNames))
            return obj.Name, names

        def capture_region(self):
            object_id, names = self._selection()
            self._send('pre.fem.region_set', {'label': self.region_label.text(), 'subelements': names}, object_id, on_done=self._refresh_after)

        def repair_region(self):
            selected = self.regions.currentItem()
            if selected is None:
                raise ValueError('Select the named region to repair')
            row = next(row for row in self._description['regions'] if row['id'] == selected.data(0, 256))
            object_id, names = self._selection()
            self._send('pre.fem.region_set', {'region_id': row['id'], 'label': self.region_label.text(), 'subelements': names,
                                            'expected_target_sha256': row['target_sha256']}, object_id, on_done=self._refresh_after)

        def remove_region(self):
            item = self.regions.currentItem()
            if item is None:
                raise ValueError('Select the named region to remove')
            self._send('pre.fem.region_remove', {'region_id': item.data(0, 256)}, on_done=self._refresh_after)

        def highlight_condition(self):
            row = next(row for row in self.editor.descriptor()['conditions'] if row['object_id'] == self.condition.currentData())
            objects = [{'object_id': ref['object_id'], 'subelement': name}
                       for ref in row.get('native_references', []) for name in ref['subelements']]
            if not objects:
                raise ValueError('STALE_TARGET: this condition has no current native faces to highlight')
            self._send('pre.select', {'objects': objects}, on_done=lambda result:
                self.status.setPlainText('Actual current condition targets selected in the native 3D view. Review them before confirming or repairing.'))

        def _direction(self, args, is_force):
            if is_force and self.direction_region.currentData() != '__keep':
                args['direction_region_id'] = self.direction_region.currentData()
            return args

        def repair_condition(self):
            condition_id = self.condition.currentData()
            if not condition_id:
                raise ValueError('Select the existing native condition to repair')
            object_id, names = self._selection()
            if not names or any(not name.startswith('Face') for name in names):
                raise ValueError('Explicitly select supported condition faces in the native 3D view')
            obj = self.editor.owner._object(condition_id)
            direction_args = self._direction({}, obj.TypeId == 'Fem::ConstraintForce')
            initial_serial = self._edit_serial
            def region_ready(region):
                if self.condition.currentData() != condition_id or self._selection() != (object_id, names):
                    raise ValueError('STALE_SELECTION: condition/3D selection changed; prepared region retained, repair not applied')
                def repaired(result):
                    self._completion_serial = initial_serial
                    self._refresh_after()
                    self.status.setPlainText('Existing condition ' + condition_id + ' explicitly confirmed/repaired. Engineering release remains NOT_RELEASED.')
                self._send('pre.fem.condition_repair', {**direction_args, 'region_id': region['id']}, condition_id, on_done=repaired)
            self._send('pre.fem.region_set', {'label': (condition_id + ' confirmed target')[:160],
                'subelements': names}, object_id, on_done=region_ready)

        def apply_condition(self):
            identifier = self.condition.currentData()
            obj = self.editor.owner._object(identifier)
            args = {'region_id': self.condition_region.currentData()}
            if obj.TypeId == 'Fem::ConstraintForce':
                args.update(force=self.force.value(), unit='N', reversed=self.reversed.isChecked())
            self._send('pre.fem.condition_set', self._direction(args, obj.TypeId == 'Fem::ConstraintForce'), identifier, on_done=self._refresh_after)

        def create_condition(self):
            kind = self.new_condition.currentText()
            args = {'kind': kind, 'region_id': self.condition_region.currentData()}
            if kind == 'Force':
                args.update(force=self.force.value(), unit='N', reversed=self.reversed.isChecked())
            self._send('pre.fem.condition_set', self._direction(args, kind == 'Force'), self.analysis.currentData(), on_done=self._refresh_after)

        def apply_material(self):
            self._send('pre.fem.material_set', {'young_modulus': self.modulus.value(), 'unit': 'MPa',
                'poisson_ratio': self.poisson.value()}, self.material.currentData(), on_done=lambda result:
                self.status.setPlainText('Native isotropic material values applied; other native material fields retained.'))

        def native_task(self, identifier):
            self._send('pre.fem.task_edit', {}, identifier)

    return Panel()
