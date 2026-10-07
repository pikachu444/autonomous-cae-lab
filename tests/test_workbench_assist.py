"""Offline contract checks; fake generator is a mock, never live inference evidence."""
from pathlib import Path
import json
import pytest
from caelab.assist import Assistance, ExpertRuntime, KnowledgeStore, Literature, RuntimeConfig
from caelab.execution_control import ExecutionCancelled, ExecutionCleanupFailed


def store(tmp_path):
    return KnowledgeStore(tmp_path / 'archive', source_roots=[tmp_path])


def ingest(knowledge, tmp_path, text, *, name='sample.md', collection='materials', workspace='alpha', document_id=None):
    path = tmp_path / name
    path.write_text(text, encoding='utf-8')
    return knowledge.ingest(path, collection, workspace_id=workspace, document_id=document_id)


def test_real_haystack_bm25_identifier_korean_english_and_rebuild(tmp_path):
    knowledge = store(tmp_path)
    identifier = ingest(knowledge, tmp_path, '# Standard\nASTM-D638 tensile specimen strain measurement.', name='standard.md')
    korean = ingest(knowledge, tmp_path, '# 시험\n인장 시험 탄성계수 측정 자료와 변형률 보정.', name='korean.md')
    english = ingest(knowledge, tmp_path, '# Models\nHyperelastic material calibration requires independent biaxial measurements.', name='english.md')
    for query, expected in [('ASTM-D638', identifier), ('인장 탄성계수', korean), ('biaxial calibration', english)]:
        hits = knowledge.search(query, ['materials'], workspace_id='alpha')['hits']
        assert hits[0]['document_id'] == expected['document_id']
        assert hits[0]['revision'] == 1 and hits[0]['locator']['section']
    assert knowledge.search('인장', workspace_id='beta')['hits'] == []
    assert knowledge.search('인장', ['testing'], workspace_id='alpha')['hits'] == []
    restored = KnowledgeStore(knowledge.root, source_roots=[tmp_path])
    assert restored.rebuild()['segments_indexed'] == 3
    assert restored.search('ASTM-D638', workspace_id='alpha')['hits'][0]['document_id'] == identifier['document_id']


def test_revision_archive_and_revoked_citation_access(tmp_path):
    knowledge = store(tmp_path)
    original = ingest(knowledge, tmp_path, '# Original\nold stiffness reference')
    newer = ingest(knowledge, tmp_path, '# Revised\nnew stiffness reference', document_id=original['document_id'])
    assert newer['revision'] == 2
    hits = knowledge.search('stiffness', workspace_id='alpha')['hits']
    assert hits[0]['revision'] == 2
    assert 'old' in knowledge.source(original['document_id'], 1, workspace_id='alpha')['segments'][0]['text']
    knowledge.revoke(original['document_id'], workspace_id='alpha')
    assert knowledge.search('stiffness', workspace_id='alpha')['hits'] == []
    with pytest.raises(PermissionError):
        knowledge.source(original['document_id'], 1, workspace_id='alpha')
    with pytest.raises(PermissionError):
        knowledge.source(original['document_id'], 2, workspace_id='beta')


def test_ingest_limits_and_pdf_page_extraction(tmp_path):
    from pypdf import PdfWriter
    knowledge = store(tmp_path)
    outside = tmp_path.parent / 'outside.txt'
    outside.write_text('source')
    with pytest.raises(PermissionError):
        knowledge.ingest(outside, 'materials')
    pdf = tmp_path / 'blank.pdf'
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    writer.write(pdf)
    result = knowledge.ingest(pdf, 'materials')
    assert result['segments_read'] == 0
    assert result['failed_segments'][0]['page'] == 1
    with pytest.raises(ValueError):
        knowledge.search('source', filters={'arbitrary': 'filter'})


def crossref_fixture(with_abstract=True):
    item = {'DOI': '10.1234/example', 'title': ['Actual fixture title'], 'author': [{'given': 'A', 'family': 'Author'}],
            'issued': {'date-parts': [[2025]]}, 'type': 'journal-article', 'URL': 'https://doi.org/10.1234/example',
            'link': [{'URL': 'https://public.example/paper.xml', 'content-type': 'application/xml'}]}
    if with_abstract:
        item['abstract'] = '<jats:p>Only an abstract.</jats:p>'
    return item


def test_literature_metadata_abstract_fulltext_and_explicit_import(tmp_path):
    calls = []
    def fetch(url):
        calls.append(url)
        if 'api.crossref.org' in url:
            return json.dumps({'message': {'items': [crossref_fixture(), crossref_fixture()]}}).encode(), 'application/json', url
        return b'<article><body><p>Public full text observation.</p></body></article>', 'application/xml', url
    literature = Literature(fetch=fetch)
    found = literature.search('material calibration')
    assert len(found['papers']) == 1
    paper_id = found['papers'][0]['paper_id']
    abstract = literature.read(paper_id, {'kind': 'abstract'})
    assert abstract['status'] == 'abstract_only' and abstract['segments'][0]['text'] == 'Only an abstract.'
    full = literature.read(paper_id)
    assert full['status'] == 'fulltext' and 'Public full text' in full['segments'][0]['text']
    assert full['table_figure_status'] == 'unverified'
    knowledge = store(tmp_path)
    imported = literature.import_paper(paper_id, knowledge, 'materials', workspace_id='alpha')
    assert imported['import_status'] == 'IMPORTED'
    assert knowledge.search('observation', workspace_id='alpha')['hits']
    def fail(url):
        raise OSError('Offline test: unavailable network')
    literature.fetch = fail
    unavailable = literature.read(paper_id)
    assert unavailable['status'] == 'abstract_only' and unavailable['access_failures']
    assert literature.search('question')['status'] == 'UNAVAILABLE'
    literature._papers['doi:no-abstract'] = {**found['papers'][0], 'abstract': None}
    assert literature.read('doi:no-abstract')['status'] == 'metadata_only'


def definitions(tools=None):
    return [{'id': 'materials', 'instructions': 'Material research.', 'collections': ['materials'],
             'tools': tools or ['knowledge.search', 'calculations.plan', 'experts.consult']},
            {'id': 'testing', 'instructions': 'Testing research.', 'collections': ['materials'],
             'tools': ['knowledge.search', 'experts.consult']}]


