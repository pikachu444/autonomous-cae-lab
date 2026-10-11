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
        body=handler._json_body()
        if path=='/api/workbench/native-submit':
            if set(body)!={'command_id'}:
                raise ServiceError(400,'Native submit requires the exact completed export command_id')
            return handler._json(202,workbench.desktop.submit_frozen(body['command_id']))
        if path=='/api/workbench/numerical-adopt':
            if set(body)!={'plan_id','job_id','candidate_id','material_document_id','session_id','expected_generation','command_id'}:
                raise ServiceError(400,'Adoption requires the selected candidate and exact target generation')
            return handler._json(200,workbench.desktop.adopt(**body))
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
            if operation not in {'knowledge.list','knowledge.search','knowledge.source','experts.list','experts.describe','calculations.plan'}:
                raise ServiceError(400,'Use a managed job for long-running assistance')
            return handler._json(200,workbench.assistance_call(operation,body.get('arguments',{})))
        if path=='/api/workbench/inputs/describe':
            return handler._json(200,workbench.describe_inputs(body))
        if path=='/api/workbench/local-inputs':
            if set(body)!={'root_id','relative'}:
                raise ServiceError(400,'Unknown local input field')
            return handler._json(201,workbench.register_local_input(body['root_id'],body['relative']))
        raise ServiceError(404,'Unknown workbench route')
    if path=='/api/workbench':
        return handler._json(200,workbench.overview())
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
    match=re.fullmatch(r'/api/workbench/documents/([^/]+)/results/([^/]+)',path)
    if match:
        if set(query)-{'selection'} or any(len(value)!=1 for value in query.values()):
            raise ServiceError(400,'Unknown document result selection')
        selection=json.loads(query['selection'][0]) if 'selection' in query else None
        return handler._json(200,workbench.document_result(match.group(1),match.group(2),selection=selection))
    match=re.fullmatch(r'/api/workbench/(documents|commands)/([^/]+)',path)
    if match:
        if query:
            raise ServiceError(400,'Document/command read does not accept query arguments')
        operation=workbench.document_read if match.group(1)=='documents' else workbench.native_commands.status
        return handler._json(200,operation(match.group(2)))
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
        return handler._json(200,workbench.manager.status(match.group(1)))
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
