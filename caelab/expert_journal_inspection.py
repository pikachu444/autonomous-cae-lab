"""Read-only interpretation of EXISTING saved Co-STORM job results.

This is not another journal, retry implementation, or polling scheduler. Sol's
partial-response reader can keep using document_result directly. This optional
projection states explicitly what is partial, committed, and rejected.
"""
from copy import deepcopy


def inspect_journal(result, *, document_id, job_id, job_state=None, cancel_requested=False,
                    offset=0, limit=64):
    if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 256:
        raise ValueError('중간 응답의 읽기 범위를 확인하세요.')
    if not isinstance(result, dict) or not isinstance(result.get('costorm'), dict):
        raise ValueError('선택한 원 작업에는 보존된 Co-STORM journal이 없습니다.')
    protocol = result['costorm']
    retry = protocol.get('retry') or {}
    journal = retry.get('journal', [])
    if not isinstance(journal, list):
        raise ValueError('보존된 journal 형식이 올바르지 않습니다.')
    invalid = retry.get('invalid_completion_key')
    rows = []
    for index, row in enumerate(journal[offset:offset+limit], offset):
        if not isinstance(row, dict) or not all(isinstance(row.get(k), str) for k in ('key', 'prompt', 'text')):
            raise ValueError('보존된 중간 응답 항목 형식이 올바르지 않습니다.')
        excluded = invalid is not None and row['key'] == invalid
        rows.append({'index': index, 'text': row['text'], 'prompt': row['prompt'],
            'completion_key': row['key'], 'adopted_utterance': False,
            'state': 'INVALID_COMPLETION_EXCLUDED' if excluded else 'RETAINED_PARTIAL',
            # Replay still needs owner, permission, exact inputs and budget checks.
            'replay_candidate': not excluded})
    confirmed = result.get('execution_status') == 'CANCELLED'
    # A STOPPED budget result is not an acknowledgement of physical cancellation.
    stop = 'CANCEL_CONFIRMED' if confirmed else 'CANCEL_REQUESTED' if cancel_requested else (
        'ACTION_STOPPED' if result.get('status') == 'STOPPED' else 'NOT_STOPPED')
    return {'document_id': document_id, 'job_id': job_id, 'job_state': job_state,
        'stop_state': stop, 'outcome': result.get('status'), 'reason': result.get('reason'),
        'rows': rows, 'total': len(journal),
        'next_offset': offset+len(rows) if offset+len(rows) < len(journal) else None,
        'committed_turns': deepcopy(protocol.get('view', {}).get('turns', [])),
        'committed_report': deepcopy(protocol.get('report')),
        'retry_available_in_result': bool(retry), 'retry_requires_explicit_owner_command': True,
        'usage': deepcopy(protocol.get('usage', {})), 'read_performed_model_calls': 0,
        'partial_text_is_answered': False}


def read_journal(owner, document_id, job_id, *, offset=0, limit=64):
    """Owner validates exact document/run ownership and retained checksums.

    Reading can collect a finished job through the EXISTING owner. It cannot
    submit/complete a new action, consume a budget, or change unsent composer text.
    """
    document = owner.read(document_id)
    run = next((r for r in document['runs'] if r['job_id'] == job_id), None)
    if run is None:
        raise ValueError('선택한 원 작업이 이 토론 문서에 없습니다.')
    result = owner.result(document_id, job_id)
    return inspect_journal(result, document_id=document_id, job_id=job_id,
        job_state=run.get('state'), cancel_requested=run.get('cancel_requested', False),
        offset=offset, limit=limit)
