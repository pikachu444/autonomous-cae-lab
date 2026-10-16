"""Explicit supplied uncertainty on retained affine/processed measurements.

No import, read, or save calls this calculation. The Data channel and its DAG
remain authoritative; this module neither recalibrates values nor selects rows.
Only first-order VALUE propagation at frozen coordinates is implemented.
"""
from __future__ import annotations

from copy import deepcopy
import math
from typing import Any

import numpy as np

from .experiment_calibration import UNITS, factor, validate_calibration
from .storage import canonical_hash

MAX_VARIABLES = 512
MAX_SAMPLES = 512
# Exact maximal-known-block validation is bounded, never silently truncated.
MAX_PSD_BLOCKS = 4096
MAX_PSD_SEARCH_NODES = 65536
METADATA = ('location', 'component', 'measure', 'frame', 'coordinate_system',
            'coordinate_frame', 'direction', 'position', 'axes')


class PropagationUnavailable(ValueError):
    """The selected propagation is unavailable; original data remain readable."""


class InvalidCovariance(ValueError):
    """A supplied/propagated known covariance block is mathematically invalid."""


def plain(value: Any) -> Any:
    """Preserve nonfinite original tokens; never convert an unknown into zero."""
    if isinstance(value, np.ndarray):
        return plain(value.tolist())
    if isinstance(value, np.generic):
        return plain(value.item())
    if isinstance(value, dict):
        return {str(k): plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(v) for v in value]
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    return deepcopy(value)


def _number(value, label):
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, float, np.number)) or not math.isfinite(value):
        raise ValueError(label + ': 유한한 수치가 필요합니다.')
    return float(value)


def _unit(unit):
    """Existing calibration units, plus one explicit coefficient ratio."""
    if not isinstance(unit, str):
        raise ValueError('단위를 명시하세요.')
    if unit in {'mm^2','m^2'}:
        return (('area',1),), {'mm^2':1e-6,'m^2':1.}[unit]
    if unit in UNITS:
        dimension, scale = UNITS[unit]
        return (() if dimension == 'dimensionless' else ((dimension, 1),)), scale
    if unit.count('/') != 1:
        raise ValueError('지원하지 않는 불확실성 단위: ' + unit)
    numerator, denominator = unit.split('/')
    if numerator not in UNITS or denominator not in UNITS:
        raise ValueError('계수 단위에는 지원 단위의 명시 비율을 입력하세요: ' + unit)
    dims = {}
    for name, exponent in ((numerator, 1), (denominator, -1)):
        dimension = UNITS[name][0]
        if dimension != 'dimensionless':
            dims[dimension] = dims.get(dimension, 0) + exponent
    return tuple(sorted((k, v) for k, v in dims.items() if v)), UNITS[numerator][1] / UNITS[denominator][1]


def unit_factor(source, target):
    a, sa = _unit(source)
    b, sb = _unit(target)
    if a != b:
        raise ValueError(f'불확실성 단위가 다릅니다: {source} → {target}')
    return sa / sb


def _mask(value, count, name):
    if value is None:
        return [True] * count
    value = plain(value)
    if not isinstance(value, list) or len(value) != count or any(type(x) is not bool for x in value):
        raise ValueError(name + ': 원 표본과 같은 길이의 명시 선택이 필요합니다.')
    return value


def standard_uncertainty(record, target_unit):
    """Return (u, reason). Expanded U without supplied k stays UNKNOWN."""
    if record is None:
        return None, '제공 불확실성 없음'
    if not isinstance(record, dict) or set(record) - {'value', 'unit', 'kind', 'k', 'note', 'source', 'correlation'}:
        raise ValueError('제공 불확실성의 값·단위·종류·포함인자를 확인하세요.')
    if record.get('value') is None or record.get('kind') in (None, 'UNKNOWN'):
        return None, '불확실성 값 또는 종류 미확인'
    value = _number(record['value'], '불확실성')
    if value < 0:
        raise ValueError('불확실성은 음수일 수 없습니다.')
    value *= unit_factor(record.get('unit'), target_unit)
    if record['kind'] == 'expanded':
        if record.get('k') is None:
            return None, '확장 불확실성의 포함인자 k 미제공'
        k = _number(record['k'], '포함인자 k')
        if k <= 0:
            raise ValueError('포함인자 k는 양수여야 합니다.')
        value /= k
    elif record['kind'] != 'standard':
        raise ValueError('standard/expanded 또는 UNKNOWN을 선택하세요.')
    if not math.isfinite(value):
        raise ValueError('단위 변환 후 불확실성이 유한하지 않습니다.')
    return value, None


