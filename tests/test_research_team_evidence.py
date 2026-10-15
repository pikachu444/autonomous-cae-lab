"""Actual offline archive/BM25 provenance; no provider or network execution."""
from copy import deepcopy
import json
from types import SimpleNamespace

import pytest

from caelab.assist.experts import ExpertRuntime,RuntimeConfig,_Budget
from caelab.assist.knowledge import KnowledgeStore
from caelab.assist.literature import Literature
from caelab.assist.research_evidence import (GenerationLedger,role_context,selected_knowledge_context,
    shared_projection,check_receipt,to_costorm_information,dependency_closure)
from caelab.research_team_contract import ApprovedRoleBinding
from caelab.storage import canonical_hash


def make_env(tmp_path,*,public=True):
    source=tmp_path/'source.md';source.write_text('# Engineering reference\nThe mesh convergence criterion uses displacement and energy.\n',encoding='utf-8')
    store=KnowledgeStore(tmp_path/'knowledge',source_roots=[tmp_path])
    ingested=store.ingest(source,'engineering',{'title':'Engineering guide','document_version':'1.2',
        'applicability':'REFERENCE_ONLY','access_scope':'public' if public else ['local']})
    pin={'document_id':ingested['document_id'],'revision':1}
    tools=['knowledge.search','knowledge.source','literature.search','literature.read','experts.consult']
    definitions=[{'id':actor,'collections':['engineering'],'tools':tools} for actor in ('mesh','material')]
    policy={'allow_external_model':True,'allow_question':True,'allow_public_search':True,'collections':['engineering'],'allow_results':True}
    runtime=ExpertRuntime(store,Literature(tmp_path/'literature',fetch=lambda *a,**kw:(_ for _ in ()).throw(AssertionError('Live network forbidden'))),
        experts=definitions,runtime=RuntimeConfig(transmission=policy,max_tool_calls=64))
    context={'selected_sources':[pin],'selected_document_ids':[pin['document_id']],
        'transmission_scope':{'allow_question':True,'allow_public_search':True,'source_refs':[pin],
            'collections':['engineering'],'result_ids':[]},'research_team':{'objective':'Check mesh convergence','deliverable':'Review',
                'assignments':[{'expert_id':'material','question':'PRIVATE OTHER QUESTION'}],'carry_forward':'PRIVATE'}}
    assignments={actor:{'expert_id':actor,'question':'Inspect this engineering source','tools':tools,
        'source_refs':[pin],'result_refs':[]} for actor in ('mesh','material')}
    assets={};events=[];event_digests={};state={'owner_id':'owner','owner_session_id':'owner-session','phase_id':'phase',
        'context':context,'assignments':assignments,'paused':False,'intervened':False}
    def checkpoint(event,payload):
        digest=canonical_hash(payload)
        if event in event_digests:assert event_digests[event]==digest,'Owner CAS event reused for different content'
        event_digests[event]=digest
        events.append((event,deepcopy(payload)))
        if 'asset' in payload:
            value=payload['asset']['payload'];reference={'path':'research-team/assets/'+payload['asset']['id']+'.json','sha256':canonical_hash(value)}
            assets[reference['path']]=deepcopy(value);return {'asset_ref':reference}
        return {}
    def resolve(ref):
        value=deepcopy(assets[ref['path']]);assert canonical_hash(value)==ref['sha256'];return value
    state['resolve_payload']=resolve
    env=SimpleNamespace(runtime=runtime,store=store,pin=pin,state=state,checkpoint=checkpoint,assets=assets,events=events,source=source)
    return env


def make_binding(env,actor='mesh',*,state=None,task=None,visibility='independent'):
    assignment=env.state['assignments'][actor]
    bound=role_context(assignment,{'context':env.state['context']},runtime=env.runtime,workspace_id='local',visibility=visibility,accepted_responses=[])
    ids={'owner_id':'owner','phase_id':'phase','task_id':task or 'task-'+actor,'actor_id':actor,'attempt_id':'attempt'}
    ledger=GenerationLedger(ids,runtime=env.runtime,workspace_id='local',context=bound['context'],checkpoint=env.checkpoint,state=state)
    binding=ApprovedRoleBinding('owner','owner-session','phase','action','attempt',ids['task_id'],actor,'session-'+ids['task_id'],{},
        deepcopy(assignment),visibility,_Budget(env.runtime.runtime,{}),deepcopy(assignment['source_refs']),deepcopy(assignment['result_refs']),lambda:env.state,
        ledger,None,getattr(env,'result_access',None),None,env.checkpoint,lambda:{})
    binding.prepare_model_input({'question':assignment['question']},mode='initial',supplied_items=bound['supplied_items'])
    return binding


