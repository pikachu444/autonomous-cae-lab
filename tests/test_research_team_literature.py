"""Controlled fetch adapter only; actual Literature archive/journal is exercised."""
from copy import deepcopy
import json
import pytest
from test_research_team_evidence import make_env,make_binding
from caelab.assist.research_team_literature import ActionLiteratureAccess
from caelab.assist.research_evidence import selected_knowledge_context
from caelab.execution_control import ExecutionCancelled


def access(env,binding,*,state=None):
    obj=ActionLiteratureAccess(env.runtime,action_id='action',workspace_id='local',context=env.state['context'],
        budget=binding.budget_slice,checkpoint=env.checkpoint,state=state,current_scope_probe=lambda:env.state)
    binding.public_access=obj
    return obj


def fetcher(calls,*,abstract='Controlled public abstract',fail=False):
    def fetch(url):
        calls.append(url)
        if fail:raise OSError('Controlled unavailable')
        return json.dumps({'message':{'items':[{'DOI':'10.0000/control','title':['Controlled paper'],
            'abstract':abstract,'type':'journal-article','URL':'https://example.org/paper'}]}}).encode(),'application/json',url
    return fetch


def test_action_search_cache_is_shared_across_roles_retry_and_exact_read_level(tmp_path):
    env=make_env(tmp_path);one=make_binding(env);obj=access(env,one);calls=[]
    env.runtime.literature.fetch=fetcher(calls)
    first=obj.search({'query':'mesh convergence'},caller=one,input_dependencies=[])
    paper=first['payload']['papers'][0]['paper_id']
    read=obj.read({'paper_id':paper,'locator':{'kind':'abstract'}},caller=one,input_dependencies=[])
    assert read['read_receipts'][0]['read_level']=='ABSTRACT'
    assert read['read_receipts'][0]['payload_ref']
    two=make_binding(env,actor='material',state=one.generation_ledger.state)
    resumed=access(env,two,state=obj.state)
    assert resumed.search({'query':'mesh convergence'},caller=two,input_dependencies=[])['payload']==first['payload']
    cached=resumed.read({'paper_id':paper,'locator':{'kind':'abstract'}},caller=two,input_dependencies=[])
    assert cached['payload']==read['payload'] and len(calls)==1
    assert resumed.state['attempt_count']==1
    # Cached data still obeys the current operator gate.
    env.runtime.runtime.transmission['allow_public_search']=False
    with pytest.raises(PermissionError):resumed.search({'query':'mesh convergence'},caller=two,input_dependencies=[])
    assert len(calls)==1


@pytest.mark.parametrize('failure',['unavailable','cancelled'])
def test_failed_cancelled_attempts_count_and_explicit_retry_does_not_reset(tmp_path,failure):
    env=make_env(tmp_path);binding=make_binding(env);obj=access(env,binding);calls=[]
    if failure=='cancelled':
        def search(**kw):calls.append(kw);raise ExecutionCancelled('controlled')
        env.runtime.literature.search=search
    else:env.runtime.literature.fetch=fetcher(calls,fail=True)
    for _ in range(2):
        if failure=='cancelled':
            with pytest.raises(ExecutionCancelled):obj.search({'query':'same'},caller=binding,input_dependencies=[])
        else:assert obj.search({'query':'same'},caller=binding,input_dependencies=[])['status']=='UNAVAILABLE'
    retry=access(env,binding,state=obj.state)
    with pytest.raises(PermissionError):retry.search({'query':'new'},caller=binding,input_dependencies=[])
    assert len(calls)==2 and retry.state['attempt_count']==2


