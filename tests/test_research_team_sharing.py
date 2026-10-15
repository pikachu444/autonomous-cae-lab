"""Whole-response access, including uncited/history/consultation parents."""
from copy import deepcopy
import json
import pytest
from test_research_team_evidence import make_env,make_binding,view
from caelab.assist.research_evidence import selected_knowledge_context,shared_projection


def test_uncited_restricted_snippet_blocks_entire_response_title_plan_and_cache(tmp_path):
    env=make_env(tmp_path,public=False);binding=make_binding(env)
    selected_knowledge_context(binding)
    response=binding.finalize_response({'answer':'A fresh uncited hypothesis','title':'SECRET TITLE',
        'proposed_actions':[{'title':'SECRET PLAN'}],'sources':[]},{})
    assert view(env,binding,response,('mesh','material'))['status']=='AVAILABLE'
    env.runtime.definitions['material']['collections']=[]
    result=view(env,binding,response,('mesh','material'))
    assert result=={'status':'BLOCKED_SCOPE','projection':None,'dependency_ids':[],'reason_code':'BLOCKED_SCOPE'}
    assert 'SECRET' not in json.dumps(result)
    env.runtime.definitions['material']['collections']=['engineering']
    env.runtime.runtime.transmission['collections']=[]
    assert view(env,binding,response)['projection'] is None


def test_history_chain_keeps_original_uncited_dependency_and_rechecks_revocation(tmp_path):
    env=make_env(tmp_path);first=make_binding(env,visibility='shared')
    selected_knowledge_context(first)
    response=first.finalize_response({'answer':'source-derived answer','sources':[]},{})
    second=make_binding(env,state=first.generation_ledger.state,task='followup',visibility='shared')
    messages=second.prepare_history([{'actor_id':'mesh','phase_id':'phase','task_id':'task-mesh','question':'prior','response':response}])
    assert messages and messages[0]['dependency_ids']
    next_response=second.finalize_response({'answer':'summary without citations','sources':[]},{})
    env.store.revoke(env.pin['document_id'])
    assert view(env,second,next_response)['projection'] is None
    assert second.prepare_history([{'actor_id':'mesh','phase_id':'phase','task_id':'followup','response':next_response}])==[]


def test_legacy_citations_do_not_create_a_verified_dependency(tmp_path):
    env=make_env(tmp_path);binding=make_binding(env)
    result=view(env,binding,{'answer':'Old private text','sources':[env.pin]})
    assert result['status']=='DEPENDENCY_UNVERIFIED' and result['projection'] is None
    with pytest.raises(ValueError):
        binding.generation_ledger.add_supplied({'kind':'response','payload':'derived','exact_ref':{}},dependencies=['invented-citation'],origin='history')


def test_consult_response_inherits_target_input_not_just_caller_question(tmp_path):
    env=make_env(tmp_path);caller=make_binding(env,visibility='shared')
    target=make_binding(env,actor='material',state=caller.generation_ledger.state,visibility='shared')
    selected_knowledge_context(target)
    target_response=target.finalize_response({'answer':'Target recommendation','sources':[]},{})
    # Owner action state is merged before returning the target response.
    caller.generation_ledger.state=deepcopy(target.generation_ledger.state)
    permit=caller.prepare_tool('experts.consult',{'expert_id':'material','question':'review'},debit=True)
    caller.finish_tool(permit,{'answer':'Target recommendation','research_response':target_response})
    derived=caller.finalize_response({'answer':'Use target recommendation','sources':[]},{})
    env.store.revoke(env.pin['document_id'])
    assert view(env,caller,derived)['projection'] is None


def test_public_clean_cannot_reuse_private_supplied_context(tmp_path):
    env=make_env(tmp_path,public=False);binding=make_binding(env)
    selected_knowledge_context(binding)
    with pytest.raises(PermissionError):binding.prepare_model_input({'question':'public looking'},mode='public_clean',supplied_items=[])
    # A new independent owner task has no private snippets/history supplied.
    clean=make_binding(env,task='clean')
    assert clean.prepare_model_input({'question':'What is mesh convergence?'},mode='public_clean',supplied_items=[])['coverage']=='COMPLETE_SUPPLIED_INPUT'


def test_local_owner_facet_needs_no_provider_role_or_transmission_and_rechecks_revoke(tmp_path,monkeypatch):
    from caelab.assist.research_evidence import local_projection
    env=make_env(tmp_path,public=False);binding=make_binding(env)
    selected_knowledge_context(binding)
    response=binding.finalize_response({'answer':'Allowed private local work','sources':[]},{})
    def local_check(row):
        if row['kind']=='knowledge':
            env.store.check_access(row['exact_ref']['document_id'],row['exact_ref']['revision'],workspace_id='local')
        return True
    monkeypatch.setattr(env.runtime,'describe',lambda *a:pytest.fail('Local reading must not require a role'))
    monkeypatch.setattr(env.runtime,'_transmission_check',lambda *a:pytest.fail('Local reading must not require external transmission'))
    kwargs={'state':binding.generation_ledger.state,'resolve_payload':env.state['resolve_payload'],'check_dependency':local_check}
    assert local_projection(response,**kwargs)['projection']['answer']=='Allowed private local work'
    env.store.revoke(env.pin['document_id'])
    assert local_projection(response,**kwargs)['status']=='BLOCKED_SCOPE'


def test_local_missing_navigation_can_read_allowed_frozen_body_but_denial_cannot(tmp_path):
    from caelab.assist.research_evidence import local_projection
    env=make_env(tmp_path);binding=make_binding(env)
    selected_knowledge_context(binding)
    response=binding.finalize_response({'answer':'Frozen body','sources':[]},{})
    kwargs={'state':binding.generation_ledger.state,'resolve_payload':env.state['resolve_payload']}
    allowed=local_projection(response,check_dependency=lambda row:{'status':'SOURCE_UNAVAILABLE'},**kwargs)
    assert allowed['status']=='AVAILABLE' and allowed['reason_code']=='SOURCE_UNAVAILABLE'
    assert local_projection(response,check_dependency=lambda row:False,**kwargs)['projection'] is None
    response['payload_digest']='0'*64
    assert local_projection(response,check_dependency=lambda row:True,**kwargs)['status']=='DEPENDENCY_UNVERIFIED'


def test_failed_consultation_records_failure_parents_without_masking_original_error(tmp_path):
    env=make_env(tmp_path);binding=make_binding(env,visibility='shared')
    permit=binding.prepare_tool('experts.consult',{'expert_id':'material','question':'Review selected source'},debit=True)
    original=RuntimeError('controlled original target failure')
    result=binding.finish_tool(permit,original)
    assert result['payload']=={'status':'TOOL_FAILED','tool':'experts.consult','error_type':'RuntimeError'}
    assert result['dependency_ids'] and result['status']=='TOOL_FAILED'
    assert any(row['kind']=='tool_output' and row['introduced_by']=='consultation'
        for row in binding.generation_ledger.state['dependencies'].values())
