"""Read-only acknowledged snapshots for the existing portable owner projection.

Not an owner, draft editor, raw-widget capsule collector or save coordinator.
The virtual revision is a retained-asset container, NEVER the saved document head.
Only explicitly selected owners and their declared inputs/jobs are inspected.
"""
from __future__ import annotations
from copy import deepcopy
import hashlib
import json
from pathlib import Path

from .connection_graph import SnapshotReader, is_acknowledged_container
from .evaluation import read_result
from .jobs import TERMINAL
from .portable_project_io import fail, fingerprint_file, inside, json_file, no_links, relative_name
from .storage import canonical_hash, check_id

WORKING = 'acknowledged'
HISTORY = 'acknowledged-input-'

def virtual_revision(revision):
    return revision == WORKING or revision.startswith(HISTORY)
POLICIES = {'acknowledged', 'saved_only'}
# Explicit kept archives only; no runtime UI/global settings discovery.
from .portable_project_recovery import BOUNDARY as CAPSULE_CONTRACT


def snapshot_bytes(document):
    return (json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True,
                       allow_nan=False) + '\n').encode('utf-8')


def data_input_ids(document):
    """The same explicit Data draft/history/calibration fields as _retain_inputs.

    Empty/invalid editable input identifiers are not fabricated file references.
    Syntactically valid missing source IDs do block acknowledged publication.
    """
    drafts = [document['draft'], *document.get('_undo', []), *document.get('_redo', [])]
    drafts += [row.get('draft', {}) for row in document.get('runs', [])]
    identifiers = set(document.get('retained_inputs', {}))
    for draft in drafts:
        if not isinstance(draft, dict):
            continue
        values = [draft.get('data_id')]
        mapping = draft.get('mapping')
        columns = mapping.get('columns', {}) if isinstance(mapping, dict) else {}
        specs = list(columns.values()) if isinstance(columns, dict) else []
        acquisition = draft.get('acquisition')
        if isinstance(acquisition, dict) and isinstance(acquisition.get('channels'), list):
            specs += acquisition['channels']
        for spec in specs:
            calibration = spec.get('calibration') if isinstance(spec, dict) else None
            source = calibration.get('source') if isinstance(calibration, dict) else None
            if isinstance(source, dict):
                values.append(source.get('data_id'))
        for value in values:
            try:
                check_id(value)
            except (TypeError, ValueError):
                continue
            if value.startswith('D'):
                identifiers.add(value)
    return sorted(identifiers)


def recorded_material_input(reader, identifier, input_revision):
    """Prove a referenced earlier acknowledged input from that owner's receipt.

    History lists contain drafts but not prior input IDs. Matching by content
    alone would invent identity. Only an exact completed owner response qualifies.
    The original receipt bytes are separately archived, never copied as commands.
    """
    owner = reader.owner(identifier)
    if owner.kind != 'material':
        raise FileNotFoundError('이 owner의 이전 acknowledged 입력 증거 계약은 지원하지 않습니다.')
    paths = sorted((owner._folder(identifier) / 'commands').glob('*.json'))
    if len(paths) > 10000:
        raise ValueError('owner 명령 이력 한도를 넘었습니다. 정확한 입력을 원도구에서 별도로 보존하세요.')
    found = []
    for path in paths:
        record = json_file(path)
        response = record.get('response', {})
        doc = response.get('document') if isinstance(response, dict) else None
        if not isinstance(doc, dict) or doc.get('input_revision') != input_revision:
            continue
        if doc.get('id') != identifier or doc.get('kind') != 'material' or type(doc.get('generation')) is not int:
            raise ValueError('이전 acknowledged 입력의 owner 증거가 일치하지 않습니다.')
        owner._draft(doc['draft'])
        found.append((doc, path))
    if not found:
        raise FileNotFoundError('정확한 이전 acknowledged 입력/세대의 owner 확인 기록이 없습니다.')
    if len({canonical_hash({'input':d['draft'],'generation':d['generation']}) for d,_ in found}) != 1:
        raise ValueError('같은 입력 개정에 서로 다른 owner 확인 기록이 있습니다.')
    return deepcopy(found[0][0]), found[0][1]


