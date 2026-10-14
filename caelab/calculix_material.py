"""CalculiX solid material contract shared by native editing and deck export.

NS1: isotropic elasticity and tabular, rate-independent J2 isotropic hardening.
This module validates/converts definitions, not constitutive responses.  A raw
editing draft is never silently repaired, sorted, fitted or substituted.
"""
from copy import deepcopy
import math

LINEAR = 'isotropic_linear_elastic'
J2 = 'j2_isotropic_hardening'
STRESS_MEASURE = 'cauchy'
STRAIN_MEASURE = 'equivalent_plastic_strain'
STRESS_FACTORS = {'Pa': 1e-6, 'kPa': 1e-3, 'MPa': 1.0, 'GPa': 1e3}
STRAIN_FACTORS = {'1': 1.0, '%': 0.01}
# CalculiX 2.22 plcopy.f resamples larger tables to 200 points. Do not opt in
# silently: this is an execution limit, never a reason to discard an editing draft.
MAX_YIELD_POINTS = 200
NATIVE_PRECISION = '20-character fields; 13 significant digits; original curve retained'


def finite(value):
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ValueError('완전한 유한 숫자를 입력하세요.')
    try:
        value = float(value)
    except (ValueError, OverflowError) as error:
        raise ValueError('완전한 유한 숫자를 입력하세요.') from error
    if not math.isfinite(value):
        raise ValueError('유한 숫자를 입력하세요.')
    return value


def default_plasticity():
    """An empty, saveable input, not an assumed material."""
    return {'hardening': 'isotropic', 'stress_measure': STRESS_MEASURE,
            'strain_measure': STRAIN_MEASURE, 'stress_unit': 'MPa',
            'strain_unit': '1', 'yield_points': []}


def plasticity_errors(definition, path='plasticity'):
    errors = []
    def fail(field, message):
        errors.append({'path': path + '.' + field, 'message': message,
                       'severity': 'error', 'blocks_evaluation': True})
    if not isinstance(definition, dict):
        fail('yield_points', '등방 경화 재료 표를 입력하세요.')
        return errors
    if definition.get('hardening') != 'isotropic':
        fail('hardening', '이번 CalculiX 경로는 J2 등방 경화만 지원합니다.')
    if definition.get('stress_measure') != STRESS_MEASURE:
        fail('stress_measure', '진응력(Cauchy) 표가 필요합니다. 공칭응력을 자동 변환하지 않습니다.')
    if definition.get('strain_measure') != STRAIN_MEASURE:
        fail('strain_measure', '등가 소성변형률이 필요합니다. 전체변형률을 소성변형률로 해석하지 않습니다.')
    if definition.get('stress_unit') not in STRESS_FACTORS:
        fail('stress_unit', '응력 단위는 Pa, kPa, MPa, GPa 중에서 선택하세요.')
    if definition.get('strain_unit') not in STRAIN_FACTORS:
        fail('strain_unit', '소성변형률 단위는 무차원(1) 또는 %로 지정하세요.')
    rows = definition.get('yield_points')
    if not isinstance(rows, list) or not rows:
        fail('yield_points', '항복점 표를 입력하세요. 첫 점의 소성변형률은 0입니다.')
        return errors
    if len(rows) > MAX_YIELD_POINTS:
        fail('yield_points.' + str(MAX_YIELD_POINTS),
             '실행 곡선은 200점 이하입니다. 초안은 저장할 수 있지만 자동 단순화하지 않습니다.')
        return errors
    previous = None
    for index, row in enumerate(rows):
        base = 'yield_points.' + str(index)
        if not isinstance(row, (list, tuple)) or len(row) != 2:
            fail(base, '한 행에 진응력과 등가 소성변형률 두 값을 입력하세요.')
            previous = None
            continue
        values = []
        for column, value in enumerate(row):
            try:
                values.append(finite(value))
            except ValueError as error:
                fail(base + '.' + str(column), str(error))
                values.append(None)
        stress, strain = values
        if stress is not None and stress <= 0:
            fail(base + '.0', '항복 진응력은 0보다 커야 합니다.')
        if strain is not None:
            if strain < 0 or index == 0 and strain != 0:
                fail(base + '.1', '첫 소성변형률은 0, 이후 값은 양수여야 합니다.')
            if previous is not None and strain <= previous[1]:
                fail(base + '.1', '소성변형률은 위 행보다 커야 합니다. 행을 자동 정렬하지 않습니다.')
        if previous is not None and stress is not None and stress < previous[0]:
            fail(base + '.0', '등방 경화 표의 항복응력은 감소할 수 없습니다. 일정 응력 구간은 허용합니다.')
        previous = (stress, strain) if stress is not None and strain is not None else None
    return errors


