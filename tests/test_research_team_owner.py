"""Existing Discussion owner checkpoint/CAS tests; provider execution is zero."""
from copy import deepcopy
import pytest
from caelab.workbench import Workbench
from caelab.discussion_document import default_draft
from caelab.discussion_research_team import (start_record, _OwnerBinding, checkpoint,
    read_checkpoint, resolve_asset, empty_state)
from caelab.research_team_contract import enabled, validate_draft
from caelab.storage import canonical_hash


def team_draft(roles=('r0','r1','r2'),limit=4):
    draft=default_draft();draft['participants']=list(roles);draft['composer']['text']='공개 관측을 구별할 조건은 무엇인가?'
    draft['budget']['model_calls']=limit
    draft['context']={'discussion_mode':'costorm','selected_sources':[],
        'research_team':{'version':2,'phase_id':None,'parent_phase_id':None,
        'objective':draft['composer']['text'],'deliverable':'근거 가설과 판별 질문',
        'assignments':[{'expert_id':role,'mode':'investigator','question':role+'의 근거와 불확실성을 조사하세요.',
            'checks':[],'tools':['knowledge.source'],'source_refs':[],'result_refs':[]} for role in roles],
        'shared_evidence':[],'carry_forward_turn_ids':[],'requested_next':None,'turn_limit':8,'stop_when':[]}}
    return draft


def definitions():
    return [{'id':role,'label':role,'instructions':'Use actual scoped tools. Do not grant engineering approval.',
        'collections':['public'],'tools':['knowledge.source'],'answer_sections':['evidence','assumptions','next_check']}
        for role in ('r0','r1','r2')]


def seeded(tmp_path):
    wb=Workbench(tmp_path,configuration={'experts':definitions(),'runtime':{'provider':'openscience',
        'model':'openai-codex/test-double','external_model':False,'max_model_calls':8}})
    opened=wb.document_open(kind='expert',draft=team_draft())
    owner=wb.discussion_documents;document=owner._documents[opened['id']]
    record=start_record(owner,document,'Cstart',action='start',turn={'id':'Uauthored'})
    spec=record['protocol_request'];record['active_job_id']='Jcontrolled'
    team=document['discussion']['research_team'];team['actions'][spec['action_id']]['job_id']='Jcontrolled'
    bound=_OwnerBinding(owner,opened['id'],owner.session_id,record['id'],'Jcontrolled','fixed-arguments')
    return wb,owner,document,record,bound


def test_contract_pure_malformed_legacy_and_registered_assignments():
    assert not enabled({'context':'invalid retained editing'})
    assert not enabled({'context':{'discussion_mode':'costorm','research_team':{'version':1}}})
    draft=team_draft();assert not validate_draft(draft,definitions())
    draft['context']['research_team']['assignments'][0]['tools'].append('shell.execute')
    assert validate_draft(draft,definitions())


def test_explicit_acknowledgement_current_task_receipt_and_original_failure(tmp_path):
    wb,owner,document,record,bound=seeded(tmp_path)
    try:
        record['status']='COMPLETED';record['active_job_id']=None
        phase=document['discussion']['research_team']['phases'][record['protocol_request']['phase_id']]
        task=document['discussion']['research_team']['tasks'][phase['initial_task_ids'][0]]
        task.update(status='WAITING_REPAIR',continuation={'raw_response_ref':{'path':'preserved-original.json','sha256':'a'*64},
            'error_type':'ControlledOriginalFailure'})
        original=deepcopy(task['continuation']);owner._persist_draft(document)
        before=len(wb.manager.list());generation=document['generation']
        arguments={'task_id':task['id'],'reason':'측정 자료가 부족하여 이번 범위에서는 판단을 보류합니다.'}
        accepted=wb.document_command(document['id'],'expert.acknowledge_unresolved',arguments,
            session_id=owner.session_id,expected_generation=generation,command_id='CexplicitUnresolved')
        current=owner._documents[document['id']];saved=current['discussion']['research_team']['tasks'][task['id']]
        assert saved['status']=='ACKNOWLEDGED_UNRESOLVED' and saved['completed_response_id'] is None
        assert saved['continuation']==original and saved['acknowledgement']['previous_status']=='WAITING_REPAIR'
        assert current['generation']==generation+1 and len(wb.manager.list())==before
        assert wb.document_command(document['id'],'expert.acknowledge_unresolved',arguments,
            session_id=owner.session_id,expected_generation=generation,command_id='CexplicitUnresolved')==accepted
        with pytest.raises(ValueError):wb.document_command(document['id'],'expert.acknowledge_unresolved',
            {**arguments,'reason':'Different body'},session_id=owner.session_id,expected_generation=generation,command_id='CexplicitUnresolved')
        with pytest.raises(ValueError):wb.document_command(document['id'],'expert.acknowledge_unresolved',arguments,
            session_id=owner.session_id,expected_generation=generation,command_id='CstaleUnresolved')
        assert current['discussion']['research_team']['responses']=={} and current['discussion']['research_team']['map_checkpoints']=={}
        # Acknowledging a question does not fabricate the missing question or
        # allow its dependent answer to call a role.
        for identifier in phase['initial_task_ids'][1:]:
            current=owner._documents[document['id']]
            wb.document_command(document['id'],'expert.acknowledge_unresolved',
                {'task_id':identifier,'reason':'원 관측 부족을 명시 보존합니다.'},session_id=owner.session_id,
                expected_generation=current['generation'])
        current=owner._documents[document['id']];team=current['discussion']['research_team']
        assert team['phases'][phase['id']]['initial_barrier']=='OPEN'
        question=next(row for row in team['tasks'].values() if row['kind']=='QUESTION')
        wb.document_command(document['id'],'expert.acknowledge_unresolved',
            {'task_id':question['id'],'reason':'질문 자체가 아직 완성되지 않았습니다.'},session_id=owner.session_id,
            expected_generation=current['generation'])
        team=owner._documents[document['id']]['discussion']['research_team']
        from types import SimpleNamespace
        from caelab.assist.research_team import _resolve_target,TeamWaiting
        answer=next(row for row in team['tasks'].values() if row['kind']=='ANSWER')
        with pytest.raises(TeamWaiting,match='새 질문'):
            _resolve_target(SimpleNamespace(read_checkpoint=lambda:team,phase_id=phase['id']),answer)
        assert len(wb.manager.list())==before and team['responses']=={}
    finally:assert wb.shutdown()['joined']


