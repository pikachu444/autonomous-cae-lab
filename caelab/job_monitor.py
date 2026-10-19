"""Read adapter-declared logs for one owned job, without changing its state."""
from hashlib import sha256
import codecs
import json
import os
from pathlib import Path, PureWindowsPath

MAX_CHUNK = 65536
MAX_RECEIPT = 65536
MAX_ENTRIES = 4096


def _utf8_chunk(handle, offset, limit, total):
    """Keep complete UTF-8 characters, extending a byte window by at most 3.

    A caller can request a byte inside a character. Report the actual aligned
    offset, so paging never silently drops part of a Korean word.
    """
    start = min(offset, total)
    if start < total:
        before = max(0, start - 3)
        handle.seek(before)
        prefix = handle.read(start - before + 1)
        if not prefix:
            # The solver may truncate/replace a live log after fstat.
            return start, b''
        index = len(prefix) - 1
        while index > 0 and prefix[index] & 0xC0 == 0x80:
            index -= 1
        lead = prefix[index]
        width = 2 if 0xC2 <= lead <= 0xDF else 3 if 0xE0 <= lead <= 0xEF else 4 if 0xF0 <= lead <= 0xF4 else 1
        if width > 1 and 0 < start - (before + index) < width:
            start = before + index
    handle.seek(start)
    chunk = handle.read(min(limit, total - start))
    decoder = codecs.getincrementaldecoder('utf-8')(errors='replace')
    decoder.decode(chunk, final=False)
    pending = decoder.getstate()[0]
    if pending and start + len(chunk) < total:
        lead = pending[0]
        width = 2 if lead < 0xE0 else 3 if lead < 0xF0 else 4
        chunk += handle.read(min(width - len(pending), total - start - len(chunk)))
    return start, chunk


def _local_file(root, relative):
    if (not isinstance(relative, str) or not relative or '\\' in relative or
            '\x00' in relative or PureWindowsPath(relative).drive):
        return None
    path = Path(relative)
    if path.is_absolute() or '..' in path.parts:
        return None
    candidate = root / path
    # Refuse links/junctions even when they happen to point back into this job.
    for part in (candidate, *candidate.parents):
        if part == root.parent:
            break
        if part.is_symlink() or (hasattr(part, 'is_junction') and part.is_junction()):
            return None
    if not candidate.resolve().is_relative_to(root.resolve()):
        return None
    return candidate if candidate.is_file() else None


def read_monitor(root, job, *, log=None, offset=0, limit=MAX_CHUNK):
    """Offsets/counts address bytes. Mutable logs have a chunk digest, not a seal.

    Only stdout/stderr named by execution receipts in this job's native folder
    are exposed. Missing receipts/logs are unavailable, never guessed paths.
    """
    from .storage import check_id
    identifier = check_id(job['id'])
    if type(offset) is not int or offset < 0:
        raise ValueError('Log offset must be a nonnegative integer')
    if type(limit) is not int or not 1 <= limit <= MAX_CHUNK:
        raise ValueError('Log limit must be between 1 and 65536 bytes')
    if log is not None and (not isinstance(log, str) or not log):
        raise ValueError('Choose a log from this job catalog')
    root = Path(root).absolute()
    native = root / 'native' / identifier
    result = {'job_id': identifier, 'state': job['state'], 'phase': job.get('phase'),
              'progress': None, 'executions': [], 'logs': [], 'selected_log': None,
              'errors': [job['error']] if job.get('error') else [], 'warnings': [],
              'catalog_truncated': False}
    files = {}
    visited = 0
    safe_root = (native.is_dir() and not any(
        p.is_symlink() or (hasattr(p, 'is_junction') and p.is_junction())
        for p in (root, root / 'native', native)))
    if safe_root:
        for folder, directories, names in os.walk(native, followlinks=False):
            directories[:] = sorted(name for name in directories
                if not (Path(folder) / name).is_symlink() and not (
                    hasattr(Path(folder) / name, 'is_junction') and
                    (Path(folder) / name).is_junction()))
            visited += 1 + len(names) + len(directories)
            if visited > MAX_ENTRIES:
                result['catalog_truncated'] = True
                break
            for name in sorted(names):
                if name != 'execution.json' and not name.endswith('.execution.json'):
                    continue
                relative = (Path(folder) / name).relative_to(native).as_posix()
                receipt = _local_file(native, relative)
                if receipt is None or receipt.stat().st_size > MAX_RECEIPT:
                    continue
                try:
                    with receipt.open('rb') as handle:
                        payload = handle.read(MAX_RECEIPT + 1)
                    if len(payload) > MAX_RECEIPT:
                        continue
                    data = json.loads(payload)
                except (OSError, ValueError, UnicodeError):
                    # An adapter may be replacing a running receipt at this moment.
                    continue
                if not isinstance(data, dict) or not isinstance(data.get('status'), str):
                    continue
                execution_id = 'native:' + relative
                result['executions'].append({'id': execution_id,
                    'label': relative.removesuffix('.execution.json').removesuffix('/execution.json'),
                    **{key: data.get(key) for key in ('status', 'started_utc', 'finished_utc', 'return_code')}})
                for stream in ('stdout', 'stderr'):
                    declared = data.get(stream)
                    if not isinstance(declared, str):
                        continue
                    # Validate the declared name before combining it with the receipt folder.
                    if _local_file(Path(folder), declared) is None:
                        continue
                    log_relative = (Path(folder) / declared).relative_to(native).as_posix()
                    source = _local_file(native, log_relative)
                    if source is None:
                        continue
                    log_id = 'native:' + log_relative
                    if log_id not in files:
                        files[log_id] = source
                        result['logs'].append({'id': log_id, 'label': log_relative,
                                               'bytes': source.stat().st_size})
    if log is not None:
        if log not in files:
            raise ValueError('The selected log is not available in this job catalog')
        source = files[log]
        # Revalidate links immediately before opening; a catalog is not path authority.
        if _local_file(native, source.relative_to(native).as_posix()) is None:
            raise ValueError('The selected log is no longer available')
        with source.open('rb') as handle:
            total = os.fstat(handle.fileno()).st_size
            start, chunk = _utf8_chunk(handle, offset, limit, total)
        result['selected_log'] = {'id': log, 'text': chunk.decode('utf-8', errors='replace'),
            'encoding': 'utf-8', 'decode_errors': 'replace', 'offset': start,
            'next_offset': start + len(chunk), 'total_bytes': total,
            'truncated': start > 0 or start + len(chunk) < total,
            'chunk_sha256': sha256(chunk).hexdigest()}
    return result
