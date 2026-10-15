"""Native branch of the EXISTING portable transaction and explicit opener.

File-only stages use copy_verified. Native adapters alone materialize/load native
projects. Original source inventory and the current saved head remain distinct.
"""
from copy import deepcopy
from dataclasses import dataclass,field,replace
from pathlib import Path
import uuid

from .storage import canonical_hash,check_id,save_json
from .portable_project_io import inside,json_file,copy_verified,fingerprint_file,relative_name,no_links
from .native_project_contract import (CONTRACT,OpenBinding,NativeOpenTicket,_SEAL,_need,_keys,
    validate_native_reference,validate_snapshot,snapshot_reference,project_native_reference,require_verified_input)
from .native_project_inputs import (NativeOnlyContext,_require_context,verify_registered,register_saved,_head_publication)

FORMAT='caelab.portable-project/2'


def native_context(value):
    if type(value) is NativeOnlyContext:return _require_context(value)
    from .native_project_inputs import context_from_workbench
    return context_from_workbench(value)


def inspect_union(value,selections,*,research_inspector,draft_policy,recovery_archives):
    """Native selection admission; research inspection remains owned by its owner."""
    _need(isinstance(selections,list) and 1<=len(selections)<=128,'Select 1–128 saved documents')
    native=[s for s in selections if isinstance(s,dict) and 'native' in s]
    research=[s for s in selections if not (isinstance(s,dict) and 'native' in s)]
    if research:
        _need(type(value) is not NativeOnlyContext,'연구 문서는 기존 연구 연결에서 선택하세요. Native 파일 사본은 연구 실행기를 만들지 않습니다.')
        result=research_inspector(value,research,draft_policy=draft_policy,recovery_archives=recovery_archives)
        if result.get('status')!='READY':return result
    else:
        _need(draft_policy in {'acknowledged','saved_only'},'Unknown draft policy')
        _need(not recovery_archives,'Recovery archives require an explicitly selected research owner')
        result={'format':'caelab.portable-project/1','status':'READY','view_state':None,
            'service_session_id':value.session_id,'selections':[],'documents':[],
            'draft_policy':draft_policy,'capsule_boundary':None,
            'recovery_selections':[],'recovery_archives':[],'recovery_files':[],
            'source_store':str(value.workspace),'pins':[],'files':[],'knowledge':[],'literature':[],
            'revisions':[],'bytes_to_copy':0,'warnings':[],'issues':[],
            'executed':False,'engineering_release':'NOT_RELEASED'}
    refs=result.pop('_native_references',[])
    if native or refs:
        collected=collect_native_references(native_context(value),refs,native)
        result.update(format=FORMAT,native_contract=CONTRACT,native_inspections=collected['inspections'],
            native_selections=[{'native':r['reference'],'copy_intent':r['copy_intent'],'working_target':r['working_target']} for r in collected['selections']])
        result['bytes_to_copy']+=2*sum(i['total_bytes'] for i in collected['inspections'])
        from .portable_project_io import MAX_BYTES,MAX_FILES
        _need(result['bytes_to_copy']<=MAX_BYTES,'Native and research inventory exceeds the existing byte limit')
        _need(len(result['files'])*2+sum(len(i['files'])*2+4 for i in collected['inspections'])<=MAX_FILES,'Native and research inventory exceeds the existing file limit')
    result['inspection_sha256']=_hash(result,'inspection_sha256')
    return result


def _hash(value,key):return canonical_hash({k:v for k,v in value.items() if k!=key})


def inspect_native(context,reference,*,copy_intent):
    _need(copy_intent in {'complete','preserve_declared_partial'},'Choose a known native copy intent')
    verified=verify_registered(context,reference,full=True);snapshot=verified.snapshot
    if copy_intent=='complete':
        _need(snapshot['validation']['closure']=='COMPLETE','DEPENDENCY_UNBOUND: explicitly preserve the declared partial snapshot or choose a complete saved project')
        _need(not (snapshot['native_kind']=='post' and snapshot['format']=='pvsm'),'MANAGED_SAVE_REQUIRED: save a managed ParaView project first')
        _need(not any(i['severity']=='error' for i in snapshot['validation']['issues']),'Native saved source contains an unsupported/incomplete branch')
    files=[]
    for member in snapshot['members']:
        if member['storage']=='file':
            files.append({'member_id':member['id'],'source':verified.member_paths[member['id']].relative_to(context.workspace).as_posix(),
                **{k:member[k] for k in ('relative','bytes','sha256')}})
    result={'version':1,'reference':deepcopy(verified.reference),'snapshot':deepcopy(snapshot),'copy_intent':copy_intent,
        'files':files,'bindings':[deepcopy(e) for e in snapshot['edges'] if e['child_member'] is not None],
        'issues':deepcopy(snapshot['validation']['issues']),'total_bytes':sum(row['bytes'] for row in files)}
    result['inspection_sha256']=canonical_hash(result);return result


