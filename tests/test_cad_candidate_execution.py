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
    def partial_copy(source, target):
        Path(target).write_bytes(b'truncated new draft')
        raise OSError('transfer refused')
    monkeypatch.setattr(projects.shutil, 'copyfile', partial_copy)
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



def test_exact_successful_candidate_branch_survives_plan_reopen(tmp_path, monkeypatch):
    """Real owners/DOE/retention with an explicit saved-model evaluator double."""
    import time
    from caelab.workbench import Workbench
    from caelab.numerical_document import request_draft
    from caelab.native_inputs import register_native_input
    from caelab.cad_numerical import open_candidate
    from caelab.jobs import TERMINAL
    wb = Workbench(tmp_path / 'store')
    captured = []
    try:
        source = tmp_path / 'base' / 'model.caepre'; archive(source, recipe())
        base_bytes = source.read_bytes()
        registered = register_native_input(wb.root, source.parent, source, 'Dbase',
            root_id='test-model', relative=source.name, limit=10000000)
        arguments = settings(); arguments.update(data_id=registered['id'], source_sha256=registered['sha256'])
        def evaluate(self, settings, *, output, runtime=None):
            output = Path(output)
            output.mkdir(parents=True, exist_ok=True)
            selected = deepcopy(settings['recipe'])
            selected['variables'][0]['value'] = settings['values']['width']
            model = output / 'editable.caepre'; archive(model, selected)
            captured.append((settings['values']['width'], model.read_bytes()))
            success = len(captured) > 1
            return {'execution_status': 'SUCCEEDED' if success else 'FAILED',
                'responses': {'uz_max': {'kind': 'scalar', 'value': settings['values']['width'] * 10,
                    'unit': 'mm', 'reduction': 'max'}} if success else {},
                'diagnostics': {'scope': 'explicit saved-model test double'},
                'editable_design': {'relative': model.name, 'sha256': file_hash(model), 'bytes': model.stat().st_size,
                    'calculated': success, 'base_data_id': registered['id'], 'base_sha256': registered['sha256']},
                'artifacts': [{'path': p.relative_to(output).as_posix(), 'sha256': file_hash(p)}
                              for p in output.iterdir() if p.is_file()]}
        monkeypatch.setattr(module.CADAnalysisAdapter, 'run', evaluate)
        inputs = {'backend': module.BACKEND, 'settings': arguments,
            'variables': [{'id': 'width', 'value': .02, 'unit': 'm', 'lower': .01, 'upper': .03}],
            'count': 2, 'seed': 0, 'responses': ['uz_max'],
            'execution': {'mode': 'serial', 'workers': 1, 'on_failure': 'continue'}}
        plan = wb.document_open(kind='numerical', title='CAD study',
            draft=request_draft({'purpose': 'Two retained candidates', 'operation': 'doe',
                                 'inputs': inputs, 'budget': {'evaluations': 2}}))
        submitted = wb.numerical_documents.command(plan['id'], 'numerical.run', {},
            session_id=wb.session_id, expected_generation=plan['generation'])
        job = submitted['job']['id']
        deadline = time.monotonic() + 15
        while wb.manager.status(job)['state'] not in TERMINAL and time.monotonic() < deadline:
            time.sleep(.01)
        assert wb.manager.status(job)['state'] in TERMINAL, wb.manager.status(job)
        result = wb.document_result(plan['id'], job)
        rows = result['candidates']
        assert len(rows) == len(captured) == 2
        failed = next(row for row in rows if row['execution_status'] == 'FAILED')
        successful = next(row for row in rows if row['execution_status'] == 'SUCCEEDED')
        assert failed['responses'] == {}
        assert successful['responses']['uz_max']['value'] == successful['values']['width'] * 10
        with pytest.raises(ValueError, match='successful'):
            open_candidate(wb, plan['id'], job, failed['candidate_id'], 0)
        current = wb.numerical_documents.read(plan['id'])
        wb.numerical_documents.command(plan['id'], 'document.save', {},
            session_id=wb.session_id, expected_generation=current['generation'])
        assert source.read_bytes() == base_bytes
        expected = next(data for value, data in captured if value == successful['values']['width'])
        store = wb.root
    finally:
        wb.shutdown()
    # A fresh service owner follows the saved result, not a live base document.
    wb = Workbench(store)
    try:
        restored = wb.document_open(kind='numerical', document_id=plan['id'])
        assert restored['draft']['request']['inputs'] == inputs
        registered_design = open_candidate(wb, plan['id'], job, successful['candidate_id'], 0)
        receipt = wb.native_input(registered_design['input_id'])
        assert Path(receipt['path']).read_bytes() == expected
        assert receipt['candidate_branch']['candidate_id'] == successful['candidate_id']
        assert registered_design['calculation_performed'] is False
        assert len(wb.manager.list()) == 1
    finally:
        wb.shutdown()



