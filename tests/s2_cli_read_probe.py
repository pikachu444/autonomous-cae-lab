"""Actual CLI -> existing HTTP -> exact saved Numerical owner; zero FE calls."""
from pathlib import Path
import json,subprocess,sys
from examples.s1_windows_transfer import local_service
from caelab import evaluation,p1_temperature_transfer
from caelab.adapters.scikit_fem_spatial import _Spatial
from caelab.storage import canonical_hash


def main(path):
    record=json.loads(Path(path).read_text(encoding='utf-8'));calls=[]
    def forbidden(*a,**kw):calls.append('FORBIDDEN');raise AssertionError('CLI reader started a solve')
    evaluation.run=forbidden;_Spatial.run=forbidden;_Spatial.run_adjoint=forbidden;p1_temperature_transfer.map_temperature=forbidden
    with local_service(record['workspace']) as (wb,client):
        doc=client.document_open(kind='numerical',document_id=record['document_id'])
        result=client.document_result(doc['id'],record['job_id']);assert canonical_hash(result)==record['result_hash']
        candidate=result['candidates'][0]['candidate_id'];items=[]
        query={'responses':[],'include_settings':True}
        if record['case']=='mdo':query={'transfer':{'id':'TtoU','iteration':5,'start':0,'count':3}}
        expected=client.numerical_evaluation_result(doc['id'],record['job_id'],candidate,evaluation_index=0,selection=query)
        args=[sys.executable,'-c','from caelab.cli import main; raise SystemExit(main())','documents','candidate',doc['id'],record['job_id'],candidate,
            '--url',client.url,'--evaluation-index','0','--selection',json.dumps(query)]
        process=None
        try:
            process=subprocess.Popen(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
            stdout,stderr=process.communicate(timeout=40)
            assert process.returncode==0,stderr
            actual=json.loads(stdout);assert canonical_hash(actual)==canonical_hash(expected)
            items.append({'selection':query,'response_sha256':canonical_hash(actual)})
        finally:
            if process is not None:
                if process.poll() is None:process.kill()
                process.wait(timeout=10)
                if process.stdout:process.stdout.close()
                if process.stderr:process.stderr.close()
        assert not calls
        print(json.dumps({'CLI':'PASS','case':record['case'],'owner_document':doc['id'],
            'job':record['job_id'],'saved_reads':items,'calculation_calls':len(calls),'process_reaped':process.returncode is not None},ensure_ascii=False))


if __name__=='__main__':main(sys.argv[1])