def collect_native_references(context,typed_references,explicit_selections):
    chosen={};working={}
    def add(reference,intent,target):
        reference=validate_native_reference(reference);key=reference['snapshot_sha256']
        identity=(reference['kind'],reference['document_id'])
        if target:
            _need(identity not in working or working[identity]==key,'Choose one working start snapshot per native document')
            working[identity]=key
        if key in chosen:
            _need(all(chosen[key]['reference'][k]==reference[k] for k in ('kind','document_id','saved_revision')),'Conflicting native snapshot identity')
            chosen[key]['working_target']=chosen[key]['working_target'] or target
            return
        chosen[key]={'reference':reference,'copy_intent':intent,'working_target':target}
    for typed in typed_references:
        reference=getattr(typed,'value',typed)
        if isinstance(reference,dict) and reference.get('kind') in {'native_pre','native_post'}:
            add(reference,'preserve_declared_partial',False)
    for selection in explicit_selections:
        _keys(selection,{'native','copy_intent','working_target'},'Native copy selection')
        _need(type(selection['working_target']) is bool,'Working target selection must be explicit')
        add(selection['native'],selection['copy_intent'],selection['working_target'])
        # Explicit stronger complete intent must not be weakened by history dedupe.
        chosen[selection['native']['snapshot_sha256']]['copy_intent']=selection['copy_intent']
    # A current head is editable state, not the original source. Recopy its
    # explicitly declared lineage as archival snapshots, using the existing
    # local mapping rather than looking up the old store or scanning metadata.
    if (context.workspace/'portable-project.json').is_file() or context.known_targets:
        manifest=_manifest(context) if (context.workspace/'portable-project.json').is_file() else {'native_projects':[],'native_mapping':[]}
        targets={t['target_id']:t for t in [*manifest['native_projects'],*context.known_targets.values()]}
        remaining=dict(targets)
        while remaining:
            matched=False
            for target_id,target in list(remaining.items()):
                pointer=json_file(inside(context.workspace,target['head_file']))
                if pointer['reference'] not in [r['reference'] for r in chosen.values()]:continue
                _,head,_=_target(context,target_id)
                lineage=[target['source'],*target['source_lineage']]
                if head['parent_reference'] is not None:lineage.append(head['parent_reference'])
                for reference in lineage:
                    if not (context.root/'inputs'/reference['input_id']/'input.json').is_file():
                        reference=project_native_reference(reference,manifest)
                    verify_registered(context,reference,full=True)
                    add(reference,'preserve_declared_partial',False)
                del remaining[target_id];matched=True
            if not matched:break
    pending=list(chosen);visited=set()
    while pending:
        key=pending.pop(0)
        if key in visited:continue
        visited.add(key);_need(len(visited)<=4096,'Native declared source closure exceeds the existing member bound')
        verified=verify_registered(context,chosen[key]['reference'],full=True)
        for link in verified.snapshot['source_links']:
            target=link['target']
            if target['kind']!='exact' or target['form'] not in {'native_pre','native_post'}:continue
            reference=target['reference']
            if not (context.root/'inputs'/reference['input_id']/'input.json').is_file() and (context.workspace/'portable-project.json').is_file():
                reference=project_native_reference(reference,_manifest(context))
            add(reference,'preserve_declared_partial',False)
            pending.append(reference['snapshot_sha256'])
    inspections=[]
    for row in chosen.values():
        inspected=inspect_native(context,row['reference'],copy_intent=row['copy_intent'])
        inspections.append(inspected)
    return {'inspections':inspections,'selections':list(chosen.values()),'working_snapshots':list(working.values())}


def stage_native(context,inspections,stage,*,project_id,local_ids):
    context=_require_context(context);stage=Path(stage);no_links(stage);check_id(project_id)
    result={'native_contract':CONTRACT,'native_inputs':[],'native_projects':[],'native_mapping':[]}
    stage_context=NativeOnlyContext(stage,approved_roots={},config=context.config,adapters=context.adapters)
    for inspection in inspections:
        context.check();_need(_hash(inspection,'inspection_sha256')==inspection['inspection_sha256'],'Native inspection changed')
        fresh=inspect_native(context,inspection['reference'],copy_intent=inspection['copy_intent'])
        _need(fresh==inspection,'INPUT_CHANGED: native saved inspection changed')
        verified=verify_registered(context,inspection['reference'],full=True);snapshot=verified.snapshot
        digest=snapshot['snapshot_sha256'];identifier=local_ids.setdefault(digest,'D'+uuid.uuid4().hex)
        check_id(identifier)
        original=stage/'portable'/'originals'/'native'/digest
        source_folder=context.root/'inputs'/verified.reference['input_id']
        for name in ['input.json',verified.receipt['native_project']['manifest_file']]:
            source=inside(source_folder,name);copy_verified(source,original/name,fingerprint_file(source))
        for member in snapshot['members']:
            if member['storage']=='file':
                source=verified.member_paths[member['id']]
                copy_verified(source,original/'files'/member['relative'],member)
                copy_verified(source,stage_context.root/'inputs'/identifier/'files'/member['relative'],member)
        folder=stage_context.root/'inputs'/identifier
        sidecar_name=verified.receipt['native_project']['manifest_file']
        copy_verified(inside(source_folder,sidecar_name),folder/sidecar_name,fingerprint_file(inside(source_folder,sidecar_name)))
        receipt=deepcopy(verified.receipt);receipt['id']=identifier
        for row in receipt['files']:row['file']='inputs/'+identifier+'/files/'+row['relative']
        entry=next(m for m in snapshot['members'] if m['id']==snapshot['entry_member'])
        receipt['file']='inputs/'+identifier+'/files/'+entry['relative']
        receipt['origin']={'mode':'PORTABLE_SNAPSHOT','source_reference':deepcopy(verified.reference)}
        save_json(folder/'input.json',receipt)
        reference=snapshot_reference(receipt,snapshot);verify_registered(stage_context,reference,full=True)
        selection=next((s for s in local_ids.get('selections',[]) if s['reference']['snapshot_sha256']==digest),None)
        working=(digest in local_ids.get('working_snapshots',[])) if selection is None else selection['working_target']
        target_id='K'+uuid.uuid4().hex if working else None
        result['native_inputs'].append({'local_input_id':identifier,'source_reference':deepcopy(verified.reference),
            'snapshot_sha256':digest,'receipt_path':'workbench/inputs/'+identifier+'/input.json',
            'snapshot_manifest_path':'workbench/inputs/'+identifier+'/'+sidecar_name})
        result['native_mapping'].append({'source_kind':verified.reference['kind'],'source_document_id':verified.reference['document_id'],
            'source_saved_revision':verified.reference['saved_revision'],'snapshot_sha256':digest,'local_input_id':identifier,'target_id':target_id})
        if target_id:
            working_id=('P' if snapshot['native_kind']=='pre' else 'D')+uuid.uuid4().hex
            head_file='native/'+target_id+'/head.json'
            target={'target_id':target_id,'native_kind':snapshot['native_kind'],'source':reference,
                'working_document_id':working_id,'head_file':head_file,'title':verified.receipt['name'],
                'source_lineage':[deepcopy(row['reference']) for row in collect_native_references(context,[],[
                    {'native':verified.reference,'copy_intent':inspection['copy_intent'],'working_target':False}])['selections']]}
            result['native_projects'].append(target)
            save_json(stage/head_file,{'version':1,'target_id':target_id,'working_document_id':working_id,
                'head_generation':0,'layer':'DERIVED_BASE','reference':reference,'parent_reference':None})
    return result


