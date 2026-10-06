"""Real Core/DE orchestration with TEST ONLY native response substitution."""
from copy import deepcopy
import hashlib

import pytest

from caelab import declared_model, engine, model_parameters, optimization
from caelab.storage import load_json
from test_model_optimization import _lab, _plan


@pytest.fixture(autouse=True)
def fake_source(monkeypatch):
    identity = {'core_commit': 'TEST_ONLY', 'core_dirty': True, 'core_source_sha256': 'a'*64}
    for module in (declared_model, engine, model_parameters, optimization):
        monkeypatch.setattr(module, 'source_identity', lambda root: deepcopy(identity))
    monkeypatch.setattr(model_parameters, 'core_source_hash', lambda root: identity['core_source_sha256'])


def parent(lab):
    _plan(lab, campaign_id='C-template', constraints=[])
    return lab.plan_multiobjective(parent_id='M-tradeoff', template_campaign_id='C-template',
        objectives=[{'source':'model','metric':'synthetic_objective','unit':'1','direction':'minimize'},
                    {'source':'model','metric':'synthetic_constraint','unit':'1','direction':'minimize'}],
        primary_index=0, threshold_grid=[[{'source':'model','metric':'synthetic_constraint','unit':'1','limit':limit,'scale':1.0}] for limit in (2.5,3.5)],
        child_budget={'max_generations':1,'population_size':5},seed=13,total_evaluation_budget=40)


def files(path):
    return {p.relative_to(path).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
            for p in path.rglob('*') if p.is_file() and not p.name.endswith('.lock')}


def test_existing_native_feedback_real_de_children_and_independent_pareto(tmp_path):
    lab, adapter = _lab(tmp_path); parent(lab)
    result = lab.run_multiobjective('M-tradeoff')
    rows = result['record']['evaluations']
    assert result['integrity']=='VERIFIED' and result['record']['status']=='COMPLETED_REVIEW_REQUIRED'
    assert len(result['record']['children'])==2 and len(rows)>0
    valid = [r for r in rows if r['eligible']]
    vectors = {r['experiment_id']:[v['metric']['value'] for v in r['vector']] for r in valid}
    expected = [identifier for identifier,a in vectors.items() if not any(
        all(b[i]<=a[i] for i in range(2)) and any(b[i]<a[i] for i in range(2)) for b in vectors.values())]
    assert set(result['record']['pareto']['nondominated_ids'])==set(expected)
    for row in valid:
        raw = lab.inspect_experiment(row['experiment_id'])
        assert [raw['metrics'][v['definition']['metric']]['value'] for v in row['vector']]==vectors[row['experiment_id']]
    original=files(lab.store); calls=deepcopy(adapter.calls)
    assert lab.inspect_multiobjective('M-tradeoff')==result
    assert lab.run_multiobjective('M-tradeoff')==result
    assert files(lab.store)==original and adapter.calls==calls
    assert result['record']['decision']=='NOT_RELEASED' and result['record']['physical_qualification']=='UNKNOWN'


def test_owned_child_can_resume_after_completed_first_child_without_reexecution(tmp_path, monkeypatch):
    lab, adapter = _lab(tmp_path); parent(lab)
    real=lab.run_optimization; count=0
    def interrupted(identifier):
        nonlocal count
        count+=1
        if count==2:raise RuntimeError('TEST ONLY cooperative interruption before native')
        return real(identifier)
    monkeypatch.setattr(lab,'run_optimization',interrupted)
    with pytest.raises(RuntimeError):lab.run_multiobjective('M-tradeoff')
    original=files(lab.store/'experiments'); calls=deepcopy(adapter.calls)
    assert lab.inspect_multiobjective('M-tradeoff')['record']['status']=='PARTIAL'
    monkeypatch.setattr(lab,'run_optimization',real)
    complete=lab.run_multiobjective('M-tradeoff')
    assert complete['record']['status']=='COMPLETED_REVIEW_REQUIRED'
    assert all(files(lab.store/'experiments')[name]==sha for name,sha in original.items())
    assert adapter.calls>calls


def test_ambiguous_unbound_child_is_not_adopted_or_replayed(tmp_path):
    lab,adapter=_lab(tmp_path);p=parent(lab)
    child=p['children'][0];folder=lab.store/'optimizations'/child['campaign_id'];folder.mkdir(parents=True)
    old=files(lab.store); calls=deepcopy(adapter.calls)
    with pytest.raises(ValueError,match='UNKNOWN child binding'):lab.run_multiobjective('M-tradeoff')
    assert files(lab.store)==old and adapter.calls==calls


