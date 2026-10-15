"""Actual CoSTORM owner/runner; network and completion boundaries are explicit doubles."""
from copy import deepcopy
import json
import time

import pytest

from caelab.assist import costorm
from caelab.assist.experts import _Budget
from caelab.assist.literature import Literature
from caelab.discussion_document import default_draft
from caelab.execution_control import CancellationToken, ExecutionCancelled, cancellation_scope
from caelab.workbench import Workbench
from test_costorm_protocol import command, finished, scripted


def configured(tmp_path, *, operator=True, request=True, tools=True, abstract=True, network='OK', local=False):
    roles = [{'id': name, 'label': name, 'instructions': 'Use actually read evidence, not titles as findings.',
              'collections': ['research'], 'tools': ['knowledge.search', 'knowledge.source', 'literature.search', 'literature.read']}
             for name in ('testing', 'mechanics')]
    if not tools:roles[1]['tools'].remove('literature.read')
    config = {'experts': roles, 'runtime': {'provider': 'openscience', 'model': 'openai-codex/test-double',
        'external_model': False, 'transmission': {'allow_public_search': operator},
        'max_model_calls': 100, 'max_tool_calls': 100, 'max_seconds': 60}}
    wb=Workbench(tmp_path, configuration=config)
    calls=[]
    def fetch(url, **kwargs):
        calls.append(url)
        assert url.startswith('https://api.crossref.org/works?'), 'No publisher/full-text/other provider request'
        if network=='error':raise TimeoutError('Controlled Crossref timeout')
        paper={'DOI':'10.5555/alpha-public', 'URL':'https://doi.org/10.5555/alpha-public',
            'title':['ALPHA measurement study'], 'author':[{'given':'Public','family':'Author'}],
            'published':{'date-parts':[[2024]]}, 'type':'journal-article',
            'link':[{'URL':'https://publisher.example/not-authorized-fulltext.pdf'}]}
        if abstract:paper['abstract']='<jats:p>ALPHA stress is 17 MPa. Measured area matters.</jats:p>'
        body={'message':{'items':[] if network=='empty' else [paper]}}
        return json.dumps(body).encode(),'application/json',url
    wb.assistance().literature=Literature(wb.root/'assistance/literature',fetch=fetch)
    wb.assistance().experts.literature=wb.assistance().literature
    draft=default_draft();draft['participants']=['testing','mechanics']
    draft['composer']['text']='What do the ALPHA measurements show?'
    draft['context']={'discussion_mode':'costorm','selected_sources':[],
        'transmission_scope':{'allow_public_search':request}}
    draft['budget']={'model_calls':100,'tool_calls':100,'consultations':0,'seconds':60}
    if local:
        path=wb.root/'selected.md';path.write_text('ALPHA selected local evidence.',encoding='utf-8')
        source=wb.assistance().knowledge.ingest(str(path),collection='research')
        draft['context']['selected_sources']=[{k:source[k] for k in ('document_id','revision')}]
    return wb,draft,config,calls


def retriever(wb, draft, *, tools=100, seconds=60, journal=None):
    runtime=wb.assistance().experts
    budget=_Budget(runtime.runtime,{'tool_calls':tools,'model_calls':1,'consultations':0,'seconds':seconds})
    return costorm.SelectedRetriever(runtime,deepcopy(draft['context']),'local',['research'],budget,lambda:None,journal=journal)


@pytest.mark.parametrize('operator,allowed,tools',[(False,True,True),(True,False,True),(True,True,False)])
def test_public_only_permission_denial_before_any_model_or_network(tmp_path,scripted,operator,allowed,tools):
    wb,draft,_,calls=configured(tmp_path,operator=operator,request=allowed,tools=tools)
    runtime=wb.assistance().experts
    spec={'roles':draft['participants'],'action':'start'}
    context={**draft['context'],'costorm':spec}
    try:
        with costorm.owner_step({'request':spec}),pytest.raises(PermissionError):
            costorm.run(runtime,runtime.describe('testing'),draft['composer']['text'],context,
                {'session_id':'public-test','turns':[]},tmp_path/'session.json','local',_Budget(runtime.runtime,draft['budget']))
        assert calls==scripted==[]
    finally:wb.shutdown()


