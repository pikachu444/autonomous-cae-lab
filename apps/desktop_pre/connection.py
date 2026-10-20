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
              'document.redo': '다시 실행', 'document.activate': '모델 전환',
              'pre.freeze': '입력 파일 생성', 'pre.contact.freeze': '접촉 입력 생성', 'pre.pretension.freeze': '체결 입력 생성',
              'pre.initial.freeze': '초기조건 입력 생성', 'pre.contact.aster_freeze': 'Code_Aster 접촉 입력 생성',
              'pre.links.record': '계산 연결'}.get(operation)
    if action is None:
        family = operation.rsplit('.', 1)[0]
        action = {'pre.motion': '운동 설정', 'pre.joint': '관절 편집',
                  'pre.assembly': '조립 편집', 'pre.parameters': '설계 변수',
                  'pre.fem': '해석 조건', 'pre.contact': '접촉 설정',
                  'pre.project': '프로젝트', 'pre.impact': '충격 해석', 'pre.beam': '빔 설정'}.get(family, '작업')
    status = {'SUCCEEDED': '완료', 'FAILED': '실패', 'CANCELLED': '취소됨',
              'INTERRUPTED': '중단됨', 'QUEUED': '대기 중'}.get(state, '진행 중')
    return action + ': ' + status


class Connection:
    def __init__(self, config, App, Gui, QtCore, QtWidgets, *, log=None, initial_owners=()):
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
        self.identity = QtWidgets.QLabel('현재 모델을 연결하는 중…')
        self.identity.setWordWrap(True)
        self.message = QtWidgets.QLabel('솔버를 선택해 계산하고, 결과를 선택해 ParaView에서 여세요.')
        self.message.setWordWrap(True)
        self.native_solver_button = QtWidgets.QPushButton('FreeCAD에서 계산…')
        self.native_solver_button.setToolTip('모델 트리의 솔버 하나를 선택합니다. FreeCAD의 솔버 작업창에서 입력 작성과 실행을 진행합니다.')
        self.native_solver_button.clicked.connect(self.open_native_solver)
        self.native_post_button = QtWidgets.QPushButton('선택 결과를 ParaView에서 열기')
        self.native_post_button.setToolTip('선택한 결과만 새 VTU로 내보냅니다. FreeCAD 기계 결과의 좌표는 mm, 변위는 m, 응력은 Pa입니다. Post 결과는 원 배열의 단위를 확인하세요.')
        self.native_post_button.clicked.connect(self.open_native_result)
        self.run_button = QtWidgets.QPushButton('입력 보존 후 계산')
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
        tabs = QtWidgets.QTabWidget()
        native = QtWidgets.QWidget()
        native_row = QtWidgets.QHBoxLayout(native)
        for widget in (self.native_solver_button, self.native_post_button):
            widget.setMinimumHeight(32)
            native_row.addWidget(widget)
        tabs.addTab(native, '기본 해석')
        managed = QtWidgets.QWidget()
        controls = QtWidgets.QGridLayout()
        controls.setHorizontalSpacing(8)
        controls.setVerticalSpacing(8)
        for index, widget in enumerate((self.export_button, self.run_button, self.cancel_button, self.retry_button,
                       self.numerical_button, self.impact_button, self.runner_button, self.connect_button)):
            widget.setMinimumHeight(30)
            controls.addWidget(widget, index // 4, index % 4)
        managed.setLayout(controls)
        tabs.addTab(managed, '계산 관리')
        layout.addWidget(tabs)
        layout.addWidget(self.message)
        self.dock.setWidget(panel)
        Gui.getMainWindow().addDockWidget(QtCore.Qt.BottomDockWidgetArea, self.dock)
        self.timer = QtCore.QTimer(self.dock)
        self.timer.setInterval(500)
        self.timer.timeout.connect(self.tick)
        self.timer.start()
        QtWidgets.QApplication.instance().aboutToQuit.connect(self.close)
        from .shell_controls import install as install_shell_controls
        install_shell_controls(self)
        from .composite_controls import install as install_composite_controls
        install_composite_controls(self)
        for owner in initial_owners:
            if (owner.doc.Name in self.owners or App.listDocuments().get(owner.doc.Name) is not owner.doc
                    or owner.App is not App or owner.Gui is not Gui):
                raise ValueError('Native owner adoption requires its current exact document')
            self.owners[owner.doc.Name] = bridge.start(owner.doc, config, QtCore, log=self.log, _existing_owner=owner)
            owner.find_owner = lambda linked: next((row[0] for row in self.owners.values() if row[0].doc is linked), None)
        self.tick()

    def active_owner(self):
        doc = self.App.ActiveDocument
        if doc is None or doc.Name not in self.owners:
            raise ValueError('CAD 모델을 만들거나 연 뒤 연결이 끝날 때까지 기다리세요.')
        return self.owners[doc.Name][0]

    def _native_selection(self, kind):
        doc = self.App.ActiveDocument
        selected = self.Gui.Selection.getSelection()
        if doc is None or len(selected) != 1 or getattr(selected[0], 'Document', None) is not doc:
            raise ValueError('현재 모델의 ' + ('솔버' if kind == 'solver' else '계산 결과') + ' 하나를 모델 트리에서 선택하세요.')
        obj = selected[0]
        types = ('Fem::FemSolverObjectPython',) if kind == 'solver' else ('Fem::FemResultObject', 'Fem::FemPostObject')
        if not any(obj.isDerivedFrom(name) for name in types):
            raise ValueError('모델 트리에서 ' + ('솔버' if kind == 'solver' else '계산 결과') + ' 하나를 선택하세요.')
        binding = self.owners.get(doc.Name)
        if self.pending or (binding and any(row['document_id'] == binding[0].document_id for row in self.native_requests.values())):
            raise ValueError('진행 중인 모델 작업을 마친 뒤 선택한 ' + ('솔버를 여세요.' if kind == 'solver' else '결과를 여세요.'))
        return obj

    def open_native_solver(self):
        try:
            solver = self._native_selection('solver')
            binding = self.owners.get(solver.Document.Name)
            if binding:
                transfers = binding[0].read_metadata().get('displacement_transfers', {})
                if any(record.get('draft', {}).get('solver_id') == solver.Name for record in transfers.values()):
                    raise ValueError('가져온 변위 경계조건은 계산 관리에서 입력을 생성해 실행하세요. FreeCAD 기본 솔버 창의 입력에는 가져온 변위가 포함되지 않습니다.')
            composites = binding[0].read_metadata().get('composite_shells', {}) if binding else {}
            targets = [aid for aid, record in composites.items() if record['draft'].get('solver_id') == solver.Name]
            if targets:
                if len(targets) != 1: raise ValueError('적층 해석 하나를 활성화하세요.')
                from .composite_controls import route as composite_route
                composite_route(self, binding[0], targets[0], open_only=True)
                return
            if binding:
                from .initial_field_controls import route as initial_route
                if initial_route(self, binding[0], solver):return
                from .pretension_controls import route_native_solver
                if route_native_solver(self, binding[0], solver): return
            # Same entry point as native FEM_SolverControl. Its own task panel
            # owns input writing, ccx preferences/PATH, QProcess and results.
            if self.Gui.ActiveDocument.setEdit(solver, 0) is False:
                raise ValueError('열려 있는 편집 작업을 마친 뒤 솔버를 다시 여세요.')
            for dock in self.Gui.getMainWindow().findChildren(self.QtWidgets.QDockWidget):
                if dock.objectName() == 'Tasks':
                    dock.show()
                    dock.raise_()
            self.message.setText('FreeCAD 솔버 작업창에서 입력 파일 작성과 계산을 실행하세요.')
        except Exception as error:
            self.message.setText(str(error))

    def open_native_result(self):
        result = None
        try:
            selected = self._native_selection('result')
            executable = self._native_paraview()
            if executable is None:
                return
            if self._native_selection('result') is not selected:
                raise ValueError('실행 파일을 고르는 동안 선택한 결과가 바뀌었습니다. 결과를 다시 선택하세요.')
            from feminout import importVTKResults
            folder = Path(self.config['output']) / 'native-results' / uuid.uuid4().hex
            folder.mkdir(parents=True, exist_ok=False)
            result = folder / 'result.vtu'
            # Native official exporter consumes exactly the captured selection.
            # Do not freeze/recompute the model or parse FRD a second time.
            importVTKResults.export([selected], str(result))
            if not result.is_file() or result.stat().st_size == 0:
                raise ValueError('선택한 결과를 VTU로 내보내지 못했습니다. FreeCAD 오류를 확인하세요.')
            environment = os.environ.copy()
            for key in ('PYTHONHOME', 'PYTHONPATH', 'QT_PLUGIN_PATH', 'QML2_IMPORT_PATH', 'LD_LIBRARY_PATH'):
                environment.pop(key, None)
            command = [self.config['python'], '-m', 'apps.research.desktop', '--service',
                       self.config['service_url'], 'post', '--input-path', str(result),
                       '--executable', str(executable)]
            repository = self.config.get('repo_root') or str(Path(__file__).resolve().parents[2])
            with (folder / 'launch.stdout.log').open('wb') as stdout, (folder / 'launch.stderr.log').open('wb') as stderr:
                subprocess.Popen(command, cwd=str(repository), env=environment, stdout=stdout, stderr=stderr)
            units = ('기계 결과: 좌표 mm, 변위 m, 응력 Pa.' if selected.isDerivedFrom('Fem::FemResultObject')
                     else 'Post 결과의 원 배열 단위를 확인하세요.')
            self.message.setText('같은 연구 작업공간의 후처리 열기를 요청했습니다. ' + units + '\n' + str(result))
        except Exception as error:
            self.message.setText(str(error) + ('\n내보낸 결과: ' + str(result) +
                '\n열기 오류 기록: ' + str(result.parent / 'launch.stderr.log') if result is not None and result.is_file() else ''))

    def _native_paraview(self):
        settings = self.QtCore.QSettings('AutonomousCAELab', 'DesktopLaunchers')
        for source, value in (('연결 설정 paraview_executable', self.config.get('paraview_executable')),
                              ('CAELAB_PARAVIEW_EXE', os.getenv('CAELAB_PARAVIEW_EXE')),
                              ('saved', settings.value('paraview_executable', ''))):
            if value:
                path = Path(str(value)).expanduser()
                if path.is_file() and path.name.lower() in {'paraview.exe', 'paraview'}:
                    return path.resolve()
                if source != 'saved':
                    raise ValueError(source + '에 지정한 ParaView 실행 파일을 확인하세요: ' + str(path))
        filename, _ = self.QtWidgets.QFileDialog.getOpenFileName(self.dock, '설치된 ParaView 선택', '',
            'ParaView (paraview.exe);;모든 파일 (*)')
        if not filename:
            self.message.setText('ParaView 열기를 취소했습니다. 원 결과는 그대로입니다.')
            return None
        path = Path(filename).resolve(strict=True)
        if not path.is_file() or path.name.lower() not in {'paraview.exe', 'paraview'}:
            raise ValueError('설치된 paraview.exe를 선택하세요.')
        settings.setValue('paraview_executable', str(path))
        return path

    def submit_native(self, operation, arguments, target=None, on_done=None, *, owner=None, _capture_motion_view=True, _capture_shell=True, _capture_beam=True, _capture_dynamic=True, _capture_composite=True, _capture_connector=True):
        owner = owner or self.active_owner()
        if operation in {'document.save','pre.project.save'}:
            from .native_controls import transfer_pending
            if transfer_pending(self, owner):
                raise ValueError('변위 가져오기 창에서 초안을 저장하거나 편집을 취소한 뒤 프로젝트를 저장하세요.')
        if operation == 'document.save' and _capture_composite:
            from .composite_controls import flush_before_save
            captured = flush_before_save(self, owner, arguments, target, on_done, _capture_motion_view=_capture_motion_view, _capture_shell=_capture_shell, _capture_beam=_capture_beam, _capture_dynamic=_capture_dynamic)
            if captured is not None: return captured
        if operation == 'document.save' and _capture_dynamic:
            from .dynamic_menu import flush_before_save
            captured = flush_before_save(self, owner, arguments, target, on_done, capture_motion=_capture_motion_view, capture_shell=_capture_shell, capture_beam=_capture_beam)
            if captured is not None: return captured
        if operation == 'document.save' and _capture_shell:
            from .shell_controls import flush_before_save
            captured = flush_before_save(self, owner, arguments, target, on_done, capture_motion=_capture_motion_view, capture_beam=_capture_beam)
            if captured is not None: return captured
        owner.refresh()
        broker = self.owners[owner.doc.Name][2]
        if any(row['document_id'] == owner.document_id for row in self.native_requests.values()):
            raise ValueError('이 모델의 이전 작업이 아직 진행 중입니다.')
        if operation == 'document.save' and _capture_beam:
            from .beam_menu import flush_before_save
            queued = flush_before_save(self, owner, arguments, target, on_done, capture_motion=_capture_motion_view, capture_shell=_capture_shell)
            if queued is not None: return queued
        disconnected = broker.stop.is_set() or not broker.registered.is_set()
        if disconnected:
            from .native_controls import _motion_controller
            controller = _motion_controller(self, owner)
            def apply_local(op, args, selected):
                owner.refresh()
                return owner.dispatch({'command_id': 'C'+uuid.uuid4().hex, 'document_id': owner.document_id,
                    'session_id': owner.session_id, 'expected_generation': owner.generation,
                    'operation': op, 'arguments': args, 'target': selected})
            if operation in {'pre.connector.draft', 'pre.fem.pretension_save_editor',
                             'pre.initial.save_draft', 'pre.initial.discard',
                             'pre.fem.displacement_read', 'pre.fem.displacement_save',
                             'pre.fem.displacement_remove'} or operation.startswith(('pre.beam.', 'pre.dynamic.', 'pre.composite.')):
                result = apply_local(operation, arguments, target or {})
                value = result if result.get('status') == 'FAILED' else result.get('result', result)
                if on_done: on_done(value)
                return {'queued': True, 'completed': True, 'command_id': result.get('command_id')}
            if operation == 'pre.motion.save_editor':
                assembly = owner.motion._assembly(target or {})
                stored = owner.read_metadata().get('motion_editors', {}).get(assembly.Name)
                editor = arguments.get('editor')
                if (set(arguments) != {'editor'} or not isinstance(stored, dict) or not isinstance(editor, dict)
                        or set(editor) != set(stored) or editor.get('view') != stored.get('view') or editor.get('path_view') != stored.get('path_view')
                        or any(editor.get(key) is not None and editor.get(key) != stored.get(key) for key in ('joint_draft', 'definition_draft'))
                        or not any(stored.get(key) is not None and editor.get(key) is None for key in ('joint_draft', 'definition_draft'))):
                    raise ValueError('연결이 끊긴 동안에는 저장 또는 명시적 편집 취소만 가능합니다.')
                result = apply_local(operation, arguments, target)
                value = result if result.get('status') == 'FAILED' else result.get('result', result)
                if on_done: on_done(value)
                return {'queued': True, 'completed': True, 'command_id': result.get('command_id')}
            if operation != 'document.save':
                error = ValueError('모델 연결이 끊겼습니다. 다시 연결한 뒤 편집하세요.')
                error.native_terminal = True  # No command was submitted.
                raise error
            snapshot = deepcopy(controller.pending_editor()) if controller is not None and _capture_motion_view else None
            if snapshot is not None:
                result = apply_local('pre.motion.save_editor', {'editor': snapshot['editor']}, {'assembly_id': snapshot['assembly_id']})
                if result.get('status') == 'FAILED':
                    if on_done: on_done(result)
                    return {'queued': True, 'completed': True, 'command_id': result.get('command_id')}
            if _capture_connector:
                from .connector_menu import flush_before_save
                def document_saved(value):
                    if value.get('status') != 'FAILED' and snapshot is not None: controller.accept_saved_editor(snapshot)
                    if on_done: on_done(value)
                captured = flush_before_save(self, owner, arguments, target, document_saved,
                    _capture_motion_view=False, _capture_shell=False, _capture_beam=False,
                    _capture_dynamic=False, _capture_composite=False)
                if captured is not None: return captured
            result = apply_local('document.save', arguments, target or {})
            value = result if result.get('status') == 'FAILED' else result.get('result', result)
            if result.get('status') != 'FAILED' and snapshot is not None: controller.accept_saved_editor(snapshot)
            if on_done: on_done(value)
            return {'queued': True, 'completed': True, 'command_id': result.get('command_id')}
        if operation == 'document.save' and _capture_motion_view:
            dock = getattr(self, 'panels', {}).get(owner.doc.Name, {}).get('motion')
            controller = getattr(dock.widget(), 'motion_controller', None) if dock is not None else None
            editor_save = controller is not None and hasattr(controller, 'pending_editor')
            snapshot = deepcopy(controller.pending_editor() if editor_save else controller.pending_view()) if controller is not None else None
            if snapshot is not None:
                saved_arguments, saved_target = deepcopy(arguments), deepcopy(target)
                def saved(value):
                    if value.get('status') != 'FAILED':
                        if editor_save: controller.accept_saved_editor(snapshot)
                        else: controller.accept_saved_view(snapshot)
                    if on_done:
                        on_done(value)
                def view_applied(value):
                    if value.get('status') == 'FAILED':
                        if on_done:
                            on_done(value)
                        return
                    try:
                        self.submit_native('document.save', saved_arguments, saved_target, saved,
                                           owner=owner, _capture_motion_view=False, _capture_shell=_capture_shell, _capture_beam=_capture_beam, _capture_dynamic=_capture_dynamic)
                    except Exception as error:
                        if on_done:
                            on_done({'status': 'FAILED', 'error': {'message': str(error)}})
                        raise
                return self.submit_native('pre.motion.save_editor' if editor_save else 'pre.motion.set_view',
                    {'editor': snapshot['editor']} if editor_save else {'view': snapshot['view']},
                    {'assembly_id': snapshot['assembly_id']}, view_applied, owner=owner)
        if operation == 'document.save' and _capture_connector:
            from .connector_menu import flush_before_save
            captured = flush_before_save(self, owner, arguments, target, on_done,
                _capture_motion_view=False, _capture_shell=False, _capture_beam=False,
                _capture_dynamic=False, _capture_composite=False)
            if captured is not None: return captured
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
        from .assembly_pose_candidate import in_preparation
        for name, doc in documents.items():
            if in_preparation(doc):
                continue
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
                    dock.document_label.setText('대상 모델: ' + str(owner.doc.Label))
        if self.records:
            # Small project identity record, not a copy of native CAD/mesh arrays.
            try:
                if not self.project_path.exists() or load_json(self.project_path) != self.records:
                    save_json(self.project_path, self.records)
            except Exception as error:
                self.message.setText('모델 연결 정보를 저장하지 못했습니다: ' + str(error) +
                                     '\nCAD 모델과 이전 계산 결과는 그대로 남아 있습니다.')
        active = self.App.ActiveDocument
        binding = self.owners.get(active.Name) if active else None
        if binding:
            owner, _, broker = binding
            connected = broker.registered.is_set() and not broker.stop.is_set()
            self.identity.setText(str(active.Label) + '\n' +
                ('연결됨' if connected else '모델 연결을 기다리는 중'))
        else:
            connected = False
            self.identity.setText('CAD 모델을 만들거나 여세요.')
        waiting = self.pending is not None
        self.native_solver_button.setEnabled(active is not None and not waiting)
        self.native_post_button.setEnabled(active is not None and not waiting)
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
                raise ValueError('먼저 CAD 모델을 열고 연결하세요.')
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
            from .composite_controls import route as composite_route
            if composite_route(self, owner, selected.Name, export_only=export_only):
                return
            if selected.Name in owner.read_metadata().get('shells', {}):
                # Shell Run always uses the exact explicitly prepared/reviewed command.
                self.show_panel('shell', owner=owner)
                panel = self.panels[doc.Name]['shell'].widget().shell_controller
                if panel.buffer.analysis_id != selected.Name:
                    panel.reload(selected=selected.Name)
                panel.action('prepare' if export_only else 'run_prepared')
                return
            from .beam_menu import start_run
            if selected.Name in owner.read_metadata().get('beam_models', {}):
                start_run(self, owner, selected.Name, export_only=export_only)
                return
            if selected.Name in owner.read_metadata().get('dynamic_programs', {}):
                from .dynamic_menu import start_run as start_dynamic
                start_dynamic(self, owner, selected.Name, export_only=export_only)
                return
            owner.refresh()
            from .nonlinear_material import uses_custom_static
            from .freeze_contact_aster import uses_hard
            from .native_controls import transfer_pending
            if transfer_pending(self, owner):
                raise ValueError('변위 가져오기에 미저장 편집 또는 진행 중 요청이 있습니다. 초안을 저장하거나 편집을 취소하세요.')
            transfer = owner.read_metadata().get('displacement_transfers', {}).get(selected.Name)
            transfer_arguments = {}
            if transfer is not None:
                from caelab.storage import canonical_hash
                if (not isinstance(transfer.get('accepted'), dict) or
                        transfer['accepted'].get('draft_sha256') != canonical_hash(transfer.get('draft'))):
                    raise ValueError('가져올 변위를 확인하고 경계조건에 적용한 뒤 입력을 생성하세요.')
                transfer_arguments['source_reference'] = deepcopy(transfer['draft']['source_reference'])
            self.pending = {'command_id': 'C' + uuid.uuid4().hex, 'stage': 'command', 'retry': False,
                'document_id': owner.document_id, 'session_id': owner.session_id,
                'generation': owner.generation, 'export_only': bool(export_only),
                'operation': ('pre.initial.freeze' if selected.Name in owner.read_metadata().get('initial_fields', {}) else
                    'pre.contact.aster_freeze' if uses_hard(selected, owner.read_metadata()) else
                    'pre.pretension.freeze' if any(row.get('analysis_id') == selected.Name
                    for row in owner.read_metadata().get('pretension_sections', [])) else
                    'pre.contact.freeze' if uses_custom_static(selected, owner.read_metadata()) else 'pre.freeze'),
                'arguments': {'analysis_id': selected.Name, 'solver_id': solvers[0].Name, **transfer_arguments}}
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
                    self.message.setText('입력 생성 완료. 원 모델 연결을 확인한 뒤 같은 요청을 다시 조회하세요.')
                    self.pending['retry']=True
                    return
                path=(owner.export_root/relative).resolve(strict=True)
                if not path.is_relative_to(owner.export_root.resolve()):
                    raise ValueError('생성된 입력 파일의 경로가 현재 모델의 저장 폴더를 벗어났습니다.')
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
            detail = error.get('message', '계산을 시작하지 않았습니다. 입력과 이전 결과는 남아 있습니다.')
            # Keep the original diagnostic in the command receipt. The work
            # area tells users how to reconnect the condition's selected face.
            detail = detail.replace('UNTRACKED_TARGET: explicitly confirm/repair this condition target',
                '적용 면을 확인하세요. 모델 트리에서 해당 하중·구속을 열고 적용 면을 다시 지정하세요.')
            self.message.setText(command_status_text('pre.freeze', state) + ': ' +
                detail)
            self.pending = None
        else:
            self.message.setText(command_status_text('pre.freeze', state) +
                '\n대기 중에는 취소할 수 있습니다. 파일을 생성하기 시작한 뒤에는 완료될 때까지 기다리세요.')

    def show_export(self, manifest):
        from caelab.storage import load_json
        if load_json(manifest).get('kind') == 'freecad-beam-frozen':
            from .beam_menu import show_input
        elif (Path(manifest).parent/'mesh.json').is_file() and load_json(Path(manifest).parent/'mesh.json').get('dynamic'):
            from .dynamic_menu import show_input
        else:
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

    def open_motion_data(self, path, on_done, document=None):
        """Keep the exact sampled CSV and Data owner if save or launch fails."""
        from copy import deepcopy
        from .motion_path import save_data_document
        config = deepcopy(self.config)
        service_url = (document or {}).get('_motion_service_url', config['service_url'])
        client = self.client if service_url == config['service_url'] else Client(service_url)
        snapshot = deepcopy(path); retained = {'document': document}
        def create():
            try:
                saved = save_data_document(client, snapshot, document=document,
                    on_created=lambda value: retained.update(document=value))
                return {'document': saved}
            except Exception as error: return {**retained, 'error': str(error)}
        def opened(reply):
            if reply.get('document'): reply['document'] = {**reply['document'], '_motion_service_url': service_url}
            if reply.get('error'):
                on_done(reply); return
            try:
                environment = os.environ.copy()
                for key in ('PYTHONHOME', 'PYTHONPATH', 'QT_PLUGIN_PATH', 'QML2_IMPORT_PATH', 'LD_LIBRARY_PATH'):
                    environment.pop(key, None)
                process = subprocess.Popen([config['python'], '-m', 'apps.research.desktop', '--service',
                    service_url, 'data', '--document-id', reply['document']['id']],
                    cwd=str(Path(__file__).resolve().parents[2]), env=environment)
                on_done({**reply, 'status': 'LAUNCH_REQUESTED', 'pid': process.pid})
            except Exception as error: on_done({**reply, 'error': str(error)})
        self.request('motion-data:' + uuid.uuid4().hex, create, opened)

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

    def open_structural_displacement_source(self, reference):
        exact = deepcopy(reference)
        def resolved(value):
            if value.get('reference') != exact:
                raise ValueError('선택한 저장 변위 원본과 다른 결과입니다.')
            post = value['post_input']
            command = [self.config['python'], '-m', 'apps.research.desktop', '--service',
                       self.config['service_url'], 'post', '--input-id', post['id']]
            environment = os.environ.copy()
            for key in ('PYTHONHOME','PYTHONPATH','QT_PLUGIN_PATH','QML2_IMPORT_PATH','LD_LIBRARY_PATH'):
                environment.pop(key, None)
            subprocess.Popen(command, cwd=str(Path(__file__).resolve().parents[2]), env=environment)
        self.request('displacement-source:'+uuid.uuid4().hex,
                     lambda: self.client.structural_displacement_post_input(exact), resolved)

    def show_panel(self, kind, *, owner=None):
        owner = owner or self.active_owner()
        panels = self.panels.setdefault(owner.doc.Name, {})
        existing = kind in panels
        if kind not in panels:
            from importlib import import_module
            modules = {'parameters': ('parameter_panel', owner.parameters, '설계 변수'),
                       'motion': ('motion_panel', owner.motion, '조립 운동'),
                       'shell': ('shell_panel', owner.shell, '판재 셸')}
            if kind == 'composite':
                from .composite_controls import make_panel
                widget = make_panel(self, owner)
                title = '적층 셸'
            elif kind == 'structural_transfer':
                from .structural_transfer_panel import make_panel
                widget = make_panel(self, owner)
                owner._structural_transfer_panel = widget
                title = '변위 가져오기'
            elif kind == 'beam':
                from .beam_menu import make_panel
                widget = make_panel(self, owner)
                title = '빔 설정'
            elif kind == 'dynamic':
                from .dynamic_menu import make_panel
                widget = make_panel(self, owner)
                title = '동해석 설정'
            elif kind == 'research':
                from .research_panel import make_panel
                submit = lambda operation, args, target=None, on_done=None: self.submit_native(operation, args, target, on_done, owner=owner)
                widget = make_panel(self.QtWidgets, self.QtCore, owner.research, submit, self.create_numerical_plan)
                title = '수치 연구'
            elif kind == 'assembly_candidate':
                from .assembly_pose_panel import make_panel
                widget = make_panel(self, owner)
                title = '선택 자세 해석'
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
                                     read=lambda: dict(owner.descriptor(), session_id=owner.session_id),
                                     open_data=self.open_motion_data)
                    from .assembly_pose_panel import attach_motion
                    attach_motion(self, owner, widget.motion_controller)
                else:
                    widget = factory(self.QtWidgets, self.QtCore, editor, submit)
                    if kind == 'shell': widget.shell_controller.attach(self)
            if kind == 'structural_transfer':
                class TransferTaskDock(self.QtWidgets.QDockWidget):
                    def closeEvent(task_dock, event):
                        if getattr(task_dock, '_approved_task_close', False):
                            super().closeEvent(event)
                            return
                        event.ignore()
                        task_dock.widget().request_close()
                dock = TransferTaskDock(title, self.Gui.getMainWindow())
            else:
                dock = self.QtWidgets.QDockWidget(title, self.Gui.getMainWindow())
            dock.setToolTip(owner.doc.Label)
            dock.document_label = self.QtWidgets.QLabel('대상 모델: ' + str(owner.doc.Label))
            dock.document_label.setWordWrap(True)
            widget.layout().insertWidget(0, dock.document_label)
            dock.setObjectName('CAELab-' + kind + '-' + owner.document_id)
            dock.setWidget(widget); dock.resize(720, 520)
            self.Gui.getMainWindow().addDockWidget(self.QtCore.Qt.RightDockWidgetArea, dock)
            panels[kind] = dock
            dock.visibilityChanged.connect(
                lambda visible, dock=dock: self._editor_dock_visibility(dock, visible))
            if kind == 'structural_transfer':
                dock.visibilityChanged.connect(lambda visible, dock=dock: self._transfer_task_visibility(dock, visible))
        if existing and kind in ('structural_transfer', 'dynamic'):
            panels[kind].widget().refresh_context()
        self._activate_editor_dock(panels[kind])
        panels[kind].show(); panels[kind].raise_()
        if not existing:
            main = self.Gui.getMainWindow()
            width = min(520, max(400, int(main.width() * .46)))
            main.resizeDocks([panels[kind]], [width], self.QtCore.Qt.Horizontal)
        if kind == 'structural_transfer':
            self._transfer_task_visibility(panels[kind], True)
        return panels[kind].widget()

    def _activate_editor_dock(self, selected):
        """Give one current editing task the dock area without discarding drafts."""
        if getattr(self, '_switching_editor_dock', False):
            return
        self._switching_editor_dock = True
        try:
            for panels in self.panels.values():
                for dock in panels.values():
                    if dock is not selected and dock.isVisible():
                        dock.hide()
            main = self.Gui.getMainWindow()
            retained = getattr(self, '_editor_hidden_auxiliaries', [])
            for dock in [self.dock]:
                if dock.isVisible():
                    if dock not in retained:
                        retained.append(dock)
                    dock.hide()
            self._editor_hidden_auxiliaries = retained
            for dock in main.findChildren(self.QtWidgets.QDockWidget):
                if dock.objectName() == 'Model':
                    dock.show()
        finally:
            self._switching_editor_dock = False

    def _editor_dock_visibility(self, dock, visible):
        if getattr(self, '_switching_editor_dock', False) or self.closed:
            return
        if visible:
            self._activate_editor_dock(dock)
            return
        def settled():
            if self.closed or any(item.isVisible() for panels in self.panels.values() for item in panels.values()):
                return
            for auxiliary in getattr(self, '_editor_hidden_auxiliaries', []):
                try:
                    auxiliary.show()
                except RuntimeError:
                    pass
            self._editor_hidden_auxiliaries = []
        self.QtCore.QTimer.singleShot(0, settled)

    def structural_transfer_view_actions(self):
        return [(item.windowTitle(), item.toggleViewAction()) for item in
                self.Gui.getMainWindow().findChildren(self.QtWidgets.QDockWidget)
                if item.objectName() == 'Model']

    def _transfer_task_visibility(self, dock, visible):
        tasks = getattr(self, '_transfer_tasks', None)
        if tasks is None:
            tasks = self._transfer_tasks = set()
        if visible and dock not in tasks:
            first = not tasks
            tasks.add(dock)
            if first:
                self._transfer_hidden_docks = [item for item in [self.dock] if item.isVisible()]
                self._transfer_hidden_overlay = None
                for item in self._transfer_hidden_docks:
                    item.hide()
                epoch = self._transfer_focus_epoch = getattr(self, '_transfer_focus_epoch', 0) + 1
                def settled():
                    if (not self.closed and self._transfer_tasks and self._transfer_focus_epoch == epoch):
                        self._hide_structural_transfer_overlay()
                self.QtCore.QTimer.singleShot(0, settled)
        elif not visible and dock in tasks:
            tasks.remove(dock)
            if not tasks and not self.closed:
                self.restore_structural_transfer_layout()

    def _hide_structural_transfer_overlay(self):
        active = self.Gui.activeDocument()
        if self.Gui.Control.activeDialog() or (active and active.getInEdit()):return
        for overlay in self.Gui.getMainWindow().findChildren(self.QtWidgets.QWidget):
            if overlay.objectName() != 'OverlayRight' or not overlay.isVisible():continue
            docks = overlay.findChildren(self.QtWidgets.QDockWidget)
            if docks and all(item.objectName() == 'Tasks' for item in docks):
                # FreeCAD 1.1's overlay uses splitter state rather than QAction's
                # checked bit. Its standard command closes the overlay itself.
                self._transfer_hidden_overlay = overlay
                self.Gui.runCommand('Std_DockOverlayToggleRight', 0)
            return

    def restore_structural_transfer_layout(self):
        self._transfer_focus_epoch = getattr(self, '_transfer_focus_epoch', 0) + 1
        for item in reversed(getattr(self, '_transfer_hidden_docks', [])):
            try:item.show()
            except RuntimeError:pass
        self._transfer_hidden_docks = []
        overlay = getattr(self, '_transfer_hidden_overlay', None)
        if overlay is not None:
            try:
                if not overlay.isVisible():
                    self.Gui.runCommand('Std_DockOverlayToggleRight', 0)
                    # Native Showing is animated; accepted Close must see the
                    # restored visibility before FreeCAD saves its layout.
                    overlay.show()
            except RuntimeError:pass
        self._transfer_hidden_overlay = None

    def close_structural_transfer(self, owner):
        dock = self.panels.get(owner.doc.Name, {}).get('structural_transfer')
        if dock is not None:
            def close_approved():
                if self.closed:return
                dock._approved_task_close = True
                try:dock.close()
                except RuntimeError:pass  # The document may have closed while its save completed.
                finally:dock._approved_task_close = False
            self.QtCore.QTimer.singleShot(0, close_approved)

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
            from .connector_menu import rebind as rebind_connector
            for name, (previous_owner, _, _) in previous:
                if name in self.owners: rebind_connector(self, previous_owner, self.owners[name][0])
            self.message.setText('모델을 다시 연결했습니다.')
        def request_context():
            from .native_controls import _motion_controller, transfer_token
            from .beam_menu import editor_token as beam_token
            from .dynamic_menu import editor_token as dynamic_token
            from .shell_controls import editor_token as shell_token
            from .composite_controls import editor_token as composite_token
            from .connector_menu import editor_token as connector_token
            versions = {name: ((controller.editor_token() if (controller := _motion_controller(self, owner)) is not None else None), beam_token(self, owner), shell_token(self, owner), dynamic_token(self, owner), composite_token(self, owner), connector_token(self, owner), transfer_token(self, owner))
                        for name, (owner, _, _) in self.owners.items()}
            def accepted(context):
                for name, (owner, _, _) in self.owners.items():
                    controller = _motion_controller(self, owner)
                    current = ((controller.editor_token() if controller is not None else None), beam_token(self, owner), shell_token(self, owner), dynamic_token(self, owner), composite_token(self, owner), connector_token(self, owner), transfer_token(self, owner))
                    if name not in versions or current != versions[name]:
                        self.message.setText('다시 연결하는 동안 편집이 바뀌었습니다. 현재 모델과 편집을 유지합니다.'); return
                connected(context)
            self.request('reconnect', self.client.desktop_context, accepted)
        guards = getattr(self, 'guards', None)
        if guards is not None: guards.prepare_reconnect([row[0] for row in self.owners.values()], request_context)
        else: request_context()

    def close(self):
        if self.closed:
            return
        self.closed = True
        self.restore_structural_transfer_layout()
        self.timer.stop()
        for owner, dispatch, broker in self.owners.values():
            dispatch.close()
