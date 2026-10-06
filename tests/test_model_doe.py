"""Real seeded SciPy sampling with analytical TEST ONLY observations.

No native CAD or solver is executed. Synthetic Core identity is explicit so
parallel source writers cannot change a test's declared execution context.
"""
from copy import deepcopy
import hashlib
from pathlib import Path
import shutil

import pytest

from caelab import Lab, analysis_conditions, condition_parameters, declared_model, engine, model_doe, model_parameters
from caelab.adapters.native_structural import NativeStructuralAdapter
from caelab.contracts import Candidate, CapabilityUnavailable, Outcome
from caelab.optimizers.scipy_lhs import ScipyLatinHypercube
from caelab.schema import validate as validate_schema
from caelab.storage import canonical_hash, load_json, save_json
from test_analysis_conditions import condition_request
from test_fixed_cad_optimization import TestCatalogCAD, TestResponse, register as register_condition
from test_model_parameters import STUDY, SyntheticParameterizedModel, register_x, synthetic_lab, template_settings


CAMPAIGN = 'C-model-doe'
FIXED = 'C-fixed-doe'


@pytest.fixture(autouse=True)
def controlled_core_identity(monkeypatch):
    identity = {'core_commit': 'TEST_ONLY_NO_NATIVE', 'core_dirty': True, 'core_source_sha256': 'a' * 64}
    for module in (model_doe, model_parameters, condition_parameters, declared_model, engine, analysis_conditions):
        monkeypatch.setattr(module, 'source_identity', lambda root: deepcopy(identity))
    for module in (model_parameters, condition_parameters):
        monkeypatch.setattr(module, 'core_source_hash', lambda root: identity['core_source_sha256'])
    return identity


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _files(folder):
    return {p.relative_to(folder).as_posix(): p.read_bytes() for p in folder.rglob('*')
            if p.is_file() and not p.name.endswith('.lock')}


def _lab(path, adapter=None, *, two=False):
    lab, adapter = synthetic_lab(path, adapter)
    lab.doe_adapters = {model_doe.ENGINE: ScipyLatinHypercube()}
    register_x(lab)
    if two:
        lab.register_model_parameter(STUDY, adapter.backend, template_settings(), 'input_y',
                                     'research_y', 'Research Y', 0.0, 4.0)
    return lab, adapter


def _plan(lab, **changes):
    args = {'study_id': STUDY, 'campaign_id': CAMPAIGN, 'backend': SyntheticParameterizedModel.backend,
            'settings': template_settings(), 'parameter_ids': ['research_x'], 'sample_count': 4, 'seed': 13,
            'required_validations': {'model': ['synthetic_check']}}
    args.update(changes)
    return model_doe.plan_model_doe(lab, **args)


class SyntheticRetainedCAD(TestCatalogCAD):
    """TEST ONLY parent/manifest; no CadQuery, FreeCAD or geometry generation."""

    def document_id(self, model):
        return 'TEST_ONLY_retained_model'

    def discover(self, model):
        return [Candidate(native={'backend': self.backend, 'document': self.document_id(model),
                                  'object': model, 'path': 'support_width_mm'},
                          label='TEST ONLY parent width', unit='mm', value=38, lower=28, upper=60,
                          source_sha256='4' * 64)]

    def probe_effect(self, model, candidate, lower, upper):
        return {'status': 'PASS', 'method': 'TEST ONLY declared binding, no native geometry',
                'source_sha256': '4' * 64}

    def preflight_effects(self, model, native_values):
        return []

    def regenerate(self, model, native_values, output):
        output.mkdir()
        save_json(output / 'input.json', {'model': model, 'parameters': native_values})
        save_json(output / 'result.json', {'cad_generated': True, 'decision': 'REVIEW_REQUIRED', 'model': model,
                  'parameters': native_values, 'bom': [{'part': 'TEST_ONLY', 'volume_mm3': 1000}]})
        (output / 'native.step').write_text('TEST ONLY placeholder; never consumed by a native solver')
        return Outcome(decision='REVIEW_REQUIRED', generated=True, checks=[],
                       metrics={'cad_volume': {'value': 1000, 'unit': 'mm^3', 'valid': True}},
                       pending_validations=['physical_validation'], native_revision='4' * 64,
                       source_sha256='4' * 64, raw_result='cad/result.json')

    @staticmethod
    def source_commit():
        return 'TEST_ONLY'

    @staticmethod
    def source_fingerprint():
        return {'test_only': True, 'source_sha256': _sha(Path(__file__))}


