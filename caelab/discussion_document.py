"""Editable Expert discussions with append-only actual runtime turns.

The existing JobManager executes experts.ask.  A bounded round advances only
through explicit owner commands; opening, saving and Undo never invoke a model.
"""
from copy import deepcopy
import uuid

from .material_document import MaterialDocuments
from .jobs import TERMINAL
from .assist.knowledge import selected_source_refs
from .evaluation import read_result
from .storage import canonical_hash, check_id, load_json, save_json, utc_now


SPECIAL_OPERATIONS = {'expert.ask', 'expert.intervene', 'expert.pause', 'expert.resume', 'expert.advance'}


def default_draft():
    return {'topics': [{'id': 'Qmain', 'title': 'Research question', 'parent_id': None}],
            'participants': [],
            'composer': {'text': '', 'topic_id': 'Qmain', 'reply_to': None,
                         'classification': 'question', 'evidence': []},
            'context': {}, 'budget': {'model_calls': 4, 'tool_calls': 8, 'consultations': 0, 'seconds': 120}}


def diagnostics(draft):
    try:
        if not isinstance(draft, dict) or set(draft) != set(default_draft()):
            raise ValueError('Discussion requires topics, participants, composer, context and budget')
        if not isinstance(draft['topics'], list) or not draft['topics']:
            raise ValueError('Add at least one discussion topic')
        topics = {}
        for item in draft['topics']:
            if not isinstance(item, dict) or set(item) != {'id', 'title', 'parent_id'}:
                raise ValueError('Topics require id, title and parent_id')
            identifier = check_id(item['id'])
            if identifier in topics or not isinstance(item['title'], str) or not item['title'].strip():
                raise ValueError('Topic identities must be unique and titles nonempty')
            topics[identifier] = item
        for identifier, item in topics.items():
            seen = {identifier}
            parent = item['parent_id']
            while parent is not None:
                if parent not in topics or parent in seen:
                    raise ValueError('Topic parent is missing or creates a cycle')
                seen.add(parent)
                parent = topics[parent]['parent_id']
        roles = draft['participants']
        if not isinstance(roles, list) or any(not isinstance(role, str) or not role for role in roles) or len(set(roles)) != len(roles) or len(roles) > 8:
            raise ValueError('Select up to eight distinct registered roles')
        composer = draft['composer']
        if not isinstance(composer, dict) or set(composer) != {'text', 'topic_id', 'reply_to', 'classification', 'evidence'}:
            raise ValueError('Question requires text, topic, explicit reply target, classification and evidence')
        if not isinstance(composer['text'], str) or composer['topic_id'] not in topics:
            raise ValueError('Enter question text and select an existing topic')
        if composer['reply_to'] is not None:
            check_id(composer['reply_to'])
        if composer['classification'] not in {'question', 'observation', 'assumption', 'challenge', 'unknown'}:
            raise ValueError('Select the authored statement classification')
        if not isinstance(composer['evidence'], list) or any(not isinstance(item, dict) for item in composer['evidence']):
            raise ValueError('Evidence must contain explicit reference objects')
        if not isinstance(draft['context'], dict) or not isinstance(draft['budget'], dict):
            raise ValueError('Context and budget must be objects')
        if set(draft['budget']) - {'model_calls', 'tool_calls', 'consultations', 'seconds'}:
            raise ValueError('Unknown expert budget field')
        for key, value in draft['budget'].items():
            if type(value) not in (int, float) or value < (1 if key in {'model_calls', 'seconds'} else 0):
                raise ValueError('Expert budget values must be nonnegative; model_calls and seconds must be positive')
            if key != 'seconds' and type(value) is not int:
                raise ValueError('Expert call budgets must be integers')
    except (ValueError, TypeError, KeyError) as error:
        return [{'severity': 'error', 'path': 'discussion', 'message': str(error), 'blocks_evaluation': True}]
    return []