def view(env,binding,response,recipients=('mesh',)):
    scope={**env.state,'generation_ledger':binding.generation_ledger}
    return shared_projection(response,list(recipients),runtime=env.runtime,workspace_id='local',current_scope=scope)


def test_actual_bm25_exact_revision_metadata_and_owned_read_receipt(tmp_path):
    env=make_env(tmp_path);binding=make_binding(env)
    context,snippets=selected_knowledge_context(binding)
    assert snippets and snippets[0]['revision_metadata']['document_version']=='1.2'
    assert snippets[0]['revision_metadata']['applicability']=='REFERENCE_ONLY'
    assert 'PRIVATE' not in json.dumps(context)
    permit=binding.prepare_tool('knowledge.search',{'query':'mesh convergence'},debit=True)
    result=binding.finish_tool(permit,permit['invoke']())
    assert result['payload']['method']=='Haystack BM25L' and result['payload']['hits']
    hit=result['payload']['hits'][0]
    permit=binding.prepare_tool('knowledge.source',{k:hit[k] for k in ('document_id','revision','locator')},debit=True)
    read=binding.finish_tool(permit,env.store.source(hit['document_id'],hit['revision'],hit['locator']))
    receipt=read['read_receipts'][0]
    scope={**env.state,'generation_ledger':binding.generation_ledger}
    scope['check_receipt']=lambda r:check_receipt(r,runtime=env.runtime,workspace_id='local',current_scope=scope,recipients=['mesh'])
    scope.update(read_question='Inspect actual convergence criterion',read_query='mesh convergence')
    information=to_costorm_information(receipt,current_scope=scope)
    assert information.meta['question']=='Inspect actual convergence criterion'
    assert information.meta['query']=='mesh convergence'
    assert information.title and information.snippets and receipt['payload_ref']
    response=binding.finalize_response({'answer':'Mesh is discussed.','sources':[]},{'status':'VALID'})
    assert view(env,binding,response)['status']=='AVAILABLE'
    env.source.write_text('# A new revision\nDifferent conclusion',encoding='utf-8')
    env.store.ingest(env.source,'engineering',{'title':'Engineering guide','access_scope':'public'},document_id=env.pin['document_id'])
    assert view(env,binding,response)['status']=='AVAILABLE' # same exact revision remains
    env.store.revoke(env.pin['document_id'])
    assert view(env,binding,response)['projection'] is None
    with pytest.raises(PermissionError):to_costorm_information(receipt,current_scope=scope)


def test_response_reads_are_task_local_and_body_is_not_in_metadata(tmp_path):
    env=make_env(tmp_path);first=make_binding(env)
    permit=first.prepare_tool('knowledge.search',{'query':'mesh'},debit=True)
    first.finish_tool(permit,permit['invoke']())
    one=first.finalize_response({'answer':'private body','sources':[]},{})
    second=make_binding(env,state=first.generation_ledger.state,task='later')
    two=second.finalize_response({'answer':'new task','sources':[]},{})
    assert one['read_receipt_ids'] and two['read_receipt_ids']==[]
    assert 'private body' not in json.dumps(first.generation_ledger.state)


def test_tool_failure_is_actual_input_and_unknown_parent_is_blocked(tmp_path):
    env=make_env(tmp_path);binding=make_binding(env)
    permit=binding.prepare_tool('knowledge.search',{'query':'mesh'},debit=True)
    result=binding.finish_tool(permit,RuntimeError('PRIVATE PATH'))
    assert result['payload']=={'status':'TOOL_FAILED','tool':'knowledge.search','error_type':'RuntimeError'}
    response=binding.finalize_response({'answer':'No source found','sources':[]},{})
    closure=dependency_closure(binding.generation_ledger.state['dependencies'],response['dependency_ids'])
    assert any(binding.generation_ledger.state['dependencies'][key]['kind']=='tool_output' for key in closure)
    assert view(env,binding,{'dependency_ids':['unknown'],'answer':'secret'})['projection'] is None


