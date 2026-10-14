"""Retained one-axis curves for Post. No solver, interpolation library or store.

Raw row order and quality survive even when alignment is refused. The only
interpolation is an explicitly requested adjacent, valid bracket of source B.
"""
from copy import deepcopy
import base64
import hashlib
import json
import math
from pathlib import Path
import struct
import xml.etree.ElementTree as ET

from .post_comparison import affine_unit, validate_observable, UNKNOWN_OBSERVABLE
from .storage import canonical_hash

MAX_ROWS = 20000
MAX_BYTES = 16 * 1024 * 1024
AXIS_KINDS = ('physical_time', 'load_parameter', 'displacement', 'strain', 'other')
MEANING = ('quantity', 'measure', 'frame', 'observable', 'reduction', 'temperature_kind')


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def numeric(value):
    # Non-finite spelling survives separately in raw; it never becomes zero.
    try:
        result = float(value)
    except (ValueError, TypeError):
        return None
    return result if math.isfinite(result) else None


def plain(value):
    if hasattr(value, 'tolist'):
        return plain(value.tolist())
    if isinstance(value, dict):
        return {str(k): plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(v) for v in value]
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    return value


def observable_for(component):
    # These are explicit named scalar response components, not tuple-size guesses.
    from .post_comparison import observable_value, COMPONENTS
    if component in ('x', 'y', 'z'):
        return observable_value('vector', component)
    if component in COMPONENTS:
        return observable_value('tensor', component)
    if component == 'scalar':
        return observable_value('scalar', 'scalar')
    return deepcopy(UNKNOWN_OBSERVABLE)


def from_response(response, *, origin, title):
    r = plain(response)
    axes = r.get('axes', [])
    if r.get('kind') != 'series' or len(axes) != 1:
        raise ValueError('하나의 명시된 가로축을 가진 저장 채널을 선택하세요.')
    raw = r.get('raw_samples') or {}
    values = raw.get('transformed_value', r.get('value', []))
    x = raw.get('transformed_axis', axes[0].get('values', []))
    n = len(values)
    if (not 1 <= n <= MAX_ROWS or not isinstance(x, list) or len(x) != n
            or any(isinstance(v, (list, dict)) for v in values)):
        raise ValueError('곡선은 1–20000행의 단일 성분이어야 합니다.')
    identities = raw.get('source_rows', r.get('source_rows', list(range(n))))
    def column(key, default):
        vals = raw.get(key, default)
        if not isinstance(vals, list) or len(vals) != n:
            raise ValueError('저장된 원행과 품질 열의 길이가 다릅니다: ' + key)
        return vals
    quality = column('quality_valid', r.get('mask', [True] * n))
    calculation = column('calculation_valid', [True] * n)
    visible = column('display_visible', [True] * n)
    qreason = column('quality_reasons', [''] * n)
    creason = column('exclusion_reasons', [''] * n)
    if len(identities) != n or any(type(v) is not bool for vals in (quality, calculation, visible) for v in vals):
        raise ValueError('원행과 명시적 유효성 열을 확인하세요.')
    segments = [0] * n
    if not raw:
        for segment_id, segment in enumerate(r.get('segments', [{'rows': [0, n]}])):
            lo, hi = segment['rows']
            if not (type(lo) is int and type(hi) is int and 0 <= lo < hi <= n):
                raise ValueError('저장된 구간이 원행 범위와 다릅니다.')
            for i in range(lo, hi):
                segments[i] = segment_id
    rows = []
    for i, (xi, yi) in enumerate(zip(x, values)):
        rows.append({'identity': {'kind': r.get('source_row_kind', 'retained_row'), 'row': identities[i]},
            'x': numeric(xi), 'y': numeric(yi), 'raw_x': deepcopy(xi), 'raw_y': deepcopy(yi),
            'quality': quality[i], 'calculation': calculation[i], 'visible': visible[i],
            'quality_reason': qreason[i], 'exclusion_reason': creason[i], 'segment': segments[i]})
    declaration = {'units': r.get('unit'), 'quantity': r.get('quantity'),
        'measure': r.get('measure'), 'frame': r.get('frame'),
        'location': r.get('location'), 'reduction': r.get('reduction', 'none'),
        'observable': deepcopy(r.get('observable', observable_for(r.get('component')))),
        'temperature_kind': r.get('temperature_kind')}
    result = {'version': 1, 'kind': 'retained_curve', 'title': title, 'origin': plain(origin),
        'declaration': declaration, 'axis': {k: deepcopy(v) for k, v in axes[0].items() if k != 'values'},
        'rows': rows, 'provenance': {k: r[k] for k in ('mapping', 'calibration', 'source_selector',
            'coordinate_system', 'source_row_kind', 'raw_samples', 'role') if k in r}}
    if len(json.dumps(result, ensure_ascii=False, allow_nan=False).encode()) > MAX_BYTES:
        raise ValueError('곡선이 16 MiB를 초과합니다.')
    return result


