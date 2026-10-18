"""Pure adoption over actual owners and controlled saved candidate results.

The queue only persists a supplied result; no numerical engine, solver, native
runtime or inference is executed.
"""
from copy import deepcopy
import time
from types import SimpleNamespace

import pytest

from caelab import domain_candidate
from caelab.evaluation_definition import default_draft, document_reference, input_descriptors
from caelab.numerical_document import request_draft
from caelab.pde_document import default_draft as pde_draft
from caelab.simulation_document import default_draft as simulation_draft
from caelab.storage import canonical_hash, load_json
from caelab.workbench import Workbench


@pytest.fixture
def workbench(tmp_path):
    wb = Workbench(tmp_path)
    yield wb
    assert wb.shutdown()['joined']


def command(wb, document, operation, arguments=None):
    return wb.document_command(document['id'], operation, arguments or {}, session_id=wb.session_id,
        expected_generation=document['generation'])['document']


def saved(wb, kind, draft=None, title=None):
    return command(wb, wb.document_open(kind=kind, draft=draft, title=title), 'document.save')


def candidate_plan(wb, source, inputs, *, result_mutation=None, operation='doe'):
    request = {'purpose': 'Controlled saved candidate selection', 'operation': operation,
        'inputs': deepcopy(inputs), 'budget': {'evaluations': 1}}
    variables = deepcopy(inputs['variables'])
    values = {row['id']: row['value'] for row in variables}
    result = {'kind': 'doe', 'execution_status': 'SUCCEEDED', 'variables': variables,
        'responses': {}, 'candidates': [{'candidate_id': 'Cselected', 'values': values,
                                        'execution_status': 'SUCCEEDED', 'responses': {}, 'diagnostics': {}}]}
    if operation == 'fit':
        result['kind'] = 'fit'
        result['candidates'][0]['objective'] = 0.0
    if result_mutation:
        result_mutation(result)
    supplied = deepcopy(result)
    wb.manager._execute = lambda operation, arguments, job_id: deepcopy(supplied)
    plan = wb.document_open(kind='numerical', draft=request_draft(request, source=document_reference(source)))
    receipt = wb.document_command(plan['id'], 'numerical.run', {}, session_id=wb.session_id, expected_generation=0)
    job_id = receipt['job']['id']
    deadline = time.monotonic() + 3
    while wb.manager.status(job_id)['state'] not in {'SUCCEEDED', 'FAILED'}:
        assert time.monotonic() < deadline
        time.sleep(.005)
    plan = command(wb, wb.document_read(plan['id']), 'document.save')
    return SimpleNamespace(plan=plan, job_id=job_id, candidate_id='Cselected', source=source,
        payload={'target_document_id': source['id'], 'session_id': wb.session_id,
                 'expected_generation': source['generation'], 'command_id': 'Cadoptselected'})


def simulation_scene(wb, *, result_mutation=None, input_mutation=None, operation='doe'):
    source = saved(wb, 'simulation', simulation_draft('thermal.fenicsx.rectangle'))
    descriptor = input_descriptors(source['draft'])[0]
    inputs = {'backend': source['draft']['backend'], 'settings': deepcopy(source['draft']['settings']),
        'variables': [{'id': descriptor['id'], 'unit': descriptor['unit'], 'lower': descriptor['value'] / 2,
                       'upper': descriptor['value'] * 2, 'value': descriptor['value'] * 1.1}], 'count': 1}
    if input_mutation:
        input_mutation(inputs)
    return candidate_plan(wb, source, inputs, result_mutation=result_mutation, operation=operation)


