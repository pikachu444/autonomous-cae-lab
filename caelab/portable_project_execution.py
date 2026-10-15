"""Checked execution identity for portable Numerical history.

The document/run exposed for editing uses the new owner IDs. Immutable fit
inputs, detail contexts, candidate snapshots and results retain execution IDs.
This module proves that relationship; it never evaluates, submits, saves an
owner or supplies command authority. The read facet has ONLY read/result.

Proof files are ordinary declared assets of existing Numerical revisions. Each
copy appends a typed projection step and retains the original input/job bytes.
There is no path fallback to an origin store and no mutable/global ID registry.
"""
from __future__ import annotations
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

from .connection_graph_refs import TypedReference, draft_references, replace_at
from .evaluation import file_hash
from .portable_project_io import inside, json_file, copy_verified, fingerprint_file
from .storage import canonical_hash, check_id, save_json, revision_read_scope

SCHEMA = 'caelab.portable-execution/1'
MAP_SCHEMA = 'caelab.portable-execution-map/1'
LINK_SCHEMA = 'caelab.portable-execution-link/1'
MAX_HOPS = 32
# Retention locations change during an ordinary owner.save, not execution.
_LOCATION = {'retained_record', 'retained_result', 'retained_state', 'retained_error',
             'retention_complete', 'is_current_input', 'portable_origin', 'portable_execution', 'portable_execution_read'}


def _error(message):
    from .numerical_candidate_detail import DetailIdentityError
    raise DetailIdentityError('Portable execution identity: ' + message)


def logical_run(run):
    return {k: deepcopy(v) for k, v in run.items() if k not in _LOCATION}


def _ref(path, digest):
    return {'file': path, 'sha256': digest}


def _read_asset(folder, ref):
    if not isinstance(ref, dict) or set(ref) != {'file', 'sha256'}:
        _error('invalid declared proof asset')
    if not str(ref['file']).startswith('portable_execution/'):
        _error('proof asset is outside its retained execution folder')
    path = inside(folder, ref['file'])
    if file_hash(path) != ref['sha256']:
        _error('retained proof bytes changed: ' + str(path))
    return json_file(path)


