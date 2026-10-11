"""Actual shared owner revisions/Undo; no calculation or Expert runtime."""
from copy import deepcopy
import pytest

from caelab.study_document import StudyDocuments, default_draft, diagnostics
from caelab.storage import canonical_hash


class NeverRun:
    def __call__(self, *args, **kwargs):
        raise AssertionError('Study must never submit a calculation or inference')
    def list(self):
        raise AssertionError('Study reads must not inspect execution jobs')


def research_draft():
    draft = default_draft()
    draft['question'] = 'Which of the two competing mechanisms agrees with the retained observation?'
    draft['hypotheses'] = [{'id': 'Hone', 'title': 'Mechanism one', 'statement': 'Explicit first hypothesis', 'status': 'UNKNOWN'},
                           {'id': 'Htwo', 'title': 'Mechanism two', 'statement': 'Explicit competing hypothesis', 'status': 'UNKNOWN'}]
    draft['evidence'] = [
        {'id': 'Edomain', 'label': 'Original PDE', 'kind': 'document', 'reference': {'kind': 'document', 'document_kind': 'pde',
         'document_id': 'Qoriginal', 'saved_revision': 'Roriginal', 'input_revision': 'Ioriginal', 'input_sha256': 'a' * 64}, 'note': ''},
        {'id': 'Eresult', 'label': 'Original response', 'kind': 'result', 'reference': {'kind': 'result', 'document_id': 'Toriginal',
         'job_id': 'Jactual', 'input_revision': 'Iactual', 'input_sha256': 'b' * 64, 'result_sha256': 'c' * 64, 'response': 'axial'}, 'note': ''},
        {'id': 'Eturn', 'label': 'Actual opposing Expert turn', 'kind': 'expert_turn', 'reference': {'kind': 'expert_turn',
         'discussion_id': 'Xoriginal', 'saved_revision': 'Rdiscussion', 'turn_id': 'Bactual', 'turn_sha256': 'd' * 64}, 'note': ''}]
    draft['decisions'] = [{'id': 'Ddecision', 'title': 'Current provisional interpretation', 'statement': 'The evidence is conflicting',
        'hypothesis_ids': ['Hone', 'Htwo'], 'supporting': ['Eresult'], 'conflicting': ['Eturn'], 'status': 'UNKNOWN'}]
    draft['next_observations'] = [{'id': 'Onext', 'question': 'Measure the discriminating response', 'hypothesis_ids': ['Hone', 'Htwo'],
        'evidence_ids': ['Edomain'], 'status': 'PLANNED', 'note': 'Observation remains unperformed'}]
    return draft


def command(owner, doc, operation, arguments=None, command_id=None):
    return owner.command(doc['id'], operation, arguments or {}, session_id=doc['session_id'],
        expected_generation=doc['generation'], command_id=command_id)['document']


def test_actual_study_owner_save_restart_undo_and_competing_evidence(tmp_path):
    never = NeverRun()
    owner = StudyDocuments(tmp_path, 'Ssession', never, never)
    draft = research_draft()
    assert diagnostics(draft) == []
    doc = owner.open(title='Independent research question', draft=draft)
    assert doc['kind'] == 'study' and doc['id'].startswith('S')
    assert doc['capabilities'] == ['document.redo', 'document.save', 'document.undo', 'study.update']
    saved = command(owner, doc, 'document.save')
    revision = saved['saved_revision']
    edited = deepcopy(draft)
    edited['decisions'][0]['status'] = 'SUPPORTED'
    edited['decisions'][0]['statement'] = 'Authored judgment; conflicting evidence remains explicit'
    changed = command(owner, saved, 'study.update', {'draft': edited}, 'Cupdate')
    assert changed['generation'] == 1 and changed['draft']['engineering_release'] == 'NOT_RELEASED'
    undone = command(owner, changed, 'document.undo')
    assert undone['draft'] == draft
    redone = command(owner, undone, 'document.redo')
    assert redone['draft'] == edited
    saved2 = command(owner, redone, 'document.save')
    assert owner._verify_revision(doc['id'], revision)['draft'] == draft
    reopened = StudyDocuments(tmp_path, 'Srestart', never, never).open(document_id=doc['id'])
    assert reopened['draft'] == edited and reopened['session_id'] == 'Srestart'
    assert reopened['saved_revision'] == saved2['saved_revision'] and reopened['runs'] == []


def test_invalid_study_draft_is_saved_exactly_and_has_no_calculation_op(tmp_path):
    never = NeverRun()
    owner = StudyDocuments(tmp_path, 'Ssession', never, never)
    raw = {'question': ['invalid but authored'], 'unknown_original': {'release_claim': 'untouched'}}
    doc = owner.open(draft=raw)
    assert doc['diagnostics']
    saved = command(owner, doc, 'document.save')
    reopened = StudyDocuments(tmp_path, 'Snew', never, never).open(document_id=doc['id'])
    assert reopened['draft'] == raw and reopened['saved_revision'] == saved['saved_revision']
    for operation in ('study.run', 'study.evaluate', 'expert.ask', 'numerical.run'):
        with pytest.raises(ValueError, match='Unsupported'):
            command(owner, reopened, operation)


def test_study_generation_session_and_exact_command_receipt(tmp_path):
    never = NeverRun()
    owner = StudyDocuments(tmp_path, 'Ssession', never, never)
    before = owner.open(draft=research_draft())
    updated = deepcopy(before['draft'])
    updated['question'] = 'Explicit revised question'
    after = command(owner, before, 'study.update', {'draft': updated}, 'Cexact')
    assert command(owner, before, 'study.update', {'draft': updated}, 'Cexact') == after
    with pytest.raises(ValueError, match='generation changed'):
        command(owner, before, 'study.update', {'draft': research_draft()}, 'Cother')
    with pytest.raises(ValueError, match='session is stale'):
        owner.command(before['id'], 'document.save', {}, session_id='Sold', expected_generation=after['generation'])


def test_missing_conflicting_references_remain_visible_and_saveable(tmp_path):
    draft = research_draft()
    draft['decisions'][0]['status'] = 'SUPPORTED'
    draft['decisions'][0]['supporting'] = ['Emissing']
    draft['engineering_release'] = 'RELEASED'
    errors = diagnostics(draft)
    assert any('absent' in row['message'] for row in errors)
    assert any('NOT_RELEASED' in row['message'] for row in errors)
    never = NeverRun()
    owner = StudyDocuments(tmp_path, 'Ssession', never, never)
    doc = owner.open(draft=draft)
    assert command(owner, doc, 'document.save')['draft'] == draft


def test_exact_source_validation_reports_unavailable_without_changing_decision(tmp_path):
    calls = []
    def resolve(reference):
        calls.append(deepcopy(reference))
        if reference['kind'] == 'expert_turn':
            raise FileNotFoundError('Original saved turn is missing')
        return {'status': 'MATCHED' if reference['kind'] == 'document' else 'STALE', 'message': 'Controlled source validation'}
    never = NeverRun()
    owner = StudyDocuments(tmp_path, 'Ssession', never, never, resolve_reference=resolve)
    doc = owner.open(draft=research_draft())
    fingerprint = canonical_hash(doc['draft'])
    result = owner.resolve_references(doc['id'])
    assert [row['status'] for row in result['references']] == ['MATCHED', 'STALE', 'UNAVAILABLE']
    assert calls == [row['reference'] for row in doc['draft']['evidence']]
    assert canonical_hash(owner.read(doc['id'])['draft']) == fingerprint
    assert command(owner, doc, 'document.save')['draft']['decisions'][0]['status'] == 'UNKNOWN'
