"""Versioned project-local view state; never domain/reference storage or QSettings.

Opaque view keys address layout only. Anchors identify graph positions; exact
saved/result/input references remain exclusively in their existing domain owners.
"""
from __future__ import annotations
from copy import deepcopy
import math
from pathlib import Path
import uuid

from .portable_project_io import json_file, no_links, fail, fingerprint_file, copy_verified
from .storage import canonical_hash, check_id, save_json

FORMAT = 'caelab.connection-view/1'
RELATIVE = 'workbench/views/connection.json'
MAX_NODES = 1024
MAX_STATE_BYTES = 96 * 1024


def store_scope(wb):
    # Runtime envelope, never persisted inside a domain ref. Both path and live
    # controller session prevent aliasing cloned stores with identical IDs.
    return {'store_key': canonical_hash(str(wb.workspace)), 'service_session_id': wb.session_id}


def check_scope(wb, scope):
    if scope != store_scope(wb):
        raise ValueError('다른 보관소 또는 이전 서비스의 선택입니다. 현재 창에서 문서를 다시 선택하세요.')


def default_state():
    return {'bindings': [], 'positions': {}, 'selected': None, 'checked_documents': [],
            'filter': '', 'graph_documents': None, 'panel': {'tab': 0, 'document_visible': True, 'document_width': 265, 'zoom': 1.0}}


def validate_state(state):
    import json
    if not isinstance(state, dict) or set(state) != set(default_state()):
        raise ValueError('프로젝트 연결 배치의 필드가 다릅니다. 바이너리 창 설정은 읽지 않습니다.')
    if len(json.dumps(state, ensure_ascii=False, allow_nan=False).encode()) > MAX_STATE_BYTES:
        raise ValueError('연결 배치는 96 KiB 이하입니다. 문서 선택을 나누세요.')
    bindings = state['bindings']
    if not isinstance(bindings, list) or len(bindings) > MAX_NODES:
        raise ValueError('배치 노드 수가 한도를 넘습니다.')
    keys, anchors = set(), set()
    for row in bindings:
        if not isinstance(row, dict) or set(row) != {'view_key', 'anchor'}:
            raise ValueError('배치 키와 노드 위치 식별자를 구분하세요.')
        key = check_id(row['view_key'])
        if not key.startswith('V') or key in keys:
            raise ValueError('배치 키는 중복할 수 없습니다.')
        anchor = row['anchor']
        if not isinstance(anchor, dict) or anchor.get('type') not in {'document', 'reference', 'run', 'source'}:
            raise ValueError('지원하지 않는 배치 노드입니다.')
        expected = {'type', 'document_id'} | {'reference': {'path'}, 'run': {'job_id'}, 'source': {'data_id'}}.get(anchor['type'], set())
        if set(anchor) != expected:
            raise ValueError('배치 위치에는 정확한 참조 내용/파일 경로를 넣지 않습니다.')
        check_id(anchor['document_id'])
        if anchor['type'] == 'reference':
            path = anchor['path']
            if (not isinstance(path, list) or not 1 <= len(path) <= 12 or
                    any(not ((type(p) is int and 0 <= p < 100000) or
                             (isinstance(p, str) and 0 < len(p) <= 128 and not any(ord(c) < 32 for c in p))) for p in path)):
                raise ValueError('배치의 관계 위치가 잘못되었습니다.')
        for field in ('job_id', 'data_id'):
            if field in anchor:
                check_id(anchor[field])
        signature = canonical_hash(anchor)
        if signature in anchors:
            raise ValueError('한 노드에는 하나의 배치 키를 사용하세요.')
        keys.add(key); anchors.add(signature)
    if not isinstance(state['positions'], dict) or set(state['positions']) - keys:
        raise ValueError('배치 좌표에 알 수 없는 노드가 있습니다.')
    for position in state['positions'].values():
        if (not isinstance(position, list) or len(position) != 2 or
                any(type(v) not in (int, float) or not math.isfinite(v) or abs(v) > 1.e6 for v in position)):
            raise ValueError('배치 좌표는 유한한 두 숫자여야 합니다.')
    if state['selected'] is not None and state['selected'] not in keys:
        raise ValueError('선택한 배치 노드가 없습니다.')
    checked = state['checked_documents']
    if not isinstance(checked, list) or len(checked) > 256 or len(set(checked)) != len(checked):
        raise ValueError('체크한 문서 목록이 잘못되었습니다.')
    for identifier in checked:
        check_id(identifier)
    graph_documents = state['graph_documents']
    if graph_documents is not None:
        if not isinstance(graph_documents, list) or not 1 <= len(graph_documents) <= 256:
            raise ValueError('그래프 필터에는 선택한 실제 문서 목록을 지정하세요.')
        for identifier in graph_documents:
            check_id(identifier)
        if len(set(graph_documents)) != len(graph_documents):
            raise ValueError('그래프 문서 필터에 중복이 있습니다.')
    if not isinstance(state['filter'], str) or len(state['filter']) > 200:
        raise ValueError('문서 필터는 200자 이하입니다.')
    panel = state['panel']
    if (not isinstance(panel, dict) or set(panel) != set(default_state()['panel']) or
            type(panel['tab']) is not int or panel['tab'] not in (0, 1) or
            type(panel['document_visible']) is not bool or type(panel['document_width']) is not int or
            not 180 <= panel['document_width'] <= 640 or type(panel['zoom']) not in (int, float) or
            not math.isfinite(panel['zoom']) or not .25 <= panel['zoom'] <= 2.5):
        raise ValueError('지원하는 보기 패널 상태가 아닙니다.')
    return deepcopy(state)