class TypedProjection:
    """Replay only the existing declared owner reference paths, never strings."""
    def __init__(self, value):
        if (not isinstance(value, dict) or set(value) != {'schema', 'source_scope', 'target_scope', 'documents', 'inputs', 'revisions'}
                or value.get('schema') != MAP_SCHEMA
                or any(not isinstance(value.get(k), list) for k in ('documents', 'inputs', 'revisions'))
                or not all(isinstance(value.get(k), str) and value[k] for k in ('source_scope', 'target_scope'))):
            _error('unknown or malformed mapping schema')
        self.value = value
        self.docs = {r['source_document_id']: r for r in value['documents']}
        self.inputs = {(r['source_document_id'], r['source_input_revision']): r for r in value['inputs']}
        self.revisions = {(r['source_document_id'], r['source_revision']): r['revision'] for r in value['revisions']}
        if (len(self.docs) != len(value['documents']) or len(self.inputs) != len(value['inputs'])
                or len(self.revisions) != len(value['revisions'])
                or len({r['document_id'] for r in value['documents']}) != len(self.docs)
                or len({r['input_revision'] for r in value['inputs']}) != len(self.inputs)):
            _error('duplicate/cross-owner mapping')
        for old, row in self.docs.items():
            check_id(old); check_id(row['document_id'])
            if old[0] != row['document_id'][0] or row['kind'] not in {'data', 'material', 'numerical', 'report', 'study', 'expert', 'pde', 'simulation'}:
                _error('mapping changed owner kind')
        for (doc, revision), row in self.inputs.items():
            if row['document_id'] != self.docs[doc]['document_id']:
                _error('input belongs to another mapped document')
            if canonical_hash(row['source_draft']) != row['source_input_sha256']:
                _error('source input/map hash differs')
            check_id(revision); check_id(row['input_revision'])
        self.hashes, self.busy = {}, set()

    def input_hash(self, doc, revision):
        key = (doc, revision)
        if key not in self.hashes:
            if key in self.busy or key not in self.inputs:
                _error('cyclic or absent exact input mapping')
            self.busy.add(key)
            try:
                row = self.inputs[key]
                digest = canonical_hash(self.draft(doc, row['source_draft']))
                if digest != row['input_sha256']:
                    _error('typed projection does not produce the recorded input hash')
                self.hashes[key] = digest
            finally:
                self.busy.remove(key)
        return self.hashes[key]

    def reference(self, typed):
        ref, doc = deepcopy(typed.value), typed.document_id
        if ref.get('kind') == 'knowledge':
            return ref
        if ref.get('paper_id') and not doc:
            from .portable_research_knowledge import evidence_pin
            return evidence_pin(ref)
        if doc not in self.docs:
            _error('reference targets an unselected owner')
        key = ('discussion_id' if ref.get('kind') == 'expert_turn' else
               {'adoption': 'plan_id', 'proposal': 'discussion_id', 'pde': 'pde_document_id'}.get(typed.form, 'document_id'))
        ref[key] = self.docs[doc]['document_id']
        revkey = 'plan_revision' if typed.form == 'adoption' else 'saved_revision'
        if revkey in ref:
            ref[revkey] = self.revisions[(doc, ref[revkey])]
        if 'input_revision' in ref and not (ref.get('kind') == 'result' and self.docs[doc]['kind'] == 'expert'):
            old = ref['input_revision']
            row = self.inputs[(doc, old)]
            if 'input_sha256' in ref and ref['input_sha256'] != row['source_input_sha256']:
                _error('typed source input hash differs from retained source input')
            ref['input_revision'] = row['input_revision']
            if 'input_sha256' in ref:
                ref['input_sha256'] = self.input_hash(doc, old)
            if typed.form == 'material_input':
                if canonical_hash(ref['draft']) != row['source_input_sha256']:
                    _error('Material binding substituted another draft')
                ref['draft'] = self.draft(doc, ref['draft'])
        return ref

    def draft(self, doc, value):
        result = deepcopy(value)
        for typed in draft_references(self.docs[doc]['kind'], value):
            if self.docs[doc]['kind'] == 'report':
                from .portable_project_report import can_navigate
                if not can_navigate(typed.value, self.docs):
                    continue
            replace_at(result, typed.path, self.reference(typed))
        from .portable_research_owner import current_draft
        return current_draft(self.docs[doc]['kind'], result)

    def arguments(self, value):
        result = deepcopy(value)
        # Only fit/detail's actual inline experiment contract. Frozen raw input
        # files are retained by Data, never read from a submitted path here.
        for i, experiment in enumerate(value.get('experiments', [])):
            if not isinstance(experiment, dict):
                continue
            for path in [('source',), ('observation_source', 'data_source')]:
                original = experiment
                for field in path:
                    original = original.get(field) if isinstance(original, dict) else None
                if isinstance(original, dict) and 'document_id' in original:
                    replace_at(result, ('experiments', i, *path),
                               self.reference(TypedReference((), '원실행 관측', 'observation', original)))
        return result

    def run(self, doc, value):
        result = logical_run(value)
        original_input = value['input_revision']
        if canonical_hash(value['draft']) != value['input_sha256']:
            _error('source run Plan hash changed')
        row = self.inputs[(doc, original_input)]
        if value['input_sha256'] != row['source_input_sha256']:
            _error('run and mapping have different original inputs')
        result.update(draft=self.draft(doc, value['draft']), input_revision=row['input_revision'],
                      input_sha256=self.input_hash(doc, original_input), arguments=self.arguments(value['arguments']))
        return result


