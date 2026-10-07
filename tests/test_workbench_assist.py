"""Offline contract checks; fake generator is a mock, never live inference evidence."""
from pathlib import Path
import json
import pytest
from caelab.assist import Assistance, ExpertRuntime, KnowledgeStore, Literature, RuntimeConfig


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
                return {'replies': [ChatMessage.from_assistant(tool_calls=[ToolCall(tool_name=name, arguments={'request': request}, id=str(len(self.calls)))])]}
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
            'variables': [{'id': 'x', 'lower': 0, 'upper': 1}]}, 'budget': {'evaluations': 4}}
    generator = mock_generator([('calculations_plan', plan),
        ('numerical_doe', {'backend': 'registered-test-model', 'budget': {'evaluations': 4}}),
        lambda messages: ('numerical_analyze', {'candidates': json.loads(messages[-1].tool_call_results[0].result)['candidates']}),
        lambda messages: {'answer': 'Actual least-squares slope is ' + str(json.loads(messages[-1].tool_call_results[0].result)['slope']),
                          'sources': [], 'proposed_actions': [{'purpose': 'Confirm at a second condition', 'operation': 'doe',
                            'inputs': {'backend': 'registered-test-model'}, 'budget': {'evaluations': 2}}]}])
    _, runtime = runtime_for(tmp_path, generator, tools=['calculations.plan', 'numerical.doe', 'numerical.analyze'],
                            callbacks={'numerical.doe': doe, 'numerical.analyze': analyze})
    result = runtime.ask('materials', 'Propose DOE, compute influence and propose next study',
                         {'calculation_scope': {'allow_execution': True, 'max_evaluations': 4,
                                                'backends': ['registered-test-model']}}, workspace_id='alpha')
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
    request = {'backend': 'test', 'budget': {'evaluations': 3}}
    generator = mock_generator([('numerical_doe', request), ('numerical_doe', request)])
    _, runtime = runtime_for(tmp_path, generator, tools=['numerical.doe'],
                            callbacks={'numerical.doe': lambda value: calls.append(value) or {'status': 'SUCCEEDED'}})
    context = {'calculation_scope': {'allow_execution': True, 'max_evaluations': 4, 'backends': ['test'],
                                    'variables': {'E': [1, 10]}}}
    result = runtime.ask('materials', 'run batches', context)
    assert result['status'] == 'FAILED' and len(calls) == 1
    generator.script = [('numerical_doe', {**request, 'variables': [{'id': 'E', 'lower': 1, 'upper': 50}]})]
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
                           'experiments': [{'observation_job': 'OTHER_PROJECT'}]})]:
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
        ('numerical_analyze', {'job_id': 'ALLOWED', 'responses': ['force']}),
        {'answer': 'Actual slope is 9.', 'sources': [{'run_id': 'ALLOWED', 'response_selection': ['force']}]}])
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
    assert analysis['sources'] == [{'run_id': 'ALLOWED', 'response_selection': ['force']}]


@pytest.mark.parametrize('tool,nested',[('numerical.doe',False),('calculations.submit',True)])
def test_effective_numerical_workers_obey_expert_resource_scope(tmp_path,tool,nested):
    calls=[]
    inputs={'backend':'test','execution':{'mode':'process','workers':8,'threads':1}}
    request={'operation':'doe','inputs':inputs} if nested else inputs
    request={**request,'budget':{'evaluations':2}}
    generator=mock_generator([(tool.replace('.','_'),request)])
    _,runtime=runtime_for(tmp_path,generator,tools=[tool],callbacks={tool:lambda value:calls.append(value) or {'status':'SUCCEEDED'}})
    response=runtime.ask('materials','Run',{'calculation_scope':{'allow_execution':True,'max_evaluations':2,
        'backends':['test'],'resources':{'threads':1}}})
    assert response['status']=='FAILED' and 'Resource request' in response['reason']
    assert calls==[]