@pytest.mark.parametrize('state',['RUNNING','OUTCOME_UNCONFIRMED','COMPLETED','ACKNOWLEDGED_UNRESOLVED',
    'CLEANUP_UNCONFIRMED','ACTIVE_ROUND','OTHER_PHASE','LEGACY'])
def test_acknowledgement_cannot_clear_running_uncertain_or_complete_task(tmp_path,state):
    wb,owner,document,record,bound=seeded(tmp_path)
    try:
        record['status']='COMPLETED';record['active_job_id']=None
        task=next(iter(document['discussion']['research_team']['tasks'].values()));task['status']=state
        if state=='CLEANUP_UNCONFIRMED':task.update(status='WAITING_TIME',continuation={'cleanup_unconfirmed':True})
        if state=='ACTIVE_ROUND':task['status']='PENDING';record['status']='RUNNING'
        if state=='OTHER_PHASE':task['status']='PENDING';document['draft']['context']['research_team']['phase_id']='Pother'
        if state=='LEGACY':task['status']='PENDING';document['draft']['context']['research_team']['version']=1
        owner._persist_draft(document);before=deepcopy(document)
        with pytest.raises(ValueError):wb.document_command(document['id'],'expert.acknowledge_unresolved',
            {'task_id':task['id'],'reason':'Explicit controlled acknowledgement'},session_id=owner.session_id,
            expected_generation=document['generation'])
        assert owner._documents[document['id']]==before and wb.manager.list()==[]
    finally:assert wb.shutdown()['joined']


def test_real_owner_atomic_raw_checkpoint_cas_idempotence_and_late_job(tmp_path):
    wb,owner,document,record,bound=seeded(tmp_path)
    try:
        raw={'answer':'원문 [1]','proposed_actions':[{'purpose':'판별할 관측'}]}
        receipt=checkpoint(bound,expected_revision=0,event_id='Rraw',payload={'asset':{'id':'Rone','payload':raw}})
        assert resolve_asset(bound,receipt['asset_ref'])==raw
        assert checkpoint(bound,expected_revision=0,event_id='Rraw',payload={'asset':{'id':'Rone','payload':raw}})==receipt
        with pytest.raises(ValueError,match='다른 내용'):
            checkpoint(bound,expected_revision=1,event_id='Rraw',payload={'asset':{'id':'Rone','payload':{'answer':'changed'}}})
        with pytest.raises(ValueError,match='checkpoint'):
            checkpoint(bound,expected_revision=0,event_id='stale',payload={})
        old=deepcopy(document['draft']);document['draft']['composer']['text']='새 미전송 입력 1e'
        checkpoint(bound,expected_revision=1,event_id='late-source',payload={'asset':{'id':'Rtwo','payload':raw}})
        assert document['draft']['composer']['text']=='새 미전송 입력 1e' and old!=document['draft']
        record['status']='COMPLETED'
        with pytest.raises(PermissionError,match='종료'):
            checkpoint(bound,expected_revision=2,event_id='after-end',payload={})
        assert read_checkpoint(bound)['revision']==2
    finally:assert wb.shutdown()['joined']


def test_owner_public_search_ledger_and_nonserializable_handles_do_not_disappear(tmp_path):
    wb,owner,document,record,bound=seeded(tmp_path)
    try:
        ledger={'id':'Laction','logical_action_id':record['protocol_request']['action_id'],
                'attempt_count':2,'entries':{},'read_entries':{}}
        checkpoint(bound,expected_revision=0,event_id='search',payload={'public_search_ledger':ledger})
        saved=read_checkpoint(bound);assert saved['public_search_ledgers'][ledger['logical_action_id']]==ledger
        with pytest.raises(TypeError):
            checkpoint(bound,expected_revision=1,event_id='bad-handle',payload={'asset':{'id':'Bbad','payload':{'invoke':lambda:None}}})
        assert read_checkpoint(bound)==saved
    finally:assert wb.shutdown()['joined']
