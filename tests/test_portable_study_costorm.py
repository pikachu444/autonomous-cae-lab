"""Real vendored runner/owner; generation and exact retrieval are labelled doubles.

NO AI answer, provider, Haystack ranking qualification or installation. The
existing knowledge source/access/transmission gates and owner dispatch run.
"""
from copy import deepcopy
from contextlib import contextmanager
from unittest.mock import patch

import pytest
from caelab.assist.knowledge import KnowledgeStore
from caelab.assist.experts import RuntimeConfig
from caelab.storage import canonical_hash
from examples.portable_study_expert_public import fixture, publish, rows, saved, update, cmd, finished, source_free, LABEL
from test_portable_study_expert import workspace, policy
from test_costorm_protocol import scripted  # Existing labelled generation boundary.

ROLES = [{'id': n, 'label': n, 'instructions': LABEL, 'collections': ['research'],
    'tools': ['knowledge.search', 'knowledge.source']} for n in ('testing', 'mechanics')]


@contextmanager
def controlled_protocol(wb):
    """The existing runner is not replaced. Only LM output/retrieval is scripted."""
    def retrieval(store, query, collections=None, filters=None, top_k=10, *, workspace_id='local', source_refs=None):
        assert source_refs, 'Co-STORM must pin exact selected sources'
        hits=[]
        for ref in source_refs:
            selected=store.source(**ref, workspace_id=workspace_id, collections=collections)
            hits.extend({**deepcopy(row), 'score':1.0} for row in selected['segments'])
        return {'status':'OK', 'method': 'CONTROLLED EXACT SOURCE ENUMERATION — NOT BM25 QUALIFICATION', 'hits':hits[:top_k]}
    runtime=wb.assistance().experts
    settings=RuntimeConfig(provider='openscience', model='openai-codex/test-double', external_model=False,
        max_model_calls=100,max_tool_calls=100,max_seconds=60)
    with patch.object(runtime, 'definitions', {r['id']:r for r in ROLES}), patch.object(runtime, 'runtime', settings), \
         patch('caelab.assist.readiness.require_features', return_value=None), patch.object(KnowledgeStore,'search', retrieval):
        yield


def protocol_draft(doc, source, *, calls=100):
    draft=deepcopy(doc['draft'])
    draft['participants']=['testing','mechanics']
    draft['composer']['text']=LABEL+' — What do the ALPHA measurements show?'
    draft['context']={'discussion_mode':'costorm','selected_sources':[{'document_id':source['document_id'],'revision':1}]}
    draft['budget']={'model_calls':calls,'tool_calls':100,'consultations':0,'seconds':60}
    return draft


