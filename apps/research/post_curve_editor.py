"""Compact retained-curve controls for the existing Post comparison page."""
from copy import deepcopy
from PySide6.QtCore import Signal, Qt, QTimer, QThreadPool
from PySide6.QtWidgets import (QWidget, QGridLayout, QFormLayout, QDialog, QDialogButtonBox,
    QComboBox, QLabel, QPushButton, QLineEdit, QCheckBox, QVBoxLayout, QSizePolicy)
from caelab.post_comparison import (UNKNOWN_OBSERVABLE, COMPONENTS, observable_value, observable_label)
from .post_comparison_editor import combo
from .data_window import number_or_raw
from .pde_window import _Read
from .response_selection import response_choices


def default_recipe():
    return {'version': 3, 'a': {'source_ref': ''}, 'b': {'source_ref': ''},
        'axis_kind': None, 'axis_origins': {'a': '', 'b': ''}, 'b_axis_offset': 0.,
        'alignment': 'exact', 'axis_tolerance': 0., 'max_gap': None,
        'target_unit': '', 'locations_confirmed': False}


def identity(value):
    return {k: value.get(k) for k in ('source_ref', 'revision', 'block', 'column', 'component', 'axis_column')}


def title(option):
    d = option.get('declaration', {})
    return (option.get('label', '저장 곡선') + ' — ' + option.get('column', '값') +
            ' / ' + observable_label(d.get('observable') or UNKNOWN_OBSERVABLE) +
            ' [' + str(d.get('units') or '?') + '] / 위치 ' + ('/'.join(str(i+1) for i in option.get('block', [])) or '전체') +
            ' / 축 ' + str(option.get('axis_column', '')))


