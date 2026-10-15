"""Research-team phases/checkpoints owned by existing DiscussionDocuments(X)."""
from copy import deepcopy
from dataclasses import dataclass
import json
import uuid

from .storage import canonical_hash, check_id, load_json, save_json, utc_now
from .research_team_contract import (VERSION, VARIANT, TrustedAction,
    ApprovedRoleBinding, enabled, validate_draft, FINISHED_TASKS)


def _id(prefix):return prefix + uuid.uuid4().hex


def empty_state():
    return {'version': VERSION, 'revision': 0, **{key: {} for key in (
        'phases', 'tasks', 'actions', 'attempts', 'responses', 'projections',
        'map_pending', 'map_checkpoints', 'dependencies', 'manifests',
        'read_receipts', 'outputs', 'assets', 'result_verifications', 'public_search_ledgers')}}


def retain_result_verification(owner, document, receipt):
    """Explicit UI attachment only; callers capture using C's real reader first."""
    from .evaluation import file_hash
    reference = receipt['reference']
    identifier = 'V' + canonical_hash(receipt)[:40]
    path = owner._folder(document['id']) / 'research-team' / 'inputs' / (identifier + '.json')
    save_json(path, receipt)
    ref = {'path': path.relative_to(owner._folder(document['id'])).as_posix(), 'sha256': file_hash(path)}
    team = document['discussion'].setdefault('research_team', empty_state())
    team['assets'][identifier] = ref
    team['result_verifications'][canonical_hash(reference)] = ref
    return deepcopy(ref)


def normalize_update(current, proposed_draft, *, command_id=None):
    proposed = deepcopy(proposed_draft)
    if not enabled(proposed):return proposed
    team = proposed['context']['research_team']
    context = current.get('draft', current).get('context')
    previous = context.get('research_team', {}) if isinstance(context, dict) else {}
    if not isinstance(previous, dict):previous = {}
    if team.get('phase_id') is None:
        team['parent_phase_id'] = previous.get('phase_id')
        team['phase_id'] = ('P' + canonical_hash({'document': current.get('id'), 'command': command_id})[:32]
                           if command_id is not None else _id('P'))
    return proposed


def acknowledge_unresolved(owner, identifier, arguments, *, session_id, expected_generation, command_id=None):
    """Explicit local human decision; no job, result, scope grant or inference."""
    if session_id != owner.session_id:raise ValueError('Document session is stale; reopen the document')
    if type(expected_generation) is not int or expected_generation < 0:raise ValueError('An exact input generation is required')
    if not isinstance(arguments, dict) or set(arguments) != {'task_id', 'reason'}:
        raise ValueError('미해결로 남길 과제와 사유를 입력하세요.')
    check_id(arguments['task_id'])
    reason = arguments['reason']
    if not isinstance(reason, str) or not reason.strip() or len(reason) > 4000:
        raise ValueError('미해결로 남기는 사유를 4,000자 이내로 입력하세요.')
    identifier = check_id(identifier); command_id = check_id(command_id or _id('C'))
    operation = 'expert.acknowledge_unresolved'
    signature = canonical_hash(dict(document_id=identifier, operation=operation, arguments=arguments,
                                   session_id=session_id, expected_generation=expected_generation))
    with owner._lock(identifier):
        owner.read(identifier)
        document = deepcopy(owner._documents[identifier])
        path = owner._folder(identifier) / 'commands' / (command_id + '.json')
        if path.exists():
            prior = load_json(path)
            if prior['request_hash'] != signature:raise ValueError('command_id conflicts with an earlier request')
            if prior.get('response') is not None:return deepcopy(prior['response'])
            if command_id in document.get('_expert_applied_commands', []):
                response = {'command_id': command_id, 'document': owner._public(document), 'recovered_after_response_loss': True}
                save_json(path, {'request_hash': signature, 'response': response}); return response
            raise ValueError('Previous command outcome is unconfirmed; reread before a new command')
        if document['generation'] != expected_generation:raise ValueError('Document generation changed; reread before applying')
        if not enabled(document['draft']):raise ValueError('현재 연구팀 단계의 과제만 선택하세요.')
        team = document['discussion'].get('research_team', {})
        phase_id = document['draft']['context']['research_team'].get('phase_id')
        task = team.get('tasks', {}).get(arguments['task_id'])
        phase = team.get('phases', {}).get(phase_id)
        if task is None or phase is None or task['phase_id'] != phase_id or task['id'] not in phase['task_ids']:
            raise ValueError('현재 단계의 실제 과제를 선택하세요.')
        if task['actor_id'] not in {row['expert_id'] for row in document['draft']['context']['research_team']['assignments']}:
            raise ValueError('현재 배정된 담당자의 과제만 선택하세요.')
        from .portable_research_owner import live_rounds
        local = [row for row in live_rounds(document) if row.get('protocol_request', {}).get('phase_id') == phase_id]
        if not local or not any(team['actions'][row['protocol_request']['action_id']]['origin'] == 'local' for row in local):
            raise PermissionError('보관한 원 사본의 과제를 현지 완료로 바꾸지 않습니다.')
        if any(row['status'] in {'READY', 'RUNNING'} for row in local):
            raise ValueError('현재 실행을 마치고 정리 상태를 확인한 뒤 변경하세요.')
        allowed = {'PENDING', 'WAITING_BUDGET', 'WAITING_TIME', 'WAITING_FINAL', 'WAITING_REPAIR', 'BLOCKED_SCOPE'}
        if task['status'] not in allowed or (task.get('continuation') or {}).get('cleanup_unconfirmed'):
            raise ValueError('실행 중이거나 결과·정리가 미확인인 과제, 완료한 과제는 변경할 수 없습니다.')
        previous = task['status']
        task['acknowledgement'] = {'reason': reason.strip(), 'previous_status': previous,
                                   'command_id': command_id, 'created_utc': utc_now()}
        task['status'] = 'ACKNOWLEDGED_UNRESOLVED'
        phase['initial_barrier'] = 'OPEN' if all(team['tasks'][key]['status'] in FINISHED_TASKS
                                               for key in phase['initial_task_ids']) else 'CLOSED'
        save_json(path, {'request_hash': signature, 'operation': operation, 'state': 'APPLYING'})
        document.setdefault('_expert_applied_commands', []).append(command_id)
        owner._changed(document); owner._persist_draft(document); owner._documents[identifier] = document
        response = {'command_id': command_id, 'document': owner._public(document)}
        save_json(path, {'request_hash': signature, 'response': response})
        return response


