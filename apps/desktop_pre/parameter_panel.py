"""Compact native research-variable table; the owner performs every edit."""
import uuid


def make_panel(QtWidgets, QtCore, parameters, submit):
    class Panel(QtWidgets.QWidget):
        def __init__(self):
            super().__init__()
            self.info, self.proof, self.busy = None, None, False
            layout = QtWidgets.QVBoxLayout(self)
            self.message = QtWidgets.QLabel('Discover supported dimensions in this live document. Native CAD tools remain available.')
            self.message.setWordWrap(True); layout.addWidget(self.message)
            controls = QtWidgets.QHBoxLayout()
            self.discover = QtWidgets.QPushButton('Discover live dimensions')
            self.discover.clicked.connect(self.refresh)
            self.highlight = QtWidgets.QPushButton('Select in CAD')
            self.highlight.clicked.connect(self.select_native)
            controls.addWidget(self.discover); controls.addWidget(self.highlight); controls.addStretch()
            layout.addLayout(controls)
            self.table = QtWidgets.QTableWidget(0, 7)
            self.table.setHorizontalHeaderLabels(['Target / research ID', 'Current mm', 'Label', 'Lower mm', 'Upper mm', 'Mode', 'Status'])
            self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
            self.table.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
            self.table.horizontalHeader().setStretchLastSection(True)
            self.table.setMinimumHeight(150)
            layout.addWidget(self.table, 1)
            form = QtWidgets.QFormLayout()
            self.effect = QtWidgets.QComboBox(); self.name = QtWidgets.QLineEdit()
            self.trial = QtWidgets.QLineEdit()
            form.addRow('Effect on solid', self.effect); form.addRow('Trial value (mm)', self.trial)
            form.addRow('New research ID', self.name); layout.addLayout(form)
            actions = QtWidgets.QHBoxLayout()
            self.probe = QtWidgets.QPushButton('Check effect and restore')
            self.probe.clicked.connect(self.check_effect)
            self.register = QtWidgets.QPushButton('Register selected')
            self.register.clicked.connect(self.register_selected)
            self.apply = QtWidgets.QPushButton('Apply registered edit')
            self.apply.clicked.connect(self.update_selected)
            self.remove = QtWidgets.QPushButton('Remove registration')
            self.remove.clicked.connect(self.remove_selected)
            for button in (self.probe, self.register, self.apply, self.remove): actions.addWidget(button)
            layout.addLayout(actions)
            self.table.itemSelectionChanged.connect(lambda: setattr(self, 'proof', None))

        def _send(self, operation, args, target=None, accepted=None):
            if self.busy: return
            self.busy = True; self.setEnabled(False)
            def done(result):
                self.busy = False; self.setEnabled(True)
                if result.get('status') == 'FAILED':
                    self.message.setText(result.get('error', {}).get('message', 'Native command failed')); return
                if accepted: accepted(result)
            try:
                submit(operation, args, target or {}, done)
            except Exception as error:
                done({'status': 'FAILED', 'error': {'message': str(error)}})

        def refresh(self):
            self._send('pre.parameters.discover', {}, accepted=self.populate)

        def populate(self, info):
            self.info, self.proof = info, None
            self.rows = [(False, row) for row in info['candidates']] + [(True, row) for row in info['parameters']]
            self.table.setRowCount(len(self.rows))
            for index, (registered, row) in enumerate(self.rows):
                value = row.get('current_value', row.get('value'))
                cells = [row.get('name', row.get('key')), str(value), row.get('label', row.get('object_label', '')),
                         str(row.get('min', value - .2 * abs(value or 1.))),
                         str(row.get('max', value + .2 * abs(value or 1.))),
                         row.get('mode', 'fixed'), row.get('diagnostic') or ('Registered' if registered else 'Discovered; not registered')]
                for col, value in enumerate(cells):
                    item = QtWidgets.QTableWidgetItem(str(value))
                    if col in (0, 6) or col == 1 and not registered:
                        item.setFlags(item.flags() & ~QtCore.Qt.ItemIsEditable)
                    self.table.setItem(index, col, item)
            self.effect.clear()
            for solid in info['effect_objects']: self.effect.addItem(solid['label'] + ' · ' + solid['object_id'], solid['object_id'])
            self.message.setText('Live g' + str(info['generation']) + '. Registration and value edits use native Undo; effect probes restore the design.')

        def selected(self):
            row = self.table.currentRow()
            if self.info is None or row < 0: raise ValueError('Select a discovered or registered native dimension')
            return row, self.rows[row]

        def select_native(self):
            try:
                _, (_, row) = self.selected()
                self._send('pre.select', {'objects': [{'object_id': row['object']}]})
            except Exception as error: self.message.setText(str(error))

        def check_effect(self):
            try:
                _, (_, row) = self.selected()
                args = {'selector': row['key'], 'source_stamp': self.info['source_stamp'],
                        'effect_object_id': self.effect.currentData(), 'trial_value': float(self.trial.text()), 'unit': 'mm'}
                def shown(result):
                    self.proof = result
                    self.message.setText('Restored original design. Geometry effect: ' + str(result['changed']) +
                                         ('; ' + result['error'] if result['error'] else ''))
                self._send('pre.parameters.probe', args, accepted=shown)
            except Exception as error: self.message.setText(str(error))

        def register_selected(self):
            try:
                index, (registered, row) = self.selected()
                if registered or not self.proof: raise ValueError('Probe this unregistered target first')
                args = {'selector': row['key'], 'source_stamp': self.info['source_stamp'], 'proof_id': self.proof['proof_id'],
                    'parameter_id': self.name.text().strip(), 'label': self.table.item(index, 2).text(),
                    'lower': float(self.table.item(index, 3).text()), 'upper': float(self.table.item(index, 4).text()),
                    'mode': self.table.item(index, 5).text()}
                self._send('pre.parameters.register', args, accepted=self.populate)
            except Exception as error: self.message.setText(str(error))

        def update_selected(self):
            try:
                index, (registered, row) = self.selected()
                if not registered: raise ValueError('Explicitly register the discovered dimension first')
                args = {'parameter_id': row['name'], 'value': float(self.table.item(index, 1).text()), 'unit': 'mm',
                    'label': self.table.item(index, 2).text(), 'lower': float(self.table.item(index, 3).text()),
                    'upper': float(self.table.item(index, 4).text()), 'mode': self.table.item(index, 5).text()}
                self._send('pre.parameters.update', args, accepted=self.populate)
            except Exception as error: self.message.setText(str(error))

        def remove_selected(self):
            try:
                _, (registered, row) = self.selected()
                if not registered: raise ValueError('Select a registered research ID')
                self._send('pre.parameters.remove', {'parameter_id': row['name']}, accepted=self.populate)
            except Exception as error: self.message.setText(str(error))
    return Panel()
