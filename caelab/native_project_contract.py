"""Strict native saved-file contracts; no native runtime, document owner or jobs.

A saved source is immutable. Current native working identity and live sessions
are separate, and JSON dictionaries never become trusted open/save handles.
"""
from copy import deepcopy
from dataclasses import dataclass,field
import json
import math
import re
from pathlib import Path
from typing import Any,TypedDict

from .storage import canonical_hash,check_id
from .portable_project_io import relative_name,MAX_JSON_BYTES,MAX_BYTES,_portable_aliases

CONTRACT='caelab.native-project/1'
REFERENCE_KEYS=frozenset('kind version document_id saved_revision input_id snapshot_sha256'.split())
SNAPSHOT_KEYS=frozenset(('version native_kind input_kind format source_document_id saved_revision native_revision '
 'identity_origin revision_origin entry_member source_manifest_pin members edges reader_bindings native_metadata_bindings '
 'logical_origins unavailable source_links producer required_capabilities validation snapshot_sha256').split())
ROLES=frozenset('pre_archive pre_document post_manifest pvsm source_container source_data analysis_data analysis_container declared_metadata'.split())
ROLES=ROLES|frozenset('research_job_record research_input_record research_result_record research_output'.split())
HISTORY_FIELDS=frozenset({'relocation_bases','history_availability'})
CODECS=frozenset('freecad_xlink_v1 pvd_v1 vtk_parallel_xml_v1 vtk_composite_xml_v1 pvsm_reader_v1 post_manifest_v1 declared_companion_v1'.split())
METADATA_KINDS=frozenset('dynamic_locations contact_inspection shell_inspection beam_inspection curve'.split())
RECORD_FIELDS={
 'Issue':'code native_kind source_reference member_id locator message recovery severity',
 'NativeInspection':'version reference snapshot copy_intent files bindings issues total_bytes inspection_sha256',
 'VerifiedFilePin':'member_id source relative bytes sha256',
 'RegisteredReplacement':'parent_member locator expected_child replacement_input_id replacement_member',
 'RelocationBinding':'parent_member locator child_member required original_reference',
 'RelocationRecord':'version source_snapshot_sha256 open_id target_id algorithm_version derived_members identity_edit original_data_unchanged',
 'NativeOpenRequest':'reference intent target_id expected_head selection allow_partial',
 'NativeTarget':'target_id native_kind source working_document_id head_file title source_lineage',
 'NativeHead':'version target_id working_document_id head_generation layer reference parent_reference',
 'HistoryKey':'object_ref revision_id revision_sha256',
 'PostHistoryBasis':'version history bindings_sha256 graph_sha256 retained_graph_sha256 slots',
 'HistoryPathSlot':'site binding_ref upstream reader_key reader_type output_port file_property value_shape slot_count element_index basis_value member_id closure_member_ids closure_sha256',
 'HistoryAvailability':'history state record_sha256 missing reason_code',
 'DeclaredResearchLink':'version relation source target authority',
 'ExactLinkTarget':'kind form reference',
 'JobHistoryTarget':'kind job_id operation state_when_recorded origin records output_members',
}
for _name,_fields in RECORD_FIELDS.items():globals()[_name]=TypedDict(_name,{key:Any for key in _fields.split()})


def _need(condition,message):
    if not condition:raise ValueError(message)


def _keys(value,keys,label):
    _need(isinstance(value,dict) and set(value)==set(keys),label+' has unexpected or missing fields')


def _sha(value):
    _need(isinstance(value,str) and re.fullmatch('[a-f0-9]{64}',value) is not None,'Expected a lowercase SHA-256 pin')


def _json(value):
    _need(len(json.dumps(value,ensure_ascii=False,allow_nan=False).encode('utf-8'))<=MAX_JSON_BYTES,'Native metadata exceeds the existing JSON bound')


def _pin(value,*,member=False):
    _keys(value,{'bytes','sha256'}|({'member_id'} if member else set()),'File pin')
    _need(type(value['bytes']) is int and value['bytes']>=0,'File bytes must be an exact nonnegative integer')
    _sha(value['sha256'])
    if member:check_id(value['member_id'])


def validate_native_reference(value):
    _keys(value,REFERENCE_KEYS,'Native saved reference')
    _need(value['kind'] in {'native_pre','native_post'} and type(value['version']) is int and value['version']==1,'Unsupported native reference')
    for key in ('document_id','saved_revision','input_id'):check_id(value[key])
    _sha(value['snapshot_sha256']);return deepcopy(value)


