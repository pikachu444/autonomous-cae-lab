"""FreeCAD-native controls for freeze -> existing JobManager -> Runner.

HTTP is performed on background threads. Only the main-thread timer and typed
owner touch native objects; retrying a lost response reuses the original ID.
"""
from pathlib import Path
from copy import deepcopy
import os
import queue
import subprocess
import threading
import uuid

from caelab.storage import load_json, save_json
from caelab.workbench_client import Client
from apps.desktop_pre import bridge


def command_status_text(operation, state):
    action = {'document.save': '저장', 'document.undo': '실행 취소',
              'document.redo': '다시 실행', 'document.activate': '문서 전환',
              'pre.freeze': '입력 파일 생성', 'pre.contact.freeze': '접촉 입력 생성',
              'pre.links.record': '계산 연결'}.get(operation)
    if action is None:
        family = operation.rsplit('.', 1)[0]
        action = {'pre.motion': '운동 설정', 'pre.joint': '관절 편집',
                  'pre.assembly': '조립 편집', 'pre.parameters': '설계 변수',
                  'pre.fem': '해석 조건', 'pre.contact': '접촉 설정',
                  'pre.project': '프로젝트', 'pre.impact': '충격 해석'}.get(family, '작업')
    status = {'SUCCEEDED': '완료', 'FAILED': '실패', 'CANCELLED': '취소됨',
              'INTERRUPTED': '중단됨', 'QUEUED': '대기 중'}.get(state, '진행 중')
    return action + ': ' + status


