"""Editable declarations for the existing structural/explicit/material adapters.

The catalogue describes the admitted model, not the availability of a solver.
No runtime is imported or started to edit, validate or reopen a document.
"""
from copy import deepcopy
from importlib import import_module

from .material_document import MaterialDocuments


CATALOG = {
    'structure.calculix.support_reaction': (None, None,
        '원 선형 C3D10 정적 결과의 선택 프레임에서 원 SPC 지지 반력을 읽습니다. 새 솔버 계산은 하지 않습니다.'),
    'structure.calculix.conservative_load': (None, None,
        '선택한 평면 TRI6 경계의 절점력을 사용자 선형 정적 모델에 추가합니다. 원 조건·하중·단계는 보존합니다.'),
    'structure.codeaster.contact': (None, None,
        'Code_Aster 17.4의 두 독립 TETRA10/HEXA8 탄성 고체 정적 구조해석. 작은 변형·작은 미끄럼의 비관통/쿨롱 접촉이며 공학 적합성은 UNKNOWN입니다.'),
    'structure.calculix.initial_fields': (None, None,
        '사용자 고체와 정적 단계에 온도 또는 원 적분점 초기응력을 적용합니다. 초기조건과 첫 평형/후속 결과를 구분합니다.'),
    'structure.codeaster.initial_fields': (None, None,
        '한정한 정적 구조해석에 호환 초기 변위·총변형률·응력을 적용합니다. 미지원 하중 곡선/증분 제어는 실행 전에 차단합니다.'),
    'structure.calculix.pretension': (None, None,
        '실제 C3D10 내부 절단면의 조임·길이 고정·외력. 정적 절단면 절점력 합·복구 응력 면적분·참조 자유도 응답을 구분합니다.'),
    'thermal.scikit_fem.rectangle': (None, None,
        'scikit-fem 12.0.2 + SciPy: P1 열전도, 절대 온도, 명시한 정상 상태, 기존 Picard 반복.'),
    'structural.scikit_fem.thermoelastic_rectangle': (None, None,
        '미소변형 plane-stress P1 열탄성, 구조 기준온도, 검증된 절대/차분 온도 입력. 공학적 판정 UNKNOWN.'),
    'structure.felupe.law_native': (None, None,
        'FELUPE 11.1.3 Hex8 point/FE pair: DP, log-J Neo-Hooke, exact-ramp single-branch SLS. Not CalculiX/impact/shell.'),
    'damage.rainflow': (None,None,'보존 이력의 S–N/Miner, total-strain CMB/NONE, 단축 SWT 및 최대 정상변형률 범위 면의 CP-SWT. 명시 교정 범위 안에서만 계산하며 전단 지배 재료의 적합성·반복 소성·계면 피로 연계는 승인하지 않습니다.'),
    'structure.calculix.shell.composite': (None, None,
        '보존한 S8R 적층 셸 입력. 등방/직교이방성 선형 탄성, 정적 고정/압력. DAT 원 층별 적분점과 FRD 외삽값을 구분하며 공학적 승인은 별도입니다.'),
    'explicit.opencourant.connector': (None, None,
        '실제 CAD/메시 영역의 명시 rigid attachment와 TYPE13 병진·회전 k/c. 기존 탄성 C3D4 FE 질량·강성 보존. 공학 판정 UNKNOWN.'),
    'explicit.opencourant.model': (None, None,
        '사용자 FE 메시, 초기 운동, TYPE24, 명시 LAW117 응집 손상. Mg/mm/s 입력. 수명·공학 승인은 별도입니다.'),
    'material.mfront.user': (None, None,
        '운영자가 원문 SHA로 허용한 사용자 법칙. generic 3차원 미소변형, Pa/1/s. FE export는 별도 미지원.'),
    'structure.calculix.design': (None, None,
        'Saved native Analysis candidates: independent editable copy, mapped references, remesh and existing CalculiX execution.'),
    'structural.code_aster': ('plugins.elasticity.reference', 'native_doctor_settings',
        'Existing affine uniaxial 3D elasticity block; exact declared dimensions, mesh and traction, not arbitrary CAD elasticity.'),
    'structural.code_aster.plasticity': ('plugins.elasticity.plasticity_reference', 'selected_settings',
        'Small-strain J2 block; declared axial history and mesh. No DP, damage or contact.'),
    'structural.code_aster.geometric_nonlinearity': ('plugins.geometric_nonlinearity.reference', 'default_settings',
        'Declared geometric-nonlinearity model and original reference limits.'),
    'structural.code_aster.contact_patch': ('plugins.contact_patch.reference', None,
        'Frictionless SSNP121A contact patch; not arbitrary assembly contact or preload.'),
    'structural.families.calculix': ('plugins.structural_families.reference', 'specification',
        'Existing declared cantilever, cylinder and curved-solid families; fixed reference definitions.'),
    'structural.families.code_aster': ('plugins.structural_families.reference', 'specification',
        'The same declared structural families through Code_Aster.'),
    'explicit.openradioss': ('plugins.explicit_dynamics.reference', 'selected_history_settings',
        'Rigid translation or the existing compliant-stop topology; explicit acceleration history. No general crash model.'),
    'material.mfront': ('plugins.material_point.reference', 'canonical_settings',
        'Existing small-strain Elasticity material point, integration and tangent checks.'),
    'material.mfront.inverse': ('plugins.material_point.inverse_reference', 'canonical_settings',
        'Existing bounded MFront inverse input/observation definition.'),
    'material.mfront.hyperelastic': ('plugins.hyperelastic.reference', 'canonical_settings',
        'Existing finite-strain hyperelastic material point and tangent convention.'),
    'material.mfront.viscoelastic': ('plugins.material_point.viscoelastic_reference', 'canonical_settings',
        'Existing single-branch Maxwell material point; delayed recovery is time dependent.'),
    'thermal.fenicsx.rectangle': (None, None,
        'Steady SI conduction on a declared rectangle; actual solved temperature, optional Picard conductivity.'),
    'structural.fenicsx.thermoelastic_rectangle': (None, None,
        'SI plane-stress small-strain thermal expansion; explicit temperature field, CTE and stress-free temperature.'),
}
BACKENDS = tuple(CATALOG)


