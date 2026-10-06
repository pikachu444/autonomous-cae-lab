"""Core lifecycle uses actual owned Python children, never CAE physics fixtures."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sys
import time

import pytest

from caelab import Lab
from caelab.execution_control import (CancellationToken, ExecutionCleanupFailed,
                                     cancellation_scope, run_owned_command)


class OwnedAnalysis:
    backend = 'test.owned'
    version = 'TEST_ONLY'
    domain = 'test'
    physics_domain = 'TEST_ONLY_PROCESS'
    analysis_type = 'TEST_ONLY_PROCESS_LIFETIME'
    default_metrics = ['response']

    def solve(self, parent, parent_root, output, settings):
        owned_child(output)


class OwnedModel(OwnedAnalysis):
    def solve(self, output, settings):
        owned_child(output)


def owned_child(output):
    output.mkdir(parents=True)
    command = "from pathlib import Path; import time; print('TEST_ONLY partial native output',flush=True); Path('entered').touch(); time.sleep(30)"
    run_owned_command([sys.executable, '-u', '-c', command], output, 'native')
    pytest.fail('This lifecycle fixture must be cancelled before its child completes')


def lab_with_parent(tmp_path):
    lab = Lab(tmp_path, analysis_adapters={OwnedAnalysis.backend: OwnedAnalysis()},
              model_analysis_adapters={OwnedModel.backend: OwnedModel()},
              pde_adapters={OwnedModel.backend: OwnedModel()})
    lab.create_study('S-cancel', 'TEST_ONLY cancellation', 'Retain inputs and actual partial output',
                     'Cancellation is distinct from numerical failure', 'No physical verdict')
    lab.register_parameter('S-cancel', 'fixture.cadquery', 'roller_support',
                           'support_width_mm', 'width', 'Width', 28, 60)
    lab.run_experiment(study_id='S-cancel', experiment_id='E-parent',
                       backend='fixture.cadquery', model='roller_support', values={'width': 38})
    return lab


@pytest.mark.parametrize('family,output_directory', [('analysis', 'simulation'), ('model', 'simulation'), ('pde', 'pde'), ('cad', 'cad')])
def test_actual_owned_cancellation_is_readable_without_failure_or_completed_metrics(tmp_path, family, output_directory, monkeypatch):
    lab = lab_with_parent(tmp_path)
    parent_root = tmp_path / 'experiments/E-parent'
    before = {path.relative_to(parent_root): path.read_bytes() for path in parent_root.rglob('*') if path.is_file()}
    identifier = 'E-cancel-' + family
    output = tmp_path / 'experiments' / identifier / output_directory
    token = CancellationToken()
    if family == 'cad':
        monkeypatch.setattr(lab.adapters['fixture.cadquery'], 'regenerate',
                            lambda _model, _values, folder: owned_child(folder))
    def execute():
        with cancellation_scope(token):
            if family == 'analysis':
                return lab.run_analysis(parent_experiment_id='E-parent', experiment_id=identifier,
                                        backend=OwnedAnalysis.backend, settings={})
            if family == 'cad':
                return lab.run_experiment(study_id='S-cancel', experiment_id=identifier,
                                          backend='fixture.cadquery', model='roller_support', values={'width': 40})
            operation = lab.run_model_analysis if family == 'model' else lab.run_pde
            return operation(study_id='S-cancel', experiment_id=identifier, backend=OwnedModel.backend, settings={})
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(execute)
        deadline = time.monotonic() + 15
        while not (output / 'entered').exists():
            if future.done():
                future.result()
            assert time.monotonic() < deadline
            time.sleep(.01)
        token.request()
        result = future.result(timeout=10)
    assert result['status'] == 'CANCELLED' and result['decision'] == 'NOT_RELEASED'
    assert result['solver_status'] == ('NOT_RUN' if family == 'cad' else 'CANCELLED')
    assert result['converged'] is None and result['metrics'] == {}
    assert not any(item['status'] == 'FAIL' for item in result['validations'])
    assert {'model_qualification', 'physical_validation'} <= {v['type'] for v in result['validations'] if v['status'] == 'UNKNOWN'}
    assert token.observed and not token.cleanup_pending
    native = json.loads((output / 'native.execution.json').read_text())
    assert native['status'] == 'CANCELLED' and native['return_code'] is not None
    assert 'TEST_ONLY partial native output' in (output / 'native.stdout.log').read_text()
    assert lab.inspect_experiment(identifier) == result
    assert any(a['path'] == 'execution.json' for a in result['artifacts'])
    assert {path.relative_to(parent_root): path.read_bytes() for path in parent_root.rglob('*') if path.is_file()} == before
    if family == 'analysis':
        with pytest.raises(ValueError, match='parent|CAD|completed|review'):
            lab.run_analysis(parent_experiment_id=identifier, experiment_id='E-invalid-parent',
                             backend=OwnedAnalysis.backend, settings={})


@pytest.mark.parametrize('family', ['analysis', 'model', 'pde', 'cad'])
def test_unconfirmed_cleanup_never_seals_mutable_partial_output(tmp_path, family, monkeypatch):
    lab = lab_with_parent(tmp_path)
    def unconfirmed(*args):
        output = args[-2] if family == 'analysis' else args[0]
        if family == 'cad':
            output = args[-1]
        output.mkdir(parents=True)
        (output / 'partial.log').write_text('TEST_ONLY unconfirmed cleanup; no child launched')
        raise ExecutionCleanupFailed('TEST_ONLY owned cleanup remains unknown')
    if family == 'analysis':
        monkeypatch.setattr(lab.analysis_adapters[OwnedAnalysis.backend], 'solve', unconfirmed)
        call = lambda: lab.run_analysis(parent_experiment_id='E-parent', experiment_id='E-pending', backend=OwnedAnalysis.backend, settings={})
    elif family == 'cad':
        monkeypatch.setattr(lab.adapters['fixture.cadquery'], 'regenerate', unconfirmed)
        call = lambda: lab.run_experiment(study_id='S-cancel', experiment_id='E-pending', backend='fixture.cadquery', model='roller_support', values={'width': 40})
    else:
        mapping = lab.model_analysis_adapters if family == 'model' else lab.pde_adapters
        monkeypatch.setattr(mapping[OwnedModel.backend], 'solve', unconfirmed)
        operation = lab.run_model_analysis if family == 'model' else lab.run_pde
        call = lambda: operation(study_id='S-cancel', experiment_id='E-pending', backend=OwnedModel.backend, settings={})
    with pytest.raises(ExecutionCleanupFailed):
        call()
    folder = tmp_path / 'experiments/E-pending'
    assert (folder / 'proposal.json').is_file()
    assert not (folder / 'result.json').exists() and not (folder / 'thread.json').exists()
    assert not (tmp_path / 'ledger/E-pending.json').exists()
