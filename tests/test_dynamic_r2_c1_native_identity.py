"""C1 file-identity regressions. Windows stat observations are replayed, not native runs."""
from types import SimpleNamespace
import hashlib
import os
from pathlib import Path

import pytest
from caelab import dynamic_native_stream as native


def stat_view(value, **changes):
    """Preserve real file fields; override only explicitly named probe fields."""
    fields = {k: getattr(value, k) for k in dir(value) if k.startswith('st_')}
    fields.update(changes)
    return SimpleNamespace(**fields)


def test_observed_cross_api_ctime_skew_is_not_file_replacement(tmp_path, monkeypatch):
    path = tmp_path / 'native.frd'
    payload = b'first\nsecond\n'
    path.write_bytes(payload)
    raw_fstat = native.os.fstat
    identity = path.stat()
    def observed(fd):
        value = raw_fstat(fd)
        if (value.st_dev, value.st_ino) == (identity.st_dev, identity.st_ino):
            # Probe's two APIs disagree by 996000 ns on an otherwise unchanged file.
            return stat_view(value, st_ctime_ns=value.st_ctime_ns + 996000)
        return value
    monkeypatch.setattr(native.os, 'fstat', observed)
    lines = native.NativeLines(path)
    try:
        assert [lines[i] for i in range(len(lines))] == ['first', 'second']
        lines.finish()
        assert lines.sha256 == hashlib.sha256(payload).hexdigest()
    finally:
        lines.close()

import json
import stat
from test_dynamic_support import dynamic_model, outputs
from test_dynamic_r2_streaming import options
from caelab.adapters.frozen_fem import read_frd
from caelab.execution_control import ExecutionCancelled

PROBE = Path(__file__).parent / 'fixtures/dynamic_r2_c1/windows-stat-probe.json'


def probes():
    return json.loads(PROBE.read_text(encoding='utf-8'))


@pytest.mark.parametrize('case', [0, 1], ids=['observed-skew', 'observed-equal'])
def test_exact_observed_stat_records_have_same_cross_api_identity(case):
    row = probes()[case]
    p = SimpleNamespace(st_mode=stat.S_IFREG, **row['path_stat'])
    f = SimpleNamespace(st_mode=stat.S_IFREG, **row['fd_stat'])
    assert native._stamp(p) == native._stamp(f)
    assert (native._view_stamp(p) == native._view_stamp(f)) == (case == 1)


def install_probe_times(monkeypatch, path, row):
    """Real data and file IDs, only the supplied path/fd ctime/birthtime replayed."""
    raw_stat, raw_fstat = Path.stat, native.os.fstat
    original = raw_stat(path)
    identity = original.st_dev, original.st_ino
    def path_stat(self, *args, **kwargs):
        value = raw_stat(self, *args, **kwargs)
        if (value.st_dev, value.st_ino) == identity:
            value = stat_view(value, **{k: row['path_stat'][k] for k in
                                       ('st_ctime_ns', 'st_birthtime_ns')})
        return value
    def fd_stat(fd):
        value = raw_fstat(fd)
        if (value.st_dev, value.st_ino) == identity:
            value = stat_view(value, **{k: row['fd_stat'][k] for k in
                                       ('st_ctime_ns', 'st_birthtime_ns')})
        return value
    monkeypatch.setattr(Path, 'stat', path_stat)
    monkeypatch.setattr(native.os, 'fstat', fd_stat)


