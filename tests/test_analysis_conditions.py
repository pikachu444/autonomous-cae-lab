"""Real CAD/Core integrity with a TEST_ONLY capturing solver, never native FEA."""

from copy import deepcopy
import hashlib
from pathlib import Path
import shutil

from jsonschema.exceptions import ValidationError
import pytest

from caelab import Lab
from caelab.adapters.fixture_cadquery import FixtureCadQueryAdapter
from caelab.adapters.fixture_calculix import FixtureCalculiXAdapter
from caelab.contracts import CapabilityUnavailable
from caelab.storage import canonical_hash, load_json, save_json


class CaptureSolver(FixtureCalculiXAdapter):
    """Only execution is synthetic; real admission/projection stay in use."""
    def __init__(self):
        self.calls = []

    def solve(self, parent_result, parent_root, output, settings):
        self.calls.append(deepcopy(settings))
        output.mkdir()
        (output / 'test-only.txt').write_text('TEST_ONLY; no native solver or physical evidence')
        return {'status': 'COMPLETED', 'solver_status': 'CONVERGED', 'converged': True,
                'checks': [{'code': 'test_only_transport', 'status': 'PASS', 'observed': 'TEST_ONLY'}],
                'metrics': {}, 'pending_validations': ['static_strength'], 'provenance': {},
                'raw_result': 'simulation/test-only.txt'}


@pytest.fixture(scope='module')
def conditions_cad(tmp_path_factory):
    root = tmp_path_factory.mktemp('conditions-real-cad')
    lab = Lab(root, adapters={'fixture.cadquery': FixtureCadQueryAdapter()},
              analysis_adapters={}, model_analysis_adapters={}, pde_adapters={}, doe_adapters={}, optimization_adapters={})
    lab.create_study('S-conditions', 'CAD-bound conditions', 'What do explicit conditions change?',
                     'TEST_ONLY mechanics execution', 'Preserve the same CAD source')
    lab.register_parameter('S-conditions', 'fixture.cadquery', 'roller_support',
                           'support_width_mm', 'width', 'Width', 28, 60)
    parent = lab.run_experiment(study_id='S-conditions', experiment_id='E-cad',
                                backend='fixture.cadquery', model='roller_support', values={'width': 38})
    assert parent['status'] == 'COMPLETED_REVIEW_REQUIRED'
    return root


@pytest.fixture
def conditions_lab(conditions_cad, tmp_path):
    root = tmp_path / 'store'
    shutil.copytree(conditions_cad, root)
    lab = Lab(root, adapters={'fixture.cadquery': FixtureCadQueryAdapter()},
              analysis_adapters={'fixture.calculix': CaptureSolver()},
              model_analysis_adapters={}, pde_adapters={}, doe_adapters={}, optimization_adapters={})
    return lab


def condition_request(lab, identifier='C-conditions'):
    described = lab.describe_analysis_conditions('E-cad')
    return {'conditions_id': identifier, 'experiment_id': 'E-cad',
            'cad_revision': described['source']['cad_revision'],
            'catalog_revision': described['catalog_revision'], 'backend': 'fixture.calculix',
            'declaration': {
                'analysis_type': 'linear_static', 'units': {'length': 'mm', 'force': 'N', 'stress': 'MPa'},
                'coordinate_system': 'global',
                'materials': [{'id': 'M1', 'selection_id': 'B-final', 'law': 'isotropic_linear_elastic',
                    'young_modulus_MPa': 210000, 'poisson_ratio': .3,
                    'source': {'category': 'ASSUMED', 'description': 'Explicit TEST_ONLY isotropic assumption'}}],
                'boundary_conditions': [{'id': 'BC1', 'selection_id': 'S-base', 'type': 'displacement',
                    'components': {'UX': 0, 'UY': 0, 'UZ': 0}, 'unit': 'mm', 'coordinate_system': 'global',
                    'source': 'Whole base fixed in existing support-screen idealization'}],
                'loads': [{'id': 'L1', 'selection_id': 'S-saddle', 'type': 'resultant_force',
                    'components': {'FX': 0, 'FY': 0, 'FZ': -150}, 'unit': 'N', 'coordinate_system': 'global',
                    'source': 'TEST_ONLY declared negative global Z force'}],
                'contact': {'mode': 'none', 'source': 'One body, no modeled contact'},
                'mesh': {'mode': 'selected', 'max_size_mm': 4}}}


