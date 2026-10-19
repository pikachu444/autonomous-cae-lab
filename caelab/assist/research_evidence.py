"""Research-team supplied-input provenance and recipient-safe projections.

DiscussionDocuments remains the owner; these records are checkpointed through its
existing bounded assets. Model citations never create a dependency or a grant.
"""
from copy import copy,deepcopy
import json
import threading
import uuid

from ..storage import canonical_hash
from .knowledge import selected_source_refs

KINDS = {'knowledge','literature','result','authored','role_definition','response','analysis','tool_output'}
ORIGINS = {'prompt','auto_snippet','history','forwarded_turn','tool_return','consultation','map_base'}
MODES = {'initial','tool_followup','repair','map','report','public_clean'}


def _bytes(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,allow_nan=False,separators=(',',':')).encode('utf-8')


def _identifier(prefix):
    return prefix+'-'+uuid.uuid4().hex


def _matches(reference, grants):
    """Match existing exact reference fields; never infer a later revision."""
    for grant in grants:
        if not isinstance(grant,dict): continue
        locator=grant.get('locator')
        keys={k:v for k,v in grant.items() if k!='locator'}
        if all(reference.get(k)==v for k,v in keys.items()) and (not locator or
                all(reference.get('locator',{}).get(k)==v for k,v in locator.items())):
            return True
    return False


def _state(scope):
    ledger=scope.get('generation_ledger')
    return ledger.state if ledger is not None else scope.get('ledger_state',{})


def dependency_closure(dependencies, identifiers):
    """The complete transitive set, including errors and uncited supplied input."""
    found=set(); visiting=set()
    def visit(identifier):
        if identifier in found:return
        if identifier in visiting or identifier not in dependencies:
            raise ValueError('DEPENDENCY_UNVERIFIED')
        visiting.add(identifier)
        row=dependencies[identifier]
        if row.get('id')!=identifier or row.get('kind') not in KINDS:
            raise ValueError('DEPENDENCY_UNVERIFIED')
        for parent in row['parent_ids']:visit(parent)
        visiting.remove(identifier);found.add(identifier)
    for identifier in identifiers:visit(identifier)
    return sorted(found)


def _context_for(scope, actor):
    contexts=scope.get('recipient_contexts',{})
    return contexts.get(actor,scope.get('context',{}))


def _check_dependency(row, actor, *, runtime, workspace_id, scope, public=False):
    """Reuse current store/registry/transmission checks before returning bytes."""
    context=_context_for(scope,actor)
    assignment=scope.get('assignments',{}).get(actor)
    if not isinstance(assignment,dict) or actor not in runtime.definitions:raise PermissionError('BLOCKED_SCOPE')
    definition=runtime.describe(actor)
    ref=row['exact_ref'];kind=row['kind']
    if kind=='knowledge':
        pins=selected_source_refs(context)
        if not _matches(ref,pins):raise PermissionError('BLOCKED_SCOPE')
        runtime.knowledge.check_access(ref['document_id'],ref['revision'],workspace_id=workspace_id,
            collections=definition.get('collections',[]))
        details=runtime.knowledge.revision_details(ref['document_id'],ref['revision'],
            workspace_id=workspace_id,collections=definition.get('collections',[]))
        # Current local grant is not inferred from archived origin metadata.
        if public:
            with runtime.knowledge._lock:
                runtime.knowledge.check_access(ref['document_id'],ref['revision'],workspace_id=workspace_id,
                    collections=definition.get('collections',[]))
                if runtime.knowledge._data['documents'][ref['document_id']]['access_scope']!='public':
                    raise PermissionError('PUBLIC_QUERY_DEPENDS_ON_RESTRICTED_INPUT')
        if ref.get('sha256') and ref['sha256']!=details['source_sha256']:
            raise ValueError('DEPENDENCY_UNVERIFIED')
        actual=runtime.knowledge.source(ref['document_id'],ref['revision'],ref.get('locator'),
            workspace_id=workspace_id,collections=definition.get('collections',[]))
        if not any(canonical_hash(segment['text'])==row['content_digest'] for segment in actual['segments']):
            raise ValueError('DEPENDENCY_UNVERIFIED')
        runtime._transmission_check({'document_id':ref['document_id'],'revision':ref['revision'],
            'collection':runtime.knowledge._data['documents'][ref['document_id']]['collection']},context)
    elif kind=='literature':
        if not {'literature.search','literature.read'}<=set(definition.get('tools',[])) & set(assignment.get('tools',[])):
            raise PermissionError('BLOCKED_SCOPE')
        from .literature import archive_digest
        if not (runtime.runtime.transmission or {}).get('allow_public_search') or not context.get('transmission_scope',{}).get('allow_public_search'):
            raise PermissionError('BLOCKED_SCOPE')
        locator=ref.get('locator',{})
        archive=locator.get('archive_id')
        if not archive:raise ValueError('DEPENDENCY_UNVERIFIED')
        value=runtime.literature.read(ref['paper_id'],{'archive_id':archive})
        if archive_digest(value)!=archive:raise ValueError('DEPENDENCY_UNVERIFIED')
        if {k:v for k,v in locator.items() if k!='archive_id'}:
            runtime.literature.read(ref['paper_id'],locator)
        runtime._transmission_check(ref,context)
    elif kind=='result':
        if public:raise PermissionError('PUBLIC_QUERY_DEPENDS_ON_RESTRICTED_INPUT')
        selections=assignment.get('result_refs',[])
        access=scope.get('result_access')
        if access is None:raise ValueError('DEPENDENCY_UNVERIFIED')
        access.check_reference(ref,row['selector'],selections=selections,context=context)
    elif kind in {'response','analysis','tool_output'}:
        if not row.get('parent_ids'):raise ValueError('DEPENDENCY_UNVERIFIED')
        if kind=='tool_output' and ref.get('tool','').startswith('literature.'):
            if (not (runtime.runtime.transmission or {}).get('allow_public_search')
                    or not context.get('transmission_scope',{}).get('allow_public_search')
                    or ref['tool'] not in set(definition.get('tools',[])) & set(assignment.get('tools',[]))):
                raise PermissionError('BLOCKED_SCOPE')
    elif kind=='authored':
        # Authored question transmission is still the existing operator + request gate.
        runtime._transmission_check({'question':'scope check'},context)
    elif kind=='role_definition':
        # Definitions are versioned input, not permission certificates.
        if ref.get('expert_id') not in runtime.definitions:raise PermissionError('BLOCKED_SCOPE')


