"""Qt original-row return using existing plot, command queue and reference view.

The local guard is deliberately checked on the GUI thread between every remote
phase. A worker only executes one phase, never verify+select+activate together.
"""
from copy import deepcopy
import json

from PySide6.QtCore import QObject, Qt, Slot, QThreadPool
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QFileDialog, QTableWidget, QTableWidgetItem, QAbstractItemView,
    QHeaderView, QPlainTextEdit, QGridLayout)

from caelab.post_curve_origin import read_data
from .post_curve_origin import NativeReturn
from .post_curve_plot import text
from .expert_window import _Call
from .reference_content import ReferenceContent


def unit_label(value):
    return str(value) if value not in (None, '', 'UNKNOWN') else '단위 미상'


def with_unit(value, unit):
    return f'{text(value)} {unit_label(unit)}'


def table(parent, columns, rows):
    widget = QTableWidget(len(rows), len(columns), parent)
    widget.setHorizontalHeaderLabels([title for _, title in columns])
    widget.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    widget.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    widget.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    widget.verticalHeader().hide()
    widget.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
    widget.horizontalHeader().setStretchLastSection(True)
    for i, row in enumerate(rows):
        for j, (key, _) in enumerate(columns):
            value = row.get(key)
            item = QTableWidgetItem(text(value)); item.setToolTip(str(value))
            widget.setItem(i, j, item)
    return widget


class OriginControls(QObject):
    """Lifetime and row-choice guard owned by the already existing CurvePlot."""
    def __init__(self, plot, host):
        super().__init__(plot)
        self.plot, self.host = plot, host
        self.serial, self.choice, self.closed = 0, None, False
        self.pending_basis = None
        self.button = QPushButton('원자료 열기…', plot)
        self.button.setObjectName('openCurveOriginal')
        self.button.setToolTip('A 또는 B의 실제 원행을 확인합니다. 보간 B는 양쪽 원행을 각각 엽니다.')
        plot.layout().addWidget(self.button)
        self.button.clicked.connect(self.read)
        for tag, widget in plot.tables.items():
            widget.itemSelectionChanged.connect(lambda tag=tag: self.changed(tag))
        plot.finished.connect(self.close)

    @Slot(int)
    def close(self, *_):
        self.closed = True; self.serial += 1

    def changed(self, tag):
        if self.closed: return
        widget = self.plot.tables[tag]; row = widget.currentRow()
        self.serial += 1
        self.choice = None if row < 0 or widget.item(row, 0) is None else (
            tag, widget.item(row, 0).data(Qt.ItemDataRole.UserRole))

    def basis(self):
        host = self.host
        return (deepcopy(self.plot.basis), host.document_id, host.session_id,
                host._object_ref, host._edit_serial, self.serial, self.choice)

    def current(self, basis):
        try:
            host = self.host
            return (not self.closed and self.plot.isVisible() and host.isVisible()
                and not getattr(host, '_allow_close', False) and not host.local_dirty
                and basis == self.basis() and not basis[0].get('preview', True)
                and (basis[0].get('document_id'), basis[0].get('session_id'), basis[0].get('object_ref'))
                    == (host.document_id, host.session_id, host._object_ref)
                and host._current_sample_revision(False) == basis[0].get('revision'))
        except (RuntimeError, AttributeError):
            return False

    @Slot()
    def read(self):
        basis = self.basis()
        if not self.choice or not self.current(basis):
            self.host.message.setText('적용·저장한 v3 비교의 원곡선 또는 대응 표에서 원행을 선택하세요.')
            return
        if self.pending_basis is not None and self.host._pending is None and not self.host._busy:
            self.pending_basis = None  # Previous read-only request terminated or never submitted.
        if self.pending_basis is not None:
            self.host.message.setText('원행 읽기 요청이 남아 있습니다. 기존 명령 상태를 확인하세요.')
            return
        self.pending_basis = basis
        try:
            accepted = self.host.queue_command('post.curve_origin_read', {
                'object_ref': basis[0]['object_ref'], 'revision': basis[0]['revision'],
                'table': self.choice[0], 'row_index': self.choice[1],
                'expected_view_generation': self.host.document['view_generation']}, accepted=self.received)
            if accepted is False and self.host._pending is None:
                self.pending_basis = None
        except Exception:
            # The host retains the durable command ID. Do not blindly replay it.
            raise

    def received(self, payload):
        basis, self.pending_basis = self.pending_basis, None
        if basis is None or not self.current(basis): return
        if (payload.get('status') != 'ORIGINALS_READ' or payload.get('preview') is not False
                or (payload.get('object_ref'), payload.get('revision'), payload.get('table'), payload.get('row_index'))
                    != (basis[0]['object_ref'], basis[0]['revision'], basis[-1][0], basis[-1][1])):
            self.host.message.setText('선택과 다른 원행 응답입니다. 원자료를 열지 않았습니다.'); return
        dialog = OriginDialog(self, basis, payload)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dialog.show()