def mock_generator(script):
    from haystack import component
    from haystack.dataclasses import ChatMessage, ToolCall
    @component
    class ScriptedMockGenerator:
        def __init__(self):
            self.calls = []
            self.script = list(script)
        @component.output_types(replies=list[ChatMessage])
        def run(self, messages, tools=None, generation_kwargs=None):
            self.calls.append(messages)
            step = self.script.pop(0)
            if callable(step):
                step = step(messages)
            if isinstance(step, tuple):
                name, request = step
                return {'replies': [ChatMessage.from_assistant(tool_calls=[ToolCall(tool_name=name, arguments=request, id=str(len(self.calls)))])]}
            return {'replies': [ChatMessage.from_assistant(text=json.dumps(step))]}
    return ScriptedMockGenerator()


def runtime_for(tmp_path, generator=None, tools=None, callbacks=None, external=False, transmission=None):
    knowledge = store(tmp_path)
    runtime = ExpertRuntime(knowledge, Literature(), experts=definitions(tools), callbacks=callbacks,
                            runtime=RuntimeConfig(generator=generator, model='explicit-test-mock',
                                external_model=external, transmission=transmission))
    return knowledge, runtime


def test_absent_model_is_honest_and_expert_definitions_are_arbitrary(tmp_path):
    knowledge, runtime = runtime_for(tmp_path)
    response = runtime.ask('materials', 'Unknown defect', workspace_id='alpha')
    assert response['status'] == 'NOT_CONFIGURED' and response['answer'] is None
    assert response['tool_events'] == []
    assert len(runtime.list()['experts']) == 2
    with pytest.raises(ValueError):
        runtime.ask('missing', 'question')
    additional = ExpertRuntime(knowledge, Literature(), experts=[{'id': 'custom-role', 'collections': [], 'tools': []}])
    assert additional.describe('custom-role')['id'] == 'custom-role'


def test_mock_agent_real_search_citation_and_session_followup(tmp_path):
    generator = mock_generator([])
    knowledge, runtime = runtime_for(tmp_path, generator)
    document = ingest(knowledge, tmp_path, '# Measurement\nASTM-D638 stiffness measured at 25 C.')
    citation = {'document_id': document['document_id'], 'revision': 1,
                'locator': knowledge.source(document['document_id'], workspace_id='alpha')['segments'][0]['locator']}
    generator.script = [('knowledge_search', {'query': 'ASTM-D638'}),
                        {'answer': 'The source describes measurement at 25 C.', 'sources': [citation], 'assumptions': []},
                        {'answer': 'A follow-up needs another measured condition.', 'sources': [citation]}]
    answer = runtime.ask('materials', 'What condition?', workspace_id='alpha')
    assert answer['status'] == 'ANSWERED', answer
    assert answer['tool_events'][0]['tool'] == 'knowledge.search'
    assert answer['sources'] == [citation]
    followup = runtime.ask('materials', 'What next?', {'selected_document_ids': [document['document_id']]},
                           answer['session_id'], workspace_id='alpha')
    assert followup['status'] == 'ANSWERED'
    assert len(generator.calls[-1]) >= 3
    with pytest.raises(PermissionError):
        runtime.ask('materials', 'different workspace', session_id=answer['session_id'], workspace_id='beta')


def test_mock_agent_bounds_consultation_and_rejects_invented_sources(tmp_path):
    generator = mock_generator([('experts_consult', {'expert_id': 'testing', 'question': 'test condition?'}),
                                {'answer': 'A second measurement is needed.', 'sources': []},
                                {'answer': 'We agree a measurement is needed.', 'sources': []}])
    _, runtime = runtime_for(tmp_path, generator)
    result = runtime.ask('materials', 'review', {'consult_experts': ['testing']}, workspace_id='alpha')
    assert result['status'] == 'ANSWERED', result
    assert result['budget_used']['consultations'] == 1
    assert result['tool_events'][0]['tool'] == 'experts.consult'
    generator.script = [('experts_consult', {'expert_id': 'testing', 'question': 'again'}),
                        ('experts_consult', {'expert_id': 'materials', 'question': 'loop'})]
    stopped = runtime.ask('materials', 'review', {'consult_experts': ['testing', 'materials']}, workspace_id='alpha')
    assert stopped['status'] == 'FAILED'
    generator.script = [{'answer': 'Fabricated evidence', 'sources': [{'paper_id': 'invented', 'locator': {}}]}]
    assert runtime.ask('materials', 'claim', workspace_id='alpha')['status'] == 'FAILED'


def test_model_transmission_and_tool_scope_cannot_be_expanded(tmp_path):
    generator = mock_generator([{'answer': 'unused', 'sources': []}])
    knowledge, runtime = runtime_for(tmp_path, generator, external=True,
        transmission={'allow_external_model': True, 'allow_question': True, 'collections': []})
    with pytest.raises(PermissionError):
        runtime.ask('materials', 'private question', workspace_id='alpha')
    doc = ingest(knowledge, tmp_path, '# Private\nCompany measurement.')
    with pytest.raises(PermissionError):
        runtime.ask('materials', 'review', {'selected_document_ids': [doc['document_id']],
                    'transmission_scope': {'allow_question': True, 'collections': ['materials']}}, workspace_id='alpha')
    assert generator.calls == []
    generator.script = [('knowledge_search', {'query': 'Company', 'collections': ['secret']})]
    runtime.runtime.external_model = False
    assert runtime.ask('materials', 'search', workspace_id='alpha')['status'] == 'FAILED'


