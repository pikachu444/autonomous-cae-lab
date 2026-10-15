"""Explicit original-archive -> CURRENT owner buffer transport.

The only domain write is the existing owner.update of the acknowledged base,
when explicitly approved. Raw/local_draft are returned to the existing editor,
not applied or evaluated. Current Keep/save/close commands retain their gates.
"""
from __future__ import annotations
from copy import deepcopy
import re

from .portable_project_recovery import projected_buffer
from .related_save_recovery import RawRecoveryDrafts
from .storage import canonical_hash, check_id

FORMAT = 'caelab.portable-buffer-review/1'


def _buffer(token):
    if (not isinstance(token, dict) or set(token) != {'editor_revision', 'raw_sha256'}
            or not isinstance(token['editor_revision'], str) or not token['editor_revision']
            or not re.fullmatch('[0-9a-f]{64}', str(token['raw_sha256']))):
        raise ValueError('Use the exact noncommitting current editor buffer token')
    return deepcopy(token)


def buffer_token(raw):
    from .related_save_recovery import _json_copy
    raw = _json_copy(raw)
    return _buffer({'editor_revision': raw['editor_revision'], 'raw_sha256': canonical_hash(raw)})


def preview_resume(workbench, archive_id, *, target_identity, buffer):
    recovery = RawRecoveryDrafts(workbench.root, workbench._document_owner)
    recovery._check_identity(target_identity)
    row, inspected, draft, raw = projected_buffer(workbench.workspace, archive_id)
    if row['document_id'] != target_identity['document_id']:
        raise ValueError('Choose this archive CURRENT editing owner, not its original owner or a peer Plan')
    owner = recovery._owner(row['document_id'])
    with owner._lock(row['document_id']):
        current = owner.read(row['document_id'])
        if recovery.identity(current) != target_identity:
            raise ValueError('Current owner CAS changed before buffer review')
        state = owner.acknowledged_state(current['id'])
        owner._draft(draft)  # Reuse actual owner size/JSON validation; no physics apply.
        result = {'format': FORMAT, 'archive_id': archive_id,
            'capsule_sha256': row['capsule_sha256'], 'capsule_file_sha256': row['capsule_file_sha256'],
            'original_identity': deepcopy(row['original_identity']), 'target_identity': deepcopy(target_identity),
            'target_document_sha256': canonical_hash(state['document']), 'buffer': _buffer(buffer),
            'base_draft_sha256': canonical_hash(draft), 'projected_raw_sha256': canonical_hash(raw),
            'base_change_required': canonical_hash(current['draft']) != canonical_hash(draft),
            'receipt_interpretation': 'AS_RECORDED', 'original_recover_permission': 'NOT_GRANTED',
            'original_discard_permission': 'NOT_GRANTED', 'raw_applied': False,
            'saved_revision_created': False, 'job_submitted': False}
        result['preview_sha256'] = canonical_hash(result)
        # Bound to this exact review. A different archive/raw/target cannot reuse
        # this ID even if its acknowledged draft happened to contain equal values.
        result['command_id'] = 'C' + canonical_hash(['portable-buffer-resume', result['preview_sha256']])[:40]
        return result


def validate_review(preview, *, approved, overwrite_approved, live_buffer, command_id):
    """Same review/command/buffer gate for transport and Data owner retention."""
    if approved is not True or overwrite_approved is not True:
        raise ValueError('Explicitly approve this current owner base and current editor buffer replacement')
    if not isinstance(preview, dict):
        raise ValueError('Use the original buffer review')
    body = {k: deepcopy(v) for k, v in preview.items() if k not in {'preview_sha256', 'command_id'}}
    digest = canonical_hash(body)
    expected_command = 'C' + canonical_hash(['portable-buffer-resume', digest])[:40]
    if (preview.get('format') != FORMAT or preview.get('preview_sha256') != digest
            or preview.get('command_id') != expected_command or check_id(command_id) != expected_command):
        raise ValueError('Buffer review or its exact same-command retry identity changed')
    if _buffer(live_buffer) != preview['buffer']:
        raise ValueError('Current editor changed during review; preserve it and review again')


def resume(workbench, preview, *, approved, overwrite_approved, live_buffer, command_id):
    validate_review(preview, approved=approved, overwrite_approved=overwrite_approved,
                    live_buffer=live_buffer, command_id=command_id)
    recovery = RawRecoveryDrafts(workbench.root, workbench._document_owner)
    identity = recovery._check_identity(preview['target_identity'])
    row, inspected, draft, raw = projected_buffer(workbench.workspace, preview['archive_id'])
    if (row['document_id'] != identity['document_id'] or row['original_identity'] != preview['original_identity']
            or row['capsule_sha256'] != preview['capsule_sha256']
            or row['capsule_file_sha256'] != preview['capsule_file_sha256']
            or canonical_hash(draft) != preview['base_draft_sha256']
            or canonical_hash(raw) != preview['projected_raw_sha256']):
        raise ValueError('Original archive or its explicit editing projection changed')
    owner = recovery._owner(row['document_id'])
    if identity['session_id'] != owner.session_id:
        raise ValueError('Current store session changed; old resume commands grant no authority')
    with owner._lock(row['document_id']):
        current = owner.read(row['document_id'])
        prior = owner._folder(current['id']) / 'commands' / (command_id + '.json')
        # A lost response can ONLY replay this exact existing owner command.
        # Do not create a different command or silently accept another generation.
        if not prior.exists():
            state = owner.acknowledged_state(current['id'])
            if (recovery.identity(current) != identity
                    or canonical_hash(state['document']) != preview['target_document_sha256']):
                raise ValueError('Current owner changed after review; no acknowledged base or raw was replaced')
        # With an existing command, let the owner recover its exact published
        # mutation marker first (durable write may precede memory/receipt loss).
        # The full post-state is still mandatory below; no new command is made.
        arguments = {'draft': draft}
        if owner.kind == 'data':
            arguments['portable_recovery_inputs'] = {'preview': deepcopy(preview),
                'approved': approved, 'overwrite_approved': overwrite_approved,
                'live_buffer': deepcopy(live_buffer)}
        response = owner.command(current['id'], owner.update_operation, arguments,
            session_id=identity['session_id'], expected_generation=identity['generation'], command_id=command_id)
        now = owner.read(current['id'])
        state = owner.acknowledged_state(current['id'])
        # This is the existing owner's durable command receipt, including its
        # whole post-state digest. A legitimate lost reply has exactly that
        # state. Same input with a new run/comparison/history is NOT a replay.
        if (response.get('acknowledged_document_sha256') != canonical_hash(state['document'])
                or canonical_hash(now) != canonical_hash(response['document'])):
            raise ValueError('Owner changed or lacks whole-state proof after the recorded resume command; '
                             'do not replace the newer editor')
        if owner.kind == 'data':
            from .portable_recovery_data_inputs import verify_current
            verify_current(owner, state['document'], row['archive_id'])
        return {'state': 'BUFFER_READY', 'document': response['document'], 'raw': raw,
            'target_identity': recovery.identity(now), 'archive_id': row['archive_id'],
            'original_identity': deepcopy(row['original_identity']), 'capsule_sha256': row['capsule_sha256'],
            'current_command_id': command_id, 'receipt_interpretation': 'AS_RECORDED',
            'original_recover_permission': 'NOT_GRANTED', 'original_discard_permission': 'NOT_GRANTED',
            'raw_applied': False, 'saved_revision_created': False, 'job_submitted': False,
            'current_keep_required_for_raw_close': True}
