"""Exact local source scope; scripted generators/host are explicit test doubles."""
from copy import deepcopy
import json
import time

import pytest

from caelab.assist.knowledge import selected_source_refs
from caelab.assist.experts import ExpertRuntime, RuntimeConfig
from caelab.discussion_document import default_draft
from caelab.workbench import Workbench
from test_workbench_assist import store, ingest, mock_generator, runtime_for


def pins(*documents):
    return {'selected_sources': [{'document_id': doc['document_id'], 'revision': doc['revision']}
                                 for doc in documents],
            'selected_document_ids': [doc['document_id'] for doc in documents]}


def test_exact_revision_search_source_and_same_collection_isolation(tmp_path):
    generator = mock_generator([])
    knowledge, runtime = runtime_for(tmp_path, generator, tools=['knowledge.search', 'knowledge.source'])
    first = ingest(knowledge, tmp_path, '# Original\nALPHA stiffness 17', name='a.md')
    other = ingest(knowledge, tmp_path, '# Other\nSECRET-B stiffness 999', name='b.md')
    ingest(knowledge, tmp_path, '# Changed\nALPHA stiffness 23', name='a.md', document_id=first['document_id'])
    selection = pins(first)
    hits = knowledge.search('stiffness', ['materials'], workspace_id='alpha',
                            source_refs=selection['selected_sources'])['hits']
    assert hits and {row['revision'] for row in hits} == {1}
    assert {row['document_id'] for row in hits} == {first['document_id']}
    seen = []
    def final(messages):
        seen.append(json.loads(messages[-1].tool_call_results[0].result))
        return {'answer': 'SCRIPTED TEST: original only', 'sources': []}
    generator.script = [('knowledge_source', {'document_id': first['document_id']}), final]
    result = runtime.ask('materials', 'Read selected', selection, workspace_id='alpha')
    assert result['status'] == 'ANSWERED', result
    assert seen[0]['revision'] == 1 and '17' in seen[0]['segments'][0]['text']
    assert 'SECRET-B' not in str([message.to_dict() for call in generator.calls for message in call])
    for request in ({'document_id': other['document_id']},
                    {'document_id': first['document_id'], 'revision': 2}):
        generator.script = [('knowledge_source', request)]
        assert runtime.ask('materials', 'Try source', selection, workspace_id='alpha')['status'] == 'FAILED'
    assert knowledge.search('stiffness', source_refs=[], workspace_id='alpha')['hits'] == []
    with pytest.raises(ValueError, match='pin'):
        runtime.ask('materials', 'Legacy', {'selected_document_ids': [first['document_id']]}, workspace_id='alpha')
    knowledge.revoke(first['document_id'], workspace_id='alpha')
    with pytest.raises(PermissionError):
        runtime.ask('materials', 'Revoked', selection, workspace_id='alpha')


def test_both_histories_and_nested_consultation_keep_exact_scope(tmp_path):
    generator = mock_generator([{'answer': 'SCRIPTED UNSELECTED-HISTORY-SECRET', 'sources': []},
                                {'answer': 'SCRIPTED clean', 'sources': []}])
    knowledge, runtime = runtime_for(tmp_path, generator)
    old = ingest(knowledge, tmp_path, '# Prior\nUNSELECTED-HISTORY-SECRET', name='old.md')
    new = ingest(knowledge, tmp_path, '# Current\ncurrent evidence', name='new.md')
    first = runtime.ask('materials', 'Read prior', pins(old), workspace_id='alpha')
    context = pins(new)
    context['discussion'] = {'turns': [
        {'text': 'UNSELECTED-HISTORY-SECRET', 'knowledge_sources': pins(old)['selected_sources']},
        {'text': 'LEGACY-UNKNOWN-SECRET'},
        {'text': 'Current authored question', 'knowledge_sources': []}], 'evidence': []}
    result = runtime.ask('materials', 'Next', context, first['session_id'], workspace_id='alpha')
    assert result['status'] == 'ANSWERED', result
    transmitted = str([message.to_dict() for message in generator.calls[-1]])
    assert 'UNSELECTED-HISTORY-SECRET' not in transmitted
    assert 'LEGACY-UNKNOWN-SECRET' not in transmitted
    assert 'Current authored question' in transmitted
    runtime.definitions['testing']['collections'] = ['testing']
    generator.script = [('experts_consult', {'expert_id': 'testing',
                                            'question': 'May include current evidence'})]
    result = runtime.ask('materials', 'Consult', dict(pins(new), consult_experts=['testing']), workspace_id='alpha')
    assert result['status'] == 'FAILED'
    assert result['budget_used']['model_calls'] == 1  # No narrower-role inference.