def check_dependencies(identifiers, *, runtime, workspace_id, current_scope, recipients, public=False):
    dependencies=_state(current_scope).get('dependencies',{})
    closure=dependency_closure(dependencies,identifiers)
    if not recipients:raise PermissionError('BLOCKED_SCOPE')
    for actor in recipients:
        for identifier in closure:
            _check_dependency(dependencies[identifier],actor,runtime=runtime,workspace_id=workspace_id,
                scope=current_scope,public=public)
    return closure


class GenerationLedger:
    def __init__(self,binding_ids,*,runtime,workspace_id,context,checkpoint,state=None):
        self.binding_ids=deepcopy(binding_ids);self.runtime=runtime;self.workspace_id=workspace_id
        self.context=deepcopy(context);self.checkpoint=checkpoint;self.lock=threading.RLock()
        self.state={key:deepcopy((state or {}).get(key,{})) for key in ('dependencies','manifests','read_receipts','outputs')}
        self.supplied=[];self.manifest_ids=[];self.active_dependencies=[];self.read_receipt_ids=[]

    def _commit(self,state,event):
        from ..portable_project_io import MAX_JSON_BYTES
        if len(_bytes(state))>MAX_JSON_BYTES:raise ValueError('Existing research asset limit exceeded')
        changes={key:{identifier:deepcopy(row) for identifier,row in rows.items()
            if self.state.get(key,{}).get(identifier)!=row} for key,rows in state.items()}
        receipt=self.checkpoint(event+'-'+canonical_hash(state)[:20],changes)
        self.state=state
        return receipt

    def add_supplied(self,item,*,dependencies,origin):
        if not isinstance(item,dict) or item.get('kind') not in KINDS or origin not in ORIGINS:
            raise ValueError('Trusted supplied input requires an exact kind and origin')
        with self.lock:
            parents=dependency_closure(self.state['dependencies'],dependencies)
            row={'kind':item['kind'],'exact_ref':deepcopy(item.get('exact_ref',{})),
                'selector':deepcopy(item.get('selector')),'content_digest':canonical_hash(item['payload']),
                'parent_ids':parents,'introduced_by':origin}
            row['id']='dep-'+canonical_hash(row)
            state=deepcopy(self.state);state['dependencies'][row['id']]=row
            self._commit(state,'dependency-'+row['id'])
            if row['id'] not in self.active_dependencies:self.active_dependencies.append(row['id'])
            self.supplied.append({'dependency_id':row['id'],'payload_digest':row['content_digest']})
            return {'id':row['id']}

    def begin_model(self,payload,*,mode):
        if mode not in MODES:raise ValueError('Unknown tracked model input mode')
        encoded=_bytes(payload)
        if len(encoded)>self.runtime.runtime.max_payload_bytes:raise ValueError('Model payload exceeds the existing transmission bound')
        with self.lock:
            identifiers=dependency_closure(self.state['dependencies'],self.active_dependencies)
            row={'id':_identifier('manifest'),**self.binding_ids,'host_invocation_id':_identifier('invocation'),
                'mode':mode,'payload_digest':canonical_hash(payload),'payload_bytes':len(encoded),
                'dependency_ids':identifiers,'coverage':'COMPLETE_SUPPLIED_INPUT' if self.supplied else 'UNVERIFIED','status':'STARTED'}
            # Binding IDs are exactly the five persisted contract fields.
            row={key:row[key] for key in ('id','owner_id','phase_id','task_id','actor_id','attempt_id',
                'host_invocation_id','mode','payload_digest','payload_bytes','dependency_ids','coverage','status')}
            state=deepcopy(self.state);state['manifests'][row['id']]=row
            self._commit(state,'model-input-'+row['id']);self.manifest_ids.append(row['id'])
            return deepcopy(row)

    def finish_model(self,manifest_id,*,output_ref):
        with self.lock:
            row=self.state['manifests'][manifest_id]
            if any(row[k]!=self.binding_ids[k] for k in ('owner_id','phase_id','task_id','actor_id','attempt_id')):
                raise PermissionError('Manifest belongs to another task or actor')
            state=deepcopy(self.state);state['manifests'][manifest_id]['status']='COMPLETED'
            closure=dependency_closure(state['dependencies'],row['dependency_ids']+self.active_dependencies)
            state['manifests'][manifest_id]['dependency_ids']=closure
            # A CLI host may make internal follow-up turns without a new local
            # BeforeModel hook. Conservatively bind all returned tool inputs.
            prior=state['outputs'].get(canonical_hash(output_ref),{})
            value={'output_ref':deepcopy(output_ref),'dependency_ids':closure,
                'input_manifest_ids':list(dict.fromkeys(prior.get('input_manifest_ids',[])+[manifest_id])),
                'coverage':row['coverage']}
            state['outputs'][canonical_hash(output_ref)]=value
            self._commit(state,'model-output-'+manifest_id)
            return deepcopy(value)

    def retain_payload(self,payload,*,prefix='read'):
        identifier=_identifier(prefix)
        receipt=self.checkpoint(identifier,{'asset':{'id':identifier,'payload':deepcopy(payload)}})
        reference=receipt.get('asset_ref') if isinstance(receipt,dict) else None
        if not reference:raise ValueError('The owner did not retain the bounded payload')
        return reference

    def lookup_operation(self,kind,key):
        probe=getattr(self,'current_state_probe',None)
        if callable(probe):
            self.state['outputs'].update(deepcopy(probe().get('ledger_state',{}).get('outputs',{})))
        row=deepcopy(self.state['outputs'].get(kind+':'+key))
        if row is None:return None
        payload=None
        if row.get('payload_ref'):
            resolver=getattr(self,'resolve_payload',None)
            if not callable(resolver):raise ValueError('Owner payload resolver is unavailable')
            payload=resolver(row['payload_ref'])
            if canonical_hash(payload)!=row['payload_digest']:raise ValueError('Retained operation changed')
        return {'status':row['status'],'payload':payload,'metadata':row['metadata']}

    def record_operation(self,kind,key,payload,metadata):
        with self.lock:
            row={'status':metadata['status'],'metadata':deepcopy(metadata)}
            if payload is not None:
                row.update(payload_ref=self.retain_payload(payload,prefix=kind),payload_digest=canonical_hash(payload))
            state=deepcopy(self.state);state['outputs'][kind+':'+key]=row
            self._commit(state,kind+'-operation-'+key+'-'+metadata['status'])
            return deepcopy(row)

    def retain_read(self,receipt,payload):
        with self.lock:
            receipt=deepcopy(receipt)
            receipt['payload_ref']=self.retain_payload(payload)
            state=deepcopy(self.state);state['read_receipts'][receipt['id']]=receipt
            self._commit(state,'read-receipt-'+receipt['id'])
            if receipt['id'] not in self.read_receipt_ids:self.read_receipt_ids.append(receipt['id'])
            return receipt


