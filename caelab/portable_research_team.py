"""Declared research-team closure on the existing portable owner pipeline.

No store lookup, provider, job collection or ACL lives here. Current projection
checks are the caller's binding to B's local or recipient-sharing projection. Origin
records remain in the existing byte-exact owner archive, with a separate local
history projection that never authorizes resuming their work.
"""
from __future__ import annotations

from copy import deepcopy
import re

from .storage import canonical_hash

_ASSET = re.compile(r'research-team/(?:[A-Za-z0-9_-]{1,128}/assets/[A-Za-z0-9_-]{1,128}\.json|inputs/V[0-9a-f]{40}\.json|[A-Za-z0-9_-]{1,128}/action\.json)\Z')
_SHA = re.compile(r'[a-f0-9]{64}\Z')
_REF_FIELDS = {
    'phases': ('frozen_draft_ref',),
    'tasks': ('question_ref', 'input_snapshot_ref'),
    'responses': ('raw_response_ref',),
    'projections': ('body_ref',),
    'map_pending': ('conversation_turn_ref', 'journal_ref'),
    'map_checkpoints': ('kb_asset_ref', 'applied_turn_ref'),
    'read_receipts': ('payload_ref',),
    'outputs': ('output_ref', 'payload_ref'),
}


def _state(value):
    if 'discussion' in value:
        return value.get('discussion', {}).get('research_team') or {}
    return value


def _asset(reference):
    if (not isinstance(reference, dict) or set(reference) != {'path', 'sha256'}
            or not isinstance(reference['path'], str) or not _ASSET.fullmatch(reference['path'])
            or not isinstance(reference['sha256'], str) or not _SHA.fullmatch(reference['sha256'])):
        raise ValueError('연구 기록의 정확한 보존 파일을 확인하세요.')
    return deepcopy(reference)


def validate_current_team_view(value, *, project, derived=()):
    """Invoke B's CURRENT whole-dependency check; return checked facets only.

    ``project(record)`` is a trusted caller-supplied adapter for B's local or
    shared_projection, with the current owner or recipient and payload reader.
    A stored AVAILABLE field is never accepted instead of calling it.
    """
    team = _state(value)
    if not team:
        return {'status': 'AVAILABLE', 'facets': {}}
    if team.get('version') != 2:
        raise PermissionError('이전 연구 기록은 현지 새 연구의 권한으로 사용할 수 없습니다.')
    candidates = {}
    for collection in ('responses', 'projections', 'map_checkpoints', 'outputs'):
        for identifier, record in team.get(collection, {}).items():
            # Operation journals prevent duplicate work; they are retained as
            # assets, not presented as independently shareable derived text.
            if collection == 'outputs' and 'dependency_ids' not in record:
                continue
            candidates[(collection, identifier)] = record
    for index, record in enumerate(derived):
        candidates[('derived', str(index))] = record
    for identifier, action in team.get('actions', {}).items():
        report = action.get('report')
        if isinstance(report, dict) and report.get('dependency_ids'):
            candidates[('reports', identifier)] = report
    if candidates and not callable(project):
        raise PermissionError('현재 자료 공유 범위를 확인할 수 없습니다.')
    facets = {}
    for (collection, identifier), record in candidates.items():
        view_record = deepcopy(record)
        if collection == 'map_checkpoints' and view_record.get('kb_asset_ref'):
            view_record['body_ref'] = deepcopy(view_record['kb_asset_ref'])
        checked = project(view_record)
        if (not isinstance(checked, dict) or checked.get('status') not in
                {'AVAILABLE', 'BLOCKED_SCOPE', 'DEPENDENCY_UNVERIFIED'}):
            raise PermissionError('현재 자료 공유 검사가 올바르게 반환되지 않았습니다.')
        if checked['status'] != 'AVAILABLE' and checked.get('projection') is not None:
            raise PermissionError('공유할 수 없는 원문이 표시 결과에 포함되었습니다.')
        # Only B's safe projection can contain content. No private/raw record
        # is copied into a public facet before checking and hidden afterwards.
        facets.setdefault(collection, {})[identifier] = deepcopy(checked)
    return {'status': 'AVAILABLE' if all(row['status'] == 'AVAILABLE'
        for rows in facets.values() for row in rows.values()) else 'PARTIAL', 'facets': facets}