def test_openscience_tools_and_explicit_source_transmission_use_same_pins(tmp_path, monkeypatch):
    knowledge = store(tmp_path)
    first = ingest(knowledge, tmp_path, '# Source\noriginal source text', name='a.md')
    other = ingest(knowledge, tmp_path, '# Other\nPRIVATE UNSELECTED text', name='b.md')
    ingest(knowledge, tmp_path, '# Revised\nreplacement source text', name='a.md', document_id=first['document_id'])
    calls = []
    def host(prompt, tools, budget, model, **kwargs):
        calls.append(prompt)
        assert 'original source text' in prompt and 'replacement source text' not in prompt
        assert 'PRIVATE UNSELECTED' not in prompt
        assert tools['knowledge_source']['call'](document_id=first['document_id'])['revision'] == 1
        with pytest.raises(PermissionError):
            tools['knowledge_source']['call'](document_id=other['document_id'])
        found = tools['knowledge_search']['call'](query='source')
        assert found['hits'] and all(row['revision'] == 1 for row in found['hits'])
        return json.dumps({'answer': 'EXPLICIT TEST HOST', 'sources': []})
    monkeypatch.setattr('caelab.assist.openscience_host.run_openscience', host)
    from caelab.assist import Literature
    runtime = ExpertRuntime(knowledge, Literature(),
        experts=[{'id': 'reviewer', 'collections': ['materials'],
                  'tools': ['knowledge.source', 'knowledge.search']}],
        runtime=RuntimeConfig(provider='openscience', model='openai-codex/test-double', external_model=True,
            transmission={'allow_external_model': True, 'allow_question': True, 'collections': ['materials']}))
    context = pins(first)
    context['transmission_scope'] = {'allow_question': True, 'collections': ['materials']}
    with pytest.raises(PermissionError):
        runtime.ask('reviewer', 'Question', context, workspace_id='alpha')
    assert not calls
    context['transmission_scope']['source_refs'] = deepcopy(context['selected_sources'])
    result = runtime.ask('reviewer', 'Question', context, workspace_id='alpha')
    assert result['status'] == 'ANSWERED', result
    assert len(calls) == 1  # No account, provider, key or real model call.


def test_managed_import_and_discussion_freeze_local_save_and_legacy_block(tmp_path):
    wb = Workbench(tmp_path / 'store')
    try:
        upload = wb.upload('연구 자료.md', b'# Local source\nRetained public fixture.')
        job = wb.submit('knowledge.ingest', {'data_id': upload['id'], 'collection': 'research'},
                        request_id='source-import-test')
        deadline = time.monotonic() + 5
        while wb.manager.status(job['id'])['state'] not in {'SUCCEEDED', 'FAILED'} and time.monotonic() < deadline:
            time.sleep(.005)
        result = wb.manager.result(job['id'])
        source = wb.assistance_call('knowledge.source',
            {'document_id': result['document_id'], 'revision': result['revision']})
        assert source['segments'][0]['text'].startswith('# Local source')
        draft = default_draft()
        draft['composer']['text'] = 'Keep my question'
        draft['context'].update(pins(result))
        owner = wb.discussion_documents
        doc = owner.open(draft=draft)
        def command(operation, arguments=None):
            nonlocal doc
            doc = owner.command(doc['id'], operation, arguments or {}, session_id=wb.session_id,
                expected_generation=doc['generation'])['document']
            return doc
        command('document.save')
        command('expert.intervene')
        assert doc['turns'][0]['knowledge_sources'] == draft['context']['selected_sources']
        assert len(wb.manager.list()) == 1  # Import only, no Ask or solver.
        changed = deepcopy(doc['draft'])
        changed['context'] = {'selected_document_ids': [result['document_id']]}
        changed['participants'] = ['test']
        owner.list_experts = lambda: {'experts': [{'id': 'test'}]}
        command('expert.update', {'draft': changed})
        with pytest.raises(ValueError, match='pin'):
            command('expert.ask')
        assert len(wb.manager.list()) == 1
        # Existing frozen legacy rounds cannot trap a repaired current draft.
        internal = owner._documents[doc['id']]
        record = {'id': 'Blegacy', 'roles': ['test'], 'next_index': 0,
                  'draft': deepcopy(changed), 'status': 'READY', 'history': [],
                  'sessions': {'test': 'Etest'}, 'user_turn_id': 'Utest',
                  'input_generation': internal['generation'], 'input_revision': internal['input_revision']}
        internal['discussion']['rounds'].append(record)
        owner._persist_draft(internal)
        command('expert.advance')
        assert doc['discussion']['rounds'][-1]['status'] == 'BLOCKED_SOURCES'
        assert doc['discussion']['rounds'][-1]['draft'] == changed
        command('document.undo')
        assert doc['draft']['context']['selected_sources'] == draft['context']['selected_sources']
        command('document.save')
        identifier = doc['id']
    finally:
        wb.shutdown()
    reopened = Workbench(tmp_path / 'store')
    try:
        saved = reopened.document_read(identifier)
        assert saved['draft']['composer']['text'] == 'Keep my question'
        assert saved['draft']['context']['selected_sources'] == draft['context']['selected_sources']
        assert saved['turns'][0]['status'] == 'AUTHORED'
    finally:
        reopened.shutdown()