class Connection:
    def __init__(self, config, App, Gui, QtCore, QtWidgets, *, log=None):
        self.config, self.App, self.Gui = config, App, Gui
        self.QtCore, self.QtWidgets = QtCore, QtWidgets
        self.log = log or (lambda *a, **kw: None)
        self.client = Client(config['service_url'])
        self.owners, self.pending, self.working = {}, None, set()
        self.native_requests, self.panels = {}, {}
        self.replies = queue.Queue()
        self.closed = False
        self.project_path = Path(config['output']) / 'native_documents.json'
        self.records = load_json(self.project_path) if self.project_path.exists() else {}
        self.dock = QtWidgets.QDockWidget('계산', Gui.getMainWindow())
        self.dock.setObjectName('CAELabCalculation')
        panel = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(panel)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)
        self.identity = QtWidgets.QLabel('현재 문서를 연결하는 중…')
        self.identity.setWordWrap(True)
        self.message = QtWidgets.QLabel('해석과 현재 메시를 선택하세요. 입력 파일 생성은 계산을 실행하지 않습니다.')
        self.message.setWordWrap(True)
        self.run_button = QtWidgets.QPushButton('계산 실행')
        self.export_button = QtWidgets.QPushButton('입력 파일 생성…')
        self.export_button.clicked.connect(lambda: self.run(export_only=True))
        self.run_button.setToolTip('선택한 해석의 현재 메시와 조건으로 계산을 시작합니다.')
        self.run_button.clicked.connect(self.run)
        self.cancel_button = QtWidgets.QPushButton('생성 취소')
        self.cancel_button.clicked.connect(self.cancel)
        self.retry_button = QtWidgets.QPushButton('다시 확인')
        self.retry_button.setToolTip('응답이 끊긴 작업의 상태를 다시 확인합니다. 계산을 중복 실행하지 않습니다.')
        self.retry_button.clicked.connect(self.retry)
        self.numerical_button = QtWidgets.QPushButton('수치 연구…')
        self.numerical_button.clicked.connect(lambda: self.show_panel('research'))
        self.impact_button = QtWidgets.QPushButton('충격 해석…')
        self.impact_button.clicked.connect(self.open_impact)
        self.runner_button = QtWidgets.QPushButton('계산 목록…')
        self.runner_button.clicked.connect(lambda: self.open_runner())
        self.connect_button = QtWidgets.QPushButton('다시 연결')
        self.connect_button.clicked.connect(self.reconnect)
        layout.addWidget(self.identity)
        controls = QtWidgets.QGridLayout()
        controls.setHorizontalSpacing(8)
        controls.setVerticalSpacing(8)
        for index, widget in enumerate((self.export_button, self.run_button, self.cancel_button, self.retry_button,
                       self.numerical_button, self.impact_button, self.runner_button, self.connect_button)):
            widget.setMinimumHeight(30)
            controls.addWidget(widget, index // 4, index % 4)
        layout.addLayout(controls)
        layout.addWidget(self.message)
        self.dock.setWidget(panel)
        Gui.getMainWindow().addDockWidget(QtCore.Qt.BottomDockWidgetArea, self.dock)
        self.timer = QtCore.QTimer(self.dock)
        self.timer.setInterval(500)
        self.timer.timeout.connect(self.tick)
        self.timer.start()
        QtWidgets.QApplication.instance().aboutToQuit.connect(self.close)
        self.tick()

    def active_owner(self):
        doc = self.App.ActiveDocument
        if doc is None or doc.Name not in self.owners:
            raise ValueError('CAD 문서를 만들거나 연 뒤 연결이 끝날 때까지 기다리세요.')
        return self.owners[doc.Name][0]

    def submit_native(self, operation, arguments, target=None, on_done=None, *, owner=None, _capture_motion_view=True):
        owner = owner or self.active_owner()
        owner.refresh()
        broker = self.owners[owner.doc.Name][2]
        if broker.stop.is_set() or not broker.registered.is_set():
            raise ValueError('문서 연결이 끊겼습니다. 다시 연결한 뒤 편집하세요.')
        if any(row['document_id'] == owner.document_id for row in self.native_requests.values()):
            raise ValueError('이 문서의 이전 작업이 아직 진행 중입니다.')
        if operation == 'document.save' and _capture_motion_view:
            dock = getattr(self, 'panels', {}).get(owner.doc.Name, {}).get('motion')
            controller = getattr(dock.widget(), 'motion_controller', None) if dock is not None else None
            snapshot = deepcopy(controller.pending_view()) if controller is not None else None
            if snapshot is not None:
                saved_arguments, saved_target = deepcopy(arguments), deepcopy(target)
                def saved(value):
                    if value.get('status') != 'FAILED':
                        controller.accept_saved_view(snapshot)
                    if on_done:
                        on_done(value)
                def view_applied(value):
                    if value.get('status') == 'FAILED':
                        if on_done:
                            on_done(value)
                        return
                    try:
                        self.submit_native('document.save', saved_arguments, saved_target, saved,
                                           owner=owner, _capture_motion_view=False)
                    except Exception as error:
                        if on_done:
                            on_done({'status': 'FAILED', 'error': {'message': str(error)}})
                        raise
                return self.submit_native('pre.motion.set_view', {'view': snapshot['view']},
                    {'assembly_id': snapshot['assembly_id']}, view_applied, owner=owner)
        identifier = 'C' + uuid.uuid4().hex
        self.native_requests[identifier] = {'command_id': identifier, 'document_id': owner.document_id,
            'session_id': owner.session_id, 'generation': owner.generation, 'operation': operation,
            'arguments': dict(arguments, **({'target': target} if target else {})), 'on_done': on_done, 'retry': False}
        self._send_native(identifier)
        return {'queued': True, 'command_id': identifier}

    def _send_native(self, identifier):
        row = self.native_requests[identifier]
        row['retry'] = False
        self.request(identifier, lambda: self.client.document_command(row['document_id'], row['operation'], row['arguments'],
            session_id=row['session_id'], expected_generation=row['generation'], command_id=identifier), self._native_status)

    def _native_status(self, command):
        identifier = command['command_id']
        row = self.native_requests.get(identifier)
        if row is None: return
        state = command['state']
        if state not in {'SUCCEEDED', 'FAILED', 'CANCELLED', 'INTERRUPTED'}:
            self.message.setText(command_status_text(row['operation'], state))
            return
        if state == 'INTERRUPTED' and command.get('completion_recoverable'):
            row['retry'] = True
            self.message.setText('작업 완료 응답이 끊겼습니다. ‘다시 확인’을 눌러 결과를 확인하세요.')
            return
        self.native_requests.pop(identifier)
        outcome = command.get('outcome', {})
        envelope = outcome.get('result', {})
        value = envelope.get('result') if state == 'SUCCEEDED' else None
        if value is None:
            error = envelope.get('error') or outcome.get('error') or command.get('error') or {'message': state}
            value = {'status': 'FAILED', 'error': error, 'command_id': identifier}
        if row['on_done']:
            row['on_done'](value)
        self.message.setText(command_status_text(row['operation'], state) +
            (': ' + value.get('error', {}).get('message', '') if value.get('status') == 'FAILED' else ''))

    def request(self, key, call, success):
        if key in self.working or self.closed:
            return
        self.working.add(key)
        def run():
            try:
                result, error = call(), None
            except Exception as exc:
                result, error = None, str(exc)
                if hasattr(exc, 'read'):
                    try:
                        error = exc.read().decode('utf-8')
                    except Exception:
                        pass
            self.replies.put((key, success, result, error))
        threading.Thread(target=run, name='CAE Pre request', daemon=True).start()

    def tick(self):
        if self.closed:
            return
        while not self.replies.empty():
            key, success, value, error = self.replies.get_nowait()
            self.working.discard(key)
            if error:
                self.message.setText('연결 오류: ' + error + '\n‘다시 확인’으로 이어갈 수 있습니다. 계산은 중복 실행하지 않습니다.')
                if self.pending and key != 'cancel':
                    self.pending['retry'] = True
                if key in self.native_requests:
                    self.native_requests[key]['retry'] = True
                self.log('request_failed', request=key, error=error)
            else:
                try:
                    success(value)
                except Exception as exc:
                    self.message.setText(str(exc))
                    self.log('response_failed', request=key, error=str(exc))
        documents = self.App.listDocuments()
        for name, doc in documents.items():
            if name not in self.owners and 'reconnect' not in self.working:
                previous = self.records.get(name, {})
                identifier = previous.get('id') if doc.FileName and previous.get('working_file') == doc.FileName else None
                from apps.desktop_pre.metadata import read
                stored_id = read(doc).get('document_id')
                if any(record[0].document_id == (identifier or stored_id) for record in self.owners.values()):
                    identifier = 'P' + uuid.uuid4().hex  # Explicit separate live branch, never two owners for one ID.
                self.owners[name] = bridge.start(doc, self.config, self.QtCore, log=self.log, document_id=identifier)
                self.owners[name][0].find_owner = lambda linked: next((row[0] for row in self.owners.values() if row[0].doc is linked), None)
        for name in list(self.owners):
            owner, dispatch, broker = self.owners[name]
            if name not in documents or owner.closed:
                dispatch.close()
                del self.owners[name]
                for dock in self.panels.pop(name, {}).values(): dock.close(); dock.deleteLater()
            else:
                self.records[name] = {'id': owner.document_id, 'working_file': owner.doc.FileName}
                for dock in self.panels.get(name, {}).values():
                    dock.document_label.setText('대상 문서: ' + str(owner.doc.Label))
        if self.records:
            # Small project identity record, not a copy of native CAD/mesh arrays.
            try:
                if not self.project_path.exists() or load_json(self.project_path) != self.records:
                    save_json(self.project_path, self.records)
            except Exception as error:
                self.message.setText('문서 연결 정보를 저장하지 못했습니다: ' + str(error) +
                                     '\nCAD 문서와 이전 계산 결과는 그대로 남아 있습니다.')
        active = self.App.ActiveDocument
        binding = self.owners.get(active.Name) if active else None
        if binding:
            owner, _, broker = binding
            connected = broker.registered.is_set() and not broker.stop.is_set()
            self.identity.setText(str(active.Label) + '\n' +
                ('연결됨' if connected else '문서 연결을 기다리는 중'))
        else:
            connected = False
            self.identity.setText('CAD 문서를 만들거나 여세요.')
        waiting = self.pending is not None
        self.run_button.setEnabled(connected and not waiting)
        self.export_button.setEnabled(connected and not waiting)
        self.cancel_button.setEnabled(waiting and self.pending['stage'] == 'command' and not self.pending.get('retry'))
        self.retry_button.setEnabled(not self.working and
            ((waiting and self.pending.get('retry', False)) or any(row['retry'] for row in self.native_requests.values())))
        if waiting and self.pending['stage'] == 'command' and not self.pending.get('retry') and 'command' not in self.working:
            identifier = self.pending['command_id']
            self.request('status', lambda: self.client.command_status(identifier), self.command_status)
        for identifier, row in list(self.native_requests.items()):
            if identifier not in self.working and not row['retry']:
                self.request(identifier, lambda identifier=identifier: self.client.command_status(identifier), self._native_status)
        if hasattr(self, 'guards'): self.guards.refresh()

    def run(self, *, export_only=False):
        if self.pending:
            return
        try:
            from femtools import femutils
            import FemGui
            doc = self.App.ActiveDocument
            if doc is None or doc.Name not in self.owners:
                raise ValueError('먼저 CAD 문서를 열고 연결하세요.')
            selected = FemGui.getActiveAnalysis()
            if selected is None or selected.Document is not doc:
                choices = [obj for obj in doc.Objects if femutils.type_of_obj(obj) == 'Fem::FemAnalysis']
                if len(choices) != 1:
                    raise ValueError('모델 트리에서 계산할 해석을 활성화하세요.')
                selected = choices[0]
            solvers = [obj for obj in selected.Group if femutils.type_of_obj(obj) == 'Fem::SolverCcxTools']
            if len(solvers) != 1:
                raise ValueError('CalculiX 솔버가 하나 지정된 해석을 선택하세요.')
            owner = self.owners[doc.Name][0]
            dock = self.panels.get(doc.Name,{}).get('fem')
            page = getattr(dock.widget(),'steps_page',None) if dock is not None else None
            if page is not None and page.modified:
                raise ValueError('해석 단계에 미적용 수정이 있습니다. 단계 적용 또는 수정 취소 후 진행하세요.')
            owner.refresh()
            self.pending = {'command_id': 'C' + uuid.uuid4().hex, 'stage': 'command', 'retry': False,
                'document_id': owner.document_id, 'session_id': owner.session_id,
                'generation': owner.generation, 'export_only': bool(export_only),
                'operation': 'pre.contact.freeze' if any(femutils.type_of_obj(obj) == 'Fem::ConstraintContact'
                    and not getattr(obj, 'Suppressed', False) for obj in selected.Group) else 'pre.freeze',
                'arguments': {'analysis_id': selected.Name, 'solver_id': solvers[0].Name}}
            self.send_command()
        except Exception as exc:
            self.message.setText(str(exc))

    def send_command(self):
        request = dict(self.pending)
        self.message.setText('선택한 해석과 메시로 입력 파일을 준비하는 중…')
        self.request('command', lambda: self.client.document_command(request['document_id'], request.get('operation', 'pre.freeze'), request['arguments'],
            session_id=request['session_id'], expected_generation=request['generation'], command_id=request['command_id']),
            self.command_status)

    def command_status(self, command):
        if not self.pending or command['command_id'] != self.pending['command_id']:
            return
        state = command['state']
        if state == 'SUCCEEDED':
            if self.pending.get('export_only'):
                envelope=command.get('outcome',{}).get('result',{})
                value=envelope.get('result',{})
                relative=value.get('snapshot_relative')
                owner=next((v[0] for v in self.owners.values() if v[0].document_id==self.pending['document_id']),None)
                if not relative or owner is None:
                    self.message.setText('입력 생성 완료. 원 문서 연결을 확인한 뒤 같은 요청을 다시 조회하세요.')
                    self.pending['retry']=True
                    return
                path=(owner.export_root/relative).resolve(strict=True)
                if not path.is_relative_to(owner.export_root.resolve()):
                    raise ValueError('생성된 입력 파일의 경로가 현재 문서의 저장 폴더를 벗어났습니다.')
                self.pending=None
                self.message.setText('입력 파일을 생성했습니다. 계산은 실행하지 않았습니다.\n'+str(path.parent))
                self.show_export(path)
                return
            self.pending.update(stage='submit', retry=False)
            self.submit()
        elif state == 'INTERRUPTED' and command.get('completion_recoverable'):
            # Export may finish after its HTTP completion channel timed out.
            # Preserve the acknowledged identity: retry can recover that
            # receipt, but must never freeze the edited document a second time.
            self.pending.update(stage='command', retry=True)
            self.message.setText('입력 생성의 완료 응답이 끊겼습니다. ‘다시 확인’으로 결과를 확인하세요. '
                                 '입력 생성과 계산을 중복 실행하지 않습니다.')
        elif state in {'FAILED', 'CANCELLED', 'INTERRUPTED'}:
            outcome = command.get('outcome', {})
            error = outcome.get('result', {}).get('error') or outcome.get('error') or command.get('error', {})
            self.message.setText(command_status_text('pre.freeze', state) + ': ' +
                error.get('message', '계산을 시작하지 않았습니다. 입력과 이전 결과는 남아 있습니다.'))
            self.pending = None
        else:
            self.message.setText(command_status_text('pre.freeze', state) +
                '\n대기 중에는 취소할 수 있습니다. 파일을 생성하기 시작한 뒤에는 완료될 때까지 기다리세요.')

    def show_export(self, manifest):
        from .contact_input_dialog import show_input
        show_input(manifest,self.QtWidgets,self.QtCore,parent=self.Gui.getMainWindow())

    def submit(self):
        identifier = self.pending['command_id']
        self.message.setText('생성한 입력 파일로 계산을 시작하는 중…')
        def submitted(value):
            self.pending = None
            self.message.setText('계산을 등록했습니다. 진행 상태는 계산 목록에서 확인하세요.')
            try:
                owner = next(item[0] for item in self.owners.values() if item[0].document_id == value['origin']['document_id'])
                self.submit_native('pre.links.record', {'job_id': value['job']['id']}, owner=owner)
            except Exception as error:
                self.message.setText('계산은 등록했지만 모델과 연결하지 못했습니다: ' + str(error))
            self.open_runner(value['job']['id'])
        self.request('submit', lambda: self.client.native_submit(identifier), submitted)

    def cancel(self):
        if self.pending and self.pending['stage'] == 'command':
            identifier = self.pending['command_id']
            self.request('cancel', lambda: self.client.command_cancel(identifier), self.command_status)

    def retry(self):
        if self.working:
            return
        for identifier, row in list(self.native_requests.items()):
            if row['retry']:
                row['retry'] = False
                self._send_native(identifier)  # Exact identity: unknown submission is sent once; an existing one is only queried.
                return
        if not self.pending: return
        self.pending['retry'] = False
        if self.pending['stage'] == 'submit':
            self.submit()
        else:
            self.send_command()  # Exact command ID/session/generation; never an automatic new attempt.

    def open_impact(self):
        try:
            from .fem_edit import _native_type
            owner = self.active_owner()
            analyses = [o for o in owner.doc.Objects if _native_type(o) == 'Fem::FemAnalysis']
            labels = [str(i + 1) + '. ' + o.Label for i, o in enumerate(analyses)]
            if not labels:
                raise ValueError('먼저 해석과 물체 메시를 준비하세요.')
            selected, ok = self.QtWidgets.QInputDialog.getItem(self.dock, '충격 해석', '해석 선택', labels, 0, False)
            if not ok: return
            analysis = analyses[labels.index(selected)]
            solvers = [o for o in analysis.Group if _native_type(o) == 'Fem::SolverCcxTools' and not getattr(o,'Suppressed',False)]
            if len(solvers) != 1: raise ValueError('메시를 가져올 CalculiX 솔버를 하나 선택하세요.')
            def captured(value):
                if value.get('status') == 'FAILED': return
                def opened(document):
                    env = os.environ.copy()
                    for key in ('PYTHONHOME','PYTHONPATH','QT_PLUGIN_PATH','QML2_IMPORT_PATH','LD_LIBRARY_PATH'):
                        env.pop(key, None)
                    subprocess.Popen([self.config['python'], '-m', 'apps.research.desktop', '--service',
                        self.config['service_url'], 'simulation', '--document-id', document['id']],
                        cwd=str(Path(__file__).resolve().parents[2]), env=env)
                self.request('impact-document', lambda: self.client.document_open(kind='simulation',
                    title=value['title'],draft=value['draft']), opened)
            self.submit_native('pre.impact.capture', {'analysis_id':analysis.Name,'solver_id':solvers[0].Name},
                on_done=captured,owner=owner)
        except Exception as error:
            self.message.setText(str(error))

    def create_numerical_plan(self, command_id, operation):
        def opened(value):
            document = value['document']
            command = [self.config['python'], '-m', 'apps.research.desktop', '--service',
                       self.config['service_url'], 'numerical', '--document-id', document['id']]
            environment = os.environ.copy()
            for key in ('PYTHONHOME', 'PYTHONPATH', 'QT_PLUGIN_PATH', 'QML2_IMPORT_PATH', 'LD_LIBRARY_PATH'):
                environment.pop(key, None)
            subprocess.Popen(command, cwd=str(Path(__file__).resolve().parents[2]), env=environment)
        self.request('cad-plan:' + command_id,
            lambda: self.client.cad_numerical_plan(command_id, operation=operation), opened)

    def open_runner(self, identifier=None):
        command = [self.config['python'], '-m', 'apps.research.runner_window', '--service', self.config['service_url']]
        if identifier:
            command += ['--job-id', identifier]
        environment = os.environ.copy()
        for key in ('PYTHONHOME', 'PYTHONPATH', 'QT_PLUGIN_PATH', 'QML2_IMPORT_PATH', 'LD_LIBRARY_PATH'):
            environment.pop(key, None)
        subprocess.Popen(command, cwd=str(Path(__file__).resolve().parents[2]), env=environment)

    def open_post(self, identifier):
        def resolved(value):
            post = value.get('post_input')
            if not post:
                raise ValueError('아직 열 수 있는 계산 결과가 없습니다. 계산 목록에서 진행 상태와 오류를 확인하세요.')
            command = [self.config['python'], '-m', 'apps.research.desktop', '--service', self.config['service_url'],
                       'post', '--input-id', post['id'], '--job-id', identifier]
            environment = os.environ.copy()
            for key in ('PYTHONHOME', 'PYTHONPATH', 'QT_PLUGIN_PATH', 'QML2_IMPORT_PATH', 'LD_LIBRARY_PATH'):
                environment.pop(key, None)
            subprocess.Popen(command, cwd=str(Path(__file__).resolve().parents[2]), env=environment)
        self.request('post-navigation', lambda: self.client.job_navigation(identifier), resolved)

    def show_panel(self, kind, *, owner=None):
        owner = owner or self.active_owner()
        panels = self.panels.setdefault(owner.doc.Name, {})
        if kind not in panels:
            from importlib import import_module
            modules = {'parameters': ('parameter_panel', owner.parameters, '설계 변수'),
                       'motion': ('motion_panel', owner.motion, '조립 운동'),
                       'fem': ('fem_panel', owner.fem, '해석 설정')}
            if kind == 'research':
                from .research_panel import make_panel
                submit = lambda operation, args, target=None, on_done=None: self.submit_native(operation, args, target, on_done, owner=owner)
                widget = make_panel(self.QtWidgets, self.QtCore, owner.research, submit, self.create_numerical_plan)
                title = '수치 연구'
            elif kind == 'project':
                from .native_controls import project_panel
                widget = project_panel(self, owner)
                title = '프로젝트'
            else:
                module, editor, title = modules[kind]
                factory = import_module('apps.desktop_pre.' + module).make_panel
                submit = lambda operation, args, target=None, on_done=None: self.submit_native(operation, args, target, on_done, owner=owner)
                if kind == 'motion':
                    widget = factory(self.QtCore, self.QtWidgets, submit,
                                     read=lambda: dict(owner.descriptor(), session_id=owner.session_id))
                else:
                    widget = factory(self.QtWidgets, self.QtCore, editor, submit)
            dock = self.QtWidgets.QDockWidget(title, self.Gui.getMainWindow())
            dock.setToolTip(owner.doc.Label)
            dock.document_label = self.QtWidgets.QLabel('대상 문서: ' + str(owner.doc.Label))
            dock.document_label.setWordWrap(True)
            widget.layout().insertWidget(0, dock.document_label)
            dock.setObjectName('CAELab-' + kind + '-' + owner.document_id)
            dock.setWidget(widget); dock.resize(720, 520)
            self.Gui.getMainWindow().addDockWidget(self.QtCore.Qt.RightDockWidgetArea, dock)
            panels[kind] = dock
        panels[kind].show(); panels[kind].raise_()

    def reconnect(self):
        if self.pending or self.native_requests:
            self.message.setText('진행 중인 작업을 먼저 완료하거나 취소하세요. 응답이 끊겼다면 ‘다시 확인’을 누르세요.')
            return
        def connected(context):
            # Keep observing the live CAD while the context request is in
            # flight. A network failure must not discard its save destination
            # or leave dock controls pointing to a closed owner.
            if self.pending or self.native_requests:
                self.message.setText('다시 연결하는 동안 작업이 시작됐습니다. 해당 작업이 끝난 뒤 다시 연결하세요.')
                return
            previous = list(self.owners.items())
            for _, (owner, _, _) in previous:
                owner.before_design_action('reconnect')
            retained = []
            for name, (owner, dispatch, _) in previous:
                visible = [kind for kind, dock in self.panels.get(name, {}).items() if dock.isVisible()]
                retained.append((owner.doc, owner.document_id, owner.generation, owner.saved_generation,
                    owner.project.path, deepcopy(owner.project.last_save), owner.project.last_failure,
                    owner.recovery_error, (owner.project.connection_state()
                        if hasattr(owner.project, 'connection_state') else None), visible))
                dispatch.close()
                for dock in self.panels.pop(name, {}).values():
                    dock.close(); dock.deleteLater()
            self.owners.clear()
            self.config.update(export_root=context['export_root'], python=context['python'])
            live = self.App.listDocuments()
            for doc, identifier, generation, saved, path, last_save, failure, recovery, graph_state, _ in retained:
                if live.get(doc.Name) is not doc:
                    continue
                owner, dispatch, broker = bridge.start(doc, self.config, self.QtCore, log=self.log, document_id=identifier)
                owner.generation, owner.saved_generation = generation, saved
                owner.project.path, owner.project.last_save, owner.project.last_failure = path, last_save, failure
                if graph_state is not None:
                    owner.project.restore_connection_state(graph_state)
                owner.recovery_error = recovery
                owner.find_owner = lambda linked: next((row[0] for row in self.owners.values() if row[0].doc is linked), None)
                self.owners[doc.Name] = owner, dispatch, broker
            for doc, *_, visible in retained:
                binding = self.owners.get(doc.Name)
                if binding and binding[0].doc is doc:
                    for kind in visible:
                        self.show_panel(kind, owner=binding[0])
            self.message.setText('문서를 다시 연결했습니다.')
        self.request('reconnect', self.client.desktop_context, connected)

    def close(self):
        if self.closed:
            return
        self.closed = True
        self.timer.stop()
        for owner, dispatch, broker in self.owners.values():
            dispatch.close()