def attach_origin_controls(plot, host):
    plot.origin_controls = OriginControls(plot, host)
    return plot.origin_controls


class OriginDialog(QDialog):
    def __init__(self, controls, basis, payload):
        super().__init__(controls.plot)
        self.controls, self.basis, self.payload = controls, basis, deepcopy(payload)
        self.closed, self.worker, self.phase, self.operation = False, None, None, None
        self.data_payload = None
        self.setWindowTitle('원자료 열기'); self.resize(880, 590)
        layout = QVBoxLayout(self)
        intro = QLabel('실제 저장 원행을 선택하세요. 보간 B는 양쪽 원행을 각각 엽니다.\n'
                       '원축 값과 공통 정렬값은 서로 다르며, 표시 제외와 계산 제외도 별개입니다.')
        intro.setWordWrap(True); layout.addWidget(intro)
        self.targets = QComboBox(); self.targets.setObjectName('originalBracketChoice')
        summary = getattr(controls.plot, 'payload', {}).get('summary', {})
        common_axis = summary.get('sources', {}).get('a', {}).get('axis', {}).get('unit')
        common_unit = summary.get('recipe', {}).get('target_unit')
        for i, target in enumerate(payload['targets']):
            side = target['side'].upper(); raw = target['raw']
            suffix = ' / 보간 구간 원행' if side == 'B' and len((target.get('correspondence') or {}).get('b_rows', [])) == 2 else ''
            self.targets.addItem(f'{side} {target["title"]}: 원축 {with_unit(raw["raw_x"], target["axis"].get("unit"))}'
                                 f' / 원값 {with_unit(raw["raw_y"], target["declaration"].get("units"))}{suffix}', i)
        layout.addWidget(self.targets)
        rows = []
        for target in payload['targets']:
            raw = target['raw']; identity = raw['identity']
            row_kind = {'physical_line':'CSV', 'array_index':'배열', 'retained_row':'저장행'}.get(
                identity.get('kind'), 'native(0)' if 'block' in identity else '원행')
            rows.append({'side': target['side'].upper(), 'source_row': f'{row_kind} {identity.get("row")}',
                'axis': with_unit(raw['raw_x'], target['axis'].get('unit')),
                'value': with_unit(raw['raw_y'], target['declaration'].get('units')),
                'common_x': with_unit(target['common_x'], common_axis),
                'common_y': with_unit(target['common_y'], common_unit), 'quality': raw['quality'],
                'calculation': '포함' if raw['calculation'] else '제외',
                'visible': '표시' if raw['visible'] else '숨김',
                'reason': raw['quality_reason'] or raw['exclusion_reason']})
        self.raw_table = table(self, [('side','원곡선'),('source_row','원행'),
            ('axis','원축'),('value','원값'),('common_x','정렬축'),('common_y','공통값'),
            ('quality','품질'),('calculation','계산'),('visible','표시'),('reason','사유')], rows)
        layout.addWidget(self.raw_table, 1)
        correspondence = payload['targets'][0].get('correspondence')
        if correspondence is not None:
            layout.addWidget(table(self, [('x',f'공통 정렬축 [{unit_label(common_axis)}]'),
                ('a',f'정렬 A [{unit_label(common_unit)}]'),('b',f'정렬 B [{unit_label(common_unit)}]'),
                ('delta',f'B − A [{unit_label(common_unit)}]'),('valid','비교 유효'),('reason','비교 사유'),
                ('b_axis',f'B 정렬축 구간 [{unit_label(common_axis)}]'),
                ('weight','보간 가중치')], [correspondence]))
        self.message = QLabel('원자료를 읽고 검증한 뒤 해당 성분·축·원행을 선택합니다.')
        self.message.setWordWrap(True); layout.addWidget(self.message)
        actions = QGridLayout()
        self.open_button = QPushButton('원자료 열기'); self.retry = QPushButton('같은 요청 상태 확인')
        self.open_button.setProperty('appearanceRole', 'primary')
        self.project = QPushButton('정확한 저장본 선택…'); self.lineage = QPushButton('시험의 원 측정 열기')
        self.details = QPushButton('기술 상세…')
        for i, button in enumerate((self.open_button, self.retry, self.project, self.lineage, self.details)):
            actions.addWidget(button, i//2, i%2)
        layout.addLayout(actions)
        self.retry.setEnabled(False); self.project.hide(); self.lineage.hide()
        self.open_button.clicked.connect(self.open_original); self.retry.clicked.connect(self.retry_phase)
        self.project.clicked.connect(self.choose_project); self.lineage.clicked.connect(self.open_lineage)
        self.details.clicked.connect(self.show_details)
        self.targets.currentIndexChanged.connect(self.choose)
        self.finished.connect(self.abandon)
        self.choose()

    def valid(self):
        return not self.closed and self.controls.current(self.basis)

    @Slot(int)
    def abandon(self, *_):
        self.closed = True
        if self.operation is not None: self.operation.invalidate()
        if self.worker is not None: self.worker.abandon()

    @Slot()
    def choose(self, *_):
        if self.operation is not None: self.operation.invalidate()
        self.operation = None; self.data_payload = None; self.phase = None
        self.project.hide(); self.lineage.hide(); self.retry.setEnabled(False)
        self.raw_table.selectRow(self.targets.currentIndex())
        target = self.target()
        self.open_button.setText('원 시험 자료 열기' if target['kind'] == 'data_curve' else '원 측정 열기')

    def target(self):
        return deepcopy(self.payload['targets'][self.targets.currentIndex()])

    @Slot()
    def open_original(self):
        if not self.valid() or self.worker is not None: return
        target = self.target()
        if target['kind'] == 'data_curve': self.start('data', lambda: read_data(self.controls.host.client, target))
        else:
            try: self.operation = NativeReturn(self.controls.host.client, target)
            except Exception as error: self.message.setText(str(error)); return
            self.start('verify', self.operation.verify)

    def start(self, phase, function):
        if not self.valid() or self.worker is not None: return
        self.phase = phase; self.targets.setEnabled(False); self.open_button.setEnabled(False)
        self.retry.setEnabled(False); self.project.setEnabled(False); self.lineage.setEnabled(False)
        self.worker = _Call(function)
        self.worker.signals.finished.connect(self.completed, Qt.ConnectionType.QueuedConnection)
        QThreadPool.globalInstance().start(self.worker)

    @Slot(object, object)
    def completed(self, result, error):
        self.worker = None
        if not self.valid():
            if self.operation is not None: self.operation.invalidate()
            return  # NO follow-on select, activate or launch on a stale callback.
        self.project.setEnabled(True); self.lineage.setEnabled(True)
        if error:
            self.message.setText(str(error)+'\n원곡선과 편집을 보존했습니다. 응답 유실은 같은 요청 상태만 확인하세요. 확정 실패는 원파일 복원 후 이 창을 닫고 비교 원행을 다시 읽으세요.')
            self.retry.setEnabled(True)
            return  # Keep choice frozen while a sent mutation may be unresolved.
        if self.phase == 'data':
            self.data_payload = result; self.show_data(result)
            self.lineage.setVisible(result.get('lineage_status') == 'AVAILABLE')
            self.message.setText('원 시험 응답과 원행을 확인했습니다. '+str(result.get('lineage_error') or ''))
            self.targets.setEnabled(True); self.open_button.setEnabled(True)
        elif self.phase == 'verify':
            if result.get('status') == 'CLOSED':
                self.message.setText('원창이 닫혔습니다. 정확한 저장 프로젝트를 명시적으로 선택하세요.')
                self.project.show(); return
            self.message.setText('원행·성분·축 검증 확인. 해당 원행을 선택합니다.')
            self.start('select', self.operation.select)
        elif self.phase == 'select':
            self.message.setText('원행 선택을 확인했습니다. 창 활성화는 별도로 확인합니다.')
            self.start('activate', self.operation.activate)
        elif self.phase == 'activate':
            self.message.setText('원행 선택 및 원창 활성화 확인.' if result.get('status') == 'ACTIVATED'
                                 else '원행 선택 확인. '+str(result.get('message', '창 활성화 미확인.')))
            self.targets.setEnabled(True); self.open_button.setEnabled(True)
        elif self.phase == 'launch':
            self.message.setText('원창 열기를 요청했습니다. 새 owner 등록 상태를 확인하세요. 아직 원행 선택 완료가 아닙니다.')
            self.phase = 'poll_launch'; self.retry.setEnabled(True)
        elif self.phase == 'poll_launch':
            self.message.setText('새 owner 확인. 원행을 다시 검증합니다.' if result['status'] == 'OWNER_AVAILABLE'
                                 else '원창 등록 미확인. 새 창을 중복 실행하지 않습니다.')
            if result['status'] == 'OWNER_AVAILABLE': self.start('verify', self.operation.verify)
            else: self.retry.setEnabled(True)

    @Slot()
    def retry_phase(self):
        if not self.valid() or self.worker is not None: return
        if self.phase == 'data': self.start('data', lambda: read_data(self.controls.host.client, self.target()))
        elif self.phase == 'launch':
            self.start('poll_launch', self.operation.poll_launch)  # Never re-spawn after a lost launch reply.
        elif self.operation is not None and self.phase in ('verify','select','activate','poll_launch'):
            self.start(self.phase, getattr(self.operation, self.phase))

    @Slot()
    def choose_project(self):
        if not self.valid() or self.worker is not None or self.operation is None: return
        path, _ = QFileDialog.getOpenFileName(self, '원 측정의 정확한 저장 프로젝트',
            self.operation.origin['project']['path'], '저장 Post 프로젝트 (*.json)')
        if not path or not self.valid(): return  # Explicit cancellation performs no I/O/launch.
        self.start('launch', lambda: self.operation.launch(path))

    @Slot()
    def open_lineage(self):
        if not self.valid() or not self.data_payload or self.worker is not None: return
        try: self.operation = NativeReturn(self.controls.host.client, self.data_payload['native_target'])
        except Exception as error: self.message.setText(str(error)); return
        self.start('verify', self.operation.verify)

    def show_data(self, payload):
        dialog = QDialog(self); dialog.setWindowTitle('원 시험 자료'); dialog.resize(900, 660)
        layout = QVBoxLayout(dialog); content = ReferenceContent(dialog)
        name = self.target()['origin']['response']
        content.set_payload({'status':'AVAILABLE', 'kind':'result',
            'result': {'responses': {name: payload['response']}}}, label='원 시험 채널: '+name)
        layout.addWidget(content, 2)
        rows = [{**r, 'source_row': r['identity'].get('row'), 'calculation': '포함' if r['calculation'] else '제외',
                 'visible': '표시' if r['visible'] else '숨김'} for r in payload['curve']['rows']]
        raw = table(dialog, [('source_row','원 CSV 줄'),
            ('raw_x',f'원축 [{unit_label(payload["curve"]["axis"].get("unit"))}]'),
            ('raw_y',f'원값 [{unit_label(payload["curve"]["declaration"].get("units"))}]'),
            ('quality','품질'),('calculation','계산'),('visible','표시'),('quality_reason','품질 사유'),
            ('exclusion_reason','제외 사유')], rows)
        note = QLabel('곡선 원값은 저장 비교가 사용한 값입니다. 보정이 있으면 변환 후 값이며, 취득값이 따로 보존된 경우 아래에 표시합니다.')
        note.setWordWrap(True); layout.addWidget(note)
        layout.addWidget(raw, 1); raw.selectRow(payload['source_index'])
        raw.scrollToItem(raw.item(payload['source_index'], 0))
        acquisition_rows = payload['acquisition_rows']
        if acquisition_rows:
            input_unit = (payload['response'].get('calibration') or {}).get('input_unit')
            acquisition = table(dialog, [('source_row','원 CSV 줄'),('axis','취득 원축 [단위 미상]'),
                ('value',f'취득 원값 [{unit_label(input_unit)}]')], acquisition_rows)
            layout.addWidget(acquisition, 1)
            selected = next((i for i,r in enumerate(acquisition_rows) if r['source_row'] == self.target()['raw']['identity']['row']), None)
            if selected is not None:
                acquisition.selectRow(selected); acquisition.scrollToItem(acquisition.item(selected, 0))
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose); dialog.show()

    @Slot()
    def show_details(self):
        dialog = QDialog(self); dialog.setWindowTitle('원자료 기술 상세'); dialog.resize(750, 520)
        layout = QVBoxLayout(dialog); output = QPlainTextEdit(); output.setReadOnly(True)
        output.setPlainText(json.dumps({'read':self.payload, 'selected':self.target(),
            'verification':getattr(self.operation,'verification',None),
            'selection':getattr(self.operation,'selection',None),
            'activation':getattr(self.operation,'activation',None)}, ensure_ascii=False, indent=2))
        layout.addWidget(output); dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose); dialog.show()