def transfer_map(fork):
    value = {'schema': MAP_SCHEMA, 'source_scope': fork.execution_source_scope,
        'target_scope': fork.project_id,
        'documents': [{'source_document_id': old, 'document_id': new,
            'kind': next(r['kind'] for r in fork.plan['documents'] if r['document_id'] == old)}
            for old, new in sorted(fork.documents.items())],
        'inputs': [{'source_document_id': doc, 'source_input_revision': rev,
            'document_id': fork.documents[doc], 'input_revision': fork.input_ids[(doc, rev)],
            'source_draft': deepcopy(draft), 'source_input_sha256': canonical_hash(draft),
            'input_sha256': fork.input_hash(doc, rev)} for (doc, rev), draft in sorted(fork.inputs.items())],
        'revisions': [{'source_document_id': doc, 'source_revision': rev, 'revision': new}
            for (doc, rev), new in sorted(fork.revisions.items())]}
    projection = TypedProjection(value)
    for doc, rev in projection.inputs:
        projection.input_hash(doc, rev)
    return value


def _put_json(folder, category, value):
    name = f'portable_execution/{category}/H{canonical_hash(value)}.json'
    path = inside(folder, name, must_exist=False)
    if path.exists():
        if json_file(path) != value:
            _error('immutable proof collision')
    else:
        save_json(path, value)
    return _ref(name, file_hash(path))


def _put_original(folder, category, source):
    identity = fingerprint_file(source)
    name = f'portable_execution/{category}/H{identity["sha256"]}.json'
    destination = inside(folder, name, must_exist=False)
    if not destination.exists():
        copy_verified(source, destination, identity)
    elif file_hash(destination) != identity['sha256']:
        _error('original byte collision')
    return _ref(name, identity['sha256'])


def proof_assets(proof):
    return [proof['origin']['input'], proof['origin']['job'], *[hop['mapping'] for hop in proof['hops']]]


def replay_proof(folder, link, document_id, run, *, expected_scope=None):
    if not isinstance(link, dict) or set(link) != {'schema', 'file', 'sha256'} or link['schema'] != LINK_SCHEMA:
        _error('missing/invalid execution link')
    proof = _read_asset(folder, {k: link[k] for k in ('file', 'sha256')})
    if (not isinstance(proof, dict) or set(proof) != {'schema', 'origin', 'hops'}
            or proof.get('schema') != SCHEMA or not isinstance(proof.get('hops'), list)
            or not 1 <= len(proof['hops']) <= MAX_HOPS):
        _error('unknown or excessive projection history')
    origin = proof['origin']
    if not isinstance(origin, dict) or set(origin) != {'scope', 'document_id', 'input', 'job', 'result_sha256'}:
        _error('malformed original execution declaration')
    raw = _read_asset(folder, origin['input'])
    job = _read_asset(folder, origin['job'])
    execution = logical_run(raw)
    if (execution['job_id'] != job.get('id') or execution['operation'] != job.get('operation')
            or execution['arguments'] != job.get('arguments')
            or canonical_hash(execution['draft']) != execution['input_sha256']):
        _error('original job/input receipt does not agree')
    if job['state'] not in {'SUCCEEDED', 'FAILED', 'CANCELLED', 'INTERRUPTED', 'REJECTED', 'PARTIAL_FAILURE'}:
        _error('original execution is not terminal')
    doc, scope, projected = origin['document_id'], origin['scope'], execution
    for hop in proof['hops']:
        mapping = _read_asset(folder, hop['mapping'])
        transform = TypedProjection(mapping)
        if (mapping['source_scope'] != scope or hop['source_document_id'] != doc
                or hop['source_run_sha256'] != canonical_hash(projected)):
            _error('projection source belongs to another store/document/run')
        before_projection = deepcopy(projected)
        projected = transform.run(doc, projected)
        doc = transform.docs[doc]['document_id']
        scope = mapping['target_scope']
        if hop['document_id'] != doc or hop['run_sha256'] != canonical_hash(projected):
            _error('projection target differs from its declared typed transformation')
    if doc != document_id or logical_run(run) != projected or (expected_scope is not None and scope != expected_scope):
        _error('current run/owner/store is not this projection')
    if (not run.get('retention_complete') or run.get('retained_state') != job['state']
            or run.get('retained_error') != job.get('error')):
        _error('current retained status/error differs from original execution')
    # The old C1 informational marker is not authority, but contradictions in it
    # are not silently ignored either.
    marker = run.get('portable_origin', {})
    previous = proof['hops'][-1]
    expected_marker = {'document_id': previous['source_document_id'], 'job_id': before_projection['job_id'],
        'input_revision': before_projection['input_revision'], 'input_sha256': before_projection['input_sha256'],
        'arguments_sha256': canonical_hash(before_projection['arguments']), 'execution_replayed': False}
    if marker != expected_marker:
        _error('origin marker contradicts the checked proof')
    return proof, execution