def _adapter(backend):
    from .backends import get_backend
    return get_backend(backend)


def default_draft(backend='structural.code_aster.plasticity'):
    if backend not in CATALOG:
        raise ValueError('Choose an explicitly supported simulation declaration')
    module, factory, _ = CATALOG[backend]
    if module is None:
        settings = _adapter(backend).default_settings()
    elif factory == 'native_doctor_settings':
        from .adapters.native_doctor import _smoke_settings
        settings = _smoke_settings(backend)
    elif factory == 'specification':
        settings = import_module(module).specification('ansys_vmd1_regular')
    elif factory:
        settings = getattr(import_module(module), factory)()
    else:
        settings = {'case': 'ssnp121a_frictionless_patch',
            'material': {'youngs_modulus_pa': 100000., 'poisson_ratio': 0.},
            'top_displacement_m': -.1,
            'limits': {'reference_relative': .01, 'force_balance_relative': 1e-6}}
    return {'backend': backend, 'settings': deepcopy(settings)}


def validate_draft(draft):
    if not isinstance(draft, dict) or set(draft) != {'backend', 'settings'}:
        raise ValueError('Simulation requires the visible backend and settings only')
    backend = draft['backend']
    if not isinstance(backend, str) or backend not in CATALOG or not isinstance(draft['settings'], dict):
        raise ValueError('Choose a supported simulation backend and an editable settings object')
    module = CATALOG[backend][0]
    return (import_module(module).validate_settings(deepcopy(draft['settings'])) if module else
            _adapter(backend).validate_settings(deepcopy(draft['settings'])))


def diagnostics(draft):
    try:
        validate_draft(draft)
    except (ValueError, TypeError, KeyError, OverflowError, ImportError) as error:
        return [{'path': getattr(error,'path','settings'), 'line':getattr(error,'line',None), 'column':getattr(error,'column',None), 'file':getattr(error,'file',None), 'occurrence':getattr(error,'occurrence',None), 'impact':deepcopy(getattr(error,'impact',{})), 'severity': 'error', 'message': str(error), 'blocks_evaluation': True}]
    return []


def support_details(draft):
    backend = draft.get('backend') if isinstance(draft, dict) else None
    result = {'limitations': [CATALOG[backend][2]] if isinstance(backend, str) and backend in CATALOG else ['Unsupported declared backend'],
              'readiness': 'NOT_PROBED', 'decision': 'NOT_RELEASED', 'declaration': {}, 'ports': {}}
    if not diagnostics(draft):
        module = CATALOG[backend][0]
        if module:
            result['declaration'] = import_module(module).model_declaration(deepcopy(draft['settings']))
        else:
            result['ports'] = _adapter(backend).describe_ports(deepcopy(draft['settings']))
            if backend == 'structure.felupe.law_native':
                result['declaration'] = _adapter(backend).describe_model(deepcopy(draft['settings']))
        result['limitations'].append('Editing and declaration checks do not establish an installed backend or engineering approval.')
    return result


class SimulationDocuments(MaterialDocuments):
    kind, prefix = 'simulation', 'V'
    update_operation, evaluate_operation = 'simulation.update', 'simulation.evaluate'
    evaluation_operation = 'simulation.run'
    default_draft = staticmethod(default_draft)
    diagnostics = staticmethod(diagnostics)

    @staticmethod
    def _draft(value):
        # A captured thermal field is bounded by the existing research document limit.
        from .pde_document import PDEDocuments
        return PDEDocuments._draft(value)

    @property
    def evaluation_commands(self):
        return super().evaluation_commands | {'simulation.reprocess'}

    def prepare_command_job(self, operation, arguments, document):
        if operation == 'simulation.reprocess':
            from .impact_recovery import document_request
            return document_request(self, document, arguments)
        return super().prepare_command_job(operation, arguments, document)

    def command_input_context(self, operation, arguments, document, snapshot):
        if operation == 'simulation.reprocess':
            from .impact_recovery import source_input_context
            return source_input_context(document, arguments, snapshot)
        return super().command_input_context(operation, arguments, document, snapshot)

    def _retain_inputs(self, saved, folder):
        super()._retain_inputs(saved, folder)
        from .portable_project_execution import retain_execution_inputs
        retain_execution_inputs(self, saved, folder)

    def _public(self, document):
        from .portable_project_execution import public_execution
        result = public_execution(self, super()._public(document))
        result['simulation_support'] = support_details(document['draft'])
        return result
