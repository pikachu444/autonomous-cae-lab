"""Read-only Data input closure for existing Keep-recovery artifacts.

Uses the same current/Undo/Redo/run source boundary as DataDocuments._retain_inputs
and its _retained_source/resolve_input/_check_source contracts. No input is
registered, no revision is made and no draft, command or processing result is
rewritten. Actual input.json bytes (not regenerated JSON) are retained.
"""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from .evaluation import file_hash
from .storage import canonical_hash, check_id, load_json


def declared_uses(document):
    """Enumerate acknowledged dependencies only; raw/local buffers are NOT here.

    Field paths point into the immutable acknowledged document. Run arguments
    are additional *frozen* claims, not a substitute for the submitted draft.
    Incomplete unsubmitted declarations remain inspectable without invented IDs.
    """
    uses = []

    def add(value, path, role, required=False, claim=None):
        uses.append({'data_id': deepcopy(value), 'path': path, 'role': role,
                     'required': required, 'claim': deepcopy(claim)})

    def draft(value, path, required=False):
        if not isinstance(value, dict):
            return
        if 'data_id' in value:
            add(value['data_id'], path + ['data_id'], 'data', required)
        else:
            add(None, path + ['data_id'], 'data', required)
        mapping = value.get('mapping')
        columns = mapping.get('columns', {}) if isinstance(mapping, dict) else {}
        specs = [(spec, path + ['mapping', 'columns', name])
                 for name, spec in columns.items()] if isinstance(columns, dict) else []
        acquisition = value.get('acquisition')
        if isinstance(acquisition, dict) and isinstance(acquisition.get('channels'), list):
            specs += [(spec, path + ['acquisition', 'channels', i])
                      for i, spec in enumerate(acquisition['channels'])]
        for spec, location in specs:
            if not isinstance(spec, dict) or 'calibration' not in spec:
                continue
            calibration = spec['calibration']
            source = calibration.get('source') if isinstance(calibration, dict) else None
            add(source.get('data_id') if isinstance(source, dict) else None,
                location + ['calibration', 'source'], 'calibration', required, source)

    draft(document['draft'], ['draft'])
    for key in ('_undo', '_redo'):
        for i, value in enumerate(document.get(key, [])):
            draft(value, [key, i])
    for i, run in enumerate(document.get('runs', [])):
        # Data owners submit import_table; never interpret another operation as
        # an import just because an unrelated payload happens to use "data_id".
        if run.get('operation') != 'import_table':
            raise ValueError('Data recovery run has no supported import source contract')
        draft(run.get('draft'), ['runs', i, 'draft'], True)
        args = run.get('arguments')
        if isinstance(args, dict):
            submitted = run.get('draft', {})
            if (isinstance(submitted, dict) and submitted and
                    (submitted.get('data_id') != args.get('data_id')
                     or submitted.get('mapping') != args.get('mapping'))):
                raise ValueError('Submitted Data draft and frozen import arguments differ')
            draft(args, ['runs', i, 'arguments'], True)
            if args.get('source_ref') is not None:
                ref = args['source_ref']
                if not isinstance(ref, dict) or ref.get('data_id') != args.get('data_id'):
                    raise ValueError('Import source_ref does not match its original data_id')
                add(ref.get('data_id') if isinstance(ref, dict) else None,
                    ['runs', i, 'arguments', 'source_ref'], 'frozen_source', True, ref)
            refs = args.get('calibration_sources', [])
            if not isinstance(refs, list):
                raise ValueError('Invalid frozen calibration source list')
            for j, ref in enumerate(refs):
                add(ref.get('data_id') if isinstance(ref, dict) else None,
                    ['runs', i, 'arguments', 'calibration_sources', j],
                    'frozen_calibration', True, ref)
    return uses


def _valid_id(value):
    try:
        return check_id(value).startswith('D')
    except ValueError:
        return False


def _groups(document):
    groups, incomplete = {}, []
    for use in declared_uses(document):
        if _valid_id(use['data_id']):
            groups.setdefault(use['data_id'], []).append(use)
        else:
            if use['required']:
                raise ValueError('A submitted Data/calibration input has no valid original identity')
            incomplete.append({'data_id': use['data_id'], 'uses': [use],
                'state': 'UNDECLARED' if use['data_id'] in (None, '') else 'INVALID_IDENTITY'})
    return groups, incomplete


