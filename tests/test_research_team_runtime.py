"""Actual owner/JobManager/ExpertRuntime/upstream step with scripted host only."""
from copy import deepcopy
import json
import time
import pytest
from test_costorm_protocol import scripted
from test_research_team_owner import team_draft,definitions
from caelab.workbench import Workbench
from caelab.storage import canonical_hash


def command(wb,doc,operation,args=None):
    return wb.document_command(doc['id'],operation,args or {},session_id=doc['session_id'],expected_generation=doc['generation'])


def finish(wb,doc,response):
    job=response['job']['id'];deadline=time.monotonic()+20
    while time.monotonic()<deadline:
        state=wb.manager.status(job)
        if state['state'] in {'SUCCEEDED','FAILED','CANCELLED','PARTIAL_FAILURE'}:
            value=wb.manager.result(job)
            return wb.document_read(doc['id']),value
        time.sleep(.005)
    raise AssertionError(wb.manager.status(job))


def configured(tmp_path,limit):
    config={'experts':definitions(),'runtime':{'provider':'openscience','model':'openai-codex/test-double',
        'external_model':False,'max_model_calls':8,'max_tool_calls':8,'max_seconds':120}}
    wb=Workbench(tmp_path,configuration=config)
    source=wb.root/'public-observations.md';source.write_text('# Public\nMeasured length is 12 mm. Check calibration and loading direction.',encoding='utf-8')
    ingested=wb.assistance().knowledge.ingest(str(source),collection='public')
    draft=team_draft(limit=limit)
    reference={'document_id':ingested['document_id'],'revision':ingested['revision']}
    draft['context']['selected_sources']=[reference]
    for assignment in draft['context']['research_team']['assignments']:assignment['source_refs']=[deepcopy(reference)]
    return wb,wb.document_open(kind='expert',draft=draft),config


def role_host(monkeypatch):
    from caelab.assist import openscience_host
    map_host=openscience_host.run_openscience;calls=[]
    def host(prompt,tools,budget,model,**options):
        if 'Conversation and request JSON: ' not in prompt:return map_host(prompt,tools,budget,model,**options)
        payload=json.loads(prompt.split('Conversation and request JSON: ',1)[1])
        task=payload['context']['research_task'];calls.append({'task':deepcopy(task),'input':deepcopy(payload),
            'max_steps':options['max_steps'],'model':model,'session_actor':task['actor_id']})
        sources=[]
        if task['kind']!='QUESTION':
            source=payload['source_segments'][0]
            ref={key:source[key] for key in ('document_id','revision','locator')}
            returned=tools['knowledge_source']['call'](**ref)
            assert returned['segments']
            sources=[ref]
        reply={'kind':'question' if task['kind']=='QUESTION' else 'hypothesis',
            'claims':[] if task['kind']=='QUESTION' else [{'text':'CALIBRATION_CHECK '+task['actor_id'],
                'basis':'inferred','conditions':['same measured quantity'],'source_refs':sources,'missing_evidence':['repeat test']}],
            'questions':[{'expert_id':'r0','target_turn_id':task['target_turn_id'],
                'target_claim_id':task['target_claim_id'],'question':'Which calibration observation distinguishes this?',
                'discriminating_observation':'repeat calibration'}] if task['kind']=='QUESTION' else [],
            'revisions':[],'unknowns':[{'input':'actual repeat test','blocks_judgement':True,'next_observation':'repeat test'}]}
        return json.dumps({'answer':'CONTROLLED '+task['kind']+' '+task['actor_id'], 'sources':sources,
            'assumptions':['CONTROLLED host, not a live subscription answer'],
            'proposed_actions':[{'purpose':'Compare calibration before interpreting the measurement.'}],
            'research_reply':reply},ensure_ascii=False)
    monkeypatch.setattr(openscience_host,'run_openscience',host)
    return calls


def test_flat_result_marker_exact_task_and_nested_selector_rejection():
    from caelab.research_team_contract import match_result_citation
    reference = {'document_id': 'Mretained', 'job_id': 'Jactual', 'input_revision': 'Rone',
                 'input_sha256': 'a' * 64, 'result_sha256': 'b' * 64}
    selector = {'metadata_only': False, 'channels': [{'response': 'force', 'frame_indices': [2]}]}
    receipt = {'id': 'read-one', 'kind': 'result', 'source_ref': reference, 'returned_selector': selector}
    marker = {**reference, 'selector': deepcopy(selector), 'read_receipt_id': receipt['id']}
    assert match_result_citation(marker, [receipt]) is receipt
    assert match_result_citation(reference, [receipt]) is receipt
    second = {**deepcopy(receipt), 'id': 'read-other', 'returned_selector': {
        'metadata_only': False, 'channels': [{'response': 'force', 'frame_indices': [1]}]}}
    assert match_result_citation(reference, [receipt, second]) is None
    assert match_result_citation(marker, [receipt, second]) is receipt
    assert match_result_citation({**marker, 'selector': second['returned_selector']}, [receipt]) is None
    assert match_result_citation({'reference': {**reference, 'selector': second['returned_selector']},
                                 'selector': selector}, [receipt]) is None
    assert match_result_citation({'reference': reference, 'read_receipt_id': receipt['id']}, [receipt]) is None
    assert match_result_citation(marker, []) is None  # Other tasks' receipts are not supplied.