@pytest.mark.parametrize('abstract',['Controlled abstract',None])
def test_selected_archive_and_metadata_only_reopen_without_new_fetch(tmp_path,abstract):
    env=make_env(tmp_path);binding=make_binding(env);obj=access(env,binding);calls=[]
    env.runtime.literature.fetch=fetcher(calls,abstract=abstract)
    search=obj.search({'query':'one'},caller=binding,input_dependencies=[])
    paper=search['payload']['papers'][0]['paper_id']
    result=obj.read({'paper_id':paper,'locator':{'kind':'abstract'}},caller=binding,input_dependencies=[])
    again=obj.read({'paper_id':paper,'locator':{'kind':'abstract'}},caller=binding,input_dependencies=[])
    assert result['payload']==again['payload'] and len(calls)==1
    ref=result['read_receipts'][0]['source_ref']
    binding.permitted_source_refs=[ref]
    other=access(env,binding)
    env.runtime.literature.fetch=lambda *a:pytest.fail('Selected archive cannot refetch')
    assert other.read({'paper_id':paper},caller=binding,input_dependencies=[])['payload']==result['payload']


def test_private_uncited_auto_snippet_prevents_public_query_before_fetch(tmp_path):
    env=make_env(tmp_path,public=False);binding=make_binding(env);obj=access(env,binding)
    selected_knowledge_context(binding);calls=[];env.runtime.literature.fetch=fetcher(calls)
    with pytest.raises(PermissionError):obj.search({'query':'apparently public'},caller=binding,input_dependencies=[])
    assert calls==[] and obj.state['attempt_count']==0


def test_success_search_failed_read_resumes_only_read_and_uses_original_paper(tmp_path,monkeypatch):
    env=make_env(tmp_path);binding=make_binding(env);obj=access(env,binding);calls=[]
    env.runtime.literature.fetch=fetcher(calls)
    found=obj.search({'query':'one'},caller=binding,input_dependencies=[]);paper=found['payload']['papers'][0]['paper_id']
    original=type(env.runtime.literature).read;seen=[]
    def flaky(self,paper_id,locator=None):
        if not (locator or {}).get('archive_id'):
            seen.append(deepcopy(self._papers[paper_id]))
            if len(seen)==1:raise OSError('controlled read failure')
        return original(self,paper_id,locator)
    monkeypatch.setattr(type(env.runtime.literature),'read',flaky)
    with pytest.raises(OSError):obj.read({'paper_id':paper,'locator':{'kind':'abstract'}},caller=binding,input_dependencies=[])
    env.runtime.literature._papers[paper]['title']='MUTABLE LATEST REPLACEMENT'
    resumed=access(env,binding,state=obj.state)
    read=resumed.read({'paper_id':paper,'locator':{'kind':'abstract'}},caller=binding,input_dependencies=[])
    assert read['payload']['paper']['title']=='Controlled paper' and len(calls)==1
    assert all(row['title']=='Controlled paper' for row in seen)


def test_result_only_and_local_only_retrieval_do_not_require_public_search(tmp_path):
    env=make_env(tmp_path);binding=make_binding(env);obj=access(env,binding)
    env.runtime.runtime.transmission['allow_public_search']=False
    rows=obj.retrieve(['mesh'],caller=binding,input_dependencies=[])
    assert rows and all(row['meta']['source'].get('document_id') for row in rows)
    assert obj.state['attempt_count']==0


def test_actual_selected_retriever_and_role_tools_use_one_action(tmp_path):
    from caelab.assist.costorm import SelectedRetriever
    env=make_env(tmp_path);binding=make_binding(env);obj=access(env,binding);calls=[]
    env.runtime.literature.fetch=fetcher(calls)
    retriever=SelectedRetriever(env.runtime,env.state['context'],'local',['engineering'],binding.budget_slice,
        lambda:None,public_access=obj,public_caller=binding)
    rows=retriever('mesh convergence')
    assert len(rows)>=2 and len(calls)==1
    assert any(row['meta']['source'].get('document_id') for row in rows)
    assert any(row['meta']['source'].get('paper_id') for row in rows)
    permit=binding.prepare_tool('literature.search',{'query':'mesh convergence'},debit=True)
    binding.finish_tool(permit,permit['invoke']())
    assert len(calls)==1 and obj.state['attempt_count']==1


