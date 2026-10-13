"""Direct editor for the admitted native structural/explicit/material declarations.

Reuses the PDE document editor's typed fields, revision commands and actual
result selectors. It never exposes a general solver-card or Python editor.
"""
import argparse
import math
import os
import sys
from copy import deepcopy

from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import QApplication, QComboBox, QInputDialog, QLabel, QMessageBox, QPlainTextEdit, QPushButton, QToolBar
from caelab.workbench_client import Client
from caelab.simulation_document import BACKENDS, default_draft, diagnostics, support_details
from .pde_window import PDEWindow, ROLE, display

MODELS = {
    'explicit.opencourant.model': ('사용자 FE 충격 (OpenCourant)', '원 메시·밀도·초기 운동과 명시 TYPE24 접촉. 결과의 손상·수명은 별도 판정합니다.'),
    'structure.calculix.design': ('CAD 구조 해석 (CalculiX)', '저장한 Analysis의 편집 사본과 매핑된 참조를 사용합니다. 재메시 후 기존 CalculiX 계산으로 이어집니다.'),
    'structural.code_aster': ('단축 탄성 블록 (Code_Aster)', '지정한 3차원 탄성 블록의 치수·메시·인장 하중만 지원합니다. 임의 CAD 구조 해석이 아닙니다.'),
    'structural.code_aster.plasticity': ('J2 소성 블록 (Code_Aster)', '작은 변형률 J2 블록과 축방향 이력을 지원합니다. DP·손상·접촉은 지원하지 않습니다.'),
    'structural.code_aster.geometric_nonlinearity': ('기하 비선형 기준 모델 (Code_Aster)', '지정한 기하 비선형 모델과 원래의 기준 허용값을 사용합니다.'),
    'structural.code_aster.contact_patch': ('마찰 없는 접촉 패치 (Code_Aster)', 'SSNP121A 접촉 패치만 지원합니다. 일반 조립 접촉이나 예압 모델이 아닙니다.'),
    'structural.families.calculix': ('구조 기준 모델 (CalculiX)', '기존 외팔보·원통·곡선 솔리드의 고정된 기준 정의를 사용합니다.'),
    'structural.families.code_aster': ('구조 기준 모델 (Code_Aster)', '기존 외팔보·원통·곡선 솔리드의 고정된 기준 정의를 사용합니다.'),
    'explicit.openradioss': ('명시적 운동 모델 (OpenRadioss)', '강체 이동과 기존 탄성 스톱 형상 및 가속도 이력을 지원합니다. 일반 충돌 모델은 지원하지 않습니다.'),
    'material.mfront': ('탄성 재료점 (MFront)', '기존 작은 변형률 탄성 재료점의 적분과 접선 검사를 지원합니다.'),
    'material.mfront.inverse': ('재료점 역산 (MFront)', '기존 범위 제한 MFront 역산 입력과 관측 정의를 사용합니다.'),
    'material.mfront.hyperelastic': ('초탄성 재료점 (MFront)', '기존 유한 변형률 초탄성 재료점과 지정한 접선 규약을 사용합니다.'),
    'material.mfront.viscoelastic': ('Maxwell 점탄성 재료점 (MFront)', '단일 Maxwell 분기의 시간에 따른 회복을 지원합니다.'),
    'thermal.fenicsx.rectangle': ('직사각형 정상 열전도 (FEniCSx)', 'SI 단위의 직사각형 정상 열전도와 선택적 Picard 열전도율을 지원합니다.'),
    'structural.fenicsx.thermoelastic_rectangle': ('직사각형 열탄성 (FEniCSx)', 'SI 단위의 작은 변형률 평면응력 모델입니다. 온도장·열팽창계수·무응력 온도를 명시해야 합니다.'),
}

class _ModelChoice(QComboBox):
    """Human labels while the inherited backend API retains exact keys."""
    def currentText(self):
        if self.isEditable() and super().currentText() != self.itemText(self.currentIndex()):
            return super().currentText()
        return self.currentData() or super().currentText()

    def text(self):
        return self.currentText()

    def setText(self, text):
        self.setCurrentText(text)

    def setCurrentText(self, text):
        index = self.findData(text)
        if index < 0:
            self.addItem(str(text), text)
            index = self.count() - 1
        self.setCurrentIndex(index)


