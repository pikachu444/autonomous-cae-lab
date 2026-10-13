"""Native local operator connection editor; no credentials or model requests."""
from copy import deepcopy
from pathlib import Path
import json

from PySide6.QtCore import Qt, QTimer, QThreadPool
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QVBoxLayout, QHBoxLayout,
    QFormLayout, QLabel, QPushButton, QComboBox, QFileDialog, QCheckBox, QTableWidget,
    QTableWidgetItem, QHeaderView, QTabWidget, QWidget, QListWidget, QListWidgetItem)

from caelab import expert_connection as setup


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
        self.enabled = QCheckBox('Use existing OpenScience subscription profile')
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
        self.roles = QTableWidget(0, 2)
        self.roles.setHorizontalHeaderLabels(['Role', 'Model override'])
        self.roles.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.roles.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        form.addRow(self.roles)
        role_buttons = QHBoxLayout()
        choose = QPushButton('Choose roles…')
        example = QPushButton('Use example roles')
        choose.clicked.connect(self.choose_roles)
        example.clicked.connect(self.example_roles)
        role_buttons.addWidget(choose)
        role_buttons.addWidget(example)
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
        path = self.path
        def read():
            service = self.client.expert_connection()
            registry = self.client.request('/api/workbench/assist',
                                           {'operation': 'experts.list', 'arguments': {}})
            if path is None:
                raise ValueError('Choose the local configuration used by this service')
            if Path(service.get('operator_config_path') or '').resolve() != path.resolve():
                raise ValueError('Choose this service’s local operator configuration; no file was changed')
            config, sha = setup.read_config(path)
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
            self.message.setText('Local setup only. Authentication and model entitlement have not been checked.')
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
            combo = QComboBox()
            combo.setEditable(True)
            combo.addItem('')
            combo.addItems([self.model.itemText(i) for i in range(self.model.count())])
            combo.setEditText(overrides.get(role['id'], {}).get('model', ''))
            combo.lineEdit().setPlaceholderText('Default model')
            self.roles.setCellWidget(index, 1, combo)

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