def _manifest(context):
    manifest=json_file(inside(context.workspace,'portable-project.json'))
    _need(manifest.get('format')==FORMAT and manifest.get('native_contract')==CONTRACT,'Unsupported native portable contract')
    _need(_hash(manifest,'manifest_sha256')==manifest['manifest_sha256'],'Portable manifest changed')
    return manifest


def _target(context,target_id):
    check_id(target_id)
    manifest=_manifest(context) if (context.workspace/'portable-project.json').is_file() else {'native_projects':[]}
    targets=[row for row in manifest['native_projects'] if row['target_id']==target_id]
    _need(len(targets)<=1,'Duplicate native working target')
    if targets:target=targets[0]
    else:
        publication=json_file(inside(context.workspace,'native/'+target_id+'/target.json'))
        _keys(publication,{'version','target','prepare_command_id','save_id','request_sha256','registered_reference'},'Local native target publication')
        _need(type(publication['version']) is int and publication['version']==1,'Unknown local native target publication')
        reservation=json_file(inside(context.root,'native_project/target_saves/'+check_id(publication['prepare_command_id'])+'.json'))
        _need(reservation['state'] in {'REGISTERED','PUBLISHED'} and reservation['target_id']==target_id
            and reservation['save_id']==publication['save_id'] and reservation['request_sha256']==publication['request_sha256']
            and canonical_hash(reservation['arguments'])==reservation['request_sha256']
            and reservation['registered_reference']==publication['registered_reference'],'Local native target does not match its verified Save reservation')
        target=publication['target']
        _need(target['source']==reservation['source_reference'] and target['working_document_id']==reservation['arguments']['expected_stamp']['document_id'],'Local target source/owner differs from its reserved Save')
        verify_registered(context,publication['registered_reference'],full=True)
    _keys(target,{'target_id','native_kind','source','working_document_id','head_file','title','source_lineage'},'Native target')
    _need(target['native_kind'] in {'pre','post'} and isinstance(target['title'],str),'Invalid native working target')
    check_id(target['working_document_id']);validate_native_reference(target['source'])
    _need(isinstance(target['source_lineage'],list),'Invalid declared native lineage')
    for reference in target['source_lineage']:validate_native_reference(reference)
    _need(target['head_file']=='native/'+target_id+'/head.json','Native head points outside its target')
    head=json_file(inside(context.workspace,target['head_file']))
    _keys(head,{'version','target_id','working_document_id','head_generation','layer','reference','parent_reference'},'Native head')
    _need(head['version']==1 and type(head['version']) is int and head['target_id']==target_id and head['working_document_id']==target['working_document_id'],'Native head owner differs')
    _need(type(head['head_generation']) is int and head['head_generation']>=0 and head['layer'] in {'DERIVED_BASE','NATIVE_SAVED'},'Invalid native head state')
    reference=validate_native_reference(head['reference']);verified=verify_registered(context,reference,full=True)
    _need(verified.snapshot['native_kind']==target['native_kind'],'Native head kind differs')
    if head['layer']=='DERIVED_BASE':_need(head['head_generation']==0 and reference==target['source'] and head['parent_reference'] is None,'Derived base source differs')
    else:
        _need(reference['document_id']==target['working_document_id'] and head['head_generation']>0,'Current native saved identity differs')
        verify_registered(context,validate_native_reference(head['parent_reference']),full=True)
    context.known_targets[target_id]=deepcopy(target)
    return target,head,verified


