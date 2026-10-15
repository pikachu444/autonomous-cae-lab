"""Raw editor capsules beside existing owner working.json, never saved revisions.

This is an artifact helper for Material/Data/Plan owners, not a draft owner or a
transaction engine. No capsule text is parsed, applied or submitted to a solver.
The caller must compare the returned close guard with its live editor immediately
before closing (or use close_permitted with a fresh raw snapshot).
"""
from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
import uuid

from .related_save import input_identity
from .storage import canonical_hash, check_id, load_json, save_json, utc_now

FORMAT = 'caelab.raw-editor-capsule/1'
PREVIEW = 'caelab.keep-recovery-preview/1'
KINDS = {'material', 'data', 'numerical'}
MAX_RAW_BYTES = 512 * 1024


def _json_copy(value):
    # Round-trip also rejects Qt objects, non-string keys, NaN and non-JSON types.
    if not isinstance(value, dict):
        raise ValueError('Raw editor state must be a JSON object')
    encoded = json.dumps(value, ensure_ascii=False, allow_nan=False)
    if len(encoded.encode('utf-8')) > MAX_RAW_BYTES:
        raise ValueError('Raw editor state exceeds the 512 KiB capsule limit')
    restored = json.loads(encoded)
    if restored != value:
        raise ValueError('Raw editor state must use JSON string keys and JSON arrays')
    return restored


def _at(value, path):
    try:
        for key in path:
            if isinstance(value, list) and type(key) is int and 0 <= key < len(value):
                value = value[key]
            elif isinstance(value, dict) and isinstance(key, str) and key in value:
                value = value[key]
            else:
                return False, None
        return True, value
    except (KeyError, IndexError, TypeError):
        return False, None


def validate_raw(raw, draft):
    """Validate the envelope, not the unfinished text or domain enum/number."""
    raw = _json_copy(raw)
    allowed = {'cells', 'focus', 'selection', 'paste', 'local_draft', 'editor_revision'}
    if set(raw) - allowed or not {'cells', 'editor_revision'} <= set(raw):
        raise ValueError('Raw state needs cells and an explicit editor_revision')
    if not isinstance(raw['editor_revision'], str) or not raw['editor_revision']:
        raise ValueError('editor_revision must be the live editor snapshot token')
    cells = raw['cells']
    if not isinstance(cells, list) or len(cells) > 4096:
        raise ValueError('Choose at most 4096 raw cells')
    seen = set()
    for cell in cells:
        if (not isinstance(cell, dict) or not {'field_path', 'raw_text', 'original_value', 'position'} <= set(cell)
                or set(cell) - {'field_path', 'raw_text', 'original_value', 'original_exists', 'position', 'editor_kind'}):
            raise ValueError('Each raw cell requires field_path, raw_text, original_value and position')
        path = cell['field_path']
        if (not isinstance(path, list) or not path or len(path) > 32
                or any(not isinstance(k, str) and not (type(k) is int and k >= 0) for k in path)):
            raise ValueError('field_path is an explicit JSON path inside this owner draft')
        key = canonical_hash(path)
        if key in seen:
            raise ValueError('Duplicate raw cell field_path')
        seen.add(key)
        if not isinstance(cell['raw_text'], str) or not isinstance(cell['position'], dict):
            raise ValueError('Preserve raw text and a JSON cell position')
        exists, original = _at(draft, path)
        declared_exists = cell.get('original_exists', True)
        if type(declared_exists) is not bool or exists != declared_exists or (exists and original != cell['original_value']):
            raise ValueError('Raw cell original value differs from the acknowledged owner draft')
    if 'local_draft' in raw and not isinstance(raw['local_draft'], dict):
        raise ValueError('A pending local_draft must remain a separate JSON object')
    return raw


