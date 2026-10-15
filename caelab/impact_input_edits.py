"""Optimistic, byte-range edits over an immutable captured input bundle.

The original files are never rewritten. Ranges refer to ORIGINAL ASCII bytes;
GUI previews can show both versions. Replacing the complete hunk list is one
explicit Simulation update and is undoable by the existing document owner.
"""
from copy import deepcopy
from .impact_source import SourceError, digest, relative_name, MAX_BYTES, _bounded
from .storage import canonical_hash


def original_files(source):
    bundle = source.get('bundle', {})
    files = bundle.get('files')
    if not isinstance(files, list) or not files:
        raise SourceError('먼저 원 입력 묶음을 가져오세요. 외부 파일을 다시 읽지 않습니다')
    result = {}
    for row in files:
        if not isinstance(row, dict): raise SourceError('보존 원파일 항목을 확인하세요')
        name = relative_name(row.get('path'))
        if name != row['path'] or name.casefold() in {n.casefold() for n in result}:
            raise SourceError('보존 원파일 이름이 중복되거나 정규 상대 경로가 아닙니다', name)
        try:
            raw = row['text'].encode('ascii')
        except (KeyError, AttributeError, UnicodeError) as error:
            raise SourceError('원 입력은 보존된 ASCII bytes여야 합니다', name) from error
        if b'\0' in raw or digest(raw) != row.get('sha256'):
            raise SourceError('보존 원파일이 변조되었습니다', name)
        result[name] = raw
    return result


def edited_files(source):
    files = original_files(source)
    edits = source.get('edits', [])
    if not isinstance(edits, list) or len(edits) > 4096:
        raise SourceError('명시 편집 hunk 목록은 4096개 이하여야 합니다')
    grouped = {}
    for h in edits:
        if not isinstance(h, dict) or set(h) != {'file', 'start', 'end', 'before', 'after', 'base_sha256', 'reason'}:
            raise SourceError('편집 범위·원문·수정문·사유를 모두 지정하세요')
        name = h['file']
        if name not in files or h['base_sha256'] != digest(files[name]):
            raise SourceError('편집 hunk의 원파일이 다릅니다', name)
        start, end = h['start'], h['end']
        if type(start) is not int or type(end) is not int or not 0 <= start <= end <= len(files[name]):
            raise SourceError('원문 byte 범위가 잘못되었습니다', name)
        if not isinstance(h['reason'], str) or not h['reason'].strip() or len(h['reason']) > 512:
            raise SourceError('편집 사유를 입력하세요', name)
        try:
            before, after = h['before'].encode('ascii'), h['after'].encode('ascii')
        except (UnicodeError, AttributeError) as error:
            raise SourceError('편집 내용은 ASCII 입력 문법이어야 합니다', name) from error
        if b'\0' in after or len(after) > MAX_BYTES or files[name][start:end] != before:
            raise SourceError('선택한 원문 범위가 현재 보존 원문과 다릅니다', name)
        grouped.setdefault(name, []).append(h)
    for name, hunks in grouped.items():
        hunks.sort(key=lambda h: (h['start'], h['end']))
        for left, right in zip(hunks, hunks[1:]):
            if right['start'] < left['end'] or right['start'] == left['start']:
                raise SourceError('겹치거나 같은 위치의 편집 hunk는 허용하지 않습니다', name)
        raw = files[name]
        for h in reversed(hunks):
            raw = raw[:h['start']] + h['after'].encode('ascii') + raw[h['end']:]
        files[name] = raw
    if sum(map(len, files.values())) > MAX_BYTES:
        raise SourceError('편집된 입력 묶음은 6 MiB 이하여야 합니다')
    return files


def apply_hunks(source, hunks, *, expected_source_sha256):
    """Replace the explicit edit list, never accept a stale editor snapshot."""
    from .impact_source import resolve, flatten
    resolve(source)
    if canonical_hash(source) != expected_source_sha256:
        raise SourceError('입력이 바뀌었습니다. 현재 원문을 다시 확인한 후 적용하세요')
    value = deepcopy(source)
    value['edits'] = deepcopy(hunks)
    files = edited_files(value)
    if value.get('format') == 'RAD':
        from .impact_rad_source import refresh
        refresh(value, files)
    else:
        def read(name):
            if name not in files: raise SourceError('보존 묶음에 포함 파일이 없습니다: '+name, name)
            return files[name]
        text, _, _, _ = flatten(value['bundle']['entry'], read)
        value['text'] = text
    _bounded(value)
    resolve(value)
    return value


def replace_range(source, file, start, end, after, *, reason, expected_source_sha256):
    """Original range. Re-editing the SAME range replaces that hunk explicitly."""
    files = original_files(source)
    if file not in files:
        raise SourceError('보존 원파일을 선택하세요', file)
    if type(start) is not int or type(end) is not int or not 0 <= start <= end <= len(files[file]):
        raise SourceError('원문 byte 범위를 확인하세요', file)
    h = {'file': file, 'start': start, 'end': end, 'before': files[file][start:end].decode('ascii'),
         'after': after, 'base_sha256': digest(files[file]), 'reason': reason}
    hunks = [deepcopy(e) for e in source.get('edits', [])
             if (e['file'], e['start'], e['end']) != (file, start, end)]
    hunks.append(h)
    return apply_hunks(source, hunks, expected_source_sha256=expected_source_sha256)


def original_offset(source, file, offset):
    """Map an effective byte boundary back to the base, or explicitly refuse."""
    files = edited_files(source)
    if file not in files or type(offset) is not int or not 0 <= offset <= len(files[file]):
        raise SourceError('현재 원문 byte 경계를 확인하세요', file)
    delta = 0
    for h in sorted((h for h in source.get('edits', []) if h['file'] == file), key=lambda h: h['start']):
        start, stop = h['start'] + delta, h['start'] + delta + len(h['after'])
        if offset < start:
            break
        if offset <= stop:
            if len(h['after']) == h['end'] - h['start']:
                return h['start'] + offset - start
            if offset == start: return h['start']
            if offset == stop: return h['end']
            raise SourceError('길이가 바뀐 수정 범위 안입니다. 원문 hunk 전체를 편집하세요', file)
        delta += len(h['after']) - (h['end'] - h['start'])
    return offset - delta


def view(source, file):
    from .impact_source import resolve
    resolve(source)
    originals, effective = original_files(source), edited_files(source)
    if file not in originals:
        raise SourceError('보존 원파일을 선택하세요', file)
    def rows(raw):
        offset = 0
        result = []
        for i, line in enumerate(raw.splitlines(keepends=True), 1):
            result.append({'line': i, 'start': offset, 'end': offset + len(line), 'text': line.decode('ascii')})
            offset += len(line)
        return result
    return {'file': file, 'original': rows(originals[file]), 'effective': rows(effective[file]),
            'original_sha256': digest(originals[file]), 'effective_sha256': digest(effective[file]),
            'source_sha256': canonical_hash(source),
            'hunks': [deepcopy(h) for h in source.get('edits', []) if h['file'] == file]}
