"""Nonexecuting selection adapter for the existing Expert-to-Study owner route."""
from copy import deepcopy

from caelab.storage import canonical_hash
from caelab.study_document import reference_error


def exact_evidence(client, reference):
    """Use the existing readers, keeping the selected job/revision/selection."""
    reference = deepcopy(reference)
    if reference.get('kind'):
        issue = reference_error(reference)
        if issue:
            raise ValueError(issue)
        client.research_reference(reference)
        return reference
    if reference.get('document_id') and reference.get('job_id'):
        exact = client.document_result_reference(reference['document_id'], reference['job_id'])
        for key in ('input_revision', 'input_sha256'):
            if not reference.get(key) or reference[key] != exact.get(key):
                raise ValueError('선택한 계산의 원 입력이 일치하지 않습니다. 같은 실행을 다시 선택하세요.')
        if reference.get('result_sha256') and reference['result_sha256'] != exact['result_sha256']:
            raise ValueError('선택한 보존 결과가 일치하지 않습니다.')
        result = dict(kind='result', **exact)
        if 'selection' in reference:
            result['selection'] = deepcopy(reference['selection'])
        elif 'response' in reference:
            result['response'] = reference['response']
        client.research_reference(result)
        return result
    if reference.get('document_id') and type(reference.get('revision')) is int:
        from .expert_sources import assist
        locator = deepcopy(reference.get('locator', {}))
        source = assist(client, 'knowledge.source', {'document_id': reference['document_id'],
            'revision': reference['revision'], 'locator': locator})
        if source.get('status') != 'AVAILABLE':
            raise ValueError('선택한 보관 문헌 구간을 읽을 수 없습니다.')
        return dict(kind='knowledge', document_id=reference['document_id'], revision=reference['revision'],
            locator=locator, source_sha256=source['sha256'], content_sha256=canonical_hash(source))
    raise ValueError('이 근거에는 정확한 보관 참조가 없습니다. 원자료에서 저장한 뒤 다시 선택하세요.')


def selected_references(client, document, turn_id, evidence=None):
    turn = next((row for row in document.get('turns', []) if row['id'] == turn_id), None)
    if turn is None or not document.get('saved_revision') or document.get('dirty'):
        raise ValueError('선택 발언이 포함된 대화를 먼저 저장하세요.')
    reference = dict(kind='expert_turn', discussion_id=document['id'], saved_revision=document['saved_revision'],
        turn_id=turn_id, turn_sha256=canonical_hash(turn))
    client.research_reference(reference)
    selection = {'turn_ref': reference}
    if evidence is not None:
        selection['evidence_ref'] = exact_evidence(client, evidence)
    return selection