def covariance(variables, supplied, dependence):
    """Partial explicit covariance. NaN means missing, not independent/zero.

    The matrix is in the declared variables' units. A full supplied covariance
    can supply diagonal variances itself; a correlation matrix needs marginal u.
    Explicit zero u mathematically implies zero covariance; no correlation is
    inferred for any nonzero/unknown marginal.
    """
    ids = [row['id'] for row in variables]
    if not ids or len(ids) > MAX_VARIABLES or len(ids) != len(set(ids)):
        raise ValueError(f'서로 다른 불확실 입력은 1–{MAX_VARIABLES}개여야 합니다.')
    if not isinstance(supplied, dict) or set(supplied) - set(ids):
        raise ValueError('불확실성 입력이 선택한 원값/교정계수에 속하지 않습니다.')
    marginal = [standard_uncertainty(supplied.get(row['id']), row['unit']) for row in variables]
    u = np.asarray([x if x is not None else np.nan for x, _ in marginal])
    C = np.full((len(ids), len(ids)), np.nan)
    np.fill_diagonal(C, u * u)
    reasons = {key: reason for key, (_, reason) in zip(ids, marginal) if reason}
    dependence = deepcopy(dependence)
    if dependence is None or dependence == {'kind': 'UNKNOWN'}:
        pass
    elif not isinstance(dependence, dict):
        raise ValueError('상관/공분산은 명시 객체 또는 UNKNOWN이어야 합니다.')
    elif dependence.get('kind') == 'independent_declared':
        if set(dependence) != {'kind', 'note'} or not isinstance(dependence['note'], str) or not dependence['note'].strip():
            raise ValueError('독립성은 근거 설명과 함께 명시 선언하세요.')
        for i in range(len(ids)):
            for j in range(len(ids)):
                if i != j and math.isfinite(u[i]) and math.isfinite(u[j]):
                    C[i, j] = 0.
    else:
        kind = dependence.get('kind')
        required = {'kind', 'order', 'matrix', 'note'} | ({'units'} if kind == 'covariance' else set())
        if kind not in ('correlation', 'covariance') or set(dependence) != required:
            raise ValueError('명시 correlation/covariance의 순서·행렬·단위·근거를 확인하세요.')
        if not isinstance(dependence['note'], str) or not dependence['note'].strip():
            raise ValueError('상관/공분산의 제공 근거를 명시하세요.')
        if dependence['order'] != ids:
            raise ValueError('상관/공분산 입력 순서가 원값/계수 순서와 다릅니다.')
        matrix = dependence['matrix']
        if not isinstance(matrix, list) or len(matrix) != len(ids) or any(not isinstance(row, list) or len(row) != len(ids) for row in matrix):
            raise ValueError('상관/공분산 행렬의 크기가 다릅니다.')
        A = np.asarray([[np.nan if x is None else _number(x, '공분산/상관') for x in row] for row in matrix])
        if not np.array_equal(np.isnan(A), np.isnan(A.T)) or not np.allclose(A, A.T, rtol=1e-12, atol=0., equal_nan=True):
            raise ValueError('상관/공분산은 누락 위치를 포함해 대칭이어야 합니다.')
        if kind == 'correlation':
            if np.any(np.abs(A[np.isfinite(A)]) > 1.) or np.any(np.diag(A)[np.isfinite(np.diag(A))] != 1.):
                raise ValueError('상관은 -1…1, 제공 대각 성분은 1이어야 합니다.')
            C = A * np.outer(u, u)
            # Missing self-correlation does not erase supplied variance.
            np.fill_diagonal(C, u * u)
        else:
            units = dependence['units']
            if not isinstance(units, list) or len(units) != len(ids):
                raise ValueError('공분산 축마다 단위가 필요합니다.')
            factors = np.asarray([unit_factor(a, b['unit']) for a, b in zip(units, variables)])
            C = A * np.outer(factors, factors)
            if np.any(np.diag(C)[np.isfinite(np.diag(C))] < 0):
                raise ValueError('분산은 음수일 수 없습니다.')
            for i, (value, _) in enumerate(marginal):
                if value is not None and math.isfinite(C[i, i]) and not math.isclose(C[i, i], value**2, rel_tol=1e-10, abs_tol=0.):
                    raise ValueError('제공 표준불확실성과 공분산 대각 성분이 다릅니다: ' + ids[i])
                if not math.isfinite(C[i, i]) and value is not None:
                    # A missing matrix diagonal cannot erase independently
                    # supplied standard uncertainty for that same variable.
                    C[i, i] = value**2
                if math.isfinite(C[i, i]):
                    reasons.pop(ids[i], None)
    for i, variance in enumerate(np.diag(C).copy()):
        if variance == 0.:
            known = np.isfinite(C[i])
            if np.any(C[i, known] != 0.):
                raise ValueError('0 분산과 0이 아닌 공분산은 양립할 수 없습니다.')
            C[i, :] = C[:, i] = 0.
    for i in range(len(ids)):
        for j in range(i):
            if np.isfinite(C[[i, j], [i, j]]).all() and math.isfinite(C[i, j]):
                if abs(C[i, j]) > math.sqrt(C[i, i]) * math.sqrt(C[j, j]) * (1 + 1e-12):
                    raise ValueError('공분산이 제공 분산의 허용 범위를 넘습니다.')
    if np.isfinite(C).all():
        _psd(C)
    return C, reasons