def validate_declared_links(links,*,native_kind):
    _need(native_kind in {'pre','post'} and isinstance(links,list),'Invalid declared native links')
    for link in links:
        _keys(link,RECORD_FIELDS['DeclaredResearchLink'].split(),'Declared native research link')
        _need(type(link['version']) is int and link['version']==1 and link['authority']=='HISTORY_ONLY','Saved links do not grant live execution authority')
        _need(link['relation'] in {'native_source','research_context','result_source','recorded_job'},'Unknown declared link relation')
        site=link['source'];_need(isinstance(site,dict),'Invalid native link site')
        fields={'project':{'kind'},'pre_object':{'kind','document_member','object_name'},
            'post_source':{'kind','source_ref'},'post_history':{'kind','object_ref','revision_id'}}
        _need(site.get('kind') in fields,'Unknown native link site');_keys(site,fields[site['kind']],'Native link site')
        _need(site['kind']=='project' or (native_kind=='pre' and site['kind']=='pre_object') or
            (native_kind=='post' and site['kind'] in {'post_source','post_history'}),'Native link site kind differs')
        for key,value in site.items():
            if key!='kind':_need(isinstance(value,str) and value,'Missing exact native link site')
        if site['kind']=='pre_object':check_id(site['document_member'])
        target=link['target'];_need(isinstance(target,dict),'Invalid declared link target')
        if link['relation']=='recorded_job':
            _keys(target,RECORD_FIELDS['JobHistoryTarget'].split(),'Historical job target')
            _need(target['kind']=='job_history','Recorded job requires its historical record')
            check_id(target['job_id'])
            _need(all(isinstance(target[k],str) and target[k] for k in ('operation','state_when_recorded')),'Historical job requires its original operation/state')
            _need(target['origin'] is None or isinstance(target['origin'],dict),'Invalid historical job origin')
            _keys(target['records'],{'job','submitted_input','result'},'Historical job record members')
            for member in target['records'].values():
                if member is not None:check_id(member)
            _need(isinstance(target['output_members'],list),'Invalid historical outputs')
            for member in target['output_members']:check_id(member)
        else:
            _keys(target,RECORD_FIELDS['ExactLinkTarget'].split(),'Exact saved link target')
            expected={'native_source':{'native_pre','native_post'},'research_context':{'exact'},'result_source':{'result'}}[link['relation']]
            _need(target['kind']=='exact' and target['form'] in expected and isinstance(target['reference'],dict),'Link target form differs from its declared relation')
            if target['form'] in {'native_pre','native_post'}:
                reference=validate_native_reference(target['reference']);_need(reference['kind']==target['form'],'Native link form differs')
            # Research/result fields belong to their EXISTING exact resolver.
            # Shape resemblance never proves that such a reference is valid.
        _json(link)
    return deepcopy(links)


def metadata_declared_links(metadata,*,native_kind,source=None):
    """Project only the two explicit saved link fields; never query a controller."""
    _need(isinstance(metadata,dict),'Native metadata must be an object')
    links=validate_declared_links(metadata.get('native_links',[]),native_kind=native_kind)
    site=deepcopy(source or {'kind':'project'});issues=[]
    # Existing Pre.links.record records these four exact original values. Its
    # result_refs are not file-member declarations and cannot invent assets.
    if native_kind=='pre':
        for field in ('links','link_history'):
            rows=metadata.get(field,[])
            if not isinstance(rows,list):
                issues.append({'code':'LINK_UNSUPPORTED','field':field,'message':'원 계산 연결의 목록 형식을 확인할 수 없습니다.'});continue
            for index,row in enumerate(rows):
                if not isinstance(row,dict) or not {'job_id','operation','state_when_recorded','origin'}<=set(row):
                    issues.append({'code':'LINK_UNSUPPORTED','field':field,'index':index,'message':'필수 원 계산 연결 값이 없습니다. 원문은 그대로 보존합니다.'});continue
                link={'version':1,'relation':'recorded_job','source':deepcopy(site),'authority':'HISTORY_ONLY',
                    'target':{'kind':'job_history','job_id':row['job_id'],'operation':row['operation'],
                        'state_when_recorded':row['state_when_recorded'],'origin':deepcopy(row['origin']),
                        'records':{'job':None,'submitted_input':None,'result':None},'output_members':[]}}
                try:validate_declared_links([link],native_kind=native_kind)
                except ValueError as error:
                    issues.append({'code':'LINK_UNSUPPORTED','field':field,'index':index,'message':str(error)});continue
                if link not in links:links.append(link)
    return {'links':links,'issues':issues}


def _history_key(value):
    _keys(value,RECORD_FIELDS['HistoryKey'].split(),'History key')
    for key in ('object_ref','revision_id'):check_id(value[key])
    _sha(value['revision_sha256'])


