"""Instance proxy and atomic, replayable transactions for the pinned KB.

Raw role turns are immutable. A failed vendor insertion touches only a temporary
KB/turn, while successful completions survive through existing owner assets.
"""
from copy import deepcopy
from functools import partial

from ..execution_control import check_cancelled, ExecutionCancelled, ExecutionCleanupFailed
from ..storage import canonical_hash


def pack_turn(turn):
    value = deepcopy(turn.to_dict())
    value['cited_information'] = {str(key): deepcopy(info.to_dict()) for key, info in (turn.cited_info or {}).items()}
    return value


def unpack_turn(value):
    from ._vendor.costorm.dataclass import ConversationTurn
    from ._vendor.costorm.interface import Information
    turn = ConversationTurn.from_dict(deepcopy(value))
    # Pinned from_dict joins role and description with ': '; restore the saved
    # description exactly instead of introducing a leading space on each read.
    turn.role_description = value['role_description']
    turn.cited_info = {int(key): Information.from_dict(info) for key, info in value.get('cited_information', {}).items()}
    return turn


def _asset(binding, identifier, value):
    return binding.checkpoint('asset-' + identifier,
        {'asset': {'id': identifier, 'payload': deepcopy(value)}})['asset_ref']


class DeferredKnowledgeBase:
    def __init__(self, approved_snapshot, *, binding):
        self._snapshot, self._binding = deepcopy(approved_snapshot), binding

    def to_dict(self):
        self._binding.verify_dependencies(self._binding.base_dependencies())
        return deepcopy(self._snapshot)

    def update_from_conv_turn(self, conv_turn, allow_create_new_node=True, insert_under_root=False):
        event = getattr(conv_turn, '_team_event', None)
        if not event:raise PermissionError('A role checkpoint must precede a shared turn')
        register_pending(self._binding, projection=event,
            turn_copy=conv_turn, flags={'allow_create_new_node': allow_create_new_node,
                                       'insert_under_root': insert_under_root})

    def reorganize(self):
        self._binding.checkpoint('map-reorganize-request', {'map_service_requested': True})

    def to_report(self):
        if not getattr(self._binding, 'report_service', False):
            raise PermissionError('보고서 정리는 명시한 보고서 작업에서 실행하세요.')
        return self._binding.report_from_snapshot(self._snapshot)


def register_pending(binding, *, projection, turn_copy, flags):
    state = binding.read_checkpoint()
    identifier = 'M' + canonical_hash({'phase': binding.phase_id, 'event': projection['event_id']})[:32]
    if identifier in state['map_pending']:return deepcopy(state['map_pending'][identifier])
    binding.verify_dependencies(projection['dependency_ids'])
    packed = pack_turn(turn_copy)
    ref = _asset(binding, 'U' + identifier, packed)
    state = binding.read_checkpoint()
    pending = {'id': identifier, 'phase_id': binding.phase_id,
        'response_id': projection['response_id'], 'shared_projection_id': projection['id'],
        'event_id': projection['event_id'], 'conversation_turn_ref': ref,
        'cited_information_refs': deepcopy(packed['cited_information']),
        'dependency_ids': deepcopy(projection['dependency_ids']),
        'allow_create_new_node': flags['allow_create_new_node'], 'insert_under_root': flags['insert_under_root'],
        'base_map_revision': None, 'journal_ref': None, 'status': 'PENDING',
        'last_error': None, 'applied_map_revision': None}
    state['map_pending'][identifier] = pending
    phase = state['phases'][binding.phase_id]
    if projection['event_id'] not in phase['shared_turn_ids']:phase['shared_turn_ids'].append(projection['event_id'])
    binding.checkpoint('pending-' + identifier, {'state': state})
    return deepcopy(pending)


def rebuild_shared_history(binding):
    state = binding.read_checkpoint(); phase = state['phases'][binding.phase_id]
    history = []
    pending_by_event = {row['event_id']: row for row in state['map_pending'].values() if row['phase_id'] == binding.phase_id}
    for event in phase['shared_turn_ids']:
        pending = pending_by_event[event]
        try:
            binding.verify_dependencies(pending['dependency_ids'])
        except PermissionError:
            # Omit revoked input from the runtime view; preserve its saved
            # event and the whole-closure gate for map/report derivations.
            continue
        turn = unpack_turn(binding.resolve_payload(pending['conversation_turn_ref']))
        turn._team_event = {'event_id': event, 'id': pending['shared_projection_id'],
            'response_id': pending['response_id'], 'dependency_ids': pending['dependency_ids']}
        history.append(turn)
    return history


