"""Read-only, exact B32R identity across native FCStd label compaction.

A label is not geometry. Never infer a new label by its magnitude, enumeration
position or nearest neighbour. The saved native coordinates must identify a
unique bijection, and BOTH ordered Seg3/B32R connectivities must commute with
that bijection. CAD pins remain byte-for-byte/value-for-value comparisons.

Only an explicit successful beam apply stores a reference. Inspection/freeze
can use that reference, but must not rewrite metadata or old frozen results.
Legacy records without raw mesh evidence cannot bridge a changed mesh hash.
"""
from copy import deepcopy
import math

from caelab.beam_model import BeamInputError
from caelab.storage import canonical_hash

SCHEMA = 'caelab-beam-mesh-reference/1'
REFERENCE_KEY = 'mesh_reference'
_MESH_KEYS = ('nodes', 'elements')
_GEOMETRY_KEYS = ('end_node_ids', 'edge_start_mm', 'edge_end_mm')


def _fail(message):
    raise BeamInputError('mesh_id', message + ' 원 메시와 참조를 확인한 뒤 명시적으로 다시 지정하세요. 초안과 이전 결과는 유지됩니다.')


def _identifier(value):
    if type(value) is not int or value <= 0:
        _fail('절점·요소 번호가 올바르지 않습니다.')
    return value


def _xyz(value):
    # Do not round or turn strings into coordinates. Python numeric equality
    # treats +/-0 as the same coordinate, and compares int/float exactly.
    if not isinstance(value, list) or len(value) != 3:
        _fail('저장된 원 좌표가 올바르지 않습니다.')
    try:
        valid = all(type(v) in (int, float) and math.isfinite(v) for v in value)
    except OverflowError:
        valid = False
    if not valid:
        _fail('저장된 원 좌표에 유한하지 않거나 숫자가 아닌 값이 있습니다.')
    return tuple(value)


def _mesh(value):
    """Index only unique native entities, preserving local order and mid-node role."""
    if not isinstance(value, dict):
        _fail('검증할 원 메시가 없습니다.')
    rows, cells = value.get('nodes'), value.get('elements')
    if not isinstance(rows, list) or not rows or not isinstance(cells, list) or not cells:
        _fail('원 절점·요소 목록이 없습니다.')
    nodes, at_coordinate = {}, {}
    for row in rows:
        if not isinstance(row, dict) or set(row) != {'id', 'xyz_mm'}:
            _fail('원 절점 기록의 형식이 다릅니다.')
        n, xyz = _identifier(row['id']), _xyz(row['xyz_mm'])
        if n in nodes:
            _fail('절점 번호가 중복됐습니다.')
        if xyz in at_coordinate:
            _fail('같은 좌표의 절점이 둘 이상이라 대응이 모호합니다.')
        nodes[n], at_coordinate[xyz] = xyz, n
    elements, at_connectivity = {}, {}
    used, mids, corners = set(), set(), set()
    for row in cells:
        if not isinstance(row, dict) or set(row) != {'id', 'native_nodes', 'ccx_nodes'}:
            _fail('원 요소 기록의 형식이 다릅니다.')
        e = _identifier(row['id'])
        native, ccx = row['native_nodes'], row['ccx_nodes']
        for connection in (native, ccx):
            if not isinstance(connection, list) or len(connection) != 3:
                _fail('3절점 선 요소의 연결이 필요합니다.')
            if any(_identifier(n) not in nodes for n in connection) or len(set(connection)) != 3:
                _fail('요소 연결에 없는 절점이나 중복 절점이 있습니다.')
        if ccx != [native[0], native[2], native[1]]:
            _fail('Seg3와 B32R의 연결 순서 또는 중간절점 역할이 다릅니다.')
        signature = (tuple(native), tuple(ccx))
        if e in elements or signature in at_connectivity:
            _fail('요소 번호 또는 같은 연결의 요소가 중복되어 대응이 모호합니다.')
        if native[2] in mids:
            _fail('서로 다른 요소가 중간절점을 공유합니다.')
        elements[e], at_connectivity[signature] = signature, e
        used.update(native); corners.update(native[:2]); mids.add(native[2])
    if used != set(nodes) or mids & corners:
        _fail('고립 절점 또는 서로 다른 중간·끝 절점 역할이 있습니다.')
    return nodes, at_coordinate, elements, at_connectivity


def _payload(value):
    return {key: deepcopy(value[key]) for key in _MESH_KEYS}