def record_read(returned,*,tool,request,source_reference,actual_selector,input_dependencies):
    kind='result' if tool=='results.read' else 'literature' if tool.startswith('literature.') else 'knowledge' if tool.startswith('knowledge.') else 'tool_output'
    status=returned.get('status','RETURNED') if isinstance(returned,dict) else 'RETURNED'
    level={'abstract_only':'ABSTRACT','metadata_only':'BIBLIOGRAPHIC','fulltext':'SELECTED_TEXT',
        'access_unavailable':'UNAVAILABLE','NO_MATCHING_SEGMENTS':'NO_MATCHING_SEGMENTS'}.get(status,
        'RESULT_VALUES' if kind=='result' else 'SELECTED_TEXT' if kind=='knowledge' and tool=='knowledge.source' else 'DISCOVERY_ONLY')
    if kind=='result':
        level='RESULT_METADATA' if isinstance(actual_selector,dict) and actual_selector.get('metadata_only') is True else 'RESULT_VALUES'
    limitations=deepcopy(returned.get('limitations',returned.get('failed_segments',[]))) if isinstance(returned,dict) else []
    return {'id':_identifier('read'),'kind':kind,'request_digest':canonical_hash(request),
        'source_ref':deepcopy(source_reference),'requested_selector':deepcopy(request.get('selection',request.get('locator'))),
        'returned_selector':deepcopy(actual_selector),'read_level':level,'returned_digest':canonical_hash(returned),
        'returned_bytes':len(_bytes(returned)),'payload_ref':None,'dependency_ids':sorted(set(input_dependencies)),
        'status':status,'limitations':limitations}


def shared_projection(response,recipients,*,runtime,workspace_id,current_scope):
    """All-or-nothing response/derived view, checked again even for cached bodies."""
    identifiers=response.get('dependency_ids')
    blocked={'status':'DEPENDENCY_UNVERIFIED','projection':None,'dependency_ids':[],
        'reason_code':'DEPENDENCY_UNVERIFIED'}
    if not isinstance(identifiers,list) or not identifiers:return blocked
    try:
        state=_state(current_scope)
        manifests=[state.get('manifests',{}).get(identifier) for identifier in response.get('input_manifest_ids',[])]
        if any(not row or row.get('coverage')!='COMPLETE_SUPPLIED_INPUT' for row in manifests):
            raise ValueError('DEPENDENCY_UNVERIFIED')
        closure=check_dependencies(identifiers,runtime=runtime,workspace_id=workspace_id,
            current_scope=current_scope,recipients=recipients)
        reference=response.get('raw_response_ref',response.get('body_ref'))
        projection=(current_scope['resolve_payload'](reference) if reference is not None else deepcopy(response))
        # Revalidate after the bounded owner asset read; revocation cannot race a cached return.
        check_dependencies(closure,runtime=runtime,workspace_id=workspace_id,current_scope=current_scope,recipients=recipients)
        return {'status':'AVAILABLE','projection':deepcopy(projection),'dependency_ids':closure,'reason_code':None}
    except PermissionError:
        return {**blocked,'status':'BLOCKED_SCOPE','reason_code':'BLOCKED_SCOPE'}
    except (ValueError,KeyError,OSError,TypeError):return blocked


def local_projection(record,*,state,resolve_payload,check_dependency):
    """Owner-authorized local facet; no model, role or transmission permission.

    The owner adapter supplies existing current local checks. Missing navigation
    may retain an authorized frozen body; denial can never use that fallback.
    """
    blocked={'status':'DEPENDENCY_UNVERIFIED','projection':None,'dependency_ids':[],
        'reason_code':'DEPENDENCY_UNVERIFIED'}
    try:
        identifiers=record.get('dependency_ids')
        if not isinstance(identifiers,list) or not identifiers:raise ValueError('DEPENDENCY_UNVERIFIED')
        closure=dependency_closure(state.get('dependencies',{}),identifiers)
        unavailable=False
        def recheck():
            missing=False
            for identifier in closure:
                verdict=check_dependency(deepcopy(state['dependencies'][identifier]))
                if verdict is True:continue
                if isinstance(verdict,dict) and verdict.get('status') in {'AVAILABLE','SOURCE_UNAVAILABLE'}:
                    missing=missing or verdict['status']=='SOURCE_UNAVAILABLE';continue
                raise PermissionError('BLOCKED_SCOPE')
            return missing
        unavailable=recheck()
        reference=record.get('raw_response_ref',record.get('body_ref'))
        payload=resolve_payload(reference) if reference is not None else deepcopy(record)
        if record.get('payload_digest') and canonical_hash(payload)!=record['payload_digest']:
            raise ValueError('DEPENDENCY_UNVERIFIED')
        unavailable=recheck() or unavailable
        return {'status':'AVAILABLE','projection':deepcopy(payload),'dependency_ids':closure,
            'reason_code':'SOURCE_UNAVAILABLE' if unavailable else None}
    except PermissionError:return {**blocked,'status':'BLOCKED_SCOPE','reason_code':'BLOCKED_SCOPE'}
    except (ValueError,KeyError,OSError,TypeError):return blocked


