"""Request-local path verification, never a persistent artifact/byte cache.

Directory identity is checked once during traversal and again before a reader
returns. Files are checked on every access. Byte hashes, native envelopes and
file-handle checks remain the responsibility of the existing readers.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
from pathlib import Path, PurePosixPath, PureWindowsPath
import stat


_active = ContextVar('caelab_verified_read_paths', default=None)


def _identity(value):
    if value is None:
        return None
    base = (value.st_dev, value.st_ino, stat.S_IFMT(value.st_mode),
            getattr(value, 'st_file_attributes', 0), getattr(value, 'st_reparse_tag', 0))
    # Appending a different experiment may change a shared directory's mtime,
    # but cannot replace its identity or turn it into a redirect.
    return base if stat.S_ISDIR(value.st_mode) else (*base, value.st_size, value.st_mtime_ns)


def _metadata(path):
    try:
        value = path.lstat()
    except FileNotFoundError:
        return None
    if (stat.S_ISLNK(value.st_mode)
            or getattr(value, 'st_file_attributes', 0) & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x400)):
        raise ValueError('Verified read paths must not be symlinks or reparse points')
    return value


class _ReadPaths:
    def __init__(self, lab):
        self.lab = lab
        self.original = Path(lab.store).absolute()
        self.root = self.original.resolve()
        self.nodes = {}
        # Include the resolved root's ancestors so a redirect of a mounted
        # store parent during this request cannot silently change its target.
        for path in reversed((self.root, *self.root.parents)):
            self._check(path, cache_directory=False)

    def _check(self, path, *, cache_directory):
        prior = self.nodes.get(path)
        if cache_directory and prior is not None and prior[1] is not None and stat.S_ISDIR(prior[1].st_mode):
            return prior[1]
        value = _metadata(path)
        identity = _identity(value)
        if path in self.nodes and self.nodes[path][0] != identity:
            raise ValueError('Verified read path changed during this request')
        self.nodes.setdefault(path, (identity, value))
        return value

    def path(self, candidate, *, boundary=None, directory=None):
        if Path(self.lab.store).absolute() != self.original:
            raise ValueError('Verified reader changed its selected store')
        candidate = Path(candidate).absolute()
        boundary = self.root if boundary is None else Path(boundary).absolute()
        if not boundary.is_relative_to(self.root) or not candidate.is_relative_to(boundary):
            raise ValueError('Verified read path escapes its declared boundary')
        current = self.root
        parts = candidate.relative_to(self.root).parts
        value = self._check(current, cache_directory=True)
        for index, part in enumerate(parts):
            if part in ('', '.', '..') or '\x00' in part:
                raise ValueError('Verified read path is not normalized')
            current = current / part
            value = self._check(current, cache_directory=index < len(parts)-1)
        if directory is not None and (value is None or not (
                stat.S_ISDIR(value.st_mode) if directory else stat.S_ISREG(value.st_mode))):
            raise ValueError('Verified read path has the wrong file type')
        return candidate

    def relative(self, relative):
        if (type(relative) is not str or not relative or '\x00' in relative or '\\' in relative
                or ':' in relative or PurePosixPath(relative).is_absolute() or PureWindowsPath(relative).drive
                or any(part in ('', '.', '..') for part in relative.split('/'))):
            raise ValueError('Verified read path must be a normalized store-relative path')
        return self.path(self.root / relative)

    def recheck(self):
        if Path(self.lab.store).absolute() != self.original or self.original.resolve() != self.root:
            raise ValueError('Verified reader store changed during this request')
        for path, (identity, _) in self.nodes.items():
            if _identity(_metadata(path)) != identity:
                raise ValueError('Verified read path changed before returning the result')


@contextmanager
def verified_read_paths(lab):
    previous = _active.get()
    if previous is not None and previous.lab is lab:
        yield previous
        return
    guard = _ReadPaths(lab)
    token = _active.set(guard)
    try:
        yield guard
        guard.recheck()
    finally:
        _active.reset(token)


def guarded_reader(method):
    @wraps(method)
    def read(lab, *args, **kwargs):
        with verified_read_paths(lab):
            return method(lab, *args, **kwargs)
    return read


def active_relative_path(lab, relative):
    guard = _active.get()
    return guard.relative(relative) if guard is not None and guard.lab is lab else None


def active_bounded_path(root, path, *, directory=False):
    guard = _active.get()
    if guard is None:
        return None
    return guard.path(path, boundary=root, directory=directory)
