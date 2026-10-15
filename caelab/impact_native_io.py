"""Pinned ASCII payload transport. Reuses C2's Windows-safe identity guards.

No FRD grammar is called: impact_results continues to own the ANIM→VTK grammar.
"""
import hashlib
import os
from pathlib import Path
from .dynamic_native_stream import _stamp, _view_stamp, _path_stat, _open_native
from .execution_control import check_cancelled


def read_bytes(path, *, expected=None, maximum=256*1024*1024):
    path=Path(path).absolute();before=_path_stat(path)
    if not 0<before.st_size<=maximum:raise ValueError('Native payload exceeds the declared single-file bound')
    stamp=_stamp(before);view=_view_stamp(before)
    with _open_native(path) as stream:
        handle=_view_stamp(os.fstat(stream.fileno()))
        if _stamp(os.fstat(stream.fileno()))!=stamp:raise ValueError('Native path/handle identity changed before read')
        chunks=[];digest=hashlib.sha256();count=0
        while True:
            check_cancelled();chunk=stream.read(1024*1024)
            if not chunk:break
            count+=len(chunk)
            if count>maximum:raise ValueError('Growing native payload exceeds limit')
            digest.update(chunk);chunks.append(chunk)
        if _view_stamp(os.fstat(stream.fileno()))!=handle or _view_stamp(_path_stat(path))!=view:
            raise ValueError('Native payload changed during read')
        if count!=before.st_size:raise ValueError('Native payload size changed')
        # Two-pass hashing of the exact same opened file. A successful metadata
        # admission is never reported as a verified payload.
        stream.seek(0);again=hashlib.sha256()
        while True:
            check_cancelled();chunk=stream.read(1024*1024)
            if not chunk:break
            again.update(chunk)
        if (again.digest()!=digest.digest() or _view_stamp(os.fstat(stream.fileno()))!=handle
                or _view_stamp(_path_stat(path))!=view):
            raise ValueError('Native payload changed between read passes')
    if expected is not None and (count!=expected['bytes'] or digest.hexdigest()!=expected['sha256']):
        raise ValueError('Retained native payload hash/size differs')
    return b''.join(chunks)
