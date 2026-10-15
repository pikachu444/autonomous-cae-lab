"""Immutable Keep-recovery evidence beside existing owners, not a saved revision.

The existing owner decides what is acknowledged. This helper snapshots those
bytes and the exact referenced immutable files; it never repairs commands,
submits jobs, changes a draft, or calls document.save. Mutable receipts are
recorded AS_RECORDED at review time, not reconciled while inspecting history.
"""
from __future__ import annotations
from copy import deepcopy
import os
from pathlib import Path
import shutil
import tempfile

from .evaluation import file_hash, read_result
from .storage import canonical_hash, check_id, load_json


def _read_snapshot(path):
    path = Path(path)
    before = file_hash(path)
    value = load_json(path)
    if file_hash(path) != before:
        raise ValueError('Recovery evidence changed during review: ' + str(path))
    return {'sha256': before, 'value_sha256': canonical_hash(value), 'snapshot': value}


def capture(owner, identifier, root, resolve_owner):
    """Caller holds owner lock. All public projections are outside this boundary."""
    state = owner.acknowledged_state(identifier)
    document = state['document']
    root = Path(root).resolve()
    files, revisions = {}, {}

    def add_file(path):
        path = Path(path)
        resolved = path.resolve()
        if path.is_symlink() or not resolved.is_relative_to(root) or not path.is_file():
            raise ValueError('Recovery artifact is missing or outside its acknowledged store')
        relative = resolved.relative_to(root).as_posix()
        item = {'path': relative, 'sha256': file_hash(path), 'size_bytes': path.stat().st_size}
        if relative in files and files[relative] != item:
            raise ValueError('Referenced immutable recovery file changed during review')
        files[relative] = item

    def add_tree(folder):
        folder = Path(folder)
        if not folder.is_dir():
            raise ValueError('Referenced recovery artifact directory is missing')
        for path in sorted(folder.rglob('*')):
            if path.is_symlink():
                raise ValueError('Symlinks are not immutable recovery artifacts')
            if path.is_file():
                add_file(path)

    def revision(document_id, revision_id, reference=None):
        key = (check_id(document_id), check_id(revision_id))
        peer = resolve_owner(document_id)
        saved = peer._verify_revision(*key)
        folder = peer._folder(document_id) / 'revisions' / revision_id
        if saved.get('id') != document_id or saved.get('saved_revision') != revision_id:
            raise ValueError('Recovery reference points to another saved document')
        if reference is not None:
            for name, value in [('input_revision', saved['input_revision']),
                                ('input_sha256', canonical_hash(saved['draft']))]:
                if name in reference and reference[name] != value:
                    raise ValueError('Recovery saved reference ' + name + ' differs')
        if key not in revisions:
            add_tree(folder)
            revisions[key] = {'document_id': document_id, 'saved_revision': revision_id,
                'kind': saved['kind'], 'input_revision': saved['input_revision'],
                'input_sha256': canonical_hash(saved['draft']),
                'document_sha256': canonical_hash(saved),
                'revision_manifest_sha256': file_hash(folder / 'revision.json')}
        return saved

    if document.get('saved_revision'):
        revision(identifier, document['saved_revision'])

    def references(value):
        if isinstance(value, dict):
            did = value.get('document_id') or value.get('pde_document_id')
            if did and value.get('saved_revision'):
                revision(did, value['saved_revision'], value)
            for child in value.values():
                references(child)
        elif isinstance(value, list):
            for child in value:
                references(child)
    # References inside the current input and retained records are immutable
    # dependencies. A pending command's proposed input is a different, unapplied
    # buffer and is preserved below without pretending it was admitted.
    references(document['draft'])
    for key in ('adoptions', 'candidate_evidence'):
        references(document.get(key, []))

    # Unsaved Data inputs have no saved revision yet. Retain only exact
    # acknowledged current/Undo/Redo/run inputs and calibration dependencies.
    data_inputs = None
    if document['kind'] == 'data':
        from .data_recovery_inputs import capture_inputs
        data_inputs = capture_inputs(owner, document, root, add_file, revision)

    jobs = []
    for run in document.get('runs', []):
        jid = check_id(run['job_id'])
        retained = run.get('retained_record') or run.get('retained_result')
        if retained and run.get('retention_complete'):
            revision(identifier, retained['revision'])
            base = owner._folder(identifier) / 'revisions' / retained['revision']
            job = load_json(base / 'jobs' / (jid + '.json'))
            result_folder = base / 'results' / jid
        else:
            job = owner.manager.status(jid)
            result_folder = owner.manager.root / 'results' / jid
        expected = run.get('arguments')
        if expected is None:
            expected = {'backend': run['backend'], 'settings': run['settings']}
        if job.get('id') != jid or job['arguments'] != expected or job['operation'] != run.get('operation', 'evaluate'):
            raise ValueError('Recovery run and actual job inputs differ')
        item = {'job_id': jid, 'record_sha256': canonical_hash(run),
                'job': deepcopy(job), 'job_sha256': canonical_hash(job),
                'state_at_review': job['state'], 'result_at_review': 'NOT_PUBLISHED'}
        if job.get('result_refs'):
            metadata = read_result(result_folder, verify='all', selection={'metadata_only': True})
            if data_inputs is not None:
                from .data_recovery_inputs import verify_import_sources
                verify_import_sources(run, metadata, data_inputs)
            add_tree(result_folder)
            item.update(result_at_review='PUBLISHED', result_path=result_folder.resolve().relative_to(root).as_posix(),
                        result_sha256=file_hash(result_folder / 'result.json'))
        jobs.append(item)

    for record in document.get('processing_revisions', []):
        from .data_processing_document import _result_folder
        folder = _result_folder(owner, document, record)
        read_result(folder, verify='all', selection={'metadata_only': True})
        add_tree(folder)
    for record in document.get('comparisons', []):
        folder = owner._comparison_folder(document, record)
        read_result(folder, verify='all', selection={'metadata_only': True})
        add_tree(folder)
    for record in document.get('candidate_evidence', []):
        base = (owner._folder(identifier) / 'revisions' / check_id(record['retained_revision'])
                if record.get('retained_revision') else owner._folder(identifier))
        path = base / 'candidate_evidence' / (check_id(record['id']) + '.json')
        if canonical_hash(load_json(path)) != record['sha256']:
            raise ValueError('Candidate evidence changed before recovery capture')
        add_file(path)

    commands = []
    for path in sorted((owner._folder(identifier) / 'commands').glob('*.json')):
        commands.append({'command_id': check_id(path.stem), **_read_snapshot(path),
            'artifact_path': path.resolve().relative_to(root).as_posix(), 'interpretation': 'AS_RECORDED'})
        add_file(path)
    related = []
    for path in sorted((root / 'documents' / 'related-saves').glob('*.json')):
        record = _read_snapshot(path)
        if any(t.get('identity', {}).get('document_id') == identifier for t in record['snapshot'].get('targets', [])):
            related.append({'receipt_id': check_id(path.stem), **record,
                'artifact_path': path.resolve().relative_to(root).as_posix(), 'interpretation': 'AS_RECORDED'})
            add_file(path)
    acknowledged = {'storage': 'immutable_capsule_and_assets', 'document': deepcopy(document),
        'document_sha256': canonical_hash(document), 'content_sha256': owner._fingerprint(document),
        'input_revision': document['input_revision'], 'input_sha256': canonical_hash(document['draft']),
        'mutation_command': deepcopy(document.get('_mutation_command')),
        'save_command': deepcopy(document.get('_save_command')), 'durability': deepcopy(state['durability']),
        'saved_reference': next((r for k, r in revisions.items() if k == (identifier, document.get('saved_revision'))), None),
        'saved_sources': list(revisions.values()), 'jobs': jobs,
        'owner_commands': commands, 'related_save_receipts': related,
        'artifacts': sorted(files.values(), key=lambda r: r['path'])}
    if data_inputs is not None:
        acknowledged['data_inputs'] = data_inputs
    acknowledged['acknowledged_sha256'] = canonical_hash(acknowledged)
    return acknowledged



