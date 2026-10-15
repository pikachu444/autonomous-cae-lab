"""Exact original-row navigation for retained v3 comparisons.

This is a read/identity adapter, not a curve engine or an authority store.  Native
rows arrive through the existing authenticated Post owner; Data rows are resolved
through the existing retained-result resolver.  No import, snapshot, fit or job
is submitted here.  A comparison's local row number is never a solver ID.
"""
from copy import deepcopy

from .post_curves import MAX_ROWS, configured, from_response
from .storage import canonical_hash

RAW_FIELDS = ('identity', 'x', 'y', 'raw_x', 'raw_y', 'quality', 'calculation',
              'visible', 'quality_reason', 'exclusion_reason', 'segment')
FULL_ORIGIN_FIELDS = ('kind', 'document_id', 'session_id', 'pid', 'project', 'workspace',
                      'object_ref', 'revision', 'recipe_sha256',
                      'result_files_sha256', 'result_sha256')


def raw_record(row):
    """Normalize only native-table bool storage, never raw acquisition values."""
    if not isinstance(row, dict) or any(k not in row for k in RAW_FIELDS):
        raise ValueError('보존 원행의 값·품질·표시 정보가 불완전합니다. 비교를 다시 읽으세요.')
    value = {k: deepcopy(row[k]) for k in RAW_FIELDS}
    if not isinstance(value['identity'], dict) or not value['identity']:
        raise ValueError('원행 식별자가 없습니다. 표시 순번으로 대신 열지 않습니다.')
    for key in ('quality', 'calculation', 'visible'):
        if value[key] not in (False, True, 0., 1.):
            raise ValueError('보존 원행의 명시적 유효성 값이 잘못되었습니다.')
        value[key] = bool(value[key])
    if type(value['segment']) not in (int, float) or int(value['segment']) != value['segment']:
        raise ValueError('원행의 구간 번호가 잘못되었습니다.')
    value['segment'] = int(value['segment'])
    return value


def unique(rows, key, value):
    hits = [row for row in rows if row.get(key) == value]
    if len(hits) != 1:
        raise ValueError('원행이 없거나 식별자가 중복됩니다. 다른 행을 추정하여 열지 않습니다.')
    return hits[0]


def targets(payload, table, row_index):
    """Follow stored a_row/b_rows, including both B brackets, without math.

    payload must contain the original rows required by this selection.  The
    native adapter fetches missing pages; GUI previews may only show local rows.
    Every returned entry is one ACTUAL original, including excluded/hidden rows.
    """
    if (payload.get('semantics') != 'retained_curve_comparison' or table not in ('a', 'b', 'aligned')
            or type(row_index) is not int or row_index < 0):
        raise ValueError('저장된 v3 비교의 원곡선 또는 대응 행을 선택하세요.')
    summary = payload['summary']
    originals = payload['originals']
    correspondence = None
    if table == 'aligned':
        correspondence = unique(payload['rows'], 'row_index', row_index)
        b_rows = correspondence.get('b_rows', [])
        if not isinstance(b_rows, list) or len(b_rows) > 2:
            raise ValueError('저장된 B 대응은 정확 행 하나 또는 양쪽 원행이어야 합니다.')
        if len(b_rows) == 2 and b_rows[0] == b_rows[1]:
            raise ValueError('B의 양쪽 원행이 중복됩니다.')
        pairs = [('a', unique(originals['a'], 'identity', correspondence['a_row']))]
        pairs += [('b', unique(originals['b'], 'identity', identity)) for identity in b_rows]
    else:
        pairs = [(table, unique(originals[table], 'row_index', row_index))]
    answer = []
    for tag, row in pairs:
        source = summary['sources'][tag]
        index = row['row_index']
        bounds = source.get('selected_rows')
        if (type(index) is not int or not isinstance(bounds, list) or len(bounds) != 2
                or any(type(i) is not int for i in bounds)
                or not 0 <= bounds[0] < bounds[1] <= MAX_ROWS or not 0 <= index < bounds[1]-bounds[0]):
            raise ValueError('보존 원곡선의 선택 구간과 원행 위치가 다릅니다.')
        answer.append({'side': tag, 'source_index': bounds[0]+index, 'raw': raw_record(row),
            'title': source['title'], 'origin': deepcopy(source['origin']),
            'selector': deepcopy(summary['recipe'][tag]),
            'declaration': deepcopy(source['declaration']), 'axis': deepcopy(source['axis']),
            'selected_rows': deepcopy(bounds),
            'common_x': deepcopy(row.get('common_x')), 'common_y': deepcopy(row.get('common_y')),
            'correspondence': deepcopy(correspondence)})
    return answer


def verify_curve(curve, target):
    """Check the selected raw row against the already-retained source curve."""
    if curve['origin'] != target['origin']:
        raise ValueError('원곡선의 저장 참조가 다릅니다. 최신 자료로 바꾸지 않았습니다.')
    bound = configured(curve, target['selector'])  # existing declaration/bounds guard
    if (bound['axis'] != target['axis'] or bound['declaration'] != target['declaration']
            or bound['selected_rows'] != target['selected_rows']):
        raise ValueError('원곡선의 성분·축·단위·선택 구간 선언이 다릅니다.')
    index = target['source_index']
    if (type(index) is not int or not 0 <= index < len(curve['rows'])
            or not target['selected_rows'][0] <= index < target['selected_rows'][1]):
        raise ValueError('원행이 저장 구간 밖에 있습니다.')
    row = unique(bound['rows'], 'identity', target['raw']['identity'])
    if row != curve['rows'][index] or raw_record(row) != raw_record(target['raw']):
        raise ValueError('원행의 값·품질·포함·숨김 또는 구간이 변경되었습니다.')
    return row


