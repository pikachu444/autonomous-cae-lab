"""Actual existing analyze math over manufactured retained rows; no provider/solver."""
from copy import deepcopy
from types import SimpleNamespace

import pytest

from caelab.execution_control import CancellationToken
from caelab.research_team_results import (ANALYSIS_LIMITS, AnalysisAccess, analysis_input_factory,
    execute_prepared_analysis, make_result_selection, prepare_analysis)
from test_research_team_results import wb, retain_fixture


DEFINITIONS = [{'response': 'force', 'unit': 'N', 'reduction': 'none', 'direction': 'minimize',
                'component': 'scalar', 'location': 'manufactured observation'}]


def table():
    return {'kind': 'manufactured_table', 'execution_status': 'SUCCEEDED',
        'variables': [{'id': 'x', 'unit': '1', 'value': 0, 'lower': 0, 'upper': 10}],
        'candidates': [{'candidate_id': 'C' + str(i), 'values': {'x': i},
            'execution_status': 'SUCCEEDED' if i < 8 else 'FAILED',
            'failure_reason': None if i < 8 else 'Manufactured missing observation',
            'responses': {'force': {'kind': 'scalar', 'unit': 'N', 'value': 2. * i + 1.,
                'component': 'scalar', 'location': 'manufactured observation', 'reduction': 'none'}} if i < 8 else {}}
            for i in range(9)]}


class SourceAccess:
    """Scope boundary double only; C physical validation/real owner/math stay real."""
    def __init__(self, reference, selector, readers):
        self.reference, self.selector, self.readers = reference, selector, readers
        self.prepares = 0
    def prepare_analysis_source(self, source_id, selection, *, limits):
        assert source_id == 'selected'
        self.prepares += 1
        return {'reference': self.reference, 'selector': selection or self.selector,
                'input_dependencies': ['dep-full-source-response']}
    def revalidate_analysis_source(self, source):
        self.readers['probe'](source['reference'])


@pytest.fixture
def analysis(wb, monkeypatch):
    _, reference, _, readers = retain_fixture(wb, monkeypatch, table())
    selection = make_result_selection(readers['probe'](reference), source_id='selected')
    access = SourceAccess(reference, selection['selector'], readers)
    scope = {'allow_execution': True, 'resources': {'threads': 1, 'memory_mb': 64},
        'analysis': {'operation': 'analyze', 'source_ids': ['selected'], 'response_definitions': deepcopy(DEFINITIONS),
            'options': {}, 'limits': deepcopy(ANALYSIS_LIMITS), 'resources': {'threads': 1, 'memory_mb': 64},
            'request_revision': 'Ireviewed'}}
    calls = []
    def execute(request):
        calls.append(deepcopy(request))
        return wb._execute('analyze', request, 'read')
    return {'access': access, 'scope': scope, 'describe_inputs': analysis_input_factory(wb, readers=readers),
            'describe_resources': lambda resources: wb.resource_request({}, resources), 'execute': execute, 'calls': calls}


def prepare(analysis, request=None, scope=None):
    return prepare_analysis(request or {'source_id': 'selected'}, scope=scope or analysis['scope'],
        result_access=analysis['access'], describe_inputs=analysis['describe_inputs'],
        describe_resources=analysis['describe_resources'])


def test_trusted_preparation_runs_existing_math_once_preserves_failures_and_caches(analysis):
    prepared = prepare(analysis)
    assert analysis['calls'] == []
    assert prepared.validated_inputs['table']['candidates'][-1]['execution_status'] == 'FAILED'
    receipt = execute_prepared_analysis(prepared, existing_callback=analysis['execute'], execution_control=CancellationToken())
    assert receipt['execution_status'] == 'SUCCEEDED' and receipt['payload']['statistics'][0]['count'] == 8
    assert receipt['payload']['statistics'][0]['max'] == 15
    assert receipt['payload']['decision'] == 'NOT_RELEASED'
    assert {'id': 'C8', 'reason': 'ROW_UNUSABLE'} in receipt['payload']['exclusions']
    assert receipt['input_dependencies'] == ['dep-full-source-response']
    assert receipt['source_receipts'][0]['reference'] == analysis['access'].reference
    assert execute_prepared_analysis(prepared, existing_callback=analysis['execute'], execution_control=CancellationToken()) == receipt
    assert len(analysis['calls']) == 1


