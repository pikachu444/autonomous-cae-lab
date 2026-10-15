"""Pro research-team R2 records and trusted, non-serializable call bindings.

Only DiscussionDocuments issues bindings. Saved dictionaries describe history,
never credentials, current grants, locks or permission to resume an old job.
"""
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Callable, TypedDict

from .storage import canonical_hash

VARIANT = 'cae_research_team_v2'
VERSION = 2
TASK_STATES = frozenset({'PENDING', 'RUNNING', 'WAITING_BUDGET', 'WAITING_TIME',
    'WAITING_FINAL', 'WAITING_REPAIR', 'BLOCKED_SCOPE', 'OUTCOME_UNCONFIRMED',
    'COMPLETED', 'ACKNOWLEDGED_UNRESOLVED'})
MAP_STATES = frozenset({'PENDING', 'APPLYING', 'WAITING_BUDGET', 'WAITING_TIME',
    'FAILED', 'BLOCKED_SCOPE', 'APPLIED', 'ARCHIVED_PENDING'})
FINISHED_TASKS = frozenset({'COMPLETED', 'ACKNOWLEDGED_UNRESOLVED'})
REPLY_KINDS = frozenset({'observation', 'hypothesis', 'question', 'challenge',
    'revision', 'plan', 'synthesis'})

# Records use dictionaries throughout the existing owner. ToolPermit and
# BoundContext are in-process handles: invoke/runtime/binding are NEVER written
# to checkpoints. Their plain request/receipt fields alone enter owner assets.
# TrustedAction/ApprovedRoleBinding likewise cannot be JSON input or authority.
RECORD_FIELDS = {
    'InputDependency': 'id kind exact_ref selector content_digest parent_ids introduced_by',
    'ModelInputManifest': 'id owner_id phase_id task_id actor_id attempt_id host_invocation_id mode payload_digest payload_bytes dependency_ids coverage status',
    'ReadReceipt': 'id kind request_digest source_ref requested_selector returned_selector read_level returned_digest returned_bytes payload_ref dependency_ids status limitations',
    'ToolPermit': 'id tool canonical_request dispatch invoke current_binding_id debit dependency_ids',
    'BoundToolResult': 'payload read_receipts dependency_ids status limitations',
    'ProjectionResult': 'status projection dependency_ids reason_code',
    'BoundContext': 'context supplied_items dependency_ids',
    'PhaseRecord': 'id parent_id frozen_draft_ref assignments initial_task_ids initial_barrier task_ids shared_turn_ids current_map_revision review_status',
    'TaskRecord': 'id phase_id actor_id kind priority depends_on target_turn_id target_claim_id question_ref input_snapshot_ref status completed_response_id continuation',
    'ActionRecord': 'id phase_id origin kind command_id job_id prepared_arguments_digest allocation_plan task_ids checkpoint_revision search_ledger_id',
    'AttemptRecord': 'id action_id job_id command_id budget_limit reservations observed_tool_calls observed_host_invocations started_at terminal_state',
    'RoleResponse': 'id task_id actor_id phase_id raw_response_ref validation input_manifest_ids dependency_ids read_receipt_ids proposal_refs local_status shared_projection_id',
    'SharedProjection': 'id response_id body_ref dependency_ids recipient_set validation_record current_access_status',
    'MapPending': 'id phase_id response_id shared_projection_id event_id conversation_turn_ref cited_information_refs dependency_ids allow_create_new_node insert_under_root base_map_revision journal_ref status last_error applied_map_revision',
    'MapCheckpoint': 'id previous_id base_revision applied_pending_ids kb_asset_ref dependency_ids citation_map created_by_attempt',
}
# TypedDicts deliberately remain ordinary dicts at runtime and on disk.
for _name, _fields in RECORD_FIELDS.items():
    globals()[_name] = TypedDict(_name, {key: Any for key in _fields.split()})


def enabled(draft):
    context = draft.get('context', {}) if isinstance(draft, dict) else {}
    if not isinstance(context, dict):
        return False
    team = context.get('research_team')
    return (context.get('discussion_mode') == 'costorm' and isinstance(team, dict)
            and type(team.get('version')) is int and team['version'] == VERSION)


