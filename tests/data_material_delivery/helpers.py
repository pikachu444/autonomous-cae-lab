from copy import deepcopy
from pathlib import Path
import hashlib, uuid
import numpy as np
from caelab.storage import canonical_hash, save_json, utc_now
from caelab.evaluation import read_result, save_evaluation


def command(owner,document,operation,args=None,cid=None):
    return owner.command(document['id'], operation,args or {},session_id=document['session_id'],
       expected_generation=document['generation'],command_id=cid or 'C'+uuid.uuid4().hex)

class PassiveManager:
    """Durable result fixture, not a claimed JobManager/native execution test."""
    def __init__(self,root): self.root=Path(root); self.jobs={}; self.submissions=[]
    def list(self): return deepcopy(list(self.jobs.values()))
    def status(self,jid): return deepcopy(self.jobs[jid])
    def result(self,jid,selection=None): return read_result(self.root/'results'/jid,selection=selection)
    def submit(self,operation,arguments,request_id=None):
        jid='J'+uuid.uuid4().hex
        job={'id':jid,'operation':operation,'arguments':deepcopy(arguments),'request_id':request_id,
             'state':'SUCCEEDED','created_utc':utc_now(),'result_refs':[],'error':None}
        self.jobs[jid]=job; self.submissions.append(jid)
        return deepcopy(job)

class OwnerSet:
    def __init__(self,root,session='Stest',manager=None,inputs=None):
        from caelab.material_document import MaterialDocuments
        from caelab.data_document import DataDocuments
        from caelab.numerical_document import NumericalDocuments
        self.root=Path(root); self.manager=manager or PassiveManager(self.root)
        self.inputs=inputs or {}
        self.material_documents=MaterialDocuments(self.root,session,self.manager.submit,self.manager)
        self.data_documents=DataDocuments(self.root,session,self.manager.submit,self.manager,
           resolve_input=lambda key:self.inputs[key])
        self.numerical_documents=NumericalDocuments(self.root,session,self.manager.submit,self.manager,
           resolve_document=self.document_read, resolve_result=lambda key,jid,**kw:self._document_owner(key).result(key,jid,**kw),
           resolve_source_revision=lambda key,rev:self._document_owner(key)._verify_revision(key,rev),
           resolve_processing=self.data_documents.processing_result)
    def _document_owner(self,key):
        return next(o for o in (self.material_documents,self.numerical_documents,self.data_documents) if key.startswith(o.prefix))
    def document_read(self,key): return self._document_owner(key).read(key)
    def pair(self):
        from caelab.numerical_document import from_material_document
        m=self.material_documents.open()
        n=self.numerical_documents.open(draft=from_material_document(m))
        return m,n


def fixture_file(folder, variant='A', reorder=False, irregular=False):
    folder=Path(folder); folder.mkdir(parents=True,exist_ok=True)
    rows=[]
    names=['time_s','force_N','extension_mm','temperature_C'] if variant=='A' else ['extension_um','temperature_K','load_kN','time_ms']
    for row in range(1,141):
        time=row/10 + (.021 if irregular and row==64 else 0)
        ext=.005*row; force=20*(.7*row); temperature=20+.03*row
        values=[time,force if row!=82 else np.nan,ext,temperature] if variant=='A' else [ext*1000,temperature+273.15,force/1000 if row!=82 else np.nan,time*1000]
        rows.append(values)
    if reorder:
        order=[2,0,3,1]; names=[names[i] for i in order]; rows=[[r[i] for i in order] for r in rows]
    path=folder/(variant+('_reordered' if reorder else '')+('_irregular' if irregular else '')+'.csv')
    path.write_text(','.join(names)+'\n'+'\n'.join(','.join(format(x,'.15g') for x in row) for row in rows)+'\n', encoding='utf-8')
    return path


