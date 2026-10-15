"""Actual pinned KB/step with explicit controlled generation and fault points."""
from copy import deepcopy
from types import SimpleNamespace
import pytest
from test_costorm_protocol import scripted
from test_research_team_owner import seeded
from caelab.storage import canonical_hash
from caelab.discussion_research_team import checkpoint,read_checkpoint,resolve_asset
from caelab.assist.experts import _Budget
from caelab.assist.research_team import (bind_allocation,plan_action,service_slice,_MapContext,
    BoundDiscourseManager)
from caelab.assist.research_team_map import (DeferredKnowledgeBase,register_pending,
    apply_pending_map,rebuild_shared_history,pack_turn)
from caelab.assist._vendor.costorm.dataclass import ConversationTurn,KnowledgeBase
from caelab.assist._vendor.costorm.interface import Information


def test_cancel_before_map_and_lost_commit_return_do_not_change_raw_or_repeat(tmp_path,scripted):
    from caelab.execution_control import CancellationToken,cancellation_scope,ExecutionCancelled
    wb,owner,document,record,bound=seeded(tmp_path)
    try:
        binding,root,plan=map_context(wb,document,record,bound)
        turn,projection=seed_turn(binding);original=pack_turn(turn)
        pending=register_pending(binding,projection=projection,turn_copy=turn,
            flags={'allow_create_new_node':True,'insert_under_root':False})
        token=CancellationToken();token.request()
        with cancellation_scope(token),pytest.raises(ExecutionCancelled):
            apply_pending_map(pending['id'],binding=binding,budget_slice=service_slice(root,plan,'MAP_SERVICE','r0'))
        assert binding.read_checkpoint()['map_pending'][pending['id']]['status']=='WAITING_TIME' and token.observed
        assert binding.approved_snapshot() is None and not scripted and root.used_models==0
        assert pack_turn(turn)==original
        # A new actual retry attempt/owner binding owns the resumed transaction.
        from caelab.discussion_research_team import start_record,_OwnerBinding
        from caelab.storage import canonical_hash
        retry=start_record(owner,document,'Cretry',action='retry')
        retry['active_job_id']='Jretry';spec=retry['protocol_request']
        document['discussion']['research_team']['actions'][spec['action_id']]['job_id']='Jretry'
        fresh=_OwnerBinding(owner,document['id'],owner.session_id,retry['id'],'Jretry','retry-arguments')
        resumed,budget,nextplan=map_context(wb,document,retry,fresh,8)
        actual=resumed.checkpoint
        def lost(event,payload):
            result=actual(event,payload)
            if event.startswith('map-commit-'):raise ConnectionError('Commit succeeded; local return was lost')
            return result
        resumed.checkpoint=lost
        result=apply_pending_map(pending['id'],binding=resumed,budget_slice=service_slice(budget,nextplan,'MAP_SERVICE','r0'))
        assert result['status']=='APPLIED' and result['recovered_after_response_loss']
        before=len(scripted);snapshot=deepcopy(resumed.approved_snapshot())
        assert apply_pending_map(pending['id'],binding=resumed,budget_slice=None)['status']=='APPLIED'
        assert len(scripted)==before and resumed.approved_snapshot()==snapshot and pack_turn(turn)==original
    finally:assert wb.shutdown()['joined']