def role_context(assignment,frozen_request,*,runtime,workspace_id,visibility,accepted_responses):
    context=deepcopy(frozen_request.get('context',frozen_request))
    team=context.pop('research_team',{})
    # Role payload contains the common objective and its own authored assignment.
    # Other roles' source pins, carry-forward and generated protocol state are not input.
    context['research_team']={key:deepcopy(team[key]) for key in ('objective','deliverable') if key in team}
    context['research_team']['assignment']=deepcopy(assignment)
    for name in ('carry_forward','costorm','costorm_protocol','protocol','accepted_responses'):
        context.pop(name,None)
    pins=[{k:ref[k] for k in ('document_id','revision')} for ref in assignment['source_refs'] if 'document_id' in ref]
    # The ordinary context API requires one revision per document.
    pins=list({ref['document_id']:ref for ref in pins}.values())
    context['selected_sources']=pins;context['selected_document_ids']=[ref['document_id'] for ref in pins]
    context['selected_result_ids']=list(dict.fromkeys(row['reference']['job_id'] for row in assignment['result_refs']))
    context['result_selections']=deepcopy(assignment['result_refs'])
    if visibility=='independent':
        for name in ('discussion','history','knowledge_base','map','report','shared_responses'):context.pop(name,None)
        context['consult_experts']=[]
    elif visibility!='shared':raise ValueError('Select independent or shared role input')
    else:
        # A separately projects and records the actual forwarded target. A list
        # of stored response metadata is neither a permission nor supplied text.
        context.pop('shared_responses',None)
    supplied=[{'kind':'authored','exact_ref':{'kind':'authored_question'},'payload':{
        'question':assignment['question'],'objective':context.get('research_team',{}).get('objective')},'origin':'prompt','dependency_ids':[]},
        {'kind':'role_definition','exact_ref':{'expert_id':assignment['expert_id']},
         'payload':runtime.describe(assignment['expert_id']),'origin':'prompt','dependency_ids':[]}]
    return {'context':context,'supplied_items':supplied,'dependency_ids':[]}


def to_costorm_information(read_receipt,*,current_scope):
    """Only an already checked, exact bounded read may become upstream evidence."""
    checker=current_scope.get('check_receipt')
    if not callable(checker) or checker(read_receipt) is not True:raise PermissionError('BLOCKED_SCOPE')
    resolver=current_scope.get('resolve_payload')
    if not callable(resolver) or read_receipt.get('payload_ref') is None:raise ValueError('DEPENDENCY_UNVERIFIED')
    payload=resolver(read_receipt['payload_ref'])
    if canonical_hash(payload)!=read_receipt['returned_digest']:raise ValueError('DEPENDENCY_UNVERIFIED')
    from ._vendor.costorm.interface import Information
    return Information(url='caelab-read:'+read_receipt['id'],description=read_receipt['read_level'],
        title=payload.get('title',payload.get('paper',{}).get('title',read_receipt['read_level'])) if isinstance(payload,dict) else read_receipt['read_level'],
        snippets=[json.dumps(payload,ensure_ascii=False)],meta={'source':deepcopy(read_receipt['source_ref']),
            'question':current_scope.get('read_question') or 'Not applicable (direct retained read)',
            'query':current_scope.get('read_query') or 'Not applicable (direct retained read)'})


def check_receipt(receipt,*,runtime,workspace_id,current_scope,recipients):
    """An upstream evidence conversion is another current, whole-input read."""
    retained=_state(current_scope).get('read_receipts',{}).get(receipt.get('id'))
    if retained!=receipt or not receipt.get('payload_ref'):raise ValueError('DEPENDENCY_UNVERIFIED')
    check_dependencies(receipt['dependency_ids'],runtime=runtime,workspace_id=workspace_id,
        current_scope=current_scope,recipients=recipients)
    payload=current_scope['resolve_payload'](receipt['payload_ref'])
    if canonical_hash(payload)!=receipt['returned_digest']:raise ValueError('DEPENDENCY_UNVERIFIED')
    return True


def _binding_scope(binding):
    scope=dict(binding.current_scope_probe())
    if (scope.get('owner_id')!=binding.owner_id or scope.get('owner_session_id')!=binding.owner_session_id
            or scope.get('phase_id')!=binding.phase_id):raise PermissionError('BLOCKED_SCOPE')
    assignment=scope.get('assignments',{}).get(binding.actor_id)
    if not isinstance(assignment,dict):raise PermissionError('BLOCKED_SCOPE')
    binding.generation_ledger.current_state_probe=binding.current_scope_probe
    current=scope.get('ledger_state')
    if isinstance(current,dict):
        for key in ('dependencies','manifests','read_receipts','outputs'):
            binding.generation_ledger.state[key].update(deepcopy(current.get(key,{})))
    if callable(scope.get('resolve_payload')):binding.generation_ledger.resolve_payload=scope['resolve_payload']
    scope.update(generation_ledger=binding.generation_ledger,result_access=binding.result_access)
    return scope


def _binding_check(binding,identifiers=None,*,public=False):
    ledger=binding.generation_ledger;scope=_binding_scope(binding)
    if scope.get('paused') or scope.get('intervened'):raise PermissionError('Research action is paused or changed')
    identifiers=ledger.active_dependencies if identifiers is None else identifiers
    return check_dependencies(identifiers,runtime=ledger.runtime,workspace_id=ledger.workspace_id,
        current_scope=scope,recipients=[binding.actor_id],public=public)


