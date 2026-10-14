"""Compact A/B editor; native owner remains the comparison executor."""
from copy import deepcopy
from PySide6.QtCore import Signal
from PySide6.QtWidgets import (QWidget, QGridLayout, QHBoxLayout, QVBoxLayout, QFormLayout,
    QLabel, QComboBox, QPushButton, QDialog, QDialogButtonBox, QLineEdit,
    QTabWidget, QTableWidget, QTableWidgetItem, QCheckBox)
from apps.research.data_window import number_or_raw, display
from caelab.post_comparison import IDENTITY, COMPONENTS


def default_recipe():
    side = {'source_ref': '', 'array': '', 'association': 'POINTS', 'quantity': '',
        'units': '', 'measure': '', 'frame': '', 'coordinate_units': '', 'coordinate_frame': '',
        'time': None, 'time_units': None, 'time_origin': None, 'clock_offset': 0.,
        'sampling': {'mode': 'exact', 'time': None}, 'layout': None, 'validity_masks': []}
    return {'version': 2, 'a': deepcopy(side), 'b': deepcopy(side),
        'method': 'same_mesh', 'tolerance': 0., 'target': {'units': ''},
        'selection': 'scalar', 'difference': 'selected_difference', 'percent': 'disabled',
        'clock': {'value': None, 'unit': None, 'semantics': None},
        'alignment': {'geometry_rotation': deepcopy(IDENTITY), 'response_rotation': deepcopy(IDENTITY),
                      'translation': [0., 0., 0.], 'geometry_declared': False, 'response_declared': False}}


def combo(items, selected, parent=None):
    field = QComboBox(parent)
    for text, value in items: field.addItem(text, deepcopy(value))
    index = field.findData(selected)
    if index < 0:
        field.addItem('미확인: ' + display(selected), deepcopy(selected)); index = field.count()-1
    field.setCurrentIndex(index)
    return field


def line(value):
    return QLineEdit('' if value is None else str(value))


def table(values, columns):
    widget = QTableWidget(len(values), len(columns))
    widget.setHorizontalHeaderLabels(columns)
    for r, row in enumerate(values):
        for c, value in enumerate(row): widget.setItem(r, c, QTableWidgetItem(str(value)))
    widget.setMaximumHeight(135)
    for c in range(len(columns)): widget.setColumnWidth(c, 85)
    return widget


def table_values(widget):
    return [[number_or_raw(widget.item(r, c).text() if widget.item(r, c) else '')
             for c in range(widget.columnCount())] for r in range(widget.rowCount())]


