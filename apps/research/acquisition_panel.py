"""Recorded acquisition beside the existing Data worksheet, using the same owner."""
from collections import deque
from copy import deepcopy
import json
from pathlib import Path
import uuid

from PySide6.QtCore import Qt, QThreadPool, QTimer
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QComboBox, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QFileDialog, QSpinBox, QCheckBox, QPlainTextEdit)

from .data_window import _Read
from .experiment_dialogs import AcquisitionDialog

LABELS = {'CONNECTED': '준비', 'RUNNING': '재생 중', 'PAUSE_REQUESTED': '일시정지 응답 대기',
    'PAUSED': '일시정지 확인', 'STOP_REQUESTED': '중지 응답 대기', 'STOPPED': '재생 종료',
    'FAILED': '실패', 'DISCONNECTED': '연결 끊김', 'INTERRUPTED': '이전 작업 종료'}
EVENTS = {'SAMPLE': '표본', 'GAP': '누락 감지', 'CLOCK_RESET': '시계 재설정',
    'SEQUENCE_CONFLICT': '같은 순번 원문 충돌', 'MALFORMED': '읽을 수 없는 행',
    'OVERFLOW': '버퍼 초과', 'STOP_REQUESTED': '중지 요청', 'PAUSE_REQUESTED': '일시정지 요청',
    'STOP_RECEIPT': '재생 종료 확인', 'PAUSE_RECEIPT': '일시정지 확인', 'RESUME': '명시 재개',
    'STOP_UNCONFIRMED': '중지 응답 없음', 'CONNECTED': '기록 연결', 'RUNNING': '재생 시작'}
QUALITY = {'OUT_OF_ORDER': '늦은 순번', 'CLOCK_RESET': '시계 재설정', 'GAP_BEFORE': '앞 구간 누락',
    'CLOCK_SEGMENT_UNKNOWN': '시간 구간 미확인',
    'LATE_AFTER_STOP_REQUESTED': '중지 요청 뒤 도착', 'LATE_AFTER_PAUSE_REQUESTED': '일시정지 요청 뒤 도착'}


def _command():
    return 'C' + uuid.uuid4().hex


