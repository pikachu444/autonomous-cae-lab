"""Editable follow-up proposals for existing X/N/S owners; never submit or Ask."""
from copy import deepcopy

from .assist.experts import validate_plan_request
from .research_operations import validate_result_reference
from .storage import canonical_hash
from .study_document import default_draft as study_draft


def _need(value, message):
    if not value:
        raise ValueError(message)


def _team(discussion):
    return discussion.get('research_team', discussion.get('discussion', {}).get('research_team', {}))


def _turns(discussion):
    return discussion.get('turns', discussion.get('discussion', {}).get('turns', []))


def _response(discussion, turn):
    identity = turn.get('research_response_id')
    record = _team(discussion).get('responses', {}).get(identity)
    _need(record is not None and record.get('id') == identity and record.get('input_manifest_ids')
          and isinstance(record.get('dependency_ids'), list), 'Choose a verified research response with its full input provenance')
    return record


def proposal_origin(discussion, turn_id, proposal_index):
    turn = next((t for t in _turns(discussion) if t['id'] == turn_id), None)
    _need(turn is not None and turn.get('job_id') and turn.get('job_state') == 'SUCCEEDED',
          'Choose an actual managed reply and its unexecuted Plan proposal')
    record = _response(discussion, turn)
    proposals = turn.get('response', {}).get('proposed_actions', [])
    _need(type(proposal_index) is int and 0 <= proposal_index < len(proposals), 'Choose an exact proposal index')
    action = proposals[proposal_index]
    _need(action.get('status') == 'PLANNED' and action.get('executed') is False, 'A prediction or executed action is not a Plan draft')
    plan = validate_plan_request(action.get('plan'))['plan']
    run = next((r for r in discussion.get('runs', []) if r['job_id'] == turn['job_id']), None)
    _need(run is not None and all(run.get(k) == turn.get(k) for k in ('input_revision', 'input_sha256')),
          'Reply and submitted input differ')
    source = {k: run[k] for k in ('job_id', 'input_revision', 'input_sha256')}
    source.update(discussion_id=discussion['id'], turn_id=turn_id, proposal_index=proposal_index,
                  proposal_sha256=canonical_hash(plan))
    return {'source': source, 'proposal': deepcopy(plan), 'response_id': record['id'],
            'task_id': record['task_id'], 'phase_id': record['phase_id'],
            'dependency_ids': deepcopy(record['dependency_ids']),
            'input_manifest_ids': deepcopy(record['input_manifest_ids']), 'executed': False}


def plan_link(origin, plan_document):
    _need(plan_document.get('kind') == 'numerical' and plan_document['draft'].get('mode') == 'request' and
          plan_document['draft'].get('source') == origin['source'], 'Plan is not linked to this exact response proposal')
    return {'origin': deepcopy(origin), 'plan_document_id': plan_document['id'],
            'plan_input_revision': plan_document['input_revision'],
            'plan_input_sha256': canonical_hash(plan_document['draft']),
            'dependency_ids': deepcopy(origin['dependency_ids']), 'executed': False}