def review_summary(acknowledged):
    """Small read-only GUI review, bound to the complete captured evidence.

    Execute recaptures and compares this FULL evidence hash under the owner lock
    before any capsule is written. Changed receipts/jobs require explicit review;
    they are not quietly updated. No server-side preview registry is needed.
    """
    a = acknowledged
    return {**{k: deepcopy(a[k]) for k in ('acknowledged_sha256', 'document_sha256',
        'content_sha256', 'input_revision', 'input_sha256', 'saved_reference')},
        **({'data_inputs': [{k: deepcopy(row[k]) for k in
            ('data_id', 'state', 'sha256', 'bytes') if k in row}
            for row in a['data_inputs']]} if 'data_inputs' in a else {}),
        'review_only': True, 'artifact_count': len(a['artifacts']),
        'artifact_bytes': sum(item['size_bytes'] for item in a['artifacts']),
        'jobs': [{'job_id': j['job_id'], 'state_at_review': j['state_at_review'],
                  'result_at_review': j['result_at_review'], 'job_sha256': j['job_sha256']}
                 for j in a['jobs']],
        'owner_commands': [{'command_id': c['command_id'], 'sha256': c['sha256'],
            'state_at_review': c['snapshot'].get('state'),
            'response_at_review': 'response' in c['snapshot']} for c in a['owner_commands']],
        'related_save_receipts': [{'receipt_id': r['receipt_id'], 'sha256': r['sha256'],
            'interpretation': r['interpretation']} for r in a['related_save_receipts']]}


