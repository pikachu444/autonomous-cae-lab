"""Explicit two predeclared LAW117 histories through the existing owner/runtime.

No campaign, retuning, new tolerance, fatigue or constitutive qualification.
"""
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
pytestmark=pytest.mark.skipif(os.environ.get('CAELAB_RUN_INTERFACE_HISTORIES')!='1',reason='Explicit two predeclared installed-runtime loops')
EXPECTED={'normal':'9fc6f4897ba0130ef0f7bd257f3aa59f1c18d3720c130421206f724ddf7ad1e0',
          'mixed':'cc8217996c6f1539c04822da3795d36f654d7fa480f176d9d8b597b7e9738933'}


@pytest.mark.parametrize('kind',['normal','mixed'])
def test_fixed_history_native_save_and_cold_reopen(kind,tmp_path):
    if os.environ.get('CAELAB_INTERFACE_HISTORY_INPUT_ROOT'):
        declared=Path(os.environ['CAELAB_INTERFACE_HISTORY_INPUT_ROOT']).resolve()/kind/'settings.json'
    else:
        from interface_history_fixtures import declared_settings
        declared=tmp_path/'settings.json';save_json(declared,declared_settings(kind))
    assert file_hash(declared)==EXPECTED[kind],'Use the predeclared input without retuning'
    settings=json.loads(declared.read_text(encoding='utf-8'));validate_settings(settings)
    assert settings['motions']==[] and settings['contacts']==[]
    assert settings['cohesive'][0]['normal_strength_mpa']==2.
    assert settings['cohesive'][0]['shear_strength_mpa']==2.
    assert settings['time']['scale']==.9
    output=Path(os.environ['CAELAB_INTERFACE_HISTORY_RUN_ROOT']).resolve()/kind
    output.mkdir(parents=True,exist_ok=False)
    save_json(output/'declared-settings.json',settings)
    sources={str(Path(p).resolve().relative_to(REPO)):file_hash(p) for p in ImpactAdapter.input_source_files}
    save_json(output/'source-sha256.json',sources)
    for relative in sources:
        target=output/'source-snapshot'/relative;target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes((REPO/relative).read_bytes())
    wb=Workbench(output/'store',configuration={'workers':1});actual=None;audit=None
    try:
        doc=wb.document_open(kind='simulation',title='계면 반복 이력 '+kind,draft={'backend':BACKEND,'settings':settings})
        def command(operation):
            nonlocal doc
            receipt=wb.document_command(doc['id'],operation,{},session_id=doc['session_id'],expected_generation=doc['generation'])
            doc=receipt.get('document',doc);return receipt
        command('document.save');job=command('simulation.evaluate')['job']
        limit=time.monotonic()+180
        while time.monotonic()<limit:
            job=wb.manager.status(job['id'])
            if job['state'] in {'SUCCEEDED','FAILED','CANCELLED','INTERRUPTED','PARTIAL_FAILURE'}:break
            time.sleep(.05)
        save_json(output/'job.json',job)
        calculation=wb.root/'results'/job['id']/'calculation'
        if (calculation/'result.json').is_file():
            actual=read_result(calculation,verify='all');save_json(output/'observed-result.json',actual)
        if (calculation/'interface_history_observations.json').is_file():
            audit=json.loads((calculation/'interface_history_observations.json').read_text(encoding='utf-8'))
            save_json(output/'observed-history.json',audit)
        command('document.save')
        if actual is None:
            save_json(output/'retained.json',{'status':'NO_RESULT','job':job,'new_jobs':1})
            pytest.fail('Preserved native failure has no result; see job.json')
        retained=wb.document_result(doc['id'],job['id'])
        assert canonical_hash(retained['responses'])==canonical_hash(actual['responses'])
        record={'document_id':doc['id'],'job_id':job['id'],'settings_sha256':canonical_hash(settings),
            'responses_sha256':canonical_hash(actual['responses']),'result_sha256':file_hash(calculation/'result.json'),
            'history_sha256':file_hash(calculation/'interface_history_observations.json') if audit else None}
        save_json(output/'retained.json',{'status':'PRESERVED','record':record,'new_jobs':1,
            'execution_state':job['state'],'engineering_qualification':'UNKNOWN','constitutive_numerical_criterion':'UNKNOWN'})
    finally:assert wb.shutdown()['joined']
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
root=Path(sys.argv[1]);record=json.loads((root/'retained.json').read_text(encoding='utf-8'))['record']
wb=Workbench(root/'store',configuration={'workers':1})
try:
 count=len(wb.manager.list());doc=wb.document_open(kind='simulation',document_id=record['document_id'])
 assert canonical_hash(doc['draft']['settings'])==record['settings_sha256']
 result=wb.document_result(doc['id'],record['job_id']);assert canonical_hash(result['responses'])==record['responses_sha256']
 calculation=wb.root/'results'/record['job_id']/'calculation'
 assert file_hash(calculation/'result.json')==record['result_sha256']
 if record['history_sha256']:assert file_hash(calculation/'interface_history_observations.json')==record['history_sha256']
 assert len(wb.manager.list())==count
 save_json(root/'cold-reopen.json',{'status':'PASS','record':record,'new_jobs':0,'runtime_probed':False})
finally:assert wb.shutdown()['joined']
''',encoding='utf-8')
    process=run_owned_command([sys.executable,str(child),str(output),str(REPO)],output,'history-cold-reopen',timeout=30,owned_tree=True)
    assert process.returncode==0
    assert job['state']=='SUCCEEDED',job
    assert actual['execution_status']=='SUCCEEDED'
    assert audit is not None
    assert len(audit['elements'])==1 and audit['elements'][0]['element_id']==2
    element=audit['elements'][0]
    assert element['strict_partial_times_s'],'No observed strict partial state; preserve inputs and do not retune'
    assert element['sampled_damage_nondecrease']=='OBSERVED'
    assert all(s['active']==1 and s['adjacent_bulk_activity']=={'1':[1],'3':[1]} for s in element['samples'])
    assert element['sampled_initial_basis_compressive_sign']=='OBSERVED'
    # Check exact source provenance without imposing response equality/thresholds.
    assert {relative:file_hash(REPO/relative) for relative in sources}==sources
