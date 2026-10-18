"""Direct editor for the admitted native structural/explicit/material declarations.

Reuses the PDE document editor's typed fields, revision commands and actual
result selectors. It never exposes a general solver-card or Python editor.
"""
import argparse
import math
import os
import sys
import uuid
from copy import deepcopy

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import QApplication, QComboBox, QInputDialog, QLabel, QMessageBox, QPlainTextEdit, QPushButton, QToolBar, QToolButton, QStyle
from caelab.workbench_client import Client, WorkbenchHTTPError
from caelab.simulation_document import BACKENDS, default_draft, diagnostics, support_details
from .pde_window import PDEWindow, ROLE, display

NATIVE_MODELS = {
    'explicit.opencourant.connector': ('스프링과 댐퍼 해석', '선택한 두 대상의 국부 6모드 스프링·댐퍼 입력을 사용합니다.'),
    'structure.calculix.pretension': ('볼트 체결 해석', '전처리에서 준비한 체결과 후속 하중 단계를 사용합니다.'),
    'structure.calculix.shell.composite': ('적층 셸 해석', '원 모델의 적층 순서·재료·방향을 보관한 입력을 사용합니다.'),
}


def _is_native(backend):
    return isinstance(backend, str) and backend in NATIVE_MODELS

CONNECTOR_RESPONSES = {
    **{'connector.F'+axis: '국부 일반화 힘 '+axis+'' for axis in 'XYZ'},
    **{'connector.M'+axis: '국부 일반화 모멘트 '+axis+'' for axis in 'XYZ'},
    'connector.LX': '축 신장', 'connector.LY': 'beam 전단 변형 Y', 'connector.LZ': 'beam 전단 변형 Z',
    **{'connector.R'+axis: '상대 회전 '+axis+'' for axis in 'XYZ'},
    'connector.LENGTH': '전체 길이', 'connector.IE': '점성항 포함 내부 일',
    'connector.OFF': '원 OFF 플래그',
}