def test_actual_runner_public_citations_map_report_save_cold_and_permission_withdrawal(tmp_path,scripted):
    wb,draft,config,calls=configured(tmp_path)
    try:
        doc=wb.document_open(kind='expert',draft=draft)
        doc,result=finished(wb,doc,command(wb,doc,'expert.ask'))
        assert result['status']=='ANSWERED',result
        assert calls and all('crossref.org' in u for u in calls)
        view=doc['discussion']['costorm']
        assert view['topics'] and doc['discussion']['turns']
        source=next(iter(result['costorm']['view']['sources'].values()))
        assert source['paper_id']=='doi:10.5555/alpha-public'
        assert source['doi']=='10.5555/alpha-public' and source['authors']==['Public Author']
        assert source['title']=='ALPHA measurement study' and source['url']=='https://doi.org/10.5555/alpha-public'
        assert source['read_status']=='abstract_only' and 'full text not read' in source['read_scope']
        assert source['locator']['kind']=='abstract' and len(source['locator']['archive_id'])==64
        assert list(costorm._paper_sources(result['costorm']['state']))
        assert any('Actually read abstract:' in p for p in scripted)
        doc,result=finished(wb,doc,command(wb,doc,'expert.report'))
        assert result['status']=='ANSWERED',result
        report=doc['discussion']['costorm']['report']
        assert report['references'] and all(r['source']['paper_id']==source['paper_id'] for r in report['references'])
        doc=command(wb,doc,'document.save')['document'];identifier=doc['id']
        old_calls=len(scripted);old_network=len(calls)
    finally:wb.shutdown()
    cold=Workbench(tmp_path,configuration=config)
    try:
        def forbidden(*a,**k):pytest.fail('Cold read must not access the network')
        cold.assistance().literature.fetch=forbidden
        reopened=cold.document_open(kind='expert',document_id=identifier)
        assert reopened['discussion']['costorm']['report']==report
        assert reopened['discussion']['costorm']['topics']==doc['discussion']['costorm']['topics']
        assert len(scripted)==old_calls and len(calls)==old_network
        changed=deepcopy(reopened['draft']);changed['context']['transmission_scope']['allow_public_search']=False
        reopened=command(cold,reopened,'expert.update',{'draft':changed})['document']
        with pytest.raises((ValueError,PermissionError)):
            command(cold,reopened,'expert.advance')
        assert len(scripted)==old_calls
    finally:cold.shutdown()


def test_selected_local_and_result_precede_public_and_multiquery_is_bounded(tmp_path):
    wb,draft,_,calls=configured(tmp_path,local=True)
    try:
        rm=retriever(wb,draft)
        rm.result_sources=[{'reference':{'job_id':'Jselected','selection':['stress']},'payload':{'responses':{'stress':17}}}]
        rows=rm(['ALPHA','ALPHA','area','third query not sent'])
        assert len(calls)==2 and all('third+query' not in u for u in calls)
        public=next(i for i,r in enumerate(rows) if 'paper_id' in r['meta']['source'])
        assert any('document_id' in r['meta']['source'] for r in rows[:public])
        assert any('job_id' in r['meta']['source'] for r in rows[:public])
        assert len([r for r in rows if 'paper_id' in r['meta']['source']])==1
    finally:wb.shutdown()


@pytest.mark.parametrize('network,abstract,status',[('empty',True,'EMPTY'),('error',True,'UNAVAILABLE'),('OK',False,'metadata_only')])
def test_absent_abstract_or_public_failure_is_explicit(tmp_path,network,abstract,status):
    wb,draft,_,calls=configured(tmp_path,abstract=abstract,network=network)
    try:
        rm=retriever(wb,draft);rows=rm('ALPHA')
        assert status in {r['status'] for r in rm.events}
        if status=='metadata_only':
            assert len(rows)==1
            assert 'not read' in rows[0]['snippets'][0]
            assert 'text' not in rows[0]['meta']['source']
            assert '17 MPa' not in rows[0]['snippets'][0]
            source=rows[0]['meta']['source']
            assert set(source['locator'])=={'archive_id'}
            archived=wb.assistance_call('literature.read',{'paper_id':source['paper_id'],'locator':source['locator']})
            assert archived['status']=='metadata_only' and archived['segments']==[]
        else:assert rows==[]
    finally:wb.shutdown()