def result_review_draft(discussion, *, plan_link, result_reference, selector, current_scope):
    reference = validate_result_reference(result_reference)
    origin = proposal_origin(discussion, plan_link['origin']['source']['turn_id'],
                             plan_link['origin']['source']['proposal_index'])
    _need(origin == plan_link['origin'], 'Source response/proposal changed; keep the original follow-up')
    _need(reference['document_id'] == plan_link['plan_document_id'], 'Select the actual result of this Plan document')
    # The caller supplies B's current scope/result check, not a saved grant dict.
    checked = current_scope(deepcopy(origin['dependency_ids']), deepcopy(reference), deepcopy(selector))
    _need(isinstance(checked, dict) and checked.get('status') == 'AVAILABLE' and checked.get('result_selection'),
          'Current source/result selection is not available for follow-up')
    _need(checked.get('submitted_plan_source') == origin['source'],
          'The selected run was not submitted from this exact response proposal')
    selected = checked['result_selection']
    _need(selected['reference'] == reference and selected['selector'] == selector, 'Follow-up result check changed the selection')
    draft = deepcopy(discussion['draft'])
    team = draft.get('context', {}).get('research_team')
    _need(isinstance(team, dict) and team.get('version') == 2, 'Create an explicit research-team phase first')
    previous = team.get('phase_id')
    team.update(parent_phase_id=previous, phase_id=None, carry_forward_turn_ids=[origin['source']['turn_id']], requested_next=None)
    actors = checked.get('actor_ids')
    _need(isinstance(actors, list) and actors and set(actors) <= {a['expert_id'] for a in team.get('assignments', [])},
          'Explicitly select the roles allowed to receive the follow-up result')
    for assignment in team.get('assignments', []):
        if assignment['expert_id'] in actors:
            assignment['result_refs'] = [deepcopy(selected)]
    draft['composer'].update(text='원 가설과 판별 조건을 선택한 실제 결과와 대조해 유지·수정·철회 또는 미확인을 검토하세요.',
                             reply_to=origin['source']['turn_id'], classification='question', evidence=[])
    draft['context']['research_followup'] = {'plan_link': deepcopy(plan_link), 'result_reference': reference,
        'selector': deepcopy(selector), 'dependency_ids': list(dict.fromkeys(origin['dependency_ids'] + checked.get('dependency_ids', []))),
        'input_manifest_ids': deepcopy(origin['input_manifest_ids']), 'new_ask': False, 'executed': False}
    draft['context']['selected_result_ids'] = list(dict.fromkeys(draft['context'].get('selected_result_ids', []) + [reference['job_id']]))
    transmission = draft['context'].setdefault('transmission_scope', {})
    transmission['result_ids'] = list(dict.fromkeys(transmission.get('result_ids', []) + [reference['job_id']]))
    # This is a draft only. The current owner issues the next phase ID on update.
    return {'draft': draft, 'origin': deepcopy(origin), 'result_selection': deepcopy(selected),
            'dependency_ids': deepcopy(draft['context']['research_followup']['dependency_ids']),
            'status': 'DRAFT_PREPARED', 'executed': False, 'new_ask': False}


def claim_rows(discussion):
    """Consume owner-issued claim references; never grant a model-provided ID."""
    result = []
    for turn in _turns(discussion):
        if turn.get('status') == 'SOURCE_UNAVAILABLE' and turn.get('response') == {'status': 'SOURCE_UNAVAILABLE', 'answer': None}:
            continue  # Current owner display redaction; it grants no claim.
        if not turn.get('research_response_id'):
            continue
        record = _response(discussion, turn)
        claims = turn.get('response', {}).get('research_reply', {}).get('claims', [])
        for ref in record.get('claim_refs', []):
            index = ref['index']
            identifier = ref['id']
            _need(type(index) is int and 0 <= index < len(claims) and ref['response_id'] == record['id'] and
                  identifier == 'C' + canonical_hash({'response': record['id'], 'index': index})[:32],
                  'Owner-issued claim reference differs from its original response')
            claim = claims[index]
            result.append({'id': identifier, 'turn_id': turn['id'], 'response_id': record['id'],
                           'index': index, 'claim': deepcopy(claim),
                           'dependency_ids': deepcopy(record['dependency_ids']),
                           'input_manifest_ids': deepcopy(record['input_manifest_ids'])})
    return result


def study_proposal(discussion, selected_claim_ids):
    _need(isinstance(selected_claim_ids, list) and selected_claim_ids and
          len(set(selected_claim_ids)) == len(selected_claim_ids), 'Select distinct original research claims')
    available = {r['id']: r for r in claim_rows(discussion)}
    _need(set(selected_claim_ids) <= set(available), 'A selected claim is absent from this discussion')
    draft = study_draft()
    draft['question'] = discussion['draft']['context']['research_team']['objective']
    dependencies, manifests, sources = [], [], []
    _need(discussion.get('saved_revision'), 'Save the source discussion before proposing Study evidence')
    for index, identity in enumerate(selected_claim_ids):
        row = available[identity]
        turn = next(t for t in _turns(discussion) if t['id'] == row['turn_id'])
        evidence_id = 'E' + identity[1:]
        draft['hypotheses'].append({'id': identity, 'title': '선택 주장 ' + str(index + 1),
            'statement': row['claim']['text'], 'status': 'UNKNOWN'})
        reference = {'kind': 'expert_turn', 'discussion_id': discussion['id'],
                     'saved_revision': discussion['saved_revision'], 'turn_id': turn['id'], 'turn_sha256': canonical_hash(turn)}
        draft['evidence'].append({'id': evidence_id, 'label': '원 연구 발언', 'kind': 'expert_turn',
                                  'reference': reference, 'note': '관측·가설의 구별과 원 발언 전체의 입력 의존성을 유지합니다.'})
        draft['decisions'].append({'id': 'D' + identity[1:], 'title': '판단 작성', 'statement': '',
            'hypothesis_ids': [identity], 'supporting': [], 'conflicting': [], 'status': 'UNKNOWN'})
        dependencies.extend(row['dependency_ids']); manifests.extend(row['input_manifest_ids']); sources.append(reference)
    return {'draft': draft, 'source_references': sources,
            'dependency_ids': list(dict.fromkeys(dependencies)), 'input_manifest_ids': list(dict.fromkeys(manifests)),
            'status': 'PROPOSED', 'applied': False, 'executed': False}


