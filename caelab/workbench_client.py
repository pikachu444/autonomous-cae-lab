"""Thin loopback HTTP delegation; stdio MCP never creates a second shared controller."""
import json
import io
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

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
            if body is None or error.code!=403 or not _retry_auth:
                raise
            payload=error.read()
            error.fp=io.BytesIO(payload)
            try:
                refusal=json.loads(payload)
            except (ValueError,UnicodeError):
                raise error
            if refusal!={'error':'A valid X-CAE-Token is required'}:
                raise error
            # This exact guard runs before body parsing or effects; one retry cannot duplicate a command.
            self.token=None
            return self.request(path,body,_retry_auth=False)
    def submit(self,operation,arguments,*,request_id=None,resources=None):
        return self.request('/api/workbench/jobs',{'operation':operation,'arguments':arguments,'request_id':request_id,'resources':resources})
    def documents(self):
        return self.request('/api/workbench/documents')
    def document_open(self,*,kind='material',title='Material research',draft=None,document_id=None):
        return self.request('/api/workbench/documents/open',{'kind':kind,'title':title,'draft':draft,'document_id':document_id})
    def document_read(self,identifier):
        from .storage import check_id
        return self.request('/api/workbench/documents/'+check_id(identifier))
    def document_source_preview(self,identifier):
        from .storage import check_id
        return self.request('/api/workbench/documents/'+check_id(identifier)+'/source-preview')
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
    def cancel(self,identifier):
        from .storage import check_id
        return self.request('/api/workbench/jobs/'+check_id(identifier)+'/cancel',{})
    def result(self,identifier,*,selection=None):
        from urllib.parse import urlencode
        from .storage import check_id
        query='?'+urlencode({'selection':json.dumps(selection)}) if selection is not None else ''
        return self.request('/api/workbench/results/'+check_id(identifier)+query)