def selected_knowledge_context(binding):
    """Selected documents are the retrieval scope, not whole-document input."""
    ledger=binding.generation_ledger;context=deepcopy(ledger.context);snippets=[]
    scope=_binding_scope(binding);current=scope['assignments'][binding.actor_id]
    collections=ledger.runtime.describe(binding.actor_id).get('collections',[])
    question=binding.frozen_task_ref.get('question_ref',{}).get('text') or current.get('question','')
    query=' '.join(str(value) for value in [question,current.get('question',''),
        context.get('research_team',{}).get('objective',''),*current.get('checks',[])])
    # Transparent lexical assistance only; scores are not physical applicability.
    for term,english in {'응력':'stress','변위':'displacement','메시':'mesh',
            '수렴':'convergence','하중':'load','구속':'boundary constraint',
            '접촉':'contact','반력':'reaction','특이점':'singularity',
            '관측':'observation','회복':'recovery'}.items():
        if term in query:query+=' '+english
    limit=min(60000,max(0,ledger.runtime.runtime.max_payload_bytes-20000-len(_bytes(context))-len(_bytes(question))))
    retrieval={'method':'Haystack BM25L','query':query,'top_k_per_source':4,
        'max_snippet_bytes':limit,'read_scope':'Only the exact returned chunks were supplied; whole selected documents were not read into the model.',
        'sources':[],'limitations':['Lexical relevance is not evidence of physical applicability.']}
    context['source_retrieval']=retrieval
    for reference in binding.permitted_source_refs:
        if 'document_id' not in reference:continue
        if not _matches(reference,current.get('source_refs',[])):raise PermissionError('BLOCKED_SCOPE')
        pin={key:reference[key] for key in ('document_id','revision')}
        result=ledger.runtime.knowledge.search(query,collections,top_k=100 if reference.get('locator') else 4,
            workspace_id=ledger.workspace_id,source_refs=[pin])
        hits=[hit for hit in result['hits'] if _matches(hit,[reference])][:4]
        selection={**deepcopy(pin),'status':'SELECTED_CHUNKS' if hits else 'NO_LEXICAL_MATCH',
            'read_locators':[],'not_supplied':[]}
        retrieval['sources'].append(selection)
        details=ledger.runtime.knowledge.revision_details(**pin,workspace_id=ledger.workspace_id,collections=collections)
        for hit in hits:
            exact={**pin,'locator':deepcopy(hit['locator'])}
            value=ledger.runtime.knowledge.source(**exact,workspace_id=ledger.workspace_id,collections=collections)
            segment=next((s for s in value['segments'] if s['locator']==hit['locator'] and s['text']==hit['text']),None)
            if segment is None:raise ValueError('The retrieved exact source chunk changed')
            from ..research_team_contract import projected_source_metadata
            item=deepcopy(segment);item['revision_metadata']=projected_source_metadata(details['metadata'],segment)
            item['extraction_limitations']=deepcopy(details['failed_segments'])
            item['retrieval']={'method':'Haystack BM25L','score':hit['score'],'scope':'Selected chunk, not the complete document'}
            if len(_bytes(snippets+[item]))>limit:
                selection['not_supplied'].append({'locator':deepcopy(item['locator']),'reason':'EXACT_CHUNK_EXCEEDS_REMAINING_PAYLOAD'})
                continue
            ledger.runtime._transmission_check(item,context)
            snippets.append(item);selection['read_locators'].append(deepcopy(item['locator']))
            dependency=ledger.add_supplied({'kind':'knowledge','exact_ref':exact,'payload':item['text']},dependencies=[],origin='auto_snippet')
            receipt=record_read(item,tool='knowledge.source',request=exact,source_reference=exact,
                actual_selector=exact['locator'],input_dependencies=[dependency['id']])
            receipt['status']='AVAILABLE';ledger.retain_read(receipt,item)
        if hits and not selection['read_locators']:selection['status']='NOT_SUPPLIED_PAYLOAD_LIMIT'
    return context,snippets


