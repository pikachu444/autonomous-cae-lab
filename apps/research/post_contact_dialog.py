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
        self.setWindowTitle('접촉면·합력·모멘트')
        self.resize(1440, 900)
        self.setMinimumSize(1020, 700)
        outer = QVBoxLayout(self)
        controls = QHBoxLayout()
        self.pair, self.side, self.frame, self.field = [QComboBox() for _ in range(4)]
        for label, combo, name in [('접촉 쌍', self.pair, 'contactPair'), ('면', self.side, 'contactSide'),
                                   ('증분', self.frame, 'contactIncrement')]:
            controls.addWidget(QLabel(label))
            combo.setObjectName(name)
            controls.addWidget(combo, 2 if name in ('contactPair', 'contactIncrement') else 1)
        for label, value in [('A 면 (slave)', 'a'), ('B 면 (master)', 'b'), ('A + B', 'both')]:
            self.side.addItem(label, value)
        self.show_button = QPushButton('ParaView에서 면 보기')
        self.show_button.clicked.connect(lambda: self.read(show=True))
        outer.addLayout(controls)
        self.faces = QLabel()
        self.faces.setWordWrap(True)
        outer.addWidget(self.faces)
        self.meaning = QLabel('절점 투영 필드와 DAT의 A 면 합력을 별도로 읽습니다. 접촉 활성 여부는 확인되지 않았습니다.')
        self.meaning.setWordWrap(True)
        outer.addWidget(self.meaning)
        split = QSplitter(Qt.Orientation.Horizontal)
        left = QWidget()
        column = QVBoxLayout(left)
        surface_controls = QHBoxLayout()
        surface_controls.addWidget(QLabel('접촉면 필드'))
        surface_controls.addWidget(self.field, 1)
        surface_controls.addWidget(self.show_button)
        column.addLayout(surface_controls)
        self.field_table = self.table(['절점', '값', '유효성'], 'contactFieldRows')
        column.addWidget(self.field_table, 1)
        paging = QHBoxLayout()
        self.back_page, self.next_page = QPushButton('이전 구간'), QPushButton('다음 구간')
        self.back_page.clicked.connect(lambda: self.read(offset=max(0, self.payload.get('offset', 0)-500)))
        self.next_page.clicked.connect(lambda: self.read(offset=self.payload.get('next_offset') or 0))
        paging.addWidget(self.back_page)
        paging.addWidget(self.next_page)
        column.addLayout(paging)
        split.addWidget(left)
        right = QWidget()
        layout = QVBoxLayout(right)
        force = QHBoxLayout()
        force.addWidget(QLabel('A 면 합력'))
        self.quantity, self.component = QComboBox(), QComboBox()
        self.quantity.setObjectName('contactForceQuantity')
        self.component.setObjectName('contactForceComponent')
        for label, value in [('전체 힘 (CF)', 'CF'), ('법선 힘 (CFN)', 'CFN'), ('접선 힘 (CFS)', 'CFS')]:
            self.quantity.addItem(label, value)
        for index, label in enumerate(('선택 좌표계 X', '선택 좌표계 Y', '선택 좌표계 Z')):
            self.component.addItem(label, index)
        force.addWidget(self.quantity, 2)
        force.addWidget(self.component, 1)
        self.read_button = QPushButton('선택 조회')
        self.read_button.setProperty('appearanceRole', 'primary')
        self.read_button.clicked.connect(lambda: self.read())
        force.addWidget(self.read_button)
        layout.addLayout(force)
        from .post_resultant_controls import ResultantControls
        self.resultants = ResultantControls(self.changed, self)
        layout.addWidget(self.resultants)
        self.figure = Figure(figsize=(6, 3.5))
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.canvas.mpl_connect('pick_event', self.picked)
        self.canvas.mpl_connect('resize_event', self.fit_plot)
        layout.addWidget(self.canvas, 2)
        self.history = self.table(['단계 / 증분', '하중 계수 λ [1]', 'A 면 합력 [N]', '유효성'], 'contactForceHistory')
        self.history.itemSelectionChanged.connect(self.history_selected)
        layout.addWidget(self.history, 1)
        split.addWidget(right)
        split.setSizes([390, 750])
        outer.addWidget(split, 1)
        self.status = QLabel()
        self.status.setWordWrap(True)
        outer.addWidget(self.status)
        actions = QHBoxLayout()
        self.save_selection = QPushButton('현재 면과 증분 저장')
        self.save_selection.clicked.connect(self.save_inspection)
        self.save_measurement = QPushButton('합력 / 모멘트 측정 저장')
        self.save_measurement.clicked.connect(self.create_measurement)
        self.numerical = QPushButton('Numerical로 보내기…')
        self.numerical.setMinimumWidth(165)
        self.numerical.setProperty('appearanceRole', 'primary')
        self.numerical.clicked.connect(self.use_numerical)
        close = QPushButton('닫기')
        close.clicked.connect(self.close)
        actions.addWidget(self.save_selection)
        actions.addStretch()
        for button in (self.save_measurement, self.numerical, close):
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
                'component': self.component.currentData(),
                'resultant': self.resultants.value()}

    def changed(self, *_):
        if self._loading:
            return
        self._serial += 1
        self.saved_object = None
        self.status.setText('선택을 바꿨습니다. 표와 곡선은 이전 조회입니다. 선택 조회 후 측정을 저장하세요.')
        self.sync()

    def sync(self):
        idle = self.same_owner() and not self.post._busy and self.post._pending is None and not self.post.conflict
        for combo in (self.pair, self.side, self.frame, self.field, self.quantity, self.component):
            combo.setEnabled(idle)
        self.resultants.sync(idle)
        ready = idle and self.payload is not None
        last = self.post._last_command or {}
        failed = last.get('state') in {'FAILED', 'REJECTED', 'INTERRUPTED'} and last.get('operation') == 'post.contact_inspect'
        if failed:
            self.status.setText('접촉 조회 실패. ' + ('표와 곡선은 마지막 성공 조회입니다. ' if self.payload else
                '선택 조회로 다시 시도하세요. ') + self.post.message.text())
        matches = ready and all(self.payload['selection'].get(key) == value for key, value in self.selection().items())
        self.show_button.setEnabled(ready)
        self.read_button.setEnabled(idle)
        self.save_selection.setEnabled(ready)
        self.save_measurement.setEnabled(matches and not failed and not self.post.local_dirty)
        self.numerical.setEnabled(matches and not failed and bool(self.saved_object) and not self.post.local_dirty)
        self.back_page.setEnabled(ready and bool(self.payload.get('offset')) if self.payload else False)
        self.next_page.setEnabled(ready and self.payload.get('next_offset') is not None if self.payload else False)

    def read(self, *, show=False, initial=False, offset=0, after=None):
        if not self.same_owner():
            self.status.setText('The Post document changed. Reopen Contact results for the selected source.')
            return False
        initial = initial or self.payload is None
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
        axis_label = '시간 [s]' if catalog['axis']['unit']=='s' else '누적 하중 계수 [1]'
        symbol = 't' if catalog['axis']['unit']=='s' else 'λ'
        response = payload['history'].get('resultant', {}).get('response', 'force')
        response_label = 'A 면 합모멘트' if response == 'moment' else 'A 면 합력'
        response_unit = payload['history']['unit']
        self.history.setHorizontalHeaderLabels(['단계 / 증분', axis_label, response_label+' ['+response_unit+']', '유효성'])
        self.resultants.load(selected.get('resultant'))
        if initial:
            self.pair.clear()
            for pair in catalog['pairs']:
                self.pair.addItem(pair['label'], pair['id'])
            self.frame.clear()
            for index, frame in enumerate(catalog['frames']):
                location=(catalog.get('steps') or [None]*len(catalog['frames']))[index]
                name=location['label'] if location else str(frame['step'])+'단계'
                self.frame.addItem(f"{name} / 증분 {frame['increment']}   {symbol}={frame['load_parameter']:.9g}", index)
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
        self.faces.setText('A: ' + side_text('a') + '    B: ' + side_text('b') + '    A 주황 / B 청록')
        self.faces.setToolTip(str(pair))
        self.meaning.setText(
            '형상 간극은 변형된 면의 근사값입니다. 면 색상은 절점 투영값이며 접촉 활성 여부는 확인되지 않았습니다.'
            if selected['field'] == 'GeomGap_mm' else
            '공유 절점에 투영한 값입니다. 접촉 쌍을 선택해도 그 쌍의 압력·미끄럼 기여만 분리되지 않습니다. 접촉 활성 여부는 확인되지 않았습니다.')
        if payload.get('input_activation') is not None:
            state = {'active': '활성', 'inactive': '비활성'}.get(payload['input_activation'], '미확인')
            self.meaning.setText(self.meaning.text()+' 선택 단계의 접촉쌍 입력 상태: '+state+' (실제 접촉 여부 아님).')
        if catalog.get('execution',{}):
            self.meaning.setText('실패·취소 실행의 수렴한 일부 증분입니다. 전체 해석 완료가 아닙니다. '+self.meaning.text())
        self.field_table.setHorizontalHeaderLabels(['절점', payload['field'] + ' [' + payload['unit'] + ']', '유효성'])
        self.field_table.setRowCount(len(payload['rows']))
        for index, row in enumerate(payload['rows']):
            for column, value in enumerate((row['node_id'], self.number(row['value']), '유효' if row['valid'] else row['reason'])):
                item = QTableWidgetItem(str(value))
                item.setToolTip(str(row) if column == 0 else str(value))
                self.field_table.setItem(index, column, item)
        rows = payload['history']['rows']
        self.history.blockSignals(True)
        self.history.setRowCount(len(rows))
        for index, row in enumerate(rows):
            static = row['static']
            values = (str(static['step']) + ' / ' + str(static['increment']), self.number(static['load_parameter']),
                      self.number(row['value']), '유효' if row['valid'] else row['reason'])
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
        self.axes.set_xlabel(axis_label)
        frame_label = payload['history'].get('resultant', {}).get('frame_label', 'Global')
        self.axes.set_ylabel(selected['quantity'] + ' ' + frame_label + ' ' + 'XYZ'[selected['component']] + ' [' + response_unit + ']')
        self.axes.grid(True, alpha=.2)
        self.figure.tight_layout()
        self.canvas.draw_idle()
        self.status.setText(('ParaView에 면을 표시했습니다. ' if payload['displayed'] else '') +
            str(payload['total_rows']) + '개 표면 절점, ' + str(len(rows)) + '개 저장 증분을 조회했습니다.')
        self._loading = False
        self.sync()

    @staticmethod
    def number(value):
        return '값 없음' if value is None else format(value, '.10g')

    def fit_plot(self, _event=None):
        if hasattr(self, 'axes'):
            self.figure.tight_layout()
            self.canvas.draw_idle()

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
        if not self.same_owner() or self.post.local_dirty or not self.payload or not all(
                self.payload['selection'].get(key) == value for key, value in self.selection().items()):
            self.status.setText('현재 표와 곡선은 이전 조회입니다. 선택한 합력/모멘트 성분을 먼저 조회한 뒤 측정을 저장하세요.')
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
                    self.status.setText('측정을 저장했습니다. Numerical로 보내기에서 기존 계획·같은 축/단위·추가할 행을 검토하세요.')
                    self.sync()
            self.post.queue_command('document.save', {}, accepted=saved)
        return self.post.queue_command('post.contact_measurement',
            {**{key: selected[key] for key in ('source_ref', 'pair_id', 'quantity', 'component')},
             **({'resultant': selected['resultant']} if 'resultant' in selected else {}),
             **({'frame_indices': [selected['frame_index']]} if self.resultants.only_frame.isChecked() else {})}, accepted=created)

    def use_numerical(self):
        if self.saved_object and self.payload and all(self.payload['selection'].get(key) == value
                for key, value in self.selection().items()) and self.select_object(self.saved_object):
            self.hide()
            return self.post.use_in_numerical()
        return False