def _task(phase_id, actor, kind, question, priority, depends=()):
    return {'id': _id('T'), 'phase_id': phase_id, 'actor_id': actor, 'kind': kind,
        'priority': priority, 'depends_on': list(depends), 'target_turn_id': None,
        'target_claim_id': None, 'question_ref': {'text': question},
        'input_snapshot_ref': None, 'status': 'PENDING',
        'completed_response_id': None, 'continuation': None}


def start_record(owner, document, command_id, *, action, turn=None):
    from .portable_research_owner import live_rounds
    draft = deepcopy(document['draft'])
    errors = validate_draft(draft, owner.list_experts())
    if errors:raise ValueError(errors[0]['message'])
    if document['discussion']['paused']:raise ValueError('일시 정지를 해제한 뒤 계속하세요.')
    team_draft = draft['context']['research_team']
    phase_id = team_draft.get('phase_id') or _id('P')
    team_draft['phase_id'] = phase_id
    document['draft']['context']['research_team']['phase_id'] = phase_id
    team = document['discussion'].setdefault('research_team', empty_state())
    phase = team['phases'].get(phase_id)
    previous = [row for row in live_rounds(document) if row.get('protocol_request', {}).get('variant') == VARIANT]
    if action != 'start' and phase is None:raise ValueError('먼저 현재 연구 단계를 시작하세요.')
    if phase is None:
        initial = []
        for index, assignment in enumerate(team_draft['assignments']):
            if assignment['mode'] == 'coordinator':continue
            # No-data problem framing remains useful; it asserts no evidence read.
            kind = 'INITIAL_RESEARCH' if assignment['tools'] else 'PROBLEM_DEFINITION'
            task = _task(phase_id, assignment['expert_id'], kind, assignment['question'], index)
            team['tasks'][task['id']] = task; initial.append(task['id'])
        if not initial:raise ValueError('실제 조사 담당을 한 명 이상 선택하세요.')
        investigators = [row for row in team_draft['assignments'] if row['mode'] == 'investigator']
        q = _task(phase_id, investigators[-1]['expert_id'], 'QUESTION', '실제 주장에 판별 가능한 질문을 하세요.', 100, initial)
        a = _task(phase_id, investigators[0]['expert_id'], 'ANSWER', '질문에 근거를 읽고 판단을 유지하거나 수정하세요.', 101, [q['id']])
        team['tasks'].update({q['id']: q, a['id']: a})
        phase = {'id': phase_id, 'parent_id': team_draft.get('parent_phase_id'),
            'frozen_draft_ref': {'input_revision': document['input_revision'], 'sha256': canonical_hash(draft)},
            'assignments': deepcopy(team_draft['assignments']), 'initial_task_ids': initial,
            'initial_barrier': 'CLOSED', 'task_ids': initial + [q['id'], a['id']],
            'shared_turn_ids': [], 'current_map_revision': None, 'review_status': 'RESEARCHING',
            'turn_limit': team_draft['turn_limit'], 'objective': team_draft['objective'],
            'initial_user_turn_id': (turn or {}).get('id')}
        team['phases'][phase_id] = phase
    elif canonical_hash(phase['assignments']) != canonical_hash(team_draft['assignments']):
        raise ValueError('배정이 바뀌었습니다. 다음 연구 단계를 명시 작성하세요.')
    requested = team_draft.get('requested_next')
    if requested is not None and action not in {'retry', 'report'}:
        authored_turn = turn or next((row for row in reversed(document['discussion']['turns'])
                                    if row.get('author') == 'user'), {})
        authored = draft['composer']['text'].strip() or authored_turn.get('text', '')
        digest = canonical_hash({'selection': requested, 'user_turn_id': authored_turn.get('id'), 'text': authored})
        selected = phase.setdefault('requested_tasks', {}).get(digest)
        if selected is None:
            task_id = requested.get('task_id')
            target_turn = requested.get('target_turn_id')
            target_claim = requested.get('target_claim_id')
            target = next((row for row in team['responses'].values()
                           if 'A' + row['id'] == target_turn and row['phase_id'] == phase_id), None)
            if target_turn is not None and target is None:raise ValueError('다음 질문의 원 발언을 현재 연구 단계에서 찾을 수 없습니다.')
            if target_claim is not None and (target is None or not any(
                    claim['id'] == target_claim for claim in target.get('claim_refs', []))):
                raise ValueError('선택한 주장이 원 발언에 없습니다.')
            if task_id is not None:
                task = team['tasks'].get(task_id)
                if task is None or task['phase_id'] != phase_id or task['actor_id'] != requested['expert_id']:
                    raise ValueError('현재 단계의 실제 담당 과제를 선택하세요.')
                if task['status'] in FINISHED_TASKS:raise ValueError('완료한 과제를 다시 호출하지 않습니다.')
            else:
                task = _task(phase_id, requested['expert_id'], 'ANSWER',
                    authored or '사용자가 선택한 주장에 판별 가능한 질문을 하세요.', -1, phase['initial_task_ids'])
                task['user_question'] = True
                team['tasks'][task['id']] = task; phase['task_ids'].append(task['id'])
            task.update(priority=-1, target_turn_id=target_turn, target_claim_id=target_claim)
            task['explicit_target'] = target_turn is not None
            phase['requested_tasks'][digest] = task['id']
    # The editor clears its composer after Ask. Progression still submits the
    # immutable phase question, without rewriting that current editor buffer.
    if not draft['composer']['text'].strip():draft['composer']['text'] = phase['objective']
    if action == 'retry':
        source = next((row for row in reversed(previous) if row['protocol_request']['phase_id'] == phase_id), None)
        if source is None:raise ValueError('다시 시도할 현지 작업이 없습니다.')
        action_id = source['protocol_request']['action_id']
        if team['actions'][action_id]['origin'] != 'local':raise PermissionError('원 사본의 실행 권한을 재사용하지 않습니다.')
    else:action_id = _id('D')
    attempt_id, round_id = _id('A'), _id('B')
    actor = draft['participants'][0]
    record = {'id': round_id, 'command_id': command_id, 'protocol': 'costorm',
        'user_turn_id': phase['initial_user_turn_id'] or (turn or {}).get('id'),
        'roles': [actor], 'participants': deepcopy(draft['participants']),
        'sessions': {actor: _id('E')}, 'next_index': 0, 'active_job_id': None,
        'status': 'READY', 'draft': draft, 'knowledge_sources': deepcopy(draft['context'].get('selected_sources', [])),
        'input_generation': document['generation'], 'input_revision': document['input_revision'],
        'history': [], 'previous_job_id': None,
        'protocol_request': {'variant': VARIANT, 'document_id': document['id'], 'round_id': round_id,
            'action': action, 'phase_id': phase_id, 'action_id': action_id, 'attempt_id': attempt_id,
            'roles': deepcopy(draft['participants']), 'evidence': deepcopy(draft['composer']['evidence'])}}
    team['actions'].setdefault(action_id, {'id': action_id, 'phase_id': phase_id, 'origin': 'local',
        'kind': action, 'command_id': command_id, 'job_id': None, 'prepared_arguments_digest': None,
        'allocation_plan': None, 'task_ids': [], 'checkpoint_revision': 0, 'search_ledger_id': 'L' + action_id})
    team['attempts'][attempt_id] = {'id': attempt_id, 'action_id': action_id,
        'job_id': None, 'command_id': command_id, 'budget_limit': deepcopy(draft['budget']),
        'reservations': [], 'observed_tool_calls': [], 'observed_host_invocations': [],
        'started_at': utc_now(), 'terminal_state': None}
    document['discussion']['rounds'].append(record)
    return record


