"""Collect Numerical evidence through declared owner assets, never replay receipts.

Pending snapshots are owner-acknowledged data, not proof of publication or write
approval. Their exact bytes are copied to candidate_evidence/ for the existing
save hook. CAPTURE journals travel as HISTORY_ONLY retained files, not commands.
"""
from copy import deepcopy
from types import SimpleNamespace

from .evaluation import file_hash
from .portable_project_io import json_file, fail
from .storage import canonical_hash, check_id


def _failure(path, error, identifier):
    fail('CANDIDATE_EVIDENCE_UNAVAILABLE', path,
         '원 후보/선택 attempt 증거를 완결 보존할 수 없습니다: ' + str(error),
         '표시된 owner 증거 파일·동일 원입력·결과를 복구하세요. 원본은 보존되며 자동 저장/재계산하지 않습니다.', identifier)


def collect_working_evidence(reader, document):
    if document.get('kind') != 'numerical':
        return
    # CAPTURE is admitted only against an original fit belonging to this owner.
    # Other Request Plans have ordinary (potentially large) run receipts, not
    # candidate-capture journals. Preserve them in their existing owner store.
    if (not any(run.get('operation')=='fit' for run in document.get('runs',[]))
            and not document.get('candidate_evidence')
            and not document.get('_candidate_evidence_publications')
            and not document.get('portable_capture_history')):
        return
    from .portable_project_drafts import WORKING
    from .numerical_candidate_evidence import CAPTURE, _binding, resolve_candidate_evidence
    identifier = document['id']
    folder = reader.owner(identifier)._folder(identifier)
    rows = {r['id']: r for r in document.get('candidate_evidence', [])}
    if len(rows) != len(document.get('candidate_evidence', [])):
        _failure(folder, '중복 evidence identity', identifier)
    for row in rows.values():
        if row.get('retained_revision'):
            continue
        path = folder / 'candidate_evidence' / (check_id(row['id']) + '.json')
        try:
            value = json_file(path)
            if ('H' + canonical_hash(value) != row['id'] or canonical_hash(value) != row['sha256']
                    or row['binding'] != _binding(value)):
                raise ValueError('acknowledged row and original snapshot hash/binding differ')
            reader._add(identifier, 'candidate_evidence/' + row['id'] + '.json', path)
        except (OSError, ValueError, KeyError, TypeError) as error:
            _failure(path, error, identifier)
    history = deepcopy(document.get('portable_capture_history', []))
    paths = sorted((folder / 'commands').glob('*.json'))
    if len(paths) > 10000:
        _failure(folder / 'commands', 'CAPTURE 이력 검사 한도 초과', identifier)
    for path in paths:
        # Exact owner journal only. No credentials/config/widget traversal.
        receipt = json_file(path)
        if receipt.get('operation') != CAPTURE:
            continue
        try:
            if receipt.get('state') == 'PRESERVING':
                scope = receipt.get('capture_scope', {})
                if (scope.get('document_id') != identifier
                        or scope.get('schema') != 'caelab.candidate-capture-scope.v1'
                        or receipt.get('phase') not in {'PREPARED', 'REGISTERED'}):
                    raise ValueError('pending capture scope/owner/phase is contradictory')
                row = rows.get('H' + receipt['snapshot_sha256'])
                if receipt['phase'] == 'REGISTERED' and row is None:
                    raise ValueError('registered receipt has no acknowledged evidence row')
                if row is not None and row['sha256'] != receipt['snapshot_sha256']:
                    raise ValueError('pending receipt refers to another evidence hash')
            elif receipt.get('state') == 'COMPLETED':
                ref = receipt.get('response', {}).get('reference', {})
                if ref.get('document_id') != identifier or ref.get('evidence_id') not in rows:
                    raise ValueError('completed receipt does not belong to this evidence owner')
                resolve_candidate_evidence(reader.owner(identifier), ref)
                response = receipt['response']
                if response.get('command_id') != path.stem or response.get('document', {}).get('id') != identifier:
                    raise ValueError('completed response identity disagrees with its journal')
            else:
                raise ValueError('unknown capture receipt outcome; explicit recovery required')
            witness = receipt.get('publication')
            if witness is not None:
                expected = {'command_id': path.stem, 'request_hash': receipt['request_hash'],
                    'saved_revision': check_id(witness['saved_revision']),
                    'snapshot_sha256': receipt['snapshot_sha256'],
                    'scope_sha256': canonical_hash(receipt['capture_scope'])}
                if witness != expected:
                    raise ValueError('capture publication witness contradicts its original scope/journal')
                if receipt['state'] == 'COMPLETED':
                    saved = reader.revision(identifier, witness['saved_revision'])
                    if saved.get('_candidate_evidence_publications', {}).get(path.stem) != witness:
                        raise ValueError('completed capture has no matching exact published witness')
            digest = file_hash(path)
            name = 'portable_execution/history/' + check_id(path.stem) + '-' + digest + '.json'
            if not any(r['file'] == name for r in history):
                reader._add(identifier, name, path)
                history.append({'file': name, 'sha256': digest, 'revision': WORKING,
                    'authority': 'HISTORY_ONLY', 'source_document_id': identifier,
                    'command_id': path.stem, 'state': receipt.get('state'), 'phase': receipt.get('phase')})
        except (ValueError, KeyError, TypeError) as error:
            _failure(path, error, identifier)
    if history:
        document['portable_capture_history'] = history


def historical_reader(reader, document):
    identifier = document['id']
    def read(target):
        if target != identifier:
            raise ValueError('Evidence read requested another source owner')
        return deepcopy(document)
    def result(target, job, **kwargs):
        if target != identifier or kwargs:
            raise ValueError('Evidence result requested another source owner/selection')
        return reader.result(document, reader.run(document, job))
    return SimpleNamespace(read=read, result=result, manager=None,
                           _portable_storage_owner=reader.owner(identifier))


def validate_document_evidence(reader, document):
    """Pre-publication semantic check using the unchanged C2 evidence consumer."""
    if document.get('kind') != 'numerical':
        return
    from .numerical_candidate_evidence import _binding, prepare_candidate_evidence
    from .portable_project_execution import execution_read
    identifier = document['id']
    owner = reader.owner(identifier)
    facet = historical_reader(reader, document)
    for row in document.get('candidate_evidence', []):
        base = owner._folder(identifier)
        if row.get('retained_revision'):
            reader.revision(identifier, row['retained_revision'])
            base = base / 'revisions' / row['retained_revision']
        path = base / 'candidate_evidence' / (check_id(row['id']) + '.json')
        try:
            value = json_file(path)
            if ('H' + canonical_hash(value) != row['id'] or canonical_hash(value) != row['sha256']
                    or _binding(value) != row['binding']):
                raise ValueError('evidence row / content / binding mismatch')
            bridge = execution_read(facet, identifier, value['source']['job_id'])
            if bridge:
                if bridge.execution_source != value['source']:
                    raise ValueError('evidence originated in another input/result/store')
                source = bridge.source
            else:
                source = value['source']
                if source['document_id'] != identifier:
                    raise ValueError('evidence belongs to another owner')
            checked = prepare_candidate_evidence(facet, source, value['original_candidate']['candidate_id'],
                attempt_job_id=value['selected_attempt_job_id'],
                required_experiments=[r['experiment_id'] for r in value['scope']], purpose=value['purpose'])
            if canonical_hash(checked) != row['sha256']:
                raise ValueError('original trial/scope/attempt/input verification differs')
        except (OSError, ValueError, KeyError, TypeError) as error:
            _failure(path, error, identifier)
