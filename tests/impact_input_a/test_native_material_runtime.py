"""Opt-in two bounded existing-input RAD runs; no campaign or material calibration."""
import json
import os
from pathlib import Path
import sys
import time
import pytest
from native_material_fixtures import make_native
from caelab.impact_native import settings_from_source,parse_source,edit_field
from caelab.impact_input_edits import original_files,edited_files
from caelab.impact_reference_bindings import KEY,snapshot
from caelab.impact_model import BACKEND,validate_settings
from caelab.storage import save_json,canonical_hash
from caelab.workbench import Workbench
from caelab.adapters.impact import ImpactAdapter
from caelab.evaluation import read_result,file_hash
from caelab.execution_control import run_owned_command

REPO=Path(__file__).resolve().parents[2]
pytestmark=pytest.mark.skipif(os.environ.get('CAELAB_RUN_NATIVE_RAD_MATERIALS')!='1',reason='Explicit bounded installed-runtime RAD check')


@pytest.mark.parametrize('kind',['bulk','interface'])
def test_native_material_edit_run_save_and_cold_reopen(kind):
    output=Path(os.environ['CAELAB_NATIVE_RAD_RUN_ROOT']).resolve()/kind
    output.mkdir(parents=True,exist_ok=False)
    declared,_,_,source=make_native(output/'original',kind)
    settings=settings_from_source(source)
    key,value=('gf_n_mm',.025) if kind=='bulk' else ('normal_strength_mpa',2.1)
    field=next(row for row in parse_source(source)['fields'] if row['field']==key)
    settings=edit_field(settings,field['id'],value,reason='사전 명시 물성 편집',expected_source_sha256=canonical_hash(source))
    # Explicit output edit, recorded separately from constitutive parameters.
    field=next(row for row in parse_source(settings['source'])['fields'] if row['field']=='field_interval_s')
    settings=edit_field(settings,field['id'],declared['time']['field_interval_s']/2,
        reason='장면 출력 간격 명시 편집',expected_source_sha256=canonical_hash(settings['source']))
    settings['responses']=declared['responses']
    settings['b_responses']=declared.get('b_responses',[])
    settings[KEY]=snapshot(settings);validate_settings(settings)
    assert original_files(settings['source'])==original_files(source)
    save_json(output/'declared-inputs.json',{'original':declared,'native':settings,'explicit_edit':{key:value},'source_unchanged':True})
    sources={str(Path(p).resolve().relative_to(REPO)):file_hash(p) for p in ImpactAdapter.input_source_files}
    save_json(output/'source-sha256.json',sources)
    wb=Workbench(output/'store',configuration={'workers':1})
    try:
        doc=wb.document_open(kind='simulation',title='원 RAD '+kind,draft={'backend':BACKEND,'settings':settings})
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
        if (calculation/'result.json').is_file():save_json(output/'observed.json',read_result(calculation,verify='all'))
        assert job['state']=='SUCCEEDED',job
        actual=wb.document_result(doc['id'],job['id'])
        assert actual['execution_status']=='SUCCEEDED',actual
        for name,raw in edited_files(settings['source']).items():assert (calculation/'native'/name).read_bytes()==raw
        assert json.loads((calculation/'native_direct_export.json').read_text())['converter_execution']=='NOT_PERFORMED'
        command('document.save')
        record={'document_id':doc['id'],'job_id':job['id'],'settings_sha256':canonical_hash(settings),'responses_sha256':canonical_hash(actual['responses'])}
        save_json(output/'retained.json',{'status':'PASS','record':record,'observations':{
            key:{'status':response.get('metadata',{}).get('status','UNKNOWN'),'value_count':len(response.get('value',[])),
                 'unit':response.get('unit'),'measure':response.get('measure')}
            for key,response in actual['responses'].items()},'engineering_qualification':'UNKNOWN'})
        assert {name:file_hash(REPO/name) for name in sources}==sources,'Preserve both source revisions; do not attribute another source to this run'
    finally:assert wb.shutdown()['joined']
    child=output/'reopen.py'
    child.write_text('''from pathlib import Path
import sys,json
sys.path.insert(0,sys.argv[2])
from caelab.workbench import Workbench
from caelab.storage import canonical_hash,save_json
import caelab.adapters.impact as adapter
def forbidden(*a,**k):raise AssertionError('Cold reopen must not probe or execute a solver')
adapter.selected_runtime=forbidden;adapter.run_owned_command=forbidden
root=Path(sys.argv[1]);record=json.loads((root/'retained.json').read_text(encoding='utf-8'))['record']
wb=Workbench(root/'store',configuration={'workers':1})
try:
 count=len(wb.manager.list());doc=wb.document_open(kind='simulation',document_id=record['document_id'])
 assert canonical_hash(doc['draft']['settings'])==record['settings_sha256']
 result=wb.document_result(doc['id'],record['job_id']);assert canonical_hash(result['responses'])==record['responses_sha256']
 assert len(wb.manager.list())==count
 save_json(root/'cold-reopen.json',{'status':'PASS','record':record,'new_jobs':0,'runtime_probed':False})
finally:assert wb.shutdown()['joined']
''',encoding='utf-8')
    process=run_owned_command([sys.executable,str(child),str(output),str(REPO)],output,'native-rad-cold-reopen',timeout=30,owned_tree=True)
    assert process.returncode==0