def verify_native(context,manifest):
    context=_require_context(context)
    _need(manifest.get('format')==FORMAT and manifest.get('native_contract')==CONTRACT,'Unknown native portable format')
    for name in ('native_inputs','native_projects','native_mapping'):_need(isinstance(manifest.get(name),list),'Missing native portable inventory')
    inputs=set();partial=False;catalog=[]
    for row in manifest['native_inputs']:
        _keys(row,{'local_input_id','source_reference','snapshot_sha256','receipt_path','snapshot_manifest_path'},'Native portable input')
        old=validate_native_reference(row['source_reference']);identifier=check_id(row['local_input_id'])
        _need(identifier not in inputs and row['snapshot_sha256']==old['snapshot_sha256'],'Duplicate/conflicting native input');inputs.add(identifier)
        _need(row['receipt_path']=='workbench/inputs/'+identifier+'/input.json','Native receipt path differs')
        reference={**old,'input_id':identifier};verified=verify_registered(context,reference,full=True)
        _need(row['snapshot_manifest_path']=='workbench/inputs/'+identifier+'/'+verified.receipt['native_project']['manifest_file'],'Native sidecar path differs')
        original=context.workspace/'portable'/'originals'/'native'/old['snapshot_sha256']
        old_receipt=json_file(inside(original,'input.json'));old_snapshot=validate_snapshot(json_file(inside(original,old_receipt['native_project']['manifest_file'])))
        _need(fingerprint_file(inside(original,old_receipt['native_project']['manifest_file']))['sha256']==old_receipt['native_project']['manifest_sha256'],'Original native sidecar bytes changed')
        _need(snapshot_reference(old_receipt,old_snapshot)==old and old_snapshot==verified.snapshot,'Original native snapshot differs')
        raw={m['id']:inside(original,'files/'+m['relative']) for m in old_snapshot['members'] if m['storage']=='file'}
        for member in old_snapshot['members']:
            if member['storage']=='file':_need(fingerprint_file(raw[member['id']])=={k:member[k] for k in ('bytes','sha256')},'Original native member changed')
        context.adapter(old_snapshot['native_kind'])['verify'](old_snapshot,raw)
        is_partial=old_snapshot['validation']['closure']!='COMPLETE' or old_snapshot['format']=='pvsm'
        partial=partial or is_partial;catalog.append({'reference':reference,'native_availability':'PARTIAL' if is_partial else 'COMPLETE'})
    targets=set()
    for row in manifest['native_projects']:
        _need(row['target_id'] not in targets,'Duplicate native working target');targets.add(row['target_id']);_target(context,row['target_id'])
    mapped=set();mapped_targets=set()
    for row in manifest['native_mapping']:
        _keys(row,{'source_kind','source_document_id','source_saved_revision','snapshot_sha256','local_input_id','target_id'},'Native mapping')
        _need(row['local_input_id'] in inputs and (row['target_id'] is None or row['target_id'] in targets),'Native mapping target/input is unavailable')
        _need(row['local_input_id'] not in mapped,'Duplicate native local mapping');mapped.add(row['local_input_id'])
        old=next(r['source_reference'] for r in manifest['native_inputs'] if r['local_input_id']==row['local_input_id'])
        _need(all(row[k]==old[v] for k,v in [('source_kind','kind'),('source_document_id','document_id'),('source_saved_revision','saved_revision'),('snapshot_sha256','snapshot_sha256')]),'Native mapping exact source differs')
        if row['target_id'] is not None:
            _need(row['target_id'] not in mapped_targets,'Native working target has more than one source mapping');mapped_targets.add(row['target_id'])
            target=next(t for t in manifest['native_projects'] if t['target_id']==row['target_id'])
            _need(target['source']=={**old,'input_id':row['local_input_id']},'Native target source differs from its exact local mapping')
    _need(mapped==inputs and mapped_targets==targets,'Native inventory has an undeclared mapping/target')
    return {'status':'READY','native_availability':'PARTIAL' if partial else 'COMPLETE','complete_native':not partial,
        'native_projects':deepcopy(manifest['native_projects']),'native_inputs':catalog,'executed':False,'engineering_release':'NOT_RELEASED'}


