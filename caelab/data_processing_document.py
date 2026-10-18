"""Processing actions of the existing Data document owner (not another owner).

All mutations run inside MaterialDocuments.command's CAS/command receipt and
owner lock. Preview has no side effects. Applied recipes/results are append-only
and become part of the Data owner's normal saved-revision asset manifest.
"""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import shutil

from .data_processing import preview_recipe, validate_recipe, read_sheet_group
from .evaluation import file_hash, read_result, save_evaluation
from .storage import canonical_hash, check_id, utc_now


def validate_processing(value):
    if not isinstance(value, dict) or set(value) != {'source', 'recipe'}:
        raise ValueError('Processing requires its frozen import source and editable recipe')
    source = value['source']
    required = {'document_id', 'job_id', 'input_revision', 'input_sha256'}
    if not isinstance(source, dict) or set(source) != required:
        raise ValueError('Processing requires an exact original Data import identity')
    for key in ('document_id', 'job_id', 'input_revision'):
        check_id(source[key])
    if not source['document_id'].startswith('T'):
        raise ValueError('Processing source must be a Data document')
    digest = source['input_sha256']
    if not isinstance(digest, str) or len(digest) != 64 or set(digest) - set('0123456789abcdef'):
        raise ValueError('Processing source requires its submitted input SHA-256')
    validate_recipe(value['recipe'])


def preview(owner, identifier, *, document=None):
    """Return a sealed, recomputable preview; does not apply or retain anything."""
    with owner._lock(identifier):
        document = deepcopy(document if document is not None else owner.read(identifier))
        specification = document['draft'].get('processing')
        validate_processing(specification)
        source = specification['source']
        if source['document_id'] != identifier:
            raise ValueError('Apply a recipe in the owner of its original Data import')
        run = next((run for run in document['runs'] if run['job_id'] == source['job_id']), None)
        if run is None or any(run.get(k) != source[k] for k in ('input_revision', 'input_sha256')):
            raise ValueError('Processing source is not the selected immutable import')
        imported = owner.result(identifier, source['job_id'])
        if imported.get('execution_status') != 'SUCCEEDED':
            raise ValueError('The original import did not succeed')
        from .finite_measure_input import verify_processing_specification
        verify_processing_specification(document['draft'], imported)
        result = preview_recipe(imported, source, specification['recipe'])
        result['owner_identity'] = {
            'document_id': identifier, 'session_id': document['session_id'],
            'generation': document['generation'], 'input_revision': document['input_revision'],
            'input_sha256': canonical_hash(document['draft'])}
        # Bind BOTH source bytes and the exact current owner's editable input.
        result.pop('preview_sha256', None)
        result['preview_sha256'] = canonical_hash(result)
        return result


def apply(owner, document, arguments, command_id):
    """Called only by the existing generation-checked Data command dispatch."""
    if set(arguments) != {'preview_sha256'}:
        raise ValueError('data.processing.apply requires the reviewed preview_sha256')
    result = preview(owner, document['id'], document=document)
    if result['preview_sha256'] != arguments['preview_sha256']:
        raise ValueError('Processing preview is stale; preserve the buffer and review again')
    # Unsupported operations may be saved as an explicit PARTIAL processing
    # revision. They never acquire a successful response by relabelling errors.
    revision = 'P' + canonical_hash([document['id'], command_id, result['preview_sha256']])[:40]
    destination = owner._folder(document['id']) / 'processing' / revision
    if destination.exists():
        existing = read_result(destination, verify='all')
        if existing.get('preview_sha256') != result['preview_sha256']:
            raise ValueError('Existing processing revision has different reviewed inputs')
    else:
        save_evaluation(result, destination)
    # A successfully written result is not publication until working.json or a
    # saved Data revision names it. An orphan directory is deliberately ignored.
    record = {'id': revision, 'command_id': command_id,
        'input_revision': document['input_revision'], 'input_sha256': canonical_hash(document['draft']),
        'preview_sha256': result['preview_sha256'], 'source': deepcopy(document['draft']['processing']['source']),
        'recipe_sha256': canonical_hash(document['draft']['processing']['recipe']),
        'result_sha256': file_hash(destination / 'result.json'),
        'state': result['diagnostics']['processing_status'], 'created_utc': utc_now()}
    document.setdefault('processing_revisions', []).append(record)
    document['generation'] += 1  # Retention is not an edit to the recipe input.
    return deepcopy(record)


def _result_folder(owner, document, record):
    retained = record.get('retained_revision')
    if retained:
        owner._verify_revision(document['id'], check_id(retained))
        base = owner._folder(document['id']) / 'revisions' / retained
    else:
        base = owner._folder(document['id'])
    folder = base / 'processing' / check_id(record['id'])
    if file_hash(folder / 'result.json') != record['result_sha256']:
        raise ValueError('An applied processing result changed; no substitute is used')
    return folder