def _psd(C):
    if not len(C):
        return
    if not np.isfinite(C).all() or np.any(np.diag(C) < 0):
        raise InvalidCovariance('공분산의 분산은 유한하고 음수가 아니어야 합니다.')
    zero = np.diag(C) == 0
    if np.any(C[zero, :] != 0):
        raise InvalidCovariance('0 분산과 0이 아닌 공분산은 양립할 수 없습니다.')
    diag = np.sqrt(np.diag(C))
    active = diag > 0
    # The pre-existing DIMENSIONLESS tolerance is unchanged. No eigenvalue
    # clipping, diagonal jitter or physical-unit-dependent acceptance.
    A = C[np.ix_(active, active)] / np.outer(diag[active], diag[active])
    if not np.allclose(A, A.T, rtol=1e-12, atol=1e-12):
        raise InvalidCovariance('공분산이 표준불확실성 정규화 기준에서 대칭이 아닙니다.')
    if len(A) and np.linalg.eigvalsh(A)[0] < -1e-12 * max(1., float(np.linalg.norm(A, 2))):
        raise InvalidCovariance('제공 공분산이 양의 준정부호가 아닙니다.')


def _known_principal_psd(C, indexes, label):
    """Check every maximal fully-known relevant principal block, exactly.

    A finite entry is an edge, NOT a zero imputation. Every fully known
    principal submatrix lies in a maximal clique, so testing those suffices
    for the claim made here. Nonchordal missing-covariance completion is NOT
    inferred or solved. A bounded search that cannot finish is UNKNOWN, not
    a successful covariance check. Common full and independent cases are one
    block; disjoint/overlapping partial blocks remain independently readable.
    """
    indexes = sorted(set(int(i) for i in indexes))
    known = {i for i in indexes if np.isfinite(C[i, i])}
    neighbours = {i: {j for j in known if i != j and np.isfinite(C[i, j])
                       and np.isfinite(C[j, i])} for i in known}
    blocks, largest, visits = 0, 0, 0

    def check(block):
        nonlocal blocks, largest
        blocks += 1
        if blocks > MAX_PSD_BLOCKS:
            raise PropagationUnavailable('알려진 결합 공분산 block 검사 한도를 넘었습니다. 누락 관계를 채우지 않습니다.')
        ordered = sorted(block)
        try:
            _psd(C[np.ix_(ordered, ordered)])
        except InvalidCovariance as error:
            raise InvalidCovariance(label + ' principal block ' + str(ordered) + ': ' + str(error)) from error
        largest = max(largest, len(ordered))

    def visit(chosen, pending, done):
        nonlocal visits
        visits += 1
        if visits > MAX_PSD_SEARCH_NODES:
            raise PropagationUnavailable('부분 공분산의 정확한 결합 검사 한도를 넘었습니다. 검증 성공으로 표시하지 않습니다.')
        if not pending:
            if not done and chosen:
                check(chosen)
            return
        # Avoid depth/search overhead for full matrices and large known blocks.
        if not done and all(pending - {v} <= neighbours[v] for v in pending):
            check(chosen | pending)
            return
        pivot = max(pending | done, key=lambda v: (len(pending & neighbours[v]), -v))
        for vertex in sorted(pending - neighbours[pivot]):
            visit(chosen | {vertex}, pending & neighbours[vertex], done & neighbours[vertex])
            pending.remove(vertex)
            done.add(vertex)

    visit(set(), set(known), set())
    unknown = sum(not np.isfinite(C[i, j]) for k, i in enumerate(indexes) for j in indexes[k:])
    return {'checked_maximal_blocks': blocks, 'largest_block_size': largest,
            'unknown_entries_upper_triangle': int(unknown),
            'status': 'KNOWN_PRINCIPAL_BLOCKS_VALIDATED',
            'complete_joint_covariance': 'VALIDATED' if indexes and not unknown else 'UNKNOWN',
            'missing_covariance_completion': 'NOT_PERFORMED'}