class CurveEditor(QWidget):
    changed = Signal()
    refreshRequested = Signal()
    importRequested = Signal()

    def __init__(self, draft, catalog, parent=None):
        super().__init__(parent)
        self.value = deepcopy(draft)
        self.catalog = deepcopy(catalog or [])
        self.grid = QGridLayout(self); self.grid.setContentsMargins(0, 0, 0, 0)
        self.selectors = {}
        for col, side in enumerate(('a', 'b')):
            self.grid.addWidget(QLabel('기준 곡선 A' if side == 'a' else '비교 곡선 B'), 0, col)
            current = self.value[side]
            entries = [('자료 선택', None)] + [(title(o), identity(o)) for o in self.catalog]
            selector = combo(entries, identity(current) if current.get('source_ref') else None)
            selector.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            selector.setMinimumContentsLength(12); selector.setMinimumWidth(0)
            selector.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
            self.grid.addWidget(selector, 1, col); self.selectors[side] = selector
            button = QPushButton('물리량·가로축 확인…')
            button.clicked.connect(lambda checked=False, side=side: self.meaning(side))
            self.grid.addWidget(button, 2, col)
            selector.currentIndexChanged.connect(lambda i, side=side, w=selector: self.choose(side, w.currentData()))
        self.mode = combo([('정확한 표본 대응', 'exact'), ('두 표본 사이 보간', 'bracket')], self.value.get('alignment'))
        self.mode.currentIndexChanged.connect(lambda: self.set_value('alignment', self.mode.currentData()))
        self.grid.addWidget(self.mode, 3, 0)
        settings = QPushButton('축 정렬·구간…'); settings.clicked.connect(self.settings)
        self.grid.addWidget(settings, 3, 1)
        refresh = QPushButton('저장 곡선 읽기'); refresh.clicked.connect(self.refreshRequested)
        add = QPushButton('시험 Data 가져오기…'); add.clicked.connect(self.importRequested)
        self.grid.addWidget(refresh, 4, 0); self.grid.addWidget(add, 4, 1)

    def draft(self):
        return deepcopy(self.value)

    def set_value(self, key, value):
        self.value[key] = deepcopy(value); self.changed.emit()

    def choose(self, side, selected):
        option = next((o for o in self.catalog if identity(o) == selected), None)
        self.value[side] = deepcopy(option) if option else {'source_ref': ''}
        if option:
            self.value[side]['rows'] = [0, option['row_count']]
            if side == 'a' and not self.value.get('target_unit'):
                self.value['target_unit'] = option.get('declaration', {}).get('units') or ''
        self.value['locations_confirmed'] = False
        self.changed.emit()

    def meaning(self, side):
        current = deepcopy(self.value[side])
        original = next((o for o in self.catalog if identity(o) == identity(current)), {})
        declaration = current.setdefault('declaration', {})
        known = original.get('declaration', {})
        dialog = QDialog(self); dialog.setWindowTitle('곡선의 물리량'); form = QFormLayout(dialog)
        fields = {}
        choices = {
            'quantity': [('힘','force'),('응력','stress'),('변위','displacement'),('변형률','strain'),
                ('온도','temperature'),('속도','velocity'),('가속도','acceleration'),('에너지','energy'),
                ('접촉 합력','CF'),('접촉 법선력','CFN'),('접촉 전단력','CFS')],
            'measure': [('힘','force'),('Cauchy 응력','cauchy'),('제1 Piola 응력','PK1'),
                ('제2 Piola 응력','PK2'),('공학 변형률','engineering_strain'),
                ('변위','displacement'),('온도','temperature')],
            'frame': [('전역','global'),('월드 좌표계','world'),('국소','local')],
            'reduction': [('축약 없음','none'),('평균','avg'),('합계','sum'),('최소','min'),
                ('최대','max'),('중앙값','med'),('1사분위','q1'),('3사분위','q3'),('표준편차','std')]}
        for key, label in (('quantity', '물리량'), ('units', '단위'), ('measure', '측도'),
                           ('frame', '성분 좌표계'), ('location', '측정 위치'), ('reduction', '축약')):
            fixed = known.get(key) not in (None, '', 'UNKNOWN', 'UNSPECIFIED')
            if key in choices:
                value = declaration.get(key) or ''
                items = [('미확인','')] + choices[key]
                if value not in [v for _,v in items]:
                    items.append((str(value),value))
                field = combo(items, value)
                field.setEditable(not fixed); field.setEnabled(not fixed)
            else:
                field = QLineEdit(str(declaration.get(key) or ''))
                field.setReadOnly(fixed)
            form.addRow(label, field); fields[key] = field
        leaves = [('미확인', UNKNOWN_OBSERVABLE)]
        for kind, names in (('scalar', ['scalar']), ('vector', ['x', 'y', 'z', 'magnitude']),
                            ('tensor', COMPONENTS + ['magnitude'])):
            for name in names:
                leaf = observable_value(kind, name)
                leaves.append((observable_label(leaf), leaf))
        observed = declaration.get('observable') or UNKNOWN_OBSERVABLE
        if not any(v == observed for _, v in leaves):
            leaves.append((observable_label(observed), observed))
        observable = combo(leaves, observed)
        observable.setEnabled(known.get('observable') in (None, UNKNOWN_OBSERVABLE))
        form.addRow('성분·불변량', observable)
        temperature = combo([('해당 없음 / 미확인', None), ('절대온도', 'absolute'), ('온도차', 'difference')],
                            declaration.get('temperature_kind'))
        temperature.setEnabled(known.get('temperature_kind') is None)
        form.addRow('온도 의미', temperature)
        axis = current.setdefault('axis', {})
        axis_fields = {}
        for key, label in (('name', '가로축'), ('unit', '가로축 단위')):
            field = QLineEdit(str(axis.get(key) or ''))
            field.setReadOnly(original.get('axis', {}).get(key) not in (None, '', 'UNKNOWN'))
            form.addRow(label, field); axis_fields[key] = field
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept); buttons.rejected.connect(dialog.reject); form.addRow(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        def field_value(field):
            if isinstance(field, QComboBox):
                return field.currentData() if field.currentText() == field.itemText(field.currentIndex()) else field.currentText()
            return field.text()
        declaration.update({key: field_value(field) for key, field in fields.items()})
        declaration.update(observable=deepcopy(observable.currentData()), temperature_kind=temperature.currentData())
        axis.update({key: field.text() for key, field in axis_fields.items()})
        self.value[side] = current; self.changed.emit()

    def settings(self):
        value = self.draft()
        dialog = QDialog(self); dialog.setWindowTitle('곡선 축 정렬'); form = QFormLayout(dialog)
        kind = combo([('미확인', None), ('물리시간', 'physical_time'), ('하중 단계 매개변수', 'load_parameter'),
                      ('변위', 'displacement'), ('변형률', 'strain'), ('다른 명시된 축', 'other')], value.get('axis_kind'))
        form.addRow('가로축 의미', kind)
        fields = {}
        labels = [('target_unit', '공통 응답 단위'), ('b_axis_offset', 'B 원점 이동 [A 축 단위]'),
                  ('axis_tolerance', '정확 대응 허용오차 [A 축 단위]'),
                  ('max_gap', '최대 보간 간격 [A 축 단위]'), ('axis_meaning', '다른 축의 물리 의미')]
        for key, label in labels:
            field = QLineEdit('' if value.get(key) is None else str(value[key]))
            form.addRow(label, field); fields[key] = field
        def mode_fields():
            fields['max_gap'].setEnabled(value.get('alignment') == 'bracket')
            fields['axis_meaning'].setEnabled(kind.currentData() == 'other')
        kind.currentIndexChanged.connect(mode_fields); mode_fields()
        bounds, origins = {}, {}
        for side in ('a', 'b'):
            source = value[side]
            group = QWidget(); row = QFormLayout(group); row.setContentsMargins(0, 0, 0, 0)
            low, high = source.get('rows', [0, source.get('row_count', 0)])
            first, last = QLineEdit(str(low+1) if type(low) is int else str(low)), QLineEdit(str(high))
            row.addRow('시작 행', first); row.addRow('마지막 행', last)
            form.addRow(side.upper()+' 원행 구간', group); bounds[side] = first, last
            origin = QLineEdit(value.get('axis_origins', {}).get(side, ''))
            form.addRow(side.upper()+' 축 원점', origin); origins[side] = origin
        confirmed = QCheckBox('선택한 두 측정 위치를 비교 대상으로 확인')
        confirmed.setChecked(value.get('locations_confirmed', False)); form.addRow(confirmed)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept); buttons.rejected.connect(dialog.reject); form.addRow(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        value.update(axis_kind=kind.currentData(), locations_confirmed=confirmed.isChecked(),
                     axis_origins={side: field.text() for side, field in origins.items()})
        for key, field in fields.items():
            value[key] = number_or_raw(field.text()) if key in ('b_axis_offset', 'axis_tolerance', 'max_gap') else field.text()
        for side, (first, last) in bounds.items():
            def row_value(text, adjustment):
                try:
                    return int(text) + adjustment
                except ValueError:
                    return text
            value[side]['rows'] = [row_value(first.text(), -1), row_value(last.text(), 0)]
        self.value = value; self.changed.emit()


class DataCurvePicker(QDialog):
    """Read actual document/job/channel choices with existing result catalog API."""
    def __init__(self, client, parent=None):
        super().__init__(parent)
        self.client = client; self.selected = None; self._workers = []; self._closed = False; self._serial = 0
        self.setWindowTitle('저장 시험 곡선'); self.resize(560, 250)
        layout = QFormLayout(self)
        self.documents, self.jobs, self.responses = QComboBox(), QComboBox(), QComboBox()
        for label, w in (('시험 자료', self.documents), ('저장 결과', self.jobs), ('물리량', self.responses)):
            w.setMinimumContentsLength(18); w.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            layout.addRow(label, w)
        self.message = QLabel('저장 자료를 읽고 있습니다.'); self.message.setWordWrap(True); layout.addRow(self.message)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText('가져오기')
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)
        self.buttons.accepted.connect(self.pick); self.buttons.rejected.connect(self.reject); layout.addRow(self.buttons)
        self.documents.currentIndexChanged.connect(self.document_changed)
        self.jobs.currentIndexChanged.connect(self.job_changed)
        self.responses.currentIndexChanged.connect(self.response_changed)
        QTimer.singleShot(0, self.load)

    def call(self, function, accepted):
        self._serial += 1; serial = self._serial
        worker = _Read(function); self._workers.append(worker)
        def done(value, error):
            if worker in self._workers:
                self._workers.remove(worker)
            if self._closed or serial != self._serial:
                return
            if error:
                self.message.setText(str(error))
            else:
                accepted(value)
        worker.signals.finished.connect(done, Qt.ConnectionType.QueuedConnection)
        QThreadPool.globalInstance().start(worker)

    def load(self):
        def accepted(listing):
            self.documents.blockSignals(True)
            for row in listing['documents']:
                if row.get('kind') == 'data':
                    self.documents.addItem(row.get('title', '시험'), row['id'])
            self.documents.blockSignals(False); self.document_changed()
        self.call(self.client.documents, accepted)

    def document_changed(self, *_):
        self.jobs.blockSignals(True); self.jobs.clear(); self.jobs.blockSignals(False)
        self.responses.clear()
        document = self.documents.currentData()
        if not document:
            return
        def accepted(doc):
            self.jobs.blockSignals(True)
            for i, run in enumerate(doc.get('runs', []), 1):
                if run.get('retention_complete'):
                    self.jobs.addItem('저장 결과 '+str(i), run['job_id'])
            self.jobs.blockSignals(False); self.job_changed()
        self.call(lambda: self.client.document_read(document), accepted)

    def job_changed(self, *_):
        self.responses.clear()
        document, job = self.documents.currentData(), self.jobs.currentData()
        if not job:
            return
        def accepted(metadata):
            if metadata.get('execution_counts', {}).get('SUCCEEDED') != 1:
                self.message.setText('완료된 가져오기 결과를 선택하세요.'); return
            for option in response_choices(metadata):
                if option['definition'].get('kind') == 'series' and not option.get('requires_location'):
                    self.responses.addItem(option['label'], option['selector'])
            self.message.setText('선택 채널의 보존 원행을 가져옵니다. 계산은 실행하지 않습니다.')
        self.call(lambda: self.client.document_result_metadata(document, job), accepted)

    def response_changed(self, *_):
        # A late reference reply belongs to the old channel, not the new label.
        self._serial += 1
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(self.responses.currentData() is not None)

    def pick(self):
        document, job, response = self.documents.currentData(), self.jobs.currentData(), self.responses.currentData()
        if not all((document, job, response)):
            return
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)
        def accepted(reference):
            if (document, job, response) != (self.documents.currentData(), self.jobs.currentData(), self.responses.currentData()):
                return
            self.selected = {'reference': reference, 'response': response}
            self.accept()
        self.call(lambda: self.client.document_result_reference(document, job), accepted)

    def done(self, result):
        self._closed = True
        super().done(result)