def configured(curve, side):
    """Bind explicit declarations without rewriting any known source meaning."""
    result = deepcopy(curve)
    original = result['declaration']
    supplied = side.get('declaration', {})
    for key in (*MEANING, 'units', 'location'):
        value = original.get(key)
        known = value not in (None, '', 'UNKNOWN', 'UNSPECIFIED', UNKNOWN_OBSERVABLE)
        if key in supplied:
            if known and supplied[key] != value:
                raise ValueError('저장된 물리량 정의를 바꿀 수 없습니다: ' + key)
            original[key] = deepcopy(supplied[key])
    axis = result['axis']
    for key in ('name', 'unit', 'semantics'):
        if key in side.get('axis', {}):
            if axis.get(key) not in (None, '', 'UNKNOWN') and axis[key] != side['axis'][key]:
                raise ValueError('저장된 가로축 선언과 다릅니다: ' + key)
            axis[key] = side['axis'][key]
    bounds = side.get('rows', [0, len(result['rows'])])
    if (not isinstance(bounds, list) or len(bounds) != 2 or any(type(i) is not int for i in bounds)
            or not 0 <= bounds[0] < bounds[1] <= len(result['rows'])):
        raise ValueError('원곡선의 시작/끝 행을 확인하세요. 끝 행은 포함하지 않습니다.')
    result['rows'] = result['rows'][bounds[0]:bounds[1]]
    result['selected_rows'] = bounds
    return result


def _usable(row):
    return finite(row['x']) and finite(row['y']) and row['quality'] and row['calculation']


def _known(value):
    return isinstance(value, str) and value.strip() and value not in ('UNKNOWN', 'UNSPECIFIED')


