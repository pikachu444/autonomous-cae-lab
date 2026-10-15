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