class RawRecoveryDrafts:
    """Persist/retrieve raw capsules using each existing owner's lock and store."""
    def __init__(self, root, resolve_owner):
        self.root = Path(root).resolve()
        self.resolve_owner = resolve_owner
        # No competing store registry. A copied/moved workspace has a different
        # identity and cannot implicitly resume the old location's raw capsule.
        self.store_id = 'Store' + canonical_hash(os.path.normcase(str(self.root)))[:40]

    def identity(self, document):
        return {**input_identity(document), 'store_id': self.store_id}

    def _owner(self, identifier):
        owner = self.resolve_owner(check_id(identifier))
        if owner.kind not in KINDS or Path(owner.root).resolve() != self.root / 'documents':
            raise ValueError('Recovery requires a Material/Data/Plan owner in this exact store')
        return owner

    def _check_identity(self, identity):
        keys = {'document_id', 'kind', 'session_id', 'generation', 'input_revision',
                'input_sha256', 'saved_revision', 'store_id'}
        if not isinstance(identity, dict) or set(identity) != keys or identity['store_id'] != self.store_id:
            raise ValueError('Use the complete recovery identity from this store')
        if identity['kind'] not in KINDS or type(identity['generation']) is not int or identity['generation'] < 0:
            raise ValueError('Recovery identity needs an existing owner and exact generation')
        for key in ('document_id', 'session_id', 'input_revision'):
            check_id(identity[key])
        return identity

    def owner_identity(self, document_id):
        owner = self._owner(document_id)
        with owner._lock(document_id):
            return self.identity(owner.read(document_id))

    def _path(self, owner, identifier, capsule_id):
        return owner._folder(identifier) / 'raw-recovery' / (check_id(capsule_id) + '.json')

    def _working_matches(self, owner, document):
        try:
            state = owner.acknowledged_state(document['id'])
            return self.identity(state['document']) == self.identity(document)
        except (OSError, ValueError, KeyError):
            return False

    @staticmethod
    def _content(owner, document):
        # The owner supplies the durable internal representation, not stripped
        # presentation fields from owner.read(). All subclass fields participate.
        return owner._fingerprint(owner.acknowledged_state(document['id'])['document'])

    def _assets_path(self, owner, identifier, capsule_id):
        return self._path(owner, identifier, capsule_id).with_suffix('.assets')

    def prepare(self, requests, *, review_id=None):
        """Read/review only; requests carry raw snapshots for ALL dirty owners."""
        if not isinstance(requests, list) or not 1 <= len(requests) <= 16:
            raise ValueError('Review 1 to 16 distinct dirty owners')
        review_id = check_id(review_id or 'R' + uuid.uuid4().hex)
        targets, seen = [], set()
        for request in requests:
            if not isinstance(request, dict) or set(request) != {'identity', 'raw'}:
                raise ValueError('Each recovery request needs identity and raw')
            identity = deepcopy(self._check_identity(request['identity']))
            identifier = identity['document_id']
            if identifier in seen:
                raise ValueError('Review an owner only once')
            seen.add(identifier)
            owner = self._owner(identifier)
            with owner._lock(identifier):
                current = owner.read(identifier)
                # Even a stale preview preserves its exact text, but never grants
                # a close permission or validates it against a different draft.
                raw = _json_copy(request['raw'])
                problems = []
                acknowledged = None
                if self.identity(current) != identity or not self._working_matches(owner, current):
                    problems.append('OWNER_IDENTITY_OR_DURABLE_ACK_CONFLICT')
                else:
                    raw = validate_raw(raw, current['draft'])
                    try:
                        from .related_save_recovery_assets import capture, review_summary
                        acknowledged = review_summary(capture(owner, identifier, self.root, self.resolve_owner))
                    except (OSError, ValueError, KeyError) as error:
                        problems.append('ACKNOWLEDGED_EVIDENCE_UNAVAILABLE: ' + str(error))
                targets.append({'identity': identity, 'raw': raw,
                    'raw_sha256': canonical_hash(raw),
                    'content_sha256': acknowledged['content_sha256'] if acknowledged else None,
                    'acknowledged': acknowledged,
                    'capsule_id': 'Q' + canonical_hash([review_id, identity, raw])[:40],
                    'problems': problems})
        payload = {'format': PREVIEW, 'review_id': review_id, 'targets': targets,
                   'related_owners': [deepcopy(t['identity']) for t in targets]}
        return {**payload, 'preview_sha256': canonical_hash(payload), 'published': False}

    def _preview(self, preview):
        value = {k: deepcopy(preview[k]) for k in ('format', 'review_id', 'targets', 'related_owners')}
        if value['format'] != PREVIEW or canonical_hash(value) != preview.get('preview_sha256'):
            raise ValueError('Recovery review changed; preserve the editor and review again')
        check_id(value['review_id'])
        targets = value['targets']
        if not isinstance(targets, list) or not 1 <= len(targets) <= 16:
            raise ValueError('Recovery review must retain 1 to 16 actual owner targets')
        identities = []
        for target in targets:
            if set(target) != {'identity', 'raw', 'raw_sha256', 'content_sha256', 'acknowledged', 'capsule_id', 'problems'}:
                raise ValueError('Recovery target metadata changed')
            identity = self._check_identity(target['identity']); identities.append(identity)
            raw = _json_copy(target['raw'])
            if (canonical_hash(raw) != target['raw_sha256'] or target['capsule_id'] !=
                    'Q' + canonical_hash([value['review_id'], identity, raw])[:40]):
                raise ValueError('Recovery raw snapshot or capsule identity changed')
        if len({i['document_id'] for i in identities}) != len(identities) or identities != value['related_owners']:
            raise ValueError('Recovery review owner relationships changed')
        return value

    def _capsule(self, owner, identifier, capsule_id):
        path = self._path(owner, identifier, capsule_id)
        record = load_json(path)
        body = {k: v for k, v in record.items() if k != 'capsule_sha256'}
        if (record.get('format') != FORMAT or record.get('capsule_id') != capsule_id
                or record.get('capsule_sha256') != canonical_hash(body)
                or record['identity']['document_id'] != identifier
                or record['identity']['kind'] != owner.kind
                or canonical_hash(record['raw']) != record['raw_sha256']):
            raise ValueError('Recovery capsule identity/content verification failed')
        if 'document' in record['acknowledged']:
            from .related_save_recovery_assets import verify_snapshot, verify_assets
            verify_snapshot(owner, record['identity'], record['acknowledged'])
            verify_assets(self._assets_path(owner, identifier, capsule_id), record['acknowledged'])
            validate_raw(record['raw'], record['acknowledged']['document']['draft'])
        # C1 capsules remain inspectable as LEGACY_BASE_NOT_RETAINED. A current
        # working file must never be presented as their missing historical base.
        # Read of a portable copy is allowed for inspection, never auto-resume.
        discarded = path.with_suffix('.discard.json')
        status = 'STORED'
        if discarded.exists():
            marker = load_json(discarded)
            if marker.get('capsule_sha256') != record['capsule_sha256']:
                raise ValueError('Recovery discard marker does not match the capsule')
            status = 'DISCARDED'
        return record, status

    def execute(self, preview):
        """Explicit Keep recovery drafts; each owner has an independent outcome."""
        reviewed = self._preview(preview)
        results = []
        for target in reviewed['targets']:
            identity = target['identity']; identifier = identity['document_id']
            result = {'document_id': identifier, 'capsule_id': target['capsule_id'],
                      'identity': deepcopy(identity), 'raw_sha256': target['raw_sha256'],
                      'close_permitted': False, 'state': 'FAILED'}
            try:
                owner = self._owner(identifier)
                with owner._lock(identifier):
                    current = owner.read(identifier)
                    if (target['problems'] or self.identity(current) != identity
                            or self._content(owner, current) != target['content_sha256']
                            or not self._working_matches(owner, current)):
                        result.update(state='CONFLICT', reason='OWNER_CHANGED_AFTER_REVIEW')
                    else:
                        path = self._path(owner, identifier, target['capsule_id'])
                        if path.exists():
                            capsule, status = self._capsule(owner, identifier, target['capsule_id'])
                            if capsule['preview_sha256'] != preview['preview_sha256'] or capsule['raw_sha256'] != target['raw_sha256']:
                                raise ValueError('Capsule ID already records a different review')
                            result.update(state=status, capsule_sha256=capsule['capsule_sha256'])
                        else:
                            raw = validate_raw(target['raw'], current['draft'])
                            # Reuse acknowledged owner persistence. Do not call
                            # update/save, change generation, or parse raw text.
                            owner._persist_draft(deepcopy(owner._documents[identifier]))
                            working = owner.acknowledged_state(identifier)['document']
                            reviewed_ack = target['acknowledged']
                            if (self.identity(working) != identity or reviewed_ack is None
                                    or canonical_hash(working) != reviewed_ack['document_sha256']):
                                raise ValueError('Acknowledged working draft did not persist exactly')
                            from .related_save_recovery_assets import capture, review_summary, verify_snapshot, preserve
                            acknowledged = capture(owner, identifier, self.root, self.resolve_owner)
                            if (review_summary(acknowledged) != reviewed_ack if reviewed_ack.get('review_only')
                                    else acknowledged != reviewed_ack):
                                raise ValueError('Reviewed base/command/result evidence changed; preserve raw and review again')
                            verify_snapshot(owner, identity, acknowledged)
                            preserve(self.root, self._assets_path(owner, identifier, target['capsule_id']), acknowledged)
                            capsule = {'format': FORMAT, 'capsule_id': target['capsule_id'],
                                'review_id': reviewed['review_id'], 'preview_sha256': preview['preview_sha256'],
                                'identity': deepcopy(identity), 'related_owners': deepcopy(reviewed['related_owners']),
                                'raw': raw, 'raw_sha256': target['raw_sha256'],
                                'acknowledged': deepcopy(acknowledged),
                                'saved_revision_created': False, 'created_utc': utc_now()}
                            capsule['capsule_sha256'] = canonical_hash(capsule)
                            save_json(path, capsule)
                            actual, status = self._capsule(owner, identifier, target['capsule_id'])
                            if actual != capsule:
                                raise ValueError('Recovery write read-back differs from prepared capsule')
                            result.update(state=status, capsule_sha256=capsule['capsule_sha256'])
                        result['close_permitted'] = result['state'] == 'STORED'
                        result['close_guard'] = {'identity': deepcopy(identity),
                            'raw_sha256': target['raw_sha256'], 'editor_revision': target['raw']['editor_revision']}
            except Exception as error:
                # A lost response after publication is reconciled by read or a
                # repeated explicit execute. An exception never closes a window.
                result.update(state='FAILED', close_permitted=False,
                              error={'type': type(error).__name__, 'message': str(error)})
            results.append(result)
        # Recheck earlier owners after all independent writes. The GUI must
        # still compare its own live raw snapshot after receiving this result.
        gate = self.close_permitted(preview, [{'identity': t['identity'], 'raw': t['raw']} for t in reviewed['targets']])
        for result, current_gate in zip(results, gate['targets']):
            result['close_permitted'] = result['close_permitted'] and current_gate['close_permitted']
            result['close_reasons'] = current_gate['reasons']
        return {'review_id': reviewed['review_id'], 'targets': results,
                'requires_live_editor_comparison': True,
                'close_permitted': all(r['close_permitted'] for r in results),
                'all_kept': all(r['state'] == 'STORED' for r in results),
                'live_buffers_must_be_preserved': [r['document_id'] for r in results if not r['close_permitted']]}

    def read(self, document_id, capsule_id=None):
        owner = self._owner(document_id)
        with owner._lock(document_id):
            ids = ([check_id(capsule_id)] if capsule_id else
                   [p.stem for p in (owner._folder(document_id) / 'raw-recovery').glob('Q*.json')
                    if not p.name.endswith('.discard.json')])
            records = []
            for cid in sorted(ids):
                capsule, status = self._capsule(owner, document_id, cid)
                records.append({'state': status, 'capsule': capsule,
                    'same_store': capsule['identity']['store_id'] == self.store_id,
                    'automatically_applied': False})
            return {'document_id': document_id, 'capsules': records}

    def inspect(self, document_id, capsule_id):
        owner = self._owner(document_id)
        with owner._lock(document_id):
            capsule, status = self._capsule(owner, document_id, capsule_id)
            complete = 'document' in capsule['acknowledged']
            source_retention = {}
            if complete and capsule['identity']['kind'] == 'data':
                from .data_recovery_inputs import verify_inputs
                source_retention['source_retention'] = verify_inputs(
                    self._assets_path(owner, document_id, capsule_id), capsule['acknowledged'])
            return {'state': status, 'verification': 'VERIFIED' if complete else 'LEGACY_BASE_NOT_RETAINED',
                **source_retention,
                'capsule_sha256': capsule['capsule_sha256'], 'identity': deepcopy(capsule['identity']),
                'raw': deepcopy(capsule['raw']),
                'pending_local_draft': deepcopy(capsule['raw'].get('local_draft')),
                'acknowledged': deepcopy(capsule['acknowledged']),
                'same_store': capsule['identity']['store_id'] == self.store_id,
                'owner_mutated': False, 'resume_permission': 'NOT_REQUESTED'}

    def source_preview(self, document_id, capsule_id, data_id):
        """Bounded original Data bytes through existing owner/asset verification."""
        owner = self._owner(document_id)
        with owner._lock(document_id):
            capsule, _ = self._capsule(owner, document_id, capsule_id)
            from .data_recovery_inputs import preview_source
            return preview_source(self._path(owner, document_id, capsule_id), data_id,
                expected_capsule_sha256=capsule['capsule_sha256'])

    def portable_payload(self, document_id, capsule_id):
        """Existing portable writer copies listed bytes; never calls save/apply.

        The caller rechecks these hashes while exporting. A new store can inspect
        this bundle, but existing store/session/content guards still block resume.
        """
        owner = self._owner(document_id)
        with owner._lock(document_id):
            result = self.inspect(document_id, capsule_id)
            path = self._path(owner, document_id, capsule_id)
            from .evaluation import file_hash
            files = [{'path': path.relative_to(self.root).as_posix(), 'sha256': file_hash(path)}]
            marker = path.with_suffix('.discard.json')
            if marker.exists():
                files.append({'path': marker.relative_to(self.root).as_posix(), 'sha256': file_hash(marker)})
            for item in result['acknowledged'].get('artifacts', []):
                asset = self._assets_path(owner, document_id, capsule_id) / item['path']
                files.append({**item, 'path': asset.relative_to(self.root).as_posix()})
            return {**result, 'files': files, 'saved_revision_created': False,
                    'implicit_apply': False, 'acknowledged_base_is_saved_revision': False}

    def recover(self, document_id, capsule_id, *, identity, acknowledge_session_change=False):
        """Explicit resume returns raw state to the GUI; NEVER applies a draft.

        A cold process may resume only after explicitly acknowledging the session
        change AND matching every original base field, including generation.
        """
        self._check_identity(identity)
        if identity['document_id'] != document_id:
            raise ValueError('Resume target is a different owner')
        owner = self._owner(document_id)
        with owner._lock(document_id):
            current = owner.read(document_id)
            capsule, status = self._capsule(owner, document_id, capsule_id)
            original = capsule['identity']
            reasons = []
            if status != 'STORED': reasons.append('CAPSULE_DISCARDED')
            if not self._working_matches(owner, current): reasons.append('UNRESOLVED_DURABLE_OWNER_ACK')
            if self.identity(current) != identity: reasons.append('CURRENT_OWNER_CAS_CONFLICT')
            if any(original.get(k) != identity.get(k) for k in original if k != 'session_id'):
                reasons.append('STALE_OR_DIFFERENT_BASE')
            if original['session_id'] != identity['session_id'] and acknowledge_session_change is not True:
                reasons.append('EXPLICIT_SESSION_ACK_REQUIRED')
            if self._working_matches(owner, current):
                if self._content(owner, current) != capsule['acknowledged']['content_sha256']:
                    reasons.append('ACKNOWLEDGED_CONTENT_CHANGED')
            if 'document' not in capsule['acknowledged']:
                reasons.append('LEGACY_BASE_NOT_RETAINED')
            return {'state': 'BLOCKED' if reasons else 'RESUME_READY', 'reasons': reasons,
                'raw': None if reasons else deepcopy(capsule['raw']),
                'capsule_sha256': capsule['capsule_sha256'], 'identity': deepcopy(identity),
                'original_identity': deepcopy(original), 'owner_mutated': False,
                'acknowledged': deepcopy(capsule['acknowledged']),
                'pending_local_draft': deepcopy(capsule['raw'].get('local_draft')),
                'saved_revision_created': False, 'capsule_retained': True}

    def discard(self, document_id, capsule_id, *, identity, capsule_sha256):
        self._check_identity(identity)
        if identity['document_id'] != document_id:
            raise ValueError('Discard target is a different owner')
        owner = self._owner(document_id)
        with owner._lock(document_id):
            current = owner.read(document_id)
            if self.identity(current) != identity or not self._working_matches(owner, current):
                raise ValueError('Owner changed or durable mutation is unresolved before explicit discard')
            capsule, status = self._capsule(owner, document_id, capsule_id)
            if capsule['identity']['store_id'] != self.store_id or capsule['capsule_sha256'] != capsule_sha256:
                raise ValueError('Discard requires the inspected capsule in its original store')
            if status != 'DISCARDED':
                save_json(self._path(owner, document_id, capsule_id).with_suffix('.discard.json'),
                    {'capsule_sha256': capsule_sha256, 'identity': deepcopy(identity), 'discarded_utc': utc_now()})
            return {'state': 'DISCARDED', 'document_id': document_id, 'owner_mutated': False}

    def close_permitted(self, preview, live_requests):
        """Fresh GUI snapshots + current owner CAS + durable per-owner evidence."""
        reviewed = self._preview(preview)
        if not isinstance(live_requests, list):
            raise ValueError('Provide the actual live editor snapshots')
        live = {r['identity']['document_id']: r for r in live_requests}
        if len(live) != len(live_requests) or set(live) != {t['identity']['document_id'] for t in reviewed['targets']}:
            raise ValueError('Close gate must include exactly the reviewed dirty owners')
        targets = []
        for t in reviewed['targets']:
            identifier = t['identity']['document_id']; reasons = []
            try:
                owner = self._owner(identifier)
                with owner._lock(identifier):
                    if (live[identifier]['identity'] != t['identity']
                            or canonical_hash(live[identifier]['raw']) != t['raw_sha256']):
                        reasons.append('LIVE_EDITOR_CHANGED')
                    current = owner.read(identifier)
                    if (self.identity(current) != t['identity'] or self._content(owner, current) != t['content_sha256']
                            or not self._working_matches(owner, current)):
                        reasons.append('OWNER_CHANGED')
                    capsule, status = self._capsule(owner, identifier, t['capsule_id'])
                    if capsule['identity']['kind'] == 'data' and 'data_inputs' not in capsule['acknowledged']:
                        reasons.append('DATA_INPUT_CLOSURE_NOT_RETAINED')
                    if any(item['state'] == 'UNRESOLVED_UNSUBMITTED'
                           for item in capsule['acknowledged'].get('data_inputs', [])):
                        reasons.append('DECLARED_DATA_SOURCE_BYTES_UNAVAILABLE')
                    if status != 'STORED' or capsule['preview_sha256'] != preview['preview_sha256']:
                        reasons.append('RECOVERY_NOT_CONFIRMED')
            except Exception as error:
                reasons.append(type(error).__name__ + ': ' + str(error))
            targets.append({'document_id': identifier, 'close_permitted': not reasons, 'reasons': reasons})
        return {'targets': targets, 'close_permitted': all(t['close_permitted'] for t in targets)}