def load_execution(owner, document_id, run):
    storage = getattr(owner, '_portable_storage_owner', owner)
    retained = run.get('retained_record')
    if not retained or retained.get('job_id') != run['job_id']:
        _error('execution has no exact retained owner record')
    revision = check_id(retained['revision'])
    saved = storage._verify_revision(document_id, revision)
    declared = next((r for r in saved.get('runs', []) if r['job_id'] == run['job_id']), None)
    if (saved.get('id') != document_id or saved.get('saved_revision') != revision
            or declared is None or declared.get('portable_execution') != run.get('portable_execution')
            or logical_run(declared) != logical_run(run)):
        _error('current execution link is not declared by this exact retained owner')
    folder = storage._folder(document_id) / 'revisions' / revision
    proof, original = replay_proof(folder, run.get('portable_execution'), document_id, run)
    return folder, proof, original


def write_execution(fork, identifier, revision, original, projected, folder, *, operations=('fit', 'detail_eval')):
    """Retain original bytes; each domain explicitly admits its own operations."""
    if original['operation'] not in operations:
        return
    old_link = original.get('portable_execution')
    if old_link:
        source_folder, old_proof, execution = load_execution(fork.reader.owner(identifier), identifier, original)
        proof = deepcopy(old_proof)
        if len(proof['hops']) >= MAX_HOPS:
            _error('maximum explicit copy lineage reached')
        # Every reference is individually hashed; never crawl another store.
        for ref in proof_assets(proof):
            source = inside(source_folder, ref['file'])
            target = inside(folder, ref['file'], must_exist=False)
            if not target.exists():
                copy_verified(source, target, fingerprint_file(source))
    else:
        if original.get('portable_origin'):
            _error('legacy C1 run has no verified execution proof; select its preserved original store')
        retained = original.get('retained_record')
        if not retained:
            _error('copy requires a retained terminal input and job record')
        archive = fork.stage / 'portable/originals' / identifier / retained['revision']
        input_ref = _put_original(folder, 'inputs', inside(archive, 'inputs/' + check_id(original['job_id']) + '.json'))
        job_ref = _put_original(folder, 'jobs', inside(archive, 'jobs/' + original['job_id'] + '.json'))
        result_digest = None
        if original.get('retained_result'):
            from .numerical_candidate_detail import plain
            result_digest = canonical_hash(plain(fork.reader.result(fork.snapshots[(identifier, revision)], original)))
        proof = {'schema': SCHEMA, 'origin': {'scope': fork.execution_source_scope, 'document_id': identifier,
            'input': input_ref, 'job': job_ref, 'result_sha256': result_digest}, 'hops': []}
    mapping = transfer_map(fork)
    map_ref = _put_json(folder, 'maps', mapping)
    expected = TypedProjection(mapping).run(identifier, original)
    if expected != logical_run(projected):
        _error('copy writer and typed execution projection disagree')
    proof['hops'].append({'source_document_id': identifier, 'document_id': fork.documents[identifier],
        'source_run_sha256': canonical_hash(logical_run(original)), 'run_sha256': canonical_hash(expected), 'mapping': map_ref})
    proof_ref = _put_json(folder, 'proofs', proof)
    projected['portable_execution'] = {'schema': LINK_SCHEMA, **proof_ref}
    replay_proof(folder, projected['portable_execution'], fork.documents[identifier], projected,
                 expected_scope=fork.project_id)


