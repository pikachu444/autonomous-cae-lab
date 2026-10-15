"""FN32: trusted native PNG receipts in the existing immutable Report assets.

No renderer, result store, solver, provider, unit conversion or Study owner lives
here. Only a successful *stored broker command* may introduce an image. Reads of
an already retained asset never consult the mutable Post selection.
"""
from __future__ import annotations

import base64
import binascii
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import re
import struct
import zlib

from .storage import canonical_hash, check_id
from .post_observation import check_pin, file_pin

MAX_PNG_BYTES = 5 * 1024 * 1024  # Base64 + bounded metadata fit the existing 8 MiB asset.
MAX_METADATA_BYTES = 256 * 1024
MAX_PROJECT_BYTES = 16 * 1024 * 1024
MAX_PIXELS = 16_000_000
LEGACY_FORMAT = 'caelab.post-report-image/1'
FORMAT = 'caelab.post-report-image/2'


def _json_bytes(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True,
                      separators=(',', ':')).encode('utf-8')


def _sha(value):
    if not isinstance(value, str) or re.fullmatch(r'[0-9a-f]{64}', value) is None:
        raise ValueError('정확한 자료 해시가 필요합니다.')
    return value


def reference_error(reference):
    try:
        if not isinstance(reference, dict) or set(reference) != {'kind', 'command_id', 'snapshot_sha256'}:
            raise ValueError('보존한 Post 이미지 참조를 선택하세요.')
        if reference['kind'] != 'post_image':
            raise ValueError('Post 이미지 참조가 아닙니다.')
        check_id(reference['command_id'])
        _sha(reference['snapshot_sha256'])
    except (ValueError, TypeError, KeyError) as error:
        return str(error)
    return None