@pytest.fixture
def fixed_lab(tmp_path, monkeypatch):
    cad = SyntheticRetainedCAD()
    lab = Lab(tmp_path / 'fixed', adapters={cad.backend: cad},
              analysis_adapters={NativeStructuralAdapter.backend: TestResponse()}, model_analysis_adapters={},
              pde_adapters={}, optimization_adapters={}, doe_adapters={model_doe.ENGINE: ScipyLatinHypercube()})
    lab.create_study('S-conditions', 'TEST ONLY retained CAD', 'Do scalar scenarios preserve one parent?',
                     'TEST ONLY bookkeeping', 'No physical qualification')
    lab.register_parameter('S-conditions', cad.backend, 'roller_support', 'support_width_mm', 'width', 'Width', 28, 60)
    parent = lab.run_experiment(study_id='S-conditions', experiment_id='E-cad', backend=cad.backend,
                                model='roller_support', values={'width': 38})
    assert parent['status'] == 'COMPLETED_REVIEW_REQUIRED'
    request = condition_request(lab)
    request['backend'] = NativeStructuralAdapter.backend
    lab.save_analysis_conditions(**request)
    register_condition(lab)
    monkeypatch.setattr(cad, 'regenerate', lambda *args: pytest.fail('DOE must never regenerate fixed CAD'))
    return lab


def _fixed_plan(lab, **changes):
    args = {'study_id': 'S-conditions', 'campaign_id': FIXED, 'conditions_id': 'C-conditions',
            'parameter_ids': ['elastic_E'], 'sample_count': 4, 'seed': 13,
            'required_validations': {'cad': [], 'analysis': ['test_only_response']}}
    args.update(changes)
    return model_doe.plan_condition_doe(lab, **args)