def test_editable_plan_then_registered_real_calculation_result_and_followup(tmp_path):
    import numpy as np
    from scipy.stats import qmc
    requests = []
    def doe(request):
        requests.append(request)
        values = qmc.LatinHypercube(d=1, rng=5).random(n=request['budget']['evaluations'])[:, 0]
        return {'status': 'SUCCEEDED', 'candidates': [{'x': float(x), 'response': float(2*x)} for x in values]}
    def analyze(request):
        x = np.array([r['x'] for r in request['candidates']])
        y = np.array([r['response'] for r in request['candidates']])
        return {'status': 'SUCCEEDED', 'method': 'NumPy least squares', 'slope': float(np.linalg.lstsq(x[:, None], y, rcond=None)[0][0])}
    plan = {'purpose': 'Assess influence', 'operation': 'doe', 'inputs': {'backend': 'registered-test-model',
            'variables': [{'id': 'x', 'unit': '1', 'lower': 0, 'upper': 1}]}, 'budget': {'evaluations': 4}}
    generator = mock_generator([('calculations_plan', plan),
        ('numerical_doe', {'backend': 'registered-test-model', 'budget': {'evaluations': 4},
                           'variables': [{'id': 'x', 'unit': '1', 'lower': 0, 'upper': 1}]}),
        lambda messages: ('numerical_analyze', {'candidates': json.loads(messages[-1].tool_call_results[0].result)['candidates']}),
        lambda messages: {'answer': 'Actual least-squares slope is ' + str(json.loads(messages[-1].tool_call_results[0].result)['slope']),
                          'sources': [], 'proposed_actions': [{'purpose': 'Confirm at a second condition', 'operation': 'doe',
                          'inputs': {'backend': 'registered-test-model', 'variables': [
                              {'id': 'x', 'unit': '1', 'lower': 0, 'upper': 1}], 'count': 2},
                          'budget': {'evaluations': 2}}]}])
    _, runtime = runtime_for(tmp_path, generator, tools=['calculations.plan', 'numerical.doe', 'numerical.analyze'],
                            callbacks={'numerical.doe': doe, 'numerical.analyze': analyze})
    result = runtime.ask('materials', 'Propose DOE, compute influence and propose next study',
                         {'calculation_scope': {'allow_execution': True, 'max_evaluations': 4,
                                                'backends': ['registered-test-model'],
                                                'variables': {'x': [0, 1]}}}, workspace_id='alpha')
    assert result['status'] == 'ANSWERED', result
    assert '2.0' in result['answer']
    assert len(requests) == 1
    assert result['proposed_actions'][0]['status'] == 'PLANNED'
    assert result['proposed_actions'][0]['editable'] and not result['proposed_actions'][0]['executed']
    assert result['proposed_actions'][1]['plan']['budget']['evaluations'] == 2
    assert [e['tool'] for e in result['tool_events']] == ['calculations.plan', 'numerical.doe', 'numerical.analyze']


def test_facade_and_unapproved_execution(tmp_path):
    generator = mock_generator([('calculations_submit', {'backend': 'test', 'budget': {'evaluations': 1}})])
    invoked = []
    assistance = Assistance(tmp_path / 'assist', experts=definitions(['calculations.submit']),
        runtime=RuntimeConfig(generator=generator, external_model=False), source_roots=[tmp_path],
        callbacks={'calculations.submit': lambda request: invoked.append(request)})
    result = assistance.call('experts.ask', {'expert_id': 'materials', 'question': 'run'})
    assert result['status'] == 'FAILED' and invoked == []
    assert assistance.call('experts.describe', {'expert_id': 'testing'})['id'] == 'testing'


def test_pdf_actual_extracted_text_and_public_literature_archive(tmp_path):
    from pypdf import PdfWriter
    from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject
    writer = PdfWriter()
    page = writer.add_blank_page(width=300, height=300)
    font = DictionaryObject({NameObject('/Type'): NameObject('/Font'), NameObject('/Subtype'): NameObject('/Type1'),
                             NameObject('/BaseFont'): NameObject('/Helvetica')})
    page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({NameObject('/F1'): writer._add_object(font)})})
    stream = DecodedStreamObject()
    stream.set_data(b'BT /F1 12 Tf 30 200 Td (ASTM-D638 tensile modulus) Tj ET')
    page[NameObject('/Contents')] = writer._add_object(stream)
    pdf = tmp_path / 'measurement.pdf'
    writer.write(pdf)
    knowledge = store(tmp_path)
    result = knowledge.ingest(pdf, 'materials', workspace_id='alpha')
    assert result['segments_read'] == 1
    hit = knowledge.search('ASTM-D638', workspace_id='alpha')['hits'][0]
    assert hit['locator']['page'] == 1
    assert 'modulus' in hit['text']
    def fetch(url):
        if 'api.crossref.org' in url:
            return json.dumps({'message': {'items': [crossref_fixture()]}}).encode(), 'application/json', url
        return b'<article><body><p>Version one observation.</p></body></article>', 'application/xml', url
    root = tmp_path / 'literature'
    literature = Literature(root, fetch=fetch)
    paper_id = literature.search('material')['papers'][0]['paper_id']
    read = literature.read(paper_id)
    locator = read['segments'][0]['locator']
    assert 'archive_id' in locator
    restored = Literature(root, fetch=lambda url: (_ for _ in ()).throw(OSError('offline')))
    archived = restored.read(paper_id, locator)
    assert archived['segments'][0]['text'] == read['segments'][0]['text']


def test_cumulative_calculation_budget_and_range_guard(tmp_path):
    calls = []
    request = {'backend': 'test', 'budget': {'evaluations': 3},
               'variables': [{'id': 'E', 'unit': 'MPa', 'lower': 1, 'upper': 10}]}
    generator = mock_generator([('numerical_doe', request), ('numerical_doe', request)])
    _, runtime = runtime_for(tmp_path, generator, tools=['numerical.doe'],
                            callbacks={'numerical.doe': lambda value: calls.append(value) or {'status': 'SUCCEEDED'}})
    context = {'calculation_scope': {'allow_execution': True, 'max_evaluations': 4, 'backends': ['test'],
                                    'variables': {'E': [1, 10]}}}
    result = runtime.ask('materials', 'run batches', context)
    assert result['status'] == 'FAILED' and len(calls) == 1
    generator.script = [('numerical_doe', {**request, 'variables': [{'id': 'E', 'unit': 'MPa', 'lower': 1, 'upper': 50}]})]
    result = runtime.ask('materials', 'expand range', context)
    assert result['status'] == 'FAILED' and len(calls) == 1


def test_revoked_history_does_not_enter_later_model_context(tmp_path):
    generator = mock_generator([{'answer': 'Private previous measurement SECRET-MEASUREMENT', 'sources': []},
                                {'answer': 'No retained source is accessible.', 'sources': []}])
    knowledge, runtime = runtime_for(tmp_path, generator)
    doc = ingest(knowledge, tmp_path, '# Private\nSECRET-MEASUREMENT')
    first = runtime.ask('materials', 'review', {'selected_document_ids': [doc['document_id']]}, workspace_id='alpha')
    knowledge.revoke(doc['document_id'], workspace_id='alpha')
    followup = runtime.ask('materials', 'followup', session_id=first['session_id'], workspace_id='alpha')
    assert followup['status'] == 'ANSWERED'
    assert 'SECRET-MEASUREMENT' not in str([m.to_dict() for m in generator.calls[-1]])


