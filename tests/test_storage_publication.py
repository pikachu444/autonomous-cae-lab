"""Prepared JSON I/O recovery with controlled Windows sharing errors.

The reported winerror is injected on this host; no Windows runtime is claimed.
"""
from copy import deepcopy
import errno
import json
from pathlib import Path
from types import SimpleNamespace
import threading

import pytest

from caelab import storage
from caelab.material_document import MaterialDocuments


def windows_error(code):
    error = OSError(errno.EACCES, 'controlled Windows sharing/access conflict')
    error.winerror = code
    return error


@pytest.fixture
def short_retry(monkeypatch):
    monkeypatch.setattr(storage, 'IO_RETRY_SECONDS', 0.02)


@pytest.mark.parametrize('code', [5, 32, 33])
def test_publish_retries_identical_prepared_temp_only(tmp_path, monkeypatch, short_retry, code):
    target = tmp_path / 'document.json'
    previous = {'revision': 'old', 'description': '이전 결과'}
    storage.save_json(target, previous)
    value = {'revision': 'new', 'description': '새 시험 결과', 'values': list(range(30))}
    original_replace = Path.replace
    attempts = []
    def conflict_once(temporary, destination):
        if destination == target:
            attempts.append((temporary, temporary.read_bytes()))
            assert json.loads(target.read_text(encoding='utf-8')) == previous
            if len(attempts) == 1:
                raise windows_error(code)
        return original_replace(temporary, destination)
    monkeypatch.setattr(Path, 'replace', conflict_once)
    storage.save_json(target, value)
    assert len(attempts) == 2
    assert attempts[0] == attempts[1]
    assert json.loads(target.read_text(encoding='utf-8')) == value
    assert not attempts[0][0].exists()


@pytest.mark.parametrize('code', [5, 32, 33])
def test_expired_publish_keeps_previous_json_and_prepared_temp(tmp_path, monkeypatch, short_retry, code):
    target = tmp_path / 'document.json'
    storage.save_json(target, {'revision': 'previous'})
    before = target.read_bytes()
    attempts = []
    failure = windows_error(code)
    def conflict_always(temporary, destination):
        assert destination == target
        attempts.append((temporary, temporary.read_bytes()))
        raise failure
    monkeypatch.setattr(Path, 'replace', conflict_always)
    with pytest.raises(OSError) as caught:
        storage.save_json(target, {'revision': 'pending', 'draft': '보존할 편집'})
    assert caught.value is failure
    assert 2 <= len(attempts) <= 8
    assert all(attempt == attempts[0] for attempt in attempts)
    assert target.read_bytes() == before
    assert attempts[0][0].is_file()
    assert json.loads(attempts[0][1]) == {'revision': 'pending', 'draft': '보존할 편집'}
    assert caught.value.temporary_path == str(attempts[0][0])
    assert caught.value.target_path == str(target)


@pytest.mark.parametrize('failure', [PermissionError(errno.EACCES, 'non-Windows permission error'),
                                    windows_error(2), windows_error(87)])
def test_publish_does_not_retry_unrelated_os_errors(tmp_path, monkeypatch, short_retry, failure):
    target = tmp_path / 'document.json'
    storage.save_json(target, {'revision': 'old'})
    before = target.read_bytes()
    attempts = []
    def fail(temporary, destination):
        attempts.append(temporary)
        raise failure
    monkeypatch.setattr(Path, 'replace', fail)
    with pytest.raises(OSError) as caught:
        storage.save_json(target, {'revision': 'unpublished'})
    assert caught.value is failure and len(attempts) == 1
    assert target.read_bytes() == before
    assert attempts[0].is_file()


@pytest.mark.parametrize('code', [5, 32, 33])
def test_load_retries_transient_windows_read_conflict(tmp_path, monkeypatch, short_retry, code):
    target = tmp_path / 'document.json'
    value = {'description': '측정 시험', 'generation': 3}
    storage.save_json(target, value)
    original_read = storage._read_utf8
    attempts = []
    def conflict_once(path, *args, **kwargs):
        if path == target:
            attempts.append(path)
            if len(attempts) == 1:
                raise windows_error(code)
        return original_read(path, *args, **kwargs)
    monkeypatch.setattr(storage, '_read_utf8', conflict_once)
    assert storage.load_json(target) == value
    assert attempts == [target, target]


def test_load_read_retry_is_bounded_and_keeps_file(tmp_path, monkeypatch, short_retry):
    target = tmp_path / 'document.json'
    storage.save_json(target, {'generation': 2})
    before = target.read_bytes()
    attempts = []
    failure = windows_error(32)
    def unavailable(path, *args, **kwargs):
        attempts.append(path)
        raise failure
    monkeypatch.setattr(storage, '_read_utf8', unavailable)
    with pytest.raises(OSError) as caught:
        storage.load_json(target)
    assert caught.value is failure
    assert 2 <= len(attempts) <= 8
    assert target.read_bytes() == before


