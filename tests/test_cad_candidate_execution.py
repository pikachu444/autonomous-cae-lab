"""Focused candidate execution boundaries; native work is an explicit test double."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace as NS
import subprocess

import pytest

from test_cad_numerical import archive, recipe, settings
from caelab.storage import save_json
from caelab.evaluation import file_hash
from caelab.adapters import cad_analysis as module
from caelab.execution_control import ExecutionCancelled, ExecutionCleanupFailed


@pytest.mark.parametrize('failure', [None, 'prepare', 'solver', 'response', 'cancel', 'cleanup'])
def test_candidate_stage_retention_and_no_base_edit(tmp_path, monkeypatch, failure):
    source = tmp_path / 'saved' / 'base.caepre'
    saved = archive(source, recipe())
    executable = tmp_path / 'native.exe'; executable.write_bytes(b'explicit test double')
    arguments = settings()
    arguments.update(source_sha256=saved['sha256'], _native_context={
        'source': str(source), 'freecad_executable': str(executable), 'gmsh': None})
    before = source.read_bytes()
    def native(command, folder, label, **kwargs):
        assert kwargs['owned_tree'] is True
        assert '--' not in command
        editable = folder / 'prepared' / 'editable.caepre'
        editable.parent.mkdir()
        editable.write_bytes(source.read_bytes())
        snapshot = editable.parent / 'snapshot.json'
        save_json(snapshot, {'explicit_test_double': True})
        receipt = {'state': 'FAILED' if failure == 'prepare' else 'PREPARED',
            'phase': 'correspondence' if failure in ('prepare', 'cancel') else 'prepared',
            'error': 'mapped face deleted' if failure == 'prepare' else None,
            'snapshot': str(snapshot), 'editable_project': str(editable),
            'editable_sha256': file_hash(editable)}
        save_json(folder / 'candidate-preparation.json', receipt)
        if failure == 'cancel':
            raise ExecutionCancelled('explicit test cancellation')
        if failure == 'cleanup':
            raise ExecutionCleanupFailed('explicit unconfirmed process stop')
        return subprocess.CompletedProcess(command, 1 if failure == 'prepare' else 0)
    def calculate(self, settings, *, output, runtime=None):
        output.mkdir()
        return {'execution_status': 'FAILED' if failure == 'solver' else 'SUCCEEDED',
                'responses': {} if failure == 'response' else {
                    'displacement': {'kind': 'field', 'unit': 'mm', 'value': [[0, 0, -.2], [0, 0, -.1]]}},
                'diagnostics': {'reason': 'explicit solver failure'} if failure == 'solver' else {}}
    monkeypatch.setattr(module, 'run_owned_command', native)
    from caelab.adapters.frozen_fem import FrozenFemCalculixAdapter
    monkeypatch.setattr(FrozenFemCalculixAdapter, 'run', calculate)
    output = tmp_path / 'candidate'
    if failure == 'cleanup':
        with pytest.raises(ExecutionCleanupFailed):
            module.CADAnalysisAdapter().run(arguments, output=output)
        assert not (output / 'result.json').exists()
    else:
        result = module.CADAnalysisAdapter().run(arguments, output=output)
        expected = 'SUCCEEDED' if failure is None else 'CANCELLED' if failure == 'cancel' else 'FAILED'
        assert result['execution_status'] == expected
        assert result['qualification'] == 'UNKNOWN' and result['decision'] == 'NOT_RELEASED'
        if failure is None:
            assert result['responses']['uz_max']['value'] == -.1
        else:
            assert result['responses'] == {}
            assert result['diagnostics']['phase'] == {
                'prepare': 'native_prepare', 'cancel': 'native_prepare', 'solver': 'solver', 'response': 'response'}[failure]
        if failure in (None, 'solver', 'response'):
            assert (output / result['editable_design']['relative']).read_bytes() == before
        if failure in ('prepare', 'cancel'):
            assert result['candidate_preparation']['phase'] == 'correspondence'
        assert (output / 'base.caepre').read_bytes() == before
    assert source.read_bytes() == before


def test_short_native_copy_retains_identical_bytes_and_reports_failed_transfer(tmp_path, monkeypatch):
    from apps.desktop_pre import projects
    native_paths = []
    def save_copy(path):
        native_paths.append(Path(path))
        Path(path).write_bytes(b'explicit native save test double')
    monkeypatch.setattr(projects, '_native_copy_uses_short_path', lambda _: True)
    destination = tmp_path / 'deep-store' / 'model.FCStd'
    destination.parent.mkdir()
    projects.save_native_copy(NS(saveCopy=save_copy), destination)
    assert destination.read_bytes() == b'explicit native save test double'
    assert native_paths[0].name == 'model.FCStd' and not native_paths[0].exists()
    real = projects.shutil.copyfile
    monkeypatch.setattr(projects.shutil, 'copyfile', lambda *a, **k: (_ for _ in ()).throw(OSError('transfer refused')))
    with pytest.raises(OSError, match='short staging retained'):
        projects.save_native_copy(NS(saveCopy=save_copy), destination)
    assert native_paths[-1].read_bytes() == destination.read_bytes()
    monkeypatch.setattr(projects.shutil, 'copyfile', real)
    projects.shutil.rmtree(native_paths[-1].parent)


def test_freecad_portable_launcher_resolves_same_installation_bin(tmp_path, monkeypatch):
    from caelab.cad_numerical import resolve_settings
    from caelab.workbench import Workbench
    from caelab.native_inputs import register_native_input
    wb = Workbench(tmp_path / 'store')
    try:
        source = tmp_path / 'input' / 'base.caepre'
        archive(source, recipe())
        receipt = register_native_input(wb.root, source.parent, source, 'Dportable',
            root_id='public-test', relative=source.name, limit=10000000)
        install = tmp_path / '공개 FreeCAD'
        (install / 'bin').mkdir(parents=True)
        launcher = install / 'FreeCAD.exe'; launcher.write_bytes(b'launcher double')
        actual = install / 'bin' / 'FreeCAD.exe'; actual.write_bytes(b'native double')
        monkeypatch.setattr(wb.desktop, 'context', lambda: {'freecad_executable': str(launcher)})
        value = settings(); value.update(data_id=receipt['id'], source_sha256=receipt['sha256'])
        assert resolve_settings(wb, value)['_native_context']['freecad_executable'] == str(actual.resolve())
    finally:
        wb.shutdown()