def retain_execution_inputs(owner, saved, folder):
    """Existing Numerical save hook; retain declared proof/history bytes only."""
    for run in saved.get('runs', []):
        if not run.get('portable_execution'):
            continue
        source_folder, proof, _ = load_execution(owner, saved['id'], run)
        refs = [{k: run['portable_execution'][k] for k in ('file', 'sha256')}, *proof_assets(proof)]
        for ref in refs:
            source = inside(source_folder, ref['file'])
            destination = inside(folder, ref['file'], must_exist=False)
            if not destination.exists():
                copy_verified(source, destination, {'sha256': ref['sha256'], 'bytes': source.stat().st_size})
    for ref in saved.get('portable_capture_history', []):
        owner._verify_revision(saved['id'], ref['revision'])
        source = inside(owner._folder(saved['id']) / 'revisions' / ref['revision'], ref['file'])
        copy_verified(source, inside(folder, ref['file'], must_exist=False),
                      {'sha256': ref['sha256'], 'bytes': source.stat().st_size})
        ref['revision'] = folder.name


@dataclass
class ExecutionRead:
    reader: object
    source: dict
    execution_source: dict
    document: dict
    original_run: dict
    scope: str


@revision_read_scope()
def execution_read(owner, document_id, job_id):
    """Read-only facet over the *same* owner/results; no command/session proxy."""
    if getattr(owner, '_portable_execution_view', False):
        return None
    document = owner.read(check_id(document_id))
    selected = next((r for r in document.get('runs', []) if r['job_id'] == job_id), None)
    if selected is None or not selected.get('portable_execution'):
        return None
    from .numerical_candidate_detail import plain
    _, source_proof, source_run = _read_projection(owner, document_id, selected)
    origin = source_proof['origin']
    results = {}
    original_runs = []
    for run in document['runs']:
        if not run.get('portable_execution'):
            # Native new fits retain native identities. They cannot impersonate
            # another copied fit just because candidate IDs happen to coincide.
            continue
        _, proof, original = _read_projection(owner, document_id, run)
        if (proof['origin']['scope'], proof['origin']['document_id']) != (origin['scope'], origin['document_id']):
            _error('one execution history mixes independent source owners/stores')
        adapted = deepcopy(original)
        adapted.update({k: deepcopy(v) for k, v in run.items() if k in _LOCATION and k not in {'portable_origin', 'portable_execution', 'portable_execution_read'}})
        original_runs.append(adapted)
        if run.get('retained_result'):
            value = owner.result(document_id, run['job_id'])
            if canonical_hash(plain(value)) != proof['origin']['result_sha256']:
                _error('original result digest changed')
            results[run['job_id']] = value
        elif proof['origin']['result_sha256'] is not None:
            _error('original result is absent from the current owner')
    if source_run.get('operation') != 'fit' or job_id not in results:
        _error('select an exact original fit result')
    digest = canonical_hash(plain(results[job_id]))
    source = {'document_id': document_id, 'job_id': job_id, 'input_revision': selected['input_revision'],
              'input_sha256': selected['input_sha256'], 'result_sha256': digest}
    exact = {'document_id': origin['document_id'], 'job_id': job_id, 'input_revision': source_run['input_revision'],
             'input_sha256': source_run['input_sha256'], 'result_sha256': digest}
    historical = deepcopy(document)
    historical.update(id=origin['document_id'], runs=original_runs)
    def read(identifier):
        if identifier != origin['document_id']:
            _error('execution read attempted another original owner')
        return deepcopy(historical)
    def result(identifier, job, **kwargs):
        if identifier != origin['document_id'] or job not in results or kwargs:
            _error('execution result selection is not in this exact history')
        return deepcopy(results[job])
    facet = SimpleNamespace(read=read, result=result, manager=None, _portable_execution_view=True)
    return ExecutionRead(facet, source, exact, document, source_run, origin['scope'])


@revision_read_scope()
def detail_view(owner, document_id, job_id, candidate_id, *, source=None, attempt_job_id=None):
    bridge = execution_read(owner, document_id, job_id)
    if bridge is None:
        return None
    if source is not None and source != bridge.source:
        _error('detail selection has another current source reference')
    from .numerical_candidate_detail import read_candidate_detail
    view = read_candidate_detail(bridge.reader, bridge.execution_source['document_id'], job_id, candidate_id,
        source=bridge.execution_source, attempt_job_id=attempt_job_id)
    view['source'] = deepcopy(bridge.source)
    view['execution_source'] = deepcopy(bridge.execution_source)
    view['identity_projection'] = {'state': 'VERIFIED', 'origin_scope': bridge.scope,
                                   'execution_replayed': False}
    return view


