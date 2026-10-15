"""Compact A/B editor; native owner remains the comparison executor."""
from copy import deepcopy
from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (QWidget, QGridLayout, QHBoxLayout, QVBoxLayout, QFormLayout,
    QLabel, QComboBox, QPushButton, QDialog, QDialogButtonBox, QLineEdit,
    QTabWidget, QTableWidget, QTableWidgetItem, QCheckBox, QListWidget,
    QListWidgetItem, QScrollArea, QHeaderView)
from apps.research.data_window import number_or_raw, display
from caelab.post_comparison import (IDENTITY, COMPONENTS, UNKNOWN_OBSERVABLE,
    observable_value, observable_label, retained_declarations)
from .experiment_dialogs import _ExplicitApplyDialog


def default_recipe():
    side = {'source_ref': '', 'array': '', 'association': 'POINTS', 'quantity': '',
        'units': '', 'measure': '', 'frame': '', 'coordinate_units': '', 'coordinate_frame': '',
        'time': None, 'time_units': None, 'time_origin': None, 'clock_offset': 0.,
        'sampling': {'mode': 'exact', 'time': None}, 'layout': None, 'validity_masks': []}
    return {'version': 2, 'a': deepcopy(side), 'b': deepcopy(side),
        'method': 'same_mesh', 'tolerance': 0., 'target': {'units': ''},
        'selection': 'scalar', 'difference': 'selected_difference', 'percent': 'disabled',
        'clock': {'value': None, 'unit': None, 'semantics': None},
        'coverage': {'policy': 'allow_partial', 'array': None},
        'conservation': {'mode': 'none'},
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
        self.result_summary = None
        self.selectors = {}
        self.layout_grid = QGridLayout(self)
        self.layout_grid.setContentsMargins(0, 0, 0, 0)
        self._refresh()

    def metadata(self, ref):
        source = next((r for r in self.sources if r['source_ref'] == ref), {})
        actual = deepcopy(source.get('metadata') or {})
        declared = retained_declarations(source.get('native_metadata')) or {}
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
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()
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
            meanings = {'force': '힘', 'displacement': '변위', 'cauchy': 'Cauchy 응력',
                        'global': '전역', 'rotated': '회전 기저'}
            info = QLabel(' / '.join(meanings.get(current.get(k), str(current.get(k) or '미지정'))
                                   for k in ('units', 'measure', 'frame')))
            if current.get('observable') is not None:
                info.setText(observable_label(current['observable']) + ' / ' + info.text())
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
        if self.value.get('selection') not in names:
            self.component.setItemText(self.component.currentIndex(), '성분 선택')
        self.component.currentIndexChanged.connect(lambda: self._set('selection', self.component.currentData()))
        self.layout_grid.addWidget(self.component, 5, 0)
        settings = QPushButton('변환 설정…'); settings.clicked.connect(self.settings)
        self.layout_grid.addWidget(settings, 5, 1)
        together = QPushButton('원본 나란히 보기')
        together.clicked.connect(lambda: self.showTogether.emit(self.value['a']['source_ref'], self.value['b']['source_ref']))
        self.layout_grid.addWidget(together, 6, 0, 1, 2)
        policy = self.value.get('coverage', {}).get('policy', 'allow_partial')
        note = QLabel({'allow_partial': '부분 비교: 무효 점은 마스크로 남깁니다.',
                       'all_a_points': 'A의 모든 점이 필수입니다. 무효 점이 있으면 적용하지 않습니다.',
                       'a_mask': 'A에서 지정한 마스크 영역이 필수입니다.'}.get(policy, '필수 영역 설정을 확인하세요.'))
        note.setWordWrap(True)
        note.setToolTip('점 보간과 인접 셀 평균은 보존적 전달이 아닙니다. 체적 적분 검사는 변환 설정에서 별도로 선택합니다.')
        self.layout_grid.addWidget(note, 7, 0, 1, 2)
        self.checks_button = QPushButton('영역과 적분 결과…')
        self.checks_button.clicked.connect(self.show_transfer_result)
        self.layout_grid.addWidget(self.checks_button, 8, 0, 1, 2)
        self.set_result_summary(self.result_summary)
        self.setMinimumWidth(0)

    def set_result_summary(self, summary):
        self.result_summary = deepcopy(summary) if (summary or {}).get('field_transfer') else None
        self.checks_button.setEnabled(self.result_summary is not None)
        earlier = self.result_summary is not None and self.result_summary.get('recipe') != self.value
        self.checks_button.setText('이전 결과의 영역과 적분…' if earlier else '영역과 적분 결과…')

    def show_transfer_result(self):
        if self.result_summary is None: return
        summary = deepcopy(self.result_summary)
        transfer = summary['field_transfer']; coverage = transfer['coverage']
        dialog = QDialog(self); dialog.setWindowTitle('영역과 적분 결과'); dialog.resize(820, 420)
        root = QVBoxLayout(dialog)
        heading = QLabel('현재 편집과 다른 이전 결과입니다.' if summary.get('recipe') != self.value
                         else '표에서 읽고 있는 비교 결과입니다.')
        heading.setWordWrap(True); root.addWidget(heading)
        root.addWidget(QLabel('필수 점 ' + str(coverage['required_count']) + '개 / 유효 점 '
                             + str(coverage['valid_count']) + '개'))
        integral = transfer['conservation']
        if integral['mode'] == 'none':
            root.addWidget(QLabel('체적 적분 검사를 요청하지 않았습니다.'))
        else:
            root.addWidget(QLabel('체적 적분: ' + ('허용값 만족' if integral['status'] == 'PASS' else '허용값 초과')
                                 + ' [' + integral['integral_units'] + ']'))
            count = len(integral['source_integral'])
            names = {1: ['스칼라'], 3: ['X', 'Y', 'Z'], 9: [n.upper() for n in COMPONENTS]}.get(count)
            result = QTableWidget(count, 5)
            result.setHorizontalHeaderLabels(['성분', '원 B 적분', 'A 위치 B 적분', '절대 오차', '허용값'])
            result.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
            for row in range(count):
                values = [names[row] if names else str(row + 1)] + [integral[key][row]
                    for key in ('source_integral', 'receiver_integral', 'absolute_error', 'limits')]
                for column, value in enumerate(values): result.setItem(row, column, QTableWidgetItem(str(value)))
            result.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
            root.addWidget(result, 1)
        note = QLabel('점 보간·인접 셀 평균은 보존적 전달 알고리즘이 아닙니다. 원 B 적분은 셀 자료라면 원 셀 값으로 계산합니다.')
        note.setWordWrap(True); root.addWidget(note)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.button(QDialogButtonBox.StandardButton.Close).setText('닫기')
        buttons.rejected.connect(dialog.reject); root.addWidget(buttons)
        dialog.exec()

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
        if selected is None:
            ref = self.value[side]['source_ref']
            self.value[side] = default_recipe()[side]
            self.value[side]['source_ref'] = ref
            self._refresh(); self.changed.emit()
            return
        current = self.value[side]; current['array'], current['association'] = selected
        metadata, declared = self.metadata(current['source_ref'])
        row = next((r for r in metadata.get('arrays', []) if [r['name'], r['association']] == selected), {})
        for key in ('quantity', 'units', 'measure', 'frame', 'layout', 'temperature_kind', 'validity_masks', 'observable', 'validity_policy', 'spatial_mask'):
            current[key] = deepcopy(row.get(key, [] if key == 'validity_masks' else None))
        if row.get('components') == 1 and current.get('layout') is None:
            current['layout'] = {'kind': 'scalar', 'components': ['scalar']}
        for key in ('coordinate_units', 'coordinate_frame', 'time_units'):
            current[key] = metadata.get(key)
        current['time_origin'] = metadata.get('time_semantics')
        current['sampling'] = {'mode': 'exact', 'time': None}; current['time'] = None
        current.pop('frozen_clock', None)
        if 'frozen_clock' in declared:
            current['frozen_clock'] = deepcopy(declared['frozen_clock'])
            if declared['frozen_clock']:
                current['time_units'] = declared['frozen_clock']['unit']
                current['time_origin'] = declared['frozen_clock']['semantics']
                if side == 'a': self.value['clock'] = deepcopy(declared['frozen_clock'])
        if side == 'a' and not self.value['target'].get('units'):
            self.value['target']['units'] = current.get('units')
        self._refresh(); self.changed.emit()

    def meaning(self, side):
        current = deepcopy(self.value[side]); metadata, declared = self.metadata(current['source_ref'])
        declaration = next((r for r in declared.get('arrays', []) if
            (r.get('name'), r.get('association')) == (current.get('array'), current.get('association'))), {})
        dialog = _ExplicitApplyDialog(self); dialog.setWindowTitle('물리량과 성분'); dialog.resize(620, 700)
        root = QVBoxLayout(dialog)
        page = QWidget(); form = QFormLayout(page)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setWidget(page)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame); root.addWidget(scroll)
        fields = {}
        labels = {'quantity': '물리량', 'units': '단위', 'measure': '측도', 'frame': '성분 좌표계',
                  'coordinate_units': '형상 길이 단위', 'coordinate_frame': '형상 좌표계',
                  'time_units': '시간 단위', 'time_origin': '시간 의미'}
        for key, title in labels.items():
            field = line(current.get(key))
            known = declared.get(key) if key.startswith('coordinate_') else declaration.get(key)
            if key in ('time_units', 'time_origin'):
                clock = declared.get('frozen_clock') or declared.get('time')
                if clock: known = clock.get('unit' if key == 'time_units' else 'semantics')
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
        if declaration.get('layout') is not None:
            for field in (kind, components, shear, scalar_meaning, tensor_indices): field.setEnabled(False)
        if declaration.get('temperature_kind') is not None: temperature.setEnabled(False)

        observed = current.get('observable')
        known_observed = declaration.get('observable')
        observable_fields = None
        if known_observed is not None and known_observed != UNKNOWN_OBSERVABLE:
            form.addRow('저장된 관측량', QLabel(observable_label(known_observed)))
        elif layout.get('kind') == 'scalar':
            leaves = [('미확인', None)]
            for source_kind, selections in (('scalar', ['scalar']), ('vector', ['x','y','z','magnitude']),
                                           ('tensor', COMPONENTS + ['magnitude'])):
                for selection in selections:
                    leaf = observable_value(source_kind, selection)
                    leaves.append((observable_label(leaf), leaf))
            invariant = observable_value('scalar', 'scalar', scalar_semantics='invariant')
            leaves.append(('회전에 무관한 스칼라 값', invariant))
            operand = observed.get('operand') if isinstance(observed, dict) and observed.get('operation') == 'difference' else observed
            if isinstance(observed, dict) and observed.get('operation') == 'norm_of_difference':
                operand = observable_value(observed['source_kind'], 'magnitude')
            if isinstance(operand, dict) and operand != UNKNOWN_OBSERVABLE and not any(value == operand for _, value in leaves):
                # A retained nested difference is not flattened by opening OK.
                leaves.append((observable_label(operand), deepcopy(operand)))
            leaf_field = combo(leaves, operand if operand != UNKNOWN_OBSERVABLE else None)
            leaf_field.setObjectName('observable_value')
            operation = combo([('원 관측량', 'value'), ('선택값의 차이 B − A', 'difference'),
                               ('전체 차이의 크기 |B − A|', 'norm_of_difference')],
                              observed.get('operation', 'value') if isinstance(observed, dict) and observed != UNKNOWN_OBSERVABLE else 'value')
            operation.setObjectName('observable_operation')
            form.addRow('원 성분 또는 크기', leaf_field); form.addRow('값의 정의', operation)
            observable_fields = (leaf_field, operation)

        masks = QListWidget(); masks.setObjectName('comparisonValidityMasks'); masks.setMaximumHeight(110)
        actual_masks = [row['name'] for row in metadata.get('arrays', [])
                        if row.get('association') == current.get('association') and row.get('components') == 1]
        selected_masks = current.get('validity_masks') or []
        for name in dict.fromkeys(actual_masks + selected_masks):
            item = QListWidgetItem(name if name in actual_masks else name + ' (원자료에 없음)', masks)
            item.setData(Qt.ItemDataRole.UserRole, name)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if name in selected_masks else Qt.CheckState.Unchecked)
        form.addRow('원자료 유효성 배열', masks)
        if declaration.get('validity_masks') is not None: masks.setEnabled(False)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText('설정 반영')
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('취소')
        for button in buttons.buttons(): button.setAutoDefault(False); button.setDefault(False)
        buttons.accepted.connect(dialog.accept); buttons.rejected.connect(dialog.reject); root.addWidget(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted: return
        for key, field in fields.items(): current[key] = field.text() or None
        current['layout'] = {'kind': kind.currentData(), 'components': [s.strip() for s in components.text().split(',') if s.strip()]}
        if kind.currentData() == 'scalar':
            current['layout'].update(components=['scalar'], scalar_semantics=scalar_meaning.currentData())
        if kind.currentData() == 'tensor': current['layout'].update(shear=shear.currentData(), indices=tensor_indices.currentData())
        if declaration.get('layout') is not None: current['layout'] = deepcopy(declaration['layout'])

        if known_observed is not None and known_observed != UNKNOWN_OBSERVABLE:
            current['observable'] = deepcopy(known_observed)
        elif observable_fields is not None:
            leaf_field, operation = observable_fields
            leaf = deepcopy(leaf_field.currentData())
            if leaf is None:
                current['observable'] = deepcopy(UNKNOWN_OBSERVABLE) if observed is not None else None
            elif operation.currentData() == 'difference':
                current['observable'] = {'version': 1, 'operation': 'difference', 'operand': leaf}
            elif operation.currentData() == 'norm_of_difference':
                current['observable'] = {'version': 1, 'operation': 'norm_of_difference',
                    'source_kind': leaf.get('source_kind'),
                    'norm': 'euclidean' if leaf.get('source_kind') == 'vector' else 'frobenius'}
            else:
                current['observable'] = leaf
        current['temperature_kind'] = temperature.currentData()
        current['validity_masks'] = [masks.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(masks.count()) if masks.item(i).checkState() == Qt.CheckState.Checked]
        self.value[side] = current
        if side == 'a' and not self.value['target'].get('units'): self.value['target']['units'] = current.get('units')
        self._refresh(); self.changed.emit()

    def settings(self):
        draft = deepcopy(self.value)
        dialog = _ExplicitApplyDialog(self); dialog.setWindowTitle('비교 변환'); dialog.resize(740, 620)
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
        geometry_checked = QCheckBox('이 형상 정렬을 명시적으로 사용')
        response_checked = QCheckBox('이 성분 기저 회전을 명시적으로 사용')
        geometry_checked.setChecked(bool(draft['alignment'].get('geometry_declared')))
        response_checked.setChecked(bool(draft['alignment'].get('response_declared')))
        form2.addRow(geometry_checked); form2.addRow(response_checked)
        time_page = QWidget(); timeform = QFormLayout(time_page); tabs.addTab(time_page, '시각')
        clock = draft.get('clock', {})
        common_time, common_unit, semantics = line(clock.get('value')), line(clock.get('unit')), line(clock.get('semantics'))
        exact_tolerance = line(clock.get('exact_tolerance', 0.))
        timeform.addRow('정확 시각 허용 오차 [비교 단위]', exact_tolerance)
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
            if 'frozen_clock' in draft[side]:
                fixed = draft[side]['frozen_clock']
                label = '시각 없는 저장 측정' if fixed is None else display(fixed['value']) + ' ' + str(fixed['unit']) + ' (고정)'
                timeform.addRow(side.upper() + ' 저장 표본', QLabel(label))
                for field in (mode, exact, lo, hi, maxgap): field.setEnabled(False)
            else:
                timeform.addRow(side.upper() + ' 방식', mode); timeform.addRow('저장 시각', exact)
            pair = QWidget(); pair_layout = QHBoxLayout(pair); pair_layout.setContentsMargins(0,0,0,0); pair_layout.addWidget(lo); pair_layout.addWidget(hi)
            if 'frozen_clock' not in draft[side]:
                timeform.addRow('보간 구간', pair); timeform.addRow('최대 간격 [비교 시간 단위]', maxgap)
            else:
                pair.setParent(time_page); pair.hide()
                maxgap.setParent(time_page); maxgap.hide()
                mode.setParent(time_page); mode.hide(); exact.setParent(time_page); exact.hide()
            timeform.addRow('원점 이동 [비교 시간 단위]', offset)
            time_controls[side] = (mode, exact, lo, hi, maxgap, offset)
        transfer_page = QWidget(); transfer_form = QFormLayout(transfer_page)
        transfer_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        tabs.addTab(transfer_page, '필수 영역과 적분')
        coverage = draft.get('coverage', {'policy': 'allow_partial', 'array': None})
        required = combo([('부분 비교 허용', 'allow_partial'), ('A 전체 점 필수', 'all_a_points'),
                          ('A 점 마스크로 지정', 'a_mask')], coverage.get('policy'))
        required.setObjectName('transferCoverage')
        metadata, _ = self.metadata(draft['a']['source_ref'])
        mask_choices = [('영역 배열 선택', None)] + [(row['name'], row['name'])
            for row in metadata.get('arrays', []) if row.get('association') == 'POINTS' and row.get('components') == 1]
        required_array = combo(mask_choices, coverage.get('array')); required_array.setObjectName('transferRequiredArray')
        required_array.setToolTip('실제 A 점 배열을 선택합니다. 적용할 때 모든 값이 0 또는 1인지 확인합니다.')
        transfer_form.addRow('필수 수신 영역', required); transfer_form.addRow('A 필수 영역 배열', required_array)
        required_array.setEnabled(required.currentData() == 'a_mask')
        required.currentIndexChanged.connect(lambda: required_array.setEnabled(required.currentData() == 'a_mask'))
        conservation = draft.get('conservation', {'mode': 'none'})
        integral = combo([('적분 검사 안 함', 'none'), ('원 B와 보간 B의 체적 적분 검사', 'check_volume_integral')], conservation.get('mode'))
        integral.setObjectName('transferConservation')
        absolute = line(conservation.get('absolute_tolerance', '')); absolute.setObjectName('transferIntegralAbsolute')
        relative = line(conservation.get('relative_tolerance', '')); relative.setObjectName('transferIntegralRelative')
        transfer_form.addRow('보간 후 보존 검사', integral)
        transfer_form.addRow('절대 허용값 [응답 단위 × A 길이 단위³]', absolute)
        transfer_form.addRow('상대 허용값 [1]', relative)
        def integral_enabled():
            for field in (absolute, relative): field.setEnabled(integral.currentData() == 'check_volume_integral')
        integral.currentIndexChanged.connect(integral_enabled); integral_enabled()
        limitation = QLabel('점 보간과 인접 셀 평균은 보존적 전달이 아닙니다.\n'
            '적분 검사는 같은 실제 경계 삼각형을 가진 선형 사면체 영역에서만 지원합니다. '
            '원 B의 전체 성분과 A에 전달된 B를 비교하며, 절대온도의 적분을 열량으로 해석하지 않습니다.')
        limitation.setWordWrap(True); transfer_form.addRow(limitation)
        for index in range(tabs.count()):
            page = tabs.widget(index); title = tabs.tabText(index)
            page.layout().setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
            tabs.removeTab(index)
            scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setWidget(page)
            scroll.setFrameShape(QScrollArea.Shape.NoFrame)
            tabs.insertTab(index, scroll, title)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText('설정 반영')
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('취소')
        for button in buttons.buttons():
            button.setAutoDefault(False); button.setDefault(False)
        buttons.accepted.connect(dialog.accept); buttons.rejected.connect(dialog.reject); root.addWidget(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted: return
        draft.update(method=method.currentData(), tolerance=number_or_raw(tolerance.text()),
            target={'units': units.text()}, difference=difference.currentData(), percent=percent.currentData())
        draft['coverage'] = {'policy': required.currentData(),
                             'array': required_array.currentData() if required.currentData() == 'a_mask' else None}
        draft['conservation'] = ({'mode': integral.currentData(),
            'absolute_tolerance': number_or_raw(absolute.text()),
            'relative_tolerance': number_or_raw(relative.text())}
            if integral.currentData() == 'check_volume_integral' else {'mode': integral.currentData()})
        for side, field in projections.items(): draft[side]['projection'] = field.currentData()
        for key, field in matrices.items(): draft['alignment'][key] = table_values(field)
        draft['alignment']['translation'] = table_values(translation)[0]
        draft['alignment'].update(geometry_declared=geometry_checked.isChecked(), response_declared=response_checked.isChecked())
        draft['clock'] = {'value': number_or_raw(common_time.text()) if common_time.text() else None,
                          'unit': common_unit.text() or None, 'semantics': semantics.text() or None,
                          'exact_tolerance': number_or_raw(exact_tolerance.text())}
        for side, (mode, exact, lo, hi, gap, offset) in time_controls.items():
            if 'frozen_clock' in draft[side]:
                # Preserve the known sample identity; only an explicit clock
                # origin conversion may change its position on the common axis.
                draft[side]['sampling'] = {'mode': 'exact', 'time': None}
                draft[side]['time'] = None
            elif mode.currentData() == 'exact':
                draft[side]['sampling'] = {'mode': 'exact', 'time': exact.currentData()}
                draft[side]['time'] = exact.currentData()
            elif mode.currentData() == 'linear':
                draft[side]['sampling'] = {'mode': 'linear', 'bracket': [lo.currentData(), hi.currentData()], 'max_gap': number_or_raw(gap.text())}
                draft[side]['time'] = None
            # Unknown saved sampling remains unchanged until the user selects a supported mode.
            draft[side]['clock_offset'] = number_or_raw(offset.text())
        self.value = draft; self._refresh(); self.changed.emit()
