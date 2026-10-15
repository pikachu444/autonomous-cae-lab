"""Bounded role schedule on ExpertRuntime and the pinned CoStormRunner.

The action owns one root budget, one model at a time and durable checkpoints.
Opening/serializing a team never invokes this module's execution entry point.
"""
from copy import deepcopy
import time

from ..execution_control import check_cancelled, ExecutionCancelled, ExecutionCleanupFailed
from ..storage import canonical_hash
from ..research_team_contract import FINISHED_TASKS


class TeamWaiting(RuntimeError):
    def __init__(self, status, message):
        self.status = status
        super().__init__(message)


def restore_task_reads(binding, context, raw_ref):
    """Supply original task reads for tool-free finalization, checking them now."""
    from .research_evidence import check_receipt
    scope = {**binding.current_scope_probe(), 'generation_ledger': binding.generation_ledger,
             'result_access': binding.result_access}
    state = scope['ledger_state']
    previous = next((row for row in state['responses'].values() if row['task_id'] == binding.task_id
                     and row['raw_response_ref'] == raw_ref), None)
    if (previous is None or previous.get('phase_id') != binding.phase_id
            or previous.get('actor_id') != binding.actor_id):
        raise PermissionError('미완료 응답의 실제 원 과제 읽기를 찾을 수 없습니다.')
    result = deepcopy(context); supplied = []
    ledger = binding.generation_ledger
    for identifier in previous['read_receipt_ids']:
        receipt = state['read_receipts'][identifier]
        check_receipt(receipt, runtime=ledger.runtime, workspace_id=ledger.workspace_id,
                      current_scope=scope, recipients=[binding.actor_id])
        payload = scope['resolve_payload'](receipt['payload_ref'])
        ref = deepcopy(receipt['source_ref'])
        marker = ({**ref, 'selector': deepcopy(receipt['returned_selector']), 'read_receipt_id': identifier}
                  if receipt['kind'] == 'result' else ref)
        row = {'read_receipt_id': identifier, 'source': marker, 'returned': payload,
               'read_level': receipt['read_level'], 'limitations': deepcopy(receipt['limitations'])}
        ledger.add_supplied({'kind': 'tool_output', 'exact_ref': {'read_receipt_id': identifier}, 'payload': row},
                            dependencies=receipt['dependency_ids'], origin='history')
        if identifier not in ledger.read_receipt_ids:ledger.read_receipt_ids.append(identifier)
        supplied.append(row)
    result['retained_task_reads'] = supplied
    feedback = {'task_id': binding.task_id, 'response_id': previous['id'],
                'raw_response_ref': deepcopy(raw_ref), 'status': previous['validation']['status'],
                'errors': deepcopy(previous['validation'].get('errors', []))}
    ledger.add_supplied({'kind': 'tool_output', 'exact_ref': {'response_id': previous['id'], 'field': 'validation'},
                        'payload': feedback}, dependencies=previous['dependency_ids'], origin='history')
    result['owner_validation_feedback'] = feedback
    return result


def cited_information(response, record, state, scope):
    """Map body [n] to its nth verified source, retaining uncited reads after it."""
    from ..research_team_contract import match_result_citation
    from .research_evidence import to_costorm_information
    receipts = [state['read_receipts'][identifier] for identifier in record['read_receipt_ids']]
    ordered = []
    for source in response.get('sources', []):
        if 'job_id' in source or 'run_id' in source:
            chosen = match_result_citation(source, receipts)
        else:
            keys = ('document_id', 'revision', 'locator') if 'document_id' in source else ('paper_id', 'locator')
            chosen = next((row for row in reversed(receipts)
                if all(row.get('source_ref', {}).get(key) == source.get(key) for key in keys)), None)
        if chosen is None:raise ValueError('본문 인용과 실제 읽은 원 자료를 연결할 수 없습니다.')
        ordered.append(chosen)
    used = {row['id'] for row in ordered}
    ordered.extend(row for row in receipts if row['id'] not in used)
    return {index + 1: to_costorm_information(row, current_scope=scope) for index, row in enumerate(ordered)}


