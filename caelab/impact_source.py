"""Bounded INP project capture. All INCLUDE paths use the selected job directory.

Original ASCII bytes (including CRLF) live in source.bundle, not an external store.
Only declared files are read; execution resolves solely from this retained bundle.
"""
from copy import deepcopy
from pathlib import Path, PureWindowsPath
import hashlib
import json
import posixpath
import re
import os
from types import SimpleNamespace

MAX_FILES = 128
MAX_DEPTH = 24
MAX_OCCURRENCES = 1024
MAX_BYTES = 6 * 1024**2
# Existing Simulation draft limit is 8 MiB. Leave space for conditions and edits.
MAX_SOURCE_JSON = 6 * 1024**2


class SourceError(ValueError):
    def __init__(self, message, file=None, line=None, chain=()):
        self.file, self.line, self.column = file, line, 0
        self.path = ['settings', 'source', 'text']
        self.chain = list(chain)
        prefix = f'{file}:{line}: ' if file and line else (f'{file}: ' if file else '')
        super().__init__(prefix + message)


class ImportCancelled(Exception):
    pass


def digest(payload):
    return hashlib.sha256(payload).hexdigest()


def relative_name(value):
    if not isinstance(value, str) or not value or '\x00' in value:
        raise SourceError('포함 파일 이름을 확인하세요')
    value = value.replace('\\', '/')
    win = PureWindowsPath(value)
    if win.drive or value.startswith('/') or ':' in value:
        raise SourceError('포함 파일은 선택한 작업 폴더 안의 상대 경로여야 합니다')
    name = posixpath.normpath(value)
    if name in ('.', '..') or name.startswith('../') or len(name) > 256:
        raise SourceError('작업 폴더를 벗어나거나 너무 긴 포함 경로입니다')
    # Prevent Windows aliases, alternate streams and device names in retained paths.
    for part in name.split('/'):
        if part.endswith((' ', '.')) or re.fullmatch(r'(?i)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?', part):
            raise SourceError('일반 상대 파일 이름을 사용하세요')
    return name


def include_name(line):
    """Return INPUT preserving quoted spaces/case; keyword names are insensitive."""
    if not re.match(r'^\s*\*INCLUDE(?:\s*,|\s*$)', line, re.I):
        return None
    match = re.fullmatch(r'\s*\*INCLUDE\s*,\s*INPUT\s*=\s*(.*?)\s*', line, re.I)
    if not match:
        raise SourceError('INCLUDE는 INPUT 상대 파일 하나를 지정해야 합니다')
    raw = match[1]
    if raw.startswith('"'):
        if len(raw) < 2 or not raw.endswith('"') or '"' in raw[1:-1]:
            raise SourceError('포함 파일 이름의 따옴표를 확인하세요')
        raw = raw[1:-1]
    elif '"' in raw or ',' in raw:
        raise SourceError('포함 파일 이름이나 중복 INPUT 옵션을 확인하세요')
    else:
        raw = ''.join(raw.split())
    return relative_name(raw)