@pytest.mark.parametrize('case', [0, 1], ids=['observed-skew', 'observed-equal'])
@pytest.mark.parametrize('crlf', [False, True], ids=['LF', 'CRLF'])
def test_strict_grammar_and_raw_hash_with_observed_stat_views(tmp_path, monkeypatch, case, crlf):
    model = dynamic_model()
    data = outputs(model)[0].encode('ascii')
    if crlf:
        data = data.replace(b'\n', b'\r\n')
    path = tmp_path / 'native.frd'
    path.write_bytes(data)
    n, e, k = options(model)
    original = read_frd(path, n, e, **k)
    install_probe_times(monkeypatch, path, probes()[case])
    result = native.read_dynamic_frd(path, n, e, parent=tmp_path, **k)
    try:
        assert list(result['frames']) == original['frames']
        assert result['native_transport']['raw_sha256'] == hashlib.sha256(data).hexdigest()
        assert result['native_transport']['raw_bytes'] == len(data)
    finally:
        native.release(result)
    assert not list(tmp_path.glob('.dynamic-native-*'))
    assert path.read_bytes() == data


def track_handles(monkeypatch):
    original, handles = native._open_native, []
    def opened(path):
        handle = original(path)
        handles.append(handle)
        return handle
    monkeypatch.setattr(native, '_open_native', opened)
    return handles


@pytest.mark.parametrize('field', ['st_dev', 'st_ino', 'st_size', 'st_mtime_ns',
                                    'st_birthtime_ns', 'st_mode', 'zero_inode'])
def test_cross_api_non_ctime_mismatch_fails_before_scan_and_closes(tmp_path, monkeypatch, field):
    path = tmp_path / 'native.frd'; path.write_bytes(b'a\nb\n')
    original = native.os.fstat
    def changed(fd):
        s = original(fd)
        if field == 'st_mode': return stat_view(s, st_mode=stat.S_IFDIR)
        if field == 'zero_inode': return stat_view(s, st_ino=0)
        return stat_view(s, **{field: getattr(s, field, 0) + 1})
    monkeypatch.setattr(native.os, 'fstat', changed)
    handles = track_handles(monkeypatch)
    with pytest.raises(ValueError): native.NativeLines(path)
    assert handles and all(h.closed for h in handles)
    assert path.read_bytes() == b'a\nb\n'


@pytest.mark.parametrize('view', ['path', 'handle'])
def test_ctime_changes_within_each_api_are_still_rejected(tmp_path, monkeypatch, view):
    path = tmp_path / 'native.frd'; path.write_bytes(b'a\nb\n')
    lines = native.NativeLines(path)
    try:
        if view == 'path':
            original = Path.stat
            def changed(self, *a, **k):
                s = original(self, *a, **k)
                return stat_view(s, st_ctime_ns=s.st_ctime_ns + 1) if self == path else s
            monkeypatch.setattr(Path, 'stat', changed)
        else:
            original = native.os.fstat
            monkeypatch.setattr(native.os, 'fstat', lambda fd:
                stat_view(original(fd), st_ctime_ns=original(fd).st_ctime_ns + 1))
        with pytest.raises(ValueError, match='changed'): lines.finish()
    finally: lines.close()


@pytest.mark.parametrize('mutation', ['grow', 'mtime', 'same_size'])
def test_file_mutation_after_first_pass_is_rejected(tmp_path, mutation):
    path = tmp_path / 'native.frd'; path.write_bytes(b'a\nb\n')
    original = path.stat()
    lines = native.NativeLines(path)
    try:
        if mutation == 'grow': path.write_bytes(b'a\nb\nc\n')
        elif mutation == 'mtime': os.utime(path, ns=(original.st_atime_ns, original.st_mtime_ns + 10000000))
        else:
            path.write_bytes(b'z\nb\n')
            os.utime(path, ns=(original.st_atime_ns, original.st_mtime_ns))
        with pytest.raises(ValueError, match='changed'): lines.finish()
    finally: lines.close()


def freeze_observed_metadata(monkeypatch, path, handle):
    """Simulate a file system exposing unchanged stamps; bytes must still be checked."""
    raw_stat, raw_fstat = Path.stat, native.os.fstat
    p, f = raw_stat(path), raw_fstat(handle.fileno())
    def path_stat(self, *a, **k):
        return p if self == path else raw_stat(self, *a, **k)
    def fd_stat(fd):
        return f if fd == handle.fileno() else raw_fstat(fd)
    monkeypatch.setattr(Path, 'stat', path_stat)
    monkeypatch.setattr(native.os, 'fstat', fd_stat)