@pytest.mark.parametrize('analysis_request,mutation', [
    ({'source_id': 'selected', 'table': []}, None),
    ({'source_id': 'selected', 'options': {'method': 'invented'}}, None),
    ({'source_id': 'selected', 'resources': {'threads': 2, 'memory_mb': 64}}, None),
    ({'source_id': 'selected'}, 'permission'), ({'source_id': 'selected'}, 'outer_resources'),
    ({'source_id': 'selected'}, 'rows'), ({'source_id': 'selected'}, 'bytes'),
    ({'source_id': 'selected'}, 'hard_memory'),
    ({'source_id': 'selected', 'responses': [dict(DEFINITIONS[0], unit='kN')]}, None),
])
def test_unapproved_or_oversized_analysis_never_executes(analysis, analysis_request, mutation):
    scope = deepcopy(analysis['scope'])
    if mutation == 'permission': scope['allow_execution'] = False
    if mutation == 'outer_resources': scope.pop('resources')
    if mutation == 'rows': scope['analysis']['limits']['max_rows'] = 2
    if mutation == 'bytes': scope['analysis']['limits']['max_input_bytes'] = 16
    if mutation == 'hard_memory': scope['hard_memory_limit'] = True
    with pytest.raises(ValueError):
        prepare(analysis, analysis_request, scope)
    assert analysis['calls'] == []


def test_model_dict_tampered_prepared_and_unknown_outcome_do_not_run(analysis):
    with pytest.raises(ValueError):
        execute_prepared_analysis({'validated_inputs': table()}, existing_callback=analysis['execute'], execution_control=CancellationToken())
    prepared = prepare(analysis)
    prepared.resources['threads'] = 2
    with pytest.raises(ValueError, match='changed'):
        execute_prepared_analysis(prepared, existing_callback=analysis['execute'], execution_control=CancellationToken())
    assert analysis['calls'] == []
    pending = prepare(analysis)
    count = []
    def lost(request):
        count.append(request)
        raise ConnectionError('Controlled lost reply after dispatch')
    with pytest.raises(ConnectionError):
        execute_prepared_analysis(pending, existing_callback=lost, execution_control=CancellationToken())
    with pytest.raises(ValueError, match='unconfirmed'):
        execute_prepared_analysis(pending, existing_callback=lost, execution_control=CancellationToken())
    assert len(count) == 1


def test_callback_factory_uses_durable_existing_operation_ledger(analysis):
    from caelab.assist.research_evidence import GenerationLedger
    state = {'outputs': {}}
    assets = {}
    def checkpoint(event, payload):
        if 'asset' in payload:
            asset = payload['asset']; assets[asset['id']] = deepcopy(asset['payload'])
            return {'asset_ref': {'path': asset['id'], 'sha256': 'fixture'}}
        for key in ('outputs', 'dependencies', 'manifests', 'read_receipts'):
            state.setdefault(key, {}).update(deepcopy(payload.get(key, {})))
        return {'revision': 1}
    ledger = GenerationLedger({}, runtime=None, workspace_id='local', context={}, checkpoint=checkpoint)
    ledger.resolve_payload = lambda ref: deepcopy(assets[ref['path']])
    binding = SimpleNamespace(owner_id='Xfixture', phase_id='Pfixture', action_id='Afixture',
        generation_ledger=ledger, checkpoint=checkpoint,
        current_scope_probe=lambda: {'context': {'calculation_scope': analysis['scope']}, 'ledger_state': state})
    factory = AnalysisAccess(describe_inputs=analysis['describe_inputs'], describe_resources=analysis['describe_resources'],
        existing_callback=analysis['execute'], execution_control=CancellationToken())
    prepared = factory.prepare({'source_id': 'selected'}, scope=analysis['scope'], result_access=analysis['access'], binding=binding)
    first = factory.execute(prepared)
    again = factory.prepare({'source_id': 'selected'}, scope=analysis['scope'], result_access=analysis['access'], binding=binding)
    assert factory.execute(again) == first and len(analysis['calls']) == 1