def validate_retained_covariance(result):
    """Read-only guard for downstream use of even pre-C1 stored analyses.

    Does not rerun propagation or touch the stored result. The original value,
    masks and failed results remain ordinary owner-readable. A stale success
    with an invalid known joint block cannot become new Study/report evidence.
    """
    if result.get('kind') != 'experiment_uncertainty':
        return
    a = result.get('experiment_analysis', {})
    rows = a.get('rows', [])
    computed = [i for i, row in enumerate(rows) if row.get('status') == 'COMPUTED_FIRST_ORDER']
    if not computed:
        return
    p = a['source_problem']
    C = np.asarray(a['input_covariance'], dtype=float)
    Y = np.asarray(a['output_covariance'], dtype=float)
    G = np.asarray(p['sensitivities'], dtype=float)
    if (G.shape != (len(rows), len(p['variables'])) or C.shape != (G.shape[1], G.shape[1])
            or Y.shape != (len(rows), len(rows))):
        raise InvalidCovariance('보존한 결합 공분산/민감도 크기가 다릅니다.')
    if any(not p['included'][i] or not np.isfinite(G[i]).all() for i in computed):
        raise InvalidCovariance('보존 계산 행이 원 mask/민감도와 다릅니다.')
    for matrix in (C, Y):
        if np.isinf(matrix).any() or not np.array_equal(np.isnan(matrix), np.isnan(matrix.T)):
            raise InvalidCovariance('보존 공분산의 누락 위치/유한성이 다릅니다.')
    relevant = np.flatnonzero(np.any(G[computed] != 0, axis=0))
    if any(not np.isfinite(C[np.ix_(np.flatnonzero(G[i] != 0), np.flatnonzero(G[i] != 0))]).all()
           or not np.isfinite(Y[i, i]) for i in computed):
        raise InvalidCovariance('보존 계산 행에 필요한 불확실성 정보가 없습니다.')
    _known_principal_psd(C, relevant, '보존 입력')
    _known_principal_psd(Y, computed, '보존 출력')


