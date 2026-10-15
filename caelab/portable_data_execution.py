"""Narrow original import_table proof for current-owner Data Keep after copying.

Data's original CSV/input.json/result validators remain unchanged. This proves
only the explicit C2 storage/navigation relocation before those validators see
the ORIGINAL submitted arguments. It never supplies a job/command capability.
"""
from __future__ import annotations
from copy import deepcopy

from .portable_project_execution import (TypedProjection, transfer_map, logical_run,
    _put_json, _put_original, _read_asset, MAX_HOPS)
from .portable_project_io import inside, json_file, fingerprint_file, copy_verified
from .evaluation import file_hash, read_result
from .storage import canonical_hash, check_id
from .jobs import TERMINAL

SCHEMA = 'caelab.portable-data-import/1'


def logical(run):
    return {k: v for k, v in logical_run(run).items() if k != 'portable_data_execution'}


def _arguments(projection, original, claimed):
    result = deepcopy(original)
    def source(old, new):
        if not isinstance(old, dict) or old.get('kind') not in {'registered_input', 'retained_data_input'}:
            if old != new:
                raise ValueError('Original Data calibration/source declaration changed')
            return deepcopy(old)
        value = deepcopy(old); did = old['document_id']
        value['document_id'] = projection.docs[did]['document_id']
        if old['kind'] == 'retained_data_input':
            value['revision'] = projection.revisions[(did, old['revision'])]
            # This is an explicit STORAGE pin, not an execution hash. The final
            # pinned manifest is independently checked below and by Data C3.
            digest = new.get('revision_sha256')
            if not isinstance(digest, str) or len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
                raise ValueError('Invalid relocated Data revision manifest pin')
            value['revision_sha256'] = digest
        if value != new:
            raise ValueError('Data projection changed original bytes/receipt/physical arguments')
        return value
    if 'source_ref' in original:
        result['source_ref'] = source(original['source_ref'], claimed.get('source_ref'))
    if 'calibration_sources' in original:
        refs = claimed.get('calibration_sources')
        if not isinstance(refs, list) or len(refs) != len(original['calibration_sources']):
            raise ValueError('Data projection lost an original calibration source')
        result['calibration_sources'] = [source(a,b) for a,b in zip(original['calibration_sources'],refs)]
    if result != claimed:
        raise ValueError('Data projection changed the submitted argument contract')
    return result


def replay(folder, document_id, run, *, result_folder=None):
    link = run.get('portable_data_execution')
    if not isinstance(link, dict) or set(link) != {'schema','file','sha256'} or link['schema'] != SCHEMA:
        raise ValueError('Portable Data import requires its retained original execution proof')
    proof = _read_asset(folder, {k:link[k] for k in ('file','sha256')})
    if (proof.get('schema') != SCHEMA or set(proof) != {'schema','origin','hops'}
            or not isinstance(proof['hops'],list) or not 1 <= len(proof['hops']) <= MAX_HOPS):
        raise ValueError('Data execution proof is invalid or exceeds 32 copies')
    origin = proof['origin']
    raw, job = _read_asset(folder, origin['input']), _read_asset(folder, origin['job'])
    original = logical(raw)
    if (original.get('operation') != 'import_table' or job.get('operation') != 'import_table'
            or job.get('id') != original['job_id'] or job['arguments'] != original['arguments']
            or canonical_hash(original['draft']) != original['input_sha256'] or job['state'] not in TERMINAL):
        raise ValueError('Original Data import input/job/state are inconsistent')
    current, did, scope = original, origin['document_id'], origin['scope']
    for hop in proof['hops']:
        projection = TypedProjection(_read_asset(folder,hop['mapping']))
        if (projection.value['source_scope'] != scope or did != hop['source_document_id']
                or projection.docs[did]['kind'] != 'data' or canonical_hash(current) != hop['source_run_sha256']):
            raise ValueError('Data execution navigation crossed another owner/store/run')
        target = logical(hop['run'])
        expected = deepcopy(current)
        mapped = projection.inputs[(did,current['input_revision'])]
        if canonical_hash(current['draft']) != mapped['source_input_sha256']:
            raise ValueError('Original Data input and typed mapping differ')
        expected.update(draft=projection.draft(did,current['draft']), input_revision=mapped['input_revision'],
                        input_sha256=projection.input_hash(did,current['input_revision']),
                        arguments=_arguments(projection,current['arguments'],target['arguments']))
        if target != expected:
            raise ValueError('Data execution projection changed an original run field')
        did,scope,current = projection.docs[did]['document_id'],projection.value['target_scope'],target
    if (did != document_id or current != logical(run) or not run.get('retention_complete')
            or run.get('retained_state') != job['state'] or run.get('retained_error') != job.get('error')):
        raise ValueError('Current Data run/status is not the original import projection')
    refs = [run['arguments'].get('source_ref'), *run['arguments'].get('calibration_sources',[])]
    for ref in refs:
        if isinstance(ref,dict) and ref.get('kind') == 'retained_data_input':
            if ref['document_id'] != document_id:
                raise ValueError('Relocated Data source belongs to another current owner')
            # folder = this actual existing owner's revisions/R... directory.
            manifest = inside(folder.parent, check_id(ref['revision']) + '/revision.json')
            if file_hash(manifest) != ref['revision_sha256']:
                raise ValueError('Relocated Data source revision pin changed')
    if result_folder is not None:
        if origin['result_file_sha256'] is None or file_hash(inside(result_folder,'result.json')) != origin['result_file_sha256']:
            raise ValueError('Original import result bytes changed')
        read_result(result_folder,verify='all',selection={'metadata_only':True})
    return proof, original


