"""Use the exact supplied Windows RED originals, never alter or regenerate them.

Set C2_PUBLIC_PACKET to the extracted source packet root. This is an optional
external-fixture test when that request packet is not available to a checkout.
"""
from pathlib import Path
import os
import shutil
import pytest
from caelab.workbench import Workbench
from caelab.storage import load_json
from caelab.evaluation import file_hash
from _portable_connection_c2_support import copied,run_cold,evidence_hashes


@pytest.mark.parametrize('case',['pending_evidence','data_bound_frozen_input','detail_attempt_identity'])
def test_supplied_windows_originals_cold_no_store(tmp_path,case):
    configured=os.environ.get('C2_PUBLIC_PACKET')
    if not configured:pytest.skip('C2_PUBLIC_PACKET exact supplied fixture not configured')
    base=Path(configured)/'evidence/portable-c2-repro'/case
    source=base/'원본 보존 연결 해제'
    before={p.relative_to(source).as_posix():file_hash(p) for p in source.rglob('*') if p.is_file()}
    local=tmp_path/'원본 보관소';shutil.copytree(source,local)
    row=load_json(base/'result.json');request=load_json(base/'cold-request.json')
    request.update(document_id=row['original_document_id'],result_hash=row['original_result_hash'])
    wb=Workbench(local)
    try:
        chosen=load_json(base/'inspection.json')['selections']
        request['evidence_hashes']=evidence_hashes(wb,request['document_id'])
        copied(wb,chosen,tmp_path/'before move')
    finally:wb.shutdown()
    local.rename(tmp_path/'원본은 보존하며 연결만 해제')
    target=tmp_path/'한글 공백 cold 사본';(tmp_path/'before move').rename(target)
    result=run_cold(target,request,tmp_path/'cold',adopt=False)
    assert result['status']=='PASSED' and result['jobs_on_reopen']==0
    assert result['evaluator_and_dispatch_calls']==[]
    assert not local.exists()
    assert before=={p.relative_to(source).as_posix():file_hash(p) for p in source.rglob('*') if p.is_file()}