def collect_team_closure(value, *, project, checkpoint_assets=()):
    """Collect DECLARED pins/assets only after the current output check.

    The existing reader subsequently checks/copies each exact file and its
    bytes. Optional action.json references come from the owner's selected
    checkpoint inventory, never a directory walk or a guessed adjacent file.
    """
    team = _state(value)
    if not team:
        return {'references': [], 'assets': []}
    checked = validate_current_team_view(team, project=project)
    if checked['status'] != 'AVAILABLE':
        raise PermissionError('현재 공유할 수 없는 자료에 의존한 연구 내용은 사본에 포함할 수 없습니다.')
    from .research_team_contract import source_closure
    references = {canonical_hash(ref): deepcopy(ref) for ref in source_closure(team)}
    assignments = [row for phase in team.get('phases', {}).values()
                   for row in phase.get('assignments', [])]
    if 'draft' in value:
        assignments += value.get('draft', {}).get('context', {}).get('research_team', {}).get('assignments', [])
    for row in assignments:
        for reference in row.get('source_refs', []):
            references[canonical_hash(reference)] = deepcopy(reference)
        for selection in row.get('result_refs', []):
            reference = selection['reference']
            references[canonical_hash(reference)] = deepcopy(reference)
    return {'references': [references[key] for key in sorted(references)],
            'assets': declared_team_assets(team, checkpoint_assets=checkpoint_assets)}


def declared_team_assets(value, *, checkpoint_assets=()):
    """Validate the owner's declared inventory without reading or granting it.

    Root's existing portable owner verifies every path/hash before retention.
    This inventory does not read content or replace current dependency checks.
    """
    team = _state(value)
    assets = {}
    for reference in team.get('assets', {}).values():
        ref = _asset(reference)
        previous = assets.get(ref['path'])
        if previous is not None and previous != ref:
            raise ValueError('같은 연구 보존 파일에 서로 다른 내용이 선언되었습니다.')
        assets[ref['path']] = ref
    required = list(team.get('result_verifications', {}).values())
    for action in team.get('actions', {}).values():
        report = action.get('report') or {}
        required += [report[key] for key in ('body_ref', 'journal_ref') if report.get(key)]
    for ledger in team.get('public_search_ledgers', {}).values():
        entries = ledger.get('entries', [])
        for entry in entries:
            if entry.get('raw_error_ref'):
                required.append(entry['raw_error_ref'])
    for collection, fields in _REF_FIELDS.items():
        for row in team.get(collection, {}).values():
            for field in fields:
                ref = row.get(field)
                if isinstance(ref, dict) and 'path' in ref:
                    required.append(ref)
            if collection == 'map_pending':
                required += [ref for ref in row.get('cited_information_refs', [])
                             if isinstance(ref, dict) and 'path' in ref]
            if collection == 'responses':
                required += [ref for ref in row.get('proposal_refs', [])
                             if isinstance(ref, dict) and 'path' in ref]
    for reference in required:
        ref = _asset(reference)
        if assets.get(ref['path']) != ref:
            raise ValueError('선택한 원 연구 내용의 필수 보존 파일이 누락되거나 변경되었습니다.')
    for reference in checkpoint_assets:
        ref = _asset(reference)
        previous = assets.get(ref['path'])
        if previous is not None and previous != ref:
            raise ValueError('원 연구 checkpoint 파일의 내용이 다릅니다.')
        assets[ref['path']] = ref
    return [assets[key] for key in sorted(assets)]


def is_team_asset(name):
    return isinstance(name, str) and bool(_ASSET.fullmatch(name))


