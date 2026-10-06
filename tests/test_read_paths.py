"""Real filesystem controls for request-local verification; no native solver."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pytest

from caelab.read_paths import verified_read_paths
from caelab.response_comparison import _path
from apps.lab.reporting import _read


def _lab(tmp_path):
    store = tmp_path/'store'; store.mkdir()
    folder = store/'experiments/E-test'; folder.mkdir(parents=True)
    (folder/'source.txt').write_bytes(b'original verified bytes')
    return SimpleNamespace(store=store), folder


def test_repeated_reads_preserve_exact_bytes_and_bounded_file_handle_checks(tmp_path):
    lab, folder = _lab(tmp_path)
    with verified_read_paths(lab):
        for _ in range(3):
            candidate = _path(lab, 'experiments/E-test/source.txt')
            assert _read(folder, candidate) == b'original verified bytes'


def test_cached_directory_redirect_is_rejected_before_returning(tmp_path):
    lab, folder = _lab(tmp_path)
    other = tmp_path/'foreign'; other.mkdir(); (other/'source.txt').write_bytes(b'foreign bytes')
    with pytest.raises(ValueError, match='symlinks|changed'):
        with verified_read_paths(lab):
            assert _path(lab, 'experiments/E-test/source.txt').read_bytes() == b'original verified bytes'
            retained = folder.with_name('retained'); folder.rename(retained)
            folder.symlink_to(other, target_is_directory=True)
            # A read still cannot escape the declared boundary unnoticed even
            # if its directory was checked earlier within the same request.
            _path(lab, 'experiments/E-test/source.txt')


def test_changed_file_generation_and_missing_file_creation_are_rejected(tmp_path):
    lab, folder = _lab(tmp_path)
    with pytest.raises(ValueError, match='changed'):
        with verified_read_paths(lab):
            _path(lab, 'experiments/E-test/source.txt')
            (folder/'source.txt').write_bytes(b'changed result')
    with pytest.raises(ValueError, match='changed'):
        with verified_read_paths(lab):
            _path(lab, 'experiments/E-test/new.txt')
            (folder/'new.txt').write_bytes(b'new generation')


def test_new_request_rechecks_current_generation_without_cross_request_cache(tmp_path):
    lab, folder = _lab(tmp_path)
    with verified_read_paths(lab):
        assert _path(lab, 'experiments/E-test/source.txt').read_bytes().startswith(b'original')
    (folder/'source.txt').write_bytes(b'new valid request generation')
    with verified_read_paths(lab):
        assert _path(lab, 'experiments/E-test/source.txt').read_bytes() == b'new valid request generation'


def test_appending_another_experiment_does_not_retarget_the_current_result(tmp_path):
    lab, folder = _lab(tmp_path)
    with verified_read_paths(lab):
        candidate = _path(lab, 'experiments/E-test/source.txt')
        sibling = folder.with_name('E-appended'); sibling.mkdir()
        (sibling/'new.txt').write_bytes(b'new independent experiment')
        assert _read(folder, candidate) == b'original verified bytes'


@pytest.mark.parametrize('relative', ['/etc/passwd', '../foreign', 'experiments/../outside',
    'experiments//E-test/source.txt', 'C:/foreign', 'experiments\\E-test', 'experiments/\x00'])
def test_ambiguous_or_escaping_relative_paths_are_refused(tmp_path, relative):
    lab, _ = _lab(tmp_path)
    with verified_read_paths(lab):
        with pytest.raises(ValueError):
            _path(lab, relative)


def test_nested_scope_and_failure_restore_the_correct_store(tmp_path):
    left = tmp_path/'left'; left.mkdir(); right = tmp_path/'right'; right.mkdir()
    a, _ = _lab(left); b, _ = _lab(right)
    with verified_read_paths(a):
        with pytest.raises(RuntimeError):
            with verified_read_paths(b):
                assert _path(b, 'experiments/E-test/source.txt').is_relative_to(b.store)
                raise RuntimeError('TEST ONLY reader exception')
        assert _path(a, 'experiments/E-test/source.txt').is_relative_to(a.store)
    with verified_read_paths(b):
        assert _path(b, 'experiments/E-test/source.txt').is_relative_to(b.store)


def test_independent_http_threads_have_independent_read_scopes(tmp_path):
    labs=[]
    for name in ('first', 'second'):
        root=tmp_path/name; root.mkdir(); lab, folder=_lab(root)
        (folder/'source.txt').write_bytes(name.encode()); labs.append(lab)
    def read(lab):
        with verified_read_paths(lab):
            return _path(lab, 'experiments/E-test/source.txt').read_bytes()
    with ThreadPoolExecutor(max_workers=2) as executor:
        assert list(executor.map(read,labs)) == [b'first', b'second']


def test_boundary_and_store_replacement_cannot_retarget_the_reader(tmp_path):
    lab, folder = _lab(tmp_path)
    with verified_read_paths(lab):
        with pytest.raises(ValueError, match='boundary'):
            _read(folder, lab.store/'outside.txt')
    replacement = tmp_path/'replacement'; replacement.mkdir()
    with pytest.raises(ValueError, match='store'):
        with verified_read_paths(lab):
            lab.store = replacement
            _path(lab, 'experiments/E-test/source.txt')