def _validate_claims(document, identifier, uses, receipt):
    """Same hash/size/receipt meaning as the existing frozen import boundary."""
    for use in uses:
        claim = use['claim']
        if not isinstance(claim, dict):
            continue
        if claim.get('data_id') != identifier:
            raise ValueError('Data recovery source identity changed')
        if use['role'] in ('frozen_source', 'frozen_calibration'):
            kind = claim.get('kind')
            required = {'kind', 'data_id', 'sha256', 'bytes', 'receipt_sha256'}
            if kind in ('registered_input', 'retained_data_input'):
                required |= {'document_id'}
                if claim.get('document_id') != document['id']:
                    raise ValueError('Frozen input belongs to a different Data owner')
            elif kind != 'registered_calibration':
                raise ValueError('Unsupported frozen Data input reference')
            if kind == 'retained_data_input':
                required |= {'revision', 'revision_sha256'}
            if set(claim) != required:
                raise ValueError('Incomplete or unsupported frozen input fields')
            if (claim['sha256'] != receipt['sha256'] or claim['bytes'] != receipt['bytes']
                    or claim['receipt_sha256'] != canonical_hash(receipt)):
                raise ValueError('Frozen Data source bytes or registration receipt changed')
        elif use['role'] == 'calibration':
            # An unfinished recipe can be kept, but a supplied hash cannot be
            # silently replaced by whatever bytes happen to occupy that ID.
            if claim.get('sha256') not in (None, '') and claim['sha256'] != receipt['sha256']:
                raise ValueError('Declared calibration source hash differs from retained bytes')
            if use['required'] and claim.get('sha256') != receipt['sha256']:
                raise ValueError('Submitted calibration is missing its exact source hash')


def _relative(root, path):
    """Registered/retained files stay inside the original store, without aliases."""
    root, path = Path(root).resolve(), Path(path)
    # Check the original lexical path as well: resolving first hides symlinks.
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError('Recovery source/receipt cannot use symlink aliases')
    resolved = path.resolve()
    if not resolved.is_relative_to(root) or not resolved.is_file():
        raise ValueError('Recovery source/receipt is missing or outside its store')
    return resolved.relative_to(root).as_posix()


def capture_inputs(owner, document, root, add_file, revision):
    """Caller holds the existing owner lock. Return fields for its existing manifest.

    Saved source bindings have priority exactly as in _retain_inputs; malformed
    or changed bindings never fall through to a live replacement. A previously
    submitted input missing from both locations is a hard failure, not a draft.
    """
    groups, incomplete = _groups(document)
    records = []
    for identifier, uses in sorted(groups.items()):
        binding = document.get('retained_inputs', {}).get(identifier)
        original = owner._retained_source(document, identifier)
        metadata = None
        try:
            if original is not None:
                source, receipt = original
                base = owner._folder(document['id']) / 'revisions' / check_id(binding['revision'])
                metadata = base / binding['metadata']
                revision(document['id'], binding['revision'])
                resolution = 'retained_data_input'
            else:
                source, receipt = owner.resolve_input(identifier)
                metadata = Path(root) / 'inputs' / identifier / 'input.json'
                resolution = 'registered_input'
        except FileNotFoundError:
            # Same unfinished-ID distinction as _retain_inputs. If even a
            # partial registration exists, its loss is NOT a new unfinished ID.
            pinned = any(u['required'] or isinstance(u['claim'], dict)
                         and u['claim'].get('sha256') not in (None, '') for u in uses)
            if pinned or binding is not None or (Path(root) / 'inputs' / identifier).exists():
                raise
            records.append({'data_id': identifier, 'uses': uses,
                            'state': 'UNRESOLVED_UNSUBMITTED'})
            continue
        source = Path(source)
        owner._check_source(identifier, source, receipt)
        source_file, metadata_file = _relative(root, source), _relative(root, metadata)
        metadata_hash = file_hash(metadata)
        actual = load_json(metadata)
        if actual != receipt or file_hash(metadata) != metadata_hash:
            raise ValueError('Actual input.json differs from the resolved registration receipt')
        if resolution == 'registered_input':
            # Do not let a receipt for a sibling registration redirect reads.
            if (receipt.get('file') != source_file
                    or not source.resolve().is_relative_to((Path(root) / 'inputs' / identifier).resolve())):
                raise ValueError('Registered source path is not owned by its input.json')
        _validate_claims(document, identifier, uses, receipt)
        for use in uses:
            claim = use['claim']
            if isinstance(claim, dict) and claim.get('kind') == 'retained_data_input':
                # Reuse the owner verifier for the *original* frozen revision.
                # Even if a newer saved copy is selected, both references must
                # still describe exactly the same bytes and receipt.
                frozen_source, frozen_receipt = owner.resolve_job_source(identifier, claim)
                if frozen_receipt != receipt or file_hash(frozen_source) != receipt['sha256']:
                    raise ValueError('Frozen retained source differs from acknowledged fallback')
                revision(claim['document_id'], claim['revision'])
        add_file(source)
        add_file(metadata)
        owner._check_source(identifier, source, receipt)
        if file_hash(metadata) != metadata_hash:
            raise ValueError('Registration receipt changed during recovery capture')
        record = {'data_id': identifier, 'state': 'RETAINED', 'uses': uses,
            'resolution': resolution, 'source_file': source_file, 'metadata_file': metadata_file,
            'sha256': receipt['sha256'], 'bytes': receipt['bytes'],
            'receipt': deepcopy(receipt), 'receipt_sha256': canonical_hash(receipt),
            'metadata_sha256': metadata_hash}
        if binding is not None:
            record['retained_binding'] = deepcopy(binding)
        records.append(record)
    return records + incomplete