def plan_action(frozen_phase, tasks, *, limits, pending):
    """Allocate before calling a host; future target IDs may be resolved later."""
    model_limit = min(8, int(limits.get('model_calls', 4)))
    tools = int(limits.get('tool_calls', 8))
    turn_limit = frozen_phase.get('turn_limit', 8)
    tickets = []; remaining = model_limit; tool_remaining = tools
    eligible = sorted((task for task in tasks if not task.get('optional_consult') and task['status'] not in FINISHED_TASKS
                       and not (task.get('continuation') or {}).get('cleanup_unconfirmed')
                       and not (task['status'] == 'WAITING_REPAIR' and (task.get('continuation') or {}).get('repair_used'))
                       and not (task['status'] == 'OUTCOME_UNCONFIRMED' and limits.get('kind') != 'retry')),
                      key=lambda task: task.get('priority', 0))
    for task in eligible:
        if len(tickets) >= turn_limit:break
        scheduled = {row['task_id'] for row in tickets}
        done = {row['id'] for row in tasks if row['status'] in FINISHED_TASKS}
        if not set(task.get('depends_on', [])).issubset(done | scheduled):continue
        if task['kind'] == 'ANSWER' and not task.get('user_question') and not set(task['depends_on']).issubset(done):
            continue  # The actual question determines its recipient, before allocating its ticket.
        kind = ('FINALIZE' if task['status'] == 'WAITING_FINAL' else
                'REPAIR' if task['status'] == 'WAITING_REPAIR' else
                'QUESTION' if task['kind'] in {'QUESTION', 'PROBLEM_DEFINITION'} else
                'ANSWER' if task['kind'] == 'ANSWER' else 'EVIDENCE')
        steps = 1 if kind in {'FINALIZE', 'REPAIR', 'QUESTION'} else 2
        tool_calls = 1 if kind in {'EVIDENCE', 'ANSWER'} else 0
        if steps > remaining or tool_calls > tool_remaining:
            continue
        tickets.append({'id': 'K' + canonical_hash({'action': limits.get('action_id'), 'task': task['id']})[:30],
            'task_id': task['id'], 'actor_id': task['actor_id'], 'kind': kind,
            'invocation_steps': steps, 'model_steps': steps, 'tool_calls': tool_calls,
            'consultations': 0, 'protected_for_others': True, 'status': 'PENDING'})
        remaining -= steps; tool_remaining -= tool_calls
        consult_id = task.get('consult_target_task_id')
        if consult_id and int(limits.get('consultations', 0)) > 0 and remaining >= 2 and tool_remaining >= 1:
            target = next(row for row in tasks if row['id'] == consult_id)
            tickets[-1]['consultations'] = 1
            tickets.append({'id': 'K' + canonical_hash({'action': limits['action_id'], 'task': consult_id})[:30],
                'task_id': consult_id, 'actor_id': target['actor_id'], 'kind': 'EVIDENCE',
                'invocation_steps': 2, 'model_steps': 2, 'tool_calls': 1,
                'consultations': 0, 'protected_for_others': True, 'status': 'PENDING',
                'consult_parent': task['id']})
            remaining -= 2; tool_remaining -= 1
    return {'action_id': limits['action_id'], 'model_limit': model_limit, 'tool_limit': tools,
        'consult_limit': int(limits.get('consultations', 0)),
        'deadline': limits.get('deadline'), 'turn_limit': turn_limit, 'tickets': tickets,
        'service_pool': {'model_steps': remaining, 'tool_calls': tool_remaining,
                         'pending_ids': list(pending)}, 'revision': 1}


def bind_allocation(root, plan, *, checkpoint, control_status):
    # These identities live only in this worker; JSON cannot manufacture them.
    root._team_plan = plan
    root._team_checkpoint = checkpoint
    root._team_control = control_status
    root._team_slices = []
    root._team_actor_reservations = {}
    root._team_observed_hosts = 0


class BudgetSlice:
    def __init__(self, root, ticket):
        if not hasattr(root, '_team_plan') or not any(row is ticket for row in root._team_plan['tickets']):
            raise PermissionError('Budget ticket was not issued for this action')
        self.root, self.ticket = root, ticket
        self.model_calls, self.tool_calls = ticket['model_steps'], ticket['tool_calls']
        self.consultations = ticket['consultations']
        self.used_models = self.used_tools = self.used_consultations = 0
        self.used_model_host_invocations = 0
        self.lock = root.lock
        self.active = True
        root._team_slices.append(self)

    @property
    def deadline(self):return self.root.deadline
    @property
    def used_evaluations(self):return self.root.used_evaluations
    @used_evaluations.setter
    def used_evaluations(self, value):self.root.used_evaluations = value

    def _check(self, *, starting=False):
        check_cancelled()
        if not self.active or self not in self.root._team_slices:
            raise PermissionError('Inactive research allocation')
        control = self.root._team_control()
        if control.get('paused') or control.get('intervened'):
            raise TeamWaiting('WAITING_TIME', '사용자 개입 또는 일시 정지를 확인한 뒤 계속하세요.')
        if time.monotonic() + (5 if starting else 0) >= self.deadline:
            raise TeamWaiting('WAITING_TIME', '남은 시간으로 새 응답을 시작할 수 없습니다.')

    def _reserve_locked(self, root, *, allowed_consultations=0, correction=False):
        if root is not self.root or not any(row is self.ticket for row in root._team_plan['tickets']):
            raise PermissionError('Allocation belongs to another action')
        self._check(starting=True)
        kind = self.ticket['kind']
        if correction and kind not in {'REPAIR', 'FINALIZE', 'MAP_SERVICE', 'REPORT_SERVICE'}:
            raise TeamWaiting('WAITING_BUDGET', '형식 교정에는 별도 배정한 과제가 필요합니다.')
        steps = 1 if correction else self.ticket['invocation_steps']
        if self.used_models + steps > self.model_calls or root.used_models + steps > root.model_calls:
            raise TeamWaiting('WAITING_BUDGET', '이번 응답의 모델 처리 상한에 도달했습니다.')
        # Every ticket is protected by its preallocated ceiling. An actor cannot
        # take unstarted peers' steps or the separately allocated service pool.
        protected = sum(row['model_steps'] for row in root._team_plan['tickets']
                        if row is not self.ticket and row['status'] == 'PENDING')
        if root.model_calls - root.used_models - steps < protected:
            raise TeamWaiting('WAITING_BUDGET', '다른 담당자의 예약 범위를 사용할 수 없습니다.')
        root.used_models += steps; self.used_models += steps
        root.used_model_host_invocations += 1; self.used_model_host_invocations += 1
        actor = self.ticket['actor_id']
        root._team_actor_reservations[actor] = root._team_actor_reservations.get(actor, 0) + steps
        self.ticket['status'] = 'RESERVED'
        receipt = {'ticket_id': self.ticket['id'], 'task_id': self.ticket['task_id'],
            'actor_id': actor, 'steps': steps, 'root_used_models': root.used_models,
            'host_started': False}
        # Failure retains conservative counters; host starts only after return.
        root._team_checkpoint('reserve-' + self.ticket['id'] + '-' + str(self.used_model_host_invocations),
                              {'reservation': receipt})
        return steps

    def reserve_provider_steps(self, *, allowed_consultations=0, correction=False):
        return self.root.reserve_provider_steps(allowed_consultations=allowed_consultations,
                                                correction=correction, _allocation=self)

    def consume(self, kind):
        with self.lock:
            self._check(starting=kind == 'model')
            attr, limit = {'model': ('used_models', self.model_calls),
                'tool': ('used_tools', self.tool_calls),
                'consultation': ('used_consultations', self.consultations)}[kind]
            root_limit = {'model': self.root.model_calls, 'tool': self.root.tool_calls,
                          'consultation': self.root.consultations}[kind]
            if getattr(self, attr) >= limit or getattr(self.root, attr) >= root_limit:
                raise TeamWaiting('WAITING_BUDGET', kind + ' 처리 상한에 도달했습니다.')
            setattr(self, attr, getattr(self, attr) + 1)
            setattr(self.root, attr, getattr(self.root, attr) + 1)
            self.ticket['status'] = 'RUNNING'
            self.root._team_checkpoint('consume-' + self.ticket['id'] + '-' + kind + '-' + str(getattr(self, attr)),
                {'debit': {'ticket_id': self.ticket['id'], 'kind': kind, 'used': getattr(self, attr)}})

    def observe_host(self):
        with self.lock:
            self.root._team_observed_hosts += 1
            self.root._team_checkpoint('host-' + self.ticket['id'] + '-' + str(self.root._team_observed_hosts),
                {'observed_host_invocation': {'ticket_id': self.ticket['id'],
                    'actor_id': self.ticket['actor_id']}})


