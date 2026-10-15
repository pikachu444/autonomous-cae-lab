"""Runner's explicit remote batch actions using the existing service and jobs."""
from copy import deepcopy
import json
import uuid

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Qt, Signal, QSettings
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDialog, QDialogButtonBox,
    QFormLayout, QGroupBox, QHBoxLayout, QHeaderView, QLabel, QPushButton,
    QSpinBox, QTableWidget, QTableWidgetItem, QVBoxLayout)
from caelab.workbench_client import WorkbenchHTTPError


STATES = {'PREPARING':'입력 준비', 'PREPARED':'입력 전송됨', 'SUBMITTING':'제출 확인 중',
    'SUBMITTED':'제출됨', 'QUEUED':'대기', 'RUNNING':'실행 중', 'COMPLETED':'원격 계산 종료',
    'SUCCEEDED':'작업 완료', 'FAILED':'실패', 'CANCELLED':'취소 확인', 'TIMEOUT':'시간 초과',
    'UNKNOWN':'종료 미확인', 'CONNECTION_OR_RESULT_ERROR':'연결 또는 결과 확인 필요',
    'MONITORING_PAUSED':'추적 일시 중지', 'RECOVERED':'결과 회수됨',
    'CANCEL_REQUESTED':'취소 요청됨', 'TERMINATION_UNCONFIRMED':'종료 미확인',
    'CLEANUP_PENDING':'종료 미확인', 'INTERRUPTED':'재접속 필요'}


def _settings():
    return QSettings('AutonomousCAELab','DesktopLaunchers')


class _Signals(QObject):
    done = Signal(object, object)


class _Request(QRunnable):
    def __init__(self, function):
        super().__init__(); self.function = function; self.signals = _Signals()

    def run(self):
        try: self.signals.done.emit(self.function(), None)
        except Exception as error: self.signals.done.emit(None, error)


