"""Retained source limits and concurrent-size changes; no solver execution."""
from pathlib import Path

import pytest

from caelab.adapters.frozen_fem import _read


def test_small_source_and_exact_limit_are_read_without_changing_bytes(tmp_path):
    source = tmp_path / 'source.bin'
    data = bytes(range(128))
    source.write_bytes(data)
    assert _read(source) == data
    assert _read(source, limit=len(data)) == data
    with pytest.raises(ValueError, match='admission size limit'):
        _read(source, limit=len(data) - 1)


@pytest.mark.parametrize('changed', [b'longer source', b'x'])
def test_size_change_during_read_is_rejected_within_the_large_allowance(tmp_path, monkeypatch, changed):
    source = tmp_path / 'source.bin'
    source.write_bytes(b'original')
    original_open = Path.open

    class ChangingRead:
        def __init__(self, stream):
            self.stream = stream

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return self.stream.__exit__(*args)

        def fileno(self):
            return self.stream.fileno()

        def read(self, size):
            with original_open(source, 'wb') as writer:
                writer.write(changed)
            return self.stream.read(size)

    def opened(path, *args, **kwargs):
        stream = original_open(path, *args, **kwargs)
        return ChangingRead(stream) if path == source and args == ('rb',) else stream

    monkeypatch.setattr(Path, 'open', opened)
    with pytest.raises(ValueError, match='Frozen source changed'):
        _read(source)