def service_slice(root, plan, kind, actor_id):
    pool = plan['service_pool']
    remaining = min(pool['model_steps'], root.model_calls - root.used_models)
    if remaining < 1:return None
    ticket = {'id': 'K' + canonical_hash({'action': plan['action_id'], 'service': kind,
        'index': len(plan['tickets'])})[:30], 'task_id': None, 'actor_id': actor_id, 'kind': kind,
        'invocation_steps': 1, 'model_steps': remaining, 'tool_calls': 0,
        'consultations': 0, 'protected_for_others': False, 'status': 'PENDING'}
    plan['tickets'].append(ticket); pool['model_steps'] -= remaining
    root._team_checkpoint('plan-service-' + ticket['id'], {'allocation_plan': deepcopy(plan)})
    return BudgetSlice(root, ticket)


class _MapContext:
    """Internal instance adapter; not serialized or accepted from a request."""
    def __init__(self, runtime, context, workspace_id, trusted, root_budget, topic):
        from ._vendor.costorm.vectors import LocalEncoder
        self.runtime, self.context, self.workspace_id = runtime, context, workspace_id
        self.trusted, self.root_budget, self.topic = trusted, root_budget, topic
        self.phase_id, self.action_id, self.attempt_id = trusted.phase_id, trusted.action_id, trusted.attempt_id
        self.encoder = LocalEncoder()
        self.read_checkpoint, self.checkpoint = trusted.read_checkpoint, trusted.checkpoint
        self.resolve_payload = trusted.resolve_payload
        self.report_service = False
        self.last_successful_completion_key = None

    def approved_snapshot(self):
        state = self.read_checkpoint(); revision = state['phases'][self.phase_id]['current_map_revision']
        return self.resolve_payload(state['map_checkpoints'][revision]['kb_asset_ref']) if revision else None

    def base_dependencies(self):
        state = self.read_checkpoint(); revision = state['phases'][self.phase_id]['current_map_revision']
        return deepcopy(state['map_checkpoints'][revision]['dependency_ids']) if revision else []

    def verify_dependencies(self, dependencies):
        self.last_successful_completion_key = None
        from .research_evidence import shared_projection
        state = self.read_checkpoint(); phase = state['phases'][self.phase_id]
        probe = self.trusted.current_scope_probe()
        result = shared_projection({'dependency_ids': dependencies, 'answer': ''},
            [row['expert_id'] for row in phase['assignments']], runtime=self.runtime,
            workspace_id=self.workspace_id, current_scope={**probe, 'ledger_state': state})
        if result['status'] != 'AVAILABLE':raise PermissionError('현재 자료 범위로 이 지도를 공유할 수 없습니다.')

    def make_completion(self, slice_budget, journal, component, base, dependencies, save_journal):
        from .costorm import Completion
        parent = self
        phase = self.read_checkpoint()['phases'][self.phase_id]
        actor = phase['assignments'][0]['expert_id']
        config = self.runtime.runtime.for_expert(actor)
        context = deepcopy(self.context)
        context['_source_grants'] = deepcopy(context.get('selected_sources', []))
        instructions = 'Team map transaction ' + canonical_hash({'phase': self.phase_id,
            'component': component, 'base': base, 'actor': actor, 'dependencies': dependencies})
        class DurableCompletion(Completion):
            def before_model_input(self, full):
                with self.lock:
                    parent.verify_dependencies(dependencies)
                    supplied = {'prompt': full, 'model': config.model}
                    identifier = 'M' + canonical_hash({'component': component, 'input': supplied})[:40]
                    encoded = __import__('json').dumps(supplied, ensure_ascii=False, sort_keys=True,
                                                       separators=(',', ':')).encode('utf-8')
                    manifest = {'id': identifier, 'owner_id': parent.trusted.owner_id,
                        'phase_id': parent.phase_id, 'task_id': 'service-' + component, 'actor_id': actor,
                        'attempt_id': parent.attempt_id, 'host_invocation_id': identifier,
                        'mode': 'report_service' if component.startswith('report-') else 'map_service',
                        'payload_digest': canonical_hash(supplied), 'payload_bytes': len(encoded),
                        'dependency_ids': deepcopy(dependencies), 'coverage': 'COMPLETE_SUPPLIED_INPUT', 'status': 'SUPPLIED'}
                    # A replay keeps the original invocation manifest exactly.
                    if identifier not in parent.read_checkpoint()['manifests']:
                        parent.checkpoint('service-input-' + identifier, {'manifests': {identifier: manifest}})
            def __call__(self, prompt, **kwargs):
                with self.lock:
                    if len(journal) >= 32 and not any(row.get('prompt', '').endswith(prompt) for row in journal):
                        raise RuntimeError('MAP_COMPLEXITY_LIMIT')
                    before = len(journal)
                    value = super().__call__(prompt, **kwargs)
                    from ._vendor.costorm.prompting import last_completion_key
                    parent.last_successful_completion_key = last_completion_key.get()
                    if len(journal) != before:save_journal()
                    return value
        return DurableCompletion(self.runtime, config, context, self.workspace_id,
            config.transmission.get('collections', []) if config.transmission else [],
            slice_budget, journal, instructions, lambda: parent.verify_dependencies(dependencies))

    def report_from_snapshot(self, snapshot):
        from ._vendor.costorm.dataclass import KnowledgeBase
        return KnowledgeBase.from_dict(snapshot, self.report_completion, 6, self.encoder).to_report()


