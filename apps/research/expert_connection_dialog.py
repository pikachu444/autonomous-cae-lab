"""Native local operator connection editor; no credentials or model requests."""
from copy import deepcopy
from pathlib import Path
import json

from PySide6.QtCore import Qt, QTimer, QThreadPool
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QVBoxLayout, QHBoxLayout,
    QFormLayout, QLabel, QPushButton, QComboBox, QFileDialog, QCheckBox, QTableWidget,
    QTableWidgetItem, QHeaderView, QTabWidget, QWidget, QListWidget, QListWidgetItem, QPlainTextEdit,
    QScrollArea)

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
        self._saved = False
        self._save_started = False
        self.setWindowTitle('Expert 연결 설정')
        self.resize(900, 650)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(10)
        title = QLabel('기존 OpenScience 연결')
        title.setProperty('appearanceRole', 'title')
        layout.addWidget(title)
        boundary = QLabel('설정 적용은 로그인, 모델 사용 권한, 역할의 전문성을 검증하지 않습니다.')
        boundary.setProperty('appearanceRole', 'muted')
        boundary.setWordWrap(True)
        layout.addWidget(boundary)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)

        connection = QWidget()
        connection_layout = QVBoxLayout(connection)
        connection_layout.setSpacing(12)
        self.enabled = QCheckBox('기존 OpenScience 설정 사용')
        self.enabled.setToolTip('기존 ChatGPT 로그인 경로를 사용합니다. 이 창에서는 인증 정보를 읽거나 모델을 호출하지 않습니다.')
        connection_layout.addWidget(self.enabled)
        explanation = QLabel('이미 준비한 로컬 폴더를 선택하세요. 폴더 확인은 파일과 실행 도구의 일치 여부만 확인합니다.')
        explanation.setWordWrap(True)
        connection_layout.addWidget(explanation)
        form = QFormLayout()
        form.setVerticalSpacing(10)
        self.profile, self.runtime, self.model = QComboBox(), QComboBox(), QComboBox()
        self.connection_inputs = []
        for combo in (self.profile, self.runtime, self.model):
            combo.setEditable(True)
            combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            combo.setMinimumContentsLength(20)
            self.connection_inputs.append(combo)
        self.profile.setToolTip('기존 OpenScience 로그인 경로와 로컬 설정을 보관하는 폴더입니다.')
        self.runtime.setToolTip('프로젝트에서 준비한 OpenScience 실행 도구가 설치된 폴더입니다.')
        for label, combo in (('로그인 설정 폴더', self.profile), ('실행 도구 폴더', self.runtime)):
            row = QHBoxLayout()
            row.addWidget(combo, 1)
            button = QPushButton('폴더 선택…')
            button.clicked.connect(lambda checked=False, combo=combo: self.choose_folder(combo))
            row.addWidget(button)
            self.connection_inputs.append(button)
            form.addRow(label, row)
        self.model.lineEdit().setPlaceholderText('설정에 있는 모델 이름 입력')
        self.model.setToolTip('모델 이름을 그대로 사용합니다. 목록에 있다고 해당 모델의 사용 권한이 확인된 것은 아닙니다.')
        form.addRow('기본 모델', self.model)
        connection_layout.addLayout(form)
        self.check_files = QPushButton('폴더 확인')
        self.check_files.clicked.connect(self.inspect_files)
        self.connection_inputs.append(self.check_files)
        connection_layout.addWidget(self.check_files, 0, Qt.AlignmentFlag.AlignLeft)
        self.local_check = QLabel('폴더 확인 전')
        self.local_check.setWordWrap(True)
        connection_layout.addWidget(self.local_check)
        connection_layout.addStretch()
        self.tabs.addTab(connection, '연결 설정')

        role_page = QWidget()
        role_layout = QVBoxLayout(role_page)
        self.role_model_summary = QLabel()
        self.role_model_summary.setTextFormat(Qt.TextFormat.PlainText)
        self.role_model_summary.setWordWrap(True)
        role_layout.addWidget(self.role_model_summary)
        role_note = QLabel('모델을 따로 지정하지 않으면 기본 모델을 사용합니다. 예제는 역할 지시이며 전문 자료나 평가 결과가 아닙니다.')
        role_note.setWordWrap(True)
        role_layout.addWidget(role_note)
        self.roles = QTableWidget(0, 3)
        self.roles.setHorizontalHeaderLabels(['역할', '역할별 모델', '역할 정의'])
        self.roles.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.roles.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.roles.verticalHeader().hide()
        self.roles.verticalHeader().setDefaultSectionSize(34)
        self.roles.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.roles.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.roles.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.roles.itemSelectionChanged.connect(self._role_selection_changed)
        self.roles.cellDoubleClicked.connect(lambda row, column: self.show_role_details() if column != 1 else None)
        role_layout.addWidget(self.roles, 1)
        role_buttons = QHBoxLayout()
        choose = QPushButton('역할 파일 불러오기…')
        example = QPushButton('예제 역할 불러오기')
        choose.clicked.connect(self.choose_roles)
        example.clicked.connect(self.example_roles)
        role_buttons.addWidget(choose)
        role_buttons.addWidget(example)
        role_buttons.addStretch()
        self.role_details = QPushButton('선택 역할 상세…')
        self.role_details.setEnabled(False)
        self.role_details.clicked.connect(self.show_role_details)
        role_buttons.addWidget(self.role_details)
        role_layout.addLayout(role_buttons)
        self.tabs.addTab(role_page, '역할')

        scope = QWidget()
        permissions = QVBoxLayout(scope)
        permissions.setSpacing(12)
        note = QLabel('이 연결에서 허용할 범위입니다. 실제 토론에서는 질문과 사용할 자료에 대한 동의가 다시 필요합니다.')
        note.setWordWrap(True)
        permissions.addWidget(note)
        self.question = QCheckBox('질문을 외부 모델에 전송 허용')
        self.results = QCheckBox('직접 첨부한 계산 결과 전송 허용')
        self.public = QCheckBox('직접 요청한 공개 문헌 검색 허용')
        for widget in (self.question, self.results, self.public):
            permissions.addWidget(widget)
            widget.toggled.connect(self._update_summary)
        permissions.addWidget(QLabel('전송을 허용할 자료 분류'))
        self.collections = QListWidget()
        self.collections.itemChanged.connect(self._update_summary)
        permissions.addWidget(self.collections, 1)
        self.tabs.addTab(scope, '자료 전송')
        for index in range(self.tabs.count()):
            page, label = self.tabs.widget(index), self.tabs.tabText(index)
            self.tabs.removeTab(index)
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QScrollArea.Shape.NoFrame)
            scroll.setWidget(page)
            self.tabs.insertTab(index, scroll, label)

        self.permission_summary = QLabel()
        self.permission_summary.setTextFormat(Qt.TextFormat.PlainText)
        self.permission_summary.setWordWrap(True)
        layout.addWidget(self.permission_summary)
        self.message = QLabel('현재 연결과 로컬 설정을 읽는 중입니다…')
        self.message.setTextFormat(Qt.TextFormat.PlainText)
        self.message.setWordWrap(True)
        layout.addWidget(self.message)
        self.details_toggle = QPushButton('확인 상세 펼치기')
        self.details_toggle.setCheckable(True)
        self.details_toggle.setFlat(True)
        layout.addWidget(self.details_toggle, 0, Qt.AlignmentFlag.AlignLeft)
        self.details = QWidget()
        detail_layout = QVBoxLayout(self.details)
        detail_layout.setContentsMargins(0, 0, 0, 0)
        self.service = QLabel(client.url)
        self.service.setTextFormat(Qt.TextFormat.PlainText)
        self.service.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        detail_layout.addWidget(self.service)
        self.checks = QTableWidget(6, 2)
        self.checks.setHorizontalHeaderLabels(['확인 항목', '확인 결과'])
        self.checks.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.checks.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.checks.verticalHeader().hide()
        self.checks.verticalHeader().setDefaultSectionSize(26)
        self.checks.setFixedHeight(188)
        self.checks.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        detail_layout.addWidget(self.checks)
        config_row = QHBoxLayout()
        self.config_label = QLabel()
        self.config_label.setTextFormat(Qt.TextFormat.PlainText)
        self.config_label.setWordWrap(True)
        self.config_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        config_row.addWidget(self.config_label, 1)
        self.choose_config_button = QPushButton('설정 파일 선택…')
        self.choose_config_button.clicked.connect(self.choose_config)
        config_row.addWidget(self.choose_config_button)
        detail_layout.addLayout(config_row)
        self.error_detail = QLabel()
        self.error_detail.setTextFormat(Qt.TextFormat.PlainText)
        self.error_detail.setWordWrap(True)
        self.error_detail.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        detail_layout.addWidget(self.error_detail)
        self.details_scroll = QScrollArea()
        self.details_scroll.setWidgetResizable(True)
        self.details_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.details_scroll.setWidget(self.details)
        self.details_scroll.setFixedHeight(210)
        self.details_scroll.hide()
        layout.addWidget(self.details_scroll)
        self.details_toggle.toggled.connect(self._toggle_details)

        actions = QHBoxLayout()
        self.reload_button = QPushButton('다시 읽기')
        self.reload_button.setToolTip('편집 내용을 로컬 설정 파일의 현재 값으로 다시 읽습니다.')
        self.reload_button.clicked.connect(self._reload)
        actions.addWidget(self.reload_button)
        actions.addStretch()
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Apply | QDialogButtonBox.StandardButton.Cancel)
        apply_button = self.buttons.button(QDialogButtonBox.StandardButton.Apply)
        apply_button.setText('설정 적용')
        apply_button.setProperty('appearanceRole', 'primary')
        apply_button.clicked.connect(self.apply)
        apply_button.setAutoDefault(False)
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('취소')
        self.buttons.rejected.connect(self.reject)
        actions.addWidget(self.buttons)
        layout.addLayout(actions)
        self.enabled.toggled.connect(self._update_summary)
        self.model.currentTextChanged.connect(self._update_summary)
        self.profile.currentTextChanged.connect(self._local_paths_changed)
        self.runtime.currentTextChanged.connect(self._local_paths_changed)
        self.retry = QTimer(self)
        self.retry.setInterval(1000)
        self.retry.timeout.connect(self.activate_saved)
        self.refresh()

    def _toggle_details(self, checked):
        self.details_scroll.setVisible(checked)
        self.details_toggle.setText('확인 상세 접기' if checked else '확인 상세 펼치기')

    def _local_paths_changed(self, *_):
        self.local_check.setText('폴더 확인 전')
        self._status_item(2, 'NOT_CHECKED')
        self._mark_changed()

    def _mark_changed(self, *_):
        if self.loaded and not self._busy and self._pending_sha is None:
            self.message.setText('변경 사항은 아직 적용하지 않았습니다. 설정 적용 전까지 현재 연결은 유지됩니다.')

    def _update_summary(self, *_):
        enabled = self.enabled.isChecked()
        model = self.model.currentText().strip()
        self.role_model_summary.setText('현재 기본 모델: ' + (model or '미설정') if enabled
                                       else '연결 사용 안 함. 역할 정의는 보관할 수 있습니다.')
        for widget in self.connection_inputs:
            widget.setEnabled(enabled)
        for row in range(self.roles.rowCount()):
            combo = self.roles.cellWidget(row, 1)
            if combo:
                combo.setEnabled(enabled)
                combo.lineEdit().setPlaceholderText('기본값 사용: ' + (model or '미설정'))
                combo.setToolTip('비워 두면 현재 기본 모델을 사용합니다. 직접 입력하면 이 역할에만 적용합니다.')
        allowed = [name for widget, name in ((self.question, '질문'), (self.results, '첨부 결과'),
                                             (self.public, '공개 문헌 검색')) if widget.isChecked()]
        selected = self._selected_collections()
        if selected:
            allowed.append('자료 분류 ' + str(len(selected)) + '개')
        self.permission_summary.setText('전송 허용: ' + (' / '.join(allowed) or '없음') if enabled
                                        else '연결 사용 안 함. 외부 전송도 사용하지 않습니다.')
        self._mark_changed()

    def _sync_controls(self):
        self.tabs.setEnabled(not self._busy and self._pending_sha is None)
        self.choose_config_button.setEnabled(not self._busy and self._pending_sha is None)
        self.reload_button.setEnabled(not self._busy and self._pending_sha is None)
        button = self.buttons.button(QDialogButtonBox.StandardButton.Apply)
        button.setEnabled(self.loaded and not self._busy)
        button.setText('다시 적용' if self._pending_sha else '설정 적용')
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(
            '닫기' if self._saved or self._save_started else '취소')

    def _reload(self):
        return self.refresh()

    def _status_item(self, index, value):
        names = {'CONFIGURED': '설정 있음', 'NOT_CONFIGURED': '연결 사용 안 함',
                 'UNKNOWN': '확인 불가', 'MISSING_DEPENDENCIES': '필요한 패키지 없음',
                 'IMPORTS_AVAILABLE': '불러오기 가능', 'NOT_CHECKED': '확인 전',
                 'UNVERIFIED': '확인하지 않음', 'NOT_RUN': '모델 호출하지 않음',
                 'PINNED_FILES_VERIFIED': '로컬 파일 일치', 'UNAVAILABLE': '폴더 확인 필요',
                 'HOST_UNAVAILABLE': 'PowerShell 7 확인 필요'}
        item = QTableWidgetItem(names.get(value, value))
        item.setData(Qt.ItemDataRole.UserRole, value)
        item.setToolTip(value)
        self.checks.setItem(index, 1, item)

    def _call(self, function, success):
        if self._closed or self._busy:
            return False
        from .expert_window import _Call
        self._busy = True
        self._sync_controls()
        worker = _Call(function)
        self._workers.append(worker)
        def done(value, error):
            self._workers.remove(worker)
            self._busy = False
            if self._closed:
                return
            if error:
                self.retry.stop()
                self._save_started = False
                if self._pending_sha:
                    self.message.setText('설정은 저장됐지만 파일이 다시 변경되어 적용할 수 없습니다. 닫고 연결 설정을 다시 열어 현재 파일을 읽으세요.'
                                         if 'file differs' in error or 'file changed' in error else
                                         '설정은 저장됐지만 연결에 적용하지 못했습니다. 다시 적용하거나 닫을 수 있습니다.')
                elif 'Operator settings changed' in error or 'file differs' in error:
                    self.message.setText('설정 파일이 다른 곳에서 변경됐습니다. 다시 읽은 뒤 편집하고 적용하세요.')
                elif 'this service' in error or 'service’s local' in error:
                    self.message.setText('현재 연결에서 사용하는 설정 파일을 선택하세요. 파일은 변경하지 않았습니다.')
                elif 'profile/runtime' in error:
                    self.message.setText('로그인 설정과 실행 도구 폴더를 확인한 뒤 적용하세요.')
                else:
                    self.message.setText('작업을 완료하지 못했습니다. 확인 상세에서 오류를 확인하고 다시 시도하세요.')
                self.error_detail.setText(error)
            else:
                self.error_detail.clear()
                success(value)
            self._sync_controls()
        worker.signals.finished.connect(done, Qt.ConnectionType.QueuedConnection)
        QThreadPool.globalInstance().start(worker)
        return True

    def refresh(self):
        if self._closed or self._busy:
            return False
        # Destination, content and CAS hash must come from one verified read.
        # Failed reads must never leave the previous file eligible for Apply.
        self.loaded = False
        self.message.setText('현재 연결과 로컬 설정을 읽는 중입니다…')
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
            self._show_status(service, registry)
            self._update_summary()
            self.loaded = True
            self.message.setText('역할을 불러오지 못했습니다. 역할 파일을 선택해 교체할 수 있습니다.'
                                 if registry.get('connection_setup_error') else
                                 '저장된 설정이 현재 연결과 다릅니다. 이 설정을 사용하려면 설정 적용을 누르세요.'
                                 if service.get('config_sha256') != sha else
                                 '로컬 설정을 읽었습니다. 변경한 설정은 적용 전까지 현재 토론에 반영되지 않습니다.')
        return self._call(read, opened)

    def _show_status(self, service, registry):
        missing = [x for x in registry.get('packages', {}).get('missing_dependencies', [])
                   if x.get('extra') in ('assist-core', 'mcp')]
        rows = [('연결 설정', service.get('configuration', 'UNKNOWN')),
                ('필요한 패키지', 'MISSING_DEPENDENCIES' if missing else
                 'IMPORTS_AVAILABLE' if registry.get('packages') else 'NOT_CHECKED'),
                ('로컬 폴더', 'NOT_CHECKED'),
                ('로그인', 'UNVERIFIED'), ('모델 사용 권한', 'UNVERIFIED'),
                ('모델 호출', 'NOT_RUN')]
        for index, (key, value) in enumerate(rows):
            self.checks.setItem(index, 0, QTableWidgetItem(key))
            self._status_item(index, value)

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
            combo.currentTextChanged.connect(self._mark_changed)
            self.roles.setCellWidget(index, 1, combo)
        self._role_selection_changed()
        self._update_summary()

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
        path = QFileDialog.getExistingDirectory(self, '기존 ' + ('로그인 설정 폴더 선택' if combo is self.profile else '실행 도구 폴더 선택'),
                                                combo.currentText())
        if path:
            combo.setEditText(path)
            self.inspect_files()

    def inspect_files(self):
        profile, runtime = self.profile.currentText(), self.runtime.currentText()
        def show(value):
            self._status_item(2, value['status'])
            self.local_check.setText('로컬 파일이 일치합니다. 로그인과 모델 사용 권한은 확인하지 않았습니다.'
                                    if value['status'] == 'PINNED_FILES_VERIFIED' else
                                    '준비된 로그인 설정 폴더와 일치하는 실행 도구 폴더를 선택하세요.')
            try:
                setup.powershell_command(Path(__file__).resolve().parents[2] / 'caelab/assist/openscience_host.ps1')
            except ValueError as error:
                self.local_check.setText('실행에 필요한 PowerShell 7을 찾지 못했습니다. 확인 상세를 확인하세요.')
                self.error_detail.setText(str(error))
                self._status_item(2, 'HOST_UNAVAILABLE')
            for model in value.get('models', []):
                if self.model.findText(model) < 0:
                    self.model.addItem(model)
        return self._call(lambda: setup.installation(profile, runtime), show)

    def choose_roles(self):
        path, _ = QFileDialog.getOpenFileName(self, '역할 정의 파일 선택', '', '역할 정의 (*.json)')
        if path:
            self._read_roles(Path(path))

    def example_roles(self):
        self._read_roles(Path(__file__).resolve().parents[2] / 'examples' / 'workbench_experts.json')

    def _read_roles(self, path):
        try:
            definitions = setup.roles(setup.read_config(path)[0])
        except (OSError, ValueError) as error:
            self.message.setText('역할 파일을 읽지 못했습니다. 기존 역할은 유지했습니다. 확인 상세를 확인하세요.')
            self.error_detail.setText(str(error))
            return
        selected = self._selected_collections()
        self.definitions = definitions
        self._populate_roles()
        self._populate_collections(selected)
        self.message.setText('역할을 불러왔습니다. 설정 적용 전까지 현재 토론의 역할은 유지됩니다.')
        self.error_detail.clear()

    def choose_config(self):
        path, _ = QFileDialog.getOpenFileName(self, '현재 연결의 로컬 설정 파일 선택', '', '로컬 설정 (*.json)')
        if path:
            self.path = Path(path)
            self.refresh()

    def apply(self):
        if not self.loaded or self._busy or self._closed:
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
            self._saved = True
            self._save_started = False
            self.message.setText('설정을 로컬 파일에 저장했습니다. 현재 연결에 적용하는 중입니다…')
            QTimer.singleShot(0, self.activate_saved)
        self._save_started = True
        self.message.setText('설정을 저장하는 중입니다. 닫아도 이미 시작한 저장은 계속됩니다.')
        return self._call(save, saved)

    def activate_saved(self):
        if not self._pending_sha:
            return
        def received(value):
            if value['status'] == 'DEFERRED':
                self.message.setText('설정은 저장됐습니다. 이 창을 열어두면 작업 종료 후 적용합니다. 닫으면 저장만 유지되며 다시 열어 적용해야 합니다.')
                self.retry.start()
            elif value['status'] == 'APPLIED':
                self.retry.stop()
                self._pending_sha = None
                self.tabs.setEnabled(True)
                self.message.setText('연결 설정을 적용했습니다. 현재 토론의 질문과 자료 전송 동의는 유지됩니다.')
                self._status_item(0, value['configuration'])
            else:
                self.retry.stop()
                self.message.setText('설정은 저장됐지만 이전 작업의 정리가 끝나지 않아 적용하지 못했습니다. 정리 후 다시 적용하세요.'
                                     if value['status'] == 'CLEANUP_PENDING' else
                                     '설정은 저장됐지만 연결에 적용하지 못했습니다. 확인 상세에서 원인을 확인하세요.')
                self.error_detail.setText(value.get('reason', value['status']))
        return self._call(lambda: self.client.reload_expert_connection(self._pending_sha), received)

    def reject(self):
        self._closed = True
        self.retry.stop()
        for worker in self._workers:
            worker.abandon()
        super().reject()
