"""Byte-identical guard identity, including changes hidden by size/mtime."""
import hashlib
import os

from caelab import storage


def test_uncached_guard_matches_legacy_digest_without_git(tmp_path, monkeypatch):
    (tmp_path / 'caelab').mkdir(); (tmp_path / 'schemas').mkdir()
    paths = [tmp_path / 'caelab/a.py', tmp_path / 'caelab/b.py', tmp_path / 'schemas/a.json']
    for path, value in zip(paths, (b'old', b'code', b'{}')):
        path.write_bytes(value)
    digest = hashlib.sha256()
    for path in paths:
        digest.update(path.relative_to(tmp_path).as_posix().encode())
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    def no_git(*args, **kwargs):
        raise AssertionError('A byte guard must not query Git')
    monkeypatch.setattr(storage.subprocess, 'check_output', no_git)
    original = storage.core_source_hash(tmp_path)
    assert original == digest.hexdigest()
    stat = paths[0].stat()
    paths[0].write_bytes(b'new')
    os.utime(paths[0], ns=(stat.st_atime_ns, stat.st_mtime_ns))
    assert storage.core_source_hash(tmp_path) != original
    (tmp_path / 'caelab/added.py').write_bytes(b'added')
    added = storage.core_source_hash(tmp_path)
    (tmp_path / 'caelab/added.py').unlink()
    assert storage.core_source_hash(tmp_path) != added


def test_producer_keeps_git_metadata_with_same_guard_hash(tmp_path, monkeypatch):
    (tmp_path / 'caelab').mkdir(); (tmp_path / 'schemas').mkdir()
    (tmp_path / 'caelab/a.py').write_bytes(b'code')
    def git(args, **kwargs):
        return 'TEST_ONLY_COMMIT\n' if args[1] == 'rev-parse' else ' M unrelated.txt\n'
    monkeypatch.setattr(storage.subprocess, 'check_output', git)
    assert storage.source_identity(tmp_path) == {
        'core_commit': 'TEST_ONLY_COMMIT', 'core_dirty': True,
        'core_source_sha256': storage.core_source_hash(tmp_path)}