def prepare_open(context,request,*,command_id):
    context=_require_context(context);check_id(command_id)
    _keys(request,{'reference','intent','target_id','expected_head','selection','allow_partial'},'Native open request')
    reference=validate_native_reference(request['reference']);_need(type(request['allow_partial']) is bool,'Partial open must be explicit')
    with context.lock:
        target=None;head=None
        if request['intent']=='working':
            _need(request['target_id'] is not None and request['expected_head'] is not None,'Working open requires an exact target head')
            target,head,verified=_target(context,request['target_id'])
            _need(request['expected_head']=={'generation':head['head_generation'],'reference':head['reference']} and reference==head['reference'],'STALE_TARGET: current head differs; review it explicitly')
        else:
            _need(request['intent']=='saved' and request['target_id'] is None and request['expected_head'] is None,'Saved open cannot follow a working head')
            verified=verify_registered(context,reference,full=True)
        snapshot=verified.snapshot
        _need(request['allow_partial'] or snapshot['validation']['closure']=='COMPLETE','Source has declared missing/unsupported native dependencies')
        if request['selection'] is not None:
            from .native_project_contract import validate_native_selection
            validate_native_selection(request['selection'],snapshot)
        action=context.root/'native_project'/'opens'/(command_id+'.json')
        signature=canonical_hash(request)
        if action.exists():
            record=json_file(action);_need(record['request_sha256']==signature,'COMMAND_CONFLICT: native open request changed')
            _need(record['context_session']==context.session_id and record['open_id'] in context.tickets,'OPEN_UNCONFIRMED: an earlier launcher outcome must be checked; do not automatically launch again')
            return context.tickets[record['open_id']]
        open_id='O'+uuid.uuid4().hex
        target_id=target['target_id'] if target else None
        target_root=context.workspace/'native'/(target_id or ('saved-'+open_id))
        working_root=target_root/'working'/open_id
        working_id=target['working_document_id'] if target else ('P' if snapshot['native_kind']=='pre' else 'D')+uuid.uuid4().hex
        owner_map=[]
        documents=[m for m in snapshot['members'] if m['role']=='pre_document']
        if documents:
            if head and head['layer']=='NATIVE_SAVED':
                from apps.desktop_pre.portable_project import saved_owner_id_map
                owner_map=saved_owner_id_map(verified)
                _need(all(row['owner_document_id'] is not None for row in owner_map),'OWNER_IDENTITY_UNBOUND: saved child identity is unavailable')
                _need(owner_map[0]['owner_document_id']==working_id,'Native saved root identity differs from the working target')
            else:
                owner_map=[{'member_id':m['id'],'owner_document_id':working_id if i==0 else 'P'+uuid.uuid4().hex} for i,m in enumerate(documents)]
        binding=OpenBinding(open_id,signature,request['intent'],reference,working_id,owner_map,target_id,
            deepcopy(request['expected_head']),working_root,target_root/'saved' if target else None,verified,
            dict(verified.member_paths),{},deepcopy(snapshot.get('relocation_bases',[])),context.session_id,_SEAL)
        save_json(action,{'open_id':open_id,'request':deepcopy(request),'request_sha256':signature,
            'context_session':context.session_id,'state':'PREPARING'})
        derived={}
        status='PREPARED'
        if snapshot['native_kind']=='post':
            if snapshot['format']=='pvsm':
                derived={'status':'MANAGED_SAVE_REQUIRED'};status='ADOPTION_REQUIRED'
            else:
                from apps.desktop_post.portable_project import derive_project
                derived=derive_project(verified,working_root,binding=binding)
        ticket=NativeOpenTicket(binding,verified,derived,status,_SEAL)
        config={'version':1,'workspace':str(context.workspace),'context_session':context.session_id,
            'command_id':command_id,'open_id':open_id,'request_sha256':signature}
        config_path=context.root/'native_project'/'launches'/(open_id+'.json')
        save_json(action,{'open_id':open_id,'request':deepcopy(request),'request_sha256':signature,
            'working_document_id':working_id,'owner_id_map':owner_map,'context_session':context.session_id,'state':status,
            'launch_sha256':canonical_hash(config)})
        save_json(config_path,config)
        derived['launch_config']=str(config_path)
        context.tickets[open_id]=ticket
        context.open_actions[open_id]=action
        return ticket


def resume_open_ticket(config_path):
    """Private native startup seam: verify the owned journal and raw pins again.

    This is not a public JSON-to-ticket converter. The launcher passes the
    generated local file; reference, paths and working identity come from the
    current owned journal/target and full registered-byte verification.
    """
    path=Path(config_path).absolute();no_links(path);config=json_file(path)
    _keys(config,{'version','workspace','context_session','command_id','open_id','request_sha256'},'Native private launch config')
    _need(type(config['version']) is int and config['version']==1,'Unknown native launch version')
    command_id=check_id(config['command_id']);open_id=check_id(config['open_id'])
    context=NativeOnlyContext(config['workspace'],approved_roots={},session_id=config['context_session'])
    _need(path==context.root/'native_project'/'launches'/(open_id+'.json'),'Private native launch file is outside its owned operation')
    action=context.root/'native_project'/'opens'/(command_id+'.json');record=json_file(action)
    _need(record['open_id']==open_id and record['context_session']==context.session_id
        and record['request_sha256']==config['request_sha256'] and record['launch_sha256']==canonical_hash(config),
        'Native private launch config/journal differs')
    _need(record['state'] in {'PREPARED','ADOPTION_REQUIRED','LAUNCHING'},'OPEN_UNCONFIRMED: this launch has already completed or requires explicit reconciliation')
    request=record['request'];_need(canonical_hash(request)==record['request_sha256'],'Native open request changed')
    _keys(request,{'reference','intent','target_id','expected_head','selection','allow_partial'},'Native open request')
    verified=verify_registered(context,request['reference'],full=True)
    if request['intent']=='working':
        target,head,_=_target(context,request['target_id'])
        _need(request['reference']==head['reference'] and request['expected_head']=={'generation':head['head_generation'],'reference':head['reference']},'STALE_TARGET: native target changed before launch')
        working_id=target['working_document_id']
    else:
        _need(request['intent']=='saved' and request['target_id'] is None and request['expected_head'] is None,'Invalid isolated saved launch')
        working_id=check_id(record['working_document_id'])
    _need(working_id==record['working_document_id'],'Native working identity changed')
    target_root=context.workspace/'native'/(request['target_id'] or ('saved-'+open_id))
    owner_map=record['owner_id_map'];members={m['id'] for m in verified.snapshot['members'] if m['role']=='pre_document'}
    _need({row['member_id'] for row in owner_map}==members,'Native launch owner mapping omits a saved document')
    for row in owner_map:
        _keys(row,{'member_id','owner_document_id'},'Native owner mapping');check_id(row['owner_document_id'])
    binding=OpenBinding(open_id,record['request_sha256'],request['intent'],deepcopy(verified.reference),working_id,
        deepcopy(owner_map),request['target_id'],deepcopy(request['expected_head']),target_root/'working'/open_id,
        target_root/'saved' if request['target_id'] else None,verified,dict(verified.member_paths),{},
        deepcopy(verified.snapshot.get('relocation_bases',[])),context.session_id,_SEAL)
    derived={'launch_config':str(path)}
    if verified.snapshot['native_kind']=='post' and verified.snapshot['format']!='pvsm':
        derived['project_path']=str(binding.working_root/'project.json')
    ticket=NativeOpenTicket(binding,verified,derived,record['state'],_SEAL)
    context.tickets[open_id]=ticket;context.open_actions[open_id]=action
    return context,ticket