def verify_inputs(folder, acknowledged):
    """Validate dependency closure, bindings and original bytes, not just a seal."""
    if 'data_inputs' not in acknowledged:
        return 'LEGACY_INPUT_CLOSURE_NOT_RETAINED'
    document = acknowledged['document']
    if document['kind'] != 'data':
        raise ValueError('Data recovery input evidence belongs to another owner kind')
    records = acknowledged['data_inputs']
    if not isinstance(records, list):
        raise ValueError('Invalid recovery Data input evidence')
    expected = declared_uses(document)
    actual = [u for r in records for u in r['uses']]
    if (len(actual) != len(expected) or sorted(map(canonical_hash, actual)) != sorted(map(canonical_hash, expected))):
        raise ValueError('Recovery input closure differs from acknowledged current/Undo/Redo/run dependencies')
    from .related_save_recovery_assets import _target
    from .data_document import DataDocuments
    artifacts = {a['path']: a for a in acknowledged['artifacts']}
    seen = set()
    for record in records:
        identifier, uses, state = record['data_id'], record['uses'], record['state']
        if not uses or any(u['data_id'] != identifier for u in uses):
            raise ValueError('Input evidence lost its original dependency identity')
        if state in ('UNDECLARED', 'INVALID_IDENTITY'):
            if _valid_id(identifier) or any(u['required'] for u in uses):
                raise ValueError('Submitted input cannot be relabelled incomplete')
            correct = 'UNDECLARED' if identifier in (None, '') else 'INVALID_IDENTITY'
            if state != correct:
                raise ValueError('Incomplete input identity status changed')
            continue
        if not _valid_id(identifier) or identifier in seen:
            raise ValueError('Invalid or duplicate retained input identity')
        seen.add(identifier)
        if state == 'UNRESOLVED_UNSUBMITTED':
            if any(u['required'] or isinstance(u['claim'], dict) and u['claim'].get('sha256') not in (None, '') for u in uses):
                raise ValueError('Required original input is missing from recovery')
            continue
        if state != 'RETAINED':
            raise ValueError('Unknown recovery input state')
        receipt = record['receipt']
        source = _target(folder, {'path': record['source_file']})
        metadata = _target(folder, {'path': record['metadata_file']})
        _relative(folder, Path(folder) / record['source_file'])
        _relative(folder, Path(folder) / record['metadata_file'])
        DataDocuments._check_source(identifier, source, receipt)
        if (record['receipt_sha256'] != canonical_hash(receipt)
                or load_json(metadata) != receipt or file_hash(metadata) != record['metadata_sha256']
                or record['sha256'] != receipt['sha256'] or record['bytes'] != receipt['bytes']):
            raise ValueError('Recovery source bytes/input.json/receipt identity differs')
        for path, digest, size in ((record['source_file'], receipt['sha256'], receipt['bytes']),
                                  (record['metadata_file'], record['metadata_sha256'], metadata.stat().st_size)):
            if path not in artifacts or artifacts[path]['sha256'] != digest or artifacts[path]['size_bytes'] != size:
                raise ValueError('Data source/receipt is absent from the exact artifact manifest')
        _validate_claims(document, identifier, uses, receipt)
        binding = document.get('retained_inputs', {}).get(identifier)
        if record['resolution'] == 'retained_data_input':
            if binding is None or record.get('retained_binding') != binding:
                raise ValueError('Recovery changed the original retained source binding')
            base = Path('documents') / document['id'] / 'revisions' / check_id(binding['revision'])
            if (record['source_file'] != (base / binding['file']).as_posix()
                    or record['metadata_file'] != (base / binding['metadata']).as_posix()
                    or binding['sha256'] != receipt['sha256'] or binding['bytes'] != receipt['bytes']):
                raise ValueError('Retained Data input path/identity changed')
            saved = load_json(_target(folder, {'path': (base / 'document.json').as_posix()}))
            if saved.get('retained_inputs', {}).get(identifier) != binding:
                raise ValueError('Saved Data revision does not own this retained input')
        elif record['resolution'] == 'registered_input':
            base = Path('inputs') / identifier
            if (binding is not None or record['metadata_file'] != (base / 'input.json').as_posix()
                    or record['source_file'] != receipt.get('file')
                    or Path(record['source_file']).parent != base):
                raise ValueError('Registered input source/receipt relation changed')
        else:
            raise ValueError('Unsupported recovery source resolution')
        for use in uses:
            claim = use['claim']
            if isinstance(claim, dict) and claim.get('kind') == 'retained_data_input':
                base = Path('documents') / document['id'] / 'revisions' / check_id(claim['revision'])
                if file_hash(_target(folder, {'path': (base / 'revision.json').as_posix()})) != claim['revision_sha256']:
                    raise ValueError('Original frozen source revision changed')
    return ('COMPLETE' if all(r['state'] == 'RETAINED' for r in records)
            else 'INCOMPLETE_UNSUBMITTED_DECLARATIONS')