def test_cleanup_unconfirmed_role_stops_all_services_and_retry_admission(tmp_path,monkeypatch):
    from caelab.execution_control import ExecutionCleanupFailed
    from caelab.research_team_contract import TrustedAction
    from caelab.assist import research_team as module
    wb,owner,document,record,bound=seeded(tmp_path)
    try:
        context,root,_=map_context(wb,document,record,bound,8)
        simple=context.trusted
        trusted=TrustedAction(document['id'],owner.session_id,context.phase_id,context.action_id,
            context.attempt_id,'Jcontrolled',{},simple.read_checkpoint,simple.checkpoint,lambda:{},
            lambda *a,**k:SimpleNamespace(generation_ledger=SimpleNamespace(context={}),role_session_id='Econtrolled'),
            None,None,None)
        trusted.resolve_payload=simple.resolve_payload;trusted.current_scope_probe=simple.current_scope_probe
        runtime=wb.assistance().experts;started=[]
        def unknown(*args,**kwargs):started.append(args[0]);raise ExecutionCleanupFailed('Controlled unconfirmed owned host')
        monkeypatch.setattr(runtime,'_run_approved_role',unknown)
        monkeypatch.setattr(module,'service_slice',lambda *a,**k:pytest.fail('No service after unconfirmed cleanup'))
        with pytest.raises(ExecutionCleanupFailed):
            module.run_team_action(runtime,runtime.describe('r0'),'public question',
                {**record['draft']['context'],'costorm':{'action':'start'}},{},None,'local',root,trusted)
        assert started==['r0']
        state=trusted.read_checkpoint();task=next(row for row in state['tasks'].values() if row['status']=='OUTCOME_UNCONFIRMED')
        assert task['continuation']['cleanup_unconfirmed'] is True
        retry=plan_action(state['phases'][context.phase_id],[task],limits={'action_id':'Dretry',
            'model_calls':8,'tool_calls':8,'kind':'retry'},pending=[])
        assert retry['tickets']==[] and not state['map_checkpoints']
    finally:assert wb.shutdown()['joined']


def test_actual_prompt_parser_rejects_only_bad_completion_and_replays_valid_prefix(tmp_path,monkeypatch):
    from caelab.assist import openscience_host
    from caelab.discussion_research_team import start_record,_OwnerBinding
    wb,owner,document,record,bound=seeded(tmp_path)
    try:
        calls=[];bad=True
        def host(prompt,tools,budget,model,**options):
            nonlocal bad
            assert tools=={} and options['max_steps']==1;calls.append(prompt)
            if 'Output field: Decision:' in prompt:return 'No reasonable choice'
            assert 'Output field: Choice:' in prompt
            if bad:
                bad=False;return 'CONTROLLED_MALFORMED missing the required second field'
            return "Reasoning: Let's think step by step in order to place this retained source.\nChoice:\ninsert"
        monkeypatch.setattr(openscience_host,'run_openscience',host)
        binding,root,plan=map_context(wb,document,record,bound,8)
        turn,projection=seed_turn(binding)
        pending=register_pending(binding,projection=projection,turn_copy=turn,
            flags={'allow_create_new_node':True,'insert_under_root':False})
        failed=apply_pending_map(pending['id'],binding=binding,budget_slice=service_slice(root,plan,'MAP_SERVICE','r0'))
        assert failed['status']=='FAILED' and binding.approved_snapshot() is None
        state=binding.read_checkpoint();item=state['map_pending'][pending['id']]
        journal=binding.resolve_payload(item['journal_ref'])
        assert item['invalid_completion_key'] and len(journal)==1 and journal[0]['text']=='No reasonable choice'
        original_bad=[binding.resolve_payload(ref) for ref in state['assets'].values()]
        assert any(isinstance(value,list) and any('CONTROLLED_MALFORMED' in row.get('text','') for row in value if isinstance(row,dict))
                   for value in original_bad)
        retry=start_record(owner,document,'CparserRetry',action='retry');retry['active_job_id']='JparserRetry'
        spec=retry['protocol_request'];document['discussion']['research_team']['actions'][spec['action_id']]['job_id']='JparserRetry'
        fresh=_OwnerBinding(owner,document['id'],owner.session_id,retry['id'],'JparserRetry','parser-retry')
        resumed,budget,nextplan=map_context(wb,document,retry,fresh,8)
        result=apply_pending_map(pending['id'],binding=resumed,budget_slice=service_slice(budget,nextplan,'MAP_SERVICE','r0'))
        assert result['status']=='APPLIED' and calls.count(calls[0])==1
        assert resumed.approved_snapshot()
    finally:assert wb.shutdown()['joined']