_CAPTIONS = {
    'case':'모델 종류', 'domain':'영역', 'geometry':'형상', 'type':'종류', 'unit':'단위',
    'dimensions_mm':'치수 [mm]', 'mesh_sizes_mm':'메시 크기 [mm]', 'lengths':'영역 길이',
    'cell_counts':'메시 분할 수', 'degree':'함수 공간 차수', 'origin':'원점', 'value':'값',
    'youngs_modulus_mpa':'탄성계수 [MPa]', 'poisson_ratio':'Poisson 비', 'yield_stress_mpa':'항복 응력 [MPa]',
    'plastic_modulus_mpa':'소성 계수 [MPa]', 'youngs_modulus_pa':'탄성계수 [Pa]',
    'times_s':'시간 [s]', 'axial_strain':'축 변형률 [1]', 'temperature':'온도 입력',
    'conductivity':'열전도율', 'heat_source':'체적 열원', 'boundary_temperature':'경계 온도',
    'stress_free_temperature':'무응력 온도', 'linearization_temperature':'이전 온도',
    'displacement_absolute_mm':'변위 절대 허용값 [mm]', 'displacement_relative':'변위 상대 허용값',
    'mesh_agreement_relative':'메시 상대 허용값', 'plastic_dissipation_absolute_mj':'소성 소산 절대 허용값 [mJ]',
    'plastic_dissipation_relative':'소성 소산 상대 허용값', 'plastic_strain_absolute':'소성 변형률 절대 허용값',
    'reaction_absolute_n':'반력 절대 허용값 [N]', 'reaction_relative':'반력 상대 허용값',
    'stress_absolute_mpa':'응력 절대 허용값 [MPa]', 'stress_relative':'응력 상대 허용값',
    'max_residual_relative':'상대 잔차 허용값', 'min_l2_rate':'최소 L2 수렴률',
    'max_l2_error':'L2 오차 허용값', 'max_h1_seminorm_error':'H1 반노름 오차 허용값',
    'source':'원본', 'sha256':'원본 확인값', 'data':'원본 데이터', 'analysis_id':'원본 해석 식별자',
    'input_provenance':'입력 출처', 'mode':'계산 방식', 'axis':'축', 'start':'시작', 'end':'끝',
    'time':'물리 시간', 'limits':'수치 허용값', 'density':'밀도', 'loads':'하중',
    'boundary_conditions':'경계 조건', 'material':'재료', 'constitutive':'구성식',
    'plastic_dissipation_absolute_mpa':'소성 소산 절대 허용값 [MPa]',
    'young_modulus':'탄성계수', 'young_modulus_unit':'탄성계수 단위',
    'poisson_ratio_unit':'Poisson 비 단위', 'thermal_expansion':'열팽창계수',
    'thermal_expansion_unit':'열팽창계수 단위', 'reference_temperature':'기준 온도',
    'reference_temperature_unit':'기준 온도 단위', 'reference_unit':'기준 온도 단위',
    'beta':'온도 의존 계수', 'beta_unit':'온도 의존 계수 단위',
    'edge_m':'모서리 길이 [m]', 'mass_kg':'질량 [kg]', 'center_height_m':'중심 높이 [m]',
    'initial_velocity_m_s':'초기 속도 [m/s]', 'end_time_s':'종료 시간 [s]',
    'time_step_s':'시간 간격 [s]', 'history_interval_s':'이력 출력 간격 [s]',
    'acceleration_history':'가속도 이력', 'time_s':'시간 [s]',
    'acceleration_z_m_s2':'z 가속도 [m/s²]', 'mass_relative':'질량 상대 허용값',
    'cells':'메시 분할 수', 'cell':'요소 형상', 'frame':'좌표계', 'reference':'출처 설명',
    'spring_stiffness_n_m':'스프링 강성 [N/m]', 'spring_mass_kg':'스프링 질량 [kg]',
}

_CHOICES = {
    'case': {'uniaxial_j2_isotropic_hardening':'단축 J2 등방 경화',
             'rigid_cube_freefall':'강체 자유 이동', 'rigid_cube_compliant_stop':'강체와 탄성 스톱',
             'ssnp121a_frictionless_patch':'SSNP121A 마찰 없는 접촉 패치'},
    'mode': {'selected_mesh':'선택 메시', 'selected_history':'지정 이력'},
    'origin': {'ASSUMED':'가정한 입력'},
}