def evaluation_scene(wb, *, duplicate_stage=False):
    domains = [saved(wb, 'material'), saved(wb, 'simulation', simulation_draft('thermal.fenicsx.rectangle')),
               saved(wb, 'pde', pde_draft('pde.fenicsx.coupled'))]
    draft = default_draft()
    descriptors = [input_descriptors(document['draft'])[0] for document in domains]
    variables = []
    for index, (document, descriptor) in enumerate(zip(domains, descriptors)):
        stage_id, research_id = 'Stage' + str(index), 'Input' + str(index)
        draft['stages'].append({'id': stage_id, 'name': 'Stage ' + str(index), 'source': document_reference(document)})
        draft['bindings'].append({'id': research_id, 'stage': stage_id, 'input_id': descriptor['id'], 'unit': descriptor['unit']})
        variables.append({'id': research_id, 'unit': descriptor['unit'], 'lower': descriptor['value'] / 2,
                          'upper': descriptor['value'] * 2, 'value': descriptor['value'] * 1.1})
    if duplicate_stage:
        draft['stages'].append({**deepcopy(draft['stages'][0]), 'id': 'StageTwin', 'name': 'Same source and assignment'})
        draft['bindings'].append({**deepcopy(draft['bindings'][0]), 'id': 'InputTwin', 'stage': 'StageTwin'})
        variables.append({**deepcopy(variables[0]), 'id': 'InputTwin'})
    source = saved(wb, 'evaluation', draft)
    scene = candidate_plan(wb, source, {'backend': 'evaluation.definition', 'settings': {'definition_ref': document_reference(source)},
                                      'variables': variables, 'count': 1})
    scene.domains = domains
    return scene


def prepare(wb, scene):
    return domain_candidate.preview(wb, scene.plan['id'], scene.job_id, scene.candidate_id)


def adopt(wb, scene):
    return domain_candidate.adopt(wb, scene.plan['id'], scene.job_id, scene.candidate_id, **scene.payload)


def test_simulation_preview_is_pure_and_adoption_uses_owner_undo(workbench):
    wb = workbench
    scene = simulation_scene(wb)
    documents_before = {row['id'] for row in wb.documents()['documents']}
    preview = prepare(wb, scene)
    assert preview['target_kind'] == 'simulation' and preview['candidate_id'] == scene.candidate_id
    assert preview['source'] == document_reference(scene.source)
    assert preview['executed'] is False and preview['branch_plan'] == []
    assert preview['result_sha256'] == canonical_hash(wb.document_result(scene.plan['id'], scene.job_id))
    assert preview['changes'] == [{'path': ['inputs', 'conductivity'], 'before': 200.0,
                                   'after': 220.00000000000003, 'unit': 'W/(m*K)'}]
    assert wb.document_read(scene.source['id'])['draft'] == scene.source['draft']
    assert {row['id'] for row in wb.documents()['documents']} == documents_before
    response = adopt(wb, scene)
    edited = response['document']
    assert response['executed'] is False and edited['generation'] == 1
    assert edited['draft'] == preview['draft'] and edited['can_undo']
    assert edited['adoptions'][0]['result_sha256'] == preview['result_sha256']
    assert adopt(wb, scene) == response
    assert wb.document_read(edited['id'])['generation'] == 1
    undone = command(wb, edited, 'document.undo')
    assert undone['draft'] == scene.source['draft']
    assert len(wb.manager.list()) == 1


@pytest.mark.parametrize('mutation,match', [
    (lambda r: r['candidates'][0].update(execution_status='FAILED'), 'actually evaluated'),
    (lambda r: r['candidates'][0].update(prediction_status='PREDICTED'), 'actually evaluated'),
    (lambda r: r['candidates'][0]['diagnostics'].update(evaluation_mode='PREDICTED'), 'actually evaluated'),
    (lambda r: r.update(candidates=[]), 'exactly once'),
    (lambda r: r['candidates'].append(deepcopy(r['candidates'][0])), 'exactly once'),
    (lambda r: r['variables'][0].update(unit='wrong'), 'variable IDs, units or bounds'),
    (lambda r: r['candidates'][0]['values'].update(conductivity=1000), 'outside submitted bounds'),
    (lambda r: r['candidates'][0]['values'].update(unknown=1), 'assignments differ'),
    (lambda r: r.update(kind='optimization'), 'result kind'),
])
def test_nonactual_or_mismatched_candidates_are_rejected_before_owner_edit(workbench, mutation, match):
    scene = simulation_scene(workbench, result_mutation=mutation)
    before = workbench.document_read(scene.source['id'])
    with pytest.raises(ValueError, match=match):
        prepare(workbench, scene)
    with pytest.raises(ValueError, match=match):
        adopt(workbench, scene)
    assert workbench.document_read(scene.source['id']) == before
    assert not (workbench.root / 'domain_adoptions').exists()