@pytest.mark.parametrize('case', ['malformed', 'missing', 'permission'])
def test_load_does_not_hide_parse_missing_or_nonwindows_permission_errors(tmp_path, monkeypatch, short_retry, case):
    target = tmp_path / 'document.json'
    if case != 'missing':
        target.write_text('{broken' if case == 'malformed' else '{}', encoding='utf-8')
    original_read = storage._read_utf8
    attempts = []
    failure = PermissionError(errno.EACCES, 'controlled non-Windows permission denied')
    def read(path, *args, **kwargs):
        attempts.append(path)
        if case == 'permission':
            raise failure
        return original_read(path, *args, **kwargs)
    monkeypatch.setattr(storage, '_read_utf8', read)
    with pytest.raises({'malformed': json.JSONDecodeError, 'missing': FileNotFoundError, 'permission': PermissionError}[case]):
        storage.load_json(target)
    assert attempts == [target]


def test_normal_json_reader_observes_complete_publications(tmp_path):
    target = tmp_path / 'document.json'
    storage.save_json(target, {'generation': 0, 'values': [0] * 300})
    stop, ready = threading.Event(), threading.Event()
    reads, failures = [], []
    def reader():
        while not stop.is_set():
            try:
                value = json.loads(target.read_text(encoding='utf-8'))
                assert value['values'] == [value['generation']] * 300
                reads.append(value['generation'])
                ready.set()
            except BaseException as error:
                failures.append(error)
                break
    thread = threading.Thread(target=reader, daemon=True)
    thread.start()
    try:
        assert ready.wait(1)
        for generation in range(1, 21):
            storage.save_json(target, {'generation': generation, 'values': [generation] * 300})
    finally:
        stop.set()
        thread.join(1)
    assert not thread.is_alive() and reads and not failures
    assert storage.load_json(target)['generation'] == 20


def test_material_final_receipt_sharing_retry_publishes_one_edit(tmp_path, monkeypatch, short_retry):
    submitted = []
    def forbid_submit(*args, **kwargs):
        submitted.append((args, kwargs))
        raise AssertionError('An update must not submit a physics job')
    owner = MaterialDocuments(tmp_path, 'Sexact', forbid_submit, SimpleNamespace(list=lambda: []))
    original = owner.open()
    draft = deepcopy(original['draft'])
    draft['settings']['parameters']['E'] = 1550
    request = {'session_id': original['session_id'], 'expected_generation': 0, 'command_id': 'Cexactedit'}
    receipt_path = owner._folder(original['id']) / 'commands' / 'Cexactedit.json'
    original_replace, original_changed = Path.replace, owner._changed
    edits, attempts = [], []
    def changed(document):
        edits.append(document['generation'])
        original_changed(document)
    def receipt_conflict_once(temporary, destination):
        if destination == receipt_path:
            payload = json.loads(temporary.read_text(encoding='utf-8'))
            if 'response' in payload:
                attempts.append((temporary, temporary.read_bytes()))
                if len(attempts) == 1:
                    assert payload['response']['document']['generation'] == 1
                    assert storage.load_json(receipt_path)['state'] == 'APPLYING'
                    raise windows_error(32)
        return original_replace(temporary, destination)
    monkeypatch.setattr(owner, '_changed', changed)
    monkeypatch.setattr(Path, 'replace', receipt_conflict_once)
    response = owner.command(original['id'], 'material.update', {'draft': draft}, **request)
    assert len(attempts) == 2 and attempts[0] == attempts[1]
    assert edits == [0] and not submitted
    assert response['document']['generation'] == 1 and response['document']['draft'] == draft
    assert owner.command(original['id'], 'material.update', {'draft': draft}, **request) == response
    assert edits == [0] and len(attempts) == 2 and not submitted
    stored = storage.load_json(owner._folder(original['id']) / 'working.json')
    assert stored['generation'] == 1 and stored['draft'] == draft
    assert stored['_undo'] == [original['draft']]
    assert storage.load_json(receipt_path)['response'] == response


def test_windows_reader_allows_atomic_rename_and_transfers_handle_to_closed_stream(tmp_path, monkeypatch):
    import ctypes
    import ctypes.wintypes
    import os
    import sys

    target = tmp_path / 'document.json'
    target.write_text('{"description": "한국어 시험", "generation": 1}', encoding='utf-8')
    calls, descriptors = [], []
    def create_file(*arguments):
        calls.append(('create', arguments))
        return 9100
    def close_handle(handle):
        calls.append(('close_handle', handle))
        return True
    def adopt_handle(handle, flags):
        calls.append(('adopt', handle, flags))
        descriptor = os.open(target, os.O_RDONLY)
        descriptors.append(descriptor)
        return descriptor
    monkeypatch.setattr(storage, 'os', SimpleNamespace(name='nt', O_RDONLY=os.O_RDONLY,
        O_BINARY=0x8000, fdopen=os.fdopen))
    monkeypatch.setattr(ctypes, 'WinDLL', lambda name, **kwargs: SimpleNamespace(
        CreateFileW=create_file, CloseHandle=close_handle), raising=False)
    monkeypatch.setitem(sys.modules, 'msvcrt', SimpleNamespace(open_osfhandle=adopt_handle))
    assert storage.load_json(target) == {'description': '한국어 시험', 'generation': 1}
    assert calls[0] == ('create', (str(target), 0x80000000, 0x1 | 0x2 | 0x4, None, 3, 0x80, None))
    assert calls[1] == ('adopt', 9100, os.O_RDONLY | 0x8000)
    assert len(calls) == 2  # fd ownership transferred; no second CloseHandle.
    with pytest.raises(OSError) as caught:
        os.fstat(descriptors[0])
    assert caught.value.errno == errno.EBADF
