"""FC06: actual Data -> existing Simulation -> select -> save -> separate cold process.

Run from the repository root:
  python examples/impact/strain_fatigue_example.py --output /absolute/new/folder
No FE/native/provider calls, no network/server and no installation.
"""
from __future__ import annotations
import argparse
from copy import deepcopy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from caelab.workbench import Workbench
from caelab.fatigue_example import csv_bytes,data_draft,settings
from caelab.fatigue_strain import select_result
from caelab.storage import canonical_hash


def command(wb,doc,op,args=None):
    return wb.document_command(doc['id'],op,args or {},session_id=doc['session_id'],expected_generation=doc['generation'])


def wait(wb,job):
    deadline=time.monotonic()+30
    while time.monotonic()<deadline:
        state=wb.manager.status(job['id'])
        if state['state'] in {'SUCCEEDED','FAILED','CANCELLED','REJECTED','PARTIAL_FAILURE','INTERRUPTED'}:
            if state['state']!='SUCCEEDED':
                raise AssertionError(state)
            return wb.result(job['id'])
        time.sleep(.01)
    wb.manager.cancel(job['id'])
    raise TimeoutError('Owned synthetic import/assessment did not complete within 30 s')


def cold(folder,expected):
    wb=Workbench(folder)
    try:
        assert len(wb.manager.list())==0
        data=wb.document_open(kind='data',document_id=expected['data_document'])
        assert canonical_hash(wb.document_result(data['id'],expected['data_job']))==expected['data_result_sha256']
        preview=wb.document_source_preview(data['id'])
        # Source preview must be resolved from the saved Data owner, not the
        # original registered inputs removed by the parent process.
        assert preview is not None
        for entry in expected['evaluations']:
            doc=wb.document_open(kind='simulation',document_id=entry['document'])
            result=wb.document_result(doc['id'],entry['job'])
            assert canonical_hash(result)==entry['result_sha256']
            assert doc['draft']['settings']['selection']==entry['selection']
            selection=entry['selection']
            assert select_result(result,job_id=entry['job'],plane_id=selection['plane_id'],
                                 cycle=selection['cycle'],source_row=selection['source_row'])==selection
            assert result['source_bundle']['source_result_sha256']==expected['source_ref']['result_sha256']
        # Invalid edit/save/reopen works. Evaluation is blocked before creating a
        # job; explicit repair/save keeps the old result immutable.
        last=expected['evaluations'][-1];doc=wb.document_read(last['document'])
        valid=deepcopy(doc['draft']);invalid=deepcopy(valid);invalid['settings']['calibration']['E']='1e'
        doc=command(wb,doc,'simulation.update',{'draft':invalid})['document']
        doc=command(wb,doc,'document.save')['document']
        assert doc['draft']['settings']['calibration']['E']=='1e'
        try:command(wb,doc,'simulation.evaluate')
        except ValueError:pass
        else:raise AssertionError('Invalid 1e draft evaluated')
        assert len(wb.manager.list())==0
        stale=deepcopy(doc)
        doc=command(wb,doc,'simulation.update',{'draft':valid})['document']
        try:command(wb,stale,'simulation.update',{'draft':invalid})
        except ValueError:pass
        else:raise AssertionError('Stale generation overwrote current edit')
        command(wb,doc,'document.save')
        assert canonical_hash(wb.document_result(doc['id'],last['job']))==last['result_sha256']
        assert len(wb.manager.list())==0
        return {'status':'PASS','cold_process_pid':os.getpid(),'cold_jobs_created':0,
                'original_inputs_present':(wb.root/'inputs').exists(),
                'original_csv_required':False,'original_solver_runtime_required':False,
                'retained_data_preview':'READ','saved_result_hashes':'IDENTICAL',
                'selection':'IDENTICAL','invalid_draft_save':'PASS','invalid_run_blocked':'PASS',
                'stale_CAS_blocked':'PASS','explicit_repair_save':'PASS'}
    finally:
        assert wb.shutdown()['joined']