def test_seeded_model_doe_retains_exact_context_native_ids_and_original_metrics(tmp_path):
    lab, adapter = _lab(tmp_path, two=True)
    settings = template_settings()
    plan = _plan(lab, settings=settings, parameter_ids=['research_y', 'research_x'], sample_count=8)
    settings['load']['force'] = 999
    assert adapter.calls == 0 and not (lab.store / 'experiments').exists()
    assert plan['objective'] is None and plan['constraints'] == []
    assert plan['algorithm']['engine'] == model_doe.ENGINE
    assert plan['algorithm']['strength'] == 1 and plan['algorithm']['optimization'] is None
    assert not {'initial_population', 'population_size', 'constraint_count', 'max_generations'} & set(plan['algorithm'])
    validate_schema('model-doe-plan', plan)
    result = model_doe.run_doe(lab, CAMPAIGN)
    validate_schema('model-doe-result', result)
    assert result['route'] == 'model_analysis' and result['algorithm'] == plan['algorithm']
    assert not {'incumbent', 'termination', 'evaluations'} & set(result)
    assert len(result['samples']) == 8 and any(r['status'] == 'REJECTED' for r in result['samples'])
    for row, frozen in zip(result['samples'], plan['samples']):
        assert all(row[k] == v for k, v in frozen.items())
        assert row['model_experiment_id'] == f"E-{CAMPAIGN}-{row['index']:04d}"
        assert not {'cad_experiment_id', 'analysis_experiment_id', 'feedback', 'objective'} & set(row)
        folder = lab.store / 'experiments' / row['model_experiment_id']
        native = lab.inspect_experiment(row['model_experiment_id'])
        proposal, thread = load_json(folder / 'proposal.json'), load_json(folder / 'thread.json')
        assert proposal['objectives'] == proposal['constraints'] == []
        assert proposal['execution'] == row['model_settings']
        assert native['campaign_id'] == proposal['campaign_id'] == thread['campaign'] == CAMPAIGN
        assert native['cad_revision'] is None and 'parent_experiment_id' not in proposal
        assert native['input_parameters'] == row['values']
        assert row['model_result_sha256'] == _sha(folder / 'result.json')
        assert row['metrics'] == {'model': native['metrics']}
        assert row['model_revision'] == native['model_revision'] == thread['model_revision']
        assert type(row['model_settings']['mesh']['cell_count']) is int
        assert type(row['model_settings']['flags']['audit']) is bool
        assert row['model_settings']['load'] == template_settings()['load']
        assert row['decision'] == native['decision'] == result['decision'] == 'NOT_RELEASED'
        if row['usable']:
            x, y = row['values']['research_x'], row['values']['research_y']
            assert row['metrics']['model']['synthetic_objective']['value'] == pytest.approx((x - 1.25)**2 + (y - 1.75)**2)
            assert {'physical_validation', 'model_qualification'} <= set(row['unknown'])
        else:
            assert native['solver_status'] == 'NOT_RUN' and row['metrics']['model'] == {}
            assert not (folder / 'simulation').exists()
    assert adapter.calls == sum(r['usable'] for r in result['samples'])
    independent, _ = _lab(tmp_path / 'independent', two=True)
    second = _plan(independent, parameter_ids=['research_y', 'research_x'], sample_count=8)
    assert second['algorithm'] == plan['algorithm'] and second['samples'] == plan['samples']


def test_completed_doe_is_read_only_without_installed_adapter_or_sampler(tmp_path):
    lab, adapter = _lab(tmp_path)
    _plan(lab)
    result = model_doe.run_doe(lab, CAMPAIGN)
    before, calls = _files(lab.store), adapter.calls
    lab.model_analysis_adapters = {}; lab.doe_adapters = {}
    assert model_doe.inspect_doe(lab, CAMPAIGN) == result
    assert model_doe.run_doe(lab, CAMPAIGN) == result
    assert _files(lab.store) == before and adapter.calls == calls


@pytest.mark.parametrize('changes', [
    {'sample_count': True}, {'sample_count': 1}, {'sample_count': 33}, {'seed': True}, {'seed': -1},
    {'seed': 2**32}, {'parameter_ids': []}, {'parameter_ids': ['research_x', 'research_x']},
    {'parameter_ids': ['unadvertised']}, {'required_validations': {'cad': []}},
    {'required_validations': {'model': ['synthetic_check', 'synthetic_check']}},
    {'required_validations': {'model': [' ']}}, {'engine': 'test.unavailable'}])
def test_invalid_request_never_reserves_campaign_or_executes(tmp_path, changes):
    lab, adapter = _lab(tmp_path)
    with pytest.raises((ValueError, CapabilityUnavailable)):
        _plan(lab, **changes)
    assert not (lab.store / 'campaigns' / CAMPAIGN).exists() and adapter.calls == 0


@pytest.mark.parametrize('key,value', [('unit', 'mm'), ('lower_bound', True), ('upper_bound', float('inf')),
                                     ('lower_bound', -1), ('mode', 'fixed'), ('kind', 'integer')])
def test_registry_unit_bounds_and_noncontinuous_inputs_are_refused(tmp_path, key, value):
    lab, adapter = _lab(tmp_path)
    registry_path = lab.store / 'studies' / STUDY / 'parameters.json'
    registry = load_json(registry_path); registry['entries'][0][key] = value
    if value == float('inf'):
        # Preserve a malformed input fixture without using the checked writer.
        registry_path.write_text(__import__('json').dumps(registry))
    else:
        save_json(registry_path, registry)
    with pytest.raises(ValueError):
        _plan(lab)
    assert adapter.calls == 0 and not (lab.store / 'campaigns' / CAMPAIGN).exists()