def load(owner, document_id, run, *, result_folder=None):
    retained = run['retained_record']; rev = check_id(retained['revision'])
    saved = owner._verify_revision(document_id,rev)
    declared = next((r for r in saved.get('runs',[]) if r['job_id']==run['job_id']),None)
    if (saved['id'] != document_id or declared is None or logical(declared) != logical(run)
            or declared.get('portable_data_execution') != run.get('portable_data_execution')):
        raise ValueError('Data execution proof is not declared by this exact saved owner')
    folder = owner._folder(document_id)/'revisions'/rev
    proof, original = replay(folder,document_id,run,result_folder=result_folder)
    return folder,proof,original


def assets(proof):
    return [proof['origin']['input'],proof['origin']['job'],*[h['mapping'] for h in proof['hops']]]


def write(fork, identifier, revision, original, projected, folder):
    if original.get('operation') != 'import_table':
        raise ValueError('Data archive supports its actual import_table execution only')
    if original.get('portable_data_execution'):
        source_folder, proof, _ = load(fork.reader.owner(identifier),identifier,original)
        proof = deepcopy(proof)
        if len(proof['hops']) >= MAX_HOPS:
            raise ValueError('Data original execution exceeded 32 copies')
        for ref in assets(proof):
            target = inside(folder,ref['file'],must_exist=False)
            if not target.exists():
                source = inside(source_folder,ref['file'])
                copy_verified(source,target,fingerprint_file(source))
    else:
        if original.get('portable_origin'):
            raise ValueError('Legacy C2 Data copy has no original import proof for new Keep; retain/read its archive without resuming')
        retained = original['retained_record']
        archive = fork.stage/'portable/originals'/identifier/retained['revision']
        jid = check_id(original['job_id'])
        result_hash = None
        if original.get('retained_result'):
            base = fork.stage/'portable/originals'/identifier/original['retained_result']['revision']
            result_hash = file_hash(inside(base,'results/'+jid+'/result.json'))
        proof = {'schema':SCHEMA,'origin':{'scope':fork.execution_source_scope,'document_id':identifier,
            'input':_put_original(folder,'data-inputs',inside(archive,'inputs/'+jid+'.json')),
            'job':_put_original(folder,'data-jobs',inside(archive,'jobs/'+jid+'.json')),
            'result_file_sha256':result_hash},'hops':[]}
    mapping = _put_json(folder,'data-maps',transfer_map(fork))
    proof['hops'].append({'source_document_id':identifier,'source_run_sha256':canonical_hash(logical(original)),
                         'mapping':mapping,'run':logical(projected)})
    projected['portable_data_execution'] = {'schema':SCHEMA,**_put_json(folder,'data-proofs',proof)}
    # Current source revisions are already written by fork.arguments.
    replay(folder,fork.documents[identifier],projected)


def retain(owner, saved, folder):
    for run in saved.get('runs',[]):
        if not run.get('portable_data_execution'):
            continue
        source_folder,proof,_ = load(owner,saved['id'],run)
        refs = [{k:run['portable_data_execution'][k] for k in ('file','sha256')},*assets(proof)]
        for ref in refs:
            source = inside(source_folder,ref['file']);target = inside(folder,ref['file'],must_exist=False)
            if not target.exists():
                copy_verified(source,target,{'sha256':ref['sha256'],'bytes':source.stat().st_size})


def original_for_capture(owner, document, run, result_folder):
    return load(owner,document['id'],run,result_folder=result_folder)[2]


def original_for_archive(asset_folder, document, run, result_folder):
    folder = inside(asset_folder, 'documents/'+check_id(document['id'])+'/revisions/'+
                    check_id(run['retained_record']['revision']),must_exist=False)
    return replay(folder,document['id'],run,result_folder=result_folder)[1]