def test_analysis_and_status_reject_unselected_result_before_callback(tmp_path):
    for tool, request in [('numerical.analyze', {'job_id': 'OTHER_PROJECT', 'responses': []}),
                          ('calculations.status', {'job_id': 'OTHER_PROJECT'}),
                          ('numerical.fit', {'backend': 'test', 'budget': {'evaluations': 1},
                           'variables': [{'id': 'E', 'unit': 'MPa', 'lower': 1, 'upper': 2}],
                           'experiments': [{'id': 'fit-1', 'settings': {'observation_job': 'OTHER_PROJECT'},
                                            'response': 'force', 'observations': {'kind': 'scalar', 'unit': 'N',
                                            'component': '', 'location': '', 'reduction': 'none', 'value': 1}}]})]:
        calls = []
        generator = mock_generator([(tool.replace('.', '_'), request)])
        _, runtime = runtime_for(tmp_path, generator, tools=[tool],
                                callbacks={tool: lambda request: calls.append(request) or {'slope': 9}})
        response = runtime.ask('materials', 'Read a selected result', {'selected_result_ids': ['ALLOWED'],
            'calculation_scope': {'allow_execution': True, 'max_evaluations': 1, 'backends': ['test']}})
        assert response['status'] == 'FAILED'
        assert 'selected access scope' in response['reason']
        assert calls == []


def test_derived_analysis_requires_result_transmission_permission(tmp_path):
    generator = mock_generator([('numerical_analyze', {'job_id': 'ALLOWED', 'responses': []})])
    calls = []
    _, runtime = runtime_for(tmp_path, generator, tools=['numerical.analyze'], external=True,
        transmission={'allow_external_model': True, 'allow_question': True, 'allow_results': False},
        callbacks={'numerical.analyze': lambda request: calls.append(request) or {'slope': 9}})
    response = runtime.ask('materials', 'Analyze', {'selected_result_ids': ['ALLOWED'],
        'transmission_scope': {'allow_question': True, 'result_ids': ['ALLOWED']}})
    assert response['status'] == 'FAILED'
    assert 'transmission scope' in response['reason']
    assert calls == []


def test_selected_status_omits_stored_arguments_and_analysis_carries_actual_provenance(tmp_path):
    generator = mock_generator([('calculations_status', {'job_id': 'ALLOWED'}),
        {'answer': 'The selected job finished.', 'sources': [{'run_id': 'ALLOWED', 'response_selection': []}]},
        ('numerical_analyze', {'job_id': 'ALLOWED', 'responses': [{'response': 'force', 'unit': 'N', 'direction': 'minimize'}]}),
        {'answer': 'Actual slope is 9.', 'sources': [{'run_id': 'ALLOWED', 'response_selection': [{'response': 'force', 'unit': 'N', 'direction': 'minimize'}]}]}])
    _, runtime = runtime_for(tmp_path, generator, tools=['calculations.status', 'numerical.analyze'], external=True,
        transmission={'allow_external_model': True, 'allow_question': True, 'allow_results': True},
        callbacks={'calculations.status': lambda request: {'job_id': 'ALLOWED', 'state': 'SUCCEEDED',
                    'arguments': {'question': 'SECRET_OTHER_QUESTION', 'observations': ['PRIVATE_RAW']}, 'request_hash': 'PRIVATE_HASH'},
                   'numerical.analyze': lambda request: {'method': 'actual test callback', 'slope': 9}})
    context = {'selected_result_ids': ['ALLOWED'], 'transmission_scope': {'allow_question': True, 'result_ids': ['ALLOWED']}}
    status = runtime.ask('materials', 'Status', context)
    assert status['status'] == 'ANSWERED', status
    sent = str([message.to_dict() for message in generator.calls[-1]])
    assert 'SECRET_OTHER_QUESTION' not in sent and 'PRIVATE_RAW' not in sent and 'PRIVATE_HASH' not in sent
    assert 'source_results' in sent and 'ALLOWED' in sent
    analysis = runtime.ask('materials', 'Influence', context)
    assert analysis['status'] == 'ANSWERED', analysis
    assert analysis['sources'] == [{'run_id': 'ALLOWED', 'response_selection': [{'response': 'force', 'unit': 'N', 'direction': 'minimize'}]}]


@pytest.mark.parametrize('tool,nested',[('numerical.doe',False),('calculations.submit',True)])
def test_effective_numerical_workers_obey_expert_resource_scope(tmp_path,tool,nested):
    calls=[]
    inputs={'backend':'test','variables':[{'id':'E','unit':'MPa','lower':1,'upper':2}],
            'execution':{'mode':'process','workers':8,'threads':1}}
    request={'operation':'doe','inputs':inputs} if nested else inputs
    request={**request,'budget':{'evaluations':2}}
    generator=mock_generator([(tool.replace('.','_'),request)])
    _,runtime=runtime_for(tmp_path,generator,tools=[tool],callbacks={tool:lambda value:calls.append(value) or {'status':'SUCCEEDED'}})
    response=runtime.ask('materials','Run',{'calculation_scope':{'allow_execution':True,'max_evaluations':2,
        'backends':['test'],'variables':{'E':[1,2]},'resources':{'threads':1}}})
    assert response['status']=='FAILED' and 'Resource request' in response['reason']
    assert calls==[]