def claim_open_launch(context,open_id):
    """Call once immediately before the existing launcher creates its process."""
    context=_require_context(context);check_id(open_id)
    with context.lock:
        _need(open_id in context.tickets and open_id in context.open_actions,'OPEN_UNCONFIRMED: current local ticket is unavailable')
        action=context.open_actions[open_id];record=json_file(action)
        _need(record['state'] in {'PREPARED','ADOPTION_REQUIRED'},'OPEN_UNCONFIRMED: query the existing launch/readback instead of launching again')
        claim=context.root/'native_project'/'launches'/(open_id+'.claim')
        no_links(claim)
        try:
            with claim.open('x',encoding='utf-8') as stream:
                import json
                json.dump({'open_id':open_id,'context_session':context.session_id,'request_sha256':record['request_sha256']},stream)
                stream.flush()
        except FileExistsError as error:raise ValueError('OPEN_UNCONFIRMED: this native launch was already claimed') from error
        save_json(action,{**record,'state':'LAUNCHING'})
        return {'open_id':open_id,'status':'LAUNCHING'}


def open_ticket_view(context,open_id):
    """Current file-only query; never claims a launcher or dispatches native work."""
    context=_require_context(context);check_id(open_id)
    ticket=context.tickets.get(open_id);_need(ticket is not None,'OPEN_UNCONFIRMED: no current local ticket exists')
    binding=ticket.binding;verify_registered(context,binding.reference,full=True)
    record=json_file(context.open_actions[open_id])
    _need(record['request_sha256']==binding.request_sha256 and canonical_hash(record['request'])==binding.request_sha256,'Native open request changed')
    status=record['state'];target_id=binding.target_id or record.get('published_target')
    local_state='UNSAVED_IMPORT' if binding.intent=='saved' else 'DERIVED_BASE'
    if target_id:
        target,head,_=_target(context,target_id)
        _need(target['working_document_id']==binding.owner_document_id,'Native open target owner changed')
        if status in {'PREPARED','ADOPTION_REQUIRED','LAUNCHING'} and binding.target_id:
            _need(binding.expected_head=={'generation':head['head_generation'],'reference':head['reference']},'STALE_TARGET: native head changed before open')
        local_state=head['layer']
    claim=context.root/'native_project'/'launches'/(open_id+'.claim')
    if status in {'PREPARED','ADOPTION_REQUIRED'} and claim.exists():status='OPEN_UNCONFIRMED'
    return {'status':status,'open_id':open_id,'reference':deepcopy(binding.reference),'owner_document_id':binding.owner_document_id,
        'target_id':target_id,'local_save_state':local_state,'native_kind':ticket.verified_input.snapshot['native_kind'],
        'launch_config':ticket.derived.get('launch_config'),'readback':deepcopy(record.get('readback')),
        'warnings':deepcopy(ticket.verified_input.snapshot['validation']['issues']),
        'effects':{'native_launch':False,'native_save':False,'head_published':False,'executed':False}}


@dataclass(frozen=True)
class NativeOpenReadback:
    payload:dict
    _seal:object=field(repr=False)
    def __post_init__(self):_need(self._seal is _SEAL,'Native readback must come from the authenticated owner/launcher')


def _native_open_readback(payload):return NativeOpenReadback(deepcopy(payload),_SEAL)