def result(owner, identifier, revision, *, selection=None):
    """Read a retained processing revision, optionally selecting READY channels.

    A PARTIAL recipe may contain independent READY operations. Explicitly reading
    only such channels succeeds for those channels; overall recipe status remains
    PARTIAL in diagnostics. Reading all preserves the overall FAILED status.
    """
    return context(owner,identifier,revision,selection=selection)[0]


def context(owner, identifier, revision, *, selection=None):
    """Trusted internal compiler context; public results remain ordinary records."""
    with owner._lock(identifier):
        document = owner.read(identifier)
        record = next((row for row in document.get('processing_revisions', []) if row['id'] == revision), None)
        if record is None:
            raise ValueError('Processing revision is not published by this Data owner')
        folder=_result_folder(owner,document,record)
        retained=read_snapshot(folder,record,selection=selection)
        def revision_folder(value):
            owner._verify_revision(identifier,check_id(value))
            return owner._folder(identifier)/'revisions'/value
        from .portable_data_processing import source
        original=source(document,record,retained,folder.parent.parent,revision_folder)
        return retained,original


def read_snapshot(folder, record, *, selection=None):
    """Read a published row from an already verified owner snapshot, without opening it."""
    if file_hash(Path(folder)/'result.json') != record['result_sha256']:
        raise ValueError('An applied processing result changed; no substitute is used')
    retained = read_result(folder, verify='all')
    if selection is not None:
        if (not isinstance(selection, list) or not selection or len(selection) != len(set(selection))
                or any(not isinstance(name, str) for name in selection)):
            raise ValueError('Choose explicit distinct processing response names')
        if set(selection) - set(retained['responses']):
            raise ValueError('Selected processing operation is unsupported or has no valid result')
        retained['responses'] = {name: retained['responses'][name] for name in selection}
        retained['execution_status'] = 'SUCCEEDED'
        retained['diagnostics']['selected_channels_only'] = True
    retained['diagnostics']['processing_revision'] = record['id']
    retained['diagnostics']['processing_record'] = deepcopy(record)
    return retained


def retain(owner, saved, folder):
    """Hook in existing DataDocuments._retain_inputs before manifest publication."""
    from .portable_data_processing import retain as retain_proofs
    retain_proofs(owner,saved,folder)
    for record in saved.get('processing_revisions', []):
        source = _result_folder(owner, saved, record)
        target = Path(folder) / 'processing' / check_id(record['id'])
        shutil.copytree(source, target)
        read_result(target, verify='all')
        if file_hash(target / 'result.json') != record['result_sha256']:
            raise ValueError('Processing result changed while retaining a Data revision')
        record['retained_revision'] = Path(folder).name


def recover_apply(owner, identifier):
    """Reconcile durable owner publication; an orphan result is never evidence.

    A process can lose the return from publishing working.json before assigning
    its in-memory document. Reconcile that exact transition without rerunning
    the recipe, incrementing generation, or replacing a newer editor buffer.
    """
    from .storage import load_json, save_json
    current = owner._documents[identifier]
    candidates = [deepcopy(current)]
    working = owner._folder(identifier) / 'working.json'
    if working.exists():
        durable = load_json(working)
        if durable.get('id') != identifier or durable.get('kind') != 'data':
            raise ValueError('Processing publication belongs to a different owner')
        candidates.append(durable)
    seen = set()
    for document in candidates:
        for record in document.get('processing_revisions', []):
            command_id = check_id(record['command_id'])
            if command_id in seen:
                continue
            path = owner._folder(identifier) / 'commands' / (command_id + '.json')
            if not path.exists():
                continue
            command = load_json(path)
            if 'response' in command:
                seen.add(command_id)
                continue
            signature = canonical_hash(dict(document_id=identifier,
                operation='data.processing.apply',
                arguments={'preview_sha256': record['preview_sha256']},
                session_id=command.get('session_id'),
                expected_generation=command.get('input_generation')))
            if (command.get('operation') != 'data.processing.apply'
                    or command.get('request_hash') != signature
                    or command.get('input_revision') != record['input_revision']
                    or canonical_hash(command.get('input')) != record['input_sha256']):
                raise ValueError('Applied processing receipt conflicts with its owner command')
            read_result(_result_folder(owner, document, record), verify='all')
            current = owner._documents[identifier]
            if (current.get('session_id') == document.get('session_id') == command.get('session_id')
                    and current['generation'] == command['input_generation']
                    and document['generation'] == command['input_generation'] + 1
                    and current['input_revision'] == document['input_revision'] == record['input_revision']
                    and canonical_hash(current['draft']) == canonical_hash(document['draft']) == record['input_sha256']
                    and current.get('_disk_revision') == document.get('_disk_revision')):
                owner._documents[identifier] = deepcopy(document)
            response = {'document': owner._public(document), 'command_id': command_id,
                        'processing': deepcopy(record), 'recovered_after_response_loss': True}
            save_json(path, {'request_hash': command['request_hash'], 'response': response})
            seen.add(command_id)
