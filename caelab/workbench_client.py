"""Thin loopback HTTP delegation; stdio MCP never creates a second shared controller."""
import json
import io
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


class WorkbenchHTTPError(HTTPError):
    """Keep HTTP status/receipt bytes and a validated service diagnostic."""
    def __init__(self, error, payload, message):
        super().__init__(error.url, error.code, error.reason, error.headers, io.BytesIO(payload))
        self.service_message = message

    def __str__(self):
        return f'HTTP {self.code}: {self.service_message}'


class Client:
    def __init__(self,url):
        parsed=urlsplit(url)
        if parsed.scheme!='http' or parsed.hostname not in {'127.0.0.1','localhost'} or parsed.path not in {'','/'} or parsed.username:
            raise ValueError('Use an explicit local workbench service URL')
        self.url=url.rstrip('/')
        self.token=None
    def request(self,path,body=None,*,_retry_auth=True):
        headers={}
        data=None
        if body is not None:
            if self.token is None:
                self.token=self.request('/api/overview')['token']
            headers={'Content-Type':'application/json','X-CAE-Token':self.token}
            data=json.dumps(body,allow_nan=False).encode()
        try:
            with urlopen(Request(self.url+path,data=data,headers=headers),timeout=30) as response:
                return json.load(response)
        except HTTPError as error:
            payload=error.read()
            error.fp=io.BytesIO(payload)
            try:
                refusal=json.loads(payload)
            except (ValueError,UnicodeError):
                raise error
            if body is not None and error.code == 403 and _retry_auth and refusal == {'error':'A valid X-CAE-Token is required'}:
                # This exact guard runs before body parsing or effects. Only
                # this refusal is retried, with the unchanged request body/ID.
                self.token=None
                return self.request(path,body,_retry_auth=False)
            message = refusal.get('error') if isinstance(refusal, dict) else None
            if isinstance(message, str) and message.strip():
                raise WorkbenchHTTPError(error, payload, message) from error
            raise error

    def upload(self, name, payload, *, _retry_auth=True):
        """Register explicitly selected local bytes through the existing bounded endpoint."""
        from urllib.parse import quote
        if not isinstance(payload, bytes) or not 1 <= len(payload) <= 16 * 1024 * 1024:
            raise ValueError('Choose a nonempty file no larger than 16 MiB')
        if self.token is None:
            self.token = self.request('/api/overview')['token']
        headers = {'Content-Type': 'application/octet-stream', 'X-CAE-Token': self.token,
                   'X-File-Name': quote(name, safe=''), 'X-File-Name-Encoding': 'percent-utf8'}
        try:
            with urlopen(Request(self.url + '/api/workbench/upload', data=payload, headers=headers), timeout=30) as response:
                return json.load(response)
        except HTTPError as error:
            body = error.read()
            error.fp = io.BytesIO(body)
            try:
                refusal = json.loads(body)
            except (ValueError, UnicodeError):
                raise error
            if error.code == 403 and _retry_auth and refusal == {'error': 'A valid X-CAE-Token is required'}:
                self.token = None
                return self.upload(name, payload, _retry_auth=False)
            if isinstance(refusal, dict) and isinstance(refusal.get('error'), str):
                raise WorkbenchHTTPError(error, body, refusal['error']) from error
            raise error

    def submit(self,operation,arguments,*,request_id=None,resources=None):
        return self.request('/api/workbench/jobs',{'operation':operation,'arguments':arguments,'request_id':request_id,'resources':resources})
    def backend_readiness(self, backend):
        return self.request('/api/workbench/backend-readiness', {'backend': backend})
    def documents(self):
        return self.request('/api/workbench/documents')
    def document_open(self,*,kind='material',title=None,draft=None,document_id=None):
        return self.request('/api/workbench/documents/open',{'kind':kind,'title':title,'draft':draft,'document_id':document_id})
    def document_read(self,identifier):
        from .storage import check_id
        return self.request('/api/workbench/documents/'+check_id(identifier))
    def document_source_preview(self,identifier):
        from .storage import check_id
        return self.request('/api/workbench/documents/'+check_id(identifier)+'/source-preview')
    def document_compare(self,source,prediction_source):
        return self.request('/api/workbench/document-compare',{'source':source,'prediction_source':prediction_source})
    def document_comparison(self,identifier,comparison_id,*,start=0,count=4096):
        from .storage import check_id
        from urllib.parse import urlencode
        return self.request('/api/workbench/documents/'+check_id(identifier)+'/comparisons/'+check_id(comparison_id)+'?'+urlencode({'start':start,'count':count}))
    def constitutive_inspect(self, document_id, job_id, increment=0):
        return self.request('/api/workbench/constitutive-inspect', dict(document_id=document_id, job_id=job_id, increment=increment))

    def evaluation_transfer(self, document_id, job_id, transfer_id=None, iteration=None, *, start=0, count=256):
        return self.request('/api/workbench/evaluation-transfer', dict(document_id=document_id, job_id=job_id,
            transfer_id=transfer_id, iteration=iteration, start=start, count=count))

    def evaluation_inspect(self, identifier):
        from .storage import check_id
        return self.request('/api/workbench/evaluations/'+check_id(identifier)+'/inspect')
    def evaluation_progress(self, identifier, job_id):
        from .storage import check_id
        return self.request('/api/workbench/evaluations/'+check_id(identifier)+'/jobs/'+check_id(job_id))
    def evaluation_stage_result(self, identifier, job_id, attempt_id, *, selection=None):
        from .storage import check_id
        from urllib.parse import urlencode
        query='?'+urlencode({'selection':json.dumps(selection)}) if selection is not None else ''
        return self.request('/api/workbench/evaluations/'+check_id(identifier)+'/jobs/'+check_id(job_id)+'/stages/'+check_id(attempt_id)+query)
    def numerical_evaluation_result(self, identifier, job_id, candidate_id, *, evaluation_index=None, attempt_id=None, selection=None):
        from .storage import check_id
        from urllib.parse import urlencode
        query={key:value for key,value in dict(evaluation_index=evaluation_index,attempt_id=attempt_id).items() if value is not None}
        if selection is not None: query['selection']=json.dumps(selection)
        suffix='?'+urlencode(query) if query else ''
        return self.request('/api/workbench/numerical/'+check_id(identifier)+'/jobs/'+check_id(job_id)+'/candidates/'+check_id(candidate_id)+'/evaluations'+suffix)
    def study_references(self, identifier):
        from .storage import check_id
        return self.request('/api/workbench/studies/'+check_id(identifier)+'/references')
    def research_reference(self, reference):
        return self.request('/api/workbench/research-reference',{'reference':reference})
    def domain_plan(self, document_id, *, session_id, expected_generation, command_id):
        return self.request('/api/workbench/domain-plan',dict(document_id=document_id,
            session_id=session_id,expected_generation=expected_generation,command_id=command_id))
    def study_followup(self, context, kind, *, session_id, command_id):
        return self.request('/api/workbench/study-followup',dict(context=context,kind=kind,
            session_id=session_id,command_id=command_id))
    def data_followup(self,source,kind,*,session_id,command_id,material_document_id=None):
        return self.request('/api/workbench/data-followup',dict(source=source,kind=kind,session_id=session_id,
            command_id=command_id,material_document_id=material_document_id))
    def document_command(self,identifier,operation,arguments,*,session_id,expected_generation,command_id=None):
        from .storage import check_id
        return self.request('/api/workbench/documents/'+check_id(identifier)+'/commands',{
            'operation':operation,'arguments':arguments,'session_id':session_id,
            'expected_generation':expected_generation,'command_id':command_id})
    def document_result(self,identifier,job_id,*,selection=None):
        from .storage import check_id
        from urllib.parse import urlencode
        query='?'+urlencode({'selection':json.dumps(selection)}) if selection is not None else ''
        return self.request('/api/workbench/documents/'+check_id(identifier)+'/results/'+check_id(job_id)+query)
    def document_result_reference(self,identifier,job_id):
        from .storage import check_id
        return self.request('/api/workbench/documents/'+check_id(identifier)+'/result-reference/'+check_id(job_id))
    def document_result_metadata(self,identifier,job_id):
        from .storage import check_id
        return self.request('/api/workbench/documents/'+check_id(identifier)+'/result-metadata/'+check_id(job_id))
    def document_response_locations(self,identifier,job_id,channel,*,start=0,count=128,search=''):
        from .storage import check_id
        from urllib.parse import urlencode
        query = urlencode(dict(channel=channel, start=start, count=count, search=search))
        return self.request('/api/workbench/documents/'+check_id(identifier)+'/response-locations/'+check_id(job_id)+'?'+query)
    def post_measurement_preview(self, command_id):
        return self.request('/api/workbench/post-measurement-preview', {'command_id': command_id})
    def post_measurement_plan(self, command_id, selection, *, session_id, handoff_id, target_plan_id=None):
        return self.request('/api/workbench/post-measurement-plan', dict(command_id=command_id,
            selection=selection, session_id=session_id, handoff_id=handoff_id, target_plan_id=target_plan_id))
    def post_observation(self, reference):
        return self.request('/api/workbench/post-observation', {'reference': reference})
    def result_followup(self,source_ref,kind='expert',*,session_id,command_id,request=None):
        return self.request('/api/workbench/result-followup',dict(source_ref=source_ref,kind=kind,
            session_id=session_id,command_id=command_id,request=request))
    def expert_connection(self):
        return self.request('/api/workbench/expert-connection')
    def reload_expert_connection(self, expected_sha256):
        return self.request('/api/workbench/expert-connection/reload', {'expected_sha256': expected_sha256})

    def hosts(self):
        return self.request('/api/workbench/hosts')
    def command_status(self,identifier):
        from .storage import check_id
        return self.request('/api/workbench/commands/'+check_id(identifier))
    def command_cancel(self,identifier):
        from .storage import check_id
        return self.request('/api/workbench/commands/'+check_id(identifier)+'/cancel',{})
    def local_roots(self):
        return self.request('/api/workbench/local-roots')
    def local_inputs(self,root_id,relative='',*,cursor=0):
        from urllib.parse import urlencode
        return self.request('/api/workbench/local-inputs?'+urlencode({'root_id':root_id,'relative':relative,'cursor':cursor}))
    def register_local_input(self,root_id,relative):
        return self.request('/api/workbench/local-inputs',{'root_id':root_id,'relative':relative})
    def input_preview(self,identifier):
        from .storage import check_id
        return self.request('/api/workbench/inputs/'+check_id(identifier))
    def native_input(self,identifier):
        from .storage import check_id
        return self.request('/api/workbench/inputs/'+check_id(identifier)+'/native')
    def status(self,identifier):
        from .storage import check_id
        return self.request('/api/workbench/jobs/'+check_id(identifier))
    def desktop_context(self):
        return self.request('/api/workbench/desktop')
    def cad_numerical_plan(self, command_id, *, operation='doe'):
        return self.request('/api/workbench/cad-numerical-plan', {'command_id': command_id, 'operation': operation})

    def cad_candidate_post(self, plan_id, job_id, candidate_id, evaluation_index):
        return self.request('/api/workbench/cad-candidate-post', dict(plan_id=plan_id, job_id=job_id,
            candidate_id=candidate_id, evaluation_index=evaluation_index))

    def cad_candidate_open(self, plan_id, job_id, candidate_id, evaluation_index):
        return self.request('/api/workbench/cad-candidate-open', dict(plan_id=plan_id, job_id=job_id,
            candidate_id=candidate_id, evaluation_index=evaluation_index))

    def native_submit(self, command_id):
        return self.request('/api/workbench/native-submit', {'command_id':command_id})
    def job_navigation(self, identifier):
        from .storage import check_id
        return self.request('/api/workbench/jobs/'+check_id(identifier)+'/navigation')
    def numerical_adopt(self, document_id, job_id, candidate_id, *, material_document_id,
                        session_id, expected_generation, command_id):
        return self.request('/api/workbench/numerical-adopt', dict(plan_id=document_id,job_id=job_id,
            candidate_id=candidate_id,material_document_id=material_document_id,session_id=session_id,
            expected_generation=expected_generation,command_id=command_id))
    def describe_inputs(self, request):
        return self.request('/api/workbench/inputs/describe', request)
    def pde_candidate_preview(self, plan_id, job_id, candidate_id):
        return self.request('/api/workbench/pde-candidate-preview', dict(plan_id=plan_id, job_id=job_id, candidate_id=candidate_id))
    def domain_candidate_preview(self, plan_id, job_id, candidate_id):
        return self.request('/api/workbench/domain-candidate-preview',dict(plan_id=plan_id,job_id=job_id,candidate_id=candidate_id))
    def domain_candidate_adopt(self, plan_id, job_id, candidate_id, *, target_document_id, session_id, expected_generation, command_id):
        return self.request('/api/workbench/domain-candidate-adopt',dict(plan_id=plan_id,job_id=job_id,candidate_id=candidate_id,
            target_document_id=target_document_id,session_id=session_id,expected_generation=expected_generation,command_id=command_id))
    def pde_adopt(self, plan_id, job_id, candidate_id, *, pde_document_id,
                  session_id, expected_generation, command_id):
        return self.request('/api/workbench/pde-adopt', dict(plan_id=plan_id, job_id=job_id,
            candidate_id=candidate_id, pde_document_id=pde_document_id, session_id=session_id,
            expected_generation=expected_generation, command_id=command_id))
    def discussion_plan(self, discussion_id, turn_id, proposal_index, *, session_id, command_id):
        return self.request('/api/workbench/discussion-plan',dict(discussion_id=discussion_id,
            turn_id=turn_id,proposal_index=proposal_index,session_id=session_id,command_id=command_id))
    def pde_plan(self, document_id, *, session_id, expected_generation, command_id):
        return self.request('/api/workbench/pde-plan',dict(document_id=document_id,
            session_id=session_id,expected_generation=expected_generation,command_id=command_id))
    def cancel(self,identifier):
        from .storage import check_id
        return self.request('/api/workbench/jobs/'+check_id(identifier)+'/cancel',{})
    def result(self,identifier,*,selection=None):
        from urllib.parse import urlencode
        from .storage import check_id
        query='?'+urlencode({'selection':json.dumps(selection)}) if selection is not None else ''
        return self.request('/api/workbench/results/'+check_id(identifier)+query)
