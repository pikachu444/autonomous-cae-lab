"""Saved-result mapping lifetime without a cyclic-GC dependency.

These tests use real NumPy mappings and the host filesystem. Checking the
mapping's closed state is portable; an overwrite on Linux is not presented as
Windows native verification. No evaluator, solver or provider is started.
"""
from copy import deepcopy
import gc
from pathlib import Path
from types import SimpleNamespace
import weakref

import numpy as np
import pytest

from caelab import evaluation, storage


@pytest.fixture
def mapped_reads(monkeypatch):
    enabled = gc.isenabled()
    gc.disable()
    records = []
    load = np.load

    def tracked(path, *args, **kwargs):
        assert kwargs['mmap_mode'] == 'r'
        assert kwargs['allow_pickle'] is False
        array = load(path, *args, **kwargs)
        assert isinstance(array, np.memmap)
        records.append({'path': Path(path), 'array': weakref.ref(array), 'mapping': array._mmap})
        return array

    monkeypatch.setattr(np, 'load', tracked)
    try:
        yield records
    finally:
        # A broken reader must not leak mappings from the failing test either.
        for record in records:
            if not record['mapping'].closed:
                record['mapping'].close()
        if enabled:
            gc.enable()


@pytest.fixture
def saved_result(tmp_path):
    output = tmp_path / 'result'
    response = {'kind': 'series', 'unit': 'K', 'value': [300., 301., 302.],
                'axes': [{'name': 'time', 'unit': 's', 'values': [0., 1., 2.]}]}
    metadata = evaluation.save_evaluation({
        'execution_status': 'SUCCEEDED',
        'responses': {'first': deepcopy(response), 'second': deepcopy(response)},
        'native_channels': {'temperature': {'node_ids': [101, 202, 303]}},
        'settings': {'load_history': [5., 6., 7.]},
        'diagnostics': {'unselected_field': list(range(1000))},
    }, output)
    return output, metadata


def assert_released_and_overwritable(records):
    assert not gc.isenabled()
    assert records  # The test actually opened mappings before returning.
    assert all(record['mapping'].closed for record in records)
    for record in records:
        path = record['path']
        before = path.read_bytes()
        path.write_bytes(before)
        assert path.read_bytes() == before


@pytest.mark.parametrize(('selection', 'verify', 'expected_mappings'), [
    (None, 'all', 5),
    (['first', 'second'], 'selected', 5),
    ({'responses': ['first', 'second'], 'rows': [1, 3]}, 'all', 3),
    ({'responses': [], 'metadata_only': True, 'include_settings': True}, 'selected', 2),
])
def test_read_releases_owned_mappings_before_success_return(
        saved_result, mapped_reads, selection, verify, expected_mappings):
    output, metadata = saved_result
    result = evaluation.read_result(output, selection=selection, verify=verify)
    assert len(mapped_reads) == expected_mappings
    assert len({record['path'] for record in mapped_reads}) == expected_mappings
    assert_released_and_overwritable(mapped_reads)
    assert all(record['array']() is None for record in mapped_reads)
    if isinstance(selection, dict) and selection.get('metadata_only'):
        assert result['settings']['load_history'] == [5., 6., 7.]
        assert result['native_channels']['temperature']['node_ids'] == [101, 202, 303]
        assert result['responses'] == {}
    else:
        expected = [301., 302.] if isinstance(selection, dict) else [300., 301., 302.]
        assert result['responses']['first']['value'] == expected
        assert result['responses']['second']['value'] == expected
    if isinstance(selection, dict):
        # A bounded read must not map the unrelated large diagnostic array.
        diagnostic = metadata['diagnostics']['unselected_field']['data_ref']
        assert output / diagnostic['path'] not in {record['path'] for record in mapped_reads}
        assert result['diagnostics']['unselected_field'] == {'data_ref': diagnostic}


@pytest.mark.parametrize('mode', ['full', 'selected', 'metadata_only'])
def test_read_releases_mappings_with_gc_disabled_and_exception_traceback_alive(
        saved_result, mapped_reads, mode):
    output, metadata = saved_result
    selection = None
    if mode == 'selected':
        metadata['responses']['first']['axes'][0]['name'] = 'distance'
        selection = {'responses': ['first'], 'time_range': [0., 2.]}
        message = 'no time axis'
    elif mode == 'metadata_only':
        metadata['settings']['load_history']['data_ref']['sha256'] = '0' * 64
        selection = {'responses': [], 'metadata_only': True, 'include_settings': True}
        message = 'hash differs'
    else:
        # JSON keys are sorted on save; settings is unpacked after the mapped
        # diagnostics, native catalog and response arrays in a full read.
        metadata['settings']['load_history']['data_ref']['sha256'] = '0' * 64
        message = 'hash differs'
    storage.save_json(output / 'result.json', metadata)
    storage.save_json(output / 'result.sha256.json', {
        'sha256': evaluation.file_hash(output / 'result.json')})

    with pytest.raises(ValueError, match=message) as caught:
        evaluation.read_result(output, selection=selection)
    assert_released_and_overwritable(mapped_reads)
    # Retain the actual traceback: cleanup cannot depend on releasing it or
    # collecting the recursive unpack closure. Array views may remain alive,
    # but their owned mappings must be closed and the per-read cache empty.
    trace = caught.value.__traceback__
    saw_reader = False
    while trace is not None:
        if trace.tb_frame.f_code is evaluation._read_result.__code__:
            saw_reader = True
            assert trace.tb_frame.f_locals['arrays'] == {}
        trace = trace.tb_next
    assert saw_reader
    assert all(record['array']() is None or record['array']()._mmap.closed
               for record in mapped_reads)


@pytest.mark.parametrize('read_fails', [False, True])
def test_mapping_close_failure_preserves_read_error_and_cleans_other_mappings(monkeypatch, read_fails):
    """A controlled close failure checks error handling, not an OS failure."""
    calls, seen = [], {}
    original = ValueError('Saved response array hash differs')

    class Mapping:
        def __init__(self, name, fail=False):
            self.name, self.fail, self.closed = name, fail, False

        def close(self):
            calls.append(self.name)
            if self.fail:
                raise OSError('controlled mapping close failure')
            self.closed = True

    first, middle, last = Mapping('first'), Mapping('middle', fail=True), Mapping('last')

    def controlled_read(path, *, verify, selection, arrays):
        seen['cache'] = arrays
        arrays.update({name: SimpleNamespace(_mmap=mapping)
                       for name, mapping in [('first', first), ('middle', middle), ('last', last)]})
        if read_fails:
            raise original
        return {'responses': {}}

    monkeypatch.setattr(evaluation, '_read_result', controlled_read)
    expected = ValueError if read_fails else OSError
    with pytest.raises(expected) as caught:
        evaluation.read_result('controlled saved-result reader')
    assert calls == ['last', 'middle', 'first']
    assert first.closed and last.closed
    assert not middle.closed
    assert seen['cache'] == {}
    if read_fails:
        assert caught.value is original
        assert any('OSError: controlled mapping close failure' in note
                   for note in caught.value.__notes__)
    else:
        assert str(caught.value) == 'controlled mapping close failure'