class ConfiguredExpertAgent:
    def __init__(self, runtime, trusted, task, budget_slice, *, workspace_id, map_binding):
        self.runtime, self.trusted, self.task = runtime, trusted, deepcopy(task)
        self.budget_slice, self.workspace_id, self.map_binding = budget_slice, workspace_id, map_binding

    def generate_utterance(self, knowledge_base, conversation_history):
        from .research_evidence import shared_projection, to_costorm_information, check_receipt
        from ._vendor.costorm.dataclass import ConversationTurn
        trusted = self.trusted; state = trusted.read_checkpoint(); task = state['tasks'][self.task['id']]
        if task['status'] in FINISHED_TASKS:return None
        phase = state['phases'][trusted.phase_id]
        if task['id'] not in phase['initial_task_ids'] and any(
                state['tasks'][identifier]['status'] not in FINISHED_TASKS for identifier in phase['initial_task_ids']):
            raise PermissionError('다른 담당자의 최초 조사가 아직 끝나지 않았습니다.')
        binding = trusted.make_role_binding(task, self.budget_slice, runtime=self.runtime, workspace_id=self.workspace_id)
        # Ignore upstream shared KB/history during INITIAL_RESEARCH. B builds
        # the independent context; initial sessions are per task, not per role.
        context = deepcopy(binding.generation_ledger.context)
        context['research_task'] = deepcopy(task)
        question = task['question_ref']['text']
        try:
            response = self.runtime._run_approved_role(task['actor_id'], question, context,
                binding.role_session_id, workspace_id=self.workspace_id, budget=self.budget_slice,
                visited=[task['actor_id']], binding=binding)
        except (ExecutionCancelled, ExecutionCleanupFailed) as error:
            current = trusted.read_checkpoint()
            current['tasks'][task['id']].update(status='OUTCOME_UNCONFIRMED',
                continuation={'error_type': type(error).__name__, 'message': str(error),
                              'cleanup_unconfirmed': isinstance(error, ExecutionCleanupFailed)})
            trusted.checkpoint('role-unconfirmed-' + task['id'] + '-' + trusted.attempt_id, {'state': current})
            raise
        record = response.get('research_response')
        if not isinstance(record, dict):
            # Transport/preflight failure remains a raw event; no synthetic
            # successful role response and no automatic host retry.
            record = binding.finalize_response(response, {'status': 'INCOMPLETE',
                'errors': [response.get('reason') or '역할 응답이 완료되지 않았습니다.'], 'engineering_qualification': 'UNKNOWN'})
            state = trusted.read_checkpoint(); task = state['tasks'][task['id']]
            state['responses'][record['id']] = record
            task.update(status='WAITING_FINAL' if binding.generation_ledger.read_receipt_ids else 'BLOCKED_SCOPE',
                continuation={'raw_response_ref': record['raw_response_ref'], 'reason': response.get('reason')})
            trusted.checkpoint('role-stopped-' + record['id'], {'state': state})
            return None
        state = trusted.read_checkpoint(); state['responses'][record['id']] = deepcopy(record)
        task = state['tasks'][task['id']]
        valid = record['validation'].get('status') == 'VALID' and response.get('status') == 'ANSWERED'
        task.update(status='COMPLETED' if valid else 'WAITING_REPAIR',
            completed_response_id=record['id'] if valid else None,
            continuation=None if valid else {'raw_response_ref': record['raw_response_ref'], 'repair_used': self.budget_slice.ticket['kind'] == 'REPAIR'})
        if valid:
            # FINALIZE/REPAIR keep actual earlier reads of this same task, never
            # reads made by a different independent investigator.
            prior_reads = [identifier for prior in state['responses'].values() if prior['task_id'] == task['id']
                           for identifier in prior['read_receipt_ids']]
            record['read_receipt_ids'] = list(dict.fromkeys(prior_reads + record['read_receipt_ids']))
            record['proposal_refs'] = [{'response_id': record['id'], 'proposal_index': index,
                'sha256': canonical_hash(proposal)} for index, proposal in enumerate(response.get('proposed_actions', []))]
            record['claim_refs'] = [{'id': 'C' + canonical_hash({'response': record['id'], 'index': i})[:32],
                'index': i, 'response_id': record['id']} for i, _ in enumerate(response.get('research_reply', {}).get('claims', []))]
            state['responses'][record['id']] = deepcopy(record)
        phase = state['phases'][trusted.phase_id]
        phase['initial_barrier'] = 'OPEN' if all(state['tasks'][i]['status'] in FINISHED_TASKS for i in phase['initial_task_ids']) else 'CLOSED'
        trusted.checkpoint('role-complete-' + record['id'], {'state': state})
        if not valid:return None
        scope = {**trusted.current_scope_probe(), 'generation_ledger': binding.generation_ledger,
                 'ledger_state': trusted.read_checkpoint(), 'read_question': task['question_ref']['text']}
        scope['check_receipt'] = lambda receipt: check_receipt(receipt, runtime=self.runtime,
            workspace_id=self.workspace_id, current_scope=scope,
            recipients=[row['expert_id'] for row in phase['assignments']])
        projected = shared_projection(record, [row['expert_id'] for row in phase['assignments']],
            runtime=self.runtime, workspace_id=self.workspace_id, current_scope=scope)
        if projected['status'] != 'AVAILABLE':
            state = trusted.read_checkpoint(); state['responses'][record['id']]['local_status'] = 'COMPLETED_LOCAL'
            trusted.checkpoint('role-private-' + record['id'], {'state': state})
            return None
        body = projected['projection']; event_id = 'E' + record['id']
        identifier = 'S' + record['id']
        body_ref = trusted.checkpoint('projection-body-' + identifier,
            {'asset': {'id': identifier, 'payload': body}})['asset_ref']
        projection = {'id': identifier, 'response_id': record['id'], 'event_id': event_id,
            'body_ref': body_ref, 'dependency_ids': deepcopy(record['dependency_ids']),
            'recipient_set': [row['expert_id'] for row in phase['assignments']],
            'validation_record': deepcopy(record['validation']), 'current_access_status': 'AVAILABLE'}
        state = trusted.read_checkpoint(); state['projections'][identifier] = projection
        state['responses'][record['id']]['shared_projection_id'] = identifier
        trusted.checkpoint('projection-' + identifier, {'state': state})
        information = cited_information(body, record, state, scope)
        turn = ConversationTurn(role=task['actor_id'], raw_utterance=body.get('answer', ''),
            utterance_type='Information Request' if task['kind'] == 'QUESTION' else 'Potential Answer',
            cited_info=information)
        turn._team_event = projection
        return turn


