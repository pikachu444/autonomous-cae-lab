"""Real CAD + deterministic engines; analysis responses are explicitly TEST_ONLY."""

from copy import deepcopy
import shutil

import pytest

from caelab import Lab
from caelab.adapters.fixture_cadquery import FixtureCadQueryAdapter
from caelab.optimizers.scipy_de import ScipyDifferentialEvolution
from caelab.optimizers.scipy_lhs import ScipyLatinHypercube
from test_analysis_conditions import CaptureSolver, condition_request, conditions_cad


class ResponseSolver(CaptureSolver):
    def solve(self, parent_result, parent_root, output, settings):
        result = super().solve(parent_result, parent_root, output, settings)
        width = parent_result['input_parameters']['width']
        force = settings['load']['force_per_support_N']
        result['metrics'] = {'max_displacement': {'value': force / width, 'unit': 'mm', 'valid': True}}
        result['provenance'] = {'versions': {'solver': 'TEST_ONLY_RESPONSE_1'}}
        return result


@pytest.fixture
def lab(conditions_cad, tmp_path):
    root = tmp_path / 'store'
    shutil.copytree(conditions_cad, root)
    lab = Lab(root, adapters={'fixture.cadquery': FixtureCadQueryAdapter()},
              analysis_adapters={'fixture.calculix': ResponseSolver()},
              model_analysis_adapters={}, pde_adapters={},
              optimization_adapters={'scipy.differential_evolution': ScipyDifferentialEvolution()},
              doe_adapters={'scipy.latin_hypercube': ScipyLatinHypercube()})
    lab.save_analysis_conditions(**condition_request(lab))
    return lab


def options(campaign='C-search-conditions'):
    return {'study_id': 'S-conditions', 'campaign_id': campaign, 'backend': 'fixture.cadquery',
            'model': 'roller_support', 'parameter_ids': ['width'], 'analysis_backend': 'fixture.calculix',
            'conditions_id': 'C-conditions', 'seed': 13}


def optimization_options():
    return {**options(), 'objective': {'source': 'analysis', 'metric': 'max_displacement',
                                     'unit': 'mm', 'direction': 'minimize'},
            'constraints': [], 'initial_values': {'width': 38}, 'max_generations': 1, 'population_size': 5,
            'required_validations': {'cad': [], 'analysis': ['test_only_transport']}}


def test_de_rebinds_each_revision_preserves_condition_semantics_and_completed_replay(lab):
    plan = lab.plan_optimization(**optimization_options())
    template = plan['analysis']['conditions_template']
    assert template['reference']['id'] == 'C-conditions'
    assert template['record']['source']['experiment_id'] == 'E-cad'
    assert template['rebind_policy'] == 'REVISION_REBIND_EXACT_SELECTIONS'
    original = (lab.store / 'analysis_conditions/C-conditions/record.json').read_bytes()
    result = lab.run_optimization(plan['campaign_id'])
    rows = result['evaluations']
    assert 5 <= len(rows) <= 10
    assert result['termination']['converged'] is False and result['decision'] == 'NOT_RELEASED'
    for row in rows:
        assert row['usable']
        child = lab.inspect_experiment(row['analysis_experiment_id'])
        context = lab.research_summary(child['experiment_id'])['analysis_conditions_context']
        assert context['reference']['id'] == f"C-{plan['campaign_id']}-{row['index']:04d}"
        assert context['declaration'] == template['record']['request']['declaration']
        assert context['source_experiment_id'] == row['cad_experiment_id']
        assert context['cad_revision'] == child['cad_revision']
        assert context['engineering'] == 'UNKNOWN' and context['decision'] == 'NOT_RELEASED'
        assert row['objective']['value'] == pytest.approx(150 / row['values']['width'])
    assert len(lab.analysis_adapters['fixture.calculix'].calls) == len(rows)
    assert (lab.store / 'analysis_conditions/C-conditions/record.json').read_bytes() == original
    retained = {p: p.read_bytes() for p in lab.store.rglob('*') if p.is_file() and p.suffix != '.lock'}
    assert lab.run_optimization(plan['campaign_id']) == result
    assert all(p.read_bytes() == raw for p, raw in retained.items())
    assert len(lab.analysis_adapters['fixture.calculix'].calls) == len(rows)
    # Finished child/campaign context remains readable without mutable C listing
    # or current adapter objects, while native artifacts retain their own pins.
    shutil.rmtree(lab.store / 'analysis_conditions')
    lab.analysis_adapters = {}
    assert lab.inspect_optimization(plan['campaign_id']) == result
    assert lab.research_summary(rows[0]['analysis_experiment_id'])['analysis_conditions_context']['scope'] == 'USER_DECLARED_UNVERIFIED'


