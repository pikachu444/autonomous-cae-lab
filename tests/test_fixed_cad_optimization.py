"""Actual SciPy feedback/replay on real CAD with a TEST_ONLY solver/catalog.

No native FEA or physical qualification is claimed by these Core tests.
"""
from copy import deepcopy
from pathlib import Path
import shutil

import pytest

from caelab import Lab
from caelab.adapters.fixture_cadquery import FixtureCadQueryAdapter
from caelab.adapters.native_structural import NativeStructuralAdapter
from caelab.condition_parameters import bind, describe
from caelab.optimizers.scipy_de import ScipyDifferentialEvolution
from caelab.storage import canonical_hash, load_json
from test_analysis_conditions import conditions_cad, condition_request


class TestCatalogCAD(FixtureCadQueryAdapter):
    __test__ = False

    def conditions_catalog(self, folder, result, proposal):
        catalog = super().conditions_catalog(folder, result, proposal)
        catalog['cad_backend'] = 'fixture.freecad'  # TEST_ONLY native-face catalog.
        for index, item in enumerate(catalog['selections'][1:], 1):
            item.update(kind='native_face', roles=['load', 'boundary'], native_object='TEST_ONLY',
                        native_name=f'Face{index}', geometry_sha256=str(index)*64,
                        bounds_mm={'min': [100*index, 0, 0], 'max': [100*index, 10, 8]})
        return catalog


class TestResponse(NativeStructuralAdapter):
    __test__ = False

    def __init__(self):
        self.calls = []

    def solve(self, parent, root, output, settings):
        self.calls.append(deepcopy(settings))
        output.mkdir()
        (output/'test-only.txt').write_text('TEST_ONLY scalar feedback; no native solver')
        declaration = settings['declaration']; material = declaration['materials'][0]
        force = abs(declaration['loads'][0]['components']['FZ'])
        return {'status': 'COMPLETED', 'solver_status': 'COMPLETED', 'converged': True,
            'checks': [{'code': 'test_only_response', 'status': 'PASS', 'observed': 'TEST_ONLY'}],
            'metrics': {'max_displacement': {'value': force/material['young_modulus_MPa'], 'unit': 'mm', 'valid': True}},
            'pending_validations': ['material_qualification', 'static_strength'],
            'provenance': {'versions': {'solver': 'TEST_ONLY_1'}}, 'raw_result': 'simulation/test-only.txt'}


@pytest.fixture
def lab(conditions_cad, tmp_path):
    root = tmp_path/'store'; shutil.copytree(conditions_cad, root)
    lab = Lab(root, adapters={'fixture.cadquery': TestCatalogCAD()},
        analysis_adapters={NativeStructuralAdapter.backend: TestResponse()}, model_analysis_adapters={},
        pde_adapters={}, doe_adapters={}, optimization_adapters={'scipy.differential_evolution': ScipyDifferentialEvolution()})
    request = condition_request(lab); request['backend'] = NativeStructuralAdapter.backend
    lab.save_analysis_conditions(**request)
    return lab


def register(lab, input_id='material_M1_E', parameter_id='elastic_E', lower=180000, upper=240000):
    return lab.register_condition_parameter(study_id='S-conditions', conditions_id='C-conditions',
        input_id=input_id, parameter_id=parameter_id, display_name='Declared scenario input', lower=lower, upper=upper)


def plan(lab, **changes):
    args = {'study_id': 'S-conditions', 'campaign_id': 'C-fixed-search', 'conditions_id': 'C-conditions',
        'parameter_ids': ['elastic_E'], 'objective': {'source': 'analysis', 'metric': 'max_displacement', 'unit': 'mm', 'direction': 'minimize'},
        'constraints': [], 'seed': 13, 'max_generations': 1, 'population_size': 5,
        'required_validations': {'cad': [], 'analysis': ['test_only_response']}}
    args.update(changes)
    return lab.plan_condition_optimization(**args)


def retained(folder):
    return {p.relative_to(folder).as_posix(): p.read_bytes() for p in folder.rglob('*') if p.is_file() and not p.name.endswith('.lock')}