def test_evaluation_prepares_saved_material_simulation_pde_branches_then_only_edits_e(workbench):
    wb = workbench
    scene = evaluation_scene(wb)
    original_domains = {row['id']: wb.document_read(row['id']) for row in scene.domains}
    preview = prepare(wb, scene)
    assert preview['target_kind'] == 'evaluation'
    assert len(preview['branch_plan']) == 3
    assert {row['kind'] for row in preview['branch_plan']} == {'material', 'simulation', 'pde'}
    assert {row['stage'] for row in preview['changes']} == {'Stage0', 'Stage1', 'Stage2'}
    response = adopt(wb, scene)
    updated = response['document']
    assert updated['saved_revision'] != scene.source['saved_revision']
    assert updated['generation'] == 1 and not updated['dirty']
    assert len(response['branches']) == 3
    for before, after in zip(scene.source['draft']['stages'], updated['draft']['stages']):
        assert after['source']['document_id'] != before['source']['document_id']
        branch = wb.document_read(after['source']['document_id'])
        assert branch['generation'] == 0 and not branch['dirty']
        assert document_reference(branch) == after['source']
        assert branch['draft'] == next(row['draft'] for row in preview['branch_plan'] if after['id'] in row['stage_ids'])
    assert not wb.evaluation_inspect(updated['id'])['diagnostics']
    assert {row['id']: wb.document_read(row['id']) for row in scene.domains} == original_domains
    refs = deepcopy(updated['draft']['stages'])
    assert adopt(wb, scene) == response
    assert wb.document_read(updated['id'])['generation'] == 1
    undone = command(wb, updated, 'document.undo')
    assert undone['draft'] == scene.source['draft']
    for stage in refs:
        assert not wb.document_read(stage['source']['document_id'])['dirty']
    assert len(wb.manager.list()) == 1


