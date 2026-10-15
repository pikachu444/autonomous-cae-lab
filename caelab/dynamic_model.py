"""NS2 input/state contract for the existing C3D10 CalculiX pipeline.

No solver, scheduler or project serializer lives here. Numeric strings are kept
in the owner's draft; only a separately admitted frozen model contains numbers.
"""
from copy import deepcopy
import math

from .contact import number
from .storage import canonical_hash

NAMESPACE = 'dynamic_programs'
OPERATIONS = ('pre.dynamic.inspect', 'pre.dynamic.create', 'pre.dynamic.draft',
              'pre.dynamic.apply', 'pre.dynamic.capture', 'pre.dynamic.freeze',
              'pre.dynamic.restart')
READ_ONLY = {'pre.dynamic.inspect', 'pre.dynamic.capture'}
DENSITY_FACTOR = 1e-12  # kg/m^3 -> tonne/mm^3 in the mm, N, s system


class DynamicInputError(ValueError):
    def __init__(self, path, message):
        self.path, self.message = path, message
        super().__init__(path + ': ' + message)

    def record(self):
        return {'path': self.path, 'message': self.message}


def positive(value, path, *, zero=False):
    try:
        v = number(value)
        if (v < 0 if zero else v <= 0):
            raise ValueError('0 이상' if zero else '0 초과')
        return v
    except (TypeError, ValueError, OverflowError) as exc:
        raise DynamicInputError(path, '완전한 유한 숫자와 범위를 확인하세요.') from exc


def density(value):
    result = positive(value, 'density') * DENSITY_FACTOR
    if not math.isfinite(result) or result <= 0:
        raise DynamicInputError('density', '단위 변환 후 양의 유한 밀도가 필요합니다.')
    return result


def enabled(model):
    return isinstance(model.get('dynamic'), dict)


def has_dynamic(program):
    return any(r.get('procedure', program.get('procedure')) == 'dynamic'
               for r in program.get('steps', []))


def default_draft(analysis_id, solver_id, program, densities=()):
    p = deepcopy(program)
    p['procedure'] = 'dynamic'
    for step in p['steps']:
        step['procedure'] = 'dynamic'
    return {'version': 1, 'analysis_id': analysis_id, 'solver_id': solver_id,
            'program': p, 'densities': deepcopy(list(densities)),
            'initial_conditions': [], 'rayleigh': {'alpha_per_s': '0', 'beta_s': '0'},
            'numerical_alpha': '-0.05', 'restart_frequency': '1'}


def continuation_step(source, *, identifier, label='동적 후속 단계'):
    """Default a new step without reactivating released force/displacement DOFs.

    This edits a copy of the draft only; compile_program still owns admission.
    A release is a state (force off / displacement free), not a held endpoint.
    Keep unrecognized modes unchanged so an invalid draft stays visibly invalid.
    """
    step = deepcopy(source)
    step.update(id=identifier, label=label, procedure='dynamic')
    for row in step['curves']:
        if row.get('mode', 'curve') in ('curve', 'hold'):
            row['mode'] = 'hold'
    return step


def check_shape(draft):
    keys = {'version', 'analysis_id', 'solver_id', 'program', 'densities',
            'initial_conditions', 'rayleigh', 'numerical_alpha', 'restart_frequency'}
    if not isinstance(draft, dict) or set(draft) != keys or draft.get('version') != 1:
        raise DynamicInputError('draft', '지원되는 동해석 초안이 아닙니다.')
    if not all(isinstance(draft.get(k), str) and draft[k] for k in ('analysis_id', 'solver_id')):
        raise DynamicInputError('analysis_id', '해석과 solver를 명시적으로 선택하세요.')
    for key, limit in (('initial_conditions', 10000), ('densities', 1000)):
        if not isinstance(draft[key], list) or len(draft[key]) > limit:
            raise DynamicInputError(key, '편집 목록의 종류 또는 크기가 잘못됐습니다.')
    # This also refuses NaN, objects and cycles; it does not parse numeric text.
    canonical_hash(draft)


