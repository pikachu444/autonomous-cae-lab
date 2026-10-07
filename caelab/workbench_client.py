"""Thin loopback HTTP delegation; stdio MCP never creates a second shared controller."""
import json
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

class Client:
    def __init__(self,url):
        parsed=urlsplit(url)
        if parsed.scheme!='http' or parsed.hostname not in {'127.0.0.1','localhost'} or parsed.path not in {'','/'} or parsed.username:
            raise ValueError('Use an explicit local workbench service URL')
        self.url=url.rstrip('/')
        self.token=None
    def request(self,path,body=None):
        headers={}
        data=None
        if body is not None:
            if self.token is None:
                self.token=self.request('/api/overview')['token']
            headers={'Content-Type':'application/json','X-CAE-Token':self.token}
            data=json.dumps(body,allow_nan=False).encode()
        with urlopen(Request(self.url+path,data=data,headers=headers),timeout=30) as response:
            return json.load(response)
    def submit(self,operation,arguments,*,request_id=None,resources=None):
        return self.request('/api/workbench/jobs',{'operation':operation,'arguments':arguments,'request_id':request_id,'resources':resources})
    def status(self,identifier):
        from .storage import check_id
        return self.request('/api/workbench/jobs/'+check_id(identifier))
    def cancel(self,identifier):
        from .storage import check_id
        return self.request('/api/workbench/jobs/'+check_id(identifier)+'/cancel',{})
    def result(self,identifier,*,selection=None):
        from urllib.parse import urlencode
        from .storage import check_id
        query='?'+urlencode({'selection':json.dumps(selection)}) if selection is not None else ''
        return self.request('/api/workbench/results/'+check_id(identifier)+query)
