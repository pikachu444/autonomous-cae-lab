"""Candidate adoption binds real PDE inputs; these tests execute no PDE solver."""
from copy import deepcopy

import pytest

from caelab.backends import get_backend
from caelab.contracts import CapabilityUnavailable
from caelab import model_parameters
from caelab.pde_candidate import prepare_candidate
from caelab.pde_document import default_draft
from caelab.storage import canonical_hash


@pytest.fixture
def retained(monkeypatch):
    backend = 'pde.fenicsx.coupled'
    adapter = get_backend(backend)
    def forbidden(*args, **kwargs):
        raise AssertionError('Input binding must not execute a PDE solver')
    monkeypatch.setattr(type(adapter), 'solve', forbidden)
    draft = default_draft(backend)
    source = {'kind': 'pde', 'id': 'Qoriginal', 'saved_revision': 'Roriginal',
              'input_revision': 'Ioriginal', 'draft': draft}
    reference = {'pde_document_id': source['id'], 'saved_revision': source['saved_revision'],
                 'input_revision': source['input_revision'], 'input_sha256': canonical_hash(draft)}
    variables = [{'id': 'length_0', 'unit': '1', 'lower': 1., 'upper': 3., 'value': 2., 'transform': 'linear'},
                 {'id': 'diffusion_left_01', 'unit': '1', 'lower': 0., 'upper': .8, 'value': .5, 'transform': 'linear'}]
    request = {'purpose': 'Explore declared rectangle coefficients', 'operation': 'doe',
               'inputs': {**deepcopy(draft), 'variables': variables, 'count': 2},
               'budget': {'evaluations': 2}}
    plan = {'mode': 'request', 'request': request, 'source': reference}
    run = {'job_id': 'Jretained', 'input_revision': 'Iplan', 'draft': plan,
           'input_sha256': canonical_hash(plan)}
    result = {'kind': 'doe', 'variables': deepcopy(variables), 'execution_status': 'PARTIAL_FAILURE',
              'candidates': [{'candidate_id': 'Cgood', 'execution_status': 'SUCCEEDED',
                              'values': {'length_0': 2.5, 'diffusion_left_01': .25}},
                             {'candidate_id': 'Cfailed', 'execution_status': 'FAILED',
                              'values': {'length_0': 2.25, 'diffusion_left_01': .7}}]}
    return run, result, source


def _rehash(run):
    run['input_sha256'] = canonical_hash(run['draft'])


def test_real_declared_rectangle_binding_preserves_fixed_input_and_evidence(retained):
    run, result, source = retained
    originals = deepcopy(retained)
    prepared = prepare_candidate(run, result, 'Cgood', source)
    expected = model_parameters.bind(get_backend(source['draft']['backend']), source['draft']['settings'],
                                     result['candidates'][0]['values'])
    assert prepared['draft'] == {'backend': source['draft']['backend'], 'settings': expected}
    settings = prepared['draft']['settings']
    assert settings['problem']['domain']['lengths'] == [2.5, 1.]
    assert settings['problem']['weak_form']['diffusion']['left'] == [[2., .25], [.25, 1.]]
    assert settings['validation'] == source['draft']['settings']['validation']
    assert settings['problem']['reference'] is None
    assert settings['mesh'] == source['draft']['settings']['mesh']
    evidence = prepared['source']
    assert evidence['parameter_assignments'] == result['candidates'][0]['values']
    assert evidence['original_pde']['input_sha256'] == canonical_hash(source['draft'])
    assert evidence['result_sha256'] == canonical_hash(result)
    assert evidence['bound_draft_sha256'] == canonical_hash(prepared['draft'])
    assert all(item['unit'] == '1' for item in evidence['declared_inputs'])
    assert {item['id'] for item in evidence['declared_inputs'] if item['free']} == set(evidence['parameter_assignments'])
    assert evidence['engineering_release'] == 'NOT_RELEASED'
    assert retained == originals


@pytest.mark.parametrize(('operation', 'kind'), [('doe', 'doe'), ('fit', 'fit'),
    ('optimize', 'optimization'), ('uq', 'uq'), ('epsilon', 'epsilon_optimization')])
