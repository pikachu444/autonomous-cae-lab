"""One logical action's existing Literature operations and success journal.

This is a scoped facade over Literature, not a provider, cache or source owner.
Failed/cancelled search attempts consume the same two slots across retries.
"""
from copy import copy,deepcopy
import threading
import time

from ..execution_control import check_cancelled,ExecutionCancelled
from ..storage import canonical_hash
from .literature import archive_digest
from .research_evidence import (_binding_check,_binding_scope,_bytes,dependency_closure,
    record_read,check_dependencies)


class ActionLiteratureAccess:
    def __init__(self,runtime,*,action_id,workspace_id,context,budget,checkpoint,state=None,current_scope_probe=None):
        self.runtime=runtime;self.action_id=action_id;self.workspace_id=workspace_id
        self.context=deepcopy(context);self.budget=budget;self.checkpoint=checkpoint
        self.current_scope_probe=current_scope_probe;self.lock=threading.RLock()
        self.state=deepcopy(state) if state else {'id':'search-'+action_id,'logical_action_id':action_id,
            'attempt_count':0,'entries':[],'read_entries':[]}
        if self.state['logical_action_id']!=action_id or not 0<=self.state['attempt_count']<=2:
            raise ValueError('The retained search journal belongs to another logical action')

    def _persist(self,event):
        self.checkpoint(event,{'public_search_ledger':deepcopy(self.state)})

    def _authorize(self,caller,input_dependencies):
        if caller is None or caller.action_id!=self.action_id or caller.public_access is not self:
            raise PermissionError('Use the same owner-issued action literature access')
        scope=_binding_scope(caller)
        context=scope['context'];policy=self.runtime.runtime.transmission or {}
        if not policy.get('allow_public_search') or not context.get('transmission_scope',{}).get('allow_public_search'):
            raise PermissionError('Public literature access was not approved or was withdrawn')
        # The existing public-search rule requires all selected participants' grants.
        for actor,assignment in scope['assignments'].items():
            tools=set(self.runtime.describe(actor).get('tools',[])) & set(assignment.get('tools',[]))
            if not {'literature.search','literature.read'}<=tools:
                raise PermissionError('All participating roles must permit public literature tools')
        closure=_binding_check(caller,list(set(input_dependencies+caller.generation_ledger.active_dependencies)),public=True)
        check_cancelled()
        if time.monotonic()>=caller.budget_slice.deadline:raise RuntimeError('Research time budget exhausted')
        return closure

    def _debit(self,caller,debit):
        if debit is not True:caller.budget_slice.consume('tool')

    def _bound(self,value,caller,parents,request,tool,source_ref=None):
        ledger=caller.generation_ledger
        value=deepcopy(value);discovery_receipts=[]
        value.pop('detail',None)
        if tool=='literature.search' and value.get('status')=='OK':
            # Search supplies bibliography, not a claim of abstract/full-text read.
            for paper in value.get('papers',[]):
                paper.pop('abstract',None);paper.pop('fulltext_candidates',None)
                discovery=self.runtime.literature._archive({'status':'metadata_only','paper_id':paper['paper_id'],
                    'paper':deepcopy(paper),'segments':[],'fulltext_access':'not_read','table_figure_status':'unverified'})
                reference={'paper_id':paper['paper_id'],'locator':{'archive_id':archive_digest(discovery)}}
                item=ledger.add_supplied({'kind':'literature','exact_ref':reference,'payload':paper},
                    dependencies=parents,origin='tool_return')
                parents=parents+[item['id']]
                receipt=record_read(discovery,tool=tool,request=request,source_reference=reference,
                    actual_selector=reference['locator'],input_dependencies=parents)
                receipt['status']='SUCCEEDED'
                discovery_receipts.append(ledger.retain_read(receipt,discovery))
        for failure in value.get('access_failures',[]):
            if failure.get('error'):failure.pop('reason',None)
        if source_ref is not None:
            ref=ledger.add_supplied({'kind':'literature','exact_ref':source_ref,'payload':value},
                dependencies=parents,origin='tool_return')
            parents=parents+[ref['id']]
        output=ledger.add_supplied({'kind':'tool_output','exact_ref':{'tool':tool,'request_digest':canonical_hash(request)},
            'payload':value},dependencies=parents,origin='tool_return')
        parents=dependency_closure(ledger.state['dependencies'],parents+[output['id']])
        receipt=record_read(value,tool=tool,request=request,source_reference=source_ref or request,
            actual_selector=source_ref.get('locator') if source_ref else None,input_dependencies=parents)
        if receipt['status'] in {'OK','abstract_only','metadata_only','fulltext'}:receipt['status']='SUCCEEDED'
        _binding_check(caller,parents)
        if len(_bytes(value))>min(20000,self.runtime.runtime.max_payload_bytes):
            raise ValueError('Public read exceeds the existing model payload bound; select a narrower locator')
        receipt=ledger.retain_read(receipt,value)
        return {'payload':deepcopy(value),'read_receipts':discovery_receipts+[receipt],'dependency_ids':parents,
            'status':value.get('status','RETURNED'),'limitations':deepcopy(value.get('access_failures',[]))}

    def search(self,request,*,caller,input_dependencies,_debit=None):
        if not isinstance(request,dict) or set(request)-{'query','providers','filters','top_k'}:
            raise ValueError('Use the existing public query, provider, filters and top_k fields')
        query=request.get('query');top=request.get('top_k',4);providers=request.get('providers',['crossref'])
        filters=deepcopy(request.get('filters') or {})
        if not isinstance(query,str) or not query.strip() or len(query)>1000 or type(top) is not int or not 1<=top<=4:
            raise ValueError('Public search accepts one exact query and at most four papers')
        if providers!=['crossref'] or set(filters)-{'from_year','until_year','type'}:
            raise ValueError('Use the existing Crossref provider and supported filters')
        if any(type(filters[key]) is not int for key in ('from_year','until_year') if key in filters):
            raise ValueError('Publication year filters require exact integers')
        if 'type' in filters and (not isinstance(filters['type'],str) or not filters['type'].strip()):
            raise ValueError('Publication type requires the existing explicit text filter')
        canonical={'query':query,'providers':providers,'filters':filters,'top_k':top}
        key=canonical_hash({'logical_action_id':self.action_id,'tool':'literature.search','arguments':canonical,'contract':2})
        with self.lock:
            self._debit(caller,_debit)
            parents=self._authorize(caller,input_dependencies)
            matches=[entry for entry in self.state['entries'] if entry['key']==key]
            successful=next((entry for entry in matches if entry['status']=='SUCCEEDED'),None)
            if successful is not None:
                value=deepcopy(successful['result'])
                if canonical_hash(value)!=successful['result_digest']:raise ValueError('Retained successful search changed')
                return self._bound(value,caller,parents,canonical,'literature.search')
            if matches and matches[-1]['status'] in {'STARTED','OUTCOME_UNCONFIRMED'}:
                raise RuntimeError('The earlier search outcome is unconfirmed; no automatic repeated request')
            if self.state['attempt_count']>=2:raise PermissionError('This logical action has used both external search attempts')
            self.state['attempt_count']+=1
            entry={'id':'search-entry-'+str(self.state['attempt_count']),'key':key,'tool':'literature.search',
                'arguments':canonical,'status':'STARTED','dependency_ids':parents,'result':None,'result_digest':None}
            self.state['entries'].append(entry)
            self._persist('search-start-'+entry['id'])  # A failed checkpoint prevents network dispatch.
            try:
                value=self.runtime.literature.search(**canonical)
            except BaseException as error:
                entry.update(status='CANCELLED' if isinstance(error,ExecutionCancelled) else 'FAILED',error_type=type(error).__name__)
                self._persist('search-stop-'+entry['id']);raise
            if value.get('status')!='OK' and value.get('detail'):
                entry['raw_error_ref']=caller.generation_ledger.retain_payload(value,prefix='search-error')
                value=deepcopy(value);value.pop('detail',None)
            entry.update(status='SUCCEEDED' if value.get('status')=='OK' else 'FAILED',
                result=deepcopy(value),result_digest=canonical_hash(value))
            try:self._persist('search-finish-'+entry['id'])
            except BaseException:
                entry['status']='OUTCOME_UNCONFIRMED'
                raise
            # Save successful work before observing a later cancellation/revoke.
            check_cancelled();self._authorize(caller,parents)
            return self._bound(value,caller,parents,canonical,'literature.search')

    def _paper(self,paper_id,caller):
        for entry in self.state['entries']:
            if entry['status']=='SUCCEEDED':
                for paper in entry['result'].get('papers',[]):
                    if paper['paper_id']==paper_id:return deepcopy(paper),entry['id']
        for ref in caller.permitted_source_refs:
            if ref.get('paper_id')==paper_id and ref.get('locator',{}).get('archive_id'):
                value=self.runtime.literature.read(paper_id,{'archive_id':ref['locator']['archive_id']})
                return deepcopy(value['paper']),deepcopy(ref)
        raise PermissionError('Select an exact archive or a paper from this action\'s successful search')

    def read(self,request,*,caller,input_dependencies,_debit=None):
        if not isinstance(request,dict) or set(request)-{'paper_id','locator'} or not isinstance(request.get('paper_id'),str):
            raise ValueError('Read one selected paper and exact locator')
        with self.lock:
            self._debit(caller,_debit)
            parents=self._authorize(caller,input_dependencies)
            paper,origin=self._paper(request['paper_id'],caller)
            locator=deepcopy(request.get('locator') or {})
            if isinstance(origin,dict):
                selected=origin['locator']
                if any(locator.get(k,v)!=v for k,v in selected.items()):raise PermissionError('Exact archive locator cannot expand')
                locator={**locator,**selected}
            key=canonical_hash({'action':self.action_id,'paper':paper,'origin':origin,'locator':locator})
            prior=next((row for row in self.state['read_entries'] if row['key']==key and row['status']=='SUCCEEDED'),None)
            if prior is None and not locator.get('archive_id'):
                retained={row['raw_ref']['locator']['archive_id']:row['raw_ref'] for row in self.state['read_entries']
                    if row['paper_id']==paper['paper_id'] and row.get('status')=='SUCCEEDED' and row.get('raw_ref')}
                if len(retained)>1:raise ValueError('Select one exact retained archive for this paper')
                if retained:
                    reference=next(iter(retained.values()))
                    value=self.runtime.literature.read(paper['paper_id'],{**reference['locator'],**locator})
                    return self._bound(value,caller,parents,request,'literature.read',
                        {'paper_id':paper['paper_id'],'locator':{**reference['locator'],**locator}})
            if prior:
                ref=deepcopy(prior['raw_ref'])
                if locator.get('archive_id') and locator['archive_id']!=ref['locator']['archive_id']:
                    raise ValueError('Selected archive differs from the retained successful read')
                value=self.runtime.literature.read(ref['paper_id'],ref['locator'])
                if canonical_hash(value)!=prior['returned_digest']:raise ValueError('Retained read bytes or locator changed')
                return self._bound(value,caller,parents,request,'literature.read',ref)
            unresolved=[row for row in self.state['read_entries'] if row['key']==key and row['status'] in {'STARTED','OUTCOME_UNCONFIRMED'}]
            if unresolved:raise RuntimeError('The earlier read outcome is unconfirmed; select its retained archive explicitly')
            if locator.get('archive_id'):
                allowed=[row.get('raw_ref') for row in self.state['read_entries'] if row.get('raw_ref')]
                allowed += [ref for ref in caller.permitted_source_refs if ref.get('paper_id')]
                allowed += [caller.generation_ledger.state['read_receipts'][identifier]['source_ref']
                    for identifier in caller.generation_ledger.read_receipt_ids
                    if caller.generation_ledger.state['read_receipts'][identifier]['source_ref'].get('paper_id')]
                if not any(ref['paper_id']==paper['paper_id'] and ref.get('locator',{}).get('archive_id')==locator['archive_id'] for ref in allowed):
                    raise PermissionError('An unselected archive is not authorized by a matching paper title')
            entry={'key':key,'search_entry_id':origin if isinstance(origin,str) else None,
                'selected_archive_ref':origin if isinstance(origin,dict) else None,'paper_id':paper['paper_id'],
                'archive_id':None,'locator':locator,'read_level':None,'status':'STARTED','raw_ref':None,'dependency_ids':parents}
            self.state['read_entries'].append(entry)
            event_key=key+'-'+str(len(self.state['read_entries']))
            self._persist('read-start-'+event_key)
            try:
                # Pin successful search metadata, never mutable latest paper state.
                reader=copy(self.runtime.literature);reader._papers={paper['paper_id']:deepcopy(paper)}
                value=reader.read(paper['paper_id'],locator)
                archive=locator.get('archive_id') or archive_digest(value)
                exact_locator={'archive_id':archive,**{k:v for k,v in locator.items() if k!='archive_id'}}
                # Full-text redirects are recorded by the existing archive. Reopening
                # uses its exact returned locator, not a fresh URL resolution.
                if not value.get('segments') or not locator:
                    exact_locator={'archive_id':archive}
                ref={'paper_id':paper['paper_id'],'locator':exact_locator}
                if value.get('status') in {'abstract_only','metadata_only','fulltext'}:
                    entry.update(status='SUCCEEDED',archive_id=archive,raw_ref=ref,
                        read_level=value['status'],returned_digest=canonical_hash(value))
                else:entry.update(status='FAILED',read_level=value.get('status'))
            except BaseException as error:
                entry.update(status='CANCELLED' if isinstance(error,ExecutionCancelled) else 'FAILED',error_type=type(error).__name__)
                self._persist('read-stop-'+event_key);raise
            try:self._persist('read-finish-'+event_key)
            except BaseException:
                entry['status']='OUTCOME_UNCONFIRMED'
                raise
            check_cancelled();self._authorize(caller,parents)
            return self._bound(value,caller,parents,request,'literature.read',ref if entry['status']=='SUCCEEDED' else None)

    def retrieve(self,queries,*,caller,input_dependencies,exclude_urls=(),result_sources=()):
        """SelectedRetriever and direct role tools share this exact instance/journal."""
        from .costorm import _paper_rows
        queries=[queries] if isinstance(queries,str) else list(queries)
        if any(not isinstance(query,str) or not query.strip() or len(query)>1000 for query in queries):
            raise ValueError('Use nonempty source queries of at most 1000 characters')
        rows=[];seen=set();events=[]
        for query in queries:
            # Local retrieval never treats an empty selected list as store-wide.
            if any('document_id' in ref for ref in caller.permitted_source_refs):
                caller.budget_slice.consume('tool')
                permit=caller.prepare_tool('knowledge.search',{'query':query,'top_k':4},debit=True)
                result=caller.finish_tool(permit,permit['invoke']())
                for hit in result['payload']['hits']:
                    ref={key:deepcopy(hit[key]) for key in ('document_id','revision','locator')}
                    url='caelab-source:'+canonical_hash(ref)
                    if url not in seen and url not in exclude_urls:
                        seen.add(url);rows.append({'url':url,'title':hit['title'],'description':'실제 선택 원문 검색',
                            'snippets':[hit['text']],'meta':{'source':hit,'dependency_ids':result['dependency_ids']}})
            scope=_binding_scope(caller)
            if not (self.runtime.runtime.transmission or {}).get('allow_public_search') or not scope['context'].get('transmission_scope',{}).get('allow_public_search'):
                continue
            try:
                found=self.search({'query':query,'top_k':4},caller=caller,input_dependencies=input_dependencies)
                events.append({'tool':'literature.search','status':found['status']})
            except (PermissionError,RuntimeError) as error:
                if not rows:raise
                events.append({'tool':'literature.search','status':'NOT_PERMITTED' if isinstance(error,PermissionError) else 'FAILED'});continue
            if found['status']!='OK':continue
            for paper in found['payload'].get('papers',[]):
                try:
                    read=self.read({'paper_id':paper['paper_id'],'locator':{'kind':'abstract'}},caller=caller,input_dependencies=input_dependencies)
                    for row in _paper_rows(read['payload']):
                        if row['url'] not in seen and row['url'] not in exclude_urls:
                            seen.add(row['url']);row['meta']['dependency_ids']=read['dependency_ids'];rows.append(row)
                except (ExecutionCancelled,KeyboardInterrupt):raise
                except (ValueError,RuntimeError,OSError) as error:
                    events.append({'tool':'literature.read','status':'FAILED','error_type':type(error).__name__})
        for source in result_sources:
            identifiers=source.get('dependency_ids')
            if not identifiers:raise ValueError('Exact selected result source has no supplied-input provenance')
            _binding_check(caller,identifiers)
            url='caelab-result:'+canonical_hash(source['reference'])
            if url not in seen and url not in exclude_urls:
                rows.append({'url':url,'title':'선택한 계산 결과','description':'검증된 실제 선택',
                    'snippets':[_bytes(source['payload']).decode()],
                    'meta':{'source':source['reference'],'dependency_ids':identifiers}})
        partial=any(event['status'] in {'FAILED','UNAVAILABLE','NOT_PERMITTED'} for event in events)
        ledger=caller.generation_ledger
        outcome={'status':'PARTIAL' if partial else 'SUCCEEDED','events':events,'returned_sources':len(rows)}
        ledger.add_supplied({'kind':'tool_output','exact_ref':{'tool':'selected.retrieve'},'payload':outcome},
            dependencies=list(ledger.active_dependencies),origin='tool_return')
        identifiers=_binding_check(caller)
        for row in rows:
            row['meta'].update(retrieval_status=outcome['status'],retrieval_events=deepcopy(events),dependency_ids=identifiers)
        if rows and partial:
            rows[0]['snippets'].insert(0,'검색 일부 미완료: 아래 내용은 성공한 자료에서 실제로 읽은 범위입니다.')
        return rows