@pytest.mark.parametrize('selected_shared', [True, False])
def test_shared_evaluation_candidate_preserves_logical_and_both_target_values(workbench, selected_shared):
    from examples.s2_mdo_adjoint import declarations
    from caelab.evaluation_shared_inputs import assign
    from caelab.evaluation_definition import bind_values, compile_definition
    wb = workbench
    models, draft, _ = declarations('mdo')
    domains = []
    for stage_id, title, backend, settings in models:
        domain = saved(wb, 'simulation', {'backend': backend, 'settings': settings}, title)
        domains.append(domain)
        draft['stages'].append({'id': stage_id, 'name': title, 'source': document_reference(domain)})
    if selected_shared:
        variable = {'id': 'Tref', 'unit': 'K', 'lower': 285., 'upper': 305., 'value': 300.}
    else:
        draft['bindings'].append({'id': 'k', 'stage': 'Heat', 'input_id': 'conductivity', 'unit': 'W/(m*K)'})
        variable = {'id': 'k', 'unit': 'W/(m*K)', 'lower': 5., 'upper': 50., 'value': 25.}
    source = saved(wb, 'evaluation', draft)
    scene = candidate_plan(wb, source, {'backend': 'evaluation.definition',
        'settings': {'definition_ref': document_reference(source)}, 'variables': [variable], 'count': 1})
    original_domains = {row['id']: wb.document_read(row['id']) for row in domains}
    original_jobs = deepcopy(wb.manager.list())
    before_documents = wb.documents()
    preview = prepare(wb, scene)
    assert wb.document_read(source['id']) == source and wb.documents() == before_documents  # Cancel means no command.
    expected = 300. if selected_shared else 293.15
    assert preview['draft']['bindings'][0]['value'] == expected
    if selected_shared:
        assert {'path': ['bindings', 'Tref'], 'before': 293.15, 'after': 300., 'unit': 'K'} in preview['changes']
        assert {row.get('stage') for row in preview['changes'] if 'stage' in row} == {'Heat', 'Structure'}
    response = adopt(wb, scene)
    updated = response['document']
    assert updated['draft']['bindings'][0]['value'] == expected
    compiled = compile_definition(updated['draft'], wb.evaluation_documents.snapshots(updated['draft'], updated))
    effective, _ = assign(updated['draft']['bindings'], {key: row['model'] for key, row in compiled['stages'].items()},
        {}, input_descriptors, bind_values)
    assert effective['Heat']['settings']['conductivity']['reference_temperature'] == expected
    assert effective['Structure']['settings']['material']['reference_temperature'] == expected
    assert {row['id']: wb.document_read(row['id']) for row in domains} == original_domains
    assert wb.manager.list() == original_jobs and adopt(wb, scene) == response
    assert wb.shutdown()['joined']
    cold = Workbench(wb.root.parent)
    try:
        reopened = cold.document_read(source['id'])
        assert reopened['draft'] == updated['draft'] and reopened['saved_revision'] == updated['saved_revision']
        fresh = compile_definition(reopened['draft'], cold.evaluation_documents.snapshots(reopened['draft'], reopened))
        effective, _ = assign(reopened['draft']['bindings'], {key: row['model'] for key, row in fresh['stages'].items()},
            {}, input_descriptors, bind_values)
        assert effective['Heat']['settings']['conductivity']['reference_temperature'] == expected
        assert effective['Structure']['settings']['material']['reference_temperature'] == expected
        assert {row['id'] for row in cold.manager.list()} == {row['id'] for row in original_jobs}
    finally:
        assert cold.shutdown()['joined']


def test_changed_original_target_is_never_overwritten(workbench):
    scene = simulation_scene(workbench)
    draft = deepcopy(scene.source['draft'])
    draft['settings']['conductivity']['value'] = 150
    edited = command(workbench, scene.source, 'simulation.update', {'draft': draft})
    with pytest.raises(ValueError, match='changed after this Plan'):
        prepare(workbench, scene)
    with pytest.raises(ValueError, match='changed after this Plan'):
        adopt(workbench, scene)
    assert workbench.document_read(edited['id']) == edited


def test_changed_domain_sources_are_not_overwritten_when_evaluation_branches_from_saved_refs(workbench):
    scene = evaluation_scene(workbench)
    material = scene.domains[0]
    draft = deepcopy(material['draft'])
    draft['settings']['parameters']['E'] = 1777
    changed = command(workbench, material, 'material.update', {'draft': draft})
    response = adopt(workbench, scene)
    branch_id = response['document']['draft']['stages'][0]['source']['document_id']
    assert workbench.document_read(material['id']) == changed
    assert workbench.document_read(branch_id)['draft']['settings']['parameters']['E'] == pytest.approx(1100)


def test_preparation_failure_keeps_original_e_refs_and_retries_same_saved_branches(workbench, monkeypatch):
    wb = workbench
    scene = evaluation_scene(wb)
    original_command = wb.simulation_documents.command
    def fail_save_once(identifier, operation, arguments, **options):
        if operation == 'document.save' and identifier != scene.domains[1]['id']:
            raise OSError('Controlled failure before Save admission')
        return original_command(identifier, operation, arguments, **options)
    monkeypatch.setattr(wb.simulation_documents, 'command', fail_save_once)
    with pytest.raises(OSError, match='before Save admission'):
        adopt(wb, scene)
    assert wb.document_read(scene.source['id']) == scene.source
    prepared = load_json(wb.root / 'domain_adoptions' / (scene.payload['command_id'] + '.json'))
    assert len(prepared['branches']) == 1
    first_id = next(iter(prepared['branches'].values()))['document_id']
    first_revision = wb.document_read(first_id)['saved_revision']
    monkeypatch.setattr(wb.simulation_documents, 'command', original_command)
    response = adopt(wb, scene)
    assert response['document']['generation'] == 1
    assert wb.document_read(first_id)['saved_revision'] == first_revision
    assert len(response['branches']) == 3


