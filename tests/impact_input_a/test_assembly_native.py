"""Explicit opt-in small installed-runtime flat/assembly pairs; owned jobs only."""
from copy import deepcopy
import json
import os
from pathlib import Path
import runpy
import sys
import time
import pytest
from test_assembly_physics import hierarchical
from caelab.impact_model import BACKEND, model_from_settings, render
from caelab.impact_assembly import target_key, exact_entity
from caelab.impact_responses import QUANTITIES
from caelab.impact_source import capture
from caelab.storage import canonical_hash, save_json
from caelab.workbench import Workbench
from caelab.execution_control import run_owned_command
from caelab.evaluation import read_result, file_hash
from caelab.adapters.impact_results import read_vtk
from caelab.adapters.impact import ImpactAdapter

REPO=Path(__file__).resolve().parents[2]
pytestmark=pytest.mark.skipif(os.environ.get('CAELAB_RUN_ASSEMBLY_IMPACT')!='1',reason='Explicit bounded installed-runtime assembly check')


def source_settings(kind):
    if kind=='COH3D8':
        from examples.impact.cohesive_model import settings
        return settings()
    factory=runpy.run_path(str(REPO/'tests/test_impact_elastic_tetra_formulation.py'))['simple_settings']
    result=factory('C3D8' if kind=='C3D8R' else kind,plastic=kind in ('C3D8','C3D8R'))
    if kind=='C3D8R':result['source']['text']=result['source']['text'].replace('TYPE=C3D8,','TYPE=C3D8R,')
    result['responses']=[{'name':'stress','quantity':'stress','identity':1,'component':'zz'},
                         {'name':'displacement','quantity':'displacement','identity':4,'component':'Z'}]
    return result


def assembly_settings(original,folder):
    folder.mkdir();wrapped=hierarchical(original['source']['text'],second=False)
    # Retained root -> part include -> mesh include; model material cards stay global.
    start=wrapped.index('\n',wrapped.index('*PART'))+1;end=wrapped.index('*END PART')
    (folder/'mesh.inc').write_text(wrapped[start:end],encoding='ascii')
    (folder/'part.inc').write_text('*INCLUDE,INPUT=mesh.inc\n',encoding='ascii')
    root=wrapped[:start]+'*INCLUDE,INPUT=part.inc\n'+wrapped[end:]
    (folder/'root.inp').write_text(root,encoding='ascii')
    result=deepcopy(original);result['source']=capture(folder/'root.inp',folder)
    model=model_from_settings(result)
    for row in result['motions']:row['node_set']=target_key(model,'nsets','DROP.BODY-1.'+row['node_set'])
    for row in result['responses']:
        row['identity']=exact_entity(model,QUANTITIES[row['quantity']][1],'BODY-1',row['identity'])
    return result


def wait(wb,job):
    limit=time.monotonic()+180
    while time.monotonic()<limit:
        current=wb.manager.status(job['id'])
        if current['state'] in {'SUCCEEDED','FAILED','CANCELLED','PARTIAL_FAILURE','INTERRUPTED'}:return current
        time.sleep(.05)
    raise AssertionError('Small assigned native job exceeded 180 seconds; Workbench finally cleans owned jobs')