@pytest.mark.parametrize('value', [True, float('nan'), float('inf'), -1, 5])
def test_malformed_sampler_point_is_not_a_native_assignment(tmp_path, monkeypatch, value):
    lab, adapter = _lab(tmp_path)
    sampler = lab.doe_adapters[model_doe.ENGINE]; original = sampler.sample
    def bad(*args, **kwargs):
        points, metadata = original(*args, **kwargs)
        points[0]['research_x'] = value
        return points, metadata
    monkeypatch.setattr(sampler, 'sample', bad)
    with pytest.raises(ValueError):
        _plan(lab)
    assert adapter.calls == 0 and not (lab.store / 'campaigns' / CAMPAIGN).exists()


@pytest.mark.parametrize('status', ['FAIL', 'UNKNOWN', 'MISSING'])
def test_missing_or_failed_required_verdict_remains_unusable(tmp_path, status):
    lab, adapter = _lab(tmp_path, SyntheticParameterizedModel(check_status=status))
    _plan(lab, sample_count=2)
    result = model_doe.run_doe(lab, CAMPAIGN)
    assert adapter.calls == 2
    for row in result['samples']:
        assert not row['usable'] and not row['failed_execution']
        assert row['decision'] == 'NOT_RELEASED'
        if status == 'FAIL':
            assert any(v['type'] == 'synthetic_check' for v in row['failures'])
        elif status == 'UNKNOWN':
            assert 'synthetic_check' in row['unknown']


def test_invalid_metric_is_preserved_and_not_promoted_by_doe(tmp_path):
    invalid = {'value': None, 'unit': '1', 'valid': False, 'reason': 'TEST ONLY unavailable observation'}
    lab, adapter = _lab(tmp_path, SyntheticParameterizedModel(metric_overrides={'synthetic_objective': invalid}))
    _plan(lab, sample_count=2)
    result = model_doe.run_doe(lab, CAMPAIGN)
    assert adapter.calls == 2
    # Usability is exactly the existing completion/validation/convergence rule;
    # DOE does not invent an objective or replace the invalid metric.
    assert all(r['usable'] and r['metrics']['model']['synthetic_objective'] == invalid for r in result['samples'])


class Interrupted(RuntimeError):
    pass


def _interrupt(lab, monkeypatch):
    original = lab.run_model_analysis
    def stop(**args):
        if args['experiment_id'].endswith('-0002'):
            raise Interrupted('TEST ONLY before second model')
        return original(**args)
    monkeypatch.setattr(lab, 'run_model_analysis', stop)
    with pytest.raises(Interrupted):
        model_doe.run_doe(lab, CAMPAIGN)
    monkeypatch.setattr(lab, 'run_model_analysis', original)
    partial = model_doe.inspect_doe(lab, CAMPAIGN)
    assert partial['status'] == 'RUNNING' and partial['completed_samples'] == 1
    return partial


def test_interruption_resumes_exact_samples_without_repeating_first_experiment(tmp_path, monkeypatch):
    lab, adapter = _lab(tmp_path)
    _plan(lab)
    partial = _interrupt(lab, monkeypatch)
    first = lab.store / 'experiments' / partial['samples'][0]['model_experiment_id']
    before = _files(first)
    journal = lab.store / 'campaigns' / CAMPAIGN / 'journal/0001.json'
    journal_bytes = journal.read_bytes()
    result = model_doe.run_doe(lab, CAMPAIGN)
    assert result['samples'][0] == partial['samples'][0]
    assert _files(first) == before and journal.read_bytes() == journal_bytes and adapter.calls == 4


