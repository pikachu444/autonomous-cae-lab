"""Compact native Analysis variables/response worksheet, using existing commands."""
from copy import deepcopy
import re


def make_panel(QtWidgets, QtCore, research, submit, create_plan):
    owner = research.owner
    class Panel(QtWidgets.QWidget):
        def __init__(self):
            super().__init__()
            self.info, self.busy, self.capture_id = None, False, None
            layout = QtWidgets.QVBoxLayout(self)
            row = QtWidgets.QHBoxLayout()
            self.analysis, self.solver, self.method = QtWidgets.QComboBox(), QtWidgets.QComboBox(), QtWidgets.QComboBox()
            self.method.addItems(['DOE', 'Optimization'])
            from .fem_edit import _native_type
            for obj in owner.doc.Objects:
                if _native_type(obj) == 'Fem::FemAnalysis':
                    self.analysis.addItem(obj.Label, obj.Name)
            refresh = QtWidgets.QPushButton('Refresh')
            refresh.clicked.connect(self.refresh)
            self.analysis.currentIndexChanged.connect(self.refresh)
            row.addWidget(self.analysis, 2); row.addWidget(self.solver, 1); row.addWidget(refresh)
            layout.addLayout(row)
            self.table = QtWidgets.QTableWidget(0, 7)
            self.table.setHorizontalHeaderLabels(['Variable', 'Current', 'Unit', 'Model lower', 'Model upper', 'Research name', 'Status'])
            self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
            self.table.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
            self.table.horizontalHeader().setStretchLastSection(True)
            layout.addWidget(self.table, 3)
            row = QtWidgets.QHBoxLayout()
            for text, callback in [('Select in CAD', self.highlight), ('Register / update bounds', self.register),
                                   ('Remove registration', self.remove)]:
                button = QtWidgets.QPushButton(text); button.clicked.connect(callback); row.addWidget(button)
            row.addStretch(); layout.addLayout(row)
            self.responses = QtWidgets.QTableWidget(0, 8)
            self.responses.setHorizontalHeaderLabels(['Response', 'Kind', 'Pair', 'Field / quantity', 'Side / component', 'Increment', 'Reduction', 'Unit'])
            self.responses.horizontalHeader().setStretchLastSection(True)
            layout.addWidget(self.responses, 2)
            row = QtWidgets.QHBoxLayout()
            add = QtWidgets.QPushButton('Add response'); add.clicked.connect(self.add_response)
            remove = QtWidgets.QPushButton('Remove response')
            remove.clicked.connect(lambda: self.responses.removeRow(self.responses.currentRow()) if self.responses.currentRow() >= 0 else None)
            self.prepare = QtWidgets.QPushButton('Create Numerical Plan…'); self.prepare.clicked.connect(self.plan)
            row.addWidget(add); row.addWidget(remove); row.addStretch(); row.addWidget(self.method); row.addWidget(self.prepare)
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
                    self.message.setText(result.get('error', {}).get('message', 'Native command failed'))
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
                values = [row['label'], row['value'], item['unit'],
                          item.get('lower', ''), item.get('upper', ''), item.get('id', ''),
                          row['diagnostic'] or ('Registered' if registered else 'Select model bounds')]
                for col, value in enumerate(values):
                    cell = QtWidgets.QTableWidgetItem(str(value) if value is not None else '')
                    if col in (0, 1, 6):
                        cell.setFlags(cell.flags() & ~QtCore.Qt.ItemIsEditable)
                    self.table.setItem(index, col, cell)
            self.table.resizeColumnsToContents()
            self.message.setText('Model limits are saved with CAD; search limits are edited in the Plan.')
            if not self.responses.rowCount():
                self.add_response()

        def selected(self):
            index = self.table.currentRow()
            if self.info is None or index < 0:
                raise ValueError('Select a native variable')
            return index, self.info['candidates'][index]

        def highlight(self):
            try:
                _, row = self.selected()
                self.send('pre.select', {'objects': [{'object_id': row['target']['object_id']}]}, lambda _: None)
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

        def add_response(self):
            pairs = [r for r in owner.fem.contact._data()['contacts']
                     if r['analysis_id'] == self.analysis.currentData()
                     and not getattr(owner._object(r['object_id']), 'Suppressed', False)]
            row = self.responses.rowCount(); self.responses.insertRow(row)
            values = (['force_z_' + str(row + 1), 'pair', pairs[0]['object_id'], 'CFN', 'Z', 'final', 'value', 'N']
                      if pairs else ['u_z_' + str(row + 1), 'displacement', '', 'displacement', 'Z', 'final', 'max', 'mm'])
            for col, value in enumerate(values):
                cell = QtWidgets.QTableWidgetItem(value)
                if col == 2 and pairs:
                    cell.setToolTip('\n'.join(r['object_id'] + ': ' + r['draft']['label'] for r in pairs))
                self.responses.setItem(row, col, cell)
            self.responses.resizeColumnsToContents()

        def definitions(self):
            result = []
            for row in range(self.responses.rowCount()):
                cells = [self.responses.item(row, col).text().strip() for col in range(8)]
                name, kind, pair, field, component, increment, reduction, unit = cells
                item = {'id': name, 'kind': kind, 'increment': 'final' if increment == 'final' else int(increment),
                        'reduction': reduction, 'unit': unit}
                if kind == 'pair':
                    item.update(pair_id=pair, quantity=field, component=component)
                elif kind == 'contact_field':
                    item.update(pair_id=pair, field=field, side=component)
                else:
                    item.update(component=component)
                result.append(item)
            return result

        def plan(self):
            try:
                identifiers = [r['id'] for r in self.info['registered']]
                args = {'analysis_id': self.analysis.currentData(), 'solver_id': self.solver.currentData(),
                        'variable_ids': identifiers, 'responses': self.definitions()}
                operation = 'doe' if self.method.currentIndex() == 0 else 'optimize'
                def prepared(result):
                    create_plan(self.capture_id, operation)
                    self.message.setText('Opening the editable Numerical Plan. No candidate has run.')
                self.send('pre.research.prepare', args, prepared)
            except Exception as error:
                self.message.setText(str(error))
    return Panel()