class ResultAccess:
    """Scope/permits only. All physical selector/reader validation belongs to C."""
    def __init__(self,*,readers,current_scope_probe,read_limits=None):
        self.readers=readers;self.current_scope_probe=current_scope_probe
        self.read_limits=read_limits or {'max_rows':1024,'max_values':16384,'max_bytes':20000}

    def _selection(self,request,selections):
        if not isinstance(request,dict) or set(request)-{'source_id','job_id','selection'}:
            raise ValueError('Select one approved result and its exact physical selection')
        if 'source_id' in request and 'job_id' in request:raise ValueError('Use one result identity form')
        found=[row for row in selections if row['source_id']==request.get('source_id')] if 'source_id' in request else [
            row for row in selections if row['reference']['job_id']==request.get('job_id')]
        if len(found)!=1:raise PermissionError('One exact result selection is required')
        return deepcopy(found[0])

    def check_reference(self,reference,selector,*,selections,context):
        from ..research_team_results import normalize_selection
        matching=[row for row in selections if row['reference']==reference]
        if not matching:raise PermissionError('Result is outside the recipient selection')
        self._transmit(reference,context)
        descriptor=self.readers['probe'](reference)
        for row in matching:
            try:
                normalize_selection(descriptor,selector,granted_selector=row['selector']);return
            except (ValueError,PermissionError):pass
        raise PermissionError('Result physical samples are outside the approved selection')

    def _transmit(self,reference,context):
        # The same operator/request transmission contract used by ordinary Expert.
        check=self.readers.get('transmission_check')
        if not callable(check):raise PermissionError('Current result transmission check is unavailable')
        check({'job_id':reference['job_id']},context)

    def prepare(self,request,binding):
        from ..research_team_results import normalize_selection
        scope=_binding_scope(binding)
        selected=self._selection(request,binding.result_selections)
        current=scope['assignments'][binding.actor_id].get('result_refs',[])
        if not any(row['source_id']==selected['source_id'] and row['reference']==selected['reference'] for row in current):
            raise PermissionError('Current exact result selection was withdrawn')
        self.check_reference(selected['reference'],selected['selector'],selections=current,context=scope['context'])
        descriptor=self.readers['probe'](selected['reference'])
        selector=normalize_selection(descriptor,request.get('selection',selected['selector']),granted_selector=selected['selector'])
        limits={key:min(self.read_limits[key],selected['read_limits'][key]) for key in self.read_limits}
        return {'reference':selected['reference'],'selector':selector,'descriptor':descriptor,'read_limits':limits,
                'source_id':selected['source_id'],'binding':binding,
                'input_dependencies':dependency_closure(binding.generation_ledger.state['dependencies'],binding.generation_ledger.active_dependencies)}

    def read(self,prepared):
        from ..research_team_results import read_selected_result
        binding=prepared['binding'];scope=_binding_scope(binding)
        self.check_reference(prepared['reference'],prepared['selector'],
            selections=scope['assignments'][binding.actor_id]['result_refs'],context=scope['context'])
        value=read_selected_result(prepared['reference'],prepared['selector'],readers=self.readers,read_limits=prepared['read_limits'])
        self.check_reference(prepared['reference'],prepared['selector'],
            selections=_binding_scope(binding)['assignments'][binding.actor_id]['result_refs'],context=_binding_scope(binding)['context'])
        return value

    def for_binding(self,binding):
        access=copy(self);access.analysis_binding=binding
        return access

    def prepare_analysis_source(self,source_id,selection,*,limits):
        binding=getattr(self,'analysis_binding',None)
        if binding is None:raise PermissionError('Analysis requires its current role binding')
        prepared=self.prepare({'source_id':source_id,**({'selection':selection} if selection is not None else {})},binding)
        prepared['read_limits']={key:min(value,limits.get(key,value)) for key,value in prepared['read_limits'].items()}
        return prepared

    def revalidate_analysis_source(self,source):
        binding=source['binding'];scope=_binding_scope(binding)
        self.check_reference(source['reference'],source['selector'],
            selections=scope['assignments'][binding.actor_id]['result_refs'],context=scope['context'])


