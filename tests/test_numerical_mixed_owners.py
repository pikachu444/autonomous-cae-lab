"""Real SciPy ODE, actual owner/JobManager, and relocated fresh Python processes.

Material/Simulation cases at the bottom are explicitly controlled-evaluator
owner tests, not FELUPE/FEniCSx/native runtime claims.
"""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import uuid

import pytest

from caelab import dimensioned_models as dm, model_parameters as mp, numerical as n
from caelab import variable_domains as vd, variable_binding as vb
from caelab.backends import get_backend
from caelab.storage import canonical_hash
from caelab.workbench import Workbench
from caelab.evaluation_definition import document_reference, default_draft, input_descriptors
from examples.numerical_mixed_domains import (model_settings, declarations, explicit_candidates,
    reference_check, command, forbid_runtime)


@pytest.fixture(scope='module')
def real_ode(tmp_path_factory):
    from caelab.adapters.native_evaluation import NativeEvaluationFactory
    root = tmp_path_factory.mktemp('mixed-real-ode')
    factory = NativeEvaluationFactory(dm.ODE, root/'evaluations', ['temperature'], retained_root=root)
    raw = declarations()
    result = n.run_doe(factory, raw, settings=model_settings(), candidates=explicit_candidates())
    return root, raw, result


def test_real_four_solver_methods_full_clock_and_actual_saved_input(real_ode):
    root, _, result = real_ode
    checked = reference_check(result, output_root=root)
    assert len(checked['records']) == 24
    assert len({r['final_temperature_K'] for r in checked['records']}) > 6
    assert {r['method'] for r in checked['records']} == set(vb.ODE_METHODS)
    assert result['timing']['model_calls'] == 24
    (root/'reference.json').write_text(json.dumps(checked, indent=2))


def pure_run(raw):
    source = {'id': 'Qsource', 'kind': 'pde', 'saved_revision': 'Rsaved', 'input_revision': 'Iinput',
              'draft': {'backend': dm.ODE, 'settings': model_settings()}}
    ref = document_reference(source)
    draft = {'mode': 'request', 'source': ref, 'request': {'operation': 'doe',
             'inputs': {'backend': dm.ODE, 'settings': model_settings(), 'variables': raw}}}
    return {'draft': draft, 'input_sha256': canonical_hash(draft)}, source


def test_actual_pde_preview_replays_bind_without_resolving(real_ode):
    from caelab.pde_candidate import prepare_candidate
    _, raw, result = real_ode
    run, source = pure_run(raw)
    with forbid_runtime():
        prepared = prepare_candidate(run, result, result['candidates'][-1]['candidate_id'], source)
    assigned = result['candidates'][-1]['values']
    params = {p['name']: p['value'] for p in prepared['draft']['settings']['parameters']}
    assert type(params['count']) is int and params['sink_rate'] == assigned['sink_rate']
    assert prepared['draft']['settings']['solver']['method'] == assigned[vb.ODE_METHOD_ID]
    assert prepared['source']['domain_assignment'] == result['candidates'][-1]['domain_assignment']


@pytest.mark.parametrize('mutation', ['fractional', 'enum', 'dependent', 'bound_input', 'missing_receipt',
                                      'failed', 'source', 'declaration_order', 'choice_order', 'owner_revision'])
def test_forged_or_stale_read_is_blocked_without_work(real_ode, mutation):
    from caelab.pde_candidate import prepare_candidate
    _, raw, original = real_ode
    result = deepcopy(original); run, source = pure_run(deepcopy(raw)); row = result['candidates'][0]
    if mutation == 'fractional': row['values']['count'] = 1.5
    elif mutation == 'enum': row['values'][vb.ODE_METHOD_ID] = 'LSODA'
    elif mutation == 'dependent': row['values']['sink_rate'] = .9
    elif mutation == 'bound_input': row['input_binding']['bound_settings_sha256'] = '0'*64
    elif mutation == 'missing_receipt': row.pop('input_binding')
    elif mutation == 'failed': row['execution_status'] = 'FAILED'
    elif mutation == 'source': source['draft']['settings']['time']['end'] = 3.
    elif mutation == 'owner_revision': source['input_revision'] = 'Iother'
    elif mutation == 'declaration_order': result['domain_input']['declarations'].reverse()
    elif mutation == 'choice_order': result['variables'][-1]['choices'].reverse()
    old_source, old_result = deepcopy(source), deepcopy(result)
    with forbid_runtime(), pytest.raises(ValueError):
        prepare_candidate(run, result, row['candidate_id'], source)
    assert source == old_source and canonical_hash(result) == canonical_hash(old_result)


