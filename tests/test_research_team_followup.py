"""Proposal links and real owner/math/storage chain with controlled role input."""
from copy import deepcopy

import pytest

from caelab.research_team_followup import (claim_rows, plan_link, proposal_origin,
    result_review_draft, study_proposal)
from caelab.storage import canonical_hash
from examples.research_team_followup_public import run_public


@pytest.fixture
def discussion():
    proposal = {'purpose': 'Public analysis proposal', 'operation': 'analyze',
        'inputs': {'job_id': 'Jsource', 'responses': [{'response': 'force', 'unit': 'N', 'reduction': 'none'}]},
        'budget': {'evaluations': 1}}
    response_id = 'Rsource'
    claim_id = 'C' + canonical_hash({'response': response_id, 'index': 0})[:32]
    return {'id': 'Xdiscussion', 'saved_revision': 'Rsaved', 'kind': 'expert',
        'draft': {'context': {'research_team': {'version': 2, 'phase_id': 'Pold',
            'objective': 'Public review question', 'assignments': [
                {'expert_id': 'reviewer', 'result_refs': []}, {'expert_id': 'unselected', 'result_refs': []}]}},
            'composer': {'text': 'Unsaved authored edit', 'evidence': [], 'reply_to': None, 'classification': 'question'}},
        'runs': [{'job_id': 'Jactual', 'input_revision': 'Iactual', 'input_sha256': 'a' * 64}],
        'turns': [{'id': 'Aturn', 'job_id': 'Jactual', 'job_state': 'SUCCEEDED', 'input_revision': 'Iactual',
            'input_sha256': 'a' * 64, 'research_response_id': response_id, 'response': {
                'proposed_actions': [{'status': 'PLANNED', 'executed': False, 'plan': proposal}],
                'research_reply': {'claims': [{'text': 'A hypothesis, not an observed result', 'basis': 'hypothesized'}]}}}],
        'research_team': {'responses': {response_id: {'id': response_id, 'task_id': 'Torigin', 'phase_id': 'Pold',
            'dependency_ids': ['Duncited-private', 'Dresponse-parent'], 'input_manifest_ids': ['Mwhole-response'],
            'claim_refs': [{'id': claim_id, 'index': 0, 'response_id': response_id}]}}}}


def test_exact_proposal_followup_and_study_keep_full_dependencies_without_execution(discussion):
    before = deepcopy(discussion)
    origin = proposal_origin(discussion, 'Aturn', 0)
    plan = {'id': 'Nplan', 'kind': 'numerical', 'input_revision': 'Iplan',
            'draft': {'mode': 'request', 'source': origin['source'], 'request': origin['proposal']}}
    link = plan_link(origin, plan)
    reference = {'document_id': 'Nplan', 'job_id': 'Jresult', 'input_revision': 'Ifrozen',
                 'input_sha256': 'b' * 64, 'result_sha256': 'c' * 64}
    selector = {'metadata_only': False, 'channels': [{'response': 'force'}]}
    selected = {'source_id': 'selection', 'reference': reference, 'selector': selector}
    followup = result_review_draft(discussion, plan_link=link, result_reference=reference, selector=selector,
        current_scope=lambda *a: {'status': 'AVAILABLE', 'result_selection': selected,
                                  'dependency_ids': ['Dactual-read'], 'actor_ids': ['reviewer'],
                                  'submitted_plan_source': origin['source']})
    assert followup['draft']['context']['research_team']['phase_id'] is None
    assert followup['draft']['context']['research_team']['parent_phase_id'] == 'Pold'
    assert followup['draft']['context']['research_team']['assignments'][0]['result_refs'] == [selected]
    assert followup['draft']['context']['research_team']['assignments'][1]['result_refs'] == []
    assert followup['dependency_ids'] == ['Duncited-private', 'Dresponse-parent', 'Dactual-read']
    assert followup['executed'] is False and followup['new_ask'] is False and discussion == before
    study = study_proposal(discussion, [claim_rows(discussion)[0]['id']])
    assert study['dependency_ids'] == ['Duncited-private', 'Dresponse-parent']
    assert study['draft']['hypotheses'][0]['status'] == 'UNKNOWN'
    assert study['draft']['engineering_release'] == 'NOT_RELEASED' and study['applied'] is False
    assert study['source_references'][0]['turn_sha256'] == canonical_hash(discussion['turns'][0])
    assert discussion == before


def test_wrong_origin_or_selected_result_and_unverified_claim_are_rejected(discussion):
    origin = proposal_origin(discussion, 'Aturn', 0)
    with pytest.raises(ValueError):
        plan_link(origin, {'kind': 'numerical', 'draft': {'mode': 'request', 'source': {}}})
    discussion['turns'][0]['response']['proposed_actions'][0]['executed'] = True
    with pytest.raises(ValueError):
        proposal_origin(discussion, 'Aturn', 0)
    discussion['research_team']['responses']['Rsource']['claim_refs'] = []
    assert claim_rows(discussion) == []
    with pytest.raises(ValueError):
        study_proposal(discussion, ['Cmodel-invented'])