class BoundDiscourseManager:
    def __init__(self, agent):
        self.agent = agent; self.next_turn_moderator_override = False

    def get_next_turn_policy(self, conversation_history, dry_run=False, simulate_user=False, simulate_user_intent=None):
        from ._vendor.costorm.collaborative_storm.engine import TurnPolicySpec
        if simulate_user:raise PermissionError('등록되지 않은 자동 사용자 역할은 실행하지 않습니다.')
        return TurnPolicySpec(agent=self.agent, should_update_experts_list=False,
            should_polish_utterance=False, should_reorganize_knowledge_base=False)


def _generate_report(runner, binding, root_budget, plan, actor):
    """Actual vendor report on a copied approved KB, explicit action only."""
    from .costorm import report_record
    state = binding.read_checkpoint(); action = state['actions'][binding.action_id]
    phase = state['phases'][binding.phase_id]; base = phase['current_map_revision']
    prior = action.get('report') or {}
    if prior.get('status') == 'APPLIED' and prior.get('base_map_revision') == base:
        return binding.resolve_payload(prior['body_ref'])
    record = {'status': 'PENDING', 'base_map_revision': base,
        'dependency_ids': binding.base_dependencies(), 'body_ref': None,
        'journal_ref': prior.get('journal_ref'), 'error': None}
    action['report'] = record
    binding.checkpoint('report-start-' + binding.attempt_id, {'state': state})
    try:
        snapshot = binding.approved_snapshot()
        if snapshot is None:raise RuntimeError('승인한 근거 지도가 아직 없습니다. 지도 반영을 먼저 확인하세요.')
        dependencies = binding.base_dependencies(); binding.verify_dependencies(dependencies)
        budget = service_slice(root_budget, plan, 'REPORT_SERVICE', actor)
        if budget is None:raise TeamWaiting('WAITING_BUDGET', '보고서 처리 몫이 없습니다.')
        journal = binding.resolve_payload(record['journal_ref']) if record['journal_ref'] else []
        def save_journal():
            identifier = 'J' + canonical_hash({'report': binding.action_id, 'base': base, 'journal': journal})[:32]
            ref = binding.checkpoint('asset-' + identifier, {'asset': {'id': identifier, 'payload': journal}})['asset_ref']
            current = binding.read_checkpoint(); current['actions'][binding.action_id]['report']['journal_ref'] = ref
            binding.checkpoint('report-journal-' + identifier + '-' + canonical_hash(current)[:20], {'state': current})
        binding.report_completion = binding.make_completion(budget, journal, 'report-' + binding.action_id,
            base, dependencies, save_journal)
        binding.report_service = True
        try:
            text = runner.generate_report()
        finally:binding.report_service = False
        binding.verify_dependencies(dependencies)
        value = report_record(text, {'knowledge_base': snapshot})
        value['unapplied_map_ids'] = [row['id'] for row in binding.read_checkpoint()['map_pending'].values()
                                    if row['phase_id'] == binding.phase_id and row['status'] != 'APPLIED']
        identifier = 'F' + canonical_hash({'action': binding.action_id, 'base': base, 'report': value})[:32]
        ref = binding.checkpoint('asset-' + identifier, {'asset': {'id': identifier, 'payload': value}})['asset_ref']
        current = binding.read_checkpoint()
        if current['phases'][binding.phase_id]['current_map_revision'] != base:raise ValueError('보고서의 원 지도가 바뀌었습니다.')
        manifest_ids = [key for key, value in current['manifests'].items()
                        if value['task_id'] == 'service-report-' + binding.action_id]
        current['actions'][binding.action_id]['report'].update(status='APPLIED', body_ref=ref,
                                                              input_manifest_ids=manifest_ids)
        current['phases'][binding.phase_id]['current_report_action'] = binding.action_id
        binding.checkpoint('report-commit-' + binding.action_id, {'state': current})
        return value
    except Exception as error:
        current = binding.read_checkpoint()
        current['actions'][binding.action_id]['report'].update(status=getattr(error, 'status', 'FAILED'),
            error={'type': type(error).__name__, 'message': str(error)})
        binding.checkpoint('report-wait-' + binding.attempt_id, {'state': current})
        if isinstance(error, (ExecutionCancelled, ExecutionCleanupFailed)):raise
        previous = current['phases'][binding.phase_id].get('current_report_action')
        return binding.resolve_payload(current['actions'][previous]['report']['body_ref']) if previous else None


