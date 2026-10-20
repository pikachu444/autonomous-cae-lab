"""On-demand FreeCAD task dock for the existing prescribed-U transfer.

Qt is injected by the native connection. This module must not import PySide6
into FreeCAD's own Qt runtime, launch a solver, or create another document owner.
"""
from copy import deepcopy
import math
import os
import uuid

from caelab.storage import canonical_hash
from caelab.post_spatial_mapping import tetra10_boundary
from . import structural_transfer_native as native


def _number(text, integer=False):
    try:
        value = int(text) if integer else float(text)
        return value if math.isfinite(value) else text
    except (ValueError, TypeError):
        return text


def make_panel(connection, owner):
    W, C = connection.QtWidgets, connection.QtCore
    role = C.Qt.UserRole

    class Panel(W.QWidget):
        def __init__(self):
            super().__init__()
            if os.name == 'nt':
                body_font = self.font()
                body_font.setFamily('Malgun Gothic'); body_font.setPointSizeF(10.0)
                self.setFont(body_font)
            self._record = None
            self._analysis_id = None
            self._busy = False
            self._epoch = 0
            self._populating = False
            self._target = None
            self._source = None
            self._read_reference = None
            self._static = None
            self._preview = None
            self._unrepresented = None
            self._loaded = None
            self._raw_draft = {}
            self._catalog_error = None
            self._replacement_conditions = []
            self._replace_condition_ids = []
            self._replace_key = False
            self.setObjectName('displacementImportTask')
            self.setMinimumWidth(350)
            outer = W.QVBoxLayout(self); outer.setContentsMargins(12, 10, 12, 10); outer.setSpacing(9)
            heading = W.QLabel('해석 결과에서 변위 가져오기')
            heading.setStyleSheet('font-weight:600; font-size:14px;')
            outer.addWidget(heading)
            self.task_state = W.QLabel(); self.task_state.setWordWrap(True)
            self.task_state.setTextFormat(C.Qt.PlainText)
            self.task_state.setStyleSheet('color:#405669;')
            outer.addWidget(self.task_state)
            form = W.QHBoxLayout()
            self.analysis = W.QComboBox(); self.solver = W.QComboBox()
            self.analysis.setSizeAdjustPolicy(W.QComboBox.AdjustToMinimumContentsLengthWithIcon)
            self.analysis.setMinimumContentsLength(8)
            form.addWidget(W.QLabel('변위를 적용할 해석')); form.addWidget(self.analysis, 1)
            outer.addLayout(form)
            self.analysis_kind = W.QLabel('종류: 해석 설정 확인 필요')
            self.analysis_kind.setWordWrap(True); self.analysis_kind.setTextFormat(C.Qt.PlainText)
            outer.addWidget(self.analysis_kind)
            self.steps = W.QTabWidget(); self.steps.setDocumentMode(True)
            self.steps.setUsesScrollButtons(False)
            outer.addWidget(self.steps, 1)
            source_page = W.QWidget(); layout = W.QVBoxLayout(source_page)
            layout.setContentsMargins(0, 12, 0, 4); layout.setSpacing(9)
            introduction = W.QLabel('변위를 가져올 계산 결과를 선택하세요.')
            introduction.setWordWrap(True); layout.addWidget(introduction)
            source_row = W.QHBoxLayout()
            self.source = W.QComboBox(); self.source.setMinimumWidth(150)
            self.source.setSizeAdjustPolicy(W.QComboBox.AdjustToMinimumContentsLengthWithIcon)
            self.source.setMinimumContentsLength(12)
            self.read_source = W.QPushButton('결과 확인')
            self.refresh_sources = W.QPushButton('목록 다시 읽기')
            self.open_source = W.QPushButton('원본 결과 열기')
            source_row.addWidget(self.source, 1); source_row.addWidget(self.read_source)
            layout.addLayout(source_row)
            source_tools = W.QHBoxLayout(); source_tools.addWidget(self.open_source); source_tools.addWidget(self.refresh_sources)
            layout.addLayout(source_tools)
            self.source_info = W.QLabel('결과 확인을 누르면 원본의 좌표계, 단위와 해석 단계를 읽습니다.')
            self.source_info.setTextFormat(C.Qt.PlainText)
            self.source_info.setWordWrap(True); layout.addWidget(self.source_info)
            layout.addSpacing(7)
            self.all_faces = W.QPushButton('원본의 외부 면 모두 사용'); layout.addWidget(self.all_faces)
            self.source_faces_info = W.QLabel('원본 결과를 확인한 뒤 사용할 범위를 선택하세요.')
            self.source_faces_info.setWordWrap(True); layout.addWidget(self.source_faces_info)
            self.faces_dialog = W.QDialog(self); self.faces_dialog.setWindowTitle('사용할 원본 면')
            self.faces_dialog.resize(420, 460)
            face_layout = W.QVBoxLayout(self.faces_dialog)
            face_note = W.QLabel('원본 메시의 외부 면 중 변위를 가져올 범위를 선택합니다.')
            face_note.setWordWrap(True); face_layout.addWidget(face_note)
            self.faces = W.QListWidget(); face_layout.addWidget(self.faces, 1)
            face_buttons = W.QDialogButtonBox(W.QDialogButtonBox.Ok | W.QDialogButtonBox.Cancel)
            face_buttons.button(W.QDialogButtonBox.Ok).setText('선택 완료')
            face_buttons.button(W.QDialogButtonBox.Cancel).setText('취소')
            face_buttons.accepted.connect(self.faces_dialog.accept); face_buttons.rejected.connect(self.faces_dialog.reject)
            face_layout.addWidget(face_buttons)
            self.choose_faces = W.QPushButton('일부 원본 면만 선택…')
            self.choose_faces.clicked.connect(self._choose_faces); layout.addWidget(self.choose_faces)
            layout.addStretch(1)
            self.steps.addTab(source_page, '원본 결과')
            target_page = W.QWidget(); target_outer = W.QVBoxLayout(target_page)
            target_outer.setContentsMargins(0, 0, 0, 0)
            self.target_scroll = W.QScrollArea(); self.target_scroll.setWidgetResizable(True)
            self.target_scroll.setFrameShape(W.QFrame.NoFrame)
            self.target_scroll.setHorizontalScrollBarPolicy(C.Qt.ScrollBarAlwaysOff)
            target_body = W.QWidget(); target_layout = W.QVBoxLayout(target_body)
            self.target_scroll.setWidget(target_body); target_outer.addWidget(self.target_scroll)
            target_layout.setContentsMargins(0, 12, 0, 4); target_layout.setSpacing(6)
            target_note = W.QLabel('3D 화면에서 적용할 물체의 외부 면을 선택하세요. 여러 면은 Ctrl을 누른 채 선택합니다.')
            target_note.setWordWrap(True); target_layout.addWidget(target_note)
            target_row = W.QHBoxLayout()
            self.use_selection = W.QPushButton('선택한 면 사용')
            self.highlight = W.QPushButton('3D에서 확인')
            target_row.addWidget(self.use_selection); target_row.addWidget(self.highlight)
            target_layout.addLayout(target_row)
            self.target_info = W.QLabel('아직 적용할 면을 선택하지 않았습니다.')
            self.target_info.setTextFormat(C.Qt.PlainText)
            self.target_info.setWordWrap(True)
            self.target_info.setStyleSheet('background:#eef3f7; color:#203849; padding:10px;')
            self.target_info.setMinimumHeight(2 * self.target_info.fontMetrics().lineSpacing() + 20)
            target_layout.addWidget(self.target_info)
            components = W.QHBoxLayout(); components.addWidget(W.QLabel('가져올 변위 [mm]'))
            self.components = []
            for label in ('X', 'Y', 'Z'):
                box = W.QCheckBox(label); box.setChecked(True); self.components.append(box)
                components.addWidget(box); box.toggled.connect(self._edited)
            components.addStretch(); target_layout.addLayout(components)
            self.replacement_summary = W.QLabel('기존 조건은 자동으로 바꾸지 않습니다.')
            self.replacement_summary.setWordWrap(True)
            self.replacement_summary.setTextFormat(C.Qt.PlainText)
            target_layout.addWidget(self.replacement_summary)
            self.choose_replacements = W.QPushButton('교체할 기존 조건 선택…')
            self.choose_replacements.clicked.connect(self._choose_replacements)
            target_layout.addWidget(self.choose_replacements)
            self._receiver_frame = 'FREECAD_DOCUMENT_GLOBAL'
            self.receiver_frame = W.QLineEdit('전역 좌표계')
            self.receiver_frame.setToolTip(self._receiver_frame)
            self.receiver_frame.setReadOnly(True)
            target_layout.addWidget(W.QLabel('적용 좌표계')); target_layout.addWidget(self.receiver_frame)
            self.advanced_button = W.QPushButton('좌표 변환과 매핑 설정…')
            target_layout.addWidget(self.advanced_button)
            self.mapping_status = W.QLabel(); self.mapping_status.setWordWrap(True)
            target_layout.addWidget(self.mapping_status)
            self.scope = W.QLabel('선택한 면의 자유 성분에 변위를 추가합니다. 기존 조건과 겹치면 교체할 조건을 명시적으로 선택하세요.')
            self.scope.setWordWrap(True); target_layout.addWidget(self.scope)
            target_layout.addStretch(1); self.steps.addTab(target_page, '적용할 면')
            self.settings_dialog = W.QDialog(self); self.settings_dialog.setWindowTitle('좌표 변환과 매핑 설정')
            self.settings_dialog.resize(480, 560)
            settings_layout = W.QVBoxLayout(self.settings_dialog)
            self.advanced = W.QWidget(); advanced = W.QFormLayout(self.advanced)
            advanced.addRow('적용할 솔버', self.solver)
            self.rotation = []
            for i in range(3):
                row = W.QHBoxLayout(); values = []
                for j in range(3):
                    field = W.QLineEdit('1' if i == j else '0'); field.setMaximumWidth(100)
                    field.textEdited.connect(self._edited); row.addWidget(field); values.append(field)
                self.rotation.append(values); advanced.addRow('회전 R ' + str(i + 1), row)
            self.translation = []
            row = W.QHBoxLayout()
            for label in ('X', 'Y', 'Z'):
                field = W.QLineEdit('0'); field.setMaximumWidth(100); field.setToolTip(label + ' [mm]')
                field.textEdited.connect(self._edited); row.addWidget(field); self.translation.append(field)
            advanced.addRow('좌표 이동 [mm]', row)
            self.limits = {}
            for key, label in [('distance_tolerance', '거리 허용값 [mm]'),
                               ('natural_tolerance', '자연좌표 허용값'),
                               ('weight_tolerance', '가중치 허용값'), ('max_iterations', '역변환 반복 한도')]:
                field = W.QLineEdit(); field.setPlaceholderText('명시 설정 필요')
                field.textEdited.connect(self._edited); self.limits[key] = field; advanced.addRow(label, field)
            note = W.QLabel('좌표 이동은 변위에 더하지 않습니다. 회전과 길이 변환은 한 번 적용합니다. 허용값은 선택한 모델에 맞게 명시하며 실패를 통과시키기 위해 완화하지 않습니다.')
            note.setWordWrap(True); advanced.addRow(note)
            settings_scroll = W.QScrollArea(); settings_scroll.setWidgetResizable(True)
            settings_scroll.setWidget(self.advanced); settings_layout.addWidget(settings_scroll, 1)
            settings_buttons = W.QDialogButtonBox(W.QDialogButtonBox.Ok | W.QDialogButtonBox.Cancel)
            settings_buttons.button(W.QDialogButtonBox.Ok).setText('설정 확인')
            settings_buttons.button(W.QDialogButtonBox.Cancel).setText('취소')
            settings_buttons.accepted.connect(self.settings_dialog.accept); settings_buttons.rejected.connect(self.settings_dialog.reject)
            settings_layout.addWidget(settings_buttons)
            check_page = W.QWidget(); check_layout = W.QVBoxLayout(check_page)
            check_layout.setContentsMargins(0, 12, 0, 4); check_layout.setSpacing(8)
            self.summary = W.QLabel('적용할 면을 선택한 뒤 변위를 확인하세요.'); self.summary.setWordWrap(True)
            check_layout.addWidget(self.summary)
            self.table = W.QTableWidget(0, 8)
            self.table.setHorizontalHeaderLabels(['절점', 'X [mm]', 'Y [mm]', 'Z [mm]',
                                                  'Ux [mm]', 'Uy [mm]', 'Uz [mm]', '상태'])
            self.table.setEditTriggers(W.QAbstractItemView.NoEditTriggers)
            self.table.setSelectionBehavior(W.QAbstractItemView.SelectRows)
            self.table.setSelectionMode(W.QAbstractItemView.SingleSelection)
            self.table.verticalHeader().hide(); self.table.setAlternatingRowColors(True)
            for column in (1, 2, 3): self.table.setColumnHidden(column, True)
            self.table.setMinimumHeight(160); check_layout.addWidget(self.table, 1)
            self.details_button = W.QPushButton('선택 절점의 좌표와 매핑 근거…'); check_layout.addWidget(self.details_button)
            limits_note = W.QLabel('변위 단위: mm')
            limits_note.setWordWrap(True); check_layout.addWidget(limits_note)
            self.steps.addTab(check_page, '변위 확인')
            self.message = W.QLabel(); self.message.setWordWrap(True); outer.addWidget(self.message)
            primary = W.QHBoxLayout()
            self.save = W.QPushButton('초안 저장'); self.preview = W.QPushButton('변위 확인')
            self.apply = W.QPushButton('경계조건 적용'); self.cancel = W.QPushButton('편집 취소')
            self.next_step = W.QPushButton('적용면 선택 →')
            self.reload = W.QPushButton('초안 다시 읽기')
            self.reload.clicked.connect(lambda: self.open_analysis(self._analysis_id))
            self.remove = W.QPushButton('적용 해제')
            more = self.more_button = W.QToolButton(); more.setText('기타'); more.setPopupMode(W.QToolButton.InstantPopup)
            menu = W.QMenu(more)
            self.reload_action = menu.addAction('저장한 초안 다시 읽기'); self.reload_action.triggered.connect(self.reload.click)
            self.remove_action = menu.addAction('가져온 변위 적용 해제'); self.remove_action.triggered.connect(self.remove.click)
            view_actions = getattr(connection, 'structural_transfer_view_actions', None)
            if callable(view_actions):
                actions = view_actions()
                if actions: menu.addSeparator()
                for label, action in actions:
                    menu.addAction(action)
            more.setMenu(menu)
            buttons = W.QHBoxLayout()
            for button in (self.save, self.cancel, more): buttons.addWidget(button)
            buttons.addStretch(1)
            self.close_button = W.QPushButton('닫기'); self.close_button.clicked.connect(self.request_close)
            buttons.addWidget(self.close_button)
            for button in (self.next_step, self.preview, self.apply): primary.addWidget(button, 1)
            outer.addLayout(primary)
            outer.addLayout(buttons)
            self._primary_style = 'QPushButton {background:#245b80;color:white;border:1px solid #245b80;border-radius:3px;padding:6px 10px;} QPushButton:hover {background:#1c4e71;} QPushButton:pressed {background:#193d58;} QPushButton:disabled {background:#e5ebef;color:#7b8790;border-color:#cdd5db;} QPushButton:focus {border:2px solid #163c58;}'
            self.apply.setStyleSheet(self._primary_style); self.next_step.setStyleSheet(self._primary_style)
            self.next_step.clicked.connect(lambda: self.steps.setCurrentIndex(1))
            self.steps.currentChanged.connect(self._refresh_task)
            self.analysis.currentIndexChanged.connect(self._analysis_changed)
            self.solver.currentIndexChanged.connect(self._edited)
            self.receiver_frame.textEdited.connect(self._edited)
            self.source.activated.connect(self._source_selected)
            self.read_source.clicked.connect(self._source_selected)
            self.refresh_sources.clicked.connect(self._catalog)
            self.open_source.clicked.connect(self._open_source)
            self.all_faces.clicked.connect(self._select_all)
            self.faces.itemChanged.connect(self._edited)
            self.use_selection.clicked.connect(self._use_selection)
            self.highlight.clicked.connect(self._highlight)
            self.advanced_button.clicked.connect(self._settings)
            self.save.clicked.connect(lambda: self._operation('save'))
            self.preview.clicked.connect(lambda: self._operation('preview'))
            self.apply.clicked.connect(lambda: self._operation('apply'))
            self.cancel.clicked.connect(self._cancel)
            self.remove.clicked.connect(lambda: self._operation('remove'))
            self.details_button.clicked.connect(self._details)
            self._catalog()

        def _refresh_task(self, *_):
            self._refresh_analysis_kind()
            page = self.steps.currentIndex()
            self.next_step.setVisible(page == 0)
            self.preview.setVisible(page != 0)
            self.preview.setText('다시 확인' if page == 2 else '변위 확인 →')
            self.preview.setStyleSheet(self._primary_style if page == 1 else '')
            self.apply.setVisible(page == 2)
            selected = len(self._selected_faces())
            if self._source is not None:
                self.source_faces_info.setText('원본 외부 면 ' + str(selected) + '개 선택됨' if selected else '가져올 원본 면의 범위를 선택하세요.')
            elif selected:
                self.source_faces_info.setText('저장한 원본 면 ' + str(selected) + '개 — 결과 확인으로 현재 원본을 검토하세요.')
            else:
                self.source_faces_info.setText('원본 결과를 확인한 뒤 사용할 범위를 선택하세요.')
            applied = (self._record or {}).get('accepted')
            same = isinstance(applied, dict) and canonical_hash(self.current_draft()) == applied.get('draft_sha256')
            state = ('경계조건에 적용됨' if same else
                '적용한 경계조건과 다른 편집 내용이 있습니다.' if applied else '아직 경계조건에 적용하지 않았습니다.')
            name = self.source.currentText() if self.source.currentData() else ''
            shown = self.fontMetrics().elidedText(name, C.Qt.ElideRight, max(220, self.width() - 42))
            target_name = ''
            if self._target:
                try: target_name = owner._object(self._target['body_id']).Label
                except Exception: target_name = '선택한 물체'
                target_name += ' / 면 ' + str(len(self._target['faces'])) + '개'
            target_shown = self.fontMetrics().elidedText(target_name, C.Qt.ElideRight, max(200, self.width() - 82))
            self.task_state.setText(state + ('\n원본: ' + shown if name else '') +
                ('\n적용면: ' + target_shown if target_name else ''))
            self.task_state.setToolTip(name + ('\n적용면: ' + target_name if target_name else ''))
            self.next_step.setEnabled(not self._busy and self._source is not None and selected > 0)
            missing = any(not field.text().strip() for field in self.limits.values())
            malformed = any(not isinstance(_number(field.text(), key == 'max_iterations'), (int, float))
                            for key, field in self.limits.items())
            self.mapping_status.setText('매핑 허용값을 먼저 설정하세요.' if missing else
                '허용값 형식을 확인하세요. 입력 원문은 유지됩니다.' if malformed else '')
            self.mapping_status.setVisible(missing or malformed)
            self.advanced_button.setText('매핑 허용값 설정…' if missing else '좌표 변환과 매핑 설정…')
            selected_conditions = (set(self._replace_condition_ids) if isinstance(self._replace_condition_ids, list)
                                   and all(isinstance(value, str) for value in self._replace_condition_ids) else set())
            labels = [row['label'] for row in self._replacement_conditions
                      if row['object_id'] in selected_conditions]
            missing_conditions = selected_conditions - {row['object_id'] for row in self._replacement_conditions}
            if missing_conditions: labels.append('현재 목록에 없는 저장 조건 ' + str(len(missing_conditions)) + '개')
            if labels:
                text = '교체 선택: ' + ', '.join(labels)
                self.replacement_summary.setText(self.fontMetrics().elidedText(text, C.Qt.ElideRight, max(260, self.width() - 40)))
                self.replacement_summary.setToolTip(text + '\n겹치는 성분은 변위 확인에서 검사합니다.')
            else:
                self.replacement_summary.setText('기존 조건 교체 안 함' if self._replacement_conditions else '교체할 기존 고정·변위 조건이 없습니다.')
                self.replacement_summary.setToolTip('다른 지지 조건과 하중은 유지합니다. 겹치는 기존 조건을 선택하지 않으면 적용할 수 없습니다.')

        def _refresh_analysis_kind(self):
            """Describe actual settings, independently of the authored object label."""
            text = '종류: 해석 설정 확인 필요'
            detail = '해석 이름은 사용자가 지정한 이름입니다. 솔버와 단계 설정으로 종류를 확인합니다.'
            try:
                if not self._analysis_id or not self.solver.currentData():
                    raise ValueError('해석 이름과 솔버를 선택하세요.')
                solver = owner._object(self.solver.currentData())
                native_type = getattr(getattr(solver, 'Proxy', None), 'Type', solver.TypeId)
                if native_type != 'Fem::SolverCcxTools':
                    raise ValueError('선택한 솔버의 해석 종류를 이 작업창에서 확인할 수 없습니다.')
                analysis_type = getattr(solver, 'AnalysisType', None)
                known = {'frequency': '고유진동 해석', 'thermomech': '열·구조 해석',
                         'check': '모델 검사', 'buckling': '좌굴 해석'}
                if analysis_type in known:
                    text = '종류: ' + known[analysis_type] + ' / CalculiX (가져오기 미지원)'
                elif analysis_type != 'static':
                    raise ValueError('솔버의 해석 종류를 확인하세요: ' + str(analysis_type))
                else:
                    data = owner.fem._metadata()
                    contacts = data.get('contact_programs', [])
                    dynamics = data.get('dynamic_programs', {})
                    if not isinstance(contacts, list) or not isinstance(dynamics, dict):
                        raise ValueError('저장된 단계 설정을 확인하세요.')
                    programs = [row for row in contacts if row['analysis_id'] == self._analysis_id]
                    if len(programs) > 1: raise ValueError('같은 해석 이름의 단계 설정이 중복됐습니다.')
                    dynamic = dynamics.get(self._analysis_id)
                    program = dynamic['draft']['program'] if dynamic else programs[0]['draft'] if programs else None
                    procedure, count = 'static', 1
                    if program is not None:
                        procedure = program['procedure']; steps = program['steps']; count = len(steps)
                        if not isinstance(steps, list) or not steps: raise ValueError('저장된 단계 종류를 확인하세요.')
                        kinds = {step.get('procedure', procedure) for step in steps}
                        expected = {'static', 'dynamic'} if procedure == 'mixed' else {procedure}
                        if procedure not in ('static', 'dynamic', 'mixed') or kinds != expected:
                            raise ValueError('해석 종류와 단계별 종류가 일치하는지 확인하세요.')
                    geometry = getattr(solver, 'GeometricalNonlinearity', None)
                    if geometry not in ('linear', 'nonlinear'):
                        raise ValueError('솔버의 기하 선형성 설정을 확인하세요.')
                    if procedure == 'static':
                        name = '정적 구조 해석' if geometry == 'linear' else '비선형 정적 구조 해석'
                        if count != 1: name += ', 여러 단계'
                    elif procedure == 'dynamic': name = '동적 구조 해석'
                    else: name = '정적/동적 혼합 구조 해석'
                    unsupported = procedure != 'static' or geometry != 'linear' or count != 1
                    text = '종류: ' + name + ' / CalculiX' + (' (가져오기 미지원)' if unsupported else '')
                detail += '\n변위 가져오기는 단일 선형 정적 단계만 지원하며, 모델과 조건의 적용 가능성은 변위 확인에서 검사합니다.'
            except (AttributeError, KeyError, TypeError, ValueError, RuntimeError) as error:
                detail += '\n' + str(error)
            self.analysis_kind.setText(text); self.analysis_kind.setToolTip(detail)

        def _choose_replacements(self):
            dialog = W.QDialog(self); dialog.setWindowTitle('교체할 기존 조건')
            dialog.setObjectName('replacementConditionsDialog')
            dialog.resize(560, 380)
            layout = W.QVBoxLayout(dialog)
            note = W.QLabel('고른 조건에서 가져올 변위와 겹치는 성분을 교체합니다. 다른 조건은 유지합니다. 정확한 겹침은 변위 확인에서 검사합니다.')
            note.setWordWrap(True); layout.addWidget(note)
            table = W.QTableWidget(0, 3); table.setObjectName('replacementConditions')
            table.setHorizontalHeaderLabels(['기존 조건', '성분', '적용 대상'])
            table.setEditTriggers(W.QAbstractItemView.NoEditTriggers)
            table.setSelectionBehavior(W.QAbstractItemView.SelectRows)
            table.verticalHeader().hide(); table.setWordWrap(True)
            rows = deepcopy(self._replacement_conditions)
            available = {row['object_id'] for row in rows}
            rows += [{'object_id': identifier, 'label': '저장된 조건 (현재 목록에 없음)',
                      'components': [], 'targets': []}
                     for identifier in self._replace_condition_ids if identifier not in available]
            table.setRowCount(len(rows))
            for i, row in enumerate(rows):
                kind = {'Fem::ConstraintFixed': '고정', 'Fem::ConstraintDisplacement': '변위'}.get(row.get('type'), '')
                item = W.QTableWidgetItem(row['label'] + (' (' + kind + ')' if kind else ''))
                item.setData(role, row['object_id']); item.setToolTip(row['object_id'])
                item.setFlags(item.flags() | C.Qt.ItemIsUserCheckable)
                item.setCheckState(C.Qt.Checked if row['object_id'] in self._replace_condition_ids else C.Qt.Unchecked)
                table.setItem(i, 0, item)
                axes = ', '.join('XYZ'[axis - 1] for axis in row['components'] if type(axis) is int and axis in (1, 2, 3))
                table.setItem(i, 1, W.QTableWidgetItem(axes or '미제공'))
                targets = []
                for target in row['targets']:
                    identifier = target['body_id']
                    try: label = owner._object(identifier).Label
                    except Exception: label = '원래 대상'
                    names = [('면 ' + name[4:] if name.startswith('Face') else name)
                             for name in target['subelements']]
                    targets.append(label + (': ' + ', '.join(names) if names else ' (전체)'))
                target_item = W.QTableWidgetItem('; '.join(targets) or '현재 대상 확인 필요')
                target_item.setToolTip(target_item.text()); table.setItem(i, 2, target_item)
            table.setColumnWidth(0, 210); table.setColumnWidth(1, 65)
            table.horizontalHeader().setStretchLastSection(True); table.resizeRowsToContents()
            layout.addWidget(table, 1)
            buttons = W.QDialogButtonBox(W.QDialogButtonBox.Ok | W.QDialogButtonBox.Cancel)
            buttons.button(W.QDialogButtonBox.Ok).setText('선택 확인')
            buttons.button(W.QDialogButtonBox.Cancel).setText('취소')
            buttons.accepted.connect(dialog.accept); buttons.rejected.connect(dialog.reject)
            layout.addWidget(buttons)
            if dialog.exec() == W.QDialog.Accepted:
                checked = [table.item(i, 0).data(role) for i in range(table.rowCount())
                           if table.item(i, 0).checkState() == C.Qt.Checked]
                selected = [value for value in self._replace_condition_ids if value in checked]
                selected += [value for value in checked if value not in selected]
                if selected != self._replace_condition_ids:
                    self._replace_condition_ids = selected
                    self._replace_key = bool(selected) or 'replace_condition_ids' in self._raw_draft
                    self._edited()
            dialog.deleteLater()

        def _settings(self):
            fields = [field for row in self.rotation for field in row] + self.translation + list(self.limits.values())
            before = [field.text() for field in fields]
            solver = self.solver.currentIndex(); previous_preview = deepcopy(self._preview)
            if self.settings_dialog.exec() != W.QDialog.Accepted:
                self._populating = True
                for field, text in zip(fields, before): field.setText(text)
                self.solver.setCurrentIndex(solver)
                self._populating = False
                self._preview = previous_preview
            self._enabled()

        def _choose_faces(self):
            before = [self.faces.item(i).checkState() for i in range(self.faces.count())]
            previous_preview = deepcopy(self._preview)
            if self.faces_dialog.exec() != W.QDialog.Accepted:
                self._populating = True
                for i, checked in enumerate(before): self.faces.item(i).setCheckState(checked)
                self._populating = False
                self._preview = previous_preview
            self._enabled()

        def request_close(self):
            if self._busy:
                self.message.setText('현재 요청이 끝난 뒤 닫으세요. 편집 내용은 유지합니다.')
                return False
            def close():
                callback = getattr(connection, 'close_structural_transfer', None)
                if callable(callback): callback(owner)
            if not self.pending_changes():
                close(); return True
            question = W.QMessageBox(self); question.setWindowTitle('편집한 변위 조건')
            question.setText('적용하지 않은 편집 내용을 어떻게 할까요?')
            save = question.addButton('초안 저장 후 닫기', W.QMessageBox.AcceptRole)
            discard = question.addButton('편집 취소 후 닫기', W.QMessageBox.DestructiveRole)
            keep = question.addButton('계속 편집', W.QMessageBox.RejectRole)
            question.setDefaultButton(keep); question.exec()
            if question.clickedButton() is save:
                self._operation('save', after=lambda: close() if not self.pending_changes() else None)
            elif question.clickedButton() is discard:
                self._cancel()
                if not self.pending_changes(): close()
            return False

        def _context(self):
            return (id(owner.doc), owner.document_id, getattr(owner, 'session_id', None), self._analysis_id, self._epoch)

        def _populate_analyses(self):
            selected = self._analysis_id
            self._populating = True
            self.analysis.clear()
            self.analysis.addItem('해석 이름 선택', None)
            for obj in owner.doc.Objects:
                if getattr(getattr(obj, 'Proxy', None), 'Type', obj.TypeId) == 'Fem::FemAnalysis':
                    self.analysis.addItem(obj.Label, obj.Name)
            if self.analysis.findData(selected) < 1:
                selected = self.analysis.itemData(1) if self.analysis.count() == 2 else None
            self.analysis.setCurrentIndex(max(0, self.analysis.findData(selected)))
            self._populating = False
            self.open_analysis(selected)

        def refresh_context(self):
            if self._busy or self.pending_changes():
                self.message.setText('현재 요청을 마치고 편집을 저장하거나 취소한 뒤 목록을 다시 읽으세요.')
                return False
            self._catalog(); return True

        def _analysis_changed(self, *_):
            if self._populating: return
            self.open_analysis(self.analysis.currentData())

        def open_analysis(self, identifier):
            if self.pending_changes():
                self.message.setText('현재 편집을 저장하거나 취소한 뒤 다른 해석을 선택하세요.')
                blocked = self.analysis.blockSignals(True)
                self.analysis.setCurrentIndex(self.analysis.findData(self._analysis_id))
                self.analysis.blockSignals(blocked); return False
            self._analysis_id = identifier; self._epoch += 1; self._record = None
            self._loaded = None; self._preview = None
            self._replacement_conditions = []
            self.table.setRowCount(0); self.summary.setText('변위를 적용할 해석 이름을 선택하세요.')
            self._populating = True
            self.analysis.setCurrentIndex(max(0, self.analysis.findData(identifier)))
            self.solver.clear()
            if identifier:
                for obj in owner._object(identifier).Group:
                    if getattr(getattr(obj, 'Proxy', None), 'Type', obj.TypeId) == 'Fem::SolverCcxTools':
                        self.solver.addItem(obj.Label, obj.Name)
            self._populating = False
            if identifier: self._send('read', {}, self._accept_state)
            self._enabled(); return True

        def _request(self, name, function, accepted):
            context = self._context(); self._busy = True; self._enabled()
            def read():
                try: return {'value': function()}
                except Exception as error: return {'error': str(error)}
            def done(value):
                self._busy = False
                if self._context() != context or getattr(owner, 'closed', False):
                    self._enabled(); return
                if 'error' in value:
                    self.message.setText(value['error'])
                    if name == 'sources': self._catalog_error = value['error']
                    if name == 'source': self.source_info.setText('원본 결과를 확인하지 못했습니다. 결과 확인으로 다시 읽으세요.')
                else:
                    try: accepted(value['value'])
                    except Exception as error: self.message.setText(str(error))
                if name == 'sources': self._populate_analyses()
                self._enabled()
            connection.request('displacement:' + name + ':' + uuid.uuid4().hex, read, done)

        def _catalog(self):
            if self._busy or self.pending_changes():
                self.message.setText('현재 요청을 마치고 편집을 저장하거나 취소한 뒤 목록을 다시 읽으세요.')
                return
            def received(rows):
                self._catalog_error = None
                if self._source is None and self._static is None:
                    self.source_info.setText('저장한 원본을 선택한 뒤 결과 확인으로 좌표계·단위와 정적 위치를 확인하세요.')
                reference = self.source.currentData(); previous_label = self.source.currentText()
                blocked = self.source.blockSignals(True); self.source.clear()
                self.source.addItem('저장한 변위 원본 선택', None)
                for row in rows:
                    label = row['label']; static = row.get('static')
                    if isinstance(static, dict):
                        label += ' / 단계 ' + str(static.get('step', '미제공')) + ', 증분 ' + str(static.get('increment', '미제공')) + ', λ ' + str(static.get('load_parameter', '미제공'))
                    self.source.addItem(label, deepcopy(row['reference']))
                    self.source.setItemData(self.source.count() - 1, label + '\n정적 하중 매개변수는 물리 시간이 아닙니다.\n' + str(row['reference']), C.Qt.ToolTipRole)
                if reference is not None:
                    index = self.source.findData(reference)
                    if index < 0:
                        self.source.addItem(previous_label, deepcopy(reference)); index = self.source.count() - 1
                    self.source.setCurrentIndex(index)
                self.source.blockSignals(blocked)
            self._request('sources', connection.client.structural_displacement_sources, received)

        def _source_selected(self, *_):
            reference = self.source.currentData()
            if not reference: self.message.setText('저장한 변위 원본을 선택하세요.'); return
            previous = self._read_reference
            selected_faces = self._selected_faces() if reference == previous else []
            self._read_reference = deepcopy(reference)
            self._edited()
            self._source = None
            self.source_info.setText('선택한 원본 결과를 확인하고 있습니다.')
            if reference != previous:
                self._static = None
                self._populating = True; self.faces.clear(); self._populating = False
            def received(envelope):
                if envelope['reference'] != reference: raise ValueError('다른 저장 원본의 응답입니다.')
                old_faces = selected_faces; self._source = deepcopy(envelope)
                self._static = deepcopy(envelope['field']['static'])
                field = envelope['field']; self._populating = True; self.faces.clear()
                catalog = tetra10_boundary(field['node_ids'], field['coordinates'], field['elements'])
                known = {(f['element_id'], f['face']): f for f in catalog}
                pairs = old_faces + [[f['element_id'], f['face']] for f in catalog
                                     if [f['element_id'], f['face']] not in old_faces]
                for i, pair in enumerate(pairs):
                    item = W.QListWidgetItem('원본 외부 면 ' + str(i + 1))
                    item.setData(role, pair)
                    item.setFlags(item.flags() | C.Qt.ItemIsUserCheckable)
                    item.setCheckState(C.Qt.Checked if pair in old_faces else C.Qt.Unchecked)
                    item.setToolTip('요소 ' + str(pair[0]) + ' / 면 ' + str(pair[1]) +
                                    ('' if tuple(pair) in known else ' · 현재 원본에 없는 선택'))
                    self.faces.addItem(item)
                frame = field['coordinate_frame']
                self.source_info.setToolTip(frame)
                self.source_info.setText('기준 좌표 / ' + ('전역 좌표계' if frame == 'FREECAD_DOCUMENT_GLOBAL' else frame) + '\n좌표 ' + field['units']['position'] +
                    ', 변위 ' + field['units']['displacement'] + '\n정적 단계 ' + str(self._static['step']) +
                    ', 증분 ' + str(self._static['increment']) + '\n하중 매개변수 ' + str(self._static['load_parameter']) + ' [1] (초 아님)')
                self._populating = False; self._edited()
            self._request('source', lambda: connection.client.structural_displacement_source(reference), received)

        def _selected_faces(self):
            return [deepcopy(self.faces.item(i).data(role)) for i in range(self.faces.count())
                    if self.faces.item(i).checkState() == C.Qt.Checked]

        def _select_all(self):
            for i in range(self.faces.count()): self.faces.item(i).setCheckState(C.Qt.Checked)

        def _use_selection(self):
            try:
                self._target = native.capture_selection(owner.fem)
                self.target_info.setText(owner._object(self._target['body_id']).Label + ': ' +
                    ', '.join('면 ' + name[4:] for name in self._target['faces']))
                self._edited()
            except Exception as error: self.message.setText(str(error))

        def _highlight(self):
            try:
                if not self._target: raise ValueError('변위를 적용할 면을 먼저 선택하세요.')
                from .fem_edit import _target
                obj = owner._object(self._target['body_id'])
                if native.canonical_capture(_target(obj, self._target['faces'])) != self._target['stamp']:
                    raise ValueError('변위를 적용할 형상이 바뀌었습니다. 면을 다시 선택하세요.')
                owner.Gui.Selection.clearSelection()
                for name in self._target['faces']: owner.Gui.Selection.addSelection(owner.doc.Name, obj.Name, name)
                owner.Gui.updateGui()
            except Exception as error: self.message.setText(str(error))

        def _open_source(self):
            reference = self.source.currentData()
            if not reference: return
            callback = getattr(connection, 'open_structural_displacement_source', None)
            if not callable(callback):
                self.message.setText('정확한 원본 결과 열기가 연결되지 않았습니다. 모델을 다시 연결하세요.'); return
            try: callback(deepcopy(reference))
            except Exception as error: self.message.setText(str(error))

        def current_draft(self):
            if self._unrepresented is not None: return deepcopy(self._unrepresented)
            original = self._raw_draft.get('definition', {})
            def number(field, value, integer=False):
                return deepcopy(value) if field.text() == str(value) else _number(field.text(), integer)
            draft = {'source_reference': deepcopy(self.source.currentData()), 'solver_id': self.solver.currentData(),
                    'target': deepcopy(self._target), 'components': [i + 1 for i, box in enumerate(self.components) if box.isChecked()],
                    'receiver_frame': self._receiver_frame,
                    'definition': {'source_faces': self._selected_faces(),
                        'rotation': [[number(v, original.get('rotation', [[1, 0, 0], [0, 1, 0], [0, 0, 1]])[i][j])
                                      for j, v in enumerate(row)] for i, row in enumerate(self.rotation)],
                        'translation': [number(v, original.get('translation', [0, 0, 0])[i]) for i, v in enumerate(self.translation)],
                        **{k: number(v, original.get(k, ''), k == 'max_iterations') for k, v in self.limits.items()},
                        'source_static': deepcopy(self._static)}}
            if self._replace_key: draft['replace_condition_ids'] = deepcopy(self._replace_condition_ids)
            return draft

        def pending_changes(self):
            return bool(self._loaded is not None and canonical_hash(self.current_draft()) != canonical_hash(self._loaded))

        def editor_token(self):
            return canonical_hash(self.current_draft())

        def _edited(self, *_):
            if self._populating: return
            self._epoch += 1; self._preview = None
            if getattr(self, '_displayed_preview', None):
                self.summary.setText('입력이 변경되었습니다. 표는 이전 확인값입니다. 변위를 다시 확인하세요.')
            self.message.setText('원본 범위를 확인하고 적용면을 선택하세요.' if self.steps.currentIndex() == 0 else
                '면과 변위 성분을 선택한 뒤 변위를 확인하세요.' if self.steps.currentIndex() == 1 else
                '입력이 바뀌었습니다. 변위를 다시 확인하세요.')
            self._enabled()

        def _load(self, draft):
            self._populating = True; self._source = None; self._preview = None; self._unrepresented = None
            self._raw_draft = deepcopy(draft)
            self._replace_condition_ids = deepcopy(draft.get('replace_condition_ids', []))
            self._replace_key = 'replace_condition_ids' in draft
            self._read_reference = deepcopy(draft.get('source_reference'))
            self.source_info.setText('결과 확인으로 저장한 좌표계와 단위와 현재 파일을 검토하세요.')
            self._target = deepcopy(draft.get('target')); definition = draft.get('definition', {})
            keys = {'source_reference', 'solver_id', 'target', 'components', 'receiver_frame', 'definition'}
            definition_keys = {'source_faces', 'rotation', 'translation', 'distance_tolerance',
                               'natural_tolerance', 'weight_tolerance', 'max_iterations', 'source_static'}
            represented = (keys <= set(draft) <= keys | {'replace_condition_ids'} and
                isinstance(self._replace_condition_ids, list) and
                all(isinstance(value, str) and value for value in self._replace_condition_ids) and
                len(self._replace_condition_ids) == len(set(self._replace_condition_ids)) and
                isinstance(definition, dict) and set(definition) == definition_keys and
                isinstance(draft.get('receiver_frame'), str) and isinstance(draft.get('components'), list) and
                all(type(v) is int and v in (1, 2, 3) for v in draft['components']) and
                len(draft['components']) == len(set(draft['components'])) and
                (draft.get('source_reference') is None or isinstance(draft['source_reference'], dict)) and
                isinstance(definition.get('source_faces'), list) and
                (definition.get('source_static') is None or isinstance(definition['source_static'], dict)) and
                all(isinstance(pair, list) and len(pair) == 2 for pair in definition['source_faces']) and
                (self._target is None or isinstance(self._target, dict) and set(self._target) == {'body_id', 'faces', 'stamp'} and
                 isinstance(self._target['faces'], list) and all(isinstance(n, str) for n in self._target['faces'])))
            rotation = definition.get('rotation') if isinstance(definition, dict) else None
            translation = definition.get('translation') if isinstance(definition, dict) else None
            if not represented or not isinstance(rotation, list) or len(rotation) != 3 or any(not isinstance(r, list) or len(r) != 3 for r in rotation) or not isinstance(translation, list) or len(translation) != 3:
                self._unrepresented = deepcopy(draft)
                self.message.setText('이 저장 초안의 변환 형식은 화면에서 편집할 수 없습니다. 원본은 유지되며 다시 구성하려면 기타 메뉴에서 가져온 변위 적용 해제를 사용하세요.')
                self._populating = False; self._loaded = deepcopy(draft); return
            reference = draft.get('source_reference'); index = self.source.findData(reference)
            if index < 0 and reference:
                self.source.addItem(((self._record or {}).get('accepted') or {}).get('source_label', '원본 결과'), deepcopy(reference)); index = self.source.count() - 1
            self.source.setCurrentIndex(max(0, index)); self.solver.setCurrentIndex(self.solver.findData(draft.get('solver_id')))
            self._static = deepcopy(definition.get('source_static'))
            self._receiver_frame = str(draft.get('receiver_frame', 'FREECAD_DOCUMENT_GLOBAL'))
            self.receiver_frame.setText('전역 좌표계' if self._receiver_frame == 'FREECAD_DOCUMENT_GLOBAL' else self._receiver_frame)
            self.receiver_frame.setToolTip(self._receiver_frame)
            for i, box in enumerate(self.components): box.setChecked(i + 1 in draft.get('components', [1, 2, 3]))
            for i, row in enumerate(self.rotation):
                for j, field in enumerate(row): field.setText(str(rotation[i][j]))
            for field, value in zip(self.translation, translation): field.setText(str(value))
            for key, field in self.limits.items(): field.setText(str(definition.get(key, '')))
            self.faces.clear()
            for i, pair in enumerate(definition.get('source_faces', [])):
                item = W.QListWidgetItem('선택한 원본 외부 면 ' + str(i + 1)); item.setData(role, deepcopy(pair))
                item.setFlags(item.flags() | C.Qt.ItemIsUserCheckable); item.setCheckState(C.Qt.Checked); self.faces.addItem(item)
            if self._target:
                try: label = owner._object(self._target['body_id']).Label
                except Exception: label = '선택한 물체'
                self.target_info.setText(label + '\n' + ', '.join('면 ' + n[4:] for n in self._target['faces']))
                self.target_info.setToolTip(str(self._target['body_id']))
            else: self.target_info.setText('아직 적용할 면을 선택하지 않았습니다.')
            if self._static:
                self.source_info.setText('저장한 원본 결과 · 정적 단계 ' + str(self._static.get('step')) +
                    ', 증분 ' + str(self._static.get('increment')) + ', 하중 매개변수 ' +
                    str(self._static.get('load_parameter')) + ' [1] (초 아님)\n결과 확인으로 현재 파일과 좌표계, 단위를 검토하세요.')
            self._populating = False; self._loaded = deepcopy(self.current_draft())

        def _accept_state(self, state):
            self._record = deepcopy(state['record'])
            self._replacement_conditions = deepcopy(state.get('replacement_conditions', self._replacement_conditions))
            draft = self._record['draft'] if self._record else {
                'source_reference': None, 'solver_id': self.solver.currentData(), 'target': None,
                'components': [1, 2, 3], 'receiver_frame': 'FREECAD_DOCUMENT_GLOBAL',
                'definition': {'source_faces': [], 'rotation': [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
                    'translation': [0, 0, 0], 'distance_tolerance': '', 'natural_tolerance': '',
                    'weight_tolerance': '', 'max_iterations': '', 'source_static': None}}
            self._load(draft)
            accepted = (self._record or {}).get('accepted')
            if isinstance(accepted, dict) and isinstance(accepted.get('preview'), dict):
                self._show_accepted(accepted, state['state'] == 'APPLIED')
            else: self.table.setRowCount(0); self.summary.setText('아직 적용하지 않았습니다. 적용할 면과 변위를 확인하세요.')
            self.message.setText('경계조건에 적용했습니다. 계산은 실행하지 않았습니다.' if state['state'] == 'APPLIED' else '변위를 확인한 뒤 경계조건에 적용하세요.')
            if self._catalog_error:
                self.source_info.setText('원본 목록을 읽지 못했습니다. 목록 다시 읽기로 복구하세요.\n' + self._catalog_error)

        def _send(self, name, args, accepted):
            if self._busy or not self._analysis_id: return
            context = self._context(); self._busy = True; self._enabled()
            delivered = False
            def done(value):
                nonlocal delivered
                delivered = True
                self._busy = False
                if self._context() != context or getattr(owner, 'closed', False):
                    self._enabled(); return
                try:
                    if value.get('status') == 'FAILED': raise ValueError(value.get('error', {}).get('message', '작업이 거절됐습니다.'))
                    accepted(value.get('result', value))
                except Exception as error: self.message.setText(str(error))
                self._enabled()
            try:
                value = connection.submit_native('pre.fem.displacement_' + name, args,
                    {'object_id': self._analysis_id}, on_done=done, owner=owner)
                if isinstance(value, dict) and not value.get('queued') and not delivered: done(value)
            except Exception as error:
                self._busy = False; self.message.setText(str(error)); self._enabled()

        def _operation(self, name, after=None):
            args = {'expected_revision': self._record.get('revision') if self._record else None}
            if name != 'remove': args['draft'] = self.current_draft()
            if name == 'apply': args['preview_sha256'] = self._preview['preview_sha256'] if self._preview else None
            def accepted(value):
                if name == 'preview':
                    self._preview = value if value['preview']['status'] == 'READY' else None
                    self._show_preview(value['preview']); self.steps.setCurrentIndex(2)
                    self.message.setText(value['preview'].get('error', '아직 적용하지 않았습니다. 값을 확인한 뒤 적용하세요.'))
                else: self._accept_state(value)
                if after: after()
            self._send(name, args, accepted)

        def _show_accepted(self, accepted, applied):
            preview = accepted['preview']
            self._show_preview(preview, previous=not applied)
            if not applied: return
            units = preview.get('units', {}); static = preview.get('static', {})
            frame = preview.get('source_frame', '미제공')
            self.source_info.setToolTip(str(frame))
            self.source_info.setText('저장한 원본 결과 / ' + ('전역 좌표계' if frame == 'FREECAD_DOCUMENT_GLOBAL' else str(frame)) +
                '\n좌표 ' + str(units.get('position', '미제공')) + ', 변위 ' + str(units.get('displacement', '미제공')) +
                '\n정적 단계 ' + str(static.get('step', '미제공')) + ', 증분 ' + str(static.get('increment', '미제공')) +
                '\n하중 매개변수 ' + str(static.get('load_parameter', '미제공')) + ' [1] (초 아님)' +
                '\n저장된 값입니다. 결과 확인으로 현재 파일을 검토하세요.')

        def _show_preview(self, preview, previous=False):
            rows = preview.get('rows', []); self.table.setRowCount(len(rows))
            self._displayed_preview = deepcopy(preview)
            for i, row in enumerate(rows):
                values = [row['node_id'], *row.get('position', [None] * 3), *row.get('displacement_mm', [None] * 3), '유효' if row.get('valid') is True else '지원 없음']
                for j, value in enumerate(values):
                    item = W.QTableWidgetItem('—' if value is None else format(value, '.6g') if isinstance(value, float) else str(value))
                    item.setToolTip(('—' if value is None else format(value, '.17g') if isinstance(value, float) else str(value)) +
                        ('\n' + str(row['error']) if row.get('error') else ''))
                    self.table.setItem(i, j, item)
            valid = sum(v is True for v in preview.get('mask', []))
            title = '이전 적용값 (현재 초안에는 미적용)' if previous else ('변위를 확인했습니다' if preview.get('status') == 'READY' else '적용할 수 없는 절점이 있습니다')
            self.summary.setText(title + '\n경계 절점 ' + str(valid) + ' / ' + str(len(preview.get('mask', []))) + '개 확인')
            self.summary.setToolTip('지정 변위 ' + str(len(preview.get('boundary_dofs', []))) + '개 / 공학 판정 미확인')
            self.table.resizeColumnsToContents()
            self.table.horizontalHeader().setStretchLastSection(True)

        def _details(self):
            row = self.table.currentRow(); preview = getattr(self, '_displayed_preview', {})
            if row < 0 or row >= len(preview.get('rows', [])): return
            import json
            value = preview['rows'][row]
            dialog = W.QDialog(self); dialog.setWindowTitle('선택 절점의 변위와 좌표'); dialog.resize(520, 460)
            layout = W.QVBoxLayout(dialog)
            heading = W.QLabel('적용할 경계 절점 ' + str(value['node_id'])); heading.setStyleSheet('font-weight:600;')
            layout.addWidget(heading)
            values = W.QTableWidget(6, 2); values.setHorizontalHeaderLabels(['항목', '값 [mm]'])
            values.setEditTriggers(W.QAbstractItemView.NoEditTriggers); values.verticalHeader().hide()
            for i, (label, number) in enumerate(zip(('X 좌표', 'Y 좌표', 'Z 좌표', 'X 변위', 'Y 변위', 'Z 변위'),
                    [*value.get('position', [None] * 3), *value.get('displacement_mm', [None] * 3)])):
                values.setItem(i, 0, W.QTableWidgetItem(label))
                values.setItem(i, 1, W.QTableWidgetItem('미제공' if number is None else format(number, '.17g')))
            values.horizontalHeader().setStretchLastSection(True); layout.addWidget(values)
            source_face = value.get('selected_source_face')
            if source_face:
                layout.addWidget(W.QLabel('원본 요소 ' + str(source_face[0]) + '의 면 ' + str(source_face[1]) + '에서 가져온 값입니다.'))
            if value.get('error'):
                issue = W.QLabel(str(value['error'])); issue.setWordWrap(True); layout.addWidget(issue)
            limitation = W.QLabel('이 표는 원본 결과에서 가져온 변위와 매핑 근거입니다. '
                '값을 확인하거나 경계조건에 적용한 것으로 구조 안전성이나 공학적 승인이 성립하지 않습니다. '
                '계산 입력을 만들 때 원본 결과와 적용면을 다시 확인합니다.')
            limitation.setWordWrap(True); layout.addWidget(limitation)
            text = W.QPlainTextEdit(); text.setReadOnly(True)
            text.setPlainText(json.dumps(value, ensure_ascii=False, indent=2)); text.hide()
            raw = W.QPushButton('원 매핑 진단 보기'); raw.setCheckable(True); raw.toggled.connect(text.setVisible)
            layout.addWidget(raw); layout.addWidget(text)
            close = W.QPushButton('닫기'); close.clicked.connect(dialog.accept); layout.addWidget(close)
            dialog.exec()

        def _cancel(self):
            if self._busy: return
            self._epoch += 1; self._preview = None
            if self._loaded is not None: self._load(deepcopy(self._loaded))
            accepted = (self._record or {}).get('accepted')
            if isinstance(accepted, dict) and isinstance(accepted.get('preview'), dict):
                self._show_accepted(accepted, canonical_hash(self.current_draft()) == accepted.get('draft_sha256'))
            else: self.table.setRowCount(0); self.summary.setText('편집을 취소했습니다. 적용한 정의와 기준 CAD는 바뀌지 않았습니다.')
            self.message.setText('저장하거나 적용하지 않은 편집을 취소했습니다.'); self._enabled()

        def _enabled(self):
            exists = bool(self._analysis_id); ready = exists and not self._busy
            for widget in (self.analysis, self.solver, self.source, self.read_source, self.use_selection,
                           self.highlight, self.receiver_frame, self.faces, self.advanced_button,
                           self.save, self.preview, self.cancel): widget.setEnabled(not self._busy and (exists or widget is self.analysis))
            self.all_faces.setEnabled(ready and self._source is not None)
            self.open_source.setEnabled(ready and bool(self.source.currentData()))
            self.apply.setEnabled(ready and self._preview is not None)
            self.remove.setEnabled(ready and self._record is not None)
            self.refresh_sources.setEnabled(not self._busy)
            self.reload.setEnabled(ready)
            self.close_button.setEnabled(not self._busy)
            self.advanced.setEnabled(ready and self._unrepresented is None)
            self.choose_faces.setEnabled(ready and self._source is not None and self._unrepresented is None)
            self.choose_replacements.setEnabled(ready and self._target is not None and self._unrepresented is None and
                                                bool(self._replacement_conditions or self._replace_condition_ids))
            self.reload_action.setEnabled(self.reload.isEnabled())
            self.remove_action.setEnabled(self.remove.isEnabled())
            for box in self.components: box.setEnabled(ready and self._unrepresented is None)
            if self._unrepresented is not None:
                for widget in (self.solver, self.source, self.read_source, self.use_selection,
                               self.highlight, self.faces, self.all_faces, self.advanced_button): widget.setEnabled(False)
            self._refresh_task()

    return Panel()