def test_lhs_uses_same_typed_conditions_and_replay_never_repeats_analysis(lab):
    plan = lab.plan_doe(**options('C-lhs-conditions'), sample_count=2)
    result = lab.run_doe(plan['campaign_id'])
    assert result['decision'] == 'NOT_RELEASED' and len(result['samples']) == 2
    assert len(lab.analysis_adapters['fixture.calculix'].calls) == 2
    for row in result['samples']:
        context = lab.research_summary(row['analysis_experiment_id'])['analysis_conditions_context']
        assert context['declaration']['loads'][0]['components']['FZ'] == -150
        assert context['source_experiment_id'] == row['cad_experiment_id']
    assert lab.run_doe(plan['campaign_id']) == result
    assert len(lab.analysis_adapters['fixture.calculix'].calls) == 2


@pytest.mark.parametrize('change', [{'study_id': 'S-other'}, {'model': 'fixture'},
                                   {'analysis_backend': None}, {'analysis_settings': {} }])
def test_wrong_model_study_or_competing_settings_never_creates_campaign(lab, change):
    lab.create_study('S-other', 'Other', 'Question', 'Hypothesis', 'Objective')
    request = {**optimization_options(), **change}
    with pytest.raises((ValueError, KeyError)):
        lab.plan_optimization(**request)
    assert not (lab.store / 'optimizations/C-search-conditions').exists()
    assert not lab.analysis_adapters['fixture.calculix'].calls


def test_template_bytes_tampering_refuses_read_and_new_execution(lab):
    plan = lab.plan_optimization(**optimization_options())
    path = lab.store / 'optimizations' / plan['campaign_id'] / 'analysis_conditions_template.json'
    path.write_bytes(path.read_bytes() + b' ')
    with pytest.raises(ValueError, match='frozen conditions'):
        lab.inspect_optimization(plan['campaign_id'])
    with pytest.raises(ValueError, match='frozen conditions'):
        lab.run_optimization(plan['campaign_id'])
    assert not lab.analysis_adapters['fixture.calculix'].calls


def test_region_definition_drift_blocks_rebind_before_native_execution(lab, monkeypatch):
    from caelab.campaign_conditions import bind
    plan = lab.plan_optimization(**optimization_options())
    candidate = lab.run_experiment(study_id='S-conditions', experiment_id='E-candidate',
                                  backend='fixture.cadquery', model='roller_support', values={'width': 40})
    original = lab.describe_analysis_conditions
    def changed(identifier):
        value = deepcopy(original(identifier))
        value['catalog']['selections'][-1]['definition'] = 'Different load distribution'
        return value
    monkeypatch.setattr(lab, 'describe_analysis_conditions', changed)
    with pytest.raises(ValueError, match='selection semantics'):
        bind(lab, plan, {'cad_experiment_id': candidate['experiment_id'], 'index': 1})
    assert not (lab.store / f"analysis_conditions/C-{plan['campaign_id']}-0001").exists()
    assert not lab.analysis_adapters['fixture.calculix'].calls


def test_policy_drift_refuses_fresh_campaign_work(lab, monkeypatch):
    plan = lab.plan_optimization(**optimization_options())
    adapter = lab.analysis_adapters['fixture.calculix']
    original = adapter.conditions_policy_identity
    monkeypatch.setattr(adapter, 'conditions_policy_identity', lambda: {**original(), 'changed': '0' * 64})
    with pytest.raises(ValueError, match='binding mismatch'):
        lab.run_optimization(plan['campaign_id'])
    assert not adapter.calls


def test_summary_names_loaded_uz_only_for_advertised_fixture_version(lab):
    lab.run_analysis(parent_experiment_id='E-cad', experiment_id='E-child',
                     backend='fixture.calculix', conditions_id='C-conditions')
    summary = lab.research_summary('E-child')
    assert summary['metric_semantics']['max_displacement']['component'] == 'UZ'
    assert summary['metric_semantics']['max_displacement']['selection_id'] == 'S-saddle'
    assert 'metric_semantics' not in lab.research_summary('E-cad')