class DiscussionDocuments(MaterialDocuments):
    kind, prefix = 'expert', 'X'
    update_operation = 'expert.update'
    # No inherited evaluation command; dispatch needs the discussion round contract.
    evaluate_operation = 'expert.ask'
    default_draft, diagnostics = staticmethod(default_draft), staticmethod(diagnostics)

    @property
    def operations(self):
        return {self.update_operation, 'document.undo', 'document.redo', 'document.save'} | SPECIAL_OPERATIONS

    def __init__(self, root, session_id, submit, manager, *, list_experts,
                 resolve_document=None, resolve_result=None, resolve_knowledge=None):
        super().__init__(root, session_id, submit, manager)
        self.list_experts = list_experts
        self.resolve_document, self.resolve_result = resolve_document, resolve_result
        self.resolve_knowledge = resolve_knowledge

    @staticmethod
    def _state(document):
        return document.setdefault('discussion', {'paused': False, 'turns': [], 'rounds': []})

    @staticmethod
    def _fingerprint(document):
        return canonical_hash({key: document.get(key) for key in ('title', 'draft', 'runs', 'discussion')})

    def _recover_evaluations(self, document):
        """Harvest actual finished jobs, never request inference from a read."""
        changed = False
        for record in self._state(document)['rounds']:
            if record['status'] not in {'READY', 'RUNNING'}:
                continue
            if record.get('dispatch_pending') and not record.get('active_job_id'):
                request_id = self._request_id(document, record)
                job = next((item for item in self.manager.list() if item.get('request_id') == request_id), None)
                if job is not None:
                    self._attach_job(document, record, job, record['prepared_arguments'])
                    changed = True
            changed = self._collect(document, record) or changed
        if changed:
            self._changed(document)
            self._persist_draft(document)

    def _public(self, document):
        self._state(document)
        result = super()._public(document)
        result['turns'] = deepcopy(document['discussion']['turns'])
        return result

    def _validate_sources(self, context):
        references = selected_source_refs(context)
        for reference in references:
            if self.resolve_knowledge is None:
                raise ValueError('Source reader unavailable; preserve the draft and reconnect the existing service')
            payload = self.resolve_knowledge(reference)
            if payload.get('revision') != reference['revision'] or not payload.get('segments'):
                raise ValueError('Selected source revision has no readable content; inspect it in Sources')
        return references

    def _validate_question(self, document, *, needs_roles):
        draft = document['draft']
        errors = self.diagnostics(draft)
        if errors:
            raise ValueError('Invalid discussion draft: ' + errors[0]['message'])
        if not draft['composer']['text'].strip():
            raise ValueError('Enter a nonempty question or intervention')
        turns = self._state(document)['turns']
        target = draft['composer']['reply_to']
        if target and not any(turn['id'] == target for turn in turns):
            raise ValueError('Reply target does not belong to this discussion')
        if needs_roles:
            self._validate_sources(draft['context'])
            registry = self.list_experts()
            registered = {item['id'] for item in (registry['experts'] if isinstance(registry, dict) else registry)}
            if not draft['participants'] or not set(draft['participants']).issubset(registered):
                raise ValueError('Choose actual registered expert roles before requesting a round')
        for key in ('selected_result_ids', 'selected_document_ids', 'consult_experts'):
            value = draft['context'].get(key, [])
            if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
                raise ValueError(key + ' must contain explicit selected identities')
        for evidence in draft['composer']['evidence']:
            if 'job_id' not in evidence:
                # Knowledge/literature references are validated by their existing runtime readers.
                if not any(key in evidence for key in ('document_id', 'paper_id')):
                    raise ValueError('Evidence requires an explicit document, paper or result identity')
                continue
            check_id(evidence['job_id'])
            if not evidence.get('document_id') or self.resolve_document is None or self.resolve_result is None:
                raise ValueError('A result reference requires its owning document and configured result resolver')
            source = self.resolve_document(evidence['document_id'])
            run = next((row for row in source.get('runs', []) if row['job_id'] == evidence['job_id']), None)
            if run is None:
                raise ValueError('Evidence job does not belong to the selected document')
            for key in ('input_revision', 'input_sha256'):
                if evidence.get(key) != run.get(key) or not evidence.get(key):
                    raise ValueError('Evidence requires the exact retained job input revision and hash')
            selection = evidence.get('selection', [])
            if not isinstance(selection, list) or any(not isinstance(item, str) for item in selection):
                raise ValueError('Evidence requires an explicit response selection')
            self.resolve_result(evidence['document_id'], evidence['job_id'], selection=selection)

    def _user_turn(self, document, command_id):
        composer = deepcopy(document['draft']['composer'])
        topic = next(row for row in document['draft']['topics'] if row['id'] == composer['topic_id'])
        turn = {'id': 'U' + uuid.uuid4().hex, 'author': 'user', 'status': 'AUTHORED',
                'command_id': command_id, 'created_utc': utc_now(),
                'input_generation': document['generation'], 'input_revision': document['input_revision'],
                'input_sha256': canonical_hash(document['draft']), 'topic': deepcopy(topic), **composer}
        try:
            turn['knowledge_sources'] = selected_source_refs(document['draft']['context'])
        except ValueError:
            turn['knowledge_sources'] = None  # Legacy/unresolved source work remains an authored local turn.
        self._state(document)['turns'].append(turn)
        return turn

    def _arguments(self, document, round_record, role):
        snapshot = round_record['draft']
        composer = snapshot['composer']
        context = deepcopy(snapshot['context'])
        if 'knowledge_sources' in round_record:
            context['selected_sources'] = deepcopy(round_record['knowledge_sources'])
        result_ids = [item['job_id'] for item in composer['evidence'] if 'job_id' in item]
        context['selected_result_ids'] = list(dict.fromkeys(context.get('selected_result_ids', []) + result_ids))
        context['discussion'] = {'document_id': document['id'], 'round_id': round_record['id'],
            'topic_id': composer['topic_id'], 'reply_to': composer['reply_to'],
            'evidence': deepcopy(composer['evidence']), 'turns': []}
        # New replies in this bounded round are actual returned records. Pending
        # user edits/interventions do not silently widen the frozen context.
        history = round_record['history'] + [turn for turn in self._state(document)['turns']
            if turn.get('round_id') == round_record['id'] and turn.get('author') != 'user']
        context['discussion']['turns'] = [{key: deepcopy(turn.get(key)) for key in
            ('id', 'author', 'text', 'status', 'topic_id', 'reply_to', 'classification', 'knowledge_sources')} for turn in history]
        return {'expert_id': role, 'question': composer['text'], 'context': context,
                'session_id': round_record['sessions'][role], 'budget': deepcopy(snapshot['budget'])}

    def _request_id(self, document, record):
        return 'expert:' + document['id'] + ':' + record['id'] + ':' + str(record['next_index'])

    def _attach_job(self, document, round_record, job, arguments):
        if job['operation'] != 'experts.ask' or canonical_hash(job['arguments']) != canonical_hash(arguments):
            raise ValueError('Recovered discussion request differs from its frozen runtime input')
        role = round_record['roles'][round_record['next_index']]
        if not any(run['job_id'] == job['id'] for run in document['runs']):
            run = self._run_record(job, round_record['draft'], round_record['input_generation'],
                                   round_record['input_revision'], self.session_id)
            run.update(round_id=round_record['id'], role=role, user_turn_id=round_record['user_turn_id'])
            document['runs'].append(run)
        round_record.update(active_job_id=job['id'], status='RUNNING', dispatch_pending=False)
        round_record.pop('prepared_arguments', None)

    def _submit_next(self, document, round_record):
        index = round_record['next_index']
        if index >= len(round_record['roles']):
            round_record['status'] = 'COMPLETED'
            return None
        role = round_record['roles'][index]
        request_id = self._request_id(document, round_record)
        job = next((item for item in self.manager.list() if item.get('request_id') == request_id), None)
        arguments = round_record.get('prepared_arguments')
        if job is None:
            try:
                if ('knowledge_sources' not in round_record
                        and 'selected_sources' not in round_record['draft']['context']):
                    raise ValueError('Legacy round source scope is unresolved; start a new round after reviewing Sources')
                self._validate_sources(round_record['draft']['context'])
            except (ValueError, PermissionError, OSError) as error:
                # Preserve frozen legacy/revoked rounds and already completed roles.
                # A later explicit Ask may use the user's repaired current draft.
                round_record.update(status='BLOCKED_SOURCES', source_error=str(error), dispatch_pending=False)
                self._persist_draft(document)
                return None
        if arguments is None:
            arguments = self._arguments(document, round_record, role)
            round_record['prepared_arguments'] = arguments
            round_record['dispatch_pending'] = True
            self._persist_draft(document)
        if job is None:
            job = self.submit('experts.ask', arguments, request_id=request_id)
        self._attach_job(document, round_record, job, arguments)
        self._persist_draft(document)
        return job

    def _read_response(self, document, run):
        if run.get('retained_result'):
            revision = run['retained_result']['revision']
            self._verify_revision(document['id'], revision)
            return read_result(self._folder(document['id']) / 'revisions' / revision / 'results' / check_id(run['job_id']),
                               verify='all')
        return self.manager.result(run['job_id'])

    def _collect(self, document, round_record):
        job_id = round_record.get('active_job_id')
        if not job_id:
            return False
        run = next(row for row in document['runs'] if row['job_id'] == job_id)
        if run.get('retention_complete'):
            state, error = run['retained_state'], run.get('retained_error')
        else:
            status = self.manager.status(job_id)
            state, error = status['state'], status.get('error')
        if state not in TERMINAL:
            return False
        try:
            response = self._read_response(document, run)
        except (ValueError, FileNotFoundError) as failure:
            response = {'status': state, 'answer': None, 'reason': (error or {}).get('message', str(failure)),
                        'error': deepcopy(error), 'sources': [], 'proposed_actions': []}
        # One immutable event per actual job; repeat advance never duplicates it.
        if not any(turn.get('job_id') == job_id for turn in self._state(document)['turns']):
            composer = round_record['draft']['composer']
            self._state(document)['turns'].append({'id': 'A' + job_id, 'author': run['role'],
                'status': response.get('status', state), 'job_state': state, 'job_id': job_id,
                'round_id': round_record['id'], 'topic_id': composer['topic_id'],
                'topic': deepcopy(next(row for row in round_record['draft']['topics'] if row['id'] == composer['topic_id'])),
                'reply_to': round_record['user_turn_id'], 'requested_reply_to': composer['reply_to'],
                'text': response.get('answer'), 'classification': 'expert_reply',
                'created_utc': utc_now(), 'input_generation': round_record['input_generation'],
                'input_revision': round_record['input_revision'], 'input_sha256': canonical_hash(round_record['draft']),
                'evidence': deepcopy(composer['evidence']), 'response': deepcopy(response),
                'knowledge_sources': deepcopy(round_record.get('knowledge_sources',
                    round_record['draft']['context'].get('selected_sources')))})
        round_record.update(active_job_id=None, next_index=round_record['next_index'] + 1)
        # Failure stops this round; resume never silently retries a failed role.
        if state != 'SUCCEEDED' or response.get('status') in {'FAILED', 'NOT_CONFIGURED', 'STOPPED'}:
            round_record['status'] = 'INTERRUPTED' if state in {'CANCELLED', 'INTERRUPTED'} or response.get('status') == 'STOPPED' else 'FAILED'
        else:
            round_record['status'] = 'COMPLETED' if round_record['next_index'] == len(round_record['roles']) else 'READY'
        return True

    def command(self, identifier, operation, arguments, *, session_id, expected_generation, command_id=None):
        if operation not in SPECIAL_OPERATIONS:
            return super().command(identifier, operation, arguments, session_id=session_id,
                                   expected_generation=expected_generation, command_id=command_id)
        if arguments != {}:
            raise ValueError('Discussion progression requires empty arguments; edit the draft explicitly first')
        if session_id != self.session_id:
            raise ValueError('Document session is stale; reopen after service restart')
        if type(expected_generation) is not int or expected_generation < 0:
            raise ValueError('An exact input generation is required')
        command_id = check_id(command_id or 'C' + uuid.uuid4().hex)
        signature = canonical_hash(dict(document_id=identifier, operation=operation, arguments=arguments,
            session_id=session_id, expected_generation=expected_generation))
        with self._lock(identifier):
            self.read(identifier)
            current = self._documents[identifier]
            receipt = self._folder(identifier) / 'commands' / (command_id + '.json')
            if receipt.exists():
                prior = load_json(receipt)
                if prior['request_hash'] != signature:
                    raise ValueError('command_id conflicts with an earlier request')
                if 'response' in prior:
                    return prior['response']
                if prior.get('applied') or command_id in current.get('_expert_applied_commands', []):
                    response = {'document': self._public(current), 'command_id': command_id,
                                'recovered_after_response_loss': True}
                    save_json(receipt, {'request_hash': signature, 'response': response})
                    return response
                if any(row.get('command_id') == command_id for row in self._state(current)['rounds']) or any(
                        row.get('command_id') == command_id for row in self._state(current)['turns']):
                    # Dispatch may have been submitted while its response was lost.
                    response = {'document': self._public(current), 'command_id': command_id,
                                'recovered_after_response_loss': True}
                    save_json(receipt, {'request_hash': signature, 'response': response})
                    return response
                raise ValueError('Previous command outcome is unconfirmed; reread before a new command')
            if current['generation'] != expected_generation:
                raise ValueError('Document generation changed; reread before applying')
            document = deepcopy(current)
            state = self._state(document)
            active = next((row for row in state['rounds'] if row['status'] in {'READY', 'RUNNING'}), None)
            if operation in {'expert.ask', 'expert.intervene'}:
                self._validate_question(document, needs_roles=operation == 'expert.ask')
            if operation == 'expert.ask' and (state['paused'] or active):
                raise ValueError('Resume the discussion or finish the active round before requesting another')
            save_json(receipt, {'request_hash': signature, 'operation': operation, 'state': 'APPLYING'})
            document.setdefault('_expert_applied_commands', []).append(command_id)
            job = None
            changed = False
            if operation in {'expert.ask', 'expert.intervene'}:
                turn = self._user_turn(document, command_id)
                changed = True
                if operation == 'expert.ask':
                    active = {'id': 'B' + uuid.uuid4().hex, 'command_id': command_id,
                        'user_turn_id': turn['id'], 'roles': deepcopy(document['draft']['participants']),
                        'sessions': {role: 'E' + uuid.uuid4().hex for role in document['draft']['participants']},
                        'next_index': 0, 'active_job_id': None, 'status': 'READY',
                        'draft': deepcopy(document['draft']),
                        'knowledge_sources': selected_source_refs(document['draft']['context']),
                        'input_generation': document['generation'],
                        'input_revision': document['input_revision'], 'history': deepcopy(state['turns'])}
                    state['rounds'].append(active)
                    self._changed(document)
                    self._persist_draft(document)
                    self._documents[identifier] = document
                    job = self._submit_next(document, active)
                    changed = False  # generation already advanced before publishing dispatch
            elif operation in {'expert.pause', 'expert.resume'}:
                paused = operation == 'expert.pause'
                changed = state['paused'] != paused
                state['paused'] = paused
            elif operation == 'expert.advance' and active:
                changed = self._collect(document, active)
                if active['status'] in {'READY', 'RUNNING'} and not state['paused'] and not active.get('active_job_id'):
                    job = self._submit_next(document, active)
                    changed = True
            if changed:
                self._changed(document)
            self._persist_draft(document)
            self._documents[identifier] = document
            # A completed state persists before the response, allowing lost-response recovery.
            save_json(receipt, {'request_hash': signature, 'operation': operation, 'applied': True})
            response = {'document': self._public(document), 'command_id': command_id}
            if job is not None:
                response['job'] = job
            save_json(receipt, {'request_hash': signature, 'response': response})
            return response