@dataclass
class _OwnerBinding:
    owner: object
    owner_id: str
    owner_session_id: str
    record_id: str
    job_id: str
    arguments_digest: str


def _current(binding, *, writing=False):
    owner = binding.owner
    if owner.session_id != binding.owner_session_id:raise PermissionError('연구 서비스가 바뀌었습니다.')
    document = owner._documents[binding.owner_id]
    record = next(row for row in document['discussion']['rounds'] if row['id'] == binding.record_id)
    from .portable_research_owner import assert_live
    assert_live(document, record)
    if record.get('active_job_id') not in (None, binding.job_id):raise PermissionError('다른 작업이 이 단계를 소유합니다.')
    if writing and record['status'] not in {'READY', 'RUNNING'}:
        raise PermissionError('이미 종료한 연구 작업에 새 사건을 쓸 수 없습니다.')
    action = document['discussion']['research_team']['actions'][record['protocol_request']['action_id']]
    if writing and action.get('job_id') not in (None, binding.job_id):
        raise PermissionError('다른 현지 attempt가 이 action을 소유합니다.')
    # manager metadata is checked on authorization; checkpoints need no result
    # reader, network, recovery or a recursive owner.read call.
    return document, record


def _checkpoint_path(binding):
    return binding.owner._folder(binding.owner_id) / 'research-team' / check_id(binding.record_id) / 'action.json'