def test_budget_timeout_cancellation_and_cached_permission_and_archive_integrity(tmp_path):
    wb,draft,_,calls=configured(tmp_path)
    try:
        with pytest.raises(RuntimeError,match='tool call budget'):
            retriever(wb,draft,tools=0)('ALPHA')
        with pytest.raises(RuntimeError,match='remaining time'):
            retriever(wb,draft,seconds=1)('ALPHA')
        token=CancellationToken();token.request()
        with cancellation_scope(token),pytest.raises(ExecutionCancelled):retriever(wb,draft)('ALPHA')
        assert calls==[]
        rm=retriever(wb,draft);rows=rm('ALPHA');count=len(calls)
        assert rm('ALPHA')==rows and len(calls)==count
        rm.context['transmission_scope']['allow_public_search']=False
        with pytest.raises(PermissionError):rm('ALPHA')
        rm.context['transmission_scope']['allow_public_search']=True
        source=rows[0]['meta']['source'];archive=wb.assistance().literature.root/(source['locator']['archive_id']+'.json')
        damaged=json.loads(archive.read_text(encoding='utf-8'));damaged['segments'][0]['text']='fabricated text'
        archive.write_text(json.dumps(damaged),encoding='utf-8')
        with pytest.raises(ValueError,match='archive changed'):rm('ALPHA')
        assert len(calls)==count
    finally:wb.shutdown()


@pytest.mark.parametrize('stop',['deadline','cancel','read_budget'])
def test_stop_after_search_does_not_read_or_return_unapproved_public_evidence(tmp_path,stop):
    wb,draft,_,calls=configured(tmp_path)
    try:
        rm=retriever(wb,draft,tools=1 if stop=='read_budget' else 100)
        fetch=wb.assistance().literature.fetch
        token=CancellationToken()
        def controlled(url,**kwargs):
            returned=fetch(url,**kwargs)
            if stop=='deadline':rm.budget.deadline=time.monotonic()-1
            elif stop=='cancel':token.request()
            return returned
        wb.assistance().literature.fetch=controlled
        with cancellation_scope(token),pytest.raises((RuntimeError,ExecutionCancelled)):
            rm('ALPHA')
        assert len(calls)==1 and not rm.journal
        assert not list(wb.assistance().literature.root.glob('*.source'))
        assert not list(wb.assistance().literature.root.glob('?'*64+'.json'))
    finally:wb.shutdown()


def test_public_k_caps_returned_papers_even_when_transport_returns_more(tmp_path):
    wb,draft,_,calls=configured(tmp_path)
    try:
        fetch=wb.assistance().literature.fetch
        def many(url,**kwargs):
            raw,mime,returned_url=fetch(url,**kwargs)
            body=json.loads(raw);item=body['message']['items'][0]
            body['message']['items']=[{**item,'DOI':'10.5555/paper'+str(i)} for i in range(8)]
            return json.dumps(body).encode(),mime,returned_url
        wb.assistance().literature.fetch=many
        rows=retriever(wb,draft)('ALPHA')
        assert len(rows)==4 and len(calls)==1
        assert all('rows=4' in url for url in calls)
    finally:wb.shutdown()


@pytest.mark.parametrize('network',['empty','error'])
def test_public_only_without_read_evidence_stops_instead_of_writing_an_article(tmp_path,scripted,network):
    wb,draft,_,calls=configured(tmp_path,network=network)
    try:
        doc=wb.document_open(kind='expert',draft=draft)
        doc,result=finished(wb,doc,command(wb,doc,'expert.ask'))
        assert result['status']=='STOPPED' and result['answer'] is None
        assert 'no matching evidence' in result['reason']
        assert result['costorm']['report'] is None and calls
    finally:wb.shutdown()


def test_actual_runner_partial_retry_replays_public_retrieval_without_duplicate_inference(tmp_path,scripted):
    wb,draft,_,calls=configured(tmp_path)
    try:
        draft['budget']['model_calls']=5
        doc=wb.document_open(kind='expert',draft=draft)
        doc,result=finished(wb,doc,command(wb,doc,'expert.ask'))
        assert result['status']=='STOPPED'
        assert result['costorm']['retry']['retrieval_journal']
        first_prompts=list(scripted);network_count=len(calls)
        changed=deepcopy(doc['draft']);changed['budget']['model_calls']=100
        doc=command(wb,doc,'expert.update',{'draft':changed})['document']
        doc,result=finished(wb,doc,command(wb,doc,'expert.retry'))
        assert result['status']=='ANSWERED',result
        assert result['costorm']['usage']['replayed_completions']>=len(first_prompts)
        assert len(calls)==network_count
        assert len(scripted)==len(set(scripted))
    finally:wb.shutdown()