@pytest.mark.parametrize('boundary', ['journal', 'checkpoint', 'state'])
def test_completed_native_or_journal_crash_boundary_does_not_repeat_execution(tmp_path, monkeypatch, boundary):
    lab, adapter = _lab(tmp_path)
    _plan(lab, sample_count=2)
    campaign = lab.store / 'campaigns' / CAMPAIGN
    original = model_doe.save_json
    target = campaign / {'journal': 'journal/0001.json', 'checkpoint': 'checkpoints/0001.json', 'state': 'state.json'}[boundary]
    def stop(path, value):
        if path == target:
            raise Interrupted('TEST ONLY atomic persistence boundary')
        return original(path, value)
    monkeypatch.setattr(model_doe, 'save_json', stop)
    with pytest.raises(Interrupted):
        model_doe.run_doe(lab, CAMPAIGN)
    assert adapter.calls == 1
    before = _files(lab.store / 'experiments' / f'E-{CAMPAIGN}-0001')
    monkeypatch.setattr(model_doe, 'save_json', original)
    result = model_doe.run_doe(lab, CAMPAIGN)
    assert len(result['samples']) == 2 and adapter.calls == 2
    assert _files(lab.store / 'experiments' / f'E-{CAMPAIGN}-0001') == before


@pytest.mark.parametrize('change', ['registry', 'runtime', 'core', 'template', 'sampler', 'candidate_context'])
def test_changed_execution_context_blocks_before_native(tmp_path, monkeypatch, controlled_core_identity, change):
    lab, adapter = _lab(tmp_path)
    _plan(lab)
    if change == 'registry':
        path = lab.store / 'studies' / STUDY / 'parameters.json'
        registry = load_json(path); registry['revision'] += 1; save_json(path, registry)
    elif change == 'runtime':
        adapter.runtime_version = 'TEST_ONLY_CHANGED'
    elif change == 'core':
        controlled_core_identity['core_source_sha256'] = 'b' * 64
    elif change == 'template':
        original = adapter.describe_model
        def changed(settings):
            result = original(settings); result['fixed_context']['validation']['max_error'] = 999
            return result
        monkeypatch.setattr(adapter, 'describe_model', changed)
    elif change == 'sampler':
        sampler = lab.doe_adapters[model_doe.ENGINE]; original = sampler.sample
        def changed(*args, **kwargs):
            points, metadata = original(*args, **kwargs); points.reverse(); return points, metadata
        monkeypatch.setattr(sampler, 'sample', changed)
    else:
        original = adapter.describe_model
        def changed(settings):
            result = original(settings)
            if settings['inputs']['x'] != 1:
                result['fixed_context']['flags']['audit'] = False
            return result
        monkeypatch.setattr(adapter, 'describe_model', changed)
    with pytest.raises(ValueError):
        model_doe.run_doe(lab, CAMPAIGN)
    assert adapter.calls == 0 and not (lab.store / 'experiments').exists()


def test_runtime_drift_after_first_result_retains_native_and_stops_before_second(tmp_path, monkeypatch):
    lab, adapter = _lab(tmp_path)
    _plan(lab)
    original = adapter.solve
    def drift(*args):
        outcome = original(*args); adapter.runtime_version = 'CHANGED_AFTER_FIRST'; return outcome
    monkeypatch.setattr(adapter, 'solve', drift)
    with pytest.raises(ValueError, match='changed since planning'):
        model_doe.run_doe(lab, CAMPAIGN)
    assert adapter.calls == 1 and not (lab.store / 'experiments' / f'E-{CAMPAIGN}-0002').exists()
    first = lab.inspect_experiment(f'E-{CAMPAIGN}-0001')
    assert first['status'] == 'COMPLETED_REVIEW_REQUIRED'
    assert model_doe.inspect_doe(lab, CAMPAIGN)['completed_samples'] == 0
    adapter.runtime_version = '1'
    monkeypatch.setattr(adapter, 'solve', original)
    model_doe.run_doe(lab, CAMPAIGN)
    assert adapter.calls == 4