def _geometry(value, nodes):
    try:
        ends = value['end_node_ids']
        if (not isinstance(ends, list) or len(ends) != 2 or
                any(_identifier(n) not in nodes for n in ends) or len(set(ends)) != 2):
            _fail('저장된 양 끝 절점이 올바르지 않습니다.')
        start, end = _xyz(value['edge_start_mm']), _xyz(value['edge_end_mm'])
        if start == end:
            _fail('모서리의 진행 방향이 없습니다.')
        return ends, start, end
    except KeyError:
        _fail('원 모서리와 끝점 대응 자료가 없습니다.')


def capture_reference(model, binding):
    """Prepare a detached reference; the caller publishes it inside native apply."""
    nodes, _, _, _ = _mesh(model)
    _geometry(model, nodes)
    payload = _payload(model)
    digest = canonical_hash(payload)
    if not isinstance(binding, dict) or digest != binding.get('mesh_sha256'):
        _fail('현재 메시와 참조의 확인값이 일치하지 않습니다.')
    return {'schema': SCHEMA, 'mesh_sha256': digest, **payload,
            **{key: deepcopy(model[key]) for key in _GEOMETRY_KEYS}}


def require_same_binding(record, model, current_binding):
    """Return explicit old->current label maps, or raise; never mutate inputs.

    The binding's only relaxed field is its ID-sensitive mesh hash, and only
    after independently checking the full saved mesh against that hash. No
    tolerance, arithmetic numbering rule, CAD pin relaxation or fallback to an
    unrelated frozen calculation is permitted. Current labels remain native.
    """
    old_binding = record.get('binding')
    if not isinstance(old_binding, dict) or not isinstance(current_binding, dict):
        _fail('저장된 메시 참조가 없습니다.')
    pins = lambda b: {k: v for k, v in b.items() if k != 'mesh_sha256'}
    if pins(old_binding) != pins(current_binding):
        raise BeamInputError('edge', '형상·배치·메시 객체·끝점 참조가 변경됐습니다. 확인한 뒤 참조를 다시 지정하세요.')

    current = capture_reference(model, current_binding)
    nn, coordinates, ee, connectivity = _mesh(current)
    current_ends, start, end = _geometry(current, nn)
    if REFERENCE_KEY not in record:
        # Backward compatibility for an unchanged old record, NOT a migration
        # from its hash. The next explicit apply captures the complete reference.
        if old_binding != current_binding:
            _fail('이전 저장에는 번호 변경을 검증할 원 메시가 없습니다. 번호만으로 자동 복구하지 않습니다.')
        return {'kind': 'IDENTICAL_LEGACY', 'nodes': {n: n for n in nn},
                'elements': {e: e for e in ee}}
    old = record[REFERENCE_KEY]
    if (not isinstance(old, dict) or set(old) !=
            {'schema', 'mesh_sha256', *_MESH_KEYS, *_GEOMETRY_KEYS} or old.get('schema') != SCHEMA):
        _fail('저장된 원 메시 참조의 형식 또는 버전이 다릅니다.')
    on, _, oe, _ = _mesh(old)
    old_ends, old_start, old_end = _geometry(old, on)
    if canonical_hash(_payload(old)) != old.get('mesh_sha256') or old.get('mesh_sha256') != old_binding.get('mesh_sha256'):
        _fail('저장된 원 메시와 참조의 확인값이 일치하지 않습니다.')
    if start != old_start or end != old_end:
        _fail('모서리의 원 좌표 또는 진행 방향이 변경됐습니다.')
    if len(on) != len(nn) or len(oe) != len(ee):
        _fail('원 메시와 현재 메시의 절점·요소 수가 다릅니다.')
    if set(on.values()) != set(coordinates):
        _fail('원 메시와 현재 메시의 좌표가 정확히 일치하지 않습니다.')
    node_map = {old_id: coordinates[xyz] for old_id, xyz in on.items()}
    element_map = {}
    for old_id, signature in oe.items():
        mapped = tuple(tuple(node_map[n] for n in order) for order in signature)
        if mapped not in connectivity:
            _fail('요소 연결·방향 또는 중간절점 역할이 변경됐습니다.')
        element_map[old_id] = connectivity[mapped]
    if len(set(element_map.values())) != len(ee):
        _fail('요소 대응을 유일하게 정할 수 없습니다.')
    if [node_map[n] for n in old_ends] != current_ends:
        raise BeamInputError('ends', 'CAD 끝점과 빔 끝 절점의 대응이 변경됐습니다. 양 끝 참조를 다시 확인하세요.')
    return {'kind': 'IDENTICAL' if old_binding == current_binding else 'RENUMBERED',
            'nodes': node_map, 'elements': element_map}