class SimulationWindow(PDEWindow):
    document_kind, tool_label = 'simulation', '해석'
    model_backends = BACKENDS
    model_default, model_diagnostics, model_support = map(staticmethod, (default_draft, diagnostics, support_details))
    settings_sections = [(label, ('settings', name)) for name, label in (
        ('domain', '영역'), ('case', '모델 종류'),
        ('geometry', '형상'), ('mesh', '메시와 함수 공간'),
        ('material', '재료'), ('constitutive', '구성식'),
        ('history', '하중과 변형 이력'), ('time', '물리 시간'),
        ('conductivity', '열전도율'), ('heat_source', '체적 열원'),
        ('boundary_temperature', '경계 온도'), ('temperature', '온도 입력'),
        ('linearization_temperature', '이전 온도'), ('limits', '수치 허용값'),
        ('validation', '수치 판정 기준'), ('analysis', '해석 조건'),
        ('loads', '하중'), ('boundary_conditions', '경계 조건'))]

    @staticmethod
    def field_label(path):
        key = path[-1]
        if 'input_provenance' in path and key in ('origin', 'reference'):
            return '입력 유형' if key == 'origin' else '자료 참조'
        if isinstance(key, int):
            parent = next((k for k in reversed(path[:-1]) if isinstance(k, str)), '')
            return _CAPTIONS.get(parent, parent.replace('_', ' ')) + ' ' + str(key + 1)
        return _CAPTIONS.get(key, str(key).replace('_', ' '))

    def _build_ui(self):
        from .appearance import configure_plot_fonts
        configure_plot_fonts()
        super()._build_ui()
        self.new_action.setText('새 해석 모델…')
        self.open_action.setText('해석 모델 열기…')
        self.identity.setText('해석 모델을 여는 중…')
        self.validate_button.setText('입력 검사')
        self.plan_button.setObjectName('simulationNumericalPlan')
        self.readiness_button = QPushButton('계산 환경 확인')
        self.readiness_button.setToolTip('기존 설치와 버전만 확인합니다. 계산을 시작하지 않습니다.')
        self.readiness_button.clicked.connect(self.inspect_runtime)
        self.statusBar().addPermanentWidget(self.readiness_button)
        self._model_graph_available = False
        self._preview_graph_sizes = [205, 360, 835]
        self.model_splitter.setSizes([205, 360, 835])
        toolbar = self.findChild(QToolBar)
        self._secondary_toolbar_actions = []
        for action in list(toolbar.actions()):
            if action is self.save_action or toolbar.widgetForAction(action) in (self.apply_button, self.evaluate_button):
                continue
            toolbar.removeAction(action)
            self._secondary_toolbar_actions.append(action)
        self._menu_refs = self.menuBar().actions()
        self._menus = [action.menu() for action in self._menu_refs]
        edit_menu, research_menu = self._menus[1:3]
        self._command_actions = []
        for button, menu, shortcut in ((self.apply_button, edit_menu, 'Ctrl+Return'),
                                       (self.validate_button, research_menu, None),
                                       (self.evaluate_button, research_menu, 'F5')):
            action = QAction(button.text(), self)
            if shortcut: action.setShortcut(QKeySequence(shortcut))
            action.triggered.connect(button.click)
            menu.addAction(action)
            self._command_actions.append((button, action))
        self.plan_button.hide()
        self.validate_button.hide()
        old = self.backend
        choice = _ModelChoice()
        choice.setEditable(True)
        for key in self.model_backends:
            choice.addItem(MODELS.get(key, (key, ''))[0], key)
        self.settings_panel.layout().replaceWidget(old, choice)
        old.hide(); old.deleteLater()
        self.backend = choice
        choice.setObjectName('pdeBackend')
        choice.currentTextChanged.connect(self._backend_changed)
        self.reload_button.setText('저장 버전 다시 읽기')
        self.copy_button.setText('편집본을 새 모델로 보관')
        self.impact_action = QAction('충격 조건…', self)
        self.impact_action.triggered.connect(lambda: __import__('apps.research.impact_editor', fromlist=['edit']).edit(self))
        research_menu.addAction(self.impact_action)
        self._update_actions()

    def inspect_runtime(self):
        backend = self.edited_draft().get('backend')
        def accepted(result):
            self.messages.appendPlainText('계산 환경: ' + str(backend) + '\n' + display(result))
            state = result.get('dependencies')
            self.message.setText({'READY':'필요한 설치를 찾았습니다. 실제 계산과 공학 판정은 수행하지 않았습니다.',
                'UNAVAILABLE':'계산 환경을 찾지 못했습니다. 기술 상세에서 설치 경로와 오류를 확인하세요.'}.get(state,
                '계산 환경을 확인하지 못했습니다. 기술 상세를 확인하세요.'))
        return self._call(lambda: self.client.backend_readiness(backend), accepted)

    def _show_document(self, document, *, preserve_draft=None):
        # Include every existing adapter setting as a normal editable section;
        # model validation, not a copied schema, decides admission.
        draft = preserve_draft if preserve_draft is not None else document['draft']
        if not self.document or self.document['id'] != document['id']:
            self._numeric_paths = set()
        settings = draft.get('settings', {})
        base = type(self).settings_sections
        known = {path[-1] for _, path in base}
        self.settings_sections = base + [(self.field_label(('settings', k)), ('settings', k))
            for k in settings if k not in known] if isinstance(settings, dict) else base
        super()._show_document(document, preserve_draft=preserve_draft)
        for path, node in self._nodes.items():
            if len(path) > 2:
                caption = self.field_label(path)
                node.setText(0, caption)
                data = node.data(0, ROLE)
                data['label'] = caption
                node.setData(0, ROLE, data)
        for path in (('settings', 'limits'), ('settings', 'validation'), ('settings', 'input_provenance')):
            node = self._nodes.get(path)
            if node: node.setExpanded(False)
        selected = self.tree.currentItem()
        if selected:
            self.settings_title.setText('속성 — ' + selected.text(0))
        self.setWindowTitle(document['title'] + ' — ' + self.tool_label)

    def _show_support(self, draft=None, checks=None, details=None):
        draft = self._draft if draft is None else draft
        details = details if details is not None else self.document.get('simulation_support', {}) if self.document else {}
        checks = self.model_diagnostics(draft) if checks is None else checks
        backend = draft.get('backend', '')
        label, limit = MODELS.get(backend, (str(backend), '지원하지 않는 모델입니다. 입력은 보관할 수 있습니다.')) if isinstance(backend, str) else (
            display(backend), '잘못된 모델 선택입니다. 원 입력은 보관할 수 있습니다.')
        self.equation.clear()
        self.equation.hide()
        self.equation.setToolTip(label)
        self.space.setText('준정적 입력 경로이며 관성·속도 의존 응답은 계산하지 않습니다.' if backend == 'structural.code_aster.plasticity' else '')
        self.space.setVisible(bool(self.space.text()))
        self.support.setText(limit)
        self.messages.setPlainText('\n'.join(['Input diagnostics:', *[row['message'] for row in checks],
            'Supported model:', *details.get('limitations', []), 'Declared inputs / transfer ports:',
            display(details.get('declaration') or details.get('ports') or {}),
            '계산 환경은 별도 확인이 필요합니다. 입력 검사는 공학적 승인이 아닙니다.']))
        self._input_checks = deepcopy(checks)
        self._refresh_issue_summary()

    def _backend_changed(self, text):
        super()._backend_changed(self.backend.currentText())
        if not self._populating:
            self._show_support(self.edited_draft())

    def edited_draft(self):
        draft = super().edited_draft()
        # A partial numeric edit may become the original string on node changes.
        from .pde_window import display, set_path, typed_value
        numeric = {'times_s', 'axial_strain', 'time_s', 'acceleration_z_m_s2',
                   'young_modulus', 'thermal_expansion', 'poisson_ratio', 'beta',
                   'reference_temperature', 'mass_relative'}
        for path, (field, original) in self.fields.items():
            key = next((k for k in reversed(path) if isinstance(k, str)), '')
            if isinstance(original, str) and (path in getattr(self, '_numeric_paths', set()) or
                    key in numeric or '[' in _CAPTIONS.get(key, '') or
                    key == 'value' and len(path)>2 and path[-2] in ('conductivity','heat_source','boundary_temperature','time')):
                text = field.toPlainText() if isinstance(field, QPlainTextEdit) else field.text()
                if text != display(original):
                    set_path(draft, path, typed_value(text, 0., path))
        return draft

    def _edited(self, *_):
        super()._edited()
        if not self._populating:
            self._draw_domain()

    def _add_fields(self, form, value, path):
        if type(value) in (int, float):
            self._numeric_paths = getattr(self, '_numeric_paths', set())
            self._numeric_paths.add(path)
        if self._draft.get('backend') == 'explicit.opencourant.model':
            if path[1:2] == ('source',) or len(path)>1 and path[1] in ('motions','contacts','time','gravity_mm_s2'):
                if path == ('settings','source'):
                    source=self._draft['settings']['source']
                    form.addRow(QLabel(source.get('title') or '유한요소 모델 미선택'))
                button=QPushButton('충격 조건…')
                button.clicked.connect(lambda: __import__('apps.research.impact_editor',fromlist=['edit']).edit(self))
                form.addRow(button)
                return
        choices = _CHOICES.get(path[-1])
        if choices and isinstance(value, str):
            field = _ModelChoice()
            field.setEditable(True)
            for raw, caption in choices.items(): field.addItem(caption, raw)
            field.setCurrentText(value)
            field.setToolTip('.'.join(map(str, path[1:])))
            field.currentTextChanged.connect(self._edited)
            self.fields[path] = (field, value)
            form.addRow(QLabel(self.field_label(path)), field)
        else:
            super()._add_fields(form, value, path)

    def _update_actions(self):
        super()._update_actions()
        for button, action in getattr(self, '_command_actions', []):
            action.setEnabled(button.isEnabled())
        graph = self.model_splitter.widget(2)
        if hasattr(self, '_model_graph_available'):
            show = self._model_graph_available or bool(self._selected_job)
            self.model_splitter.setStretchFactor(1, 0 if show else 1)
            self.model_splitter.setStretchFactor(2, 1 if show else 0)
            was_hidden = graph.isHidden()
            if not show and not was_hidden:
                if self.isVisible():
                    self._preview_graph_sizes = self.model_splitter.sizes()
                total = sum(self._preview_graph_sizes)
                graph.hide()
                self.model_splitter.setSizes([self._preview_graph_sizes[0], total-self._preview_graph_sizes[0], 0])
            elif show and was_hidden:
                graph.show()
                self.model_splitter.setSizes(getattr(self, '_preview_graph_sizes', [205, 360, 835]))
        if hasattr(self, 'impact_action'):
            self.impact_action.setEnabled(not self._busy and self._draft.get('backend') == 'explicit.opencourant.model')
        if hasattr(self, 'readiness_button'):
            self.readiness_button.setEnabled(not self._busy)

    def _refresh_issue_summary(self):
        super()._refresh_issue_summary()
        text = self.issue_summary.text()
        for key, caption in _CAPTIONS.items():
            if text == key + ' must be a finite number':
                self.issue_summary.setText(caption + ': 유한한 숫자를 입력하세요.')
                return
        if text == 'Choose a supported simulation backend and an editable settings object':
            self.issue_summary.setText('지원 모델과 조건 값을 확인하세요. 원 입력은 보관할 수 있습니다.')

    def new_document(self):
        keys = list(self.model_backends)
        labels = [MODELS.get(key, (key, ''))[0] for key in keys]
        selected, ok = QInputDialog.getItem(self, '새 해석 모델', '지원 모델', labels, 0, False)
        if ok:
            self._abandon(lambda: self.open_document(title=selected, draft=self.model_default(keys[labels.index(selected)])))

    def open_document(self, *, document_id=None, title=None, draft=None):
        return super().open_document(document_id=document_id, title=title or self.tool_label + ' 모델', draft=draft)

    def copy_edits(self):
        self.open_document(title=self.document['title'] + ' 편집본', draft=self.edited_draft())

    def _abandon(self, after):
        if not self.local_dirty and not (self.document and self.document.get('dirty')):
            after(); return True
        answer = QMessageBox.question(self, self.tool_label + ' 모델', '다른 모델로 이동하거나 닫기 전에 현재 모델을 저장할까요?',
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel)
        if answer == QMessageBox.StandardButton.Save:
            self.save_document(after=after); return False
        if answer == QMessageBox.StandardButton.Discard:
            after(); return True
        return False

    def reload_remote(self):
        if QMessageBox.question(self, '저장 버전 다시 읽기', '적용 전 편집을 버리고 현재 저장 버전을 다시 읽을까요?',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel) == QMessageBox.StandardButton.Yes:
            self._call(lambda: self.client.document_read(self.document['id']), self._opened)

    def closeEvent(self, event):
        if self._allow_close:
            event.accept()
        elif self._busy:
            self.message.setText('현재 요청이 끝난 뒤 창을 닫아 주세요.')
            event.ignore()
        elif self.local_dirty or self.document and self.document.get('dirty'):
            answer = QMessageBox.question(self, self.tool_label + ' 모델 닫기', '닫기 전에 현재 모델을 저장할까요?',
                QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel)
            if answer == QMessageBox.StandardButton.Save:
                event.ignore()
                def saved():
                    self._allow_close = True
                    self.close()
                self.save_document(after=saved)
            elif answer == QMessageBox.StandardButton.Discard:
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()

    def choose_document(self):
        def accepted(documents):
            if isinstance(documents, dict): documents = documents.get('documents', [])
            rows = [row for row in documents if row.get('kind') == self.document_kind]
            labels = [str(i + 1) + '. ' + row.get('title', '해석 모델') for i, row in enumerate(rows)]
            if not labels:
                self.message.setText('저장된 ' + self.tool_label + ' 모델이 없습니다.'); return
            selected, ok = QInputDialog.getItem(self, self.tool_label + ' 모델 열기', '모델', labels, 0, False)
            if ok:
                self._abandon(lambda: self.open_document(document_id=rows[labels.index(selected)]['id']))
        return self._call(self.client.documents, accepted)

    def _draw_domain(self, path=None):
        axes = self.domain_axes
        axes.clear()
        axes.set_aspect('auto')
        self._model_graph_available = False
        settings = self.edited_draft().get('settings', {})
        domain = settings.get('domain', {}) if isinstance(settings, dict) else {}
        lengths = domain.get('lengths') if isinstance(domain, dict) else None
        if self._draft.get('backend') == 'explicit.opencourant.model':
            try:
                from caelab.impact_model import parse_inp
                model=parse_inp(settings['source']['text'])
                points=list(model['nodes'].values())
                stride=max(1,len(points)//10000); points=points[::stride]
                axes.scatter([p[0] for p in points],[p[2] for p in points],s=4,color='#2563eb')
                axes.set_aspect('equal'); axes.set_xlabel('X [mm]'); axes.set_ylabel('Z [mm]')
                axes.set_title('원 입력 메시 / XZ 투영')
                self._model_graph_available=True
            except (ValueError,KeyError,TypeError):
                axes.set_axis_off(); axes.text(.5,.5,'충격 조건에서 유한요소 메시를 선택하세요',ha='center',va='center',transform=axes.transAxes)
            self.domain_canvas.draw_idle(); self._update_actions(); return
        if isinstance(lengths, list) and len(lengths) == 2 and all(type(x) in (int, float) and math.isfinite(x) and x > 0 for x in lengths):
            x, y = lengths
            axes.plot([0, x, x, 0, 0], [0, 0, y, y, 0], color='#334155')
            axes.set_aspect('equal')
            axes.set_xlabel('x [' + str(domain.get('unit', '?')) + ']')
            axes.set_ylabel('y [' + str(domain.get('unit', '?')) + ']')
            axes.set_title('입력 영역 (계산 변형 아님)')
            self._model_graph_available = True
        else:
            history = settings.get('history', settings.get('acceleration_history', {})) if isinstance(settings, dict) else {}
            acceleration = 'acceleration_z_m_s2' in history if isinstance(history, dict) else False
            times, values = (history.get('time_s' if acceleration else 'times_s'), history.get(
                'acceleration_z_m_s2' if acceleration else 'axial_strain')) if isinstance(history, dict) else (None, None)
            if isinstance(times, list) and isinstance(values, list) and len(times) == len(values) and len(times) > 1 and all(
                    type(x) in (int, float) and math.isfinite(x) for x in times + values):
                axes.plot(times, values, marker='o', color='#2563eb')
                axes.set_xlabel('시간 [s]'); axes.set_ylabel('입력 z 가속도 [m/s²]' if acceleration else '입력 축 변형률 [1]')
                axes.set_title('입력 가속도 이력 (계산 결과 아님)' if acceleration else '입력 축변형률 이력 (계산 결과 아님)')
                self._model_graph_available = True
            else:
                axes.set_axis_off()
        self.domain_canvas.draw_idle()
        self._update_actions()


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--service', default=os.environ.get('CAELAB_SERVICE_URL'))
    parser.add_argument('--document-id')
    options = parser.parse_args(argv)
    if not options.service:
        parser.error('--service or CAELAB_SERVICE_URL is required')
    from .desktop import launch_tool, open_document_result, open_domain_plan
    client = Client(options.service)
    app = QApplication.instance() or QApplication(sys.argv[:1])
    window = SimulationWindow(client, document_id=options.document_id,
        runner_open=lambda job: launch_tool(client, 'runner', job_id=job),
        result_open=lambda doc, job, **kwargs: open_document_result(client, doc, job, **kwargs),
        plan_open=lambda doc, **kwargs: open_domain_plan(client, doc, **kwargs))
    window.show()
    return app.exec()


if __name__ == '__main__':
    raise SystemExit(main())