def verify_opened(context,open_id,actual):
    context=_require_context(context);check_id(open_id)
    _need(type(actual) is NativeOpenReadback and actual._seal is _SEAL,'A public caller dictionary is not native completion evidence')
    ticket=context.tickets.get(open_id);_need(type(ticket) is NativeOpenTicket,'OPEN_UNCONFIRMED: current ticket is unavailable')
    verified=verify_registered(context,ticket.binding.reference,full=True)
    payload=actual.payload;binding=ticket.binding
    _need(all(payload.get(k)==v for k,v in {'open_id':open_id,'reference':verified.reference,'target_id':binding.target_id,
        'working_document_id':binding.working_document_id,'context_session':context.session_id}.items()),'Native opened owner/readback does not match this exact ticket')
    _need(payload.get('status') in {'OPENED','PARTIAL_OPEN'},'Native load/selection is not confirmed')
    _need(payload.get('native_owner_session') and payload.get('native_kind')==verified.snapshot['native_kind'],'Native owner session/kind was not confirmed')
    action_path=context.open_actions.get(open_id)
    _need(action_path is not None,'OPEN_UNCONFIRMED: original native open request is unavailable')
    action=json_file(action_path);selected=action['request']['selection']
    if selected is not None:
        _need(payload.get('selection_status')=='SELECTED' and payload.get('selection')==selected,'SELECTION_UNAVAILABLE: exact native selection was not confirmed')
    if binding.target_id:
        _,head,_=_target(context,binding.target_id)
        _need(binding.expected_head=={'generation':head['head_generation'],'reference':head['reference']},'STALE_TARGET: target changed while native opened')
    save_json(action_path,{**action,'state':'OPENED','readback':deepcopy(payload)})
    return deepcopy(payload)


def _finish_target_save(context,target_save,result):
    cached=context.target_saves.get(target_save.save_id)
    _need(cached is not None and cached[0]==target_save,'Native Save reservation is not current')
    path=context.root/'native_project'/'target_saves'/(cached[1]+'.json');record=json_file(path)
    save_json(path,{**record,'state':'PUBLISHED','registered_reference':result['reference'],'result':result})
    opened_path=context.open_actions[target_save.open_id];opened=json_file(opened_path)
    save_json(opened_path,{**opened,'published_target':target_save.target_id})
    _target(context,target_save.target_id)


def _publish_first_head(context,target_id,completed_save,*,command_id,target_save):
    from .native_project_contract import require_target_save
    target_save=require_target_save(target_save)
    _need(target_save.creation=='NEW_TARGET' and target_save.target_id==target_id and target_save.expected_head is None,'First native head requires its new-target reservation')
    cached=context.target_saves.get(target_save.save_id)
    _need(cached is not None and cached[0]==target_save,'Native target reservation is not owned by this current context')
    _,prepare_command_id=cached
    reservation_path=context.root/'native_project'/'target_saves'/(prepare_command_id+'.json')
    reservation=json_file(reservation_path)
    _need(reservation['request_sha256']==target_save.request_sha256 and reservation['target_id']==target_id,'Native first Save reservation changed')
    _need(completed_save.command_id==target_save.save_command_id and completed_save.owner_stamp['document_id']==target_save.owner_document_id
        and completed_save.owner_stamp['session_id']==target_save.expected_stamp['session_id'],'Native completed Save is not this reserved owner/command')
    _need(completed_save.native_kind==target_save.source_reference['kind'][7:] and completed_save.publication_complete,'Native Save publication is unconfirmed')
    root=target_save.native_save_root.parent
    _need(completed_save.saved_file.is_relative_to(root),'First native Save is outside the reserved target')
    arguments={'target_id':target_id,'save_command_id':completed_save.command_id,'expected_head':None,'pin':completed_save.pin,'save_id':target_save.save_id}
    action=context.root/'native_project'/'heads'/(command_id+'.json')
    with context.lock,_head_publication(context,target_id):
        if action.exists():
            prior=json_file(action);_need(prior['arguments']==arguments,'COMMAND_CONFLICT: first native head request changed')
            if prior['state']=='PUBLISHED':
                _finish_target_save(context,target_save,prior['result']);return deepcopy(prior['result'])
        scoped=NativeOnlyContext(context.workspace,approved_roots={'native-target':target_save.native_save_root},config=context.config,
            session_id=context.session_id,adapters=context.adapters,cancel=context.cancel)
        if completed_save.native_kind=='post':scoped.native_save_binding=(context.tickets[target_save.open_id].binding,target_save)
        if reservation.get('registered_reference') is not None:
            reference=reservation['registered_reference'];verify_registered(context,reference,full=True)
        else:
            save_json(action,{'state':'SAVE_COMPLETED','arguments':arguments})
            registered=register_saved(scoped,completed_save,command_id='C'+canonical_hash({'first_head':command_id,'save':completed_save.command_id})[:40])
            reference=registered['reference']
            _need(reference['document_id']==target_save.owner_document_id,'Native registered Save identity differs from the imported live owner')
            reservation={**reservation,'state':'REGISTERED','registered_reference':reference}
            save_json(reservation_path,reservation)
        _need(reference['document_id']==target_save.owner_document_id,'Native first Save registration belongs to another document')
        ticket=context.tickets[target_save.open_id]
        target={'target_id':target_id,'native_kind':completed_save.native_kind,'source':deepcopy(target_save.source_reference),
            'working_document_id':target_save.owner_document_id,'head_file':'native/'+target_id+'/head.json',
            'title':ticket.verified_input.receipt['name'],'source_lineage':[deepcopy(target_save.source_reference)]}
        publication={'version':1,'target':target,'prepare_command_id':prepare_command_id,'save_id':target_save.save_id,
            'request_sha256':target_save.request_sha256,'registered_reference':reference}
        descriptor=root/'target.json'
        if descriptor.exists():_need(json_file(descriptor)==publication,'TARGET_CONFLICT: reserved target publication differs')
        else:save_json(descriptor,publication)
        new_head={'version':1,'target_id':target_id,'working_document_id':target_save.owner_document_id,
            'head_generation':1,'layer':'NATIVE_SAVED','reference':reference,'parent_reference':deepcopy(target_save.source_reference)}
        head_path=root/'head.json'
        if head_path.exists():_need(json_file(head_path)==new_head,'TARGET_CONFLICT: first native head was published by another Save')
        else:save_json(head_path,new_head)
        result={'status':'PUBLISHED','target_id':target_id,'head':new_head,'reference':reference}
        save_json(action,{'state':'PUBLISHED','arguments':arguments,'result':result})
        _finish_target_save(context,target_save,result)
        return result