def test_cleanup_without_caller_scope_keeps_same_live_retry_owner():
    from caelab.execution_control import stop_owned_process
    state = {'refuse': True, 'closed': False}
    def terminate():
        if state['refuse']:
            raise OSError('explicit query/termination refusal')
    job = NS(terminate=terminate, active=lambda: 0,
             close=lambda: state.update(closed=True))
    process = NS(pid=123, returncode=None, stdin=None, _caelab_windows_job=job,
                 poll=lambda: None, kill=lambda: None, wait=lambda **kw: 0)
    with pytest.raises(ExecutionCleanupFailed) as caught:
        stop_owned_process(process, isolated_group=False)
    token = caught.value.cleanup_token
    assert token.cleanup_pending and process._caelab_windows_job is job and not state['closed']
    state['refuse'] = False
    assert not token.retry_cleanup(1)
    assert state['closed'] and process._caelab_windows_job is None


def test_short_workspace_moves_receipt_paths_without_rewriting_frozen_bytes(tmp_path):
    from caelab.storage import load_json
    native = tmp_path / 'short'; native.mkdir()
    retained = tmp_path / 'store' / 'candidate'; retained.mkdir(parents=True)
    frozen = native / 'exchange' / 'Pcandidate' / 'Finput'; frozen.mkdir(parents=True)
    snapshot = frozen / 'snapshot.json'; snapshot.write_bytes(b'{"files":[],"kind":"test double"}')
    editable = frozen / 'editable.caepre'; editable.write_bytes(b'unchanged archived native bytes')
    mesh = native / 'meshes' / 'Mesh'; mesh.mkdir(parents=True)
    (mesh / 'shape2mesh.geo').write_text('explicit test fixture', encoding='utf-8')
    original = {p.relative_to(native).as_posix(): p.read_bytes() for p in native.rglob('*') if p.is_file()}
    save_json(native / 'candidate-preparation.json', {'state': 'PREPARED',
        'snapshot': str(snapshot), 'editable_project': str(editable), 'editable_sha256': file_hash(editable),
        'mesh_directories': [str(mesh)]})
    raw_receipt = (native / 'candidate-preparation.json').read_bytes()
    module._retain_workspace(retained, native)
    assert not native.exists()
    restored = load_json(retained / 'candidate-preparation.json')
    assert Path(restored['snapshot']).is_relative_to(retained / 'native')
    assert Path(restored['editable_project']).read_bytes() == original['exchange/Pcandidate/Finput/editable.caepre']
    assert (retained / 'native' / 'candidate-preparation.json').read_bytes() == raw_receipt
    for relative, content in original.items():
        assert (retained / 'native' / relative).read_bytes() == content
    assert load_json(retained / 'native-workspace.json')['state'] == 'RETAINED'



from test_pre_fem_edit import native  # Existing native-shaped fixture, no application launch.


def test_meshing_validation_never_checks_the_live_shape(native, monkeypatch):
    from test_pre_fem_edit import Shape
    from apps.desktop_pre.fem_edit import FEMEditor, _target
    before = _target(native.shape, ['Face1'])
    def cache_changing_check(shape):
        shape.brep += ':native validation cache flag'
        return True
    monkeypatch.setattr(Shape, 'isValid', cache_changing_check)
    editor = FEMEditor(native)
    editor._generate(native.mesh)
    assert _target(native.shape, ['Face1']) == before
    assert native.tools[-1].calls == ['prepare', 'compute']