def apply_team_local_view(owner, document, result):
    """A local user's read facet using the EXISTING owner composition callback.

    Current policy lives in the owner's injected C factory. No role/provider
    configuration is consulted here, and original records/assets are untouched.
    """
    from .research_team_contract import enabled
    current_team = enabled(document.get('draft', {}))
    team = document.get('discussion', {}).get('research_team') or {}
    if team.get('version') != 2:
        if current_team:
            result.setdefault('discussion', {}).setdefault('costorm', {}).update(topics=[], report=None, ready=False)
        return result
    from .assist.research_evidence import local_projection
    factory = getattr(owner, 'research_team_transfer_context', None)
    try:
        if not callable(factory):
            raise PermissionError('현지 자료 열람 연결을 확인할 수 없습니다.')
        context = factory(document)
        def project(record):
            return local_projection(record, state=context['state'], resolve_payload=context['resolve_payload'],
                check_dependency=context['check_local_dependency'])
        checked = validate_current_team_view(document, project=project)
    except (PermissionError, ValueError, OSError, KeyError, TypeError) as error:
        checked = {'status': 'PARTIAL', 'facets': {}}
        result['research_team_read_error'] = str(error)
    result['research_team_local_view'] = checked
    permitted = checked['facets'].get('responses', {})
    discussion = result.setdefault('discussion', {})
    turns = discussion.get('turns', [])
    for index, turn in enumerate(turns):
        identifier, action_id = turn.get('research_response_id'), turn.get('research_action_id')
        if not identifier and not action_id:
            continue
        facet = (permitted.get(identifier, {}) if identifier else
                 checked['facets'].get('reports', {}).get(action_id, {}))
        if facet.get('status') != 'AVAILABLE':
            turns[index] = {key: deepcopy(turn[key]) for key in ('id', 'author', 'topic_id', 'classification',
                'research_response_id', 'research_action_id', 'research_phase_id') if key in turn}
            turns[index].update(status='SOURCE_UNAVAILABLE', text='현재 자료 접근 범위에서 이 발언을 읽을 수 없습니다.',
                response={'status': 'SOURCE_UNAVAILABLE', 'answer': None})
        elif facet.get('reason_code') == 'SOURCE_UNAVAILABLE':
            turn['source_status'] = 'SOURCE_UNAVAILABLE'
    result['turns'] = deepcopy(turns)
    if not current_team:
        return result  # Past team turns remain checked; current legacy views keep their own presentation.
    cfg = document.get('draft', {}).get('context', {}).get('research_team') or {}
    phase = team.get('phases', {}).get(cfg.get('phase_id') or cfg.get('parent_phase_id'), {})
    protocol = discussion.setdefault('costorm', {})
    # A new/unstarted phase has no checked map or report yet. Previous legacy
    # presentation caches are not a fallback for the current team's facets.
    protocol.update(topics=[], report=None, ready=False)
    map_id = phase.get('current_map_revision')
    if map_id:
        facet = checked['facets'].get('map_checkpoints', {}).get(map_id, {})
        if facet.get('status') == 'AVAILABLE':
            from .assist.costorm import presentation
            map_state = {'knowledge_base': facet['projection']}
            topic = phase.get('objective') or cfg.get('objective')
            if not topic and (facet['projection'].get('tree') or {}).get('name') == 'root':
                topic = '전체 논점'
            if topic:
                map_state['runner_argument'] = {'topic': topic}
            protocol['topics'] = presentation(map_state)['topics']
            protocol['ready'] = True
        else:
            protocol.update(topics=[], ready=False, source_status='SOURCE_UNAVAILABLE')
    report_id = phase.get('current_report_action')
    if report_id:
        facet = checked['facets'].get('reports', {}).get(report_id, {})
        protocol['report'] = deepcopy(facet['projection']) if facet.get('status') == 'AVAILABLE' else None
        if facet.get('status') != 'AVAILABLE':
            protocol['source_status'] = 'SOURCE_UNAVAILABLE'
    return result


def project_archived_team(document):
    """Current history projection only; never alter an original archive asset."""
    projected = deepcopy(document)
    team = projected.get('discussion', {}).get('research_team')
    if not team:
        return projected
    origin = {'actions': {}, 'attempts': {}, 'map_pending': {}}
    for identifier, action in team.get('actions', {}).items():
        origin['actions'][identifier] = canonical_hash(action)
        action['origin'] = 'archived_origin'
    for identifier, attempt in team.get('attempts', {}).items():
        origin['attempts'][identifier] = canonical_hash(attempt)
    for identifier, pending in team.get('map_pending', {}).items():
        origin['map_pending'][identifier] = {'status': pending.get('status'), 'sha256': canonical_hash(pending)}
        if pending.get('status') != 'APPLIED':
            pending['status'] = 'ARCHIVED_PENDING'
    team['archived_origin'] = origin
    # Undo/Redo must not reinstate a source phase as local execution authority.
    for draft in [projected.get('draft', {}), *projected.get('_undo', []), *projected.get('_redo', [])]:
        cfg = draft.get('context', {}).get('research_team')
        if isinstance(cfg, dict):
            cfg['parent_phase_id'] = cfg.get('phase_id') or cfg.get('parent_phase_id')
            cfg['phase_id'] = None
            cfg['requested_next'] = None
    return projected