@pytest.mark.parametrize('mutation', ['same_size', 'extra_eof', 'truncated'])
def test_two_pass_digest_and_eof_gate_even_with_unchanged_stat_records(tmp_path, monkeypatch, mutation):
    path = tmp_path / 'native.frd'; path.write_bytes(b'a\nb\n')
    lines = native.NativeLines(path)
    try:
        freeze_observed_metadata(monkeypatch, path, lines.stream)
        if mutation == 'same_size': path.write_bytes(b'z\nb\n')
        elif mutation == 'extra_eof': path.write_bytes(b'a\nb\nc\n')
        else: path.write_bytes(b'a\n')
        with pytest.raises(ValueError, match='changed|truncated'): lines.finish()
    finally: lines.close()


@pytest.mark.parametrize('phase', [1, 2], ids=['before-scan-open', 'between-passes'])
@pytest.mark.parametrize('mutation', ['delete', 'replace'])
def test_path_delete_or_crossfile_swap_at_open_is_rejected(tmp_path, monkeypatch, phase, mutation):
    path = tmp_path / 'native.frd'; payload = b'a\nb\n'; path.write_bytes(payload)
    replacement = tmp_path / 'other'; replacement.write_bytes(payload)
    original_stat = path.stat()
    os.utime(replacement, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))
    original, calls, handles = native._open_native, [], []
    def opened(p):
        calls.append(p)
        if len(calls) == phase:
            if mutation == 'delete': p.unlink()
            else: os.replace(replacement, p)
        h = original(p); handles.append(h); return h
    monkeypatch.setattr(native, '_open_native', opened)
    with pytest.raises((ValueError, OSError)): native.NativeLines(path)
    assert all(h.closed for h in handles)


@pytest.mark.parametrize('at', ['initial-leaf', 'initial-parent', 'between-passes'])
def test_symlink_is_rejected_even_when_target_bytes_match(tmp_path, monkeypatch, at):
    folder = tmp_path / 'real'; folder.mkdir(); real = folder / 'native.frd'
    real.write_bytes(b'a\nb\n')
    path = tmp_path / 'link'
    def link(p, target, directory=False):
        try: p.symlink_to(target, target_is_directory=directory)
        except OSError as error: pytest.skip('Host symlink creation unavailable: ' + str(error))
    if at == 'initial-leaf': link(path, real)
    elif at == 'initial-parent':
        link(path, folder, True); path = path / 'native.frd'
    else:
        path.write_bytes(real.read_bytes())
        original, calls = native._open_native, []
        def opened(p):
            calls.append(p)
            if len(calls) == 2:
                p.unlink(); link(p, real)
            return original(p)
        monkeypatch.setattr(native, '_open_native', opened)
    with pytest.raises((ValueError, OSError)): native.NativeLines(path)
    assert real.read_bytes() == b'a\nb\n'


@pytest.mark.parametrize('phase', ['metadata', 'parse'])
def test_cancellation_keeps_input_and_closes_streams_and_spool(tmp_path, monkeypatch, phase):
    model = dynamic_model(); path = tmp_path / 'native.frd'
    payload = outputs(model)[0].encode('ascii'); path.write_bytes(payload)
    handles = track_handles(monkeypatch)
    calls = []
    def cancel():
        calls.append(1)
        if len(calls) == (1 if phase == 'metadata' else 2):
            raise ExecutionCancelled('C1 cancellation at ' + phase)
    monkeypatch.setattr(native, 'check_cancelled', cancel)
    n, e, k = options(model)
    with pytest.raises(ExecutionCancelled): native.read_dynamic_frd(path, n, e, parent=tmp_path, **k)
    assert handles and all(h.closed for h in handles)
    assert path.read_bytes() == payload
    assert not list(tmp_path.glob('.dynamic-native-*'))
