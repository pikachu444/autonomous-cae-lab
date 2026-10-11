"""Typed commands routed to the actual native owner; never a solver scheduler."""
from copy import deepcopy
from pathlib import Path
import secrets
import threading
import time
import uuid

from .storage import canonical_hash, check_id, load_json, save_json, utc_now


TERMINAL = {'SUCCEEDED', 'FAILED', 'CANCELLED', 'INTERRUPTED'}


class NativeCommands:
    def __init__(self, root, service_session_id, *, heartbeat_timeout=30):
        self.root = Path(root) / 'native_commands'
        self.root.mkdir(parents=True, exist_ok=True)
        self.session_id = service_session_id
        self.timeout = heartbeat_timeout
        self._lock = threading.RLock()
        self._hosts, self._commands = {}, {}
        for path in self.root.glob('*.json'):
            command = load_json(path)
            if command['state'] not in TERMINAL:
                self._interrupt(command, 'Service restarted; native application is unconfirmed')
            self._commands[command['command_id']] = command

    def _persist(self, command):
        command['updated_utc'] = utc_now()
        save_json(self.root / (check_id(command['command_id']) + '.json'), command)

    def _interrupt(self, command, reason):
        command.update(application_unconfirmed=command['state'] != 'QUEUED',
                       state='INTERRUPTED', error={'code': 'OWNER_DISCONNECTED', 'message': reason})
        self._persist(command)

    def _expire(self):
        for host in self._hosts.values():
            if host['connected'] and time.monotonic() - host['_seen'] > self.timeout:
                self._disconnect(host, 'Native owner heartbeat expired; no command is replayed')

    def _disconnect(self, host, reason):
        host['connected'] = False
        for command in self._commands.values():
            if (command['host_id'], command['session_id']) == (host['host_id'], host['session_id']) and command['state'] not in TERMINAL:
                self._interrupt(command, reason)

    @staticmethod
    def _descriptors(documents):
        if not isinstance(documents, list) or len(documents) > 100:
            raise ValueError('Native documents must be a bounded list')
        result = {}
        for document in documents:
            identifier = check_id(document['id'])
            if identifier in result or identifier.startswith('M') or document.get('kind') != 'post':
                raise ValueError('Use unique Post document identities')
            for key in ('generation', 'view_generation'):
                if type(document.get(key)) is not int or document[key] < 0:
                    raise ValueError('Native generations must be nonnegative integers')
            capabilities = document.get('capabilities', [])
            if not isinstance(capabilities, list) or any(item not in {'post.inspect', 'post.select_array', 'document.save'} for item in capabilities):
                raise ValueError('Unsupported native command capability')
            canonical_hash(document)
            result[identifier] = deepcopy(document)
        return result

    def register(self, *, host_id, session_id, application, version, execution_mode, documents, registration_nonce):
        check_id(host_id)
        check_id(session_id)
        if application != 'paraview' or execution_mode not in {'gui', 'headless'} or not isinstance(version, str):
            raise ValueError('Only an explicitly identified ParaView owner is supported')
        if not isinstance(registration_nonce, str) or not 32 <= len(registration_nonce) <= 128:
            raise ValueError('Native registration requires a private retry nonce')
        descriptors = self._descriptors(documents)
        with self._lock:
            self._expire()
            existing = self._hosts.get(host_id)
            if existing and existing['connected']:
                if existing['session_id'] != session_id:
                    raise ValueError('Host identity is already owned by a live session')
                if not secrets.compare_digest(existing['_registration_nonce'], registration_nonce):
                    raise ValueError('Native registration retry proof is invalid')
                # A registration retry recovers the token without discarding queued commands.
                return {key: existing[key] for key in ('host_id', 'session_id', 'host_token', 'service_session_id')}
            for host in self._hosts.values():
                if host['connected'] and set(host['documents']) & set(descriptors):
                    raise ValueError('Document already has a live native owner')
            host = dict(host_id=host_id, session_id=session_id, application=application,
                        version=version, execution_mode=execution_mode, documents=descriptors,
                        connected=True, host_token=secrets.token_urlsafe(32),
                        service_session_id=self.session_id, _seen=time.monotonic(), _registration_nonce=registration_nonce)
            self._hosts[host_id] = host
            return {key: host[key] for key in ('host_id', 'session_id', 'host_token', 'service_session_id')}

    def _authenticate(self, host_id, session_id, host_token):
        self._expire()
        host = self._hosts.get(check_id(host_id))
        if (not host or not host['connected'] or host['session_id'] != session_id
                or not isinstance(host_token, str) or not secrets.compare_digest(host['host_token'], host_token)):
            raise ValueError('Native owner session is stale or unauthenticated')
        return host

    def hosts(self):
        with self._lock:
            self._expire()
            return {'hosts': [{key: deepcopy(value) for key, value in host.items()
                               if key not in {'host_token', 'documents'} and not key.startswith('_')} for host in self._hosts.values()]}

    def documents(self):
        with self._lock:
            self._expire()
            return [{**deepcopy(document), 'host_id': host['host_id'], 'session_id': host['session_id'],
                     'connected': host['connected'], 'execution_mode': host['execution_mode'],
                     'state_freshness': 'last_owner_report', 'service_session_id': self.session_id}
                    for host in self._hosts.values() for document in host['documents'].values()]

    def read(self, identifier):
        matches = [document for document in self.documents() if document['id'] == identifier]
        if not matches:
            raise KeyError('Native document is not registered')
        return next((document for document in matches if document['connected']), matches[-1])

    def submit(self, document_id, operation, arguments, *, session_id, expected_generation, command_id=None):
        if not isinstance(arguments, dict) or type(expected_generation) is not int or expected_generation < 0:
            raise ValueError('Command needs arguments and an exact input generation')
        identifier = check_id(command_id or 'C' + uuid.uuid4().hex)
        request = dict(document_id=check_id(document_id), operation=operation, arguments=deepcopy(arguments),
                       session_id=session_id, expected_generation=expected_generation)
        signature = canonical_hash(request)
        with self._lock:
            self._expire()
            if identifier in self._commands:
                prior = self._commands[identifier]
                if prior['request_hash'] != signature:
                    raise ValueError('command_id conflicts with an earlier request')
                return deepcopy(prior)
            document = self.read(document_id)
            if not document['connected'] or document['session_id'] != session_id:
                raise ValueError('Native owner session is stale or disconnected')
            if document['generation'] != expected_generation:
                raise ValueError('Document generation changed; reread before applying')
            if operation not in document.get('capabilities', []):
                raise ValueError('Operation is not supported by this native owner')
            target = request['arguments'].pop('target', {})
            if not isinstance(target, dict):
                raise ValueError('Native command target must be an object')
            command = {**request, 'command_id': identifier, 'host_id': document['host_id'], 'target': target,
                       'service_session_id': self.session_id, 'request_hash': signature, 'state': 'QUEUED',
                       'supports_cancel': 'queued_only', 'cancel_requested': False, 'created_utc': utc_now()}
            self._persist(command)
            self._commands[identifier] = command
            return deepcopy(command)

    def next(self, host_id, *, session_id, host_token):
        with self._lock:
            self._authenticate(host_id, session_id, host_token)
            for command in self._commands.values():
                if (command['host_id'], command['session_id'], command['state']) == (host_id, session_id, 'QUEUED'):
                    command.update(state='RUNNING', phase='DISPATCHED')
                    self._persist(command)
                    return {'command': deepcopy(command)}
            return {'command': None}

    def event(self, host_id, *, session_id, host_token, event, documents=None, command_id=None, outcome=None):
        if event not in {'heartbeat', 'started', 'finished', 'closed'}:
            raise ValueError('Unknown native owner event')
        descriptors = self._descriptors(documents) if documents is not None else None
        with self._lock:
            host = self._authenticate(host_id, session_id, host_token)
            host['_seen'] = time.monotonic()
            command = None
            if event in {'started', 'finished'}:
                command = self._commands[check_id(command_id)]
                if (command['host_id'], command['session_id']) != (host_id, session_id):
                    raise ValueError('Command belongs to another native owner')
                if event == 'finished' and (not isinstance(outcome, dict) or outcome.get('state') not in {'SUCCEEDED', 'FAILED', 'CANCELLED'}):
                    raise ValueError('A terminal native outcome is required')
                if command['state'] in TERMINAL:
                    if event == 'finished' and command.get('outcome') == outcome:
                        return {'accepted': True}
                    raise ValueError('Native command already has a terminal outcome')
                if command['state'] != 'RUNNING':
                    raise ValueError('Command was not dispatched to the native owner')
            if descriptors is not None:
                if set(descriptors) != set(host['documents']):
                    raise ValueError('Changing native document identities requires a new owner session')
                for identifier, document in descriptors.items():
                    old = host['documents'][identifier]
                    if document['generation'] >= old['generation'] and document['view_generation'] >= old['view_generation']:
                        host['documents'][identifier] = document
            if event == 'closed':
                self._disconnect(host, 'Native owner closed')
            elif event == 'started':
                command['phase'] = 'APPLYING'
                self._persist(command)
            elif event == 'finished':
                canonical_hash(outcome)
                command.update(state=outcome['state'], outcome=deepcopy(outcome), phase='FINISHED',
                               final_generation=host['documents'][command['document_id']]['generation'],
                               final_view_generation=host['documents'][command['document_id']]['view_generation'])
                self._persist(command)
            return {'accepted': True}

    def status(self, identifier):
        with self._lock:
            self._expire()
            return deepcopy(self._commands[check_id(identifier)])

    def cancel(self, identifier):
        with self._lock:
            self._expire()
            command = self._commands[check_id(identifier)]
            if command['state'] == 'QUEUED':
                command.update(state='CANCELLED', cancel_requested=True, phase='NOT_DISPATCHED')
                self._persist(command)
            elif command['state'] not in TERMINAL:
                raise ValueError('This native command supports cancellation only before dispatch')
            return deepcopy(command)

    def shutdown(self):
        with self._lock:
            for host in self._hosts.values():
                self._disconnect(host, 'Service shut down; native application is unconfirmed')