class RemoteExecutionDialog(QDialog):
    job_ready = Signal(str)

    def __init__(self, client, parent=None, *, selected_job=None, auto_load=True):
        super().__init__(parent)
        self.client = client; self.selected_job = selected_job
        self._busy = False; self._pending = None; self._workers = []
        self._hosts = {}; self._attempts = {}; self._close_when_idle = False
        self._store_key = None
        self._pending_uncertain = False
        self.setWindowTitle('원격 실행'); self.resize(1000, 720); self.setMinimumSize(660, 560)
        layout = QVBoxLayout(self)
        group = QGroupBox('실행할 입력과 자원'); form = QFormLayout(group)
        self.host = QComboBox(); self.batch = QComboBox()
        self.host.currentIndexChanged.connect(self._host_changed)
        form.addRow('실행 위치', self.host); form.addRow('입력 묶음', self.batch)
        self.runtime = QLabel('등록한 실행 위치를 선택하세요.'); self.runtime.setWordWrap(True)
        form.addRow('솔버와 대기열', self.runtime)
        resources = QHBoxLayout()
        self.threads = QSpinBox(); self.threads.setRange(1, 1); self.threads.setSuffix(' 스레드')
        self.memory = QSpinBox(); self.memory.setRange(1, 1024); self.memory.setValue(1024); self.memory.setSuffix(' MiB')
        self.wall = QSpinBox(); self.wall.setRange(1, 3600); self.wall.setValue(3600); self.wall.setSuffix(' 초')
        for widget in (self.threads, self.memory, self.wall): resources.addWidget(widget)
        form.addRow('자원 요청', resources)
        actions = QHBoxLayout()
        self.preview_button = QPushButton('입력 확인'); self.preview_button.clicked.connect(self.preview)
        self.submit_button = QPushButton('원격 제출'); self.submit_button.clicked.connect(self.submit)
        self.submit_button.setProperty('appearanceRole','primary')
        actions.addWidget(self.preview_button); actions.addStretch(); actions.addWidget(self.submit_button)
        form.addRow(actions); layout.addWidget(group)
        self.message = QLabel('기존 연결과 작업 기록을 읽고 있습니다…'); self.message.setWordWrap(True)
        self.message.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.message)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(['작업', '실행 위치', '상태', '스케줄러 작업', '갱신 시간'])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column, width in ((1,130),(2,160),(3,125),(4,165)): self.table.setColumnWidth(column,width)
        self.table.verticalHeader().hide(); self.table.itemSelectionChanged.connect(self._selected)
        layout.addWidget(self.table, 1)
        row = QHBoxLayout()
        self.refresh_button = QPushButton('목록 새로 고침'); self.refresh_button.clicked.connect(self.refresh)
        self.reconnect_button = QPushButton('상태 확인'); self.reconnect_button.clicked.connect(lambda:self.action('reconnect'))
        self.cancel_button = QPushButton('원격 취소'); self.cancel_button.clicked.connect(lambda:self.action('cancel'))
        self.collect_button = QPushButton('결과 회수'); self.collect_button.clicked.connect(lambda:self.action('collect'))
        self.result_button = QPushButton('Runner에서 보기'); self.result_button.clicked.connect(self.open_result)
        for button in (self.refresh_button,self.reconnect_button,self.cancel_button,self.collect_button,self.result_button): row.addWidget(button)
        layout.addLayout(row)
        self.detail = QLabel('상태 확인은 같은 작업을 조회합니다. 종료 확인 후 결과를 회수하세요.')
        self.detail.setWordWrap(True); layout.addWidget(self.detail)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close); buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.StandardButton.Close).setText('닫기')
        layout.addWidget(buttons); self._controls()
        if auto_load: self.refresh()

    def _controls(self):
        editable = not self._busy and self._pending is None
        for widget in (self.host,self.batch,self.threads,self.memory,self.wall,self.preview_button): widget.setEnabled(editable)
        self.preview_button.setEnabled(editable and bool(self.host.currentData() and self.batch.currentData()))
        self.submit_button.setEnabled(not self._busy and (self._pending is not None or bool(self.host.currentData() and self.batch.currentData())))
        self.submit_button.setText('요청 응답 다시 확인' if self._pending else '원격 제출')
        self.refresh_button.setEnabled(not self._busy)
        for button in (self.reconnect_button,self.cancel_button,self.collect_button,self.result_button):
            button.setEnabled(not self._busy and self._pending is None and bool(self.selected_job))

    def _request(self, function, accepted, failed=None):
        if self._busy: return
        self._busy = True; self._controls()
        worker = _Request(function); self._workers.append(worker)
        def done(value, error):
            self._workers.remove(worker); self._busy = False
            if error:
                if failed: failed(error)
                else: self.message.setText(str(error))
            else: accepted(value)
            self._controls()
            if self._close_when_idle: self.reject()
        worker.signals.done.connect(done); QThreadPool.globalInstance().start(worker)

    def _api(self, operation, arguments=None):
        return self.client.request('/api/workbench/remote', {'operation':operation,'arguments':arguments or {}})

    def refresh(self):
        self._request(lambda:self._api('catalog'), self._catalog)

    def _catalog(self, catalog):
        previous_host, previous_batch = self.host.currentData(), self.batch.currentData()
        self._hosts = {row['id']:row for row in catalog['hosts'] if not row.get('error')}
        self.host.blockSignals(True); self.host.clear(); self.batch.clear()
        for identifier,row in self._hosts.items(): self.host.addItem(row['label'],identifier)
        for row in catalog['batches']: self.batch.addItem(row['label'],row['id'])
        for combo,value in ((self.host,previous_host),(self.batch,previous_batch)):
            index = combo.findData(value)
            if index >= 0: combo.setCurrentIndex(index)
        self.host.blockSignals(False); self._host_changed()
        self._store_key = catalog['store_key']
        self._restore_pending()
        self._attempts = {row['id']:row for row in catalog['attempts']}
        self.table.blockSignals(True); self.table.setRowCount(len(self._attempts))
        for index,row in enumerate(self._attempts.values()):
            host = self._hosts.get(row.get('host_id'),{})
            values = [row['label'],host.get('label','기존 실행 위치'),STATES.get(row['state'],'확인 필요'),
                      row.get('scheduler_id') or '확인 전',row.get('updated_utc','').replace('T',' ')[:19]]
            for column,value in enumerate(values):
                item = QTableWidgetItem(str(value)); self.table.setItem(index,column,item)
            self.table.item(index,0).setData(Qt.ItemDataRole.UserRole,row['id'])
            if row['id'] == self.selected_job: self.table.selectRow(index)
        self.table.blockSignals(False)
        self.message.setText('실행 위치를 등록한 후 사용할 수 있습니다. 로컬 실행은 계속 사용할 수 있습니다.' if not self._hosts else
            '이전 요청의 응답이 미확인입니다. 같은 요청을 다시 확인하세요.' if self._pending else
            '입력 묶음과 솔버를 확인한 후 명시적으로 제출하세요.')
        self._controls()

    def _pending_key(self, request_id):
        return 'remote-pending/'+self._store_key+'/'+request_id

    def _restore_pending(self):
        if self._pending or not self._store_key: return
        settings=_settings();settings.beginGroup('remote-pending/'+self._store_key)
        keys=settings.childKeys()
        if not keys: return
        value=json.loads(settings.value(keys[0]))
        if not isinstance(value,list) or len(value)!=3 or value[0] not in {'remote.run','remote.reconnect','remote.cancel','remote.collect'} or value[2]!=keys[0]:
            raise ValueError('보존한 원격 요청을 읽지 못했습니다. 기존 요청 기록을 확인하세요.')
        self._pending=tuple(value)
        self._pending_uncertain = True
        args=value[1]
        if value[0]=='remote.run':
            for combo,key in ((self.host,'host_id'),(self.batch,'batch_job')):
                index=combo.findData(args[key])
                if index>=0: combo.setCurrentIndex(index)
            for widget,key in ((self.threads,'threads'),(self.memory,'memory_mb'),(self.wall,'wall_seconds')):
                widget.setValue(args['remote_resources'][key])
        else: self.selected_job=args['source_job']

    def _host_changed(self):
        row = self._hosts.get(self.host.currentData())
        if not row: self.runtime.setText('등록한 실행 위치가 없습니다.'); return
        runtime = row['runtime']
        self.runtime.setText(f"{runtime['id']} {runtime['version']} / {row['scheduler'].upper()}" +
            (f" / 대기열 {row['queue']}" if row.get('queue') else '') + (f" / 계정 {row['account']}" if row.get('account') else ''))
        for widget,key in ((self.threads,'max_threads'),(self.memory,'max_memory_mb'),(self.wall,'max_wall_seconds')):
            widget.setMaximum(row['limits'][key])

    def _arguments(self):
        return {'host_id':self.host.currentData(),'batch_job':self.batch.currentData(),
            'remote_resources':{'threads':self.threads.value(),'memory_mb':self.memory.value(),'wall_seconds':self.wall.value()},
            'label':self.batch.currentText()[:145]+' 원격 실행'}

    def preview(self):
        args = self._arguments(); args.pop('label')
        args['resources'] = args.pop('remote_resources')
        def accepted(value):
            rows = value['manifest']['candidates']
            self.message.setText(f"후보 {len(rows)}개 / {value['runtime']['id']} {value['runtime']['version']} / 입력 확인 완료")
        self._request(lambda:self._api('preview',args),accepted)

    def submit(self):
        if self._pending is None:
            self._pending = ('remote.run',deepcopy(self._arguments()),'remote-'+uuid.uuid4().hex)
            self._pending_uncertain = False
        self._send_pending()

    def action(self, action):
        if not self.selected_job: return
        if self._pending: self._send_pending();return
        self._pending = ('remote.'+action, {'source_job':self.selected_job}, 'remote-'+uuid.uuid4().hex)
        self._pending_uncertain = False
        self._send_pending()

    def _send_pending(self):
        operation,arguments,request_id = self._pending
        if not self._store_key:
            self.message.setText('작업공간을 확인한 뒤 같은 요청을 다시 확인하세요.');return
        settings=_settings();settings.setValue(self._pending_key(request_id),json.dumps(self._pending,ensure_ascii=False))
        settings.sync()
        if settings.status()!=QSettings.Status.NoError:
            self.message.setText('요청 복구 기록을 저장하지 못했습니다. 쓰기 권한을 확인하세요.');self._controls();return
        def accepted(job):
            if job.get('request_id')!=request_id or job.get('operation')!=operation or job.get('arguments')!=arguments:
                self.message.setText('접수한 요청이 원 입력과 다릅니다. 같은 요청의 확인이 필요합니다.');return
            settings=_settings();settings.remove(self._pending_key(request_id));settings.sync()
            if settings.status()!=QSettings.Status.NoError:
                self.message.setText('접수 기록의 정리를 확인하지 못했습니다. 같은 요청으로 다시 확인하세요.');return
            self._pending = None; self._pending_uncertain = False
            self.selected_job = job['id']; self.job_ready.emit(job['id'])
            self._restore_pending()
            self.message.setText('요청을 접수했습니다. Runner에서 진행 상태를 확인하세요.')
        def confirm():
            catalog=self._api('catalog')
            if catalog['store_key']!=self._store_key: raise ValueError('서비스의 작업공간이 바뀌었습니다. 원 작업공간에서 같은 요청을 확인하세요.')
            for job in catalog['requests']:
                if job['request_id']==request_id: return job
            return self.client.submit(operation,deepcopy(arguments),request_id=request_id)
        def failed(error):
            if not self._pending_uncertain and isinstance(error,WorkbenchHTTPError) and error.code in {400,403,404,409,422}:
                settings=_settings();settings.remove(self._pending_key(request_id));settings.sync()
                if settings.status()==QSettings.Status.NoError:
                    self._pending=None
                    self.message.setText('요청이 접수 전에 거절됐습니다. 입력을 수정하세요. '+error.service_message)
                    return
            self._pending_uncertain=True
            self.message.setText(str(error)+' 같은 요청을 다시 확인하세요.')
        self._request(confirm,accepted,failed)

    def _selected(self):
        rows = self.table.selectionModel().selectedRows()
        if rows:
            self.selected_job = self.table.item(rows[0].row(),0).data(Qt.ItemDataRole.UserRole)
            row = self._attempts[self.selected_job]
            self.detail.setText('선택한 작업: '+row['label']+' / '+STATES.get(row['state'],'확인 필요'))
        self._controls()

    def open_result(self):
        if self.selected_job:
            self.job_ready.emit(self.selected_job)
            self.accept()

    def reject(self):
        if self._busy:
            self._close_when_idle = True
            self.message.setText('현재 요청의 응답을 확인한 후 닫습니다. 원격 작업 취소는 별도로 요청하세요.')
            return
        super().reject()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'table'):
            self.table.setColumnHidden(4, self.width()<850)


def show_remote(runner):
    dialog = RemoteExecutionDialog(runner.client,runner,selected_job=runner.selected_job_id)
    def selected(identifier):
        runner.select_job(identifier); runner.refresh()
    dialog.job_ready.connect(selected)
    if dialog.exec() == QDialog.DialogCode.Accepted and dialog.selected_job:
        identifier, epoch = dialog.selected_job, runner._selection_epoch
        def loaded(job, ticket):
            runner._merge_job(job,ticket);runner._draw_jobs();runner._show_job(job);runner.read_result()
        runner._request('remote-result:'+identifier,lambda:runner.client.status(identifier),loaded,
            relevant=lambda:(identifier,epoch)==(runner.selected_job_id,runner._selection_epoch))