def verify_snapshot(owner, identity, acknowledged):
    """Validate the captured content itself; current mutable files are not its base."""
    a = acknowledged
    if canonical_hash({k: v for k, v in a.items() if k != 'acknowledged_sha256'}) != a.get('acknowledged_sha256'):
        raise ValueError('Immutable acknowledged base hash mismatch')
    d = a['document']
    from .related_save import input_identity
    if (input_identity(d) != {k: v for k, v in identity.items() if k != 'store_id'}
            or canonical_hash(d) != a['document_sha256'] or owner._fingerprint(d) != a['content_sha256']
            or canonical_hash(d['draft']) != a['input_sha256'] or d['input_revision'] != a['input_revision']):
        raise ValueError('Immutable acknowledged base is not the reviewed owner/input')
    for record in a['owner_commands'] + a['related_save_receipts']:
        if canonical_hash(record['snapshot']) != record['value_sha256'] or record['interpretation'] != 'AS_RECORDED':
            raise ValueError('Reviewed pending command/receipt snapshot changed')
    for item in a['jobs']:
        run = next((r for r in d['runs'] if r['job_id'] == item['job_id']), None)
        expected = ((run.get('arguments') or {'backend': run.get('backend'), 'settings': run.get('settings')})
                    if run is not None else None)
        if (run is None or canonical_hash(run) != item['record_sha256']
                or canonical_hash(item['job']) != item['job_sha256']
                or item['state_at_review'] != item['job']['state']
                or item['job'].get('id') != run['job_id']
                or item['job'].get('operation') != run.get('operation', 'evaluate')
                or item['job'].get('arguments') != expected
                or bool(item['job'].get('result_refs')) != (item['result_at_review'] == 'PUBLISHED')):
            raise ValueError('Reviewed job/result relationship changed')
    saved = a['saved_reference']
    if bool(saved) != bool(d.get('saved_revision')) or (saved and (
            saved['document_id'] != d['id'] or saved['saved_revision'] != d['saved_revision']
            or saved not in a['saved_sources'])):
        raise ValueError('Original acknowledged saved reference changed')
    return a