def test_changed_parent_or_native_result_is_rejected_on_reopen(tmp_path):
    lab,_=_lab(tmp_path);parent(lab); lab.run_multiobjective('M-tradeoff')
    path=lab.store/'multiobjective/M-tradeoff/result.json';original=path.read_bytes()
    path.write_bytes(original.replace(b'UNKNOWN',b'PASSED_',1))
    with pytest.raises(ValueError):lab.inspect_multiobjective('M-tradeoff')
    path.write_bytes(original)
    path=lab.store/'multiobjective/M-tradeoff/plan.json';path.write_bytes(path.read_bytes()+b' ')
    with pytest.raises(ValueError):lab.inspect_multiobjective('M-tradeoff')


def test_fixed_cad_parent_and_report_catalogue_use_native_solver_not_cad(tmp_path, monkeypatch):
    """TEST ONLY verified-plan seams; no CAD/native/provider execution."""
    from types import SimpleNamespace
    from caelab import multiobjective
    from caelab.optimizers.epsilon_campaign import source_pins_for
    from caelab.storage import save_json
    from apps.lab.service import LabService
    from apps.lab import reporting
    from test_epsilon_campaign import _template, _objectives

    template = _template()
    for key in list(template):
        if key.startswith('model_'):
            del template[key]
    template.update(route='fixed_cad_analysis', backend='TEST_ONLY_CAD', model='retained_model',
                    cad_adapter_version='test-cad-1', cad_source_fingerprint={'commit': 'TEST_ONLY'},
                    analysis_adapter_version='test-analysis-1',
                    analysis={'backend': 'TEST_ONLY_ANALYSIS', 'settings': {'preserved': True}},
                    fixed_cad={'conditions_id': 'C-saved', 'template_revision': 'e'*64,
                               'source': {'experiment_id': 'E-parent', 'cad_revision': 'f'*64,
                                          'result_sha256': 'a'*64}},
                    required_validations={'cad': [], 'analysis': ['test_numerical']})
    template['variables'][0]['target'] = 'analysis_conditions'
    for definition in [template['objective'], *template['constraints']]:
        definition['source'] = 'analysis'
    objectives = _objectives()
    for definition in objectives:
        definition['source'] = 'analysis'
    folder = tmp_path/'optimizations/C-original'
    save_json(folder/'plan.json', template)
    lab = SimpleNamespace(store=tmp_path,
        adapters={'TEST_ONLY_CAD': SimpleNamespace(default_metrics=('volume',))},
        analysis_adapters={'TEST_ONLY_ANALYSIS': SimpleNamespace(default_metrics=('loss', 'gain'))},
        model_analysis_adapters={}, inspect_optimization=lambda _: {'status': 'PLANNED'},
        campaign_reports=lambda _: [])
    monkeypatch.setattr(multiobjective, '_plan', lambda *_: (template, folder, None, None, {}))
    monkeypatch.setattr(optimization, '_verify_sources', lambda *_: None)
    result = multiobjective.create(lab, parent_id='M-fixed', template_campaign_id='C-original',
        objectives=objectives, primary_index=0,
        threshold_grid=[[{'source': 'analysis', 'metric': 'gain', 'unit': 'N', 'limit': -2., 'scale': 1.}]],
        child_budget={'max_generations': 1, 'population_size': 5}, seed=13, total_evaluation_budget=10)
    assert result['template_plan']['backend'] == 'TEST_ONLY_CAD'
    assert result['template_plan']['analysis']['backend'] == 'TEST_ONLY_ANALYSIS'
    assert result['children'][0]['request']['conditions_id'] == 'C-saved'
    assert result['source_pins'] == source_pins_for(template, result['template_plan_sha256'])
    service = LabService.__new__(LabService)
    service._selected = lambda: SimpleNamespace(lab=lab, path=tmp_path)
    service._campaign = lambda *_: ('optimization', folder)
    service._campaign_preflight = lambda *_args, **_kwargs: ('optimization', [])
    monkeypatch.setattr(reporting, 'recheck_records', lambda *_: None)
    assert service.campaign('C-original')['response_catalogue'] == ['loss', 'gain']