def test_failed_execution_is_retained_and_never_repaired_in_place(tmp_path):
    lab, adapter = _lab(tmp_path, SyntheticParameterizedModel(crash=True))
    _plan(lab)
    with pytest.raises(RuntimeError, match='evidence retained'):
        model_doe.run_doe(lab, CAMPAIGN)
    partial = model_doe.inspect_doe(lab, CAMPAIGN)
    row = partial['samples'][0]
    assert partial['status'] == row['status'] == 'FAILED_EXECUTION' and row['failed_execution']
    assert not row['usable'] and row['model_result_sha256'] == _sha(lab.store / 'experiments' / row['model_experiment_id'] / 'result.json')
    preserved = _files(lab.store)
    adapter.crash = False
    with pytest.raises(RuntimeError, match='plan a new campaign'):
        model_doe.run_doe(lab, CAMPAIGN)
    assert adapter.calls == 1 and _files(lab.store) == preserved


@pytest.mark.parametrize('name', ['plan.json', 'registry_snapshot.json', 'candidates/0001.json', 'journal/0001.json',
                                  'checkpoints/0001.json', 'state.json', 'result.json', 'native_artifact'])
def test_tamper_is_refused_on_read_and_replay(tmp_path, name):
    lab, adapter = _lab(tmp_path)
    _plan(lab, sample_count=2)
    result = model_doe.run_doe(lab, CAMPAIGN)
    campaign = lab.store / 'campaigns' / CAMPAIGN
    if name == 'native_artifact':
        path = lab.store / 'experiments' / result['samples'][0]['model_experiment_id'] / 'simulation/raw.log'
        path.write_bytes(path.read_bytes() + b'changed')
    elif name in ('plan.json', 'registry_snapshot.json', 'result.json'):
        path = campaign / name; path.write_bytes(path.read_bytes() + b' ')
    else:
        path = campaign / name; value = load_json(path); value['TEST_ONLY_tamper'] = True; save_json(path, value)
    for call in (model_doe.inspect_doe, model_doe.run_doe):
        with pytest.raises(ValueError):
            call(lab, CAMPAIGN)
    assert adapter.calls == 2


@pytest.mark.parametrize('name', ['candidate', 'journal_gap', 'checkpoint_extra'])
def test_extra_or_missing_sequence_members_are_refused(tmp_path, name):
    lab, adapter = _lab(tmp_path)
    _plan(lab, sample_count=2)
    model_doe.run_doe(lab, CAMPAIGN)
    campaign = lab.store / 'campaigns' / CAMPAIGN
    if name == 'candidate':
        save_json(campaign / 'candidates/0003.json', {})
    elif name == 'journal_gap':
        (campaign / 'journal/0001.json').unlink()
    else:
        save_json(campaign / 'checkpoints/0003.json', {})
    with pytest.raises(ValueError):
        model_doe.inspect_doe(lab, CAMPAIGN)
    assert adapter.calls == 2


def test_rehashed_frozen_context_and_result_provenance_tamper_are_still_refused(tmp_path):
    lab, adapter = _lab(tmp_path)
    _plan(lab, sample_count=2)
    model_doe.run_doe(lab, CAMPAIGN)
    campaign, ledger_path = lab.store / 'campaigns' / CAMPAIGN, lab.store / 'ledger' / f'campaign-{CAMPAIGN}.json'
    result = load_json(campaign / 'result.json'); result['provenance']['journal_sha256']['0001.json'] = 'f' * 64
    save_json(campaign / 'result.json', result)
    ledger = load_json(ledger_path); ledger['result_sha256'] = _sha(campaign / 'result.json'); save_json(ledger_path, ledger)
    with pytest.raises(ValueError, match='verified plan'):
        model_doe.inspect_doe(lab, CAMPAIGN)
    plan = load_json(campaign / 'plan.json'); plan['model_template']['mesh']['degree'] = 99
    save_json(campaign / 'plan.json', plan)
    ledger['plan_sha256'] = _sha(campaign / 'plan.json'); save_json(ledger_path, ledger)
    with pytest.raises(ValueError, match='template revision'):
        model_doe.inspect_doe(lab, CAMPAIGN)
    assert adapter.calls == 2