def test_actual_costorm_report_partial_journal_copy_new_failure_and_recopy(tmp_path, scripted):
    with workspace(tmp_path/'origin') as wb, controlled_protocol(wb):
        case=fixture(wb,history=False)
        doc=wb.document_open(kind='expert')
        doc=update(wb,doc,protocol_draft(doc,case['source']))
        doc,response=finished(wb,doc,cmd(wb,doc,'expert.ask'))
        assert response['status']=='ANSWERED', response
        assert doc['discussion']['costorm']['topics']
        doc,response=finished(wb,doc,cmd(wb,doc,'expert.report'))
        assert response['status']=='ANSWERED',response
        report=deepcopy(doc['discussion']['costorm']['report'])
        assert report['references']
        doc=saved(wb,doc)
        complete_id=doc['id']
        partial=wb.document_open(kind='expert')
        partial=update(wb,partial,protocol_draft(partial,case['source'],calls=2))
        partial,response=finished(wb,partial,cmd(wb,partial,'expert.ask'))
        assert response['status']=='STOPPED',response
        journal=deepcopy(response['costorm']['retry']['journal'])
        assert len(journal)==2
        partial=saved(wb,partial)
        old_turns=deepcopy(doc['turns']); partial_id=partial['id']
        receipt=publish(wb,[doc['id'],partial['id']],tmp_path/'copy')
        old_calls=len(scripted)
    # The only generated origin is removed after its controller has joined.
    from examples.portable_study_expert_public import owned_remove
    owned_remove(tmp_path,tmp_path/'origin')
    mapping={r['source_document_id']:r['document_id'] for r in receipt['documents']}
    with workspace(tmp_path/'copy') as wb:
        with source_free(wb):
            doc=wb.document_read(mapping[complete_id]); partial=wb.document_read(mapping[partial_id])
            assert doc['discussion']['costorm']['report']==report
            assert doc['turns']==old_turns
            assert wb.document_result(partial['id'],partial['runs'][-1]['job_id'])['costorm']['retry']['journal']==journal
            assert len(scripted)==old_calls and not wb.manager.list()
            with pytest.raises(ValueError,match='먼저'):
                cmd(wb,partial,'expert.retry')
        # A fresh local NOT_CONFIGURED job must keep the archived readable report/map.
        draft=protocol_draft(doc,case['source']); draft['composer']['text']+=' 새 현지 질문'
        doc=update(wb,doc,draft)
        # Current role registry is explicit; provider/generator remains unset.
        with patch.object(wb.assistance().experts, 'definitions', {r['id']:r for r in ROLES}):
            doc,response=finished(wb,doc,cmd(wb,doc,'expert.ask'))
        assert response['status']=='NOT_CONFIGURED', response
        assert doc['discussion']['costorm']['report']==report
        assert doc['draft']['composer']['text']==draft['composer']['text']
        assert len(scripted)==old_calls
        doc=saved(wb,doc); partial=saved(wb,partial)
        made=publish(wb,[doc['id'],partial['id']],tmp_path/'recopy')
        ids=[r['document_id'] for r in made['documents']]
    owned_remove(tmp_path,tmp_path/'copy')
    with workspace(tmp_path/'recopy') as wb, source_free(wb):
        current=[wb.document_read(i) for i in ids]
        complete=next(d for d in current if d['discussion']['costorm'].get('report'))
        assert complete['discussion']['costorm']['report']==report
        assert len(scripted)==old_calls and not wb.manager.list()


def test_new_costorm_indices_do_not_collide_with_original_turns(tmp_path, scripted):
    with workspace(tmp_path/'origin') as wb, controlled_protocol(wb):
        case=fixture(wb,history=False)
        doc=wb.document_open(kind='expert')
        doc=update(wb,doc,protocol_draft(doc,case['source']))
        doc,response=finished(wb,doc,cmd(wb,doc,'expert.ask'))
        assert response['status']=='ANSWERED',response
        doc=saved(wb,doc); original=deepcopy(doc['turns'])
        receipt=publish(wb,[doc['id']],tmp_path/'copy')
    with workspace(tmp_path/'copy') as wb, controlled_protocol(wb):
        doc=wb.document_read(rows(receipt)['expert'])
        doc=update(wb,doc,protocol_draft(doc,case['source']))
        doc,response=finished(wb,doc,cmd(wb,doc,'expert.ask'))
        assert response['status']=='ANSWERED',response
        assert doc['turns'][:len(original)]==original
        new=[t for t in doc['turns'][len(original):] if t.get('protocol')=='costorm']
        assert new
        assert {t['protocol_index'] for t in new} & {t['protocol_index'] for t in original if t.get('protocol')=='costorm'}
        submitted=doc['runs'][-1]['arguments']
        assert submitted['context']['costorm']['previous_job_id'] is None
        assert submitted['context']['costorm']['interventions']==[]