def _target(folder, item):
    relative = item['path']
    if not isinstance(relative, str) or not relative:
        raise ValueError('Invalid recovery artifact path')
    p = Path(relative)
    if '\\' in relative or p.is_absolute() or '..' in p.parts:
        raise ValueError('Invalid recovery artifact path')
    target = (Path(folder) / p).resolve()
    if not target.is_relative_to(Path(folder).resolve()):
        raise ValueError('Recovery artifact escapes its capsule')
    return target


def preserve(root, asset_folder, acknowledged):
    """Copy exact reviewed immutable bytes. Failed prefixes are never completion."""
    for item in acknowledged['artifacts']:
        source = _target(root, item); target = _target(asset_folder, item)
        if file_hash(source) != item['sha256'] or source.stat().st_size != item['size_bytes']:
            raise ValueError('Referenced artifact changed after recovery review')
        if target.exists():
            if file_hash(target) != item['sha256']:
                raise ValueError('Partial recovery artifact conflicts with reviewed bytes')
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=target.parent, prefix='.caelab-', delete=False) as stream:
            temporary = Path(stream.name)
            with source.open('rb') as incoming:
                shutil.copyfileobj(incoming, stream)
            stream.flush(); os.fsync(stream.fileno())
        if file_hash(temporary) != item['sha256'] or file_hash(source) != item['sha256']:
            raise ValueError('Artifact changed while preserving recovery evidence')
        os.replace(temporary, target)
    verify_assets(asset_folder, acknowledged)


def verify_assets(folder, acknowledged):
    seen = set()
    for item in acknowledged['artifacts']:
        if item['path'] in seen:
            raise ValueError('Duplicate recovery artifact')
        seen.add(item['path']); path = _target(folder, item)
        if (not path.is_file() or path.is_symlink() or file_hash(path) != item['sha256']
                or path.stat().st_size != item['size_bytes']):
            raise ValueError('Immutable recovery artifact is missing or corrupt: ' + item['path'])
    for record in acknowledged['owner_commands'] + acknowledged['related_save_receipts']:
        path = _target(folder, {'path': record['artifact_path']})
        if (file_hash(path) != record['sha256']
                or canonical_hash(load_json(path)) != record['value_sha256']):
            raise ValueError('Reviewed command/receipt snapshot differs from its preserved original bytes')
    # Existing manifests retain their own internal hash checks as well. This
    # verifies exact stored revision documents, arrays and selected detail DAGs.
    for saved in acknowledged['saved_sources']:
        base = Path(folder) / 'documents' / saved['document_id'] / 'revisions' / saved['saved_revision']
        if file_hash(base / 'revision.json') != saved['revision_manifest_sha256']:
            raise ValueError('Recovery saved revision manifest changed')
        for item in load_json(base / 'revision.json')['files']:
            if file_hash(_target(base, item)) != item['sha256']:
                raise ValueError('Recovery saved revision asset changed')
        if canonical_hash(load_json(base / 'document.json')) != saved['document_sha256']:
            raise ValueError('Recovery saved document snapshot changed')
    for job in acknowledged['jobs']:
        if job['result_at_review'] == 'PUBLISHED':
            base = _target(folder, {'path': job['result_path']})
            if file_hash(base / 'result.json') != job['result_sha256']:
                raise ValueError('Recovery result identity changed')
            metadata = read_result(base, verify='all', selection={'metadata_only': True})
            if 'data_inputs' in acknowledged:
                from .data_recovery_inputs import verify_import_sources
                run = next(r for r in acknowledged['document']['runs'] if r['job_id'] == job['job_id'])
                verify_import_sources(run, metadata, acknowledged['data_inputs'])

    if 'data_inputs' in acknowledged:
        from .data_recovery_inputs import verify_inputs
        verify_inputs(folder, acknowledged)