def _resolve_target(trusted, task):
    from .research_evidence import shared_projection
    state = trusted.read_checkpoint(); phase = state['phases'][trusted.phase_id]
    if task['kind'] not in {'QUESTION', 'ANSWER'}:return task
    if task.get('target_resolved'):return task
    if phase['initial_barrier'] != 'OPEN':raise PermissionError('초기 조사 이후에 질문할 수 있습니다.')
    if task['kind'] == 'QUESTION' or task.get('user_question'):
        candidates = [row for row in state['responses'].values() if row['phase_id'] == phase['id']
            and row.get('shared_projection_id') and row.get('claim_refs')]
        other = [row for row in candidates if row['actor_id'] != task['actor_id']]
        if other and not task.get('explicit_target') and not task.get('user_question'):candidates = other
        candidates.sort(key=lambda row: phase['task_ids'].index(row['task_id']))
        if not candidates:raise PermissionError('공유 가능한 실제 주장이나 근거가 필요합니다.')
        if task.get('explicit_target'):
            candidates = [row for row in candidates if 'A' + row['id'] == task['target_turn_id']]
            if not candidates:raise PermissionError('명시 선택한 원 주장이 현재 공유 범위에 없습니다.')
        target = candidates[0]
        claim = next((row for row in target['claim_refs'] if row['id'] == task.get('target_claim_id')),
                     target['claim_refs'][0])
        scope = trusted.current_scope_probe()
        checked = shared_projection(target, [task['actor_id']], runtime=trusted.runtime,
            workspace_id=trusted.workspace_id, current_scope=scope)
        if checked['status'] != 'AVAILABLE':raise PermissionError('현재 공유 가능한 실제 주장이 필요합니다.')
        task.update(target_turn_id='A' + target['id'], target_claim_id=claim['id'])
        authored = task['question_ref']['text'] if task.get('explicit_target') else ''
        instruction = ('사용자의 질문에 실제 근거로 답하세요. 대상 주장: ' if task.get('user_question')
                       else '다음 실제 주장에 판별 가능한 질문을 하세요. ')
        task['question_ref'] = {'text': (authored + '\n' if authored else '') + instruction +
            checked['projection']['research_reply']['claims'][claim['index']]['text'],
            'response_id': target['id'], 'dependency_ids': checked['dependency_ids']}
    else:
        question = state['tasks'][task['depends_on'][0]]
        if not question.get('completed_response_id'):
            raise TeamWaiting('WAITING_USER', '미해결로 남긴 질문에는 보존한 질문 응답이 없습니다. 새 질문과 답할 담당자를 명시하세요.')
        response = state['responses'][question['completed_response_id']]
        # Resolve a generated question's actual registered recipient before a
        # ticket/role session is created. Its metadata is not source permission.
        raw = trusted.resolve_payload(response['raw_response_ref'])
        questions = raw.get('research_reply', {}).get('questions', [])
        addressed = next((row for row in questions if row.get('target_turn_id') == question['target_turn_id']
                          and row.get('target_claim_id') == question['target_claim_id']), None)
        if addressed is None or addressed.get('expert_id') not in {row['expert_id'] for row in phase['assignments']}:
            raise PermissionError('질문의 실제 수신 담당자와 원 주장을 확인하세요.')
        task['actor_id'] = addressed['expert_id']
        checked = shared_projection(response, [task['actor_id']], runtime=trusted.runtime,
            workspace_id=trusted.workspace_id, current_scope=trusted.current_scope_probe())
        if checked['status'] != 'AVAILABLE':raise PermissionError('질문을 현재 담당자에게 전달할 수 없습니다.')
        task.update(target_turn_id='A' + response['id'], target_claim_id=question['target_claim_id'])
        task['question_ref'] = {'text': '다음 질문에 실제 근거로 답하고 판단을 유지 또는 수정하세요. ' +
            checked['projection']['answer'], 'response_id': response['id'], 'dependency_ids': checked['dependency_ids']}
    task['target_resolved'] = True
    state['tasks'][task['id']] = task
    trusted.checkpoint('target-' + task['id'], {'state': state})
    return task


