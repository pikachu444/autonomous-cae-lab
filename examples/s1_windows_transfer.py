"""Actual S1 public calculation, saved owner and independent-process cold read.

Run from the repository root: python -m examples.s1_windows_transfer --workspace "S1 결과" --case uniform
No controlled adapter or synthetic field is injected. Missing OSS is a retained
FAILED run, not a fallback, synthetic success, installation or transient solver.
"""
from contextlib import contextmanager
from copy import deepcopy
import argparse
import json
from pathlib import Path
import subprocess
import sys
import threading
import time

from caelab import scikit_fem_models as domain
from caelab import p1_temperature_transfer as transfer
from caelab.evaluation_definition import default_draft, document_reference
from caelab.storage import canonical_hash
from caelab.jobs import TERMINAL


@contextmanager
def local_service(workspace):
    from apps.lab.server import LabHTTPServer
    from apps.lab.service import LabService
    from caelab.workbench_client import Client
    server = LabHTTPServer(LabService(Path(workspace)), 0)
    thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .02}, daemon=True)
    thread.start()
    try:
        yield server.workbench, Client('http://127.0.0.1:' + str(server.server_port))
    finally:
        for job in server.workbench.manager.list():
            if job['state'] not in TERMINAL:
                server.workbench.manager.cancel(job['id'])
        server.shutdown()
        try:
            terminal = server.workbench.shutdown(timeout=10)
            if not terminal['joined']:
                raise RuntimeError('Owned calculation cleanup is not confirmed; inspect its job/cleanup state.')
        finally:
            server.server_close(); thread.join(5)
        if thread.is_alive():
            raise RuntimeError('Owned HTTP thread did not terminate')


def command(client, document, operation, arguments=None):
    return client.document_command(document['id'], operation, arguments or {}, session_id=document['session_id'],
                                   expected_generation=document['generation'])


def declarations(case):
    heat = domain.default_settings(domain.THERMAL)
    heat['mesh']['cells'] = [2, 2]  # 9 DOFs, one free interior DOF: actual sparse solve, not boundary-only lookup.
    heat['time'] = {'value': 0., 'unit': 's', 'origin': 'public_s1_physical_snapshots'}
    structure = domain.default_settings(domain.STRUCTURAL)
    structure['mesh']['cells'] = [3, 2]
    structure['time'] = deepcopy(heat['time'])
    models = [('Start', '공급 온도 0초', domain.THERMAL, heat)]
    policy = transfer.default_options('Start', receiver_time=structure['time'])
    if case == 'affine':
        heat['boundary_temperature']['value'] = 300.
        heat['boundary_gradient']['values'] = [4., -2.]
        end = deepcopy(heat)
        end['mesh']['cells'] = [4, 2]
        end['time']['value'] = 2.
        end['boundary_temperature']['value'] = 310.
        models.append(('End', '공급 온도 2초', domain.THERMAL, end))
        structure['time']['value'] = 1.
        structure['validation']['free_expansion_max_error'] = None  # Explicitly not the UNIFORM benchmark.
        policy['time'].update(mode='linear', receiver=deepcopy(structure['time']),
                              sources=[{'stage':'Start','output':'temperature'},{'stage':'End','output':'temperature'}])
    models.append(('Structure', '다른 P1 메시의 열변형', domain.STRUCTURAL, structure))
    return models, policy


