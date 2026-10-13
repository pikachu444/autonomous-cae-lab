"""Compact contact pair inspection using the existing native Post command owner."""
from copy import deepcopy
import math

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDialog, QHBoxLayout,
    QHeaderView, QLabel, QPushButton, QSplitter, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget)
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure


class ContactDialog(QDialog):
    def __init__(self, post, source_ref):
        super().__init__(post)
        self.post, self.source_ref = post, source_ref
        self.owner = (post.document['id'], post.document['session_id'])
        self.payload = None
        self.saved_object = None
        self._loading = False
        self._serial = 0
        self.setWindowTitle('Contact results')
        self.resize(1180, 800)
        outer = QVBoxLayout(self)
        controls = QHBoxLayout()
        self.pair, self.side, self.frame, self.field = [QComboBox() for _ in range(4)]
        for label, combo, name in [('Pair', self.pair, 'contactPair'), ('Faces', self.side, 'contactSide'),
                                   ('Increment', self.frame, 'contactIncrement'), ('Field', self.field, 'contactField')]:
            controls.addWidget(QLabel(label))
            combo.setObjectName(name)
            controls.addWidget(combo, 2 if name in ('contactPair', 'contactIncrement') else 1)
        for label, value in [('A — slave', 'a'), ('B — master', 'b'), ('A + B', 'both')]:
            self.side.addItem(label, value)
        self.show_button = QPushButton('Show faces')
        self.show_button.clicked.connect(lambda: self.read(show=True))
        controls.addWidget(self.show_button)
        outer.addLayout(controls)
        self.faces = QLabel()
        self.faces.setWordWrap(True)
        outer.addWidget(self.faces)
        self.meaning = QLabel('Shared nodal fields; DAT force on A. Active state: UNKNOWN.')
        self.meaning.setWordWrap(True)
        outer.addWidget(self.meaning)
        split = QSplitter(Qt.Orientation.Horizontal)
        left = QWidget()
        column = QVBoxLayout(left)
        self.field_table = self.table(['Node', 'Value', 'State / reason'], 'contactFieldRows')
        column.addWidget(self.field_table, 1)
        paging = QHBoxLayout()
        self.back_page, self.next_page = QPushButton('Previous rows'), QPushButton('Next rows')
        self.back_page.clicked.connect(lambda: self.read(offset=max(0, self.payload.get('offset', 0)-500)))
        self.next_page.clicked.connect(lambda: self.read(offset=self.payload.get('next_offset') or 0))
        paging.addWidget(self.back_page)
        paging.addWidget(self.next_page)
        column.addLayout(paging)
        split.addWidget(left)
        right = QWidget()
        layout = QVBoxLayout(right)
        force = QHBoxLayout()
        force.addWidget(QLabel('Force on A'))
        self.quantity, self.component = QComboBox(), QComboBox()
        self.quantity.setObjectName('contactForceQuantity')
        self.component.setObjectName('contactForceComponent')
        for label, value in [('CF — total', 'CF'), ('CFN — normal part', 'CFN'), ('CFS — tangential part', 'CFS')]:
            self.quantity.addItem(label, value)
        for index, label in enumerate(('Global X', 'Global Y', 'Global Z')):
            self.component.addItem(label, index)
        force.addWidget(self.quantity, 2)
        force.addWidget(self.component, 1)
        self.read_button = QPushButton('Read selection')
        self.read_button.clicked.connect(lambda: self.read())
        force.addWidget(self.read_button)
        layout.addLayout(force)
        self.figure = Figure(figsize=(6, 3.5))
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.canvas.mpl_connect('pick_event', self.picked)
        layout.addWidget(self.canvas, 2)
        self.history = self.table(['Step / increment', 'Load parameter [1]', 'Force on A [N]', 'State'], 'contactForceHistory')
        self.history.itemSelectionChanged.connect(self.history_selected)
        layout.addWidget(self.history, 1)
        split.addWidget(right)
        split.setSizes([390, 750])
        outer.addWidget(split, 1)
        self.status = QLabel()
        self.status.setWordWrap(True)
        outer.addWidget(self.status)
        actions = QHBoxLayout()
        self.save_selection = QPushButton('Save inspection')
        self.save_selection.clicked.connect(self.save_inspection)
        self.save_measurement = QPushButton('Save force measurement')
        self.save_measurement.clicked.connect(self.create_measurement)
        self.numerical = QPushButton('Use in Numerical…')
        self.numerical.clicked.connect(self.use_numerical)
        close = QPushButton('Close')
        close.clicked.connect(self.close)
        for button in (self.save_selection, self.save_measurement, self.numerical, close):
            actions.addWidget(button)
        outer.addLayout(actions)
        for combo in (self.pair, self.side, self.frame, self.field, self.quantity, self.component):
            combo.currentIndexChanged.connect(self.changed)
        self.sync()
        self.read(initial=True)

    @staticmethod
    def table(headers, name):
        table = QTableWidget(0, len(headers))
        table.setObjectName(name)
        table.setHorizontalHeaderLabels(headers)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setStretchLastSection(True)
        return table

    def same_owner(self):
        return self.post.document is not None and (
            self.post.document['id'], self.post.document['session_id']) == self.owner

    def token(self):
        return (self.post.document_id, self.post.session_id, self.source_ref, self._serial)

    def selection(self):
        return {'source_ref': self.source_ref, 'pair_id': self.pair.currentData(),
                'side': self.side.currentData(), 'frame_index': self.frame.currentData(),
                'field': self.field.currentData(), 'quantity': self.quantity.currentData(),
                'component': self.component.currentData()}

    def changed(self, *_):
        if self._loading:
            return
        self._serial += 1
        self.saved_object = None
        self.status.setText('Selection changed. Read selection or Show faces.')
        self.sync()

    def sync(self):
        idle = self.same_owner() and not self.post._busy and self.post._pending is None and not self.post.conflict
        for combo in (self.pair, self.side, self.frame, self.field, self.quantity, self.component):
            combo.setEnabled(idle)
        ready = idle and self.payload is not None
        self.show_button.setEnabled(ready)
        self.read_button.setEnabled(ready)
        self.save_selection.setEnabled(ready)
        self.save_measurement.setEnabled(ready and not self.post.local_dirty)
        self.numerical.setEnabled(ready and bool(self.saved_object) and not self.post.local_dirty)
        self.back_page.setEnabled(ready and bool(self.payload.get('offset')) if self.payload else False)
        self.next_page.setEnabled(ready and self.payload.get('next_offset') is not None if self.payload else False)

    def read(self, *, show=False, initial=False, offset=0, after=None):
        if not self.same_owner():
            self.status.setText('The Post document changed. Reopen Contact results for the selected source.')
            return False
        token = self.token()
        args = {'source_ref': self.source_ref} if initial else self.selection()
        args.update(show=show, offset=offset, limit=500)
        def accepted(payload):
            if token != self.token() or not self.isVisible():
                return
            self.display(payload, initial=initial)
            if after is not None:
                after()
        return self.post.queue_command('post.contact_inspect', args, accepted=accepted)

    def display(self, payload, *, initial=False):
        self._loading = True
        self.payload = deepcopy(payload)
        selected = payload['selection']
        catalog = payload['catalog']
        if initial:
            self.pair.clear()
            for pair in catalog['pairs']:
                self.pair.addItem(pair['label'], pair['id'])
            self.frame.clear()
            for index, frame in enumerate(catalog['frames']):
                self.frame.addItem(f"{frame['step']} / {frame['increment']}   λ={frame['load_parameter']:.9g}", index)
            self.field.clear()
            for field in catalog['fields']:
                label = 'Geometric gap (derived)' if field['name'] == 'GeomGap_mm' else 'COPEN (raw)' if field['name'] == 'COPEN' else field['name']
                self.field.addItem(label + ' [' + field['unit'] + ']', field['name'])
        for combo, key in [(self.pair, 'pair_id'), (self.side, 'side'), (self.frame, 'frame_index'),
                           (self.field, 'field'), (self.quantity, 'quantity'), (self.component, 'component')]:
            combo.setCurrentIndex(combo.findData(selected[key]))
        pair = next(row for row in catalog['pairs'] if row['id'] == selected['pair_id'])
        def side_text(key):
            faces = pair[key]['faces']
            return pair[key]['body'] + ' ' + ', '.join(row['face'] for row in faces)
        self.faces.setText('A: ' + side_text('a') + '    B: ' + side_text('b') + '    Orange A / cyan B')
        self.faces.setToolTip(str(pair))
        self.meaning.setText(
            'Geometric gap: deformed face approximation; surface colour is the unambiguous nodal projection. Active state: UNKNOWN.'
            if selected['field'] == 'GeomGap_mm' else
            'Shared nodal projection; selecting a pair does not separate its pressure/slip contribution. Active state: UNKNOWN.')
        self.field_table.setHorizontalHeaderLabels(['Node', payload['field'] + ' [' + payload['unit'] + ']', 'State / reason'])
        self.field_table.setRowCount(len(payload['rows']))
        for index, row in enumerate(payload['rows']):
            for column, value in enumerate((row['node_id'], self.number(row['value']), 'Available' if row['valid'] else row['reason'])):
                item = QTableWidgetItem(str(value))
                item.setToolTip(str(row) if column == 0 else str(value))
                self.field_table.setItem(index, column, item)
        rows = payload['history']['rows']
        self.history.blockSignals(True)
        self.history.setRowCount(len(rows))
        for index, row in enumerate(rows):
            static = row['static']
            values = (str(static['step']) + ' / ' + str(static['increment']), self.number(static['load_parameter']),
                      self.number(row['value']), 'Available' if row['valid'] else row['reason'])
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setToolTip(row.get('raw_text') or str(value))
                self.history.setItem(index, column, item)
        self.history.selectRow(selected['frame_index'])
        self.history.blockSignals(False)
        self.figure.clear()
        self.axes = self.figure.add_subplot(111)
        x = [r['static']['load_parameter'] for r in rows]
        y = [r['value'] if r['valid'] else math.nan for r in rows]
        self.axes.plot(x, y, marker='o', markersize=4, picker=6)
        index = selected['frame_index']
        if rows[index]['valid']:
            self.axes.plot([x[index]], [y[index]], 'o', color='#c55b28', markersize=8)
        self.axes.set_xlabel('Load parameter [1]')
        self.axes.set_ylabel(selected['quantity'] + ' global ' + 'XYZ'[selected['component']] + ' on A [N]')
        self.axes.grid(True, alpha=.2)
        self.figure.tight_layout()
        self.canvas.draw_idle()
        self.status.setText(('Faces displayed. ' if payload['displayed'] else '') +
            str(payload['total_rows']) + ' surface nodes; ' + str(len(rows)) + ' retained increments.')
        self._loading = False
        self.sync()

    @staticmethod
    def number(value):
        return 'Unavailable' if value is None else format(value, '.10g')

    def history_selected(self):
        row = self.history.currentRow()
        if self._loading or not self.payload or row < 0 or self.post._busy or self.post._pending:
            return
        self.frame.setCurrentIndex(self.frame.findData(row))
        self.read(show=True)

    def picked(self, event):
        if len(getattr(event, 'ind', [])):
            self.history.selectRow(int(event.ind[0]))
            self.history.scrollToItem(self.history.item(int(event.ind[0]), 0))

    def save_inspection(self):
        token = self.token()
        def saved(_):
            if token == self.token():
                self.status.setText('Inspection saved with the native view and exact increment.')
        return self.read(show=True, after=lambda: self.post.queue_command('document.save', {}, accepted=saved))

    def select_object(self, object_ref):
        if not self.same_owner():
            return False
        if self.post.local_dirty:
            self.status.setText('Keep or Reset the edited analysis recipe first; its edits remain unchanged.')
            return False
        obj = next((o for o in self.post._objects() if o['id'] == object_ref), None)
        if obj is None:
            self.status.setText('Refresh the owner to select the retained force measurement.')
            return False
        self.post._object_ref = object_ref
        self.post._tree_selection = ('object', object_ref)
        self.post._kind, self.post._draft = 'measurement', deepcopy(obj['draft'])
        self.post._show_document(self.post.document)
        return True

    def create_measurement(self):
        if not self.same_owner() or self.post.local_dirty:
            return False
        selected, token = self.selection(), self.token()
        def created(payload):
            if token != self.token():
                return
            object_ref = payload['object_ref']
            if not self.select_object(object_ref):
                return
            def saved(_):
                if token == self.token():
                    self.saved_object = object_ref
                    self.status.setText('Force measurement saved. Use in Numerical to choose an existing Plan and review the append.')
                    self.sync()
            self.post.queue_command('document.save', {}, accepted=saved)
        return self.post.queue_command('post.contact_measurement',
            {key: selected[key] for key in ('source_ref', 'pair_id', 'quantity', 'component')}, accepted=created)

    def use_numerical(self):
        if self.saved_object and self.select_object(self.saved_object):
            self.hide()
            return self.post.use_in_numerical()
        return False