def propagate_linear(variables, sensitivities, supplied, dependence, *, included=None):
    """First-order G C G^T, without a missing-correlation default."""
    C, missing = covariance(variables, supplied, dependence)
    G = np.asarray(sensitivities, dtype=float)
    if G.ndim != 2 or G.shape[1] != len(variables) or len(G) > MAX_SAMPLES:
        raise ValueError('민감도와 원 표본/입력 개수가 다릅니다.')
    included = _mask(included, len(G), '전파 선택')
    values, rows = [], []
    for i, g in enumerate(G):
        active = np.flatnonzero(g != 0)
        if not included[i]:
            value, state, reason = None, 'EXCLUDED', '원 품질·계산 선택 또는 Plan mask에서 제외됨'
        elif not np.isfinite(g).all():
            value, state, reason = None, 'UNKNOWN', '유한한 값 민감도가 없음'
        elif not np.isfinite(C[np.ix_(active, active)]).all():
            absent = [(variables[a]['id'], variables[b]['id']) for a in active for b in active if b >= a and not math.isfinite(C[a, b])]
            value, state, reason = None, 'UNKNOWN', '불확실성/공분산 미제공: ' + ', '.join(a if a == b else a+' ↔ '+b for a, b in absent)
        else:
            sub = C[np.ix_(active, active)]
            _psd(sub)
            # Exclude unneeded NaN entries rather than multiplying 0*NaN.
            variance = float(g[active] @ sub @ g[active])
            rounding = float(np.abs(g[active]) @ np.abs(sub) @ np.abs(g[active])) * 1e-12
            if not math.isfinite(variance) or variance < -rounding:
                raise ValueError('전파 분산이 유한하지 않거나 음수입니다.')
            value, state, reason = math.sqrt(max(0., variance)), 'COMPUTED_FIRST_ORDER', None
        values.append(value)
        rows.append({'index': i, 'status': state, 'standard_uncertainty': value, 'reason': reason})
    computed = [i for i, value in enumerate(values) if value is not None]
    relevant = np.flatnonzero(np.any(G[computed] != 0, axis=0)) if computed else []
    # Per-output variance validity is insufficient: even identity G can expose
    # a known indefinite 3x3 block hidden by a fourth UNKNOWN/excluded input.
    input_audit = _known_principal_psd(C, relevant, '관련 입력')
    output_covariance = []
    for i, gi in enumerate(G):
        out = []
        for j, gj in enumerate(G):
            ai, aj = np.flatnonzero(gi != 0), np.flatnonzero(gj != 0)
            sub = C[np.ix_(ai, aj)]
            if values[i] is None or values[j] is None or not np.isfinite(sub).all():
                out.append(None)
            else:
                value = float(gi[ai] @ sub @ gj[aj])
                if not math.isfinite(value):
                    raise ValueError('전파 공분산이 유한하지 않습니다.')
                out.append(value)
        output_covariance.append(out)
    Y = np.asarray(output_covariance, dtype=float).reshape((len(G), len(G)))
    output_audit = _known_principal_psd(Y, computed, '계산 출력')
    return {'rows': rows, 'standard_uncertainty': values, 'output_covariance': output_covariance,
            'joint_covariance_validation': {'input': input_audit, 'output': output_audit,
                'relevant_input_indexes': list(map(int, relevant)), 'computed_output_indexes': computed,
                'excluded_output_indexes': [i for i, included_i in enumerate(included) if not included_i]},
            'input_covariance': [[float(x) if math.isfinite(x) else None for x in row] for row in C],
            'missing_input_information': missing, 'correlation_assumption': plain(dependence)}