class ComparisonEditor(QWidget):
    changed = Signal()
    showSource = Signal(str)
    showTogether = Signal(str, str)

    def __init__(self, draft, sources, parent=None):
        super().__init__(parent)
        self.value = deepcopy(draft); self.sources = deepcopy(sources)
        self.selectors = {}
        self.layout_grid = QGridLayout(self)
        self.layout_grid.setContentsMargins(0, 0, 0, 0)
        self._refresh()

    def metadata(self, ref):
        source = next((r for r in self.sources if r['source_ref'] == ref), {})
        actual = deepcopy(source.get('metadata') or {})
        declared = source.get('native_metadata') or {}
        by_key = {(r.get('name'), r.get('association')): r for r in declared.get('arrays', [])}
        rows = actual.get('arrays') or declared.get('arrays', [])
        actual['arrays'] = [{**r, **by_key.get((r.get('name'), r.get('association')), {})} for r in rows]
        for key in ('coordinate_units', 'coordinate_frame'):
            if declared.get(key) is not None: actual[key] = declared[key]
        clock = declared.get('time') or {}
        if clock:
            actual.update(time_units=clock.get('unit'), time_semantics=clock.get('semantics'))
        return actual, declared

    def _refresh(self):
        while self.layout_grid.count():
            item = self.layout_grid.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        self.selectors = {}
        for column, side in enumerate(('a', 'b')):
            current = self.value[side]
            self.layout_grid.addWidget(QLabel('기준 결과 A' if side == 'a' else '비교 결과 B'), 0, column)
            source = combo([('자료 선택', '')] + [(r['label'], r['source_ref']) for r in self.sources], current['source_ref'])
            source.setMinimumWidth(0); source.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            source.setMinimumContentsLength(12)
            self.layout_grid.addWidget(source, 1, column)
            metadata, _ = self.metadata(current['source_ref'])
            fields = [('물리량 선택', None)]
            for row in metadata.get('arrays', []):
                if row.get('association') not in ('POINTS', 'CELLS'): continue
                label = row['name'] + ' (' + {'POINTS': '점', 'CELLS': '셀'}[row['association']] + ')'
                fields.append((label, [row['name'], row['association']]))
            field = combo(fields, [current['array'], current['association']] if current.get('array') else None)
            field.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            field.setMinimumContentsLength(12)
            self.layout_grid.addWidget(field, 2, column)
            info = QLabel(' / '.join(str(current.get(k) or '미지정') for k in ('units', 'measure', 'frame')))
            info.setWordWrap(True); self.layout_grid.addWidget(info, 3, column)
            actions = QWidget(); row = QHBoxLayout(actions); row.setContentsMargins(0, 0, 0, 0)
            meaning = QPushButton('물리량 확인…'); meaning.clicked.connect(lambda checked=False, s=side: self.meaning(s))
            original = QPushButton('원본 보기'); original.clicked.connect(lambda checked=False, s=side: self.showSource.emit(self.value[s]['source_ref']))
            row.addWidget(meaning); row.addWidget(original); self.layout_grid.addWidget(actions, 4, column)
            source.currentIndexChanged.connect(lambda i, s=side, w=source: self.change_source(s, w.currentData()))
            field.currentIndexChanged.connect(lambda i, s=side, w=field: self.change_field(s, w.currentData()))
            self.selectors[side] = (source, field)
        kind = (self.value['a'].get('layout') or {}).get('kind')
        names = {'scalar': ['scalar'], 'vector': ['x', 'y', 'z', 'magnitude'], 'tensor': COMPONENTS + ['magnitude']}.get(kind, [])
        labels = {'scalar': '스칼라 값', 'magnitude': '크기'}
        self.component = combo([(labels.get(n, n.upper()), n) for n in names], self.value.get('selection'))
        self.component.currentIndexChanged.connect(lambda: self._set('selection', self.component.currentData()))
        self.layout_grid.addWidget(self.component, 5, 0)
        settings = QPushButton('변환 설정…'); settings.clicked.connect(self.settings)
        self.layout_grid.addWidget(settings, 5, 1)
        together = QPushButton('원본 나란히 보기')
        together.clicked.connect(lambda: self.showTogether.emit(self.value['a']['source_ref'], self.value['b']['source_ref']))
        self.layout_grid.addWidget(together, 6, 0, 1, 2)
        self.setMinimumWidth(0)

    def draft(self):
        return deepcopy(self.value)

    def _set(self, key, value):
        self.value[key] = deepcopy(value); self.changed.emit()

    def change_source(self, side, ref):
        if ref == self.value[side]['source_ref']: return
        fresh = default_recipe()[side]; fresh['source_ref'] = ref
        self.value[side] = fresh
        self._refresh(); self.changed.emit()

    def change_field(self, side, selected):
        if selected is None: return
        current = self.value[side]; current['array'], current['association'] = selected
        metadata, declared = self.metadata(current['source_ref'])
        row = next((r for r in metadata.get('arrays', []) if [r['name'], r['association']] == selected), {})
        for key in ('quantity', 'units', 'measure', 'frame', 'layout', 'temperature_kind', 'validity_masks'):
            current[key] = deepcopy(row.get(key, [] if key == 'validity_masks' else None))
        if row.get('components') == 1 and current.get('layout') is None:
            current['layout'] = {'kind': 'scalar', 'components': ['scalar']}
        for key in ('coordinate_units', 'coordinate_frame', 'time_units'):
            current[key] = metadata.get(key)
        current['time_origin'] = metadata.get('time_semantics')
        current['sampling'] = {'mode': 'exact', 'time': None}; current['time'] = None
        if side == 'a' and not self.value['target'].get('units'):
            self.value['target']['units'] = current.get('units')
        self._refresh(); self.changed.emit()

    def meaning(self, side):
        current = deepcopy(self.value[side]); metadata, declared = self.metadata(current['source_ref'])
        declaration = next((r for r in declared.get('arrays', []) if
            (r.get('name'), r.get('association')) == (current.get('array'), current.get('association'))), {})
        dialog = QDialog(self); dialog.setWindowTitle('물리량과 성분'); form = QFormLayout(dialog)
        fields = {}
        labels = {'quantity': '물리량', 'units': '단위', 'measure': '측도', 'frame': '성분 좌표계',
                  'coordinate_units': '형상 길이 단위', 'coordinate_frame': '형상 좌표계',
                  'time_units': '시간 단위', 'time_origin': '시간 의미'}
        for key, title in labels.items():
            field = line(current.get(key))
            known = declared.get(key) if key.startswith('coordinate_') else declaration.get(key)
            if key in ('time_units', 'time_origin') and declared.get('time'):
                known = declared['time'].get('unit' if key == 'time_units' else 'semantics')
            if known is not None: field.setText(str(known)); field.setReadOnly(True)
            form.addRow(title, field); fields[key] = field
        layout = current.get('layout') or {}
        kind = combo([('미확인', None), ('스칼라', 'scalar'), ('벡터', 'vector'), ('텐서', 'tensor')], layout.get('kind'))
        components = QLineEdit(', '.join(layout.get('components', [])))
        components.setPlaceholderText('벡터: x, y, z   텐서: xx, yy, zz, xy, yz, xz')
        shear = combo([('실제 텐서 전단', 'tensor'), ('공학 전단 변형률', 'engineering'), ('Kelvin 성분', 'kelvin')], layout.get('shear', 'tensor'))
        temperature = combo([('해당 없음 / 미확인', None), ('절대온도', 'absolute'), ('온도차', 'difference')], current.get('temperature_kind'))
        scalar_meaning = combo([('미확인', None), ('회전에 무관한 스칼라', 'invariant'), ('벡터·텐서의 한 성분', 'component')], layout.get('scalar_semantics'))
        tensor_indices = combo([('미확인 / 두 기저', None), ('두 지표가 같은 직교 기저', 'same_cartesian_basis')], layout.get('indices'))
        form.addRow('스칼라 의미', scalar_meaning); form.addRow('텐서 기저', tensor_indices)
        form.addRow('성분 종류', kind); form.addRow('배열의 성분 순서', components)
        form.addRow('텐서 전단 규약', shear); form.addRow('온도 의미', temperature)
        mask = QLineEdit(', '.join(current.get('validity_masks') or [])); form.addRow('원자료 유효성 배열', mask)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept); buttons.rejected.connect(dialog.reject); form.addRow(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted: return
        for key, field in fields.items(): current[key] = field.text() or None
        current['layout'] = {'kind': kind.currentData(), 'components': [s.strip() for s in components.text().split(',') if s.strip()]}
        if kind.currentData() == 'scalar':
            current['layout'].update(components=['scalar'], scalar_semantics=scalar_meaning.currentData())
        if kind.currentData() == 'tensor': current['layout'].update(shear=shear.currentData(), indices=tensor_indices.currentData())
        current['temperature_kind'] = temperature.currentData()
        current['validity_masks'] = [s.strip() for s in mask.text().split(',') if s.strip()]
        self.value[side] = current
        if side == 'a' and not self.value['target'].get('units'): self.value['target']['units'] = current.get('units')
        self._refresh(); self.changed.emit()

    def settings(self):
        draft = deepcopy(self.value)
        dialog = QDialog(self); dialog.setWindowTitle('비교 변환'); dialog.resize(680, 570)
        root = QVBoxLayout(dialog); tabs = QTabWidget(); root.addWidget(tabs)
        common = QWidget(); form = QFormLayout(common); tabs.addTab(common, '비교 방법')
        method = combo([('같은 위치와 점 순서', 'same_mesh'), ('B 사면체에서 A 위치 보간', 'linear_tetra_b_to_a')], draft['method'])
        tolerance = line(draft['tolerance']); units = line(draft['target'].get('units'))
        difference = combo([('선택값 B − A', 'selected_difference'), ('차이 벡터·텐서의 크기 |B − A|', 'norm_of_difference')], draft.get('difference', 'selected_difference'))
        percent = combo([('변화율 계산 안 함', 'disabled'), ('A의 절댓값 기준', 'relative_a'), ('절대온도 Kelvin 기준', 'absolute_kelvin')], draft.get('percent', 'disabled'))
        form.addRow('공간 대응', method); form.addRow('공간 허용 오차 [A 좌표 단위]', tolerance)
        form.addRow('비교 응답 단위', units); form.addRow('차이', difference); form.addRow('변화율', percent)
        projections = {}
        for side in ('a', 'b'):
            if draft[side].get('association') == 'CELLS':
                projections[side] = combo([('미선택', None), ('인접 셀 동일 가중 평균 → 점', 'cell_to_point_equal_incident')], draft[side].get('projection'))
                form.addRow(side.upper() + ' 셀 값', projections[side])
        alignment = QWidget(); form2 = QFormLayout(alignment); tabs.addTab(alignment, '좌표 정렬')
        matrices = {}
        for key, label in [('geometry_rotation', 'B 형상 축 → A 형상 축'), ('response_rotation', 'B 성분 기저 → A 성분 기저')]:
            matrices[key] = table(draft['alignment'][key], ['X', 'Y', 'Z']); form2.addRow(label, matrices[key])
        translation = table([draft['alignment']['translation']], ['X', 'Y', 'Z'])
        form2.addRow('형상 이동 [A 길이 단위]', translation)
        checked = QCheckBox('이 형상 정렬과 성분 기저 회전을 명시적으로 사용')
        checked.setChecked(bool(draft['alignment'].get('geometry_declared') and draft['alignment'].get('response_declared')))
        form2.addRow(checked)
        time_page = QWidget(); timeform = QFormLayout(time_page); tabs.addTab(time_page, '시각')
        clock = draft.get('clock', {})
        common_time, common_unit, semantics = line(clock.get('value')), line(clock.get('unit')), line(clock.get('semantics'))
        timeform.addRow('비교 시각', common_time); timeform.addRow('시간 단위', common_unit); timeform.addRow('시간 의미', semantics)
        time_controls = {}
        for side in ('a', 'b'):
            metadata, _ = self.metadata(draft[side]['source_ref'])
            times = metadata.get('timesteps', [])
            sample = draft[side].get('sampling', {'mode': 'exact', 'time': draft[side].get('time')})
            mode = combo([('정확한 저장 시각', 'exact'), ('두 시각 사이 선형 보간', 'linear')], sample.get('mode'))
            items = [('시각 없음', None)] + [(display(t), t) for t in times]
            exact = combo(items, sample.get('time'))
            bracket = sample.get('bracket', [None, None])
            lo, hi = combo(items, bracket[0]), combo(items, bracket[1])
            maxgap, offset = line(sample.get('max_gap')), line(draft[side].get('clock_offset', 0.))
            timeform.addRow(side.upper() + ' 방식', mode); timeform.addRow('저장 시각', exact)
            pair = QWidget(); pair_layout = QHBoxLayout(pair); pair_layout.setContentsMargins(0,0,0,0); pair_layout.addWidget(lo); pair_layout.addWidget(hi)
            timeform.addRow('보간 구간', pair); timeform.addRow('최대 간격 [비교 시간 단위]', maxgap)
            timeform.addRow('원점 이동 [비교 시간 단위]', offset)
            time_controls[side] = (mode, exact, lo, hi, maxgap, offset)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept); buttons.rejected.connect(dialog.reject); root.addWidget(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted: return
        draft.update(method=method.currentData(), tolerance=number_or_raw(tolerance.text()),
            target={'units': units.text()}, difference=difference.currentData(), percent=percent.currentData())
        for side, field in projections.items(): draft[side]['projection'] = field.currentData()
        for key, field in matrices.items(): draft['alignment'][key] = table_values(field)
        draft['alignment']['translation'] = table_values(translation)[0]
        draft['alignment'].update(geometry_declared=checked.isChecked(), response_declared=checked.isChecked())
        draft['clock'] = {'value': number_or_raw(common_time.text()) if common_time.text() else None,
                          'unit': common_unit.text() or None, 'semantics': semantics.text() or None}
        for side, (mode, exact, lo, hi, gap, offset) in time_controls.items():
            draft[side]['sampling'] = ({'mode': 'exact', 'time': exact.currentData()} if mode.currentData() == 'exact' else
                {'mode': 'linear', 'bracket': [lo.currentData(), hi.currentData()], 'max_gap': number_or_raw(gap.text())})
            draft[side]['time'] = exact.currentData() if mode.currentData() == 'exact' else None
            draft[side]['clock_offset'] = number_or_raw(offset.text())
        self.value = draft; self._refresh(); self.changed.emit()