def normalize_plasticity(definition):
    """Explicit units-only conversion; stress/strain measures must already match."""
    errors = plasticity_errors(definition)
    if errors:
        raise ValueError('; '.join(e['path'] + ': ' + e['message'] for e in errors))
    result = deepcopy(definition)
    stress_factor = STRESS_FACTORS[result['stress_unit']]
    strain_factor = STRAIN_FACTORS[result['strain_unit']]
    result['yield_points'] = [[finite(finite(s) * stress_factor),
                               finite(finite(e) * strain_factor)] for s, e in result['yield_points']]
    result.update(stress_unit='MPa', strain_unit='1')
    errors = plasticity_errors(result)
    if errors:
        raise ValueError('단위 변환 후 표가 유효하지 않습니다: ' + '; '.join(e['message'] for e in errors))
    return result


def native_plasticity(yield_points, hardening='isotropic hardening'):
    """Read FreeCAD 1.1.4's literal YieldPoints (native writer: MPa, unit strain).

    The native writer emits these strings without unit conversion.  Unit-bearing
    tokens, third temperature columns and malformed rows are rejected here rather
    than guessing their meaning. The native object and its strings are unchanged.
    """
    result = default_plasticity()
    result['hardening'] = 'isotropic' if hardening == 'isotropic hardening' else hardening
    if not isinstance(yield_points, (list, tuple)):
        raise ValueError('Native YieldPoints must be a list of stress, plastic-strain rows.')
    result['yield_points'] = [line.split(',') if isinstance(line, str) else line for line in yield_points]
    return normalize_plasticity(result)


def native_yield_points(definition):
    normalized = normalize_plasticity(definition)
    # Local import avoids a material/deck import cycle when the writer calls us.
    from .adapters.native_structural_deck import native_number
    rows = [native_number(s) + ', ' + native_number(e)
            for s, e in normalized['yield_points']]
    # Validate what plastics.f actually reads, not just the in-memory curve.
    # A pair of very close abscissae must not collapse into duplicate strains.
    serialized = deepcopy(normalized)
    serialized['yield_points'] = [[float(token.strip()[:20]) for token in row.split(',')]
                                  for row in rows]
    errors = plasticity_errors(serialized)
    if errors:
        raise ValueError('13자리 native 출력에서 곡선이 유효하지 않습니다: ' +
                         '; '.join(e['path'] + ': ' + e['message'] for e in errors))
    return rows


def material_errors(material, path='material'):
    errors = []
    def fail(field, message):
        errors.append({'path': path + '.' + field, 'message': message,
                       'severity': 'error', 'blocks_evaluation': True})
    if not isinstance(material, dict):
        fail('law', '재료 정의가 필요합니다.')
        return errors
    for key in ('young_modulus_MPa', 'poisson_ratio'):
        try:
            value = finite(material.get(key))
            if key == 'young_modulus_MPa' and value <= 0:
                raise ValueError('Young 계수는 0보다 커야 합니다.')
            if key == 'poisson_ratio' and not -1 < value < .5:
                raise ValueError('Poisson 비는 -1보다 크고 0.5보다 작아야 합니다.')
        except ValueError as error:
            fail(key, str(error))
    if material.get('law') == J2:
        errors.extend(plasticity_errors(material.get('plasticity'), path + '.plasticity'))
        if isinstance(material.get('plasticity'), dict) and (
                material['plasticity'].get('stress_unit') != 'MPa' or
                material['plasticity'].get('strain_unit') != '1'):
            fail('plasticity', '실행 입력은 MPa와 무차원 소성변형률이어야 합니다. 먼저 단위 변환을 확인하고 적용하세요.')
    elif material.get('law') != LINEAR:
        fail('law', '등방 탄성 또는 표형 J2 등방 경화를 선택하세요.')
    elif material.get('plasticity') is not None:
        fail('plasticity', '소성 표가 있는 재료를 선형으로 내보낼 수 없습니다. 법칙을 명시적으로 선택하세요.')
    return errors