def validate_draft(draft, registry):
    """Pure validation; malformed/v1 teams remain editable but cannot execute."""
    errors = []
    def issue(message):
        errors.append({'severity': 'error', 'path': 'context.research_team',
            'message': message, 'blocks_evaluation': True})
    try:
        if not enabled(draft):
            raise ValueError('연구팀 실행은 명시한 현재 v2 단계에서만 가능합니다.')
        team = draft['context']['research_team']
        if any(not isinstance(team.get(key), str) or not team[key].strip()
               for key in ('objective', 'deliverable')):
            raise ValueError('연구 질문과 필요한 산출물을 입력하세요.')
        assignments = team.get('assignments')
        if not isinstance(assignments, list) or not 1 <= len(assignments) <= 8:
            raise ValueError('등록된 역할을 하나 이상, 여덟 개 이하로 선택하세요.')
        definitions = registry.get('experts', []) if isinstance(registry, dict) else registry
        definitions = {row['id']: row for row in definitions}
        actors = set(); coordinators = 0
        for row in assignments:
            actor = row.get('expert_id')
            if actor not in definitions or actor in actors:
                raise ValueError('실제 등록된 역할을 중복 없이 선택하세요.')
            actors.add(actor)
            if row.get('mode') not in {'investigator', 'coordinator'}:
                raise ValueError('역할의 조사 또는 진행 담당을 선택하세요.')
            coordinators += row['mode'] == 'coordinator'
            if not isinstance(row.get('question'), str) or not row['question'].strip():
                raise ValueError('각 역할이 답할 질문을 입력하세요.')
            for key in ('checks', 'tools', 'source_refs', 'result_refs'):
                if not isinstance(row.get(key), list):
                    raise ValueError('역할의 자료·도구·확인 항목을 명시하세요.')
            if not set(row['tools']).issubset(definitions[actor].get('tools', [])):
                raise ValueError('등록 역할의 도구 범위를 늘릴 수 없습니다.')
            for result in row['result_refs']:
                if not isinstance(result, dict) or not {'source_id', 'reference', 'selector', 'descriptor_ref', 'read_limits'} <= result.keys():
                    raise ValueError('정확한 계산·응답·위치 선택이 필요합니다.')
        if coordinators > 1:
            raise ValueError('진행 담당은 한 명까지 선택하세요.')
        if set(draft.get('participants', [])) != actors:
            raise ValueError('참여 역할과 이번 연구팀의 배정을 맞추세요.')
        if type(team.get('turn_limit')) is not int or not 1 <= team['turn_limit'] <= 8:
            raise ValueError('이번 진행의 발언 상한은 1~8입니다.')
        for key in ('shared_evidence', 'carry_forward_turn_ids', 'stop_when'):
            if not isinstance(team.get(key), list):
                raise ValueError('공유 자료와 이어갈 발언을 명시 선택하세요.')
        requested = team.get('requested_next')
        if requested is not None and (not isinstance(requested, dict) or
                requested.get('expert_id') not in actors):
            raise ValueError('다음 질문의 실제 수신 역할을 선택하세요.')
    except (KeyError, TypeError, ValueError) as error:
        issue(str(error))
    return errors


def validate_reply(raw_response, *, task, allowed_references, read_receipts):
    """Validate research structure/exact references, never engineering truth."""
    errors = []
    allowed = {canonical_hash(ref) for ref in allowed_references}
    actual = set()
    for row in read_receipts:
        if row.get('read_level') in {'RESULT_VALUES', 'SELECTED_TEXT', 'ABSTRACT', 'BIBLIOGRAPHIC'}:
            ref = row.get('source_ref')
            actual.add(canonical_hash(ref))
            if row.get('kind') == 'result' and isinstance(ref, dict):
                selector = row.get('returned_selector')
                actual.add(canonical_hash({**ref, 'selector': selector, 'read_receipt_id': row['id']}))
    try:
        import re
        count = len(raw_response.get('sources', []))
        if any(not 1 <= int(number) <= count for number in re.findall(r'\[(\d+)\]', raw_response.get('answer') or '')):
            errors.append('본문 인용 번호는 실제 sources 목록의 1번부터 같은 순서로 연결해야 합니다.')
        reply = raw_response['research_reply']
        if reply.get('kind') not in REPLY_KINDS:
            errors.append('연구 발언의 종류가 필요합니다.')
        for name in ('claims', 'questions', 'revisions', 'unknowns'):
            if not isinstance(reply.get(name), list):
                errors.append(name + ' 목록이 필요합니다.')
        for claim in reply.get('claims', []):
            if (not isinstance(claim.get('text'), str) or not claim['text'].strip()
                    or claim.get('basis') not in {'observed', 'inferred', 'hypothesized'}):
                errors.append('주장의 원문과 관측·추론·가설 구분이 필요합니다.')
            for name in ('conditions', 'source_refs', 'missing_evidence'):
                if not isinstance(claim.get(name), list):errors.append(name + ' 목록이 필요합니다.')
            for ref in claim.get('source_refs', []):
                if canonical_hash(ref) not in allowed:
                    errors.append('허용된 정확 자료에 없는 인용입니다.')
            if claim.get('basis') == 'observed' and not claim.get('source_refs'):
                errors.append('관측 주장은 실제 읽은 근거를 연결해야 합니다.')
            if claim.get('basis') == 'observed' and any(canonical_hash(ref) not in actual for ref in claim.get('source_refs', [])):
                errors.append('관측 근거의 실제 읽기 기록이 없습니다.')
        if task.get('target_claim_id') and reply.get('kind') in {'question', 'challenge'}:
            if not any(q.get('target_claim_id') == task['target_claim_id'] for q in reply.get('questions', [])):
                errors.append('배정한 실제 주장에 질문을 연결하세요.')
        for revision in reply.get('revisions', []):
            if revision.get('decision') not in {'keep', 'revise', 'withdraw', 'undetermined'}:
                errors.append('판단 변경의 종류를 명시하세요.')
    except (KeyError, TypeError, AttributeError) as error:
        errors.append('연구 답변 형식이 올바르지 않습니다: ' + str(error))
    return {'status': 'VALID' if not errors else 'INVALID', 'errors': errors,
            'engineering_qualification': 'UNKNOWN'}