def calculate(workspace, case, deadline_seconds):
    workspace = Path(workspace).resolve()
    with local_service(workspace) as (wb, client):
        jobs_before = len(wb.manager.list())
        models, policy = declarations(case)
        sources = []
        for identifier, title, backend, settings in models:
            doc = client.document_open(kind='simulation', title=title, draft={'backend':backend,'settings':settings})
            if doc['diagnostics']: raise ValueError(doc['diagnostics'])
            saved = command(client, doc, 'document.save')['document']
            sources.append({'id':identifier,'name':title,'source':document_reference(saved)})
        draft = default_draft(); draft['stages'] = sources
        draft['transfers'] = [{'id':'TtoU','from_stage':'Start','output':'temperature','to_stage':'Structure',
                              'input':'temperature','mapping':transfer.MAPPING,'lag':0,'options':policy}]
        draft['responses'] = [{'id':'displacement','stage':'Structure','response':'displacement','unit':'m'},
                              {'id':'stress','stage':'Structure','response':'stress','unit':'Pa'}]
        doc = client.document_open(kind='evaluation', title='S1 '+case+' 실제 공간 전달', draft=draft)
        inspection = client.evaluation_inspect(doc['id'])
        if inspection['diagnostics']: raise ValueError(inspection['diagnostics'])
        if len(wb.manager.list()) != jobs_before: raise AssertionError('Draft creation/Check unexpectedly created a calculation')
        job = command(client, doc, 'evaluation.run')['job']['id']
        deadline = time.monotonic() + deadline_seconds
        while client.status(job)['state'] not in TERMINAL:
            if time.monotonic() >= deadline:
                client.cancel(job)
                raise TimeoutError('Explicit public-example deadline exceeded; owned job cancellation requested')
            time.sleep(.05)
        result = client.document_result(doc['id'], job)
        catalog = client.evaluation_transfer(doc['id'], job)
        mapped = client.evaluation_transfer(doc['id'], job, 'TtoU', 0) if catalog['transfers'] else None
        stages = []
        for attempt in result['stages']:
            if attempt.get('result_sha256'):
                saved = client.evaluation_stage_result(doc['id'], job, attempt['attempt_id'])
                stages.append({'attempt_id':attempt['attempt_id'], 'stage_id':attempt['stage_id'],
                    'backend':saved['backend'],'execution_status':saved['execution_status'],
                    'checks':saved['checks'],'diagnostics':saved['diagnostics'],
                    'post_inputs':saved.get('post_inputs',[]), 'result_sha256':canonical_hash(saved)})
        checks = {'physics':'NOT_RUN_OR_FAILED', 'native_ParaView':'NOT_RUN', 'qualification':'UNKNOWN'}
        if result['execution_status'] == 'SUCCEEDED':
            import numpy as np
            if not mapped or not mapped['exact_values_match']:
                raise AssertionError('Retained receiver input differs from mapped field')
            expected = [323.15 if case=='uniform' else 305+4*r['coordinates'][0]-2*r['coordinates'][1] for r in mapped['rows']]
            error = max(abs(row['mapped']-v) for row,v in zip(mapped['rows'],expected))
            if error > 1e-10: raise AssertionError('Independent analytic temperature error exceeds 1e-10 K')
            if not mapped['original_source_and_receiver_are_different_meshes']:
                raise AssertionError('The actual retained meshes are not different')
            last = client.evaluation_stage_result(doc['id'],job,result['stages'][-1]['attempt_id'])
            if {row['response'] for row in last.get('post_inputs',[])} != {'temperature','displacement','stress'}:
                raise AssertionError('Exact temperature/displacement/stress Post set was not registered')
            if case=='uniform':
                field=last['responses']['displacement'];xy=np.asarray(field['coordinates'])
                e=float(np.max(np.linalg.norm(np.asarray(field['value'])-23e-6*30.*xy,axis=1)))
                if e>1e-10:raise AssertionError('Original free-expansion tolerance failed')
                checks['free_expansion_error_m']=e
            checks.update(physics='EXECUTED',temperature_max_error_K=error,
                          thermal_sparse_solves=sum(s['diagnostics'].get('assembly',{}).get('linear_solve_calls',0) for s in stages if s['stage_id']!='Structure'))
        doc=command(client,client.document_read(doc['id']),'document.save')['document']
        record={'schema':'public-s1-execution-v1','case':case,'workspace':str(workspace),
                'document_id':doc['id'],'job_id':job,'saved_revision':doc['saved_revision'],
                'execution_status':result['execution_status'],'result_sha256':canonical_hash(result),
                'draft_sha256':canonical_hash(doc['draft']),'transfer_sha256':canonical_hash(mapped),
                'has_transfer':mapped is not None,'stages':stages,'checks':checks,
                'platform':sys.platform,'python':sys.version,'paid_calls':0,
                'scope':'S1 only; recorded steady snapshots are NOT a transient solver; S2 not implemented'}
        destination=workspace/('s1-'+case+'-'+job+'.json')
        destination.write_text(json.dumps(record,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
        return destination,record


def reopen(record_path):
    """Run in a NEW interpreter. No skfem/SciPy import, mapping or evaluator call."""
    import builtins
    from caelab.workbench import Workbench
    from caelab.adapters.scikit_fem_spatial import _Spatial
    from caelab import evaluation
    expected=json.loads(Path(record_path).read_text(encoding='utf-8'))
    calls=[]
    def forbidden(*args,**kwargs):
        calls.append('FORBIDDEN');raise AssertionError('Cold read attempted a calculation/mapping')
    _Spatial.run=forbidden;transfer.map_temperature=forbidden;evaluation.run=forbidden;evaluation.evaluate=forbidden
    original=builtins.__import__
    def guard(name,*args,**kwargs):
        if name.split('.')[0] in {'skfem','scipy','dolfinx','petsc4py'}:
            raise AssertionError('Cold read imported a solver dependency')
        return original(name,*args,**kwargs)
    builtins.__import__=guard
    wb=Workbench(Path(expected['workspace']))
    try:
        doc=wb.document_open(kind='evaluation',document_id=expected['document_id'])
        result=wb.document_result(doc['id'],expected['job_id'])
        assert canonical_hash(doc['draft'])==expected['draft_sha256']
        assert canonical_hash(result)==expected['result_sha256']
        if expected['has_transfer']:
            mapped=wb.evaluation_transfer(doc['id'],expected['job_id'],'TtoU',0)
            assert canonical_hash(mapped)==expected['transfer_sha256']
        for row in expected['stages']:
            stage=wb.evaluation_stage_result(doc['id'],expected['job_id'],row['attempt_id'])
            assert canonical_hash(stage)==row['result_sha256']
            for post in stage.get('post_inputs',[]):
                wb.native_input(post['id'])
        assert not calls
        return {'cold_read':'PASS','new_process':True,'solve_calls':0,'mapping_calls':0,
                'original_execution_status':expected['execution_status']}
    finally:
        builtins.__import__=original
        if not wb.shutdown()['joined']:raise RuntimeError('New owner did not terminate')


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace',type=Path)
    parser.add_argument('--case',choices=('uniform','affine'),default='uniform')
    parser.add_argument('--deadline-seconds',type=float,default=180.)
    parser.add_argument('--reopen',type=Path)
    args=parser.parse_args(argv)
    if args.reopen:
        print(json.dumps(reopen(args.reopen),ensure_ascii=False));return 0
    if args.workspace is None or args.deadline_seconds<=0:
        parser.error('Use --workspace and a positive explicit --deadline-seconds')
    path,record=calculate(args.workspace,args.case,args.deadline_seconds)
    process=None
    try:
        process=subprocess.Popen([sys.executable,'-m','examples.s1_windows_transfer','--reopen',str(path)],
                                  stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        stdout,stderr=process.communicate(timeout=45)
        if process.returncode:
            raise RuntimeError('Cold-read process failed; original result retained at '+str(path)+'\n'+stderr)
        print(json.dumps({'record':str(path),'execution_status':record['execution_status'],
                          'checks':record['checks'],'cold_read':json.loads(stdout)},ensure_ascii=False,indent=2))
        return 0 if record['execution_status']=='SUCCEEDED' else 2
    finally:
        if process is not None:
            if process.poll() is None:process.kill()
            process.wait(timeout=5)
            if process.stdout:process.stdout.close()
            if process.stderr:process.stderr.close()


if __name__=='__main__':
    raise SystemExit(main())