def read_data(client, target, *, with_lineage=True):
    """Resolve exact Data job/input/result/response twice; never read latest draft."""
    from .research_operations import _resolve
    target = deepcopy(target)
    origin = target.get('origin', {})
    if set(origin) != {'reference', 'response', 'response_sha256'}:
        raise ValueError('원 시험 자료의 보존 결과 참조와 응답 해시가 필요합니다.')
    reference, name = origin['reference'], origin['response']
    document = client.document_read(reference['document_id'])
    if document.get('kind') != 'data':
        raise ValueError('시험 자료는 정확한 Data 결과 소유자에서 읽습니다.')
    result = _resolve(reference, client.document_read, client.document_result)
    response = result.get('responses', {}).get(name)
    if (result.get('execution_status') != 'SUCCEEDED' or response is None
            or canonical_hash(response) != origin['response_sha256']):
        raise ValueError('보존 시험 응답이 없거나 변경되었습니다. 새 가져오기는 하지 않았습니다.')
    curve = from_response(response, origin=origin, title=target['title'])
    row = verify_curve(curve, target)
    # Reusing the resolver also rechecks retention and the exact submitted input.
    if canonical_hash(_resolve(reference, client.document_read, client.document_result)) != reference['result_sha256']:
        raise ValueError('원 시험 자료를 읽는 중 결과가 바뀌었습니다.')
    acquired = response.get('raw_samples') or {}
    acquisition_rows = []
    if acquired:
        identities, values, axes = (acquired.get(key) for key in ('source_rows', 'value', 'axis'))
        if (not isinstance(identities, list) or not isinstance(values, list) or not isinstance(axes, list)
                or len(identities) != len(values) or len(identities) != len(axes)):
            raise ValueError('보존된 취득 원행·원축·원값의 길이가 일치하지 않습니다.')
        acquisition_rows = [{'source_row': identity, 'axis': axis, 'value': value}
                            for identity, axis, value in zip(identities, axes, values)]
    answer = {'status': 'DATA_VERIFIED', 'target_sha256': canonical_hash(target),
              'reference': {'kind': 'result', **deepcopy(reference), 'response': name},
              'response': deepcopy(response), 'curve': curve, 'row': deepcopy(row),
              'source_index': target['source_index'], 'lineage_status': 'NOT_CHECKED',
              'acquisition_rows': acquisition_rows}
    if with_lineage:
        answer.update(read_lineage(client, target))
    return answer


def read_lineage(client, target):
    """Post lineage is optional and independent of successful Data verification."""
    reference = target['origin']['reference']
    try:
        observation = client.post_observation(reference)
    except (ValueError, OSError, RuntimeError, KeyError) as error:
        # A failed optional lineage read must not invent a Post origin, nor hide
        # a source failure as a successful return.  Data itself stays readable.
        status = 'NOT_PRESENT' if 'does not contain a native Post measurement origin' in str(error) else 'UNAVAILABLE'
        return {'lineage_status': status, 'lineage_error': str(error)}
    origin = observation.get('origin', {})
    if origin.get('kind') != 'post_measurement':
        return {'lineage_status': 'NOT_PRESENT'}
    if (target['origin']['response'] != 'measured'
            or canonical_hash(observation.get('response')) != target['origin']['response_sha256']):
        return {'lineage_status': 'UNAVAILABLE', 'lineage_error': '시험 응답과 Post에서 인도한 채널이 다릅니다.'}
    if not observation.get('source_available'):
        return {'lineage_status': 'UNAVAILABLE', 'lineage_error': observation.get('source_error')}
    # A processed/derived ID is never silently cast to a physical CSV row.
    identity = target['raw']['identity']
    if identity.get('kind') != 'physical_line' or type(identity.get('row')) is not int:
        return {'lineage_status': 'UNAVAILABLE', 'lineage_error': '이 곡선의 행은 원 CSV 행이 아닙니다. 저장된 처리 계보에서 확인하세요.'}
    try:
        mapping = unique(origin.get('row_identity', []), 'source_row', identity['row'])
        from .post_observation import verify_origin
        verify_origin(origin)
        full = {key: deepcopy(origin[key]) for key in FULL_ORIGIN_FIELDS}
    except (ValueError, OSError, KeyError) as error:
        return {'lineage_status': 'UNAVAILABLE', 'lineage_error': str(error)}
    return {'lineage_status': 'AVAILABLE', 'native_target': {
        'kind': 'measurement_lineage', 'origin': full,
        'selection': deepcopy(origin['selection']), 'mapping': deepcopy(mapping),
        'summary_sha256': canonical_hash(origin['summary']),
        'native_column': deepcopy(origin['native_column']),
        'data_origin': deepcopy(target['origin']), 'data_raw': deepcopy(target['raw'])}}
