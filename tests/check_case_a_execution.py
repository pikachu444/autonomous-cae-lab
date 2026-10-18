"""Run each approved Case A input once through existing owners/JobManager."""
import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import sys
import threading
import time
import uuid
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from apps.lab.service import LabService
from apps.lab.server import LabHTTPServer
from caelab.workbench_client import Client
from caelab.native_inputs import register_frozen_input
from caelab.storage import canonical_hash,save_json
from caelab.adapters.contact_fem import validate_snapshot

TERMINAL={'SUCCEEDED','FAILED','REJECTED','CANCELLED','INTERRUPTED'}


def command(client,doc,op):
    return client.document_command(doc['id'],op,{},session_id=doc['session_id'],
        expected_generation=doc['generation'],command_id='C'+uuid.uuid4().hex)


def finish(client,job):
    deadline=time.monotonic()+210
    while job['state'] not in TERMINAL:
        if time.monotonic()>deadline:raise TimeoutError('Confirmed terminal not received; no retry or inferred cancel')
        time.sleep(.1);job=client.status(job['id'])
    return job


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--packet',type=Path,required=True);parser.add_argument('--packet-sha256',required=True)
    parser.add_argument('--author',type=Path,required=True);parser.add_argument('--ccx',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--resume',type=Path)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    harness=Path(__file__).read_bytes();(args.output/'executed-harness.py').write_bytes(harness)
    packet=json.loads(args.packet.read_text(encoding='utf-8'))
    assert canonical_hash(packet)==args.packet_sha256
    for path,pin in packet['source_sha256'].items():assert hashlib.sha256((ROOT/path).read_bytes()).hexdigest()==pin,path
    assert hashlib.sha256(args.ccx.read_bytes()).hexdigest()==packet['ccx_executable_sha256']
    author=json.loads((args.author/'author.json').read_text(encoding='utf-8'))
    assert author['status']=='PASS' and author['solver_calls']==0
    snapshots={r['name']:Path(r['frozen']) for r in author['cases']}
    captured={}
    for case in packet['cases']:
        _,model,_,_=validate_snapshot(snapshots[case['name']])
        assert [r['node_ids'] for r in model['elements']]==packet['CCX_authored_mesh']['cells_C3D10_1_based']
        assert [r['position_mm'] for r in model['nodes']]==packet['CCX_authored_mesh']['points_mm']
        assert model['step']['geometry']=='linear' and len(model['analysis_steps']['steps'])==3
        captured[case['name']]=canonical_hash(model)
    os.environ['PATH']=str(args.ccx.resolve().parent)+os.pathsep+os.environ.get('PATH','')
    os.environ.update(OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1')
    prior=json.loads((args.resume/'execution.json').read_text(encoding='utf-8')) if args.resume else None
    store=args.resume/'store' if args.resume else args.output/'store'
    service=LabService(store);server=LabHTTPServer(service,0)
    thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.02},daemon=True);thread.start()
    client=Client(f'http://127.0.0.1:{server.server_port}')
    report=dict(status='RUNNING',packet_sha256=args.packet_sha256,cases=[],jobs_before=0,
        maximum_jobs=9,captured_model_sha256=captured,engineering_release='UNKNOWN/NOT_RELEASED')
    if prior:
        assert prior['packet_sha256']==args.packet_sha256
        report['cases']=[deepcopy(c) for c in prior['cases'] if c.get('result_sha256')]
        report['preserved_pre_native_failures']=[deepcopy(c) for c in prior['cases'] if not c.get('result_sha256')]
        report['original_execution']=str(args.resume.resolve())
        report['store']=str(store.resolve())
        report['original_owner_job_limit']=9
        report['maximum_jobs']=10
        report['budget']=dict(maximum_physical_evaluations=9,preserved_pre_native_dispatch_failures=1,
                              maximum_owner_jobs=10,additional_fit_provider=0)
    report['harness_sha256']=hashlib.sha256(harness).hexdigest()
    save_json(args.output/'execution.json',report)
    try:
        report['jobs_before']=len(client.request('/api/workbench')['jobs'])
        assert report['jobs_before']==(3 if prior else 0)
        if prior:
            assert len(report['cases'])==2 and len(report['preserved_pre_native_failures'])==1
            failed=client.status(report['preserved_pre_native_failures'][0]['job_id'])
            assert failed['state']=='FAILED' and failed['operation']=='evaluate'
            assert failed['error']['message']=='Choose a supported simulation backend and an editable settings object'
            report['preserved_pre_native_failures'][0].update(terminal=failed)
            for old in report['cases']:
                doc=client.document_open(kind='simulation' if old['name'].endswith('_DP_FE') else 'material',
                    document_id=old['document_id'])
                assert canonical_hash(client.document_result(doc['id'],old['job_id']))==old['result_sha256']
        for case in packet['cases']:
            for kind,backend,settings in (
                ('simulation','structure.felupe.law_native',case['DP_FE_settings']),
                ('material','material.law_native',case['J2_point_settings'])):
                label=case['name']+('_DP_FE' if kind=='simulation' else '_J2_reduction_point')
                if any(c['name']==label for c in report['cases']):continue
                doc=client.document_open(kind=kind,title=label,draft=dict(backend=backend,settings=settings))
                assert doc['draft']['settings']==settings
                reply=command(client,doc,kind+'.evaluate');job=reply['job']
                report['cases'].append(dict(name=label,document_id=doc['id'],job_id=job['id'],
                    submitted_settings_sha256=canonical_hash(settings),initial_state_sha256=canonical_hash(
                        settings['law']['initial_state'] if kind=='simulation' else settings['initial_state'])))
                save_json(args.output/'execution.json',report)
                terminal=finish(client,job);result=client.document_result(doc['id'],job['id'])
                doc=client.document_read(doc['id']);saved=command(client,doc,'document.save')['document']
                report['cases'][-1].update(state=terminal['state'],execution_status=result['execution_status'],
                    result_sha256=canonical_hash(result),saved_revision=saved['saved_revision'],
                    input_revision=saved['input_revision'],input_sha256=canonical_hash(saved['draft']))
                save_json(args.output/'execution.json',report)
                print(label,terminal['state'],flush=True)
            source=snapshots[case['name']];data_id='D'+uuid.uuid4().hex
            registered=register_frozen_input(server.workbench.root,source.parent,source,data_id,
                root_id='CaseAExplicitAuthored',relative='snapshot.json',limit=64*1024**2)
            job=client.submit('run',dict(backend='structure.calculix.contact',settings=dict(data_id=data_id)),
                              request_id='CaseA'+uuid.uuid4().hex)
            report['cases'].append(dict(name=case['name']+'_CCX_J2',job_id=job['id'],
                data_id=data_id,frozen_sha256=registered['sha256'],snapshot=str(source)))
            save_json(args.output/'execution.json',report)
            terminal=finish(client,job);result=client.result(job['id'])
            report['cases'][-1].update(state=terminal['state'],execution_status=result['execution_status'],
                result_sha256=canonical_hash(result))
            save_json(args.output/'execution.json',report)
            print(case['name']+'_CCX_J2',terminal['state'],flush=True)
        jobs=client.request('/api/workbench')['jobs'];assert len(jobs)==(10 if prior else 9)
        report.update(status='COMPLETED',jobs_after=len(jobs),new_jobs=len(jobs),
            successful=sum(c['execution_status']=='SUCCEEDED' for c in report['cases']),
            failed=[c['name'] for c in report['cases'] if c['execution_status']!='SUCCEEDED'])
        assert all(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==pin for p,pin in packet['source_sha256'].items())
        assert Path(__file__).read_bytes()==harness
        save_json(args.output/'execution.json',report)
    finally:
        server.shutdown();server.server_close();service.shutdown();thread.join(5)


if __name__=='__main__':main()