def test_current_assignment_removal_blocks_source_before_dispatch(tmp_path):
    env=make_env(tmp_path);binding=make_binding(env)
    env.state['assignments']['mesh']['source_refs']=[]
    with pytest.raises(PermissionError):binding.prepare_tool('knowledge.source',env.pin,debit=True)


def test_same_source_repeated_after_other_inputs_keeps_checkpoint_identity(tmp_path):
    env=make_env(tmp_path);binding=make_binding(env)
    selected_knowledge_context(binding)
    permit=binding.prepare_tool('knowledge.search',{'query':'mesh'},debit=True)
    binding.finish_tool(permit,permit['invoke']())
    selected_knowledge_context(binding)
    metadata={'status':'STARTED','request_digest':'same'}
    binding.generation_ledger.record_operation('analysis','same',None,metadata)
    binding.generation_ledger.record_operation('analysis','same',{'answer':42},{**metadata,'status':'SUCCEEDED'})
    binding.current_scope_probe() # real owner provides the resolver, no payload in outputs
    binding.generation_ledger.resolve_payload=env.state['resolve_payload']
    assert binding.generation_ledger.lookup_operation('analysis','same')['payload']=={'answer':42}


def test_actual_retained_owner_result_scope_reader_receipt_and_revoke(tmp_path,monkeypatch):
    from caelab.workbench import Workbench
    from caelab import research_team_results as physical
    from caelab.assist.research_evidence import ResultAccess
    from test_research_team_results import retain_fixture
    bench=Workbench(tmp_path/'workbench',configuration={'workers':1})
    try:
        _,reference,_,readers=retain_fixture(bench,monkeypatch,{'execution_status':'SUCCEEDED','responses':{
            'force':{'kind':'series','value':[2.,3.,5.],'unit':'N','component':'Z','location':'top',
                'axes':[{'name':'time','unit':'s','values':[0.,1.,2.]}]}}})
        env=make_env(tmp_path)
        chosen=physical.make_result_selection(readers['probe'](reference),source_id='selected',
            selection_request={'metadata_only':False,'channels':[{'response':'force','frame_indices':[1]}]})
        for assignment in env.state['assignments'].values():
            assignment['tools'].extend(['results.read','calculations.status']);assignment['result_refs']=[chosen]
        for definition in env.runtime.definitions.values():definition['tools'].extend(['results.read','calculations.status'])
        env.state['context']['transmission_scope']['result_ids']=[reference['job_id']]
        readers['transmission_check']=env.runtime._transmission_check
        env.result_access=ResultAccess(readers=readers,current_scope_probe=lambda:env.state)
        binding=make_binding(env)
        assert any(row['kind']=='result' and row['introduced_by']=='prompt' for row in binding.generation_ledger.state['dependencies'].values())
        status=binding.prepare_tool('calculations.status',{'job_id':reference['job_id']},debit=True)
        returned=binding.finish_tool(status,{'state':bench.manager.status(reference['job_id'])['state'],'job_id':reference['job_id']})
        assert returned['read_receipts'][0]['source_ref']==reference
        assert returned['read_receipts'][0]['read_level']=='RESULT_METADATA'
        permit=binding.prepare_tool('results.read',{'source_id':'selected'},debit=True)
        bound=binding.finish_tool(permit,permit['invoke']())
        assert bound['payload']['channels'][0]['response']['value']==[3.]
        receipt=bound['read_receipts'][0]
        assert receipt['source_ref']==reference and receipt['status']=='VERIFIED' and receipt['payload_ref']
        assert receipt['returned_selector']['channels'][0]['frame_indices']==[1]
        response=binding.finalize_response({'answer':'Selected force is 3 N','sources':[]},{})
        scope={**env.state,'generation_ledger':binding.generation_ledger,'result_access':binding.result_access}
        assert shared_projection(response,['mesh'],runtime=env.runtime,workspace_id='local',current_scope=scope)['status']=='AVAILABLE'
        env.state['context']['transmission_scope']['result_ids']=[]
        assert shared_projection(response,['mesh'],runtime=env.runtime,workspace_id='local',current_scope=scope)['projection'] is None
    finally:assert bench.shutdown()['joined']


