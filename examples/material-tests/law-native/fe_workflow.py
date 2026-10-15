"""Actual existing Simulation/JobManager -> FELUPE -> retained/cold reader.

Without --input, runs the three public spatial pairs. With --input, runs an
explicit law_freeze simulation_draft. Never converts a rejection to success.
"""
from copy import deepcopy
from pathlib import Path
import argparse,sys,time,traceback
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
from caelab.workbench import Workbench
from caelab.storage import save_json,load_json,canonical_hash
from caelab import law_native_fe as fe
from plugins.material_point import law_native as law

def command(wb,d,op,args=None):
    return wb.document_command(d['id'],op,args or {},session_id=d['session_id'],expected_generation=d['generation'])

def execute(output,input_path=None):
    root=Path(output);root.mkdir(parents=True,exist_ok=False)
    receipt={'status':'STARTING','platform':sys.platform,'Windows':'ACTUAL' if sys.platform=='win32' else 'NOT_RUN',
             'cases':[],'native_assignment':'EXPLICIT_FROZEN_INPUT' if input_path else 'NOT_TESTED_PUBLIC_SYNTHETIC_MESH'}
    wb=None;code=1
    try:
        if input_path:
            seed=load_json(input_path);drafts=[seed.get('simulation_draft',seed)]
        else:drafts=[{'backend':law.FE,'settings':fe.default_settings(m)} for m in law.MODELS]
        wb=Workbench(root/'workspace')
        for draft in drafts:
            d=wb.document_open(kind='simulation',title='공개 동일 법칙 FE 시편',draft=deepcopy(draft))
            d=command(wb,d,'document.save')['document']
            launched=command(wb,d,'simulation.evaluate');job=launched['job'];deadline=time.monotonic()+195
            while time.monotonic()<deadline:
                status=wb.manager.status(job['id'])
                if status['state'] in ('SUCCEEDED','FAILED','CANCELLED','REJECTED','INTERRUPTED'):break
                time.sleep(.03)
            else:raise TimeoutError('Existing FE worker did not finish within the bounded acceptance wait')
            r=wb.result(job['id'])
            record={'model':draft['settings']['law']['model'],'document_id':d['id'],'job_id':job['id'],
                    'execution_status':r['execution_status'],'result_sha256':canonical_hash(r),
                    'FE_execution':r.get('diagnostics',{}).get('FE_execution'),
                    'pair':r.get('diagnostics',{}).get('pair_comparison')}
            receipt['cases'].append(record);save_json(root/'workflow-receipt.json',receipt)
            if r['execution_status']!='SUCCEEDED' or record['FE_execution']!='ACTUAL' or record['pair']['status']!='PASS':
                raise AssertionError('Actual FE and same-law point comparison have not both passed')
            command(wb,wb.document_read(d['id']),'document.save')
        receipt['jobs_before_cold']=len(wb.manager.list())
        receipt['first_shutdown']=wb.shutdown();wb=None
        if not receipt['first_shutdown']['joined']:raise RuntimeError('First owner cleanup not confirmed')
        wb=Workbench(root/'workspace')
        for row in receipt['cases']:
            wb.document_open(kind='simulation',document_id=row['document_id'])
            if canonical_hash(wb.result(row['job_id']))!=row['result_sha256']:
                raise AssertionError('Cold retained result bytes changed')
        if len(wb.manager.list())!=receipt['jobs_before_cold']:raise AssertionError('Cold read submitted a job')
        receipt['status']='PASS';code=0
    except BaseException as error:
        receipt.update(status='FAIL',error_type=type(error).__name__,error=str(error),traceback=traceback.format_exc())
        traceback.print_exc()
    finally:
        if wb is not None:
            receipt['finally_shutdown']=wb.shutdown()
            if not receipt['finally_shutdown']['joined']:receipt['cleanup']='UNKNOWN';code=125
        save_json(root/'workflow-receipt.json',receipt)
    return code

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);p.add_argument('--input')
    a=p.parse_args();raise SystemExit(execute(a.output,a.input))