MODELS = {**NATIVE_MODELS,
    'thermal.scikit_fem.rectangle': ('정상 열전도 (scikit-fem)', 'P1 공간 열전도, SI 온도, 명시한 정상 상태. 기존 Picard 반복을 사용합니다.'),
    'structural.scikit_fem.thermoelastic_rectangle': ('평면응력 열탄성 (scikit-fem)', '다른 메시의 온도 전달, 구조 기준온도, 미소변형 변위 [m]와 응력 [Pa].'),
    'structure.felupe.law_native': ('저장 재료 · FELUPE Hex8 시편', '준정적 Hex8: DP / Neo-Hooke / 단일 branch Maxwell. 실제 실행과 point–FE 검증은 결과에서 확인합니다.'),
    'damage.rainflow': ('반복하중 피로 평가', 'S–N/Miner, total-strain CMB/NONE, 단축 SWT와 최대 정상변형률 범위 면 CP-SWT. 명시 교정 범위·동시 이력이며 실재 재료 승인과 별도.'),
    'explicit.opencourant.model': ('사용자 FE 충격 (OpenCourant)', '원 메시·밀도·초기 운동, TYPE24 접촉과 LAW117 응집 손상. 수명·공학 승인은 별도입니다.'),
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
    'sn_curve':'S–N 시험 자료','calibration':'적용 시험 조건','temperature_k':'평가 온도 [K]',
    'repeat_block':'반복 블록 가정','cohesive':'응집 손상','motions':'초기 운동','contacts':'접촉','gravity_mm_s2':'중력',
    'generated_sets':'생성 집합','qualification':'계산 적용 범위','text':'입력 원문','provenance':'기술 출처',
    'end_s':'종료 시간 [s]','field_interval_s':'장 출력 간격 [s]','scale':'시간증분 계수','responses':'결과 이력',
    'mass_scaling':'질량 스케일링','target_step_s':'목표 증분 [s]',
    'case':'모델 종류', 'domain':'영역', 'geometry':'형상', 'type':'종류', 'unit':'단위',
    'dimensions_mm':'치수 [mm]', 'mesh_sizes_mm':'메시 크기 [mm]', 'lengths':'영역 길이',
    'cell_counts':'메시 분할 수', 'degree':'함수 공간 차수', 'origin':'원점', 'value':'값',
    'youngs_modulus_mpa':'탄성계수 [MPa]', 'poisson_ratio':'Poisson 비', 'yield_stress_mpa':'항복 응력 [MPa]',
    'plastic_modulus_mpa':'소성 계수 [MPa]', 'youngs_modulus_pa':'탄성계수 [Pa]',
    'times_s':'시간 [s]', 'axial_strain':'축 변형률 [1]', 'temperature':'온도 입력',
    'boundary_gradient':'경계 온도 공간 기울기 [K/m]', 'temperature_mode':'온도 입력 의미',
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
    'temperature_mode': {'absolute':'절대 온도 [K] — 구조 기준온도를 한 번 뺌', 'difference':'온도차 [ΔK] — 기준온도 출처를 확인하고 그대로 사용'},
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
        ('boundary_temperature', '경계 온도'), ('boundary_gradient', '경계 온도 기울기'),
        ('temperature_mode', '온도 입력 의미'), ('temperature', '온도 입력'),
        ('linearization_temperature', '이전 온도'), ('limits', '수치 허용값'),
        ('validation', '수치 판정 기준'), ('analysis', '해석 조건'),
        ('loads', '하중'), ('boundary_conditions', '경계 조건'))]

    def field_label(self,path):
        key = path[-1]
        if (getattr(self,'_draft',{}).get('backend')=='structure.felupe.law_native'
                and tuple(path[:3])==('settings','mesh','cells')):
            if len(path)==3:return '요소 연결'
            return ('요소 ' if len(path)==4 else '연결 절점 ')+str(key+1)
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
        self._backend_note = next((label for label in self.settings_panel.findChildren(QLabel)
            if label.text() == '계산 방법 선택은 모델을 자동 변환하지 않습니다.'), None)
        self.input_model_action = QAction(self.style().standardIcon(QStyle.StandardPixmap.SP_DirOpenIcon), '입력 모델 열기', self)
        self.input_model_action.setToolTip('이 해석에 보관된 편집 가능한 입력 사본을 FreeCAD에서 엽니다.')
        self.input_model_action.triggered.connect(self.open_input_model)
        edit_menu.addAction(self.input_model_action)
        self.reload_button.setText('저장 버전 다시 읽기')
        self.copy_button.setText('편집본을 새 모델로 보관')
        self.impact_action = QAction('충격 조건…', self)
        self.impact_action.triggered.connect(lambda: __import__('apps.research.impact_editor', fromlist=['edit']).edit(self))
        research_menu.addAction(self.impact_action)
        self.fatigue_action=QAction('반복하중 조건…',self)
        self.fatigue_action.triggered.connect(lambda:__import__('apps.research.fatigue_editor',fromlist=['edit']).edit(self))
        research_menu.addAction(self.fatigue_action)
        self.cycles_action=QAction('사이클과 누적값…',self)
        self.cycles_action.triggered.connect(self.read_fatigue_cycles);research_menu.addAction(self.cycles_action)
        self._impact_read_requests = {}
        self.reprocess_impact_action = QAction('보존 결과 다시 읽기…', self)
        self.reprocess_impact_action.setObjectName('impactReprocessAction')
        self.reprocess_impact_action.setToolTip('선택한 계산의 원 출력을 별도 작업으로 읽습니다. 솔버 계산은 시작하지 않습니다.')
        self.reprocess_impact_action.triggered.connect(self.reprocess_impact)
        research_menu.addAction(self.reprocess_impact_action)
        self.interface_history_action = QAction('계면 이력 관측…', self)
        self.interface_history_action.triggered.connect(self.show_interface_history)
        research_menu.addAction(self.interface_history_action)
        self.impact_history_action=QAction('충격 이력 선택…',self)
        self.impact_history_action.triggered.connect(self.show_impact_history)
        research_menu.addAction(self.impact_history_action)
        self._history_commands={}
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
        if draft.get('backend') in ('explicit.opencourant.model','damage.rainflow'):
            for path,node in self._nodes.items():
                if len(path)>2 or path==('settings','qualification'):node.setHidden(True)
                elif len(path)==2:node.setExpanded(False)
        if draft.get('backend')=='damage.rainflow':
            # One task entry opens the dedicated editor; technical fields stay
            # in the existing diagnostics rather than duplicating that editor.
            for path,node in self._nodes.items():
                node.setHidden(path!=('settings','calibration'))
            fatigue_node=self._nodes.get(('settings','calibration'))
            if fatigue_node:
                fatigue_node.setText(0,'피로 조건')
                data=fatigue_node.data(0,ROLE);data['label']='피로 조건';fatigue_node.setData(0,ROLE,data)
                self.tree.setCurrentItem(fatigue_node)
        native = _is_native(draft.get('backend'))
        self.backend.setVisible(not native)
        if self._backend_note is not None: self._backend_note.setVisible(not native)
        if native:
            for path, node in self._nodes.items():
                node.setHidden(path != ('settings', 'data_id'))
            input_node = self._nodes.get(('settings', 'data_id'))
            if input_node is not None:
                input_node.setText(0, '입력 모델')
                data = input_node.data(0, ROLE); data['label'] = '입력 모델'; input_node.setData(0, ROLE, data)
                if not (self.tree.currentItem() and self.tree.currentItem().data(0, ROLE).get('job_id')):
                    self.tree.setCurrentItem(input_node)
                    self._selection_changed(input_node)
        self.graph_tabs.setTabVisible(self.graph_tabs.indexOf(self.domain_canvas),not native and draft.get('backend')!='damage.rainflow')
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
            *(['보관된 입력 정의:', display(draft)] if _is_native(backend) else []),
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
                    ('boundary_gradient' in path and draft.get('backend')=='thermal.scikit_fem.rectangle') or
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
        if _is_native(self._draft.get('backend')) and path[:1] == ('settings',):
            title = QLabel(self.document.get('title') or NATIVE_MODELS[self._draft['backend']][0]); title.setWordWrap(True)
            form.addRow(title)
            family = QLabel(NATIVE_MODELS[self._draft['backend']][0]); family.setWordWrap(True); form.addRow(family)
            state = QLabel('전처리에서 보관한 입력을 사용합니다.' if self._native_input_id() else '보관된 입력을 확인할 수 없습니다. 전처리에서 해석 입력을 다시 준비하세요.')
            state.setWordWrap(True); form.addRow(state)
            button = QToolButton(); button.setDefaultAction(self.input_model_action)
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon); form.addRow(button)
            note = QLabel('모델과 조건 편집은 입력 사본에서 진행합니다. 변경한 입력은 전처리에서 다시 준비해 해석으로 여세요.'); note.setWordWrap(True); form.addRow(note)
            return
        if self._draft.get('backend') == 'explicit.opencourant.model':
            if path[1:2] == ('source',) or len(path)>1 and path[1] in ('motions','contacts','cohesive','responses','time','gravity_mm_s2','generated_sets'):
                if path == ('settings','source'):
                    source=self._draft['settings']['source']
                    form.addRow(QLabel(source.get('title') or '유한요소 모델 미선택'))
                    details=QPushButton('원문과 출처…')
                    details.clicked.connect(self.impact_details);form.addRow(details)
                button=QPushButton('충격 조건…')
                button.clicked.connect(lambda: __import__('apps.research.impact_editor',fromlist=['edit']).edit(self))
                form.addRow(button)
                return
        if self._draft.get('backend')=='damage.rainflow':
            settings=self._draft.get('settings',{})
            source=settings.get('source') or {}
            method=('CP-SWT 최대 정상변형률 범위 면' if settings.get('method')=='CP_SWT' else
                '단축 SWT' if settings.get('mean_stress')=='SWT' else '단축 전체 변형률 CMB' if 'method' in settings else 'S–N 응력 수명')
            calibration=settings.get('calibration',{})
            summary=QLabel(method+'\n'+str(source.get('title') or '보존 이력 선택 필요'))
            summary.setWordWrap(True);form.addRow(summary)
            if 'method' in settings:
                limits=QLabel('교정 수명: '+str(calibration.get('cycles_min') or '미입력')+'–'+
                    str(calibration.get('cycles_max') or '미입력')+' 사이클')
                limits.setWordWrap(True);form.addRow(limits)
            button=QPushButton('반복하중 조건…')
            button.clicked.connect(lambda:__import__('apps.research.fatigue_editor',fromlist=['edit']).edit(self))
            form.addRow(button);return
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

    def _native_input_id(self):
        settings = self._draft.get('settings')
        value = settings.get('data_id') if isinstance(settings, dict) else None
        from caelab.storage import check_id
        try: return check_id(value) if isinstance(value, str) and value else None
        except (ValueError, TypeError): return None

    def open_input_model(self):
        if (not self.document or self._busy or self.conflict or self.local_dirty
                or not _is_native(self._draft.get('backend')) or not self._native_input_id()):
            self.message.setText('현재 보관된 해석 입력을 선택하고 편집을 적용한 뒤 여세요.'); return False
        from .desktop import open_native_input
        key = (self.document['id'], self.document['session_id'], self.document['generation'], self._native_input_id())
        def accepted(result):
            current = (self.document['id'], self.document['session_id'], self.document['generation'], self._native_input_id()) if self.document else None
            if current != key: return
            self.message.setText('입력 모델 열기를 요청했습니다. 별도 FreeCAD 창에서 보관된 사본을 확인하세요.')
        return self._call(lambda: open_native_input(self.client, key[3]), accepted)

    def _accept_result(self, result):
        super()._accept_result(result)
        if not _is_native(self._draft.get('backend')): return
        channels = (self._result or {}).get('native_channels', {})
        for index in range(self.channel.count()):
            key = self.channel.itemData(index); descriptor = channels.get(key, {})
            label = descriptor.get('label') or (CONNECTOR_RESPONSES.get(key) if self._draft.get('backend') == 'explicit.opencourant.connector' else None)
            if label: self.channel.setItemText(index, label+' ['+str(descriptor.get('unit') or '단위 미확인')+']')

    def response_caption(self, name, response):
        from .law_native_labels import response_label
        caption=response_label(name,self._result or {})
        if caption:return caption
        if self._result and self._result.get('backend') == 'explicit.opencourant.connector' and name in CONNECTOR_RESPONSES:
            return CONNECTOR_RESPONSES[name]
        caption = super().response_caption(name, response)
        if caption == name and self._result and self._result.get('backend') == 'damage.rainflow' and name == 'stress_history':
            return '원 응력 이력'
        return caption

    def axis_caption(self, axis):
        if self._result and _is_native(self._result.get('backend')) and axis.get('name') == 'time': return '시간'
        if self._result and self._result.get('backend') == 'damage.rainflow' and axis.get('name') == 'cycle_count_record':
            return '사이클 기록 번호'
        return super().axis_caption(axis)

    def read_fatigue_cycles(self):
        if not self.document or not self._selected_job:return
        key=(self.document['id'],self._selected_job)
        def accepted(result):
            if not self.document or (self.document['id'],self._selected_job)!=key:return
            if result.get('backend')!='damage.rainflow':
                self.message.setText('반복하중 평가 결과를 선택하세요');return
            from .fatigue_editor import show_cycles
            show_cycles(self,result)
        self._call(lambda:self.client.document_result(*key),accepted)

    def impact_details(self):
        from PySide6.QtWidgets import QDialog,QVBoxLayout,QDialogButtonBox
        source=self.edited_draft()['settings']['source']
        dialog=QDialog(self);dialog.setWindowTitle('유한요소 원문과 출처');dialog.resize(760,560)
        layout=QVBoxLayout(dialog);view=QPlainTextEdit();view.setReadOnly(True)
        view.setPlainText(source.get('text','')+'\n\n'+display(source.get('provenance',{})))
        layout.addWidget(view);buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dialog.reject);layout.addWidget(buttons);dialog.exec()

    def _impact_source_run(self):
        if not self.document or self._result_key != (self.document['id'], self._selected_job):
            return None
        run = next((row for row in self.document.get('runs', []) if row['job_id'] == self._selected_job), None)
        if (not run or run.get('operation') != 'simulation.run'
                or run.get('draft', {}).get('backend') != 'explicit.opencourant.model'
                or not self._result or self._result.get('execution_status') not in
                   {'SUCCEEDED', 'FAILED', 'PARTIAL_FAILURE', 'CANCELLED', 'INTERRUPTED'}):
            return None
        return run

    def _interface_history_audit(self):
        if (self._busy or not self.document or not self._selected_job
                or self._result_key != (self.document['id'], self._selected_job)):
            return None
        audit = (self._result or {}).get('diagnostics', {}).get('b_observations', {}).get('interface_history')
        return audit if isinstance(audit, dict) and audit.get('elements') else None

    def show_interface_history(self):
        audit = self._interface_history_audit()
        if audit is None:
            return False
        from .impact_interface_history_view import InterfaceHistoryView
        InterfaceHistoryView(deepcopy(audit), self).exec()
        return True

    def _impact_history_available(self):
        return bool(not self._busy and self.document and self._selected_job
            and self._result_key==(self.document['id'],self._selected_job)
            and ((self._result or {}).get('operation')=='impact.reprocess'
                 or (self._result or {}).get('backend')=='explicit.opencourant.model')
            and (self._result or {}).get('responses'))

    def show_impact_history(self):
        if not self._impact_history_available():return False
        identifier,job=self.document['id'],self._selected_job
        def read():
            return self.client.impact_history_snapshot(identifier,job)
        def opened(snapshot):
            if self._result_key!=(identifier,job):return
            from .impact_history_view import ImpactHistoryView
            dialog=ImpactHistoryView(snapshot,self)
            dialog.study_requested.connect(lambda packet:self._history_followup(packet,'study'))
            dialog.plan_requested.connect(lambda packet:self._history_followup(packet,'numerical'))
            dialog.show()
            self._history_dialog=dialog
        return self._call(read,opened)

    def _history_followup(self,packet,kind):
        from .impact_history_actions import prepare_followup
        command=self._history_commands.setdefault((packet['selection_sha256'],kind),'C'+uuid.uuid4().hex)
        def opened(receipt):
            if receipt.get('executed') is not False:
                self.message.setText('전달 결과가 확인되지 않았습니다. 현재 문서를 다시 읽으세요.')
                return
            from .desktop import launch_tool
            launch_tool(self.client,kind,document_id=receipt['document']['id'],parent=self)
            self.message.setText('선택한 이력을 전달했습니다. 계산은 시작하지 않았습니다.')
        return self._call(lambda:prepare_followup(self.client,packet,kind,command),opened)

    def _refresh_result_caption(self):
        super()._refresh_result_caption()
        result = self._result or {}
        if result.get('operation') != 'impact.reprocess':
            return
        scopes = result.get('diagnostics', {}).get('readback_scopes') or {}
        history, animation = scopes.get('history', {}), scopes.get('animation', {})
        labels = {'COMPLETE': '읽음', 'PARTIAL': '일부만 읽음', 'UNKNOWN': '읽지 못함'}
        details = []
        if history:
            details.append('이력 ' + str(history.get('available_samples', 0)) + '개 (' +
                           labels.get(history.get('status'), '미확인') + ')')
        if animation:
            count = animation.get('available_frame_count', 0)
            details.append('공간 결과 ' + str(count) + '/' + str(animation.get('expected_slots', 0)) + '시각')
            missing = animation.get('unavailable_frame_count', 0)
            if missing:
                details.append('누락·손상 ' + str(missing) + '시각')
        state = result.get('execution_status')
        caption = {'SUCCEEDED': '읽기 완료', 'FAILED': '읽기 실패 또는 일부만 읽음',
                   'CANCELLED': '읽기 취소', 'INTERRUPTED': '읽기 중단'}.get(state, '읽기 상태 미확인')
        original = {'SUCCEEDED': '완료', 'FAILED': '실패', 'CANCELLED': '취소',
                    'INTERRUPTED': '중단', 'PARTIAL_FAILURE': '일부 실패'}.get(result.get('source_execution_status'), '미확인')
        text = caption + (': ' + ' / '.join(details) if details else '')
        if result.get('post_registration', {}).get('status') == 'FAILED':
            text += '\n후처리 연결 실패. 보존한 결과와 오류를 확인하세요.'
        self.result_label.setText(text + '\n원 계산: ' + original + ' / 새 솔버 계산 없음')

    def reprocess_impact(self):
        run = self._impact_source_run()
        if not run or self._busy or self.conflict:
            return False
        key = (self.document['id'], self.document['session_id'], run['job_id'])
        request = self._impact_read_requests.get(key)
        if request is None:
            if self.local_dirty:
                self.message.setText('편집한 입력을 먼저 변경 적용하세요. 원 계산의 입력은 바뀌지 않습니다.')
                return False
            choices = ['저장된 결과 파일 읽기', '원 ANIM/TH를 다시 변환해 읽기']
            choice, ok = QInputDialog.getItem(self, '보존 결과 다시 읽기',
                '선택한 계산의 출력을 읽습니다. 원 계산의 상태는 유지됩니다.', choices, 0, False)
            if not ok or choice not in choices:
                return False
            current = self._impact_source_run()
            if (not current or (self.document['id'], self.document['session_id'], current['job_id']) != key
                    or self._busy or self.conflict or self.local_dirty):
                self.message.setText('선택이나 편집 중인 입력이 바뀌었습니다. 계산을 다시 선택하세요.')
                return False
            request = {'command_id': 'C' + uuid.uuid4().hex,
                       'expected_generation': self.document['generation'],
                       'arguments': {'source_job_id': run['job_id'], 'convert_raw': choice == choices[1]}}
            self._impact_read_requests[key] = request
        submitted_buffer = self.edited_draft()

        def submit():
            try:
                receipt = self.client.document_command(key[0], 'simulation.reprocess', deepcopy(request['arguments']),
                    session_id=key[1], expected_generation=request['expected_generation'], command_id=request['command_id'])
            except WorkbenchHTTPError as error:
                if error.code in {400, 403, 404, 409, 422}:
                    self._impact_read_requests.pop(key, None)
                raise
            job, document = receipt.get('job') or {}, receipt.get('document') or {}
            if (document.get('id') != key[0] or document.get('session_id') != key[1]
                    or job.get('operation') != 'impact.reprocess' or job.get('id', job.get('job_id')) == key[2]
                    or not job.get('id', job.get('job_id'))
                    or job.get('arguments', {}).get('source_job_id') != key[2]):
                raise ValueError('결과 읽기의 원 계산이 다릅니다. 같은 읽기 요청의 상태를 확인하세요.')
            return receipt

        def accepted(receipt):
            self._impact_read_requests.pop(key, None)
            if not self.document or (self.document['id'], self.document['session_id']) != key[:2]:
                return
            current_buffer = self.edited_draft()
            late_edit = self.local_dirty or current_buffer != submitted_buffer
            select_derived = self._selected_job == key[2]
            self._show_document(receipt['document'], preserve_draft=current_buffer if late_edit else None)
            self.local_dirty = late_edit
            if select_derived:
                job = receipt['job']
                self._selected_job = job.get('id', job.get('job_id'))
                self._result_key = self._result = None
                target = self._run_nodes.get(self._selected_job)
                if target is not None:
                    self.tree.setCurrentItem(target)
                QTimer.singleShot(0, self.refresh_result)
            self.message.setText('결과 읽기를 요청했습니다. 원 계산의 상태는 유지됩니다.')

        return self._call(submit, accepted)

    def _update_actions(self):
        super()._update_actions()
        self.evaluate_button.setText('계산 실행' if _is_native(self._draft.get('backend')) else '모델 평가')
        for button, action in getattr(self, '_command_actions', []):
            action.setText(button.text()); action.setEnabled(button.isEnabled())
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
        if hasattr(self,'fatigue_action'):
            self.fatigue_action.setEnabled(not self._busy and self._draft.get('backend')=='damage.rainflow')
            self.cycles_action.setEnabled(not self._busy and bool(self._selected_job))
        if hasattr(self, 'reprocess_impact_action'):
            source = self._impact_source_run()
            key = (self.document['id'], self.document['session_id'], source['job_id']) if source else None
            uncertain = key in self._impact_read_requests
            self.reprocess_impact_action.setEnabled(bool(source) and not self._busy and not self.conflict
                                                   and (not self.local_dirty or uncertain))
            self.reprocess_impact_action.setText('결과 읽기 상태 확인…' if uncertain else '보존 결과 다시 읽기…')
        if hasattr(self, 'interface_history_action'):
            self.interface_history_action.setEnabled(self._interface_history_audit() is not None)
        if hasattr(self,'impact_history_action'):
            self.impact_history_action.setEnabled(self._impact_history_available())
        if hasattr(self, 'input_model_action'):
            self.input_model_action.setVisible(_is_native(self._draft.get('backend')))
            self.input_model_action.setEnabled(bool(self.document) and _is_native(self._draft.get('backend'))
                and bool(self._native_input_id()) and not (self._busy or self.local_dirty or self.conflict))
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
                from caelab.impact_model import model_from_settings
                model=model_from_settings(settings)
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
    if options.document_id:
        from .result_return import activate_existing
        if activate_existing(client,options.document_id,kind='simulation').get('status')=='ACTIVATED':return 0
    window = SimulationWindow(client, document_id=options.document_id,
        runner_open=lambda job: launch_tool(client, 'runner', job_id=job),
        result_open=lambda doc, job, **kwargs: open_document_result(client, doc, job, **kwargs),
        plan_open=lambda doc, **kwargs: open_domain_plan(client, doc, **kwargs))
    window.show()
    return app.exec()


if __name__ == '__main__':
    raise SystemExit(main())
