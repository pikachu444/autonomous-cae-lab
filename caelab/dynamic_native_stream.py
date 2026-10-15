"""Bounded native text/spool transport for the EXISTING strict FRD grammar.

Not a new FRD parser: frozen_fem._read_frd_lines owns every numeric/identity,
coverage, ordering and EOF decision. Only line transport and transient frames
change. The durable result remains dynamic_result_store's existing v2 artifacts.
"""
from collections import OrderedDict
from collections.abc import Sequence
from copy import deepcopy
import hashlib
import os
import stat as stat_mode
from pathlib import Path
import tempfile

from .execution_control import check_cancelled
from .dynamic_result_store import _write, _json, file_pin

LINE_LIMIT = 1024 * 1024


def _stamp(stat):
    """Cross-API identity/content stamp; ctime is NOT portable between stat/fstat.

    Python's Windows ctime semantics can differ between path and handle views.
    Keep birthtime (when supplied), never substitute ctime for it. Each view's
    own ctime is still checked for changes by _view_stamp below.
    """
    if not stat_mode.S_ISREG(stat.st_mode) or not stat.st_ino:
        raise ValueError('Native output must have a regular, stable file identity')
    return (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns,
            getattr(stat, 'st_birthtime_ns', None))


def _view_stamp(stat):
    """Compare ctime only within the same observation API, never across APIs."""
    return _stamp(stat), stat.st_ctime_ns


def _path_stat(path):
    # Repeat link checks at phase boundaries, not merely at construction. An
    # opened handle must still belong to this unredirected original path.
    if any(p.is_symlink() or (hasattr(p, 'is_junction') and p.is_junction())
           for p in (path, *path.parents)):
        raise ValueError('Native output must be a regular local file, not a link')
    value = path.stat()
    _stamp(value)
    return value


def _open_native(path):
    # O_NOFOLLOW narrows the final-component open race where the OS supports it.
    # Windows still uses both path/handle stamps before and after each pass.
    def opener(name, flags):
        return os.open(name, flags | getattr(os, 'O_NOFOLLOW', 0))
    return open(path, 'rb', opener=opener)


def _decode(raw):
    if len(raw) > LINE_LIMIT or b'\x00' in raw:
        raise ValueError('Malformed or oversized native ASCII line')
    text = raw.decode('ascii').replace('\r\n', '\n')
    if '\r' in text:
        raise ValueError('Malformed ASCII FRD line encoding')
    return text.rstrip('\n')


class NativeLines:
    """Length-known two-pass sequential lines, O(one line + field headers).

    Both passes hash the bytes. The second pass may only look ahead or revisit
    its last two lines; the strict grammar does not seek into past frame arrays.
    outline retains ONLY PSTEP/end-marker lines for the existing prefix policy.
    """
    def __init__(self, path):
        self.path = Path(path).absolute()
        before = _path_stat(self.path)
        self.before = _stamp(before)
        self._path_before = _view_stamp(before)
        self.versions, self.starts, self.endings = [], [], []
        self.count, self.byte_count, self.ends_with_newline = 0, 0, False
        digest = hashlib.sha256()
        after_end = False
        with _open_native(self.path) as stream:
            self._handle_before = _view_stamp(os.fstat(stream.fileno()))
            self._check_source(stream, 'before metadata scan')
            while True:
                raw = stream.readline(LINE_LIMIT + 1)
                if not raw:
                    break
                if self.count % 4096 == 0:
                    check_cancelled()
                line = _decode(raw)
                digest.update(raw); self.byte_count += len(raw)
                if line.strip().startswith('1UVERSION'):
                    self.versions.append(line.strip())
                if line.split()[:1] == ['1PSTEP']:
                    self.starts.append((self.count, line))
                if line.strip() == '9999':
                    self.endings.append(self.count)
                if self.endings and self.count > self.endings[0] and line.strip():
                    after_end = True
                self.count += 1
                self.ends_with_newline = raw.endswith(b'\n')
            self._check_source(stream, 'during metadata scan')
        if self.byte_count != self.before[2]:
            raise ValueError('Native output size differs from metadata scan')
        self.trailing_after_end = after_end
        self.sha256 = digest.hexdigest()
        self.stream = _open_native(self.path)
        try:
            self._check_source(self.stream, 'before strict parse')
        except BaseException:
            self.stream.close()
            raise
        self.position, self.cache, self.digest = -1, OrderedDict(), hashlib.sha256()

    def _check_source(self, stream, phase):
        handle = os.fstat(stream.fileno())
        if (self.before != _stamp(handle)
                or self._handle_before != _view_stamp(handle)
                or self._path_before != _view_stamp(_path_stat(self.path))):
            raise ValueError('Native output changed ' + phase)

    def __len__(self):
        return self.count

    def __getitem__(self, index):
        if type(index) is not int or not 0 <= index < self.count:
            raise IndexError(index)
        if index < self.position - 1:
            raise ValueError('Native line consumer attempted unbounded backwards access')
        while self.position < index:
            if (self.position + 1) % 4096 == 0:
                check_cancelled()
            raw = self.stream.readline(LINE_LIMIT + 1)
            if not raw:
                raise ValueError('Native output truncated during strict parse')
            self.digest.update(raw)
            self.position += 1
            self.cache[self.position] = _decode(raw)
            while len(self.cache) > 2:
                self.cache.popitem(last=False)
        return self.cache[index]

    def finish(self):
        self._check_source(self.stream, 'before strict parse completion')
        if self.count:
            self[self.count - 1]
        if self.stream.read(1) or self.digest.hexdigest() != self.sha256:
            raise ValueError('Native output changed during strict parse')
        self._check_source(self.stream, 'during strict parse')

    def close(self):
        self.stream.close()

    def copy_prefix(self, destination, cut, *, terminator):
        """Exact existing prefix policy: normalize CRLF; append labelled end only."""
        destination = Path(destination)
        if any(p.is_symlink() for p in (destination, *destination.parents)):
            raise ValueError('Derived native output must be a regular local path')
        destination.parent.mkdir(parents=True, exist_ok=True)
        with _open_native(self.path) as stream, destination.open('w+b') as target:
            self._check_source(stream, 'before deriving prefix')
            for index in range(cut):
                if index % 4096 == 0:
                    check_cancelled()
                raw = stream.readline(LINE_LIMIT + 1)
                if not raw:
                    raise ValueError('Native output truncated while deriving prefix')
                _decode(raw)
                target.write(raw.replace(b'\r\n', b'\n'))
            if terminator:
                # Existing reading copy strips final newlines, then adds one.
                end = target.tell()
                while end:
                    target.seek(end-1)
                    if target.read(1) != b'\n':
                        break
                    end -= 1
                target.seek(end); target.truncate()
                target.write(b'\n 9999\n')
            self._check_source(stream, 'while deriving prefix')