def open_study_from_claims(wb, discussion_id, selected_claim_ids, *, session_id,
                           expected_generation, command_id, current_scope):
    """Explicit existing-owner transfer, with the same retry pattern as Plan open."""
    from .storage import check_id, load_json, save_json
    command_id, discussion_id = check_id(command_id), check_id(discussion_id)
    _need(session_id == wb.session_id and type(expected_generation) is int, 'Use the current document owner session')
    owner = wb.discussion_documents
    with wb.desktop._lock, owner._lock(discussion_id):
        discussion = owner.read(discussion_id)
        _need(discussion['generation'] == expected_generation, 'The source discussion changed; preserve your current edit')
        rows = {r['id']: r for r in claim_rows(discussion)}
        _need(isinstance(selected_claim_ids, list) and selected_claim_ids and
              len(set(selected_claim_ids)) == len(selected_claim_ids) and set(selected_claim_ids) <= set(rows), 'Select actual original claims')
        dependencies = list(dict.fromkeys(d for identity in selected_claim_ids for d in rows[identity]['dependency_ids']))
        _need(current_scope(deepcopy(dependencies)) is True, 'Current source dependencies are not allowed')
        signature = canonical_hash({'discussion_id': discussion_id, 'claims': selected_claim_ids,
            'selected_rows': [rows[i] for i in selected_claim_ids], 'generation': expected_generation, 'session_id': session_id})
        path = wb.desktop.root / 'discussion_studies' / (command_id + '.json')
        if path.exists():
            prepared = load_json(path)
            _need(prepared['request_hash'] == signature, 'Study command conflicts with another source selection')
        else:
            saved = owner.command(discussion_id, 'document.save', {}, session_id=session_id,
                                  expected_generation=expected_generation, command_id='C' + canonical_hash(command_id)[:40])['document']
            proposal = study_proposal(saved, selected_claim_ids)
            prepared = {'request_hash': signature, 'document_id': 'S' + signature[:32],
                        'proposal': proposal, 'state': 'APPLYING'}
            save_json(path, prepared)
        # Original response closure remains attached to the expert_turn source;
        # a retry opens the same Study and does not overwrite its authored draft.
        target = wb.study_documents
        with target._lock(prepared['document_id']):
            identifier = prepared['document_id']
            if (target._folder(identifier) / 'working.json').exists() or target._manifest(identifier):
                document = target.read(identifier)
            else:
                document = target.open(_new_id=identifier, title='연구 판단 작성', draft=prepared['proposal']['draft'])
            save_json(path, {**prepared, 'state': 'SUCCEEDED'})
        return {'document': document, 'command_id': command_id, 'status': 'DRAFT_OPENED',
                'dependency_ids': deepcopy(prepared['proposal']['dependency_ids']),
                'source_references': deepcopy(prepared['proposal']['source_references']), 'executed': False}


TRANSFER_SELECTIONS = {
    'study': {'claim_ids'}, 'report': {'action_id'},
    'result_review': {'turn_id', 'proposal_index', 'plan_document_id', 'job_id', 'selector', 'actor_ids'}}