@revision_read_scope()
def prepare_evidence(owner, source, candidate_id, **kwargs):
    bridge = execution_read(owner, source['document_id'], source['job_id'])
    if bridge is None:
        return None
    if source != bridge.source:
        _error('evidence selection has another current input/result')
    from .numerical_candidate_evidence import prepare_candidate_evidence
    return prepare_candidate_evidence(bridge.reader, bridge.execution_source, candidate_id, **kwargs)


@revision_read_scope()
def reference_source(owner, document_id, revision, original_source):
    """Translate only a checked navigation reference, never snapshot contents."""
    if owner is None:
        if original_source['document_id'] != document_id:
            _error('portable evidence reference requires its actual owner for mapping validation')
        return deepcopy(original_source)
    from .numerical_candidate_evidence import _saved_owner
    _, historical = _saved_owner(owner, document_id, revision)
    bridge = execution_read(historical, document_id, original_source['job_id'])
    if bridge is None:
        if original_source['document_id'] != document_id:
            _error('evidence source belongs to another owner')
        return deepcopy(original_source)
    if original_source != bridge.execution_source:
        _error('evidence snapshot belongs to another original result/input/store')
    return deepcopy(bridge.source)


def adoption_run(owner, reference, run):
    if not run.get('portable_execution'):
        return run
    _, _, original = load_execution(owner, reference['document_id'], run)
    return original


def retain_snapshot_bytes(saved, source, destination):
    """Preserve CRLF/LF and the original serialization after canonical validation.

    Return False for native documents, whose existing save path is untouched.
    No content is normalized or accepted on the strength of an origin label.
    """
    if not saved.get('portable_origin'):
        return False
    copy_verified(source, destination, fingerprint_file(source))
    return True


@revision_read_scope()
def public_execution(owner, document):
    """Existing document-read transport projection; never stored in the owner.

    Remote read helpers have no filesystem authority. Supply only already
    owner-verified execution records beside current editable records. Server
    CAPTURE/adoption always rechecks real retained files and ignores this field.
    No new endpoint, body upload, command, credentials or provider is introduced.
    """
    for run in document.get('runs', []):
        if not run.get('portable_execution'):
            continue
        _, proof, original = load_execution(owner, document['id'], run)
        run['portable_execution_read'] = {
            'schema': 'caelab.portable-execution-read/1',
            'document_id': document['id'], 'current_run_sha256': canonical_hash(logical_run(run)),
            'origin_scope': proof['origin']['scope'], 'source_document_id': proof['origin']['document_id'],
            'result_sha256': proof['origin']['result_sha256'], 'original_run': deepcopy(original)}
    return document


def _read_projection(owner, document_id, run):
    if not getattr(owner, '_portable_client_read', False):
        return load_execution(owner, document_id, run)
    # This is ONLY the existing read-only client adapter, never a server owner.
    value = run.get('portable_execution_read')
    required = {'schema', 'document_id', 'current_run_sha256', 'origin_scope',
                'source_document_id', 'result_sha256', 'original_run'}
    if (not isinstance(value, dict) or set(value) != required
            or value['schema'] != 'caelab.portable-execution-read/1'
            or value['document_id'] != document_id
            or value['current_run_sha256'] != canonical_hash(logical_run(run))):
        _error('server did not supply this exact verified execution read projection')
    original = value['original_run']
    if (original['job_id'] != run['job_id'] or original['operation'] != run['operation']
            or canonical_hash(original['draft']) != original['input_sha256']):
        _error('server execution read projection has another original job/input')
    return None, {'origin': {'scope': value['origin_scope'], 'document_id': value['source_document_id'],
                             'result_sha256': value['result_sha256']}}, deepcopy(original)