def _png_scanlines(compressed, width, height, depth, color, interlace):
    """Bound inflate by the exact scanline budget; validate PNG row filters.

    Do not decode/render pixels or keep an unbounded decompression result. Qt is
    still responsible for the display, but a CRC-valid corrupt zlib stream must
    not enter a durable Report asset in headless operation either.
    """
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[color]
    passes = ((0, 0, 1, 1),) if not interlace else (
        (0, 0, 8, 8), (4, 0, 8, 8), (0, 4, 4, 8), (2, 0, 4, 4),
        (0, 2, 2, 4), (1, 0, 2, 2), (0, 1, 1, 2))
    row_sizes = []
    for x, y, dx, dy in passes:
        columns = max(0, (width - x + dx - 1) // dx)
        rows = max(0, (height - y + dy - 1) // dy)
        if columns and rows:
            row_sizes.extend([1 + (columns * channels * depth + 7) // 8] * rows)
    expected = sum(row_sizes)
    decoder = zlib.decompressobj()
    count = next_filter = row = 0
    pending = b''.join(compressed)
    try:
        while pending:
            decoded = decoder.decompress(pending, 64 * 1024)
            pending = decoder.unconsumed_tail
            end = count + len(decoded)
            if end > expected:
                raise ValueError('PNG 압축 해제 크기가 헤더보다 큽니다.')
            while next_filter < end:
                if row >= len(row_sizes) or decoded[next_filter - count] > 4:
                    raise ValueError('PNG 행 필터가 잘못되었습니다.')
                next_filter += row_sizes[row]
                row += 1
            count = end
            if decoder.unused_data:
                raise ValueError('PNG 압축 스트림 뒤에 불필요한 데이터가 있습니다.')
        if count != expected or not decoder.eof or row != len(row_sizes):
            raise ValueError('PNG 압축 데이터 또는 이미지 행이 불완전합니다.')
    except zlib.error as error:
        raise ValueError('PNG 압축 데이터가 손상되었습니다.') from error


def png_dimensions(data: bytes) -> tuple[int, int]:
    """Bounded PNG integrity validation, NOT numerical/engineering validation.

    Check every CRC and the decoded pixel budget before handing bytes to Qt.
    No extension-only or caller-supplied 'image' assertion is trusted.
    """
    if not isinstance(data, bytes) or not 45 <= len(data) <= MAX_PNG_BYTES:
        raise ValueError('PNG는 5 MiB 이하의 완전한 이미지여야 합니다.')
    if data[:8] != b'\x89PNG\r\n\x1a\n':
        raise ValueError('실제 PNG 파일이 아닙니다.')
    offset, dimensions, compressed, palette, idat_ended = 8, None, [], False, False
    while offset < len(data):
        if offset + 12 > len(data):
            raise ValueError('PNG 청크가 잘렸습니다.')
        length = struct.unpack('>I', data[offset:offset + 4])[0]
        tag = data[offset + 4:offset + 8]
        end = offset + 12 + length
        if end > len(data):
            raise ValueError('PNG 데이터가 잘렸습니다.')
        chunk = data[offset + 8:end - 4]
        crc = struct.unpack('>I', data[end - 4:end])[0]
        if zlib.crc32(tag + chunk) & 0xffffffff != crc:
            raise ValueError('PNG 내용의 CRC가 일치하지 않습니다.')
        if dimensions is None and tag != b'IHDR':
            raise ValueError('PNG 헤더가 없습니다.')
        if tag == b'IHDR':
            if dimensions is not None or length != 13:
                raise ValueError('PNG 헤더가 중복되거나 잘못되었습니다.')
            width, height, depth, color, compression, filtering, interlace = struct.unpack('>IIBBBBB', chunk)
            depths = {0: {1, 2, 4, 8, 16}, 2: {8, 16}, 3: {1, 2, 4, 8}, 4: {8, 16}, 6: {8, 16}}
            if (not 0 < width <= 8192 or not 0 < height <= 8192 or width * height > MAX_PIXELS
                    or depth not in depths.get(color, set()) or compression or filtering or interlace not in (0, 1)):
                raise ValueError('지원하지 않는 PNG 형식 또는 이미지 크기입니다.')
            dimensions = (width, height)
        elif tag == b'PLTE':
            if palette or compressed or not 0 < length <= 768 or length % 3 or color in (0, 4):
                raise ValueError('PNG 팔레트가 잘못되었습니다.')
            if color == 3 and length // 3 > 2 ** depth:
                raise ValueError('PNG 팔레트가 색상 비트 수를 넘습니다.')
            palette = True
        elif tag == b'IDAT':
            if idat_ended or color == 3 and not palette:
                raise ValueError('PNG 데이터 순서 또는 팔레트가 잘못되었습니다.')
            compressed.append(chunk)
        elif tag == b'IEND':
            if length or not compressed or end != len(data):
                raise ValueError('PNG 종결 또는 이미지 데이터가 잘못되었습니다.')
            _png_scanlines(compressed, width, height, depth, color, interlace)
            return dimensions
        elif tag in (b'acTL', b'fcTL', b'fdAT'):
            raise ValueError('동영상 PNG는 정지 결과 이미지로 등록하지 않습니다.')
        elif not tag[0] & 32:
            raise ValueError('지원하지 않는 필수 PNG 청크입니다.')
        if compressed and tag != b'IDAT':
            idat_ended = True
        offset = end
    raise ValueError('PNG가 완성되지 않았습니다.')


def read_pinned(pin, maximum):
    """Hash the bytes actually read, not a check-then-reopen mutable pathname."""
    if not isinstance(pin, dict) or set(pin) != {'path', 'bytes', 'sha256'}:
        raise ValueError('원자료 파일 참조가 불완전합니다.')
    _sha(pin['sha256'])
    if type(pin['bytes']) is not int or not 0 < pin['bytes'] <= maximum:
        raise ValueError('원자료 크기가 지원 범위를 벗어났습니다.')
    with Path(pin['path']).open('rb') as stream:
        data = stream.read(maximum + 1)
    if len(data) != pin['bytes'] or hashlib.sha256(data).hexdigest() != pin['sha256']:
        raise ValueError('원자료가 없거나 저장된 해시와 다릅니다: ' + Path(pin['path']).name)
    return data


def saved_result(project, object_ref, revision):
    """Select the exact applied saved 3D analysis, not 'latest' or a raw source."""
    obj = project.get('analysis', {}).get('objects', {}).get(object_ref)
    if not isinstance(obj, dict) or obj.get('kind') not in ('filter', 'comparison'):
        raise ValueError('적용하고 저장한 3D 필터 또는 공간 비교 결과를 선택하세요.')
    history, position = obj.get('history', []), obj.get('position', -1)
    if type(position) is not int or not 0 <= position < len(history):
        raise ValueError('적용한 결과를 먼저 저장하세요.')
    record = history[position]
    if record.get('id') != revision:
        raise ValueError('선택한 결과가 정확한 저장 개정과 다릅니다.')
    if not record.get('result_files') or not record.get('result_file') or not record.get('view_name'):
        raise ValueError('저장된 결과 파일과 retained view가 필요합니다.')
    return obj, record


def _identity(record):
    return {key: record[key] for key in ('id', 'recipe', 'graph', 'bindings')}


def source_records(project, obj, record):
    """Follow exact retained dependency hashes, including non-current histories."""
    originals, visiting = {}, set()

    def visit(current_obj, current):
        key = (current_obj['id'], current['id'])
        if key in visiting:
            raise ValueError('저장된 결과의 입력 참조에 순환이 있습니다.')
        visiting.add(key)
        try:
            recipe = current['recipe']
            refs = ([recipe['a']['source_ref'], recipe['b']['source_ref']]
                    if current_obj['kind'] == 'comparison' else [recipe['source_ref']])
            for ref in refs:
                binding = current['bindings'][ref]
                if ref in project.get('sources', {}):
                    original = project['sources'][ref]
                    entry = Path(original['entry_path'])
                    pins = original['source_pins']
                    stamp = canonical_hash({'format': entry.suffix.lower(), 'files': sorted([
                        {'relative': Path(pin['path']).relative_to(entry.parent).as_posix(),
                         'bytes': pin['bytes'], 'sha256': pin['sha256']} for pin in pins], key=lambda p: p['relative'])})
                    if original.get('source_revision', stamp) != stamp or binding['revision'] != stamp:
                        raise ValueError('결과와 저장된 원입력 개정이 일치하지 않습니다.')
                    if original.get('native_metadata') is not None and canonical_hash(original['native_metadata']) != original.get('native_metadata_sha256'):
                        raise ValueError('원입력의 물리 선언 해시가 일치하지 않습니다.')
                    if binding.get('metadata') != original.get('native_metadata_sha256'):
                        raise ValueError('결과와 원입력의 물리 선언이 다릅니다.')
                    originals[ref] = deepcopy(original)
                else:
                    upstream = project['analysis']['objects'][ref]
                    matches = [r for r in upstream['history'] if canonical_hash(_identity(r)) == binding['revision']]
                    if len(matches) != 1:
                        raise ValueError('정확한 이전 입력 결과가 없거나 중복됩니다.')
                    visit(upstream, matches[0])
        finally:
            visiting.remove(key)

    visit(obj, record)
    return originals


def retained_analyses(project, obj, record):
    """All exact upstream applied graphs, not the current upstream UI positions."""
    rows, visited, active = [], set(), set()
    def visit(current_obj, current):
        key = (current_obj['id'], current['id'])
        if key in active:
            raise ValueError('결과 입력 그래프에 순환이 있습니다.')
        if key in visited:
            return
        active.add(key)
        recipe = current['recipe']
        refs = ([recipe['a']['source_ref'], recipe['b']['source_ref']]
                if current_obj['kind'] == 'comparison' else [recipe['source_ref']])
        for ref in refs:
            if ref in project.get('sources', {}):
                continue
            upstream = project['analysis']['objects'][ref]
            matches = [item for item in upstream['history']
                       if canonical_hash(_identity(item)) == current['bindings'][ref]['revision']]
            pinned = current.get('dependencies', {}).get(ref)
            if len(matches) != 1 or pinned is not None and matches[0]['id'] != pinned:
                raise ValueError('정확한 이전 입력 결과가 없거나 모호합니다.')
            visit(upstream, matches[0])
        rows.append({'object_ref': current_obj['id'], 'revision': current['id'],
                     'graph': deepcopy(current['graph']), 'recipe': deepcopy(current['recipe'])})
        active.remove(key); visited.add(key)
    visit(obj, record)
    return rows


def make_origin(project_pin, document_id, session_id, pid, object_ref, revision):
    project = json.loads(read_pinned(project_pin, MAX_PROJECT_BYTES).decode('utf-8-sig'))
    obj, record = saved_result(project, object_ref, revision)
    workspace = file_pin(Path(project_pin['path']).parent / project['workspace_file'])
    origin = {'kind': 'saved_post_result', 'document_id': document_id, 'session_id': session_id,
              'pid': pid, 'project': deepcopy(project_pin), 'workspace': workspace,
              'object_ref': object_ref, 'revision': revision,
              'identity_sha256': canonical_hash(_identity(record)),
              'result_files_sha256': canonical_hash(record['result_files']),
              'result_sha256': record['result_sha256'],
              'sources_sha256': canonical_hash(source_records(project, obj, record))}
    verify_origin(origin)
    return origin, project, obj, record


def verify_origin(origin):
    if not isinstance(origin, dict) or origin.get('kind') != 'saved_post_result':
        raise ValueError('저장된 Post 결과의 출처가 없습니다.')
    project = json.loads(read_pinned(origin['project'], MAX_PROJECT_BYTES).decode('utf-8-sig'))
    if project.get('document_id') != origin['document_id']:
        raise ValueError('Post 원문서가 다른 문서입니다.')
    path = Path(origin['project']['path'])
    workspace = check_pin(origin['workspace'])
    if ((path.parent / project['workspace_file']).resolve() != workspace
            or project.get('workspace_sha256') != origin['workspace']['sha256']):
        raise ValueError('Post 저장 상태와 workspace 파일이 다릅니다.')
    obj, record = saved_result(project, origin['object_ref'], origin['revision'])
    if (canonical_hash(_identity(record)) != origin['identity_sha256']
            or canonical_hash(record['result_files']) != origin['result_files_sha256']
            or record['result_sha256'] != origin['result_sha256']):
        raise ValueError('Post 원입력 또는 정확한 결과가 변경되었습니다.')
    pins = record['result_files']
    entry = [pin for pin in pins if Path(pin['path']).resolve() == Path(record['result_file']).resolve()]
    if len(entry) != 1 or entry[0]['sha256'] != record['result_sha256']:
        raise ValueError('정확한 결과 파일이 저장 참조에 없습니다.')
    originals = source_records(project, obj, record)
    if canonical_hash(originals) != origin['sources_sha256']:
        raise ValueError('원자료와 물리 선언이 변경되었습니다.')
    for pin in pins:
        check_pin(pin)
    for source in originals.values():
        for pin in source['source_pins']:
            check_pin(pin)
    return project, obj, record


def warp_conditions(lineage):
    return [{'type': node['type'], 'scale': node['properties'].get('ScaleFactor'),
             'object_ref': item['object_ref'], 'revision': item['revision'],
             'properties': deepcopy(node['properties'])} for item in lineage
            for node in item['graph'].get('nodes', []) if node['type'].startswith('Warp')]


def validate_snapshot(snapshot):
    if not isinstance(snapshot, dict) or snapshot.get('format') not in (FORMAT, LEGACY_FORMAT):
        raise ValueError('동일 시점의 Post 이미지 기록이 없습니다.')
    if len(_json_bytes(snapshot)) > MAX_METADATA_BYTES:
        raise ValueError('이미지 조건과 출처 기록이 256 KiB를 넘습니다.')
    if snapshot.get('capture_status') != 'SUCCEEDED' or snapshot.get('engineering_release') != 'NOT_RELEASED':
        raise ValueError('실패하거나 미확인인 캡처는 적용하지 않습니다.')
    if snapshot.get('data_match', {}).get('status') != 'EXACT':
        raise ValueError('표시 데이터와 저장 결과의 정확한 대응을 확인하지 못했습니다.')
    _sha(snapshot['data_match']['sha256'])
    scene = snapshot['scene']
    if scene.get('view_type') != 'RenderView' or not scene.get('view_name'):
        raise ValueError('정확한 3D retained view가 없습니다.')
    if not all(key in scene for key in ('field', 'clock', 'camera', 'warp', 'view', 'representation', 'legend', 'graph')):
        raise ValueError('이미지의 실제 표시 조건이 불완전합니다.')
    field = scene['field']
    if not all(key in field for key in ('name', 'association', 'component', 'unit', 'unit_status')):
        raise ValueError('필드 성분·위치·단위 기록이 없습니다.')
    if field['association'] not in ('POINTS', 'CELLS') or not isinstance(field['name'], str) or not field['name']:
        raise ValueError('실제 점/셀 필드를 선택하세요. 단색 그림은 물리 결과가 아닙니다.')
    if not isinstance(field['component'], dict) or field['component'].get('mode') not in ('SCALAR', 'COMPONENT', 'MAGNITUDE'):
        raise ValueError('실제 색상 성분 기록이 없습니다.')
    components = field.get('components')
    if type(components) is not int or components < 1:
        raise ValueError('실제 필드 성분 수가 없습니다.')
    component = field['component']
    if ((component['mode'] == 'SCALAR' and components != 1)
            or (component['mode'] == 'COMPONENT' and
                (type(component.get('index')) is not int or not 0 <= component['index'] < components))):
        raise ValueError('선택한 색상 성분과 실제 배열의 성분 수가 다릅니다.')
    if (field['unit_status'] not in ('DECLARED', 'UNKNOWN')
            or field['unit_status'] == 'UNKNOWN' and field['unit'] is not None
            or field['unit_status'] == 'DECLARED' and
                (not isinstance(field['unit'], str) or not field['unit'].strip())):
        raise ValueError('미제공 물리 단위를 추정하지 않습니다.')
    from .report_image_axis import validate_axis_snapshot
    validate_axis_snapshot(snapshot, strict=snapshot['format'] == FORMAT)
    if snapshot['format'] == FORMAT:
        audit = scene.get('block_coloring', {})
        if (audit.get('profile') != 'ParaView-SM-single-field-blocks/1'
                or audit.get('status') != 'SINGLE_GLOBAL_FIELD'
                or audit.get('policy') != 'ALL_CONFIGURED_SELECTORS_EQUIVALENT'):
            raise ValueError('블록별 색상 의미를 검증한 native 기록이 없습니다.')
    if not scene['camera'] or not isinstance(scene['warp'], list):
        raise ValueError('카메라 또는 변형 조건이 없습니다.')
    if scene['warp'] != warp_conditions(snapshot.get('lineage', [])):
        raise ValueError('표시 배율과 정확한 이전 처리 조건이 다릅니다.')


def completed_content(command):
    """Return the exact image payload from a broker-owned successful export only."""
    if (not isinstance(command, dict) or command.get('state') != 'SUCCEEDED'
            or command.get('operation') != 'post.export'
            or command.get('outcome', {}).get('state') != 'SUCCEEDED'):
        raise ValueError('정확한 Post 이미지 캡처가 완료되지 않았습니다. 이전 보고서는 유지됩니다.')
    args = command.get('arguments', {})
    if args.get('format') != 'png' or args.get('report_snapshot') is not True:
        raise ValueError('일반 PNG 내보내기는 결과 연결 증거가 아닙니다. 보고서 캡처를 사용하세요.')
    envelope = command['outcome'].get('result', {})
    if envelope.get('status') != 'COMPLETED' or any(envelope.get(key) != command.get(key)
            for key in ('command_id', 'document_id', 'session_id')):
        raise ValueError('다른 Post 요청의 응답입니다.')
    receipt = envelope.get('result', {})
    if receipt.get('analysis_saved') is not False:
        raise ValueError('이미지 출력과 분석 저장은 별개입니다.')
    snapshot = deepcopy(receipt.get('report_snapshot'))
    validate_snapshot(snapshot)
    if snapshot['format'] != FORMAT:
        raise ValueError('이전 캡처는 축·블록 검증 전 기록입니다. 기존 보고서는 유지하고 새 캡처를 요청하세요.')
    origin = snapshot['origin']
    if any(origin.get(key) != command.get(key) for key in ('document_id', 'session_id')) or (
            origin.get('object_ref') != args.get('object_ref') or origin.get('revision') != receipt.get('revision')):
        raise ValueError('선택한 원문서/결과와 캡처가 다릅니다.')
    project, obj, record = verify_origin(origin)
    if (snapshot.get('sources') != source_records(project, obj, record)
            or snapshot.get('result_files') != record['result_files']
            or snapshot.get('lineage') != retained_analyses(project, obj, record)
            or snapshot['scene']['graph'] != record['graph']):
        raise ValueError('캡처 기록과 저장 결과의 출처/입력 그래프가 다릅니다.')
    from .report_image_axis import saved_axis_context
    if snapshot['scene']['axis_context'] != saved_axis_context(project, obj, record):
        raise ValueError('축 선언과 정확한 저장 결과 개정이 다릅니다.')
    if snapshot.get('recipe') != record['recipe']:
        raise ValueError('캡처와 저장 결과의 처리 조건이 다릅니다.')
    pin = snapshot['png']
    root = (Path(project['project_root']) / 'exports').resolve()
    path = Path(pin['path']).resolve()
    if (not path.is_relative_to(root) or path.suffix.lower() != '.png'
            or Path(receipt.get('file', '')).resolve() != path or receipt.get('sha256') != pin['sha256']):
        raise ValueError('현재 owner가 내보낸 정확한 PNG가 아닙니다.')
    data = read_pinned(pin, MAX_PNG_BYTES)
    dimensions = png_dimensions(data)
    if list(dimensions) != snapshot.get('pixel_size'):
        raise ValueError('PNG와 기록한 크기가 다릅니다.')
    if snapshot['scene']['view_name'] != record['view_name']:
        raise ValueError('저장 결과와 캡처한 view가 다릅니다.')
    verify_origin(origin)  # File changes while reading cannot publish a new binding.
    reference = {'kind': 'post_image', 'command_id': check_id(command['command_id']),
                 'snapshot_sha256': canonical_hash(snapshot)}
    content = {'kind': 'post_image', 'snapshot': snapshot,
               'png_base64': base64.b64encode(data).decode('ascii')}
    validate_content(content, reference)
    return reference, content


def validate_content(content, reference=None):
    """Pure retained read: no filesystem, native process or provider is required."""
    if not isinstance(content, dict) or set(content) != {'kind', 'snapshot', 'png_base64'} or content['kind'] != 'post_image':
        raise ValueError('보존된 이미지 자료 형식이 잘못되었습니다.')
    snapshot = content['snapshot']
    validate_snapshot(snapshot)
    if reference is not None:
        issue = reference_error(reference)
        if issue or canonical_hash(snapshot) != reference['snapshot_sha256']:
            raise ValueError(issue or '보존한 이미지 조건이 참조와 다릅니다.')
    encoded = content['png_base64']
    if not isinstance(encoded, str) or len(encoded) > (MAX_PNG_BYTES + 2) // 3 * 4:
        raise ValueError('보존 이미지의 크기가 지원 범위를 벗어났습니다.')
    try:
        data = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as error:
        raise ValueError('보존 이미지 인코딩이 손상되었습니다.') from error
    if (len(data) != snapshot['png']['bytes'] or hashlib.sha256(data).hexdigest() != snapshot['png']['sha256']
            or list(png_dimensions(data)) != snapshot['pixel_size']):
        raise ValueError('보존 이미지의 해시 또는 크기가 다릅니다.')
    return data


def _status_text(value):
    return {'UNKNOWN': '미확인', 'UNQUALIFIED': '미확인', 'SUCCEEDED': '완료', 'COMPLETED': '완료',
            'FAILED': '실패', 'FAIL': '실패', 'PASS': '통과', 'PASSED': '통과',
            'CANCELLED': '취소됨', 'INTERRUPTED': '중단됨',
            'NOT_EVALUATED': '미평가', 'NOT_RELEASED': '승인하지 않음'}.get(value, str(value))


def caption(snapshot):
    """Main-view meaning; raw references are available separately as diagnostics."""
    scene = snapshot['scene']; field = scene['field']; clock = scene['clock']
    comp = field['component']
    component = {'SCALAR': '스칼라', 'MAGNITUDE': '벡터 크기'}.get(comp['mode'],
        '성분 ' + str(comp.get('name') or comp.get('index')))
    unit = field['unit'] if field['unit_status'] == 'DECLARED' else '단위 미확인'
    location = {'POINTS': '절점/점', 'CELLS': '요소/셀'}[field['association']]
    from .report_image_axis import caption as axis_caption
    time = axis_caption(snapshot)
    legacy = ('\n이전 캡처: 블록별 색상 검증 미기록. 다시 캡처하기 전 단일 필드 보증 없음.'
              if snapshot.get('format') == LEGACY_FORMAT else '')
    warp = ('변형 표시 없음' if not scene['warp'] else '변형 표시: ' + ', '.join(
        str(w['type']) + ' ×' + str(w.get('scale', '미확인')) for w in scene['warp']))
    execution = snapshot.get('result_status', {}).get('execution_status', 'UNKNOWN')
    qualification = snapshot.get('result_status', {}).get('qualification', 'UNKNOWN')
    return (f"{field['name']} / {component} / {location} [{unit}]\n{time} / {warp}\n"
            f"계산 상태: {_status_text(execution)} · 수치/물리 판정: {_status_text(qualification)} · 공학 승인 없음. "
            '표시 배율은 물리값이 아닙니다.' + legacy)


def image_options(section):
    value = section.get('image', {'show': True, 'width_percent': 100})
    if (not isinstance(value, dict) or set(value) != {'show', 'width_percent'}
            or type(value['show']) is not bool or type(value['width_percent']) is not int
            or not 10 <= value['width_percent'] <= 100):
        raise ValueError('이미지 표시 여부와 너비 10–100%를 확인하세요.')
    return deepcopy(value)


def apply_binding(draft, binding, content, *, section_id=None, expected_section=None, title='3D 결과 이미지'):
    """One explicit edit; the caller's existing Undo owner retains the old draft."""
    validate_content(content, binding['reference'])
    frozen = {'reference': binding['reference'], 'content': content}
    if binding.get('sha256') != canonical_hash(frozen) or binding.get('id') != 'A' + binding['sha256']:
        raise ValueError('선택한 보고서 이미지 자산이 일치하지 않습니다.')
    updated = deepcopy(draft)
    if section_id is None:
        import uuid
        if len(updated['sections']) >= 100:
            raise ValueError('보고서 섹션은 100개까지 추가할 수 있습니다.')
        updated['sections'].append({'id': 'E' + uuid.uuid4().hex, 'title': title, 'text': '',
            'include': True, 'table': False, 'curve': False, 'asset': deepcopy(binding),
            'image': {'show': True, 'width_percent': 100}})
    else:
        matches = [row for row in updated['sections'] if row['id'] == section_id]
        if len(matches) != 1 or expected_section is None or matches[0] != expected_section:
            raise ValueError('선택 섹션이 바뀌었습니다. 현재 이미지·본문·판단은 유지됩니다.')
        matches[0]['asset'] = deepcopy(binding)
        matches[0].setdefault('image', {'show': True, 'width_percent': 100})
    return updated


def merge_read_assets(previous, received):
    """An unavailable reread may flag, but never erase a last verified preview."""
    result = deepcopy(previous)
    for asset in received:
        identifier = asset.get('id')
        old = result.get(identifier)
        if 'content' not in asset and old and 'content' in old:
            result[identifier] = {**old, 'source_status': 'SNAPSHOT_UNAVAILABLE',
                'message': asset.get('message', ''), 'retained_preview_only': True}
        else:
            result[identifier] = deepcopy(asset)
    return result


def read_degraded_revision(folder, manifest, identifier, revision):
    """Read a published report body if ONLY its known image copies are damaged.

    Not used for an unpublished save. Every non-image byte, the publication
    manifest and the body must verify. Missing pixels stay unavailable; no
    hash is relaxed, repaired or relabelled successful.
    """
    from .evaluation import file_hash
    from .storage import load_json
    folder = Path(folder).resolve()
    if (not manifest or manifest.get('revision') != revision
            or file_hash(folder / 'revision.json') != manifest.get('revision_sha256')):
        raise ValueError('보고서 개정 목록을 검증하지 못했습니다.')
    retained = load_json(folder / 'revision.json')
    files = retained['files']
    if retained.get('id') != identifier or retained.get('revision') != revision:
        raise ValueError('다른 보고서의 개정 목록입니다.')
    body = [row for row in files if row['path'] == 'document.json']
    if len(body) != 1 or file_hash(folder / 'document.json') != body[0]['sha256']:
        raise ValueError('보고서 본문을 검증하지 못했습니다.')
    document = load_json(folder / 'document.json')
    if document.get('id') != identifier or document.get('kind') != 'report':
        raise ValueError('다른 보고서 본문입니다.')
    images = set()
    for draft in [document['draft'], *document.get('_undo', []), *document.get('_redo', [])]:
        for section in draft.get('sections', []):
            binding = section.get('asset') or {}
            reference = binding.get('reference') or {}
            if reference.get('kind') == 'post_image':
                if reference_error(reference) or binding.get('id') != 'A' + _sha(binding.get('sha256')):
                    raise ValueError('이미지 자산 참조를 검증하지 못했습니다.')
                images.add('assets/' + binding['id'] + '.json')
    seen, issues = set(), []
    for row in files:
        relative = row['path']; path = (folder / relative).resolve()
        if relative in seen or not path.is_relative_to(folder):
            raise ValueError('보고서 개정의 파일 목록이 잘못되었습니다.')
        seen.add(relative)
        if not path.is_file() or file_hash(path) != row['sha256']:
            if relative not in images:
                raise ValueError('보고서의 본문 또는 다른 원자료가 손상되었습니다.')
            issues.append({'asset_id': Path(relative).stem, 'state': 'SNAPSHOT_UNAVAILABLE',
                           'message': '저장된 이미지 보관 사본이 없거나 해시가 다릅니다.'})
    if not issues:
        raise ValueError('보고서 검증 오류를 이미지 누락으로 한정하지 못했습니다.')
    return document, issues