def validate_history_bases(bases,*,history_records,members):
    _need(isinstance(bases,list) and isinstance(history_records,dict),'Invalid history basis inventory')
    member_ids={m['id'] for m in members};seen=set()
    for basis in bases:
        _keys(basis,RECORD_FIELDS['PostHistoryBasis'].split(),'Post history basis');_history_key(basis['history'])
        key=(basis['history']['object_ref'],basis['history']['revision_id'])
        _need(key not in seen,'Duplicate history basis');seen.add(key)
        _need(type(basis['version']) is int and basis['version']==1,'Unknown history basis version')
        for name in ('bindings_sha256','graph_sha256'):_sha(basis[name])
        if basis['retained_graph_sha256'] is not None:_sha(basis['retained_graph_sha256'])
        record=history_records.get(key)
        if record is None:record=history_records.get(key[0],{}).get(key[1])
        _need(isinstance(record,dict),'History basis has no exact retained history')
        core={name:record[name] for name in ('id','recipe','graph','bindings')}
        _need(canonical_hash(core)==basis['history']['revision_sha256'] and canonical_hash(record['bindings'])==basis['bindings_sha256']
            and canonical_hash(record['graph'])==basis['graph_sha256'],'History basis core digest differs')
        _need(basis['retained_graph_sha256']==(canonical_hash(record['retained_graph']) if record.get('retained_graph') is not None else None),'Retained history graph digest differs')
        _need(isinstance(basis['slots'],list),'Invalid history file slots');slots=set()
        for slot in basis['slots']:
            _keys(slot,RECORD_FIELDS['HistoryPathSlot'].split(),'History path slot');validate_reader_key(slot['reader_key'])
            _need(slot['site'] in {'graph','retained_graph','binding'} and slot['file_property']=='FileName','Unsupported history slot')
            if slot['site']=='binding':
                _need(isinstance(slot['binding_ref'],str) and slot['binding_ref'],'Missing upstream binding reference');_history_key(slot['upstream'])
                _need(record['bindings'][slot['binding_ref']]['revision']==slot['upstream']['revision_sha256'],'Upstream history binding differs')
            else:
                _need(slot['binding_ref'] is None,'Graph slot cannot name an upstream binding')
                if slot['upstream'] is not None:_history_key(slot['upstream'])
            _need(type(slot['output_port']) is int and slot['output_port']>=0 and isinstance(slot['reader_type'],str) and slot['reader_type'],'Invalid history reader/port')
            _need(slot['value_shape'] in {'scalar','list'} and type(slot['slot_count']) is int and slot['slot_count']>0
                and type(slot['element_index']) is int and 0<=slot['element_index']<slot['slot_count'],'Invalid history slot shape')
            _need(slot['value_shape']!='scalar' or (slot['slot_count']==1 and slot['element_index']==0),'Scalar history slot shape differs')
            _need(isinstance(slot['basis_value'],str) and slot['member_id'] in member_ids,'Unknown history member')
            _need(isinstance(slot['closure_member_ids'],list) and slot['member_id'] in slot['closure_member_ids'] and set(slot['closure_member_ids'])<=member_ids,'Unknown history closure member')
            _sha(slot['closure_sha256']);identity=(slot['site'],slot['binding_ref'],canonical_hash(slot['reader_key']),slot['element_index'])
            _need(identity not in slots,'Duplicate history file slot');slots.add(identity)
    return deepcopy(bases)


def validate_native_selection(value,snapshot):
    """Validate the wire shape and saved basis; actual native domain is adapter-owned."""
    _keys(value,{'version','native_kind','snapshot_sha256','selection'},'Native selection')
    _need(type(value['version']) is int and value['version']==1 and value['native_kind']==snapshot['native_kind']
        and value['snapshot_sha256']==snapshot['snapshot_sha256'],'Selection belongs to another saved snapshot')
    selected=value['selection']
    def text(item):_need(isinstance(item,str) and bool(item),'Native selection requires an exact nonempty name')
    def ordinal(item):_need(type(item) is int and item>=0,'Invalid native selection ordinal')
    if value['native_kind']=='pre':
        _keys(selected,{'document_member','occurrence_chain','object_name','subelements'},'Pre selection')
        members={m['id']:m for m in snapshot['members']}
        _need(selected['document_member'] in members and members[selected['document_member']]['role']=='pre_document','Unknown selected Pre document')
        text(selected['object_name']);_need(isinstance(selected['occurrence_chain'],list),'Invalid occurrence chain')
        for node in selected['occurrence_chain']:
            _keys(node,{'document_member','object_name'},'Pre occurrence')
            _need(node['document_member'] in members and members[node['document_member']]['role']=='pre_document','Unknown occurrence document');text(node['object_name'])
        _need(isinstance(selected['subelements'],list),'Invalid native subelements')
        for item in selected['subelements']:text(item)
    else:
        _keys(selected,{'source','view','association','array_name','component','time','block','analysis'},'Post selection')
        source=selected['source'];_keys(source,{'registration_name','proxy_type','saved_proxy_id','output_port'},'Post source')
        for field in ('registration_name','proxy_type','saved_proxy_id'):text(source[field])
        ordinal(source['output_port'])
        if selected['view'] is not None:
            _keys(selected['view'],{'registration_name','view_type','saved_proxy_id'},'Post view')
            for item in selected['view'].values():text(item)
        _need(selected['association'] is None or selected['association'] in {'POINTS','CELLS','ROWS','FIELD','VERTICES','EDGES'},'Unknown array association')
        if selected['array_name'] is not None:text(selected['array_name'])
        if selected['component'] is not None:
            component=selected['component'];_keys(component,{'mode','index'},'Array component')
            _need(component['mode'] in {'scalar','magnitude','index'},'Unknown component mode')
            if component['mode']=='index':ordinal(component['index'])
            else:_need(component['index'] is None,'Scalar/magnitude cannot carry a component index')
        if selected['time'] is not None:
            time=selected['time'];_keys(time,{'value','data_time_value','frame_index'},'Post time')
            for key in ('value','data_time_value'):
                if key=='data_time_value' and time[key] is None:continue
                _need(type(time[key]) in (int,float) and math.isfinite(time[key]),'Post selection time must be finite')
            if time['frame_index'] is not None:ordinal(time['frame_index'])
        if selected['block'] is not None:
            _keys(selected['block'],{'assembly','selectors'},'Post block');text(selected['block']['assembly'])
            _need(isinstance(selected['block']['selectors'],list) and bool(selected['block']['selectors']),'Missing assembly selectors')
            for item in selected['block']['selectors']:text(item)
        if selected['analysis'] is not None:
            _keys(selected['analysis'],{'object_ref','revision_id'},'Post analysis selection')
            for item in selected['analysis'].values():text(item)
    _json(value);return deepcopy(value)


def validate_reader_key(value):
    _keys(value,{'proxy_group','registration_name','saved_proxy_id'},'Saved reader key')
    _need(all(isinstance(item,str) and item and len(item)<=1024 for item in value.values()),'Saved reader key requires exact strings')
    return deepcopy(value)


