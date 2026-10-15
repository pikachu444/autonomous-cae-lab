"""Bound Material / report host for C1 service gates, using real document owners.

Numerical work is explicitly algebraic synthetic stress, NOT the FELUPE solver.
Only Workbench initialization of absent native imports is bypassed. Existing
Workbench.document_command, DesktopLinks and report reference methods execute.
"""
from copy import deepcopy
import threading
from types import SimpleNamespace

from caelab.material_document import MaterialDocuments
from caelab.numerical_document import from_material_document
from caelab.desktop_links import DesktopLinks
from caelab.workbench import Workbench
from caelab.report_document import ReportDocuments
from caelab.research_workflows import resolve_reference
from caelab.workbench_client import Client
from caelab.storage import canonical_hash
from _numerical_candidate_detail_support import DetailHost


def algebra_stress(values,settings):
    return {'execution_status':'SUCCEEDED','responses':{'stress_xx':{
        'kind':'series','unit':'MPa','value':[values['E']*.001*t for t in settings['time']],
        'component':'xx','location':'material_point','reduction':'none',
        'measure':'infinitesimal_Cauchy','frame':'material_cartesian',
        'axes':[{'name':'time','unit':'s','values':settings['time']}]}},
        'diagnostics':{'test_fixture':'algebra_stress_not_felupe','protocol':deepcopy(settings)}}


class BoundHost(DetailHost):
    def __init__(self,root):
        super().__init__(root,evaluator=algebra_stress)
        self.materials=MaterialDocuments(root,self.owner.session_id,self._submit,self.manager)
        self.data_docs,self.data_results={},{}
        self.owner.resolve_document=lambda ident:self.materials.read(ident) if ident.startswith('M') else deepcopy(self.data_docs[ident])
        self.owner.resolve_result=lambda ident,job,**kwargs:deepcopy(self.data_results[ident])
        self.core=Workbench.__new__(Workbench)
        self.core.root=self.root
        self.core.session_id=self.owner.session_id
        self.core.config={}
        self.core.manager=self.manager
        self.core._assist_config_lock=threading.RLock()
        self.core.numerical_documents=self.owner
        self.core.material_documents=self.materials
        self.core.native_commands=object()
        self.core.desktop=DesktopLinks(self.core)
        # Real Workbench dispatch remains unchanged; only absent other owners
        # are outside this focused synthetic host.
        self.reports=ReportDocuments(root,self.owner.session_id,self._submit,self.manager,
            resolve_reference=lambda ref:resolve_reference(self.core,ref))
        self.core.report_documents=self.reports
        self.core._document_owner=lambda ident: {'M':self.materials,'N':self.owner,'B':self.reports}[ident[0]]
        self.core.document_read=lambda ident:self.core._document_owner(ident).read(ident)
        self.core.document_result=lambda ident,job,**kwargs:self.core._document_owner(ident).result(ident,job,**kwargs)

    def create_bound_fit(self):
        material=self.materials.open(title='원 Material — synthetic binding test')
        draft=from_material_document(material)
        protocol=material['draft']['settings']
        for var in draft['variables']:
            if var['id']=='E': var.update(lower=500.,upper=2000.)
        for i in range(2):
            response=algebra_stress({'E':1250.},protocol)['responses']['stress_xx']
            response.update(source_rows=[i*10+j for j in (1,3,5)],source_column_identity=2)
            source=dict(document_id=f'Tobs{i}',job_id=f'Jobs{i}',input_revision=f'Robs{i}',
                        input_sha256=canonical_hash({'obs':i}),response='stress_xx')
            self.data_docs[source['document_id']]=dict(id=source['document_id'],kind='data',runs=[dict(
                job_id=source['job_id'],input_revision=source['input_revision'],input_sha256=source['input_sha256'])])
            self.data_results[source['document_id']]=dict(execution_status='SUCCEEDED',
                responses={'stress_xx':response},diagnostics={'source_sha256':canonical_hash({'i':i})})
            draft['experiments'].append(dict(id=f'Trial{i}',role='fit' if i==0 else 'holdout',source=source,
                response='stress_xx',settings=deepcopy(protocol),weight=2.,scale=1.))
        document=self.owner.open(title='계수 채택 근거',draft=draft)
        assert document['diagnostics']==[],document['diagnostics']
        result=self.command(document['id'],'numerical.run',{})
        job=result['job']['id'];assert self.wait(job)['state']=='SUCCEEDED'
        return document['id'],job,material['id']

    def report_command(self,identifier,operation,arguments):
        document=self.reports.read(identifier)
        return self.reports.command(identifier,operation,arguments,session_id=document['session_id'],
            expected_generation=document['generation'])


class InProcessClient(Client):
    """Wire-format test using real Client methods, not an HTTP server claim."""
    def __init__(self,core):
        super().__init__('http://127.0.0.1:8000');self.core=core;self.requests=[]
    def request(self,path,body=None,**kwargs):
        self.requests.append((path,deepcopy(body)))
        if path.endswith('/commands'):
            return self.core.document_command(path.split('/')[-2],body['operation'],body['arguments'],
                **{k:body[k] for k in ('session_id','expected_generation','command_id') if k in body})
        if '/documents/' in path and body is None:
            return self.core.document_read(path.split('/')[-1])
        if path=='/api/workbench/numerical-adopt':
            return self.core.desktop.adopt(**body)
        raise AssertionError('Unexpected request '+repr((path,body)))
