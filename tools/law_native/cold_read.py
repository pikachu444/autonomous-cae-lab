"""Fresh-process read of an existing fit/Material receipt; zero new jobs.

Run against an explicit disposable copy of the retained workspace. Existing
Material/Numerical owners and result reader are used, never a replacement store.
"""
from pathlib import Path
import argparse,sys,traceback
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from caelab.workbench import Workbench
from caelab.storage import load_json,save_json,canonical_hash
from caelab.material_fe_transfer import verify_source

def main():
    p=argparse.ArgumentParser();p.add_argument('--workspace',required=True);p.add_argument('--receipt',required=True)
    p.add_argument('--snapshot',required=True);p.add_argument('--output',required=True);a=p.parse_args()
    out=Path(a.output);out.mkdir(parents=True,exist_ok=False);wb=None;code=1
    receipt={'status':'STARTING','layer':'ACTUAL_FRESH_PROCESS_COLD_READER','platform':sys.platform,
             'compiler':'NOT_RUN','native_FE':'NOT_RUN'}
    try:
        prior=load_json(a.receipt);snapshot=load_json(a.snapshot)
        verify_source(snapshot)  # Retained text/hash only; no live-path/current-source check.
        wb=Workbench(Path(a.workspace));before=len(wb.manager.list())
        m=wb.document_open(kind='material',document_id=prior['material_id'])
        wb.document_open(kind='numerical',document_id=prior['numerical_id'])
        assert canonical_hash(m['draft'])==prior['adopted_material_sha256']
        assert canonical_hash(wb.result(prior['job_id']))==prior['result_sha256']
        after=len(wb.manager.list());assert before==after==prior['jobs']
        receipt.update(status='PASS',jobs_before=before,jobs_after=after,new_jobs=after-before,
            material_input_sha256=canonical_hash(m['draft']),result_sha256=prior['result_sha256'],
            retained_source_sha256=snapshot['snapshot_sha256'],retained_source_file_count=len(snapshot['law_source']['files']))
        code=0
    except BaseException as error:
        receipt.update(status='FAIL',error_type=type(error).__name__,error=str(error),traceback=traceback.format_exc())
        traceback.print_exc()
    finally:
        if wb is not None:
            receipt['shutdown']=wb.shutdown()
            if not receipt['shutdown']['joined']:receipt['cleanup']='UNKNOWN';code=125
        save_json(out/'receipt.json',receipt)
    return code

if __name__=='__main__':raise SystemExit(main())