def validate_locator(value):
    _need(isinstance(value,dict) and value.get('codec') in CODECS,'Unknown native dependency locator')
    codec=value['codec']
    if codec=='freecad_xlink_v1':
        _keys(value,{'codec','document_member','object_name','property_name','xlink_index','target_name','original_file'},'XLink locator')
        check_id(value['document_member']);_need(type(value['xlink_index']) is int and value['xlink_index']>=0,'Invalid XLink occurrence')
        _need(all(isinstance(value[key],str) for key in ('object_name','property_name','target_name','original_file')),'Invalid XLink strings')
    elif codec in {'pvd_v1','vtk_parallel_xml_v1'}:
        _keys(value,{'codec','ordinal','attributes'},'XML dependency locator')
        _need(type(value['ordinal']) is int and value['ordinal']>=0,'Invalid XML occurrence')
        _need(isinstance(value['attributes'],dict) and all(isinstance(k,str) and isinstance(v,str) for k,v in value['attributes'].items()),'Invalid XML attributes')
    elif codec=='vtk_composite_xml_v1':
        _keys(value,{'codec','hierarchy'},'Composite locator')
        _need(isinstance(value['hierarchy'],list) and 0<len(value['hierarchy'])<=16,'Invalid composite depth')
        for node in value['hierarchy']:
            _keys(node,{'tag','ordinal','attributes'},'Composite node')
            _need(isinstance(node['tag'],str) and type(node['ordinal']) is int and node['ordinal']>=0,'Invalid composite node')
            _need(isinstance(node['attributes'],dict) and all(isinstance(k,str) and isinstance(v,str) for k,v in node['attributes'].items()),'Invalid composite attributes')
    elif codec=='pvsm_reader_v1':
        _keys(value,{'codec','reader_key','file_property','element_index'},'PVSM slot')
        validate_reader_key(value['reader_key'])
        _need(value['file_property']=='FileName' and type(value['element_index']) is int and value['element_index']>=0,'Unsupported reader file property')
    elif codec=='post_manifest_v1':
        _keys(value,{'codec','field'},'Post manifest locator');_need(isinstance(value['field'],str) and value['field'],'Missing typed manifest field')
    else:
        _keys(value,{'codec','kind','field'},'Declared companion locator')
        _need(value['kind'] in METADATA_KINDS and isinstance(value['field'],str),'Unknown declared metadata companion')
    _json(value);return deepcopy(value)


def validate_issue(value):
    _keys(value,RECORD_FIELDS['Issue'].split(),'Native issue')
    _need(value['native_kind'] in {'pre','post'} and value['severity'] in {'error','warning','info'},'Invalid native issue kind/severity')
    for key in ('code','message','recovery'):_need(isinstance(value[key],str) and value[key],'Native issue requires actionable text')
    if value['source_reference'] is not None:validate_native_reference(value['source_reference'])
    if value['member_id'] is not None:check_id(value['member_id'])
    if value['locator'] is not None:validate_locator(value['locator'])
    return deepcopy(value)