def map_context(wb,document,record,bound,limit=4):
    spec=record['protocol_request'];owner=bound.owner
    def save(event,payload):
        path=owner._folder(bound.owner_id)/'research-team'/record['id']/'action.json'
        from caelab.storage import load_json
        revision=load_json(path)['revision'] if path.exists() else 0
        return checkpoint(bound,expected_revision=revision,event_id=event,payload=payload)
    def scope():
        state=read_checkpoint(bound)
        return {'owner_id':bound.owner_id,'owner_session_id':owner.session_id,
            'phase_id':spec['phase_id'],'context':record['draft']['context'],
            'assignments':{r['expert_id']:r for r in record['draft']['context']['research_team']['assignments']},
            'ledger_state':state,'resolve_payload':lambda ref:resolve_asset(bound,ref)}
    trusted=SimpleNamespace(owner_id=bound.owner_id,phase_id=spec['phase_id'],action_id=spec['action_id'],attempt_id=spec['attempt_id'],
        read_checkpoint=lambda:read_checkpoint(bound),checkpoint=save,resolve_payload=lambda ref:resolve_asset(bound,ref),
        current_scope_probe=scope)
    root=_Budget(wb.assistance().experts.runtime,{'model_calls':limit,'tool_calls':8,'seconds':120})
    plan=plan_action({'turn_limit':8},[],limits={'action_id':spec['action_id'],'model_calls':limit,'tool_calls':8},pending=[])
    bind_allocation(root,plan,checkpoint=save,control_status=lambda:{})
    return _MapContext(wb.assistance().experts,record['draft']['context'],'local',trusted,root,'Public observations'),root,plan


def seed_turn(binding):
    state=binding.read_checkpoint()
    state['dependencies']['Dpublic']={'id':'Dpublic','kind':'authored','exact_ref':{'kind':'public_observation'},
        'selector':None,'content_digest':canonical_hash('controlled public observation'),
        'parent_ids':[],'introduced_by':'prompt'}
    binding.checkpoint('authored',{'state':state})
    infos={i:Information('authored:'+str(i),'CONTROLLED authored observation',['public measurement '+str(i)],
        'Public authored observation '+str(i),meta={'question':'distinct question '+str(i),'query':'Not applicable',
            'source':{'kind':'authored','observation':i}}) for i in (1,2)}
    turn=ConversationTurn('r0','CONTROLLED observation [1] and [2]','Potential Answer',cited_info=infos)
    projection={'id':'Spublic','response_id':'Rpublic','event_id':'Epublic','dependency_ids':['Dpublic']}
    turn._team_event=projection
    return turn,projection


def test_actual_step_deferred_proxy_raw_turn_and_pending_idempotence(tmp_path,scripted):
    from caelab.assist.costorm import _restore,_new_state
    wb,owner,document,record,bound=seeded(tmp_path)
    try:
        binding,root,plan=map_context(wb,document,record,bound)
        turn,projection=seed_turn(binding);original=pack_turn(turn)
        runner=_restore(_new_state('Public observations'),lambda *a,**k:pytest.fail('Unexpected model'),lambda *a,**k:[])
        proxy=DeferredKnowledgeBase(None,binding=binding);runner.knowledge_base=proxy
        runner.conversation_history=[ConversationTurn('Guest','public question','Original Question')]
        class Agent:
            def generate_utterance(self,**kwargs):return turn
        runner.discourse_manager=BoundDiscourseManager(Agent())
        runner.step()
        assert len(runner.conversation_history)==2 and root.used_models==0
        pending=list(binding.read_checkpoint()['map_pending'].values());assert len(pending)==1
        again=register_pending(binding,projection=projection,turn_copy=turn,
            flags={'allow_create_new_node':True,'insert_under_root':False})
        assert again['id']==pending[0]['id'] and pack_turn(turn)==original
        rebuilt=rebuild_shared_history(binding);assert pack_turn(rebuilt[0])==original
        with pytest.raises(PermissionError):proxy.to_report()
        with pytest.raises(AttributeError):proxy.insert_information('root',None)
        assert not scripted
    finally:assert wb.shutdown()['joined']