def settings(draft, model):
    """Resolve body-local IC IDs against the already proven native frozen mesh.

    Native shape/mesh/source bindings are checked by dynamic_native before this
    call. Global deck IDs are never accepted as an editable source-node identity.
    """
    check_shape(draft)
    from .contact_steps import compile_program, integer
    try:
        stages = compile_program(draft['program'], model['conditions'])
    except (ValueError, TypeError, KeyError) as exc:
        raise DynamicInputError('program', str(exc)) from exc
    if not has_dynamic(draft['program']):
        raise DynamicInputError('program', '하나 이상의 implicit dynamic 단계가 필요합니다.')
    seen_dynamic = False
    for row in stages:
        seen_dynamic |= row['procedure'] == 'dynamic'
        if seen_dynamic and row['procedure'] == 'static':
            raise DynamicInputError('program', '첫 경로는 정적 선행 단계 뒤 연속 동적 단계만 지원합니다.')
    rayleigh = draft['rayleigh']
    if not isinstance(rayleigh, dict) or set(rayleigh) != {'alpha_per_s', 'beta_s'}:
        raise DynamicInputError('rayleigh', '모델 전체의 Rayleigh α, β 한 쌍이 필요합니다.')
    damping = {k: positive(v, 'rayleigh.' + k, zero=True) for k, v in rayleigh.items()}
    try:
        alpha = number(draft['numerical_alpha'])
        if not -1/3 <= alpha <= 0:
            raise ValueError('range')
    except (TypeError, ValueError, OverflowError) as exc:
        raise DynamicInputError('numerical_alpha', '수치감쇠 α는 -1/3~0의 유한 값이어야 합니다.') from exc
    try:
        frequency = integer(draft['restart_frequency'], '저장 주기 (완료 단계 수)')
    except (TypeError, ValueError, OverflowError) as exc:
        raise DynamicInputError('restart_frequency', '저장 주기는 양의 정수여야 합니다.') from exc
    material_by_body = {r['body_id']: r for r in model['materials']}
    densities, bodies = [], set()
    for i, r in enumerate(draft['densities']):
        path = 'densities.' + str(i)
        if not isinstance(r, dict) or set(r) != {'body_id', 'material_id', 'kg_m3'}:
            raise DynamicInputError(path, 'body·재료 객체와 kg/m³ 밀도가 필요합니다.')
        b = r['body_id']
        mat = material_by_body.get(b)
        if b in bodies or mat is None or r['material_id'] != mat.get('object_id'):
            raise DynamicInputError(path, '밀도 대상 body/재료가 삭제·변경됐거나 중복입니다.')
        bodies.add(b)
        densities.append({'body_id': b, 'material_id': r['material_id'],
                          'kg_m3': positive(r['kg_m3'], path + '.kg_m3'),
                          'tonne_mm3': density(r['kg_m3'])})
    if bodies != set(material_by_body):
        raise DynamicInputError('densities', '모든 body의 밀도를 정확히 한 번 지정하세요.')
    grouped = {}
    for row in densities:
        previous = grouped.setdefault(row['material_id'], row['kg_m3'])
        if previous != row['kg_m3']:
            raise DynamicInputError('densities', '동일 native 재료 객체에 서로 다른 밀도를 지정할 수 없습니다.')
    lookup = {(r['body_id'], r['native_node_id']): r['node_id'] for r in model['nodes']}
    initial, occupied, ids = [], set(), set()
    for i, raw in enumerate(draft['initial_conditions']):
        path = 'initial_conditions.' + str(i)
        if not isinstance(raw, dict) or set(raw) != {'id', 'label', 'kind', 'component', 'value', 'target'}:
            raise DynamicInputError(path, '초기조건 행의 원 대상과 값이 필요합니다.')
        if not isinstance(raw['id'], str) or not raw['id'] or raw['id'] in ids:
            raise DynamicInputError(path + '.id', '중복되지 않는 초기조건 ID가 필요합니다.')
        ids.add(raw['id'])
        if raw['kind'] not in ('U', 'V') or type(raw['component']) is not int or raw['component'] not in (1, 2, 3):
            raise DynamicInputError(path, 'U/V와 전역 X/Y/Z 자유도를 선택하세요.')
        try:
            value = number(raw['value'])
        except (ValueError, TypeError) as exc:
            raise DynamicInputError(path + '.value', '완전한 유한 초기값을 입력하세요.') from exc
        target = raw['target']
        if not isinstance(target, dict) or not isinstance(target.get('native_node_ids'), list) or not target['native_node_ids']:
            raise DynamicInputError(path + '.target', '실제 메시 절점 또는 CAD 영역을 선택하세요.')
        native_ids = target['native_node_ids']
        if any(type(n) is not int or n < 1 for n in native_ids) or len(native_ids) != len(set(native_ids)):
            raise DynamicInputError(path + '.target', '원 절점 번호가 잘못됐거나 중복입니다.')
        for native in native_ids:
            node = lookup.get((target.get('body_id'), native))
            if node is None:
                raise DynamicInputError(path + '.target', '선택한 원 절점이 현재 body 메시에서 없어졌습니다.')
            key = raw['kind'], node, raw['component']
            if key in occupied:
                raise DynamicInputError(path, '같은 종류의 초기조건이 같은 절점/자유도에 중복됩니다.')
            occupied.add(key)
            if stages[0]['procedure'] == 'static' and value != 0:
                raise DynamicInputError(path, '비영 초기 U/V와 정적 선행 단계의 조합은 미지원입니다. 동적 첫 단계 또는 native 선행 상태를 선택하세요.')
            if value != 0 and (node, raw['component']) in stages[0]['boundary']:
                raise DynamicInputError(path, '비영 초기 U/V는 첫 단계의 지정 변위 자유도와 겹칠 수 없습니다.')
            initial.append({'id': raw['id'], 'node_id': node, 'body_id': target['body_id'],
                            'native_node_id': native, 'component': raw['component'], 'kind': raw['kind'],
                            'value': value, 'unit': 'mm' if raw['kind'] == 'U' else 'mm/s'})
    result = {'version': 1, 'rayleigh': damping, 'numerical_alpha': alpha,
              'restart_frequency': frequency, 'densities': densities, 'initial_conditions': initial,
              'initial_origin': 'MODEL_INITIAL_CONDITIONS', 'draft': deepcopy(draft)}
    return result


