"""Native Starter/Engine bundle capture with the pinned #include syntax.

All include names are submission-root relative, as executed with that root as
cwd. v2 explicitly carries TWO entry graphs. Inspection flattening is not the
exporter: native export writes the original file tree plus explicit edit hunks.
"""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import json
import os
import re

from .impact_source import (SourceError, ImportCancelled, relative_name, flatten, digest,
                            _bounded, MAX_BYTES, MAX_FILES)


def include_name(line):
    if not re.match(r'^\s*#include(?:\s|$)', line, re.I):
        # Reject native include-like directives instead of treating them as comments.
        if re.match(r'^\s*#include', line, re.I):
            raise SourceError('native include는 #include 상대파일 형식이어야 합니다')
        return None
    match = re.fullmatch(r'#include[ \t]+([^\r\n]+)', line)
    if not match:
        raise SourceError('pinned native 문법은 열 1의 소문자 #include 상대파일입니다')
    raw = match[1].rstrip(' \t')
    if not raw or any(c in raw for c in ('"', "'", '#', '*')):
        raise SourceError('native #include에는 따옴표·옵션 없는 원 상대 파일명을 지정하세요')
    # The first admitted syntax does not guess parent-relative path semantics.
    return relative_name(raw)


def _graphs(bundle, files, cancel=lambda: False):
    graphs = {}
    used = {}
    for role in ('starter', 'engine'):
        entry = relative_name(bundle[role])
        def read(name):
            if name not in files: raise SourceError('보존된 native include가 없습니다: ' + name)
            return files[name]
        text, rows, order, spans = flatten(entry, read, cancel, dialect='RAD')
        used.update({r['path']:r for r in rows})
        graphs[role] = {'entry':entry,'text':text,'order':order,'line_map':spans,
                        'flattened_sha256':digest(text.encode('ascii'))}
    if set(used) != set(files): raise SourceError('참조되지 않은 native 원파일이 있습니다')
    return graphs


def refresh(source, files):
    graphs = _graphs(source['bundle'], files)
    source['text'] = graphs['starter']['text']
    source['native_effective'] = {role:{k:v for k,v in graph.items() if k != 'text'}
                                 for role,graph in graphs.items()}


def capture(entry, engine, root, *, cancel=lambda: False, units=None):
    if engine is None: raise SourceError('native 입력은 Starter와 Engine 파일을 모두 선택하세요')
    root = Path(root).absolute()
    if not root.is_dir() or root.is_symlink(): raise SourceError('native 제출 작업 폴더를 선택하세요')
    entries = {}
    for role, value in (('starter', entry), ('engine', engine)):
        path = Path(value).absolute()
        try: name = relative_name(path.relative_to(root).as_posix())
        except ValueError as error: raise SourceError('Starter/Engine는 제출 폴더 안의 파일이어야 합니다') from error
        entries[role] = name
    if entries['starter'] == entries['engine']: raise SourceError('Starter와 Engine는 서로 다른 파일입니다')
    from .read_paths import verified_read_paths
    # Use the C2/R2 handle/path identity split. This is byte reading, NOT its FRD parser.
    from .dynamic_native_stream import _stamp, _view_stamp
    files = {}
    try:
        with verified_read_paths(SimpleNamespace(store=root)) as guard:
            def read(name):
                if cancel(): raise ImportCancelled()
                if name in files: return files[name]
                target = guard.path(root / name, directory=False)
                before = target.lstat()
                flags = os.O_RDONLY | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NOFOLLOW', 0)
                with os.fdopen(os.open(target, flags), 'rb') as stream:
                    opened = os.fstat(stream.fileno())
                    if _stamp(opened) != _stamp(before): raise SourceError('native 원파일이 열기 전에 변경되었습니다', name)
                    payload = stream.read(MAX_BYTES + 1)
                    after = os.fstat(stream.fileno())
                    if _stamp(after) != _stamp(before) or _view_stamp(after) != _view_stamp(opened):
                        raise SourceError('native 원파일이 읽는 동안 변경되었습니다', name)
                if _view_stamp(target.lstat()) != _view_stamp(before): raise SourceError('native 원파일 경로가 변경되었습니다', name)
                guard.recheck()
                if len(payload) > MAX_BYTES or sum(map(len,files.values())) + len(payload) > MAX_BYTES:
                    raise SourceError('native 입력 묶음은 6 MiB 이하여야 합니다')
                if len(files) >= MAX_FILES: raise SourceError('native 원파일은 최대 128개입니다')
                if any(n.casefold() == name.casefold() for n in files): raise SourceError('Windows에서 충돌하는 파일 이름입니다')
                payload.decode('ascii')
                files[name] = payload
                return payload
            for role in ('starter','engine'):
                flatten(entries[role], read, cancel, dialect='RAD')
    except (SourceError, ImportCancelled): raise
    except (ValueError,OSError,UnicodeError) as error:
        raise SourceError('native 원파일을 안전하게 읽지 못했습니다: ' + str(error)) from error
    bundle = {'version':2,'dialect':'RAD','root_label':root.name, **entries,
              'files':[{'path':n,'text':raw.decode('ascii'),'sha256':digest(raw)} for n,raw in files.items()]}
    graphs = _graphs(bundle, files, cancel)
    bundle['graphs'] = {role:{k:v for k,v in graph.items() if k != 'text'} for role,graph in graphs.items()}
    source = {'title':Path(entry).name,'format':'RAD','units':units if units is not None else 'UNKNOWN',
              'text':graphs['starter']['text'], 'bundle':bundle,
              'provenance':{'filename':entries['starter'],'units_declared_by_user':units is not None},
              'native_effective':deepcopy(bundle['graphs']), 'edits':[]}
    _bounded(source)
    resolve(source)
    return source


