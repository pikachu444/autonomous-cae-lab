"""Verify relocation of a published processing record; keep channel lineage original."""
from copy import deepcopy

from .connection_graph_refs import TypedReference
from .evaluation import file_hash
from .portable_project_execution import TypedProjection, transfer_map, _put_json, _read_asset, MAX_HOPS
from .portable_project_io import inside, fingerprint_file, copy_verified
from .storage import canonical_hash, check_id

SCHEMA='caelab.portable-data-processing/1'
SOURCE=('document_id','job_id','input_revision','input_sha256')


def logical(record):
    return {k:deepcopy(v) for k,v in record.items() if k not in {'retained_revision','portable_processing'}}


def project(projection, identifier, record):
    value=logical(record)
    entry=projection.inputs[(identifier,record['input_revision'])]
    if entry['source_input_sha256']!=record['input_sha256']:
        raise ValueError('Processing input differs from the exact relocation map')
    value.update(input_revision=entry['input_revision'],input_sha256=projection.input_hash(identifier,record['input_revision']))
    value['source']=projection.reference(TypedReference((),'처리 원자료','result',record['source']))
    return value


def source(document, record, retained, base, revision_folder):
    """Return the verified ORIGINAL compiler identity, never a diagnostic flag."""
    current=record['source']
    run=next((r for r in document.get('runs',[]) if r['job_id']==current['job_id']),None)
    if (run is None or current['document_id']!=document['id'] or
            any(run[k]!=current[k] for k in ('input_revision','input_sha256'))):
        raise ValueError('Processing source differs from this owner import')
    link=record.get('portable_processing')
    if not link:
        if any(retained['source'].get(k)!=current[k] for k in SOURCE):
            raise ValueError('Processing result and original import identity differ')
        return deepcopy(current)
    if not isinstance(link,dict) or set(link)!={'schema','file','sha256'} or link['schema']!=SCHEMA:
        raise ValueError('Invalid processing relocation link')
    proof=_read_asset(base,{k:link[k] for k in ('file','sha256')})
    if (set(proof)!={'schema','origin','hops'} or proof['schema']!=SCHEMA or
            not isinstance(proof['hops'],list) or not 1<=len(proof['hops'])<=MAX_HOPS):
        raise ValueError('Invalid or excessive processing relocation history')
    origin=proof['origin']; previous=origin['record']; identifier=origin['document_id']; scope=origin['scope']
    if any(retained['source'].get(k)!=previous['source'][k] for k in SOURCE):
        raise ValueError('Original processing bytes have a different import identity')
    for hop in proof['hops']:
        projection=TypedProjection(_read_asset(base,hop['mapping']))
        if (projection.value['source_scope']!=scope or hop['source_document_id']!=identifier or
                canonical_hash(previous)!=hop['source_record_sha256']):
            raise ValueError('Processing history crosses another source or owner')
        previous=project(projection,identifier,previous)
        identifier=projection.docs[identifier]['document_id']; scope=projection.value['target_scope']
    if identifier!=document['id'] or previous!=logical(record):
        raise ValueError('Published processing record differs from exact relocation')
    from .portable_data_execution import replay
    raw_base=revision_folder(run['retained_record']['revision'])
    raw_result=revision_folder(run['retained_result']['revision'])/'results'/check_id(run['job_id'])
    imported,raw=replay(raw_base,document['id'],run,result_folder=raw_result)
    original_source=origin['record']['source']
    # A new P may be authored after a copy. Match its creation point in the
    # fully verified import chain, rather than assuming the first raw owner.
    identities=[(imported['origin']['scope'],{'document_id':imported['origin']['document_id'],
        'job_id':raw['job_id'],'input_revision':raw['input_revision'],'input_sha256':raw['input_sha256']})]
    for hop in imported['hops']:
        projection=TypedProjection(_read_asset(raw_base,hop['mapping']))
        mapped=hop['run']
        identities.append((projection.value['target_scope'],{
            'document_id':projection.docs[hop['source_document_id']]['document_id'],
            **{k:mapped[k] for k in ('job_id','input_revision','input_sha256')}}))
    if (not any(scope==origin['scope'] and all(value[k]==original_source[k] for k in SOURCE)
                for scope,value in identities) or record['result_sha256']!=origin['record']['result_sha256']):
        raise ValueError('Processing proof differs from its original import execution')
    return deepcopy(original_source)