def test_conditions_preserve_declared_vectors_and_frozen_child_snapshot(conditions_lab):
    lab = conditions_lab
    original = (lab.store / 'experiments/E-cad/result.json').read_bytes()
    request = condition_request(lab)
    catalog = lab.describe_analysis_conditions('E-cad')['catalog']
    assert {x['id'] for x in catalog['selections']} == {'B-final', 'S-base', 'S-saddle'}
    assert catalog['coordinate_systems'][0]['basis'] == [[1, 0, 0], [0, 1, 0], [0, 0, 1]]
    saved = lab.save_analysis_conditions(**request)
    assert saved['support']['status'] == 'SUPPORTED_DECLARED_INPUTS'
    assert saved['support']['native_runtime'] == 'NOT_CHECKED'
    assert saved['engineering'] == 'UNKNOWN' and saved['decision'] == 'NOT_RELEASED'
    assert saved['adapter_binding']['settings']['load']['force_per_support_N'] == 150
    assert saved['adapter_binding']['settings']['material']['qualification'] == 'USER_DECLARED_UNVERIFIED'
    assert lab.inspect_analysis_conditions(saved['id']) == saved
    assert lab.list_analysis_conditions('E-cad') == [{'record': saved, 'integrity': 'VERIFIED'}]
    child = lab.run_analysis(parent_experiment_id='E-cad', experiment_id='E-analysis',
                              backend='fixture.calculix', conditions_id=saved['id'])
    proposal = load_json(lab.store / 'experiments/E-analysis/proposal.json')
    assert proposal['loads'] == request['declaration']['loads']
    assert proposal['boundary_conditions'] == request['declaration']['boundary_conditions']
    assert proposal['model']['materials'] == request['declaration']['materials']
    assert lab.analysis_adapters['fixture.calculix'].calls == [saved['adapter_binding']['settings']]
    assert (lab.store / 'experiments/E-cad/result.json').read_bytes() == original
    assert child['decision'] == 'NOT_RELEASED'
    assert lab.inspect_experiment('E-analysis') == child
    # The immutable child has its own record and never requires a mutable listing namespace.
    shutil.rmtree(lab.store / 'analysis_conditions')
    assert lab.inspect_experiment('E-analysis') == child
    (lab.store / 'experiments/E-analysis/analysis_conditions.json').write_bytes(b'corrupt')
    with pytest.raises(ValueError, match='Artifact hash mismatch'):
        lab.inspect_experiment('E-analysis')


@pytest.mark.parametrize('field,value', [('cad_revision', '0' * 64), ('catalog_revision', '0' * 64)])
def test_stale_revision_never_creates_record(conditions_lab, field, value):
    request = condition_request(conditions_lab)
    request[field] = value
    with pytest.raises(ValueError, match='revision changed'):
        conditions_lab.save_analysis_conditions(**request)
    assert not (conditions_lab.store / 'analysis_conditions').exists()


@pytest.mark.parametrize('change', [
    ('loads', 'unit', 'kN'), ('loads', 'coordinate_system', 'local'),
    ('loads', 'selection_id', 'Face-unknown'), ('loads', 'source', '   '),
    ('boundary_conditions', 'selection_id', 'S-saddle'),
    ('materials', 'selection_id', 'S-base'), ('materials', 'young_modulus_MPa', 0),
    ('materials', 'young_modulus_MPa', True), ('materials', 'poisson_ratio', .5)])
def test_invalid_declarations_block_storage_and_downstream(conditions_lab, change):
    request = condition_request(conditions_lab)
    group, key, value = change
    request['declaration'][group][0][key] = value
    with pytest.raises((ValueError, ValidationError)):
        conditions_lab.save_analysis_conditions(**request)
    assert not (conditions_lab.store / 'analysis_conditions').exists()
    assert not conditions_lab.analysis_adapters['fixture.calculix'].calls


@pytest.mark.parametrize('value', [float('nan'), float('inf'), True])
def test_nonfinite_or_boolean_force_is_not_a_numeric_condition(conditions_lab, value):
    request = condition_request(conditions_lab)
    request['declaration']['loads'][0]['components']['FZ'] = value
    with pytest.raises((ValueError, ValidationError)):
        conditions_lab.save_analysis_conditions(**request)