def test_supported_operation_rows_and_generic_source_reference(retained, operation, kind):
    run, result, source = retained
    run['draft']['request']['operation'] = operation
    if operation == 'fit':
        # Real fit requests have per-experiment protocols, no global settings.
        run['draft']['request']['inputs'].pop('settings')
        run['draft']['request']['inputs'].pop('count')
        run['draft']['request']['inputs']['experiments'] = []
    run['draft']['source'] = {'kind': 'pde', 'document_id': source['id'],
        **{key: run['draft']['source'][key] for key in ('saved_revision', 'input_revision', 'input_sha256')}}
    _rehash(run)
    result['kind'] = kind
    result['candidates'][0]['objective'] = .1
    assert prepare_candidate(run, result, 'Cgood', source)['source']['operation'] == operation


@pytest.mark.parametrize('status', ['FAILED', 'CANCELLED', 'REJECTED', 'NOT_EVALUATED', 'PREDICTED'])
def test_failed_or_unperformed_candidates_cannot_be_adopted(retained, status):
    run, result, source = retained
    result['candidates'][0]['execution_status'] = status
    with pytest.raises(ValueError, match='actually evaluated'):
        prepare_candidate(run, result, 'Cgood', source)


@pytest.mark.parametrize('change', ['prediction', 'duplicate', 'missing', 'nonfinite', 'boolean',
    'outside', 'extra_value', 'missing_value', 'kind', 'result_unit', 'result_bound',
    'backend', 'source_kind', 'source_id', 'source_revision', 'source_input', 'source_changed',
    'settings_changed', 'unit', 'binding_bound', 'unadvertised', 'stale_run'])
def test_candidate_and_frozen_source_counterexamples(retained, change):
    run, result, source = retained
    row = result['candidates'][0]
    variables = run['draft']['request']['inputs']['variables']
    if change == 'prediction': row['prediction_status'] = 'PREDICTED'
    elif change == 'duplicate': result['candidates'].append(deepcopy(row))
    elif change == 'missing': row['candidate_id'] = 'Cother'
    elif change == 'nonfinite': row['values']['length_0'] = float('nan')
    elif change == 'boolean': row['values']['length_0'] = True
    elif change == 'outside': row['values']['length_0'] = 3.1
    elif change == 'extra_value': row['values']['unknown'] = 1.
    elif change == 'missing_value': row['values'].pop('length_0')
    elif change == 'kind': result['kind'] = 'surrogate'
    elif change == 'result_unit': result['variables'][0]['unit'] = 'm'
    elif change == 'result_bound': result['variables'][0]['upper'] = 4.
    elif change == 'backend': run['draft']['request']['inputs']['backend'] = 'pde.fenicsx.rectangle'
    elif change == 'source_kind': source['kind'] = 'material'
    elif change == 'source_id': source['id'] = 'Qother'
    elif change == 'source_revision': source['saved_revision'] = 'Rother'
    elif change == 'source_input': source['input_revision'] = 'Iother'
    elif change == 'source_changed': source['draft']['settings']['mesh']['cell_counts'] = [32]
    elif change == 'settings_changed': run['draft']['request']['inputs']['settings']['mesh']['cell_counts'] = [32]
    elif change == 'unit': variables[0]['unit'] = result['variables'][0]['unit'] = 'm'
    elif change == 'binding_bound': variables[0]['upper'] = result['variables'][0]['upper'] = 2000.
    elif change == 'unadvertised':
        variables[0]['id'] = result['variables'][0]['id'] = 'unknown'
        row['values']['unknown'] = row['values'].pop('length_0')
    elif change == 'stale_run': run['input_sha256'] = '0' * 64
    if change != 'stale_run': _rehash(run)
    with pytest.raises(ValueError):
        prepare_candidate(run, result, 'Cgood', source)


def test_unsupported_actual_pde_adapter_fails_explicitly(retained):
    run, result, source = retained
    # The legacy scalar adapter does not advertise a checked input binder.
    source['draft'] = default_draft('pde.fenicsx')
    run['draft']['request']['inputs'].update(deepcopy(source['draft']))
    run['draft']['source']['input_sha256'] = canonical_hash(source['draft'])
    _rehash(run)
    with pytest.raises(CapabilityUnavailable, match='no declared scalar input binding'):
        prepare_candidate(run, result, 'Cgood', source)


def test_simultaneous_scientific_binding_rejection_is_not_repaired(retained):
    run, result, source = retained
    for variables in (run['draft']['request']['inputs']['variables'], result['variables']):
        variables[1]['upper'] = 10.
    result['candidates'][0]['values']['diffusion_left_01'] = 9.
    _rehash(run)
    with pytest.raises(ValueError):
        prepare_candidate(run, result, 'Cgood', source)
    assert source['draft']['settings']['problem']['weak_form']['diffusion']['left'] == [[2., .5], [.5, 1.]]