def test_model_sees_named_tool_fields_and_recovers_from_invalid_input(tmp_path):
    generator = mock_generator([('knowledge_search', {}),
                                ('knowledge_search', {'query': 'actual source'}),
                                {'answer': 'No accessible source was found.', 'sources': []}])
    _, runtime = runtime_for(tmp_path, generator, tools=['knowledge.search'])
    result = runtime.ask('materials', 'Find the source', workspace_id='alpha')
    assert result['status'] == 'ANSWERED', result
    assert result['tool_events'][0]['status'] == 'INVALID_TOOL_INPUT'
    assert result['tool_events'][1]['tool'] == 'knowledge.search'
    visible = generator.calls[0]
    assert visible
    # The installed Haystack Agent uses Tool.tool_spec to expose these direct fields.
    from caelab.assist.experts import _TOOL_INPUTS
    assert _TOOL_INPUTS['knowledge.search']['required'] == ['query']
    assert 'request' not in _TOOL_INPUTS['knowledge.search']['properties']
    # The OpenScience MCP client rejects the complete tool catalog if any
    # inputSchema omits this top-level object type.
    assert all(schema.get('type') == 'object' for schema in _TOOL_INPUTS.values())
    from jsonschema import Draft202012Validator
    for schema in _TOOL_INPUTS.values():
        Draft202012Validator.check_schema(schema)
    search = Draft202012Validator(_TOOL_INPUTS['literature.search'])
    assert not list(search.iter_errors({'query':'oscillator','providers':['crossref']}))
    assert list(search.iter_errors({'query':'oscillator','providers':['uninstalled']}))
    read = Draft202012Validator(_TOOL_INPUTS['literature.read'])
    assert not list(read.iter_errors({'paper_id':'doi:example','locator':{'kind':'abstract'}}))
    assert not list(read.iter_errors({'paper_id':'doi:example','locator':{'url':'https://example.test/paper.pdf','page':2}}))
    assert list(read.iter_errors({'paper_id':'doi:example','locator':{'kind':'metadata_only'}}))


def test_scoped_tool_name_cannot_be_rebound_by_mcp_arguments(tmp_path, monkeypatch):
    import caelab.assist.openscience_host as host
    submissions = []
    observed = []
    def fake_host(_prompt, tools, _budget, _model, **_kwargs):
        observed.append(tools['knowledge_search']['call'](
            _name='calculations.submit', operation='evaluate',
            inputs={'backend': 'test'}, budget={'evaluations': 1}))
        return json.dumps({'answer': 'Rejected an invalid search request.', 'sources': []})
    monkeypatch.setattr(host, 'run_openscience', fake_host)
    runtime = ExpertRuntime(store(tmp_path), Literature(),
        experts=definitions(['knowledge.search', 'calculations.submit']),
        callbacks={'calculations.submit': lambda request: submissions.append(request) or {'job_id': 'J1'}},
        runtime=RuntimeConfig(provider='openscience', model='openai-codex/gpt-5.6-sol',
                              transmission={'allow_external_model': True, 'allow_question': True}))
    result = runtime.ask('materials', 'Search', {'calculation_scope': {
        'allow_execution': True, 'max_evaluations': 1, 'backends': ['test']},
        'transmission_scope': {'allow_question': True}}, workspace_id='alpha')
    assert result['status'] == 'ANSWERED', result
    assert observed[0]['status'] == 'INVALID_TOOL_INPUT'
    assert observed[0]['tool'] == 'knowledge.search'
    assert submissions == []


def test_citation_repair_uses_only_read_markers_and_preserves_actions(tmp_path, monkeypatch):
    import caelab.assist.openscience_host as host
    knowledge = store(tmp_path)
    document = ingest(knowledge, tmp_path, '# Evidence\nA saved measurement.')
    calls, marker = [], {}
    def fake_host(_prompt, tools, _budget, _model, **_kwargs):
        calls.append(sorted(tools))
        if len(calls) == 1:
            source = tools['knowledge_source']['call'](document_id=document['document_id'], revision=1)
            marker.update({key: source['segments'][0][key] for key in ('document_id', 'revision', 'locator')})
            return json.dumps({'answer': 'A source was read, but this extra paper was not.',
                'sources': [{'paper_id': 'doi:unread', 'locator': {'kind': 'metadata_only'}}],
                'proposed_actions': ['Keep the bounded study editable.']})
        assert tools == {}
        assert 'doi:unread' in _prompt and document['document_id'] in _prompt
        return json.dumps({'answer': 'The archived measurement was read.', 'sources': [marker],
                           'proposed_actions': ['Widen computation without approval.']})
    monkeypatch.setattr(host, 'run_openscience', fake_host)
    runtime = ExpertRuntime(knowledge, Literature(), experts=definitions(['knowledge.source']),
        runtime=RuntimeConfig(provider='openscience', model='openai-codex/gpt-5.6-sol',
            transmission={'allow_external_model': True, 'allow_question': True,
                          'collections': ['materials']}))
    answer = runtime.ask('materials', 'Use the evidence', {'transmission_scope': {
        'allow_question': True, 'collections': ['materials']}}, workspace_id='alpha')
    assert answer['status'] == 'ANSWERED', answer
    assert answer['sources'] == [marker]
    assert answer['proposed_actions'][0]['proposal'] == 'Keep the bounded study editable.'
    # OpenScience reports a reservation for its maximum provider steps, not
    # an inferred count of the steps the hosted model actually used.
    assert answer['budget_used']['model_calls'] == 8
    assert answer['budget_used']['model_host_invocations'] == 2
    assert [event['status'] for event in answer['tool_events'] if event['tool'] == 'answer.citations'] == ['REJECTED', 'REPAIRED']
    assert len(calls) == 2