def test_cross_assigned_official_metadata_projects_exact_source_before_external_transmission(tmp_path,monkeypatch):
    """Real local retrieval/guard/ledger; no Ask, host, network or operator update."""
    from test_research_team_evidence import make_env,make_binding
    from caelab.assist.research_evidence import selected_knowledge_context
    from caelab.research_team_contract import projected_source_metadata
    from caelab.assist import openscience_host
    import hashlib
    env=make_env(tmp_path)
    monkeypatch.setattr(openscience_host,'run_openscience',lambda *a,**k:pytest.fail('Live/model execution is forbidden'))
    collections=['pre-freecad-fem','mesh-gmsh','post-paraview'];pins=[];metadata=[]
    for index,collection in enumerate(collections):
        path=tmp_path/('official-'+str(index)+'.md')
        path.write_text('# Official public source\nPublic retained guidance '+str(index),encoding='utf-8')
        meta={'title':'Official '+str(index),'access_scope':'public','official_document':{
            'collection':collection,'title':'Original bibliographic metadata','license':'Public test fixture'}}
        saved=env.store.ingest(path,collection,meta);pins.append({key:saved[key] for key in ('document_id','revision')})
        metadata.append(deepcopy(meta))
    definitions={};assignments={}
    pairs=[(0,2),(0,1),(1,2)]
    for index,pair in enumerate(pairs):
        actor='r'+str(index)
        definitions[actor]={'id':actor,'instructions':'Read only the assigned exact sources.',
            'collections':[collections[i] for i in pair],'tools':['knowledge.source']}
        assignments[actor]={'expert_id':actor,'question':'Review these public sources.','tools':['knowledge.source'],
            'source_refs':[pins[i] for i in pair],'result_refs':[]}
    env.runtime.definitions=definitions;env.state['assignments']=assignments
    context=env.state['context'];context['selected_sources']=deepcopy(pins)
    context['selected_document_ids']=[row['document_id'] for row in pins]
    context['transmission_scope'].update(source_refs=deepcopy(pins),collections=collections,
        allow_public_search=False,result_ids=[],allow_generated_results=False)
    env.runtime.runtime.external_model=True
    env.runtime.runtime.transmission.update(collections=collections,allow_public_search=False,allow_results=False)
    before={p.relative_to(env.store.root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
            for p in env.store.root.rglob('*') if p.is_file()}
    binding=make_binding(env,actor='r0');role_context,snippets=selected_knowledge_context(binding)
    assert role_context['selected_sources']==[pins[0],pins[2]]
    assert {row['document_id'] for row in snippets}=={pins[0]['document_id'],pins[2]['document_id']}
    assert role_context['research_team']['assignment']['source_refs']==[pins[0],pins[2]]
    raw=deepcopy(snippets)
    for item in raw:
        original=deepcopy(item['revision_metadata']['official_document'])
        for key in ('document_id','revision','locator'):original.pop(key,None)
        item['revision_metadata']['official_document']=original
    with pytest.raises(PermissionError,match='Unselected source'):
        env.runtime._transmission_check(raw,role_context)  # Exact pre-fix failure.
    payload={'question':'Review assigned sources.','context':role_context,'source_segments':snippets}
    env.runtime._transmission_check(payload,role_context)
    manifest=binding.prepare_model_input(payload,mode='initial',supplied_items=[])
    assert manifest['payload_digest']==canonical_hash(payload)
    for receipt_id,item in zip(binding.generation_ledger.read_receipt_ids,snippets):
        receipt=binding.generation_ledger.state['read_receipts'][receipt_id]
        assert env.state['resolve_payload'](receipt['payload_ref'])==item
        projected=item['revision_metadata']['official_document']
        assert {key:projected[key] for key in ('document_id','revision','locator')}=={
            key:item[key] for key in ('document_id','revision','locator')}
    forbidden=env.store.source(**pins[1])['segments'][0]
    with pytest.raises(PermissionError):env.runtime._transmission_check([forbidden],role_context)
    for invalid in ({'collection':collections[1]},
                    {'collection':collections[0],'document_id':pins[1]['document_id'],'revision':1},
                    {'collection':collections[0],'document_id':pins[0]['document_id']}):
        assert projected_source_metadata(invalid,snippets[0])==invalid
        with pytest.raises(PermissionError):env.runtime._transmission_check(invalid,role_context)
    after={p.relative_to(env.store.root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
           for p in env.store.root.rglob('*') if p.is_file()}
    assert after==before and binding.budget_slice.used_models==binding.budget_slice.used_tools==0


def test_unconfigured_roles_preserve_failed_tasks_without_answered_or_host(tmp_path,monkeypatch):
    from caelab.assist import openscience_host
    wb,doc,_=configured(tmp_path,4)
    try:
        wb.assistance().experts.runtime.model=None
        monkeypatch.setattr(openscience_host,'run_openscience',lambda *a,**k:pytest.fail('No configured model'))
        doc,result=finish(wb,doc,command(wb,doc,'expert.ask'))
        assert result['status']=='STOPPED' and result['costorm']['usage']['model_calls']==0
        assert result['costorm']['usage']['observed_host_invocations']==0
        assert any(row['status']=='BLOCKED_SCOPE' for row in doc['discussion']['research_team']['tasks'].values())
        assert doc['discussion']['research_team']['map_checkpoints']=={}
    finally:assert wb.shutdown()['joined']


def test_manual_rag_new_revision_exact_chunks_korean_query_payload_and_permissions(tmp_path,monkeypatch):
    """Real archived manuals/BM25/receipts; no host, public search or live store."""
    import hashlib
    import socket
    from pathlib import Path
    from test_research_team_evidence import make_env,make_binding
    from caelab.assist import knowledge as knowledge_module
    from caelab.assist.research_evidence import selected_knowledge_context,check_receipt
    from caelab.research_team_contract import projected_source_metadata
    from examples.research_knowledge_public import PACK
    monkeypatch.setattr(socket.socket,'connect',lambda *a,**k:pytest.fail('Network forbidden'))
    env=make_env(tmp_path);env.store.source_roots.append(PACK.parent.resolve())
    entries=[row for row in json.loads(PACK.read_text(encoding='utf-8'))['documents'] if row['availability']=='BUNDLED']
    old_pins=[];new_pins=[];old_files={}
    for entry in entries:
        path=PACK.parent/entry['file'];metadata={'title':entry['title'],'access_scope':'public','official_document':entry}
        with monkeypatch.context() as patch:
            patch.setattr(knowledge_module,'_retrieval_chunks',lambda rows:rows)
            old=env.store.ingest(path,entry['collection'],metadata)
        pin={'document_id':old['document_id'],'revision':1};old_pins.append(pin)
        archive=env.store.root/pin['document_id']/'1'
        old_files.update({str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in archive.iterdir()})
        new=env.store.ingest(path,entry['collection'],metadata,document_id=pin['document_id'])
        assert new['revision']==2 and new['sha256']==old['sha256']
        new_pin={**pin,'revision':2};new_pins.append(new_pin)
        segments=env.store.source(**new_pin)['segments']
        assert ''.join(row['text'] for row in segments)==path.read_text(encoding='utf-8')
        if entry['id']=='paraview-basic':
            assert len(env.store.source(**pin)['segments'])==1 and len(segments)>20
            assert max(len(row['text'].encode()) for row in segments)<8000
        for segment in segments:
            exact=env.store.source(**new_pin,locator=segment['locator'])
            assert exact['segments']==[segment]
    assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==digest for p,digest in old_files.items())
    collections=[entry['collection'] for entry in entries]
    own=[new_pins[0],new_pins[2]];others=[new_pins[1]]
    env.runtime.definitions['mesh'].update(collections=collections)
    env.runtime.runtime.external_model=True
    env.runtime.runtime.transmission.update(collections=collections,allow_public_search=False,allow_results=False)
    context=env.state['context'];context['selected_sources']=deepcopy(new_pins)
    context['selected_document_ids']=[p['document_id'] for p in new_pins]
    context['transmission_scope'].update(collections=collections,source_refs=deepcopy(new_pins),allow_public_search=False)
    context['research_team']['objective']='메시와 응력 회복, 하중과 변위를 어떤 관측으로 구분할까요?'
    env.state['assignments']['mesh'].update(source_refs=own,question='공식 문서에서 응력과 메시 관측을 확인하세요.',checks=['접촉과 구속의 적용 조건'])
    original_auto=[]
    for pin in [old_pins[0],old_pins[2]]:
        details=env.store.revision_details(**pin)
        for row in env.store.source(**pin)['segments']:
            original_auto.append({**row,'revision_metadata':projected_source_metadata(details['metadata'],row),
                'extraction_limitations':details['failed_segments']})
    original_bytes=len(json.dumps(original_auto,ensure_ascii=False).encode())
    assert original_bytes>env.runtime.runtime.max_payload_bytes==100000
    before={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in env.store.root.rglob('*') if p.is_file()}
    binding=make_binding(env);role_context,snippets=selected_knowledge_context(binding)
    assert {row['document_id'] for row in snippets}=={row['document_id'] for row in own}
    assert all(row['revision']==2 for row in snippets)
    assert not any(row['document_id']==others[0]['document_id'] for row in snippets)
    assert 'stress' in role_context['source_retrieval']['query'] and 'mesh' in role_context['source_retrieval']['query']
    assert all(row['retrieval']['score']>0 for row in snippets)
    assert all('not the complete document' in row['retrieval']['scope'] for row in snippets)
    payload={'question':binding.assignment['question'],'context':role_context,'source_segments':snippets}
    env.runtime._transmission_check(payload,role_context)
    manifest=binding.prepare_model_input(payload,mode='initial',supplied_items=[])
    assert manifest['payload_digest']==canonical_hash(payload) and manifest['payload_bytes']<100000
    for receipt_id in binding.generation_ledger.read_receipt_ids:
        receipt=binding.generation_ledger.state['read_receipts'][receipt_id]
        scope={**env.state,'generation_ledger':binding.generation_ledger}
        assert check_receipt(receipt,runtime=env.runtime,workspace_id='local',current_scope=scope,recipients=['mesh'])
        item=env.state['resolve_payload'](receipt['payload_ref'])
        assert item['text']==env.store.source(**receipt['source_ref'])['segments'][0]['text']
    assert binding.tool_parameters('knowledge.search',{'type':'object'}) is not None
    binding.budget_slice.consume('tool')
    permit=binding.prepare_tool('knowledge.search',{'query':'stress mesh','top_k':2},debit=True)
    found=binding.finish_tool(permit,permit['invoke']())['payload']['hits']
    assert found and all(row['document_id'] in {p['document_id'] for p in own} for row in found)
    env.state['assignments']['mesh']['tools']=['knowledge.source']
    assert make_binding(env,task='source-only').tool_parameters('knowledge.search',{'type':'object'}) is None
    env.state['assignments']['mesh'].update(question='zzzznomatchtoken',checks=[])
    context['research_team']['objective']='zzzznomatchtoken'
    empty_context,empty=selected_knowledge_context(make_binding(env,task='empty'))
    assert empty==[] and all(row['status']=='NO_LEXICAL_MATCH' for row in empty_context['source_retrieval']['sources'])
    env.state['assignments']['mesh'].update(source_refs=[old_pins[2]],question='ParaView pipeline display filter')
    oversized_binding=make_binding(env,task='original-large-chunk')
    oversized_context,oversized=selected_knowledge_context(oversized_binding)
    assert oversized==[] and oversized_binding.generation_ledger.read_receipt_ids==[]
    assert oversized_context['source_retrieval']['sources'][0]['status']=='NOT_SUPPLIED_PAYLOAD_LIMIT'
    after={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in env.store.root.rglob('*') if p.is_file()}
    assert after==before and binding.budget_slice.used_models==0
    print(json.dumps({'original_auto_bytes':original_bytes,'new_manifest_bytes':manifest['payload_bytes'],
        'new_snippet_count':len(snippets),'new_snippet_bytes':len(json.dumps(snippets,ensure_ascii=False).encode()),
        'cap':100000,'models':0,'network':0,'original_and_new_source_bytes_unchanged':True}))


def test_actual_two_reads_subset_reverse_and_vendor_citation_roundtrip(tmp_path):
    from test_research_team_evidence import make_env,make_binding
    from caelab.assist.research_team import cited_information
    from caelab.assist.research_evidence import check_receipt
    from caelab.research_team_contract import validate_reply
    from caelab.assist._vendor.costorm.dataclass import KnowledgeBase,ConversationTurn
    from caelab.assist._vendor.costorm.vectors import LocalEncoder
    env=make_env(tmp_path)
    second=tmp_path/'second.md';second.write_text('# Second\nIndependent length is 23 mm.',encoding='utf-8')
    saved=env.store.ingest(second,'engineering',{'title':'Second public guide','access_scope':'public'})
    pin={key:saved[key] for key in ('document_id','revision')}
    env.state['context']['selected_sources'].append(pin)
    env.state['context']['selected_document_ids'].append(pin['document_id'])
    env.state['context']['transmission_scope']['source_refs'].append(pin)
    for assignment in env.state['assignments'].values():assignment['source_refs'].append(pin)
    binding=make_binding(env);refs=[]
    for selected in (env.pin,pin):
        segment=env.store.source(**selected)['segments'][0]
        ref={key:segment[key] for key in ('document_id','revision','locator')};refs.append(ref)
        permit=binding.prepare_tool('knowledge.source',ref,debit=True)
        binding.finish_tool(permit,env.store.source(**ref))
    ledger=binding.generation_ledger
    scope={**env.state,'generation_ledger':ledger}
    scope['check_receipt']=lambda receipt:check_receipt(receipt,runtime=env.runtime,workspace_id='local',current_scope=scope,recipients=['mesh'])
    record={'read_receipt_ids':ledger.read_receipt_ids}
    for sources in ([refs[1]],[refs[1],refs[0]]):
        original={'answer':'Chosen source [1].'+(' Other source [2].' if len(sources)==2 else ''),'sources':deepcopy(sources)}
        raw=deepcopy(original)
        infos=cited_information(raw,record,ledger.state,scope)
        assert infos[1].meta['source']==refs[1] and infos[2].meta['source']==refs[0]
        turn=ConversationTurn('mesh',raw['answer'],'Potential Answer',cited_info=infos)
        kb=KnowledgeBase('Public citation test',lambda *a,**k:pytest.fail('No model during root insertion'),6,LocalEncoder())
        kb.update_from_conv_turn(turn,insert_under_root=True)
        restored=KnowledgeBase.from_dict(kb.to_dict(),lambda *a,**k:pytest.fail('No model during read'),6,LocalEncoder())
        assert restored.info_uuid_to_info_dict[1].meta['source']==refs[1]
        assert restored.info_uuid_to_info_dict[2].meta['source']==refs[0]
        assert raw==original
    invalid={'answer':'Unresolved [3].','sources':[refs[1]],'research_reply':{
        'kind':'hypothesis','claims':[],'questions':[],'revisions':[],'unknowns':[]}}
    assert validate_reply(invalid,task={'kind':'INITIAL_RESEARCH'},allowed_references=[refs[1]],
        read_receipts=list(ledger.state['read_receipts'].values()))['status']=='INVALID'


def test_actual_retained_result_repair_uses_same_task_receipts_without_new_read(tmp_path,monkeypatch):
    from test_research_team_evidence import make_env,make_binding
    from test_research_team_results import retain_fixture
    from test_workbench_assist import mock_generator
    from caelab import research_team_results as physical
    from caelab.assist.research_evidence import ResultAccess
    bench=Workbench(tmp_path/'result-owner',configuration={'workers':1})
    try:
        _,reference,_,readers=retain_fixture(bench,monkeypatch,{'execution_status':'SUCCEEDED','responses':{
            'force':{'kind':'series','value':[2.,3.,5.],'unit':'N','component':'Z','location':'top',
                     'axes':[{'name':'time','unit':'s','values':[0.,1.,2.]}]}}})
        env=make_env(tmp_path)
        selected=physical.make_result_selection(readers['probe'](reference),source_id='exact-force',
            selection_request={'metadata_only':False,'channels':[{'response':'force','frame_indices':[1]}]})
        for assignment in env.state['assignments'].values():
            assignment['tools'].append('results.read');assignment['result_refs']=[selected]
        for definition in env.runtime.definitions.values():definition['tools'].append('results.read')
        env.state['context']['transmission_scope']['result_ids']=[reference['job_id']]
        readers['transmission_check']=env.runtime._transmission_check
        env.result_access=ResultAccess(readers=readers,current_scope_probe=lambda:env.state)
        initial=make_binding(env)
        permit=initial.prepare_tool('results.read',{'source_id':'exact-force'},debit=True)
        read=initial.finish_tool(permit,permit['invoke']())['read_receipts'][0]
        original=initial.finalize_response({'answer':'Original invalid raw response','sources':[]},{'status':'INVALID'})
        env.state['ledger_state']={**deepcopy(initial.generation_ledger.state),'responses':{original['id']:original}}
        repaired=make_binding(env,state=initial.generation_ledger.state,task=initial.task_id)
        repaired.frozen_task_ref={'id':initial.task_id,'kind':'INITIAL_RESEARCH',
            'continuation':{'raw_response_ref':original['raw_response_ref']}}
        repaired.budget_slice.ticket={'kind':'REPAIR'};repaired.budget_slice.tool_calls=0
        marker={**reference,'selector':read['returned_selector'],'read_receipt_id':read['id']}
        final={'answer':'Controlled retained force is 3 N.','sources':[marker],
            'research_reply':{'kind':'observation','claims':[{'text':'The retained selected sample is 3 N.',
                'basis':'observed','conditions':['same frame'],'source_refs':[marker],'missing_evidence':[]}],
                'questions':[],'revisions':[],'unknowns':[]}}
        env.runtime.runtime.generator=mock_generator([final])
        original_read=readers['read'];numeric=[]
        readers['read']=lambda *a,**k:(numeric.append(1),original_read(*a,**k))[1]
        result=env.runtime._run_approved_role('mesh','Finish the same task',repaired.generation_ledger.context,
            repaired.role_session_id,workspace_id='local',budget=repaired.budget_slice,visited=['mesh'],binding=repaired)
        assert result['status']=='ANSWERED',result
        assert result['research_response']['validation']['status']=='VALID'
        assert read['id'] in result['research_response']['read_receipt_ids'] and not numeric
        # A retained value never grants access after the original result is withdrawn.
        env.state['context']['transmission_scope']['result_ids']=[]
        from caelab.assist.research_team import restore_task_reads
        with pytest.raises(PermissionError):restore_task_reads(repaired,{},original['raw_response_ref'])
        assert not numeric
    finally:assert bench.shutdown()['joined']


def test_real_report_saved_turn_and_failed_report_preserves_previous(tmp_path, monkeypatch):
    from examples.research_team_public import create_case, controlled_generation
    from caelab.assist import openscience_host
    wb, doc, config = create_case(tmp_path / 'wb', limit=8)
    try:
        with controlled_generation() as calls:
            doc, result = finish(wb, doc, command(wb, doc, 'expert.ask'))
            assert result['status'] == 'ANSWERED'
            # Explicit retry services only retained pending map transactions.
            before = len([row for row in calls if row['kind'] == 'role'])
            doc, result = finish(wb, doc, command(wb, doc, 'expert.retry'))
            assert len([row for row in calls if row['kind'] == 'role']) == before
            doc, result = finish(wb, doc, command(wb, doc, 'expert.report'))
            assert result['status'] == 'ANSWERED', result
            team = doc['discussion']['research_team']
            reports = [row for row in team['actions'].values() if row.get('report', {}).get('status') == 'APPLIED']
            assert len(reports) == 1 and reports[0]['report']['input_manifest_ids']
            original = result['costorm']['report']
            turn = next(row for row in doc['turns'] if row.get('research_action_id') == reports[0]['id'])
            assert turn['text'] == original['text'] and turn['dependency_ids']
            assert turn['response']['costorm']['report'] == original and turn['input_manifest_ids']
            assert len([row for row in calls if row['kind'] == 'role']) == before
            monkeypatch.setattr(openscience_host, 'run_openscience', lambda *a, **k: (_ for _ in ()).throw(RuntimeError('controlled report failure')))
            doc, failed = finish(wb, doc, command(wb, doc, 'expert.report'))
            assert failed['status'] == 'STOPPED' and failed['costorm']['report'] == original
            assert len([row for row in calls if row['kind'] == 'role']) == before
            saved = command(wb, doc, 'document.save')['document']
            identifier = saved['id']; observed = len(calls)
    finally:assert wb.shutdown()['joined']
    cold = Workbench(tmp_path / 'wb', configuration=config)
    try:
        reopened = cold.document_open(kind='expert', document_id=identifier)
        assert len(calls) == observed
        assert next(row for row in reopened['turns'] if row.get('research_action_id') == reports[0]['id'])['text'] == original['text']
    finally:assert cold.shutdown()['joined']


def test_actual_shared_consultation_has_protected_target_and_separate_task(tmp_path, monkeypatch):
    from examples.research_team_public import controlled_generation
    from caelab.assist import openscience_host
    wb, doc, config = configured(tmp_path, 8)
    try:
        runtime = wb.assistance().experts
        for row in runtime.definitions.values():row['tools'].append('experts.consult')
        draft = deepcopy(doc['draft'])
        for row in draft['context']['research_team']['assignments']:row['tools'].append('experts.consult')
        draft['context']['consult_experts'] = ['r1']; draft['budget']['consultations'] = 1
        doc = command(wb, doc, 'expert.update', {'draft': draft})['document']
        with controlled_generation() as calls:
            underlying = openscience_host.run_openscience; observed = []
            def host(prompt, tools, budget, model, **options):
                if 'Conversation and request JSON: ' in prompt:
                    payload = json.loads(prompt.split('Conversation and request JSON: ', 1)[1])
                    task = payload['context']['research_task']; observed.append((deepcopy(task), list(tools)))
                    if task['kind'] == 'ANSWER':
                        assert 'experts_consult' in tools
                        response = tools['experts_consult']['call'](expert_id='r1', question='Which repeat calibration would distinguish the target claim?')
                        assert response['status'] == 'ANSWERED', response
                        return underlying(prompt, {k: v for k, v in tools.items() if k != 'knowledge_source'}, budget, model, **options)
                return underlying(prompt, tools, budget, model, **options)
            monkeypatch.setattr(openscience_host, 'run_openscience', host)
            doc, first = finish(wb, doc, command(wb, doc, 'expert.ask'))
            assert first['status'] == 'ANSWERED', first['answer']
            assert all('experts_consult' not in tools for task, tools in observed if task['kind'] == 'INITIAL_RESEARCH')
            draft = deepcopy(doc['draft']); draft['budget']['model_calls'] = 4
            doc = command(wb, doc, 'expert.update', {'draft': draft})['document']
            doc, answer = finish(wb, doc, command(wb, doc, 'expert.advance'))
            assert answer['status'] == 'ANSWERED', answer['answer']
            assert answer['costorm']['usage']['model_calls'] == 4
            assert answer['costorm']['usage']['consultations'] == 1
            team = doc['discussion']['research_team']
            child = next(row for row in team['tasks'].values() if row['kind'] == 'CONSULT')
            parent = next(row for row in team['tasks'].values() if row['kind'] == 'ANSWER')
            assert child['status'] == parent['status'] == 'COMPLETED' and child['id'] != parent['id']
            target_response = team['responses'][child['completed_response_id']]
            caller_response = team['responses'][parent['completed_response_id']]
            assert set(target_response['dependency_ids']) <= set(caller_response['dependency_ids'])
            assert [row['task']['kind'] for row in calls if row['kind'] == 'role'].count('CONSULT') == 1
            identifiers = ['E' + canonical_hash({'owner': doc['id'], 'phase': row['phase_id'], 'task': row['id']})[:40]
                           for row in (child, parent)]
            assert identifiers[0] != identifiers[1]
            sessions = [json.loads((wb.root / 'assistance' / 'sessions' / (identifier + '.json')).read_text(encoding='utf-8'))
                        for identifier in identifiers]
            assert all(session['turns'] for session in sessions)
    finally:assert wb.shutdown()['joined']


@pytest.mark.parametrize('failure', ['invalid', 'transport'])
def test_explicit_one_step_repair_or_finalize_keeps_completed_peers(tmp_path, monkeypatch, failure):
    from examples.research_team_public import controlled_generation
    from caelab.assist import openscience_host
    wb, doc, _ = configured(tmp_path, 4)
    try:
        with controlled_generation():
            original = openscience_host.run_openscience; seen = []; injected = False
            def host(prompt, tools, budget, model, **options):
                nonlocal injected
                if 'Conversation and request JSON: ' in prompt:
                    task = json.loads(prompt.split('Conversation and request JSON: ', 1)[1])['context']['research_task']
                    seen.append((task['actor_id'], task['id'], options['max_steps'], list(tools)))
                    raw = original(prompt, tools, budget, model, **options)
                    if task['actor_id'] == 'r0' and not injected:
                        injected = True
                        if failure == 'transport':raise ConnectionError('Controlled failure after the retained read')
                        reply = json.loads(raw); reply['research_reply']['kind'] = 'invalid controlled structure'
                        return json.dumps(reply)
                    return raw
                return original(prompt, tools, budget, model, **options)
            monkeypatch.setattr(openscience_host, 'run_openscience', host)
            doc, first = finish(wb, doc, command(wb, doc, 'expert.ask'))
            team = doc['discussion']['research_team']; initial = next(iter(team['phases'].values()))['initial_task_ids']
            task = next(row for row in team['tasks'].values() if row['id'] in initial and row['actor_id'] == 'r0')
            assert task['status'] == ('WAITING_FINAL' if failure == 'transport' else 'WAITING_REPAIR')
            assert any(row['status'] == 'COMPLETED' and row['actor_id'] == 'r1' for row in team['tasks'].values())
            original_raw = deepcopy(team['responses'])
            doc, second = finish(wb, doc, command(wb, doc, 'expert.advance'))
            task_after = doc['discussion']['research_team']['tasks'][task['id']]
            assert task_after['status'] == 'COMPLETED', second['answer']
            repaired = [row for row in seen if row[1] == task['id']]
            assert [row[2] for row in repaired] == [2, 1]
            assert repaired[-1][3] == []
            assert len([row for row in seen if row[0] == 'r1']) == 1
            assert all(doc['discussion']['research_team']['responses'][key] == value for key, value in original_raw.items())
    finally:assert wb.shutdown()['joined']


def test_actual_addressed_answer_user_intervention_and_new_phase_undo_cold(tmp_path, monkeypatch):
    from examples.research_team_public import create_case,controlled_generation
    from caelab.assist import openscience_host
    wb,doc,config=create_case(tmp_path/'wb',limit=8)
    try:
        with controlled_generation() as calls:
            original=openscience_host.run_openscience;inputs=[]
            def host(prompt,tools,budget,model,**options):
                raw=original(prompt,tools,budget,model,**options)
                if 'Conversation and request JSON: ' in prompt:
                    payload=json.loads(prompt.split('Conversation and request JSON: ',1)[1]);inputs.append(deepcopy(payload))
                    if payload['context']['research_task']['kind']=='QUESTION':
                        parsed=json.loads(raw);parsed['research_reply']['questions'][0]['expert_id']='r1'
                        return json.dumps(parsed)
                return raw
            monkeypatch.setattr(openscience_host,'run_openscience',host)
            doc,first=finish(wb,doc,command(wb,doc,'expert.ask'))
            doc,second=finish(wb,doc,command(wb,doc,'expert.advance'))
            assert second['status']=='ANSWERED',second['answer']
            actual_answer=[row for row in calls if row['kind']=='role' and row['task']['kind']=='ANSWER']
            assert len(actual_answer)==1 and actual_answer[0]['task']['actor_id']=='r1'
            team=doc['discussion']['research_team'];phase=next(iter(team['phases'].values()))
            target=next(row for row in team['responses'].values() if row['actor_id']=='r0' and row.get('claim_refs'))
            authored='추가 계산 없이 같은 하중 방향으로 교정을 재확인할 이유를 설명해 주세요.'
            paused=command(wb,doc,'expert.pause')['document'];draft=deepcopy(paused['draft'])
            draft['composer']['text']=authored;draft['composer']['reply_to']='A'+target['id']
            draft['context']['research_team']['requested_next']={'expert_id':'r2','task_id':None,
                'target_turn_id':'A'+target['id'],'target_claim_id':target['claim_refs'][0]['id']}
            updated=command(wb,paused,'expert.update',{'draft':draft})['document']
            before=len(calls);intervened=command(wb,updated,'expert.intervene')['document']
            assert len(calls)==before
            with pytest.raises(ValueError):command(wb,intervened,'expert.advance')
            resumed=command(wb,intervened,'expert.resume')['document']
            doc,answer=finish(wb,resumed,command(wb,resumed,'expert.advance'))
            assert answer['status']=='ANSWERED',answer['answer']
            user=[row for row in calls if row['kind']=='role' and row['task'].get('user_question')]
            assert len(user)==1 and user[0]['task']['actor_id']=='r2'
            assert user[0]['task']['target_claim_id']==target['claim_refs'][0]['id']
            assert authored in user[0]['task']['question_ref']['text']
            # The same recipient/claim with a distinct authored question is a
            # new task; repeating advance without another question is not.
            second_question='같은 교정 자료로 하중 방향의 영향을 어떻게 구별하나요?'
            draft=deepcopy(doc['draft']);draft['composer']['text']=second_question
            doc=command(wb,doc,'expert.update',{'draft':draft})['document']
            doc=command(wb,doc,'expert.intervene')['document']
            doc,again=finish(wb,doc,command(wb,doc,'expert.advance'))
            answered=[row for row in calls if row['kind']=='role' and row['task'].get('user_question')]
            assert len(answered)==2 and answered[0]['task']['id']!=answered[1]['task']['id']
            assert second_question in answered[1]['task']['question_ref']['text']
            old=doc['draft']['context']['research_team']['phase_id'];draft=deepcopy(doc['draft'])
            draft['context']['research_team'].update(phase_id=None,requested_next=None)
            command_id='CexplicitNextPhase'
            args={'draft':draft};generation=doc['generation'];before=len(calls)
            prepared=wb.document_command(doc['id'],'expert.update',args,session_id=doc['session_id'],
                expected_generation=generation,command_id=command_id)
            new=prepared['document']['draft']['context']['research_team']
            assert new['phase_id'] and new['phase_id']!=old and new['parent_phase_id']==old
            assert wb.document_command(doc['id'],'expert.update',args,session_id=doc['session_id'],
                expected_generation=generation,command_id=command_id)==prepared
            undone=command(wb,prepared['document'],'document.undo')['document']
            assert undone['draft']['context']['research_team']['phase_id']==old
            redone=command(wb,undone,'document.redo')['document']
            assert redone['draft']['context']['research_team']==new
            saved=command(wb,redone,'document.save')['document'];identifier=saved['id']
            assert len(calls)==before
    finally:assert wb.shutdown()['joined']
    cold=Workbench(tmp_path/'wb',configuration=config)
    try:
        read=cold.document_open(kind='expert',document_id=identifier)
        assert read['draft']['context']['research_team']==new and len(calls)==before
    finally:assert cold.shutdown()['joined']


def test_selected_prior_phase_body_and_checks_are_actual_inputs(tmp_path,monkeypatch):
    from examples.research_team_public import controlled_generation
    from caelab.assist import openscience_host
    wb,doc,_=configured(tmp_path,4)
    try:
        with controlled_generation() as calls:
            doc,_=finish(wb,doc,command(wb,doc,'expert.ask'))
            team=doc['discussion']['research_team']
            prior=next(row for row in team['responses'].values() if row['actor_id']=='r0')
            turn_id='A'+prior['id'];draft=deepcopy(doc['draft'])
            draft['participants']=['r2'];draft['budget']['model_calls']=1
            draft['composer']['text']='선택한 이전 판단의 적용 조건을 구별해 주세요.'
            assignment=deepcopy(draft['context']['research_team']['assignments'][2]);assignment['tools']=[]
            assignment['checks']=['교정 자료의 적용 범위']
            draft['context']['research_team'].update(phase_id=None,assignments=[assignment],
                carry_forward_turn_ids=[turn_id],requested_next=None)
            doc=command(wb,doc,'expert.update',{'draft':draft})['document']
            original=openscience_host.run_openscience;inputs=[]
            def host(prompt,*args,**kwargs):
                if 'Conversation and request JSON: ' in prompt:
                    inputs.append(json.loads(prompt.split('Conversation and request JSON: ',1)[1]))
                return original(prompt,*args,**kwargs)
            monkeypatch.setattr(openscience_host,'run_openscience',host)
            doc,result=finish(wb,doc,command(wb,doc,'expert.ask'))
            assert result['status']=='ANSWERED',result['answer']
            assert len(inputs)==1 and inputs[0]['context']['selected_prior_turns'][0]['turn_id']==turn_id
            assert inputs[0]['context']['selected_prior_turns'][0]['response']['answer'].startswith('CONTROLLED')
            assert inputs[0]['context']['research_team']['assignment']['checks']==['교정 자료의 적용 범위']
            newest=next(row for row in doc['discussion']['research_team']['responses'].values()
                        if row['phase_id']==doc['draft']['context']['research_team']['phase_id'])
            assert set(prior['dependency_ids'])<=set(newest['dependency_ids'])
    finally:assert wb.shutdown()['joined']


def test_revoked_shared_history_does_not_stop_still_permitted_independent_role(tmp_path,monkeypatch):
    from examples.research_team_public import controlled_generation
    from caelab.assist import openscience_host
    wb,doc,_=configured(tmp_path,4)
    try:
        source=wb.root/'independent.md';source.write_text('# Independent\nIndependent measured length is 27 mm.',encoding='utf-8')
        ingested=wb.assistance().knowledge.ingest(str(source),collection='public')
        reference={key:ingested[key] for key in ('document_id','revision')}
        draft=deepcopy(doc['draft']);first=draft['context']['selected_sources'][0]
        draft['context']['selected_sources'].append(reference)
        draft['context']['research_team']['assignments'][2]['source_refs']=[reference]
        doc=command(wb,doc,'expert.update',{'draft':draft})['document']
        with controlled_generation() as calls:
            doc,_=finish(wb,doc,command(wb,doc,'expert.ask'))
            wb.assistance().knowledge.revoke(first['document_id'])
            original=openscience_host.run_openscience;inputs=[]
            def host(prompt,*args,**kwargs):
                if 'Conversation and request JSON: ' in prompt:
                    inputs.append(json.loads(prompt.split('Conversation and request JSON: ',1)[1]))
                return original(prompt,*args,**kwargs)
            monkeypatch.setattr(openscience_host,'run_openscience',host)
            doc,result=finish(wb,doc,command(wb,doc,'expert.advance'))
            independent=[row for row in inputs if row['context']['research_task']['kind']=='INITIAL_RESEARCH']
            assert len(independent)==1 and independent[0]['context']['research_task']['actor_id']=='r2'
            assert '27 mm' in independent[0]['source_segments'][0]['text'] and not independent[0]['history']
            assert result['costorm']['map_results'][0]['status']=='BLOCKED_SCOPE'
            assert doc['discussion']['research_team']['map_checkpoints']=={}
    finally:assert wb.shutdown()['joined']


def test_denied_initial_task_has_no_host_while_other_initial_task_runs(tmp_path):
    from examples.research_team_public import controlled_generation
    wb,doc,_=configured(tmp_path,8)
    try:
        source=wb.root/'permitted.md';source.write_text('# Permitted\nMeasured length is 31 mm.',encoding='utf-8')
        ingested=wb.assistance().knowledge.ingest(str(source),collection='public')
        reference={key:ingested[key] for key in ('document_id','revision')}
        draft=deepcopy(doc['draft']);denied=draft['context']['selected_sources'][0]
        draft['context']['selected_sources'].append(reference)
        draft['context']['research_team']['assignments'][2]['source_refs']=[reference]
        doc=command(wb,doc,'expert.update',{'draft':draft})['document']
        wb.assistance().knowledge.revoke(denied['document_id'])
        with controlled_generation() as calls:
            doc,result=finish(wb,doc,command(wb,doc,'expert.ask'))
            assert result['status']=='STOPPED'
            assert [row['task']['actor_id'] for row in calls if row['kind']=='role']==['r2']
            tasks=doc['discussion']['research_team']['tasks'].values()
            assert {row['actor_id'] for row in tasks if row['status']=='BLOCKED_SCOPE'}=={'r0','r1'}
            assert any(row['actor_id']=='r2' and row['kind']=='INITIAL_RESEARCH' and row['status']=='COMPLETED' for row in tasks)
    finally:assert wb.shutdown()['joined']


@pytest.mark.parametrize('limit,actions',[(4,3),(8,2)])
def test_real_owner_registered_roles_barrier_exact_task_targets_and_cold(tmp_path,scripted,monkeypatch,limit,actions):
    calls=role_host(monkeypatch);wb,doc,config=configured(tmp_path,limit)
    try:
        results=[]
        for index in range(actions):
            doc,result=finish(wb,doc,command(wb,doc,'expert.ask' if index==0 else 'expert.advance'))
            assert result['status']=='ANSWERED',(result['status'],result.get('reason'),result.get('answer'))
            results.append(result)
            if index==0:
                assert [c['task']['actor_id'] for c in calls if c['task']['kind']=='INITIAL_RESEARCH']==(
                    ['r0','r1'] if limit==4 else ['r0','r1','r2'])
        assert [c['task']['kind'] for c in calls]==['INITIAL_RESEARCH']*3+['QUESTION','ANSWER']
        assert len({c['task']['id'] for c in calls})==5
        for call in calls[:3]:
            assert 'CALIBRATION_CHECK' not in json.dumps(call['input'])
            assert not call['input']['history'] and 'shared_responses' not in call['input']['context']
            assert call['max_steps']==2
        assert calls[3]['max_steps']==1 and calls[3]['task']['target_claim_id']
        assert calls[4]['task']['target_turn_id']
        team=doc['discussion']['research_team'];phase=next(iter(team['phases'].values()))
        assert phase['initial_barrier']=='OPEN'
        assert all(team['tasks'][i]['status']=='COMPLETED' for i in phase['task_ids'])
        assert len(team['responses'])==5
        assert all(row['raw_response_ref'] and row['input_manifest_ids'] for row in team['responses'].values())
        assert all(row['proposal_refs'] is not None for row in team['responses'].values())
        assert all(row['costorm']['usage']['model_calls']<=limit for row in results)
        before=len(calls);jobs=len(wb.manager.list())
        saved=command(wb,doc,'document.save')['document'];identifier=saved['id']
        assert len(calls)==before and len(wb.manager.list())==jobs
    finally:assert wb.shutdown()['joined']
    cold=Workbench(tmp_path,configuration=config)
    try:
        reopened=cold.document_open(kind='expert',document_id=identifier)
        assert len(calls)==before and len(cold.manager.list())==jobs
        assert reopened['discussion']['research_team']['responses']==saved['discussion']['research_team']['responses']
    finally:assert cold.shutdown()['joined']