def publish_registered_head(context,target_id,completed_save,*,expected_head,command_id,_target_save=None):
    context=_require_context(context);check_id(command_id)
    from .native_project_contract import CompletedSaveWitness
    _need(type(completed_save) is CompletedSaveWitness and completed_save._seal is _SEAL,'A real completed Save witness is required')
    if expected_head is None:
        return _publish_first_head(context,target_id,completed_save,command_id=command_id,target_save=_target_save)
    if _target_save is not None:
        from .native_project_contract import require_target_save
        require_target_save(_target_save)
        _need(_target_save.creation=='EXISTING_TARGET' and _target_save.target_id==target_id and _target_save.expected_head==expected_head
            and _target_save.save_command_id==completed_save.command_id and _target_save.owner_document_id==completed_save.owner_stamp['document_id']
            and _target_save.expected_stamp['session_id']==completed_save.owner_stamp['session_id'],'Native completed Save differs from its exact target reservation')
    if completed_save.source.get('mode')=='authenticated_native_command':
        _need(completed_save.source['target_id']==target_id and completed_save.source['expected_head']==expected_head,
            'STALE_TARGET: publication must use the head captured by the actual native Save completion')
    with context.lock, _head_publication(context,target_id):
        action=context.root/'native_project'/'heads'/(command_id+'.json')
        arguments={'target_id':target_id,'save_command_id':completed_save.command_id,'expected_head':expected_head,'pin':completed_save.pin}
        prior=None
        if action.exists():
            prior=json_file(action);_need(prior['arguments']==arguments,'COMMAND_CONFLICT: native head publication differs')
            if prior['state']=='PUBLISHED':
                if _target_save is not None:_finish_target_save(context,_target_save,prior['result'])
                return deepcopy(prior['result'])
        target,head,_=_target(context,target_id)
        if prior and prior['state']=='REGISTERED' and head['reference']==prior['registered_reference']:
            _need(head['head_generation']==expected_head['generation']+1 and head['parent_reference']==expected_head['reference'],'STALE_TARGET: saved head lineage differs')
            result={'status':'PUBLISHED','target_id':target_id,'head':head,'reference':head['reference']}
            save_json(action,{'state':'PUBLISHED','arguments':arguments,'result':result})
            if _target_save is not None:_finish_target_save(context,_target_save,result)
            return result
        _need(expected_head=={'generation':head['head_generation'],'reference':head['reference']},'STALE_TARGET: saved native bytes are retained; the pointer must be reviewed')
        _need(completed_save.native_kind==target['native_kind'],'Saved native kind differs from the target')
        _need(completed_save.owner_stamp['document_id']==target['working_document_id'],'Save witness belongs to another native working document')
        # The generated target is owned by this verified local manifest. It is
        # not an expansion of the user's external file chooser roots.
        owned_root=context.workspace/'native'/target_id
        _need(completed_save.saved_file.is_relative_to(owned_root),'Save witness is outside this native working target')
        save_context=NativeOnlyContext(context.workspace,approved_roots={**context.approved_roots.paths,'native-target':owned_root},
            config=context.config,session_id=context.session_id,adapters=context.adapters,cancel=context.cancel)
        if completed_save.native_kind=='post' and _target_save is not None:
            save_context.approved_roots=type(save_context.approved_roots)({'native-target':_target_save.native_save_root},_SEAL)
            save_context.native_save_binding=(context.tickets[_target_save.open_id].binding,_target_save)
        save_json(action,{'state':'SAVE_COMPLETED','arguments':arguments})
        registered=register_saved(save_context,completed_save,command_id='C'+canonical_hash({'head':command_id,'save':completed_save.command_id})[:40])
        reference=registered['reference'];verified=verify_registered(context,reference,full=True)
        _need(reference['document_id']==target['working_document_id'],'Native saved identity differs from this working target')
        save_json(action,{'state':'REGISTERED','arguments':arguments,'registered_reference':reference})
        new_head={'version':1,'target_id':target_id,'working_document_id':target['working_document_id'],
            'head_generation':head['head_generation']+1,'layer':'NATIVE_SAVED','reference':reference,'parent_reference':head['reference']}
        # Recheck the mutable head immediately before its atomic pointer write.
        _need(json_file(inside(context.workspace,target['head_file']))==head,'STALE_TARGET: native head changed before publication')
        save_json(context.workspace/target['head_file'],new_head)
        result={'status':'PUBLISHED','target_id':target_id,'head':new_head,'reference':reference}
        save_json(action,{'state':'PUBLISHED','arguments':arguments,'result':result})
        if _target_save is not None:_finish_target_save(context,_target_save,result)
        return result