def apply_pending_map(pending_id, *, binding, budget_slice):
    from ._vendor.costorm.dataclass import KnowledgeBase
    state = binding.read_checkpoint(); pending = state['map_pending'][pending_id]
    phase = state['phases'][binding.phase_id]
    previous = phase['current_map_revision']
    result = {'status': 'FAILED', 'pending_id': pending_id, 'previous_revision': previous,
        'committed_revision': None, 'completion_receipts': [], 'error': None}
    if pending['status'] == 'APPLIED':
        return {**result, 'status': 'APPLIED', 'committed_revision': pending['applied_map_revision']}
    if state['actions'][binding.action_id]['origin'] != 'local' or pending['status'] == 'ARCHIVED_PENDING':
        raise PermissionError('사본의 원 지도 작업은 현지 실행 권한이 아닙니다.')
    by_event = {row['event_id']: row for row in state['map_pending'].values() if row['phase_id'] == binding.phase_id}
    first = next((by_event[event] for event in phase['shared_turn_ids']
                  if by_event[event]['status'] != 'APPLIED'), None)
    if first is not None and first['id'] != pending_id:
        raise PermissionError('가장 먼저 보존한 지도 작업부터 처리해야 합니다.')
    # Fix base on first attempt. Explicit None represents the empty first KB.
    if pending['status'] == 'PENDING':pending['base_map_revision'] = previous
    if pending['base_map_revision'] != previous:
        raise ValueError('Pending 지도는 원래의 base 개정에서만 이어갈 수 있습니다.')
    dependencies = sorted(set(pending['dependency_ids'] + binding.base_dependencies()))
    journal = binding.resolve_payload(pending['journal_ref']) if pending['journal_ref'] else []
    try:
        binding.verify_dependencies(dependencies); check_cancelled()
        if budget_slice is None:
            raise RuntimeError('WAITING_BUDGET: 지도 처리 몫이 없습니다.')
        pending['status'] = 'APPLYING'; state['map_pending'][pending_id] = pending
        binding.checkpoint('map-start-' + pending_id + '-' + binding.attempt_id, {'state': state})
        # Success journal entries are published one by one, including a prefix
        # completed before a later budget/cancel/model/KB failure.
        def save_journal():
            identifier = 'J' + canonical_hash({'pending': pending_id, 'journal': journal})[:32]
            ref = _asset(binding, identifier, journal)
            current = binding.read_checkpoint(); current['map_pending'][pending_id]['journal_ref'] = ref
            binding.checkpoint('map-journal-' + identifier + '-' + canonical_hash(current)[:20], {'state': current})
        lm = binding.make_completion(budget_slice, journal, pending_id, previous, dependencies, save_journal)
        snapshot = binding.approved_snapshot()
        temporary = (KnowledgeBase.from_dict(snapshot, lm, 6, binding.encoder) if snapshot else
                     KnowledgeBase(binding.topic, lm, 6, binding.encoder))
        # The actual pinned insertion module exposes a call-level max_thread.
        temporary.information_insert_module = partial(temporary.information_insert_module, max_thread=1)
        turn = unpack_turn(binding.resolve_payload(pending['conversation_turn_ref']))
        cited = dict(turn.cited_info)
        temporary.update_from_conv_turn(turn, allow_create_new_node=pending['allow_create_new_node'],
                                       insert_under_root=pending['insert_under_root'])
        check_cancelled(); binding.verify_dependencies(dependencies)
        snapshot = temporary.to_dict()
        # Validate source/citation dictionary roundtrip before making it active.
        reconstructed = KnowledgeBase.from_dict(snapshot, lm, 6, binding.encoder).to_dict()
        if canonical_hash(reconstructed) != canonical_hash(snapshot):raise ValueError('지도 roundtrip이 다릅니다.')
        identifier = 'C' + canonical_hash({'pending': pending_id, 'base': previous, 'kb': snapshot})[:32]
        kb_ref = _asset(binding, 'K' + identifier, snapshot)
        derived_turn_ref = _asset(binding, 'D' + identifier, turn.to_dict())
        citation_map = {str(old): info.citation_uuid for old, info in cited.items()}
        checkpoint = {'id': identifier, 'previous_id': previous, 'base_revision': previous,
            'applied_pending_ids': [pending_id], 'kb_asset_ref': kb_ref, 'dependency_ids': dependencies,
            'citation_map': citation_map, 'created_by_attempt': binding.attempt_id,
            'applied_turn_ref': derived_turn_ref}
        binding.verify_dependencies(dependencies)
        binding.checkpoint('map-commit-' + pending_id, {'map_commit': {'id': identifier,
            'previous_revision': previous, 'pending_id': pending_id, 'checkpoint': checkpoint}})
        return {**result, 'status': 'APPLIED', 'committed_revision': identifier,
                'completion_receipts': [row['key'] for row in journal]}
    except (Exception,) as error:
        # An acknowledged owner CAS can outlive a lost local return value.
        # Reconcile the committed pointer rather than overwriting APPLIED and
        # inserting the same source turn a second time on explicit retry.
        current = binding.read_checkpoint()
        committed = current['map_pending'][pending_id]
        if committed['status'] == 'APPLIED':
            return {**result, 'status': 'APPLIED', 'committed_revision': committed['applied_map_revision'],
                    'completion_receipts': [row['key'] for row in journal],
                    'recovered_after_response_loss': True}
        rejected = getattr(binding, 'last_successful_completion_key', None)
        if isinstance(error, ValueError) and rejected and any(row['key'] == rejected for row in journal):
            # The original journal asset remains immutable forensic evidence.
            # Only a text rejected before the next scope/commit check leaves
            # the active replay set; other successful completions stay pinned.
            journal[:] = [row for row in journal if row['key'] != rejected]
            save_journal()
            current = binding.read_checkpoint()
            current['map_pending'][pending_id]['invalid_completion_key'] = rejected
        status = ('BLOCKED_SCOPE' if isinstance(error, PermissionError) else
                  'WAITING_TIME' if isinstance(error, (ExecutionCancelled, ExecutionCleanupFailed)) else
                  getattr(error, 'status', 'WAITING_BUDGET' if 'budget' in str(error).lower() else 'FAILED'))
        current['map_pending'][pending_id].update(status=status, last_error={'type': type(error).__name__, 'message': str(error)})
        binding.checkpoint('map-wait-' + pending_id + '-' + binding.attempt_id,
                           {'state': current})
        if isinstance(error, (ExecutionCancelled, ExecutionCleanupFailed)):raise
        return {**result, 'status': status, 'error': {'type': type(error).__name__, 'message': str(error)},
                'completion_receipts': [row['key'] for row in journal]}
