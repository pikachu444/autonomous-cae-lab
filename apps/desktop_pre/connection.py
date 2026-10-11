"""FreeCAD-native controls for freeze -> existing JobManager -> Runner.

HTTP is performed on background threads. Only the main-thread timer and typed
owner touch native objects; retrying a lost response reuses the original ID.
"""
from pathlib import Path
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
        self.message = QtWidgets.QLabel('Use the native FEM tree to select the Analysis and its existing mesh.\n'
            'Connected adapter: one solid, C3D10, static linear elasticity, Fixed/Force. Other native studies remain editable.')
        self.message.setWordWrap(True)
        self.run_button = QtWidgets.QPushButton('Run FEM')
        self.run_button.setToolTip('Freeze this Analysis with its existing mesh and native conditions, then submit through Runner')
        self.run_button.clicked.connect(self.run)
        self.cancel_button = QtWidgets.QPushButton('Cancel export')
        self.cancel_button.clicked.connect(self.cancel)
        self.retry_button = QtWidgets.QPushButton('Retry request')
        self.retry_button.clicked.connect(self.retry)
        self.runner_button = QtWidgets.QPushButton('Runner…')
        self.runner_button.clicked.connect(lambda: self.open_runner())
        self.connect_button = QtWidgets.QPushButton('Reconnect')
        self.connect_button.clicked.connect(self.reconnect)
        layout.addWidget(self.identity)
        controls = QtWidgets.QHBoxLayout()
        for widget in (self.run_button, self.cancel_button, self.retry_button,
                       self.runner_button, self.connect_button):
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
                self.owners[name] = bridge.start(doc, self.config, self.QtCore, log=self.log, document_id=identifier)
        for name in list(self.owners):
            owner, dispatch, broker = self.owners[name]
            if name not in documents or owner.closed:
                dispatch.close()
                del self.owners[name]
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
        self.cancel_button.setEnabled(waiting and self.pending['stage'] == 'command' and not self.pending.get('retry'))
        self.retry_button.setEnabled(waiting and self.pending.get('retry', False) and not self.working)
        if waiting and self.pending['stage'] == 'command' and not self.pending.get('retry') and 'command' not in self.working:
            identifier = self.pending['command_id']
            self.request('status', lambda: self.client.command_status(identifier), self.command_status)

    def run(self):
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
            owner.refresh()
            self.pending = {'command_id': 'C' + uuid.uuid4().hex, 'stage': 'command', 'retry': False,
                'document_id': owner.document_id, 'session_id': owner.session_id,
                'generation': owner.generation, 'arguments': {'analysis_id': selected.Name, 'solver_id': solvers[0].Name}}
            self.send_command()
        except Exception as exc:
            self.message.setText(str(exc))

    def send_command(self):
        request = dict(self.pending)
        self.message.setText('Freezing the selected existing mesh and native input…')
        self.request('command', lambda: self.client.document_command(request['document_id'], 'pre.freeze', request['arguments'],
            session_id=request['session_id'], expected_generation=request['generation'], command_id=request['command_id']),
            self.command_status)

    def command_status(self, command):
        if not self.pending or command['command_id'] != self.pending['command_id']:
            return
        state = command['state']
        if state == 'SUCCEEDED':
            self.pending.update(stage='submit', retry=False)
            self.submit()
        elif state in {'FAILED', 'CANCELLED', 'INTERRUPTED'}:
            error = command.get('outcome', {}).get('error') or command.get('error', {})
            self.message.setText(state + ': ' + error.get('message', 'No calculation submitted. Input and previous results remain.'))
            self.pending = None
        else:
            self.message.setText('Native export: ' + command.get('phase', state) +
                '\nCancellation is supported while queued; native export already applying must finish.')

    def submit(self):
        identifier = self.pending['command_id']
        self.message.setText('Submitting this exact frozen native input…')
        def submitted(value):
            self.pending = None
            self.message.setText('Submitted ' + value['job']['id'] + '. Further editing belongs to a new input; this job keeps its snapshot.')
            self.open_runner(value['job']['id'])
        self.request('submit', lambda: self.client.native_submit(identifier), submitted)

    def cancel(self):
        if self.pending and self.pending['stage'] == 'command':
            identifier = self.pending['command_id']
            self.request('cancel', lambda: self.client.command_cancel(identifier), self.command_status)

    def retry(self):
        if not self.pending or self.working:
            return
        self.pending['retry'] = False
        if self.pending['stage'] == 'submit':
            self.submit()
        else:
            self.send_command()  # Exact command ID/session/generation; never an automatic new attempt.

    def open_runner(self, identifier=None):
        command = [self.config['python'], '-m', 'apps.research.runner_window', '--service', self.config['service_url']]
        if identifier:
            command += ['--job-id', identifier]
        environment = os.environ.copy()
        for key in ('PYTHONHOME', 'PYTHONPATH', 'QT_PLUGIN_PATH', 'QML2_IMPORT_PATH', 'LD_LIBRARY_PATH'):
            environment.pop(key, None)
        subprocess.Popen(command, cwd=str(Path(__file__).resolve().parents[2]), env=environment)

    def reconnect(self):
        if self.pending:
            self.message.setText('Resolve the pending command first. A disconnected applying command is not automatically replayed.')
            return
        for owner, dispatch, broker in self.owners.values():
            dispatch.close()
        self.owners.clear()
        def connected(context):
            self.config.update(export_root=context['export_root'], python=context['python'])
            self.message.setText('New native owner session; previous session commands remain separate.')
        self.request('reconnect', self.client.desktop_context, connected)

    def close(self):
        if self.closed:
            return
        self.closed = True
        self.timer.stop()
        for owner, dispatch, broker in self.owners.values():
            dispatch.close()