def flatten(entry, read, cancel=lambda: False, *, dialect="INP"):
    """read(logical_name)->ASCII bytes, never resolves from the including parent."""
    files, order, spans, lines = {}, [], [], []
    expanded_bytes = 0
    def visit(name, stack=(), parent=None, parent_line=None):
        nonlocal expanded_bytes
        if cancel(): raise ImportCancelled()
        if name in stack:
            raise SourceError('INCLUDE 순환: ' + ' → '.join((*stack, name)), parent, parent_line, stack)
        if len(stack) >= MAX_DEPTH or len(order) >= MAX_OCCURRENCES:
            raise SourceError('포함 깊이 또는 펼치기 횟수 한도를 초과했습니다', parent, parent_line, stack)
        if name not in files:
            if any(other.casefold()==name.casefold() for other in files):
                raise SourceError('대소문자만 다른 파일 경로는 Windows에서 구별할 수 없습니다',parent,parent_line)
            if len(files) >= MAX_FILES: raise SourceError('포함 파일은 최대 128개입니다', parent, parent_line)
            try:
                payload = read(name)
                if len(payload) > MAX_BYTES or sum(len(f['text'].encode('ascii')) for f in files.values()) + len(payload) > MAX_BYTES:
                    raise SourceError('원 입력 묶음은 6 MiB 이하여야 합니다')
                text = payload.decode('ascii')
                if '\x00' in text: raise SourceError('NUL 문자가 포함된 입력입니다')
            except (OSError, UnicodeError, ValueError) as error:
                raise SourceError(str(error), parent or name, parent_line, stack) from error
            files[name] = {'path': name, 'text': text, 'sha256': digest(payload)}
        occurrence = len(order)
        order.append({'file': name, 'parent': parent, 'line': parent_line})
        physical = files[name]['text'].splitlines()
        i = 0
        while i < len(physical):
            if cancel(): raise ImportCancelled()
            start = i + 1
            logical = physical[i]; i += 1
            # Abaqus keyword continuation, including INCLUDE split after a comma.
            if dialect == 'INP' and logical.lstrip().startswith('*') and not logical.lstrip().startswith('**'):
                while logical.rstrip().endswith(',') and i < len(physical):
                    following = physical[i].strip()
                    if following.startswith('*'): break
                    logical += following; i += 1
            try:
                if dialect == 'RAD':
                    from .impact_rad_source import include_name as rad_include
                    child = rad_include(logical)
                else:
                    child = include_name(logical)
            except SourceError as error: raise SourceError(str(error), name, start, stack) from error
            if child is not None:
                visit(child, (*stack, name), name, start)
                continue
            # Flatten normalizes only physical endings; originals remain byte exact.
            expanded_bytes += len(logical.encode('ascii')) + 1
            if expanded_bytes > MAX_BYTES: raise SourceError('펼친 입력은 6 MiB를 초과할 수 없습니다', name, start)
            output_line = len(lines) + 1
            lines.append(logical)
            if spans and spans[-1]['file'] == name and spans[-1]['occurrence'] == occurrence and spans[-1]['source_line'] + spans[-1]['count'] == start and i == start:
                spans[-1]['count'] += 1
            else:
                spans.append({'flat_line': output_line, 'count': 1, 'file': name, 'source_line': start, 'occurrence': occurrence})
    visit(relative_name(entry))
    text = '\n'.join(lines) + '\n'
    return text, list(files.values()), order, spans


def _bounded(source):
    if len(json.dumps(source, ensure_ascii=False, allow_nan=False).encode('utf-8')) > MAX_SOURCE_JSON:
        raise SourceError('원파일과 펼친 입력을 함께 저장하는 한도(6 MiB)를 초과했습니다')


def capture(entry, root, *, cancel=lambda: False, engine=None, units=None):
    if Path(entry).suffix.lower() == '.rad' or engine is not None:
        from .impact_rad_source import capture as capture_rad
        return capture_rad(entry, engine, root, cancel=cancel, units=units)
    if not str(root).strip() or not str(entry).strip():
        raise SourceError('주 입력 파일과 제출 작업 폴더를 명시적으로 선택하세요')
    root = Path(root).absolute()
    if not root.is_dir() or root.is_symlink(): raise SourceError('입력 제출 작업 폴더를 선택하세요')
    entry = Path(entry).absolute()
    try: name = entry.relative_to(root).as_posix()
    except ValueError as error: raise SourceError('주 입력 파일은 선택한 작업 폴더 안에 있어야 합니다') from error
    from .read_paths import verified_read_paths
    from .dynamic_native_stream import _stamp, _view_stamp
    try:
        with verified_read_paths(SimpleNamespace(store=root)) as guard:
            def read(relative):
                target = guard.path(root / relative, directory=False)
                before = target.lstat()
                flags = os.O_RDONLY | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NOFOLLOW', 0)
                with os.fdopen(os.open(target, flags), 'rb') as stream:
                    opened = os.fstat(stream.fileno())
                    if _stamp(opened) != _stamp(before):
                        raise SourceError('입력 파일이 읽기 전에 변경되었습니다')
                    payload = stream.read(MAX_BYTES + 1)
                    after = os.fstat(stream.fileno())
                    if _stamp(after) != _stamp(before) or _view_stamp(after) != _view_stamp(opened):
                        raise SourceError('입력 파일이 읽는 동안 변경되었습니다')
                if _view_stamp(target.lstat()) != _view_stamp(before):
                    raise SourceError('입력 파일 경로가 읽는 동안 변경되었습니다')
                guard.recheck()
                return payload
            text, files, order, spans = flatten(name, read, cancel)
    except SourceError:
        raise
    except ValueError as error:
        raise SourceError('입력 경로나 파일이 변경되었거나 링크입니다: '+str(error),name) from error
    source = {'title': entry.name, 'format': 'INP', 'units': 'Mg/mm/s', 'text': text,
        'provenance': {'filename': name, 'units_declared_by_user': True},
        'bundle': {'version': 1, 'root_label': root.name, 'entry': name, 'files': files,
                   'order': order, 'line_map': spans, 'flattened_sha256': digest(text.encode('ascii'))}}
    _bounded(source)
    return source