def test_owner_save_relocated_cold_edit_resave_third_process(tmp_path):
    script = Path(__file__).resolve().parents[1]/'examples/numerical_mixed_domains.py'
    output = tmp_path/'owner-evidence'
    completed = subprocess.run([sys.executable, str(script), '--output', str(output), '--owner-cold'],
        cwd=tmp_path, text=True, encoding='utf-8', capture_output=True, timeout=120)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    receipt = json.loads((output/'completed.json').read_text())
    assert receipt['owner']['warm_read_save_adopt_runtime_calls'] == 0
    assert receipt['cold']['cold_read_preview_save_runtime_calls'] == 0
    assert receipt['final']['read_runtime_calls'] == 0 and receipt['final']['cold_edit_persisted']
    assert receipt['final']['pid'] != receipt['cold']['pid']
    assert not (output/'original-workspace').exists()
    assert receipt['cold']['edited_draft']['settings']['time']['end'] == 3.


def save(wb, kind, draft):
    return command(wb, wb.document_open(kind=kind, draft=draft), 'document.save')['document']


def execute_plan(wb, source, inputs, count):
    request = {'purpose': 'Mixed owner test', 'operation': 'doe', 'inputs': deepcopy(inputs),
               'budget': {'evaluations': count}}
    plan = wb.document_open(kind='numerical', draft={'mode': 'request', 'request': request,
                                                   'source': document_reference(source)})
    assert not plan['diagnostics'], plan['diagnostics']
    job = command(wb, plan, 'numerical.run')['job']['id']
    wb.manager._futures[job].result(timeout=120)
    assert wb.manager.status(job)['state'] == 'SUCCEEDED', wb.manager.status(job)
    plan = command(wb, wb.document_read(plan['id']), 'document.save')['document']
    return plan, job, wb.document_result(plan['id'], job)


def test_real_evaluation_definition_stage_enum_and_dependent_adopt(tmp_path):
    wb = Workbench(tmp_path)
    try:
        pde = save(wb, 'pde', {'backend': dm.ODE, 'settings': model_settings()})
        definition = default_draft()
        definition['stages'] = [{'id': 'StageOde', 'name': '냉각', 'source': document_reference(pde)}]
        raw = declarations(('RK45', 'DOP853'))
        definition['bindings'] = [{'id': v['id'], 'stage': 'StageOde', 'input_id': v['id'], 'unit': v['unit']} for v in raw]
        definition['responses'] = [{'id': 'temperature', 'stage': 'StageOde', 'response': 'temperature', 'unit': 'K'}]
        owner = save(wb, 'evaluation', definition)
        cases = [explicit_candidates(('RK45', 'DOP853'))[0], explicit_candidates(('RK45', 'DOP853'))[-1]]
        plan, job, result = execute_plan(wb, owner, {'backend': 'evaluation.definition',
            'settings': {'definition_ref': document_reference(owner)}, 'variables': raw, 'candidates': cases}, 2)
        assert result['candidates'][0]['values'][vb.ODE_METHOD_ID] == 'RK45'
        assert result['candidates'][-1]['values']['sink_rate'] == 3 * .2
        retained = list((wb.root/'results'/job/'evaluations').glob('candidate-*/input.json'))
        assert len(retained) == 2
        assert {json.loads(p.read_text())['values'][vb.ODE_METHOD_ID] for p in retained} == {'RK45', 'DOP853'}
        original = deepcopy(wb.document_read(pde['id']))
        with forbid_runtime():
            preview = wb.domain_candidate_preview(plan['id'], job, cases[-1]['candidate_id'])
            assert len(preview['branch_plan']) == 1
            branch = preview['branch_plan'][0]['draft']['settings']
            assert branch['solver']['method'] == 'DOP853'
            assert {p['name']: p['value'] for p in branch['parameters']}['sink_rate'] == 3*.2
            adopted = wb.domain_candidate_adopt(plan['id'], job, cases[-1]['candidate_id'],
                target_document_id=owner['id'], session_id=owner['session_id'],
                expected_generation=owner['generation'], command_id='C' + uuid.uuid4().hex)['document']
            adopted = command(wb, adopted, 'document.save')['document']
            assert adopted['draft']['stages'][0]['source']['document_id'] != pde['id']
            assert wb.document_read(pde['id']) == original
            assert canonical_hash(wb.document_result(plan['id'], job)) == canonical_hash(result)
    finally:
        assert wb.shutdown()['joined']
    # A separate owner instance loads the adopted independent stage revision.
    with forbid_runtime():
        wb = Workbench(tmp_path)
        try:
            reopened = wb.document_open(kind='evaluation', document_id=owner['id'])
            assert reopened['draft'] == adopted['draft']
            wb.evaluation_documents.snapshots(reopened['draft'], reopened)
        finally:
            assert wb.shutdown()['joined']