@pytest.mark.parametrize('kind',['COH3D8','C3D10','C3D8','C3D8R'])
def test_installed_flat_assembly_pair_saved_cold_reopen(kind):
    output=Path(os.environ['CAELAB_ASSEMBLY_RUN_ROOT']).resolve()/kind
    output.mkdir(parents=True,exist_ok=False)
    flat=source_settings(kind);assembled=assembly_settings(flat,output/'source')
    save_json(output/'declared-inputs.json',{'flat':flat,'assembly':assembled})
    snapshots={str(Path(p).resolve().relative_to(REPO)):file_hash(p) for p in ImpactAdapter.input_source_files}
    save_json(output/'source-sha256.json',snapshots)
    workspace=output/'workspace';wb=Workbench(workspace,configuration={'workers':1})
    records=[];results=[];folders=[]
    try:
        for title,settings in (('flat',flat),('assembly',assembled)):
            before=canonical_hash(settings)
            doc=wb.document_open(kind='simulation',title=kind+' '+title,draft={'backend':BACKEND,'settings':settings})
            def command(op):
                nonlocal doc
                receipt=wb.document_command(doc['id'],op,{},session_id=doc['session_id'],expected_generation=doc['generation'])
                doc=receipt.get('document',doc);return receipt
            command('document.save');job=wait(wb,command('simulation.evaluate')['job'])
            save_json(output/(title+'-job.json'),job)
            folder=wb.root/'results'/job['id']/'calculation';folders.append(folder)
            if folder.is_dir() and (folder/'result.json').is_file():
                actual=read_result(folder,verify='all');save_json(output/(title+'-observed.json'),actual)
            assert job['state']=='SUCCEEDED',job
            actual=wb.document_result(doc['id'],job['id']);assert actual['execution_status']=='SUCCEEDED',actual
            assert canonical_hash(settings)==before
            for selected in settings['responses']:
                response=actual['responses'][selected['name']];quantity=QUANTITIES[selected['quantity']]
                assert response['metadata']['status']=='AVAILABLE' and response['value'] and response['axes'][0]['values']
                assert len(response['value'])==len(response['axes'][0]['values'])
                assert all(value is not None for value in response['raw_samples']['native_values'])
                assert response['unit']==quantity[3] and response['measure']==quantity[5] and response['component']==selected['component']
                assert response['metadata']['origin']==('DERIVED' if selected['quantity'] in ('cohesive_opening','cohesive_slip','contact_impulse') else 'NATIVE')
            if kind=='COH3D8':
                assert actual['responses']['damage']['value']
                assert actual['responses']['opening']['metadata']['origin']=='DERIVED'
            command('document.save')
            records.append({'document_id':doc['id'],'job_id':job['id'],'settings_sha256':before,
                            'responses_sha256':canonical_hash(actual['responses'])})
            results.append(actual)
        # Compare the actual decoded retained arrays, not file hashes or log titles.
        first=sorted((folders[0]/'native').glob('frame*.vtk'));second=sorted((folders[1]/'native').glob('frame*.vtk'))
        assert first and len(first)==len(second)
        for a,b in zip(first,second):assert read_vtk(a)==read_vtk(b),(str(a),str(b))
        # Provenance differs; every declared scalar/vector, sample/time/unit and derived opening is exact.
        comparable=lambda response:{key:value for key,value in response.items() if key in ('kind','unit','component','location','frame','measure','reduction','value','axes','raw_samples')}
        assert {k:comparable(v) for k,v in results[0]['responses'].items()}=={k:comparable(v) for k,v in results[1]['responses'].items()}
        save_json(output/'pair.json',{'status':'PASS','kind':kind,'records':records,'frame_count':len(first),
            'comparison':'EXACT_RETAINED_SAMPLES','engineering_qualification':'UNKNOWN','source_sha256':snapshots})
        assert {name:file_hash(REPO/name) for name in snapshots}==snapshots,'Source changed during actual run; preserve and inspect both source receipts'
    finally:
        assert wb.shutdown()['joined']
    save_json(output/'reopen-request.json',records)
    child=output/'reopen.py'
    child.write_text('''from pathlib import Path
import json,sys
sys.path.insert(0,sys.argv[2])
from caelab.workbench import Workbench
from caelab.storage import canonical_hash,save_json
import caelab.adapters.impact as adapter
def forbidden(*args,**kwargs):raise AssertionError('Cold reopen must not run or probe a solver')
adapter.selected_runtime=forbidden;adapter.run_owned_command=forbidden
root=Path(sys.argv[1]);records=json.loads((root/'reopen-request.json').read_text(encoding='utf-8'))
wb=Workbench(root/'workspace',configuration={'workers':1})
try:
 count=len(wb.manager.list())
 for item in records:
  doc=wb.document_open(kind='simulation',document_id=item['document_id'])
  assert canonical_hash(doc['draft']['settings'])==item['settings_sha256']
  result=wb.document_result(doc['id'],item['job_id'])
  assert canonical_hash(result['responses'])==item['responses_sha256']
 assert len(wb.manager.list())==count
 save_json(root/'cold-reopen.json',{'status':'PASS','same_documents':records,'new_jobs':0,'runtime_probed':False})
finally:assert wb.shutdown()['joined']
''',encoding='utf-8')
    child_result=run_owned_command([sys.executable,str(child),str(output),str(REPO)],output,'assembly-cold-reopen',timeout=30,owned_tree=True)
    assert child_result.returncode==0