def test_metadata_result_repair_retains_actual_values_and_exact_whole_result_marker(tmp_path, monkeypatch):
    import caelab.assist.openscience_host as host
    identifier = 'Jrecorded'
    recorded = {'candidate_count': 8, 'execution_status': 'SUCCEEDED',
        'statistics': [{'metric': 'peak_force', 'unit': 'N', 'count': 8, 'min': 1.25, 'max': 9.75}],
        'sensitivity': [{'metric': 'peak_force', 'valid': True,
                         'coefficients': [{'parameter_id': 'mass_kg', 'coefficient': 0.6125}]}],
        'surrogate': [{'metric': 'peak_force', 'unit': 'N', 'valid': True, 'test_rmse': 0.03125}]}
    calls = []
    def fake_host(prompt, tools, _budget, _model, **_kwargs):
        calls.append(sorted(tools))
        if len(calls) == 1:
            returned = tools['results_read']['call'](job_id=identifier, selection={'metadata_only': True})
            marker = {'run_id': identifier, 'response_selection': []}
            assert returned['citation_markers'] == [marker]
            assert 'whole returned metadata' in returned['citation_rule']
            assert returned['result']['statistics'][0]['max'] == 9.75
            return json.dumps({'answer': 'The actual eight samples reached 9.75 N.', 'sources': [
                {'run_id': identifier, 'response_selection': ['result.statistics']}],
                'assumptions': [], 'proposed_actions': []})
        assert tools == {}
        payload = json.loads(prompt.rsplit('\n', 1)[1])
        assert payload['verified_sources'] == [{'run_id': identifier, 'response_selection': []}]
        evidence = next(row for row in payload['verified_evidence'] if row['tool'] == 'results.read')
        assert evidence['returned']['result']['statistics'][0]['max'] == 9.75
        assert evidence['returned']['result']['sensitivity'][0]['coefficients'][0]['coefficient'] == 0.6125
        assert evidence['returned']['result']['surrogate'][0]['test_rmse'] == 0.03125
        assert 'does not mean the result was empty' in prompt
        return json.dumps({'answer': 'The recorded eight-sample maximum was 9.75 N; '
                           'normalized mass coefficient 0.6125 and held-out RMSE 0.03125 N.',
                           'sources': payload['verified_sources'], 'assumptions': [], 'proposed_actions': []})
    monkeypatch.setattr(host, 'run_openscience', fake_host)
    runtime = ExpertRuntime(store(tmp_path), Literature(), experts=definitions(['results.read']),
        callbacks={'results.read': lambda _request: recorded},
        runtime=RuntimeConfig(provider='openscience', model='openai-codex/gpt-5.6-sol',
            transmission={'allow_external_model': True, 'allow_question': True,
                          'allow_results': True}))
    answer = runtime.ask('materials', 'Summarize the actual analysis',
        {'selected_result_ids': [identifier], 'transmission_scope': {'allow_question': True,
         'result_ids': [identifier]}}, workspace_id='alpha')
    assert answer['status'] == 'ANSWERED', answer
    assert answer['sources'] == [{'run_id': identifier, 'response_selection': []}]
    assert '9.75 N' in answer['answer'] and '0.03125 N' in answer['answer']
    assert len(calls) == 2


@pytest.mark.parametrize(('returncode', 'stdout', 'error'), [
    (0, '{"status":"stopped","cleanup_confirmed":true}', ExecutionCancelled),
    (1, '{"status":"stopped","cleanup_confirmed":true}', ExecutionCleanupFailed),
    (0, 'not json', ExecutionCleanupFailed),
    (0, '{"status":"stopped","cleanup_confirmed":false}', ExecutionCleanupFailed),
    (0, '{"status":"stopped"}', ExecutionCleanupFailed),
])
def test_openscience_host_cancellation_requires_confirmed_owned_child_cleanup(
        monkeypatch, returncode, stdout, error):
    import time
    from types import SimpleNamespace
    from urllib.request import Request, urlopen
    import caelab.assist.openscience_host as host
    import mcp.server.lowlevel  # Import before replacing subprocess.Popen in this test.
    from caelab.execution_control import (CancellationToken, ExecutionCancelled,
                                           ExecutionCleanupFailed, cancellation_scope)
    token = CancellationToken()
    observed = []
    monkeypatch.setattr(host.subprocess, 'check_output', lambda *_args, **_kwargs: 'C:\\host.ps1\n')
    class FakeProcess:
        def __init__(self, *_args, **_kwargs):
            self.turn = 0
            self.returncode = None
        def communicate(self, input=None, timeout=None):
            self.turn += 1
            if self.turn == 1:
                request = json.loads(input)
                token.request()
                probe = Request(request['bridge_url'] + '/status', headers={
                    'Authorization': 'Bearer ' + request['bridge_token']})
                with urlopen(probe, timeout=2) as response:
                    observed.append(json.load(response)['cancel_requested'])
                raise host.subprocess.TimeoutExpired('pwsh.exe', timeout)
            self.returncode = returncode
            return stdout, 'Synthetic wrapper status'
    monkeypatch.setattr(host.subprocess, 'Popen', FakeProcess)
    with cancellation_scope(token), pytest.raises(error):
        host.run_openscience('bounded prompt', {}, SimpleNamespace(
            deadline=time.monotonic() + 5), 'openai-codex/gpt-5.6-sol', max_steps=1)
    assert observed == [True]


def test_openscience_host_uses_utf8_for_unicode_request_and_response(monkeypatch):
    import time
    from types import SimpleNamespace
    import caelab.assist.openscience_host as host
    import mcp.server.lowlevel  # Import before replacing subprocess.Popen in this test.
    prompt = '검토: 항복강도 σy와 길이 10 μm'
    answer = '검토 완료: σy=210 MPa, 길이 10 μm'
    monkeypatch.setattr(host.subprocess, 'check_output', lambda *_args, **_kwargs: 'C:\\host.ps1\n')
    class FakeProcess:
        returncode = 0
        def __init__(self, *_args, **kwargs):
            assert kwargs['encoding'] == 'utf-8'
            assert kwargs['errors'] == 'strict'
        def communicate(self, input=None, timeout=None):
            assert json.loads(input)['prompt'] == prompt
            return json.dumps({'status': 'completed', 'cleanup_confirmed': True,
                               'text': answer}, ensure_ascii=False), ''
    monkeypatch.setattr(host.subprocess, 'Popen', FakeProcess)
    assert host.run_openscience(prompt, {}, SimpleNamespace(deadline=time.monotonic() + 5),
                                'openai-codex/gpt-5.6-sol', max_steps=1) == answer