@pytest.mark.parametrize('kind', ['material', 'simulation'])
def test_controlled_typed_owner_preview_adopt_no_native_or_felupe(tmp_path, monkeypatch, kind):
    from caelab.material_document import default_draft as material_draft
    from caelab.simulation_document import default_draft as simulation_draft
    wb = Workbench(tmp_path)
    try:
        source = save(wb, kind, material_draft() if kind == 'material' else simulation_draft('thermal.fenicsx.rectangle'))
        descriptor = input_descriptors(source['draft'])[0]
        low = descriptor['value']
        raw = [{'id': descriptor['id'], 'kind': 'discrete', 'unit': descriptor['unit'], 'values': [low, 1.1*low]}]
        # Real Numerical normalization and JobManager/owner, controlled model only.
        inputs = {'backend': source['draft']['backend'], 'settings': deepcopy(source['draft']['settings']),
                  'variables': raw, 'candidates': [{'candidate_id': 'Cchosen', 'values': {descriptor['id']: 1.1*low}}]}
        def controlled(operation, arguments, job_id):
            return n.run_doe(lambda v, s: {'execution_status': 'SUCCEEDED', 'responses': {},
                'diagnostics': {'test_evaluator': 'controlled-not-native', 'actual_values': deepcopy(v)}},
                raw, settings=inputs['settings'], candidates=inputs['candidates'])
        monkeypatch.setattr(wb.manager, '_execute', controlled)
        plan, job, result = execute_plan(wb, source, inputs, 1)
        with forbid_runtime():
            preview = wb.domain_candidate_preview(plan['id'], job, 'Cchosen')
            assert preview['parameter_assignments'][descriptor['id']] == 1.1*low
            adopted = wb.domain_candidate_adopt(plan['id'], job, 'Cchosen', target_document_id=source['id'],
                session_id=source['session_id'], expected_generation=source['generation'],
                command_id='C' + uuid.uuid4().hex)['document']
            assert adopted['draft'] == preview['draft']
            adopted = command(wb, adopted, 'document.save')['document']
            assert canonical_hash(wb.document_result(plan['id'], job)) == canonical_hash(result)
            # Source changed after adoption; stale reuse must not overwrite it.
            with pytest.raises((ValueError, RuntimeError)):
                wb.domain_candidate_adopt(plan['id'], job, 'Cchosen', target_document_id=source['id'],
                    session_id=source['session_id'], expected_generation=source['generation'],
                    command_id='C' + uuid.uuid4().hex)
    finally:
        assert wb.shutdown()['joined']


def test_enum_checked_setter_preserves_trusted_paths_and_full_input_set(monkeypatch):
    adapter, settings = get_backend(dm.ODE), model_settings()
    for i in range(64-len(settings['parameters'])):
        settings['parameters'].append({'name': 'unused' + str(i), 'unit': '1', 'value': 1.})
    assert len(mp._inputs(adapter, settings)) == 65
    bound = mp.bind(adapter, settings, {vb.ODE_METHOD_ID: 'BDF', 'count': 2})
    assert bound['solver']['method'] == 'BDF'
    with pytest.raises(ValueError):
        mp._validated_inputs(mp._inputs(adapter, settings))  # other adapters still bounded at 32
    with pytest.raises(ValueError): mp.bind(adapter, settings, {vb.ODE_METHOD_ID: 1})
    with pytest.raises(ValueError): mp.bind(adapter, settings, {vb.ODE_METHOD_ID: 'LSODA'})
    original = adapter.bind_inputs
    def wrong_settings(s, v):
        result = original(s, v); result['time']['end'] += 1; return result
    monkeypatch.setattr(adapter, 'bind_inputs', wrong_settings)
    with pytest.raises(ValueError, match='outside its declared locations'):
        mp.bind(adapter, settings, {vb.ODE_METHOD_ID: 'BDF'})


def test_real_ode_de_best_uses_physical_values_not_codes(tmp_path):
    from caelab.adapters.native_evaluation import NativeEvaluationFactory
    factory = NativeEvaluationFactory(dm.ODE, tmp_path/'evaluations', ['temperature'], retained_root=tmp_path)
    table = n.optimize(factory, declarations(('RK45','DOP853')),
        {'response':'temperature','unit':'K','reduction':'final','direction':'minimize'},
        settings=model_settings(), seed=4, options={'population_size':16,'max_generations':30,'retain_responses':'all'},
        execution={'max_evaluations':12})
    assert table['best']['values']['count'] == 3 and table['best']['values']['base_rate'] == .2
    assert table['timing']['model_calls'] <= 12
    report = reference_check(table, output_root=tmp_path)
    assert len(report['records']) == table['timing']['model_calls']
    assert table['solver_dispatch']['feedback_cache_hits'] > 0