def test_actual_kb_partial_failure_discards_temporary_replays_success_prefix(tmp_path,scripted,monkeypatch):
    wb,owner,document,record,bound=seeded(tmp_path)
    try:
        binding,root,plan=map_context(wb,document,record,bound,1)
        turn,projection=seed_turn(binding);original=pack_turn(turn)
        pending=register_pending(binding,projection=projection,turn_copy=turn,
            flags={'allow_create_new_node':True,'insert_under_root':False})
        first=apply_pending_map(pending['id'],binding=binding,budget_slice=service_slice(root,plan,'MAP_SERVICE','r0'))
        assert first['status']=='WAITING_BUDGET' and binding.approved_snapshot() is None
        assert root.used_models==1 and len(scripted)==1
        assert pack_turn(turn)==original
        state=binding.read_checkpoint();prefix=deepcopy(binding.resolve_payload(state['map_pending'][pending['id']]['journal_ref']))
        assert len(prefix)==1
        from caelab.discussion_research_team import start_record,_OwnerBinding
        record.update(status='FAILED',active_job_id=None)
        retry_record=start_record(owner,document,'CexplicitRetry',action='retry')
        retry_record['active_job_id']='Jretry'
        document['discussion']['research_team']['actions'][binding.action_id]['job_id']='Jretry'
        retry_bound=_OwnerBinding(owner,document['id'],owner.session_id,retry_record['id'],'Jretry','retry-arguments')
        binding,retry_root,retry_plan=map_context(wb,document,retry_record,retry_bound,4)
        second=apply_pending_map(pending['id'],binding=binding,budget_slice=service_slice(retry_root,retry_plan,'MAP_SERVICE','r0'))
        assert second['status']=='APPLIED' and binding.approved_snapshot()['info_uuid_to_info_dict']
        assert pack_turn(turn)==original and len(binding.approved_snapshot()['info_uuid_to_info_dict'])==2
        assert scripted.count(scripted[0])==1  # The successful original completion was replayed.
        calls=len(scripted)
        again=apply_pending_map(pending['id'],binding=binding,budget_slice=None)
        assert again['status']=='APPLIED' and len(scripted)==calls
    finally:assert wb.shutdown()['joined']


@pytest.mark.parametrize('failure',['after_insert','revoked'])
def test_failed_or_revoked_map_preserves_raw_and_active_snapshot(tmp_path,scripted,monkeypatch,failure):
    wb,owner,document,record,bound=seeded(tmp_path)
    try:
        binding,root,plan=map_context(wb,document,record,bound)
        turn,projection=seed_turn(binding);before=pack_turn(turn)
        pending=register_pending(binding,projection=projection,turn_copy=turn,
            flags={'allow_create_new_node':True,'insert_under_root':False})
        if failure=='after_insert':
            original=KnowledgeBase.insert_information
            def insert(self,*args,**kwargs):
                original(self,*args,**kwargs)
                raise RuntimeError('CONTROLLED failure after real temporary insert')
            monkeypatch.setattr(KnowledgeBase,'insert_information',insert)
        else:
            monkeypatch.setattr(binding,'verify_dependencies',lambda ids:(_ for _ in ()).throw(PermissionError('CONTROLLED revoked')))
        result=apply_pending_map(pending['id'],binding=binding,budget_slice=service_slice(root,plan,'MAP_SERVICE','r0'))
        assert result['status']==('BLOCKED_SCOPE' if failure=='revoked' else 'FAILED')
        assert binding.approved_snapshot() is None and pack_turn(turn)==before
        assert binding.read_checkpoint()['map_pending'][pending['id']]['status']==result['status']
    finally:assert wb.shutdown()['joined']