@pytest.mark.parametrize('target,component,value', [
    ('loads', 'FX', 1), ('loads', 'FZ', 0), ('loads', 'FZ', 150),
    ('boundary_conditions', 'UZ', .1)])
def test_valid_but_unsupported_vectors_are_preserved_and_never_executed(conditions_lab, target, component, value):
    request = condition_request(conditions_lab)
    request['declaration'][target][0]['components'][component] = value
    saved = conditions_lab.save_analysis_conditions(**request)
    assert saved['request'] == request
    assert saved['support']['status'] == 'UNSUPPORTED_FOR_CONDITIONS'
    assert saved['adapter_binding'] is None
    with pytest.raises(CapabilityUnavailable):
        conditions_lab.run_analysis(parent_experiment_id='E-cad', experiment_id='E-refused',
                                    backend='fixture.calculix', conditions_id=saved['id'])
    assert not (conditions_lab.store / 'experiments/E-refused').exists()
    assert not conditions_lab.analysis_adapters['fixture.calculix'].calls


@pytest.mark.parametrize('components', [
    {'UX': 0}, {'UY': 0}, {'UZ': 0},
    {'UX': 0, 'UY': 0}, {'UX': 0, 'UZ': 0}, {'UY': 0, 'UZ': 0}])
def test_fixture_partial_constraints_are_preserved_without_silent_fixity(conditions_lab, components):
    request = condition_request(conditions_lab)
    request['declaration']['boundary_conditions'][0]['components'] = components
    saved = conditions_lab.save_analysis_conditions(**request)
    assert saved['request'] == request
    assert saved['support']['status'] == 'UNSUPPORTED_FOR_CONDITIONS'
    assert saved['adapter_binding'] is None
    assert conditions_lab.inspect_analysis_conditions(saved['id']) == saved
    with pytest.raises(CapabilityUnavailable):
        conditions_lab.run_analysis(parent_experiment_id='E-cad', experiment_id='E-refused',
                                    backend='fixture.calculix', conditions_id=saved['id'])
    assert not (conditions_lab.store / 'experiments/E-refused').exists()
    assert not conditions_lab.analysis_adapters['fixture.calculix'].calls


def test_foreign_model_uses_unsupported_admission_without_syntax_bypass(conditions_lab, monkeypatch):
    lab = conditions_lab
    hook = lab.adapters['fixture.cadquery'].conditions_catalog
    def imported(*args):
        catalog = hook(*args)
        catalog.update(cad_backend='fixture.freecad', model='TEST_ONLY imported final solid')
        catalog['selections'] = catalog['selections'][:1]
        return catalog
    monkeypatch.setattr(lab.adapters['fixture.cadquery'], 'conditions_catalog', imported)
    request = condition_request(lab)
    for group in ('boundary_conditions', 'loads'):
        request['declaration'][group][0]['selection_id'] = 'B-final'
    saved = lab.save_analysis_conditions(**request)
    assert saved['support']['status'] == 'UNSUPPORTED_FOR_MODEL'
    assert lab.inspect_analysis_conditions(saved['id']) == saved
    with pytest.raises(CapabilityUnavailable):
        lab.run_analysis(parent_experiment_id='E-cad', experiment_id='E-refused',
                          backend='fixture.calculix', conditions_id=saved['id'])
    assert not lab.analysis_adapters['fixture.calculix'].calls


@pytest.mark.parametrize('mode', ['duplicate', 'source', 'record', 'receipt', 'policy', 'competing', 'parent', 'backend'])
def test_immutable_source_binding_and_identity_refusals(conditions_lab, monkeypatch, mode):
    lab = conditions_lab
    saved = lab.save_analysis_conditions(**condition_request(lab))
    record = lab.store / 'analysis_conditions/C-conditions/record.json'
    receipt = record.with_name('receipt.json')
    arguments = {'parent_experiment_id': 'E-cad', 'experiment_id': 'E-refused',
                 'backend': 'fixture.calculix', 'conditions_id': saved['id']}
    if mode == 'duplicate':
        original = record.read_bytes()
        with pytest.raises(FileExistsError):
            lab.save_analysis_conditions(**condition_request(lab))
        assert record.read_bytes() == original
        return
    if mode == 'source':
        (lab.store / 'experiments/E-cad/cad/result.json').write_text('changed')
    elif mode == 'record':
        record.write_text('{}')
    elif mode == 'receipt':
        receipt.unlink()
    elif mode == 'policy':
        monkeypatch.setattr(lab.analysis_adapters['fixture.calculix'], 'conditions_policy_identity',
                            lambda: {'changed_policy.py': '0' * 64})
    elif mode == 'competing':
        arguments['settings'] = saved['adapter_binding']['settings']
    elif mode == 'parent':
        arguments['parent_experiment_id'] = 'E-other'
    elif mode == 'backend':
        arguments['backend'] = 'missing.solver'
    with pytest.raises((ValueError, FileNotFoundError, ValidationError)):
        lab.run_analysis(**arguments)
    assert not (lab.store / 'experiments/E-refused').exists()
    assert not lab.analysis_adapters['fixture.calculix'].calls