def calibration_problem(response, *, plan_mask=None):
    """Read original y and form derivatives, never call calibrate(y, recipe)."""
    response = plain(response)
    recipe = response.get('calibration') or response.get('mapping', {}).get('calibration')
    validate_calibration(recipe, response.get('unit'))
    raw = response.get('raw_samples')
    if not isinstance(raw, dict):
        raise PropagationUnavailable('원 표본이 보존되지 않아 입력/계수 전파를 할 수 없습니다.')
    rows = raw['source_rows']
    if len(rows) != len(set(rows)) or not rows or len(rows) > min(MAX_SAMPLES, MAX_VARIABLES-3):
        raise ValueError('원 표본 행이 없거나 중복되거나 한도를 넘습니다.')
    n = len(rows)
    if any(len(raw[key]) != n for key in ('value', 'transformed_value', 'calculation_valid', 'quality_valid')):
        raise ValueError('원 표본/교정값/품질 길이가 다릅니다.')
    selected = response.get('source_rows', [])
    if any(row not in rows for row in selected):
        raise ValueError('선택 표본이 원자료에 없습니다.')
    masks = _mask(plan_mask, len(selected), 'Plan mask')
    plan = dict(zip(selected, masks))
    units = recipe['input_unit'], recipe['coefficient_input_unit']
    sx = factor(*units)
    sz = factor(recipe['x0_unit'], units[1])
    variables = [{'id': 'raw:'+str(row), 'unit': units[0], 'value': raw['value'][i],
                  'source_row': row} for i, row in enumerate(rows)]
    variables += [{'id': key, 'unit': unit, 'value': recipe[key], 'calibration_source': recipe['source']}
                  for key, unit in (('a', recipe['output_unit']+'/'+units[1]),
                                    ('x0', recipe['x0_unit']), ('b', recipe['output_unit']))]
    G = np.zeros((n, n+3))
    for i, raw_value in enumerate(raw['value']):
        try:
            x = _number(raw_value, '원값')
        except ValueError:
            G[i, :] = np.nan
            continue
        G[i, i] = recipe['a'] * sx
        G[i, n:] = [x*sx - recipe['x0']*sz, -recipe['a']*sz, 1.]
    included = [bool(raw['calculation_valid'][i] and raw['quality_valid'][i] and plan.get(row, False)) for i, row in enumerate(rows)]
    return {'variables': variables, 'sensitivities': G.tolist(), 'included': included,
            'sample_ids': ['raw:'+str(row) for row in rows], 'values': raw['transformed_value'],
            'unit': response['unit'], 'metadata': {key: response.get(key, 'UNKNOWN') for key in METADATA},
            'original': response, 'supplied_output_uncertainty': deepcopy(recipe['uncertainty']),
            'coefficient_basis': 'analytic affine value derivatives; input and coefficient units explicit',
            'calibration_reapplied': False}