class RoleBindingMethods:
    """Methods delegated by A's single ApprovedRoleBinding; no duplicate record."""
    def tool_parameters(self,name,legacy_schema):
        ledger=self.generation_ledger;scope=_binding_scope(self)
        current=scope['assignments'][self.actor_id]
        allowed=set(self.assignment['tools']) & set(current['tools']) & set(ledger.runtime.describe(self.actor_id).get('tools',[]))
        if name not in allowed:return None
        if name=='experts.consult' and (self.initial_visibility=='independent' or not self.budget_slice.consultations):return None
        if name.startswith('literature.') and self.public_access is None:return None
        if name=='numerical.analyze':
            calculation=scope['context'].get('calculation_scope',{})
            if not self.analysis_access or calculation.get('allow_execution') is not True or not calculation.get('analysis'):return None
            return self.analysis_access.tool_parameters(self)
        if name=='literature.search':
            schema=deepcopy(legacy_schema)
            schema.setdefault('properties',{})['top_k']={'type':'integer','minimum':1,'maximum':4}
            return schema
        if name=='calculations.status' and (not self.result_access or not self.result_selections):return None
        if name=='results.read':
            if not self.result_access or not self.result_selections:return None
            return {'type':'object','properties':{'source_id':{'type':'string','enum':[r['source_id'] for r in self.result_selections]},
                'job_id':{'type':'string','enum':list({r['reference']['job_id'] for r in self.result_selections})},
                'selection':{'type':'object'}},'oneOf':[{'required':['source_id']},{'required':['job_id']}],'additionalProperties':False}
        return deepcopy(legacy_schema)

    def prepare_history(self,session_turns):
        ledger=self.generation_ledger;scope=_binding_scope(self);messages=[]
        for turn in session_turns:
            if turn.get('actor_id')!=self.actor_id or turn.get('phase_id')!=self.phase_id:continue
            if self.initial_visibility=='independent' and turn.get('task_id')!=self.task_id:continue
            response=turn.get('response',{})
            projection=shared_projection(response,[self.actor_id],runtime=ledger.runtime,
                workspace_id=ledger.workspace_id,current_scope=scope)
            if projection['status']!='AVAILABLE':continue
            payload={'question':turn.get('question'),'response':projection['projection']}
            ref=ledger.add_supplied({'kind':'response','exact_ref':{'response_id':response.get('id')},'payload':payload},
                dependencies=projection['dependency_ids'],origin='history')
            messages.append({'question':turn.get('question'),'answer':projection['projection'].get('answer',''),
                'dependency_ids':[ref['id']]})
        return messages

    def prepare_consult(self,target_id,question,*,visited):
        if self.initial_visibility=='independent' or target_id in visited:raise PermissionError('Consultation is outside this task')
        scope=_binding_scope(self);factory=scope.get('make_consult_binding')
        if target_id not in self.generation_ledger.context.get('consult_experts',[]) or not callable(factory):
            raise PermissionError('No separately allocated target consultation is available')
        closure=_binding_check(self)
        check_dependencies(closure,runtime=self.generation_ledger.runtime,workspace_id=self.generation_ledger.workspace_id,
            current_scope=scope,recipients=[target_id])
        target=factory(target_id,question,caller=self,dependency_ids=closure)
        if target.role_session_id==self.role_session_id:raise PermissionError('Consultation needs a separate role session')
        return target

    def prepare_model_input(self,payload,*,mode,supplied_items):
        ledger=self.generation_ledger
        if mode=='public_clean':
            if self.initial_visibility!='independent' or ledger.context.get('history') or ledger.context.get('discussion'):
                raise PermissionError('Public clean research requires a new independent task/session')
            if any(row['introduced_by'] in {'history','forwarded_turn','consultation','map_base'} for row in ledger.state['dependencies'].values()
                   if row['id'] in ledger.active_dependencies):raise PermissionError('Public clean input has a restricted ancestry')
        for item in supplied_items:
            ledger.add_supplied(item,dependencies=item.get('dependency_ids',[]),origin=item.get('origin','prompt'))
        # Selected result descriptors are also actual prompt input, even when no
        # numeric result tool has been called. Verify metadata without hydrating it.
        for selected in self.result_selections:
            if self.result_access is None:raise PermissionError('Exact result verification is unavailable')
            selector={**deepcopy(selected['selector']),'metadata_only':True}
            prepared=self.result_access.prepare({'source_id':selected['source_id'],'selection':selector},self)
            ledger.add_supplied({'kind':'result','exact_ref':prepared['reference'],
                'selector':prepared['selector'],'payload':selected},dependencies=[],origin='prompt')
        _binding_check(self,public=mode=='public_clean')
        return ledger.begin_model(payload,mode=mode)

    def prepare_tool(self,name,request,*,debit):
        if debit is not True:raise PermissionError('A trusted consumed tool debit is required')
        if RoleBindingMethods.tool_parameters(self,name,{}) is None:raise PermissionError('Tool is outside the current role grant')
        dependencies=_binding_check(self);ledger=self.generation_ledger
        permit={'id':_identifier('permit'),'tool':name,'canonical_request':deepcopy(request),'dispatch':'EXISTING',
            'invoke':None,'current_binding_id':canonical_hash({**ledger.binding_ids,'role_session_id':self.role_session_id}),
            'debit':True,'dependency_ids':dependencies}
        if name.startswith('literature.'):
            if self.public_access is None:raise PermissionError('No action-wide literature access')
            invoke=self.public_access.search if name=='literature.search' else self.public_access.read
            permit.update(dispatch='GUARDED',invoke=lambda:invoke(deepcopy(request),caller=self,
                input_dependencies=dependencies,_debit=True))
        elif name=='results.read':
            prepared=self.result_access.prepare(request,self)
            permit.update(dispatch='GUARDED',invoke=lambda:self.result_access.read(prepared))
        elif name=='calculations.status':
            prepared=self.result_access.prepare({'job_id':request['job_id'],
                'selection':{'metadata_only':True,'channels':[]}},self)
            if not hasattr(ledger,'_permit_sources'):ledger._permit_sources={}
            ledger._permit_sources[permit['id']]={key:deepcopy(prepared[key]) for key in ('reference','selector')}
        elif name=='numerical.analyze':
            prepared=self.analysis_access.prepare(request,scope=_binding_scope(self)['context'].get('calculation_scope',{}),
                result_access=self.result_access.for_binding(self),binding=self)
            permit.update(dispatch='GUARDED',invoke=lambda:self.analysis_access.execute(prepared))
        elif name.startswith('knowledge.'):
            refs=[r for r in self.permitted_source_refs if 'document_id' in r]
            current_refs=_binding_scope(self)['assignments'][self.actor_id].get('source_refs',[])
            if any(not _matches(r,current_refs) for r in refs):raise PermissionError('Current source selection was withdrawn')
            if name=='knowledge.source' and not _matches(request,refs):raise PermissionError('Exact source locator is outside the selection')
            if name=='knowledge.search':
                requested=request.get('collections',ledger.runtime.describe(self.actor_id).get('collections',[]))
                if not set(requested)<=set(ledger.runtime.describe(self.actor_id).get('collections',[])):raise PermissionError('Collections cannot expand')
                def search():
                    if not refs:return {'status':'OK','hits':[],'method':'Haystack BM25L'}
                    result=ledger.runtime.knowledge.search(request['query'],requested,request.get('filters'),request.get('top_k',5),
                        workspace_id=ledger.workspace_id,source_refs=[{k:r[k] for k in ('document_id','revision')} for r in refs])
                    result['hits']=[hit for hit in result['hits'] if _matches(hit,refs)]
                    return result
                permit.update(dispatch='GUARDED',invoke=search)
        if not hasattr(ledger,'_permits'):ledger._permits={}
        ledger._permits[permit['id']]=permit
        return permit

    def finish_tool(self,permit,returned_or_error):
        _binding_scope(self)  # Nested consultation may have checkpointed new parent records.
        ledger=self.generation_ledger
        if getattr(ledger,'_permits',{}).pop(permit.get('id'),None) is not permit:
            raise PermissionError('Tool permit was not issued by this current binding')
        parents=dependency_closure(ledger.state['dependencies'],permit['dependency_ids'])
        name=permit['tool'];request=permit['canonical_request'];read_receipts=[]
        if isinstance(returned_or_error,BaseException):
            payload={'status':'TOOL_FAILED','tool':name,'error_type':type(returned_or_error).__name__}
        elif isinstance(returned_or_error,dict) and {'payload','read_receipts','dependency_ids','status','limitations'}<=returned_or_error.keys():
            payload=deepcopy(returned_or_error['payload']);parents=dependency_closure(ledger.state['dependencies'],parents+returned_or_error['dependency_ids'])
            read_receipts=deepcopy(returned_or_error['read_receipts'])
        else:payload=deepcopy(returned_or_error)
        # Every actually returned snippet/source, including uncited auto retrieval, is tracked.
        if name.startswith('knowledge.') and isinstance(payload,dict):
            for segment in payload.get('hits',payload.get('segments',[])):
                ref={k:deepcopy(segment[k]) for k in ('document_id','revision','locator')}
                item=ledger.add_supplied({'kind':'knowledge','exact_ref':ref,'payload':segment['text']},dependencies=[],origin='tool_return')
                parents.append(item['id'])
        if name=='results.read' and isinstance(payload,dict) and 'receipt' in payload:
            receipt=payload['receipt']
            item=ledger.add_supplied({'kind':'result','exact_ref':receipt['reference'],
                'selector':receipt['returned_selector'],'payload':payload['payload']},dependencies=parents,origin='tool_return')
            parents.append(item['id'])
            native_ref=ledger.retain_payload(receipt,prefix='result-verification')
            read=record_read(payload['payload'],tool=name,request=request,source_reference=receipt['reference'],
                actual_selector=receipt['returned_selector'],input_dependencies=parents)
            read['status']='VERIFIED';read['limitations'].append({'verification_receipt_ref':native_ref})
            read_receipts.append(read);payload=payload['payload']
        source=getattr(ledger,'_permit_sources',{}).pop(permit['id'],None)
        if source:
            item=ledger.add_supplied({'kind':'result','exact_ref':source['reference'],
                'selector':source['selector'],'payload':payload},dependencies=parents,origin='tool_return')
            parents.append(item['id'])
            read=record_read(payload,tool='results.read',request=request,source_reference=source['reference'],
                actual_selector=source['selector'],input_dependencies=parents)
            read['read_level']='RESULT_METADATA'
            read['status']='AVAILABLE' if not isinstance(returned_or_error,BaseException) else 'TOOL_FAILED'
            read_receipts.append(read)
        if name=='numerical.analyze' and isinstance(payload,dict) and 'input_dependencies' in payload:
            for source in payload.get('source_receipts',[]):
                if source.get('verification')!='VERIFIED':raise ValueError('Analysis source was not verified by the retained reader')
                source_item=ledger.add_supplied({'kind':'result','exact_ref':source['reference'],
                    'selector':source['returned_selector'],'payload':source},dependencies=parents,origin='tool_return')
                parents.append(source_item['id'])
            parents=dependency_closure(ledger.state['dependencies'],parents+payload['input_dependencies'])
            item=ledger.add_supplied({'kind':'analysis','exact_ref':{'analysis_receipt_id':payload['id'],
                'prepared_id':payload['prepared_id']},'payload':payload},dependencies=parents,origin='tool_return')
            parents.append(item['id'])
        if name=='experts.consult' and isinstance(payload,dict) and not isinstance(returned_or_error,BaseException):
            response=payload.get('research_response')
            if not isinstance(response,dict):raise ValueError('Consultation has no complete supplied-input provenance')
            parents=dependency_closure(ledger.state['dependencies'],parents+response['dependency_ids'])
            item=ledger.add_supplied({'kind':'response','exact_ref':{'response_id':response['id']},'payload':payload},
                dependencies=parents,origin='consultation')
            parents.append(item['id'])
        item=ledger.add_supplied({'kind':'tool_output','exact_ref':{'tool':name,'request_digest':canonical_hash(request)},'payload':payload},
            dependencies=parents,origin='consultation' if name=='experts.consult' else 'tool_return')
        identifiers=dependency_closure(ledger.state['dependencies'],parents+[item['id']])
        _binding_check(self,identifiers)
        if not read_receipts:
            read_receipts=[record_read(payload,tool=name,request=request,source_reference=request,
                actual_selector=request.get('selection',request.get('locator')),input_dependencies=identifiers)]
        if name=='knowledge.source' and isinstance(payload,dict):
            # A whole-document read also supplies its returned chunks for exact citations.
            for segment in payload.get('segments',[]):
                reference={key:deepcopy(segment[key]) for key in ('document_id','revision','locator')}
                if reference==request:continue
                receipt=record_read(segment,tool=name,request=request,source_reference=reference,
                    actual_selector=reference['locator'],input_dependencies=identifiers)
                read_receipts.append(ledger.retain_read(receipt,segment))
        state=deepcopy(ledger.state)
        retained=[]
        for receipt in read_receipts:
            receipt['dependency_ids']=identifiers
            if receipt.get('payload_ref') is None:receipt=ledger.retain_read(receipt,payload)
            elif receipt['id'] not in ledger.read_receipt_ids:ledger.read_receipt_ids.append(receipt['id'])
            retained.append(receipt)
        read_receipts=retained
        state=deepcopy(ledger.state)
        for receipt in read_receipts:state['read_receipts'][receipt['id']]=receipt
        ledger._commit(state,'tool-result-'+permit['id'])
        return {'payload':payload,'read_receipts':read_receipts,'dependency_ids':identifiers,
            'status':payload.get('status','RETURNED') if isinstance(payload,dict) else 'RETURNED','limitations':[]}

    def finalize_response(self,raw_response,validation):
        ledger=self.generation_ledger;identifier=_identifier('response')
        receipt=self.checkpoint('raw-'+identifier,{'asset':{'id':identifier,'payload':deepcopy(raw_response)}})
        reference=receipt.get('asset_ref') if isinstance(receipt,dict) else None
        if not reference:raise ValueError('Raw response was not durably retained by the owner')
        identifiers=dependency_closure(ledger.state['dependencies'],ledger.active_dependencies)
        manifests=[ledger.state['manifests'][key] for key in ledger.manifest_ids]
        coverage='COMPLETE_SUPPLIED_INPUT' if manifests and all(row['coverage']=='COMPLETE_SUPPLIED_INPUT' for row in manifests) else 'UNVERIFIED'
        for key in ledger.manifest_ids:ledger.finish_model(key,output_ref=reference)
        row={'id':identifier,'task_id':self.task_id,'actor_id':self.actor_id,'phase_id':self.phase_id,
            'raw_response_ref':reference,'validation':deepcopy(validation),'input_manifest_ids':list(ledger.manifest_ids),
            'dependency_ids':identifiers,'read_receipt_ids':list(ledger.read_receipt_ids),
            'proposal_refs':[],'local_status':'COMPLETED_LOCAL' if coverage=='COMPLETE_SUPPLIED_INPUT' else 'DEPENDENCY_UNVERIFIED',
            'shared_projection_id':None}
        self.checkpoint('response-'+identifier,{'response':deepcopy(row)})
        return row

    def validation_failed(self,raw_response,errors):
        value={'status':'INVALID','errors':deepcopy(errors),'repair_status':'WAITING_REPAIR','engineering_qualification':'UNKNOWN'}
        RoleBindingMethods.finalize_response(self,raw_response,value)
        return value


def __getattr__(name):
    if name=='ActionLiteratureAccess':
        from .research_team_literature import ActionLiteratureAccess
        return ActionLiteratureAccess
    raise AttributeError(name)