def _validate_record(record,*,hash_check):
    _need(isinstance(record,dict) and set(record) in (set(SNAPSHOT_KEYS),set(SNAPSHOT_KEYS|HISTORY_FIELDS)),'Native snapshot has unexpected or missing fields');_json(record)
    _need(type(record['version']) is int and record['version']==1,'Unsupported native snapshot version')
    kind=record['native_kind'];_need(kind in {'pre','post'},'Unknown native kind')
    _need(record['input_kind']=={'pre':'native_design','post':'native_post_project'}[kind],'Native input kind mismatch')
    _need(record['format'] in ({'caepre','fcstd'} if kind=='pre' else {'post-project','pvsm'}),'Native format mismatch')
    for key in ('source_document_id','saved_revision','entry_member'):check_id(record[key])
    _need(record['native_revision'] is None or isinstance(record['native_revision'],str),'Invalid native revision')
    _need(record['identity_origin'] in {'native_manifest','embedded_metadata','registration_assigned'},'Unknown native identity origin')
    _need(record['revision_origin'] in {'native_save','registered_snapshot'},'Unknown native revision origin')
    members=record['members'];_need(isinstance(members,list) and 0<len(members)<= (1024 if kind=='pre' else 4096),'Native member count exceeds existing bound')
    index={};paths=[];total=0
    for member in members:
        _need(isinstance(member,dict),'Invalid native member')
        storage=member.get('storage')
        keys={'id','storage','role','bytes','sha256'}|({'relative'} if storage=='file' else {'archive_member_of','archive_member'} if storage=='archive_member' else set())
        _need(storage in {'file','archive_member'},'Unknown native member storage');_keys(member,keys,'Native member')
        check_id(member['id']);_need(member['id'] not in index,'Duplicate native member identity');index[member['id']]=member
        _need(member['role'] in ROLES,'Unknown native member role');_pin({key:member[key] for key in ('bytes','sha256')})
        if storage=='file':paths.append(relative_name(member['relative']));total+=member['bytes']
        else:relative_name(member['archive_member']);check_id(member['archive_member_of'])
    _need(total<=MAX_BYTES,'Native bytes exceed existing portable bound');_portable_aliases(paths)
    _need(len({p.casefold() for p in paths})==len(paths),'Duplicate native file paths')
    for member in members:
        if member['storage']=='archive_member':_need(index.get(member['archive_member_of'],{}).get('storage')=='file','Archive owner must be an exact file member')
    _need(record['entry_member'] in index and index[record['entry_member']]['storage']=='file','Native entry must be a file member')
    if record['source_manifest_pin'] is not None:
        pin=record['source_manifest_pin'];_pin(pin,member=True)
        _need(pin['member_id'] in index and all(index[pin['member_id']][k]==pin[k] for k in ('bytes','sha256')),'Original native manifest pin mismatch')
    graph={key:[] for key in index};edge_keys=set()
    _need(isinstance(record['edges'],list) and len(record['edges'])<=16384,'Invalid native edge count')
    for edge in record['edges']:
        _keys(edge,RECORD_FIELDS['RelocationBinding'].split(),'Dependency edge');validate_locator(edge['locator'])
        _need(edge['parent_member'] in index and (edge['child_member'] is None or edge['child_member'] in index),'Dependency refers to an unknown member')
        _need(type(edge['required']) is bool and isinstance(edge['original_reference'],str),'Invalid dependency declaration')
        slot=(edge['parent_member'],canonical_hash(edge['locator']))
        _need(slot not in edge_keys,'Conflicting duplicate dependency slot');edge_keys.add(slot)
        if edge['child_member'] is not None:graph[edge['parent_member']].append(edge['child_member'])
    active=set();done=set()
    def visit(key):
        _need(key not in active,'DEPENDENCY_CYCLE')
        if key in done:return
        active.add(key)
        for child in graph[key]:visit(child)
        active.remove(key);done.add(key)
    for key in graph:visit(key)
    _need(isinstance(record['reader_bindings'],list) and (kind=='post' or not record['reader_bindings']),'Pre cannot declare Post reader bindings')
    readers=set();registration_names=set()
    for reader in record['reader_bindings']:
        _keys(reader,{'reader_key','reader_type','file_property','input_slots','source_ref','history_origin','codec_ids','metadata_binding'},'Reader binding')
        validate_reader_key(reader['reader_key']);key=canonical_hash(reader['reader_key']);_need(key not in readers,'Duplicate reader registration');readers.add(key)
        name=(reader['reader_key']['proxy_group'],reader['reader_key']['registration_name'])
        _need(name not in registration_names,'Ambiguous native reader registration name');registration_names.add(name)
        _need(isinstance(reader['reader_type'],str) and reader['reader_type'] and reader['file_property']=='FileName','Unsupported reader binding')
        _need(isinstance(reader['input_slots'],list) and reader['input_slots'],'Missing ordered reader inputs')
        slots=set()
        for slot in reader['input_slots']:
            _keys(slot,{'element_index','original_value','member_id'},'Reader input slot')
            _need(type(slot['element_index']) is int and slot['element_index']>=0 and slot['element_index'] not in slots,'Duplicate/invalid reader input slot')
            slots.add(slot['element_index']);_need(slot['member_id'] in index and isinstance(slot['original_value'],str),'Invalid reader member binding')
        _need([s['element_index'] for s in reader['input_slots']]==list(range(len(slots))),'Reader input order changed')
        _need(reader['source_ref'] is None or isinstance(reader['source_ref'],str),'Invalid managed source key')
        if reader['history_origin'] is not None:
            _keys(reader['history_origin'],{'object_ref','revision_id'},'Reader history origin');_json(reader['history_origin'])
        _need(isinstance(reader['codec_ids'],list) and all(isinstance(c,str) and c for c in reader['codec_ids']),'Invalid reader codec list')
        if reader['metadata_binding'] is not None:
            pin=reader['metadata_binding'];_pin(pin,member=True)
            _need(pin['member_id'] in index and all(index[pin['member_id']][key]==pin[key] for key in ('bytes','sha256')),'Reader metadata binding differs from its pinned member')
    _need(isinstance(record['native_metadata_bindings'],list),'Invalid declared metadata')
    for binding in record['native_metadata_bindings']:
        _keys(binding,{'kind','declaration_member','declaration_sha256','data_member_ids','source_registration_origin'},'Declared metadata')
        _need(binding['kind'] in METADATA_KINDS and binding['declaration_member'] in index,'Unknown native declaration')
        _sha(binding['declaration_sha256']);_need(index[binding['declaration_member']]['sha256']==binding['declaration_sha256'],'Native declaration changed')
        _need(isinstance(binding['data_member_ids'],list) and set(binding['data_member_ids'])<=set(index),'Unknown declared data member');_json(binding['source_registration_origin'])
    _need(isinstance(record['logical_origins'],list),'Invalid logical origins')
    origins=set()
    for origin in record['logical_origins']:
        _keys(origin,{'member_id','original_location'},'Logical origin')
        _need(origin['member_id'] in index and origin['member_id'] not in origins and isinstance(origin['original_location'],str),'Invalid logical origin')
        origins.add(origin['member_id'])
    _need(isinstance(record['unavailable'],list),'Invalid missing dependencies')
    for missing in record['unavailable']:
        _keys(missing,{'parent_member','locator','expected_child','required','code'},'Missing dependency')
        _need(missing['parent_member'] in index and type(missing['required']) is bool and isinstance(missing['code'],str),'Invalid missing dependency')
        validate_locator(missing['locator'])
        if missing['expected_child'] is not None:
            expected=missing['expected_child'];_keys(expected,{'relative','bytes','sha256'},'Expected missing pin');relative_name(expected['relative']);_pin({k:expected[k] for k in ('bytes','sha256')})
    validate_declared_links(record['source_links'],native_kind=kind)
    for link in record['source_links']:
        site=link['source'];target=link['target']
        if site['kind']=='pre_object':_need(site['document_member'] in index and index[site['document_member']]['role']=='pre_document','Unknown native link document member')
        if target['kind']=='job_history':
            for field,role in [('job','research_job_record'),('submitted_input','research_input_record'),('result','research_result_record')]:
                member=target['records'][field]
                if member is not None:_need(member in index and index[member]['role']==role,'Historical job references an undeclared/wrong record member')
            for member in target['output_members']:_need(member in index and index[member]['role']=='research_output','Historical output references an undeclared/wrong member')
    for name in HISTORY_FIELDS:_need(isinstance(record.get(name,[]),list),'Invalid native history inventory')
    if kind=='pre':_need(not record.get('relocation_bases') and not record.get('history_availability'),'Pre snapshot cannot declare Post history')
    for basis in record.get('relocation_bases',[]):
        _keys(basis,RECORD_FIELDS['PostHistoryBasis'].split(),'Post history basis');_history_key(basis['history']);_json(basis)
    for availability in record.get('history_availability',[]):
        _keys(availability,RECORD_FIELDS['HistoryAvailability'].split(),'History availability');_history_key(availability['history'])
        _need(availability['state'] in {'AVAILABLE','RETAINED_ONLY','UNAVAILABLE_DECLARED'},'Unknown retained history availability')
        _sha(availability['record_sha256']);_need(isinstance(availability['missing'],list),'Invalid history missing declarations')
        _need(availability['reason_code'] is None or isinstance(availability['reason_code'],str),'Invalid history availability reason')
    _keys(record['producer'],{'application','version','origin'},'Native producer')
    _need(record['producer']['application']=={'pre':'freecad','post':'paraview'}[kind] and record['producer']['origin'] in {'trusted_save','saved_metadata','unknown'},'Native producer mismatch')
    _need(record['producer']['version'] is None or isinstance(record['producer']['version'],str),'Invalid producer version')
    _need(isinstance(record['required_capabilities'],list) and len(set(record['required_capabilities']))==len(record['required_capabilities']) and all(isinstance(v,str) and v for v in record['required_capabilities']),'Invalid required capabilities')
    _keys(record['validation'],{'closure','issues'},'Closure validation')
    _need(record['validation']['closure'] in {'COMPLETE','DECLARED_PARTIAL'},'Unknown closure state')
    for issue in record['validation']['issues']:validate_issue(issue)
    if record['validation']['closure']=='COMPLETE':
        _need(not record['unavailable'] and not any(e['required'] and e['child_member'] is None for e in record['edges']),'Incomplete native dependency closure')
        _need(not any(issue['severity']=='error' for issue in record['validation']['issues']),'Unsupported native branch cannot be a complete closure')
    if hash_check:_sha(record['snapshot_sha256']);_need(snapshot_digest(record)==record['snapshot_sha256'],'SNAPSHOT_CHANGED')
    return deepcopy(record)


