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
        self.dock = QtWidgets.QDockWidget('CAE calculation', Gui.getMainWindow())
        self.dock.setObjectName('CAELabCalculation')
        panel = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(panel)
        self.identity = QtWidgets.QLabel('Connecting the active native document…')
        self.identity.setWordWrap(True)
        self.message = QtWidgets.QLabel('해석과 현재 메시를 선택하세요. 입력 파일 생성은 계산을 실행하지 않습니다.')
        self.message.setWordWrap(True)
        self.run_button = QtWidgets.QPushButton('계산 실행')
        self.export_button = QtWidgets.QPushButton('입력 파일 생성…')
        self.export_button.clicked.connect(lambda: self.run(export_only=True))
        self.run_button.setToolTip('Freeze this Analysis with its existing mesh and native conditions, then submit through Runner')
        self.run_button.clicked.connect(self.run)
        self.cancel_button = QtWidgets.QPushButton('Cancel export')
        self.cancel_button.clicked.connect(self.cancel)
        self.retry_button = QtWidgets.QPushButton('Retry request')
        self.retry_button.clicked.connect(self.retry)
        self.numerical_button = QtWidgets.QPushButton('Numerical…')
        self.numerical_button.clicked.connect(lambda: self.show_panel('research'))
        self.impact_button = QtWidgets.QPushButton('충격 해석…')
        self.impact_button.clicked.connect(self.open_impact)
        self.runner_button = QtWidgets.QPushButton('Runner…')
        self.runner_button.clicked.connect(lambda: self.open_runner())
        self.connect_button = QtWidgets.QPushButton('Reconnect')
        self.connect_button.clicked.connect(self.reconnect)
        layout.addWidget(self.identity)
        controls = QtWidgets.QHBoxLayout()
        for widget in (self.export_button, self.run_button, self.cancel_button, self.retry_button,
                       self.numerical_button, self.impact_button, self.runner_button, self.connect_button):
            controls.addWidget(widget)
        controls.addStretch()
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
            raise ValueError('Create/open the native document and wait for its connection')
        return self.owners[doc.Name][0]

    def submit_native(self, operation, arguments, target=None, on_done=None, *, owner=None):
        owner = owner or self.active_owner()
        owner.refresh()
        broker = self.owners[owner.doc.Name][2]
        if broker.stop.is_set() or not broker.registered.is_set():
            raise ValueError('Native owner is disconnected; reconnect before submitting an edit')
        if any(row['document_id'] == owner.document_id for row in self.native_requests.values()):
            raise ValueError('An explicit command for this document is already pending')
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
            self.message.setText(row['operation'] + ' · ' + command.get('phase', state))
            return
        if state == 'INTERRUPTED' and command.get('completion_recoverable'):
            row['retry'] = True
            self.message.setText('Native completion is recoverable. Retry queries the same command; it does not repeat the edit.')
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
        self.message.setText(row['operation'] + ' · ' + state +
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
                self.message.setText(error + '\nThe same request can be retried; no new calculation was silently submitted.')
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
        if self.records:
            # Small project identity record, not a copy of native CAD/mesh arrays.
            try:
                if not self.project_path.exists() or load_json(self.project_path) != self.records:
                    save_json(self.project_path, self.records)
            except Exception as error:
                self.message.setText('Native identity record could not be saved: ' + str(error) +
                                     '\nThe editable CAD document and previous results are unchanged.')
        active = self.App.ActiveDocument
        binding = self.owners.get(active.Name) if active else None
        if binding:
            owner, _, broker = binding
            connected = broker.registered.is_set() and not broker.stop.is_set()
            self.identity.setText(f'{active.Label} · input g{owner.generation}' +
                (' · native owner connected' if connected else ' · connecting / stopped'))
        else:
            connected = False
            self.identity.setText('Create or open a native CAD document')
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
                raise ValueError('Open a connected native CAD document first')
            selected = FemGui.getActiveAnalysis()
            if selected is None or selected.Document is not doc:
                choices = [obj for obj in doc.Objects if femutils.type_of_obj(obj) == 'Fem::FemAnalysis']
                if len(choices) != 1:
                    raise ValueError('Activate the exact FEM Analysis in the native tree')
                selected = choices[0]
            solvers = [obj for obj in selected.Group if femutils.type_of_obj(obj) == 'Fem::SolverCcxTools']
            if len(solvers) != 1:
                raise ValueError('Select an Analysis with one native CalculiX solver')
            owner = self.owners[doc.Name][0]
            dock = self.panels.get(doc.Name,{}).get('fem')
            page = getattr(dock.widget(),'steps_page',None) if dock is not None else None
            if page is not None and page.modified:
                raise ValueError('해석 단계에 미적용 수정이 있습니다. 단계 적용 또는 수정 취소 후 진행하세요.')
            owner.refresh()
            self.pending = {'command_id': 'C' + uuid.uuid4().hex, 'stage': 'command', 'retry': False,
                'document_id': owner.document_id, 'session_id': owner.session_id,
                'generation': owner.generation, 'export_only': bool(export_only),
                'operation': 'pre.contact.freeze' if any(femutils.type_of_obj(obj) in ('Fem::ConstraintContact', 'Fem::ConstraintTie')
                    and not getattr(obj, 'Suppressed', False) for obj in selected.Group) else 'pre.freeze',
                'arguments': {'analysis_id': selected.Name, 'solver_id': solvers[0].Name}}
            self.send_command()
        except Exception as exc:
            self.message.setText(str(exc))

    def send_command(self):
        request = dict(self.pending)
        self.message.setText('Preparing the selected analysis and current body meshes…')
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
                    raise ValueError('Export receipt is outside this owner')
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
            self.message.setText('Native export completion is unconfirmed. Retry checks this same export; '
                                 'it does not repeat it or submit a new calculation.')
        elif state in {'FAILED', 'CANCELLED', 'INTERRUPTED'}:
            outcome = command.get('outcome', {})
            error = outcome.get('result', {}).get('error') or outcome.get('error') or command.get('error', {})
            self.message.setText(state + ': ' + error.get('message', 'No calculation submitted. Input and previous results remain.'))
            self.pending = None
        else:
            self.message.setText('Native export: ' + command.get('phase', state) +
                '\nCancellation is supported while queued; native export already applying must finish.')

    def show_export(self, manifest):
        from .contact_input_dialog import show_input
        show_input(manifest,self.QtWidgets,self.QtCore,parent=self.Gui.getMainWindow())

    def submit(self):
        identifier = self.pending['command_id']
        self.message.setText('Submitting this exact frozen native input…')
        def submitted(value):
            self.pending = None
            self.message.setText('Submitted ' + value['job']['id'] + '. Further editing belongs to a new input; this job keeps its snapshot.')
            try:
                owner = next(item[0] for item in self.owners.values() if item[0].document_id == value['origin']['document_id'])
                self.submit_native('pre.links.record', {'job_id': value['job']['id']}, owner=owner)
            except Exception as error:
                self.message.setText('Job submitted; design link needs explicit retry: ' + str(error))
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
                raise ValueError('먼저 native Analysis와 현재 물체 메시를 준비하세요')
            selected, ok = self.QtWidgets.QInputDialog.getItem(self.dock, '충격 해석', 'Analysis', labels, 0, False)
            if not ok: return
            analysis = analyses[labels.index(selected)]
            solvers = [o for o in analysis.Group if _native_type(o) == 'Fem::SolverCcxTools' and not getattr(o,'Suppressed',False)]
            if len(solvers) != 1: raise ValueError('메시 참조용 CalculiX solver 하나를 선택하세요')
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
                raise ValueError('This job has no completed registered Post field. Open its Runner diagnostics.')
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
            modules = {'parameters': ('parameter_panel', owner.parameters, 'Research variables'),
                       'motion': ('motion_panel', owner.motion, 'Assembly motion'),
                       'fem': ('fem_panel', owner.fem, 'Mesh, regions and conditions')}
            if kind == 'research':
                from .research_panel import make_panel
                submit = lambda operation, args, target=None, on_done=None: self.submit_native(operation, args, target, on_done, owner=owner)
                widget = make_panel(self.QtWidgets, self.QtCore, owner.research, submit, self.create_numerical_plan)
                title = 'Analysis research'
            elif kind == 'project':
                from .native_controls import project_panel
                widget = project_panel(self, owner)
                title = 'Project and calculations'
            else:
                module, editor, title = modules[kind]
                factory = import_module('apps.desktop_pre.' + module).make_panel
                submit = lambda operation, args, target=None, on_done=None: self.submit_native(operation, args, target, on_done, owner=owner)
                if kind == 'motion':
                    widget = factory(self.QtCore, self.QtWidgets, submit,
                                     read=lambda: dict(owner.descriptor(), session_id=owner.session_id))
                else:
                    widget = factory(self.QtWidgets, self.QtCore, editor, submit)
            dock = self.QtWidgets.QDockWidget(title + ' · ' + owner.doc.Label, self.Gui.getMainWindow())
            dock.setObjectName('CAELab-' + kind + '-' + owner.document_id)
            dock.setWidget(widget); dock.resize(720, 520)
            self.Gui.getMainWindow().addDockWidget(self.QtCore.Qt.RightDockWidgetArea, dock)
            panels[kind] = dock
        panels[kind].show(); panels[kind].raise_()

    def reconnect(self):
        if self.pending or self.native_requests:
            self.message.setText('Resolve the pending command first. A disconnected applying command is not automatically replayed.')
            return
        def connected(context):
            # Keep observing the live CAD while the context request is in
            # flight. A network failure must not discard its save destination
            # or leave dock controls pointing to a closed owner.
            if self.pending or self.native_requests:
                self.message.setText('A command started while reconnecting. Resolve it before changing the owner session.')
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
            self.message.setText('New native owner session; previous session commands remain separate.')
        self.request('reconnect', self.client.desktop_context, connected)

    def close(self):
        if self.closed:
            return
        self.closed = True
        self.timer.stop()
        for owner, dispatch, broker in self.owners.values():
            dispatch.close()