def run(output):
    output=Path(output).absolute();output.mkdir(parents=True,exist_ok=False)
    source=output/'public-synthetic-tensor.csv';source.write_bytes(csv_bytes())
    workspace=output/'original-workspace';wb=Workbench(workspace)
    expected={'evaluations':[]}
    try:
        upload=wb.upload(source.name,source.read_bytes())
        data=wb.document_open(kind='data',draft=data_draft(upload['id']),title='공개 합성 tensor')
        imported=command(wb,data,'data.import');wait(wb,imported['job'])
        data=command(wb,wb.document_read(data['id']),'document.save')['document']
        ref=wb.document_result_reference(data['id'],imported['job']['id'])
        expected.update(data_document=data['id'],data_job=imported['job']['id'],source_ref=ref,
                        data_result_sha256=canonical_hash(wb.document_result(data['id'],imported['job']['id'])))
        for method,mean in [('STRAIN_LIFE','NONE'),('STRAIN_LIFE','SWT'),('CP_SWT','SWT')]:
            s=settings(ref,method=method,mean_stress=mean)
            doc=wb.document_open(kind='simulation',title=method+'/'+mean,
                                 draft={'backend':'damage.rainflow','settings':s})
            submitted=command(wb,doc,'simulation.evaluate');wait(wb,submitted['job'])
            job=submitted['job']['id'];result=wb.document_result(doc['id'],job)
            damage=result['responses']['miner_damage']['value']
            assert abs(damage-.002)/.002<=2e-9,damage
            assert abs(result['responses']['repeating_blocks_to_D1']['value']-500)/500<=2e-9
            p=next(p for p in result['planes'] if p['plane_id']==result['display_plane_id'])
            first=p['cycles'][0]
            selection=select_result(result,job_id=job,plane_id=p['plane_id'],cycle=first['cycle'],
                                    source_row=first['member_source_rows'][0])
            doc=wb.document_read(doc['id']);draft=deepcopy(doc['draft']);draft['settings']['selection']=selection
            count=len(wb.manager.list())
            doc=command(wb,doc,'simulation.update',{'draft':draft})['document']
            doc=command(wb,doc,'document.save')['document']
            assert len(wb.manager.list())==count
            assert canonical_hash(wb.document_result(doc['id'],job))==selection['result_sha256']
            expected['evaluations'].append({'method':method,'mean_stress':mean,'document':doc['id'],
                'job':job,'result_sha256':selection['result_sha256'],'selection':selection,
                'damage':damage,'expected_damage':.002,'relative_tolerance':2e-9,
                'repeating_blocks':result['responses']['repeating_blocks_to_D1']['value'],
                'planes':len(result['planes']),'cycle_records':len(p['cycles']),
                'physical_time_s':p['history']['time_s']})
        expected['jobs_submitted']=len(wb.manager.list())
        assert expected['jobs_submitted']==4
    finally:
        assert wb.shutdown()['joined']
    copy=output/'retained-copy';shutil.copytree(workspace,copy)
    # Deliberately delete original sources, job outputs and registered bytes.
    shutil.rmtree(workspace);source.unlink()
    for name in ('inputs','jobs'):
        shutil.rmtree(copy/'workbench'/name,ignore_errors=True)
    manifest=output/'expected.json';manifest.write_text(json.dumps(expected,ensure_ascii=False,indent=2),encoding='utf-8')
    child=None
    with (output/'cold.stdout.txt').open('w',encoding='utf-8') as stdout, (output/'cold.stderr.txt').open('w',encoding='utf-8') as stderr:
        try:
            child=subprocess.Popen([sys.executable,str(Path(__file__).resolve()),'--cold',str(copy),'--expected',str(manifest)],
                                   cwd=ROOT,stdout=stdout,stderr=stderr)
            status=child.wait(timeout=120)
            if status:raise RuntimeError('Cold process failed: '+(output/'cold.stderr.txt').read_text())
        finally:
            if child is not None and child.poll() is None:
                child.terminate()
                try:child.wait(timeout=5)
                except subprocess.TimeoutExpired:child.kill();child.wait(timeout=5)
    result={'status':'PASS','parent_pid':os.getpid(),'jobs_submitted':expected['jobs_submitted'],
            'data_import_jobs':1,'fatigue_calculation_jobs':3,'solver_calls':0,'provider_calls':0,
            'cold':json.loads((output/'cold.stdout.txt').read_text()),
            'comparisons':expected['evaluations'],'windows_qt':'NOT_RUN','engineering_qualification':'UNKNOWN'}
    (output/'RUN_RESULT.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output');parser.add_argument('--cold');parser.add_argument('--expected')
    args=parser.parse_args()
    if args.cold:
        value=cold(Path(args.cold),json.loads(Path(args.expected).read_text(encoding='utf-8')))
    elif args.output:value=run(args.output)
    else:parser.error('--output or --cold is required')
    print(json.dumps(value,ensure_ascii=False,indent=2))