def processing_problem(channel, *, plan_mask=None):
    """Reuse trace_sample; supplement only affine coefficient derivatives.

    This walks the EXISTING frozen DAG, without changing/creating any node.
    validity_inputs never become value contributors. Their raw value is read
    only when needed for d[a(x-x0)+b]/da at an import with a == 0.
    """
    from .data_processing_lineage import trace_sample, verify_channel, raw_key
    channel = plain(channel)
    verify_channel(channel)
    nodes = channel['lineage']['nodes']
    count = len(channel['samples'])
    if not count or count > MAX_SAMPLES:
        raise ValueError('명시 전파 표본 한도를 넘습니다.')
    variables, gradients, traces, variable_index = [], [], [], {}
    raw_units = {}
    for node in nodes.values():
        if node.get('stage', {}).get('operation') != 'import_mapping':
            continue
        mapping = node['stage']['mapping']
        unit = (mapping.get('calibration') or {}).get('input_unit', mapping.get('unit'))
        for sid in node['validity_inputs']:
            if nodes[sid]['kind'] == 'raw':
                raw_units[canonical_hash(nodes[sid]['raw_ref'])] = unit
    def register(identifier, unit, value, **source):
        row = {'id': identifier, 'unit': unit, 'value': value, **source}
        if identifier in variable_index:
            old = variables[variable_index[identifier]]
            if old['unit'] != unit or old['value'] != value:
                raise ValueError('같은 원값/교정계수의 단위 또는 값이 다릅니다.')
        else:
            _unit(unit)
            variable_index[identifier] = len(variables)
            variables.append(row)
        return identifier
    memo, visiting = {}, set()
    output_uncertainties = {}
    def coefficients(sid):
        if sid in memo:
            return deepcopy(memo[sid])
        if sid in visiting:
            raise ValueError('처리 DAG가 순환합니다.')
        visiting.add(sid)
        node = nodes[sid]
        out = {}
        if node['kind'] != 'raw':
            mapping = node.get('stage', {}).get('mapping', {})
            c = mapping.get('calibration')
            if c:
                validate_calibration(c)
                raw_nodes = [nodes[k] for k in node['validity_inputs'] if nodes[k]['kind'] == 'raw']
                if len(raw_nodes) != 1 or not raw_nodes[0]['value_known']:
                    raise PropagationUnavailable('교정 계수 미분에 필요한 원값이 없습니다.')
                raw_value = _number(raw_nodes[0]['value'], '교정 원값')
                # Numeric equality of two recipes is NOT shared metrological
                # identity. The exact import application is shared across its
                # own samples, but distinct source channels remain distinct.
                application = {'source': node['stage'].get('source'),
                    'response_channel_id': node.get('response_channel_id'), 'mapping': mapping}
                prefix = 'cal:'+canonical_hash(application)+':'
                output_uncertainties[prefix] = {'application': deepcopy(application),
                    'provided_output_uncertainty': deepcopy(c.get('uncertainty', 'UNKNOWN'))}
                specs = [('a', c['output_unit']+'/'+c['coefficient_input_unit'],
                          raw_value*factor(c['input_unit'], c['coefficient_input_unit']) - c['x0']*factor(c['x0_unit'], c['coefficient_input_unit'])),
                         ('x0', c['x0_unit'], -c['a']*factor(c['x0_unit'], c['coefficient_input_unit'])),
                         ('b', c['output_unit'], 1.)]
                for key, unit, derivative in specs:
                    identifier = register(prefix+key, unit, c[key], calibration_source=c['source'], coefficient=key, calibration_application=application)
                    out[identifier] = derivative
            else:
                for edge in node['inputs']:
                    for key, value in coefficients(edge['sample_id']).items():
                        out[key] = out.get(key, 0.) + edge['coefficient']*value
        visiting.remove(sid)
        memo[sid] = out
        return deepcopy(out)
    cache = {}
    masks = _mask(plan_mask, count, 'Plan mask')
    included = []
    for i, sample in enumerate(channel['samples']):
        sid = sample['sample_id']
        good = bool(channel['operation_valid'][i] and channel['quality_valid'][i] and channel['calculation_valid'][i] and masks[i])
        included.append(good)
        if not channel['operation_valid'][i]:
            traces.append({'sample_id': sid, 'coefficient_status': 'NOT_APPLICABLE', 'terms': []})
            gradients.append({})
            continue
        trace = trace_sample(channel, sid, cache=cache)
        if trace['coefficient_status'] != 'KNOWN':
            raise PropagationUnavailable('확정된 signed 값 기여 계수가 없습니다.')
        gradient = {}
        for term in trace['terms']:
            reference = term['raw_ref']
            unit = raw_units[canonical_hash(reference)]
            identifier = register('raw:'+canonical_hash(raw_key(reference)), unit, term['raw_value'], raw_ref=reference)
            gradient[identifier] = gradient.get(identifier, 0.) + term['coefficient']
        gradient.update(coefficients(sid))
        traces.append(trace)
        gradients.append(gradient)
    if not variables:
        raise PropagationUnavailable('전파할 값/계수 입력이 없습니다. 원자료는 유지됩니다.')
    return {'variables': variables,
            'sensitivities': [[g.get(row['id'], 0.) for row in variables] for g in gradients],
            'included': included, 'sample_ids': [s['sample_id'] for s in channel['samples']],
            'values': deepcopy(channel['values']), 'unit': channel['metadata']['unit'],
            'metadata': {key: channel['metadata'].get(key, 'UNKNOWN') for key in METADATA},
            'original': channel, 'trace': traces,
            'supplied_output_uncertainty': list(output_uncertainties.values()),
            'coefficient_basis': 'signed value contributions conditional on frozen axes; affine import coefficients',
            'calibration_reapplied': False}