def match_result_citation(citation, receipts):
    """Resolve one flat marker against actual task reads, without reading data."""
    if not isinstance(citation, dict) or 'reference' in citation:
        return None
    matches = []
    for receipt in receipts:
        if receipt.get('kind') != 'result':continue
        ref = receipt['source_ref']
        if 'run_id' in citation:
            channels = [row['response'] for row in receipt['returned_selector'].get('channels', [])]
            if citation['run_id'] != ref.get('job_id') or citation.get('response_selection') != channels:continue
        elif any(citation.get(key) != ref.get(key) for key in (
                'document_id', 'job_id', 'input_revision', 'input_sha256', 'result_sha256')):continue
        if 'selector' in citation and citation['selector'] != receipt['returned_selector']:continue
        if 'read_receipt_id' in citation and citation['read_receipt_id'] != receipt['id']:continue
        matches.append(receipt)
    return matches[0] if len(matches) == 1 else None


def source_closure(team_record):
    """Declared exact references, including uncited supplied inputs; no fetch."""
    references = {}
    dependencies = team_record.get('dependencies', {})
    rows = dependencies.values() if isinstance(dependencies, dict) else dependencies
    for dependency in rows:
        ref = dependency.get('exact_ref')
        if isinstance(ref, dict) and dependency.get('kind') in {'knowledge', 'literature', 'result'}:
            references[canonical_hash(ref)] = deepcopy(ref)
    for receipt in team_record.get('read_receipts', {}).values():
        ref = receipt.get('source_ref')
        if isinstance(ref, dict):references[canonical_hash(ref)] = deepcopy(ref)
    return list(references.values())


@dataclass
class ApprovedRoleBinding:
    owner_id: str
    owner_session_id: str
    phase_id: str
    action_id: str
    attempt_id: str
    task_id: str
    actor_id: str
    role_session_id: str
    frozen_task_ref: dict
    assignment: dict
    initial_visibility: str
    budget_slice: Any
    permitted_source_refs: list
    result_selections: list
    current_scope_probe: Callable
    generation_ledger: Any
    public_access: Any
    result_access: Any
    analysis_access: Any
    checkpoint: Callable
    control_status: Callable

    def _call(self, name, *args, **kwargs):
        from .assist.research_evidence import RoleBindingMethods
        return getattr(RoleBindingMethods, name)(self, *args, **kwargs)

    def tool_parameters(self, name, legacy_schema):return self._call('tool_parameters', name, legacy_schema)
    def prepare_history(self, session_turns):return self._call('prepare_history', session_turns)
    def prepare_consult(self, target_id, question, *, visited):return self._call('prepare_consult', target_id, question, visited=visited)
    def prepare_model_input(self, payload, *, mode, supplied_items):return self._call('prepare_model_input', payload, mode=mode, supplied_items=supplied_items)
    def prepare_tool(self, name, request, *, debit):return self._call('prepare_tool', name, request, debit=debit)
    def finish_tool(self, permit, returned_or_error):return self._call('finish_tool', permit, returned_or_error)
    def finalize_response(self, raw_response, validation):return self._call('finalize_response', raw_response, validation)
    def validation_failed(self, raw_response, errors):return self._call('validation_failed', raw_response, errors)


@dataclass
class TrustedAction:
    owner_id: str
    owner_session_id: str
    phase_id: str
    action_id: str
    attempt_id: str
    job_id: str
    frozen_request: dict
    read_checkpoint: Callable
    checkpoint: Callable
    control_status: Callable
    make_role_binding: Callable
    public_access: Any
    result_access: Any
    analysis_access: Any