def _alignment(a, b, recipe):
    ad, bd = a['declaration'], b['declaration']
    for key in ('quantity', 'measure', 'frame', 'reduction'):
        if not _known(ad.get(key)) or ad.get(key) != bd.get(key):
            raise ValueError('양쪽의 동일한 물리량·측도·기준계·축약을 확인하세요: ' + key)
    if validate_observable(ad.get('observable')) != validate_observable(bd.get('observable')):
        raise ValueError('서로 다른 성분 또는 불변량입니다. 원벡터 없이 성분 기저를 바꾸지 않습니다.')
    if recipe.get('locations_confirmed') is not True:
        raise ValueError('선택한 두 위치를 비교 대상으로 확인하세요.')
    if not _known(ad.get('location')) or not _known(bd.get('location')):
        raise ValueError('비교할 실제 측정 위치를 지정하세요.')
    if ad.get('temperature_kind') != bd.get('temperature_kind'):
        raise ValueError('절대온도와 온도차를 함께 비교할 수 없습니다.')
    kind = recipe.get('axis_kind')
    if kind not in AXIS_KINDS:
        raise ValueError('가로축의 물리 의미를 선택하세요.')
    for curve in (a, b):
        axis = curve['axis']
        semantic = axis.get('semantics')
        if semantic in ('STATIC_LOAD_PARAMETER', 'DIMENSIONLESS_MODEL_TIME') and kind != 'load_parameter':
            raise ValueError('하중 단계 매개변수는 물리시간이 아닙니다.')
        if kind == 'physical_time' and axis.get('unit') not in ('s', 'ms', 'us', 'min', 'h'):
            raise ValueError('물리시간에는 실제 시간 단위가 필요합니다.')
        if kind == 'load_parameter' and axis.get('unit') != '1':
            raise ValueError('하중 매개변수의 단위는 1입니다.')
        dimension = {'displacement': 'length', 'strain': 'dimensionless'}.get(kind)
        if dimension:
            from .experiment_calibration import UNITS
            if UNITS.get(axis.get('unit'), (None,))[0] != dimension:
                raise ValueError('가로축의 단위와 선택한 물리 의미가 다릅니다.')
        if semantic not in (None, '', 'UNKNOWN', 'STATIC_LOAD_PARAMETER', 'DIMENSIONLESS_MODEL_TIME') and axis.get('unit') in ('s', 'ms', 'us', 'min', 'h') and kind != 'physical_time':
            raise ValueError('선언된 실제 시각을 다른 물리량으로 다시 이름 붙일 수 없습니다.')
        if not _known(recipe.get('axis_origins', {}).get('a' if curve is a else 'b')):
            raise ValueError('양쪽 축 원점을 명시하세요.')
    if kind == 'other' and not _known(recipe.get('axis_meaning')):
        raise ValueError('비교할 가로축의 실제 물리 의미를 명시하세요.')
    target_unit = recipe.get('target_unit')
    sa, oa = affine_unit(ad.get('units'), target_unit, ad['quantity'], ad.get('temperature_kind'))
    sb, ob = affine_unit(bd.get('units'), target_unit, bd['quantity'], bd.get('temperature_kind'))
    # Axis conversion is never a response conversion. Small time unit aliases
    # are explicit and do not make a static parameter a physical clock.
    time = {'s': 1., 'ms': .001, 'us': .000001, 'min': 60., 'h': 3600.}
    au, bu = a['axis'].get('unit'), b['axis'].get('unit')
    if kind == 'physical_time':
        sx = time[bu] / time[au]
    else:
        sx, axis_offset = affine_unit(bu, au, kind)
        if axis_offset:
            raise ValueError('이 가로축의 offset 단위 변환은 지원하지 않습니다.')
    shift = recipe.get('b_axis_offset', 0.)
    if not finite(shift):
        raise ValueError('B 축 원점 이동량을 A 축 단위로 입력하세요.')
    mode = recipe.get('alignment')
    if mode not in ('exact', 'bracket'):
        raise ValueError('정확한 표본 또는 명시적인 두 표본 사이 보간을 선택하세요.')
    gap = recipe.get('max_gap')
    if mode == 'bracket' and (not finite(gap) or gap <= 0):
        raise ValueError('보간에 허용할 최대 표본 간격을 A 축 단위로 입력하세요.')
    tolerance = recipe.get('axis_tolerance', 0.)
    if not finite(tolerance) or tolerance < 0:
        raise ValueError('축 대응의 절대 허용오차를 확인하세요.')
    # Input order is a physical path. Never sort away a loading/unloading branch.
    for curve in (a, b):
        coords = [r['x'] for r in curve['rows'] if finite(r['x'])]
        if any(y <= x for x, y in zip(coords, coords[1:])):
            raise ValueError('중복 또는 역방향 축이 있습니다. 단조로운 원행 구간을 명시적으로 선택하세요.')
    return sa, oa, sb, ob, sx, shift, mode, gap, tolerance