def test_lost_final_e_save_receipt_recovers_without_new_edit_or_branch_revision(workbench, monkeypatch):
    from caelab import material_document
    wb = workbench
    scene = evaluation_scene(wb)
    real_save = material_document.save_json
    lost = []
    def lose_response(path, value):
        if (path.parent == wb.evaluation_documents._folder(scene.source['id']) / 'commands'
                and 'response' in value and value['response'].get('command_id') != scene.payload['command_id']):
            lost.append(path)
            raise OSError('Controlled lost final E Save receipt')
        return real_save(path, value)
    monkeypatch.setattr(material_document, 'save_json', lose_response)
    with pytest.raises(OSError, match='lost final E Save receipt'):
        adopt(wb, scene)
    current = wb.document_read(scene.source['id'])
    assert current['generation'] == 1 and not current['dirty']
    revisions = {stage['source']['document_id']: stage['source']['saved_revision'] for stage in current['draft']['stages']}
    monkeypatch.setattr(material_document, 'save_json', real_save)
    response = adopt(wb, scene)
    assert response['document']['generation'] == 1
    assert response['document']['saved_revision'] == current['saved_revision']
    assert {stage['source']['document_id']: stage['source']['saved_revision'] for stage in response['document']['draft']['stages']} == revisions
    assert len(response['document']['adoptions']) == 1 and len(lost) == 1


def test_identical_stage_assignments_share_one_saved_branch(workbench):
    scene = evaluation_scene(workbench, duplicate_stage=True)
    preview = prepare(workbench, scene)
    assert len(preview['branch_plan']) == 3
    first = next(row for row in preview['branch_plan'] if 'Stage0' in row['stage_ids'])
    assert first['stage_ids'] == ['Stage0', 'StageTwin']
    response = adopt(workbench, scene)
    stages = {row['id']: row for row in response['document']['draft']['stages']}
    assert stages['Stage0']['source'] == stages['StageTwin']['source']
    assert len(response['branches']) == 3
    assert adopt(workbench, scene) == response


def test_lost_outer_adoption_receipt_recovers_exact_published_target_and_branches(workbench, monkeypatch):
    scene = evaluation_scene(workbench)
    path = workbench.root / 'domain_adoptions' / (scene.payload['command_id'] + '.json')
    real_save = domain_candidate.save_json
    def lose_final_response(destination, value):
        if destination == path and value.get('state') == 'SUCCEEDED':
            raise OSError('Controlled lost final adoption receipt')
        return real_save(destination, value)
    monkeypatch.setattr(domain_candidate, 'save_json', lose_final_response)
    with pytest.raises(OSError, match='lost final adoption receipt'):
        adopt(workbench, scene)
    before = workbench.document_read(scene.source['id'])
    assert before['generation'] == 1 and not before['dirty']
    branch_refs = [deepcopy(row['source']) for row in before['draft']['stages']]
    ids = {row['id'] for row in workbench.documents()['documents']}
    assert 'response' not in load_json(path)
    monkeypatch.setattr(domain_candidate, 'save_json', real_save)
    response = adopt(workbench, scene)
    assert response['document'] == before
    assert [row['source'] for row in response['document']['draft']['stages']] == branch_refs
    assert {row['id'] for row in workbench.documents()['documents']} == ids
    assert len(response['document']['adoptions']) == 1
    assert load_json(path)['response'] == response


