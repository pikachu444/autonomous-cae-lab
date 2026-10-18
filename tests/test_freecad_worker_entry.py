"""FreeCAD's non-main script naming must still enter exactly the trusted worker."""
import importlib.util
from pathlib import Path
import runpy

import pytest


ENTRY = Path(__file__).resolve().parents[1] / 'caelab/adapters/freecad_worker_entry.py'


def load_entry(*, with_file=True):
    spec = importlib.util.spec_from_file_location('freecad_worker_entry', ENTRY)
    module = importlib.util.module_from_spec(spec)
    if not with_file:
        del module.__file__
    spec.loader.exec_module(module)


@pytest.mark.parametrize('relative', ['caelab/adapters/freecad_parameter_worker.py',
                                     'plugins/fixture_design/upstream/fixturelab/freecad_worker.py'])
def test_non_main_freecad_entry_runs_trusted_worker_as_main(monkeypatch, relative):
    worker = ENTRY.parents[2] / relative
    monkeypatch.setenv('CAELAB_FREECAD_PARAMETER_WORKER', str(worker))
    calls = []
    monkeypatch.setattr(runpy, 'run_path', lambda *args, **kwargs: calls.append((args, kwargs)))
    load_entry()
    assert calls == [((str(worker.resolve()),), {'run_name': '__main__'})]


def test_entry_rejects_a_same_named_worker_outside_product(monkeypatch, tmp_path):
    worker = tmp_path / 'freecad_parameter_worker.py'
    worker.write_text('raise AssertionError("untrusted code")', encoding='utf-8')
    monkeypatch.setenv('CAELAB_FREECAD_PARAMETER_WORKER', str(worker))
    monkeypatch.setattr(runpy, 'run_path', lambda *_a, **_k: pytest.fail('Untrusted worker executed'))
    with pytest.raises(RuntimeError, match='NATIVE_WORKER_ENTRY_INVALID'):
        load_entry()


def test_console_wrapper_without_file_uses_the_child_only_fixed_entry(monkeypatch):
    worker = ENTRY.with_name('freecad_parameter_worker.py')
    monkeypatch.setenv('CAELAB_FREECAD_WORKER_ENTRY', str(ENTRY))
    monkeypatch.setenv('CAELAB_FREECAD_PARAMETER_WORKER', str(worker))
    calls = []
    monkeypatch.setattr(runpy, 'run_path', lambda *args, **kwargs: calls.append((args, kwargs)))
    load_entry(with_file=False)
    assert calls == [((str(worker.resolve()),), {'run_name': '__main__'})]
