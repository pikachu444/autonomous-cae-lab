"""Actual existing Data -> Material/Numerical fit -> evidence -> explicit CAS -> cold owner.

Only k0 is fitted to independent synthetic tension/shear. Compression/confinement
are holdout. E, nu, alpha, beta, H are FIXED, not identified by this experiment.
No native solver or paid provider is run. Original observations remain immutable.
"""
from copy import deepcopy
from pathlib import Path
import argparse,json,sys,time,uuid
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(Path(__file__).parent))
from reference_cases import protocols
from caelab.workbench import Workbench
from caelab.storage import canonical_hash,save_json
from caelab.numerical_document import from_material_document
from caelab.material_fe_transfer import source_snapshot
from plugins.material_point.law_native import POINT


def command(wb,doc,op,args=None,cid=None):
    return wb.document_command(doc['id'],op,args or {},session_id=doc['session_id'],
        expected_generation=doc['generation'],command_id=cid or 'C'+uuid.uuid4().hex)


def wait(wb,job):
    deadline=time.monotonic()+20
    while time.monotonic()<deadline:
        status=wb.manager.status(job['id'])
        if status['state'] in ('SUCCEEDED','FAILED','CANCELLED','REJECTED','INTERRUPTED'):
            if status['state']!='SUCCEEDED':raise RuntimeError(str(status))
            return wb.result(job['id'])
        time.sleep(.01)
    raise TimeoutError('Bounded existing JobManager operation exceeded 20 seconds')


def execute(root):
    root=Path(root);root.mkdir(parents=True,exist_ok=False)
    wb=Workbench(root/'workspace');receipt={'source_kind':'SYNTHETIC_ANALYTICAL_REFERENCE',
        'native_FE':'NOT_RUN','Windows':'NOT_RUN' if sys.platform!='win32' else 'ACTUAL_PYTHON_ONLY',
        'identified':['k0'],'fixed':['E','nu','alpha','beta','H'],'engineering_release':'UNKNOWN'}
    try:
        cases=protocols();s=deepcopy(cases[0]['settings']);s['parameters']['k0']=275.
        material=wb.document_open(kind='material',title='DP synthetic k0 calibration',draft={'backend':POINT,'settings':s})
        material=command(wb,material,'document.save')['document'];original=deepcopy(material)
        plan=from_material_document(material);plan['budget']=80
        for variable in plan['variables']:
            variable['free']=variable['id']=='k0'
            if variable['free']:variable.update(value=275.,lower=200.,upper=300.)
        sources=[]
        for i,case in enumerate(cases):
            data_bytes=('time_s,stress_MPa\n'+'\n'.join(f'{t:.17g},{v:.17g}' for t,v in zip(case['settings']['time'],case['observations']))+'\n').encode()
            upload=wb.upload(case['id']+'.csv',data_bytes)
            mapping={'delimiter':',','skip_header':1,'columns':{'stress':{'column':1,'unit':'MPa','component':case['component'],
                'measure':'infinitesimal_Cauchy','frame':'material_cartesian','location':'material_point','reduction':'none',
                'scale':1.,'axis':{'column':0,'name':'time','unit':'s','scale':1.}}}}
            data=wb.document_open(kind='data',title=case['id']+' — synthetic',draft={'data_id':upload['id'],'mapping':mapping})
            started=command(wb,data,'data.import');wait(wb,started['job'])
            data=command(wb,wb.document_read(data['id']),'document.save')['document'];run=data['runs'][0]
            source={'document_id':data['id'],'job_id':run['job_id'],'response':'stress',
                    'input_revision':run['input_revision'],'input_sha256':run['input_sha256']}
            sources.append(source)
            plan['experiments'].append({'id':case['id'],'role':case['role'],'source':source,
                'response':case['response'],'settings':deepcopy(case['settings']),'weight':float(i+1),'scale':1.})
        p=wb.document_open(kind='numerical',title='DP two-fit two-holdout',draft=plan)
        if p['diagnostics']:raise ValueError(str(p['diagnostics']))
        compiled=wb.numerical_documents.job_arguments(plan)
        save_json(root/'compiled-fit-input.json',compiled)
        started=command(wb,p,'numerical.run');result=wait(wb,started['job'])
        if abs(result['parameters']['k0']-250)>1e-6:raise AssertionError('Independent synthetic k0 was not recovered')
        if any(c['rmse']>1e-6 for c in result['curves']):raise AssertionError('Fit/holdout failed independent expected stresses')
        best=min((c for c in result['candidates'] if c['execution_status']=='SUCCEEDED'),key=lambda c:c['objective'])
        view=wb.numerical_candidate_detail(p['id'],started['job']['id'],best['candidate_id'])
        # Original candidate/final holdout detail must already be retained; no hidden re-fit.
        p=wb.document_read(p['id'])
        captured=command(wb,p,'numerical.evidence.capture',{'source':view['source'],'candidate_id':best['candidate_id'],
            'attempt_job_id':None,'purpose':'success_judgment'},cid='ClawEvidence')
        reference=captured.get('reference',captured.get('evidence_reference'))
        material=wb.document_read(material['id']);adopt_args=dict(material_document_id=material['id'],
            session_id=material['session_id'],expected_generation=material['generation'],command_id='ClawAdopt',detail_evidence=reference)
        adopted=wb.desktop.adopt(p['id'],started['job']['id'],best['candidate_id'],**adopt_args)['document']
        replay=wb.desktop.adopt(p['id'],started['job']['id'],best['candidate_id'],**adopt_args)['document']
        if adopted['generation']!=replay['generation']:raise AssertionError('Lost-ack adoption duplicated a write')
        saved=command(wb,adopted,'document.save')['document']
        source=source_snapshot(wb.material_documents,{'document_id':saved['id'],'saved_revision':saved['saved_revision'],
                                                    'input_sha256':canonical_hash(saved['draft'])})
        save_json(root/'source-snapshot.json',source)
        command(wb,wb.document_read(p['id']),'document.save')
        jobs=len(wb.manager.list());receipt.update(parameters=result['parameters'],curves=result['curves'],
            material_id=saved['id'],numerical_id=p['id'],job_id=started['job']['id'],candidate_id=best['candidate_id'],
            data_sources=sources,evidence_reference=reference,jobs=jobs,source_snapshot_sha256=source['snapshot_sha256'],
            original_material_sha256=canonical_hash(original['draft']),adopted_material_sha256=canonical_hash(saved['draft']),
            result_sha256=canonical_hash(result))
        if not wb.shutdown()['joined']:raise RuntimeError('Original Workbench did not close')
        wb=Workbench(root/'workspace')
        cold=wb.document_open(kind='material',document_id=saved['id'])
        old=wb.document_result(p['id'],started['job']['id'])
        if cold['draft']!=saved['draft'] or canonical_hash(old)!=receipt['result_sha256'] or len(wb.manager.list())!=jobs:
            raise AssertionError('Cold owner changed saved inputs/results or submitted new jobs')
        receipt.update(status='PASS',cold_reopen='PASS',automatic_new_jobs=0)
        return receipt
    except BaseException as error:
        receipt.update(status='FAIL',error_type=type(error).__name__,error=str(error));raise
    finally:
        receipt['finally_shutdown']=wb.shutdown()
        save_json(root/'workflow-receipt.json',receipt)


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',required=True)
    r=execute(ap.parse_args().output);print(json.dumps({k:v for k,v in r.items() if k!='curves'},ensure_ascii=False,indent=2))