def test_openscience_remote_mcp_handshake_auth_scope_and_invocation(monkeypatch):
    import asyncio
    import time
    from types import SimpleNamespace
    import httpx
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client
    import caelab.assist.openscience_host as host

    observed = []
    monkeypatch.setattr(host.subprocess, 'check_output', lambda *_args, **_kwargs: 'C:\\host.ps1\n')

    class FakeProcess:
        returncode = 0
        def __init__(self, *_args, **_kwargs):
            pass
        def communicate(self, input=None, timeout=None):
            request = json.loads(input)
            assert request['mcp_url'].startswith('http://127.0.0.1:')
            assert 'bridge_python' not in request

            async def probe():
                async with httpx.AsyncClient(timeout=5) as anonymous:
                    rejected = await anonymous.post(request['mcp_url'], json={})
                    assert rejected.status_code == 403
                async with httpx.AsyncClient(timeout=5, headers={
                        'Authorization': 'Bearer ' + request['bridge_token']}) as client:
                    async with streamable_http_client(request['mcp_url'], http_client=client) as (reader, writer, _):
                        async with ClientSession(reader, writer) as session:
                            await session.initialize()
                            listed = await session.list_tools()
                            assert [tool.name for tool in listed.tools] == ['knowledge_source']
                            called = await session.call_tool('knowledge_source', {'document_id': 'visible'})
                            assert called.isError is False
                            observed.append(json.loads(called.content[0].text))
            asyncio.run(probe())
            return json.dumps({'status': 'completed', 'cleanup_confirmed': True,
                               'text': '{"answer":"done","sources":[]}'}, ensure_ascii=False), ''

    monkeypatch.setattr(host.subprocess, 'Popen', FakeProcess)
    tools = {'knowledge_source': {'parameters': {'type': 'object',
        'properties': {'document_id': {'type': 'string'}}, 'required': ['document_id']},
        'description': 'Read one selected source',
        'call': lambda **kwargs: {'status': 'READ', 'document_id': kwargs['document_id']}}}
    host.run_openscience('check scoped tool', tools, SimpleNamespace(deadline=time.monotonic() + 10),
                         'openai-codex/gpt-5.6-sol', max_steps=1)
    assert observed == [{'status': 'READ', 'document_id': 'visible'}]


def test_remote_mcp_callbacks_share_owner_token_and_reject_after_cancellation(monkeypatch):
    import asyncio
    import time
    from types import SimpleNamespace
    import httpx
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client
    import caelab.assist.openscience_host as host
    from caelab.execution_control import (CancellationToken, ExecutionCancelled,
                                           _current, cancellation_scope)
    owner = CancellationToken()
    callbacks = []
    monkeypatch.setattr(host.subprocess, 'check_output', lambda *_args, **_kwargs: 'C:\\host.ps1\n')

    class FakeProcess:
        returncode = 0
        def __init__(self, *_args, **_kwargs):
            pass
        def communicate(self, input=None, timeout=None):
            request = json.loads(input)

            async def probe():
                async with httpx.AsyncClient(timeout=5, headers={
                        'Authorization': 'Bearer ' + request['bridge_token']}) as client:
                    async with streamable_http_client(request['mcp_url'], http_client=client) as (reader, writer, _):
                        async with ClientSession(reader, writer) as session:
                            await session.initialize()
                            first = await session.call_tool('scoped_probe', {'value': 1})
                            assert first.isError is False
                            owner.request()
                            second = await session.call_tool('scoped_probe', {'value': 2})
                            assert second.isError is True
                            rejected = json.loads(second.content[0].text)
                            assert rejected['status'] == 'TOOL_REJECTED'
                            assert rejected['error'] == 'ExecutionCancelled'
            asyncio.run(probe())
            return json.dumps({'status': 'stopped', 'cleanup_confirmed': True}), ''

    monkeypatch.setattr(host.subprocess, 'Popen', FakeProcess)
    tools = {'scoped_probe': {'parameters': {'type': 'object',
        'properties': {'value': {'type': 'integer'}}, 'required': ['value']},
        'description': 'Approved test callback',
        'call': lambda **kwargs: callbacks.append((_current.get() is owner, kwargs['value'])) or {'ok': True}}}
    with cancellation_scope(owner), pytest.raises(ExecutionCancelled):
        host.run_openscience('scope check', tools, SimpleNamespace(deadline=time.monotonic() + 10),
                             'openai-codex/gpt-5.6-sol', max_steps=1)
    assert callbacks == [(True, 1)]


def test_plain_final_answer_gets_one_no_tool_format_repair_and_keeps_tool_plan(tmp_path, monkeypatch):
    import caelab.assist.openscience_host as host
    calls = []
    def fake_host(_prompt, tools, _budget, _model, **_kwargs):
        calls.append(sorted(tools))
        if len(calls) == 1:
            planned = tools['calculations_plan']['call'](purpose='Screen a response', operation='doe',
                inputs={'backend':'test', 'variables':[{'id':'x','unit':'1','lower':0,'upper':1}],
                        'count':2,'seed':1}, budget={'evaluations':2})
            assert planned['status'] == 'PLANNED'
            return 'The plan was created, but I forgot the JSON wrapper.'
        assert tools == {}
        return json.dumps({'answer':'An editable DOE plan was created, not run.', 'sources':[],
                           'proposed_actions':['Try to add a new action']})
    monkeypatch.setattr(host, 'run_openscience', fake_host)
    runtime = ExpertRuntime(store(tmp_path), Literature(), experts=definitions(['calculations.plan']),
        runtime=RuntimeConfig(provider='openscience', model='openai-codex/gpt-5.6-sol',
            transmission={'allow_external_model':True,'allow_question':True}))
    result = runtime.ask('materials', 'Plan a DOE', {'transmission_scope':{'allow_question':True}}, workspace_id='alpha')
    assert result['status'] == 'ANSWERED', result
    assert result['proposed_actions'][0]['plan']['operation'] == 'doe'
    assert len(result['proposed_actions']) == 1
    assert [event['status'] for event in result['tool_events'] if event['tool']=='answer.format'] == ['REJECTED','REPAIRED']
    assert len(calls) == 2


def test_openscience_step_reservation_bounds_nested_consultation_and_repair(tmp_path, monkeypatch):
    import caelab.assist.openscience_host as host
    steps = []
    def fake_host(_prompt, tools, _budget, _model, *, max_steps, **_kwargs):
        steps.append(max_steps)
        if len(steps) == 1:
            nested = tools['experts_consult']['call'](expert_id='testing', question='Check this?')
            assert nested['status'] == 'ANSWERED'
            return 'Parent answer without JSON wrapper.'
        if len(steps) == 2:
            return json.dumps({'answer': 'Nested check complete.', 'sources': [],
                               'assumptions': [], 'proposed_actions': []})
        assert tools == {}
        return json.dumps({'answer': 'The check was proposed.', 'sources': [],
                           'assumptions': [], 'proposed_actions': []})
    monkeypatch.setattr(host, 'run_openscience', fake_host)
    runtime = ExpertRuntime(store(tmp_path), Literature(), experts=definitions(['experts.consult']),
        runtime=RuntimeConfig(provider='openscience', model='openai-codex/gpt-5.6-sol',
            max_model_calls=6, max_consultations=1,
            transmission={'allow_external_model': True, 'allow_question': True}))
    result = runtime.ask('materials', 'Review', {'consult_experts': ['testing'],
        'transmission_scope': {'allow_question': True}}, workspace_id='alpha')
    assert result['status'] == 'ANSWERED', result
    assert steps == [3, 2, 1]
    assert result['budget_used']['model_calls'] == 6
    assert result['budget_used']['model_host_invocations'] == 3