# D public retrieval closure: actual owner/runner; network and model are labelled
# doubles from the existing focused protocol checks, never a provider call.
def test_public_report_and_partial_operations_move_exactly_without_source_store(tmp_path, scripted):
    from test_costorm_public_retrieval import configured
    from caelab.portable_project import open_project, inspect_copy
    from caelab.evaluation import file_hash
    from caelab.assist.literature import Literature
    from caelab.assist.costorm import _paper_sources
    wb, draft, _, network = configured(tmp_path/'origin')
    try:
        complete=wb.document_open(kind='expert',draft=draft)
        complete,result=finished(wb,complete,cmd(wb,complete,'expert.ask'))
        assert result['status']=='ANSWERED',result
        source=next(iter(result['costorm']['view']['sources'].values()))
        complete,result=finished(wb,complete,cmd(wb,complete,'expert.report'))
        assert result['status']=='ANSWERED',result
        complete=saved(wb,complete)
        report=deepcopy(complete['discussion']['costorm']['report'])
        partial_draft=deepcopy(draft);partial_draft['budget']['model_calls']=5
        partial=wb.document_open(kind='expert',draft=partial_draft)
        partial,result=finished(wb,partial,cmd(wb,partial,'expert.ask'))
        assert result['status']=='STOPPED',result
        operations=deepcopy(result['costorm']['retry']['retrieval_operations'])
        assert any(op['tool']=='literature.read' for op in operations)
        partial=saved(wb,partial)
        plan=inspect_copy(wb,[complete['id'],partial['id']])
        assert plan['status']=='READY',plan['issues']
        assert plan['literature'] and not plan['knowledge']
        assert all(r['paper_id']==source['paper_id'] for r in plan['literature'])
        archive=source['locator']['archive_id']+'.json'
        digest=file_hash(wb.assistance().literature.root/archive)
        # An unrelated cached archive and mutable catalogue must not be copied.
        (wb.assistance().literature.root/('f'*64+'.json')).write_text('{}')
        receipt=publish(wb,[complete['id'],partial['id']],tmp_path/'copy')
        original={complete['id']:complete,partial['id']:partial}
        counts=len(scripted),len(network)
    finally:wb.shutdown()
    (tmp_path/'origin').rename(tmp_path/'origin-preserved')
    forbidden=lambda *a,**k:pytest.fail('Reopen/copy must not search, call a model or fetch literature')
    with patch('caelab.assist.literature.fetch_url',forbidden):
        cold=open_project(tmp_path/'copy')
    try:
        cold.assistance().literature.fetch=forbidden
        assert not cold.manager.list()
        assert file_hash(cold.assistance().literature.root/archive)==digest
        assert not (cold.assistance().literature.root/('f'*64+'.json')).exists()
        assert not (cold.assistance().literature.root/'papers.json').exists()
        assert not cold.assistance().experts.runtime.generator
        mapping={r['source_document_id']:r['document_id'] for r in receipt['documents']}
        with patch.object(cold,'submit',forbidden),patch.object(cold.manager,'submit',forbidden):
            documents=[cold.document_read(mapping[i]) for i in original]
            complete=next(d for d in documents if d['discussion']['costorm'].get('report'))
            partial=next(d for d in documents if d['id']!=complete['id'])
            assert complete['discussion']['costorm']['report']==report
            recovered=cold.document_result(partial['id'],partial['runs'][-1]['job_id'])
            assert recovered['costorm']['retry']['retrieval_operations']==operations
            assert cold.assistance_call('literature.read',{'paper_id':source['paper_id'],'locator':source['locator']})['segments'][0]['text']==source['text']
        edited=deepcopy(complete['draft']);edited['composer']['text']+=' 새 위치의 판단'
        changed=update(cold,complete,edited)
        undone=cmd(cold,changed,'document.undo')['document'];assert undone['draft']==complete['draft']
        redone=cmd(cold,undone,'document.redo')['document'];assert redone['draft']==edited
        complete=saved(cold,redone)
        second=publish(cold,[complete['id'],partial['id']],tmp_path/'recopy')
        assert (len(scripted),len(network))==counts and not cold.manager.list()
    finally:cold.shutdown()
    (tmp_path/'copy').rename(tmp_path/'copy-preserved')
    last=open_project(tmp_path/'recopy')
    try:
        last.assistance().literature.fetch=forbidden
        documents=[last.document_read(r['document_id']) for r in second['documents']]
        complete=next(d for d in documents if d['discussion']['costorm'].get('report'))
        assert complete['discussion']['costorm']['report']==report
        assert complete['draft']['composer']['text']==edited['composer']['text']
        assert file_hash(last.assistance().literature.root/archive)==digest
        assert not last.manager.list() and (len(scripted),len(network))==counts
    finally:last.shutdown()