def test_actual_haystack_role_dispatch_source_reply_projection_and_information(tmp_path):
    from test_workbench_assist import mock_generator
    env=make_env(tmp_path);binding=make_binding(env)
    segment=env.store.source(env.pin['document_id'],1)['segments'][0]
    reference={key:segment[key] for key in ('document_id','revision','locator')}
    answer={'answer':'Controlled local generator: mesh convergence is discussed.','sources':[reference],
        'research_reply':{'kind':'observation','claims':[{'text':'The selected guide discusses mesh convergence.',
            'basis':'observed','conditions':['Reference only'],'source_refs':[reference],'missing_evidence':[]}],
            'questions':[],'revisions':[],'unknowns':['Engineering qualification remains unknown']}}
    generator=mock_generator([('knowledge_search',{'query':'mesh convergence'}),
        ('knowledge_source',reference),answer])
    env.runtime.runtime.generator=generator
    binding.budget_slice.ticket={'kind':'INITIAL_RESEARCH'}
    result=env.runtime._run_approved_role('mesh','Inspect source',binding.generation_ledger.context,
        binding.role_session_id,workspace_id='local',budget=binding.budget_slice,visited=['mesh'],binding=binding)
    assert result['status']=='ANSWERED',result
    response=result['research_response']
    assert response['validation']['status']=='VALID',response
    assert view(env,binding,response,('mesh','material'))['projection']['answer']==answer['answer']
    scope={**env.state,'generation_ledger':binding.generation_ledger}
    scope['check_receipt']=lambda receipt:check_receipt(receipt,runtime=env.runtime,workspace_id='local',current_scope=scope,recipients=['mesh','material'])
    information=[to_costorm_information(binding.generation_ledger.state['read_receipts'][identifier],current_scope=scope)
        for identifier in response['read_receipt_ids']]
    assert information and all(row.snippets for row in information)
    assert len(generator.calls)==3 and binding.budget_slice.used_models==3
    assert all(row['coverage']=='COMPLETE_SUPPLIED_INPUT' for row in binding.generation_ledger.state['manifests'].values())
    assert all(set(response['dependency_ids'])<=set(row['dependency_ids']) for row in binding.generation_ledger.state['manifests'].values())


def test_authoritative_metadata_result_read_is_not_observed_numeric_evidence():
    from caelab.assist.research_evidence import record_read
    from caelab.research_team_contract import validate_reply
    reference={'document_id':'source-document','job_id':'source-job','input_revision':'R1',
        'input_sha256':'a'*64,'result_sha256':'b'*64}
    arguments={'source_id':'selected','selection':{'metadata_only':False,'channels':[{'response':'force'}]}}
    metadata=record_read({'status':'AVAILABLE','channels':[]},tool='results.read',request=arguments,
        source_reference=reference,actual_selector={'metadata_only':True,'channels':[]},input_dependencies=['source-parent'])
    assert metadata['read_level']=='RESULT_METADATA' # Actual return, never the requested value-read flag.
    response={'research_reply':{'kind':'observation','claims':[{'text':'The force is 3 N.','basis':'observed',
        'conditions':[],'source_refs':[reference],'missing_evidence':[]}],'questions':[],'revisions':[],'unknowns':[]}}
    verdict=validate_reply(response,task={},allowed_references=[reference],read_receipts=[metadata])
    assert verdict['status']=='INVALID'
    values=record_read({'status':'AVAILABLE','channels':[{'response':{'value':[3.],'unit':'N'}}]},
        tool='results.read',request=arguments,source_reference=reference,
        actual_selector={'metadata_only':False,'channels':[{'response':'force'}]},input_dependencies=['source-parent'])
    assert values['read_level']=='RESULT_VALUES'
    assert validate_reply(response,task={},allowed_references=[reference],read_receipts=[values])['status']=='VALID'
