"""Non-transactional related saves over the existing document owners.

A coordinator records intent/outcome, never owns drafts, revisions, or Undo. A
successful document.save is immutable and is never retried to repair its peer.
Unknown outcomes require reconciliation, not automatic command replay.
"""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Callable
import uuid

from filelock import FileLock

from .storage import canonical_hash, check_id, load_json, save_json, utc_now

FORMAT = 'caelab.related_save/1'
RETRYABLE = {'FAILED', 'CONFLICT', 'BLOCKED'}


def input_identity(document: dict) -> dict:
    """Identity the GUI must keep with its buffer; no identity refresh on failure."""
    return {'document_id': document['id'], 'kind': document['kind'],
            'session_id': document['session_id'], 'generation': document['generation'],
            'input_revision': document['input_revision'],
            'input_sha256': canonical_hash(document['draft']),
            'saved_revision': document.get('saved_revision')}


def saved_reference(owner, document: dict) -> dict:
    revision = document.get('saved_revision')
    if not revision:
        raise ValueError('The document has no saved revision')
    saved = owner._verify_revision(document['id'], check_id(revision))
    if saved['input_revision'] != document['input_revision'] or canonical_hash(saved['draft']) != canonical_hash(document['draft']):
        raise ValueError('Saved revision does not contain the selected input')
    return {'document_id': saved['id'], 'kind': saved['kind'], 'saved_revision': revision,
            'input_revision': saved['input_revision'], 'input_sha256': canonical_hash(saved['draft'])}


def _expected_signature(target, command_id=None):
    identity = target['identity']
    return canonical_hash({'document_id': identity['document_id'], 'operation': 'document.save',
        'arguments': {}, 'session_id': identity['session_id'], 'expected_generation': identity['generation']})


def save_marker(document, command_id, request_hash):
    """Called by the root command patch immediately before existing _save()."""
    return {'command_id': command_id, 'request_hash': request_hash,
            'session_id': document['session_id'], 'generation': document['generation'],
            'input_revision': document['input_revision'], 'input_sha256': canonical_hash(document['draft']),
            'previous_saved_revision': document.get('_disk_revision'),
            'content_sha256': None}


def recover_saved_commands(owner, identifier):
    """Repair only a proven, published save's lost response. Never saves again.

    The root _save_command marker is in the immutable revision included in its
    hash-verified manifest. An orphan revision directory is NOT publication.
    """
    manifest = owner._manifest(identifier)
    if not manifest:
        return False
    from .evaluation import file_hash
    path = owner._folder(identifier) / 'revisions' / manifest['revision'] / 'revision.json'
    try:
        digest = file_hash(path)
    except OSError as error:
        raise ValueError('Published revision changed outside this owner or is missing') from error
    if digest != manifest['revision_sha256']:
        raise ValueError('Published revision manifest changed outside this owner')
    saved = owner._verify_revision(identifier, manifest['revision'])
    marker = saved.get('_save_command')
    if not isinstance(marker, dict):
        return False
    receipt_path = owner._folder(identifier) / 'commands' / (check_id(marker['command_id']) + '.json')
    if not receipt_path.exists():
        return False
    prior = load_json(receipt_path)
    if prior.get('request_hash') != marker['request_hash'] or prior.get('operation', 'document.save') != 'document.save':
        raise ValueError('Published save marker conflicts with the original owner command')
    if 'response' in prior:
        return False
    if (prior.get('input_revision') != marker['input_revision'] or
            canonical_hash(prior.get('input')) != marker['input_sha256']):
        raise ValueError('Published save does not prove the interrupted input identity')
    cached = owner._documents.get(identifier)
    if (cached is not None and cached.get('session_id') == marker['session_id']
            and cached.get('_disk_revision') == marker.get('previous_saved_revision')):
        if marker.get('content_sha256') == owner._fingerprint(cached):
            restored = deepcopy(saved)
            restored['session_id'] = cached['session_id']
            owner._documents[identifier] = restored
        else:
            # A later acknowledged edit/run remains dirty and untouched. Only
            # align the proven disk pointer, avoiding loss on the next reopen.
            for key in ('saved_revision', '_disk_revision', '_saved_fingerprint'):
                cached[key] = saved[key]
        owner._persist_draft(owner._documents[identifier])
    response = {'document': owner._public(saved), 'command_id': marker['command_id'],
                'recovered_after_response_loss': True}
    save_json(receipt_path, {'request_hash': prior['request_hash'], 'response': response})
    return True