@pytest.mark.parametrize('boundary',['query_budget','read_budget','cancel','deadline'])
def test_partial_public_operations_retry_keeps_completed_search_and_read_exact(tmp_path,boundary):
    wb,draft,_,calls=configured(tmp_path)
    try:
        first=retriever(wb,draft,tools=2 if boundary=='query_budget' else 3 if boundary=='read_budget' else 100)
        original=wb.assistance().literature.fetch;token=CancellationToken()
        def transport(url,**kwargs):
            raw,mime,address=original(url,**kwargs)
            value=json.loads(raw)
            if 'second' in url:
                value['message']['items'][0]['DOI']='10.5555/second'
                if boundary=='cancel':token.request()
                elif boundary=='deadline':first.budget.deadline=time.monotonic()-1
            return json.dumps(value).encode(),mime,address
        wb.assistance().literature.fetch=transport
        with cancellation_scope(token),pytest.raises(RuntimeError):first(['first','second'])
        assert len(first.operations)==(2 if boundary=='query_budget' else 3)
        assert not first.journal
        old_count=len(calls)
        # Simulate changed mutable metadata and a newer remote answer. Completed
        # reads/searches must still use their original exact source, not these.
        for paper in wb.assistance().literature._papers.values():paper['abstract']='NEWER 999 MPa, not the original abstract'
        def newer(url,**kwargs):
            assert 'first' not in url, 'Completed first query must not be repeated'
            return original(url,**kwargs)
        wb.assistance().literature.fetch=newer
        second=retriever(wb,draft)
        second.operations=deepcopy(first.operations)
        rows=second(['first','second'])
        assert len(calls)==old_count+(1 if boundary=='query_budget' else 0)
        assert rows and all('NEWER' not in row['snippets'][0] for row in rows)
        assert rows[0]['meta']['source']['text']=='ALPHA stress is 17 MPa. Measured area matters.'
        assert any(event['replayed'] for event in second.events)
    finally:wb.shutdown()


@pytest.mark.parametrize('failure',['empty','error'])
def test_explicit_retry_retries_failed_search_only(tmp_path,scripted,failure):
    wb,draft,_,calls=configured(tmp_path)
    try:
        original=wb.assistance().literature.fetch
        broken=True
        def transport(url,**kwargs):
            if broken:
                calls.append(url)
                if failure=='error':raise TimeoutError('Controlled transient search failure')
                return json.dumps({'message':{'items':[]}}).encode(),'application/json',url
            return original(url,**kwargs)
        wb.assistance().literature.fetch=transport
        doc=wb.document_open(kind='expert',draft=draft)
        doc,result=finished(wb,doc,command(wb,doc,'expert.ask'))
        assert result['status']=='STOPPED'
        assert not result['costorm']['retry']['retrieval_journal']
        assert not result['costorm']['retry']['retrieval_operations']
        prior_calls=len(calls);broken=False
        doc,result=finished(wb,doc,command(wb,doc,'expert.retry'))
        assert result['status']=='ANSWERED',result
        assert len(calls)==prior_calls+1
        assert len(scripted)==len(set(scripted))
    finally:wb.shutdown()


def test_public_source_failure_retains_valid_query_completion_for_retry(tmp_path,scripted,monkeypatch):
    wb,draft,_,calls=configured(tmp_path)
    try:
        original=costorm._public_source;broken=True
        def source(*args):
            if broken:raise ValueError('Controlled source integrity failure')
            return original(*args)
        monkeypatch.setattr(costorm,'_public_source',source)
        doc=wb.document_open(kind='expert',draft=draft)
        doc,result=finished(wb,doc,command(wb,doc,'expert.ask'))
        assert result['status']=='STOPPED'
        assert result['costorm']['retry']['invalid_completion_key'] is None
        assert result['costorm']['retry']['retrieval_operations']
        broken=False;prior_calls=len(calls)
        doc,result=finished(wb,doc,command(wb,doc,'expert.retry'))
        assert result['status']=='ANSWERED',result
        assert len(calls)==prior_calls
        assert len(scripted)==len(set(scripted))
    finally:wb.shutdown()