def test_late_source_change_cannot_persist_a_stale_declaration(conditions_lab, monkeypatch):
    import caelab.analysis_conditions as module
    lab = conditions_lab
    request = condition_request(lab)
    original = module._parent
    calls = []
    def changed(*args):
        source, catalog = original(*args)
        calls.append(True)
        if len(calls) == 2:
            source = {**source, 'result_sha256': '0' * 64}
        return source, catalog
    monkeypatch.setattr(module, '_parent', changed)
    with pytest.raises(ValueError, match='before persistence'):
        lab.save_analysis_conditions(**request)
    assert not (lab.store / 'analysis_conditions').exists()


@pytest.mark.parametrize('path', ['analysis_conditions', 'experiments'])
def test_symlink_namespace_cannot_redirect_storage_or_execution(conditions_lab, tmp_path, path):
    lab = conditions_lab
    request = condition_request(lab)
    if path == 'experiments':
        saved = lab.save_analysis_conditions(**request)
        outside = tmp_path / 'outside'
        shutil.move(lab.store / path, outside)
    else:
        outside = tmp_path / 'outside'
        outside.mkdir()
    try:
        (lab.store / path).symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip('Host does not permit symlinks')
    with pytest.raises(ValueError):
        if path == 'analysis_conditions':
            lab.save_analysis_conditions(**request)
        else:
            lab.run_analysis(parent_experiment_id='E-cad', experiment_id='E-refused',
                              backend='fixture.calculix', conditions_id=saved['id'])
    assert not (outside / 'C-conditions').exists()
    assert not (outside / 'E-refused').exists()


def test_corrupt_record_listing_is_unknown_and_not_an_executable_payload(conditions_lab):
    lab = conditions_lab
    lab.save_analysis_conditions(**condition_request(lab))
    path = lab.store / 'analysis_conditions/C-conditions/record.json'
    path.write_bytes(path.read_bytes() + b'\n')
    rows = lab.list_analysis_conditions('E-cad')
    assert len(rows) == 1 and rows[0]['integrity'] == 'UNKNOWN'
    assert 'record' not in rows[0]


def test_snapshot_self_consistency_refuses_altered_projected_settings(conditions_lab):
    lab = conditions_lab
    lab.save_analysis_conditions(**condition_request(lab))
    result = lab.run_analysis(parent_experiment_id='E-cad', experiment_id='E-analysis',
                              backend='fixture.calculix', conditions_id='C-conditions')
    folder = lab.store / 'experiments/E-analysis'
    from caelab.analysis_conditions import verify_child
    proposal = load_json(folder / 'proposal.json')
    proposal['execution']['load']['force_per_support_N'] = 100
    save_json(folder / 'proposal.json', proposal)
    with pytest.raises(ValueError, match='projected settings mismatch'):
        verify_child(folder, result)


def test_cli_conditions_and_legacy_settings_are_mutually_exclusive():
    from caelab.cli import parser
    assert parser().parse_args(['conditions', 'describe', 'E-cad']).action == 'describe'
    args = parser().parse_args(['solve', '--parent', 'E-cad', '--experiment', 'E-child', '--conditions', 'C-one'])
    assert args.conditions == 'C-one' and args.settings is None
    with pytest.raises(SystemExit):
        parser().parse_args(['solve', '--parent', 'E-cad', '--experiment', 'E-child',
                            '--conditions', 'C-one', '--settings', '{}'])