class RelatedSaveCoordinator:
    def __init__(self, root: str | Path, resolve_owner: Callable):
        self.root = Path(root) / 'documents' / 'related-saves'
        self.resolve_owner = resolve_owner

    def _path(self, receipt_id):
        return self.root / (check_id(receipt_id) + '.json')

    def _lock(self, receipt_id):
        self.root.mkdir(parents=True, exist_ok=True)
        return FileLock(str(self._path(receipt_id)) + '.lock', timeout=0)

    def _write(self, receipt):
        receipt['updated_utc'] = utc_now()
        save_json(self._path(receipt['receipt_id']), receipt)

    def preview(self, requests: list[dict], *, receipt_id=None) -> dict:
        """Read-only preview. requests=[{identity: input_identity(doc), buffer: draft}].

        A buffer not yet applied to its owner blocks that item's save. The
        coordinator never turns a GUI buffer into an unrequested owner edit.
        """
        if not isinstance(requests, list) or not 1 <= len(requests) <= 16:
            raise ValueError('Select 1 to 16 existing document owners')
        targets, seen = [], set()
        for request in requests:
            if not isinstance(request, dict) or set(request) - {'identity', 'buffer'} or 'identity' not in request:
                raise ValueError('Each save item requires identity and an optional recovery buffer')
            identity = deepcopy(request['identity'])
            if not isinstance(identity, dict) or set(identity) != {
                    'document_id', 'kind', 'session_id', 'generation', 'input_revision', 'input_sha256', 'saved_revision'}:
                raise ValueError('Use the complete identity from input_identity(document)')
            identifier = check_id(identity['document_id'])
            if identity['kind'] not in {'material', 'numerical'} or identifier in seen:
                raise ValueError('Select each Material/Plan owner once')
            seen.add(identifier)
            owner = self.resolve_owner(identifier)
            with owner._lock(identifier):
                current = owner.read(identifier)
                buffer = deepcopy(request.get('buffer', current['draft']))
                # Reuse the owner's byte-size/JSON rules, not a second draft owner.
                owner._draft(buffer)
                problems = []
                if input_identity(current) != identity:
                    problems.append('OWNER_IDENTITY_CONFLICT')
                if canonical_hash(buffer) != identity['input_sha256']:
                    problems.append('UNAPPLIED_BUFFER')
                targets.append({'identity': identity, 'buffer': buffer,
                    'content_sha256': owner._fingerprint(current),
                    'previous_link': deepcopy(current['draft'].get('material', current['draft'].get('source'))),
                    'preview_problems': problems, 'command_id': 'C' + uuid.uuid4().hex})
        payload = {'format': FORMAT, 'receipt_id': check_id(receipt_id or 'S' + uuid.uuid4().hex),
                   'targets': targets}
        return {**payload, 'preview_sha256': canonical_hash(payload),
                'saveable_count': sum(not row['preview_problems'] for row in targets),
                'link_publication': 'EXPLICIT_SEPARATE_COMMAND'}

    def _outcome(self, target, attempt, *, synchronous_error=None):
        owner = self.resolve_owner(target['identity']['document_id'])
        identifier, command_id = target['identity']['document_id'], attempt['command_id']
        path = owner._folder(identifier) / 'commands' / (check_id(command_id) + '.json')
        expected = _expected_signature(target)
        try:
            recover_saved_commands(owner, identifier)
            prior = load_json(path) if path.exists() else None
            if prior and prior.get('request_hash') != expected:
                return {'state': 'CONFLICT', 'error': {'type': 'CommandConflict', 'message': 'Command identity already has different arguments'}}
            if prior and 'response' in prior:
                response = prior['response']
                ref = saved_reference(owner, response['document'])
                identity = target['identity']
                if (ref['input_revision'], ref['input_sha256']) != (identity['input_revision'], identity['input_sha256']):
                    raise ValueError('Save response differs from the reviewed input')
                return {'state': 'SAVED', 'saved_reference': ref, 'response': deepcopy(response),
                        'confirmed_by': 'OWNER_COMMAND_RECEIPT'}
            if synchronous_error is not None:
                # The same owner lock is held by the caller. No effect is
                # reported failed if the disk pointer changed without evidence.
                manifest = owner._manifest(identifier)
                current_revision = (manifest or {}).get('revision')
                if current_revision == target['identity'].get('saved_revision'):
                    kind = 'CONFLICT' if isinstance(synchronous_error, ValueError) and not prior else 'FAILED'
                    return {'state': kind, 'error': {'type': type(synchronous_error).__name__, 'message': str(synchronous_error)}}
            if not prior:
                return {'state': 'FAILED', 'error': {'type': 'NotDispatched',
                    'message': 'No owner command was admitted; explicit retry is required'}}
            return {'state': 'UNKNOWN', 'error': {'type': 'UnconfirmedOwnerOutcome',
                'message': 'Owner command is incomplete without proof of publication; do not replay it'}}
        except Exception as error:
            return {'state': 'UNKNOWN', 'error': {'type': type(error).__name__, 'message': str(error)}}

    def _perform(self, receipt, target):
        attempt = target['attempts'][-1]
        owner = self.resolve_owner(target['identity']['document_id'])
        identifier = target['identity']['document_id']
        with owner._lock(identifier):
            try:
                current = owner.read(identifier)
            except Exception as error:
                attempt.update(state='FAILED', error={'type': type(error).__name__, 'message': str(error)})
                target['state'] = attempt['state']
                self._write(receipt)
                return
            if (input_identity(current) != target['identity'] or
                    owner._fingerprint(current) != target['content_sha256']):
                attempt.update(state='CONFLICT', error={'type': 'OwnerConflict',
                    'message': 'The owner or retained content changed after preview; recovery buffer was not replaced'})
            elif target['preview_problems']:
                attempt.update(state='BLOCKED', error={'type': 'PreviewBlocked',
                    'message': ', '.join(target['preview_problems'])})
            else:
                attempt.update(state='APPLYING', dispatched_utc=utc_now())
                target['state'] = 'APPLYING'
                self._write(receipt)  # Intent is durable before any owner command.
                try:
                    owner.command(identifier, 'document.save', {},
                        session_id=target['identity']['session_id'], expected_generation=target['identity']['generation'],
                        command_id=attempt['command_id'])
                except Exception as error:
                    attempt.update(self._outcome(target, attempt, synchronous_error=error))
                else:
                    attempt.update(self._outcome(target, attempt))
            target['state'] = attempt['state']
            if attempt.get('saved_reference'):
                target['saved_reference'] = deepcopy(attempt['saved_reference'])
        self._write(receipt)

    @staticmethod
    def _summary(receipt):
        states = [target['state'] for target in receipt['targets']]
        receipt['state'] = ('UNCONFIRMED' if any(s in {'APPLYING', 'UNKNOWN'} for s in states) else
            'SAVED' if all(s == 'SAVED' for s in states) else 'PARTIAL' if 'SAVED' in states else 'FAILED')
        receipt['all_saved'] = all(s == 'SAVED' for s in states)
        receipt['link_published'] = receipt.get('publication', {}).get('state') == 'PUBLISHED'
        return receipt

    def execute(self, preview: dict) -> dict:
        payload = {key: deepcopy(preview[key]) for key in ('format', 'receipt_id', 'targets')}
        if payload['format'] != FORMAT or canonical_hash(payload) != preview.get('preview_sha256'):
            raise ValueError('Related save preview changed')
        with self._lock(payload['receipt_id']):
            path = self._path(payload['receipt_id'])
            if path.exists():
                receipt = load_json(path)
                if receipt['preview_sha256'] != preview['preview_sha256']:
                    raise ValueError('Receipt identity conflicts with a different preview')
                return self._read_locked(receipt)  # Never redispatch a prior request.
            receipt = {**payload, 'preview_sha256': preview['preview_sha256'], 'created_utc': utc_now(),
                       'publication': {'state': 'NOT_REQUESTED', 'attempts': []}}
            for target in receipt['targets']:
                target.update(state='NOT_STARTED', attempts=[{'command_id': target.pop('command_id'),
                    'identity': deepcopy(target['identity']), 'buffer': deepcopy(target['buffer']), 'state': 'NOT_STARTED'}])
            self._write(receipt)
            for target in receipt['targets']:
                self._perform(receipt, target)
            self._summary(receipt)
            self._write(receipt)
            return deepcopy(receipt)

    def _read_locked(self, receipt):
        for target in receipt['targets']:
            if (target['state'] in {'APPLYING', 'UNKNOWN'}
                    or target['attempts'][-1]['state'] == 'APPLYING'):
                owner = self.resolve_owner(target['identity']['document_id'])
                with owner._lock(target['identity']['document_id']):
                    outcome = self._outcome(target, target['attempts'][-1])
                target['attempts'][-1].update(outcome)
                target['state'] = outcome['state']
                if outcome.get('saved_reference'):
                    target['saved_reference'] = deepcopy(outcome['saved_reference'])
            elif target['state'] == 'NOT_STARTED':
                target['state'] = target['attempts'][-1]['state'] = 'FAILED'
                target['attempts'][-1]['error'] = {'type': 'InterruptedBeforeDispatch', 'message': 'Explicit retry required'}
        self._summary(receipt)
        self._write(receipt)
        result = deepcopy(receipt)
        # Recovery does not open/overwrite a GUI buffer. Current owner status is
        # auxiliary, explicitly distinguished from saved refs and receipt input.
        result['recovery'] = [{'document_id': row['identity']['document_id'],
            'saved_reference': deepcopy(row.get('saved_reference')), 'reviewed_buffer': deepcopy(row['buffer']),
            'reviewed_identity': deepcopy(row['identity']), 'state': row['state']} for row in receipt['targets']]
        return result

    def read_receipt(self, receipt_id) -> dict:
        with self._lock(receipt_id):
            return self._read_locked(load_json(self._path(receipt_id)))

    def retry(self, receipt_id, preview: dict) -> dict:
        """Retry ONLY explicitly selected failed items, using a fresh reviewed CAS.

        The caller must obtain a new preview after fixing the path or resolving
        a conflict. Old attempts and their unapplied buffers remain in receipt.
        """
        payload = {key: deepcopy(preview[key]) for key in ('format', 'receipt_id', 'targets')}
        if canonical_hash(payload) != preview.get('preview_sha256'):
            raise ValueError('Retry preview changed')
        with self._lock(receipt_id):
            receipt = load_json(self._path(receipt_id))
            by_id = {t['identity']['document_id']: t for t in receipt['targets']}
            selected = []
            for proposed in preview['targets']:
                target = by_id.get(proposed['identity']['document_id'])
                if target is None or target['state'] not in RETRYABLE:
                    raise ValueError('Retry may select only failed/conflicted/blocked items, never a saved or unknown item')
                if any(a['command_id'] == proposed['command_id'] for t in receipt['targets'] for a in t['attempts']):
                    raise ValueError('Retry requires a new command ID')
                selected.append((target, proposed))
            for target, proposed in selected:
                previous_identity = deepcopy(target['identity'])
                for key in ('identity', 'buffer', 'content_sha256', 'preview_problems'):
                    target[key] = deepcopy(proposed[key])
                target['attempts'].append({'command_id': proposed['command_id'], 'state': 'NOT_STARTED',
                    'identity': deepcopy(target['identity']), 'buffer': deepcopy(target['buffer']),
                    'replaces_reviewed_identity': previous_identity})
                target['state'] = 'NOT_STARTED'
            self._write(receipt)
            for target, _ in selected:
                self._perform(receipt, target)
            self._summary(receipt)
            self._write(receipt)
            return deepcopy(receipt)

    def publish_link(self, receipt_id, *, material_id, plan_id, expected_plan: dict, command_id: str) -> dict:
        """Explicit Plan source update + a separate link save, after both saves.

        Original successful saves are never repeated. A link-update/save failure
        is a distinct publication failure and leaves the old saved Plan readable.
        A new command_id explicitly retries a failed link save without re-updating.
        """
        command_id = check_id(command_id)
        with self._lock(receipt_id):
            receipt = load_json(self._path(receipt_id))
            self._summary(receipt)
            if not receipt['all_saved']:
                raise ValueError('All selected owners must be saved before explicit link publication')
            targets = {t['identity']['document_id']: t for t in receipt['targets']}
            material, plan = targets.get(material_id), targets.get(plan_id)
            if not material or not plan or material['identity']['kind'] != 'material' or plan['identity']['kind'] != 'numerical':
                raise ValueError('Choose the saved Material and Plan in this receipt')
            publication = receipt['publication']
            if publication['state'] == 'PUBLISHED':
                return deepcopy(receipt)
            if publication['state'] in {'UPDATING', 'SAVING', 'UNKNOWN'}:
                raise ValueError('Interrupted link publication requires reconcile_publication, not replay')
            if any(a['command_id'] == command_id for a in publication['attempts']):
                return deepcopy(receipt)
            owner = self.resolve_owner(plan_id)
            with owner._lock(plan_id):
                current = owner.read(plan_id)
                if input_identity(current) != expected_plan:
                    raise ValueError('Plan changed before link publication; the caller buffer remains untouched')
                material_ref = material['saved_reference']
                source_owner = self.resolve_owner(material_id)
                source = source_owner._verify_revision(material_id, material_ref['saved_revision'])
                if saved_reference(source_owner, source) != material_ref:
                    raise ValueError('Saved Material reference changed')
                continuing = publication['state'] == 'LINK_SAVE_FAILED'
                if continuing:
                    if (current['input_revision'], canonical_hash(current['draft'])) != (
                            publication['linked_identity']['input_revision'], publication['linked_identity']['input_sha256']):
                        raise ValueError('Link draft was edited after the failed publication')
                else:
                    saved_plan = owner._verify_revision(plan_id, plan['saved_reference']['saved_revision'])
                    if (current['input_revision'], canonical_hash(current['draft']), current.get('saved_revision')) != (
                            saved_plan['input_revision'], canonical_hash(saved_plan['draft']), saved_plan['saved_revision']):
                        raise ValueError('Only the exact reviewed saved Plan can receive this link')
                attempt = {'command_id': command_id, 'expected_plan': deepcopy(expected_plan),
                           'material_reference': deepcopy(material_ref), 'state': 'STARTED'}
                publication['attempts'].append(attempt)
                if not continuing:
                    draft = deepcopy(current['draft'])
                    if draft.get('mode') == 'request':
                        draft['source'] = deepcopy(material_ref)
                    else:
                        from .numerical_document import material_reference
                        draft['material'] = {**material_reference(source),
                            'saved_revision': material_ref['saved_revision'], 'input_sha256': material_ref['input_sha256']}
                    publication.update(state='UPDATING', proposed_draft=deepcopy(draft),
                        update_command_id='C' + canonical_hash([receipt_id, command_id, 'link-update'])[:40])
                    self._write(receipt)
                    try:
                        response = owner.command(plan_id, owner.update_operation, {'draft': draft},
                            session_id=current['session_id'], expected_generation=current['generation'],
                            command_id=publication['update_command_id'])
                    except Exception as error:
                        publication.update(state='UNKNOWN', error={'type': type(error).__name__, 'message': str(error)})
                        attempt['state'] = 'UNKNOWN'
                        self._write(receipt)
                        return deepcopy(receipt)
                    current = response['document']
                    publication['linked_identity'] = input_identity(current)
                target = {'identity': input_identity(current), 'buffer': deepcopy(current['draft']),
                          'content_sha256': owner._fingerprint(current), 'preview_problems': [],
                          'attempts': [{'command_id': 'C' + canonical_hash([receipt_id, command_id, 'link-save'])[:40],
                                        'state': 'NOT_STARTED'}], 'state': 'NOT_STARTED'}
                publication.update(state='SAVING', save_target=target)
                self._write(receipt)
                self._perform(receipt, target)
                if target['state'] == 'SAVED':
                    publication.update(state='PUBLISHED', plan_reference=deepcopy(target['saved_reference']),
                                       material_reference=deepcopy(material_ref))
                elif target['state'] in RETRYABLE:
                    publication['state'] = 'LINK_SAVE_FAILED'
                else:
                    publication['state'] = 'UNKNOWN'
                attempt['state'] = publication['state']
                self._summary(receipt)
                self._write(receipt)
                return deepcopy(receipt)

    def reconcile_publication(self, receipt_id):
        """Read durable owner evidence only; never invoke update/save here."""
        with self._lock(receipt_id):
            receipt = load_json(self._path(receipt_id))
            publication = receipt['publication']
            target = publication.get('save_target')
            if target:
                owner = self.resolve_owner(target['identity']['document_id'])
                with owner._lock(target['identity']['document_id']):
                    outcome = self._outcome(target, target['attempts'][-1])
                target['attempts'][-1].update(outcome)
                target['state'] = outcome['state']
                if outcome['state'] == 'SAVED':
                    publication.update(state='PUBLISHED', plan_reference=outcome['saved_reference'],
                        material_reference=deepcopy(publication['attempts'][-1]['material_reference']))
                else:
                    publication['state'] = 'UNKNOWN'
            elif publication.get('update_command_id'):
                attempt = publication['attempts'][-1]
                identity = attempt['expected_plan']
                owner = self.resolve_owner(identity['document_id'])
                path = owner._folder(identity['document_id']) / 'commands' / (publication['update_command_id'] + '.json')
                from .related_save_edits import recover_mutation
                with owner._lock(identity['document_id']):
                    recover_mutation(owner, identity['document_id'], publication['update_command_id'])
                    prior = load_json(path) if path.exists() else {}
                response = prior.get('response')
                expected_hash = canonical_hash({'document_id': identity['document_id'], 'operation': owner.update_operation,
                    'arguments': {'draft': publication['proposed_draft']}, 'session_id': identity['session_id'],
                    'expected_generation': identity['generation']})
                if response and prior.get('request_hash') == expected_hash:
                    publication.update(state='LINK_SAVE_FAILED', linked_identity=input_identity(response['document']))
                else:
                    publication['state'] = 'UNKNOWN'
            self._summary(receipt)
            self._write(receipt)
            return deepcopy(receipt)
