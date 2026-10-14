"""Typed commands routed to the actual native owner; never a solver scheduler."""
from copy import deepcopy
from pathlib import Path
import secrets
import threading
import time
import uuid

from .storage import canonical_hash, check_id, load_json, save_json, utc_now


TERMINAL = {'SUCCEEDED', 'FAILED', 'CANCELLED', 'INTERRUPTED'}
CAPABILITIES = {
    'post': {'post.inspect', 'post.select_array', 'document.save', 'document.activate',
             'post.source_add', 'post.source_select', 'post.source_repair',
             'post.comparison_edit', 'post.mapping_validate', 'post.sample',
             'post.filter_edit', 'post.measurement_edit', 'post.measurement_capture',
             'post.measurement_snapshot', 'post.measurement_open', 'post.contact_inspect', 'post.contact_measurement',
             'post.apply', 'post.show_analysis', 'post.reset', 'post.undo', 'post.redo', 'post.export'},
    'pre': {'pre.inspect', 'pre.set_property', 'pre.set_datum', 'pre.select', 'pre.freeze',
            'document.save', 'document.undo', 'document.redo', 'document.activate',
            'pre.workbench', 'pre.export_native_copy', 'pre.validate',
            'pre.research.discover', 'pre.research.register', 'pre.research.remove', 'pre.research.prepare', 'pre.research.connect_assembly',
            'pre.parameters.discover', 'pre.parameters.probe', 'pre.parameters.register',
            'pre.parameters.update', 'pre.parameters.remove', 'pre.parameters.preflight',
            'pre.project.inspect', 'pre.project.save', 'pre.project.open', 'pre.links.record',
            'pre.assembly.create', 'pre.assembly.link', 'pre.joint.create', 'pre.joint.update', 'pre.joint.remove',
            'pre.motion.inspect', 'pre.motion.configure', 'pre.motion.set_view', 'pre.motion.save_editor', 'pre.motion.calculate', 'pre.motion.frame',
            'pre.motion.play', 'pre.motion.pause', 'pre.motion.stop', 'pre.motion.cancel', 'pre.motion.path', 'pre.motion.adopt_pose',
            'pre.fem.mesh_settings', 'pre.fem.mesh_local_size', 'pre.fem.mesh_generate',
            'pre.fem.mesh_cancel', 'pre.fem.mesh_quality', 'pre.fem.mesh_highlight',
            'pre.fem.region_set', 'pre.fem.region_remove', 'pre.fem.condition_set',
            'pre.fem.condition_repair', 'pre.fem.material_set', 'pre.fem.task_edit',
            'pre.contact.set', 'pre.contact.remove', 'pre.contact.swap', 'pre.contact.highlight',
            'pre.contact.preview_rebind', 'pre.contact.apply_rebind', 'pre.contact.cancel_rebind',
            'pre.contact.prepare_meshes', 'pre.contact.inspect', 'pre.contact.freeze',
            'pre.contact.geometry', 'pre.contact.steps_read', 'pre.contact.steps_set'},
}


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
                running = self._running(host)
                if (running is not None and running.get('phase') == 'APPLYING'
                        and time.monotonic() - host['_contact_seen'] <= self.timeout):
                    # The service acknowledged a synchronous native operation.
                    # Its missing GUI tick is not proof of failure or progress.
                    # Keep this exact completion channel; never replay the call.
                    continue
                kind = 'transport_timeout' if running is not None and running.get('phase') == 'APPLYING' else 'gui_timeout'
                self._disconnect(host, 'Native owner transport expired during APPLYING; outcome is unconfirmed'
                                 if kind == 'transport_timeout' else 'Native owner heartbeat expired; no command is replayed', kind=kind)

    def _running(self, host):
        return next((command for command in self._commands.values()
                     if (command['host_id'], command['session_id'], command['state'])
                     == (host['host_id'], host['session_id'], 'RUNNING')), None)

    def _activity(self, host):
        running = self._running(host)
        age = max(0.0, time.monotonic() - host['_seen'])
        applying = host['connected'] and running is not None and running.get('phase') == 'APPLYING'
        status = ('APPLYING_UNCONFIRMED' if age > self.timeout else 'APPLYING') if applying else (
            'IDLE' if host['connected'] else 'DISCONNECTED')
        return {'dispatcher_status': status, 'busy_command_id': running['command_id'] if applying else None,
                'gui_heartbeat_age_s': age, 'gui_responsive': bool(host['connected'] and not applying),
                'state_freshness': 'last_owner_report_busy' if applying else 'last_owner_report'}

    def _disconnect(self, host, reason, *, kind='closed'):
        host['connected'] = False
        host['_disconnect_kind'] = kind
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
            kind = document.get('kind')
            if identifier in result or identifier[0] in {'M', 'T', 'N', 'B'} or kind not in CAPABILITIES:
                raise ValueError('Use unique native Pre/Post document identities')
            for key in ('generation', 'view_generation'):
                if type(document.get(key)) is not int or document[key] < 0:
                    raise ValueError('Native generations must be nonnegative integers')
            capabilities = document.get('capabilities', [])
            if not isinstance(capabilities, list) or any(item not in CAPABILITIES[kind] for item in capabilities):
                raise ValueError('Unsupported native command capability')
            canonical_hash(document)
            result[identifier] = deepcopy(document)
        return result

    def register(self, *, host_id, session_id, application, version, execution_mode, documents, registration_nonce):
        check_id(host_id)
        check_id(session_id)
        if application not in {'paraview', 'freecad'} or execution_mode not in {'gui', 'headless'} or not isinstance(version, str):
            raise ValueError('Identify the actual FreeCAD or ParaView owner')
        if not isinstance(registration_nonce, str) or not 32 <= len(registration_nonce) <= 128:
            raise ValueError('Native registration requires a private retry nonce')
        descriptors = self._descriptors(documents)
        if any(row['kind'] != {'paraview': 'post', 'freecad': 'pre'}[application] for row in descriptors.values()):
            raise ValueError('Native application and document kind disagree')
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
                        service_session_id=self.session_id, _seen=time.monotonic(),
                        _contact_seen=time.monotonic(), _registration_nonce=registration_nonce)
            self._hosts[host_id] = host
            return {key: host[key] for key in ('host_id', 'session_id', 'host_token', 'service_session_id')}

    def _authenticate(self, host_id, session_id, host_token, *, completion_id=None):
        self._expire()
        host = self._hosts.get(check_id(host_id))
        if (not host or host['session_id'] != session_id
                or not isinstance(host_token, str) or not secrets.compare_digest(host['host_token'], host_token)):
            raise ValueError('Native owner session is stale or unauthenticated')
        if not host['connected']:
            command = self._commands.get(completion_id)
            recovering = (host.get('_disconnect_kind') == 'transport_timeout' and command is not None
                          and (command['host_id'], command['session_id'], command['service_session_id'])
                          == (host_id, session_id, self.session_id)
                          and (command.get('phase') == 'APPLYING' and command['state'] == 'INTERRUPTED'
                               or command.get('phase') == 'FINISHED' and command.get('outcome') is not None))
            if not recovering:
                raise ValueError('Native owner session is stale or unauthenticated')
        return host

    def hosts(self):
        with self._lock:
            self._expire()
            return {'hosts': [{**{key: deepcopy(value) for key, value in host.items()
                               if key not in {'host_token', 'documents'} and not key.startswith('_')},
                               **self._activity(host)} for host in self._hosts.values()]}

    def documents(self):
        with self._lock:
            self._expire()
            return [{**deepcopy(document), 'host_id': host['host_id'], 'session_id': host['session_id'],
                     'connected': host['connected'], 'execution_mode': host['execution_mode'],
                     **self._activity(host), 'service_session_id': self.session_id}
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
            if document['busy_command_id']:
                raise ValueError('BUSY_APPLYING: wait for the native command outcome and reread the document')
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
            host = self._authenticate(host_id, session_id, host_token)
            host['_contact_seen'] = time.monotonic()  # Transport presence, never GUI freshness.
            if self._running(host) is not None:
                return {'command': None}
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
            host = self._authenticate(host_id, session_id, host_token,
                                      completion_id=check_id(command_id) if event == 'finished' else None)
            command = None
            if event in {'started', 'finished'}:
                command = self._commands[check_id(command_id)]
                if (command['host_id'], command['session_id']) != (host_id, session_id):
                    raise ValueError('Command belongs to another native owner')
                if event == 'finished' and (not isinstance(outcome, dict) or outcome.get('state') not in {'SUCCEEDED', 'FAILED', 'CANCELLED'}):
                    raise ValueError('A terminal native outcome is required')
                recovering = (event == 'finished' and command['state'] == 'INTERRUPTED'
                              and command.get('phase') == 'APPLYING'
                              and host.get('_disconnect_kind') == 'transport_timeout')
                if command['state'] in TERMINAL and not recovering:
                    if event == 'finished' and command.get('outcome') == outcome:
                        return {'accepted': True}
                    raise ValueError('Native command already has a terminal outcome')
                if command['state'] != 'RUNNING' and not recovering:
                    raise ValueError('Command was not dispatched to the native owner')
                if event == 'started' and command.get('phase') == 'APPLYING':
                    host['_contact_seen'] = time.monotonic()
                    return {'accepted': True}  # A retry is not a fresh GUI heartbeat.
                if event == 'finished':
                    canonical_hash(outcome)
            if descriptors is not None:
                if set(descriptors) != set(host['documents']):
                    raise ValueError('Changing native document identities requires a new owner session')
                for identifier, document in descriptors.items():
                    old = host['documents'][identifier]
                    if document['kind'] != old['kind']:
                        raise ValueError('Native document kind cannot change')
                    if document['generation'] >= old['generation'] and document['view_generation'] >= old['view_generation']:
                        host['documents'][identifier] = document
            host['_seen'] = time.monotonic()
            host['_contact_seen'] = time.monotonic()
            if event == 'closed':
                self._disconnect(host, 'Native owner closed')
            elif event == 'started':
                command['phase'] = 'APPLYING'
                command['started_utc'] = utc_now()
                self._persist(command)
            elif event == 'finished':
                if recovering:
                    command['recovered_interruption'] = {
                        'state': command['state'], 'error': deepcopy(command['error']),
                        'recorded_utc': command['updated_utc'], 'completion_reported_utc': utc_now()}
                    command.pop('error', None)
                    command.pop('application_unconfirmed', None)
                command.update(state=outcome['state'], outcome=deepcopy(outcome), phase='FINISHED',
                               final_generation=host['documents'][command['document_id']]['generation'],
                               final_view_generation=host['documents'][command['document_id']]['view_generation'])
                self._persist(command)
                if recovering and not any(other is not host and other['connected']
                                           and set(other['documents']) & set(host['documents'])
                                           for other in self._hosts.values()):
                    # Only the exact old completion re-establishes its owner.
                    # A replacement owner is never displaced or rewritten.
                    host['connected'] = True
                    host.pop('_disconnect_kind', None)
            return {'accepted': True}

    def status(self, identifier):
        with self._lock:
            self._expire()
            command = deepcopy(self._commands[check_id(identifier)])
            host = self._hosts.get(command['host_id'])
            if command['state'] == 'RUNNING' and host is not None:
                command['owner_status'] = self._activity(host)
            elif command['state'] == 'INTERRUPTED' and host is not None:
                command['completion_recoverable'] = (
                    host.get('_disconnect_kind') == 'transport_timeout' and command.get('phase') == 'APPLYING'
                    and (command['session_id'], command['service_session_id']) == (host['session_id'], self.session_id))
            return command

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
