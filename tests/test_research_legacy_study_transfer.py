"""Saved legacy turn transfer uses existing owners and durable command receipts."""
from copy import deepcopy

import pytest

from caelab.storage import canonical_hash
from caelab.workbench import Workbench


@pytest.fixture
def source(tmp_path):
    wb = Workbench(tmp_path / 'store', configuration={'workers': 1})
    owner = wb.discussion_documents
    document = owner.open(title='보존된 연구 대화')
    actual = owner._documents[document['id']]
    turn = {'id': 'Aoriginal', 'author': 'user', 'text': '원 관측을 비교할 필요가 있다.', 'status': 'AUTHORED'}
    actual['discussion']['turns'].append(turn)
    owner._persist_draft(actual)
    saved = owner.command(document['id'], 'document.save', {}, session_id=wb.session_id,
        expected_generation=actual['generation'], command_id='CsaveSource')['document']
    reference = {'kind': 'expert_turn', 'discussion_id': saved['id'], 'saved_revision': saved['saved_revision'],
        'turn_id': turn['id'], 'turn_sha256': canonical_hash(turn)}
    args = dict(session_id=wb.session_id, expected_generation=saved['generation'], command_id='Ctransfer')
    try:
        yield wb, saved, reference, args
    finally:
        assert wb.shutdown()['joined']


def test_retry_after_reply_loss_and_source_edit_keeps_same_authored_study(source, monkeypatch):
    wb, saved, reference, args = source
    before = deepcopy(wb.document_read(saved['id']))
    first = wb.research_team_transfer(saved['id'], 'study', {'turn_ref': reference}, **args)
    target = first['document']
    assert target['draft']['evidence'][0]['reference'] == reference
    assert target['draft']['decisions'] == [] and target['draft']['engineering_release'] == 'NOT_RELEASED'
    assert wb.document_read(saved['id']) == before and wb.manager.list() == []
    draft = deepcopy(target['draft']); draft['question'] = '사용자가 작성한 판단 질문'
    wb.document_command(target['id'], 'study.update', {'draft': draft}, session_id=wb.session_id,
        expected_generation=target['generation'], command_id='CeditStudy')
    current = wb.document_read(saved['id']); changed = deepcopy(current['draft'])
    changed['composer']['text'] = '원 대화의 이후 편집'
    wb.document_command(saved['id'], 'expert.update', {'draft': changed}, session_id=wb.session_id,
        expected_generation=current['generation'], command_id='CeditExpert')
    again = wb.research_team_transfer(saved['id'], 'study', {'turn_ref': reference}, **args)
    assert again['document']['id'] == target['id'] and again['document']['draft'] == draft
    assert len(wb.study_documents.list()) == 1 and wb.manager.list() == []
    # A committed receipt never bypasses a subsequent current-access check.
    monkeypatch.setattr(wb, 'research_reference', lambda ref: (_ for _ in ()).throw(PermissionError('revoked')))
    with pytest.raises(PermissionError, match='revoked'):
        wb.research_team_transfer(saved['id'], 'study', {'turn_ref': reference}, **args)
    assert wb.study_documents.read(target['id'])['draft'] == draft


def test_wrong_saved_turn_and_reused_command_selection_are_rejected(source):
    wb, saved, reference, args = source
    wrong = {**reference, 'turn_sha256': '0' * 64}
    with pytest.raises(ValueError, match='differs'):
        wb.research_team_transfer(saved['id'], 'study', {'turn_ref': wrong}, **args)
    assert wb.study_documents.list() == []
    wb.research_team_transfer(saved['id'], 'study', {'turn_ref': reference}, **args)
    with pytest.raises(ValueError, match='conflicts'):
        wb.research_team_transfer(saved['id'], 'study', {'turn_ref': reference, 'evidence_ref': None}, **args)
    assert len(wb.study_documents.list()) == 1 and wb.manager.list() == []


def test_same_saved_selection_after_owner_restart_reopens_existing_authored_study(source):
    wb, saved, reference, args = source
    target = wb.research_team_transfer(saved['id'], 'study', {'turn_ref': reference}, **args)['document']
    draft = deepcopy(target['draft']); draft['question'] = '재시작 후에도 보존할 질문'
    edited = wb.document_command(target['id'], 'study.update', {'draft': draft}, session_id=wb.session_id,
        expected_generation=target['generation'], command_id='CkeepEdit')['document']
    wb.document_command(target['id'], 'document.save', {}, session_id=wb.session_id,
        expected_generation=edited['generation'], command_id='CsaveStudy')
    assert wb.shutdown()['joined']
    reopened = Workbench(wb.root.parent, configuration={'workers': 1})
    try:
        current = reopened.document_read(saved['id'])
        assert current['session_id'] != args['session_id']
        result = reopened.research_team_transfer(saved['id'], 'study', {'turn_ref': reference},
            session_id=reopened.session_id, expected_generation=current['generation'], command_id=args['command_id'])
        assert result['document']['id'] == target['id'] and result['document']['draft'] == draft
        assert len(reopened.study_documents.list()) == 1 and reopened.manager.list() == []
    finally:
        assert reopened.shutdown()['joined']


def test_earlier_local_receipt_recovers_only_its_existing_exact_destination(source):
    from caelab.storage import save_json
    from caelab.study_document import default_draft
    wb, saved, reference, args = source
    old_hash = canonical_hash({'document_id': saved['id'], 'kind': 'legacy_study',
        'selection': {'turn_ref': reference}, 'session_id': 'Sprevious', 'generation': 0})
    original = default_draft()
    original['evidence'] = [{'id': 'Eturn', 'label': '원 발언', 'kind': 'expert_turn', 'reference': reference, 'note': ''}]
    target = wb.study_documents.open(_new_id='S' + old_hash[:32], draft=original)
    edited = deepcopy(original); edited['question'] = '이전 응답 유실 뒤 작성한 질문'
    wb.document_command(target['id'], 'study.update', {'draft': edited}, session_id=wb.session_id,
        expected_generation=target['generation'], command_id='CpreviousEdit')
    receipt = {'request_hash': old_hash, 'document_id': target['id'], 'state': 'SUCCEEDED',
        'proposal': {'draft': original, 'source_references': [reference]}}
    path = wb.desktop.root / 'discussion_studies' / (args['command_id'] + '.json')
    save_json(path, receipt)
    result = wb.research_team_transfer(saved['id'], 'study', {'turn_ref': reference}, **args)
    assert result['document']['id'] == target['id'] and result['document']['draft'] == edited
    assert len(wb.study_documents.list()) == 1 and wb.manager.list() == []
    receipt['proposal']['source_references'] = [{**reference, 'turn_sha256': '0' * 64}]
    save_json(path, receipt)
    with pytest.raises(ValueError, match='conflicts'):
        wb.research_team_transfer(saved['id'], 'study', {'turn_ref': reference}, **args)
    assert wb.study_documents.read(target['id'])['draft'] == edited
