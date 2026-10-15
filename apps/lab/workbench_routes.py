"""HTTP routes only; numerical and assistance behavior lives in shared services."""
import re
import json
from urllib.parse import unquote
from .service import ServiceError


def handle(handler,method,path,query):
    workbench=handler.server.workbench
    if method=='POST':
        if query:
            raise ServiceError(400,'POST does not accept query arguments')
        if path=='/api/workbench/upload':
            payload=handler._bytes_body('application/octet-stream',16*1024*1024,1)
            name=handler.headers.get('X-File-Name','')
            if handler.headers.get('X-File-Name-Encoding')=='percent-utf8':
                name=unquote(name,encoding='utf-8',errors='strict')
            return handler._json(201,workbench.upload(name,payload))
        if re.fullmatch(r'/api/workbench/hosts/[^/]+/events', path):
            from .server import MAX_NATIVE_EVENT_BODY
            body = handler._json_body(maximum=MAX_NATIVE_EVENT_BODY)
        elif path == '/api/workbench/portable-project/create':
            body = handler._json_body(maximum=8*1024*1024)
        elif path == '/api/workbench/documents/open' or re.fullmatch(r'/api/workbench/documents/[^/]+/commands',path):
            # Existing document drafts are bounded at 8 MiB. Only their owner
            # transport accepts that draft plus a bounded command envelope.
            body = handler._json_body(maximum=8*1024*1024+64*1024)
        else:
            body = handler._json_body()
        if path == '/api/workbench/connection-graph':
            if set(body) - {'document_ids', 'include_history'} or type(body.get('include_history', False)) is not bool:
                raise ServiceError(400, '실제 문서 목록과 편집 이력 포함 여부만 지정하세요.')
            return handler._json(200, workbench.connection_graph(**body))
        connection_routes = {
            '/api/workbench/connection/impact': ('connection_impact', {'target_id', 'port'}),
            '/api/workbench/connection/catalog': ('connection_catalog', {'target_id'}),
            '/api/workbench/connection/preview': ('connection_preview', {'target', 'port', 'action', 'source'}),
            '/api/workbench/connection/apply': ('connection_apply', {'proposal', 'confirmed', 'command_id'}),
            '/api/workbench/connection/view-read': ('connection_view_read', set()),
            '/api/workbench/connection/view-save': ('connection_view_save',
                {'state', 'scope', 'expected_revision', 'expected_sha256', 'command_id'}),
        }
        if path in connection_routes:
            name, fields = connection_routes[path]
            if set(body) != fields:
                raise ServiceError(400, '정확한 관계/배치 명령 필드가 다릅니다.')
            return handler._json(200, getattr(workbench, name)(**body))
        if path == '/api/workbench/portable-project/inspect':
            if 'selections' not in body or set(body) - {'selections', 'draft_policy'}:
                raise ServiceError(400, '문서 선택과 초안 포함 방식을 지정하세요.')
            return handler._json(200, workbench.portable_inspect(**body))
        portable_routes = {
            '/api/workbench/portable-project/create': ('portable_create',
                {'inspection', 'destination', 'approved', 'command_id', 'session_id'}),
            '/api/workbench/portable-project/verify': ('portable_verify', {'folder'}),
            '/api/workbench/portable-project/repair': ('portable_repair', {'folder', 'relative', 'replacement', 'approved'}),
        }
        if path in portable_routes:
            name, fields = portable_routes[path]
            if set(body) != fields:
                raise ServiceError(400, '작업 사본의 명시적 선택/확인 필드가 다릅니다.')
            return handler._json(200, getattr(workbench, name)(**body))
        if path == '/api/workbench/expert-connection/reload':
            if set(body) != {'expected_sha256'}:
                raise ServiceError(400, 'Reload accepts only the saved local operator-file hash')
            from caelab.expert_connection import reload_local
            return handler._json(200, reload_local(workbench, body['expected_sha256']))
        if path=='/api/workbench/backend-readiness':
            if set(body)!={'backend'}:
                raise ServiceError(400,'Dependency discovery accepts a registered backend only; no execution/configuration arguments')
            return handler._json(200,workbench.backend_readiness(body['backend']))
        if path=='/api/workbench/constitutive-inspect':
            if set(body)-{'document_id','job_id','increment'} or not {'document_id','job_id'} <= set(body):
                raise ServiceError(400,'재료 계산과 증분을 선택하세요.')
            return handler._json(200,workbench.constitutive_inspect(**body))
        if path=='/api/workbench/evaluation-transfer':
            if set(body)-{'document_id','job_id','transfer_id','iteration','start','count'} or not {'document_id','job_id'} <= set(body):
                raise ServiceError(400,'정확한 연성 결과와 전달을 선택하세요.')
            return handler._json(200,workbench.evaluation_transfer(**body))
        if path in {'/api/workbench/report-capture', '/api/workbench/report-content'}:
            field = 'reference' if path.endswith('capture') else 'assets'
            if set(body) != {'document_id', field}:
                raise ServiceError(400, '보고서와 정확한 자료를 선택하세요.')
            function = workbench.report_capture if field == 'reference' else workbench.report_content
            return handler._json(200, function(**body))
        if path=='/api/workbench/research-reference':
            if set(body)!={'reference'}:
                raise ServiceError(400,'Select the exact saved evidence reference')
            return handler._json(200,workbench.research_reference(body['reference']))
        if path=='/api/workbench/domain-plan':
            if set(body)!={'document_id','session_id','expected_generation','command_id'}:
                raise ServiceError(400,'Select the exact source owner generation')
            return handler._json(200,workbench.desktop.domain_plan(**body))
        if path=='/api/workbench/study-followup':
            if set(body)!={'context','kind','session_id','command_id'}:
                raise ServiceError(400,'Select a saved Study issue and target editor')
            return handler._json(200,workbench.desktop.study_followup(**body))
        if path=='/api/workbench/document-compare':
            if set(body)!={'source','prediction_source'}:
                raise ServiceError(400,'Choose the two explicit retained curve references')
            return handler._json(200,workbench.document_compare(**body))
        if path=='/api/workbench/data-followup':
            if set(body)-{'source','kind','session_id','command_id','material_document_id'}:
                raise ServiceError(400,'Unknown follow-up field')
            return handler._json(200,workbench.desktop.data_followup(**body))
        if path=='/api/workbench/post-curve-snapshot':
            if set(body) != {'reference', 'response'}:
                raise ServiceError(400, 'Choose an exact retained Data channel')
            return handler._json(200, workbench.post_curve_snapshot(**body))
        if path=='/api/workbench/post-measurement-preview':
            if set(body) != {'command_id'}:
                raise ServiceError(400,'Select the exact completed native measurement command')
            return handler._json(200,workbench.post_measurement_preview(**body))
        if path=='/api/workbench/post-measurement-plan':
            if set(body) - {'target_plan_id'} != {'command_id','selection','session_id','handoff_id'}:
                raise ServiceError(400,'Choose the measurement, mapping and explicit New Plan action')
            return handler._json(200,workbench.post_measurement_plan(**body))
        if path=='/api/workbench/post-observation':
            if set(body) != {'reference'}:
                raise ServiceError(400,'Select the exact retained Data result reference')
            return handler._json(200,workbench.post_observation(**body))
        if path=='/api/workbench/result-followup':
            if set(body)-{'source_ref','kind','session_id','command_id','request'}:
                raise ServiceError(400,'Unknown result follow-up field')
            return handler._json(200,workbench.desktop.result_followup(**body))
        if path == '/api/workbench/cad-numerical-plan':
            if set(body) != {'command_id', 'operation'}:
                raise ServiceError(400, 'Choose a completed native capture and DOE/optimization')
            from caelab.cad_numerical import prepare_plan
            return handler._json(200, prepare_plan(workbench, **body))
        if path == '/api/workbench/cad-candidate-post':
            if set(body) != {'plan_id', 'job_id', 'candidate_id', 'evaluation_index'}:
                raise ServiceError(400, 'Choose the actual retained candidate field')
            from caelab.cad_numerical import candidate_post
            return handler._json(200, candidate_post(workbench, **body))
        if path == '/api/workbench/cad-candidate-open':
            if set(body) != {'plan_id', 'job_id', 'candidate_id', 'evaluation_index'}:
                raise ServiceError(400, 'Choose the actual retained candidate evaluation')
            from caelab.cad_numerical import open_candidate
            return handler._json(200, open_candidate(workbench, **body))
        if path=='/api/workbench/native-submit':
            if set(body)!={'command_id'}:
                raise ServiceError(400,'Native submit requires the exact completed export command_id')
            return handler._json(202,workbench.desktop.submit_frozen(body['command_id']))
        if path=='/api/workbench/numerical-adopt':
            if set(body)!={'plan_id','job_id','candidate_id','material_document_id','session_id','expected_generation','command_id'}:
                raise ServiceError(400,'Adoption requires the selected candidate and exact target generation')
            return handler._json(200,workbench.desktop.adopt(**body))
        if path=='/api/workbench/pde-candidate-preview':
            if set(body)!={'plan_id','job_id','candidate_id'}:
                raise ServiceError(400,'Select the exact Plan, retained run and PDE candidate')
            return handler._json(200,workbench.desktop.pde_candidate_preview(**body))
        if path=='/api/workbench/domain-candidate-preview':
            if set(body)!={'plan_id','job_id','candidate_id'}:
                raise ServiceError(400,'Select the exact Plan, retained run and domain candidate')
            return handler._json(200,workbench.domain_candidate_preview(**body))
        if path=='/api/workbench/domain-candidate-adopt':
            if set(body)!={'plan_id','job_id','candidate_id','target_document_id','session_id','expected_generation','command_id'}:
                raise ServiceError(400,'Domain adoption requires the reviewed candidate and exact target generation')
            return handler._json(200,workbench.domain_candidate_adopt(**body))
        if path=='/api/workbench/pde-adopt':
            if set(body)!={'plan_id','job_id','candidate_id','pde_document_id','session_id','expected_generation','command_id'}:
                raise ServiceError(400,'PDE adoption requires the bound candidate and exact target generation')
            return handler._json(200,workbench.desktop.pde_adopt(**body))
        if path=='/api/workbench/discussion-plan':
            if set(body)!={'discussion_id','turn_id','proposal_index','session_id','command_id'}:
                raise ServiceError(400,'Select the exact actual discussion proposal and service session')
            return handler._json(200,workbench.desktop.discussion_plan(**body))
        if path=='/api/workbench/pde-plan':
            if set(body)!={'document_id','session_id','expected_generation','command_id'}:
                raise ServiceError(400,'Select the PDE owner, session and exact input generation')
            return handler._json(200,workbench.desktop.pde_plan(**body))
        if path=='/api/workbench/documents/open':
            if set(body)-{'kind','title','draft','document_id'}:
                raise ServiceError(400,'Unknown document field')
            return handler._json(200,workbench.document_open(**body))
        match=re.fullmatch(r'/api/workbench/documents/([^/]+)/commands',path)
        if match:
            if set(body)-{'operation','arguments','session_id','expected_generation','command_id'}:
                raise ServiceError(400,'Unknown document command field')
            return handler._json(200,workbench.document_command(match.group(1),**body))
        if path=='/api/workbench/hosts/register':
            return handler._json(200,workbench.native_commands.register(**body))
        match=re.fullmatch(r'/api/workbench/hosts/([^/]+)/(commands/next|events)',path)
        if match:
            operation=workbench.native_commands.next if match.group(2)=='commands/next' else workbench.native_commands.event
            return handler._json(200,operation(match.group(1),**body))
        match=re.fullmatch(r'/api/workbench/commands/([^/]+)/cancel',path)
        if match:
            if body:
                raise ServiceError(400,'Command cancellation requires empty JSON')
            return handler._json(200,workbench.native_commands.cancel(match.group(1)))
        if path=='/api/workbench/jobs':
            if set(body)-{'operation','arguments','request_id','resources'}:
                raise ServiceError(400,'Unknown job field')
            return handler._json(202,workbench.submit(body['operation'],body.get('arguments',{}),
                    request_id=body.get('request_id'),resources=body.get('resources')))
        match=re.fullmatch(r'/api/workbench/jobs/([^/]+)/cancel',path)
        if match:
            if body:
                raise ServiceError(400,'Cancellation requires empty JSON')
            return handler._json(200,workbench.manager.cancel(match.group(1)))
        if path=='/api/workbench/assist':
            operation=body['operation']
            if operation == 'literature.read':
                # Opening a retained citation is local archive reading only.
                # An absent locator must never turn this into a network fetch.
                arguments = body.get('arguments')
                locator = arguments.get('locator') if isinstance(arguments, dict) else None
                archive = locator.get('archive_id') if isinstance(locator, dict) else None
                if (set(arguments or {}) != {'paper_id', 'locator'} or not isinstance(archive, str)
                        or not re.fullmatch(r'[a-f0-9]{64}', archive)):
                    raise ServiceError(400, 'Select an exact archived literature citation; new reads require a managed job')
            elif operation not in {'knowledge.list','knowledge.search','knowledge.source','experts.list','experts.describe','calculations.plan'}:
                raise ServiceError(400,'Use a managed job for long-running assistance')
            return handler._json(200,workbench.assistance_call(operation,body.get('arguments',{})))
        if path=='/api/workbench/inputs/describe':
            return handler._json(200,workbench.describe_inputs(body))
        if path=='/api/workbench/local-inputs':
            if set(body)!={'root_id','relative'}:
                raise ServiceError(400,'Unknown local input field')
            return handler._json(201,workbench.register_local_input(body['root_id'],body['relative']))
        raise ServiceError(404,'Unknown workbench route')
    if path == '/api/workbench/material-build-context':
        if query:
            raise ServiceError(400, 'Build context takes no arguments')
        from caelab.material_build_permission import context
        return handler._json(200, {**context(), 'service_session_id': workbench.session_id})
    if path == '/api/workbench/expert-connection':
        if query:
            raise ServiceError(400, 'Connection status takes no arguments')
        from caelab.expert_connection import status
        return handler._json(200, status(workbench))
    if path=='/api/workbench':
        return handler._json(200,workbench.overview())
    match=re.fullmatch(r'/api/workbench/numerical/([^/]+)/jobs/([^/]+)/candidates/([^/]+)/evaluations',path)
    if match:
        if set(query)-{'evaluation_index','attempt_id','selection'} or any(len(value)!=1 for value in query.values()):
            raise ServiceError(400,'Choose one exact candidate evaluation/stage and response selection')
        index=int(query['evaluation_index'][0]) if 'evaluation_index' in query else None
        selection=json.loads(query['selection'][0]) if 'selection' in query else None
        return handler._json(200,workbench.numerical_evaluation_result(*match.groups(),evaluation_index=index,
            attempt_id=query.get('attempt_id',[None])[0],selection=selection))
    match=re.fullmatch(r'/api/workbench/(evaluations|studies)/([^/]+)/(inspect|references)',path)
    if match:
        if query or (match.group(1),match.group(3)) not in {('evaluations','inspect'),('studies','references')}:
            raise ServiceError(400,'Unknown research inspection request')
        method=workbench.evaluation_inspect if match.group(1)=='evaluations' else workbench.study_references
        return handler._json(200,method(match.group(2)))
    match=re.fullmatch(r'/api/workbench/evaluations/([^/]+)/jobs/([^/]+)(?:/stages/([^/]+))?',path)
    if match:
        if set(query)-{'selection'} or any(len(value)!=1 for value in query.values()) or query and not match.group(3):
            raise ServiceError(400,'Stage results accept only an explicit response selection')
        if match.group(3):
            selection=json.loads(query['selection'][0]) if 'selection' in query else None
            return handler._json(200,workbench.evaluation_stage_result(*match.groups(),selection=selection))
        return handler._json(200,workbench.evaluation_progress(match.group(1),match.group(2)))
    if path=='/api/workbench/desktop':
        if query:
            raise ServiceError(400,'Desktop context does not accept query arguments')
        return handler._json(200,workbench.desktop.context())
    match=re.fullmatch(r'/api/workbench/jobs/([^/]+)/navigation',path)
    if match:
        if query:
            raise ServiceError(400,'Job navigation does not accept query arguments')
        return handler._json(200,workbench.desktop.navigation(match.group(1)))
    if path in {'/api/workbench/documents','/api/workbench/hosts'}:
        if query:
            raise ServiceError(400,'Listing does not accept query arguments')
        return handler._json(200,workbench.documents() if path.endswith('/documents') else workbench.native_commands.hosts())
    match=re.fullmatch(r'/api/workbench/documents/([^/]+)/source-preview',path)
    if match:
        if query:
            raise ServiceError(400,'Source preview does not accept query arguments')
        return handler._json(200,workbench.document_source_preview(match.group(1)))
    match=re.fullmatch(r'/api/workbench/documents/([^/]+)/comparisons/([^/]+)',path)
    if match:
        if set(query)-{'start','count'} or any(len(value)!=1 for value in query.values()):
            raise ServiceError(400,'Unknown comparison page field')
        start,count=(query.get(key,[default])[0] for key,default in (('start','0'),('count','4096')))
        if not start.isascii() or not start.isdigit() or not count.isascii() or not count.isdigit():
            raise ServiceError(400,'Comparison page requires nonnegative integers')
        owner=workbench._document_owner(match.group(1))
        if getattr(owner,'kind',None) not in {'data','material','pde','simulation'}:
            raise ServiceError(400,'Select the owning research document for this saved curve comparison')
        return handler._json(200,owner.comparison(*match.groups(),start=int(start),count=int(count)))
    match=re.fullmatch(r'/api/workbench/documents/([^/]+)/results/([^/]+)',path)
    if match:
        if set(query)-{'selection'} or any(len(value)!=1 for value in query.values()):
            raise ServiceError(400,'Unknown document result selection')
        selection=json.loads(query['selection'][0]) if 'selection' in query else None
        return handler._json(200,workbench.document_result(match.group(1),match.group(2),selection=selection))
    match=re.fullmatch(r'/api/workbench/documents/([^/]+)/response-locations/([^/]+)',path)
    if match:
        if set(query)-{'channel','start','count','search'} or any(len(value)!=1 for value in query.values()) or 'channel' not in query:
            raise ServiceError(400,'Location lookup requires one exact channel and page')
        start, count = query.get('start',['0'])[0], query.get('count',['128'])[0]
        if not start.isascii() or not start.isdigit() or not count.isascii() or not count.isdigit():
            raise ServiceError(400,'Location page requires nonnegative integer indexes')
        return handler._json(200,workbench.document_response_locations(*match.groups(),query['channel'][0],
            start=int(start),count=int(count),search=query.get('search',[''])[0]))
    match=re.fullmatch(r'/api/workbench/documents/([^/]+)/(result-reference|result-metadata)/([^/]+)',path)
    if match:
        if query:
            raise ServiceError(400,'Result identity/catalog lookup does not accept query arguments')
        method=workbench.document_result_reference if match.group(2)=='result-reference' else workbench.document_result_metadata
        return handler._json(200,method(match.group(1),match.group(3)))
    match=re.fullmatch(r'/api/workbench/(documents|commands)/([^/]+)',path)
    if match:
        if query:
            raise ServiceError(400,'Document/command read does not accept query arguments')
        operation=workbench.document_read if match.group(1)=='documents' else workbench.native_commands.status
        try:
            result=operation(match.group(2))
        except KeyError:
            if match.group(1)=='commands':
                raise ServiceError(404,'Native command ID has not been registered in this service')
            raise
        return handler._json(200,result)
    if path=='/api/workbench/local-roots':
        if query:
            raise ServiceError(400,'Root listing does not accept query arguments')
        return handler._json(200,workbench.local_roots())
    if path=='/api/workbench/local-inputs':
        if set(query)-{'root_id','relative','cursor'} or any(len(values)!=1 for values in query.values()):
            raise ServiceError(400,'Unknown local input query')
        root=query.get('root_id',[''])[0]
        relative=query.get('relative',[''])[0]
        cursor=query.get('cursor',['0'])[0]
        if not cursor.isascii() or not cursor.isdigit():
            raise ServiceError(400,'File cursor must be a nonnegative integer')
        return handler._json(200,workbench.local_inputs(root,relative,cursor=int(cursor)))
    match=re.fullmatch(r'/api/workbench/jobs/([^/]+)',path)
    if match:
        return handler._json(200,workbench.desktop.job_record(match.group(1)))
    match=re.fullmatch(r'/api/workbench/results/([^/]+)',path)
    if match:
        if set(query)-{'responses','selection'} or ('responses' in query and 'selection' in query):
            raise ServiceError(400,'Unknown result selection')
        selected=query.get('responses',[None])[0]
        selection=json.loads(query['selection'][0]) if 'selection' in query else (selected.split(',') if selected else None)
        if isinstance(selection,dict) and set(selection)-{'responses','component','location','rows','time_range','metadata_only'}:
            raise ServiceError(400,'Unknown response selection')
        return handler._json(200,workbench.result(match.group(1),selection=selection))
    match=re.fullmatch(r'/api/workbench/inputs/([^/]+)/native',path)
    if match:
        if query:
            raise ServiceError(400,'Native input lookup does not accept query arguments')
        return handler._json(200,workbench.native_input(match.group(1)))
    match=re.fullmatch(r'/api/workbench/inputs/([^/]+)',path)
    if match:
        return handler._json(200,workbench.input_preview(match.group(1)))
    raise ServiceError(404,'Unknown workbench route')