def test_followup_preserves_prior_challenges_constraints_and_selected_results(discussion):
    team = discussion['draft']['context']['research_team']
    team['carry_forward_turn_ids'] = ['ApriorChallenge']
    team['assignments'][0]['result_refs'] = [{'source_id': 'previous-comparison'}]
    discussion['draft']['context']['user_constraints'] = ['Do not change the friction coefficient.']
    discussion['draft']['composer']['evidence'] = [{'kind': 'authored', 'text': 'Earlier failure'}]
    origin = proposal_origin(discussion, 'Aturn', 0)
    plan = {'id': 'Nplan', 'kind': 'numerical', 'input_revision': 'Iplan',
            'draft': {'mode': 'request', 'source': origin['source'], 'request': origin['proposal']}}
    reference = {'document_id': 'Nplan', 'job_id': 'Jresult', 'input_revision': 'Ifrozen',
        'input_sha256': 'b' * 64, 'result_sha256': 'c' * 64}
    selected = {'reference': reference, 'selector': {'metadata_only': True}}
    result = result_review_draft(discussion, plan_link=plan_link(origin, plan), result_reference=reference,
        selector=selected['selector'], current_scope=lambda *args: {'status': 'AVAILABLE',
            'result_selection': selected, 'actor_ids': ['reviewer'], 'submitted_plan_source': origin['source']})
    draft = result['draft']
    assert draft['context']['research_team']['carry_forward_turn_ids'] == ['ApriorChallenge', 'Aturn']
    assert draft['context']['research_team']['assignments'][0]['result_refs'] == [{'source_id': 'previous-comparison'}, selected]
    assert draft['context']['user_constraints'] == discussion['draft']['context']['user_constraints']
    assert draft['composer']['evidence'] == discussion['draft']['composer']['evidence']


@pytest.mark.parametrize('wrapped', [False, True])
def test_incomplete_proposal_retains_original_identity_and_can_be_completed(discussion, wrapped):
    from caelab.assist.experts import proposal_request, validate_plan_request
    action = {'status': 'PROPOSED', 'executed': False,
              'proposal': {'operation': 'evaluate', 'inputs': {'backend': 'material.felupe'}}}
    if wrapped:
        action['proposal'] = {'tool': 'calculations.plan', 'request': action['proposal']}
    discussion['turns'][0]['response']['proposed_actions'] = [action]
    before = deepcopy(discussion)
    origin = proposal_origin(discussion, 'Aturn', 0)
    request = proposal_request(action)
    assert request['purpose'] == '' and request['budget'] == {'evaluations': 1}
    assert origin['source']['proposal_sha256'] == canonical_hash(action['proposal'])
    with pytest.raises(ValueError):
        validate_plan_request(request)
    request.update(purpose='Evaluate the edited model')
    request['inputs']['settings'] = {}
    assert validate_plan_request(request)['executed'] is False
    assert discussion == before


def test_one_redacted_response_does_not_block_another_allowed_claim(discussion):
    allowed = deepcopy(discussion['turns'][0]); allowed['id'] = 'Aallowed'; allowed['research_response_id'] = 'Rallowed'
    record = deepcopy(discussion['research_team']['responses']['Rsource']); record['id'] = 'Rallowed'
    record['claim_refs'] = [{'id': 'C' + canonical_hash({'response': 'Rallowed', 'index': 0})[:32],
                             'response_id': 'Rallowed', 'index': 0}]
    discussion['research_team']['responses']['Rallowed'] = record
    discussion['turns'].append(allowed)
    discussion['turns'][0].update(status='SOURCE_UNAVAILABLE', response={'status': 'SOURCE_UNAVAILABLE', 'answer': None})
    rows = claim_rows(discussion)
    assert [r['response_id'] for r in rows] == ['Rallowed']
    assert study_proposal(discussion, [rows[0]['id']])['draft']['hypotheses'][0]['status'] == 'UNKNOWN'
    # An allegedly available but mismatched body is still corruption, not a
    # reason to silently skip the original claim reference.
    discussion['turns'][0].update(status='AVAILABLE', response={'research_reply': {'claims': []}})
    with pytest.raises(ValueError, match='Owner-issued claim'):
        claim_rows(discussion)