def read_checkpoint(binding):
    with binding.owner._lock(binding.owner_id):
        document, record = _current(binding)
        path = _checkpoint_path(binding)
        if path.exists():
            saved = load_json(path)
            if saved['arguments_digest'] != binding.arguments_digest:raise PermissionError('고정 요청이 다릅니다.')
            return deepcopy(saved['team'])
        return deepcopy(document['discussion']['research_team'])


def checkpoint(binding, *, expected_revision, event_id, payload):
    """Short existing-owner lock + atomic JSON/CAS, never provider/network I/O."""
    owner = binding.owner
    with owner._lock(binding.owner_id):
        document, record = _current(binding, writing=True)
        path = _checkpoint_path(binding)
        prior = load_json(path) if path.exists() else {'revision': 0, 'events': {},
            'team': deepcopy(document['discussion']['research_team']), 'arguments_digest': binding.arguments_digest}
        if prior['arguments_digest'] != binding.arguments_digest:raise PermissionError('원 제출 요청이 다릅니다.')
        digest = canonical_hash(payload)
        if event_id in prior['events']:
            event = prior['events'][event_id]
            if event['digest'] != digest:raise ValueError('같은 checkpoint 사건에 다른 내용을 쓸 수 없습니다.')
            return deepcopy(event['receipt'])
        if prior['revision'] != expected_revision:raise ValueError('연구 checkpoint가 바뀌었습니다. 다시 읽으세요.')
        team = deepcopy(prior['team']); receipt = {'revision': expected_revision + 1}
        if 'asset' in payload:
            asset = payload['asset']; identifier = check_id(asset['id']); value = asset['payload']
            from .portable_project_io import MAX_JSON_BYTES
            if len(json.dumps(value, ensure_ascii=False, allow_nan=False).encode('utf-8')) > MAX_JSON_BYTES:
                raise ValueError('기존 연구 asset JSON 상한을 초과했습니다.')
            asset_path = path.parent / 'assets' / (identifier + '.json')
            if asset_path.exists() and canonical_hash(load_json(asset_path)) != canonical_hash(value):
                raise ValueError('이미 보존한 원 asset을 바꾸지 않습니다.')
            save_json(asset_path, value)
            import hashlib
            ref = {'path': asset_path.relative_to(owner._folder(binding.owner_id)).as_posix(),
                   'sha256': hashlib.sha256(asset_path.read_bytes()).hexdigest()}
            team['assets'][identifier] = ref; receipt['asset_ref'] = ref
        if 'state' in payload:
            incoming = deepcopy(payload['state'])
            if incoming.get('version') != VERSION:raise ValueError('연구 기록의 계약판이 다릅니다.')
            # The worker cannot replace authenticated action identity/dispatch.
            action_id = record['protocol_request']['action_id']
            if incoming['actions'][action_id]['origin'] != 'local':raise PermissionError('원 action은 실행하지 않습니다.')
            team = incoming
        for key in ('dependencies', 'manifests', 'read_receipts', 'outputs'):
            if key in payload:team[key].update(deepcopy(payload[key]))
        action_id, attempt_id = (record['protocol_request'][key] for key in ('action_id', 'attempt_id'))
        attempt = team['attempts'][attempt_id]
        if 'public_search_ledger' in payload:
            team['public_search_ledgers'][action_id] = deepcopy(payload['public_search_ledger'])
        if 'response' in payload:
            response = payload['response']
            if response['phase_id'] != record['protocol_request']['phase_id']:
                raise PermissionError('다른 연구 단계의 응답입니다.')
            team['responses'][response['id']] = deepcopy(response)
        for key, target in [('reservation', 'reservations'), ('debit', 'observed_tool_calls'),
                            ('observed_host_invocation', 'observed_host_invocations')]:
            if key in payload:attempt[target].append(deepcopy(payload[key]))
        if 'allocation_plan' in payload:
            plan = payload['allocation_plan']
            team['actions'][action_id]['allocation_plan'] = deepcopy(plan)
            if record['protocol_request']['action'] != 'retry':
                team['actions'][action_id]['task_ids'] = [row['task_id'] for row in plan['tickets'] if row['task_id']]
        if 'map_commit' in payload:
            commit = payload['map_commit']; phase = team['phases'][record['protocol_request']['phase_id']]
            if phase['current_map_revision'] != commit['previous_revision']:
                raise ValueError('승인 지도 개정이 바뀌었습니다.')
            pending = team['map_pending'][commit['pending_id']]
            if pending['status'] == 'APPLIED':raise ValueError('이미 반영한 지도입니다.')
            team['map_checkpoints'][commit['id']] = deepcopy(commit['checkpoint'])
            phase['current_map_revision'] = commit['id']
            pending.update(status='APPLIED', applied_map_revision=commit['id'])
        team['revision'] = receipt['revision']; team['actions'][action_id]['checkpoint_revision'] = receipt['revision']
        prior.update(team=team, revision=receipt['revision'])
        prior['events'][event_id] = {'digest': digest, 'receipt': receipt}
        # Existing bounded owner assets; callables/runtime/credentials must fail
        # JSON encoding before publication rather than being stringified.
        from .portable_project_io import MAX_JSON_BYTES
        if len(json.dumps(prior, ensure_ascii=False, allow_nan=False).encode('utf-8')) > MAX_JSON_BYTES:
            raise ValueError('기존 연구 JSON 보존 상한을 초과했습니다.')
        save_json(path, prior)
        document['discussion']['research_team'] = team
        owner._persist_draft(document)
        return deepcopy(receipt)


