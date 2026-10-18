"""Explicit fixed P0/P1 through Simulation/JobManager, never a campaign."""
from pathlib import Path
import json
import os
import sys
import time
import pytest
from caelab.storage import canonical_hash,save_json
from caelab.evaluation import file_hash,read_result
from caelab.impact_model import BACKEND,validate_settings
from caelab.workbench import Workbench
from caelab.execution_control import run_owned_command
from caelab.adapters.impact import ImpactAdapter

REPO=Path(__file__).resolve().parents[1]
SETTINGS_SHA='afa230cd56ae31f95588af20768a49e27fdab08a568b69ffa98da4b4ec727d7b'
P1_SETTINGS_SHA='66b6ba64dd262708eb3c54c37dd0ecfb2434f761c01b69ad1a641290301f24bb'


@pytest.mark.skipif(os.environ.get('CAELAB_RUN_RECLOSURE_P0')!='1',reason='Explicit assigned P0 only')
def test_declared_p0_owner_native_save_and_cold():
    _run_declared(SETTINGS_SHA,1.e-5,'삭제 연동 초기 실행 확인')


@pytest.mark.skipif(os.environ.get('CAELAB_RUN_RECLOSURE_P1')!='1',reason='Explicit assigned fixed P1 only')
def test_declared_p1_owner_native_save_and_cold():
    _run_declared(P1_SETTINGS_SHA,.004,'완전 삭제 후 압축 재개구')


def _run_declared(settings_sha,end_time,title):
    declared=Path(os.environ['CAELAB_RECLOSURE_DECLARATION_ROOT']).resolve()
    settings_path=declared/'settings.json'
    assert file_hash(settings_path)==settings_sha
    settings=json.loads(settings_path.read_text(encoding='utf-8'));validate_settings(settings)
    assert settings['motions']==[] and settings['cohesive'][0]['normal_strength_mpa']==2.
    assert settings['time']['scale']==.9 and settings['time']['end_s']==end_time
    policy=json.loads((declared/'policy.json').read_text(encoding='utf-8'))
    declaration=json.loads((declared/'declaration.json').read_text(encoding='utf-8'))
    output=Path(os.environ['CAELAB_RECLOSURE_RUN_ROOT']).resolve()
    output.mkdir(parents=True,exist_ok=False)
    save_json(output/'declared-settings.json',settings)
    save_json(output/'declared-policy.json',policy)
    sources={str(Path(p).resolve().relative_to(REPO)):file_hash(p) for p in ImpactAdapter.input_source_files}
    assert 'caelab/impact_reclosure_policy.py' in {p.replace('\\','/') for p in sources}
    if (declared/'source-sha256.json').is_file():
        assert sources==json.loads((declared/'source-sha256.json').read_text(encoding='utf-8'))
    save_json(output/'source-sha256.json',sources)
    for relative in sources:
        target=output/'source-snapshot'/relative;target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes((REPO/relative).read_bytes())
    wb=Workbench(output/'store',configuration={'workers':1});actual=None
    try:
        doc=wb.document_open(kind='simulation',title=title,
            draft={'backend':BACKEND,'settings':settings})
        def command(operation):
            nonlocal doc
            receipt=wb.document_command(doc['id'],operation,{},session_id=doc['session_id'],
                expected_generation=doc['generation'])
            doc=receipt.get('document',doc);return receipt
        command('document.save');job=command('simulation.evaluate')['job']
        deadline=time.monotonic()+180
        while time.monotonic()<deadline:
            job=wb.manager.status(job['id'])
            if job['state'] in {'SUCCEEDED','FAILED','CANCELLED','INTERRUPTED','PARTIAL_FAILURE'}:break
            time.sleep(.05)
        save_json(output/'job.json',job)
        calculation=wb.root/'results'/job['id']/'calculation'
        if (calculation/'result.json').is_file():
            actual=read_result(calculation,verify='all');save_json(output/'observed-result.json',actual)
        command('document.save')
        record={'document_id':doc['id'],'job_id':job['id'],'settings_sha256':canonical_hash(settings),
            'execution_state':job['state'],'new_jobs':1,'engineering_qualification':'UNKNOWN'}
        record['reclosure_files']={path.relative_to(calculation).as_posix():file_hash(path)
            for path in calculation.rglob('*reclosure*') if path.is_file()}
        record['owned_process_receipts']={path.relative_to(calculation).as_posix():
            json.loads(path.read_text(encoding='utf-8')) for path in calculation.rglob('*.execution.json')}
        if end_time==.004:
            record['declared_deck_comparison']={key:{'expected':declaration[key],
                'actual':file_hash(calculation/'native'/name)} for key,name in (
                    ('effective_starter_sha256','impact_0000.rad'),('effective_engine_sha256','impact_0001.rad'),
                    ('callback_sha256',policy['function_name']+'.py'))}
        if actual is not None:
            retained=wb.document_result(doc['id'],job['id'])
            assert canonical_hash(retained['responses'])==canonical_hash(actual['responses'])
            record.update(responses_sha256=canonical_hash(actual['responses']),
                result_sha256=file_hash(calculation/'result.json'))
        save_json(output/'retained.json',record)
    finally:assert wb.shutdown(timeout=30)['joined']
    assert actual is not None,'Preserved failure without result; do not rerun or retune'
    child=output/'reopen.py'
    child.write_text('''from pathlib import Path
import sys,json
sys.path.insert(0,sys.argv[2])
from caelab.workbench import Workbench
from caelab.storage import canonical_hash,save_json
from caelab.evaluation import file_hash
import caelab.adapters.impact as adapter
def forbidden(*a,**k):raise AssertionError('Cold open must not probe or execute solver')
adapter.selected_runtime=forbidden;adapter.run_owned_command=forbidden
root=Path(sys.argv[1]);record=json.loads((root/'retained.json').read_text(encoding='utf-8'))
wb=Workbench(root/'store',configuration={'workers':1})
try:
 count=len(wb.manager.list());doc=wb.document_open(kind='simulation',document_id=record['document_id'])
 assert canonical_hash(doc['draft']['settings'])==record['settings_sha256']
 result=wb.document_result(doc['id'],record['job_id'])
 assert canonical_hash(result['responses'])==record['responses_sha256']
 calculation=wb.root/'results'/record['job_id']/'calculation'
 assert file_hash(calculation/'result.json')==record['result_sha256']
 for relative,digest in record['reclosure_files'].items():assert file_hash(calculation/relative)==digest
 assert len(wb.manager.list())==count
 save_json(root/'cold-reopen.json',{'status':'PASS','record':record,'new_jobs':0,'runtime_probed':False})
finally:assert wb.shutdown()['joined']
''',encoding='utf-8')
    process=run_owned_command([sys.executable,str(child),str(output),str(REPO)],output,
        'reclosure-cold-reopen',timeout=30,owned_tree=True)
    assert process.returncode==0
    assert {relative:file_hash(REPO/relative) for relative in sources}==sources
    if end_time==.004:
        assert all(row['expected']==row['actual'] for row in record['declared_deck_comparison'].values())
    assert job['state']=='SUCCEEDED',job
    # Capability/trace acceptance is assessed from original retained files, not
    # manufactured from solver exit or a sparse animation result.