def test_fixed_cad_target_matching_keeps_raw_response_constraints_and_parent(lab):
    before = retained(lab.store/'experiments/E-cad')
    register(lab)
    target = 150 / 210000
    objective = {'source': 'analysis', 'metric': 'max_displacement', 'unit': 'mm', 'direction': 'match',
        'target': target, 'scale': 0.001, 'origin': 'SYNTHETIC', 'reference': 'TEST ONLY scalar response'}
    frozen = plan(lab, objective=objective, initial_values={'elastic_E': 210000}, constraints=[
        {'source': 'analysis', 'metric': 'max_displacement', 'unit': 'mm', 'operator': '<=', 'limit': 0.001, 'scale': 0.001}])
    result = lab.run_optimization(frozen['campaign_id'])
    assert retained(lab.store/'experiments/E-cad') == before
    for row in result['evaluations']:
        if row['usable']:
            raw = 150 / row['values']['elastic_E']
            assert row['objective']['value'] == pytest.approx(raw)
            assert row['feedback']['objective'] == pytest.approx(((raw-target)/0.001)**2)
            assert row['constraints'][0]['value'] == pytest.approx(raw)
    assert result['incumbent']['feedback']['objective'] == pytest.approx(0)
    assert lab.inspect_optimization(frozen['campaign_id']) == result


def test_discovery_registration_and_real_de_keep_one_cad_and_historical_reads(lab):
    before = retained(lab.store/'experiments/E-cad')
    template = lab.discover_condition_parameters('C-conditions')
    assert template['rebind_policy'] == 'FIXED_CAD_NO_REBIND'
    entry = register(lab)
    assert entry['target'] == 'analysis_conditions' and entry['input_effect']['physical'] == 'UNKNOWN'
    frozen = plan(lab)
    result = lab.run_optimization(frozen['campaign_id'])
    assert result['route'] == 'fixed_cad_analysis' and result['decision'] == 'NOT_RELEASED'
    assert 5 <= len(result['evaluations']) <= 10
    for row in result['evaluations']:
        assert row['cad_experiment_id'] == 'E-cad' and row['usable']
        child = lab.inspect_experiment(row['analysis_experiment_id'])
        assert child['input_parameters'] == {'width': 38}
        assert child['cad_revision'] == template['source']['cad_revision']
        assert child['decision'] == 'NOT_RELEASED'
        assert row['objective']['value'] == pytest.approx(150/row['values']['elastic_E'])
        bound = row['condition_declaration']
        assert bound['materials'][0]['source']['category'] == 'ASSUMED'
        assert bound['loads'] == template['record']['request']['declaration']['loads']
        assert bound['boundary_conditions'] == template['record']['request']['declaration']['boundary_conditions']
        assert bound['mesh'] == template['record']['request']['declaration']['mesh']
    assert retained(lab.store/'experiments/E-cad') == before
    calls = len(lab.analysis_adapters[NativeStructuralAdapter.backend].calls)
    assert calls == len(result['evaluations'])
    assert lab.run_optimization(frozen['campaign_id']) == result
    assert len(lab.analysis_adapters[NativeStructuralAdapter.backend].calls) == calls
    shutil.rmtree(lab.store/'analysis_conditions')
    lab.analysis_adapters = {}
    assert lab.inspect_optimization(frozen['campaign_id']) == result


def test_interrupted_campaign_replays_without_duplicate_native_calls(lab, monkeypatch):
    register(lab); frozen = plan(lab); original = lab.run_analysis
    def interrupted(**args):
        if args['experiment_id'].endswith('-0002'):
            raise RuntimeError('TEST_ONLY interruption before second solver')
        return original(**args)
    monkeypatch.setattr(lab, 'run_analysis', interrupted)
    with pytest.raises(RuntimeError, match='interruption'):
        lab.run_optimization(frozen['campaign_id'])
    assert lab.inspect_optimization(frozen['campaign_id'])['completed_evaluations'] == 1
    first = retained(lab.store/'experiments/E-C-fixed-search-0001')
    monkeypatch.setattr(lab, 'run_analysis', original)
    result = lab.run_optimization(frozen['campaign_id'])
    assert retained(lab.store/'experiments/E-C-fixed-search-0001') == first
    assert len(lab.analysis_adapters[NativeStructuralAdapter.backend].calls) == len(result['evaluations'])


@pytest.mark.parametrize('changes', [
    {'conditions_id': 'C-absent'}, {'parameter_ids': ['width']}, {'parameter_ids': ['elastic_E', 'elastic_E']},
    {'objective': {'source': 'cad', 'metric': 'cad_volume', 'unit': 'mm^3', 'direction': 'minimize'}},
    {'objective': {'source': 'analysis', 'metric': 'unadvertised', 'unit': 'mm', 'direction': 'minimize'}},
    {'population_size': True}, {'max_generations': 100, 'population_size': 64},
    {'required_validations': {'model': []}}, {'initial_values': {'elastic_E': float('nan')}}])
def test_invalid_plan_never_creates_campaign_or_solver(lab, changes):
    register(lab)
    with pytest.raises((ValueError, FileNotFoundError)):
        plan(lab, **changes)
    assert not (lab.store/'optimizations/C-fixed-search').exists()
    assert not lab.analysis_adapters[NativeStructuralAdapter.backend].calls