def snapshot_digest(record):return canonical_hash({k:v for k,v in record.items() if k!='snapshot_sha256'})


def saved_basis(record):
    return {'native_kind':record['native_kind'],'source_document_id':record['source_document_id'],'format':record['format'],
        'entry_member':record['entry_member'],'source_manifest_pin':deepcopy(record['source_manifest_pin']),
        'members':sorted(deepcopy(record['members']),key=lambda m:m['id']),'edges':deepcopy(record['edges']),
        'reader_bindings':deepcopy(record['reader_bindings']),
        'declared_native_metadata_pins':[{k:deepcopy(b[k]) for k in ('kind','declaration_member','declaration_sha256','data_member_ids')}
            for b in record['native_metadata_bindings']]}


def saved_revision_for(record):return 'R'+canonical_hash(saved_basis(record))


def finalize_snapshot(record):
    record=deepcopy(record)
    if record.get('revision_origin')=='registered_snapshot' or record.get('native_kind')=='post':record['saved_revision']=saved_revision_for(record)
    record['snapshot_sha256']=snapshot_digest(record)
    return validate_snapshot(record)


def validate_snapshot(record):
    value=_validate_record(record,hash_check=True)
    if value['revision_origin']=='registered_snapshot' or value['native_kind']=='post':
        _need(value['saved_revision']==saved_revision_for(value),'Saved basis revision mismatch')
    return value


def snapshot_reference(receipt,record):
    record=validate_snapshot(record)
    _need(receipt.get('kind')==record['input_kind'] and receipt.get('format')==record['format'],'Input/snapshot kind mismatch')
    files={f['relative']:f for f in receipt['files']}
    _need(len(files)==len(receipt['files']),'Duplicate registered files')
    for member in record['members']:
        if member['storage']=='file':
            pin=files.get(member['relative']);_need(pin is not None and all(pin[k]==member[k] for k in ('bytes','sha256')),'Registered file/snapshot mismatch')
    entry=next(m for m in record['members'] if m['id']==record['entry_member'])
    _need(receipt['file']==files[entry['relative']]['file'],'Registered native entry mismatch')
    return validate_native_reference({'kind':'native_'+record['native_kind'],'version':1,'document_id':record['source_document_id'],
        'saved_revision':record['saved_revision'],'input_id':receipt['id'],'snapshot_sha256':record['snapshot_sha256']})