def test_unpublished_e_save_failure_preserves_complete_draft_old_manifest_and_branches(workbench, monkeypatch):
    wb = workbench
    scene = evaluation_scene(wb)
    def fail_save(document):
        raise OSError('Controlled unpublished E Save')
    monkeypatch.setattr(wb.evaluation_documents, '_save', fail_save)
    with pytest.raises(OSError, match='unpublished E Save'):
        adopt(wb, scene)
    current = wb.document_read(scene.source['id'])
    assert current['generation'] == 1 and current['dirty']
    assert current['saved_revision'] == scene.source['saved_revision']
    assert len(current['adoptions']) == 1
    assert all(not wb.document_read(stage['source']['document_id'])['dirty'] for stage in current['draft']['stages'])
    with pytest.raises(ValueError, match='Save outcome is unconfirmed'):
        adopt(wb, scene)
    assert wb.document_read(scene.source['id']) == current


def test_study_source_with_definition_inputs_has_no_inferred_adoption_target(workbench):
    wb = workbench
    scene = evaluation_scene(wb)
    run = wb.numerical_documents._documents[scene.plan['id']]['runs'][0]
    draft = deepcopy(run['draft'])
    study = saved(wb, 'study')
    draft['source'] = document_reference(study)
    run['draft'], run['input_sha256'] = draft, canonical_hash(draft)
    with pytest.raises(ValueError, match='Study evidence does not declare'):
        prepare(wb, scene)


def test_wrong_target_session_generation_and_command_conflict_are_explicit(workbench):
    scene = simulation_scene(workbench)
    for key, value, match in [('target_document_id', 'Vdifferent', 'another original'),
                              ('session_id', 'Sold', 'current service session'),
                              ('expected_generation', 4, 'changed after this Plan')]:
        with pytest.raises(ValueError, match=match):
            domain_candidate.adopt(workbench, scene.plan['id'], scene.job_id, scene.candidate_id,
                **{**scene.payload, key: value})
    response = adopt(workbench, scene)
    with pytest.raises(ValueError, match='command_id conflicts'):
        domain_candidate.adopt(workbench, scene.plan['id'], scene.job_id, 'Cother', **scene.payload)
    assert workbench.document_read(scene.source['id']) == response['document']


@pytest.mark.parametrize('fixed_settings', ['exact', 'missing', 'changed', 'changed_holdout'])
def test_simulation_fit_requires_exact_saved_settings_for_every_experiment(workbench, fixed_settings):
    def fit_inputs(inputs):
        settings = inputs.pop('settings')
        inputs.pop('count')
        observation = {'kind': 'scalar', 'unit': 'K', 'component': '', 'location': '',
                       'reduction': 'final', 'value': 300.0}
        inputs['experiments'] = [{'id': 'Fit', 'role': 'fit', 'settings': deepcopy(settings),
                                 'response': 'temperature', 'observations': observation}]
        if fixed_settings == 'missing':
            inputs['experiments'][0].pop('settings')
        elif fixed_settings == 'changed':
            inputs['experiments'][0]['settings']['conductivity']['value'] = 150.0
        elif fixed_settings == 'changed_holdout':
            holdout = deepcopy(inputs['experiments'][0])
            holdout.update(id='Holdout', role='holdout')
            holdout['settings']['conductivity']['value'] = 150.0
            inputs['experiments'].append(holdout)
    scene = simulation_scene(workbench, input_mutation=fit_inputs, operation='fit')
    before = workbench.document_read(scene.source['id'])
    if fixed_settings == 'exact':
        preview = prepare(workbench, scene)
        assert preview['changes'] and preview['executed'] is False
    else:
        with pytest.raises(ValueError, match='Every fit experiment must use the exact saved Simulation settings'):
            prepare(workbench, scene)
    # This controlled fixture has no captured original candidate/detail evidence.
    # The existing stricter fit-adoption gate precedes settings preparation.
    with pytest.raises(ValueError, match='Preserve the selected original candidate/detail evidence'):
        adopt(workbench, scene)
    assert workbench.document_read(scene.source['id']) == before
    assert not (workbench.root / 'domain_adoptions').exists()
