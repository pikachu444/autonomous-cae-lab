"""Read an existing DP spatial result over HTTP; never submit a calculation."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
import threading
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from apps.lab.service import LabService
from apps.lab.server import LabHTTPServer
from caelab.workbench_client import Client
from caelab.storage import canonical_hash
from caelab.law_native_fe import dp_observables


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    stage=json.loads((args.source/'stage.json').read_text(encoding='utf-8'))
    source_files=('caelab/law_native_fe.py','caelab/adapters/law_native_fe_worker.py',
        'caelab/law_native_inspection.py','tests/check_case_a_retained.py')
    pins={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in source_files}
    store=args.output/'store';shutil.copytree(args.source/'workspace',store)
    service=LabService(store);server=LabHTTPServer(service,0)
    thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.02},daemon=True);thread.start()
    client=Client(f'http://127.0.0.1:{server.server_port}')
    try:
        jobs=client.request('/api/workbench')['jobs']
        doc=client.document_open(kind='simulation',document_id=stage['document_id'])
        identifier=stage['job']['id']
        result=client.document_result(doc['id'],identifier)
        assert canonical_hash(result)==stage['result_sha256']
        diagnostics=result['diagnostics'];settings=stage['job']['arguments']['settings']['law']
        rows=[]
        for step in diagnostics['steps']:
            for ip in step['local']:
                observed=dp_observables(ip['stress'],ip['state'],settings['parameters'])
                # Independently check pressure/volume using retained physical components.
                assert abs(observed['pressure']+sum(ip['stress'][:3])/3)<1e-12
                assert observed['plastic_volume_strain']==sum(ip['state']['plastic_strain_kelvin'][:3])
                rows.append(dict(increment=step['increment'],cell_index=ip['cell_index'],
                    quadrature_index=ip['quadrature_index'],**observed))
        assert client.document_read(doc['id'])==doc
        assert client.request('/api/workbench')['jobs']==jobs
        report=dict(status='PASS',document_id=doc['id'],job_id=identifier,
            saved_revision=stage['saved_revision'],result_sha256=canonical_hash(result),
            source_files=pins,derived_from_retained=True,new_jobs=0,
            jobs_before=len(jobs),jobs_after=len(jobs),actual_ip_rows=len(rows),rows=rows,
            original_FE_limits=stage['FE_LIMITS'],
            claim='Existing actual DP spatial result; no new FE/point calculation or engineering qualification')
        (args.output/'retained.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({k:v for k,v in report.items() if k!='rows'},ensure_ascii=False))
    finally:
        server.shutdown();server.server_close();service.shutdown();thread.join(5)


if __name__=='__main__':main()