def fixture_mapping(variant='A'):
    axis={'column':'time_s' if variant=='A' else 'time_ms','name':'time','unit':'s' if variant=='A' else 'ms'}
    def channel(column,unit,measure,drop=False):
        c={'column':column,'unit':unit,'component':'xx','measure':measure,'frame':'material_cartesian',
           'location':'material_point','reduction':'none','axis':deepcopy(axis)}
        c['row_selection']={'display_hidden_rows':[60]}
        if drop:
            c['row_selection'].update(exclude_rows=[82],quality_rows=[82],
                reasons={'82':'dropout'},quality_reasons={'82':'instrument dropout'})
        return c
    return {'delimiter':',','columns':{
        'force':channel('force_N' if variant=='A' else 'load_kN','N' if variant=='A' else 'kN','force',True),
        'extension':channel('extension_mm' if variant=='A' else 'extension_um','mm' if variant=='A' else 'um','gauge_extension'),
        'temperature':channel('temperature_C' if variant=='A' else 'temperature_K','C' if variant=='A' else 'K','absolute_temperature')}}


def import_fixture(folder,variant='A',reorder=False,irregular=False):
    from caelab.adapters.file_table import read_table
    path=fixture_file(folder,variant,reorder,irregular)
    result=read_table(path,fixture_mapping(variant))
    # Existing read_table has a response map, not a full Workbench envelope.
    if 'responses' not in result:
        result={'execution_status':'SUCCEEDED','responses':result,'checks':[],
                'diagnostics':{'source_sha256':hashlib.sha256(path.read_bytes()).hexdigest()}}
    source={'document_id':'Tfixture'+variant,'job_id':'Jfixture'+variant,'input_revision':'Ifixture'+variant,
            'input_sha256':canonical_hash(fixture_mapping(variant))}
    return path,result,source


def recipe(variant='A'):
    operations=[]
    def op(id,kind,input,settings,output):
        operations.append({'id':id,'operation':kind,'input':input,'settings':settings,'output':output})
    if variant=='B':
        for name in ('extension','force','temperature'):
            op('axis_'+name,'convert_axis',name,{'quantity':'time','to_unit':'s'},name+'_s')
    suffix='_s' if variant=='B' else ''
    op('strain','engineering_strain','extension'+suffix,{'L0':50.,'length_unit':'mm','measurement':'extensometer_gauge_extension'},'e')
    op('stretch','stretch','e',{},'lambda')
    op('stress','nominal_stress','force'+suffix,{'A0':20.,'area_unit':'mm2'},'P11')
    op('temperature','convert','temperature'+suffix,{'quantity':'absolute_temperature','to_unit':'K'},'T_K')
    return {'version':1,'operations':operations}


def attach_import(owners,folder,variant='A'):
    path,imported,_=import_fixture(folder,variant)
    key='Dfixture'+variant
    receipt={'id':key,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'bytes':path.stat().st_size,'name':path.name}
    owners.inputs[key]=(path,receipt)
    owner=owners.data_documents
    d=owner.open(draft={'data_id':key,'mapping':fixture_mapping(variant)})
    response=command(owner,d,'data.import')
    d=response['document']; job=response['job']; jid=job['id']
    save_evaluation(imported,owners.manager.root/'results'/jid)
    owners.manager.jobs[jid]['result_refs']=['result.json']
    run=d['runs'][-1]
    source={'document_id':d['id'],'job_id':jid,'input_revision':run['input_revision'],'input_sha256':run['input_sha256']}
    draft=deepcopy(d['draft']); draft['processing']={'source':source,'recipe':recipe(variant)}
    d=command(owner,d,'data.update',{'draft':draft})['document']
    return d,source,path


def linear_oracle(E=1000.,nu=.25):
    mu=E/(2*(1+nu)); lam=E*nu/((1+nu)*(1-2*nu)); eye=np.eye(3)
    H=lam*np.einsum('ij,kl->ijkl',eye,eye)+mu*(np.einsum('ik,jl->ijkl',eye,eye)+np.einsum('il,jk->ijkl',eye,eye))
    def point(F):
        eps=(F+F.T)/2-eye
        return lam*np.trace(eps)*eye+2*mu*eps,H.copy()
    return point


def neo_oracle(mu=2.,lmbda=6.):
    def point(F):
        J=np.linalg.det(F); inverse=np.linalg.inv(F).T; q=lmbda*np.log(J)-mu
        P=mu*F+q*inverse
        H=mu*np.einsum('ik,jl->ijkl',np.eye(3),np.eye(3))+lmbda*np.einsum('ij,kl->ijkl',inverse,inverse)-q*np.einsum('il,kj->ijkl',inverse,inverse)
        return P,H
    return point