@pytest.mark.parametrize('abstract',[True,False])
def test_public_completed_read_operation_alone_is_an_exact_portable_dependency(tmp_path,abstract):
    from types import SimpleNamespace
    from test_costorm_public_retrieval import configured,retriever
    from caelab.portable_research_knowledge import _source_rows,collect_reference,reviewed_literature,check_literature
    wb,draft,_,calls=configured(tmp_path,abstract=abstract)
    try:
        rm=retriever(wb,draft,tools=2)
        with pytest.raises(RuntimeError,match='tool call budget'):rm(['first','second'])
        assert not rm.journal and len(rm.operations)==2
        refs=list(_source_rows({'costorm':{'retry':{'retrieval_operations':rm.operations}}}))
        assert len(refs)==1 and refs[0]['read_status']==('abstract_only' if abstract else 'metadata_only')
        reader=SimpleNamespace(wb=wb)
        collect_reference(reader,refs[0]);rows=reviewed_literature(reader)
        assert len(rows)==1 and rows[0]['archive_id']==refs[0]['locator']['archive_id']
        value=wb.assistance().literature.read(refs[0]['paper_id'],refs[0]['locator'])
        changed={**refs[0],'read_scope':'pretend full text'}
        with pytest.raises(ValueError,match='SOURCE_CHANGED'):check_literature(value,changed)
        archive=wb.assistance().literature.root/(rows[0]['archive_id']+'.json')
        archive.write_text(archive.read_text()+'garbage')
        with pytest.raises((ValueError, __import__('json').JSONDecodeError)):collect_reference(reader,refs[0])
        assert len(calls)==1
    finally:wb.shutdown()

def test_unasked_public_attachment_undo_and_authored_turn_move_without_dispatch(tmp_path):
    from test_costorm_public_retrieval import configured,retriever
    from caelab.portable_project import open_project,inspect_copy
    wb,draft,_,calls=configured(tmp_path/'origin')
    try:
        source=retriever(wb,draft)('ALPHA')[0]['meta']['source']
        # Only discovery is a transport double; there has been no Ask/model.
        doc=wb.document_open(kind='expert')
        edited=deepcopy(doc['draft']);edited['composer']['text']='저장 인용을 붙인 미완성 질문'
        edited['composer']['evidence']=[deepcopy(source)]
        doc=update(wb,doc,edited)
        doc=cmd(wb,doc,'expert.intervene')['document']  # authored note, no response/job
        authored=deepcopy(doc['discussion']['turns'])
        edited=deepcopy(doc['draft']);edited['composer']['evidence']=[]
        doc=update(wb,doc,edited)
        edited['composer']['text']='현재 질문에도 같은 인용을 선택'
        edited['composer']['evidence']=[deepcopy(source)]
        doc=update(wb,doc,edited);doc=saved(wb,doc)
        assert not doc['runs'] and not wb.manager.list() and len(calls)==1
        plan=inspect_copy(wb,[doc['id']]);assert plan['status']=='READY',plan['issues']
        assert len(plan['literature'])==1
        made=publish(wb,[doc['id']],tmp_path/'copy')
    finally:wb.shutdown()
    (tmp_path/'origin').rename(tmp_path/'origin-preserved')
    cold=open_project(tmp_path/'copy')
    try:
        with source_free(cold):
            current=cold.document_read(rows(made)['expert'])
            assert current['draft']['composer']['evidence']==[source]
            assert current['discussion']['turns']==authored
            current=cmd(cold,current,'document.undo')['document']
            assert current['draft']['composer']['evidence']==[]
            current=cmd(cold,current,'document.redo')['document']
            assert current['draft']['composer']['evidence']==[source]
            current=saved(cold,current)
            second=publish(cold,[current['id']],tmp_path/'recopy')
            assert not cold.manager.list()
    finally:cold.shutdown()
    (tmp_path/'copy').rename(tmp_path/'copy-preserved')
    final=open_project(tmp_path/'recopy')
    try:
        with source_free(final):
            current=final.document_read(rows(second)['expert'])
            assert current['draft']['composer']['evidence']==[source]
            assert current['discussion']['turns']==authored
            assert not final.manager.list() and len(calls)==1
    finally:final.shutdown()
