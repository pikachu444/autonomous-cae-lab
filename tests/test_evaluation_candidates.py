"""New composite-to-candidate connections, with a controlled native boundary.

The existing numerical engine and actual HTTP/owners/retention are used. These
are not a new material fit, native solve or physics qualification.
"""
from copy import deepcopy

import pytest

from test_connected_evaluation_study import service, controlled, sources, change, wait
from caelab.jobs import TERMINAL
from caelab.storage import load_json


def plan(client, draft):
    definition=client.document_open(kind='evaluation',draft=draft)
    definition=change(client,definition,'document.save')['document']
    document=client.domain_plan(definition['id'],session_id=definition['session_id'],
        expected_generation=definition['generation'],command_id='CcandidatePlan')['document']
    updated=deepcopy(document['draft'])
    request=updated['request']; request['operation']='doe'; request['budget']={'evaluations':2}
    request['inputs'].update(variables=[{'id':'temperature','unit':'K','value':310.,
        'lower':300.,'upper':330.}], candidates=[
        {'candidate_id':'C310','values':{'temperature':310.}},
        {'candidate_id':'C320','values':{'temperature':320.}}])
    return change(client,document,'numerical.update',{'draft':updated})['document']


def test_http_candidate_to_retained_stage_and_native_launch_source(service, controlled):
    wb,client=service
    originals,draft=sources(client)
    draft['bindings']=[{'id':'temperature','stage':'Heat','input_id':'boundary_temperature','unit':'K'}]
    document=plan(client,draft)
    assert not document['diagnostics']
    job=change(client,document,'numerical.run')['job']['id']
    wait(lambda:wb.manager.status(job)['state'] in TERMINAL)
    assert client.status(job)['state'] in TERMINAL
    result=client.document_result(document['id'],job)
    assert result['execution_status']=='PARTIAL_FAILURE',result
    assert controlled['calls']==['thermal','structural','thermal','structural']
    assert [row['candidate_id'] for row in result['candidates']]==['C310','C320']
    for row in result['candidates']:
        assert len(row['evaluation_refs'])==1
        reference=row['evaluation_refs'][0]
        recorded=load_json(wb.root/'results'/job/reference['relative']/'input.json')
        assert recorded['models']['Heat']['settings']['boundary_temperature']['value']==row['values']['temperature']
    for candidate in ['C310','C320']:
        catalog=client.numerical_evaluation_result(document['id'],job,candidate)
        assert len(catalog['evaluations'])==1 and 'relative' not in catalog['evaluations'][0]
        actual=client.numerical_evaluation_result(document['id'],job,candidate,
            evaluation_index=0,selection={'metadata_only':True})
        assert actual['candidate_id']==candidate and len(actual['stages'])==2
    assert client.numerical_evaluation_result(document['id'],job,'C310',evaluation_index=0,
        selection={'metadata_only':True})['execution_status']=='FAILED'
    heat=client.numerical_evaluation_result(document['id'],job,'C320',evaluation_index=0,
        attempt_id=actual['stages'][0]['attempt_id'],selection={'responses':['temperature']})
    assert heat['responses']['temperature']['unit']=='K' and heat['post_input']['format']=='pvd'
    source={'document_id':document['id'],'candidate_id':'C320','evaluation_index':0,
            'attempt_id':actual['stages'][0]['attempt_id']}
    from apps.research.desktop import _post_result_sources
    assert heat['post_input'] in _post_result_sources(client,job,source)
    # Save copies the exact nested stage files. Reading selects the retained
    # owner result, including failed candidates, without dispatching anything.
    change(client,client.document_read(document['id']),'document.save')
    assert client.numerical_evaluation_result(document['id'],job,'C320',evaluation_index=0,
        attempt_id=actual['stages'][0]['attempt_id'],selection={'responses':['temperature']})==heat
    assert controlled['calls']==['thermal','structural','thermal','structural']
    assert client.document_read(originals[0]['id'])['draft']==originals[0]['draft']
    target=client.document_read(document['draft']['source']['document_id'])
    review=client.domain_candidate_preview(document['id'],job,'C320')
    assert review['target_kind']=='evaluation' and review['changes'][0]['after']==320.
    adopted=client.domain_candidate_adopt(document['id'],job,'C320',target_document_id=target['id'],
        session_id=target['session_id'],expected_generation=target['generation'],command_id='CactualCandidateAdopt')
    updated=adopted['document']
    branch=updated['draft']['stages'][0]['source']
    assert updated['generation']==target['generation']+1 and not updated['dirty']
    assert branch['document_id']!=originals[0]['id']
    assert client.document_read(branch['document_id'])['draft']['settings']['boundary_temperature']['value']==320.
    assert change(client,updated,'document.undo')['document']['draft']==target['draft']
    assert client.document_read(originals[0]['id'])['draft']==originals[0]['draft']
    assert controlled['calls']==['thermal','structural','thermal','structural']


def test_engine_error_keeps_already_completed_composite_attempt(service, controlled, monkeypatch):
    wb,client=service
    _,draft=sources(client)
    controlled['fail_structure']=False
    draft['bindings']=[{'id':'temperature','stage':'Heat','input_id':'boundary_temperature','unit':'K'}]
    document=plan(client,draft)
    from caelab import numerical
    def after_actual_evaluation(factory, **options):
        with factory.prepare(options['settings']) as model:
            model.evaluate({'temperature':310.})
        raise ValueError('Controlled error in downstream objective metadata')
    monkeypatch.setattr(numerical,'run_doe',after_actual_evaluation)
    job=change(client,document,'numerical.run')['job']['id']
    wait(lambda:wb.manager.status(job)['state'] in TERMINAL)
    result=client.document_result(document['id'],job)
    assert result['execution_status']=='FAILED' and not result['candidates']
    assert len(result['evaluation_attempts'])==1
    assert result['diagnostics']['candidate_association']=='UNASSIGNED_AFTER_ENGINE_ERROR'
    assert result['evaluation_attempts'][0]['execution_status']=='SUCCEEDED'
    change(client,client.document_read(document['id']),'document.save')
    assert client.document_result(document['id'],job)==result
    assert controlled['calls']==['thermal','structural']


@pytest.mark.parametrize('response', ['displacement', 'not_exported'])
def test_doe_explicit_response_uses_only_declared_evaluation_exports(service, controlled, response):
    wb, client = service
    _, draft = sources(client)
    controlled['fail_structure'] = False
    draft['bindings'] = [{'id': 'temperature', 'stage': 'Heat', 'input_id': 'boundary_temperature', 'unit': 'K'}]
    document = plan(client, draft)
    requested = deepcopy(document['draft'])
    requested['request']['inputs']['responses'] = [response]
    document = change(client, document, 'numerical.update', {'draft': requested})['document']
    job = change(client, document, 'numerical.run')['job']['id']
    wait(lambda: wb.manager.status(job)['state'] in TERMINAL)
    if response == 'not_exported':
        assert wb.manager.status(job)['state'] == 'FAILED' and controlled['calls'] == []
    else:
        result = client.document_result(document['id'], job)
        assert result['execution_status'] == 'SUCCEEDED'
        assert controlled['calls'] == ['thermal', 'structural', 'thermal', 'structural']
        assert all('displacement' in row['responses'] for row in result['candidates'])