def test_plan_rejects_noncanonical_operation_keys_and_backend_settings(tmp_path):
    schema = {'type': 'object', 'additionalProperties': False,
              'properties': {'values': {'type': 'object'}, 'conditions': {
                  'type': 'object', 'additionalProperties': False,
                  'properties': {'duration_s': {'type': 'number'}}, 'required': ['duration_s']}}}
    _, runtime = runtime_for(tmp_path, callbacks={
        'calculations.inputs': lambda _request: {'settings_schema': schema}})
    base = {'purpose': 'Explore a real response', 'operation': 'doe',
            'inputs': {'backend': 'external.oscillator', 'settings': {'conditions': {'duration_s': 1}},
                       'variables': [{'id': 'mass_kg', 'unit': 'kg', 'lower': 1, 'upper': 2}],
                       'count': 4, 'seed': 7}, 'budget': {'evaluations': 4}}
    assert runtime.plan(base)['status'] == 'PLANNED'
    malformed = json.loads(json.dumps(base))
    malformed['inputs']['design'] = {'count': 4, 'method': 'LHS'}
    with pytest.raises(ValueError, match='Additional properties'):
        runtime.plan(malformed)
    malformed = json.loads(json.dumps(base))
    malformed['inputs']['settings'] = {'conditions': {'unexpected': 1}}
    with pytest.raises(ValueError, match='Invalid backend settings'):
        runtime.plan(malformed)
    malformed = json.loads(json.dumps(base))
    malformed['inputs']['count'] = 5
    with pytest.raises(ValueError, match='exceeds the evaluation budget'):
        runtime.plan(malformed)


def test_generated_job_grant_survives_restart_and_rechecks_workspace(tmp_path):
    job = 'Jgenerated'
    callbacks = {
        'calculations.submit': lambda request: {'job_id': job, 'state': 'QUEUED'},
        'calculations.status': lambda request: {'job_id': job, 'workspace_id': 'alpha',
                                                'state': 'SUCCEEDED', 'result_refs': ['result.json']},
        'results.read': lambda request: {'responses': {'stress': {'value': 3, 'unit': 'MPa'}}},
    }
    generator = mock_generator([('calculations_submit', {'operation': 'evaluate', 'inputs': {'backend': 'test'},
                                                          'budget': {'evaluations': 1}}),
                                {'answer': 'Submitted a managed job.', 'sources': []}])
    knowledge, runtime = runtime_for(tmp_path, generator, tools=['calculations.submit'], callbacks=callbacks)
    first = runtime.ask('materials', 'Run', {'calculation_scope': {'allow_execution': True,
        'max_evaluations': 1, 'backends': ['test']}}, workspace_id='alpha')
    assert first['status'] == 'ANSWERED', first
    assert first['tool_events'][0]['summary']['job_id'] == job
    later = ExpertRuntime(knowledge, Literature(), experts=definitions(['calculations.status', 'results.read']),
        callbacks=callbacks, runtime=RuntimeConfig(generator=mock_generator([
            ('calculations_status', {'job_id': job}), ('results_read', {'job_id': job}),
            {'answer': 'The retained stress is 3 MPa.', 'sources': [{'run_id': job, 'response_selection': []}]}]),
            external_model=False), session_root=runtime.session_root)
    result = later.ask('materials', 'Read the completed job', session_id=first['session_id'], workspace_id='alpha')
    assert result['status'] == 'ANSWERED', result
    assert result['sources'][0]['run_id'] == job
    later.callbacks['calculations.status'] = lambda request: {'job_id': job, 'workspace_id': 'beta', 'state': 'SUCCEEDED'}
    later.runtime.generator.script = [('results_read', {'job_id': job})]
    rejected = later.ask('materials', 'Read again', session_id=first['session_id'], workspace_id='alpha')
    assert rejected['status'] == 'FAILED'
    assert 'selected access scope' in rejected['reason']


def test_public_discovery_scope_allows_new_query_and_discovered_paper(tmp_path):
    class PublicSource:
        def __init__(self):
            self.calls = []
        def search(self, **request):
            self.calls.append(('search', request))
            return {'status': 'OK', 'papers': [{'paper_id': 'doi:new-study', 'title': 'A study'}]}
        def read(self, **request):
            self.calls.append(('read', request))
            return {'status': 'abstract_only', 'paper_id': request['paper_id'],
                    'segments': [{'locator': {'kind': 'abstract'}, 'text': 'Actual abstract text'}]}
    literature = PublicSource()
    generator = mock_generator([('literature_search', {'query': 'new bounded search', 'providers': ['crossref']}),
                                ('literature_read', {'paper_id': 'doi:new-study', 'locator': {'kind': 'abstract'}}),
                                {'answer': 'The abstract reports a study.', 'sources': [
                                    {'paper_id': 'doi:new-study', 'locator': {'kind': 'abstract'}}]}])
    runtime = ExpertRuntime(store(tmp_path), literature, experts=definitions(['literature.search', 'literature.read']),
        runtime=RuntimeConfig(generator=generator, external_model=True,
            transmission={'allow_external_model': True, 'allow_question': True, 'allow_public_search': True}))
    context = {'transmission_scope': {'allow_question': True, 'allow_public_search': True}}
    answer = runtime.ask('materials', 'Find public work', context, workspace_id='alpha')
    assert answer['status'] == 'ANSWERED', answer
    assert [name for name, _ in literature.calls] == ['search', 'read']
    generator.script = [('literature_search', {'query': 'another search'})]
    context['transmission_scope']['allow_public_search'] = False
    denied = runtime.ask('materials', 'Find public work', context, workspace_id='alpha')
    assert denied['status'] == 'FAILED'
    assert len(literature.calls) == 2
