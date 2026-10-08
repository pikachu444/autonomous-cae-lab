"""Declared finite LHS propagation through retained TEST_ONLY Core records.

No native solver, provider, new optimizer or measured distribution is executed.
The common source byte fingerprint is replaced only at this test boundary so
concurrent implementation owners cannot invalidate a synthetic Core identity.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest

from caelab import (analysis_conditions, campaign, campaign_report, condition_parameters,
                    declared_model, engine, model_doe, model_parameters, optimization)
from caelab.optimizers import probabilistic_analysis as uq
from caelab.optimizers.scipy_de import ScipyDifferentialEvolution
from caelab.optimizers.scipy_lhs import ScipyLatinHypercube
from caelab.storage import canonical_hash, load_json, save_json
from test_campaign import CountingAnalysis
from test_fixed_cad_optimization import register as register_condition
from test_model_doe import SyntheticRetainedCAD, fixed_lab
from test_model_parameters import (STUDY, SyntheticParameterizedModel, register_x,
                                   synthetic_lab, template_settings)


CAMPAIGN = 'C-probability-doe'
REPORT = 'R-probability'
PURE_MODULE_PIN = '5e45c0c61c2d7c1578ba847abbc80a1c57d80ef02921e5ca19ecd70f57171a6d'


@pytest.fixture(autouse=True)
def controlled_core_identity(monkeypatch):
    identity = {'core_commit': 'TEST_ONLY_NO_NATIVE', 'core_dirty': True,
                'core_source_sha256': 'a' * 64}
    for module in (analysis_conditions, campaign, campaign_report, condition_parameters, declared_model,
                   engine, model_doe, model_parameters, optimization):
        monkeypatch.setattr(module, 'source_identity', lambda root: deepcopy(identity))
    for module in (condition_parameters, model_parameters):
        monkeypatch.setattr(module, 'core_source_hash', lambda root: identity['core_source_sha256'])
    monkeypatch.setattr(campaign, 'core_source_hash', lambda root: identity['core_source_sha256'])


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _source_sha(path):
    # Git stores this Python source with LF. Windows worktrees may check it out
    # with CRLF, so pin the canonical source bytes rather than checkout EOLs.
    return hashlib.sha256(path.read_bytes().replace(b'\r\n', b'\n')).hexdigest()


def _files(root):
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob('*')
            if p.is_file() and not p.name.endswith('.lock')}


class SignedResponseModel(SyntheticParameterizedModel):
    """TEST_ONLY signed y=x-2; optional invalid result has no zero substitute."""

    def __init__(self, invalid_indices=(), fail_checks=False, **kwargs):
        super().__init__(**kwargs)
        self.invalid_indices = invalid_indices
        self.fail_checks = fail_checks

    def solve(self, output, settings):
        answer = super().solve(output, settings)
        invalid = self.calls in self.invalid_indices
        answer['metrics']['synthetic_constraint'] = {
            'value': None if invalid else settings['inputs']['x'] - 2.,
            'unit': '1', 'valid': not invalid}
        if invalid:
            answer['metrics']['synthetic_constraint']['reason'] = 'TEST_ONLY missing signed scalar'
        if self.fail_checks:
            answer['checks'][0]['status'] = 'FAIL'
        save_json(output / 'result.json', answer)
        return answer


def _completed(path, *, count=8, seed=13, adapter=None, two=False, order=None):
    lab, adapter = synthetic_lab(path, adapter or SignedResponseModel())
    lab.doe_adapters = {model_doe.ENGINE: ScipyLatinHypercube()}
    register_x(lab)
    if two:
        lab.register_model_parameter(STUDY, adapter.backend, template_settings(),
                                     'input_y', 'research_y', 'Y', 0., 4.)
    plan = lab.plan_model_doe(study_id=STUDY, campaign_id=CAMPAIGN, backend=adapter.backend,
        settings=template_settings(), parameter_ids=order or ['research_x'],
        sample_count=count, seed=seed, required_validations={'model': ['synthetic_check']})
    result = lab.run_doe(CAMPAIGN)
    return lab, adapter, plan, result


def _probability(plan, *, metric='synthetic_constraint', unit='1', value=0.,
                 operator='>', origin='ASSUMED'):
    return {'marginals': [
        {**{k: variable[k] for k in ('parameter_id', 'unit', 'lower_bound', 'upper_bound')},
         'distribution': 'uniform'} for variable in plan['variables']],
        'independence': 'INDEPENDENT_USER_DECLARED',
        'source': {'origin': origin, 'reference': 'TEST_ONLY explicitly assumed law; no measurements'},
        'thresholds': [{'id': 'T-positive', 'metric': metric, 'unit': unit,
                        'operator': operator, 'value': value}]}


def _arguments(plan, **changes):
    options = {'campaign_id': plan['campaign_id'], 'report_id': REPORT,
        'purpose': 'TEST_ONLY finite signed response propagation',
        'origin': 'SYNTHETIC', 'reference': 'TEST_ONLY y=x-2, not measured failure probability',
        'response_definitions': [{'metric': 'synthetic_constraint', 'unit': '1', 'direction': 'minimize'},
                                 {'metric': 'synthetic_objective', 'unit': '1', 'direction': 'minimize'}],
        'uncertainty': {'interpretation': 'USER_DECLARED_UNIFORM_INPUTS',
                        'reference': 'TEST_ONLY declared independent uniform research inputs'},
        'probability': _probability(plan), 'seed': 41}
    options.update(changes)
    return options


def test_pure_uq_module_reuses_the_exact_frozen_candidate_bytes():
    assert _source_sha(Path(uq.__file__)) == PURE_MODULE_PIN


@pytest.mark.parametrize('origin', ['ASSUMED', 'SYNTHETIC', 'PUBLISHED_REFERENCE', 'MEASURED_REPORTED'])
def test_probability_preserves_signed_originals_exact_lhs_and_declared_source(tmp_path, origin):
    lab, adapter, plan, result = _completed(tmp_path)
    before = _files(lab.store)
    probability = _probability(plan, origin=origin)
    arguments = _arguments(plan, probability=probability)
    original_arguments = deepcopy(arguments)
    report = lab.create_campaign_report(**arguments)
    assert arguments == original_arguments
    assert len(report) == 17 and len(report['declaration']) == 6
    propagation = report['probability_analysis']
    assert report['seed'] == 41 and propagation['declaration']['seed'] == plan['seed'] == 13
    assert report['declaration']['probability'] == probability
    assert propagation['declaration']['source'] == probability['source']
    assert propagation['declaration']['marginals'] == probability['marginals']
    assert propagation['declaration']['sampling']['version'] == plan['algorithm']['version']
    assert propagation['source_sampling']['algorithm'] == result['algorithm'] == plan['algorithm']
    assert propagation['source_sampling']['plan_sha256'] == _sha(lab.store / f'campaigns/{CAMPAIGN}/plan.json')
    assert propagation['source_sampling']['result_sha256'] == _sha(lab.store / f'campaigns/{CAMPAIGN}/result.json')
    assert propagation['sample_ids'] == [item['model_experiment_id'] for item in result['samples']]
    assert [item['values'] for item in propagation['declaration']['samples']] == [
        item['values'] for item in plan['samples']]
    assert [s['responses']['synthetic_constraint']['value'] for s in propagation['samples']] == [
        item['values']['research_x'] - 2. for item in result['samples']]
    assert propagation['statistics'][0]['min'] < 0 < propagation['statistics'][0]['max']
    estimate = propagation['thresholds'][0]
    assert estimate['exceedance_count'] == 4 and estimate['probability_estimate'] == .5
    assert estimate['confidence_interval'] is None
    assert estimate['confidence_interval_reason'] == 'LHS_STRATIFIED_DEPENDENT_NOT_IID_BINOMIAL'
    assert propagation['physical'] == propagation['engineering'] == 'UNKNOWN'
    assert propagation['decision'] == report['decision'] == 'NOT_RELEASED'
    assert 'finite declared design' in ' '.join(propagation['limitations'])
    assert all(_files(lab.store)[name] == value for name, value in before.items())
    calls = adapter.calls
    assert lab.inspect_campaign_report(REPORT) == report and adapter.calls == calls
    with pytest.raises(FileExistsError):
        lab.create_campaign_report(**arguments)


def test_none_keeps_the_original_sixteen_key_envelope_and_declaration(tmp_path):
    lab, _, plan, _ = _completed(tmp_path)
    args = _arguments(plan, probability=None)
    report = lab.create_campaign_report(**args)
    assert len(report) == 16 and len(report['declaration']) == 5
    assert 'probability' not in report['declaration'] and 'probability_analysis' not in report
    assert lab.inspect_campaign_report(REPORT) == report
    args.pop('probability'); args['report_id'] = 'R-legacy-omitted'
    other = lab.create_campaign_report(**args)
    assert report['declaration'] == other['declaration'] and report['analysis'] == other['analysis']
    assert report['samples'] == other['samples']


@pytest.mark.parametrize('operation', ['>', '>=', '<', '<='])
def test_exact_signed_threshold_boundary_uses_no_absolute_value(tmp_path, operation):
    lab, _, plan, result = _completed(tmp_path)
    boundary = result['samples'][0]['metrics']['model']['synthetic_constraint']['value']
    probability = _probability(plan, value=boundary, operator=operation)
    report = lab.create_campaign_report(**_arguments(plan, probability=probability))
    values = [r['metrics']['model']['synthetic_constraint']['value'] for r in result['samples']]
    expected = {'>': lambda x: x > boundary, '>=': lambda x: x >= boundary,
                '<': lambda x: x < boundary, '<=': lambda x: x <= boundary}[operation]
    threshold = report['probability_analysis']['thresholds'][0]
    assert threshold['exceedance_count'] == sum(expected(x) for x in values)
    assert threshold['value'] == boundary


def test_invalid_response_retains_original_reason_and_unknown_finite_design_bounds(tmp_path):
    lab, _, plan, result = _completed(tmp_path, adapter=SignedResponseModel(invalid_indices=(2,)))
    report = lab.create_campaign_report(**_arguments(plan))
    analysis = report['probability_analysis']
    missing_id = result['samples'][1]['model_experiment_id']
    assert analysis['counts'] == {'declared': 8, 'valid': 7, 'excluded': 1}
    assert analysis['exclusions'] == [{'id': missing_id, 'reason': 'INVALID_RESPONSE:synthetic_constraint'}]
    response = analysis['samples'][1]['responses']['synthetic_constraint']
    assert response == {'value': None, 'unit': '1', 'valid': False,
                        'reason': 'TEST_ONLY missing signed scalar'}
    threshold = analysis['thresholds'][0]
    n = threshold['exceedance_count']
    assert threshold['probability_estimate'] == n / 7
    assert threshold['unknown_outcome_fraction_bounds'] == {'lower': n / 8, 'upper': (n + 1) / 8}
    assert missing_id not in analysis['valid_sample_ids']


def test_domain_rejection_remains_unusable_and_missing_response_not_zero(tmp_path):
    lab, _, plan, result = _completed(tmp_path, two=True, order=['research_y', 'research_x'])
    report = lab.create_campaign_report(**_arguments(plan))
    analysis = report['probability_analysis']
    rejected = [r for r in result['samples'] if r['status'] == 'REJECTED']
    assert rejected and analysis['counts']['excluded'] == len(rejected)
    assert [m['parameter_id'] for m in analysis['declaration']['marginals']] == ['research_y', 'research_x']
    for row in rejected:
        saved = next(s for s in analysis['samples'] if s['id'] == row['model_experiment_id'])
        assert saved['usable'] is False and saved['responses']['synthetic_constraint']['value'] is None
        assert saved['responses']['synthetic_constraint']['valid'] is False
    assert lab.inspect_campaign_report(REPORT) == report


def test_native_numerical_rejection_has_no_valid_probability(tmp_path):
    lab, _, plan, _ = _completed(tmp_path, adapter=SignedResponseModel(fail_checks=True))
    report = lab.create_campaign_report(**_arguments(plan))
    analysis = report['probability_analysis']
    assert analysis['counts'] == {'declared': 8, 'valid': 0, 'excluded': 8}
    assert all(s['responses']['synthetic_constraint']['value'] is not None for s in analysis['samples'])
    threshold = analysis['thresholds'][0]
    assert threshold['probability_estimate'] is None and not threshold['valid']
    assert threshold['unknown_outcome_fraction_bounds'] == {'lower': 0., 'upper': 1.}


@pytest.mark.parametrize('change', [
    {'extra': True}, {'independence': 'INDEPENDENT_VERIFIED'},
    {'source': {'origin': 'VERIFIED_MEASURED', 'reference': 'unsupported'}},
    {'source': {'origin': 'ASSUMED', 'reference': ' '}},
    {'source': {'origin': 'ASSUMED', 'reference': 'x' * 2001}},
    {'thresholds': [{'id': 'T', 'metric': 'foreign', 'unit': '1', 'operator': '>', 'value': 0.}]},
    {'thresholds': [{'id': 'T', 'metric': 'synthetic_constraint', 'unit': 'N', 'operator': '>', 'value': 0.}]},
    {'thresholds': [{'id': 'T', 'metric': 'synthetic_constraint', 'unit': '1', 'operator': '==', 'value': 0.}]},
    {'thresholds': [{'id': 'T', 'metric': 'synthetic_constraint', 'unit': '1', 'operator': '>', 'value': True}]},
    {'thresholds': [{'id': 'T', 'metric': 'synthetic_constraint', 'unit': '1', 'operator': '>', 'value': float('nan')}]},
    {'thresholds': []},
])
def test_invalid_probability_declaration_refuses_without_report_or_new_execution(tmp_path, change):
    lab, adapter, plan, _ = _completed(tmp_path)
    probability = {**_probability(plan), **deepcopy(change)}
    before, calls = _files(lab.store), adapter.calls
    with pytest.raises(ValueError):
        lab.create_campaign_report(**_arguments(plan, probability=probability))
    assert not (lab.store / f'campaign_reports/{REPORT}').exists()
    assert _files(lab.store) == before and adapter.calls == calls


@pytest.mark.parametrize('key,value', [('unit', 'N'), ('lower_bound', -.1),
    ('upper_bound', 3.), ('lower_bound', False), ('distribution', 'normal'), ('parameter_id', 'other')])
def test_marginals_exactly_match_original_bounds_units_and_variable_identity(tmp_path, key, value):
    lab, _, plan, _ = _completed(tmp_path)
    probability = _probability(plan); probability['marginals'][0][key] = value
    with pytest.raises(ValueError, match='marginal'):
        lab.create_campaign_report(**_arguments(plan, probability=probability))
    assert not (lab.store / f'campaign_reports/{REPORT}').exists()


def test_marginal_order_cannot_relabel_original_lhs_columns(tmp_path):
    lab, _, plan, _ = _completed(tmp_path, two=True, order=['research_y', 'research_x'])
    probability = _probability(plan); probability['marginals'].reverse()
    with pytest.raises(ValueError, match='marginal order'):
        lab.create_campaign_report(**_arguments(plan, probability=probability))


def test_browser_integral_number_roundtrip_preserves_user_json_and_frozen_lhs_bytes(tmp_path):
    lab, _, plan, _ = _completed(tmp_path)
    probability = _probability(plan)
    assert type(probability['marginals'][0]['lower_bound']) is float
    # JSON.stringify emits 0 for the Number obtained from JSON's 0.0. Parsing
    # the actual browser payload in Python produces int, with the same value.
    serialized = json.dumps(probability).replace('"lower_bound": 0.0', '"lower_bound": 0')
    serialized = serialized.replace('"upper_bound": 4.0', '"upper_bound": 4')
    browser = json.loads(serialized)
    assert type(browser['marginals'][0]['lower_bound']) is int
    original_plan = (lab.store / f'campaigns/{CAMPAIGN}/plan.json').read_bytes()
    original_result = (lab.store / f'campaigns/{CAMPAIGN}/result.json').read_bytes()
    report = lab.create_campaign_report(**_arguments(plan, probability=browser))
    assert report['declaration']['probability'] == browser
    assert type(report['declaration']['probability']['marginals'][0]['lower_bound']) is int
    propagation = report['probability_analysis']
    assert type(propagation['declaration']['marginals'][0]['lower_bound']) is int
    assert [row['values'] for row in propagation['declaration']['samples']] == [
        row['values'] for row in plan['samples']]
    assert (lab.store / f'campaigns/{CAMPAIGN}/plan.json').read_bytes() == original_plan
    assert (lab.store / f'campaigns/{CAMPAIGN}/result.json').read_bytes() == original_result
    assert lab.inspect_campaign_report(REPORT) == report
    browser['marginals'][0]['lower_bound'] = 1e-12
    with pytest.raises(ValueError, match='marginal order/bounds/unit'):
        lab.create_campaign_report(**_arguments(plan, report_id='R-actual-bound-drift', probability=browser))
    assert not (lab.store / 'campaign_reports/R-actual-bound-drift').exists()


@pytest.mark.parametrize('left,right,equal', [(0., 0, True), (4., 4, True), (-0., 0, True),
    (0., 1e-12, False), (0, False, False), (1, True, False), (float('nan'), 0, False),
    (float('inf'), float('inf'), False), (10 ** 400, 10 ** 400, False),
    (2 ** 53 + 1, float(2 ** 53 + 1), False), (float(2 ** 53 + 1), 2 ** 53 + 1, False),
    (2 ** 53 + 2, float(2 ** 53 + 2), True)])
def test_bound_numeric_equivalence_refuses_bool_nonfinite_and_integer_rounding(left, right, equal):
    assert campaign_report._bound_equal(left, right) is equal


@pytest.mark.parametrize('removed', ['adapter', 'metrics'])
def test_sealed_probability_reopens_without_current_advertised_backend(tmp_path, removed):
    lab, adapter, plan, _ = _completed(tmp_path)
    report = lab.create_campaign_report(**_arguments(plan))
    before, calls = _files(lab.store), adapter.calls
    if removed == 'adapter':
        lab.model_analysis_adapters = {}; lab.doe_adapters = {}
    else:
        adapter.default_metrics = []
    assert lab.inspect_campaign_report(REPORT) == report
    assert _files(lab.store) == before and adapter.calls == calls
    with pytest.raises(ValueError, match='advertised'):
        lab.create_campaign_report(**_arguments(plan, report_id='R-new-without-admission'))


@pytest.mark.parametrize('location', ['record', 'receipt', 'rehash_analysis', 'rehash_declaration'])
def test_report_receipt_or_rehashed_probability_payload_tamper_is_refused(tmp_path, location):
    lab, _, plan, _ = _completed(tmp_path)
    lab.create_campaign_report(**_arguments(plan))
    folder = lab.store / f'campaign_reports/{REPORT}'
    if location == 'receipt':
        path = folder / 'receipt.json'; payload = load_json(path); payload['record_sha256'] = 'f' * 64
    else:
        path = folder / 'record.json'; payload = load_json(path)
        if location == 'rehash_declaration':
            payload['probability_analysis']['declaration']['source']['origin'] = 'MEASURED_REPORTED'
        else:
            payload['probability_analysis']['thresholds'][0]['exceedance_count'] += 1
    save_json(path, payload)
    if location.startswith('rehash'):
        save_json(folder / 'receipt.json', {'report_id': REPORT, 'record_sha256': _sha(path)})
    with pytest.raises(ValueError):
        lab.inspect_campaign_report(REPORT)


@pytest.mark.parametrize('mutation', ['points', 'version', 'numpy_version', 'engine', 'strength', 'optimization', 'seed'])
def test_exact_frozen_sampler_and_points_refuse_changed_replay(tmp_path, monkeypatch, mutation):
    lab, _, plan, result = _completed(tmp_path)
    report = lab.create_campaign_report(**_arguments(plan))
    changed_plan, changed_result = deepcopy(plan), deepcopy(result)
    if mutation == 'points':
        changed_plan['samples'][0]['values']['research_x'] += .01
        changed_result['samples'][0]['values']['research_x'] += .01
    else:
        values = {'version': 'historical-unsupported', 'numpy_version': 'historical-unsupported',
                  'engine': 'test.other_sampling', 'strength': True, 'optimization': 'random-cd', 'seed': 14}
        changed_plan['algorithm'][mutation] = values[mutation]
        changed_result['algorithm'][mutation] = values[mutation]
    # This isolates the probability seam after the ordinary source reader. The
    # full Core tamper controls below retain their actual ledger/journal checks.
    monkeypatch.setattr(campaign_report, '_campaign', lambda *args:
                        ('doe', lab.store / f'campaigns/{CAMPAIGN}', changed_plan, changed_result))
    with pytest.raises(ValueError):
        lab.create_campaign_report(**_arguments(plan, report_id='R-refused-replay'))
    assert not (lab.store / 'campaign_reports/R-refused-replay').exists()
    assert report['probability_analysis']['declaration']['seed'] == 13


@pytest.mark.parametrize('target', ['plan', 'result', 'native', 'candidate', 'journal'])
def test_native_source_ledger_and_candidate_tamper_is_refused_on_saved_report(tmp_path, target):
    lab, _, plan, result = _completed(tmp_path)
    lab.create_campaign_report(**_arguments(plan))
    campaign = lab.store / f'campaigns/{CAMPAIGN}'
    paths = {'plan': campaign / 'plan.json', 'result': campaign / 'result.json',
             'native': lab.store / f"experiments/{result['samples'][0]['model_experiment_id']}/result.json",
             'candidate': campaign / 'candidates/0001.json', 'journal': campaign / 'journal/0001.json'}
    path = paths[target]; payload = load_json(path)
    if target == 'native':
        payload['metrics']['synthetic_constraint']['value'] += .1
    else:
        payload['TEST_ONLY_tamper'] = True
    save_json(path, payload)
    with pytest.raises(ValueError):
        lab.inspect_campaign_report(REPORT)


def test_adaptive_optimization_refuses_even_when_uncertainty_is_design_space(tmp_path):
    lab, adapter = synthetic_lab(tmp_path, SignedResponseModel())
    register_x(lab); lab.optimization_adapters = {'scipy.differential_evolution': ScipyDifferentialEvolution()}
    plan = lab.plan_model_optimization(study_id=STUDY, campaign_id='C-adaptive', backend=adapter.backend,
        settings=template_settings(), parameter_ids=['research_x'], seed=13, max_generations=1,
        population_size=5, objective={'source': 'model', 'metric': 'synthetic_objective', 'unit': '1',
                                     'direction': 'minimize'}, constraints=[])
    lab.run_optimization(plan['campaign_id'])
    before = _files(lab.store)
    with pytest.raises(ValueError, match='never adaptive'):
        lab.create_campaign_report(**_arguments(plan,
            uncertainty={'interpretation': 'DESIGN_SPACE_ONLY', 'reference': 'TEST_ONLY adaptive set'}))
    assert _files(lab.store) == before


def test_failed_execution_or_unfinished_plan_cannot_be_probability_doe(tmp_path):
    adapter = SignedResponseModel(crash=True)
    lab, adapter = synthetic_lab(tmp_path, adapter)
    lab.doe_adapters = {model_doe.ENGINE: ScipyLatinHypercube()}; register_x(lab)
    plan = lab.plan_model_doe(study_id=STUDY, campaign_id=CAMPAIGN, backend=adapter.backend,
        settings=template_settings(), parameter_ids=['research_x'], sample_count=4, seed=13)
    with pytest.raises(ValueError, match='Complete'):
        lab.create_campaign_report(**_arguments(plan))
    with pytest.raises(RuntimeError, match='execution failed'):
        lab.run_doe(CAMPAIGN)
    partial = lab.inspect_doe(CAMPAIGN)
    assert partial['status'] == 'FAILED_EXECUTION' and partial['completed_samples'] == 1
    with pytest.raises(ValueError, match='Complete'):
        lab.create_campaign_report(**_arguments(plan))
    assert not (lab.store / f'campaign_reports/{REPORT}').exists() and adapter.calls == 1


def test_fixed_cad_condition_doe_uses_analysis_results_and_preserves_one_parent(fixed_lab):
    lab = fixed_lab
    plan = lab.plan_condition_doe(study_id='S-conditions', campaign_id=CAMPAIGN,
        conditions_id='C-conditions', parameter_ids=['elastic_E'], sample_count=4, seed=13,
        required_validations={'cad': [], 'analysis': ['test_only_response']})
    result = lab.run_doe(CAMPAIGN); before = _files(lab.store)
    definition = [{'metric': 'max_displacement', 'unit': 'mm', 'direction': 'minimize'}]
    probability = _probability(plan, metric='max_displacement', unit='mm', value=.00075)
    report = lab.create_campaign_report(**_arguments(plan, response_definitions=definition, probability=probability))
    propagation = report['probability_analysis']
    assert propagation['sample_ids'] == [row['analysis_experiment_id'] for row in result['samples']]
    assert [s['responses']['max_displacement']['value'] for s in propagation['samples']] == [
        row['metrics']['analysis']['max_displacement']['value'] for row in result['samples']]
    assert 'E-cad' not in propagation['sample_ids']
    assert all(_files(lab.store)[name] == value for name, value in before.items())
    assert lab.inspect_campaign_report(REPORT) == report


def test_fixed_cad_rejected_condition_keeps_its_placeholder_and_never_borrows_parent(fixed_lab, monkeypatch):
    from caelab import fixed_cad_optimization
    from caelab.condition_parameters import ConditionInputRejected
    lab = fixed_lab
    original = fixed_cad_optimization.bind
    def bounded_test_domain(*args, **kwargs):
        values = args[2]
        if values['material_M1_E'] < 200000:
            raise ConditionInputRejected('TEST_ONLY stricter hypothetical material admissibility')
        return original(*args, **kwargs)
    monkeypatch.setattr(fixed_cad_optimization, 'bind', bounded_test_domain)
    plan = lab.plan_condition_doe(study_id='S-conditions', campaign_id=CAMPAIGN,
        conditions_id='C-conditions', parameter_ids=['elastic_E'], sample_count=4, seed=13)
    result = lab.run_doe(CAMPAIGN)
    report = lab.create_campaign_report(**_arguments(plan,
        response_definitions=[{'metric': 'max_displacement', 'unit': 'mm', 'direction': 'minimize'}],
        probability=_probability(plan, metric='max_displacement', unit='mm')))
    propagation = report['probability_analysis']
    rejected = [row for row in result['samples'] if row['analysis_experiment_id'] is None]
    assert rejected and propagation['counts']['excluded'] == len(rejected)
    for row in rejected:
        placeholder = f"E-{CAMPAIGN}-{row['index']:04d}"
        retained = next(item for item in propagation['samples'] if item['id'] == placeholder)
        assert retained['responses']['max_displacement'] == {'value': None, 'unit': 'mm', 'valid': False}
        assert retained['usable'] is False and not (lab.store / f'experiments/{placeholder}').exists()
    assert 'E-cad' not in propagation['sample_ids']
    assert lab.inspect_campaign_report(REPORT) == report


def test_legacy_cad_lhs_retains_failed_native_child_as_unknown_response(tmp_path):
    from caelab import Lab
    class FailedTestAnalysis(CountingAnalysis):
        def solve(self, parent, root, output, settings):
            self.calls += 1
            output.mkdir()
            (output / 'failed.txt').write_text('TEST_ONLY failed callback, no native backend')
            raise RuntimeError('TEST_ONLY execution failure')
    cad, analysis = SyntheticRetainedCAD(), FailedTestAnalysis()
    lab = Lab(tmp_path, adapters={cad.backend: cad}, analysis_adapters={analysis.backend: analysis},
              model_analysis_adapters={}, pde_adapters={},
              doe_adapters={model_doe.ENGINE: ScipyLatinHypercube()}, optimization_adapters={})
    lab.create_study(STUDY, 'TEST_ONLY legacy CAD DOE', 'Retain failed children?',
                     'TEST_ONLY unknown outcomes', 'No physical claim')
    lab.register_parameter(STUDY, cad.backend, 'roller_support', 'support_width_mm',
                           'width', 'TEST_ONLY width', 28, 60)
    plan = lab.plan_doe(study_id=STUDY, campaign_id=CAMPAIGN, backend=cad.backend,
        model='roller_support', parameter_ids=['width'], sample_count=2, seed=13,
        analysis_backend=analysis.backend, analysis_settings={'TEST_ONLY': True})
    result = lab.run_doe(CAMPAIGN)
    assert len(result['samples']) == 2 and all(row['analysis_status'] == 'FAILED_EXECUTION'
                                             for row in result['samples'])
    report = lab.create_campaign_report(**_arguments(plan,
        response_definitions=[{'metric': 'test_displacement', 'unit': 'mm', 'direction': 'minimize'}],
        probability=_probability(plan, metric='test_displacement', unit='mm')))
    propagation = report['probability_analysis']
    assert propagation['sample_ids'] == [row['analysis_experiment_id'] for row in result['samples']]
    assert propagation['counts'] == {'declared': 2, 'valid': 0, 'excluded': 2}
    assert all(row['responses']['test_displacement']['value'] is None for row in propagation['samples'])
    assert propagation['thresholds'][0]['probability_estimate'] is None
    assert propagation['thresholds'][0]['unknown_outcome_fraction_bounds'] == {'lower': 0., 'upper': 1.}
    assert lab.inspect_campaign_report(REPORT) == report and analysis.calls == 2


@pytest.mark.parametrize('add_or_drop', ['add_to_legacy', 'drop_analysis', 'drop_declaration'])
def test_unpaired_probability_payload_is_never_returned_as_verified(tmp_path, add_or_drop):
    lab, _, plan, _ = _completed(tmp_path)
    lab.create_campaign_report(**_arguments(plan, probability=None if add_or_drop == 'add_to_legacy'
                                            else _probability(plan)))
    folder = lab.store / f'campaign_reports/{REPORT}'; path = folder / 'record.json'
    record = load_json(path)
    if add_or_drop == 'add_to_legacy':
        record['probability_analysis'] = {'TEST_ONLY_unverified': 'not replayed'}
    elif add_or_drop == 'drop_analysis':
        del record['probability_analysis']
    else:
        del record['declaration']['probability']
    save_json(path, record)
    save_json(folder / 'receipt.json', {'report_id': REPORT, 'record_sha256': _sha(path)})
    with pytest.raises(ValueError, match='presence differs'):
        lab.inspect_campaign_report(REPORT)


def test_false_lhs_zero_candidate_is_not_relabelled_as_probability(fixed_lab, monkeypatch):
    lab = fixed_lab
    register_condition(lab, input_id='load_L1_FZ', parameter_id='force_z', lower=-300, upper=300)
    sampler = lab.doe_adapters[model_doe.ENGINE]; original = sampler.sample
    def altered_points(*args, **kwargs):
        points, metadata = original(*args, **kwargs)
        points[0]['force_z'] = 0.
        return points, metadata
    monkeypatch.setattr(sampler, 'sample', altered_points)
    plan = lab.plan_condition_doe(study_id='S-conditions', campaign_id=CAMPAIGN,
        conditions_id='C-conditions', parameter_ids=['force_z'], sample_count=2, seed=13)
    result = lab.run_doe(CAMPAIGN)
    assert result['samples'][0]['analysis_experiment_id'] is None
    with pytest.raises(ValueError, match='exact seeded LHS'):
        lab.create_campaign_report(**_arguments(plan,
            response_definitions=[{'metric': 'max_displacement', 'unit': 'mm', 'direction': 'minimize'}],
            probability=_probability(plan, metric='max_displacement', unit='mm')))
    assert not (lab.store / f'campaign_reports/{REPORT}').exists()