def propagate(problem, specification):
    """Explicit computation over an already bound source problem."""
    if problem.get('kind')=='observation_chain':
        from .experiment_observation_uncertainty import propagate as observation_propagate
        return observation_propagate(problem,specification)
    required = {'uncertainties', 'dependence', 'axis_uncertainty'}
    if not isinstance(specification, dict) or set(specification) - required - {'requested_transform'} or not required <= specification.keys():
        raise ValueError('원값/계수 불확실성·상관·축 불확실성을 명시하세요.')
    base = {'kind': 'experiment_uncertainty', 'responses': {}, 'checks': [],
            'experiment_analysis': {'source_problem': plain(problem), 'supplied': plain(specification),
                'measurement_uncertainty_source': 'SUPPLIED_INPUTS_ONLY',
                'scope': 'first_order_value_propagation_conditional_on_frozen_axis',
                'confidence_interval': 'UNKNOWN', 'global_uniqueness': 'UNKNOWN',
                'engineering_release': 'NOT_RELEASED', 'metadata': deepcopy(problem['metadata']),
                'unsupported_judgments': ['공간 투영/mesh mapping', 'actuator travel → specimen strain'],
                'model_calls': 0, 'calibration_reapplied': False}}
    axis = specification['axis_uncertainty']
    if axis not in ('UNKNOWN', 'fixed_coordinates_declared') or specification.get('requested_transform') not in (None, 'none'):
        reason = ('축 불확실성 미분·공간 투영·mesh mapping은 지원하지 않습니다. 값 조건부 전파와 원자료 읽기/저장은 별개입니다.')
        base.update(execution_status='REJECTED', failure_reason=reason)
        base['experiment_analysis'].update(status='UNKNOWN', reason=reason)
        return base
    try:
        result = propagate_linear(problem['variables'], problem['sensitivities'], specification['uncertainties'],
                                  specification['dependence'], included=problem['included'])
    except (InvalidCovariance, PropagationUnavailable) as error:
        # Keep the entire input and specification, but never retain a computed
        # prefix of an invalid joint result as successful uncertainty evidence.
        reason = str(error)
        base.update(execution_status='REJECTED', failure_reason=reason)
        base['experiment_analysis'].update(status='UNKNOWN', reason=reason,
            complete_measurement_uncertainty='UNKNOWN',
            covariance_validity='INVALID' if isinstance(error, InvalidCovariance) else 'UNKNOWN',
            rows=[{'index': i, 'sample_id': sid, 'original_value': value, 'unit': problem['unit'],
                   'status': 'UNKNOWN' if problem['included'][i] else 'EXCLUDED',
                   'standard_uncertainty': None,
                   'reason': reason if problem['included'][i] else '원 품질·계산 선택 또는 Plan mask에서 제외됨'}
                  for i, (sid, value) in enumerate(zip(problem['sample_ids'], problem['values']))])
        base['diagnostics'] = {'model_calls': 0, 'source_recalibrated': False, 'decision': 'NOT_RELEASED'}
        return base
    for row, sid, value in zip(result['rows'], problem['sample_ids'], problem['values']):
        row.update(sample_id=sid, original_value=value, unit=problem['unit'])
    count = sum(row['status'] == 'COMPUTED_FIRST_ORDER' for row in result['rows'])
    total = sum(problem['included'])
    base['experiment_analysis'].update(result, status='COMPUTED_FIRST_ORDER' if count == total and total else 'UNKNOWN',
        complete_measurement_uncertainty='UNKNOWN' if axis == 'UNKNOWN' else 'CONDITIONAL_FIRST_ORDER_ONLY')
    base['execution_status'] = 'SUCCEEDED' if count == total and total else 'PARTIAL_FAILURE' if count else 'REJECTED'
    base['diagnostics'] = {'model_calls': 0, 'decision': 'NOT_RELEASED', 'unknown_outputs': total-count,
                           'source_recalibrated': False}
    return base