def test_empty_sources_never_invoke_store_search_or_rebuild(tmp_path,monkeypatch):
    env=make_env(tmp_path);env.state['assignments']['mesh']['source_refs']=[]
    binding=make_binding(env);obj=access(env,binding)
    env.runtime.runtime.transmission['allow_public_search']=False
    monkeypatch.setattr(env.store,'search',lambda *a,**kw:pytest.fail('Empty selection must not search store'))
    monkeypatch.setattr(env.store,'rebuild',lambda *a,**kw:pytest.fail('Empty selection must not build index'))
    permit=binding.prepare_tool('knowledge.search',{'query':'topic only'},debit=True)
    assert binding.finish_tool(permit,permit['invoke']())['payload']['hits']==[]
    assert obj.retrieve('topic only',caller=binding,input_dependencies=[])==[]


def test_changed_retained_archive_is_not_silently_refetched(tmp_path):
    env=make_env(tmp_path);binding=make_binding(env);obj=access(env,binding);calls=[]
    env.runtime.literature.fetch=fetcher(calls)
    found=obj.search({'query':'one'},caller=binding,input_dependencies=[])
    paper=found['payload']['papers'][0]['paper_id']
    read=obj.read({'paper_id':paper,'locator':{'kind':'abstract'}},caller=binding,input_dependencies=[])
    digest=read['read_receipts'][0]['source_ref']['locator']['archive_id']
    path=env.runtime.literature.root/(digest+'.json')
    raw=json.loads(path.read_text(encoding='utf-8'));raw['segments'][0]['text']='changed conclusion'
    path.write_text(json.dumps(raw),encoding='utf-8')
    with pytest.raises(ValueError):obj.read({'paper_id':paper,'locator':{'kind':'abstract'}},caller=binding,input_dependencies=[])
    assert len(calls)==1


def test_started_search_is_unconfirmed_and_does_not_repeat_on_reconnect(tmp_path):
    env=make_env(tmp_path);binding=make_binding(env);obj=access(env,binding);calls=[]
    env.runtime.literature.fetch=fetcher(calls)
    obj.search({'query':'one'},caller=binding,input_dependencies=[])
    state=deepcopy(obj.state);state['entries'][0]['status']='STARTED';state['entries'][0]['result']=None
    resumed=access(env,binding,state=state)
    with pytest.raises(RuntimeError,match='unconfirmed'):resumed.search({'query':'one'},caller=binding,input_dependencies=[])
    assert len(calls)==1 and resumed.state['attempt_count']==1


def test_later_query_limit_preserves_earlier_actual_rows(tmp_path):
    env=make_env(tmp_path);binding=make_binding(env);obj=access(env,binding);calls=[]
    env.runtime.literature.fetch=fetcher(calls)
    rows=obj.retrieve(['first','second','third'],caller=binding,input_dependencies=[])
    assert rows and len(calls)==2 and obj.state['attempt_count']==2
    assert rows[0]['snippets'][0].startswith('검색 일부 미완료')
    assert rows[0]['meta']['retrieval_status']=='PARTIAL'


def test_omitted_archive_resolves_action_retained_read_and_cannot_expand_to_url(tmp_path):
    env=make_env(tmp_path);binding=make_binding(env);obj=access(env,binding);calls=[]
    env.runtime.literature.fetch=fetcher(calls)
    found=obj.search({'query':'one'},caller=binding,input_dependencies=[]);paper=found['payload']['papers'][0]['paper_id']
    read=obj.read({'paper_id':paper,'locator':{'kind':'abstract'}},caller=binding,input_dependencies=[])
    env.runtime.literature.fetch=lambda *a:pytest.fail('An omitted archive must reuse the exact retained read')
    assert obj.read({'paper_id':paper},caller=binding,input_dependencies=[])['payload']==read['payload']
    with pytest.raises(ValueError):obj.read({'paper_id':paper,'locator':{'url':'https://example.org/new'}},caller=binding,input_dependencies=[])
    assert len(calls)==1


