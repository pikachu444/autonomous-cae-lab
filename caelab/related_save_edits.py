"""Owner-separated edit previews for a shared Material/Plan paste operation.

The Numerical widget owns typed cells, binding/readonly semantics and delegates.
This module owns only the existing document command boundary. Invalid but JSON-
serializable drafts remain saveable. It never synthesizes a second Plan draft.
"""
from __future__ import annotations
from copy import deepcopy
import uuid

from .related_save import input_identity
from .storage import canonical_hash, check_id, load_json, save_json


def mutation_marker(document, *, operation, command_id, request_hash):
    return {'operation': operation, 'command_id': command_id, 'request_hash': request_hash,
            'session_id': document['session_id'], 'generation': document['generation'],
            'input_revision': document['input_revision'], 'input_sha256': canonical_hash(document['draft'])}


def recover_mutation(owner, identifier, command_id):
    """Recover only an exact marker already published in working/saved state."""
    path = owner._folder(identifier) / 'commands' / (check_id(command_id) + '.json')
    if not path.exists():
        return None
    prior = load_json(path)
    if 'response' in prior:
        return prior['response']
    if prior.get('operation') not in {owner.update_operation, 'document.undo', 'document.redo'}:
        return None
    candidates = []
    working = owner._folder(identifier) / 'working.json'
    if working.exists():
        candidates.append(load_json(working))
    manifest = owner._manifest(identifier)
    if manifest:
        candidates.append(owner._verify_revision(identifier, manifest['revision']))
    for document in candidates:
        marker = document.get('_mutation_command') or {}
        if (marker.get('command_id') != command_id or marker.get('request_hash') != prior['request_hash']
                or marker.get('operation') != prior['operation'] or document.get('id') != identifier):
            continue
        if (document['input_revision'] != marker['input_revision']
                or canonical_hash(document['draft']) != marker['input_sha256']
                or document['generation'] != marker['generation']):
            raise ValueError('Published mutation marker and input differ')
        current = owner._documents.get(identifier)
        if (current is not None and current['session_id'] == marker['session_id']
                and current['generation'] == prior['input_generation']
                and current['input_revision'] == prior['input_revision']
                and canonical_hash(current['draft']) == canonical_hash(prior['input'])):
            # The durable write completed before a lost in-memory assignment.
            # Never replace an already newer acknowledged buffer.
            owner._documents[identifier] = deepcopy(document)
        response = {'document': owner._public(document), 'command_id': command_id,
                    'recovered_after_response_loss': True}
        save_json(path, {'request_hash': prior['request_hash'], 'response': response})
        return response
    return None


def _diff(before, after, path=''):
    if isinstance(before, dict) and isinstance(after, dict):
        result = []
        for key in sorted(set(before) | set(after)):
            pointer = path + '/' + key.replace('~', '~0').replace('/', '~1')
            if key not in before or key not in after:
                result.append({'path': pointer, 'before_present': key in before,
                    'after_present': key in after, 'before': deepcopy(before.get(key)), 'after': deepcopy(after.get(key))})
            else:
                result.extend(_diff(before[key], after[key], pointer))
        return result
    if isinstance(before, list) and isinstance(after, list) and len(before) == len(after):
        return [item for i, (a, b) in enumerate(zip(before, after)) for item in _diff(a, b, path + '/' + str(i))]
    return [] if before == after and type(before) is type(after) else [
        {'path': path, 'before_present': True, 'after_present': True, 'before': deepcopy(before), 'after': deepcopy(after)}]


def preview_edits(resolve_owner, requests):
    if not isinstance(requests, list) or not 1 <= len(requests) <= 2:
        raise ValueError('Preview Material and/or Plan separately, at most two owners')
    items, seen = [], set()
    for request in requests:
        if not isinstance(request, dict) or set(request) != {'identity', 'buffer'}:
            raise ValueError('Each edit requires the retained base identity and local buffer')
        identity = deepcopy(request['identity'])
        identifier = check_id(identity['document_id'])
        owner = resolve_owner(identifier)
        if owner.kind not in {'material', 'numerical'} or identifier in seen:
            raise ValueError('Each Material/Plan owner can appear once')
        seen.add(identifier)
        with owner._lock(identifier):
            current = owner.read(identifier)
            if set(identity) != set(input_identity(current)):
                raise ValueError('Use the complete owner identity, without implicit refresh')
            buffer = owner._draft(request['buffer'])
            items.append({'identity': identity, 'buffer': buffer, 'command_id': 'C' + uuid.uuid4().hex,
                'content_sha256': owner._fingerprint(current),
                'conflict': identity != input_identity(current),
                'changes': _diff(current['draft'], buffer), 'diagnostics': owner.diagnostics(buffer),
                'invalid_draft_saveable': True})
    result = {'version': 1, 'items': items}
    return {**result, 'preview_sha256': canonical_hash(result)}


def execute_edits(resolve_owner, preview):
    payload = {key: deepcopy(preview[key]) for key in ('version', 'items')}
    if payload['version'] != 1 or canonical_hash(payload) != preview.get('preview_sha256'):
        raise ValueError('Owner patch preview changed')
    outcomes = []
    for item in payload['items']:
        identity, command_id = item['identity'], check_id(item['command_id'])
        identifier = identity['document_id']
        owner = resolve_owner(identifier)
        outcome = {'document_id': identifier, 'command_id': command_id, 'reviewed_identity': deepcopy(identity),
                   'reviewed_buffer': deepcopy(item['buffer'])}
        with owner._lock(identifier):
            try:
                current = owner.read(identifier)
                signature = canonical_hash({'document_id': identifier, 'operation': owner.update_operation,
                    'arguments': {'draft': item['buffer']}, 'session_id': identity['session_id'],
                    'expected_generation': identity['generation']})
                receipt = owner._folder(identifier) / 'commands' / (command_id + '.json')
                if receipt.exists():
                    prior = load_json(receipt)
                    if prior['request_hash'] != signature:
                        raise ValueError('Patch command ID conflicts with a different request')
                    response = recover_mutation(owner, identifier, command_id)
                    if response is None:
                        outcome.update(state='UNKNOWN', error='Admitted edit has no confirmed outcome; do not replay')
                    else:
                        outcome.update(state='APPLIED', response=deepcopy(response))
                elif item['conflict'] or input_identity(current) != identity or owner._fingerprint(current) != item['content_sha256']:
                    outcome.update(state='CONFLICT', current_identity=input_identity(current),
                                   error='Owner changed; buffer preserved without merge or retry')
                else:
                    response = owner.command(identifier, owner.update_operation, {'draft': item['buffer']},
                        session_id=identity['session_id'], expected_generation=identity['generation'], command_id=command_id)
                    outcome.update(state='APPLIED', response=deepcopy(response))
            except Exception as error:
                receipt = owner._folder(identifier) / 'commands' / (command_id + '.json')
                outcome.update(state='UNKNOWN' if receipt.exists() else 'FAILED',
                               error={'type': type(error).__name__, 'message': str(error)})
            # A delayed reply acknowledges its exact input, not whatever is
            # currently visible. The GUI must not replace its local buffer here.
            try:
                outcome['current_identity'] = input_identity(owner.read(identifier))
            except Exception as error:
                outcome['current_read_error'] = str(error)
        outcomes.append(outcome)
    return {'outcomes': outcomes, 'all_applied': all(row['state'] == 'APPLIED' for row in outcomes),
            'atomic_across_owners': False, 'saved': False, 'local_buffers_replaced': False}