def _read(wb):
    path = wb.workspace / RELATIVE
    no_links(path)
    if not path.exists():
        return {'format': FORMAT, 'view_id': None, 'revision': 0, 'state': default_state(), 'last_command': None}
    record = json_file(path)
    if (not isinstance(record, dict) or set(record) != {'format', 'view_id', 'revision', 'state', 'last_command'}
            or record['format'] != FORMAT or type(record['revision']) is not int or record['revision'] < 1):
        raise ValueError('프로젝트 배치 버전을 읽을 수 없습니다. 원 배치 파일은 보존했습니다.')
    check_id(record['view_id'])
    last = record['last_command']
    if last is not None:
        if not isinstance(last, dict) or set(last) != {'id', 'request_sha256'}:
            raise ValueError('배치 저장 명령의 확인 기록이 잘못되었습니다.')
        check_id(last['id'])
        digest = last['request_sha256']
        if not isinstance(digest, str) or len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
            raise ValueError('배치 저장 명령의 확인값이 잘못되었습니다.')
    validate_state(record['state'])
    return record


def read_view(wb):
    with wb.material_documents._lock('ViewConnectionState'):
        record = _read(wb)
        return {'format': FORMAT, 'scope': store_scope(wb), 'revision': record['revision'],
                'state': deepcopy(record['state']), 'state_sha256': canonical_hash(record['state']),
                'view_id': record['view_id'], 'executed': False}


def save_view(wb, state, *, scope, expected_revision, expected_sha256, command_id):
    check_scope(wb, scope)
    state = validate_state(state)
    command_id = check_id(command_id)
    if type(expected_revision) is not int or expected_revision < 0:
        raise ValueError('정확한 배치 개정을 지정하세요.')
    signature = canonical_hash({'state': state, 'expected_revision': expected_revision,
                                'expected_sha256': expected_sha256, 'scope': scope})
    with wb.material_documents._lock('ViewConnectionState'):
        current = _read(wb)
        last = current['last_command']
        if last and last.get('id') == command_id:
            if last.get('request_sha256') != signature:
                raise ValueError('배치 요청 ID가 이전 요청과 충돌합니다.')
            return {**read_view(wb), 'status': 'ALREADY_SAVED'}
        if current['revision'] != expected_revision or canonical_hash(current['state']) != expected_sha256:
            fail('STALE_VIEW', wb.workspace / RELATIVE, '다른 창에서 배치를 저장했습니다. 현재 선택은 유지됩니다.',
                 '서버 배치를 다시 읽고 현재 배치를 유지할지 명시적으로 선택하세요.')
        record = {'format': FORMAT, 'view_id': current['view_id'] or 'V' + uuid.uuid4().hex,
                  'revision': current['revision'] + 1, 'state': state,
                  'last_command': {'id': command_id, 'request_sha256': signature}}
        save_json(wb.workspace / RELATIVE, record)
        return {**read_view(wb), 'status': 'SAVED'}


def attach_anchors(graph):
    for row in graph['nodes']:
        kind = row['node_type']
        owner = row.get('consumer_id') if kind == 'reference' else row.get('owner_id')
        if not owner:
            continue
        anchor = {'type': kind, 'document_id': owner}
        if kind == 'reference':
            anchor['path'] = row['path']
        elif kind == 'run':
            anchor['job_id'] = row['job_id']
        elif kind == 'source':
            anchor['data_id'] = row['diagnostic']['data_id']
        row['view_anchor'] = anchor
    return graph


def merge_bindings(graph, state):
    """Pure UI helper. Generating a view key never changes an exact ref or owner."""
    state = validate_state(state)
    seen = {canonical_hash(row['anchor']): row['view_key'] for row in state['bindings']}
    keys = {}
    for node in graph['nodes']:
        anchor = node.get('view_anchor')
        if anchor is None:
            continue
        digest = canonical_hash(anchor)
        if digest not in seen:
            if len(state['bindings']) >= MAX_NODES:
                raise ValueError('배치 노드 한도에 도달했습니다. 프로젝트 문서 선택을 줄이세요.')
            seen[digest] = 'V' + uuid.uuid4().hex
            state['bindings'].append({'view_key': seen[digest], 'anchor': deepcopy(anchor)})
        keys[node['key']] = seen[digest]
    return state, keys


def view_inventory(wb):
    path = wb.workspace / RELATIVE
    if not path.exists():
        return None
    _read(wb)
    return {'path': RELATIVE, **fingerprint_file(path)}


def transfer_view(wb, stage, document_map, expected):
    if expected is None:
        return
    current = _read(wb)
    copy_verified(wb.workspace / RELATIVE, stage / 'portable/originals/connection-view.json', expected)
    state = deepcopy(current['state'])
    state['bindings'] = [row for row in state['bindings'] if row['anchor']['document_id'] in document_map]
    keys = {row['view_key'] for row in state['bindings']}
    for row in state['bindings']:
        row['anchor']['document_id'] = document_map[row['anchor']['document_id']]
    state['positions'] = {key: value for key, value in state['positions'].items() if key in keys}
    if state['selected'] not in keys:
        state['selected'] = None
    state['checked_documents'] = [document_map[i] for i in state['checked_documents'] if i in document_map]
    if state['graph_documents'] is not None:
        state['graph_documents'] = [document_map[i] for i in state['graph_documents'] if i in document_map] or None
    validate_state(state)
    save_json(stage / RELATIVE, {'format': FORMAT, 'view_id': 'V' + uuid.uuid4().hex,
        'revision': 1, 'state': state, 'last_command': None})