def run_team_action(runtime, definition, question, context, session, path, workspace_id, budget, trusted):
    from .research_evidence import ActionLiteratureAccess
    from .costorm import _restore, _new_state
    from .research_team_map import DeferredKnowledgeBase, rebuild_shared_history, apply_pending_map
    from ._vendor.costorm.dataclass import ConversationTurn
    from ..research_team_contract import TrustedAction
    if not isinstance(trusted, TrustedAction):raise PermissionError('현재 문서가 발급한 연구 요청이 필요합니다.')
    trusted.runtime, trusted.workspace_id = runtime, workspace_id
    state = trusted.read_checkpoint(); phase = state['phases'][trusted.phase_id]
    action = state['actions'][trusted.action_id]
    if action['origin'] != 'local':raise PermissionError('원 사본의 연구를 자동 실행하지 않습니다.')
    if not callable(getattr(runtime, '_run_approved_role', None)):raise RuntimeError('연구팀 역할 연결이 아직 준비되지 않았습니다.')
    # C's callback factory is attached by root only. Missing exact readers never
    # silently fall back to the legacy job-ID callbacks.
    factory = getattr(trusted, 'configure_tools', None)
    if factory:
        accesses = factory(runtime, budget)
        trusted.result_access, trusted.analysis_access = accesses['result_access'], accesses['analysis_access']
    elif any(row['result_refs'] for row in phase['assignments']):
        raise PermissionError('정확 결과의 현재 reader 연결이 필요합니다. 원 결과를 넓게 읽지 않습니다.')
    trusted.public_access = ActionLiteratureAccess(runtime, action_id=trusted.action_id,
        workspace_id=workspace_id, context=context, budget=budget, checkpoint=trusted.checkpoint,
        state=state.get('public_search_ledgers', {}).get(trusted.action_id), current_scope_probe=trusted.current_scope_probe)
    tasks = [state['tasks'][i] for i in phase['task_ids']]
    for task in tasks:
        if (task['kind'] == 'ANSWER' and not task.get('user_question') and task['status'] not in FINISHED_TASKS
                and all(state['tasks'][i]['status'] in FINISHED_TASKS for i in task['depends_on'])):
            _resolve_target(trusted, deepcopy(task))
    state = trusted.read_checkpoint(); tasks = [state['tasks'][i] for i in phase['task_ids']]
    if budget.consultations > 0 and context.get('consult_experts'):
        # Positive consultations require two protected hosts, separate tasks and
        # sessions. No target ticket is ever executed by the ordinary step loop.
        caller = next((row for row in tasks if row['kind'] == 'ANSWER' and row['status'] not in FINISHED_TASKS), None)
        if caller and not caller.get('consult_target_task_id'):
            assignment = next(row for row in phase['assignments'] if row['expert_id'] == caller['actor_id'])
            targets = [row for row in phase['assignments'] if row['expert_id'] in context['consult_experts']
                       and row['expert_id'] != caller['actor_id']]
            if targets and 'experts.consult' in assignment['tools']:
                from ..discussion_research_team import _task
                target = _task(phase['id'], targets[0]['expert_id'], 'CONSULT', '', 200, caller['depends_on'])
                target['optional_consult'] = True; caller['consult_target_task_id'] = target['id']
                state['tasks'][target['id']] = target; state['tasks'][caller['id']] = caller
                state['phases'][phase['id']]['task_ids'].append(target['id'])
                trusted.checkpoint('consult-plan-' + caller['id'], {'state': state})
                tasks.append(target)
    if context['costorm']['action'] == 'report':tasks = []
    if context['costorm']['action'] == 'retry':
        tasks = [row for row in tasks if row['id'] in action['task_ids']]
    pending_ids = [row['id'] for row in state['map_pending'].values()
                   if row['phase_id'] == phase['id'] and row['status'] != 'APPLIED']
    plan = plan_action(phase, tasks, limits={'action_id': trusted.action_id,
        'model_calls': budget.model_calls, 'tool_calls': budget.tool_calls,
        'consultations': budget.consultations, 'deadline': budget.deadline,
        'kind': context['costorm']['action']}, pending=pending_ids)
    bind_allocation(budget, plan, checkpoint=trusted.checkpoint, control_status=trusted.control_status)
    trusted.checkpoint('allocation-' + trusted.attempt_id, {'allocation_plan': deepcopy(plan)})
    map_binding = _MapContext(runtime, context, workspace_id, trusted, budget, question)
    def no_unallocated_model(*args, **kwargs):raise PermissionError('모델 처리는 배정한 서비스에서만 가능합니다.')
    runner = _restore(_new_state(question), no_unallocated_model, lambda *a, **k: [])
    runner.knowledge_base = DeferredKnowledgeBase(map_binding.approved_snapshot(), binding=map_binding)
    runner.conversation_history = [ConversationTurn('Guest', phase['objective'], 'Original Question')]
    runner.conversation_history.extend(rebuild_shared_history(map_binding))
    stopped = None
    for ticket in plan['tickets'][:]:
        if ticket.get('consult_parent'):continue
        slice_budget = None
        try:
            task = _resolve_target(trusted, deepcopy(trusted.read_checkpoint()['tasks'][ticket['task_id']]))
            if task['status'] in FINISHED_TASKS:continue
            slice_budget = BudgetSlice(budget, ticket)
            slice_budget._check(starting=True)
            agent = ConfiguredExpertAgent(runtime, trusted, task, slice_budget,
                workspace_id=workspace_id, map_binding=map_binding)
            runner.discourse_manager = BoundDiscourseManager(agent)
            runner.step()  # Real pinned append + deferred insertion; never warm_start.
            ticket['status'] = 'FINISHED'; slice_budget.active = False
        except Exception as error:
            if isinstance(error, (ExecutionCancelled, ExecutionCleanupFailed)):raise
            stopped = {'status': getattr(error, 'status', 'BLOCKED_SCOPE' if isinstance(error, PermissionError) else 'FAILED'),
                       'reason': str(error)}
            if (ticket['task_id'] in phase['initial_task_ids'] and isinstance(error, (PermissionError, ValueError, OSError))):
                current = trusted.read_checkpoint()
                current['tasks'][ticket['task_id']].update(status='BLOCKED_SCOPE',
                    continuation={'error_type': type(error).__name__, 'message': str(error)})
                trusted.checkpoint('role-blocked-' + ticket['task_id'] + '-' + trusted.attempt_id, {'state': current})
                ticket['status'] = 'FINISHED'
                if slice_budget is not None:slice_budget.active = False
                continue
            break
    # Repair/map consume only the explicitly left service pool. Completed role
    # tasks above are never called while retrying these derived operations.
    is_report = context['costorm']['action'] == 'report' or (
        context['costorm']['action'] == 'retry' and action.get('report') is not None)
    service = None if is_report else service_slice(budget, plan, 'MAP_SERVICE', definition['id'])
    state = trusted.read_checkpoint()
    maps = []
    by_event = {row['event_id']: row for row in state['map_pending'].values() if row['phase_id'] == phase['id']}
    for event_id in state['phases'][phase['id']]['shared_turn_ids']:
        pending = by_event[event_id]
        if is_report:break
        if pending['phase_id'] != phase['id'] or pending['status'] == 'APPLIED':continue
        result = apply_pending_map(pending['id'], binding=map_binding, budget_slice=service)
        maps.append(result)
        if result['status'] != 'APPLIED':break
    report = _generate_report(runner, map_binding, budget, plan, definition['id']) if is_report else None
    state = trusted.read_checkpoint()
    incomplete = [state['tasks'][row['task_id']] for row in plan['tickets'] if row['task_id']
                  and not row.get('consult_parent') and state['tasks'][row['task_id']]['status'] not in FINISHED_TASKS]
    if incomplete and stopped is None:
        stopped = {'status': incomplete[0]['status'], 'reason': '완료하지 못한 과제를 보존했습니다. 연결·자료·응답 상태를 확인하고 다음 동작을 선택하세요.'}
    if is_report and state['actions'][trusted.action_id]['report']['status'] != 'APPLIED':
        failure = state['actions'][trusted.action_id]['report']
        stopped = {'status': failure['status'], 'reason': (failure.get('error') or {}).get('message', '보고서 반영을 마치지 못했습니다.')}
    tasks = [state['tasks'][i] for i in phase['task_ids']]
    result = {'status': 'ANSWERED' if not stopped else 'STOPPED',
        'answer': '현재 범위의 연구 응답을 보존했습니다.' if not stopped else stopped['reason'],
        'sources': [], 'proposed_actions': [], 'tool_events': [], 'assumptions': [],
        'costorm': {'team': {**deepcopy(state), 'version': 2}, 'report': report,
            'usage': {'model_calls': budget.used_models, 'tool_calls': budget.used_tools,
                'consultations': budget.used_consultations, 'model_host_invocations': budget.used_model_host_invocations,
                'observed_host_invocations': budget._team_observed_hosts, 'billed_model_calls': None},
            'remaining_task_ids': [task['id'] for task in tasks if task['status'] not in FINISHED_TASKS],
            'map_results': maps, 'view': {'turns': [], 'topics': []}},
        'inference_performed': bool(budget.used_models)}
    return result
