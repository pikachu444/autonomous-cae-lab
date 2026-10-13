"""Actual pinned Co-STORM runner on existing local source/model/job boundaries.

The caller supplies an owner-verified predecessor through a ContextVar, never a
runner state accepted from HTTP/model arguments. No package installation,
provider selection, public search or inference occurs on import/read/restore.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
from dataclasses import asdict
import hashlib
import json
import re
import threading
import time

from ..execution_control import check_cancelled, ExecutionCancelled, ExecutionCleanupFailed
from ..storage import canonical_hash
from .knowledge import selected_source_refs

VERSION = 'stanford-costorm-fb951af-local-1'
_TRUSTED = ContextVar('owner_costorm_step', default=None)


@contextmanager
def owner_step(request):
    binding = _TRUSTED.set(request)
    try:
        yield
    finally:
        _TRUSTED.reset(binding)


def _snapshot(runner):
    state = runner.to_dict()
    state.pop('lm_config', None)  # Configuration/credentials belong to the operator.
    state['moderator_override'] = runner.discourse_manager.next_turn_moderator_override
    return state


def _restore(state, lm, rm):
    from ._vendor.costorm.collaborative_storm.engine import CoStormRunner, CollaborativeStormLMConfigs, RunnerArgument
    from ._vendor.costorm.dataclass import ConversationTurn, KnowledgeBase
    from ._vendor.costorm.logging_wrapper import LoggingWrapper
    from ._vendor.costorm.vectors import LocalEncoder
    config = CollaborativeStormLMConfigs()
    for key in ('question_answering', 'discourse_manage', 'utterance_polishing',
                'warmstart_outline_gen', 'question_asking', 'knowledge_base'):
        getattr(config, 'set_' + key + '_lm')(lm)
    args = RunnerArgument.from_dict(state['runner_argument'])
    encoder = LocalEncoder()
    runner = CoStormRunner(config, args, LoggingWrapper(config), rm=rm, encoder=encoder)
    if 'knowledge_base' in state:
        runner.knowledge_base = KnowledgeBase.from_dict(state['knowledge_base'], lm,
            args.node_expansion_trigger_count, encoder)
        runner.conversation_history = [ConversationTurn.from_dict(turn) for turn in state['conversation_history']]
        runner.warmstart_conv_archive = [ConversationTurn.from_dict(turn) for turn in state.get('warmstart_conv_archive', [])]
        runner.discourse_manager.deserialize_experts(state['experts'])
        runner.discourse_manager.next_turn_moderator_override = bool(state['moderator_override'])
    return runner


def _new_state(question):
    from ._vendor.costorm.collaborative_storm.engine import RunnerArgument
    return {'runner_argument': asdict(RunnerArgument(topic=question, retrieve_top_k=4,
        max_search_queries=2, max_search_thread=1, warmstart_max_num_experts=2,
        warmstart_max_turn_per_experts=1, warmstart_max_thread=1, max_thread_num=1,
        max_num_round_table_experts=2, node_expansion_trigger_count=6))}


class Completion:
    """Raw single-completion host adapter; replay only this interrupted action."""
    def __init__(self, runtime, config, context, workspace_id, collections, budget, journal, instructions, verify):
        self.runtime, self.config, self.context = runtime, config, context
        self.workspace_id, self.collections, self.budget = workspace_id, collections, budget
        self.journal, self.instructions, self.verify = journal, instructions, verify
        self.kwargs = {'temperature': 0, 'n': 1, 'max_tokens': config.max_output_tokens}
        self.history = []
        self.lock = threading.RLock()
        self.cache_hits = 0

    def __call__(self, prompt, **kwargs):
        with self.lock:
            check_cancelled()
            self.verify()  # Recheck revocation/access, including replayed work.
            full = ('Answer in the language of the research question. Preserve every required output label. '
                    'You are discussing evidence, not granting engineering approval.\n'
                    + self.instructions + '\n\n' + prompt)
            self.runtime._transmission_check({'prompt': full, 'sources': self.context['_source_grants']}, self.context)
            key = canonical_hash({'prompt': full, 'model': self.config.model, 'format': VERSION})
            prior = next((row for row in self.journal if row['key'] == key), None)
            if prior is not None:
                from ._vendor.costorm.prompting import last_completion_key
                last_completion_key.set(key)
                self.cache_hits += 1
                return [prior['text']]
            if len(self.journal) >= 256:
                raise RuntimeError('This discussion action exceeds the retained completion limit')
            from .openscience_host import run_openscience
            steps = self.budget.reserve_provider_steps(correction=True)
            text = run_openscience(full, {}, self.budget, self.config.model,
                max_steps=steps, profile_path=self.config.openscience_profile,
                runtime_prefix=self.config.openscience_runtime_prefix)
            if not isinstance(text, str) or not text.strip():
                raise ValueError('The selected model returned no usable text')
            # Actual raw replies remain in the existing job result on partial failure.
            self.journal.append({'key': key, 'text': text, 'prompt': full})
            self.history.append({'prompt': full, 'response': text})
            from ._vendor.costorm.prompting import last_completion_key
            last_completion_key.set(key)
            check_cancelled()
            return [text]

    def get_usage_and_reset(self):
        return {}  # The host does not supply trustworthy token counts.


class SelectedRetriever:
    """Existing revision-scoped BM25, projected into upstream Information rows."""
    def __init__(self, runtime, context, workspace_id, collections, budget, verify, result_sources=()):
        self.runtime, self.context = runtime, context
        self.workspace_id, self.collections, self.budget, self.verify = workspace_id, collections, budget, verify
        self.result_sources = result_sources

    def __call__(self, query_or_queries, exclude_urls=()):
        self.verify()
        rows, seen = [], set()
        for query in query_or_queries:
            check_cancelled()
            self.budget.consume('tool')
            result = self.runtime.knowledge.search(str(query), self.collections, top_k=4,
                workspace_id=self.workspace_id, source_refs=selected_source_refs(self.context))
            self.runtime._transmission_check(result, self.context)
            for hit in result['hits']:
                reference = {key: deepcopy(hit[key]) for key in ('document_id', 'revision', 'locator')}
                url = 'caelab-source:' + canonical_hash(reference)
                if url in seen or url in exclude_urls:
                    continue
                seen.add(url)
                rows.append({'url': url, 'title': hit['title'], 'description': hit['title'],
                    'snippets': [hit['text']], 'meta': {'source': deepcopy(hit)}})
        for source in self.result_sources:
            url = 'caelab-result:' + canonical_hash(source['reference'])
            if url not in seen and url not in exclude_urls:
                rows.append({'url': url, 'title': '선택한 계산 결과', 'description': 'Retained selected response',
                    'snippets': [json.dumps(source['payload'], ensure_ascii=False)],
                    'meta': {'source': {**deepcopy(source['reference']), 'title': '선택한 계산 결과'}}})
        return rows


def presentation(state):
    """Exact source-backed map/turns; unresolved citation numbers stay explicit."""
    kb = state.get('knowledge_base', {})
    infos = kb.get('info_uuid_to_info_dict', {})
    sources = {}
    for key, info in infos.items():
        source = info.get('meta', {}).get('source')
        if source:
            sources[str(key)] = deepcopy(source)
    nodes = []
    def visit(node, parent=None, path=()):
        path = (*path, node['name'])
        identifier = 'Q' + canonical_hash(path)[:24]
        citations = [str(value) for value in node.get('content', [])]
        title = state.get('runner_argument', {}).get('topic', node['name']) if parent is None else node['name']
        nodes.append({'id': identifier, 'title': title, 'parent_id': parent,
                      'citations': citations})
        for child in node.get('children', []):
            visit(child, identifier, path)
    if kb.get('tree'):
        visit(kb['tree'])
    turns = []
    # With no revised catch-up transcript upstream reuses the archive verbatim.
    # Keep those turns once; separate genuinely revised catch-up turns stay visible.
    available = {}
    for turn in state.get('conversation_history', []):
        key = canonical_hash(turn)
        available[key] = available.get(key, 0) + 1
    history = []
    for index, turn in enumerate(state.get('warmstart_conv_archive', [])):
        key = canonical_hash(turn)
        if available.get(key, 0):
            available[key] -= 1
        else:
            history.append(('warm:' + str(index), turn))
    history += [(i, turn) for i, turn in enumerate(state.get('conversation_history', []))]
    for index, turn in history:
        if turn.get('role') == 'Guest':
            continue  # The owner already retains the exact authored intervention.
        text = turn.get('utterance', '')
        citations = list(dict.fromkeys(re.findall(r'\[(\d+)\]', text)))
        related = [node['id'] for node in nodes if set(node['citations']) & set(citations)]
        turns.append({'index': index, 'author': turn['role'], 'text': text,
            'role_description': turn.get('role_description', ''),
            'topic_ids': related, 'citations': [{'number': key, 'source': sources.get(key),
                'status': 'AVAILABLE' if key in sources else 'MISSING_SOURCE'} for key in citations]})
    return {'topics': nodes, 'turns': turns, 'sources': sources}


def report_record(text, state):
    view = presentation(state)
    numbers = list(dict.fromkeys(re.findall(r'\[(\d+)\]', text)))
    references = [{'number': key, 'source': view['sources'].get(key),
                   'status': 'AVAILABLE' if key in view['sources'] else 'MISSING_SOURCE'} for key in numbers]
    return {'text': text, 'references': references,
            'status': 'DRAFT' if numbers and all(row['source'] for row in references) else 'INCOMPLETE_CITATIONS'}


def _retry_journal(retry):
    rejected = retry.get('invalid_completion_key')
    return [deepcopy(row) for row in retry['journal'] if not rejected or row['key'] != rejected]


def run(runtime, definition, question, context, session, path, workspace_id, budget):
    trusted = _TRUSTED.get()
    if not isinstance(trusted, dict):
        raise PermissionError('Co-STORM steps must be submitted by the existing discussion owner')
    spec = deepcopy(trusted['request'])
    if canonical_hash(context.get('costorm')) != canonical_hash(spec):
        raise PermissionError('Protocol request differs from the owner prepared step')
    config = runtime.runtime.for_expert(definition['id'])
    if config.provider != 'openscience' or not (config.model or '').startswith('openai-codex/'):
        return {'status': 'NOT_CONFIGURED', 'execution_status': 'FAILED', 'answer': None,
                'reason': '연결에서 기존 OpenScience 설정과 사용 가능한 ChatGPT 모델을 선택하세요.',
                'sources': [], 'proposed_actions': [], 'inference_performed': False}
    roles = [runtime.describe(role) for role in spec['roles']]
    required = {'knowledge.search', 'knowledge.source'}
    if any(not required.issubset(set(role.get('tools', []))) for role in roles):
        raise PermissionError('참여 역할 모두에 선택 자료 검색·원문 읽기 권한이 필요합니다.')
    collections = sorted(set.intersection(*(set(role.get('collections', [])) for role in roles)))
    pins = selected_source_refs(context)
    if not pins:
        raise ValueError('Co-STORM 토론에 사용할 자료를 선택하세요.')
    grants = []
    if spec.get('evidence') and any('results.read' not in role.get('tools', []) for role in roles):
        raise PermissionError('선택한 계산 결과를 읽을 참여 역할 권한이 필요합니다.')
    result_sources = trusted.get('read_results', lambda: [])()
    for result in result_sources:
        runtime._transmission_check({**result['reference'], 'data': result['payload']}, context)
    for ref in pins:
        source = runtime.knowledge.source(**ref, workspace_id=workspace_id, collections=collections)
        grants.append({key: source[key] for key in ('document_id', 'revision', 'collection')})
    # Role-generated names never grant collections, tools, models or permissions.
    context = deepcopy(context)
    context['_source_grants'] = grants
    instructions = '\n'.join(str(role.get('system_prompt', role.get('instructions', role.get('description', ''))))
                             for role in roles)
    runtime_identity = canonical_hash({
        key: getattr(config, key) for key in ('provider', 'model', 'external_model', 'transmission',
            'openscience_profile', 'openscience_runtime_prefix', 'max_output_tokens', 'max_payload_bytes')})
    scope = canonical_hash({'pins': pins, 'roles': roles, 'model': runtime_identity,
                            'topic': question, 'version': VERSION})
    prior = deepcopy(trusted.get('previous') or {})
    if prior and prior.get('scope') != scope:
        raise ValueError('자료·역할·연결이 이전 토론과 달라졌습니다. 기존 토론을 보관하고 새 토론을 시작하세요.')
    action = spec['action']
    if action == 'retry':
        if not prior.get('retry'):
            raise ValueError('이어갈 중단 작업이 없습니다.')
        action = prior['retry']['action']
        inputs = prior['retry']['interventions']
        base = prior['retry']['base']
        # Only the exact rejected reply is requested again; valid later queued
        # completions remain reusable too.
        journal = _retry_journal(prior['retry'])
    else:
        base = deepcopy(prior.get('state')) or _new_state(question)
        inputs = deepcopy(spec.get('interventions', []))
        journal = []
    def verify():
        check_cancelled()
        for ref in pins:
            source = runtime.knowledge.source(**ref, workspace_id=workspace_id, collections=collections)
            if not source.get('segments'):
                raise PermissionError('선택한 원문을 읽을 수 없습니다.')
        current_results = trusted.get('read_results', lambda: [])()
        if canonical_hash(current_results) != canonical_hash(result_sources):
            raise ValueError('Selected retained result changed during this action')
        runtime._transmission_check({'question': question, 'sources': grants, 'results': current_results}, context)
    for information in (prior.get('state') or {}).get('knowledge_base', {}).get('info_uuid_to_info_dict', {}).values():
        source = information.get('meta', {}).get('source', {})
        if 'job_id' in source:
            keys = ('document_id', 'job_id', 'input_revision', 'input_sha256', 'selection')
            if not any(all(source.get(key) == item['reference'].get(key) for key in keys) for item in result_sources):
                raise PermissionError('이 토론의 이전 계산 근거가 첨부 목록에서 빠졌습니다. 다시 첨부하거나 새 대화를 시작하세요.')
        runtime._transmission_check(source, context)
    verify()
    lm = Completion(runtime, config, context, workspace_id, collections, budget, journal, instructions, verify)
    rm = SelectedRetriever(runtime, context, workspace_id, collections, budget, verify, result_sources)
    runner = _restore(base, lm, rm)
    before = len(base.get('conversation_history', []))
    started = time.monotonic()
    outcome, reason, report = 'ANSWERED', None, deepcopy(prior.get('report'))
    retry = None
    from ._vendor.costorm.prompting import last_completion_key
    last_completion_key.set(None)
    try:
        if action == 'start':
            runner.warm_start()
        else:
            if not runner.conversation_history:
                raise ValueError('먼저 자료 토론을 시작하세요.')
            for item in inputs:
                context_text = ''
                if item.get('topic_title'):
                    context_text += '\nSelected discussion topic: ' + item['topic_title']
                if item.get('reply_text'):
                    context_text += '\nReplying to this earlier utterance:\n' + item['reply_text']
                runner.step(user_utterance=item['text'] + context_text)
            if action == 'step':
                runner.step()
            elif action == 'report':
                runner.knowledge_base.reorganize()
                report = report_record(runner.generate_report(), _snapshot(runner))
            else:
                raise ValueError('Unknown Co-STORM action')
        verify()
        committed = _snapshot(runner)
        if action == 'start' and not committed['conversation_history']:
            raise ValueError('No completed background discussion was returned')
    except ExecutionCleanupFailed:
        raise  # No reusable output while an owned model process remains unconfirmed.
    except Exception as error:
        outcome = 'STOPPED'
        reason = str(error)
        committed = deepcopy(base)
        retry = {'action': action, 'base': deepcopy(base), 'interventions': deepcopy(inputs),
                 'journal': deepcopy(journal),
                 'invalid_completion_key': (getattr(error, 'completion_key', last_completion_key.get())
                    if isinstance(error, ValueError) else None)}
        cancelled = isinstance(error, ExecutionCancelled)
    else:
        cancelled = False
    consumed = list(prior.get('consumed_user_ids', []))
    if outcome == 'ANSWERED':
        consumed = list(dict.fromkeys(consumed + [item['id'] for item in inputs]))
    usage = {'model_calls': budget.used_models, 'source_queries': budget.used_tools,
             'host_invocations': budget.used_model_host_invocations,
             'replayed_completions': lm.cache_hits, 'seconds': time.monotonic() - started,
             'token_count': None}
    total = deepcopy(prior.get('total_usage', {'model_calls': 0, 'source_queries': 0, 'host_invocations': 0}))
    for key in total:
        total[key] += usage.get(key, 0)
    protocol = {'version': VERSION, 'scope': scope, 'state': committed, 'report': report, 'retry': retry,
        'consumed_user_ids': consumed, 'view': presentation(committed), 'usage': usage, 'total_usage': total}
    new_turns = [turn for turn in protocol['view']['turns'] if isinstance(turn['index'], int) and turn['index'] >= before]
    result = {'status': outcome, 'execution_status': 'CANCELLED' if cancelled else
              'SUCCEEDED' if outcome == 'ANSWERED' else 'PARTIAL_FAILURE',
        'answer': new_turns[-1]['text'] if new_turns and outcome == 'ANSWERED' else None,
        'reason': reason, 'sources': list(protocol['view']['sources'].values()),
        'proposed_actions': [], 'assumptions': [], 'tool_events': [],
        'expert_id': definition['id'], 'session_id': session['session_id'],
        'inference_performed': bool(budget.used_models), 'costorm': protocol}
    session['turns'].append({'question': question, 'context': deepcopy(context), 'response': deepcopy(result),
                             'read_sources': deepcopy(result['sources'])})
    from ..storage import save_json
    save_json(path, session)
    return result