class NativeFrames(Sequence):
    """Transient pinned frames. Metadata scans never materialize native arrays."""
    def __init__(self, parent=None):
        self.temporary = tempfile.TemporaryDirectory(prefix='.dynamic-native-', dir=parent)
        self.root = Path(self.temporary.name)
        self.metadata, self.pins, self.cache = [], [], OrderedDict()
        self.closed = False
        self.max_resident_frames = 0

    def append(self, frame):
        check_cancelled()
        index = len(self.metadata)
        if index >= 1024:
            raise ValueError('Expected 1..1024 retained exact frames')
        path = self.root / ('frame%04d.json' % index)
        _write(path, frame)
        self.pins.append(file_pin(self.root, path))
        self.metadata.append({k: deepcopy(frame[k]) for k in ('static', 'load_parameter_token')}
                             | {'fields': {name: {} for name in frame['fields']}})

    def __len__(self):
        return len(self.metadata)

    def __getitem__(self, index):
        if self.closed:
            raise ValueError('Transient native frames have been released')
        if isinstance(index, slice):
            return [self[i] for i in range(*index.indices(len(self)))]
        if type(index) is not int:
            raise TypeError('Choose an exact integer native frame')
        if index < 0:
            index += len(self)
        if not 0 <= index < len(self):
            raise IndexError(index)
        if index not in self.cache:
            row = _json(self.root, self.pins[index])
            row['fields'] = {name: {int(n): values for n, values in field.items()}
                             for name, field in row['fields'].items()}
            row['contact_tokens'] = {int(n): v for n, v in row.get('contact_tokens', {}).items()}
            self.cache[index] = row
            while len(self.cache) > 3:
                self.cache.popitem(last=False)
            self.max_resident_frames = max(self.max_resident_frames, len(self.cache))
        self.cache.move_to_end(index)
        row = self.cache[index]
        if 'step_location' in self.metadata[index]:
            row['step_location'] = deepcopy(self.metadata[index]['step_location'])
        return row

    def close(self):
        self.cache.clear()
        self.closed = True
        self.temporary.cleanup()


def frame_catalog(frames):
    """Borrow metadata for validation; ordinary lists retain their public behavior."""
    return getattr(frames, 'metadata', frames)


def read_dynamic_frd(path, nodes, elements, *, parent=None, **kwargs):
    """Strict grammar + bounded transport; caller owns returned transient frames."""
    from .adapters.frozen_fem import _read_frd_lines
    lines = NativeLines(path)
    frames = NativeFrames(parent)
    try:
        observed = _read_frd_lines(lines, nodes, elements, versions=lines.versions,
            ends_with_newline=lines.ends_with_newline, frame_sink=frames, **kwargs)
        lines.finish()
        observed['native_transport'] = {'kind': 'strict_grammar_streamed',
            'raw_bytes': lines.byte_count, 'raw_sha256': lines.sha256,
            'resident_frame_limit': 3, 'line_limit_bytes': LINE_LIMIT,
            'frame_count': len(frames)}
        return observed
    except BaseException:
        frames.close()
        raise
    finally:
        lines.close()


def release(observed):
    frames = (observed or {}).get('frames')
    if isinstance(frames, NativeFrames) and not frames.closed:
        frames.close()