def project_native_reference(reference,mapping):
    reference=validate_native_reference(reference)
    rows=mapping.get('native_mapping',[]) if isinstance(mapping,dict) else mapping
    found=[row for row in rows if all(row[key]==reference[ref] for key,ref in (
        ('source_kind','kind'),('source_document_id','document_id'),('source_saved_revision','saved_revision'),('snapshot_sha256','snapshot_sha256')))]
    _need(len(found)==1,'Native saved reference has no exact local mapping')
    return validate_native_reference({**reference,'input_id':found[0]['local_input_id']})


def validate_native_mapping(rows):
    _need(isinstance(rows,list),'Invalid native projection mapping');seen=set();inputs=set()
    for row in rows:
        _keys(row,{'source_kind','source_document_id','source_saved_revision','snapshot_sha256','local_input_id','target_id'},'Native projection mapping')
        validate_native_reference({'kind':row['source_kind'],'version':1,'document_id':row['source_document_id'],
            'saved_revision':row['source_saved_revision'],'input_id':row['local_input_id'],'snapshot_sha256':row['snapshot_sha256']})
        if row['target_id'] is not None:check_id(row['target_id'])
        key=(row['source_kind'],row['source_document_id'],row['source_saved_revision'],row['snapshot_sha256'])
        _need(key not in seen and row['local_input_id'] not in inputs,'Duplicate native projection mapping')
        seen.add(key);inputs.add(row['local_input_id'])
    return deepcopy(rows)


def validate_relocation_record(value,*,source_snapshot=None):
    """Strict declared allowed-diff record; native adapters verify actual diffs."""
    _keys(value,RECORD_FIELDS['RelocationRecord'].split(),'Native relocation record')
    _need(type(value['version']) is int and value['version']==1 and value['original_data_unchanged'] is True,'Unverified native relocation declaration')
    _sha(value['source_snapshot_sha256']);check_id(value['open_id'])
    if value['target_id'] is not None:check_id(value['target_id'])
    _need(isinstance(value['algorithm_version'],str) and value['algorithm_version'],'Missing relocation algorithm version')
    members=None
    if source_snapshot is not None:
        _need(value['source_snapshot_sha256']==source_snapshot['snapshot_sha256'],'Relocation belongs to another source snapshot')
        members={m['id'] for m in source_snapshot['members']}
    _need(isinstance(value['derived_members'],list),'Invalid derived member inventory');seen=set();paths=[]
    for row in value['derived_members']:
        _keys(row,{'source_member','derived_relative','bytes','sha256','edits'},'Derived native member')
        check_id(row['source_member']);_need(row['source_member'] not in seen,'Duplicate relocation source member');seen.add(row['source_member'])
        if members is not None:_need(row['source_member'] in members,'Relocation source member is not registered')
        paths.append(relative_name(row['derived_relative']));_pin({k:row[k] for k in ('bytes','sha256')})
        _need(isinstance(row['edits'],list),'Invalid relocation edits')
        for edit in row['edits']:
            _keys(edit,{'locator','old_value','new_value'},'Allowed relocation edit');validate_locator(edit['locator'])
            _need(isinstance(edit['old_value'],str) and isinstance(edit['new_value'],str),'Invalid native path edit')
    _portable_aliases(paths)
    if value['identity_edit'] is not None:
        _keys(value['identity_edit'],{'source_document_id','owner_document_id'},'Native identity initialization')
        if value['identity_edit']['source_document_id'] is not None:check_id(value['identity_edit']['source_document_id'])
        check_id(value['identity_edit']['owner_document_id'])
    _json(value);return deepcopy(value)


_SEAL=object()
@dataclass(frozen=True)
class CompletedSaveWitness:
    native_kind:str
    saved_file:Path
    owner_stamp:dict
    command_id:str
    publication_complete:bool
    source:dict
    pin:dict
    _seal:object=field(repr=False,compare=False)
    def __post_init__(self):_need(self._seal is _SEAL,'Completed native Save witness must come from its actual adapter')


def _completed_save_witness(native_kind,saved_file,*,owner_stamp,command_id,publication_complete,source):
    from .portable_project_io import fingerprint_file
    _need(native_kind in {'pre','post'} and isinstance(owner_stamp,dict) and type(publication_complete) is bool,'Invalid native Save witness')
    _keys(owner_stamp,{'document_id','kind','session_id','generation','view_generation','saved_revision','graph_version'},'Native owner stamp')
    _need(owner_stamp['kind']==native_kind,'Native Save owner kind differs')
    for key in ('document_id','session_id'):check_id(owner_stamp[key])
    if owner_stamp['saved_revision'] is not None:
        _need(isinstance(owner_stamp['saved_revision'],str) and 0<len(owner_stamp['saved_revision'])<=1024,'Invalid native saved revision stamp')
    for key in ('generation','view_generation'):_need(type(owner_stamp[key]) is int and owner_stamp[key]>=0,'Invalid native owner generation')
    _need(isinstance(owner_stamp['graph_version'],str),'Native graph stamp must be a string')
    check_id(command_id);path=Path(saved_file).resolve(strict=True)
    return CompletedSaveWitness(native_kind,path,deepcopy(owner_stamp),command_id,publication_complete,
        deepcopy(source),fingerprint_file(path),_SEAL)


@dataclass(frozen=True)
class VerifiedNativeInput:
    reference:dict
    receipt:dict
    snapshot:dict
    entry_path:Path
    member_paths:dict
    full:bool
    context_session:str
    _seal:object=field(repr=False,compare=False)
    def __post_init__(self):_need(self._seal is _SEAL,'Native input must be verified by the current file adapter')