def compare(a, b, recipe):
    """Always preserve the original curves; incompatibility blocks only alignment."""
    a, b = configured(a, recipe['a']), configured(b, recipe['b'])
    result = {'version': 3, 'a': a, 'b': b, 'recipe': deepcopy(recipe), 'rows': [], 'blocked': None}
    try:
        sa, oa, sb, ob, sx, shift, mode, gap, tolerance = _alignment(a, b, recipe)
    except (ValueError, TypeError, KeyError) as error:
        result['blocked'] = str(error)
        return result
    bx = [r['x'] * sx + shift if finite(r['x']) else None for r in b['rows']]
    b_transformed = [r['y'] * sb + ob if finite(r['y']) else None for r in b['rows']]
    a_transformed = [r['y'] * sa + oa if finite(r['y']) else None for r in a['rows']]
    result.update(b_axis=bx, a_values=a_transformed, b_values=b_transformed)
    def groups(rows):
        group = 0; previous = None; result = []
        for row in rows:
            usable = _usable(row)
            if not usable or previous is None or previous != row['segment']:
                group += 1
            result.append(group if usable else None)
            previous = row['segment'] if usable else None
        return result
    ag, bg = groups(a['rows']), groups(b['rows'])
    finite_x = [(x, i) for i, x in enumerate(bx) if finite(x)]
    import bisect
    xs = [x for x, _ in finite_x]
    for i, row in enumerate(a['rows']):
        x, av = row['x'], a_transformed[i]
        out = {'row_index': i, 'a_row': deepcopy(row['identity']), 'x': x,
            'a_raw': row['y'], 'a': av, 'a_valid': _usable(row), 'b': None, 'b_raw': None,
            'b_rows': [], 'weight': None, 'delta': None, 'percent': None,
            'valid': False, 'b_valid': False, 'a_segment': ag[i], 'b_segment': None,
            'reason': 'axis_missing', 'percent_reason': 'difference_unavailable'}
        result['rows'].append(out)
        if not finite(x):
            continue
        near = [(v, j) for v, j in finite_x[max(0, bisect.bisect_left(xs, x-tolerance)):
                                              bisect.bisect_right(xs, x+tolerance)]]
        if len(near) > 1:
            result['blocked'] = '허용오차 안에 B 표본이 둘 이상입니다. 축 허용오차 또는 구간을 수정하세요.'
            result['rows'] = []
            return result
        weight, endpoints = 0., []
        if near:
            endpoints = [near[0][1]]
        elif mode == 'bracket':
            k = bisect.bisect_left(xs, x)
            if 0 < k < len(finite_x):
                lo, hi = finite_x[k-1][1], finite_x[k][1]
                if hi != lo+1 or b['rows'][lo]['segment'] != b['rows'][hi]['segment']:
                    out['reason'] = 'missing_segment'; continue
                if bx[hi]-bx[lo] > gap:
                    out['reason'] = 'gap_exceeds_limit'; continue
                endpoints, weight = [lo, hi], (x-bx[lo])/(bx[hi]-bx[lo])
        if not endpoints:
            out['reason'] = 'outside_b_range' if not xs or x < xs[0] or x > xs[-1] else 'no_exact_sample'
            continue
        out.update(b_rows=[deepcopy(b['rows'][j]['identity']) for j in endpoints], weight=weight,
                   b_axis=[bx[j] for j in endpoints])
        if not all(_usable(b['rows'][j]) for j in endpoints):
            out['reason'] = 'b_excluded_or_missing'; continue
        out.update(b_valid=True, b_segment=bg[endpoints[0]])
        values = [b_transformed[j] for j in endpoints]
        raws = [b['rows'][j]['y'] for j in endpoints]
        out['b'] = values[0] if len(values) == 1 else (1-weight)*values[0]+weight*values[1]
        out['b_raw'] = raws[0] if len(raws) == 1 else (1-weight)*raws[0]+weight*raws[1]
        if not _usable(row):
            out['reason'] = 'a_excluded_or_missing'; continue
        delta = out['b']-av
        if not finite(delta):
            out['reason'] = 'nonfinite_difference'; continue
        out.update(delta=delta, valid=True, reason='valid')
        denominator = abs(av)
        if ad_kind := a['declaration'].get('temperature_kind'):
            if ad_kind == 'absolute':
                out['percent_reason'] = 'absolute_temperature_disabled'; continue
        if denominator == 0:
            out['percent_reason'] = 'zero_a'; continue
        percent = 100*delta/denominator
        if finite(percent):
            out.update(percent=percent, percent_reason='valid')
        else:
            out['percent_reason'] = 'nonfinite_percent'
    return result