def resolve_asset(binding, ref):
    from .portable_project_io import inside
    from .evaluation import file_hash
    root = binding.owner._folder(binding.owner_id)
    path = inside(root, ref['path'])
    if file_hash(path) != ref['sha256']:raise ValueError('보존 연구 원문이 바뀌었습니다.')
    return load_json(path)


def authorize(owner, arguments, job_id):
    spec = arguments.get('context', {}).get('costorm', {})
    if spec.get('variant') != VARIANT:raise PermissionError('현재 owner의 연구팀 요청이 아닙니다.')
    identifier = check_id(spec.get('document_id'))
    with owner._lock(identifier):
        owner.read(identifier); document = owner._documents[identifier]
        record = next((row for row in document['discussion']['rounds'] if row['id'] == spec.get('round_id')), None)
        if record is None:raise PermissionError('연구 단계가 현재 문서에 없습니다.')
        from .portable_research_owner import assert_live
        assert_live(document, record)
        job = owner.manager.status(job_id)
        expected = record.get('prepared_arguments') or owner._arguments(document, record, record['roles'][0])
        if (job.get('operation') != 'experts.ask' or job.get('request_id') != owner._request_id(document, record)
                or canonical_hash(job['arguments']) != canonical_hash(arguments)
                or canonical_hash(expected) != canonical_hash(arguments)
                or record.get('active_job_id') not in (None, job_id)):
            raise PermissionError('원 제출 입력과 현재 연구 작업이 다릅니다.')
        bound = _OwnerBinding(owner, identifier, owner.session_id, record['id'], job_id, canonical_hash(arguments))
        for key in ('actions', 'attempts'):
            row_id = spec['action_id' if key == 'actions' else 'attempt_id']
            document['discussion']['research_team'][key][row_id]['job_id'] = job_id
        document['discussion']['research_team']['actions'][spec['action_id']]['prepared_arguments_digest'] = canonical_hash(arguments)

    def save(event_id, payload):
        path = _checkpoint_path(bound)
        with owner._lock(identifier):
            revision = load_json(path)['revision'] if path.exists() else 0
            return checkpoint(bound, expected_revision=revision, event_id=event_id, payload=payload)
    def control():
        with owner._lock(identifier):
            current, _ = _current(bound)
            authored = current['draft']['context'].get('research_team', {})
            return {'owner_id': identifier, 'owner_session_id': owner.session_id,
                'phase_id': spec['phase_id'], 'paused': current['discussion']['paused'],
                'intervened': any(row.get('author') == 'user' and row.get('input_generation', -1) > record['input_generation']
                                 for row in current['discussion']['turns']),
                'context': deepcopy(current['draft']['context']),
                'assignments': {row['expert_id']: deepcopy(row) for row in authored.get('assignments', [])}}
    trusted = TrustedAction(identifier, owner.session_id, spec['phase_id'], spec['action_id'],
        spec['attempt_id'], job_id, deepcopy(arguments), lambda: read_checkpoint(bound),
        save, control, None, None, None, None)
    # Binding factory implementation is A's role runtime; tools/inputs belong B.
    def make(task, budget_slice, *, runtime, workspace_id):
        from .assist.research_evidence import GenerationLedger, role_context, shared_projection
        state = trusted.read_checkpoint(); phase = state['phases'][trusted.phase_id]
        assignment = next(row for row in phase['assignments'] if row['expert_id'] == task['actor_id'])
        visibility = 'independent' if task['id'] in phase['initial_task_ids'] else 'shared'
        scope = control(); scope.update(ledger_state=state, resolve_payload=lambda ref: resolve_asset(bound, ref))
        accepted = [deepcopy(row) for row in state['responses'].values() if row['phase_id'] == phase['id']]
        prepared = role_context(assignment, record['draft'], runtime=runtime,
            workspace_id=workspace_id, visibility=visibility, accepted_responses=[] if visibility == 'independent' else accepted)
        role_context_value = prepared['context']
        ids = {'owner_id': identifier, 'phase_id': phase['id'], 'task_id': task['id'],
               'actor_id': task['actor_id'], 'attempt_id': trusted.attempt_id}
        ledger = GenerationLedger(ids, runtime=runtime, workspace_id=workspace_id,
            context=role_context_value, checkpoint=save, state=state)
        ledger.context['citation_rule'] = 'Use [n] only for the nth exact entry in answer.sources, starting at 1. Do not number sources by tool/read order.'
        role_session = 'E' + canonical_hash({'owner': identifier, 'phase': phase['id'], 'task': task['id']})[:40]
        binding = ApprovedRoleBinding(identifier, owner.session_id, phase['id'], trusted.action_id,
            trusted.attempt_id, task['id'], task['actor_id'], role_session,
            deepcopy(task), deepcopy(assignment), visibility, budget_slice,
            deepcopy(assignment['source_refs']), deepcopy(assignment['result_refs']),
            lambda: {**control(), 'ledger_state': trusted.read_checkpoint(),
                     'resolve_payload': lambda ref: resolve_asset(bound, ref)},
            ledger, trusted.public_access, trusted.result_access, trusted.analysis_access, save, control)
        ledger.add_supplied({'kind': 'authored', 'exact_ref': {'task_id': task['id']},
            'payload': deepcopy(task['question_ref'])}, dependencies=[], origin='prompt')
        def consult(target_id, question, *, caller, dependency_ids):
            from .assist.research_team import BudgetSlice
            plan = budget_slice.root._team_plan
            ticket = next((row for row in plan['tickets'] if row.get('consult_parent') == task['id']
                           and row['actor_id'] == target_id), None)
            if ticket is None or ticket['status'] != 'PENDING':raise PermissionError('자문 대상의 별도 처리 몫이 없습니다.')
            current = trusted.read_checkpoint(); target = current['tasks'][ticket['task_id']]
            target['question_ref'] = {'text': question, 'caller_task_id': task['id']}
            current['tasks'][target['id']] = target
            save('consult-question-' + target['id'], {'state': current})
            result = make(target, BudgetSlice(budget_slice.root, ticket), runtime=runtime, workspace_id=workspace_id)
            result.generation_ledger.context['consult_experts'] = []
            result.generation_ledger.context['research_task'] = deepcopy(target)
            result.generation_ledger.add_supplied({'kind': 'tool_output',
                'exact_ref': {'caller_task_id': task['id']}, 'payload': question},
                dependencies=dependency_ids, origin='consultation')
            def completed(response):
                latest = trusted.read_checkpoint(); raw = response.get('research_response')
                row = latest['tasks'][target['id']]
                if raw:
                    raw = deepcopy(raw)
                    raw['proposal_refs'] = [{'response_id': raw['id'], 'proposal_index': index,
                        'sha256': canonical_hash(proposal)} for index, proposal in enumerate(response.get('proposed_actions', []))]
                    raw['claim_refs'] = [{'id': 'C' + canonical_hash({'response': raw['id'], 'index': i})[:32],
                        'index': i, 'response_id': raw['id']} for i, _ in enumerate(response.get('research_reply', {}).get('claims', []))]
                    latest['responses'][raw['id']] = deepcopy(raw)
                    valid = raw['validation'].get('status') == 'VALID' and response.get('status') == 'ANSWERED'
                    row.update(status='COMPLETED' if valid else 'WAITING_REPAIR',
                               completed_response_id=raw['id'] if valid else None)
                else:row['status'] = 'OUTCOME_UNCONFIRMED'
                save('consult-complete-' + target['id'] + '-' + trusted.attempt_id, {'state': latest})
                ticket['status'] = 'FINISHED'; result.budget_slice.active = False
            result.complete_consult = completed
            return result
        original_probe = binding.current_scope_probe
        binding.current_scope_probe = lambda: {**original_probe(), 'make_consult_binding': consult}
        available = [row['actor_id'] for row in budget_slice.root._team_plan['tickets']
                     if row.get('consult_parent') == task['id']]
        ledger.context['consult_experts'] = available
        for item in prepared.get('supplied_items', []):
            ledger.add_supplied(item, dependencies=prepared.get('dependency_ids', []), origin='prompt')
        inherited = []
        for turn_id in record['draft']['context']['research_team']['carry_forward_turn_ids']:
            source_turn = next((row for row in document['discussion']['turns'] if row['id'] == turn_id), None)
            if source_turn is None:raise PermissionError('이어갈 원 발언을 찾을 수 없습니다.')
            if source_turn.get('research_response_id'):
                original = state['responses'][source_turn['research_response_id']]
                if visibility == 'independent' and original['phase_id'] == phase['id']:
                    raise PermissionError('현재 단계의 독립 조사에 같은 단계의 다른 결론을 넣지 않습니다. 새 단계를 작성하세요.')
            elif source_turn.get('research_action_id'):
                original = state['actions'][source_turn['research_action_id']]['report']
            elif source_turn.get('author') == 'user':
                original = {'answer': source_turn['text'], 'dependency_ids': source_turn.get('dependency_ids', [])}
                if not original['dependency_ids']:
                    ledger.add_supplied({'kind': 'authored', 'exact_ref': {'turn_id': turn_id},
                        'payload': original}, dependencies=[], origin='prompt')
                    inherited.append({'turn_id': turn_id, 'response': original}); continue
            else:raise PermissionError('생성 의존성이 확인된 원 발언을 선택하세요.')
            checked = shared_projection(original, [task['actor_id']], runtime=runtime,
                workspace_id=workspace_id, current_scope={**scope, 'result_access': trusted.result_access})
            if checked['status'] != 'AVAILABLE':raise PermissionError('이어갈 원 발언의 현재 자료 범위를 확인하세요.')
            ledger.add_supplied({'kind': 'response', 'exact_ref': {'turn_id': turn_id},
                'payload': checked['projection']}, dependencies=checked['dependency_ids'], origin='forwarded_turn')
            inherited.append({'turn_id': turn_id, 'response': deepcopy(checked['projection'])})
        if inherited:ledger.context['selected_prior_turns'] = inherited
        target_id = task.get('question_ref', {}).get('response_id')
        if target_id:
            target = state['responses'][target_id]
            scope.update(result_access=trusted.result_access)
            projected = shared_projection(target, [task['actor_id']], runtime=runtime,
                workspace_id=workspace_id, current_scope=scope)
            if projected['status'] != 'AVAILABLE':raise PermissionError('대상 발언을 현재 담당자에게 전달할 수 없습니다.')
            ledger.add_supplied({'kind': 'response', 'exact_ref': {'response_id': target_id},
                'payload': projected['projection']}, dependencies=projected['dependency_ids'], origin='forwarded_turn')
            ledger.context['target_response'] = deepcopy(projected['projection'])
        if task['input_snapshot_ref'] is None:
            snapshot = {'task': deepcopy(task), 'assignment': deepcopy(assignment), 'context': deepcopy(ledger.context)}
            snapshot_id = 'I' + canonical_hash(snapshot)[:40]
            reference = save('input-asset-' + snapshot_id, {'asset': {'id': snapshot_id, 'payload': snapshot}})['asset_ref']
            current = trusted.read_checkpoint(); current['tasks'][task['id']]['input_snapshot_ref'] = reference
            save('task-input-' + task['id'], {'state': current})
        return binding
    trusted.make_role_binding = make
    trusted.resolve_payload = lambda ref: resolve_asset(bound, ref)
    def verification(reference):
        team = trusted.read_checkpoint()
        ref = team['result_verifications'].get(canonical_hash(reference))
        if ref is None:raise PermissionError('정확 결과의 명시 첨부 검증 기록이 없습니다.')
        value = resolve_asset(bound, ref)
        if value['reference'] != reference:raise PermissionError('첨부한 원 결과 참조가 다릅니다.')
        return value
    trusted.lookup_result_verification = verification
    trusted.current_scope_probe = lambda: {**control(), 'ledger_state': trusted.read_checkpoint(),
        'resolve_payload': trusted.resolve_payload, 'result_access': trusted.result_access}
    return {'request': deepcopy(spec), 'team_action': trusted}