def resolve(source):
    if not isinstance(source, dict): raise SourceError('원 입력을 확인하세요')
    if source.get('format') == 'RAD':
        from .impact_rad_source import resolve as resolve_rad
        return resolve_rad(source)
    if 'bundle' not in source:
        if source.get('edits'): raise SourceError('편집에는 보존 원 입력 묶음이 필요합니다')
        return source.get('text'), []
    _bounded(source)
    bundle = source['bundle']
    if not isinstance(bundle, dict) or type(bundle.get('version')) is not int or bundle['version'] != 1: raise SourceError('입력 묶음 버전을 확인하세요')
    files = bundle.get('files')
    if not isinstance(files, list) or not 1 <= len(files) <= MAX_FILES: raise SourceError('보존 원파일 목록을 확인하세요')
    table = {}
    for row in files:
        name = relative_name(row['path'])
        if name != row['path'] or name in table or not isinstance(row.get('text'), str):
            raise SourceError('보존 원파일 경로가 중복되거나 잘못되었습니다')
        try: payload = row['text'].encode('ascii')
        except UnicodeError as error: raise SourceError('원 INP는 ASCII여야 합니다', name) from error
        if digest(payload) != row.get('sha256'): raise SourceError('보존 원파일이 변경되었습니다', name)
        table[name] = payload
    def read(name):
        if name not in table: raise SourceError('보존 묶음에 포함 파일이 없습니다: ' + name)
        return table[name]
    text, used, order, spans = flatten(bundle['entry'], read)
    if {f['path'] for f in used} != set(table): raise SourceError('참조되지 않은 파일이 보존 묶음에 있습니다')
    if (not source.get('edits') and text != source.get('text')) or digest(text.encode('ascii')) != bundle.get('flattened_sha256') or order != bundle.get('order') or spans != bundle.get('line_map'):
        raise SourceError('펼친 입력 또는 원행 대응이 보존 원파일과 다릅니다')
    if source.get('edits'):
        from .impact_input_edits import edited_files
        effective = edited_files(source)
        text, used, _, spans = flatten(bundle['entry'], effective.__getitem__)
        if {f['path'] for f in used} != set(effective) or text != source.get('text'):
            raise SourceError('수정 입력 또는 include 대응이 편집 hunk와 다릅니다')
    return text, spans


def locate(spans, line):
    for span in spans:
        if span['flat_line'] <= line < span['flat_line'] + span['count']:
            return span['file'], span['source_line'] + line - span['flat_line']
    return None, line


def retain(source, output):
    """Only adapter-owned empty attempt subdirectory; no external source reread."""
    if source.get('format') == 'RAD':
        from .impact_rad_source import retain as retain_rad
        return retain_rad(source, output)
    text, _ = resolve(source)
    output = Path(output); output.mkdir()
    (output / 'flattened.inp').write_bytes(text.encode('ascii'))
    if 'bundle' in source:
        originals = output / 'files'; originals.mkdir()
        for row in source['bundle']['files']:
            target = originals / relative_name(row['path'])
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(row['text'].encode('ascii'))
        (output / 'manifest.json').write_text(json.dumps(source['bundle'], ensure_ascii=False, indent=2), encoding='utf-8')
    if source.get('edits'):
        (output / 'edits.json').write_text(json.dumps(source['edits'], ensure_ascii=False, indent=2), encoding='utf-8')
    return {'format': 'INP', 'units': source['units'], 'flattened_sha256': digest(text.encode('ascii'))}


def export_effective(settings, path):
    """Write a new standalone canonical INP; never overwrite an imported original."""
    if settings.get('source', {}).get('format') == 'RAD':
        from .impact_native import export_direct
        return export_direct(settings, path)
    from .impact_model import render
    text, _ = render(settings)
    path = Path(path)
    with path.open('xb') as stream:
        stream.write(text.encode('ascii'))
    return path
