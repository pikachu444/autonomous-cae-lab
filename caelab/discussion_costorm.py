"""Co-STORM actions use the existing discussion owner, jobs and saved revisions."""
from copy import deepcopy
import uuid
from .storage import canonical_hash, check_id, utc_now

OPERATIONS = {'expert.report', 'expert.retry'}


def enabled(document):
    return document['draft'].get('context', {}).get('discussion_mode') == 'costorm'


def records(document):
    return [row for row in document.get('discussion', {}).get('rounds', []) if row.get('protocol') == 'costorm']


def previous_response(owner, document, record):
    identifier = record.get('previous_job_id')
    if not identifier:
        return None
    prior = next((row for row in records(document) if row.get('completed_job_id') == identifier), None)
    if prior is None:
        raise ValueError('Predecessor is not a completed step of this discussion')
    run = next(row for row in document['runs'] if row['job_id'] == identifier)
    return owner._read_response(document, run)


def start_record(owner, document, command_id, *, action, turn=None):
    prior = records(document)
    if action == 'start' and prior:
        raise ValueError('이 토론은 이미 시작했습니다. 계속하기 또는 새 대화를 선택하세요.')
    if action != 'start' and not prior:
        raise ValueError('먼저 자료 토론을 시작하세요.')
    if document['discussion']['paused']:
        raise ValueError('일시 정지를 해제한 뒤 계속하세요.')
    source = prior[0] if prior else None
    frozen = deepcopy(source['draft'] if source else document['draft'])
    if source:
        if document['draft']['participants'] != frozen['participants']:
            raise ValueError('참여 역할이 달라졌습니다. 기존 토론을 보관하고 새 대화를 시작하세요.')
        for key in ('selected_sources',):
            if document['draft']['context'].get(key) != frozen['context'].get(key):
                raise ValueError('자료 또는 전송 선택이 달라졌습니다. 새 대화에서 시작하세요.')
    owner._validate_sources(frozen['context'])
    # New returned results enter only through the user's current explicit
    # attachment and per-question permission, while source revisions stay pinned.
    frozen['context']['transmission_scope'] = deepcopy(document['draft']['context'].get('transmission_scope', {}))
    frozen['composer']['evidence'] = deepcopy(document['draft']['composer']['evidence'])
    checking = deepcopy(document)
    checking['draft']['composer']['text'] = frozen['composer']['text']
    owner._validate_question(checking, needs_roles=False)
    has_results = any('job_id' in reference for reference in frozen['composer']['evidence'])
    public_search = frozen['context'].get('transmission_scope', {}).get('allow_public_search') is True
    if not frozen['context'].get('selected_sources') and not has_results and not public_search:
        raise ValueError('토론 자료나 계산 결과를 선택하거나, 공개 문헌 검색을 허용하세요.')
    previous = prior[-1].get('completed_job_id') if prior else None
    if prior and not previous:
        raise ValueError('이전 응답을 수신한 뒤 계속하세요.')
    last = None
    effective_action = action
    if previous:
        for prior_record in reversed(prior):
            candidate_job = prior_record.get('completed_job_id')
            if not candidate_job:
                continue
            run = next(row for row in document['runs'] if row['job_id'] == candidate_job)
            try:
                candidate_result = owner._read_response(document, run).get('costorm')
            except (ValueError, FileNotFoundError):
                candidate_result = None
            if candidate_result:
                previous, last = candidate_job, candidate_result
                break
        else:
            previous = None
        if action == 'retry' and not last:
            effective_action = 'start'
        elif action == 'retry' and previous != prior[-1].get('completed_job_id'):
            effective_action = prior[-1]['protocol_request']['action']
            if effective_action == 'retry':
                effective_action = 'retry' if last.get('retry') else 'step'
        elif action == 'retry' and not last.get('retry'):
            raise ValueError('다시 시도할 중단 작업이 없습니다.')
        if action != 'retry' and (not last or last.get('retry')):
            raise ValueError('중단된 작업을 먼저 다시 시도하세요.')
    consumed = set((last or {}).get('consumed_user_ids', []))
    initial_user = source['user_turn_id'] if source else turn['id']
    interventions = [{'id': item['id'], 'text': item['text'],
                      'topic_id': item['topic_id'], 'topic_title': (item.get('topic') or {}).get('title'),
                      'reply_to': item.get('reply_to'),
                      'reply_text': next((turn.get('text') for turn in document['discussion']['turns']
                                          if turn['id'] == item.get('reply_to')), None)}
        for item in document['discussion']['turns'] if item.get('author') == 'user'
        and item['id'] != initial_user and item['id'] not in consumed]
    role = frozen['participants'][0]
    record = {'id': 'B' + uuid.uuid4().hex, 'command_id': command_id, 'protocol': 'costorm',
        'user_turn_id': initial_user, 'roles': [role], 'participants': frozen['participants'],
        'sessions': deepcopy(source['sessions']) if source else {role: 'E' + uuid.uuid4().hex},
        'next_index': 0, 'active_job_id': None, 'status': 'READY',
        'draft': frozen, 'knowledge_sources': deepcopy(frozen['context'].get('selected_sources', [])),
        'input_generation': document['generation'], 'input_revision': document['input_revision'],
        'history': [], 'previous_job_id': previous,
        'protocol_request': {'document_id': document['id'], 'action': effective_action,
            'roles': deepcopy(frozen['participants']), 'previous_job_id': previous,
            'interventions': interventions, 'evidence': deepcopy(frozen['composer']['evidence'])}}
    # One explicit action authorizes one budget; polling never authorizes another.
    record['draft']['budget'] = deepcopy(document['draft']['budget'])
    record['protocol_request']['round_id'] = record['id']
    document['discussion']['rounds'].append(record)
    return record