@pytest.mark.parametrize('assignment', [True, float('nan'), float('inf'), -1, 10**400])
def test_invalid_candidate_never_reaches_adapter(lab, assignment):
    template = describe(lab, 'C-conditions')
    with pytest.raises(ValueError):
        bind(lab, template, {'material_M1_E': assignment})
    assert not lab.analysis_adapters[NativeStructuralAdapter.backend].calls


def test_unadvertised_constraint_conflict_cannot_register_or_start_native(lab, monkeypatch):
    cad = lab.adapters['fixture.cadquery']; original = cad.conditions_catalog
    def adjacent(*args):
        catalog = original(*args)
        catalog['selections'][1]['bounds_mm'] = {'min': [0, 0, 0], 'max': [16, 0, 8]}
        catalog['selections'][2]['bounds_mm'] = {'min': [16, 0, 0], 'max': [16, 10, 8]}
        return catalog
    monkeypatch.setattr(cad, 'conditions_catalog', adjacent)
    request = condition_request(lab, identifier='C-adjacent')
    request['backend'] = NativeStructuralAdapter.backend
    request['declaration']['boundary_conditions'][0]['components'] = {'UY': 0, 'UZ': 0}
    request['declaration']['loads'][0]['components'] = {'FX': 150, 'FY': 0, 'FZ': 0}
    lab.save_analysis_conditions(**request)
    template = lab.discover_condition_parameters('C-adjacent')
    assert {item['id'] for item in template['descriptors']} == {'material_M1_E', 'material_M1_nu', 'load_L1_FX'}
    before = retained(lab.store)
    for axis in ('FY', 'FZ'):
        with pytest.raises(ValueError, match='not advertised'):
            lab.register_condition_parameter(study_id='S-conditions', conditions_id='C-adjacent',
                input_id=f'load_L1_{axis}', parameter_id=f'force_{axis}', display_name=axis, lower=-100, upper=100)
    assert retained(lab.store) == before
    assert not lab.analysis_adapters[NativeStructuralAdapter.backend].calls


def test_core_fixed_context_failure_is_not_domain_rejection(lab, monkeypatch):
    register(lab); frozen = plan(lab)
    adapter = lab.analysis_adapters[NativeStructuralAdapter.backend]; original = adapter.bind_condition_inputs
    def corrupt(catalog, declaration, assignments):
        bound = original(catalog, declaration, assignments); bound['mesh']['max_size_mm'] = 99
        return bound
    monkeypatch.setattr(adapter, 'bind_condition_inputs', corrupt)
    with pytest.raises(ValueError, match='undeclared fixed context'):
        lab.run_optimization(frozen['campaign_id'])
    assert not adapter.calls


def test_domain_rejection_retains_candidate_with_null_feedback_and_no_solver(lab, monkeypatch):
    register(lab); frozen = plan(lab)
    adapter = lab.analysis_adapters[NativeStructuralAdapter.backend]
    def reject(*args):
        raise ValueError('TEST_ONLY unsupported Domain scenario')
    monkeypatch.setattr(adapter, 'bind_condition_inputs', reject)
    result = lab.run_optimization(frozen['campaign_id'])
    assert result['status'] == 'NO_FEASIBLE_DESIGN' and result['incumbent'] is None
    assert not adapter.calls
    for row in result['evaluations']:
        assert row['analysis_status'] == 'SKIPPED_DOMAIN_CONDITION_REJECTED'
        assert row['conditions_id'] is None and row['analysis_experiment_id'] is None
        assert row['feedback']['objective'] is None and not row['usable']
    assert lab.inspect_optimization(frozen['campaign_id']) == result


def test_source_change_before_execution_blocks_native(lab, monkeypatch):
    register(lab); frozen = plan(lab)
    adapter = lab.analysis_adapters[NativeStructuralAdapter.backend]
    monkeypatch.setattr(adapter, 'condition_input_policy_identity', lambda: {'TEST_CHANGED': 'f'*64})
    with pytest.raises(ValueError, match='changed after planning'):
        lab.run_optimization(frozen['campaign_id'])
    assert not adapter.calls


def test_retained_child_tamper_blocks_campaign_read(lab):
    register(lab); frozen = plan(lab); result = lab.run_optimization(frozen['campaign_id'])
    child = lab.store/'experiments'/result['evaluations'][0]['analysis_experiment_id']/'analysis_conditions.json'
    child.write_bytes(child.read_bytes()+b' ')
    with pytest.raises(ValueError, match='Artifact hash mismatch'):
        lab.inspect_optimization(frozen['campaign_id'])
