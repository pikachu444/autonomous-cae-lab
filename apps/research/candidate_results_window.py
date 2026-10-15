"""Read an exact candidate's retained evaluations, stage attempts and histories."""
from copy import deepcopy
import json
import math

from PySide6.QtCore import Qt, QThreadPool
from PySide6.QtWidgets import (QComboBox, QHBoxLayout, QLabel, QMainWindow, QPlainTextEdit,
    QPushButton, QSpinBox, QSplitter, QTabWidget, QTableWidgetItem, QVBoxLayout, QWidget)
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure

from .data_window import _Read, display
from .runner_window import readonly_table, state_description

DATA = Qt.ItemDataRole.UserRole


class CandidateResultsWindow(QMainWindow):
    """A read-only candidate view; all result access stays in the existing owner."""
    def __init__(self, client, *, document_id, session_id, job_id, candidate_id,
                 values=None, units=None, relevant=None, post_open=None, parent=None):
        super().__init__(parent)
        self.client = client
        self.identity = (document_id, session_id, job_id, candidate_id)
        self._parent_relevant = relevant or (lambda: True)
        self.post_open = post_open
        self._closed = self._busy = self._populating = False
        self._pending = None
        self._worker = None
        self._serial = 0
        self._evaluation_index = self._attempt_id = None
        self._composite = self._stage_result = None
        self._native_catalog = {}
        self._curve_result = None
        self.resize(1180, 820)
        self.setWindowTitle('후보 분야 결과')
        root = QWidget(); layout = QVBoxLayout(root)
        label = QLabel('선택한 후보의 저장된 입력과 분야별 결과')
        label.setToolTip(f'{document_id} / {job_id} / {candidate_id} / {session_id}')
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(label)
        self.message = QLabel('후보의 보존 결과를 읽습니다. 계산 실행이나 입력 채택은 하지 않습니다.')
        self.message.setWordWrap(True); layout.addWidget(self.message)
        self.parameters = readonly_table(['설계 변수', '실제 적용값', '물리 단위'])
        self.parameters.setMaximumHeight(140)
        self._rows(self.parameters, [(name, value, (units or {}).get(name, '미기록')) for name, value in (values or {}).items()])
        self.parameters.setMaximumHeight(min(140, self.parameters.horizontalHeader().height() +
            sum(self.parameters.rowHeight(row) for row in range(self.parameters.rowCount())) + 4))
        layout.addWidget(self.parameters)
        row = QHBoxLayout(); self.evaluations = QComboBox()
        self.evaluations.setObjectName('candidateEvaluations')
        self.evaluations.currentIndexChanged.connect(self._evaluation_selected)
        self.refresh_button = QPushButton('결과 읽기 / 다시 시도')
        self.refresh_button.clicked.connect(self.refresh_catalog)
        row.addWidget(QLabel('후보 계산')); row.addWidget(self.evaluations, 1); row.addWidget(self.refresh_button)
        layout.addLayout(row)
        split = QSplitter(Qt.Orientation.Vertical)
        self.stages = readonly_table(['반복', '분야', '실행 식별자', '계산 상태', '계산 엔진', '재사용 여부'])
        self.stages.setObjectName('candidateStageAttempts')
        self.stages.itemSelectionChanged.connect(self._stage_selected)
        split.addWidget(self.stages)
        tabs = QTabWidget()
        self.responses = readonly_table(['응답', '종류', '단위', '성분', '위치', '배치 / 좌표계', '시간', '실제 값 / 보존 배열'])
        tabs.addTab(self.responses, '분야 응답')
        self.residuals = readonly_table(['반복', '분야', '응답', '단위', '실제 잔차', '허용값', '충족 여부'])
        tabs.addTab(self.residuals, '반복 수렴')
        from .s2_gradient_widgets import GradientEvidence
        self.gradient_evidence = GradientEvidence(self)
        tabs.addTab(self.gradient_evidence, '미분과 공유 입력')
        self.diagnostics = QPlainTextEdit(); self.diagnostics.setReadOnly(True)
        tabs.addTab(self.diagnostics, '기술 상세')
        curve = QWidget(); curve_layout = QVBoxLayout(curve)
        row = QHBoxLayout()
        self.native_channel, self.native_location = QComboBox(), QComboBox()
        self.native_channel.setObjectName('candidateNativeChannel')
        self.native_location.setObjectName('candidateNativeLocation')
        self.native_channel.currentIndexChanged.connect(self._native_channel_selected)
        self.native_location.currentIndexChanged.connect(self._curve_selection_changed)
        row.addWidget(QLabel('보존 채널')); row.addWidget(self.native_channel, 1)
        row.addWidget(QLabel('결과 위치')); row.addWidget(self.native_location, 1)
        curve_layout.addLayout(row)
        row = QHBoxLayout()
        self.curve_start, self.curve_count = QSpinBox(), QSpinBox()
        self.curve_start.setObjectName('candidateCurveStart'); self.curve_start.setRange(0, 2**31 - 1)
        self.curve_count.setObjectName('candidateCurveCount'); self.curve_count.setRange(1, 4096); self.curve_count.setValue(1000)
        self.curve_start.valueChanged.connect(self._curve_selection_changed)
        self.curve_count.valueChanged.connect(self._curve_selection_changed)
        self.curve_read = QPushButton('선택 곡선 읽기')
        self.curve_read.setObjectName('candidateReadNativeCurve'); self.curve_read.clicked.connect(self.read_native_curve)
        row.addWidget(QLabel('시작 행')); row.addWidget(self.curve_start)
        row.addWidget(QLabel('최대 행 수')); row.addWidget(self.curve_count); row.addWidget(self.curve_read); row.addStretch()
        curve_layout.addLayout(row)
        self.curve_figure = Figure(constrained_layout=True)
        self.curve_canvas = FigureCanvasQTAgg(self.curve_figure)
        self.curve_axes = self.curve_figure.add_subplot(111)
        self.curve_values = readonly_table(['보존 행', '축 값', '응답 값', '사용 여부'])
        self.curve_values.setObjectName('candidateNativeCurveValues'); self.curve_values.setMaximumHeight(180)
        self.curve_split = QSplitter(Qt.Orientation.Vertical)
        self.curve_split.addWidget(self.curve_canvas); self.curve_split.addWidget(self.curve_values)
        self.curve_split.setStretchFactor(0, 3); self.curve_split.setStretchFactor(1, 1)
        self.curve_split.setSizes([420, 100])
        curve_layout.addWidget(self.curve_split, 1)
        self.curve_detail = QLabel('보존 채널과 정확한 위치를 선택한 뒤 곡선을 읽으세요. 계산은 실행하지 않습니다.')
        self.curve_detail.setWordWrap(True); curve_layout.addWidget(self.curve_detail)
        self.curve_metadata_toggle = QPushButton('원자료와 물리량 상세')
        self.curve_metadata_toggle.setCheckable(True)
        self.curve_metadata = QPlainTextEdit()
        self.curve_metadata.setReadOnly(True)
        self.curve_metadata.setMaximumHeight(170)
        self.curve_metadata.hide()
        self.curve_metadata_toggle.toggled.connect(self.curve_metadata.setVisible)
        curve_layout.addWidget(self.curve_metadata_toggle)
        curve_layout.addWidget(self.curve_metadata)
        self.result_tabs = tabs
        tabs.addTab(curve, '보존 곡선')
        split.addWidget(tabs); split.setStretchFactor(0, 1); split.setStretchFactor(1, 3)
        self.stages.setMaximumHeight(180)
        split.setSizes([135, 550])
        layout.addWidget(split, 1)
        row = QHBoxLayout(); self.fields = QComboBox()
        self.fields.setObjectName('candidateRetainedFields')
        self.fields.currentIndexChanged.connect(self._update_actions)
        self.design_button = QPushButton('새 설계로 열기…')
        self.design_button.clicked.connect(self.open_design)
        self.post_button = QPushButton('선택 결과를 Post에서 열기')
        self.post_button.clicked.connect(self.open_post)
        self.transfer_button=QPushButton('전달값 보기')
        self.transfer_button.clicked.connect(self.open_transfer)
        row.addWidget(self.transfer_button)
        row.addWidget(self.fields, 1); row.addWidget(self.post_button); row.addWidget(self.design_button); layout.addLayout(row)
        self.setCentralWidget(root)
        self._update_actions()
        self.refresh_catalog()

    @staticmethod
    def _rows(table, rows):
        table.setRowCount(len(rows))
        for row, values in enumerate(rows):
            for column, value in enumerate(values):
                item = QTableWidgetItem(display(value)); item.setData(DATA, deepcopy(value))
                table.setItem(row, column, item)
        table.resizeColumnsToContents()

    def _current(self):
        return not self._closed and bool(self._parent_relevant())

    def _update_actions(self, *_):
        current = self._current()
        self.refresh_button.setEnabled(current and not self._busy)
        self.design_button.setEnabled(current and not self._busy and
            (self._composite or {}).get('execution_status') == 'SUCCEEDED' and
            bool((self._composite or {}).get('editable_design', {}).get('calculated')))
        self.post_button.setEnabled(current and not self._busy and self.fields.currentData() is not None)
        self.transfer_button.setEnabled(current and not self._busy and self._evaluation_index is not None and bool((self._composite or {}).get('transfers')))
        self.curve_read.setEnabled(current and not self._busy and self._evaluation_index is not None
                                   and self.native_location.currentData() is not None)

    def _call(self, function, accepted, key):
        if self._busy:
            self._pending = (function, accepted, key)
            return
        if not self._current():
            self.message.setText('The originating plan selection changed. Reopen from the selected candidate to read its records.')
            self._update_actions(); return
        self._busy = True; self._update_actions()
        worker = self._worker = _Read(function)
        def finished(value, error):
            self._busy = False; self._worker = None
            if self._current() and key == self._serial:
                if error: self.message.setText('Exact retained read failed; no execution started. ' + error)
                else:
                    try: accepted(value)
                    except (ValueError, TypeError, KeyError) as invalid:
                        self.message.setText('The retained response does not match this selected record. ' + str(invalid))
            elif not self._closed:
                self.message.setText('Selection changed while reading; the late response was ignored.')
            self._update_actions()
            pending, self._pending = self._pending, None
            if pending and not self._closed: self._call(*pending)
        worker.signals.finished.connect(finished, Qt.ConnectionType.QueuedConnection)
        QThreadPool.globalInstance().start(worker)

    def _check_identity(self, result, *, evaluation=False, attempt=False):
        document, _, job, candidate = self.identity
        if any(result.get(key) != expected for key, expected in
               [('document_id', document), ('job_id', job), ('candidate_id', candidate)]):
            raise ValueError('Document, job or candidate identity differs')
        if evaluation and result.get('evaluation_index') != self._evaluation_index:
            raise ValueError('Evaluation index differs')
        if attempt and result.get('stage_attempt', {}).get('attempt_id') != self._attempt_id:
            raise ValueError('Stage attempt differs')

    def refresh_catalog(self):
        self._serial += 1
        self._evaluation_index = self._attempt_id = None
        self._composite = self._stage_result = None
        self.gradient_evidence.set_result({})
        self.stages.setRowCount(0); self.responses.setRowCount(0); self.residuals.setRowCount(0); self.fields.clear()
        self._clear_curve_catalog()
        self._populating = True; self.evaluations.clear(); self._populating = False
        self.diagnostics.clear()
        document, _, job, candidate = self.identity
        def accepted(result):
            self._check_identity(result)
            self._populating = True; self.evaluations.clear()
            for record in result.get('evaluations', []):
                label = '계산 '+str(record['evaluation_index']+1)+' / '+state_description({'state':record.get('execution_status')})
                if 'stage_execution_count' in record:
                    label += f" / 분야 실행 {record['stage_execution_count']}회"
                else:
                    label += ' / 보존 결과'
                self.evaluations.addItem(label, record['evaluation_index'])
            self._populating = False
            if not self.evaluations.count():
                self.message.setText('이 후보의 보존 결과가 없습니다. 원 계산의 실패와 진단은 계획에서 확인하세요.')
                self.diagnostics.setPlainText(json.dumps(result, ensure_ascii=False, indent=2))
            else: self._evaluation_selected()
        self._call(lambda: self.client.numerical_evaluation_result(document, job, candidate), accepted, self._serial)

    def _evaluation_selected(self, *_):
        if self._populating: return
        self._serial += 1; self._evaluation_index = self.evaluations.currentData(); self._attempt_id = None
        self._composite = self._stage_result = None
        self.gradient_evidence.set_result({})
        self.stages.setRowCount(0); self.responses.setRowCount(0); self.residuals.setRowCount(0); self.fields.clear()
        self._clear_curve_catalog()
        if self._evaluation_index is None: return
        document, _, job, candidate = self.identity
        index = self._evaluation_index
        def accepted(result):
            self._check_identity(result, evaluation=True)
            self._composite = deepcopy(result)
            self._populating = True
            attempts = result.get('stages', []) + result.get('derivative_attempts', [])
            self._rows(self.stages, [(r.get('iteration'),
                ('수반 미분 / ' if 'primal_reference' in r else '') + result.get('stage_names', {}).get(r.get('stage_id'), str(r.get('stage_id'))),
                r.get('attempt_id'), state_description({'state':r.get('state')}),
                {'thermal.scikit_fem.rectangle':'scikit-fem 정상 열전도'}.get(r.get('backend'),r.get('backend')),
                '재사용' if r.get('reused_from') else '새 계산') for r in attempts])
            self.stages.setColumnHidden(2, True)
            for i,attempt in enumerate(attempts):
                self.stages.item(i,1).setToolTip(str(attempt.get('attempt_id'))+'\n'+str(attempt.get('backend')))
            self.stages.setVisible(bool(attempts))
            self.stages.setMaximumHeight(min(180, self.stages.horizontalHeader().height() +
                sum(self.stages.rowHeight(row) for row in range(self.stages.rowCount())) + 4))
            self._populating = False
            self._rows(self.residuals, [(i.get('iteration'), r.get('stage'), r.get('response'), r.get('unit'), r.get('observed'), r.get('limit'), r.get('passed')) for i in result.get('iterations', []) for r in i.get('checks', [])])
            self._display_result(result)
            detail = ' 분야를 선택하면 해당 원 결과를 따로 읽습니다.' if attempts else ' 이 계산에 보존된 채널을 읽습니다.'
            self.message.setText('보존 계산: ' + state_description({'state':result.get('execution_status')}) + '.' + detail)
        self._call(lambda: self.client.numerical_evaluation_result(document, job, candidate,
            evaluation_index=index, selection={'metadata_only': True}), accepted, self._serial)

    def _stage_selected(self):
        if self._populating: return
        rows = self.stages.selectionModel().selectedRows()
        if len(rows) != 1: return
        self._serial += 1
        self._attempt_id = self.stages.item(rows[0].row(), 2).data(DATA)
        self._stage_result = None; self.responses.setRowCount(0); self.fields.clear()
        self._clear_curve_catalog()
        document, _, job, candidate = self.identity
        index, attempt = self._evaluation_index, self._attempt_id
        def accepted(result):
            self._check_identity(result, evaluation=True, attempt=True)
            self._stage_result = deepcopy(result); self._display_result(result)
            self.message.setText('선택 분야 원 계산: '+state_description({'state':result.get('execution_status')})+
                '. 원 후보의 미분 검증과 최적화 사용 상태는 아래에서 확인하세요.')
        self._call(lambda: self.client.numerical_evaluation_result(document, job, candidate,
            evaluation_index=index, attempt_id=attempt, selection={'metadata_only': True}), accepted, self._serial)

    def _display_result(self, result):
        context=self._composite or result
        self.gradient_evidence.set_result(result, eligible=context.get('execution_status') == 'SUCCEEDED',parent=context)
        rows = []
        for name, response in result.get('responses', {}).items():
            value = response.get('value', response.get('data_ref'))
            if isinstance(value, list): value = {'count': len(value), 'first_values': value[:6]}
            rows.append((name, response.get('kind'), response.get('unit'), response.get('component'), response.get('location'),
                {'association': response.get('association'), 'frame': response.get('frame')},
                {'value': response.get('time'), 'unit': response.get('time_units')}, value))
        self._rows(self.responses, rows)
        self.diagnostics.setPlainText(json.dumps({'execution_status': result.get('execution_status'),
            'parent_execution_status':context.get('parent_execution_status'),
            'candidate_execution_status':context.get('candidate_execution_status'),
            'candidate_purpose':context.get('candidate_purpose'),
            'candidate_gradient_admission':context.get('candidate_gradient_admission'),
            'gradient_verification':context.get('gradient_verification'),
            'gradients':result.get('gradients'),'derivatives':result.get('derivatives'),
            'diagnostics': result.get('diagnostics'), 'checks': result.get('checks'), 'stage_attempt': result.get('stage_attempt'),
            'stages':result.get('stages'),'derivative_attempts':result.get('derivative_attempts')}, ensure_ascii=False, indent=2))
        self.fields.clear()
        fields = [result['post_input']] if result.get('post_input') else []
        fields += result.get('post_inputs', [])
        seen = set()
        for field in fields:
            if not isinstance(field, dict) or not field.get('id') or field['id'] in seen: continue
            seen.add(field['id'])
            name = field.get('response', '저장 결과')
            self.fields.addItem({'temperature':'온도','displacement':'변위','stress':'응력'}.get(name, name) +
                                ' [' + str(field.get('format', 'field')) + ']', deepcopy(field))
        if result.get('backend') == 'structure.calculix.design' and result.get('post_artifact'):
            self.fields.addItem('계산한 공간 결과', {'native_candidate': True})
        self._native_catalog = deepcopy(result.get('native_channels', {}))
        for name, response in result.get('responses', {}).items():
            if response.get('kind') == 'series':
                self._native_catalog.setdefault(name, {'unit': response.get('unit'),
                    'selectors': [{'selector': name, 'label': name}], 'axes': deepcopy(response.get('axes', []))})
        self.native_channel.blockSignals(True); self.native_channel.clear()
        for name, descriptor in self._native_catalog.items():
            self.native_channel.addItem(name + ' [' + str(descriptor.get('unit', '미기록')) + ']', name)
        self.native_channel.blockSignals(False)
        self._native_channel_selected()
        self._update_actions()

    def _clear_curve_data(self):
        self._curve_result = None
        self.curve_metadata.clear()
        self.curve_values.setRowCount(0)
        self.curve_axes.clear()
        self.curve_axes.text(.5, .5, '채널과 위치를 선택한 뒤 보존된 이력을 읽으세요.\n스칼라나 공간 결과 정보로 곡선을 추정하지 않습니다.',
                             ha='center', va='center', transform=self.curve_axes.transAxes)
        self.curve_canvas.draw_idle()

    def _clear_curve_catalog(self):
        self._native_catalog = {}
        self.native_channel.blockSignals(True); self.native_channel.clear(); self.native_channel.blockSignals(False)
        self.native_location.blockSignals(True); self.native_location.clear(); self.native_location.blockSignals(False)
        self._clear_curve_data()
        self.curve_detail.setText('이 결과에서 읽을 보존 이력을 선택하세요.')
        self._update_actions()

    def _native_channel_selected(self, *_):
        self.native_location.blockSignals(True); self.native_location.clear()
        name = self.native_channel.currentData()
        descriptor = self._native_catalog.get(name, {})
        selectors = descriptor.get('selectors', [])
        if descriptor.get('gauss_ids'):
            template = descriptor.get('selector_template')
            fields = ('element_id', 'point', 'subpoint')
            if isinstance(template, str) and all(template.count('<' + key + '>') == 1 for key in fields):
                for point in descriptor['gauss_ids']:
                    if not isinstance(point, dict) or not all(key in point for key in fields):
                        continue
                    selector = template
                    for key in fields:
                        selector = selector.replace('<' + key + '>', str(point[key]))
                    label = '요소 {} / 적분점 {} / 세부점 {}'.format(*(point[key] for key in fields))
                    self.native_location.addItem(label, selector)
        elif selectors and not descriptor.get('selectors_truncated'):
            for row in selectors:
                if isinstance(row, dict) and isinstance(row.get('selector'), str) and row['selector']:
                    self.native_location.addItem(str(row.get('label', row['selector'])), row['selector'])
        elif descriptor.get('node_ids'):
            template = descriptor.get('selector_template', str(name) + '@<node_id>')
            if isinstance(template, str) and template.count('<node_id>') == 1:
                for node in descriptor['node_ids']:
                    self.native_location.addItem('절점 ' + str(node), template.replace('<node_id>', str(node)))
        else:
            selector = descriptor.get('source', {}).get('selector')
            if isinstance(selector, str) and selector:
                self.native_location.addItem(selector, selector)
        self.native_location.blockSignals(False)
        self._curve_selection_changed()

    def _curve_selection_changed(self, *_):
        self._clear_curve_data()
        self.curve_detail.setText('선택한 위치의 보존 이력을 읽습니다.' if self.native_location.currentData() is not None
                                 else '이 결과에는 읽을 수 있는 정확한 위치별 이력이 없습니다.')
        self._update_actions()

    def _curve_key(self):
        return (self.identity, self._evaluation_index, self._attempt_id, self.native_channel.currentData(),
                self.native_location.currentData(), self.curve_start.value(), self.curve_count.value())

    def read_native_curve(self):
        if not self._current() or self._busy or self._evaluation_index is None:
            return
        key = self._curve_key()
        selector = self.native_location.currentData()
        if selector is None:
            return
        document, _, job, candidate = self.identity
        index, attempt = self._evaluation_index, self._attempt_id
        start, count = self.curve_start.value(), self.curve_count.value()
        def accepted(result):
            if self._curve_key() != key:
                self.message.setText('Native channel, location or sample page changed; the late curve was ignored.')
                return
            self._check_identity(result, evaluation=True, attempt=attempt is not None)
            response = result.get('responses', {}).get(selector)
            if not isinstance(response, dict) or response.get('kind') != 'series':
                raise ValueError('Selected native response is not an actual retained series')
            values = response.get('value')
            axis = next((a for a in response.get('axes', []) if isinstance(a, dict) and isinstance(a.get('values'), list)), None)
            if (not isinstance(values, list) or not values or len(values) > count or axis is None
                    or len(axis['values']) != len(values)
                    or any(type(v) not in (int, float) or not math.isfinite(v) for v in values + axis['values'])):
                raise ValueError('Retained native curve has no matching bounded finite scalar axis/value rows')
            mask = response.get('mask')
            if mask is not None and (not isinstance(mask, list) or len(mask) != len(values) or any(type(v) is not bool for v in mask)):
                raise ValueError('Retained curve validity mask differs from the bounded samples')
            rows = response.get('source_rows', list(range(start, start + len(values))))
            if not isinstance(rows, list) or len(rows) != len(values):
                raise ValueError('Retained curve original sample identities differ from its values')
            self._curve_result = deepcopy(response)
            self._rows(self.curve_values, [(row, x, y, '사용' if mask is None or mask[i] else '제외')
                for i, (row, x, y) in enumerate(zip(rows, axis['values'], values))])
            self.curve_axes.clear()
            self.curve_axes.plot(axis['values'], [v if mask is None or mask[i] else math.nan for i, v in enumerate(values)], label=selector)
            self.curve_axes.set_xlabel(str(axis.get('name', 'axis')) + ' [' + str(axis.get('unit', 'undeclared')) + ']')
            self.curve_axes.set_ylabel(selector + ' [' + str(response.get('unit', 'undeclared')) + ']')
            self.curve_axes.legend(); self.curve_canvas.draw_idle()
            self.curve_detail.setText(str(response.get('unit', '미기록')) +
                ' / 보존 행 ' + str(start) + '–' + str(start + len(values)) + ' / 원자료 값')
            self.curve_metadata.setPlainText(display({'selector': selector, 'component': response.get('component'),
                'quantity': response.get('quantity'), 'location': response.get('location'),
                'frame': response.get('frame', response.get('coordinate_frame')), 'measure': response.get('measure'),
                'axes': [{key: deepcopy(axis[key]) for key in ('name', 'unit', 'semantics') if key in axis}
                         for axis in response.get('axes', [])],
                'source': response.get('source'), 'sample_page': [start, start + len(values)]}))
            self.result_tabs.setCurrentIndex(self.result_tabs.count() - 1)
            self.message.setText('보존한 원자료 '+str(len(values))+'개를 읽었습니다. 계산이나 채택은 실행하지 않았습니다.')
        options = {'evaluation_index': index, 'selection': {'responses': [selector], 'rows': [start, start + count]}}
        if attempt is not None:
            options['attempt_id'] = attempt
        self._call(lambda: self.client.numerical_evaluation_result(document, job, candidate, **options), accepted, self._serial)

    def open_design(self):
        if not self._current() or self._busy or self._evaluation_index is None:
            return
        from PySide6.QtWidgets import QMessageBox
        answer = QMessageBox.question(self, 'Open calculated design',
            'Open this calculated candidate as a separate editable CAD design?',
            QMessageBox.StandardButton.Open | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel)
        if answer != QMessageBox.StandardButton.Open:
            return
        document, _, job, candidate = self.identity
        index = self._evaluation_index
        def launch():
            receipt = self.client.cad_candidate_open(document, job, candidate, index)
            from .desktop import _spawn
            return _spawn(self.client, ['pre', '--input-id', receipt['input_id']])
        self._call(launch, lambda _: self.message.setText('Opened the retained calculated candidate as a new design.'), self._serial)

    def open_transfer(self):
        if self._evaluation_index is None:return
        document,_,job,candidate=self.identity
        index=self._evaluation_index
        # Capture the immutable selection. Later row selection never retargets
        # an open inspection window or launches a calculation.
        def read_transfer(transfer_id=None,iteration=None,*,start=0,count=256):
            query={'start':start,'count':count}
            if transfer_id is not None:query.update(id=transfer_id,iteration=iteration)
            return self.client.numerical_evaluation_result(document,job,candidate,
                evaluation_index=index,selection={'transfer':query})
        from .transfer_inspection_window import TransferInspectionWindow
        window=TransferInspectionWindow(self.client,document,job,parent=self,read_transfer=read_transfer)
        window.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose,True)
        window.show()

    def open_post(self):
        field = self.fields.currentData()
        if not field or not self._current(): return
        document, _, job, candidate = self.identity
        source = {'document_id': document, 'candidate_id': candidate, 'evaluation_index': self._evaluation_index, 'attempt_id': self._attempt_id}
        def launch():
            selected = field
            if field.get('native_candidate'):
                selected = self.client.cad_candidate_post(document, job, candidate, source['evaluation_index'])
            native = self.client.native_input(selected['id'])
            if not selected.get('sha256') or native.get('sha256') != selected['sha256']:
                raise ValueError('Registered field differs from this retained stage result')
            if self.post_open: return self.post_open(deepcopy(selected), deepcopy(source))
            from .desktop import launch_post
            return launch_post(self.client, selected['id'], job_id=job, research_source=source)
        self._call(launch, lambda _: self.message.setText('Requested Post for the exact retained field and parent Plan job.'), self._serial)

    def closeEvent(self, event):
        self._closed = True; self._serial += 1; self._pending = None
        event.accept()