class AcquisitionPanel(QMainWindow):
    def __init__(self, host):
        super().__init__(host)
        self.host, self.client = host, host.client
        self.document = deepcopy(host.document)
        self._binding = (self.document['id'], self.document['session_id'])
        self.run_id = None
        self._busy = self._closed = False
        self._workers = []
        self._after = 0
        self._head = None
        self._more_events = False
        self._raw_serial = 0
        self._raw_pending = False
        self._events = deque(maxlen=500)
        self.setWindowTitle('기록 취득')
        self.resize(1040, 740)
        self.setMinimumSize(620, 480)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        file_menu = self.menuBar().addMenu('파일(&F)')
        self.open_action = QAction('기록 CSV 열기…', self)
        self.open_action.setShortcut(QKeySequence.StandardKey.Open)
        self.open_action.triggered.connect(self.open_replay)
        file_menu.addAction(self.open_action)
        self.save_action = QAction('Data 문서 저장', self)
        self.save_action.setShortcut(QKeySequence.StandardKey.Save)
        self.save_action.triggered.connect(self.save)
        file_menu.addAction(self.save_action)
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(10)
        title = QLabel('기록 취득')
        title.setProperty('appearanceRole', 'title')
        layout.addWidget(title)
        row = QHBoxLayout()
        self.runs = QComboBox()
        self.runs.setMinimumWidth(180)
        self.runs.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.runs.setAccessibleName('저장된 취득 기록')
        self.runs.activated.connect(self.select_run)
        row.addWidget(self.runs, 1)
        self.open_button = QPushButton('CSV 열기…')
        self.open_button.setProperty('appearanceRole', 'primary')
        self.open_button.clicked.connect(self.open_replay)
        row.addWidget(self.open_button)
        self.plan_button = QPushButton('취득 계획…')
        self.plan_button.clicked.connect(self.edit_plan)
        row.addWidget(self.plan_button)
        layout.addLayout(row)
        self.plan = QLabel()
        self.plan.setWordWrap(True)
        self.plan.setProperty('appearanceRole', 'muted')
        layout.addWidget(self.plan)
        controls = QHBoxLayout()
        self.start_button = QPushButton('재생 시작')
        self.pause_button = QPushButton('일시정지 요청')
        self.stop_button = QPushButton('중지 요청')
        self.start_button.clicked.connect(self.start)
        self.pause_button.clicked.connect(lambda: self.request('pause'))
        self.stop_button.clicked.connect(lambda: self.request('stop'))
        for button in (self.start_button, self.pause_button, self.stop_button):
            controls.addWidget(button)
        controls.addStretch()
        layout.addLayout(controls)
        self.status = QLabel('기록 CSV를 열거나 저장한 취득을 선택하세요.')
        self.status.setWordWrap(True)
        self.status.setProperty('appearanceRole', 'section')
        layout.addWidget(self.status)
        self.physical = QLabel('기록 파일 재생')
        self.physical.setToolTip('파일 재생 종료이며 장비 중지 응답이 아닙니다. 장비의 물리 중지는 확인하지 않았습니다.')
        self.physical.setWordWrap(True)
        self.physical.setProperty('appearanceRole', 'muted')
        layout.addWidget(self.physical)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(['기록', '순번', '시각 [s]', '채널 원값', '품질 / 상태'])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setStretchLastSection(True)
        for i, width in enumerate((125, 70, 100, 210)):
            self.table.setColumnWidth(i, width)
        self.table.setAccessibleName('취득 표본과 오류 기록')
        self.table.itemSelectionChanged.connect(self._raw_selection_changed)
        layout.addWidget(self.table, 1)
        review = QHBoxLayout()
        review.addWidget(QLabel('시간 구간'))
        self.segment = QSpinBox()
        self.segment.setRange(-1, 0)
        self.segment.setSpecialValueText('미확인')
        self.segment.setValue(0)
        self.segment.setAccessibleName('Data로 검토할 시간 구간')
        review.addWidget(self.segment)
        review.addWidget(QLabel('첫 표본'))
        self.first = QSpinBox()
        self.first.setRange(0, 1000000000)
        self.first.setAccessibleName('구간 내 부분검토 시작 표본, 0부터')
        review.addWidget(self.first)
        review.addStretch()
        self.partial_button = QPushButton('Data에서 검토')
        self.partial_button.clicked.connect(self.materialize)
        review.addWidget(self.partial_button)
        layout.addLayout(review)
        options = QHBoxLayout()
        self.exclude = QCheckBox('비수치 표본 계산 제외')
        self.exclude.setToolTip('원 표본은 보존하며 선택한 구간의 비수치 행만 계산에서 제외합니다.')
        options.addWidget(self.exclude)
        options.addWidget(QLabel('한 번에 최대 512개 표본'))
        options.addStretch()
        layout.addLayout(options)
        self.details_button = QPushButton('선택 원문 / 진단')
        self.details_button.setCheckable(True)
        self.details_button.toggled.connect(self.show_raw)
        layout.addWidget(self.details_button, alignment=Qt.AlignmentFlag.AlignLeft)
        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setMaximumHeight(130)
        self.details.hide()
        layout.addWidget(self.details)
        self.message = QLabel('원파일 순서와 원문을 보존합니다. 화면은 최근 500개 기록입니다.')
        self.message.setWordWrap(True)
        layout.addWidget(self.message)
        self.timer = QTimer(self)
        self.timer.setInterval(350)
        self.timer.timeout.connect(self.poll)
        self.timer.start()
        self._state = None
        self._update_controls()
        self.reload_runs()

    def _binding_current(self):
        document = self.host.document or {}
        return (document.get('id'), document.get('session_id')) == self._binding

    def _identity(self):
        if not self._binding_current():
            raise ValueError('현재 Data 문서에서 기록 취득을 다시 여세요.')
        if not self.host.local_dirty and not self.host.conflict:
            self.document = deepcopy(self.host.document)
        return {'document_id': self.document['id'], 'session_id': self.document['session_id'],
            'expected_generation': self.document['generation']}

    def _call(self, function, accepted):
        if not self._binding_current():
            self.close()
            return False
        if self._busy or self._closed:
            return False
        self._busy = True
        self._update_controls()
        worker = _Read(function)
        self._workers.append(worker)
        def completed(value, error):
            if self._closed:
                return
            if not self._binding_current():
                self.close()
                return
            self._workers.remove(worker)
            self._busy = False
            if error:
                self.message.setText('작업을 완료하지 못했습니다: ' + error + ' 이전 기록은 보존됩니다.')
            else:
                accepted(value)
            self._update_controls()
            if self._raw_pending:
                self._raw_pending = False
                QTimer.singleShot(0, self._raw_selection_changed)
        worker.signals.finished.connect(completed)
        QThreadPool.globalInstance().start(worker)
        return True

    def _action(self, name, arguments, accepted):
        return self._call(lambda: self.client.data_material('acquisition.' + name, arguments), accepted)

    def reload_runs(self):
        def filled(value):
            self.runs.clear()
            for row in value['runs']:
                self.runs.addItem((row['name'] or '이름 없는 취득') + ' — ' + LABELS.get(row['state'], row['state']), row['run_id'])
            if self.runs.count():
                self.select_run(0)
        self._action('list', {'document_id': self.document['id']}, filled)

    def select_run(self, index):
        self.run_id = self.runs.itemData(index)
        self._state = self._head = None
        self._more_events = False
        self._after = 0
        self._events.clear()
        self.table.setRowCount(0)
        self._raw_selection_changed()
        self._update_controls()
        self.refresh()

    def refresh(self):
        if self.run_id:
            self._action('read', {'document_id': self.document['id'], 'run_id': self.run_id,
                'after': self._after, 'count': 100}, self._received)

    def poll(self):
        if not self._binding_current():
            self.close()
            return
        if not self.run_id:
            return
        if self._more_events:
            self.refresh()
            return
        def changed(value):
            if value != self._head:
                self.refresh()
        self._action('head', {'document_id': self.document['id'], 'run_id': self.run_id,
            'job_id': (self._state or {}).get('job_id')}, changed)

    def _received(self, value):
        if not self._binding_current():
            self.close()
            return
        if self.run_id != value['run_id']:
            return  # A delayed response cannot replace the newly selected run.
        self._more_events = len(value['events']) == 100
        self._state = state = value['state']
        self._head = {'head': {'revision': state.get('ledger_revision', 0),
            'acknowledged_cursor': state['source_cursor'], 'samples': state['samples']},
            'job_state': value.get('job_state')}
        index = self.runs.findData(self.run_id)
        name = (state['plan']['name'] or state['source']['name']) + ' — ' + LABELS.get(state['state'], state['state'])
        if index < 0:
            self.runs.addItem(name, self.run_id)
            index = self.runs.count() - 1
        self.runs.setItemText(index, name)
        self.runs.setCurrentIndex(index)
        self.plan.setText(f"{state['source']['name']}  |  {state['plan']['sample_rate_hz']:g} Hz, {state['plan']['duration_s']:g} s 요청  |  {state['plan']['clock']}")
        self.status.setText(f"{LABELS.get(state['state'], state['state'])}  |  표본 {state['samples']}  동일 중복 {state['duplicates']}  충돌 {state['conflicts']}  읽기 오류 {state['malformed']}")
        receipt = state.get('stop_receipt')
        self.physical.setText('기록 파일 재생' +
            ('  |  파일 끝 도달' if receipt and receipt['scope'] == 'REPLAY_EOF' else
             '  |  요청 기간 도달' if receipt and receipt['scope'] == 'REPLAY_DURATION' else '  |  재생 중지 확인' if receipt else ''))
        if state.get('failure'):
            self.message.setText(state['failure']['message'])
        elif state.get('interruption'):
            self.message.setText(state['interruption'])
        self.segment.setMaximum(state['segment'])
        raw_units = {c['name']: (c['calibration']['input_unit'] if c['calibration'] else c['unit'])
                     for c in state['plan']['channels']}
        for event in value['events']:
            if event['id'] <= self._after:
                continue
            self._after = max(self._after, event['id'])
            self._events.append(event)
            if self.table.rowCount() >= 500:
                self.table.removeRow(0)
            row = self.table.rowCount()
            self.table.insertRow(row)
            values = [EVENTS.get(event['kind'], event['kind']), event.get('sequence', ''), event.get('timestamp', ''),
                ', '.join(f'{k}: {v} {raw_units.get(k, "")}' for k, v in event.get('values', {}).items()),
                '; '.join(QUALITY.get(q, q.replace(':NONFINITE', ': 비유한값').replace(':NONNUMERIC', ': 비수치'))
                    for q in event.get('quality', [])) or event.get('error', '')]
            for col, text in enumerate(values):
                item = QTableWidgetItem('' if text is None else str(text))
                item.setData(Qt.ItemDataRole.UserRole, event['id'])
                self.table.setItem(row, col, item)
        self._update_controls()

    def _update_controls(self):
        state = (self._state or {}).get('state')
        available = not self._busy and not self._closed and self._binding_current()
        self.start_button.setText('재생 시작' if state == 'CONNECTED' else '명시적으로 재개')
        self.start_button.setEnabled(available and state in {'CONNECTED', 'PAUSED', 'STOPPED', 'FAILED', 'DISCONNECTED', 'INTERRUPTED'})
        self.pause_button.setEnabled(available and state == 'RUNNING')
        self.stop_button.setEnabled(available and state in {'RUNNING', 'PAUSED', 'PAUSE_REQUESTED'})
        self.partial_button.setEnabled(available and bool((self._state or {}).get('samples')))
        self.open_button.setEnabled(available)
        self.plan_button.setEnabled(available)
        self.save_action.setEnabled(available)

    def _editable(self):
        if not self._binding_current():
            self.close()
            return False
        if self.host.local_dirty or self.host.conflict:
            self.message.setText('Data 창의 편집을 먼저 적용하거나 보존하세요.')
            return False
        return True

    def open_replay(self):
        if not self._editable():
            return
        path, _ = QFileDialog.getOpenFileName(self, '기록 CSV 열기', '', '기록 CSV (*.csv)')
        if path:
            self.load_replay(path)

    def load_replay(self, path):
        if not self._editable():
            return False
        identity, command = self._identity(), _command()
        def load():
            source = Path(path)
            if source.stat().st_size > 16 * 1024 * 1024:
                raise ValueError('기존 업로드 경로는 16 MiB 이하 파일을 지원합니다.')
            receipt = self.client.upload(source.name, source.read_bytes())
            return self.client.data_material('acquisition.create', {**identity,
                'source_id': receipt.get('data_id', receipt.get('id')), 'command_id': command})
        def selected(value):
            self.run_id = value['run_id']
            self._head = None
            self._after = 0
            self._events.clear()
            self.table.setRowCount(0)
            self._raw_selection_changed()
            self._received(value)
        return self._call(load, selected)

    def start(self):
        if not self._editable():
            return False
        return self._action('start', {**self._identity(), 'run_id': self.run_id,
            'command_id': _command(), 'resume': self._state['state'] != 'CONNECTED'}, self._received)

    def request(self, action):
        if not self._editable():
            return False
        return self._action('request', {**self._identity(), 'run_id': self.run_id,
            'action': action, 'command_id': _command()}, self._received)

    def _updated(self, value):
        document = value['document']
        if (not self._binding_current()
                or (document.get('id'), document.get('session_id')) != self._binding):
            self.close()
            return False
        self.document = value['document']
        if not self.host.local_dirty and not self.host.conflict:
            self.host._opened(self.document)
        return True

    def edit_plan(self):
        if not self._editable():
            return
        identity = self._identity()
        draft = deepcopy(self.document['draft'])
        dialog = AcquisitionDialog(draft.get('acquisition'),
            draft['mapping']['columns'], self)
        dialog.reuse.hide()  # Frozen run plans connect calibration on Data materialization.
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        draft['acquisition'] = dialog.edited()
        self._call(lambda: self.client.document_command(identity.pop('document_id'), 'data.update',
            {'draft': draft}, **identity, command_id=_command()), self._updated)

    def materialize(self):
        if not self._editable():
            return
        def accepted(value):
            if not self._updated(value):
                return
            self.message.setText('선택 구간을 Data에 적용했습니다. 원행·단위와 교정을 확인하고 가져오세요. 시각 역전은 행 선택이 필요합니다.')
            self.host.show()
            self.host.raise_()
        self._action('materialize', {**self._identity(), 'run_id': self.run_id,
            'segment': self.segment.value(), 'exclude_invalid': self.exclude.isChecked(),
            'start': self.first.value(),
            'command_id': _command()}, accepted)

    def save(self):
        if not self._editable():
            return
        identity = self._identity()
        def accepted(value):
            if not self._updated(value):
                return
            self.message.setText('데이터와 취득 원문을 함께 저장했습니다.')
        self._call(lambda: self.client.document_command(identity.pop('document_id'), 'document.save', {},
            **identity, command_id=_command()), accepted)

    def show_raw(self, checked):
        self.details.setVisible(checked)
        self._raw_selection_changed()

    def _raw_selection_changed(self):
        self._raw_serial += 1
        self.details.clear()
        if not self.details_button.isChecked():
            self._raw_pending = False
            return
        row = self.table.currentRow()
        if row < 0 or self.table.item(row, 0) is None:
            return
        event = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        run, serial = self.run_id, self._raw_serial
        def accepted(value):
            row = self.table.currentRow()
            item = self.table.item(row, 0) if row >= 0 else None
            if (self.details_button.isChecked() and serial == self._raw_serial and run == self.run_id
                    and value['run_id'] == run and item is not None
                    and item.data(Qt.ItemDataRole.UserRole) == event
                    and value['events'] and value['events'][0]['id'] == event):
                self.details.setPlainText(json.dumps(value['events'], ensure_ascii=False, indent=2))
        if self._busy:
            self._raw_pending = True
            return
        self._action('read', {'document_id': self.document['id'], 'run_id': self.run_id,
            'after': event - 1, 'count': 1, 'raw': True}, accepted)

    def closeEvent(self, event):
        self._closed = True
        self.timer.stop()
        for worker in self._workers:
            worker.abandon()
        super().closeEvent(event)


def show_acquisition(host):
    if not host.document or host._busy or host.local_dirty or host.conflict:
        host.message.setText('Data 문서의 편집을 먼저 적용하고 기록 취득을 여세요.')
        return False
    window = AcquisitionPanel(host)
    host._acquisition_windows = getattr(host, '_acquisition_windows', []) + [window]
    window.show()
    return window