def arguments(owner, document, record, role):
    result = owner._legacy_arguments(document, record, role)
    result['context']['discussion_mode'] = 'costorm'
    result['context']['costorm'] = deepcopy(record['protocol_request'])
    return result


def authorize(owner, arguments, job_id):
    spec = arguments.get('context', {}).get('costorm')
    if not isinstance(spec, dict):
        raise PermissionError('Missing owner protocol request')
    identifier = check_id(spec.get('document_id'))
    with owner._lock(identifier):
        owner.read(identifier)
        document = owner._documents[identifier]
        record = next((row for row in records(document) if row['id'] == spec.get('round_id')), None)
        if record is None:
            raise PermissionError('Co-STORM request does not belong to this discussion')
        job = owner.manager.status(job_id)
        if job.get('request_id') != owner._request_id(document, record):
            raise PermissionError('Co-STORM job was not submitted by its discussion owner')
        expected = record.get('prepared_arguments') or owner._arguments(document, record, record['roles'][0])
        if canonical_hash(expected) != canonical_hash(arguments):
            raise PermissionError('Co-STORM input differs from the retained owner request')
        if record.get('active_job_id') not in (None, job_id):
            raise PermissionError('Another job owns this discussion step')
        owner._validate_sources(record['draft']['context'])
        response = previous_response(owner, document, record)
        evidence = deepcopy(record['protocol_request'].get('evidence', []))
        def read_results():
            result = []
            for reference in evidence:
                if 'job_id' not in reference:
                    continue
                check = deepcopy(document)
                check['draft'] = deepcopy(record['draft'])
                owner._validate_question(check, needs_roles=False)
                payload = owner.resolve_result(reference['document_id'], reference['job_id'],
                    selection=reference.get('selection', []))
                result.append({'reference': deepcopy(reference), 'payload': payload})
            return result
        return {'request': deepcopy(record['protocol_request']),
                'previous': deepcopy((response or {}).get('costorm')), 'read_results': read_results}


def collect(owner, document, record, run, response, state):
    protocol = response.get('costorm') or {}
    if not protocol:
        # A preflight/transport failure must not erase the previously readable map/report.
        earlier = previous_response(owner, document, record) if record.get('previous_job_id') else None
        protocol = deepcopy((earlier or {}).get('costorm') or {})
    view = protocol.get('view') or {}
    existing = {item.get('protocol_index') for item in document['discussion']['turns']
                if item.get('protocol') == 'costorm'}
    for turn in view.get('turns', []):
        if turn['index'] in existing:
            continue
        citations = turn.get('citations', [])
        sources = [deepcopy(item['source']) for item in citations if item.get('source')]
        topic_ids = turn.get('topic_ids', [])
        topic = next((row for row in view.get('topics', []) if row['id'] in topic_ids), None)
        topic = {key: (topic or record['draft']['topics'][0])[key] for key in ('id', 'title', 'parent_id')}
        document['discussion']['turns'].append({
            'id': 'A' + uuid.uuid4().hex, 'author': turn['author'],
            'status': 'ANSWERED', 'text': turn['text'], 'classification': 'expert_reply',
            'protocol': 'costorm', 'protocol_index': turn['index'], 'topic_ids': topic_ids,
            'topic_id': topic['id'], 'topic': topic, 'role_description': turn.get('role_description', ''),
            'job_state': state, 'job_id': run['job_id'], 'round_id': record['id'],
            'reply_to': record['user_turn_id'], 'created_utc': utc_now(),
            'input_generation': record['input_generation'], 'input_revision': record['input_revision'],
            'input_sha256': canonical_hash(record['draft']), 'evidence': [],
            'knowledge_sources': deepcopy(record['knowledge_sources']),
            'response': {'status': 'ANSWERED', 'answer': turn['text'], 'sources': sources,
                'citations': deepcopy(citations), 'proposed_actions': []}})
    record.update(active_job_id=None, completed_job_id=run['job_id'], next_index=1,
                  status='COMPLETED' if state == 'SUCCEEDED' and response.get('status') == 'ANSWERED' else 'FAILED')
    prior = document['discussion'].get('costorm', {})
    topic_history_ids = set(prior.get('topic_history_ids', []))
    topic_history_ids.update(row['id'] for row in prior.get('topics', []))
    topic_history_ids.update(row['id'] for row in view.get('topics', []))
    document['discussion']['costorm'] = {
        'topic_history_ids': sorted(topic_history_ids),
        'topics': deepcopy(view.get('topics', [])), 'report': deepcopy(protocol.get('report')),
        'can_retry': bool(protocol.get('retry')) or response.get('status') != 'ANSWERED', 'ready': bool(protocol.get('state', {}).get('conversation_history')),
        'reason': response.get('reason'), 'usage': deepcopy(protocol.get('total_usage', {})),
        'partial_completions': len((protocol.get('retry') or {}).get('journal', [])),
        'job_id': run['job_id'], 'turn_topics': {str(turn['index']): turn['topic_ids'] for turn in view.get('turns', [])}}
    return True