def build_transfer_context(wb, discussion):
    """Compose existing owner/portable and B gates; never contact a provider."""
    from types import SimpleNamespace
    from .discussion_research_team import resolve_asset
    from .portable_research_knowledge import require_owner_sources
    from .portable_research_owner import current_folder, historical_reference
    from .connection_graph_refs import TypedReference
    from .research_team_results import (_owner_snapshot, normalize_selection, make_result_selection,
        workbench_readers, probe_retained_result, capture_result_verification, retained_result_files)
    owner = wb.discussion_documents
    identifier = discussion['id']
    # Use owner state, not a filtered GUI projection or a caller-supplied map.
    original = owner._documents[identifier]
    state = deepcopy(_team(original))
    bound = SimpleNamespace(owner=owner, owner_id=identifier)
    resolver = lambda ref: resolve_asset(bound, ref)
    navigation = {}  # One owner view/request only; never a permission cache.
    def verification(reference):
        asset = state.get('result_verifications', {}).get(canonical_hash(reference))
        _need(asset is not None, 'The explicitly attached result verification is unavailable')
        value = resolver(asset)
        _need(value['reference'] == reference, 'The original result verification differs')
        return value
    readers = workbench_readers(wb, verification_receipts=verification)
    def check_local(row):
        kind, ref = row['kind'], row['exact_ref']
        if kind == 'knowledge':
            require_owner_sources(owner, [ref])
            source = owner.resolve_knowledge({k: ref[k] for k in ('document_id', 'revision', 'locator') if k in ref})
            _need(source.get('status') == 'AVAILABLE' and (not ref.get('sha256') or source['sha256'] == ref['sha256']),
                  'The original knowledge revision differs')
            _need(any(canonical_hash(s['text']) == row['content_digest'] for s in source['segments']),
                  'The originally supplied knowledge segment differs')
        elif kind == 'literature':
            require_owner_sources(owner, [ref])
        elif kind == 'result':
            proof = verification(ref)
            key = canonical_hash(ref)
            if key not in navigation:
                navigation[key] = historical_reference(current_folder(owner._folder(identifier), original), original,
                    TypedReference((), '원 계산 결과', 'result', ref)).value
            current = deepcopy(navigation[key])
            storage, _, descriptor = _owner_snapshot(wb, current)
            _need(descriptor == proof['descriptor'], 'The original physical result catalog differs')
            normalize_selection({'descriptor': descriptor, 'descriptor_digest': canonical_hash(descriptor)},
                                row['selector'], granted_selector=row['selector'])
            if current == ref:
                _need(storage == proof['verified_storage_ref'], 'The retained result file set changed')
            else:
                _need(proof.get('result_files') and retained_result_files(wb, current, storage) == proof['result_files'],
                      'The exact original result bytes are unavailable; explicitly reattach this result')
        else:
            # These are authored/definition text or derived records inside the
            # verified owner, not an external permission or new execution grant.
            _need(kind in {'authored', 'role_definition', 'response', 'analysis', 'tool_output'}, 'Unknown local research input')
            _need(kind not in {'response', 'analysis', 'tool_output'} or row.get('parent_ids'), 'Derived input has no source closure')
        return True
    result = {'state': state, 'resolve_payload': resolver, 'check_local_dependency': check_local}
    def shared(actors=None, extra=None, extra_proof=None):
        from .assist.research_evidence import role_context, ResultAccess
        from .assist.knowledge import selected_source_refs
        runtime = wb.assistance().experts
        authored = original['draft']['context'].get('research_team', {})
        assignments = {r['expert_id']: deepcopy(r) for r in authored.get('assignments', [])}
        recipients = list(assignments) if actors is None else actors
        _need(recipients and set(recipients) <= set(assignments), 'Select current recipient roles')
        if extra is not None:
            for actor in recipients:
                assignments[actor]['result_refs'].append(deepcopy(extra))
        contexts = {actor: role_context(assignments[actor], original['draft'], runtime=runtime,
            workspace_id=wb.workspace_id, visibility='shared', accepted_responses=[])['context'] for actor in recipients}
        # Direct tool input is assignment-scoped; sharing an already generated
        # response uses the document's currently selected sources and each
        # recipient's registry collections, as B's shared gate defines.
        global_sources = selected_source_refs(original['draft']['context'])
        for context in contexts.values():
            context['selected_sources'] = deepcopy(global_sources)
            context['selected_document_ids'] = list(dict.fromkeys(r['document_id'] for r in global_sources))
            if extra is not None:
                transmission = context.setdefault('transmission_scope', {})
                transmission['result_ids'] = list(dict.fromkeys(transmission.get('result_ids', []) + [extra['reference']['job_id']]))
        current = {'ledger_state': state, 'context': deepcopy(original['draft']['context']),
            'assignments': assignments, 'recipient_contexts': contexts, 'resolve_payload': resolver}
        actual_readers = {**readers, 'transmission_check': runtime._transmission_check}
        if extra is not None:
            # A human selected this exact newly retained Plan result. This
            # transient metadata proof is not retained authority for model tools.
            ref = extra['reference']
            prior_probe = readers['probe']
            def verify_extra(reference, document):
                storage, _, descriptor = _owner_snapshot(wb, reference)
                _need(storage == extra_proof['verified_storage_ref'] and descriptor == extra_proof['descriptor'],
                      'The explicitly selected result changed during follow-up')
                return deepcopy(extra_proof)
            actual_readers['probe'] = lambda selected: probe_retained_result(selected,
                resolve_document=wb.document_read, verify_retention=verify_extra
                ) if selected == ref else prior_probe(selected)
        current['result_access'] = ResultAccess(readers=actual_readers, current_scope_probe=lambda: current)
        return runtime, current, recipients
    def check_review(source, ref, selector, actors):
        from .assist.research_evidence import shared_projection
        # This explicit navigation alone may perform the existing canonical
        # attachment verification. Tools and metadata probes never capture.
        verified = capture_result_verification(wb, ref)
        wrapper = make_result_selection(verified, source_id='selection-' + canonical_hash({'reference': ref, 'selector': selector})[:32],
                                        selection_request=selector)
        _need(wrapper['selector'] == selector, 'Choose an exact canonical result selection')
        runtime, current, recipients = shared(actors, wrapper, verified)
        projected = shared_projection(source, recipients, runtime=runtime, workspace_id=wb.workspace_id, current_scope=current)
        _need(projected['status'] == 'AVAILABLE', 'The original response cannot be shared with these roles')
        for actor in recipients:
            current['result_access'].check_reference(ref, selector,
                selections=current['assignments'][actor]['result_refs'], context=current['recipient_contexts'][actor])
        return {'status': 'AVAILABLE', 'result_selection': wrapper, 'dependency_ids': projected['dependency_ids']}
    result['check_result_review'] = check_review
    # Shared registry/role/provider configuration is deliberately lazy: local
    # Study/history remains usable without participants or configured inference.
    result['shared_context'] = shared
    return result