def write_table(path, curve):
    """Standard uncompressed inline-binary Float64 VTK XML; no VTK dependency."""
    root = ET.Element('VTKFile', type='Table', version='1.0', byte_order='LittleEndian', header_type='UInt32')
    table = ET.SubElement(root, 'Table')
    piece = ET.SubElement(table, 'Piece', NumberOfRows=str(len(curve['rows'])))
    data = ET.SubElement(piece, 'RowData')
    for name, values in (('axis', [r['x'] for r in curve['rows']]),
                         ('value', [r['y'] for r in curve['rows']])):
        raw = struct.pack('<'+'d'*len(values), *[float(v) if v is not None else math.nan for v in values])
        node = ET.SubElement(data, 'DataArray', type='Float64', Name=name, NumberOfComponents='1', format='binary')
        node.text = base64.b64encode(struct.pack('<I', len(raw))+raw).decode('ascii')
    ET.ElementTree(root).write(path, encoding='utf-8', xml_declaration=True)


def load_curve(entry, metadata):
    spec = metadata.get('curve') if isinstance(metadata, dict) else None
    if not isinstance(spec, dict) or set(spec) != {'file', 'sha256'} or spec['file'] != 'curve.json':
        raise ValueError('보존 곡선의 등록 정보를 확인하세요.')
    path = Path(entry).parent / spec['file']
    if path.stat().st_size > MAX_BYTES or hashlib.sha256(path.read_bytes()).hexdigest() != spec['sha256']:
        raise ValueError('보존 곡선 원자료가 변경되었습니다.')
    curve = json.loads(path.read_text(encoding='utf-8'))
    if curve.get('kind') != 'retained_curve' or curve.get('version') != 1 or not 1 <= len(curve.get('rows', [])) <= MAX_ROWS:
        raise ValueError('지원하지 않는 보존 곡선입니다.')
    return curve, path


def snapshot(workbench, reference, response):
    from .research_operations import _resolve
    from .storage import save_json
    document = workbench.document_read(reference.get('document_id'))
    if document.get('kind') != 'data':
        raise ValueError('Data에 저장된 시험 채널을 선택하세요.')
    result = _resolve(reference, workbench.document_read, workbench.document_result)
    if result.get('execution_status') != 'SUCCEEDED' or response not in result.get('responses', {}):
        raise ValueError('완료된 저장 Data의 실제 채널을 선택하세요.')
    curve = from_response(result['responses'][response],
        origin={'reference': deepcopy(reference), 'response': response,
                'response_sha256': canonical_hash(result['responses'][response])},
        title=document.get('title', '시험') + ' / ' + response)
    if canonical_hash(_resolve(reference, workbench.document_read, workbench.document_result)) != reference['result_sha256']:
        raise ValueError('곡선을 읽는 동안 저장 결과가 변경되었습니다.')
    payload = json.dumps(curve, ensure_ascii=False, allow_nan=False).encode('utf-8')
    receipt = workbench.upload('curve.json', payload)
    folder = workbench.root / 'inputs' / receipt['id']
    (folder / 'source.json').rename(folder / 'curve.json')
    path = folder / 'curve.vtt'
    write_table(path, curve)
    def pin(p):
        return {'file': p.relative_to(workbench.root).as_posix(), 'relative': p.name,
                'bytes': p.stat().st_size, 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}
    files = [pin(path), pin(folder/'curve.json')]
    metadata = {'curve': {'file': 'curve.json', 'sha256': files[1]['sha256']}}
    receipt.update(name=curve['title'][:240], kind='native_curve', format='vtt', file=files[0]['file'],
        bytes=files[0]['bytes'], sha256=files[0]['sha256'], files=files,
        total_bytes=sum(p['bytes'] for p in files), native_metadata=metadata,
        native_metadata_sha256=canonical_hash(metadata), origin=deepcopy(curve['origin']))
    save_json(folder/'input.json', receipt)
    return receipt
