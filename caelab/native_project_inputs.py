"""Explicit saved-native registration on existing native_inputs file receipts.

Standalone context is file-only. No Workbench, JobManager, native app, provider or
new source store is created. The small journals only reconcile existing actions.
"""
from copy import deepcopy
from contextlib import contextmanager
from dataclasses import dataclass,field
from pathlib import Path
import os
import threading
import uuid

from . import native_inputs
from .storage import canonical_hash,check_id,save_json
from .portable_project_io import (inside,json_file,no_links,copy_verified,fingerprint_file,
    relative_name,MAX_BYTES)
from .execution_control import check_cancelled
from .native_project_contract import (CompletedSaveWitness,VerifiedNativeInput,_SEAL,
    NativeTargetSaveBinding,require_target_save,VerifiedReplacementMap,require_replacement_map,validate_locator,
    validate_native_reference,validate_snapshot,snapshot_reference,finalize_snapshot,_need,_keys,_pin)

_LOCKS={};_LOCK=threading.RLock()


def _lock(root):
    with _LOCK:return _LOCKS.setdefault(str(root),threading.RLock())


@contextmanager
def _head_publication(context,target_id):
    """One OS-held byte lock for the existing mutable head CAS, no dependency.

    The OS releases the handle on process exit; the empty operational lock file
    is never part of portable source inventory or native document identity.
    """
    path=context.workspace/'native'/check_id(target_id)/'head.publish.lock'
    no_links(path);stream=path.open('a+b')
    acquired=False
    try:
        if path.stat().st_size==0:stream.write(b'\0');stream.flush()
        stream.seek(0)
        try:
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(stream.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError as error:raise ValueError('HEAD_BUSY: another native Save is publishing this working head; reconfirm the same completed Save') from error
        acquired=True;yield
    finally:
        if acquired:
            stream.seek(0)
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(stream.fileno(),msvcrt.LK_UNLCK,1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(),fcntl.LOCK_UN)
        stream.close()


@dataclass(frozen=True)
class ApprovedRoots:
    paths:dict
    _seal:object=field(repr=False)
    def __post_init__(self):_need(self._seal is _SEAL,'Roots must come from the current explicit file context')


class NativeOnlyContext:
    def __init__(self,workspace,*,approved_roots,config=None,session_id=None,adapters=None,resolve_completed_save=None,resolve_link=None,cancel=None):
        workspace=Path(workspace).absolute();no_links(workspace)
        self.workspace=workspace.resolve();self.root=self.workspace/'workbench'
        self.session_id=check_id(session_id or 'L'+uuid.uuid4().hex)
        options=config or {};limit=options.get('local_input_max_bytes',2*1024**3)
        _need(type(limit) is int and limit>0,'local_input_max_bytes must be a positive integer')
        self.config={'local_input_max_bytes':min(limit,MAX_BYTES)}
        roots={}
        for identifier,value in approved_roots.items():
            check_id(identifier);path=Path(value).absolute();no_links(path)
            _need(path.is_dir(),'An explicitly approved native root is unavailable');roots[identifier]=path.resolve()
        self.approved_roots=ApprovedRoots(roots,_SEAL)
        self.adapters=adapters or {};self.resolve_completed_save=resolve_completed_save;self.resolve_link=resolve_link;self.cancel=cancel or check_cancelled
        self._seal=_SEAL;self.lock=_lock(self.root);self.tickets={};self.open_actions={};self.target_saves={};self.known_targets={}

    def check(self):
        _need(self._seal is _SEAL,'Use the current trusted native file context');self.cancel()

    def adapter(self,kind):
        if kind in self.adapters:return self.adapters[kind]
        if kind=='pre':
            from apps.desktop_pre import portable_project
            return {'inspect':portable_project.pre_snapshot_files,'verify':portable_project.verify_snapshot_members}
        from . import native_post_dependencies
        return {'inspect':native_post_dependencies.post_project_files,'verify':native_post_dependencies.verify_snapshot_members}


def context_from_workbench(workbench,*,resolve_completed_save=None):
    """Borrow current file roots/session only; never creates an application owner."""
    if resolve_completed_save is None and hasattr(workbench,'native_commands'):
        resolve_completed_save=lambda command_id:resolve_completed_command(workbench,command_id)
    key=canonical_hash({'session':workbench.session_id,'workspace':str(workbench.workspace),
        'roots':workbench.config.get('input_roots',{}),'limit':workbench.config.get('local_input_max_bytes',2*1024**3)})
    cached=getattr(workbench,'_native_project_context',None)
    if cached is None or cached[0]!=key:
        cached=(key,NativeOnlyContext(workbench.workspace,approved_roots=workbench.config.get('input_roots',{}),
            config=workbench.config,session_id=workbench.session_id,resolve_completed_save=resolve_completed_save))
        workbench._native_project_context=cached
    elif resolve_completed_save is not None:cached[1].resolve_completed_save=resolve_completed_save
    def resolve_link(link):
        from .connection_graph import SnapshotReader
        from .connection_graph_refs import TypedReference
        return SnapshotReader(workbench).resolve(TypedReference((),link['relation'],link['target']['form'],link['target']['reference']))
    cached[1].resolve_link=resolve_link
    return cached[1]


def _require_context(context):
    _need(type(context) is NativeOnlyContext and context._seal is _SEAL,'A current trusted native file context is required')
    context.check();return context


def _approved_path(context,path):
    path=Path(path).absolute();no_links(path);resolved=path.resolve(strict=True)
    _need(any(path.is_relative_to(root) and resolved.is_relative_to(root) for root in context.approved_roots.paths.values()),'ROOT_DENIED: native source is outside approved roots')
    _need(resolved.is_file(),'Select an actual saved native file');return resolved


def _source(context,source):
    if isinstance(source,CompletedSaveWitness):
        _need(source._seal is _SEAL and source.publication_complete is True,'SAVE_UNCONFIRMED: the native file publication did not complete')
        _need(fingerprint_file(source.saved_file)==source.pin,'INPUT_CHANGED: completed native saved bytes changed')
        return source.native_kind,_approved_path(context,source.saved_file),{'mode':'completed_native_save','command_id':source.command_id}
    _need(isinstance(source,dict),'Select a saved native file or completed command')
    mode=source.get('mode')
    if mode=='completed_native_save':
        _keys(source,{'mode','command_id'},'Completed native save source');check_id(source['command_id'])
        _need(callable(context.resolve_completed_save),'SAVE_UNCONFIRMED: completed native command lookup is unavailable')
        witness=context.resolve_completed_save(source['command_id'])
        _need(type(witness) is CompletedSaveWitness and witness.command_id==source['command_id'],'A public result dictionary is not a completed native save')
        return _source(context,witness)
    _keys(source,{'mode','native_kind','root_id','relative'},'Selected saved native file')
    _need(mode=='selected_file' and source['native_kind'] in {'pre','post'},'Select a known saved native kind')
    root=context.approved_roots.paths.get(source['root_id']);_need(root is not None,'ROOT_DENIED: choose a currently approved native root')
    return source['native_kind'],_approved_path(context,inside(root,relative_name(source['relative']))),deepcopy(source)


def _save_registered_source_members(context,binding,source_ref,record):
    """Exact same-content registered relocation for this sealed Post source only."""
    from .native_project_contract import require_open_binding
    require_open_binding(binding)
    _need(binding.context_session==context.session_id and binding.reference['kind']=='native_post',
        'Native repaired source belongs to another open context')
    verified=verify_registered(context,binding.reference,full=True)
    original=json_file(verified.entry_path).get('sources',{}).get(source_ref)
    _need(isinstance(original,dict) and isinstance(record,dict),'REPLACEMENT_UNBOUND: choose this saved native source')
    for key in ('source_revision','reader_name','reader_type','native_metadata'):
        _need(record.get(key)==original.get(key),'CONTENT_CHANGED: repaired native source identity differs')
    _need(isinstance(original.get('source_revision'),str) and bool(original['source_revision']),
        'REPLACEMENT_UNBOUND: saved native source has no exact content revision')
    identifier=check_id(record.get('input_id'));folder=context.root/'inputs'/identifier
    receipt=json_file(inside(folder,'input.json'))
    _need(receipt.get('id')==identifier and receipt.get('kind') in {'native_result','native_curve'},
        'Repaired source must be a current registered native result')
    _need(receipt.get('native_metadata')==record.get('native_metadata'),'CONTENT_CHANGED: registered source metadata differs')
    if receipt.get('native_metadata') is not None:
        _need(canonical_hash(receipt['native_metadata'])==receipt.get('native_metadata_sha256'),'Registered source metadata changed')
    files=receipt.get('files');_need(isinstance(files,list) and 0<len(files)<=4096,'Registered source has no bounded file inventory')
    entry=inside(context.root,receipt['file']);no_links(entry)
    _need(Path(record['entry_path']).resolve()==entry and entry.suffix.lower()==Path(original['entry_path']).suffix.lower(),
        'CONTENT_CHANGED: repaired source entry differs from its exact registered entry/type')
    registered={};total=0
    for file in files:
        relative=relative_name(file['relative'])
        _need(file['file']=='inputs/'+identifier+'/files/'+relative,'Registered source file escapes its input set')
        physical=inside(context.root,file['file']);no_links(physical)
        pin={key:file[key] for key in ('bytes','sha256')}
        _need(fingerprint_file(physical)==pin,'CONTENT_CHANGED: registered source file changed')
        name=physical.relative_to(entry.parent).as_posix()
        _need(name not in registered,'Duplicate registered source member');registered[name]=(physical,pin)
        total+=pin['bytes']
    _need(total==receipt.get('total_bytes') and total<=context.config['local_input_max_bytes'],'Registered source inventory exceeds its current bound')
    def content(pins,entry):
        result={}
        for pin in pins:
            name=Path(pin['path']).relative_to(Path(entry).parent).as_posix()
            _need(name not in result,'Duplicate native source content member')
            result[name]={key:pin[key] for key in ('bytes','sha256')}
        return result
    original_content=content(original['source_pins'],original['entry_path'])
    _need(original_content==content(record['source_pins'],record['entry_path'])=={name:pin for name,(_,pin) in registered.items()},
        'CONTENT_CHANGED: repaired registered source relative content differs')
    _need({Path(pin['path']).resolve() for pin in record['source_pins']}=={path for path,_ in registered.values()},
        'Repaired source pins point outside its exact registered set')
    origins={row['original_location']:row['member_id'] for row in verified.snapshot['logical_origins']}
    members={row['id']:row for row in verified.snapshot['members']};allowed={}
    source_members={origins[pin['path']] for pin in original['source_pins'] if pin['path'] in origins}
    reachable={origins[original['entry_path']]} if original['entry_path'] in origins else set()
    pending=list(reachable)
    while pending:
        parent=pending.pop()
        for edge in verified.snapshot['edges']:
            child=edge['child_member']
            if edge['parent_member']==parent and child in source_members and child not in reachable:
                reachable.add(child);pending.append(child)
    origin_paths={row['member_id']:row['original_location'] for row in verified.snapshot['logical_origins']}
    def missing_pin(pin,index):
        matches=[]
        for missing in verified.snapshot['unavailable']:
            expected=missing['expected_child'];locator=missing['locator']
            if expected is None or missing['code']!='MISSING_DEPENDENCY' or any(expected[key]!=pin[key] for key in ('bytes','sha256')):continue
            edges=[edge for edge in verified.snapshot['edges'] if edge['parent_member']==missing['parent_member'] and edge['locator']==locator and edge['child_member'] is None]
            if len(edges)!=1:continue
            edge=edges[0]
            if locator['codec']=='post_manifest_v1':
                fields={'sources/'+source_ref+'/entry_path','sources/'+source_ref+'/entry_path/missing/'+str(index)}
                if missing['parent_member']!=verified.snapshot['entry_member'] or locator['field'] not in fields:continue
                target=edge['original_reference']
            elif locator['codec'] in {'pvd_v1','vtk_parallel_xml_v1','vtk_composite_xml_v1'} and missing['parent_member'] in reachable:
                parent=origin_paths[missing['parent_member']]
                target=os.path.normpath(str(Path(parent).parent/edge['original_reference']))
            else:continue
            if os.path.normpath(target)==os.path.normpath(pin['path']):matches.append(expected)
        _need(bool(matches) and all(item==matches[0] for item in matches),
            'REPLACEMENT_UNBOUND: repaired source has no exact typed missing dependency pin')
        return deepcopy(matches[0])
    for index,pin in enumerate(original['source_pins']):
        member=members.get(origins.get(pin['path']))
        if member is None:member=missing_pin(pin,index)
        else:_need(member['storage']=='file' and all(member[key]==pin[key] for key in ('bytes','sha256')),
            'CONTENT_CHANGED: repaired source differs from its original saved member')
        name=Path(pin['path']).relative_to(Path(original['entry_path']).parent).as_posix()
        allowed[registered[name][0]]=deepcopy(member)
    return allowed


def _plan(context,kind,path,identifier,*,_replacements=None,primary_root=None):
    adapter=context.adapter(kind)
    roots=[primary_root] if primary_root is not None else [max((root for root in context.approved_roots.paths.values() if path.is_relative_to(root)),key=lambda root:len(root.parts))]
    private={} if _replacements is None else {'_replacements':require_replacement_map(_replacements)}
    save_pair=getattr(context,'native_save_binding',None);save_files={}
    if save_pair is not None:
        from .native_project_contract import require_open_binding
        binding,target_save=save_pair;require_open_binding(binding);require_target_save(target_save)
        _need(kind=='post' and binding.reference['kind']=='native_post' and binding.open_id==target_save.open_id and binding.owner_document_id==target_save.owner_document_id
            and path.is_relative_to(target_save.native_save_root),'Native Save source scope belongs to another reservation')
        verified=verify_registered(context,binding.reference,full=True)
        for member in verified.snapshot['members']:
            if member['storage']!='file':continue
            physical=binding.materialization_root/'files'/member['relative']
            no_links(physical)
            _need(fingerprint_file(physical)=={key:member[key] for key in ('bytes','sha256')},'CONTENT_CHANGED: current native materialized source member changed')
            save_files[physical]={key:member[key] for key in ('bytes','sha256')}
        private['_save_binding']=save_pair
        def registered_source(source_ref,record):
            allowed=_save_registered_source_members(context,binding,source_ref,record)
            for physical,member in allowed.items():save_files[physical]={key:member[key] for key in ('bytes','sha256')}
            return allowed
        private['_save_registered_source']=registered_source
    if kind=='pre':
        plan=adapter['inspect'](path,approved_roots=roots,
            source_document_id='P'+canonical_hash(identifier)[:32],**private)
    else:
        plan=adapter['inspect'](path,approved_roots=roots,
            limits={'max_files':4096,'max_bytes':context.config['local_input_max_bytes']},**private)
    snapshot=deepcopy(plan['snapshot'])
    if kind=='post' and snapshot['identity_origin']=='registration_assigned':
        snapshot['source_document_id']='D'+canonical_hash(identifier)[:32]
        from .native_project_contract import saved_revision_for
        snapshot['saved_revision']=saved_revision_for(snapshot)
        snapshot=finalize_snapshot(snapshot)
    snapshot=validate_snapshot(snapshot)
    _need(snapshot['native_kind']==kind,'Saved file kind differs from its adapter')
    expected={m['id']:m for m in snapshot['members'] if m['storage']=='file'}
    _need(isinstance(plan['files'],list) and len(plan['files'])==len(expected),'Native file plan omits or duplicates a member')
    seen=set();total=0
    for row in plan['files']:
        member=expected.get(row['member_id']);_need(member is not None and row['member_id'] not in seen,'Unknown/duplicate source member');seen.add(row['member_id'])
        _need(all(row[k]==member[k] for k in ('relative','bytes','sha256')),'Source plan pin differs from snapshot')
        if Path(row['source']) in save_files:
            source=Path(row['source']);_need(all(row[key]==save_files[source][key] for key in ('bytes','sha256')),'Native Save source plan differs from its verified materialized member')
        elif _replacements is not None and _replacements.permits(Path(row['source']),row):source=Path(row['source'])
        else:
            source=_approved_path(context,row['source'])
            _need(any(source.is_relative_to(root) for root in roots),'ROOT_DENIED: an external native dependency needs its exact registered replacement')
        _need(fingerprint_file(source)=={k:row[k] for k in ('bytes','sha256')},'INPUT_CHANGED: source changed during inspection')
        total+=row['bytes']
    _need(total<=context.config['local_input_max_bytes'],'Native input set exceeds the current file limit')
    if _replacements is not None:_replacements.verify_consumed()
    return {**plan,'snapshot':snapshot}


def _replacement_declarations(replacements):
    _need(isinstance(replacements,(list,tuple)) and len(replacements)<=1024,'Choose a bounded explicit replacement list')
    result=[];seen=set()
    for row in replacements:
        _keys(row,{'parent_member','locator','expected_child','replacement_input_id','replacement_member'},'Registered native replacement')
        check_id(row['parent_member']);validate_locator(row['locator']);check_id(row['replacement_input_id']);relative_name(row['replacement_member'])
        _need(row['expected_child'] is not None,'REPLACEMENT_UNBOUND: a caller cannot supply missing original source evidence')
        expected=row['expected_child'];_keys(expected,{'relative','bytes','sha256'},'Expected original child pin');relative_name(expected['relative']);_pin({key:expected[key] for key in ('bytes','sha256')})
        key=(row['parent_member'],canonical_hash(row['locator']));_need(key not in seen,'Duplicate native replacement source edge');seen.add(key)
        result.append(deepcopy(row))
    return result


def verify_replacements(context,source,replacements):
    context=_require_context(context);declarations=_replacement_declarations(replacements)
    kind,path,arguments=_source(context,source);rows=[]
    for declaration in declarations:
        identifier=declaration['replacement_input_id'];folder=context.root/'inputs'/identifier
        receipt_path=inside(folder,'input.json');receipt=json_file(receipt_path)
        _need(receipt.get('id')==identifier and receipt.get('kind') in {'native_design','native_result','native_post_project','native_curve','frozen_fem','frozen_contact','frozen_shell','frozen_beam'},'Replacement must be an existing registered native input set')
        _need(isinstance(receipt.get('files'),list) and 0<len(receipt['files'])<=4096,'Registered replacement has no bounded file set')
        if receipt.get('native_project') is not None:registered_input(context,identifier,full=True)
        if receipt.get('native_metadata') is not None:
            _need(canonical_hash(receipt['native_metadata'])==receipt.get('native_metadata_sha256'),'Registered replacement metadata changed')
        files=[];seen=set();total=0
        for file in receipt['files']:
            relative=relative_name(file['relative']);_need(relative not in seen,'Duplicate registered replacement file');seen.add(relative)
            _need(file['file']=='inputs/'+identifier+'/files/'+relative,'Replacement file points outside its registered set')
            physical=inside(context.root,file['file']);_need(fingerprint_file(physical)=={key:file[key] for key in ('bytes','sha256')},'Registered replacement file changed')
            total+=file['bytes'];files.append({'source':physical,'relative':'registered/'+identifier+'/'+relative,**{key:file[key] for key in ('bytes','sha256')}})
        _need(total==receipt['total_bytes'] and total<=context.config['local_input_max_bytes'],'Registered replacement set exceeds current bounds')
        matches=[file for file in files if file['relative']=='registered/'+identifier+'/'+declaration['replacement_member']]
        _need(len(matches)==1,'Select the exact relative member of the registered replacement set')
        file=matches[0];_need(all(file[key]==declaration['expected_child'][key] for key in ('bytes','sha256')),'CONTENT_CHANGED: replacement bytes differ from the expected original source pin')
        rows.append({**declaration,**file,'files':files,'receipt_path':receipt_path,'receipt_sha256':fingerprint_file(receipt_path)['sha256']})
    verified=VerifiedReplacementMap(path,fingerprint_file(path),tuple(rows),context.session_id,{'consumed':set(),'source_verified':False},_SEAL)
    if rows:
        root=context.approved_roots.paths.get(arguments.get('root_id'))
        _plan(context,kind,path,'CVerifyReplacements',_replacements=verified,primary_root=root)
    else:verified.verify_consumed()
    return verified


def _member_paths(context,receipt,snapshot):
    _need(isinstance(receipt.get('files'),list),'Registered native input lacks its file set')
    files={row['relative']:row for row in receipt['files']}
    _need(len(files)==len(receipt['files']),'Duplicate native receipt file')
    members=[m for m in snapshot['members'] if m['storage']=='file']
    _need(set(files)=={m['relative'] for m in members},'Registered native inventory differs from the snapshot')
    _need(all(row['file']=='inputs/'+receipt['id']+'/files/'+row['relative'] for row in files.values()),'Native member points outside its registered input')
    return {member['id']:inside(context.root,files[member['relative']]['file']) for member in members}


def register_saved(context,source,*,replacements=(),command_id):
    context=_require_context(context);command_id=check_id(command_id)
    declarations=_replacement_declarations(replacements)
    with context.lock:
        action=context.root/'native_project'/'registrations'/(command_id+'.json')
        if action.exists() and json_file(action)['state']=='REGISTERED':
            prior=json_file(action)
            if type(source) is CompletedSaveWitness:
                _need(source._seal is _SEAL and source.publication_complete,'SAVE_UNCONFIRMED: native Save did not publish')
                source_arguments={'mode':'completed_native_save','command_id':source.command_id}
            else:
                _need(isinstance(source,dict),'Select the same saved native input')
                source_arguments=deepcopy(source)
            arguments={'source':source_arguments,'replacements':declarations} if declarations else source_arguments
            _need(prior['arguments']==arguments,'COMMAND_CONFLICT: registration request changed')
            if source_arguments['mode']=='selected_file':
                root=context.approved_roots.paths.get(source_arguments['root_id'])
                _need(root is not None,'ROOT_DENIED: original file selection root is no longer approved')
                selected=root/relative_name(source_arguments['relative'])
                _need(selected in {Path(r['source']) for r in prior['sources']},'COMMAND_CONFLICT: selected root now resolves to another source')
            for row in prior['sources']:
                old=Path(row['source'])
                if old.exists():_need(fingerprint_file(old)=={k:row[k] for k in ('bytes','sha256')},'COMMAND_CONFLICT: saved source changed')
            verified=verify_registered(context,prior['reference'])
            return {'status':'REGISTERED','reference':deepcopy(verified.reference),'input_id':verified.receipt['id']}
        kind,path,source_arguments=_source(context,source)
        arguments={'source':source_arguments,'replacements':declarations} if declarations else source_arguments
        if action.exists():
            prior=json_file(action);_need(prior['arguments']==arguments,'COMMAND_CONFLICT: registration request changed')
            identifier=prior['input_id']
        else:
            identifier='D'+uuid.uuid4().hex
            save_json(action,{'state':'PREPARING','arguments':arguments,'input_id':identifier})
        replacement_map=verify_replacements(context,source,declarations) if declarations else None
        plan=_plan(context,kind,path,command_id,_replacements=replacement_map,primary_root=context.approved_roots.paths.get(source_arguments.get('root_id')));snapshot=plan['snapshot']
        prior=json_file(action)
        _need(prior.get('snapshot_sha256',snapshot['snapshot_sha256'])==snapshot['snapshot_sha256'],'COMMAND_CONFLICT: original saved bytes changed during registration')
        save_json(action,{**prior,'snapshot_sha256':snapshot['snapshot_sha256']})
        folder=context.root/'inputs'/identifier
        # Interrupted registration with no published receipt remains unconfirmed.
        if folder.exists() and not (folder/'input.json').exists():
            raise ValueError('SAVE_UNCONFIRMED: registered staging exists; preserve it and inspect before retry')
        if (folder/'input.json').exists():
            prior_receipt=json_file(folder/'input.json');reference=snapshot_reference(prior_receipt,snapshot)
            verified=verify_registered(context,reference)
        else:
            # Operational staging is not a portable source path. Keep it short
            # for native Python runtimes without Windows long-path support.
            admission=context.root/'native_stage'/command_id
            admission.mkdir(parents=True,exist_ok=True);paths=[]
            for row in plan['files']:
                context.check();target=admission/relative_name(row['relative'])
                if target.exists():_need(fingerprint_file(target)=={k:row[k] for k in ('bytes','sha256')},'INPUT_CHANGED: interrupted admission differs')
                else:copy_verified(Path(row['source']),target,row)
                paths.append(target)
            entry=next(m for m in snapshot['members'] if m['id']==snapshot['entry_member'])
            entry_path=admission/entry['relative'];paths=[entry_path]+[p for p in paths if p!=entry_path]
            def postprocess(folder,receipt):
                context.check();member_paths=_member_paths(context,receipt,snapshot)
                context.adapter(kind)['verify'](snapshot,member_paths)
                sidecar=folder/'native-project.json';save_json(sidecar,snapshot)
                pin=fingerprint_file(sidecar)
                return {**receipt,'native_project':{'version':1,'manifest_file':'native-project.json','manifest_sha256':pin['sha256']}}
            receipt=native_inputs._register_set(context.root,admission,entry_path,paths,None,identifier,
                root_id=source_arguments.get('root_id','native-save'),relative=entry['relative'],limit=context.config['local_input_max_bytes'],
                kind=snapshot['input_kind'],format=snapshot['format'],_postprocess=postprocess)
            reference=snapshot_reference(receipt,snapshot);verified=verify_registered(context,reference)
        save_json(action,{'state':'REGISTERED','arguments':arguments,'input_id':identifier,'reference':verified.reference,
            'sources':[{key:str(row[key]) if key=='source' else row[key] for key in ('source','bytes','sha256')} for row in plan['files']]})
        return {'status':'REGISTERED','reference':deepcopy(verified.reference),'input_id':identifier}


def verify_registered(context,reference,*,full=True):
    context=_require_context(context);reference=validate_native_reference(reference)
    _need(type(full) is bool,'Full verification must be explicit')
    folder=context.root/'inputs'/reference['input_id'];receipt=json_file(inside(folder,'input.json'))
    _need(receipt.get('id')==reference['input_id'],'Native receipt owner differs')
    pin=receipt.get('native_project');_keys(pin,{'version','manifest_file','manifest_sha256'},'Native sidecar pin')
    _need(type(pin['version']) is int and pin['version']==1,'Unknown native sidecar version')
    sidecar=inside(folder,pin['manifest_file']);_need(fingerprint_file(sidecar)['sha256']==pin['manifest_sha256'],'SNAPSHOT_CHANGED: native sidecar differs')
    snapshot=validate_snapshot(json_file(sidecar));_need(snapshot_reference(receipt,snapshot)==reference,'Native saved reference differs from the registration')
    paths=_member_paths(context,receipt,snapshot)
    if full:
        total=0
        for member in snapshot['members']:
            if member['storage']!='file':continue
            context.check();_need(fingerprint_file(paths[member['id']])=={k:member[k] for k in ('bytes','sha256')},'CONTENT_CHANGED: native registered member differs')
            total+=member['bytes']
        _need(total==receipt['total_bytes'] and total<=context.config['local_input_max_bytes'],'Native registered total differs or exceeds current limit')
        context.adapter(snapshot['native_kind'])['verify'](snapshot,paths)
    entry=paths[snapshot['entry_member']]
    return VerifiedNativeInput(reference,deepcopy(receipt),snapshot,entry,paths,full,context.session_id,_SEAL)


def registered_input(context,identifier,*,full=True):
    """Existing registered-input lookup; its current sidecar defines the reference."""
    context=_require_context(context);check_id(identifier)
    folder=context.root/'inputs'/identifier;receipt=json_file(inside(folder,'input.json'))
    pin=receipt.get('native_project');_keys(pin,{'version','manifest_file','manifest_sha256'},'Native sidecar pin')
    sidecar=inside(folder,pin['manifest_file'])
    _need(fingerprint_file(sidecar)['sha256']==pin['manifest_sha256'],'SNAPSHOT_CHANGED: native sidecar differs')
    return verify_registered(context,snapshot_reference(receipt,validate_snapshot(json_file(sidecar))),full=full)


def read_registered(context,reference,*,facet='summary'):
    _need(facet in {'summary','manifest','dependencies','source_links'},'Choose a known native read facet')
    verified=verify_registered(context,reference,full=False);snapshot=verified.snapshot
    if facet=='manifest':return deepcopy(snapshot)
    if facet=='dependencies':return {key:deepcopy(snapshot[key]) for key in ('members','edges','unavailable','reader_bindings')}
    if facet=='source_links':return bind_declared_links(context,snapshot['source_links'],members=snapshot['members'])
    return {'reference':deepcopy(verified.reference),'native_kind':snapshot['native_kind'],'format':snapshot['format'],
        'closure':snapshot['validation']['closure'],'issues':deepcopy(snapshot['validation']['issues']),
        'verification':'METADATA_ONLY','full_verified':False,'total_bytes':verified.receipt['total_bytes']}


def bind_declared_links(context,links,*,members):
    """Current exact-read availability on preserved HISTORY_ONLY relationships."""
    from .native_project_contract import validate_declared_links
    context=_require_context(context)
    # A list may contain only the site's native kind; project sites are shared.
    kind='post' if any(link.get('source',{}).get('kind') in {'post_source','post_history'} for link in links) else 'pre'
    links=validate_declared_links(links,native_kind=kind);member_ids={m['id'] for m in members};availability=[];issues=[]
    for index,link in enumerate(links):
        target=link['target'];state='UNAVAILABLE';message='원 자료를 현재 사본에서 읽을 수 없습니다.'
        if target['kind']=='job_history':
            recorded=[m for m in [*target['records'].values(),*target['output_members']] if m is not None]
            _need(set(recorded)<=member_ids,'Historical job references an undeclared native member')
            state='HISTORY_ONLY' if recorded else 'ORIGINAL_FILES_NOT_RETAINED'
            message='보존한 원 계산 기록입니다. 현재 실행·재시도 권한은 없습니다.'
        else:
            try:
                if target['form'] in {'native_pre','native_post'}:
                    reference=target['reference']
                    if not (context.root/'inputs'/reference['input_id']/'input.json').is_file() and (context.workspace/'portable-project.json').is_file():
                        from .portable_project_native import _manifest
                        from .native_project_contract import project_native_reference
                        reference=project_native_reference(reference,_manifest(context))
                    verify_registered(context,reference,full=True);state='AVAILABLE';message='검증된 원본 저장 모델입니다.'
                elif callable(context.resolve_link):
                    resolved=context.resolve_link(link)
                    _need(resolved.get('exact_reference')==target['reference'],'LINK_UNSUPPORTED: existing resolver did not confirm this exact reference')
                    _need(resolved.get('status') in {'AVAILABLE','NEWER_REVISION'},'Linked saved source is unavailable')
                    state='AVAILABLE';message=resolved.get('message','검증된 저장 원자료입니다.')
            except (ValueError,KeyError,TypeError,OSError) as error:
                message=str(error);issues.append({'code':'LINK_UNAVAILABLE','index':index,'message':message})
        availability.append({'index':index,'state':state,'authority':'HISTORY_ONLY','message':message})
    return {'source_links':links,'availability':availability,'issues':issues}


def _save_witness_receipt(witness,binding,*,_target_save=None):
    """Private native-owner result metadata, emitted after its real Save only."""
    from .native_project_contract import require_open_binding
    require_open_binding(binding)
    _need(type(witness) is CompletedSaveWitness and witness._seal is _SEAL,'A completed native Save witness is required')
    _need(witness.native_kind==binding.reference['kind'][7:],'Native Save owner kind differs')
    _need(witness.owner_stamp['document_id']==binding.working_document_id,'Native Save owner differs from its open binding')
    expected=deepcopy(binding.expected_head);target_id=binding.target_id;save_id=None
    if _target_save is not None:
        require_target_save(_target_save)
        _need(_target_save.open_id==binding.open_id and _target_save.owner_document_id==binding.owner_document_id
            and _target_save.save_command_id==witness.command_id and _target_save.expected_stamp['session_id']==witness.owner_stamp['session_id'],'Native completed Save differs from the current reservation')
        expected=deepcopy(_target_save.expected_head);target_id=_target_save.target_id;save_id=_target_save.save_id
    elif binding.target_id:
        from .portable_project_native import _target
        context=NativeOnlyContext(binding.target_root.parents[1],approved_roots={},session_id=binding.context_session)
        target,head,_=_target(context,binding.target_id)
        _need(target['working_document_id']==binding.working_document_id,'Native Save target working identity changed')
        expected={'generation':head['head_generation'],'reference':deepcopy(head['reference'])}
    return {'version':1,'native_kind':witness.native_kind,'command_id':witness.command_id,
        'saved_file':str(witness.saved_file),'owner_stamp':deepcopy(witness.owner_stamp),
        'publication_complete':witness.publication_complete,'pin':deepcopy(witness.pin),
        'open_id':binding.open_id,'target_id':target_id,'expected_head':expected,'save_id':save_id}


def resolve_completed_command(workbench,command_id):
    """Resolve the authenticated broker completion, never a caller result dict.

    Failed/interrupted/old-service commands remain unconfirmed. This does not
    submit another Save, register files or move a working head.
    """
    from .native_commands import NativeCommands
    from .native_project_contract import _completed_save_witness
    registry=workbench.native_commands
    _need(type(registry) is NativeCommands and registry.root==workbench.root/'native_commands',
        'Use the current native command owner for Save reconciliation')
    command=registry.status(check_id(command_id))
    _need(command['service_session_id']==workbench.session_id and command['operation'] in {'document.save','pre.project.save'}
        and command['state']=='SUCCEEDED' and command.get('phase')=='FINISHED','SAVE_UNCONFIRMED: the actual native Save command did not complete in this service')
    outcome=command.get('outcome',{});response=outcome.get('result',{})
    _need(outcome.get('state')=='SUCCEEDED' and response.get('status')=='COMPLETED'
        and response.get('command_id')==command_id and response.get('document_id')==command['document_id']
        and response.get('session_id')==command['session_id'],'SAVE_UNCONFIRMED: native Save owner response differs')
    receipt=response.get('result',{}).get('native_save_receipt')
    _keys(receipt,{'version','native_kind','command_id','saved_file','owner_stamp','publication_complete','pin','open_id','target_id','expected_head','save_id'},'Native Save completion receipt')
    _need(type(receipt['version']) is int and receipt['version']==1 and receipt['command_id']==command_id,'Native Save receipt command differs')
    stamp=receipt['owner_stamp']
    _need(stamp.get('document_id')==command['document_id'] and stamp.get('session_id')==command['session_id']
        and stamp.get('generation')==command.get('final_generation') and stamp.get('view_generation')==command.get('final_view_generation'),
        'SAVE_UNCONFIRMED: native Save receipt owner stamp differs')
    context=context_from_workbench(workbench)
    binding=context.tickets.get(receipt['open_id'])
    _need(binding is not None,'SAVE_UNCONFIRMED: current verified native open ticket is unavailable')
    binding=binding.binding
    target_save=None
    if receipt['save_id'] is not None:
        target_save=resolve_target_save_command(context,command_id)
        _need(target_save.save_id==receipt['save_id'] and target_save.target_id==receipt['target_id'] and target_save.expected_head==receipt['expected_head'],'Native Save completion differs from its reserved target')
    else:_need(receipt['target_id']==binding.target_id,'Native Save receipt belongs to another target')
    _need(stamp['document_id']==binding.working_document_id,'Native Save receipt belongs to another owner')
    if receipt['expected_head'] is not None:
        _keys(receipt['expected_head'],{'generation','reference'},'Saved native target head')
        _need(type(receipt['expected_head']['generation']) is int and receipt['expected_head']['generation']>=0,'Invalid saved native target generation')
        validate_native_reference(receipt['expected_head']['reference'])
    else:_need(target_save is not None and target_save.creation=='NEW_TARGET','First native Save has no verified target reservation')
    path=Path(receipt['saved_file']).absolute();no_links(path)
    save_root=target_save.native_save_root.parent if target_save else binding.target_root
    _need(path.is_relative_to(save_root),'Native Save receipt points outside the current native target')
    _need(fingerprint_file(path)==receipt['pin'],'INPUT_CHANGED: completed native Save bytes changed')
    return _completed_save_witness(receipt['native_kind'],path,owner_stamp=stamp,command_id=command_id,
        publication_complete=receipt['publication_complete'],source={'mode':'authenticated_native_command','command_id':command_id,
            'target_id':receipt['target_id'],'expected_head':deepcopy(receipt['expected_head']),'open_id':receipt['open_id']})


def prepare_target_save(context,open_id,*,expected_stamp,expected_head,command_id):
    """Reserve one Save destination after explicit approval; never calls native Save."""
    context=_require_context(context);check_id(open_id);check_id(command_id)
    with context.lock:
        ticket=context.tickets.get(open_id);_need(ticket is not None,'OPEN_UNCONFIRMED: reopen or reconfirm the actual native owner')
        binding=ticket.binding
        _keys(expected_stamp,{'document_id','kind','session_id','generation','view_generation','saved_revision','graph_version'},'Native owner stamp')
        _need(expected_stamp['document_id']==binding.owner_document_id and expected_stamp['kind']==binding.reference['kind'][7:],'Native Save stamp belongs to another owner')
        check_id(expected_stamp['session_id'])
        for key in ('generation','view_generation'):_need(type(expected_stamp[key]) is int and expected_stamp[key]>=0,'Invalid native Save generation')
        open_action=context.open_actions[open_id];opened=json_file(open_action)
        _need(opened.get('state')=='OPENED','OPEN_UNCONFIRMED: actual native owner readback is required before Save reservation')
        _need(opened['readback']['native_owner_session']==expected_stamp['session_id'],'Native Save owner session differs from the confirmed open')
        arguments={'open_id':open_id,'expected_stamp':deepcopy(expected_stamp),'expected_head':deepcopy(expected_head)}
        signature=canonical_hash(arguments);action=context.root/'native_project'/'target_saves'/(command_id+'.json')
        if action.exists():
            record=json_file(action);_need(record['request_sha256']==signature,'COMMAND_CONFLICT: native Save reservation changed')
            return resume_target_save(context,command_id)
        pending=opened.get('pending_save');retry_target=None
        if pending:
            previous=json_file(context.root/'native_project'/'target_saves'/(check_id(pending)+'.json'))
            _need(previous['state'] in {'PUBLISHED','FAILED_CONFIRMED'},'NATIVE_SAVED_UNPUBLISHED: reconfirm the existing Save reservation before another Save')
            if previous['state']=='FAILED_CONFIRMED' and previous['creation']=='NEW_TARGET':retry_target=previous['target_id']
        target_id=binding.target_id or opened.get('published_target')
        if target_id:
            from .portable_project_native import _target
            target,head,_=_target(context,target_id)
            _need(target['working_document_id']==binding.owner_document_id and expected_head=={'generation':head['head_generation'],'reference':head['reference']},'STALE_TARGET: current native Save head differs')
            creation='EXISTING_TARGET'
        else:
            _need(binding.intent=='saved' and expected_head is None,'First saved import Save requires a new target with no existing head')
            target_id=retry_target or 'K'+uuid.uuid4().hex;creation='NEW_TARGET'
        save_id='W'+uuid.uuid4().hex;save_command_id='C'+canonical_hash({'prepare':command_id,'open_id':open_id})[:40]
        root=context.workspace/'native'/target_id/'saved'
        record={'state':'RESERVED','arguments':arguments,'request_sha256':signature,'context_session':context.session_id,
            'save_id':save_id,'save_command_id':save_command_id,'target_id':target_id,'creation':creation,
            'source_reference':deepcopy(binding.reference),'native_save_root':str(root)}
        save_json(action,record);save_json(open_action,{**opened,'pending_save':command_id})
        return resume_target_save(context,command_id)


def resume_target_save(context,command_id):
    """Private same-operation recovery from the current owned reservation."""
    context=_require_context(context);check_id(command_id)
    record=json_file(context.root/'native_project'/'target_saves'/(command_id+'.json'))
    arguments=record['arguments'];_need(canonical_hash(arguments)==record['request_sha256'],'Native Save reservation changed')
    ticket=context.tickets.get(arguments['open_id'])
    _need(ticket is not None and record['context_session']==context.session_id,'Native Save reservation belongs to another local open session')
    binding=ticket.binding
    _need(record['source_reference']==binding.reference and arguments['expected_stamp']['document_id']==binding.owner_document_id,'Native Save reservation source/owner differs')
    root=context.workspace/'native'/check_id(record['target_id'])/'saved'
    _need(str(root)==record['native_save_root'],'Native Save destination changed')
    result=NativeTargetSaveBinding(record['save_id'],record['save_command_id'],arguments['open_id'],binding.owner_document_id,
        record['target_id'],deepcopy(arguments['expected_stamp']),deepcopy(arguments['expected_head']),record['creation'],
        deepcopy(record['source_reference']),root,record['request_sha256'],_SEAL)
    require_target_save(result);context.target_saves[result.save_id]=(result,command_id)
    return result


def resolve_target_save_command(context,save_command_id,stamp=None):
    context=_require_context(context);check_id(save_command_id)
    rows=[(binding,command_id) for binding,command_id in context.target_saves.values() if binding.save_command_id==save_command_id]
    _need(len(rows)==1,'SAVE_UNCONFIRMED: this actual Save command has no current owned reservation')
    result=resume_target_save(context,rows[0][1])
    if stamp is not None:_need(result.expected_stamp==stamp,'STALE_DOCUMENT: native owner changed after Save reservation')
    return result


def _record_target_save_failure(context,target_save,error,*,stage='native_save'):
    """Native adapter only: proven pre-dispatch refusal or synchronous Save error.

    Transport loss, missing witness or errors after Save returned are UNKNOWN
    and must not call this function. Existing files/failed receipts remain.
    """
    context=_require_context(context);require_target_save(target_save)
    _need(isinstance(error,BaseException),'A caller status dictionary is not a confirmed native Save failure')
    _need(stage in {'before_save','native_save'},'An unknown/after-Save outcome must be reconciled')
    cached=context.target_saves.get(target_save.save_id);_need(cached is not None and cached[0]==target_save,'Native Save failure belongs to another reservation')
    path=context.root/'native_project'/'target_saves'/(cached[1]+'.json')
    with context.lock:
        record=json_file(path)
        _need(record['state']=='RESERVED' and not record.get('registered_reference'),'A completed/registered Save must be reconciled, not retried')
        save_json(path,{**record,'state':'FAILED_CONFIRMED','failure_stage':stage,'native_save_invoked':stage=='native_save','error':{'type':type(error).__name__,'message':str(error)}})
    return {'status':'FAILED_CONFIRMED','save_id':target_save.save_id,'target_id':target_save.target_id}


def publish_head(context,target_id,completed_save,*,expected_head,command_id,_target_save=None):
    from .portable_project_native import publish_registered_head
    return publish_registered_head(context,target_id,completed_save,expected_head=expected_head,command_id=command_id,_target_save=_target_save)