def test_direct_trusted_debit_is_not_double_charged_and_cached_internal_calls_are_bounded(tmp_path):
    env=make_env(tmp_path);binding=make_binding(env);obj=access(env,binding);calls=[]
    env.runtime.literature.fetch=fetcher(calls)
    binding.budget_slice.consume('tool')
    permit=binding.prepare_tool('literature.search',{'query':'one'},debit=True)
    binding.finish_tool(permit,permit['invoke']())
    assert binding.budget_slice.used_tools==1
    obj.search({'query':'one'},caller=binding,input_dependencies=[])
    assert binding.budget_slice.used_tools==2 and len(calls)==1


def test_completed_search_checkpoint_failure_stays_unconfirmed_not_retryable(tmp_path):
    env=make_env(tmp_path);binding=make_binding(env);obj=access(env,binding);calls=[]
    env.runtime.literature.fetch=fetcher(calls)
    original=obj.checkpoint
    def checkpoint(event,payload):
        if event.startswith('search-finish'):raise OSError('Controlled owner checkpoint failure')
        return original(event,payload)
    obj.checkpoint=checkpoint
    with pytest.raises(OSError):obj.search({'query':'one'},caller=binding,input_dependencies=[])
    assert obj.state['entries'][0]['status']=='OUTCOME_UNCONFIRMED'
    resumed=access(env,binding,state=obj.state)
    with pytest.raises(RuntimeError):resumed.search({'query':'one'},caller=binding,input_dependencies=[])
    assert len(calls)==1


def test_provider_error_detail_is_retained_locally_and_not_returned_to_model(tmp_path):
    env=make_env(tmp_path);binding=make_binding(env);obj=access(env,binding)
    env.runtime.literature.fetch=lambda *a:(_ for _ in ()).throw(OSError('PRIVATE local path'))
    result=obj.search({'query':'one'},caller=binding,input_dependencies=[])
    assert result['status']=='UNAVAILABLE' and 'PRIVATE' not in json.dumps(result)
    entry=obj.state['entries'][0]
    assert entry['raw_error_ref'] and 'PRIVATE' not in json.dumps(entry['result'])
    assert 'PRIVATE' in env.state['resolve_payload'](entry['raw_error_ref'])['detail']


@pytest.mark.parametrize('arguments',[{'query':'one','top_k':5},{'query':'one','filters':{'from_year':'not a year'}},
    {'query':'one','filters':{'from_year':True}},{'query':'one','providers':['uninstalled']}])
def test_typed_invalid_public_request_is_rejected_before_network_or_search_slot(tmp_path,arguments):
    env=make_env(tmp_path);binding=make_binding(env);obj=access(env,binding);calls=[]
    env.runtime.literature.fetch=fetcher(calls)
    with pytest.raises(ValueError):obj.search(arguments,caller=binding,input_dependencies=[])
    assert calls==[] and obj.state['attempt_count']==0


def test_search_is_bibliographic_and_uncited_discovery_rechecks_current_permission(tmp_path):
    from test_research_team_evidence import view
    env=make_env(tmp_path);binding=make_binding(env);obj=access(env,binding);calls=[]
    env.runtime.literature.fetch=fetcher(calls)
    result=obj.search({'query':'one'},caller=binding,input_dependencies=[])
    assert 'abstract' not in result['payload']['papers'][0]
    assert result['read_receipts'][0]['read_level']=='BIBLIOGRAPHIC'
    response=binding.finalize_response({'answer':'A paper exists.','sources':[]},{})
    assert view(env,binding,response)['status']=='AVAILABLE'
    env.runtime.runtime.transmission['allow_public_search']=False
    assert view(env,binding,response)['projection'] is None
    assert len(calls)==1