def inspect_graphs(source):
    from .impact_input_edits import original_files, edited_files
    if not isinstance(source,dict) or source.get('format')!='RAD': raise SourceError('native RAD 원문을 선택하세요')
    _bounded(source)
    b = source.get('bundle')
    if not isinstance(b,dict) or type(b.get('version')) is not int or b['version']!=2 or b.get('dialect')!='RAD':
        raise SourceError('native 입력 묶음은 명시 v2 RAD 형식이어야 합니다')
    originals = original_files(source)
    if not 2 <= len(originals) <= MAX_FILES: raise SourceError('native 원파일 목록을 확인하세요')
    for name in (b.get('starter'),b.get('engine')):
        if name not in originals: raise SourceError('보존 Starter/Engine가 없습니다')
    raw_graphs = _graphs(b, originals)
    metadata = {role:{k:v for k,v in graph.items() if k!='text'} for role,graph in raw_graphs.items()}
    if metadata != b.get('graphs'): raise SourceError('native 원 include graph/행/occurrence가 변경되었습니다')
    effective = _graphs(b, edited_files(source))
    if source.get('text') != effective['starter']['text'] or source.get('native_effective') != {
            role:{k:v for k,v in graph.items() if k!='text'} for role,graph in effective.items()}:
        raise SourceError('native 편집 hunk와 effective graph가 다릅니다')
    return effective


def resolve(source):
    graphs = inspect_graphs(source)
    return graphs['starter']['text'], graphs['starter']['line_map']


def retain(source, output):
    from .impact_input_edits import original_files, edited_files
    inspect_graphs(source)
    output=Path(output);output.mkdir()
    for folder,files in [('files',original_files(source)),('effective_files',edited_files(source))]:
        for name,raw in files.items():
            path=output/folder/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
    (output/'manifest.json').write_text(json.dumps(source,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    return {'format':'RAD','units':source['units'],'mode':'NATIVE_DIRECT','starter':source['bundle']['starter'],
            'engine':source['bundle']['engine'],'original_bytes_unchanged':True}


def export_tree(source, output):
    """No flatten, serializer or converter. Only exact per-file edited bytes."""
    from .impact_input_edits import edited_files
    inspect_graphs(source)
    output=Path(output)
    output.mkdir()  # Fresh folder only; neither user originals nor attempts can be overwritten.
    receipts={}
    for name,raw in edited_files(source).items():
        path=output/name;path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('xb') as stream:stream.write(raw)
        receipts[name]={'sha256':digest(raw),'bytes':len(raw)}
    return receipts
