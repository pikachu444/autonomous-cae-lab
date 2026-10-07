"""HTTP routes only; numerical and assistance behavior lives in shared services."""
import re
import json
from .service import ServiceError


def handle(handler,method,path,query):
    workbench=handler.server.workbench
    if method=='POST':
        if query:
            raise ServiceError(400,'POST does not accept query arguments')
        if path=='/api/workbench/upload':
            payload=handler._bytes_body('application/octet-stream',16*1024*1024,1)
            return handler._json(201,workbench.upload(handler.headers.get('X-File-Name',''),payload))
        body=handler._json_body()
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
        raise ServiceError(404,'Unknown workbench route')
    if path=='/api/workbench':
        return handler._json(200,workbench.overview())
    match=re.fullmatch(r'/api/workbench/jobs/([^/]+)',path)
    if match:
        return handler._json(200,workbench.manager.status(match.group(1)))
    match=re.fullmatch(r'/api/workbench/results/([^/]+)',path)
    if match:
        if set(query)-{'responses','selection'} or ('responses' in query and 'selection' in query):
            raise ServiceError(400,'Unknown result selection')
        selected=query.get('responses',[None])[0]
        selection=json.loads(query['selection'][0]) if 'selection' in query else (selected.split(',') if selected else None)
        if isinstance(selection,dict) and set(selection)-{'responses','component','location','rows','time_range'}:
            raise ServiceError(400,'Unknown response selection')
        return handler._json(200,workbench.manager.result(match.group(1),selection=selection))
    match=re.fullmatch(r'/api/workbench/inputs/([^/]+)',path)
    if match:
        return handler._json(200,workbench.input_preview(match.group(1)))
    raise ServiceError(404,'Unknown workbench route')