def inspect_capsule(capsule_path, *, expected_capsule_sha256=None):
    """Capsule+assets only, no owner construction, original store or writes.

    The optional expected hash comes from the caller's retained Keep receipt.
    Local hashes detect corruption; they are not authentication against an actor
    replacing the whole bundle *and* its separately held expected hash.
    """
    from .related_save_recovery import FORMAT, validate_raw
    from .related_save_recovery_assets import verify_snapshot, verify_assets
    from .data_document import DataDocuments
    path = Path(capsule_path)
    before = file_hash(path)
    capsule = load_json(path)
    if (capsule.get('format') != FORMAT or capsule.get('capsule_id') != path.stem
            or canonical_hash({k: v for k, v in capsule.items() if k != 'capsule_sha256'}) != capsule.get('capsule_sha256')
            or expected_capsule_sha256 is not None and capsule['capsule_sha256'] != expected_capsule_sha256):
        raise ValueError('Recovery capsule identity or expected hash changed')
    if capsule['identity']['kind'] != 'data' or capsule.get('saved_revision_created') is not False:
        raise ValueError('Choose the original Data recovery capsule, not a saved/renamed owner')
    ack = capsule['acknowledged']
    verify_snapshot(DataDocuments, capsule['identity'], ack)
    verify_assets(path.with_suffix('.assets'), ack)
    validate_raw(capsule['raw'], ack['document']['draft'])
    if canonical_hash(capsule['raw']) != capsule['raw_sha256'] or file_hash(path) != before:
        raise ValueError('Recovery capsule/raw changed while reading')
    return {'capsule': capsule, 'source_retention': verify_inputs(path.with_suffix('.assets'), ack),
            'owner_mutated': False, 'resume_permission': 'NOT_GRANTED', 'source_registered': False}


def resolve_source(capsule_path, data_id, *, expected_capsule_sha256=None):
    """Return verified archived path + ORIGINAL receipt, never a new registered ID.

    For a bounded atomic read use preview_source. Callers of this path-level API
    must reverify after their reader finishes (as read_table_source does).
    """
    value = inspect_capsule(capsule_path, expected_capsule_sha256=expected_capsule_sha256)
    if value['source_retention'] == 'LEGACY_INPUT_CLOSURE_NOT_RETAINED':
        raise ValueError('This legacy capsule did not retain its Data input closure')
    record = next((r for r in value['capsule']['acknowledged']['data_inputs'] if r['data_id'] == check_id(data_id)), None)
    if record is None or record['state'] != 'RETAINED':
        raise ValueError('Original source bytes are not retained for this acknowledged identity')
    from .related_save_recovery_assets import _target
    return _target(Path(capsule_path).with_suffix('.assets'), {'path': record['source_file']}), deepcopy(record['receipt'])