def validate_effective(model):
    """Re-derive frozen settings; do not trust a stored 'validated' flag."""
    d = model['dynamic']
    admitted = settings(d['draft'], model)
    if admitted != d or d['draft']['program'] != model.get('analysis_steps'):
        raise DynamicInputError('dynamic', '원 초안과 동결된 단계/초기조건/단위가 다릅니다.')
    for r in d['densities']:
        m = next(m for m in model['materials'] if m['body_id'] == r['body_id'])
        if m.get('density_tonne_per_mm3') != r['tonne_mm3']:
            raise DynamicInputError('density', '원 밀도와 solver 밀도 변환이 다릅니다.')
    from .calculix_material import J2
    for m in model['materials']:
        if m.get('law') not in ('isotropic_linear_elastic', J2):
            raise DynamicInputError('materials', '첫 경로는 등방 탄성 또는 기존 J2 등방경화입니다.')
    if any(p['draft']['normal_law'] == 'tie' for p in model['contacts']):
        raise DynamicInputError('contacts', 'NS2의 tie/adjusted MPC 조합은 미완료입니다. 기존 정적 tie 경로는 유지됩니다.')
    return d


def attach(model, draft):
    """Return a new frozen model; the caller's draft/native values stay intact."""
    result = deepcopy(model)
    result['analysis_steps'] = deepcopy(draft['program'])
    result['dynamic'] = settings(draft, result)
    for r in result['dynamic']['densities']:
        m = next(m for m in result['materials'] if m['body_id'] == r['body_id'])
        m['density_tonne_per_mm3'] = r['tonne_mm3']
    if not result['contacts']:
        result['analysis_scope'] = 'single_solid_dynamic'
    validate_effective(result)
    from .contact_deck import validate_model
    validate_model(result)
    return result


def capability(model):
    """Input support is distinct from native execution and physical qualification."""
    from .calculix_material import has_plasticity
    return {'formulation': 'implicit_direct_integration', 'element': 'C3D10',
            'law': 'J2_isotropic_hardening' if has_plasticity(model) else 'isotropic_linear_elastic',
            'geometry': model['step']['geometry'],
            'contact': 'linear_penalty/Coulomb' if model['contacts'] else 'none',
            'input_support': 'IMPLEMENTED', 'native_validation': 'REQUIRED_FOR_THIS_BUILD',
            'qualification': 'UNKNOWN', 'decision': 'NOT_RELEASED',
            'remaining': ['E3', 'E4', 'E5', 'E6', 'C1', 'C2', 'C3', 'C4', 'C5', 'C6']}