def reconcile_checkpoint(binding):
    """Pure deterministic owner collection, never a new role/step/model call."""
    state = binding.read_checkpoint()
    return {'revision': state['revision'], 'state': state,
        'completed_task_ids': [row['id'] for row in state['tasks'].values() if row['status'] in FINISHED_TASKS]}


def collect(owner, document, record, run, response, state):
    """Read actual local checkpoint first, even when its outer job failed."""
    bound = _OwnerBinding(owner, document['id'], owner.session_id, record['id'], run['job_id'], canonical_hash(run['arguments']))
    path = _checkpoint_path(bound)
    if path.exists():
        saved = load_json(path)
        if saved['arguments_digest'] != bound.arguments_digest:raise ValueError('연구 결과의 원 입력이 다릅니다.')
        document['discussion']['research_team'] = deepcopy(saved['team'])
    team = document['discussion']['research_team']
    existing = {row.get('research_response_id') for row in document['discussion']['turns']}
    for role_response in team['responses'].values():
        if role_response['id'] in existing:continue
        raw = resolve_asset(bound, role_response['raw_response_ref'])
        document['discussion']['turns'].append({'id': 'A' + role_response['id'],
            'author': role_response['actor_id'], 'research_response_id': role_response['id'],
            'research_phase_id': role_response['phase_id'], 'status': raw.get('status'),
            'text': raw.get('answer'), 'response': raw, 'classification': 'expert_reply',
            'topic_id': record['draft']['composer']['topic_id'],
            'topic': deepcopy(next(row for row in record['draft']['topics'] if row['id'] == record['draft']['composer']['topic_id'])), 'reply_to': record['user_turn_id'],
            'round_id': record['id'], 'job_id': run['job_id'], 'job_state': state,
            'created_utc': utc_now(), 'input_generation': record['input_generation'],
            'input_revision': record['input_revision'], 'input_sha256': canonical_hash(record['draft']),
            'evidence': [], 'knowledge_sources': deepcopy(record['knowledge_sources'])})
    # A report is an actual saved derivation of the approved map, not another
    # expert response. Expose it through the existing expert_turn reference.
    action_id = record['protocol_request']['action_id']
    report = team['actions'][action_id].get('report')
    if report and report.get('status') == 'APPLIED':
        turn_id = 'F' + action_id
        if not any(row['id'] == turn_id for row in document['discussion']['turns']):
            original = resolve_asset(bound, report['body_ref'])
            document['discussion']['turns'].append({'id': turn_id, 'author': record['roles'][0],
                'research_action_id': action_id, 'research_phase_id': record['protocol_request']['phase_id'],
                'status': 'ANSWERED', 'text': original['text'],
                'response': {'status': 'ANSWERED', 'answer': original['text'], 'sources': [],
                    'proposed_actions': [], 'costorm': {'report': deepcopy(original)},
                    'dependency_ids': deepcopy(report['dependency_ids']),
                    'input_manifest_ids': deepcopy(report.get('input_manifest_ids', []))},
                'dependency_ids': deepcopy(report['dependency_ids']),
                'input_manifest_ids': deepcopy(report.get('input_manifest_ids', [])),
                'classification': 'expert_reply', 'topic_id': record['draft']['composer']['topic_id'],
                'topic': deepcopy(next(row for row in record['draft']['topics'] if row['id'] == record['draft']['composer']['topic_id'])), 'reply_to': record['user_turn_id'],
                'round_id': record['id'], 'job_id': run['job_id'], 'job_state': state,
                'created_utc': utc_now(), 'input_generation': record['input_generation'],
                'input_revision': record['input_revision'], 'input_sha256': canonical_hash(record['draft']),
                'evidence': [], 'knowledge_sources': deepcopy(record['knowledge_sources'])})
    team['attempts'][record['protocol_request']['attempt_id']]['terminal_state'] = state
    record.update(active_job_id=None, completed_job_id=run['job_id'], next_index=1,
        status='COMPLETED' if response.get('status') == 'ANSWERED' else 'FAILED')
    return True