def test_public_plan_actual_math_followup_and_study_reopen(tmp_path):
    output = tmp_path / 'public chain'
    receipt = run_public(output)
    assert receipt['actual_math'] == 'existing numerical.analyze'
    assert receipt['provider'] == receipt['solver'] == 'NOT_RUN'
    assert receipt['cold_read'] == 'PASSED_NO_NEW_JOB'
    assert receipt['study_draft']['engineering_release'] == 'NOT_RELEASED'
    from examples.research_team_followup_public import CONFIG
    from caelab.workbench import Workbench
    from caelab.research_team_followup import build_transfer_context
    wb = Workbench(output, configuration=CONFIG)
    try:
        discussion = wb.document_read(receipt['discussion_id'])
        access = build_transfer_context(wb, discussion)
        source = access['state']['responses']['RpublicControlled']
        selector = {'metadata_only': True, 'channels': []}
        for key, wrong in [('result_sha256', '0' * 64), ('input_sha256', '0' * 64),
                           ('input_revision', 'Ifake'), ('job_id', 'Jfake'), ('document_id', 'Nfake')]:
            changed = {**receipt['result_reference'], key: wrong}
            with pytest.raises((ValueError, FileNotFoundError)):
                access['check_result_review'](source, changed, selector, ['public-role'])
        args = dict(session_id=wb.session_id, expected_generation=discussion['generation'], command_id='CwrongRun')
        with pytest.raises(ValueError, match='actual retained run'):
            wb.research_team_transfer(discussion['id'], 'result_review', {'turn_id': receipt['source_turn_id'],
                'proposal_index': 0, 'plan_document_id': receipt['plan_id'], 'job_id': 'Jfake',
                'selector': selector, 'actor_ids': ['public-role']}, **args)
        runtime = wb.assistance().experts
        runtime._transmission_check = lambda *a, **k: (_ for _ in ()).throw(PermissionError('Controlled current revocation'))
        with pytest.raises(ValueError, match='cannot be shared'):
            wb.research_team_transfer(discussion['id'], 'report', {'action_id': 'DpublicReport'},
                session_id=wb.session_id, expected_generation=discussion['generation'], command_id='CpublicReportCold')
        assert wb.document_read(receipt['report_id'])['draft'] == receipt['report_draft']
        assert len(wb.manager.list()) == receipt['job_count']
    finally:
        assert wb.shutdown()['joined']


def test_actual_owner_study_transfer_retry_keeps_edits_and_local_scope_without_model(tmp_path):
    from types import SimpleNamespace
    from caelab.workbench import Workbench
    from caelab.research_team_followup import transfer, build_transfer_context
    from caelab.discussion_research_team import empty_state, resolve_asset
    from caelab.evaluation import file_hash
    from caelab.storage import save_json
    wb = Workbench(tmp_path / 'transfer', configuration={'workers': 1})
    try:
        owner = wb.discussion_documents
        opened = owner.open(title='Public local Study transfer')
        doc = owner._documents[opened['id']]
        response_id = 'Rsource'
        raw = {'research_reply': {'claims': [{'text': 'A hypothesis remains unknown', 'basis': 'hypothesized'}]}}
        path = owner._folder(doc['id']) / 'research-team' / 'Dfixture' / 'assets' / 'Rsource.json'
        save_json(path, raw)
        asset = {'path': path.relative_to(owner._folder(doc['id'])).as_posix(), 'sha256': file_hash(path)}
        claim = 'C' + canonical_hash({'response': response_id, 'index': 0})[:32]
        state = empty_state()
        state['dependencies'] = {'Dsource': {'id': 'Dsource', 'kind': 'authored', 'parent_ids': [],
            'exact_ref': {'kind': 'authored_question'}, 'content_digest': canonical_hash('public')}}
        state['assets']['Rsource'] = asset
        state['responses'][response_id] = {'id': response_id, 'task_id': 'Tsource', 'phase_id': 'Psource',
            'dependency_ids': ['Dsource'], 'input_manifest_ids': ['Msource'], 'raw_response_ref': asset,
            'claim_refs': [{'id': claim, 'response_id': response_id, 'index': 0}]}
        doc['draft']['context']['research_team'] = {'version': 2, 'objective': 'Public local review'}
        doc['discussion']['research_team'] = state
        doc['discussion']['turns'] = [{'id': 'Aturn', 'research_response_id': response_id, 'response': raw}]
        owner._persist_draft(doc)
        allowed = [True]
        def context(document):
            actual = build_transfer_context(wb, document)
            checker = actual['check_local_dependency']
            actual['check_local_dependency'] = lambda row: checker(row) if allowed[0] else False
            return actual
        owner.research_team_transfer_context = context
        wb.assistance = lambda: (_ for _ in ()).throw(AssertionError('Local Study must not require the role/provider registry'))
        args = dict(session_id=wb.session_id, expected_generation=doc['generation'], command_id='Cstudy')
        first = transfer(wb, doc['id'], 'study', {'claim_ids': [claim]}, **args)
        target = first['document']
        draft = deepcopy(target['draft']); draft['question'] = 'My retained authored question'
        wb.document_command(target['id'], 'study.update', {'draft': draft},
            session_id=wb.session_id, expected_generation=target['generation'], command_id='Cedit')
        again = transfer(wb, doc['id'], 'study', {'claim_ids': [claim]}, **args)
        assert again['document']['id'] == target['id']
        assert again['document']['draft']['question'] == 'My retained authored question'
        assert again['dependency_ids'] == ['Dsource'] and wb.manager.list() == []
        allowed[0] = False
        with pytest.raises(ValueError):
            transfer(wb, doc['id'], 'study', {'claim_ids': [claim]}, **args)
        assert wb.study_documents.read(target['id'])['draft'] == draft
        with pytest.raises(ValueError):
            transfer(wb, doc['id'], 'study', {'claim_ids': [claim], 'payload': raw}, **args)
    finally:
        assert wb.shutdown()['joined']