def input_draft(reader, document, record):
    """Recover only the exact published P input, including after later edits."""
    wanted=record['input_revision']; digest=record['input_sha256']
    drafts=[(document['input_revision'],document['draft']),
            *((r['input_revision'],r['draft']) for r in document.get('runs',[]))]
    for revision,draft in drafts:
        if revision==wanted and canonical_hash(draft)==digest:return deepcopy(draft)
    if record.get('portable_processing'):
        base=reader.processing_folder(document,record).parent.parent
        link=record['portable_processing']; proof=_read_asset(base,{k:link[k] for k in ('file','sha256')})
        hop=proof['hops'][-1]; projection=TypedProjection(_read_asset(base,hop['mapping']))
        candidates=[row for row in projection.inputs.values() if
            row['document_id']==document['id'] and row['input_revision']==wanted]
        if len(candidates)!=1:raise ValueError('Processing input is not uniquely retained in its map')
        row=candidates[0]
        draft=projection.draft(hop['source_document_id'],row['source_draft'])
    else:
        from .portable_project_io import json_file
        path=reader.owner(document['id'])._folder(document['id'])/'commands'/(check_id(record['command_id'])+'.json')
        command=json_file(path)
        response=command.get('response',{}); published=response.get('document',{})
        generation=published.get('generation')
        if type(generation) is not int or generation<1:
            raise ValueError('Processing input has no completed owner generation')
        signature=canonical_hash(dict(document_id=document['id'],operation='data.processing.apply',
            arguments={'preview_sha256':record['preview_sha256']},session_id=published.get('session_id'),
            expected_generation=generation-1))
        if (command.get('request_hash')!=signature or response.get('command_id')!=record['command_id'] or
                published.get('id')!=document['id'] or published.get('kind')!='data' or
                published.get('input_revision')!=wanted or
                logical(response.get('processing',{}))!=logical(record) or
                not any(logical(row)==logical(record) for row in published.get('processing_revisions',[]))):
            raise ValueError('Processing input has no exact completed owner receipt')
        draft=published['draft']
    if canonical_hash(draft)!=digest:raise ValueError('Processing input draft hash differs')
    return deepcopy(draft)


def write(fork, identifier, revision, original, document, folder):
    """Keep exact processing bytes and append the existing typed transfer map."""
    if not original.get('processing_revisions'):return
    mapping=transfer_map(fork); projection=TypedProjection(mapping)
    for index,record in enumerate(original['processing_revisions']):
        # This also verifies the original published record, channel assets and raw import.
        fork.reader.processing(original,record['id'])
        source_folder=fork.reader.processing_folder(original,record)
        base=source_folder.parent.parent
        if record.get('portable_processing'):
            link=record['portable_processing']
            proof=deepcopy(_read_asset(base,{k:link[k] for k in ('file','sha256')}))
            if len(proof['hops'])>=MAX_HOPS:raise ValueError('Processing relocation exceeds 32 copies')
            for hop in proof['hops']:
                ref=hop['mapping']; target=inside(folder,ref['file'],must_exist=False)
                if not target.exists():
                    original_asset=inside(base,ref['file'])
                    copy_verified(original_asset,target,fingerprint_file(original_asset))
        else:
            proof={'schema':SCHEMA,'origin':{'scope':fork.execution_source_scope,
                'document_id':identifier,'record':logical(record)},'hops':[]}
        # Storage may be re-retained here; original result/array bytes are unchanged.
        prefix='processing/'+check_id(record['id'])+'/'
        old_revision=record.get('retained_revision')
        for entry in fork.plan['files']:
            if (entry['document_id']==identifier and entry['saved_revision']==old_revision
                    and entry['asset'].startswith(prefix) and not entry.get('archive_only')):
                target=inside(folder,entry['asset'],must_exist=False)
                if not target.exists():fork.copy_entry(entry,target)
        if file_hash(inside(folder,prefix+'result.json'))!=record['result_sha256']:
            raise ValueError('Processing bytes changed during relocation')
        projected=project(projection,identifier,record)
        proof['hops'].append({'source_document_id':identifier,
            'source_record_sha256':canonical_hash(logical(record)),
            'mapping':_put_json(folder,'data-processing-maps',mapping)})
        projected['retained_revision']=fork.revisions[(identifier,revision)]
        projected['portable_processing']={'schema':SCHEMA,**_put_json(folder,'data-processing',proof)}
        document['processing_revisions'][index]=projected


def retain(owner, saved, destination):
    """A later ordinary Data Save keeps its exact proof assets with each result."""
    for record in saved.get('processing_revisions',[]):
        if not record.get('portable_processing'):continue
        base=owner._folder(saved['id'])/'revisions'/check_id(record['retained_revision'])
        link=record['portable_processing']
        proof=_read_asset(base,{k:link[k] for k in ('file','sha256')})
        for ref in [link,*[hop['mapping'] for hop in proof['hops']]]:
            source_path=inside(base,ref['file']); target=inside(destination,ref['file'],must_exist=False)
            if not target.exists():copy_verified(source_path,target,fingerprint_file(source_path))