def test_campaign_id_reuse_cannot_replace_an_existing_plan_or_optimizer(tmp_path):
    lab, adapter = _lab(tmp_path)
    _plan(lab)
    before = _files(lab.store)
    with pytest.raises(ValueError, match='already used'):
        _plan(lab)
    assert _files(lab.store) == before and adapter.calls == 0
    (lab.store / 'optimizations/C-used').mkdir(parents=True)
    with pytest.raises(ValueError, match='already used'):
        _plan(lab, campaign_id='C-used')


def test_fixed_cad_doe_reuses_one_parent_and_preserves_conditions_sources(fixed_lab):
    lab = fixed_lab
    parent = _files(lab.store / 'experiments/E-cad')
    original = _files(lab.store / 'analysis_conditions/C-conditions')
    plan = _fixed_plan(lab)
    result = model_doe.run_doe(lab, FIXED)
    assert result['route'] == 'fixed_cad_analysis' and len(result['samples']) == 4
    assert result['algorithm'] == plan['algorithm'] and plan['objective'] is None
    for row in result['samples']:
        assert row['cad_experiment_id'] == 'E-cad' and row['usable']
        assert row['analysis_experiment_id'] == f"E-{FIXED}-{row['index']:04d}"
        child = lab.inspect_experiment(row['analysis_experiment_id'])
        assert child['parent_experiment_id'] == 'E-cad' and child['cad_revision'] == plan['fixed_cad']['source']['cad_revision']
        assert child['input_parameters'] == {'width': 38}
        assert row['metrics']['analysis'] == child['metrics']
        assert row['metrics']['analysis']['max_displacement']['value'] == pytest.approx(150 / row['values']['elastic_E'])
        assert row['analysis_result_sha256'] == _sha(lab.store / 'experiments' / row['analysis_experiment_id'] / 'result.json')
        declaration = row['condition_declaration']
        assert declaration['materials'][0]['source']['category'] == 'ASSUMED'
        assert 'qualification UNKNOWN' in declaration['materials'][0]['source']['description']
        for key in ('loads', 'mesh', 'contact', 'boundary_conditions', 'coordinate_system', 'units'):
            assert declaration[key] == plan['fixed_cad']['record']['request']['declaration'][key]
    assert _files(lab.store / 'experiments/E-cad') == parent
    assert _files(lab.store / 'analysis_conditions/C-conditions') == original
    assert len(lab.analysis_adapters[NativeStructuralAdapter.backend].calls) == 4
    shutil.rmtree(lab.store / 'analysis_conditions')
    lab.analysis_adapters = {}; lab.doe_adapters = {}; lab.adapters = {}
    assert model_doe.inspect_doe(lab, FIXED) == result and model_doe.run_doe(lab, FIXED) == result


def test_fixed_cad_interrupted_child_reuses_preserved_result(fixed_lab, monkeypatch):
    lab = fixed_lab
    _fixed_plan(lab)
    original = lab.run_analysis
    def stop(**args):
        if args['experiment_id'].endswith('-0002'):
            raise Interrupted('TEST ONLY fixed child interruption')
        return original(**args)
    monkeypatch.setattr(lab, 'run_analysis', stop)
    with pytest.raises(Interrupted):
        model_doe.run_doe(lab, FIXED)
    partial = model_doe.inspect_doe(lab, FIXED)
    assert partial['completed_samples'] == 1
    first = _files(lab.store / 'experiments' / partial['samples'][0]['analysis_experiment_id'])
    monkeypatch.setattr(lab, 'run_analysis', original)
    result = model_doe.run_doe(lab, FIXED)
    assert _files(lab.store / 'experiments' / result['samples'][0]['analysis_experiment_id']) == first
    assert len(lab.analysis_adapters[NativeStructuralAdapter.backend].calls) == 4