@dataclass(frozen=True)
class OpenBinding:
    open_id:str
    request_sha256:str
    open_intent:str
    source_reference:dict
    owner_document_id:str
    owner_id_map:list
    target_id:str|None
    expected_head:dict|None
    materialization_root:Path
    native_save_root:Path|None
    verified_input:VerifiedNativeInput
    member_paths:dict
    relocation:dict
    history_bases:list
    context_session:str
    _seal:object=field(repr=False,compare=False)
    def __post_init__(self):_need(self._seal is _SEAL,'Native open binding must come from a verified current ticket')
    @property
    def intent(self):return self.open_intent
    @property
    def reference(self):return self.source_reference
    @property
    def working_document_id(self):return self.owner_document_id
    @property
    def working_root(self):return self.materialization_root
    @property
    def target_root(self):return self.native_save_root.parent if self.native_save_root else self.materialization_root.parents[1]
    @property
    def reader_bindings(self):return self.verified_input.snapshot['reader_bindings']


@dataclass(frozen=True)
class NativeTargetSaveBinding:
    save_id:str
    save_command_id:str
    open_id:str
    owner_document_id:str
    target_id:str
    expected_stamp:dict
    expected_head:dict|None
    creation:str
    source_reference:dict
    native_save_root:Path
    request_sha256:str
    _seal:object=field(repr=False,compare=False)
    def __post_init__(self):_need(self._seal is _SEAL,'Native target Save must come from the current verified reservation')


def require_target_save(value):
    _need(type(value) is NativeTargetSaveBinding and value._seal is _SEAL,'Caller dictionaries are not native target Save reservations')
    _need(value.creation in {'NEW_TARGET','EXISTING_TARGET'},'Unknown native Save reservation')
    for key in ('save_id','save_command_id','open_id','owner_document_id','target_id'):check_id(getattr(value,key))
    validate_native_reference(value.source_reference);_sha(value.request_sha256)
    return value


@dataclass(frozen=True)
class VerifiedReplacementMap:
    source_path:Path
    source_pin:dict
    rows:tuple
    context_session:str
    _state:dict=field(repr=False,compare=False)
    _seal:object=field(repr=False,compare=False)
    def __post_init__(self):_need(self._seal is _SEAL,'Replacement maps must come from existing registered inputs')
    def resolve(self,parent_member,locator,*,expected_child):
        from .portable_project_io import fingerprint_file
        validate_locator(locator)
        _need(expected_child is not None,'REPLACEMENT_UNBOUND: the original source has no expected child pin')
        _keys(expected_child,{'relative','bytes','sha256'},'Original expected replacement pin');relative_name(expected_child['relative']);_pin({k:expected_child[k] for k in ('bytes','sha256')})
        found=[(i,row) for i,row in enumerate(self.rows) if row['parent_member']==parent_member and row['locator']==locator]
        _need(len(found)==1,'REPLACEMENT_UNBOUND: this exact source edge was not selected')
        index,row=found[0]
        _need(row['expected_child']==expected_child,'REPLACEMENT_UNBOUND: caller expected pin differs from the original saved source evidence')
        _need(fingerprint_file(self.source_path)==self.source_pin,'INPUT_CHANGED: replacement source declaration changed')
        self._verify_row(row);self._state['consumed'].add(index)
        return deepcopy({key:row[key] for key in ('source','relative','bytes','sha256','replacement_input_id','replacement_member','files')})
    def has(self,parent_member,locator):
        return any(row['parent_member']==parent_member and row['locator']==locator for row in self.rows)
    def _verify_row(self,row):
        from .portable_project_io import fingerprint_file
        _need(fingerprint_file(row['receipt_path'])['sha256']==row['receipt_sha256'],'Registered replacement receipt changed')
        for pin in row['files']:
            _need(fingerprint_file(pin['source'])=={key:pin[key] for key in ('bytes','sha256')},'Registered replacement file changed')
    def verify_consumed(self):
        _need(self._state['consumed']==set(range(len(self.rows))),'REPLACEMENT_UNBOUND: a selected replacement did not match an authoritative source edge')
        for row in self.rows:self._verify_row(row)
        self._state['source_verified']=True
    def permits(self,path,pin):
        path=Path(path)
        found=[row for row in self.rows for row in row['files'] if row['source']==path]
        if not found:return False
        _need(all(all(row[key]==pin[key] for key in ('bytes','sha256')) for row in found),'Replacement plan changed a registered pin')
        return True


def require_replacement_map(value):
    _need(type(value) is VerifiedReplacementMap and value._seal is _SEAL,'Caller dictionaries are not verified replacement mappings')
    return value


@dataclass(frozen=True)
class NativeOpenTicket:
    binding:OpenBinding
    verified_input:VerifiedNativeInput
    derived:dict
    status:str
    _seal:object=field(repr=False,compare=False)
    def __post_init__(self):_need(self._seal is _SEAL,'Native open ticket must come from the current file adapter')


def require_verified_input(value,*,full=True):
    _need(type(value) is VerifiedNativeInput and value._seal is _SEAL,'Caller dictionaries are not verified native input')
    _need(not full or value.full is True,'Full native verification is required')
    validate_native_reference(value.reference);validate_snapshot(value.snapshot)
    _need(value.reference==snapshot_reference(value.receipt,value.snapshot),'Verified native input changed')
    return value


def require_open_binding(value):
    _need(type(value) is OpenBinding and value._seal is _SEAL,'Caller dictionaries are not trusted open bindings')
    validate_native_reference(value.reference)
    return value