class AcknowledgedReader(SnapshotReader):
    """Adds explicit in-memory/disk acknowledged snapshots, without owner.open/save.

    Public inspection returns only inventory metadata, never the file payload.
    All synthetic records are reconstructed under the owner's locks at creation.
    """
    def __init__(self, workbench, included=()):
        super().__init__(workbench)
        self.included = set(included)
        self.raw = {}
        self.working_documents = {}
        self.working_files = {}
        self.payloads = {}
        self.live_results = {}
        self.live_jobs = {}
        self.history_documents = {}
        self.archive_folders = {}
        self.recovery_inputs = set()

    def revision_folder(self, identifier, revision):
        return self.archive_folders.get((identifier, revision),
            self.owner(identifier)._folder(identifier) / 'revisions' / revision)

    def archived_revision(self, identifier, revision, folder, proof):
        """Register an already verified Q saved source, not a substitute owner.

        Existing live immutable bytes must agree if present. A missing historical
        folder may be read from Q.assets; a corrupt live revision is NOT repaired.
        """
        key = (check_id(identifier), check_id(revision))
        folder = Path(folder)
        document = json_file(inside(folder, 'document.json'))
        manifest = inside(folder, 'revision.json')
        from .evaluation import file_hash
        if (document.get('id') != identifier or document.get('saved_revision') != revision
                or document.get('kind') != self.owner(identifier).kind
                or canonical_hash(document) != proof['document_sha256']
                or file_hash(manifest) != proof['revision_manifest_sha256']
                or self.owner(identifier)._fingerprint(document) != document.get('_saved_fingerprint')):
            raise ValueError('Q saved source differs from its actual owner retention proof')
        live = self.owner(identifier)._folder(identifier) / 'revisions' / revision
        if live.exists():
            verified = super().revision(identifier, revision)
            if canonical_hash(verified) != canonical_hash(document) or file_hash(live / 'revision.json') != file_hash(manifest):
                raise ValueError('Current immutable revision conflicts with original Q saved source')
            return
        if key in self._revisions and canonical_hash(self._revisions[key]) != canonical_hash(document):
            raise ValueError('Two Q assets disagree about one exact saved revision')
        self._revisions[key] = deepcopy(document)
        self.archive_folders.setdefault(key, folder)

    def resolve(self, typed):
        if typed.form == 'material_input' and typed.value.get('saved_revision'):
            from .connection_graph import saved_reference
            ref = typed.value
            saved = self.revision(typed.document_id, ref['saved_revision'])
            if (saved['kind'] != 'material' or saved['input_revision'] != ref['input_revision']
                    or saved['generation'] != ref['generation']
                    or canonical_hash(saved['draft']) != canonical_hash(ref['draft'])
                    or canonical_hash(saved['draft']) != ref.get('input_sha256')):
                raise ValueError('Exact saved Material binding differs from retained owner input')
            return {'exact_reference':saved_reference(saved), 'reference_basis':'stored_reference'}
        return super().resolve(typed)

    def _add(self, identifier, asset, path=None, *, payload=None, archive_only=False, revision=WORKING):
        relative_name(asset)
        if payload is not None:
            identity = {'bytes': len(payload), 'sha256': hashlib.sha256(payload).hexdigest()}
            location = f'workbench/documents/{identifier}/{revision}/{asset}'
            self.payloads[(identifier, revision, asset)] = payload
        else:
            path = Path(path).absolute()
            no_links(path)
            if not path.is_relative_to(self.wb.workspace):
                fail('SOURCE_OUTSIDE_STORE', path, '승인된 owner 보존소 밖의 자료입니다.',
                     'Data의 명시적 로컬 자료 등록을 먼저 사용하세요.', identifier)
            identity = fingerprint_file(path)
            location = path.relative_to(self.wb.workspace).as_posix()
        row = {'path': location, 'document_id': identifier, 'saved_revision': revision,
               'asset': asset, **identity}
        if payload is not None:
            row['origin'] = 'acknowledged_snapshot'
        if archive_only:
            row['archive_only'] = True
        self.working_files.setdefault(identifier, []).append(row)
        return row

    def working(self, identifier):
        if identifier in self.working_documents:
            return deepcopy(self.working_documents[identifier])
        if identifier not in self.included:
            fail('DRAFT_NOT_SELECTED', identifier, '이 문서의 초안을 포함하지 않았습니다.',
                 '초안 포함 옵션으로 문서를 명시적으로 선택하세요.', identifier)
        owner = self.owner(identifier)
        raw = super().current(identifier)
        self.raw[identifier] = deepcopy(raw)
        doc = deepcopy(raw)
        # Serialized live owner snapshot is separate from whatever disk recovery
        # file remains after a save (the shared owner may leave that file older).
        self._add(identifier, 'document.json', payload=snapshot_bytes(raw))
        disk = owner._folder(identifier) / 'working.json'
        if disk.is_file():
            self._add(identifier, 'owner-working.json', disk, archive_only=True)
        if doc['kind'] == 'data':
            retained = deepcopy(doc.get('retained_inputs', {}))
            for data_id in data_input_ids(doc):
                if data_id in retained:
                    owner._retained_source(doc, data_id)
                    continue
                receipt_path = self.wb.root / 'inputs' / data_id / 'input.json'
                try:
                    source, receipt = owner.resolve_input(data_id)
                    source = Path(source)
                    owner._check_source(data_id, source, receipt)
                except (OSError, ValueError, KeyError) as error:
                    fail('DRAFT_SOURCE_MISSING', receipt_path,
                         '받아들인 초안/Undo 이력의 원자료를 보존할 수 없습니다: ' + str(error),
                         '동일 원자료를 Data에서 명시적으로 복구하거나 저장본만 복사를 선택하세요.', identifier)
                # No directory walking, environment or input-registry enumeration.
                original_receipt = json_file(receipt_path)
                if original_receipt != receipt:
                    fail('SOURCE_CHANGED', receipt_path, '자료 등록 기록이 변경되었습니다.', '목록을 다시 확인하세요.', identifier)
                target = f'sources/{data_id}/source{source.suffix}'
                self._add(identifier, target, source)
                self._add(identifier, f'sources/{data_id}/input.json', receipt_path)
                retained[data_id] = {'revision': WORKING, 'file': target,
                    'metadata': f'sources/{data_id}/input.json', 'sha256': receipt['sha256'], 'bytes': receipt['bytes']}
            doc['retained_inputs'] = retained
            doc['unresolved_inputs'] = []
        if doc['kind'] == 'report':
            from .portable_project_report import collect_working
            collect_working(self, doc)
        for run in doc.get('runs', []):
            if run.get('retention_complete') and run.get('retained_record'):
                continue
            job = self.wb.manager.status(run['job_id']) if run.get('retained_record') else super().job(raw, run)
            if job['state'] not in TERMINAL:
                fail('DRAFT_RUN_ACTIVE', self.wb.manager.root / 'jobs' / (run['job_id'] + '.json'),
                     '진행 중이거나 상태가 미확정인 초안 계산은 발행할 수 없습니다.',
                     '완료/취소 확인 후 다시 검사하거나 저장본만 복사를 명시적으로 선택하세요.', identifier)
            # A stale retained nonterminal snapshot must not hide the actual job.
            if run.get('retained_record') and not run.get('retention_complete'):
                job = self.wb.manager.status(run['job_id'])
            if (job['state'] not in TERMINAL or job['operation'] != run['operation']
                    or job['arguments'] != run['arguments']):
                fail('DRAFT_RUN_UNCONFIRMED', run['job_id'], '초안 계산의 원입력/종료 상태가 다릅니다.',
                     '원 owner에서 계산 기록을 확인하세요. 자동 재실행하지 않습니다.', identifier)
            job_path = self.wb.manager.root / 'jobs' / (check_id(run['job_id']) + '.json')
            if json_file(job_path) != job:
                fail('SOURCE_CHANGED', job_path, '계산 기록이 변경되었습니다.', '목록을 다시 확인하세요.', identifier)
            self._add(identifier, 'jobs/' + run['job_id'] + '.json', job_path)
            self._add(identifier, 'inputs/' + run['job_id'] + '.json', payload=snapshot_bytes(run))
            result_folder = self.wb.manager.root / 'results' / run['job_id']
            if job.get('result_refs'):
                read_result(result_folder, verify='all', selection={'metadata_only': True})
                self.live_results[(identifier, run['job_id'])] = result_folder
                run['retained_result'] = {'revision': WORKING, 'job_id': run['job_id']}
            # Only this explicit owned job's retained result tree, including a
            # failed attempt's failure.json, is copied; never the jobs root.
            if result_folder.exists():
                no_links(result_folder)
                for path in sorted(result_folder.rglob('*')):
                    no_links(path)
                    if path.is_file():
                        self._add(identifier, 'results/' + run['job_id'] + '/' + path.relative_to(result_folder).as_posix(), path)
            run.update(retained_record={'revision': WORKING, 'job_id': run['job_id']},
                       retained_state=job['state'], retained_error=deepcopy(job.get('error')), retention_complete=True)
            self.live_jobs[(identifier, run['job_id'])] = job
        # Comparisons have their own immutable owner-managed snapshot. An
        # unretained comparison cannot be converted into an invented saved one.
        for row in doc.get('comparisons', []):
            if not row.get('retained_revision'):
                fail('DRAFT_COMPARISON_NOT_RETAINED', identifier + '/comparisons/' + str(row.get('id')),
                     '초안 비교의 보존 개정이 없습니다.',
                     '원 owner에서 비교를 보존하거나 저장본만 복사를 선택하세요.', identifier)
        from .portable_project_evidence import collect_working_evidence
        collect_working_evidence(self, doc)
        self.working_documents[identifier] = doc
        return deepcopy(doc)

    def history_input(self, identifier, input_revision):
        key = (identifier, input_revision)
        revision = HISTORY + check_id(input_revision)
        if key not in self.history_documents:
            if identifier not in self.included | self.recovery_inputs:
                raise ValueError('이전 입력을 증명할 원문서의 acknowledged 이력을 명시적으로 포함하세요.')
            original, path = recorded_material_input(self, identifier, input_revision)
            # Input-only snapshot, NOT an invented old whole document/history.
            doc = {k: deepcopy(original[k]) for k in ('id','kind','title','generation','input_revision','draft')}
            doc.update(saved_revision=revision, _disk_revision=None, _saved_fingerprint=None,
                runs=[], _undo=[], _redo=[], _portable_layer='ACKNOWLEDGED_INPUT',
                session_id=original.get('session_id'))
            self._add(identifier, 'document.json', payload=snapshot_bytes(doc), revision=revision)
            self._add(identifier, 'owner-receipt.json', path, archive_only=True, revision=revision)
            self.history_documents[key] = doc
        return deepcopy(self.history_documents[key])

    def revision(self, identifier, revision):
        if revision == WORKING:
            return self.working(identifier)
        if revision.startswith(HISTORY):
            return self.history_input(identifier, revision[len(HISTORY):])
        return super().revision(identifier, revision)

    def matching_input(self, identifier, input_revision, digest, generation=None):
        for (did, rev), doc in sorted(self._revisions.items()):
            if ((did, rev) in self.archive_folders and did == identifier
                    and doc['input_revision'] == input_revision and canonical_hash(doc['draft']) == digest
                    and (generation is None or doc['generation'] == generation)):
                return deepcopy(doc)
        try:
            return super().matching_input(identifier, input_revision, digest, generation)
        except FileNotFoundError:
            if identifier not in self.included:
                if identifier not in self.recovery_inputs:
                    raise
                prior = self.history_input(identifier, input_revision)
                if (canonical_hash(prior['draft']) != digest or
                        generation is not None and prior['generation'] != generation):
                    raise ValueError('Recovery acknowledged input differs from exact owner receipt')
                return prior
            current = self.working(identifier)
            if (current['input_revision'] == input_revision and canonical_hash(current['draft']) == digest
                    and (generation is None or current['generation'] == generation)):
                current['saved_revision'] = WORKING
                return current
            prior = super().acknowledged_input(identifier, input_revision, digest, generation)
            if is_acknowledged_container(prior):
                return prior
            return self.history_input(identifier, input_revision)

    def job(self, document, run):
        revision = run.get('retained_record', {}).get('revision')
        if (document['id'], revision) in self.archive_folders:
            folder = self.revision_folder(document['id'], revision)
            job = json_file(inside(folder, 'jobs/' + check_id(run['job_id']) + '.json'))
            if (job['id'] != run['job_id'] or job['operation'] != run['operation']
                    or job['arguments'] != run['arguments']):
                raise ValueError('Q retained job differs from its acknowledged run')
            return job
        if run.get('retained_record', {}).get('revision') == WORKING:
            self.working(document['id'])
            return deepcopy(self.live_jobs[(document['id'], run['job_id'])])
        return super().job(document, run)

    def result(self, document, run, *, metadata_only=False):
        revision = run.get('retained_result', {}).get('revision')
        if (document['id'], revision) in self.archive_folders:
            folder = self.revision_folder(document['id'], revision) / 'results' / check_id(run['job_id'])
            return read_result(folder, verify='all', selection={'metadata_only': True} if metadata_only else None)
        if document['id'] in self.included:
            self.working(document['id'])
            folder = self.live_results.get((document['id'], run['job_id']))
            if folder is not None:
                return read_result(folder, verify='all', selection={'metadata_only': True} if metadata_only else None)
        return super().result(document, run, metadata_only=metadata_only)