def test_fixed_cad_zero_resultant_is_retained_domain_rejection_without_child(fixed_lab, monkeypatch):
    lab = fixed_lab
    register_condition(lab, input_id='load_L1_FZ', parameter_id='force_z', lower=-300, upper=300)
    sampler = lab.doe_adapters[model_doe.ENGINE]; original = sampler.sample
    def explicit_points(*args, **kwargs):
        points, metadata = original(*args, **kwargs)
        points[0]['force_z'] = 0
        return points, metadata
    monkeypatch.setattr(sampler, 'sample', explicit_points)
    plan = _fixed_plan(lab, parameter_ids=['force_z'], sample_count=2)
    result = model_doe.run_doe(lab, FIXED)
    rejected = result['samples'][0]
    assert rejected['values'] == {'force_z': 0} and rejected['analysis_status'] == 'SKIPPED_DOMAIN_CONDITION_REJECTED'
    assert rejected['conditions_id'] is rejected['analysis_experiment_id'] is rejected['metrics']['analysis'] is None
    assert not rejected['usable'] and not rejected['failed_execution']
    assert rejected['condition_input_rejection'] == plan['samples'][0]['condition_input_rejection']
    assert not (lab.store / 'experiments' / f'E-{FIXED}-0001').exists()
    assert len(lab.analysis_adapters[NativeStructuralAdapter.backend].calls) == 1
    original = _files(lab.store)
    report = lab.create_campaign_report(campaign_id=FIXED, report_id='R-mixed-fixed',
        purpose='TEST ONLY valid response and rejected condition retain distinct source identities',
        origin='SYNTHETIC', reference='TEST ONLY zero force has no native child',
        response_definitions=[{'metric':'max_displacement','unit':'mm','direction':'minimize'}],
        uncertainty={'interpretation':'DESIGN_SPACE_ONLY','reference':'TEST ONLY declared force bounds'},seed=13)
    assert report['source']['experiment_ids'] == [result['samples'][1]['analysis_experiment_id']]
    assert set(report['source']['experiment_ids']) <= set(report['source']['sample_ids'])
    assert 'E-cad' not in report['source']['experiment_result_sha256']
    missing = report['samples'][0]
    assert missing['id'] == f'E-{FIXED}-0001' and not missing['usable']
    assert missing['responses']['max_displacement'] == {'value':None,'unit':'mm','valid':False}
    assert any(row['id'] == missing['id'] for row in report['analysis']['exclusions'])
    assert lab.inspect_campaign_report('R-mixed-fixed') == report
    assert len(lab.analysis_adapters[NativeStructuralAdapter.backend].calls) == 1
    assert all((lab.store/name).read_bytes() == value for name,value in original.items())


def test_fixed_parent_and_policy_drift_block_without_solver(fixed_lab, monkeypatch):
    lab = fixed_lab
    _fixed_plan(lab)
    adapter = lab.analysis_adapters[NativeStructuralAdapter.backend]
    original = adapter.condition_input_policy_identity
    monkeypatch.setattr(adapter, 'condition_input_policy_identity', lambda: {'TEST_ONLY_CHANGED': 'f' * 64})
    with pytest.raises(ValueError, match='changed after planning'):
        model_doe.run_doe(lab, FIXED)
    monkeypatch.setattr(adapter, 'condition_input_policy_identity', original)
    path = lab.store / 'experiments/E-cad/cad/native.step'; path.write_bytes(path.read_bytes() + b'changed')
    with pytest.raises(ValueError, match='Artifact hash mismatch'):
        model_doe.run_doe(lab, FIXED)
    assert not adapter.calls