def plastic_cards(material):
    """Additional material cards, inserted after *ELASTIC before *SOLID SECTION."""
    errors = material_errors(material)
    if errors:
        raise ValueError('; '.join(e['path'] + ': ' + e['message'] for e in errors))
    if material['law'] == LINEAR:
        return []
    return ['*PLASTIC,HARDENING=ISOTROPIC', *native_yield_points(material['plasticity'])]


def has_plasticity(model):
    return any(row.get('law') == J2 for row in model.get('materials', []))


RESULT_MEANINGS = {
    'STRESS': {'quantity': 'stress', 'measure': 'cauchy', 'unit': 'MPa',
               'association': 'POINTS', 'recovery': 'native integration-point extrapolation and nodal averaging'},
    'TOSTRAIN': {'quantity': 'total_strain', 'measure': None, 'unit': '1',
                 'requires_step_context': True,
                 'association': 'POINTS', 'components': 'tensor shear, not engineering shear',
                 'scope': 'isotropic elasticity and incremental J2 plasticity'},
    'PE': {'quantity': 'equivalent_plastic_strain', 'measure': STRAIN_MEASURE, 'unit': '1',
           'association': 'POINTS', 'native_request': 'PEEQ',
           'recovery': 'native integration-point extrapolation and nodal averaging',
           'note': 'Scalar accumulated plastic strain; PE is not a plastic strain tensor.'},
    'FORC': {'quantity': 'nodal_force', 'unit': 'N', 'association': 'POINTS',
             'native_request': 'RF', 'note': 'Use restrained DOFs for reactions; do not label every nodal force a reaction.'},
}


def result_meanings(nlgeom=None):
    """Meanings for one step; an external FRD alone does not establish NLGEOM.

    None retains an unknown strain measure rather than guessing finite strain.
    STATIC step time is a load parameter, not physical seconds; the result
    reader supplies time-axis metadata separately from these field meanings.
    """
    if nlgeom is not None and type(nlgeom) is not bool:
        raise ValueError('NLGEOM must be True, False or unknown (None).')
    result = deepcopy(RESULT_MEANINGS)
    if nlgeom is not None:
        result['TOSTRAIN']['measure'] = 'green_lagrange' if nlgeom else 'infinitesimal'
        result['TOSTRAIN']['requires_step_context'] = False
    return result


def ns1_enabled(model):
    return has_plasticity(model) or model.get('analysis_scope') == 'single_solid_static'


def field_specifications(model):
    """Shared native/Post/Runner quantities for the admitted common NLGEOM setting."""
    geometry = model.get('step', {}).get('geometry')
    meanings = result_meanings({'linear': False, 'nonlinear': True}.get(geometry))
    return [
        ('FORC', 'F', 'N', meanings['FORC']['quantity'], ('X', 'Y', 'Z')),
        ('STRESS', 'S', 'MPa', 'cauchy_stress', ('XX', 'YY', 'ZZ', 'XY', 'YZ', 'ZX')),
        ('TOSTRAIN', 'E', '1', meanings['TOSTRAIN']['measure'] or 'unknown_total_strain_measure',
         ('XX', 'YY', 'ZZ', 'XY', 'YZ', 'ZX')),
        ('PE', 'PEEQ', '1', 'equivalent_plastic_strain', ('',)),
    ]
