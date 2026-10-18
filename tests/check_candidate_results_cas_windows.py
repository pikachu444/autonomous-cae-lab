"""No-evaluation metadata CAS fixture, distinct from historical fit adoption."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import shutil
import sys
import threading
import uuid
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from apps.lab.service import LabService
from apps.lab.server import LabHTTPServer
from caelab.workbench_client import Client,WorkbenchHTTPError
from caelab.storage import canonical_hash


def command(client,doc,operation,arguments=None):
    return client.document_command(doc['id'],operation,arguments or {},session_id=doc['session_id'],
        expected_generation=doc['generation'],command_id='C'+uuid.uuid4().hex)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    checkpoint=json.loads((args.case/'checkpoint.json').read_text(encoding='utf-8'))
    store=args.output/'store';shutil.copytree(args.case/'store',store)
    service=LabService(store);server=LabHTTPServer(service,0)
    thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.02},daemon=True);thread.start()
    first=Client(f'http://127.0.0.1:{server.server_port}');second=Client(first.url)
    try:
        jobs=first.request('/api/workbench')['jobs']
        plan=first.document_open(kind='numerical',document_id=checkpoint['plan_id'])
        original_material=first.document_open(kind='material',document_id=checkpoint['material_id'])
        run=next(r for r in plan['runs'] if r['job_id']==checkpoint['fit_job'])
        frozen=deepcopy(run['draft']['material']['draft'])
        fixture=first.document_open(kind='material',title='동일 계수 CAS 메타데이터 반례',draft=frozen)
        # A second view changes only unit metadata, then Undo restores exact
        # coefficients AND the full draft. It still creates a new owner revision.
        temporary=deepcopy(frozen);temporary['settings']['stress_unit']='kPa'
        changed=command(second,fixture,'material.update',{'draft':temporary})['document']
        restored=command(second,changed,'document.undo')['document']
        assert restored['draft']==fixture['draft'] and restored['generation']!=fixture['generation']
        try:
            command(first,fixture,'material.update',{'draft':deepcopy(restored['draft'])})
            raise AssertionError('Stale generation was admitted')
        except WorkbenchHTTPError as error:
            assert error.code==400;metadata_refusal=error.service_message
        assert first.document_read(fixture['id'])==restored
        # Original candidate evidence still targets its ORIGINAL Material. Do
        # not rebind it to the metadata fixture to manufacture an adoption.
        reference=checkpoint['evidence'][0]
        try:
            first.numerical_evidence_adopt(plan['id'],checkpoint['fit_job'],'C000010',reference,
                target_document_id=original_material['id'],target_kind='material',
                session_id=original_material['session_id'],expected_generation=original_material['generation'],
                command_id='C'+uuid.uuid4().hex)
            raise AssertionError('Historical changed target must remain blocked')
        except WorkbenchHTTPError as error:
            assert error.code==400;historical_refusal=error.service_message
            assert 'changed after this Plan was bound' in historical_refusal
        assert first.document_read(original_material['id'])==original_material
        assert canonical_hash(first.document_result(plan['id'],checkpoint['fit_job']))==checkpoint['fit_hash']
        assert first.request('/api/workbench')['jobs']==jobs
        result=dict(status='PASS',metadata_fixture=dict(document_id=fixture['id'],before_generation=fixture['generation'],
            after_generation=restored['generation'],same_full_draft=True,same_coefficients=True,
            expected_input_revision=fixture['input_revision'],current_input_revision=restored['input_revision'],
            draft_hash=canonical_hash(restored['draft']),HTTP_status=400,diagnostic=metadata_refusal,
            claim='Two clients on one Core owner; stale metadata command CAS, not a new successful candidate adoption'),
            historical_candidate=dict(document_id=plan['id'],candidate_id='C000010',HTTP_status=400,
                diagnostic=historical_refusal,original_target_unchanged=True),jobs_before=len(jobs),jobs_after=len(jobs),new_jobs=0)
        (args.output/'cas.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(result,ensure_ascii=False))
    finally:
        server.shutdown();server.server_close();service.shutdown();thread.join(5)


if __name__=='__main__':main()