def transfer(wb, document_id, kind, selection, *, session_id, expected_generation, command_id):
    """Explicit local navigation through existing owners; no Ask or calculation.

    The owner supplies the same current local/shared projection adapters used by
    its display. Serialized model fields are never callbacks or permission proof.
    """
    from .storage import check_id, load_json, save_json
    from .assist.research_evidence import local_projection, shared_projection
    document_id, command_id = map(check_id, (document_id, command_id))
    _need(kind in TRANSFER_SELECTIONS and isinstance(selection, dict) and
          set(selection) == TRANSFER_SELECTIONS[kind], 'Choose a supported stored research selection')
    _need(session_id == wb.session_id and type(expected_generation) is int and expected_generation >= 0,
          'Use the current document owner session and generation')
    owner = wb.discussion_documents
    with wb.desktop._lock, owner._lock(document_id):
        discussion = owner.read(document_id)
        _need(discussion['generation'] == expected_generation, 'The source discussion changed; preserve your current edit')
        factory = getattr(owner, 'research_team_transfer_context', None)
        _need(callable(factory), 'Current research source access is unavailable')
        access = factory(discussion)
        state, resolver = access['state'], access['resolve_payload']
        def local(record):
            checked = local_projection(record, state=state, resolve_payload=resolver,
                                       check_dependency=access['check_local_dependency'])
            _need(checked['status'] == 'AVAILABLE', 'The original research source is unavailable or denied')
            return checked
        if kind == 'study':
            identities = selection['claim_ids']
            rows = {r['id']: r for r in claim_rows(discussion)}
            _need(isinstance(identities, list) and identities and len(set(identities)) == len(identities)
                  and set(identities) <= set(rows), 'Select distinct original research claims')
            for identity in identities:
                record = state['responses'][rows[identity]['response_id']]
                projected = local(record)['projection']
                turn = next(t for t in _turns(discussion) if t['id'] == rows[identity]['turn_id'])
                _need(projected == turn['response'], 'The selected claim differs from the verified original response')
            # The existing helper rechecks all dependencies before opening or
            # recovering the same Study; it never replaces an authored draft.
            return open_study_from_claims(wb, document_id, identities, session_id=session_id,
                expected_generation=expected_generation, command_id=command_id,
                current_scope=lambda deps: local({'dependency_ids': deps})['status'] == 'AVAILABLE')
        signature = canonical_hash({'document_id': document_id, 'kind': kind, 'selection': selection,
            'session_id': session_id, 'generation': expected_generation})
        path = wb.desktop.root / 'research_team_transfers' / (command_id + '.json')
        prior = load_json(path) if path.exists() else None
        _need(prior is None or prior['request_hash'] == signature, 'Transfer command conflicts with another selection')
        if kind == 'result_review':
            origin = proposal_origin(discussion, selection['turn_id'], selection['proposal_index'])
            source_record = state['responses'][origin['response_id']]
            local(source_record)
            plan = wb.numerical_documents.read(check_id(selection['plan_document_id']))
            link = plan_link(origin, plan)
            run = next((r for r in plan['runs'] if r['job_id'] == selection['job_id']), None)
            _need(run is not None and run.get('draft', {}).get('source') == origin['source'],
                  'Select an actual retained run submitted from this exact Plan proposal')
            reference = wb.document_result_reference(plan['id'], check_id(selection['job_id']))
            actors = selection['actor_ids']
            _need(isinstance(actors, list) and actors and len(set(actors)) == len(actors), 'Select distinct recipient roles')
            checked = access['check_result_review'](source_record, reference, selection['selector'], actors)
            _need(isinstance(checked, dict) and checked.get('status') == 'AVAILABLE', 'The selected result cannot be sent to these roles')
            checked = {**checked, 'actor_ids': actors, 'submitted_plan_source': run['draft']['source']}
            result = result_review_draft(discussion, plan_link=link, result_reference=reference,
                selector=selection['selector'], current_scope=lambda *args: checked)
            if prior:
                _need(prior['response'] == result, 'The retained follow-up source changed')
            else:
                save_json(path, {'request_hash': signature, 'response': result})
            return deepcopy(result)
        action_id = check_id(selection['action_id'])
        action = state['actions'].get(action_id, {})
        report = action.get('report', {})
        _need(report.get('status') == 'APPLIED' and report.get('body_ref'), 'Select an actual completed research report')
        runtime, current_scope, recipients = access['shared_context']()
        checked = shared_projection(report, recipients, runtime=runtime,
            workspace_id=wb.workspace_id, current_scope=current_scope)
        _need(checked['status'] == 'AVAILABLE', 'The report inputs cannot be shared in the current scope')
        value = checked['projection']
        _need(isinstance(value, dict) and isinstance(value.get('text'), str), 'The original generated report is unavailable')
        turn = next((t for t in _turns(discussion) if t.get('research_action_id') == action_id), None)
        _need(turn is not None and turn.get('response', {}).get('costorm', {}).get('report') == value,
              'The generated report has no matching retained discussion turn')
        if prior:
            prepared = prior
        else:
            saved = owner.command(document_id, 'document.save', {}, session_id=session_id,
                expected_generation=expected_generation, command_id='C' + canonical_hash(command_id)[:40])['document']
            source_turn = next(t for t in _turns(saved) if t['id'] == turn['id'])
            reference = {'kind': 'expert_turn', 'discussion_id': document_id, 'saved_revision': saved['saved_revision'],
                         'turn_id': source_turn['id'], 'turn_sha256': canonical_hash(source_turn)}
            prepared = {'request_hash': signature, 'document_id': 'B' + signature[:32],
                'reference': reference, 'body': value, 'dependency_ids': checked['dependency_ids'], 'state': 'APPLYING'}
            save_json(path, prepared)
        target = wb.report_documents
        with target._lock(prepared['document_id']):
            identifier = prepared['document_id']
            if (target._folder(identifier) / 'working.json').exists() or target._manifest(identifier):
                document = target.read(identifier)
            else:
                document = target.open(_new_id=identifier, title='연구 보고서')
            if prepared['state'] == 'APPLYING':
                from .report_document import default_draft
                asset = target.capture(identifier, prepared['reference'])
                draft = default_draft()
                draft['sections'] = [{'id': 'R' + signature[:32], 'title': '연구팀 보고서',
                    'text': prepared['body']['text'], 'include': True, 'table': False, 'curve': False, 'asset': asset}]
                target.command(identifier, 'report.update', {'draft': draft}, session_id=session_id,
                    expected_generation=0, command_id='C' + signature[:40])
                document = target.read(identifier)
            save_json(path, {**prepared, 'state': 'SUCCEEDED'})
        return {'document': document, 'status': 'DRAFT_OPENED', 'command_id': command_id,
            'dependency_ids': deepcopy(prepared['dependency_ids']), 'executed': False}