def preview_source(capsule_path, data_id, *, expected_capsule_sha256=None):
    """Existing bounded UTF-8/table preview; no implicit import, calibration or job."""
    inspected = inspect_capsule(capsule_path, expected_capsule_sha256=expected_capsule_sha256)
    expected_capsule_sha256 = inspected['capsule']['capsule_sha256']
    source, receipt = resolve_source(capsule_path, data_id, expected_capsule_sha256=expected_capsule_sha256)
    result = {'id': data_id, 'receipt': receipt, 'source_sha256': receipt['sha256'],
              'source_registered': False, 'owner_mutated': False, 'resume_permission': 'NOT_GRANTED'}
    if source.suffix.lower() not in {'.csv', '.txt', '.dat', '.asc', '.json', '.md'}:
        return {**result, 'preview': 'Binary original; exact bytes are retained and available through resolve_source.'}
    with source.open(encoding='utf-8-sig') as stream:
        text = stream.read(16385)
    resolve_source(capsule_path, data_id, expected_capsule_sha256=expected_capsule_sha256)
    from .adapters.file_table import preview_table
    result.update(text=text[:16384], truncated=len(text) > 16384)
    result['table_preview'] = preview_table(result['text'], truncated=result['truncated'])
    return result


def read_table_source(capsule_path, *, draft_path=None, expected_capsule_sha256=None):
    """Read the selected acknowledged mapping with the unchanged files.table reader.

    This is a read-only parse, not owner.data.import or a new retained result.
    No mapping/units/rows are supplied or guessed by this helper.
    """
    value = inspect_capsule(capsule_path, expected_capsule_sha256=expected_capsule_sha256)
    expected_capsule_sha256 = value['capsule']['capsule_sha256']
    d = value['capsule']['acknowledged']['document']
    path = ['draft'] if draft_path is None else draft_path
    valid_paths = [['draft'], *[['_undo', i] for i in range(len(d.get('_undo', [])))],
                   *[['_redo', i] for i in range(len(d.get('_redo', [])))],
                   *[['runs', i, 'draft'] for i in range(len(d.get('runs', [])))]]
    if path not in valid_paths:
        raise ValueError('Select an exact acknowledged current/Undo/Redo/run draft path')
    draft = d
    for key in path:
        draft = draft[key]
    source, receipt = resolve_source(capsule_path, draft['data_id'], expected_capsule_sha256=expected_capsule_sha256)
    # All mapping certificates were verified in inspect_capsule, including their
    # declared hashes, original receipt and frozen run-reference relationships.
    from .adapters.file_table import read_table
    table = read_table(source, deepcopy(draft['mapping']))
    inspect_capsule(capsule_path, expected_capsule_sha256=expected_capsule_sha256)
    return {'table': table, 'receipt': receipt, 'draft_path': deepcopy(path),
            'mapping': deepcopy(draft['mapping']), 'interpretation': 'READ_ONLY_PARSE_NOT_IMPORT',
            'owner_mutated': False, 'source_registered': False, 'job_submitted': False}


def verify_import_sources(run, result, records):
    """Bind a retained import to its preserved raw source, not a new input alias."""
    args = run.get('arguments', {})
    identifier = args.get('data_id', run.get('draft', {}).get('data_id'))
    source = next((r for r in records if r['data_id'] == identifier and r['state'] == 'RETAINED'), None)
    if source is None:
        raise ValueError('Submitted Data result has no preserved original source bytes')
    diagnostics = result.get('diagnostics', {})
    if diagnostics.get('source_sha256') is not None and diagnostics['source_sha256'] != source['sha256']:
        raise ValueError('Imported result source hash differs from original bytes')
    if diagnostics.get('source_ref') is not None and diagnostics['source_ref'] != args.get('source_ref'):
        raise ValueError('Import result and submitted frozen source references differ')
    if diagnostics.get('calibration_sources') is not None and diagnostics['calibration_sources'] != args.get('calibration_sources', []):
        raise ValueError('Import result and submitted calibration sources differ')
