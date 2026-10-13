"""Native local operator connection editor; no credentials or model requests."""
from copy import deepcopy
from pathlib import Path
import json

from PySide6.QtCore import Qt, QTimer, QThreadPool
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QVBoxLayout, QHBoxLayout,
    QFormLayout, QLabel, QPushButton, QComboBox, QFileDialog, QCheckBox, QTableWidget,
    QTableWidgetItem, QHeaderView, QTabWidget, QWidget, QListWidget, QListWidgetItem, QPlainTextEdit)

from caelab import expert_connection as setup


def is_example_role(definition):
    """Recognize the actual shipped definition, never an ID/name alone."""
    try:
        path = Path(__file__).resolve().parents[2] / 'examples' / 'workbench_experts.json'
        examples = setup.roles(setup.read_config(path)[0])
    except (OSError, ValueError):
        return False
    return any(definition == row for row in examples)


class RoleDetailsDialog(QDialog):
    """Read only the selected definition; no qualification or corpus is inferred."""
    def __init__(self, definition, *, model=None, provider=None, parent=None):
        super().__init__(parent)
        self.definition = deepcopy(definition)
        self.setWindowTitle('역할 상세')
        self.resize(660, 520)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        name = QLabel(definition.get('label') or definition.get('id', ''))
        name.setTextFormat(Qt.TextFormat.PlainText)
        name.setWordWrap(True)
        form.addRow('역할', name)
        self.definition_kind = QLabel('프로젝트 예제 역할 정의' if is_example_role(definition)
                                     else '선택한 역할 정의')
        self.definition_kind.setToolTip('역할 지시와 자료 분류·도구 설정입니다. 전문자료집이나 분야 평가 결과를 포함하지 않습니다.')
        form.addRow('정의', self.definition_kind)
        self.model_label = QLabel(model or '미설정')
        self.model_label.setTextFormat(Qt.TextFormat.PlainText)
        self.model_label.setWordWrap(True)
        self.model_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.model_label.setToolTip('선택한 모델 설정입니다. 인증과 해당 모델 사용 권한은 별도 확인이 필요합니다.')
        form.addRow('모델', self.model_label)
        route = QLabel('OpenScience / 기존 ChatGPT 로그인 경로' if provider == 'openscience'
                       else provider or '미연결')
        route.setTextFormat(Qt.TextFormat.PlainText)
        route.setWordWrap(True)
        form.addRow('연결', route)
        layout.addLayout(form)
        layout.addWidget(QLabel('역할 지시'))
        self.instructions = QPlainTextEdit()
        self.instructions.setReadOnly(True)
        self.instructions.setPlainText(definition.get('instructions', ''))
        layout.addWidget(self.instructions, 2)
        tabs = QTabWidget()
        self.collections, self.tools = QListWidget(), QListWidget()
        self.collections.addItems(definition.get('collections', []) or ['지정 없음'])
        self.tools.addItems(definition.get('tools', []) or ['지정 없음'])
        self.collections.setToolTip('분류명만 표시합니다. 실제 자료 내용은 Expert의 Sources에서 확인하세요.')
        self.tools.setToolTip('역할에 설정된 도구 목록입니다. 실제 사용은 요청 권한과 예산에 따릅니다.')
        tabs.addTab(self.collections, '자료 분류 (내용 미확인)')
        tabs.addTab(self.tools, '허용 도구')
        layout.addWidget(tabs, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


class ConnectionDialog(QDialog):
    def __init__(self, client, parent=None, *, config_path=None):
        super().__init__(parent)
        self.client = client
        self.path = Path(config_path) if config_path is not None else setup.default_config_path()
        self.original, self.expected_sha, self.definitions = {}, None, []
        self.loaded = False
        self._workers, self._busy, self._closed = [], False, False
        self._pending_sha = None
        self.setWindowTitle('Expert connection')
        self.resize(780, 650)
        layout = QVBoxLayout(self)
        self.service = QLabel(client.url)
        self.service.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.service)
        self.message = QLabel('Reading current service and local settings…')
        self.message.setWordWrap(True)
        layout.addWidget(self.message)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)
        connection = QWidget()
        form = QFormLayout(connection)
        self.enabled = QCheckBox('기존 OpenScience 설정 사용')
        self.enabled.setToolTip('OpenScience는 오픈소스 실행 도구입니다. 기존 ChatGPT 로그인 경로를 사용하며, 인증과 모델 사용 권한은 별도로 확인합니다.')
        form.addRow(self.enabled)
        self.profile, self.runtime, self.model = QComboBox(), QComboBox(), QComboBox()
        for combo in (self.profile, self.runtime, self.model):
            combo.setEditable(True)
            combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            combo.setMinimumContentsLength(25)
        for label, combo in (('Profile', self.profile), ('Runtime', self.runtime)):
            row = QHBoxLayout()
            row.addWidget(combo, 1)
            button = QPushButton('Browse…')
            button.clicked.connect(lambda checked=False, combo=combo: self.choose_folder(combo))
            row.addWidget(button)
            form.addRow(label, row)
        self.model.lineEdit().setPlaceholderText('openai-codex/model-name')
        form.addRow('Default model', self.model)
        check_files = QPushButton('Check local setup')
        check_files.clicked.connect(self.inspect_files)
        form.addRow(check_files)
        self.roles = QTableWidget(0, 3)
        self.roles.setHorizontalHeaderLabels(['Role', 'Model override', '정의'])
        self.roles.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.roles.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.roles.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.roles.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.roles.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.roles.itemSelectionChanged.connect(self._role_selection_changed)
        self.roles.cellDoubleClicked.connect(lambda row, column: self.show_role_details() if column != 1 else None)
        form.addRow(self.roles)
        role_buttons = QHBoxLayout()
        choose = QPushButton('Choose roles…')
        example = QPushButton('Use example roles')
        choose.clicked.connect(self.choose_roles)
        example.clicked.connect(self.example_roles)
        role_buttons.addWidget(choose)
        role_buttons.addWidget(example)
        self.role_details = QPushButton('역할 상세…')
        self.role_details.setEnabled(False)
        self.role_details.clicked.connect(self.show_role_details)
        role_buttons.addWidget(self.role_details)
        role_buttons.addStretch()
        form.addRow(role_buttons)
        self.tabs.addTab(connection, 'Model and roles')
        scope = QWidget()
        permissions = QVBoxLayout(scope)
        self.question = QCheckBox('Allow external question transmission')
        self.results = QCheckBox('Allow explicitly attached result transmission')
        self.public = QCheckBox('Allow explicitly requested public literature searches')
        for widget in (self.question, self.results, self.public):
            permissions.addWidget(widget)
        permissions.addWidget(QLabel('Permitted source collections'))
        self.collections = QListWidget()
        permissions.addWidget(self.collections, 1)
        note = QLabel('Each discussion still requires its own explicit question, source and result permission.')
        note.setWordWrap(True)
        permissions.addWidget(note)
        self.tabs.addTab(scope, 'Transmission')
        status_tab = QWidget()
        status_layout = QVBoxLayout(status_tab)
        self.checks = QTableWidget(6, 2)
        self.checks.setHorizontalHeaderLabels(['Check', 'Status'])
        self.checks.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.checks.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.checks.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        status_layout.addWidget(self.checks)
        self.config_label = QLabel()
        self.config_label.setWordWrap(True)
        status_layout.addWidget(self.config_label)
        choose_config = QPushButton('Choose service config…')
        choose_config.clicked.connect(self.choose_config)
        status_layout.addWidget(choose_config)
        self.tabs.addTab(status_tab, 'Status')
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Apply | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Apply).setText('Apply connection')
        self.buttons.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(self.apply)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self.retry = QTimer(self)
        self.retry.setInterval(1000)
        self.retry.timeout.connect(self.activate_saved)
        self.refresh()

    def _call(self, function, success):
        if self._closed or self._busy:
            return False
        from .expert_window import _Call
        self._busy = True
        self.tabs.setEnabled(False)
        self.buttons.button(QDialogButtonBox.StandardButton.Apply).setEnabled(False)
        worker = _Call(function)
        self._workers.append(worker)
        def done(value, error):
            self._workers.remove(worker)
            self._busy = False
            if self._closed:
                return
            self.tabs.setEnabled(self._pending_sha is None)
            if error:
                self.retry.stop()
                self.message.setText('Connection was not applied. ' + error)
            else:
                success(value)
            self.buttons.button(QDialogButtonBox.StandardButton.Apply).setEnabled(self.loaded)
        worker.signals.finished.connect(done, Qt.ConnectionType.QueuedConnection)
        QThreadPool.globalInstance().start(worker)
        return True

    def refresh(self):
        if self._closed or self._busy:
            return False
        # Destination, content and CAS hash must come from one verified read.
        # Failed reads must never leave the previous file eligible for Apply.
        self.loaded = False
        self.original, self.expected_sha, self.definitions = {}, None, []
        path = self.path
        def read():
            service = self.client.expert_connection()
            if path is None:
                raise ValueError('Choose the local configuration used by this service')
            if Path(service.get('operator_config_path') or '').resolve() != path.resolve():
                raise ValueError('Choose this service’s local operator configuration; no file was changed')
            config, sha = setup.read_config(path)
            try:
                registry = self.client.request('/api/workbench/assist',
                                               {'operation': 'experts.list', 'arguments': {}})
            except Exception:
                # Local replacement remains possible when old legacy roles or
                # optional packages cannot initialize the current assistance.
                registry = {'connection_setup_error': True}
            return service, registry, config, sha, setup.discover()
        def opened(payload):
            service, registry, config, sha, locations = payload
            self.original, self.expected_sha = config, sha
            runtime = config.get('runtime') or {}
            definitions = config.get('experts', [])
            # A legacy external roles file is not reread under the config hash.
            self.definitions = (setup.roles(definitions) if isinstance(definitions, (list, dict))
                                else deepcopy(registry.get('experts', [])))
            for combo, values, chosen in (
                (self.profile, locations['profiles'], runtime.get('openscience_profile')),
                (self.runtime, locations['runtimes'], runtime.get('openscience_runtime_prefix'))):
                combo.clear()
                combo.addItems(values)
                combo.setEditText(chosen or (values[0] if len(values) == 1 else ''))
            self.model.clear()
            models = list(dict.fromkeys([x for x in [runtime.get('model')] +
                [row.get('model') for row in (runtime.get('expert_models') or {}).values()] if x]))
            self.model.addItems(models)
            self.model.setEditText(runtime.get('model') or '')
            self.enabled.setChecked(runtime.get('provider') == 'openscience')
            self._populate_roles(runtime.get('expert_models') or {})
            policy = runtime.get('transmission') or {}
            self.question.setChecked(bool(policy.get('allow_external_model') and policy.get('allow_question')))
            self.results.setChecked(bool(policy.get('allow_results')))
            self.public.setChecked(bool(policy.get('allow_public_search')))
            self._populate_collections(policy.get('collections', []))
            self.config_label.setText(str(path))
            self.loaded = True
            self.message.setText('Choose replacement roles; current roles could not be loaded.'
                                 if registry.get('connection_setup_error') else
                                 'Local setup only. Authentication and model entitlement have not been checked.')
            self._show_status(service, registry)
        return self._call(read, opened)

    def _show_status(self, service, registry):
        missing = [x for x in registry.get('packages', {}).get('missing_dependencies', [])
                   if x.get('extra') in ('assist-core', 'mcp')]
        rows = [('Service configuration', service.get('configuration', 'UNKNOWN')),
                ('Python packages', 'MISSING_DEPENDENCIES' if missing else
                 'IMPORTS_AVAILABLE' if registry.get('packages') else 'NOT_CHECKED'),
                ('Profile/runtime', 'NOT_CHECKED'),
                ('Authentication', 'UNVERIFIED'), ('Model entitlement', 'UNVERIFIED'),
                ('Inference check', 'NOT_RUN')]
        for index, (key, value) in enumerate(rows):
            self.checks.setItem(index, 0, QTableWidgetItem(key))
            self.checks.setItem(index, 1, QTableWidgetItem(value))

    def _populate_roles(self, overrides=None):
        overrides = overrides or {}
        self.roles.setRowCount(len(self.definitions))
        for index, role in enumerate(self.definitions):
            item = QTableWidgetItem(role.get('label', role['id']))
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            item.setToolTip(role.get('instructions', ''))
            self.roles.setItem(index, 0, item)
            kind = QTableWidgetItem('예제' if is_example_role(role) else '선택한 정의')
            kind.setFlags(kind.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.roles.setItem(index, 2, kind)
            combo = QComboBox()
            combo.setEditable(True)
            combo.addItem('')
            combo.addItems([self.model.itemText(i) for i in range(self.model.count())])
            combo.setEditText(overrides.get(role['id'], {}).get('model', ''))
            combo.lineEdit().setPlaceholderText('Default model')
            self.roles.setCellWidget(index, 1, combo)
        self._role_selection_changed()

    def _role_selection_changed(self):
        if hasattr(self, 'role_details'):
            self.role_details.setEnabled(0 <= self.roles.currentRow() < len(self.definitions))

    def show_role_details(self):
        row = self.roles.currentRow()
        if self._closed or self._busy or not 0 <= row < len(self.definitions):
            return False
        override = self.roles.cellWidget(row, 1).currentText().strip()
        model = (override or self.model.currentText().strip()) if self.enabled.isChecked() else None
        dialog = RoleDetailsDialog(self.definitions[row], model=model,
                                   provider='openscience' if self.enabled.isChecked() else None, parent=self)
        dialog.exec()
        return True

    def _populate_collections(self, selected):
        self.collections.clear()
        names = sorted(set(selected) | {name for row in self.definitions for name in row.get('collections', [])})
        for name in names:
            item = QListWidgetItem(name)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if name in selected else Qt.CheckState.Unchecked)
            self.collections.addItem(item)

    def _selected_collections(self):
        return [self.collections.item(i).text() for i in range(self.collections.count())
                if self.collections.item(i).checkState() == Qt.CheckState.Checked]

    def choose_folder(self, combo):
        path = QFileDialog.getExistingDirectory(self, 'Select existing ' + ('profile' if combo is self.profile else 'runtime'),
                                                combo.currentText())
        if path:
            combo.setEditText(path)
            self.inspect_files()

    def inspect_files(self):
        profile, runtime = self.profile.currentText(), self.runtime.currentText()
        def show(value):
            self.checks.setItem(2, 1, QTableWidgetItem(value['status']))
            self.message.setText(value.get('reason', ''))
            try:
                setup.powershell_command(Path(__file__).resolve().parents[2] / 'caelab/assist/openscience_host.ps1')
            except ValueError as error:
                self.message.setText(str(error))
                self.checks.setItem(2, 1, QTableWidgetItem('HOST_UNAVAILABLE'))
            for model in value.get('models', []):
                if self.model.findText(model) < 0:
                    self.model.addItem(model)
        return self._call(lambda: setup.installation(profile, runtime), show)

    def choose_roles(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Choose Expert roles', '', 'Role definitions (*.json)')
        if path:
            self._read_roles(Path(path))

    def example_roles(self):
        self._read_roles(Path(__file__).resolve().parents[2] / 'examples' / 'workbench_experts.json')

    def _read_roles(self, path):
        try:
            definitions = setup.roles(setup.read_config(path)[0])
        except (OSError, ValueError) as error:
            self.message.setText('Roles were not changed. ' + str(error))
            return
        selected = self._selected_collections()
        self.definitions = definitions
        self._populate_roles()
        self._populate_collections(selected)
        self.message.setText('Selected roles are pending Apply; the discussion is unchanged.')

    def choose_config(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Choose this service’s operator config', '', 'Operator config (*.json)')
        if path:
            self.path = Path(path)
            self.refresh()

    def apply(self):
        if not self.loaded:
            return
        if self._pending_sha:
            return self.activate_saved()
        original, path, expected = deepcopy(self.original), self.path, self.expected_sha
        values = dict(enabled=self.enabled.isChecked(), profile=self.profile.currentText(),
            runtime_prefix=self.runtime.currentText(), model=self.model.currentText().strip(),
            definitions=deepcopy(self.definitions), role_models={
                row['id']: self.roles.cellWidget(i, 1).currentText().strip()
                for i, row in enumerate(self.definitions)}, allow_question=self.question.isChecked())
        collections, results, public = self._selected_collections(), self.results.isChecked(), self.public.isChecked()
        def save():
            candidate = setup.proposal(original, **values)
            if candidate.get('runtime'):
                candidate['runtime']['transmission'].update(
                    collections=collections, allow_results=results, allow_public_search=public)
            sha = setup.save_local(path, expected, candidate)
            return candidate, sha
        def saved(payload):
            self.original, self.expected_sha = payload
            self._pending_sha = self.expected_sha
            self.message.setText('Settings saved locally. Applying to this service…')
            QTimer.singleShot(0, self.activate_saved)
        return self._call(save, saved)

    def activate_saved(self):
        if not self._pending_sha:
            return
        def received(value):
            if value['status'] == 'DEFERRED':
                self.message.setText('Settings saved. Current work continues; connection will apply when it finishes.')
                self.retry.start()
            elif value['status'] == 'APPLIED':
                self.retry.stop()
                self._pending_sha = None
                self.tabs.setEnabled(True)
                self.message.setText('Connection applied. Question and source permissions in the discussion are unchanged.')
                self.checks.setItem(0, 1, QTableWidgetItem(value['configuration']))
                self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('Close')
            else:
                self.retry.stop()
                self.message.setText(value.get('reason', value['status']))
        return self._call(lambda: self.client.reload_expert_connection(self._pending_sha), received)

    def reject(self):
        self._closed = True
        self.retry.stop()
        for worker in self._workers:
            worker.abandon()
        super().reject()
